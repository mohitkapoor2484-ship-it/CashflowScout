from io import BytesIO
import unittest
from unittest.mock import patch

from reportlab.pdfgen import canvas

from statement_lookup import (
    _document_matches_address,
    _is_rea_property_url,
    extract_statement_pdf,
    lookup_statement_of_information,
)


def make_soi_pdf(address: str, price_line: str) -> bytes:
    buffer = BytesIO()
    document = canvas.Canvas(buffer)
    document.drawString(72, 750, "Statement of Information")
    document.drawString(72, 730, address)
    document.drawString(72, 710, price_line)
    document.save()
    return buffer.getvalue()


class StatementLookupTests(unittest.TestCase):
    def test_verified_pdf_returns_price_range(self) -> None:
        pdf = make_soi_pdf(
            "Unit 44, 66 Julia St, Portland VIC 3305",
            "Indicative selling price $220,000 - $240,000",
        )

        result = extract_statement_pdf(pdf, "44/66 Julia Street, Portland VIC 3305", "test.pdf")

        self.assertTrue(result["found"])
        self.assertEqual(result["low"], 220_000)
        self.assertEqual(result["high"], 240_000)

    def test_wrong_address_is_rejected(self) -> None:
        pdf = make_soi_pdf(
            "44/66 Julia Street, Portland VIC 3305",
            "Indicative selling price $220,000 - $240,000",
        )

        result = extract_statement_pdf(pdf, "3 Redcliffe Parade, Tarneit VIC 3029", "test.pdf")

        self.assertFalse(result["found"])
        self.assertIn("does not match", result["message"])

    def test_address_matching_accepts_common_street_abbreviations(self) -> None:
        self.assertTrue(
            _document_matches_address(
                "Statement for 3 Redcliffe Pde Tarneit VIC 3029",
                "3 Redcliffe Parade, Tarneit VIC 3029",
            )
        )

    def test_only_exact_rea_property_hosts_are_accepted(self) -> None:
        self.assertTrue(
            _is_rea_property_url(
                "https://www.realestate.com.au/property-apartment-vic-portland-151200472"
            )
        )
        self.assertFalse(
            _is_rea_property_url(
                "https://www.realestate.com.au.example.com/property-apartment-vic-portland-151200472"
            )
        )

    @patch("statement_lookup._extract_from_document")
    @patch("statement_lookup._search_candidates", side_effect=RuntimeError("search blocked"))
    def test_listing_url_is_tried_when_public_search_is_blocked(self, _search, extract) -> None:
        listing_url = "https://www.realestate.com.au/property-apartment-vic-portland-151200472"
        extract.return_value = {
            "low": 220_000,
            "high": 240_000,
            "source_url": "https://example.com/verified-soi.pdf",
        }

        result = lookup_statement_of_information(
            "44/66 Julia Street, Portland VIC 3305",
            listing_url,
        )

        self.assertTrue(result["found"])
        extract.assert_called_once_with(listing_url, "44/66 Julia Street, Portland VIC 3305")


if __name__ == "__main__":
    unittest.main()
