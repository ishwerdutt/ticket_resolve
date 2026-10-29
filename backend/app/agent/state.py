from typing import TypedDict


class AgentState(TypedDict):
    conversation_id: str
    customer_id: str
    messages: list  # list of dicts with role/content
    intent: str | None
    customer_context: dict  # recent orders, open tickets
    tool_calls_count: int
    state: str  # NEW, IDENTIFIED, GATHERING_INFO, ACTING, AWAITING_APPROVAL, RESOLVED, ESCALATED
    pending_approval_id: str | None
    final_response: str | None
    error: str | None
