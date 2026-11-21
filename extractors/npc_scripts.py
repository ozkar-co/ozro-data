"""NPC script body analysis — refine functions + evidence inventory (Etapa 3)."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

import yaml

from discovery.scan import _load_extractor_config
from extractors.npcs import parse_npc_line

# rAthena script cmds are usually `cmd arg` (no parens); allow both styles.
def _cmd(*names: str) -> re.Pattern[str]:
    alt = "|".join(re.escape(n) for n in names)
    return re.compile(rf"\b(?:{alt})(?:\s*\(|\s+)")


# Evidence → function (only high-confidence script commands).
_EVIDENCE_RULES: list[tuple[str, re.Pattern[str], str]] = [
    ("Shop", _cmd("callshop", "npcshopitem", "npcshopadditem", "npcshopdelitem"), "shop_cmd"),
    ("Storage", _cmd("openstorage", "guildopenstorage", "openstoragex"), "storage_cmd"),
    ("Kafra", re.compile(r"\b(?:callfunc\s*\(\s*[\"']F_Kafra|callfunc\s+[\"']F_Kafra|F_Kafra|F_CashKafra|F_KafStorage)\b"), "kafra_func"),
    ("Healer", _cmd("percentheal", "fullheal"), "heal_cmd"),
    ("Repair", _cmd("repair", "repairitem", "repairall"), "repair_cmd"),
    ("Refine", _cmd("successrefitem", "failedrefitem", "getequiprefinerycnt"), "refine_cmd"),
    ("Enchant", _cmd("enchantitem", "enchantgrade", "successrandomoptitem"), "enchant_cmd"),
    ("Socket", _cmd("successremovecards", "failedremovecards"), "socket_cmd"),
    ("Instance", _cmd("instance_create", "instance_enter", "instance_destroy", "instance_npcname"), "instance_cmd"),
    ("Quest", _cmd("setquest", "completequest", "erasequest", "checkquest", "isbegin_quest", "changequest"), "quest_cmd"),
    ("Transport", _cmd("warp", "warpchar", "warpparty", "warpguild", "warppartner", "savepoint"), "warp_cmd"),
    ("Guild", _cmd("guildgetexp", "guildchangegm", "setcastledata"), "guild_cmd"),
]

_MOB_CMD_RE = re.compile(
    r"\b(?P<cmd>monster|areamonster|boss_monster|guardian)(?:\s*\(|\s+)",
    re.IGNORECASE,
)
_QUEST_ID_RE = re.compile(
    r"\b(?:setquest|completequest|erasequest|checkquest|isbegin_quest|changequest)"
    r"(?:\s*\(\s*|\s+)(?P<qid>\d+)",
)
_VAR_RE = re.compile(
    r"(?<![\w.])(?P<var>(?:\$\$|\$|#|@|\.'|'\.|'|\.)[A-Za-z_][\w]*)"
)

_SCRIPT_HEADER_RE = re.compile(
    r"^(?P<map>-|[A-Za-z0-9_@-]+),(?P<x>-?\d+),(?P<y>-?\d+),(?P<dir>\d+)\t"
    r"(?P<type>script)\t(?P<rest>.+)$"
)
_FLOAT_SCRIPT_RE = re.compile(r"^-\tscript\t(?P<rest>.+)$")


def _provenance_id(domain: str, record_id: str, source_path: str) -> str:
    raw = f"{domain}|{record_id}|{source_path}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def _evidence_id(*parts: Any) -> str:
    raw = "|".join("" if p is None else str(p) for p in parts)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def _extract_braced_body(text: str, open_idx: int) -> tuple[str, int] | None:
    """Return (body_inside_braces, end_index_exclusive) starting at '{'."""
    if open_idx < 0 or open_idx >= len(text) or text[open_idx] != "{":
        return None
    depth = 0
    i = open_idx
    while i < len(text):
        ch = text[i]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[open_idx + 1 : i], i + 1
        elif ch in "'\"":
            quote = ch
            i += 1
            while i < len(text) and text[i] != quote:
                if text[i] == "\\" and i + 1 < len(text):
                    i += 2
                    continue
                i += 1
        i += 1
    return None


def _strip_script_comments(body: str) -> str:
    out: list[str] = []
    for line in body.splitlines():
        # keep strings roughly; strip // comments outside quotes is hard — simple cut
        if "//" in line:
            in_str = False
            buf: list[str] = []
            j = 0
            while j < len(line):
                c = line[j]
                if c in "'\"":
                    in_str = not in_str
                    buf.append(c)
                elif c == "/" and not in_str and j + 1 < len(line) and line[j + 1] == "/":
                    break
                else:
                    buf.append(c)
                j += 1
            out.append("".join(buf))
        else:
            out.append(line)
    return "\n".join(out)


def analyze_script_body(body: str) -> dict[str, Any]:
    clean = _strip_script_comments(body)
    funcs: list[str] = []
    evidence: list[dict[str, str]] = []
    for fn, pat, kind in _EVIDENCE_RULES:
        if pat.search(clean):
            if fn not in funcs:
                funcs.append(fn)
            evidence.append({"kind": kind, "function": fn})

    quest_ids = sorted({int(m.group("qid")) for m in _QUEST_ID_RE.finditer(clean)})
    mob_cmds = sorted({m.group("cmd").lower() for m in _MOB_CMD_RE.finditer(clean)})

    def _var_scope(name: str) -> str:
        if name.startswith("$$"):
            return "server"
        if name.startswith("$@"):
            return "temp_server"
        if name.startswith("$"):
            return "permanent_char"
        if name.startswith("##"):
            return "account_global"
        if name.startswith("#"):
            return "account"
        if name.startswith(".@"):
            return "temp_npc"
        if name.startswith(".'"):
            return "npc_instance"
        if name.startswith("."):
            return "npc"
        if name.startswith("'"):
            return "instance"
        if name.startswith("@"):
            return "temp_char"
        return "unknown"

    vars_found: dict[str, str] = {}
    for m in _VAR_RE.finditer(clean):
        name = m.group("var")
        vars_found[name] = _var_scope(name)

    return {
        "functions": funcs,
        "evidence": evidence,
        "quest_ids": quest_ids,
        "mob_commands": mob_cmds,
        "variables": [
            {"name": n, "scope": s} for n, s in sorted(vars_found.items())[:80]
        ],
        "variable_count": len(vars_found),
    }


def _merge_functions(existing: list[str], discovered: list[str]) -> list[str]:
    out: list[str] = []
    for fn in existing:
        if fn == "pending":
            continue
        if fn not in out:
            out.append(fn)
    for fn in discovered:
        if fn not in out:
            out.append(fn)
    return out or ["pending"]


def extract_npc_scripts(project_root: Path | None = None) -> dict[str, Any]:
    root = project_root or Path(__file__).resolve().parents[1]
    cfg = _load_extractor_config(root)
    rathena = Path(cfg["paths"]["rathena"])
    reports_dir = root / cfg["output"]["reports_dir"]
    reports_dir.mkdir(parents=True, exist_ok=True)

    npcs_path = reports_dir / "npcs.jsonl"
    if not npcs_path.is_file():
        raise FileNotFoundError("reports/npcs.jsonl missing; run: extract npcs")

    files_path = reports_dir / "discovery_files.yml"
    disc = yaml.safe_load(files_path.read_text(encoding="utf-8"))
    scripts: list[str] = list(disc.get("scripts") or [])

    # Index NPCs by (script_path, script_line) for updates
    npcs: list[dict[str, Any]] = []
    by_loc: dict[tuple[str, int], int] = {}
    by_unique: dict[str, list[int]] = {}
    for i, line in enumerate(npcs_path.read_text(encoding="utf-8").splitlines()):
        if not line.strip():
            continue
        rec = json.loads(line)
        by_loc[(rec["script_path"], int(rec["script_line"]))] = len(npcs)
        npcs.append(rec)
        uid = rec.get("name")
        if uid:
            by_unique.setdefault(str(uid), []).append(len(npcs) - 1)

    evidence_rows: list[dict[str, Any]] = []
    analyzed = 0
    refined = 0
    still_pending = 0
    no_body = 0

    for rel in scripts:
        path = rathena / rel
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        lines = text.splitlines()
        # Build absolute char offsets per line start
        starts: list[int] = []
        pos = 0
        for ln in lines:
            starts.append(pos)
            pos += len(ln) + 1

        for line_no, raw in enumerate(lines, 1):
            line = raw.split("//", 1)[0].rstrip()
            if "\tscript\t" not in line:
                continue
            if not (_SCRIPT_HEADER_RE.match(line) or _FLOAT_SCRIPT_RE.match(line)):
                continue
            # Find '{' on this line or following lines
            abs_start = starts[line_no - 1]
            brace_rel = line.find("{")
            if brace_rel >= 0:
                open_idx = abs_start + brace_rel
            else:
                # search forward in file text
                open_idx = text.find("{", abs_start + len(raw))
                if open_idx < 0:
                    no_body += 1
                    continue
                # ensure no other NPC header between
                between = text[abs_start : open_idx]
                if "\tscript\t" in between.split("\n", 1)[-1] and between.count("\n") > 0:
                    # ok if only whitespace lines
                    pass

            extracted = _extract_braced_body(text, open_idx)
            if not extracted:
                no_body += 1
                continue
            body, _end = extracted
            analyzed += 1
            info = analyze_script_body(body)

            idx = by_loc.get((rel, line_no))
            if idx is None:
                # header parse mismatch — try parse_npc_line for id only
                rec = parse_npc_line(line, rel, line_no)
                if not rec:
                    continue
                npc_id = rec["npc_id"]
            else:
                npc_id = npcs[idx]["npc_id"]
                before = list(npcs[idx].get("functions") or [])
                after = _merge_functions(before, info["functions"])
                if after != before:
                    refined += 1
                npcs[idx]["functions"] = after
                npcs[idx]["classification_layer"] = (
                    "absolute" if after != ["pending"] else "pending"
                )
                npcs[idx]["script_analysis"] = {
                    "quest_ids": info["quest_ids"],
                    "mob_commands": info["mob_commands"],
                    "variable_count": info["variable_count"],
                    "evidence": info["evidence"],
                }

            eid = _evidence_id("npc_script", npc_id, rel, line_no)
            evidence_rows.append(
                {
                    "evidence_id": eid,
                    "npc_id": npc_id,
                    "script_path": rel,
                    "script_line": line_no,
                    "functions": info["functions"],
                    "quest_ids": info["quest_ids"],
                    "mob_commands": info["mob_commands"],
                    "variables": info["variables"],
                    "variable_count": info["variable_count"],
                    "evidence": info["evidence"],
                    "provenance_id": _provenance_id(
                        "npc_scripts", eid, f"{rel}:{line_no}"
                    ),
                }
            )

    # Propagate functions to duplicates from source unique name
    dup_filled = 0
    for rec in npcs:
        if rec.get("npc_type") != "duplicate":
            continue
        src = rec.get("duplicate_of")
        if not src:
            continue
        src_idxs = by_unique.get(str(src)) or []
        if not src_idxs:
            continue
        src_funcs = list(npcs[src_idxs[0]].get("functions") or [])
        if not src_funcs or src_funcs == ["pending"]:
            continue
        before = list(rec.get("functions") or [])
        after = _merge_functions(before, src_funcs)
        if after != before:
            rec["functions"] = after
            rec["classification_layer"] = (
                "absolute" if after != ["pending"] else "pending"
            )
            dup_filled += 1

    for rec in npcs:
        if rec.get("functions") == ["pending"]:
            still_pending += 1

    with npcs_path.open("w", encoding="utf-8") as f:
        for row in npcs:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    ev_path = reports_dir / "npc_script_evidence.jsonl"
    with ev_path.open("w", encoding="utf-8") as f:
        for row in evidence_rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    func_counts: dict[str, int] = {}
    for r in npcs:
        for fn in r.get("functions") or []:
            func_counts[fn] = func_counts.get(fn, 0) + 1

    summary = {
        "domain": "npc_scripts",
        "npc_count": len(npcs),
        "scripts_analyzed": analyzed,
        "functions_refined": refined,
        "duplicates_filled": dup_filled,
        "still_pending": still_pending,
        "no_body": no_body,
        "evidence_rows": len(evidence_rows),
        "function_counts": func_counts,
        "deferred": [
            "full_variable_read_write_split",
            "resolved_monster_ids_in_scripts",
            "barter_db",
        ],
        "wrote": [str(npcs_path), str(ev_path)],
    }
    summary_path = reports_dir / "npc_scripts_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    summary["summary_path"] = str(summary_path)
    return summary
