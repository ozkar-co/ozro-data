"""MySQL connection from config/database.yml."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pymysql
import yaml
from pymysql.connections import Connection


def load_database_config(project_root: Path) -> dict[str, Any]:
    path = project_root / "config" / "database.yml"
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    mysql = raw.get("mysql") or {}
    missing = [k for k in ("host", "user", "password", "database") if not mysql.get(k)]
    if missing:
        raise ValueError(f"config/database.yml mysql missing keys: {missing}")
    return {
        "table_prefix": str(raw.get("table_prefix") or "ozro_"),
        "mysql": {
            "host": str(mysql["host"]),
            "port": int(mysql.get("port") or 3306),
            "user": str(mysql["user"]),
            "password": str(mysql["password"]),
            "database": str(mysql["database"]),
            "charset": "utf8mb4",
            "autocommit": False,
        },
    }


def connect(project_root: Path) -> tuple[Connection, str]:
    cfg = load_database_config(project_root)
    conn = pymysql.connect(**cfg["mysql"])
    return conn, cfg["table_prefix"]
