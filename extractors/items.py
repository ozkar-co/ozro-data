"""Items extractor — item_db YAML (+ import) + client asset presence + costume norm."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import yaml

from discovery.scan import _load_extractor_config

_LOCATION_FAMILY = {
    "Head_Top": "head_top",
    "Head_Mid": "head_mid",
    "Head_Low": "head_low",
    "Armor": "armor",
    "Garment": "garment",
    "Shoes": "shoes",
    "Right_Hand": "right_hand",
    "Left_Hand": "left_hand",
    "Both_Hand": "both_hand",
    "Right_Accessory": "right_accessory",
    "Left_Accessory": "left_accessory",
    "Both_Accessory": "both_accessory",
    "Costume_Head_Top": "head_top",
    "Costume_Head_Mid": "head_mid",
    "Costume_Head_Low": "head_low",
    "Costume_Garment": "garment",
    "Shadow_Armor": "shadow_armor",
    "Shadow_Weapon": "shadow_weapon",
    "Shadow_Shield": "shadow_shield",
    "Shadow_Shoes": "shadow_shoes",
    "Shadow_Right_Accessory": "shadow_right_accessory",
    "Shadow_Left_Accessory": "shadow_left_accessory",
}

# Keys are lowercase; YAML Type casing is inconsistent (Petegg vs PetEgg).
_TYPE_CATEGORY = {
    "weapon": "Weapon",
    "armor": "Armor",
    "card": "Card",
    "etc": "Miscellaneous",
    "healing": "Healing",
    "usable": "Usable",
    "delayconsume": "Usable",
    "cash": "Cash",
    "petegg": "Pet Egg",
    "petarmor": "Pet Armor",
    "ammo": "Ammo",
    "shadowgear": "Shadow Gear",
}


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


def _load_item_db(
    rathena: Path, files: list[str]
) -> tuple[dict[int, dict[str, Any]], set[int]]:
    by_id: dict[int, dict[str, Any]] = {}
    import_ids: set[int] = set()
    for rel in files:
        path = rathena / rel
        if not path.is_file():
            continue
        is_import = rel.replace("\\", "/").startswith("db/import/")
        doc = yaml.safe_load(path.read_text(encoding="utf-8", errors="replace"))
        for row in (doc or {}).get("Body") or []:
            iid = row.get("Id")
            if iid is None:
                continue
            iid = int(iid)
            if is_import:
                import_ids.add(iid)
            if iid not in by_id:
                by_id[iid] = dict(row)
            else:
                merged = dict(by_id[iid])
                merged.update(row)
                by_id[iid] = merged
    return by_id, import_ids


def _true_keys(mapping: Any) -> list[str]:
    if not isinstance(mapping, dict):
        return []
    return [str(k) for k, v in mapping.items() if v]


def classify_item(row: dict[str, Any]) -> dict[str, Any]:
    """Normalized category / costume / slot family from Type + Locations."""
    item_type = row.get("Type")
    type_key = str(item_type).lower() if item_type is not None else ""
    locations = _true_keys(row.get("Locations"))
    costume_locs = [k for k in locations if k.startswith("Costume_")]
    shadow_locs = [k for k in locations if k.startswith("Shadow_")]
    is_costume = bool(costume_locs)

    if is_costume:
        category = "Costume"
        primary = costume_locs[0]
    elif type_key == "shadowgear" or shadow_locs:
        category = "Shadow Gear"
        primary = shadow_locs[0] if shadow_locs else None
    elif type_key == "armor" and locations:
        # Prefer distinctive armor slots over generic.
        for key, cat in (
            ("Garment", "Garment"),
            ("Shoes", "Shoes"),
            ("Right_Accessory", "Accessory"),
            ("Left_Accessory", "Accessory"),
            ("Both_Accessory", "Accessory"),
            ("Head_Top", "Armor"),
            ("Head_Mid", "Armor"),
            ("Head_Low", "Armor"),
            ("Armor", "Armor"),
        ):
            if key in locations:
                category = cat
                primary = key
                break
        else:
            category = "Armor"
            primary = locations[0]
    else:
        category = _TYPE_CATEGORY.get(type_key, "Miscellaneous")
        primary = locations[0] if locations else None

    family = _LOCATION_FAMILY.get(primary) if primary else None
    subcategory = row.get("SubType") or primary

    return {
        "item_category": category,
        "item_subcategory": str(subcategory) if subcategory else None,
        "is_costume": is_costume,
        "equip_location": primary,
        "equip_location_family": family,
        "locations_list": locations,
    }


def extract_items(project_root: Path | None = None) -> dict[str, Any]:
    root = project_root or Path(__file__).resolve().parents[1]
    cfg = _load_extractor_config(root)
    rathena = Path(cfg["paths"]["rathena"])
    reports_dir = root / cfg["output"]["reports_dir"]
    reports_dir.mkdir(parents=True, exist_ok=True)

    item_files = list(cfg["db"]["item_files"])
    by_id, import_ids = _load_item_db(rathena, item_files)
    client = _load_jsonl_index(reports_dir / "client_item_info.jsonl", "item_id")
    gaps = _load_jsonl_index(reports_dir / "client_item_server_gaps.jsonl", "item_id")

    records: list[dict[str, Any]] = []
    for iid in sorted(by_id):
        row = by_id[iid]
        classed = classify_item(row)
        info = client.get(iid)
        gap = gaps.get(iid)

        flags = row.get("Flags") if isinstance(row.get("Flags"), dict) else row.get("Flags")
        jobs = row.get("Jobs") if isinstance(row.get("Jobs"), dict) else row.get("Jobs")
        locations = row.get("Locations")
        if isinstance(locations, dict):
            locations = {k: bool(v) for k, v in locations.items()}

        has_script = any(row.get(k) for k in ("Script", "EquipScript", "UnEquipScript"))
        sprite_name = None
        if info:
            sprite_name = info.get("identified_resource_name")
        elif gap:
            sprite_name = gap.get("identified_resource_name")

        source_path = item_files[0]
        record = {
            "item_id": iid,
            "aegis_name": row.get("AegisName"),
            "name": row.get("Name"),
            "display_name": row.get("Name"),
            "type": row.get("Type"),
            "subtype": row.get("SubType"),
            "item_category": classed["item_category"],
            "item_subcategory": classed["item_subcategory"],
            "is_costume": classed["is_costume"],
            "equip_location": classed["equip_location"],
            "equip_location_family": classed["equip_location_family"],
            "buy_base": row.get("Buy"),
            "sell_base": row.get("Sell"),
            "buy_effective": None,
            "sell_effective": None,
            "weight": row.get("Weight"),
            "attack": row.get("Attack"),
            "magic_attack": row.get("MagicAttack"),
            "defense": row.get("Defense"),
            "range_atk": row.get("Range"),
            "slots": row.get("Slots"),
            "weapon_level": row.get("WeaponLevel"),
            "armor_level": row.get("ArmorLevel"),
            "equip_level_min": row.get("EquipLevelMin"),
            "equip_level_max": row.get("EquipLevelMax"),
            "refineable": row.get("Refineable"),
            "view_id": row.get("View"),
            "flags": flags,
            "jobs": jobs,
            "locations": locations,
            "sprite_name": sprite_name,
            "has_sprite": bool(info.get("has_sprite")) if info else False,
            "has_item_icon": bool(info.get("has_item_icon")) if info else False,
            "assets_complete": bool(info.get("assets_complete")) if info else False,
            "has_script": has_script,
            "client_gap_reason": gap.get("reason") if gap else None,
            "classification_layer": "inferred",
            "provenance_id": _provenance_id("items", str(iid), source_path),
            "source": {
                "item_files": item_files,
                "client_item_info": "reports/client_item_info.jsonl" if info else None,
                "import_override": iid in import_ids,
            },
        }
        records.append(record)

    out_path = reports_dir / "items.jsonl"
    with out_path.open("w", encoding="utf-8") as f:
        for row in records:
            f.write(json.dumps(row, ensure_ascii=False, sort_keys=False) + "\n")

    by_cat: dict[str, int] = {}
    by_type: dict[str, int] = {}
    for r in records:
        by_cat[r["item_category"] or "?"] = by_cat.get(r["item_category"] or "?", 0) + 1
        by_type[str(r["type"] or "?")] = by_type.get(str(r["type"] or "?"), 0) + 1

    summary = {
        "domain": "items",
        "item_count": len(records),
        "costume_count": sum(1 for r in records if r["is_costume"]),
        "assets_complete": sum(1 for r in records if r["assets_complete"]),
        "with_script": sum(1 for r in records if r["has_script"]),
        "import_override_count": len(import_ids),
        "client_gap_count": sum(1 for r in records if r["client_gap_reason"]),
        "by_category": by_cat,
        "by_type": by_type,
        "wrote": str(out_path),
    }
    summary_path = reports_dir / "items_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    summary["summary_path"] = str(summary_path)
    return summary
