from __future__ import annotations

import json
from pathlib import Path

import numpy as np


def _sigmoid(x: np.ndarray) -> np.ndarray:
    x = np.clip(x, -40.0, 40.0)
    return 1.0 / (1.0 + np.exp(-x))


class LogisticRiskModel:
    """Small dependency-free logistic risk model for research prototypes."""

    def __init__(self, learning_rate: float = 0.05, epochs: int = 1500, l2: float = 1e-3):
        self.learning_rate = learning_rate
        self.epochs = epochs
        self.l2 = l2
        self.mean_: np.ndarray | None = None
        self.scale_: np.ndarray | None = None
        self.weights_: np.ndarray | None = None
        self.intercept_: float | None = None

    def fit(self, X: np.ndarray, y: np.ndarray) -> "LogisticRiskModel":
        X = np.asarray(X, dtype=float)
        y = np.asarray(y, dtype=float)
        if X.ndim != 2 or y.ndim != 1 or len(X) != len(y):
            raise ValueError("X must be 2D and y must be a matching 1D array")
        if len(np.unique(y)) < 2:
            raise ValueError("y must contain both outcome classes")
        self.mean_ = X.mean(axis=0)
        self.scale_ = X.std(axis=0)
        self.scale_[self.scale_ == 0] = 1.0
        Z = (X - self.mean_) / self.scale_
        self.weights_ = np.zeros(Z.shape[1], dtype=float)
        self.intercept_ = float(np.log(y.mean() / (1.0 - y.mean())))
        for _ in range(self.epochs):
            p = _sigmoid(self.intercept_ + Z @ self.weights_)
            error = p - y
            self.intercept_ -= self.learning_rate * error.mean()
            self.weights_ -= self.learning_rate * ((Z.T @ error) / len(y) + self.l2 * self.weights_)
        return self

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        if self.weights_ is None or self.mean_ is None or self.scale_ is None or self.intercept_ is None:
            raise RuntimeError("fit must be called before predict_proba")
        X = np.asarray(X, dtype=float)
        Z = (X - self.mean_) / self.scale_
        return _sigmoid(self.intercept_ + Z @ self.weights_)

    def predict_one(self, features: np.ndarray) -> float:
        return float(self.predict_proba(np.asarray(features, dtype=float).reshape(1, -1))[0])

    def to_dict(self) -> dict:
        if self.weights_ is None or self.mean_ is None or self.scale_ is None or self.intercept_ is None:
            raise RuntimeError("fit must be called before serialization")
        return {
            "learning_rate": self.learning_rate,
            "epochs": self.epochs,
            "l2": self.l2,
            "mean": self.mean_.tolist(),
            "scale": self.scale_.tolist(),
            "weights": self.weights_.tolist(),
            "intercept": self.intercept_,
        }

    @classmethod
    def from_dict(cls, payload: dict) -> "LogisticRiskModel":
        model = cls(payload.get("learning_rate", 0.05), payload.get("epochs", 1500), payload.get("l2", 1e-3))
        model.mean_ = np.asarray(payload["mean"], dtype=float)
        model.scale_ = np.asarray(payload["scale"], dtype=float)
        model.weights_ = np.asarray(payload["weights"], dtype=float)
        model.intercept_ = float(payload["intercept"])
        return model


def save_model_json(model: LogisticRiskModel, path: str | Path) -> None:
    Path(path).write_text(json.dumps(model.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")


def load_model_json(path: str | Path) -> LogisticRiskModel:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    return LogisticRiskModel.from_dict(payload)
