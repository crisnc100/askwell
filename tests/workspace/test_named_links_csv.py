"""Uploaded files, inferred links (v0.3, PR-2, switch `inferred_links`): a column named
`<role>_<x>_id`, or `<x>_id` where `<x>` is a singular the `<x>_id` rule misses, links to
table `<x>` only when its values are that table's IDs, with enough of them to be
evidence. A column that fails stays a plain column, never an error."""

from __future__ import annotations

from askwell.core.features import ALL
from askwell.workspace.check import CheckResult, Link, UploadedFile, check_files
from tests.workspace.conftest import csv_file, sample_files

NO_INFERENCE = ALL - {"inferred_links"}
KEYS = range(1, 13)


def _ids(name: str, column: str = "id") -> UploadedFile:
    return csv_file(name, f"{column},name\n" + "".join(f"{k},n{k}\n" for k in KEYS))


def _links(result: CheckResult, table: str) -> list[Link]:
    assert result.ok, [(f.name, f.problems) for f in result.files if f.problems]
    return next(t for t in result.tables if t.name == table).links


def test_a_role_before_the_table_name_links_on_evidence() -> None:
    flights = csv_file(
        "flights.csv",
        "id,origin_airport_id,dest_airport_id\n" + "".join(f"{k},{k},{13 - k}\n" for k in KEYS),
    )
    links = _links(check_files([_ids("airports.csv"), flights]), "flights")
    assert links == [
        Link("origin_airport_id", "airports", "id"),
        Link("dest_airport_id", "airports", "id"),
    ]


def test_a_singular_the_plain_rule_misses_links_on_evidence() -> None:
    contacts = csv_file("contacts.csv", "id,company_id\n" + "".join(f"{k},{k}\n" for k in KEYS))
    links = _links(check_files([_ids("companies.csv"), contacts]), "contacts")
    assert links == [Link("company_id", "companies", "id")]


def test_too_few_values_or_a_stray_value_leaves_a_plain_column() -> None:
    flights = csv_file(
        "flights.csv",
        "id,few_airport_id,stray_airport_id\n"
        + "".join(f"{k},{min(k, 9)},{99 if k == 1 else k}\n" for k in KEYS),
    )
    result = check_files([_ids("airports.csv"), flights])
    assert _links(result, "flights") == []
    assert all(not f.problems for f in result.files)


def test_switch_off_restores_todays_links() -> None:
    contacts = csv_file("contacts.csv", "id,company_id\n" + "".join(f"{k},{k}\n" for k in KEYS))
    result = check_files([_ids("companies.csv"), contacts], features=NO_INFERENCE)
    assert _links(result, "contacts") == []


def test_the_sample_files_load_as_before() -> None:
    # P2.3: a set that loaded before loads with the same tables, types and links.
    on = check_files(sample_files())
    off = check_files(sample_files(), features=frozenset())
    assert on.ok
    assert off.ok
    assert [
        (t.name, t.id_column, t.links, [(c.name, c.type) for c in t.columns]) for t in on.tables
    ] == [(t.name, t.id_column, t.links, [(c.name, c.type) for c in t.columns]) for t in off.tables]
