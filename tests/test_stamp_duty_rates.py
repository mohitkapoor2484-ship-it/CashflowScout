import unittest

import stamp_duty


class StampDutyRateTests(unittest.TestCase):
    def test_qld_general_duty_uses_current_investor_rates(self) -> None:
        self.assertEqual(stamp_duty.calculate_qld_general_duty(449_000.0), 14_140.0)
        self.assertEqual(stamp_duty.calculate_qld_general_duty(540_000.0), 17_325.0)
        self.assertEqual(stamp_duty.calculate_qld_general_duty(850_000.0), 31_275.0)

    def test_calculate_stamp_duty_supports_qld(self) -> None:
        result = stamp_duty.calculate_stamp_duty(540_000.0, "30 Anderson Court., Moranbah QLD 4744")

        self.assertTrue(result["supported"])
        self.assertEqual(result["state"], "QLD")
        self.assertEqual(result["duty"], 17_325.0)
        self.assertEqual(result["source_url"], stamp_duty.QLD_SOURCE_URL)
        self.assertIn("Queensland", str(result["message"]))


if __name__ == "__main__":
    unittest.main()
