"""Deterministic generator and loader for the fieldservice demo data.

Same seed + same reference time + same locked Faker version gives the same rows,
byte for byte. About 5k work orders over the 24 months ending at `LEDGERLINE_NOW`.
"""

from __future__ import annotations

import hashlib
import random
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from faker import Faker
from sqlalchemy import Connection, Engine, Table, select, text

from ledgerline.fieldservice import schema

DEFAULT_SEED = 20260630
N_CUSTOMERS = 400
N_TECHNICIANS = 40
N_PARTS = 120
N_WORK_ORDERS = 5000
N_USERS = 25
WINDOW_MONTHS = 24

Row = dict[str, Any]

# City, state, region. Customer region and site city always agree.
CITIES: list[tuple[str, str, str]] = [
    ("Minneapolis", "MN", "north"),
    ("Milwaukee", "WI", "north"),
    ("Detroit", "MI", "north"),
    ("Fargo", "ND", "north"),
    ("Chicago", "IL", "north"),
    ("Atlanta", "GA", "south"),
    ("Houston", "TX", "south"),
    ("Austin", "TX", "south"),
    ("Nashville", "TN", "south"),
    ("Charlotte", "NC", "south"),
    ("Boston", "MA", "east"),
    ("Philadelphia", "PA", "east"),
    ("Newark", "NJ", "east"),
    ("Baltimore", "MD", "east"),
    ("Hartford", "CT", "east"),
    ("Seattle", "WA", "west"),
    ("Portland", "OR", "west"),
    ("Sacramento", "CA", "west"),
    ("San Diego", "CA", "west"),
    ("Phoenix", "AZ", "west"),
    ("Denver", "CO", "central"),
    ("Kansas City", "MO", "central"),
    ("Omaha", "NE", "central"),
    ("Tulsa", "OK", "central"),
    ("Des Moines", "IA", "central"),
]
REGIONS = ["north", "south", "east", "west", "central"]

PART_NAMES: dict[str, tuple[str, list[str], list[str]]] = {
    "electrical": (
        "EL",
        ["Breaker", "Outlet", "Switch", "Wire Spool", "Junction Box", "Fuse", "Conduit"],
        ["15A", "20A", "GFCI", "Dimmer", "12-Gauge", "Weatherproof", "Industrial"],
    ),
    "plumbing": (
        "PL",
        ["Valve", "Pipe", "Faucet", "Drain Trap", "Water Heater Element", "Coupling", "Pump"],
        ["1/2in", "3/4in", "PEX", "Copper", "Brass", "Sump", "Pressure"],
    ),
    "hvac": (
        "HV",
        ["Air Filter", "Capacitor", "Thermostat", "Blower Motor", "Compressor", "Coil", "Damper"],
        ["MERV-13", "Smart", "Dual-Run", "Variable-Speed", "Rooftop", "Condenser", "Zone"],
    ),
    "hardware": (
        "HW",
        ["Anchor Kit", "Bracket", "Fastener Pack", "Hinge", "Sealant", "Lock Set", "Strap"],
        ["Stainless", "Heavy-Duty", "Galvanized", "Commercial", "Fire-Rated", "Marine", "Mini"],
    ),
}

JOB_TYPES = ["repair", "maintenance", "installation", "inspection"]
JOB_TYPE_WEIGHTS = [0.40, 0.30, 0.18, 0.12]
PRIORITIES = ["low", "medium", "high", "urgent"]
PRIORITY_WEIGHTS = [0.25, 0.45, 0.22, 0.08]
# Labor-hour range per job type.
LABOR_HOURS = {
    "repair": (1.0, 6.0),
    "maintenance": (0.5, 3.0),
    "installation": (3.0, 12.0),
    "inspection": (0.5, 2.0),
}
# Days from open to completion, by priority.
COMPLETION_DAYS = {"urgent": (0, 2), "high": (0, 5), "medium": (1, 10), "low": (2, 21)}
SKILL_RATES = {"junior": (38, 48), "mid": (50, 66), "senior": (70, 95)}


@dataclass
class Dataset:
    tables: dict[str, list[Row]] = field(default_factory=dict[str, list[Row]])

    def counts(self) -> dict[str, int]:
        return {name: len(rows) for name, rows in self.tables.items()}


def _money(value: float | Decimal) -> Decimal:
    return Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _months_before(moment: datetime, months: int) -> datetime:
    year, month = moment.year, moment.month - months
    while month <= 0:
        month += 12
        year -= 1
    return moment.replace(year=year, month=month)


def _naive_utc(moment: datetime) -> datetime:
    if moment.tzinfo is None:
        return moment
    return moment.astimezone(UTC).replace(tzinfo=None)


def generate(now: datetime, seed: int = DEFAULT_SEED) -> Dataset:
    """Build every row in memory. Pure: no I/O, no wall clock."""
    rng = random.Random(seed)
    fake = Faker("en_US")
    fake.seed_instance(seed)

    end = _naive_utc(now)
    start = _months_before(end, WINDOW_MONTHS)
    today = end.date()

    customers: list[Row] = []
    sites: list[Row] = []
    for cid in range(1, N_CUSTOMERS + 1):
        segment = rng.choices(["residential", "commercial", "industrial"], [0.5, 0.35, 0.15])[0]
        region = rng.choice(REGIONS)
        name = fake.name() if segment == "residential" else fake.company()
        created = date(2020, 1, 1) + timedelta(days=rng.randrange((today - date(2020, 1, 1)).days))
        customers.append(
            {
                "id": cid,
                "name": name,
                "segment": segment,
                "region": region,
                "created_at": created,
                "is_active": rng.random() < 0.9,
            }
        )
        n_sites = 1 if segment == "residential" else rng.choice([1, 1, 2, 2, 3])
        region_cities = [c for c in CITIES if c[2] == region]
        for n in range(n_sites):
            city, state, _ = rng.choice(region_cities)
            if segment == "residential":
                site_type = "residence"
                site_name = f"{name} residence"
            else:
                site_type = rng.choice(
                    ["office", "retail", "warehouse"]
                    if segment == "commercial"
                    else ["plant", "warehouse"]
                )
                site_name = f"{name} {city} {site_type}" + (f" {n + 1}" if n else "")
            sites.append(
                {
                    "id": len(sites) + 1,
                    "customer_id": cid,
                    "name": site_name,
                    "city": city,
                    "state": state,
                    "site_type": site_type,
                }
            )

    technicians: list[Row] = []
    for tid in range(1, N_TECHNICIANS + 1):
        skill = rng.choices(["junior", "mid", "senior"], [0.3, 0.45, 0.25])[0]
        lo, hi = SKILL_RATES[skill]
        hired = date(2015, 1, 1) + timedelta(days=rng.randrange((today - date(2015, 1, 1)).days))
        technicians.append(
            {
                "id": tid,
                "full_name": fake.name(),
                "skill_level": skill,
                "home_region": rng.choice(REGIONS),
                "hourly_rate": _money(rng.uniform(lo, hi)),
                "hired_at": hired,
                "is_active": rng.random() < 0.85,
            }
        )

    parts: list[Row] = []
    categories = list(PART_NAMES)
    seen_names: set[str] = set()
    while len(parts) < N_PARTS:
        category = categories[len(parts) % len(categories)]
        prefix, nouns, adjectives = PART_NAMES[category]
        part_name = f"{rng.choice(adjectives)} {rng.choice(nouns)}"
        if part_name in seen_names:
            continue
        seen_names.add(part_name)
        cost = rng.uniform(2, 60) if rng.random() < 0.7 else rng.uniform(60, 400)
        price = cost * rng.uniform(1.3, 1.8)
        parts.append(
            {
                "id": len(parts) + 1,
                "sku": f"{prefix}-{len(parts) + 1:04d}",
                "name": part_name,
                "category": category,
                "unit_cost": _money(cost),
                "unit_price": _money(price),
            }
        )

    # Work-order volume grows about 40% across the window.
    window_seconds = int((end - start).total_seconds())
    opened_times: list[datetime] = []
    while len(opened_times) < N_WORK_ORDERS:
        offset = rng.randrange(window_seconds)
        if rng.random() < 0.7 + 0.3 * (offset / window_seconds):
            opened_times.append(start + timedelta(seconds=offset))
    opened_times.sort()

    work_orders: list[Row] = []
    work_order_parts: list[Row] = []
    invoices: list[Row] = []
    tech_rate = {t["id"]: t["hourly_rate"] for t in technicians}
    part_price = {p["id"]: p["unit_price"] for p in parts}
    for woid, opened in enumerate(opened_times, start=1):
        site = rng.choice(sites)
        priority = rng.choices(PRIORITIES, PRIORITY_WEIGHTS)[0]
        job_type = rng.choices(JOB_TYPES, JOB_TYPE_WEIGHTS)[0]
        scheduled = opened.date() + timedelta(days=rng.randint(0, 7))
        lo_d, hi_d = COMPLETION_DAYS[priority]
        planned_completion = opened + timedelta(
            days=rng.randint(lo_d, hi_d), hours=rng.randint(2, 10), minutes=rng.randrange(60)
        )
        cancelled = rng.random() < 0.06
        eligible = [t["id"] for t in technicians if t["hired_at"] <= opened.date()]

        technician_id: int | None = rng.choice(eligible)
        completed_at: datetime | None = None
        labor: Decimal | None = None
        if cancelled:
            status = "cancelled"
            if rng.random() < 0.5:
                technician_id = None
        elif planned_completion < end:
            status = "completed"
            completed_at = planned_completion
            lo_h, hi_h = LABOR_HOURS[job_type]
            # Quarter-hour increments.
            labor = _money(max(1, round(rng.uniform(lo_h, hi_h) * 4)) / 4)
        elif scheduled <= today:
            status = "in_progress"
        elif rng.random() < 0.7:
            status = "scheduled"
        else:
            status = "open"
            technician_id = None
        work_orders.append(
            {
                "id": woid,
                "site_id": site["id"],
                "technician_id": technician_id,
                "opened_at": opened,
                "scheduled_for": None if status == "open" else scheduled,
                "completed_at": completed_at,
                "status": status,
                "priority": priority,
                "job_type": job_type,
                "labor_hours": labor,
            }
        )

        if status not in ("completed", "in_progress"):
            continue
        n_lines = {
            "installation": rng.randint(1, 4),
            "repair": rng.randint(1, 3),
            "maintenance": rng.randint(0, 2),
            "inspection": 0,
        }[job_type]
        lines: list[Row] = []
        for part_id in rng.sample(range(1, N_PARTS + 1), n_lines):
            lines.append(
                {
                    "id": len(work_order_parts) + len(lines) + 1,
                    "work_order_id": woid,
                    "part_id": part_id,
                    "quantity": rng.randint(1, 10) if rng.random() < 0.8 else rng.randint(11, 40),
                }
            )
        work_order_parts.extend(lines)

        if completed_at is None or technician_id is None or labor is None:
            continue
        issued = completed_at.date() + timedelta(days=rng.randint(0, 3))
        if issued >= today:
            continue  # completed, not yet invoiced
        parts_total = sum(
            (part_price[line["part_id"]] * line["quantity"] for line in lines), Decimal("0")
        )
        amount = _money(labor * tech_rate[technician_id] + parts_total)
        invoices.append(_invoice(rng, len(invoices) + 1, woid, issued, amount, today))
        if rng.random() < 0.08:  # supplemental invoice: one-to-many on purpose
            extra_issued = issued + timedelta(days=rng.randint(5, 40))
            if extra_issued < today:
                extra_amount = _money(Decimal(str(rng.uniform(40, 600))))
                invoices.append(
                    _invoice(rng, len(invoices) + 1, woid, extra_issued, extra_amount, today)
                )

    users: list[Row] = []
    for uid in range(1, N_USERS + 1):
        full_name = fake.name()
        username = f"{full_name.split()[0][0]}{full_name.split()[-1]}".lower() + str(uid)
        digest = hashlib.sha256(rng.randbytes(32)).hexdigest()
        users.append(
            {
                "id": uid,
                "username": username,
                "full_name": full_name,
                "email": f"{username}@example.com",
                # Synthetic: random bytes in a pbkdf2-shaped string, not a hash of any password.
                "password_hash": f"pbkdf2_sha256$600000${digest[:16]}${digest[16:]}",
                "role": rng.choices(["dispatcher", "manager", "admin"], [0.6, 0.3, 0.1])[0],
                "created_at": start - timedelta(days=rng.randrange(900)),
            }
        )

    return Dataset(
        tables={
            "customers": customers,
            "sites": sites,
            "technicians": technicians,
            "parts": parts,
            "work_orders": work_orders,
            "work_order_parts": work_order_parts,
            "invoices": invoices,
            "users": users,
        }
    )


def _invoice(
    rng: random.Random, iid: int, woid: int, issued: date, amount: Decimal, today: date
) -> Row:
    due = issued + timedelta(days=30)
    paid_at: date | None = None
    roll = rng.random()
    if roll < 0.02:
        status = "void"
    else:
        paid_at = issued + timedelta(days=rng.randint(0, 50))
        if roll < 0.88 and paid_at < today:
            status = "paid"
        else:
            paid_at = None
            status = "overdue" if due < today else "unpaid"
    return {
        "id": iid,
        "work_order_id": woid,
        "issued_at": issued,
        "due_at": due,
        "amount": amount,
        "status": status,
        "paid_at": paid_at,
    }


def _chunks(rows: Sequence[Row], size: int) -> Iterable[Sequence[Row]]:
    for i in range(0, len(rows), size):
        yield rows[i : i + size]


def load(engine: Engine, dataset: Dataset, ro_role: str | None = "ledgerline_ro") -> None:
    """Drop and recreate the fieldservice tables, then insert every row.

    On Postgres, SELECT is granted to `ro_role` when that role exists.
    """
    schema.metadata.drop_all(engine)
    schema.metadata.create_all(engine)
    with engine.begin() as conn:
        for table in schema.TABLES_IN_LOAD_ORDER:
            rows = dataset.tables[table.name]
            for chunk in _chunks(rows, 2000):
                conn.execute(table.insert(), list(chunk))
        if engine.dialect.name == "postgresql" and ro_role is not None:
            exists = conn.execute(
                text("SELECT 1 FROM pg_roles WHERE rolname = :r"), {"r": ro_role}
            ).first()
            if exists:
                _grant_readonly(conn, ro_role)


def _grant_readonly(conn: Connection, ro_role: str) -> None:
    """SELECT on every table, except column-level SELECT on tables with denied columns.

    A table-level grant would cover every column, so those tables get the table grant
    revoked and a column list granted instead."""
    for table in schema.TABLES_IN_LOAD_ORDER:
        denied = schema.RO_DENIED_COLUMNS.get(table.name, frozenset())
        conn.execute(text(f'REVOKE ALL ON "{table.name}" FROM "{ro_role}"'))
        if not denied:
            conn.execute(text(f'GRANT SELECT ON "{table.name}" TO "{ro_role}"'))
            continue
        allowed = ", ".join(f'"{c.name}"' for c in table.columns if c.name not in denied)
        conn.execute(text(f'GRANT SELECT ({allowed}) ON "{table.name}" TO "{ro_role}"'))


def content_hash(engine: Engine) -> str:
    """SHA-256 over every row of every table in primary-key order."""
    digest = hashlib.sha256()
    with engine.connect() as conn:
        for table in schema.TABLES_IN_LOAD_ORDER:
            digest.update(table.name.encode())
            for row in conn.execute(select(table).order_by(*_pk(table))):
                digest.update(repr(tuple(_normalise(v) for v in row)).encode())
    return digest.hexdigest()


def _pk(table: Table) -> list[Any]:
    return list(table.primary_key.columns)


def _normalise(value: object) -> object:
    if isinstance(value, Decimal):
        return str(value.quantize(Decimal("0.01")))
    if isinstance(value, float):
        return f"{value:.2f}"
    if isinstance(value, datetime):
        return _naive_utc(value).isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return value
