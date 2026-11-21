"""NPC enchant/socket inventory — getitem2 stone/target literals (playable path)."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

import yaml

from discovery.scan import _load_extractor_config
from extractors.client_scope import load_client_item_ids

_GETITEM2_RE = re.compile(
    r"getitem2\s*\(\s*([^)]*)\)",
    re.IGNORECASE,
)
_ADDPART_RE = re.compile(
    r"set\s+\.@addpart\s*,\s*(\d+)\s*;",
    re.IGNORECASE,
)
_SETARRAY_RE = re.compile(
    r"setarray\s+(\.@\w+)\s*(?:\[0\])?\s*,\s*([^\n;]+)",
    re.IGNORECASE,
)
_NUM_RE = re.compile(r"\b(\d{3,7})\b")
# Seiyablem/Leablem: callfunc "Func_Socket"|"Func_Socket2", from_id, to_id, ...
_FUNC_SOCKET_RE = re.compile(
    r'callfunc\s+"(Func_Socket2?)"\s*,\s*(\d+)\s*,\s*(\d+)\s*,',
    re.IGNORECASE,
)

_TARGET_VARS = re.compile(r"^\.@[Ii]tems$", re.IGNORECASE)
# Common enchant stone / pool array names in official scripts.
_STONE_VARS = re.compile(
    r"^\.@("
    r"addpart|enchant\w*|enchants|special|"
    r"card|cards"
    r")$",
    re.IGNORECASE,
)


def _provenance_id(domain: str, record_id: str, source_path: str) -> str:
    raw = f"{domain}|{record_id}|{source_path}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def _eid(*parts: Any) -> str:
    raw = "|".join("" if p is None else str(p) for p in parts)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def _classify(rel: str, text: str) -> str:
    low = rel.lower()
    if "socket_enchant" in low:
        return "socketing"
    if "enchan" in low or "getitem2" in text.lower():
        return "enchanting"
    return "other"


def _parse_getitem2_cards(args_blob: str) -> list[int]:
    """getitem2 item,qty,id,refine,attr,card0,card1,card2,card3 — keep literal ints."""
    parts = [p.strip() for p in args_blob.split(",")]
    if len(parts) < 9:
        return []
    out: list[int] = []
    for p in parts[5:9]:
        if re.fullmatch(r"\d+", p):
            out.append(int(p))
    return out


def _parse_getitem2_item(args_blob: str) -> int | None:
    parts = [p.strip() for p in args_blob.split(",")]
    if not parts:
        return None
    if re.fullmatch(r"\d+", parts[0]):
        return int(parts[0])
    return None


def extract_npc_enchants(project_root: Path | None = None) -> dict[str, Any]:
    root = project_root or Path(__file__).resolve().parents[1]
    cfg = _load_extractor_config(root)
    rathena = Path(cfg["paths"]["rathena"])
    reports_dir = root / cfg["output"]["reports_dir"]
    reports_dir.mkdir(parents=True, exist_ok=True)
    client_ids = load_client_item_ids(reports_dir)

    item_ids: set[int] = set()
    items_path = reports_dir / "items.jsonl"
    if items_path.is_file():
        for line in items_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            it = json.loads(line)
            if it.get("item_id") is not None:
                item_ids.add(int(it["item_id"]))

    files_path = reports_dir / "discovery_files.yml"
    disc = yaml.safe_load(files_path.read_text(encoding="utf-8")) if files_path.is_file() else {}
    scripts: list[str] = list(disc.get("scripts") or [])

    sources_out: list[dict[str, Any]] = []
    items_out: list[dict[str, Any]] = []
    transforms_out: list[dict[str, Any]] = []
    unresolved = 0
    unresolved_transform = 0
    scripts_scanned = 0

    def _emit_item(
        *,
        rel: str,
        sid: str,
        item_id: int,
        role: str,
        evidence: str,
        seen: set[tuple[int, str]],
    ) -> None:
        nonlocal unresolved
        if item_id not in item_ids or item_id not in client_ids:
            unresolved += 1
            return
        key = (item_id, role)
        if key in seen:
            return
        seen.add(key)
        rid = _eid("npceitem", rel, role, item_id)
        items_out.append(
            {
                "npc_enchant_item_id": rid,
                "npc_enchant_source_id": sid,
                "script_path": rel,
                "item_id": item_id,
                "role": role,
                "evidence": evidence,
                "provenance_id": _provenance_id("npc_enchant_items", rid, rel),
            }
        )

    for rel in scripts:
        path = rathena / rel
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        low = rel.lower()
        has_gi2 = "getitem2" in text.lower()
        is_socket = "socket_enchant" in low
        is_enchan = "enchan" in low
        if not (has_gi2 or is_socket or is_enchan):
            continue
        scripts_scanned += 1
        kind = _classify(rel, text)
        sid = _eid("npcesrc", rel)
        seen: set[tuple[int, str]] = set()
        gi2_count = 0

        for m in _GETITEM2_RE.finditer(text):
            gi2_count += 1
            blob = m.group(1)
            item_lit = _parse_getitem2_item(blob)
            if item_lit is not None:
                _emit_item(
                    rel=rel, sid=sid, item_id=item_lit, role="target",
                    evidence="getitem2_item", seen=seen,
                )
            for cid in _parse_getitem2_cards(blob):
                if cid == 0:
                    continue
                _emit_item(
                    rel=rel, sid=sid, item_id=cid, role="stone",
                    evidence="getitem2_card", seen=seen,
                )

        for m in _ADDPART_RE.finditer(text):
            _emit_item(
                rel=rel, sid=sid, item_id=int(m.group(1)), role="stone",
                evidence="set_addpart", seen=seen,
            )

        for m in _SETARRAY_RE.finditer(text):
            var = m.group(1)
            nums = [int(x) for x in _NUM_RE.findall(m.group(2))]
            if _TARGET_VARS.match(var):
                role = "target"
                evidence = "setarray_items"
            elif _STONE_VARS.match(var) or "enchant" in var.lower():
                role = "stone"
                evidence = f"setarray_{var.lstrip('.')}"
            else:
                continue
            for n in nums:
                _emit_item(
                    rel=rel, sid=sid, item_id=n, role=role,
                    evidence=evidence, seen=seen,
                )

        # Socket item→item transforms (Func_Socket / Func_Socket2)
        transform_n = 0
        for m in _FUNC_SOCKET_RE.finditer(text):
            func = m.group(1)
            from_id = int(m.group(2))
            to_id = int(m.group(3))
            if from_id not in item_ids or from_id not in client_ids:
                unresolved_transform += 1
                continue
            if to_id not in item_ids or to_id not in client_ids:
                unresolved_transform += 1
                continue
            tid = _eid("npctransform", rel, func, from_id, to_id)
            transforms_out.append(
                {
                    "npc_item_transform_id": tid,
                    "npc_enchant_source_id": sid,
                    "script_path": rel,
                    "transform_kind": "socketing",
                    "func_name": func,
                    "from_item_id": from_id,
                    "to_item_id": to_id,
                    "provenance_id": _provenance_id(
                        "npc_item_transforms", tid, rel
                    ),
                }
            )
            transform_n += 1
            _emit_item(
                rel=rel, sid=sid, item_id=from_id, role="transform_from",
                evidence=func, seen=seen,
            )
            _emit_item(
                rel=rel, sid=sid, item_id=to_id, role="transform_to",
                evidence=func, seen=seen,
            )

        stone_n = sum(1 for a, b in seen if b == "stone")
        target_n = sum(1 for a, b in seen if b == "target")
        sources_out.append(
            {
                "npc_enchant_source_id": sid,
                "script_path": rel,
                "kind": kind,
                "getitem2_count": gi2_count,
                "stone_count": stone_n,
                "target_count": target_n,
                "transform_count": transform_n,
                "provenance_id": _provenance_id("npc_enchant_sources", sid, rel),
            }
        )

    writes = {
        "npc_enchant_sources": sources_out,
        "npc_enchant_items": items_out,
        "npc_item_transforms": transforms_out,
    }
    wrote: list[str] = []
    for name, rows in writes.items():
        path = reports_dir / f"{name}.jsonl"
        with path.open("w", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        wrote.append(str(path))

    summary = {
        "domain": "npc_enchants",
        "scripts_scanned": scripts_scanned,
        "source_count": len(sources_out),
        "item_rows": len(items_out),
        "unique_stones": len({r["item_id"] for r in items_out if r["role"] == "stone"}),
        "unique_targets": len({r["item_id"] for r in items_out if r["role"] == "target"}),
        "socket_transform_rows": len(transforms_out),
        "unique_socket_results": len({r["to_item_id"] for r in transforms_out}),
        "by_kind": {},
        "unresolved_item": unresolved,
        "unresolved_transform": unresolved_transform,
        "wrote": wrote,
    }
    for s in sources_out:
        k = s["kind"]
        summary["by_kind"][k] = summary["by_kind"].get(k, 0) + 1

    summary_path = reports_dir / "npc_enchants_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    summary["summary_path"] = str(summary_path)
    return summary
