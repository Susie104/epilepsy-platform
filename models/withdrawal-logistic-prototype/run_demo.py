from __future__ import annotations

import json
from pathlib import Path

from src.data import extract_features, generate_synthetic_dataset
from src.metrics import average_precision, brier_score, log_loss, roc_auc
from src.model import LogisticRiskModel


def main() -> None:
    X, y, feature_names = generate_synthetic_dataset(n=2000, seed=42)
    split = 1500
    model = LogisticRiskModel(learning_rate=0.08, epochs=2200, l2=1e-3)
    model.fit(X[:split], y[:split])
    p = model.predict_proba(X[split:])

    example = {
        "epilepsy_duration_before_remission_years": 6,
        "seizure_free_months": 18,
        "age_at_onset": 14,
        "febrile_seizure_history": True,
        "seizure_count_before_remission": 5,
        "self_limiting_syndrome": False,
        "developmental_delay": False,
        "eeg_epileptiform": True,
    }
    values, _ = extract_features(example)
    result = {
        "warning": "synthetic research demo; coefficients are not clinical and must be refit on local data",
        "n_train": split,
        "n_test": len(y) - split,
        "synthetic_event_rate": float(y.mean()),
        "test_metrics": {
            "auroc": roc_auc(y[split:], p),
            "auprc": average_precision(y[split:], p),
            "brier": brier_score(y[split:], p),
            "log_loss": log_loss(y[split:], p),
        },
        "feature_names": list(feature_names),
        "example_2y_risk": model.predict_one(values),
    }
    output = Path(__file__).resolve().parents[2] / "outputs" / "demo_result.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
