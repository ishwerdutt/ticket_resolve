"""LangGraph state machine for the ThreadNest AI Support Agent."""
import logging
from typing import Any

from langgraph.graph import END, START, StateGraph
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.nodes import (
    classify_intent_node,
    format_response_node,
    make_agent_step_node,
    make_load_context_node,
)
from app.agent.state import AgentState
from app.config import settings

logger = logging.getLogger(__name__)


def _should_continue(state: AgentState) -> str:
    """Conditional edge: loop back to agent or move to format_response."""
    tool_calls_count = state.get("tool_calls_count", 0)
    final_response = state.get("final_response")

    if final_response is not None:
        return "format_response"
    if tool_calls_count >= settings.AGENT_MAX_STEPS:
        return "format_response"
    return "agent"


def build_graph(db: AsyncSession) -> Any:
    """Build and compile the LangGraph state machine with DB access."""
    load_context = make_load_context_node(db)
    agent_step = make_agent_step_node(db)

    graph_builder = StateGraph(AgentState)

    # Add nodes
    graph_builder.add_node("classify", classify_intent_node)
    graph_builder.add_node("load_context", load_context)
    graph_builder.add_node("agent", agent_step)
    graph_builder.add_node("format_response", format_response_node)

    # Add edges
    graph_builder.add_edge(START, "classify")
    graph_builder.add_edge("classify", "load_context")
    graph_builder.add_edge("load_context", "agent")

    # Conditional: loop agent or proceed to format
    graph_builder.add_conditional_edges(
        "agent",
        _should_continue,
        {
            "agent": "agent",
            "format_response": "format_response",
        },
    )
    graph_builder.add_edge("format_response", END)

    return graph_builder.compile()


async def run_agent(
    conversation_id: str,
    customer_id: str,
    messages: list,
    db: AsyncSession,
) -> AgentState:
    """
    Run the agent graph for a single conversation turn.

    Args:
        conversation_id: UUID of the current conversation.
        customer_id: UUID of the authenticated customer.
        messages: List of message dicts with 'role' and 'content'.
        db: SQLAlchemy async session.

    Returns:
        Final AgentState after graph execution.
    """
    graph = build_graph(db)

    initial_state: AgentState = {
        "conversation_id": conversation_id,
        "customer_id": customer_id,
        "messages": messages,
        "intent": None,
        "customer_context": {},
        "tool_calls_count": 0,
        "state": "NEW",
        "pending_approval_id": None,
        "final_response": None,
        "error": None,
    }

    try:
        result = await graph.ainvoke(initial_state)
        return result
    except Exception as e:
        logger.error(f"Agent graph execution failed: {e}")
        return {
            **initial_state,
            "final_response": "I'm sorry, I encountered an unexpected error. Please try again.",
            "error": str(e),
            "state": "NEW",
        }
