import unittest
import numpy as np

from src.data import generate_synthetic_dataset, extract_features
from src.model import LogisticRiskModel
from src.metrics import roc_auc, average_precision, brier_score


class RecurrenceModelTests(unittest.TestCase):
    def test_synthetic_dataset_has_expected_schema_and_event_rate(self):
        X, y, feature_names = generate_synthetic_dataset(n=500, seed=7)
        self.assertEqual(X.shape, (500, 8))
        self.assertEqual(y.shape, (500,))
        self.assertEqual(len(feature_names), 8)
        self.assertGreater(float(y.mean()), 0.25)
        self.assertLess(float(y.mean()), 0.70)

    def test_logistic_model_learns_risk_signal(self):
        X, y, _ = generate_synthetic_dataset(n=800, seed=2)
        split = 600
        model = LogisticRiskModel(learning_rate=0.08, epochs=1800)
        model.fit(X[:split], y[:split])
        p = model.predict_proba(X[split:])
        self.assertEqual(p.shape, (200,))
        self.assertTrue(np.all((p >= 0) & (p <= 1)))
        self.assertGreater(roc_auc(y[split:], p), 0.60)
        self.assertLess(brier_score(y[split:], p), 0.26)

    def test_metrics_and_llm_extraction(self):
        record = {
            "epilepsy_duration_before_remission_years": 6,
            "seizure_free_months": 18,
            "age_at_onset": 14,
            "febrile_seizure_history": True,
            "seizure_count_before_remission": 5,
            "self_limiting_syndrome": False,
            "developmental_delay": False,
            "eeg_epileptiform": True,
        }
        values, names = extract_features(record)
        self.assertEqual(values.shape, (8,))
        self.assertEqual(names[0], "epilepsy_duration_before_remission_years")
        self.assertGreater(average_precision(np.array([0, 1, 1]), np.array([0.1, 0.7, 0.6])), 0.5)


if __name__ == "__main__":
    unittest.main()
