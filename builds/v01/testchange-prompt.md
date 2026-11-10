Cross-vendor check of a test-only commit. For each changed assertion: did it get weaker, or would it now pass on broken code? Answer per assertion PASS (not weakened) / FAIL (weakened) with one-line evidence; read the code under test as needed.

commit e82b3232723e1ec85a974bc66c4d831ae1eb3eac
Author: Cristian Ortega <153694889+crisnc100@users.noreply.github.com>
Date:   Mon Nov 9 16:05:13 2026 -0500

    Tests: failing tests for the PR1 grade findings; strengthen the sentinel property
    
    Changed existing test (tests/core/test_sqlbuild.py,
    test_every_filter_value_is_bound_never_inlined), stronger only:
    - generators now also produce boolean eq/neq filters (customers.is_active,
      technicians.is_active), datetime comparisons on work_orders.opened_at and
      integer IN lists; nothing was removed from the generator;
    - new assertion: the number of bound parameters equals the number of filter
      values, so a value inlined as a literal (TRUE, or 1 on SQLite) fails;
    - _is_bound now requires a boolean to be bound as that exact boolean (True == 1
      in Python, which would otherwise pass an inlined 1);
    - _sql_mentions now flags any TRUE/FALSE literal for boolean values and checks
      both ISO forms of a datetime;
    - the registry is loaded inside the test instead of via the fixture, so a
      falsifying example does not print the whole registry. Same registry file.
    The property still asserts every value is absent from the SQL text and present
    in the bound params, on Postgres and SQLite.
    
    New tests (fail before the fixes): test_boolean_filter_values_are_bound,
    test_two_resumes_after_a_torn_line_keep_progress_and_spend,
    test_append_after_a_torn_line_without_load_is_still_readable,
    test_rule_alias_collision, test_default_metric_labels_step_around_group_labels,
    test_date_vs_datetime_comparison_including_midnight (both engines),
    test_rerunning_roles_sql_keeps_hidden_columns_denied,
    test_roles_sql_denies_the_same_columns_as_the_seed.

diff --git a/tests/core/test_sqlbuild.py b/tests/core/test_sqlbuild.py
index bfee0a5..aac06c9 100644
--- a/tests/core/test_sqlbuild.py
+++ b/tests/core/test_sqlbuild.py
@@ -16,10 +16,10 @@ from sqlalchemy.exc import CompileError
 
 from ledgerline.core.executor import run
 from ledgerline.core.intent import Intent
-from ledgerline.core.registry import Registry
+from ledgerline.core.registry import Registry, load_registry
 from ledgerline.core.sqlbuild import GRAINS, build, compile_sql, dialect_for
 from ledgerline.core.validate import validate
-from tests.core.conftest import NOW
+from tests.core.conftest import FIELDSERVICE_REGISTRY, NOW
 
 # --- sentinel property ---
 
@@ -37,11 +37,26 @@ float_sentinel = st.floats(min_value=1e9, max_value=2e9, allow_nan=False).map(la
 # an unknown value; parts is on the many side).
 TEXT_FIELDS = ["customers.name", "sites.name", "technicians.full_name"]
 NUM_FIELDS = ["amount", "work_orders.labor_hours", "technicians.hourly_rate", "id"]
+BOOL_FIELDS = ["customers.is_active", "technicians.is_active"]
 
 
 @st.composite
 def condition(draw: st.DrawFn) -> tuple[dict[str, Any], list[Any]]:
-    kind = draw(st.sampled_from(["text_eq", "text_in", "ilike", "num_cmp", "num_between", "date"]))
+    kind = draw(
+        st.sampled_from(
+            [
+                "text_eq",
+                "text_in",
+                "ilike",
+                "num_cmp",
+                "num_between",
+                "num_in",
+                "date",
+                "datetime",
+                "bool",
+            ]
+        )
+    )
     if kind == "text_eq":
         v = draw(text_sentinel)
         return {"field": draw(st.sampled_from(TEXT_FIELDS)), "op": "neq", "value": v}, [v]
@@ -64,20 +79,41 @@ def condition(draw: st.DrawFn) -> tuple[dict[str, Any], list[Any]]:
         lo = draw(int_sentinel)
         hi = lo + draw(st.integers(1, 10**6))
         return {"field": "amount", "op": "between", "values": [lo, hi]}, [lo, hi]
+    if kind == "num_in":
+        vs = draw(st.lists(int_sentinel, min_size=1, max_size=3, unique=True))
+        return {"field": "id", "op": "in", "values": vs}, vs
+    if kind == "datetime":
+        moment = datetime(2017, 3, 9, 7, 11, 13, 123457) + timedelta(
+            seconds=draw(st.integers(0, 10**8)), microseconds=draw(st.integers(1, 999_999))
+        )
+        op = draw(st.sampled_from(["eq", "neq", "gt", "gte", "lt", "lte"]))
+        return {"field": "work_orders.opened_at", "op": op, "value": moment.isoformat()}, [moment]
+    if kind == "bool":
+        v = draw(st.booleans())
+        field = draw(st.sampled_from(BOOL_FIELDS))
+        return {"field": field, "op": draw(st.sampled_from(["eq", "neq"])), "value": v}, [v]
     days = draw(st.integers(0, 3000))
     day = date(2017, 3, 9) + timedelta(days=days)
     return {"field": "issued_at", "op": "lte", "value": day.isoformat()}, [day]
 
 
 def _sql_mentions(sql: str, value: Any) -> bool:
+    if isinstance(value, bool):
+        # A boolean has no unique text; any TRUE/FALSE literal means one was inlined.
+        # (An inlined 1/0 on SQLite is caught by the parameter count instead.)
+        return re.search(r"\b(true|false)\b", sql, re.IGNORECASE) is not None
     if isinstance(value, str):
         return value in sql
+    if isinstance(value, datetime):
+        return value.isoformat() in sql or value.isoformat(sep=" ") in sql
     if isinstance(value, date):
         return value.isoformat() in sql
     return repr(value) in sql or str(int(value)) in sql
 
 
 def _is_bound(value: Any, bound: Any) -> bool:
+    if isinstance(value, bool) or isinstance(bound, bool):
+        return bound is value  # True == 1 in Python; a bool must be bound as a bool
     if value == bound:
         return True
     # ilike_contains binds the value with LIKE wildcards escaped by "/" (autoescape).
@@ -89,8 +125,9 @@ def _is_bound(value: Any, bound: Any) -> bool:
 @settings(max_examples=300, deadline=None, suppress_health_check=[HealthCheck.too_slow])
 @given(conditions=st.lists(condition(), min_size=1, max_size=4))
 def test_every_filter_value_is_bound_never_inlined(
-    registry: Registry, conditions: list[tuple[dict[str, Any], list[Any]]]
+    conditions: list[tuple[dict[str, Any], list[Any]]],
 ) -> None:
+    registry = load_registry(FIELDSERVICE_REGISTRY)
     intent = Intent.model_validate(
         {
             "intent_type": "row_list",
@@ -109,6 +146,9 @@ def test_every_filter_value_is_bound_never_inlined(
             for value in values:
                 assert not _sql_mentions(sql, value), (dialect, value, sql)
                 assert any(_is_bound(value, b) for b in bound), (dialect, value, params)
+        # Every filter value is its own bound parameter, and nothing else is bound: a
+        # value inlined as a literal (e.g. TRUE, or 1 on SQLite) leaves the count short.
+        assert len(params) == sum(len(values) for _, values in conditions), (dialect, params)
 
 
 # --- compile shape ---
@@ -213,3 +253,21 @@ def test_grains_agree_across_engines_on_edge_dates(
             stmt = select(GRAINS[grain](literal(value, sa_type)))
             got = run(engine, stmt).rows[0][0]
             assert got == _expected(grain, day), (grain, engine_name, value, got)
+
+
+def test_boolean_filter_values_are_bound(registry: Registry) -> None:
+    intent = Intent.model_validate(
+        {
+            "intent_type": "summary",
+            "entity": "customers",
+            "metrics": [{"agg": "count"}],
+            "filters": [{"field": "is_active", "op": "eq", "value": True}],
+        }
+    )
+    plan = validate(intent, registry, now=NOW).plan
+    assert plan is not None
+    for dialect in ("postgresql", "sqlite"):
+        sql, params = compile_sql(build(plan), dialect)
+        assert list(params.values()) == [True], (dialect, sql, params)
+        assert "true" not in sql.lower()
+        assert "= 1" not in sql
diff --git a/tests/core/test_temporal_compare.py b/tests/core/test_temporal_compare.py
new file mode 100644
index 0000000..1bb0a36
--- /dev/null
+++ b/tests/core/test_temporal_compare.py
@@ -0,0 +1,117 @@
+"""Column comparisons between a DATE and a DATETIME normalise both sides to a datetime on
+both engines, so midnight on the same day compares equal (it did not on SQLite, where the
+raw operands compared as strings)."""
+
+from __future__ import annotations
+
+from collections.abc import Iterator
+from pathlib import Path
+
+import pytest
+from sqlalchemy import Engine, create_engine, text
+
+from ledgerline.config import get_settings
+from ledgerline.core.executor import readonly_engine, run
+from ledgerline.core.intent import Intent
+from ledgerline.core.registry import EntityDef, FieldDef, Registry
+from ledgerline.core.sqlbuild import build
+from ledgerline.core.validate import validate
+from tests.core.conftest import NOW
+
+ROWS = [
+    (1, "2026-06-01 00:00:00", "2026-06-01"),  # midnight on the day: equal
+    (2, "2026-06-01 10:30:00", "2026-06-01"),  # later that day: greater
+    (3, "2026-05-31 23:59:59", "2026-06-01"),  # the evening before: less
+    (4, "2026-06-03 00:00:00", "2026-06-02"),  # a day after: greater
+]
+EXPECTED = {"eq": [1], "neq": [2, 3, 4], "gt": [2, 4], "gte": [1, 2, 4], "lt": [3], "lte": [1, 3]}
+SCHEMA = "ledgerline_test_temporal"
+
+
+def _registry(db_schema: str | None) -> Registry:
+    return Registry(
+        schema_version=1,
+        draft=False,
+        entities={
+            "jobs": EntityDef(
+                table="jobs",
+                db_schema=db_schema,
+                fields={
+                    "id": FieldDef(column="id", type="integer"),
+                    "done_at": FieldDef(column="done_at", type="datetime"),
+                    "due_on": FieldDef(column="due_on", type="date"),
+                },
+            )
+        },
+    )
+
+
+@pytest.fixture
+def sqlite_jobs(tmp_path: Path) -> Iterator[Engine]:
+    """SQLite with timestamps stored the way SQLAlchemy writes them (with microseconds)."""
+    path = tmp_path / "jobs.sqlite"
+    writer = create_engine(f"sqlite:///{path}")
+    with writer.begin() as conn:
+        conn.execute(
+            text("CREATE TABLE jobs (id INTEGER PRIMARY KEY, done_at DATETIME, due_on DATE)")
+        )
+        for i, done, due in ROWS:
+            conn.execute(
+                text("INSERT INTO jobs VALUES (:i, :d, :u)"),
+                {"i": i, "d": f"{done}.000000", "u": due},
+            )
+    writer.dispose()
+    engine = readonly_engine(f"sqlite:///{path}")
+    yield engine
+    engine.dispose()
+
+
+@pytest.fixture
+def pg_jobs(pg_owner: Engine) -> Iterator[Engine]:
+    with pg_owner.begin() as conn:
+        conn.execute(text(f"DROP SCHEMA IF EXISTS {SCHEMA} CASCADE"))
+        conn.execute(text(f"CREATE SCHEMA {SCHEMA}"))
+        conn.execute(
+            text(f"CREATE TABLE {SCHEMA}.jobs (id int PRIMARY KEY, done_at timestamp, due_on date)")
+        )
+        for i, done, due in ROWS:
+            conn.execute(
+                text(
+                    f"INSERT INTO {SCHEMA}.jobs "
+                    "VALUES (:i, CAST(:d AS timestamp), CAST(:u AS date))"
+                ),
+                {"i": i, "d": done, "u": due},
+            )
+        conn.execute(text(f"GRANT USAGE ON SCHEMA {SCHEMA} TO ledgerline_ro"))
+        conn.execute(text(f"GRANT SELECT ON {SCHEMA}.jobs TO ledgerline_ro"))
+    engine = readonly_engine(get_settings().database_ro_url)
+    yield engine
+    engine.dispose()
+    with pg_owner.begin() as conn:
+        conn.execute(text(f"DROP SCHEMA {SCHEMA} CASCADE"))
+
+
+@pytest.mark.parametrize("engine_name", ["postgresql", "sqlite"])
+@pytest.mark.parametrize("op", sorted(EXPECTED))
+def test_date_vs_datetime_comparison_including_midnight(
+    op: str, engine_name: str, request: pytest.FixtureRequest
+) -> None:
+    engine: Engine = request.getfixturevalue(
+        "pg_jobs" if engine_name == "postgresql" else "sqlite_jobs"
+    )
+    registry = _registry(SCHEMA if engine_name == "postgresql" else None)
+    for left, right, flipped in (("done_at", "due_on", False), ("due_on", "done_at", True)):
+        intent = Intent.model_validate(
+            {
+                "intent_type": "row_list",
+                "entity": "jobs",
+                "select": ["id"],
+                "filters": [{"field": left, "op": op, "other_field": right}],
+                "order_by": [{"target": "id"}],
+            }
+        )
+        plan = validate(intent, registry, now=NOW).plan
+        assert plan is not None
+        got = [row[0] for row in run(engine, build(plan)).rows]
+        mirror = {"gt": "lt", "gte": "lte", "lt": "gt", "lte": "gte"}.get(op, op)
+        assert got == EXPECTED[mirror if flipped else op], (engine_name, left, op, right)
diff --git a/tests/core/test_validate.py b/tests/core/test_validate.py
index 9f54b9c..60043e1 100644
--- a/tests/core/test_validate.py
+++ b/tests/core/test_validate.py
@@ -884,3 +884,36 @@ def test_text_and_boolean_column_comparisons(registry: Registry) -> None:
         metrics=COUNT,
         filters=[{"field": "is_active", "op": "eq", "other_field": "full_name"}],
     ) == ["column_comparison_type"]
+
+
+def test_rule_alias_collision(registry: Registry) -> None:
+    # A metric alias equal to a group label would shadow the group in ORDER BY.
+    assert codes(
+        registry,
+        intent_type="grouped_summary",
+        entity="work_orders",
+        metrics=[{"agg": "count", "alias": "status"}],
+        group_by=[{"field": "status"}],
+        order_by=[{"target": "work_orders.status"}],
+    ) == ["alias_collision"]
+    # The same field grouped twice gives two identical labels.
+    assert codes(
+        registry,
+        intent_type="grouped_summary",
+        entity="work_orders",
+        metrics=COUNT,
+        group_by=[{"field": "status"}, {"field": "work_orders.status"}],
+    ) == ["alias_collision"]
+
+
+def test_default_metric_labels_step_around_group_labels() -> None:
+    reg = make_registry({"t": ["count"]}, [])
+    plan = plan_of(
+        reg,
+        intent_type="grouped_summary",
+        entity="t",
+        metrics=[{"agg": "count"}],
+        group_by=[{"field": "count"}],
+    )
+    assert [g.label for g in plan.group_by] == ["count"]
+    assert [m.label for m in plan.metrics] == ["count_2"]
diff --git a/tests/test_llm_budget.py b/tests/test_llm_budget.py
index 1a36edd..724b10e 100644
--- a/tests/test_llm_budget.py
+++ b/tests/test_llm_budget.py
@@ -128,3 +128,41 @@ def test_torn_last_line_is_ignored_on_resume(tmp_path: Path) -> None:
     outcome = run_checkpointed(ITEMS[:3], str, make_work(0.1, resumed_calls), checkpoint, 1)
     assert resumed_calls == ["q2"]
     assert outcome.resumed == 2
+
+
+def test_two_resumes_after_a_torn_line_keep_progress_and_spend(tmp_path: Path) -> None:
+    """A torn tail is repaired on load, so appends after it stay readable on later resumes."""
+    path = tmp_path / "run.jsonl"
+    checkpoint = Checkpoint(path)
+    calls: list[str] = []
+    run_checkpointed(ITEMS[:2], str, make_work(0.1, calls), checkpoint, budget_usd=10)
+    with path.open("a") as fh:
+        fh.write('{"key": "q2", "cost_usd": 0.1, "rec')  # killed mid-write
+
+    first_resume: list[str] = []
+    one = run_checkpointed(ITEMS[:4], str, make_work(0.1, first_resume), checkpoint, 10)
+    assert first_resume == ["q2", "q3"]
+    assert one.spent_usd == pytest.approx(0.4)
+
+    second_resume: list[str] = []
+    two = run_checkpointed(ITEMS[:6], str, make_work(0.1, second_resume), checkpoint, 10)
+    assert second_resume == ["q4", "q5"]
+    assert two.resumed == 4
+    assert [r["id"] for r in two.records] == ITEMS[:6]
+    assert two.spent_usd == pytest.approx(0.6)
+    done, spent = Checkpoint(path).load()
+    assert sorted(done) == ITEMS[:6]
+    assert spent == pytest.approx(0.6)
+
+
+def test_append_after_a_torn_line_without_load_is_still_readable(tmp_path: Path) -> None:
+    path = tmp_path / "run.jsonl"
+    checkpoint = Checkpoint(path)
+    checkpoint.append("q0", 0.1, {"id": "q0"})
+    with path.open("a") as fh:
+        fh.write('{"key": "q1", "co')
+    checkpoint.append("q1", 0.2, {"id": "q1"})
+    checkpoint.append("q2", 0.3, {"id": "q2"})
+    done, spent = checkpoint.load()
+    assert sorted(done) == ["q0", "q1", "q2"]
+    assert spent == pytest.approx(0.6)
diff --git a/tests/test_roles.py b/tests/test_roles.py
new file mode 100644
index 0000000..6df9e32
--- /dev/null
+++ b/tests/test_roles.py
@@ -0,0 +1,62 @@
+"""infra/postgres/roles.sql is idempotent AND keeps the hidden users columns denied."""
+
+from __future__ import annotations
+
+import re
+import shutil
+import subprocess
+from pathlib import Path
+
+import pytest
+from sqlalchemy import Engine, text
+from sqlalchemy.engine import make_url
+from sqlalchemy.exc import ProgrammingError
+
+from ledgerline.config import get_settings
+from ledgerline.fieldservice.schema import RO_DENIED_COLUMNS
+
+ROLES_SQL = Path(__file__).resolve().parent.parent / "infra" / "postgres" / "roles.sql"
+
+
+def _run_roles_sql() -> None:
+    psql = shutil.which("psql")
+    if psql is None:
+        pytest.fail("psql is required to run infra/postgres/roles.sql (tests never skip)")
+    url = make_url(get_settings().database_url).set(drivername="postgresql")
+    ro_password = make_url(get_settings().database_ro_url).password or ""
+    subprocess.run(
+        [
+            psql,
+            url.render_as_string(hide_password=False),
+            "-q",
+            "-v",
+            "ON_ERROR_STOP=1",
+            "-v",
+            f"ro_password={ro_password}",
+            "-f",
+            str(ROLES_SQL),
+        ],
+        check=True,
+        capture_output=True,
+    )
+
+
+def test_rerunning_roles_sql_keeps_hidden_columns_denied(pg_seeded: Engine) -> None:
+    _run_roles_sql()
+    _run_roles_sql()
+    for column in sorted(RO_DENIED_COLUMNS["users"]):
+        with (
+            pg_seeded.connect() as conn,
+            pytest.raises(ProgrammingError, match="permission denied"),
+        ):
+            conn.execute(text(f"SELECT {column} FROM users"))
+    with pg_seeded.connect() as conn:
+        assert conn.execute(text("SELECT count(username) FROM users")).scalar_one() == 25
+
+
+def test_roles_sql_denies_the_same_columns_as_the_seed() -> None:
+    sql = ROLES_SQL.read_text()
+    match = re.search(r"column_name NOT IN \(([^)]*)\)", sql)
+    assert match is not None
+    denied = {c.strip().strip("'") for c in match.group(1).split(",")}
+    assert denied == set(RO_DENIED_COLUMNS["users"])
