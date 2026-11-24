"""Apply / reset ozro_* schema from database/schema/001_master.sql."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .connection import connect, load_database_config


def _split_sql(sql: str) -> list[str]:
    """Split on semicolons outside of strings (simple DDL splitter)."""
    stmts: list[str] = []
    buf: list[str] = []
    in_single = False
    in_double = False
    i = 0
    while i < len(sql):
        ch = sql[i]
        if ch == "'" and not in_double:
            in_single = not in_single
            buf.append(ch)
        elif ch == '"' and not in_single:
            in_double = not in_double
            buf.append(ch)
        elif ch == ";" and not in_single and not in_double:
            stmt = "".join(buf).strip()
            if stmt:
                stmts.append(stmt)
            buf = []
        else:
            buf.append(ch)
        i += 1
    tail = "".join(buf).strip()
    if tail:
        stmts.append(tail)
    return stmts


def _rewrite_prefix(sql: str, prefix: str) -> str:
    if prefix == "ozro_":
        return sql
    return sql.replace("ozro_", prefix)


def list_ozro_tables(conn, prefix: str) -> list[str]:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT TABLE_NAME FROM information_schema.TABLES "
            "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME LIKE %s "
            "ORDER BY TABLE_NAME",
            (f"{prefix}%",),
        )
        return [r[0] for r in cur.fetchall()]


def apply_schema(project_root: Path, *, reset: bool = False) -> dict[str, Any]:
    cfg = load_database_config(project_root)
    prefix = cfg["table_prefix"]
    schema_path = project_root / "database" / "schema" / "001_master.sql"
    sql = _rewrite_prefix(
        schema_path.read_text(encoding="utf-8"),
        prefix,
    )
    # Strip comments
    cleaned_lines = []
    for line in sql.splitlines():
        if line.strip().startswith("--"):
            continue
        cleaned_lines.append(line)
    sql = "\n".join(cleaned_lines)

    conn, _ = connect(project_root)
    dropped: list[str] = []
    created = 0
    try:
        with conn.cursor() as cur:
            cur.execute("SET FOREIGN_KEY_CHECKS=0")
            if reset:
                for name in list_ozro_tables(conn, prefix):
                    cur.execute(f"DROP TABLE IF EXISTS `{name}`")
                    dropped.append(name)
            stmts = _split_sql(sql)
            for stmt in stmts:
                if not stmt.upper().lstrip().startswith("CREATE"):
                    continue
                cur.execute(stmt)
                created += 1
            cur.execute("SET FOREIGN_KEY_CHECKS=1")
        conn.commit()
        tables_after = list_ozro_tables(conn, prefix)
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    return {
        "prefix": prefix,
        "schema_file": str(schema_path),
        "reset": reset,
        "dropped": dropped,
        "statements_executed": created,
        "tables_after": tables_after,
    }
