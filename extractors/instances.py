"""Instances — instance_db.yml + maps + NPC links via instance_create (Etapa 3)."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

import yaml

from discovery.scan import _load_extractor_config

_CREATE_LIT_RE = re.compile(
    r"""\binstance_create\s*(?:\(|\s+)\s*(?P<q>["'])(?P<name>[^"']+)(?P=q)""",
    re.IGNORECASE,
)
_CREATE_ANY_RE = re.compile(r"\binstance_create\b", re.IGNORECASE)


def _provenance_id(domain: str, record_id: str, source_path: str) -> str:
    raw = f"{domain}|{record_id}|{source_path}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def extract_instances(project_root: Path | None = None) -> dict[str, Any]:
    root = project_root or Path(__file__).resolve().parents[1]
    cfg = _load_extractor_config(root)
    rathena = Path(cfg["paths"]["rathena"])
    reports_dir = root / cfg["output"]["reports_dir"]
    reports_dir.mkdir(parents=True, exist_ok=True)

    other = list(cfg.get("db", {}).get("other") or [])
    files = [p for p in other if "instance_db" in p] or [
        "db/re/instance_db.yml",
        "db/import/instance_db.yml",
    ]

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

    known_maps: set[str] = set()
    maps_path = reports_dir / "maps.jsonl"
    if maps_path.is_file():
        for line in maps_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                known_maps.add(json.loads(line)["map_id"])

    spawn_by_map: dict[str, int] = {}
    spawns_path = reports_dir / "spawns.jsonl"
    if spawns_path.is_file():
        for line in spawns_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            s = json.loads(line)
            mid = s.get("map_id")
            if mid:
                spawn_by_map[mid] = spawn_by_map.get(mid, 0) + 1

    instances: list[dict[str, Any]] = []
    instance_maps: list[dict[str, Any]] = []
    name_to_id: dict[str, int] = {}

    for iid in sorted(by_id):
        row, src = by_id[iid]
        name = row.get("Name")
        if name:
            name_to_id[str(name)] = iid
        enter = row.get("Enter") if isinstance(row.get("Enter"), dict) else {}
        enter_map = enter.get("Map")
        time_limit = row.get("TimeLimit")
        add = row.get("AdditionalMaps") if isinstance(row.get("AdditionalMaps"), dict) else {}

        maps: list[str] = []
        if enter_map:
            maps.append(str(enter_map))
            instance_maps.append(
                {
                    "instance_id": iid,
                    "map_id": str(enter_map),
                    "role": "enter",
                    "in_maps_catalog": str(enter_map) in known_maps,
                    "spawn_rows": spawn_by_map.get(str(enter_map), 0),
                }
            )
        for mname, active in add.items():
            if active is False:
                continue
            maps.append(str(mname))
            instance_maps.append(
                {
                    "instance_id": iid,
                    "map_id": str(mname),
                    "role": "additional",
                    "in_maps_catalog": str(mname) in known_maps,
                    "spawn_rows": spawn_by_map.get(str(mname), 0),
                }
            )

        instances.append(
            {
                "instance_id": iid,
                "name": name,
                "time_limit_seconds": int(time_limit) if time_limit is not None else None,
                "enter_map_id": str(enter_map) if enter_map else None,
                "enter_x": enter.get("X"),
                "enter_y": enter.get("Y"),
                "map_count": len(maps),
                "maps": maps,
                "source_file": src,
                "provenance_id": _provenance_id("instances", str(iid), src),
            }
        )

    # NPC links: scan scripts for instance_create("Name") and attach NPCs from that file
    npcs_by_path: dict[str, list[dict[str, Any]]] = {}
    npcs_path = reports_dir / "npcs.jsonl"
    if npcs_path.is_file():
        for line in npcs_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            n = json.loads(line)
            npcs_by_path.setdefault(n.get("script_path") or "", []).append(n)

    links: list[dict[str, Any]] = []
    create_literal = 0
    create_dynamic = 0
    unmatched_name = 0
    seen_link: set[tuple[str, int]] = set()

    # Prefer files under instances/ from discovery scripts list
    files_path = reports_dir / "discovery_files.yml"
    scripts: list[str] = []
    if files_path.is_file():
        disc = yaml.safe_load(files_path.read_text(encoding="utf-8"))
        scripts = list(disc.get("scripts") or [])

    for rel in scripts:
        if "instances" not in rel.replace("\\", "/").lower() and "instance" not in rel.lower():
            # still scan if file contains instance_create — but limit to speed: only instances paths + ozro
            if "/custom/ozro" not in rel.replace("\\", "/"):
                continue
        path = rathena / rel
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        if "instance_create" not in text.lower():
            continue
        names_in_file: set[str] = set()
        for line in text.splitlines():
            line = line.split("//", 1)[0]
            m = _CREATE_LIT_RE.search(line)
            if m:
                create_literal += 1
                names_in_file.add(m.group("name"))
            elif _CREATE_ANY_RE.search(line):
                create_dynamic += 1

        for iname in names_in_file:
            iid = name_to_id.get(iname)
            if iid is None:
                unmatched_name += 1
                continue
            for n in npcs_by_path.get(rel, []):
                key = (n["npc_id"], iid)
                if key in seen_link:
                    continue
                seen_link.add(key)
                role = "entrance"
                if "Instance" not in (n.get("functions") or []):
                    role = "script_related"
                lid = hashlib.sha1(f"inst_npc|{n['npc_id']}|{iid}".encode()).hexdigest()
                links.append(
                    {
                        "link_id": lid,
                        "instance_id": iid,
                        "instance_name": iname,
                        "npc_id": n["npc_id"],
                        "role": role,
                        "script_path": rel,
                        "match_kind": "instance_create_literal",
                        "provenance_id": _provenance_id(
                            "instance_npcs", lid, rel
                        ),
                    }
                )

    # Count Instance-function NPCs in instances/ not bound by literal create (no row spam).
    linked_npcs = {L["npc_id"] for L in links}
    soft = 0
    for rel, ns in npcs_by_path.items():
        if "/instances/" not in rel.replace("\\", "/"):
            continue
        for n in ns:
            if "Instance" not in (n.get("functions") or []):
                continue
            if n["npc_id"] in linked_npcs:
                continue
            soft += 1

    i_path = reports_dir / "instances.jsonl"
    with i_path.open("w", encoding="utf-8") as f:
        for row in instances:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    m_path = reports_dir / "instance_maps.jsonl"
    with m_path.open("w", encoding="utf-8") as f:
        for row in instance_maps:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    l_path = reports_dir / "instance_npc_links.jsonl"
    with l_path.open("w", encoding="utf-8") as f:
        for row in links:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    summary = {
        "domain": "instances",
        "instance_count": len(instances),
        "instance_map_rows": len(instance_maps),
        "maps_missing_catalog": sum(
            1 for r in instance_maps if not r["in_maps_catalog"]
        ),
        "npc_links": len(links),
        "npc_links_bound": sum(1 for L in links if L.get("instance_id") is not None),
        "npc_links_unbound": soft,
        "instance_create_literal": create_literal,
        "instance_create_dynamic": create_dynamic,
        "unmatched_create_name": unmatched_name,
        "out_of_scope": [
            "dynamic_instance_create_vars",  # not identifiable statically
            "requirements_rewards_scripts",  # player discovers flow
            "idle_timeout_fields",
        ],
        "note": (
            "Creator NPC = literal instance_create Name binds. "
            "Dynamic .@var creates counted but not bound."
        ),
        "wrote": [str(i_path), str(m_path), str(l_path)],
    }
    summary_path = reports_dir / "instances_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    summary["summary_path"] = str(summary_path)
    return summary
