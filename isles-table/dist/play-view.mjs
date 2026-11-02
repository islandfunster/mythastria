// LIVE-PLAY-01 (GM 2026-10-19: attacks dragged from a character sheet onto a token, the action checked against the SRD;
// "Use the simulator: let players choose actions in a live fight, starting with weapon attacks ..., then spells").
// What the Play live page shows, from the simulator service's live fight (Mythastria sim/live_play.py). The
// simulator offers the legal targets and checks every choice again when it arrives; this module only arranges its
// answers for the page and decides nothing.
import { SERVER } from './server.mjs';                         // PLAYER-SITE-01: the GM's Mythastria
import { parseRecording, buildFrames } from './replay.mjs';
import { seatPart, seatNotice } from './seat-ticket.mjs';     // JOIN-01; BETA-B: the seat-closed notice

// The map view for one live snapshot: the replay adapter's own view (token art from the Rust registry, walls, doors).
export function liveView(scenario, snapshot, registry = null) {
  if (!scenario || !snapshot?.state) return null;
  const rec = parseRecording([scenario, snapshot.state]);
  return buildFrames(rec, registry)[0].view;
}

// How a token looks while an attack card is held: a legal foe, a legal ally (the SRD allows it; the page warns), or
// refused with the simulator's reason. The acting character itself is never a target.
export function targetLook(offers, key, combatant) {
  const a = offers?.attacks?.find(x => x.key === key);
  if (!a || combatant.id === offers.actor) return { cls: 'self', reason: '' };
  if (a.targets.includes(combatant.id)) {
    const ally = combatant.side === offers.side;
    return { cls: ally ? 'legal-ally' : 'legal-foe', reason: ally ? `${combatant.name} is on your side` : '' };
  }
  return { cls: 'refused', reason: a.refused?.[combatant.id] ?? 'Not a legal target.' };
}

// The sheet card for one attack: "Greatsword · +5 · 2d6+3 slashing · reach 5 ft".
export function cardText(a) {
  const range = a.ranged ? `range ${a.reach} ft` : `reach ${a.reach} ft`;
  const extra = a.light_extra === 'bonus' ? 'Bonus Action, after a Light attack' : a.light_extra ? 'after a Light attack (Nick)' : '';   // GM 2026-10-25
  return [a.name, `${a.atk >= 0 ? '+' : ''}${a.atk} to hit`, `${a.dmg}${a.type ? ' ' + a.type : ''}`, range, extra].filter(Boolean).join(' · ');
}

export function actionText(offers) {
  if (!offers) return '';
  const n = offers.attacks_per_action;
  if (!offers.action_used) return `Action ready (Attack: ${n} attack${n === 1 ? '' : 's'})`;
  return offers.attacks_left > 0 ? `Attack action: ${offers.attacks_left} attack${offers.attacks_left === 1 ? '' : 's'} left` : 'Action used';
}

// JOIN-01: on the players' door a request carries this browser's seat ticket (seat-ticket.mjs); the GM door has none.
export function createLivePort({ fetch: fetchFn = globalThis.fetch, base = SERVER } = {}) {
  let token = null;
  let identity = {};
  async function hello() {
    const res = await fetchFn(base + '/api/hello');
    const out = await res.json();
    if (res.ok && out.ok) token = out.token;
    return out;
  }
  const post = async (path, body, retry = true) => {
    const res = await fetchFn(base + path, { method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ ...body, token, ...seatPart() }) });
    let out;
    try { out = await res.json(); } catch { out = { ok: false, error: 'The service sent no answer.' }; }
    if (out.live?.fight_id) identity = { fight_id: out.live.fight_id, actor: out.live.waiting };
    seatNotice(out);
    if (res.status === 403 && retry && /token/i.test(out.error || '')) { await hello().catch(() => null); return post(path, body, false); }
    return res.ok ? out : { ...out, ok: false, status: res.status, error: out.error || out.refused || `HTTP ${res.status}` };
  };
  return {
    hello,
    start: settings => post('/api/live/new', settings),
    state: since => post('/api/live/state', { since }),
    act: choice => post('/api/live/act', { ...identity, ...choice }),
    ruling: (n, text, allow = false) => post('/api/live/ruling', { n, text, allow }),    // GM 2026-10-24: the GM rules an Ask the GM request
    reaction: (n, cast) => post('/api/live/reaction', { n, cast }),   // SPELL-BATCH-02: a Reaction asked (Shield, Counterspell)
    reactionMode: auto => post('/api/live/reaction-mode', { auto }),   // OA-AUTO-01: the GM's Auto mode
    socialMode: on => post('/api/live/social', { off: !on }),       // GM 2026-11-01: the Influence buttons
    stealth: body => post('/api/live/stealth', body),               // STEALTH-01: Perception, the group stealth check
    initiative: body => post('/api/live/initiative', body),         // INITIATIVE-01: a character's Initiative, Roll the rest
    aim: body => post('/api/live/aim', body),                       // HINTS-01 H4: who an aimed area would catch (read only)
    traps: request => post('/api/live/traps', request),           // GM 2026-10-24: the GM's traps (op catalog/place/remove)
    hazards: request => post('/api/live/hazards', request),       // HAZARDS-01: ice, water, weather, fear, stress, contagions
    sight: picks => post('/api/live/sight', { picks }),           // SIGHT-01: which creatures each character sees
    light: request => post('/api/live/light', request),           // LIGHTS-01: the map's own light (the GM)
    freeze: frozen => post('/api/live/freeze', { frozen }),        // GM 2026-10-24: freeze the fight or let it go on
    panic: on => post('/api/live/panic', { on }),                  // GM 2026-11-01: the Panic Button, on or Resume
    undo: () => post('/api/live/undo', {}),                        // GM-UNDO-01: one step back through the fight
    timerMode: on => post('/api/live/timer', { on }),              // GM 2026-11-01: the tracker's turn timer
    srdMode: on => post('/api/live/srd', { on }),                  // BY-THE-SRD-01: the GM's By the SRD switch
    control: (character, gm) => post('/api/live/control', { character, gm }),   // GM 2026-10-24: the GM plays a character
    mountMode: (mount, mode) => post('/api/live/mount-mode', { mount, mode }),   // MAP-LAYERS-01: the GM's choice
    scene: choice => post('/api/live/scene', { fight_id: identity.fight_id, ...choice }),   // GM 2026-10-24: attitudes, morale
    hints: level => post('/api/join', { op: 'hints', level }),   // HINTS-01: a seat's own hint level (players' door)
    dm: request => post('/api/dm', request),                       // DM-SWAP-01: ask to be the GM, approve, take back
    party: request => post('/api/party', request),                 // GM 2026-10-25: the table's party (GM side)
    day: request => post('/api/adventures/day', request),          // GM 2026-10-25: the adventure's day (restore the party)
    remix: settings => post('/api/remix', settings),              // REMIX-01: the Remix panel's offer
    lineups: request => post('/api/lineups', request),            // Remix Live: saved creature lineups (op list/save/load/delete)
    fly: request => post('/api/live/fly', request),               // ON-THE-FLY-01: the GM's changes to the running fight
    notes: map => post('/api/notes', { map }),                     // VIEW-01: the GM's map notes
    saveNotes: (map, notes) => post('/api/notes/save', { map, notes }),
    flavor: (rev, asks_rev) => post('/api/flavor', { rev, asks_rev }),   // FLAVOR-01: the table's Flavor (a seat: what it may see)
    saveFlavor: (flavor, rev) => post('/api/flavor/save', { flavor, rev }),
    askFlavor: (actor, flavor) => post('/api/flavor/ask', { actor, flavor }),      // PLAYER-FLAVOR-01: a player's look
    ruleFlavor: (actor, approve) => post('/api/flavor/rule', { actor, approve }),  // the GM's answer
    mapPaint: (map, rev, player) => post('/api/map_paint', { map, rev, player }),   // MAP-PAINT-01: the GM's paint over a map
    saveMapPaint: request => post('/api/map_paint/save', request),                 // { map, picture?, shown? }
    importMap: request => post('/api/import-map', request),      // VIEW-01: a Universal VTT map
    importDraft: request => post('/api/import-map/draft', request),   // MAP RULE: its thin walls drafted as squares
  };
}

// 2026-10-19 (GM: "the movement spline and area boundaries isn't showing"): the simulator sends every square the
// character can reach this turn as [x, y, feet, previous x, previous y] (offers.reach). The route to a square follows
// the previous squares back to the start; the outline is the edges between reachable and other squares.
export function reachPath(offers, x, y, start) {
  const reach = new Map((offers?.reach ?? []).map(r => [`${r[0]},${r[1]}`, r]));
  const end = reach.get(`${x},${y}`);
  if (!end) return null;
  const path = [[x, y]];
  let at = end, guard = 0;
  while (at && guard++ < 500) {
    path.unshift([at[3], at[4]]);
    at = reach.get(`${at[3]},${at[4]}`);
  }
  if (start && (path[0][0] !== start[0] || path[0][1] !== start[1])) return null;
  return { path, feet: end[2] };
}

export function reachOutline(reach) {
  const inside = new Set((reach ?? []).map(r => `${r[0]},${r[1]}`)), edges = [];
  for (const r of reach ?? []) {
    const [x, y] = r;
    if (!inside.has(`${x},${y - 1}`)) edges.push([x, y, x + 1, y]);
    if (!inside.has(`${x},${y + 1}`)) edges.push([x, y + 1, x + 1, y + 1]);
    if (!inside.has(`${x - 1},${y}`)) edges.push([x, y, x, y + 1]);
    if (!inside.has(`${x + 1},${y}`)) edges.push([x + 1, y, x + 1, y + 1]);
  }
  return edges;
}

// ------------------------------------------------------------------ spells (LIVE-PLAY-01 slice 2, 2026-10-19)
// The simulator offers the caster's spells (offers.spells: name, level, time, shape, range/radius/length, ready/why,
// targets/refused for creature spells) and slots (offers.slots: left per level). These helpers only arrange them.
export const SPELL_KEY = 'spell:';
export const spellOf = (offers, key) => key?.startsWith(SPELL_KEY) ? offers?.spells?.find(s => s.name === key.slice(SPELL_KEY.length)) ?? null : null;

export function spellCardText(s) {
  const kind = { creature: 'a creature', creatures: s.strikes ? `${s.strikes} at one or several creatures` : `up to ${s.max_targets} creatures`,
    cone: `${s.length_ft}-ft Cone`, sphere: `${s.radius_ft}-ft-radius Sphere`, self: s.radius_ft ? `${s.radius_ft}-ft aura` : 'yourself',
    line: `${s.length_ft}-ft Line`, cube: `${s.size_ft}-ft Cube`, cube_self: `${s.size_ft}-ft Cube from you`,
    wall: `${s.length_ft}-ft wall`, spheres: `up to ${s.points} ${s.radius_ft}-ft-radius Spheres`,   // SPELLS-4-9
    cubes: `up to ${s.points} ${s.size_ft}-ft Cubes` }[s.shape] ?? s.shape;   // group 2: Fire Storm
  const place = s.call ? 'a square (a Magic action, no spell slot)' : s.summoned ? 'a square' : s.teleport ? 'teleport to a square' : null;   // SPELL-EFFECTS-01; SPELL-BATCH-01: Misty Step
  return [s.name, `level ${s.level}`, s.time === 'bonus' ? 'Bonus Action' : 'Action', place ?? kind,
    s.touch ? 'Touch' : s.range_ft ? `range ${s.range_ft} ft` : null, s.concentration ? 'Concentration' : null,
    s.arcanum ? `Mystic Arcanum: ${s.arcanum.left ? 'ready' : 'spent until a Long Rest'}` : null,   // INVISIBILITY-01: touch spells
    s.no_slot ? `${s.no_slot.by}: no slot` : null, s.overchannel ? 'Overchannel' : null,           // CASTER-HIGH
    s.divine?.ready ? 'Divine Intervention' : null].filter(Boolean).join(' · ');
}

export function slotsText(slots) {
  if (!slots?.length) return '';
  return 'Spell slots: ' + slots.map((n, i) => n ? `level ${i + 1} ${'●'.repeat(n)}` : null).filter(Boolean).join(' · ') || 'Spell slots: none left';
}

// How a token looks while a spell card is held: the same colours as for attacks.
export function spellLook(spell, combatant, offers) {
  if (!spell?.targets) return { cls: '', reason: '' };
  if (spell.targets.includes(combatant.id)) {
    const ally = combatant.side === offers?.side;
    return { cls: ally ? 'legal-ally' : 'legal-foe', reason: '' };
  }
  return { cls: 'refused', reason: spell.refused?.[combatant.id] ?? 'Not a legal target.' };
}

// The preview of an area spell while aiming (the simulator decides what it really hits when it is cast).
export function aimPreview(spell, caster, square) {
  if (!spell || !square) return null;
  if (spell.shape === 'cone') {
    const dx = square[0] - caster[0], dy = square[1] - caster[1];
    if (!dx && !dy) return null;
    return { shape: 'cone', appearance: spell.appearance, origin: [caster[0], caster[1]], angle_deg: Math.atan2(dy, dx) * 180 / Math.PI,
      length_ft: spell.length_ft, width_ft: spell.length_ft, preview: true };
  }
  if (spell.shape === 'sphere' || spell.shape === 'spheres') return { shape: 'circle', appearance: spell.appearance, origin: [square[0], square[1]], radius_ft: spell.radius_ft, preview: true };
  // SPELLS-4-9: Wall of Fire, centred on the square and across the caster's view of it, as the simulator places it
  if (spell.shape === 'wall') {
    const w = wallOf(caster, square, spell.length_ft, spell.along_grid);   // SPELLS-4-6-FIGHT: Blade Barrier along the grid
    return { shape: 'line', appearance: spell.appearance, origin: w.origin, angle_deg: w.angle_deg, length_ft: spell.length_ft, width_ft: 5, preview: true };
  }
  // SPELL-CASTER-01: a Line from the caster, a Cube on a square (that square up-left of its middle when it is even), a
  // Cube beside the caster toward the square; the simulator decides what each really holds when it is cast
  if (spell.shape === 'line') {
    const dx = square[0] - caster[0], dy = square[1] - caster[1];
    if (!dx && !dy) return null;
    return { shape: 'line', appearance: spell.appearance, origin: [caster[0], caster[1]], angle_deg: Math.atan2(dy, dx) * 180 / Math.PI,
      length_ft: spell.length_ft, width_ft: spell.width_ft ?? 5, preview: true };
  }
  if (spell.shape === 'cube' || spell.shape === 'cube_self' || spell.shape === 'cubes') {
    const n = spell.size_ft / 5;
    let x0, y0;
    if (spell.shape === 'cubes') { x0 = square[0] - .5; y0 = square[1] - .5; }   // group 2: Fire Storm, the clicked square top-left
    else if (spell.shape === 'cube') { x0 = square[0] + .5 - Math.ceil(n / 2); y0 = square[1] + .5 - Math.ceil(n / 2); }
    else {
      const sx = Math.sign(square[0] - caster[0]), sy = Math.sign(square[1] - caster[1]);
      if (!sx && !sy) return null;
      x0 = sx > 0 ? caster[0] + .5 : sx < 0 ? caster[0] - .5 - n : caster[0] - n / 2;
      y0 = sy > 0 ? caster[1] + .5 : sy < 0 ? caster[1] - .5 - n : caster[1] - n / 2;
    }
    return { shape: 'rectangle', appearance: spell.appearance, origin: [x0, y0 + n / 2], angle_deg: 0, length_ft: spell.size_ft,
      width_ft: spell.size_ft, preview: true };
  }
  return null;
}

// SPELLS-4-9: a straight wall centred on `square`, across the line from the caster (the nearest of 8 directions),
// through the squares' centres: 12 squares along the grid, 8 on a diagonal (sim/live_general.py General.wall).
export function wallOf(caster, square, lengthFt = 60, alongGrid = false) {
  const dx = square[0] - caster[0], dy = square[1] - caster[1];
  const k = !(dx || dy) ? 0 : alongGrid ? 2 * Math.round((Math.atan2(dy, dx) + Math.PI / 2) / (Math.PI / 2))   // 4 directions
    : Math.round((Math.atan2(dy, dx) + Math.PI / 2) / (Math.PI / 4));
  const sx = Math.round(Math.cos(k * Math.PI / 4)), sy = Math.round(Math.sin(k * Math.PI / 4)), step = Math.hypot(sx, sy);
  const n = Math.floor(lengthFt / (5 * step)), first = [square[0] - Math.floor(n / 2) * sx, square[1] - Math.floor(n / 2) * sy];
  return { origin: [first[0] - sx / 2, first[1] - sy / 2], angle_deg: Math.atan2(sy, sx) * 180 / Math.PI, squares: n };
}
// SPELLS-4-9: a cast's effects to draw: one per Sphere for Meteor Swarm (its origins), else the one
export function castEffects(e) {
  if (!e) return [];
  return (e.origins?.length > 1 ? e.origins.map(o => ({ ...e, origin: o })) : [e]).map(effectFromCast);
}

// SPELL-CASTER-01: what a general spell asks before it is cast: one of its choices (Chromatic Orb's damage type,
// Command's word, Blinded or Deafened) and, when a higher slot does more, the slot. ask(question, default) -> text or
// null (cancelled: no cast). The simulator checks both again.
export function spellExtras(s, ask) {
  if (!s) return {};
  const out = {}, high = casterHighExtras(s, ask, out);            // CASTER-HIGH (GM 2026-10-28)
  if (high === null) return null;
  if (!s.general) {                                                 // GM 2026-10-28: the older spells upcast too (Bless)
    if (!high.slot && s.upcast && s.slots_ok?.includes(s.chosen_slot) && s.chosen_slot !== s.slots_ok[0]) out.slot = s.chosen_slot;
    return out;
  }
  if (s.choices?.length) {
    const c = ask(`${s.name}: choose one of ${s.choices.join(', ')}`, s.choices[0]);
    if (c == null) return null;
    out.choice = s.choices.find(x => x.toLowerCase() === String(c).trim().toLowerCase()) ?? s.choices[0];
  }
  if (!high.slot && s.upcast && (s.slots_ok?.length ?? 0) > 1) {
    if (s.slots_ok.includes(s.chosen_slot)) {                      // GM 2026-10-28: the Cast at dropdown on the sheet
      if (s.chosen_slot !== s.slots_ok[0]) out.slot = s.chosen_slot;
      return out;
    }
    const v = ask(`${s.name}: cast it with a spell slot of level ${s.slots_ok.join(', ')}? A higher slot does more.`, String(s.slots_ok[0]));
    if (v == null) return null;
    const n = parseInt(v, 10);
    if (s.slots_ok.includes(n) && n !== s.slots_ok[0]) out.slot = n;
  }
  return out;
}

// CASTER-HIGH (GM 2026-10-28, SRD 5.2.1): what a Cast card the simulator marks asks first. Divine Intervention (Cleric
// 10: a Magic action, no slot, no Material components); Overchannel (Evoker 14: the maximum damage, the cost said);
// Spell Mastery and Signature Spells (Wizard 18, 20: no slot, unless a slot level is typed). Fills `out`; returns
// { slot: true } when the slot was settled here, or null when cancelled.
const YES = v => /^\s*y/i.test(String(v ?? ''));
export function casterHighExtras(s, ask, out) {
  if (s.divine_only) {                                              // no slot or component left: only this way
    const v = ask(`${s.name}: no spell slot or component for it now; cast it with Divine Intervention? A Magic action, once per Long Rest. Yes or no`, 'yes');
    if (v == null || !YES(v)) return null;
    out.divine = true; return { slot: true };
  }
  if (s.divine?.ready) {
    const v = ask(`${s.name}: cast it with Divine Intervention? A Magic action, no spell slot, no Material components; once per Long Rest. Yes or no`, 'no');
    if (v == null) return null;
    if (YES(v)) { out.divine = true; return { slot: true }; }
  }
  if (s.overchannel?.ready) {
    const v = ask(`${s.name}: Overchannel, the spell's maximum damage this turn? Cost: ${s.overchannel.cost}. Yes or no`, 'no');
    if (v == null) return null;
    if (YES(v)) out.overchannel = true;
  }
  if (s.no_slot && !out.overchannel) {
    const slots = (s.slots_ok ?? []).filter(n => n >= (s.level ?? 1));
    const v = ask(`${s.name}: ${s.no_slot.by}, ${s.no_slot.note}. Press OK for no slot${slots.length ? `, or type a slot level (${slots.join(', ')})` : ', or type "slot" to spend one'}.`, 'no slot');
    if (v == null) return null;
    const n = parseInt(v, 10);
    if (slots.includes(n)) { out.slot = n; out.use_slot = true; }
    else if (/slot/i.test(v) && !/no slot/i.test(v)) out.use_slot = true;
    return { slot: true };
  }
  return {};
}

// The table's effect objects for what the simulator sent (cast effects and lasting auras), in squares.
export function effectFromCast(e) {
  if (!e) return null;
  const out = { shape: e.shape, appearance: e.appearance, origin: e.origin, angle_deg: e.angle_deg ?? 0,
    length_ft: e.length_ft ?? 5, width_ft: e.width_ft ?? 5, radius_ft: e.radius_ft ?? 5 };
  return out;
}
// GM 2026-10-22 ("the phone display doesn't shows effects"): the live state carries each cast's effect for a few
// seconds (sim/live_play.py EFFECT_SECONDS); every screen draws the ones it has not drawn yet, whoever cast them.
// seen: the "<fight>:<number>" of the effects this screen drew.
export function newCastEffects(snap, seen) {
  return (snap?.effects ?? []).filter(e => {
    const key = `${snap.fight_id}:${e.n}`;
    if (!e.effect || seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}
// The GM console follows a seated player's turn (a phone) without redrawing every second: only when the fight moved.
export function liveMoved(before, after) {
  if (!before || !after) return true;
  return ['fight_id', 'revision', 'waiting', 'log_n', 'done', 'error', 'round'].some(k => before[k] !== after[k]);
}
// MAP-LAYERS-01 (GM 2026-10-24: "mask layers ... effects on layers"; "spell effects that cause obscurement (fog,
// smoke, darkness etc), invisibility"): the simulator's lasting spell zones (snapshot layers.zones: Fog Cloud,
// Darkness, Stinking Cloud), drawn on the air layer above the tokens on the 2D map and as volumes in 3D. The engine
// already decided who sees what (party_sight); a zone only shows where it is.
export const ZONE_LOOK = { gm: { fog: .34, dark: .5 }, players: { fog: .62, dark: .88 } };
// SPELL-EFFECTS-01: Web, Entangle and Grease are squares (cube: their edges in squares); veil: how much it hides
// (heavy: Fog Cloud, Sleet Storm, Cloudkill; light: Web; none: a ground spell, only tinted).
export function layerEffects(layers) {
  return (layers?.zones ?? []).map(z => {
    const base = { appearance: z.darkness ? 'darkness' : z.appearance, lasting: true, layer: z.layer ?? 'air', darkness: !!z.darkness,
      spell: z.spell, owner: z.owner_name, rounds_left: z.rounds_left, id: `zone-${z.n}`, veil: z.veil ?? 'heavy' };
    if (z.cube) {
      const [x0, y0, x1, y1] = z.cube;
      return { ...base, shape: 'rectangle', origin: [x0, (y0 + y1) / 2], angle_deg: 0, length_ft: (x1 - x0) * 5, width_ft: (y1 - y0) * 5,
        cube: z.cube, radius_ft: (x1 - x0) * 2.5 };
    }
    return { ...base, shape: 'circle', origin: z.origin, radius_ft: z.radius_ft };
  });
}
// MAP-LAYERS-01 step 2: an Invisible creature per viewer. The service already left out of a seat's map what that
// character can't see (sim/map_layers.py, tools/table_seats.py); what is still here is drawn faded: for the GM a faded
// outline (dashed), for players their own invisible character (or one their character's senses pierce).
export function invisibleLook(c, perspective) {
  if (!(c?.conditions ?? []).includes('Invisible')) return null;
  return perspective === 'gm' ? { opacity: .38, dashed: true, label: "Invisible (players whose characters can't see it don't get it)" }
    : { opacity: .45, dashed: false, label: 'Invisible' };
}
// MAP-LAYERS-01 step 3: a rider and its mount as layered tokens. Mounts first, riders after (drawn on top, smaller and
// raised, so the mount's edge stays its own click); each keeps its own HP, conditions and saves.
export function layerOrder(combatants, layers) {
  const riders = new Map((layers?.mounts ?? []).map(m => [m.rider, m.mount]));
  const mounts = new Set(riders.values());
  const rank = c => riders.has(c.id) ? 2 : mounts.has(c.id) ? 0 : 1;
  return [...(combatants ?? [])].map((c, i) => ({ c, i })).sort((a, b) => rank(a.c) - rank(b.c) || a.i - b.i).map(({ c }) => {
    const m = riders.get(c.id), mount = m && combatants.find(x => x.id === m);
    // drawn on the mount's centre (its own square stays in the rules: c.square)
    return mount ? { ...c, square: [c.x, c.y], x: mount.x, y: mount.y, riding: m, rider_scale: .74, rider_lift: Math.max(.35, mount.space_ft / 5 * .55) } : c;
  });
}
// The sheet's Mount line (sim/map_layers.py mount_offers): Mount <creature> for each creature within 5 ft (greyed with
// the reason), or Dismount and the controlled mount's three actions while riding.
const MOUNT_ACT = { dash: 'Dash', disengage: 'Disengage', dodge: 'Dodge' };
// GM 2026-10-25 ("a warning given to casters if they are intentionally wanting to break their concentration"): a
// Concentration spell cast while another is held ends the held one (SRD 5.2.1 Concentration), so the table asks first,
// hints on or off. Moving Hex or Hunter's Mark keeps it: no question. '' when nothing is ended.
export function concentrationBreak(offers, s) {
  const held = offers?.concentrating;
  if (!held || !s?.concentration || s.moves) return '';
  return s.name === held ? `Casting ${s.name} again ends the ${held} you hold now and starts it over.`
    : `Casting ${s.name} ends your Concentration on ${held}.`;
}
export function mountButtons(offers) {
  const m = offers?.mount;
  if (!m) return [];
  // GM 2026-10-25 (ruling M2): a player's character is ridden only when its player says yes, here on its own sheet
  const consent = m.consent ? [{ label: m.consent.on ? 'Stop letting others ride me' : 'Let others ride me', ready: true, why: '',
    cmd: { op: 'mount_consent', on: !m.consent.on } }] : [];
  if (!m.riding) return [...(m.candidates ?? []).map(c => ({ label: `Mount ${c.name} (${m.half_ft} ft)`, ready: c.ready, why: c.why,
    cmd: { op: 'mount', target: c.target }, mode: c.mode, link: c.link })), ...consent];
  return [{ label: `Dismount (${m.half_ft} ft)`, ready: m.dismount?.ready, why: m.dismount?.why, cmd: { op: 'dismount' } },
    ...(m.actions ?? []).map(a => ({ label: `Mount: ${MOUNT_ACT[a.action]}`, ready: a.ready, why: a.why, cmd: { op: 'mount_action', action: a.action } }))];
}
export function mountText(offers, name = id => id) {
  const m = offers?.mount;
  if (!m?.riding) return '';
  return `Riding ${name(m.riding)} (${m.mode === 'controlled' ? 'controlled: it moves on this turn with its own Speed' : 'independent: it moves on its own turn'})` +
    ` · own movement ${m.own_movement} ft`;
}

export function auraEffects(auras, combatants) {
  return (auras ?? []).map(a => {
    const c = combatants?.find(x => x.id === a.caster);
    return c ? { shape: 'circle', appearance: a.appearance, origin: [c.x, c.y], radius_ft: a.radius_ft, aura: true } : null;
  }).filter(Boolean);
}

// LIVE-PLAY-01 slice 3 (GM 2026-10-20): the sheet's other actions and the doors beside the character, from the
// simulator's offers (sim/live_actions.py checks them again when chosen). A Rogue's Cunning Action adds Bonus Action
// buttons for Dash and Disengage.
// Slice 4: Help, Grapple, Shove and Lay On Hands pick a creature like an attack card (ACT_KEY + op[:mode]); Ready gets one
// button per sheet attack; class Bonus Actions say so.
// GM 2026-10-23 (the Sorcerer): Innate Sorcery and Font of Magic come with the others (sim/live_sorcery.py); Font of
// Magic's buttons carry the slot level and the service's own label.
const ACTION_LABEL = { dash: 'Dash', disengage: 'Disengage', dodge: 'Dodge', help: 'Help', hide: 'Hide', search: 'Search',
  ready: 'Ready', second_wind: 'Second Wind', action_surge: 'Action Surge', rage: 'Rage', lay_on_hands: 'Lay on Hands', grapple: 'Grapple', shove: 'Shove',
  innate_sorcery: 'Innate Sorcery', study: 'Study', influence: 'Influence', shake: 'Shake awake', stabilize: 'Stabilize',   // shake: GM 2026-10-25 (L4)
  spirit_strike: 'Spiritual Weapon: strike',                     // GM 2026-10-25: its Bonus Action on later turns
  martial_arts: 'Martial Arts: Unarmed Strike' };                 // MONK-01 (the others carry their mode's label)
export const ACT_KEY = 'act:';
const PICK = { help: 'a creature next to you', grapple: 'a creature next to you', shove: 'a creature next to you', lay_on_hands: 'yourself or an ally in touch',
  study: 'a creature you can see', influence: 'a creature you can see', shake: 'a sleeper next to you', stabilize: 'a dying character next to you',
  spirit_strike: 'a creature within 20 ft of the spectral force',     // GM 2026-10-23: Study, Influence (one per way)
  command_undead: 'a creature for your undead to attack', familiar_help: 'a foe for your familiar to help against',   // SPELL-EFFECTS-01
  martial_arts: 'a creature within 5 ft', flurry: 'a creature within 5 ft',                         // MONK-01
  break_enchantment: 'a creature you touch, Charmed or Frightened by a Celestial, Elemental, Fey, Fiend or Undead' };   // SPELLS-4-6-FIGHT
export function actionButtons(offers) {
  const acts = offers?.actions ?? [], out = [];
  for (const a of acts) {
    if (FONT[a.op]) continue;                                      // Font of Magic: its own compact row (fontButtons)
    if (a.square) {                                                // GM 2026-10-24: Search or Study a square (traps)
      out.push({ ready: !!a.ready, why: a.why ?? '', label: a.label, square: { op: a.op } }); continue;
    }
    if (a.op === 'trap') {                                         // GM 2026-10-24: a step on a known trap, or a lock
      const cmd = { op: 'trap', how: a.how, ...(a.trap ? { trap: a.trap } : {}), ...(a.target ? { target: a.target } : {}), ...(a.door ? { door: a.door } : {}) };
      out.push({ ready: !!a.ready, why: a.why ?? '', link: a.link ?? null, label: a.time === 'bonus' ? `${a.label} (Bonus Action)` : a.time === 'move' ? `${a.label} (movement)` : a.label,
        ...(a.how === 'climb' ? { square: cmd } : { cmd }) });
      continue;
    }
    const name = ACTION_LABEL[a.op] ?? a.label ?? a.op;
    const label = a.haste ? `${name} (Haste's action)` :                 // SPELL-EFFECTS-01: the hasted creature's extra action
      a.time === 'bonus' ? `${name} (Bonus Action)` : a.time === 'free' ? `${name} (no action)` : name;
    const base = { ready: !!a.ready, why: a.why ?? '' };
    if (a.op === 'ready') {
      for (const w of a.weapons ?? []) out.push({ ...base, label: `Ready: ${w.name}`, cmd: { op: 'ready', weapon: w.key } });
      // GM 2026-10-25: a readied spell (cast now, held with Concentration, released with the Reaction)
      for (const s of a.spells ?? []) out.push({ ready: !!s.ready, why: s.why ?? '', label: `Ready: ${s.name} (spell, within ${s.range_ft} ft)`,
        cmd: { op: 'ready', spell: s.name }, readySpell: { ...s, concentration: true } });
      continue;
    }
    if (PICK[a.op]) {
      const none = base.ready && !(a.targets ?? []).length ? { ready: false, why: `No creature to ${name.toLowerCase()} now (${PICK[a.op]}).` } : {};
      for (const mode of a.op === 'shove' ? ['prone', 'push'] : [a.mode ?? null])
        out.push({ ...base, ...none, label: a.mode ? a.label : mode ? `${name} (${mode === 'prone' ? 'Prone' : 'Push'})` : label,
          pick: ACT_KEY + a.op + (mode ? ':' + mode : '') });
      continue;
    }
    out.push({ ...base, label: a.mode ? a.label : label,              // MONK-01: Patient Defense / Step of the Wind, each way
      cmd: { op: a.op, ...(a.level ? { level: a.level } : {}), ...(a.door ? { door: a.door } : {}), ...(a.mode ? { mode: a.mode } : {}) } });   // douse_door: its door
  }
  for (const a of acts.filter(a => a.bonus))
    out.push({ label: `${ACTION_LABEL[a.op] ?? a.op} (Bonus Action)`, cmd: { op: a.op, bonus: true }, ready: !a.blocked, why: a.blocked ?? '' });
  return out;
}
// GM 2026-10-23 (the Sorcerer): the sheet's Sorcery line, and Metamagic chosen ("armed") before a spell or an attack
// cantrip: it travels with that choice, and each card says whether the armed options suit it (the card's own list from
// the service, which checks everything again when the spell is cast).
export const TRANSMUTE = ['acid', 'cold', 'fire', 'lightning', 'poison', 'thunder'];
const FONT = { font_convert: 'A slot into points (no action):', font_create: 'Points into a slot (Bonus Action):' };
// Font of Magic's buttons, one small one per slot level: [{title, buttons: [{label, cmd, ready, why}]}]
export function fontButtons(offers) {
  return Object.entries(FONT).map(([op, title]) => ({ title, buttons: (offers?.actions ?? []).filter(a => a.op === op).map(a => ({
    label: op === 'font_create' ? `Level ${a.level} (${a.cost} pts)` : `Level ${a.level} (+${a.level})`, title: a.label,
    cmd: { op, level: a.level }, ready: !!a.ready, why: a.why ?? '' })) })).filter(g => g.buttons.length);
}
export function sorceryText(offers) {
  const s = offers?.sorcery;
  if (!s) return '';
  const r = s.innate_rounds, n = s.innate_left;
  return [s.max ? `Sorcery Points ${s.points}/${s.max}` : null,
    r ? `Innate Sorcery active (${r} round${r === 1 ? '' : 's'} left)` : `Innate Sorcery: ${n} use${n === 1 ? '' : 's'} left`,
    s.metamagic?.length ? `Metamagic: ${s.per_spell > 1 ? 'up to two options' : 'one option'} per spell (choose it before casting)` : null,
    // SORCERER-20 (GM 2026-10-28): Arcane Apotheosis's free option this turn, Dragon Wings
    s.apotheosis === 'free' ? 'Arcane Apotheosis: one Metamagic option free this turn' :
      s.apotheosis === 'used' ? 'Arcane Apotheosis: used this turn' : null,
    s.wings ? (s.wings.on ? 'Dragon Wings: flying (Fly Speed 60 ft)' : `Dragon Wings: ${s.wings.left ? '1 use' : 'used (3 Sorcery Points restore it)'}`) : null]
    .filter(Boolean).join(' · ');
}
export function metamagicFields(armed) {
  if (!armed?.metas?.length) return {};
  return { metamagic: [...armed.metas], ...(armed.metas.includes('Transmuted Spell') ? { transmute: armed.transmute || 'cold' } : {}) };
}
export function metamagicNote(card, armed) {
  if (!armed?.metas?.length) return null;
  if (!card?.metamagic) return { ok: false, why: 'Metamagic changes a spell, not this attack.' };
  for (const m of armed.metas) {
    const o = card.metamagic.find(x => x.name === m);
    if (!o?.ready) return { ok: false, why: o?.why ?? `${m} does not suit ${card.name}.` };
  }
  return { ok: true, why: 'With ' + armed.metas.join(' and ') };
}
export const twinArmed = (spell, armed) => !!armed?.metas?.includes('Twinned Spell') && !!spell?.metamagic?.some(m => m.name === 'Twinned Spell' && m.ready);

// GM 2026-10-23 ("Check all prerequisites before allowing a tool, consumable, or process to be availed. Create
// in-game links to connect prerequisites"): the bag's items in a fight (sim/live_items.py). Each use comes ready, or with
// why not and a link to where it is fixed (the Market, Characters); the service checks every need again when chosen.
const TIME_LABEL = { bonus: 'Bonus Action', action: 'Action', attack: 'one attack' };
export function itemButtons(offers) {
  return (offers?.items?.uses ?? []).map(u => ({
    label: `${u.label} (${TIME_LABEL[u.time] ?? u.time}${u.uses != null ? `, ${u.uses} use${u.uses === 1 ? '' : 's'} left` : ''})`,
    [u.square ? 'square' : 'cmd']: { op: 'use_item', item: u.item, ...(u.weapon ? { weapon: u.weapon } : {}), ...(u.target ? { target: u.target } : {}),
      ...(u.use != null ? { use: u.use } : {}) },                    // GM 2026-10-26: which of a tool's Utilize uses
    ready: !!u.ready, why: u.why ?? '', link: u.link ?? null, effect: u.effect ?? '' }));
}

// GM 2026-10-24 (SRD 5.2.1 traps, sim/traps.py): what the map shows of each trap. The GM sees every trap (a hidden one
// dashed); a player's snapshot carries only the traps the party knows (table_seats.player_view). A square pick
// (Search/Study a square, area gear, climbing out) sends the command with the square clicked.
const TRAP_MARK = { hidden_pit: 'pit', spiked_pit: 'pit', collapsing_roof: 'wire', falling_net: 'wire', fire_statue: 'plate',
  poisoned_darts: 'plate', poisoned_needle: 'lock', rolling_stone: 'plate', caltrops: 'gear', 'ball-bearings': 'gear', oil: 'oil', 'hunting-trap': 'gear',
  net: 'gear' };                                                   // GM 2026-10-26: a thrown Net, until the creature escapes
export function trapMarks(traps) {
  const out = [];
  for (const t of traps ?? []) {
    const state = t.kind === 'net' ? 'holding a creature until it escapes' : t.gear ? (t.lit ? 'burning' : 'set') : t.open ? 'open pit' : t.disarmed ? 'made safe' : t.rubble ? 'rubble' : !t.armed ? 'spent' : t.fired ? 'gone off (it resets)' : t.found?.length ? 'found' : 'hidden';
    const cls = ['trap', TRAP_MARK[t.kind] ?? 'plate', t.known ? 'known' : 'secret', t.open ? 'open' : t.armed ? 'armed' : 'safe', t.lit ? 'lit' : ''].filter(Boolean).join(' ');
    const title = `${t.name}${t.severity ? ` (${t.severity}${t.band ? ', levels ' + t.band : ''})` : ''}: ${state}`;
    for (const [x, y] of t.squares ?? []) out.push({ x, y, cls, title, id: t.id });
    if (t.statue) out.push({ x: t.statue[0], y: t.statue[1], cls: 'trap statue ' + (t.known ? 'known' : 'secret'), title: `${t.name}: the statue`, id: t.id });
    if (t.stone && (t.stone.rolling || t.stone.done)) out.push({ x: t.stone.at[0], y: t.stone.at[1], size: 2, cls: 'trap stone', title: 'The Rolling Stone', id: t.id });
    if (t.rubble) for (const [x, y] of t.area ?? []) out.push({ x, y, cls: 'trap rubble', title: 'Rubble: Difficult Terrain', id: t.id });
  }
  return out;
}
export function squareCommand(pick, x, y) {
  return { ...pick, x, y };
}
export function bagText(offers) {
  const it = offers?.items;
  if (!it) return '';
  const coat = offers.coated ? ` · Basic Poison on the ${offers.coated.name}${offers.coated.pieces ? ` (${offers.coated.pieces} pieces)` : ''}` : '';
  return (it.bag?.length ? 'Bag: ' + it.bag.map(b => b.qty > 1 ? `${b.name} x${b.qty}` : b.name).join(', ') : 'Bag: empty') + coat;
}

// GM 2026-10-24 ("the player's character sheet with the playable actions as buttons next to the action"): the turn
// bar's lights, the class features apart from the other actions, and an attack roll's line on the sheet.
export const FEATURE_OPS = new Set(['second_wind', 'action_surge', 'rage', 'lay_on_hands', 'innate_sorcery', 'font_convert', 'font_create',
  'abjure_foes',                                                     // GM 2026-10-26: Abjure Foes (Paladin 9)
  'martial_arts', 'flurry', 'patient_defense', 'step_of_the_wind',   // MONK-01: Martial Arts, Monk's Focus
  'superior_defense',                                                 // GM 2026-10-28: Superior Defense (Monk 18)
  'dragon_wings', 'fold_wings',                                      // SORCERER-20: Dragon Wings (Draconic Sorcery 14)
  'intimidating_presence', 'holy_nimbus',                          // MARTIAL-HIGH: Berserker 14, Devotion 20
  'merge_shadows', 'blink_steps']);                                  // EPIC-BOONS-01: Night Spirit, Dimensional Travel
// MONK-01 (GM 2026-10-28, "Monk as SRD"): the sheet's Focus line
export function focusText(offers) {
  const f = offers?.focus;
  if (!f) return '';
  return [f.max ? `Focus Points ${f.points}/${f.max}` : null, `Martial Arts d${f.die}`, f.max ? `save DC ${f.dc}` : null,
    f.superior_defense ? `Superior Defense on (${f.superior_defense} round${f.superior_defense === 1 ? '' : 's'} left)` : null,
    f.reactions?.length ? `Reactions asked when they happen: ${f.reactions.join(', ')}` : null].filter(Boolean).join(' · ');
}
// GM 2026-10-26 (the test heroes to level 20): an attack's own choices, picked on its row before the target. Tactical
// Master (Fighter 9) swaps the weapon's mastery for Push, Sap or Slow; Supreme Sneak (Thief 9) makes it a Stealth Attack
// (one Sneak Attack die: a hidden Rogue stays hidden behind cover). The service checks both again.
export function attackExtras(a, pick) {
  const out = {};
  if (pick?.mastery && (a?.masteries ?? []).includes(pick.mastery)) out.mastery = pick.mastery;
  if (pick?.dmgtype && (a?.choices ?? []).includes(pick.dmgtype)) out.dmgtype = pick.dmgtype;   // GM 2026-11-01: Sorcerous Burst
  if (pick?.stealth && a?.stealth_attack?.ready) out.cunning = 'stealth_attack';
  if (pick?.stun && a?.stunning_strike?.ready) out.stun = true;         // MONK-01: Stunning Strike, paid only on a hit
  if (pick?.hurl && a?.hurl_through_hell?.ready) out.hurl = true;      // CASTER-HIGH: Hurl Through Hell, on a hit
  if (pick?.devious && a?.devious?.options?.some(o => o.key === pick.devious && o.ready)) out.devious = pick.devious;   // MARTIAL-HIGH
  return out;
}
export function turnLights(offers) {
  if (!offers) return [];
  return [{ label: 'Action', used: !!offers.action_used && !(offers.attacks_left > 0) },
    { label: offers.attacks_left > 0 ? `Attacks: ${offers.attacks_left} left` : null, used: false },
    { label: 'Bonus Action', used: !!offers.bonus_used }, { label: 'Reaction', used: !!offers.reaction_used },
    { label: `${offers.movement} ft move`, used: !(offers.movement > 0) },
    // SPELL-EFFECTS-01: Haste's extra action, Slow's limits, a 1-minute casting under way
    { label: offers.haste ? "Haste's action" : null, used: !offers.haste?.free, title: offers.haste ? `One more action: ${offers.haste.for}` : '' },
    { label: offers.slowed ? 'Slowed' : null, used: false, title: offers.slowed ?? '' },
    { label: offers.casting ? `Casting ${offers.casting.spell}: ${offers.casting.turns} of ${offers.casting.of}` : null, used: false }]
    .filter(l => l.label);
}
export function rollLine(out) {
  const line = (out?.lines ?? []).find(x => / -> (hit|miss|crit)/.test(x)) ?? '';
  const m = line.match(/: (d20 .*?) -> (hit|miss|crit)/);
  const res = out?.result;
  return { text: m ? `${m[1]} → ${res === 'crit' ? 'Critical' : res === 'hit' ? 'Hit' : 'Miss'}` : (res === 'crit' ? 'Critical' : res === 'hit' ? 'Hit' : res === 'miss' ? 'Miss' : ''),
    cls: res === 'crit' ? 'crit' : res === 'hit' ? 'hit' : 'miss' };
}

// The command a picked action makes on a creature: "act:shove:push" + target -> {op: 'shove', mode: 'push', target}.
export function actCommand(key, target) {
  const [op, mode] = key.slice(ACT_KEY.length).split(':');
  return mode ? { op, mode, target } : { op, target };
}
export function actLook(offers, key, combatant) {
  // MARTIAL-HIGH: an action of that very mode first (Restoring Touch: lay_on_hands:Blinded), else the action itself
  const [op, mode] = key.slice(ACT_KEY.length).split(':'), list = offers?.actions ?? [];
  const a = list.find(x => x.op === op && mode && x.mode === mode) ?? list.find(x => x.op === op && (!x.mode || x.mode === mode));
  if (!a || (combatant.id === offers.actor && !(a.targets ?? []).includes(combatant.id))) return { cls: 'self', reason: '' };
  if ((a.targets ?? []).includes(combatant.id)) return { cls: combatant.side === offers.side ? 'legal-ally' : 'legal-foe', reason: '' };
  return { cls: 'refused', reason: a.refused?.[combatant.id] ?? 'Not a legal choice.' };
}
export function doorButtons(offers) {
  return (offers?.doors ?? []).filter(d => d.near).map(d => {
    const why = d.broken ? `The ${d.id} is broken: the doorway stays open.` : d.locked ? `The ${d.id} is locked.` :
      offers.interaction_used ? 'Your free object interaction is used this turn.' : '';
    return { label: `${d.open ? 'Close' : 'Open'} the ${d.id}`, cmd: { op: 'door', door: d.id }, ready: !why && d.ready !== false, why };
  });
}

// VIEW-01 (GM 2026-10-20: a player view and fog of war; "we already have fog of war mostly with sight, hearing, and
// perception"): the simulator reports the party's sight (sim/live_play.py party_sight: squares and creatures, by its
// own rules for walls, doors, light, darkvision and hidden creatures); the page only draws it.
export function mergeExplored(explored, sight) {
  const out = new Set(explored ?? []);
  for (const [x, y] of sight?.squares ?? []) out.add(`${x},${y}`);
  return [...out];
}
export function fogCells(cols, rows, sight, explored) {
  const dim = [], hidden = [];
  if (!sight) return { dim, hidden };
  const now = new Set((sight.squares ?? []).map(p => p.join())), before = new Set(explored ?? []);
  for (let y = 0; y < rows; y++) for (let x = 0; x < cols; x++) {
    const k = `${x},${y}`;
    if (!now.has(k)) (before.has(k) ? dim : hidden).push([x, y]);
  }
  return { dim, hidden };
}
export function playerCombatants(combatants, sight) {
  if (!sight) return combatants;
  const seen = new Set(sight.creatures ?? []);
  return combatants.filter(c => c.pc || seen.has(c.id));
}
// SPELL-OBJECTS-01 (GM 2026-10-27: spells at doors): the doors the held spell card or attack cantrip may be cast at
// (the service's own list: range, a clear line, what the spell targets) and why not the others; null when it says none.
// Step 5: with Distant Spell armed, the doors twice as far (Touch: 30 ft) the service listed as distant_doors.
// Step 6: the same for the map's props (which: 'props': crates, statues, braziers... by "crate at (4, 5)").
export function doorAim(offers, key, metas = [], which = 'doors') {
  const s = key?.startsWith(SPELL_KEY) ? spellOf(offers, key) : (offers?.attacks ?? []).find(a => a.key === key);
  const one = which === 'doors' ? 'door' : 'prop';
  if (!s || !(s[which] || s[one + '_refused'])) return null;
  const ok = metas.includes('Distant Spell') && s['distant_' + which] ? s['distant_' + which] : s[which] ?? [];
  const refused = Object.fromEntries(Object.entries(s[one + '_refused'] ?? {}).filter(([d]) => !ok.includes(d)));
  return { spell: s.spell ?? s.name, ok, refused };
}
// A door's state for its tooltip: "wood, AC 15, 12 of 18 Hit Points, burning" (SRD 5.2.1 Breaking Objects).
export function doorText(id, st) {
  if (!st) return `The ${id}`;
  if (st.broken) return `The ${id}: broken, an open doorway for good`;
  return `The ${id}: ${st.material}, AC ${st.ac}, ${st.hp} of ${st.max_hp} Hit Points` + (st.burning ? ', burning (1d4 Fire each round)' : '') +
    (st.arcane_lock ? ', held by Arcane Lock' : st.sealed ? ', sealed shut by Stone Shape' : st.locked ? ', locked' : '') + (st.hot ? ', red-hot (Heat Metal)' : '');
}

export function withDoors(map, openDoors) {
  if (!Array.isArray(openDoors)) return map;
  const open = new Set(openDoors.map(String));
  return { ...map, walls: map.walls.map(w => w.door ? { ...w, open: open.has(String(w.id)) } : w) };
}

// VIEW-01 (GM 2026-10-20): notes pinned to the map (kept by the service on the GM's PC). The GM sees every pin; the
// player view only notes marked show_players, on squares the party has explored. One note per square.
export function notePins(notes, explored, player) {
  if (!player) return notes ?? [];
  const seen = new Set(explored ?? []);
  return (notes ?? []).filter(n => n.show_players && seen.has(`${n.x},${n.y}`));
}
export const noteAt = (notes, x, y) => (notes ?? []).find(n => n.x === x && n.y === y) ?? null;
export function upsertNote(notes, note) {
  const id = note.id ?? `n${Date.now().toString(36)}${Math.floor(Math.random() * 1e6).toString(36)}`;
  const clean = { id, x: note.x, y: note.y, text: String(note.text ?? '').slice(0, 2000), show_players: !!note.show_players };
  return [...(notes ?? []).filter(n => n.id !== id && !(n.x === note.x && n.y === note.y)), clean];
}
export const deleteNote = (notes, id) => (notes ?? []).filter(n => n.id !== id);

// VIEW-02 (GM 2026-10-20: "I want the actual map with full functionality be able to pop out and the tokens fully
// functioning and draggable. The commands will still be on the main console."): the pop-out map and the main console are
// two windows on ONE live session (the service decides every move; a stale window is refused by the revision). Over a
// BroadcastChannel each tells the other: changed (refresh now), select (the main console's held attack or spell, so the
// pop-out shows the same highlights), used (the pop-out spent it), result (what a pick in the pop-out did).
export const SYNC_CHANNEL = 'mythastria-live';
export function liveSync({ channel, refresh, onSelect = null, onUsed = null, onResult = null }) {
  const id = Math.random().toString(36).slice(2);
  let lastSelect = null;
  channel.onmessage = e => {
    const m = e.data;
    if (!m || m.from === id) return;
    if (m.type === 'changed') refresh();
    else if (m.type === 'select') onSelect?.({ held: m.held ?? null, casting: m.casting ?? null });
    else if (m.type === 'used') onUsed?.();
    else if (m.type === 'result') onResult?.(m.text, m.cls);
  };
  const send = m => channel.postMessage({ ...m, from: id });
  return {
    changed: () => send({ type: 'changed' }),
    select: ({ held = null, casting = null }) => {
      const s = JSON.stringify({ held, casting });
      if (s === lastSelect) return;
      lastSelect = s;
      send({ type: 'select', held, casting });
    },
    used: () => send({ type: 'used' }),
    result: (text, cls = '') => send({ type: 'result', text, cls }),
    close: () => channel.close(),
  };
}

// LIGHTS-01 (GM 2026-10-26, the Documents page goal "Light sources in play"): torches, lanterns, lamps, candles and the
// light spells (Mythastria sim/light_sources.py). The engine decides who sees what by them (party_sight, each seat's
// cut); the page draws the map's own light as a veil, the lit areas cut out of it, and each light's rings: Bright solid,
// Dim dashed (dim_ft is the outer radius), a Bullseye Lantern as its Cone. The GM sees every light; a player's window
// only those its party sees (carried by a creature on that map, or lying on a square seen now).
export const AMBIENT_LABEL = { bright: 'Bright Light', dim: 'Dim Light', dark: 'Darkness' };
export const VEIL = { gm: { dim: .22, dark: .5 }, players: { dim: .35, dark: .82 } };
export function seenLights(lights, sight, keptIds) {
  if (!lights || !sight) return lights;
  const now = new Set((sight.squares ?? []).map(p => p.join())), kept = new Set(keptIds ?? []);
  return { ...lights, sources: (lights.sources ?? []).filter(l => l.holder ? kept.has(l.holder) : now.has((l.at ?? []).join())) };
}
export function lightRings(lights, squareFt = 5) {
  return (lights?.sources ?? []).filter(l => l.lit && l.dim_ft > 0).map(l => ({ n: l.n, x: l.x, y: l.y, bright: l.bright_ft / squareFt,
    dim: l.dim_ft / squareFt, cone: !!l.cone, aim: l.aim ?? 0, name: l.name, held: !!l.holder,
    title: `${l.name}: ${l.bright_ft ? `Bright Light ${l.bright_ft} ft, ` : ''}Dim Light to ${l.dim_ft} ft${l.cone ? ' (a Cone)' : ''}` +
      (l.minutes_left != null ? ` · ${l.minutes_left} min left` : '') + (l.hood === 'down' ? ' · hood lowered' : '') }));
}
export function groundLights(lights) {
  return (lights?.sources ?? []).filter(l => !l.holder && l.at).map(l => ({ n: l.n, x: l.at[0], y: l.at[1], lit: l.lit,
    title: `${l.name} on the ground${l.lit ? ', burning' : l.covered ? ', covered' : ', unlit'}` }));
}
// An SRD 5.2.1 Cone: as wide as it is far from its origin (half-angle atan 1/2), pointing aim degrees (0 east, 90 south)
export function conePath(cx, cy, r, aim) {
  const half = Math.atan(.5), a = aim * Math.PI / 180, p = t => `${cx + r * Math.cos(t)} ${cy + r * Math.sin(t)}`;
  return `M${cx} ${cy} L${p(a - half)} A${r} ${r} 0 0 1 ${p(a + half)} Z`;
}
const LIGHT_TIME = { bonus: 'Bonus Action', action: 'Action', interaction: 'object interaction', free: 'no action' };
export function lightButtons(offers) {
  return (offers?.lights ?? []).map(o => {
    const cmd = { op: 'light', do: o.do };
    for (const k of ['item', 'light', 'target', 'spell', 'on']) if (o[k] != null) cmd[k] = o[k];
    return { label: `${o.label} (${LIGHT_TIME[o.time] ?? o.time})`, [o.square ? 'square' : 'cmd']: cmd, ready: !!o.ready,
      why: o.why ?? '', link: o.link ?? null };
  });
}
export function lightText(offers, lights) {
  const mine = (lights?.sources ?? []).filter(l => l.holder === offers?.actor);
  return mine.length ? 'Holding: ' + mine.map(l => `${l.name}${l.lit ? ` (lit${l.minutes_left != null ? `, ${l.minutes_left} min` : ''})` : l.covered ? ' (covered)' : ' (unlit)'}`).join(', ')
    : 'No light in hand.';
}
