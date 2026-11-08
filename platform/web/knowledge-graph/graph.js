
  const DATA = JSON.parse(document.getElementById("app-data").textContent);
  const nodes = DATA.graph.nodes;
  const edges = DATA.graph.edges;
  const nodeById = Object.fromEntries(nodes.map(node => [node.entity_id, node]));
  const sourceById = Object.fromEntries(DATA.sources.map(source => [source.source_id, source]));
  const claimById = Object.fromEntries(DATA.claims.map(claim => [claim.claim_id, claim]));
  const outgoing = new Map();
  const incoming = new Map();
  for (const node of nodes) { outgoing.set(node.entity_id, []); incoming.set(node.entity_id, []); }
  for (const edge of edges) {
    if (!outgoing.has(edge.from)) outgoing.set(edge.from, []);
    if (!incoming.has(edge.to)) incoming.set(edge.to, []);
    outgoing.get(edge.from).push(edge);
    incoming.get(edge.to).push(edge);
  }

  const typeConfig = {
    Model: {label:"模型", className:"pill-model", color:"#c2f778"},
    ScoreComponent: {label:"评分变量", className:"pill-score", color:"#d5b4f3"},
    ClinicalConcept: {label:"临床概念", className:"pill-concept", color:"#b9b8ed"},
    Outcome: {label:"结局", className:"pill-outcome", color:"#e69bb5"},
    Study: {label:"研究", className:"pill-study", color:"#c192e4"},
    Dataset: {label:"数据集", className:"pill-data", color:"#b1a5cc"},
    ResearchVariable: {label:"研究变量", className:"pill-data", color:"#b1a5cc"},
    Population: {label:"人群", className:"pill-concept", color:"#b9b8ed"},
    DataQualityIssue: {label:"数据限制", className:"pill-issue", color:"#e6bb8b"},
    DefinitionConcept: {label:"定义概念", className:"pill-concept", color:"#b9b8ed"},
    ClinicalEvent: {label:"临床事件", className:"pill-outcome", color:"#e69bb5"},
    FeatureSet: {label:"特征集", className:"pill-score", color:"#d5b4f3"},
    Disease: {label:"疾病", className:"pill-outcome", color:"#e69bb5"},
    AnatomicalStructure: {label:"解剖结构", className:"pill-default", color:"#ad99be"},
    DecisionPoint: {label:"待决问题", className:"pill-issue", color:"#e6bb8b"},
  };

  const relationPriority = {
    HAS_SCORE_COMPONENT:120, HAS_DATA_QUALITY_ISSUE:115, CANNOT_CALCULATE:110,
    APPLIES_TO:105, PREDICTS:104, SCORES_CONCEPT:100, HAS_FEATURE_SET:98,
    EVALUATED_IN:96, PENDING_DECISION:96, USES_CLINICAL_CONCEPT:92,
    PROXY_ONLY_FOR:90, NOT_EQUIVALENT_TO:90, DEFINES_RULE_FOR:88,
    AFFECTS:85, CONTAINS_VARIABLE:72, MEASURES:75, BELONGS_TO_DATASET:50,
  };

  let neighborPage = 0;
  let currentFocus = null;
  let currentPath = null;
  let currentStep = 0;
  let zoom = 1;
  const overviewId = "model_select_1_0";
  let showAllRelations = false;
  let openDrawer = null;

  function showDrawer(panel, restoreFocus = false) {
    const previous = openDrawer;
    openDrawer = panel;
    document.getElementById("paths-panel").hidden = panel !== "paths";
    document.getElementById("inspector-panel").hidden = panel !== "inspector";
    document.getElementById("open-paths").setAttribute("aria-expanded", String(panel === "paths"));
    if (panel) {
      document.getElementById("close-" + panel).focus({preventScroll:true});
    } else if (restoreFocus) {
      const target = previous === "paths" ? document.getElementById("open-paths")
        : document.querySelector(`#graph [data-node="${CSS.escape(currentFocus)}"]`);
      (target || document.getElementById("search")).focus({preventScroll:true});
    }
  }

  function escapeHtml(value) {
    const element = document.createElement("span");
    element.textContent = String(value ?? "");
    return element.innerHTML;
  }
  function typeInfo(type) {
    return typeConfig[type] || {label:type || "其他", className:"pill-default", color:"#ad99be"};
  }
  function shortLabel(value, max = 26) {
    const text = String(value || "");
    return text.length > max ? `${text.slice(0, max - 1)}…` : text;
  }
  function formatCount(value) {
    return new Intl.NumberFormat("zh-CN").format(value);
  }
  function formatValue(value) {
    if (Array.isArray(value)) {
      if (!value.length) return "—";
      if (value.length > 8) return `${value.slice(0, 8).map(String).join("、")} 等${value.length}项`;
      return value.map(String).join("、");
    }
    if (value && typeof value === "object") return JSON.stringify(value);
    if (value === true) return "是";
    if (value === false) return "否";
    return String(value ?? "—");
  }
  function edgeLabel(edge) {
    return DATA.relation_labels[edge.relation_type] || edge.relation_type;
  }

  function initialize() {
    document.getElementById("global-stats").textContent =
      `${formatCount(nodes.length)}个节点 · ${formatCount(edges.length)}条关系 · 来源可追溯`;
    renderPathList();
    bindControls();
    const first = nodeFromHash();
    focusNode(nodeById[first] ? first : overviewId, false, false, false);
  }

  function renderPathList() {
    document.getElementById("path-list").innerHTML = DATA.paths.map(path => `
      <button class="path-button" type="button" data-path="${path.id}">
        <span class="path-number">${path.number}</span>
        <span><strong>${escapeHtml(path.title)}</strong><span>${escapeHtml(path.subtitle)}</span></span>
      </button>
    `).join("");
    document.getElementById("path-list").addEventListener("click", event => {
      const button = event.target.closest("[data-path]");
      if (!button) return;
      startPath(button.dataset.path);
    });
  }

  function nodeFromHash() {
    try { return decodeURIComponent(location.hash.slice(1)); } catch { return ""; }
  }
  function bindControls() {
    const pathsButton = document.getElementById("open-paths");
    const legend = document.querySelector(".graph-help");
    pathsButton.addEventListener("click", () => {
      if (openDrawer === "paths") showDrawer(null, true);
      else showDrawer("paths");
    });
    for (const name of ["paths", "inspector"]) {
      document.getElementById("close-" + name).addEventListener("click", () => showDrawer(null, true));
    }
    document.addEventListener("keydown", event => {
      if (event.key !== "Escape" || event.defaultPrevented) return;
      if (legend.open) {
        legend.open = false;
        legend.querySelector("summary").focus();
      } else if (openDrawer) {
        showDrawer(null, true);
      }
    });
    const toggleRelations = document.getElementById("toggle-relations");
    toggleRelations.addEventListener("click", () => {
      showAllRelations = !showAllRelations;
      neighborPage = 0;
      renderGraph(currentFocus);
    });
    document.getElementById("relayout").addEventListener("click",()=>window.GraphMotion?.relayout(document.getElementById("graph"),()=>renderGraph(currentFocus)));
    window.addEventListener("hashchange", () => {
      const id = nodeFromHash();
      const target = nodeById[id] ? id : overviewId;
      if (target !== currentFocus) focusNode(target, false, false, false);
    });
    for (const [id, delta] of [["neighbors-prev", -1], ["neighbors-next", 1]]) {
      document.getElementById(id).addEventListener("click", () => {
        neighborPage += delta; if (currentFocus) renderGraph(currentFocus);
      });
    }
    const search = document.getElementById("search");
    search.addEventListener("keydown", event => {
      if (event.key === "ArrowDown" || event.key === "Enter") {
        const first = document.querySelector("#search-results:not(.hidden) .search-item[data-node]");
        if (first) { event.preventDefault(); if (event.key === "Enter") first.click(); else first.focus(); }
      }
      if (event.key === "Escape") { document.getElementById("search-results").classList.add("hidden"); search.setAttribute("aria-expanded", "false"); }
    });
    const results = document.getElementById("search-results");
    search.addEventListener("input", () => renderSearch(search.value));
    search.addEventListener("focus", () => renderSearch(search.value));
    document.addEventListener("click", event => {
      if (!event.target.closest(".graph-help")) legend.open = false;
      if (!event.target.closest(".search-wrap")) {
        results.classList.add("hidden");
        search.setAttribute("aria-expanded", "false");
      }
    });
    results.addEventListener("keydown", event => {
      const items = [...results.querySelectorAll("[data-node]")];
      const index = items.indexOf(document.activeElement);
      if (event.key === "ArrowDown" || event.key === "ArrowUp") {
        event.preventDefault(); items[(index + (event.key === "ArrowDown" ? 1 : -1) + items.length) % items.length]?.focus();
      }
      if (event.key === "Escape") { results.classList.add("hidden"); search.setAttribute("aria-expanded", "false"); search.focus(); }
    });
    results.addEventListener("click", event => {
      const button = event.target.closest("[data-node]");
      if (!button) return;
      results.classList.add("hidden"); search.setAttribute("aria-expanded", "false");
      search.value = "";
      setActivePath(null);
      focusNode(button.dataset.node);
    });
    document.getElementById("zoom-in").addEventListener("click", () => setZoom(zoom + .12));
    document.getElementById("zoom-out").addEventListener("click", () => setZoom(zoom - .12));
    document.getElementById("zoom-reset").addEventListener("click", () => setZoom(1));
    document.getElementById("guide-exit").addEventListener("click", () => {
      focusNode(currentFocus, false, false);
      pathsButton.focus({preventScroll:true});
    });
    document.getElementById("guide-prev").addEventListener("click", () => {
      if (!currentPath) return;
      currentStep = Math.max(0, currentStep - 1);
      renderPathStep();
    });
    document.getElementById("guide-next").addEventListener("click", () => {
      if (!currentPath) return;
      currentStep = Math.min(currentPath.steps.length - 1, currentStep + 1);
      renderPathStep();
    });
    window.addEventListener("resize", () => {
      if (currentFocus) renderGraph(currentFocus);
    });
  }

  function nodeSearchText(node) {
    return [
      node.canonical_name_zh, node.canonical_name_en,
      ...(node.aliases_zh || []), ...(node.aliases_en || []),
      ...(node.abbreviations || []), ...(node.non_synonyms || []),
      ...(node.properties?.field_name ? [node.properties.field_name] : []),
    ].join(" ").toLowerCase();
  }

  function renderSearch(query) {
    const results = document.getElementById("search-results");
    const term = String(query || "").trim().toLowerCase();
    if (!term) {
      document.getElementById("search").setAttribute("aria-expanded", "false");
      results.innerHTML = "";
      results.classList.add("hidden");
      return;
    }
    const matches = nodes
      .filter(node => nodeSearchText(node).includes(term))
      .sort((a, b) => {
        const aStarts = nodeSearchText(a).startsWith(term) ? 1 : 0;
        const bStarts = nodeSearchText(b).startsWith(term) ? 1 : 0;
        return bStarts - aStarts || (a.canonical_name_zh || "").localeCompare(b.canonical_name_zh || "", "zh-CN");
      })
      .slice(0, 14);
    results.innerHTML = matches.length ? matches.map(node => {
      const info = typeInfo(node.entity_type);
      return `<button class="search-item" type="button" data-node="${escapeHtml(node.entity_id)}">
        <strong>${escapeHtml(node.canonical_name_zh)}</strong>
        <span>${escapeHtml(info.label)} · ${escapeHtml(node.entity_id)}</span>
      </button>`;
    }).join("") : `<div class="search-item"><strong>没有匹配结果</strong><span>可尝试模型名称、字段名或中文概念。</span></div>`;
    results.classList.remove("hidden"); document.getElementById("search").setAttribute("aria-expanded", "true");
  }

  function setActivePath(pathId) {
    document.querySelectorAll(".path-button").forEach(button => {
      button.classList.toggle("active", button.dataset.path === pathId);
      if (button.dataset.path === pathId) button.setAttribute("aria-current", "step"); else button.removeAttribute("aria-current");
    });
  }

  function startPath(pathId) {
    currentPath = DATA.paths.find(path => path.id === pathId);
    currentStep = 0;
    setActivePath(pathId);
    showDrawer(null);
    renderPathStep();
    document.getElementById("guide-next").focus({preventScroll:true});
  }

  function renderPathStep() {
    if (!currentPath) return;
    const step = currentPath.steps[currentStep];
    document.getElementById("guide").classList.remove("hidden");
    document.getElementById("guide-kicker").textContent =
      `路径 ${currentPath.number} · 第 ${currentStep + 1} / ${currentPath.steps.length} 步`;
    document.getElementById("guide-title").textContent = step.title;
    document.getElementById("guide-text").textContent = step.text;
    document.getElementById("guide-prev").disabled = currentStep === 0;
    document.getElementById("guide-next").disabled = currentStep === currentPath.steps.length - 1;
    document.getElementById("guide-progress").innerHTML = currentPath.steps.map((_, index) =>
      `<span class="progress-dot ${index < currentStep ? "done" : index === currentStep ? "active" : ""}"></span>`
    ).join("");
    focusNode(step.node, true);
  }

  function focusNode(nodeId, fromPath = false, inspect = !fromPath, updateHash = true) {
    if (!nodeById[nodeId]) return;
    if (currentFocus !== nodeId || fromPath) showAllRelations = false;
    neighborPage = 0;
    currentFocus = nodeId;
    if (!fromPath && currentPath) {
      currentPath = null;
      setActivePath(null);
      document.getElementById("guide").classList.add("hidden");
    }
    if (updateHash) location.hash = encodeURIComponent(nodeId);
    const node = nodeById[nodeId];
    document.getElementById("stage-title").textContent = node.canonical_name_zh;
    document.getElementById("stage-subtitle").textContent =
      typeInfo(node.entity_type).label;
    document.getElementById("graph-empty").style.display = "none";
    renderGraph(nodeId);
    if (inspect) {
      renderInspector(nodeId);
      showDrawer("inspector");
    } else if (openDrawer === "inspector") {
      showDrawer(null);
    }
  }

  function incidentEdges(nodeId) {
    return [...(outgoing.get(nodeId) || []), ...(incoming.get(nodeId) || [])];
  }

  function buildNeighborhood(focusId) {
    const combined = new Map();
    for (const edge of incidentEdges(focusId)) {
      const other = edge.from === focusId ? edge.to : edge.from;
      if (!combined.has(other)) combined.set(other, []);
      combined.get(other).push(edge);
    }
    return [...combined.entries()]
      .map(([nodeId, nodeEdges]) => ({
        nodeId,
        edges: nodeEdges,
        priority: Math.max(...nodeEdges.map(edge => relationPriority[edge.relation_type] || 10)),
      }))
      .sort((a, b) => b.priority - a.priority || a.nodeId.localeCompare(b.nodeId));
  }

  function setZoom(value) {
    zoom = Math.max(.62, Math.min(1.55, value));
    document.getElementById("zoom-reset").textContent = `${Math.round(zoom * 100)}%`;
    if (currentFocus) renderGraph(currentFocus);
  }

  function svgElement(name, attrs = {}) {
    const element = document.createElementNS("http://www.w3.org/2000/svg", name);
    for (const [key, value] of Object.entries(attrs)) {
      if (value !== null && value !== undefined) element.setAttribute(key, value);
    }
    return element;
  }

  function textLines(label, maxChars) {
    const text = String(label || "");
    if (text.length <= maxChars) return [text];
    const midpoint = Math.ceil(text.length / 2);
    return [text.slice(0, midpoint), text.slice(midpoint)];
  }

  function renderGraph(focusId) {
    const svg = document.getElementById("graph");
    const motionSnapshot = window.GraphMotion?.capture(svg);
    const shell = svg.parentElement;
    const width = Math.max(320, shell.clientWidth);
    const height = Math.max(390, shell.clientHeight);
    svg.setAttribute("viewBox", `0 0 ${width} ${height}`);
    svg.innerHTML = `<defs>
      <marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="5" markerHeight="5" orient="auto-start-reverse">
        <path d="M 0 0 L 10 5 L 0 10 z" fill="#a28ab7"></path>
      </marker>
      <filter id="soft-shadow" x="-20%" y="-20%" width="140%" height="140%">
        <feDropShadow dx="0" dy="4" stdDeviation="5" flood-color="#c2f778" flood-opacity=".18"/>
      </filter>
    </defs>`;
    const layer = svgElement("g", {
      "data-motion-layer":"true",
      transform: `translate(${width / 2},${height / 2}) scale(${zoom}) translate(${-width / 2},${-height / 2})`
    });
    svg.appendChild(layer);

    const allNeighbors = buildNeighborhood(focusId);
    const overview = focusId === overviewId && !currentPath;
    const scoreNeighbors = overview
      ? allNeighbors.filter(item => item.edges.some(edge => edge.from === focusId && edge.relation_type === "HAS_SCORE_COMPONENT"))
      : [];
    const focusedOverview = overview && !showAllRelations && scoreNeighbors.length > 0;
    const neighbors = focusedOverview ? scoreNeighbors : allNeighbors;
    const compactGraph = width < 620;
    const limit = focusedOverview ? scoreNeighbors.length : width >= 880 ? 8 : width >= 600 ? 6 : 4;
    const pages = Math.max(1, Math.ceil(neighbors.length / limit));
    neighborPage = Math.max(0, Math.min(pages - 1, neighborPage));
    const shown = neighbors.slice(neighborPage * limit, (neighborPage + 1) * limit);
    const toggle = document.getElementById("toggle-relations");
    toggle.hidden = !overview || !scoreNeighbors.length || allNeighbors.length <= scoreNeighbors.length;
    toggle.textContent = showAllRelations ? "只看评分变量" : "展开更多关系";
    toggle.setAttribute("aria-expanded", String(showAllRelations));
    document.querySelector(".graph-pages").hidden = pages <= 1;
    document.getElementById("neighbors-label").textContent = focusedOverview
      ? `显示 ${scoreNeighbors.length} 个评分变量 · 点击节点查看详情`
      : neighbors.length
        ? pages > 1 ? `相邻节点 ${neighborPage * limit + 1}–${Math.min((neighborPage + 1) * limit, neighbors.length)} / ${neighbors.length}`
          : `${neighbors.length} 个相邻节点`
        : "暂无直接邻近节点";
    document.getElementById("neighbors-prev").disabled = neighborPage === 0;
    document.getElementById("neighbors-next").disabled = neighborPage + 1 >= pages;
    const cx = width / 2, cy = height / 2;
    const positions = { [focusId]: {x:cx, y:cy} };
    const rx = Math.min(width * (width < 620 ? .32 : .34), 390);
    const ry = Math.min(height * .36, 225);
    shown.forEach((item, index) => {
      const angle = -Math.PI / 2 + 2 * Math.PI * index / shown.length;
      positions[item.nodeId] = {x:cx + Math.cos(angle)*rx, y:cy + Math.sin(angle)*ry};
    });

    const edgeLayer = svgElement("g");
    const nodeLayer = svgElement("g");
    layer.append(edgeLayer, nodeLayer);
    shown.forEach(item => {
      const target = positions[item.nodeId];
      const edge = item.edges.sort((a,b) => (relationPriority[b.relation_type]||0)-(relationPriority[a.relation_type]||0))[0];
      const line = svgElement("line", {
        "data-edge-source":focusId, "data-edge-target":item.nodeId,
        x1:cx, y1:cy, x2:target.x, y2:target.y,
        stroke:"#a989c165", "stroke-width":"1.1",
        "marker-end": edge.to === focusId ? null : "url(#arrow)",
      });
      edgeLayer.appendChild(line);
      if (!compactGraph && !focusedOverview) {
        const label = svgElement("text", {
          "data-edge-target":item.nodeId,
          x:(cx+target.x)/2, y:(cy+target.y)/2 - 3,
          "text-anchor":"middle", fill:"#beabd0", "font-size":"7.5",
          "paint-order":"stroke", stroke:"#1f152c", "stroke-width":"3",
        });
        label.textContent = edgeLabel(edge);
        edgeLayer.appendChild(label);
      }
    });

    const focusEntity = nodeById[focusId];
    const spaciousOverview = focusedOverview && width >= 880;
    createGraphNode(nodeLayer, focusEntity, positions[focusId], true, spaciousOverview);
    shown.forEach(item => {
      const node = nodeById[item.nodeId];
      if (!node) return;
      createGraphNode(nodeLayer, node, positions[item.nodeId], false, spaciousOverview, item.edges);
    });
    window.GraphMotion?.attach({svg,layer,focusId,key:`${focusId}:${neighborPage}`,width,height,zoom,targets:positions,previous:motionSnapshot,onFocus:focusNode});

  }

  function nodeLabelLines(text, units) {
    const lines = []; let line = "", used = 0;
    for (const char of String(text)) {
      const cost = /[\x00-\xff]/.test(char) ? .55 : 1;
      if (used + cost > units && line) { lines.push(line.trim()); line = ""; used = 0; }
      line += char; used += cost;
    }
    if (line.trim()) lines.push(line.trim());
    if (lines.length > 2) lines[1] = lines[1].slice(0, -1) + "…";
    return lines.slice(0, 2);
  }

  function createGraphNode(layer, node, position, isFocus, spaciousOverview, nodeEdges = []) {
    const info = typeInfo(node.entity_type);
    const shellWidth = document.getElementById("graph").parentElement.clientWidth;
    const cardWidth = spaciousOverview ? 168 : shellWidth < 440 ? 104 : shellWidth < 620 ? 112 : shellWidth < 760 ? 120 : 134;
    const focusRadius = spaciousOverview ? 54 : shellWidth < 440 ? 42 : 47;
    const labelSize = spaciousOverview ? (isFocus ? 16 : 14) : (isFocus ? 12 : 11);
    const group = svgElement("g", { transform:`translate(${position.x},${position.y})`, tabindex:"0", role:"button", "aria-label":node.canonical_name_zh, "data-node":node.entity_id, style:"cursor:pointer" });
    const title = svgElement("title"); title.textContent = node.canonical_name_zh; group.appendChild(title);
    const shape = isFocus
      ? svgElement("circle", {r:focusRadius,fill:"#28351e",stroke:"#c2f778","stroke-width":2.5,filter:"url(#soft-shadow)"})
      : svgElement("rect", {x:-cardWidth/2,y:-33,width:cardWidth,height:66,rx:15,fill:"#281c37",stroke:info.color,"stroke-opacity":.65,"stroke-width":1.1});
    shape.setAttribute("class","node-shape"); group.appendChild(shape);
    const type = svgElement("text", {x:0,y:isFocus?-13:-16,"text-anchor":"middle",fill:isFocus?"#c2f778":info.color,"font-size":9,"font-weight":500});
    type.textContent = info.label; group.appendChild(type);
    const name = node.entity_type === "ScoreComponent" ? node.canonical_name_zh.replace(/^SeLECT\s*[\d.]+\s*[:：]\s*/, "") : node.canonical_name_zh;
    const lines = nodeLabelLines(name, isFocus ? (focusRadius * 1.6) / labelSize : (cardWidth - 14) / labelSize);
    const label = svgElement("text", {x:0,y:isFocus?5:3,"text-anchor":"middle",fill:"#f5eefb","font-size":labelSize,"font-weight":600});
    lines.forEach((line, index) => { const span=svgElement("tspan",{x:0,dy:index?labelSize+3:0}); span.textContent=line; label.appendChild(span); });
    group.appendChild(label);
    if (!isFocus && nodeEdges.length > 1) {
      group.appendChild(svgElement("circle",{cx:cardWidth/2-4,cy:-28,r:7,fill:"#24182e",stroke:info.color,"stroke-width":1}));
      const count=svgElement("text",{x:cardWidth/2-4,y:-25.5,"text-anchor":"middle",fill:info.color,"font-size":7,"font-weight":700}); count.textContent=String(nodeEdges.length); group.appendChild(count);
    }
    group.addEventListener("click",event=>{event.stopPropagation();focusNode(node.entity_id);});
    group.addEventListener("keydown",event=>{if(event.key==="Enter"||event.key===" "){event.preventDefault();focusNode(node.entity_id);}});
    layer.appendChild(group);
  }

  function getNodeClaims(nodeId) {
    return DATA.claims.filter(claim => claim.subject === nodeId || claim.object === nodeId);
  }

  function sourceLinksForNode(nodeId) {
    const sourceIds = new Set();
    for (const sourceId of (nodeById[nodeId]?.properties?.source_ids || [])) sourceIds.add(sourceId);
    for (const edge of incidentEdges(nodeId)) {
      for (const sourceId of (edge.attributes?.source_ids || [])) sourceIds.add(sourceId);
      const claim = claimById[edge.attributes?.claim_id];
      if (claim) {
        for (const sourceId of (claim.source_ids || [claim.source_id])) sourceIds.add(sourceId);
      }
    }
    return [...sourceIds].map(sourceId => sourceById[sourceId]).filter(Boolean);
  }

  function sourceLink(source, locator = "") {
    const local = DATA.local_sources[source.source_id];
    const href = local || source.url;
    const label = local ? "打开本地依据" : source.url ? "打开原始来源" : "查看来源信息";
    if (!href) {
      return `<span class="source-link">${escapeHtml(label)}</span>`;
    }
    return `<a class="source-link" href="${escapeHtml(href)}" target="_blank" rel="noreferrer">${escapeHtml(label)}</a>`;
  }

  function renderInspector(nodeId) {
    const node = nodeById[nodeId];
    const info = typeInfo(node.entity_type);
    const body = document.getElementById("inspector-body");
    body.scrollTop = 0;
    const neighbors = buildNeighborhood(nodeId);
    const claims = getNodeClaims(nodeId);
    const properties = node.properties || {};
    const pending = [
      ...(outgoing.get(nodeId)||[]).filter(edge=>edge.relation_type==="PENDING_DECISION"),
      ...(incoming.get(nodeId)||[]).filter(edge=>edge.relation_type==="PENDING_DECISION"),
    ];
    const issueEdges = incidentEdges(nodeId).filter(edge =>
      edge.relation_type === "HAS_DATA_QUALITY_ISSUE" ||
      (edge.relation_type === "AFFECTS" && nodeById[edge.from]?.entity_type === "DataQualityIssue")
    );
    const sources = sourceLinksForNode(nodeId);

    const sections = [];
    sections.push(`
      <span class="type-pill ${info.className}">${escapeHtml(info.label)}</span>
      <h2>${escapeHtml(node.canonical_name_zh)}</h2>
      <div style="color:var(--muted);font-size:10px;margin-top:3px">${escapeHtml(node.canonical_name_en || "")}</div>
      <p class="definition">${escapeHtml(node.definition || "暂无定义")}</p>
    `);

    if (nodeId === "model_select_2_0" || nodeId === "model_select_1_0") {
      sections.push(renderModelSpecial(nodeId, neighbors));
    }
    if (nodeId === "dataset_d13") {
      sections.push(renderD13Special());
    }
    if (nodeId === "model_d13_s1_lr_platt_v0_3") {
      sections.push('<div class="section"><div class="section-title">正向预测</div><p>公开真实队列的冻结参数，仅限 D13 原始编码字段；不是临床验证。</p><a class="source-link" href="/workspace?view=single&amp;scenario=stroke">进入 D13 预测 ↗</a></div>');
    }
    if (nodeId === "study_five_arch_d_20261107") {
      sections.push('<div class="section"><div class="section-title">正向预测</div><p>温州 167 例卒中后早期首次发作队列，核心 8 变量 LR；仅供研究演示。</p><a class="source-link" href="/workspace?view=single&amp;scenario=first">进入 D 研究预测 ↗</a></div>');
    }
    if (node.entity_type === "Outcome") {
      sections.push(renderOutcomeSpecial(nodeId, properties));
    }
    if (issueEdges.length && nodeId !== "dataset_d13") {
      sections.push(renderIssues(issueEdges, nodeId));
    }
    if (pending.length) {
      sections.push(`<div class="section"><div class="section-title">待确认问题</div>
        ${pending.map(edge => `<div class="pending">${escapeHtml(nodeById[edge.to]?.properties?.question || nodeById[edge.from]?.properties?.question || "尚有决策问题待确认")}</div>`).join("")}
      </div>`);
    }
    const propertyDetails = renderProperties(properties, ["source_ids","features","components"]);
    const related = neighbors.length ? renderNeighbors(neighbors) : "";
    if (propertyDetails || related) {
      sections.push(`<details class="inspector-disclosure"><summary>相关节点与属性</summary>${related}${propertyDetails}</details>`);
    }
    if (claims.length || sources.length) {
      sections.push(`<details class="inspector-disclosure"><summary>研究证据与来源</summary>${renderClaims(claims, sources)}</details>`);
    }
    body.innerHTML = sections.join("");
    body.querySelectorAll("[data-focus]").forEach(button => {
      button.addEventListener("click", () => focusNode(button.dataset.focus));
    });
  }

  function renderModelSpecial(nodeId, neighbors) {
    const components = neighbors.filter(item => nodeById[item.nodeId]?.entity_type === "ScoreComponent")
      .sort((a,b) => (nodeById[a.nodeId].properties.component_order||0) - (nodeById[b.nodeId].properties.component_order||0));
    const studies = neighbors.filter(item => nodeById[item.nodeId]?.entity_type === "Study");
    const population = neighbors.find(item => nodeById[item.nodeId]?.entity_type === "Population");
    const outcome = neighbors.find(item => nodeById[item.nodeId]?.entity_type === "Outcome");
    return `
      <div class="section">
        <div class="section-title"><span>评分变量</span><span>${components.length}项</span></div>
        <div class="tag-list">${components.map(item => {
          const props = nodeById[item.nodeId].properties;
          return `<button class="tag" type="button" data-focus="${item.nodeId}">${escapeHtml(nodeById[item.nodeId].canonical_name_zh.replace(/^.*：/, ""))}<br><small>${escapeHtml(props.scoring_rule)}</small></button>`;
        }).join("") || '<span class="empty-help">该版本没有独立评分项。</span>'}</div>
      </div>
      <div class="section">
        <div class="section-title"><span>适用人群与结局</span></div>
        <div class="tag-list">
          ${population ? `<button class="tag" type="button" data-focus="${population.nodeId}">${escapeHtml(nodeById[population.nodeId].canonical_name_zh)}</button>` : ""}
          ${outcome ? `<button class="tag" type="button" data-focus="${outcome.nodeId}">${escapeHtml(nodeById[outcome.nodeId].canonical_name_zh)}</button>` : ""}
        </div>
      </div>
      <div class="section">
        <div class="section-title"><span>验证与更新研究</span><span>${studies.length}项</span></div>
        <div class="tag-list">${studies.map(item => `<button class="tag" type="button" data-focus="${item.nodeId}">${escapeHtml(nodeById[item.nodeId].canonical_name_zh)}</button>`).join("") || '<span class="empty-help">暂无直接研究关系。</span>'}</div>
      </div>`;
  }

  function renderD13Special() {
    const issues = (outgoing.get("dataset_d13")||[]).filter(edge=>edge.relation_type==="HAS_DATA_QUALITY_ISSUE");
    return `
      <div class="section">
        <div class="section-title"><span>D13与SeLECT字段对照</span><span>点击行可跳转字段</span></div>
        <table class="d13-table">
          <thead><tr><th>SeLECT变量</th><th>D13映射</th><th>限制</th></tr></thead>
          <tbody>${DATA.d13_mapping.map(item => `
            <tr>
              <td>${escapeHtml(item.select_variable)}</td>
              <td><span class="mapping-status map-${escapeHtml(item.mapping)}">${escapeHtml(item.mapping)}</span></td>
              <td>${escapeHtml(item.limitation)}</td>
            </tr>`).join("")}
          </tbody>
        </table>
      </div>
      <div class="section">
        <div class="section-title"><span>数据边界</span><span>${issues.length}项</span></div>
        <div class="issues">${issues.map(edge => {
          const issue = nodeById[edge.to];
          return `<div class="issue-card ${issue?.properties?.severity === "critical" ? "critical" : ""}">
            <strong>${escapeHtml(issue?.canonical_name_zh || edge.to)}</strong><br>${escapeHtml(issue?.definition || "")}
          </div>`;
        }).join("")}</div>
      </div>`;
  }

  function renderOutcomeSpecial(nodeId, properties) {
    const values = [];
    if (properties.time_window) values.push(["时间窗", properties.time_window]);
    if (properties.operational_definition) values.push(["操作定义", properties.operational_definition]);
    if (properties.operational_status) values.push(["定义状态", properties.operational_status]);
    if (properties.strict_late_unprovoked_endpoint !== undefined) {
      values.push(["严格晚期无诱因终点", properties.strict_late_unprovoked_endpoint ? "是" : "否"]);
    }
    return `<div class="section">
      <div class="section-title"><span>结局定义与时间</span></div>
      <div class="property-grid">${values.map(([key,value]) => `<div class="property"><span>${escapeHtml(key)}</span><strong>${escapeHtml(formatValue(value))}</strong></div>`).join("")}</div>
    </div>`;
  }

  function renderIssues(edges, nodeId) {
    const seen = new Set();
    return `<div class="section"><div class="section-title"><span>相关数据限制</span></div><div class="issues">
      ${edges.map(edge => {
        const issueId = nodeById[edge.from]?.entity_type === "DataQualityIssue" ? edge.from : edge.to;
        if (seen.has(issueId)) return "";
        seen.add(issueId);
        const issue = nodeById[issueId];
        if (!issue) return "";
        return `<button class="issue-card ${issue.properties?.severity === "critical" ? "critical" : ""}" type="button" data-focus="${issueId}" style="width:100%;text-align:left;border-top:0;border-right:0;border-bottom:0">
          <strong>${escapeHtml(issue.canonical_name_zh)}</strong><br>${escapeHtml(issue.definition)}
        </button>`;
      }).join("")}
    </div></div>`;
  }

  function renderProperties(properties, excluded = []) {
    const labelMap = {
      model_version:"版本", score_range:"分数范围", development:"开发队列", external_validation:"验证状态",
      applicability:"适用范围", limitations:"限制", test_auc:"测试AUROC", test_auprc:"测试AUPRC",
      test_brier:"测试Brier", time_condition:"时间条件", scoring_rule:"计分规则",
      d13_mapping_status:"D13映射", d13_mapping_limitation:"D13限制", feature_count:"特征数",
      role:"用途级别", issue_type:"问题类型", severity:"严重程度", status:"状态",
      region:"地区", sample_size:"样本量", evidence_type:"证据类型", result:"结果",
      operational_definition:"操作定义", time_window:"时间窗", population:"人群",
      source_records:"来源记录数", included_records:"最终记录数", has_patient_id:"患者ID",
      has_event_date:"癫痫日期", has_death_date:"死亡日期", upstream_imputation:"缺失处理",
    };
    const entries = Object.entries(properties).filter(([key,value]) =>
      !excluded.includes(key) && key !== "source_ids" && value !== null && value !== undefined && value !== ""
    ).slice(0, 18);
    if (!entries.length) return "";
    return `<div class="section">
      <div class="section-title"><span>属性</span></div>
      <div class="property-grid">${entries.map(([key,value]) => {
        let formatted = formatValue(value);
        if (["has_patient_id","has_event_date","has_death_date"].includes(key)) formatted = value ? "有" : "无";
        return `<div class="property"><span>${escapeHtml(labelMap[key] || key)}</span><strong>${escapeHtml(formatted)}</strong></div>`;
      }).join("")}</div>
    </div>`;
  }

  function renderNeighbors(neighbors) {
    const displayed = neighbors.slice(0, 36);
    return `<div class="section">
      <div class="section-title"><span>邻近关系</span><span>${neighbors.length}个节点</span></div>
      <div class="tag-list">${displayed.map(item => {
        const node = nodeById[item.nodeId];
        const labels = [...new Set(item.edges.map(edgeLabel))].join(" / ");
        return `<button class="tag" type="button" data-focus="${item.nodeId}">${escapeHtml(node.canonical_name_zh)}<br><small>${escapeHtml(labels)}</small></button>`;
      }).join("")}</div>
      ${neighbors.length > displayed.length ? `<div class="pending">另有 ${neighbors.length - displayed.length} 个邻近节点，可通过搜索继续查询。</div>` : ""}
    </div>`;
  }

  function renderClaims(claims, sources) {
    const items = [];
    const sourceByClaim = new Map();
    for (const claim of claims) {
      const sourceIds = claim.source_ids || [claim.source_id];
      for (const sourceId of sourceIds) {
        const source = sourceById[sourceId];
        if (!source) continue;
        const key = `${claim.claim_id}|${sourceId}`;
        if (sourceByClaim.has(key)) continue;
        sourceByClaim.set(key, true);
        items.push({ claim, source });
      }
    }
    if (!items.length && !sources.length) return "";
    return `<div class="section">
      <div class="section-title"><span>证据与来源定位</span></div>
      <div class="evidence-list">
        ${items.slice(0, 18).map(({claim, source}) => `
          <article class="evidence">
            <p>${escapeHtml(claim.statement)}</p>
            <div class="evidence-meta">${escapeHtml(source.title)} · ${escapeHtml(claim.source_locator || source.verification || "")}</div>
            <div class="source-actions">${sourceLink(source, claim.source_locator)}</div>
          </article>`).join("")}
        ${!items.length ? sources.slice(0,8).map(source => `
          <article class="evidence"><p>${escapeHtml(source.title)}</p>
          <div class="evidence-meta">${escapeHtml(source.origin || "")} · ${escapeHtml(source.verification || "")}</div>
          <div class="source-actions">${sourceLink(source)}</div></article>`).join("") : ""}
      </div>
    </div>`;
  }

  initialize();
  if (location.protocol === "file:") {
    document.getElementById("back-to-platform").href = "http://127.0.0.1:3000/";
    document.querySelector(".brand").href = "http://127.0.0.1:3000/";
  }
