/* Single prediction report. All displayed scores come from the prediction response. */
const singlePercent = new Intl.NumberFormat("zh-CN", { style: "percent", maximumFractionDigits: 2 });
const singlePrecisePercent = new Intl.NumberFormat("zh-CN", { style: "percent", maximumFractionDigits: 4 });
const singlePoints = new Intl.NumberFormat("zh-CN", { maximumFractionDigits: 2 });
const validRisk = (value) => typeof value === "number" && Number.isFinite(value) && value >= 0 && value <= 1;
function formatRisk(value, thresholds) {
  if (!validRisk(value)) return "—";
  if (Array.isArray(thresholds) &&
      thresholds.some(threshold => value !== threshold && Math.abs(value - threshold) < .00005)) {
    return singlePrecisePercent.format(value);
  }
  return singlePercent.format(value);
}

function resultSection(title, ...children) {
  return el("section", { class: "single-result-section" }, el("h4", {}, title), ...children);
}

function riskOverview(result) {
  const risk = result.risk_730 ?? result.risk_730d;
  const thresholds = result.thresholds;
  const hasBands = Array.isArray(thresholds) && thresholds.length === 2 &&
    thresholds.every(validRisk) && thresholds[0] > 0 &&
    thresholds[0] < thresholds[1] && thresholds[1] < 1 && result.risk_level;
  const displayedRisk = formatRisk(risk, hasBands ? thresholds : undefined);
  const section = resultSection("730 天复发风险", el("div", { class: "single-risk-head" },
    el("strong", { class: "single-risk-value", title: validRisk(risk) ? singlePrecisePercent.format(risk) : null }, displayedRisk),
    hasBands ? el("span", { class: "single-risk-level" }, result.risk_level + " · 演示分档") : null));
  if (!hasBands) return section;

  const low = formatRisk(thresholds[0]);
  const high = formatRisk(thresholds[1]);
  const position = "left:" + risk * 100 + "%";
  const scale = " --low:" + thresholds[0] * 100 + "%; --high:" + thresholds[1] * 100 + "%";
  section.append(el("div", { class: "single-risk-scale", style: scale, role: "img",
    "aria-label": "风险 " + displayedRisk + "，" + result.risk_level + "，演示分档" },
  el("div", { class: "single-risk-track" }),
  el("span", { class: "single-risk-marker", style: position }),
  el("div", { class: "single-risk-ticks", "aria-hidden": "true" },
    el("span", {}, "0%"), el("span", { style: "left:" + thresholds[0] * 100 + "%" }, low),
    el("span", { style: "left:" + thresholds[1] * 100 + "%" }, high), el("span", {}, "100%"))));
  section.append(el("ul", { class: "single-risk-legend" },
    el("li", {}, "低危 < " + low), el("li", {}, "中危 " + low + "–" + high), el("li", {}, "高危 > " + high)),
  el("p", { class: "single-detail" }, "演示默认阈值，非临床标准。等级按上方概率直接换算。"));
  return section;
}

function featureExplanation(result) {
  const features = (result.top_features || []).filter(item =>
    Number.isFinite(item.impact) && item.impact >= 0 && ["+", "-", "0"].includes(item.direction));
  const section = resultSection("特征解释");
  if (!features.length) {
    section.append(el("p", { class: "single-detail" }, "本次接口未返回特征解释。"));
    return section;
  }

  const strongest = features.find(item => item.impact > 0 && item.direction !== "0");
  const summary = strongest
    ? "相对合成训练均值，" + strongest.name + "在本例中" +
      (strongest.direction === "+" ? "推高" : "降低") + "模型风险的幅度最大。"
    : "各字段对本例输出的影响接近零。";
  const maxImpact = Math.max(...features.map(item => item.impact), Number.EPSILON);
  const chart = el("div", { class: "single-impact-chart" },
    el("div", { class: "single-impact-key", "aria-hidden": "true" },
      el("span", {}, "← 降低"), el("span", {}, "推高 →")));
  for (const item of features) {
    const style = "--impact:" + item.impact / maxImpact * 50 + "%";
    const direction = item.direction === "+" ? "up" : item.direction === "-" ? "down" : "zero";
    const magnitude = (item.direction === "0" ? "" : item.direction) + singlePoints.format(item.impact * 100) + " 个百分点";
    chart.append(el("div", { class: "single-impact-row" },
      el("span", { class: "single-feature-name" }, item.name),
      el("span", { class: "single-impact-axis", "aria-hidden": "true" },
        el("span", { class: "single-impact-bar " + direction, style })),
      el("span", { class: "single-impact-number " + direction }, magnitude)));
  }

  section.append(el("p", { class: "single-summary" }, summary), chart,
    el("p", { class: "single-detail" }, "参照风险 " + formatRisk(result.baseline_risk) +
      "。条长表示对本例模型概率的贡献。风险差异 ≠ 治疗效果，特征方向不代表因果。"));
  if (result.global_features?.length) {
    section.append(el("details", { class: "single-global-features" },
      el("summary", {}, "模型整体特征排名 · 前 5"),
      el("p", { class: "single-detail" }, "按标准化逻辑回归系数的绝对值排序。"),
      el("ol", {}, ...result.global_features.map(item => el("li", {},
        el("span", {}, item.name), el("span", { class: "num" }, item.weight.toFixed(3)))))));
  }
  return section;
}

function riskTimeline(result) {
  const end = (result.risk_curve || []).find(point => point.t === 730 && validRisk(point.risk));
  const displayedRisk = end ? formatRisk(end.risk, result.thresholds) : "—";
  const milestones = el("div", { class: "single-timeline" });
  for (const day of [30, 90, 365, 730]) {
    const available = day === 730 && end;
    milestones.append(el("div", { class: available ? "single-time active" : "single-time" },
      el("span", { class: "single-time-dot", "aria-hidden": "true" }),
      el("strong", {}, day + " 天"),
      el("span", {}, available ? displayedRisk : "未输出")));
  }
  let plot;
  if (end) {
    const ns = "http://www.w3.org/2000/svg";
    const svg = (tag, attrs, label) => {
      const item = document.createElementNS(ns, tag);
      for (const [key, value] of Object.entries(attrs)) item.setAttribute(key, value);
      if (label) item.textContent = label;
      return item;
    };
    const left = 62, right = 473, top = 15, bottom = 102;
    plot = svg("svg", { class: "single-risk-plot", viewBox: "0 0 530 132", role: "img",
      "aria-label": "730 天模型风险 " + displayedRisk + "。其余时间节点无模型输出。" });
    for (const probability of [0, .5, 1]) {
      const y = bottom - (bottom - top) * probability;
      plot.append(svg("line", { x1: left, x2: right, y1: y, y2: y }),
        svg("text", { x: left - 9, y: y + 4, "text-anchor": "end" }, formatRisk(probability)));
    }
    for (const day of [30, 90, 365, 730]) {
      const x = left + (right - left) * day / 730;
      plot.append(svg("line", { x1: x, x2: x, y1: bottom, y2: bottom + 5 }),
        svg("text", { x, y: 124, "text-anchor": "middle" }, day + " 天"));
    }
    const y = bottom - (bottom - top) * end.risk;
    plot.append(svg("line", { x1: right, x2: right, y1: y, y2: bottom, class: "endpoint-guide" }),
      svg("circle", { cx: right, cy: y, r: 5, class: "endpoint" }),
      svg("text", { x: right - 12, y: y - 8, "text-anchor": "end", class: "endpoint" }, displayedRisk));
  }
  return resultSection("时间与风险",
    el("p", { class: "single-detail" }, "仅 730 天为模型真实输出。当前版本未提供多时间点曲线或置信区间。"),
    plot, milestones);
}

function reverseComparison(result) {
  const rows = el("tbody");
  for (const entry of result.scenarios || []) {
    const change = entry.changes?.find(item => item.feature === "planned_reduction_pct");
    if (!change || !Number.isFinite(change.to) || !validRisk(entry.new_risk)) continue;
    const initial = Number.isFinite(change.from) ? singlePoints.format(change.from) + "%" : "—";
    rows.append(el("tr", {}, el("td", {}, initial + " → " + singlePoints.format(change.to) + "%"),
      el("td", { class: "num" }, formatRisk(entry.new_risk))));
  }
  return resultSection("逆向情景 · 关联对比",
    el("div", { class: "single-reverse-head" },
      el("div", {}, el("span", {}, "目标风险"), el("strong", {}, formatRisk(result.target_risk))),
      el("div", {}, el("span", {}, "录入情景的模型风险"), el("strong", {}, formatRisk(result.reference_risk)))),
    el("p", { class: "single-detail" }, "独立教学模型。在训练支持范围内，比较不同减量幅度的模型输出。"),
    rows.childElementCount ? el("div", { class: "table-wrap" }, el("table", { class: "tbl single-scenarios" },
      el("thead", {}, el("tr", {}, el("th", { scope: "col" }, "减量幅度 · 录入值 → 候选值"),
        el("th", { scope: "col" }, "候选情景模型风险"))), rows)) : null,
    el("div", { class: "single-reverse-fields" },
      el("span", { class: "tag" }, "演示可变项 · 减量幅度"),
      el("span", { class: "tag fixed" }, "固定项 · 年龄、病程等病史字段")),
    el("p", { class: "single-detail" }, "可修改表单中的计划减药幅度后重新提交，比较录入情景。风险差异 ≠ 治疗效果。"));
}

function printSingleResult(report) {
  if (document.querySelector(".single-print-sheet")) return;
  const copy = report.cloneNode(true);
  copy.removeAttribute("id");
  copy.classList.add("single-print-sheet");
  copy.querySelector(".single-result-actions")?.remove();
  copy.querySelectorAll("details").forEach((details) => { details.open = true; });
  copy.prepend(el("div", { class: "single-print-watermark", "aria-hidden": "true" },
    report.dataset.provenance === "real-research" ? "真实队列 · 研究演示" : "合成数据"));
  document.body.append(copy);
  document.body.classList.add("printing-single-result");
  window.addEventListener("afterprint", () => {
    document.body.classList.remove("printing-single-result");
    copy.remove();
  }, { once: true });
  window.print();
}

function forwardModelEvidence(result) {
  const studies = [
    ["A", "入院资料基准", "21,459 例公共卒中队列；用 36 项入院特征比较逻辑回归、LightGBM 与 TabPFN。"],
    ["B", "实验室特征增量", "同一公共队列增加 34 项实验室指标；原始数据缺少采样时间戳，入院时可用性仍需核实。"],
    ["C", "并发症边界检验", "检验 4 项卒中后并发症的增量；强调预测时点之后的信息可能造成时间泄漏。"],
    ["D", "首次发作时点预测", "167 例卒中后早期发作队列；比较 8 项核心变量与 24 项扩展变量，仍需独立外部验证。"],
    ["E", "用药观察分析", "同一 167 例队列分析早期用药与晚期卒中后癫痫；观察性结果不代表治疗因果效果。"],
  ];
  return el("section", { class: "single-model-card", "aria-labelledby": "single-model-title" },
    el("div", { class: "single-model-heading" },
      el("h4", { id: "single-model-title" }, "使用模型")),
    el("p", { class: "single-model-name" }, "减药后 730 天复发预测"),
    el("p", { class: "single-model-method" }, "逻辑回归 · 8 项输入 · 合成数据训练"),
    el("dl", { class: "single-model-facts" },
      el("div", {}, el("dt", {}, "模型版本"), el("dd", { class: "mono" }, result.model_version || "—")),
      el("div", {}, el("dt", {}, "训练支持范围"), el("dd", {}, result.in_support ? "范围内" : "范围外"))),
    el("div", { class: "single-theory" },
      el("div", { class: "single-theory-heading" },
        el("h5", {}, "理论依据"),
        el("a", { href: "https://pubmed.ncbi.nlm.nih.gov/28483337/", target: "_blank", rel: "noopener noreferrer" }, "查看原始研究 ↗")),
      el("p", { class: "single-theory-highlight" }, "8 项变量参考减药后复发研究；本模型未复现原研究，也未经临床验证。")),
    el("details", { class: "single-research-details" },
      el("summary", {}, "卒中后癫痫研究 A–E"),
      el("p", { class: "single-research-note" }, "以下研究的预测人群和终点与本页减药后复发模型不同，不用于解释本次概率。"),
      el("ol", { class: "single-study-list" }, ...studies.map(([letter, title, description]) =>
        el("li", {}, el("span", { class: "single-study-letter" }, letter),
          el("div", {}, el("strong", {}, title), el("p", {}, description))))),
      el("p", { class: "single-research-sources" },
        "资料：A–E 中英文方案、《卒中后癫痫五套算法架构·跑数结果汇编》及《配置要求与复现说明》。")));
}

function renderSingleResult(box, result) {
  const report = el("article", { class: "single-report", "aria-labelledby": "single-report-title" },
    el("header", { class: "single-report-header" },
      el("div", {}, el("span", { class: "single-report-badge" }, "合成数据"),
        el("h3", { id: "single-report-title", tabindex: "-1" },
          result.scenario === "reverse" ? "单例逆向情景结果" : "单例预测结果")),
      el("div", { class: "single-result-actions" },
        el("button", { class: "btn btn-outline btn-sm", type: "button", onclick: () => printSingleResult(report) },
          "打印 / 存为 PDF"))),
    el("p", { class: "single-report-disclaimer" }, result.disclaimer ||
      "本结果基于合成数据，仅供工程联调，不作为减药或临床决策依据。"));

  if (result.scenario === "reverse") report.append(reverseComparison(result));
  else report.append(riskOverview(result), featureExplanation(result), riskTimeline(result));
  if (result.scenario === "reverse") {
    report.append(el("dl", { class: "single-model-info" },
      el("dt", {}, "训练支持范围"), el("dd", {}, result.in_support ? "范围内" : "范围外"),
      el("dt", {}, "模型版本"), el("dd", { class: "mono" }, result.model_version || "—")));
  } else {
    report.append(forwardModelEvidence(result));
  }
  box.append(report);
  report.querySelector("h3").focus({ preventScroll: true });
  box.scrollIntoView({ block: "start", behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "instant" : "smooth" });
}

function researchRiskOverview(scenario, probability) {
  const title = scenario === "first" ? "随访期间晚期 PSE 模型估计" : "一年内继发性癫痫模型估计";
  const percent = formatRisk(probability);
  return resultSection(title,
    el("div", { class: "single-risk-head" },
      el("strong", { class: "single-risk-value", title: singlePrecisePercent.format(probability) }, percent),
      el("span", { class: "single-risk-level" }, "研究演示 · 未设临床分档")),
    el("div", { class: "single-risk-scale", role: "img", "aria-label": `模型估计 ${percent}，无临床风险分档` },
      el("div", { class: "single-risk-track unbanded" }),
      el("span", { class: "single-risk-marker", style: `left:${probability * 100}%` }),
      el("div", { class: "single-risk-ticks", "aria-hidden": "true" },
        el("span", {}, "0%"), el("span", {}, "100%"))),
    el("p", { class: "single-detail" }, "横条只标示模型输出在 0–100% 中的位置；没有经过验证的低、中、高风险阈值。"));
}

function researchFeatureExplanation(bundle, values, probability, estimate) {
  const contributions = bundle.feature_order.map(name => {
    const alternate = { ...values, [name]: bundle.medians[name] };
    return { name, delta: probability - estimate(alternate) };
  }).filter(item => Number.isFinite(item.delta) && Math.abs(item.delta) > 1e-8)
    .sort((a, b) => Math.abs(b.delta) - Math.abs(a.delta)).slice(0, 6);
  const section = resultSection("特征解释 · 相对训练中位数");
  if (!contributions.length) {
    section.append(el("p", { class: "single-detail" }, "本例输入与训练中位数参考值接近，没有可展示的单字段差异。"));
    return section;
  }
  const largest = contributions[0];
  section.append(el("p", { class: "single-summary" },
    `在这组输入下，${bundle.labels[largest.name] || largest.name}与训练中位数的差异，对模型输出的影响幅度最大。`));
  const max = Math.max(...contributions.map(item => Math.abs(item.delta)));
  const chart = el("div", { class: "single-impact-chart" },
    el("div", { class: "single-impact-key", "aria-hidden": "true" },
      el("span", {}, "← 降低"), el("span", {}, "推高 →")));
  for (const item of contributions) {
    const direction = item.delta > 0 ? "up" : "down";
    chart.append(el("div", { class: "single-impact-row" },
      el("span", { class: "single-feature-name" }, bundle.labels[item.name] || item.name),
      el("span", { class: "single-impact-axis", "aria-hidden": "true" },
        el("span", { class: `single-impact-bar ${direction}`,
          style: `--impact:${Math.abs(item.delta) / max * 50}%` })),
      el("span", { class: `single-impact-number ${direction}` },
        `${item.delta > 0 ? "+" : "−"}${singlePoints.format(Math.abs(item.delta) * 100)} 个百分点`)));
  }
  section.append(chart, el("p", { class: "single-detail" },
    "每次只把一个字段替换为训练中位数，其余输入保持不变；各条差值不能相加，也不代表治疗或其他因果效果。"));
  return section;
}

function researchTimeline(scenario, probability) {
  const days = [30, 90, 365, 730];
  const endpoint = scenario === "stroke" ? 365 : null;
  const description = scenario === "stroke"
    ? "D13 仅有一年内二分类标签；只有 365 天对应模型输出，30、90、730 天均未建模。没有事件时间或风险曲线。"
    : "温州 D 队列的个体随访长度不同；模型预测的是随访期间是否发生晚期 PSE，没有固定时间点风险或风险曲线。";
  const milestones = el("div", { class: "single-timeline" });
  for (const day of days) {
    const available = day === endpoint;
    milestones.append(el("div", { class: available ? "single-time active" : "single-time" },
      el("span", { class: "single-time-dot", "aria-hidden": "true" }),
      el("strong", {}, `${day} 天`),
      el("span", {}, available ? formatRisk(probability) : "未输出")));
  }
  return resultSection("时间与风险", el("p", { class: "single-detail" }, description), milestones);
}

function researchModelEvidence(scenario, bundle, config) {
  const first = scenario === "first";
  const title = first ? "首次发作后晚期 PSE 预测" : "卒中后癫痫一年内结局预测";
  const method = first ? "核心 8 变量逻辑回归 · 温州 167 例真实去标识队列" :
    "28 变量逻辑回归 + Platt 校准 · D13 公开真实队列";
  const n = first ? "167 例，49 例结局事件" : "21,457 例成人筛选记录，内部测试集 4,226 例";
  const highlight = first
    ? "按 D 研究的预处理与逻辑回归口径重训全队列参数；5 折 × 10 次交叉验证的 AUROC 0.7101、AUPRC 0.5331、Brier 0.1825 已复算，与交付汇编一致。"
    : "使用已交付的 D13-S1-LR-Platt-v0.3 冻结参数；结局仅为筛选队列的一年内二分类标签，不能替代首次晚期无诱因发作的时间结局。";
  return el("section", { class: "single-model-card", "aria-labelledby": "single-model-title" },
    el("div", { class: "single-model-heading" }, el("h4", { id: "single-model-title" }, "使用模型")),
    el("p", { class: "single-model-name" }, title),
    el("p", { class: "single-model-method" }, method),
    el("dl", { class: "single-model-facts" },
      el("div", {}, el("dt", {}, "模型版本"), el("dd", { class: "mono" }, bundle.model_id)),
      el("div", {}, el("dt", {}, "训练队列"), el("dd", {}, n)),
      el("div", {}, el("dt", {}, "字段范围"), el("dd", {}, "本次输入已通过原始取值范围检查"))),
    el("div", { class: "single-theory" },
      el("div", { class: "single-theory-heading" },
        el("h5", {}, "研究依据"),
        el("a", { href: config.source, target: "_blank", rel: "noopener noreferrer" }, "查看模型证据 ↗")),
      el("p", { class: "single-theory-highlight" }, highlight)),
    el("p", { class: "single-detail" }, "训练范围检查不等于外部验证；本页只供研究演示，不用于临床决策。"));
}

function renderResearchResult(box, scenario, bundle, config, values, probability, estimate) {
  const report = el("article", { class: "single-report", "aria-labelledby": "single-report-title",
      "data-provenance": "real-research" },
    el("header", { class: "single-report-header" },
      el("div", {}, el("span", { class: "single-report-badge real-research" }, "真实队列研究"),
        el("h3", { id: "single-report-title", tabindex: "-1" }, "单例预测结果")),
      el("div", { class: "single-result-actions" },
        el("button", { class: "btn btn-outline btn-sm", type: "button",
          onclick: () => printSingleResult(report) }, "打印 / 存为 PDF"))),
    el("p", { class: "single-report-disclaimer" },
      "本结果来自真实研究队列的模型，仅供研究演示；未经外部临床验证，不作为诊疗决策依据。"),
    researchRiskOverview(scenario, probability),
    researchFeatureExplanation(bundle, values, probability, estimate),
    researchTimeline(scenario, probability),
    researchModelEvidence(scenario, bundle, config));
  box.append(report);
  report.querySelector("h3").focus({ preventScroll: true });
  box.scrollIntoView({ block: "start", behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "instant" : "smooth" });
}

