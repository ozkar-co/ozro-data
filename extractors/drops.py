"""Mob drops — mob_db Drops/MvpDrops + map_drops, with OzRo rate adjust (Etapa 3)."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

import yaml

from discovery.scan import _load_extractor_config

# item Type (YAML) → rate family used by mob_drop_ratio_adjust
_TYPE_FAMILY: dict[str, str] = {
    "healing": "heal",
    "usable": "use",
    "delayconsume": "use",
    "cash": "use",
    "weapon": "equip",
    "armor": "equip",
    "petarmor": "equip",
    "shadowgear": "equip",
    "card": "card",
}


def _provenance_id(domain: str, record_id: str, source_path: str) -> str:
    raw = f"{domain}|{record_id}|{source_path}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def _drop_id(*parts: Any) -> str:
    raw = "|".join("" if p is None else str(p) for p in parts)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def _parse_battle_conf(path: Path) -> dict[str, int]:
    out: dict[str, int] = {}
    if not path.is_file():
        return out
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.split("//", 1)[0].strip()
        if not line or ":" not in line:
            continue
        key, _, val = line.partition(":")
        key = key.strip()
        val = val.strip()
        if re.fullmatch(r"-?\d+", val):
            out[key] = int(val)
    return out


def _load_drop_rates(rathena: Path, cfg: dict[str, Any]) -> dict[str, int]:
    """Merge conf/battle/drops.conf then import (rAthena order)."""
    rates: dict[str, int] = {}
    battle_dir = rathena / cfg.get("conf", {}).get("battle_dir", "conf/battle")
    drops_conf = battle_dir / "drops.conf"
    rates.update(_parse_battle_conf(drops_conf))
    # other battle files may redefine; import wins
    import_path = rathena / cfg.get("conf", {}).get(
        "battle_import", "conf/import/battle_conf.txt"
    )
    rates.update(_parse_battle_conf(import_path))
    return rates


def _mob_drop_adjust(
    baserate: int, rate_adjust: int, rate_min: int, rate_max: int
) -> int:
    """Linear path of mob_drop_adjust (logarithmic_drops is off on OzRo)."""
    if rate_adjust == 0:
        return 0
    rate = baserate * rate_adjust / 100.0
    return int(max(rate_min, min(rate_max, rate)))


def _item_family(item_type: str | None) -> str:
    if not item_type:
        return "common"
    return _TYPE_FAMILY.get(str(item_type).lower(), "common")


def _boss_kind(mob: dict[str, Any]) -> str:
    modes = mob.get("modes") if isinstance(mob.get("modes"), dict) else {}
    if mob.get("is_mvp") or modes.get("Mvp") is True:
        return "mvp"
    if mob.get("mob_class") == "Boss":
        return "boss"
    return "normal"


def _is_treasure(mob_row: dict[str, Any]) -> bool:
    rg = mob_row.get("RaceGroups")
    if isinstance(rg, dict):
        return rg.get("Treasure") is True
    return False


def _rate_key_and_bounds(
    family: str, boss_kind: str, treasure: bool, rates: dict[str, int]
) -> tuple[str, int, int, int]:
    if treasure:
        key = "item_rate_treasure"
        return (
            key,
            rates.get(key, 100),
            rates.get("item_drop_treasure_min", 1),
            rates.get("item_drop_treasure_max", 10000),
        )
    # MvpDrops list uses item_rate_mvp exclusively (handled by caller)
    suffix = {"mvp": "_mvp", "boss": "_boss", "normal": ""}[boss_kind]
    key = f"item_rate_{family}{suffix}"
    min_k = f"item_drop_{family}_min"
    max_k = f"item_drop_{family}_max"
    return (
        key,
        rates.get(key, 100),
        rates.get(min_k, 1),
        rates.get(max_k, 10000),
    )


def _load_yaml_bodies(rathena: Path, files: list[str]) -> dict[int, tuple[dict[str, Any], str]]:
    by_id: dict[int, tuple[dict[str, Any], str]] = {}
    for rel in files:
        path = rathena / rel
        if not path.is_file():
            continue
        doc = yaml.safe_load(path.read_text(encoding="utf-8", errors="replace"))
        for row in (doc or {}).get("Body") or []:
            mid = row.get("Id")
            if mid is None:
                continue
            mid = int(mid)
            if mid not in by_id:
                by_id[mid] = (dict(row), rel)
            else:
                merged = dict(by_id[mid][0])
                merged.update(row)
                by_id[mid] = (merged, rel)
    return by_id


def extract_drops(project_root: Path | None = None) -> dict[str, Any]:
    root = project_root or Path(__file__).resolve().parents[1]
    cfg = _load_extractor_config(root)
    rathena = Path(cfg["paths"]["rathena"])
    reports_dir = root / cfg["output"]["reports_dir"]
    reports_dir.mkdir(parents=True, exist_ok=True)

    rates = _load_drop_rates(rathena, cfg)
    mob_files = list(cfg.get("db", {}).get("mob_files") or [])
    mobs_yaml = _load_yaml_bodies(rathena, mob_files)

    # indexes from reports
    item_by_aegis: dict[str, dict[str, Any]] = {}
    item_by_id: dict[int, dict[str, Any]] = {}
    items_path = reports_dir / "items.jsonl"
    if items_path.is_file():
        for line in items_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            it = json.loads(line)
            item_by_id[int(it["item_id"])] = it
            if it.get("aegis_name"):
                item_by_aegis[str(it["aegis_name"])] = it

    mob_meta: dict[int, dict[str, Any]] = {}
    mobs_path = reports_dir / "mobs.jsonl"
    if mobs_path.is_file():
        for line in mobs_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            m = json.loads(line)
            mob_meta[int(m["mob_id"])] = m

    mob_by_aegis: dict[str, int] = {}
    for mid, (row, _) in mobs_yaml.items():
        name = row.get("AegisName")
        if name:
            mob_by_aegis[str(name)] = mid
        if mid not in mob_meta:
            # minimal meta from yaml
            modes = row.get("Modes") if isinstance(row.get("Modes"), dict) else {}
            mob_meta[mid] = {
                "mob_id": mid,
                "aegis_name": name,
                "mob_class": row.get("Class") or "Normal",
                "is_mvp": bool(modes.get("Mvp")),
                "modes": modes,
            }

    records: list[dict[str, Any]] = []
    unresolved_item = 0
    unresolved_mob = 0
    by_category: dict[str, int] = {}
    drop_rateincrease = bool(rates.get("drop_rateincrease", 0))

    def _emit(
        *,
        mob_id: int,
        item_aegis: str,
        rate_original: int,
        category: str,
        source_file: str,
        index: int | None,
        steal_protected: bool | None,
        random_option_group: str | None,
        map_id: str | None,
        rate_key_force: str | None = None,
    ) -> None:
        nonlocal unresolved_item
        it = item_by_aegis.get(item_aegis)
        if not it:
            unresolved_item += 1
            return
        item_id = int(it["item_id"])
        meta = mob_meta.get(mob_id) or {}
        yaml_row = (mobs_yaml.get(mob_id) or ({},))[0]
        treasure = _is_treasure(yaml_row)
        boss_kind = _boss_kind(meta)

        family = (
            "mvp"
            if category == "mvp"
            else _item_family(it.get("type"))
        )
        is_map_bonus = category == "map_specific"

        if is_map_bonus:
            # map_drops.yml: Rate is n/100000; bonus layer on top of mob_db.
            # YAML contract: unaffected by item_rate_*; not stealable.
            # enable_bonus_map_drops runtime path → pending (not applied here).
            rate_key = None
            adj = None
            rate_unit = "per_100000"
            chance_effective = rate_original
            rate_status = "map_yaml_base"
            stealable = False
        elif category == "mvp":
            rate_key = "item_rate_mvp"
            adj = rates.get(rate_key, 100)
            rmin = rates.get("item_drop_mvp_min", 1)
            rmax = rates.get("item_drop_mvp_max", 10000)
            rate_unit = "per_10000"
            base = rate_original
            chance_effective = _mob_drop_adjust(base, adj, rmin, rmax)
            rate_status = "adjusted"
            stealable = False if steal_protected else True
        else:
            rate_key, adj, rmin, rmax = _rate_key_and_bounds(
                family, boss_kind, treasure, rates
            )
            if rate_key_force:
                rate_key = rate_key_force
                adj = rates.get(rate_key, adj)
            rate_unit = "per_10000"
            base = rate_original
            if drop_rateincrease and base < 5000:
                base = base + 1
            chance_effective = _mob_drop_adjust(base, adj, rmin, rmax)
            # Flag MVP-normal rows whose *_mvp key is still default 100 (1x)
            rate_status = "adjusted"
            if (
                boss_kind == "mvp"
                and rate_key
                and rate_key.endswith("_mvp")
                and adj == 100
            ):
                rate_status = "pending_config_verify"
            stealable = False if steal_protected else True

        did = _drop_id(
            category,
            mob_id,
            item_id,
            index,
            map_id,
            rate_original,
            source_file,
        )
        rec = {
            "drop_id": did,
            "mob_id": mob_id,
            "item_id": item_id,
            "item_aegis_name": item_aegis,
            "drop_category": category,
            "is_map_bonus": is_map_bonus,
            "drop_slot": index,
            "chance_base": rate_original,
            "chance_effective": chance_effective,
            "rate_unit": rate_unit,
            "rate_key": rate_key,
            "rate_adjust": adj,
            "rate_status": rate_status,
            "boss_kind": boss_kind if category != "mvp" else "mvp",
            "item_family": family,
            "stealable": stealable,
            "random_option_group": random_option_group,
            "map_id": map_id,
            "source_file": source_file,
            "provenance_id": _provenance_id("drops", did, source_file),
        }
        records.append(rec)
        by_category[category] = by_category.get(category, 0) + 1

    # --- mob_db Drops / MvpDrops ---
    for mid, (row, src) in mobs_yaml.items():
        for i, d in enumerate(row.get("Drops") or []):
            if not isinstance(d, dict):
                continue
            item = d.get("Item")
            rate = d.get("Rate")
            if item is None or rate is None:
                continue
            _emit(
                mob_id=mid,
                item_aegis=str(item),
                rate_original=int(rate),
                category="normal",
                source_file=src,
                index=d.get("Index", i),
                steal_protected=bool(d.get("StealProtected")),
                random_option_group=d.get("RandomOptionGroup"),
                map_id=None,
            )
        for i, d in enumerate(row.get("MvpDrops") or []):
            if not isinstance(d, dict):
                continue
            item = d.get("Item")
            rate = d.get("Rate")
            if item is None or rate is None:
                continue
            _emit(
                mob_id=mid,
                item_aegis=str(item),
                rate_original=int(rate),
                category="mvp",
                source_file=src,
                index=d.get("Index", i),
                steal_protected=bool(d.get("StealProtected")),
                random_option_group=d.get("RandomOptionGroup"),
                map_id=None,
            )

    # --- map_drops.yml ---
    map_drops_path = rathena / "db/re/map_drops.yml"
    map_drop_rows = 0
    if map_drops_path.is_file():
        mdoc = yaml.safe_load(
            map_drops_path.read_text(encoding="utf-8", errors="replace")
        )
        for entry in (mdoc or {}).get("Body") or []:
            map_id = entry.get("Map")
            for sd in entry.get("SpecificDrops") or []:
                mon = sd.get("Monster")
                mid = mob_by_aegis.get(str(mon)) if mon else None
                if mid is None:
                    unresolved_mob += 1
                    continue
                for i, d in enumerate(sd.get("Drops") or []):
                    if not isinstance(d, dict):
                        continue
                    item = d.get("Item")
                    rate = d.get("Rate")
                    if item is None or rate is None:
                        continue
                    map_drop_rows += 1
                    _emit(
                        mob_id=mid,
                        item_aegis=str(item),
                        rate_original=int(rate),
                        category="map_specific",
                        source_file="db/re/map_drops.yml",
                        index=d.get("Index", i),
                        steal_protected=bool(d.get("StealProtected")),
                        random_option_group=d.get("RandomOptionGroup"),
                        map_id=str(map_id) if map_id else None,
                    )

    out_path = reports_dir / "drops.jsonl"
    with out_path.open("w", encoding="utf-8") as f:
        for row in records:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    by_rate_status: dict[str, int] = {}
    for r in records:
        st = r.get("rate_status") or "?"
        by_rate_status[st] = by_rate_status.get(st, 0) + 1

    summary = {
        "domain": "drops",
        "drop_count": len(records),
        "unique_mobs": len({r["mob_id"] for r in records}),
        "unique_items": len({r["item_id"] for r in records}),
        "by_category": by_category,
        "by_rate_status": by_rate_status,
        "map_drop_rows": map_drop_rows,
        "map_bonus_note": "per_100000; no item_rate_*; stealable=false; bonus layer",
        "unresolved_item": unresolved_item,
        "unresolved_mob": unresolved_mob,
        "rates_snapshot": {
            k: rates[k]
            for k in sorted(rates)
            if k.startswith("item_rate_") or k.startswith("item_drop_")
        },
        "deferred": [
            "item_rate_mvp_family_config_verify",
            "enable_bonus_map_drops_runtime",
            "mob_item_ratio_yml",
            "script_event_drops",
            "vip_luk_runtime_modifiers",
            "logarithmic_drops",
        ],
        "wrote": str(out_path),
    }
    summary_path = reports_dir / "drops_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    summary["summary_path"] = str(summary_path)
    return summary
