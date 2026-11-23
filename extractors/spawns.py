"""Spawns extractor — permanent headers + scripted monster/areamonster/guardian.

Pre-E5: scripted spawns link enclosing npc_id (alternate route; conditions out of scope).
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

import yaml

from discovery.scan import _load_extractor_config
from extractors.npcs import parse_npc_line

# map[,x,y[,xs,ys]] <TAB> monster|boss_monster <TAB> Name <TAB> id,amount[,...]
_SPAWN_RE = re.compile(
    r"^(?P<loc>[A-Za-z0-9_@-]+(?:,-?\d+,-?\d+(?:,-?\d+,-?\d+)?)?)\t"
    r"(?P<kind>monster|boss_monster)\t"
    r"(?P<name>[^\t]+)\t"
    r"\s*(?P<body>.+)$"
)

_EVENT_RE = re.compile(r'^"(?P<event>[^"]*)"\s*$')

# Indented script commands (not map-header lines).
_SCRIPTED_CALL_RE = re.compile(
    r"^\s+(?P<kind>monster|areamonster|guardian)\s+(?P<args>.+?)\s*;?\s*$"
)
_SCRIPT_NPC_RE = re.compile(
    r"^(?:-|[A-Za-z0-9_@-]+,-?\d+,-?\d+,\d+)\tscript\t"
)
_STR_LIT_RE = re.compile(r'^"(?P<val>(?:\\.|[^"\\])*)"$')
_INT_LIT_RE = re.compile(r"^-?\d+$")
_INSTANCE_MAP_RE = re.compile(
    r'^instance_mapname\s*\(\s*"(?P<map>[A-Za-z0-9_@-]+)"\s*\)$'
)


def _enclosing_script_npc(
    lines: list[str], line_no: int, script_path: str
) -> dict[str, Any] | None:
    for i in range(line_no - 1, -1, -1):
        raw = lines[i].split("//", 1)[0].rstrip()
        if not _SCRIPT_NPC_RE.match(raw):
            continue
        return parse_npc_line(raw, script_path, i + 1)
    return None


def _provenance_id(domain: str, record_id: str, source_path: str) -> str:
    raw = f"{domain}|{record_id}|{source_path}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def _spawn_id(*parts: Any) -> str:
    raw = "|".join("" if p is None else str(p) for p in parts)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def _parse_loc(loc: str) -> tuple[str, int | None, int | None, int | None, int | None]:
    parts = loc.split(",")
    map_id = parts[0]
    if len(parts) == 1:
        return map_id, None, None, None, None
    if len(parts) == 3:
        return map_id, int(parts[1]), int(parts[2]), None, None
    if len(parts) == 5:
        return map_id, int(parts[1]), int(parts[2]), int(parts[3]), int(parts[4])
    raise ValueError(f"unexpected spawn loc: {loc}")


def _parse_body(
    body: str, aegis_to_id: dict[str, int]
) -> dict[str, Any] | None:
    """Parse id|AegisName,amount[,delay1[,delay2[,flag_or_event...]]]."""
    s = body.strip().rstrip(";")
    # Split on commas not inside quotes
    parts: list[str] = []
    cur = []
    in_q = False
    for ch in s:
        if ch == '"':
            in_q = not in_q
            cur.append(ch)
        elif ch == "," and not in_q:
            parts.append("".join(cur).strip())
            cur = []
        else:
            cur.append(ch)
    if cur or parts:
        parts.append("".join(cur).strip())

    if len(parts) < 2:
        return None
    try:
        amount = int(parts[1])
    except ValueError:
        return None

    mob_token = parts[0]
    if re.fullmatch(r"-?\d+", mob_token):
        mob_id = int(mob_token)
    else:
        mob_id = aegis_to_id.get(mob_token)
        if mob_id is None:
            return None

    respawn_min = None
    respawn_max = None
    event_id = None
    boss_flag = None

    rest = parts[2:]
    nums: list[int] = []
    for p in rest:
        em = _EVENT_RE.match(p)
        if em:
            event_id = em.group("event") or None
            continue
        if re.fullmatch(r"-?\d+", p):
            nums.append(int(p))
            continue
        # bare event label without quotes (rare)
        if p and not p[0].isdigit() and event_id is None:
            event_id = p

    if nums:
        respawn_min = nums[0]
    if len(nums) >= 2:
        respawn_max = nums[1]
    if len(nums) >= 3:
        boss_flag = nums[2]

    return {
        "mob_id": mob_id,
        "amount": amount,
        "respawn_min": respawn_min,
        "respawn_max": respawn_max,
        "event_id": event_id,
        "boss_flag": boss_flag,
    }


def _load_aegis_index(mobs_path: Path) -> dict[str, int]:
    out: dict[str, int] = {}
    if not mobs_path.is_file():
        return out
    for line in mobs_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        aegis = row.get("aegis_name")
        mid = row.get("mob_id")
        if aegis is not None and mid is not None:
            out[str(aegis)] = int(mid)
    return out



def _spawn_type(kind: str, script_path: str, map_id: str, event_id: str | None) -> str:
    path_l = script_path.lower()
    if re.match(r"^\d+@", map_id) or "instance" in path_l:
        return "instance"
    if event_id:
        return "event"
    return "permanent"


def _split_args(argstr: str) -> list[str]:
    """Split script args on commas; respect quotes and parentheses."""
    parts: list[str] = []
    cur: list[str] = []
    depth = 0
    in_q = False
    i = 0
    s = argstr.strip().rstrip(";")
    while i < len(s):
        ch = s[i]
        if in_q:
            cur.append(ch)
            if ch == "\\" and i + 1 < len(s):
                cur.append(s[i + 1])
                i += 2
                continue
            if ch == '"':
                in_q = False
            i += 1
            continue
        if ch == '"':
            in_q = True
            cur.append(ch)
        elif ch == "(":
            depth += 1
            cur.append(ch)
        elif ch == ")":
            depth = max(0, depth - 1)
            cur.append(ch)
        elif ch == "," and depth == 0:
            parts.append("".join(cur).strip())
            cur = []
        else:
            cur.append(ch)
        i += 1
    if cur or parts:
        parts.append("".join(cur).strip())
    return [p for p in parts if p != ""]


def _parse_str_lit(expr: str) -> str | None:
    m = _STR_LIT_RE.match(expr.strip())
    return m.group("val") if m else None


def _parse_int_lit(expr: str) -> int | None:
    e = expr.strip()
    if _INT_LIT_RE.fullmatch(e):
        return int(e)
    return None


def _resolve_map_expr(expr: str) -> tuple[str | None, str | None]:
    """Return (map_id or None, raw_expr if unresolved)."""
    e = expr.strip()
    lit = _parse_str_lit(e)
    if lit is not None:
        return lit, None
    im = _INSTANCE_MAP_RE.match(e)
    if im:
        return im.group("map"), None
    return None, e


def _resolve_mob_token(expr: str, aegis_to_id: dict[str, int]) -> tuple[int | None, str | None]:
    e = expr.strip()
    n = _parse_int_lit(e)
    if n is not None:
        return n, None
    lit = _parse_str_lit(e)
    if lit is not None:
        if lit in aegis_to_id:
            return aegis_to_id[lit], None
        return None, e
    return None, e


def _resolve_name(expr: str) -> str | None:
    return _parse_str_lit(expr)


def _scripted_spawn_type(script_path: str, map_id: str | None, map_raw: str | None) -> str:
    path_l = script_path.lower()
    if "instance" in path_l:
        return "instance"
    if map_id and re.match(r"^\d+@", map_id):
        return "instance"
    if map_raw and "instance_mapname" in map_raw:
        return "instance"
    return "scripted"


def _parse_scripted_call(
    kind: str, args: list[str], aegis_to_id: dict[str, int]
) -> dict[str, Any] | None:
    """Parse monster/areamonster/guardian args. Require resolvable mob_id."""
    unresolved: list[str] = []

    if kind == "areamonster":
        if len(args) < 8:
            return None
        map_id, map_raw = _resolve_map_expr(args[0])
        if map_raw:
            unresolved.append("map")
        coords = []
        for idx, label in enumerate(("x", "y", "x2", "y2"), start=1):
            v = _parse_int_lit(args[idx])
            coords.append(v)
            if v is None:
                unresolved.append(label)
        display = _resolve_name(args[5])
        if display is None:
            unresolved.append("display_name")
        mob_id, mob_raw = _resolve_mob_token(args[6], aegis_to_id)
        if mob_id is None:
            return None  # cannot attribute spawn without mob
        amount = _parse_int_lit(args[7])
        if amount is None:
            unresolved.append("amount")
        event_id = _parse_str_lit(args[8]) if len(args) > 8 else None
        return {
            "mob_id": mob_id,
            "map_id": map_id,
            "display_name": display,
            "amount": amount,
            "x": coords[0],
            "y": coords[1],
            "x_area": None,
            "y_area": None,
            "x2": coords[2],
            "y2": coords[3],
            "event_id": event_id,
            "unresolved": unresolved,
            "map_raw": map_raw,
            "mob_raw": mob_raw,
        }

    if kind == "guardian":
        if len(args) < 5:
            return None
        map_id, map_raw = _resolve_map_expr(args[0])
        if map_raw:
            unresolved.append("map")
        x = _parse_int_lit(args[1])
        y = _parse_int_lit(args[2])
        if x is None:
            unresolved.append("x")
        if y is None:
            unresolved.append("y")
        display = _resolve_name(args[3])
        if display is None:
            unresolved.append("display_name")
        mob_id, mob_raw = _resolve_mob_token(args[4], aegis_to_id)
        if mob_id is None:
            return None
        event_id = _parse_str_lit(args[5]) if len(args) > 5 else None
        return {
            "mob_id": mob_id,
            "map_id": map_id,
            "display_name": display,
            "amount": 1,
            "x": x,
            "y": y,
            "x_area": None,
            "y_area": None,
            "x2": None,
            "y2": None,
            "event_id": event_id,
            "unresolved": unresolved,
            "map_raw": map_raw,
            "mob_raw": mob_raw,
        }

    # monster
    if len(args) < 6:
        return None
    map_id, map_raw = _resolve_map_expr(args[0])
    if map_raw:
        unresolved.append("map")
    x = _parse_int_lit(args[1])
    y = _parse_int_lit(args[2])
    if x is None:
        unresolved.append("x")
    if y is None:
        unresolved.append("y")
    display = _resolve_name(args[3])
    if display is None:
        unresolved.append("display_name")
    mob_id, mob_raw = _resolve_mob_token(args[4], aegis_to_id)
    if mob_id is None:
        return None
    amount = _parse_int_lit(args[5])
    if amount is None:
        unresolved.append("amount")
    event_id = _parse_str_lit(args[6]) if len(args) > 6 else None
    return {
        "mob_id": mob_id,
        "map_id": map_id,
        "display_name": display,
        "amount": amount,
        "x": x,
        "y": y,
        "x_area": None,
        "y_area": None,
        "x2": None,
        "y2": None,
        "event_id": event_id,
        "unresolved": unresolved,
        "map_raw": map_raw,
        "mob_raw": mob_raw,
    }


def extract_spawns(project_root: Path | None = None) -> dict[str, Any]:
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
    aegis_to_id = _load_aegis_index(reports_dir / "mobs.jsonl")

    records: list[dict[str, Any]] = []
    by_type: dict[str, int] = {}
    by_kind: dict[str, int] = {}
    parse_fail = 0
    scripted_skip_no_mob = 0
    scripted_partial = 0

    scripted_with_npc = 0
    scripted_missing_npc = 0

    for rel in scripts:
        path = rathena / rel
        if not path.is_file():
            continue
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        for line_no, raw in enumerate(lines, 1):
            line = raw.split("//", 1)[0].rstrip()
            if not line.strip():
                continue
            if "/*" in line:
                line = re.sub(r"/\*.*?\*/", "", line).rstrip()

            # --- permanent / boss headers ---
            m = _SPAWN_RE.match(line)
            if m:
                try:
                    map_id, x, y, x_area, y_area = _parse_loc(m.group("loc"))
                except ValueError:
                    parse_fail += 1
                    continue
                body = _parse_body(m.group("body"), aegis_to_id)
                if not body:
                    parse_fail += 1
                    continue

                kind = m.group("kind")
                name = m.group("name").strip()
                stype = _spawn_type(kind, rel, map_id, body["event_id"])
                sid = _spawn_id(
                    "header",
                    map_id,
                    body["mob_id"],
                    x,
                    y,
                    x_area,
                    y_area,
                    body["amount"],
                    body["respawn_min"],
                    body["respawn_max"],
                    body["event_id"],
                    kind,
                    rel,
                    line_no,
                )
                rec = {
                    "spawn_id": sid,
                    "mob_id": body["mob_id"],
                    "map_id": map_id,
                    "spawn_type": stype,
                    "spawn_kind": kind,
                    "display_name": name,
                    "amount": body["amount"],
                    "x": x,
                    "y": y,
                    "x_area": x_area,
                    "y_area": y_area,
                    "respawn_min": body["respawn_min"],
                    "respawn_max": body["respawn_max"],
                    "respawn_unit": "ms" if body["respawn_min"] is not None else None,
                    "spawn_condition": None,
                    "event_id": body["event_id"],
                    "boss_flag": body["boss_flag"],
                    "script_path": rel,
                    "script_line": line_no,
                    "classification_layer": "absolute",
                    "provenance_id": _provenance_id("spawns", sid, f"{rel}:{line_no}"),
                    "source": {"script_path": rel, "line": line_no, "form": "header"},
                }
                records.append(rec)
                by_type[stype] = by_type.get(stype, 0) + 1
                by_kind[kind] = by_kind.get(kind, 0) + 1
                continue

            # --- scripted monster / areamonster / guardian ---
            sm = _SCRIPTED_CALL_RE.match(line)
            if not sm:
                continue
            kind = sm.group("kind")
            args = _split_args(sm.group("args"))
            parsed = _parse_scripted_call(kind, args, aegis_to_id)
            if not parsed:
                scripted_skip_no_mob += 1
                continue

            stype = _scripted_spawn_type(rel, parsed["map_id"], parsed.get("map_raw"))
            # Instance path + scripted call: keep type instance (not scripted)
            if stype == "instance":
                pass
            else:
                stype = "scripted"

            unresolved = list(parsed.get("unresolved") or [])
            if unresolved:
                scripted_partial += 1
            cond = {"unresolved": unresolved} if unresolved else None
            if parsed.get("map_raw"):
                cond = cond or {}
                cond["map_expr"] = parsed["map_raw"]

            caller = _enclosing_script_npc(lines, line_no, rel)
            npc_id = caller["npc_id"] if caller else None
            if stype == "scripted":
                if npc_id:
                    scripted_with_npc += 1
                else:
                    scripted_missing_npc += 1
            sid = _spawn_id(
                "scripted",
                kind,
                parsed["map_id"],
                parsed["mob_id"],
                parsed["x"],
                parsed["y"],
                parsed.get("x2"),
                parsed.get("y2"),
                parsed["amount"],
                parsed["event_id"],
                rel,
                line_no,
            )
            rec = {
                "spawn_id": sid,
                "mob_id": parsed["mob_id"],
                "map_id": parsed["map_id"],
                "npc_id": npc_id,
                "spawn_type": stype,
                "spawn_kind": kind,
                "spawn_route": "npc_script"
                if stype == "scripted"
                else ("instance_script" if stype == "instance" else stype),
                "display_name": parsed["display_name"],
                "amount": parsed["amount"],
                "x": parsed["x"],
                "y": parsed["y"],
                "x_area": parsed["x_area"],
                "y_area": parsed["y_area"],
                "x2": parsed.get("x2"),
                "y2": parsed.get("y2"),
                "respawn_min": None,
                "respawn_max": None,
                "respawn_unit": None,
                "spawn_condition": cond,
                "event_id": parsed["event_id"],
                "boss_flag": None,
                "script_path": rel,
                "script_line": line_no,
                "classification_layer": "absolute"
                if not unresolved
                else "inferred",
                "provenance_id": _provenance_id("spawns", sid, f"{rel}:{line_no}"),
                "source": {
                    "script_path": rel,
                    "line": line_no,
                    "form": "script_command",
                    "command": kind,
                },
            }
            records.append(rec)
            by_type[stype] = by_type.get(stype, 0) + 1
            by_kind[kind] = by_kind.get(kind, 0) + 1

    # --- slaves from skill_summons.jsonl (run extract skills first) ---
    summons_path = reports_dir / "skill_summons.jsonl"
    slave_added = 0
    if summons_path.is_file():
        for line in summons_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            s = json.loads(line)
            if s.get("summon_kind") != "mob_slave":
                continue
            child = s.get("summoned_mob_id")
            parent = s.get("parent_mob_id")
            if child is None or parent is None:
                continue
            sid = _spawn_id(
                "slave",
                parent,
                child,
                s.get("skill_id"),
                s.get("skill_name"),
                s.get("source_file"),
                s.get("source_line"),
            )
            rec = {
                "spawn_id": sid,
                "mob_id": int(child),
                "map_id": None,
                "spawn_type": "slave",
                "spawn_kind": "mob_skill_summon",
                "display_name": None,
                "amount": s.get("amount"),
                "x": None,
                "y": None,
                "x_area": None,
                "y_area": None,
                "respawn_min": None,
                "respawn_max": None,
                "respawn_unit": None,
                "spawn_condition": s.get("conditions"),
                "event_id": None,
                "parent_mob_id": int(parent),
                "skill_id": s.get("skill_id"),
                "boss_flag": None,
                "script_path": s.get("source_file"),
                "script_line": s.get("source_line"),
                "classification_layer": "absolute",
                "provenance_id": _provenance_id(
                    "spawns", sid, f"{s.get('source_file')}:{s.get('source_line')}"
                ),
                "source": {
                    "form": "mob_skill_db",
                    "summon_id": s.get("summon_id"),
                    "skill_name": s.get("skill_name"),
                },
            }
            records.append(rec)
            by_type["slave"] = by_type.get("slave", 0) + 1
            by_kind["mob_skill_summon"] = by_kind.get("mob_skill_summon", 0) + 1
            slave_added += 1

    out_path = reports_dir / "spawns.jsonl"
    with out_path.open("w", encoding="utf-8") as f:
        for row in records:
            f.write(json.dumps(row, ensure_ascii=False, sort_keys=False) + "\n")

    summary = {
        "domain": "spawns",
        "spawn_count": len(records),
        "by_type": by_type,
        "by_kind": by_kind,
        "unique_mobs": len({r["mob_id"] for r in records if r.get("mob_id") is not None}),
        "unique_maps": len({r["map_id"] for r in records if r.get("map_id")}),
        "parse_fail": parse_fail,
        "scripted_skip_unresolved_mob": scripted_skip_no_mob,
        "scripted_partial_fields": scripted_partial,
        "scripted_with_npc_id": scripted_with_npc,
        "scripted_missing_npc_id": scripted_missing_npc,
        "slave_from_skills": slave_added,
        "note": (
            "scripted spawn_route=npc_script links enclosing npc_id when found; "
            "conditions out of scope"
        ),
        "wrote": str(out_path),
    }
    summary_path = reports_dir / "spawns_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    summary["summary_path"] = str(summary_path)
    return summary
