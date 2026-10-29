"""
ThreadNest Database Seed Script

Creates realistic test data for 5 Indian customers, 2 staff members,
and a variety of orders with different statuses.

Run with: python -m seed.seed
"""
import asyncio
import os
import uuid
from datetime import datetime, timedelta, timezone

import asyncpg
import bcrypt as _bcrypt


def _hash_password(password: str) -> str:
    return _bcrypt.hashpw(password.encode(), _bcrypt.gensalt()).decode()


# Shim so the rest of the file works unchanged
class _PwdContext:
    def hash(self, password: str) -> str:
        return _hash_password(password)


pwd_context = _PwdContext()

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://support_user:support_pass@localhost:5432/ai_support",
)

# Convert SQLAlchemy URL to asyncpg DSN
def to_asyncpg_dsn(url: str) -> str:
    return url.replace("postgresql+asyncpg://", "postgresql://")


CUSTOMERS = [
    {"name": "Priya Sharma", "email": "priya.sharma@example.com", "phone": "+91-9876543210"},
    {"name": "Arjun Mehta", "email": "arjun.mehta@example.com", "phone": "+91-9123456789"},
    {"name": "Kavya Nair", "email": "kavya.nair@example.com", "phone": "+91-9988776655"},
    {"name": "Rohit Gupta", "email": "rohit.gupta@example.com", "phone": "+91-9654321098"},
    {"name": "Ananya Reddy", "email": "ananya.reddy@example.com", "phone": "+91-9871234560"},
]

STAFF = [
    {"name": "Rahul Verma", "email": "reviewer@threadnest.com", "role": "reviewer"},
    {"name": "Sneha Patel", "email": "admin@threadnest.com", "role": "admin"},
]

PRODUCTS = [
    {"sku": "TN-TSH-001", "name": "ThreadNest Classic T-Shirt", "price": 599.00},
    {"sku": "TN-JNS-002", "name": "ThreadNest Slim Fit Jeans", "price": 1499.00},
    {"sku": "TN-KRT-003", "name": "ThreadNest Festive Kurta", "price": 899.00},
    {"sku": "TN-DRS-004", "name": "ThreadNest Summer Dress", "price": 1299.00},
    {"sku": "TN-HOD-005", "name": "ThreadNest Premium Hoodie", "price": 1199.00},
    {"sku": "TN-SAR-006", "name": "ThreadNest Silk Saree", "price": 2499.00},
]

ADDRESSES = [
    {"line1": "42 MG Road", "line2": "Koramangala", "city": "Bengaluru", "state": "Karnataka", "pincode": "560034"},
    {"line1": "15 Park Street", "line2": "Flat 3B", "city": "Mumbai", "state": "Maharashtra", "pincode": "400001"},
    {"line1": "8 Anna Salai", "line2": "", "city": "Chennai", "state": "Tamil Nadu", "pincode": "600002"},
    {"line1": "27 Connaught Place", "line2": "Block D", "city": "New Delhi", "state": "Delhi", "pincode": "110001"},
    {"line1": "103 Banjara Hills", "line2": "Road No. 12", "city": "Hyderabad", "state": "Telangana", "pincode": "500034"},
]

now = datetime.now(timezone.utc)

ORDER_SCENARIOS = [
    # (status, placed_days_ago, dispatched_days_ago, delivered_days_ago)
    # delivered 35 days ago → ineligible for refund
    ("delivered", 40, 37, 35),
    # delivered 5 days ago → eligible for refund (small amount)
    ("delivered", 10, 7, 5),
    # delivered 3 days ago → eligible for refund (large amount)
    ("delivered", 8, 6, 3),
    # dispatched (in transit)
    ("dispatched", 4, 2, None),
    # pending (address can be changed)
    ("pending", 1, None, None),
    # confirmed
    ("confirmed", 2, None, None),
    # cancelled
    ("cancelled", 15, None, None),
]


async def seed():
    dsn = to_asyncpg_dsn(DATABASE_URL)
    print(f"🔗 Connecting to: {dsn.split('@')[1]}")  # hide credentials

    conn = await asyncpg.connect(dsn)

    try:
        # ── Customers ──────────────────────────────────────────────────────────
        print("\n👥 Creating customers...")
        customer_password_hash = pwd_context.hash("password123")
        customer_ids = []

        for c in CUSTOMERS:
            cid = str(uuid.uuid4())
            await conn.execute(
                """
                INSERT INTO customers (id, name, email, phone, password_hash)
                VALUES ($1, $2, $3, $4, $5)
                ON CONFLICT (email) DO NOTHING
                """,
                cid, c["name"], c["email"], c["phone"], customer_password_hash,
            )
            # Fetch the actual ID (in case of conflict)
            row = await conn.fetchrow("SELECT id FROM customers WHERE email = $1", c["email"])
            customer_ids.append(str(row["id"]))
            print(f"  ✅ {c['name']} ({c['email']})")

        # ── Staff ──────────────────────────────────────────────────────────────
        print("\n👔 Creating staff...")
        staff_password_hash = pwd_context.hash("staffpass123")
        staff_ids = []

        for s in STAFF:
            sid = str(uuid.uuid4())
            await conn.execute(
                """
                INSERT INTO staff (id, name, email, password_hash, role)
                VALUES ($1, $2, $3, $4, $5)
                ON CONFLICT (email) DO NOTHING
                """,
                sid, s["name"], s["email"], staff_password_hash, s["role"],
            )
            row = await conn.fetchrow("SELECT id FROM staff WHERE email = $1", s["email"])
            staff_ids.append(str(row["id"]))
            print(f"  ✅ {s['name']} ({s['role']}) — {s['email']}")

        # ── Orders ─────────────────────────────────────────────────────────────
        print("\n📦 Creating orders...")
        import json
        import random

        order_ids = []
        order_item_ids = []  # list of (order_id, item_id, customer_id)

        scenario_cycle = list(enumerate(ORDER_SCENARIOS))

        for ci, customer_id in enumerate(customer_ids):
            # Each customer gets 2-3 orders
            num_orders = 2 if ci % 2 == 0 else 3
            addr = ADDRESSES[ci % len(ADDRESSES)]

            for oi in range(num_orders):
                scenario_idx = (ci * 3 + oi) % len(ORDER_SCENARIOS)
                status, placed_days, disp_days, deliv_days = ORDER_SCENARIOS[scenario_idx]

                placed_at = now - timedelta(days=placed_days)
                dispatched_at = (now - timedelta(days=disp_days)) if disp_days is not None else None
                delivered_at = (now - timedelta(days=deliv_days)) if deliv_days is not None else None

                # Pick 1-3 random products
                products = random.sample(PRODUCTS, random.randint(1, 3))
                total = sum(p["price"] for p in products)

                oid = str(uuid.uuid4())
                await conn.execute(
                    """
                    INSERT INTO orders (id, customer_id, status, total, currency,
                                        placed_at, dispatched_at, delivered_at, address_json)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                    """,
                    oid, customer_id, status, total, "INR",
                    placed_at, dispatched_at, delivered_at, json.dumps(addr),
                )
                order_ids.append(oid)

                item_ids_for_order = []
                for product in products:
                    iid = str(uuid.uuid4())
                    await conn.execute(
                        """
                        INSERT INTO order_items (id, order_id, sku, name, qty, price)
                        VALUES ($1, $2, $3, $4, $5, $6)
                        """,
                        iid, oid, product["sku"], product["name"], 1, product["price"],
                    )
                    item_ids_for_order.append(iid)
                    order_item_ids.append((oid, iid, customer_id))

                items_str = ", ".join(p["name"] for p in products)
                print(f"  ✅ Order {oid[:8]}... | {status} | ₹{total:.2f} | {items_str}")

        # ── Tickets ────────────────────────────────────────────────────────────
        print("\n🎫 Creating sample tickets...")

        ticket_data = [
            (customer_ids[0], "medium", "Customer reports wrong size delivered for kurta order"),
            (customer_ids[2], "high", "Customer received damaged saree and is requesting urgent replacement"),
        ]

        ticket_ids = []
        for cid, priority, summary in ticket_data:
            tid = str(uuid.uuid4())
            await conn.execute(
                """
                INSERT INTO tickets (id, customer_id, status, priority, summary)
                VALUES ($1, $2, $3, $4, $5)
                """,
                tid, cid, "open", priority, summary,
            )
            ticket_ids.append(tid)
            print(f"  ✅ Ticket {tid[:8]}... | {priority} priority | {summary[:50]}...")

        # ── Summary ────────────────────────────────────────────────────────────
        print("\n" + "="*60)
        print("🎉 Seed complete!")
        print("="*60)
        print(f"  Customers : {len(customer_ids)}")
        print(f"  Staff     : {len(staff_ids)}")
        print(f"  Orders    : {len(order_ids)}")
        print(f"  Items     : {len(order_item_ids)}")
        print(f"  Tickets   : {len(ticket_ids)}")
        print()
        print("📋 Login credentials:")
        print("  Customers  — any of the emails above, password: password123")
        print("  Reviewer   — reviewer@threadnest.com, password: staffpass123")
        print("  Admin      — admin@threadnest.com, password: staffpass123")
        print()
        print("💡 Useful order IDs for testing:")
        print(f"  Delivered 35d ago (ineligible refund) : see orders for priya.sharma@example.com")
        print(f"  Delivered recently (eligible refund)  : see orders for arjun.mehta@example.com")

    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(seed())
