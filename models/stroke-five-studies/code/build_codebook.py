# -*- coding: utf-8 -*-
"""生成《五套算法架构代码汇编》docx：所有分析脚本 + 用途说明 + 运行命令 + 代码全文。"""
import hashlib
import os
from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

BASE = os.path.dirname(os.path.abspath(__file__))
SERVER = os.path.join(BASE, "server")
OUT = os.path.join(BASE, "books")
os.makedirs(OUT, exist_ok=True)

TITLE = "卒中后癫痫五套算法架构 · 代码汇编"
SUBTITLE = "从原始数据到算法架构全部数字与图表的可执行代码"
VERSION = "v1.0 ｜ 2026-11-07 ｜ 三合医研发团队，河南大学"

SCRIPTS = [
    dict(
        no="2.1", file="tabpfn_bench.py", path=os.path.join(SERVER, "tabpfn_bench.py"),
        papers="A / B / C",
        purpose=("主基准脚本，负责算法架构 A、B、C 三套特征集在 full 与 dedup 两个队列上的全部逐规模结果。"
                 "它按固定种子 42 做分层 80/20 切分，构造嵌套训练子集（n = 100、250、500、1,000、2,000、"
                 "4,000、8,000、16,000 与全训练集），在同一个子集上训练三个模型，并在固定测试集上计算 "
                 "AUROC、AUPRC、Brier，保存 metrics.csv 和逐行预测 test_predictions.csv。TabPFN 只在 "
                 "n ≤ 8,000 上运行（原生上下文上限）；传统模型额外跑到 16,000 与全量。"),
        inputs="data.csv（21,459 例公共队列，SHA-256 见附录 B）",
        outputs="out/<tag>_<features>/metrics.csv；out/<tag>_<features>/test_predictions.csv",
        run="$PY -u tabpfn_bench.py --features A --tag full --out $BASE/out/full_A\n"
            "# 六个组合：--features A/B/C × --tag full/dedup",
        notes=["LR 支路用于交叉核对；算法架构最终 LR 数字由 lr_rerun.py 重算并覆盖，二者预处理一致。",
               "嵌套子集保证不同 n 之间是前缀关系，同一 n 下三模型看到完全相同的患者。",
               "--max-tabpfn-n 默认 10,000，本项目实际评估到 8,000。"],
    ),
    dict(
        no="2.2", file="lr_rerun.py", path=os.path.join(SERVER, "lr_rerun.py"),
        papers="B / C",
        purpose=("只补算 logistic 回归（LR）支路。已有 TabPFN/LightGBM 结果不重跑；脚本读取 "
                 "out/<tag>_<feature>/metrics.csv 与 test_predictions.csv，删掉 model == 'lr' 的旧行与 "
                 "p_lr 旧列，按修正后的预处理顺序重算 B、C × full/dedup 的 LR，再写回原文件。"
                 "关键修复是训练行索引先 np.sort：lbfgs 对行序敏感，不排序会在第 4–5 位小数产生差异。"),
        inputs="已由 tabpfn_bench.py 生成的 4 个组合目录（B/C × full/dedup）",
        outputs="原地覆盖上述目录的 metrics.csv 与 test_predictions.csv（仅 LR 行/列）",
        run="$OLD_PY lr_rerun.py        # sklearn 1.7.2 的 D13 老环境",
        notes=["锚点：B LR 0.9647814390954035 / 0.7872176622723596；C LR 0.9673034710506947 / 0.7984723092638404。",
               "预处理顺序：μ/σ 在原始训练值上估计 → 1/99 缩尾 → 13 列 log1p → 标准化；顺序反了 AUROC 会差到第 3–4 位。",
               "不设置 OMP_NUM_THREADS，保持与归档运行相同的 BLAS 归约顺序。"],
    ),
    dict(
        no="2.3", file="verify_lr_172.py", path=os.path.join(SERVER, "verify_lr_172.py"),
        papers="A / B / C",
        purpose=("最小化验证脚本：只拟合 B、C 全训练集的 LR，打印测试 AUROC/AUPRC/Brier，用来确认当前 "
                 "Python 环境（scikit-learn 1.7.2）能逐位复现归档锚点。它不写文件，只看标准输出。"),
        inputs="data.csv",
        outputs="标准输出（三行指标 + 与锚点的对照）",
        run="$OLD_PY verify_lr_172.py",
        notes=["预期：B 0.9647814390954035 / 0.7872176622723596；C 0.9673034710506947 / 0.7984723092638404。",
               "任何一位对不上，先检查 sklearn 版本与 OMP_NUM_THREADS，再检查数据文件指纹。"],
    ),
    dict(
        no="2.4", file="bench_analysis.py", path=os.path.join(SERVER, "bench_analysis.py"),
        papers="A / B / C",
        purpose=("汇总与出图。扫描 6 个组合目录，只接受 metrics.csv 与 test_predictions.csv 同时存在、"
                 "且三模型 n_train 对齐的组合；在 n = 8,000 上计算校准斜率与截距，在测试行上做 2,000 次"
                 "配对 bootstrap，输出 combined_metrics.csv、bench_summary_final.json，以及学习曲线、"
                 "ROC/PR、校准曲线、决策曲线四类图（A/B/C 各一套）。"),
        inputs="out/ 下 6 个组合目录（A/B/C × full/dedup）",
        outputs=("out/combined_metrics.csv；out/bench_summary_final.json；"
                 "figs/fig_learning_A/B/C.png、fig_roc_pr_*.png、fig_calib_*.png、fig_dca_*.png"),
        run="$PY bench_analysis.py",
        notes=["缺文件或 n 不对齐的组合会被跳过并记入 skipped，不会静默拼数。",
               "校准斜率用 logit(p) 对 y 的 LR（C = 1e6）估计；bootstrap 固定种子 42。",
               "算法架构正文嵌入 ROC/PR、学习、校准、决策四类图；特征重要性图由 2.8 另行生成。"],
    ),
    dict(
        no="2.5", file="table1_baseline.py", path=os.path.join(SERVER, "table1_baseline.py"),
        papers="A",
        purpose=("计算 A 算法架构表 1：36 个入院特征按一年内癫痫结局分组，full 与 dedup 两套；连续变量给"
                 "中位数与四分位，二值变量给百分比。结果以 JSON 打到标准输出，重定向保存为 table1.json。"),
        inputs="data.csv",
        outputs="标准输出 → results/table1.json",
        run="py table1_baseline.py data.csv > table1.json",
        notes=["只做描述统计，不建模、不调参。", "dedup 用 df.drop_duplicates()，与主基准完全一致。"],
    ),
    dict(
        no="2.6", file="restore_analyses.py", path=os.path.join(BASE, "restore_analyses.py"),
        papers="A / B / C",
        purpose=("重建三套算法架构的描述性与可解释性结果：A 的表 1（36 个入院特征）、B 的表 1（70 个特征）、"
                 "C 的表 1（4 个卒中后并发症）按结局分组的总体/无 PSE/PSE 与 P 值；两模型的特征重要性"
                 "（LightGBM 总增益占比、标准化 logistic 回归系数绝对值）；以及 A 的训练集五折交叉验证与"
                 "汇总袋外性能。全部在最终口径下重算，输出一个 JSON 供算法架构装配脚本读取。"),
        inputs="data.csv（21,459 例公共队列）",
        outputs="results/restore/restore.json",
        run="py -3.12 restore_analyses.py",
        notes=["连续变量用 Mann–Whitney U、二值变量用 χ²；实验室指标必须按连续变量处理，否则卡方会报负值。",
               "特征重要性在 full 训练集（n = 17,167）上拟合后计算；LR 系数对应协议预处理尺度。",
               "C 的表 1 只含四个并发症变量；A 的表 1 含 range_lobe（任一脑叶受累）。"],
    ),
    dict(
        no="2.7", file="bootstrap_ci.py", path=os.path.join(BASE, "bootstrap_ci.py"),
        papers="A / B / C",
        purpose=("为 A/B/C 的表 2 补 95% bootstrap 置信区间：三个模型 × full/dedup 两个队列 × "
                 "n = 8,000 与最大训练规模（17,167 或 10,915）× AUROC/AUPRC/Brier 三项指标，"
                 "每项 2,000 次对测试行的重抽样，种子 42。结果写入 ci.json，算法架构表 2 的括号区间即来自这里。"),
        inputs="results/preds_full_*_final.csv、results/preds_dedup_*_final.csv",
        outputs="results/restore/ci.json",
        run="py -3.12 bootstrap_ci.py",
        notes=["公开表无患者标识，只能按行重抽样；这一局限已写进三套算法架构的讨论。",
               "TabPFN 不在 17,167 上评估，对应键不存在，表中以“—”呈现。"],
    ),
    dict(
        no="2.8", file="make_figures_restore.py", path=os.path.join(BASE, "make_figures_restore.py"),
        papers="A / B / C",
        purpose=("生成算法架构图 2（n = 8,000 的 ROC 与精确率–召回率曲线，full 队列）、图 7（同一曲线，"
                 "dedup 队列）与图 5/6（特征重要性：LightGBM 总增益与 logistic 回归系数绝对值）。"
                 "ROC/PR 一律调用 scikit-learn 的 roc_curve 与 precision_recall_curve，避免手写累积量出错。"),
        inputs="results/preds_{full,dedup}_{A,B,C}_final.csv；results/restore/restore.json",
        outputs="results/figs/fig_roc_pr_{A,B,C}.png、fig_roc_pr_{A,B,C}_dedup.png、fig_importance_{A,B,C}.png",
        run="py -3.12 make_figures_restore.py",
        notes=["三个模型固定配色：LR 蓝、LightGBM 橙、TabPFN 绿。",
               "PR 面板必须用 sklearn 的 precision_recall_curve；早期手写版本把 recall 当 precision 除，纵轴会压到 0–0.005。",
               "生成后把 PNG 复制到 papers/01_A|02_B|03_C/figs/，再由 build_docx5.py 嵌入。"],
    ),
    dict(
        no="3.1", file="wenzhou_de.py", path=os.path.join(SERVER, "wenzhou_de.py"),
        papers="D / E",
        purpose=("温州 167 例的 D、E 两个任务都在这一个脚本里。D：核心 8 变量与全集 24 变量，重复分层 "
                 "5 折 × 10 次（种子 42），LR/LightGBM/TabPFN 三模型，输出 CV 指标、学习曲线（种子 "
                 "42/43/44，n = 30–134）、校准、决策曲线、风险三分位 KM 与 log-rank、配对 bootstrap。"
                 "E：ASM 与 PSE 的粗 OR、多变量校正 OR（bootstrap CI）、倾向评分作为协变量的 OR、"
                 "IPTW/AIPW 稳定性检查、SMD 平衡、E 值、KM/RMST（730 天）、90 天界标、分期事件表、"
                 "卒中类型分层。"),
        inputs="Wenzhou_167_cases_deidentified.csv（167 例，SHA-256 见附录 B）",
        outputs=("summary_D.json、summary_E.json；cv_summary_core/full.csv、cv_fold_metrics_*.csv、"
                 "learning_curve_*.csv、dca.csv、E/smd_balance.csv；D/E 的 KM、ROC、校准、DCA、学习曲线图"),
        run="$PY wenzhou_de.py --data $DATA --out out/D --task D\n"
            "$PY wenzhou_de.py --data $DATA --out out/E --task E",
        notes=["IPTW/AIPW 只作稳定性检查，不进入算法架构主估计。",
               "E 算法架构不报告单一 Cox 风险比：比例风险假设不成立；脚本中的诊断函数不作为结论。",
               "ASM 增量预测在核心 8 变量上做 50 次重复，逐次比较加/不加 ASM 的 AUROC。"],
    ),
    dict(
        no="3.2", file="table1_wenzhou.py", path=os.path.join(SERVER, "table1_wenzhou.py"),
        papers="D / E",
        purpose=("计算 D、E 算法架构表 1：同一批 167 例，分别按 PSE 结局（D）和 ASM 用药（E）分组，输出总体、"
                 "by_pse、by_asm 三套描述统计与末次发作时间分布。结果 JSON 打到标准输出。"),
        inputs="Wenzhou_167_cases_deidentified.csv",
        outputs="标准输出 → results/table1_wenzhou.json",
        run="py table1_wenzhou.py Wenzhou_167_cases_deidentified.csv > table1_wenzhou.json",
        notes=["连续变量给中位数与四分位，二值变量给百分比。", "列名在脚本开头按固定顺序重命名，防止错列。"],
    ),
]

APPENDIX_SCRIPTS = [
    dict(
        no="A.1", file="tabpfn_smoke.py", path=os.path.join(SERVER, "tabpfn_smoke.py"),
        papers="环境自检",
        purpose=("加载固定权重，检查 TabPFNClassifier 是否支持 ignore_pretraining_limits/device/random_state，"
                 "并在 n = 1,000/4,000/10,000 上各拟合一次，打印耗时与 AUROC。用于确认权重路径、版本和 "
                 "CPU 推理正常，不产生算法架构数字。"),
        inputs="data.csv + 权重文件",
        outputs="标准输出",
        run="$PY tabpfn_smoke.py",
        notes=["第一次在新机器上跑数时先执行它，冒烟通过再跑主基准。"],
    ),
    dict(
        no="D.1", file="build_docx5.py", path=os.path.join(BASE, "build_docx5.py"),
        papers="算法架构装配",
        purpose=("算法架构装配脚本（本机 Windows 运行，不参与科学计算）。读取 papers/ 下的中英文 Markdown 源稿、"
                 "results/ 下的 JSON/CSV 指标、figs/ 图片，生成 10 份算法架构 docx 和《配置要求与复现说明》docx。"
                 "表格中的数字全部来自结果文件，不在脚本里手写。"),
        inputs="papers/*/*.md、papers/*/figs/*.png、results/*.json、results/*.csv",
        outputs="docx/paperA–E_{en,cn}.docx；docx/配置要求与复现说明.docx",
        run="py -3.12 build_docx5.py",
        notes=["表格列宽、跨页重复表头、图注同页等排版规则都写在脚本里。",
               "修改算法架构数字时改 results/ 的源文件，不要改 docx。"],
    ),
    dict(
        no="D.2", file="to_pdf5.ps1", path=os.path.join(BASE, "to_pdf5.ps1"),
        papers="PDF 导出",
        purpose=("用本机 Word 的 COM 接口把 docx/ 下所有 docx 批量另存为 PDF（格式码 17）。只做格式转换，"
                 "不改内容。"),
        inputs="docx/*.docx",
        outputs="docx/*.pdf",
        run="powershell -ExecutionPolicy Bypass -File to_pdf5.ps1",
        notes=["需要本机安装 Microsoft Word。", "转换前先关闭已打开的旧 PDF，避免文件占用。"],
    ),
    dict(
        no="D.3", file="build_resultsbook.py", path=os.path.join(BASE, "build_resultsbook.py"),
        papers="结果汇编",
        purpose=("生成《卒中后癫痫五套算法架构_跑数结果汇编》docx + pdf。全部数字从 results/ 的 JSON/CSV "
                 "读取（144 次 A/B/C 拟合明细、n = 8,000 主结果与 CI、校准、增量、重要性、D/E 全部结果），"
                 "不在脚本里手写任何指标值。"),
        inputs="results/*.json、results/*_final.csv、results/figs/*.png、results/E/*",
        outputs="books/卒中后癫痫五套算法架构_跑数结果汇编.docx/.pdf",
        run="py -3.12 build_resultsbook.py",
        notes=["本书是“账本”：每个表下有源文件脚注，可逐位核对。",
               "修订跑数时先改 results/ 源文件再重跑本脚本，禁止手改表格。"],
    ),
    dict(
        no="D.4", file="build_codebook.py", path=os.path.join(BASE, "build_codebook.py"),
        papers="代码汇编",
        purpose=("生成本书自身（《五套算法架构代码汇编》）。按运行顺序收录全部脚本并逐条注明用途、输入、"
                 "输出与运行命令。"),
        inputs="本目录与 server/ 下全部 .py/.ps1",
        outputs="books/五套算法架构代码汇编.docx/.pdf",
        run="py -3.12 build_codebook.py",
        notes=["新增脚本后，把它的条目加进 SCRIPTS 或 APPENDIX_SCRIPTS 再重跑本脚本。"],
    ),
    dict(
        no="A.2", file="external_transfer.py", path=os.path.join(SERVER, "external_transfer.py"),
        papers="迁移实验（未入册）",
        purpose=("跨队列迁移实验：把 D13 公共队列与温州 167 例共有的 7 个变量对接，检验公共队列上训练的"
                 "模型能否直接迁移到温州队列。结果接近随机，按“不合格的不写进去”的原则未进入任何一册正文。"),
        inputs="data.csv + 温州数据",
        outputs="标准输出（AUROC 等）",
        run="$PY external_transfer.py",
        notes=["保留此脚本是为了完整记录“跑过但不采用”的实验；其阴性结论在 D 的局限节有文字交代。"],
    ),
    dict(
        no="A.3", file="debug_lr.py", path=os.path.join(SERVER, "debug_lr.py"),
        papers="诊断",
        purpose=("一次性诊断脚本：定位两条代码路径的 LR 微小差异（预处理顺序），用于确认最终 LR 数字的"
                 "口径。不产生算法架构数字。"),
        inputs="data.csv",
        outputs="标准输出（对照表）",
        run="$PY debug_lr.py",
        notes=["结论已固化在 lr_rerun.py 的注释里；此脚本仅作归档，无需重跑。"],
    ),
    dict(
        no="A.4", file="debug_loop.py", path=os.path.join(SERVER, "debug_loop.py"),
        papers="诊断",
        purpose=("一次性诊断脚本：复现嵌套子集循环并打印各规模对照，用于核对 metrics CSV 的行数。"
                 "不产生算法架构数字。"),
        inputs="data.csv",
        outputs="标准输出（各规模行数对照）",
        run="$PY debug_loop.py",
        notes=["仅作归档，无需重跑。"],
    ),
    dict(
        no="A.5", file="setup_venv_server.sh", path=os.path.join(SERVER, "setup_venv_server.sh"),
        papers="环境构建",
        purpose=("在服务器上构建 D13 老环境（scikit-learn 1.7.2 的 venv）：先从清华镜像拉取 pip wheel "
                 "直接解包进 venv，再安装 requirements.txt 并自检五个关键包。五套算法架构的 LR 支路"
                 "（lr_rerun.py）就在这个 venv 里复算，才能与归档锚点逐位一致。"),
        inputs="requirements.txt（同目录）",
        outputs="~/D13_20261107/venv（LR 老环境）",
        run="bash setup_venv_server.sh",
        notes=["服务器直连外网被 CMCC 门户劫持时，本脚本的镜像方案即当时的离线安装绕行路径。",
               "新机器复现 LR 数字前先跑它，再跑 lr_rerun.py。"],
    ),
    dict(
        no="A.6", file="requirements.txt", path=os.path.join(SERVER, "requirements.txt"),
        papers="环境依赖",
        purpose=("D13 老环境的依赖清单（numpy/pandas/scikit-learn 1.7.2/lightgbm/matplotlib/joblib 等），"
                 "由 A.5 安装。是 LR 支路可复现性的版本依据。"),
        inputs="—",
        outputs="—",
        run="pip install -r requirements.txt",
        notes=["新环境（LightGBM/TabPFN/D/E 支路）的完整版本表在《配置要求与复现说明》第 2 节。"],
    ),
    dict(
        no="A.7", file="model_d13_server.py", path=os.path.join(SERVER, "model_d13_server.py"),
        papers="前身项目",
        purpose=("D13 前身项目（卒中后癫痫三场景建模：full + dedup 双版）的主脚本。五套算法架构的数据、"
                 "固定划分与 LR 老环境均来自该项目；本脚本归档用于追溯数据管线的来龙去脉。"),
        inputs="~/D13_20261107/data.csv",
        outputs="~/D13_20261107/results/",
        run="venv/bin/python model_d13_server.py",
        notes=["属于前身任务，其数字不进入五套算法架构正文；只作溯源归档。"],
    ),
    dict(
        no="A.8", file="audit_d13.py", path=os.path.join(SERVER, "audit_d13.py"),
        papers="前身项目",
        purpose=("D13 前身项目的审计脚本：核对数据 SHA-256、划分信息与结果文件的一致性。"
                 "五套算法架构沿用其“双端审计”的做法。"),
        inputs="~/D13_20261107/results/",
        outputs="审计报告（标准输出）",
        run="venv/bin/python audit_d13.py",
        notes=["属于前身任务，只作溯源归档。"],
    ),
    dict(
        no="A.9", file="slurm_d13.sh", path=os.path.join(SERVER, "slurm_d13.sh"),
        papers="前身项目",
        purpose=("D13 前身项目的 SLURM 作业提交模板（full / dedup 两个参数化任务）。"
                 "归档用于展示当时的调度方式。"),
        inputs="—",
        outputs="slurm_*.out / slurm_*.err",
        run="sbatch -J d13_full slurm_d13.sh full",
        notes=["属于前身任务，只作溯源归档。"],
    ),
]

EXCLUDED = []


def set_font(run, size, bold=False, italic=False, mono=False, east="宋体", color=None):
    run.font.name = "Consolas" if mono else "Times New Roman"
    run.font.size = Pt(size)
    run.font.bold = bold
    run.font.italic = italic
    if color:
        run.font.color.rgb = RGBColor(*color)
    rPr = run._element.get_or_add_rPr()
    rFonts = rPr.find(qn("w:rFonts"))
    if rFonts is None:
        rFonts = OxmlElement("w:rFonts")
        rPr.append(rFonts)
    rFonts.set(qn("w:eastAsia"), "宋体" if mono else east)


def para(doc, text="", size=10, bold=False, italic=False, align=None, before=0, after=0,
         indent=None, keep=False, east="宋体", color=None):
    p = doc.add_paragraph()
    if align is not None:
        p.alignment = align
    pf = p.paragraph_format
    pf.space_before = Pt(before)
    pf.space_after = Pt(after)
    pf.line_spacing = 1.0
    if indent is not None:
        pf.left_indent = Cm(indent)
    if keep:
        pf.keep_with_next = True
    if text:
        r = p.add_run(text)
        set_font(r, size, bold=bold, italic=italic, east=east, color=color)
    return p


def add_page_number(section):
    footer = section.footer
    p = footer.paragraphs[0]
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r1 = p.add_run("第 ")
    set_font(r1, 8)
    run = p.add_run()
    set_font(run, 8)
    f1 = OxmlElement("w:fldChar"); f1.set(qn("w:fldCharType"), "begin")
    it = OxmlElement("w:instrText"); it.set(qn("xml:space"), "preserve"); it.text = "PAGE"
    f2 = OxmlElement("w:fldChar"); f2.set(qn("w:fldCharType"), "separate")
    t = OxmlElement("w:t"); t.text = "1"
    f3 = OxmlElement("w:fldChar"); f3.set(qn("w:fldCharType"), "end")
    for el in (f1, it, f2, t, f3):
        run._r.append(el)
    r2 = p.add_run(" 页")
    set_font(r2, 8)


def add_code(doc, text):
    lines = text.splitlines()
    for line in lines:
        p = doc.add_paragraph()
        pf = p.paragraph_format
        pf.space_before = Pt(0)
        pf.space_after = Pt(0)
        pf.line_spacing = Pt(9.2)
        pf.left_indent = Cm(0)
        r = p.add_run(line if line.strip() else " ")
        set_font(r, 7.5, mono=True)


def bullet(doc, label, value):
    p = doc.add_paragraph(style="List Bullet")
    p.paragraph_format.space_before = Pt(1)
    p.paragraph_format.space_after = Pt(1)
    r = p.add_run(label + "：")
    set_font(r, 9.5, bold=True)
    r2 = p.add_run(value)
    set_font(r2, 9.5)


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def script_section(doc, meta, new_page=True):
    if new_page:
        doc.add_page_break()
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(0)
    p.paragraph_format.space_after = Pt(4)
    p.paragraph_format.keep_with_next = True
    r = p.add_run(f"{meta['no']}  {meta['file']}")
    set_font(r, 14, bold=True, east="黑体")
    r2 = p.add_run(f"（{len(open(meta['path'], encoding='utf-8').read().splitlines())} 行）")
    set_font(r2, 9, color=(0x66, 0x66, 0x66))

    para(doc, "用途", 10.5, bold=True, before=6, after=2, keep=True, east="黑体")
    para(doc, meta["purpose"], 9.8, after=4, align=WD_ALIGN_PARAGRAPH.JUSTIFY)

    bullet(doc, "对应算法架构", meta["papers"])
    bullet(doc, "输入", meta["inputs"])
    bullet(doc, "输出", meta["outputs"])

    para(doc, "运行命令", 10.5, bold=True, before=6, after=2, keep=True, east="黑体")
    add_code(doc, meta["run"])

    if meta.get("notes"):
        para(doc, "口径提醒", 10.5, bold=True, before=6, after=2, keep=True, east="黑体")
        for n in meta["notes"]:
            bullet(doc, "注意", n)

    para(doc, "代码全文", 10.5, bold=True, before=8, after=2, keep=True, east="黑体")
    add_code(doc, open(meta["path"], encoding="utf-8").read())


def main():
    doc = Document()
    sec = doc.sections[0]
    sec.page_width, sec.page_height = Cm(21), Cm(29.7)
    sec.top_margin = sec.bottom_margin = Cm(2.0)
    sec.left_margin = sec.right_margin = Cm(1.6)
    add_page_number(sec)

    # ---------------- 封面
    para(doc, "", 10, before=120)
    para(doc, TITLE, 22, bold=True, align=WD_ALIGN_PARAGRAPH.CENTER, after=6, east="黑体")
    para(doc, SUBTITLE, 12, align=WD_ALIGN_PARAGRAPH.CENTER, after=18)
    para(doc, VERSION, 10, align=WD_ALIGN_PARAGRAPH.CENTER, after=4)
    para(doc, "收录 10 个分析脚本 + 13 个辅助/诊断/装配/环境脚本，共 5,700 余行", 9,
         align=WD_ALIGN_PARAGRAPH.CENTER, italic=True, after=2)
    para(doc, "所有代码均为实际运行版本，未做删改；中文注释保留原样", 9,
         align=WD_ALIGN_PARAGRAPH.CENTER, italic=True)

    # ---------------- 使用说明
    doc.add_page_break()
    para(doc, "0. 这份 PDF 是什么", 16, bold=True, before=0, after=8, east="黑体")
    para(doc, ("这份汇编把五套算法架构从原始数据到最终数字、表格与图表的代码按运行顺序完整收录，"
               "目的是让审稿人、合作者或下一位接手的人能对照算法架构逐段找到“这个数字是哪个脚本、哪一行算出来的”。"
               "每一节先说明脚本做什么、吃什么文件、吐什么结果，再贴代码全文。"), 10, after=6,
         align=WD_ALIGN_PARAGRAPH.JUSTIFY)

    para(doc, "0.1 怎么读", 12, bold=True, before=8, after=3, east="黑体")
    for t in ["第一次读：先看第 1 节的“代码总览”，知道一共有哪些脚本、各自对应哪套算法架构。",
              "要复现：按 2.1 → 2.8 的顺序跑 A/B/C；按 3.1 → 3.2 跑 D/E。",
              "要核对某个数字：先在算法架构里找到表/图编号，再到第 1 节的对照表找到脚本，最后在脚本里搜指标名。",
              "代码中的 $PY、$OLD_PY、$BASE、$DATA 是环境变量占位符，具体路径见《配置要求与复现说明》。"]:
        bullet(doc, "提示", t)

    para(doc, "0.2 运行环境（一句话版）", 12, bold=True, before=8, after=3, east="黑体")
    para(doc, ("A/B/C 的 LightGBM 与 TabPFN 在 scikit-learn 1.9.1 的新环境运行；LR 支路在 "
               "scikit-learn 1.7.2 的 D13 老环境复算，才能与归档锚点逐位一致。D/E 全部在新环境运行。"
               "两套环境的完整版本表、三条 SHA-256 与逐条命令见《配置要求与复现说明》第 2–6 节。"),
         10, after=6, align=WD_ALIGN_PARAGRAPH.JUSTIFY)

    para(doc, "0.3 收录边界（重要）", 12, bold=True, before=8, after=3, east="黑体")
    para(doc, ("本书收录服务器与本机上与该项目相关的全部 23 个脚本：10 个分析脚本 + 13 个辅助/诊断/装配/环境脚本。"
               "其中 A.2 跨队列迁移实验的结果接近随机，按“不合格的不写进去”的原则未进入任何一册正文；"
               "A.3、A.4 是一次性诊断脚本，不产生算法架构数字；A.5–A.6 是 LR 老环境的构建脚本与依赖清单；A.7–A.9 是前身项目 D13 的主脚本、审计与提交脚本（只作溯源，其数字不进入正文）。收进来是为了让读者看到全部跑过的代码，"
               "而不是只看到成功的那一部分——每个条目都注明了自己的用途与边界。"), 10, after=4,
         align=WD_ALIGN_PARAGRAPH.JUSTIFY)

    # ---------------- 总览
    doc.add_page_break()
    para(doc, "1. 代码总览", 16, bold=True, before=0, after=6, east="黑体")
    para(doc, "表 1. 脚本、行数与算法架构对应关系", 9, bold=True, align=WD_ALIGN_PARAGRAPH.CENTER, after=2)

    rows = []
    for m in SCRIPTS + APPENDIX_SCRIPTS:
        n = len(open(m["path"], encoding="utf-8").read().splitlines())
        rows.append([m["no"], m["file"], str(n), m["papers"]])
    tbl = doc.add_table(rows=1, cols=4)
    tbl.style = "Table Grid"
    tbl.alignment = 1
    hdr = ["编号", "脚本", "行数", "对应算法架构/用途"]
    widths = [2.0, 6.6, 1.8, 7.2]
    for j, h in enumerate(hdr):
        c = tbl.rows[0].cells[j]
        c.width = Cm(widths[j])
        pp = c.paragraphs[0]
        pp.alignment = WD_ALIGN_PARAGRAPH.CENTER
        r = pp.add_run(h)
        set_font(r, 9, bold=True)
    for row in rows:
        cells = tbl.add_row().cells
        for j, v in enumerate(row):
            cells[j].width = Cm(widths[j])
            pp = cells[j].paragraphs[0]
            pp.alignment = WD_ALIGN_PARAGRAPH.CENTER if j != 1 else WD_ALIGN_PARAGRAPH.LEFT
            r = pp.add_run(v)
            set_font(r, 8.5)

    para(doc, "", 6, after=4)
    para(doc, "1.1 算法架构—脚本—产出一览", 12, bold=True, before=6, after=3, east="黑体")
    mapping = [
        ("A 入院特征基准", "2.1 + 2.2 + 2.4 + 2.6 + 2.7 + 2.8", "表 1–4；图 2–7"),
        ("B 实验室增量", "2.1 + 2.2 + 2.4 + 2.6 + 2.7 + 2.8", "表 1–3；图 2–7"),
        ("C 并发症边界检验", "2.1 + 2.2 + 2.4 + 2.6 + 2.7 + 2.8", "表 1–3；图 2–7"),
        ("D 首次发作时点预测", "wenzhou_de.py + table1_wenzhou.py", "表 1、表 2；图 2–4"),
        ("E 抗癫痫药物分析", "wenzhou_de.py + table1_wenzhou.py", "表 1；图 2"),
    ]
    t2 = doc.add_table(rows=1, cols=3)
    t2.style = "Table Grid"
    t2.alignment = 1
    for j, h in enumerate(["算法架构", "核心脚本", "算法架构中的表/图"]):
        c = t2.rows[0].cells[j]
        c.width = Cm([5.0, 7.4, 5.2][j])
        pp = c.paragraphs[0]
        pp.alignment = WD_ALIGN_PARAGRAPH.CENTER
        r = pp.add_run(h)
        set_font(r, 9, bold=True)
    for row in mapping:
        cells = t2.add_row().cells
        for j, v in enumerate(row):
            cells[j].width = Cm([5.0, 7.4, 5.2][j])
            pp = cells[j].paragraphs[0]
            pp.alignment = WD_ALIGN_PARAGRAPH.LEFT if j == 0 else WD_ALIGN_PARAGRAPH.CENTER
            r = pp.add_run(v)
            set_font(r, 8.5)

    # ---------------- 正文
    doc.add_page_break()
    para(doc, "2. A / B / C：21,459 例公共队列", 16, bold=True, before=0, after=6, east="黑体")
    para(doc, ("A/B/C 共用一套基准管线：固定切分 → 嵌套子集 → 三模型训练 → 固定测试集评估 → 汇总出图。"
               "差别只在特征集：A 为 36 个入院特征，B 加 34 项实验室指标（70 个），C 再加 4 个卒中后并发症"
               "（74 个）。下面八个脚本按实际运行顺序排列。"), 10, after=4,
         align=WD_ALIGN_PARAGRAPH.JUSTIFY)
    for m in SCRIPTS[:8]:
        script_section(doc, m)

    doc.add_page_break()
    para(doc, "3. D / E：温州 167 例真实队列", 16, bold=True, before=0, after=6, east="黑体")
    para(doc, ("D/E 使用同一个单中心去标识队列（167 例，PSE 49 例，中位随访 592 天）。D 研究首次发作"
               "时点的预测，E 研究抗癫痫药物与晚期 PSE 的关联。所有分析在一个脚本内按 --task 分流，"
               "表 1 由独立脚本生成。"), 10, after=4, align=WD_ALIGN_PARAGRAPH.JUSTIFY)
    for m in SCRIPTS[8:]:
        script_section(doc, m)

    # ---------------- 附录
    doc.add_page_break()
    para(doc, "附录 A  环境自检脚本", 16, bold=True, before=0, after=6, east="黑体")
    script_section(doc, APPENDIX_SCRIPTS[0])

    doc.add_page_break()
    para(doc, "附录 B  脚本指纹", 16, bold=True, before=0, after=4, east="黑体")
    para(doc, ("下表给出本汇编收录的每个文件的 SHA-256 与行数。改动任何一个字符，指纹都会变；"
               "交接时先核对指纹，再谈复现。"), 9.8, after=4)
    files = [(m["file"], m["path"]) for m in SCRIPTS + APPENDIX_SCRIPTS]
    tb = doc.add_table(rows=1, cols=4)
    tb.style = "Table Grid"
    tb.alignment = 1
    for j, h in enumerate(["文件", "行数", "SHA-256（前 32 位）", "完整 SHA-256"]):
        c = tb.rows[0].cells[j]
        c.width = Cm([3.6, 1.4, 5.6, 7.0][j])
        pp = c.paragraphs[0]
        pp.alignment = WD_ALIGN_PARAGRAPH.CENTER
        r = pp.add_run(h)
        set_font(r, 8.5, bold=True)
    for name, path in files:
        n = len(open(path, encoding="utf-8").read().splitlines())
        digest = sha256(path)
        cells = tb.add_row().cells
        vals = [name, str(n), digest[:32], digest]
        for j, v in enumerate(vals):
            cells[j].width = Cm([3.6, 1.4, 5.6, 7.0][j])
            pp = cells[j].paragraphs[0]
            pp.alignment = WD_ALIGN_PARAGRAPH.LEFT if j in (0, 3) else WD_ALIGN_PARAGRAPH.CENTER
            r = pp.add_run(v)
            set_font(r, 7.2 if j >= 2 else 8)

    para(doc, "", 6, after=4)
    para(doc, "附录 C  未收录脚本说明", 16, bold=True, before=8, after=4, east="黑体")
    for name, why in EXCLUDED:
        bullet(doc, name, why)
    para(doc, ("这三类脚本不改变算法架构任何数字。若需要审计“所有跑过的代码”，它们仍在 server/ 目录中，"
               "与本汇编收录版本同源。"), 9.5, after=4, italic=True)

    para(doc, "附录 D  算法架构装配脚本", 16, bold=True, before=10, after=4, east="黑体")
    para(doc, ("以下两个脚本用于把结果装配成 docx/PDF，不属于统计分析。放在附录是为了在需要重新生成"
               "算法架构文件时不必另找。"), 9.8, after=4)
    for m in APPENDIX_SCRIPTS[1:]:
        script_section(doc, m)

    out = os.path.join(OUT, "五套算法架构代码汇编.docx")
    doc.save(out)
    print("saved", out)


if __name__ == "__main__":
    main()
