// 2026-10-19 (GM: art style 1, "the same cartoon style, softer colours"; "leave the tokens bright coloured"): the world's
// palette. The Retro tokens are bright with thick dark outlines and flat cel shading; the world uses the same drawing
// language (ink outlines, two or three flat tones per surface) in muted stone, wood and sea colours so the tokens stand
// out on top of it. Colours are RGB 0-1. Display only.

export const WORLD = {
  ink: [.11, .09, .1],                      // outlines and seams, as the tokens' black lines (a little warm)
  stone: [.47, .43, .37],                   // floor flagstones: warm sandstone
  stoneLight: [.55, .5, .43],               // the lit edge of a flagstone
  mortar: [.3, .29, .27],                   // seams when the grid is off (still readable as squares)
  wall: [.47, .48, .49],                    // wall faces: cool grey stone, apart from the floor
  wallCap: [.62, .63, .62],                 // the top of a wall
  door: [.55, .38, .22],                    // door planks
  doorDark: [.36, .24, .14],                // a door's frame and plank lines
  sky: [.16, .2, .22],                      // background and distance fog: a soft dusk
};

// A steady small number for a square (0..1): the same tile always gets the same tone, crack and highlight.
export function hash2(x, y) {
  let h = (Math.imul(x | 0, 374761393) + Math.imul(y | 0, 668265263)) | 0;
  h = Math.imul(h ^ (h >>> 13), 1274126177);
  return ((h ^ (h >>> 16)) >>> 0) / 4294967296;
}

// A flagstone's tone: the stone colour a few percent lighter or darker, never far from the palette.
export function tileTone(x, y) {
  const k = 1 + (hash2(x, y) - .5) * .12;
  return WORLD.stone.map(v => v * k);
}

export const INK_HEX = '#' + WORLD.ink.map(v => Math.round(v * 255).toString(16).padStart(2, '0')).join('');   // for SVG strokes
