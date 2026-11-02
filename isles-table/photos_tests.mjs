// Tests for dist/character-photos.mjs (VIEW-01, GM 2026-10-20: "character sheets will need to be attached to player tokens.
// Character sheet needs photo(s) which will appear on the token."). Browser runner: tests/replay_tests.html.
import { MAX_PHOTOS, emptyPhotos, addPhoto, removePhoto, setActive, photoOf, linkSheet, sheetFor, tokenPhoto, decorate,
  loadPhotos, savePhotos } from './dist/character-photos.mjs';

function assert(cond, text) { if (!cond) throw new Error('FAILED: ' + text); }

export function run() {
  const results = [];
  const test = (name, fn) => { try { fn(); results.push([name, true, '']); } catch (e) { results.push([name, false, e.message]); } };
  const roster = [{ id: 'c1', name: 'Hero 1 Vale' }, { id: 'c2', name: 'Hero 3 Leafshadow' }];

  test('photos: up to four per sheet, one chosen for the token, removing keeps a valid choice', () => {
    let s = emptyPhotos();
    for (const u of ['data:a', 'data:b', 'data:c', 'data:d', 'data:e']) s = addPhoto(s, 'c1', u);
    assert(s.sheets.c1.photos.length === MAX_PHOTOS && MAX_PHOTOS === 4, 'at most four');
    assert(photoOf(s, 'c1') === 'data:a', 'the first is the token picture');
    s = setActive(s, 'c1', 2);
    assert(photoOf(s, 'c1') === 'data:c', 'chosen');
    s = removePhoto(s, 'c1', 2);
    assert(s.sheets.c1.photos.length === 3 && photoOf(s, 'c1') === 'data:a', 'the chosen one removed: back to the first');
    s = removePhoto(removePhoto(removePhoto(s, 'c1', 0), 'c1', 0), 'c1', 0);
    assert(photoOf(s, 'c1') === null, 'none left');
    assert(addPhoto(emptyPhotos(), 'c1', 'https://x/y.png').sheets.c1 === undefined, 'only pictures kept on this PC (data: URLs)');
  });

  test('sheets: a party member is linked to a saved sheet by hand, or by its first name', () => {
    let s = emptyPhotos();
    assert(sheetFor(s, roster, 'Hero 1') === 'c1' && sheetFor(s, roster, 'Hero 4') === null, 'name match');
    s = linkSheet(s, 'Hero 4', 'c2');
    assert(sheetFor(s, roster, 'Hero 4') === 'c2', 'by hand');
    s = linkSheet(s, 'Hero 1', null);
    assert(sheetFor(s, roster, 'Hero 1') === null, 'unlinked by hand wins over the name match');
    assert(sheetFor(linkSheet(emptyPhotos(), 'Hero 4', 'gone'), roster, 'Hero 4') === null, 'a deleted sheet is no link');
  });

  test('tokens: a party member shows its sheet\'s chosen photo, in 2D and 3D', () => {
    const s = addPhoto(emptyPhotos(), 'c1', 'data:corran');
    assert(tokenPhoto(s, roster, 'Hero 1') === 'data:corran' && tokenPhoto(s, roster, 'Hero 4') === null, 'photo by member');
    const view = { state: { combatants: [{ id: 'p1', name: 'Hero 1', pc: true }, { id: 'g1', name: 'Goblin 1', token_id: 'goblin', token_path: 'tokens/goblin.png' }] } };
    const { view: v, tokens } = decorate(view, s, roster);
    const corran = v.state.combatants[0];
    assert(corran.token_path === 'data:corran' && tokens.get(corran.token_id).path === 'data:corran', 'Hero 1: 2D path and 3D token');
    assert(v.state.combatants[1].token_path === 'tokens/goblin.png', 'creatures keep their art');
    assert(view.state.combatants[0].token_path === undefined, 'the view is not changed in place');
  });

  test('storage: kept in this browser; a broken or blocked store starts empty', () => {
    const kept = {};
    const store = { getItem: k => kept[k] ?? null, setItem: (k, v) => { kept[k] = v; } };
    savePhotos(addPhoto(emptyPhotos(), 'c1', 'data:x'), store);
    assert(photoOf(loadPhotos(store), 'c1') === 'data:x', 'round trip');
    assert(loadPhotos({ getItem: () => '{oops' }).sheets && loadPhotos({ getItem() { throw Error('blocked'); } }).sheets, 'empty on errors');
    assert(savePhotos(emptyPhotos(), { setItem() { throw Error('full'); } }) === false, 'a full store says so');
  });
  return results;
}
