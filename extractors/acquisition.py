"""Acquisition Sources — union of existing catalog extracts (§14)."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from discovery.scan import _load_extractor_config
from extractors.client_scope import load_client_item_ids


def _provenance_id(domain: str, record_id: str, source_path: str) -> str:
    raw = f"{domain}|{record_id}|{source_path}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def _eid(*parts: Any) -> str:
    raw = "|".join("" if p is None else str(p) for p in parts)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def _iter_jsonl(path: Path):
    if not path.is_file():
        return
    with path.open(encoding="utf-8") as f:
        for line in f:
            if line.strip():
                yield json.loads(line)


def extract_acquisition(project_root: Path | None = None) -> dict[str, Any]:
    root = project_root or Path(__file__).resolve().parents[1]
    cfg = _load_extractor_config(root)
    reports_dir = root / cfg["output"]["reports_dir"]
    reports_dir.mkdir(parents=True, exist_ok=True)
    client_ids = load_client_item_ids(reports_dir)

    outputs: list[dict[str, Any]] = []
    by_type: dict[str, int] = {}
    items_touched: set[int] = set()
    missing_inputs: list[str] = []

    def _add(
        *,
        source_type: str,
        source_ref: str,
        item_id: int | None,
        quantity_min: int = 1,
        quantity_max: int = 1,
        probability: Any = None,
        probability_unit: str | None = None,
        npc_id: Any = None,
        map_id: Any = None,
        mob_id: Any = None,
        extra: dict[str, Any] | None = None,
        provenance_src: str = "union",
    ) -> None:
        if item_id is None:
            return
        iid = int(item_id)
        if iid not in client_ids:
            return
        oid = _eid("acq", source_type, source_ref, iid)
        row = {
            "acquisition_output_id": oid,
            "source_type": source_type,
            "source_ref": source_ref,
            "item_id": iid,
            "quantity_min": quantity_min,
            "quantity_max": quantity_max,
            "probability": probability,
            "probability_unit": probability_unit,
            "npc_id": npc_id,
            "map_id": map_id,
            "mob_id": mob_id,
            "provenance_id": _provenance_id("acquisition_outputs", oid, provenance_src),
        }
        if extra:
            row.update(extra)
        outputs.append(row)
        by_type[source_type] = by_type.get(source_type, 0) + 1
        items_touched.add(iid)

    # drops
    drops_path = reports_dir / "drops.jsonl"
    if drops_path.is_file():
        for d in _iter_jsonl(drops_path):
            cat = d.get("drop_category")
            st = "map_drop" if cat == "map_specific" or d.get("is_map_bonus") else "mob_drop"
            _add(
                source_type=st,
                source_ref=str(d.get("drop_id")),
                item_id=d.get("item_id"),
                probability=d.get("chance_effective"),
                probability_unit=d.get("rate_unit"),
                mob_id=d.get("mob_id"),
                map_id=d.get("map_id"),
                provenance_src="drops.jsonl",
            )
    else:
        missing_inputs.append("drops.jsonl")

    # shops
    shop_items = reports_dir / "npc_shop_items.jsonl"
    if shop_items.is_file():
        for s in _iter_jsonl(shop_items):
            _add(
                source_type="npc_shop",
                source_ref=f"{s.get('shop_id')}:{s.get('item_id')}",
                item_id=s.get("item_id"),
                npc_id=s.get("npc_id"),
                extra={"price": s.get("price"), "stock": s.get("stock")},
                provenance_src="npc_shop_items.jsonl",
            )
    else:
        missing_inputs.append("npc_shop_items.jsonl")

    # barters
    barter_items = reports_dir / "barter_items.jsonl"
    if barter_items.is_file():
        for b in _iter_jsonl(barter_items):
            _add(
                source_type="npc_barter",
                source_ref=str(b.get("barter_item_id")),
                item_id=b.get("item_id"),
                extra={
                    "barter_name": b.get("barter_name"),
                    "zeny": b.get("zeny"),
                    "refine": b.get("refine"),
                },
                provenance_src="barter_items.jsonl",
            )
    else:
        missing_inputs.append("barter_items.jsonl")

    # boxes (rewards as obtainable content)
    box_rewards = reports_dir / "box_rewards.jsonl"
    if box_rewards.is_file():
        for r in _iter_jsonl(box_rewards):
            amt = int(r.get("amount") or 1)
            _add(
                source_type="box_reward",
                source_ref=str(r.get("reward_id")),
                item_id=r.get("item_id"),
                quantity_min=amt,
                quantity_max=amt,
                probability=r.get("chance_effective", r.get("rate")),
                probability_unit=r.get("chance_unit") or "raw_group_rate",
                extra={
                    "box_id": r.get("box_id"),
                    "group_name": r.get("group_name"),
                    "algorithm": r.get("algorithm"),
                    "chance_status": r.get("chance_status"),
                },
                provenance_src="box_rewards.jsonl",
            )
    else:
        missing_inputs.append("box_rewards.jsonl")

    # recipes (craft result)
    recipes = reports_dir / "recipes.jsonl"
    if recipes.is_file():
        for r in _iter_jsonl(recipes):
            amt = int(r.get("result_amount") or 1)
            _add(
                source_type="crafting",
                source_ref=str(r.get("recipe_id")),
                item_id=r.get("result_item_id"),
                quantity_min=amt,
                quantity_max=amt,
                probability=r.get("success_rate"),
                probability_unit="recipe_success_raw",
                provenance_src="recipes.jsonl",
            )
    else:
        missing_inputs.append("recipes.jsonl")

    # quest drops (quest_db Drops — not full script rewards)
    quest_drops = reports_dir / "quest_drops.jsonl"
    if quest_drops.is_file():
        for q in _iter_jsonl(quest_drops):
            _add(
                source_type="quest_drop",
                source_ref=f"{q.get('quest_id')}:{q.get('drop_index')}",
                item_id=q.get("item_id"),
                probability=q.get("rate"),
                probability_unit=q.get("rate_unit"),
                mob_id=q.get("mob_id"),
                provenance_src="quest_drops.jsonl",
            )
    else:
        missing_inputs.append("quest_drops.jsonl")

    # NPC enchant stones as enchanting "sources" of applying those items (optional catalog)
    npc_enchant_items = reports_dir / "npc_enchant_items.jsonl"
    if npc_enchant_items.is_file():
        for e in _iter_jsonl(npc_enchant_items):
            if e.get("role") != "stone":
                continue
            _add(
                source_type="enchanting",
                source_ref=str(e.get("npc_enchant_item_id")),
                item_id=e.get("item_id"),
                extra={"script_path": e.get("script_path"), "role": "stone"},
                provenance_src="npc_enchant_items.jsonl",
            )

    # Socket item→item (Seiyablem/Leablem): result item is obtainable via transform
    transforms = reports_dir / "npc_item_transforms.jsonl"
    if transforms.is_file():
        for t in _iter_jsonl(transforms):
            _add(
                source_type="socketing",
                source_ref=str(t.get("npc_item_transform_id")),
                item_id=t.get("to_item_id"),
                extra={
                    "from_item_id": t.get("from_item_id"),
                    "script_path": t.get("script_path"),
                    "func_name": t.get("func_name"),
                },
                provenance_src="npc_item_transforms.jsonl",
            )
    else:
        missing_inputs.append("npc_item_transforms.jsonl")

    # Literal getitem/getitembound from NPC scripts
    script_rewards = reports_dir / "npc_script_rewards.jsonl"
    if script_rewards.is_file():
        for s in _iter_jsonl(script_rewards):
            qty = int(s.get("quantity") or 1)
            _add(
                source_type="npc_reward",
                source_ref=str(s.get("npc_script_reward_id")),
                item_id=s.get("item_id"),
                quantity_min=qty,
                quantity_max=qty,
                npc_id=s.get("npc_id"),
                map_id=s.get("map_id"),
                extra={
                    "script_path": s.get("script_path"),
                    "command": s.get("command"),
                },
                provenance_src="npc_script_rewards.jsonl",
            )
    else:
        missing_inputs.append("npc_script_rewards.jsonl")

    out_path = reports_dir / "acquisition_outputs.jsonl"
    with out_path.open("w", encoding="utf-8") as f:
        for row in outputs:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    # Coverage vs client items present in items.jsonl
    all_items: set[int] = set()
    items_path = reports_dir / "items.jsonl"
    if items_path.is_file():
        for it in _iter_jsonl(items_path):
            iid = it.get("item_id")
            if iid is not None and int(iid) in client_ids:
                all_items.add(int(iid))
    with_source = items_touched & all_items
    without = all_items - with_source

    # Sample without-source ids for triage (cap)
    without_sample = sorted(without)[:50]

    summary = {
        "domain": "acquisition",
        "output_rows": len(outputs),
        "by_source_type": by_type,
        "unique_items_with_source": len(with_source),
        "client_items_total": len(all_items),
        "client_items_without_source": len(without),
        "without_source_sample": without_sample,
        "missing_inputs": missing_inputs,
        "coverage_note": (
            "without_source = unused client pool (custom quests/shops/events); "
            "not content gaps"
        ),
        "wrote": [str(out_path)],
    }
    summary_path = reports_dir / "acquisition_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    summary["summary_path"] = str(summary_path)
    return summary
