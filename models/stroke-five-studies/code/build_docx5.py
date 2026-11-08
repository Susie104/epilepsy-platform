# -*- coding: utf-8 -*-
"""五篇论文（A-E, EN/CN）+ 配置要求与复现说明 的 docx 生成器。
真实表格：A/B/C 的 Table 1/2 来自 results/ 下的最终指标与 table_numbers.json；
D/E 的 Table 1 来自 table1_wenzhou.json，Table 2 来自 cv_summary_*.csv。
"""
import json
import os
import re

import pandas as pd
from docx import Document
from docx.enum.section import WD_SECTION
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT, WD_CELL_VERTICAL_ALIGNMENT
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt

BASE = os.path.dirname(os.path.abspath(__file__))
PAPERS = os.path.join(BASE, "papers")
RES = os.path.join(BASE, "results")
DOCS = os.path.join(BASE, "docs")
OUT = os.path.join(BASE, "docx")
os.makedirs(OUT, exist_ok=True)

SUMMARY = json.load(open(os.path.join(RES, "bench_summary_final.json"), encoding="utf-8"))["summary"]
TN = json.load(open(os.path.join(RES, "table_numbers.json"), encoding="utf-8"))
T1 = json.load(open(os.path.join(RES, "table1.json"), encoding="utf-8"))
REST = json.load(open(os.path.join(RES, "restore", "restore.json"), encoding="utf-8"))
CI = json.load(open(os.path.join(RES, "restore", "ci.json"), encoding="utf-8"))
TW = json.load(open(os.path.join(RES, "table1_wenzhou.json"), encoding="utf-8"))

CVCOLS = ["model", "repeat_mean", "repeat_sd", "auroc", "auroc_sd",
          "auprc", "auprc_sd", "brier", "brier_sd", "cal_slope", "cal_slope_sd"]
CVC = pd.read_csv(os.path.join(RES, "cv_summary_core.csv"), skiprows=2, names=CVCOLS)
CVF = pd.read_csv(os.path.join(RES, "cv_summary_full.csv"), skiprows=2, names=CVCOLS)


# ---------------------------------------------------------------- 通用排版
def set_font(run, size, lang, bold=False, italic=False, east_font=None):
    run.font.name = "Times New Roman"
    run.font.size = Pt(size)
    run.font.bold = bold
    run.font.italic = italic
    rPr = run._element.get_or_add_rPr()
    rFonts = rPr.find(qn("w:rFonts"))
    if rFonts is None:
        rFonts = OxmlElement("w:rFonts")
        rPr.append(rFonts)
    rFonts.set(qn("w:eastAsia"), east_font or ("宋体" if lang == "cn" else "Times New Roman"))


def add_rich(p, text, size, lang, bold_all=False, italic_all=False, mono=False, east_font=None):
    parts = re.split(r"(\*\*.*?\*\*|`[^`]*`)", text)
    for part in parts:
        if not part:
            continue
        if part.startswith("**") and part.endswith("**") and len(part) > 4:
            r = p.add_run(part[2:-2])
            set_font(r, size, lang, bold=True, italic=italic_all, east_font=east_font)
        elif part.startswith("`") and part.endswith("`") and len(part) > 2:
            r = p.add_run(part[1:-1])
            set_font(r, size, lang, bold=bold_all, italic=italic_all, east_font=east_font)
            r.font.name = "Consolas"
        else:
            r = p.add_run(part)
            set_font(r, size, lang, bold=bold_all, italic=italic_all, east_font=east_font)
            if mono:
                r.font.name = "Consolas"


def add_caption(doc, text, lang, size=9, keep_next=True):
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.keep_with_next = keep_next
    m = re.match(r"^((?:Table|表)\s*\d+\.?)\s*(.*)$", text)
    if m:
        r = p.add_run(m.group(1) + " ")
        set_font(r, size, lang, bold=True)
        r2 = p.add_run(m.group(2))
        set_font(r2, size, lang)
    else:
        add_rich(p, text, size, lang)
    p.paragraph_format.space_after = Pt(3)


def _tr_prop(row, tag):
    trPr = row._tr.get_or_add_trPr()
    el = OxmlElement(tag)
    trPr.append(el)


def add_table(doc, hdr, rows, foot, lang, size=8, widths=None):
    t = doc.add_table(rows=1, cols=len(hdr))
    t.style = "Table Grid"
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    _tr_prop(t.rows[0], "w:tblHeader")
    if widths:
        t.autofit = False
        for j, w in enumerate(widths):
            t.columns[j].width = Cm(w)
            t.rows[0].cells[j].width = Cm(w)
    for j, h in enumerate(hdr):
        c = t.rows[0].cells[j]
        c.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
        c.paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER
        r = c.paragraphs[0].add_run(str(h))
        set_font(r, size, lang, bold=True)
    for row in rows:
        tr = t.add_row()
        _tr_prop(tr, "w:cantSplit")
        cells = tr.cells
        if widths:
            for j, w in enumerate(widths):
                cells[j].width = Cm(w)
        if isinstance(row, tuple) and row and row[0] == "__SECTION__":
            merged = cells[0].merge(cells[-1])
            r = merged.paragraphs[0].add_run(row[1])
            set_font(r, size, lang, bold=True)
            continue
        for j, v in enumerate(row):
            cells[j].vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
            cells[j].paragraphs[0].alignment = (WD_ALIGN_PARAGRAPH.LEFT if j == 0 else WD_ALIGN_PARAGRAPH.CENTER)
            add_rich(cells[j].paragraphs[0], str(v), size, lang)
    if len(rows) <= 20:  # 短表整表不跨页
        for tr in t.rows[:-1]:
            for c in tr.cells:
                for para in c.paragraphs:
                    para.paragraph_format.keep_with_next = True
    if foot:
        p = doc.add_paragraph()
        r = p.add_run(foot)
        set_font(r, 7.5, lang, italic=True)
        p.paragraph_format.space_after = Pt(8)


def new_section(doc, cols):
    s = doc.add_section(WD_SECTION.CONTINUOUS)
    sectPr = s._sectPr
    c = sectPr.find(qn("w:cols"))
    if c is None:
        c = OxmlElement("w:cols")
        sectPr.append(c)
    c.set(qn("w:num"), str(cols))
    c.set(qn("w:space"), "720")
    return s


# ---------------------------------------------------------------- 数字格式
def f4(x):
    return f"{x:.4f}"


def sgn(x, nd=4):
    return f"{x:+.{nd}f}"


def ci(v, nd=4):
    return f"{v[0]:+.{nd}f} ({v[1]:+.{nd}f}, {v[2]:+.{nd}f})"


def med_iqr(v):
    return f"{v[0]:g} ({v[1]:g}–{v[2]:g})"


def pct(v):
    return f"{v:.1f}%"


def get(combo, key):
    return SUMMARY[combo][f"p_{ {'lr':'lr','lgbm':'lgbm','tabpfn':'tabpfn'}[key] }"]


def met(combo, model, field):
    return SUMMARY[combo]["p_" + model][field]


# ---------------------------------------------------------------- A 表 1
A_T1_ROWS = [
    ("age", "Age, years", "年龄（岁）", "med"),
    ("gender", "Sex (value 1)", "性别（取 1 值）", "pct"),
    ("nihss", "NIHSS score", "NIHSS 评分", "med"),
    ("__SEC__", "Comorbidities", "合并症"),
    ("uremia", "Uremia", "尿毒症", "pct"),
    ("fatty_liver", "Fatty liver", "脂肪肝", "pct"),
    ("diabetes", "Diabetes mellitus", "糖尿病", "pct"),
    ("hypertension", "Hypertension", "高血压", "pct"),
    ("coronary_disease", "Coronary heart disease", "冠心病", "pct"),
    ("atrial_fibrillation", "Atrial fibrillation", "心房颤动", "pct"),
    ("hyperuricemia", "Hyperuricemia", "高尿酸血症", "pct"),
    ("hyperlipidaemia", "Hyperlipidemia", "高脂血症", "pct"),
    ("__SEC__", "Initial imaging: lesion location", "初始影像：病灶位置"),
    ("frontal_lobe", "Frontal lobe", "额叶", "pct"),
    ("parietal_lobe", "Parietal lobe", "顶叶", "pct"),
    ("temporal_lobe", "Temporal lobe", "颞叶", "pct"),
    ("occipital_lobe", "Occipital lobe", "枕叶", "pct"),
    ("insular_lobe", "Insular lobe", "岛叶", "pct"),
    ("range_lobe", "Any lobe involved (≥1)", "脑叶受累（任一，≥1）", "pct"),
    ("basal_ganglia", "Basal ganglia", "基底节", "pct"),
    ("capsula_interna", "Internal capsule", "内囊", "pct"),
    ("brainstem", "Brainstem", "脑干", "pct"),
    ("epencephalon", "Cerebellum", "小脑", "pct"),
    ("paraventricular", "Paraventricular", "脑室旁", "pct"),
    ("centrum_semiovale", "Centrum semiovale", "半卵圆中心", "pct"),
    ("thalamus", "Thalamus", "丘脑", "pct"),
    ("subcortex_lobe", "Subcortical", "皮层下", "pct"),
    ("__SEC__", "Vascular features", "血管特征"),
    ("aca", "ACA territory", "ACA 供血区", "pct"),
    ("mca", "MCA territory", "MCA 供血区", "pct"),
    ("pca", "PCA territory", "PCA 供血区", "pct"),
    ("va", "VA territory", "VA 供血区", "pct"),
    ("ba", "BA territory", "BA 供血区", "pct"),
    ("cca_plaque", "Common carotid plaque", "颈总动脉斑块", "pct"),
    ("ica_plaque", "Internal carotid plaque", "颈内动脉斑块", "pct"),
    ("eca_plaque", "External carotid plaque", "颈外动脉斑块", "pct"),
    ("ant_circle", "Anterior circulation", "前循环", "pct"),
    ("post_circle", "Posterior circulation", "后循环", "pct"),
    ("large_ves_as", "Large-vessel atherosclerosis", "大血管动脉粥样硬化", "pct"),
]

LAB_ROWS = [
    ("plt", "Platelet count (×10⁹/L)", "血小板计数（×10⁹/L）"),
    ("wbc", "White blood cell count (×10⁹/L)", "白细胞计数（×10⁹/L）"),
    ("rbc", "Red blood cell count (×10¹²/L)", "红细胞计数（×10¹²/L）"),
    ("hba1c", "HbA1c (%)", "糖化血红蛋白（%）"),
    ("crp", "C-reactive protein (mg/L)", "C 反应蛋白（mg/L）"),
    ("tg", "Triglycerides (mmol/L)", "甘油三酯（mmol/L）"),
    ("ldl", "LDL cholesterol (mmol/L)", "低密度脂蛋白胆固醇（mmol/L）"),
    ("hdl", "HDL cholesterol (mmol/L)", "高密度脂蛋白胆固醇（mmol/L）"),
    ("ast", "Aspartate aminotransferase (U/L)", "谷草转氨酶（U/L）"),
    ("alt", "Alanine aminotransferase (U/L)", "谷丙转氨酶（U/L）"),
    ("bilirubin", "Total bilirubin (µmol/L)", "总胆红素（µmol/L）"),
    ("albumin", "Albumin (g/L)", "白蛋白（g/L）"),
    ("urea", "Urea (mmol/L)", "尿素（mmol/L）"),
    ("creatinine", "Creatinine (µmol/L)", "肌酐（µmol/L）"),
    ("bua", "Uric acid (µmol/L)", "血尿酸（µmol/L）"),
    ("pt", "Prothrombin time (s)", "凝血酶原时间（s）"),
    ("aptt", "Activated partial thromboplastin time (s)", "活化部分凝血活酶时间（s）"),
    ("tt", "Thrombin time (s)", "凝血酶时间（s）"),
    ("inr", "International normalized ratio", "国际标准化比值"),
    ("d_dimer", "D-dimer (mg/L)", "D-二聚体（mg/L）"),
    ("fibrinogen", "Fibrinogen (g/L)", "纤维蛋白原（g/L）"),
    ("ck", "Creatine kinase (U/L)", "肌酸激酶（U/L）"),
    ("ck_mb", "Creatine kinase-MB (U/L)", "肌酸激酶同工酶 MB（U/L）"),
    ("ldh", "Lactate dehydrogenase (U/L)", "乳酸脱氢酶（U/L）"),
    ("hbdh", "α-Hydroxybutyrate dehydrogenase (U/L)", "α-羟丁酸脱氢酶（U/L）"),
    ("ima", "Ischemia-modified albumin (AU)", "缺血修饰白蛋白（AU）"),
    ("na", "Sodium (mmol/L)", "钠（mmol/L）"),
    ("k", "Potassium (mmol/L)", "钾（mmol/L）"),
    ("cl", "Chloride (mmol/L)", "氯（mmol/L）"),
    ("ca", "Calcium (mmol/L)", "钙（mmol/L）"),
    ("p", "Phosphorus (mmol/L)", "磷（mmol/L）"),
    ("lactate", "Lactate (mmol/L)", "乳酸（mmol/L）"),
    ("anion_gap", "Anion gap (mmol/L)", "阴离子间隙（mmol/L）"),
    ("tco2", "Total CO2 (mmol/L)", "总二氧化碳（mmol/L）"),
]

POST_ROWS = [
    ("dvt", "Deep vein thrombosis", "深静脉血栓"),
    ("cerebral_hernia", "Cerebral hernia", "脑疝"),
    ("hydrocephalus", "Hydrocephalus", "脑积水"),
    ("hypoproteinemia", "Hypoproteinemia", "低蛋白血症"),
]

T1P = {fs: {r["var"]: r for r in REST["table1"][fs]} for fs in ("A", "B", "C")}


def t1_header(lang, d):
    if lang == "en":
        return ["Characteristic", f"Overall (n = {d['n_total']:,})",
                f"No PSE (n = {d['n_neg']:,})", f"PSE (n = {d['n_pos']:,})", "P value"]
    return ["特征", f"总体（n = {d['n_total']:,}）",
            f"无 PSE（n = {d['n_neg']:,}）", f"PSE（n = {d['n_pos']:,}）", "P 值"]


def t1_row(lang, key, en, cn):
    r = T1P["A"].get(key) or T1P["B"].get(key) or T1P["C"].get(key)
    return [en if lang == "en" else cn, r["overall"], r["neg"], r["pos"], r["p"]]


def tbl_A1(lang):
    hdr = t1_header(lang, T1["full"])
    rows = []
    for item in A_T1_ROWS:
        if len(item) == 3:
            rows.append(("__SECTION__", item[1] if lang == "en" else item[2]))
            continue
        key, en, cn, _ = item
        rows.append(t1_row(lang, key, en, cn))
    cap = ("Table 1. Baseline characteristics of the 21,459 patients by one-year epilepsy status (full cohort)."
           if lang == "en" else "表 1. 21,459 例患者按一年内癫痫状态的基线特征（全队列）。")
    foot = ("Continuous variables: median (IQR); binary variables: n (%). P values: χ² test for binary variables, "
            "Mann–Whitney U test for continuous variables. PSE, post-stroke epilepsy."
            if lang == "en" else
            "连续变量：中位数（IQR）；二值变量：n（%）。P 值：二值变量用 χ² 检验，连续变量用 Mann–Whitney U 检验。"
            "PSE，卒中后癫痫。")
    return cap, hdr, rows, foot


# ---------------------------------------------------------------- A 表 2
def f4ci(key, model, metric):
    d = CI[key][model]
    lo, hi = d["ci"][metric]
    return f"{d[metric]:.4f} ({lo:.4f}–{hi:.4f})"


def tbl_A2(lang):
    hdr = (["Model", "Training cohort / n", "AUROC (95% CI)", "AUPRC (95% CI)", "Brier (95% CI)", "Calibration slope"]
           if lang == "en" else ["模型", "训练队列 / n", "AUROC（95% CI）", "AUPRC（95% CI）", "Brier（95% CI）", "校准斜率"])
    rows = []
    labels = {"lr": "Logistic regression", "lgbm": "LightGBM", "tabpfn": "TabPFN v2"}
    labels_cn = {"lr": "logistic 回归", "lgbm": "LightGBM", "tabpfn": "TabPFN v2"}
    cohorts = [("A_full", "A_full_8000", "Full", "全队列", "8,000"),
               ("A_dedup", "A_dedup_8000", "Dedup", "去重队列", "8,000"),
               ("A_full", "A_full_17167", "Full", "全队列", "17,167")]
    for m in ["lr", "lgbm", "tabpfn"]:
        for combo, key, coh_en, coh_cn, n in cohorts:
            label = f"{coh_en} / {n}" if lang == "en" else f"{coh_cn} / {n}"
            if n.startswith("17") and m == "tabpfn":
                rows.append([labels[m] if lang == "en" else labels_cn[m], label, "—", "—", "—", "—"])
                continue
            if n.startswith("17"):
                sl = TN[f"slope_full_A_{m}_fullsize"]
                rows.append([labels[m] if lang == "en" else labels_cn[m], label,
                             f4ci(key, m, "auroc"), f4ci(key, m, "auprc"), f4ci(key, m, "brier"),
                             f"{sl:.4f}"])
            else:
                rows.append([labels[m] if lang == "en" else labels_cn[m], label,
                             f4ci(key, m, "auroc"), f4ci(key, m, "auprc"), f4ci(key, m, "brier"),
                             f4(met(combo, m, "cal_slope"))])
    cap = ("Table 2. Test-set discrimination and calibration at n = 8,000 and at the full training set, in the full and deduplicated cohorts."
           if lang == "en" else "表 2. n = 8,000 与全训练集下的测试集判别力与校准（全队列与去重队列）。")
    foot = ("Values are point estimates with 95% bootstrap confidence intervals (2,000 resamples of test rows). "
            "At n = 8,000 (full cohort), ΔAUROC TabPFN − LightGBM = +0.0067 (95% CI −0.0021 to +0.0159); "
            "TabPFN − logistic regression = +0.0892 (+0.0718 to +0.1090). TabPFN was not evaluated above 8,000 "
            "because of its native context limit."
            if lang == "en" else
            "数值为点估计与 95% bootstrap 置信区间（对测试行重抽样 2,000 次）。n = 8,000（全队列）时，"
            "ΔAUROC TabPFN − LightGBM = +0.0067（95% CI −0.0021 至 +0.0159）；TabPFN − logistic 回归 = +0.0892（+0.0718 至 +0.1090）。"
            "受原生上下文上限约束，TabPFN 未在 8,000 以上评估。")
    return cap, hdr, rows, foot


# ---------------------------------------------------------------- A 表 3 / 表 4
def feat_label(var, lang):
    for key, en, cn, *_ in A_T1_ROWS:
        if key == var:
            return en if lang == "en" else cn
    for key, en, cn in LAB_ROWS + POST_ROWS:
        if key == var:
            return en if lang == "en" else cn
    return var


def tbl_A3(lang):
    hdr = (["Rank", "LightGBM feature (gain share)", "Rank", "Logistic regression feature (|coefficient|)"]
           if lang == "en" else ["排名", "LightGBM 特征（增益占比）", "排名", "logistic 回归特征（|系数|）"])
    g = REST["importance"]["A"]["lgbm"][:10]
    l = REST["importance"]["A"]["lr"][:10]
    rows = []
    for i in range(10):
        rows.append([str(i + 1), f"{feat_label(g[i]['var'], lang)} ({g[i]['gain_share']*100:.2f}%)",
                     str(i + 1), f"{feat_label(l[i]['var'], lang)} ({l[i]['abs_coef']:.2f})"])
    cap = ("Table 3. Top ten predictors in the two admission-only models (full training set, n = 17,167)."
           if lang == "en" else "表 3. 仅入院特征两模型的前十预测因子（全训练集，n = 17,167）。")
    foot = ("LightGBM importance is total gain share; logistic-regression importance is the absolute coefficient "
            "on the protocol preprocessing scale."
            if lang == "en" else "LightGBM 为总增益占比；logistic 回归为协议预处理尺度上的系数绝对值。")
    return cap, hdr, rows, foot


def tbl_A4(lang):
    hdr = (["Model", "CV AUROC", "CV AUPRC", "CV Brier", "OOF AUROC", "OOF AUPRC", "OOF Brier"]
           if lang == "en" else ["模型", "CV AUROC", "CV AUPRC", "CV Brier", "OOF AUROC", "OOF AUPRC", "OOF Brier"])
    rows = []
    labels = {"lr": ("Logistic regression", "logistic 回归"), "lgbm": ("LightGBM", "LightGBM")}
    for m in ["lr", "lgbm"]:
        d = REST["cv_A"][m]
        rows.append([labels[m][0] if lang == "en" else labels[m][1],
                     f"{d['auroc_mean']:.4f} ± {d['auroc_sd']:.4f}",
                     f"{d['auprc_mean']:.4f} ± {d['auprc_sd']:.4f}",
                     f"{d['brier_mean']:.4f} ± {d['brier_sd']:.4f}",
                     f"{d['oof_auroc']:.4f}", f"{d['oof_auprc']:.4f}", f"{d['oof_brier']:.4f}"])
    cap = ("Table 4. Five-fold cross-validation and pooled out-of-fold performance on the training set (full cohort)."
           if lang == "en" else "表 4. 训练集五折交叉验证与汇总袋外性能（全队列）。")
    foot = ("CV, five-fold stratified cross-validation (mean ± SD across folds); OOF, pooled out-of-fold predictions. "
            "The hold-out test set is never used here."
            if lang == "en" else "CV，五折分层交叉验证（各折均值 ± 标准差）；OOF，汇总袋外预测。此处不使用留出测试集。")
    return cap, hdr, rows, foot


# ---------------------------------------------------------------- B 表 1-3
def tbl_B1(lang):
    hdr = t1_header(lang, T1["full"])
    rows = [("__SECTION__", "Admission characteristics (36)" if lang == "en" else "入院特征（36 项）")]
    for item in A_T1_ROWS:
        if len(item) == 3:
            rows.append(("__SECTION__", item[1] if lang == "en" else item[2]))
            continue
        key, en, cn, _ = item
        rows.append(t1_row(lang, key, en, cn))
    rows.append(("__SECTION__", "Laboratory tests (34)" if lang == "en" else "实验室检查（34 项）"))
    for key, en, cn in LAB_ROWS:
        r = T1P["B"][key]
        rows.append([en if lang == "en" else cn, r["overall"], r["neg"], r["pos"], r["p"]])
    cap = ("Table 1. Baseline and laboratory characteristics of the 21,459 patients by one-year epilepsy status (full cohort)."
           if lang == "en" else "表 1. 21,459 例患者按一年内癫痫结局分组的基线与实验室特征（全队列）。")
    foot = ("Continuous variables: median (IQR); binary variables: n (%). P values: χ² test for binary variables, "
            "Mann–Whitney U test for continuous variables. PSE, post-stroke epilepsy."
            if lang == "en" else
            "连续变量：中位数（IQR）；二值变量：n（%）。P 值：二值变量用 χ² 检验，连续变量用 Mann–Whitney U 检验。"
            "PSE，卒中后癫痫。")
    return cap, hdr, rows, foot


def tbl_B2(lang):
    hdr = (["Model", "Feature set", "AUROC", "AUPRC", "Brier", "Slope", "ΔAUROC vs 36 (95% CI)"]
           if lang == "en" else ["模型", "特征集", "AUROC", "AUPRC", "Brier", "斜率", "ΔAUROC vs 36（95% CI）"])
    labels = {"lr": ("Logistic regression", "logistic 回归"), "lgbm": ("LightGBM", "LightGBM"), "tabpfn": ("TabPFN v2", "TabPFN v2")}
    rows = []
    for m in ["lr", "lgbm", "tabpfn"]:
        lab = labels[m][0] if lang == "en" else labels[m][1]
        for combo, fs in [("A_full", "36 admission"), ("B_full", "70 admission + lab")]:
            rows.append([lab if fs.startswith("36") else "",
                         fs if lang == "en" else ("36 入院特征" if fs.startswith("36") else "70 入院＋实验室"),
                         f4(met(combo, m, "auroc")), f4(met(combo, m, "auprc")),
                         f4(met(combo, m, "brier")), f4(met(combo, m, "cal_slope")),
                         "—" if fs.startswith("36") else ci(TN[f"delta_AB_full_{m}"])])
    cap = ("Table 2. Incremental value of the 34-feature laboratory block at n = 8,000 (full cohort)."
           if lang == "en" else "表 2. n = 8,000 时 34 项实验室特征的增量价值（全队列）。")
    foot = ("ΔAUROC from 2,000 paired bootstrap replications on identical test patients. The laboratory block added "
            "+0.1072, +0.0544 and +0.0535 AUROC to logistic regression, LightGBM and TabPFN, respectively."
            if lang == "en" else
            "ΔAUROC 为同一批测试患者上的 2,000 次配对 bootstrap。实验室块分别使 logistic 回归、LightGBM 与 TabPFN 的 AUROC "
            "提高 +0.1072、+0.0544 与 +0.0535。")
    return cap, hdr, rows, foot


def tbl_B3(lang):
    hdr = (["Rank", "LightGBM feature (gain share)", "Rank", "Logistic regression feature (|coefficient|)"]
           if lang == "en" else ["排名", "LightGBM 特征（增益占比）", "排名", "logistic 回归特征（|系数|）"])
    g = REST["importance"]["B"]["lgbm"][:15]
    l = REST["importance"]["B"]["lr"][:15]
    rows = []
    for i in range(15):
        rows.append([str(i + 1), f"{feat_label(g[i]['var'], lang)} ({g[i]['gain_share']*100:.2f}%)",
                     str(i + 1), f"{feat_label(l[i]['var'], lang)} ({l[i]['abs_coef']:.2f})"])
    cap = ("Table 3. Top fifteen predictors in the 70-feature models (full training set, n = 17,167)."
           if lang == "en" else "表 3. 70 特征模型的前十五预测因子（全训练集，n = 17,167）。")
    foot = ("LightGBM importance is total gain share; logistic-regression importance is the absolute coefficient "
            "on the protocol preprocessing scale."
            if lang == "en" else "LightGBM 为总增益占比；logistic 回归为协议预处理尺度上的系数绝对值。")
    return cap, hdr, rows, foot


# ---------------------------------------------------------------- C 表 1-3
def tbl_C1(lang):
    hdr = t1_header(lang, T1["full"])
    rows = []
    for key, en, cn in POST_ROWS:
        r = T1P["C"][key]
        rows.append([en if lang == "en" else cn, r["overall"], r["neg"], r["pos"], r["p"]])
    cap = ("Table 1. Prevalence of the four post-stroke complications by one-year epilepsy status (full cohort)."
           if lang == "en" else "表 1. 四项卒中后并发症按一年内癫痫结局分组的患病率（全队列）。")
    foot = ("Values are n (%). P values from the χ² test. PSE, post-stroke epilepsy."
            if lang == "en" else "数值为 n（%）。P 值来自 χ² 检验。PSE，卒中后癫痫。")
    return cap, hdr, rows, foot


def tbl_C2(lang):
    hdr = (["Model", "Feature set", "AUROC", "AUPRC", "Brier", "Slope", "ΔAUROC vs 70 (95% CI)"]
           if lang == "en" else ["模型", "特征集", "AUROC", "AUPRC", "Brier", "斜率", "ΔAUROC vs 70（95% CI）"])
    labels = {"lr": ("Logistic regression", "logistic 回归"), "lgbm": ("LightGBM", "LightGBM"), "tabpfn": ("TabPFN v2", "TabPFN v2")}
    rows = []
    for m in ["lr", "lgbm", "tabpfn"]:
        lab = labels[m][0] if lang == "en" else labels[m][1]
        for combo, fs in [("B_full", "70 admission + lab"), ("C_full", "74 + complications")]:
            rows.append([lab if fs.startswith("70") else "",
                         fs if lang == "en" else ("70 入院＋实验室" if fs.startswith("70") else "74 ＋卒中后并发症"),
                         f4(met(combo, m, "auroc")), f4(met(combo, m, "auprc")),
                         f4(met(combo, m, "brier")), f4(met(combo, m, "cal_slope")),
                         "—" if fs.startswith("70") else ci(TN[f"delta_CB_full_{m}"])])
    cap = ("Table 2. Incremental value of the four-variable post-stroke complication block at n = 8,000 (full cohort)."
           if lang == "en" else "表 2. n = 8,000 时四变量卒中后并发症块的增量价值（全队列）。")
    foot = ("ΔAUROC from 2,000 paired bootstrap replications on identical test patients. Only the logistic-regression "
            "interval excludes zero (+0.0043, 95% CI +0.0008 to +0.0084), a gain 25-fold smaller than the laboratory increment (+0.107)."
            if lang == "en" else
            "ΔAUROC 为同一批测试患者上的 2,000 次配对 bootstrap。仅 logistic 回归的区间排除零（+0.0043，95% CI +0.0008 至 +0.0084），"
            "其增益仅为实验室增量（+0.107）的二十五分之一。")
    return cap, hdr, rows, foot


def tbl_C3(lang):
    hdr = (["Variable", "Prevalence, n (%)", "Univariate P", "LGBM rank (/74)", "LR rank (/74)"]
           if lang == "en" else ["变量", "患病率，n（%）", "单变量 P", "LGBM 排名（/74）", "LR 排名（/74）"])
    rows = []
    for key, en, cn in POST_ROWS:
        r = T1P["C"][key]
        rg = REST["importance"]["C"]["ranks_lgbm"][key]
        rl = REST["importance"]["C"]["ranks_lr"][key]
        rows.append([en if lang == "en" else cn, r["overall"], r["p"], str(rg), str(rl)])
    cap = ("Table 3. Prevalence, univariate association and importance rank of the four complication variables in the 74-feature models."
           if lang == "en" else "表 3. 四项并发症变量的患病率、单变量关联与在 74 特征模型中的重要性排名。")
    foot = ("Ranks are among all 74 features; 1 = most important. Importance is total gain for LightGBM and absolute "
            "coefficient for logistic regression (full training set)."
            if lang == "en" else "排名范围为全部 74 个特征，1 = 最重要。重要性在全训练集上计算：LightGBM 为总增益，"
            "logistic 回归为系数绝对值。")
    return cap, hdr, rows, foot


# ---------------------------------------------------------------- D/E 表 1
WZ_ROWS = [
    ("age_med_iqr", "Age, years", "年龄（岁）", "med"),
    ("sex_male_pct", "Male", "男性", "pct"),
    ("stroke_ischemic_pct", "Ischemic stroke", "缺血性卒中", "pct"),
    ("nihss_med_iqr", "NIHSS score", "NIHSS 评分", "med"),
    ("interval_days_med_iqr", "Days from stroke to first seizure", "卒中至首次发作天数", "med"),
    ("interval_gt3_pct", "First seizure >3 days after stroke", "首次发作在卒中 3 天后", "pct"),
    ("multiple_seizures_pct", "Multiple early seizures", "早期多次发作", "pct"),
    ("status_epilepticus_pct", "Status epilepticus", "癫痫持续状态", "pct"),
    ("cortical_pct", "Cortical involvement", "皮层受累", "pct"),
    ("eeg_epileptic_pct", "Epileptiform EEG", "癫痫样脑电", "pct"),
    ("hypertension_pct", "Hypertension", "高血压", "pct"),
    ("diabetes_pct", "Diabetes mellitus", "糖尿病", "pct"),
    ("hyperlipidemia_pct", "Hyperlipidemia", "高脂血症", "pct"),
    ("hyperuricemia_pct", "Hyperuricemia", "高尿酸血症", "pct"),
    ("smoking_pct", "Smoking", "吸烟", "pct"),
    ("alcohol_pct", "Alcohol use", "饮酒", "pct"),
    ("infection_pct", "Infection", "感染", "pct"),
    ("lesion_vol_med_iqr", "Lesion volume (mL)", "病灶体积（mL）", "med"),
    ("multilobar_pct", "Multilobar involvement", "多脑叶受累", "pct"),
    ("deep_pct", "Deep structure involvement", "深部结构受累", "pct"),
    ("nihss_gt14_pct", "NIHSS >14", "NIHSS >14", "pct"),
    ("thrombolysis_pct", "Thrombolysis", "溶栓", "pct"),
    ("surgery_pct", "Neurosurgery", "神经外科手术", "pct"),
]


def wz_block(d, lang, include_asm=True):
    rows = []
    for key, en, cn, typ in WZ_ROWS:
        v = d[key]
        val = med_iqr(v) if typ == "med" else pct(v)
        rows.append([en if lang == "en" else cn, val])
    if include_asm:
        rows.insert(2, ["ASM (antiseizure medication)" if lang == "en" else "抗癫痫药物（ASM）", pct(d["asm_pct"])])
    rows.append(["Follow-up, days" if lang == "en" else "随访天数", med_iqr(d["followup_days_med_iqr"])])
    return rows


def tbl_D1(lang):
    a, b = TW["by_pse"]["pse_0"], TW["by_pse"]["pse_1"]
    hdr = (["Characteristic", f"No PSE (n = {a['n']})", f"PSE (n = {b['n']})"]
           if lang == "en" else ["特征", f"无 PSE（n = {a['n']}）", f"PSE（n = {b['n']}）"])
    ra, rb = wz_block(a, lang, include_asm=True), wz_block(b, lang, include_asm=True)
    rows = [[ra[i][0], ra[i][1], rb[i][1]] for i in range(len(ra))]
    cap = ("Table 1. Baseline characteristics of the 167 patients by PSE status."
           if lang == "en" else "表 1. 167 例患者按 PSE 状态的基线特征。")
    foot = ("Continuous variables: median (IQR); binary variables: %. ASM, antiseizure medication; EEG, electroencephalogram."
            if lang == "en" else "连续变量：中位数（IQR）；二值变量：百分比（%）。ASM，抗癫痫药物；EEG，脑电图。")
    return cap, hdr, rows, foot


def tbl_E1(lang):
    a, b = TW["by_asm"]["asm_1"], TW["by_asm"]["asm_0"]
    hdr = (["Characteristic", f"ASM (n = {a['n']})", f"No ASM (n = {b['n']})"]
           if lang == "en" else ["特征", f"ASM 组（n = {a['n']}）", f"未用 ASM（n = {b['n']}）"])
    ra, rb = wz_block(a, lang, include_asm=False), wz_block(b, lang, include_asm=False)
    rows = [[ra[i][0], ra[i][1], rb[i][1]] for i in range(len(ra))]
    cap = ("Table 1. Baseline characteristics of the 167 patients by ASM status."
           if lang == "en" else "表 1. 167 例患者按 ASM 状态的基线特征。")
    foot = ("Continuous variables: median (IQR); binary variables: %. ASM, antiseizure medication."
            if lang == "en" else "连续变量：中位数（IQR）；二值变量：百分比（%）。ASM，抗癫痫药物。")
    return cap, hdr, rows, foot


# ---------------------------------------------------------------- D 表 2
def tbl_D2(lang):
    hdr = (["Model", "Feature set", "AUROC", "AUPRC", "Brier", "Calibration slope"]
           if lang == "en" else ["模型", "特征集", "AUROC", "AUPRC", "Brier", "校准斜率"])
    labels = {"lr": ("Logistic regression", "logistic 回归"), "lgbm": ("LightGBM", "LightGBM"), "tabpfn": ("TabPFN v2", "TabPFN v2")}
    order = ["lr", "lgbm", "tabpfn"]
    rows = []
    for m in order:
        for df_, fs in [(CVC, "core (8 variables)"), (CVF, "full (24 variables)")]:
            r = df_[df_["model"] == m].iloc[0]
            rows.append([labels[m][0] if lang == "en" else labels[m][1],
                         fs if lang == "en" else ("核心（8 变量）" if fs.startswith("core") else "全集（24 变量）"),
                         f"{float(r['auroc']):.4f} ± {float(r['auroc_sd']):.4f}",
                         f"{float(r['auprc']):.4f} ± {float(r['auprc_sd']):.4f}",
                         f"{float(r['brier']):.4f} ± {float(r['brier_sd']):.4f}",
                         f"{float(r['cal_slope']):.4f} ± {float(r['cal_slope_sd']):.4f}"])
    cap = ("Table 2. Cross-validated performance (mean ± SD over 50 folds) of the three models on the core and full feature sets."
           if lang == "en" else "表 2. 三模型在核心与全集特征集上的交叉验证表现（50 折均值 ± 标准差）。")
    foot = ("50 folds = 5-fold stratified cross-validation × 10 repeats, seed 42. Paired bootstrap ΔAUROC (core set): "
            "TabPFN − logistic regression = −0.0565 (95% CI −0.1090 to −0.0058); TabPFN − LightGBM = −0.0383 (−0.0943 to +0.0145)."
            if lang == "en" else
            "50 折 = 5 折分层交叉验证 × 10 次重复，种子 42。配对 bootstrap ΔAUROC（核心集）："
            "TabPFN − logistic 回归 = −0.0565（95% CI −0.1090 至 −0.0058）；TabPFN − LightGBM = −0.0383（−0.0943 至 +0.0145）。")
    return cap, hdr, rows, foot


# ---------------------------------------------------------------- 解析 markdown
def parse_md(path):
    blocks = []
    with open(path, encoding="utf-8") as f:
        for raw in f:
            s = raw.rstrip("\n").strip()
            if not s or s == "---":
                continue
            if s.startswith("!["):
                m = re.match(r"^!\[(.*?)\]\((.*?)\)$", s)
                blocks.append(("fig", m.group(1), m.group(2)))
            elif s.startswith("*[") and s.endswith("]*"):
                blocks.append(("tbl", s))
            elif s.startswith("# "):
                blocks.append(("title", s[2:]))
            elif s.startswith("### "):
                blocks.append(("h2", s[4:]))
            elif s.startswith("## "):
                blocks.append(("h1", s[3:]))
            else:
                blocks.append(("p", s))
    return blocks


PAPER_DIRS = {"A": "01_A", "B": "02_B", "C": "03_C", "D": "04_D", "E": "05_E"}
WIDTHS = {
    ("A", 0): [4.2, 3.4, 3.5, 3.4, 1.9],
    ("A", 1): [2.8, 2.7, 3.2, 3.2, 3.2, 1.9],
    ("A", 2): [1.2, 7.6, 1.2, 6.8],
    ("A", 3): [2.5, 2.4, 2.4, 2.4, 2.4, 2.4, 2.4],
    ("B", 0): [4.2, 3.4, 3.5, 3.4, 1.9],
    ("B", 1): [2.8, 3.0, 1.8, 1.8, 1.8, 1.8, 4.0],
    ("B", 2): [1.2, 7.6, 1.2, 6.8],
    ("C", 0): [4.2, 3.4, 3.5, 3.4, 1.9],
    ("C", 1): [2.8, 3.0, 1.8, 1.8, 1.8, 1.8, 4.0],
    ("C", 2): [4.2, 3.4, 2.4, 3.4, 3.4],
    ("D", 0): [6.2, 5.4, 5.4],
    ("D", 1): [3.4, 3.6, 2.5, 2.5, 2.5, 2.5],
    ("E", 0): [6.2, 5.4, 5.4],
}


def build_paper(paper, lang):
    md = os.path.join(PAPERS, PAPER_DIRS[paper], f"paper{paper}_{'en' if lang == 'en' else 'cn'}.md")
    doc_dir = os.path.dirname(md)
    blocks = parse_md(md)
    spec = {"A": [tbl_A1, tbl_A2, tbl_A3, tbl_A4],
            "B": [tbl_B1, tbl_B2, tbl_B3],
            "C": [tbl_C1, tbl_C2, tbl_C3],
            "D": [tbl_D1, tbl_D2], "E": [tbl_E1]}[paper]
    ti = 0

    doc = Document()
    sec = doc.sections[0]
    sec.page_width, sec.page_height = Cm(21), Cm(29.7)
    sec.top_margin = sec.bottom_margin = Cm(2.54)
    sec.left_margin = sec.right_margin = Cm(2.0)

    refs_h1 = "References" if lang == "en" else "参考文献"
    abstract_h1 = "Abstract" if lang == "en" else "摘要"
    head_east = "黑体" if lang == "cn" else None

    assert blocks[0][0] == "title"
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    add_rich(p, blocks[0][1], 16, lang, bold_all=True, east_font=head_east)
    p.paragraph_format.space_after = Pt(6)
    i = 1
    # 作者/通讯行（正文开始前的普通段落）
    while i < len(blocks) and blocks[i][0] == "p" and not blocks[i][1].startswith("**"):
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        add_rich(p, blocks[i][1], 10.5 if i == 1 else 9, lang, italic_all=(i > 1))
        p.paragraph_format.space_after = Pt(2)
        i += 1

    body_started = False
    while i < len(blocks):
        kind, *rest = blocks[i]
        if kind == "h1":
            txt = rest[0]
            p = doc.add_paragraph()
            if txt == refs_h1:
                add_rich(p, txt, 11, lang, bold_all=True, east_font=head_east)
                p.paragraph_format.space_before = Pt(10)
            elif txt == abstract_h1:
                add_rich(p, txt, 11, lang, bold_all=True, east_font=head_east)
            else:
                body_started = True
                add_rich(p, txt, 11, lang, bold_all=True, east_font=head_east)
                p.paragraph_format.space_before = Pt(8)
            p.paragraph_format.space_after = Pt(3)
            p.paragraph_format.keep_with_next = True
            i += 1
            continue
        if kind == "h2":
            p = doc.add_paragraph()
            add_rich(p, rest[0], 10, lang, bold_all=True, italic_all=(lang == "en"), east_font=head_east)
            p.paragraph_format.space_before = Pt(6)
            p.paragraph_format.space_after = Pt(2)
            p.paragraph_format.keep_with_next = True
            i += 1
            continue
        if kind == "p":
            txt = rest[0]
            in_abstract = (not body_started)
            is_kw = txt.startswith("**关键词") or txt.startswith("**Keywords")
            is_ref = bool(re.match(r"^\[\d+\]", txt))
            p = doc.add_paragraph()
            p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
            p.paragraph_format.space_after = Pt(4)
            if in_abstract and not is_kw:
                p.paragraph_format.left_indent = Cm(1)
                p.paragraph_format.right_indent = Cm(1)
                add_rich(p, txt, 9, lang)
            elif is_kw:
                add_rich(p, txt, 9, lang)
            elif is_ref:
                p.paragraph_format.left_indent = Cm(0.75)
                p.paragraph_format.first_line_indent = Cm(-0.75)
                add_rich(p, txt, 8, lang)
            else:
                add_rich(p, txt, 10, lang)
            i += 1
            continue
        if kind == "fig":
            cap, rel = rest
            img = os.path.join(doc_dir, rel)
            p = doc.add_paragraph()
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            p.add_run().add_picture(img, width=Cm(9.5))
            p.paragraph_format.space_after = Pt(2)
            p.paragraph_format.keep_with_next = True
            add_caption(doc, cap, lang, keep_next=False)
            i += 1
            continue
        if kind == "tbl":
            cap, hdr, rows, foot = spec[ti](lang)
            add_caption(doc, cap, lang)
            add_table(doc, hdr, rows, foot, lang, widths=WIDTHS.get((paper, ti)))
            ti += 1
            i += 1
            continue
        i += 1

    out = os.path.join(OUT, f"paper{paper}_{'en' if lang == 'en' else 'cn'}.docx")
    doc.save(out)
    print("saved", out, "| tables:", ti)


# ---------------------------------------------------------------- 复现说明生成
def build_doc():
    md = os.path.join(DOCS, "配置要求与复现说明.md")
    lines = open(md, encoding="utf-8").read().splitlines()
    doc = Document()
    sec = doc.sections[0]
    sec.page_width, sec.page_height = Cm(21), Cm(29.7)
    sec.top_margin = sec.bottom_margin = Cm(2.2)
    sec.left_margin = sec.right_margin = Cm(2.2)

    i = 0
    first_title = True
    while i < len(lines):
        s = lines[i].rstrip()
        st = s.strip()
        if not st or st == "---":
            i += 1
            continue
        if st.startswith("```"):
            # 代码块
            i += 1
            code = []
            while i < len(lines) and not lines[i].strip().startswith("```"):
                code.append(lines[i])
                i += 1
            i += 1
            p = doc.add_paragraph()
            p.paragraph_format.left_indent = Cm(0.4)
            p.paragraph_format.space_after = Pt(6)
            r = p.add_run("\n".join(code))
            r.font.name = "Consolas"
            r.font.size = Pt(8)
            r._element.get_or_add_rPr()
            continue
        if st.startswith("|") and st.endswith("|"):
            # 管道表格
            rows = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                cells = [c.strip() for c in lines[i].strip().strip("|").split("|")]
                if not all(re.fullmatch(r":?-{3,}:?", c) for c in cells):
                    rows.append(cells)
                i += 1
            if rows:
                hdr, data = rows[0], rows[1:]
                w = None
                if len(hdr) == 3 and hdr[-1] == "说明":
                    w = [3.2, 3.2, 10.2]
                elif len(hdr) == 4 and "SHA-256" in hdr[-1]:
                    w = [2.2, 5.8, 2.6, 6.0]
                elif len(hdr) == 3 and hdr[-1] == "95% CI":
                    w = [4.6, 5.0, 7.0]
                elif len(hdr) == 2:
                    w = [4.8, 11.8]
                add_table(doc, hdr, data, None, "cn", size=8, widths=w)
            continue
        if st.startswith("# "):
            p = doc.add_paragraph()
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            add_rich(p, st[2:], 16 if first_title else 13, "cn", bold_all=True, east_font="黑体")
            p.paragraph_format.space_after = Pt(6)
            first_title = False
            i += 1
            continue
        if st.startswith("## "):
            p = doc.add_paragraph()
            add_rich(p, st[3:], 12, "cn", bold_all=True, east_font="黑体")
            p.paragraph_format.space_before = Pt(10)
            p.paragraph_format.space_after = Pt(3)
            i += 1
            continue
        if st.startswith("### "):
            p = doc.add_paragraph()
            add_rich(p, st[4:], 10.5, "cn", bold_all=True, east_font="黑体")
            p.paragraph_format.space_before = Pt(6)
            p.paragraph_format.space_after = Pt(2)
            i += 1
            continue
        if st.startswith("> "):
            p = doc.add_paragraph()
            p.paragraph_format.left_indent = Cm(0.8)
            add_rich(p, st[2:], 9, "cn", italic_all=True)
            p.paragraph_format.space_after = Pt(4)
            i += 1
            continue
        if st.startswith("- [ ] "):
            p = doc.add_paragraph(style="List Bullet")
            add_rich(p, "□ " + st[6:], 10, "cn")
            p.paragraph_format.space_after = Pt(1)
            i += 1
            continue
        if st.startswith("- "):
            p = doc.add_paragraph(style="List Bullet")
            add_rich(p, st[2:], 10, "cn")
            p.paragraph_format.space_after = Pt(1)
            i += 1
            continue
        if re.match(r"^\d+\.\s", st):
            p = doc.add_paragraph(style="List Number")
            add_rich(p, re.sub(r"^\d+\.\s", "", st), 10, "cn")
            p.paragraph_format.space_after = Pt(1)
            i += 1
            continue
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
        add_rich(p, st, 10, "cn")
        p.paragraph_format.space_after = Pt(3)
        i += 1

    out = os.path.join(OUT, "配置要求与复现说明.docx")
    doc.save(out)
    print("saved", out)


if __name__ == "__main__":
    for p_ in ["A", "B", "C", "D", "E"]:
        for l_ in ["en", "cn"]:
            build_paper(p_, l_)
    build_doc()
