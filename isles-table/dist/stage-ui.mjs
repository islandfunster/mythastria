// The Stage page (STAGE-01): seats, the ON AIR banner with a running clock, the player and Director controls and the
// public Stage log. Every change goes to the simulator service, which applies the Stage rules and answers with the
// seat's view; the page polls that view so other tabs and seats stay current. See stage-view.mjs.
import { cue, tableNames, createStagePort } from './stage-view.mjs';
import { createLivePort } from './play-view.mjs';
import { mountScene, attitudeLine } from './scene-ui.mjs';          // GM 2026-10-24: attitudes (sim/attitude.py)
import { mountPillar } from './pillar-ui.mjs';                       // GM 2026-10-26: the social scene (sim/scenes.py)
import { loadSeat } from './seat-ticket.mjs';                        // GM 2026-10-28: The Stage in the player client

const $ = id => document.getElementById(id);
const el = (tag, cls, text) => { const e = document.createElement(tag); if (cls) e.className = cls; if (text !== undefined) e.textContent = String(text); return e; };
const SEATS_KEY = 'isles-stage-seats';

let port = null, view = null, fetchedAt = 0, seats = [];
// GM 2026-10-28 ("the client side also needs The Stage"): on the players' door the seat is the player's own (the door
// takes it from the seat ticket whatever the page sends); no seat picker, no Director controls
let playerSeat = null;
// GM 2026-10-26 (goal 14): a social scene plays here: the creatures present with their attitudes, Influence and other
// checks with no turns; the GM's attitude controls and scene choices. The live encounter is Play live's (one at a time).
let live = null, liveSnap = null, liveLog = [], liveSince = 0, attUi = null, pillarGm = null, pillarPlayer = null, lastSeat = '';

function loadSeats() {
  try { const s = JSON.parse(localStorage.getItem(SEATS_KEY) || '[]'); return Array.isArray(s) ? s.filter(n => typeof n === 'string') : []; }
  catch { return []; }
}
function saveSeats() { try { localStorage.setItem(SEATS_KEY, JSON.stringify(seats)); } catch { /* private window: seats last this visit */ } }

const seat = () => $('seat').value;
function say(text, isError = false) { const n = $('said'); n.textContent = text || ''; n.className = isError ? 'error' : ''; }

function fillSeats() {
  const keep = seat() || 'GM', sel = $('seat');
  if (playerSeat) { sel.replaceChildren(new Option(playerSeat, playerSeat)); return; }
  sel.replaceChildren(new Option('GM (Director)', 'GM'));
  for (const n of tableNames(view, seats)) sel.append(new Option(n, n));
  sel.value = [...sel.options].some(o => o.value === keep) ? keep : 'GM';
}

function fillNames(selectId) {
  const sel = $(selectId), keep = sel.value, me = seat();
  sel.replaceChildren(...tableNames(view, seats).filter(n => selectId !== 'applaud-to' || n !== me).map(n => new Option(n, n)));
  if ([...sel.options].some(o => o.value === keep)) sel.value = keep;
}

function draw() {
  if (!view) return;
  fillSeats(); fillNames('applaud-to'); fillNames('spot-to');
  const me = seat(), director = me === 'GM';
  $('player').hidden = director;
  $('director').hidden = !director;
  const mine = (view.participants || []).find(p => p.name.toLowerCase() === me.toLowerCase());
  $('join').disabled = !!mine?.stage;
  $('leave').disabled = !mine?.stage;
  const holder = view.holder && view.holder.toLowerCase() === me.toLowerCase();
  $('discuss').hidden = !holder;
  $('discuss').textContent = view.discussion ? 'End Dialogue' : 'Dialogue';
  $('pause').hidden = !(view.holder && view.running);
  $('resume').hidden = !(view.holder && !view.running);
  $('stop').disabled = !view.holder;
  $('roster').replaceChildren(...(view.participants || []).map(p =>
    el('li', p.stage ? 'in' : 'out', `${p.name}${p.stage ? ' · on the Stage' : ' · regular player'}`)));
  if (!view.participants?.length) $('roster').append(el('li', 'out', 'No one has joined yet.'));
  $('log').replaceChildren(...(view.log || []).slice().reverse().map(e => el('li', e.text.startsWith('Applause') ? 'applause' : '', e.text)));
  $('report').hidden = !director;
  $('report').textContent = view.time_report || '';
  tick();
}

function tick() {
  const c = cue(view, fetchedAt, Date.now()), b = $('banner');
  b.className = c ? (c.discussion ? 'banner discussion' : 'banner onair') : 'banner idle';
  $('banner-label').textContent = c ? c.label : 'THE STAGE';
  $('banner-line').textContent = c ? c.line : 'No one holds the spotlight.';
  $('banner-time').textContent = c ? c.time : '';
}

function take(out) {
  if (out?.stage) { view = out.stage; fetchedAt = Date.now(); draw(); }
}

async function refresh() {
  if (!port) return;
  const out = await port.state(seat() || 'GM').catch(() => ({ ok: false, error: 'The simulator service stopped.' }));
  if (out.ok) take(out); else say(out.error, true);
}

async function send(cmd) {
  const out = await port.command(seat(), cmd).catch(() => ({ ok: false, error: 'The simulator service stopped.' }));
  take(out);
  if (out.private) say(out.private, !out.ok);
  else if (out.ok === false) say(out.error || 'Refused.', true);
  else say('');
}

function addSeat() {
  const name = $('new-seat').value.trim();
  if (!/^[A-Za-z0-9][A-Za-z0-9 '\-]{0,39}$/.test(name) || name === 'GM') { say('A name: letters, digits, spaces, \' and - (up to 40).', true); return; }
  if (!seats.some(s => s.toLowerCase() === name.toLowerCase())) { seats.push(name); saveSeats(); }
  $('new-seat').value = '';
  draw();
  $('seat').value = tableNames(view, seats).find(n => n.toLowerCase() === name.toLowerCase()) || 'GM';
  refresh();
}

function liveTake(out) {
  if (!out?.live) return;
  liveSnap = out.live;
  for (const e of liveSnap.log ?? []) if (e.n > liveSince) { liveLog.push(e); liveSince = e.n; }
  liveLog = liveLog.slice(-60);
  drawLive();
}
function liveResult(text) { if (text) say(text, true); }
function drawLive() {
  const s = liveSnap, gm = seat() === 'GM';
  $('scene-live').hidden = !s?.pillar || s.done;
  if ($('scene-live').hidden) return;
  if (lastSeat !== seat()) { $('pillar-stage').dataset.key = ''; $('att-panel').dataset.key = ''; lastSeat = seat(); }
  pillarGm ??= mountPillar({ panel: $('pillar-stage'), body: $('pillar-stage'), port: live, take: liveTake, result: liveResult, gm: true, stage: true });
  pillarPlayer ??= mountPillar({ panel: $('pillar-stage'), body: $('pillar-stage'), port: live, take: liveTake, result: liveResult, gm: false, stage: true,
    mine: () => $('inf-who').value || null });
  (gm ? pillarGm : pillarPlayer).draw(s);
  if (gm) {                                                          // the GM's attitude controls (the Play live panel)
    attUi ??= mountScene({ panel: $('att-panel'), body: $('att-stage'), port: live, take: liveTake, result: liveResult, gm: true });
    attUi.draw(s);
  } else {
    $('att-panel').hidden = false; $('att-panel').dataset.key = '';
    const ul = el('ul', 'att-list');
    for (const c of s.scene?.creatures ?? []) {
      const li = el('li', 'att-' + c.attitude.toLowerCase());
      li.append(el('span', '', c.name), el('span', 'att-badge', attitudeLine(c))); ul.append(li);
    }
    $('att-stage').replaceChildren(el('p', 'note', 'Present, as your characters can tell:'), ul);
  }
  const fill = (sel, list) => {
    const keep = sel.value;
    sel.replaceChildren(...list.map(c => new Option(c.name, c.id)));
    if (list.some(c => c.id === keep)) sel.value = keep;
  };
  const people = (s.state?.combatants ?? []).filter(c => !c.down && !c.dead);
  fill($('inf-who'), people.filter(c => c.pc));
  fill($('inf-target'), (s.scene?.creatures ?? []).filter(c => people.some(p => p.id === c.id)));
  $('influence-box').hidden = s.pillar.mode === 'fight' || !!s.social_off;   // GM 2026-11-01: the GM's switch
  $('scene-log').replaceChildren(...liveLog.filter(e => ['dice', 'scene'].includes(e.kind) && !e.text.startsWith('Morale (for the GM)') || (e.kind === 'turn' && /finds|Scene:/.test(e.text)))
    .slice(-10).reverse().map(e => el('li', '', e.text)));
}
async function refreshLive() {
  if (!live) return;
  const out = await live.state(liveSince).catch(() => null);
  if (out?.ok) liveTake(out); else { liveSnap = null; drawLive(); }
}
async function influence() {
  const s = liveSnap;
  if (!s) return;
  if (!$('inf-who').value || !$('inf-target').value) { say('Choose who urges whom.', true); return; }
  const urge = $('inf-urge').value.trim();                      // GM 2026-11-01: it goes to the GM to rule
  const out = await live.act({ op: 'influence', actor: $('inf-who').value, target: $('inf-target').value, mode: $('inf-mode').value,
    ...(urge ? { urge } : {}), fight_id: s.fight_id, revision: s.revision, since: liveSince }).catch(() => ({ ok: false, error: 'The simulator service stopped.' }));
  liveTake(out);
  if (!out.ok) say(out.refused || out.error || 'Refused.', true);
  else { say('Sent to the GM, who rules what happens.'); $('inf-urge').value = ''; }
}

async function start() {
  seats = loadSeats();
  port = createStagePort();
  let hello;
  try { hello = await port.hello(); } catch { hello = null; }
  if (!hello?.ok) {
    $('offline').hidden = false;
    $('table').hidden = true;
    return;
  }
  if (hello.door === 'players') {                                   // the player client: this seat only
    const mine = loadSeat();
    if (!mine?.name) { location.href = 'join.html'; return; }
    playerSeat = mine.name;
    document.querySelector('.toolbar').hidden = true;
    $('how-seat').hidden = true;                                    // no seats to pick here
  }
  $('seat').addEventListener('change', () => { say(''); draw(); refresh(); });     // the seat's controls at once, then its view
  $('add-seat').addEventListener('click', addSeat);
  $('new-seat').addEventListener('keydown', e => { if (e.key === 'Enter') addSeat(); });
  $('join').addEventListener('click', () => send({ op: 'join' }));
  $('leave').addEventListener('click', () => send({ op: 'leave' }));
  $('discuss').addEventListener('click', () => send({ op: 'discuss', on: !view.discussion, revision: view.revision }));
  $('applaud').addEventListener('click', () => {
    if (!$('applaud-to').value) { say('Choose who to applaud.', true); return; }
    send({ op: 'applaud', to: $('applaud-to').value, reason: $('applaud-why').value.trim() });
    $('applaud-why').value = '';
  });
  $('spotlight').addEventListener('click', () => {
    if (!$('spot-to').value) { say('Add the players first (Seats).', true); return; }
    send({ op: 'spotlight', to: $('spot-to').value });
  });
  for (const op of ['pause', 'resume', 'stop', 'newsession']) $(op).addEventListener('click', () => send({ op }));
  await refresh();
  setInterval(tick, 1000);
  setInterval(refresh, 2000);
  live = createLivePort();                                           // GM 2026-10-26: the live scene, if one is on
  await live.hello().catch(() => null);
  $('inf-go').addEventListener('click', influence);
  $('seat').addEventListener('change', drawLive);
  await refreshLive();
  setInterval(refreshLive, 2000);
}

start();
