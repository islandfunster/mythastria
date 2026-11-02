// Tests for dist/props3d.mjs (display-only map props, 2026-10-19). Browser runner: tests/replay_tests.html.
import { PROP_MODELS, propMesh, propsMesh, propMarker } from './dist/props3d.mjs';
import { sceneMesh } from './dist/third-person.mjs';
import { WORLD } from './dist/world-style.mjs';

function assert(cond, text) { if (!cond) throw new Error('FAILED: ' + text); }

// The kinds the Seven Isles map builder draws (seven_isles tools/fgmap.py PROP_KINDS): keep in step.
const BUILDER_KINDS = ['table', 'bench', 'chair', 'bed', 'shelf', 'desk', 'lectern', 'barrel', 'crate', 'sacks', 'cauldron', 'hearth',
  'rug', 'lantern', 'well', 'chest', 'tree', 'dead_tree', 'bush', 'rock', 'boulder', 'stalagmite', 'crystal', 'log', 'kelp', 'statue',
  'altar', 'brazier', 'anvil', 'weapon_rack', 'sarcophagus', 'bones', 'boat', 'net_rack', 'obelisk', 'bell', 'gears',
  'stone_bench', 'stone_table', 'stone_shelf', 'broken_column', 'throne', 'vines', 'moss', 'fern', 'roots', 'mushrooms'];

const span = (m, axis) => { let lo = Infinity, hi = -Infinity; for (let i = axis; i < m.length; i += 9) { lo = Math.min(lo, m[i]); hi = Math.max(hi, m[i]); } return [lo, hi]; };

export function run() {
  const results = [];
  const test = (name, fn) => { try { fn(); results.push([name, true, '']); } catch (e) { results.push([name, false, e.message]); } };

  test('props: every kind the map builder knows has a 3D mockup; each is a sound mesh standing on the floor', () => {
    assert(JSON.stringify(Object.keys(PROP_MODELS).sort()) === JSON.stringify([...BUILDER_KINDS].sort()), 'the same kinds as the builder');
    for (const kind of BUILDER_KINDS) {
      const m = propMesh({ kind, x: 3, y: 4, rot: 0 });
      assert(m.length > 0 && m.length % 27 === 0 && [...m].every(Number.isFinite), kind + ': whole triangles, finite');
      const [ylo, yhi] = span(m, 1), [xlo, xhi] = span(m, 0), [zlo, zhi] = span(m, 2);
      assert(ylo >= -1e-9 && yhi > .02 && yhi < 5, `${kind}: from the floor up (${ylo.toFixed(2)}..${yhi.toFixed(2)})`);
      assert(xlo > 3 - 1.2 && xhi < 3 + 1.2 && zlo > 4 - 1.2 && zhi < 4 + 1.2, `${kind}: around its square`);
    }
    assert(span(propMesh({ kind: 'tree', x: 0, y: 0 }), 1)[1] > span(propMesh({ kind: 'chest', x: 0, y: 0 }), 1)[1] * 3, 'a tree stands taller than a chest');
  });

  test('props: rotation turns the footprint; an unknown kind is drawn as a crate', () => {
    const flat = propMesh({ kind: 'bench', x: 0, y: 0, rot: 0 }), turned = propMesh({ kind: 'bench', x: 0, y: 0, rot: 90 });
    const w0 = span(flat, 0)[1] - span(flat, 0)[0], d0 = span(flat, 2)[1] - span(flat, 2)[0];
    const w1 = span(turned, 0)[1] - span(turned, 0)[0], d1 = span(turned, 2)[1] - span(turned, 2)[0];
    assert(w0 > d0 * 2 && d1 > w1 * 2, 'long along x, then along z');
    assert(propMesh({ kind: 'spaceship', x: 0, y: 0 }).length === propMesh({ kind: 'crate', x: 0, y: 0 }).length, 'unknown: a crate');
  });

  test('props style: each prop sits on a soft ink shadow the size of its footprint (GM 2026-10-19, art style 1)', () => {
    for (const kind of ['barrel', 'bench', 'tree']) {
      const m = propMesh({ kind, x: 2, y: 2, rot: 0 }), shade = [];
      for (let i = 0; i < m.length; i += 9) if (m[i + 1] < .01 && Math.abs(m[i + 5] - WORLD.ink[0]) < .002 && m[i + 8] < .6) shade.push([m[i], m[i + 2]]);
      assert(shade.length >= 24, `${kind}: a shadow on the floor`);
      const r = Math.max(...shade.map(([x, z]) => Math.hypot(x - 2, z - 2)));
      assert(r > .1 && r < 1.2, `${kind}: shadow about its footprint (${r.toFixed(2)})`);
    }
  });

  test('props: the map scene includes them; flat markers by family', () => {
    const map = { cols: 4, rows: 4, square_ft: 5, walls: [], zones: [] };
    const props = [{ kind: 'chest', x: 1, y: 1, rot: 0, label: 'chest' }, { kind: 'tree', x: 2, y: 2, rot: 0, label: 'tree' }];
    assert(sceneMesh({ ...map, props }).length - sceneMesh(map).length === propsMesh(props).length, 'scene = floor + props');
    assert(propsMesh([]).length === 0 && propsMesh(undefined).length === 0, 'none');
    assert(propMarker('chest').family === 'treasure' && propMarker('tree').family === 'green' && propMarker('zz').family === 'other', 'markers');
  });
  return results;
}
