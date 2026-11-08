# -*- coding: utf-8 -*-
"""TabPFN 环境冒烟测试：分类器权重 + CPU 推理速度。"""
import inspect
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import train_test_split

from tabpfn import TabPFNClassifier

WEIGHTS = Path.home() / "TABPFN_BENCH_20261107/weights/tabpfn-v2-classifier-finetuned-zk73skhh.ckpt"
DATA = Path.home() / "D13_20261107/data.csv"

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

df = pd.read_csv(DATA)
X = df[FEATURES_A].to_numpy(dtype=float)
y = df["second_epilepsy"].to_numpy(dtype=int)
Xtr, Xte, ytr, yte = train_test_split(X, y, test_size=0.2, stratify=y, random_state=42)
print("full train", Xtr.shape, "test", Xte.shape)

sig = str(inspect.signature(TabPFNClassifier.__init__))
print("HAS ignore_pretraining_limits:", "ignore_pretraining_limits" in sig)
print("HAS device:", "device" in sig)
print("HAS random_state:", "random_state" in sig)

rng = np.random.default_rng(42)
for n in (1000, 4000, 10000):
    idx = rng.choice(len(Xtr), size=min(n, len(Xtr)), replace=False)
    t0 = time.time()
    clf = TabPFNClassifier(model_path=str(WEIGHTS), n_estimators="auto", random_state=42,
                           ignore_pretraining_limits=True, device="cpu")
    clf.fit(Xtr[idx], ytr[idx])
    t1 = time.time()
    p = clf.predict_proba(Xte)[:, 1]
    t2 = time.time()
    print(f"n_train={len(idx)} fit={t1-t0:.1f}s predict={t2-t1:.1f}s "
          f"auroc={roc_auc_score(yte, p):.4f} n_estimators_used={getattr(clf, 'n_estimators_', '?')}")
