(() => {
  const panel = document.getElementById('research-sidebar');
  const toggle = document.getElementById('sidebar-toggle');
  const closeButton = document.getElementById('sidebar-close');
  const resizeHandle = document.getElementById('sidebar-resize');
  const queryInput = document.getElementById('qa-query');
  const results = document.getElementById('qa-results');
  if (!panel || !toggle || !resizeHandle) return;

  function open() {
    panel.hidden = false;
    document.body.classList.add('workspace-sidebar-open');
    toggle.setAttribute('aria-expanded', 'true');
    queryInput.focus({ preventScroll: true });
  }
  function close() {
    panel.hidden = true;
    document.body.classList.remove('workspace-sidebar-open');
    toggle.setAttribute('aria-expanded', 'false');
    toggle.focus({ preventScroll: true });
  }
  toggle.addEventListener('click', () => panel.hidden ? open() : close());
  closeButton.addEventListener('click', close);
  document.addEventListener('keydown', event => {
    if (event.key === 'Escape' && !panel.hidden) close();
  });

  const defaultWidth = 390;
  const savedWidth = Number(localStorage.getItem('research-sidebar-width'));
  function widthBounds() { return { min:300, max:Math.max(300, Math.min(760, innerWidth - 500)) }; }
  function setWidth(value, persist = false) {
    const { min, max } = widthBounds();
    const width = Math.max(min, Math.min(max, Math.round(value)));
    document.documentElement.style.setProperty('--sidebar-width', `${width}px`);
    resizeHandle.setAttribute('aria-valuemin', String(min));
    resizeHandle.setAttribute('aria-valuemax', String(max));
    resizeHandle.setAttribute('aria-valuenow', String(width));
    if (persist) localStorage.setItem('research-sidebar-width', String(width));
  }
  setWidth(Number.isFinite(savedWidth) && savedWidth >= 300 ? savedWidth : defaultWidth);
  addEventListener('resize', () => setWidth(Number(resizeHandle.getAttribute('aria-valuenow')) || defaultWidth));
  resizeHandle.addEventListener('pointerdown', event => {
    if (innerWidth <= 1100) return;
    event.preventDefault();
    resizeHandle.setPointerCapture(event.pointerId);
    document.body.classList.add('sidebar-resizing');
    setWidth(innerWidth - event.clientX);
  });
  resizeHandle.addEventListener('pointermove', event => {
    if (resizeHandle.hasPointerCapture(event.pointerId)) setWidth(innerWidth - event.clientX);
  });
  function finishResize(event) {
    if (!resizeHandle.hasPointerCapture(event.pointerId)) return;
    resizeHandle.releasePointerCapture(event.pointerId);
    document.body.classList.remove('sidebar-resizing');
    localStorage.setItem('research-sidebar-width', resizeHandle.getAttribute('aria-valuenow'));
  }
  resizeHandle.addEventListener('pointerup', finishResize);
  resizeHandle.addEventListener('pointercancel', finishResize);
  resizeHandle.addEventListener('dblclick', () => setWidth(defaultWidth, true));
  resizeHandle.addEventListener('keydown', event => {
    const current = Number(resizeHandle.getAttribute('aria-valuenow'));
    const next = event.key === 'ArrowLeft' ? current + 24 : event.key === 'ArrowRight' ? current - 24 : event.key === 'Home' ? defaultWidth : null;
    if (next !== null) { event.preventDefault(); setWidth(next, true); }
  });

  let claims, sources;
  function terms(query) {
    const latin = query.toLowerCase().match(/[a-z0-9]+/g) || [];
    const han = query.match(/[\u3400-\u9fff]+/g) || [];
    return [...latin, ...han.flatMap(word => word.length > 2 ? [word, ...Array.from({length:word.length-1}, (_, i) => word.slice(i, i+2))] : [word])].filter(word => word.length > 1);
  }
  function score(claim, query) {
    const haystack = [claim.statement, claim.subject, claim.object, claim.predicate, claim.population, claim.source_locator].join(' ').toLowerCase();
    const words = terms(query);
    return (haystack.includes(query.toLowerCase()) ? 8 : 0) + words.reduce((sum, word) => sum + (haystack.includes(word) ? (word.length > 3 ? 2 : 1) : 0), 0);
  }
  function showMessage(message) {
    const box = document.createElement('div');
    box.className = 'qa-empty';
    box.textContent = message;
    results.replaceChildren(box);
  }
  function render(query) {
    const hits = claims.filter(claim => ['已核查','已核对','已复算','已核验','交付包核对'].includes(claim.status))
      .map(claim => ({ claim, rank:score(claim, query) }))
      .filter(item => item.rank > 0).sort((a, b) => b.rank - a.rank).slice(0, 6);
    if (!hits.length) { showMessage('未找到相符的已核对条目，请换一个关键词。'); return; }
    const heading = document.createElement('h3');
    heading.className = 'qa-results-title';
    heading.textContent = `检索到 ${hits.length} 条证据`;
    results.replaceChildren(heading);
    for (const { claim } of hits) {
      const card = document.createElement('article'); card.className = 'qa-result';
      const statement = document.createElement('p'); statement.textContent = claim.statement; card.appendChild(statement);
      const meta = document.createElement('div'); meta.className = 'qa-result-meta';
      meta.textContent = `${claim.claim_id} · 核对状态：${claim.status}${claim.source_locator ? ` · 位置：${claim.source_locator}` : ''}`;
      card.appendChild(meta);
      const source = sources.find(item => item.source_id === claim.source_id);
      if (source && /^https:\/\//.test(source.url || '')) {
        const link = document.createElement('a'); link.href = source.url; link.target = '_blank'; link.rel = 'noopener noreferrer';
        link.textContent = `查看来源 ↗ ${source.title || ''}`; card.appendChild(link);
      }
      results.appendChild(card);
    }
  }
  async function search(query) {
    query = query.trim();
    if (!query) { results.replaceChildren(); return; }
    showMessage('正在检索证据…');
    try {
      if (!claims || !sources) {
        const [claimResponse, sourceResponse] = await Promise.all([fetch('/knowledge-graph/evidence_claims.json'), fetch('/knowledge-graph/sources.json')]);
        if (!claimResponse.ok || !sourceResponse.ok) throw new Error('Knowledge base unavailable');
        [claims, sources] = await Promise.all([claimResponse.json(), sourceResponse.json()]);
      }
      render(query);
    } catch { showMessage('知识库暂时无法加载，请稍后重试。'); }
  }
  document.getElementById('qa-form').addEventListener('submit', event => { event.preventDefault(); search(queryInput.value); });
  document.querySelectorAll('#qa-examples [data-query]').forEach(button => button.addEventListener('click', () => {
    queryInput.value = button.dataset.query;
    search(queryInput.value);
  }));
})();
