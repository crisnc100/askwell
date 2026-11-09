"""The synthetic fieldservice schema, defined once in SQLAlchemy Core.

It runs on Postgres (the seeded demo DB) and SQLite (test fixtures). Timestamps
are naive UTC so both engines store the same values.
"""

from __future__ import annotations

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    MetaData,
    Numeric,
    String,
    Table,
)

metadata = MetaData()

customers = Table(
    "customers",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("name", String(120), nullable=False),
    Column("segment", String(20), nullable=False),  # residential | commercial | industrial
    Column("region", String(20), nullable=False),  # north | south | east | west | central
    Column("created_at", Date, nullable=False),
    Column("is_active", Boolean, nullable=False),
)

sites = Table(
    "sites",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("customer_id", Integer, ForeignKey("customers.id"), nullable=False),
    Column("name", String(160), nullable=False),
    Column("city", String(80), nullable=False),
    Column("state", String(2), nullable=False),
    # office | warehouse | retail | residence | plant
    Column("site_type", String(20), nullable=False),
)

technicians = Table(
    "technicians",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("full_name", String(120), nullable=False),
    Column("skill_level", String(10), nullable=False),  # junior | mid | senior
    Column("home_region", String(20), nullable=False),
    Column("hourly_rate", Numeric(8, 2), nullable=False),
    Column("hired_at", Date, nullable=False),
    Column("is_active", Boolean, nullable=False),
)

work_orders = Table(
    "work_orders",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("site_id", Integer, ForeignKey("sites.id"), nullable=False),
    Column("technician_id", Integer, ForeignKey("technicians.id"), nullable=True),
    Column("opened_at", DateTime, nullable=False),
    Column("scheduled_for", Date, nullable=True),
    Column("completed_at", DateTime, nullable=True),
    # open | scheduled | in_progress | completed | cancelled
    Column("status", String(20), nullable=False),
    Column("priority", String(10), nullable=False),  # low | medium | high | urgent
    # installation | repair | maintenance | inspection
    Column("job_type", String(20), nullable=False),
    Column("labor_hours", Numeric(6, 2), nullable=True),
)

parts = Table(
    "parts",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("sku", String(20), nullable=False, unique=True),
    Column("name", String(120), nullable=False),
    Column("category", String(20), nullable=False),  # electrical | plumbing | hvac | hardware
    Column("unit_cost", Numeric(10, 2), nullable=False),
    Column("unit_price", Numeric(10, 2), nullable=False),
)

work_order_parts = Table(
    "work_order_parts",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("work_order_id", Integer, ForeignKey("work_orders.id"), nullable=False),
    Column("part_id", Integer, ForeignKey("parts.id"), nullable=False),
    Column("quantity", Integer, nullable=False),
)

invoices = Table(
    "invoices",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("work_order_id", Integer, ForeignKey("work_orders.id"), nullable=False),
    Column("issued_at", Date, nullable=False),
    Column("due_at", Date, nullable=False),
    Column("amount", Numeric(12, 2), nullable=False),
    Column("status", String(10), nullable=False),  # paid | unpaid | overdue | void
    Column("paid_at", Date, nullable=True),
)

# Back-office logins. `email` and `password_hash` exist to exercise hidden fields.
users = Table(
    "users",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("username", String(40), nullable=False, unique=True),
    Column("full_name", String(120), nullable=False),
    Column("email", String(160), nullable=False),
    Column("password_hash", String(128), nullable=False),
    Column("role", String(20), nullable=False),  # dispatcher | manager | admin
    Column("created_at", DateTime, nullable=False),
)

TABLES_IN_LOAD_ORDER = [
    customers,
    sites,
    technicians,
    parts,
    work_orders,
    work_order_parts,
    invoices,
    users,
]

# Columns the read-only role may not SELECT at all (defence in depth: the registry
# already hides them, and the database refuses them even if a query asks).
RO_DENIED_COLUMNS: dict[str, frozenset[str]] = {
    "users": frozenset({"email", "password_hash"}),
}
