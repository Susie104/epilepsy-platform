# -*- coding: utf-8 -*-
"""只重算 B/C × full/dedup 的 LR 支路（修正后的逐位一致预处理），
拼接到已有 metrics.csv / test_predictions.csv（LGBM/TabPFN 支路不受影响，保持不变）。

验证锚点（场景存档 results_metrics_full.csv, sklearn 1.7.2/1.9.1 均逐位一致）：
  B lr test 0.9647814390954035 / 0.7872176622723596
  C lr test 0.9673034710506947 / 0.7984723092638404
  A lr test 0.8617507018309483 / 0.22712012938632675（A 无化验列，原本已逐位一致）
"""
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
BASE = Path.home() / "TABPFN_BENCH_20261107"
DATA = Path.home() / "D13_20261107/data.csv"


def lr_transform(Xtr, Xte, cols):
    """与场景脚本逐位一致：stats 在 raw 训练值上估计；apply 先 winsorize+log1p 再标准化。"""
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
    rng = np.random.default_rng(seed)
    pos = rng.permutation(np.where(y == 1)[0])
    neg = rng.permutation(np.where(y == 0)[0])
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
    df_raw = pd.read_csv(DATA)
    for tag in ["full", "dedup"]:
        df = df_raw.drop_duplicates().reset_index(drop=True) if tag == "dedup" else df_raw
        for feature in ["B", "C"]:
            cols = FEATURE_SETS[feature]
            X = df[cols].to_numpy(dtype=float)
            y = df["second_epilepsy"].to_numpy(dtype=int)
            Xtr_all, Xte, ytr_all, yte = train_test_split(
                X, y, test_size=0.2, stratify=y, random_state=SEED)
            sizes = [s for s in SIZES if s < len(ytr_all)] + [len(ytr_all)]
            out = BASE / "out" / f"{tag}_{feature}"
            rows, pred_by_n = [], {}
            for n, idx in nested_subsets(ytr_all, sizes):
                idx = np.sort(idx)  # lbfgs 对行序敏感（浮点求和顺序）：排序后全规模点与场景锚点逐位一致
                Xtr, ytr = Xtr_all[idx], ytr_all[idx]
                t0 = time.time()
                Xa, Xb = lr_transform(Xtr, Xte, cols)
                lr = LogisticRegression(C=1.0, max_iter=3000, random_state=SEED)
                lr.fit(Xa, ytr)
                p = lr.predict_proba(Xb)[:, 1]
                rows.append({"feature_set": feature, "tag": tag, "model": "lr",
                             "n_train": n, **metrics(yte, p),
                             "fit_predict_seconds": time.time() - t0})
                pred_by_n[n] = p
                print(f"{tag}/{feature} n={n} auroc={rows[-1]['auroc']:.4f} "
                      f"auprc={rows[-1]['auprc']:.4f}", flush=True)

            # 拼接 metrics.csv
            mp = out / "metrics.csv"
            m = pd.read_csv(mp)
            m = m[m.model != "lr"]
            m = pd.concat([m, pd.DataFrame(rows)], ignore_index=True)
            m.to_csv(mp, index=False, encoding="utf-8-sig")

            # 拼接 test_predictions.csv：逐 n_train 块替换 p_lr
            pp = out / "test_predictions.csv"
            pr = pd.read_csv(pp)
            new_lr = np.empty(len(pr))
            for n, p in pred_by_n.items():
                mask = (pr.n_train == n).to_numpy()
                assert mask.sum() == len(p), f"block size mismatch n={n}"
                new_lr[mask] = p
            pr["p_lr"] = new_lr
            pr.to_csv(pp, index=False, encoding="utf-8")
            print(f"DONE {tag}/{feature}", flush=True)


if __name__ == "__main__":
    main()
