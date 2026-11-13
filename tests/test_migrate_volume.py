"""scripts/migrate_volume.sh against a fake `docker`: any failed docker call stops it
before the copy, and a good run prints the command that removes the old volume."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "migrate_volume.sh"

# Logs each call. MOCK_FAIL names a call that exits 1 with no output; MOCK_IN_USE and
# MOCK_NOT_EMPTY make the safety checks find something; MOCK_NO_TARGET makes the target
# volume missing so the script creates it.
FAKE_DOCKER = """#!/usr/bin/env bash
echo "$*" >> "$MOCK_LOG"
case "$*" in
  "volume inspect "*_askwell-data) call=inspect-target ;;
  "volume inspect "*) call=inspect-source ;;
  "volume create "*) call=create ;;
  "ps "*) call=ps ;;
  *" ls -A /to") call=check-empty ;;
  *" cp -a "*) call=copy ;;
  *" ls -lan /to") call=list ;;
  *) echo "unexpected docker call: $*" >&2; exit 99 ;;
esac
[ "$call" = "${MOCK_FAIL:-}" ] && exit 1
case "$call" in
  inspect-target) [ -n "${MOCK_NO_TARGET:-}" ] && exit 1 ;;
  ps) [ -n "${MOCK_IN_USE:-}" ] && echo abc123 ;;
  check-empty) [ -n "${MOCK_NOT_EMPTY:-}" ] && echo spend.sqlite ;;
esac
exit 0
"""


def _run(tmp_path: Path, **mock: str) -> tuple[subprocess.CompletedProcess[str], str]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    docker = bin_dir / "docker"
    docker.write_text(FAKE_DOCKER, encoding="utf-8")
    docker.chmod(0o755)
    log = tmp_path / "calls.log"
    log.write_text("", encoding="utf-8")
    env = {
        "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
        "MOCK_LOG": str(log),
        **mock,
    }
    result = subprocess.run(
        ["bash", str(SCRIPT), "ledgerline", "askwell"],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    return result, log.read_text(encoding="utf-8")


@pytest.mark.parametrize("call", ["inspect-source", "ps", "create", "check-empty", "copy"])
def test_a_failed_docker_call_stops_before_or_at_the_copy(tmp_path: Path, call: str) -> None:
    mock = {"MOCK_FAIL": call}
    if call == "create":
        mock["MOCK_NO_TARGET"] = "1"
    result, calls = _run(tmp_path, **mock)
    assert result.returncode != 0
    assert "docker volume rm" not in result.stdout
    if call != "copy":
        assert " cp -a " not in calls


def test_a_volume_in_use_is_refused(tmp_path: Path) -> None:
    result, calls = _run(tmp_path, MOCK_IN_USE="1")
    assert result.returncode != 0
    assert "still uses" in result.stderr
    assert " cp -a " not in calls


def test_a_target_with_files_is_refused(tmp_path: Path) -> None:
    result, calls = _run(tmp_path, MOCK_NOT_EMPTY="1")
    assert result.returncode != 0
    assert "not empty" in result.stderr
    assert " cp -a " not in calls


def test_a_good_copy_prints_how_to_remove_the_old_volume(tmp_path: Path) -> None:
    result, calls = _run(tmp_path, MOCK_NO_TARGET="1")
    assert result.returncode == 0, result.stderr
    assert "volume create" in calls
    assert " cp -a " in calls
    assert "docker volume rm ledgerline_ledgerline-data" in result.stdout


def test_the_copy_image_is_pinned_by_digest() -> None:
    assert "alpine:3.20@sha256:" in SCRIPT.read_text(encoding="utf-8")
