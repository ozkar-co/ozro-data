"""Boxes / item groups — item_group_db.yml + getgroupitem links (Etapa 3)."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

import yaml

from discovery.scan import _load_extractor_config
from extractors.client_scope import load_client_item_ids

_GETGROUP_RE = re.compile(
    r"\bget(?:rand)?groupitem\s*\(\s*(?P<name>IG_[A-Za-z0-9_]+)\s*\)",
    re.IGNORECASE,
)


def _provenance_id(domain: str, record_id: str, source_path: str) -> str:
    raw = f"{domain}|{record_id}|{source_path}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def _group_key(name: str) -> str:
    n = name.strip()
    if n.upper().startswith("IG_"):
        n = n[3:]
    return n.upper()


def extract_boxes(project_root: Path | None = None) -> dict[str, Any]:
    root = project_root or Path(__file__).resolve().parents[1]
    cfg = _load_extractor_config(root)
    rathena = Path(cfg["paths"]["rathena"])
    reports_dir = root / cfg["output"]["reports_dir"]
    reports_dir.mkdir(parents=True, exist_ok=True)
    client_ids = load_client_item_ids(reports_dir)

    other = list(cfg.get("db", {}).get("other") or [])
    files = [p for p in other if "item_group" in p] or [
        "db/re/item_group_db.yml",
        "db/import/item_group_db.yml",
    ]

    item_by_aegis: dict[str, int] = {}
    container_ids: set[int] = set()
    items_path = reports_dir / "items.jsonl"
    if items_path.is_file():
        for line in items_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            it = json.loads(line)
            if it.get("aegis_name"):
                item_by_aegis[str(it["aegis_name"]).upper()] = int(it["item_id"])
            flags = it.get("flags") if isinstance(it.get("flags"), dict) else {}
            if flags.get("Container"):
                container_ids.add(int(it["item_id"]))

    # merge groups
    by_key: dict[str, tuple[dict[str, Any], str]] = {}
    for rel in files:
        path = rathena / rel
        if not path.is_file():
            continue
        doc = yaml.safe_load(path.read_text(encoding="utf-8", errors="replace"))
        for row in (doc or {}).get("Body") or []:
            gname = row.get("Group")
            if not gname:
                continue
            key = _group_key(str(gname))
            if key not in by_key:
                by_key[key] = (dict(row), rel)
            else:
                merged = dict(by_key[key][0])
                merged.update(row)
                by_key[key] = (merged, rel)

    boxes: list[dict[str, Any]] = []
    rewards: list[dict[str, Any]] = []
    unresolved_item = 0
    skipped_no_client = 0
    by_algo: dict[str, int] = {}

    # First pass: build reward item ids per group for nesting detection later
    group_reward_items: dict[str, set[int]] = {}

    for key in sorted(by_key):
        row, src = by_key[key]
        gname = str(row.get("Group"))
        box_id = hashlib.sha1(f"box|{key}".encode()).hexdigest()
        subgroups = row.get("SubGroups") or []
        reward_count = 0
        algos: list[str] = []
        reward_ids: set[int] = set()

        if isinstance(subgroups, list):
            for sg in subgroups:
                if not isinstance(sg, dict):
                    continue
                algo = sg.get("Algorithm") or "SharedPool"
                algos.append(str(algo))
                by_algo[str(algo)] = by_algo.get(str(algo), 0) + 1
                sg_num = sg.get("SubGroup")
                for entry in sg.get("List") or []:
                    if not isinstance(entry, dict):
                        continue
                    item_aegis = entry.get("Item")
                    if not item_aegis:
                        continue
                    item_id = item_by_aegis.get(str(item_aegis).upper())
                    if item_id is None:
                        unresolved_item += 1
                        skipped_no_client += 1
                        continue
                    if item_id not in client_ids:
                        skipped_no_client += 1
                        continue
                    reward_ids.add(item_id)
                    reward_count += 1
                    rid = hashlib.sha1(
                        f"boxrew|{key}|{sg_num}|{entry.get('Index')}|{item_aegis}".encode()
                    ).hexdigest()
                    rewards.append(
                        {
                            "reward_id": rid,
                            "box_id": box_id,
                            "group_name": gname,
                            "subgroup": sg_num,
                            "algorithm": algo,
                            "index": entry.get("Index"),
                            "item_id": item_id,
                            "item_aegis_name": str(item_aegis),
                            "rate": entry.get("Rate"),
                            "amount": entry.get("Amount", 1),
                            "refine_min": entry.get("RefineMinimum"),
                            "refine_max": entry.get("RefineMaximum"),
                            "announced": entry.get("Announced"),
                            "duration": entry.get("Duration"),
                            "random_option_group": entry.get("RandomOptionGroup"),
                            "source_file": src,
                        }
                    )

        group_reward_items[key] = reward_ids
        boxes.append(
            {
                "box_id": box_id,
                "group_name": gname,
                "group_key": key,
                "subgroup_count": len(subgroups) if isinstance(subgroups, list) else 0,
                "reward_count": reward_count,
                "algorithms": sorted(set(algos)),
                "source_file": src,
                "provenance_id": _provenance_id("boxes", box_id, src),
            }
        )

    # Nesting: reward item is Container OR opens another group (via later links)
    # Item → group links from item_scripts
    links: list[dict[str, Any]] = []
    opener_items: dict[str, set[int]] = {}  # group_key → item_ids that open it
    scripts_path = reports_dir / "item_scripts.jsonl"
    missing_group = 0
    if scripts_path.is_file():
        seen: set[tuple[int, str]] = set()
        for line in scripts_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            s = json.loads(line)
            body = s.get("script_body") or ""
            if "getgroupitem" not in body.lower() and "getrandgroupitem" not in body.lower():
                continue
            item_id = int(s["item_id"])
            if item_id not in client_ids:
                skipped_no_client += 1
                continue
            for m in _GETGROUP_RE.finditer(body):
                raw_name = m.group("name")
                gkey = _group_key(raw_name)
                if gkey not in by_key:
                    missing_group += 1
                    continue
                pair = (item_id, gkey)
                if pair in seen:
                    continue
                seen.add(pair)
                opener_items.setdefault(gkey, set()).add(item_id)
                box_id = hashlib.sha1(f"box|{gkey}".encode()).hexdigest()
                lid = hashlib.sha1(f"boxlink|{item_id}|{gkey}".encode()).hexdigest()
                links.append(
                    {
                        "link_id": lid,
                        "item_id": item_id,
                        "box_id": box_id,
                        "group_name": by_key[gkey][0].get("Group"),
                        "group_key": gkey,
                        "is_container_flag": item_id in container_ids,
                        "script_kind": s.get("script_kind"),
                        "source_file": s.get("source_file"),
                        "provenance_id": _provenance_id(
                            "box_links", lid, f"item:{item_id}"
                        ),
                    }
                )

    # Mark nested boxes: any reward item_id appears as opener of some group
    opener_all = {i for s in opener_items.values() for i in s}
    nested_box_ids: set[str] = set()
    for b in boxes:
        gkey = b["group_key"]
        for iid in group_reward_items.get(gkey, set()):
            if iid in opener_all or iid in container_ids:
                nested_box_ids.add(b["box_id"])
                break
    for b in boxes:
        b["contains_nested_box"] = b["box_id"] in nested_box_ids
        b["opener_item_count"] = len(opener_items.get(b["group_key"], set()))

    for r in rewards:
        iid = r.get("item_id")
        r["reward_is_container"] = bool(iid is not None and iid in container_ids)
        r["reward_opens_group"] = bool(iid is not None and iid in opener_all)

    b_path = reports_dir / "boxes.jsonl"
    with b_path.open("w", encoding="utf-8") as f:
        for row in boxes:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    r_path = reports_dir / "box_rewards.jsonl"
    with r_path.open("w", encoding="utf-8") as f:
        for row in rewards:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    l_path = reports_dir / "box_item_links.jsonl"
    with l_path.open("w", encoding="utf-8") as f:
        for row in links:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    summary = {
        "domain": "boxes",
        "box_count": len(boxes),
        "reward_rows": len(rewards),
        "item_links": len(links),
        "unique_opener_items": len({L["item_id"] for L in links}),
        "boxes_with_nested": len(nested_box_ids),
        "by_algorithm": by_algo,
        "unresolved_reward_item": unresolved_item,
        "skipped_no_client": skipped_no_client,
        "getgroupitem_missing_group": missing_group,
        "deferred": [
            "sharedpool_probability_normalize",
            "npc_quest_instance_rewards",
            "getrandgroupitem_full_args",
        ],
        "wrote": [str(b_path), str(r_path), str(l_path)],
    }
    summary_path = reports_dir / "boxes_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    summary["summary_path"] = str(summary_path)
    return summary
