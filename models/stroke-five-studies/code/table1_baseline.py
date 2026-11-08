# -*- coding: utf-8 -*-
"""计算 A 论文 Table 1：36 特征按结局分组的基线描述（full 与 dedup）。"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

FEATURES_A = ["age", "gender", "nihss",
              "uremia", "fatty_liver", "diabetes", "hypertension", "coronary_disease",
              "atrial_fibrillation", "hyperuricemia", "hyperlipidaemia",
              "frontal_lobe", "parietal_lobe", "temporal_lobe", "occipital_lobe",
              "insular_lobe", "range_lobe", "basal_ganglia", "capsula_interna",
              "brainstem", "epencephalon", "paraventricular", "centrum_semiovale",
              "thalamus", "subcortex_lobe",
              "aca", "mca", "pca", "va", "ba", "cca_plaque", "ica_plaque", "eca_plaque",
              "ant_circle", "post_circle", "large_ves_as"]

df = pd.read_csv(sys.argv[1])
y = df["second_epilepsy"].to_numpy(int)

def med_iqr(a):
    return [float(np.median(a)), float(np.percentile(a, 25)), float(np.percentile(a, 75))]

out = {}
for tag, d in [("full", df), ("dedup", df.drop_duplicates())]:
    t = {}
    t["n_total"] = int(len(d)); t["n_pos"] = int(d.second_epilepsy.sum())
    t["n_neg"] = int(len(d) - d.second_epilepsy.sum())
    for c in FEATURES_A:
        v0 = d.loc[d.second_epilepsy == 0, c].to_numpy(float)
        v1 = d.loc[d.second_epilepsy == 1, c].to_numpy(float)
        if c in ["age", "nihss", "range_lobe"]:
            t[c] = {"neg_med_iqr": med_iqr(v0), "pos_med_iqr": med_iqr(v1)}
        else:
            t[c] = {"neg_pct": round(float(v0.mean()) * 100, 2),
                    "pos_pct": round(float(v1.mean()) * 100, 2)}
    out[tag] = t

print(json.dumps(out, ensure_ascii=False, indent=1))
