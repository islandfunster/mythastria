// HINTS-01 step H2 (GM 2026-10-22: "I liked the idea of suggested turns, but not sure if they can be reassuring to
// experienced players"; then "Hints are opt-in"): the turn reminders on screen. The simulator builds them from its own
// checks (Mythastria sim/live_hints.py: offers.hints) and sends them only to the seat that plays the acting character
// at the Reminders level; this module only shows them. Quiet: one line by End turn, a warning on a Concentration
// spell's card, each kind mutable. No pop-ups, no sounds, never a choice made for anyone.
// Levels: Off (every seat and character starts here) / Reminders. The phone's level is kept with its seat (the service)
// and in this browser; the GM console keeps one per character in this browser (hotseat).
export const HINT_KINDS = { action: 'Action unused', bonus: 'Bonus Action free', movement: 'Movement left',
  slot: 'One spell slot a turn', resources: 'Resources free', concentration: 'Concentration warning',
  sneak: 'Sneak Attack unused', attack: 'Advantage and Disadvantage', reach: "Foes' reach", area: 'Who is inside' };
export const HINT_LEVELS = { off: 'Off', reminders: 'Reminders' };
const CONSOLE_KEY = 'mythastria-hints-console', SEAT_KEY = 'mythastria-hints-seat', MUTE_KEY = 'mythastria-hints-mute';

const read = (key, fallback, storage = globalThis.localStorage) => {
  try { return JSON.parse(storage?.getItem(key) ?? 'null') ?? fallback; } catch { return fallback; }
};
const write = (key, value, storage = globalThis.localStorage) => { try { storage?.setItem(key, JSON.stringify(value)); } catch {} };
const level = v => v in HINT_LEVELS ? v : 'off';

// The GM console: a level per character, Off until someone turns it on for that character.
export const consoleLevel = (name, storage) => level(read(CONSOLE_KEY, {}, storage)[name]);
export function setConsoleLevel(name, value, storage) {
  const all = read(CONSOLE_KEY, {}, storage);
  all[name] = level(value);
  write(CONSOLE_KEY, all, storage);
}
// A phone: the level this browser chose for its seat (null when never chosen here).
export const seatLevel = storage => { const v = read(SEAT_KEY, null, storage); return v in HINT_LEVELS ? v : null; };
export const setSeatLevel = (value, storage) => write(SEAT_KEY, level(value), storage);
export const mutedKinds = storage => new Set(read(MUTE_KEY, [], storage).filter(k => k in HINT_KINDS));
export function setMuted(kind, on, storage) {
  const m = mutedKinds(storage);
  if (on) m.add(kind); else m.delete(kind);
  write(MUTE_KEY, [...m], storage);
}

// What the End turn line shows: the reminders that apply now, minus the muted kinds ([] at Off).
export const hintLine = (offers, lvl, muted = new Set()) =>
  lvl === 'reminders' ? (offers?.hints?.line ?? []).filter(h => !muted.has(h.kind)) : [];
// The warning on one spell's card ('' at Off, muted, or when none applies).
export const spellWarning = (offers, spell, lvl, muted = new Set()) =>
  lvl === 'reminders' ? (offers?.hints?.spells?.[spell] ?? []).filter(h => !muted.has(h.kind)).map(h => h.text).join(' ') : '';

// H4-H6 facts, shown while pointing (the simulator's offers.hints.attacks / .reach and /api/live/aim): [{kind, text}].
// Never a chance to hit or an Armor Class (GM 2026-10-29: Advantage and Disadvantage and why only).
const nameOf = (cs, id) => cs?.find(c => c.id === id)?.name ?? null;
const listed = names => names.length < 2 ? names.join('') : `${names.slice(0, -1).join(', ')} and ${names.at(-1)}`;
// An attack held over a target: its Advantage or Disadvantage, and Sneak Attack
export function attackFacts(offers, key, target, lvl, muted = new Set()) {
  if (lvl !== 'reminders') return [];
  const f = offers?.hints?.attacks?.[key]?.[target];
  return [f?.text && { kind: 'attack', text: f.text }, f?.sneak && { kind: 'sneak', text: f.sneak }]
    .filter(h => h && !muted.has(h.kind));
}
// A move's destination: the foes whose reach it is in, and who may make an Opportunity Attack on the way
export function reachFacts(offers, x, y, cs, lvl, muted = new Set()) {
  if (lvl !== 'reminders' || muted.has('reach')) return [];
  const r = offers?.hints?.reach, sq = r?.squares?.[`${x},${y}`];
  if (!sq) return [];
  const near = sq.near.map(id => nameOf(cs, id) && `${nameOf(cs, id)} (${r.foes[id]} ft)`).filter(Boolean);
  const oa = sq.oa.map(id => nameOf(cs, id)).filter(Boolean);
  return [near.length && { kind: 'reach', text: `In reach of: ${near.join(', ')}.` },
    oa.length && { kind: 'reach', text: `${listed(oa)} may make an Opportunity Attack on this path (Disengage prevents it).` }].filter(Boolean);
}
// An area aimed: who is inside, foes and allies apart (aim: /api/live/aim's answer)
export function areaFacts(aim, side, cs, lvl, muted = new Set()) {
  if (lvl !== 'reminders' || muted.has('area') || !aim) return [];
  const who = ids => ids.map(id => cs?.find(c => c.id === id)).filter(Boolean);
  const inside = who(aim.inside), spared = who(aim.spared ?? []);
  const foes = inside.filter(c => c.side !== side).map(c => c.name), allies = inside.filter(c => c.side === side).map(c => c.name);
  const parts = [foes.length && `${foes.join(', ')} (${foes.length === 1 ? 'foe' : 'foes'})`,
    allies.length && `${allies.join(', ')} (${allies.length === 1 ? 'ally' : 'allies'})`].filter(Boolean);
  const text = parts.length ? `Inside: ${parts.join('; ')}.` : 'Inside: no creature.';
  return [{ kind: 'area', text: spared.length ? `${text} Spared (${aim.why ?? 'its caster'}): ${spared.map(c => c.name).join(', ')}.` : text }];
}
// The fact line: each fact with a one-tap mute, as the End turn line
export const drawFacts = (box, items, mute) => drawLine(box, items, mute);

const el = (tag, cls, text) => { const e = document.createElement(tag); if (cls) e.className = cls; if (text !== undefined) e.textContent = String(text); return e; };

// H3 (GM 2026-10-28): the lower of two levels (the GM's table cap and a seat's limit only ever lower a level)
export const lowerLevel = (a, b) => (Object.keys(HINT_LEVELS).indexOf(a) <= Object.keys(HINT_LEVELS).indexOf(b) ? a : b);

// The Hints switch (Off / Reminders) and the mutes, in `box`. change(level) and mute(kind, on) save and redraw.
// max: the highest level the GM allows here (H3: the table cap, a seat's limit); the levels above it are greyed out.
export function drawSwitch(box, { lvl, muted, change, mute, label = 'Hints', max = 'reminders' }) {
  const pick = el('select'); pick.setAttribute('aria-label', 'Turn hints');
  pick.title = 'Turn reminders on your own screen only: an unused Action or Bonus Action, movement left, a spell that ends your Concentration. Off until you turn them on.';
  const keys = Object.keys(HINT_LEVELS);
  for (const [v, text] of Object.entries(HINT_LEVELS)) {
    const over = keys.indexOf(v) > keys.indexOf(max);
    pick.append(Object.assign(el('option', '', over ? `${text} (the GM has turned hints off)` : text), { value: v, selected: v === lvl, disabled: over }));
  }
  if (max === 'off') pick.title = 'The GM has turned hints off.';
  pick.addEventListener('change', () => change(pick.value));
  const parts = [el('span', 'hints-label', label), pick];
  if (lvl === 'reminders') {
    const more = el('details', 'hints-mute'), sum = el('summary', '', muted.size ? `Muted ${muted.size}` : 'Mute…');
    more.open = !!box.querySelector('details.hints-mute')?.open;    // stays open while kinds are ticked
    sum.title = 'Mute a kind of reminder';
    const list = el('div', 'hints-mute-box');
    for (const [kind, text] of Object.entries(HINT_KINDS)) {
      const box = Object.assign(el('input'), { type: 'checkbox', checked: muted.has(kind) });
      box.addEventListener('change', () => mute(kind, box.checked));
      const row = el('label'); row.append(box, ' ' + text); list.append(row);
    }
    more.append(sum, list); parts.push(more);
  }
  box.replaceChildren(...parts);
}

// The quiet line by End turn: each reminder with a one-tap mute.
export function drawLine(box, items, mute) {
  box.replaceChildren(...items.flatMap((h, i) => {
    const x = el('button', 'hints-x', '×'); x.type = 'button';
    x.title = h.kind in HINT_KINDS ? `Mute "${HINT_KINDS[h.kind]}" reminders (Hints, Muted brings them back)` : 'Hide this note';
    x.setAttribute('aria-label', x.title);
    x.addEventListener('click', () => mute(h.kind, true));
    const item = el('span', 'hints-item'); item.append(el('span', '', h.text), x);
    return i ? [el('span', 'hints-sep', ' · '), item] : [item];
  }));
  box.hidden = !items.length;
}
