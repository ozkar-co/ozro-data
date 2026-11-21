"""Item dependencies §22.2 — union of already-extracted consume/produce edges."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from discovery.scan import _load_extractor_config
from extractors.client_scope import load_client_item_ids


def _provenance_id(domain: str, record_id: str, source_path: str) -> str:
    raw = f"{domain}|{record_id}|{source_path}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def _eid(*parts: Any) -> str:
    raw = "|".join("" if p is None else str(p) for p in parts)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def _iter_jsonl(path: Path):
    if not path.is_file():
        return
    with path.open(encoding="utf-8") as f:
        for line in f:
            if line.strip():
                yield json.loads(line)


def extract_item_dependencies(project_root: Path | None = None) -> dict[str, Any]:
    root = project_root or Path(__file__).resolve().parents[1]
    cfg = _load_extractor_config(root)
    reports_dir = root / cfg["output"]["reports_dir"]
    reports_dir.mkdir(parents=True, exist_ok=True)
    client_ids = load_client_item_ids(reports_dir)

    edges: list[dict[str, Any]] = []
    by_kind: dict[str, int] = {}
    missing: list[str] = []

    def _add(
        *,
        kind: str,
        from_item_id: int | None,
        to_item_id: int | None,
        source_ref: str,
        amount: Any = None,
        extra: dict[str, Any] | None = None,
        provenance_src: str,
    ) -> None:
        if from_item_id is None and to_item_id is None:
            return
        fid = int(from_item_id) if from_item_id is not None else None
        tid = int(to_item_id) if to_item_id is not None else None
        if fid is not None and fid not in client_ids:
            return
        if tid is not None and tid not in client_ids:
            return
        eid = _eid("dep", kind, source_ref, fid, tid)
        row = {
            "item_dependency_id": eid,
            "dependency_kind": kind,
            "from_item_id": fid,
            "to_item_id": tid,
            "amount": amount,
            "source_ref": source_ref,
            "provenance_id": _provenance_id(
                "item_dependencies", eid, provenance_src
            ),
        }
        if extra:
            row.update(extra)
        edges.append(row)
        by_kind[kind] = by_kind.get(kind, 0) + 1

    # recipe: material → result
    recipes = {r["recipe_id"]: r for r in _iter_jsonl(reports_dir / "recipes.jsonl") or []}
    mats_path = reports_dir / "recipe_materials.jsonl"
    if mats_path.is_file():
        for m in _iter_jsonl(mats_path):
            rec = recipes.get(m.get("recipe_id")) or {}
            _add(
                kind="craft_consume",
                from_item_id=m.get("item_id"),
                to_item_id=rec.get("result_item_id"),
                source_ref=str(m.get("recipe_material_id")),
                amount=m.get("amount"),
                extra={"role": m.get("role"), "recipe_id": m.get("recipe_id")},
                provenance_src="recipe_materials.jsonl",
            )
    else:
        missing.append("recipe_materials.jsonl")

    # barter: required → offer
    barter_items = {
        b["barter_item_id"]: b
        for b in (_iter_jsonl(reports_dir / "barter_items.jsonl") or [])
    }
    req_path = reports_dir / "barter_required_items.jsonl"
    if req_path.is_file():
        for r in _iter_jsonl(req_path):
            offer = barter_items.get(r.get("barter_item_id")) or {}
            _add(
                kind="barter_consume",
                from_item_id=r.get("item_id"),
                to_item_id=offer.get("item_id"),
                source_ref=str(r.get("barter_required_id")),
                amount=r.get("amount"),
                extra={"barter_name": r.get("barter_name")},
                provenance_src="barter_required_items.jsonl",
            )
    else:
        missing.append("barter_required_items.jsonl")

    # combo: member → set (to_item_id null; set/group ids in extra)
    members_path = reports_dir / "item_combo_members.jsonl"
    if members_path.is_file():
        for m in _iter_jsonl(members_path):
            mid = m.get("combo_member_id")
            if not mid:
                continue
            _add(
                kind="combo_member",
                from_item_id=m.get("item_id"),
                to_item_id=None,
                source_ref=str(mid),
                extra={
                    "combo_set_id": m.get("combo_set_id"),
                    "combo_group_id": m.get("combo_group_id"),
                },
                provenance_src="item_combo_members.jsonl",
            )
    else:
        missing.append("item_combo_members.jsonl")

    # socket transform: from → to
    tr_path = reports_dir / "npc_item_transforms.jsonl"
    if tr_path.is_file():
        for t in _iter_jsonl(tr_path):
            _add(
                kind="socket_transform",
                from_item_id=t.get("from_item_id"),
                to_item_id=t.get("to_item_id"),
                source_ref=str(t.get("npc_item_transform_id")),
                extra={
                    "script_path": t.get("script_path"),
                    "func_name": t.get("func_name"),
                },
                provenance_src="npc_item_transforms.jsonl",
            )
    else:
        missing.append("npc_item_transforms.jsonl")

    # box nested: opener/container → reward (via box_item_links + box_rewards)
    # opener item opens group; reward is content
    links = list(_iter_jsonl(reports_dir / "box_item_links.jsonl") or [])
    rewards_by_box: dict[str, list[dict[str, Any]]] = {}
    for rw in _iter_jsonl(reports_dir / "box_rewards.jsonl") or []:
        rewards_by_box.setdefault(str(rw.get("box_id")), []).append(rw)
    if links:
        for link in links:
            box_id = str(link.get("box_id"))
            opener = link.get("item_id")
            for rw in rewards_by_box.get(box_id, []):
                _add(
                    kind="box_contains",
                    from_item_id=opener,
                    to_item_id=rw.get("item_id"),
                    source_ref=f"{link.get('link_id')}:{rw.get('reward_id')}",
                    amount=rw.get("amount"),
                    extra={"box_id": box_id, "group_name": rw.get("group_name")},
                    provenance_src="box_item_links+box_rewards",
                )
    else:
        missing.append("box_item_links.jsonl")

    out_path = reports_dir / "item_dependencies.jsonl"
    with out_path.open("w", encoding="utf-8") as f:
        for row in edges:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    summary = {
        "domain": "item_dependencies",
        "edge_count": len(edges),
        "by_kind": by_kind,
        "missing_inputs": missing,
        "wrote": [str(out_path)],
    }
    # fix combo source_ref if dict slipped through — rewrite cleanly
    # (guard already uses str(m.get(...)))
    summary_path = reports_dir / "item_dependencies_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    summary["summary_path"] = str(summary_path)
    return summary
