// MAP-PAINT-01 (GM 2026-10-27, Flavor: "I want the DM to be able to draw/paint on the map and erase what he did. It would
// need to add an alpha channel on top of the map"; the GM reveals it on/off; kept per map): a transparent picture over
// the map's squares (0,0 to cols,rows). The GM paints with a brush or erases; each stroke is saved to the service
// (/api/map_paint/save, per map name). The players' window and the player clients fetch it only while it is shown.
// Presentation only: the rules never read it.
import { load } from './server.mjs';   // PLAYER-SITE-01: pictures from the GM's PC

const MAX_SIDE = 4096, MAX_PX = 48, MIN_PX = 8, UNDO = 12, SAVE_AFTER = 500;

export function paintScale(cols, rows) {                     // pixels per square: sharp on a small map, bounded on a big one
  return Math.max(MIN_PX, Math.min(MAX_PX, Math.floor(MAX_SIDE / Math.max(1, cols, rows))));
}

export function createMapPaint({ port, player = false, doc = globalThis.document, onStatus = () => {}, onChange = () => {} }) {
  const NS = 'http://www.w3.org/2000/svg';
  const layer = doc.createElementNS(NS, 'foreignObject');
  layer.setAttribute('class', 'map-paint');
  layer.setAttribute('pointer-events', 'none');
  const canvas = doc.createElement('canvas');
  canvas.style.cssText = 'display:block;width:100%;height:100%';
  layer.append(canvas);
  const ctx = canvas.getContext('2d', player ? { willReadFrequently: true } : undefined);   // a player's view reads it (blocks)
  const s = { name: null, cols: 0, rows: 0, rev: null, shown: false, loading: 0, dirty: false, saveTimer: 0,
    on: false, tool: 'brush', colour: '#d0342c', size: 1, opacity: .6, stroke: null, undo: [] };
  let mapEl = null;
  const map = () => mapEl;

  function size(cols, rows) {
    const px = paintScale(cols, rows), w = cols * px, h = rows * px;
    if (canvas.width === w && canvas.height === h) return false;
    const old = canvas.width && canvas.height ? copy() : null;
    canvas.width = w; canvas.height = h;
    if (old) ctx.drawImage(old, 0, 0, w, h);
    return true;
  }
  function copy() {
    const c = doc.createElement('canvas'); c.width = canvas.width; c.height = canvas.height;
    c.getContext('2d').drawImage(canvas, 0, 0); return c;
  }
  const blank = () => { ctx.clearRect(0, 0, canvas.width, canvas.height); };
  function picture(src) {
    return new Promise(done => {
      if (!src) { blank(); done(); return; }
      const img = new Image();
      img.onload = () => { blank(); ctx.drawImage(img, 0, 0, canvas.width, canvas.height); done(); };
      img.onerror = () => done();
      load(img, src);
    });
  }

  async function load(name, force = false) {
    if (!name || s.dirty) return;
    const job = ++s.loading;
    const out = await port.mapPaint(name, force || name !== s.name ? null : s.rev, player).catch(() => null);
    if (!out?.ok && s.asked === name) s.asked = null;              // the next redraw asks again
    if (job !== s.loading || !out?.ok || s.dirty || s.stroke) return;
    const changed = name !== s.name || out.rev !== s.rev;
    s.name = name; s.shown = !!out.shown;
    if (player && !out.shown) { if (s.rev !== out.rev) blank(); s.rev = out.rev; if (changed) onChange(); return; }
    if ('picture' in out) { await picture(out.picture); if (job !== s.loading) return; }
    s.rev = out.rev;
    if (changed) { if (!player) s.undo = []; onChange(); }
  }

  // drawMap calls this after the map's own pictures: the layer goes back on top of them, sized to the map's squares
  function draw(root, view) {
    const m = view?.map;
    if (!m?.cols || !m?.rows) return;
    if (m.name !== s.name && m.name !== s.asked) { s.asked = m.name; blank(); s.rev = null; s.undo = []; load(m.name); }
    s.cols = m.cols; s.rows = m.rows;
    size(m.cols, m.rows);
    layer.setAttribute('x', 0); layer.setAttribute('y', 0);
    layer.setAttribute('width', m.cols); layer.setAttribute('height', m.rows);
    if (player && !s.shown) return;
    root.append(layer);
  }

  // ---------------------------------------------------------------- the GM's brush
  const point = e => {
    const ctm = map().getScreenCTM?.();
    if (!ctm || !s.cols) return null;
    const p = new DOMPoint(e.clientX, e.clientY).matrixTransform(ctm.inverse()), px = canvas.width / s.cols;
    return [p.x * px, p.y * px];
  };
  function paintStroke() {
    const st = s.stroke, px = canvas.width / s.cols;
    ctx.save();
    blank(); ctx.drawImage(st.before, 0, 0);
    ctx.globalCompositeOperation = st.tool === 'eraser' ? 'destination-out' : 'source-over';
    ctx.globalAlpha = st.tool === 'eraser' ? 1 : st.opacity;
    ctx.strokeStyle = ctx.fillStyle = st.colour;
    ctx.lineWidth = st.size * px; ctx.lineCap = ctx.lineJoin = 'round';
    ctx.beginPath();
    const [a, ...rest] = st.points;
    if (!rest.length) { ctx.arc(a[0], a[1], ctx.lineWidth / 2, 0, Math.PI * 2); ctx.fill(); }
    else { ctx.moveTo(...a); for (const p of rest) ctx.lineTo(...p); ctx.stroke(); }   // one stroke: no darker joins
    ctx.restore();
  }
  function down(e) {
    if (!s.on) return;
    e.stopImmediatePropagation(); e.preventDefault();
    if (e.button !== 0 || !s.name) return;
    const p = point(e);
    if (!p) return;
    map().setPointerCapture?.(e.pointerId);
    s.loading++;                                           // a fetch still on its way must not undo this stroke
    s.stroke = { pointer: e.pointerId, before: copy(), points: [p], tool: s.tool, colour: s.colour, size: s.size, opacity: s.opacity };
    paintStroke();
  }
  function move(e) {
    if (!s.on) return;
    e.stopImmediatePropagation();
    if (!s.stroke || e.pointerId !== s.stroke.pointer) return;
    const p = point(e);
    if (p) { s.stroke.points.push(p); paintStroke(); }
  }
  function up(e) {
    if (!s.on) return;
    e.stopImmediatePropagation();
    if (!s.stroke || e.pointerId !== s.stroke.pointer) return;
    s.undo.push(s.stroke.before); if (s.undo.length > UNDO) s.undo.shift();
    s.stroke = null;
    changed();
  }
  function block(e) { if (s.on) { e.stopImmediatePropagation(); e.preventDefault(); } }

  function changed() {
    s.dirty = true;
    clearTimeout(s.saveTimer);
    s.saveTimer = setTimeout(save, SAVE_AFTER);
  }
  const empty = () => !ctx.getImageData(0, 0, canvas.width, canvas.height).data.some((v, i) => i % 4 === 3 && v);
  async function save(extra = {}) {
    clearTimeout(s.saveTimer);
    if (!s.name) return null;
    const body = { map: s.name, ...extra };
    if (s.dirty) body.picture = empty() ? '' : canvas.toDataURL('image/png');
    const sent = s.dirty; s.dirty = false;
    const out = await port.saveMapPaint(body).catch(() => null);
    if (!out?.ok) { if (sent) s.dirty = true; onStatus('The paint was not saved: ' + (out?.error ?? 'the service stopped.'), true); return null; }
    s.rev = out.rev; s.shown = !!out.shown; onChange();
    return out;
  }

  // GM 2026-10-28 ("the paint should block the vision"): a square hides what stands on it from the players when at least
  // half of it is painted at half strength or more (the See-through slider at 0.5 or above). Shown paint only.
  function blocks(x, y) {
    if (!s.shown || !s.cols || !canvas.width) return false;
    const sx = Math.round(x), sy = Math.round(y);
    if (sx < 0 || sy < 0 || sx >= s.cols || sy >= s.rows) return false;
    const px = canvas.width / s.cols, side = Math.max(1, Math.floor(px));
    const d = ctx.getImageData(Math.floor(sx * px), Math.floor(sy * px), side, side).data;
    let solid = 0;
    for (let i = 3; i < d.length; i += 4) if (d[i] >= 128) solid++;
    return solid * 2 >= d.length / 4;
  }

  return {
    draw, blocks, load: name => load(name, true),
    follow: name => load(name),                            // a player's view: only what changed since the last look
    attach(el) {                                            // the map's SVG: painting takes its pointer while it is on
      mapEl = el;
      el.addEventListener('pointerdown', down, true);
      el.addEventListener('pointermove', move, true);
      el.addEventListener('pointerup', up, true);
      el.addEventListener('pointercancel', up, true);
      el.addEventListener('click', block, true);
      el.addEventListener('dblclick', block, true);
    },
    get on() { return s.on; },
    set on(v) { s.on = !!v; },
    get shown() { return s.shown; },
    get map() { return s.name; },
    get canUndo() { return s.undo.length > 0; },
    set(opts) { for (const k of ['tool', 'colour', 'size', 'opacity']) if (opts[k] !== undefined) s[k] = opts[k]; },
    undo() { const last = s.undo.pop(); if (!last) return; blank(); ctx.drawImage(last, 0, 0); changed(); },
    clear() { s.undo.push(copy()); if (s.undo.length > UNDO) s.undo.shift(); blank(); changed(); },
    show: shown => save({ shown: !!shown }),
    flush: () => (s.dirty ? save() : null),
  };
}
