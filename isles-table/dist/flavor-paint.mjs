// Flavor paint (GM 2026-10-21: "maybe we should add a simple paint to put a temporary mask on a copy of a creature"):
// a small paint box over a copy of the creature's picture: a mask, a scar, a colour patch. It gives back the strokes
// alone (to paint on later) and the picture with the strokes on it; Flavor keeps both for that one creature. The token
// files are never changed (art rule: never recolour the tokens themselves). Paint is presentation only.
import { load } from './server.mjs';   // PLAYER-SITE-01: pictures from the GM's PC
export const PAINT_SIZE = 256;
let ui = null;

const loadImage = src => new Promise(ok => {
  if (!src) { ok(null); return; }
  const i = new Image(); i.onload = () => ok(i); i.onerror = () => ok(null); load(i, src);
});
function fit(ctx, img) {                                          // the picture whole and centred, as on the token
  if (!img) return;
  const s = Math.min(PAINT_SIZE / img.naturalWidth, PAINT_SIZE / img.naturalHeight), w = img.naturalWidth * s, h = img.naturalHeight * s;
  ctx.drawImage(img, (PAINT_SIZE - w) / 2, (PAINT_SIZE - h) / 2, w, h);
}
const blank = canvas => !canvas.getContext('2d').getImageData(0, 0, canvas.width, canvas.height).data.some((v, i) => i % 4 === 3 && v);
const webp = canvas => canvas.toDataURL('image/webp', .85);       // PNG where WebP is missing; both are kept

function build(doc) {
  const make = (tag, props = {}) => Object.assign(doc.createElement(tag), props);
  const dialog = make('dialog', { id: 'paint-dialog' }); dialog.setAttribute('aria-labelledby', 'paint-title');
  const title = make('h2', { id: 'paint-title', textContent: 'Paint a mask' });
  const help = make('p', { className: 'note', textContent: 'Paint on a copy of this creature’s picture: a mask, a scar, a colour patch. The token picture itself never changes. Paint is looks only: no rules change.' });
  const stack = make('div', { className: 'paint-stack' });
  const under = make('canvas', { width: PAINT_SIZE, height: PAINT_SIZE }), over = make('canvas', { width: PAINT_SIZE, height: PAINT_SIZE, className: 'paint-over' });
  over.setAttribute('aria-label', 'Paint here: drag to paint');
  stack.append(under, over);
  const colour = make('input', { type: 'color', value: '#5d4a6b' }), size = make('input', { type: 'range', min: 2, max: 48, value: 12 });
  const erase = make('input', { type: 'checkbox' });
  const label = (text, control) => { const l = make('label'); l.append(text + ' ', control); return l; };
  const tools = make('div', { className: 'paint-tools' });
  const clear = make('button', { type: 'button', textContent: 'Clear the paint', className: 'quiet' });
  tools.append(label('Colour', colour), label('Brush', size), label('Eraser', erase), clear);
  const actions = make('div', { className: 'flavor-actions' });
  const save = make('button', { type: 'button', textContent: 'Use this paint' }), cancel = make('button', { type: 'button', textContent: 'Cancel', className: 'quiet' });
  actions.append(save, cancel);
  dialog.append(title, help, stack, tools, actions);
  doc.body.append(dialog);
  const pen = over.getContext('2d');
  let last = null, done = null;
  const at = e => { const r = over.getBoundingClientRect(); return [(e.clientX - r.left) * PAINT_SIZE / r.width, (e.clientY - r.top) * PAINT_SIZE / r.height]; };
  function stroke(to) {
    pen.globalCompositeOperation = erase.checked ? 'destination-out' : 'source-over';
    pen.strokeStyle = pen.fillStyle = colour.value; pen.lineWidth = Number(size.value); pen.lineCap = pen.lineJoin = 'round';
    pen.beginPath(); pen.moveTo(...(last ?? to)); pen.lineTo(...to); pen.stroke();
    last = to;
  }
  over.addEventListener('pointerdown', e => { e.preventDefault(); over.setPointerCapture?.(e.pointerId); last = null; stroke(at(e)); });
  over.addEventListener('pointermove', e => { if (last) stroke(at(e)); });
  for (const k of ['pointerup', 'pointercancel', 'pointerleave']) over.addEventListener(k, () => { last = null; });
  clear.addEventListener('click', () => pen.clearRect(0, 0, PAINT_SIZE, PAINT_SIZE));
  const finish = value => { const d = done; done = null; dialog.close(); d?.(value); };
  cancel.addEventListener('click', () => finish(null));
  dialog.addEventListener('cancel', e => { e.preventDefault(); finish(null); });
  save.addEventListener('click', () => {
    if (blank(over)) { finish({ mask: '', paint: '' }); return; }     // nothing painted: the paint comes off
    const out = make('canvas', { width: PAINT_SIZE, height: PAINT_SIZE }), ctx = out.getContext('2d');
    ctx.drawImage(under, 0, 0); ctx.drawImage(over, 0, 0);
    finish({ mask: webp(over), paint: webp(out) });
  });
  return { dialog, under, over, pen, title, setDone: fn => { done = fn; } };
}

// Opens the paint box on a copy of `base` (a picture's address) with the earlier strokes (`mask`); resolves to
// { mask, paint } (both '' when the paint was cleared) or null on Cancel.
export async function paintPicture({ document: doc = globalThis.document, base = '', mask = '', name = '' } = {}) {
  ui ??= build(doc);
  const [img, old] = await Promise.all([loadImage(base), loadImage(mask)]);
  const under = ui.under.getContext('2d');
  under.clearRect(0, 0, PAINT_SIZE, PAINT_SIZE); fit(under, img);
  ui.pen.globalCompositeOperation = 'source-over';
  ui.pen.clearRect(0, 0, PAINT_SIZE, PAINT_SIZE); if (old) ui.pen.drawImage(old, 0, 0, PAINT_SIZE, PAINT_SIZE);
  ui.title.textContent = name ? `Paint a mask: ${name}` : 'Paint a mask';
  return new Promise(ok => { ui.setDone(ok); ui.dialog.showModal(); });
}
