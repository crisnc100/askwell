"""The benchmark fetch script: checksum pin, safe extraction, licence notice, and no
benchmark data in git. No test downloads anything."""

from __future__ import annotations

import hashlib
import io
import subprocess
import zipfile
from pathlib import Path

import httpx
import pytest

from scripts.fetch_benchmarks import (
    LICENSE_NOTICE,
    SPIDER_SHA256,
    ChecksumError,
    fetch_spider,
    safe_extract,
)

ROOT = Path(__file__).resolve().parent.parent


def _zip(entries: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        for name, data in entries.items():
            zf.writestr(name, data)
    return buffer.getvalue()


ARCHIVE = _zip(
    {
        "spider_data/dev.json": b"[]",
        "spider_data/database/x/x.sqlite": b"sqlite",
        "__MACOSX/spider_data/._dev.json": b"junk",
        "spider_data/.DS_Store": b"junk",
    }
)


def _client(body: bytes, calls: list[str]) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        return httpx.Response(200, content=body)

    return httpx.Client(transport=httpx.MockTransport(handler))


def test_fetch_verifies_extracts_and_writes_notice(tmp_path: Path) -> None:
    calls: list[str] = []
    sha = hashlib.sha256(ARCHIVE).hexdigest()
    out = fetch_spider(tmp_path, "https://example.test/s.zip", sha, _client(ARCHIVE, calls))
    assert (out / "dev.json").read_bytes() == b"[]"
    assert (out / "database" / "x" / "x.sqlite").exists()
    assert not (tmp_path / "spider" / "__MACOSX").exists()
    assert not (out / ".DS_Store").exists()
    notice = (tmp_path / "spider" / "LICENSE_NOTICE.txt").read_text()
    assert "CC BY-SA 4.0" in notice
    assert sha in notice
    # A second fetch reuses the verified archive.
    fetch_spider(tmp_path, "https://example.test/s.zip", sha, _client(ARCHIVE, calls))
    assert len(calls) == 1


def test_checksum_mismatch_deletes_the_download_and_extracts_nothing(tmp_path: Path) -> None:
    with pytest.raises(ChecksumError, match="pinned"):
        fetch_spider(tmp_path, "https://example.test/s.zip", "0" * 64, _client(ARCHIVE, []))
    assert not (tmp_path / "downloads" / "spider_data.zip").exists()
    assert not (tmp_path / "spider").exists()


def test_extraction_refuses_paths_outside_the_target(tmp_path: Path) -> None:
    evil = tmp_path / "evil.zip"
    evil.write_bytes(_zip({"../escaped.txt": b"x"}))
    with pytest.raises(ValueError, match="unsafe path"):
        safe_extract(evil, tmp_path / "out")
    assert not (tmp_path / "escaped.txt").exists()


def test_pin_and_licence_are_set() -> None:
    assert len(SPIDER_SHA256) == 64
    assert "CC BY-SA 4.0" in LICENSE_NOTICE


def _git(*args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=ROOT, check=True, capture_output=True, text=True
    ).stdout


def test_data_dir_is_ignored_by_git() -> None:
    assert _git("check-ignore", "data/spider/spider_data/dev.json").strip()


def test_no_benchmark_data_is_tracked() -> None:
    tracked = _git("ls-files").splitlines()
    assert not [p for p in tracked if p.startswith("data/")]
    assert not [p for p in tracked if p.endswith((".sqlite", ".db", "dev.json", "tables.json"))]
