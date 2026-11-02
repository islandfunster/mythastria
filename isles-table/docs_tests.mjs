// Tests for the Documents page and its feature list (DOCS-01, GM 2026-10-22: "Let's maintain a list of features to be
// included in a documents page in the game."). Browser runner: tests/replay_tests.html.
import { filtered } from './dist/docs-page.mjs';
import { PAGES } from './dist/site.mjs';

function assert(cond, text) { if (!cond) throw new Error('FAILED: ' + text); }

export async function runAsync() {
  const results = [];
  const test = async (name, fn) => { try { await fn(); results.push([name, true, '']); } catch (e) { results.push([name, false, e.message]); } };
  const doc = await (await fetch('../dist/features.json', { cache: 'no-cache' })).json();
  const all = doc.groups.flatMap(g => g.features);

  await test('docs: every feature says what it is, its status and (when used) how', () => {
    assert(doc.format === 'mythastria-features/1' && /^\d{4}-\d{2}-\d{2}$/.test(doc.updated), 'format and date');
    assert(new Set(all.map(f => f.id)).size === all.length, 'each id once');
    for (const f of all) {
      assert(f.name && f.what && ['built', 'partly', 'planned'].includes(f.status), `${f.id}: name, what, status`);
      if (f.status !== 'planned') assert(f.how, `${f.id}: how to use it`);
      if (f.status === 'partly') assert(f.limits, `${f.id}: a partly built feature says what is not done`);
    }
  });

  await test('docs: every page in the page row is documented, and every link goes to a page', () => {
    const hrefs = PAGES.map(p => p[1]);
    for (const [id, href] of PAGES) assert(all.some(f => f.page === href), `the ${id} page has a feature entry`);
    for (const f of all) assert(f.page == null || hrefs.includes(f.page), `${f.id}: its page is in the row`);
  });

  await test('docs: search and status filter', () => {
    const walls = filtered(doc, 'thick walls');
    assert(walls.length === 1 && walls[0].features.some(f => f.id === 'maprule'), 'found by words');
    assert(filtered(doc, '', 'planned').every(g => g.features.every(f => f.status === 'planned')), 'by status');
    assert(filtered(doc, 'no such words at all').length === 0, 'nothing');
  });
  return results;
}
