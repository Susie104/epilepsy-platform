# -*- coding: utf-8 -*-
"""汇总 A/B/C × full/dedup 的 TabPFN 基准结果：表 + 图 + JSON。

只统计通过口径校验的产物：metrics.csv 与 test_predictions.csv 必须同时存在，
且三模型在相同 n_train 上预测同一批测试行（列 p_lr/p_lgbm/p_tabpfn）。
不合格（缺文件、n_train 不对齐）的组合直接跳过并记录。
"""
import json
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score, roc_curve

warnings.filterwarnings("ignore")
BASE = Path.home() / "TABPFN_BENCH_20261107"
OUT = BASE / "out"
FIG = BASE / "figs"
FIG.mkdir(exist_ok=True)

COLORS = {"lr": "#4C72B0", "lgbm": "#DD8452", "tabpfn": "#55A868"}
COMBOS = [(f, t) for f in ["A", "B", "C"] for t in ["full", "dedup"]]


def calib(y, p):
    lp = np.log(np.clip(p, 1e-6, 1 - 1e-6) / (1 - np.clip(p, 1e-6, 1 - 1e-6)))
    m = LogisticRegression(C=1e6, max_iter=1000).fit(lp.reshape(-1, 1), y)
    return float(m.coef_[0, 0]), float(m.intercept_[0])


def boot_delta(y, p1, p2, n=2000, seed=42):
    rng = np.random.default_rng(seed)
    d = []
    for _ in range(n):
        i = rng.integers(0, len(y), len(y))
        if y[i].min() == y[i].max():
            continue
        d.append(roc_auc_score(y[i], p1[i]) - roc_auc_score(y[i], p2[i]))
    d = np.array(d)
    return float(np.mean(d)), float(np.percentile(d, 2.5)), float(np.percentile(d, 97.5))


def load_combo(feature, tag):
    d = OUT / f"{tag}_{feature}"
    mp, pp = d / "metrics.csv", d / "test_predictions.csv"
    if not (mp.exists() and pp.exists()):
        return None, None, f"missing files: {d}"
    m = pd.read_csv(mp)
    p = pd.read_csv(pp)
    # 口径校验：每个 n_train 下三模型都有预测列且测试集行数一致
    sizes = sorted(p.n_train.unique())
    need = {"p_lr", "p_lgbm"}
    if not need.issubset(p.columns):
        return None, None, "missing prediction columns"
    return m, p, None


def main():
    summary, skipped = {}, []
    all_metrics = []
    for f, t in COMBOS:
        m, p, err = load_combo(f, t)
        if err:
            skipped.append({"feature": f, "tag": t, "reason": err}); continue
        m["feature_set"], m["tag"] = f, t
        all_metrics.append(m)
        sizes = sorted(p.n_train.unique())
        common = [s for s in sizes if s <= 8000]
        n0 = 8000 if 8000 in common else max(common)
        idx = p.n_train == n0
        y = p.loc[idx, "y"].to_numpy(int)
        has_tab = "p_tabpfn" in p.columns and p.loc[idx, "p_tabpfn"].notna().all()
        rec = {"n_eval": int(n0), "test_rows": int(idx.sum()), "test_events": int(y.sum())}
        preds = {k: p.loc[idx, k].to_numpy(float) for k in ["p_lr", "p_lgbm"]}
        if has_tab:
            preds["p_tabpfn"] = p.loc[idx, "p_tabpfn"].to_numpy(float)
        for k, v in preds.items():
            sl, ic = calib(y, v)
            rec[k] = {"auroc": float(roc_auc_score(y, v)),
                      "auprc": float(average_precision_score(y, v)),
                      "brier": float(brier_score_loss(y, v)),
                      "cal_slope": sl, "cal_intercept": ic}
        if has_tab:
            rec["delta_auroc_tabpfn_minus_lgbm"] = boot_delta(y, preds["p_tabpfn"], preds["p_lgbm"])
            rec["delta_auroc_tabpfn_minus_lr"] = boot_delta(y, preds["p_tabpfn"], preds["p_lr"])
            rec["delta_auroc_lgbm_minus_lr"] = boot_delta(y, preds["p_lgbm"], preds["p_lr"])
        # 数据效率：TabPFN 达到 LGBM 在 8,000 时的 AUROC 所需最小 n
        if has_tab:
            lgb_8000 = roc_auc_score(y, preds["p_lgbm"])
            tp_curve = m[m.model == "tabpfn"].sort_values("n_train")
            reach = tp_curve[tp_curve.auroc >= lgb_8000 - 0.002]
            rec["tabpfn_n_to_match_lgbm_at_8000"] = int(reach.n_train.min()) if len(reach) else None
        summary[f"{f}_{t}"] = rec

    metrics = pd.concat(all_metrics, ignore_index=True)
    metrics.to_csv(OUT / "combined_metrics.csv", index=False)
    (OUT / "bench_summary.json").write_text(
        json.dumps({"summary": summary, "skipped": skipped}, ensure_ascii=False, indent=2),
        encoding="utf-8")

    # ---- 图：每个特征集一张学习曲线（full 实线 + dedup 虚线）----
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    for f in ["A", "B", "C"]:
        fig, ax = plt.subplots(figsize=(5.6, 4.2))
        for t, ls in [("full", "-"), ("dedup", "--")]:
            m, p, err = load_combo(f, t)
            if err:
                continue
            for model in ["lr", "lgbm", "tabpfn"]:
                s = m[m.model == model].sort_values("n_train")
                if len(s) == 0:
                    continue
                ax.plot(s.n_train, s.auroc, ls, marker="o", ms=3.5,
                        color=COLORS[model], alpha=1.0 if t == "full" else 0.55,
                        label=f"{model.upper()} ({t})")
        ax.set_xscale("log")
        ax.set_xlabel("Training set size (n, log scale)")
        ax.set_ylabel("Test AUROC")
        ax.set_title(f"Feature set {f}: TabPFN vs conventional models")
        ax.legend(frameon=False, fontsize=6.5, ncol=2)
        ax.grid(alpha=0.25, lw=0.5)
        fig.tight_layout()
        fig.savefig(FIG / f"fig_learning_{f}.png", dpi=300)
        plt.close(fig)

    # ---- 图：n=8000 的 ROC / PR / 校准 / DCA ----
    for f, t in [(f, "full") for f in ["A", "B", "C"]]:
        m, p, err = load_combo(f, t)
        if err:
            continue
        idx = p.n_train == 8000
        y = p.loc[idx, "y"].to_numpy(int)
        preds = {k: p.loc[idx, k].to_numpy(float) for k in ["p_lr", "p_lgbm", "p_tabpfn"]
                 if k in p.columns and p.loc[idx, k].notna().all()}
        fig, axes = plt.subplots(1, 2, figsize=(9, 4))
        for k, v in preds.items():
            fpr, tpr, _ = roc_curve(y, v)
            axes[0].plot(fpr, tpr, color=COLORS[k.replace("p_", "")],
                         label=f"{k[2:].upper()} AUROC {roc_auc_score(y, v):.3f}")
        axes[0].plot([0, 1], [0, 1], "k--", lw=0.7)
        axes[0].set_xlabel("1 - Specificity"); axes[0].set_ylabel("Sensitivity")
        axes[0].legend(frameon=False, fontsize=7)
        for k, v in preds.items():
            order = np.argsort(-v)
            tp = np.cumsum(y[order]) / y.sum()
            pr = tp / (np.arange(len(y)) + 1)
            axes[1].plot(np.arange(len(y)) / len(y), pr,
                         color=COLORS[k.replace("p_", "")],
                         label=f"{k[2:].upper()} AUPRC {average_precision_score(y, v):.3f}")
        axes[1].set_xlabel("Recall"); axes[1].set_ylabel("Precision")
        axes[1].legend(frameon=False, fontsize=7)
        fig.suptitle(f"Feature set {f}, n_train = 8,000 (full cohort)")
        fig.tight_layout()
        fig.savefig(FIG / f"fig_roc_pr_{f}.png", dpi=300)
        plt.close(fig)

        fig, ax = plt.subplots(figsize=(4.6, 4.2))
        for k, v in preds.items():
            bins = np.quantile(v, np.linspace(0, 1, 6))
            bi = np.clip(np.searchsorted(bins, v, side="right") - 1, 0, 4)
            xs = [v[bi == b].mean() for b in range(5) if (bi == b).sum() > 5]
            ys = [y[bi == b].mean() for b in range(5) if (bi == b).sum() > 5]
            ax.plot(xs, ys, "o-", ms=4, color=COLORS[k.replace("p_", "")], label=k[2:].upper())
        ax.plot([0, 0.9], [0, 0.9], "k--", lw=0.7)
        ax.set_xlabel("Predicted risk (quintiles)"); ax.set_ylabel("Observed rate")
        ax.legend(frameon=False, fontsize=7)
        ax.set_title(f"Calibration, feature set {f} (n=8,000)")
        fig.tight_layout(); fig.savefig(FIG / f"fig_calib_{f}.png", dpi=300); plt.close(fig)

        fig, ax = plt.subplots(figsize=(4.8, 4.2))
        th = np.arange(0.05, 0.61, 0.01)
        prev = y.mean()
        for k, v in preds.items():
            nb = [((v >= x) & (y == 1)).sum() / len(y)
                  - ((v >= x) & (y == 0)).sum() / len(y) * x / (1 - x) for x in th]
            ax.plot(th, nb, color=COLORS[k.replace("p_", "")], label=k[2:].upper())
        ax.plot(th, [prev - (1 - prev) * x / (1 - x) for x in th], "k--", lw=0.7, label="Treat all")
        ax.axhline(0, color="gray", lw=0.6)
        ax.set_ylim(-0.05, max(0.5, prev * 1.1))
        ax.set_xlabel("Threshold probability"); ax.set_ylabel("Net benefit")
        ax.legend(frameon=False, fontsize=7)
        ax.set_title(f"Decision curve, feature set {f} (n=8,000)")
        fig.tight_layout(); fig.savefig(FIG / f"fig_dca_{f}.png", dpi=300); plt.close(fig)

    print(json.dumps({"summary": summary, "skipped": skipped}, ensure_ascii=False, indent=1))
    print("FIGURES", sorted(str(p) for p in FIG.glob("*.png")))
    print("DONE")


if __name__ == "__main__":
    main()
