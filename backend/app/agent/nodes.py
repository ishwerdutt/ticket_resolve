"""LangGraph node functions for the ThreadNest AI Support Agent."""
import json
import logging
from typing import Any

from fastapi import HTTPException
from pydantic import ValidationError
from openai import AsyncOpenAI
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.agent.prompts import INTENT_CLASSIFICATION_PROMPT, SYSTEM_PROMPT
from app.agent.state import AgentState
from app.config import settings
from app.models.db import Order
from app.models.schemas import (
    CheckRefundEligibilityInput,
    CreateRefundInput,
    CreateReplacementInput,
    CreateTicketInput,
    GetOrderInput,
    SearchPolicyInput,
    TrackShipmentInput,
    UpdateAddressInput,
)
from app.tools.registry import TOOL_SCHEMAS

logger = logging.getLogger(__name__)

TOOL_VALIDATORS = {
    "get_order": GetOrderInput,
    "track_shipment": TrackShipmentInput,
    "update_address": UpdateAddressInput,
    "check_refund_eligibility": CheckRefundEligibilityInput,
    "create_refund": CreateRefundInput,
    "create_replacement": CreateReplacementInput,
    "search_policy": SearchPolicyInput,
    "create_ticket": CreateTicketInput,
}

_openai_client: AsyncOpenAI | None = None


def _get_client() -> AsyncOpenAI:
    global _openai_client
    if _openai_client is None:
        _openai_client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
    return _openai_client


# ─── Intent Classification Node ──────────────────────────────────────────────

async def classify_intent_node(state: AgentState) -> dict:
    """Classify the customer's last message into an intent category."""
    messages = state.get("messages", [])
    if not messages:
        return {"intent": "unknown"}

    # Get the last user message
    last_user_msg = next(
        (m["content"] for m in reversed(messages) if m["role"] == "user"),
        "",
    )

    try:
        client = _get_client()
        response = await client.chat.completions.create(
            model=settings.MODEL_NAME,
            messages=[
                {"role": "system", "content": INTENT_CLASSIFICATION_PROMPT},
                {"role": "user", "content": last_user_msg},
            ],
            max_tokens=20,
            temperature=0,
        )
        intent = response.choices[0].message.content.strip().lower()

        valid_intents = {
            "order_status", "track_shipment", "address_change", "refund",
            "replacement", "policy_question", "escalation", "unknown",
        }
        if intent not in valid_intents:
            intent = "unknown"
    except Exception as e:
        logger.warning(f"Intent classification failed: {e}")
        intent = "unknown"

    return {"intent": intent, "state": "IDENTIFIED"}


# ─── Load Context Node ────────────────────────────────────────────────────────

def make_load_context_node(db: AsyncSession):
    """Factory that creates load_context_node with DB access."""

    async def load_context_node(state: AgentState) -> dict:
        """Fetch the customer's 3 most recent orders as context."""
        customer_id = state.get("customer_id")
        if not customer_id:
            return {"customer_context": {}}

        try:
            result = await db.execute(
                select(Order)
                .options(selectinload(Order.items))
                .where(Order.customer_id == customer_id)
                .order_by(Order.placed_at.desc())
                .limit(3)
            )
            orders = result.scalars().all()

            customer_context = {
                "recent_orders": [
                    {
                        "order_id": str(o.id),
                        "status": o.status,
                        "total": float(o.total),
                        "currency": o.currency,
                        "placed_at": o.placed_at.isoformat() if o.placed_at else None,
                        "items": [
                            {"item_id": str(i.id), "name": i.name, "qty": i.qty, "price": float(i.price)}
                            for i in o.items
                        ],
                    }
                    for o in orders
                ]
            }
        except Exception as e:
            logger.warning(f"Failed to load customer context: {e}")
            customer_context = {"recent_orders": []}

        return {"customer_context": customer_context, "state": "GATHERING_INFO"}

    return load_context_node


# ─── Agent Step Node ──────────────────────────────────────────────────────────

def make_agent_step_node(db: AsyncSession):
    """Factory that creates agent_step_node with DB access."""

    async def agent_step_node(state: AgentState) -> dict:
        """Main agent node: call OpenAI, handle tool calls, return updated state."""
        messages = list(state.get("messages", []))
        customer_context = state.get("customer_context", {})
        tool_calls_count = state.get("tool_calls_count", 0)
        conversation_id = state.get("conversation_id", "unknown")
        customer_id = state.get("customer_id", "")
        intent = state.get("intent", "unknown")

        # Build context injection for system prompt
        context_str = ""
        if customer_context.get("recent_orders"):
            context_str = f"\n\n## Customer's Recent Orders\n{json.dumps(customer_context['recent_orders'], indent=2)}"

        # Check max steps guard
        if tool_calls_count >= settings.AGENT_MAX_STEPS:
            return {
                "final_response": (
                    "I've reached the maximum number of actions for this turn. "
                    "Please send another message to continue, and I'll pick up right where we left off."
                ),
                "state": "GATHERING_INFO",
            }

        # Build messages for OpenAI
        openai_messages = [
            {"role": "system", "content": SYSTEM_PROMPT + context_str},
        ] + messages

        try:
            client = _get_client()
            response = await client.chat.completions.create(
                model=settings.MODEL_NAME,
                messages=openai_messages,
                tools=TOOL_SCHEMAS,
                tool_choice="auto",
                temperature=0.3,
            )
        except Exception as e:
            logger.error(f"OpenAI call failed: {e}")
            return {
                "final_response": "I'm sorry, I encountered a technical issue. Please try again.",
                "error": str(e),
                "state": state.get("state", "NEW"),
            }

        choice = response.choices[0]
        assistant_message = choice.message

        # No tool calls → final response
        if not assistant_message.tool_calls:
            final_text = assistant_message.content or ""
            messages.append({"role": "assistant", "content": final_text})
            return {
                "messages": messages,
                "final_response": final_text,
                "state": _infer_state(intent, state),
            }

        # Handle tool calls
        # Add assistant message with tool_calls to history
        messages.append({
            "role": "assistant",
            "content": assistant_message.content or "",
            "tool_calls": [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                }
                for tc in assistant_message.tool_calls
            ],
        })

        pending_approval_id = state.get("pending_approval_id")

        for tool_call in assistant_message.tool_calls:
            tool_name = tool_call.function.name
            try:
                tool_args = json.loads(tool_call.function.arguments)
            except json.JSONDecodeError:
                tool_args = {}

            tool_result = await _dispatch_tool(
                tool_name=tool_name,
                tool_args=tool_args,
                customer_id=customer_id,
                conversation_id=conversation_id,
                db=db,
            )

            # Track pending approval
            if isinstance(tool_result, dict) and tool_result.get("approval_id"):
                pending_approval_id = tool_result["approval_id"]

            messages.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": json.dumps(tool_result),
            })
            tool_calls_count += 1

        new_conv_state = "ACTING"
        if pending_approval_id:
            new_conv_state = "AWAITING_APPROVAL"

        return {
            "messages": messages,
            "tool_calls_count": tool_calls_count,
            "pending_approval_id": pending_approval_id,
            "state": new_conv_state,
            # No final_response yet — loop back to agent
        }

    return agent_step_node


async def _dispatch_tool(
    tool_name: str,
    tool_args: dict,
    customer_id: str,
    conversation_id: str,
    db: AsyncSession,
) -> Any:
    """Dispatch a tool call to the appropriate tool function with Pydantic validation."""
    validator = TOOL_VALIDATORS.get(tool_name)
    if validator:
        try:
            validated = validator.model_validate(tool_args)
            tool_args = validated.model_dump()
        except ValidationError as ve:
            errors = [f"{err['loc']}: {err['msg']}" for err in ve.errors()]
            logger.warning(f"Validation failed for tool '{tool_name}': {errors}")
            return {"error": f"Invalid arguments for {tool_name}: {', '.join(errors)}", "tool": tool_name}

    try:
        if tool_name == "get_order":
            from app.tools.order_tools import get_order
            return await get_order(
                order_id=tool_args["order_id"],
                customer_id=customer_id,
                db=db,
                conversation_id=conversation_id,
            )

        elif tool_name == "track_shipment":
            from app.tools.order_tools import track_shipment
            return await track_shipment(
                order_id=tool_args["order_id"],
                customer_id=customer_id,
                db=db,
                conversation_id=conversation_id,
            )

        elif tool_name == "update_address":
            from app.tools.order_tools import update_address
            return await update_address(
                order_id=tool_args["order_id"],
                new_address=tool_args["new_address"],
                customer_id=customer_id,
                db=db,
                conversation_id=conversation_id,
            )

        elif tool_name == "check_refund_eligibility":
            from app.tools.refund_tools import check_refund_eligibility
            return await check_refund_eligibility(
                order_id=tool_args["order_id"],
                reason=tool_args.get("reason", ""),
                customer_id=customer_id,
                db=db,
                conversation_id=conversation_id,
            )

        elif tool_name == "create_refund":
            from app.tools.refund_tools import create_refund
            return await create_refund(
                order_id=tool_args["order_id"],
                amount=tool_args["amount"],
                reason=tool_args.get("reason", ""),
                customer_id=customer_id,
                conversation_id=conversation_id,
                db=db,
            )

        elif tool_name == "create_replacement":
            from app.tools.replacement_tools import create_replacement
            return await create_replacement(
                order_id=tool_args["order_id"],
                item_id=tool_args["item_id"],
                reason=tool_args.get("reason", ""),
                customer_id=customer_id,
                conversation_id=conversation_id,
                db=db,
            )

        elif tool_name == "search_policy":
            from app.tools.policy_tools import search_policy
            return await search_policy(query=tool_args["query"], db=db)

        elif tool_name == "create_ticket":
            from app.tools.ticket_tools import create_ticket
            return await create_ticket(
                customer_id=customer_id,
                summary=tool_args["summary"],
                priority=tool_args.get("priority", "medium"),
                conversation_id=conversation_id,
                db=db,
            )

        else:
            return {"error": f"Unknown tool: {tool_name}"}

    except HTTPException as he:
        logger.warning(f"Tool '{tool_name}' returned HTTP {he.status_code}: {he.detail}")
        return {"error": he.detail, "status_code": he.status_code, "tool": tool_name}
    except Exception as e:
        logger.error(f"Tool '{tool_name}' raised an exception: {e}")
        return {"error": str(e), "tool": tool_name}


def _infer_state(intent: str | None, state: AgentState) -> str:
    """Infer the new conversation state after a final response."""
    current = state.get("state", "NEW")
    if current in ("ESCALATED", "AWAITING_APPROVAL"):
        return current
    if intent in ("refund", "replacement"):
        return "RESOLVED"
    return "RESOLVED"


# ─── Format Response Node ─────────────────────────────────────────────────────

async def format_response_node(state: AgentState) -> dict:
    """Extract the final response from the last assistant message."""
    final_response = state.get("final_response")
    if final_response:
        return {"final_response": final_response}

    # Fallback: search messages for last assistant message
    messages = state.get("messages", [])
    for msg in reversed(messages):
        if msg.get("role") == "assistant" and msg.get("content"):
            return {"final_response": msg["content"]}

    return {
        "final_response": "I'm sorry, I wasn't able to generate a response. Please try again."
    }
