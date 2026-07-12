from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional


DB_PATH = Path(__file__).with_name("property_check.db")


def _get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with _get_connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS properties (
                name TEXT PRIMARY KEY,
                address TEXT NOT NULL,
                state TEXT NOT NULL,
                is_favorite INTEGER NOT NULL DEFAULT 0,
                payload_json TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        columns = {row["name"] for row in conn.execute("PRAGMA table_info(properties)").fetchall()}
        if "is_favorite" not in columns:
            conn.execute("ALTER TABLE properties ADD COLUMN is_favorite INTEGER NOT NULL DEFAULT 0")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS app_settings (
                key TEXT PRIMARY KEY,
                value_json TEXT NOT NULL,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )


def save_property(name: str, address: str, state: str, payload: Dict[str, Any]) -> None:
    with _get_connection() as conn:
        conn.execute(
            """
            INSERT INTO properties (name, address, state, is_favorite, payload_json, created_at, updated_at)
            VALUES (?, ?, ?, 0, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            ON CONFLICT(name) DO UPDATE SET
                address = excluded.address,
                state = excluded.state,
                payload_json = excluded.payload_json,
                updated_at = CURRENT_TIMESTAMP
            """,
            (name, address, state, json.dumps(payload)),
        )


def list_properties() -> List[Dict[str, Any]]:
    with _get_connection() as conn:
        rows = conn.execute(
            """
            SELECT name, address, state, is_favorite, updated_at
            FROM properties
            ORDER BY is_favorite DESC, state ASC, updated_at DESC, name ASC
            """
        ).fetchall()
    return [dict(row) for row in rows]


def load_property(name: str) -> Optional[Dict[str, Any]]:
    with _get_connection() as conn:
        row = conn.execute(
            """
            SELECT name, address, state, is_favorite, payload_json, updated_at
            FROM properties
            WHERE name = ?
            """,
            (name,),
        ).fetchone()
    if row is None:
        return None
    return {
        "name": row["name"],
        "address": row["address"],
        "state": row["state"],
        "is_favorite": bool(row["is_favorite"]),
        "payload": json.loads(row["payload_json"]),
        "updated_at": row["updated_at"],
    }


def delete_property(name: str) -> None:
    with _get_connection() as conn:
        conn.execute("DELETE FROM properties WHERE name = ?", (name,))


def toggle_property_favorite(name: str) -> Optional[bool]:
    with _get_connection() as conn:
        row = conn.execute("SELECT is_favorite FROM properties WHERE name = ?", (name,)).fetchone()
        if row is None:
            return None
        new_value = 0 if bool(row["is_favorite"]) else 1
        conn.execute(
            "UPDATE properties SET is_favorite = ?, updated_at = CURRENT_TIMESTAMP WHERE name = ?",
            (new_value, name),
        )
    return bool(new_value)


def save_setting(key: str, value: Any) -> None:
    with _get_connection() as conn:
        conn.execute(
            """
            INSERT INTO app_settings (key, value_json, updated_at)
            VALUES (?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(key) DO UPDATE SET
                value_json = excluded.value_json,
                updated_at = CURRENT_TIMESTAMP
            """,
            (key, json.dumps(value)),
        )


def load_setting(key: str, default: Any = None) -> Any:
    with _get_connection() as conn:
        row = conn.execute(
            "SELECT value_json FROM app_settings WHERE key = ?",
            (key,),
        ).fetchone()
    if row is None:
        return default
    try:
        return json.loads(row["value_json"])
    except (TypeError, json.JSONDecodeError):
        return default
