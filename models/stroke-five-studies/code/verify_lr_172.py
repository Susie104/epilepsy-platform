# -*- coding: utf-8 -*-
"""用 D13 原 venv（sklearn 1.7.2）重拟合 B/C 的 LR 测试模型，核对场景存档锚点。
预期（results_metrics_full.csv）：
  B lr test_auroc 0.9647814390954035  test_auprc 0.7872176622723596
  C lr test_auroc 0.9673034710506947  test_auprc 0.7984723092638404
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score
from sklearn.model_selection import train_test_split

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
ORD = ["age", "nihss", "range_lobe"]


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


df = pd.read_csv(sys.argv[1])
X = df[FEATURE_SETS["C"]].to_numpy(dtype=float)
y = df["second_epilepsy"].to_numpy(dtype=int)
Xtr_all, Xte, ytr_all, yte = train_test_split(X, y, test_size=0.2, stratify=y,
                                              random_state=SEED)
for f in ["A", "B", "C"]:
    cols = FEATURE_SETS[f]
    Xa, Xb = lr_transform(Xtr_all[:, :len(cols)].copy(), Xte[:, :len(cols)].copy(), cols)
    lr = LogisticRegression(C=1.0, max_iter=3000)
    lr.fit(Xa, ytr_all)
    p = lr.predict_proba(Xb)[:, 1]
    print(f, "auroc", roc_auc_score(yte, p), "auprc", average_precision_score(yte, p),
          "brier", brier_score_loss(yte, p))
