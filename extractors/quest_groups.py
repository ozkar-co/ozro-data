"""Quest groups — high-precision clusters from script transitions + title runs.

Reasons (prefer false negatives over false positives):

Quest↔quest (merge into a group):
  - script_transition  changequest / erasequest+setquest / completequest+setquest
  - same_title_contig  consecutive quest_ids with the same normalized title

NPC↔group:
  - same_id    NPC script mentions a member quest_id (from npc_quest_links)
  - same_file  NPC (npc_type=script) shares script_path with a same_id NPC of the
               group; every quest_id linked from that file belongs to this group;
               path is not under /warps/; and same_id script density on the path
               is high enough (anti-FP vs city warp packs / huge job arenas)
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter, defaultdict, deque
from pathlib import Path
from typing import Any

import yaml

from discovery.scan import _load_extractor_config

_QUEST_EDGE_PRIORITY = ("script_transition", "same_title_contig")
_NPC_REASON_PRIORITY = ("same_id", "same_file")
# same_file: require enough quest-touching scripts on the path (prefer FN).
_SAME_FILE_MIN_SCRIPT_DENSITY = 0.25

_CHANGE = re.compile(
    r"\bchangequest(?:\s*\(\s*|\s+)(\d+)\s*,\s*(\d+)",
    re.IGNORECASE,
)
_ERASE_SET = re.compile(
    r"erasequest\s*\(?\s*(\d+)\s*\)?\s*;\s*setquest\s*\(?\s*(\d+)",
    re.IGNORECASE | re.DOTALL,
)
_COMPLETE_SET = re.compile(
    r"completequest\s*\(?\s*(\d+)\s*\)?\s*;\s*setquest\s*\(?\s*(\d+)",
    re.IGNORECASE | re.DOTALL,
)


def _provenance_id(domain: str, record_id: str, source_path: str) -> str:
    raw = f"{domain}|{record_id}|{source_path}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def _eid(*parts: Any) -> str:
    raw = "|".join("" if p is None else str(p) for p in parts)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def _norm_title(title: str | None) -> str:
    if not title:
        return ""
    return " ".join(str(title).casefold().split())


def _strip_line_comments(text: str) -> str:
    out: list[str] = []
    for line in text.splitlines():
        if "//" not in line:
            out.append(line)
            continue
        in_str = False
        buf: list[str] = []
        j = 0
        while j < len(line):
            c = line[j]
            if c in "'\"":
                in_str = not in_str
                buf.append(c)
            elif (
                c == "/"
                and not in_str
                and j + 1 < len(line)
                and line[j + 1] == "/"
            ):
                break
            else:
                buf.append(c)
            j += 1
        out.append("".join(buf))
    return "\n".join(out)


def _sort_reasons(reasons: set[str], priority: tuple[str, ...]) -> list[str]:
    rank = {r: i for i, r in enumerate(priority)}
    return sorted(reasons, key=lambda r: (rank.get(r, 99), r))


def _scan_transitions(rathena: Path, script_rels: list[str]) -> list[dict[str, Any]]:
    """Directed quest transitions with source location."""
    rows: list[dict[str, Any]] = []
    seen: set[tuple[int, int, str, str]] = set()
    for rel in script_rels:
        path = rathena / rel
        if not path.is_file():
            continue
        raw = path.read_text(encoding="utf-8", errors="replace")
        clean = _strip_line_comments(raw)
        for kind, pat in (
            ("changequest", _CHANGE),
            ("erase_set", _ERASE_SET),
            ("complete_set", _COMPLETE_SET),
        ):
            for m in pat.finditer(clean):
                a, b = int(m.group(1)), int(m.group(2))
                if a == b:
                    continue
                # Approximate line from match start in cleaned text (good enough).
                line = clean.count("\n", 0, m.start()) + 1
                key = (a, b, kind, rel)
                if key in seen:
                    continue
                seen.add(key)
                rows.append(
                    {
                        "from_quest_id": a,
                        "to_quest_id": b,
                        "transition_kind": kind,
                        "script_path": rel,
                        "script_line": line,
                    }
                )
    return rows


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def extract_quest_groups(project_root: Path | None = None) -> dict[str, Any]:
    root = project_root or Path(__file__).resolve().parents[1]
    cfg = _load_extractor_config(root)
    rathena = Path(cfg["paths"]["rathena"])
    reports_dir = root / cfg["output"]["reports_dir"]
    reports_dir.mkdir(parents=True, exist_ok=True)

    quests_path = reports_dir / "quests.jsonl"
    if not quests_path.is_file():
        raise FileNotFoundError("reports/quests.jsonl missing; run: extract quests")

    quests = _load_jsonl(quests_path)
    by_id: dict[int, dict[str, Any]] = {
        int(q["quest_id"]): q for q in quests if q.get("quest_id") is not None
    }

    disc_path = reports_dir / "discovery_files.yml"
    script_rels: list[str] = []
    if disc_path.is_file():
        disc = yaml.safe_load(disc_path.read_text(encoding="utf-8")) or {}
        script_rels = list(disc.get("scripts") or [])

    transitions = _scan_transitions(rathena, script_rels)

    # --- merge graph: script_transition + same_title_contig ---
    graph: dict[int, set[int]] = defaultdict(set)
    edge_reasons: dict[tuple[int, int], set[str]] = defaultdict(set)
    edge_transitions: dict[tuple[int, int], list[dict[str, Any]]] = defaultdict(list)

    for tr in transitions:
        a, b = int(tr["from_quest_id"]), int(tr["to_quest_id"])
        if a not in by_id and b not in by_id:
            # keep edges even if one side missing from quest_db (orphan script id)
            pass
        graph[a].add(b)
        graph[b].add(a)
        lo, hi = (a, b) if a < b else (b, a)
        edge_reasons[(lo, hi)].add("script_transition")
        edge_transitions[(lo, hi)].append(
            {
                "from_quest_id": a,
                "to_quest_id": b,
                "transition_kind": tr["transition_kind"],
                "script_path": tr["script_path"],
                "script_line": tr["script_line"],
            }
        )

    # Contiguous runs by normalized title (case/whitespace insensitive).
    sorted_ids = sorted(by_id)
    i = 0
    contig_runs = 0
    while i < len(sorted_ids):
        qid = sorted_ids[i]
        norm = _norm_title(by_id[qid].get("title"))
        j = i + 1
        if not norm:
            i = j
            continue
        while j < len(sorted_ids):
            nxt = sorted_ids[j]
            if nxt != sorted_ids[j - 1] + 1:
                break
            if _norm_title(by_id[nxt].get("title")) != norm:
                break
            j += 1
        if j - i >= 2:
            contig_runs += 1
            run = sorted_ids[i:j]
            for k in range(len(run) - 1):
                a, b = run[k], run[k + 1]
                graph[a].add(b)
                graph[b].add(a)
                edge_reasons[(a, b)].add("same_title_contig")
        i = j

    npc_links = _load_jsonl(reports_dir / "npc_quest_links.jsonl")
    linked_quest_ids = {
        int(L["quest_id"])
        for L in npc_links
        if L.get("quest_id") is not None
    }

    # Connected components from merge graph.
    visited: set[int] = set()
    components: list[list[int]] = []
    for node in list(graph):
        if node in visited:
            continue
        q: deque[int] = deque([node])
        visited.add(node)
        comp: list[int] = []
        while q:
            u = q.popleft()
            comp.append(u)
            for v in graph[u]:
                if v not in visited:
                    visited.add(v)
                    q.append(v)
        components.append(sorted(comp))

    # Singletons for quests that have NPC links but no merge edges.
    for qid in sorted(linked_quest_ids):
        if qid not in visited:
            components.append([qid])
            visited.add(qid)

    components.sort(key=lambda c: (c[0], len(c)))

    quest_to_group: dict[int, str] = {}
    groups_out: list[dict[str, Any]] = []
    members_out: list[dict[str, Any]] = []
    edges_out: list[dict[str, Any]] = []

    for members in components:
        # Drop components with no quest_db member and no linked id (pure orphans).
        known = [q for q in members if q in by_id or q in linked_quest_ids]
        if not known:
            continue
        members = sorted(set(members))
        group_id = f"qg_{members[0]}"
        for qid in members:
            quest_to_group[qid] = group_id

        title_votes = Counter()
        for qid in members:
            raw = (by_id.get(qid) or {}).get("title")
            if raw:
                title_votes[str(raw)] += 1
        if title_votes:
            # Prefer most common; tie-break by earliest quest_id bearing that title.
            best_count = max(title_votes.values())
            candidates = [t for t, n in title_votes.items() if n == best_count]
            display_title = None
            for qid in members:
                t = (by_id.get(qid) or {}).get("title")
                if t and str(t) in candidates:
                    display_title = str(t)
                    break
            if display_title is None:
                display_title = candidates[0]
        else:
            display_title = None

        member_set = set(members)
        group_reason_set: set[str] = set()
        for (a, b), reasons in edge_reasons.items():
            if a in member_set and b in member_set:
                group_reason_set |= reasons

        merge_reasons = _sort_reasons(group_reason_set, _QUEST_EDGE_PRIORITY)
        groups_out.append(
            {
                "group_id": group_id,
                "display_title": display_title,
                "member_count": len(members),
                "merge_reasons": merge_reasons,
                "primary_merge_reason": merge_reasons[0] if merge_reasons else None,
                "provenance_id": _provenance_id(
                    "quest_groups", group_id, "quest_groups"
                ),
            }
        )

        for idx, qid in enumerate(members):
            members_out.append(
                {
                    "group_id": group_id,
                    "quest_id": qid,
                    "sort_index": idx,
                    "title": (by_id.get(qid) or {}).get("title"),
                    "in_quest_db": qid in by_id,
                    "provenance_id": _provenance_id(
                        "quest_group_members",
                        f"{group_id}|{qid}",
                        "quest_groups",
                    ),
                }
            )

        for (a, b), reasons in sorted(edge_reasons.items()):
            if a not in member_set or b not in member_set:
                continue
            ordered = _sort_reasons(reasons, _QUEST_EDGE_PRIORITY)
            edge_id = _eid("qge", group_id, a, b)
            edges_out.append(
                {
                    "edge_id": edge_id,
                    "group_id": group_id,
                    "from_quest_id": a,
                    "to_quest_id": b,
                    "reasons": ordered,
                    "primary_reason": ordered[0],
                    "transitions": edge_transitions.get((a, b)) or [],
                    "provenance_id": _provenance_id(
                        "quest_group_edges", edge_id, "quest_groups"
                    ),
                }
            )

    # --- NPC attachments ---
    npcs = _load_jsonl(reports_dir / "npcs.jsonl")
    npc_by_id = {n["npc_id"]: n for n in npcs if n.get("npc_id")}

    # quest_ids linked per script_path (from npc_quest_links)
    quests_by_path: dict[str, set[int]] = defaultdict(set)
    same_id_by_group: dict[str, set[str]] = defaultdict(set)
    # npc -> reasons accumulator
    npc_group_reasons: dict[tuple[str, str], set[str]] = defaultdict(set)
    npc_group_meta: dict[tuple[str, str], dict[str, Any]] = {}

    for L in npc_links:
        qid = L.get("quest_id")
        npc_id = L.get("npc_id")
        if qid is None or not npc_id:
            continue
        qid = int(qid)
        group_id = quest_to_group.get(qid)
        if not group_id:
            continue
        path = L.get("script_path") or (npc_by_id.get(npc_id) or {}).get("script_path")
        if path:
            quests_by_path[str(path)].add(qid)
        key = (group_id, str(npc_id))
        npc_group_reasons[key].add("same_id")
        same_id_by_group[group_id].add(str(npc_id))
        meta = npc_group_meta.setdefault(
            key,
            {
                "script_path": path,
                "script_line": L.get("script_line")
                or (npc_by_id.get(npc_id) or {}).get("script_line"),
            },
        )
        if path and not meta.get("script_path"):
            meta["script_path"] = path

    # Paths that are exclusive to one group (all linked quest_ids map to that group).
    exclusive_path_group: dict[str, str] = {}
    for path, qids in quests_by_path.items():
        groups = {quest_to_group[q] for q in qids if q in quest_to_group}
        if len(groups) == 1:
            exclusive_path_group[path] = next(iter(groups))

    # Per-path script NPC counts for density gate.
    script_npcs_by_path: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for npc in npcs:
        path = npc.get("script_path")
        if not path or npc.get("npc_type") != "script":
            continue
        script_npcs_by_path[str(path)].append(npc)

    def _path_allows_same_file(path: str, group_id: str) -> bool:
        if "/warps/" in path.replace("\\", "/"):
            return False
        scripts = script_npcs_by_path.get(path) or []
        if not scripts:
            return False
        same_id_scripts = 0
        for n in scripts:
            nid = str(n.get("npc_id"))
            if "same_id" in npc_group_reasons.get((group_id, nid), set()):
                same_id_scripts += 1
        if same_id_scripts < 1:
            return False
        return (same_id_scripts / len(scripts)) >= _SAME_FILE_MIN_SCRIPT_DENSITY

    # same_file: script NPCs on a dense exclusive path, not already same_id
    for path, group_id in exclusive_path_group.items():
        if not _path_allows_same_file(path, group_id):
            continue
        for npc in script_npcs_by_path.get(path) or []:
            npc_id = str(npc.get("npc_id"))
            key = (group_id, npc_id)
            if "same_id" in npc_group_reasons.get(key, set()):
                continue
            npc_group_reasons[key].add("same_file")
            npc_group_meta.setdefault(
                key,
                {
                    "script_path": path,
                    "script_line": npc.get("script_line"),
                },
            )

    npcs_out: list[dict[str, Any]] = []
    for (group_id, npc_id), reasons in sorted(npc_group_reasons.items()):
        ordered = _sort_reasons(reasons, _NPC_REASON_PRIORITY)
        meta = npc_group_meta.get((group_id, npc_id)) or {}
        link_id = _eid("qgn", group_id, npc_id)
        npcs_out.append(
            {
                "link_id": link_id,
                "group_id": group_id,
                "npc_id": npc_id,
                "reasons": ordered,
                "primary_reason": ordered[0],
                "script_path": meta.get("script_path"),
                "script_line": meta.get("script_line"),
                "provenance_id": _provenance_id(
                    "quest_group_npcs", link_id, "quest_groups"
                ),
            }
        )

    # Write JSONL
    g_path = reports_dir / "quest_groups.jsonl"
    m_path = reports_dir / "quest_group_members.jsonl"
    e_path = reports_dir / "quest_group_edges.jsonl"
    n_path = reports_dir / "quest_group_npcs.jsonl"
    with g_path.open("w", encoding="utf-8") as f:
        for row in groups_out:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    with m_path.open("w", encoding="utf-8") as f:
        for row in members_out:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    with e_path.open("w", encoding="utf-8") as f:
        for row in edges_out:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    with n_path.open("w", encoding="utf-8") as f:
        for row in npcs_out:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    multi = sum(1 for g in groups_out if g["member_count"] > 1)
    summary = {
        "domain": "quest_groups",
        "group_count": len(groups_out),
        "multi_member_groups": multi,
        "singleton_groups": len(groups_out) - multi,
        "member_rows": len(members_out),
        "edge_rows": len(edges_out),
        "npc_link_rows": len(npcs_out),
        "npc_same_id": sum(1 for r in npcs_out if "same_id" in (r.get("reasons") or [])),
        "npc_same_file_only": sum(
            1
            for r in npcs_out
            if (r.get("reasons") or []) == ["same_file"]
        ),
        "transition_rows_scanned": len(transitions),
        "contig_runs": contig_runs,
        "exclusive_script_paths": len(exclusive_path_group),
        "wrote": [str(g_path), str(m_path), str(e_path), str(n_path)],
    }
    summary_path = reports_dir / "quest_groups_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    summary["summary_path"] = str(summary_path)
    return summary
