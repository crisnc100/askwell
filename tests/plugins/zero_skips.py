"""Pytest plugin: a run with any skipped or xfailed test fails.

A skipped test reads as a pass in most summaries, so a missing Postgres or a
missing fixture could hide behind it. This turns every skip into a failure.
(An xfailed test is reported as skipped by pytest, so it fails the run too.)
"""

from __future__ import annotations

import pytest

_skipped: list[str] = []


def pytest_sessionstart(session: pytest.Session) -> None:
    _skipped.clear()


def pytest_runtest_logreport(report: pytest.TestReport) -> None:
    if report.skipped:
        _skipped.append(report.nodeid)


def pytest_collectreport(report: pytest.CollectReport) -> None:
    if report.skipped:
        _skipped.append(report.nodeid or "<collection>")


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    if _skipped and session.exitstatus in (pytest.ExitCode.OK, pytest.ExitCode.NO_TESTS_COLLECTED):
        session.exitstatus = pytest.ExitCode.TESTS_FAILED


def pytest_terminal_summary(terminalreporter: pytest.TerminalReporter) -> None:
    if _skipped:
        terminalreporter.write_sep("=", "ZERO-SKIPS RULE VIOLATED", red=True, bold=True)
        for nodeid in _skipped:
            terminalreporter.write_line(f"skipped or xfailed: {nodeid}")
