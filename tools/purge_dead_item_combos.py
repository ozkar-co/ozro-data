"""Remove item_combos sets whose members are missing from playable items.

A set is dead if any Combo member is not in reports/items.jsonl (OzRo client scope).
Groups with no remaining sets are removed entirely. Dead YAML is written under
trash_bin/db/ozro_archive/ (outside the live load tree).

Usage (from ozro-data):
  python3 tools/purge_dead_item_combos.py
  python3 tools/purge_dead_item_combos.py --dry-run
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from discovery.scan import _load_extractor_config  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    cfg = _load_extractor_config(ROOT)
    rathena = Path(cfg["paths"]["rathena"])
    reports_dir = ROOT / cfg["output"]["reports_dir"]
    items_path = reports_dir / "items.jsonl"
    if not items_path.is_file():
        raise SystemExit(f"missing {items_path}; run: python3 pipeline.py extract items")

    live: set[str] = set()
    for line in items_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        it = json.loads(line)
        if it.get("aegis_name"):
            live.add(str(it["aegis_name"]).upper())

    path = rathena / "db/re/item_combos.yml"
    doc = yaml.safe_load(path.read_text(encoding="utf-8", errors="replace"))
    body = list((doc or {}).get("Body") or [])

    kept_body: list[dict] = []
    dead_body: list[dict] = []
    kept_sets = 0
    dead_sets = 0
    dropped_groups = 0

    for row in body:
        if not isinstance(row, dict):
            continue
        if row.get("Clear") is True:
            kept_body.append(row)
            continue
        combos = row.get("Combos") or []
        live_combos: list[dict] = []
        dead_combos: list[dict] = []
        for c in combos:
            if not isinstance(c, dict):
                continue
            names = [str(n) for n in (c.get("Combo") or []) if n]
            if len(names) < 2:
                dead_combos.append(c)
                dead_sets += 1
                continue
            if all(n.upper() in live for n in names):
                live_combos.append(c)
                kept_sets += 1
            else:
                dead_combos.append(c)
                dead_sets += 1
        if live_combos:
            new_row = dict(row)
            new_row["Combos"] = live_combos
            kept_body.append(new_row)
            if dead_combos:
                dead_body.append(
                    {"Combos": dead_combos, "Script": row.get("Script")}
                )
        else:
            dropped_groups += 1
            dead_body.append(dict(row))

    print(
        f"groups_in={len(body)} groups_out={len(kept_body)} "
        f"dropped_groups={dropped_groups} kept_sets={kept_sets} dead_sets={dead_sets}"
    )
    if args.dry_run:
        return

    archive_dir = rathena / "trash_bin/db/ozro_archive"
    archive_dir.mkdir(parents=True, exist_ok=True)
    arch = archive_dir / "item_combos_dead.yml"
    arch_doc = {
        "Header": {"Type": "COMBO_DB", "Version": 1},
        "Body": dead_body,
    }
    arch_text = yaml.dump(
        arch_doc, default_flow_style=False, allow_unicode=True, sort_keys=False, width=120
    )
    arch_text = arch_text.replace(": True", ": true").replace(": False", ": false")
    arch.write_text(
        "# Archived dead item_combos (member missing from OzRo items/client scope).\n"
        f"# dead_sets={dead_sets} dropped_groups={dropped_groups}\n"
        + arch_text,
        encoding="utf-8",
    )

    out_doc = {
        "Header": {"Type": "COMBO_DB", "Version": 1},
        "Body": kept_body,
    }
    # Keep original license header comment block if present
    raw = path.read_text(encoding="utf-8", errors="replace")
    header_end = raw.find("Header:")
    preamble = raw[:header_end] if header_end > 0 else (
        "# OzRo: purged dead combos (missing item_db members).\n"
    )
    body_yaml = yaml.dump(
        out_doc, default_flow_style=False, allow_unicode=True, sort_keys=False, width=120
    )
    body_yaml = body_yaml.replace(": True", ": true").replace(": False", ": false")
    path.write_text(preamble + body_yaml, encoding="utf-8")
    print(f"wrote {path}")
    print(f"wrote {arch}")


if __name__ == "__main__":
    main()
