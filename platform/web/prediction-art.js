import {
  AdditiveBlending, BufferGeometry, CanvasTexture, CatmullRomCurve3, CurvePath,
  Float32BufferAttribute, Group, LineCurve3, Mesh, MeshBasicMaterial,
  OrthographicCamera, Points, PointsMaterial, Scene, Sprite, SpriteMaterial,
  TubeGeometry, Vector3, WebGLRenderer
} from './vendor/three-0.187.0/three.module.js';

const violet = 0xc3a5f4;
const lime = 0xd4ff9a;

function path(vertices, {straight = false, closed = false} = {}) {
  const points = vertices.map(vertex => new Vector3(...vertex));
  if (!straight) return new CatmullRomCurve3(points, closed);
  const route = new CurvePath();
  for (let i = 1; i < points.length; i++) {
    route.add(new LineCurve3(points[i - 1], points[i]));
  }
  return route;
}

function orbit(tilt, radius) {
  return path(Array.from({length: 40}, (_, i) => {
    const angle = i / 40 * Math.PI * 2;
    return [Math.cos(angle) * radius, Math.sin(angle) * radius * .55 * Math.cos(tilt), Math.sin(angle) * radius * .65 * Math.sin(tilt)];
  }), {closed: true});
}

function createGlowTexture() {
  const surface = document.createElement('canvas');
  surface.width = surface.height = 64;
  const context = surface.getContext('2d');
  const glow = context.createRadialGradient(32, 32, 0, 32, 32, 32);
  glow.addColorStop(0, '#fff');
  glow.addColorStop(.16, '#ffffffee');
  glow.addColorStop(.32, '#ffffff75');
  glow.addColorStop(.58, '#ffffff24');
  glow.addColorStop(1, '#ffffff00');
  context.fillStyle = glow;
  context.fillRect(0, 0, 64, 64);
  return new CanvasTexture(surface);
}

function buildArt(index, glowTexture) {
  const group = new Group();
  const fades = [];
  const tracers = [];
  const remember = (material, opacity) => {
    fades.push({material, opacity});
    return material;
  };

  function line(curve, radius = .023, color = violet, opacity = .82) {
    const shell = new Mesh(
      new TubeGeometry(curve, 92, radius * 3, 5, curve.closed === true),
      remember(new MeshBasicMaterial({color, transparent: true, depthWrite: false, blending: AdditiveBlending}), opacity * .10)
    );
    const core = new Mesh(
      new TubeGeometry(curve, 92, radius, 6, curve.closed === true),
      remember(new MeshBasicMaterial({color, transparent: true, depthWrite: false}), opacity)
    );
    group.add(shell, core);
    return curve;
  }

  function light(scale, opacity, color = lime) {
    const sprite = new Sprite(remember(new SpriteMaterial({
      map: glowTexture, color, transparent: true, depthWrite: false, blending: AdditiveBlending
    }), opacity));
    sprite.scale.setScalar(scale);
    group.add(sprite);
    return sprite;
  }

  function trace(curve, speed, phase = 0, size = .55) {
    const sparks = [
      light(size, .95),
      light(size * .64, .43),
      light(size * .39, .26)
    ];
    tracers.push({curve, speed, phase, sparks});
  }

  if (index === 0) {
    const stairs = [[-3.8,1.1,0],[-2.2,1.1,0],[-2.2,.45,0],[-.35,.45,.22],[-.35,-.18,.22],[1.38,-.18,.48],[1.38,-.83,.48],[3.8,-.83,.72]];
    for (const [dy, dz] of [[-.23,-.65],[-.48,-1.15]]) {
      line(path(stairs.map(([x,y,z]) => [x,y+dy,z+dz]), {straight: true}), .012, violet, .25);
    }
    trace(line(path(stairs, {straight: true})), .24, .29);
  } else if (index === 1) {
    const pulse = [[-3.9,-.12,0],[-2.7,-.12,0],[-2.1,.2,.04],[-1.75,-.34,.16],[-1.2,1.36,.58],[-.7,-1.14,.4],[-.26,.16,.25],[.65,-.12,0],[1.4,.28,-.25],[1.85,-.16,0],[3.85,-.16,.24]];
    line(path(pulse.map(([x,y,z]) => [x,y * .64 - .42,z - .72])), .013, violet, .32);
    trace(line(path(pulse), .027), .33, .19);
  } else if (index === 2) {
    const junction = [.1,-.14,.22];
    const stem = line(path([[-3.6,-1.15,-.35],[-2.22,-.95,-.05],[-1.15,-.63,.34],junction]), .032);
    trace(stem, .3, .42);
    for (const [i, points] of [
      [[.95,.42,.45],[1.85,.86,.28],[3.6,1.25,-.22]],
      [[.75,.1,-.05],[2.18,.03,-.52],[3.8,.48,-.65]],
      [[1.15,-.52,.38],[2.04,-.84,.62],[3.44,-1.12,.34]],
      [[.35,.39,.13],[.63,1.13,-.15],[1.34,1.48,-.48]]
    ].entries()) {
      const route = line(path([junction, ...points]), .018 + (3-i)*.002, violet, .74);
      trace(route, .24 + i * .03, i * .21, .39);
      light(.31, .68).position.set(...points.at(-1));
    }
    light(.68, .84).position.set(...junction);
  } else if (index === 3) {
    const ring = line(orbit(.65, 3.15), .021);
    const inner = line(orbit(1.29, 2.45), .019, violet, .61);
    line(orbit(-.73, 1.72), .014, violet, .45);
    trace(ring, .22, .2);
    trace(inner, .28, .7, .43);
    light(.88, .78).position.set(0, 0, .26);
  } else {
    const wave = [[-3.9,-.72,-.25],[-3.25,-.4,.02],[-2.35,.92,.35],[-1.65,1.24,.57],[-.95,.5,.49],[-.25,-.57,.25],[.55,-.68,-.15],[1.22,-.15,.02],[1.95,.25,.46],[2.76,.12,.3],[3.85,.03,.25]];
    line(path(wave.map(([x,y,z]) => [x,y * .83 - .32,z - .66])), .013, violet, .34);
    line(path([[-3.9,0,-.6],[3.85,0,-.6]], {straight: true}), .009, violet, .23);
    trace(line(path(wave), .028), .25, .52, .63);
  }

  return {group, fades, tracers, weight: 0};
}

function makeGrid() {
  const dots = [];
  for (let x = -4.05; x < 4.1; x += .34) {
    for (let y = -1.62; y < 1.65; y += .32) dots.push(x,y,-1.6);
  }
  const geometry = new BufferGeometry();
  geometry.setAttribute('position', new Float32BufferAttribute(dots, 3));
  return new Points(geometry, new PointsMaterial({
    color: 0xaf96d7, size: .026, transparent: true, opacity: .30, depthWrite: false
  }));
}

export function mountPredictionArt(viewport) {
  const reduced = matchMedia('(prefers-reduced-motion: reduce)');
  if (reduced.matches) return;
  const canvas = document.createElement('canvas');
  const context = canvas.getContext('webgl2', {alpha: true, antialias: true});
  if (!context) return;
  const renderer = new WebGLRenderer({canvas, context, alpha: true, antialias: true});
  renderer.setClearColor(0x000000, 0);
  canvas.className = 'prediction-art-canvas';
  canvas.setAttribute('aria-hidden', 'true');
  viewport.append(canvas);

  const scene = new Scene();
  const rig = new Group();
  const grid = makeGrid();
  rig.add(grid);
  scene.add(rig);
  const camera = new OrthographicCamera(-4.6, 4.6, 2.6, -2.6, .1, 30);
  camera.position.z = 12;
  const glowTexture = createGlowTexture();
  const models = Array.from({length: 5}, (_, index) => buildArt(index, glowTexture));
  for (const {group} of models) rig.add(group);
  let current = Number(viewport.dataset.activeSlide || 1) - 1;
  models[current].weight = 1;
  let direction = 1;
  let visible = false;
  let lost = false;
  let frame = 0;
  let lastTime = 0;
  let clock = 0;
  const pointer = new Vector3();
  const nextPosition = new Vector3();

  function resize() {
    const {clientWidth: width, clientHeight: height} = canvas;
    if (!width || !height) return;
    const aspect = width / height;
    const halfHeight = Math.max(1.95, 4.62 / aspect);
    camera.left = -halfHeight * aspect;
    camera.right = -camera.left;
    camera.top = halfHeight;
    camera.bottom = -halfHeight;
    camera.updateProjectionMatrix();
    renderer.setPixelRatio(Math.min(devicePixelRatio, 1.5));
    renderer.setSize(width, height, false);
  }

  function tick(now) {
    frame = 0;
    const elapsed = lastTime ? Math.min((now - lastTime) / 1000, .05) : 0;
    lastTime = now;
    clock += elapsed;
    const smoothing = 1 - Math.exp(-elapsed * 5);
    rig.rotation.x += (pointer.y * .18 + Math.sin(clock * .6) * .06 - rig.rotation.x) * smoothing;
    rig.rotation.y += (pointer.x * .25 + Math.sin(clock * .43) * .08 - rig.rotation.y) * smoothing;

    models.forEach((model, index) => {
      const selected = index === current;
      model.weight += ((selected ? 1 : 0) - model.weight) * smoothing;
      model.group.visible = selected || model.weight > .005;
      if (!model.group.visible) return;
      const shift = 1 - model.weight;
      model.group.position.x = shift * direction * (selected ? .88 : -.88);
      model.group.position.z = -shift * .75;
      for (const {material, opacity} of model.fades) material.opacity = opacity * model.weight;
      for (const {curve, speed, phase, sparks} of model.tracers) {
        sparks.forEach((spark, tail) => {
          const position = (clock * speed + phase + 1 - tail * .028) % 1;
          curve.getPointAt(position, nextPosition);
          spark.position.copy(nextPosition);
          if (!curve.closed) {
            spark.material.opacity *= Math.min(1, position * 16, (1 - position) * 16);
          }
        });
      }
    });
    renderer.render(scene, camera);
    viewport.classList.add('prediction-webgl');
    frame = requestAnimationFrame(tick);
  }

  function sync() {
    if (frame) cancelAnimationFrame(frame);
    frame = 0;
    lastTime = 0;
    if (lost || reduced.matches) viewport.classList.remove('prediction-webgl');
    if (visible && !document.hidden && !lost && !reduced.matches) {
      frame = requestAnimationFrame(tick);
    }
  }

  viewport.addEventListener('prediction:change', event => {
    current = event.detail.index;
    direction = event.detail.direction;
  });
  viewport.addEventListener('pointermove', event => {
    if (event.pointerType !== 'mouse') return;
    const box = viewport.getBoundingClientRect();
    pointer.set((event.clientX - box.left) / box.width * 2 - 1, (event.clientY - box.top) / box.height * 2 - 1, 0);
  });
  viewport.addEventListener('pointerleave', () => pointer.set(0, 0, 0));
  canvas.addEventListener('webglcontextlost', event => {
    event.preventDefault();
    lost = true;
    sync();
  });
  canvas.addEventListener('webglcontextrestored', () => {
    lost = false;
    resize();
    sync();
  });
  new ResizeObserver(resize).observe(canvas);
  new IntersectionObserver(([entry]) => {
    visible = entry.isIntersecting;
    sync();
  }, {threshold: .12}).observe(viewport);
  document.addEventListener('visibilitychange', sync);
  reduced.addEventListener('change', sync);
  resize();
}

