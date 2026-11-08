
(() => {
  const reduced = matchMedia('(prefers-reduced-motion: reduce)');
  const art = [
    '<path d="M155 110H285V165H410V230H545V292H710"/><path d="M155 110H710" opacity=".24"/><circle cx="545" cy="292" r="57" opacity=".35"/><circle cx="545" cy="292" r="9" fill="#c2f778"/>',
    '<path d="M90 218H272L322 185L353 264L404 92L452 296L502 214L536 226H722"/><circle cx="404" cy="92" r="32" opacity=".35"/><circle cx="404" cy="92" r="7" fill="#c2f778"/>',
    '<path d="M421 332V182L322 106M421 207L526 102M321 106L219 75M322 106L279 175M526 102L610 70M526 102L575 181"/><circle cx="421" cy="207" r="76" opacity=".26"/><circle cx="421" cy="207" r="10" fill="#c2f778"/>',
    '<ellipse cx="420" cy="192" rx="225" ry="135"/><ellipse cx="420" cy="192" rx="145" ry="88" opacity=".5"/><path d="M420 40V344M170 192H670" stroke-dasharray="5 10"/><circle cx="420" cy="192" r="32"/><circle cx="420" cy="192" r="9" fill="#c2f778"/>',
    '<path d="M106 266C185 266 194 109 267 109S337 258 404 258 471 172 537 172 614 191 722 191"/><path d="M106 191H722" opacity=".28" stroke-dasharray="5 10"/><circle cx="537" cy="172" r="37" opacity=".35"/><circle cx="537" cy="172" r="8" fill="#c2f778"/>'
  ];
  const titles = {
    zh: ['减药后复发', '首次发作', '卒中后癫痫', '术后发作', '长期控制后'],
    en: ['Recurrence after medication reduction', 'First seizure', 'Post stroke epilepsy', 'Postoperative seizure', 'After long term control']
  };
  const descriptions = {
    zh: ['首次减量后，探索教学模型给出的 730 天复发风险。', '卒中后早期首次发作：温州 D 研究模型预测后续晚期 PSE。', 'D13 公开真实队列的冻结模型预测一年内结局标签。', '确定术后随访的时间窗口、字段和预测结局。', '定义长期控制后的观察起点及复发结局。'],
    en: ['Explore 730 day recurrence risk after the first reduction with the teaching model.', 'After an early post stroke seizure, use the Wenzhou Study D model to estimate later PSE.', 'The frozen D13 public cohort model estimates the one year outcome label.', 'Define follow-up windows, fields, and outcomes after surgery.', 'Define the observation baseline and recurrence outcome after long term control.']
  };
  const prediction = document.querySelector('#prediction-carousel .prediction-track');
  art.forEach((drawing, index) => {
    const slide = document.createElement('article');
    slide.className = 'prediction-slide';
    slide.dataset.sceneIndex = index;
    slide.innerHTML = '<svg aria-hidden="true" viewBox="0 0 820 380" fill="none" stroke="currentColor" stroke-width="2.5">' + drawing +
      '</svg><div class="prediction-copy"><span class="prediction-state"></span><h3></h3><p></p>' +
      (index === 0 ? '<div class="prediction-figures"><div><strong class="story-number">730</strong><span data-story="days">天观察窗口</span></div><div><strong class="story-number">08</strong><span data-story="fields">项结构化字段</span></div></div><div class="story-actions"><a href="/workspace?view=single&amp;scenario=forward"></a><a class="story-secondary" href="/workspace?view=single&amp;scenario=reverse"></a></div>' : index === 1 ? '<div class="story-actions"><a href="/workspace?view=single&amp;scenario=first"></a></div>' : index === 2 ? '<div class="story-actions"><a href="/workspace?view=single&amp;scenario=stroke"></a></div>' : '') + '</div>';
    prediction.append(slide);
  });

  function makeLoop(viewport, track, prefix) {
    const cards = [...track.children];
    const count = cards.length;
    const clone = card => {
      const copy = card.cloneNode(true);
      copy.inert = true;
      copy.setAttribute('aria-hidden', 'true');
      return copy;
    };
    track.prepend(...cards.map(clone));
    track.append(...cards.map(clone));
    viewport.classList.add('loop-window');
    track.classList.add('loop-track');
    if (prefix !== 'prediction') {
      makeScan(viewport, track, count, prefix);
      return;
    }
    let index = count;
    let motion;
    let timer;
    let visible = false;
    let touchStart;
    const offset = () => track.children[index].offsetLeft;
    const position = () => 'translate3d(' + (-offset()) + 'px, 0, 0)';

    function settle() {
      index = count + (index % count);
      track.style.transform = position();
      motion?.cancel();
      motion = undefined;
      viewport.dataset.activeSlide = String(index - count + 1);
      cards.forEach((card, n) => { card.inert = n !== index - count; });
    }

    function schedule(delay = 3000) {
      clearTimeout(timer);
      if (visible && !document.hidden && !reduced.matches && !viewport.matches(':focus-within')) {
        timer = setTimeout(() => move(1), delay);
      }
    }

    function move(direction, manual = false) {
      if (motion) settle();
      const from = position();
      index += direction;
      viewport.dispatchEvent(new CustomEvent('prediction:change', {
        detail: {index: index % count, direction}
      }));
      const to = position();
      track.style.transform = to;
      if (reduced.matches) {
        settle();
      } else {
        motion = track.animate([{transform: from}, {transform: to}], {
          duration: 620,
          easing: 'cubic-bezier(.22,.72,.18,1)'
        });
        motion.onfinish = settle;
      }
      schedule(manual ? 4600 : 3000);
    }

    document.getElementById(prefix + '-prev').addEventListener('click', () => move(-1, true));
    document.getElementById(prefix + '-next').addEventListener('click', () => move(1, true));
    viewport.addEventListener('touchstart', event => {
      touchStart = event.touches[0].clientX;
      clearTimeout(timer);
    }, {passive: true});
    viewport.addEventListener('touchend', event => {
      const distance = event.changedTouches[0].clientX - touchStart;
      if (Math.abs(distance) > 38) move(distance < 0 ? 1 : -1, true);
      else schedule(4600);
    }, {passive: true});
    viewport.addEventListener('touchcancel', () => schedule(4600));
    viewport.addEventListener('focusin', () => clearTimeout(timer));
    viewport.addEventListener('focusout', () => setTimeout(() => schedule(4600), 0));
    new IntersectionObserver(([entry]) => {
      visible = entry.isIntersecting;
      schedule();
    }, {threshold: .12}).observe(viewport);
    new ResizeObserver(settle).observe(viewport);
    document.addEventListener('visibilitychange', () => schedule());
    reduced.addEventListener('change', () => { settle(); schedule(); });
    settle();
  }

  function makeScan(viewport, track, count, prefix) {
    viewport.classList.add('scan-window');
    track.classList.add('scan-track');
    const next = document.getElementById(prefix + '-next');
    const pauseButton = document.createElement('button');
    pauseButton.type = 'button';
    pauseButton.className = 'scan-toggle';
    next.after(pauseButton);
    let visible = false;
    let paused = false;
    let touchStart;
    let frameId = 0;
    let previousTime = 0;
    let offset = 0;
    let stride = 0;
    let origin = 0;
    let manualMove;
    let resumeAt = 0;

    function draw() {
      const cycle = stride * count;
      const position = ((offset % cycle) + cycle) % cycle;
      track.style.transform = 'translate3d(' + (-(origin + position)) + 'px, 0, 0)';
    }

    function canRun() {
      return visible && !document.hidden && !paused && touchStart === undefined && !reduced.matches;
    }

    function sync() {
      if (frameId) cancelAnimationFrame(frameId);
      frameId = 0;
      previousTime = 0;
      if (stride && (manualMove || canRun())) frameId = requestAnimationFrame(tick);
    }

    function tick(now) {
      frameId = 0;
      if (manualMove) {
        const progress = Math.min(1, (now - manualMove.start) / 540);
        const eased = 1 - (1 - progress) ** 3;
        offset = manualMove.from + (manualMove.to - manualMove.from) * eased;
        if (progress === 1) {
          manualMove = undefined;
          resumeAt = now + 1400;
        }
      } else if (previousTime && now >= resumeAt) {
        offset = (offset + Math.min(now - previousTime, 48) * .042) % (stride * count);
      }
      previousTime = now;
      draw();
      if (manualMove || canRun()) frameId = requestAnimationFrame(tick);
    }

    function step(direction) {
      if (!stride) return;
      const current = offset / stride;
      const index = direction > 0 ? Math.floor(current + .015) + 1 : Math.ceil(current - .015) - 1;
      const to = index * stride;
      if (reduced.matches) {
        offset = to;
        draw();
        return;
      }
      manualMove = {start: performance.now(), from: offset, to};
      sync();
    }

    function measure() {
      const first = track.children[count].getBoundingClientRect();
      const following = track.children[count + 1].getBoundingClientRect();
      const position = stride ? offset / stride : 0;
      stride = following.left - first.left;
      origin = stride * count;
      offset = position * stride;
      manualMove = undefined;
      if (stride > 0) draw();
      sync();
    }

    function labelPauseButton() {
      const en = document.documentElement.lang === 'en';
      pauseButton.textContent = paused ? '▶' : 'Ⅱ';
      const label = paused ? (en ? 'Resume auto scroll' : '继续自动滚动') : (en ? 'Pause auto scroll' : '暂停自动滚动');
      pauseButton.setAttribute('aria-label', label);
      pauseButton.title = label;
      pauseButton.hidden = reduced.matches;
    }

    document.getElementById(prefix + '-prev').addEventListener('click', () => step(-1));
    next.addEventListener('click', () => step(1));
    pauseButton.addEventListener('click', () => {
      paused = !paused;
      labelPauseButton();
      sync();
    });
    viewport.addEventListener('touchstart', event => {
      touchStart = event.touches[0].clientX;
      sync();
    }, {passive: true});
    viewport.addEventListener('touchend', event => {
      const delta = event.changedTouches[0].clientX - touchStart;
      touchStart = undefined;
      if (Math.abs(delta) > 38) step(delta < 0 ? 1 : -1);
      else sync();
    }, {passive: true});
    viewport.addEventListener('touchcancel', () => { touchStart = undefined; sync(); });
    new IntersectionObserver(([entry]) => { visible = entry.isIntersecting; sync(); }).observe(viewport);
    new ResizeObserver(measure).observe(viewport);
    document.addEventListener('visibilitychange', sync);
    document.addEventListener('research:language', labelPauseButton);
    reduced.addEventListener('change', () => {
      manualMove = undefined;
      if (reduced.matches && stride) {
        offset = Math.round(offset / stride) * stride;
        draw();
      }
      labelPauseButton();
      sync();
    });
    labelPauseButton();
    measure();
  }

  const future = document.getElementById('future-carousel');
  const futureTrack = document.createElement('div');
  futureTrack.append(...future.children);
  future.append(futureTrack);
  makeLoop(prediction.parentElement, prediction, 'prediction');
  makeLoop(document.getElementById('data-carousel-window'), document.getElementById('data-carousel-track'), 'data');
  makeLoop(future, futureTrack, 'future');

  const predictionViewport = prediction.parentElement;
  let predictionVisible = false;
  function loadPredictionArt() {
    if (!predictionVisible || reduced.matches) return;
    predictionObserver.disconnect();
    reduced.removeEventListener('change', loadPredictionArt);
    import('./prediction-art.js')
      .then(({mountPredictionArt}) => mountPredictionArt(predictionViewport))
      .catch(() => { /* The SVG in each slide is the static fallback. */ });
  }
  const predictionObserver = new IntersectionObserver(([entry]) => {
    predictionVisible = entry.isIntersecting;
    loadPredictionArt();
  }, {rootMargin: '180px 0px'});
  predictionObserver.observe(predictionViewport);
  reduced.addEventListener('change', loadPredictionArt);

  function translate() {
    const lang = document.documentElement.lang === 'en' ? 'en' : 'zh';
    prediction.querySelectorAll('.prediction-slide').forEach(slide => {
      const index = Number(slide.dataset.sceneIndex);
      slide.querySelector('h3').textContent = titles[lang][index];
      slide.querySelector('p').textContent = descriptions[lang][index];
      slide.querySelector('.prediction-state').textContent = lang === 'en'
        ? (index === 0 ? 'Teaching demo' : index === 1 || index === 2 ? 'Real cohort prediction demo' : 'Planned')
        : (index === 0 ? '教学演示' : index === 1 || index === 2 ? '真实队列预测演示' : '规划中');
      const links = slide.querySelectorAll('a');
      if (index === 0) {
        slide.querySelector('[data-story="days"]').textContent = lang === 'en' ? 'day observation window' : '天观察窗口';
        slide.querySelector('[data-story="fields"]').textContent = lang === 'en' ? 'structured fields' : '项结构化字段';
        links[0].textContent = lang === 'en' ? 'Forward prediction ↗' : '进入正向预测 ↗';
        links[1].textContent = lang === 'en' ? 'Inverse scenarios ↗' : '探索逆向情景 ↗';
      }
      if (index === 2 || index === 1) links[0].textContent = lang === 'en' ? 'Forward prediction ↗' : '进入正向预测 ↗';
    });
    document.querySelectorAll('.story-kicker').forEach(kicker => {
      const match = kicker.textContent.match(/^(\d+ \/ \d+)(.*)$/);
      if (!match) return;
      const number = document.createElement('span');
      number.className = 'story-number';
      number.textContent = match[1];
      kicker.replaceChildren(number, match[2]);
    });
  }
  document.addEventListener('research:language', translate);
  translate();

  function playVisibleBackground(container, activeClass, early = false) {
    const video = container.querySelector('video');
    let visible = false;
    let nearby = false;
    const threshold = early ? .01 : .15;
    function prepare() {
      if (!video.src && !reduced.matches) {
        if (early) video.preload = 'auto';
        video.src = video.dataset.src;
      }
    }
    function sync() {
      if (nearby) prepare();
      const playing = visible && !document.hidden && !reduced.matches;
      container.classList.toggle(activeClass, playing);
      if (!playing) {
        video.pause();
        return;
      }
      prepare();
      video.play().catch(() => {});
    }
    if (early) {
      const preload = new IntersectionObserver(([entry]) => {
        nearby = entry.isIntersecting;
        if (nearby) prepare();
        if (video.src) preload.disconnect();
      }, {rootMargin: '100% 0px'});
      preload.observe(container);
    }
    new IntersectionObserver(([entry]) => {
      visible = entry.intersectionRatio >= threshold;
      sync();
    }, {threshold}).observe(container);
    document.addEventListener('visibilitychange', sync);
    reduced.addEventListener('change', sync);
  }

  playVisibleBackground(document.getElementById('chapter-closing'), 'closing-moving');
  playVisibleBackground(document.getElementById('chapter-qa'), 'qa-moving');
  playVisibleBackground(document.getElementById('chapter-graph'), 'graph-moving', true);
  playVisibleBackground(document.getElementById('chapter-future'), 'future-moving');
  playVisibleBackground(document.getElementById('chapter-reduction'), 'reduction-moving', true);

  const tiltStage = document.querySelector('.evidence-tilt-stage');
  const evidenceCard = tiltStage.querySelector('.story-evidence-preview');
  function resetTilt() {
    evidenceCard.classList.remove('evidence-tracking');
    for (const property of ['--tilt-x', '--tilt-y', '--light-x', '--light-y']) {
      evidenceCard.style.removeProperty(property);
    }
  }
  tiltStage.addEventListener('pointermove', event => {
    if (event.pointerType !== 'mouse' || reduced.matches) return;
    const bounds = tiltStage.getBoundingClientRect();
    const x = (event.clientX - bounds.left) / bounds.width;
    const y = (event.clientY - bounds.top) / bounds.height;
    evidenceCard.classList.add('evidence-tracking');
    evidenceCard.style.setProperty('--tilt-x', (8 - y * 16).toFixed(2) + 'deg');
    evidenceCard.style.setProperty('--tilt-y', (x * 20 - 10).toFixed(2) + 'deg');
    evidenceCard.style.setProperty('--light-x', (x * 100).toFixed(1) + '%');
    evidenceCard.style.setProperty('--light-y', (y * 100).toFixed(1) + '%');
  });
  tiltStage.addEventListener('pointerleave', resetTilt);
  tiltStage.addEventListener('pointercancel', resetTilt);
  reduced.addEventListener('change', resetTilt);
})();

