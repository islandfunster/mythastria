// Read-only replay of Claude's simulator recordings (format "sim-messages/1", Mythastria
// docs/development/SIM_MESSAGES.md) for the Isles Table client. Merge handoff 2026-10-19, step 3.
//
// The simulator stays the rules authority: this module never rolls dice, moves tokens, applies damage or
// asks the Rust kernel anything. It checks the recording, turns it into frames to draw, and reports
// what it cannot show. Pure functions, no DOM: the same code runs in the browser and under Node.
//
// Coordinates: scenario walls/zones and state positions are already in squares (a token at x, y fills
// the square centred there; walls run along the half-square edges). Only the bridge's decision moves
// (action.decisions[].move: x, y, path) are map pixels, 50 per square in the simulator: they are
// divided by 50 here, once, and nothing else is.

export const FORMAT = 'sim-messages/1';
export const SIM_PIXELS_PER_SQUARE = 50;

// What the recording may carry that this client does not draw (yet). Listed per frame, never invented.
const STATE_FIELDS_SHOWN = new Set(['id', 'name', 'side', 'pc', 'x', 'y', 'space_ft', 'hp', 'hp_max', 'ac', 'down',
  'conditions', 'underwater', 'aloft', 'mount', 'dead', 'stable', 'death_saves', 'breath_rounds', 'exhaustion', 'temp_hp',
  'level', 'fly_ft', 'flying']);                                 // fly_ft, flying: 2026-10-19 (fliers drawn raised in 3D)
const ZONE_KINDS_SHOWN = new Set(['water', 'current', 'obscured', 'shade', 'sunlit', 'drop', 'cover']);

export class ReplayError extends Error {}

function fail(text) { throw new ReplayError(text); }
const isNum = v => typeof v === 'number' && Number.isFinite(v);

// ---------------------------------------------------------------------------------------- parsing
export function parseRecording(input) {
  const messages = typeof input === 'string' ? JSON.parse(input) : input;
  if (!Array.isArray(messages) || !messages.length) fail('A recording is a JSON list of messages.');
  const [scenario, ...rest] = messages;
  if (scenario?.type !== 'scenario') fail('The first message must be the scenario.');
  if (scenario.format !== FORMAT) fail(`Unsupported format "${scenario.format}" (this client reads ${FORMAT}).`);
  const map = scenario.map;
  if (!map || !isNum(map.cols) || !isNum(map.rows)) fail('The scenario has no map grid.');
  for (const w of map.walls ?? []) {
    if (!Array.isArray(w.points) || w.points.length < 2 || !w.points.every(p => isNum(p[0]) && isNum(p[1])))
      fail(`Wall ${w.id} has unreadable points.`);
  }
  // Order: state (before a turn), action, result ... then a final state.
  const turns = [];
  let i = 0, before = null;
  for (; i < rest.length; i++) {
    const m = rest[i];
    if (m.type === 'state') {
      checkState(m, i + 1);
      if (before) turns.push({ before, action: null, result: null });
      before = m;
    } else if (m.type === 'action') {
      if (!before) fail(`Message ${i + 1}: an action without a state before it.`);
      const r = rest[i + 1];
      if (r?.type !== 'result') fail(`Message ${i + 1}: an action must be followed by its result.`);
      if (r.actor !== m.actor || r.round !== m.round) fail(`Message ${i + 2}: the result is not for that action.`);
      turns.push({ before, action: m, result: r });
      before = null;
      i++;
    } else {
      fail(`Message ${i + 1}: unknown type "${m.type}".`);
    }
  }
  if (!before) fail('The recording must end with the final state.');
  return { scenario, turns, final: before };
}

function checkState(m, index) {
  if (!Array.isArray(m.combatants)) fail(`Message ${index}: a state without combatants.`);
  const ids = new Set();
  for (const c of m.combatants) {
    if (!c.id || ids.has(c.id)) fail(`Message ${index}: a combatant without a unique id.`);
    ids.add(c.id);
    if (!isNum(c.x) || !isNum(c.y) || !isNum(c.hp) || !isNum(c.hp_max)) fail(`Message ${index}: ${c.name} lacks position or hit points.`);
  }
}

// ---------------------------------------------------------------------------------------- units
export function pixelsToSquares(v) { return v / SIM_PIXELS_PER_SQUARE; }

export function decisionMoveSquares(move) {
  if (!move) return null;
  const pt = p => [pixelsToSquares(p[0]), pixelsToSquares(p[1])];
  return {
    x: pixelsToSquares(move.x), y: pixelsToSquares(move.y), feet: move.feet ?? null,
    path: (move.path ?? []).map(pt), opens: move.opens ?? [], squeeze: move.squeeze ?? 0,
  };
}

// ---------------------------------------------------------------------------------------- tokens
export function baseName(name) { return String(name ?? '').replace(/\s+\d+$/, '').trim(); }

// Art never supplies size or rules: a creature gets a registry image only when its name without the number matches
// exactly and the image's footprint equals the creature's space; otherwise null (the client draws a plain marker).
export function tokenFor(combatant, registry) {
  if (!registry || combatant.pc) return { token_id: null, reason: combatant.pc ? 'character: no approved token' : 'no registry' };
  const want = baseName(combatant.name).toLowerCase();
  const t = registry.find(r => String(r.name).toLowerCase() === want);
  if (!t) return { token_id: null, reason: `no token named "${baseName(combatant.name)}"` };
  if (Math.round(t.squares * 5) !== combatant.space_ft) return { token_id: null, reason: `token "${t.name}" is ${t.squares * 5} ft, the creature ${combatant.space_ft} ft` };
  return { token_id: t.id, path: t.path, reason: null };
}

// ---------------------------------------------------------------------------------------- frames
function viewOf(scenario, state, openDoors, registry, round) {
  const map = scenario.map;
  const open = new Set(openDoors ?? []);
  const unsupported = [];
  for (const z of map.zones ?? []) if (!ZONE_KINDS_SHOWN.has(z.kind)) unsupported.push(`zone kind "${z.kind}" (${z.id})`);
  const combatants = state.combatants.map(c => {
    for (const k of Object.keys(c)) if (!STATE_FIELDS_SHOWN.has(k)) unsupported.push(`${c.name}: field "${k}"`);
    const tok = tokenFor(c, registry);
    return { ...structuredClone(c), token_id: tok.token_id, token_path: tok.path ?? null, token_note: tok.reason };
  });
  return {
    replay: true,
    map: {
      name: map.name, cols: map.cols, rows: map.rows, square_ft: map.square_ft ?? 5,
      walls: (map.walls ?? []).map(w => ({ ...w, open: w.door ? open.has(String(w.id)) : false })),
      zones: structuredClone(map.zones ?? []),
      lighting: structuredClone(map.lighting ?? { ambient: 'bright', lights: [] }),
      ceilings: structuredClone(map.ceilings ?? []),
      ground: map.ground ?? null, ground_cells: structuredClone(map.ground_cells ?? {}),   // REGION-01: an outdoor map's ground
      background: map.background ? structuredClone(map.background) : null,   // VIEW-01: an imported map's picture
      wall_cells: structuredClone(map.wall_cells ?? []),             // MAP RULE (GM 2026-10-20): wall squares, drawn as stone
      props: structuredClone(map.props ?? []),                       // 2026-10-19: display-only props (kind, x, y, rot, label)                 // 2026-10-19: each room's ceiling (ft, null = open sky)
    },
    state: { round: state.round ?? round ?? null, active: state.active ?? null, combatants },
    offers: [], movement_targets: [], action_available: false,     // read-only: nothing can be chosen
    unsupported: [...new Set(unsupported)],
  };
}

// One frame per state in the recording: the situation before each turn, then the end. Each turn frame carries the
// action (with decision moves in squares) and the result as recorded. The open doors are the state's own list, or,
// for older recordings without it, the result's map_changes.
export function buildFrames(recording, registry = null) {
  const { scenario, turns, final } = recording;
  const frames = [];
  let doors = turns[0]?.before?.open_doors ?? final.open_doors ?? [];
  for (const [n, t] of turns.entries()) {
    if (Array.isArray(t.before.open_doors)) doors = t.before.open_doors;
    const action = t.action && {
      ...structuredClone(t.action),
      decisions: (t.action.decisions ?? []).map(d => ({ ...structuredClone(d), move_squares: decisionMoveSquares(d.move) })),
    };
    frames.push({
      index: n, kind: 'turn', label: `Round ${t.before.round ?? '?'}: ${t.action?.actor_name ?? 'no action recorded'}`,
      view: viewOf(scenario, t.before, doors, registry), action, result: t.result && structuredClone(t.result),
    });
    const md = t.result?.map_changes?.open_doors;
    if (md) doors = md[1];
  }
  if (Array.isArray(final.open_doors)) doors = final.open_doors;
  frames.push({ index: turns.length, kind: 'final', label: 'End of the recording', view: viewOf(scenario, final, doors, registry),
    action: null, result: null });
  return frames;
}

// ---------------------------------------------------------------------------------------- consistency
// The recorded result says what changed; the next state says where things stand. They must agree: the replay shows
// the recording's own truth and never recomputes it. Returns a list of disagreements (empty when consistent).
const COMPARED = ['x', 'y', 'hp', 'down', 'conditions', 'aloft', 'mount', 'underwater'];
export function checkConsistency(recording) {
  const problems = [];
  const { turns, final } = recording;
  for (const [n, t] of turns.entries()) {
    if (!t.result) continue;
    const next = turns[n + 1]?.before ?? final;
    const now = new Map(next.combatants.map(c => [c.id, c]));
    for (const ch of t.result.changes ?? []) {
      const c = now.get(ch.id);
      if (!c) { problems.push(`turn ${n + 1}: ${ch.name} changed but is not in the next state`); continue; }
      for (const [field, pair] of Object.entries(ch.changed ?? {})) {
        if (!COMPARED.includes(field) || !Array.isArray(pair)) continue;
        if (JSON.stringify(c[field]) !== JSON.stringify(pair[1]))
          problems.push(`turn ${n + 1}: ${ch.name} ${field} is ${JSON.stringify(c[field])}, the result says ${JSON.stringify(pair[1])}`);
      }
    }
    const md = t.result.map_changes?.open_doors;
    if (md && Array.isArray(next.open_doors) && JSON.stringify([...next.open_doors].sort()) !== JSON.stringify([...md[1]].sort()))
      problems.push(`turn ${n + 1}: open doors ${JSON.stringify(next.open_doors)}, the result says ${JSON.stringify(md[1])}`);
  }
  return problems;
}
