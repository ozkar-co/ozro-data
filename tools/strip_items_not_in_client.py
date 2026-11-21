"""Remove server item_db entries missing from client_item_info.

Writes removed blocks under trash_bin/db/ozro_archive/ (outside live load tree).
Items stop existing on the map-server after @reloaditemdb / restart.

Usage (from ozro-data):
  python3 tools/strip_items_not_in_client.py
  python3 tools/strip_items_not_in_client.py --dry-run
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from discovery.scan import _load_extractor_config  # noqa: E402
from extractors.client_scope import load_client_item_ids  # noqa: E402

_ID_RE = re.compile(r"^  - Id: (\d+)\b")


def _split_body_blocks(lines: list[str]) -> tuple[list[str], list[list[str]]]:
    """Split into (pre_body_lines, body_blocks). Body starts at first `  - Id:`."""
    first = next((i for i, ln in enumerate(lines) if _ID_RE.match(ln)), None)
    if first is None:
        return lines, []

    pre = lines[:first]
    blocks: list[list[str]] = []
    cur: list[str] = []
    for ln in lines[first:]:
        if _ID_RE.match(ln) and cur:
            blocks.append(cur)
            cur = [ln]
        else:
            cur.append(ln)
    if cur:
        blocks.append(cur)
    return pre, blocks


def _block_id(block: list[str]) -> int | None:
    m = _ID_RE.match(block[0]) if block else None
    return int(m.group(1)) if m else None


def strip_file(
    path: Path, client: set[int], archive_dir: Path, *, dry_run: bool
) -> tuple[int, int]:
    raw = path.read_text(encoding="utf-8", errors="replace")
    lines = raw.splitlines()
    pre, blocks = _split_body_blocks(lines)
    if not blocks:
        return 0, 0

    keep_blocks: list[list[str]] = []
    removed_blocks: list[list[str]] = []
    for block in blocks:
        iid = _block_id(block)
        if iid is None or iid in client:
            keep_blocks.append(block)
        else:
            removed_blocks.append(block)

    rem_n = len(removed_blocks)
    kept_n = len(keep_blocks)
    if rem_n == 0 or dry_run:
        return rem_n, kept_n

    archive_dir.mkdir(parents=True, exist_ok=True)
    arch = archive_dir / f"{path.stem}_not_in_client.yml"
    arch_lines = [
        f"# Archived from {path.as_posix()} — not loaded by item_db.",
        f"# Missing from client_item_info. Count: {rem_n}",
        "Header:",
        "  Type: ITEM_DB",
        "  Version: 3",
        "Body:",
    ]
    for block in removed_blocks:
        arch_lines.extend(block)
    arch.write_text("\n".join(arch_lines) + "\n", encoding="utf-8")

    out_lines = list(pre)
    for block in keep_blocks:
        out_lines.extend(block)
    path.write_text("\n".join(out_lines) + "\n", encoding="utf-8")
    return rem_n, kept_n


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    cfg = _load_extractor_config(ROOT)
    rathena = Path(cfg["paths"]["rathena"])
    reports_dir = ROOT / cfg["output"]["reports_dir"]
    client = load_client_item_ids(reports_dir)
    archive_dir = rathena / "trash_bin/db/ozro_archive"

    files = [
        rel
        for rel in cfg["db"]["item_files"]
        if "client_disabled" not in rel and rel.endswith(".yml")
    ]

    total_rem = 0
    for rel in files:
        path = rathena / rel
        if not path.is_file():
            continue
        rem, kept = strip_file(path, client, archive_dir, dry_run=args.dry_run)
        total_rem += rem
        print(f"{rel}: removed={rem} kept={kept}")

    print(
        f"total_removed={total_rem} client={len(client)} dry_run={args.dry_run} "
        f"archive={archive_dir}"
    )


if __name__ == "__main__":
    main()
