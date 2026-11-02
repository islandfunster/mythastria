// REFEREE-01 (GM 2026-10-22): the Spells page. Every SRD 5.2.1 spell with what the engine plays of it (Play live,
// simulator only, or the GM rules it), the rules the referee reads from it, and the GM's own wording (GM: "allow
// ambiguous descriptions to be modified for clarity for that GM"). The service keeps the GM's wording on this PC.
const $ = id => document.getElementById(id);
const el = (tag, cls, text) => { const e = document.createElement(tag); if (cls) e.className = cls; if (text != null) e.textContent = text; return e; };
let token = null, spells = [], current = null;

// GM 2026-10-27 ("Make the page say to press F5 after a restart instead of showing an empty list"): a page opened while
// Mythastria was stopped or restarting stayed on "Loading the spells…" with no list; one opened before a restart had its
// key refused when saving a wording. Both now say what to do.
const DOWN = 'Mythastria is not answering: it is stopped or restarting. Start it with Start_Mythastria.bat if its window is closed, then press F5 here.';
const RESTARTED = 'Mythastria restarted since this page was opened: press F5 to load the page again.';
async function hello() { const out = await (await fetch('/api/hello')).json(); token = out.token; return out; }
async function post(path, body) {
  try {
    if (!token) await hello();
    const res = await fetch(path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ ...body, token }) });
    const out = await res.json().catch(() => ({ ok: false, error: 'The service sent no answer.' }));
    if (res.status === 403 && /token/i.test(out.error || '')) return { ok: false, error: RESTARTED };
    return res.ok ? out : { ...out, ok: false };
  } catch { return { ok: false, error: DOWN }; }                      // no answer at all: stopped, or between restarts
}
const status = (text, error = false) => { $('status').textContent = text; $('status').className = error ? 'error' : ''; };
const TAG = { 'played in Play live': ['live', 'Play live'], 'simulator only': ['sim', 'Simulator'], 'not yet (the GM rules it)': ['dm', 'GM rules'] };

export function rulesRows(s) {
  const r = s.range?.kind === 'ranged' ? `${s.range.ft} ft` : s.range?.kind === 'touch' ? 'Touch' : s.range?.kind === 'self' ? 'Self' : (s.range?.text ?? '');
  const area = s.area ? `${s.area.size_ft}-ft ${s.area.shape}` + (s.area.width_ft ? `, ${s.area.width_ft} ft wide` : '') : '';
  const who = s.targets?.kind === 'area' ? (s.targets.choice ? 'Creatures of your choice in the area' : 'Every creature in the area')
    : s.targets?.kind ? `${s.targets.max ?? ''} ${s.targets.kind}${s.targets.choice ? ' of your choice' : ''}`.trim() : '';
  return [['Level', s.level === 0 ? 'Cantrip' : s.level], ['School', s.school], ['Casting time', s.casting_time], ['Range', r],
    ['Duration', s.duration], ['Area', area], ['Affects', who],
    ['Attack', s.attack ? `${s.attack} spell attack` : ''], ['Saving throw', s.save ? `${s.save.ability.toUpperCase()}${s.save.half ? ', half on a success' : ''}` : ''],
    ['Damage', (s.damage ?? []).map(d => `${d.dice} ${d.type}${d.plus_mod ? ' + modifier' : ''}`).join(' or ')],
    ['Healing', s.healing ? `${s.healing.dice ?? ''}${s.healing.plus_mod ? ' + modifier' : ''}` : ''],
    ['Conditions', (s.conditions ?? []).join(', ')], ['Classes', (s.classes ?? []).join(', ')],
    ['Engine', s.status], ['Not read', (s.unread ?? []).join('; ')]].filter(([, v]) => v !== '' && v != null);
}

function drawList() {
  const q = $('find').value.trim().toLowerCase(), lv = $('level').value, show = $('show').value;
  const rows = spells.filter(s => (!q || s.name.toLowerCase().includes(q)) && (lv === '' || String(s.level) === lv)
    && (!show || (show === 'mine' ? s.clarified : s.status === show)));
  $('list').replaceChildren(...rows.map(s => {
    const li = el('li'), b = el('button');
    b.setAttribute('aria-current', String(s.name === current));
    const tags = el('span');
    const [cls, label] = TAG[s.status] ?? ['dm', s.status];
    tags.append(el('span', 'tag ' + cls, label));
    if (s.clarified) tags.append(' ', el('span', 'tag mine', 'My wording'));
    b.append(el('span', '', `${s.name} · ${s.level === 0 ? 'cantrip' : 'level ' + s.level}`), tags);
    b.onclick = () => { current = s.name; drawList(); drawDetail(); };
    li.append(b);
    return li;
  }));
  const count = k => spells.filter(s => s.status === k).length;
  $('counts').textContent = `${spells.length} SRD spells: ${count('played in Play live')} played in Play live, ${count('simulator only')} by the simulator only, `
    + `${count('not yet (the GM rules it)')} ruled by the GM; ${spells.filter(s => s.clarified).length} reworded for your table. Showing ${rows.length}.`;
}

function drawDetail() {
  const s = spells.find(x => x.name === current);
  $('d-body').hidden = !s;
  if (!s) return;
  $('d-name').textContent = s.name + (s.clarified ? ' (my wording)' : '');
  $('d-rules').replaceChildren(...rulesRows(s).flatMap(([k, v]) => [el('dt', '', k), el('dd', '', v)]));
  $('d-text').value = s.clarified ? s.text : s.srd_text;
  $('d-note').value = s.clarification?.note ?? '';
  $('d-clear').disabled = !s.clarified;
  $('d-srd').textContent = s.srd_text;
}

async function load() {
  const out = await post('/api/spells', {});
  if (!out.ok) {
    status(out.error || 'The Spells page needs Mythastria running (Start_Mythastria.bat).', true);
    if (!spells.length) $('counts').textContent = 'No spells loaded: press F5 once Mythastria is running.';
    return;
  }
  spells = out.spells;
  status(`SRD 5.2.1 spells (CC-BY-4.0). The referee checks every spell cast in Play live against these rules.`);
  drawList(); drawDetail();
}

$('d-save').onclick = async () => {
  const s = spells.find(x => x.name === current); if (!s) return;
  const text = $('d-text').value.trim();
  if (!text || text === s.srd_text.trim()) { status('Change the wording first (or use Back to the SRD text).', true); return; }
  const out = await post('/api/spells/clarify', { spell: s.name, text, note: $('d-note').value });
  if (!out.ok) { status(out.error, true); return; }
  status(`${s.name}: your wording is saved for this table.`); await load();
};
$('d-clear').onclick = async () => {
  const out = await post('/api/spells/clarify', { spell: current, clear: true });
  if (!out.ok) { status(out.error, true); return; }
  status(`${current}: back to the SRD text.`); await load();
};
for (const id of ['find', 'level', 'show']) $(id).addEventListener('input', drawList);
for (let i = 1; i <= 9; i++) $('level').append(new Option('Level ' + i, String(i)));
load();
