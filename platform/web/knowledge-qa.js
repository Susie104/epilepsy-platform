(() => {
  const $ = selector => document.querySelector(selector);
  const form = $('#qa-search-form');
  const question = $('#qa-question');
  const results = $('#qa-results');
  const section = $('#qa-results-section');
  const video = $('#qa-video');
  const reducedMotion = matchMedia('(prefers-reduced-motion: reduce)');
  const dictionaries = {
    zh: {
      title: '知识问答 · 癫痫研究平台', brand: '癫痫研究平台', home: '研究入口', graph: '知识图谱', headline1: '让问题回到', headline2: '证据', questionLabel: '输入研究问题', placeholder: '例如：NIHSS 与卒中后癫痫有什么关系？', sourceOnly: '仅供研究参考', suggested: '试试这些问题', scrollCue: '向下查看证据 ↓', resultsKicker: 'SOURCE LED EXPLORATION', resultsTitle: '检索结果', footer: '研究资料导览 · 来源可追溯', openGraph: '进入知识图谱 ↗', source: '查看来源 ↗', unavailable: '来源未提供', noResults: '没有找到匹配的可核对证据。试试 NIHSS、D13 v0.3 或 SeLECT。', loadError: '知识库暂时无法读取，请稍后重试。', resultCount: '找到 {n} 条证据', verified: '核对状态', position: '位置', answerKicker: 'AI 综合回答 · 基于可核对证据', answerDisclaimer: '仅供研究参考，不构成临床建议', prompts: ['D13 v0.3 校正模型', 'SeLECT-ASyS 评分', 'NIHSS 与卒中后癫痫']
    },
    en: {
      title: 'Knowledge Q&A · Epilepsy Research', brand: 'EPILEPSY RESEARCH', home: 'Research paths', graph: 'Knowledge graph', headline1: 'Ask with ', headline2: 'evidence', questionLabel: 'Enter a research question', placeholder: 'For example: NIHSS and post stroke epilepsy', sourceOnly: 'For research reference only', suggested: 'Suggested searches', scrollCue: 'View evidence below ↓', resultsKicker: 'SOURCE LED EXPLORATION', resultsTitle: 'Evidence results', footer: 'Research guide · traceable sources', openGraph: 'Open knowledge graph ↗', source: 'View source ↗', unavailable: 'Source unavailable', noResults: 'No matching reviewable evidence. Try NIHSS, D13 v0.3, or SeLECT.', loadError: 'The knowledge base could not be loaded. Please try again.', resultCount: '{n} evidence items', verified: 'Status', position: 'Location', answerKicker: 'AI answer · from reviewable evidence', answerDisclaimer: 'Research reference only, not clinical advice', prompts: ['D13 v0.3 model', 'SeLECT-ASyS score', 'NIHSS']
    }
  };
  let lang = localStorage.getItem('research-language') === 'en' ? 'en' : 'zh';
  let claims = null, sources = null, lastQuery = '', qaData = null;
  function translate() {
    const t = dictionaries[lang];
    document.documentElement.lang = lang === 'zh' ? 'zh-CN' : 'en';
    document.title = t.title;
    document.querySelectorAll('[data-i18n]').forEach(el => { el.textContent = t[el.dataset.i18n]; });
    question.placeholder = t.placeholder;
    $('#qa-language').textContent = lang === 'zh' ? 'EN' : '中';
    $('#qa-language').setAttribute('aria-label', lang === 'zh' ? 'Switch to English' : '切换为中文');
    const list = $('#qa-prompt-list'); list.replaceChildren();
    t.prompts.forEach(prompt => { const button = document.createElement('button'); button.type = 'button'; button.textContent = prompt; button.addEventListener('click', () => { question.value = prompt; updateCounter(); search(prompt); }); list.appendChild(button); });
    if (lastQuery && !section.hidden) render(lastQuery);
  }
  function updateCounter() { $('#qa-counter').textContent = `${question.value.length} / 200`; }
  function tokens(query) {
    const latin = query.toLowerCase().match(/[a-z0-9]+/g) || [];
    const han = query.match(/[\u3400-\u9fff]+/g) || [];
    return [...latin, ...han.flatMap(word => word.length > 2 ? [word, ...Array.from({length:word.length-1},(_,i) => word.slice(i,i+2))] : [word]), ...(query.includes('样本量') ? ['患者'] : [])].filter(word => word.length > 1);
  }
  function score(claim, query) {
    const haystack = [claim.statement,claim.subject,claim.object,claim.predicate,claim.population,claim.source_locator].join(' ').toLowerCase();
    const parts = tokens(query); if (!parts.length) return 0;
    if (['d13','asys','select-eeg','温州','苏州','winder'].some(anchor => query.toLowerCase().includes(anchor) && !haystack.includes(anchor))) return 0;
    const matches = parts.filter(part => haystack.includes(part));
    if (parts.length >= 3 && matches.length < Math.max(2,Math.round(parts.length * .4))) return 0;
    return (haystack.includes(query.toLowerCase()) ? 8 : 0) + matches.reduce((sum,part) => sum + (part.length > 3 ? 2 : 1),0);
  }
  function sourceHref(source) {
    const url = source?.url || '';
    if (/^https:\/\//.test(url)) return url;
    if (/^\/knowledge-graph\/assets\/sources\/[^?#]+$/.test(url) && !url.includes('..')) return url;
    return null;
  }
  function empty(message) { const card = document.createElement('div'); card.className = 'qa-empty'; card.textContent = message; results.appendChild(card); }
  function render(query) {
    const t = dictionaries[lang]; results.replaceChildren();
    if (qaData && qaData.question === query) results.appendChild(answerCard(qaData, t));
    if (!claims || !sources) return;
    const matches = claims.filter(c => ['已核查','已核对','已复算','已核验','交付包核对'].includes(c.status)).map(claim => ({claim,score:score(claim,query)})).filter(item => item.score > 0).sort((a,b) => b.score - a.score).slice(0,8);
    $('#qa-result-count').textContent = t.resultCount.replace('{n}',matches.length);
    if (!matches.length) { empty(t.noResults); return; }
    matches.forEach(({claim}) => {
      const card = document.createElement('article'); card.className = 'qa-evidence';
      const statement = document.createElement('p'); statement.textContent = claim.statement; card.appendChild(statement);
      const meta = document.createElement('div'); meta.className = 'qa-evidence-meta'; meta.textContent = `${claim.claim_id} · ${t.verified}: ${claim.status}${claim.source_locator ? ` · ${t.position}: ${claim.source_locator}` : ''}`; card.appendChild(meta);
      const source = sources.find(item => item.source_id === claim.source_id);
      if (sourceHref(source)) { const link = document.createElement('a'); link.href = sourceHref(source); link.target = '_blank'; link.rel = 'noopener noreferrer'; link.textContent = `${t.source} ${source.title || ''}`; card.appendChild(link); }
      else { const missing = document.createElement('div'); missing.className = 'qa-evidence-meta'; missing.textContent = t.unavailable; card.appendChild(missing); }
      results.appendChild(card);
    });
  }
  function answerCard(data, t) {
    const card = document.createElement('article'); card.className = 'qa-answer';
    const kicker = document.createElement('p'); kicker.className = 'qa-answer-kicker'; kicker.textContent = t.answerKicker; card.appendChild(kicker);
    const body = document.createElement('p'); body.className = 'qa-answer-body'; body.textContent = data.answer; card.appendChild(body);
    if (Array.isArray(data.citations) && data.citations.length) {
      const chips = document.createElement('div'); chips.className = 'qa-answer-cites';
      data.citations.forEach(c => {
        const chip = document.createElement('span'); chip.className = 'qa-cite';
        const src = sources && sources.find(item => item.source_id === c.source_id);
        const label = c.claim_id + (src && src.title ? ' · ' + src.title : '');
        if (sourceHref(src)) { const a = document.createElement('a'); a.href = sourceHref(src); a.target = '_blank'; a.rel = 'noopener noreferrer'; a.textContent = label; chip.appendChild(a); }
        else { chip.textContent = label; }
        chips.appendChild(chip);
      });
      card.appendChild(chips);
    }
    const note = document.createElement('div'); note.className = 'qa-answer-note';
    note.textContent = (data.disclaimer || t.answerDisclaimer) + (data.model ? ' · ' + data.model : '');
    card.appendChild(note);
    return card;
  }
  async function askModel(query) {
    try {
      const resp = await fetch('/api/v1/knowledge-qa', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ question: query }) });
      if (!resp.ok) return;
      const data = await resp.json();
      if (!data.llm_available || !data.answer) return;
      qaData = data;
      if (query === lastQuery) render(query);
    } catch { /* 模型不可用则静默退回纯检索 */ }
  }
  async function search(rawQuery) {
    const query = rawQuery.trim(); if (!query) { question.focus(); return; }
    lastQuery = query; section.hidden = false; document.body.classList.add('has-results');
    results.replaceChildren(); $('#qa-result-count').textContent = ''; qaData = null;
    try {
      if (!claims || !sources) {
        const [claimResponse,sourceResponse] = await Promise.all([fetch('/knowledge-graph/evidence_claims.json'),fetch('/knowledge-graph/sources.json')]);
        if (!claimResponse.ok || !sourceResponse.ok) throw Error('knowledge base unavailable');
        [claims,sources] = await Promise.all([claimResponse.json(),sourceResponse.json()]);
      }
      render(query);
    } catch { empty(dictionaries[lang].loadError); }
    askModel(query);
    section.scrollIntoView({behavior:reducedMotion.matches ? 'instant' : 'smooth',block:'start'});
  }
  form.addEventListener('submit', event => { event.preventDefault(); search(question.value); });
  question.addEventListener('input', updateCounter);
  question.addEventListener('keydown', event => { if (event.key === 'Enter' && !event.shiftKey) { event.preventDefault(); search(question.value); } });
  $('#qa-language').addEventListener('click', () => { lang = lang === 'zh' ? 'en' : 'zh'; localStorage.setItem('research-language',lang); translate(); });
  function syncVideo() { if (reducedMotion.matches || document.hidden) video.pause(); else video.play().catch(() => {}); }
  document.addEventListener('visibilitychange', syncVideo); reducedMotion.addEventListener('change',syncVideo);
  translate(); syncVideo();
})();
