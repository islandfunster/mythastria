// COMBAT-TRACKER-01 (GM 2026-10-27: "We need a combat tracker"): dist/combat-tracker.mjs arranges the engine's turn order.
// Browser runner: tests/tracker_tests.html.
import { healthWords, trackerRows, trackerTitle, trackerMoved, drawTracker, mapHealth, attitudeColour, ATTITUDE_COLOUR, sightGrid, sightPicks, drawSightGrid } from './dist/combat-tracker.mjs';

function assert(cond, text) { if (!cond) throw new Error('FAILED: ' + text); }

const CS = [
  { id: 'pc1', name: 'Hero 1', pc: true, side: 'friend', hp: 20, hp_max: 28, ac: 17, conditions: [] },
  { id: 'g1', name: 'Goblin 1', side: 'foe', hp: 3, hp_max: 10, ac: 15, conditions: ['Prone'] },
  { id: 'g2', name: 'Goblin 2', side: 'foe', hp: 0, hp_max: 10, ac: 15, down: true, conditions: [] },
  { id: 'pc2', name: 'Hero 4', pc: true, side: 'friend', hp: 0, hp_max: 18, ac: 12, down: true, death_saves: { successes: 1, failures: 2 } },
];
const SNAP = { round: 2, tracker: { scene: false, round: 2, acting: 'g1', concentration: { pc1: 'Bless' },
  order: [{ id: 'g1', init: 18 }, { id: 'pc1', init: 15 }, { id: 'unseen', init: 14 }, { id: 'g2', init: 9 }, { id: 'pc2', init: 7 }] } };

export function run() {
  const results = [];
  const test = (name, fn) => { try { fn(); results.push([name, true, '']); } catch (e) { results.push([name, false, e.message]); } };

  test('tracker: the engine order, who acts, the GM sees numbers', () => {
    const rows = trackerRows(SNAP, CS);
    assert(rows.map(r => r.id).join() === 'g1,pc1,g2,pc2', 'order kept, a creature the page has not got is left out');
    assert(rows[0].acting && rows[0].kind === 'foe' && rows[0].text === '3/10 HP · AC 15 · Prone', 'the GM: exact HP and AC');
    assert(rows[1].kind === 'party' && rows[1].text.includes('Concentrating: Bless'), 'Concentration');
    assert(rows[3].down && rows[3].text.includes('death saves 1 ✓ 2 ✗'), 'death saves at 0 HP');
  });
  test('tracker: a player sees creatures in words, the party exact', () => {
    const rows = trackerRows(SNAP, CS, { player: true });
    assert(rows[0].text === 'Bloodied · Prone', 'Bloodied (SRD), no AC: ' + rows[0].text);
    assert(rows[1].text.startsWith('20/28 HP · AC 17'), 'the party exact');
    assert(healthWords({ hp: 10, hp_max: 10 }) === 'unhurt' && healthWords({ hp: 6, hp_max: 10 }) === 'hurt' && healthWords({ hp: 5, hp_max: 10 }) === 'Bloodied', 'words');
    assert(healthWords({ down: true, stable: true }) === 'down, stable' && healthWords({ dead: true }) === 'dead', 'down and dead');
  });
  test('tracker: the title, scenes and when the console redraws', () => {
    assert(trackerTitle(SNAP, CS) === 'Round 2 · Goblin 1 acts', trackerTitle(SNAP, CS));
    assert(trackerTitle({ tracker: { ...SNAP.tracker, acting: null } }, CS).endsWith('The creatures are acting'), 'unseen creature');
    assert(trackerRows({ tracker: { scene: true, order: [] } }, CS).length === 0 && trackerTitle({ tracker: { scene: true } }).startsWith('No initiative'), 'scene');
    assert(trackerMoved({ acting: 'g1', round: 2 }, { acting: 'g2', round: 2 }) && !trackerMoved({ acting: 'g1', round: 2 }, { acting: 'g1', round: 2 }), 'moved');
  });
  test('tracker: each row is a drop target and a click names its creature', () => {
    const root = document.createElement('div'), clicked = [];
    drawTracker(root, trackerRows(SNAP, CS), { title: 't', marked: 'pc1', onRow: id => clicked.push(id), look: id => id === 'g1' ? { cls: 'legal-foe', reason: '' } : { cls: '', reason: '' } });
    const rows = [...root.querySelectorAll('li')];
    assert(rows.map(r => r.dataset.actor).join() === 'g1,pc1,g2,pc2', 'data-actor: the drop path of the map tokens');
    assert(rows[0].classList.contains('acting') && rows[0].classList.contains('legal-foe') && rows[1].classList.contains('marked'), 'looks');
    rows[2].click();
    assert(clicked.join() === 'g2', 'click');
  });
  test("map: a player sees a creature's health in words and a banded bar; the party and the GM see numbers", () => {
    const goblin = CS[1], corran = CS[0];
    const p = mapHealth(goblin, true);
    assert(p.text === 'Bloodied' && p.frac === .25, 'words and band: ' + JSON.stringify(p));
    assert(!p.text.includes('AC') && !/\d/.test(p.text), 'no numbers for a player');
    assert(mapHealth({ hp: 9, hp_max: 10 }, true).frac === .5 && mapHealth(CS[2], true).frac === 0, 'hurt, down');
    assert(mapHealth(corran, true).text === '20/28 HP, AC 17', 'the party exact');
    const cut = { id: 'g3', name: 'Goblin 3', side: 'foe', hp: 3, hp_max: 4, health: 'hurt' };   // as the players' door sends it
    assert(mapHealth(cut, true).text === 'hurt' && mapHealth(cut, true).frac === .5 && healthWords(cut) === 'hurt', "the door's word");
    assert(mapHealth(goblin, false).text === '3/10 HP, AC 15' && mapHealth(goblin, false).frac === .3, 'the GM exact');
  });
  test('dispositions: the engine\'s attitude colours rows and tokens; the GM changes it on the row', () => {
    const snap = { ...SNAP, scene: { creatures: [{ id: 'g1', attitude: 'Hostile' }, { id: 'g2', attitude: 'Indifferent' }] },
      tracker: { ...SNAP.tracker, sight: { pc1: ['g1'] } } };
    const rows = trackerRows(snap, CS);
    assert(rows[0].attitude === 'Hostile' && rows[2].attitude === 'Indifferent' && rows[1].attitude === null, 'attitudes, none for the party');
    assert(attitudeColour(snap, CS[1]) === ATTITUDE_COLOUR.Hostile && attitudeColour(snap, CS[0]) === null, 'token colour');
    assert(rows[0].seenBy.join() === 'Hero 1' && rows[2].seenBy.length === 0, 'seen by (GM)');
    assert(trackerRows(snap, CS, { player: true })[0].seenBy === null, 'a player gets no seen-by');
    const root = document.createElement('div'), changed = [];
    drawTracker(root, rows, { onAttitude: (id, a) => changed.push(id + ':' + a), onSight: () => {} });
    const pick = root.querySelector('li[data-actor="g1"] select');
    assert(pick && pick.value === 'Hostile' && root.querySelector('li[data-actor="g1"]').style.getPropertyValue('--disposition') === ATTITUDE_COLOUR.Hostile, 'selector and colour');
    pick.value = 'Friendly'; pick.dispatchEvent(new Event('change'));
    assert(changed.join() === 'g1:Friendly', 'the GM changes it');
    assert(!root.querySelector('li[data-actor="g2"] select'), 'no selector on a creature that is down');
    assert([...root.querySelectorAll('button')].some(b => b.textContent.startsWith('Who sees whom')), 'the sight button');
  });
  test('sight: the grid starts from each character\'s sight and sends every box', () => {
    const snap = { tracker: { order: [], sight: { pc1: ['g1'] }, sight_engine: { pc1: [] } } };
    const grid = sightGrid(snap, CS);
    assert(grid.pcs.map(c => c.id).join() === 'pc1' && grid.creatures.map(c => c.id).join() === 'g1', 'standing characters, creatures not down');
    const ticked = new Set(grid.ticked);
    assert(ticked.has('pc1|g1'), 'pre-ticked');
    const root = document.createElement('div');
    drawSightGrid(root, grid, ticked);
    const cb = root.querySelector('input');
    assert(cb.checked && cb.closest('td').classList.contains('picked'), 'differs from the engine: gold');
    cb.checked = false; cb.dispatchEvent(new Event('change'));
    assert(JSON.stringify(sightPicks(grid, ticked)) === '{"pc1":{"g1":false}}' && !cb.closest('td').classList.contains('picked'), 'picks');
    assert(sightGrid({ tracker: { scene: true } }, CS) === null, 'no grid in a scene');
  });
  return results;
}
