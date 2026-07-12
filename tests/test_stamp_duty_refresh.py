from types import SimpleNamespace
import unittest
from unittest.mock import patch

import app


class StampDutyRefreshTests(unittest.TestCase):
    def make_streamlit(self, **overrides):
        values = {
            "price": 700_000.0,
            "property_address": "1 Example Street, Melbourne VIC 3000",
            "stamp_duty": None,
            "stamp_duty_source_url": "",
            "stamp_duty_message": "",
            "stamp_duty_auto_signature": "",
        }
        values.update(overrides)
        state = SessionState(**values)
        return SimpleNamespace(session_state=state)

    def test_unsupported_state_clears_previous_auto_duty(self) -> None:
        fake_st = self.make_streamlit()
        with patch.object(app, "st", fake_st):
            app.refresh_stamp_duty()
            self.assertIsNotNone(fake_st.session_state.stamp_duty)

            fake_st.session_state.property_address = "1 Example Street, Perth WA 6000"
            app.refresh_stamp_duty()

        self.assertIsNone(fake_st.session_state.stamp_duty)
        self.assertEqual(fake_st.session_state.stamp_duty_source_url, "")

    def test_blank_price_or_address_clears_duty(self) -> None:
        for price, address in [(None, "1 Example Street, Melbourne VIC 3000"), (700_000.0, "")]:
            with self.subTest(price=price, address=address):
                fake_st = self.make_streamlit(
                    price=price,
                    property_address=address,
                    stamp_duty=37_070.0,
                    stamp_duty_source_url="https://example.com/source",
                    stamp_duty_auto_signature="old-property|700000.00",
                )
                with patch.object(app, "st", fake_st):
                    app.refresh_stamp_duty()

                self.assertIsNone(fake_st.session_state.stamp_duty)
                self.assertEqual(fake_st.session_state.stamp_duty_source_url, "")
                self.assertEqual(fake_st.session_state.stamp_duty_message, "")

    def test_manual_duty_is_retained_for_unsupported_state(self) -> None:
        fake_st = self.make_streamlit(
            property_address="1 Example Street, Perth WA 6000",
            stamp_duty=25_000.0,
        )
        with patch.object(app, "st", fake_st):
            app.refresh_stamp_duty()

        self.assertEqual(fake_st.session_state.stamp_duty, 25_000.0)
        self.assertEqual(fake_st.session_state.stamp_duty_source_url, "")

    def test_qld_auto_calculates_duty(self) -> None:
        fake_st = self.make_streamlit(
            price=540_000.0,
            property_address="30 Anderson Court., Moranbah QLD 4744",
        )
        with patch.object(app, "st", fake_st):
            app.refresh_stamp_duty()

        self.assertEqual(fake_st.session_state.stamp_duty, 17_325.0)
        self.assertIn("qro.qld.gov.au", fake_st.session_state.stamp_duty_source_url)
        self.assertTrue(fake_st.session_state.stamp_duty_auto_signature)


class SessionState(SimpleNamespace):
    def get(self, key, default=None):
        return getattr(self, key, default)


if __name__ == "__main__":
    unittest.main()
