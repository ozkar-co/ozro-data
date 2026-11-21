"""Item scripts — Script / EquipScript / UnEquipScript from item_db (Etapa 3)."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

import yaml

from discovery.scan import _load_extractor_config
from extractors.client_scope import load_client_item_ids

_SCRIPT_KINDS = ("Script", "EquipScript", "UnEquipScript")

_TRIGGER = {
    "Script": "OnUse",
    "EquipScript": "OnEquip",
    "UnEquipScript": "OnUnequip",
}


def _cmd(*names: str) -> re.Pattern[str]:
    """Match rAthena cmds: `cmd(`, `cmd args`, or bare `cmd;`."""
    alt = "|".join(re.escape(n) for n in names)
    return re.compile(rf"\b(?:{alt})(?:\s*\(|\s+|;)")


# High-confidence command → effect tag (not full semantics).
_EFFECT_RULES: list[tuple[str, re.Pattern[str]]] = [
    ("heal", _cmd("itemheal", "percentheal", "heal")),
    ("status", _cmd("sc_start", "sc_start2", "sc_start4", "sc_end", "sc_end_class")),
    ("getitem", _cmd("getitem", "getitembound", "getgroupitem", "getrandgroupitem", "getnameditem")),
    ("delitem", _cmd("delitem", "delitem2", "consumeitem")),
    ("skill", _cmd("skill", "itemskill", "addtoskill")),
    ("bonus", _cmd("bonus", "bonus2", "bonus3", "bonus4", "bonus5", "autobonus", "autobonus2", "autobonus3")),
    ("warp", _cmd("warp", "warpparty", "warpguild", "savepoint")),
    ("pet", _cmd("pet", "bpet")),
    ("monster", _cmd("monster", "areamonster", "guardian")),
    ("callfunc", _cmd("callfunc", "callsub")),
    ("unit", _cmd("unitwalk", "unitattack", "unitskilluseid")),
    ("refine", _cmd("successrefitem", "failedrefitem", "getequiprefinerycnt")),
    ("effect", _cmd("specialeffect", "specialeffect2", "misceffect", "hateffect")),
    ("rent", _cmd("rentitem", "rentitem2")),
    ("mercenary", _cmd("mercenary_create", "mercenary_delete", "mercenary_heal", "mercenary_sc_start")),
    ("laphine", _cmd("laphine_synthesis", "laphine_upgrade")),
    ("reform", _cmd("item_reform", "item_enchant")),
    ("produce", _cmd("produce", "cooking", "makerune")),
    ("transform", _cmd("transform", "setmounting", "setfont")),
]


def _provenance_id(domain: str, record_id: str, source_path: str) -> str:
    raw = f"{domain}|{record_id}|{source_path}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def _script_id(item_id: int, kind: str, body: str) -> str:
    return hashlib.sha1(f"item_script|{item_id}|{kind}|{body}".encode()).hexdigest()


def _normalize_body(raw: Any) -> str | None:
    if raw is None:
        return None
    if isinstance(raw, str):
        body = raw.strip("\n")
        return body if body.strip() else None
    # unexpected structured value
    body = str(raw).strip()
    return body or None


def _parse_effects(body: str) -> tuple[list[dict[str, str]], str]:
    tags: list[str] = []
    for tag, pat in _EFFECT_RULES:
        if pat.search(body):
            tags.append(tag)
    effects = [{"tag": t} for t in tags]
    if not body.strip():
        return [], "empty"
    if effects:
        return effects, "effects_partial"
    return [], "raw"


def extract_item_scripts(project_root: Path | None = None) -> dict[str, Any]:
    root = project_root or Path(__file__).resolve().parents[1]
    cfg = _load_extractor_config(root)
    rathena = Path(cfg["paths"]["rathena"])
    reports_dir = root / cfg["output"]["reports_dir"]
    reports_dir.mkdir(parents=True, exist_ok=True)

    files: list[str] = list(cfg.get("db", {}).get("item_files") or [])
    client_ids = load_client_item_ids(reports_dir)
    # item_id+kind → record (later files / import override)
    by_key: dict[tuple[int, str], dict[str, Any]] = {}
    per_file: dict[str, int] = {}
    skipped_empty = 0
    skipped_no_client = 0

    for rel in files:
        path = rathena / rel
        if not path.is_file():
            continue
        doc = yaml.safe_load(path.read_text(encoding="utf-8", errors="replace"))
        n = 0
        for row in (doc or {}).get("Body") or []:
            iid = row.get("Id")
            if iid is None:
                continue
            iid = int(iid)
            if iid not in client_ids:
                skipped_no_client += 1
                continue
            for kind in _SCRIPT_KINDS:
                body = _normalize_body(row.get(kind))
                if body is None:
                    continue
                effects, status = _parse_effects(body)
                sid = _script_id(iid, kind, body)
                by_key[(iid, kind)] = {
                    "item_script_id": sid,
                    "item_id": iid,
                    "script_kind": kind,
                    "trigger": _TRIGGER[kind],
                    "script_body": body,
                    "script_hash": hashlib.sha1(body.encode("utf-8")).hexdigest(),
                    "parsed_effects": effects,
                    "parse_status": status,
                    "source_file": rel,
                    "aegis_name": row.get("AegisName"),
                    "provenance_id": _provenance_id(
                        "item_scripts", sid, f"{rel}:{kind}"
                    ),
                }
                n += 1
        per_file[rel] = n

    records = list(by_key.values())
    records.sort(key=lambda r: (r["item_id"], r["script_kind"]))

    out_path = reports_dir / "item_scripts.jsonl"
    with out_path.open("w", encoding="utf-8") as f:
        for row in records:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    by_kind: dict[str, int] = {}
    by_status: dict[str, int] = {}
    effect_tags: dict[str, int] = {}
    items_with: set[int] = set()
    for r in records:
        by_kind[r["script_kind"]] = by_kind.get(r["script_kind"], 0) + 1
        by_status[r["parse_status"]] = by_status.get(r["parse_status"], 0) + 1
        items_with.add(r["item_id"])
        for e in r["parsed_effects"]:
            effect_tags[e["tag"]] = effect_tags.get(e["tag"], 0) + 1

    summary = {
        "domain": "item_scripts",
        "script_count": len(records),
        "unique_items": len(items_with),
        "by_kind": by_kind,
        "by_parse_status": by_status,
        "effect_tags": effect_tags,
        "per_file": per_file,
        "skipped_empty": skipped_empty,
        "skipped_no_client": skipped_no_client,
        "deferred": [
            "getgroupitem_group_resolve",
            "callfunc_expansion",
            "combo_scripts",
            "llm_semantic_parse",
            "raw_tail_roulette_zeny_exp",
        ],
        "wrote": str(out_path),
    }
    summary_path = reports_dir / "item_scripts_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    summary["summary_path"] = str(summary_path)
    return summary
