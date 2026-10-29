from datetime import datetime
from typing import Literal, Optional
from uuid import UUID

from pydantic import BaseModel, EmailStr, field_validator


# ─── Auth ───────────────────────────────────────────────────────────────────

class CustomerLogin(BaseModel):
    email: str
    password: str


class CustomerCreate(BaseModel):
    name: str
    email: str
    password: str
    phone: Optional[str] = None


class CustomerOut(BaseModel):
    id: UUID
    name: str
    email: str
    phone: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


# ─── Orders ─────────────────────────────────────────────────────────────────

class OrderItemOut(BaseModel):
    id: UUID
    sku: str
    name: str
    qty: int
    price: float

    model_config = {"from_attributes": True}


class OrderOut(BaseModel):
    id: UUID
    customer_id: UUID
    status: str
    total: float
    currency: str
    placed_at: datetime
    dispatched_at: Optional[datetime] = None
    delivered_at: Optional[datetime] = None
    address_json: dict
    items: list[OrderItemOut] = []

    model_config = {"from_attributes": True}


# ─── Conversations & Chat ────────────────────────────────────────────────────

class ConversationCreate(BaseModel):
    customer_id: UUID


class ConversationOut(BaseModel):
    id: UUID
    customer_id: UUID
    ticket_id: Optional[UUID] = None
    state: str
    started_at: datetime
    ended_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class MessageOut(BaseModel):
    id: UUID
    conversation_id: UUID
    role: str
    content: str
    created_at: datetime

    model_config = {"from_attributes": True}


class ChatRequest(BaseModel):
    conversation_id: Optional[str] = None
    message: str


class ChatResponse(BaseModel):
    conversation_id: str
    reply: str
    state: str
    requires_approval: bool


# ─── Approvals ───────────────────────────────────────────────────────────────

class ApprovalOut(BaseModel):
    id: UUID
    conversation_id: UUID
    action: str
    args_json: dict
    reasoning: Optional[str] = None
    status: str
    reviewer_id: Optional[UUID] = None
    decided_at: Optional[datetime] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class ApprovalDecision(BaseModel):
    action: Literal["approve", "reject"]
    reason: Optional[str] = None


# ─── Tool Calls ──────────────────────────────────────────────────────────────

class ToolCallOut(BaseModel):
    id: UUID
    conversation_id: UUID
    tool: str
    args_json: Optional[dict] = None
    result_json: Optional[dict] = None
    latency_ms: Optional[int] = None
    cost_usd: Optional[float] = None
    created_at: datetime

    model_config = {"from_attributes": True}


# ─── Metrics ─────────────────────────────────────────────────────────────────

class MetricsOut(BaseModel):
    total_conversations: int
    resolved_count: int
    escalated_count: int
    pending_approvals_count: int
    total_refunds_amount: float
    avg_tool_calls_per_conversation: float


# ─── Tickets ─────────────────────────────────────────────────────────────────

class TicketOut(BaseModel):
    id: UUID
    customer_id: UUID
    status: str
    priority: str
    summary: str
    assigned_to: Optional[UUID] = None
    created_at: datetime

    model_config = {"from_attributes": True}


# ─── Tool Validation Schemas ──────────────────────────────────────────────────

class AddressModel(BaseModel):
    line1: str
    line2: Optional[str] = ""
    city: str
    state: str
    pincode: str


class GetOrderInput(BaseModel):
    order_id: str


class TrackShipmentInput(BaseModel):
    order_id: str


class UpdateAddressInput(BaseModel):
    order_id: str
    new_address: AddressModel


class CheckRefundEligibilityInput(BaseModel):
    order_id: str
    reason: str = ""


class CreateRefundInput(BaseModel):
    order_id: str
    amount: float
    reason: str = ""


class CreateReplacementInput(BaseModel):
    order_id: str
    item_id: str
    reason: str = ""


class SearchPolicyInput(BaseModel):
    query: str


class CreateTicketInput(BaseModel):
    summary: str
    priority: Literal["low", "medium", "high", "urgent"] = "medium"

