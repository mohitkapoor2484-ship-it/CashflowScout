from __future__ import annotations

import hashlib
import hmac
import json
import os
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional


DB_PATH = Path(__file__).with_name("property_check.db")
DEFAULT_ADMIN_USERNAME = "admin"
DEFAULT_ADMIN_PASSWORD = "ChangeMe123!"


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
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                username TEXT PRIMARY KEY,
                email TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                password_salt TEXT NOT NULL,
                is_admin INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        _ensure_default_admin(conn)


def _hash_password(password: str, salt: str) -> str:
    return hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        bytes.fromhex(salt),
        120_000,
    ).hex()


def _build_password_record(password: str) -> tuple[str, str]:
    salt = os.urandom(16).hex()
    return salt, _hash_password(password, salt)


def _ensure_default_admin(conn: sqlite3.Connection) -> None:
    row = conn.execute(
        "SELECT username FROM users WHERE is_admin = 1 LIMIT 1"
    ).fetchone()
    if row is not None:
        return
    salt, password_hash = _build_password_record(DEFAULT_ADMIN_PASSWORD)
    conn.execute(
        """
        INSERT INTO users (username, email, password_hash, password_salt, is_admin, created_at, updated_at)
        VALUES (?, ?, ?, ?, 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        """,
        (
            DEFAULT_ADMIN_USERNAME,
            "admin@propertyscout.local",
            password_hash,
            salt,
        ),
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


def create_user(username: str, email: str, password: str, is_admin: bool = False) -> tuple[bool, str]:
    normalized_username = username.strip()
    normalized_email = email.strip().lower()
    if len(normalized_username) < 3:
        return False, "Username must be at least 3 characters."
    if "@" not in normalized_email or "." not in normalized_email:
        return False, "Enter a valid email address."
    if len(password) < 8:
        return False, "Password must be at least 8 characters."

    salt, password_hash = _build_password_record(password)
    try:
        with _get_connection() as conn:
            conn.execute(
                """
                INSERT INTO users (username, email, password_hash, password_salt, is_admin, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                """,
                (
                    normalized_username,
                    normalized_email,
                    password_hash,
                    salt,
                    1 if is_admin else 0,
                ),
            )
    except sqlite3.IntegrityError:
        return False, "That username or email is already registered."

    return True, "Account created successfully."


def authenticate_user(login: str, password: str, require_admin: bool = False) -> Optional[Dict[str, Any]]:
    normalized_login = login.strip()
    if not normalized_login or not password:
        return None

    with _get_connection() as conn:
        row = conn.execute(
            """
            SELECT username, email, password_hash, password_salt, is_admin, created_at, updated_at
            FROM users
            WHERE lower(username) = lower(?) OR lower(email) = lower(?)
            LIMIT 1
            """,
            (normalized_login, normalized_login),
        ).fetchone()
    if row is None:
        return None
    if require_admin and not bool(row["is_admin"]):
        return None

    expected_hash = _hash_password(password, str(row["password_salt"]))
    if not hmac.compare_digest(expected_hash, str(row["password_hash"])):
        return None

    return {
        "username": row["username"],
        "email": row["email"],
        "is_admin": bool(row["is_admin"]),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def list_users() -> List[Dict[str, Any]]:
    with _get_connection() as conn:
        rows = conn.execute(
            """
            SELECT username, email, is_admin, created_at, updated_at
            FROM users
            ORDER BY is_admin DESC, username ASC
            """
        ).fetchall()
    return [
        {
            "username": row["username"],
            "email": row["email"],
            "is_admin": bool(row["is_admin"]),
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }
        for row in rows
    ]
