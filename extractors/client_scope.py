"""Client item scope — playable items = present in client_item_info."""

from __future__ import annotations

import json
from pathlib import Path


def load_client_item_ids(reports_dir: Path) -> set[int]:
    path = reports_dir / "client_item_info.jsonl"
    if not path.is_file():
        raise FileNotFoundError(
            f"Missing {path}; run ozro-cli export_client_inventory first"
        )
    ids: set[int] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        ids.add(int(json.loads(line)["item_id"]))
    return ids
