"""Skills / mob_skill_db — summons & slave links (Etapa 3, before NPC analysis)."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from discovery.scan import _load_extractor_config

# NPC_DEATHSUMMON also calls mob_summonslave(); skill_lv = amount; val[0..4] = mob ids.
_SUMMON_SKILLS = frozenset({"NPC_SUMMONSLAVE", "NPC_SUMMONMONSTER", "NPC_DEATHSUMMON"})


def _provenance_id(domain: str, record_id: str, source_path: str) -> str:
    raw = f"{domain}|{record_id}|{source_path}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def _summon_id(*parts: Any) -> str:
    raw = "|".join("" if p is None else str(p) for p in parts)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def _parse_dummy_skill(dummy: str) -> tuple[str | None, str | None]:
    """Osiris@NPC_SUMMONSLAVE → (label, skill_name)."""
    if "@" not in dummy:
        return None, dummy or None
    left, right = dummy.split("@", 1)
    return left or None, right or None


def iter_mob_skill_rows(path: Path) -> list[dict[str, Any]]:
    """Parse db/re/mob_skill_db.txt rows into dicts."""
    rows: list[dict[str, Any]] = []
    if not path.is_file():
        return rows
    for line_no, raw in enumerate(
        path.read_text(encoding="utf-8", errors="replace").splitlines(), 1
    ):
        line = raw.strip()
        if not line or line.startswith("//"):
            continue
        parts = [p.strip() for p in line.split(",")]
        if len(parts) < 13:
            continue
        if not re.fullmatch(r"-?\d+", parts[0]):
            continue
        mob_id = int(parts[0])
        dummy = parts[1]
        label, skill_name = _parse_dummy_skill(dummy)
        skill_id = int(parts[3]) if re.fullmatch(r"-?\d+", parts[3] or "") else None
        skill_lv = int(parts[4]) if re.fullmatch(r"-?\d+", parts[4] or "") else None
        rate = int(parts[5]) if re.fullmatch(r"-?\d+", parts[5] or "") else None
        cond_type = parts[10] or None
        cond_val = parts[11] or None
        vals: list[int] = []
        for i in range(12, min(17, len(parts))):
            if re.fullmatch(r"-?\d+", parts[i] or ""):
                v = int(parts[i])
                if v > 0:
                    vals.append(v)
        val1 = vals[0] if vals else None
        rows.append(
            {
                "mob_id": mob_id,
                "dummy": dummy,
                "mob_label": label,
                "skill_name": skill_name,
                "state": parts[2] or None,
                "skill_id": skill_id,
                "skill_lv": skill_lv,
                "rate": rate,
                "cancelable": parts[8] or None,
                "target": parts[9] or None,
                "condition_type": cond_type,
                "condition_value": cond_val,
                "val1": val1,
                "vals": vals,
                "source_file": str(path.name),
                "source_line": line_no,
            }
        )
    return rows


def extract_skills(project_root: Path | None = None) -> dict[str, Any]:
    root = project_root or Path(__file__).resolve().parents[1]
    cfg = _load_extractor_config(root)
    rathena = Path(cfg["paths"]["rathena"])
    reports_dir = root / cfg["output"]["reports_dir"]
    reports_dir.mkdir(parents=True, exist_ok=True)

    # Prefer RE path; fall back to import override file if present later.
    skill_path = rathena / "db/re/mob_skill_db.txt"
    import_path = rathena / "db/import/mob_skill_db.txt"
    rows = iter_mob_skill_rows(skill_path)
    if import_path.is_file():
        rows.extend(iter_mob_skill_rows(import_path))

    mob_skill_records: list[dict[str, Any]] = []
    summons: list[dict[str, Any]] = []
    seen_summon: set[str] = set()

    for row in rows:
        mid = row["mob_id"]
        sk_name = row.get("skill_name") or ""
        msid = _summon_id(
            "mob_skill",
            mid,
            sk_name,
            row.get("state"),
            row.get("skill_id"),
            row.get("skill_lv"),
            row.get("condition_type"),
            row.get("condition_value"),
            row.get("val1"),
            row.get("source_file"),
            row.get("source_line"),
        )
        mob_skill_records.append(
            {
                "mob_skill_id": msid,
                "mob_id": mid,
                "skill_id": row.get("skill_id"),
                "skill_name": sk_name or None,
                "state": row.get("state"),
                "skill_lv": row.get("skill_lv"),
                "rate": row.get("rate"),
                "condition_type": row.get("condition_type"),
                "condition_value": row.get("condition_value"),
                "val1": row.get("val1"),
                "vals": row.get("vals") or [],
                "source_file": f"db/re/{row['source_file']}"
                if row["source_file"] == "mob_skill_db.txt"
                else f"db/import/{row['source_file']}",
                "source_line": row["source_line"],
                "provenance_id": _provenance_id(
                    "mob_skills", msid, f"{row['source_file']}:{row['source_line']}"
                ),
            }
        )

        if sk_name not in _SUMMON_SKILLS:
            continue
        # mob_summonslave: round-robin over val[0..4]; amount = skill_lv
        children = [c for c in (row.get("vals") or []) if c != mid]
        if not children:
            continue
        amount = row.get("skill_lv")
        src_file = (
            f"db/re/{row['source_file']}"
            if row["source_file"] == "mob_skill_db.txt"
            else f"db/import/{row['source_file']}"
        )
        for child in children:
            sid = _summon_id(
                "mob_slave",
                mid,
                child,
                row.get("skill_id"),
                sk_name,
                row.get("state"),
                row.get("condition_type"),
                row.get("condition_value"),
                row.get("source_file"),
                row.get("source_line"),
            )
            if sid in seen_summon:
                continue
            seen_summon.add(sid)
            summons.append(
                {
                    "summon_id": sid,
                    "summon_kind": "mob_slave",
                    "parent_mob_id": mid,
                    "skill_id": row.get("skill_id"),
                    "skill_name": sk_name,
                    "summoned_mob_id": child,
                    "amount": amount,
                    "conditions": {
                        "state": row.get("state"),
                        "rate": row.get("rate"),
                        "condition_type": row.get("condition_type"),
                        "condition_value": row.get("condition_value"),
                        "skill_lv": row.get("skill_lv"),
                        "vals": children,
                    },
                    "source_file": src_file,
                    "source_line": row["source_line"],
                    "provenance_id": _provenance_id(
                        "skill_summons", sid, f"{row['source_file']}:{row['source_line']}"
                    ),
                }
            )

    ms_path = reports_dir / "mob_skills.jsonl"
    with ms_path.open("w", encoding="utf-8") as f:
        for rec in mob_skill_records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    sum_path = reports_dir / "skill_summons.jsonl"
    with sum_path.open("w", encoding="utf-8") as f:
        for rec in summons:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    summary = {
        "domain": "skills",
        "mob_skill_rows": len(mob_skill_records),
        "skill_summons": len(summons),
        "unique_parent_mobs": len({s["parent_mob_id"] for s in summons}),
        "unique_summoned_mobs": len({s["summoned_mob_id"] for s in summons}),
        "summon_skills": sorted(_SUMMON_SKILLS),
        "deferred": ["player_skill_db_summons", "full_player_skill_catalog"],
        "wrote": [str(ms_path), str(sum_path)],
    }
    summary_path = reports_dir / "skills_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    summary["summary_path"] = str(summary_path)
    return summary
