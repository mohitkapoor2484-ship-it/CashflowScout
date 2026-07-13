from __future__ import annotations

import hashlib
import hmac
import json
import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from threading import Lock
from typing import Any, Dict, Iterable, List, Optional
from urllib.parse import quote, urlparse


DB_PATH = Path(__file__).with_name("property_check.db")
DEFAULT_ADMIN_USERNAME = "admin"
DEFAULT_ADMIN_PASSWORD = "ChangeMe123!"
LEGACY_PROPERTY_OWNER = "mohitkapoor2484"

_DATABASE_URL_ENV_KEYS = (
    "DATABASE_URL",
    "database_url",
    "SUPABASE_DB_URL",
    "supabase_db_url",
    "POSTGRES_URL",
    "postgres_url",
    "POSTGRESQL_URL",
    "postgresql_url",
)

_DATABASE_COMPONENT_KEYS = {
    "host": ("PGHOST", "POSTGRES_HOST", "DB_HOST", "db_host"),
    "port": ("PGPORT", "POSTGRES_PORT", "DB_PORT", "db_port"),
    "database": ("PGDATABASE", "POSTGRES_DB", "DB_NAME", "db_name", "dbname"),
    "user": ("PGUSER", "POSTGRES_USER", "DB_USER", "db_user"),
    "password": ("PGPASSWORD", "POSTGRES_PASSWORD", "DB_PASSWORD", "db_password"),
    "sslmode": ("PGSSLMODE", "POSTGRES_SSLMODE", "DB_SSLMODE", "db_sslmode"),
}

_PLACEHOLDER_VALUES = {
    "host",
    "hostname",
    "port",
    "database",
    "dbname",
    "db_name",
    "user",
    "username",
    "password",
    "pass",
    "postgres_host",
    "postgres_db",
    "postgres_user",
    "postgres_password",
}

_INIT_LOCK = Lock()
_INIT_TARGET: Optional[str] = None
_POSTGRES_POOL: Any = None
_POSTGRES_POOL_TARGET: Optional[str] = None


def _load_streamlit_secret(key: str) -> Optional[str]:
    try:
        import streamlit as st
    except Exception:
        return None

    try:
        value = st.secrets.get(key)
    except Exception:
        return None

    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def _load_streamlit_secret_section(key: str) -> Optional[Dict[str, Any]]:
    try:
        import streamlit as st
    except Exception:
        return None

    try:
        value = st.secrets.get(key)
    except Exception:
        return None

    if value is None:
        return None
    try:
        return dict(value)
    except Exception:
        return None


def _normalize_database_url(value: Any) -> Optional[str]:
    if value is None:
        return None
    normalized = str(value).strip()
    if not normalized:
        return None
    if len(normalized) >= 2 and normalized[0] == normalized[-1] and normalized[0] in {"'", '"'}:
        normalized = normalized[1:-1].strip()
    if normalized.startswith("postgres://"):
        normalized = "postgresql://" + normalized[len("postgres://") :]
    return normalized or None


def _looks_like_placeholder(value: Any) -> bool:
    normalized = str(value or "").strip().strip("'\"").lower()
    if not normalized:
        return False
    return normalized in _PLACEHOLDER_VALUES


def _load_database_component_values() -> Dict[str, str]:
    component_values: Dict[str, str] = {}
    for field_name, keys in _DATABASE_COMPONENT_KEYS.items():
        for key in keys:
            value = os.getenv(key)
            if value and str(value).strip():
                component_values[field_name] = str(value).strip()
                break
            secret_value = _load_streamlit_secret(key)
            if secret_value:
                component_values[field_name] = secret_value
                break

    for section_name in ("postgres", "database"):
        section = _load_streamlit_secret_section(section_name)
        if not section:
            continue
        section_keys = {str(key).lower(): value for key, value in section.items()}
        component_values.setdefault("host", str(section_keys.get("host", "")).strip())
        component_values.setdefault("port", str(section_keys.get("port", "")).strip())
        component_values.setdefault("database", str(section_keys.get("database") or section_keys.get("dbname") or "").strip())
        component_values.setdefault("user", str(section_keys.get("user", "")).strip())
        component_values.setdefault("password", str(section_keys.get("password", "")).strip())
        component_values.setdefault("sslmode", str(section_keys.get("sslmode", "")).strip())

    return {key: value for key, value in component_values.items() if value}


def _build_database_url_from_components() -> Optional[str]:
    component_values = _load_database_component_values()
    required_fields = ("host", "database", "user", "password")
    if any(not component_values.get(field_name) for field_name in required_fields):
        return None

    host = component_values["host"]
    port = component_values.get("port", "5432")
    database = quote(component_values["database"], safe="")
    user = quote(component_values["user"], safe="")
    password = quote(component_values["password"], safe="")
    sslmode = quote(component_values.get("sslmode", "require"), safe="")
    return f"postgresql://{user}:{password}@{host}:{port}/{database}?sslmode={sslmode}"


def validate_database_configuration() -> None:
    database_url = get_database_url()
    if not database_url:
        return

    parsed = urlparse(database_url)
    hostname = parsed.hostname or ""
    database_name = parsed.path.lstrip("/") if parsed.path else ""
    username = parsed.username or ""
    password = parsed.password or ""

    placeholder_fields: List[str] = []
    if _looks_like_placeholder(hostname):
        placeholder_fields.append("host")
    if _looks_like_placeholder(database_name):
        placeholder_fields.append("database")
    if _looks_like_placeholder(username):
        placeholder_fields.append("user")
    if _looks_like_placeholder(password):
        placeholder_fields.append("password")

    if placeholder_fields:
        raise RuntimeError(
            "Database configuration is using placeholder values for: "
            + ", ".join(placeholder_fields)
            + ". Replace the sample values in Streamlit secrets with your real Postgres connection details."
        )


def get_database_url() -> Optional[str]:
    for key in _DATABASE_URL_ENV_KEYS:
        value = os.getenv(key)
        normalized = _normalize_database_url(value)
        if normalized:
            return normalized
        secret_value = _normalize_database_url(_load_streamlit_secret(key))
        if secret_value:
            return secret_value
    return _build_database_url_from_components()


def using_postgres() -> bool:
    database_url = get_database_url()
    if not database_url:
        return False
    normalized = database_url.lower()
    return normalized.startswith("postgres://") or normalized.startswith("postgresql://")


def _database_target() -> str:
    return get_database_url() or str(DB_PATH)


def _prepare_sql(query: str) -> str:
    if using_postgres():
        return query.replace("?", "%s")
    return query


def _get_postgres_pool() -> Any:
    global _POSTGRES_POOL, _POSTGRES_POOL_TARGET
    database_url = get_database_url()
    if not database_url:
        return None
    if _POSTGRES_POOL is not None and _POSTGRES_POOL_TARGET == database_url:
        return _POSTGRES_POOL
    try:
        from psycopg.rows import dict_row
        from psycopg_pool import ConnectionPool
    except ImportError:
        return None

    if _POSTGRES_POOL is not None and _POSTGRES_POOL_TARGET != database_url:
        try:
            _POSTGRES_POOL.close()
        except Exception:
            pass

    _POSTGRES_POOL = ConnectionPool(
        conninfo=database_url,
        min_size=1,
        max_size=6,
        kwargs={"row_factory": dict_row},
        open=True,
    )
    _POSTGRES_POOL_TARGET = database_url
    return _POSTGRES_POOL


@contextmanager
def _get_connection() -> Any:
    if using_postgres():
        try:
            from psycopg import connect
            from psycopg.rows import dict_row
        except ImportError as exc:
            raise RuntimeError(
                "Postgres database support requires psycopg. Add 'psycopg[binary]' to requirements."
            ) from exc
        validate_database_configuration()
        database_url = get_database_url()
        pool = _get_postgres_pool()
        if pool is not None:
            try:
                with pool.connection() as conn:
                    yield conn
                return
            except Exception as exc:
                raise RuntimeError(
                    "Unable to connect to the configured Postgres database. Check the DATABASE_URL or postgres secrets, "
                    "make sure the password is URL-encoded if it contains special characters, and include sslmode=require."
                ) from exc
        try:
            with connect(database_url, row_factory=dict_row) as conn:
                yield conn
            return
        except Exception as exc:
            raise RuntimeError(
                "Unable to connect to the configured Postgres database. Check the DATABASE_URL or postgres secrets, "
                "make sure the password is URL-encoded if it contains special characters, and include sslmode=require."
            ) from exc

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def _execute(conn: Any, query: str, params: Iterable[Any] = ()) -> Any:
    return conn.execute(_prepare_sql(query), tuple(params))


def _fetchall(cursor: Any) -> List[Dict[str, Any]]:
    rows = cursor.fetchall()
    return [dict(row) for row in rows]


def _fetchone(cursor: Any) -> Optional[Dict[str, Any]]:
    row = cursor.fetchone()
    if row is None:
        return None
    return dict(row)


def _list_columns(conn: Any, table_name: str) -> set[str]:
    if using_postgres():
        rows = _fetchall(
            _execute(
                conn,
                """
                SELECT column_name AS name
                FROM information_schema.columns
                WHERE table_schema = 'public' AND table_name = ?
                """,
                (table_name,),
            )
        )
        return {str(row["name"]) for row in rows}

    rows = _fetchall(_execute(conn, f"PRAGMA table_info({table_name})"))
    return {str(row["name"]) for row in rows}


def _is_integrity_error(exc: Exception) -> bool:
    if isinstance(exc, sqlite3.IntegrityError):
        return True
    try:
        from psycopg import IntegrityError as PsycopgIntegrityError
    except ImportError:
        return False
    return isinstance(exc, PsycopgIntegrityError)


def init_db() -> None:
    global _INIT_TARGET
    current_target = _database_target()
    if _INIT_TARGET == current_target:
        return

    with _INIT_LOCK:
        current_target = _database_target()
        if _INIT_TARGET == current_target:
            return

        with _get_connection() as conn:
            _execute(
                conn,
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
                """,
            )

            columns = _list_columns(conn, "properties")
            if "is_favorite" not in columns:
                _execute(conn, "ALTER TABLE properties ADD COLUMN is_favorite INTEGER NOT NULL DEFAULT 0")
            if "owner_username" not in columns:
                _execute(conn, "ALTER TABLE properties ADD COLUMN owner_username TEXT")
            if "display_name" not in columns:
                _execute(conn, "ALTER TABLE properties ADD COLUMN display_name TEXT")

            _execute(
                conn,
                "UPDATE properties SET owner_username = COALESCE(NULLIF(owner_username, ''), ?)",
                (LEGACY_PROPERTY_OWNER,),
            )

            _execute(
                conn,
                """
                CREATE INDEX IF NOT EXISTS idx_properties_owner_updated
                ON properties (owner_username, updated_at DESC)
                """,
            )

            if using_postgres():
                _execute(
                    conn,
                    """
                    UPDATE properties
                    SET display_name = CASE
                        WHEN display_name IS NULL OR display_name = '' THEN
                            CASE
                                WHEN position('::' in name) > 0 THEN substring(name from position('::' in name) + 2)
                                ELSE name
                            END
                        ELSE display_name
                    END
                    """,
                )
                legacy_rows = _fetchall(
                    _execute(
                        conn,
                        """
                        SELECT name, owner_username, display_name
                        FROM properties
                        WHERE position('::' in name) = 0
                        """,
                    )
                )
            else:
                _execute(
                    conn,
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
                    """,
                )
                legacy_rows = _fetchall(
                    _execute(
                        conn,
                        """
                        SELECT name, owner_username, display_name
                        FROM properties
                        WHERE instr(name, '::') = 0
                        """,
                    )
                )

            for row in legacy_rows:
                _execute(
                    conn,
                    "UPDATE properties SET name = ? WHERE name = ?",
                    (_property_storage_key(str(row["owner_username"]), str(row["display_name"])), row["name"]),
                )

            _execute(
                conn,
                """
                CREATE UNIQUE INDEX IF NOT EXISTS idx_properties_owner_display_name
                ON properties (owner_username, display_name)
                """,
            )
            _execute(
                conn,
                """
                CREATE TABLE IF NOT EXISTS app_settings (
                    key TEXT PRIMARY KEY,
                    value_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """,
            )
            _execute(
                conn,
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
                """,
            )
            _execute(
                conn,
                """
                CREATE INDEX IF NOT EXISTS idx_users_lookup
                ON users (username, email)
                """,
            )
            _ensure_default_admin(conn)
            conn.commit()
        _INIT_TARGET = current_target


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


def _ensure_default_admin(conn: Any) -> None:
    row = _fetchone(
        _execute(
            conn,
            "SELECT username FROM users WHERE is_admin = 1 LIMIT 1",
        )
    )
    if row is not None:
        return
    salt, password_hash = _build_password_record(DEFAULT_ADMIN_PASSWORD)
    _execute(
        conn,
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
        _execute(
            conn,
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
        conn.commit()


def list_properties(
    owner_username: Optional[str] = None,
    include_all: bool = False,
) -> List[Dict[str, Any]]:
    with _get_connection() as conn:
        if include_all:
            rows = _fetchall(
                _execute(
                    conn,
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
                    """,
                )
            )
        else:
            scoped_owner = (owner_username or LEGACY_PROPERTY_OWNER).strip()
            rows = _fetchall(
                _execute(
                    conn,
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
                )
            )
    return rows


def load_property(
    name: str,
    owner_username: Optional[str] = None,
    include_all: bool = False,
) -> Optional[Dict[str, Any]]:
    where_clause, params = _property_lookup_clause(name, owner_username, include_all)
    with _get_connection() as conn:
        row = _fetchone(
            _execute(
                conn,
                """
                SELECT name, display_name, owner_username, address, state, is_favorite, payload_json, updated_at
                FROM properties
                WHERE """
                + where_clause,
                params,
            )
        )
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


def load_properties(
    names: List[str],
    owner_username: Optional[str] = None,
    include_all: bool = False,
) -> Dict[str, Dict[str, Any]]:
    lookup_values = [str(name).strip() for name in names if str(name).strip()]
    if not lookup_values:
        return {}

    storage_keys = [value for value in lookup_values if "::" in value]
    display_names = [value for value in lookup_values if "::" not in value]
    clauses: List[str] = []
    params: List[Any] = []

    if storage_keys:
        placeholders = ", ".join("?" for _ in storage_keys)
        clauses.append(f"name IN ({placeholders})")
        params.extend(storage_keys)

    if display_names:
        placeholders = ", ".join("?" for _ in display_names)
        if include_all:
            clauses.append(f"display_name IN ({placeholders})")
            params.extend(display_names)
        else:
            scoped_owner = (owner_username or LEGACY_PROPERTY_OWNER).strip()
            clauses.append(f"(display_name IN ({placeholders}) AND owner_username = ?)")
            params.extend(display_names)
            params.append(scoped_owner)

    if not clauses:
        return {}

    with _get_connection() as conn:
        rows = _fetchall(
            _execute(
                conn,
                """
                SELECT name, display_name, owner_username, address, state, is_favorite, payload_json, updated_at
                FROM properties
                WHERE """
                + " OR ".join(clauses),
                params,
            )
        )

    loaded: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        loaded[str(row["name"])] = {
            "name": row["display_name"],
            "storage_key": row["name"],
            "owner_username": row["owner_username"],
            "address": row["address"],
            "state": row["state"],
            "is_favorite": bool(row["is_favorite"]),
            "payload": json.loads(row["payload_json"]),
            "updated_at": row["updated_at"],
        }
    return loaded


def delete_property(
    name: str,
    owner_username: Optional[str] = None,
    include_all: bool = False,
) -> None:
    where_clause, params = _property_lookup_clause(name, owner_username, include_all)
    with _get_connection() as conn:
        _execute(conn, "DELETE FROM properties WHERE " + where_clause, params)
        conn.commit()


def toggle_property_favorite(
    name: str,
    owner_username: Optional[str] = None,
    include_all: bool = False,
) -> Optional[bool]:
    where_clause, params = _property_lookup_clause(name, owner_username, include_all)
    with _get_connection() as conn:
        row = _fetchone(
            _execute(
                conn,
                "SELECT name, is_favorite FROM properties WHERE " + where_clause,
                params,
            )
        )
        if row is None:
            return None
        new_value = 0 if bool(row["is_favorite"]) else 1
        _execute(
            conn,
            "UPDATE properties SET is_favorite = ?, updated_at = CURRENT_TIMESTAMP WHERE name = ?",
            (new_value, row["name"]),
        )
        conn.commit()
    return bool(new_value)


def save_setting(key: str, value: Any) -> None:
    with _get_connection() as conn:
        _execute(
            conn,
            """
            INSERT INTO app_settings (key, value_json, updated_at)
            VALUES (?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(key) DO UPDATE SET
                value_json = excluded.value_json,
                updated_at = CURRENT_TIMESTAMP
            """,
            (key, json.dumps(value)),
        )
        conn.commit()


def load_setting(key: str, default: Any = None) -> Any:
    with _get_connection() as conn:
        row = _fetchone(
            _execute(
                conn,
                "SELECT value_json FROM app_settings WHERE key = ?",
                (key,),
            )
        )
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
            _execute(
                conn,
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
            conn.commit()
    except Exception as exc:
        if _is_integrity_error(exc):
            return False, "That username or email is already registered."
        raise

    return True, "Account created successfully."


def authenticate_user(login: str, password: str, require_admin: bool = False) -> Optional[Dict[str, Any]]:
    normalized_login = login.strip()
    if not normalized_login or not password:
        return None

    with _get_connection() as conn:
        row = _fetchone(
            _execute(
                conn,
                """
                SELECT username, email, password_hash, password_salt, is_admin, created_at, updated_at
                FROM users
                WHERE lower(username) = lower(?) OR lower(email) = lower(?)
                LIMIT 1
                """,
                (normalized_login, normalized_login),
            )
        )
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
        rows = _fetchall(
            _execute(
                conn,
                """
                SELECT username, email, is_admin, created_at, updated_at
                FROM users
                ORDER BY is_admin DESC, username ASC
                """,
            )
        )
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
