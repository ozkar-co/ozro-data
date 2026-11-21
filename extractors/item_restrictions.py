"""Item restrictions — Trade YAML + item_noequip bitmask (Etapa 3)."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

import yaml

from discovery.scan import _load_extractor_config

# Trade: keys (YAML) → restriction_key. Keep each separate (brief §11).
_TRADE_KEYS = (
    "NoDrop",
    "NoTrade",
    "NoSell",
    "NoStorage",
    "NoCart",
    "NoMail",
    "NoAuction",
    "NoGuildStorage",
    "PartnerOverride",  # rare / alternate naming if present
    "Override",
)

# item_noequip.txt Flag bitmask (db/re/item_noequip.txt legend).
_NOEQUIP_BITS: list[tuple[int, str]] = [
    (1, "noequip_normal_maps"),
    (2, "noequip_pvp"),
    (4, "noequip_gvg"),
    (8, "noequip_battlegrounds"),
    (16, "noequip_woe_te"),
    (32, "noequip_zone_1"),
    (64, "noequip_zone_2"),
    (128, "noequip_zone_3"),
    (256, "noequip_zone_4"),
    (512, "noequip_zone_5"),
    (1024, "noequip_zone_6"),
    (2048, "noequip_zone_7"),
]


def _provenance_id(domain: str, record_id: str, source_path: str) -> str:
    raw = f"{domain}|{record_id}|{source_path}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def _load_item_rows(
    rathena: Path, files: list[str]
) -> dict[int, tuple[dict[str, Any], str]]:
    """item_id → (merged row, last source file)."""
    by_id: dict[int, tuple[dict[str, Any], str]] = {}
    for rel in files:
        path = rathena / rel
        if not path.is_file():
            continue
        doc = yaml.safe_load(path.read_text(encoding="utf-8", errors="replace"))
        for row in (doc or {}).get("Body") or []:
            iid = row.get("Id")
            if iid is None:
                continue
            iid = int(iid)
            if iid not in by_id:
                by_id[iid] = (dict(row), rel)
            else:
                merged = dict(by_id[iid][0])
                merged.update(row)
                by_id[iid] = (merged, rel)
    return by_id


def _parse_noequip_file(path: Path) -> list[tuple[int, int, int]]:
    """Return list of (item_id, flag, line_no)."""
    rows: list[tuple[int, int, int]] = []
    if not path.is_file():
        return rows
    for line_no, raw in enumerate(
        path.read_text(encoding="utf-8", errors="replace").splitlines(), 1
    ):
        line = raw.split("//", 1)[0].strip()
        if not line:
            continue
        # ItemID,Flag
        m = re.match(r"^(\d+)\s*,\s*(-?\d+)\s*$", line)
        if not m:
            continue
        rows.append((int(m.group(1)), int(m.group(2)), line_no))
    return rows


def _decode_noequip(flag: int) -> list[str]:
    if flag <= 0:
        return []
    return [name for bit, name in _NOEQUIP_BITS if flag & bit]


def extract_item_restrictions(project_root: Path | None = None) -> dict[str, Any]:
    root = project_root or Path(__file__).resolve().parents[1]
    cfg = _load_extractor_config(root)
    rathena = Path(cfg["paths"]["rathena"])
    reports_dir = root / cfg["output"]["reports_dir"]
    reports_dir.mkdir(parents=True, exist_ok=True)

    item_files: list[str] = list(cfg.get("db", {}).get("item_files") or [])
    by_id = _load_item_rows(rathena, item_files)

    records: list[dict[str, Any]] = []
    by_source: dict[str, int] = {"trade": 0, "flag_noconsume": 0, "noequip": 0}
    by_key: dict[str, int] = {}

    for iid, (row, src) in by_id.items():
        trade = row.get("Trade")
        if isinstance(trade, dict):
            for key in _TRADE_KEYS:
                if key not in trade:
                    continue
                val = trade[key]
                # Only store affirmative restrictions (true) or numeric Override
                if val is True or (key == "Override" and val not in (None, False, 0)):
                    rid = f"{iid}|trade.{key}"
                    records.append(
                        {
                            "item_id": iid,
                            "restriction_key": f"trade.{key}",
                            "restriction_value": val
                            if key == "Override"
                            else True,
                            "source_kind": "trade",
                            "source_file": src,
                            "aegis_name": row.get("AegisName"),
                            "provenance_id": _provenance_id(
                                "item_restrictions", rid, f"{src}:Trade.{key}"
                            ),
                        }
                    )
                    by_source["trade"] += 1
                    by_key[f"trade.{key}"] = by_key.get(f"trade.{key}", 0) + 1

        flags = row.get("Flags")
        if isinstance(flags, dict) and flags.get("NoConsume") is True:
            rid = f"{iid}|flag.NoConsume"
            records.append(
                {
                    "item_id": iid,
                    "restriction_key": "flag.NoConsume",
                    "restriction_value": True,
                    "source_kind": "flag",
                    "source_file": src,
                    "aegis_name": row.get("AegisName"),
                    "provenance_id": _provenance_id(
                        "item_restrictions", rid, f"{src}:Flags.NoConsume"
                    ),
                }
            )
            by_source["flag_noconsume"] += 1
            by_key["flag.NoConsume"] = by_key.get("flag.NoConsume", 0) + 1

    # noequip: base then import override (same item_id replaces)
    noequip_map: dict[int, tuple[int, str, int]] = {}
    for rel in ("db/re/item_noequip.txt", "db/import/item_noequip.txt"):
        for iid, flag, line_no in _parse_noequip_file(rathena / rel):
            noequip_map[iid] = (flag, rel, line_no)

    for iid, (flag, rel, line_no) in sorted(noequip_map.items()):
        decoded = _decode_noequip(flag)
        rid = f"{iid}|noequip"
        records.append(
            {
                "item_id": iid,
                "restriction_key": "noequip",
                "restriction_value": {
                    "flag": flag,
                    "flags_decoded": decoded,
                },
                "source_kind": "noequip",
                "source_file": rel,
                "source_line": line_no,
                "aegis_name": (by_id.get(iid) or ({}, None))[0].get("AegisName"),
                "provenance_id": _provenance_id(
                    "item_restrictions", rid, f"{rel}:{line_no}"
                ),
            }
        )
        by_source["noequip"] += 1
        by_key["noequip"] = by_key.get("noequip", 0) + 1
        for name in decoded:
            by_key[name] = by_key.get(name, 0) + 1

    records.sort(key=lambda r: (r["item_id"], r["restriction_key"]))

    out_path = reports_dir / "item_restrictions.jsonl"
    with out_path.open("w", encoding="utf-8") as f:
        for row in records:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    summary = {
        "domain": "item_restrictions",
        "restriction_rows": len(records),
        "unique_items": len({r["item_id"] for r in records}),
        "by_source": by_source,
        "by_key": by_key,
        "deferred": [
            "jobs_as_restrictions",
            "equip_level_as_restrictions",
            "noequip_zone_mapflag_names",
            "script_runtime_use_blocks",
        ],
        "wrote": str(out_path),
    }
    summary_path = reports_dir / "item_restrictions_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    summary["summary_path"] = str(summary_path)
    return summary
