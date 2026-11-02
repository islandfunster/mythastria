// MAP-ZOOM-01 (GM 2026-10-28: "every map needs a zoom out and in"): zoom and pan for a map drawn as an SVG whose own
// code sets the whole picture (Play live, Simulator fights). The map's drawing calls zoom.view(x, y, w, h) in place of
// setting its viewBox; the zoom shows part of that box. + and − buttons and Fit sit on the map's corner; the mouse wheel
// zooms at the pointer; a right- or middle-drag pans; on a phone two fingers pinch to zoom and move together to pan
// (a pinch cancels any drag the first finger began, and no tap or move reaches the map until both fingers lift).
const MIN = 1, MAX = 8, STEP = 1.25;
const make = (tag, attrs = {}, text) => { const e = document.createElement(tag); for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, v); if (text != null) e.textContent = text; return e; };

export function zoomBox(full, k, fx, fy) {
  // the part of `full` ([x, y, w, h]) shown at zoom k, centred at the fractions (fx, fy) of it, kept inside it
  const [x, y, w, h] = full, vw = w / k, vh = h / k;
  const cx = Math.min(Math.max(x + fx * w, x + vw / 2), x + w - vw / 2);
  const cy = Math.min(Math.max(y + fy * h, y + vh / 2), y + h - vh / 2);
  return [cx - vw / 2, cy - vh / 2, vw, vh];
}

const CSS = `.map-zoom-wrap{position:relative}
.map-zoom-bar{position:absolute;top:8px;right:8px;z-index:3;display:flex;gap:4px}
.map-zoom-bar button{min-width:36px;min-height:36px;padding:0 .55rem;font:600 16px/1 inherit;color:var(--paper,#e6dcc2);
 background:var(--panel,#20211d);border:1px solid var(--line,#3c3b30);border-radius:6px;opacity:.88;cursor:pointer}
.map-zoom-bar button:hover:not(:disabled){opacity:1;border-color:var(--brass,#c5a56b)}
.map-zoom-bar button:disabled{opacity:.4;cursor:default}
.map-zoom-wrap>[hidden]~.map-zoom-bar{display:none}`;

// The + / − / Fit buttons on the corner of `el` (wrapped in a positioned box), for a map that zooms its own way (the 3D
// view, the Region map) or for mountZoom below.
export function zoomButtons(el, { zoomIn, zoomOut, reset }) {
  if (!document.getElementById('map-zoom-css')) document.head.append(Object.assign(make('style', { id: 'map-zoom-css' }), { textContent: CSS }));
  const wrap = make('div', { class: 'map-zoom-wrap' });
  el.before(wrap);
  wrap.append(el);
  const bar = make('div', { class: 'map-zoom-bar', role: 'group', 'aria-label': 'Map zoom' });
  const button = (text, label, fn) => { const b = make('button', { type: 'button', 'aria-label': label, title: label }, text); b.addEventListener('click', fn); bar.append(b); return b; };
  const plus = button('+', 'Zoom in', zoomIn), minus = button('−', 'Zoom out', zoomOut), fit = button('Fit', 'Show the whole map', reset);
  wrap.append(bar);
  return { wrap, bar, plus, minus, fit };
}

export function mountZoom(root, { onChange } = {}) {
  let full = null, k = 1, fx = .5, fy = .5;
  const { wrap, plus, minus, fit } = zoomButtons(root, { zoomIn: () => by(STEP), zoomOut: () => by(1 / STEP), reset: () => reset() });

  function apply() {
    if (!full) return;
    const box = k === 1 ? full : zoomBox(full, k, fx, fy);
    if (k > 1) { fx = (box[0] + box[2] / 2 - full[0]) / full[2]; fy = (box[1] + box[3] / 2 - full[1]) / full[3]; }   // kept inside
    root.setAttribute('viewBox', box.map(n => +n.toFixed(4)).join(' '));
    plus.disabled = k >= MAX; minus.disabled = fit.disabled = k <= MIN;
    onChange?.(k);
  }
  function at(clientX, clientY) {                                 // a screen point in map units, or null
    const m = root.getScreenCTM?.();
    return m ? new DOMPoint(clientX, clientY).matrixTransform(m.inverse()) : null;
  }
  function by(f, clientX, clientY) {
    if (!full) return;
    const next = Math.min(MAX, Math.max(MIN, k * f));
    if (next === k) return;
    const r = root.getBoundingClientRect();
    const p = at(clientX ?? r.left + r.width / 2, clientY ?? r.top + r.height / 2);
    if (p) {                                                      // the point under the pointer stays under it
      const [x, y, w, h] = full, cx = x + fx * w, cy = y + fy * h;
      fx = (p.x + (cx - p.x) * k / next - x) / w;
      fy = (p.y + (cy - p.y) * k / next - y) / h;
    }
    k = next;
    if (k === 1) { fx = .5; fy = .5; }
    apply();
  }
  function reset() { k = 1; fx = .5; fy = .5; apply(); }
  function pan(dx, dy) {                                          // screen pixels
    const m = root.getScreenCTM?.();
    if (!full || !m || k === 1) return;
    fx -= dx / m.a / full[2]; fy -= dy / m.d / full[3];
    apply();
  }

  root.addEventListener('wheel', e => {
    if (!full) return;
    e.preventDefault();
    by(e.deltaY < 0 ? STEP : 1 / STEP, e.clientX, e.clientY);
  }, { passive: false });

  // pointers, in the capture phase so a pan or a pinch never reaches the map's own handlers
  const touches = new Map();
  let panning = null, pinch = null, quietUntil = 0;
  const swallow = e => { e.stopImmediatePropagation(); e.preventDefault(); };
  wrap.addEventListener('pointerdown', e => {
    if (!root.contains(e.target) && e.target !== root) return;
    if (e.pointerType === 'touch') {
      touches.set(e.pointerId, [e.clientX, e.clientY]);
      if (touches.size === 2) {                                   // a pinch: the first finger's drag is cancelled
        const [a, b] = [...touches.values()];
        pinch = { d: Math.hypot(a[0] - b[0], a[1] - b[1]) || 1, mid: [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2] };
        const first = [...touches.keys()][0];
        root.dispatchEvent(new PointerEvent('pointercancel', { pointerId: first, pointerType: 'touch', bubbles: true }));
        swallow(e);
      } else if (pinch) swallow(e);
      return;
    }
    if (e.button === 1 || e.button === 2) {                       // right- or middle-drag pans
      panning = { id: e.pointerId, x: e.clientX, y: e.clientY, moved: false };
      try { root.setPointerCapture(e.pointerId); } catch { /* a pointer that is gone */ }
      swallow(e);
    }
  }, true);
  wrap.addEventListener('pointermove', e => {
    if (pinch && touches.has(e.pointerId)) {
      touches.set(e.pointerId, [e.clientX, e.clientY]);
      if (touches.size === 2) {
        const [a, b] = [...touches.values()];
        const d = Math.hypot(a[0] - b[0], a[1] - b[1]) || 1, mid = [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2];
        pan(mid[0] - pinch.mid[0], mid[1] - pinch.mid[1]);
        by(d / pinch.d, mid[0], mid[1]);
        pinch = { d, mid };
      }
      swallow(e);
      return;
    }
    if (panning && e.pointerId === panning.id) {
      const dx = e.clientX - panning.x, dy = e.clientY - panning.y;
      if (Math.abs(dx) + Math.abs(dy) > 2) panning.moved = true;
      pan(dx, dy);
      panning.x = e.clientX; panning.y = e.clientY;
      swallow(e);
    }
  }, true);
  const lift = e => {
    if (!e.isTrusted) return;                                     // the cancel sent to the map's own drag, above
    if (touches.has(e.pointerId)) {
      touches.delete(e.pointerId);
      if (pinch) {
        swallow(e);
        if (!touches.size) { pinch = null; quietUntil = performance.now() + 350; }   // no tap from the lifted fingers
      }
      return;
    }
    if (panning && e.pointerId === panning.id) {
      if (panning.moved) quietUntil = performance.now() + 50;
      panning = null;
      swallow(e);
    }
  };
  wrap.addEventListener('pointerup', lift, true);
  wrap.addEventListener('pointercancel', lift, true);
  wrap.addEventListener('click', e => { if (performance.now() < quietUntil) swallow(e); }, true);
  wrap.addEventListener('contextmenu', e => { if (root.contains(e.target) || e.target === root) e.preventDefault(); });

  return {
    view(x, y, w, h) { full = [x, y, w, h]; apply(); },          // the whole picture, as the map's code draws it
    by, reset, pan,
    get k() { return k; },
  };
}
