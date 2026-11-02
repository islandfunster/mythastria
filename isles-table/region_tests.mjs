// Tests for dist/hex-region.mjs (REGION-01, GM 2026-10-20: a regional hex map, 2D only; 1-mile hexes dotted, 6-mile
// dashed, 24-mile solid; travel, links to tactical maps, fog, random encounters, fast travel where the party has been).
// Browser runner: tests/replay_tests.html.
import { newRegion, hexCenter, hexAt, distance, neighbors, hexesWithin, gridFromCentres, gridFromSurvey, hexHours, route,
  travel, fastRoute, placeParty, seenFrom, key, nextMorning, SCALES, PACES, checkRegion, gridPath, clockText, FORMAT, paceIn,
  regionWeather } from './dist/hex-region.mjs';

function assert(cond, text) { if (!cond) throw new Error('FAILED: ' + text); }
const near = (a, b, e = 1e-6) => Math.abs(a - b) < e;

export function run() {
  const results = [];
  const test = (name, fn) => { try { fn(); results.push([name, true, '']); } catch (e) { results.push([name, false, e.message]); } };
  const grid = { pxPerMile: 30, ox: 100, oy: 80 };

  test('region: three grid scales, 1 mile dotted, 6 dashed, 24 solid (GM)', () => {
    assert(SCALES.map(s => `${s.miles}:${s.dash}`).join() === '1:dotted,6:dashed,24:solid', 'the scales');
    const a = hexCenter(grid, 0, 0), b = hexCenter(grid, 1, 0), c = hexCenter(grid, 0, 1);
    assert(near(Math.hypot(b[0] - a[0], b[1] - a[1]), 30) && near(Math.hypot(c[0] - a[0], c[1] - a[1]), 30), 'neighbours 1 mile apart');
    const big = hexCenter(grid, 1, 0, 6);
    assert(near(Math.hypot(big[0] - a[0], big[1] - a[1]), 180), 'a 6-mile hex: neighbours 6 miles apart');
    assert(gridPath(grid, 300, 200, 1).split('Z').length > gridPath(grid, 300, 200, 6).split('Z').length, 'more 1-mile hexes than 6-mile ones');
  });

  test('region: a point finds its hex; distances count hexes', () => {
    for (const h of [[0, 0], [3, -1], [-2, 4]]) { const [x, y] = hexCenter(grid, ...h); const back = hexAt(grid, x + 3, y - 2); assert(back[0] === h[0] && back[1] === h[1], 'hex ' + h); }
    assert(distance([0, 0], [3, -1]) === 3 && neighbors(0, 0).every(n => distance([0, 0], n) === 1), 'distance');
    assert(hexesWithin([0, 0], 1).length === 7 && hexesWithin([0, 0], 2).length === 19, 'rings');
  });

  test('region: the grid is aligned from printed hex centres, or surveyed from two points a known distance apart', () => {
    const g = gridFromCentres([10, 10], [10, 130], 4);
    assert(near(g.pxPerMile, 30) && g.ox === 10 && g.oy === 10, 'centres: 4 hexes across 120 px = 30 px a mile');
    assert(near(gridFromSurvey([0, 0], [300, 400], 10).pxPerMile, 50), 'survey: 500 px for 10 miles');
    let threw = false; try { gridFromSurvey([1, 1], [1, 1], 5); } catch { threw = true; }
    assert(threw, 'the same point twice is refused');
  });

  test("region: travel pace by SRD 5.2.1 (fast 4, normal 3, slow 2 mph), the terrain's maximum pace, water blocks", () => {
    const r = newRegion(); r.terrain[key(1, 0)] = 'forest'; r.terrain[key(2, 0)] = 'water'; r.terrain[key(3, 0)] = 'mountains'; r.terrain[key(4, 0)] = 'road';
    assert(PACES.fast.mph === 4 && PACES.normal.mph === 3 && PACES.slow.mph === 2, 'paces');
    assert(near(hexHours(r, key(0, 1), 'normal'), 1 / 3) && near(hexHours(r, key(1, 0), 'normal'), 1 / 3), 'plains, forest at Normal');
    assert(near(hexHours(r, key(0, 1), 'fast'), 1 / 4) && near(hexHours(r, key(1, 0), 'fast'), 1 / 3), 'Grassland Fast; Forest at most Normal');
    assert(near(hexHours(r, key(3, 0), 'fast'), 1 / 2) && paceIn(r, key(3, 0), 'normal') === 'slow', 'Mountain: Slow');
    assert(near(hexHours(r, key(4, 0), 'fast'), 1 / 4) && paceIn(r, key(4, 0), 'slow') === 'slow', 'a good road: Fast; Slow when chosen');
    assert(hexHours(r, key(2, 0)) === null, 'open water: not on foot');
    assert(/Stealth/.test(PACES.normal.effect) && /Advantage on Wisdom/.test(PACES.slow.effect) && /Perception or Survival\) and Dexterity/.test(PACES.fast.effect), "each pace's effect");
  });

  test("region: Extended Travel past 8 hours, High Altitude counts double, the encounter's distance and pace (HAZARDS-01)", () => {
    let r = placeParty(newRegion(), [0, 0]);
    const path = route(r, [0, 0], [30, 0]).path;                   // 30 miles at 3 mph: 10 hours
    const pushed = travel(r, path, { roll: () => 1, push: true });
    assert(pushed.region.party.at.join() === '30,0' && !pushed.stopped, 'pushed on past 8 hours');
    assert(near(pushed.hours, 10, 1e-3) && pushed.todayBefore === 0 && near(pushed.todayAfter, 10, 1e-3), 'the hours for the adventure day');
    assert(pushed.paces.join() === 'normal', 'the pace kept');
    const high = placeParty(newRegion(), [0, 0]);
    for (const h of hexesWithin([0, 0], 8)) if (h[0] || h[1]) high.terrain[key(...h)] = 'mountains';   // all around
    high.environment = { altitude: true };
    const climb = travel(high, route(high, [0, 0], [4, 0]).path, { roll: () => 1 });
    assert(near(climb.hours, 2, 1e-3) && near(climb.todayAfter, 4, 1e-3), '2 hours in the mountains count as 4');
    assert(regionWeather({ environment: { cold: true, wind: true, sand: true } }).join() === 'extreme_cold,sandstorm', 'weather names');
    r.encounters.tables.forest = ['Wolves'];
    for (let q = 1; q <= 12; q++) r.terrain[key(q, 0)] = 'forest';
    const met = travel(r, route(r, [0, 0], [12, 0]).path, { roll: s => s === 20 ? 20 : s === 8 ? 4 : 1 });
    const e = met.events.at(-1);
    assert(e.kind === 'encounter' && e.distance.dice === '2d8 × 10 feet' && e.distance.feet === 80, 'Forest: 2d8 x 10 feet');
    assert(e.pace === 'normal' && /Stealth/.test(e.effect), "the pace's effect on the encounter");
  });

  test('region: a route takes the quickest way round forest and water', () => {
    const r = newRegion();
    for (const h of [[1, 0], [1, -1]]) r.terrain[key(...h)] = 'forest';
    r.terrain[key(2, -1)] = 'water';
    const rt = route(r, [0, 0], [3, -1]);
    assert(rt && rt.path[0].join() === '0,0' && rt.path.at(-1).join() === '3,-1', 'start and end');
    assert(!rt.path.some(h => key(...h) === '2,-1'), 'never through water');
    assert(near(rt.hours, rt.path.slice(1).reduce((s, h) => s + hexHours(r, key(...h)), 0), 1e-3), 'hours add up');
    assert(route(r, [0, 0], [2, -1]) === null, 'no route into water');
  });

  test('region: travelling runs the clock, reveals what the party sees, and rolls an encounter each 4-hour watch', () => {
    let r = placeParty(newRegion(), [0, 0]);
    assert(r.revealed.includes('2,0') && r.visited.includes('0,0'), 'plains: sees 2 hexes around');
    const path = route(r, [0, 0], [15, 0]).path;                   // 15 miles at 3 mph: 5 hours
    const quiet = travel(r, path, { roll: () => 1 });
    assert(quiet.region.party.at.join() === '15,0' && near(quiet.region.party.hour, 13, 1e-6) && quiet.events.filter(e => e.kind === 'quiet').length === 1, 'one watch, no encounter');
    assert(quiet.region.revealed.includes('16,0') && quiet.region.visited.includes('7,0'), 'seen and visited on the way');
    r.encounters.tables.plains = ['A pack of wolves', 'A merchant caravan'];
    const met = travel(r, path, { roll: s => s === 20 ? 20 : 1 });
    assert(met.stopped === 'Encounter' && met.events.at(-1).text === 'A pack of wolves' && met.region.party.at.join() === '12,0', 'stops where the encounter is (after 4 hours)');
    assert(met.region.log.at(-1).includes('A pack of wolves') && clockText(met.region.party) === 'Day 1, 12:00', 'logged with the time');
  });

  test('region: a travel day is 8 hours: walking stops for the night; fast travel lets the nights pass', () => {
    let r = placeParty(newRegion(), [0, 0]);
    const path = route(r, [0, 0], [30, 0]).path;                   // 30 miles at 3 mph: 10 hours
    const day1 = travel(r, path, { roll: () => 1 });
    assert(day1.region.party.at.join() === '24,0' && /travel is done/.test(day1.stopped), 'stops after 24 miles (8 hours)');
    const rested = { ...day1.region, party: { ...day1.region.party, ...nextMorning(day1.region.party) } };
    assert(rested.party.day === 2 && rested.party.hour === 8 && rested.party.today === 0, 'the next morning');
    const on = travel(rested, route(rested, [24, 0], [30, 0]).path, { roll: () => 1 });
    assert(on.region.party.at.join() === '30,0' && !on.stopped, 'and travels on');
    const fast = travel({ ...r, visited: path.map(h => key(...h)) }, path, { fast: true });
    assert(fast.region.party.at.join() === '30,0' && fast.region.party.day === 2 && near(fast.region.party.hour, 10, 1e-6), 'fast travel: 8 hours, a night, 2 more');
  });

  test('region: fast travel only through places the party has been, and never an encounter (GM)', () => {
    let r = placeParty(newRegion(), [0, 0]);
    r = travel(r, route(r, [0, 0], [6, 0]).path, { roll: () => 1 }).region;
    assert(fastRoute(r, [0, 3]) === null, 'never been there: no fast travel');
    const back = fastRoute(r, [0, 0]);
    assert(back && back.path.every(h => r.visited.includes(key(...h))), 'back along the way it came');
    const done = travel(r, back.path, { fast: true, roll: () => 20 });
    assert(done.region.party.at.join() === '0,0' && !done.events.length, 'no encounter even on a 20');
  });

  test('region: a region file is checked before use', () => {
    assert(checkRegion({ ...newRegion('Isles'), terrain: { '1,2': 'forest' } }).format === FORMAT, 'ok');
    for (const bad of [{}, { format: FORMAT, grid: {} }, { ...newRegion(), terrain: { 'x': 'forest' } }, { ...newRegion(), terrain: { '1,1': 'lava' } }]) {
      let threw = false; try { checkRegion(bad); } catch { threw = true; }
      assert(threw, 'refused: ' + JSON.stringify(bad).slice(0, 40));
    }
    assert(seenFrom({ ...newRegion(), terrain: { '0,0': 'forest' } }, [0, 0]).length === 1, 'in a forest: only that hex');
  });
  return results;
}
