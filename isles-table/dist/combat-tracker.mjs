// COMBAT-TRACKER-01 (GM 2026-10-27: "We need a combat tracker"; asked, chose: on the GM's Play live and on every
// player's screen, a player seeing the party and only the creatures the party sees now; a creature's health in words
// for players, exact Hit Points and AC for the GM; a click on a row highlights its token or, while an attack or a spell
// is aimed, picks that creature as its target; an action dragged onto a row targets that creature).
// The engine sends the order (snapshot.tracker, sim/combat_tracker.py: initiative, then initiative bonus, then name),
// who acts now and each Concentration; the players' door has already cut it to what the seat sees. This module only
// arranges it: it decides nothing.
import { asset } from './server.mjs';   // PLAYER-SITE-01: pictures from the GM's PC

// SRD 5.2.1 Rules Glossary, Bloodied: a creature with half its Hit Points or fewer.
export function healthWords(c) {
  if (c.dead) return 'dead';
  if (c.down) return c.stable ? 'down, stable' : 'down';
  if (c.health) return c.health;                                   // a seat: the players' door sends only the word
  const hp = Math.max(0, c.hp ?? 0), top = Math.max(1, c.hp_max ?? 1);
  return hp >= top ? 'unhurt' : hp * 2 <= top ? 'Bloodied' : 'hurt';
}

// GM 2026-10-27 ("on players' screens show a creature's health on the map (hover text and bar) in words too, like the
// tracker"): a token's bar and hover text. The party, and every token on the GM's screen, keep exact Hit Points; a
// creature on a player's screen gets a word and a bar in bands (unhurt full, hurt half, Bloodied a quarter, down none).
const BAND = { unhurt: 1, hurt: .5, Bloodied: .25 };
export function mapHealth(c, player = false) {
  if (!player || c.pc) return { frac: c.hp_max ? Math.max(0, c.hp) / c.hp_max : 0, text: `${c.hp}/${c.hp_max} HP, AC ${c.ac}` };
  const word = healthWords(c);
  return { frac: BAND[word] ?? 0, text: word };
}

const SIDE = { friend: 'ally', foe: 'foe', neutral: 'out of the fight' };

// GM 2026-10-27 ("the combat tracker and creatures to indicate their disposition Friendly - Green, Neutral - Yellow,
// Hostile - Red ... changeable by the DM on the combat tracker"; "Go by the engine"): the engine's attitude of each
// creature (sim/attitude.py: SRD 5.2.1 Friendly, Indifferent, Hostile; a player gets those of the creatures it sees).
export const ATTITUDE_COLOUR = { Friendly: '#6cc070', Indifferent: '#e0c050', Hostile: '#e05a4a' };
export function attitudes(snap) {
  return new Map((snap?.scene?.creatures ?? []).map(e => [e.id, e.attitude]));
}
export function attitudeColour(snap, c) {
  return c && !c.pc ? ATTITUDE_COLOUR[attitudes(snap).get(c.id)] ?? null : null;
}

// One row per combatant in turn order. `player`: a seat's screen (creatures' health in words, no AC but the party's).
export function trackerRows(snap, combatants, { player = false } = {}) {
  const tracker = snap?.tracker;
  if (!tracker || tracker.scene) return [];
  const byId = new Map((combatants ?? []).map(c => [c.id, c]));
  const conc = tracker.concentration ?? {}, att = attitudes(snap), sight = tracker.sight ?? {};
  return (tracker.order ?? []).filter(r => byId.has(r.id)).map(r => {
    const c = byId.get(r.id), party = !!c.pc, exact = !player || party;
    const saves = c.down && !c.dead && !c.stable && c.death_saves && (c.death_saves.successes || c.death_saves.failures)
      ? `death saves ${c.death_saves.successes} ✓ ${c.death_saves.failures} ✗` : '';
    const health = exact ? (c.dead ? 'dead' : c.down ? (c.stable ? 'down, stable' : 'down') : `${c.hp}/${c.hp_max} HP${c.temp_hp ? ' +' + c.temp_hp : ''}`) : healthWords(c);
    const bits = [health, exact && c.ac != null ? `AC ${c.ac}` + (c.ac_why?.length ? ` (${c.ac_why.join(', ')})` : '') : '', saves,   // AC-SHOWN-01 ...(c.conditions ?? []),
      conc[r.id] ? `Concentrating: ${conc[r.id]}` : ''].filter(Boolean);
    return { id: r.id, name: c.name, init: r.init, kind: party ? 'party' : SIDE[c.side] ?? 'foe', acting: tracker.acting === r.id,
      down: !!c.down || !!c.dead, text: bits.join(' · '), token: c.token_path ?? '',
      attitude: party ? null : att.get(r.id) ?? null,
      // SIGHT-01 (the GM's tracker): which characters see this creature now
      seenBy: player || party ? null : Object.entries(sight).filter(([, ids]) => ids.includes(r.id)).map(([p]) => byId.get(p)?.name ?? p) };
  });
}

export function trackerTitle(snap, combatants) {
  const t = snap?.tracker;
  if (!t) return '';
  if (t.scene) return 'No initiative: a scene. Each character acts when its player chooses.';
  if (snap.done) return 'The fight is over.';
  const who = (combatants ?? []).find(c => c.id === t.acting);
  return [t.round ? `Round ${t.round}` : '', who ? `${who.name} acts` : 'The creatures are acting'].filter(Boolean).join(' · ');
}

// The GM console follows the creatures' turns too: the tracker moved when another creature acts or a round begins.
export function trackerMoved(before, after) {
  return (before?.acting ?? null) !== (after?.acting ?? null) || (before?.round ?? null) !== (after?.round ?? null);
}

// The panel. Each row carries data-actor, so a card dragged from the sheet and dropped on it targets that creature
// (play-ui.mjs dropOn, the same path as a token on the map); a click calls onRow(id).
export function drawTracker(root, rows, { title = '', marked = null, onRow = () => {}, look = () => ({ cls: '', reason: '' }),
  onAttitude = null, onSight = null } = {}) {
  const head = document.createElement('p');
  head.className = 'tracker-title';
  head.textContent = title;
  const list = document.createElement('ol');
  list.className = 'tracker';
  for (const r of rows) {
    const li = document.createElement('li'), l = look(r.id);
    li.className = ['tracker-row', r.kind.replace(/ /g, '-'), r.acting ? 'acting' : '', r.down ? 'down' : '', r.id === marked ? 'marked' : '', l.cls].filter(Boolean).join(' ');
    li.dataset.actor = r.id;
    li.tabIndex = 0;
    li.title = [`${r.name} (${r.kind})`, l.reason].filter(Boolean).join(' · ');
    const init = document.createElement('span'); init.className = 'tracker-init'; init.textContent = r.init ?? '';
    const pic = document.createElement('span'); pic.className = 'tracker-pic';
    if (r.token) { const im = document.createElement('img'); im.src = asset(r.token); im.alt = ''; pic.append(im); }
    const name = document.createElement('span'); name.className = 'tracker-name'; name.textContent = (r.acting ? '▸ ' : '') + r.name;
    const sub = document.createElement('span'); sub.className = 'tracker-sub'; sub.textContent = r.text;
    const body = document.createElement('span'); body.className = 'tracker-body'; body.append(name, sub);
    if (r.seenBy) {
      const seen = document.createElement('span'); seen.className = 'tracker-sub tracker-seen';
      seen.textContent = r.seenBy.length ? `seen by ${r.seenBy.join(', ')}` : 'seen by no one';
      body.append(seen);
    }
    if (r.attitude) {                                               // the colour; the GM may change it here
      li.style.setProperty('--disposition', ATTITUDE_COLOUR[r.attitude] ?? 'transparent');
      li.classList.add('has-disposition');
      if (onAttitude && !r.down) {
        const pick = document.createElement('select'); pick.className = 'tracker-attitude'; pick.title = "Disposition (the engine's attitude)";
        for (const a of Object.keys(ATTITUDE_COLOUR)) pick.append(new Option(a, a, false, a === r.attitude));
        pick.addEventListener('click', e => e.stopPropagation());
        pick.addEventListener('change', () => onAttitude(r.id, pick.value));
        body.append(pick);
      } else {
        const word = document.createElement('span'); word.className = 'tracker-sub tracker-attitude-word'; word.textContent = r.attitude;
        body.append(word);
      }
    }
    li.append(init, pic, body);
    li.addEventListener('click', () => onRow(r.id));
    li.addEventListener('keydown', e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onRow(r.id); } });
    list.append(li);
  }
  const extra = [];
  if (onSight) { const b = document.createElement('button'); b.className = 'quiet'; b.textContent = 'Who sees whom…';
    b.title = "Which creatures each character sees (the engine's sight, changed where you pick)"; b.addEventListener('click', onSight); extra.push(b); }
  root.replaceChildren(head, ...(rows.length ? [list] : []), ...extra);
}

// SIGHT-01 (GM 2026-10-27: "when the combat tracker is launched, the DM must select which creatures can be seen
// according to each player's vision by each player"): the grid of standing characters by creatures, ticked from each
// character's sight now (the engine's: light, darkvision, blindness, walls; then the GM's picks). Confirm sends every
// box; the engine keeps a pick until its own answer for that pair changes.
export function sightGrid(snap, combatants) {
  const t = snap?.tracker, cs = combatants ?? [];
  if (!t || t.scene || !t.sight) return null;
  const pcs = cs.filter(c => c.pc && t.sight[c.id]);
  const creatures = cs.filter(c => !c.pc && !c.down);
  return { pcs, creatures, ticked: new Set(pcs.flatMap(p => (t.sight[p.id] ?? []).map(o => p.id + '|' + o))),
           engine: new Set(pcs.flatMap(p => (t.sight_engine?.[p.id] ?? []).map(o => p.id + '|' + o))) };
}
export function sightPicks(grid, ticked) {
  return Object.fromEntries(grid.pcs.map(p => [p.id, Object.fromEntries(grid.creatures.map(o => [o.id, ticked.has(p.id + '|' + o.id)]))]));
}
export function drawSightGrid(root, grid, ticked) {
  const table = document.createElement('table'); table.className = 'sight-grid';
  const head = table.createTHead().insertRow();
  head.append(document.createElement('th'));
  for (const p of grid.pcs) { const th = document.createElement('th'); th.textContent = p.name; head.append(th); }
  const body = table.createTBody();
  for (const o of grid.creatures) {
    const tr = body.insertRow(), th = document.createElement('th'); th.textContent = o.name; tr.append(th);
    for (const p of grid.pcs) {
      const key = p.id + '|' + o.id, td = tr.insertCell(), cb = document.createElement('input');
      cb.type = 'checkbox'; cb.checked = ticked.has(key);
      cb.title = `${p.name} sees ${o.name}` + (grid.engine.has(key) ? ' (the engine: yes)' : ' (the engine: no)');
      cb.setAttribute('aria-label', cb.title);
      cb.addEventListener('change', () => { if (cb.checked) ticked.add(key); else ticked.delete(key); td.classList.toggle('picked', grid.engine.has(key) !== ticked.has(key)); });
      td.append(cb);
      if (grid.engine.has(key) !== ticked.has(key)) td.classList.add('picked');
    }
  }
  root.replaceChildren(table);
}
