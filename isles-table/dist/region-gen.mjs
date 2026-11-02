// MAPGEN-01 (GM 2026-10-22: "future developing for ... automatic map making based on algorithmic design preferences";
// then "the design preference seems do-able now for outdoor maps and their corresponding battle-maps, and afterwards
// adventure indoor maps and 'dungeons'"). Step 1: a region made from the GM's design preferences: size, climate, land
// and sea, how rugged, wooded and wet, settlements joined by roads, rivers running downhill, and sites (dungeons, caves,
// ruins, lairs) waiting for the indoor generator. Seeded: the same preferences and seed give the same region. Pure logic
// here (tests: region_gen_tests.mjs); renderRegionPicture() draws it in the table's miniature style on a canvas, so a
// generated region needs no picture of its own. Terrain is display and travel only (SRD 5.2.1 pace in hex-region.mjs).
import { newRegion, key, unkey, neighbors, distance, hexCorners, hexCenter, placeParty } from './hex-region.mjs';

export const CLIMATES = { temperate: 'Temperate', cold: 'Cold', warm: 'Warm', arid: 'Arid', tropical: 'Tropical' };
export const LANDS = { inland: 'Inland', coast: 'A coast', islands: 'Islands', lakes: 'Lakes' };
export const SIZES = { small: [24, 18], medium: [48, 36], large: [96, 72] };      // miles across and down
export const DEFAULT_PREFS = { size: 'medium', climate: 'temperate', land: 'coast', rugged: 40, forest: 50, wet: 40,
  settlements: 5, sites: 4, roads: true, seed: 1 };
const SQ3 = Math.sqrt(3);

// ------------------------------------------------------------------ seeded randomness and smooth noise
export function rng(seed) {
  let h = 1779033703 ^ String(seed).length;
  for (const ch of String(seed)) { h = Math.imul(h ^ ch.charCodeAt(0), 3432918353); h = (h << 13) | (h >>> 19); }
  let a = h >>> 0;
  return () => { a |= 0; a = (a + 0x6D2B79F5) | 0; let t = Math.imul(a ^ (a >>> 15), 1 | a); t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t; return ((t ^ (t >>> 14)) >>> 0) / 4294967296; };
}
function noise2(seed) {
  const r = rng(seed), table = new Float64Array(4096);
  for (let i = 0; i < table.length; i++) table[i] = r();
  const at = (x, y) => table[((x * 374761393 + y * 668265263) >>> 0) % 4096];
  const smooth = t => t * t * (3 - 2 * t);
  const value = (x, y) => {
    const x0 = Math.floor(x), y0 = Math.floor(y), fx = smooth(x - x0), fy = smooth(y - y0);
    const a = at(x0, y0), b = at(x0 + 1, y0), c = at(x0, y0 + 1), d = at(x0 + 1, y0 + 1);
    return a + (b - a) * fx + (c - a) * fy + (a - b - c + d) * fx * fy;
  };
  return (x, y, octaves = 4) => { let s = 0, amp = 1, f = 1, norm = 0; for (let o = 0; o < octaves; o++) { s += value(x * f, y * f) * amp; norm += amp; amp *= .5; f *= 2; } return s / norm; };
}
const quantile = (values, q) => { const v = [...values].sort((a, b) => a - b); return v[Math.min(v.length - 1, Math.max(0, Math.floor(q * v.length)))]; };

// ------------------------------------------------------------------ the region's hexes: a rectangle of 1-mile hexes
/** The hexes of a W x H mile region: flat-top columns, each column offset by half a hex (so the region is a rectangle). */
export function regionHexes(widthMiles, heightMiles) {
  const cols = Math.max(2, Math.round(widthMiles / (1.5 / SQ3))), rows = Math.max(2, heightMiles), out = [];
  for (let q = 0; q < cols; q++) for (let row = 0; row < rows; row++) out.push({ q, r: row - Math.floor(q / 2), x: q * 1.5 / SQ3, y: row + (q % 2) / 2 });
  return { cols, rows, hexes: out };
}

// 2026-10-22 (GM: "Don't give the places names. Number them"; "allow the places to be named on the map manually"):
// a made region's places are numbered; the GM names them. Shown as the name once given, else the number.
export const placeLabel = p => (p?.name || '').trim() || String(p?.number ?? '?');
export function nextNumber(locations) { return Math.max(0, ...locations.map(l => Number(l.number) || 0)) + 1; }

/** Make a region from the GM's design preferences. Returns a region (hex-region.mjs format) with terrain, places (towns,
 *  villages, sites), roads and rivers, and `design` (the preferences, kept so it can be made again). */
export function generateRegion(prefs = {}) {
  const p = { ...DEFAULT_PREFS, ...prefs };
  const [W, H] = Array.isArray(p.size) ? p.size : SIZES[p.size] ?? SIZES.medium;
  const r = rng('region:' + p.seed), elev = noise2('e:' + p.seed), moist = noise2('m:' + p.seed);
  const { cols, rows, hexes } = regionHexes(W, H);
  const scale = Math.max(W, H) / 3.2;
  const land = p.land in LANDS ? p.land : 'coast';
  const seaSide = Math.floor(r() * 4);                                  // the coast's sea: north, east, south or west
  const isles = Array.from({ length: Math.max(2, Math.round(W * H / 500)) }, () => ({ x: (.15 + r() * .7) * W, y: (.15 + r() * .7) * H, rad: (.12 + r() * .14) * Math.max(W, H) }));
  const E = new Map(), M = new Map();
  for (const h of hexes) {
    let e = elev(h.x / scale, h.y / scale);
    if (land === 'coast') {
      const d = [h.y / H, 1 - h.x / W, 1 - h.y / H, h.x / W][seaSide];   // 0 at the sea's edge, 1 across
      e = e * .55 + d * .65 - .1;
    } else if (land === 'islands') {
      const best = Math.max(...isles.map(i => 1 - Math.hypot(h.x - i.x, h.y - i.y) / i.rad));
      e = e * .45 + Math.max(0, best) * .9 - .05;
    }
    E.set(key(h.q, h.r), e);
    M.set(key(h.q, h.r), moist(h.x / scale * 1.3 + 50, h.y / scale * 1.3 + 50) + (p.wet - 50) / 160);
  }
  const ev = [...E.values()];
  const waterShare = { inland: .02 + p.wet / 2500, lakes: .07 + p.wet / 900, coast: .32, islands: .58 }[land];
  const sea = quantile(ev, waterShare);
  const landKeys = [...E.keys()].filter(k => E.get(k) > sea);
  const landE = landKeys.map(k => E.get(k));
  const mountainAt = quantile(landE, 1 - p.rugged / 100 * .16 - .005), hillAt = quantile(landE, 1 - p.rugged / 100 * .38 - .03);
  const terrain = {};
  for (const k of E.keys()) if (E.get(k) <= sea) terrain[k] = 'water';
  for (const k of landKeys) { const e = E.get(k); if (e >= mountainAt) terrain[k] = 'mountains'; else if (e >= hillAt) terrain[k] = 'hills'; }
  const low = landKeys.filter(k => !terrain[k]);
  const lowM = low.map(k => M.get(k));
  const forestShare = Math.min(.85, p.forest / 100 * .65 * ({ arid: .15, cold: .8, tropical: 1.25, warm: .8 }[p.climate] ?? 1));
  const desertShare = { arid: .65, warm: .15 }[p.climate] ?? 0;
  const swampShare = Math.min(.3, p.wet / 100 * .18 * ({ arid: 0, cold: .4, tropical: 1.6, warm: 1.2 }[p.climate] ?? 1));
  const forestAt = quantile(lowM, 1 - forestShare), desertAt = quantile(lowM, desertShare), swampAt = quantile(lowM, 1 - swampShare);
  const nearWater = k => neighbors(...unkey(k)).some(n => terrain[key(...n)] === 'water');
  for (const k of low) {
    const m = M.get(k);
    if (swampShare && m >= swampAt && (nearWater(k) || E.get(k) < sea + .04)) terrain[k] = 'swamp';
    else if (m >= forestAt && forestShare) terrain[k] = 'forest';
    else if (desertShare && m <= desertAt) terrain[k] = 'desert';
  }
  for (const k of landKeys) if ((!terrain[k] || terrain[k] === 'desert') && nearWater(k)) terrain[k] = 'coast';

  // rivers: from high ground downhill to water (a pit becomes a small lake)
  const rivers = [];
  const springs = landKeys.filter(k => terrain[k] === 'mountains' || terrain[k] === 'hills').sort((a, b) => E.get(b) - E.get(a));
  const riverCount = land === 'islands' ? Math.round(p.wet / 50) : Math.round(p.wet / 25) + 1;
  for (let i = 0; i < riverCount && springs.length; i++) {
    const start = springs.splice(Math.floor(r() * Math.min(springs.length, 25)), 1)[0];
    const path = [start], seen = new Set(path);
    let at = start;
    while (terrain[at] !== 'water' && path.length < cols + rows) {
      const next = neighbors(...unkey(at)).map(n => key(...n)).filter(n => E.has(n) && !seen.has(n)).sort((a, b) => E.get(a) - E.get(b))[0];
      if (!next) break;
      if (E.get(next) >= E.get(at)) { if (path.length > 3) terrain[at] = 'water'; break; }   // a pit: a lake where the water gathers
      path.push(next); seen.add(next); at = next;
    }
    if (path.length > 3) rivers.push(path);
  }

  // settlements, spread out, by water and on open ground
  const all = new Set(E.keys());
  const open = landKeys.filter(k => ['coast', undefined, 'forest', 'desert', 'hills'].includes(terrain[k]));
  const riverSet = new Set(rivers.flat());
  const score = k => (riverSet.has(k) ? 2 : 0) + (terrain[k] === 'coast' ? 2 : 0) + (!terrain[k] ? 1 : 0) + r();
  const spread = Math.sqrt(W * H / Math.max(1, p.settlements)) * .75;
  const locations = [];
  const ranked = [...open].sort((a, b) => score(b) - score(a));
  const towns = [];
  for (const k of ranked) {
    if (towns.length >= p.settlements) break;
    if (towns.every(t => distance(unkey(t), unkey(k)) >= spread)) towns.push(k);
  }
  towns.forEach((k, i) => locations.push({ hex: k, number: locations.length + 1, name: '', kind: i === 0 ? 'town' : 'village', map: null,
    note: i === 0 ? 'Town' : 'Village' }));

  // roads: the towns joined (a tree of shortest links), the way round mountains and water
  const roads = [];
  if (p.roads && towns.length > 1) {
    const cost = k => ({ water: Infinity, mountains: 8, swamp: 4, hills: 2.5, forest: 2 }[terrain[k]] ?? 1);
    const joined = [towns[0]], rest = towns.slice(1);
    while (rest.length) {
      let best = null;
      for (const a of joined) for (const b of rest) { const d = distance(unkey(a), unkey(b)); if (!best || d < best[2]) best = [a, b, d]; }
      const path = astar(best[0], best[1], cost, all);
      if (path) { roads.push(path); for (const k of path) if (terrain[k] !== 'water') terrain[k] = 'road'; }
      joined.push(best[1]); rest.splice(rest.indexOf(best[1]), 1);
    }
  }

  // sites for adventures: dungeons, caves, ruins and lairs, away from the towns
  const SITE_GROUND = { mountains: ['cave', 'dungeon', 'lair'], hills: ['dungeon', 'ruin', 'cave'], forest: ['ruin', 'lair'], swamp: ['ruin', 'lair'], desert: ['ruin', 'dungeon'] };
  const wild = landKeys.filter(k => SITE_GROUND[terrain[k]] && towns.every(t => distance(unkey(t), unkey(k)) > 3));
  for (let i = 0; i < p.sites && wild.length; i++) {
    const k = wild.splice(Math.floor(r() * wild.length), 1)[0];
    const kinds = SITE_GROUND[terrain[k]], kind = kinds[Math.floor(r() * kinds.length)];
    locations.push({ hex: k, number: locations.length + 1, name: '', kind: 'site', site: kind, map: null,
      note: `A ${kind}: click it, then Draw this site as indoor maps` });
    for (let j = wild.length - 1; j >= 0; j--) if (distance(unkey(wild[j]), unkey(k)) < 4) wild.splice(j, 1);
  }

  for (const k of Object.keys(terrain)) if (terrain[k] === 'plains') delete terrain[k];
  const pxPerMile = Math.max(12, Math.min(40, Math.floor(2600 / Math.max(cols * 1.5 / SQ3, rows))));
  const s = pxPerMile / SQ3;
  const grid = { pxPerMile, ox: s * 1.2, oy: pxPerMile * .7 };
  let region = { ...newRegion(p.name || 'Generated region'), grid, terrain, locations, rivers, roads,
    size: [Math.ceil(grid.ox + s * 1.5 * (cols - 1) + s * 1.2), Math.ceil(grid.oy + pxPerMile * (rows - .5) + pxPerMile * .7)],
    hexes: { cols, rows }, design: { prefs: p, made: 'MAPGEN-01' } };
  if (towns.length) region = placeParty(region, unkey(towns[0]));
  return region;
}

function astar(from, to, cost, all) {
  const open = [[0, 0, from]], best = new Map([[from, 0]]), came = new Map();
  let guard = 0;
  while (open.length && guard++ < 40000) {
    open.sort((a, b) => a[0] - b[0]);
    const [, g, at] = open.shift();
    if (at === to) { const path = [to]; for (let c = came.get(to); c; c = came.get(c)) path.unshift(c); return path; }
    if (g > best.get(at)) continue;
    for (const n of neighbors(...unkey(at))) {
      const nk = key(...n);
      if (!all.has(nk)) continue;
      const c = cost(nk);
      if (!Number.isFinite(c)) continue;
      const ng = g + c;
      if (ng < (best.get(nk) ?? Infinity)) { best.set(nk, ng); came.set(nk, at); open.push([ng + distance(n, unkey(to)), ng, nk]); }
    }
  }
  return null;
}

/** What a battle on this hex looks like: its terrain, a road through it, a river across it, and the sea's side.
 *  The battle-map builder (Mythastria tools/terrain_battle.py) draws the field from this. */
export function hexContext(region, at) {
  const k = key(...at), t = region.terrain[k] ?? 'plains';
  const SIDE = ['east', 'east', 'north', 'west', 'west', 'south'];       // hex-region DIRS -> the battle map's edge
  const seaDir = neighbors(...at).findIndex(n => region.terrain[key(...n)] === 'water');
  return { terrain: t, road: t === 'road' || (region.roads ?? []).some(rd => rd.includes(k)),
    river: (region.rivers ?? []).some(rv => rv.includes(k)), sea: seaDir >= 0 && t !== 'water' ? SIDE[seaDir] : null };
}

/** The same hex always gives the same battle map: a seed from the region's own seed and the hex. */
export function hexSeed(region, at) {
  const s = `${region.design?.prefs?.seed ?? region.name}:${key(...at)}`;
  let h = 0;
  for (const ch of s) h = (Math.imul(h, 31) + ch.charCodeAt(0)) | 0;
  return (Math.abs(h) % 9973) + 1;
}

// ------------------------------------------------------------------ the picture, in the table's miniature style
const PAINT = { plains: '#9cb86a', road: '#a9b46a', forest: '#4f8a4e', hills: '#a99a63', mountains: '#8d8a84', swamp: '#6d7f55',
  desert: '#dcc58a', coast: '#d9cf9f', water: '#4f86b4' };
const INK = '#2b2620';
const EDGE = [[0, 1], [5, 0], [4, 5], [3, 4], [2, 3], [1, 2]];          // hex-region DIRS -> the two corners of that edge

/** Draw a generated region on a canvas (ctx: CanvasRenderingContext2D sized region.size): ground, glyphs (trees, peaks,
 *  hills, reeds, dunes, waves), the coastline in ink, rivers and roads. Places are drawn by the page as labels. */
export function renderRegionPicture(region, ctx) {
  const g = region.grid, P = g.pxPerMile, r = rng('paint:' + (region.design?.prefs?.seed ?? 1));
  const { cols, rows } = region.hexes;
  const all = [];
  for (let q = 0; q < cols; q++) for (let row = 0; row < rows; row++) all.push([q, row - Math.floor(q / 2)]);
  const tOf = h => region.terrain[key(...h)] ?? 'plains';
  ctx.fillStyle = '#23251f'; ctx.fillRect(0, 0, region.size[0], region.size[1]);   // beyond the region's edge
  for (const h of all) {                                                // ground, a little uneven
    const c = hexCorners(g, ...h), base = PAINT[tOf(h)], k = .92 + r() * .16;
    ctx.fillStyle = shade(base, k);
    ctx.beginPath(); c.forEach((p, i) => i ? ctx.lineTo(...p) : ctx.moveTo(...p)); ctx.closePath(); ctx.fill();
    ctx.strokeStyle = shade(base, k); ctx.lineWidth = 1; ctx.stroke();
  }
  ctx.lineCap = 'round'; ctx.lineJoin = 'round';
  for (const h of all) {                                                // glyphs
    const t = tOf(h), [x, y] = hexCenter(g, ...h), u = P;
    if (t === 'forest') for (let i = 0; i < 3; i++) tree(ctx, x + (r() - .5) * u * .6, y + (r() - .5) * u * .5, u * (.22 + r() * .08));
    else if (t === 'mountains') peak(ctx, x + (r() - .5) * u * .2, y + u * .2, u * (.45 + r() * .15));
    else if (t === 'hills') { hill(ctx, x - u * .18, y + u * .12, u * .26); hill(ctx, x + u * .16, y + u * .2, u * .22); }
    else if (t === 'swamp') for (let i = 0; i < 3; i++) reeds(ctx, x + (r() - .5) * u * .6, y + (r() - .5) * u * .5, u * .14);
    else if (t === 'desert') { ctx.strokeStyle = shade(PAINT.desert, .78); ctx.lineWidth = u * .04; ctx.beginPath(); ctx.arc(x, y + u * .3, u * .3, Math.PI * 1.15, Math.PI * 1.85); ctx.stroke(); }
    else if (t === 'water' && r() < .35) { ctx.strokeStyle = '#ffffff55'; ctx.lineWidth = u * .04; ctx.beginPath(); ctx.moveTo(x - u * .2, y); ctx.quadraticCurveTo(x - u * .1, y - u * .08, x, y); ctx.quadraticCurveTo(x + u * .1, y + u * .08, x + u * .2, y); ctx.stroke(); }
    else if ((t === 'plains' || t === 'coast') && r() < .3) { ctx.strokeStyle = shade(PAINT[t], .75); ctx.lineWidth = u * .03; ctx.beginPath(); ctx.moveTo(x - u * .08, y); ctx.lineTo(x - u * .04, y - u * .1); ctx.moveTo(x + u * .02, y); ctx.lineTo(x + u * .05, y - u * .12); ctx.stroke(); }
  }
  ctx.strokeStyle = INK; ctx.lineWidth = Math.max(1.2, P * .07);         // the coastline in ink
  ctx.beginPath();
  for (const h of all) {
    if (tOf(h) === 'water') continue;
    const c = hexCorners(g, ...h);
    neighbors(...h).forEach((n, d) => { if (inside(n, cols, rows) && region.terrain[key(...n)] === 'water') { const [a, b] = EDGE[d]; ctx.moveTo(...c[a]); ctx.lineTo(...c[b]); } });
  }
  ctx.stroke();
  const line = (path, color, width, dash = []) => {
    const pts = path.map(k => hexCenter(g, ...unkey(k)));
    ctx.strokeStyle = color; ctx.lineWidth = width; ctx.setLineDash(dash); ctx.beginPath();
    pts.forEach((p, i) => { if (!i) ctx.moveTo(...p); else { const m = [(pts[i - 1][0] + p[0]) / 2, (pts[i - 1][1] + p[1]) / 2]; ctx.quadraticCurveTo(...pts[i - 1], ...m); } });
    ctx.lineTo(...pts.at(-1)); ctx.stroke(); ctx.setLineDash([]);
  };
  for (const rv of region.rivers ?? []) { line(rv, INK, P * .2); line(rv, '#5d97c6', P * .13); }
  for (const rd of region.roads ?? []) line(rd, '#7a5a32', P * .1, [P * .25, P * .15]);
}

function inside([q, rr], cols, rows) { const row = rr + Math.floor(q / 2); return q >= 0 && q < cols && row >= 0 && row < rows; }
function shade(hex, k) {
  const n = parseInt(hex.slice(1, 7), 16), c = [n >> 16, (n >> 8) & 255, n & 255].map(v => Math.max(0, Math.min(255, Math.round(v * k))));
  return '#' + c.map(v => v.toString(16).padStart(2, '0')).join('');
}
function tree(ctx, x, y, s) {
  ctx.fillStyle = '#5b3d22'; ctx.fillRect(x - s * .1, y, s * .2, s * .35);
  ctx.fillStyle = '#3f7d43'; ctx.strokeStyle = INK; ctx.lineWidth = Math.max(.8, s * .12);
  ctx.beginPath(); ctx.moveTo(x, y - s * 1.1); ctx.lineTo(x + s * .6, y + s * .1); ctx.lineTo(x - s * .6, y + s * .1); ctx.closePath(); ctx.fill(); ctx.stroke();
}
function peak(ctx, x, y, s) {
  ctx.fillStyle = '#9c978e'; ctx.strokeStyle = INK; ctx.lineWidth = Math.max(1, s * .08);
  ctx.beginPath(); ctx.moveTo(x - s * .7, y); ctx.lineTo(x, y - s); ctx.lineTo(x + s * .7, y); ctx.closePath(); ctx.fill(); ctx.stroke();
  ctx.fillStyle = '#f2efe8'; ctx.beginPath(); ctx.moveTo(x - s * .22, y - s * .68); ctx.lineTo(x, y - s); ctx.lineTo(x + s * .22, y - s * .68); ctx.lineTo(x + s * .05, y - s * .6); ctx.lineTo(x - s * .07, y - s * .7); ctx.closePath(); ctx.fill();
}
function hill(ctx, x, y, s) {
  ctx.fillStyle = '#b5a46e'; ctx.strokeStyle = INK; ctx.lineWidth = Math.max(.8, s * .12);
  ctx.beginPath(); ctx.moveTo(x - s, y); ctx.quadraticCurveTo(x, y - s * 1.2, x + s, y); ctx.fill(); ctx.stroke();
}
function reeds(ctx, x, y, s) {
  ctx.strokeStyle = '#3e5a33'; ctx.lineWidth = Math.max(.7, s * .18);
  ctx.beginPath(); for (const dx of [-.5, 0, .5]) { ctx.moveTo(x + dx * s, y); ctx.lineTo(x + dx * s * 1.6, y - s * 1.4); } ctx.stroke();
}
