const contentChannel = typeof BroadcastChannel === 'function' ? new BroadcastChannel('mythastria-content') : null;
contentChannel?.addEventListener('message', e => { if (e.data?.type === 'packs-changed') location.reload(); });
// Replay page for simulator recordings (sim-messages/1). Read-only: it draws what the recording says and never calls
// the Rust kernel. Merge handoff 2026-10-19, step 3. See replay.mjs for the rules of the adapter.
import { mountZoom } from './map-zoom.mjs';   // MAP-ZOOM-01 (GM 2026-10-28: "every map needs a zoom out and in")
import { mountMapPicker } from './map-picker.mjs';   // GM 2026-10-25: maps in folders
import { parseRecording, buildFrames, checkConsistency, ReplayError } from './replay.mjs';
import { loadCatalog } from './catalog.mjs';
import { createSimServicePort } from './engine-port.mjs';
import { rosterFrom } from './character-photos.mjs';            // GM 2026-10-28: the Saved characters tab
import { propMarker } from './props3d.mjs';
import { drawWalls2D, drawGround2D } from './wall-art.mjs';

const $ = id => document.getElementById(id), NS = 'http://www.w3.org/2000/svg';
const mapZoom = mountZoom($('map'));                             // MAP-ZOOM-01: drawMap gives it the whole picture
const svg = (tag, attrs = {}, text) => {
  const e = document.createElementNS(NS, tag);
  for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, String(v));
  if (text !== undefined) e.textContent = String(text);
  return e;
};
const el = (tag, cls, text) => { const e = document.createElement(tag); if (cls) e.className = cls; if (text !== undefined) e.textContent = String(text); return e; };
const css = name => getComputedStyle(document.documentElement).getPropertyValue(name).trim() || '#888';

const ZONE_STYLE = { water: ['#2e5c8c', .35], current: ['#4682b4', .25], obscured: ['#6e5c42', .45], shade: ['#222', .35],
  sunlit: ['#e8c45a', .25], drop: ['#000', .55], cover: ['#7a6a4a', .3] };

let registry = null, frames = [], at = 0, recordingName = '';

// The creature catalog is a standalone manifest (creatures.json, 2026-10-20); without it every creature gets a plain
// marker.
async function loadRegistry() {
  registry = await loadCatalog();
}

function show(text, isError = false) { const n = $('notice'); n.textContent = text; n.className = isError ? 'notice error' : 'notice'; n.hidden = !text; }

function open(text, name, { last = false, more = false } = {}) {
  try {
    const rec = parseRecording(text);
    frames = buildFrames(rec, registry);
    const problems = checkConsistency(rec);
    // 2026-10-21 (GM: "simulator fights seems to have no simulator"): a live fight still being revealed ends in the
    // state before the next turn, not the end of the fight. Show the turn just played (its dice and log), and call
    // the trailing frame what it is.
    const tail = frames[frames.length - 1];
    if (more && tail?.kind === 'final') {
      const next = tail.view.state.combatants.find(c => c.id === tail.view.state.active);
      Object.assign(tail, { kind: 'pending', label: `Next up: ${next?.name ?? 'the next combatant'}` });
    }
    at = last ? Math.max(0, frames.length - (more && frames.length > 1 ? 2 : 1)) : 0; recordingName = name;
    $('slider').max = frames.length - 1;
    const s = rec.scenario;
    $('source').textContent = `${name}: ${s.source_scenario ?? '?'}, seed ${s.seed ?? '?'}, ${s.level ? 'level ' + s.level : 'scenario level'}` +
      `${s.items ? ', test item kits' : ''}${s.note ? '. ' + s.note : ''}`;
    show(problems.length ? 'The recording disagrees with itself (shown as recorded): ' + problems.join('; ') : '', problems.length > 0);
    draw();
  } catch (e) {
    show(e instanceof ReplayError || e instanceof SyntaxError ? 'Cannot replay this file: ' + e.message : String(e), true);
  }
}

function bounds(view) {
  const m = view.map;
  const pts = view.state.combatants.filter(c => c.x > -50 && c.y > -50).flatMap(c => [[c.x, c.y]]);
  if (!pts.length) return [0, 0, m.cols, m.rows];
  const xs = pts.map(p => p[0]), ys = pts.map(p => p[1]);
  const x0 = Math.max(0, Math.floor(Math.min(...xs)) - 5), y0 = Math.max(0, Math.floor(Math.min(...ys)) - 5);
  const x1 = Math.min(m.cols, Math.ceil(Math.max(...xs)) + 6), y1 = Math.min(m.rows, Math.ceil(Math.max(...ys)) + 6);
  return [x0, y0, Math.max(x1, x0 + 6), Math.max(y1, y0 + 6)];
}

function drawMap(frame) {
  const v = frame.view, m = v.map, root = $('map');
  const [x0, y0, x1, y1] = bounds(v);
  const solid = (m.wall_cells ?? []).length > 0, pad = solid ? 1.5 : .2;   // MAP RULE: room for the stone fading past the edge
  mapZoom.view(x0 - pad, y0 - pad, x1 - x0 + 2 * pad, y1 - y0 + 2 * pad);   // MAP-ZOOM-01: the part zoomed in on
  root.replaceChildren();
  drawGround2D(root, m, svg);                         // REGION-01: a terrain battle's ground
  // squares: a token at (x, y) fills [x, x + 1] on screen (the client's +0.5 display offset); edges at half squares
  for (let x = x0; x <= x1; x++) root.append(svg('line', { x1: x, y1: y0, x2: x, y2: y1, stroke: css('--line') || '#444', 'stroke-width': .01 }));
  for (let y = y0; y <= y1; y++) root.append(svg('line', { x1: x0, y1: y, x2: x1, y2: y, stroke: css('--line') || '#444', 'stroke-width': .01 }));
  for (const z of m.zones) {
    const [a, b, c, d] = z.rect, [fill, op] = ZONE_STYLE[z.kind] ?? ['#999', .2];
    const r = svg('rect', { x: a, y: b, width: c - a + 1, height: d - b + 1, fill, 'fill-opacity': op });
    r.append(svg('title', {}, `${z.kind} ${z.id}` + (z.kind === 'current' ? ` (${z.ft} ft, ${z.dx},${z.dy})` : '') +
      (z.level ? ` (${z.level})` : '') + (z.height ? ` (${z.height} ft drop)` : '')));
    root.append(r);
    root.append(svg('text', { x: a + .1, y: b + .35, 'font-size': .28, fill: '#ddd' }, z.kind));
  }
  drawWalls2D(root, m, svg);                          // MAP RULE (GM 2026-10-20): walls at least a square thick, drawn as stone
  for (const w of m.walls) {
    if (solid && !w.door || w.natural) continue;      // the stone squares are the wall now; trees and rocks show their own
    const [[ax, ay], [bx, by]] = w.points;
    root.append(svg('line', { class: w.door ? 'door' : 'wall', x1: ax + .5, y1: ay + .5, x2: bx + .5, y2: by + .5, 'stroke-linecap': 'round',
      stroke: w.door ? (w.open ? '#7fbf7f' : '#c08a3e') : '#d8d0c0', 'stroke-width': w.door ? .14 : .1,
      'stroke-dasharray': w.door && w.open ? '.15 .1' : '' }));
  }
  for (const l of m.lighting.lights ?? []) {
    if (l.x === undefined) continue;
    root.append(svg('circle', { cx: l.x + .5, cy: l.y + .5, r: (l.dim_ft ?? 0) / m.square_ft, fill: '#ffd36b', 'fill-opacity': .06 }));
    root.append(svg('circle', { cx: l.x + .5, cy: l.y + .5, r: .12, fill: '#ffd36b' }));
  }
  for (const p of m.props ?? []) {                               // 2026-10-19: display-only props
    const mk = propMarker(p.kind), round = mk.family === 'green' || mk.family === 'stone';
    const e = round ? svg('circle', { cx: p.x + .5, cy: p.y + .5, r: .3, fill: mk.colour, opacity: .85 })
      : svg('rect', { x: p.x + .2, y: p.y + .25, width: .6, height: .5, rx: .06, fill: mk.colour, opacity: .85 });
    e.append(svg('title', {}, p.label || p.kind));
    root.append(e);
  }
  // the planned route of this turn's decision (already in squares)
  for (const d of frame.action?.decisions ?? []) {
    const mv = d.move_squares;
    if (mv?.path?.length) root.append(svg('polyline', { points: mv.path.map(p => `${p[0] + .5},${p[1] + .5}`).join(' '), fill: 'none',
      stroke: '#e0c060', 'stroke-width': .06, 'stroke-dasharray': '.12 .08' }));
  }
  for (const c of v.state.combatants) {
    if (c.x < -50 || c.y < -50) continue;                      // escaped characters sit off the map in the recording
    const size = c.space_ft / m.square_ft, x = c.x + .5, y = c.y + .5;
    const col = c.side === 'friend' ? '#5aa0e0' : '#e06a5a', active = c.id === v.state.active;
    const g = svg('g', { 'data-actor': c.id, class: 'token' });
    g.append(svg('rect', { x: x - size / 2, y: y - size / 2, width: size, height: size, rx: .06, fill: col, 'fill-opacity': active ? .2 : .06,
      stroke: active ? '#e0c060' : col, 'stroke-width': active ? .07 : .03, opacity: c.down ? .4 : 1 }));
    if (c.token_path) g.append(svg('image', { href: c.token_path, x: x - size * .47, y: y - size * .47, width: size * .94, height: size * .94, opacity: c.down ? .3 : 1 }));
    else g.append(svg('text', { x, y: y + .12, 'text-anchor': 'middle', 'font-size': .34 * Math.min(size, 1.6), fill: col }, initials(c.name)));
    const frac = c.hp_max ? Math.max(0, c.hp) / c.hp_max : 0;
    g.append(svg('rect', { x: x - size / 2, y: y + size / 2 - .1, width: size * frac, height: .08, fill: frac > .5 ? '#6c6' : frac > .25 ? '#dc6' : '#d55' }));
    const badges = [...(c.conditions ?? []), c.underwater ? 'underwater' : null, c.aloft ? 'aloft' : null, c.mount ? 'mounted' : null].filter(Boolean);
    if (badges.length) g.append(svg('text', { x: x - size / 2, y: y - size / 2 - .05, 'font-size': .2, fill: '#eee' }, badges.join(', ')));
    g.append(svg('title', {}, `${c.name}: ${c.hp}/${c.hp_max} HP, AC ${c.ac}${badges.length ? ', ' + badges.join(', ') : ''}` +
      (c.token_note ? ` (no token art: ${c.token_note})` : '')));
    root.append(g);
  }
}

const initials = n => String(n).split(/\s+/).map(w => w[0]).join('').slice(0, 3);

function drawPanels(frame) {
  const v = frame.view;
  $('label').textContent = `${frame.index + 1}/${frames.length}  ${frame.label}`;
  $('lighting').textContent = `Light: ${v.map.lighting.ambient}${(v.map.lighting.lights ?? []).length ? `, ${v.map.lighting.lights.length} light(s)` : ''}` +
    ` (shown as an indicator only)`;
  const roster = $('roster'); roster.replaceChildren();
  for (const c of v.state.combatants) {
    const row = el('div', 'row' + (c.id === v.state.active ? ' active' : '') + (c.down ? ' down' : ''));
    const extra = [c.temp_hp ? `${c.temp_hp} temp HP` : '', c.exhaustion ? `Exhaustion ${c.exhaustion}` : '',
      c.breath_rounds !== null && c.breath_rounds !== undefined ? `breath ${c.breath_rounds} rounds` : '',
      c.dead ? 'dead' : c.stable ? 'stable' : '', c.down && c.death_saves ? `death saves ${c.death_saves.successes}/${c.death_saves.failures}` : '']
      .filter(Boolean).join(', ');
    row.textContent = `${c.name}  ${c.hp}/${c.hp_max} HP  AC ${c.ac}${(c.conditions ?? []).length ? '  ' + c.conditions.join(', ') : ''}${extra ? '  ' + extra : ''}`;
    roster.append(row);
  }
  const act = $('action'); act.replaceChildren();
  if (frame.action) {
    act.append(el('div', 'who', `${frame.action.actor_name} (${frame.action.controller})`));
    for (const d of frame.action.decisions ?? []) {
      act.append(el('div', 'decision', `Chose: ${d.summary ?? d.action_name ?? '?'}`));
      for (const a of d.alternatives ?? []) act.append(el('div', 'alt', `${a.id}: ${a.summary}`));
    }
    for (const t of frame.action.intent ?? []) act.append(el('div', 'intent', t));
  } else act.append(el('div', 'who', frame.kind === 'final' ? 'The recording ends here.' :
    frame.kind === 'pending' ? 'Not played yet: press Next turn.' : 'No action recorded.'));
  const log = $('log'); log.replaceChildren();
  for (const l of frame.result?.log ?? []) log.append(el('div', 'log-' + l.kind, l.text));
  const un = $('unsupported');
  un.textContent = v.unsupported.length ? 'Not drawn: ' + v.unsupported.join('; ') : '';
}

function draw() {
  if (!frames.length) return;
  const f = frames[at];
  $('slider').value = at;
  drawMap(f); drawPanels(f);
}

function step(d) { if (!frames.length) return; at = Math.max(0, Math.min(frames.length - 1, at + d)); draw(); }

addEventListener('DOMContentLoaded', async () => {
  await loadRegistry();
  $('file').addEventListener('change', async e => { const f = e.target.files[0]; if (f) open(await f.text(), f.name); });
  $('prev').addEventListener('click', () => step(-1));
  $('next').addEventListener('click', () => step(1));
  $('slider').addEventListener('input', e => { at = Number(e.target.value); draw(); });
  addEventListener('keydown', e => { if (e.key === 'ArrowRight') step(1); if (e.key === 'ArrowLeft') step(-1); });
  await startLive();
  // GM 2026-10-28 ("remove test characters from simulator fights. Allow characters to be loaded"): no sample recordings
  // (they were fought by the test heroes); with nothing to show yet, the page says how to start one
  if (!frames.length) $('source').textContent = 'No fight yet: tick your Saved characters (or Load characters…), choose a map and press New fight.';
});

// ------------------------------------------------------------------ live simulator (merge step 4 B, first increment)
// Only when this page is served by the simulator service (Mythastria tools/sim_service.py): the simulator plays the
// fight and the service reveals it one turn per request. The page draws what it receives with the replay renderer; it
// never resolves a rule. Messages so far always end with a state, so they are a valid (partial) recording.
let live = null, liveMessages = [];

function liveStatus(text, isError = false) { const n = $('live-status'); n.textContent = text; n.className = isError ? 'error' : ''; }

function showLive(note) {
  open(liveMessages, 'live simulator', { last: true, more: !live.done });
  liveStatus(`${note} Revision ${live.revision}${live.done ? '; the fight is over (or out of rounds).' : '.'}`);
  $('live-next').disabled = live.done;
}

async function startLive() {
  const port = createSimServicePort();
  let hello;
  try { hello = await port.hello(); } catch { return; }          // a plain file server: no live panel
  if (!hello?.ok) return;
  live = port;
  $('live').hidden = false;
  const sel = $('live-scenario');
  // GM 2026-10-28 ("I only want to use characters saved in the saved characters tab"): the party is the ticked saved
  // characters (sent as their sheets; each fights at its own level), never test characters.
  const first = hello.scenarios.includes('test/goblin_den_2024.json') ? 'test/goblin_den_2024.json' : hello.scenarios[0];
  for (const n of hello.scenarios) sel.append(new Option(n, n, n === first, n === first));
  mountMapPicker(sel, hello.scenario_tree);                       // GM 2026-10-25: maps in folders
  drawLiveChars();
  // GM 2026-10-28 ("Allow characters to be loaded"): a character saved on the Characters page (Load characters…) shows here at once
  addEventListener('storage', e => { if (e.key === 'isles-character-roster-v1') drawLiveChars(); });
  $('live-load').addEventListener('click', () => window.open('characters.html?tab=import', 'mythastria-characters'));
  $('live-new').addEventListener('click', liveNew);
  $('live-next').addEventListener('click', liveNext);
  liveStatus(`Connected to the ${hello.authority}.`);
}

const liveChosen = new Set();
function drawLiveChars() {
  const roster = rosterFrom(), list = $('live-chars-list');
  list.replaceChildren(...roster.map(c => {
    const lab = document.createElement('label'), cb = Object.assign(document.createElement('input'), { type: 'checkbox', checked: liveChosen.has(c.id) });
    const lv = (c.classes ?? []).reduce((n, k) => n + (k.level || 0), 0);
    cb.addEventListener('change', () => { if (cb.checked) liveChosen.add(c.id); else liveChosen.delete(c.id); drawLiveChars(); });
    cb.disabled = !cb.checked && liveChosen.size >= 7;
    lab.append(cb, ` ${c.name}${lv ? ` (level ${lv})` : ''}`); return lab;
  }));
  if (!roster.length) list.textContent = 'No saved characters yet.';
  $('live-chars').querySelector('summary').textContent = liveChosen.size ? `Saved characters (${liveChosen.size})` : 'Saved characters';
}
async function liveNew() {
  const characters = rosterFrom().filter(c => liveChosen.has(c.id)).map(({ provenance, import: _, build, ...rest }) => rest);
  if (!characters.length) { liveStatus('Tick the party in Saved characters first.', true); return; }
  const settings = { scenario: $('live-scenario').value, characters,
    seed: Number($('live-seed').value) || 1, rounds: Number($('live-rounds').value) || 3 };
  liveStatus('The simulator is playing the fight…');
  $('live-new').disabled = $('live-next').disabled = true;
  const out = await live.newFight(settings);
  $('live-new').disabled = false;
  if (!out.ok) { liveStatus('Refused: ' + out.error, true); return; }
  liveMessages = out.messages;
  showLive('Fight ready: press Next turn.');
}

async function liveNext() {
  const out = await live.step();
  if (out.ok) { liveMessages = liveMessages.concat(out.messages); showLive(out.messages.length ? 'Turn shown.' : 'Nothing more to show.'); return; }
  if (out.status === 409) {                                       // stale: someone else stepped; take the service's list
    const all = await live.messages();
    if (all.ok) { liveMessages = all.messages; showLive('That step was already taken; caught up with the service.'); }
    liveStatus('Refused (stale step): ' + out.error + ' Showing what the service has revealed.', true);
    return;
  }
  liveStatus('Refused: ' + out.error, true);
}
