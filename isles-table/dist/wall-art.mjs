// MAP RULE (GM 2026-10-20: "we need to change the map walls to be a minimum of 5 feet wide. The outside edges of the
// outer walls should have stone-like framing that fades away appearing as if it just continues on."; "this is a rule for
// map building"). Maps now carry wall_cells: every square that is wall or rock (tools/fgmap.py MapSpec.wall_cells). The
// squares beside the floor are drawn as stone blocks (faces), the rest as the rock they are cut from, and beyond the
// map's edge the stone fades out over three squares. Display only: the wall lines still decide movement and sight.
import { WORLD, INK_HEX } from './world-style.mjs';

const FADE = 3;

// REGION-01 (GM 2026-10-20: "a popup of a standard terrain battle map"): an outdoor map's ground, and its road squares.
// Display only, in the style's soft colours; each square varies a little so the field does not look flat.
export const GROUND = { grass: [.37, .49, .27], forest: [.25, .35, .2], dry: [.54, .48, .32], stone: [.43, .42, .4],
  mud: [.31, .29, .21], sand: [.76, .67, .45], road: [.55, .46, .31] };
export function groundTone(map, x, y, hash = () => .5) {
  const road = (map?.ground_cells?.road ?? []).some(c => c[0] === x && c[1] === y);
  const base = GROUND[road ? 'road' : map?.ground];
  if (!base) return null;
  const k = 1 + (hash(x, y) - .5) * .14;
  return base.map(v => Math.min(1, v * k));
}
// MAPGEN-01: water on the flat map (a river, the sea, swamp pools: the simulator's water zones), soft blue with a
// light ripple, so Play live's top-down view shows what the 3D view and Simulator fights already show.
export function drawWater2D(root, map, svg) {
  const zones = (map?.zones ?? []).filter(z => z.kind === 'water' && Array.isArray(z.rect));
  if (!zones.length) return;
  const g = svg('g', { class: 'water', 'pointer-events': 'none' });
  for (const z of zones) {
    const [a, b, c, d] = z.rect;
    g.append(svg('rect', { x: a, y: b, width: c - a + 1, height: d - b + 1, fill: '#4f86b4', 'fill-opacity': .82 }));
    for (let y = b; y <= d; y++) g.append(svg('path', { d: `M${a + .15} ${y + .55}q.2 -.12 .35 0t.35 0`, stroke: '#ffffff', 'stroke-opacity': .35, 'stroke-width': .04, fill: 'none' }));
  }
  root.append(g);
}

export function drawGround2D(root, map, svg) {
  if (!GROUND[map?.ground]) return;
  const g = svg('g', { class: 'ground', 'pointer-events': 'none' });
  for (let y = 0; y < map.rows; y++) for (let x = 0; x < map.cols; x++)
    g.append(svg('rect', { x, y, width: 1.01, height: 1.01, fill: hex(groundTone(map, x, y, (a, b) => ((a * 73856093) ^ (b * 19349663)) % 97 / 97)) }));
  root.append(g);
}
const hex = c => '#' + c.map(v => Math.round(v * 255).toString(16).padStart(2, '0')).join('');

export function wallLayers(map, pad = FADE) {
  const cells = map?.wall_cells ?? [];
  if (!cells.length) return { stone: [], fade: [] };
  const wall = new Set(cells.map(c => `${c[0]},${c[1]}`));
  const inside = (x, y) => x >= 0 && y >= 0 && x < map.cols && y < map.rows;
  const open = (x, y) => inside(x, y) && !wall.has(`${x},${y}`);
  const stone = cells.map(([x, y]) => ({ x, y, face: open(x - 1, y) || open(x + 1, y) || open(x, y - 1) || open(x, y + 1) }));
  const fade = [];
  for (let y = -pad; y < map.rows + pad; y++) for (let x = -pad; x < map.cols + pad; x++) {
    if (inside(x, y)) continue;
    const d = Math.max(x < 0 ? -x : x >= map.cols ? x - map.cols + 1 : 0, y < 0 ? -y : y >= map.rows ? y - map.rows + 1 : 0);
    fade.push({ x, y, alpha: +(0.85 * (1 - d / (pad + 1))).toFixed(3) });
  }
  return { stone, fade };
}

export function drawWalls2D(root, map, svg) {
  const { stone, fade } = wallLayers(map);
  if (!stone.length) return;
  const g = svg('g', { class: 'wall-art', 'pointer-events': 'none' });
  const deep = hex(WORLD.wall.map(v => v * .55)), face = hex(WORLD.wall), cap = hex(WORLD.wallCap);
  for (const f of fade) g.append(svg('rect', { class: 'wall-fade', x: f.x, y: f.y, width: 1.01, height: 1.01, fill: deep, 'fill-opacity': f.alpha }));
  for (const s of stone) {
    if (!s.face) { g.append(svg('rect', { class: 'wall-deep', x: s.x, y: s.y, width: 1.01, height: 1.01, fill: deep })); continue; }
    g.append(svg('rect', { class: 'wall-face', x: s.x + .02, y: s.y + .02, width: .96, height: .96, rx: .06, fill: face,
      stroke: INK_HEX, 'stroke-width': .05 }));
    g.append(svg('path', { d: `M${s.x + .12} ${s.y + .5}H${s.x + .88}M${s.x + .5} ${s.y + .14}V${s.y + .5}`, stroke: cap, 'stroke-width': .04,
      'stroke-opacity': .7, fill: 'none' }));
  }
  root.append(g);
}
