"""Etapa 3 closure sanity — trash_bin refs, barter integrity, key report presence."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from discovery.scan import _load_extractor_config


def extract_closure_sanity(project_root: Path | None = None) -> dict[str, Any]:
    root = project_root or Path(__file__).resolve().parents[1]
    cfg = _load_extractor_config(root)
    rathena = Path(cfg["paths"]["rathena"])
    reports_dir = root / cfg["output"]["reports_dir"]
    reports_dir.mkdir(parents=True, exist_ok=True)

    # Live tree must not reference trash_bin (even in comments — OzRo rule)
    live_roots = [
        rathena / "npc" / "re",
        rathena / "npc" / "custom",
        rathena / "conf",
        rathena / "db" / "re",
        rathena / "db" / "import",
        rathena / "src",
    ]
    trash_hits: list[str] = []
    for base in live_roots:
        if not base.exists():
            continue
        for path in base.rglob("*"):
            if not path.is_file():
                continue
            if "trash_bin" in str(path):
                continue
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except Exception:
                continue
            if "trash_bin" in text:
                rel = str(path.relative_to(rathena))
                trash_hits.append(rel)

    # Barters: unresolved must be 0 after purge
    barters_summary = {}
    bs = reports_dir / "barters_summary.json"
    if bs.is_file():
        barters_summary = json.loads(bs.read_text(encoding="utf-8"))

    # Dead names must not appear in live barter YAML
    dead_needles = [
        "SuNoviceStone_Top",
        "SuNoviceStone_Middle",
        "SuNoviceStone_Bottom",
        "SuNoviceStone_Robe",
        "barter_mall_coupon_1",
        "barter_mall_coupon_2",
        "barter_mall_coupon_3",
        "barter_mall_coupon_4",
        "Coupon_FateSinBoots",
        "Coupon_GoodnEvil_Helm",
        "Coupon_Justice_Weapon",
        "Coupon_Injustice_Weapon",
    ]
    dead_live: list[str] = []
    for yml in (rathena / "npc/re/merchants/barters").rglob("*.yml"):
        text = yml.read_text(encoding="utf-8", errors="replace")
        for n in dead_needles:
            if n in text:
                dead_live.append(f"{yml.relative_to(rathena)}:{n}")

    # callshop targets for cookie stones must still resolve
    cookie_shops = [
        "barter_stone_top",
        "barter_stone_mid",
        "barter_stone_low",
        "barter_stone_garment",
        "barter_stone_dual",
        "barter_costume_1",
        "barter_costume_2",
    ]
    barter_names: set[str] = set()
    bp = reports_dir / "barters.jsonl"
    if bp.is_file():
        for line in bp.read_text(encoding="utf-8").splitlines():
            if line.strip():
                barter_names.add(json.loads(line)["barter_name"])
    missing_cookie = [n for n in cookie_shops if n not in barter_names]

    required_reports = [
        "random_options_summary.json",
        "barters_summary.json",
        "npc_enchants_summary.json",
        "acquisition_summary.json",
        "item_dependencies_summary.json",
        "npc_script_rewards_summary.json",
        "npc_item_transforms.jsonl",
    ]
    missing_reports = [n for n in required_reports if not (reports_dir / n).is_file()]

    ok = (
        not trash_hits
        and not dead_live
        and not missing_cookie
        and barters_summary.get("unresolved_item", -1) == 0
        and barters_summary.get("skipped_no_client_offer", -1) == 0
        and not missing_reports
    )

    summary = {
        "domain": "closure_sanity",
        "ok": ok,
        "trash_bin_refs_in_live": trash_hits,
        "dead_barter_refs_in_live": dead_live,
        "cookie_callshop_missing_barters": missing_cookie,
        "barters_unresolved_item": barters_summary.get("unresolved_item"),
        "barters_skipped_no_client_offer": barters_summary.get(
            "skipped_no_client_offer"
        ),
        "barter_count": barters_summary.get("barter_count"),
        "missing_reports": missing_reports,
        "smoke_maps": [
            {"map": "malangdo", "npc": "Mysterious Cookie Shop", "xy": [124, 152]},
            {"map": "payon", "npc": "Seiyablem#pay", "xy": [140, 151]},
            {"map": "morocc", "npc": "Seiyablem#moc", "xy": [51, 41]},
            {"map": "morocc", "npc": "Leablem#moc", "xy": [270, 159]},
            {"map": "prt_in", "npc": "Seiyablem#prt", "xy": [33, 70]},
            {"map": "lhz_in02", "npc": "Seiyablem#lhz", "xy": [281, 35]},
        ],
    }
    summary_path = reports_dir / "etapa3_closure_sanity.json"
    summary_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    summary["summary_path"] = str(summary_path)
    return summary
