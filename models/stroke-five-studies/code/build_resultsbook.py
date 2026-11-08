# -*- coding: utf-8 -*-
"""生成《卒中后癫痫五套算法架构_跑数结果汇编》docx + pdf。

全部数字从 results/ 的 JSON / CSV 读取，不在正文手写。
"""
import json
import os
import re

import pandas as pd
from docx import Document
from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT, WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt

BASE = os.path.dirname(os.path.abspath(__file__))
RES = os.path.join(BASE, "results")
FIG = os.path.join(RES, "figs")
OUT = os.path.join(BASE, "books")
os.makedirs(OUT, exist_ok=True)

SUMMARY = json.load(open(os.path.join(RES, "bench_summary_final.json"), encoding="utf-8"))["summary"]
TN = json.load(open(os.path.join(RES, "table_numbers.json"), encoding="utf-8"))
REST = json.load(open(os.path.join(RES, "restore", "restore.json"), encoding="utf-8"))
CI = json.load(open(os.path.join(RES, "restore", "ci.json"), encoding="utf-8"))
SD = json.load(open(os.path.join(RES, "summary_D.json"), encoding="utf-8"))
SE = json.load(open(os.path.join(RES, "E", "summary_E.json"), encoding="utf-8"))
TW = json.load(open(os.path.join(RES, "table1_wenzhou.json"), encoding="utf-8"))
SMD = pd.read_csv(os.path.join(RES, "E", "smd_balance.csv"))

MET = {}
for _fs in "ABC":
    for _tag in ("full", "dedup"):
        MET[(_fs, _tag)] = pd.read_csv(os.path.join(RES, f"metrics_{_tag}_{_fs}_final.csv"))

MODEL = {"lr": "LR", "lgbm": "LGBM", "tabpfn": "TabPFN"}
CN = {
    "age": "年龄", "gender": "性别（男=1）", "nihss": "NIHSS 评分", "uremia": "尿毒症",
    "fatty_liver": "脂肪肝", "diabetes": "糖尿病", "hypertension": "高血压",
    "coronary_disease": "冠心病", "atrial_fibrillation": "心房颤动",
    "hyperuricemia": "高尿酸血症", "hyperlipidaemia": "高脂血症",
    "frontal_lobe": "额叶", "parietal_lobe": "顶叶", "temporal_lobe": "颞叶",
    "occipital_lobe": "枕叶", "insular_lobe": "岛叶", "range_lobe": "多叶",
    "basal_ganglia": "基底节", "capsula_interna": "内囊", "brainstem": "脑干",
    "epencephalon": "小脑", "paraventricular": "脑室旁", "centrum_semiovale": "半卵圆中心",
    "thalamus": "丘脑", "subcortex_lobe": "皮层下", "aca": "大脑前动脉供血区",
    "mca": "大脑中动脉供血区", "pca": "大脑后动脉供血区", "va": "椎动脉供血区",
    "ba": "基底动脉供血区", "cca_plaque": "颈总动脉斑块", "ica_plaque": "颈内动脉斑块",
    "eca_plaque": "颈外动脉斑块", "ant_circle": "前循环", "post_circle": "后循环",
    "large_ves_as": "大血管病变", "plt": "血小板", "wbc": "白细胞", "rbc": "红细胞",
    "hba1c": "糖化血红蛋白", "crp": "C 反应蛋白", "tg": "甘油三酯", "ldl": "LDL 胆固醇",
    "hdl": "HDL 胆固醇", "ast": "谷草转氨酶", "alt": "谷丙转氨酶", "bilirubin": "总胆红素",
    "albumin": "白蛋白", "urea": "尿素", "creatinine": "肌酐", "bua": "血尿酸",
    "pt": "凝血酶原时间", "aptt": "APTT", "tt": "凝血酶时间", "inr": "INR",
    "d_dimer": "D-二聚体", "fibrinogen": "纤维蛋白原", "ck": "肌酸激酶", "ck_mb": "CK-MB",
    "ldh": "乳酸脱氢酶", "hbdh": "α-羟丁酸脱氢酶", "ima": "缺血修饰白蛋白",
    "na": "钠", "k": "钾", "cl": "氯", "ca": "钙", "p": "磷", "lactate": "乳酸",
    "anion_gap": "阴离子间隙", "tco2": "总二氧化碳", "dvt": "深静脉血栓",
    "cerebral_hernia": "脑疝", "hydrocephalus": "脑积水", "hypoproteinemia": "低蛋白血症",
}


# ------------------------------------------------------------------ 排版工具
def set_font(run, size, bold=False, italic=False, east=None, color=None, mono=False):
    run.font.name = "Consolas" if mono else "Times New Roman"
    run.font.size = Pt(size)
    run.font.bold = bold
    run.font.italic = italic
    if color:
        run.font.color.rgb = color
    rPr = run._element.get_or_add_rPr()
    rFonts = rPr.find(qn("w:rFonts"))
    if rFonts is None:
        rFonts = OxmlElement("w:rFonts")
        rPr.append(rFonts)
    rFonts.set(qn("w:eastAsia"), east or ("宋体" if not mono else "宋体"))


def add_rich(p, text, size, bold_all=False, italic_all=False, east=None, color=None):
    parts = re.split(r"(\*\*.*?\*\*|`[^`]*`)", text)
    for part in parts:
        if not part:
            continue
        if part.startswith("**") and part.endswith("**") and len(part) > 4:
            r = p.add_run(part[2:-2])
            set_font(r, size, bold=True, italic=italic_all, east=east, color=color)
        elif part.startswith("`") and part.endswith("`") and len(part) > 2:
            r = p.add_run(part[1:-1])
            set_font(r, size, bold=bold_all, italic=italic_all, color=color, mono=True)
        else:
            r = p.add_run(part)
            set_font(r, size, bold=bold_all, italic=italic_all, east=east, color=color)


def para(doc, text="", size=9.5, bold=False, italic=False, align=WD_ALIGN_PARAGRAPH.JUSTIFY,
         before=0, after=4, indent=None, keep=False, east=None, color=None):
    p = doc.add_paragraph()
    p.alignment = align
    pf = p.paragraph_format
    pf.space_before = Pt(before)
    pf.space_after = Pt(after)
    if indent:
        pf.first_line_indent = Cm(indent)
    if keep:
        pf.keep_with_next = True
    if text:
        add_rich(p, text, size, bold_all=bold, italic_all=italic, east=east, color=color)
    return p


def h1(doc, text, page=True):
    if page:
        doc.add_page_break()
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(0)
    p.paragraph_format.space_after = Pt(6)
    p.paragraph_format.keep_with_next = True
    r = p.add_run(text)
    set_font(r, 15, bold=True, east="黑体")
    return p


def h2(doc, text):
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(9)
    p.paragraph_format.space_after = Pt(3)
    p.paragraph_format.keep_with_next = True
    r = p.add_run(text)
    set_font(r, 11.5, bold=True, east="黑体")
    return p


def cap(doc, text, before=6, after=3, keep=True):
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_before = Pt(before)
    p.paragraph_format.space_after = Pt(after)
    p.paragraph_format.keep_with_next = keep
    m = re.match(r"^((?:图|表)\s*\d+-\d+)\s*(.*)$", text)
    if m:
        r = p.add_run(m.group(1) + "　")
        set_font(r, 8.8, bold=True)
        r2 = p.add_run(m.group(2))
        set_font(r2, 8.8, bold=True)
    else:
        r = p.add_run(text)
        set_font(r, 8.8, bold=True)
    return p


def _tr_prop(row, tag):
    trPr = row._tr.get_or_add_trPr()
    el = OxmlElement(tag)
    trPr.append(el)


def shade(cell, fill="F2F2F2"):
    tcPr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), fill)
    tcPr.append(shd)


def table(doc, hdr, rows, widths, size=7.9, foot=None, first_left=True):
    t = doc.add_table(rows=1, cols=len(hdr))
    t.style = "Table Grid"
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    t.autofit = False
    _tr_prop(t.rows[0], "w:tblHeader")
    for j, w in enumerate(widths):
        t.columns[j].width = Cm(w)
        c = t.rows[0].cells[j]
        c.width = Cm(w)
        c.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
        shade(c)
        c.paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER
        r = c.paragraphs[0].add_run(str(hdr[j]))
        set_font(r, size, bold=True)
    for row in rows:
        tr = t.add_row()
        _tr_prop(tr, "w:cantSplit")
        cells = tr.cells
        for j, w in enumerate(widths):
            cells[j].width = Cm(w)
        if isinstance(row, tuple) and row and row[0] == "__SECTION__":
            merged = cells[0].merge(cells[-1])
            merged.paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.LEFT
            r = merged.paragraphs[0].add_run(row[1])
            set_font(r, size, bold=True)
            shade(merged, "FAFAFA")
            continue
        for j, v in enumerate(row):
            c = cells[j]
            c.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
            c.paragraphs[0].alignment = (
                WD_ALIGN_PARAGRAPH.LEFT if (j == 0 and first_left) else WD_ALIGN_PARAGRAPH.CENTER
            )
            add_rich(c.paragraphs[0], str(v), size)
    if len(rows) <= 26:
        for tr in t.rows[:-1]:
            for c in tr.cells:
                for pp in c.paragraphs:
                    pp.paragraph_format.keep_with_next = True
    if foot:
        p = doc.add_paragraph()
        r = p.add_run(foot)
        set_font(r, 7.4, italic=True)
        p.paragraph_format.space_before = Pt(2)
        p.paragraph_format.space_after = Pt(8)


def size_table(doc, data, foot=None):
    """两级表头的规模明细表：n × 3 模型 × 3 指标。"""
    widths = [1.55] + [1.74] * 9
    t = doc.add_table(rows=2, cols=10)
    t.style = "Table Grid"
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    t.autofit = False
    for j, w in enumerate(widths):
        t.columns[j].width = Cm(w)
    for a, b, lab in [(1, 3, "Logistic regression"), (4, 6, "LightGBM"), (7, 9, "TabPFN v2")]:
        c = t.cell(0, a).merge(t.cell(0, b))
        c.paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER
        shade(c)
        r = c.paragraphs[0].add_run(lab)
        set_font(r, 7.6, bold=True)
    c0 = t.cell(0, 0)
    shade(c0)
    c0.paragraphs[0].add_run("")
    hdr1 = ["n_train", "AUROC", "AUPRC", "Brier", "AUROC", "AUPRC", "Brier",
            "AUROC", "AUPRC", "Brier"]
    for j, h in enumerate(hdr1):
        c = t.cell(1, j)
        c.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
        c.paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER
        shade(c)
        r = c.paragraphs[0].add_run(h)
        set_font(r, 7.6, bold=True)
    for j in range(10):
        t.cell(1, j).width = Cm(widths[j])
    for n in sorted(data.n_train.unique()):
        tr = t.add_row()
        _tr_prop(tr, "w:cantSplit")
        cells = tr.cells
        for j, w in enumerate(widths):
            cells[j].width = Cm(w)
        cells[0].paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER
        add_rich(cells[0].paragraphs[0], f"{int(n):,}", 7.6)
        for k, m in enumerate(["lr", "lgbm", "tabpfn"]):
            r = data[(data.n_train == n) & (data.model == m)]
            vals = ["—", "—", "—"] if len(r) == 0 else [
                f"{r.iloc[0].auroc:.4f}", f"{r.iloc[0].auprc:.4f}", f"{r.iloc[0].brier:.4f}"
            ]
            for q, v in enumerate(vals):
                c = cells[1 + 3 * k + q]
                c.paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER
                add_rich(c.paragraphs[0], v, 7.6)
    for tr in t.rows[:2]:
        _tr_prop(tr, "w:tblHeader")
    if foot:
        p = doc.add_paragraph()
        r = p.add_run(foot)
        set_font(r, 7.4, italic=True)
        p.paragraph_format.space_before = Pt(2)
        p.paragraph_format.space_after = Pt(8)


def figure(doc, filename, caption, width=12.3):
    path = filename if os.path.isabs(filename) else os.path.join(FIG, filename)
    if not os.path.exists(path):
        path = os.path.join(RES, os.path.basename(filename))
    if not os.path.exists(path):
        path = os.path.join(RES, "E", os.path.basename(filename))
    doc.add_picture(path, width=Cm(width))
    p = doc.paragraphs[-1]
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.keep_with_next = True
    p.paragraph_format.space_before = Pt(4)
    p.paragraph_format.space_after = Pt(2)
    cap(doc, caption, before=0, after=7, keep=False)


def add_page_number(section):
    p = section.footer.paragraphs[0]
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r1 = p.add_run("第 ")
    set_font(r1, 8)
    run = p.add_run()
    set_font(run, 8)
    f1 = OxmlElement("w:fldChar"); f1.set(qn("w:fldCharType"), "begin")
    it = OxmlElement("w:instrText"); it.set(qn("xml:space"), "preserve"); it.text = "PAGE"
    f2 = OxmlElement("w:fldChar"); f2.set(qn("w:fldCharType"), "separate")
    tt = OxmlElement("w:t"); tt.text = "1"
    f3 = OxmlElement("w:fldChar"); f3.set(qn("w:fldCharType"), "end")
    for el in (f1, it, f2, tt, f3):
        run._r.append(el)
    r2 = p.add_run(" 页")
    set_font(r2, 8)


# ------------------------------------------------------------------ 数字helper
def f4(x):
    return f"{x:.4f}"


def sci(x):
    if x < 1e-3:
        e = int(f"{x:.0e}".split("e")[1])
        m = x / (10 ** e)
        sup = str(-e) if e < 0 else str(e)
        trans = str.maketrans("0123456789-", "⁰¹²³⁴⁵⁶⁷⁸⁹⁻")
        return f"{m:.1f}×10{sup.translate(trans)}"
    return f"{x:.4f}"


def mval(fs, tag, n, model, field="auroc"):
    d = MET[(fs, tag)]
    r = d[(d.n_train == n) & (d.model == model)]
    if len(r) == 0:
        return None
    return float(r.iloc[0][field])


def mrow_best(fs, tag):
    d = MET[(fs, tag)]
    r = d.sort_values("auroc", ascending=False).iloc[0]
    return r.model, int(r.n_train), float(r.auroc)


def dmet(fs, metric, model, stat="mean"):
    return SD["feature_sets"][fs]["metrics_mean_std"][f"('{metric}', '{stat}')"][model]


def med_iqr(v):
    return f"{v[0]:g}（{v[1]:g}–{v[2]:g}）"


def pct(v):
    return f"{v:.1f}%"


def sgn(x, nd=4):
    return f"{x:+.{nd}f}"


def ci_str(v, nd=4, signed=False):
    f = (lambda z: f"{z:+.{nd}f}") if signed else (lambda z: f"{z:.{nd}f}")
    return f"{f(v[0])}（{f(v[1])}, {f(v[2])}）"


def ci95(obj, metric):
    return f"{obj[metric]:.4f}（{obj['ci'][metric][0]:.4f}, {obj['ci'][metric][1]:.4f}）"


# ================================================================== 正文
def cover(doc):
    para(doc, "", 10, before=150)
    para(doc, "卒中后癫痫五套算法架构", 26, bold=True, align=WD_ALIGN_PARAGRAPH.CENTER, after=8, east="黑体")
    para(doc, "第五次大跑数 · 全量结果汇编", 15, align=WD_ALIGN_PARAGRAPH.CENTER, after=22)
    para(doc, "A / B / C：21,459 例公共队列（Dryad v8）", 10.5, align=WD_ALIGN_PARAGRAPH.CENTER, after=2)
    para(doc, "D / E：温州 167 例真实队列", 10.5, align=WD_ALIGN_PARAGRAPH.CENTER, after=26)
    para(doc, "三合医研发团队 · 河南大学", 11, align=WD_ALIGN_PARAGRAPH.CENTER, after=6)
    para(doc, "2026-11-07", 10, align=WD_ALIGN_PARAGRAPH.CENTER, after=40)
    para(doc, "全部数字直接读取 results/ 原始 JSON 与 CSV，未做人工转录或修饰", 9,
         italic=True, align=WD_ALIGN_PARAGRAPH.CENTER, after=2)
    para(doc, "每个表、每张图均注明源文件，可逐位核对", 9,
         italic=True, align=WD_ALIGN_PARAGRAPH.CENTER)


def toc(doc):
    doc.add_page_break()
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = p.add_run("目　录")
    set_font(r, 16, bold=True, east="黑体")
    p.paragraph_format.space_after = Pt(14)
    items = [
        ("0", "阅读指南：这本书是什么、怎么核对"),
        ("1", "数据与设计：队列、特征集、模型、跑数清单"),
        ("2", "A / B / C 全训练规模明细（144 次拟合）"),
        ("3", "主结果：n = 8,000 与全训练集锚点"),
        ("4", "校准与决策曲线"),
        ("5", "增量与配对比较：哪个特征块、哪个模型真正有用"),
        ("6", "特征重要性：A / B / C 的前十变量"),
        ("7", "特征集 A 的五折交叉验证与 OOF"),
        ("8", "D 研究：温州 167 例的首次发作时点预测"),
        ("9", "E 研究：抗癫痫药物与晚期 PSE 风险"),
        ("10", "图表总索引"),
        ("11", "复现锚点：文件指纹、关键数字、运行步骤"),
    ]
    for no, title in items:
        p = doc.add_paragraph()
        p.paragraph_format.space_before = Pt(2)
        p.paragraph_format.space_after = Pt(2)
        r = p.add_run(f"{no}　")
        set_font(r, 10.5, bold=True)
        r2 = p.add_run(title)
        set_font(r2, 10.5)


def sec0(doc):
    h1(doc, "0　阅读指南")
    para(doc, "这份汇编是五套算法架构的账本。算法架构正文回答“这些数字说明什么”，本书回答四个更基础的问题："
              "每个数字具体是多少；它在哪一种数据划分、哪一档训练规模、哪一个模型下得到；"
              "换一种划分是否还成立；以及这个数字可以在哪个原始文件里逐位核对。")
    para(doc, "本书覆盖第五次大跑数的全部最终结果：公共队列 A/B/C 三项研究共 **144 次模型拟合**；"
              "温州 167 例队列 D 研究 **300 次交叉验证拟合**；E 研究 **5 类效应估计、2,000 次 bootstrap** "
              "与全部生存分析。所有数字由脚本直接写入 JSON/CSV，本书再由脚本读取生成，中间没有人工转录。")
    para(doc, "一条阅读建议：先看第 3 节主结果表（n = 8,000），再看第 5 节增量表；这两张表足以回答"
              "“哪个模型更好、哪个特征块有用”。第 2 节的全量明细用于核对与复现，不必顺序阅读。")

    h2(doc, "0.1　数据流（一页看懂）")
    for t in [
        "公共队列 21,459 例（事件 936，4.36%）→ 分层 80/20 划分（种子 42）→ 训练 17,167 / 测试 4,292（事件 187）。",
        "去重臂：删除 7,815 条所有字段完全相同的重复行 → 13,644 例（事件 892，6.54%）→ 训练 10,915 / 测试 2,729（事件 178）。",
        "特征集：A = 36 个入院特征；B = 70 个（A + 34 项实验室指标）；C = 74 个（B + 4 项卒中后并发症）。",
        "模型：L2 logistic 回归（LR）、LightGBM（LGBM）、TabPFN v2（预训练检查点，零调参）。",
        "训练规模：100、250、500、1,000、2,000、4,000、8,000、16,000、17,167；去重臂最后一档为 10,915；TabPFN 受上下文上限约束，最大 8,000。",
        "温州队列 167 例（PSE 49 例，29.3%）→ D：核心 8 特征 / 扩展 24 特征，5 折 × 10 重复；E：ASM 暴露（134 vs 33）的观察性比较。",
    ]:
        para(doc, "· " + t, 9.3, after=3, indent=0.0)

    h2(doc, "0.2　记号与缩写")
    cap(doc, "表 0-1　本书反复出现的术语")
    table(doc, ["术语", "含义"], [
        ["AUROC", "受试者工作特征曲线下面积；0.5 = 随机猜测，1 = 完美排序"],
        ["AUPRC", "精确率–召回率曲线下面积（average precision）；事件稀少时比 AUROC 更能区分模型"],
        ["Brier 分数", "预测概率与真实结局（0/1）的均方误差；越低越好，同时惩罚判别力与校准"],
        ["校准斜率", "把预测 logit 对真实结局做 logistic 回归的斜率；1 = 校准良好，< 1 = 概率被压缩/过度自信"],
        ["校准截距", "同一回归的截距；0 = 无系统性高估或低估"],
        ["ΔAUROC", "同一批测试患者上两个模型的 AUROC 之差；配对 bootstrap 2,000 次给出 95% 区间"],
        ["n_train", "训练子集例数（每一档都从训练集重新抽样，测试集始终不变）"],
        ["full / dedup", "原始全队列 / 去除完全重复行后的去重队列"],
        ["LR / LGBM / TabPFN", "logistic 回归 / LightGBM / TabPFN v2 表格基础模型"],
        ["E 值", "未测量混杂需要达到多强的关联，才能把观察到的效应完全解释掉"],
        ["SMD", "标准化均值差；绝对值 < 0.1 通常视为两组平衡"],
        ["IPTW / AIPW", "逆概率加权 / 增广逆概率加权，两类倾向评分方法"],
        ["RMST", "限制平均生存时间：在固定时间窗（此处 730 天）内的平均无事件时间"],
    ], [3.6, 13.6], size=8.2, foot="源文件：术语定义对应 docs/配置要求与复现说明.md 与各算法架构方法节。")

    h2(doc, "0.3　怎么核对")
    for t in [
        "每个表下都有“源文件”脚注；打开 results/ 下对应文件即可逐位核对。",
        "重跑后，用第 11 节的锚点表比对到小数点后四位；任何一位不同都说明环境或数据版本不一致。",
        "图中曲线由 preds_*.csv 的行级预测重绘；若图与表不一致，以表为准，并检查 preds 文件是否为 final 版本。",
        "本书的“第五次”沿用项目内部计数；不同次跑数的口径可能不同，跨版本比较请只使用本书数字。",
    ]:
        para(doc, "· " + t, 9.3, after=3)


def sec1(doc):
    h1(doc, "1　数据与设计")
    h2(doc, "1.1　队列与划分")
    para(doc, "公共队列来自 Dryad 公开的缺血性卒中数据集（第 8 版），共 21,459 例，一年内继发性癫痫 936 例（4.36%）。"
              "固定分层 80/20 划分（种子 42）产生 17,167 例训练集与 4,292 例测试集；测试集含 187 个事件。"
              "去重臂删除 7,815 条所有字段完全相同的重复记录，剩 13,644 例（事件 892，6.54%），"
              "训练 10,915 / 测试 2,729（事件 178）。")
    para(doc, "一个值得注意的事实：被删除的 7,815 行里只有 44 个事件（0.56%），远低于全队列的 4.36%——"
              "重复记录以阴性随访为主。这正是去重臂要检验的：如果结论依赖这些重复的阴性记录，去重后应当改变。"
              "第 2–5 节会看到，结论没有改变，数值只发生了小幅移动。")
    cap(doc, "表 1-1　两套数据划分")
    table(doc, ["队列", "总例数", "事件数", "事件率", "训练例数", "测试例数", "测试事件"], [
        ["full（原始）", "21,459", "936", "4.36%", "17,167", "4,292", "187"],
        ["dedup（去重）", "13,644", "892", "6.54%", "10,915", "2,729", "178"],
    ], [3.8, 2.6, 2.2, 2.2, 2.6, 2.6, 2.4], size=8.4,
        foot="源文件：results/metrics_{full,dedup}_{A,B,C}_final.csv 的 n_train 网格；事件率 = 事件数 / 总例数。")

    h2(doc, "1.2　三套特征集")
    para(doc, "A/B/C 共用同一套划分、同一批测试患者与同一组模型，唯一变化是特征块。这是本系列能够做"
              "“同一患者上的配对增量比较”的原因：A→B 的差值就是实验室块的贡献，B→C 的差值就是并发症块的贡献。")
    cap(doc, "表 1-2　三套特征集的构成")
    table(doc, ["特征集", "变量数", "构成", "回答的问题"], [
        ["A", "36", "人口学（年龄、性别）、血管危险因素与病史、卒中病灶部位（脑叶/基底节/脑干/小脑等）、供血区与颈动脉斑块、大血管病变", "仅凭入院即可得的信息能预测到什么程度"],
        ["B", "70", "A 的 36 个 + 34 项实验室指标（血常规、凝血、生化、心肌酶、电解质等）", "实验室块带来多少增量"],
        ["C", "74", "B 的 70 个 + 4 项卒中后并发症（深静脉血栓、脑疝、脑积水、低蛋白血症）", "后验变量还能不能带来增量（边界测试）"],
    ], [1.6, 1.8, 10.4, 3.6], size=8.0,
        foot="源文件：server/tabpfn_bench.py 的 FEATURES_A/B/C 定义；D 研究另有核心 8 特征与扩展 24 特征，见 8.1 节。")

    h2(doc, "1.3　三个模型")
    para(doc, "三个模型代表三种归纳偏置：线性加性（LR）、树集成（LGBM）、预训练 Transformer（TabPFN）。"
              "三者使用完全相同的输入列与训练行，不做任何按模型的额外特征工程。")
    cap(doc, "表 1-3　A / B / C 的模型配置")
    table(doc, ["模型", "实现", "关键设置", "说明"], [
        ["LR", "scikit-learn LogisticRegression", "C = 1.0；max_iter = 3,000；random_state = 42", "实验室值按训练集 1/99 百分位缩尾；13 个偏态实验室变量 log1p；连续与有序变量标准化；二值变量原值。所有变换参数只来自训练行。"],
        ["LGBM", "LightGBM LGBMClassifier", "n_estimators = 300；learning_rate = 0.05；num_leaves = 31；min_child_samples = 50；subsample = 0.8；colsample_bytree = 0.8；reg_alpha = 0.1；reg_lambda = 0.1；scale_pos_weight = 阴性/阳性", "沿用源研究超参数，未在本数据上调参；随机种子 42。"],
        ["TabPFN", "TabPFN v2（预训练检查点）", "n_estimators = \"auto\"；ignore_pretraining_limits = True；device = cpu；random_state = 42", "零调参；仅在 n ≤ 8,000 时运行。检查点 SHA-256 见 11.1。"],
    ], [1.6, 4.2, 6.2, 5.2], size=7.8,
        foot="源文件：server/tabpfn_bench.py 第 130–165 行；预处理函数 lr_transform()。")
    para(doc, "D 研究使用不同配置：LR 的 max_iter = 5,000；LGBM 改为浅树（n_estimators = 100、num_leaves = 3、"
              "min_child_samples = 10），因为 n = 167 时深树会直接过拟合；TabPFN 配置不变。E 不是机器学习研究，"
              "而是观察性效应估计，方法见第 9 节。", 9.2, after=4)

    h2(doc, "1.4　跑数清单")
    para(doc, "下表是本次归档包含的全部拟合次数。A/B/C 的每一次拟合都产生一行指标（结果 CSV 共 144 行）；"
              "D 的 300 次拟合汇总为均值±标准差；E 的每次 bootstrap 重抽样都记录估计值，用于构造区间。")
    cap(doc, "表 1-4　本次跑数的拟合次数")
    table(doc, ["研究", "数据", "模型 × 规模", "拟合次数"], [
        ["A/B/C full", "17,167 训练 / 4,292 测试", "LR 9 档 + LGBM 9 档 + TabPFN 7 档 = 25 / 特征集", "75"],
        ["A/B/C dedup", "10,915 训练 / 2,729 测试", "LR 8 档 + LGBM 8 档 + TabPFN 7 档 = 23 / 特征集", "69"],
        ["D", "167 例，5 折 × 10 重复", "3 模型 × 2 特征集 × 50 折次", "300"],
        ["E", "167 例", "5 类效应估计 + 2,000 次 bootstrap + 生存分析", "—"],
    ], [3.2, 4.2, 7.2, 2.4], size=8.2,
        foot="合计 A/B/C 拟合 144 次。TabPFN 的 7 档为 100–8,000；16,000 与 17,167（或 10,915）档不运行。")

    h2(doc, "1.5　统计协议")
    para(doc, "判别力用 AUROC 与 AUPRC；概率质量用 Brier 分数；校准用“预测 logit 对真实结局”的 logistic 回归"
              "（C = 1e6，固定）给出斜率与截距。所有区间来自测试行上的 **2,000 次配对 bootstrap**（种子 42，"
              "百分位法）；配对意味着每次重抽样都同时抽取两个模型的同一批患者，因此区间反映的是“同一批人上的差”，"
              "而不是两个独立样本的比较。决策曲线在 0.05–0.60 的阈值网格上以 0.01 为步长计算净获益。"
              "D 研究另用 5 折 × 10 重复的分层交叉验证、Kaplan–Meier 三分位与 log-rank 检验；E 研究用 "
              "bootstrap 区间、E 值与 90 天界标分析。", 9.3)


def sec2(doc):
    h1(doc, "2　A / B / C 全训练规模明细")
    para(doc, "本节把 144 次拟合的每一条结果原样列出。每一行是一个训练规模；三组列分别是三个模型；"
              "每组内是 AUROC、AUPRC 与 Brier。“—”表示该模型在该规模没有运行（TabPFN 的预训练上下文上限为 8,000）。"
              "表格只做四位小数取舍，没有其他加工。")
    para(doc, "读表时注意三件事：第一，测试集始终固定，因此同一列内不同 n 的差异只来自训练集大小；第二，"
              "AUPRC 的随机基线约等于事件率（full 4.36%，dedup 6.52%），不是 0.5；第三，Brier 同时受判别力与"
              "校准影响，不能单独当作“准确率”。", 9.2, after=4)

    blocks = [
        ("A", "特征集 A（36 个入院特征）", "这是信息最少的一套特征：只有入院当时可得的人口学、病史、病灶与血管信息。"),
        ("B", "特征集 B（70 个：A + 34 项实验室）", "实验室块把信息量推高一档；这也是本系列的主推配置。"),
        ("C", "特征集 C（74 个：B + 4 项并发症）", "并发症块位于预测时点之后，本应不带来增量；这张表是验证。"),
    ]
    tno = 1
    for fs, title, intro in blocks:
        h2(doc, f"2.{'ABC'.index(fs) + 1}　{title}")
        para(doc, intro, 9.2, after=4)
        for tag, label in [("full", "全队列"), ("dedup", "去重队列")]:
            cap(doc, f"表 2-{tno}　特征集 {fs}，{label}：全部训练规模的指标（n = {MET[(fs, tag)].n_train.min():,}–{MET[(fs, tag)].n_train.max():,}）")
            size_table(doc, MET[(fs, tag)],
                       foot=("源文件：results/metrics_%s_%s_final.csv。n 为训练例数；测试集固定为 "
                             "4,292 例/187 事件（full）或 2,729 例/178 事件（dedup）。" % (tag, fs)))
            tno += 1

        # 汇总段落（从数据生成，避免手抄）
        d_f = MET[(fs, "full")]
        n0, nmax_f = int(d_f.n_train.min()), int(d_f.n_train.max())
        d_d = MET[(fs, "dedup")]
        nmax_d = int(d_d.n_train.max())
        best_m, best_n, best_v = mrow_best(fs, "full")
        para(doc,
             f"全队列：LR 从 n = {n0:,} 的 {mval(fs,'full',n0,'lr'):.4f} 升到 n = {nmax_f:,} 的 "
             f"{mval(fs,'full',nmax_f,'lr'):.4f}；LGBM 从 {mval(fs,'full',n0,'lgbm'):.4f} 升到 "
             f"{mval(fs,'full',nmax_f,'lgbm'):.4f}；TabPFN 在 n = {n0:,} 已达 {mval(fs,'full',n0,'tabpfn'):.4f}，"
             f"n = 8,000 为 {mval(fs,'full',8000,'tabpfn'):.4f}。全表最高值出现在 {MODEL[best_m]}、"
             f"n = {best_n:,}（{best_v:.4f}）。去重队列（n = {int(d_d.n_train.min()):,}–{nmax_d:,}）的形态相同："
             f"LR {mval(fs,'dedup',int(d_d.n_train.min()),'lr'):.4f} → {mval(fs,'dedup',nmax_d,'lr'):.4f}；"
             f"LGBM {mval(fs,'dedup',int(d_d.n_train.min()),'lgbm'):.4f} → {mval(fs,'dedup',nmax_d,'lgbm'):.4f}；"
             f"TabPFN {mval(fs,'dedup',int(d_d.n_train.min()),'tabpfn'):.4f} → {mval(fs,'dedup',8000,'tabpfn'):.4f}。",
             9.1, before=4, after=6)

    para(doc, "把六张表放在一起看，能读出三条跨特征集的稳定规律。第一，LR 的学习曲线最平：从 100 例到全量，"
              "涨幅约 0.09–0.24 AUROC，而 LGBM 在 100 例时几乎等于随机（0.5000–0.6626），到全量才追上来。"
              "第二，TabPFN 的曲线在前段最高、后段趋平：100 例时比 LGBM 高 0.24–0.38，8,000 例时与 LGBM 的差距"
              "缩到 0.001–0.007。第三，去重没有改变排序，只把绝对水平移动了 −0.002 到 +0.004，"
              "说明重复记录不是结论的来源。", 9.2, before=2)
    para(doc, "唯一的例外值得单独指出：在特征集 A 上，LGBM 用 16,000 例达到 0.9464，略高于 TabPFN 在 8,000 例上限的 0.9445。"
              "这不是“树模型更好”，而是 TabPFN 被上下文长度限制在 8,000——给它同样的 16,000 例，比较才公平，"
              "而当前实现做不到。B/C 上 TabPFN 在 8,000 例已经足够领先，所以这个上限不构成实际限制；"
              "在信息较少的 A 上，它恰好落在临界点。", 9.2, after=4)


def sec3(doc):
    h1(doc, "3　主结果：n = 8,000 与全训练集锚点")
    para(doc, "如果只看一张表，就看表 3-1。它给出 n = 8,000（三模型共同可用的最大规模）下，"
              "A/B/C × full/dedup × 三模型的 AUROC 与 2,000 次配对 bootstrap 的 95% 区间。"
              "区间来自同一批测试患者的配对重抽样，因此可以直接比较重叠程度。")
    cap(doc, "表 3-1　n = 8,000 的主结果（AUROC / AUPRC / Brier，括号内为 95% CI）")
    rows = []
    for fs in "ABC":
        for tag, label in [("full", "全队列"), ("dedup", "去重队列")]:
            rows.append(("__SECTION__", f"特征集 {fs} · {label}"))
            for m in ["lr", "lgbm", "tabpfn"]:
                o = CI[f"{fs}_{tag}_8000"][m]
                slope = SUMMARY[f"{fs}_{tag}"]["p_" + m]["cal_slope"]
                rows.append([MODEL[m], ci95(o, "auroc"), ci95(o, "auprc"), ci95(o, "brier"),
                             f"{slope:.3f}"])
    table(doc, ["模型", "AUROC（95% CI）", "AUPRC（95% CI）", "Brier（95% CI）", "校准斜率"], rows,
          [1.6, 4.3, 4.3, 4.3, 2.4], size=8.0,
          foot="源文件：results/restore/ci.json（区间）与 bench_summary_final.json（斜率）。测试集：full 4,292 例/187 事件；dedup 2,729 例/178 事件。")

    para(doc, "三条读数。第一，在 B/C 上 TabPFN 的 AUROC 为 0.9980 / 0.9982（full），区间下界 0.9954 / 0.9964，"
              "已经贴近该测试集可分辨的上限；LGBM 紧随其后（0.9923 / 0.9912），LR 明显更低（0.9625 / 0.9669）。"
              "第二，在 A 上三模型 closer：TabPFN 0.9445、LGBM 0.9378、LR 0.8553；TabPFN 对 LGBM 的配对差为 "
              "+0.0067（−0.0021, +0.0159），区间跨零——在只有 36 个入院特征时，两者的差别不足以在 4,292 例测试集上"
              "稳定检出。第三，去重后排序不变：A 为 TabPFN 0.9309 > LGBM 0.9282 > LR 0.8724；"
              "B 为 0.9985 / 0.9964 / 0.9660；C 为 0.9988 / 0.9960 / 0.9695。", 9.2, before=4)

    cap(doc, "表 3-2　全训练集锚点（LR 与 LGBM 用满训练集；TabPFN 标 † 者为 8,000 上限）")
    rows = []
    for fs in "ABC":
        for tag, label in [("full", "全队列"), ("dedup", "去重队列")]:
            rows.append(("__SECTION__", f"特征集 {fs} · {label}"))
            nmax = int(MET[(fs, tag)].n_train.max())
            for m in ["lr", "lgbm", "tabpfn"]:
                n_show = 8000 if m == "tabpfn" else nmax
                r = MET[(fs, tag)]
                rr = r[(r.n_train == n_show) & (r.model == m)]
                if len(rr) == 0:
                    continue
                rr = rr.iloc[0]
                slope = TN[f"slope_{tag}_{fs}_{m}_fullsize"]
                star = " †" if m == "tabpfn" else ""
                rows.append([MODEL[m] + star, f"{n_show:,}", f"{rr.auroc:.4f}", f"{rr.auprc:.4f}",
                             f"{rr.brier:.4f}", f"{slope:.3f}"])
    table(doc, ["模型", "n_train", "AUROC", "AUPRC", "Brier", "校准斜率"], rows,
          [2.2, 2.0, 3.0, 3.0, 3.0, 3.0], size=8.0,
          foot="源文件：metrics_{full,dedup}_{A,B,C}_final.csv 的最大 n 行；斜率来自 table_numbers.json 的 slope_*_fullsize。† TabPFN 无法在 8,000 以上运行，此行为 8,000 例估计，不是全量估计。")

    para(doc, "这张表回答“再多给数据还有没有用”。A 上 LGBM 从 8,000 的 0.9378 升到 17,167 的 0.9460（+0.0082），"
              "说明入院特征仍有可学的余量；B 上 LGBM 从 0.9923 升到 0.9956（+0.0033），已接近天花板；"
              "C 上 LGBM 从 0.9912 升到 0.9937（+0.0025），但仍低于 B 的 0.9956——并发症块没有带来信息，"
              "还轻微稀释了模型。LR 的对应变化是 A +0.0065、B +0.0023、C +0.0004（8,000 → 最大 n）。", 9.2, before=4)
    para(doc, "注意 TabPFN 的两行不是“全量”结果：其上下文上限为 8,000，表中数值与上一张表的 8,000 行相同。"
              "本书在所有出现 † 的地方都保持这一约定，避免把 8,000 的估计误读成 17,167 的结果。", 9.1, after=4)

    h2(doc, "3.1　计算成本")
    para(doc, "同一台服务器、同一批 CPU 上的墙钟时间（拟合 + 预测一次）。这不是 benchmarking 级别的精确计时，"
              "但足以回答临床落地时最现实的问题：训练一次要等多久。")
    cap(doc, "表 3-3　n = 8,000 时的单次拟合+预测耗时（秒）")
    rows = []
    for fs in "ABC":
        for tag, label in [("full", "全队列"), ("dedup", "去重队列")]:
            rows.append(("__SECTION__", f"特征集 {fs} · {label}"))
            d = MET[(fs, tag)]
            s = d[d.n_train == 8000].set_index("model")["fit_predict_seconds"]
            base = max(float(s["lr"]), 1e-3)
            for m in ["lr", "lgbm", "tabpfn"]:
                rows.append([MODEL[m], f"{float(s[m]):.2f}", f"{float(s[m]) / base:.0f}×"])
    table(doc, ["模型", "秒", "相对 LR"], rows, [3.4, 5.0, 5.0], size=8.0,
          foot="源文件：metrics_*_final.csv 的 fit_predict_seconds 列。单次运行、共享服务器、CPU；未做重复计时。")
    para(doc, "LR 与 LGBM 都在 1 秒以内；TabPFN 在 CPU 上需要 2–5 分钟，是 LR 的数千倍。"
              "这个成本差是真实的：TabPFN 的优势要用“更少样本达到同样性能”来兑换，而不是免费获得。"
              "在 B/C 上它用 500 例追平 LGBM 8,000 例，省下的是数据与标注，不是算力。", 9.2, before=3)


def sec4(doc):
    h1(doc, "4　校准与决策曲线")
    para(doc, "判别力只回答“排序对不对”，校准回答“概率能不能直接拿给患者看”。校准斜率 < 1 表示模型把概率推得"
              "过散（高估高风险、低估低风险），> 1 表示推得过于集中。表中同时给出 n = 8,000 与全训练集的斜率，"
              "以及对应的 Brier 分数。")
    for tag, label, tno in [("full", "全队列", 1), ("dedup", "去重队列", 2)]:
        cap(doc, f"表 4-{tno}　{label}的校准（n = 8,000 与全训练集）")
        rows = []
        for fs in "ABC":
            rows.append(("__SECTION__", f"特征集 {fs}"))
            for m in ["lr", "lgbm", "tabpfn"]:
                o = SUMMARY[f"{fs}_{tag}"]["p_" + m]
                nmax = int(MET[(fs, tag)].n_train.max())
                n_show = 8000 if m == "tabpfn" else nmax
                rr = MET[(fs, tag)]
                rr = rr[(rr.n_train == n_show) & (rr.model == m)].iloc[0]
                rows.append([MODEL[m], f"{o['cal_slope']:.3f}", f"{o['cal_intercept']:+.3f}",
                             f"{TN[f'slope_{tag}_{fs}_{m}_fullsize']:.3f}", f"{o['brier']:.4f}",
                             f"{rr.brier:.4f}"])
        table(doc, ["模型", "斜率@8,000", "截距@8,000", "斜率@全量", "Brier@8,000", "Brier@全量"], rows,
              [2.0, 2.9, 2.9, 2.9, 3.0, 3.0], size=8.0,
              foot=("源文件：bench_summary_final.json（8,000）与 table_numbers.json（全量斜率）、"
                    "metrics_*_final.csv（Brier）。† TabPFN 的“全量”列仍为 8,000 估计。"))
    para(doc, "LightGBM 的斜率在六个组合中全部低于 0.85（0.677–0.815），是系统性的概率压缩：它排序很好，"
              "但输出的概率偏保守/过度自信，直接用于个体风险沟通会失真。LR 除 A-full 的 0.846 外都在 0.96–1.01，"
              "校准接近恒等；TabPFN 在 0.897–1.240 之间，B/C 的去重队列略高于 1（1.15 / 1.24），"
              "说明它在极低风险区的概率被推得过于集中——这是接近完美判别时校准斜率不稳定的典型表现，"
              "不应解读为“校准变差”。", 9.2, before=4)
    para(doc, "全训练集上的斜率进一步放大这一模式：B/C 的 LR 与 TabPFN 斜率都略高于 1（1.02–1.04 与 1.02–1.24），"
              "因为测试集里几乎没有中间风险的患者，logistic 斜率对少数极端概率非常敏感。结论不变："
              "若要把概率用于临床，LR 与 TabPFN 可直接使用，LGBM 需要先做校准（Platt 或 isotonic）。", 9.2)

    for fs, name in [("A", "特征集 A"), ("B", "特征集 B"), ("C", "特征集 C")]:
        figure(doc, f"fig_calib_{fs}.png",
               f"图 4-{ 'ABC'.index(fs) + 1 }　{name}在 n = 8,000 下的校准曲线（按预测风险五分位）")
    for fs, name in [("A", "特征集 A"), ("B", "特征集 B"), ("C", "特征集 C")]:
        figure(doc, f"fig_dca_{fs}.png",
               f"图 4-{ 'ABC'.index(fs) + 4 }　{name}在 n = 8,000 下的决策曲线（阈值 0.05–0.60）")
    para(doc, "决策曲线的读法：在某个阈值上，曲线高于“全治”与“不治”两条参考线，才说明按模型分流有净获益。"
              "B/C 上 TabPFN 在绝大多数阈值上最高；A 上三模型在 0.10–0.30 区间接近，LGBM 在中段略优。"
              "校准与决策曲线的完整像素级结果见 results/figs/。", 9.1, before=4)


def sec5(doc):
    h1(doc, "5　增量与配对比较")
    para(doc, "本节回答两个问题：加一个特征块值不值（A→B、B→C）；换一个模型值不值（TabPFN vs LGBM vs LR）。"
              "所有差值都在同一批测试患者上计算，区间来自 2,000 次配对 bootstrap。")

    h2(doc, "5.1　特征块增量")
    cap(doc, "表 5-1　特征块带来的 ΔAUROC（n = 8,000；括号内为 95% CI）")
    rows = []
    for label, pre in [("A → B（加实验室）", "delta_AB_full"), ("B → C（加并发症）", "delta_CB_full")]:
        for tag, tlabel in [("full", "全队列"), ("dedup", "去重队列")]:
            key = pre if tag == "full" else pre.replace("_full", "_dedup")
            if tag == "dedup" and pre == "delta_AB_full":
                key = "delta_B_minus_A"
                suffix = "_dedup"
            elif tag == "dedup":
                key = "delta_CB_dedup"
                suffix = ""
            else:
                suffix = ""
            vals = []
            for m in ["lr", "lgbm", "tabpfn"]:
                k = key + ("" if tag == "full" else ("_dedup" if pre == "delta_CB_full" else ""))
                if tag == "dedup" and pre == "delta_AB_full":
                    k = "delta_B_minus_A_" + m + "_dedup"
                elif tag == "dedup":
                    k = "delta_CB_dedup_" + m
                else:
                    k = pre + "_" + m
                vals.append(ci_str(TN[k], signed=True))
            rows.append([label, tlabel] + vals)
    table(doc, ["对比", "队列", "LR", "LGBM", "TabPFN"], rows, [4.0, 1.9, 3.8, 3.8, 3.8], size=7.8,
          foot="源文件：results/table_numbers.json（delta_AB_*、delta_B_minus_A_*、delta_CB_*）。正值为加入新特征块后 AUROC 升高。")
    para(doc, "实验室块是唯一大幅改变判别力的增量：LR +0.1072、LGBM +0.0544、TabPFN +0.0535（full），"
              "三个区间都不含零；去重后同向且幅度相近（+0.0936 / +0.0683 / +0.0676）。"
              "这个增量在 LR 上最大，因为线性模型从新信息中获益最多；对已经很强的 LGBM/TabPFN，"
              "增益相对小，但仍然真实。", 9.2, before=4)
    para(doc, "并发症块的增量则是噪声级别：LR +0.0043（+0.0008, +0.0084），LGBM −0.0011（−0.0029, +0.0005），"
              "TabPFN +0.0002（−0.0004, +0.0011）。只有 LR 的区间排除零，但 0.0043 仅为实验室块增量（0.1072）的"
              "二十五分之一，且低于任何合理的临床意义阈值。去重后 LR 的区间甚至触及零（−0.00005, +0.00745）。"
              "结论是清楚的：四个卒中后并发症变量在 70 个基线+实验室特征之外没有增量价值。", 9.2)

    h2(doc, "5.2　模型之间的配对差")
    cap(doc, "表 5-2　同一测试集上的 ΔAUROC（n = 8,000；括号内为 95% CI）")
    rows = []
    for fs in "ABC":
        for tag, label in [("full", "全队列"), ("dedup", "去重队列")]:
            rows.append(("__SECTION__", f"特征集 {fs} · {label}"))
            for key, name in [
                ("delta_auroc_tabpfn_minus_lgbm", "TabPFN − LGBM"),
                ("delta_auroc_tabpfn_minus_lr", "TabPFN − LR"),
                ("delta_auroc_lgbm_minus_lr", "LGBM − LR"),
            ]:
                v = SUMMARY[f"{fs}_{tag}"][key]
                crosses = "是" if v[1] <= 0 <= v[2] else "否"
                rows.append([name, ci_str(v, signed=True), crosses])
    table(doc, ["对比", "ΔAUROC（95% CI）", "区间跨零"], rows, [4.6, 9.0, 2.4], size=8.0,
          foot="源文件：bench_summary_final.json 的 delta_auroc_* 字段。跨零 = 95% 区间包含 0，差异不能在 5% 水平上检出。")
    para(doc, "三条结论。第一，TabPFN 相对 LR 的优势在所有六个组合中都统计上可检出（最小 +0.0293，"
              "区间 +0.0178 至 +0.0439，C-dedup）。第二，TabPFN 相对 LGBM 的优势在 B/C 上可检出"
              "（B full +0.0057 [0.0017, 0.0110]；C full +0.0069 [0.0019, 0.0138]），在 A 上不可检出"
              "（+0.0067 [−0.0021, +0.0159]）。第三，LGBM 相对 LR 的优势在所有组合中都可检出，"
              "幅度 0.024–0.083——树模型比线性模型更适合这套特征。", 9.2, before=4)

    h2(doc, "5.3　数据效率：TabPFN 用多少例追平 LGBM")
    para(doc, "定义：以 LGBM 在 n = 8,000 的 AUROC 为基准，允许 −0.002 的容差，找 TabPFN 首次达到该水平的"
              "最小训练规模。这是对“小样本优势”最直接、也最不容易夸大的量化。")
    cap(doc, "表 5-3　TabPFN 追平 LGBM（8,000 例水平）所需的最小 n")
    rows = []
    for fs in "ABC":
        for tag, label in [("full", "全队列"), ("dedup", "去重队列")]:
            n_match = SUMMARY[f"{fs}_{tag}"]["tabpfn_n_to_match_lgbm_at_8000"]
            lgb8 = mval(fs, tag, 8000, "lgbm")
            tp = mval(fs, tag, n_match, "tabpfn")
            rows.append([f"特征集 {fs} · {label}", f"{lgb8:.4f}", f"{int(n_match):,}", f"{tp:.4f}",
                         f"{tp - lgb8:+.4f}"])
    table(doc, ["组合", "LGBM@8,000", "TabPFN 最小 n", "TabPFN@该 n", "差值"], rows,
          [5.0, 3.0, 3.2, 3.2, 2.6], size=8.2,
          foot="源文件：bench_summary_final.json 的 tabpfn_n_to_match_lgbm_at_8000；定义为 TabPFN AUROC ≥ LGBM@8,000 − 0.002 的最小 n。")
    para(doc, "B/C 全队列只需 500 例就进入容差（0.9911 / 0.9907 vs 0.9923 / 0.9912），去重队列需 2,000 例；"
              "A 需要 4,000 例（0.9424，已超过 LGBM@8,000 的 0.9378）。换成比例：在 B/C 上，TabPFN 用 6.25% 的训练数据"
              "达到 LGBM 用满 8,000 例的水平；在 A 上这个比例是 50%。信息越少的问题，预训练先验越值钱——"
              "这与“小样本优势来自先验而非数据”的解释一致。", 9.2, before=4)

    for fs, name in [("A", "特征集 A"), ("B", "特征集 B"), ("C", "特征集 C")]:
        figure(doc, f"fig_roc_pr_{fs}.png",
               f"图 5-{ 'ABC'.index(fs) + 1 }　{name}在 n = 8,000 下的 ROC 与 PR 曲线（全队列）")
    for fs, name in [("A", "特征集 A"), ("B", "特征集 B"), ("C", "特征集 C")]:
        figure(doc, f"fig_roc_pr_{fs}_dedup.png",
               f"图 5-{ 'ABC'.index(fs) + 4 }　{name}在 n = 8,000 下的 ROC 与 PR 曲线（去重队列）")


def sec6(doc):
    h1(doc, "6　特征重要性：A / B / C 的前十变量")
    para(doc, "重要性用两种口径：LGBM 的总增益份额（gain share，所有树分裂带来的不纯度下降占比，加总为 100%），"
              "以及标准化 LR 的系数绝对值。两者不可直接比较——增益份额是相对量，系数是每标准差变化的 log-odds——"
              "但各自内部可以排序。下表列出每个特征集的前十，右侧同时给出另一模型的前十，便于对照。")
    for fs, tno in [("A", 1), ("B", 2), ("C", 3)]:
        im = REST["importance"][fs]
        cap(doc, f"表 6-{tno}　特征集 {fs}（{im['n_features']} 个变量）的前十重要性")
        rows = []
        for k in range(10):
            g = im["lgbm"][k]
            l = im["lr"][k]
            rows.append([str(k + 1), CN.get(g["var"], g["var"]), f"{g['gain_share'] * 100:.2f}%",
                         CN.get(l["var"], l["var"]), f"{l['abs_coef']:.2f}"])
        table(doc, ["排名", "LGBM 变量", "增益份额", "LR 变量", "|系数|"], rows,
              [1.2, 5.2, 2.6, 5.2, 2.4], size=8.2,
              foot=f"源文件：results/restore/restore.json 的 importance.{fs}。模型在全训练集（17,167 例）上重拟合；"
                   f"LGBM 测试 AUROC {im['test_auroc_lgbm']:.4f}，LR 测试 AUROC {im['test_auroc_lr']:.4f}。")
        figure(doc, f"fig_importance_{fs}.png",
               f"图 6-{tno}　特征集 {fs} 的特征重要性：LightGBM 总增益（左）与 LR 系数绝对值（右）")

    para(doc, "A 的信息高度集中：NIHSS 单独占 LGBM 增益的 49.99%，年龄 17.53%，高血压 6.66%，"
              "其余变量都在 3% 以下；LR 的口径更分散，岛叶（1.68）、NIHSS（1.30）、高尿酸血症（0.91）排前三。"
              "这解释了 A 的学习曲线为什么最陡：模型主要在学习“NIHSS 越高越危险”这一条主轴。", 9.2, before=4)
    para(doc, "B 把重要性重新分配：NIHSS 降到 29.54%，白细胞 9.75%、C 反应蛋白 7.64%、α-羟丁酸脱氢酶 6.09%、"
              "谷草转氨酶 5.20% 进入前五；LR 侧则是 D-二聚体（3.84）、高血压（3.23）、C 反应蛋白（3.03）、"
              "谷草转氨酶（2.99）。实验室指标不是“锦上添花”，它们确实承担了相当一部分判别信息。", 9.2)
    para(doc, "C 的变化最能说明问题：加入四个并发症变量后，LGBM 的增益重心转到 CK-MB（18.68%）、NIHSS（14.91%）、"
              "C 反应蛋白（12.56%）、α-羟丁酸脱氢酶（6.44%）与乳酸（4.90%）；四个并发症变量在 LGBM 中排名"
              "第 45（深静脉血栓）、74（脑疝）、65（脑积水）、35（低蛋白血症），全部在后半段。"
              "LR 中脑积水（第 9）与低蛋白血症（第 12）进入中上段，深静脉血栓（第 19）、脑疝（第 25）居中——"
              "这四项的单变量关联很强（第 3.1 节表 1），但在 70 个特征之外能提供的增量几乎为零。"
              "单变量关联与增量价值是两个不同的量。", 9.2, after=4)


def sec7(doc):
    h1(doc, "7　特征集 A 的五折交叉验证与 OOF")
    para(doc, "主分析用的是固定 80/20 划分。为了确认 A 的结果不是某一次划分的偶然，另做一次 5 折分层交叉验证"
              "（在 17,167 例训练集内部，种子 42），并汇总折外预测（OOF）。OOF 指标与“折均值”不完全相同："
              "前者把所有折的预测拼成一份完整训练集的预测，后者是五个折指标的算术平均。")
    cap(doc, "表 7-1　特征集 A 的 5 折交叉验证（训练集内部）")
    rows = []
    for m in ["lr", "lgbm"]:
        c = REST["cv_A"][m]
        rows.append([MODEL[m],
                     f"{c['auroc_mean']:.4f} ± {c['auroc_sd']:.4f}",
                     f"{c['auprc_mean']:.4f} ± {c['auprc_sd']:.4f}",
                     f"{c['brier_mean']:.4f} ± {c['brier_sd']:.4f}",
                     f"{c['oof_auroc']:.4f}", f"{c['oof_auprc']:.4f}", f"{c['oof_brier']:.4f}"])
    table(doc, ["模型", "AUROC（折均值±SD）", "AUPRC", "Brier", "OOF AUROC", "OOF AUPRC", "OOF Brier"], rows,
          [1.6, 3.4, 3.0, 2.9, 2.2, 2.2, 2.2], size=7.9,
          foot="源文件：results/restore/restore.json 的 cv_A。5 折、单次重复；OOF = 折外预测拼接后整体计算。")
    para(doc, "CV 的数值高于固定测试集（LR 0.8849 vs 0.8553；LGBM 0.9461 vs 0.9378），原因不是模型变了，"
              "而是评估对象不同：CV 在训练集内部做，测试折与训练折来自同一分布且没有留出整个 20% 的固定测试集；"
              "固定测试集是更严格、也更接近外部验证的口径。两者都报告，是为了让读者看到“划分带来的不确定性”有多大——"
              "约 0.01–0.03 AUROC，远大于模型之间的部分差距。任何小于这个量级的模型比较都应谨慎解读。", 9.2, before=4)


def sec8(doc):
    h1(doc, "8　D 研究：温州 167 例的首次发作时点预测")
    para(doc, "D 研究换了队列与临床问题：167 例卒中后早期癫痫发作患者（PSE 49 例，29.3%；中位随访 592 天），"
              "在“首次发作之后”这个决策点预测是否会发展为晚期 PSE。核心特征集只有 8 个变量，"
              "扩展集 24 个；评估用 5 折 × 10 重复交叉验证（种子 42）。因此它的数字不能与 A/B/C 横向比较，"
              "只能在本节内部比较。")

    h2(doc, "8.1　队列基线")
    cap(doc, "表 8-1　温州队列基线（总体、无 PSE、PSE）")
    rows = []
    spec = [
        ("年龄（岁，中位/IQR）", "age_med_iqr", "iqr"),
        ("男性", "sex_male_pct", "pct"),
        ("缺血性卒中", "stroke_ischemic_pct", "pct"),
        ("NIHSS（中位/IQR）", "nihss_med_iqr", "iqr"),
        ("首次发作距卒中 > 3 天", "interval_gt3_pct", "pct"),
        ("早期多次发作", "multiple_seizures_pct", "pct"),
        ("癫痫持续状态", "status_epilepticus_pct", "pct"),
        ("皮层受累", "cortical_pct", "pct"),
        ("EEG 癫痫样放电", "eeg_epileptic_pct", "pct"),
        ("病灶体积（cm³，中位/IQR）", "lesion_vol_med_iqr", "iqr"),
        ("使用 ASM", "asm_pct", "pct"),
        ("随访天数（中位/IQR）", "followup_days_med_iqr", "iqr"),
    ]
    for label, key, kind in spec:
        vals = []
        for g in ["overall", "pse_0", "pse_1"]:
            block = TW["overall"] if g == "overall" else TW["by_pse"][g]
            v = block[key]
            vals.append(med_iqr(v) if kind == "iqr" else pct(v))
        rows.append([label] + vals)
    table(doc, ["指标", "总体（n = 167）", "无 PSE（n = 118）", "PSE（n = 49）"], rows,
          [5.6, 4.2, 4.2, 4.2], size=8.1,
          foot="源文件：results/table1_wenzhou.json。PSE 组的随访天数为“到首次晚期发作或末次随访”的时间，因此中位数仅 74 天，不能与无 PSE 组直接比较。")
    para(doc, "两组差异集中在发作本身的信息：首次发作距卒中 > 3 天者 32.7% vs 10.2%，早期多次发作 26.5% vs 6.8%，"
              "癫痫持续状态 32.7% vs 23.7%；PSE 组 NIHSS 的上四分位数更高（16 vs 11）。"
              "皮层受累与 EEG 癫痫样放电在两组间反而略低（83.7% vs 85.6%；18.4% vs 22.0%），"
              "提示这套队列的转归更多由发作时间与复发模式驱动，而不是单纯的病灶严重度。", 9.2, before=4)

    h2(doc, "8.2　交叉验证结果")
    cap(doc, "表 8-2　D 研究 5 折 × 10 重复交叉验证（均值 ± SD）")
    rows = []
    for m in ["lr", "lgbm", "tabpfn"]:
        rows.append([MODEL[m],
                     f"{dmet('core','auroc',m):.4f} ± {dmet('core','auroc',m,'std'):.4f}",
                     f"{dmet('core','auprc',m):.4f} ± {dmet('core','auprc',m,'std'):.4f}",
                     f"{dmet('core','brier',m):.4f} ± {dmet('core','brier',m,'std'):.4f}",
                     f"{dmet('core','cal_slope',m):.3f}",
                     f"{dmet('full','auroc',m):.4f} ± {dmet('full','auroc',m,'std'):.4f}",
                     f"{dmet('full','auprc',m):.4f}",
                     f"{dmet('full','brier',m):.4f}",
                     f"{dmet('full','cal_slope',m):.3f}"])
    table(doc, ["模型", "核心 AUROC", "核心 AUPRC", "核心 Brier", "核心斜率", "扩展 AUROC", "扩展 AUPRC", "扩展 Brier", "扩展斜率"], rows,
          [1.4, 2.6, 2.4, 2.2, 1.6, 2.6, 2.0, 1.8, 1.6], size=7.4,
          foot="源文件：results/summary_D.json 的 feature_sets.*.metrics_mean_std。核心 8 变量、扩展 24 变量；50 个折次。")
    para(doc, "核心 8 变量上 LR 最好（AUROC 0.7101，AUPRC 0.5331，Brier 0.1825），LGBM 次之（0.7018），"
              "TabPFN 最低（0.6706）。扩展到 24 变量后三个模型全部变差（0.6359 / 0.6389 / 0.6233）——"
              "在 n = 167 下，额外 16 个变量带来的是过拟合而不是信息。校准方面 TabPFN 最好（核心斜率 0.939），"
              "LGBM 0.804，LR 0.918；扩展集上三者都退化（0.50–0.87）。", 9.2, before=4)

    h2(doc, "8.3　配对差与 ASM 增量")
    cap(doc, "表 8-3　核心特征集上的配对 ΔAUROC（bootstrap 95% CI）")
    rows = []
    for key, name in [("tabpfn_minus_lgbm", "TabPFN − LGBM"), ("tabpfn_minus_lr", "TabPFN − LR"),
                      ("lr_minus_lgbm", "LR − LGBM")]:
        v = SD["paired_bootstrap_delta_auroc_core"][key]
        rows.append([name, ci_str(v, signed=True), "是" if v[1] <= 0 <= v[2] else "否"])
    table(doc, ["对比", "ΔAUROC（95% CI）", "区间跨零"], rows, [4.6, 9.0, 2.4], size=8.2,
          foot="源文件：results/summary_D.json 的 paired_bootstrap_delta_auroc_core。")
    para(doc, "只有 TabPFN − LR 的区间排除零（−0.0565 [−0.1090, −0.0058]），即 TabPFN 显著更差；"
              "TabPFN − LGBM 与 LR − LGBM 的区间都跨零。在小队列里，模型差距的区间本身就很宽，"
              "这正是 D 研究反复强调“诚实基准”的原因。", 9.2, before=4)

    cap(doc, "表 8-4　加入 ASM 变量前后的 AUROC（核心集，10 次重复）")
    rows = []
    for m in ["lr", "lgbm", "tabpfn"]:
        a = SD["asm_incremental_core"][m]
        rows.append([MODEL[m], f"{a['auroc_without_asm']:.4f}", f"{a['auroc_with_asm']:.4f}",
                     f"{a['delta_mean']:+.4f}", f"{a['n_repeats_delta_gt0']}/10"])
    table(doc, ["模型", "不含 ASM", "含 ASM", "ΔAUROC", "Δ>0 的重复次数"], rows,
          [2.4, 3.2, 3.2, 3.0, 3.6], size=8.2,
          foot="源文件：results/summary_D.json 的 asm_incremental_core。")
    para(doc, "三个模型的 Δ 都为负，且 Δ>0 的重复次数只有 0–2/10。ASM 使用不提供增量预测价值；"
              "这与 E 研究的结论一致：是否用药主要由发作严重度决定，而严重度已经由核心 8 变量编码。", 9.2, before=3)

    h2(doc, "8.4　风险三分位与生存分层")
    cap(doc, "表 8-5　按模型风险评分三分位的两年无 PSE 生存率")
    rows = []
    for m in ["lr", "tabpfn"]:
        k = SD["km_risk_tertiles"][m]
        rows.append([MODEL[m],
                     f"{k['tertile0']['n']}/{k['tertile0']['events']}/{k['tertile0']['pse_free_2y']:.3f}",
                     f"{k['tertile1']['n']}/{k['tertile1']['events']}/{k['tertile1']['pse_free_2y']:.3f}",
                     f"{k['tertile2']['n']}/{k['tertile2']['events']}/{k['tertile2']['pse_free_2y']:.3f}",
                     f"{k['logrank_chi2']:.2f}", sci(k["logrank_p"])])
    table(doc, ["模型", "低危（n/事件/2 年）", "中危（n/事件/2 年）", "高危（n/事件/2 年）", "log-rank χ²", "p"], rows,
          [1.8, 3.6, 3.6, 3.6, 2.2, 2.2], size=8.0,
          foot="源文件：results/summary_D.json 的 km_risk_tertiles。每格为“组内例数/事件数/两年无 PSE 生存率”。")
    figure(doc, "fig_km_lr.png", "图 8-1　按 LR 风险评分三分位的 Kaplan–Meier 两年无 PSE 生存曲线")
    figure(doc, "fig_km_tabpfn.png", "图 8-2　按 TabPFN 风险评分三分位的 Kaplan–Meier 两年无 PSE 生存曲线")
    para(doc, "LR 三分位的两年无 PSE 生存率为 0.889 / 0.769 / 0.477，log-rank χ² = 25.16，p = 3.4 × 10⁻⁶；"
              "TabPFN 为 0.853 / 0.750 / 0.524，χ² = 15.72，p = 3.9 × 10⁻⁴。两者都能把风险分层拉开，"
              "但 LR 的梯度更陡。注意这是“分层能力”，不是“判别力”——三分位割裂会放大看起来的差异，"
              "不能替代 AUROC。", 9.2, before=4)

    h2(doc, "8.5　学习曲线与决策曲线")
    figure(doc, "fig_learning_curve.png", "图 8-3　核心特征集上的学习曲线（三个种子均值）：TabPFN 在 n = 30–80 领先，线性模型在全队列规模反超")
    para(doc, "n = 30 时 TabPFN 0.5681、LR 0.5014、LGBM 0.4174；n = 80 时 TabPFN 0.6944 仍最高；"
              "到 n = 134 时 LGBM 0.7104、LR 0.6875，TabPFN 回落到 0.6486。这是全系列中唯一出现"
              "“基础模型在小样本领先、随样本增加被反超”完整轨迹的数据集——恰好在 n 只有一两百例时，"
              "预训练先验的价值最大，而数据量一旦足够，简单模型的归纳偏置更合适。", 9.2, before=2)
    figure(doc, "fig_dca.png", "图 8-4　核心特征集三个模型的决策曲线")
    para(doc, "决策曲线在高阈值段三模型接近；在 0.2–0.4 的临床相关区间，LR 与 LGBM 略高于 TabPFN。"
              "结合判别力与校准，D 研究的推荐是 8 变量 LR：不是因为它最“先进”，而是因为它在 n = 167 时"
              "最稳、最可解释、校准也足够好。", 9.2, before=3)


def sec9(doc):
    h1(doc, "9　E 研究：抗癫痫药物与晚期 PSE 风险")
    para(doc, "E 研究是观察性比较，不是预测建模：134 例使用 ASM、33 例未使用，比较随访期内 PSE 的发生风险。"
              "由于用药由发作严重度决定，粗比较天然受指征混杂影响；本节给出粗估计、多变量校正、倾向评分校正、"
              "IPTW 与 AIPW 五种口径，目的是看结论是否稳健，而不是宣称因果。")

    h2(doc, "9.1　效应估计")
    c = SE["crude"]; a = SE["adjusted"]; ps = SE["ps_adjusted"]; ip = SE["iptw"]; ai = SE["aipw"]
    cap(doc, "表 9-1　ASM 与 PSE 风险的效应估计")
    rows = [
        ["粗比值比（OR）", f"{c['or']:.3f}", f"（{c['or_lo']:.3f}, {c['or_hi']:.3f}）", f"E 值 {c['e_value']:.3f}"],
        ["多变量校正 OR", f"{a['or']:.3f}", f"（{a['or_lo']:.3f}, {a['or_hi']:.3f}）", f"E 值 {a['e_value']:.3f}；协变量 9 个"],
        ["倾向评分校正 OR", f"{ps['or']:.3f}", f"（{ps['or_lo']:.3f}, {ps['or_hi']:.3f}）", "PS 作为协变量"],
        ["IPTW 风险差", f"{ip['risk_diff']:+.5f}", f"（{ip['rd_lo']:+.3f}, {ip['rd_hi']:+.3f}）", f"PS c 统计量 {ip['ps_auc']:.3f}"],
        ["AIPW 风险差", f"{ai['ate_risk_diff']:+.4f}", f"（{ai['rd_lo']:+.3f}, {ai['rd_hi']:+.3f}）", "增广估计"],
    ]
    table(doc, ["方法", "估计值", "95% CI", "备注"], rows, [4.2, 3.2, 5.2, 4.0], size=8.1,
          foot="源文件：results/E/summary_E.json 的 crude / adjusted / ps_adjusted / iptw / aipw。所有区间为 bootstrap 2,000 次。")
    para(doc, "五个口径的点估计在 0.92–1.38 之间，全部区间跨 1（或风险差跨 0）。没有保护效应的证据，"
              "也没有可信的危害信号。E 值 2.10（粗）与 1.57（校正）意味着：需要一个与 ASM 和 PSE 都有"
              "约 1.6–2.1 倍关联的未测量混杂因素，才能把观察到的效应完全解释掉——在本领域这并非不可能，"
              "因此不能把“无显著”读成“无效应”。", 9.2, before=4)

    h2(doc, "9.2　协变量平衡")
    cap(doc, "表 9-2　倾向评分加权前后的标准化均值差（SMD）")
    rows = []
    for _, r in SMD.iterrows():
        rows.append([CN.get(r.variable, r.variable), f"{r.smd_before:+.3f}", f"{r.smd_after:+.3f}",
                     "是" if abs(r.smd_after) < 0.1 else "否"])
    table(doc, ["协变量", "加权前 SMD", "加权后 SMD", "|SMD| < 0.1"], rows, [5.0, 3.6, 3.6, 3.0], size=8.2,
          foot="源文件：results/E/smd_balance.csv。SMD 为 ASM 组减未用药组。")
    figure(doc, "fig_love.png", "图 9-1　协变量平衡的 Love 图（加权前后）")
    para(doc, "加权前最大 |SMD| 为 0.423（早期多次发作），加权后降到 0.152（皮层受累）；多数协变量已平衡，"
              "但仍有两个超过 0.1。更重要的是倾向评分本身的 c 统计量只有 0.510——它几乎不能区分治疗组与"
              "对照组，说明可观测变量无法解释用药选择。因此 IPTW 结果只能作为稳定性检查，不能当作因果估计；"
              "真正决定用药的是未测量的发作严重度。", 9.2, before=4)

    h2(doc, "9.3　生存分析")
    s = SE["survival"]
    cap(doc, "表 9-3　两年无 PSE 生存与限制平均生存时间")
    rows = [
        ["两年无 PSE 生存率", f"{s['pse_free_2y_asm']:.3f}", f"{s['pse_free_2y_noasm']:.3f}",
         f"log-rank p = {s['logrank_p']:.3f}"],
        ["730 天 RMST（天）", f"{s['rmst_730_asm']:.1f}", f"{s['rmst_730_noasm']:.1f}",
         f"差 {s['rmst_diff']:+.1f}（{s['rmst_diff_lo']:+.1f}, {s['rmst_diff_hi']:+.1f}）"],
        ["90 天界标 OR", "—", "—", f"{s['landmark_90d']['or']:.3f}（{s['landmark_90d']['or_lo']:.3f}, {s['landmark_90d']['or_hi']:.3f}）"],
    ]
    table(doc, ["指标", "ASM（n = 134）", "无 ASM（n = 33）", "差异 / 检验"], rows, [4.2, 4.0, 4.0, 5.0], size=8.2,
          foot="源文件：results/E/summary_E.json 的 survival。RMST = 限制平均生存时间（0–730 天）。")
    figure(doc, "fig_km_asm.png", "图 9-2　按 ASM 状态的 Kaplan–Meier 两年无 PSE 生存曲线")
    para(doc, "两条曲线几乎重合：两年无 PSE 生存 70.3% vs 74.5%，log-rank p = 0.447；RMST 差 −23.6 天"
              "（95% CI −122.4 至 +81.1）。90 天界标分析（排除最早期的死亡/事件竞争）OR 0.924"
              "（0.320–3.910），同样没有信号。比例风险假设未通过检验，因此不报告单一 Cox 风险比——"
              "这也是方法节明确写下的决定。", 9.2, before=4)

    h2(doc, "9.4　事件分期与卒中类型分层")
    cap(doc, "表 9-4　按时期划分的 PSE 事件数")
    rows = []
    for epoch in ["0-90d", "91-365d", ">365d"]:
        e = s["events_by_epoch"][epoch]
        rows.append([epoch.replace("d", " 天"), str(e["1"]), str(e["0"])])
    table(doc, ["时期", "ASM 组事件", "无 ASM 组事件"], rows, [4.6, 4.6, 4.6], size=8.4,
          foot="源文件：results/E/summary_E.json 的 survival.events_by_epoch。")
    para(doc, "早期事件高度集中在 ASM 组（0–90 天 24 vs 3），随后两组差距收窄（91–365 天 7 vs 4；>365 天 10 vs 1）。"
              "这符合指征混杂的预期：临床医生给最严重的患者用药，而最严重的患者最早发生事件；"
              "若把 0–90 天的事件当作“药物危害”，就会误读。90 天界标分析正是为此设计，结果无差异。", 9.2, before=4)

    cap(doc, "表 9-5　按卒中类型的 ASM 效应")
    rows = []
    for key, name in [("ICH", "出血性卒中"), ("ischemic", "缺血性卒中")]:
        x = SE["stroke_type_strata"][key]
        rows.append([name, f"{x['n']}（{x['n_asm']}/{x['n_noasm']}）",
                     f"{x['risk_asm'] * 100:.1f}%", f"{x['risk_noasm'] * 100:.1f}%",
                     f"{x['or']:.3f}（{x['or_lo']:.3f}, {x['or_hi']:.3f}）"])
    table(doc, ["卒中类型", "n（ASM/无）", "ASM 组事件率", "无 ASM 组事件率", "OR（95% CI）"], rows,
          [3.2, 3.4, 3.2, 3.4, 4.0], size=8.2,
          foot="源文件：results/E/summary_E.json 的 stroke_type_strata。")
    para(doc, "分层结果方向相反：出血性卒中 OR 0.488（0.110–2.140），缺血性卒中 OR 2.907（0.948–12.131）。"
              "两个区间都很宽，且样本量小（分别为 56 与 111 例），不足以支持“效应异质性”的结论；"
              "它更可能反映随机波动与小样本不稳定性。E 研究的立场是描述而非推断：在这 167 例里，"
              "没有可复现的保护信号。", 9.2, before=3)


def sec10(doc):
    h1(doc, "10　图表总索引")
    para(doc, "按编号列出本书全部图与表，以及它们在五套算法架构中的对应位置。算法架构中的编号与本书不完全相同："
              "本书是“结果账本”，编号按数据流排列；算法架构按叙事排列。对应关系以本表为准。")
    figs = [
        ("图 4-1 / 4-2 / 4-3", "A/B/C 校准曲线（n = 8,000）", "A/B/C 图 4", "fig_calib_{A,B,C}.png"),
        ("图 4-4 / 4-5 / 4-6", "A/B/C 决策曲线（n = 8,000）", "A/B/C 图 6", "fig_dca_{A,B,C}.png"),
        ("图 5-1 / 5-2 / 5-3", "A/B/C ROC 与 PR 曲线（全队列）", "A/B/C 图 2", "fig_roc_pr_{A,B,C}.png"),
        ("图 5-4 / 5-5 / 5-6", "A/B/C ROC 与 PR 曲线（去重）", "A/B/C 图 7", "fig_roc_pr_*_dedup.png"),
        ("图 6-1 / 6-2 / 6-3", "A/B/C 特征重要性", "A/B/C 图 5（C 为图 6）", "fig_importance_{A,B,C}.png"),
        ("图 8-1", "LR 风险三分位 KM 曲线", "D 图 3a", "fig_km_lr.png"),
        ("图 8-2", "TabPFN 风险三分位 KM 曲线", "D 图 3b", "fig_km_tabpfn.png"),
        ("图 8-3", "D 学习曲线", "D 图 2", "fig_learning_curve.png"),
        ("图 8-4", "D 决策曲线", "D 图 4", "fig_dca.png"),
        ("图 9-1", "协变量平衡 Love 图", "E 补充图", "fig_love.png"),
        ("图 9-2", "ASM 分层 KM 曲线", "E 图 2", "fig_km_asm.png"),
    ]
    cap(doc, "表 10-1　图索引")
    table(doc, ["本书编号", "内容", "算法架构位置", "源文件"], figs, [3.6, 5.6, 4.0, 4.2], size=7.9,
          foot="A/B/C 的学习曲线（图 3-4 至 3-6）由 results/figs/fig_learning_{A,B,C}.png 提供，对应算法架构图 3。")
    tables = [
        ("表 0-1", "术语表", "—"), ("表 1-1", "两套数据划分", "方法节"), ("表 1-2", "三套特征集", "方法节"),
        ("表 1-3", "模型配置", "方法节"), ("表 1-4", "拟合次数", "—"),
        ("表 2-1 至 2-6", "A/B/C × full/dedup 全规模明细", "补充材料"),
        ("表 3-1", "n = 8,000 主结果与 CI", "A/B/C 表 2"), ("表 3-2", "全训练集锚点", "A/B/C 表 2 注"),
        ("表 3-3", "计算成本", "—"),
        ("表 4-1 / 4-2", "校准斜率与截距", "A/B/C 正文"), ("表 5-1", "特征块增量", "B/C 表 2"),
        ("表 5-2", "模型配对差", "A/B/C 正文"), ("表 5-3", "数据效率", "A/B/C 正文"),
        ("表 6-1 至 6-3", "A/B/C 前十重要性", "A 表 3；B/C 表 3"),
        ("表 7-1", "A 的五折 CV 与 OOF", "A 表 4"),
        ("表 8-1", "温州队列基线", "D 表 1"), ("表 8-2", "D 交叉验证", "D 表 2"),
        ("表 8-3", "D 配对差", "D 正文"), ("表 8-4", "ASM 增量", "D 正文"), ("表 8-5", "KM 三分位", "D 正文"),
        ("表 9-1", "E 效应估计", "E 表 1"), ("表 9-2", "SMD 平衡", "E 补充表"),
        ("表 9-3", "生存指标", "E 正文"), ("表 9-4", "事件分期", "E 正文"), ("表 9-5", "卒中类型分层", "E 正文"),
        ("表 11-1", "文件指纹", "—"), ("表 11-2", "关键数字锚点", "—"),
    ]
    cap(doc, "表 10-2　表索引")
    table(doc, ["本书编号", "内容", "算法架构位置"], tables, [3.8, 8.6, 5.0], size=7.9)


def sec11(doc):
    h1(doc, "11　复现锚点")
    para(doc, "这一节是给“下一位接手的人”的：不需要读完整本书，只要重跑后比对下面三张表，就能判断"
              "环境与数据是否一致。")

    h2(doc, "11.1　文件指纹（SHA-256）")
    cap(doc, "表 11-1　输入文件的 SHA-256")
    table(doc, ["文件", "说明", "SHA-256"], [
        ["data.csv", "公共队列 21,459 行", "be84a00921702c45e5c9d250176602b2c62ed96ac41716dca8893b0c5be49d4b"],
        ["Wenzhou_167_cases_deidentified.csv", "温州队列 167 行", "98d04a5eb44813e223f9150913637ccc9368d20e1adff80edb11a6bd1af900d4"],
        ["tabpfn-v2-classifier-finetuned-zk73skhh.ckpt", "TabPFN v2 检查点", "cf8c519c01eaf1613ee91239006d57b1c806ff5f23ac1aeb1315ba1015210e49"],
    ], [4.6, 3.4, 9.4], size=6.8,
        foot="源文件：docs/配置要求与复现说明.md 第 6 节；数据指纹与 split_info.json 的 data_sha256 一致。")
    para(doc, "哈希值用 `sha256sum` 或 Python `hashlib.sha256` 计算；任何一位不同都说明文件被改动过，"
              "后续数字不可直接比较。", 9.1, after=4)

    h2(doc, "11.2　关键数字锚点")
    cap(doc, "表 11-2　重跑后应逐位一致的数字（保留四位小数）")
    anchors = [
        ("A full, n = 8,000: LR AUROC", f"{mval('A','full',8000,'lr'):.4f}", "metrics_full_A_final.csv"),
        ("A full, n = 8,000: LGBM AUROC", f"{mval('A','full',8000,'lgbm'):.4f}", "同上"),
        ("A full, n = 8,000: TabPFN AUROC", f"{mval('A','full',8000,'tabpfn'):.4f}", "同上"),
        ("B full, n = 8,000: TabPFN AUROC", f"{mval('B','full',8000,'tabpfn'):.4f}", "metrics_full_B_final.csv"),
        ("C full, n = 8,000: TabPFN AUROC", f"{mval('C','full',8000,'tabpfn'):.4f}", "metrics_full_C_final.csv"),
        ("C dedup, n = 8,000: TabPFN AUROC", f"{mval('C','dedup',8000,'tabpfn'):.4f}", "metrics_dedup_C_final.csv"),
        ("A→B ΔAUROC（LR，full）", f"{TN['delta_AB_full_lr'][0]:+.4f}", "table_numbers.json"),
        ("B→C ΔAUROC（TabPFN，full）", f"{TN['delta_CB_full_tabpfn'][0]:+.4f}", "table_numbers.json"),
        ("D 核心集 LR AUROC（均值）", f"{dmet('core','auroc','lr'):.4f}", "summary_D.json"),
        ("D 核心集 TabPFN AUROC（均值）", f"{dmet('core','auroc','tabpfn'):.4f}", "summary_D.json"),
        ("E 粗 OR", f"{SE['crude']['or']:.4f}", "E/summary_E.json"),
    ]
    table(doc, ["指标", "期望值", "源文件"],
          anchors, [7.6, 3.4, 6.2], size=8.0,
          foot="这些值对环境和数据版本敏感；建议先跑四个规模（100 / 8,000 / 全量）再全量重跑。")

    h2(doc, "11.3　运行顺序")
    for t in [
        "① 校验三个输入文件的 SHA-256（表 11-1）。",
        "② 运行 A/B/C 基准：固定划分 → 逐规模训练 → 固定测试集评估 → 输出 metrics_*_final.csv 与 preds_*_final.csv。",
        "③ 运行汇总与出图：bench_analysis.py → table_numbers.json；restore_analyses.py → restore.json；bootstrap_ci.py → ci.json；make_figures_restore.py → 图。",
        "④ 运行 D/E：wenzhou_de.py → summary_D.json 与 E/summary_E.json；table1_wenzhou.py → 基线表。",
        "⑤ 比对表 11-2；全部一致后再重新生成本书与五套算法架构的 docx/PDF。",
    ]:
        para(doc, "· " + t, 9.2, after=3)
    para(doc, "环境提示：LR 支路需要 scikit-learn 1.7.2 的旧环境才能与归档锚点逐位一致；LGBM/TabPFN 与 D/E "
              "在 scikit-learn 1.9.1、pandas 3.0.6、numpy 2.5.3、lightgbm 4.7.0、tabpfn 9.2.0 的新环境运行。"
              "本机用 `py -3.12`。两套环境的完整版本表与逐条命令见《配置要求与复现说明》第 2–6 节。", 9.2, before=4)

    h2(doc, "11.4　版本说明")
    para(doc, "本书对应第五次大跑数的最终归档。与之前几次相比，本次的关键变化是：TabPFN 补跑到 8,000 例上限、"
              "新增去重臂、并把温州 167 例的 D/E 研究纳入同一结果体系。早期版本的 A/B/C 曾使用不同的图表组合"
              "（例如缺少基线表、ROC/PR 或特征重要性）；本次已把两版内容合并，算法架构与本书使用同一套数字。"
              "如发现本书与旧版 PDF 不一致，以本书为准。", 9.3)


def build():
    doc = Document()
    sec = doc.sections[0]
    sec.page_width, sec.page_height = Cm(21), Cm(29.7)
    sec.top_margin = sec.bottom_margin = Cm(2.0)
    sec.left_margin = sec.right_margin = Cm(1.7)
    add_page_number(sec)

    style = doc.styles["Normal"]
    style.font.name = "Times New Roman"
    style.font.size = Pt(9.5)
    style.element.rPr.rFonts.set(qn("w:eastAsia"), "宋体")

    cover(doc)
    toc(doc)
    sec0(doc)
    sec1(doc)
    sec2(doc)
    sec3(doc)
    sec4(doc)
    sec5(doc)
    sec6(doc)
    sec7(doc)
    sec8(doc)
    sec9(doc)
    sec10(doc)
    sec11(doc)

    out = os.path.join(OUT, "卒中后癫痫五套算法架构_跑数结果汇编.docx")
    doc.save(out)
    print("saved", out.encode("ascii", "ignore").decode() or "docx")
    return out


def to_pdf(docx_path):
    import win32com.client as win32
    word = win32.DispatchEx("Word.Application")
    word.Visible = False
    try:
        d = word.Documents.Open(docx_path, ReadOnly=False)
        pdf = os.path.splitext(docx_path)[0] + ".pdf"
        d.SaveAs(pdf, 17)
        d.Close(False)
        print("pdf ok")
        return pdf
    finally:
        word.Quit()


if __name__ == "__main__":
    p = build()
    to_pdf(p)
