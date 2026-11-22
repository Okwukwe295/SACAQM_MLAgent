import unittest

import pandas as pd

from scripts.agent_controlled_comparison import assess_hours, select_events, station_identity


class ControlledPilotTests(unittest.TestCase):
    def setUp(self):
        self.start = pd.Timestamp("2026-08-01 12:00")
        self.key = ("S1", self.start)
        self.hourly = {self.key: True}

    def readings(self, minutes, values):
        return pd.DataFrame({
            "timestamp": self.start + pd.to_timedelta(minutes, unit="min"),
            "pm2p5": values,
        })

    def assess(self, minutes, values):
        return assess_hours(
            "S1", self.start, self.start, {self.key: self.readings(minutes, values)}, self.hourly
        )

    def test_latest_point_wins_and_equal_threshold_triggers(self):
        result = self.assess([5, 55], [1, 60])
        self.assertEqual(result["eligibility"], "eligible")
        self.assertEqual(result["latest_reading_time"], self.start + pd.Timedelta(minutes=55))
        self.assertEqual(self.assess([5, 55], [120, 59])["eligibility"], "ineligible")

    def test_unresolved_latest_reading_does_not_fall_back_to_previous_point(self):
        self.assertEqual(self.assess([5, 55], [120, float("nan")])["eligibility"], "missing_data")
        self.assertEqual(self.assess([55, 55], [60, 59])["eligibility"], "missing_data")

    def test_a_later_eligible_hour_can_follow_an_unresolved_hour(self):
        later = self.start + pd.Timedelta(hours=1)
        key = ("S1", later)
        raw = self.readings([65], [75])
        result = assess_hours("S1", self.start, later, {key: raw}, {key: True})
        self.assertEqual(result["trigger_hour"], later)
        self.assertEqual(result["earlier_unresolved_hours"], 1)

    def test_blocked_and_multiple_sensor_stations(self):
        mapping = pd.DataFrame({
            "sensor_id": ["S1", "S2", "S3"],
            "station_id": ["665034ff099ab1a7fbcfbd2a", "other", "other"],
        })
        self.assertEqual(station_identity("S1", mapping, None)[1], "blocked_station")
        self.assertEqual(station_identity("S2", mapping, None)[1], "station_has_multiple_sensors")
        self.assertEqual(station_identity("S4", mapping, None)[1], "sensor_mapping_missing_or_ambiguous")

    def test_stratified_cap_fill_and_order_invariance(self):
        pool = pd.DataFrame({
            "event_id": [str(i) for i in range(42)],
            "proxy_label": ["fake"] * 2 + ["real"] * 40,
            "eligibility": ["eligible"] * 41 + ["missing_data"],
        })
        selected = select_events(pool)
        self.assertEqual(selected.proxy_label.value_counts().to_dict(), {"real": 28, "fake": 2})
        self.assertNotIn("41", selected.event_id.tolist())
        self.assertEqual(
            selected.event_id.tolist(), select_events(pool.sample(frac=1, random_state=1)).event_id.tolist()
        )
