"""Level penalty — flat Type/Difference/Rate rows (Pre-E5).

Sources: db/re/level_penalty.yml then db/import/level_penalty.yml (OzRo overlay).
Same Type+Difference: later file wins.

Rows are the YAML anchors only. Server fill (PenaltyDatabase::loadingFinished)
propagates rates into gaps; consumers that need the full curve must apply that
rule (or ask for an expanded dump later). Do not bake player-level penalty into
mob/drop *_effective fields.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import yaml

from discovery.scan import _load_extractor_config

# Official Type strings in YAML (PENALTY_* constants strip the prefix).
_VALID_TYPES = frozenset({"Exp", "Drop", "Mvp_Exp", "Mvp_Drop"})


def _provenance_id(domain: str, record_id: str, source_path: str) -> str:
    raw = f"{domain}|{record_id}|{source_path}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def _row_id(penalty_type: str, difference: int) -> str:
    raw = f"level_penalty|{penalty_type}|{difference}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def _load_bodies(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    doc = yaml.safe_load(path.read_text(encoding="utf-8", errors="replace")) or {}
    body = doc.get("Body") or []
    return [r for r in body if isinstance(r, dict)]


def _apply_file(
    by_key: dict[tuple[str, int], dict[str, Any]],
    rows: list[dict[str, Any]],
    source_file: str,
) -> int:
    """Overlay LevelDifferences from one file. Returns number of anchors written."""
    n = 0
    for block in rows:
        ptype = str(block.get("Type") or "").strip()
        if ptype not in _VALID_TYPES:
            continue
        for entry in block.get("LevelDifferences") or []:
            if not isinstance(entry, dict):
                continue
            if "Difference" not in entry or "Rate" not in entry:
                continue
            diff = int(entry["Difference"])
            rate = int(entry["Rate"])
            key = (ptype, diff)
            rid = _row_id(ptype, diff)
            by_key[key] = {
                "penalty_id": rid,
                "type": ptype,
                "difference": diff,
                "rate": rate,
                "rate_unit": "percent",
                "source_file": source_file,
                "provenance_id": _provenance_id("level_penalty", rid, source_file),
            }
            n += 1
    return n


def extract_level_penalty(project_root: Path | None = None) -> dict[str, Any]:
    root = project_root or Path(__file__).resolve().parents[1]
    cfg = _load_extractor_config(root)
    rathena = Path(cfg["paths"]["rathena"])
    reports_dir = root / cfg["output"]["reports_dir"]
    reports_dir.mkdir(parents=True, exist_ok=True)

    # Match db/level_penalty.yml Footer import order (Renewal).
    files = [
        ("db/re/level_penalty.yml", rathena / "db/re/level_penalty.yml"),
        ("db/import/level_penalty.yml", rathena / "db/import/level_penalty.yml"),
    ]

    by_key: dict[tuple[str, int], dict[str, Any]] = {}
    applied: list[dict[str, Any]] = []
    for rel, path in files:
        rows = _load_bodies(path)
        n = _apply_file(by_key, rows, rel)
        applied.append(
            {
                "source_file": rel,
                "exists": path.is_file(),
                "body_blocks": len(rows),
                "anchors_applied": n,
            }
        )

    records = sorted(
        by_key.values(),
        key=lambda r: (r["type"], r["difference"]),
    )

    out_path = reports_dir / "level_penalty.jsonl"
    with out_path.open("w", encoding="utf-8") as f:
        for row in records:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    by_type: dict[str, int] = {}
    for r in records:
        by_type[r["type"]] = by_type.get(r["type"], 0) + 1

    # Spot anchors used in E4 live verify (overlevel character).
    def _rate(ptype: str, diff: int) -> int | None:
        row = by_key.get((ptype, diff))
        return None if row is None else int(row["rate"])

    summary = {
        "domain": "level_penalty",
        "row_count": len(records),
        "by_type": by_type,
        "sources": applied,
        "fill_rule": (
            "Sparse YAML anchors only. Server fills gaps by propagating the last "
            "defined rate from Difference 0 outward in both directions "
            "(PenaltyDatabase::loadingFinished). Default unset = 100."
        ),
        "ozro_spot_checks": {
            "Exp_diff_-31": _rate("Exp", -31),
            "Drop_diff_-16": _rate("Drop", -16),
            "Drop_diff_16": _rate("Drop", 16),
        },
        "note": (
            "Do not apply these rates into chance_effective / *_exp_effective; "
            "query this table when computing player-relative modifiers."
        ),
        "wrote": str(out_path),
    }
    summary_path = reports_dir / "level_penalty_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    summary["summary_path"] = str(summary_path)
    return summary
