// REGION-01 (GM 2026-10-20): "we need an overall regional map system. Grids are hexes. They can be 2d only." Uses: overland
// travel, links to tactical maps, exploration and fog, random encounters; "If you've been to places you can fast travel
// without encounters". Scales: "all 3, but they are designated by dotted lines for 1 mile, dashed lines for 6 miles, solid
// lines for 24 miles." Content: a picture with a hex overlay. Pure logic (no page): region-ui.mjs draws it; tests in
// region_tests.mjs. Rules: SRD 5.2.1 travel pace (Fast 4 mph / 30 miles a day, Normal 3 / 24, Slow 2 / 18) and each pace's
// effect; HAZARDS-01 (GM 2026-10-26): the terrain's maximum pace (Gameplay Toolbox "Travel Terrain"; a good road one step
// faster), Extended Travel past 8 hours and High Altitude (each hour counts as 2), and the encounter distance by terrain.
// Everything else (encounter odds and tables, sight) is the GM's setting, not a rule.

export const FORMAT = 'region-map/1';
export const SCALES = [{ miles: 1, dash: 'dotted' }, { miles: 6, dash: 'dashed' }, { miles: 24, dash: 'solid' }];
export const PACES = {
  fast: { mph: 4, label: 'Fast', effect: 'Disadvantage on Wisdom (Perception or Survival) and Dexterity (Stealth) checks' },
  normal: { mph: 3, label: 'Normal', effect: 'Disadvantage on Dexterity (Stealth) checks' },
  slow: { mph: 2, label: 'Slow', effect: 'Advantage on Wisdom (Perception or Survival) checks' } };
export const PACE_ORDER = ['slow', 'normal', 'fast'];
export const HOURS_PER_DAY = 8;          // a day's travel (SRD 5.2.1: 8 hours; past that, Extended Travel: a Constitution save each hour)
export const MAX_TRAVEL_HOURS = 24;      // a pushed day (Extended Travel) stops at 24 hours of travel
export const WATCH_HOURS = 4;            // one random-encounter check per 4 hours of travel (the GM can change the odds)

// Terrain: its SRD 5.2.1 maximum pace (Travel Terrain: Grassland Fast; Coastal, Desert, Forest, Hill Normal; Mountain and
// Swamp Slow; a good road one step faster than Normal) and encounter distance; impassable on foot (open water: a vessel's
// speed, not a pace); sight: how many 1-mile hexes around are seen (the GM's setting). `difficult`: rough going on the map.
export const TERRAIN = {
  road: { label: 'Road', color: '#c9a76a', difficult: false, sight: 1, maxPace: 'fast', srd: 'a good road' },
  plains: { label: 'Plains', color: '#9dbb6a', difficult: false, sight: 2, maxPace: 'fast', srd: 'Grassland', distance: [6, 6] },
  forest: { label: 'Forest', color: '#3f7a46', difficult: true, sight: 0, maxPace: 'normal', srd: 'Forest', distance: [2, 8] },
  hills: { label: 'Hills', color: '#a88d5a', difficult: true, sight: 2, maxPace: 'normal', srd: 'Hill', distance: [2, 10] },
  mountains: { label: 'Mountains', color: '#8a8a8a', difficult: true, sight: 3, maxPace: 'slow', srd: 'Mountain', distance: [4, 10] },
  swamp: { label: 'Swamp', color: '#5f7550', difficult: true, sight: 1, maxPace: 'slow', srd: 'Swamp', distance: [2, 8] },
  desert: { label: 'Desert', color: '#d9c27e', difficult: false, sight: 2, maxPace: 'normal', srd: 'Desert', distance: [6, 6] },
  coast: { label: 'Coast', color: '#d6cfa3', difficult: false, sight: 2, maxPace: 'normal', srd: 'Coastal', distance: [2, 10] },
  water: { label: 'Open water', color: '#4a79a6', difficult: false, sight: 2, impassable: true, srd: 'Waterborne', distance: [6, 6] },
};
export const DEFAULT_TERRAIN = 'plains';

const SQ3 = Math.sqrt(3);
export const key = (q, r) => `${q},${r}`;
export const unkey = k => k.split(',').map(Number);

/** A new, empty region (the picture added later). */
export function newRegion(name = 'Region') {
  return { format: FORMAT, name, picture: null, grid: { pxPerMile: 40, ox: 0, oy: 0 }, terrain: {}, locations: [],
    party: { at: null, day: 1, hour: 8, pace: 'normal' }, visited: [], revealed: [], log: [],
    encounters: { chance: 3, tables: {} } };   // chance: an encounter on a d20 roll of (21 - chance) or more per watch
}

// ------------------------------------------------------------------ flat-top hexes, axial coordinates (q, r)
/** The hex size (centre to corner) in pixels for a grid of `miles` hexes: neighbouring centres are `miles` apart. */
export const hexSize = (grid, miles = 1) => grid.pxPerMile * miles / SQ3;
export function hexCenter(grid, q, r, miles = 1) {
  const s = hexSize(grid, miles);
  return [grid.ox + s * 1.5 * q, grid.oy + s * SQ3 * (r + q / 2)];
}
function cubeRound(fq, fr) {
  const fs = -fq - fr;
  let q = Math.round(fq), r = Math.round(fr), s = Math.round(fs);
  const dq = Math.abs(q - fq), dr = Math.abs(r - fr), ds = Math.abs(s - fs);
  if (dq > dr && dq > ds) q = -r - s; else if (dr > ds) r = -q - s;
  return [q, r];
}
export function hexAt(grid, x, y, miles = 1) {
  const s = hexSize(grid, miles), px = (x - grid.ox) / s, py = (y - grid.oy) / s;
  return cubeRound(2 / 3 * px, -1 / 3 * px + SQ3 / 3 * py);
}
export function hexCorners(grid, q, r, miles = 1) {
  const [cx, cy] = hexCenter(grid, q, r, miles), s = hexSize(grid, miles);
  return [0, 1, 2, 3, 4, 5].map(i => [cx + s * Math.cos(Math.PI / 3 * i), cy + s * Math.sin(Math.PI / 3 * i)]);
}
export const DIRS = [[1, 0], [1, -1], [0, -1], [-1, 0], [-1, 1], [0, 1]];
export const neighbors = (q, r) => DIRS.map(([dq, dr]) => [q + dq, r + dr]);
export const distance = (a, b) => (Math.abs(a[0] - b[0]) + Math.abs(a[0] + a[1] - b[0] - b[1]) + Math.abs(a[1] - b[1])) / 2;
export function hexesWithin(c, n) {
  const out = [];
  for (let dq = -n; dq <= n; dq++) for (let dr = Math.max(-n, -dq - n); dr <= Math.min(n, -dq + n); dr++) out.push([c[0] + dq, c[1] + dr]);
  return out;
}

/** Every hex of one scale that touches a picture of width x height pixels (to draw its grid). */
export function hexesCovering(grid, width, height, miles = 1) {
  const s = hexSize(grid, miles), out = [];
  const qs = [hexAt(grid, -s * 2, 0, miles)[0], hexAt(grid, width + s * 2, 0, miles)[0]];
  for (let q = Math.min(...qs) - 1; q <= Math.max(...qs) + 1; q++) {
    const top = hexAt(grid, grid.ox + s * 1.5 * q, -s * 2, miles)[1], bottom = hexAt(grid, grid.ox + s * 1.5 * q, height + s * 2, miles)[1];
    for (let r = Math.min(top, bottom) - 1; r <= Math.max(top, bottom) + 1; r++) {
      const [cx, cy] = hexCenter(grid, q, r, miles);
      if (cx > -s && cx < width + s && cy > -s && cy < height + s) out.push([q, r]);
    }
  }
  return out;
}

/** One SVG path for a whole grid (all hex outlines of one scale): one element, however large the map. */
export function gridPath(grid, width, height, miles = 1) {
  return hexesCovering(grid, width, height, miles).map(([q, r]) =>
    'M' + hexCorners(grid, q, r, miles).map(p => p.map(v => v.toFixed(1)).join(' ')).join('L') + 'Z').join('');
}
export function hexesPath(grid, keys) {
  return [...keys].map(k => { const [q, r] = unkey(k); return 'M' + hexCorners(grid, q, r).map(p => p.map(v => v.toFixed(1)).join(' ')).join('L') + 'Z'; }).join('');
}

// ------------------------------------------------------------------ aligning the grid to the picture
/** The picture has hexes printed on it: the centre of one 1-mile hex, and the centre of another `steps` hexes straight
 *  across (any direction): the grid that puts hex 0,0 on the first. */
export function gridFromCentres(a, b, steps) {
  const px = Math.hypot(b[0] - a[0], b[1] - a[1]);
  if (!(steps > 0) || !(px > 0)) throw new Error('Pick two different hex centres and the number of hexes between them.');
  return { pxPerMile: px / steps, ox: a[0], oy: a[1] };
}
/** No printed hexes: two points a known distance apart (a survey); hex 0,0 at the first point. */
export function gridFromSurvey(a, b, miles) {
  const px = Math.hypot(b[0] - a[0], b[1] - a[1]);
  if (!(miles > 0) || !(px > 0)) throw new Error('Pick two different points and the miles between them.');
  return { pxPerMile: px / miles, ox: a[0], oy: a[1] };
}
export const nudgeGrid = (grid, dx = 0, dy = 0, scale = 1) => ({ ...grid, ox: grid.ox + dx, oy: grid.oy + dy, pxPerMile: grid.pxPerMile * scale });

// ------------------------------------------------------------------ travel
export const terrainOf = (region, k) => TERRAIN[region.terrain[k]] ? region.terrain[k] : DEFAULT_TERRAIN;
/** The pace the party keeps in a hex: the one chosen, or slower where the terrain's maximum pace says so. */
export function paceIn(region, k, pace = region.party.pace) {
  const most = TERRAIN[terrainOf(region, k)].maxPace ?? 'fast';
  return PACE_ORDER.indexOf(pace) > PACE_ORDER.indexOf(most) ? most : pace;
}
/** Hours to cross one 1-mile hex at this pace (no faster than the terrain allows); null where a party on foot cannot go. */
export function hexHours(region, k, pace = region.party.pace) {
  const t = TERRAIN[terrainOf(region, k)];
  if (t.impassable) return null;
  return 1 / PACES[paceIn(region, k, pace)].mph;
}
/** SRD 5.2.1 High Altitude (10,000 feet or higher; here: the region's mountain hexes, when the GM says the region is that
 *  high): each hour of travel there counts as 2 hours toward the day's 8. */
export const highUp = (region, k) => !!region.environment?.altitude && terrainOf(region, k) === 'mountains';
/** The region's weather as the adventure day's hazard names (sim/hazards.py WEATHER). */
export function regionWeather(region) {
  const e = region.environment ?? {};
  return [e.cold && 'extreme_cold', e.heat && 'extreme_heat', e.wind && (e.sand ? 'sandstorm' : 'strong_wind'), e.rain && 'heavy_precipitation'].filter(Boolean);
}

/** The quickest route (in hours) from one hex to another, through hexes a party can walk; `only` limits it to a set of
 *  hex keys (fast travel: places already visited). Returns {path: [[q, r]...], hours} or null. */
export function route(region, from, to, { pace = region.party.pace, only = null, limit = 6000 } = {}) {
  const goal = key(...to), start = key(...from);
  if (start === goal) return { path: [from], hours: 0 };
  const allowed = k => (only ? only.has(k) : true) && hexHours(region, k, pace) != null;
  if (!allowed(goal)) return null;
  const open = [[distance(from, to) / PACES[pace].mph, 0, from]], best = new Map([[start, 0]]), came = new Map();
  let seen = 0;
  while (open.length && seen++ < limit) {
    open.sort((a, b) => a[0] - b[0]);
    const [, g, at] = open.shift(), k = key(...at);
    if (k === goal) {
      const path = [to];
      for (let c = came.get(goal); c; c = came.get(key(...c))) path.unshift(c);
      return { path, hours: +g.toFixed(3) };
    }
    if (g > best.get(k)) continue;
    for (const n of neighbors(...at)) {
      const nk = key(...n);
      if (!allowed(nk)) continue;
      const ng = g + hexHours(region, nk, pace);
      if (ng < (best.get(nk) ?? Infinity)) { best.set(nk, ng); came.set(nk, at); open.push([ng + distance(n, to) / PACES[pace].mph, ng, n]); }
    }
  }
  return null;
}

/** The hexes the party sees from a hex: around it as far as its terrain lets them (forest: only that hex). */
export function seenFrom(region, at) {
  return hexesWithin(at, TERRAIN[terrainOf(region, key(...at))].sight).map(h => key(...h));
}

/** SRD 5.2.1 Travel Terrain: how far away an encounter starts (dice x 10 feet), or null (a road: the land around it). */
export function encounterDistance(t, roll) {
  const d = TERRAIN[t]?.distance;
  if (!d) return null;
  let n = 0; for (let i = 0; i < d[0]; i++) n += roll(d[1]);
  return { dice: `${d[0]}d${d[1]} × 10 feet`, feet: n * 10 };
}

/** The next morning, 08:00: a night's rest ends the travel day. */
export function nextMorning(party) {
  return { day: party.hour < 8 ? party.day : party.day + 1, hour: 8, today: 0, sinceWatch: 0 };
}

/** Advance the clock by hours: {day, hour}. */
export function addHours(party, hours) {
  const total = party.hour + hours, day = party.day + Math.floor(total / 24);
  return { day, hour: total % 24 };                 // exact; rounded only when shown
}
export function clockText(p) {
  const m = Math.round(p.hour * 60), day = p.day + Math.floor(m / 1440), h = Math.floor(m / 60) % 24;
  return `Day ${day}, ${String(h).padStart(2, '0')}:${String(m % 60).padStart(2, '0')}`;
}

/** Travel along a route, hex by hex: the clock runs, the party sees around each hex, and every full watch (4 hours) on the
 *  road outside fast travel rolls for an encounter in that hex's terrain (d20 >= 21 - chance; `roll` gives the d20 and
 *  picks from the table). Stops at the first encounter. Returns the new region and what happened. Nothing is mutated.
 *  HAZARDS-01: `push` (Extended Travel) goes on past 8 hours of travel in a day (to 24); High Altitude hours count double
 *  toward the day's hours. The result says the clock hours, the day's travel hours before and after, and the paces kept,
 *  for the adventure day (the saves are rolled there: sim/hazards.py travel). */
export function travel(region, path, { fast = false, push = false, roll = sides => 1 + Math.floor(Math.random() * sides) } = {}) {
  const r = structuredClone(region), events = [];
  const visited = new Set(r.visited), revealed = new Set(r.revealed);
  let since = r.party.sinceWatch ?? 0, stopped = null, clock = 0;
  const todayBefore = r.party.today ?? 0, paces = new Set();
  for (let i = 1; i < path.length; i++) {
    const k = key(...path[i]), h = hexHours(r, k);
    if (h == null) { stopped = 'The way is blocked: open water.'; break; }
    const counts = h * (highUp(r, k) ? 2 : 1);                  // High Altitude: an hour there counts as 2
    const today = r.party.today ?? 0;
    const limit = push && !fast ? MAX_TRAVEL_HOURS : HOURS_PER_DAY;
    if (today + counts > limit + 1e-9) {                        // a travel day is 8 hours (pushed: 24)
      if (!fast) { stopped = push ? `${MAX_TRAVEL_HOURS} hours of travel today: rest until morning.` : `The day's travel is done (${HOURS_PER_DAY} hours). Rest until morning, push on (Extended Travel), then travel on.`; break; }
      const night = nextMorning(r.party), wait = (night.day - r.party.day) * 24 + night.hour - r.party.hour;
      clock += wait;
      Object.assign(r.party, night);                           // fast travel: the nights pass on the way
    }
    r.party.today = (r.party.today ?? 0) + counts;
    clock += h;
    paces.add(paceIn(r, k));
    Object.assign(r.party, addHours(r.party, h));
    r.party.at = path[i];
    visited.add(k);
    for (const s of seenFrom(r, path[i])) revealed.add(s);
    if (fast) continue;
    since += h;
    while (since >= WATCH_HOURS) {
      since -= WATCH_HOURS;
      const d = roll(20), t = terrainOf(r, k);
      if (d >= 21 - (r.encounters?.chance ?? 3)) {
        const table = r.encounters?.tables?.[t] ?? [];
        const what = table.length ? table[roll(table.length) - 1] : `an encounter in the ${TERRAIN[t].label.toLowerCase()} (the GM decides)`;
        const pace = paceIn(r, k);
        events.push({ kind: 'encounter', at: path[i], terrain: t, d20: d, text: what, when: clockText(r.party),
          pace, effect: PACES[pace].effect, distance: encounterDistance(t, roll) });
        stopped = 'Encounter';
        break;
      }
      events.push({ kind: 'quiet', at: path[i], d20: d, when: clockText(r.party) });
    }
    if (stopped) break;
  }
  r.party.sinceWatch = fast ? 0 : since;
  r.visited = [...visited]; r.revealed = [...revealed];
  r.log = [...r.log, ...events.filter(e => e.kind === 'encounter').map(e => `${e.when}: ${e.text}`)].slice(-200);
  return { region: r, events, stopped, hours: +clock.toFixed(4), todayBefore: fast ? 0 : todayBefore,
    todayAfter: fast ? 0 : +(r.party.today ?? 0).toFixed(4), paces: [...paces] };
}

/** Fast travel: "If you've been to places you can fast travel without encounters": a route only through visited hexes. */
export function fastRoute(region, to) {
  if (!region.party.at) return null;
  return route(region, region.party.at, to, { only: new Set(region.visited) });
}

/** Place the party (the GM): it sees around it and that hex counts as visited. */
export function placeParty(region, at) {
  const r = structuredClone(region);
  r.party.at = at;
  r.visited = [...new Set([...r.visited, key(...at)])];
  r.revealed = [...new Set([...r.revealed, ...seenFrom(r, at)])];
  return r;
}

/** Check a region read from a file before it is used. */
export function checkRegion(r) {
  if (!r || r.format !== FORMAT) throw new Error('Not a Mythastria region map (format ' + FORMAT + ').');
  if (!(r.grid?.pxPerMile > 0)) throw new Error('The region has no hex grid.');
  for (const [k, t] of Object.entries(r.terrain ?? {})) if (!/^-?\d+,-?\d+$/.test(k) || !TERRAIN[t]) throw new Error('Bad terrain entry ' + k);
  return { ...newRegion(r.name), ...r };
}
