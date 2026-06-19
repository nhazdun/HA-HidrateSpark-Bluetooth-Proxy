"""16-bit weight decoding, auto-calibration, and weight-based fill tracking."""

import unittest

from ha_stub import HomeAssistant, load_state

state = load_state()


def new_bottle(size=946):
    return state.BottleState(HomeAssistant(), "entry", size)


class WeightCalibrationTest(unittest.TestCase):
    def test_first_reading_calibrates_full_anchor(self):
        b = new_bottle(946)
        changed = b.update_fill_from_weight(37000)
        self.assertTrue(changed)
        self.assertEqual(b.weight_full_raw, 37000)
        self.assertEqual(b.current_fill_ml, 946)

    def test_fill_tracks_down_from_anchor(self):
        b = new_bottle(946)
        b.update_fill_from_weight(37000)  # anchor at full
        b.update_fill_from_weight(36000)  # 1000 raw units lower
        # scale ~2.0 raw/mL -> ~500 mL drunk
        self.assertAlmostEqual(b.current_fill_ml, 446, delta=5)

    def test_fill_never_exceeds_full_or_goes_negative(self):
        b = new_bottle(946)
        b.update_fill_from_weight(37000)
        b.update_fill_from_weight(99000)  # implausibly heavy
        self.assertEqual(b.current_fill_ml, 946)
        b.update_fill_from_weight(0)  # implausibly light
        self.assertEqual(b.current_fill_ml, 0)

    def test_calibration_is_not_a_refill_but_cap_close_is(self):
        b = new_bottle(946)
        b.refill("calibration", 37000)
        self.assertEqual(b.refills_today, 0, "calibration must not count as a refill")
        b.refill("cap_close", 37100)
        self.assertEqual(b.refills_today, 1, "a real refill increments the counter")


if __name__ == "__main__":
    unittest.main(verbosity=2)
