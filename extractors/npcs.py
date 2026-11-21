"""NPCs extractor — enabled script headers (script/shop/duplicate/warp)."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

import yaml

from discovery.scan import _load_extractor_config

# map,x,y,dir<TAB>type<TAB>...
_NPC_HEADER_RE = re.compile(
    r"^(?P<map>-|[A-Za-z0-9_@-]+),(?P<x>-?\d+),(?P<y>-?\d+),(?P<dir>\d+)\t"
    r"(?P<type>script|shop|cashshop|itemshop|pointshop|marketshop|warp|warp2|"
    r"duplicate\([^)]+\))"
    r"\t(?P<rest>.+)$"
)

# Floating / label-only: -<TAB>script<TAB>...
_FLOAT_SCRIPT_RE = re.compile(
    r"^-\tscript\t(?P<rest>.+)$"
)

_FUNCTION_SCRIPT_RE = re.compile(r"^function\tscript\t")

# DisplayName::UniqueName  OR  ::UniqueName  OR  DisplayName
_NAME_SPRITE_RE = re.compile(
    r"^(?P<name>[^\t]+)\t(?P<sprite>[^\t,{]+)(?P<tail>.*)$"
)


def _provenance_id(domain: str, record_id: str, source_path: str) -> str:
    raw = f"{domain}|{record_id}|{source_path}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def _parse_name_fields(name_field: str) -> tuple[str, str | None, str]:
    """Return (display_name, unique_name, raw_name_field)."""
    raw = name_field.strip()
    if "::" in raw:
        left, right = raw.split("::", 1)
        display = left.strip() or right.strip()
        unique = right.strip() or None
        return display, unique, raw
    return raw, None, raw


def _parse_sprite(sprite_field: str) -> int | str | None:
    s = sprite_field.strip()
    if not s or s == "-1":
        return None
    if re.fullmatch(r"-?\d+", s):
        return int(s)
    return s


def _infer_functions(
    npc_type: str,
    _display_name: str,
    _script_path: str,
    _unique_name: str | None,
) -> list[str]:
    """Etapa 2: only 100% sure marks from header type; else pending.

    Path/name heuristics and deep script behavior → Etapa 3.
    """
    funcs: list[str] = []
    if npc_type in {"shop", "cashshop", "itemshop", "pointshop", "marketshop"}:
        funcs.append("Shop")
    if npc_type in {"warp", "warp2"}:
        funcs.append("Warper")
    return funcs or ["pending"]


def _stable_npc_id(
    unique_name: str | None,
    display_name: str,
    map_id: str | None,
    x: int | None,
    y: int | None,
    script_path: str,
    line_no: int,
) -> str:
    if unique_name:
        return unique_name
    basis = f"{script_path}:{line_no}|{map_id}|{x}|{y}|{display_name}"
    return "npc_" + hashlib.sha1(basis.encode("utf-8")).hexdigest()[:16]


def _parse_rest(rest: str) -> tuple[str, str | None, int | str | None] | None:
    m = _NAME_SPRITE_RE.match(rest.strip())
    if not m:
        return None
    display, unique, _raw = _parse_name_fields(m.group("name"))
    sprite = _parse_sprite(m.group("sprite"))
    return display, unique, sprite


def parse_npc_line(
    line: str, script_path: str, line_no: int
) -> dict[str, Any] | None:
    if _FUNCTION_SCRIPT_RE.match(line):
        return None

    map_id: str | None = None
    x = y = facing = None
    npc_type: str
    rest: str
    duplicate_of: str | None = None

    m = _NPC_HEADER_RE.match(line)
    if m:
        map_id = None if m.group("map") == "-" else m.group("map")
        x = int(m.group("x"))
        y = int(m.group("y"))
        facing = int(m.group("dir"))
        raw_type = m.group("type")
        if raw_type.startswith("duplicate("):
            npc_type = "duplicate"
            duplicate_of = raw_type[len("duplicate(") : -1]
        else:
            npc_type = raw_type
        rest = m.group("rest")
    else:
        m2 = _FLOAT_SCRIPT_RE.match(line)
        if not m2:
            return None
        npc_type = "script"
        rest = m2.group("rest")

    parsed = _parse_rest(rest)
    if not parsed:
        return None
    display, unique, sprite = parsed

    funcs = _infer_functions(npc_type, display, script_path, unique)
    npc_id = _stable_npc_id(unique, display, map_id, x, y, script_path, line_no)
    layer = "absolute" if funcs != ["pending"] else "pending"

    return {
        "npc_id": npc_id,
        "name": unique or display,
        "display_name": display,
        "map_id": map_id,
        "x": x,
        "y": y,
        "facing": facing,
        "sprite_id": sprite,
        "sprite_stem": None,
        "has_sprite": None,
        "npc_type": npc_type,
        "functions": funcs,
        "duplicate_of": duplicate_of,
        "script_path": script_path,
        "script_line": line_no,
        "classification_layer": layer,
        "provenance_id": _provenance_id("npcs", npc_id, f"{script_path}:{line_no}"),
        "source": {
            "script_path": script_path,
            "line": line_no,
        },
    }


def _load_sprite_index(path: Path) -> dict[int | str, dict[str, Any]]:
    """Index client_npc_sprites by numeric sprite_id and by JT name."""
    out: dict[int | str, dict[str, Any]] = {}
    if not path.is_file():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        info = {
            "sprite_stem": row.get("sprite_stem"),
            "has_spr": bool(row.get("has_spr")),
            "has_act": bool(row.get("has_act")),
            "paths": row.get("paths"),
            "winner_grf": row.get("winner_grf"),
            "act_deps_complete": row.get("act_deps_complete"),
        }
        for sid in row.get("sprite_ids") or []:
            out[int(sid)] = info
        for jt in row.get("jt_names") or []:
            out[str(jt)] = info
            # scripts sometimes use bare constant without JT_ prefix style
            if str(jt).startswith("JT_"):
                out[str(jt)[3:]] = info
    return out


def extract_npcs(project_root: Path | None = None) -> dict[str, Any]:
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
    sprite_index = _load_sprite_index(reports_dir / "client_npc_sprites.jsonl")

    records: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    dup_collisions = 0

    for rel in scripts:
        path = rathena / rel
        if not path.is_file():
            continue
        for line_no, raw in enumerate(
            path.read_text(encoding="utf-8", errors="replace").splitlines(), 1
        ):
            line = raw.split("//", 1)[0].rstrip()
            if not line.strip():
                continue
            rec = parse_npc_line(line, rel, line_no)
            if not rec:
                continue
            sid = rec.get("sprite_id")
            client = None
            if sid is not None:
                client = sprite_index.get(sid) or sprite_index.get(str(sid))
            if client:
                rec["sprite_stem"] = client.get("sprite_stem")
                rec["has_sprite"] = bool(
                    client.get("has_spr") and client.get("has_act")
                )
                rec["client"] = client
            else:
                rec["has_sprite"] = False if sid is not None else None
                rec["client"] = None
            npc_id = rec["npc_id"]
            if npc_id in seen_ids:
                # Keep first; count collision (common with reused ::labels across files).
                dup_collisions += 1
                rec["npc_id"] = f"{npc_id}@{rel}:{line_no}"
                rec["provenance_id"] = _provenance_id(
                    "npcs", rec["npc_id"], f"{rel}:{line_no}"
                )
            seen_ids.add(rec["npc_id"])
            records.append(rec)

    out_path = reports_dir / "npcs.jsonl"
    with out_path.open("w", encoding="utf-8") as f:
        for row in records:
            f.write(json.dumps(row, ensure_ascii=False, sort_keys=False) + "\n")

    by_type: dict[str, int] = {}
    func_counts: dict[str, int] = {}
    for r in records:
        by_type[r["npc_type"]] = by_type.get(r["npc_type"], 0) + 1
        for fn in r["functions"]:
            func_counts[fn] = func_counts.get(fn, 0) + 1

    summary = {
        "domain": "npcs",
        "npc_count": len(records),
        "script_files": len(scripts),
        "with_map": sum(1 for r in records if r["map_id"]),
        "floating": sum(1 for r in records if not r["map_id"]),
        "with_sprite_asset": sum(1 for r in records if r.get("has_sprite")),
        "sprite_id_unresolved": sum(
            1
            for r in records
            if r.get("sprite_id") is not None and not r.get("has_sprite")
        ),
        "id_collision_renames": dup_collisions,
        "ozro_custom": sum(
            1 for r in records if "custom/ozro" in (r["script_path"] or "")
        ),
        "by_type": by_type,
        "function_counts": func_counts,
        "wrote": str(out_path),
    }
    summary_path = reports_dir / "npcs_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    summary["summary_path"] = str(summary_path)
    return summary
