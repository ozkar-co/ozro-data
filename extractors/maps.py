"""Maps extractor — enabled server maps + client resource presence."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

import yaml

from discovery.scan import _load_extractor_config, resolve_maps

_CATEGORY_ORDER = (
    "Instance",
    "Guild",
    "Arena",
    "Dungeon",
    "Quest",
    "Transport",
    "Interior",
    "Field",
    "City",
    "Special",
)

_TOWN_MAPFLAG_FILES = (
    "npc/mapflag/town.txt",
    "npc/re/mapflag/town.txt",
)

# Urban hubs that lack mapflag town in this rAthena split but are city maps.
_CITY_HUBS = frozenset(
    {
        "morocc",
        "niflheim",
        "jawaii",
        "manuk",
        "moscovia",
        "nameless_n",
        "dicastes02",
    }
)

_INSTANCE_NAME_RE = re.compile(r"^\d+@")
_GUILD_RE = re.compile(
    r"(06guild|guild|_gld\b|gld_|gld2_|_cas\d|arug_|schg_|te_aldec|te_prt|"
    r"alde_gld|aru_gld|pay_gld|prt_gld|n_castle)",
    re.I,
)
_ARENA_RE = re.compile(r"(^force_|guild_vs|^ordeal_|pvp_|^gw_|^bl_|prt_are)", re.I)
_TRANSPORT_RE = re.compile(
    r"(airplane|airport|alb_ship|alb2trea|air_ship|_ship$)",
    re.I,
)
_INTERIOR_RE = re.compile(
    r"(^in_|_in\d*$|_in_|ba_|_room|ecl_hub|iz_ac|iz_int|grademk|itemmall|"
    r"turbo_room|sec_pri|^job|arena_room|quiz|p_track|poring_w|s_atelier|"
    r"new_zone|new_1-|valkyrie|himinn|_church$|_castle$|_tower$|_prison|"
    r"_lib$|auction_|ma_zif|ma_scene|monk_test|prt_monk|prt_cas|prt_pri|"
    r"mid_campin|alde_alche|alde_tt|lhz_cube|pub_cat|paramk|iz_ng|"
    r"moc_para|moc_castle|gef_tower|prt_lib)",
    re.I,
)
_FIELD_RE = re.compile(r"(_fild|fild\d|^mjolnir_|harboro|lasa_sea|moro_vol)", re.I)
_DUNGEON_RE = re.compile(
    r"(_dun|dun\d{2}|anthell|c_tower|abbey|sewb|thor_v|ra_san|ice_dun|kh_dun|"
    r"moc_pryd|gl_|treasure|beach_dun|abyss_|amicitia|mag_dun|hu_dun|ein_dun|"
    r"juperos|jupe_|lhz_dun|tha_t|ama_dun|ayo_dun|lou_dun|gon_dun|nif_dun|um_dun|"
    r"prt_maze|prt_sew|orcs?dun|xmas_dun|odin_|man_dun|dic_dun|mal_dun|dew_dun|"
    r"gef_dun|pay_dun|iz_dun|gefenia|glast_|bossnia|^cave$|clock_|tur_|"
    r"verus|rockmi|sp_cor|sp_rud|lasa_dun|e_tower|s_tower|_d\d+_i$|"
    r"ant_d|com_d|gef_d|ice_d|moro_cav|lhz_d_n|izlu2dun)",
    re.I,
)
_QUEST_RE = re.compile(r"(^que_|_que\d|_q$|^evt_|e_hugel|mosk_que|new_event)", re.I)
_SPECIAL_RE = re.compile(r"(^oz_|gon_test|ama_test|grademk|itemmall|nakhyang)", re.I)
_MAPFLAG_TOWN_RE = re.compile(r"^(\S+)\s+mapflag\s+town\b", re.I)


def _provenance_id(domain: str, record_id: str, source_path: str) -> str:
    raw = f"{domain}|{record_id}|{source_path}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def _load_jsonl_index(path: Path, key: str) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    if not path.is_file():
        return out
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            out[str(row[key])] = row
    return out


def _load_instance_maps(
    rathena: Path, rel_paths: list[str]
) -> tuple[set[str], dict[str, str]]:
    maps: set[str] = set()
    names: dict[str, str] = {}
    for rel in rel_paths:
        path = rathena / rel
        if not path.is_file():
            continue
        doc = yaml.safe_load(path.read_text(encoding="utf-8", errors="replace"))
        for row in (doc or {}).get("Body") or []:
            inst_name = row.get("Name")
            enter = (row.get("Enter") or {}).get("Map")
            if enter:
                maps.add(str(enter))
                if inst_name:
                    names[str(enter)] = str(inst_name)
            additional = row.get("AdditionalMaps") or {}
            if isinstance(additional, dict):
                for k in additional.keys():
                    maps.add(str(k))
                    if inst_name:
                        names.setdefault(str(k), str(inst_name))
    return maps, names


def _load_town_maps(rathena: Path, rel_paths: tuple[str, ...]) -> set[str]:
    towns: set[str] = set()
    for rel in rel_paths:
        path = rathena / rel
        if not path.is_file():
            continue
        for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
            line = raw.split("//", 1)[0].strip()
            if not line:
                continue
            m = _MAPFLAG_TOWN_RE.match(line)
            if m:
                towns.add(m.group(1))
    return towns


def classify_map(
    map_id: str,
    instance_maps: set[str],
    town_maps: set[str],
) -> dict[str, Any]:
    categories: list[str] = []
    flags = {
        "is_town": False,
        "is_dungeon": False,
        "is_instance": False,
        "is_quest_map": False,
        "is_guild_map": False,
        "is_interior": False,
    }

    if map_id in instance_maps or _INSTANCE_NAME_RE.match(map_id):
        categories.append("Instance")
        flags["is_instance"] = True
    if _GUILD_RE.search(map_id):
        categories.append("Guild")
        flags["is_guild_map"] = True
    if _ARENA_RE.search(map_id):
        categories.append("Arena")
    if _DUNGEON_RE.search(map_id):
        categories.append("Dungeon")
        flags["is_dungeon"] = True
    if _QUEST_RE.search(map_id):
        categories.append("Quest")
        flags["is_quest_map"] = True
    if _TRANSPORT_RE.search(map_id):
        categories.append("Transport")
    if _INTERIOR_RE.search(map_id):
        categories.append("Interior")
        flags["is_interior"] = True
    if _FIELD_RE.search(map_id):
        categories.append("Field")
    if map_id in town_maps:
        flags["is_town"] = True
        categories.append("City")
    elif map_id in _CITY_HUBS:
        categories.append("City")
    if _SPECIAL_RE.search(map_id):
        categories.append("Special")

    seen: set[str] = set()
    categories = [c for c in categories if not (c in seen or seen.add(c))]
    category = next((c for c in _CATEGORY_ORDER if c in categories), "Special")
    if "Special" not in categories and category == "Special":
        categories.append("Special")
    return {
        "category": category,
        "categories": categories,
        **flags,
        "classification_layer": "inferred",
    }


def extract_maps(project_root: Path | None = None) -> dict[str, Any]:
    root = project_root or Path(__file__).resolve().parents[1]
    cfg = _load_extractor_config(root)
    rathena = Path(cfg["paths"]["rathena"])
    reports_dir = root / cfg["output"]["reports_dir"]
    reports_dir.mkdir(parents=True, exist_ok=True)

    server = resolve_maps(rathena, cfg["server"]["maps_conf"])
    enabled = list(server["maps"])

    instance_maps, instance_names = _load_instance_maps(
        rathena,
        ["db/re/instance_db.yml", "db/import/instance_db.yml"],
    )
    town_maps = _load_town_maps(rathena, _TOWN_MAPFLAG_FILES)
    client_by_id = _load_jsonl_index(reports_dir / "client_maps.jsonl", "map_id")

    records: list[dict[str, Any]] = []
    by_cat: dict[str, int] = {}

    for map_id in enabled:
        client = client_by_id.get(map_id)
        classed = classify_map(map_id, instance_maps, town_maps)
        present = bool(client and client.get("complete"))

        display_name = client.get("display_name") if client else None
        display_source = "mapnametable" if display_name else None
        if not display_name and map_id in instance_names:
            display_name = instance_names[map_id]
            display_source = "instance_db"

        source_path = cfg["server"]["maps_conf"]
        record = {
            "map_id": map_id,
            "display_name": display_name,
            "display_name_source": display_source,
            "category": classed["category"],
            "categories": classed["categories"],
            "is_town": classed["is_town"],
            "is_dungeon": classed["is_dungeon"],
            "is_instance": classed["is_instance"],
            "is_quest_map": classed["is_quest_map"],
            "is_guild_map": classed["is_guild_map"],
            "is_interior": classed["is_interior"],
            "is_accessible": True,
            "access_conditions": None,
            "width": client.get("width") if client else None,
            "height": client.get("height") if client else None,
            "client_resource_present": present,
            "client": {
                "has_rsw": bool(client.get("has_rsw")) if client else False,
                "has_gat": bool(client.get("has_gat")) if client else False,
                "has_gnd": bool(client.get("has_gnd")) if client else False,
                "minimap_present": bool(client.get("minimap_present")) if client else False,
                "complete": bool(client.get("complete")) if client else False,
                "winner_grf": client.get("winner_grf") if client else None,
                "alias_of": client.get("alias_of") if client else None,
            }
            if client
            else None,
            "classification_layer": classed["classification_layer"],
            "provenance_id": _provenance_id("maps", map_id, source_path),
            "source": {
                "server_maps_conf": source_path,
                "client_maps": "reports/client_maps.jsonl" if client else None,
                "instance_db": map_id in instance_maps,
                "town_mapflag": map_id in town_maps,
                "city_hub_list": map_id in _CITY_HUBS,
            },
        }
        records.append(record)
        by_cat[record["category"]] = by_cat.get(record["category"], 0) + 1

    out_path = reports_dir / "maps.jsonl"
    with out_path.open("w", encoding="utf-8") as f:
        for row in records:
            f.write(json.dumps(row, ensure_ascii=False, sort_keys=False) + "\n")

    summary = {
        "domain": "maps",
        "enabled_count": len(records),
        "by_category": by_cat,
        "unclassified_count": sum(1 for r in records if r["category"] is None),
        "special_count": by_cat.get("Special", 0),
        "town_mapflag_count": len(town_maps),
        "with_display_name": sum(1 for r in records if r.get("display_name")),
        "display_from_instance_db": sum(
            1 for r in records if r.get("display_name_source") == "instance_db"
        ),
        "display_missing": sum(1 for r in records if not r.get("display_name")),
        "with_dimensions": sum(
            1 for r in records if r.get("width") and r.get("height")
        ),
        "client_complete_count": sum(1 for r in records if r["client_resource_present"]),
        "instance_db_maps": len(instance_maps),
        "wrote": str(out_path),
    }
    summary_path = reports_dir / "maps_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    summary["summary_path"] = str(summary_path)
    return summary
