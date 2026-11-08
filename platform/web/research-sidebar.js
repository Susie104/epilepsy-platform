(() => {
  const $ = selector => document.querySelector(selector);
  const panel = $('#research-sidebar');
  const toggle = $('#sidebar-toggle');
  const resizeHandle = $('#sidebar-resize');
  const views = { qa: $('#sidebar-qa'), settings: $('#sidebar-settings') };
  const tabs = { qa: $('#sidebar-tab-qa'), settings: $('#sidebar-tab-settings') };
  const copy = {
    zh: {
      pageTitle: '癫痫研究平台 · 研究入口', brand: '癫痫研究平台', hero: '选择研究<span class="accent">入口</span>', import: '导入自己的数据 ↗', toggle: '问答与设置', toggleAria: '打开知识问答与设置', closeAria: '关闭侧栏', resizeAria: '拖动调整侧栏宽度',
      ready: '研究服务已连接', failed: '模型校验未通过', unavailable: '服务暂不可用，请检查本机启动状态', connecting: '正在连接研究服务…',
      modules: [['知识问答','按场景检索与来源解读'],['知识图谱','卒中后癫痫 · SeLECT / D13']],
      scenes: {
        '02':['教学演示可进入','减药后复发','730 天复发风险 · 八字段录入','查看场景 ↗','首次实际减低抗发作药物剂量后，探索 730 天内复发风险。'],
        '01':['真实队列预测演示','首次发作','温州 D 模型 · 首次发作后预测','查看场景 ↗','卒中后 7 天内首次急性症状性发作后，用温州 D 研究的 8 项信息估计后续晚期 PSE；仅供研究演示。'],
        '03':['真实队列预测演示','卒中后癫痫','D13 冻结模型 · 一年内结局','查看场景 ↗','D13 公开真实队列的冻结模型可按原始编码字段估计一年内继发性癫痫标签；仅供研究演示。'],
        '04':['规划中','术后发作','预测模型与字段规则待建立','查看场景 ↗','术后发作场景的预测问题、字段规则与模型尚待建立。','本场景暂未开放正向预测与逆向设计。'],
        '05':['规划中','长期控制后','预测模型与字段规则待建立','查看场景 ↗','长期控制后场景的预测问题、字段规则与模型尚待建立。','本场景暂未开放正向预测与逆向设计。']
      },
      back:'← 返回入口', actions:{'02':['正向预测','逆向设计','批量数据接入'],'01':['正向预测','研究证据'],'03':['正向预测','研究证据']}, note:'减药场景为教学合成模型 · 卒中场景为真实队列预测研究演示 · 不用于临床决策',
      sidebarTitle:'知识问答', qaTab:'知识问答', settingsTab:'设置', status:'知识库证据检索 · LLM 服务待接入', intro:'检索已核对的 D13 卒中后癫痫资料，查看原始证据与来源。此处暂不生成 LLM 回答。', searchLabel:'检索知识库', placeholder:'例如：NIHSS 与卒中后癫痫', search:'检索', examplesLabel:'试试这些问题', examples:['NIHSS 与卒中后癫痫','D13 样本量','SeLECT 评分'], scope:'仅展示 D13 卒中后癫痫资料；不适用于减药后复发个体预测或临床决策。', settingsTitle:'界面设置', languageLabel:'界面语言', languageHelp:'切换开屏与右侧知识面板', settingsNote:'语言设置会保存在此浏览器中。知识条目的原始证据保持原文。', results:'检索到 {n} 条证据', noResults:'未找到相符的已核对条目。请换用 NIHSS、D13 或 SeLECT 等关键词。', loadError:'知识库暂时无法加载，请稍后重试。', source:'查看来源 ↗', sourceUnknown:'来源未提供', verified:'核对状态', locator:'位置'
    },
    en: {
      pageTitle: 'Epilepsy Research Platform · Research Paths', brand: 'EPILEPSY RESEARCH', hero: 'Choose a research <span class="accent">path</span>', import: 'Import your data ↗', toggle: 'Q&A · Settings', toggleAria: 'Open knowledge Q&A and settings', closeAria: 'Close sidebar', resizeAria: 'Drag to resize sidebar',
      ready: 'Research service connected', failed: 'Model integrity check failed', unavailable: 'Service unavailable; check the local server', connecting: 'Connecting to research service…',
      modules: [['Knowledge Q&A','Search evidence and sources by topic'],['Knowledge graph','Post stroke epilepsy · SeLECT / D13']],
      scenes: {
        '02':['Teaching demo available','After medication reduction','730 day recurrence risk · eight fields','View scenario ↗','Explore recurrence risk within 730 days after the first actual reduction in antiseizure medication dose.'],
        '01':['Real cohort prediction demo','First seizure','Wenzhou Study D · prediction after first seizure','View scenario ↗','After a first acute symptomatic seizure within seven days of stroke, the Wenzhou Study D eight-feature model estimates later PSE for research only.'],
        '03':['Real cohort prediction demo','Post stroke epilepsy','D13 frozen model · one year outcome','View scenario ↗','The frozen D13 public cohort model estimates the one year secondary epilepsy label from original coded fields for research only.'],
        '04':['Planned','Postoperative seizure','Prediction model and field rules pending','View scenario ↗','The prediction question, field rules and model for postoperative seizures are still being defined.','Forward prediction and inverse design are not yet available for this scenario.'],
        '05':['Planned','After long term control','Prediction model and field rules pending','View scenario ↗','The prediction question, field rules and model for long term control are still being defined.','Forward prediction and inverse design are not yet available for this scenario.']
      },
      back:'← Back to paths', actions:{'02':['Forward prediction','Inverse design','Batch data import'],'01':['Forward prediction','Research evidence'],'03':['Forward prediction','Research evidence']}, note:'Medication reduction: synthetic teaching model · Post stroke: real cohort prediction research demo · Not for clinical decisions',
      sidebarTitle:'Knowledge Q&A', qaTab:'Knowledge Q&A', settingsTab:'Settings', status:'Evidence search · LLM service pending', intro:'Search verified D13 post stroke epilepsy material and inspect the original evidence and source. LLM answers are not yet available.', searchLabel:'Search the knowledge base', placeholder:'e.g. NIHSS and post stroke epilepsy', search:'Search', examplesLabel:'Suggested searches', examples:['NIHSS','D13 sample size','SeLECT score'], scope:'D13 post stroke epilepsy material only. Do not use for individual recurrence prediction after medication reduction or clinical decisions.', settingsTitle:'Interface settings', languageLabel:'Interface language', languageHelp:'Change the opening screen and right panel', settingsNote:'Your language choice is saved in this browser. Evidence statements remain in the original language.', results:'{n} evidence items', noResults:'No matching verified evidence. Try NIHSS, D13 or SeLECT.', loadError:'The knowledge base could not be loaded. Please try again.', source:'View source ↗', sourceUnknown:'Source unavailable', verified:'Status', locator:'Location'
    }
  };
  let lang = localStorage.getItem('research-language') === 'en' ? 'en' : 'zh';
  let claims = null, sources = null, lastQuery = '';
  const put = (selector, value) => { const el = $(selector); if (el) el.textContent = value; };
  function translate() {
    const t = copy[lang];
    document.documentElement.lang = lang === 'zh' ? 'zh-CN' : 'en';
    document.title = t.pageTitle;
    put('.brand span:last-child', t.brand);
    $('#hero-title').innerHTML = t.hero;
    put('.platform-import-label', t.import);
    put('#sidebar-toggle-label', t.toggle);
    toggle.setAttribute('aria-label', t.toggleAria);
    $('#sidebar-close').setAttribute('aria-label', t.closeAria);
    resizeHandle.setAttribute('aria-label', t.resizeAria);
    const status = $('#service-status');
    const previous = status.dataset.state || 'connecting';
    status.textContent = t[previous];
    document.querySelectorAll('.module-card').forEach((el, i) => { el.querySelector('strong').textContent = t.modules[i][0]; el.querySelector('small').textContent = t.modules[i][1]; });
    document.querySelectorAll('#scene-grid .scene, #scene-focus .scene').forEach(el => {
      const s = t.scenes[el.dataset.scene]; if (!s) return;
      const fields = ['.state','h2','.teaser','.open-hint','.detail-description','.planned-note'];
      fields.forEach((selector, i) => { const field = el.querySelector(selector); if (field && s[i]) field.textContent = s[i]; });
      const back = el.querySelector('.back-btn'); if (back) back.textContent = t.back;
      el.querySelectorAll('.actions .cta').forEach((button, i) => { const icon = button.querySelector('span'); button.textContent = (t.actions[el.dataset.scene] || [])[i] + ' '; if (icon) button.appendChild(icon); });
      el.setAttribute('aria-label', s[1]);
    });
    put('.research-note', t.note);
    put('#sidebar-title', t.sidebarTitle); put('#sidebar-tab-qa', t.qaTab); put('#sidebar-tab-settings', t.settingsTab);
    put('#qa-status-text', t.status); put('#qa-intro', t.intro); put('#qa-label', t.searchLabel); $('#qa-query').placeholder = t.placeholder; put('#qa-submit', t.search);
    put('#qa-examples-label', t.examplesLabel); put('#qa-scope', t.scope); put('#settings-title', t.settingsTitle); put('#language-label', t.languageLabel); put('#language-help', t.languageHelp); put('#settings-note', t.settingsNote);
    $('#language-zh').setAttribute('aria-pressed', String(lang === 'zh')); $('#language-en').setAttribute('aria-pressed', String(lang === 'en'));
    const examples = $('#qa-examples'); examples.replaceChildren();
    t.examples.forEach(query => { const button = document.createElement('button'); button.type = 'button'; button.textContent = query; button.addEventListener('click', () => { $('#qa-query').value = query; search(query); }); examples.appendChild(button); });
    if (lastQuery) renderResults(lastQuery);
    document.dispatchEvent(new CustomEvent('research:language', { detail: { lang } }));
  }
  function setView(view) {
    for (const key of Object.keys(views)) { views[key].hidden = key !== view; tabs[key].classList.toggle('active', key === view); tabs[key].setAttribute('aria-selected', String(key === view)); }
    put('#sidebar-title', view === 'qa' ? copy[lang].qaTab : copy[lang].settingsTab);
  }
  function open(view = 'qa') { panel.hidden = false; document.body.classList.add('sidebar-open'); toggle.setAttribute('aria-expanded','true'); setView(view); (view === 'qa' ? $('#qa-query') : $('#language-zh')).focus({preventScroll:true}); }
  function close() { panel.hidden = true; document.body.classList.remove('sidebar-open'); toggle.setAttribute('aria-expanded','false'); toggle.focus({preventScroll:true}); }
  const defaultSidebarWidth = 390;
  const savedSidebarWidth = Number(localStorage.getItem('research-sidebar-width'));
  function widthBounds() { return { min: 300, max: Math.max(300, Math.min(760, innerWidth - 500)) }; }
  function setSidebarWidth(value, persist = false) {
    const { min, max } = widthBounds();
    const width = Math.max(min, Math.min(max, Math.round(value)));
    document.documentElement.style.setProperty('--sidebar-width', width + 'px');
    resizeHandle.setAttribute('aria-valuemin', String(min));
    resizeHandle.setAttribute('aria-valuemax', String(max));
    resizeHandle.setAttribute('aria-valuenow', String(width));
    if (persist) localStorage.setItem('research-sidebar-width', String(width));
  }
  setSidebarWidth(Number.isFinite(savedSidebarWidth) && savedSidebarWidth >= 300 ? savedSidebarWidth : defaultSidebarWidth);
  addEventListener('resize', () => setSidebarWidth(Number(resizeHandle.getAttribute('aria-valuenow')) || defaultSidebarWidth));
  resizeHandle.addEventListener('pointerdown', event => {
    if (innerWidth <= 900) return;
    event.preventDefault();
    resizeHandle.setPointerCapture(event.pointerId);
    document.body.classList.add('sidebar-resizing');
    setSidebarWidth(innerWidth - event.clientX);
  });
  resizeHandle.addEventListener('pointermove', event => {
    if (resizeHandle.hasPointerCapture(event.pointerId)) setSidebarWidth(innerWidth - event.clientX);
  });
  function finishResize(event) {
    if (resizeHandle.hasPointerCapture(event.pointerId)) resizeHandle.releasePointerCapture(event.pointerId);
    document.body.classList.remove('sidebar-resizing');
    localStorage.setItem('research-sidebar-width', resizeHandle.getAttribute('aria-valuenow'));
  }
  resizeHandle.addEventListener('pointerup', finishResize);
  resizeHandle.addEventListener('pointercancel', finishResize);
  resizeHandle.addEventListener('dblclick', () => setSidebarWidth(defaultSidebarWidth, true));
  resizeHandle.addEventListener('keydown', event => {
    const current = Number(resizeHandle.getAttribute('aria-valuenow'));
    const next = event.key === 'ArrowLeft' ? current + 24 : event.key === 'ArrowRight' ? current - 24 : event.key === 'Home' ? defaultSidebarWidth : null;
    if (next !== null) { event.preventDefault(); setSidebarWidth(next, true); }
  });
  window.openResearchSidebar = open;
  toggle.addEventListener('click', () => panel.hidden ? open('qa') : close());
  $('#sidebar-close').addEventListener('click', close);
  tabs.qa.addEventListener('click', () => setView('qa'));
  tabs.settings.addEventListener('click', () => setView('settings'));
  document.querySelectorAll('[data-lang]').forEach(button => button.addEventListener('click', () => { lang = button.dataset.lang; localStorage.setItem('research-language', lang); translate(); setView('settings'); }));
  document.addEventListener('keydown', event => { if (event.key === 'Escape' && !panel.hidden) close(); });
  const serviceStatus = $('#service-status');
  new MutationObserver(() => { const value = serviceStatus.textContent; const zh = copy.zh, en = copy.en; for (const state of ['ready','failed','unavailable','connecting']) { if (value === zh[state] || value === en[state]) { serviceStatus.dataset.state = state; if (value !== copy[lang][state]) serviceStatus.textContent = copy[lang][state]; return; } } }).observe(serviceStatus, {childList:true,characterData:true,subtree:true});
  function tokens(query) { const latin = query.toLowerCase().match(/[a-z0-9]+/g) || []; const han = query.match(/[\u3400-\u9fff]+/g) || []; return [...latin, ...han.flatMap(word => word.length > 2 ? [word, ...Array.from({length:word.length-1},(_,i)=>word.slice(i,i+2))] : [word])].filter(word => word.length > 1); }
  function score(claim, query) { const haystack = [claim.statement,claim.subject,claim.object,claim.predicate,claim.population,claim.source_locator].join(' ').toLowerCase(); const terms = tokens(query); if (!terms.length) return 0; const full = query.trim().toLowerCase(); return (haystack.includes(full) ? 8 : 0) + terms.reduce((sum,term) => sum + (haystack.includes(term) ? (term.length > 3 ? 2 : 1) : 0),0); }
  function renderResults(query) {
    const target = $('#qa-results'); target.replaceChildren();
    if (!claims || !sources) return;
    const t = copy[lang];
    const hits = claims.filter(c => ['已核查','已核对','已复算','已核验','交付包核对'].includes(c.status)).map(c => ({claim:c,score:score(c,query)})).filter(item => item.score > 0).sort((a,b) => b.score-a.score).slice(0,6);
    if (!hits.length) { const empty = document.createElement('div'); empty.className = 'qa-empty'; empty.textContent = t.noResults; target.appendChild(empty); return; }
    const heading = document.createElement('h3'); heading.className = 'qa-results-title'; heading.textContent = t.results.replace('{n}', hits.length); target.appendChild(heading);
    hits.forEach(({claim}) => {
      const card = document.createElement('article'); card.className = 'qa-result';
      const statement = document.createElement('p'); statement.textContent = claim.statement; card.appendChild(statement);
      const meta = document.createElement('div'); meta.className = 'qa-result-meta'; meta.textContent = `${claim.claim_id} · ${t.verified}: ${claim.status}${claim.source_locator ? ` · ${t.locator}: ${claim.source_locator}` : ''}`; card.appendChild(meta);
      const source = sources.find(item => item.source_id === claim.source_id);
      if (source && /^https:\/\//.test(source.url || '')) { const link = document.createElement('a'); link.href = source.url; link.target = '_blank'; link.rel = 'noopener noreferrer'; link.textContent = `${t.source} ${source.title || ''}`; card.appendChild(link); }
      else { const missing = document.createElement('div'); missing.className = 'qa-result-meta'; missing.textContent = t.sourceUnknown; card.appendChild(missing); }
      target.appendChild(card);
    });
  }
  async function search(query) {
    lastQuery = query.trim(); if (!lastQuery) return;
    const target = $('#qa-results'); target.replaceChildren();
    try {
      if (!claims || !sources) {
        const [claimResponse, sourceResponse] = await Promise.all([fetch('/knowledge-graph/evidence_claims.json'), fetch('/knowledge-graph/sources.json')]);
        if (!claimResponse.ok || !sourceResponse.ok) throw Error('knowledge base unavailable');
        [claims,sources] = await Promise.all([claimResponse.json(),sourceResponse.json()]);
      }
      renderResults(lastQuery);
    } catch { const empty = document.createElement('div'); empty.className = 'qa-empty'; empty.textContent = copy[lang].loadError; target.appendChild(empty); }
  }
  $('#qa-form').addEventListener('submit', event => { event.preventDefault(); search($('#qa-query').value); });
  translate();
})();
