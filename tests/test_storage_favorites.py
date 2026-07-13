from pathlib import Path
import shutil
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

import storage


class StorageFavoritesTests(unittest.TestCase):
    def test_uses_sqlite_when_database_url_is_not_configured(self) -> None:
        with patch.dict("os.environ", {}, clear=True), patch.object(storage, "_load_streamlit_secret", return_value=None):
            self.assertIsNone(storage.get_database_url())
            self.assertFalse(storage.using_postgres())

    def test_reads_postgres_database_url_from_environment(self) -> None:
        with patch.dict("os.environ", {"DATABASE_URL": "postgresql://demo:secret@db.example.com/app"}), patch.object(
            storage,
            "_load_streamlit_secret",
            return_value=None,
        ):
            self.assertEqual(storage.get_database_url(), "postgresql://demo:secret@db.example.com/app")
            self.assertTrue(storage.using_postgres())

    def test_init_db_adds_favorite_column_to_existing_database(self) -> None:
        tmpdir = tempfile.mkdtemp()
        try:
            db_path = Path(tmpdir) / "property_check.db"
            with sqlite3.connect(db_path) as conn:
                conn.execute(
                    """
                    CREATE TABLE properties (
                        name TEXT PRIMARY KEY,
                        address TEXT NOT NULL,
                        state TEXT NOT NULL,
                        payload_json TEXT NOT NULL,
                        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                    )
                    """
                )

            with patch.object(storage, "DB_PATH", db_path):
                storage.init_db()
                with sqlite3.connect(db_path) as conn:
                    columns = [row[1] for row in conn.execute("PRAGMA table_info(properties)").fetchall()]
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

        self.assertIn("is_favorite", columns)

    def test_toggle_favorite_persists_and_survives_save_updates(self) -> None:
        tmpdir = tempfile.mkdtemp()
        try:
            db_path = Path(tmpdir) / "property_check.db"
            with patch.object(storage, "DB_PATH", db_path):
                storage.init_db()
                storage.save_property(
                    name="Test Property",
                    address="1 Test Street, Melbourne VIC 3000",
                    state="VIC",
                    payload={"property_address": "1 Test Street, Melbourne VIC 3000", "price": 500000},
                )

                self.assertFalse(storage.load_property("Test Property")["is_favorite"])

                favorite_state = storage.toggle_property_favorite("Test Property")
                self.assertTrue(favorite_state)
                self.assertTrue(storage.load_property("Test Property")["is_favorite"])

                storage.save_property(
                    name="Test Property",
                    address="1 Test Street, Melbourne VIC 3000",
                    state="VIC",
                    payload={"property_address": "1 Test Street, Melbourne VIC 3000", "price": 525000},
                )

                loaded = storage.load_property("Test Property")
                listed = storage.list_properties()
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

        self.assertTrue(loaded["is_favorite"])
        self.assertEqual(loaded["payload"]["price"], 525000)
        self.assertTrue(bool(listed[0]["is_favorite"]))

    def test_save_and_load_setting_round_trip(self) -> None:
        tmpdir = tempfile.mkdtemp()
        try:
            db_path = Path(tmpdir) / "property_check.db"
            with patch.object(storage, "DB_PATH", db_path):
                storage.init_db()
                storage.save_setting(
                    "portfolio_screener_inputs",
                    {"portfolio_deposit_mode": "Dollar", "portfolio_deposit_value": 150000},
                )
                loaded = storage.load_setting("portfolio_screener_inputs", {})
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

        self.assertEqual(loaded["portfolio_deposit_mode"], "Dollar")
        self.assertEqual(loaded["portfolio_deposit_value"], 150000)

    def test_default_admin_is_seeded_and_can_authenticate(self) -> None:
        tmpdir = tempfile.mkdtemp()
        try:
            db_path = Path(tmpdir) / "property_check.db"
            with patch.object(storage, "DB_PATH", db_path):
                storage.init_db()
                admin = storage.authenticate_user(
                    storage.DEFAULT_ADMIN_USERNAME,
                    storage.DEFAULT_ADMIN_PASSWORD,
                    require_admin=True,
                )
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

        self.assertIsNotNone(admin)
        self.assertTrue(bool(admin["is_admin"]))

    def test_create_user_and_authenticate_round_trip(self) -> None:
        tmpdir = tempfile.mkdtemp()
        try:
            db_path = Path(tmpdir) / "property_check.db"
            with patch.object(storage, "DB_PATH", db_path):
                storage.init_db()
                created, message = storage.create_user("mohit", "mohit@example.com", "SecurePass1!")
                user = storage.authenticate_user("mohit", "SecurePass1!")
                listed_users = storage.list_users()
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

        self.assertTrue(created, message)
        self.assertIsNotNone(user)
        self.assertEqual(user["username"], "mohit")
        self.assertFalse(bool(user["is_admin"]))
        self.assertTrue(any(item["username"] == "mohit" for item in listed_users))

    def test_non_admin_cannot_use_admin_login(self) -> None:
        tmpdir = tempfile.mkdtemp()
        try:
            db_path = Path(tmpdir) / "property_check.db"
            with patch.object(storage, "DB_PATH", db_path):
                storage.init_db()
                storage.create_user("member", "member@example.com", "SecurePass1!")
                admin_attempt = storage.authenticate_user("member", "SecurePass1!", require_admin=True)
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

        self.assertIsNone(admin_attempt)

    def test_properties_are_scoped_by_owner_and_admin_can_list_all(self) -> None:
        tmpdir = tempfile.mkdtemp()
        try:
            db_path = Path(tmpdir) / "property_check.db"
            with patch.object(storage, "DB_PATH", db_path):
                storage.init_db()
                storage.save_property(
                    name="Shared Label",
                    address="1 User One Street, Melbourne VIC 3000",
                    state="VIC",
                    payload={"property_address": "1 User One Street, Melbourne VIC 3000"},
                    owner_username="user_one",
                )
                storage.save_property(
                    name="Shared Label",
                    address="2 User Two Street, Brisbane QLD 4000",
                    state="QLD",
                    payload={"property_address": "2 User Two Street, Brisbane QLD 4000"},
                    owner_username="user_two",
                )

                user_one_items = storage.list_properties(owner_username="user_one")
                user_two_items = storage.list_properties(owner_username="user_two")
                admin_items = storage.list_properties(include_all=True)
                loaded_user_one = storage.load_property("Shared Label", owner_username="user_one")
                loaded_user_two = storage.load_property("Shared Label", owner_username="user_two")
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

        self.assertEqual(len(user_one_items), 1)
        self.assertEqual(len(user_two_items), 1)
        self.assertEqual(len(admin_items), 2)
        self.assertEqual(user_one_items[0]["owner_username"], "user_one")
        self.assertEqual(user_two_items[0]["owner_username"], "user_two")
        self.assertTrue(user_one_items[0]["storage_key"].startswith("user_one::"))
        self.assertTrue(user_two_items[0]["storage_key"].startswith("user_two::"))
        self.assertEqual(loaded_user_one["address"], "1 User One Street, Melbourne VIC 3000")
        self.assertEqual(loaded_user_two["address"], "2 User Two Street, Brisbane QLD 4000")


if __name__ == "__main__":
    unittest.main()
