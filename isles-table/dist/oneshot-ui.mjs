// ONE-SHOT-01 (GM 2026-11-02: "Let's build a one-shot adventure builder. JUst like you said with a map, a story the GM can
// generate as text for locations, and maps for those locations. Encounters can be placed, traps, puzzles, social and combat"):
// the builder. The service checks and keeps a one-shot (tools/one_shot.py), and Save and play writes it as an adventure pack.
// Generate uses the model loaded in Chat; every field can be typed instead. GM 2026-11-02: "puzzles are narrative": a puzzle
// is words, a hint and a solution, with no dice. Maps come from the service: imported, drawn on Region map, or test maps.
const $ = id => document.getElementById(id);
const el = (tag, text, cls) => { const e = document.createElement(tag); if (text !== undefined) e.textContent = text; if (cls) e.className = cls; return e; };
const SVG = 'http://www.w3.org/2000/svg';
const svg = (tag, attrs) => { const e = document.createElementNS(SVG, tag); for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, v); return e; };
const blank = () => ({ title: '', level: 3, tone: '', premise: '', hook: '', question: '', locations: [] });
const blankPlace = () => ({ name: '', map: '', keep_creatures: false, read_aloud: '', gm_text: '', creatures: [], traps: [], puzzles: [] });

let token = null, setup = null, doc = blank(), placing = null;
const views = new Map();                                            // scenario -> the map's small picture

function status(text, bad = false) { $('status').textContent = text; $('status').className = bad ? 'error' : ''; }
async function hello() { const out = await (await fetch('/api/hello')).json(); token = out.token; return out; }
async function call(body, retry = true) {
  const r = await fetch('/api/oneshot', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ ...body, token }) });
  const out = await r.json().catch(() => ({ ok: false, error: 'The service sent no answer.' }));
  if (r.status === 403 && retry && /token/i.test(out.error || '')) { await hello(); return call(body, false); }
  return out.ok ? out : { ...out, ok: false, error: out.error || out.refused || `HTTP ${r.status}` };
}

function field(label, value, onChange, { area = false, generate = null, max = 2000 } = {}) {
  const box = el('label', undefined, 'field'), head = el('span'), input = el(area ? 'textarea' : 'input');
  if (!area) input.type = 'text';
  input.maxLength = max; input.value = value ?? '';
  input.addEventListener('input', () => onChange(input.value));
  head.append(el('b', label));
  if (generate) {
    const b = el('button', 'Generate', 'quiet'); b.type = 'button';
    b.title = setup.model ? 'Ask the model loaded in Chat. Your words stay if it fails.' : 'Load a model in Chat first, or type this part yourself.';
    b.addEventListener('click', async e => {
      e.preventDefault(); b.disabled = true; status(`Writing ${label.toLowerCase()}…`);
      const out = await call({ op: 'generate', field: generate.field, doc, ...(generate.place ? { place: generate.place } : {}), idea: input.value.slice(0, 500) });
      b.disabled = false;
      if (!out.ok) { status(out.error, true); return; }
      input.value = out.text; onChange(out.text); status('Written. Change anything you like.');
    });
    head.append(b);
  }
  box.append(head, input);
  return box;
}

const pick = (label, options, value, onChange) => {
  const s = el('select'); s.setAttribute('aria-label', label);
  for (const [v, t] of options) { const o = el('option', t); o.value = v; o.selected = v === value; s.append(o); }
  s.addEventListener('change', () => onChange(s.value));
  return s;
};
const removeButton = (what, onClick) => { const b = el('button', 'Remove', 'quiet'); b.type = 'button'; b.setAttribute('aria-label', 'Remove ' + what); b.addEventListener('click', onClick); return b; };
const addButton = (text, onClick) => { const b = el('button', text, 'quiet'); b.type = 'button'; b.addEventListener('click', onClick); return b; };

async function picture(place) {
  const box = el('div');
  if (!place.map) { box.append(el('p', 'Choose a map to place things on it.', 'note')); return box; }
  if (!views.has(place.map)) {
    const out = await call({ op: 'map', scenario: place.map });
    if (!out.ok) { box.append(el('p', out.error, 'note')); return box; }
    views.set(place.map, out.map);
  }
  const m = views.get(place.map), s = svg('svg', { class: 'mini', viewBox: `-0.5 -0.5 ${m.cols} ${m.rows}`, role: 'img', 'aria-label': `Map of ${place.name || 'this location'}` });
  for (const [x, y] of m.wall_cells) s.append(svg('rect', { class: 'rock', x: x - 0.5, y: y - 0.5, width: 1, height: 1 }));
  for (const pts of m.walls) if (pts?.length === 2) s.append(svg('line', { class: 'line', x1: pts[0][0], y1: pts[0][1], x2: pts[1][0], y2: pts[1][1] }));
  for (const c of m.marks) if (c.pc || place.keep_creatures) s.append(svg('circle', { class: c.pc ? 'pc' : 'foe', cx: c.x, cy: c.y, r: 0.35 }));
  for (const r of place.creatures) if (r.at) s.append(svg('circle', { class: 'put', cx: r.at[0], cy: r.at[1], r: 0.4 }));
  for (const t of place.traps) for (const [x, y] of t.squares ?? []) s.append(svg('rect', { class: 'trap', x: x - 0.4, y: y - 0.4, width: 0.8, height: 0.8 }));
  s.addEventListener('click', e => {
    if (!placing || placing.place !== place) return;
    const p = s.createSVGPoint(); p.x = e.clientX; p.y = e.clientY;
    const q = p.matrixTransform(s.getScreenCTM().inverse()), sq = [Math.round(q.x), Math.round(q.y)];
    if (m.wall_cells.some(([x, y]) => x === sq[0] && y === sq[1])) { status('That square is rock: pick a floor square.', true); return; }
    placing.done(sq); placing = null; status(`Placed at square ${sq[0]}, ${sq[1]}.`); draw();
  });
  box.append(s, el('p', 'Green: where the party starts. Gold: what you placed. Choose Place, then click a square.', 'note'));
  return box;
}

function placeButton(place, what, done) {
  return addButton('Place', () => { placing = { place, done }; status(`Click a square on the map for ${what}.`); });
}

function creatureRow(place, r) {
  const box = el('div', undefined, 'thing'), line = el('div', undefined, 'row');
  const n = el('input'); n.type = 'number'; n.min = '1'; n.max = '12'; n.value = String(r.count); n.setAttribute('aria-label', `How many ${r.name}`);
  n.addEventListener('change', () => { r.count = Math.max(1, Math.min(12, Math.round(Number(n.value) || 1))); n.value = String(r.count); });
  line.append(n, pick('Creature', setup.creatures.map(c => [c, c]), r.name, v => { r.name = v; }),
    pick('Attitude', setup.attitudes.map(a => [a, a]), r.attitude, v => { r.attitude = v; }),
    placeButton(place, r.name, sq => { r.at = sq; }),
    removeButton(r.name, () => { place.creatures.splice(place.creatures.indexOf(r), 1); draw(); }));
  box.append(line, el('p', r.at ? `Starts at square ${r.at[0]}, ${r.at[1]}.` : "Starts near the foes' start.", 'note'),
    field('Name, for a person the party can meet (optional)', r.who, v => { r.who = v; }, { max: 60 }),
    field('What they want', r.wants, v => { r.wants = v; }, { max: 300 }),
    field('What they know', r.knows, v => { r.knows = v; }, { max: 300 }));
  return box;
}

function trapRow(place, t) {
  const box = el('div', undefined, 'thing'), line = el('div', undefined, 'row'), kinds = setup.traps;
  const bands = () => (kinds[t.kind]?.bands ?? []).map(b => [String(b), String(b)]);
  line.append(pick('Trap', Object.entries(kinds).map(([k, v]) => [k, v.name]), t.kind, v => { t.kind = v; t.band = kinds[v].bands[0]; draw(); }),
    pick('Level band', bands(), String(t.band), v => { t.band = kinds[t.kind].bands.find(b => String(b) === v); }),
    placeButton(place, kinds[t.kind]?.name ?? 'the trap', sq => { t.squares = [sq]; }),
    removeButton(kinds[t.kind]?.name ?? 'trap', () => { place.traps.splice(place.traps.indexOf(t), 1); draw(); }));
  box.append(line, el('p', t.squares?.length ? `On square ${t.squares[0][0]}, ${t.squares[0][1]}.` : 'Place it on the map.', 'note'));
  return box;
}

function puzzleRow(place, p) {
  const box = el('div', undefined, 'thing'), line = el('div', undefined, 'row');
  line.append(el('strong', 'Puzzle'), removeButton(p.name || 'this puzzle', () => { place.puzzles.splice(place.puzzles.indexOf(p), 1); draw(); }));
  box.append(line, field('Name', p.name, v => { p.name = v; }, { max: 80 }),
    field('What the players see', p.text, v => { p.text = v; }, { area: true, max: 1500, generate: { field: 'puzzle', place } }),
    field('A hint to give if they are stuck', p.hint, v => { p.hint = v; }, { max: 400 }),
    field('The solution (GM only)', p.solution, v => { p.solution = v; }, { max: 800 }));
  return box;
}

async function placeCard(place, n) {
  const box = el('section', undefined, 'place');
  const head = el('div', undefined, 'row');
  head.append(el('h3', `Location ${n}`), removeButton(`location ${n}`, () => { doc.locations.splice(doc.locations.indexOf(place), 1); draw(); }));
  box.append(head, field('Name', place.name, v => { place.name = v; }, { max: 60 }));
  const mapRow = el('label', undefined, 'field'), span = el('span');
  span.append(el('b', 'Map'));
  mapRow.append(span, pick('Map for this location', [['', 'Choose a map'], ...setup.maps.map(m => [m, m])], place.map, v => { place.map = v; draw(); }));
  const keep = el('label', undefined, 'row'), tick = el('input'); tick.type = 'checkbox'; tick.checked = place.keep_creatures;
  tick.addEventListener('change', () => { place.keep_creatures = tick.checked; draw(); });
  keep.append(tick, "Keep the map's own creatures");
  box.append(mapRow, keep, await picture(place),
    el('p', 'Need a new map? Draw a site on Region map with a model loaded, or import a picture on Play live, then choose it here.', 'note'),
    field('Read aloud on arrival', place.read_aloud, v => { place.read_aloud = v; }, { area: true, generate: { field: 'read_aloud', place } }),
    field('GM notes', place.gm_text, v => { place.gm_text = v; }, { area: true, max: 4000, generate: { field: 'gm_text', place } }));
  box.append(el('h4', 'Combat and social'), ...place.creatures.map(r => creatureRow(place, r)));
  box.append(addButton('Add a creature or person', () => { place.creatures.push({ name: setup.creatures.includes('Goblin Warrior') ? 'Goblin Warrior' : setup.creatures[0], count: 1, attitude: 'Hostile', who: '', wants: '', knows: '' }); draw(); }));
  box.append(el('h4', 'Traps'), ...place.traps.map(t => trapRow(place, t)));
  box.append(addButton('Add a trap', () => { const [kind, t] = Object.entries(setup.traps)[0]; place.traps.push({ kind, band: t.bands[0], squares: [] }); draw(); }));
  box.append(el('h4', 'Puzzles'), ...place.puzzles.map(p => puzzleRow(place, p)));
  box.append(addButton('Add a puzzle', () => { place.puzzles.push({ name: '', text: '', hint: '', solution: '' }); draw(); }));
  return box;
}

async function draw() {
  const box = el('section', undefined, 'panel');
  box.append(el('h2', doc.title || 'New one-shot'));
  const lv = el('label', undefined, 'field'), s = el('span'), level = el('input');
  s.append(el('b', 'Party level')); level.type = 'number'; level.min = '1'; level.max = '20'; level.value = String(doc.level);
  level.addEventListener('change', () => { doc.level = Math.max(1, Math.min(20, Math.round(Number(level.value) || 1))); });
  lv.append(s, level);
  const two = el('div', undefined, 'two');
  two.append(field('Title', doc.title, v => { doc.title = v; }, { max: 80 }), field('Tone', doc.tone, v => { doc.tone = v; }, { max: 200 }));
  box.append(two, lv, field('Premise', doc.premise, v => { doc.premise = v; }, { area: true, max: 4000, generate: { field: 'premise' } }),
    field('Hook', doc.hook, v => { doc.hook = v; }, { area: true, max: 1500, generate: { field: 'hook' } }),
    field('The question this adventure asks', doc.question, v => { doc.question = v; }, { max: 300, generate: { field: 'question' } }));
  if (!setup.model) box.append(el('p', 'Generate needs a model loaded in Chat. Without one, type each part yourself.', 'note'));
  box.append(el('h2', 'Locations'));
  const cards = await Promise.all(doc.locations.map((p, i) => placeCard(p, i + 1)));
  box.append(...cards, addButton('Add a location', () => { doc.locations.push(blankPlace()); draw(); }));
  const actions = el('div', undefined, 'row actions');
  const save = el('button', 'Save'), play = el('button', 'Save and play'), link = el('a', 'Open Play an adventure');
  save.type = play.type = 'button'; link.href = './adventure.html'; link.hidden = true;
  save.addEventListener('click', async () => {
    const out = await call({ op: 'save', doc });
    if (!out.ok) { status(out.error, true); return; }
    doc = out.doc; status('Saved on this PC.'); await drawSaved();
  });
  play.addEventListener('click', async () => {
    status('Writing the adventure…');
    const out = await call({ op: 'publish', doc });
    if (!out.ok) { status(out.error, true); return; }
    doc = out.doc; await drawSaved(); status('Ready: it is loaded on Play an adventure.'); link.hidden = false;
  });
  actions.append(save, play, link);
  box.append(actions);
  $('editor').replaceChildren(box);
}

async function drawSaved() {
  const out = await call({ op: 'list' });
  $('saved').replaceChildren(...(out.one_shots ?? []).map(o => {
    const li = el('li'), open = el('button', `${o.title} (${o.places})`, 'quiet'), drop = removeButton(o.title, async () => {
      if (!confirm(`Delete "${o.title}" from this PC?`)) return;
      await call({ op: 'delete', id: o.id });
      if (doc.id === o.id) { doc = blank(); draw(); }
      drawSaved();
    });
    open.type = 'button';
    open.addEventListener('click', async () => { const got = await call({ op: 'get', id: o.id }); if (got.ok) { doc = got.doc; status(`Opened ${o.title}.`); draw(); } else status(got.error, true); });
    li.append(open, drop); return li;
  }));
}

async function main() {
  await hello();
  setup = await call({ op: 'setup' });
  if (!setup.ok) { status(setup.error, true); return; }
  $('new').addEventListener('click', () => { doc = blank(); draw(); });
  await drawSaved();
  await draw();
  status('Write the story, add locations, then Save and play.');
}
main().catch(e => status(e.message, true));
