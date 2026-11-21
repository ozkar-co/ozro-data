"""Item relationships — item_combos.yml (+ import) (Etapa 3).

Other relationship kinds (consume/produce/refine/socket) deferred.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import yaml

from discovery.scan import _load_extractor_config
from extractors.client_scope import load_client_item_ids
from extractors.item_scripts import _normalize_body, _parse_effects


def _provenance_id(domain: str, record_id: str, source_path: str) -> str:
    raw = f"{domain}|{record_id}|{source_path}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def _eid(*parts: Any) -> str:
    raw = "|".join("" if p is None else str(p) for p in parts)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def extract_item_relationships(project_root: Path | None = None) -> dict[str, Any]:
    root = project_root or Path(__file__).resolve().parents[1]
    cfg = _load_extractor_config(root)
    rathena = Path(cfg["paths"]["rathena"])
    reports_dir = root / cfg["output"]["reports_dir"]
    reports_dir.mkdir(parents=True, exist_ok=True)
    client_ids = load_client_item_ids(reports_dir)

    item_by_aegis: dict[str, int] = {}
    items_path = reports_dir / "items.jsonl"
    if items_path.is_file():
        for line in items_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            it = json.loads(line)
            if it.get("aegis_name"):
                item_by_aegis[str(it["aegis_name"]).upper()] = int(it["item_id"])

    other = list(cfg.get("db", {}).get("other") or [])
    files = [p for p in other if "item_combos" in p] or [
        "db/re/item_combos.yml",
        "db/import/item_combos.yml",
    ]

    # import Clear / overrides: later files append; Clear rows remove matching combos
    # Practical approach: load base then import sequentially; on Clear, drop groups whose
    # combo sets match the Clear payload (rAthena clears listed combos).
    groups: list[tuple[dict[str, Any], str]] = []
    for rel in files:
        path = rathena / rel
        if not path.is_file():
            continue
        doc = yaml.safe_load(path.read_text(encoding="utf-8", errors="replace"))
        for row in (doc or {}).get("Body") or []:
            if not isinstance(row, dict):
                continue
            if row.get("Clear") is True:
                # Remove any previously loaded group that shares an identical Combo set
                clear_sets: list[frozenset[str]] = []
                for c in row.get("Combos") or []:
                    if not isinstance(c, dict):
                        continue
                    names = [
                        str(n).upper()
                        for n in (c.get("Combo") or [])
                        if n
                    ]
                    if names:
                        clear_sets.append(frozenset(names))
                if clear_sets:
                    kept: list[tuple[dict[str, Any], str]] = []
                    for g, src in groups:
                        g_sets = []
                        for c in g.get("Combos") or []:
                            if not isinstance(c, dict):
                                continue
                            names = [
                                str(n).upper()
                                for n in (c.get("Combo") or [])
                                if n
                            ]
                            if names:
                                g_sets.append(frozenset(names))
                        if any(s in clear_sets for s in g_sets):
                            continue
                        kept.append((g, src))
                    groups = kept
                continue
            groups.append((dict(row), rel))

    combo_groups: list[dict[str, Any]] = []
    combo_sets: list[dict[str, Any]] = []
    members_out: list[dict[str, Any]] = []
    skipped_no_client = 0
    unresolved_item = 0
    by_size: dict[str, int] = {}

    for gi, (row, src) in enumerate(groups):
        body = _normalize_body(row.get("Script"))
        if body is None:
            body = ""
        effects, parse_status = _parse_effects(body)
        group_id = _eid("combogroup", gi, src, body)

        sets_raw = row.get("Combos") or []
        kept_sets = 0
        for si, c in enumerate(sets_raw):
            if not isinstance(c, dict):
                continue
            names = [str(n) for n in (c.get("Combo") or []) if n]
            if len(names) < 2:
                continue
            resolved: list[tuple[str, int]] = []
            bad = False
            for name in names:
                iid = item_by_aegis.get(name.upper())
                if iid is None or iid not in client_ids:
                    unresolved_item += 1
                    bad = True
                    break
                resolved.append((name, iid))
            if bad:
                skipped_no_client += 1
                continue

            set_id = _eid("comboset", group_id, si, *(n.upper() for n, _ in resolved))
            size_key = str(len(resolved))
            by_size[size_key] = by_size.get(size_key, 0) + 1
            kept_sets += 1
            combo_sets.append(
                {
                    "combo_set_id": set_id,
                    "combo_group_id": group_id,
                    "member_count": len(resolved),
                    "index": si,
                    "source_file": src,
                    "provenance_id": _provenance_id(
                        "item_combo_sets", set_id, src
                    ),
                }
            )
            for idx, (name, iid) in enumerate(resolved):
                mid = _eid("combomem", set_id, idx, iid)
                members_out.append(
                    {
                        "combo_member_id": mid,
                        "combo_set_id": set_id,
                        "combo_group_id": group_id,
                        "item_id": iid,
                        "aegis_name": name,
                        "index": idx,
                        "source_file": src,
                        "provenance_id": _provenance_id(
                            "item_combo_members", mid, src
                        ),
                    }
                )

        if kept_sets == 0:
            continue

        combo_groups.append(
            {
                "combo_group_id": group_id,
                "set_count": kept_sets,
                "script_body": body,
                "script_hash": hashlib.sha1(body.encode("utf-8")).hexdigest(),
                "parsed_effects": effects,
                "parse_status": parse_status,
                "source_file": src,
                "provenance_id": _provenance_id(
                    "item_combo_groups", group_id, src
                ),
            }
        )

    writes = {
        "item_combo_groups": combo_groups,
        "item_combo_sets": combo_sets,
        "item_combo_members": members_out,
    }
    wrote: list[str] = []
    for name, rows in writes.items():
        path = reports_dir / f"{name}.jsonl"
        with path.open("w", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        wrote.append(str(path))

    summary = {
        "domain": "item_relationships",
        "kind": "combos",
        "combo_group_count": len(combo_groups),
        "combo_set_count": len(combo_sets),
        "member_rows": len(members_out),
        "by_member_count": by_size,
        "skipped_no_client_set": skipped_no_client,
        "unresolved_item": unresolved_item,
        "deferred": [
            "consume_produce_graphs",
            "refine_socket_compat",
            "skill_item_requirements",
            "quest_item_requirements",
        ],
        "wrote": wrote,
    }
    summary_path = reports_dir / "item_relationships_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    summary["summary_path"] = str(summary_path)
    return summary
