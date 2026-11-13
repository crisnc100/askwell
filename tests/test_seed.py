"""Fieldservice seed: deterministic, inside the window, consistent, loaded read-only."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.exc import DBAPIError

from askwell.config import get_settings
from askwell.fieldservice.seed import Dataset, content_hash, generate, load


def _now() -> datetime:
    return get_settings().now.astimezone(UTC).replace(tzinfo=None)


def test_generate_is_deterministic(dataset: Dataset) -> None:
    assert generate(get_settings().now) == dataset


def test_different_seed_gives_different_data(dataset: Dataset) -> None:
    assert generate(get_settings().now, seed=1) != dataset


def test_volume_is_about_5k_work_orders_over_24_months(dataset: Dataset) -> None:
    orders = dataset.tables["work_orders"]
    assert len(orders) == 5000
    now = _now()
    opened = [o["opened_at"] for o in orders]
    assert min(opened) >= datetime(now.year - 2, now.month, now.day)
    assert max(opened) < now
    months = {(o.year, o.month) for o in opened}
    assert len(months) >= 24


def test_nothing_happens_after_reference_time(dataset: Dataset) -> None:
    now = _now()
    for order in dataset.tables["work_orders"]:
        if order["completed_at"] is not None:
            assert order["opened_at"] <= order["completed_at"] < now
    for invoice in dataset.tables["invoices"]:
        assert invoice["issued_at"] < now.date()
        if invoice["paid_at"] is not None:
            assert invoice["paid_at"] < now.date()


def test_status_fields_are_consistent(dataset: Dataset) -> None:
    today: date = _now().date()
    for order in dataset.tables["work_orders"]:
        assert (order["status"] == "completed") == (order["completed_at"] is not None)
        assert (order["labor_hours"] is not None) == (order["status"] == "completed")
    for invoice in dataset.tables["invoices"]:
        assert invoice["due_at"] == invoice["issued_at"] + timedelta(days=30)
        assert (invoice["status"] == "paid") == (invoice["paid_at"] is not None)
        if invoice["status"] == "overdue":
            assert invoice["due_at"] < today


def test_foreign_keys_resolve(dataset: Dataset) -> None:
    ids = {name: {r["id"] for r in rows} for name, rows in dataset.tables.items()}
    assert all(s["customer_id"] in ids["customers"] for s in dataset.tables["sites"])
    for order in dataset.tables["work_orders"]:
        assert order["site_id"] in ids["sites"]
        assert order["technician_id"] is None or order["technician_id"] in ids["technicians"]
    for line in dataset.tables["work_order_parts"]:
        assert line["work_order_id"] in ids["work_orders"]
        assert line["part_id"] in ids["parts"]
    assert all(i["work_order_id"] in ids["work_orders"] for i in dataset.tables["invoices"])


def test_work_orders_fan_out_to_invoices_and_parts(dataset: Dataset) -> None:
    """The fan-out hazard P2 must catch exists in the data."""
    per_order: dict[int, int] = {}
    for invoice in dataset.tables["invoices"]:
        per_order[invoice["work_order_id"]] = per_order.get(invoice["work_order_id"], 0) + 1
    assert max(per_order.values()) >= 2
    lines: dict[int, int] = {}
    for line in dataset.tables["work_order_parts"]:
        lines[line["work_order_id"]] = lines.get(line["work_order_id"], 0) + 1
    assert max(lines.values()) >= 2


def test_users_carry_sensitive_fields(dataset: Dataset) -> None:
    users = dataset.tables["users"]
    assert users
    assert all(u["password_hash"].startswith("pbkdf2_sha256$") for u in users)
    assert all("@" in u["email"] for u in users)


def test_load_twice_gives_identical_content(
    tmp_path_factory: pytest.TempPathFactory, dataset: Dataset, sqlite_fieldservice: Engine
) -> None:
    other = create_engine(f"sqlite:///{tmp_path_factory.mktemp('again') / 'fs.sqlite'}")
    load(other, dataset)
    load(other, dataset)  # drop-and-recreate is idempotent
    assert content_hash(other) == content_hash(sqlite_fieldservice)


def test_postgres_holds_the_same_seed_as_sqlite(pg_seeded: Engine) -> None:
    with pg_seeded.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM work_orders")).scalar_one() == 5000


def test_readonly_role_cannot_write(pg_seeded: Engine) -> None:
    with pg_seeded.connect() as conn, pytest.raises(DBAPIError, match="read-only"):
        conn.execute(text("UPDATE parts SET unit_price = 0"))


def test_readonly_role_cannot_write_even_outside_readonly_default(pg_seeded: Engine) -> None:
    """With the read-only default switched off, privileges still refuse the write."""
    with pg_seeded.connect() as conn:
        conn.execute(text("SET default_transaction_read_only = off"))
        conn.commit()
        with pytest.raises(DBAPIError, match="permission denied"):
            conn.execute(text("DELETE FROM invoices"))
        conn.rollback()
        with pytest.raises(DBAPIError, match="permission denied"):
            conn.execute(text("CREATE TABLE ro_probe (x int)"))
        conn.rollback()
