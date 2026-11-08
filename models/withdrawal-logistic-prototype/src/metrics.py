from __future__ import annotations

import numpy as np


def _validate(y_true: np.ndarray, y_score: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    y = np.asarray(y_true, dtype=int)
    p = np.asarray(y_score, dtype=float)
    if y.shape != p.shape or y.ndim != 1:
        raise ValueError("y_true and y_score must be matching 1D arrays")
    if len(np.unique(y)) < 2:
        raise ValueError("metric requires both outcome classes")
    return y, p


def roc_auc(y_true: np.ndarray, y_score: np.ndarray) -> float:
    y, p = _validate(y_true, y_score)
    order = np.argsort(p, kind="mergesort")
    ranks = np.empty_like(order, dtype=float)
    ranks[order] = np.arange(1, len(p) + 1)
    positives = y == 1
    n_pos = positives.sum()
    n_neg = len(y) - n_pos
    return float((ranks[positives].sum() - n_pos * (n_pos + 1) / 2) / (n_pos * n_neg))


def average_precision(y_true: np.ndarray, y_score: np.ndarray) -> float:
    y, p = _validate(y_true, y_score)
    order = np.argsort(-p, kind="mergesort")
    yy = y[order]
    cumulative = np.cumsum(yy)
    hits = np.flatnonzero(yy == 1)
    if len(hits) == 0:
        return 0.0
    precisions = cumulative[hits] / (hits + 1)
    return float(precisions.mean())


def brier_score(y_true: np.ndarray, y_score: np.ndarray) -> float:
    y = np.asarray(y_true, dtype=float)
    p = np.asarray(y_score, dtype=float)
    if y.shape != p.shape:
        raise ValueError("y_true and y_score must have matching shapes")
    return float(np.mean((p - y) ** 2))


def log_loss(y_true: np.ndarray, y_score: np.ndarray) -> float:
    y = np.asarray(y_true, dtype=float)
    p = np.clip(np.asarray(y_score, dtype=float), 1e-7, 1 - 1e-7)
    return float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))
