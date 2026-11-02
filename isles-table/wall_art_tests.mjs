// Tests for dist/wall-art.mjs (MAP RULE, GM 2026-10-20: "we need to change the map walls to be a minimum of 5 feet wide.
// The outside edges of the outer walls should have stone-like framing that fades away appearing as if it just continues
// on."). Browser runner: tests/replay_tests.html.
import { wallLayers, drawWalls2D } from './dist/wall-art.mjs';
import { sceneMesh } from './dist/third-person.mjs';
import { WORLD } from './dist/world-style.mjs';

function assert(cond, text) { if (!cond) throw new Error('FAILED: ' + text); }

// a 5 x 4 map: floor in the middle (1..3, 1..2), wall squares all round
const MAP = { cols: 5, rows: 4, square_ft: 5, walls: [], zones: [], ceilings: [],
  wall_cells: [[0, 0], [1, 0], [2, 0], [3, 0], [4, 0], [0, 1], [4, 1], [0, 2], [4, 2], [0, 3], [1, 3], [2, 3], [3, 3], [4, 3]] };

export function run() {
  const results = [];
  const test = (name, fn) => { try { fn(); results.push([name, true, '']); } catch (e) { results.push([name, false, e.message]); } };

  test('walls: every wall square is stone; the ones beside the floor are faces, the rest deep rock', () => {
    const w = wallLayers(MAP);
    assert(w.stone.length === 14, 'all wall squares');
    const face = new Set(w.stone.filter(s => s.face).map(s => `${s.x},${s.y}`));
    assert(face.has('1,0') && face.has('0,1') && face.has('4,2') && face.has('2,3'), 'beside the floor');
    assert(!face.has('0,0') && !face.has('4,3'), 'corners touch the floor only diagonally: deep rock');
    assert(wallLayers({ ...MAP, wall_cells: [] }).stone.length === 0 && wallLayers({ ...MAP, wall_cells: [] }).fade.length === 0,
      'a map with line walls only: nothing new drawn');
  });

  test('walls: beyond the map edge the stone fades out over three squares', () => {
    const f = wallLayers(MAP).fade;
    const at = (x, y) => f.find(s => s.x === x && s.y === y);
    assert(at(-1, 0) && at(-3, 0) && !at(-4, 0) && at(5, 3) && at(2, -2), 'a frame three squares wide all round');
    assert(at(-1, 0).alpha > at(-2, 0).alpha && at(-2, 0).alpha > at(-3, 0).alpha && at(-3, 0).alpha > 0, 'fading outward');
    assert(!f.some(s => s.x >= 0 && s.x < 5 && s.y >= 0 && s.y < 4), 'nothing over the map itself');
  });

  test('walls: drawn on the flat map', () => {
    const NS = 'http://www.w3.org/2000/svg', svg = (t, a = {}) => { const e = document.createElementNS(NS, t); for (const [k, v] of Object.entries(a)) e.setAttribute(k, v); return e; };
    const root = svg('svg');
    drawWalls2D(root, MAP, svg);
    assert(root.querySelectorAll('.wall-face').length === 10 && root.querySelectorAll('.wall-deep').length === 4, 'ten faces, four corners of deep rock');
    assert(root.querySelectorAll('.wall-fade').length > 20, 'the fading frame');
  });

  test('walls: in 3D, wall squares stand as full blocks and line walls are not drawn twice', () => {
    const plain = sceneMesh({ ...MAP, wall_cells: [] }), solid = sceneMesh(MAP);
    assert(solid.length > plain.length && solid.length % 54 === 0, 'blocks added');
    let top = 0, ink = 0;
    for (let i = 0; i < solid.length; i += 9) { top = Math.max(top, solid[i + 1]); if (Math.abs(solid[i + 5] - WORLD.ink[0]) < .002) ink++; }
    assert(top >= 1.8 && ink > 0, 'standing wall blocks with ink edges');
  });
  return results;
}
