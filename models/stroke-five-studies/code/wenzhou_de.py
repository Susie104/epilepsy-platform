# -*- coding: utf-8 -*-
"""温州 167 例真实队列：D（首次发作→晚期非诱发性发作预测）与 E（服药/未服药分析）。

数据：Wenzhou_167_cases_deidentified.csv（167 例，全部为卒中后 7 天内急性症状性发作，
结局 PSE 49 例，随访中位 592 天）。

D 任务（预测）：两套特征集（core 8 变量，EPV≈6；full 25 变量）→ PSE；
  重复分层 5 折 CV（10 次重复），LR / LightGBM / TabPFN 三模型 + 学习曲线 +
  校准 + 决策曲线 + KM 风险分层。
E 任务（治疗）：ASM 服药(134) vs 未服药(33) 与 PSE 的关联；
  未校正 OR、多变量校正 OR、倾向评分 IPTW（交叉拟合）、SMD 平衡、E 值、分层分析。

用法:
  python wenzhou_de.py --data .../Wenzhou_167_cases_deidentified.csv --out out/D --task D
  python wenzhou_de.py --data ... --out out/E --task E
"""
import argparse
import json
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score, roc_curve
from sklearn.model_selection import RepeatedStratifiedKFold, StratifiedKFold, train_test_split

warnings.filterwarnings("ignore")

SEED = 42
WEIGHTS = Path.home() / "TABPFN_BENCH_20261107/weights/tabpfn-v2-classifier-finetuned-zk73skhh.ckpt"

COLS = ["row", "stroke_type", "sex", "age", "age_lt65", "alcohol", "smoking",
        "hypertension", "diabetes", "hyperlipidemia", "hyperuricemia", "seizure_type",
        "interval_days", "interval_gt3", "multiple_seizures", "status_epilepticus",
        "eeg", "asm", "nihss", "nihss_gt14", "infection", "lesion_vol", "lesion_gt10",
        "cortical", "multilobar", "deep", "ventricular_ext", "surgery", "toast",
        "thrombolysis", "lipid_lowering", "antiplatelet", "anticoag", "pse",
        "followup_days", "late_seizure_days", "censor_days"]

D1 = ["age", "sex", "stroke_type", "smoking", "alcohol", "hypertension", "diabetes",
      "hyperlipidemia", "hyperuricemia", "sz_btc", "sz_focal", "interval_days",
      "interval_gt3", "multiple_seizures", "status_epilepticus", "eeg_epileptic",
      "eeg_nonspecific", "eeg_absent", "nihss", "infection", "log_lesion_vol",
      "cortical", "multilobar", "deep"]
# 精简核心集：按 EPV（49 事件 / 8 变量 ≈ 6）预先设定的临床变量
CORE = ["age", "stroke_type", "interval_gt3", "multiple_seizures",
        "status_epilepticus", "nihss", "cortical", "eeg_epileptic"]
FEATURE_SETS = {"core": CORE, "full": D1}
E_COV = ["age", "sex", "stroke_type", "nihss", "status_epilepticus",
         "multiple_seizures", "log_lesion_vol", "cortical", "eeg_epileptic"]


def load(path):
    df = pd.read_csv(path)
    assert df.shape[1] == 37, df.shape
    df.columns = COLS
    df["sz_btc"] = (df.seizure_type == 1).astype(float)
    df["sz_focal"] = (df.seizure_type == 2).astype(float)
    df["eeg_epileptic"] = (df.eeg == 2).astype(float)
    df["eeg_nonspecific"] = (df.eeg == 1).astype(float)
    df["eeg_absent"] = (df.eeg == 3).astype(float)
    df["log_lesion_vol"] = np.log1p(df.lesion_vol)
    # 事件时间：PSE 用首次晚期发作天数，删失用删失天数（缺失时退回随访天数）
    df["time"] = np.where(df.pse == 1, df.late_seizure_days,
                          df.censor_days.fillna(df.followup_days))
    return df


CONT = ["age", "nihss", "interval_days", "log_lesion_vol", "lesion_vol"]


def prep_lr(Xtr, Xte, cols):
    """与 D13 场景口径一致：连续列 winsorize+标准化，二值列保持原值。"""
    Xa, Xb = Xtr.copy(), Xte.copy()
    for j, c in enumerate(cols):
        if c in CONT:
            lo = np.percentile(Xtr[:, j], 1)
            hi = np.percentile(Xtr[:, j], 99)
            Xa[:, j] = np.clip(Xa[:, j], lo, hi)
            Xb[:, j] = np.clip(Xb[:, j], lo, hi)
            mu, sd = Xa[:, j].mean(), Xa[:, j].std()
            sd = sd if sd > 1e-12 else 1.0
            Xa[:, j] = (Xa[:, j] - mu) / sd
            Xb[:, j] = (Xb[:, j] - mu) / sd
    return Xa, Xb


def make_models(seed=SEED, tabpfn=True):
    from lightgbm import LGBMClassifier
    ms = {
        "lr": LogisticRegression(C=1.0, max_iter=5000, random_state=seed),
        # 小样本配置：浅树（3 叶）+ 较少树数，避免在 n~150 上过拟合
        "lgbm": LGBMClassifier(n_estimators=100, learning_rate=0.05, num_leaves=3,
                               min_child_samples=10, random_state=seed,
                               n_jobs=8, verbosity=-1),
    }
    if tabpfn:
        from tabpfn import TabPFNClassifier
        ms["tabpfn"] = TabPFNClassifier(model_path=str(WEIGHTS), n_estimators="auto",
                                        random_state=seed, ignore_pretraining_limits=True,
                                        device="cpu")
    return ms


def fit_predict(name, model, Xtr, ytr, Xte, cols=None):
    if name == "lr":
        a, b = prep_lr(Xtr, Xte, cols)
        model.fit(a, ytr)
        return model.predict_proba(b)[:, 1]
    if name == "lgbm":
        spw = (ytr == 0).sum() / max(1, (ytr == 1).sum())
        model.set_params(scale_pos_weight=float(spw))
    model.fit(Xtr, ytr)
    return model.predict_proba(Xte)[:, 1]


def cv_oof(df, cols, n_splits=5, n_repeats=10, tabpfn=True):
    X = df[cols].to_numpy(float)
    y = df.pse.to_numpy(int)
    rskf = RepeatedStratifiedKFold(n_splits=n_splits, n_repeats=n_repeats, random_state=SEED)
    names = ["lr", "lgbm", "tabpfn"] if tabpfn else ["lr", "lgbm"]
    oof = {m: np.zeros((n_repeats, len(y))) for m in names}
    for i, (tr, te) in enumerate(rskf.split(X, y)):
        rep = i // n_splits
        models = make_models(SEED + i, tabpfn=tabpfn)
        for name, model in models.items():
            oof[name][rep, te] = fit_predict(name, model, X[tr], y[tr], X[te], cols)
    return y, oof


def cv_metrics(y, oof):
    rows = []
    for name, P in oof.items():
        for rep in range(P.shape[0]):
            p = P[rep]
            row = {"model": name, "repeat": rep,
                   "auroc": roc_auc_score(y, p),
                   "auprc": average_precision_score(y, p),
                   "brier": brier_score_loss(y, p)}
            lp = np.log(np.clip(p, 1e-6, 1 - 1e-6) / (1 - np.clip(p, 1e-6, 1 - 1e-6)))
            cs = LogisticRegression(C=1e6, max_iter=1000).fit(lp.reshape(-1, 1), y)
            row["cal_slope"] = float(cs.coef_[0, 0])
            rows.append(row)
    m = pd.DataFrame(rows)
    summ = m.groupby("model").agg(["mean", "std"]).round(4)
    return m, summ


def paired_delta(y, p1, p2, n_boot=2000, seed=SEED):
    """配对 bootstrap：ΔAUROC 的 95% CI（同一批患者）。"""
    rng = np.random.default_rng(seed)
    d = []
    for _ in range(n_boot):
        idx = rng.integers(0, len(y), len(y))
        if y[idx].min() == y[idx].max():
            continue
        d.append(roc_auc_score(y[idx], p1[idx]) - roc_auc_score(y[idx], p2[idx]))
    d = np.array(d)
    return float(np.mean(d)), float(np.percentile(d, 2.5)), float(np.percentile(d, 97.5))


def km(t, e):
    t = np.asarray(t, float)
    e = np.asarray(e, int)
    times, surv = [0.0], [1.0]
    s = 1.0
    for u in np.unique(t[e == 1]):
        at_risk = (t >= u).sum()
        d = ((t == u) & (e == 1)).sum()
        if at_risk > 0:
            s *= 1 - d / at_risk
            times.append(float(u))
            surv.append(float(s))
    return np.array(times), np.array(surv)


def km_at(times, surv, q):
    idx = np.searchsorted(times, q, side="right") - 1
    return float(surv[max(idx, 0)])


def logrank_k(t, e, g):
    """k 组 log-rank 检验，返回 (chi2, p, df)。"""
    t, e, g = np.asarray(t, float), np.asarray(e, int), np.asarray(g)
    groups = np.unique(g)
    if len(groups) < 2:
        return float("nan"), float("nan"), 0
    O = np.zeros(len(groups)); E = np.zeros(len(groups))
    V = np.zeros((len(groups), len(groups)))
    for u in np.unique(t[e == 1]):
        at_risk = t >= u
        n = at_risk.sum()
        if n <= 1:
            continue
        d = ((t == u) & (e == 1)).sum()
        nk = np.array([(at_risk & (g == k)).sum() for k in groups], float)
        dk = np.array([((t == u) & (e == 1) & (g == k)).sum() for k in groups], float)
        O += dk
        E += d * nk / n
        pp = nk / n
        V += d * (n - d) / (n - 1) * (np.diag(pp) - np.outer(pp, pp))
    O_, E_, V_ = O[:-1], E[:-1], V[:-1, :-1]
    chi2 = float((O_ - E_) @ np.linalg.pinv(V_) @ (O_ - E_))
    df = len(groups) - 1
    return chi2, float(stats.chi2.sf(chi2, df)), df


def cox_binary(t, e, g):
    """单变量 Cox（二分类/连续协变量均可），返回 HR。"""
    t, e, g = np.asarray(t, float), np.asarray(e, int), np.asarray(g, float)

    def negll(b):
        b = float(b)
        ll = 0.0
        for u in np.unique(t[e == 1]):
            risk = t >= u
            xb = b * g[risk]
            mx = xb.max()
            ll += b * g[(t == u) & (e == 1)].sum() - (np.log(np.exp(xb - mx).sum()) + mx)
        return -ll

    from scipy.optimize import minimize_scalar
    r = minimize_scalar(negll, bounds=(-4, 4), method="bounded")
    return float(np.exp(r.x))


def rmst(t, e, tau):
    """限制平均生存时间（0..tau 天内 PSE-free 天数），由 KM 曲线积分。"""
    tt, ss = km(t, e)
    area = 0.0
    for i in range(1, len(tt)):
        a, b = tt[i - 1], min(tt[i], tau)
        if b > a:
            area += ss[i - 1] * (b - a)
        if tt[i] >= tau:
            break
    if tt[-1] < tau:
        area += ss[-1] * (tau - tt[-1])
    return float(area)


def e_value(orv):
    """E 值（二分类结局 OR），衡量未测量混杂需多强才能解释掉该关联。"""
    if orv < 1:
        orv = 1 / orv
    return float(orv + np.sqrt(orv * (orv - 1)))


def plot_all(out, D=None, E=None):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    if D:
        y, oof, df = D["y"], D["oof"], D["df"]
        fig, ax = plt.subplots(figsize=(5, 5))
        for name, color in [("lr", "#4C72B0"), ("lgbm", "#DD8452"), ("tabpfn", "#55A868")]:
            if name not in oof:
                continue
            p = oof[name].mean(0)
            fpr, tpr, _ = roc_curve(y, p)
            ax.plot(fpr, tpr, color=color, label=f"{name.upper()} (AUROC {roc_auc_score(y, p):.3f})")
        ax.plot([0, 1], [0, 1], "k--", lw=0.8)
        ax.set_xlabel("1 - Specificity"); ax.set_ylabel("Sensitivity")
        ax.legend(frameon=False, fontsize=8); ax.set_title("ROC (mean of 10 repeats, core model)")
        fig.tight_layout(); fig.savefig(out / "fig_roc.png", dpi=200); plt.close(fig)

        fig, ax = plt.subplots(figsize=(5, 5))
        for name, color in [("lr", "#4C72B0"), ("lgbm", "#DD8452"), ("tabpfn", "#55A868")]:
            if name not in oof:
                continue
            p = oof[name].mean(0)
            bins = np.quantile(p, np.linspace(0, 1, 6))
            idx = np.clip(np.searchsorted(bins, p, side="right") - 1, 0, 4)
            xs, ys = [], []
            for b in range(5):
                m = idx == b
                if m.sum() > 3:
                    xs.append(p[m].mean()); ys.append(y[m].mean())
            ax.plot(xs, ys, "o-", color=color, label=name.upper(), ms=4)
        ax.plot([0, 0.8], [0, 0.8], "k--", lw=0.8)
        ax.set_xlabel("Predicted risk (quintiles)"); ax.set_ylabel("Observed rate")
        ax.legend(frameon=False, fontsize=8); ax.set_title("Calibration (core model)")
        fig.tight_layout(); fig.savefig(out / "fig_calibration.png", dpi=200); plt.close(fig)

        fig, ax = plt.subplots(figsize=(5, 5))
        th = np.arange(0.05, 0.61, 0.01)
        prev = y.mean()
        for name, color in [("lr", "#4C72B0"), ("lgbm", "#DD8452"), ("tabpfn", "#55A868")]:
            if name not in oof:
                continue
            p = oof[name].mean(0)
            nb = [((p >= t) & (y == 1)).sum() / len(y) - ((p >= t) & (y == 0)).sum() / len(y) * t / (1 - t) for t in th]
            ax.plot(th, nb, color=color, label=name.upper())
        ax.plot(th, [prev - (1 - prev) * t / (1 - t) for t in th], "k--", lw=0.8, label="Treat all")
        ax.axhline(0, color="gray", lw=0.6)
        ax.set_ylim(-0.05, max(0.45, prev * 1.1))
        ax.set_xlabel("Threshold"); ax.set_ylabel("Net benefit")
        ax.legend(frameon=False, fontsize=8); ax.set_title("Decision curve (core model)")
        fig.tight_layout(); fig.savefig(out / "fig_dca.png", dpi=200); plt.close(fig)

        lc = D.get("learning_curve")
        if lc is not None and len(lc):
            fig, ax = plt.subplots(figsize=(5.5, 4))
            for name, color in [("lr", "#4C72B0"), ("lgbm", "#DD8452"), ("tabpfn", "#55A868")]:
                sub = lc[lc.model == name]
                if len(sub) == 0:
                    continue
                ax.errorbar(sub.n_train, sub.auroc_mean, yerr=sub.auroc_sd, marker="o",
                            color=color, capsize=3, label=name.upper(), ms=4)
            ax.axhline(0.5, color="gray", lw=0.6, ls=":")
            ax.set_xlabel("Training size (n)"); ax.set_ylabel("AUROC (fixed split)")
            ax.legend(frameon=False, fontsize=8); ax.set_title("Learning curve (core model)")
            fig.tight_layout(); fig.savefig(out / "fig_learning_curve.png", dpi=200); plt.close(fig)

        for nm, fn in [("lr", "fig_km_lr.png"), ("tabpfn", "fig_km_tabpfn.png")]:
            if nm not in oof:
                continue
            p = oof[nm].mean(0)
            q = np.quantile(p, [1 / 3, 2 / 3])
            grp = np.digitize(p, q)
            fig, ax = plt.subplots(figsize=(5.5, 4))
            for gi, lab, color in [(0, "Low risk", "#4C72B0"), (1, "Intermediate", "#DD8452"), (2, "High risk", "#C44E52")]:
                m = grp == gi
                tt, ss = km(df.time[m], df.pse[m])
                ax.step(tt, ss, where="post", color=color, label=f"{lab} (n={m.sum()})")
            ax.set_xlabel("Days since stroke"); ax.set_ylabel("PSE-free probability")
            ax.set_xlim(0, 1500); ax.legend(frameon=False, fontsize=8)
            ax.set_title(f"Kaplan-Meier by {nm.upper()} risk tertile")
            fig.tight_layout(); fig.savefig(out / fn, dpi=200); plt.close(fig)

    if E:
        smd = E["smd"]
        if len(smd):
            fig, ax = plt.subplots(figsize=(5, 4))
            yy = np.arange(len(smd))
            ax.scatter(smd.smd_before, yy, color="#C44E52", label="Before weighting", s=22)
            ax.scatter(smd.smd_after, yy, color="#55A868", label="After IPTW", s=22)
            ax.axvline(0.1, color="gray", ls="--", lw=0.8)
            ax.axvline(-0.1, color="gray", ls="--", lw=0.8)
            ax.set_yticks(yy); ax.set_yticklabels(smd.variable, fontsize=8)
            ax.set_xlabel("Standardized mean difference")
            ax.legend(frameon=False, fontsize=8); ax.set_title("Covariate balance")
            fig.tight_layout(); fig.savefig(out / "fig_love.png", dpi=200); plt.close(fig)
        df = E["df"]
        fig, ax = plt.subplots(figsize=(5.5, 4))
        for g, lab, color in [(0, "No ASM (n=%d)" % (df.asm == 0).sum(), "#C44E52"),
                              (1, "ASM (n=%d)" % (df.asm == 1).sum(), "#4C72B0")]:
            m = df.asm == g
            tt, ss = km(df.time[m], df.pse[m])
            ax.step(tt, ss, where="post", color=color, label=lab)
        ax.set_xlabel("Days since stroke"); ax.set_ylabel("PSE-free probability")
        ax.set_xlim(0, 1500); ax.legend(frameon=False, fontsize=8)
        ax.set_title("Kaplan-Meier by ASM status (unadjusted)")
        fig.tight_layout(); fig.savefig(out / "fig_km_asm.png", dpi=200); plt.close(fig)


def learning_curve(df, cols, tabpfn=True, seeds=(42, 43, 44)):
    X = df[cols].to_numpy(float); yv = df.pse.to_numpy(int)
    rows = []
    sizes = [30, 50, 80, 110, int(round(0.8 * len(yv)))]
    for seed in seeds:
        Xtr, Xte, ytr, yte = train_test_split(X, yv, test_size=0.2, stratify=yv, random_state=seed)
        rng = np.random.default_rng(seed)
        pos = rng.permutation(np.where(ytr == 1)[0]); neg = rng.permutation(np.where(ytr == 0)[0])
        for n in sizes:
            p_n = min(max(int(round(n * len(pos) / len(ytr))), 1), len(pos))
            q_n = min(max(n - p_n, 1), len(neg))
            idx = np.concatenate([pos[:p_n], neg[:q_n]])
            models = make_models(SEED + n + seed, tabpfn=tabpfn)
            for name, model in models.items():
                p = fit_predict(name, model, Xtr[idx], ytr[idx], Xte, cols)
                rows.append({"seed": seed, "n_train": n, "model": name,
                             "auroc": roc_auc_score(yte, p)})
    lc = pd.DataFrame(rows)
    lc_sum = lc.groupby(["model", "n_train"]).auroc.agg(["mean", "std"]).reset_index()
    lc_sum.columns = ["model", "n_train", "auroc_mean", "auroc_sd"]
    return lc, lc_sum


def task_d(df, out, tabpfn=True):
    out.mkdir(parents=True, exist_ok=True)
    res, stores = {}, {}
    for key, cols in FEATURE_SETS.items():
        y, oof = cv_oof(df, cols, tabpfn=tabpfn)
        m, summ = cv_metrics(y, oof)
        m.to_csv(out / f"cv_fold_metrics_{key}.csv", index=False)
        summ.to_csv(out / f"cv_summary_{key}.csv")
        stores[key] = (y, oof, cols)
        res[key] = {"n_features": len(cols), "features": cols,
                    "metrics_mean_std": json.loads(summ.round(4).to_json())}
        lc, lc_sum = learning_curve(df, cols, tabpfn=tabpfn)
        lc.to_csv(out / f"learning_curve_raw_{key}.csv", index=False)
        lc_sum.to_csv(out / f"learning_curve_{key}.csv", index=False)
        res[key]["learning_curve"] = json.loads(lc_sum.round(4).to_json(orient="records"))

    # 主分析 = core（EPV 预先设定）
    y, oof, cols = stores["core"]
    deltas = {}
    if "tabpfn" in oof:
        deltas["tabpfn_minus_lgbm"] = paired_delta(y, oof["tabpfn"][0], oof["lgbm"][0])
        deltas["tabpfn_minus_lr"] = paired_delta(y, oof["tabpfn"][0], oof["lr"][0])
        deltas["lr_minus_lgbm"] = paired_delta(y, oof["lr"][0], oof["lgbm"][0])

    # 增量值：core vs core+ASM
    y2, oof2 = cv_oof(df, CORE + ["asm"], tabpfn=tabpfn)
    inc = {}
    for name in oof2:
        a1 = np.array([roc_auc_score(y2, oof2[name][r]) for r in range(oof2[name].shape[0])])
        b1 = np.array([roc_auc_score(y, oof[name][r]) for r in range(oof[name].shape[0])])
        inc[name] = {"auroc_without_asm": float(b1.mean()), "auroc_with_asm": float(a1.mean()),
                     "delta_mean": float((a1 - b1).mean()), "n_repeats_delta_gt0": int((a1 > b1).sum())}

    # KM 风险三分位 + log-rank（2 组自由度），对 LR 与 TabPFN 各做一次
    kmres = {}
    for strat_model in ["lr", "tabpfn"]:
        if strat_model not in oof:
            continue
        p = oof[strat_model].mean(0)
        q = np.quantile(p, [1 / 3, 2 / 3])
        grp = np.digitize(p, q)
        entry = {}
        for g in [0, 1, 2]:
            tt, ss = km(df.time[grp == g], df.pse[grp == g])
            entry[f"tertile{g}"] = {"n": int((grp == g).sum()),
                                    "events": int(df.pse[grp == g].sum()),
                                    "pse_free_2y": round(km_at(tt, ss, 730), 3)}
        chi2, pval, dfree = logrank_k(df.time, df.pse, grp)
        entry.update({"logrank_chi2": chi2, "logrank_p": pval, "logrank_df": dfree})
        kmres[strat_model] = entry

    th = np.arange(0.05, 0.61, 0.01)
    dca = []
    for name in oof:
        p = oof[name].mean(0)
        for t in th:
            nb = ((p >= t) & (y == 1)).sum() / len(y) - ((p >= t) & (y == 0)).sum() / len(y) * t / (1 - t)
            dca.append({"model": name, "threshold": round(float(t), 2), "net_benefit": float(nb)})
    pd.DataFrame(dca).to_csv(out / "dca.csv", index=False)
    pd.DataFrame({"y": y, **{f"p_{k}": v.mean(0) for k, v in oof.items()}}).to_csv(
        out / "oof_predictions_core.csv", index=False)

    summary = {
        "cohort": {"n": int(len(df)), "events": int(df.pse.sum()),
                   "prevalence": float(df.pse.mean()),
                   "median_followup_days": float(df.followup_days.median()),
                   "median_days_to_pse": float(df.loc[df.pse == 1, "late_seizure_days"].median())},
        "cv": {"folds": 5, "repeats": 10},
        "primary_feature_set": "core",
        "feature_sets": res,
        "paired_bootstrap_delta_auroc_core": deltas,
        "asm_incremental_core": inc,
        "km_risk_tertiles": kmres,
    }
    (out / "summary_D.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    lc_core = pd.read_csv(out / "learning_curve_core.csv")
    plot_all(out, {"y": y, "oof": oof, "df": df, "learning_curve": lc_core})
    return summary


def task_e(df, out, tabpfn=True):
    out.mkdir(parents=True, exist_ok=True)
    y = df.pse.to_numpy(int)
    a = df.asm.to_numpy(int)
    rng = np.random.default_rng(SEED)

    def or_ci(yy, aa, n_boot=3000):
        def orr(y_, a_):
            t = ((a_ == 1) & (y_ == 1)).sum(); tn = ((a_ == 1) & (y_ == 0)).sum()
            c = ((a_ == 0) & (y_ == 1)).sum(); cn = ((a_ == 0) & (y_ == 0)).sum()
            if min(t, tn, c, cn) == 0:
                return np.nan
            return (t * cn) / (tn * c)
        est = orr(yy, aa)
        bs = []
        for _ in range(n_boot):
            i = rng.integers(0, len(yy), len(yy))
            bs.append(orr(yy[i], aa[i]))
        bs = np.array([b for b in bs if np.isfinite(b)])
        return float(est), float(np.percentile(bs, 2.5)), float(np.percentile(bs, 97.5))

    crude = {
        "n_asm": int((a == 1).sum()), "events_asm": int(((a == 1) & (y == 1)).sum()),
        "n_noasm": int((a == 0).sum()), "events_noasm": int(((a == 0) & (y == 1)).sum()),
        "risk_asm": float(y[a == 1].mean()), "risk_noasm": float(y[a == 0].mean()),
    }
    crude["risk_diff"] = crude["risk_asm"] - crude["risk_noasm"]
    crude["or"], crude["or_lo"], crude["or_hi"] = or_ci(y, a)
    crude["e_value"] = e_value(crude["or"])

    # 多变量校正（bootstrap 系数 CI；ASM 保持 0/1 原尺度）
    X = df[E_COV + ["asm"]].to_numpy(float)

    def fit_adj(idx):
        Xa, _ = prep_lr(X[idx][:, :-1], X[idx][:, :-1], E_COV)
        Xall = np.column_stack([Xa, X[idx][:, -1]])
        lr = LogisticRegression(C=1.0, max_iter=5000).fit(Xall, y[idx])
        return lr.coef_[0, -1]

    beta = fit_adj(np.arange(len(y)))
    bs = []
    for _ in range(2000):
        i = rng.integers(0, len(y), len(y))
        if y[i].sum() < 5 or len(np.unique(y[i])) < 2:
            continue
        try:
            bs.append(fit_adj(i))
        except Exception:
            pass
    adj_or = float(np.exp(beta))
    adj = {"or": adj_or,
           "or_lo": float(np.exp(np.percentile(bs, 2.5))),
           "or_hi": float(np.exp(np.percentile(bs, 97.5))),
           "n_boot_ok": len(bs), "e_value": e_value(adj_or),
           "covariates": E_COV}

    # 倾向评分 IPTW（交叉拟合：每折用训练折拟合，避免同数据过拟合）
    psX = df[E_COV].to_numpy(float)
    ps = np.zeros(len(y))
    for tr, te in StratifiedKFold(n_splits=5, shuffle=True, random_state=SEED).split(psX, a):
        Xa, Xb = prep_lr(psX[tr], psX[te], E_COV)
        m = LogisticRegression(C=1.0, max_iter=5000).fit(Xa, a[tr])
        ps[te] = m.predict_proba(Xb)[:, 1]
    ps_auc = float(roc_auc_score(a, ps))
    lo, hi = np.percentile(ps, [1, 99])
    psc = np.clip(ps, lo, hi)
    w = np.where(a == 1, 1 / psc, 1 / (1 - psc))
    w = np.where(a == 1, w * a.mean(), w * (1 - a.mean()))  # 稳定权重
    w = w / w.mean()

    def smd(x, aa, ww=None):
        if ww is None:
            m1, m0 = x[aa == 1].mean(), x[aa == 0].mean()
            v1, v0 = x[aa == 1].var(ddof=1), x[aa == 0].var(ddof=1)
        else:
            m1 = np.average(x[aa == 1], weights=ww[aa == 1])
            m0 = np.average(x[aa == 0], weights=ww[aa == 0])
            v1 = np.average((x[aa == 1] - m1) ** 2, weights=ww[aa == 1])
            v0 = np.average((x[aa == 0] - m0) ** 2, weights=ww[aa == 0])
        sp = np.sqrt((v1 + v0) / 2)
        return float((m1 - m0) / sp) if sp > 0 else 0.0

    smd_rows = [{"variable": c, "smd_before": smd(df[c].to_numpy(float), a),
                 "smd_after": smd(df[c].to_numpy(float), a, w)} for c in E_COV]
    smd = pd.DataFrame(smd_rows)
    smd.to_csv(out / "smd_balance.csv", index=False)

    r1 = np.average(y[a == 1], weights=w[a == 1])
    r0 = np.average(y[a == 0], weights=w[a == 0])
    rd = r1 - r0
    bs_rd = []
    for _ in range(3000):
        i = rng.integers(0, len(y), len(y))
        aa, yy, ww = a[i], y[i], w[i]
        if (aa == 1).sum() < 3 or (aa == 0).sum() < 3:
            continue
        bs_rd.append(np.average(yy[aa == 1], weights=ww[aa == 1])
                     - np.average(yy[aa == 0], weights=ww[aa == 0]))
    iptw = {"risk_asm_weighted": float(r1), "risk_noasm_weighted": float(r0),
            "risk_diff": float(rd), "rd_lo": float(np.percentile(bs_rd, 2.5)),
            "rd_hi": float(np.percentile(bs_rd, 97.5)),
            "ps_auc": ps_auc, "ps_min": float(ps.min()), "ps_max": float(ps.max()),
            "ps_median_asm": float(np.median(ps[a == 1])),
            "ps_median_noasm": float(np.median(ps[a == 0])),
            "max_abs_smd_before": float(smd.smd_before.abs().max()),
            "max_abs_smd_after": float(smd.smd_after.abs().max())}

    # PS 作为协变量校正（比 IPTW 稳定，尤其当 PS 判别力弱时）
    logit_ps = np.log(np.clip(ps, 1e-6, 1 - 1e-6) / (1 - np.clip(ps, 1e-6, 1 - 1e-6)))

    def fit_ps_adj(idx):
        Z = np.column_stack([a[idx], logit_ps[idx]])
        lr = LogisticRegression(C=1.0, max_iter=5000).fit(Z, y[idx])
        return lr.coef_[0, 0]

    b_ps = fit_ps_adj(np.arange(len(y)))
    bs_ps = []
    for _ in range(2000):
        i = rng.integers(0, len(y), len(y))
        if y[i].sum() < 5 or len(np.unique(a[i])) < 2:
            continue
        try:
            bs_ps.append(fit_ps_adj(i))
        except Exception:
            pass
    ps_adj = {"or": float(np.exp(b_ps)),
              "or_lo": float(np.exp(np.percentile(bs_ps, 2.5))),
              "or_hi": float(np.exp(np.percentile(bs_ps, 97.5))),
              "n_boot_ok": len(bs_ps)}

    # AIPW（双重稳健估计）：交叉拟合倾向评分 + 结局模型
    mu1 = np.zeros(len(y)); mu0 = np.zeros(len(y)); ps2 = np.zeros(len(y))
    for tr, te in StratifiedKFold(n_splits=5, shuffle=True, random_state=SEED).split(psX, a):
        Xa, Xb = prep_lr(psX[tr], psX[te], E_COV)
        om = LogisticRegression(C=1.0, max_iter=5000).fit(np.column_stack([Xa, a[tr]]), y[tr])
        mu1[te] = om.predict_proba(np.column_stack([Xb, np.ones(len(te))]))[:, 1]
        mu0[te] = om.predict_proba(np.column_stack([Xb, np.zeros(len(te))]))[:, 1]
        ps2[te] = LogisticRegression(C=1.0, max_iter=5000).fit(Xa, a[tr]).predict_proba(Xb)[:, 1]
    p2 = np.clip(ps2, 0.01, 0.99)
    aipw_i = (a / p2) * (y - mu1) + mu1 - ((1 - a) / (1 - p2)) * (y - mu0) - mu0
    ate = float(aipw_i.mean())
    bs_ate = [float(aipw_i[rng.integers(0, len(y), len(y))].mean()) for _ in range(3000)]
    aipw = {"ate_risk_diff": ate, "rd_lo": float(np.percentile(bs_ate, 2.5)),
            "rd_hi": float(np.percentile(bs_ate, 97.5)),
            "ps_auc": float(roc_auc_score(a, ps2))}

    # 生存分析：log-rank + RMST（比例风险假设不成立，不做单一 Cox HR）
    chi2, pval, dfree = logrank_k(df.time, df.pse, a)
    tt1, ss1 = km(df.time[a == 1], df.pse[a == 1])
    tt0, ss0 = km(df.time[a == 0], df.pse[a == 0])
    rm1, rm0 = rmst(df.time[a == 1], df.pse[a == 1], 730), rmst(df.time[a == 0], df.pse[a == 0], 730)
    bs_rm = []
    for _ in range(2000):
        i = rng.integers(0, len(y), len(y))
        try:
            bs_rm.append(rmst(df.time[i][a[i] == 1], df.pse[i][a[i] == 1], 730)
                         - rmst(df.time[i][a[i] == 0], df.pse[i][a[i] == 0], 730))
        except Exception:
            pass
    # 分期事件数（检验比例风险：早期事件是否集中在治疗组）
    epoch = {}
    for lab, m0_, m1_ in [("0-90d", 0, 90), ("91-365d", 90, 365), (">365d", 365, 10 ** 6)]:
        epoch[lab] = {g: int(((a == g) & (y == 1) & (df.time > m0_) & (df.time <= m1_)).sum())
                      for g in [0, 1]}
    # 90 天 landmark 分析：排除 90 天内事件后重新比较
    lm = df.time > 90
    yy_l, aa_l = y[lm.to_numpy()], a[lm.to_numpy()]
    lm_or = or_ci(yy_l, aa_l, n_boot=1500)
    landmark = {"n_at_risk": int(lm.sum()), "n_asm": int((aa_l == 1).sum()),
                "n_noasm": int((aa_l == 0).sum()),
                "events_asm": int(((aa_l == 1) & (yy_l == 1)).sum()),
                "events_noasm": int(((aa_l == 0) & (yy_l == 1)).sum()),
                "or": lm_or[0], "or_lo": lm_or[1], "or_hi": lm_or[2]}
    surv = {"logrank_chi2": chi2, "logrank_p": pval, "logrank_df": dfree,
            "pse_free_2y_asm": km_at(tt1, ss1, 730),
            "pse_free_2y_noasm": km_at(tt0, ss0, 730),
            "rmst_730_asm": rm1, "rmst_730_noasm": rm0,
            "rmst_diff": rm1 - rm0,
            "rmst_diff_lo": float(np.percentile(bs_rm, 2.5)),
            "rmst_diff_hi": float(np.percentile(bs_rm, 97.5)),
            "events_by_epoch": epoch, "landmark_90d": landmark,
            "ph_note": "比例风险假设不成立（早期事件集中于治疗组），不报告单一 Cox HR"}

    strata = {}
    for st, lab in [(0, "ICH"), (1, "ischemic")]:
        m = (df.stroke_type == st).to_numpy()
        yy, aa = y[m], a[m]
        o, lo_, hi_ = or_ci(yy, aa, n_boot=1500)
        strata[lab] = {"n": int(m.sum()), "n_asm": int((aa == 1).sum()),
                       "n_noasm": int((aa == 0).sum()),
                       "risk_asm": float(yy[aa == 1].mean()),
                       "risk_noasm": float(yy[aa == 0].mean()),
                       "or": o, "or_lo": lo_, "or_hi": hi_}

    ycv, oof = cv_oof(df, CORE, tabpfn=tabpfn)
    ycv2, oof2 = cv_oof(df, CORE + ["asm"], tabpfn=tabpfn)
    inc = {}
    for name in oof:
        a1 = np.array([roc_auc_score(ycv2, oof2[name][r]) for r in range(oof2[name].shape[0])])
        b1 = np.array([roc_auc_score(ycv, oof[name][r]) for r in range(oof[name].shape[0])])
        inc[name] = {"auroc_without_asm": float(b1.mean()), "auroc_with_asm": float(a1.mean()),
                     "delta_mean": float((a1 - b1).mean()),
                     "n_repeats_delta_gt0": int((a1 > b1).sum())}

    summary = {"crude": crude, "adjusted": adj, "ps_adjusted": ps_adj,
               "iptw": iptw, "aipw": aipw,
               "survival": surv, "stroke_type_strata": strata,
               "asm_incremental_prediction": inc, "covariates": E_COV,
               "iptw_note": "PS 判别力弱（c≈0.53），IPTW 估计不稳定，主报告为多变量校正 OR 与 AIPW"}
    (out / "summary_E.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    pd.DataFrame({"asm": a, "pse": y, "time": df.time, "ps": ps, "w": w}).to_csv(
        out / "iptw_patient_level.csv", index=False)
    plot_all(out, None, {"smd": smd, "df": df})
    return summary


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--task", required=True, choices=["D", "E"])
    ap.add_argument("--no-tabpfn", action="store_true")
    args = ap.parse_args()
    out = Path(args.out)
    df = load(args.data)
    print(f"loaded n={len(df)} pse={int(df.pse.sum())} asm={int(df.asm.sum())}", flush=True)
    if args.task == "D":
        s = task_d(df, out, tabpfn=not args.no_tabpfn)
    else:
        s = task_e(df, out, tabpfn=not args.no_tabpfn)
    print(json.dumps(s, ensure_ascii=False, indent=1)[:5000], flush=True)
    print("DONE", out, flush=True)


if __name__ == "__main__":
    main()
