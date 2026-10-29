"""Chat API endpoints."""
from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_customer
from app.database import get_db
from app.models.schemas import ChatRequest, ChatResponse

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    current_user: dict = Depends(get_current_customer),
    db: AsyncSession = Depends(get_db),
) -> ChatResponse:
    """Send a message and get a reply from the AI agent."""
    # Import here to avoid circular imports
    from app.agent.graph import run_agent
    from app.models.db import Conversation, Message
    from sqlalchemy import select

    customer_id = current_user["customer_id"]

    # Get or create conversation
    conv = None
    if request.conversation_id:
        result = await db.execute(
            select(Conversation).where(
                Conversation.id == request.conversation_id,
                Conversation.customer_id == customer_id,
            )
        )
        conv = result.scalar_one_or_none()

    if not conv:
        conv = Conversation(customer_id=customer_id, state="NEW")
        db.add(conv)
        await db.flush()

    # Save user message
    user_msg = Message(
        conversation_id=str(conv.id),
        role="user",
        content=request.message,
    )
    db.add(user_msg)
    await db.flush()

    # Load conversation history
    history_result = await db.execute(
        select(Message)
        .where(Message.conversation_id == str(conv.id))
        .order_by(Message.created_at)
        .limit(20)
    )
    history = history_result.scalars().all()
    messages = [{"role": m.role, "content": m.content} for m in history]

    # Run agent
    result = await run_agent(
        conversation_id=str(conv.id),
        customer_id=customer_id,
        messages=messages,
        db=db,
    )

    # Save assistant reply
    reply = result.get("final_response", "I'm sorry, I couldn't process your request.")
    assistant_msg = Message(
        conversation_id=str(conv.id),
        role="assistant",
        content=reply,
    )
    db.add(assistant_msg)

    # Update conversation state
    conv.state = result.get("state", conv.state)

    await db.commit()

    return ChatResponse(
        conversation_id=str(conv.id),
        reply=reply,
        state=conv.state,
        requires_approval=bool(result.get("pending_approval_id")),
    )


@router.websocket("/ws/{conversation_id}")
async def websocket_chat(websocket: WebSocket, conversation_id: str):
    """WebSocket chat endpoint (placeholder for streaming)."""
    await websocket.accept()
    try:
        while True:
            data = await websocket.receive_text()
            await websocket.send_text(f"Echo: {data} (WebSocket streaming coming in v2)")
    except WebSocketDisconnect:
        pass
