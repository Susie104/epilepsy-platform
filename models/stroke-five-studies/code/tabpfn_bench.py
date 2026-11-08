# -*- coding: utf-8 -*-
"""TabPFN 小样本学习曲线基准（D13 三场景 A/B/C × full/dedup）。

设计要点（与 model_d13_server.py 的科学口径保持一致）：
- 切分：stratified 80/20，random_state=42（与场景脚本完全相同），所有模型共用同一测试集。
- 去重：dedup = df.drop_duplicates()（与场景脚本相同）。
- 训练规模梯度：嵌套子集（同一置换序列的前缀），保证不同规模之间可比。
- 三个模型在**同一训练子集**上拟合：LR（winsorize 1/99 + log1p + 标准化）、
  LightGBM（场景脚本的测试模型参数）、TabPFN v2 分类器（零调参）。
- 指标：固定测试集上的 AUROC / AUPRC / Brier；保存逐行预测供 bootstrap。

用法:
  python tabpfn_bench.py --features A --tag full  --out out/full_A
"""
import argparse
import json
import platform
import sys
import time
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

A_DEMO = ["age", "gender", "nihss"]
A_COMORB = ["uremia", "fatty_liver", "diabetes", "hypertension", "coronary_disease",
            "atrial_fibrillation", "hyperuricemia", "hyperlipidaemia"]
A_BRAIN = ["frontal_lobe", "parietal_lobe", "temporal_lobe", "occipital_lobe",
           "insular_lobe", "range_lobe", "basal_ganglia", "capsula_interna",
           "brainstem", "epencephalon", "paraventricular", "centrum_semiovale",
           "thalamus", "subcortex_lobe"]
A_VESSEL = ["aca", "mca", "pca", "va", "ba", "cca_plaque", "ica_plaque", "eca_plaque",
            "ant_circle", "post_circle", "large_ves_as"]
FEATURES_A = A_DEMO + A_COMORB + A_BRAIN + A_VESSEL
LABS = ["plt", "wbc", "rbc", "hba1c", "crp", "tg", "ldl", "hdl", "ast", "alt",
        "bilirubin", "albumin", "urea", "creatinine", "bua", "pt", "aptt", "tt",
        "inr", "d_dimer", "fibrinogen", "ck", "ck_mb", "ldh", "hbdh", "ima",
        "na", "k", "cl", "ca", "p", "lactate", "anion_gap", "tco2"]
POST = ["dvt", "cerebral_hernia", "hydrocephalus", "hypoproteinemia"]
FEATURE_SETS = {"A": FEATURES_A, "B": FEATURES_A + LABS, "C": FEATURES_A + LABS + POST}
LOG1P_COLS = ["crp", "ast", "alt", "creatinine", "d_dimer", "ck", "ck_mb",
              "ldh", "hbdh", "ima", "anion_gap", "tg", "bua"]
SIZES = [100, 250, 500, 1000, 2000, 4000, 8000, 16000]


ORD = ["age", "nihss", "range_lobe"]


def lr_transform(Xtr, Xte, cols):
    """与场景脚本逐位一致的 LR 预处理：
    - 标准化均值/方差在**原始训练值**上计算（winsorize/log1p 之前），
      应用于 winsorize(1%/99%) + log1p(13列) 之后的值
    - 连续/有序列（age/nihss/range_lobe）：仅标准化，不 winsorize
    - 二值列：保持 0/1 原值
    （与 model_d13_server.py fit_preproc_lr/apply_preproc_lr 逐位一致：
      stats 在 raw X_train 上估计，apply 时先 winsorize+log1p 再 (x-mu)/sd）
    """
    Xa, Xb = Xtr.copy(), Xte.copy()
    for j, c in enumerate(cols):
        if c in ORD or c in LABS:
            mu, sd = Xa[:, j].mean(), Xa[:, j].std()
            sd = sd if sd > 1e-12 else 1.0
        if c in LABS:
            lo = np.percentile(Xtr[:, j], 1)
            hi = np.percentile(Xtr[:, j], 99)
            Xa[:, j] = np.clip(Xa[:, j], lo, hi)
            Xb[:, j] = np.clip(Xb[:, j], lo, hi)
            if c in LOG1P_COLS:
                Xa[:, j] = np.log1p(np.maximum(Xa[:, j], 0))
                Xb[:, j] = np.log1p(np.maximum(Xb[:, j], 0))
        if c in ORD or c in LABS:
            Xa[:, j] = (Xa[:, j] - mu) / sd
            Xb[:, j] = (Xb[:, j] - mu) / sd
    return Xa, Xb


def nested_subsets(y, sizes, seed=SEED):
    """嵌套分层子集：同一随机置换的前缀，规模之间互为子集。"""
    rng = np.random.default_rng(seed)
    pos = rng.permutation(np.where(y == 1)[0])
    neg = rng.permutation(np.where(y == 0)[0])
    prev = 0
    for n in sizes:
        p = int(round(n * len(pos) / len(y)))
        p = min(max(p, 1), len(pos))
        q = min(max(n - p, 1), len(neg))
        yield n, np.concatenate([pos[:p], neg[:q]])


def metrics(y, p):
    return {"auroc": float(roc_auc_score(y, p)),
            "auprc": float(average_precision_score(y, p)),
            "brier": float(brier_score_loss(y, p))}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=str(Path.home() / "D13_20261107/data.csv"))
    ap.add_argument("--features", required=True, choices=["A", "B", "C"])
    ap.add_argument("--tag", required=True, choices=["full", "dedup"])
    ap.add_argument("--out", required=True)
    ap.add_argument("--no-tabpfn", action="store_true")
    ap.add_argument("--max-tabpfn-n", type=int, default=10000,
                    help="TabPFN 只在 n<=该值的规模上运行（内存/时间护栏）")
    args = ap.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    cols = FEATURE_SETS[args.features]

    df = pd.read_csv(args.data)
    if args.tag == "dedup":
        df = df.drop_duplicates().reset_index(drop=True)
    X = df[cols].to_numpy(dtype=float)
    y = df["second_epilepsy"].to_numpy(dtype=int)
    Xtr_all, Xte, ytr_all, yte = train_test_split(X, y, test_size=0.2, stratify=y,
                                                  random_state=SEED)
    sizes = [s for s in SIZES if s < len(ytr_all)] + [len(ytr_all)]
    print(f"[{args.features}/{args.tag}] rows={len(df)} train={len(ytr_all)} test={len(Xte)} sizes={sizes}")

    from lightgbm import LGBMClassifier
    from tabpfn import TabPFNClassifier

    rows, preds = [], []
    for n, idx in nested_subsets(ytr_all, sizes):
        Xtr, ytr = Xtr_all[idx], ytr_all[idx]
        spw = float((ytr == 0).sum()) / max(1, int((ytr == 1).sum()))

        # ---- LR ----
        t0 = time.time()
        Xa, Xb = lr_transform(Xtr.copy(), Xte.copy(), cols)
        lr = LogisticRegression(C=1.0, max_iter=3000, random_state=SEED)
        lr.fit(Xa, ytr)
        p_lr = lr.predict_proba(Xb)[:, 1]
        rows.append({"feature_set": args.features, "tag": args.tag, "model": "lr",
                     "n_train": n, **metrics(yte, p_lr), "fit_predict_seconds": time.time() - t0})

        # ---- LightGBM ----
        t0 = time.time()
        gb = LGBMClassifier(n_estimators=300, learning_rate=0.05, num_leaves=31,
                            min_child_samples=50, subsample=0.8, colsample_bytree=0.8,
                            reg_alpha=0.1, reg_lambda=0.1, scale_pos_weight=spw,
                            random_state=SEED, n_jobs=8, verbosity=-1)
        gb.fit(Xtr, ytr)
        p_gb = gb.predict_proba(Xte)[:, 1]
        rows.append({"feature_set": args.features, "tag": args.tag, "model": "lgbm",
                     "n_train": n, **metrics(yte, p_gb), "fit_predict_seconds": time.time() - t0})

        # ---- TabPFN ----
        if not args.no_tabpfn and n <= args.max_tabpfn_n:
            t0 = time.time()
            clf = TabPFNClassifier(model_path=str(WEIGHTS), n_estimators="auto",
                                   random_state=SEED, ignore_pretraining_limits=True,
                                   device="cpu")
            clf.fit(Xtr, ytr)
            p_tp = clf.predict_proba(Xte)[:, 1]
            rows.append({"feature_set": args.features, "tag": args.tag, "model": "tabpfn",
                         "n_train": n, **metrics(yte, p_tp),
                         "fit_predict_seconds": time.time() - t0})

        preds.append(pd.DataFrame({"n_train": n, "y": yte, "p_lr": p_lr, "p_lgbm": p_gb,
                                   **({} if args.no_tabpfn else {"p_tabpfn": p_tp})}))
        print(json.dumps(rows[-3:], ensure_ascii=False))

    pd.DataFrame(rows).to_csv(out / "metrics.csv", index=False, encoding="utf-8-sig")
    pd.concat(preds, ignore_index=True).to_csv(out / "test_predictions.csv", index=False,
                                               encoding="utf-8")
    (out / "run_info.json").write_text(json.dumps({
        "feature_set": args.features, "tag": args.tag, "columns": cols,
        "seed": SEED, "sizes": sizes, "test_rows": int(len(yte)),
        "data": args.data, "python": sys.version.split()[0],
        "platform": platform.platform()}, ensure_ascii=False, indent=2), encoding="utf-8")
    print("DONE", out)


if __name__ == "__main__":
    main()
