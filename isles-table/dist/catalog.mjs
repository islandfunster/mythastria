// 2026-10-20 (GM: "move the creature catalog to a standalone asset manifest"; Python is the sole rules authority): the
// creature catalog is a plain data file, creatures.json, read here. Before, every page loaded the Rust/WASM engine just
// to ask it for this list. The catalog holds art only (picture, footprint in squares, hash); never rules.
export const CATALOG_FORMAT = 'mythastria-creature-catalog/1';

// The list of approved creatures, or null when the manifest is missing or not a catalog (the pages then show no art).
export async function loadCatalog(fetchFn = globalThis.fetch) {
  try {
    const res = await fetchFn('./creatures.json', { cache: 'no-cache' });
    if (!res?.ok) return null;
    const doc = await res.json();
    if (doc?.format !== CATALOG_FORMAT || !Array.isArray(doc.creatures)) return null;
    return doc.creatures.filter(t => t && t.approved === true && typeof t.id === 'string' && typeof t.path === 'string');
  } catch { return null; }
}

// GM 2026-10-23 ("Newer token art as choices"): extra artwork that Flavor offers as a creature's picture (flavor-art.json:
// the finished SRD Bestiary tokens, tokens/newer/). Never a default picture: creatures still match art in creatures.json
// only. An empty list when the file is missing or not this format.
export const FLAVOR_ART_FORMAT = 'mythastria-flavor-art/1';
export async function loadFlavorArt(fetchFn = globalThis.fetch) {
  try {
    const res = await fetchFn('./flavor-art.json', { cache: 'no-cache' });
    if (!res?.ok) return [];
    const doc = await res.json();
    if (doc?.format !== FLAVOR_ART_FORMAT || !Array.isArray(doc.art)) return [];
    return doc.art.filter(t => t && t.approved === true && typeof t.id === 'string' && typeof t.path === 'string' && typeof t.name === 'string');
  } catch { return []; }
}
