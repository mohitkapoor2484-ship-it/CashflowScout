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
LEGACY_PROPERTY_OWNER = "mohitkapoor2484"


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
        if "owner_username" not in columns:
            conn.execute("ALTER TABLE properties ADD COLUMN owner_username TEXT")
        if "display_name" not in columns:
            conn.execute("ALTER TABLE properties ADD COLUMN display_name TEXT")
        conn.execute(
            "UPDATE properties SET owner_username = COALESCE(NULLIF(owner_username, ''), ?)",
            (LEGACY_PROPERTY_OWNER,),
        )
        conn.execute(
            """
            UPDATE properties
            SET display_name = CASE
                WHEN display_name IS NULL OR display_name = '' THEN
                    CASE
                        WHEN instr(name, '::') > 0 THEN substr(name, instr(name, '::') + 2)
                        ELSE name
                    END
                ELSE display_name
            END
            """
        )
        legacy_rows = conn.execute(
            """
            SELECT name, owner_username, display_name
            FROM properties
            WHERE instr(name, '::') = 0
            """
        ).fetchall()
        for row in legacy_rows:
            conn.execute(
                "UPDATE properties SET name = ? WHERE name = ?",
                (_property_storage_key(row["owner_username"], row["display_name"]), row["name"]),
            )
        conn.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_properties_owner_display_name
            ON properties (owner_username, display_name)
            """
        )
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


def _property_storage_key(owner_username: str, display_name: str) -> str:
    return f"{owner_username.strip()}::{display_name.strip()}"


def _property_lookup_clause(
    property_name_or_key: str,
    owner_username: Optional[str],
    include_all: bool,
) -> tuple[str, tuple[Any, ...]]:
    lookup_value = property_name_or_key.strip()
    if "::" in lookup_value:
        return "name = ?", (lookup_value,)
    if include_all:
        return "display_name = ?", (lookup_value,)
    scoped_owner = (owner_username or LEGACY_PROPERTY_OWNER).strip()
    return "(name = ? OR (display_name = ? AND owner_username = ?))", (lookup_value, lookup_value, scoped_owner)


def save_property(
    name: str,
    address: str,
    state: str,
    payload: Dict[str, Any],
    owner_username: str = LEGACY_PROPERTY_OWNER,
) -> None:
    display_name = name.strip()
    scoped_owner = owner_username.strip() or LEGACY_PROPERTY_OWNER
    storage_key = _property_storage_key(scoped_owner, display_name)
    with _get_connection() as conn:
        conn.execute(
            """
            INSERT INTO properties (name, display_name, owner_username, address, state, is_favorite, payload_json, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, 0, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            ON CONFLICT(name) DO UPDATE SET
                display_name = excluded.display_name,
                owner_username = excluded.owner_username,
                address = excluded.address,
                state = excluded.state,
                payload_json = excluded.payload_json,
                updated_at = CURRENT_TIMESTAMP
            """,
            (storage_key, display_name, scoped_owner, address, state, json.dumps(payload)),
        )


def list_properties(
    owner_username: Optional[str] = None,
    include_all: bool = False,
) -> List[Dict[str, Any]]:
    with _get_connection() as conn:
        if include_all:
            rows = conn.execute(
                """
                SELECT
                    name AS storage_key,
                    display_name AS name,
                    owner_username,
                    address,
                    state,
                    is_favorite,
                    updated_at
                FROM properties
                ORDER BY owner_username ASC, is_favorite DESC, state ASC, updated_at DESC, display_name ASC
                """
            ).fetchall()
        else:
            scoped_owner = (owner_username or LEGACY_PROPERTY_OWNER).strip()
            rows = conn.execute(
                """
                SELECT
                    name AS storage_key,
                    display_name AS name,
                    owner_username,
                    address,
                    state,
                    is_favorite,
                    updated_at
                FROM properties
                WHERE owner_username = ?
                ORDER BY is_favorite DESC, state ASC, updated_at DESC, display_name ASC
                """,
                (scoped_owner,),
            ).fetchall()
    return [dict(row) for row in rows]


def load_property(
    name: str,
    owner_username: Optional[str] = None,
    include_all: bool = False,
) -> Optional[Dict[str, Any]]:
    where_clause, params = _property_lookup_clause(name, owner_username, include_all)
    with _get_connection() as conn:
        row = conn.execute(
            """
            SELECT name, display_name, owner_username, address, state, is_favorite, payload_json, updated_at
            FROM properties
            WHERE """ + where_clause + """
            """,
            params,
        ).fetchone()
    if row is None:
        return None
    return {
        "name": row["display_name"],
        "storage_key": row["name"],
        "owner_username": row["owner_username"],
        "address": row["address"],
        "state": row["state"],
        "is_favorite": bool(row["is_favorite"]),
        "payload": json.loads(row["payload_json"]),
        "updated_at": row["updated_at"],
    }


def delete_property(
    name: str,
    owner_username: Optional[str] = None,
    include_all: bool = False,
) -> None:
    where_clause, params = _property_lookup_clause(name, owner_username, include_all)
    with _get_connection() as conn:
        conn.execute("DELETE FROM properties WHERE " + where_clause, params)


def toggle_property_favorite(
    name: str,
    owner_username: Optional[str] = None,
    include_all: bool = False,
) -> Optional[bool]:
    where_clause, params = _property_lookup_clause(name, owner_username, include_all)
    with _get_connection() as conn:
        row = conn.execute(
            "SELECT name, is_favorite FROM properties WHERE " + where_clause,
            params,
        ).fetchone()
        if row is None:
            return None
        new_value = 0 if bool(row["is_favorite"]) else 1
        conn.execute(
            "UPDATE properties SET is_favorite = ?, updated_at = CURRENT_TIMESTAMP WHERE name = ?",
            (new_value, row["name"]),
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
