import math
import unittest

import pandas as pd

from scripts.agent_eligibility_analysis import join_eligibility, score


class EligibilityAnalysisTests(unittest.TestCase):
    def test_scores_use_proxy_real_as_positive(self):
        frame = pd.DataFrame({
            "label": ["real", "real", "real", "fake", "fake"],
            "prediction": [1, 1, 0, 1, 0],
        })
        result = score(frame)
        self.assertEqual([result[k] for k in ("tp", "tn", "fp", "fn")], [2, 1, 1, 1])
        self.assertAlmostEqual(result["balanced_accuracy"], (2 / 3 + 1 / 2) / 2)
        for metric in ("precision", "recall", "f1"):
            self.assertAlmostEqual(result[metric], 2 / 3)

    def test_undefined_metrics_are_omitted(self):
        no_positive_predictions = score(pd.DataFrame({"label": ["real", "fake"], "prediction": [0, 0]}))
        self.assertTrue(math.isnan(no_positive_predictions["precision"]))
        self.assertEqual(no_positive_predictions["recall"], 0)
        self.assertEqual(no_positive_predictions["f1"], 0)
        self.assertEqual(no_positive_predictions["balanced_accuracy"], 0.5)

        no_positive_truth = score(pd.DataFrame({"label": ["fake"], "prediction": [1]}))
        for metric in ("balanced_accuracy", "precision", "recall", "f1"):
            self.assertTrue(math.isnan(no_positive_truth[metric]))

        no_negative_truth = score(pd.DataFrame({"label": ["real"], "prediction": [1]}))
        self.assertTrue(math.isnan(no_negative_truth["balanced_accuracy"]))
        self.assertEqual(no_negative_truth["recall"], 1)

    def test_join_checks_labels_end_and_event_uniqueness(self):
        start = pd.Timestamp("2026-08-01")
        events = pd.DataFrame({"sensor": ["S1"], "start": [start], "end": [start], "label": ["real"]})
        audit = events.rename(columns={"label": "proxy_label"}).assign(
            eligibility="eligible", event_id="S1|2026-08-01T00:00:00"
        )
        self.assertEqual(len(join_eligibility(events, audit)), 1)
        for invalid in (audit.assign(proxy_label="fake"), audit.assign(end=start + pd.Timedelta(hours=1)),
                        pd.concat([audit, audit]), audit.iloc[:0]):
            with self.assertRaises(ValueError):
                join_eligibility(events, invalid)
