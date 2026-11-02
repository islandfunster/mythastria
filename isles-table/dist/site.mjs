// 2026-10-20 (GM: "One look for all pages"): the shared header for Play live, Simulator fights and The Stage (the same
// brand and logo slot as the main table, links to every page, the current one marked) and the player's chosen skin
// (the main table's setting, kept in this browser). <header class="site-header" data-page="play"> is filled in here.
import { api } from './server.mjs';                            // PLAYER-SITE-01: the GM's Mythastria

// 2026-10-20 (GM: "make Python live play the default"): Play live first; the old Rust training table last, marked.
export const PAGES = [['adventure', './adventure.html', 'Play an adventure'],   // ADVENTURE-01 (GM 2026-10-21): the front door, first
  ['play', './play.html', 'Play live'], ['characters', './characters.html', 'Characters'],   // CHARACTERS-01 (GM 2026-10-21)
  ['replay', './replay.html', 'Simulator fights'],
  ['stage', './stage.html', 'The Stage'], ['region', './region.html', 'Region map'],   // REGION-01 (GM 2026-10-20)
  ['oneshot', './oneshot.html', 'One-shot'], ['remix', './remix.html', 'Remix Prep'], ['spells', './spells.html', 'Spells'],   // REFEREE-01 (GM 2026-10-22)
  ['docs', './docs.html', 'Documents'], ['give', './donate.html', 'Give back']];   // DOCS-01 (GM 2026-10-22): every feature, kept up to date                                 // REMIX-02 (the AI assistant, merged 2026-10-20)
// 2026-10-21 (GM: "there's already a play live button on the row"): the old Rust training table is off the row; it stays
// at ./training.html, opened directly (no link on the start page either, GM 2026-10-21).
// 2026-10-20 (GM: art style 1 for the interface): Tabletop, the cartoon skin, is the default. The choice is kept under a
// new key so everyone starts on it once (the old 'isles-table-skin' is not read).
// 2026-10-22 (GM: "It needs a touch of elegance"; chose the Gilded look): Gilded is the default; a new key again, so
// everyone moves to it once. Tabletop stays a choice (and keeps the map's colours in both).
export const SKINS = ['gilded', 'tabletop', 'noir', 'parchment', 'deepsea'];
export const SKIN_KEY = 'mythastria-skin-2', DEFAULT_SKIN = 'gilded';

// GM 2026-10-25 ("make all DM parts only accessible if they are given a key by the current DM"): a player's page (the
// players' view, or any page on the players' door) has no links to the GM pages; GM 2026-10-28 ("the client side also
// needs The Stage"): only the table and The Stage.
export const PLAYER_PAGES = [['play', './play.html?view=player', 'The table'], ['stage', './stage.html', 'The Stage'], ['give', './donate.html', 'Give back']];
export function headerHTML(current, players = false) {
  const name = players && current === 'play' ? 'The table' : PAGES.find(([id]) => id === current)?.[2] ?? '';
  const links = (players ? PLAYER_PAGES : PAGES).map(([id, href, label]) => `<a href="${href}"${id === current ? ' aria-current="page"' : ''}>${label}</a>`).join('');
  return `<a class="brand" href="${players ? './play.html?view=player' : './'}"><span class="seal logo-slot" title="Mythastria">` +
    `<img src="logo.png" alt="Mythastria" onerror="this.parentElement.classList.add('empty');this.remove()"></span>` +
    `<span>MYTHASTRIA<small>${name}</small></span></a><nav class="site-nav" aria-label="Pages">${links}</nav>`;
}

// SRD-EDITION-01: there are no built-in test characters; this tick stays with nothing to show.
export const PREGENS_KEY = 'mythastria-show-pregens';
export function showPregens(storage = globalThis.localStorage) {
  try { return storage?.getItem(PREGENS_KEY) === '1'; } catch { return false; }
}
export function setShowPregens(on, storage = globalThis.localStorage) {
  try { storage?.setItem(PREGENS_KEY, on ? '1' : '0'); } catch { /* a convenience: without storage it resets next visit */ }
}

export function savedSkin(storage = globalThis.localStorage) {
  try { const s = storage?.getItem(SKIN_KEY); return SKINS.includes(s) ? s : DEFAULT_SKIN; } catch { return DEFAULT_SKIN; }
}

export function saveSkin(name, storage = globalThis.localStorage) {
  try { storage?.setItem(SKIN_KEY, name); } catch { /* the skin is a convenience: without storage it resets next visit */ }
}

// GM 2026-10-24 ("right from the splash screen add the option to choose Portrait and Landscape. Let's have both
// configurations in presets"): a layout preset kept on this device. Auto follows the screen's width; Portrait uses every
// page's narrow, one-column arrangement whatever the width; Landscape keeps the wide, side-by-side one. The pages' own
// width rules (@media max-width / min-width of 600 px or more) are switched on or off; nothing else changes.
export const LAYOUTS = [['auto', 'Auto'], ['portrait', 'Portrait'], ['landscape', 'Landscape']];
export const LAYOUT_KEY = 'mythastria-layout';
const NARROW_PX = 600;

export function savedLayout(storage = globalThis.localStorage) {
  try { const s = storage?.getItem(LAYOUT_KEY); return LAYOUTS.some(([id]) => id === s) ? s : 'auto'; } catch { return 'auto'; }
}

export function saveLayout(name, storage = globalThis.localStorage) {
  try { storage?.setItem(LAYOUT_KEY, name); } catch { /* a convenience: without storage it resets next visit */ }
}

/** A width rule's kind: "narrow" (max-width only), "wide" (min-width only), or null (left as it is). */
export function widthKind(media) {
  const max = /max-width\s*:\s*(\d+)px/.exec(media), min = /min-width\s*:\s*(\d+)px/.exec(media);
  if (max && !min && Number(max[1]) >= NARROW_PX) return 'narrow';
  if (min && !max && Number(min[1]) >= NARROW_PX) return 'wide';
  return null;
}

/** The media text a width rule gets under a layout (null: its own). */
export function layoutMedia(kind, layout) {
  if (layout === 'portrait') return kind === 'narrow' ? 'all' : kind === 'wide' ? 'not all' : null;
  if (layout === 'landscape') return kind === 'narrow' ? 'not all' : null;
  return null;
}

const ORIGINAL_MEDIA = new WeakMap();
export function applyLayout(layout = savedLayout(), doc = document) {
  doc.documentElement.dataset.layout = layout;
  const walk = rules => {
    for (const r of rules) {
      if (r.media && r.cssRules) {                                   // an @media block (an @import has no cssRules)
        if (!ORIGINAL_MEDIA.has(r)) ORIGINAL_MEDIA.set(r, r.media.mediaText);
        const own = ORIGINAL_MEDIA.get(r), want = layoutMedia(widthKind(own), layout) ?? own;
        if (r.media.mediaText !== want) r.media.mediaText = want;
      }
      if (r.cssRules) walk(r.cssRules);
    }
  };
  for (const sheet of doc.styleSheets) {
    let rules;
    try { rules = sheet.cssRules; } catch { continue; }                 // another site's sheet (fonts): not ours to change
    walk(rules);
  }
  const pick = doc.getElementById('layout-pick');
  if (pick) pick.value = layout;
}

function layoutPicker(doc) {
  const header = doc.querySelector('header.site-header');
  if (!header || doc.getElementById('layout-pick')) return;
  const label = doc.createElement('label'); label.className = 'layout-label'; label.title = 'Page layout on this device';
  const sel = doc.createElement('select'); sel.id = 'layout-pick'; sel.setAttribute('aria-label', 'Page layout');
  for (const [id, text] of LAYOUTS) sel.append(new Option(text, id));
  sel.value = savedLayout();
  sel.addEventListener('change', () => { saveLayout(sel.value); applyLayout(sel.value, doc); });
  label.append(sel);
  header.append(label);
}

export function applySite(doc = document) {
  const header = doc.querySelector('header.site-header');
  const players = new URLSearchParams(doc.defaultView?.location?.search ?? '').get('view') === 'player';
  if (header) header.innerHTML = headerHTML(header.dataset.page, players);
  if (header && !players && typeof fetch === 'function')         // GM 2026-10-25: the players' door
    fetch(api('/api/hello')).then(r => r.json()).then(h => { if (h?.door === 'players') header.innerHTML = headerHTML(header.dataset.page, true); }).catch(() => {});
  doc.body.dataset.skin = savedSkin();
  layoutPicker(doc);
  applyLayout(savedLayout(), doc);
  doc.defaultView?.addEventListener('load', () => applyLayout(savedLayout(), doc));   // sheets that loaded after this script
  doc.defaultView?.addEventListener('storage', e => { if (e.key === LAYOUT_KEY) applyLayout(savedLayout(), doc); });
  if (!doc.querySelector('link[rel="icon"]')) {                  // GM 2026-10-21: the gold M sun on the browser tab
    const icon = doc.createElement('link'); icon.rel = 'icon'; icon.type = 'image/png'; icon.href = 'icon.png'; doc.head.append(icon);
  }
}

if (typeof document !== 'undefined') applySite();
