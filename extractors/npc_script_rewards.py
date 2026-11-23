"""NPC → item deliveries (Pre-E5).

Literal getitem / getitembound / getitem2 in scripts. Relation only
(npc delivers X [/ modified]); conditions out of scope. Not produce/boxes.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

import yaml

from discovery.scan import _load_extractor_config
from extractors.client_scope import load_client_item_ids
from extractors.npcs import parse_npc_line

_SCRIPT_NPC_RE = re.compile(
    r"^(?:-|[A-Za-z0-9_@-]+,-?\d+,-?\d+,\d+)\tscript\t"
)
_GETITEM_RE = re.compile(
    r"\b(?P<cmd>getitem|getitembound)\s+(?P<id>\d+)\s*,\s*(?P<qty>\d+)\b",
    re.IGNORECASE,
)
# getitem2 item_id,amount,identify,refine,attribute,card1,card2,card3,card4
_GETITEM2_RE = re.compile(
    r"\b(?P<cmd>getitem2|getitembound2)\s+"
    r"(?P<id>\d+)\s*,\s*(?P<qty>\d+)\s*,\s*"
    r"(?P<identify>\d+)\s*,\s*(?P<refine>\d+)\s*,\s*(?P<attribute>\d+)\s*,\s*"
    r"(?P<c1>\d+)\s*,\s*(?P<c2>\d+)\s*,\s*(?P<c3>\d+)\s*,\s*(?P<c4>\d+)\b",
    re.IGNORECASE,
)


def _provenance_id(domain: str, record_id: str, source_path: str) -> str:
    raw = f"{domain}|{record_id}|{source_path}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def _eid(*parts: Any) -> str:
    raw = "|".join("" if p is None else str(p) for p in parts)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def _enclosing_script_npc(
    lines: list[str], line_no: int, script_path: str
) -> dict[str, Any] | None:
    for i in range(line_no - 1, -1, -1):
        raw = lines[i].split("//", 1)[0].rstrip()
        if not _SCRIPT_NPC_RE.match(raw):
            continue
        return parse_npc_line(raw, script_path, i + 1)
    return None


def extract_npc_script_rewards(project_root: Path | None = None) -> dict[str, Any]:
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
    disc = (
        yaml.safe_load(files_path.read_text(encoding="utf-8"))
        if files_path.is_file()
        else {}
    )
    scripts: list[str] = list(disc.get("scripts") or [])

    rows: list[dict[str, Any]] = []
    unresolved = 0
    missing_caller = 0
    by_cmd: dict[str, int] = {}
    by_delivery: dict[str, int] = {}

    def _emit(
        *,
        rel: str,
        line_no: int,
        lines: list[str],
        cmd: str,
        iid: int,
        qty: int,
        modified: bool,
        refine: int | None = None,
        identify: int | None = None,
        attribute: int | None = None,
        cards: list[int] | None = None,
    ) -> None:
        nonlocal unresolved, missing_caller
        if iid not in item_ids or iid not in client_ids:
            unresolved += 1
            return
        caller = _enclosing_script_npc(lines, line_no, rel)
        npc_id = caller["npc_id"] if caller else None
        if npc_id is None:
            missing_caller += 1
        delivery_kind = "npc_delivery_modified" if modified else "npc_delivery"
        rid = _eid("npcreward", rel, line_no, cmd, iid, qty, refine, cards)
        row: dict[str, Any] = {
            "npc_script_reward_id": rid,
            "acquisition_type": "npc_delivery",
            "delivery_kind": delivery_kind,
            "npc_id": npc_id,
            "script_path": rel,
            "script_line": line_no,
            "command": cmd,
            "item_id": iid,
            "quantity": qty,
            "is_modified": modified,
            "map_id": caller.get("map_id") if caller else None,
            "provenance_id": _provenance_id(
                "npc_script_rewards", rid, f"{rel}:{line_no}"
            ),
        }
        if modified:
            row["identify"] = identify
            row["refine"] = refine
            row["attribute"] = attribute
            row["cards"] = cards
        rows.append(row)
        by_cmd[cmd] = by_cmd.get(cmd, 0) + 1
        by_delivery[delivery_kind] = by_delivery.get(delivery_kind, 0) + 1

    for rel in scripts:
        path = rathena / rel
        if not path.is_file():
            continue
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        for line_no, raw in enumerate(lines, 1):
            line = raw.split("//", 1)[0]
            for m in _GETITEM2_RE.finditer(line):
                _emit(
                    rel=rel,
                    line_no=line_no,
                    lines=lines,
                    cmd=m.group("cmd").lower(),
                    iid=int(m.group("id")),
                    qty=int(m.group("qty")),
                    modified=True,
                    identify=int(m.group("identify")),
                    refine=int(m.group("refine")),
                    attribute=int(m.group("attribute")),
                    cards=[
                        int(m.group("c1")),
                        int(m.group("c2")),
                        int(m.group("c3")),
                        int(m.group("c4")),
                    ],
                )
            for m in _GETITEM_RE.finditer(line):
                _emit(
                    rel=rel,
                    line_no=line_no,
                    lines=lines,
                    cmd=m.group("cmd").lower(),
                    iid=int(m.group("id")),
                    qty=int(m.group("qty")),
                    modified=False,
                )

    out_path = reports_dir / "npc_script_rewards.jsonl"
    with out_path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    summary = {
        "domain": "npc_script_rewards",
        "acquisition_type": "npc_delivery",
        "reward_rows": len(rows),
        "unique_items": len({r["item_id"] for r in rows}),
        "unique_npcs": len({r["npc_id"] for r in rows if r["npc_id"]}),
        "by_command": by_cmd,
        "by_delivery_kind": by_delivery,
        "unresolved_item": unresolved,
        "missing_caller": missing_caller,
        "note": (
            "NPC→item relation only (branch/conditions ignored). "
            "Not produce_db / item_group. Literals only; variables omitted."
        ),
        "wrote": [str(out_path)],
    }
    summary_path = reports_dir / "npc_script_rewards_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    summary["summary_path"] = str(summary_path)
    return summary
