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


def main() -> int:
    parser = argparse.ArgumentParser(prog="ozro-data")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p_disc = sub.add_parser("discover", help="Etapa 1: scan sources and write manifest")
    p_disc.set_defaults(func=cmd_discover)
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
