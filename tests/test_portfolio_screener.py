from types import SimpleNamespace
import unittest
from unittest.mock import patch

import app
import streamlit as st


class PortfolioScreenerTests(unittest.TestCase):
    def test_calculate_metrics_includes_dscr_based_on_noi_and_annual_debt_service(self) -> None:
        payload = {
            "price": 500_000.0,
            "property_value": 500_000.0,
            "deposit_input_mode": "Percent",
            "deposit_input_value": 20.0,
            "deposit_pct": 20.0,
            "deposit_source": "Cash",
            "stamp_duty": 0.0,
            "solicitor_charge": 0.0,
            "inspection_costs": 0.0,
            "weekly_rent": 620.0,
            "vacancy_allowance_pct": 2.0,
            "maintenance_allowance_pct": 1.0,
            "council_quarterly": 250.0,
            "water_quarterly": 180.0,
            "strata_quarterly": 900.0,
            "building_insurance_annual": 1_000.0,
            "landlord_insurance_annual": 450.0,
            "annual_borrowing_costs": 395.0,
            "property_manager_rate": 7.0,
            "depreciation_estimate": 0.0,
            "income_tax_rate": 37.0,
            "mortgage_1_rate": 0.0,
            "mortgage_1_amount": 0.0,
            "mortgage_1_years": 0.0,
            "mortgage_1_repayment_type": "P+I",
            "mortgage_2_rate": 6.1,
            "mortgage_2_amount": 400_000.0,
            "mortgage_2_years": 30.0,
            "mortgage_2_repayment_type": "P+I",
            "mortgage_3_rate": 0.0,
            "mortgage_3_amount": 0.0,
            "mortgage_3_years": 0.0,
            "mortgage_3_repayment_type": "P+I",
        }

        metrics = app.calculate_metrics(payload)

        expected_dscr = metrics["net_operating_income"] / metrics["total_loan_repayments"]
        self.assertAlmostEqual(metrics["dscr"], expected_dscr, places=6)
        self.assertGreater(metrics["dscr"], 0)

    def test_calculate_metrics_can_skip_pm_fee_without_clearing_pm_rate(self) -> None:
        payload = {
            "price": 500_000.0,
            "property_value": 500_000.0,
            "deposit_input_mode": "Percent",
            "deposit_input_value": 20.0,
            "deposit_pct": 20.0,
            "deposit_source": "Cash",
            "stamp_duty": 0.0,
            "solicitor_charge": 0.0,
            "inspection_costs": 0.0,
            "weekly_rent": 620.0,
            "vacancy_allowance_pct": 2.0,
            "maintenance_allowance_pct": 1.0,
            "council_quarterly": 250.0,
            "water_quarterly": 180.0,
            "strata_quarterly": 900.0,
            "building_insurance_annual": 1_000.0,
            "landlord_insurance_annual": 450.0,
            "annual_borrowing_costs": 395.0,
            "property_manager_rate": 7.0,
            "use_property_manager_rate": False,
            "depreciation_estimate": 0.0,
            "income_tax_rate": 37.0,
            "mortgage_1_rate": 0.0,
            "mortgage_1_amount": 0.0,
            "mortgage_1_years": 0.0,
            "mortgage_1_repayment_type": "P+I",
            "mortgage_2_rate": 6.1,
            "mortgage_2_amount": 400_000.0,
            "mortgage_2_years": 30.0,
            "mortgage_2_repayment_type": "P+I",
            "mortgage_3_rate": 0.0,
            "mortgage_3_amount": 0.0,
            "mortgage_3_years": 0.0,
            "mortgage_3_repayment_type": "P+I",
        }

        metrics = app.calculate_metrics(payload)

        self.assertEqual(metrics["applied_property_manager_rate"], 0.0)
        self.assertEqual(payload["property_manager_rate"], 7.0)
        self.assertEqual(metrics["property_manager_fee"], 0.0)

    def test_build_portfolio_screening_payload_auto_calculates_stamp_duty_and_main_loan(self) -> None:
        saved = {
            "address": "1 Example Street, Melbourne VIC 3000",
            "payload": {
                "property_address": "1 Example Street, Melbourne VIC 3000",
                "price": 500_000.0,
                "property_value": 500_000.0,
                "weekly_rent": 620.0,
            },
        }
        shared = {
            "deposit_mode": "Percent",
            "deposit_value": 20.0,
            "loan_rate": 6.1,
            "loan_years": 30.0,
            "repayment_type": "P+I",
            "solicitor_charge": 1800.0,
            "inspection_costs": 650.0,
            "annual_borrowing_costs": 395.0,
            "building_insurance_annual": 1000.0,
            "landlord_insurance_annual": 450.0,
            "property_manager_rate": 7.0,
            "vacancy_allowance_pct": 2.0,
            "maintenance_allowance_pct": 1.0,
            "income_tax_rate": 37.0,
        }

        payload = app.build_portfolio_screening_payload(saved, shared)

        self.assertEqual(payload["deposit_input_mode"], "Percent")
        self.assertEqual(payload["deposit_pct"], 20.0)
        self.assertEqual(payload["mortgage_2_amount"], 400_000.0)
        self.assertEqual(payload["mortgage_2_rate"], 6.1)
        self.assertGreater(payload["stamp_duty"], 0)
        self.assertEqual(payload["solicitor_charge"], 1800.0)
        self.assertEqual(payload["inspection_costs"], 650.0)

    def test_build_portfolio_screening_payload_can_exclude_property_manager_rate(self) -> None:
        saved = {
            "address": "1 Example Street, Melbourne VIC 3000",
            "payload": {
                "property_address": "1 Example Street, Melbourne VIC 3000",
                "price": 500_000.0,
                "property_value": 500_000.0,
                "weekly_rent": 620.0,
            },
        }
        shared = {
            "deposit_mode": "Percent",
            "deposit_value": 20.0,
            "loan_rate": 6.1,
            "loan_years": 30.0,
            "repayment_type": "P+I",
            "solicitor_charge": 1800.0,
            "inspection_costs": 650.0,
            "annual_borrowing_costs": 395.0,
            "building_insurance_annual": 1000.0,
            "landlord_insurance_annual": 450.0,
            "property_manager_rate": 7.0,
            "vacancy_allowance_pct": 2.0,
            "maintenance_allowance_pct": 1.0,
            "income_tax_rate": 37.0,
        }

        payload = app.build_portfolio_screening_payload(
            saved,
            shared,
            use_property_manager_rate=False,
        )

        self.assertEqual(payload["property_manager_rate"], 7.0)
        self.assertFalse(bool(payload["use_property_manager_rate"]))

    def test_portfolio_screening_table_uses_saved_properties_and_shared_assumptions(self) -> None:
        saved_properties = [
            {
                "name": "Saved One",
                "address": "1 Example Street, Melbourne VIC 3000",
                "state": "VIC",
                "is_favorite": 1,
            }
        ]
        saved_payload = {
            "name": "Saved One",
            "address": "1 Example Street, Melbourne VIC 3000",
            "payload": {
                "property_address": "1 Example Street, Melbourne VIC 3000",
                "is_sold": True,
                "price": 500_000.0,
                "property_value": 500_000.0,
                "weekly_rent": 620.0,
                "council_quarterly": 250.0,
                "water_quarterly": 180.0,
                "strata_quarterly": 900.0,
            },
        }
        shared = {
            "deposit_mode": "Percent",
            "deposit_value": 20.0,
            "loan_rate": 6.1,
            "loan_years": 30.0,
            "repayment_type": "P+I",
            "solicitor_charge": 1800.0,
            "inspection_costs": 650.0,
            "annual_borrowing_costs": 395.0,
            "building_insurance_annual": 1000.0,
            "landlord_insurance_annual": 450.0,
            "property_manager_rate": 7.0,
            "vacancy_allowance_pct": 2.0,
            "maintenance_allowance_pct": 1.0,
            "income_tax_rate": 37.0,
        }

        with patch.object(app, "load_property", return_value=saved_payload):
            table = app.portfolio_screening_table(saved_properties, shared)

        self.assertEqual(len(table), 1)
        row = table.iloc[0]
        self.assertEqual(table.columns[0], "Recommendation")
        self.assertTrue(bool(row["Use PM rate"]))
        self.assertEqual(row["Sold"], "Yes")
        self.assertEqual(row["Property"], "Saved One")
        self.assertEqual(row["Council / yr"], 1_000.0)
        self.assertEqual(row["Water / yr"], 720.0)
        self.assertEqual(row["Strata / yr"], 3_600.0)
        self.assertGreater(row["Stamp duty"], 0)
        self.assertEqual(row["Loan needed"], 400_000.0)
        self.assertIn("DSCR", table.columns)
        self.assertGreater(row["DSCR"], 0)
        self.assertGreater(row["Break-even rent / wk"], 0)
        self.assertIn("Pre-tax CF / yr", table.columns)
        self.assertIn("Post-tax CF / yr", table.columns)
        self.assertIn(row["Recommendation"], {"BUY", "WATCH", "AVOID"})

    def test_portfolio_screening_table_allows_per_row_pm_toggle(self) -> None:
        saved_properties = [
            {
                "name": "Saved One",
                "address": "1 Example Street, Melbourne VIC 3000",
                "state": "VIC",
                "is_favorite": 0,
            }
        ]
        saved_payload = {
            "name": "Saved One",
            "address": "1 Example Street, Melbourne VIC 3000",
            "payload": {
                "property_address": "1 Example Street, Melbourne VIC 3000",
                "price": 500_000.0,
                "property_value": 500_000.0,
                "weekly_rent": 620.0,
                "council_quarterly": 250.0,
                "water_quarterly": 180.0,
                "strata_quarterly": 900.0,
            },
        }
        shared = {
            "deposit_mode": "Percent",
            "deposit_value": 20.0,
            "loan_rate": 6.1,
            "loan_years": 30.0,
            "repayment_type": "P+I",
            "solicitor_charge": 1800.0,
            "inspection_costs": 650.0,
            "annual_borrowing_costs": 395.0,
            "building_insurance_annual": 1000.0,
            "landlord_insurance_annual": 450.0,
            "property_manager_rate": 7.0,
            "vacancy_allowance_pct": 2.0,
            "maintenance_allowance_pct": 1.0,
            "income_tax_rate": 37.0,
        }

        with patch.object(app, "load_property", return_value=saved_payload):
            default_table = app.portfolio_screening_table(saved_properties, shared)
            no_pm_table = app.portfolio_screening_table(
                saved_properties,
                shared,
                {"Saved One": False},
            )

        self.assertTrue(bool(default_table.iloc[0]["Use PM rate"]))
        self.assertFalse(bool(no_pm_table.iloc[0]["Use PM rate"]))
        self.assertGreater(
            float(no_pm_table.iloc[0]["Pre-tax CF / yr"]),
            float(default_table.iloc[0]["Pre-tax CF / yr"]),
        )
        self.assertGreater(
            float(no_pm_table.iloc[0]["Net yield"]),
            float(default_table.iloc[0]["Net yield"]),
        )

    def test_apply_portfolio_screener_manager_rate_edits_persists_usage_map(self) -> None:
        with patch.object(app, "save_setting") as save_setting_mock:
            st.session_state["portfolio_screener_editor"] = {
                "edited_rows": {
                    "0": {"Use PM rate": False},
                    "1": {"Use PM rate": True},
                }
            }
            st.session_state["portfolio_screener_row_keys"] = ["Saved One", "Saved Two"]
            st.session_state["portfolio_property_manager_usage"] = {}
            st.session_state["portfolio_screener_editor_applied_signature"] = ""

            app.apply_portfolio_screener_manager_rate_edits()

        self.assertEqual(
            st.session_state["portfolio_property_manager_usage"],
            {"Saved One": False, "Saved Two": True},
        )
        save_setting_mock.assert_called_once_with(
            app.PORTFOLIO_PM_USAGE_SETTING_KEY,
            {"Saved One": False, "Saved Two": True},
        )

    def test_portfolio_screening_table_sorts_by_net_yield_descending(self) -> None:
        saved_properties = [
            {
                "name": "Lower Yield",
                "storage_key": "mohitkapoor2484::Lower Yield",
                "address": "1 Lower Street, Melbourne VIC 3000",
                "state": "VIC",
                "is_favorite": 0,
            },
            {
                "name": "Higher Yield",
                "storage_key": "mohitkapoor2484::Higher Yield",
                "address": "2 Higher Street, Melbourne VIC 3000",
                "state": "VIC",
                "is_favorite": 0,
            },
        ]
        loaded = {
            "Lower Yield": {
                "name": "Lower Yield",
                "address": "1 Lower Street, Melbourne VIC 3000",
                "payload": {
                    "property_address": "1 Lower Street, Melbourne VIC 3000",
                    "price": 600_000.0,
                    "property_value": 600_000.0,
                    "weekly_rent": 650.0,
                },
            },
            "Higher Yield": {
                "name": "Higher Yield",
                "address": "2 Higher Street, Melbourne VIC 3000",
                "payload": {
                    "property_address": "2 Higher Street, Melbourne VIC 3000",
                    "price": 400_000.0,
                    "property_value": 400_000.0,
                    "weekly_rent": 700.0,
                },
            },
        }
        shared = {
            "deposit_mode": "Percent",
            "deposit_value": 20.0,
            "loan_rate": 6.1,
            "loan_years": 30.0,
            "repayment_type": "P+I",
            "solicitor_charge": 1800.0,
            "inspection_costs": 650.0,
            "annual_borrowing_costs": 395.0,
            "building_insurance_annual": 1000.0,
            "landlord_insurance_annual": 450.0,
            "property_manager_rate": 7.0,
            "vacancy_allowance_pct": 2.0,
            "maintenance_allowance_pct": 1.0,
            "income_tax_rate": 37.0,
        }

        with patch.object(
            app,
            "load_property",
            side_effect=lambda name, owner_username=None, include_all=False: loaded[
                name.removeprefix("mohitkapoor2484::")
            ],
        ):
            table = app.portfolio_screening_table(saved_properties, shared)

        self.assertEqual(list(table["Property"]), ["Higher Yield", "Lower Yield"])
        self.assertGreater(float(table.iloc[0]["Net yield"]), float(table.iloc[1]["Net yield"]))

    def test_save_portfolio_screener_inputs_persists_expected_keys(self) -> None:
        shared = {
            "deposit_mode": "Dollar",
            "deposit_value": 150_000.0,
            "loan_rate": 5.9,
            "loan_years": 25.0,
            "repayment_type": "I only",
            "solicitor_charge": 2_100.0,
            "inspection_costs": 750.0,
            "annual_borrowing_costs": 495.0,
            "building_insurance_annual": 1_150.0,
            "landlord_insurance_annual": 525.0,
            "property_manager_rate": 6.8,
            "vacancy_allowance_pct": 1.5,
            "maintenance_allowance_pct": 1.2,
            "income_tax_rate": 32.5,
        }

        with patch.object(app, "save_setting") as save_setting_mock:
            app.save_portfolio_screener_inputs(shared)

        save_setting_mock.assert_called_once_with(
            "portfolio_screener_inputs",
            {
                "portfolio_deposit_mode": "Dollar",
                "portfolio_deposit_value": 150_000.0,
                "portfolio_loan_rate": 5.9,
                "portfolio_loan_years": 25.0,
                "portfolio_repayment_type": "I only",
                "portfolio_solicitor_charge": 2_100.0,
                "portfolio_inspection_costs": 750.0,
                "portfolio_annual_borrowing_costs": 495.0,
                "portfolio_building_insurance_annual": 1_150.0,
                "portfolio_landlord_insurance_annual": 525.0,
                "portfolio_property_manager_rate": 6.8,
                "portfolio_vacancy_allowance_pct": 1.5,
                "portfolio_maintenance_allowance_pct": 1.2,
                "portfolio_income_tax_rate": 32.5,
            },
        )


if __name__ == "__main__":
    unittest.main()
