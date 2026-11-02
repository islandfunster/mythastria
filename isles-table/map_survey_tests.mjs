// Tests for dist/map-survey.mjs: the grid tools and the square painter for an imported map.
// GM 2026-10-20: "maps will need a grid aligment tool. if an imported map already has grid marks, then the grid will need
// to be created by hand by a survey tool." MAP RULE (GM 2026-10-20): walls at least one square thick.
// Browser runner: tests/replay_tests.html.
import { gridFromCorners, gridFromDistance, nudge, gridSquares, squareAt, squareLight, draftFromLight, newCells, paint, kindAt,
  cellLists, wallRound, imageType } from './dist/map-survey.mjs';

function assert(cond, text) { if (!cond) throw new Error('FAILED: ' + text); }
const near = (a, b, e = 1e-6) => Math.abs(a - b) < e;

export function run() {
  const results = [];
  const test = (name, fn) => { try { fn(); results.push([name, true, '']); } catch (e) { results.push([name, false, e.message]); } };

  test('survey: two opposite corners of a block of printed squares give the square size and where the grid starts', () => {
    const g = gridFromCorners({ x: 130, y: 70 }, { x: 330, y: 220 }, 4, 3);     // 4 x 3 squares of 50 px from (130, 70)
    assert(near(g.px, 50) && near(g.ox, 30) && near(g.oy, 20) && near(g.skew, 0), JSON.stringify(g));
    const b = gridFromCorners({ x: 330, y: 220 }, { x: 130, y: 70 }, 4, 3);     // either corner first
    assert(near(b.px, 50) && near(b.ox, 30), 'order does not matter');
    assert(gridFromCorners({ x: 0, y: 0 }, { x: 200, y: 165 }, 4, 3).skew > 0.05, 'squares that are not square are reported');
    assert(gridFromCorners({ x: 0, y: 0 }, { x: 0, y: 0 }, 4, 3) === null, 'no block, no grid');
  });

  test('survey: with no grid marks, two points a known distance apart set the squares (5 ft each)', () => {
    const g = gridFromDistance({ x: 40, y: 25 }, { x: 340, y: 25 }, 30);       // 30 ft = 6 squares over 300 px
    assert(near(g.px, 50) && near(g.ox, 40) && near(g.oy, 25), JSON.stringify(g));
    assert(near(gridFromDistance({ x: 0, y: 0 }, { x: 30, y: 40 }, 5).px, 50), 'measured on a slant');
    assert(gridFromDistance({ x: 0, y: 0 }, { x: 100, y: 0 }, 0) === null, 'a distance is needed');
  });

  test('survey: nudging the size and the start, the squares counted on the picture, a click to its square', () => {
    let g = { px: 50, ox: 10, oy: 10 };
    g = nudge(g, { size: 1 });
    assert(g.px === 51 && g.ox === 10, 'bigger');
    g = nudge(g, { dx: -12, dy: 45 });
    assert(g.ox === 49 && g.oy === 4, 'the start wraps within one square: ' + JSON.stringify(g));
    assert(nudge({ px: 9, ox: 0, oy: 0 }, { size: -5 }).px === 8, 'never below 8 px');
    const s = gridSquares({ px: 50, ox: 30, oy: 20 }, 435, 280);
    assert(s.cols === 8 && s.rows === 5, JSON.stringify(s));
    const q = squareAt({ px: 50, ox: 30, oy: 20 }, { x: 185, y: 71 });
    assert(q.x === 3 && q.y === 1, JSON.stringify(q));
  });

  test('draft: dark squares of the picture become wall, light ones floor, the map\'s edge always wall', () => {
    const w = 40, h = 30, data = new Uint8ClampedArray(w * h * 4);             // 4 x 3 squares of 10 px; square (2, 1) bright
    for (let y = 0; y < h; y++) for (let x = 0; x < w; x++) {
      const i = (y * w + x) * 4, lit = (Math.floor(x / 10) === 1 || Math.floor(x / 10) === 2) && Math.floor(y / 10) === 1;
      data[i] = data[i + 1] = data[i + 2] = lit ? 220 : 20; data[i + 3] = 255;
    }
    const light = squareLight({ width: w, height: h, data }, { px: 10, ox: 0, oy: 0 }, 4, 3);
    assert(light.length === 12 && light[1 * 4 + 2] > .8 && light[0] < .1, Array.from(light).join());
    const c = draftFromLight(light, 4, 3, 0.3);
    assert(kindAt(c, 1, 1) === 'f' && kindAt(c, 2, 1) === 'f' && kindAt(c, 0, 1) === 'w' && kindAt(c, 3, 0) === 'w', c.kind.join(''));
    const open = draftFromLight(new Float32Array(25).fill(1), 5, 5, 0.3);
    assert(kindAt(open, 0, 2) === 'w' && kindAt(open, 2, 2) === 'f', 'a bright edge is still wall (the map rule)');
  });

  test('painter: floor, wall and door by hand; the lists the import sends; a wall round the edge', () => {
    let c = newCells(5, 4, { wall: [[0, 0]], door: [[2, 2]] });
    assert(kindAt(c, 0, 0) === 'w' && kindAt(c, 2, 2) === 'd' && kindAt(c, 1, 1) === 'f', c.kind.join(''));
    const before = c;
    c = paint(c, 1, 1, 'w');
    assert(kindAt(c, 1, 1) === 'w' && kindAt(before, 1, 1) === 'f', 'a new map each stroke (undo keeps the old one)');
    assert(paint(c, 9, 9, 'w') === c, 'off the map: unchanged');
    const l = cellLists(c);
    assert(JSON.stringify(l) === JSON.stringify({ wall: [[0, 0], [1, 1]], door: [[2, 2]] }), JSON.stringify(l));
    const r = wallRound(newCells(4, 3));
    assert(r.kind.join('') === 'wwwwwffwwwww', r.kind.join(''));
  });

  test('a Universal VTT file\'s picture: its type from its first bytes', () => {
    assert(imageType('iVBORw0KGgo') === 'image/png' && imageType('/9j/4AAQ') === 'image/jpeg' && imageType('UklGRh4A') === 'image/webp', 'types');
  });
  return results;
}
