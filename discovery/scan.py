"""Discover live OzRo sources from rAthena + client GRF paths."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

NPC_LINE = re.compile(r"^\s*npc:\s*(.+?)\s*$")
IMPORT_LINE = re.compile(r"^\s*import:\s*(.+?)\s*$")
MAP_LINE = re.compile(r"^\s*map:\s*(\S+)\s*$")
CONF_KV = re.compile(r"^\s*([A-Za-z0-9_.]+)\s*:\s*(.+?)\s*$")


def _load_extractor_config(root: Path) -> dict[str, Any]:
    path = root / "config" / "extractor.yml"
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f)


def _strip_comment(line: str) -> str:
    if "//" in line:
        return line.split("//", 1)[0]
    return line


def _iter_enabled_conf_lines(path: Path) -> list[str]:
    lines: list[str] = []
    if not path.is_file():
        return lines
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if raw.lstrip().startswith("//"):
            continue
        line = _strip_comment(raw).rstrip()
        if line.strip():
            lines.append(line)
    return lines


def resolve_npc_scripts(rathena: Path, scripts_main: str) -> dict[str, Any]:
    """Recursively resolve enabled npc: and import: from scripts_main."""
    visited_imports: set[str] = set()
    scripts: list[str] = []
    missing: list[str] = []

    def walk(rel: str) -> None:
        if rel in visited_imports:
            return
        visited_imports.add(rel)
        path = rathena / rel
        if not path.is_file():
            missing.append(rel)
            return
        for line in _iter_enabled_conf_lines(path):
            m_npc = NPC_LINE.match(line)
            if m_npc:
                scripts.append(m_npc.group(1).strip())
                continue
            m_imp = IMPORT_LINE.match(line)
            if m_imp:
                walk(m_imp.group(1).strip())

    walk(scripts_main)
    existing = [s for s in scripts if (rathena / s).is_file()]
    missing_scripts = [s for s in scripts if not (rathena / s).is_file()]
    return {
        "scripts_main": scripts_main,
        "import_files": sorted(visited_imports),
        "script_count": len(existing),
        "scripts": sorted(existing),
        "missing_imports": missing,
        "missing_scripts": missing_scripts,
    }


def resolve_maps(rathena: Path, maps_conf: str) -> dict[str, Any]:
    path = rathena / maps_conf
    enabled: list[str] = []
    for line in _iter_enabled_conf_lines(path):
        m = MAP_LINE.match(line)
        if m:
            enabled.append(m.group(1))
    return {
        "maps_conf": maps_conf,
        "enabled_count": len(enabled),
        "maps": sorted(set(enabled)),
    }


def resolve_battle_rates(rathena: Path, battle_import: str) -> dict[str, str]:
    path = rathena / battle_import
    keys_prefix = (
        "item_rate_",
        "base_exp_rate",
        "job_exp_rate",
        "mvp_exp_rate",
        "quest_exp_rate",
        "monster_hp_rate",
        "mvp_hp_rate",
    )
    out: dict[str, str] = {}
    for line in _iter_enabled_conf_lines(path):
        m = CONF_KV.match(line)
        if not m:
            continue
        key, val = m.group(1), m.group(2)
        if key.startswith(keys_prefix) or key in keys_prefix:
            out[key] = val
    return out


def check_paths(rathena: Path, ozro_cli: Path, cfg: dict[str, Any]) -> dict[str, Any]:
    db = cfg["db"]
    client = cfg["client"]
    files: dict[str, bool] = {}
    for rel in (
        list(db["item_files"])
        + list(db["mob_files"])
        + list(db.get("other", []))
        + [cfg["server"]["scripts_main"], cfg["server"]["maps_conf"], cfg["server"]["map_index"]]
        + [cfg["conf"]["battle_import"], cfg["conf"]["inter"]]
    ):
        files[rel] = (rathena / rel).is_file()

    grfs: dict[str, bool] = {}
    for name in client["grf_files"]:
        grfs[f"tmp/{name}"] = (ozro_cli / client["grf_dir"] / name).is_file()
    for rel in client["patch_grf"]:
        grfs[rel] = (ozro_cli / rel).is_file()

    return {"rathena_files": files, "client_grfs": grfs}


def run_discovery(project_root: Path | None = None) -> dict[str, Any]:
    root = project_root or Path(__file__).resolve().parents[1]
    cfg = _load_extractor_config(root)
    rathena = Path(cfg["paths"]["rathena"])
    ozro_cli = Path(cfg["paths"]["ozro_cli"])

    npc = resolve_npc_scripts(rathena, cfg["server"]["scripts_main"])
    maps = resolve_maps(rathena, cfg["server"]["maps_conf"])
    rates = resolve_battle_rates(rathena, cfg["conf"]["battle_import"])
    paths = check_paths(rathena, ozro_cli, cfg)

    ozro_scripts = [s for s in npc["scripts"] if s.startswith("npc/custom/ozro/")]
    warp_scripts = [s for s in npc["scripts"] if "/warps/" in s or s.startswith("npc/warps/")]
    mob_scripts = [s for s in npc["scripts"] if "/mobs/" in s]

    report = {
        "version": 1,
        "paths": {
            "rathena": str(rathena),
            "ozro_cli": str(ozro_cli),
            "rathena_exists": rathena.is_dir(),
            "ozro_cli_exists": ozro_cli.is_dir(),
        },
        "server": {
            "renewal": cfg["server"]["renewal"],
            "use_sql_db": cfg["server"]["use_sql_db"],
            "scripts_main": cfg["server"]["scripts_main"],
        },
        "maps": {
            "enabled_count": maps["enabled_count"],
        },
        "npc": {
            "import_file_count": len(npc["import_files"]),
            "script_count": npc["script_count"],
            "ozro_custom_count": len(ozro_scripts),
            "warp_script_count": len(warp_scripts),
            "mob_script_count": len(mob_scripts),
            "missing_imports": npc["missing_imports"],
            "missing_scripts": npc["missing_scripts"],
            "ozro_custom_scripts": ozro_scripts,
        },
        "rates": rates,
        "path_checks": paths,
        "table_prefix": cfg["output"]["table_prefix"],
    }

    reports_dir = root / cfg["output"]["reports_dir"]
    reports_dir.mkdir(parents=True, exist_ok=True)
    out_path = reports_dir / "discovery_manifest.yml"
    with out_path.open("w", encoding="utf-8") as f:
        yaml.safe_dump(report, f, sort_keys=False, allow_unicode=True)

    # Full script list kept separate (large).
    full = {
        "scripts": npc["scripts"],
        "maps": maps["maps"],
        "import_files": npc["import_files"],
    }
    with (reports_dir / "discovery_files.yml").open("w", encoding="utf-8") as f:
        yaml.safe_dump(full, f, sort_keys=False, allow_unicode=True)

    report["_wrote"] = {
        "manifest": str(out_path),
        "files": str(reports_dir / "discovery_files.yml"),
    }
    return report
