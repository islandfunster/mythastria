// Tests for dist/dice-tower.mjs (GM 2026-10-20: "make a dice tower popup that shows the dice roll in a landing box";
// "make the private roll show the dice as blank"). Browser runner: tests/replay_tests.html.
import { diceOf, landingSpots, createDiceTower } from './dist/dice-tower.mjs';

function assert(cond, text) { if (!cond) throw new Error('FAILED: ' + text); }

const ROLL = { n: 7, kind: 'roll', from: 'Hero 3', text: 'Hero 3 rolls 2d20kh1+5 (Stealth): ...', expr: '2d20kh1+5', label: 'Stealth',
  total: 21, natural: 16, terms: [{ sign: 1, dice: '2d20kh1', rolls: [16, 4], kept: [0], subtotal: 16 }, { sign: 1, const: 5 }] };
const HIDDEN = { n: 8, kind: 'gmroll', from: 'Hero 3', hidden: true, text: 'Hero 3 rolls 1d20+3 (Insight) privately for the GM.' };

export function run() {
  const results = [];
  const test = (name, fn) => { try { fn(); results.push([name, true, '']); } catch (e) { results.push([name, false, e.message]); } };

  test('dice tower: the dice of a roll, with the dropped one marked', () => {
    const d = diceOf(ROLL);
    assert(d.dice.length === 2 && d.dice.every(x => x.sides === 20), 'two d20s');
    assert(d.dice[0].value === 16 && d.dice[0].kept && d.dice[1].value === 4 && !d.dice[1].kept, 'faces and the kept one');
    assert(d.total === 21 && !d.blank && d.modifier === 5, 'total and modifier');
    const many = diceOf({ ...ROLL, terms: [{ sign: 1, dice: '20d6', rolls: Array(20).fill(3), kept: [...Array(20).keys()], subtotal: 60 }] });
    assert(many.dice.length === 12 && many.more === 8, 'at most 12 dice shown, the rest counted');
  });

  test('dice tower: a private roll lands blank for the roller; the GM sees the faces', () => {
    const d = diceOf({ ...HIDDEN, expr: '1d20+3' });
    assert(d.blank && d.dice.length === 1 && d.dice[0].sides === 20 && d.dice[0].value === null && d.total === null, 'one blank d20');
    const fromText = diceOf(HIDDEN);                                   // the hidden entry may carry only its text
    assert(fromText.blank && fromText.dice.length === 1 && fromText.dice[0].sides === 20, 'read from the text');
    const gm = diceOf({ ...ROLL, kind: 'gmroll' });
    assert(!gm.blank && gm.dice[0].value === 16 && gm.private, "the GM's own view: faces, marked private");
  });

  test('dice tower: every die gets its own spot in the landing box', () => {
    for (const n of [1, 2, 5, 12]) {
      const s = landingSpots(n, 200, 70);
      assert(s.length === n && new Set(s.map(p => p.join())).size === n, n + ' spots');
      assert(s.every(([x, y]) => x > 0 && x < 200 && y > 0 && y < 70), n + ' inside the box');
    }
  });

  test('dice tower: the popup shows who rolled, the dice in the box and the total; a private roll shows none', () => {
    const tower = createDiceTower({ animate: false });
    const a = tower.render(ROLL);
    assert(a.querySelectorAll('.dt-die').length === 2 && a.querySelector('.dt-tray'), 'dice and tray');
    assert(/Hero 3/.test(a.textContent) && /Stealth/.test(a.textContent) && a.querySelector('.dt-total').textContent === '21', 'caption and total');
    assert([...a.querySelectorAll('.dt-face')].map(f => f.textContent).join() === '16,4', 'faces');
    const b = tower.render({ ...HIDDEN, expr: '1d20+3' });
    assert(b.querySelectorAll('.dt-die').length === 1 && [...b.querySelectorAll('.dt-face')].every(f => f.textContent === ''), 'blank face');
    assert(!b.querySelector('.dt-total') && /GM/.test(b.textContent), 'no total; says the GM sees it');
  });
  return results;
}
