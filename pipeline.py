#!/usr/bin/env python3
"""OzRo Master World Dataset pipeline entrypoint."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def cmd_discover(_: argparse.Namespace) -> int:
    from discovery import run_discovery

    report = run_discovery(ROOT)
    summary = {
        "maps": report["maps"]["enabled_count"],
        "npc_scripts": report["npc"]["script_count"],
        "ozro_custom": report["npc"]["ozro_custom_count"],
        "warp_scripts": report["npc"]["warp_script_count"],
        "mob_scripts": report["npc"]["mob_script_count"],
        "missing_scripts": len(report["npc"]["missing_scripts"]),
        "rates_keys": sorted(report["rates"].keys()),
        "wrote": report["_wrote"],
    }
    print(json.dumps(summary, indent=2))
    missing_files = [
        p for p, ok in report["path_checks"]["rathena_files"].items() if not ok
    ]
    missing_grf = [p for p, ok in report["path_checks"]["client_grfs"].items() if not ok]
    if missing_files or missing_grf:
        print("MISSING:", file=sys.stderr)
        for p in missing_files:
            print(f"  rathena:{p}", file=sys.stderr)
        for p in missing_grf:
            print(f"  cli:{p}", file=sys.stderr)
        return 1
    return 0


def cmd_resolve(_: argparse.Namespace) -> int:
    """Etapa 4: dump effective battle configuration snapshot."""
    from resolvers import ConfigurationResolver

    resolver = ConfigurationResolver.from_project(ROOT)
    snap = resolver.snapshot()
    reports = ROOT / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    out = reports / "configuration_effective.json"
    out.write_text(json.dumps(snap, indent=2) + "\n", encoding="utf-8")
    # Flat rows for future ozro_dataset_rates (Etapa 5).
    catalog_path = reports / "dataset_rates.jsonl"
    with catalog_path.open("w", encoding="utf-8") as f:
        for row in snap.get("catalog") or []:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(
        json.dumps(
            {
                "command": "resolve",
                "schema_version": snap.get("schema_version"),
                "catalog_count": snap.get("catalog_count"),
                "sources": snap["sources"],
                "ozro_highlights": snap["ozro_highlights"],
                "wrote": [str(out), str(catalog_path)],
            },
            indent=2,
        )
    )
    return 0


def cmd_extract(args: argparse.Namespace) -> int:
    domain = args.domain
    if domain == "maps":
        from extractors import extract_maps

        summary = extract_maps(ROOT)
    elif domain == "mobs":
        from extractors import extract_mobs

        summary = extract_mobs(ROOT)
    elif domain == "items":
        from extractors import extract_items

        summary = extract_items(ROOT)
    elif domain == "npcs":
        from extractors import extract_npcs

        summary = extract_npcs(ROOT)
    elif domain == "map_connections":
        from extractors import extract_connections

        summary = extract_connections(ROOT)
    elif domain == "map_distances":
        from extractors import extract_map_distances

        summary = extract_map_distances(ROOT)
    elif domain == "skills":
        from extractors import extract_skills

        summary = extract_skills(ROOT)
    elif domain == "spawns":
        from extractors import extract_spawns

        summary = extract_spawns(ROOT)
    elif domain == "shops":
        from extractors import extract_shops

        summary = extract_shops(ROOT)
    elif domain == "npc_scripts":
        from extractors import extract_npc_scripts

        summary = extract_npc_scripts(ROOT)
    elif domain == "item_scripts":
        from extractors import extract_item_scripts

        summary = extract_item_scripts(ROOT)
    elif domain == "item_restrictions":
        from extractors import extract_item_restrictions

        summary = extract_item_restrictions(ROOT)
    elif domain == "drops":
        from extractors import extract_drops

        summary = extract_drops(ROOT)
    elif domain == "quests":
        from extractors import extract_quests

        summary = extract_quests(ROOT)
    elif domain == "instances":
        from extractors import extract_instances

        summary = extract_instances(ROOT)
    elif domain == "boxes":
        from extractors import extract_boxes

        summary = extract_boxes(ROOT)
    elif domain == "recipes":
        from extractors import extract_recipes

        summary = extract_recipes(ROOT)
    elif domain == "enchantments":
        from extractors import extract_enchantments

        summary = extract_enchantments(ROOT)
    elif domain == "item_relationships":
        from extractors import extract_item_relationships

        summary = extract_item_relationships(ROOT)
    elif domain == "random_options":
        from extractors import extract_random_options

        summary = extract_random_options(ROOT)
    elif domain == "barters":
        from extractors import extract_barters

        summary = extract_barters(ROOT)
    elif domain == "npc_enchants":
        from extractors import extract_npc_enchants

        summary = extract_npc_enchants(ROOT)
    elif domain == "acquisition":
        from extractors import extract_acquisition

        summary = extract_acquisition(ROOT)
    elif domain == "item_dependencies":
        from extractors import extract_item_dependencies

        summary = extract_item_dependencies(ROOT)
    elif domain == "npc_script_rewards":
        from extractors import extract_npc_script_rewards

        summary = extract_npc_script_rewards(ROOT)
    elif domain == "closure_sanity":
        from extractors import extract_closure_sanity

        summary = extract_closure_sanity(ROOT)
    elif domain == "level_penalty":
        from extractors import extract_level_penalty

        summary = extract_level_penalty(ROOT)
    else:
        print(f"unknown domain: {domain}", file=sys.stderr)
        return 2
    print(json.dumps(summary, indent=2))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(prog="ozro-data")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p_disc = sub.add_parser("discover", help="Etapa 1: scan sources and write manifest")
    p_disc.set_defaults(func=cmd_discover)
    p_res = sub.add_parser(
        "resolve", help="Etapa 4: merge battle conf and write effective snapshot"
    )
    p_res.set_defaults(func=cmd_resolve)
    p_ext = sub.add_parser("extract", help="Etapa 2+: extract a domain")
    p_ext.add_argument(
        "domain",
        choices=[
            "maps",
            "mobs",
            "items",
            "npcs",
            "map_connections",
            "map_distances",
            "skills",
            "spawns",
            "shops",
            "npc_scripts",
            "item_scripts",
            "item_restrictions",
            "drops",
            "quests",
            "instances",
            "boxes",
            "recipes",
            "enchantments",
            "item_relationships",
            "random_options",
            "barters",
            "npc_enchants",
            "acquisition",
            "item_dependencies",
            "npc_script_rewards",
            "closure_sanity",
            "level_penalty",
        ],
        help="entity domain to extract",
    )
    p_ext.set_defaults(func=cmd_extract)
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
