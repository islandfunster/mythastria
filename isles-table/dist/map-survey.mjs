// The grid tools and the square painter for an imported map (pure functions; play-ui.mjs draws and listens).
// GM 2026-10-20: "maps will need a grid aligment tool. if an imported map already has grid marks, then the grid will need
// to be created by hand by a survey tool." A picture whose grid is printed is aligned by clicking two opposite corners of
// a block of its squares; a picture with no grid marks is surveyed by clicking two points a known distance apart. Either
// can be nudged by hand. MAP RULE (GM 2026-10-20: walls at least one 5-ft square): the walls are squares, drafted from
// the picture's light (or from a Universal VTT file's thin walls, by the service) and then painted by hand: f floor,
// w wall, d door (a doorway square in a wall). The service builds the simulator's walls from them and checks the rule.
// All in picture pixels; nothing here is sent anywhere.

export const SQUARE_FT = 5, MIN_PX = 8;
const mod = (v, m) => ((v % m) + m) % m;

// Two opposite corners of a block of `across` x `down` printed squares -> { px, ox, oy, skew } (skew: how far the block's
// squares are from square, 0 = square), or null.
export function gridFromCorners(a, b, across, down) {
  const w = Math.abs(b.x - a.x), h = Math.abs(b.y - a.y);
  if (!(across > 0 && down > 0) || w < MIN_PX * across || h < MIN_PX * down) return null;
  const sx = w / across, sy = h / down, px = (sx + sy) / 2;
  return { px, ox: mod(Math.min(a.x, b.x), px), oy: mod(Math.min(a.y, b.y), px), skew: Math.abs(sx - sy) / px };
}

// Two points `feet` apart (the first on a square's corner) -> { px, ox, oy }, or null.
export function gridFromDistance(a, b, feet, squareFt = SQUARE_FT) {
  const d = Math.hypot(b.x - a.x, b.y - a.y), n = feet / squareFt;
  if (!(n > 0) || d / n < MIN_PX) return null;
  const px = d / n;
  return { px, ox: mod(a.x, px), oy: mod(a.y, px), skew: 0 };
}

// By hand: size (pixels) and the start (dx, dy pixels), the start kept within one square.
export function nudge(g, { size = 0, dx = 0, dy = 0 } = {}) {
  const px = Math.max(MIN_PX, g.px + size);
  return { ...g, px, ox: mod(g.ox + dx, px), oy: mod(g.oy + dy, px) };
}

export const gridSquares = (g, width, height) => ({ cols: Math.floor((width - g.ox) / g.px), rows: Math.floor((height - g.oy) / g.px) });
export const squareAt = (g, p) => ({ x: Math.floor((p.x - g.ox) / g.px), y: Math.floor((p.y - g.oy) / g.px) });

// The picture's light in each square (0 dark .. 1 bright), from its middle (ImageData-like { width, height, data }).
export function squareLight(img, g, cols, rows) {
  const out = new Float32Array(cols * rows), step = Math.max(1, Math.floor(g.px / 8));
  for (let y = 0; y < rows; y++) for (let x = 0; x < cols; x++) {
    let sum = 0, n = 0;
    const x0 = g.ox + (x + .2) * g.px, x1 = g.ox + (x + .8) * g.px, y0 = g.oy + (y + .2) * g.px, y1 = g.oy + (y + .8) * g.px;
    for (let py = Math.floor(y0); py < y1 && py < img.height; py += step) for (let px = Math.floor(x0); px < x1 && px < img.width; px += step) {
      const i = (py * img.width + px) * 4, d = img.data;
      sum += (0.2126 * d[i] + 0.7152 * d[i + 1] + 0.0722 * d[i + 2]) / 255; n++;
    }
    out[y * cols + x] = n ? sum / n : 0;
  }
  return out;
}

export function newCells(cols, rows, { wall = [], door = [] } = {}) {
  const kind = new Array(cols * rows).fill('f');
  for (const [x, y] of wall) if (x >= 0 && y >= 0 && x < cols && y < rows) kind[y * cols + x] = 'w';
  for (const [x, y] of door) if (x >= 0 && y >= 0 && x < cols && y < rows) kind[y * cols + x] = 'd';
  return { cols, rows, kind };
}
export const kindAt = (c, x, y) => (x >= 0 && y >= 0 && x < c.cols && y < c.rows ? c.kind[y * c.cols + x] : null);

// A first draft: squares darker than `threshold` are wall, the rest floor, the map's edge always wall (the map rule).
export function draftFromLight(light, cols, rows, threshold = 0.25) {
  const c = newCells(cols, rows);
  c.kind = c.kind.map((_, i) => (light[i] < threshold ? 'w' : 'f'));
  return wallRound(c);
}

export function paint(c, x, y, k) {
  if (kindAt(c, x, y) === null || kindAt(c, x, y) === k) return c;
  const kind = c.kind.slice();
  kind[y * c.cols + x] = k;
  return { ...c, kind };
}

export function wallRound(c) {
  const kind = c.kind.map((k, i) => {
    const x = i % c.cols, y = Math.floor(i / c.cols);
    return x === 0 || y === 0 || x === c.cols - 1 || y === c.rows - 1 ? 'w' : k;
  });
  return { ...c, kind };
}

// What the import sends: { wall: [[x, y], ...], door: [[x, y], ...] } (row by row).
export function cellLists(c) {
  const wall = [], door = [];
  c.kind.forEach((k, i) => { const xy = [i % c.cols, Math.floor(i / c.cols)]; if (k === 'w') wall.push(xy); else if (k === 'd') door.push(xy); });
  return { wall, door };
}

// A Universal VTT file's picture (base64): its type from its first bytes.
export function imageType(b64) {
  if (b64.startsWith('iVBOR')) return 'image/png';
  if (b64.startsWith('/9j/')) return 'image/jpeg';
  if (b64.startsWith('UklGR')) return 'image/webp';
  return 'image/png';
}
