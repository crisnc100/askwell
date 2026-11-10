from __future__ import annotations

from typer.testing import CliRunner

from ledgerline import __version__
from ledgerline.cli import app


def test_version_command_prints_version() -> None:
    result = CliRunner().invoke(app, ["version"])
    assert result.exit_code == 0
    assert result.output.strip() == __version__
