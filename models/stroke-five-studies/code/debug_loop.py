# -*- coding: utf-8 -*-
"""复现 lr_rerun 的嵌套子集循环，打印 full/B 在 n=16000 与 n=17167 的 AUROC，与 metrics.csv 对照。"""
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
SIZES = [100, 250, 500, 1000, 2000, 4000, 8000, 16000]


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


def nested_subsets(y, sizes, seed=SEED):
    rng = np.random.default_rng(seed)
    pos = rng.permutation(np.where(y == 1)[0])
    neg = rng.permutation(np.where(y == 0)[0])
    for n in sizes:
        p = int(round(n * len(pos) / len(y)))
        p = min(max(p, 1), len(pos))
        q = min(max(n - p, 1), len(neg))
        yield n, np.concatenate([pos[:p], neg[:q]])


df = pd.read_csv("/home/zxyaicenter2/D13_20261107/data.csv")
cols = FS["B"]
X = df[cols].to_numpy(float)
y = df["second_epilepsy"].to_numpy(int)
Xtr_all, Xte, ytr_all, yte = train_test_split(X, y, test_size=0.2, stratify=y, random_state=SEED)
sizes = [s for s in SIZES if s < len(ytr_all)] + [len(ytr_all)]
print("len ytr", len(ytr_all), "pos", int(ytr_all.sum()), "sizes", sizes)
for n, idx in nested_subsets(ytr_all, sizes):
    if n not in (16000, len(ytr_all)):
        continue
    idx_sorted = np.sort(idx)
    print(n, "idx len", len(idx_sorted), "identity?", np.array_equal(idx_sorted, np.arange(len(ytr_all))))
    Xtr, ytr = Xtr_all[idx_sorted], ytr_all[idx_sorted]
    Xa, Xb = lr_transform(Xtr, Xte, cols)
    m = LogisticRegression(C=1.0, max_iter=3000, random_state=SEED).fit(Xa, ytr)
    p = m.predict_proba(Xb)[:, 1]
    print("  loop auroc", roc_auc_score(yte, p), "auprc", average_precision_score(yte, p))
