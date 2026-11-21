"""Recipes — produce_db.txt (+ import) (Etapa 3)."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from discovery.scan import _load_extractor_config
from extractors.client_scope import load_client_item_ids

# ItemLV → family (from produce_db section comments).
_ITEMLV_FAMILY: list[tuple[range, str]] = [
    (range(1, 4), "weapon"),
    (range(11, 21), "cooking"),
    (range(21, 22), "stones_metals"),
    (range(22, 23), "potions"),
    (range(23, 24), "elemental_converters"),
    (range(24, 25), "ancilla_runes"),
    (range(25, 26), "gx_poisons"),
    (range(26, 27), "change_material"),
    (range(27, 28), "mix_cooking"),
    (range(28, 29), "create_bomb"),
    (range(29, 30), "special_pharmacy"),
    (range(30, 31), "cooking_extended"),
    (range(31, 32), "manufacture_machine"),
    (range(32, 33), "bionic_pharmacy"),
]


def _provenance_id(domain: str, record_id: str, source_path: str) -> str:
    raw = f"{domain}|{record_id}|{source_path}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def _family(item_lv: int) -> str:
    for rng, name in _ITEMLV_FAMILY:
        if item_lv in rng:
            return name
    return "other"


def _load_skill_names(rathena: Path) -> dict[int, str]:
    """skill_db.yml uses Name: (not AegisName). Line-scan — file is large."""
    path = rathena / "db/re/skill_db.yml"
    by: dict[int, str] = {}
    if not path.is_file():
        return by
    cur: int | None = None
    for ln in path.read_text(encoding="utf-8", errors="replace").splitlines():
        m = re.match(r"^  - Id: (\d+)\b", ln)
        if m:
            cur = int(m.group(1))
            continue
        if cur is None:
            continue
        m = re.match(r"^    Name: (\S+)", ln)
        if m:
            by[cur] = m.group(1)
            cur = None
    return by


def _parse_produce_file(path: Path) -> dict[int, tuple[dict[str, Any], int]]:
    """produce_id → (row, line_no). Later files overwrite same ID."""
    out: dict[int, tuple[dict[str, Any], int]] = {}
    if not path.is_file():
        return out
    for line_no, raw in enumerate(
        path.read_text(encoding="utf-8", errors="replace").splitlines(), start=1
    ):
        line = raw.split("//", 1)[0].strip()
        if not line or not line[0].isdigit():
            continue
        parts = [p.strip() for p in line.split(",")]
        if len(parts) < 5:
            continue
        try:
            nums = [int(p) for p in parts]
        except ValueError:
            continue
        produce_id = nums[0]
        result_id = nums[1]
        item_lv = nums[2]
        req_skill = nums[3]
        req_skill_lv = nums[4]
        materials: list[dict[str, Any]] = []
        rest = nums[5:]
        for i in range(0, len(rest) - 1, 2):
            mid, amt = rest[i], rest[i + 1]
            materials.append(
                {
                    "item_id": mid,
                    "amount": amt,
                    # amount 0 = must hold in inventory (guide), not consumed
                    "role": "guide" if amt == 0 else "consumed",
                }
            )
        out[produce_id] = (
            {
                "produce_id": produce_id,
                "result_item_id": result_id,
                "item_lv": item_lv,
                "require_skill_id": req_skill,
                "require_skill_lv": req_skill_lv,
                "materials": materials,
            },
            line_no,
        )
    return out


def extract_recipes(project_root: Path | None = None) -> dict[str, Any]:
    root = project_root or Path(__file__).resolve().parents[1]
    cfg = _load_extractor_config(root)
    rathena = Path(cfg["paths"]["rathena"])
    reports_dir = root / cfg["output"]["reports_dir"]
    reports_dir.mkdir(parents=True, exist_ok=True)
    client_ids = load_client_item_ids(reports_dir)

    item_name: dict[int, str] = {}
    items_path = reports_dir / "items.jsonl"
    if items_path.is_file():
        for line in items_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            it = json.loads(line)
            item_name[int(it["item_id"])] = str(it.get("aegis_name") or "")

    skill_names = _load_skill_names(rathena)

    files = [
        "db/re/produce_db.txt",
        "db/import/produce_db.txt",
    ]
    merged: dict[int, tuple[dict[str, Any], str, int]] = {}
    for rel in files:
        path = rathena / rel
        for pid, (row, line_no) in _parse_produce_file(path).items():
            merged[pid] = (row, rel, line_no)

    recipes: list[dict[str, Any]] = []
    materials_out: list[dict[str, Any]] = []
    skipped_removed = 0
    skipped_no_client = 0
    unresolved_material = 0
    by_family: dict[str, int] = {}

    for pid in sorted(merged):
        row, src, line_no = merged[pid]
        result_id = int(row["result_item_id"])
        # import delete: ProduceItemID 0
        if result_id == 0:
            skipped_removed += 1
            continue
        if result_id not in client_ids:
            skipped_no_client += 1
            continue

        item_lv = int(row["item_lv"])
        family = _family(item_lv)
        by_family[family] = by_family.get(family, 0) + 1
        req_skill = int(row["require_skill_id"])
        req_lv = int(row["require_skill_lv"])
        recipe_id = hashlib.sha1(f"recipe|produce|{pid}".encode()).hexdigest()

        recipes.append(
            {
                "recipe_id": recipe_id,
                "produce_id": pid,
                "recipe_family": family,
                "item_lv": item_lv,
                "result_item_id": result_id,
                "result_aegis_name": item_name.get(result_id) or None,
                "result_amount": 1,
                "require_skill_id": req_skill if req_skill else None,
                "require_skill_name": skill_names.get(req_skill) if req_skill else None,
                "require_skill_lv": req_lv if req_skill else None,
                "zeny_cost": None,
                "success_rate": None,
                "fail_result_item_id": None,
                "source_kind": "produce_db",
                "source_file": src,
                "source_line": line_no,
                "provenance_id": _provenance_id(
                    "recipes", recipe_id, f"{src}:{line_no}"
                ),
            }
        )

        for idx, mat in enumerate(row["materials"]):
            mid = int(mat["item_id"])
            if mid not in client_ids:
                unresolved_material += 1
                continue
            mid_key = f"{pid}|{idx}|{mid}"
            mat_id = hashlib.sha1(f"recipemat|{mid_key}".encode()).hexdigest()
            materials_out.append(
                {
                    "recipe_material_id": mat_id,
                    "recipe_id": recipe_id,
                    "produce_id": pid,
                    "item_id": mid,
                    "aegis_name": item_name.get(mid) or None,
                    "amount": int(mat["amount"]),
                    "role": mat["role"],
                    "index": idx,
                    "source_file": src,
                    "provenance_id": _provenance_id(
                        "recipe_materials", mat_id, f"{src}:{line_no}"
                    ),
                }
            )

    r_path = reports_dir / "recipes.jsonl"
    with r_path.open("w", encoding="utf-8") as f:
        for row in recipes:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    m_path = reports_dir / "recipe_materials.jsonl"
    with m_path.open("w", encoding="utf-8") as f:
        for row in materials_out:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    summary = {
        "domain": "recipes",
        "recipe_count": len(recipes),
        "material_rows": len(materials_out),
        "by_family": by_family,
        "skipped_removed": skipped_removed,
        "skipped_no_client": skipped_no_client,
        "unresolved_material": unresolved_material,
        "deferred": [
            "npc_script_crafting",
            "zeny_success_fail_runtime",
            "skill_create_item_links",
        ],
        "wrote": [str(r_path), str(m_path)],
    }
    summary_path = reports_dir / "recipes_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    summary["summary_path"] = str(summary_path)
    return summary
