"""Random Options — item_randomopt_db / group (+ import) + drop links (§21bis)."""

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


def _eid(*parts: Any) -> str:
    raw = "|".join("" if p is None else str(p) for p in parts)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def _load_yaml_body(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    doc = yaml.safe_load(path.read_text(encoding="utf-8", errors="replace")) or {}
    body = doc.get("Body") or []
    return [r for r in body if isinstance(r, dict)]


def _merge_by_id(
    files: list[tuple[str, list[dict[str, Any]]]], id_key: str = "Id"
) -> list[tuple[dict[str, Any], str]]:
    """Later files overwrite same Id."""
    by: dict[Any, tuple[dict[str, Any], str]] = {}
    for rel, rows in files:
        for row in rows:
            rid = row.get(id_key)
            if rid is None:
                continue
            by[rid] = (row, rel)
    return list(by.values())


def extract_random_options(project_root: Path | None = None) -> dict[str, Any]:
    root = project_root or Path(__file__).resolve().parents[1]
    cfg = _load_extractor_config(root)
    rathena = Path(cfg["paths"]["rathena"])
    reports_dir = root / cfg["output"]["reports_dir"]
    reports_dir.mkdir(parents=True, exist_ok=True)

    opt_files = [
        ("db/re/item_randomopt_db.yml", _load_yaml_body(rathena / "db/re/item_randomopt_db.yml")),
        (
            "db/import/item_randomopt_db.yml",
            _load_yaml_body(rathena / "db/import/item_randomopt_db.yml"),
        ),
    ]
    grp_files = [
        (
            "db/re/item_randomopt_group.yml",
            _load_yaml_body(rathena / "db/re/item_randomopt_group.yml"),
        ),
        (
            "db/import/item_randomopt_group.yml",
            _load_yaml_body(rathena / "db/import/item_randomopt_group.yml"),
        ),
    ]

    options_out: list[dict[str, Any]] = []
    option_by_name: dict[str, int] = {}
    for row, src in _merge_by_id(opt_files):
        oid = int(row["Id"])
        name = str(row.get("Option") or "")
        script = row.get("Script")
        if isinstance(script, str):
            script_body = script.strip()
        else:
            script_body = ""
        rid = _eid("ropt", oid)
        options_out.append(
            {
                "random_option_id": rid,
                "option_db_id": oid,
                "option_name": name,
                "script": script_body,
                "source_file": src,
                "provenance_id": _provenance_id("random_options", rid, src),
            }
        )
        if name:
            option_by_name[name.upper()] = oid

    groups_out: list[dict[str, Any]] = []
    group_slots_out: list[dict[str, Any]] = []
    group_entries_out: list[dict[str, Any]] = []
    unresolved_option = 0

    for row, src in _merge_by_id(grp_files):
        gid = int(row["Id"])
        gname = str(row.get("Group") or "")
        max_random = int(row.get("MaxRandom") or 0)
        group_rec_id = _eid("roptgrp", gid)
        groups_out.append(
            {
                "random_option_group_id": group_rec_id,
                "group_db_id": gid,
                "group_name": gname,
                "max_random": max_random,
                "source_file": src,
                "provenance_id": _provenance_id(
                    "random_option_groups", group_rec_id, src
                ),
            }
        )

        for slot_row in row.get("Slots") or []:
            if not isinstance(slot_row, dict):
                continue
            slot_no = slot_row.get("Slot")
            for ei, opt in enumerate(slot_row.get("Options") or []):
                if not isinstance(opt, dict):
                    continue
                oname = str(opt.get("Option") or "")
                odb = option_by_name.get(oname.upper())
                if odb is None and oname:
                    unresolved_option += 1
                eid = _eid("roptslot", gid, slot_no, ei, oname)
                group_slots_out.append(
                    {
                        "group_slot_entry_id": eid,
                        "random_option_group_id": group_rec_id,
                        "group_db_id": gid,
                        "group_name": gname,
                        "slot": slot_no,
                        "index": ei,
                        "option_name": oname,
                        "option_db_id": odb,
                        "min_value": int(opt.get("MinValue") or 0),
                        "max_value": int(opt.get("MaxValue") or 0),
                        "param": int(opt.get("Param") or 0),
                        "chance": int(opt.get("Chance") or 0),
                        "chance_unit": "per_10000",
                        "source_file": src,
                        "provenance_id": _provenance_id(
                            "random_option_group_slots", eid, src
                        ),
                    }
                )

        for ei, opt in enumerate(row.get("Random") or []):
            if not isinstance(opt, dict):
                continue
            oname = str(opt.get("Option") or "")
            odb = option_by_name.get(oname.upper())
            if odb is None and oname:
                unresolved_option += 1
            eid = _eid("roptrand", gid, ei, oname)
            group_entries_out.append(
                {
                    "group_random_entry_id": eid,
                    "random_option_group_id": group_rec_id,
                    "group_db_id": gid,
                    "group_name": gname,
                    "index": ei,
                    "option_name": oname,
                    "option_db_id": odb,
                    "min_value": int(opt.get("MinValue") or 0),
                    "max_value": int(opt.get("MaxValue") or 0),
                    "param": int(opt.get("Param") or 0),
                    "chance": int(opt.get("Chance") or 0),
                    "chance_unit": "per_10000",
                    "source_file": src,
                    "provenance_id": _provenance_id(
                        "random_option_group_random", eid, src
                    ),
                }
            )

    # Drop links: drops.jsonl RandomOptionGroup → group_name
    group_by_name = {g["group_name"].upper(): g for g in groups_out if g["group_name"]}
    drop_links: list[dict[str, Any]] = []
    drops_path = reports_dir / "drops.jsonl"
    unknown_groups: set[str] = set()
    if drops_path.is_file():
        for line in drops_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            d = json.loads(line)
            gname = d.get("random_option_group")
            if not gname:
                continue
            g = group_by_name.get(str(gname).upper())
            if g is None:
                unknown_groups.add(str(gname))
                continue
            lid = _eid("roptdrop", d.get("drop_id"), gname)
            drop_links.append(
                {
                    "drop_random_option_link_id": lid,
                    "drop_id": d.get("drop_id"),
                    "mob_id": d.get("mob_id"),
                    "item_id": d.get("item_id"),
                    "drop_category": d.get("drop_category"),
                    "map_id": d.get("map_id"),
                    "group_name": g["group_name"],
                    "group_db_id": g["group_db_id"],
                    "random_option_group_id": g["random_option_group_id"],
                    "provenance_id": _provenance_id(
                        "drop_random_option_links", lid, "drops.jsonl"
                    ),
                }
            )

    writes = {
        "random_options": options_out,
        "random_option_groups": groups_out,
        "random_option_group_slots": group_slots_out,
        "random_option_group_random": group_entries_out,
        "drop_random_option_links": drop_links,
    }
    wrote: list[str] = []
    for name, rows in writes.items():
        path = reports_dir / f"{name}.jsonl"
        with path.open("w", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        wrote.append(str(path))

    summary = {
        "domain": "random_options",
        "option_count": len(options_out),
        "group_count": len(groups_out),
        "slot_entry_rows": len(group_slots_out),
        "random_entry_rows": len(group_entries_out),
        "drop_link_rows": len(drop_links),
        "unresolved_option_name": unresolved_option,
        "unknown_drop_groups": sorted(unknown_groups),
        "chance_unit": "per_10000",
        "wrote": wrote,
    }
    summary_path = reports_dir / "random_options_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    summary["summary_path"] = str(summary_path)
    return summary
