"""Mobs extractor — mob_db YAML (+ import merge) + client sprite presence."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

import yaml

from discovery.scan import _load_extractor_config

# Quest props studied in Etapa 2 (Rebellion targets + Prontera castle plate).
_QUEST_PROP_IDS = frozenset({3169, 3170, 3455})

# Meister ABR + Biolo wooden summons (mob.hpp MOBID_* / Aegis prefixes).
_SKILL_SUMMON_ID_RANGE = frozenset(range(20834, 20838)) | frozenset(range(20848, 20852))

_PET_MOB_RE = re.compile(r"(?m)^\s+- Mob:\s+(\S+)")


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


def _load_pet_aegis_names(rathena: Path) -> set[str]:
    path = rathena / "db/re/pet_db.yml"
    if not path.is_file():
        return set()
    return set(_PET_MOB_RE.findall(path.read_text(encoding="utf-8", errors="replace")))


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


def _is_thin_stub(row: dict[str, Any]) -> bool:
    """True when YAML is essentially Id + AegisName + Name only."""
    return (
        row.get("Level") is None
        and row.get("Hp") is None
        and row.get("Race") is None
        and row.get("Element") is None
        and row.get("Attack") is None
    )


def _load_spawn_role_evidence(spawns_path: Path) -> dict[int, str]:
    """mob_id → role from spawn evidence (Etapa 3).

    Priority: map_spawn > instance > scripted > slave.
    """
    evidence: dict[int, dict[str, bool]] = {}
    if not spawns_path.is_file():
        return {}
    for line in spawns_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        mid = row.get("mob_id")
        if mid is None:
            continue
        mid = int(mid)
        slot = evidence.setdefault(
            mid,
            {"map": False, "instance": False, "scripted": False, "slave": False},
        )
        st = row.get("spawn_type")
        if st == "instance":
            slot["instance"] = True
        elif st == "scripted":
            slot["scripted"] = True
        elif st == "slave":
            slot["slave"] = True
        elif st in ("skill_summon", "pet"):
            continue
        else:
            # permanent / event headers
            slot["map"] = True

    out: dict[int, str] = {}
    for mid, flags in evidence.items():
        if flags["map"]:
            out[mid] = "map_spawn"
        elif flags["instance"]:
            out[mid] = "instance"
        elif flags["scripted"]:
            out[mid] = "scripted"
        elif flags["slave"]:
            out[mid] = "slave"
    return out


def classify_mob_role(
    mid: int,
    row: dict[str, Any],
    pet_aegis: set[str],
    spawn_roles: dict[int, str] | None = None,
) -> tuple[str, str]:
    """Return (mob_role, role_reason). Layer is always inferred for now."""
    aegis = str(row.get("AegisName") or "")
    ai = str(row.get("Ai") or "")

    if (
        mid in _SKILL_SUMMON_ID_RANGE
        or ai.startswith("Abr_")
        or aegis.startswith("ABR_")
        or aegis.startswith("SUMMON_")
    ):
        return "skill_summon", "skill_summon_id_or_ai_or_prefix"

    if mid in _QUEST_PROP_IDS:
        return "quest_prop", "known_quest_prop_id"

    if _is_thin_stub(row):
        return "stub", "thin_yaml_stub"

    # Pet-only stubs in pet_db (e.g. J_TAINI); field pets like PORING stay pending/map_spawn.
    if aegis in pet_aegis and row.get("Hp") is None:
        return "pet", "pet_db_without_hp"

    spawn_roles = spawn_roles or {}
    if mid in spawn_roles:
        role = spawn_roles[mid]
        if role == "map_spawn":
            return "map_spawn", "spawn_header_permanent_or_event"
        if role == "instance":
            return "instance", "spawn_instance_only"
        if role == "scripted":
            return "scripted", "script_monster_areamonster_guardian"
        if role == "slave":
            return "slave", "mob_skill_db_summonslave"

    return "pending", "awaiting_spawn_or_usage_evidence"


def extract_mobs(project_root: Path | None = None) -> dict[str, Any]:
    root = project_root or Path(__file__).resolve().parents[1]
    cfg = _load_extractor_config(root)
    rathena = Path(cfg["paths"]["rathena"])
    reports_dir = root / cfg["output"]["reports_dir"]
    reports_dir.mkdir(parents=True, exist_ok=True)

    mob_files = list(cfg["db"]["mob_files"])
    by_id, import_ids = _load_mob_db(rathena, mob_files)
    gaps = _load_jsonl_index(reports_dir / "client_mob_server_gaps.jsonl", "mob_id")
    pet_aegis = _load_pet_aegis_names(rathena)
    spawn_roles = _load_spawn_role_evidence(reports_dir / "spawns.jsonl")

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

        mob_role, role_reason = classify_mob_role(mid, row, pet_aegis, spawn_roles)
        mvp_exp = row.get("MvpExp")
        is_mvp = bool(mvp_exp)

        source_path = mob_files[0]
        record = {
            "mob_id": mid,
            "aegis_name": row.get("AegisName"),
            "name": row.get("Name"),
            "japanese_name": row.get("JapaneseName"),
            "mob_class": row.get("Class") or "Normal",
            "mob_role": mob_role,
            "is_mvp": is_mvp,
            "level": row.get("Level"),
            "hp_base": row.get("Hp"),
            "hp_multiplier": None,
            "hp_effective": None,
            "sp": row.get("Sp"),
            "base_exp_base": row.get("BaseExp"),
            "base_exp_effective": None,
            "job_exp_base": row.get("JobExp"),
            "job_exp_effective": None,
            "mvp_exp_base": mvp_exp,
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
            "classification_layer": "inferred",
            "provenance_id": _provenance_id("mobs", str(mid), source_path),
            "source": {
                "mob_files": mob_files,
                "client_gaps": "reports/client_mob_server_gaps.jsonl" if gap else None,
                "import_override": mid in import_ids,
                "mob_role_reason": role_reason,
                "in_pet_db": (row.get("AegisName") or "") in pet_aegis,
            },
        }
        records.append(record)

    out_path = reports_dir / "mobs.jsonl"
    with out_path.open("w", encoding="utf-8") as f:
        for row in records:
            f.write(json.dumps(row, ensure_ascii=False, sort_keys=False) + "\n")

    by_class: dict[str, int] = {}
    by_role: dict[str, int] = {}
    for r in records:
        by_class[r["mob_class"]] = by_class.get(r["mob_class"], 0) + 1
        by_role[r["mob_role"]] = by_role.get(r["mob_role"], 0) + 1

    summary = {
        "domain": "mobs",
        "mob_count": len(records),
        "with_sprite": sum(1 for r in records if r["has_sprite"]),
        "without_sprite": sum(1 for r in records if not r["has_sprite"]),
        "import_override_count": len(import_ids),
        "mvp_count": sum(1 for r in records if r["is_mvp"]),
        "by_class": by_class,
        "by_role": by_role,
        "spawn_evidence_mobs": len(spawn_roles),
        "wrote": str(out_path),
    }
    summary_path = reports_dir / "mobs_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    summary["summary_path"] = str(summary_path)
    return summary
