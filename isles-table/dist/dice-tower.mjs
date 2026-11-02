// DICE-TOWER-01 (GM 2026-10-20: "make a dice tower popup that shows the dice roll in a landing box"; "make the private
// roll show the dice as blank"). Every free roll from the dice tool or /r tumbles down a tower and lands in a box at
// its foot, each die showing its face, with the total and who rolled. A private GM roll lands blank for the player who
// rolled it (the service never sends them the faces); the GM sees the real dice. Display only: the service rolls.
// Tabletop style: ink outlines, flat tones; reduced motion: the dice simply appear in the box.

const INK = '#1c171a';
const MAX_SHOWN = 12;
const SHAPES = {                                   // a 36 x 36 die outline per kind of die
  4: 'M18 3 L34 31 L2 31 Z',
  6: 'M6 4 H30 Q33 4 33 7 V29 Q33 32 30 32 H6 Q3 32 3 29 V7 Q3 4 6 4 Z',
  8: 'M18 2 L34 18 L18 34 L2 18 Z',
  10: 'M18 2 L33 15 L18 34 L3 15 Z',
  12: 'M18 2 L34 13 L28 32 L8 32 L2 13 Z',
  20: 'M18 2 L33 10 L33 26 L18 34 L3 26 L3 10 Z',
};
const FILL = { 4: '#d98b5f', 6: '#e8c66a', 8: '#8fc28a', 10: '#7fb6d6', 12: '#b79ad9', 20: '#eab54e', 100: '#d9a0a0' };

// The dice of one chat roll: [{sides, value (null when blank), kept}], with total, modifier and whether it is blank.
export function diceOf(entry) {
  const out = { dice: [], more: 0, total: null, modifier: 0, blank: false, private: entry.kind === 'gmroll', who: entry.from ?? '',
    label: entry.label ?? '', expr: entry.expr ?? '' };
  if (entry.terms) {
    for (const t of entry.terms) {
      if (t.const !== undefined) { out.modifier += t.sign * t.const; continue; }
      const sides = Number(/d(\d+)/.exec(t.dice)?.[1] ?? 6);
      t.rolls.forEach((v, i) => out.dice.push({ sides, value: v, kept: t.kept.includes(i) }));
    }
    out.total = entry.total ?? null;
  } else {                                          // a private roll seen by its roller: the dice, never their faces
    out.blank = true;
    const expr = entry.expr ?? /rolls\s+(\S+)/.exec(entry.text ?? '')?.[1] ?? 'd20';
    for (const m of expr.toLowerCase().matchAll(/(\d*)d(\d+)/g)) {
      const n = Math.min(100, Number(m[1] || 1));
      for (let i = 0; i < n; i++) out.dice.push({ sides: Number(m[2]), value: null, kept: true });
    }
    if (!out.dice.length) out.dice.push({ sides: 20, value: null, kept: true });
    out.expr = expr;
  }
  if (out.dice.length > MAX_SHOWN) { out.more = out.dice.length - MAX_SHOWN; out.dice = out.dice.slice(0, MAX_SHOWN); }
  return out;
}

// Where each die comes to rest in a landing box of w x h: up to 6 a row, a little scatter (the same every time).
export function landingSpots(n, w, h) {
  const perRow = Math.min(6, Math.max(1, n)), rows = Math.ceil(n / perRow), out = [];
  for (let i = 0; i < n; i++) {
    const r = Math.floor(i / perRow), c = i % perRow, inRow = r === rows - 1 ? n - r * perRow : perRow;
    const x = (w / (inRow + 1)) * (c + 1) + ((i * 37) % 9 - 4), y = (h / (rows + 1)) * (r + 1) + ((i * 53) % 7 - 3);
    out.push([Math.round(Math.min(w - 8, Math.max(8, x))), Math.round(Math.min(h - 8, Math.max(8, y)))]);
  }
  return out;
}

const CSS = `
#dice-tower{position:fixed;right:18px;bottom:78px;z-index:80;width:270px;padding:10px 12px 12px;border:2.5px solid ${INK};
 border-radius:14px;background:var(--panel,#323a35);color:var(--paper,#f2e8d0);box-shadow:3px 4px 0 ${INK};font:13px Inter,system-ui,sans-serif;cursor:pointer}
#dice-tower[hidden]{display:none}
.dt-scene{position:relative;width:246px;height:250px}
.dt-scene svg.dt-tower{position:absolute;left:0;top:0}
.dt-die{position:absolute;left:0;top:0;width:34px;height:34px;transform:translate(var(--x),var(--y)) rotate(var(--r));
 animation:dt-fall 1.25s cubic-bezier(.3,.1,.4,1) both;animation-delay:var(--d)}
.dt-die svg{width:34px;height:34px;overflow:visible}
.dt-face{position:absolute;inset:0;display:grid;place-items:center;font:700 13px var(--display-font,'Fredoka',sans-serif);color:${INK};
 opacity:0;animation:dt-show .2s ease-out both;animation-delay:calc(var(--d) + 1.15s)}
.dt-die.dropped{opacity:.45}
.dt-cap{display:flex;justify-content:space-between;align-items:center;gap:8px;margin-top:4px}
.dt-who{font-weight:600}.dt-label{color:var(--muted,#bdb69f);font-size:12px}
.dt-total{min-width:44px;text-align:center;padding:4px 8px;border:2.5px solid ${INK};border-radius:10px;background:var(--brass,#eab54e);
 color:#1d1608;font:700 20px var(--display-font,'Fredoka',sans-serif);box-shadow:0 3px 0 ${INK}}
.dt-note{font-size:12px;color:var(--muted,#bdb69f);margin-top:4px}
.dt-tag{font-size:11px;padding:1px 6px;border-radius:6px;background:#c9a35a;color:#1d1608;margin-left:6px}
@keyframes dt-fall{0%{transform:translate(104px,-30px) rotate(0deg);opacity:0}8%{opacity:1}
 30%{transform:translate(132px,62px) rotate(140deg)}48%{transform:translate(96px,118px) rotate(260deg)}
 66%{transform:translate(150px,168px) rotate(380deg)}84%{transform:translate(var(--x),calc(var(--y) - 10px)) rotate(calc(var(--r) - 25deg))}
 100%{transform:translate(var(--x),var(--y)) rotate(var(--r))}}
@keyframes dt-show{from{opacity:0}to{opacity:1}}
.dt-still .dt-die,.dt-still .dt-face{animation:none!important;opacity:1}
.dt-still .dt-die.dropped{opacity:.45}
@media(prefers-reduced-motion:reduce){.dt-die,.dt-face{animation:none!important;opacity:1}.dt-die.dropped{opacity:.45}}`;

const TOWER = `<svg class="dt-tower" width="246" height="250" viewBox="0 0 246 250" aria-hidden="true">
 <path d="M86 4 H158 V170 H86 Z" fill="#6f6a62" stroke="${INK}" stroke-width="3" stroke-linejoin="round"/>
 <path d="M80 4 H164 V18 H80 Z" fill="#8a847a" stroke="${INK}" stroke-width="3"/>
 <path d="M94 18 V170 M150 18 V170" stroke="#5c574f" stroke-width="2"/>
 <path d="M90 56 L140 74" stroke="${INK}" stroke-width="5" stroke-linecap="round"/>
 <path d="M154 104 L104 124" stroke="${INK}" stroke-width="5" stroke-linecap="round"/>
 <path d="M90 146 L132 160" stroke="${INK}" stroke-width="5" stroke-linecap="round"/>
 <path d="M8 172 H238 V246 H8 Z" fill="#4a3a2a" stroke="${INK}" stroke-width="3" stroke-linejoin="round"/>
 <path class="dt-tray" d="M16 180 H230 V238 H16 Z" fill="#2f5a45" stroke="${INK}" stroke-width="2"/>
 <path d="M112 170 Q122 176 132 170" fill="none" stroke="${INK}" stroke-width="3"/>
</svg>`;

export function createDiceTower({ animate = true, doc = globalThis.document, hold = 4500 } = {}) {
  const queue = [];
  let box = null, timer = null;

  function ensureStyle() {
    if (!doc.getElementById('dice-tower-css')) {
      const s = doc.createElement('style'); s.id = 'dice-tower-css'; s.textContent = CSS; doc.head.append(s);
    }
  }

  function render(entry) {
    ensureStyle();
    const d = diceOf(entry), root = doc.createElement('div');
    root.className = 'dt-roll' + (animate ? '' : ' dt-still');
    const scene = doc.createElement('div'); scene.className = 'dt-scene'; scene.innerHTML = TOWER;
    const spots = landingSpots(d.dice.length, 214, 58);
    d.dice.forEach((die, i) => {
      const el = doc.createElement('div');
      el.className = 'dt-die' + (die.kept ? '' : ' dropped');
      el.style.setProperty('--x', `${16 + spots[i][0] - 17}px`);
      el.style.setProperty('--y', `${180 + spots[i][1] - 17}px`);
      el.style.setProperty('--r', `${((i * 47) % 50) - 25}deg`);
      el.style.setProperty('--d', `${i * 0.12}s`);
      el.title = `d${die.sides}` + (die.value === null ? '' : `: ${die.value}`) + (die.kept ? '' : ' (dropped)');
      el.innerHTML = `<svg viewBox="0 0 36 36"><path d="${SHAPES[die.sides] ?? 'M18 2 A16 16 0 1 0 18.1 2 Z'}" fill="${d.blank ? '#e9e3d6' : FILL[die.sides] ?? '#d9cfb8'}"
        stroke="${INK}" stroke-width="2.5" stroke-linejoin="round"/></svg>`;
      const face = doc.createElement('span'); face.className = 'dt-face'; face.textContent = die.value === null ? '' : String(die.value);
      el.append(face); scene.append(el);
    });
    root.append(scene);
    const cap = doc.createElement('div'); cap.className = 'dt-cap';
    const left = doc.createElement('div');
    const who = doc.createElement('div'); who.className = 'dt-who'; who.textContent = d.who || 'Someone';
    if (d.private && !d.blank) { const tag = doc.createElement('span'); tag.className = 'dt-tag'; tag.textContent = 'GM only'; who.append(tag); }
    const label = doc.createElement('div'); label.className = 'dt-label';
    label.textContent = [d.expr, d.label].filter(Boolean).join(' · ') + (d.more ? ` (+${d.more} more dice)` : '');
    left.append(who, label); cap.append(left);
    if (!d.blank && d.total !== null) { const t = doc.createElement('div'); t.className = 'dt-total'; t.textContent = String(d.total); cap.append(t); }
    root.append(cap);
    if (d.blank) { const n = doc.createElement('div'); n.className = 'dt-note'; n.textContent = 'Private roll: only the GM sees the result.'; root.append(n); }
    return root;
  }

  function next() {
    if (timer || !queue.length) return;
    if (!box) {
      box = doc.createElement('section'); box.id = 'dice-tower'; box.setAttribute('aria-live', 'polite'); box.setAttribute('aria-label', 'Dice tower');
      box.title = 'Click to close'; box.addEventListener('click', close); doc.body.append(box);
    }
    box.replaceChildren(render(queue.shift())); box.hidden = false;
    timer = setTimeout(() => { timer = null; if (queue.length) next(); else box.hidden = true; }, hold + (animate ? 1400 : 0));
  }

  function close() { clearTimeout(timer); timer = null; if (box) box.hidden = true; next(); }
  function show(entry) { queue.push(entry); if (queue.length > 6) queue.splice(0, queue.length - 6); next(); }
  return { render, show, close };
}
