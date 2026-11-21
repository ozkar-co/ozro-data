"""Enchantments — item_enchant.yml (+ import) (Etapa 3)."""

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
    """Return (item_id|None, unresolved)."""
    if not aegis:
        return None, True
    iid = item_by_aegis.get(str(aegis).upper())
    if iid is None:
        return None, True
    if iid not in client_ids:
        return None, True
    return iid, False


def _materials_list(
    raw: Any,
    *,
    parent_id: str,
    context: str,
    item_by_aegis: dict[str, int],
    client_ids: set[int],
    source_file: str,
    materials_out: list[dict[str, Any]],
    unresolved: list[int],
) -> None:
    if not isinstance(raw, list):
        return
    for idx, entry in enumerate(raw):
        if not isinstance(entry, dict):
            continue
        name = entry.get("Material")
        amt = entry.get("Amount", 1)
        iid, bad = _resolve_item(name, item_by_aegis, client_ids)
        if bad:
            unresolved[0] += 1
            continue
        mid = _eid("emat", parent_id, context, idx, name)
        materials_out.append(
            {
                "enchant_material_id": mid,
                "parent_id": parent_id,
                "context": context,
                "item_id": iid,
                "aegis_name": str(name),
                "amount": int(amt) if amt is not None else 1,
                "index": idx,
                "source_file": source_file,
                "provenance_id": _provenance_id(
                    "enchant_materials", mid, source_file
                ),
            }
        )


def extract_enchantments(project_root: Path | None = None) -> dict[str, Any]:
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
    files = [p for p in other if "item_enchant" in p] or [
        "db/re/item_enchant.yml",
        "db/import/item_enchant.yml",
    ]

    by_id: dict[int, tuple[dict[str, Any], str]] = {}
    for rel in files:
        path = rathena / rel
        if not path.is_file():
            continue
        doc = yaml.safe_load(path.read_text(encoding="utf-8", errors="replace"))
        for row in (doc or {}).get("Body") or []:
            eid = row.get("Id")
            if eid is None:
                continue
            eid = int(eid)
            if eid not in by_id:
                by_id[eid] = (dict(row), rel)
            else:
                merged = dict(by_id[eid][0])
                merged.update(row)
                by_id[eid] = (merged, rel)

    enchantments: list[dict[str, Any]] = []
    targets_out: list[dict[str, Any]] = []
    options_out: list[dict[str, Any]] = []
    perfect_out: list[dict[str, Any]] = []
    upgrades_out: list[dict[str, Any]] = []
    materials_out: list[dict[str, Any]] = []
    unresolved = [0]
    skipped_no_target = 0

    for eid in sorted(by_id):
        row, src = by_id[eid]
        enchant_id = _eid("enchant", eid)
        targets = row.get("TargetItems") or {}
        if not isinstance(targets, dict):
            targets = {}

        resolved_targets = 0
        for name, enabled in targets.items():
            if enabled is False:
                continue
            iid, bad = _resolve_item(name, item_by_aegis, client_ids)
            if bad:
                unresolved[0] += 1
                continue
            resolved_targets += 1
            tid = _eid("etarget", eid, name)
            targets_out.append(
                {
                    "enchant_target_id": tid,
                    "enchant_id": enchant_id,
                    "enchant_db_id": eid,
                    "item_id": iid,
                    "aegis_name": str(name),
                    "source_file": src,
                    "provenance_id": _provenance_id(
                        "enchant_targets", tid, src
                    ),
                }
            )

        if resolved_targets == 0:
            skipped_no_target += 1
            # still record catalog? skip orphan UI entries with no playable targets
            continue

        reset = row.get("Reset") if isinstance(row.get("Reset"), dict) else {}
        order = []
        for o in row.get("Order") or []:
            if isinstance(o, dict) and o.get("Slot") is not None:
                order.append(int(o["Slot"]))

        enchantments.append(
            {
                "enchant_id": enchant_id,
                "enchant_db_id": eid,
                "minimum_refine": row.get("MinimumRefine", 0),
                "minimum_enchantgrade": row.get("MinimumEnchantgrade", 0),
                "allow_random_options": row.get("AllowRandomOptions", True),
                "slot_order": order,
                "reset_chance": reset.get("Chance"),
                "reset_price": reset.get("Price"),
                "target_count": resolved_targets,
                "chance_unit": "per_100000",
                "source_file": src,
                "provenance_id": _provenance_id("enchantments", enchant_id, src),
            }
        )

        if reset:
            _materials_list(
                reset.get("Materials"),
                parent_id=enchant_id,
                context="reset",
                item_by_aegis=item_by_aegis,
                client_ids=client_ids,
                source_file=src,
                materials_out=materials_out,
                unresolved=unresolved,
            )

        for sl in row.get("Slots") or []:
            if not isinstance(sl, dict):
                continue
            slot = sl.get("Slot")
            slot_parent = _eid("eslot", eid, slot)
            _materials_list(
                sl.get("Materials"),
                parent_id=slot_parent,
                context="slot",
                item_by_aegis=item_by_aegis,
                client_ids=client_ids,
                source_file=src,
                materials_out=materials_out,
                unresolved=unresolved,
            )

            for eg in sl.get("Enchants") or []:
                if not isinstance(eg, dict):
                    continue
                grade = eg.get("Enchantgrade")
                for item in eg.get("Items") or []:
                    if not isinstance(item, dict):
                        continue
                    iname = item.get("Item")
                    iid, bad = _resolve_item(iname, item_by_aegis, client_ids)
                    if bad:
                        unresolved[0] += 1
                        continue
                    oid = _eid("eopt", eid, slot, grade, iname)
                    options_out.append(
                        {
                            "enchant_option_id": oid,
                            "enchant_id": enchant_id,
                            "enchant_db_id": eid,
                            "slot": slot,
                            "enchantgrade": grade,
                            "item_id": iid,
                            "aegis_name": str(iname),
                            "chance": item.get("Chance"),
                            "chance_unit": "per_100000",
                            "kind": "normal",
                            "slot_price": sl.get("Price"),
                            "source_file": src,
                            "provenance_id": _provenance_id(
                                "enchant_options", oid, src
                            ),
                        }
                    )

            for pe in sl.get("PerfectEnchants") or []:
                if not isinstance(pe, dict):
                    continue
                iname = pe.get("Item")
                iid, bad = _resolve_item(iname, item_by_aegis, client_ids)
                if bad:
                    unresolved[0] += 1
                    continue
                pid = _eid("eperf", eid, slot, iname)
                perfect_out.append(
                    {
                        "enchant_perfect_id": pid,
                        "enchant_id": enchant_id,
                        "enchant_db_id": eid,
                        "slot": slot,
                        "item_id": iid,
                        "aegis_name": str(iname),
                        "price": pe.get("Price", 0),
                        "source_file": src,
                        "provenance_id": _provenance_id(
                            "enchant_perfect", pid, src
                        ),
                    }
                )
                _materials_list(
                    pe.get("Materials"),
                    parent_id=pid,
                    context="perfect",
                    item_by_aegis=item_by_aegis,
                    client_ids=client_ids,
                    source_file=src,
                    materials_out=materials_out,
                    unresolved=unresolved,
                )

            for up in sl.get("Upgrades") or []:
                if not isinstance(up, dict):
                    continue
                from_name = up.get("Enchant")
                to_name = up.get("Upgrade")
                from_id, bad_f = _resolve_item(from_name, item_by_aegis, client_ids)
                to_id, bad_t = _resolve_item(to_name, item_by_aegis, client_ids)
                if bad_f or bad_t:
                    unresolved[0] += 1
                    continue
                uid = _eid("eup", eid, slot, from_name, to_name)
                upgrades_out.append(
                    {
                        "enchant_upgrade_id": uid,
                        "enchant_id": enchant_id,
                        "enchant_db_id": eid,
                        "slot": slot,
                        "from_item_id": from_id,
                        "from_aegis_name": str(from_name),
                        "to_item_id": to_id,
                        "to_aegis_name": str(to_name),
                        "price": up.get("Price", 0),
                        "source_file": src,
                        "provenance_id": _provenance_id(
                            "enchant_upgrades", uid, src
                        ),
                    }
                )
                _materials_list(
                    up.get("Materials"),
                    parent_id=uid,
                    context="upgrade",
                    item_by_aegis=item_by_aegis,
                    client_ids=client_ids,
                    source_file=src,
                    materials_out=materials_out,
                    unresolved=unresolved,
                )

    writes = {
        "enchantments": enchantments,
        "enchant_targets": targets_out,
        "enchant_options": options_out,
        "enchant_perfect": perfect_out,
        "enchant_upgrades": upgrades_out,
        "enchant_materials": materials_out,
    }
    wrote: list[str] = []
    for name, rows in writes.items():
        path = reports_dir / f"{name}.jsonl"
        with path.open("w", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        wrote.append(str(path))

    summary = {
        "domain": "enchantments",
        "enchant_count": len(enchantments),
        "target_rows": len(targets_out),
        "option_rows": len(options_out),
        "perfect_rows": len(perfect_out),
        "upgrade_rows": len(upgrades_out),
        "material_rows": len(materials_out),
        "skipped_no_target": skipped_no_target,
        "unresolved_item": unresolved[0],
        "chance_unit": "per_100000",
        "deferred": [
            "npc_socket_enchant_seiyablem_leablem",
            "npc_armor_enchant_craftsman",
            "enchantgrade_bonus_rows",
            "item_reform_overlap",
        ],
        "wrote": wrote,
    }
    summary_path = reports_dir / "enchantments_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    summary["summary_path"] = str(summary_path)
    return summary
