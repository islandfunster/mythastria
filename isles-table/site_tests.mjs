// Tests for dist/site.mjs (GM 2026-10-20: "One look for all pages"). Browser runner: tests/replay_tests.html.
import { PAGES, SKINS, SKIN_KEY, DEFAULT_SKIN, headerHTML, savedSkin, saveSkin, applySite } from './dist/site.mjs';

function assert(cond, text) { if (!cond) throw new Error('FAILED: ' + text); }

export function run() {
  const results = [];
  const test = (name, fn) => { try { fn(); results.push([name, true, '']); } catch (e) { results.push([name, false, e.message]); } };

  test('site: every page header links every page, marks the current one and names it under the brand', () => {
    for (const [id, href, label] of PAGES) {
      const box = document.createElement('div');
      box.innerHTML = headerHTML(id);
      const links = [...box.querySelectorAll('nav a')];
      assert(links.length === PAGES.length && PAGES.length === 11 && links.map(a => a.getAttribute('href')).join() === PAGES.map(p => p[1]).join(), `${id}: all the links`);
      assert(links.filter(a => a.getAttribute('aria-current') === 'page').map(a => a.textContent).join() === label, `${id}: marks itself`);
      assert(box.querySelector('.brand small').textContent === label && box.querySelector('.logo-slot img'), `${id}: brand, page name, logo slot`);
    }
  });

  test('site: the skin chosen on any page is used; anything else falls back to Gilded (GM 2026-10-22)', () => {
    const store = v => ({ getItem: k => (k === SKIN_KEY ? v : 'noir') });
    assert(DEFAULT_SKIN === 'gilded' && SKINS.includes('tabletop') && SKINS.includes('noir'), 'Gilded is the default; the others stay');
    assert(savedSkin(store('deepsea')) === 'deepsea' && savedSkin(store('tabletop')) === 'tabletop', 'kept');
    assert(savedSkin(store('neon')) === 'gilded' && savedSkin(store(null)) === 'gilded', 'unknown or none: Gilded (the older keys are not read)');
    assert(savedSkin({ getItem() { throw new Error('blocked'); } }) === 'gilded', 'storage blocked: Gilded');
    const kept = {}; saveSkin('parchment', { setItem: (k, v) => { kept[k] = v; } });
    assert(kept[SKIN_KEY] === 'parchment', 'saved under one key');
  });

  test('site: applySite fills the header and sets the skin on a page', () => {
    const doc = document.implementation.createHTMLDocument('t');
    doc.body.innerHTML = '<header class="site-header" data-page="stage"></header>';
    applySite(doc);
    assert(doc.querySelector('.site-nav a[aria-current="page"]').textContent === 'The Stage', 'filled');
    assert(SKINS.includes(doc.body.dataset.skin), 'skin set');
  });
  return results;
}
