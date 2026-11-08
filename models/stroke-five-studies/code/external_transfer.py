# -*- coding: utf-8 -*-
"""跨队列迁移实验：D13 公共队列（21,459）⇄ 温州 167 例真实队列。

两队列共有的 7 个变量：age, gender, hypertension, diabetes, hyperuricemia,
hyperlipidaemia, nihss。三个模型（LR / LightGBM / TabPFN）在两个方向上都评估：
  D13 → Wenzhou：在大队列上训练，直接迁移到小队列（外部验证）；
  Wenzhou → D13：在小队列上训练，迁移到大队列的固定测试集（小样本迁移）。
指标：AUROC、AUPRC、Brier、校准斜率/截距（logistic 重校准），并保存预测。

用法:
  python external_transfer.py --d13 ~/D13_20261107/data.csv \
      --wenzhou ~/WENZHOU_DE_20261107/data/Wenzhou_167_cases_deidentified.csv \
      --out out/transfer
"""
import argparse
import json
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score
from sklearn.model_selection import train_test_split

warnings.filterwarnings("ignore")
SEED = 42
WEIGHTS = Path.home() / "TABPFN_BENCH_20261107/weights/tabpfn-v2-classifier-finetuned-zk73skhh.ckpt"
COMMON = ["age", "gender", "hypertension", "diabetes", "hyperuricemia",
          "hyperlipidaemia", "nihss"]


def prep_lr(Xtr, Xte):
    lo = np.percentile(Xtr, 1, axis=0)
    hi = np.percentile(Xtr, 99, axis=0)
    Xtr = np.clip(Xtr, lo, hi)
    Xte = np.clip(Xte, lo, hi)
    mu = Xtr.mean(0)
    sd = Xtr.std(0)
    sd[sd == 0] = 1
    return (Xtr - mu) / sd, (Xte - mu) / sd


def fit_pred(name, Xtr, ytr, Xte):
    from lightgbm import LGBMClassifier
    if name == "lr":
        a, b = prep_lr(Xtr.copy(), Xte.copy())
        m = LogisticRegression(C=1.0, max_iter=5000, random_state=SEED).fit(a, ytr)
        return m.predict_proba(b)[:, 1]
    if name == "lgbm":
        g = LGBMClassifier(n_estimators=300, learning_rate=0.05, num_leaves=31,
                           min_child_samples=50, subsample=0.8, colsample_bytree=0.8,
                           reg_alpha=0.1, reg_lambda=0.1, random_state=SEED,
                           n_jobs=8, verbosity=-1)
        g.fit(Xtr, ytr)
        return g.predict_proba(Xte)[:, 1]
    from tabpfn import TabPFNClassifier
    t = TabPFNClassifier(model_path=str(WEIGHTS), n_estimators="auto", random_state=SEED,
                         ignore_pretraining_limits=True, device="cpu")
    t.fit(Xtr, ytr)
    return t.predict_proba(Xte)[:, 1]


def calib(y, p):
    lp = np.log(np.clip(p, 1e-6, 1 - 1e-6) / (1 - np.clip(p, 1e-6, 1 - 1e-6)))
    m = LogisticRegression(C=1e6, max_iter=1000).fit(lp.reshape(-1, 1), y)
    return float(m.coef_[0, 0]), float(m.intercept_[0])


def metrics(y, p):
    s, i = calib(y, p)
    return {"n": int(len(y)), "events": int(y.sum()),
            "prevalence": float(y.mean()),
            "auroc": float(roc_auc_score(y, p)),
            "auprc": float(average_precision_score(y, p)),
            "brier": float(brier_score_loss(y, p)),
            "cal_slope": s, "cal_intercept": i}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--d13", required=True)
    ap.add_argument("--wenzhou", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--d13-sub", type=int, default=167, help="小样本迁移时 D13 训练子集大小")
    args = ap.parse_args()
    out = Path(args.out); out.mkdir(parents=True, exist_ok=True)

    d13 = pd.read_csv(args.d13)
    d13 = d13.rename(columns={"hyperlipidaemia": "hyperlipidaemia"})
    wx = pd.read_csv(args.wenzhou)
    wx.columns = ["row", "stroke_type", "sex", "age", "age_lt65", "alcohol", "smoking",
                  "hypertension", "diabetes", "hyperlipidemia", "hyperuricemia",
                  "seizure_type", "interval_days", "interval_gt3", "multiple_seizures",
                  "status_epilepticus", "eeg", "asm", "nihss", "nihss_gt14", "infection",
                  "lesion_vol", "lesion_gt10", "cortical", "multilobar", "deep",
                  "ventricular_ext", "surgery", "toast", "thrombolysis", "lipid_lowering",
                  "antiplatelet", "anticoag", "pse", "followup_days", "late_seizure_days",
                  "censor_days"]
    wx = wx.rename(columns={"hyperlipidemia": "hyperlipidaemia", "sex": "gender"})
    Xd = d13[COMMON].to_numpy(float); yd = d13.second_epilepsy.to_numpy(int)
    Xw = wx[COMMON].to_numpy(float); yw = wx.pse.to_numpy(int)

    # D13 固定 80/20 切分（与主分析同种子）
    Xtr, Xte, ytr, yte = train_test_split(Xd, yd, test_size=0.2, stratify=yd, random_state=SEED)
    res, preds = {}, {}

    # 方向一：D13 全量训练 → 温州外部验证
    for name in ["lr", "lgbm", "tabpfn"]:
        Xtr_use, ytr_use = (Xtr, ytr)
        if name == "tabpfn" and len(ytr) > 10000:  # TabPFN 原生上限 10,000
            rng = np.random.default_rng(SEED)
            idx = rng.choice(len(ytr), 10000, replace=False)
            Xtr_use, ytr_use = Xtr[idx], ytr[idx]
        p = fit_pred(name, Xtr_use, ytr_use, Xw)
        preds[f"d13_to_wx_{name}"] = p
        res[f"d13_to_wx_{name}"] = {**metrics(yw, p), "n_train": int(len(ytr_use))}

    # 方向二：D13 小样本（167）→ 温州；同时 D13 自身测试集作参照
    rng = np.random.default_rng(SEED)
    pos = np.where(ytr == 1)[0]; neg = np.where(ytr == 0)[0]
    pn = int(round(args.d13_sub * len(pos) / len(ytr)))
    idx = np.concatenate([rng.choice(pos, pn, replace=False),
                          rng.choice(neg, args.d13_sub - pn, replace=False)])
    for name in ["lr", "lgbm", "tabpfn"]:
        p = fit_pred(name, Xtr[idx], ytr[idx], Xw)
        preds[f"d13small_to_wx_{name}"] = p
        res[f"d13small_to_wx_{name}"] = {**metrics(yw, p), "n_train": int(len(idx))}

    # 方向三：温州（167）训练 → D13 测试集
    for name in ["lr", "lgbm", "tabpfn"]:
        p = fit_pred(name, Xw, yw, Xte)
        preds[f"wx_to_d13_{name}"] = p
        res[f"wx_to_d13_{name}"] = {**metrics(yte, p), "n_train": int(len(yw))}

    # 方向四：D13 全量 → D13 自身（参照上界）
    for name in ["lr", "lgbm"]:
        p = fit_pred(name, Xtr, ytr, Xte)
        preds[f"d13_to_d13_{name}"] = p
        res[f"d13_to_d13_{name}"] = {**metrics(yte, p), "n_train": int(len(ytr))}

    (out / "transfer_results.json").write_text(
        json.dumps(res, ensure_ascii=False, indent=2), encoding="utf-8")
    wx_cols = {k: v for k, v in preds.items() if k.endswith("_to_wx_lr") or "_to_wx_" in k}
    d13_cols = {k: v for k, v in preds.items() if "_to_d13_" in k}
    pd.DataFrame({"y_wx": yw, **wx_cols}).to_csv(out / "predictions_wenzhou.csv", index=False)
    pd.DataFrame({"y_d13": yte, **d13_cols}).to_csv(out / "predictions_d13.csv", index=False)
    print(json.dumps(res, ensure_ascii=False, indent=2))
    print("DONE", out)


if __name__ == "__main__":
    main()
