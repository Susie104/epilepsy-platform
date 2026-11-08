# -*- coding: utf-8 -*-
"""补画：去重队列 ROC/PR（n=8,000）与 A/B/C 特征重要性图。"""
import json
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.metrics import precision_recall_curve, roc_curve, roc_auc_score, average_precision_score

BASE = os.path.dirname(os.path.abspath(__file__))
RES = os.path.join(BASE, "results")
OUT = os.path.join(RES, "figs")
os.makedirs(OUT, exist_ok=True)

COL = {"lr": "#4C72B0", "lgbm": "#DD8452", "tabpfn": "#55A868"}
NAME = {"lr": "LR", "lgbm": "LGBM", "tabpfn": "TABPFN"}

SHORT = {
    "age": "Age", "gender": "Sex (value 1)", "nihss": "NIHSS",
    "uremia": "Uremia", "fatty_liver": "Fatty liver", "diabetes": "Diabetes",
    "hypertension": "Hypertension", "coronary_disease": "Coronary disease",
    "atrial_fibrillation": "Atrial fibrillation", "hyperuricemia": "Hyperuricemia",
    "hyperlipidaemia": "Hyperlipidemia", "frontal_lobe": "Frontal lobe",
    "parietal_lobe": "Parietal lobe", "temporal_lobe": "Temporal lobe",
    "occipital_lobe": "Occipital lobe", "insular_lobe": "Insular lobe",
    "range_lobe": "Any lobe", "basal_ganglia": "Basal ganglia",
    "capsula_interna": "Internal capsule", "brainstem": "Brainstem",
    "epencephalon": "Cerebellum", "paraventricular": "Paraventricular",
    "centrum_semiovale": "Centrum semiovale", "thalamus": "Thalamus",
    "subcortex_lobe": "Subcortical", "aca": "ACA territory", "mca": "MCA territory",
    "pca": "PCA territory", "va": "VA territory", "ba": "BA territory",
    "cca_plaque": "Common carotid plaque", "ica_plaque": "Internal carotid plaque",
    "eca_plaque": "External carotid plaque", "ant_circle": "Anterior circulation",
    "post_circle": "Posterior circulation", "large_ves_as": "Large-vessel disease",
    "plt": "Platelet count", "wbc": "WBC count", "rbc": "RBC count", "hba1c": "HbA1c",
    "crp": "CRP", "tg": "Triglycerides", "ldl": "LDL cholesterol", "hdl": "HDL cholesterol",
    "ast": "AST", "alt": "ALT", "bilirubin": "Total bilirubin", "albumin": "Albumin",
    "urea": "Urea", "creatinine": "Creatinine", "bua": "Uric acid",
    "pt": "Prothrombin time", "aptt": "APTT", "tt": "Thrombin time", "inr": "INR",
    "d_dimer": "D-dimer", "fibrinogen": "Fibrinogen", "ck": "Creatine kinase",
    "ck_mb": "CK-MB", "ldh": "LDH", "hbdh": "α-HBDH", "ima": "Ischemia-modified albumin",
    "na": "Sodium", "k": "Potassium", "cl": "Chloride", "ca": "Calcium",
    "p": "Phosphorus", "lactate": "Lactate", "anion_gap": "Anion gap", "tco2": "Total CO2",
    "dvt": "Deep vein thrombosis", "cerebral_hernia": "Cerebral hernia",
    "hydrocephalus": "Hydrocephalus", "hypoproteinemia": "Hypoproteinemia",
}


def roc_pr(fs, cohort):
    """cohort: 'full' or 'dedup'; draws sklearn-exact ROC and PR panels at n = 8,000."""
    d = pd.read_csv(os.path.join(RES, f"preds_{cohort}_{fs}_final.csv"))
    d = d[d.n_train == 8000]
    y = d.y.to_numpy(int)
    fig, ax = plt.subplots(1, 2, figsize=(13, 5.2), dpi=160)
    for m in ["lr", "lgbm", "tabpfn"]:
        p = d["p_" + m].to_numpy(float)
        fpr, tpr, _ = roc_curve(y, p)
        ax[0].plot(fpr, tpr, color=COL[m], lw=2.2,
                   label=f"{NAME[m]} AUROC {roc_auc_score(y, p):.3f}")
        pr, rc, _ = precision_recall_curve(y, p)
        ax[1].plot(rc, pr, color=COL[m], lw=2.2,
                   label=f"{NAME[m]} AUPRC {average_precision_score(y, p):.3f}")
    ax[0].plot([0, 1], [0, 1], "k--", lw=1)
    ax[0].set_xlabel("1 - Specificity", fontsize=12)
    ax[0].set_ylabel("Sensitivity", fontsize=12)
    ax[0].legend(loc="lower right", fontsize=9, frameon=False)
    ax[1].set_xlabel("Recall", fontsize=12)
    ax[1].set_ylabel("Precision", fontsize=12)
    ax[1].legend(loc="lower left", fontsize=9, frameon=False)
    ax[1].set_xlim(-0.02, 1.02)
    ax[1].set_ylim(-0.02, 1.02)
    tag = "full cohort" if cohort == "full" else "deduplicated cohort"
    fig.suptitle(f"Feature set {fs}, n_train = 8,000 ({tag})", fontsize=15)
    for a in ax:
        a.tick_params(labelsize=10)
    fig.tight_layout(rect=[0, 0, 1, 0.95])
    suffix = "" if cohort == "full" else "_dedup"
    p = os.path.join(OUT, f"fig_roc_pr_{fs}{suffix}.png")
    fig.savefig(p, bbox_inches="tight")
    plt.close(fig)
    print("saved", p)


def dedup_roc(fs):
    d = pd.read_csv(os.path.join(RES, f"preds_dedup_{fs}_final.csv"))
    d = d[d.n_train == 8000]
    y = d.y.to_numpy(int)
    fig, ax = plt.subplots(1, 2, figsize=(13, 5.2), dpi=160)
    for m in ["lr", "lgbm", "tabpfn"]:
        p = d["p_" + m].to_numpy(float)
        fpr, tpr, _ = roc_curve(y, p)
        ax[0].plot(fpr, tpr, color=COL[m], lw=2.2,
                   label=f"{NAME[m]} AUROC {roc_auc_score(y, p):.3f}")
        pr, rc, _ = precision_recall_curve(y, p)
        ax[1].plot(rc, pr, color=COL[m], lw=2.2,
                   label=f"{NAME[m]} AUPRC {average_precision_score(y, p):.3f}")
    ax[0].plot([0, 1], [0, 1], "k--", lw=1)
    ax[0].set_xlabel("1 - Specificity", fontsize=12)
    ax[0].set_ylabel("Sensitivity", fontsize=12)
    ax[0].legend(loc="lower right", fontsize=9, frameon=False)
    ax[1].set_xlabel("Recall", fontsize=12)
    ax[1].set_ylabel("Precision", fontsize=12)
    ax[1].legend(loc="upper right", fontsize=9, frameon=False)
    ax[1].set_xlim(-0.02, 1.02)
    fig.suptitle(f"Feature set {fs}, n_train = 8,000 (deduplicated cohort)", fontsize=15)
    for a in ax:
        a.tick_params(labelsize=10)
    fig.tight_layout(rect=[0, 0, 1, 0.95])
    p = os.path.join(OUT, f"fig_roc_pr_{fs}_dedup.png")
    fig.savefig(p, bbox_inches="tight")
    plt.close(fig)
    print("saved", p)


def importance(fs, data):
    lgbm = data["importance"][fs]["lgbm"][:12]
    lr = data["importance"][fs]["lr"][:12]
    fig, ax = plt.subplots(1, 2, figsize=(13.5, 6.4), dpi=160)
    # LGBM
    names = [SHORT.get(x["var"], x["var"]) for x in lgbm][::-1]
    vals = [x["gain_share"] * 100 for x in lgbm][::-1]
    ax[0].barh(names, vals, color=COL["lgbm"])
    ax[0].set_xlabel("Gain share (%)", fontsize=12)
    ax[0].set_title("LightGBM: total gain", fontsize=13)
    ax[0].tick_params(labelsize=9)
    for i, v in enumerate(vals):
        ax[0].text(v + max(vals) * 0.01, i, f"{v:.1f}", va="center", fontsize=8)
    ax[0].set_xlim(0, max(vals) * 1.15)
    # LR
    names = [SHORT.get(x["var"], x["var"]) for x in lr][::-1]
    vals = [x["abs_coef"] for x in lr][::-1]
    ax[1].barh(names, vals, color=COL["lr"])
    ax[1].set_xlabel("|Coefficient|", fontsize=12)
    ax[1].set_title("Logistic regression: absolute coefficient", fontsize=13)
    ax[1].tick_params(labelsize=9)
    for i, v in enumerate(vals):
        ax[1].text(v + max(vals) * 0.01, i, f"{v:.2f}", va="center", fontsize=8)
    ax[1].set_xlim(0, max(vals) * 1.15)
    n = data["importance"][fs]["n_features"]
    fig.suptitle(f"Feature set {fs}: feature importance (full training set, n = 17,167; {n} features)",
                 fontsize=14)
    fig.tight_layout(rect=[0, 0, 1, 0.95])
    p = os.path.join(OUT, f"fig_importance_{fs}.png")
    fig.savefig(p, bbox_inches="tight")
    plt.close(fig)
    print("saved", p)


def main():
    data = json.load(open(os.path.join(RES, "restore", "restore.json"), encoding="utf-8"))
    for fs in ["A", "B", "C"]:
        roc_pr(fs, "full")
        dedup_roc(fs)
        importance(fs, data)


if __name__ == "__main__":
    main()
