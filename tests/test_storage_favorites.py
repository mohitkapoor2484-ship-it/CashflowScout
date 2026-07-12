from pathlib import Path
import shutil
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

import storage


class StorageFavoritesTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
