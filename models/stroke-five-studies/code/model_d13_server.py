# -*- coding: utf-8 -*-
r"""
================================================================================
D13 缺血性卒中后一年内继发性癫痫 —— 三场景建模（服务器运行版）
================================================================================

【科学口径】与冻结方案《D13 变量分组与建模起步方案》及原型 model_d13.py 完全一致：
    - 结局 second_epilepsy（一年内继发性癫痫二分类标签）
    - 特征集 A(36) / B(70) / C(74)
    - seed 42 分层 80/20 切分；训练集内 5 折分层 CV
    - LR(C=1.0 L2, max_iter=3000, 无类权重)：折内 winsorize(1%/99%) + log1p(13 列) + 标准化
    - LightGBM(CV: 1000 树 lr0.05 31叶 min_child50 sub0.8 col0.8 scale_pos_weight
      seed42 验证折早停50；测试模型: 300 树同参数)：原始数值
    - 指标：AUROC / AUPRC / Brier（CV 均值±SD、OOF 拼接、测试集单值）
      + 测试集 ROC/PR、校准曲线、决策曲线 + 稀疏二值变量 2×2 频数
    - 敏感性分析：full（保留完全重复行，主分析）/ dedup（去重后）

【工程适配（不改科学口径）】
    - 路径、线程数改为命令行参数
    - 新增：测试集 250 次 bootstrap 95% 区间（固定模型重抽测试行）
    - 新增：逐折预测收据 predictions.csv / fold_split.csv（供独立审计）
    - 新增：joblib 模型存档、环境记录 env_record.txt、run_record.md
    - --smoke N：预检用，子样本 + 少量 bootstrap，产物写独立 smoke 目录，不计正式完成数

【运行示例】
    python model_d13_server.py --data data.csv --out results/full --tag full --bootstrap 250 --n-jobs 32
    python model_d13_server.py --data data.csv --out results/dedup --tag dedup --bootstrap 250 --n-jobs 32
================================================================================
"""
import argparse
import hashlib
import json
import os
import platform
import sys
import time
import warnings
from datetime import datetime

import joblib
import numpy as np
import pandas as pd

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import matplotlib
matplotlib.use("Agg")  # 无界面后端
import matplotlib.pyplot as plt

from sklearn.model_selection import train_test_split, StratifiedKFold
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (roc_auc_score, average_precision_score,
                             brier_score_loss, roc_curve, precision_recall_curve)
from sklearn.calibration import calibration_curve
from sklearn.exceptions import ConvergenceWarning

warnings.filterwarnings("ignore", category=ConvergenceWarning)

try:
    import lightgbm as lgb
    HAS_LGB = True
except Exception as _e:
    HAS_LGB = False
    print("[WARN] LightGBM 未安装，将跳过 LGBM 模型:", _e)

# ----------------------------------------------------------------------------
# 冻结科学常量（与原型一致，禁止改动）
# ----------------------------------------------------------------------------
SEED = 42
TEST_SIZE = 0.20
N_SPLITS = 5
RUN_XGBOOST = False

LR_C = 1.0
LR_MAX_ITER = 3000
LR_CLASS_WEIGHT = None

LOG1P_COLS = ["crp", "ast", "alt", "creatinine", "d_dimer", "ck", "ck_mb",
              "ldh", "hbdh", "ima", "anion_gap", "tg", "bua"]
SPARSE_POS_THRESHOLD = 500

A_DEMO = ["age", "gender", "nihss"]
A_COMORB = ["uremia", "fatty_liver", "diabetes", "hypertension",
            "coronary_disease", "atrial_fibrillation", "hyperuricemia",
            "hyperlipidaemia"]
A_BRAIN = ["frontal_lobe", "parietal_lobe", "temporal_lobe", "occipital_lobe",
           "insular_lobe", "range_lobe", "basal_ganglia", "capsula_interna",
           "brainstem", "epencephalon", "paraventricular", "centrum_semiovale",
           "thalamus", "subcortex_lobe"]
A_VESSEL = ["aca", "mca", "pca", "va", "ba", "cca_plaque", "ica_plaque",
            "eca_plaque", "ant_circle", "post_circle", "large_ves_as"]

FEATURES_A = A_DEMO + A_COMORB + A_BRAIN + A_VESSEL          # 36 个

LABS = ["plt", "wbc", "rbc", "hba1c", "crp", "tg", "ldl", "hdl", "ast", "alt",
        "bilirubin", "albumin", "urea", "creatinine", "bua", "pt", "aptt", "tt",
        "inr", "d_dimer", "fibrinogen", "ck", "ck_mb", "ldh", "hbdh", "ima",
        "na", "k", "cl", "ca", "p", "lactate", "anion_gap", "tco2"]      # 34 个

FEATURES_B = FEATURES_A + LABS                               # 70 个

POST = ["dvt", "cerebral_hernia", "hydrocephalus", "hypoproteinemia"]  # 4 个（泄漏风险）

FEATURES_C = FEATURES_B + POST                               # 74 个

FEATURE_SETS = {"A": FEATURES_A, "B": FEATURES_B, "C": FEATURES_C}

ORD_COLS = ["age", "nihss", "range_lobe"]
LAB_COLS = LABS
BIN_COLS = [c for c in FEATURES_C if c not in LABS and c not in ORD_COLS]


def sha256_file(p):
    return hashlib.sha256(open(p, "rb").read()).hexdigest()


def sparse_frequency_report(df, out_dir):
    rows = []
    for c in BIN_COLS:
        n1 = int((df[c] == 1).sum())
        if n1 >= SPARSE_POS_THRESHOLD:
            continue
        tab = pd.crosstab(df[c], df["second_epilepsy"])
        cells = {}
        for v in (0, 1):
            for y in (0, 1):
                cells[(v, y)] = int(tab.loc[v, y]) if (v in tab.index and y in tab.columns) else 0
        zero_cell = any(cells[(v, y)] == 0 for v in (0, 1) for y in (0, 1))
        rows.append({"variable": c, "pos_count": n1,
                     "n_y0_v0": cells[(0, 0)], "n_y0_v1": cells[(1, 0)],
                     "n_y1_v0": cells[(0, 1)], "n_y1_v1": cells[(1, 1)],
                     "any_zero_cell": bool(zero_cell),
                     "note": "存在0单元格，LR可能完全分离，敏感性分析考虑移除" if zero_cell else ""})
    report = pd.DataFrame(rows).sort_values("pos_count")
    report.to_csv(os.path.join(out_dir, "sparse_var_frequency.csv"),
                  index=False, encoding="utf-8-sig")
    print(f"[sparse] 稀疏二值变量频数表已保存（{len(report)} 个）")
    return report


def fit_preproc_lr(X_train):
    """由训练折估计 LR 预处理参数（winsorize 阈值 / log1p 列 / 标准化均值方差）。"""
    lab_cols = [c for c in LAB_COLS if c in X_train.columns]
    ord_cols = [c for c in ORD_COLS if c in X_train.columns]
    log1p_cols = [c for c in LOG1P_COLS if c in lab_cols]
    winsor, stats = {}, {}
    for c in lab_cols:
        lo, hi = X_train[c].quantile(0.01), X_train[c].quantile(0.99)
        winsor[c] = [float(lo), float(hi)]
    for c in ord_cols + lab_cols:
        mu, sd = X_train[c].mean(), X_train[c].std(ddof=0)
        sd = sd if sd > 1e-12 else 1.0
        stats[c] = [float(mu), float(sd)]
    return {"lab_cols": lab_cols, "ord_cols": ord_cols, "log1p_cols": log1p_cols,
            "winsor": winsor, "stats": stats}


def apply_preproc_lr(X, params):
    """用已估计参数变换（训练折或验证/测试折同一函数）。"""
    Xp = X.copy()
    for c in params["lab_cols"]:
        lo, hi = params["winsor"][c]
        Xp[c] = Xp[c].clip(lo, hi)
        if c in params["log1p_cols"]:
            Xp[c] = np.log1p(Xp[c])
    for c in params["ord_cols"] + params["lab_cols"]:
        mu, sd = params["stats"][c]
        Xp[c] = (Xp[c] - mu) / sd
    return Xp


def preprocess_lr(X_train, X_test):
    """兼容原型接口：折内 winsorize+log1p+标准化。"""
    params = fit_preproc_lr(X_train)
    return apply_preproc_lr(X_train, params), apply_preproc_lr(X_test, params), params


def make_lr():
    return LogisticRegression(C=LR_C, max_iter=LR_MAX_ITER,
                              class_weight=LR_CLASS_WEIGHT)


def _scale_pos_weight(y):
    n_pos = int((y == 1).sum())
    n_neg = int((y == 0).sum())
    return (n_neg / n_pos) if n_pos > 0 else 1.0


def make_lgbm(n_estimators, n_jobs, y_train=None):
    kw = dict(n_estimators=n_estimators, learning_rate=0.05, num_leaves=31,
              min_child_samples=50, subsample=0.8, colsample_bytree=0.8,
              reg_alpha=0.1, reg_lambda=0.1, random_state=SEED, n_jobs=n_jobs,
              verbosity=-1)
    if y_train is not None:
        kw["scale_pos_weight"] = _scale_pos_weight(y_train)
    return lgb.LGBMClassifier(**kw)


def eval_metrics(y_true, y_prob):
    return {"auroc": roc_auc_score(y_true, y_prob),
            "auprc": average_precision_score(y_true, y_prob),
            "brier": brier_score_loss(y_true, y_prob)}


def _cv_fold_summary(fold_metrics):
    out = {}
    for k in ("auroc", "auprc", "brier"):
        vals = [m[k] for m in fold_metrics]
        out[f"{k}_mean"] = float(np.mean(vals))
        out[f"{k}_sd"] = float(np.std(vals))
    return out


def run_cv(X, y, model_kind, cv, n_jobs, fold_records, fs_name):
    """训练集内 5 折 CV：返回 OOF 概率、每折指标、提示；预测写入 fold_records。"""
    oof = np.zeros(len(y))
    fold_metrics = []
    notes = []
    for tr_idx, va_idx in cv.split(X, y):
        Xtr, Xva = X.iloc[tr_idx], X.iloc[va_idx]
        ytr, yva = y.iloc[tr_idx], y.iloc[va_idx]
        fold_no = len(fold_metrics)  # 当前折序号 0..4

        if model_kind == "lr":
            Xtr_p, Xva_p, _ = preprocess_lr(Xtr, Xva)
            model = make_lr()
            model.fit(Xtr_p, ytr)
            if getattr(model, "n_iter_", [0])[0] >= LR_MAX_ITER:
                notes.append("LR未收敛(达到max_iter)")
            if np.abs(model.coef_).max() > 50:
                notes.append("LR系数>50(疑似完全分离)")
        elif model_kind == "lgbm":
            Xtr_p, Xva_p = Xtr, Xva
            model = make_lgbm(1000, n_jobs, ytr)
            model.fit(Xtr_p, ytr, eval_set=[(Xva_p, yva)],
                      callbacks=[lgb.early_stopping(50, verbose=False)])
        else:
            raise ValueError(f"未知模型类型: {model_kind}")

        proba = model.predict_proba(Xva_p)[:, 1]
        oof[va_idx] = proba
        fold_metrics.append(eval_metrics(yva, proba))
        for i, idx in enumerate(va_idx):
            fold_records.append({"record_id": int(X.index[idx]), "y_true": int(y.iloc[idx]),
                                 "role": "oof", "fold": fold_no,
                                 "feature_set": fs_name, "model": model_kind,
                                 "proba": float(proba[i])})
    return oof, fold_metrics, notes


def fit_eval_test(X_train, y_train, X_test, y_test, model_kind, n_jobs):
    """测试模型：在完整训练集上拟合，评估测试集。返回概率、指标、可存档对象。"""
    if model_kind == "lr":
        Xtr_p, Xte_p, params = preprocess_lr(X_train, X_test)
        model = make_lr()
        model.fit(Xtr_p, y_train)
        y_prob = model.predict_proba(Xte_p)[:, 1]
        artifact = {"kind": "lr", "model": model, "preproc": params,
                    "features": list(X_train.columns)}
    elif model_kind == "lgbm":
        model = make_lgbm(300, n_jobs, y_train)
        model.fit(X_train, y_train)
        y_prob = model.predict_proba(X_test)[:, 1]
        artifact = {"kind": "lgbm", "model": model, "features": list(X_train.columns)}
    else:
        raise ValueError(model_kind)
    return y_prob, eval_metrics(y_test, y_prob), artifact


def bootstrap_ci(y_true, y_prob, n_boot, rng):
    """测试集固定模型 bootstrap：重抽测试行，250 次，报 2.5/97.5 百分位。"""
    if n_boot <= 0:
        return {}
    y_true = np.asarray(y_true)  # Series 带原索引，按标签取数会 KeyError，先转 numpy
    y_prob = np.asarray(y_prob)
    n = len(y_true)
    out = {}
    for k in ("auroc", "auprc", "brier"):
        vals = []
        for _ in range(n_boot):
            idx = rng.integers(0, n, n)
            vals.append(eval_metrics(y_true[idx], y_prob[idx])[k])
        lo, hi = np.quantile(vals, [0.025, 0.975])
        out[f"test_{k}_lo"] = float(lo)
        out[f"test_{k}_hi"] = float(hi)
    return out


def net_benefit(y_true, y_prob, thresholds):
    n = len(y_true)
    nb = []
    for t in thresholds:
        pred = (y_prob >= t).astype(int)
        tp = int(((pred == 1) & (y_true == 1)).sum())
        fp = int(((pred == 1) & (y_true == 0)).sum())
        nb.append(tp / n - fp / n * (t / (1 - t)))
    return np.array(nb)


def make_figs(test_preds, y_test, tag, out_dir):
    fs_list = ["A", "B", "C"]
    model_kinds = sorted({k for (k, _) in test_preds.keys()})
    colors = {"lr": "tab:blue", "lgbm": "tab:red", "xgb": "tab:green"}
    linestyles = {"A": "-", "B": "--", "C": ":"}

    fig, axes = plt.subplots(1, 2, figsize=(12, 5))
    for mk in model_kinds:
        for fs in fs_list:
            if (mk, fs) not in test_preds:
                continue
            p = test_preds[(mk, fs)]
            fpr, tpr, _ = roc_curve(y_test, p)
            prec, rec, _ = precision_recall_curve(y_test, p)
            auroc = roc_auc_score(y_test, p)
            auprc = average_precision_score(y_test, p)
            lab = f"{mk.upper()}-{fs}"
            axes[0].plot(fpr, tpr, color=colors[mk], ls=linestyles[fs],
                         label=f"{lab} (AUC={auroc:.3f})")
            axes[1].plot(rec, prec, color=colors[mk], ls=linestyles[fs],
                         label=f"{lab} (AP={auprc:.3f})")
    axes[0].plot([0, 1], [0, 1], "k--", lw=0.8)
    axes[0].set_xlabel("1-Specificity"); axes[0].set_ylabel("Sensitivity")
    axes[0].set_title("ROC (test)"); axes[0].legend(fontsize=7)
    axes[1].set_xlabel("Recall"); axes[1].set_ylabel("Precision")
    axes[1].set_title("Precision-Recall (test)"); axes[1].legend(fontsize=7)
    fig.suptitle(f"D13 second_epilepsy — {tag}")
    fig.tight_layout()
    fig.savefig(os.path.join(out_dir, f"fig_roc_pr_{tag}.png"), dpi=150)
    plt.close(fig)

    fig, axes = plt.subplots(1, 3, figsize=(15, 4.5), sharey=True)
    for j, fs in enumerate(fs_list):
        ax = axes[j]
        ax.plot([0, 1], [0, 1], "k--", lw=0.8)
        for mk in model_kinds:
            if (mk, fs) not in test_preds:
                continue
            frac, mean_pred = calibration_curve(y_test, test_preds[(mk, fs)],
                                                n_bins=10, strategy="uniform")
            ax.plot(mean_pred, frac, marker="o", color=colors[mk],
                    label=f"{mk.upper()} Brier={brier_score_loss(y_test, test_preds[(mk, fs)]):.4f}")
        ax.set_title(f"Calibration — Feature set {fs}")
        ax.set_xlabel("Mean predicted probability"); ax.legend(fontsize=7)
    axes[0].set_ylabel("Fraction of positives")
    fig.suptitle(f"D13 calibration (test) — {tag}")
    fig.tight_layout()
    fig.savefig(os.path.join(out_dir, f"fig_calibration_{tag}.png"), dpi=150)
    plt.close(fig)

    thr = np.linspace(0.01, 0.50, 100)
    prev = float(y_test.mean())
    treat_all = prev - (1 - prev) * thr / (1 - thr)
    fig, axes = plt.subplots(1, 3, figsize=(15, 4.5), sharey=True)
    for j, fs in enumerate(fs_list):
        ax = axes[j]
        ax.plot(thr, treat_all, "k--", lw=0.8, label="Treat all")
        ax.plot(thr, np.zeros_like(thr), "k-", lw=0.8, label="Treat none")
        for mk in model_kinds:
            if (mk, fs) not in test_preds:
                continue
            nb = net_benefit(y_test, test_preds[(mk, fs)], thr)
            ax.plot(thr, nb, color=colors[mk], label=f"{mk.upper()}")
        ax.set_title(f"Decision curve — Feature set {fs}")
        ax.set_xlabel("Threshold probability"); ax.legend(fontsize=7)
    axes[0].set_ylabel("Net benefit")
    fig.suptitle(f"D13 decision curve (test) — {tag}")
    fig.tight_layout()
    fig.savefig(os.path.join(out_dir, f"fig_decision_curve_{tag}.png"), dpi=150)
    plt.close(fig)


def run_one(df, tag, out_dir, n_jobs, n_boot, fold_split, pred_records, models_dir):
    """对某一版数据（full / dedup）执行完整三场景建模，返回测试集预测字典。"""
    X = df[FEATURES_C].copy()
    y = df["second_epilepsy"].copy()

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=TEST_SIZE, random_state=SEED, stratify=y)
    cv = StratifiedKFold(n_splits=N_SPLITS, shuffle=True, random_state=SEED)

    print(f"\n===== [{tag}] N={len(df)} 训练={len(X_train)} 测试={len(X_test)} "
          f"训练阳性={int(y_train.sum())} 测试阳性={int(y_test.sum())} =====")

    # 划分收据（供审计核对折成员与测试集身份）
    for i in X_train.index:
        fold_split.append({"record_id": int(i), "y_true": int(y.loc[i]), "role": "train", "fold": -1})
    for i in X_test.index:
        fold_split.append({"record_id": int(i), "y_true": int(y.loc[i]), "role": "test", "fold": -1})
    # 折成员（用字典 O(1) 回填，避免 2 万行 × 5 折的 O(n²) 扫描）
    rec_by_id = {rr["record_id"]: rr for rr in fold_split}
    for fold_no, (tr_idx, va_idx) in enumerate(cv.split(X_train, y_train)):
        for i in va_idx:
            rec_by_id[int(X_train.index[i])]["fold"] = fold_no

    model_kinds = ["lr", "lgbm"] if HAS_LGB else ["lr"]

    test_preds = {}
    results = []
    rng = np.random.default_rng(SEED)

    for fs_name, fs_cols in FEATURE_SETS.items():
        for mk in model_kinds:
            Xf, Xf_test = X_train[fs_cols], X_test[fs_cols]
            # —— 训练集内 5 折 CV ——
            oof, fold_metrics, notes = run_cv(Xf, y_train, mk, cv, n_jobs, pred_records, fs_name)
            cv_sum = _cv_fold_summary(fold_metrics)
            oof_pooled = eval_metrics(y_train, oof)
            # —— 测试集评估 ——
            y_prob, test_m, artifact = fit_eval_test(Xf, y_train, Xf_test, y_test, mk, n_jobs)
            test_preds[(mk, fs_name)] = y_prob
            joblib.dump(artifact, os.path.join(models_dir, f"{tag}_{fs_name}_{mk}.joblib"))

            row = {"data": tag, "feature_set": fs_name, "model": mk}
            row.update(cv_sum)
            row["auroc_oof_pooled"] = oof_pooled["auroc"]
            row["auprc_oof_pooled"] = oof_pooled["auprc"]
            row["brier_oof_pooled"] = oof_pooled["brier"]
            row["test_auroc"] = test_m["auroc"]
            row["test_auprc"] = test_m["auprc"]
            row["test_brier"] = test_m["brier"]
            row.update(bootstrap_ci(y_test, y_prob, n_boot, rng))
            row["notes"] = "; ".join(sorted(set(notes)))
            results.append(row)
            print(f"  [{tag}] {fs_name}/{mk}: test_AUROC={test_m['auroc']:.4f} "
                  f"test_AUPRC={test_m['auprc']:.4f} test_Brier={test_m['brier']:.4f}")

            # 测试集预测收据
            for i in range(len(Xf_test)):
                pred_records.append({"record_id": int(Xf_test.index[i]),
                                     "y_true": int(y_test.iloc[i]),
                                     "role": "test", "fold": -1,
                                     "feature_set": fs_name, "model": mk,
                                     "proba": float(y_prob[i])})

    pd.DataFrame(results).to_csv(os.path.join(out_dir, f"results_metrics_{tag}.csv"),
                                 index=False, encoding="utf-8-sig")
    return test_preds, y_test


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--tag", required=True, choices=["full", "dedup"])
    ap.add_argument("--bootstrap", type=int, default=250)
    ap.add_argument("--n-jobs", type=int, default=-1)
    ap.add_argument("--smoke", type=int, default=0, help="预检：子样本行数（>0 时产物写入 OUT/smoke）")
    a = ap.parse_args()

    t0 = time.time()
    smoke = a.smoke > 0
    out_dir = os.path.join(a.out, "smoke") if smoke else a.out
    os.makedirs(out_dir, exist_ok=True)
    models_dir = os.path.join(out_dir, "models")
    os.makedirs(models_dir, exist_ok=True)
    n_boot = 5 if smoke else a.bootstrap

    print("=" * 70)
    print(f"D13 三场景建模（服务器版） tag={a.tag} smoke={a.smoke} bootstrap={n_boot} n_jobs={a.n_jobs}")
    print(f"  LightGBM: {'已安装' if HAS_LGB else '未安装(将跳过)'}  数据: {a.data}")
    print("=" * 70)

    df = pd.read_csv(a.data)
    if smoke:
        df = df.sample(a.smoke, random_state=SEED).reset_index(drop=True)
        print(f"[smoke] 子样本 {len(df)} 行（仅预检，不计正式完成数）")
    elif a.tag == "dedup":
        before = len(df)
        df = df.drop_duplicates().reset_index(drop=True)
        print(f"[dedup] 去重后 {len(df)} 行（原 {before} 行）")

    print(f"数据：{df.shape[0]} 行 × {df.shape[1]} 列，阳性 {int(df['second_epilepsy'].sum())} 例 "
          f"({100.0 * df['second_epilepsy'].mean():.2f}%)")
    data_sha = sha256_file(a.data)

    pred_records = []
    fold_split = []

    if not smoke and a.tag == "full":
        sparse_frequency_report(df, out_dir)

    test_preds, y_test = run_one(df, a.tag, out_dir, a.n_jobs, n_boot,
                                 fold_split, pred_records, models_dir)
    make_figs(test_preds, y_test, a.tag, out_dir)

    # —— 收据 ——
    pd.DataFrame(pred_records).to_csv(os.path.join(out_dir, "predictions.csv"),
                                      index=False, encoding="utf-8-sig")
    pd.DataFrame(fold_split).to_csv(os.path.join(out_dir, "fold_split.csv"),
                                    index=False, encoding="utf-8-sig")

    # —— 可复现凭据 ——
    split_info = {
        "tag": a.tag, "smoke_rows": a.smoke or None,
        "data_path": os.path.abspath(a.data), "data_sha256": data_sha,
        "seed": SEED, "test_size": TEST_SIZE, "n_splits": N_SPLITS,
        "n_rows": int(len(df)),
        "n_train": None,  # 下方从 fold_split 重算
        "positive_rate": float(df["second_epilepsy"].mean()),
        "models": ["lr"] + (["lgbm"] if HAS_LGB else []),
        "lr_config": {"C": LR_C, "max_iter": LR_MAX_ITER, "class_weight": str(LR_CLASS_WEIGHT)},
        "lgbm_cv": {"n_estimators": 1000, "learning_rate": 0.05, "num_leaves": 31,
                    "min_child_samples": 50, "subsample": 0.8, "colsample_bytree": 0.8,
                    "reg_alpha": 0.1, "reg_lambda": 0.1, "early_stopping": 50,
                    "scale_pos_weight": "per-fold n_neg/n_pos"},
        "lgbm_test": {"n_estimators": 300, "learning_rate": 0.05, "num_leaves": 31,
                      "min_child_samples": 50, "subsample": 0.8, "colsample_bytree": 0.8,
                      "reg_alpha": 0.1, "reg_lambda": 0.1, "scale_pos_weight": "train n_neg/n_pos"},
        "log1p_cols": LOG1P_COLS,
        "bootstrap": {"n": n_boot, "units": "test rows", "model": "fixed (no refit)"},
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "lightgbm": lgb.__version__ if HAS_LGB else None,
        "numpy": np.__version__, "pandas": pd.__version__,
        "sklearn": __import__("sklearn").__version__,
    }
    fs = pd.DataFrame(fold_split)
    split_info["n_train"] = int((fs.role == "train").sum())
    split_info["n_test"] = int((fs.role == "test").sum())
    split_info["fold_sizes"] = fs[fs.role == "train"].groupby("fold").size().to_dict()
    split_info["fold_positive"] = fs[fs.role == "train"].groupby("fold")["y_true"].sum().to_dict()
    split_info["test_positive"] = int(fs[fs.role == "test"].y_true.sum())
    with open(os.path.join(out_dir, "split_info.json"), "w", encoding="utf-8") as f:
        json.dump(split_info, f, ensure_ascii=False, indent=2)

    # —— 环境记录 ——
    try:
        import subprocess
        pip_freeze = subprocess.run([sys.executable, "-m", "pip", "freeze"],
                                    capture_output=True, text=True, timeout=120).stdout
    except Exception:
        pip_freeze = "(pip freeze 不可用)"
    with open(os.path.join(out_dir, "env_record.txt"), "w", encoding="utf-8") as f:
        f.write(f"python: {sys.version}\nplatform: {platform.platform()}\n\n"
                f"lightgbm: {lgb.__version__ if HAS_LGB else 'missing'}\n"
                f"numpy: {np.__version__}\npandas: {pd.__version__}\n"
                f"sklearn: {__import__('sklearn').__version__}\n"
                f"joblib: {joblib.__version__}\nmatplotlib: {matplotlib.__version__}\n\n"
                f"--- pip freeze ---\n{pip_freeze}")

    # —— 运行记录 ——
    elapsed = time.time() - t0
    with open(os.path.join(out_dir, "run_record.md"), "w", encoding="utf-8") as f:
        f.write(f"# D13 运行记录 {datetime.now().isoformat(timespec='seconds')}\n\n"
                f"- tag: {a.tag}（{'smoke 预检 ' + str(a.smoke) + ' 行' if smoke else '正式运行'}）\n"
                f"- 命令: python model_d13_server.py --data {a.data} --out {a.out} "
                f"--tag {a.tag} --bootstrap {n_boot} --n-jobs {a.n_jobs}"
                f"{' --smoke ' + str(a.smoke) if smoke else ''}\n"
                f"- 数据 SHA256: {data_sha}\n"
                f"- 耗时: {elapsed:.1f} 秒\n"
                f"- 状态: 完成\n"
                f"- 产物: results_metrics_{a.tag}.csv, predictions.csv, fold_split.csv, "
                f"split_info.json, env_record.txt, models/{a.tag}_*.joblib, fig_*_{a.tag}.png"
                f"{', sparse_var_frequency.csv' if (not smoke and a.tag == 'full') else ''}\n"
                f"- 注意: LightGBM 多线程下极小数值波动可能跨次运行出现（科学结论不变）；"
                f"bootstrap 区间为固定模型重抽测试行口径。\n")
    print(f"\n[完成] tag={a.tag} 耗时 {elapsed:.1f}s 输出目录: {out_dir}")


if __name__ == "__main__":
    main()
