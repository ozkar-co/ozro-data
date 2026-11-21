"""Quests — quest_db.yml + NPC links from script evidence (Etapa 3)."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

import yaml

from discovery.scan import _load_extractor_config


def _provenance_id(domain: str, record_id: str, source_path: str) -> str:
    raw = f"{domain}|{record_id}|{source_path}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def _parse_time_limit(raw: Any) -> dict[str, Any] | None:
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        return {"seconds": int(raw), "raw": raw}
    s = str(raw).strip()
    m = re.fullmatch(r"(\d+)\s*([smhd])?", s, re.I)
    if not m:
        return {"raw": s}
    n = int(m.group(1))
    unit = (m.group(2) or "s").lower()
    mult = {"s": 1, "m": 60, "h": 3600, "d": 86400}[unit]
    return {"seconds": n * mult, "raw": s}


def extract_quests(project_root: Path | None = None) -> dict[str, Any]:
    root = project_root or Path(__file__).resolve().parents[1]
    cfg = _load_extractor_config(root)
    rathena = Path(cfg["paths"]["rathena"])
    reports_dir = root / cfg["output"]["reports_dir"]
    reports_dir.mkdir(parents=True, exist_ok=True)

    other = list(cfg.get("db", {}).get("other") or [])
    quest_files = [p for p in other if "quest_db" in p]
    if not quest_files:
        quest_files = ["db/re/quest_db.yml", "db/import/quest_db.yml"]

    # item/mob indexes
    item_by_aegis: dict[str, int] = {}
    items_path = reports_dir / "items.jsonl"
    if items_path.is_file():
        for line in items_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            it = json.loads(line)
            if it.get("aegis_name"):
                # quest_db sometimes uses different casing than mob/item db
                item_by_aegis[str(it["aegis_name"]).upper()] = int(it["item_id"])

    mob_by_aegis: dict[str, int] = {}
    mob_by_id: dict[int, str] = {}
    mobs_path = reports_dir / "mobs.jsonl"
    if mobs_path.is_file():
        for line in mobs_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            m = json.loads(line)
            mid = int(m["mob_id"])
            name = m.get("aegis_name")
            if name:
                mob_by_aegis[str(name).upper()] = mid
                mob_by_id[mid] = str(name)

    # merge quest rows (import overrides)
    by_id: dict[int, tuple[dict[str, Any], str]] = {}
    for rel in quest_files:
        path = rathena / rel
        if not path.is_file():
            continue
        doc = yaml.safe_load(path.read_text(encoding="utf-8", errors="replace"))
        for row in (doc or {}).get("Body") or []:
            qid = row.get("Id")
            if qid is None:
                continue
            qid = int(qid)
            if qid not in by_id:
                by_id[qid] = (dict(row), rel)
            else:
                merged = dict(by_id[qid][0])
                merged.update(row)
                by_id[qid] = (merged, rel)

    quests: list[dict[str, Any]] = []
    targets_out: list[dict[str, Any]] = []
    drops_out: list[dict[str, Any]] = []
    unresolved_mob = 0
    unresolved_item = 0

    for qid in sorted(by_id):
        row, src = by_id[qid]
        title = row.get("Title")
        time_limit = _parse_time_limit(row.get("TimeLimit"))
        targets_raw = row.get("Targets") or []
        drops_raw = row.get("Drops") or []

        quests.append(
            {
                "quest_id": qid,
                "title": title,
                "time_limit": time_limit,
                "target_count": len(targets_raw) if isinstance(targets_raw, list) else 0,
                "drop_count": len(drops_raw) if isinstance(drops_raw, list) else 0,
                "source_file": src,
                "provenance_id": _provenance_id("quests", str(qid), src),
            }
        )

        if isinstance(targets_raw, list):
            for i, t in enumerate(targets_raw):
                if not isinstance(t, dict):
                    continue
                # YAML "Id" under Targets = objective index (not mob id).
                objective_id = t.get("Id")
                count = t.get("Count")
                location = t.get("Location")
                race = t.get("Race")
                min_level = t.get("MinLevel")

                mob_entries: list[tuple[str | None, int | None]] = []
                if t.get("Mob") is not None:
                    name = str(t.get("Mob"))
                    mid = mob_by_aegis.get(name.upper())
                    if mid is None:
                        unresolved_mob += 1
                        mob_entries.append((name, None))
                    else:
                        mob_entries.append((mob_by_id.get(mid, name), mid))
                map_mobs = t.get("MapMobTargets")
                if isinstance(map_mobs, dict):
                    for name, active in map_mobs.items():
                        if active is False:
                            continue
                        mid = mob_by_aegis.get(str(name).upper())
                        if mid is None:
                            unresolved_mob += 1
                            mob_entries.append((str(name), None))
                        else:
                            mob_entries.append((mob_by_id.get(mid, str(name)), mid))

                if not mob_entries:
                    # race-only or empty objective — keep row without mob
                    targets_out.append(
                        {
                            "quest_id": qid,
                            "target_index": i,
                            "objective_id": objective_id,
                            "mob_id": None,
                            "mob_aegis_name": None,
                            "count": count,
                            "location": location,
                            "race": race,
                            "min_level": min_level,
                            "source_file": src,
                        }
                    )
                else:
                    for j, (mname, mid) in enumerate(mob_entries):
                        targets_out.append(
                            {
                                "quest_id": qid,
                                "target_index": i,
                                "objective_id": objective_id,
                                "mob_subindex": j,
                                "mob_id": mid,
                                "mob_aegis_name": mname,
                                "count": count,
                                "location": location,
                                "race": race,
                                "min_level": min_level,
                                "source_file": src,
                            }
                        )

        if isinstance(drops_raw, list):
            for i, d in enumerate(drops_raw):
                if not isinstance(d, dict):
                    continue
                mob_aegis = d.get("Mob")
                item_aegis = d.get("Item")
                mob_id = (
                    mob_by_aegis.get(str(mob_aegis).upper()) if mob_aegis else None
                )
                item_id = (
                    item_by_aegis.get(str(item_aegis).upper()) if item_aegis else None
                )
                if mob_aegis and mob_id is None:
                    unresolved_mob += 1
                if item_aegis and item_id is None:
                    unresolved_item += 1
                if mob_id is not None:
                    mob_aegis = mob_by_id.get(mob_id, mob_aegis)
                drops_out.append(
                    {
                        "quest_id": qid,
                        "drop_index": i,
                        "mob_id": mob_id,
                        "mob_aegis_name": str(mob_aegis) if mob_aegis else None,
                        "item_id": item_id,
                        "item_aegis_name": str(item_aegis) if item_aegis else None,
                        "rate": d.get("Rate"),
                        "rate_unit": "per_10000",
                        "source_file": src,
                    }
                )

    # NPC ↔ quest links from evidence
    links: list[dict[str, Any]] = []
    evidence_path = reports_dir / "npc_script_evidence.jsonl"
    linked_quests: set[int] = set()
    if evidence_path.is_file():
        seen: set[tuple[str, int]] = set()
        for line in evidence_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            ev = json.loads(line)
            npc_id = ev.get("npc_id")
            for qid in ev.get("quest_ids") or []:
                try:
                    qid_i = int(qid)
                except (TypeError, ValueError):
                    continue
                key = (str(npc_id), qid_i)
                if key in seen:
                    continue
                seen.add(key)
                linked_quests.add(qid_i)
                role = "related"
                # refine role from evidence functions if quest cmds present
                funcs = ev.get("functions") or []
                if "Quest" in funcs:
                    role = "quest_script"
                lid = hashlib.sha1(f"npc_quest|{npc_id}|{qid_i}".encode()).hexdigest()
                links.append(
                    {
                        "link_id": lid,
                        "npc_id": npc_id,
                        "quest_id": qid_i,
                        "role": role,
                        "script_path": ev.get("script_path"),
                        "script_line": ev.get("script_line"),
                        "in_quest_db": qid_i in by_id,
                        "provenance_id": _provenance_id(
                            "npc_quests", lid, f"{ev.get('script_path')}:{qid_i}"
                        ),
                    }
                )

    orphan_links = sum(1 for L in links if not L["in_quest_db"])
    quests_with_npc = sum(1 for q in quests if q["quest_id"] in linked_quests)

    q_path = reports_dir / "quests.jsonl"
    with q_path.open("w", encoding="utf-8") as f:
        for row in quests:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    t_path = reports_dir / "quest_targets.jsonl"
    with t_path.open("w", encoding="utf-8") as f:
        for row in targets_out:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    d_path = reports_dir / "quest_drops.jsonl"
    with d_path.open("w", encoding="utf-8") as f:
        for row in drops_out:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    l_path = reports_dir / "npc_quest_links.jsonl"
    with l_path.open("w", encoding="utf-8") as f:
        for row in links:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    summary = {
        "domain": "quests",
        "quest_count": len(quests),
        "with_targets": sum(1 for q in quests if q["target_count"]),
        "with_drops": sum(1 for q in quests if q["drop_count"]),
        "with_time_limit": sum(1 for q in quests if q.get("time_limit")),
        "target_rows": len(targets_out),
        "drop_rows": len(drops_out),
        "npc_quest_links": len(links),
        "quests_with_npc_link": quests_with_npc,
        "link_quest_ids_missing_db": orphan_links,
        "unresolved_mob": unresolved_mob,
        "unresolved_item": unresolved_item,
        "deferred": [
            "script_rewards_requirements",
            "quest_type_classification",
            "map_from_location",
            "ozro_bounty_repeatables",
        ],
        "wrote": [str(q_path), str(t_path), str(d_path), str(l_path)],
    }
    summary_path = reports_dir / "quests_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    summary["summary_path"] = str(summary_path)
    return summary
