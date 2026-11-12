"""Download Spider (dev) into the gitignored `data/` directory, checksum-pinned.

    uv run python -m scripts.fetch_benchmarks

Spider is licensed CC BY-SA 4.0 (Yu et al., 2018; https://yale-lily.github.io/spider).
Askwell's code is Apache-2.0, so Spider data and question text are never committed:
this script fetches them, and the repo commits only question IDs (indices into dev.json).
"""

from __future__ import annotations

import argparse
import hashlib
import shutil
import sys
import zipfile
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"

# The official download linked from https://yale-lily.github.io/spider ("spider_data.zip",
# the 2020-08-03 revision of train/dev with databases). Pinned on 2026-11-09.
SPIDER_URL = (
    "https://drive.usercontent.google.com/download"
    "?id=1403EGqzIDoHMdQF4c9Bkyl7dZLZ5Wt6J&export=download&confirm=t"
)
SPIDER_SHA256 = "00636695dabed6b5f4b8328a16b13e069a2f16591d5efcce57660669c85b121b"

LICENSE_NOTICE = """\
Spider dataset (https://yale-lily.github.io/spider)
Tao Yu, Rui Zhang, Kai Yang, Michihiro Yasunaga, Dongxu Wang, Zifan Li, James Ma,
Irene Li, Qingning Yao, Shanelle Roman, Zilin Zhang, Dragomir Radev.
"Spider: A Large-Scale Human-Labeled Dataset for Complex and Cross-Domain Semantic
Parsing and Text-to-SQL Task." EMNLP 2018.

Licensed under CC BY-SA 4.0: https://creativecommons.org/licenses/by-sa/4.0/legalcode
Downloaded unmodified by scripts/fetch_benchmarks.py, archive sha256 {sha256}.
This data is not part of Askwell's Apache-2.0 code and must not be committed.
"""


class ChecksumError(RuntimeError):
    pass


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download(url: str, dest: Path, client: httpx.Client | None = None) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    partial = dest.with_suffix(dest.suffix + ".part")
    http = client or httpx.Client(timeout=httpx.Timeout(60, read=300), follow_redirects=True)
    try:
        with http.stream("GET", url) as response:
            response.raise_for_status()
            with partial.open("wb") as fh:
                for chunk in response.iter_bytes(1 << 20):
                    fh.write(chunk)
    finally:
        if client is None:
            http.close()
    partial.replace(dest)


def verify(path: Path, expected_sha256: str) -> None:
    actual = sha256_of(path)
    if actual != expected_sha256:
        path.unlink()
        raise ChecksumError(
            f"{path.name}: sha256 {actual} != pinned {expected_sha256}; file deleted"
        )


def safe_extract(archive: Path, dest: Path) -> list[str]:
    """Extract, skipping macOS metadata and refusing any path that escapes `dest`."""
    dest = dest.resolve()
    names: list[str] = []
    with zipfile.ZipFile(archive) as zf:
        for member in zf.infolist():
            name = member.filename
            if name.startswith("__MACOSX/") or name.endswith(".DS_Store"):
                continue
            target = (dest / name).resolve()
            if not target.is_relative_to(dest):
                raise ValueError(f"unsafe path in archive: {name}")
            names.append(name)
        for name in names:
            zf.extract(name, dest)
    return names


def fetch_spider(
    data_dir: Path = DATA,
    url: str = SPIDER_URL,
    expected_sha256: str = SPIDER_SHA256,
    client: httpx.Client | None = None,
) -> Path:
    """Fetch, verify and extract Spider. Returns the extracted `spider_data` directory."""
    archive = data_dir / "downloads" / "spider_data.zip"
    if not (archive.exists() and sha256_of(archive) == expected_sha256):
        download(url, archive, client)
        verify(archive, expected_sha256)
    out = data_dir / "spider"
    if out.exists():
        shutil.rmtree(out)
    safe_extract(archive, out)
    (out / "LICENSE_NOTICE.txt").write_text(LICENSE_NOTICE.format(sha256=expected_sha256))
    return out / "spider_data"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Download Spider (dev), checksum-pinned.")
    parser.add_argument("--data-dir", type=Path, default=DATA)
    args = parser.parse_args(argv)
    print(LICENSE_NOTICE.format(sha256=SPIDER_SHA256))
    try:
        spider = fetch_spider(args.data_dir)
    except (httpx.HTTPError, ChecksumError) as exc:
        print(f"fetch failed: {exc}", file=sys.stderr)
        return 1
    print(f"Spider extracted to {spider}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
