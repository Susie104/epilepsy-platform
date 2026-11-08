(() => {
  const $ = selector => document.querySelector(selector);
  const chapters = ['chapter-home','chapter-reduction','chapter-data','chapter-qa','chapter-graph','chapter-future','chapter-closing'].map(id => document.getElementById(id));
  const requestedChapter = chapters.find(chapter => location.hash === `#${chapter.id}`);
  const reducedMotion = matchMedia('(prefers-reduced-motion: reduce)');
  const copy = {
    zh: {
      names: ['研究入口','减药后复发','数据接入','知识问答','知识图谱','未来展望','谢谢'], explore:'向下探索平台 ↓', chapter01:'01 / 06 · 预测场景', predictionTitle:'预测场景', reductionTitle:'从一次减药开始，', reductionAccent:'探索复发风险。', reductionBody:'录入首次实际减低抗发作药物剂量后的八项结构化字段，人工确认后，查看教学模型给出的 730 天复发风险与训练支持信息。', forwardLink:'进入正向预测 ↗', inverseLink:'探索逆向情景 ↗', days:'天观察窗口', fields:'项结构化字段', reductionNote:'教学合成数据用于研究联调；情景差异不代表干预效果。', chapter02:'02 / 06 · 数据接入', dataTitle:'让每一步都可核对。', dataBody:'从 CSV 到结果，按顺序完成预检、字段映射、人工确认、运行与导出。', step1Title:'导入', step1Body:'上传演示 CSV，检查文件与基本结构。', step2Title:'预检', step2Body:'定位必填、格式、取值范围和重复问题。', step3Title:'映射与确认', step3Body:'对齐字段含义，人工核对后再提交运行。', step4Title:'运行', step4Body:'查看研究联调结果和训练支持范围。', step5Title:'导出', step5Body:'导出带版本和用途标识的结果。', dataLink:'进入数据工作台 ↗', chapter03:'03 / 06 · 知识问答', qaTitle:'让问题回到', qaAccent:'证据。', qaBody:'检索已核查的 D13 卒中后癫痫资料，逐条查看原始陈述、核对状态与来源。LLM 生成回答仍待接入。', qaLink:'进入知识问答 ↗', previewLabel:'EVIDENCE / SOURCE', previewQuestion:'NIHSS 与卒中后癫痫有什么关系？', previewAnswer:'检索证据 · 查看来源 · 保留原文', chapter04:'04 / 06 · 知识图谱', graphTitle:'把研究资料，', graphAccent:'连起来。', graphBody:'沿着实体、关系、证据和来源浏览 D13 卒中后癫痫资料；图谱用于研究导览，不直接解释减药模型。', graphLink:'浏览知识图谱 ↗', chapter05:'05 / 06 · 未来展望', futureTitle:'下一步，建立可验证的研究流程。', futureBody:'从证据、数据、模型到临床验证，逐项推进并公开每一步的适用边界。', future1Title:'扩充证据', future1Body:'持续核对来源、补充研究材料与版本信息。', future2Title:'规范数据', future2Body:'完善字段定义、导入校验与人工确认流程。', future3Title:'验证模型', future3Body:'锁定模型版本，在独立样本中检验表现。', future4Title:'推进转化', future4Body:'明确适用人群、研究用途与人工复核要求。', planned:'待推进', prevChapter:'上一章', nextChapter:'下一章', prevItem:'上一项', nextItem:'下一项', closingFirst:'让 AI 成为医生的', closingAssistant:'信息助手', closingComma:'，', closingSecond:'而不是患者的', closingDecision:'决策者', closingPeriod:'。', closingName:'梁苏蕾'
    },
    en: {
      names: ['Research paths','After medication reduction','Data import','Knowledge Q&A','Knowledge graph','Future directions','Thank you'], explore:'Explore the platform ↓', chapter01:'01 / 06 · PREDICTION SCENARIOS', predictionTitle:'Prediction scenarios', reductionTitle:'Start with one reduction.', reductionAccent:'Explore recurrence risk.', reductionBody:'Enter eight structured fields after the first actual reduction in antiseizure medication. After human review, inspect the teaching model’s 730 day recurrence risk and training support information.', forwardLink:'Forward prediction ↗', inverseLink:'Explore inverse scenarios ↗', days:'day observation window', fields:'structured fields', reductionNote:'Synthetic teaching data supports research integration. Scenario differences do not demonstrate intervention effects.', chapter02:'02 / 06 · DATA IMPORT', dataTitle:'Make every step reviewable.', dataBody:'From CSV to results: precheck, field mapping, human confirmation, model run, and export.', step1Title:'Import', step1Body:'Upload a teaching CSV and check its basic structure.', step2Title:'Precheck', step2Body:'Find required field, format, range, and duplicate issues.', step3Title:'Map and confirm', step3Body:'Align field meanings and review them before running.', step4Title:'Run', step4Body:'Inspect research results and training support range.', step5Title:'Export', step5Body:'Export results with version and use labels.', dataLink:'Open the data workspace ↗', chapter03:'03 / 06 · KNOWLEDGE Q&A', qaTitle:'Bring questions back to', qaAccent:'evidence.', qaBody:'Search verified D13 post stroke epilepsy material and inspect original statements, review status, and sources. LLM generated answers are pending.', qaLink:'Open Knowledge Q&A ↗', previewLabel:'EVIDENCE / SOURCE', previewQuestion:'How is NIHSS related to post stroke epilepsy?', previewAnswer:'Find evidence · inspect sources · preserve original text', chapter04:'04 / 06 · KNOWLEDGE GRAPH', graphTitle:'Connect the research', graphAccent:'materials.', graphBody:'Explore entities, relationships, evidence, and sources in D13 post stroke epilepsy material. The graph is a research guide and does not explain the medication reduction model.', graphLink:'Explore the knowledge graph ↗', chapter05:'05 / 06 · FUTURE DIRECTIONS', futureTitle:'Build a verifiable research pathway.', futureBody:'Advance evidence, data, model validation, and translation with clear limits at every step.', future1Title:'Expand evidence', future1Body:'Review sources and grow versioned research material.', future2Title:'Standardize data', future2Body:'Improve field definitions, import checks, and human review.', future3Title:'Validate models', future3Body:'Lock model versions and test performance on independent samples.', future4Title:'Plan translation', future4Body:'Define intended users, research use, and human review.', planned:'Next phase', prevChapter:'Previous chapter', nextChapter:'Next chapter', prevItem:'Previous item', nextItem:'Next item', closingFirst:'Let AI be a clinician’s ', closingAssistant:'information assistant', closingComma:',', closingSecond:'while patients retain ', closingDecision:'their decision-making role', closingPeriod:'.', closingName:'Susie'
    }
  };
  let lang = localStorage.getItem('research-language') === 'en' ? 'en' : 'zh';
  let activeChapter = -1;
  let initializing = true;
  const rail = $('#chapter-data');
  function translate() {
    const t = copy[lang];
    document.querySelectorAll('[data-story]').forEach(el => { if (t[el.dataset.story] !== undefined) el.textContent = t[el.dataset.story]; });
    $('#chapter-prev').setAttribute('aria-label',t.prevChapter); $('#chapter-next').setAttribute('aria-label',t.nextChapter);
    for (const id of ['prediction-prev','data-prev','future-prev']) $('#' + id).setAttribute('aria-label',t.prevItem);
    for (const id of ['prediction-next','data-next','future-next']) $('#' + id).setAttribute('aria-label',t.nextItem);
    if (activeChapter >= 0) $('#chapter-name').textContent = t.names[activeChapter];
  }
  document.addEventListener('research:language', event => { lang = event.detail.lang; translate(); });
  let pageMotion = 0;
  function scrollToChapter(index) {
    const chapter = chapters[index];
    if (!chapter) return;
    cancelAnimationFrame(pageMotion);
    const start = scrollY;
    const end = Math.min(start + chapter.getBoundingClientRect().top, document.documentElement.scrollHeight - innerHeight);
    if (reducedMotion.matches) {
      pageMotion = 0;
      scrollTo({top: end, behavior: 'instant'});
      return;
    }
    const began = performance.now();
    function frame(now) {
      const time = Math.min(1, (now - began) / 920);
      const eased = time * time * time * (time * (time * 6 - 15) + 10);
      scrollTo({top: start + (end - start) * eased, behavior: 'instant'});
      pageMotion = time < 1 ? requestAnimationFrame(frame) : 0;
    }
    pageMotion = requestAnimationFrame(frame);
  }
  for (const link of document.querySelectorAll('.hero-scroll-link')) {
    link.addEventListener('click', event => {
      if (event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
      const index = chapters.findIndex(chapter => link.hash === '#' + chapter.id);
      if (index === -1) return;
      event.preventDefault();
      scrollToChapter(index);
    });
  }
  addEventListener('wheel', event => {
    if (reducedMotion.matches || event.ctrlKey || Math.abs(event.deltaX) > Math.abs(event.deltaY) || !event.deltaY) return;
    if (event.target.closest?.('.research-sidebar,[role="dialog"],textarea,input,select')) return;
    if (pageMotion) { event.preventDefault(); return; }
    const direction = Math.sign(event.deltaY);
    const index = chapters.findLastIndex(chapter => chapter.getBoundingClientRect().top <= 3);
    if (index === -1 || !chapters[index + direction]) return;
    const rect = chapters[index].getBoundingClientRect();
    // A section taller than the screen keeps normal scrolling until its edge.
    const nearEdge = direction > 0 ? rect.bottom - innerHeight <= 80 : rect.top >= -3;
    if (nearEdge) {
      event.preventDefault();
      scrollToChapter(index + direction);
    }
  }, {passive: false});
  addEventListener('touchstart', () => {
    cancelAnimationFrame(pageMotion);
    pageMotion = 0;
  }, {passive: true});
  $('#chapter-prev').addEventListener('click', () => scrollToChapter(activeChapter-1));
  $('#chapter-next').addEventListener('click', () => scrollToChapter(activeChapter+1));
  function updateChapter() {
    let next = 0;
    for (let i=1;i<chapters.length;i++) if (chapters[i].getBoundingClientRect().top <= innerHeight*.52) next = i;
    if (next === activeChapter) return;
    activeChapter = next;
    $('#chapter-indicator').textContent = `${String(next).padStart(2,'0')} / ${String(chapters.length - 1).padStart(2,'0')}`;
    $('#chapter-name').textContent = copy[lang].names[next];
    $('#chapter-prev').disabled = next === 0;
    $('#chapter-next').disabled = next === chapters.length-1;
    if (!initializing) history.replaceState(null,'',`${location.pathname}${location.search}#${chapters[next].id}`);
  }
  const video = $('#story-rail-video');
  function syncVideo(visible) { if (reducedMotion.matches || document.hidden || !visible) { video.pause(); return; } if (!video.src) video.src = video.dataset.src; video.play().catch(() => {}); }
  let videoVisible = false;
  new IntersectionObserver(([entry]) => { videoVisible = entry.isIntersecting; syncVideo(videoVisible); },{rootMargin:'350px'}).observe(rail);
  document.addEventListener('visibilitychange', () => syncVideo(videoVisible)); reducedMotion.addEventListener('change', () => syncVideo(videoVisible));
  let ticking = false;
  addEventListener('scroll', () => { if (ticking) return; ticking=true; requestAnimationFrame(() => { updateChapter(); ticking=false; }); },{passive:true});
  addEventListener('resize', updateChapter);
  translate(); updateChapter();
  requestAnimationFrame(() => { if (requestedChapter) requestedChapter.scrollIntoView({behavior:'instant',block:'start'}); initializing=false; updateChapter(); });
})();
