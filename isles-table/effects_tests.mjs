// Browser tests for the cartoon effect look (GM 2026-10-20: "spell and hit effects in the cartoon style"): ink outlines
// under the coloured edge, a flat rim band, inked particles; comic hit stars, a swoosh for a miss, inked captions; an ink
// ring under the 3D effects. Runner: tests/replay_tests.html.
import { effectGraphic } from './dist/effects.mjs';
import { visualGraphic } from './dist/effect-events.mjs';
import { effectMesh } from './dist/third-person.mjs';
import { WORLD, INK_HEX } from './dist/world-style.mjs';

function assert(cond, text) { if (!cond) throw new Error('FAILED: ' + text); }
const NS = 'http://www.w3.org/2000/svg';
const svg = (tag, attrs = {}, text) => { const el = document.createElementNS(NS, tag); for (const [k, v] of Object.entries(attrs)) el.setAttribute(k, v); if (text != null) el.textContent = text; return el; };
const inked = el => [...el.querySelectorAll('*')].filter(n => (n.getAttribute('stroke') ?? '').toLowerCase() === INK_HEX);
const fx = (shape, appearance) => ({ id: 'e1', shape, appearance, origin: [3, 3], angle_deg: 0, length_ft: 15, width_ft: 5, radius_ft: 10 });

export function run() {
  const results = [];
  const test = (name, fn) => { try { fn(); results.push([name, true, '']); } catch (e) { results.push([name, false, e.message]); } };

  test('effects style: every shape has an ink outline under its coloured edge, and a flat rim band inside', () => {
    assert(INK_HEX === '#' + WORLD.ink.map(v => Math.round(v * 255).toString(16).padStart(2, '0')).join(''), 'INK_HEX is WORLD.ink');
    for (const shape of ['circle', 'cone', 'line', 'rectangle', 'melee', 'ranged']) {
      const g = effectGraphic(fx(shape, 'fire'), svg), kids = [...g.children];
      const ink = kids.findIndex(n => n.getAttribute('stroke') === INK_HEX && n.getAttribute('fill') === 'none');
      const edge = kids.findIndex((n, i) => i > ink && n.getAttribute('fill') === 'none' && n.getAttribute('stroke') && n.getAttribute('stroke') !== INK_HEX);
      assert(ink >= 0 && edge > ink, `${shape}: ink outline, then the coloured edge on top`);
      assert(+kids[ink].getAttribute('stroke-width') > +kids[edge].getAttribute('stroke-width'), `${shape}: the ink is wider, so it shows as a dark line`);
      assert(g.querySelector('.fx-rim'), `${shape}: a rim band`);
    }
  });

  test('effects style: flames, drops, crystals and bolts are inked', () => {
    for (const look of ['fire', 'acid', 'frost', 'lightning']) assert(inked(effectGraphic(fx('circle', look), svg)).length >= 3, `${look}: inked particles`);
  });

  test('effects style: a hit is a comic star, a critical a bigger one; a miss is a swoosh with puffs; captions are inked', () => {
    const ev = outcome => ({ id: 'v' + outcome, kind: 'melee', outcome, duration_ms: 900, effect: fx('melee', 'physical') });
    const hit = visualGraphic(ev('hit'), svg), crit = visualGraphic(ev('critical'), svg), miss = visualGraphic(ev('miss'), svg);
    const star = g => g.querySelector('.vfx-star');
    assert(star(hit) && star(hit).getAttribute('stroke') === INK_HEX, 'hit: an inked star');
    const size = g => Math.max(...star(g).getAttribute('points').split(/[ ,]+/).map(Number).map(Math.abs));
    assert(star(crit) && size(crit) > size(hit) * 1.3, 'critical: a bigger star');
    assert(!star(miss) && miss.querySelector('.vfx-slash') && miss.querySelectorAll('.vfx-puff').length >= 2, 'miss: swoosh and puffs, no star');
    for (const [g, word] of [[hit, 'HIT'], [crit, 'CRIT!'], [miss, 'MISS']]) {
      const cap = g.querySelector('.vfx-caption');
      assert(cap && cap.textContent === word && cap.getAttribute('stroke') === INK_HEX, `${word}: inked caption`);
    }
  });

  test('effects style: the 3D effect has an ink ring on the floor under its coloured edge', () => {
    for (const shape of ['circle', 'cone', 'line']) {
      const m = effectMesh(fx(shape, 'frost'), 0, 4);
      let ink = 0;
      for (let i = 0; i < m.length; i += 9) if (m[i + 1] < .06 && Math.abs(m[i + 5] - WORLD.ink[0]) < .002 && Math.abs(m[i + 6] - WORLD.ink[1]) < .002) ink++;
      assert(ink >= 6 && m.length % 27 === 0, `${shape}: ink ring (${ink} vertices)`);
    }
  });
  return results;
}
