"""Barters — npc/barters.yml import tree inventory (RequiredItems model)."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import yaml

from discovery.scan import _load_extractor_config
from extractors.client_scope import load_client_item_ids


def _provenance_id(domain: str, record_id: str, source_path: str) -> str:
    raw = f"{domain}|{record_id}|{source_path}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def _eid(*parts: Any) -> str:
    raw = "|".join("" if p is None else str(p) for p in parts)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def _resolve_item(
    aegis: str | None,
    item_by_aegis: dict[str, int],
    client_ids: set[int],
) -> tuple[int | None, bool]:
    if not aegis:
        return None, True
    iid = item_by_aegis.get(str(aegis).upper())
    if iid is None or iid not in client_ids:
        return None, True
    return iid, False


def _walk_barter_files(rathena: Path) -> list[tuple[Path, str]]:
    """Follow Footer.Imports from root barter entrypoints."""
    roots = [
        rathena / "npc/barters.yml",
        rathena / "npc/re/merchants/barters.yml",
        rathena / "npc/custom/barters.yml",
    ]
    out: list[tuple[Path, str]] = []
    seen: set[Path] = set()
    queue: list[Path] = list(roots)

    while queue:
        path = queue.pop(0)
        if not path.is_file() or path in seen:
            continue
        seen.add(path)
        rel = str(path.relative_to(rathena)).replace("\\", "/")
        out.append((path, rel))
        doc = yaml.safe_load(path.read_text(encoding="utf-8", errors="replace")) or {}
        for imp in (doc.get("Footer") or {}).get("Imports") or []:
            if not isinstance(imp, dict):
                continue
            p = imp.get("Path")
            if p:
                queue.append(rathena / str(p))
    return out


def extract_barters(project_root: Path | None = None) -> dict[str, Any]:
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

    # Optional: map barter Name → npc_id from npcs.jsonl (exact name match)
    npc_by_name: dict[str, str] = {}
    npcs_path = reports_dir / "npcs.jsonl"
    if npcs_path.is_file():
        for line in npcs_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            n = json.loads(line)
            name = n.get("name") or n.get("npc_name")
            if name and n.get("npc_id"):
                npc_by_name[str(name)] = str(n["npc_id"])

    barters_out: list[dict[str, Any]] = []
    items_out: list[dict[str, Any]] = []
    req_out: list[dict[str, Any]] = []
    unresolved_item = 0
    skipped_no_client_offer = 0

    for path, rel in _walk_barter_files(rathena):
        doc = yaml.safe_load(path.read_text(encoding="utf-8", errors="replace")) or {}
        for row in doc.get("Body") or []:
            if not isinstance(row, dict):
                continue
            name = str(row.get("Name") or "")
            if not name:
                continue
            bid = _eid("barter", name, rel)
            map_name = row.get("Map")
            barters_out.append(
                {
                    "barter_id": bid,
                    "barter_name": name,
                    "map_name": map_name,
                    "x": row.get("X", 0),
                    "y": row.get("Y", 0),
                    "direction": row.get("Direction"),
                    "sprite": row.get("Sprite"),
                    "npc_id": npc_by_name.get(name),
                    "source_file": rel,
                    "provenance_id": _provenance_id("barters", bid, rel),
                }
            )
            for it in row.get("Items") or []:
                if not isinstance(it, dict):
                    continue
                offer_aegis = it.get("Item")
                offer_id, bad = _resolve_item(offer_aegis, item_by_aegis, client_ids)
                if bad:
                    skipped_no_client_offer += 1
                    unresolved_item += 1
                    continue
                idx = it.get("Index")
                iid_row = _eid("barteritem", name, idx, offer_aegis)
                items_out.append(
                    {
                        "barter_item_id": iid_row,
                        "barter_id": bid,
                        "barter_name": name,
                        "index": idx,
                        "item_id": offer_id,
                        "aegis_name": str(offer_aegis),
                        "stock": int(it.get("Stock") or 0),
                        "zeny": int(it.get("Zeny") or 0),
                        "refine": int(it.get("Refine") or 0),
                        "source_file": rel,
                        "provenance_id": _provenance_id(
                            "barter_items", iid_row, rel
                        ),
                    }
                )
                for ri, req in enumerate(it.get("RequiredItems") or []):
                    if not isinstance(req, dict):
                        continue
                    req_aegis = req.get("Item")
                    req_id, req_bad = _resolve_item(
                        req_aegis, item_by_aegis, client_ids
                    )
                    if req_bad:
                        unresolved_item += 1
                        continue
                    rid = _eid("barterreq", name, idx, ri, req_aegis)
                    req_out.append(
                        {
                            "barter_required_id": rid,
                            "barter_item_id": iid_row,
                            "barter_id": bid,
                            "barter_name": name,
                            "offer_index": idx,
                            "req_index": req.get("Index", ri),
                            "item_id": req_id,
                            "aegis_name": str(req_aegis),
                            "amount": int(req.get("Amount") or 1),
                            "refine": int(req.get("Refine") or 0),
                            "source_file": rel,
                            "provenance_id": _provenance_id(
                                "barter_required_items", rid, rel
                            ),
                        }
                    )

    writes = {
        "barters": barters_out,
        "barter_items": items_out,
        "barter_required_items": req_out,
    }
    wrote: list[str] = []
    for name, rows in writes.items():
        path = reports_dir / f"{name}.jsonl"
        with path.open("w", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        wrote.append(str(path))

    summary = {
        "domain": "barters",
        "barter_count": len(barters_out),
        "offer_rows": len(items_out),
        "required_rows": len(req_out),
        "unique_offer_items": len({r["item_id"] for r in items_out}),
        "skipped_no_client_offer": skipped_no_client_offer,
        "unresolved_item": unresolved_item,
        "npc_id_resolved": sum(1 for b in barters_out if b.get("npc_id")),
        "wrote": wrote,
    }
    summary_path = reports_dir / "barters_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    summary["summary_path"] = str(summary_path)
    return summary
