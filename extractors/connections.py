"""Map connections — warp/warp2 headers + OzRo F_OzroWarp custom teleports."""

from __future__ import annotations

import hashlib
import json
import re
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

_OZRO_WARP_RE = re.compile(
    r'callfunc\s+"F_OzroWarp"\s*,\s*"([^"]*)"\s*,\s*"([A-Za-z0-9_@-]+)"\s*,\s*(-?\d+)\s*,\s*(-?\d+)'
)

_OZRO_ZENY = 4000
_OZRO_GEM_ITEM_ID = 717
_OZRO_GEM_AMOUNT = 1


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
    return raw, None


def _load_npc_index(npcs_path: Path) -> dict[tuple[Any, ...], str]:
    """Index npc_id by (script_path, line) and by (map_id, x, y, script_path)."""
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
    # Prefer line index; merge xy as fallback keys with distinct namespace
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
                cid = _connection_id(
                    "warp", src_map, sx, sy, dest, dx, dy, rel, line_no
                )
                npc_id = _lookup_npc(npc_index, rel, line_no, src_map, sx, sy)
                if not npc_id and unique:
                    npc_id = unique
                rec = {
                    "connection_id": cid,
                    "connection_type": "warp",
                    "source_map_id": src_map,
                    "source_x": sx,
                    "source_y": sy,
                    "destination_map_id": dest,
                    "destination_x": dx,
                    "destination_y": dy,
                    "npc_id": npc_id,
                    "warp_name": display,
                    "warp_variant": wtype,
                    "trigger_xs": int(wm.group("xs")),
                    "trigger_ys": int(wm.group("ys")),
                    "zeny_cost": None,
                    "required_items": None,
                    "conditions": None,
                    "is_directional": True,
                    "friction_weight": None,
                    "classification_layer": "absolute",
                    "provenance_id": _provenance_id("map_connections", cid, f"{rel}:{line_no}"),
                    "source": {"script_path": rel, "line": line_no},
                }
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
                cid = _connection_id(
                    "custom_npc_tp",
                    src_map,
                    sx,
                    sy,
                    dest,
                    dx,
                    dy,
                    label,
                    rel,
                    line_no,
                )
                npc_id = _lookup_npc(
                    npc_index, rel, current_npc["line"], src_map, sx, sy
                )
                if not npc_id and current_npc.get("unique"):
                    npc_id = current_npc["unique"]
                rec = {
                    "connection_id": cid,
                    "connection_type": "custom_npc_tp",
                    "source_map_id": src_map,
                    "source_x": sx,
                    "source_y": sy,
                    "destination_map_id": dest,
                    "destination_x": dx,
                    "destination_y": dy,
                    "npc_id": npc_id,
                    "label": label,
                    "zeny_cost": _OZRO_ZENY,
                    "required_items": [
                        {
                            "item_id": _OZRO_GEM_ITEM_ID,
                            "amount": _OZRO_GEM_AMOUNT,
                            "note": "Blue Gemstone",
                        }
                    ],
                    "conditions": None,
                    "is_directional": True,
                    "friction_weight": None,
                    "classification_layer": "absolute",
                    "provenance_id": _provenance_id(
                        "map_connections", cid, f"{rel}:{line_no}"
                    ),
                    "source": {
                        "script_path": rel,
                        "line": line_no,
                        "callfunc": "F_OzroWarp",
                        "npc_header_line": current_npc["line"],
                    },
                }
                records.append(rec)
                by_type["custom_npc_tp"] = by_type.get("custom_npc_tp", 0) + 1

    out_path = reports_dir / "map_connections.jsonl"
    with out_path.open("w", encoding="utf-8") as f:
        for row in records:
            f.write(json.dumps(row, ensure_ascii=False, sort_keys=False) + "\n")

    summary = {
        "domain": "map_connections",
        "connection_count": len(records),
        "by_type": by_type,
        "with_npc_id": sum(1 for r in records if r.get("npc_id")),
        "script_files": len(scripts),
        "deferred": ["kafra", "airship", "boat", "dungeon_tp", "scripted"],
        "wrote": str(out_path),
    }
    summary_path = reports_dir / "map_connections_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    summary["summary_path"] = str(summary_path)
    return summary
