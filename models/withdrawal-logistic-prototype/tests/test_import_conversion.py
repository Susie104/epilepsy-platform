import csv
import tempfile
import unittest
from pathlib import Path

from src.data import (
    convert_real_csv_to_model_csv,
    export_synthetic_csv,
    load_csv,
    normalize_real_row,
)


class ImportConversionTests(unittest.TestCase):
    def test_normalize_chinese_real_row(self):
        row = {
            "癫痫病程年": "6",
            "停药前无发作月": "18",
            "起病年龄": "14",
            "热性惊厥史": "有",
            "缓解前发作次数": "5",
            "自限性综合征": "否",
            "发育迟缓": "否",
            "停药前EEG癫痫样放电": "阳性",
            "2年内复发": "1",
        }
        normalized = normalize_real_row(row)
        self.assertEqual(normalized["febrile_seizure_history"], "1")
        self.assertEqual(normalized["eeg_epileptiform"], "1")
        self.assertEqual(normalized["outcome_2y"], "1")

    def test_export_synthetic_csv_can_be_loaded(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "synthetic.csv"
            export_synthetic_csv(path, n=20, seed=3)
            X, y, names = load_csv(path)
            self.assertEqual(X.shape, (20, 8))
            self.assertEqual(len(y), 20)
            self.assertEqual(len(names), 8)

    def test_real_csv_conversion_produces_model_schema(self):
        with tempfile.TemporaryDirectory() as td:
            source = Path(td) / "real.csv"
            target = Path(td) / "model.csv"
            with source.open("w", newline="", encoding="utf-8-sig") as f:
                writer = csv.DictWriter(f, fieldnames=["癫痫病程年", "停药前无发作月", "起病年龄", "热性惊厥史", "缓解前发作次数", "自限性综合征", "发育迟缓", "停药前EEG癫痫样放电", "2年内复发"])
                writer.writeheader()
                writer.writerow({"癫痫病程年":"6", "停药前无发作月":"18", "起病年龄":"14", "热性惊厥史":"有", "缓解前发作次数":"5", "自限性综合征":"否", "发育迟缓":"否", "停药前EEG癫痫样放电":"阳性", "2年内复发":"1"})
            convert_real_csv_to_model_csv(source, target)
            X, y, _ = load_csv(target)
            self.assertEqual(X.shape, (1, 8))
            self.assertEqual(int(y[0]), 1)


if __name__ == "__main__":
    unittest.main()
