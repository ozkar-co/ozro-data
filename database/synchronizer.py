"""Full-replace sync: reports/*.jsonl → ozro_* tables."""

from __future__ import annotations

import hashlib
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from .connection import connect, load_database_config
from .schema_apply import list_ozro_tables

RESERVED = frozenset({"group", "key", "index", "rank", "trigger", "order", "status"})
JSON_SQL_TYPES = frozenset({"JSON"})


def _load_specs(project_root: Path) -> dict[str, Any]:
    path = project_root / "database" / "table_specs.json"
    return json.loads(path.read_text(encoding="utf-8"))


def _qcol(name: str) -> str:
    return f"`{name}`" if name in RESERVED else f"`{name}`"


def _coerce(value: Any, sql_type: str) -> Any:
    if value is None:
        return None
    if sql_type == "JSON" or isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    if sql_type.startswith("TINYINT"):
        return 1 if value else 0
    if sql_type.startswith("INT") or sql_type == "BIGINT":
        if isinstance(value, bool):
            return int(value)
        return int(value)
    if sql_type == "DOUBLE":
        return float(value)
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, bool):
        return 1 if value else 0
    return value


def _iter_jsonl(path: Path) -> Iterable[dict[str, Any]]:
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                yield json.loads(line)


def _hash_file(path: Path, *, chunk_size: int = 1024 * 1024) -> bytes:
    """SHA-256 of file contents without loading the whole file into RAM."""
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            h.update(chunk)
    return h.digest()


def _fingerprint(paths: list[Path]) -> str:
    h = hashlib.sha256()
    for p in sorted(paths, key=lambda x: str(x)):
        h.update(p.name.encode())
        h.update(b"\0")
        if p.is_file():
            h.update(_hash_file(p))
    return h.hexdigest()


def sync_dataset(project_root: Path) -> dict[str, Any]:
    t0 = time.time()
    cfg = load_database_config(project_root)
    prefix = cfg["table_prefix"]
    specs = _load_specs(project_root)
    reports = project_root / "reports"
    load_order: list[str] = list(specs["load_order"])
    tables: dict[str, Any] = specs["tables"]

    # Preflight: required JSONL present
    missing: list[str] = []
    jsonl_paths: list[Path] = []
    for table in load_order:
        jl = tables[table].get("jsonl")
        if not jl:
            continue
        path = reports / jl
        if not path.is_file():
            missing.append(jl)
        else:
            jsonl_paths.append(path)
    if missing:
        raise FileNotFoundError(
            "Missing report JSONL required for sync: " + ", ".join(missing)
        )

    schema_path = project_root / "database" / "schema" / "001_master.sql"
    fp = _fingerprint(jsonl_paths + [schema_path, project_root / "database" / "table_specs.json"])

    conn, _ = connect(project_root)
    counts: dict[str, int] = {}
    provenance: dict[str, dict[str, Any]] = {}

    try:
        with conn.cursor() as cur:
            cur.execute("SET FOREIGN_KEY_CHECKS=0")
            cur.execute("SET UNIQUE_CHECKS=0")
            cur.execute("SET AUTOCOMMIT=0")

            # Truncate all ozro_* tables currently present
            existing = list_ozro_tables(conn, prefix)
            for name in existing:
                cur.execute(f"TRUNCATE TABLE `{name}`")

            for table in load_order:
                if table in ("source_provenance", "dataset_metadata"):
                    continue
                full = f"{prefix}{table}"
                spec = tables[table]
                cols: list[str] = list(spec["columns"])
                types: dict[str, str] = spec["column_types"]
                jl = spec.get("jsonl")

                if table == "npc_functions":
                    n = _sync_npc_functions(cur, reports, prefix, provenance)
                    counts[table] = n
                    continue
                if table == "npc_shop_link_shops":
                    n = _sync_shop_link_shops(cur, reports, prefix)
                    counts[table] = n
                    continue

                assert jl
                path = reports / jl
                col_sql = ", ".join(_qcol(c) for c in cols)
                placeholders = ", ".join(["%s"] * len(cols))
                insert_sql = (
                    f"INSERT INTO `{full}` ({col_sql}) VALUES ({placeholders})"
                )
                batch: list[tuple[Any, ...]] = []
                batch_size = 2000 if table in ("map_distances", "map_routes") else 500
                n = 0
                unknown_keys: set[str] = set()
                # list_index: preserve duplicate natural keys (e.g. same item listed
                # multiple times in a shop header / acquisition union).
                list_index_counters: dict[Any, int] = {}
                inject_list_index = "list_index" in cols
                for row in _iter_jsonl(path):
                    extras = set(row.keys()) - set(cols)
                    # Allowed extras that we intentionally skip
                    if table == "npc_shop_links":
                        extras.discard("shop_ids")
                    if table == "npcs":
                        extras.discard("functions")
                    if table == "instances":
                        extras.discard("maps")
                    if inject_list_index:
                        extras.discard("list_index")
                    if extras:
                        unknown_keys |= extras
                    row_out = dict(row)
                    if inject_list_index:
                        if table == "npc_shop_items":
                            ck = row.get("shop_id")
                        elif table == "acquisition_outputs":
                            ck = row.get("acquisition_output_id")
                        else:
                            ck = "_global"
                        idx = list_index_counters.get(ck, 0)
                        list_index_counters[ck] = idx + 1
                        row_out["list_index"] = idx
                    # PK ints that extracts omit → 0 (quest_targets.mob_subindex)
                    if table == "quest_targets" and row_out.get("mob_subindex") is None:
                        row_out["mob_subindex"] = 0
                    values = tuple(_coerce(row_out.get(c), types[c]) for c in cols)
                    batch.append(values)
                    n += 1
                    _collect_provenance(provenance, table, row)
                    if len(batch) >= batch_size:
                        cur.executemany(insert_sql, batch)
                        batch.clear()
                if batch:
                    cur.executemany(insert_sql, batch)
                if unknown_keys:
                    raise ValueError(
                        f"{jl}: unexpected keys not in schema for {table}: "
                        f"{sorted(unknown_keys)}"
                    )
                counts[table] = n

            # Provenance derived
            n_prov = _insert_provenance(cur, prefix, provenance)
            counts["source_provenance"] = n_prov

            # Metadata last
            version = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            notes = {
                "row_counts": counts,
                "prefix": prefix,
                "sync": "full_replace",
            }
            cur.execute(
                f"INSERT INTO `{prefix}dataset_metadata` "
                f"(`dataset_version`, `generated_at`, `source_fingerprint`, `notes`) "
                f"VALUES (%s, %s, %s, %s)",
                (
                    version,
                    datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
                    fp,
                    json.dumps(notes, ensure_ascii=False),
                ),
            )
            counts["dataset_metadata"] = 1

            cur.execute("SET UNIQUE_CHECKS=1")
            cur.execute("SET FOREIGN_KEY_CHECKS=1")
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    elapsed = round(time.time() - t0, 3)
    summary = {
        "command": "sync",
        "dataset_version": version,
        "source_fingerprint": fp,
        "prefix": prefix,
        "elapsed_seconds": elapsed,
        "row_counts": counts,
        "total_rows": sum(counts.values()),
    }
    out = reports / "sync_summary.json"
    out.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    summary["wrote"] = [str(out)]
    return summary


def _collect_provenance(
    bag: dict[str, dict[str, Any]], table: str, row: dict[str, Any]
) -> None:
    pid = row.get("provenance_id")
    if not pid or pid in bag:
        return
    record_id = None
    for key in (
        "recipe_id",
        "drop_id",
        "spawn_id",
        "shop_id",
        "npc_id",
        "item_id",
        "mob_id",
        "map_id",
        "quest_id",
        "box_id",
        "penalty_id",
        "enchant_id",
        "barter_id",
        "connection_id",
        "instance_id",
        "summon_id",
        "acquisition_output_id",
        "npc_script_reward_id",
    ):
        if key in row and row[key] is not None:
            record_id = str(row[key])
            break
    bag[pid] = {
        "provenance_id": pid,
        "domain": table,
        "record_id": record_id or "",
        "source_kind": row.get("source_kind") or "extract",
        "source_path": row.get("source_file") or row.get("script_path") or "",
        "source_ref": str(row.get("source_line") or "") or None,
        "transform": "jsonl_sync",
    }


def _insert_provenance(cur, prefix: str, bag: dict[str, dict[str, Any]]) -> int:
    if not bag:
        return 0
    cols = [
        "provenance_id",
        "domain",
        "record_id",
        "source_kind",
        "source_path",
        "source_ref",
        "transform",
    ]
    sql = (
        f"INSERT INTO `{prefix}source_provenance` ("
        + ", ".join(f"`{c}`" for c in cols)
        + ") VALUES ("
        + ", ".join(["%s"] * len(cols))
        + ")"
    )
    rows = [tuple(r[c] for c in cols) for r in bag.values()]
    # batch
    for i in range(0, len(rows), 1000):
        cur.executemany(sql, rows[i : i + 1000])
    return len(rows)


def _sync_npc_functions(cur, reports: Path, prefix: str, provenance: dict) -> int:
    path = reports / "npcs.jsonl"
    sql = (
        f"INSERT INTO `{prefix}npc_functions` (`npc_id`, `function_name`) "
        f"VALUES (%s, %s)"
    )
    batch: list[tuple[str, str]] = []
    n = 0
    seen: set[tuple[str, str]] = set()
    for row in _iter_jsonl(path):
        npc_id = row.get("npc_id")
        funcs = row.get("functions") or []
        if not npc_id:
            continue
        for fn in funcs:
            key = (str(npc_id), str(fn))
            if key in seen:
                continue
            seen.add(key)
            batch.append(key)
            n += 1
            if len(batch) >= 1000:
                cur.executemany(sql, batch)
                batch.clear()
        _collect_provenance(provenance, "npcs", row)
    if batch:
        cur.executemany(sql, batch)
    return n


def _sync_shop_link_shops(cur, reports: Path, prefix: str) -> int:
    path = reports / "npc_shop_links.jsonl"
    sql = (
        f"INSERT INTO `{prefix}npc_shop_link_shops` (`link_id`, `shop_id`) "
        f"VALUES (%s, %s)"
    )
    batch: list[tuple[str, str]] = []
    n = 0
    for row in _iter_jsonl(path):
        link_id = row.get("link_id")
        for shop_id in row.get("shop_ids") or []:
            batch.append((str(link_id), str(shop_id)))
            n += 1
            if len(batch) >= 1000:
                cur.executemany(sql, batch)
                batch.clear()
    if batch:
        cur.executemany(sql, batch)
    return n
