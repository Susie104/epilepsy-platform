import tempfile
import unittest
from pathlib import Path

from src.data import generate_synthetic_dataset
from src.model import LogisticRiskModel, load_model_json, save_model_json


class ModelSerializationTests(unittest.TestCase):
    def test_saved_model_produces_same_probability(self):
        X, y, _ = generate_synthetic_dataset(300, seed=5)
        model = LogisticRiskModel(epochs=500).fit(X, y)
        expected = model.predict_one(X[0])
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "model.json"
            save_model_json(model, path)
            restored = load_model_json(path)
            self.assertAlmostEqual(expected, restored.predict_one(X[0]), places=10)


if __name__ == "__main__":
    unittest.main()
