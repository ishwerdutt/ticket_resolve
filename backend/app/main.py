"""ThreadNest AI Support Agent - FastAPI application."""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.database import engine


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Verify DB connection on startup
    async with engine.connect() as conn:
        await conn.execute(text("SELECT 1"))
    yield
    await engine.dispose()


app = FastAPI(
    title="ThreadNest AI Support Agent",
    description="AI-powered customer support for ThreadNest clothing store",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Restrict in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Auth routes (inline for simplicity)
from fastapi import Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.auth.jwt import create_access_token, verify_password
from app.database import get_db
from app.models.schemas import CustomerLogin, Token


@app.post("/auth/login", response_model=Token, tags=["auth"])
async def login(credentials: CustomerLogin, db: AsyncSession = Depends(get_db)):
    """Customer login - returns JWT token."""
    from app.models.db import Customer
    result = await db.execute(select(Customer).where(Customer.email == credentials.email))
    customer = result.scalar_one_or_none()
    if not customer or not verify_password(credentials.password, customer.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    token = create_access_token(str(customer.id), customer.email, role="customer")
    return Token(access_token=token, token_type="bearer")


@app.post("/auth/staff/login", response_model=Token, tags=["auth"])
async def staff_login(credentials: CustomerLogin, db: AsyncSession = Depends(get_db)):
    """Staff login - returns JWT token with staff role."""
    from app.models.db import Staff
    result = await db.execute(select(Staff).where(Staff.email == credentials.email))
    staff = result.scalar_one_or_none()
    if not staff or not verify_password(credentials.password, staff.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    token = create_access_token(str(staff.id), staff.email, role=staff.role)
    return Token(access_token=token, token_type="bearer")


@app.get("/health", tags=["health"])
async def health():
    return {"status": "ok", "service": "ThreadNest AI Support Agent"}


# Include routers
from app.api.chat import router as chat_router
from app.api.approvals import router as approvals_router
from app.api.admin import router as admin_router
from app.api.tickets import router as tickets_router

app.include_router(chat_router)
app.include_router(approvals_router)
app.include_router(admin_router)
app.include_router(tickets_router)
