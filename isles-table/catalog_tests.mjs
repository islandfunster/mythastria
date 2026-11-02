// 2026-10-20 (GM: "Deprecate the old Rust rules engine and keep Python as the sole rules authority. First identify
// remaining WASM dependencies, move the creature catalog to a standalone asset manifest, and make Python live play the
// default. Preserve the UI, tokens, effects and character tools."): checks for that step. Browser runner only.
import { PAGES } from './dist/site.mjs';
import { loadCatalog, CATALOG_FORMAT } from './dist/catalog.mjs';

export async function runAsync(engine) {
  const results = [];
  const test = async (name, fn) => { try { await fn(); results.push([name, true]); } catch (e) { results.push([name, false, e.message]); } };
  const assert = (ok, why) => { if (!ok) throw new Error(why); };
  const text = async path => { const r = await fetch(path, { cache: 'no-store' }); assert(r.ok, `${path}: HTTP ${r.status}`); return r.text(); };

  await test('catalog: the creature manifest is a standalone file with all 306 approved creatures', async () => {
    const doc = JSON.parse(await text('../dist/creatures.json'));
    assert(doc.format === CATALOG_FORMAT && Array.isArray(doc.creatures) && doc.creatures.length === 306, 'format and count');
    for (const t of doc.creatures) assert(t.id && t.name && t.path && t.squares > 0 && /^[0-9a-f]{64}$/.test(t.sha256) && t.approved === true, `entry ${t.id}`);
  });
  await test('catalog: the manifest matches the old Rust registry exactly (no creature lost in the move)', async () => {
    const doc = JSON.parse(await text('../dist/creatures.json'));
    const rust = engine.call({ op: 'catalog' }).tokens;
    const canon = list => JSON.stringify(list.map(t => Object.fromEntries(Object.entries(t).sort(([a], [b]) => a.localeCompare(b)))));
    assert(canon(doc.creatures) === canon(rust), 'manifest and Rust registry differ');   // same entries; field order aside
  });
  await test('catalog: loadCatalog reads the manifest without the WASM engine', async () => {
    const tokens = await loadCatalog((path, init) => fetch(path.replace('./creatures.json', '../dist/creatures.json'), init));
    assert(tokens.length === 306 && tokens[0].path.startsWith('tokens/'), 'loaded');
  });
  await test('catalog: a missing or wrong manifest gives no catalog, never a crash', async () => {
    assert((await loadCatalog(async () => ({ ok: false }))) === null, 'missing');
    assert((await loadCatalog(async () => ({ ok: true, json: async () => ({ format: 'other', creatures: [] }) }))) === null, 'wrong format');
  });
  await test('python default: Play live and Simulator fights load no WASM', async () => {
    for (const page of ['../dist/play-ui.mjs', '../dist/replay-ui.mjs']) {
      const src = await text(page);
      assert(!src.includes('isles_engine.wasm') && !src.includes("from './engine.mjs'"), `${page} still loads the Rust engine`);
    }
  });
  await test('python default: the site opens on Play live; the old training table stays reachable', async () => {
    const index = await text('../dist/index.html');
    assert(/http-equiv="refresh" content="\d+; url=play\.html"/.test(index) && index.includes('href="play.html"'), 'index.html sends visitors to Play live');
    assert(PAGES[0][0] === 'play' && PAGES[0][1] === './play.html', 'Play live is the first page');
    assert(!PAGES.some(p => p[1] === './training.html'), 'the old training table is off the page row (GM 2026-10-21)');
    assert(!index.includes('href="training.html"'), 'the start page does not link the old training table (GM 2026-10-21)');
  });
  await test('python default: the training table keeps its UI, effects and character tools', async () => {
    const html = await text('../dist/training.html');
    for (const id of ['initiative', 'map', 'effects-tray', 'characters', 'character-workshop', 'collection', 'library', 'information'])
      assert(html.includes(`id="${id}"`), `#${id} missing`);
    assert(html.includes('src="app.mjs"') && /deprecated/i.test(html), 'still the same table, marked deprecated');
  });
  return results;
}
