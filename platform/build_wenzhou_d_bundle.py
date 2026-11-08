"""Freeze the Study D core-eight LR model without publishing patient-level rows.

Usage: python build_wenzhou_d_bundle.py SOURCE_ZIP OUTPUT_JSON
The source must contain Wenzhou_167_cases_deidentified.csv from the verified
research handoff. This fits the same full-cohort LR specification used by the
Study D repeated-CV analysis; CV performance is reported separately.
"""

import hashlib
import io
import json
import sys
from pathlib import Path
from zipfile import ZipFile

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score
from sklearn.model_selection import RepeatedStratifiedKFold

EXPECTED_SOURCE_SHA256 = "98d04a5eb44813e223f9150913637ccc9368d20e1adff80edb11a6bd1af900d4"
FEATURES = ["age", "stroke_type", "interval_gt3", "multiple_seizures", "status_epilepticus", "nihss", "cortical", "eeg_epileptic"]
LABELS = {
    "age": "首次发作时年龄（岁）", "stroke_type": "卒中类型（0 出血性 / 1 缺血性）",
    "interval_gt3": "首次发作距卒中超过 3 天", "multiple_seizures": "早期多次发作",
    "status_epilepticus": "癫痫持续状态", "nihss": "NIHSS 评分",
    "cortical": "皮层受累", "eeg_epileptic": "EEG 癫痫样放电",
}


def preprocess(train, test=None):
    a = train.copy()
    b = None if test is None else test.copy()
    stats = {}
    for j, name in ((0, "age"), (5, "nihss")):
        lo, hi = np.percentile(train[:, j], [1, 99])
        a[:, j] = np.clip(a[:, j], lo, hi)
        mean, sd = float(a[:, j].mean()), float(a[:, j].std())
        if sd <= 1e-12:
            sd = 1.0
        a[:, j] = (a[:, j] - mean) / sd
        if b is not None:
            b[:, j] = (np.clip(b[:, j], lo, hi) - mean) / sd
        stats[name] = {"lower": float(lo), "upper": float(hi), "mean": mean, "sd": sd}
    return a, b, stats


def main(source_zip, output):
    with ZipFile(source_zip) as archive:
        names = [name for name in archive.namelist() if name.endswith("Wenzhou_167_cases_deidentified.csv")]
        if len(names) != 1:
            raise ValueError("Expected exactly one Wenzhou 167-case CSV")
        raw = archive.read(names[0])
    digest = hashlib.sha256(raw).hexdigest()
    if digest != EXPECTED_SOURCE_SHA256:
        raise ValueError("Research cohort SHA256 mismatch")
    frame = pd.read_csv(io.BytesIO(raw))
    if frame.shape != (167, 37):
        raise ValueError("Unexpected research cohort shape")
    c = frame.columns
    # This positional mapping follows COLS and CORE in wenzhou_de.py (code compendium, pp. 27-28).
    x = np.column_stack([
        frame[c[3]], frame[c[1]], frame[c[13]], frame[c[14]],
        frame[c[15]], frame[c[18]], frame[c[23]], (frame[c[16]] == 2).astype(float),
    ]).astype(float)
    y = frame[c[33]].to_numpy(int)
    if not np.isfinite(x).all() or int(y.sum()) != 49 or set(np.unique(y)) != {0, 1}:
        raise ValueError("Unexpected core inputs or outcome")

    oof = np.zeros((10, len(y)))
    cv = RepeatedStratifiedKFold(n_splits=5, n_repeats=10, random_state=42)
    for i, (training, testing) in enumerate(cv.split(x, y)):
        a, b, _ = preprocess(x[training], x[testing])
        model = LogisticRegression(C=1.0, max_iter=5000, random_state=42 + i)
        model.fit(a, y[training])
        oof[i // 5, testing] = model.predict_proba(b)[:, 1]
    metrics = {
        "auroc": float(np.mean([roc_auc_score(y, row) for row in oof])),
        "auprc": float(np.mean([average_precision_score(y, row) for row in oof])),
        "brier": float(np.mean([brier_score_loss(y, row) for row in oof])),
    }
    for name, expected in (("auroc", 0.7101), ("auprc", 0.5331), ("brier", 0.1825)):
        if abs(metrics[name] - expected) > 0.00005:
            raise ValueError(f"Study D CV anchor mismatch: {name}={metrics[name]}")

    a, _, stats = preprocess(x)
    model = LogisticRegression(C=1.0, max_iter=5000, random_state=42).fit(a, y)
    bundle = {
        "model_id": "WENZHOU-D-CORE8-LR-FULL-2026-11-08",
        "source_sha256": digest,
        "model_provenance": "Study D core-eight LR specification refitted on all 167 deidentified cases after reproducing the reported repeated CV anchors",
        "population": "Stroke patients with an acute symptomatic seizure within seven days after stroke in the Wenzhou cohort",
        "outcome": "Later post-stroke epilepsy during variable follow-up; no fixed risk horizon",
        "n": 167, "events": 49,
        "feature_order": FEATURES,
        "labels": LABELS,
        "binary_fields": [name for name in FEATURES if name not in ("age", "nihss")],
        "ranges": {name: {"min": float(x[:, j].min()), "max": float(x[:, j].max())} for j, name in enumerate(FEATURES)},
        "medians": {name: float(np.median(x[:, j])) for j, name in enumerate(FEATURES)},
        "continuous_preprocessing": stats,
        "coefficients": {name: float(model.coef_[0, j]) for j, name in enumerate(FEATURES)},
        "intercept": float(model.intercept_[0]),
        "cross_validation": {"design": "Repeated stratified 5-fold x 10", **metrics},
    }
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(bundle, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {output}; SHA256={hashlib.sha256(output.read_bytes()).hexdigest()}; CV={metrics}")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit("Usage: python build_wenzhou_d_bundle.py SOURCE_ZIP OUTPUT_JSON")
    main(sys.argv[1], sys.argv[2])
