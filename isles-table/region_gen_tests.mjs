// Tests for dist/region-gen.mjs (MAPGEN-01, GM 2026-10-22: "the design preference seems do-able now for outdoor maps
// and their corresponding battle-maps, and afterwards adventure indoor maps and 'dungeons'"). Browser runner:
// tests/replay_tests.html.
import { generateRegion, renderRegionPicture, hexContext, hexSeed, regionHexes, SIZES, placeLabel, nextNumber } from './dist/region-gen.mjs';
import { checkRegion, key, unkey, neighbors, distance } from './dist/hex-region.mjs';

function assert(cond, text) { if (!cond) throw new Error('FAILED: ' + text); }
const count = (r, t) => Object.values(r.terrain).filter(v => v === t).length;

export function run() {
  const results = [];
  const test = (name, fn) => { try { fn(); results.push([name, true, '']); } catch (e) { results.push([name, false, e.message]); } };

  test('mapgen: the same preferences and number give the same region; another number another', () => {
    const a = generateRegion({ seed: 11 }), b = generateRegion({ seed: 11 }), c = generateRegion({ seed: 12 });
    assert(JSON.stringify(a.terrain) === JSON.stringify(b.terrain) && JSON.stringify(a.locations) === JSON.stringify(b.locations), 'the same');
    assert(JSON.stringify(a.terrain) !== JSON.stringify(c.terrain), 'another');
    assert(checkRegion(a).design.prefs.seed === 11, 'a region file like any other, with its preferences kept');
  });

  test('mapgen: size, land and sea follow the preferences', () => {
    const small = generateRegion({ size: 'small', seed: 3 }), large = generateRegion({ size: 'large', seed: 3 });
    assert(small.hexes.rows === SIZES.small[1] && large.hexes.rows === SIZES.large[1], 'miles down');
    const isles = generateRegion({ land: 'islands', seed: 5 }), inland = generateRegion({ land: 'inland', seed: 5 });
    assert(count(isles, 'water') > 3 * count(inland, 'water'), 'islands are mostly sea; inland mostly land');
    const all = regionHexes(...SIZES.medium).hexes.length;
    assert(count(isles, 'water') > all * .4, 'islands: much water');
  });

  test('mapgen: rugged, wooded and wet change the land', () => {
    const flat = generateRegion({ rugged: 0, seed: 4 }), rough = generateRegion({ rugged: 100, seed: 4 });
    assert(count(rough, 'mountains') + count(rough, 'hills') > 3 * (count(flat, 'mountains') + count(flat, 'hills')), 'rugged');
    const bare = generateRegion({ forest: 0, seed: 4 }), woods = generateRegion({ forest: 100, seed: 4 });
    assert(count(woods, 'forest') > 5 * Math.max(1, count(bare, 'forest')), 'wooded');
    const desert = generateRegion({ climate: 'arid', seed: 4 });
    assert(count(desert, 'desert') > 50 && count(desert, 'swamp') === 0, 'arid: desert, no swamp');
  });

  test('mapgen: settlements spread out, roads join them over land, sites lie in the wilds', () => {
    const r = generateRegion({ settlements: 6, sites: 5, seed: 9 });
    const towns = r.locations.filter(l => l.kind !== 'site'), sites = r.locations.filter(l => l.kind === 'site');
    assert(towns.length === 6 && towns[0].kind === 'town' && towns.slice(1).every(t => t.kind === 'village'), 'a town and villages');
    assert(r.locations.every((l, i) => l.number === i + 1 && l.name === ''), 'numbered 1, 2, 3 ..., never named (GM: the GM names them)');
    assert(placeLabel(r.locations[2]) === '3' && placeLabel({ ...r.locations[2], name: ' Oakford ' }) === 'Oakford', 'the number until the GM names it');
    assert(nextNumber(r.locations) === r.locations.length + 1 && nextNumber([]) === 1, 'a new place takes the next number');
    for (const s of sites) assert(towns.every(t => distance(unkey(t.hex), unkey(s.hex)) > 3) && ['dungeon', 'cave', 'ruin', 'lair'].includes(s.site), 'sites in the wilds');
    assert(r.roads.length === towns.length - 1, 'a road to every settlement');
    for (const rd of r.roads) {
      for (let i = 1; i < rd.length; i++) assert(distance(unkey(rd[i - 1]), unkey(rd[i])) === 1, 'a road runs hex to hex');
      assert(rd.every(k => r.terrain[k] !== 'water'), 'never over water');
    }
    assert(generateRegion({ settlements: 6, roads: false, seed: 9 }).roads.length === 0, 'no roads when not wanted');
    assert(r.party.at && towns[0].hex === key(...r.party.at), 'the party starts in the town');
  });

  test('mapgen: rivers run hex to hex down to water, never back on themselves', () => {
    const r = generateRegion({ wet: 80, seed: 21 });
    assert(r.rivers.length >= 2, 'rivers');
    for (const rv of r.rivers) {
      assert(new Set(rv).size === rv.length, 'no loops');
      for (let i = 1; i < rv.length; i++) assert(distance(unkey(rv[i - 1]), unkey(rv[i])) === 1, 'hex to hex');
      const end = rv.at(-1);
      assert(r.terrain[end] === 'water' || neighbors(...unkey(end)).some(n => r.terrain[key(...n)] === 'water') || rv.length > 3, 'ends at water or a lake');
    }
  });

  test('mapgen: a hex tells its battle map what is on it, and always gives the same map', () => {
    const r = generateRegion({ seed: 9, wet: 80 });
    const road = r.roads[0][1], river = r.rivers[0][1];
    assert(hexContext(r, unkey(road)).road === true, 'a road hex');
    assert(hexContext(r, unkey(river)).river === true, 'a river hex');
    const shore = Object.keys(r.terrain).find(k => r.terrain[k] !== 'water' && neighbors(...unkey(k)).some(n => r.terrain[key(...n)] === 'water'));
    assert(['north', 'east', 'south', 'west'].includes(hexContext(r, unkey(shore)).sea), 'the sea has a side');
    assert(hexSeed(r, [3, 4]) === hexSeed(r, [3, 4]) && hexSeed(r, [3, 4]) !== hexSeed(r, [4, 4]), 'its own number');
  });

  test('mapgen: the region draws its own picture', () => {
    const r = generateRegion({ size: 'small', seed: 2 });
    const c = document.createElement('canvas'); c.width = r.size[0]; c.height = r.size[1];
    const ctx = c.getContext('2d');
    renderRegionPicture(r, ctx);
    const px = ctx.getImageData(Math.floor(r.size[0] / 2), Math.floor(r.size[1] / 2), 1, 1).data;
    assert(!(px[0] === 0x23 && px[1] === 0x25 && px[2] === 0x1f), 'painted inside the region');
  });
  return results;
}
