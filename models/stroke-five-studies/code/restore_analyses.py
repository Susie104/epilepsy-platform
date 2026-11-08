# -*- coding: utf-8 -*-
"""重建 A/B/C 三篇论文中被精简掉的实证内容：
- 表 1：总体 / 无 PSE / PSE / P 值（连续变量 Mann–Whitney，二值卡方）
- 特征重要性：全训练集 LightGBM 增益占比 + logistic 回归 |系数|
- A 论文的五折交叉验证与 OOF 指标
输出 results/restore/restore.json
"""
import json
import os
import warnings

import numpy as np
import pandas as pd
from scipy import stats
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score
from sklearn.model_selection import StratifiedKFold, train_test_split

warnings.filterwarnings("ignore")

BASE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(BASE, "data", "data.csv")
OUT = os.path.join(BASE, "results", "restore")
os.makedirs(OUT, exist_ok=True)
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

LABELS = {
    "age": ("Age, years", "年龄（岁）"),
    "gender": ("Male", "男性"),
    "nihss": ("NIHSS score", "NIHSS 评分"),
    "uremia": ("Uremia", "尿毒症"),
    "fatty_liver": ("Fatty liver", "脂肪肝"),
    "diabetes": ("Diabetes mellitus", "糖尿病"),
    "hypertension": ("Hypertension", "高血压"),
    "coronary_disease": ("Coronary heart disease", "冠心病"),
    "atrial_fibrillation": ("Atrial fibrillation", "心房颤动"),
    "hyperuricemia": ("Hyperuricemia", "高尿酸血症"),
    "hyperlipidaemia": ("Hyperlipidemia", "高脂血症"),
    "frontal_lobe": ("Frontal lobe", "额叶"),
    "parietal_lobe": ("Parietal lobe", "顶叶"),
    "temporal_lobe": ("Temporal lobe", "颞叶"),
    "occipital_lobe": ("Occipital lobe", "枕叶"),
    "insular_lobe": ("Insular lobe", "岛叶"),
    "range_lobe": ("Any lobe involved (>=1)", "脑叶受累（任一，≥1）"),
    "basal_ganglia": ("Basal ganglia", "基底节"),
    "capsula_interna": ("Internal capsule", "内囊"),
    "brainstem": ("Brainstem", "脑干"),
    "epencephalon": ("Cerebellum", "小脑"),
    "paraventricular": ("Paraventricular", "脑室旁"),
    "centrum_semiovale": ("Centrum semiovale", "半卵圆中心"),
    "thalamus": ("Thalamus", "丘脑"),
    "subcortex_lobe": ("Subcortical", "皮层下"),
    "aca": ("ACA territory", "ACA 供血区"),
    "mca": ("MCA territory", "MCA 供血区"),
    "pca": ("PCA territory", "PCA 供血区"),
    "va": ("VA territory", "VA 供血区"),
    "ba": ("BA territory", "BA 供血区"),
    "cca_plaque": ("Common carotid plaque", "颈总动脉斑块"),
    "ica_plaque": ("Internal carotid plaque", "颈内动脉斑块"),
    "eca_plaque": ("External carotid plaque", "颈外动脉斑块"),
    "ant_circle": ("Anterior circulation", "前循环"),
    "post_circle": ("Posterior circulation", "后循环"),
    "large_ves_as": ("Large-vessel atherosclerosis", "大血管动脉粥样硬化"),
    "plt": ("Platelet count (×10⁹/L)", "血小板计数（×10⁹/L）"),
    "wbc": ("White blood cell count (×10⁹/L)", "白细胞计数（×10⁹/L）"),
    "rbc": ("Red blood cell count (×10¹²/L)", "红细胞计数（×10¹²/L）"),
    "hba1c": ("HbA1c (%)", "糖化血红蛋白（%）"),
    "crp": ("C-reactive protein (mg/L)", "C 反应蛋白（mg/L）"),
    "tg": ("Triglycerides (mmol/L)", "甘油三酯（mmol/L）"),
    "ldl": ("LDL cholesterol (mmol/L)", "低密度脂蛋白胆固醇（mmol/L）"),
    "hdl": ("HDL cholesterol (mmol/L)", "高密度脂蛋白胆固醇（mmol/L）"),
    "ast": ("Aspartate aminotransferase (U/L)", "谷草转氨酶（U/L）"),
    "alt": ("Alanine aminotransferase (U/L)", "谷丙转氨酶（U/L）"),
    "bilirubin": ("Total bilirubin (µmol/L)", "总胆红素（µmol/L）"),
    "albumin": ("Albumin (g/L)", "白蛋白（g/L）"),
    "urea": ("Urea (mmol/L)", "尿素（mmol/L）"),
    "creatinine": ("Creatinine (µmol/L)", "肌酐（µmol/L）"),
    "bua": ("Uric acid (µmol/L)", "血尿酸（µmol/L）"),
    "pt": ("Prothrombin time (s)", "凝血酶原时间（s）"),
    "aptt": ("Activated partial thromboplastin time (s)", "活化部分凝血活酶时间（s）"),
    "tt": ("Thrombin time (s)", "凝血酶时间（s）"),
    "inr": ("International normalized ratio", "国际标准化比值"),
    "d_dimer": ("D-dimer (mg/L)", "D-二聚体（mg/L）"),
    "fibrinogen": ("Fibrinogen (g/L)", "纤维蛋白原（g/L）"),
    "ck": ("Creatine kinase (U/L)", "肌酸激酶（U/L）"),
    "ck_mb": ("Creatine kinase-MB (U/L)", "肌酸激酶同工酶 MB（U/L）"),
    "ldh": ("Lactate dehydrogenase (U/L)", "乳酸脱氢酶（U/L）"),
    "hbdh": ("α-Hydroxybutyrate dehydrogenase (U/L)", "α-羟丁酸脱氢酶（U/L）"),
    "ima": ("Ischemia-modified albumin (AU)", "缺血修饰白蛋白（AU）"),
    "na": ("Sodium (mmol/L)", "钠（mmol/L）"),
    "k": ("Potassium (mmol/L)", "钾（mmol/L）"),
    "cl": ("Chloride (mmol/L)", "氯（mmol/L）"),
    "ca": ("Calcium (mmol/L)", "钙（mmol/L）"),
    "p": ("Phosphorus (mmol/L)", "磷（mmol/L）"),
    "lactate": ("Lactate (mmol/L)", "乳酸（mmol/L）"),
    "anion_gap": ("Anion gap (mmol/L)", "阴离子间隙（mmol/L）"),
    "tco2": ("Total CO2 (mmol/L)", "总二氧化碳（mmol/L）"),
    "dvt": ("Deep vein thrombosis", "深静脉血栓"),
    "cerebral_hernia": ("Cerebral hernia", "脑疝"),
    "hydrocephalus": ("Hydrocephalus", "脑积水"),
    "hypoproteinemia": ("Hypoproteinemia", "低蛋白血症"),
}

SECTIONS = {
    "A": [("__SEC__", "Demographics and comorbidities", "人口学与合并症", 0),
          ("__SEC__", "Initial imaging: lesion location", "初始影像：病灶位置", 11),
          ("__SEC__", "Vascular features", "血管特征", 25)],
}


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


def fmt_med(v, one=False):
    if one:
        return f"{v[0]:.1f} ({v[1]:.1f}–{v[2]:.1f})"
    return f"{v[0]:g} ({v[1]:g}–{v[2]:g})"


def pfmt(p):
    return "<0.001" if p < 0.001 else f"{p:.3f}"


def table1(df, cols):
    y = df["second_epilepsy"].to_numpy(int)
    d0, d1 = df[y == 0], df[y == 1]
    rows = []
    for c in cols:
        v = df[c].to_numpy(float)
        v0, v1 = v[y == 0], v[y == 1]
        cont = c in ("age", "nihss", "range_lobe") or c in LABS
        if cont:
            med = lambda a: [float(np.median(a)), float(np.percentile(a, 25)), float(np.percentile(a, 75))]
            p = stats.mannwhitneyu(v0, v1, alternative="two-sided").pvalue
            rows.append({"var": c, "overall": fmt_med(med(v)),
                         "neg": fmt_med(med(v0), one=True), "pos": fmt_med(med(v1), one=True),
                         "p": pfmt(p)})
        else:
            tab = np.array([[int(v0.sum()), int(len(v0) - v0.sum())],
                            [int(v1.sum()), int(len(v1) - v1.sum())]])
            p = stats.chi2_contingency(tab, correction=False)[1]
            rows.append({"var": c, "overall": f"{int(v.sum())} ({v.mean()*100:.1f}%)",
                         "neg": f"{int(v0.sum())} ({v0.mean()*100:.1f}%)",
                         "pos": f"{int(v1.sum())} ({v1.mean()*100:.1f}%)", "p": pfmt(p)})
    return rows


def main():
    df = pd.read_csv(DATA)
    y = df["second_epilepsy"].to_numpy(int)
    Xall = {k: df[v].to_numpy(float) for k, v in FEATURE_SETS.items()}
    Xtr_A, Xte_A, ytr, yte = train_test_split(Xall["A"], y, test_size=0.2, stratify=y, random_state=SEED)

    out = {"table1": {}, "importance": {}, "cv_A": {}, "meta": {}}
    for fs in ["A", "B", "C"]:
        cols = FEATURES_A if fs == "A" else FEATURE_SETS[fs]
        out["table1"][fs] = table1(df, cols)
    # C 表 1 只需四个并发症
    out["table1"]["C"] = [r for r in out["table1"]["C"] if r["var"] in POST]

    # ---------- 全训练集拟合：特征重要性 ----------
    from lightgbm import LGBMClassifier
    for fs in ["A", "B", "C"]:
        cols = FEATURE_SETS[fs]
        X = df[cols].to_numpy(float)
        Xtr, Xte, ytr_, yte_ = train_test_split(X, y, test_size=0.2, stratify=y, random_state=SEED)
        spw = float((ytr_ == 0).sum()) / max(1, int((ytr_ == 1).sum()))
        gb = LGBMClassifier(n_estimators=300, learning_rate=0.05, num_leaves=31,
                            min_child_samples=50, subsample=0.8, colsample_bytree=0.8,
                            reg_alpha=0.1, reg_lambda=0.1, scale_pos_weight=spw,
                            random_state=SEED, n_jobs=8, verbosity=-1)
        gb.fit(Xtr, ytr_)
        gain = gb.booster_.feature_importance(importance_type="gain")
        share = gain / gain.sum() if gain.sum() > 0 else gain
        lr = LogisticRegression(C=1.0, max_iter=3000, random_state=SEED)
        Xa, Xb = lr_transform(Xtr.copy(), Xte.copy(), cols)
        lr.fit(Xa, ytr_)
        coef = np.abs(lr.coef_[0])
        order_g = np.argsort(-gain)
        order_l = np.argsort(-coef)
        ranks_l = {cols[i]: int(np.where(order_l == i)[0][0]) + 1 for i in range(len(cols))}
        ranks_g = {cols[i]: int(np.where(order_g == i)[0][0]) + 1 for i in range(len(cols))}
        out["importance"][fs] = {
            "n_features": len(cols),
            "lgbm": [{"var": cols[i], "gain_share": float(share[i]), "rank": int(r + 1)}
                     for r, i in enumerate(order_g)],
            "lr": [{"var": cols[i], "abs_coef": float(coef[i]), "rank": int(r + 1)}
                   for r, i in enumerate(order_l)],
            "ranks_lgbm": ranks_g, "ranks_lr": ranks_l,
            "test_auroc_lgbm": float(roc_auc_score(yte_, gb.predict_proba(Xte)[:, 1])),
            "test_auroc_lr": float(roc_auc_score(yte_, lr.predict_proba(Xb)[:, 1])),
        }
        print(fs, "top lgbm", [(cols[i], round(float(share[i]) * 100, 2)) for i in order_g[:5]])
        print(fs, "top lr", [(cols[i], round(float(coef[i]), 3)) for i in order_l[:5]])

    # ---------- A 五折 CV + OOF ----------
    X = Xall["A"]
    Xtr, Xte, ytr_, yte_ = train_test_split(X, y, test_size=0.2, stratify=y, random_state=SEED)
    skf = StratifiedKFold(n_splits=5, shuffle=True, random_state=SEED)
    rec = {"lr": [], "lgbm": []}
    oof = {m: np.zeros(len(ytr_)) for m in ("lr", "lgbm")}
    for k, (ti, vi) in enumerate(skf.split(Xtr, ytr_)):
        Xa, Xb = lr_transform(Xtr[ti].copy(), Xtr[vi].copy(), FEATURES_A)
        lr = LogisticRegression(C=1.0, max_iter=3000, random_state=SEED)
        lr.fit(Xa, ytr_[ti])
        p = lr.predict_proba(Xb)[:, 1]
        oof["lr"][vi] = p
        rec["lr"].append([float(roc_auc_score(ytr_[vi], p)), float(average_precision_score(ytr_[vi], p)),
                          float(brier_score_loss(ytr_[vi], p))])
        spw = float((ytr_[ti] == 0).sum()) / max(1, int((ytr_[ti] == 1).sum()))
        gb = LGBMClassifier(n_estimators=300, learning_rate=0.05, num_leaves=31,
                            min_child_samples=50, subsample=0.8, colsample_bytree=0.8,
                            reg_alpha=0.1, reg_lambda=0.1, scale_pos_weight=spw,
                            random_state=SEED, n_jobs=8, verbosity=-1)
        gb.fit(Xtr[ti], ytr_[ti])
        p = gb.predict_proba(Xtr[vi])[:, 1]
        oof["lgbm"][vi] = p
        rec["lgbm"].append([float(roc_auc_score(ytr_[vi], p)), float(average_precision_score(ytr_[vi], p)),
                            float(brier_score_loss(ytr_[vi], p))])
    for m in ("lr", "lgbm"):
        arr = np.array(rec[m])
        out["cv_A"][m] = {
            "auroc_mean": float(arr[:, 0].mean()), "auroc_sd": float(arr[:, 0].std(ddof=1)),
            "auprc_mean": float(arr[:, 1].mean()), "auprc_sd": float(arr[:, 1].std(ddof=1)),
            "brier_mean": float(arr[:, 2].mean()), "brier_sd": float(arr[:, 2].std(ddof=1)),
            "oof_auroc": float(roc_auc_score(ytr_, oof[m])),
            "oof_auprc": float(average_precision_score(ytr_, oof[m])),
            "oof_brier": float(brier_score_loss(ytr_, oof[m])),
        }
    out["meta"] = {"n_total": int(len(df)), "n_pos": int(y.sum()),
                   "n_train": int(len(ytr_)), "n_test": int(len(yte_)),
                   "data_sha_note": "public Dryad v8, used as provided"}
    with open(os.path.join(OUT, "restore.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print("saved", os.path.join(OUT, "restore.json"))


if __name__ == "__main__":
    main()
