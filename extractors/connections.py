"""Map connections — warps, OzRo TP, kafra, airship, boat (+ audit). Dijkstra deferred."""

from __future__ import annotations

import hashlib
import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any

import yaml

from discovery.scan import _load_extractor_config

# map,x,y,dir<TAB>warp|warp2<TAB>name<TAB[+]>xs,ys,dest,dx,dy [/* comment */]
_WARP_RE = re.compile(
    r"^(?P<map>[A-Za-z0-9_@-]+),(?P<x>-?\d+),(?P<y>-?\d+),(?P<dir>\d+)\t"
    r"(?P<type>warp2?)\t(?P<name>[^\t]*)\t+"
    r"\s*(?P<xs>\d+)\s*,\s*(?P<ys>\d+)\s*,\s*(?P<dest>[A-Za-z0-9_@-]+)\s*,"
    r"\s*(?P<dx>-?\d+)\s*,\s*(?P<dy>-?\d+)\s*"
    r"(?:/\*.*?\*/)?\s*$"
)

_NPC_HEADER_RE = re.compile(
    r"^(?P<map>-|[A-Za-z0-9_@-]+),(?P<x>-?\d+),(?P<y>-?\d+),(?P<dir>\d+)\t"
    r"(?P<type>script|shop|cashshop|itemshop|pointshop|marketshop|warp|warp2|"
    r"duplicate\([^)]+\))"
    r"\t(?P<name>[^\t]+)\t"
)

_FLOAT_SCRIPT_RE = re.compile(
    r"^-\tscript\t(?P<name>[^\t]+)\t-1,?\s*\{?\s*$"
)

_OZRO_WARP_RE = re.compile(
    r'callfunc\s+"F_OzroWarp"\s*,\s*"([^"]*)"\s*,\s*"([A-Za-z0-9_@-]+)"\s*,\s*(-?\d+)\s*,\s*(-?\d+)'
)

_KAFRA_CALL_RE = re.compile(
    r'callfunc\s+"F_Kafra"\s*,\s*(-?\d+)\s*,\s*(-?\d+)'
)
_KAFSET_RE = re.compile(r'callfunc\s+"F_KafSet"')

_WARP_CMD_RE = re.compile(
    r'warp\s+"([A-Za-z0-9_@-]+)"\s*,\s*(-?\d+)\s*,\s*(-?\d+)'
)
_ZENY_COST_RE = re.compile(
    r"(?:"
    r"Zeny\s*<\s*(\d+)"
    r"|Zeny\s*>\s*(\d+)"
    r"|Zeny\s*>=\s*(\d+)"
    r"|Zeny\s*-=\s*(\d+)"
    r"|set\s+Zeny\s*,\s*Zeny\s*-\s*(\d+)"
    r"|set\s+\.@cost\s*,\s*(\d+)"
    r")",
    re.I,
)

_OZRO_ZENY = 4000
_OZRO_GEM_ITEM_ID = 717
_OZRO_GEM_AMOUNT = 1
_AIRSHIP_BOARD_ZENY = 1200
_AIRSHIP_TICKET_ITEM = 7311

# menu_num values that expose "Use Teleport Service" (see F_Kafra)
_KAFRA_TELEPORT_MENUS = {0, 9}

FRICTION = {
    "warp": 1.0,
    "kafra": 0.2,
    "custom_npc_tp": 0.5,  # OzRo dungeon warpers (brief: Dungeon TP)
    "airship": 1.5,
    "boat": 1.2,
}

# Display name → destination used by F_KafTele (Renewal coords).
_KAFRA_DEST: dict[str, tuple[str, int, int]] = {
    "Al De Baran": ("aldebaran", 168, 112),
    "Alberta": ("alberta", 117, 56),
    "Comodo": ("comodo", 209, 143),
    "Comodo Pharos Beacon": ("cmd_fild07", 127, 134),
    "Geffen": ("geffen", 120, 39),
    "Izlude": ("izlude", 128, 98),
    "Juno": ("yuno", 158, 125),
    "Mjolnir Dead Pit": ("mjolnir_02", 99, 351),
    "Morocc": ("morocc", 156, 46),
    "Orc Dungeon": ("gef_fild10", 52, 326),
    "Payon": ("payon", 161, 58),
    "Prontera": ("prontera", 116, 72),
    "Umbala": ("umbala", 100, 154),
}

# F_KafSet destination lists per source map (base prices, non-VIP).
_KAFRA_FROM: dict[str, list[tuple[str, int]]] = {
    "prontera": [
        ("Izlude", 600),
        ("Geffen", 1200),
        ("Payon", 1200),
        ("Morocc", 1200),
        ("Orc Dungeon", 1700),
        ("Alberta", 1800),
    ],
    "alberta": [("Payon", 1200), ("Morocc", 1800), ("Prontera", 1800)],
    "aldebaran": [
        ("Geffen", 1200),
        ("Juno", 1200),
        ("Izlude", 1800),
        ("Mjolnir Dead Pit", 1700),
    ],
    "comodo": [
        ("Morocc", 1800),
        ("Comodo Pharos Beacon", 1200),
        ("Umbala", 1800),
    ],
    "cmd_fild07": [("Comodo", 1200), ("Morocc", 1200)],
    "geffen": [
        ("Prontera", 1200),
        ("Al De Baran", 1200),
        ("Orc Dungeon", 1700),
        ("Mjolnir Dead Pit", 1700),
    ],
    "izlude": [
        ("Geffen", 1200),
        ("Payon", 1200),
        ("Morocc", 1200),
        ("Al De Baran", 1800),
    ],
    "morocc": [
        ("Prontera", 1200),
        ("Payon", 1200),
        ("Alberta", 1800),
        ("Comodo", 1800),
        ("Comodo Pharos Beacon", 1200),
    ],
    "umbala": [("Comodo", 1800)],
    "payon": [("Prontera", 1200), ("Alberta", 1200), ("Morocc", 1200)],
    "yuno": [("Al De Baran", 1200)],
    "job3_rune01": [
        ("Izlude", 600),
        ("Geffen", 1200),
        ("Payon", 1200),
        ("Morocc", 1200),
        ("Alberta", 1800),
    ],
}

# City-level airship edges (matches airships.txt stop warps / transport.json).
_AIRSHIP_ROUTES: list[dict[str, Any]] = [
    {
        "route_id": "domestic-main",
        "stops": [
            ("yuno", 92, 260),
            ("einbroch", 92, 278),
            ("lighthalzen", 302, 75),
        ],
        "loop": False,
        "bidirectional": True,
        "plane": "airplane",
    },
    {
        "route_id": "domestic-hugel",
        "stops": [("yuno", 92, 260), ("hugel", 181, 146)],
        "loop": False,
        "bidirectional": True,
        "plane": "airplane",
    },
    {
        "route_id": "international",
        "stops": [
            ("izlude", 200, 73),
            ("yuno", 12, 261),
            ("ra_fild12", 292, 204),
        ],
        "loop": True,
        "bidirectional": True,
        "plane": "airplane_01",
    },
]

_BOAT_NAME_HINT = re.compile(
    r"Sailor|Fisk|Ferry|Marinero|Boat|"
    r"Sea[_ ]Captain|Kunlun[_ ]Envoy|Aibakthing|Crewman_bra|"
    r"PR_Officer_moscovia|Girl_louyang|Girl#0lou|"
    r"Dolangmal|Optamara|Janssen|Turtle_Scholar|Sailor_alberta",
    re.I,
)

_NOT_BOAT = re.compile(r"Airship|airplane|Airport", re.I)
_NOT_BOAT_MAPS = frozenset(
    {"airplane", "airplane_01", "airport", "y_airport", "lhz_airport"}
)


def _provenance_id(domain: str, record_id: str, source_path: str) -> str:
    raw = f"{domain}|{record_id}|{source_path}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def _connection_id(*parts: Any) -> str:
    raw = "|".join("" if p is None else str(p) for p in parts)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def _parse_name_unique(name_field: str) -> tuple[str, str | None]:
    raw = name_field.strip()
    if "::" in raw:
        left, right = raw.split("::", 1)
        display = left.strip() or right.strip()
        unique = right.strip() or None
        return display, unique
    if raw.startswith("::"):
        return raw[2:].strip(), raw[2:].strip()
    return raw, None


def _dup_target(npc_type: str) -> str | None:
    m = re.match(r"duplicate\(([^)]+)\)", npc_type)
    return m.group(1).strip() if m else None


def _load_npc_index(npcs_path: Path) -> dict[tuple[Any, ...], str]:
    by_line: dict[tuple[Any, ...], str] = {}
    by_xy: dict[tuple[Any, ...], str] = {}
    if not npcs_path.is_file():
        return {}
    for line in npcs_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        sp = row.get("script_path")
        ln = row.get("script_line")
        if sp and ln is not None:
            by_line[(sp, ln)] = row["npc_id"]
        if row.get("map_id") is not None and row.get("x") is not None:
            by_xy[(row["map_id"], row["x"], row["y"], sp)] = row["npc_id"]
    out = {("line", *k): v for k, v in by_line.items()}
    out.update({("xy", *k): v for k, v in by_xy.items()})
    return out


def _lookup_npc(
    index: dict[tuple[Any, ...], str],
    script_path: str,
    line_no: int,
    map_id: str | None,
    x: int | None,
    y: int | None,
) -> str | None:
    hit = index.get(("line", script_path, line_no))
    if hit:
        return hit
    if map_id is not None and x is not None and y is not None:
        return index.get(("xy", map_id, x, y, script_path))
    return None


def _mk_rec(
    *,
    connection_type: str,
    source_map_id: str,
    source_x: int | None,
    source_y: int | None,
    destination_map_id: str,
    destination_x: int | None,
    destination_y: int | None,
    npc_id: str | None,
    zeny_cost: int | None,
    required_items: list[dict[str, Any]] | None,
    conditions: Any,
    source: dict[str, Any],
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    cid = _connection_id(
        connection_type,
        source_map_id,
        source_x,
        source_y,
        destination_map_id,
        destination_x,
        destination_y,
        source.get("script_path"),
        source.get("line"),
        source.get("label"),
        source.get("route_id"),
        source.get("edge"),
    )
    rec: dict[str, Any] = {
        "connection_id": cid,
        "connection_type": connection_type,
        "source_map_id": source_map_id,
        "source_x": source_x,
        "source_y": source_y,
        "destination_map_id": destination_map_id,
        "destination_x": destination_x,
        "destination_y": destination_y,
        "npc_id": npc_id,
        "zeny_cost": zeny_cost,
        "required_items": required_items,
        "conditions": conditions,
        "is_directional": True,
        "friction_weight": FRICTION.get(connection_type),
        "classification_layer": "absolute",
        "provenance_id": _provenance_id(
            "map_connections",
            cid,
            f"{source.get('script_path')}:{source.get('line')}",
        ),
        "source": source,
    }
    if extra:
        rec.update(extra)
    return rec


def _index_script_bodies(
    rathena: Path, scripts: list[str]
) -> tuple[dict[str, dict[str, Any]], list[dict[str, Any]]]:
    """Index floating unique scripts and placed NPCs (script/duplicate)."""
    floating: dict[str, dict[str, Any]] = {}
    placed: list[dict[str, Any]] = []

    for rel in scripts:
        path = rathena / rel
        if not path.is_file():
            continue
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        i = 0
        while i < len(lines):
            line = lines[i].split("//", 1)[0].rstrip()
            fm = _FLOAT_SCRIPT_RE.match(line)
            hm = None if fm else _NPC_HEADER_RE.match(line)
            if fm or (hm and hm.group("type").startswith("script")):
                if fm:
                    display, unique = _parse_name_unique(fm.group("name"))
                    unique = unique or display
                    map_id = None
                    x = y = None
                    ntype = "script"
                    line_no = i + 1
                else:
                    assert hm is not None
                    display, unique = _parse_name_unique(hm.group("name"))
                    map_raw = hm.group("map")
                    map_id = None if map_raw == "-" else map_raw
                    x, y = int(hm.group("x")), int(hm.group("y"))
                    ntype = hm.group("type")
                    line_no = i + 1
                    unique = unique or display

                body: list[str] = []
                i += 1
                depth = 1 if line.rstrip().endswith("{") else 0
                while i < len(lines):
                    raw = lines[i]
                    stripped = raw.split("//", 1)[0]
                    if depth == 0 and (
                        _FLOAT_SCRIPT_RE.match(stripped.rstrip())
                        or _NPC_HEADER_RE.match(stripped.rstrip())
                        or stripped.startswith("function\tscript")
                    ):
                        break
                    body.append(raw)
                    depth += stripped.count("{") - stripped.count("}")
                    i += 1
                    if depth <= 0 and body:
                        break

                body_text = "\n".join(body)
                entry = {
                    "display": display,
                    "unique": unique,
                    "map_id": map_id,
                    "x": x,
                    "y": y,
                    "script_path": rel,
                    "line": line_no,
                    "body": body_text,
                    "type": ntype,
                }
                if map_id is None:
                    floating[unique] = entry
                    # also key without :: if present
                    floating[unique.lstrip(":")] = entry
                else:
                    placed.append(entry)
                continue

            if hm and hm.group("type").startswith("duplicate"):
                display, unique = _parse_name_unique(hm.group("name"))
                map_raw = hm.group("map")
                placed.append(
                    {
                        "display": display,
                        "unique": unique or display,
                        "map_id": None if map_raw == "-" else map_raw,
                        "x": int(hm.group("x")),
                        "y": int(hm.group("y")),
                        "script_path": rel,
                        "line": i + 1,
                        "body": None,
                        "type": hm.group("type"),
                        "dup_of": _dup_target(hm.group("type")),
                    }
                )
            i += 1

    return floating, placed


def _extract_kafra(
    rathena: Path,
    scripts: list[str],
    npc_index: dict[tuple[Any, ...], str],
) -> list[dict[str, Any]]:
    floating, placed = _index_script_bodies(rathena, scripts)
    # Resolve which unique scripts offer teleport
    tele_uniques: set[str] = set()
    for uniq, ent in floating.items():
        body = ent["body"]
        if not _KAFSET_RE.search(body) and "F_KafTele" not in body:
            # still check F_Kafra menu
            pass
        m = _KAFRA_CALL_RE.search(body)
        if not m:
            continue
        welcome, menu = int(m.group(1)), int(m.group(2))
        if menu in _KAFRA_TELEPORT_MENUS or welcome == 2:
            tele_uniques.add(uniq)
            tele_uniques.add(uniq.lstrip(":"))

    # Inline (non-floating) kafras with F_KafSet + teleport menu
    records: list[dict[str, Any]] = []
    seen: set[str] = set()

    def emit_from_npc(src_map: str, sx: int, sy: int, rel: str, line_no: int, uniq: str | None) -> None:
        dests = _KAFRA_FROM.get(src_map)
        if not dests:
            return
        npc_id = _lookup_npc(npc_index, rel, line_no, src_map, sx, sy)
        if not npc_id and uniq:
            npc_id = uniq
        for label, price in dests:
            dest = _KAFRA_DEST.get(label)
            if not dest:
                continue
            dmap, dx, dy = dest
            rec = _mk_rec(
                connection_type="kafra",
                source_map_id=src_map,
                source_x=sx,
                source_y=sy,
                destination_map_id=dmap,
                destination_x=dx,
                destination_y=dy,
                npc_id=npc_id,
                zeny_cost=price,
                required_items=[
                    {
                        "item_id": 7060,
                        "amount": 1,
                        "optional": True,
                        "note": "Free Ticket for Kafra Transportation",
                    }
                ],
                conditions={"vip_price_multiplier": 2, "note": "VIP_SCRIPT doubles price if inactive"},
                source={
                    "script_path": rel,
                    "line": line_no,
                    "label": label,
                    "via": "F_KafSet/F_KafTele",
                },
                extra={"label": label},
            )
            if rec["connection_id"] in seen:
                continue
            seen.add(rec["connection_id"])
            records.append(rec)

    for ent in placed:
        src_map = ent.get("map_id")
        if not src_map:
            continue
        body = ent.get("body")
        dup_of = ent.get("dup_of")
        if body is None and dup_of:
            src = floating.get(dup_of) or floating.get(f"::{dup_of}")
            body = src["body"] if src else None
            if src and (dup_of in tele_uniques or dup_of.lstrip(":") in tele_uniques):
                emit_from_npc(
                    src_map, ent["x"], ent["y"], ent["script_path"], ent["line"], ent.get("unique")
                )
                continue
        if not body:
            continue
        if not _KAFSET_RE.search(body):
            continue
        m = _KAFRA_CALL_RE.search(body)
        if not m:
            continue
        welcome, menu = int(m.group(1)), int(m.group(2))
        if menu not in _KAFRA_TELEPORT_MENUS and welcome != 2:
            continue
        emit_from_npc(
            src_map, ent["x"], ent["y"], ent["script_path"], ent["line"], ent.get("unique")
        )

    return records


def _extract_airship() -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for route in _AIRSHIP_ROUTES:
        stops: list[tuple[str, int, int]] = route["stops"]
        n = len(stops)
        pairs: list[tuple[int, int]] = []
        for i in range(n - 1):
            pairs.append((i, i + 1))
        if route.get("loop") and n > 1:
            pairs.append((n - 1, 0))

        for a, b in pairs:
            sa, sb = stops[a], stops[b]
            directions = [(sa, sb), (sb, sa)] if route.get("bidirectional") else [(sa, sb)]
            for src, dst in directions:
                records.append(
                    _mk_rec(
                        connection_type="airship",
                        source_map_id=src[0],
                        source_x=src[1],
                        source_y=src[2],
                        destination_map_id=dst[0],
                        destination_x=dst[1],
                        destination_y=dst[2],
                        npc_id=None,
                        zeny_cost=_AIRSHIP_BOARD_ZENY,
                        required_items=[
                            {
                                "item_id": _AIRSHIP_TICKET_ITEM,
                                "amount": 1,
                                "optional": True,
                                "note": "Free Ticket for Airship",
                            }
                        ],
                        conditions={
                            "schedule": True,
                            "plane": route["plane"],
                            "note": "City-level edge; boarding fee paid once to enter plane",
                        },
                        source={
                            "script_path": "npc/airports/airships.txt",
                            "line": None,
                            "route_id": route["route_id"],
                            "edge": f"{src[0]}->{dst[0]}",
                            "method": "route_model",
                        },
                        extra={"route_id": route["route_id"]},
                    )
                )
    return records


def _guess_zeny(body: str) -> int | None:
    costs = []
    for m in _ZENY_COST_RE.finditer(body):
        for g in m.groups():
            if g:
                costs.append(int(g))
    if not costs:
        return None
    # Prefer classic boat fares when present
    for preferred in (10000, 500, 250, 150, 200):
        if preferred in costs:
            return preferred
    return max(costs)


def _extract_boats(
    rathena: Path,
    scripts: list[str],
    npc_index: dict[tuple[Any, ...], str],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    floating, placed = _index_script_bodies(rathena, scripts)
    records: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    seen: set[str] = set()

    for ent in placed:
        src_map = ent.get("map_id")
        if not src_map or src_map in _NOT_BOAT_MAPS:
            continue
        body = ent.get("body")
        dup_of = ent.get("dup_of")
        origin_rel = ent["script_path"]
        origin_line = ent["line"]
        if body is None and dup_of:
            src = floating.get(dup_of) or floating.get(f"::{dup_of}")
            if not src:
                continue
            body = src["body"]
            origin_rel = src["script_path"]
            origin_line = src["line"]

        if not body:
            continue

        name = ent.get("display") or ""
        uniq = ent.get("unique") or ""
        if _NOT_BOAT.search(name) or _NOT_BOAT.search(uniq) or (
            dup_of and _NOT_BOAT.search(dup_of)
        ):
            continue
        if not (
            _BOAT_NAME_HINT.search(name)
            or _BOAT_NAME_HINT.search(uniq)
            or (dup_of and _BOAT_NAME_HINT.search(dup_of))
        ):
            continue

        # Prefer Renewal branch coords when checkre present
        warps: list[tuple[str, int, int]] = []
        # strip non-RE branches roughly: keep checkre(0) true branch warps
        for m in _WARP_CMD_RE.finditer(body):
            dmap, dx, dy = m.group(1), int(m.group(2)), int(m.group(3))
            if dmap == src_map:
                continue
            warps.append((dmap, dx, dy))

        if not warps:
            skipped.append(
                {
                    "reason": "boat_name_no_foreign_warp",
                    "map": src_map,
                    "name": name,
                    "script": ent["script_path"],
                    "line": ent["line"],
                }
            )
            continue

        # Deduplicate destinations (RE/pre-re pairs → keep first / RE-looking)
        by_dest: dict[str, tuple[str, int, int]] = {}
        for dmap, dx, dy in warps:
            if dmap not in by_dest:
                by_dest[dmap] = (dmap, dx, dy)

        zeny = _guess_zeny(body)
        conditions: dict[str, Any] = {}
        if "checkquest" in body or "TURTLE" in body or "MISC_QUEST" in body:
            conditions["quest_gated"] = True
        if "VIP_SCRIPT" in body or "vip_status" in body:
            conditions["vip_pricing"] = True

        npc_id = _lookup_npc(
            npc_index, ent["script_path"], ent["line"], src_map, ent["x"], ent["y"]
        )
        if not npc_id:
            npc_id = uniq or None

        for dmap, dx, dy in by_dest.values():
            rec = _mk_rec(
                connection_type="boat",
                source_map_id=src_map,
                source_x=ent["x"],
                source_y=ent["y"],
                destination_map_id=dmap,
                destination_x=dx,
                destination_y=dy,
                npc_id=npc_id,
                zeny_cost=zeny,
                required_items=None,
                conditions=conditions or None,
                source={
                    "script_path": ent["script_path"],
                    "line": ent["line"],
                    "body_script": origin_rel,
                    "body_line": origin_line,
                    "dup_of": dup_of,
                    "label": name,
                },
                extra={"label": name},
            )
            if rec["connection_id"] in seen:
                continue
            seen.add(rec["connection_id"])
            records.append(rec)

    return records, skipped


def _audit(
    records: list[dict[str, Any]],
    maps_path: Path,
    transport_path: Path | None,
    boat_skipped: list[dict[str, Any]],
) -> dict[str, Any]:
    map_ids: set[str] = set()
    if maps_path.is_file():
        for line in maps_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                map_ids.add(json.loads(line)["map_id"])

    by_type: dict[str, int] = defaultdict(int)
    missing_src: list[dict[str, Any]] = []
    missing_dst: list[dict[str, Any]] = []
    no_weight: list[str] = []
    parallel: dict[tuple[str, str, str], int] = defaultdict(int)

    for r in records:
        by_type[r["connection_type"]] += 1
        if r.get("friction_weight") is None:
            no_weight.append(r["connection_id"])
        if map_ids:
            if r["source_map_id"] not in map_ids:
                missing_src.append(
                    {"connection_id": r["connection_id"], "map": r["source_map_id"], "type": r["connection_type"]}
                )
            if r["destination_map_id"] not in map_ids:
                missing_dst.append(
                    {"connection_id": r["connection_id"], "map": r["destination_map_id"], "type": r["connection_type"]}
                )
        parallel[(r["connection_type"], r["source_map_id"], r["destination_map_id"])] += 1

    multi = [
        {"type": t, "from": a, "to": b, "edges": n}
        for (t, a, b), n in sorted(parallel.items(), key=lambda x: -x[1])
        if n > 1 and t in {"kafra", "airship", "boat", "custom_npc_tp"}
    ][:40]

    # transport.json verification (reference only)
    transport_diff: dict[str, Any] = {"available": False}
    if transport_path and transport_path.is_file():
        tj = json.loads(transport_path.read_text(encoding="utf-8"))
        kafra_ref = set()
        for line in tj.get("lines", []):
            if line.get("type") != "kafra":
                continue
            a, b = line["from"], line["to"]
            kafra_ref.add((a, b))
            if line.get("bidirectional", True):
                kafra_ref.add((b, a))

        kafra_got = {
            (r["source_map_id"], r["destination_map_id"])
            for r in records
            if r["connection_type"] == "kafra"
        }
        # collapse to unique map pairs
        transport_diff = {
            "available": True,
            "kafra_ref_directed": len(kafra_ref),
            "kafra_extracted_directed_unique": len(kafra_got),
            "kafra_missing_vs_ref": sorted(kafra_ref - kafra_got)[:50],
            "kafra_extra_vs_ref": sorted(kafra_got - kafra_ref)[:50],
            "note": "ozro-site transport.json is verification only, not source of truth",
        }

        boat_tooltip = set()
        for city, groups in tj.get("tooltips", {}).items():
            for g in groups:
                if g.get("type") in ("ships", "port"):
                    for d in g.get("destinations", []):
                        boat_tooltip.add((city, d["map"]))
        boat_got = {
            (r["source_map_id"], r["destination_map_id"])
            for r in records
            if r["connection_type"] == "boat"
        }
        transport_diff["boat_tooltip_pairs"] = len(boat_tooltip)
        transport_diff["boat_extracted_pairs"] = len(boat_got)
        transport_diff["boat_missing_vs_tooltip"] = sorted(boat_tooltip - boat_got)
        transport_diff["boat_extra_vs_tooltip"] = sorted(boat_got - boat_tooltip)[:40]

    critical = []
    if multi:
        critical.append(
            {
                "id": "parallel_edges",
                "severity": "high",
                "summary": "Multiple edges share the same type+from+to (esp. kafra NPCs). Dijkstra must collapse by min weight or unique map pairs.",
                "examples": multi[:10],
            }
        )
    if missing_dst:
        critical.append(
            {
                "id": "dest_not_in_maps",
                "severity": "high",
                "summary": "Destinations not present in maps.jsonl",
                "count": len(missing_dst),
                "examples": missing_dst[:10],
            }
        )
    if transport_diff.get("available") and transport_diff.get("boat_missing_vs_tooltip"):
        critical.append(
            {
                "id": "boat_coverage_gap",
                "severity": "medium",
                "summary": "Boat pairs listed in transport.json tooltips not extracted from scripts",
                "missing": transport_diff["boat_missing_vs_tooltip"],
            }
        )
    critical.append(
        {
            "id": "airship_model",
            "severity": "medium",
            "summary": "Airship edges are city-level route model (not per boarding NPC / airplane map hops). Rachel stop is ra_fild12.",
        }
    )
    critical.append(
        {
            "id": "kafra_vip",
            "severity": "low",
            "summary": "Kafra zeny_cost is base (non-VIP). VIP_SCRIPT may double prices.",
        }
    )
    critical.append(
        {
            "id": "disabled_extended_kafra",
            "severity": "info",
            "summary": "Kafra_Teleportation_Services / Zonda are in trash_bin — correctly omitted.",
        }
    )
    if any(
        isinstance(r.get("conditions"), dict) and r["conditions"].get("quest_gated")
        for r in records
        if r["connection_type"] == "boat"
    ):
        critical.append(
            {
                "id": "quest_gated_boats",
                "severity": "medium",
                "summary": "Some boat connections are quest-gated; including them in Dijkstra may overstate reachability.",
            }
        )
    critical.append(
        {
            "id": "boat_zeny_heuristic",
            "severity": "medium",
            "summary": "Boat zeny_cost is guessed per NPC body (preferred fare list), not per menu option. Multi-fare NPCs (e.g. Fisk 250/500, Izlude Sailor 150/500) may share one cost.",
        }
    )
    critical.append(
        {
            "id": "boat_landing_maps",
            "severity": "info",
            "summary": "Kunlun/Louyang boats land on gon_fild01/lou_fild01 (not city maps). transport.json labels them as gonryun/louyang — not a script bug.",
        }
    )

    return {
        "domain": "map_connections_audit",
        "connection_count": len(records),
        "by_type": dict(by_type),
        "friction_weights": FRICTION,
        "maps_catalog_size": len(map_ids),
        "missing_source_maps": missing_src[:20],
        "missing_destination_maps": missing_dst[:20],
        "connections_without_friction": len(no_weight),
        "parallel_edges_sample": multi,
        "boat_skipped_sample": boat_skipped[:30],
        "transport_json_diff": transport_diff,
        "critical_points": critical,
        "dijkstra_ready_checklist": [
            "Collapse parallel edges (same type, from, to) before graph build",
            "Decide whether quest_gated boats enter the friction graph",
            "Decide whether airplane/airport maps are nodes or only city-level airship edges",
            "Use friction_weight; keep zeny/items as attributes only",
            "Ignore connection_type=scripted if added later (brief)",
        ],
    }


def extract_connections(project_root: Path | None = None) -> dict[str, Any]:
    root = project_root or Path(__file__).resolve().parents[1]
    cfg = _load_extractor_config(root)
    rathena = Path(cfg["paths"]["rathena"])
    reports_dir = root / cfg["output"]["reports_dir"]
    reports_dir.mkdir(parents=True, exist_ok=True)

    files_path = reports_dir / "discovery_files.yml"
    if not files_path.is_file():
        raise FileNotFoundError(
            "reports/discovery_files.yml missing; run: python pipeline.py discover"
        )
    disc = yaml.safe_load(files_path.read_text(encoding="utf-8"))
    scripts: list[str] = list(disc.get("scripts") or [])

    npc_index = _load_npc_index(reports_dir / "npcs.jsonl")

    records: list[dict[str, Any]] = []
    by_type: dict[str, int] = {}

    # --- warps + OzRo custom TP (existing) ---
    for rel in scripts:
        path = rathena / rel
        if not path.is_file():
            continue

        current_npc: dict[str, Any] | None = None

        for line_no, raw in enumerate(
            path.read_text(encoding="utf-8", errors="replace").splitlines(), 1
        ):
            line = raw.split("//", 1)[0].rstrip()
            if not line.strip():
                continue

            wm = _WARP_RE.match(line)
            if wm:
                src_map = wm.group("map")
                sx, sy = int(wm.group("x")), int(wm.group("y"))
                dest = wm.group("dest")
                dx, dy = int(wm.group("dx")), int(wm.group("dy"))
                wtype = wm.group("type")
                wname = wm.group("name").strip()
                display, unique = _parse_name_unique(wname)
                npc_id = _lookup_npc(npc_index, rel, line_no, src_map, sx, sy)
                if not npc_id and unique:
                    npc_id = unique
                rec = _mk_rec(
                    connection_type="warp",
                    source_map_id=src_map,
                    source_x=sx,
                    source_y=sy,
                    destination_map_id=dest,
                    destination_x=dx,
                    destination_y=dy,
                    npc_id=npc_id,
                    zeny_cost=None,
                    required_items=None,
                    conditions=None,
                    source={"script_path": rel, "line": line_no},
                    extra={
                        "warp_name": display,
                        "warp_variant": wtype,
                        "trigger_xs": int(wm.group("xs")),
                        "trigger_ys": int(wm.group("ys")),
                    },
                )
                records.append(rec)
                by_type["warp"] = by_type.get("warp", 0) + 1
                current_npc = {
                    "map_id": src_map,
                    "x": sx,
                    "y": sy,
                    "line": line_no,
                    "name": display,
                    "unique": unique,
                }
                continue

            hm = _NPC_HEADER_RE.match(line)
            if hm:
                map_raw = hm.group("map")
                display, unique = _parse_name_unique(hm.group("name"))
                current_npc = {
                    "map_id": None if map_raw == "-" else map_raw,
                    "x": int(hm.group("x")),
                    "y": int(hm.group("y")),
                    "line": line_no,
                    "name": display,
                    "unique": unique,
                }
                continue

            om = _OZRO_WARP_RE.search(line)
            if om and current_npc and current_npc.get("map_id"):
                label, dest, dx_s, dy_s = om.group(1), om.group(2), om.group(3), om.group(4)
                dx, dy = int(dx_s), int(dy_s)
                src_map = current_npc["map_id"]
                sx, sy = current_npc["x"], current_npc["y"]
                npc_id = _lookup_npc(
                    npc_index, rel, current_npc["line"], src_map, sx, sy
                )
                if not npc_id and current_npc.get("unique"):
                    npc_id = current_npc["unique"]
                rec = _mk_rec(
                    connection_type="custom_npc_tp",
                    source_map_id=src_map,
                    source_x=sx,
                    source_y=sy,
                    destination_map_id=dest,
                    destination_x=dx,
                    destination_y=dy,
                    npc_id=npc_id,
                    zeny_cost=_OZRO_ZENY,
                    required_items=[
                        {
                            "item_id": _OZRO_GEM_ITEM_ID,
                            "amount": _OZRO_GEM_AMOUNT,
                            "note": "Blue Gemstone",
                        }
                    ],
                    conditions=None,
                    source={
                        "script_path": rel,
                        "line": line_no,
                        "callfunc": "F_OzroWarp",
                        "npc_header_line": current_npc["line"],
                        "label": label,
                    },
                    extra={"label": label},
                )
                records.append(rec)
                by_type["custom_npc_tp"] = by_type.get("custom_npc_tp", 0) + 1

    # --- kafra / airship / boat ---
    kafra = _extract_kafra(rathena, scripts, npc_index)
    records.extend(kafra)
    by_type["kafra"] = len(kafra)

    airship = _extract_airship()
    records.extend(airship)
    by_type["airship"] = len(airship)

    boats, boat_skipped = _extract_boats(rathena, scripts, npc_index)
    records.extend(boats)
    by_type["boat"] = len(boats)

    out_path = reports_dir / "map_connections.jsonl"
    with out_path.open("w", encoding="utf-8") as f:
        for row in records:
            f.write(json.dumps(row, ensure_ascii=False, sort_keys=False) + "\n")

    ozro_site = Path("/home/oz/Code/ozro-site/assets/world/transport.json")
    audit = _audit(
        records,
        reports_dir / "maps.jsonl",
        ozro_site if ozro_site.is_file() else None,
        boat_skipped,
    )
    audit_path = reports_dir / "map_connections_audit.json"
    audit_path.write_text(json.dumps(audit, indent=2) + "\n", encoding="utf-8")

    summary = {
        "domain": "map_connections",
        "connection_count": len(records),
        "by_type": by_type,
        "with_npc_id": sum(1 for r in records if r.get("npc_id")),
        "with_friction_weight": sum(1 for r in records if r.get("friction_weight") is not None),
        "script_files": len(scripts),
        "deferred": ["scripted"],
        "audit_path": str(audit_path),
        "critical_points": len(audit["critical_points"]),
        "wrote": str(out_path),
    }
    summary_path = reports_dir / "map_connections_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    summary["summary_path"] = str(summary_path)
    return summary
