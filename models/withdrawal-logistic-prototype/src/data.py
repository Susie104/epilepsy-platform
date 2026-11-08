from __future__ import annotations

import csv
from pathlib import Path
from typing import Dict, Iterable, Tuple

import numpy as np

FEATURE_NAMES = (
    "epilepsy_duration_before_remission_years",
    "seizure_free_months",
    "age_at_onset",
    "febrile_seizure_history",
    "seizure_count_before_remission",
    "self_limiting_syndrome",
    "developmental_delay",
    "eeg_epileptiform",
)

REAL_COLUMN_ALIASES = {
    "epilepsy_duration_before_remission_years": (
        "epilepsy_duration_before_remission_years",
        "epilepsy_duration_years",  # legacy alias; do not use for new datasets
        "达到缓解前的癫痫病程年",
        "达到缓解前的癫痫病程（年）",
        "缓解前癫痫病程年",
        "癫痫病程年",
        "癫痫病程（年）",
    ),
    "seizure_free_months": ("seizure_free_months", "停药前无发作月", "停药前无发作（月）"),
    "age_at_onset": ("age_at_onset", "起病年龄", "癫痫起病年龄"),
    "febrile_seizure_history": ("febrile_seizure_history", "热性惊厥史"),
    "seizure_count_before_remission": ("seizure_count_before_remission", "缓解前发作次数"),
    "self_limiting_syndrome": ("self_limiting_syndrome", "自限性综合征", "自限性癫痫综合征"),
    "developmental_delay": ("developmental_delay", "发育迟缓"),
    "eeg_epileptiform": ("eeg_epileptiform", "停药前EEG癫痫样放电", "停药前EEG异常放电"),
    "outcome_2y": ("outcome_2y", "2年内复发", "两年内复发", "复发_2年"),
}


def _sigmoid(x: np.ndarray) -> np.ndarray:
    x = np.clip(x, -40.0, 40.0)
    return 1.0 / (1.0 + np.exp(-x))


def generate_synthetic_dataset(n: int = 1000, seed: int = 0) -> Tuple[np.ndarray, np.ndarray, Tuple[str, ...]]:
    """Generate a research-only toy cohort with literature-informed directions.

    The coefficients are deliberately synthetic; they are not the published
    Lamberink coefficients and must not be used for patient care.
    """
    rng = np.random.default_rng(seed)
    duration = rng.uniform(0.5, 15.0, n)
    seizure_free = rng.uniform(6.0, 60.0, n)
    age_onset = rng.uniform(1.0, 60.0, n)
    febrile = rng.binomial(1, 0.16, n)
    seizure_count = rng.poisson(3.0, n).clip(0, 20)
    self_limiting = rng.binomial(1, 0.28, n)
    developmental_delay = rng.binomial(1, 0.12, n)
    eeg = rng.binomial(1, 0.25, n)
    X = np.column_stack((duration, seizure_free, age_onset, febrile,
                         seizure_count, self_limiting, developmental_delay, eeg)).astype(float)
    logit = (
        -0.65
        + 0.08 * duration
        - 0.018 * seizure_free
        + 0.008 * age_onset
        + 0.55 * febrile
        + 0.06 * seizure_count
        - 0.55 * self_limiting
        + 0.65 * developmental_delay
        + 0.75 * eeg
    )
    y = rng.binomial(1, _sigmoid(logit)).astype(int)
    return X, y, FEATURE_NAMES


def extract_features(record: Dict[str, object]) -> Tuple[np.ndarray, Tuple[str, ...]]:
    """Convert an LLM-extracted JSON record to the model feature vector."""
    # Keep the old field name readable so existing demonstrations do not break,
    # while all new outputs use the clinically explicit definition.
    if "epilepsy_duration_before_remission_years" not in record and "epilepsy_duration_years" in record:
        record = dict(record)
        record["epilepsy_duration_before_remission_years"] = record["epilepsy_duration_years"]
    missing = [name for name in FEATURE_NAMES if name not in record]
    if missing:
        raise ValueError(f"missing required fields: {', '.join(missing)}")
    values = []
    for name in FEATURE_NAMES:
        value = record[name]
        if isinstance(value, dict):
            # The research JSON contract stores value/status/evidence. This
            # prototype consumes only value and deliberately rejects null or
            # unknown values instead of silently converting them to zero.
            value = value.get("value")
            if value is None or str(value).strip().lower() in {"unknown", "uncertain", "not_mentioned"}:
                raise ValueError(f"{name} is unknown; resolve missingness before binary-model prediction")
        if name in {"febrile_seizure_history", "self_limiting_syndrome", "developmental_delay", "eeg_epileptiform"}:
            if isinstance(value, bool):
                values.append(float(value))
            elif value in (0, 1, "0", "1", "0.0", "1.0"):
                values.append(float(value))
            else:
                raise ValueError(f"{name} must be boolean or 0/1")
        else:
            try:
                number = float(value)
            except (TypeError, ValueError) as exc:
                raise ValueError(f"{name} must be numeric") from exc
            if not np.isfinite(number):
                raise ValueError(f"{name} must be finite")
            values.append(number)
    return np.asarray(values, dtype=float), FEATURE_NAMES


def load_csv(path: str | Path) -> Tuple[np.ndarray, np.ndarray, Tuple[str, ...]]:
    """Load a CSV with FEATURE_NAMES plus an outcome_2y column."""
    with Path(path).open(newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        raise ValueError("CSV contains no rows")
    X = []
    y = []
    for row in rows:
        values, _ = extract_features(row)
        X.append(values)
        if row.get("outcome_2y") not in {"0", "1", 0, 1, "0.0", "1.0"}:
            raise ValueError("outcome_2y must be 0 or 1; censored or unknown outcomes cannot enter this binary prototype")
        y.append(int(float(row["outcome_2y"])))
    return np.vstack(X), np.asarray(y, dtype=int), FEATURE_NAMES


def _find_value(row: Dict[str, object], aliases: Iterable[str]) -> object:
    for alias in aliases:
        if alias in row and row[alias] not in (None, ""):
            return row[alias]
    raise ValueError(f"missing column; accepted names: {', '.join(aliases)}")


def _normalize_binary(value: object) -> str:
    text = str(value).strip().lower()
    positive = {"1", "true", "yes", "y", "有", "是", "阳性", "异常", "positive"}
    negative = {"0", "false", "no", "n", "无", "否", "阴性", "正常", "negative"}
    if text in positive:
        return "1"
    if text in negative:
        return "0"
    raise ValueError(f"cannot normalize binary value: {value}")


def normalize_real_row(row: Dict[str, object]) -> Dict[str, str]:
    """Map common Chinese or canonical real-world columns to model columns."""
    normalized: Dict[str, str] = {}
    for name in FEATURE_NAMES:
        value = _find_value(row, REAL_COLUMN_ALIASES[name])
        if name in {"febrile_seizure_history", "self_limiting_syndrome", "developmental_delay", "eeg_epileptiform"}:
            normalized[name] = _normalize_binary(value)
        else:
            normalized[name] = str(value).strip()
    outcome = _find_value(row, REAL_COLUMN_ALIASES["outcome_2y"])
    normalized["outcome_2y"] = _normalize_binary(outcome)
    return normalized


def convert_real_csv_to_model_csv(source: str | Path, target: str | Path) -> None:
    """Convert a local Chinese/English clinical CSV to the model schema."""
    with Path(source).open(newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        raise ValueError("source CSV contains no rows")
    target_path = Path(target)
    target_path.parent.mkdir(parents=True, exist_ok=True)
    # Keep audit and censoring metadata when it is present. The model ignores
    # these columns, but research workflows need them for patient-level
    # splitting, survival analysis, and provenance checks.
    metadata_fields = [
        "patient_id", "index_time", "index_type", "recurrence_date",
        "last_reliable_followup_date", "death_date", "event_status",
        "censor_days", "split", "extractor_version",
    ]
    fieldnames = list(FEATURE_NAMES) + ["outcome_2y"] + [
        name for name in metadata_fields if any(name in row for row in rows)
    ]
    with target_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            normalized = normalize_real_row(row)
            for name in fieldnames:
                if name not in normalized and name in row:
                    normalized[name] = row[name]
            writer.writerow(normalized)


def export_synthetic_csv(path: str | Path, n: int = 1000, seed: int = 0) -> None:
    """Write synthetic data using exactly the same schema as real model data."""
    X, y, names = generate_synthetic_dataset(n=n, seed=seed)
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(list(names) + ["outcome_2y"])
        for values, outcome in zip(X, y):
            writer.writerow([*values.tolist(), int(outcome)])
