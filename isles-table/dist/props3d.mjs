// 2026-10-19 (GM: "Furniture, greenery, rocks, trees, statues, home amenities, treasure chests, etc. can be mockups made
// to fit the story and the adventure"): simple 3D mockups for the map props the simulator sends (map.props: kind, x, y
// squares, rot, label). Display only: props never block movement or sight (the simulator decides those). The kinds match
// the Seven Isles map builder's 2D icons (seven_isles tools/fgmap.py PROP_KINDS); an unknown kind is drawn as a crate.
// Parts are in feet from the square's centre on the floor: box [w, d, h, y0, dx, dz], cyl [r, h, y0, dx, dz],
// cone [r, h, y0, dx, dz], ball [r, y0 (its bottom), dx, dz]; colours are RGB 0-1.

import { WORLD } from './world-style.mjs';

const WOOD = [.48, .33, .18], DARK = [.33, .22, .13], STONE = [.44, .42, .4], PALE = [.69, .66, .59], IRON = [.23, .23, .24];
const BRASS = [.67, .51, .24], GREEN = [.27, .44, .23], DGREEN = [.19, .32, .17], CLOTH = [.77, .75, .67];

export const PROP_MODELS = {
  table: [['box', [4, 2.6, .25, 2.6], WOOD], ['box', [.3, .3, 2.6, 0, -1.7, -1], DARK], ['box', [.3, .3, 2.6, 0, 1.7, -1], DARK],
    ['box', [.3, .3, 2.6, 0, -1.7, 1], DARK], ['box', [.3, .3, 2.6, 0, 1.7, 1], DARK]],
  bench: [['box', [4, 1.1, .3, 1.4], WOOD], ['box', [.3, 1, 1.4, 0, -1.6], DARK], ['box', [.3, 1, 1.4, 0, 1.6], DARK]],
  chair: [['box', [1.5, 1.5, .25, 1.5], WOOD], ['box', [1.5, .2, 1.6, 1.5, 0, -.7], DARK], ['box', [1.3, 1.3, 1.5, 0], DARK]],
  bed: [['box', [2.4, 4.4, 1.2, 0], DARK], ['box', [2.2, 3.4, .4, 1.2, 0, .4], CLOTH], ['box', [1.6, .8, .35, 1.2, 0, -1.7], [.86, .84, .78]]],
  shelf: [['box', [4.4, 1.2, 6, 0], DARK], ['box', [4, .3, .25, 2, 0, .5], WOOD], ['box', [4, .3, .25, 4, 0, .5], WOOD]],
  desk: [['box', [3.4, 2.2, 2.6, 0], DARK], ['box', [3.6, 2.4, .2, 2.6], WOOD]],
  lectern: [['box', [.8, .8, 3.2, 0], STONE], ['box', [1.8, 1.3, .35, 3.2], PALE]],      // stone (temples, archives)
  barrel: [['cyl', [1.2, 3, 0], WOOD], ['cyl', [1.25, .2, .6], IRON], ['cyl', [1.25, .2, 2.3], IRON]],
  crate: [['box', [2.8, 2.8, 2.8, 0], [.59, .44, .26]], ['box', [2.9, .3, 2.85, 0], DARK]],
  sacks: [['ball', [1, 0, -.7, -.4], [.73, .67, .51]], ['ball', [1, 0, .6, .3], [.69, .63, .47]], ['ball', [.8, 1.3, 0, 0], [.77, .71, .55]]],
  cauldron: [['cyl', [1.4, 1.8, .3], [.12, .12, .13]], ['cyl', [1.1, .05, 2.1], [.27, .35, .24]]],
  hearth: [['box', [4, 2.6, 3.4, 0], STONE], ['box', [2.4, .3, 1.8, .4, 0, 1.2], [.12, .1, .09]], ['ball', [.5, .7, 0, .7], [.9, .45, .15]]],
  rug: [['box', [4.4, 4.4, .15, 0], [.47, .16, .14]], ['box', [3.6, 3.6, .17, 0], [.59, .25, .19]]],
  lantern: [['cyl', [.15, 6, 0], IRON], ['box', [.7, .7, .9, 6], [.95, .8, .45]]],
  well: [['cyl', [1.7, 2.6, 0], STONE], ['cyl', [1.3, .05, 2.6], [.08, .12, .16]], ['box', [.25, .25, 5, 0, -1.6], DARK],
    ['box', [.25, .25, 5, 0, 1.6], DARK], ['box', [3.6, .3, .3, 5], DARK]],
  chest: [['box', [3, 2, 1.6, 0], WOOD], ['box', [3.05, 2.05, .25, .7], BRASS], ['box', [3, 2, .4, 1.6], [.42, .29, .16]],
    ['box', [.4, .1, .5, .9, 0, 1.02], BRASS]],
  tree: [['cyl', [.6, 9, 0], DARK], ['cone', [4, 9, 6], DGREEN], ['cone', [3, 7, 11], GREEN]],
  dead_tree: [['cyl', [.55, 12, 0], [.14, .12, .11]], ['box', [4, .35, .35, 7, 1.6], [.17, .15, .13]], ['box', [.35, 3, .35, 9, 0, -1.2], [.17, .15, .13]]],
  bush: [['ball', [1.5, 0, -.6, -.3], DGREEN], ['ball', [1.4, 0, .7, .3], GREEN], ['ball', [1.1, 1.3, 0, .5], GREEN]],
  rock: [['ball', [1.3, -.5], STONE]],
  boulder: [['ball', [2.2, -.6], [.38, .36, .34]], ['ball', [1.3, 1.6, -.5, -.4], [.48, .46, .43]]],
  stalagmite: [['cone', [1.1, 6, 0], [.41, .36, .32]], ['cone', [.6, 3, 0, .8, .4], [.48, .43, .38]]],
  crystal: [['cone', [.6, 4, 0, -.6, -.2], [.55, .78, .86]], ['cone', [.5, 3, 0, .6, .3], [.67, .86, .94]], ['cone', [.4, 5, 0, 0, -.8], [.78, .94, .98]]],
  log: [['box', [4.4, 1.2, 1.2, 0], DARK]],
  kelp: [['box', [.3, .3, 4, 0, -1, -.4], DGREEN], ['box', [.3, .3, 5, 0, 0, .3], [.24, .38, .2]], ['box', [.3, .3, 3.5, 0, 1, -.2], DGREEN]],
  statue: [['box', [3, 3, 1.2, 0], STONE], ['cyl', [.8, 4.8, 1.2], PALE], ['ball', [.7, 6], PALE]],
  altar: [['box', [3.6, 2.2, 3, 0], PALE], ['box', [3.9, 2.5, .3, 3], [.77, .74, .67]]],
  // MAPGEN-02: stairs to another level of a site (and a site's way in): four steps rising across the square
  stairs: [['box', [4.4, 1.2, .6, 0, 0, 1.8], STONE], ['box', [4.4, 1.2, 1.2, 0, 0, .6], STONE], ['box', [4.4, 1.2, 1.8, 0, 0, -.6], PALE],
    ['box', [4.4, 1.2, 2.4, 0, 0, -1.8], PALE]],
  brazier: [['cyl', [.15, 3, 0], IRON], ['cyl', [1, .6, 3], IRON], ['ball', [.5, 3.3], [.95, .55, .2]]],
  anvil: [['box', [1.2, 1, 1.8, 0], IRON], ['box', [2.6, 1.1, .8, 1.8], IRON], ['box', [.8, .6, .5, 2, -1.6], IRON]],
  weapon_rack: [['box', [4, .6, .3, 3.5], DARK], ['box', [.3, .6, 3.8, 0, -1.8], DARK], ['box', [.3, .6, 3.8, 0, 1.8], DARK],
    ['box', [.1, .1, 5, 0, -1], IRON], ['box', [.1, .1, 5, 0, 0], IRON], ['box', [.1, .1, 5, 0, 1], IRON]],
  sarcophagus: [['box', [2.2, 4.4, 2.6, 0], STONE], ['box', [2, 4.2, .4, 2.6], PALE]],
  bones: [['ball', [.4, 0, -.6, -.4], [.86, .84, .77]], ['box', [2, .3, .3, 0, 0, .3], [.84, .81, .73]], ['ball', [.3, 0, .7, -.6], [.86, .84, .77]]],
  boat: [['box', [2.2, 4.6, 1.4, .6], DARK], ['box', [1.8, 4, .3, 1.8], WOOD], ['cone', [1.1, 1.4, .6, 0, -2.6], DARK]],
  net_rack: [['box', [.3, .3, 5, 0, -2], DARK], ['box', [.3, .3, 5, 0, 2], DARK], ['box', [4.4, .3, .3, 5], DARK],
    ['box', [4, .05, 3.5, 1.4], [.62, .58, .45]]],
  obelisk: [['box', [2.2, 2.2, 10, 0], [.24, .25, .3]], ['cone', [1.4, 2, 10], [.47, .55, .75]]],
  bell: [['cone', [1.8, 3.2, 0], [.59, .43, .2]], ['ball', [.5, 3], [.43, .31, .16]]],
  gears: [['cyl', [1.6, .5, 3], [.43, .41, .38]], ['cyl', [.9, .5, 3.6, 1.6, .9], [.51, .47, .41]], ['box', [.4, .4, 3, 0], IRON]],
  // 2026-10-19 (GM: "vegetation and stone furniture and statues belong in ruins")
  stone_bench: [['box', [4, 1.2, .4, 1.3], STONE], ['box', [.8, 1, 1.3, 0, -1.4], STONE], ['box', [.8, 1, 1.3, 0, 1.4], STONE]],
  stone_table: [['box', [4, 2.6, .5, 2.4], STONE], ['box', [1.4, 1.4, 2.4, 0], [.38, .36, .34]]],
  stone_shelf: [['box', [4.4, 1.2, 6, 0], [.35, .34, .31]], ['box', [3.8, .3, .3, 2, 0, .5], [.16, .14, .13]], ['box', [3.8, .3, .3, 4, 0, .5], [.16, .14, .13]]],
  broken_column: [['cyl', [1.1, 3.2, 0], STONE], ['cyl', [1.1, .4, 3.2], [.5, .48, .45]], ['cyl', [.8, 1.6, 0, 1.6, 1], [.47, .45, .42]]],
  throne: [['box', [2.8, 2.6, 1.8, 0], STONE], ['box', [2.8, .6, 4.6, 1.8, 0, -1], STONE], ['box', [.4, 2, 1, 1.8, -1.2], PALE], ['box', [.4, 2, 1, 1.8, 1.2], PALE]],
  vines: [['box', [3.6, .2, 3.5, 0, 0, 2], DGREEN], ['ball', [.6, 0, -1.2, 1.6], GREEN], ['ball', [.5, 1.8, .4, 1.8], GREEN], ['ball', [.6, .5, 1.4, 1.6], GREEN]],
  moss: [['box', [2.2, 1.8, .15, 0, -.6, -.4], [.25, .36, .2]], ['box', [2, 2.2, .18, 0, .7, .5], [.3, .41, .23]]],
  fern: [['cone', [1.2, 2.2, 0], GREEN], ['cone', [.9, 1.6, 0, .9, .4], DGREEN], ['cone', [.8, 1.5, 0, -.8, .5], DGREEN]],
  roots: [['box', [4, .5, .4, 0, -.4, -.2], [.31, .23, .16]], ['box', [.5, 3, .4, 0, .6, .2], [.28, .2, .14]], ['box', [.45, .45, 2.4, 0, -1.8, -.2], [.31, .23, .16]]],
  mushrooms: [['cyl', [.15, .8, 0, -.6, -.3], CLOTH], ['ball', [.5, .7, -.6, -.3], [.81, .77, .67]], ['cyl', [.15, .6, 0, .5, .4], CLOTH],
    ['ball', [.4, .5, .5, .4], [.75, .69, .59]]],
};

// mesh helpers (positions in squares: 5 ft = 1), each vertex [x, y, z, u, v, r, g, b, a]
function push(out, p, c) { out.push(p[0], p[1], p[2], 0, 0, c[0], c[1], c[2], c[3] ?? 1); }
function tri(out, a, b, c, col) { push(out, a, col); push(out, b, col); push(out, c, col); }
function quad(out, a, b, c, d, col) { tri(out, a, b, c, col); tri(out, a, c, d, col); }
const shade = (c, k) => [c[0] * k, c[1] * k, c[2] * k, c[3] ?? 1];

function boxMesh(out, cx, cz, w, d, h, y0, col, turn) {
  const pts = [[-w / 2, -d / 2], [w / 2, -d / 2], [w / 2, d / 2], [-w / 2, d / 2]].map(([x, z]) => turn(x, z)).map(([x, z]) => [cx + x, cz + z]);
  const y1 = y0 + h;
  for (let i = 0; i < 4; i++) {
    const a = pts[i], b = pts[(i + 1) % 4];
    quad(out, [a[0], y0, a[1]], [b[0], y0, b[1]], [b[0], y1, b[1]], [a[0], y1, a[1]], shade(col, [.72, .9, .66, .84][i]));
  }
  quad(out, ...pts.map(p => [p[0], y1, p[1]]), shade(col, 1.08));
}
function cylMesh(out, cx, cz, r, h, y0, col, top = r, seg = 10) {
  for (let i = 0; i < seg; i++) {
    const a = i / seg * Math.PI * 2, b = (i + 1) / seg * Math.PI * 2;
    const p = (ang, rr, y) => [cx + Math.cos(ang) * rr, y, cz + Math.sin(ang) * rr];
    quad(out, p(a, r, y0), p(b, r, y0), p(b, top, y0 + h), p(a, top, y0 + h), shade(col, .7 + .3 * Math.abs(Math.cos(a))));
    if (top > 0) tri(out, [cx, y0 + h, cz], p(a, top, y0 + h), p(b, top, y0 + h), shade(col, 1.05));
  }
}
function ballMesh(out, cx, cy, cz, r, col, seg = 8) {
  for (let i = 0; i < seg / 2; i++) for (let j = 0; j < seg; j++) {
    const a0 = -Math.PI / 2 + i / (seg / 2) * Math.PI, a1 = -Math.PI / 2 + (i + 1) / (seg / 2) * Math.PI, b0 = j / seg * Math.PI * 2, b1 = (j + 1) / seg * Math.PI * 2;
    const p = (a, b) => [cx + Math.cos(a) * Math.cos(b) * r, Math.max(0, cy + Math.sin(a) * r), cz + Math.cos(a) * Math.sin(b) * r];
    quad(out, p(a0, b0), p(a0, b1), p(a1, b1), p(a1, b0), shade(col, .75 + .3 * (i / (seg / 2))));
  }
}

// The mesh for one prop (Float32Array), at its square's centre, turned by its rotation.
export function propMesh(prop) {
  const out = [], s = 1 / 5, rot = ((prop.rot ?? 0) % 360) * Math.PI / 180, cos = Math.cos(rot), sin = Math.sin(rot);
  const turn = (x, z) => [x * cos - z * sin, x * sin + z * cos];
  for (const [shape, a, col] of PROP_MODELS[prop.kind] ?? PROP_MODELS.crate) {
    if (shape === 'box') {
      const [w, d, h, y0 = 0, dx = 0, dz = 0] = a, [ox, oz] = turn(dx * s, dz * s);
      boxMesh(out, prop.x + ox, prop.y + oz, w * s, d * s, h * s, y0 * s, col, turn);
    } else if (shape === 'cyl' || shape === 'cone') {
      const [r, h, y0 = 0, dx = 0, dz = 0] = a, [ox, oz] = turn(dx * s, dz * s);
      cylMesh(out, prop.x + ox, prop.y + oz, r * s, h * s, y0 * s, col, shape === 'cone' ? 0 : r * s);
    } else {
      const [r, y0 = 0, dx = 0, dz = 0] = a, [ox, oz] = turn(dx * s, dz * s);
      ballMesh(out, prop.x + ox, (y0 + r) * s, prop.y + oz, r * s, col);
    }
  }
  return new Float32Array([...shadow(out), ...out]);
}

// 2026-10-19 (GM: art style 1): a soft ink contact shadow under the prop, an ellipse over its footprint, so it sits
// on the floor like the tokens do.
function shadow(mesh) {
  let x0 = Infinity, x1 = -Infinity, z0 = Infinity, z1 = -Infinity;
  for (let i = 0; i < mesh.length; i += 9) { x0 = Math.min(x0, mesh[i]); x1 = Math.max(x1, mesh[i]); z0 = Math.min(z0, mesh[i + 2]); z1 = Math.max(z1, mesh[i + 2]); }
  const out = [], cx = (x0 + x1) / 2, cz = (z0 + z1) / 2, rx = (x1 - x0) / 2 * 1.08 + .03, rz = (z1 - z0) / 2 * 1.08 + .03, col = [...WORLD.ink, .38];
  for (let k = 0; k < 24; k++) {
    const a = k / 24 * Math.PI * 2, b = (k + 1) / 24 * Math.PI * 2;
    tri(out, [cx, .009, cz], [cx + Math.cos(a) * rx, .009, cz + Math.sin(a) * rz], [cx + Math.cos(b) * rx, .009, cz + Math.sin(b) * rz], col);
  }
  return out;
}

// All the props of a map in one mesh (they never change during a fight).
export function propsMesh(props) {
  const parts = (props ?? []).map(propMesh), n = parts.reduce((s, p) => s + p.length, 0), out = new Float32Array(n);
  let at = 0;
  for (const p of parts) { out.set(p, at); at += p.length; }
  return out;
}

// The flat (tactical) marker: a colour and a letter per kind family, the label as its tooltip.
const FAMILY = { furniture: ['#a07a4a', ['table', 'bench', 'chair', 'bed', 'shelf', 'desk', 'rug']],
  stores: ['#b08a52', ['barrel', 'crate', 'sacks', 'cauldron', 'hearth', 'lantern', 'well', 'net_rack', 'boat', 'weapon_rack', 'anvil', 'gears']],
  treasure: ['#d8b048', ['chest']], green: ['#5e8a4c', ['tree', 'dead_tree', 'bush', 'kelp', 'log', 'vines', 'moss', 'fern', 'roots', 'mushrooms']],
  stone: ['#8c8880', ['rock', 'boulder', 'stalagmite', 'crystal', 'statue', 'altar', 'sarcophagus', 'obelisk', 'bones', 'bell', 'brazier',
    'stone_bench', 'stone_table', 'stone_shelf', 'broken_column', 'throne', 'lectern', 'stairs']] };
export function propMarker(kind) {
  for (const [family, [colour, kinds]] of Object.entries(FAMILY)) if (kinds.includes(kind)) return { family, colour };
  return { family: 'other', colour: '#9a9384' };
}
