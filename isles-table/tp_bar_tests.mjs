// Tests for dist/tp-bar.mjs (GM 2026-10-20: Play live "difficult to use in 3d": actions too far away, targeting tokens,
// moving the character). Browser runner: tests/replay_tests.html.
import { barItems, targetList, creatureTip, squareTip, reachEdge3D, BAR_KEYS } from './dist/tp-bar.mjs';
import { SPELL_KEY } from './dist/play-view.mjs';

function assert(cond, text) { if (!cond) throw new Error('FAILED: ' + text); }

const OFFERS = {
  actor: 'pc1', name: 'Hero 2', side: 'friend', movement: 30,
  attacks: [{ key: 'Warhammer', name: 'Warhammer', targets: ['m1'] }, { key: 'Sling', name: 'Sling', targets: [] }],
  spells: [{ name: 'Guiding Bolt', shape: 'creature', ready: true, targets: ['m1', 'm2'] }, { name: 'Bless', shape: 'creatures', ready: true },
    { name: 'Spirit Guardians', shape: 'self', ready: false, why: 'No level 3 slot' }],
  // reach: [x, y, feet, fromX, fromY]; the character's own square is not listed
  reach: [[6, 5, 5, 5, 5], [7, 5, 10, 6, 5], [8, 5, 15, 7, 5]],
};
const ACTIONS = [{ label: 'Dash', ready: true, cmd: { op: 'dash' } }, { label: 'Help', ready: false, why: 'No ally in reach', pick: 'act:help' }];

export function run() {
  const results = [];
  const test = (name, fn) => { try { fn(); results.push([name, true, '']); } catch (e) { results.push([name, false, e.message]); } };

  test('3d bar: attacks, ready spells, other actions, End turn, with number keys', () => {
    const items = barItems(OFFERS, ACTIONS);
    assert(items.map(i => i.label).join('|') === 'Warhammer|Sling|Guiding Bolt|Bless|Dash|Help|End turn', 'in order, unready spells left out');
    assert(items[0].hotkey === '1' && items[6].hotkey === '7' && BAR_KEYS.length === 10, 'number keys');
    assert(items[0].kind === 'hold' && items[2].kind === 'hold' && items[2].key === SPELL_KEY + 'Guiding Bolt' && items[3].kind === 'cast', 'what a click does');
    assert(!items[1].ready && items[1].why === 'No legal target now' && !items[5].ready, 'nothing to target: not ready, and why');
    assert(barItems(OFFERS, ACTIONS, { held: 'Warhammer' })[0].on, 'the held attack lit');
    assert(barItems(null).length === 0, 'not your turn: no bar');
  });

  test('3d targets: only legal ones, nearest first, refused only counted', () => {
    const cs = [{ id: 'pc1', name: 'Hero 2', x: 5, y: 5 }, { id: 'm1', name: 'Harpy', x: 6, y: 5 }, { id: 'm2', name: 'Crab', x: 9, y: 5 },
      { id: 'm3', name: 'Hidden', x: 7, y: 7 }, { id: 'm4', name: 'Dead', x: 5, y: 6, down: true }];
    const look = c => c.id === 'pc1' ? { cls: 'self' } : ['m1', 'm2', 'm4'].includes(c.id) ? { cls: 'legal-foe' } : { cls: 'refused', reason: 'Out of range' };
    const list = targetList(cs, look, [5, 5]);
    assert(list.legal.map(t => t.name).join() === 'Harpy,Crab' && list.legal[0].feet === 5 && list.legal[1].feet === 20, 'legal, nearest first, in feet');
    assert(list.refused === 1 && !list.legal.some(t => t.name === 'Hidden'), 'a refused creature is only counted (nothing given away)');
  });

  test('3d pointer label: a creature says if it can be targeted; a square says what the move costs', () => {
    assert(creatureTip({ name: 'Harpy' }, null).text === 'Harpy', 'nothing held: the name');
    assert(creatureTip({ name: 'Harpy' }, () => ({ cls: 'refused', reason: 'Out of range' })).text === 'Harpy: Out of range', 'refused: why');
    assert(creatureTip({ name: 'Harpy' }, () => ({ cls: 'legal-foe' })).cls === 'legal', 'legal');
    const ok = squareTip(OFFERS, 7, 5, [5, 5]);
    assert(ok.ok && ok.text === 'Move here · 10 ft' && ok.path.length === 3, 'in reach: cost and path');
    const far = squareTip(OFFERS, 9, 9, [5, 5]);
    assert(!far.ok && /30 ft/.test(far.text), 'out of reach: says so');
    assert(squareTip(OFFERS, 5, 5, [5, 5]) === null, 'own square: nothing');
  });

  test('3d reach: the area edge drawn round the reachable squares', () => {
    const edge = reachEdge3D(OFFERS.reach);
    assert(edge.length === 8, 'a 3-square strip has 8 edge segments');
    assert(edge.some(s => s[0] === 5.5 && s[2] === 5.5) && edge.some(s => s[0] === 8.5 && s[2] === 8.5), 'ends on the half squares');
  });
  return results;
}
