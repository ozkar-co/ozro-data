"""Mobs extractor — mob_db YAML (+ import merge) + client sprite presence."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import yaml

from discovery.scan import _load_extractor_config


def _provenance_id(domain: str, record_id: str, source_path: str) -> str:
    raw = f"{domain}|{record_id}|{source_path}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def _load_jsonl_index(path: Path, key: str) -> dict[Any, dict[str, Any]]:
    out: dict[Any, dict[str, Any]] = {}
    if not path.is_file():
        return out
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            out[row[key]] = row
    return out


def _load_mob_db(
    rathena: Path, files: list[str]
) -> tuple[dict[int, dict[str, Any]], set[int]]:
    """Load mob YAML in order; later files shallow-merge by Id.

    Returns (by_id, import_override_ids).
    """
    by_id: dict[int, dict[str, Any]] = {}
    import_ids: set[int] = set()
    for rel in files:
        path = rathena / rel
        if not path.is_file():
            continue
        is_import = rel.replace("\\", "/").startswith("db/import/")
        doc = yaml.safe_load(path.read_text(encoding="utf-8", errors="replace"))
        for row in (doc or {}).get("Body") or []:
            mid = row.get("Id")
            if mid is None:
                continue
            mid = int(mid)
            if is_import:
                import_ids.add(mid)
            if mid not in by_id:
                by_id[mid] = dict(row)
            else:
                merged = dict(by_id[mid])
                merged.update(row)
                by_id[mid] = merged
    return by_id, import_ids


def extract_mobs(project_root: Path | None = None) -> dict[str, Any]:
    root = project_root or Path(__file__).resolve().parents[1]
    cfg = _load_extractor_config(root)
    rathena = Path(cfg["paths"]["rathena"])
    reports_dir = root / cfg["output"]["reports_dir"]
    reports_dir.mkdir(parents=True, exist_ok=True)

    mob_files = list(cfg["db"]["mob_files"])
    by_id, import_ids = _load_mob_db(rathena, mob_files)
    gaps = _load_jsonl_index(reports_dir / "client_mob_server_gaps.jsonl", "mob_id")

    records: list[dict[str, Any]] = []
    for mid in sorted(by_id):
        row = by_id[mid]
        gap = gaps.get(mid)
        has_sprite = gap is None
        sprite_name = None
        if gap is not None:
            sprite_name = gap.get("sprite_name")
        elif row.get("AegisName"):
            sprite_name = str(row["AegisName"])

        modes = row.get("Modes")
        if modes is not None and not isinstance(modes, dict):
            modes = {"_raw": modes}

        stats = {
            "str": row.get("Str"),
            "agi": row.get("Agi"),
            "vit": row.get("Vit"),
            "int": row.get("Int"),
            "dex": row.get("Dex"),
            "luk": row.get("Luk"),
            "attack_range": row.get("AttackRange"),
            "skill_range": row.get("SkillRange"),
            "chase_range": row.get("ChaseRange"),
            "walk_speed": row.get("WalkSpeed"),
            "attack_delay": row.get("AttackDelay"),
            "attack_motion": row.get("AttackMotion"),
            "damage_motion": row.get("DamageMotion"),
            "ai": row.get("Ai"),
            "damage_taken": row.get("DamageTaken"),
            "resistance": row.get("Resistance"),
            "magic_resistance": row.get("MagicResistance"),
            "race_groups": row.get("RaceGroups"),
        }

        source_path = mob_files[0]
        record = {
            "mob_id": mid,
            "aegis_name": row.get("AegisName"),
            "name": row.get("Name"),
            "japanese_name": row.get("JapaneseName"),
            "mob_class": row.get("Class") or "Normal",
            "level": row.get("Level"),
            "hp_base": row.get("Hp"),
            "hp_multiplier": None,
            "hp_effective": None,
            "sp": row.get("Sp"),
            "base_exp_base": row.get("BaseExp"),
            "base_exp_effective": None,
            "job_exp_base": row.get("JobExp"),
            "job_exp_effective": None,
            "mvp_exp_base": row.get("MvpExp"),
            "mvp_exp_effective": None,
            "attack": row.get("Attack"),
            "attack2": row.get("Attack2"),
            "defense": row.get("Defense"),
            "magic_defense": row.get("MagicDefense"),
            "stats": stats,
            "race": row.get("Race"),
            "size": row.get("Size"),
            "element": row.get("Element"),
            "element_level": row.get("ElementLevel"),
            "modes": modes,
            "sprite_name": sprite_name,
            "has_sprite": has_sprite,
            "client_gap_reason": gap.get("reason") if gap else None,
            "provenance_id": _provenance_id("mobs", str(mid), source_path),
            "source": {
                "mob_files": mob_files,
                "client_gaps": "reports/client_mob_server_gaps.jsonl" if gap else None,
                "import_override": mid in import_ids,
            },
        }
        records.append(record)

    out_path = reports_dir / "mobs.jsonl"
    with out_path.open("w", encoding="utf-8") as f:
        for row in records:
            f.write(json.dumps(row, ensure_ascii=False, sort_keys=False) + "\n")

    by_class: dict[str, int] = {}
    for r in records:
        by_class[r["mob_class"]] = by_class.get(r["mob_class"], 0) + 1

    summary = {
        "domain": "mobs",
        "mob_count": len(records),
        "with_sprite": sum(1 for r in records if r["has_sprite"]),
        "without_sprite": sum(1 for r in records if not r["has_sprite"]),
        "import_override_count": len(import_ids),
        "by_class": by_class,
        "wrote": str(out_path),
    }
    summary_path = reports_dir / "mobs_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    summary["summary_path"] = str(summary_path)
    return summary
