"""All-pairs Dijkstra over map connections (friction graph)."""

from __future__ import annotations

import heapq
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from discovery.scan import _load_extractor_config

GRAPH_TYPES = frozenset({"warp", "kafra", "custom_npc_tp", "airship", "boat"})

# Tie-break when friction equal: prefer convenience services.
_TYPE_RANK = {
    "kafra": 0,
    "custom_npc_tp": 1,
    "boat": 2,
    "airship": 3,
    "warp": 4,
}


def _is_quest_gated(row: dict[str, Any]) -> bool:
    cond = row.get("conditions")
    return isinstance(cond, dict) and bool(cond.get("quest_gated"))


def _build_graph(
    connections: list[dict[str, Any]],
) -> tuple[dict[str, list[tuple[str, float, str, str]]], dict[str, Any]]:
    """Collapse to one edge per (from, to): min friction, stable tie-break.

    Returns adjacency: from -> [(to, weight, connection_id, connection_type), ...]
    """
    best: dict[tuple[str, str], tuple[float, int, str, str]] = {}
    skipped_quest = 0
    skipped_type = 0
    skipped_weight = 0

    for row in connections:
        ctype = row.get("connection_type")
        if ctype not in GRAPH_TYPES:
            skipped_type += 1
            continue
        if _is_quest_gated(row):
            skipped_quest += 1
            continue
        w = row.get("friction_weight")
        if w is None:
            skipped_weight += 1
            continue
        a = row["source_map_id"]
        b = row["destination_map_id"]
        if a == b:
            continue
        weight = float(w)
        cid = row["connection_id"]
        rank = _TYPE_RANK.get(ctype, 99)
        key = (a, b)
        cand = (weight, rank, cid, ctype)
        prev = best.get(key)
        if prev is None or cand < (prev[0], prev[1], prev[2], prev[3]):
            best[key] = cand

    adj: dict[str, list[tuple[str, float, str, str]]] = defaultdict(list)
    for (a, b), (weight, _rank, cid, ctype) in best.items():
        adj[a].append((b, weight, cid, ctype))

    # Deterministic neighbor order
    for a in adj:
        adj[a].sort(key=lambda t: (t[0], t[1], t[2]))

    meta = {
        "unique_edges": len(best),
        "skipped_quest_gated": skipped_quest,
        "skipped_other_type": skipped_type,
        "skipped_no_weight": skipped_weight,
        "by_type_kept": {},
    }
    type_counts: dict[str, int] = defaultdict(int)
    for (_a, _b), (_w, _r, _cid, ctype) in best.items():
        type_counts[ctype] += 1
    meta["by_type_kept"] = dict(sorted(type_counts.items()))
    return dict(adj), meta


def _dijkstra_one(
    source: str,
    adj: dict[str, list[tuple[str, float, str, str]]],
) -> tuple[dict[str, float], dict[str, list[str]]]:
    dist: dict[str, float] = {source: 0.0}
    route: dict[str, list[str]] = {source: []}
    heap: list[tuple[float, str]] = [(0.0, source)]

    while heap:
        d, u = heapq.heappop(heap)
        if d != dist.get(u):
            continue
        for v, w, cid, _ctype in adj.get(u, []):
            nd = d + w
            old = dist.get(v)
            if old is None or nd < old or (nd == old and (route[u] + [cid]) < route.get(v, [])):
                dist[v] = nd
                route[v] = route[u] + [cid]
                heapq.heappush(heap, (nd, v))
    return dist, route


def _load_excluded_maps(maps_path: Path) -> set[str]:
    """Instance maps stay out of the overworld friction graph."""
    excluded: set[str] = set()
    if not maps_path.is_file():
        return excluded
    for line in maps_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if row.get("is_instance") or row.get("category") == "Instance":
            excluded.add(row["map_id"])
    return excluded


def extract_map_distances(project_root: Path | None = None) -> dict[str, Any]:
    root = project_root or Path(__file__).resolve().parents[1]
    cfg = _load_extractor_config(root)
    reports_dir = root / cfg["output"]["reports_dir"]
    reports_dir.mkdir(parents=True, exist_ok=True)

    conn_path = reports_dir / "map_connections.jsonl"
    if not conn_path.is_file():
        raise FileNotFoundError(
            "reports/map_connections.jsonl missing; run: python pipeline.py extract map_connections"
        )

    excluded_maps = _load_excluded_maps(reports_dir / "maps.jsonl")

    connections = []
    skipped_instance = 0
    for line in conn_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if row["source_map_id"] in excluded_maps or row["destination_map_id"] in excluded_maps:
            skipped_instance += 1
            continue
        connections.append(row)

    adj, graph_meta = _build_graph(connections)
    graph_meta["skipped_instance_endpoint"] = skipped_instance
    graph_meta["excluded_instance_maps"] = len(excluded_maps)
    nodes = sorted(set(adj) | {v for outs in adj.values() for v, *_ in outs})

    distance_rows: list[dict[str, Any]] = []
    route_rows: list[dict[str, Any]] = []

    for src in nodes:
        dist, routes = _dijkstra_one(src, adj)
        for dst, friction in sorted(dist.items()):
            if dst == src:
                continue
            hops = routes[dst]
            distance_rows.append(
                {
                    "from_map_id": src,
                    "to_map_id": dst,
                    "friction": round(friction, 4),
                    "hop_count": len(hops),
                }
            )
            route_rows.append(
                {
                    "from_map_id": src,
                    "to_map_id": dst,
                    "connection_ids": hops,
                }
            )

    # Reachability among graph nodes
    n = len(nodes)
    reachable_pairs = len(distance_rows)
    possible_pairs = n * (n - 1)
    unreachable_pairs = possible_pairs - reachable_pairs

    # Sample unreachable (deterministic)
    reachable_set = {(r["from_map_id"], r["to_map_id"]) for r in distance_rows}
    unreachable_sample: list[list[str]] = []
    for a in nodes:
        for b in nodes:
            if a == b:
                continue
            if (a, b) not in reachable_set:
                unreachable_sample.append([a, b])
                if len(unreachable_sample) >= 20:
                    break
        if len(unreachable_sample) >= 20:
            break

    dist_path = reports_dir / "map_distances.jsonl"
    with dist_path.open("w", encoding="utf-8") as f:
        for row in distance_rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    routes_path = reports_dir / "map_routes.jsonl"
    with routes_path.open("w", encoding="utf-8") as f:
        for row in route_rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    # Spot-check examples for manual validation
    examples = []
    for a, b in [
        ("einbroch", "hugel"),
        ("einbroch", "yuno"),
        ("prontera", "payon"),
        ("alberta", "amatsu"),
    ]:
        hit = next(
            (r for r in distance_rows if r["from_map_id"] == a and r["to_map_id"] == b),
            None,
        )
        if hit:
            route = next(
                r
                for r in route_rows
                if r["from_map_id"] == a and r["to_map_id"] == b
            )
            examples.append(
                {
                    "from": a,
                    "to": b,
                    "friction": hit["friction"],
                    "hop_count": hit["hop_count"],
                    "connection_ids": route["connection_ids"],
                }
            )

    summary = {
        "domain": "map_distances",
        "nodes": n,
        "graph_edges": graph_meta["unique_edges"],
        "graph_meta": graph_meta,
        "reachable_pairs": reachable_pairs,
        "possible_directed_pairs": possible_pairs,
        "unreachable_pairs": unreachable_pairs,
        "unreachable_sample": unreachable_sample,
        "examples": examples,
        "rules": {
            "types": sorted(GRAPH_TYPES),
            "collapse": "min friction per (from_map, to_map); tie-break type rank then connection_id",
            "exclude": [
                "quest_gated",
                "scripted",
                "VIP pricing",
                "instance maps (is_instance)",
            ],
            "weights": {
                "warp": 1.0,
                "kafra": 0.2,
                "custom_npc_tp": 0.5,
                "boat": 1.2,
                "airship": 1.5,
            },
        },
        "wrote": [str(dist_path), str(routes_path)],
    }
    summary_path = reports_dir / "map_distances_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    summary["summary_path"] = str(summary_path)
    return summary
