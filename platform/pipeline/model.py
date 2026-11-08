"""教学模型：合成数据生成、训练、支持范围校验、SHA-256 完整性。

红线（方案 §11）：本模块产出的模型**基于教学合成数据**，R²/AUC 只在合成
数据上成立，不代表真实队列性能。真实数据须走关口②（授权→审计→重训→
独立验证→阈值锁定）。任何页面与导出都必须带 research_only 标识。

逆向设计（§6.2）依赖减药强度变量，而锁定的正向模型契约（§6.1 八字段）
不含该变量，因此逆向使用独立的教学探索模型，且默认受 config 开关约束。
"""
from __future__ import annotations

import hashlib
import json
import math
import os
from dataclasses import dataclass
from typing import Any

import joblib
import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from .contract import MODEL_FIELDS, REJECT_CODES

FORWARD_MODEL_VERSION = "epi-relapse-730d@0.4.1"
REVERSE_MODEL_VERSION = "epi-reverse-teaching@0.1.0"
FORWARD_FILE = "forward_model.joblib"
REVERSE_FILE = "reverse_model.joblib"
SUMS_FILE = "SHA256SUMS"
META_FILE = "model_meta.json"

FEATURES = [f["name"] for f in MODEL_FIELDS]
DEMO_THRESHOLDS = (.20, .40)
RESULT_DISCLAIMER = "本结果基于合成数据，仅供工程联调，不作为减药或临床决策依据。"


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


# --------------------------------------------------------- 教学合成数据
def _base_logit(X: "np.ndarray") -> "np.ndarray":
    """由八字段计算教学用基准 logit（关系设定刻意简化，仅用于联调）。"""
    duration, seizure_free, age_onset, febrile, count, self_lim, dev, eeg = X.T
    return (
        -0.42
        - 0.075 * seizure_free
        + 0.052 * duration
        + 0.114 * np.log1p(count)
        + 0.62 * eeg
        + 0.48 * dev
        + 0.31 * febrile
        - 0.41 * self_lim
        + 0.012 * np.maximum(0.0, 12.0 - age_onset)
    )


def synthesize(n: int = 4000, seed: int = 20261107) -> "np.ndarray, np.ndarray":
    """生成教学合成队列（X, y）。"""
    rng = np.random.default_rng(seed)
    duration = np.round(rng.gamma(2.2, 3.0, n).clip(0, 60), 2)      # F1 年
    seizure_free = np.round(rng.gamma(3.0, 9.0, n).clip(0, 180), 1)  # F2 月
    age_onset = np.round(rng.gamma(2.6, 6.5, n).clip(0, 90), 1)      # F3 年
    febrile = rng.binomial(1, 0.18, n)                               # F4
    seizure_count = rng.poisson(4.5, n).clip(0, 200)                 # F5
    self_limiting = rng.binomial(1, 0.12, n)                         # F6
    dev_delay = rng.binomial(1, 0.16, n)                             # F7
    eeg = rng.binomial(1, 0.34, n)                                   # F8

    X = np.column_stack([duration, seizure_free, age_onset, febrile,
                         seizure_count, self_limiting, dev_delay,
                         eeg]).astype(float)
    p = 1.0 / (1.0 + np.exp(-_base_logit(X)))
    y = rng.binomial(1, p)
    return X, y


def synthesize_with_reduction(n: int = 3000, seed: int = 991107):
    """逆向设计教学数据：额外含减药幅度（%）作为干预变量。

    减药幅度提高复发风险属**教学假设**，非医学结论。
    """
    rng = np.random.default_rng(seed)
    X, _ = synthesize(n, seed)
    reduction = np.round(rng.uniform(0, 60, n), 2)
    p = 1.0 / (1.0 + np.exp(-(_base_logit(X) + 0.028 * reduction)))
    y = rng.binomial(1, p)
    Xr = np.column_stack([X, reduction]).astype(float)
    return Xr, y


# ------------------------------------------------------------- 训练与落盘
def train_model_dir(model_dir: str) -> dict[str, Any]:
    """训练正向 + 逆向教学模型，写入 model_dir，并生成 SHA256SUMS。"""
    os.makedirs(model_dir, exist_ok=True)

    X, y = synthesize()
    Xtr, Xte, ytr, yte = train_test_split(X, y, test_size=0.25,
                                          random_state=20261107, stratify=y)
    fwd = Pipeline([("scaler", StandardScaler()),
                    ("clf", LogisticRegression(max_iter=2000, C=1.0))])
    fwd.fit(Xtr, ytr)
    fwd_auc = float(roc_auc_score(yte, fwd.predict_proba(Xte)[:, 1]))
    fwd_brier = float(np.mean((fwd.predict_proba(Xte)[:, 1] - yte) ** 2))

    Xr, yr = synthesize_with_reduction()
    Xr_tr, Xr_te, yr_tr, yr_te = train_test_split(Xr, yr, test_size=0.25,
                                                 random_state=991107,
                                                 stratify=yr)
    rev = Pipeline([("scaler", StandardScaler()),
                    ("clf", LogisticRegression(max_iter=2000, C=1.0))])
    rev.fit(Xr_tr, yr_tr)
    rev_auc = float(roc_auc_score(yr_te, rev.predict_proba(Xr_te)[:, 1]))

    # 支持范围：训练集每特征 [p1, p99]，超出即 E401，不做外推
    rng = np.random.default_rng(20261107)
    Xall, _ = synthesize(20000, 20261107)
    support = {}
    for i, name in enumerate(FEATURES):
        lo, hi = np.percentile(Xall[:, i], [1, 99])
        support[name] = [float(round(lo, 4)), float(round(hi, 4))]
    Xr_all, _ = synthesize_with_reduction(20000, 991107)
    lo, hi = np.percentile(Xr_all[:, -1], [1, 99])
    support["relative_dose_reduction_pct"] = [float(round(lo, 4)),
                                              float(round(hi, 4))]

    fwd_path = os.path.join(model_dir, FORWARD_FILE)
    rev_path = os.path.join(model_dir, REVERSE_FILE)
    joblib.dump({"pipeline": fwd, "support": support,
                 "features": FEATURES, "version": FORWARD_MODEL_VERSION},
                fwd_path)
    joblib.dump({"pipeline": rev, "support": support,
                 "features": FEATURES + ["relative_dose_reduction_pct"],
                 "version": REVERSE_MODEL_VERSION}, rev_path)

    sums = {FORWARD_FILE: sha256_file(fwd_path), REVERSE_FILE: sha256_file(rev_path)}
    with open(os.path.join(model_dir, SUMS_FILE), "w", encoding="utf-8") as fh:
        for name, digest in sums.items():
            fh.write(f"{digest}  {name}\n")

    meta = {
        "forward_model_version": FORWARD_MODEL_VERSION,
        "reverse_model_version": REVERSE_MODEL_VERSION,
        "data_basis": "teaching_synthetic",
        "research_only": True,
        "synthetic_internal_metrics": {
            "forward_auc": round(fwd_auc, 4), "forward_brier": round(fwd_brier, 5),
            "forward_n": int(len(y)), "reverse_auc": round(rev_auc, 4),
        },
        "warning": ("以上指标仅在教学合成数据的内部拆分上计算，不构成任何真实性能"
                    "声明；真实队列性能须由关口②的独立验证给出。"),
        "support_range": support,
        "sha256": sums,
    }
    with open(os.path.join(model_dir, META_FILE), "w", encoding="utf-8") as fh:
        json.dump(meta, fh, ensure_ascii=False, indent=2)
    return meta


@dataclass
class IntegrityError(Exception):
    detail: str


class Predictor:
    """加载并校验模型包，提供正向预测与逆向探索。"""

    def __init__(self, model_dir: str):
        self.model_dir = model_dir
        self.meta: dict[str, Any] = {}
        self._forward = None
        self._reverse = None
        self._load_meta()
        self._verify_integrity()
        self._load_models()

    # ---- 完整性
    def _load_meta(self) -> None:
        path = os.path.join(self.model_dir, META_FILE)
        if not os.path.exists(path):
            raise IntegrityError(f"{META_FILE} 不存在：请先运行 python -m seed_demo --train")
        self.meta = json.load(open(path, encoding="utf-8"))

    def _verify_integrity(self) -> None:
        sums_path = os.path.join(self.model_dir, SUMS_FILE)
        if not os.path.exists(sums_path):
            raise IntegrityError(f"{SUMS_FILE} 不存在，拒绝启动（E402）")
        expected: dict[str, str] = {}
        for line in open(sums_path, encoding="utf-8"):
            line = line.strip()
            if not line:
                continue
            digest, _, name = line.partition("  ")
            if name.strip() not in (FORWARD_FILE, REVERSE_FILE):
                raise IntegrityError("SHA256SUMS 含未知模型文件（E402）")
            if name.strip() in expected or len(digest.strip()) != 64:
                raise IntegrityError("SHA256SUMS 格式非法（E402）")
            expected[name.strip()] = digest.strip()
        if set(expected) != {FORWARD_FILE, REVERSE_FILE}:
            raise IntegrityError("SHA256SUMS 必须完整列出正向和逆向模型（E402）")
        if expected != self.meta.get("sha256"):
            raise IntegrityError("SHA256SUMS 与 model_meta.json 不一致（E402）")
        for name, digest in expected.items():
            path = os.path.join(self.model_dir, name)
            if not os.path.exists(path):
                raise IntegrityError(f"模型文件缺失 {name}（E402）")
            actual = sha256_file(path)
            if actual != digest:
                raise IntegrityError(
                    f"{REJECT_CODES['E402']}：{name} 期望 {digest[:16]}… 实际 {actual[:16]}…")
        self.integrity = {"ok": True, "sha256": expected}

    def _load_models(self) -> None:
        fwd = joblib.load(os.path.join(self.model_dir, FORWARD_FILE))
        self._forward = fwd["pipeline"]
        self.features = fwd["features"]
        self.support = fwd["support"]
        rev_path = os.path.join(self.model_dir, REVERSE_FILE)
        if os.path.exists(rev_path):
            rev = joblib.load(rev_path)
            self._reverse = rev["pipeline"]
            self.reverse_features = rev["features"]
        else:
            self._reverse = None
            self.reverse_features = []

    # ---- 支持范围
    def in_support(self, features: dict[str, Any]) -> tuple[bool, list[str]]:
        out = []
        for name in self.features:
            val = features.get(name)
            if val is None:
                continue
            lo, hi = self.support.get(name, [None, None])
            if lo is not None and float(val) < lo:
                out.append(f"{name}={val} < 训练支持下限 {lo}")
            if hi is not None and float(val) > hi:
                out.append(f"{name}={val} > 训练支持上限 {hi}")
        return (len(out) == 0), out

    # ---- 正向预测
    def _forward_details(self, values: list[float], risk: float) -> dict[str, Any]:
        """Exact probability contributions relative to the fitted scaler's training mean."""
        scaler = self._forward.named_steps["scaler"]
        classifier = self._forward.named_steps["clf"]
        n = len(self.features)
        masks = np.arange(1 << n)
        bits = 1 << np.arange(n)
        included = (masks[:, None] & bits) != 0
        baseline = np.asarray(scaler.mean_)
        cases = np.where(included, values, baseline)
        probabilities = self._forward.predict_proba(cases)[:, 1]
        sizes = included.sum(axis=1)
        weights = np.asarray([1 / (n * math.comb(n - 1, k)) for k in range(n)])
        labels = {f["name"]: f["label"] for f in MODEL_FIELDS}
        local = []
        for index, name in enumerate(self.features):
            without = masks[~included[:, index]]
            contribution = float(np.dot(weights[sizes[without]],
                                        probabilities[without | bits[index]] - probabilities[without]))
            local.append({"feature": name, "name": labels[name],
                          "direction": "+" if contribution > 0 else "-" if contribution < 0 else "0",
                          "impact": abs(contribution)})
        global_features = [
            {"feature": name, "name": labels[name], "weight": abs(float(weight))}
            for name, weight in zip(self.features, classifier.coef_[0])
        ]
        low, high = DEMO_THRESHOLDS
        return {
            "risk_730": risk, "thresholds": list(DEMO_THRESHOLDS),
            "risk_level": "低危" if risk < low else "中危" if risk <= high else "高危",
            "threshold_basis": "demo_only",
            "baseline_risk": float(probabilities[0]),
            "top_features": sorted(local, key=lambda item: -item["impact"]),
            "global_features": sorted(global_features, key=lambda item: -item["weight"])[:5],
            "risk_curve": [{"t": 730, "risk": risk}],
            "ci": None, "disclaimer": RESULT_DISCLAIMER,
        }

    def predict_rows(self, records: list[dict[str, Any]], *,
                     include_details: bool = False) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        idx_ok: list[int] = []
        matrix = []
        for i, rec in enumerate(records):
            feats = rec["features"]
            missing = [n for n in self.features if feats.get(n) is None]
            if missing:
                # 红线：不用 0 或均值填充缺失，直接拒绝并指明字段
                rows.append(self._reject(rec, "E204",
                                         f"缺失模型字段：{', '.join(missing)}；"
                                         "契约冻结前不得填充默认值"))
                continue
            supported, why = self.in_support(feats)
            if not supported:
                rows.append(self._reject(rec, "E401", "; ".join(why)))
                continue
            idx_ok.append(i)
            matrix.append([float(feats[n]) for n in self.features])
        if matrix:
            probs = self._forward.predict_proba(np.asarray(matrix))[:, 1]
            for j, i in enumerate(idx_ok):
                rec = records[i]
                p = float(probs[j])
                row = {
                    "case_id": rec["management"].get("case_id"),
                    "status": "OK", "risk_730d": round(p, 6),
                    "risk_band": None, "ci_low": None, "ci_high": None,
                    "in_support": True, "reject_codes": [],
                    "model_version": FORWARD_MODEL_VERSION,
                    "research_only": True,
                    "__line__": rec.get("__line__"),
                }
                if include_details:
                    row.update(self._forward_details(matrix[j], row["risk_730d"]))
                rows.append(row)
        return rows

    # ---- 逆向设计
    def reverse_rows(self, records: list[dict[str, Any]], target_risk: float,
                     grid: list[float] | None = None, *,
                     include_details: bool = False) -> list[dict[str, Any]]:
        """给定目标风险，在减药幅度网格上搜索可行区间。

        契约未纳入减药强度变量时（记录缺 relative_dose_reduction_pct 或
        planned_reduction_pct），返回 E403，绝不外推填充。
        """
        requested_grid = grid if grid is not None else [round(x, 1) for x in np.arange(0, 60.1, 2.5)]
        dose_low, dose_high = self.support["relative_dose_reduction_pct"]
        grid = sorted({g for g in requested_grid if dose_low <= g <= dose_high})
        if not grid:
            return [self._reject(rec, "E403", "搜索网格不在训练支持范围内", scenario="reverse")
                    for rec in records]
        rows: list[dict[str, Any]] = []
        for rec in records:
            feats = dict(rec["features"])
            has_dose = ("relative_dose_reduction_pct" in rec.get("extension", {})
                        or "planned_reduction_pct" in rec.get("reverse", {}))
            if self._reverse is None or not has_dose:
                rows.append(self._reject(rec, "E403",
                                         "锁定的正向模型契约（八字段）未纳入减药强度变量；"
                                         "请在 CSV 中提供 planned_reduction_pct（§6.2）"
                                         "或 relative_dose_reduction_pct（§6.3 D2），"
                                         "否则无可行域，拒绝外推",
                                         scenario="reverse"))
                continue
            supported, why = self.in_support(feats)
            if not supported:
                rows.append(self._reject(rec, "E401", "; ".join(why),
                                         scenario="reverse"))
                continue
            missing = [n for n in self.features if feats.get(n) is None]
            if missing:
                rows.append(self._reject(rec, "E204",
                                         f"缺失模型字段：{', '.join(missing)}",
                                         scenario="reverse"))
                continue
            base = np.asarray([[float(feats[n]) for n in self.features]
                               * len(grid)]).reshape(len(grid), len(self.features))
            base = np.column_stack([base, np.asarray(grid)])
            probs = self._reverse.predict_proba(base)[:, 1]
            feasible = [g for g, p in zip(grid, probs) if p <= target_risk]
            if not feasible:
                rows.append({
                    "case_id": rec["management"].get("case_id"),
                    "status": "REJECTED", "risk_730d": None, "risk_band": None,
                    "ci_low": None, "ci_high": None, "in_support": True,
                    "reject_codes": ["E403"],
                    "reject_reason": f"网格内最小风险 {float(probs.min()):.3f} 仍高于目标 {target_risk}",
                    "model_version": REVERSE_MODEL_VERSION, "research_only": True,
                    "target_risk": target_risk, "feasible_reduction_range": None,
                    "dose_range_mg": None, "extrapolated": False,
                    "support_note": "教学探索模型，非临床建议",
                    "__line__": rec.get("__line__"),
                })
                continue
            lo, hi = min(feasible), max(feasible)
            dose = rec.get("reverse", {}).get("current_daily_dose_mg")
            dose_range = None
            if dose:
                dose_range = {"mg_low": round(dose * (1 - hi / 100.0), 2),
                              "mg_high": round(dose * (1 - lo / 100.0), 2)}
            row = {
                "case_id": rec["management"].get("case_id"), "status": "OK",
                "risk_730d": round(float(probs[list(grid).index(lo)]), 6),
                "risk_band": None, "ci_low": None, "ci_high": None,
                "in_support": True, "reject_codes": [],
                "model_version": REVERSE_MODEL_VERSION, "research_only": True,
                "target_risk": target_risk,
                "feasible_reduction_range": {"pct_low": lo, "pct_upper": hi},
                "dose_range_mg": dose_range, "extrapolated": False,
                "support_note": ("在教学合成模型的支持范围内给出可行减药幅度区间；"
                                 "未经院内独立验证，禁止作为处方或临床建议"),
                "__line__": rec.get("__line__"),
            }
            if include_details:
                planned = rec.get("reverse", {}).get("planned_reduction_pct")
                if planned is None:
                    planned = rec.get("extension", {}).get("relative_dose_reduction_pct")
                selected = sorted({0, len(feasible) // 2, len(feasible) - 1})
                risks = dict(zip(grid, probs))
                row["scenarios"] = [
                    {"changes": [{"feature": "planned_reduction_pct", "from": planned,
                                  "to": feasible[i]}],
                     "new_risk": round(float(risks[feasible[i]]), 6)}
                    for i in selected
                ]
                if planned is not None and dose_low <= planned <= dose_high:
                    planned_row = [[float(feats[n]) for n in self.features] + [float(planned)]]
                    row["reference_risk"] = round(float(self._reverse.predict_proba(planned_row)[0, 1]), 6)
                row["disclaimer"] = RESULT_DISCLAIMER
            rows.append(row)
        return rows

    def _reject(self, rec: dict[str, Any], code: str, reason: str,
                scenario: str = "forward") -> dict[str, Any]:
        out = {
            "case_id": rec.get("management", {}).get("case_id"),
            "status": "REJECTED", "risk_730d": None, "risk_band": None,
            "ci_low": None, "ci_high": None, "in_support": code != "E401",
            "reject_codes": [code], "reject_reason": reason,
            "model_version": (REVERSE_MODEL_VERSION if scenario == "reverse"
                              else FORWARD_MODEL_VERSION),
            "research_only": True, "__line__": rec.get("__line__"),
        }
        if scenario == "reverse":
            out.update({"target_risk": None, "feasible_reduction_range": None,
                        "dose_range_mg": None, "extrapolated": True,
                        "support_note": "拒绝外推"})
        return out
