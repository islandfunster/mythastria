// ADVENTURE-01 (GM 2026-10-21: "what happened to adventures? It needs a big bold something to take you to playing the
// multiplayer dnd game together"): the Adventure page. Before: the installed adventures, the party and its level, and
// Start (the service's /api/adventures/load, as Remix Prep). After: the adventure's places in the pack's order with their
// written encounters, each fight opening Play live on its map with this party and level; Region map, The Stage; End.
// The service remembers the loaded adventure across restarts. The party and level are kept in this browser.
// CHARACTERS-01 phase 4: saved characters (the Characters page's roster in this browser) join the party as in Play live's
// Party box (?characters=<ids>); they fight at their own level. 7 in all, as the service. GM 2026-10-28: no test characters.
import { rosterFrom } from './character-photos.mjs';
import { mountDay } from './adventure-day.mjs';                       // GM 2026-10-24: rests and the party's day
import { mountDowntime } from './adventure-downtime.mjs';             // GM 2026-10-26: crafting, brewing, scribing
import { mergeRoster, loadTableParty, saveTableParty, partyChoice } from './party-store.mjs';   // GM 2026-10-25: the party follows the GM role

const PARTY_KEY = 'mythastria-adventure-party', MAX_PARTY = 7, LEVELS = 20;  // the service's limits for a live fight (the test heroes reach 20: GM 2026-10-26)

function createPort(fetchFn = globalThis.fetch) {
  let token = null;
  async function hello() {
    const r = await fetchFn('/api/hello'); const out = await r.json();
    if (!r.ok || !out.ok) throw new Error(out.error || 'The simulator service is not answering.');
    token = out.token; return out;
  }
  async function post(route, body = {}, retry = true) {
    if (!token) await hello();
    const r = await fetchFn(route, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ ...body, token }) });
    const out = await r.json();
    if (r.status === 403 && retry && /token/i.test(out.error || '')) { await hello(); return post(route, body, false); }
    return out;
  }
  const must = async (route, body) => { const out = await post(route, body); if (!out.ok) throw new Error(out.error || 'Refused.'); return out; };
  return { hello, state: () => must('/api/adventures/state'), plan: pack => must('/api/adventures/plan', { pack }),
    load: pack => must('/api/adventures/load', { pack }),
    unload: (pack, stopFight = false) => must('/api/adventures/unload', { pack, stop_fight: stopFight }),   // GM 2026-10-24
    freeze: frozen => must('/api/live/freeze', { frozen }),
    live: () => post('/api/live/state', { since: 1e9 }), post };
}

const $ = id => document.getElementById(id);
const el = (tag, text, cls) => { const e = document.createElement(tag); if (text !== undefined) e.textContent = text; if (cls) e.className = cls; return e; };
const port = createPort();
const channel = typeof BroadcastChannel === 'function' ? new BroadcastChannel('mythastria-content') : null;
let members = [], packs = [], busy = false, placeNames = {};
let tableParty = null, partyTimer = 0;                             // GM 2026-10-25: the party Mythastria keeps
const rosterAll = () => mergeRoster(rosterFrom(), tableParty);    // this browser's sheets, then the table's
// the party's day: the page's party, saved characters as their sheets (as Play live sends them)
const sheetFor = c => { const { provenance, import: _, build, ...rest } = c; return rest; };
const dayParty = () => { const p = party(), ids = new Set(p.characters); return { ...p, characters: rosterAll().filter(c => ids.has(c.id)).map(sheetFor) }; };
const day = mountDay({ root: $('adv-day'), post: (route, body) => port.post(route, body), status: (t, e) => status(t, e), party: dayParty,
  onChange: () => downtime.refresh() });
const downtime = mountDowntime({ root: $('adv-downtime'), post: (route, body) => port.post(route, body), status: (t, e) => status(t, e),
  party: dayParty, onDay: () => day.refresh() });

const status = (text, error = false) => { $('adv-status').textContent = text; $('adv-status').className = error ? 'error' : ''; };

function savedParty() {
  try { const p = JSON.parse(localStorage.getItem(PARTY_KEY) || 'null'); if (p && Array.isArray(p.members)) return p; } catch { /* a convenience only */ }
  return null;
}
// GM 2026-10-28 ("I only want to use characters saved in the saved characters tab"): the party is the ticked saved
// characters; its level, the highest of theirs (each still fights at its own)
function party() {
  const characters = [...document.querySelectorAll('#adv-chars input:checked')].map(b => b.value), ids = new Set(characters);
  const level = Math.max(1, ...rosterAll().filter(c => ids.has(c.id)).map(c => Math.min(LEVELS, (c.classes ?? []).reduce((n, k) => n + (k.level || 0), 0))));
  return { members: [], characters, level };
}
function keepParty() {
  try { localStorage.setItem(PARTY_KEY, JSON.stringify(party())); } catch { /* without storage it resets next visit */ }
  clearTimeout(partyTimer);                                          // GM 2026-10-25: and Mythastria keeps it for the table
  partyTimer = setTimeout(async () => { const out = await saveTableParty(port.post, party(), rosterAll()); if (out?.ok) tableParty = out.party;
    else status('The party was not kept by Mythastria: ' + (out?.error || 'no answer'), true); }, 500);
  drawPartyLimits(); drawLinks(); day.refresh(); downtime.refresh();
}
function drawPartyLimits() {
  const p = party(), n = p.characters.length;
  for (const b of document.querySelectorAll('#adv-chars input')) b.disabled = !b.checked && n >= MAX_PARTY;
  $('adv-start').disabled = busy || !n || !document.querySelector('#adv-packs input:checked');
}

function drawParty(saved) {
  drawChars(saved);
}
function clearParty() {
  for (const b of document.querySelectorAll('#adv-chars input')) b.checked = false;
  keepParty(); status('Cleared. Tick the party\'s saved characters.');
}

function drawChars(saved = party()) {
  const roster = rosterAll(), chosen = new Set(saved?.characters ?? []);
  $('adv-chars').replaceChildren(...roster.map(c => {
    const label = el('label', undefined, 'check'), box = el('input'), lv = (c.classes ?? []).reduce((n, k) => n + (k.level || 0), 0);
    box.type = 'checkbox'; box.value = c.id; box.checked = chosen.has(c.id); box.addEventListener('change', keepParty);
    label.append(box, ' ' + c.name + (lv ? ` (level ${lv})` : '') + (c.fromTable ? ' (kept by the table)' : '')); return label;
  }));
  if (!roster.length) $('adv-chars').append(el('p', 'No saved characters yet: make one on the Characters page.', 'note'));
}

function fightLink(place) {
  const p = party();
  return './play.html?' + new URLSearchParams({ scenario: place.scenario, level: String(p.level),
    ...(p.characters.length ? { characters: p.characters.join(',') } : {}), ...(place.scene ? { scene: place.scene } : {}) });
}
function drawLinks() {
  for (const a of document.querySelectorAll('a[data-place]')) a.href = fightLink(JSON.parse(a.dataset.place));
  const level = party().level;
  for (const s of document.querySelectorAll('[data-written]'))
    s.textContent = Number(s.dataset.written) !== level ? ` (your party is level ${level}: Remix can adjust it)` : '';
}

function drawChoose() {
  $('adv-choose').hidden = false; $('adv-home').hidden = true; $('adv-links').hidden = true; day.hide(); downtime.hide();
  const box = $('adv-packs');
  box.replaceChildren(...packs.map((p, i) => {
    const label = el('label', undefined, 'adv-pack'), radio = el('input');
    radio.type = 'radio'; radio.name = 'adv-pack'; radio.value = p.id; radio.checked = i === 0;
    radio.addEventListener('change', drawPartyLimits);
    label.append(radio, el('strong', p.name), el('span', ' version ' + p.version, 'note')); return label;
  }));
  if (!packs.length) box.append(el('p', 'No adventures are installed. Mythastria looks for them in the adventures folder beside the engine folder.', 'note'));
  drawPartyLimits();
}

// ONE-SHOT-01 (GM 2026-11-02): a one-shot's location for the GM: what to read aloud, the notes, the people and the narrative
// puzzles (their hint and solution folded away). Read aloud or put a puzzle to the table from Remix on Play live.
function placeNotes(n) {
  const box = el('div', undefined, 'adv-enc');
  if (n.read_aloud) { box.append(el('h4', 'Read aloud')); box.append(el('p', n.read_aloud)); }
  if (n.gm_text) { box.append(el('h4', 'GM notes')); box.append(el('p', n.gm_text)); }
  if (n.people?.length) {
    box.append(el('h4', 'People'));
    const ul = el('ul');
    ul.append(...n.people.map(p => el('li', [`${p.name} (${p.attitude})`, p.wants && `wants: ${p.wants}`, p.knows && `knows: ${p.knows}`].filter(Boolean).join(' · '))));
    box.append(ul);
  }
  for (const p of n.puzzles ?? []) {
    box.append(el('h4', 'Puzzle: ' + p.name), el('p', p.text));
    const more = el('details'), head = el('summary', 'Hint and solution');
    more.append(head, ...(p.hint ? [el('p', 'Hint: ' + p.hint)] : []), ...(p.solution ? [el('p', 'Solution: ' + p.solution)] : []));
    box.append(more);
  }
  return box;
}

function placeItem(place, n) {
  const li = el('li', undefined, 'adv-place');
  const head = el('div', undefined, 'adv-place-head');
  head.append(el('span', String(n), 'adv-n'), el('h3', place.place));
  // GM 2026-10-26 (goal 14): an encounter starts as talk (a social scene on The Stage), exploration (the map, no
  // initiative) or a fight; it can change as the table plays (sim/scenes.py)
  const start = (text, scene, title, cls = 'adv-go quiet') => {
    const a = el('a', text, cls); a.dataset.place = JSON.stringify({ scenario: place.scenario, scene });
    a.target = 'mythastria-battle'; a.href = fightLink({ scenario: place.scenario, scene }); a.title = title; return a;
  };
  const talk = start('Talk', 'social', 'Start as a social scene: no turns; the creatures and their attitudes on The Stage; Influence and checks');
  const explore = start('Explore', 'exploration', 'Start as exploration: the map with no initiative; move freely, Search, Study; traps and light work');
  const go = start('Fight here', 'fight', 'Open Play live on this map with the party and level: a fight (Initiative rolled)', 'adv-go');
  // GM 2026-10-25 ("The remix must only allow the chosen encounter in the Adventure loaded"): Remix opens on this one
  const remix = el('a', 'Remix', 'adv-go quiet'); remix.target = 'mythastria-remix';
  remix.href = './remix.html?' + new URLSearchParams({ encounter: place.scenario, prep: place.scenario });
  remix.title = 'Remix or prep this encounter only (its creatures, attitudes and morale)';
  head.append(talk, ' ', explore, ' ', go, ' ', remix); li.append(head);
  const check = el('p', undefined, 'adv-check-row note'); check.dataset.check = place.scenario; check.hidden = true;   // ENCOUNTER-CHECK-01
  li.append(check);
  if (place.notes) li.append(placeNotes(place.notes));              // ONE-SHOT-01
  else if (!place.encounters.length) li.append(el('p', 'No written encounter yet: the map plays with its own creatures.', 'note'));
  for (const e of place.encounters) {
    const box = el('div', undefined, 'adv-enc');
    box.append(el('h4', (e.room ? e.room + ' · ' : '') + (e.name || 'Encounter')));
    const facts = [e.level ? 'written for level ' + e.level : '', e.party_size ? e.party_size + ' characters' : '', e.creatures.join(', ')].filter(Boolean).join(' · ');
    if (facts) {
      const p = el('p', facts, 'note'), hint = el('span');
      if (e.level) { hint.dataset.written = String(e.level); p.append(hint); }
      box.append(p);
    }
    if (e.story.length) { const ul = el('ul'); ul.append(...e.story.map(s => el('li', s))); box.append(ul); }
    li.append(box);
  }
  return li;
}

// ENCOUNTER-CHECK-01 (GM 2026-10-28: "before running a game, the GM can make sure the encounters are winnable"; "It's for
// the GM only. Players don't need to see it."; "We need characters only for the adventures"): Check the encounters
// fights each place's encounter a few times in the simulator (Mythastria tools/encounter_check.py) with the saved
// characters ticked in The party, and says per place: winnable, risky, deadly or not rated, with the win chance and risk.
const VERDICT = { winnable: 'Winnable', risky: 'Risky', deadly: 'Deadly', 'not rated': 'Not rated' };
let checkPoll = null;
function drawCheck(c) {
  for (const r of c.results) {
    const row = document.querySelector(`[data-check="${CSS.escape(r.scenario)}"]`);
    if (!row) continue;
    row.hidden = false;
    row.className = 'adv-check-row note check-' + r.verdict.replace(' ', '-');
    const odds = r.error ? `could not be fought: ${r.error}` : `won ${r.won} of ${r.runs} fights` +
      (r.lost ? `, lost ${r.lost}` : '') + (r.timeout ? `, ${r.timeout} not settled` : '') +
      ` · ${r.drops_per_run} characters dropped per fight` + (r.dead ? ` · ${r.dead} died` : '') +
      (r.avg_rounds != null ? ` · ${r.avg_rounds} rounds` : '') + (r.remix ? ' · with the saved Remix' : '');
    row.replaceChildren(el('strong', VERDICT[r.verdict] ?? r.verdict), ` — ${odds}`);
  }
  const who = c.party.join(', ');
  $('adv-check-status').textContent = c.status === 'running' ? `Checking ${c.done + 1} of ${c.of} with ${who}…`
    : c.status === 'failed' ? `The check stopped: ${c.error}`
    : `Checked ${c.of} encounters with ${who}: ${c.runs} simulated fights each, the party fresh. An estimate for your prep; Remix changes an encounter.` +
      (c.notes.length ? ' ' + c.notes.join('; ') + '.' : '');
}
$('adv-check').addEventListener('click', async () => {
  const sheets = dayParty().characters, pack = JSON.parse($('adv-end').dataset.packs || '[]')[0];
  if (!sheets.length) { $('adv-check-status').textContent = 'Tick the party\'s saved characters in The party first: the check fights with them.'; return; }
  $('adv-check').disabled = true;
  for (const row of document.querySelectorAll('[data-check]')) row.hidden = true;
  $('adv-check-status').textContent = 'Starting the check…';
  const out = await port.post('/api/adventures/check', { pack, characters: sheets }).catch(() => ({ ok: false, error: 'The simulator service stopped.' }));
  if (!out.ok) { $('adv-check').disabled = false; $('adv-check-status').textContent = out.error || out.refused || 'Refused.'; return; }
  drawCheck(out.check);
  clearInterval(checkPoll);
  checkPoll = setInterval(async () => {
    const s = await port.post('/api/adventures/check-status', { check: out.check.id }).catch(() => null);
    if (!s?.ok) { clearInterval(checkPoll); $('adv-check').disabled = false; $('adv-check-status').textContent = s?.error || 'The check was lost (Mythastria restarted?).'; return; }
    drawCheck(s.check);
    if (s.check.status !== 'running') { clearInterval(checkPoll); $('adv-check').disabled = false; }
  }, 2000);
});

async function drawHome(loaded) {
  $('adv-choose').hidden = true; $('adv-home').hidden = false; $('adv-links').hidden = false;
  const plans = [];
  for (const p of loaded) plans.push(await port.plan(p.id));
  const plan = plans[0];
  $('adv-name').textContent = plans.map(p => p.name).join(' + ');
  day.show(loaded[0].id);                                               // the first adventure's day (one is the usual)
  downtime.show(loaded[0].id);                                          // GM 2026-10-26: and its downtime
  $('adv-end').dataset.packs = JSON.stringify(loaded.map(p => p.id));
  $('adv-order').textContent = `${plan.places.length} places, in ${plan.order.charAt(0).toLowerCase() + plan.order.slice(1)}`;
  drawStory(plan.lore);
  const list = $('adv-places'); list.replaceChildren();
  let n = 0, isle = null;
  placeNames = {};
  for (const pl of plans.flatMap(p => p.places)) {
    placeNames[pl.scenario] = pl.title;
    if (pl.isle && pl.isle !== isle) {
      isle = pl.isle;
      list.append(el('li', pl.chapter ? `Chapter ${pl.chapter} · ${isle} · level ${pl.level}` : isle, 'adv-isle'));
    }
    list.append(placeItem(pl, ++n));
  }
  drawLinks();
}

// GM 2026-10-24: the pack's lore (mythastria-lore/1): premise and question, the chapters, the cast, the GM-only secrets
function drawStory(lore) {
  $('adv-story').hidden = !lore;
  if (!lore) return;
  const fold = (title, cls, open = false) => { const d = el('details', undefined, cls); d.open = open; d.append(el('summary', title)); return d; };
  const head = el('p', undefined, 'story-title'); head.append(el('strong', lore.title), el('span', ' · ' + (lore.levels || '')));
  const q = el('p', lore.question, 'story-question');
  const premise = (lore.premise || []).map(t => el('p', t));
  const chapters = fold('The chapters', 'story-fold');
  for (const ch of lore.chapters || []) {
    const box = el('div', undefined, 'story-chapter');
    box.append(el('h3', `Chapter ${ch.chapter}: ${ch.isle} (level ${ch.level})`));
    const dl = el('dl');
    for (const [k, label] of [['function', 'Function'], ['core_problem', 'Core problem'], ['revelation', 'Revelation'], ['route_key', 'Route-key'], ['moral_question', 'Moral question'], ['crossing', 'The crossing'], ['escape', 'The escape']])
      if (ch[k]) dl.append(el('dt', label), el('dd', ch[k]));
    box.append(dl); chapters.append(box);
  }
  const cast = fold('The cast', 'story-fold');
  const ul = el('ul', undefined, 'story-cast');
  for (const c of lore.cast || []) { const li = el('li'); li.append(el('strong', c.name), el('em', ' · ' + c.role), el('p', c.notes)); ul.append(li); }
  cast.append(ul);
  const secrets = fold('GM only: the secrets', 'story-fold story-secret');
  secrets.append(el('p', "Never on the players' screens before their chapter.", 'note'));
  for (const s of lore.secrets || []) { const box = el('div', undefined, 'story-chapter'); box.append(el('h3', `${s.name} (revealed: ${s.reveal})`), el('p', s.text)); secrets.append(box); }
  const tone = el('p', lore.tone || '', 'note');
  $('adv-story-body').replaceChildren(head, q, ...premise, tone, chapters, cast, secrets);
}

async function refresh() {
  const out = await port.state();
  packs = out.packs;
  for (const x of out.unavailable || []) status(`${x.id} can't be used: ${x.error}`, true);
  const loaded = packs.filter(p => p.loaded);
  if (loaded.length) await drawHome(loaded); else { placeNames = {}; drawChoose(); }
  const live = await port.live().catch(() => null);
  const fight = live?.ok && live.live && !live.live.done;
  $('adv-fight').hidden = !fight;
  if (fight) $('adv-fight-text').textContent = 'A fight is under way on ' + (placeNames[live.scenario?.source_scenario] || live.scenario?.source_scenario || 'a map') + '.';
  return loaded;
}

async function run(fn) {
  if (busy) return;
  busy = true; const buttons = [...document.querySelectorAll('button')]; buttons.forEach(b => b.disabled = true);
  try { await fn(); } catch (e) { status(e.message, true); }
  finally { busy = false; buttons.forEach(b => b.disabled = false); drawPartyLimits(); }
}

$('adv-start').addEventListener('click', () => run(async () => {
  const pick = document.querySelector('#adv-packs input:checked')?.value;
  if (!pick) return;
  status('Loading the adventure…');
  await port.load(pick); channel?.postMessage({ type: 'packs-changed' });
  keepParty(); await refresh();
  status('The adventure is loaded. Pick a place and press Fight here; it stays loaded when Mythastria restarts.');
}));

// GM 2026-10-24 ("End the Adventure ... needs to stop the fighting. A verification allows it to be continued or stopped and
// unloaded"; "Another option to freeze and make combat buttons inactive"): the GM chooses; the service stops or freezes the fight.
function askEnd(fight) {
  const d = $('end-dialog');
  $('end-text').textContent = (fight.running
    ? (fight.frozen ? 'A fight is running (frozen). ' : 'A fight is running. ') +
      (fight.frozen ? 'Keep it frozen, unfreeze it, ' : 'Keep playing, freeze it (nothing moves, its buttons wait), ') +
      'or stop it: the characters keep what they have left and the maps unload.'
    : 'Its maps leave Play live until you start it again.') + ' Saved remixes and notes stay.';
  $('end-freeze').hidden = !fight.running;
  $('end-freeze').textContent = fight.frozen ? 'Unfreeze the fight' : 'Freeze the fight';
  $('end-stop').textContent = fight.running ? 'Stop the fight and unload' : 'End and unload';
  d.returnValue = 'keep';
  d.querySelectorAll('button').forEach(b => { b.disabled = false; });   // the page is busy while the GM chooses
  return new Promise(resolve => { d.addEventListener('close', () => resolve(d.returnValue || 'keep'), { once: true }); d.showModal(); });
}

$('adv-end').addEventListener('click', () => run(async () => {
  const state = await port.state();
  const fight = { running: !!state.fight_running, frozen: !!state.fight_frozen };
  const choice = await askEnd(fight);
  if (choice === 'freeze') {
    await port.freeze(!fight.frozen);
    status(fight.frozen ? 'The fight goes on.' : 'The fight is frozen: nothing moves until you unfreeze it (here or on Play live). The adventure stays loaded.');
    return;
  }
  if (choice !== 'stop') return;
  let stop = fight.running;
  for (const id of JSON.parse($('adv-end').dataset.packs || '[]')) { await port.unload(id, stop); stop = false; }   // FLAVOR-01: the paint comes off
  channel?.postMessage({ type: 'packs-changed' });
  await refresh(); status((fight.running ? 'The fight is stopped and the' : 'The') + ' adventure is ended (unloaded). Choose one to play again.');
}));

addEventListener('DOMContentLoaded', async () => {
  let hello;
  try { hello = await port.hello(); } catch { status('This page needs Mythastria running: double-click Start_Mythastria.bat on the Desktop, then open http://127.0.0.1:8772/adventure.html', true); return; }
  members = hello.members || [];
  tableParty = await loadTableParty(port.post);                     // GM 2026-10-25: the table's party first
  drawParty(partyChoice(tableParty) ?? savedParty());
  if (!tableParty && savedParty()) {                                  // the party this browser kept joins the table once
    const out = await saveTableParty(port.post, party(), rosterAll()); if (out?.ok) tableParty = out.party;
  }
  $('adv-clear').addEventListener('click', clearParty);
  addEventListener('storage', e => { if (e.key === 'isles-character-roster-v1') { drawChars(); keepParty(); } });   // a sheet saved in another tab
  try {
    const loaded = await refresh();
    status(loaded.length ? 'The adventure is loaded. Pick a place and press Fight here.' : 'Choose an adventure, the party and its level, then press Start the adventure.');
  } catch (e) { status(e.message, true); }
});
