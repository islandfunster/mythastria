// 2026-10-20 (GM: Play live "looks good now, but difficult to use in 3d": the actions are too far away, targeting tokens
// and moving the character are hard). What the 3D view's own action bar, target list and pointer label say. Pure logic
// (no page): play-ui.mjs draws it; tests in tp_bar_tests.mjs. The simulator still checks every choice.
import { SPELL_KEY, reachPath } from './play-view.mjs';

const short = (text, n = 18) => (text.length > n ? text.slice(0, n - 1) + '…' : text);
export const BAR_KEYS = ['1', '2', '3', '4', '5', '6', '7', '8', '9', '0'];

/** The bar's buttons, in order: attacks, ready spells, other actions, End turn. Each item says what a click does:
 *  hold (an attack or a one-creature spell: then pick a target), cast (startCast), act (an action button), end. */
export function barItems(offers, actions = [], { held = null, casting = null } = {}) {
  if (!offers) return [];
  const items = [];
  for (const a of offers.attacks ?? [])
    items.push({ kind: 'hold', key: a.key, label: short(a.name), title: `${a.name}: then pick a target`,
      ready: a.targets.length > 0, why: a.targets.length ? '' : 'No legal target now', on: held === a.key });
  for (const s of offers.spells ?? []) {
    if (!s.ready) continue;
    const key = SPELL_KEY + s.name, one = s.shape === 'creature';
    items.push({ kind: one ? 'hold' : 'cast', key, spell: s, label: short(s.name), title: `${s.name} (spell)`, ready: !one || (s.targets?.length ?? 0) > 0,
      why: one && !s.targets?.length ? 'No legal target now' : '', on: held === key || casting?.name === s.name, spellLike: true });
  }
  for (const b of actions) items.push({ kind: 'act', button: b, label: short(b.label), title: b.why || b.label, ready: !!b.ready, why: b.why ?? '', on: !!b.pick && held === b.pick });
  items.push({ kind: 'end', label: 'End turn', title: 'End the turn', ready: true, why: '', on: false });
  return items.map((it, i) => ({ ...it, hotkey: i < BAR_KEYS.length ? BAR_KEYS[i] : null }));
}

const feetBetween = (a, b) => Math.max(Math.abs(a[0] - b[0]), Math.abs(a[1] - b[1])) * 5;

/** Who the held attack, spell or action can go to now: the legal targets only (never a creature the party cannot see,
 *  so the list gives nothing away), nearest first, and how many more are refused. look(c) -> {cls, reason}. */
export function targetList(combatants, look, me) {
  const legal = [], refused = [];
  for (const c of combatants ?? []) {
    if (c.down) continue;
    const l = look(c);
    if (!l || l.cls === 'self') continue;
    if (l.cls === 'legal-foe' || l.cls === 'legal-ally') legal.push({ id: c.id, name: c.name, ally: l.cls === 'legal-ally', feet: me ? feetBetween(me, [c.x, c.y]) : null });
    else refused.push(c.id);
  }
  legal.sort((a, b) => (a.feet ?? 0) - (b.feet ?? 0) || a.name.localeCompare(b.name));
  return { legal, refused: refused.length };
}

/** The label beside the pointer on a creature: its name, and with something held whether it is a legal target. */
export function creatureTip(c, look) {
  if (!c) return null;
  const l = look ? look(c) : null;
  if (!l || l.cls === 'self') return { text: c.name, cls: 'plain' };
  if (l.cls === 'refused') return { text: `${c.name}: ${l.reason || 'not a legal target'}`, cls: 'refused' };
  return { text: `${c.name}: click to target`, cls: 'legal' };
}

/** The label beside the pointer on a square on your turn: the move's cost, or why it is out of reach. */
export function squareTip(offers, x, y, start) {
  if (!offers || x == null) return null;
  if (start && x === start[0] && y === start[1]) return null;
  const r = reachPath(offers, x, y, start);
  if (r) return { text: `Move here · ${r.feet} ft`, cls: 'legal', ok: true, path: r.path };
  return { text: `Out of reach (${offers.movement} ft of movement left)`, cls: 'refused', ok: false, path: null };
}

/** The reach area's edge, in the 3D view's coordinates (a square's centre on its integer x, y): segments [x1,z1,x2,z2]. */
export function reachEdge3D(reach) {
  const inside = new Set((reach ?? []).map(r => `${r[0]},${r[1]}`)), out = [];
  for (const r of reach ?? []) {
    const [x, y] = r;
    if (!inside.has(`${x},${y - 1}`)) out.push([x - .5, y - .5, x + .5, y - .5]);
    if (!inside.has(`${x},${y + 1}`)) out.push([x - .5, y + .5, x + .5, y + .5]);
    if (!inside.has(`${x - 1},${y}`)) out.push([x - .5, y - .5, x - .5, y + .5]);
    if (!inside.has(`${x + 1},${y}`)) out.push([x + .5, y - .5, x + .5, y + .5]);
  }
  return out;
}
