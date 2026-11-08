# -*- coding: utf-8 -*-
"""为 A/B/C 的 n=8,000 与全训练集补算每个模型的 95% bootstrap 置信区间。"""
import json
import os

import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score

BASE = os.path.dirname(os.path.abspath(__file__))
RES = os.path.join(BASE, "results")
OUT = os.path.join(RES, "restore")
os.makedirs(OUT, exist_ok=True)
SEED = 42
B = 2000


def ci(y, p, rng):
    vals = {"auroc": [], "auprc": [], "brier": []}
    n = len(y)
    for _ in range(B):
        idx = rng.integers(0, n, n)
        yy, pp = y[idx], p[idx]
        if yy.min() == yy.max():
            continue
        vals["auroc"].append(roc_auc_score(yy, pp))
        vals["auprc"].append(average_precision_score(yy, pp))
        vals["brier"].append(brier_score_loss(yy, pp))
    out = {}
    for k, v in vals.items():
        out[k] = [float(np.percentile(v, 2.5)), float(np.percentile(v, 97.5))]
    return out


def main():
    rng = np.random.default_rng(SEED)
    out = {}
    for fs in ["A", "B", "C"]:
        for tag in ["full", "dedup"]:
            d = pd.read_csv(os.path.join(RES, f"preds_{tag}_{fs}_final.csv"))
            nmax = int(d.n_train.max())
            for n in [8000, nmax]:
                sub = d[d.n_train == n]
                y = sub.y.to_numpy(int)
                key = f"{fs}_{tag}_{n}"
                out[key] = {}
                for m in ["lr", "lgbm", "tabpfn"]:
                    col = "p_" + m
                    if col not in sub or sub[col].isna().all():
                        continue
                    p = sub[col].to_numpy(float)
                    out[key][m] = {
                        "auroc": float(roc_auc_score(y, p)),
                        "auprc": float(average_precision_score(y, p)),
                        "brier": float(brier_score_loss(y, p)),
                        "ci": ci(y, p, rng),
                    }
            print(fs, tag, "done")
    with open(os.path.join(OUT, "ci.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print("saved", os.path.join(OUT, "ci.json"))


if __name__ == "__main__":
    main()
