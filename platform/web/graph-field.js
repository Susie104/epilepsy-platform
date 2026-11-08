function mountNetworkField(canvas) {
  const context = canvas.getContext('2d');
  if (!context) return;
  const reduced = matchMedia('(prefers-reduced-motion: reduce)');
  const tints = ['#ac8ee5', '#81bcaa', '#bfa0dd'];
  const columns = 17;
  const rows = 5;
  const nodes = [];
  const links = [[], [], []];
  let width = 0;
  let height = 0;
  let visible = false;
  let frame = 0;
  let lastDraw = 0;
  let time = 0;

  for (let layer = 0; layer < 2; layer++) {
    for (let column = 0; column < columns; column++) {
      for (let row = 0; row < rows; row++) {
        const phase = column * 1.73 + row * 2.41 + layer;
        const node = {layer, column, row, phase, x: 0, y: 0};
        const index = nodes.push(node) - 1;
        if (column) links[layer].push([nodes[index - rows], node]);
        if (row) links[layer].push([nodes[index - 1], node]);
        if (column && row && (column + row) % 3 !== 0) {
          links[layer].push([nodes[index - rows - 1], node]);
        }
      }
    }
  }
  for (const column of [5, 8, 11, 13, 15, 16]) {
    const upper = nodes[column * rows + 4];
    const lower = nodes[columns * rows + (columns - 1 - column) * rows];
    links[2].push([upper, lower]);
  }

  function updateNodes() {
    for (const node of nodes) {
      const {layer, column, row, phase} = node;
      const s = column / (columns - 1);
      const strip = row - (rows - 1) / 2;
      const fold = Math.sin(s * 5.5 - layer * 1.9 + time * .37);
      const sway = Math.cos(phase + time * .82);
      node.x = width * (s * 1.08 - .035 + strip * (.012 + .007 * fold) + sway * .004);
      const baseline = layer ? .76 : .24;
      const spread = .029 + Math.abs(fold) * .015;
      node.y = height * (baseline + fold * .12 + strip * spread + sway * .012);
    }
  }

  function draw() {
    if (!width || !height) return;
    updateNodes();
    context.clearRect(0, 0, width, height);
    for (let layer = 0; layer < links.length; layer++) {
      context.beginPath();
      context.strokeStyle = tints[layer];
      context.globalAlpha = layer === 2 ? .13 : .25;
      context.lineWidth = layer === 2 ? .75 : .9;
      for (const [start, end] of links[layer]) {
        context.moveTo(start.x, start.y);
        if (layer === 2) {
          const midpoint = (start.x + end.x) / 2;
          context.bezierCurveTo(midpoint, start.y, midpoint, end.y, end.x, end.y);
        } else {
          context.lineTo(end.x, end.y);
        }
      }
      context.stroke();
    }

    for (const node of nodes) {
      const pulse = .5 + Math.sin(node.phase + time * 1.6) * .5;
      context.fillStyle = tints[node.layer];
      context.globalAlpha = .29 + pulse * .4;
      context.beginPath();
      context.arc(node.x, node.y, .85 + pulse * 1.25, 0, Math.PI * 2);
      context.fill();
    }

    context.fillStyle = '#cbf69c';
    for (let i = 0; i < 13; i++) {
      const layer = i % 2;
      const edge = links[layer][(i * 37 + 13) % links[layer].length];
      const progress = (time * (.21 + i * .011) + i * .37) % 1;
      const [start, end] = edge;
      const x = start.x + (end.x - start.x) * progress;
      const y = start.y + (end.y - start.y) * progress;
      const envelope = Math.sin(progress * Math.PI);
      context.beginPath();
      context.globalAlpha = .14 * envelope;
      context.arc(x, y, 6, 0, Math.PI * 2);
      context.fill();
      context.beginPath();
      context.globalAlpha = .9 * envelope;
      context.arc(x, y, 1.8, 0, Math.PI * 2);
      context.fill();
    }
    context.globalAlpha = 1;
  }

  function tick(now) {
    if (!lastDraw || now - lastDraw >= 30) {
      time += lastDraw ? Math.min(now - lastDraw, 60) / 1000 : 0;
      lastDraw = now;
      draw();
    }
    frame = requestAnimationFrame(tick);
  }

  function resize() {
    width = canvas.clientWidth;
    height = canvas.clientHeight;
    if (!width || !height) return;
    const ratio = Math.min(devicePixelRatio, 1.5, 1900 / width);
    canvas.width = Math.round(width * ratio);
    canvas.height = Math.round(height * ratio);
    context.setTransform(ratio, 0, 0, ratio, 0, 0);
    if (visible) draw();
  }

  function sync() {
    cancelAnimationFrame(frame);
    lastDraw = 0;
    if (!visible || document.hidden) return;
    if (reduced.matches) draw();
    else frame = requestAnimationFrame(tick);
  }

  new ResizeObserver(resize).observe(canvas);
  new IntersectionObserver(([entry]) => {
    visible = entry.intersectionRatio >= .01;
    sync();
  }, {threshold: .01}).observe(canvas);
  document.addEventListener('visibilitychange', sync);
  reduced.addEventListener('change', sync);
  resize();
}

document.querySelectorAll('.graph-field').forEach(mountNetworkField);

