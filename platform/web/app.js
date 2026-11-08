/* 院内数据接入平台 · 前端（方案 §5）
   身份桩：X-Demo-User / X-Demo-Role / X-Demo-Scope，生产接医院统一身份认证。 */
const $ = (s) => document.querySelector(s);
const $$ = (s) => Array.from(document.querySelectorAll(s));

const state = {
  meta: null,
  actor: JSON.parse(localStorage.getItem("qw-actor") || "null") || {
    user: "hosp-user", role: "importer", scope: "neuro-epilepsy",
  },
  view: "hub",
  importId: null,
  fileSha: "",
  retainedUntil: null,
  importCreatedBy: "",
  validation: null,
  proposed: null,
  mapping: {},
  mappingVersion: null,
  confirmed: false,
  runId: null,
  poll: null,
  page: 1,
  pageSize: 50,
  scenario: "forward",
  researchScenario: null,
  researchBundle: null,
  step: 1,
  maxStep: 1,
  uploading: false,
  uploadFailed: false,
};

const CRUMBS = {
  hub: ["01", "研究路径"], flow: ["03", "批量数据接入"], single: ["04", "单例结构化录入"],
  history: ["05", "历史任务"], audit: ["06", "审计与安全"], plan: ["07", "方案文档"],
};

const RESEARCH_MODELS = {
  first: {
    name: "首次发作", label: "卒中后早期首次发作 · 温州 D 研究",
    description: "卒中后 7 天内首次急性症状性发作后，录入 8 项特征，预测随后晚期 PSE 的研究结局。",
    bundleUrl: "/static/first-seizure/model_bundle.json",
    sha256: "fd67d26eb948bff652a19b0822e48e85d8a737d5fb5b7d251e17e8612d2add27",
    modelId: "WENZHOU-D-CORE8-LR-FULL-2026-11-08",
    displayOrder: ["age", "stroke_type", "interval_gt3", "multiple_seizures", "status_epilepticus", "nihss", "cortical", "eeg_epileptic"],
    outcome: "温州 D 队列随访期间晚期 PSE 二分类结局。随访时间不一致，本结果没有固定的 1 年或 2 年时间含义。",
    source: "/knowledge-graph/assets/sources/五套算法架构_跑数结果汇编.pdf",
  },
  stroke: {
    name: "卒中后癫痫", label: "卒中后癫痫 · D13 公开队列",
    description: "录入 28 项 D13 原始编码特征，预测筛选队列一年内继发性癫痫二分类标签。",
    bundleUrl: "/static/d13-research/model_bundle.json",
    sha256: "60896dd26ae944f2a89aa13b8a910d8cf7a4d01504c0ccc8efe2a032f9976421",
    modelId: "D13-S1-LR-Platt-v0.3",
    displayOrder: ["age", "gender", "nihss", "uremia", "fatty_liver", "diabetes", "hypertension", "coronary_disease", "atrial_fibrillation", "hyperuricemia", "hyperlipidaemia", "frontal_lobe", "parietal_lobe", "temporal_lobe", "occipital_lobe", "insular_lobe", "subcortex_lobe", "aca", "mca", "pca", "va", "ba", "cca_plaque", "ica_plaque", "eca_plaque", "ant_circle", "post_circle", "large_ves_as"],
    outcome: "D13 筛选队列一年内继发性癫痫标签的校准估计；公开数据经上游插补，未经外部临床验证。",
    source: "/knowledge-graph/assets/sources/D13_v0.3_模型卡.md",
  },
};

/* ------------------------------------------------------------------ 工具 */
function headers(extra) {
  return {
    "X-Demo-User": state.actor.user,
    "X-Demo-Role": state.actor.role,
    "X-Demo-Scope": state.actor.scope,
    ...(extra || {}),
  };
}

async function api(method, path, opts = {}) {
  const init = { method, headers: headers(opts.headers || {}) };
  if (opts.json !== undefined) {
    init.headers["Content-Type"] = "application/json";
    init.body = JSON.stringify(opts.json);
  } else if (opts.form !== undefined) {
    init.body = opts.form;
  }
  const res = await fetch(path, init);
  const ctype = res.headers.get("content-type") || "";
  if (opts.raw) return { status: res.status, blob: await res.blob() };
  const body = ctype.includes("application/json") ? await res.json() : await res.text();
  return { status: res.status, body };
}

function toast(msg, kind = "", ms = 4200) {
  const t = $("#toast");
  t.textContent = msg;
  t.className = `toast ${kind}`;
  clearTimeout(t._h);
  t._h = setTimeout(() => t.classList.add("hidden"), ms);
}

function fmtErr(body, status) {
  if (!body || typeof body !== "object") return `HTTP ${status}`;
  const code = body.code || "";
  return `${code ? code + " · " : ""}${body.message || "请求失败"}${
    body.details ? " — " + JSON.stringify(body.details).slice(0, 220) : ""}`;
}

function esc(v) {
  return String(v === null || v === undefined ? "" : v)
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function el(tag, attrs = {}, ...kids) {
  const n = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === "class") n.className = v;
    else if (k === "html") n.innerHTML = v;
    else if (k.startsWith("on")) n.addEventListener(k.slice(2), v);
    else if (v !== null && v !== undefined) n.setAttribute(k, v);
  }
  for (const k of kids) {
    if (k === null || k === undefined) continue;
    n.append(k.nodeType ? k : document.createTextNode(String(k)));
  }
  return n;
}

function num(v, d = 4) {
  return v === null || v === undefined || v === "" ? "—" : Number(v).toFixed(d).replace(/\.?0+$/, "");
}

function ts(t) {
  return t ? new Date(t * 1000).toLocaleString("zh-CN", { hour12: false }) : "—";
}

/* ------------------------------------------------------------------ 导航 */
function nav(view) {
  state.view = view;
  $$(".view").forEach((v) => v.classList.add("hidden"));
  $(`#view-${view}`).classList.remove("hidden");
  const [n, label] = CRUMBS[view] || ["01", "HUB"];
  $("#crumbNum").textContent = n;
  $("#crumbLabel").textContent = label;
  $$(".header-menu").forEach((menu) => { menu.open = false; });
  window.scrollTo({ top: 0, behavior: view === "single" ? "instant" : "smooth" });
}

function stepAvailable(step) {
  return step === 1 || (step <= state.maxStep && [false, true, !!state.importId && !state.uploadFailed,
    !!state.mappingVersion, state.confirmed, !!state.runId][step]);
}

function setStep(active, advance = true) {
  if (!advance && !stepAvailable(active)) return;
  if (advance) state.maxStep = Math.max(state.maxStep, active);
  state.step = active;
  $$("#steps li").forEach((li) => {
    const s = Number(li.dataset.step);
    li.classList.toggle("active", s === active);
    li.classList.toggle("done", s < state.maxStep && stepAvailable(s));
    li.querySelector("button").disabled = !stepAvailable(s);
    if (s === active) li.querySelector("button").setAttribute("aria-current", "step");
    else li.querySelector("button").removeAttribute("aria-current");
  });
  for (let i = 1; i <= 5; i++) $(`#panel-${i}`).classList.toggle("hidden", i !== active);
  $("#btnFlowNext").disabled = !stepAvailable(2);
  $("#btnSaveMap").disabled = state.confirmed;
  $("#btnAutoMap").disabled = state.confirmed;
  $$("#mapTable select").forEach((select) => { select.disabled = state.confirmed; });
}

function resetFlow() {
  state.importId = null; state.validation = null; state.proposed = null;
  state.mapping = {}; state.mappingVersion = null; state.confirmed = false;
  state.runId = null; state.page = 1;
  state.step = 1; state.maxStep = 1;
  state.uploadFailed = false;
  if (state.poll) clearInterval(state.poll);
  state.poll = null;
  ["#precheckBox", "#runBox", "#exportBox", "#resultToolbar"].forEach((s) => {
    $(s).innerHTML = ""; $(s).classList.add("hidden");
  });
  $("#resultTable thead").innerHTML = ""; $("#resultTable tbody").innerHTML = "";
  $("#pager").innerHTML = "";
  $("#flowPurposeTag").textContent = "用途：—";
  $("#uploadStatus").textContent = "选择文件后，开始自动预检";
  $("#btnFlowNext").disabled = true;
  ["#mapHint", "#confirmHint", "#runHint"].forEach((s) => { $(s).textContent = ""; });
}

/* --------------------------------------------------------------- 身份桩 */
function renderActor() {
  const sel = $("#actorRole");
  sel.innerHTML = "";
  for (const [k, label] of Object.entries(state.meta?.roles || { importer: "导入员" })) {
    sel.append(el("option", { value: k, selected: k === state.actor.role ? "" : null }, label));
  }
  $("#actorUser").value = state.actor.user;
  $("#actorScope").value = state.actor.scope;
  $("#actorBadge").textContent =
    `${state.actor.scope === "neuro-epilepsy" ? "神经内科" : state.actor.scope} · ${state.meta?.roles?.[state.actor.role] || state.actor.role}`;
  $("#actorBadge").title = `${state.actor.user} · ${state.actor.scope}`;
}

function bindActor() {
  const save = () => {
    state.actor = { user: $("#actorUser").value.trim() || "demo-user",
                    role: $("#actorRole").value,
                    scope: $("#actorScope").value.trim() || "neuro-epilepsy" };
    localStorage.setItem("qw-actor", JSON.stringify(state.actor));
    renderActor();
  };
  ["#actorUser", "#actorScope"].forEach((s) => $(s).addEventListener("change", save));
  $("#actorRole").addEventListener("change", save);
}

/* ------------------------------------------------------------------ hub */
function renderHub() {
  const m = state.meta;
  const c2 = m.config.channel2_envelope;
  $("#hubNote").innerHTML =
    `正向预测与逆向设计使用<b style="color:var(--txt2)">内置教学合成数据</b>；` +
    `「导入自己的数据」用于接入<b style="color:var(--green)">医院真实 CSV</b>——` +
    `文件只落在院内服务器，课题组不取得生产数据、账号或密钥。` +
    (m.config.reverse_enabled ? "" : " <b style='color:var(--amber)'>逆向设计当前已关闭。</b>");
  const sha = (m.model_sha256 || {})[Object.keys(m.model_sha256 || {})[0]] || "";
  $("#hubMeta").innerHTML = "";
  const cards = [
    ["schema_version", m.schema_version],
    ["model_version", m.model_version],
    ["model_sha256", sha ? sha.slice(0, 24) + "…" : "—"],
    ["signature_valid", m.signature_valid ? "已校验" : "校验失败（E402）"],
    ["边界二", c2 ? "信封加密 HTTP（方案B）" : "同机进程内（方案A）"],
    ["逆向设计", m.config.reverse_enabled ? "启用 · RESEARCH_ONLY" : "关闭"],
    ["链接入口", (m.config.link_whitelist || []).length ? "白名单已配置" : "D4 默认关闭"],
    ["数据留存", `${m.retention_days} 天后自动清理`],
    ["上限", `${(m.limits.max_bytes / 1048576).toFixed(0)}MB / ${m.limits.max_rows.toLocaleString()} 行`],
  ];
  for (const [k, v] of cards) {
    $("#hubMeta").append(el("div", {}, el("b", {}, k), el("span", {}, v)));
  }
}

/* --------------------------------------------------------------- 预检渲染 */
function codeChip(code, count, codes) {
  const c = el("span", { class: "chip err", title: codes[code] || "" }, `${code}${count ? ` ×${count}` : ""}`);
  c.addEventListener("click", () => showModal(
    `<b>${code}</b> · ${esc(codes[code] || "未登记")}<br><br>` +
    `<span style="color:var(--txt3)">拒绝码语义见方案 §7.3；被拒绝的行不返回默认风险值。</span>`));
  return c;
}

function renderPrecheck(v, up) {
  const box = $("#precheckBox");
  box.classList.remove("hidden");
  box.innerHTML = "";
  const codes = state.meta.reject_codes;
  const okAll = v.ok && !v.unmapped_required.length;

  box.append(el("div", { class: "stat-grid" },
    stat("总行数", v.total_rows), stat("可运行", v.runnable_rows, "ok"),
    stat("被拒绝", v.rejected_rows, v.rejected_rows ? "bad" : ""),
    stat("编码", v.encoding || "—"), stat("列数", v.columns.length),
    stat("批次状态", up.stage, up.stage === "READY" ? "ok" : "warn")));

  if (v.forbidden_hits?.length) {
    box.append(el("div", { class: "row" },
      el("span", { class: "chip err" }, `疑似直接标识符列：${v.forbidden_hits.join(", ")}`),
      el("span", { class: "hint" }, "命中即拒绝该列并告警；请院内脱敏后重新导出（方案 §9.1）")));
  }
  if (v.unmapped_required?.length) {
    box.append(el("div", { class: "row" },
      el("span", { class: "chip warn" }, `未映射的标准字段：${v.unmapped_required.join(", ")}`),
      el("span", { class: "hint" }, "去步骤 ② 建立映射，由审核员保存为映射版本")));
  }

  const seen = v.codes_seen || {};
  const chips = Object.entries(seen).map(([c, n]) => codeChip(c, n, codes));
  if (chips.length) {
    box.append(el("div", { class: "row" }, el("span", { class: "lbl" }, "拒绝码分布"),
      el("div", { class: "chips" }, ...chips)));
  }

  const stats = v.column_stats || {};
  if (Object.keys(stats).length) {
    box.append(el("div", { class: "lbl", style: "margin-top:14px" }, "列级统计（仅聚合值，不含病历原文）"));
    const t = el("table", { class: "tbl" },
      el("thead", {}, el("tr", {}, ...["字段", "类型", "n", "最小", "中位", "最大", "均值/分布"].map((h) => el("th", {}, h)))));
    const tb = el("tbody");
    for (const [name, s] of Object.entries(stats)) {
      tb.append(el("tr", {},
        el("td", { class: "mono" }, name), el("td", {}, s.kind),
        el("td", { class: "num" }, s.n),
        el("td", { class: "num" }, s.kind === "tri" ? "—" : num(s.min)),
        el("td", { class: "num" }, s.kind === "tri" ? "—" : num(s.p50)),
        el("td", { class: "num" }, s.kind === "tri" ? "—" : num(s.max)),
        el("td", { class: "num" }, s.kind === "tri" ? `1:${s.ones} / 0:${s.zeros}` : num(s.mean))));
    }
    t.append(tb);
    box.append(el("div", { class: "table-wrap" }, t));
  }

  const errs = v.errors || [];
  if (errs.length) {
    box.append(el("div", { class: "lbl", style: "margin-top:14px" },
      `逐行错误（显示前 ${Math.min(errs.length, 200)} 条${v.errors_truncated ? "，已截断" : ""}）`));
    const t = el("table", { class: "tbl" },
      el("thead", {}, el("tr", {}, ...["行号", "字段", "码", "含义"].map((h) => el("th", {}, h)))));
    const tb = el("tbody");
    for (const e of errs.slice(0, 200)) {
      tb.append(el("tr", {}, el("td", { class: "num" }, e.line || "批次"),
        el("td", { class: "mono" }, e.field), el("td", { class: "mono st-REJECTED" }, e.code),
        el("td", {}, e.message)));
    }
    t.append(tb);
    box.append(el("div", { class: "table-wrap" }, t));
  }

  box.append(el("div", { class: "actions" },
    el("span", { class: "hint" },
      okAll ? "预检通过，进入映射与确认" : "存在需人工处理的项；未确认前不得进入推理队列")));
}

function stat(label, value, kind = "") {
  return el("div", { class: `stat ${kind}` }, el("b", {}, String(value)), el("span", {}, label));
}

function showModal(html) {
  $$(".header-menu").forEach((menu) => { menu.open = false; });
  $("#modalBody").innerHTML =
    html + `<div class="actions"><button class="btn btn-outline btn-sm" onclick="hideModal()">关闭</button></div>`;
  $("#modal").classList.remove("hidden");
}
function hideModal() { $("#modal").classList.add("hidden"); }

/* --------------------------------------------------------------- 启动 */
async function boot() {
  const r = await api("GET", "/api/v1/meta/versions");
  if (r.status !== 200) { toast("无法读取平台元数据：" + fmtErr(r.body, r.status), "err"); return; }
  state.meta = r.body;
  $("#banner").textContent = "教学合成模型 · 仅供研究联调，不用于临床决策";
  $("#fileLimitHint").textContent = `支持 .csv 格式，文件不超过 ${(state.meta.limits.max_bytes / 1048576).toFixed(0)} MB`;
  $("#linkNote").textContent = state.meta.config.link_whitelist?.length
    ? "仅支持管理员配置的内网白名单地址。" : "当前未开放内网链接读取，请使用文件上传。";
  renderActor(); bindActor(); renderHub();
  const params = new URLSearchParams(location.search);
  const scenario = params.get("scenario") === "reverse" ? "reverse" : "forward";
  const researchScenario = params.get("view") === "single" && RESEARCH_MODELS[params.get("scenario")]
    ? params.get("scenario") : null;
  $("#purpose").value = scenario === "reverse" ? "reverse" : "prediction";
  updatePurpose();
  if (params.get("view") === "single") {
    state.scenario = scenario;
    state.researchScenario = researchScenario;
    $("#singleScenario").value = scenario;
    if (researchScenario) setupResearchPresentation();
    navTo("single");
    if (researchScenario) loadResearchBundle(researchScenario);
  } else if (params.get("view") === "flow") {
    resetFlow(); state.scenario = scenario;
    $("#purpose").value = scenario === "reverse" ? "reverse" : "prediction";
    $("#runScenario").value = scenario;
    nav("flow"); setStep(1);
  } else {
    nav("hub");
  }
}

document.addEventListener("DOMContentLoaded", () => {
  boot();
  $("#modal").addEventListener("click", (e) => { if (e.target.id === "modal") hideModal(); });
  $("#btnBack").addEventListener("click", () => { location.assign("/"); });
  $("#btnDemo").addEventListener("click", showConfig);
  $("#btnPlan").addEventListener("click", showPlan);
  $$("[data-hub]").forEach((b) => b.addEventListener("click", () => hubClick(b.dataset.hub)));
  $$("[data-nav]").forEach((b) => b.addEventListener("click", () => navTo(b.dataset.nav)));
  $("#steps").addEventListener("click", (e) => {
    const li = e.target.closest("li");
    if (li) setStep(Number(li.dataset.step), false);
  });
  $$("[data-go-step]").forEach((b) => b.addEventListener("click", () => setStep(Number(b.dataset.goStep), false)));
  document.addEventListener("click", (e) => {
    $$(".header-menu[open]").forEach((menu) => { if (!menu.contains(e.target)) menu.open = false; });
  });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") {
      hideModal(); $$(".header-menu").forEach((menu) => { menu.open = false; });
    }
  });
});

function hubClick(kind) {
  if (kind === "ingest") { resetFlow(); $("#purpose").value = "prediction"; updatePurpose(); nav("flow"); setStep(1); return; }
  state.scenario = kind === "reverse" ? "reverse" : "forward";
  $("#singleScenario").value = state.scenario;
  navTo("single");
}

function navTo(v) {
  if (state.researchScenario && v !== "single") {
    state.researchScenario = null;
    state.researchBundle = null;
    state.scenario = "forward";
    $("#singleScenario").replaceChildren(
      el("option", { value: "forward" }, "正向预测"),
      el("option", { value: "reverse" }, "逆向情景"));
    $(".crumb > span:first-child").textContent = "减药后复发";
    $("#view-single .hero-sub").textContent = "与批量共用同一字段校验与推理逻辑；字段不齐或非法时拒绝推理，不返回部分结果。";
    $("#singleHint").textContent = "case_id 须为院内 HMAC 生成的代号，禁止姓名/身份证/手机号";
    $("#btnSingleFill").textContent = "填入教学示例";
    $("#banner").textContent = "教学合成模型 · 仅供研究联调，不用于临床决策";
  }
  if (v === "flow") { nav("flow"); setStep(state.step); }
  else if (v === "single") { $("#singleScenario").value = state.scenario; buildSingleForm(); nav("single"); }
  else if (v === "history") { loadHistory(); nav("history"); }
  else if (v === "audit") { nav("audit"); }
  else if (v === "plan") { showPlan(); }
  else nav(v);
}

function showConfig() {
  const m = state.meta;
  showModal(
    `<b>当前运行配置</b><br><br>` +
    `<table class="tbl"><tbody>` +
    Object.entries({
      "app_version": m.app_version, "schema_version": m.schema_version,
      "model_version": m.model_version, "reverse_model_version": m.reverse_model_version,
      "signature_valid": String(m.signature_valid),
      "通道2 信封加密": m.config.channel2_envelope ? "ON（方案B）" : "OFF（方案A · 进程内边界二）",
      "逆向设计": m.config.reverse_enabled ? "ON" : "OFF",
      "缺失值策略": m.config.missing_policy, "链接白名单": (m.config.link_whitelist || []).join(", ") || "（空）",
      "算法": m.channel2.alg, "签名": m.channel2.sig_alg,
      "留存天数": m.retention_days,
      "研究提示": m.banner,
    }).map(([k, v]) => `<tr><td class="mono">${esc(k)}</td><td>${esc(v)}</td></tr>`).join("") +
    `</tbody></table><br><span style="color:var(--txt3)">红线：数据不出院；课题组零持有密钥；生产环境零外部出站。</span>`);
}

async function showPlan() {
  nav("plan");
  if ($("#planBody").textContent) return;
  $("#planBody").textContent = "加载中…";
  const res = await fetch("/plan");
  $("#planBody").textContent = await res.text();
}

/* ------------------------------------------------------- 步骤①：导入与预检 */
function bindFlow() {
  const dz = $("#dropzone"), fi = $("#fileInput");
  dz.addEventListener("click", (e) => { if (e.target !== fi && !state.uploading) fi.click(); });
  fi.addEventListener("change", () => { if (fi.files[0]) uploadFile(fi.files[0]); fi.value = ""; });
  ["dragenter", "dragover"].forEach((ev) => dz.addEventListener(ev, (e) => {
    e.preventDefault(); dz.classList.add("over");
  }));
  ["dragleave", "drop"].forEach((ev) => dz.addEventListener(ev, (e) => {
    e.preventDefault(); dz.classList.remove("over");
  }));
  dz.addEventListener("drop", (e) => {
    const f = e.dataTransfer.files[0];
    if (f) uploadFile(f);
  });
  $("#purpose").addEventListener("change", () => {
    if (state.importId) { resetFlow(); setStep(1); toast("研究用途已更改，请重新选择文件", "", 2600); }
    updatePurpose();
  });
  $$("[data-source]").forEach((tab, index, tabs) => {
    tab.addEventListener("click", () => {
      tabs.forEach((item) => {
        const selected = item === tab;
        item.classList.toggle("selected", selected);
        item.setAttribute("aria-selected", String(selected)); item.tabIndex = selected ? 0 : -1;
        $(`#source-${item.dataset.source}`).classList.toggle("hidden", !selected);
      });
    });
    tab.addEventListener("keydown", (e) => {
      if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(e.key)) return;
      e.preventDefault();
      const next = e.key === "Home" ? 0 : e.key === "End" ? tabs.length - 1 : (index + (e.key === "ArrowRight" ? 1 : -1) + tabs.length) % tabs.length;
      tabs[next].click(); tabs[next].focus();
    });
  });
  $("#btnFlowNext").addEventListener("click", () => setStep(2, false));
  $("#btnDemoOk").addEventListener("click", () => demoCsv("ok"));
  $("#btnDemoBad").addEventListener("click", () => demoCsv("bad"));
  $("#btnLink").addEventListener("click", submitLink);
  $("#btnAutoMap").addEventListener("click", () => {
    state.mapping = { ...(state.proposed?.mapping || {}) };
    buildMappingTable(); toast("已套用预检建议的映射", "ok", 1800);
  });
  $("#btnSaveMap").addEventListener("click", saveMapping);
  $("#btnConfirm").addEventListener("click", confirmImport);
  $("#btnRun").addEventListener("click", startRun);
  $("#btnCancel").addEventListener("click", cancelRun);
  $("#runScenario").addEventListener("change", (e) => {
    $("#lblTarget").style.opacity = e.target.value === "reverse" ? 1 : 0.35;
    $("#runTarget").disabled = e.target.value !== "reverse";
  });
  $$("[data-fmt]").forEach((b) => b.addEventListener("click", () => exportRun(b.dataset.fmt)));
  $("#btnSingle").addEventListener("click", submitSingle);
  $("#btnSingleFill").addEventListener("click", fillSingleExample);
  $("#singleForm").addEventListener("input", clearSingleResult);
  $("#singleTarget").addEventListener("input", clearSingleResult);
  $("#singleScenario").addEventListener("change", buildSingleForm);
  $("#btnReloadHist").addEventListener("click", loadHistory);
  $("#btnAudit").addEventListener("click", loadAudit);
  $("#btnSelftest").addEventListener("click", runSelftest);
  $("#lblTarget").style.opacity = 0.35;
  $("#runTarget").disabled = true;
}

function updatePurpose() {
  const p = $("#purpose").value;
  state.scenario = p === "reverse" ? "reverse" : "forward";
  $("#runScenario").value = state.scenario;
  $("#runScenario").dispatchEvent(new Event("change"));
  $("#purposeHint").textContent = {
    prediction: "探索首次实际减药后 730 天内的复发风险。",
    reverse: "设定目标风险，探索模型支持范围内的减药幅度。",
    validation: "接入并校验模型验证数据；此用途暂不支持运行预测。",
    retrain: "接入并校验模型重训数据；此用途暂不支持运行预测。",
  }[p];
  $("#templateLink").href = `/api/v1/templates/${state.scenario}`;
}

async function demoCsv(flavor) {
  const scenario = $("#purpose").value === "reverse" ? "reverse" : "forward";
  const r = await api("GET", `/api/v1/demo/csv?scenario=${scenario}&flavor=${flavor}&n=40`, { raw: true });
  if (r.status !== 200) return toast("生成演示文件失败", "err");
  const file = new File([r.blob], `demo-${scenario}-${flavor}.csv`, { type: "text/csv" });
  toast(flavor === "bad" ? "已生成含违规行的合成 CSV，用于演示拒绝码" : "已生成可运行的合成 CSV", "ok", 2600);
  uploadFile(file);
}

async function uploadFile(file) {
  if (state.uploading) return;
  state.uploading = true;
  $("#btnChooseFile").disabled = true; $("#purpose").disabled = true;
  $("#uploadStatus").textContent = `正在上传并预检：${file.name}`;
  try {
  const fd = new FormData();
  fd.append("file", file);
  fd.append("purpose", $("#purpose").value);
  const r = await api("POST", "/api/v1/imports/file", { form: fd });
  if (r.status !== 201) {
    $("#uploadStatus").textContent = "文件未通过上传校验，请调整后重试";
    $("#precheckBox").classList.remove("hidden");
    $("#precheckBox").innerHTML = `<span class="chip err">${esc(fmtErr(r.body, r.status))}</span>`;
    return toast("导入被拒绝：" + fmtErr(r.body, r.status), "err", 7000);
  }
  const b = r.body;
  resetFlow();
  state.importId = b.import_id;
  state.purpose = b.purpose;
  state.scenario = b.scenario;
  state.validation = b.validation;
  state.proposed = b.proposed_mapping;
  state.fileSha = b.file_sha256;
  state.retainedUntil = b.retained_until;
  state.importCreatedBy = b.created_by;
  state.mapping = { ...(b.proposed_mapping?.mapping || {}) };
  state.mappingVersion = null;
  state.confirmed = false;
  state.uploadFailed = b.stage === "FAILED";
  $("#uploadStatus").textContent = `${file.name} · ${b.validation.runnable_rows}/${b.validation.total_rows} 行可运行`;
  $("#flowPurposeTag").textContent = `用途：${b.purpose} · ${b.import_id}`;
  $("#runScenario").value = b.scenario === "reverse" ? "reverse" : "forward";
  renderPrecheck(b.validation, b);
  buildMappingTable();
  renderConfirmInfo();
  setStep(state.uploadFailed ? 1 : 2);
  if (state.uploadFailed) {
    $("#uploadStatus").textContent = `${file.name} · 预检失败，请查看下方说明并重新上传`;
    return toast("文件预检失败，请调整后重新上传", "err", 4000);
  }
  toast(`已上传并预检：${b.validation.runnable_rows}/${b.validation.total_rows} 行可运行`,
        b.validation.ok ? "ok" : "", 3600);
  } catch {
    $("#uploadStatus").textContent = "上传失败，请检查服务连接后重试";
    toast("上传失败，请检查服务连接", "err");
  } finally {
    state.uploading = false;
    $("#btnChooseFile").disabled = false; $("#purpose").disabled = false;
  }
}

async function submitLink() {
  const url = $("#linkUrl").value.trim();
  if (!url) return toast("请先粘贴链接", "err", 2200);
  const r = await api("POST", "/api/v1/imports/link", { json: { source_url: url } });
  const msg = r.status === 202 ? "白名单命中，转服务端读取" : fmtErr(r.body, r.status);
  $("#linkNote").innerHTML = `<span style="color:${r.status === 202 ? "var(--green)" : "var(--red)"}">${esc(msg)}</span>`;
  toast(msg, r.status === 202 ? "ok" : "err", 6000);
}

/* ------------------------------------------------------------- 步骤②：映射 */
function stdOptions() {
  const seen = new Set();
  const opts = [];
  const f = state.meta.fields;
  for (const group of ["management", "model", "extension", "reverse"]) {
    for (const spec of f[group] || []) {
      if (seen.has(spec.name)) continue;
      seen.add(spec.name);
      opts.push({ name: spec.name, label: `${spec.name} · ${spec.label}`,
                  required: !!spec.required, group });
    }
  }
  return opts;
}

/* 当前场景下真正必填的标准字段：逆向设计的 B1-B4 只在 reverse 场景必填 */
function requiredStdFields() {
  return stdOptions()
    .filter((o) => o.required && (o.group !== "reverse" || state.scenario === "reverse"))
    .map((o) => o.name);
}

function buildMappingTable() {
  if (!state.validation) return;
  const cols = state.validation.columns;
  const req = requiredStdFields();
  const mapped = new Set(Object.values(state.mapping));
  const missing = req.filter((n) => !mapped.has(n));
  $("#mapStatusTag").innerHTML = missing.length
    ? `<span style="color:var(--amber)">不完整 · 缺 ${missing.length} 个必填字段</span>`
    : `<span style="color:var(--green)">完整</span>`;
  $("#mapHint").textContent = missing.length
    ? `未映射必填：${missing.slice(0, 5).join(", ")}${missing.length > 5 ? " …" : ""}`
    : "所有必填标准字段均已映射";

  const thead = $("#mapTable thead"), tbody = $("#mapTable tbody");
  thead.innerHTML = ""; tbody.innerHTML = "";
  thead.append(el("tr", {}, el("th", {}, "医院列名"), el("th", {}, "映射到标准字段"),
                  el("th", {}, "必填"), el("th", {}, "抽样预览")));
  const opts = stdOptions();
  cols.forEach((col) => {
    const sel = el("select", { class: "cell-select" });
    sel.append(el("option", { value: "" }, "（不映射 / 丢弃）"));
    for (const o of opts) {
      const on = el("option", { value: o.name }, o.label);
      if (state.mapping[col] === o.name) on.selected = true;
      sel.append(on);
    }
    sel.addEventListener("change", () => {
      if (sel.value) {
        for (const [k, v] of Object.entries(state.mapping)) if (v === sel.value) delete state.mapping[k];
        state.mapping[col] = sel.value;
      } else delete state.mapping[col];
      buildMappingTable();
    });
    const isReq = req.includes(state.mapping[col]);
    const tr = el("tr", {},
      el("td", { class: "mono" }, col), el("td", {}, sel),
      el("td", {}, isReq ? "是" : "—"),
      el("td", { class: "mono", style: "color:var(--txt3)" },
         (state.validation.column_stats?.[state.mapping[col]] ? "已采集" : "")));
    tbody.append(tr);
  });
}

async function saveMapping() {
  if (!state.importId) return toast("请先导入文件", "err");
  if (!Object.keys(state.mapping).length) return toast("映射为空，无法保存", "err");
  const r = await api("POST", `/api/v1/imports/${state.importId}/mappings`, {
    json: { mapping: state.mapping, unit_rules: $("#unitRules").value,
            null_rules: $("#nullRules").value },
  });
  if (r.status !== 200) return toast("保存映射失败：" + fmtErr(r.body, r.status), "err", 6000);
  state.mappingVersion = r.body.mapping_version;
  const updated = await api("GET", `/api/v1/imports/${state.importId}/validation`);
  if (updated.status === 200) state.validation = updated.body.validation;
  if (r.body.status !== "COMPLETE") {
    toast(`映射不完整：${r.body.unmapped_required.join(", ")}`, "err", 6000);
  } else {
    toast(`已保存映射版本 ${state.mappingVersion}`, "ok", 3000);
    renderConfirmInfo();
    setStep(3);
  }
}

/* ------------------------------------------------------------- 步骤③：确认 */
function renderConfirmInfo() {
  const v = state.validation || {};
  const box = $("#confirmInfo");
  box.innerHTML = "";
  const rows = [
    ["import_id", state.importId || "—"], ["用途 purpose", $("#purpose").value],
    ["文件 SHA-256", state.fileSha ? state.fileSha.slice(0, 20) + "…" : "—"],
    ["总行数 / 可运行", `${v.total_rows ?? "—"} / ${v.runnable_rows ?? "—"}`],
    ["被拒绝行数", v.rejected_rows ?? "—"],
    ["映射版本", state.mappingVersion || "（未保存）"],
    ["schema_version", state.meta?.schema_version || "—"],
    ["model_version", state.meta?.model_version || "—"],
    ["scope（科室/项目）", state.actor.scope],
    ["留存到期", state.retainedUntil ? ts(state.retainedUntil) : "—"],
  ];
  for (const [k, val] of rows) {
    box.append(el("dt", {}, k), el("dd", {}, val));
  }
}

async function confirmImport() {
  if (!state.importId) return toast("请先导入文件", "err");
  if (!state.mappingVersion) return toast("请先保存映射版本", "err");
  const r = await api("POST", `/api/v1/imports/${state.importId}/confirm`, {
    json: { purpose: $("#purpose").value, mapping_version: state.mappingVersion,
            ethics_ref: $("#ethicsRef").value, index_rule: $("#indexRule").value,
            note: $("#confirmNote").value },
  });
  if (r.status !== 200) {
    $("#confirmHint").innerHTML = `<span style="color:var(--red)">${esc(fmtErr(r.body, r.status))}</span>`;
    return toast("确认失败：" + fmtErr(r.body, r.status), "err", 6000);
  }
  state.confirmed = true;
  $("#confirmHint").innerHTML = `<span style="color:var(--green)">已锁定：${esc(r.body.mapping_version)} · 审核人 ${esc(r.body.confirmed_by)}</span>`;
  toast("批次已确认，可提交运行", "ok", 2600);
  setStep(4);
}

/* ------------------------------------------------------------- 步骤④：运行 */
function idemKey() {
  return `ui-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}

async function startRun() {
  if (!state.importId) return toast("请先导入文件", "err");
  if (!state.confirmed) return toast("请先由审核员确认批次（E302）", "err");
  const scenario = $("#runScenario").value;
  const r = await api("POST", "/api/v1/runs", {
    json: { import_id: state.importId, scenario,
            target_risk: Number($("#runTarget").value || 0.35) },
    headers: { "Idempotency-Key": idemKey() },
  });
  if (r.status !== 202 && r.status !== 200) {
    $("#runHint").innerHTML = `<span style="color:var(--red)">${esc(fmtErr(r.body, r.status))}</span>`;
    return toast("运行被拒绝：" + fmtErr(r.body, r.status), "err", 7000);
  }
  state.runId = r.body.run_id;
  $("#runHint").innerHTML = `<span style="color:var(--txt2)">任务 ${esc(state.runId)} 已提交</span>`;
  pollRun();
}

function pollRun() {
  if (state.poll) clearInterval(state.poll);
  const tick = async () => {
    const r = await api("GET", `/api/v1/runs/${state.runId}`);
    if (r.status !== 200) return;
    renderRun(r.body);
    if (["COMPLETED", "PARTIAL_FAILED", "FAILED", "CANCELLED"].includes(r.body.status)) {
      clearInterval(state.poll); state.poll = null;
      state.page = 1;
      await loadResults(1);
      setStep(5);
    }
  };
  tick();
  state.poll = setInterval(tick, 900);
}

function renderRun(run) {
  const box = $("#runBox");
  box.classList.remove("hidden");
  box.innerHTML = "";
  const order = ["QUEUED", "RUNNING", "COMPLETED", "PARTIAL_FAILED", "FAILED", "CANCELLED"];
  const cur = run.status;
  box.append(el("div", { class: "chips" }, ...order.map((s) => {
    const isCur = s === cur;
    const isTerminalErr = ["PARTIAL_FAILED", "FAILED", "CANCELLED"].includes(s);
    return el("span", { class: `chip ${isCur ? (isTerminalErr ? "err" : "good") : ""}` },
              isCur ? `▶ ${s}` : s);
  })));
  const c = run.counts || {};
  box.append(el("div", { class: "stat-grid" },
    stat("提交行数", c.submitted ?? "—"), stat("预检拒绝", c.precheck_rejected ?? 0),
    stat("推理成功", c.ok ?? "—", "ok"), stat("逐行拒绝", c.rejected ?? "—",
      c.rejected ? "bad" : ""),
    stat("边界二", run.boundary === "envelope-http" ? "信封加密" : "进程内", run.boundary === "envelope-http" ? "good" : ""),
    stat("模型", (run.model_version_returned || run.model_version || "—"))));
  if (run.error) {
    box.append(el("div", { class: "row" },
      el("span", { class: "chip err" }, `${esc(run.error.code || "")} ${esc(run.error.message || "")}`)));
  }
  const sha = run.integrity?.sha256 || {};
  const shaKey = Object.keys(sha)[0];
  box.append(el("div", { class: "row" },
    el("span", { class: "tag" }, `run_id ${run.run_id}`),
    el("span", { class: "tag" }, `开始 ${ts(run.created_at)}`),
    run.finished_at ? el("span", { class: "tag" }, `完成 ${ts(run.finished_at)}`) : null,
    shaKey ? el("span", { class: "tag", title: sha[shaKey] },
      `${shaKey} ${String(sha[shaKey]).slice(0, 12)}… ✓`) : null));
}

async function cancelRun() {
  if (!state.runId) return toast("没有进行中的任务", "err", 2000);
  const r = await api("POST", `/api/v1/runs/${state.runId}/cancel`);
  toast(r.status === 200 ? "已请求取消" : fmtErr(r.body, r.status), r.status === 200 ? "ok" : "err");
}

/* ------------------------------------------------------------- 步骤⑤：结果 */
const FWD_COLS = [["__line__", "行"], ["case_id", "case_id"], ["status", "状态"],
  ["risk_730d", "730d 风险"], ["in_support", "支持范围"], ["reject_codes", "拒绝码"],
  ["reject_reason", "拒绝原因"], ["model_version", "模型"]];
const REV_COLS = [["__line__", "行"], ["case_id", "case_id"], ["status", "状态"],
  ["risk_730d", "风险"], ["feasible_reduction_range", "可行减药幅度(%)"],
  ["dose_range_mg", "对应日剂量(mg)"], ["reject_codes", "拒绝码"],
  ["reject_reason", "拒绝原因"], ["support_note", "支持说明"]];

async function loadResults(page) {
  state.page = page || 1;
  if (!state.runId) return;
  const r = await api("GET",
    `/api/v1/runs/${state.runId}/results?page=${state.page}&page_size=${state.pageSize}`);
  if (r.status === 403) {
    // 角色分离（§8.1）：运行员可看计数，行级结果需“结果查看者”
    const toolbar = $("#resultToolbar");
    toolbar.classList.remove("hidden");
    toolbar.innerHTML = "";
    toolbar.append(el("div", { class: "row" },
      el("span", { class: "chip warn" }, `E601 · ${r.body.message || "权限不足"}`),
      el("span", { class: "hint" },
        "行级结果需「结果查看者」及以上角色；运行员只能看到运行计数（方案 §8.1 角色分离）"),
      el("button", { class: "btn btn-outline btn-sm", onclick: () => {
        switchRole("viewer"); loadResults(state.page);
      } }, "切换为结果查看者并加载")));
    return;
  }
  if (r.status !== 200) return toast(fmtErr(r.body, r.status), "err");
  renderResults(r.body);
}

function switchRole(role) {
  $("#actorRole").value = role;
  $("#actorRole").dispatchEvent(new Event("change"));
  toast(`已切换为「${state.meta.roles[role]}」`, "ok", 2200);
}

function renderResults(res) {
  const toolbar = $("#resultToolbar");
  toolbar.classList.remove("hidden");
  toolbar.innerHTML = "";
  const c = res.counts || {};
  toolbar.append(el("div", { class: "stat-grid" },
    stat("总行数", res.total ?? "—"), stat("成功", c.ok ?? "—", "ok"),
    stat("拒绝", c.rejected ?? "—", c.rejected ? "bad" : ""),
    stat("研究标识", res.research_only ? "RESEARCH_ONLY" : "—", "warn")));
  toolbar.append(el("div", { class: "row" },
    ...Object.entries(res.versions || {}).map(([k, v]) => el("span", { class: "tag" }, `${k} ${v || "—"}`))));
  if (res.support_note) {
    toolbar.append(el("div", { class: "hint" }, res.support_note));
  }

  const cols = res.scenario === "reverse" ? REV_COLS : FWD_COLS;
  const thead = $("#resultTable thead"), tbody = $("#resultTable tbody");
  thead.innerHTML = ""; tbody.innerHTML = "";
  thead.append(el("tr", {}, ...cols.map(([k, label]) => el("th", {}, label))));
  for (const row of res.rows || []) {
    const tds = cols.map(([k]) => {
      let v = row[k];
      if (k === "reject_codes") {
        const codes = v || [];
        return el("td", {}, ...codes.map((cd) => {
          const chip = el("span", { class: "chip err", style: "margin-right:4px" }, cd);
          chip.addEventListener("click", () => showModal(
            `<b>${cd}</b> · ${esc(state.meta.reject_codes[cd] || "未登记")}<br><br>` +
            `<span style="color:var(--txt3)">${esc(row.reject_reason || "")}</span>`));
          return chip;
        }));
      }
      if (k === "status") return el("td", { class: `mono st-${row.status}` }, row.status);
      if (k === "in_support") return el("td", {}, v === true ? "✓" : "✗");
      if (k === "risk_730d") return el("td", { class: "num" }, v === null || v === undefined ? "—" : Number(v).toFixed(4));
      if (k === "feasible_reduction_range") {
        return el("td", { class: "num" }, v ? `${v.pct_low} – ${v.pct_upper}` : "—");
      }
      if (k === "dose_range_mg") {
        return el("td", { class: "num" }, v ? `${v.mg_low} – ${v.mg_high}` : "—");
      }
      return el("td", { class: k === "__line__" || k === "case_id" ? "mono" : "" },
                v === null || v === undefined ? "—" : String(v));
    });
    tbody.append(el("tr", {}, ...tds));
  }

  const pages = Math.max(1, Math.ceil((res.total || 0) / state.pageSize));
  const pager = $("#pager");
  pager.innerHTML = "";
  pager.append(
    el("button", { class: "btn btn-ghost btn-sm", disabled: state.page <= 1 ? "" : null,
      onclick: () => loadResults(state.page - 1) }, "上一页"),
    el("span", {}, `第 ${state.page} / ${pages} 页 · 共 ${res.total || 0} 行`),
    el("button", { class: "btn btn-ghost btn-sm", disabled: state.page >= pages ? "" : null,
      onclick: () => loadResults(state.page + 1) }, "下一页"));
}

async function exportRun(fmt) {
  if (!state.runId) return toast("没有可导出的任务", "err");
  const r = await api("POST", `/api/v1/runs/${state.runId}/exports`,
    { json: { format: fmt, purpose: "internal_research" } });
  const box = $("#exportBox");
  box.classList.remove("hidden");
  if (r.status !== 200) {
    box.innerHTML = `<span class="chip err">${esc(fmtErr(r.body, r.status))}</span>`;
    return toast("导出被拒绝：" + fmtErr(r.body, r.status), "err", 6000);
  }
  const b = r.body;
  box.innerHTML = "";
  box.append(el("div", { class: "row" },
    el("span", { class: "chip good" }, `已生成 ${b.file_name}`),
    el("span", { class: "tag" }, `${b.bytes} 字节`),
    el("span", { class: "tag" }, `审计 ${String(b.meta.audit_event_id).slice(0, 8)}`),
    el("button", { class: "btn btn-outline btn-sm", onclick: () => downloadExport(b) }, "下载到本机"),
    el("span", { class: "hint" }, "落盘于院内受控目录；文件带 RESEARCH_ONLY 与版本三元组")));
  toast("导出成功（已记审计）", "ok", 3000);
}

async function downloadExport(info) {
  try {
    const response = await fetch(info.download_url, { headers: headers() });
    if (!response.ok) {
      const body = await response.json();
      return toast("下载被拒绝：" + fmtErr(body, response.status), "err");
    }
    const url = URL.createObjectURL(await response.blob());
    const link = el("a", { href: url, download: info.file_name });
    document.body.append(link); link.click(); link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  } catch { toast("下载失败，请检查服务连接", "err"); }
}

/* ------------------------------------------------------------- 单例录入 */
function setupResearchPresentation() {
  const model = RESEARCH_MODELS[state.researchScenario];
  const selector = $("#singleScenario");
  selector.replaceChildren(el("option", { value: "forward" }, "正向预测"));
  selector.value = "forward";
  $(".crumb > span:first-child").textContent = model.name;
  $("#view-single .hero-sub").textContent = model.description;
  $("#singleHint").textContent = "训练统计示例不代表真实患者；逐例输入仅在本机浏览器计算。";
  $("#btnSingleFill").textContent = "填入训练中位数示例";
  $("#btnSingle").disabled = true;
  $("#btnSingleFill").disabled = true;
  $("#banner").textContent = `${model.label} · 真实队列研究演示 · 不用于临床决策`;
}

async function loadResearchBundle(scenario) {
  const config = RESEARCH_MODELS[scenario];
  const wrap = $("#singleForm");
  try {
    if (!crypto.subtle) throw Error("浏览器不支持模型包校验");
    const response = await fetch(config.bundleUrl, { cache: "no-store" });
    if (!response.ok) throw Error("模型包无法加载");
    const bytes = await response.arrayBuffer();
    const hash = Array.from(new Uint8Array(await crypto.subtle.digest("SHA-256", bytes)),
      x => x.toString(16).padStart(2, "0")).join("");
    if (hash !== config.sha256) throw Error("模型包指纹不匹配");
    const bundle = JSON.parse(new TextDecoder().decode(bytes));
    if (bundle.model_id !== config.modelId ||
        bundle.feature_order.length !== config.displayOrder.length ||
        config.displayOrder.some(name => !bundle.feature_order.includes(name))) {
      throw Error("模型版本或字段不匹配");
    }
    if (state.researchScenario !== scenario) return;
    state.researchBundle = bundle;
    $("#btnSingle").disabled = false;
    $("#btnSingleFill").disabled = false;
    buildSingleForm();
  } catch (error) {
    wrap.replaceChildren(el("p", { class: "hint" }, error.message || "模型包校验失败"));
    toast(error.message || "模型包校验失败", "err");
  }
}

function singleFields() {
  if (state.researchScenario) {
    const bundle = state.researchBundle;
    if (!bundle) return [];
    return RESEARCH_MODELS[state.researchScenario].displayOrder.map(name => ({
      name, label: bundle.labels[name] || name, required: true,
      kind: bundle.binary_fields.includes(name) ? "binary" : "integer",
      min: bundle.ranges[name].min, max: bundle.ranges[name].max,
      values: bundle.binary_fields.includes(name) ? [0, 1] : null,
      note: name === "gender" ? "仅使用原始 D13 编码；性别方向未明确" :
        name === "eeg_epileptic" && state.researchScenario === "first" ? "原始 EEG=2 编 1；0/1/3 编 0（3 为未做 EEG）" : "",
    }));
  }
  const f = state.meta.fields;
  const scenario = $("#singleScenario").value;
  const groups = [f.management, f.model, f.extension];
  if (scenario === "reverse") groups.push(f.reverse);
  return groups.flat().filter((s, i, a) => a.findIndex((x) => x.name === s.name) === i);
}

let singleInputVersion = 0;

function clearSingleResult() {
  singleInputVersion++;
  const box = $("#singleBox");
  box.classList.add("hidden");
  box.replaceChildren();
}

function buildSingleForm() {
  clearSingleResult();
  const wrap = $("#singleForm");
  wrap.innerHTML = "";
  const scenario = $("#singleScenario").value;
  $("#lblSingleTarget").style.opacity = scenario === "reverse" ? 1 : 0.35;
  $("#singleTarget").disabled = scenario !== "reverse";
  if (state.researchScenario && !state.researchBundle) {
    wrap.append(el("p", { class: "hint" }, "正在校验对应场景的模型包…"));
    return;
  }
  for (const spec of singleFields()) {
    const label = `${spec.label || spec.name}${spec.required ? " *" : ""}`;
    const hint = [spec.label, spec.kind,
      spec.min !== undefined ? `[${spec.min}, ${spec.max}]` : "",
      spec.values ? spec.values.join("/") : "", spec.note || ""].filter(Boolean).join(" · ");
    wrap.append(el("div", {},
      el("label", { class: "lbl", for: `sf-${spec.name}`, title: spec.name }, label),
      el("input", { class: "input", style: "width:100%;min-width:0", id: `sf-${spec.name}`,
                    placeholder: hint })));
  }
}

function fillSingleExample() {
  clearSingleResult();
  if (state.researchScenario) {
    const bundle = state.researchBundle;
    if (!bundle) return;
    for (const name of bundle.feature_order) $(`#sf-${name}`).value = String(bundle.medians[name]);
    $("#singleHint").textContent = "已填入训练中位数示例（非真实患者）；逐例输入仅在本机浏览器计算。";
    return;
  }
  const ex = {
    case_id: "0a1b2c3d4e5f6789", index_date: new Date().toISOString().slice(0, 10),
    epilepsy_duration_before_remission_years: "6.2", seizure_free_months: "27",
    age_at_onset: "9", febrile_seizure_history: "0", seizure_count_before_remission: "4",
    self_limiting_syndrome: "0", developmental_delay: "0", eeg_epileptiform: "1",
    relative_dose_reduction_pct: "20", reduction_strategy: "stepwise", asm_count: "1",
    previous_asm_failure_count: "0", asm_name: "LEV", current_daily_dose_mg: "1000",
    planned_reduction_pct: "20", reduction_schedule: "stepwise", reduction_steps: "4",
    asm_polytherapy: "0", previous_reduction_failure: "0",
  };
  for (const spec of singleFields()) {
    const inp = $(`#sf-${spec.name}`);
    if (inp) inp.value = ex[spec.name] ?? "";
  }
}

function researchEstimate(values) {
  const bundle = state.researchBundle;
  const sigmoid = x => x >= 0 ? 1 / (1 + Math.exp(-x)) : Math.exp(x) / (1 + Math.exp(x));
  let logit = bundle.intercept;
  if (state.researchScenario === "first") {
    for (const name of bundle.feature_order) {
      let value = values[name];
      const prep = bundle.continuous_preprocessing[name];
      if (prep) value = (Math.min(prep.upper, Math.max(prep.lower, value)) - prep.mean) / prep.sd;
      logit += bundle.coefficients[name] * value;
    }
    return sigmoid(logit);
  }
  for (const name of bundle.feature_order) {
    const clipped = Math.min(bundle.winsor_upper[name], Math.max(bundle.winsor_lower[name], values[name]));
    const value = bundle.log1p_fields.includes(name) ? Math.log1p(clipped) : clipped;
    logit += bundle.coefficients[name] * (value - bundle.means[name]) / bundle.standard_deviations[name];
  }
  const raw = Math.max(1e-8, Math.min(1 - 1e-8, sigmoid(logit)));
  return sigmoid(bundle.calibration.intercept + bundle.calibration.slope * Math.log(raw / (1 - raw)));
}

function submitResearchSingle() {
  const config = RESEARCH_MODELS[state.researchScenario];
  const bundle = state.researchBundle;
  if (!bundle) return toast("模型包尚未校验完成", "err");
  const values = {};
  for (const spec of singleFields()) {
    const input = $(`#sf-${spec.name}`);
    const raw = input.value.trim();
    const number = Number(raw);
    if (!raw || !Number.isFinite(number) || !Number.isInteger(number) ||
        number < spec.min || number > spec.max ||
        (spec.kind === "binary" && number !== 0 && number !== 1)) {
      clearSingleResult();
      const box = $("#singleBox");
      box.classList.remove("hidden");
      box.append(el("span", { class: "chip err" }, `请按原始编码填写 ${spec.label}（${spec.min}–${spec.max}）`));
      input.focus();
      return;
    }
    values[spec.name] = number;
  }
  const probability = researchEstimate(values);
  if (!validRisk(probability)) return toast("模型计算未返回有效估计", "err");
  clearSingleResult();
  const box = $("#singleBox");
  box.classList.remove("hidden");
  renderResearchResult(box, state.researchScenario, bundle, config, values, probability, researchEstimate);
}

async function submitSingle() {
  if (state.researchScenario) return submitResearchSingle();
  const fields = {};
  for (const spec of singleFields()) {
    const inp = $(`#sf-${spec.name}`);
    if (!inp) continue;
    const v = inp.value.trim();
    if (v !== "") fields[spec.name] = v;
  }
  const button = $("#btnSingle");
  if (button.disabled) return;
  clearSingleResult();
  const submittedVersion = singleInputVersion;
  button.disabled = true;
  let response;
  try {
    response = await api("POST", "/api/v1/predictions", {
      json: { scenario: $("#singleScenario").value,
              target_risk: Number($("#singleTarget").value || 0.35), fields } });
  } catch {
    if (submittedVersion === singleInputVersion) toast("推理服务暂时无法连接", "err");
    return;
  } finally {
    button.disabled = false;
  }
  if (submittedVersion !== singleInputVersion) return;

  const box = $("#singleBox");
  box.classList.remove("hidden");
  const result = response.body;
  if (response.status < 400 && result?.status === "OK" && result.in_support === true && validRisk(result.risk_730d)) {
    renderSingleResult(box, result);
    return;
  }

  let reason = "本次推理未返回可展示的结果";
  if (response.status >= 400) reason = fmtErr(result, response.status);
  else if (result?.in_support === false) reason = "本次输入超出训练支持范围";
  else if (result?.scenario === "reverse" && result.reject_codes?.includes("E403")) {
    reason = "当前搜索范围内未找到满足目标的情景";
  }
  box.append(el("span", { class: "chip err" }, reason));
  if (result?.reject_codes?.length) {
    box.append(el("div", { class: "row" },
      ...result.reject_codes.map((code) => codeChip(code, 0, state.meta.reject_codes))));
  }
  if (result?.errors?.length) {
    const table = el("table", { class: "tbl" }, el("thead", {}, el("tr", {},
      ...["行", "字段", "码", "含义"].map((label) => el("th", { scope: "col" }, label)))));
    const rows = el("tbody");
    for (const error of result.errors) rows.append(el("tr", {},
      el("td", { class: "num" }, error.line || "1"),
      el("td", { class: "mono" }, error.field),
      el("td", { class: "mono st-REJECTED" }, error.code), el("td", {}, error.message)));
    table.append(rows);
    box.append(el("div", { class: "table-wrap" }, table));
  }
  box.append(el("p", { class: "single-detail" }, "教学合成模型 · 仅供工程联调"));
  toast("本次推理未通过", "err", 5000);
}

/* ------------------------------------------------------------- 历史任务 */
async function loadHistory() {
  const panel = $("#view-history .panel");
  const [ir, rr] = await Promise.all([api("GET", "/api/v1/imports"), api("GET", "/api/v1/runs")]);
  panel.innerHTML = "";
  if (rr.status === 200) {
    panel.append(el("div", { class: "panel-title" }, `运行任务（${rr.body.count ?? 0}）`));
    panel.append(runTable(rr.body.items || []));
  } else {
    panel.append(el("div", { class: "chip err" }, fmtErr(rr.body, rr.status)));
  }
  if (ir.status === 200) {
    panel.append(el("div", { class: "panel-title", style: "margin-top:20px" },
      `导入批次（${ir.body.count ?? 0}）`));
    panel.append(importTable(ir.body.items || []));
  }
  panel.append(el("div", { class: "actions" },
    el("button", { class: "btn btn-ghost btn-sm", onclick: loadHistory }, "刷新")));
}

function runTable(items) {
  if (!items.length) return el("div", { class: "hint" }, "暂无任务");
  const t = el("table", { class: "tbl" }, el("thead", {}, el("tr", {},
    ...["run_id", "场景", "状态", "提交/成功/拒绝", "边界二", "模型", "提交时间", "操作"].map((h) => el("th", {}, h)))));
  const tb = el("tbody");
  for (const it of items) {
    const c = it.counts || {};
    const viewBtn = el("button", { class: "btn btn-ghost btn-sm", onclick: () => {
      resetFlow();
      state.scenario = it.scenario;
      state.runId = it.run_id; resetResultsOnly(); loadResults(1);
      $("#flowPurposeTag").textContent = `用途：${it.purpose || "—"} · ${it.import_id}`;
      nav("flow"); setStep(5);
    } }, "查看结果");
    tb.append(el("tr", {},
      el("td", { class: "mono" }, it.run_id), el("td", {}, it.scenario),
      el("td", { class: `mono st-${it.status}` }, it.status),
      el("td", { class: "num" }, `${c.submitted ?? "—"} / ${c.ok ?? "—"} / ${c.rejected ?? "—"}`),
      el("td", {}, it.boundary === "envelope-http" ? "信封加密" : (it.boundary || "—")),
      el("td", { class: "mono" }, it.model_version || "—"),
      el("td", { class: "mono" }, ts(it.created_at)), el("td", {}, viewBtn)));
  }
  t.append(tb);
  return el("div", { class: "table-wrap" }, t);
}

function importTable(items) {
  if (!items.length) return el("div", { class: "hint" }, "暂无批次");
  const t = el("table", { class: "tbl" }, el("thead", {}, el("tr", {},
    ...["import_id", "文件", "用途", "阶段", "行（可运行/拒绝）", "映射版本", "已确认", "导入人"].map((h) => el("th", {}, h)))));
  const tb = el("tbody");
  for (const it of items) {
    tb.append(el("tr", {},
      el("td", { class: "mono" }, it.import_id), el("td", { class: "mono" }, it.file_name),
      el("td", {}, it.purpose), el("td", { class: "mono" }, it.stage),
      el("td", { class: "num" }, `${it.runnable_rows} / ${it.rejected_rows}`),
      el("td", { class: "mono" }, it.mapping_version || "—"),
      el("td", {}, it.confirmed ? "✓" : "—"), el("td", { class: "mono" }, it.created_by)));
  }
  t.append(tb);
  return el("div", { class: "table-wrap" }, t);
}

function resetResultsOnly() {
  if (state.poll) clearInterval(state.poll);
  state.poll = null; state.page = 1;
}

/* --------------------------------------------------------- 审计与加密自检 */
async function loadAudit() {
  const r = await api("GET", "/api/v1/audit?limit=30");
  const tag = $("#chainTag");
  if (r.status !== 200) {
    tag.textContent = fmtErr(r.body, r.status);
    tag.style.color = "var(--red)";
    return;
  }
  const chain = r.body.chain || {};
  tag.textContent = `链式哈希 ${chain.ok ? "完整 ✓" : "断裂 ✗"} · ${chain.events ?? 0} 条 · 摘要 ${r.body.daily_digest}`;
  tag.style.color = chain.ok ? "var(--green)" : "var(--red)";
  const t = $("#auditTable"), thead = t.querySelector("thead"), tbody = t.querySelector("tbody");
  thead.innerHTML = ""; tbody.innerHTML = "";
  thead.append(el("tr", {}, ...["时间", "操作者", "角色", "动作", "结果", "对象", "码", "模型版本"]
    .map((h) => el("th", {}, h))));
  for (const e of r.body.events || []) {
    tbody.append(el("tr", {},
      el("td", { class: "mono" }, e.ts_iso ? e.ts_iso.slice(0, 19).replace("T", " ") : ""),
      el("td", { class: "mono" }, e.actor), el("td", {}, e.actor_role),
      el("td", { class: "mono" }, e.action),
      el("td", { class: `mono st-${e.result === "ALLOW" ? "OK" : "REJECTED"}` }, e.result),
      el("td", { class: "mono" }, e.object_id || "—"),
      el("td", { class: "mono" }, e.code || "—"),
      el("td", { class: "mono" }, e.versions?.model_version || "—")));
  }
}

async function runSelftest() {
  const r = await api("POST", "/api/v1/crypto/selftest");
  const box = $("#selftestBox");
  box.classList.remove("hidden");
  box.innerHTML = "";
  if (r.status !== 200) {
    box.append(el("span", { class: "chip err" }, fmtErr(r.body, r.status)));
    return toast("自检需要系统管理角色", "err", 4000);
  }
  const b = r.body;
  box.append(el("div", { class: "stat-grid" },
    stat("通道2", b.channel2_enabled ? "启用" : "关闭（方案A）", b.channel2_enabled ? "good" : ""),
    stat("院内密钥", b.keys_present ? "已就位" : "缺失"),
    stat("加密回环", b.roundtrip_ok ? "通过 ✓" : "失败 ✗", b.roundtrip_ok ? "ok" : "bad"),
    stat("重放拦截", b.replay_blocked ? "通过 ✓" : "—", b.replay_blocked ? "ok" : ""),
    stat("算法", "AES-256-GCM"), stat("签名", "Ed25519")));
  if (b.kid) {
    box.append(el("div", { class: "row" },
      el("span", { class: "tag" }, `kid(model) ${b.kid.model}`),
      el("span", { class: "tag" }, `fp ${b.key_fingerprint.model}`),
      el("span", { class: "tag" }, `kid(sign) ${b.kid.platform_sign}`),
      el("span", { class: "tag" }, `fp ${b.key_fingerprint.platform_sign}`)));
  }
  box.append(el("div", { class: "hint" }, b.note));
}

bindFlow();
