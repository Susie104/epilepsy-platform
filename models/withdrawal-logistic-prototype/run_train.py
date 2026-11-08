from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

import numpy as np

from src.data import convert_real_csv_to_model_csv, load_csv
from src.metrics import average_precision, brier_score, log_loss, roc_auc
from src.model import LogisticRiskModel, save_model_json


def main() -> None:
    parser = argparse.ArgumentParser(description="Train the 2-year epilepsy recurrence risk prototype")
    parser.add_argument("--input", required=True, help="model-schema CSV or real CSV with Chinese aliases")
    parser.add_argument("--real-csv", action="store_true", help="convert Chinese/real columns before training")
    parser.add_argument("--converted-output", default="converted_model_data.csv")
    parser.add_argument("--model-output", default="trained_model.json")
    parser.add_argument("--test-fraction", type=float, default=0.2)
    parser.add_argument("--seed", type=int, default=42, help="seed for the deterministic split")
    args = parser.parse_args()

    input_path = Path(args.input)
    if args.real_csv:
        converted = Path(args.converted_output)
        convert_real_csv_to_model_csv(input_path, converted)
        input_path = converted

    X, y, feature_names = load_csv(input_path)
    if not 0.1 <= args.test_fraction < 0.5:
        raise ValueError("--test-fraction must be in [0.1, 0.5)")
    # Prefer a patient-level split whenever patient_id is present. The
    # prototype still permits a row-level split for synthetic data, but the
    # report records this limitation so it cannot be mistaken for validation.
    with input_path.open(newline="", encoding="utf-8-sig") as handle:
        raw_rows = list(csv.DictReader(handle))
    patient_ids = [row.get("patient_id", "").strip() for row in raw_rows]
    rng = np.random.default_rng(args.seed)
    if patient_ids and all(patient_ids) and len(set(patient_ids)) < len(patient_ids):
        groups = {}
        for i, patient_id in enumerate(patient_ids):
            groups.setdefault(patient_id, []).append(i)
        group_ids = list(groups)
        rng.shuffle(group_ids)
        n_test_groups = max(1, round(len(group_ids) * args.test_fraction))
        test_ids = set(group_ids[:n_test_groups])
        test_idx = np.asarray([i for pid in test_ids for i in groups[pid]], dtype=int)
        train_idx = np.asarray([i for pid in group_ids[n_test_groups:] for i in groups[pid]], dtype=int)
        split_mode = "patient_level"
    else:
        order = rng.permutation(len(y))
        n_test = max(1, round(len(y) * args.test_fraction))
        test_idx, train_idx = order[:n_test], order[n_test:]
        split_mode = "row_level_demo_only"
    if len(train_idx) < 2 or len(test_idx) < 2:
        raise ValueError("CSV is too small for a train/test split")

    model = LogisticRiskModel(learning_rate=0.08, epochs=2200, l2=1e-3).fit(X[train_idx], y[train_idx])
    p = model.predict_proba(X[test_idx])
    save_model_json(model, args.model_output)
    report = {
        "n_rows": int(len(y)),
        "n_train": int(len(train_idx)),
        "n_test": int(len(test_idx)),
        "event_rate": float(y.mean()),
        "split_mode": split_mode,
        "warning": "row_level_demo_only is not acceptable for a real cohort; provide patient_id and perform temporal/external validation",
        "features": list(feature_names),
        "metrics": {
            "auroc": roc_auc(y[test_idx], p),
            "auprc": average_precision(y[test_idx], p),
            "brier": brier_score(y[test_idx], p),
            "log_loss": log_loss(y[test_idx], p),
        },
        "model_output": str(Path(args.model_output).resolve()),
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
