"""Spawns extractor — permanent monster/boss_monster headers from enabled scripts."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

import yaml

from discovery.scan import _load_extractor_config

# map[,x,y[,xs,ys]] <TAB> monster|boss_monster <TAB> Name <TAB> id,amount[,...]
_SPAWN_RE = re.compile(
    r"^(?P<loc>[A-Za-z0-9_@-]+(?:,-?\d+,-?\d+(?:,-?\d+,-?\d+)?)?)\t"
    r"(?P<kind>monster|boss_monster)\t"
    r"(?P<name>[^\t]+)\t"
    r"\s*(?P<body>.+)$"
)

_EVENT_RE = re.compile(r'^"(?P<event>[^"]*)"\s*$')


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
            # strip block comments at EOL
            if "/*" in line:
                line = re.sub(r"/\*.*?\*/", "", line).rstrip()
            m = _SPAWN_RE.match(line)
            if not m:
                continue
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
                "source": {"script_path": rel, "line": line_no},
            }
            records.append(rec)
            by_type[stype] = by_type.get(stype, 0) + 1
            by_kind[kind] = by_kind.get(kind, 0) + 1

    out_path = reports_dir / "spawns.jsonl"
    with out_path.open("w", encoding="utf-8") as f:
        for row in records:
            f.write(json.dumps(row, ensure_ascii=False, sort_keys=False) + "\n")

    summary = {
        "domain": "spawns",
        "spawn_count": len(records),
        "by_type": by_type,
        "by_kind": by_kind,
        "unique_mobs": len({r["mob_id"] for r in records}),
        "unique_maps": len({r["map_id"] for r in records}),
        "parse_fail": parse_fail,
        "deferred": ["scripted", "skill_summon", "pet", "timed", "one_time"],
        "wrote": str(out_path),
    }
    summary_path = reports_dir / "spawns_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    summary["summary_path"] = str(summary_path)
    return summary
