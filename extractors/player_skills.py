"""Player skill catalog from skill_db.yml + platinum teachers from NPC scripts."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

_SKILL_HEADER = re.compile(r"^  - Id: (\d+)\s*$")
_FIELD = re.compile(r"^    ([A-Za-z0-9_]+):\s*(.*?)\s*$")
_FLAG = re.compile(r"^      ([A-Za-z0-9_]+):\s*(.*?)\s*$")
_ITEM_COST_ITEM = re.compile(r"^        - Item:\s*(\S+)\s*$")
_ITEM_COST_AMOUNT = re.compile(r"^          Amount:\s*(-?\d+)\s*$")
_ITEM_COST_LEVEL = re.compile(r"^          Level:\s*(-?\d+)\s*$")

_PLATINUM_FN = re.compile(
    r"function\tscript\tF_GetPlatinumSkills\t\{(.*?)\n\}",
    re.S,
)
_SKILL_PERM = re.compile(
    r"""\bskill\s*\(\s*["']([A-Za-z0-9_]+)["']\s*,\s*(-?\d+)\s*,\s*SKILL_PERM"""
    r"""|\bskill\s+["']([A-Za-z0-9_]+)["']\s*,\s*(-?\d+)\s*,\s*SKILL_PERM""",
)
_CALL_PLATINUM = re.compile(
    r"""\bcallfunc\s*(?:\(\s*)?["']F_GetPlatinumSkills["']""",
    re.I,
)
_SCRIPT_HEADER = re.compile(
    r"^(?P<map>-|[A-Za-z0-9_@-]+),(?P<x>-?\d+),(?P<y>-?\d+),(?P<dir>\d+)\t"
    r"(?P<type>script)\t(?P<rest>.+)$"
)


def _provenance_id(domain: str, record_id: str, source_path: str) -> str:
    raw = f"{domain}|{record_id}|{source_path}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def _row_id(*parts: Any) -> str:
    raw = "|".join("" if p is None else str(p) for p in parts)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def _parse_bool(raw: str) -> bool | None:
    v = raw.strip().lower()
    if v in {"true", "yes", "1"}:
        return True
    if v in {"false", "no", "0"}:
        return False
    return None


def _aegis_prefix(aegis: str | None) -> str | None:
    if not aegis or "_" not in aegis:
        return None
    prefix = aegis.split("_", 1)[0].strip()
    return prefix or None


def parse_platinum_skill_names(rathena: Path) -> list[str]:
    """Canonical platinum grant list from F_GetPlatinumSkills."""
    path = rathena / "npc/other/Global_Functions.txt"
    if not path.is_file():
        return []
    text = path.read_text(encoding="utf-8", errors="replace")
    m = _PLATINUM_FN.search(text)
    if not m:
        return []
    names = sorted(set(re.findall(r'skill\s+"([A-Z0-9_]+)"', m.group(1))))
    return names


def iter_skill_db_entries(path: Path, *, source_file: str) -> list[dict[str, Any]]:
    """Line-scan skill_db.yml into flat skill records + item costs."""
    if not path.is_file():
        return []

    entries: list[dict[str, Any]] = []
    cur: dict[str, Any] | None = None
    section: str | None = None  # flags | requires | item_cost
    cost: dict[str, Any] | None = None

    def flush_cost() -> None:
        nonlocal cost
        if cur is None or cost is None:
            cost = None
            return
        item = cost.get("item")
        if item:
            cur.setdefault("item_costs", []).append(
                {
                    "item_aegis_name": item,
                    "amount": cost.get("amount"),
                    "level": cost.get("level"),
                }
            )
        cost = None

    def flush() -> None:
        nonlocal cur, section, cost
        flush_cost()
        if cur and cur.get("skill_id") is not None:
            entries.append(cur)
        cur = None
        section = None
        cost = None

    for line_no, raw in enumerate(
        path.read_text(encoding="utf-8", errors="replace").splitlines(), 1
    ):
        m = _SKILL_HEADER.match(raw)
        if m:
            flush()
            cur = {
                "skill_id": int(m.group(1)),
                "aegis_name": None,
                "description": None,
                "max_level": None,
                "skill_type": None,
                "target_type": None,
                "is_quest": False,
                "flags": {},
                "item_costs": [],
                "source_file": source_file,
                "source_line": line_no,
            }
            section = None
            continue

        if cur is None:
            continue

        if raw.startswith("      ItemCost:"):
            flush_cost()
            section = "item_cost"
            continue

        if section == "item_cost":
            m = _ITEM_COST_ITEM.match(raw)
            if m:
                flush_cost()
                cost = {"item": m.group(1), "amount": None, "level": None}
                continue
            m = _ITEM_COST_AMOUNT.match(raw)
            if m and cost is not None:
                cost["amount"] = int(m.group(1))
                continue
            m = _ITEM_COST_LEVEL.match(raw)
            if m and cost is not None:
                cost["level"] = int(m.group(1))
                continue
            if raw.startswith("      ") or raw.startswith("        "):
                # other requires subfield ends ItemCost list items
                if raw.startswith("      ") and not raw.startswith("        "):
                    flush_cost()
                    section = "requires"
                continue
            if raw.startswith("    ") and not raw.startswith("      "):
                flush_cost()
                section = None
            # fall through to field parse

        if raw.startswith("    Flags:"):
            flush_cost()
            section = "flags"
            continue
        if raw.startswith("    Requires:"):
            flush_cost()
            section = "requires"
            continue

        if section == "flags":
            m = _FLAG.match(raw)
            if m:
                key, val = m.group(1), m.group(2)
                b = _parse_bool(val)
                cur["flags"][key] = b if b is not None else val
                if key == "IsQuest" and b is True:
                    cur["is_quest"] = True
                continue
            if raw.startswith("    ") and not raw.startswith("      "):
                section = None
            else:
                continue

        m = _FIELD.match(raw)
        if not m:
            continue
        key, val = m.group(1), m.group(2)
        section = None
        if key == "Name":
            cur["aegis_name"] = val or None
        elif key == "Description":
            cur["description"] = val or None
        elif key == "MaxLevel":
            try:
                cur["max_level"] = int(val)
            except ValueError:
                pass
        elif key == "Type":
            cur["skill_type"] = val or None
        elif key == "TargetType":
            cur["target_type"] = val or None

    flush()
    return entries


def merge_skill_entries(base: list[dict[str, Any]], overrides: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_id = {e["skill_id"]: e for e in base}
    for ov in overrides:
        sid = ov["skill_id"]
        if sid not in by_id:
            by_id[sid] = ov
            continue
        dst = by_id[sid]
        for key in (
            "aegis_name",
            "description",
            "max_level",
            "skill_type",
            "target_type",
            "is_quest",
            "flags",
            "item_costs",
            "source_file",
            "source_line",
        ):
            if key in ov and ov[key] not in (None, {}, []):
                dst[key] = ov[key]
    return [by_id[k] for k in sorted(by_id)]


def build_skill_records(
    entries: list[dict[str, Any]],
    platinum_names: set[str],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    skills: list[dict[str, Any]] = []
    costs: list[dict[str, Any]] = []
    for e in entries:
        sid = e["skill_id"]
        aegis = e.get("aegis_name")
        is_platinum = bool(aegis and aegis in platinum_names)
        skills.append(
            {
                "skill_id": sid,
                "aegis_name": aegis,
                "aegis_prefix": _aegis_prefix(aegis),
                "description": e.get("description"),
                "max_level": e.get("max_level"),
                "skill_type": e.get("skill_type"),
                "target_type": e.get("target_type"),
                "is_quest": bool(e.get("is_quest")),
                "is_platinum": is_platinum,
                "flags": e.get("flags") or {},
                "source_file": e.get("source_file"),
                "source_line": e.get("source_line"),
                "provenance_id": _provenance_id(
                    "skills",
                    str(sid),
                    f"{e.get('source_file')}:{e.get('source_line')}",
                ),
            }
        )
        for idx, cost in enumerate(e.get("item_costs") or []):
            cid = _row_id(
                "skill_item_cost",
                sid,
                cost.get("item_aegis_name"),
                cost.get("amount"),
                cost.get("level"),
                idx,
            )
            costs.append(
                {
                    "skill_item_cost_id": cid,
                    "skill_id": sid,
                    "skill_aegis_name": aegis,
                    "item_aegis_name": cost.get("item_aegis_name"),
                    "amount": cost.get("amount"),
                    "level": cost.get("level"),
                    "provenance_id": _provenance_id(
                        "skill_item_costs",
                        cid,
                        f"{e.get('source_file')}:{e.get('source_line')}",
                    ),
                }
            )
    return skills, costs


def load_npc_index(reports_dir: Path) -> dict[tuple[str, int], str]:
    """(script_path, script_line) → npc_id from npcs.jsonl when available."""
    path = reports_dir / "npcs.jsonl"
    out: dict[tuple[str, int], str] = {}
    if not path.is_file():
        return out
    for line in path.open(encoding="utf-8"):
        if not line.strip():
            continue
        row = json.loads(line)
        sp = row.get("script_path")
        sl = row.get("script_line")
        nid = row.get("npc_id")
        if sp and sl is not None and nid:
            out[(str(sp), int(sl))] = str(nid)
    return out


def _active_npc_header(lines: list[str], at_line: int) -> tuple[int, re.Match[str]] | None:
    """Nearest script header above at_line (1-indexed)."""
    for i in range(at_line - 1, -1, -1):
        m = _SCRIPT_HEADER.match(lines[i])
        if m:
            return i + 1, m
    return None


def extract_skill_teachers(
    rathena: Path,
    script_rels: list[str],
    *,
    platinum_names: set[str],
    aegis_to_id: dict[str, int],
    npc_index: dict[tuple[str, int], str],
) -> list[dict[str, Any]]:
    teachers: list[dict[str, Any]] = []
    seen: set[str] = set()

    def add(
        *,
        grant_kind: str,
        skill_id: int | None,
        skill_aegis: str | None,
        script_path: str,
        script_line: int,
        npc_id: str | None,
        npc_display: str | None,
        map_id: str | None,
        x: int | None,
        y: int | None,
    ) -> None:
        tid = _row_id(
            "skill_teacher",
            grant_kind,
            skill_id,
            skill_aegis,
            script_path,
            script_line,
        )
        if tid in seen:
            return
        seen.add(tid)
        teachers.append(
            {
                "skill_teacher_id": tid,
                "grant_kind": grant_kind,
                "skill_id": skill_id,
                "skill_aegis_name": skill_aegis,
                "npc_id": npc_id,
                "npc_display_name": npc_display,
                "map_id": map_id,
                "x": x,
                "y": y,
                "script_path": script_path,
                "script_line": script_line,
                "provenance_id": _provenance_id(
                    "skill_teachers", tid, f"{script_path}:{script_line}"
                ),
            }
        )

    for rel in script_rels:
        path = rathena / rel
        if not path.is_file():
            continue
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        text = "\n".join(lines)

        for m in _CALL_PLATINUM.finditer(text):
            # line number of match
            line_no = text[: m.start()].count("\n") + 1
            hdr = _active_npc_header(lines, line_no)
            map_id = x = y = npc_display = npc_id = None
            header_line = line_no
            if hdr:
                header_line, hm = hdr
                map_id = hm.group("map")
                x = int(hm.group("x"))
                y = int(hm.group("y"))
                rest = hm.group("rest")
                # Name#Unique,{ or Name,{
                npc_display = rest.split("#", 1)[0].split(",", 1)[0].strip() or None
                npc_id = npc_index.get((rel, header_line))
            add(
                grant_kind="f_get_platinum",
                skill_id=None,
                skill_aegis=None,
                script_path=rel,
                script_line=line_no,
                npc_id=npc_id,
                npc_display=npc_display,
                map_id=None if map_id == "-" else map_id,
                x=x,
                y=y,
            )

        for m in _SKILL_PERM.finditer(text):
            aegis = m.group(1) or m.group(3)
            if not aegis or aegis not in platinum_names:
                continue
            line_no = text[: m.start()].count("\n") + 1
            hdr = _active_npc_header(lines, line_no)
            map_id = x = y = npc_display = npc_id = None
            if hdr:
                header_line, hm = hdr
                map_id = hm.group("map")
                x = int(hm.group("x"))
                y = int(hm.group("y"))
                rest = hm.group("rest")
                npc_display = rest.split("#", 1)[0].split(",", 1)[0].strip() or None
                npc_id = npc_index.get((rel, header_line))
            add(
                grant_kind="skill_perm",
                skill_id=aegis_to_id.get(aegis),
                skill_aegis=aegis,
                script_path=rel,
                script_line=line_no,
                npc_id=npc_id,
                npc_display=npc_display,
                map_id=None if map_id == "-" else map_id,
                x=x,
                y=y,
            )

    teachers.sort(
        key=lambda r: (
            r.get("script_path") or "",
            r.get("script_line") or 0,
            r.get("skill_aegis_name") or "",
        )
    )
    return teachers
