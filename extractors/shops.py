"""NPC shops — headers + callshop→inventory links (Etapa 3)."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

import yaml

from discovery.scan import _load_extractor_config
from extractors.npcs import _parse_name_fields, _stable_npc_id, parse_npc_line

_SHOP_TYPES = frozenset(
    {"shop", "cashshop", "itemshop", "pointshop", "marketshop"}
)

_SHOP_HEADER_RE = re.compile(
    r"^(?P<map>-|[A-Za-z0-9_@-]+),(?P<x>-?\d+),(?P<y>-?\d+),(?P<dir>\d+)\t"
    r"(?P<type>shop|cashshop|itemshop|pointshop|marketshop)\t"
    r"(?P<name>[^\t]+)\t(?P<body>.+)$"
)

_FLOAT_SHOP_RE = re.compile(
    r"^-\t(?P<type>shop|cashshop|itemshop|pointshop|marketshop)\t"
    r"(?P<name>[^\t]+)\t(?P<body>.+)$"
)

_ITEM_RE = re.compile(r"^(\d+):(-?\d+)(?::(-?\d+))?$")

# callshop "Name" / callshop("Name" / callshop "pref" + expr
_CALLSHOP_LIT_RE = re.compile(
    r"""\bcallshop\s*(?:\(|\s+)\s*(?P<q>["'])(?P<name>[^"']+)(?P=q)"""
    r"""(?P<rest>[^;\n]*)""",
    re.IGNORECASE,
)
_CALLSHOP_ANY_RE = re.compile(r"\bcallshop\b", re.IGNORECASE)
_SCRIPT_NPC_RE = re.compile(
    r"^(?:-|[A-Za-z0-9_@-]+,-?\d+,-?\d+,\d+)\tscript\t"
)
_BARTER_NAME_RE = re.compile(r"^\s*-\s*Name:\s*(?P<name>\S+)\s*$")
_BARTER_IMPORT_RE = re.compile(r"^\s*-\s*Path:\s*(?P<path>\S+)\s*$")


def _provenance_id(domain: str, record_id: str, source_path: str) -> str:
    raw = f"{domain}|{record_id}|{source_path}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def _shop_id(npc_id: str, script_path: str, line_no: int) -> str:
    return hashlib.sha1(f"shop|{npc_id}|{script_path}|{line_no}".encode()).hexdigest()


def _currency_for(
    shop_type: str, cost_item_id: int | None, cost_var: str | None
) -> str:
    if shop_type == "cashshop":
        return "cash"
    if shop_type == "itemshop" and cost_item_id is not None:
        return f"item:{cost_item_id}"
    if shop_type == "pointshop" and cost_var:
        return f"var:{cost_var}"
    return "zeny"


def _parse_shop_body(
    shop_type: str, body: str
) -> tuple[str | None, int | None, str | None, bool | None, list[dict[str, Any]]]:
    """Return (sprite, cost_item_id, cost_var, discount, items)."""
    parts = [p.strip() for p in body.split(",") if p.strip() != ""]
    if not parts:
        return None, None, None, None, []

    sprite = parts[0]
    idx = 1
    cost_item_id: int | None = None
    cost_var: str | None = None
    discount: bool | None = None

    if shop_type == "itemshop" and idx < len(parts):
        # costitemid{ :discount }
        cost_tok = parts[idx]
        idx += 1
        if ":" in cost_tok:
            left, right = cost_tok.split(":", 1)
            if re.fullmatch(r"\d+", left):
                cost_item_id = int(left)
            if right.lower() in {"0", "1", "yes", "no"}:
                discount = right.lower() in {"1", "yes"}
        elif re.fullmatch(r"\d+", cost_tok):
            cost_item_id = int(cost_tok)
    elif shop_type == "pointshop" and idx < len(parts):
        cost_tok = parts[idx]
        idx += 1
        if ":" in cost_tok:
            left, right = cost_tok.split(":", 1)
            cost_var = left
            if right.lower() in {"0", "1", "yes", "no"}:
                discount = right.lower() in {"1", "yes"}
        else:
            cost_var = cost_tok
    else:
        # optional yes/no discount before items (shop/cashshop)
        if idx < len(parts) and parts[idx].lower() in {"yes", "no"}:
            discount = parts[idx].lower() == "yes"
            idx += 1

    items: list[dict[str, Any]] = []
    for tok in parts[idx:]:
        m = _ITEM_RE.match(tok)
        if not m:
            continue
        item_id = int(m.group(1))
        price = int(m.group(2))
        stock = int(m.group(3)) if m.group(3) is not None else None
        if shop_type != "marketshop":
            stock = None
        items.append({"item_id": item_id, "price": price, "stock": stock})
    return sprite, cost_item_id, cost_var, discount, items


def parse_shop_line(
    line: str, script_path: str, line_no: int
) -> dict[str, Any] | None:
    map_id: str | None = None
    x = y = None
    m = _SHOP_HEADER_RE.match(line)
    if m:
        map_id = None if m.group("map") == "-" else m.group("map")
        x = int(m.group("x"))
        y = int(m.group("y"))
        shop_type = m.group("type")
        name_field = m.group("name")
        body = m.group("body")
    else:
        m2 = _FLOAT_SHOP_RE.match(line)
        if not m2:
            return None
        shop_type = m2.group("type")
        name_field = m2.group("name")
        body = m2.group("body")

    display, unique, _raw = _parse_name_fields(name_field)
    sprite, cost_item_id, cost_var, discount, items = _parse_shop_body(shop_type, body)
    npc_id = _stable_npc_id(unique, display, map_id, x, y, script_path, line_no)
    sid = _shop_id(npc_id, script_path, line_no)
    return {
        "shop_id": sid,
        "npc_id": npc_id,
        "shop_name": display,
        "shop_type": shop_type,
        "currency": _currency_for(shop_type, cost_item_id, cost_var),
        "cost_item_id": cost_item_id,
        "cost_variable": cost_var,
        "discount": discount,
        "sprite": sprite,
        "map_id": map_id,
        "x": x,
        "y": y,
        "items": items,
        "item_count": len(items),
        "script_path": script_path,
        "script_line": line_no,
        "provenance_id": _provenance_id("shops", sid, f"{script_path}:{line_no}"),
        "source": {"script_path": script_path, "line": line_no},
    }


def _load_barter_names(rathena: Path) -> set[str]:
    """Names only — classify callshop misses; full barter inventory deferred."""
    names: set[str] = set()
    roots = [
        rathena / "npc/re/merchants/barters.yml",
        rathena / "npc/barters.yml",
        rathena / "npc/custom/barters.yml",
    ]
    seen_files: set[Path] = set()

    def _ingest(path: Path) -> None:
        if not path.is_file() or path in seen_files:
            return
        seen_files.add(path)
        text = path.read_text(encoding="utf-8", errors="replace")
        for line in text.splitlines():
            m = _BARTER_NAME_RE.match(line)
            if m:
                names.add(m.group("name"))
                continue
            imp = _BARTER_IMPORT_RE.match(line)
            if imp:
                rel = imp.group("path")
                _ingest(rathena / rel)

    for root_yml in roots:
        _ingest(root_yml)
    return names


def _index_shops(
    shops: list[dict[str, Any]],
) -> tuple[dict[str, list[dict[str, Any]]], list[dict[str, Any]]]:
    by_name: dict[str, list[dict[str, Any]]] = {}
    for s in shops:
        by_name.setdefault(s["shop_name"], []).append(s)
        by_name.setdefault(s["npc_id"], []).append(s)
    return by_name, shops


def _enclosing_script_npc(
    lines: list[str], line_no: int, script_path: str
) -> dict[str, Any] | None:
    """Walk upward to the nearest script NPC header that owns this body line."""
    for i in range(line_no - 1, -1, -1):
        raw = lines[i].split("//", 1)[0].rstrip()
        if not _SCRIPT_NPC_RE.match(raw):
            continue
        return parse_npc_line(raw, script_path, i + 1)
    return None


def _extract_callshop_links(
    rathena: Path,
    scripts: list[str],
    shops: list[dict[str, Any]],
    barter_names: set[str],
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    by_name, _ = _index_shops(shops)
    links: list[dict[str, Any]] = []
    stats = {
        "callshop_rows": 0,
        "resolved_literal": 0,
        "resolved_prefix": 0,
        "unresolved_barter": 0,
        "unresolved_dynamic": 0,
        "unresolved_other": 0,
        "missing_caller": 0,
    }

    for rel in scripts:
        path = rathena / rel
        if not path.is_file():
            continue
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        for line_no, raw in enumerate(lines, 1):
            line = raw.split("//", 1)[0]
            if "callshop" not in line.lower():
                continue
            stats["callshop_rows"] += 1
            caller = _enclosing_script_npc(lines, line_no, rel)
            caller_id = caller["npc_id"] if caller else None
            if caller_id is None:
                stats["missing_caller"] += 1

            lit = _CALLSHOP_LIT_RE.search(line)
            if not lit:
                if _CALLSHOP_ANY_RE.search(line):
                    stats["unresolved_dynamic"] += 1
                    lid = hashlib.sha1(
                        f"callshop|{rel}|{line_no}|dyn".encode()
                    ).hexdigest()
                    links.append(
                        {
                            "link_id": lid,
                            "caller_npc_id": caller_id,
                            "target_name": None,
                            "resolve_status": "dynamic",
                            "shop_ids": [],
                            "script_path": rel,
                            "script_line": line_no,
                            "provenance_id": _provenance_id(
                                "shop_links", lid, f"{rel}:{line_no}"
                            ),
                        }
                    )
                continue

            name = lit.group("name")
            rest = lit.group("rest") or ""
            is_prefix = bool(re.search(r"\+\s*\S", rest))
            matched: list[dict[str, Any]] = []
            status: str

            if is_prefix:
                matched = [
                    s
                    for s in shops
                    if s["shop_name"].startswith(name) or s["npc_id"].startswith(name)
                ]
                # dedupe by shop_id
                seen: set[str] = set()
                uniq: list[dict[str, Any]] = []
                for s in matched:
                    if s["shop_id"] in seen:
                        continue
                    seen.add(s["shop_id"])
                    uniq.append(s)
                matched = uniq
                if matched:
                    status = "prefix_resolved"
                    stats["resolved_prefix"] += 1
                elif any(b.startswith(name) for b in barter_names):
                    status = "unresolved_barter"
                    stats["unresolved_barter"] += 1
                else:
                    status = "prefix_unresolved"
                    stats["unresolved_other"] += 1
            elif name in by_name:
                # dedupe
                seen = set()
                for s in by_name[name]:
                    if s["shop_id"] not in seen:
                        matched.append(s)
                        seen.add(s["shop_id"])
                status = "resolved"
                stats["resolved_literal"] += 1
            elif name in barter_names or name.startswith("barter_"):
                status = "unresolved_barter"
                stats["unresolved_barter"] += 1
            else:
                status = "unresolved"
                stats["unresolved_other"] += 1

            lid = hashlib.sha1(
                f"callshop|{rel}|{line_no}|{name}|{status}".encode()
            ).hexdigest()
            links.append(
                {
                    "link_id": lid,
                    "caller_npc_id": caller_id,
                    "target_name": name,
                    "resolve_status": status,
                    "shop_ids": [s["shop_id"] for s in matched],
                    "item_count": sum(s.get("item_count") or 0 for s in matched),
                    "script_path": rel,
                    "script_line": line_no,
                    "provenance_id": _provenance_id(
                        "shop_links", lid, f"{rel}:{line_no}"
                    ),
                }
            )

    return links, stats


def extract_shops(project_root: Path | None = None) -> dict[str, Any]:
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

    shops: list[dict[str, Any]] = []
    shop_items: list[dict[str, Any]] = []
    by_type: dict[str, int] = {}
    parse_skip = 0

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
            # Fast reject
            if not any(f"\t{t}\t" in line for t in _SHOP_TYPES):
                continue
            rec = parse_shop_line(line, rel, line_no)
            if not rec:
                parse_skip += 1
                continue
            shops.append({k: v for k, v in rec.items() if k != "items"})
            by_type[rec["shop_type"]] = by_type.get(rec["shop_type"], 0) + 1
            for it in rec["items"]:
                shop_items.append(
                    {
                        "shop_id": rec["shop_id"],
                        "npc_id": rec["npc_id"],
                        "item_id": it["item_id"],
                        "price": it["price"],
                        "stock": it["stock"],
                        "price_is_default": it["price"] < 0,
                    }
                )

    barter_names = _load_barter_names(rathena)
    links, link_stats = _extract_callshop_links(
        rathena, scripts, shops, barter_names
    )

    shops_path = reports_dir / "npc_shops.jsonl"
    with shops_path.open("w", encoding="utf-8") as f:
        for row in shops:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    items_path = reports_dir / "npc_shop_items.jsonl"
    with items_path.open("w", encoding="utf-8") as f:
        for row in shop_items:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    links_path = reports_dir / "npc_shop_links.jsonl"
    with links_path.open("w", encoding="utf-8") as f:
        for row in links:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    summary = {
        "domain": "shops",
        "shop_count": len(shops),
        "shop_item_rows": len(shop_items),
        "unique_items": len({r["item_id"] for r in shop_items}),
        "by_type": by_type,
        "parse_skip": parse_skip,
        "callshop": link_stats,
        "barter_names_indexed": len(barter_names),
        "deferred": [
            "barter_db_inventory",
            "callshop_dynamic_arrays",
            "buysell_scripted",
        ],
        "wrote": [str(shops_path), str(items_path), str(links_path)],
    }
    summary_path = reports_dir / "shops_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    summary["summary_path"] = str(summary_path)
    return summary
