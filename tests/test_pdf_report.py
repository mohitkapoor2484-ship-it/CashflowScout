from dataclasses import dataclass
from io import BytesIO
import unittest

import pandas as pd
from pypdf import PdfReader

import pdf_report


@dataclass
class FakeLoan:
    name: str
    repayment_type: str
    term_years: float
    rate_pct: float
    amount: float
    annual_repayment: float

    @property
    def effective_term_years(self) -> float:
        return self.term_years or 30.0


class PdfReportTests(unittest.TestCase):
    def test_build_property_report_generates_single_page_concept_summary(self) -> None:
        payload = {
            "property_address": "44/66 Julia Street, Portland VIC 3305",
            "listing_url": "https://www.realestate.com.au/property-apartment-vic-portland-151200472",
            "statement_source_url": "https://example.com/statement.pdf",
            "stamp_duty_source_url": "https://example.com/stamp-duty",
            "property_type": "Apartment",
            "tenancy_status": "Vacant possession",
            "suburb": "Portland",
            "property_state": "VIC",
            "postcode": "3305",
            "bedrooms": 3,
            "bathrooms": 2,
            "car_spaces": 1,
            "land_size_sqm": 110,
            "listing_price_low": 220_000,
            "listing_price_high": 240_000,
            "statement_price_low": 220_000,
            "statement_price_high": 240_000,
            "price": 230_000,
            "property_value": 230_000,
            "weekly_rent": 420,
            "deposit_input_mode": "Percent",
            "deposit_input_value": 20.0,
            "deposit_source": "Cash",
            "stamp_duty": 9_870,
            "solicitor_charge": 1_800,
            "inspection_costs": 650,
        }
        metrics = {
            "recommendation": "BUY",
            "recommendation_reasons": [
                "Yield comfortably clears the target threshold.",
                "Debt cover remains acceptable on the chosen term.",
            ],
            "deposit_amount": 46_000,
            "buying_costs": 12_320,
            "acquisition_cash_component": 58_320,
            "cash_required_upfront": 58_320,
            "total_borrowings": 184_000,
            "funding_gap": 0,
            "gross_yield": 9.50,
            "net_yield_before_interest": 6.40,
            "net_yield_after_interest": 3.15,
            "pre_tax_cashflow": 7_250,
            "after_tax_cashflow": 7_250,
            "monthly_pre_tax_cashflow": 604.17,
            "monthly_after_tax_cashflow": 604.17,
            "weekly_pre_tax_cashflow": 139.42,
            "weekly_after_tax_cashflow": 139.42,
            "overall_score": 8.2,
            "risk_score": 4.1,
            "growth_score": 6.8,
            "yield_score": 8.6,
            "break_even_rent_weekly": 281,
            "cash_on_cash": 12.43,
            "loans": [
                FakeLoan(
                    name="Mortgage 1",
                    repayment_type="P+I",
                    term_years=30,
                    rate_pct=6.1,
                    amount=184_000,
                    annual_repayment=13_425,
                )
            ],
        }
        projection = pd.DataFrame(
            [
                {"Year": 1, "Property value": 236_900, "Loan balance": 180_100, "Estimated equity": 56_800},
                {"Year": 2, "Property value": 244_007, "Loan balance": 176_000, "Estimated equity": 68_007},
                {"Year": 3, "Property value": 251_327, "Loan balance": 171_700, "Estimated equity": 79_627},
                {"Year": 4, "Property value": 258_867, "Loan balance": 167_100, "Estimated equity": 91_767},
                {"Year": 5, "Property value": 266_633, "Loan balance": 162_300, "Estimated equity": 104_333},
            ]
        )

        pdf_bytes = pdf_report.build_property_report(
            payload,
            metrics,
            loan_schedules=[],
            deposit_comparison=pd.DataFrame(),
            projection=projection,
        )

        self.assertGreater(len(pdf_bytes), 1_000)
        reader = PdfReader(BytesIO(pdf_bytes))
        self.assertEqual(len(reader.pages), 1)

        text = "\n".join(page.extract_text() or "" for page in reader.pages)
        self.assertIn("Property Feasibility Summary", text)
        self.assertIn("44/66 Julia Street, Portland VIC 3305", text)
        self.assertIn("Acquisition snapshot", text)
        self.assertIn("Cashflow snapshot", text)
        self.assertIn("Recommendation and scores", text)


if __name__ == "__main__":
    unittest.main()
