# -*- coding: utf-8 -*-
"""对照两条代码路径在 B 全训练集上的 LR 结果，定位微小差异来源。"""
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, roc_auc_score
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
FS = {"A": FEATURES_A, "B": FEATURES_A + LABS, "C": FEATURES_A + LABS + POST}
LOG1P_COLS = ["crp", "ast", "alt", "creatinine", "d_dimer", "ck", "ck_mb",
              "ldh", "hbdh", "ima", "anion_gap", "tg", "bua"]
ORD = ["age", "nihss", "range_lobe"]


def lr_transform(Xtr, Xte, cols):
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


df = pd.read_csv("/home/zxyaicenter2/D13_20261107/data.csv")
y = df["second_epilepsy"].to_numpy(int)

# 路径一：verify 风格（C 全列切前 70 列）
Xc = df[FS["C"]].to_numpy(float)
Xtr1, Xte1, ytr1, yte1 = train_test_split(Xc, y, test_size=0.2, stratify=y, random_state=SEED)
Xa1, Xb1 = lr_transform(Xtr1[:, :70].copy(), Xte1[:, :70].copy(), FS["B"])
m1 = LogisticRegression(C=1.0, max_iter=3000).fit(Xa1, ytr1)
p1 = m1.predict_proba(Xb1)[:, 1]
print("path1 auroc", roc_auc_score(yte1, p1), "auprc", average_precision_score(yte1, p1))

# 路径二：lr_rerun 风格（B 列直接取数）
Xb2 = df[FS["B"]].to_numpy(float)
Xtr2, Xte2, ytr2, yte2 = train_test_split(Xb2, y, test_size=0.2, stratify=y, random_state=SEED)
print("split same?", np.array_equal(ytr1, ytr2), np.array_equal(Xtr1[:, :70], Xtr2),
      np.array_equal(Xte1[:, :70], Xte2), len(ytr1), len(ytr2))
Xa3, Xb3 = lr_transform(Xtr2.copy(), Xte2.copy(), FS["B"])
print("transform diff:", np.abs(Xa3 - Xa1).max(), np.abs(Xb3 - Xb1).max())
m2 = LogisticRegression(C=1.0, max_iter=3000, random_state=SEED).fit(Xa3, ytr2)
p2 = m2.predict_proba(Xb3)[:, 1]
print("path2 auroc", roc_auc_score(yte2, p2), "auprc", average_precision_score(yte2, p2))
print("coef diff:", np.abs(m1.coef_ - m2.coef_).max())
print("n_iter:", m1.n_iter_, m2.n_iter_)
