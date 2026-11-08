/* Spring-based node interaction, written for this graph. No external services or libraries. */
window.GraphMotion = (() => {
  'use strict';
  const media = matchMedia('(prefers-reduced-motion: reduce)');
  const pins = new Map();
  let current = null, replay = false, ignoreClickUntil = 0;
  const svgNS = 'http://www.w3.org/2000/svg';
  const clamp = (n, a, b) => Math.max(a, Math.min(b, n));
  function element(tag, attrs) {
    const el = document.createElementNS(svgNS, tag);
    for (const [key, value] of Object.entries(attrs)) el.setAttribute(key, value);
    return el;
  }
  // Exact critically damped spring integration, independent of frame rate.
  function spring(value, velocity, target, dt, speed = 15) {
    const offset = value - target, term = velocity + speed * offset, decay = Math.exp(-speed * dt);
    return [target + (offset + term * dt) * decay, (velocity - speed * term * dt) * decay];
  }
  function capture(svg) {
    const s = current;
    if (!s || s.svg !== svg) return null;
    cancelAnimationFrame(s.frame); s.abort.abort();
    const nodes = new Map(s.nodes.map(n => [n.id, {x:n.x,y:n.y,vx:n.vx,vy:n.vy}]));
    const ghost = s.layer.cloneNode(true);
    ghost.querySelector('.motion-hover-halo')?.remove();
    current = null;
    return {nodes, ghost, camera:{...s.camera}, focusId:s.focusId, width:s.width, height:s.height};
  }
  function wake(s) {
    if (current !== s || document.hidden) return;
    if (s.reduced) { paint(s); s.svg.dataset.motionState = 'reduced'; return; }
    if (!s.frame) { s.last = performance.now(); s.frame = requestAnimationFrame(now => tick(s, now)); }
  }
  function setMotionState(s, active) {
    s.svg.dataset.motionState = s.reduced ? 'reduced' : s.drag ? 'dragging' : active ? 'moving' : 'idle';
  }
  function tick(s, now) {
    s.frame = 0;
    if (current !== s || document.hidden) return;
    const dt = clamp((now - s.last) / 1000, .001, .05); s.last = now;
    let active = !!s.drag;
    for (const n of s.nodes) {
      const age = now - n.birth - n.delay;
      const alpha = n.fresh ? clamp(1 - Math.exp(-Math.max(0, age) / 90), 0, 1) : 1;
      n.opacity = alpha;
      if (!s.drag || s.drag.node !== n) {
        [n.x,n.vx] = spring(n.x,n.vx,n.tx,dt);
        [n.y,n.vy] = spring(n.y,n.vy,n.ty,dt);
      }
      const moving = Math.hypot(n.x-n.tx,n.y-n.ty) > .08 || Math.hypot(n.vx,n.vy) > .15;
      if (!moving && (!s.drag || s.drag.node !== n)) { n.x=n.tx; n.y=n.ty; n.vx=n.vy=0; }
      if (moving || alpha < .997) active = true;
      if (alpha >= .997) { n.opacity=1; n.fresh=false; }
    }
    for (const key of ['x','y','k']) {
      const target = s.cameraTarget[key], speed = key === 'k' ? 12 : 10;
      const [value, velocity] = spring(s.camera[key], s.cameraVelocity[key], target, dt, speed);
      s.camera[key]=value; s.cameraVelocity[key]=velocity;
      if (Math.abs(value-target) > (key==='k'?.0003:.05) || Math.abs(velocity) > (key==='k'?.001:.1)) active=true;
      else { s.camera[key]=target; s.cameraVelocity[key]=0; }
    }
    for (const key of ['x','y','w','h','r','opacity']) {
      const [value, velocity] = spring(s.halo[key],s.haloVelocity[key],s.haloTarget[key],dt,22);
      s.halo[key]=value; s.haloVelocity[key]=velocity;
      if (Math.abs(value-s.haloTarget[key])>.025 || Math.abs(velocity)>.05) active=true;
    }
    paint(s); setMotionState(s, active);
    if (active) s.frame=requestAnimationFrame(t=>tick(s,t));
  }
  function anchor(n, dx, dy, inset = 0) {
    if (n.focus) {
      const ratio = (n.hw + inset) / (Math.hypot(dx,dy) || 1);
      return {x:n.x + dx*ratio,y:n.y + dy*ratio};
    }
    const ratio = Math.min((n.hw+inset)/(Math.abs(dx)||.001),(n.hh+inset)/(Math.abs(dy)||.001));
    return {x:n.x+dx*ratio,y:n.y+dy*ratio};
  }
  function paint(s) {
    s.layer.setAttribute('transform',`translate(${s.width/2+s.camera.x},${s.height/2+s.camera.y}) scale(${s.camera.k}) translate(${-s.width/2},${-s.height/2})`);
    for (const n of s.nodes) {
      const scale = n.fresh && !s.reduced ? .88 + .12*n.opacity : 1;
      n.el.setAttribute('transform',`translate(${n.x},${n.y}) scale(${scale})`);
      n.el.style.opacity=String(s.reduced?1:n.opacity);
    }
    for (const link of s.links) {
      const a=s.byId.get(link.source), b=s.byId.get(link.target); if(!a||!b) continue;
      const start=anchor(a,b.x-a.x,b.y-a.y), end=anchor(b,a.x-b.x,a.y-b.y,3);
      for(const [key,value] of Object.entries({x1:start.x,y1:start.y,x2:end.x,y2:end.y})) link.el.setAttribute(key,String(value));
      link.el.style.opacity=String(Math.min(a.opacity,b.opacity));
      link.el.classList.toggle('is-highlighted',s.hover===b.id || s.drag?.node===b);
      if(link.label) { link.label.setAttribute('x',String((start.x+end.x)/2)); link.label.setAttribute('y',String((start.y+end.y)/2-4)); link.label.style.opacity=String(Math.min(a.opacity,b.opacity)); }
    }
    if(s.hover) {
      const n=s.byId.get(s.hover);
      if(n) {s.haloTarget.x=n.x-n.hw-8; s.haloTarget.y=n.y-n.hh-8;}
    }
    const h=s.halo;
    for(const [key,value] of Object.entries({x:h.x,y:h.y,width:Math.max(0,h.w),height:Math.max(0,h.h),rx:h.r,opacity:clamp(h.opacity,0,1)})) s.haloEl.setAttribute(key,String(value));
  }
  function point(s,event) {
    const matrix=s.layer.getScreenCTM();
    return matrix ? new DOMPoint(event.clientX,event.clientY).matrixTransform(matrix.inverse()) : new DOMPoint(0,0);
  }
  function hover(s,n) {
    const id=n?.id || null;
    if(s.hover===id) return;
    s.hover=id;
    for(const item of s.nodes) item.el.classList.toggle('is-hovered',item.id===id);
    s.haloTarget.opacity=n?1:0;
    if(n) Object.assign(s.haloTarget,{x:n.x-n.hw-8,y:n.y-n.hh-8,w:n.hw*2+16,h:n.hh*2+16,r:n.focus?n.hw+8:21});
    if(s.reduced) Object.assign(s.halo,s.haloTarget);
    wake(s);
  }
  function nearest(s,event) {
    const p=point(s,event); let best=null,distance=Infinity;
    for(const n of s.nodes) {
      const dx=Math.max(0,Math.abs(p.x-n.x)-n.hw),dy=Math.max(0,Math.abs(p.y-n.y)-n.hh),d=Math.hypot(dx,dy);
      if(d<(s.hover===n.id?24:15) && d<distance) { best=n;distance=d; }
    }
    return best;
  }
  function finish(s,event,cancelled=false) {
    const drag=s.drag; if(!drag || (event.pointerId!==undefined && event.pointerId!==drag.pointer)) return;
    s.drag=null;
    if(drag.node) {
      const n=drag.node; n.el.classList.remove('is-dragging');
      if(drag.moved&&!cancelled) {
        if(!pins.has(s.key)) pins.set(s.key,new Map());
        pins.get(s.key).set(n.id,{x:n.x,y:n.y});
        n.tx=n.x; n.ty=n.y; n.vx=n.vy=0;
      } else if(cancelled) { n.tx=drag.oldTarget.x; n.ty=drag.oldTarget.y; }
    }
    s.svg.classList.remove('is-panning');
    if(drag.moved || cancelled) s.suppressUntil=ignoreClickUntil=performance.now()+350;
    if(s.svg.hasPointerCapture(drag.pointer)) s.svg.releasePointerCapture(drag.pointer);
    hover(s,null); wake(s);
    if(!drag.moved && !cancelled && drag.node) {
      ignoreClickUntil=performance.now()+350;
      s.onFocus(drag.node.id);
    }
  }
  function attach(options) {
    const {svg,layer,focusId,key,width,height,zoom,targets,previous,onFocus}=options;
    const reduced=media.matches;
    const changed=previous?.focusId!==focusId;
    const origin=previous?.nodes.get(focusId) || {x:width/2,y:height/2};
    const now=performance.now();
    const camera=previous&&!replay?{...previous.camera}:{x:0,y:0,k:zoom};
    const s={...options,frame:0,last:now,reduced,abort:new AbortController(),nodes:[],byId:new Map(),links:[],hover:null,drag:null,suppressUntil:0,camera,cameraTarget:{x:changed?0:camera.x,y:changed?0:camera.y,k:zoom},cameraVelocity:{x:0,y:0,k:0},halo:{x:width/2,y:height/2,w:1,h:1,r:15,opacity:0},haloTarget:{x:width/2,y:height/2,w:1,h:1,r:15,opacity:0},haloVelocity:{x:0,y:0,w:0,h:0,r:0,opacity:0}};
    current=s;
    let index=0;
    for(const el of layer.querySelectorAll('g[role=button][data-node]')) {
      const id=el.dataset.node, target=targets[id], old=!replay?previous?.nodes.get(id):null;
      const shape=el.querySelector('.node-shape'), focus=id===focusId;
      const hw=shape.tagName==='circle'?+shape.getAttribute('r'):+shape.getAttribute('width')/2;
      const hh=shape.tagName==='circle'?hw:+shape.getAttribute('height')/2;
      const pin=pins.get(key)?.get(id);
      const tx=pin?clamp(pin.x,hw+9,width-hw-9):target.x,ty=pin?clamp(pin.y,hh+9,height-hh-9):target.y;
      const start=old || {x:origin.x+(tx-width/2)*.18,y:origin.y+(ty-height/2)*.18,vx:0,vy:0};
      const n={id,el,focus,hw,hh,x:reduced?tx:start.x,y:reduced?ty:start.y,vx:reduced?0:start.vx||0,vy:reduced?0:start.vy||0,tx,ty,opacity:reduced||old?1:0,fresh:!reduced&&!old,birth:now,delay:focus?0:index++*15};
      s.nodes.push(n);s.byId.set(id,n);el.classList.add('motion-node'); el.style.setProperty('--node-tint',shape.getAttribute('stroke'));
      el.addEventListener('click',event=>{if(performance.now()<Math.max(s.suppressUntil,ignoreClickUntil)){event.preventDefault();event.stopImmediatePropagation();}},{capture:true,signal:s.abort.signal});
      el.addEventListener('focus',()=>hover(s,n),{signal:s.abort.signal});
      el.addEventListener('blur',()=>hover(s,null),{signal:s.abort.signal});
    }
    for(const el of layer.querySelectorAll('line[data-edge-target]')) s.links.push({el,source:el.dataset.edgeSource,target:el.dataset.edgeTarget,label:[...layer.querySelectorAll('text[data-edge-target]')].find(label=>label.dataset.edgeTarget===el.dataset.edgeTarget)});
    s.haloEl=element('rect',{class:'motion-hover-halo',width:1,height:1,rx:15,opacity:0,'aria-hidden':'true'});layer.appendChild(s.haloEl);
    if(previous?.ghost && !reduced && !replay) {
      const ghost=previous.ghost;
      for(const node of [...ghost.querySelectorAll('[data-node]')]) {
        if(s.byId.has(node.dataset.node)) node.remove();
        else {node.removeAttribute('role');node.removeAttribute('tabindex');node.removeAttribute('data-node');}
      }
      for(const link of [...ghost.querySelectorAll('[data-edge-target]')]) if(s.byId.has(link.dataset.edgeTarget)) link.remove();
      ghost.setAttribute('aria-hidden','true');ghost.removeAttribute('data-motion-layer');ghost.classList.add('motion-outgoing');
      if(ghost.querySelector('.node-shape')) {
        svg.insertBefore(ghost,layer);
        const fade=ghost.animate([{opacity:.55},{opacity:0}],{duration:230,easing:'ease-out',fill:'forwards'});
        fade.finished.then(()=>ghost.remove(),()=>ghost.remove());
      }
    }
    replay=false;
    const signal=s.abort.signal;
    svg.addEventListener('pointerdown',event=>{
      if(event.button!==0) return;
      const el=event.target.closest('[data-node]'),node=el?s.byId.get(el.dataset.node):null;
      const p=point(s,event);
      s.drag={pointer:event.pointerId,node,startX:event.clientX,startY:event.clientY,offsetX:node?p.x-node.x:0,offsetY:node?p.y-node.y:0,oldTarget:node?{x:node.tx,y:node.ty}:null,panX:s.camera.x,panY:s.camera.y,moved:false};
      if(node) node.el.classList.add('is-dragging');else svg.classList.add('is-panning');
      svg.setPointerCapture(event.pointerId); wake(s);
    },{signal});
    svg.addEventListener('pointermove',event=>{
      const d=s.drag;
      if(!d) {if(event.pointerType!=='touch') hover(s,nearest(s,event));return;}
      if(d.pointer!==event.pointerId) return;
      const dx=event.clientX-d.startX,dy=event.clientY-d.startY;
      if(Math.hypot(dx,dy)>5) d.moved=true;
      if(d.moved) {
        event.preventDefault();
        if(d.node) {const p=point(s,event),n=d.node;n.x=n.tx=clamp(p.x-d.offsetX,n.hw+9,width-n.hw-9);n.y=n.ty=clamp(p.y-d.offsetY,n.hh+9,height-n.hh-9);n.vx=n.vy=0;}
        else {const r=svg.getBoundingClientRect();s.camera.x=s.cameraTarget.x=d.panX+dx*width/r.width;s.camera.y=s.cameraTarget.y=d.panY+dy*height/r.height;}
        paint(s);
      }
      wake(s);
    },{signal});
    svg.addEventListener('pointerup',event=>finish(s,event),{signal});
    svg.addEventListener('pointercancel',event=>finish(s,event,true),{signal});
    svg.addEventListener('lostpointercapture',event=>finish(s,event,true),{signal});
    svg.addEventListener('pointerleave',()=>{if(!s.drag)hover(s,null);},{signal});
    svg.addEventListener('click',event=>{
      if(event.target.closest('[data-node]') || performance.now()<Math.max(s.suppressUntil,ignoreClickUntil)) return;
      const n=nearest(s,event); if(n) onFocus(n.id);
    },{signal});
    paint(s); setMotionState(s,!reduced); wake(s);
  }
  function relayout(svg,render) {
    if(current?.svg===svg) pins.delete(current.key);
    replay=true; render();
  }
  function syncPreference() {
    const s=current;if(!s)return;
    s.reduced=media.matches;
    if(s.reduced) {
      cancelAnimationFrame(s.frame);s.frame=0;
      for(const n of s.nodes){n.x=n.tx;n.y=n.ty;n.vx=n.vy=0;n.opacity=1;n.fresh=false;}
      Object.assign(s.camera,s.cameraTarget);Object.assign(s.halo,s.haloTarget);
      s.svg.querySelectorAll('.motion-outgoing').forEach(el=>el.remove());
      paint(s);setMotionState(s,false);
    } else wake(s);
  }
  media.addEventListener('change',syncPreference);
  document.addEventListener('visibilitychange',()=>{
    const s=current;if(!s)return;
    if(document.hidden){cancelAnimationFrame(s.frame);s.frame=0;if(s.drag)finish(s,{pointerId:s.drag.pointer},true);}
    else wake(s);
  });
  return {capture,attach,relayout};
})();
