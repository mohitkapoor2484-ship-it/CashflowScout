from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

import app
import pandas as pd
from streamlit.testing.v1 import AppTest

import storage


APP_FILE = "app.py"
SOI_FAILURE = {
    "found": False,
    "message": "REA access blocked safely; existing values were kept.",
    "low": 0.0,
    "high": 0.0,
    "source_url": "",
}


def button(app_test: AppTest, label: str):
    return next(item for item in app_test.button if item.label == label)


def delete_state_key(app_test: AppTest, key: str) -> None:
    try:
        del app_test.session_state[key]
    except KeyError:
        pass


def set_state_value(app_test: AppTest, key: str, value) -> None:
    app_test.session_state[key] = value


def authenticate_test_session(app_test: AppTest, is_admin: bool = False) -> None:
    app_test.session_state["is_authenticated"] = True
    app_test.session_state["authenticated_username"] = "admin" if is_admin else "tester"
    app_test.session_state["authenticated_email"] = "admin@example.com" if is_admin else "tester@example.com"
    app_test.session_state["authenticated_is_admin"] = is_admin


def portfolio_widget_key(app_test: AppTest, input_key: str) -> str:
    try:
        nonce = int(app_test.session_state["portfolio_widget_nonce"])
    except KeyError:
        nonce = 0
    return f"{input_key}__{nonce}"


class PropertyCheckIntegrationTests(unittest.TestCase):
    def test_unauthenticated_users_see_auth_page_only(self) -> None:
        with patch("statement_lookup.lookup_statement_of_information", return_value=SOI_FAILURE):
            app_test = AppTest.from_file(APP_FILE, default_timeout=20)
            app_test.run()

        self.assertEqual(len(app_test.exception), 0)
        self.assertFalse(bool(app_test.session_state["is_authenticated"]))
        button_labels = [item.label for item in app_test.button]
        self.assertIn("Login", button_labels)
        self.assertIn("Create account", button_labels)
        self.assertIn("Login as admin", button_labels)

    def test_admin_session_can_open_admin_panel(self) -> None:
        with patch("statement_lookup.lookup_statement_of_information", return_value=SOI_FAILURE):
            app_test = AppTest.from_file(APP_FILE, default_timeout=20)
            authenticate_test_session(app_test, is_admin=True)
            set_state_value(app_test, "active_page", "Admin panel")
            app_test.run()

        self.assertEqual(len(app_test.exception), 0)
        self.assertEqual(app_test.session_state["active_page"], "Admin panel")
        self.assertTrue(bool(app_test.session_state["authenticated_is_admin"]))

    def test_saved_properties_are_scoped_to_user_and_admin_sees_all(self) -> None:
        tmpdir = tempfile.mkdtemp()
        try:
            db_path = Path(tmpdir) / "property_check.db"
            with (
                patch.object(storage, "DB_PATH", db_path),
                patch("statement_lookup.lookup_statement_of_information", return_value=SOI_FAILURE),
            ):
                storage.init_db()
                storage.save_property(
                    name="Mohit Deal",
                    address="1 Collins Street, Melbourne VIC 3000",
                    state="VIC",
                    payload={"property_address": "1 Collins Street, Melbourne VIC 3000", "price": 500000, "weekly_rent": 600},
                    owner_username="mohitkapoor2484",
                )
                storage.save_property(
                    name="Alice Deal",
                    address="2 Queen Street, Brisbane QLD 4000",
                    state="QLD",
                    payload={"property_address": "2 Queen Street, Brisbane QLD 4000", "price": 420000, "weekly_rent": 520},
                    owner_username="alice",
                )

                mohit_app = AppTest.from_file(APP_FILE, default_timeout=20)
                authenticate_test_session(mohit_app)
                mohit_app.session_state["authenticated_username"] = "mohitkapoor2484"
                mohit_app.run()

                alice_app = AppTest.from_file(APP_FILE, default_timeout=20)
                authenticate_test_session(alice_app)
                alice_app.session_state["authenticated_username"] = "alice"
                alice_app.run()

                admin_app = AppTest.from_file(APP_FILE, default_timeout=20)
                authenticate_test_session(admin_app, is_admin=True)
                admin_app.run()

            self.assertEqual(len(mohit_app.exception), 0)
            self.assertEqual(len(alice_app.exception), 0)
            self.assertEqual(len(admin_app.exception), 0)

            mohit_buttons = [item.label for item in mohit_app.button]
            alice_buttons = [item.label for item in alice_app.button]
            admin_buttons = [item.label for item in admin_app.button]

            self.assertIn("Mohit Deal", mohit_buttons)
            self.assertNotIn("Alice Deal", mohit_buttons)
            self.assertIn("Alice Deal", alice_buttons)
            self.assertNotIn("Mohit Deal", alice_buttons)
            self.assertIn("Mohit Deal (mohitkapoor2484)", admin_buttons)
            self.assertIn("Alice Deal (alice)", admin_buttons)
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_portfolio_screener_renders_dscr_column(self) -> None:
        saved_properties = [
            {
                "name": "Saved One",
                "address": "1 Example Street, Melbourne VIC 3000",
                "state": "VIC",
                "is_favorite": 0,
                "updated_at": "2026-07-06 10:00:00",
            }
        ]
        loaded_property = {
            "name": "Saved One",
            "address": "1 Example Street, Melbourne VIC 3000",
            "payload": {
                "property_address": "1 Example Street, Melbourne VIC 3000",
                "price": 500_000.0,
                "property_value": 500_000.0,
                "weekly_rent": 620.0,
            },
        }
        with (
            patch("statement_lookup.lookup_statement_of_information", return_value=SOI_FAILURE),
            patch("storage.list_properties", return_value=saved_properties),
            patch("storage.load_property", return_value=loaded_property),
        ):
            app_test = AppTest.from_file(APP_FILE, default_timeout=20)
            authenticate_test_session(app_test)
            set_state_value(app_test, "active_page", "Portfolio screener")
            app_test.run()

        self.assertEqual(len(app_test.exception), 0)
        self.assertEqual(len(app_test.dataframe), 1)
        screener = app_test.dataframe[0].value
        self.assertIn("Use PM rate", screener.columns)
        self.assertTrue(bool(screener.iloc[0]["Use PM rate"]))
        self.assertIn("DSCR", screener.columns)
        self.assertIn("x", str(screener.iloc[0]["DSCR"]))

    def test_loading_saved_property_from_sidebar_exits_portfolio_screener(self) -> None:
        saved_properties = [
            {
                "name": "Saved One",
                "address": "1 Example Street, Melbourne VIC 3000",
                "state": "VIC",
                "is_favorite": 0,
                "updated_at": "2026-07-06 10:00:00",
            }
        ]
        loaded_property = {
            "name": "Saved One",
            "address": "1 Example Street, Melbourne VIC 3000",
            "payload": {
                "property_address": "1 Example Street, Melbourne VIC 3000",
                "price": 500_000.0,
                "property_value": 500_000.0,
                "weekly_rent": 620.0,
            },
        }
        with (
            patch("statement_lookup.lookup_statement_of_information", return_value=SOI_FAILURE),
            patch("storage.list_properties", return_value=saved_properties),
            patch("storage.load_property", return_value=loaded_property),
        ):
            app_test = AppTest.from_file(APP_FILE, default_timeout=20)
            authenticate_test_session(app_test)
            set_state_value(app_test, "active_page", "Portfolio screener")
            app_test.run()
            button(app_test, "Saved One").click().run()

        self.assertEqual(len(app_test.exception), 0)
        self.assertEqual(app_test.session_state["active_page"], "Property workspace")
        self.assertEqual(app_test.session_state["loaded_property_name"], "Saved One")
        self.assertEqual(app_test.session_state["property_address"], "1 Example Street, Melbourne VIC 3000")

    def test_portfolio_screener_left_menu_loads_saved_inputs(self) -> None:
        saved_properties = [
            {
                "name": "Saved One",
                "address": "1 Example Street, Melbourne VIC 3000",
                "state": "VIC",
                "is_favorite": 0,
                "updated_at": "2026-07-06 10:00:00",
            }
        ]
        saved_settings = {
            "portfolio_deposit_mode": "Dollar",
            "portfolio_deposit_value": 175_000.0,
            "portfolio_loan_rate": 5.85,
            "portfolio_loan_years": 25.0,
            "portfolio_repayment_type": "I only",
        }
        loaded_property = {
            "name": "Saved One",
            "address": "1 Example Street, Melbourne VIC 3000",
            "payload": {
                "property_address": "1 Example Street, Melbourne VIC 3000",
                "price": 500_000.0,
                "property_value": 500_000.0,
                "weekly_rent": 620.0,
            },
        }
        with (
            patch("statement_lookup.lookup_statement_of_information", return_value=SOI_FAILURE),
            patch("storage.list_properties", return_value=saved_properties),
            patch("storage.load_property", return_value=loaded_property),
            patch("storage.load_setting", return_value=saved_settings),
        ):
            app_test = AppTest.from_file(APP_FILE, default_timeout=20)
            authenticate_test_session(app_test)
            set_state_value(app_test, "active_page", "Portfolio screener")
            app_test.run()

        self.assertEqual(len(app_test.exception), 0)
        self.assertEqual(app_test.session_state["portfolio_deposit_mode"], "Dollar")
        self.assertEqual(app_test.session_state["portfolio_deposit_value"], 175_000.0)
        self.assertEqual(app_test.session_state["portfolio_loan_rate"], 5.85)
        self.assertEqual(app_test.session_state["portfolio_loan_years"], 25.0)
        self.assertEqual(app_test.session_state["portfolio_repayment_type"], "I only")
        self.assertEqual(app_test.session_state["portfolio_deposit_mode_input"], "Dollar")
        self.assertEqual(app_test.session_state["portfolio_deposit_value_input"], 175_000.0)
        self.assertEqual(app_test.session_state["portfolio_loan_rate_input"], 5.85)
        self.assertEqual(app_test.session_state["portfolio_loan_years_input"], 25.0)
        self.assertEqual(app_test.session_state["portfolio_repayment_type_input"], "I only")
        self.assertEqual(app_test.session_state[portfolio_widget_key(app_test, "portfolio_deposit_mode_input")], "Dollar")
        self.assertEqual(app_test.session_state[portfolio_widget_key(app_test, "portfolio_deposit_value_input")], 175_000.0)
        self.assertTrue(any(item.label == "Save screener inputs" for item in app_test.button))

    def test_portfolio_screener_reload_restores_saved_inputs_when_fields_are_zeroed(self) -> None:
        saved_properties = [
            {
                "name": "Saved One",
                "address": "1 Example Street, Melbourne VIC 3000",
                "state": "VIC",
                "is_favorite": 0,
                "updated_at": "2026-07-06 10:00:00",
            }
        ]
        saved_settings = {
            "portfolio_deposit_mode": "Dollar",
            "portfolio_deposit_value": 175_000.0,
            "portfolio_loan_rate": 5.85,
            "portfolio_loan_years": 25.0,
            "portfolio_repayment_type": "I only",
            "portfolio_solicitor_charge": 2_000.0,
            "portfolio_inspection_costs": 700.0,
            "portfolio_annual_borrowing_costs": 450.0,
            "portfolio_building_insurance_annual": 1_100.0,
            "portfolio_landlord_insurance_annual": 500.0,
            "portfolio_property_manager_rate": 6.9,
            "portfolio_vacancy_allowance_pct": 1.8,
            "portfolio_maintenance_allowance_pct": 1.2,
            "portfolio_income_tax_rate": 32.5,
        }
        loaded_property = {
            "name": "Saved One",
            "address": "1 Example Street, Melbourne VIC 3000",
            "payload": {
                "property_address": "1 Example Street, Melbourne VIC 3000",
                "price": 500_000.0,
                "property_value": 500_000.0,
                "weekly_rent": 620.0,
            },
        }
        with (
            patch("statement_lookup.lookup_statement_of_information", return_value=SOI_FAILURE),
            patch("storage.list_properties", return_value=saved_properties),
            patch("storage.load_property", return_value=loaded_property),
            patch("storage.load_setting", return_value=saved_settings),
        ):
            app_test = AppTest.from_file(APP_FILE, default_timeout=20)
            authenticate_test_session(app_test)
            set_state_value(app_test, "active_page", "Portfolio screener")
            set_state_value(app_test, "_portfolio_settings_loaded", True)
            set_state_value(app_test, portfolio_widget_key(app_test, "portfolio_deposit_value_input"), 0.0)
            set_state_value(app_test, portfolio_widget_key(app_test, "portfolio_loan_rate_input"), 0.0)
            set_state_value(app_test, portfolio_widget_key(app_test, "portfolio_loan_years_input"), 0.0)
            set_state_value(app_test, portfolio_widget_key(app_test, "portfolio_solicitor_charge_input"), 0.0)
            set_state_value(app_test, portfolio_widget_key(app_test, "portfolio_inspection_costs_input"), 0.0)
            set_state_value(app_test, portfolio_widget_key(app_test, "portfolio_annual_borrowing_costs_input"), 0.0)
            set_state_value(app_test, portfolio_widget_key(app_test, "portfolio_building_insurance_annual_input"), 0.0)
            set_state_value(app_test, portfolio_widget_key(app_test, "portfolio_landlord_insurance_annual_input"), 0.0)
            set_state_value(app_test, portfolio_widget_key(app_test, "portfolio_property_manager_rate_input"), 0.0)
            set_state_value(app_test, portfolio_widget_key(app_test, "portfolio_vacancy_allowance_pct_input"), 0.0)
            set_state_value(app_test, portfolio_widget_key(app_test, "portfolio_maintenance_allowance_pct_input"), 0.0)
            set_state_value(app_test, portfolio_widget_key(app_test, "portfolio_income_tax_rate_input"), 0.0)
            app_test.run()

        self.assertEqual(len(app_test.exception), 0)
        self.assertEqual(app_test.session_state["portfolio_deposit_mode"], "Dollar")
        self.assertEqual(app_test.session_state["portfolio_deposit_value"], 175_000.0)
        self.assertEqual(app_test.session_state["portfolio_loan_rate"], 5.85)
        self.assertEqual(app_test.session_state["portfolio_loan_years"], 25.0)
        self.assertEqual(app_test.session_state["portfolio_repayment_type"], "I only")
        self.assertEqual(app_test.session_state["portfolio_deposit_mode_input"], "Dollar")
        self.assertEqual(app_test.session_state["portfolio_deposit_value_input"], 175_000.0)
        self.assertEqual(app_test.session_state["portfolio_loan_rate_input"], 5.85)
        self.assertEqual(app_test.session_state["portfolio_loan_years_input"], 25.0)
        self.assertEqual(app_test.session_state["portfolio_repayment_type_input"], "I only")
        self.assertEqual(app_test.session_state[portfolio_widget_key(app_test, "portfolio_deposit_value_input")], 175_000.0)

    def test_portfolio_screener_save_button_persists_current_inputs(self) -> None:
        saved_properties = [
            {
                "name": "Saved One",
                "address": "1 Example Street, Melbourne VIC 3000",
                "state": "VIC",
                "is_favorite": 0,
                "updated_at": "2026-07-06 10:00:00",
            }
        ]
        loaded_property = {
            "name": "Saved One",
            "address": "1 Example Street, Melbourne VIC 3000",
            "payload": {
                "property_address": "1 Example Street, Melbourne VIC 3000",
                "price": 500_000.0,
                "property_value": 500_000.0,
                "weekly_rent": 620.0,
            },
        }
        with (
            patch("statement_lookup.lookup_statement_of_information", return_value=SOI_FAILURE),
            patch("storage.list_properties", return_value=saved_properties),
            patch("storage.load_property", return_value=loaded_property),
            patch("storage.save_setting") as save_setting_mock,
        ):
            app_test = AppTest.from_file(APP_FILE, default_timeout=20)
            authenticate_test_session(app_test)
            set_state_value(app_test, "active_page", "Portfolio screener")
            app_test.run()
            set_state_value(app_test, portfolio_widget_key(app_test, "portfolio_deposit_mode_input"), "Dollar")
            set_state_value(app_test, portfolio_widget_key(app_test, "portfolio_deposit_value_input"), 160_000.0)
            set_state_value(app_test, portfolio_widget_key(app_test, "portfolio_loan_rate_input"), 5.95)
            set_state_value(app_test, portfolio_widget_key(app_test, "portfolio_loan_years_input"), 27.0)
            set_state_value(app_test, portfolio_widget_key(app_test, "portfolio_repayment_type_input"), "I only")
            app_test.run()

            button(app_test, "Save screener inputs").click().run()

        self.assertEqual(len(app_test.exception), 0)
        save_setting_mock.assert_called_once()
        self.assertEqual(save_setting_mock.call_args.args[0], "portfolio_screener_inputs")
        saved_payload = save_setting_mock.call_args.args[1]
        self.assertEqual(saved_payload["portfolio_deposit_mode"], "Dollar")
        self.assertEqual(saved_payload["portfolio_deposit_value"], 160_000.0)
        self.assertEqual(saved_payload["portfolio_loan_rate"], 5.95)
        self.assertEqual(saved_payload["portfolio_loan_years"], 27.0)
        self.assertEqual(saved_payload["portfolio_repayment_type"], "I only")

    def test_portfolio_screener_save_button_round_trips_through_db(self) -> None:
        tmpdir = tempfile.mkdtemp()
        try:
            db_path = Path(tmpdir) / "property_check.db"
            saved_properties = [
                {
                    "name": "Saved One",
                    "address": "1 Example Street, Melbourne VIC 3000",
                    "state": "VIC",
                    "is_favorite": 0,
                    "updated_at": "2026-07-06 10:00:00",
                }
            ]
            loaded_property = {
                "name": "Saved One",
                "address": "1 Example Street, Melbourne VIC 3000",
                "payload": {
                    "property_address": "1 Example Street, Melbourne VIC 3000",
                    "price": 500_000.0,
                    "property_value": 500_000.0,
                    "weekly_rent": 620.0,
                },
            }
            with (
                patch.object(storage, "DB_PATH", db_path),
                patch("statement_lookup.lookup_statement_of_information", return_value=SOI_FAILURE),
                patch("storage.list_properties", return_value=saved_properties),
                patch("storage.load_property", return_value=loaded_property),
            ):
                app_test = AppTest.from_file(APP_FILE, default_timeout=20)
                authenticate_test_session(app_test)
                set_state_value(app_test, "active_page", "Portfolio screener")
                app_test.run()
                set_state_value(app_test, portfolio_widget_key(app_test, "portfolio_deposit_mode_input"), "Dollar")
                set_state_value(app_test, portfolio_widget_key(app_test, "portfolio_deposit_value_input"), 145_000.0)
                set_state_value(app_test, portfolio_widget_key(app_test, "portfolio_loan_rate_input"), 5.75)
                set_state_value(app_test, portfolio_widget_key(app_test, "portfolio_loan_years_input"), 26.0)
                set_state_value(app_test, portfolio_widget_key(app_test, "portfolio_repayment_type_input"), "I only")
                app_test.run()
                button(app_test, "Save screener inputs").click().run()

                loaded_settings = storage.load_setting("portfolio_screener_inputs", {})

            self.assertEqual(len(app_test.exception), 0)
            self.assertEqual(loaded_settings["portfolio_deposit_mode"], "Dollar")
            self.assertEqual(loaded_settings["portfolio_deposit_value"], 145_000.0)
            self.assertEqual(loaded_settings["portfolio_loan_rate"], 5.75)
            self.assertEqual(loaded_settings["portfolio_loan_years"], 26.0)
            self.assertEqual(loaded_settings["portfolio_repayment_type"], "I only")
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_portfolio_screener_pm_toggle_round_trips_through_db(self) -> None:
        tmpdir = tempfile.mkdtemp()
        try:
            db_path = Path(tmpdir) / "property_check.db"
            saved_properties = [
                {
                    "name": "Saved One",
                    "address": "1 Example Street, Melbourne VIC 3000",
                    "state": "VIC",
                    "is_favorite": 0,
                    "updated_at": "2026-07-06 10:00:00",
                }
            ]
            loaded_property = {
                "name": "Saved One",
                "address": "1 Example Street, Melbourne VIC 3000",
                "payload": {
                    "property_address": "1 Example Street, Melbourne VIC 3000",
                    "price": 500_000.0,
                    "property_value": 500_000.0,
                    "weekly_rent": 620.0,
                },
            }
            with (
                patch.object(storage, "DB_PATH", db_path),
                patch("statement_lookup.lookup_statement_of_information", return_value=SOI_FAILURE),
                patch("storage.list_properties", return_value=saved_properties),
                patch("storage.load_property", return_value=loaded_property),
            ):
                app_test = AppTest.from_file(APP_FILE, default_timeout=20)
                authenticate_test_session(app_test)
                set_state_value(app_test, "active_page", "Portfolio screener")
                app_test.run()
                set_state_value(
                    app_test,
                    "portfolio_screener_editor",
                    {"edited_rows": {"0": {"Use PM rate": False}}},
                )
                app_test.run()

                loaded_usage = storage.load_setting(app.PORTFOLIO_PM_USAGE_SETTING_KEY, {})

                reloaded_app_test = AppTest.from_file(APP_FILE, default_timeout=20)
                authenticate_test_session(reloaded_app_test)
                set_state_value(reloaded_app_test, "active_page", "Portfolio screener")
                reloaded_app_test.run()

            self.assertEqual(len(app_test.exception), 0)
            self.assertEqual(loaded_usage, {"Saved One": False})
            self.assertEqual(len(reloaded_app_test.exception), 0)
            self.assertEqual(
                reloaded_app_test.session_state["portfolio_property_manager_usage"],
                {"Saved One": False},
            )
            reloaded_screener = reloaded_app_test.dataframe[0].value
            self.assertFalse(bool(reloaded_screener.iloc[0]["Use PM rate"]))
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_sidebar_favorite_button_toggles_saved_property(self) -> None:
        saved_properties = [
            {
                "name": "Fav Candidate",
                "storage_key": "tester::Fav Candidate",
                "address": "1 Saved Street, Melbourne VIC 3000",
                "state": "VIC",
                "is_favorite": 0,
                "updated_at": "2026-07-06 10:00:00",
            }
        ]
        with (
            patch("statement_lookup.lookup_statement_of_information", return_value=SOI_FAILURE),
            patch("storage.list_properties", return_value=saved_properties),
            patch("storage.toggle_property_favorite") as toggle_mock,
        ):
            app_test = AppTest.from_file(APP_FILE, default_timeout=20)
            authenticate_test_session(app_test)
            app_test.run()
            next(item for item in app_test.button if item.label == "☆").click().run()

        self.assertEqual(len(app_test.exception), 0)
        toggle_mock.assert_called_once_with(
            "tester::Fav Candidate",
            owner_username="tester",
            include_all=False,
        )

    def test_favorite_property_can_render_in_favorites_and_state_sections_without_duplicate_keys(self) -> None:
        saved_properties = [
            {
                "name": "Starred Property",
                "address": "1506/45 Clarke Street, Southbank VIC 3006",
                "state": "VIC",
                "is_favorite": 1,
                "updated_at": "2026-07-06 10:00:00",
            }
        ]
        with (
            patch("statement_lookup.lookup_statement_of_information", return_value=SOI_FAILURE),
            patch("storage.list_properties", return_value=saved_properties),
        ):
            app_test = AppTest.from_file(APP_FILE, default_timeout=20)
            authenticate_test_session(app_test)
            app_test.run()

        self.assertEqual(len(app_test.exception), 0)

    def test_sidebar_save_merges_all_editor_drafts_without_calculate(self) -> None:
        with (
            patch("statement_lookup.lookup_statement_of_information", return_value=SOI_FAILURE),
            patch("storage.save_property") as save_mock,
        ):
            app_test = AppTest.from_file(APP_FILE, default_timeout=20)
            authenticate_test_session(app_test)
            app_test.run()
            set_state_value(app_test, "facts_editor_draft", pd.DataFrame(
                [
                    {"": "Property address", " ": "9 Draft Street, Geelong VIC 3220", "  ": ""},
                    {"": "Suburb", " ": "Geelong", "  ": ""},
                    {"": "State", " ": "VIC", "  ": ""},
                    {"": "Postcode", " ": "3220", "  ": ""},
                    {"": "Property type", " ": "House", "  ": ""},
                    {"": "Bedrooms", " ": "", "  ": ""},
                    {"": "Bathrooms", " ": "", "  ": ""},
                    {"": "Car spaces", " ": "", "  ": ""},
                    {"": "Land size (sqm)", " ": "", "  ": ""},
                    {"": "Tenancy status", " ": "Unknown", "  ": ""},
                    {"": "REA listing notes", " ": "Draft listing note", "  ": ""},
                ]
            ))
            set_state_value(app_test, "purchase_editor_draft", pd.DataFrame(
                [
                    {"": "REA price low", " ": "", "  ": ""},
                    {"": "REA price high", " ": "", "  ": ""},
                    {"": "SOI price low", " ": "", "  ": ""},
                    {"": "SOI price high", " ": "", "  ": ""},
                    {"": "Price", " ": "825000", "  ": ""},
                    {"": "Deposit %", " ": "20", "  ": ""},
                    {"": "Stamp duty", " ": "", "  ": ""},
                    {"": "Solicitor charge", " ": "", "  ": ""},
                    {"": "Building & pest / other costs", " ": "", "  ": ""},
                    {"": "Property value", " ": "", "  ": ""},
                ]
            ))
            set_state_value(app_test, "rent_rates_editor_draft", pd.DataFrame(
                [
                    {"": "Weekly rent", " ": "650", "  ": ""},
                    {"": "Vacancy allowance", " ": "2", "  ": ""},
                    {"": "Maintenance allowance", " ": "1", "  ": ""},
                    {"": "Annual rent growth", " ": "3", "  ": ""},
                    {"": "Annual expense inflation", " ": "3", "  ": ""},
                    {"": "Annual property growth", " ": "3", "  ": ""},
                    {"": "Council (quarterly)", " ": "", "  ": ""},
                    {"": "Water (quarterly)", " ": "", "  ": ""},
                    {"": "Strata (quarterly)", " ": "", "  ": ""},
                    {"": "Building insurance (annual)", " ": "", "  ": ""},
                    {"": "Landlord insurance (annual)", " ": "", "  ": ""},
                ]
            ))
            set_state_value(app_test, "finance_editor_draft", pd.DataFrame(
                [
                    {"": "Mortgage 1 rate", " ": "", "  ": ""},
                    {"": "Mortgage 1 amount", " ": "", "  ": ""},
                    {"": "Mortgage 1 years", " ": "", "  ": ""},
                    {"": "Mortgage 2 rate", " ": "6.1", "  ": ""},
                    {"": "Mortgage 2 amount", " ": "", "  ": ""},
                    {"": "Mortgage 2 years", " ": "", "  ": ""},
                    {"": "Mortgage 3 rate", " ": "", "  ": ""},
                    {"": "Mortgage 3 amount", " ": "", "  ": ""},
                    {"": "Mortgage 3 years", " ": "", "  ": ""},
                    {"": "Annual borrowing / package costs", " ": "", "  ": ""},
                ]
            ))
            set_state_value(app_test, "tax_editor_draft", pd.DataFrame(
                [
                    {"": "Property manager rate", " ": "7.5", "  ": ""},
                    {"": "Depreciation estimate", " ": "", "  ": ""},
                    {"": "Income", " ": "", "  ": ""},
                    {"": "Income tax rate", " ": "", "  ": ""},
                ]
            ))
            set_state_value(app_test, "deposit_source_input", "Equity")
            set_state_value(app_test, "mortgage_2_repayment_type_input", "I only")
            set_state_value(app_test, "is_sold", True)
            set_state_value(app_test, "save_name", "Draft save regression")
            set_state_value(app_test, "save_name_input", "Draft save regression")
            app_test.run()

            self.assertFalse(app_test.session_state["has_calculated"])
            button(app_test, "Save").click().run()

        self.assertEqual(len(app_test.exception), 0)
        save_mock.assert_called_once()
        saved = save_mock.call_args.kwargs
        self.assertEqual(saved["name"], "Draft save regression")
        self.assertEqual(saved["address"], "9 Draft Street, Geelong VIC 3220")
        self.assertEqual(saved["state"], "VIC")
        self.assertEqual(saved["payload"]["property_address"], "9 Draft Street, Geelong VIC 3220")
        self.assertEqual(saved["payload"]["price"], 825_000.0)
        self.assertEqual(saved["payload"]["weekly_rent"], 650.0)
        self.assertEqual(saved["payload"]["mortgage_2_rate"], 6.1)
        self.assertEqual(saved["payload"]["property_manager_rate"], 7.5)
        self.assertEqual(saved["payload"]["deposit_source"], "Equity")
        self.assertTrue(saved["payload"]["is_sold"])
        self.assertEqual(saved["payload"]["mortgage_2_repayment_type"], "I only")
        self.assertFalse(app_test.session_state["has_calculated"])
        self.assertEqual(app_test.session_state["property_address"], "9 Draft Street, Geelong VIC 3220")
        self.assertEqual(app_test.session_state["price"], 825_000.0)
        self.assertEqual(app_test.session_state["weekly_rent"], 650.0)
        self.assertEqual(app_test.session_state["loaded_property_name"], "Draft save regression")

    def test_export_save_merges_editor_drafts_without_calculate(self) -> None:
        with (
            patch("statement_lookup.lookup_statement_of_information", return_value=SOI_FAILURE),
            patch("storage.save_property") as save_mock,
        ):
            app_test = AppTest.from_file(APP_FILE, default_timeout=20)
            authenticate_test_session(app_test)
            app_test.run()
            set_state_value(app_test, "facts_editor_draft", pd.DataFrame(
                [
                    {"": "Property address", " ": "5 Export Avenue, Ballarat VIC 3350", "  ": ""},
                    {"": "Suburb", " ": "Ballarat", "  ": ""},
                    {"": "State", " ": "VIC", "  ": ""},
                    {"": "Postcode", " ": "3350", "  ": ""},
                    {"": "Property type", " ": "", "  ": ""},
                    {"": "Bedrooms", " ": "", "  ": ""},
                    {"": "Bathrooms", " ": "", "  ": ""},
                    {"": "Car spaces", " ": "", "  ": ""},
                    {"": "Land size (sqm)", " ": "", "  ": ""},
                    {"": "Tenancy status", " ": "Unknown", "  ": ""},
                    {"": "REA listing notes", " ": "", "  ": ""},
                ]
            ))
            set_state_value(app_test, "purchase_editor_draft", pd.DataFrame(
                [
                    {"": "REA price low", " ": "", "  ": ""},
                    {"": "REA price high", " ": "", "  ": ""},
                    {"": "SOI price low", " ": "", "  ": ""},
                    {"": "SOI price high", " ": "", "  ": ""},
                    {"": "Price", " ": "610000", "  ": ""},
                    {"": "Deposit %", " ": "20", "  ": ""},
                    {"": "Stamp duty", " ": "", "  ": ""},
                    {"": "Solicitor charge", " ": "1800", "  ": ""},
                    {"": "Building & pest / other costs", " ": "650", "  ": ""},
                    {"": "Property value", " ": "610000", "  ": ""},
                ]
            ))
            set_state_value(app_test, "save_name_input_export", "Export save regression")
            app_test.run()

            next(item for item in app_test.button if item.label == "Save property").click().run()

        self.assertEqual(len(app_test.exception), 0)
        save_mock.assert_called_once()
        saved = save_mock.call_args.kwargs
        self.assertEqual(saved["name"], "Export save regression")
        self.assertEqual(saved["address"], "5 Export Avenue, Ballarat VIC 3350")
        self.assertEqual(saved["payload"]["price"], 610_000.0)
        self.assertEqual(saved["payload"]["property_value"], 610_000.0)
        self.assertEqual(saved["payload"]["solicitor_charge"], 1_800.0)
        self.assertEqual(saved["payload"]["inspection_costs"], 650.0)
        self.assertEqual(app_test.session_state["property_address"], "5 Export Avenue, Ballarat VIC 3350")
        self.assertEqual(app_test.session_state["price"], 610_000.0)
        self.assertEqual(app_test.session_state["loaded_property_name"], "Export save regression")

    def test_property_details_tab_shows_property_sold_checkbox(self) -> None:
        with patch("statement_lookup.lookup_statement_of_information", return_value=SOI_FAILURE):
            app_test = AppTest.from_file(APP_FILE, default_timeout=20)
            authenticate_test_session(app_test)
            app_test.run()

        self.assertEqual(len(app_test.exception), 0)
        checkbox_labels = [item.label for item in app_test.checkbox]
        self.assertIn("Property sold", checkbox_labels)

    def test_verified_soi_updates_price_and_recalculates_vic_stamp_duty(self) -> None:
        soi_success = {
            "found": True,
            "message": "Verified exact-address SOI.",
            "low": 600_000.0,
            "high": 640_000.0,
            "source_url": "https://example.com/verified-soi.pdf",
        }
        with patch("statement_lookup.lookup_statement_of_information", return_value=soi_success):
            app_test = AppTest.from_file(APP_FILE, default_timeout=20)
            authenticate_test_session(app_test)
            app_test.run()
            address = "1 Example Street, Melbourne VIC 3000"
            set_state_value(app_test, "property_address", address)
            set_state_value(app_test, "last_soi_lookup_address", "")
            app_test.run()

            button(app_test, "Search verified REA SOI").click().run()

        self.assertEqual(len(app_test.exception), 0)
        self.assertEqual(app_test.session_state["statement_price_low"], 600_000.0)
        self.assertEqual(app_test.session_state["statement_price_high"], 640_000.0)
        self.assertEqual(app_test.session_state["price"], 620_000.0)
        self.assertEqual(app_test.session_state["property_value"], 620_000.0)
        self.assertGreater(app_test.session_state["stamp_duty"], 0)
        self.assertTrue(app_test.session_state["stamp_duty_auto_signature"])

    def test_soi_failure_preserves_same_property_but_clears_on_property_change(self) -> None:
        with patch("statement_lookup.lookup_statement_of_information", return_value=SOI_FAILURE):
            app_test = AppTest.from_file(APP_FILE, default_timeout=20)
            authenticate_test_session(app_test)
            app_test.run()
            original_address = "2 New Street, Melbourne VIC 3000"
            set_state_value(app_test, "property_address", original_address)
            set_state_value(app_test, "last_soi_lookup_address", original_address)
            set_state_value(app_test, "statement_price_low", 610_000.0)
            set_state_value(app_test, "statement_price_high", 640_000.0)
            app_test.run()

            button(app_test, "Search verified REA SOI").click().run()
            self.assertEqual(app_test.session_state["statement_price_low"], 610_000.0)
            self.assertEqual(app_test.session_state["statement_price_high"], 640_000.0)

            changed_address = "3 Other Street, Melbourne VIC 3000"
            set_state_value(app_test, "property_address", changed_address)
            app_test.run()
            button(app_test, "Search verified REA SOI").click().run()

        self.assertEqual(len(app_test.exception), 0)
        self.assertIsNone(app_test.session_state["statement_price_low"])
        self.assertIsNone(app_test.session_state["statement_price_high"])
        self.assertEqual(app_test.session_state["last_soi_lookup_address"], changed_address)

    def test_calculate_clears_stale_auto_duty_for_unsupported_state_and_blank_price(self) -> None:
        with patch("statement_lookup.lookup_statement_of_information", return_value=SOI_FAILURE):
            app_test = AppTest.from_file(APP_FILE, default_timeout=20)
            authenticate_test_session(app_test)
            app_test.run()
            set_state_value(app_test, "property_address", "1 Example Street, Melbourne VIC 3000")
            set_state_value(app_test, "price", 700_000.0)
            set_state_value(app_test, "stamp_duty", None)
            set_state_value(app_test, "stamp_duty_source_url", "")
            set_state_value(app_test, "stamp_duty_auto_signature", "")
            app_test.run()

            button(app_test, "Calculate").click().run()
            self.assertGreater(app_test.session_state["stamp_duty"], 0)

            set_state_value(app_test, "property_address", "1 Example Street, Perth WA 6000")
            app_test.run()
            button(app_test, "Calculate").click().run()
            self.assertIsNone(app_test.session_state["stamp_duty"])
            self.assertIsNone(app_test.session_state["calculated_payload"]["stamp_duty"])

            set_state_value(app_test, "property_address", "1 Example Street, Melbourne VIC 3000")
            app_test.run()
            button(app_test, "Calculate").click().run()
            self.assertGreater(app_test.session_state["stamp_duty"], 0)

            set_state_value(app_test, "price", None)
            app_test.run()
            button(app_test, "Calculate").click().run()

        self.assertEqual(len(app_test.exception), 0)
        self.assertIsNone(app_test.session_state["stamp_duty"])
        self.assertIsNone(app_test.session_state["calculated_payload"]["stamp_duty"])
        self.assertEqual(app_test.session_state["stamp_duty_source_url"], "")
        self.assertEqual(app_test.session_state["stamp_duty_message"], "")

    def test_calculate_auto_populates_qld_stamp_duty(self) -> None:
        with patch("statement_lookup.lookup_statement_of_information", return_value=SOI_FAILURE):
            app_test = AppTest.from_file(APP_FILE, default_timeout=20)
            authenticate_test_session(app_test)
            app_test.run()
            set_state_value(app_test, "property_address", "30 Anderson Court., Moranbah QLD 4744")
            set_state_value(app_test, "price", 540_000.0)
            set_state_value(app_test, "stamp_duty", None)
            set_state_value(app_test, "stamp_duty_source_url", "")
            set_state_value(app_test, "stamp_duty_auto_signature", "")
            app_test.run()

            button(app_test, "Calculate").click().run()

        self.assertEqual(len(app_test.exception), 0)
        self.assertEqual(app_test.session_state["stamp_duty"], 17_325.0)
        self.assertEqual(app_test.session_state["calculated_payload"]["stamp_duty"], 17_325.0)
        self.assertIn("qro.qld.gov.au", app_test.session_state["stamp_duty_source_url"])


if __name__ == "__main__":
    unittest.main()
