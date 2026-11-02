// REGION-01 (GM 2026-10-20): the regional hex map page. A picture of the region with three hex grids over it (1 mile
// dotted, 6 miles dashed, 24 miles solid), painted terrain, fog the party clears as it travels, places linked to tactical
// maps (opened in Play live), the party's travel by SRD 5.2.1 pace with an encounter check each 4-hour watch, and fast
// travel without encounters through places already visited. 2D only. Logic: hex-region.mjs. The region is kept in this
// browser (IndexedDB) and can be exported to a file; the player view (?view=player) shows the map under the fog only.
import { zoomButtons } from './map-zoom.mjs';   // MAP-ZOOM-01
import { newRegion, checkRegion, TERRAIN, DEFAULT_TERRAIN, SCALES, PACES, key, unkey, hexAt, hexCenter, hexCorners, hexesWithin,
  hexesCovering, gridPath, hexesPath, gridFromCentres, gridFromSurvey, nudgeGrid, route, fastRoute, travel, placeParty,
  clockText, terrainOf, nextMorning, paceIn, regionWeather, HOURS_PER_DAY, distance } from './hex-region.mjs';
import { generateRegion, renderRegionPicture, hexContext, hexSeed, CLIMATES, LANDS, DEFAULT_PREFS, placeLabel, nextNumber } from './region-gen.mjs';

const $ = id => document.getElementById(id), NS = 'http://www.w3.org/2000/svg';
const svg = (tag, attrs = {}, text) => { const e = document.createElementNS(NS, tag); for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, v); if (text != null) e.textContent = text; return e; };
const el = (tag, cls, text) => { const e = document.createElement(tag); if (cls) e.className = cls; if (text != null) e.textContent = text; return e; };
const PLAYER = new URLSearchParams(location.search).get('view') === 'player';
const channel = 'BroadcastChannel' in globalThis ? new BroadcastChannel('mythastria-region') : null;

let region = newRegion(), pictureSize = [1000, 700], view = null, tool = null, paint = null, clicks = [], trip = null, cache = {};
// "in the forest", "on the road": where the party is, in plain words
const where = t => (['road', 'coast', 'water', 'plains'].includes(t) ? 'on the ' : 'in the ') + (TERRAIN[t]?.label ?? t).toLowerCase();
const status = (text, error = false) => { $('status').textContent = text; $('status').className = error ? 'error' : ''; };

// ------------------------------------------------------------------ keeping the region (IndexedDB: pictures are large)
function db() {
  return new Promise((ok, no) => { const r = indexedDB.open('mythastria-region', 1); r.onupgradeneeded = () => r.result.createObjectStore('regions'); r.onsuccess = () => ok(r.result); r.onerror = () => no(r.error); });
}
async function save() {
  try { const d = await db(); await new Promise((ok, no) => { const t = d.transaction('regions', 'readwrite'); t.objectStore('regions').put(region, 'current'); t.oncomplete = ok; t.onerror = () => no(t.error); }); }
  catch (e) { status('Could not keep the region in this browser (' + e.message + '); use Export.', true); }
  channel?.postMessage('changed');
  if (!PLAYER) keepSoon();
}

// ------------------------------------------------------------------ ATLAS-01: the map database (tools/atlas.py)
// GM 2026-10-22: "create a database that allows multiple maps to be connected". Every map is kept in Mythastria (on this
// PC, by id); a place can lead to another map (place.to = {map: id}) or to a tactical map (place.map); Back returns.
const CURRENT = 'mythastria-atlas-current', TRAIL = 'mythastria-atlas-trail', PROJECT = 'mythastria-atlas-project';
let mapId = null, maps = [], projects = [], keepTimer = 0, keeping = null;
// GM 2026-10-22: "a filing protocol that keeps all maps associated with a project, and a place for spare maps": the
// project shown (null: Spare maps); a new map is filed there, a map made from a place or portal in its map's project
let projectId = (() => { try { return localStorage.getItem(PROJECT) || null; } catch { return null; } })();
const pval = id => id ?? 'spare', pid = v => (v === 'spare' || !v ? null : v);
const projectOfMap = id => maps.find(m => m.id === id)?.project ?? null;
function showProject(id) { projectId = id; try { if (id) localStorage.setItem(PROJECT, id); else localStorage.removeItem(PROJECT); } catch { /* fine */ } }
const worth = r => !!(r.picture || r.locations.length || Object.keys(r.terrain).length || r.party.at);
function keepSoon() { clearTimeout(keepTimer); keepTimer = setTimeout(keepNow, 700); }
async function keepNow() {
  clearTimeout(keepTimer);
  // 2026-10-22 (GM: "oakford wasn't saved"): a map already in Maps is always kept, empty or not (its name, its grid);
  // only a brand-new empty map waits until it holds something, so Clear does not fill Maps with blank maps
  if (!worth(region) && !mapId) return;
  const snapshot = region;
  keeping = (async () => {
    const out = await post('/api/atlas/save', mapId ? { id: mapId, map: snapshot } : { map: snapshot, project: projectId }).catch(() => ({ ok: false }));
    if (out.ok) { if (snapshot === region) { mapId = out.id; try { localStorage.setItem(CURRENT, mapId); } catch { /* fine */ } } await refreshAtlas(); }
    else status('Not kept in Maps: ' + (out.error || 'start Mythastria (Start_Mythastria.bat).'), true);
  })();
  await keeping;
}
const trail = () => { try { return JSON.parse(sessionStorage.getItem(TRAIL) || '[]'); } catch { return []; } };
const setTrail = t => { try { sessionStorage.setItem(TRAIL, JSON.stringify(t)); } catch { /* fine */ } };
async function refreshAtlas() {
  const out = await post('/api/atlas/list', {}).catch(() => ({ ok: false }));
  if (!out.ok) return;
  maps = out.maps; projects = out.projects;
  if (projectId && !projects.some(p => p.id === projectId)) showProject(null);
  const label = p => `${p.name} · ${p.maps} map${p.maps === 1 ? '' : 's'}`;
  $('atlas-project').replaceChildren(...projects.map(p => new Option(label(p), pval(p.id), false, p.id === projectId)));
  const filed = maps.filter(m => (m.project ?? null) === projectId);
  $('atlas-list').replaceChildren(...(mapId ? [] : [new Option(`${region.name} (not kept yet)`, '')]),
    ...filed.map(m => new Option(m.name + (m.id === mapId ? ' (open)' : '') + (m.portals ? ` · ${m.portals} portal${m.portals === 1 ? '' : 's'}` : ''), m.id, false, m.id === mapId)));
  $('atlas-move').replaceChildren(...projects.map(p => new Option(p.name, pval(p.id), false, p.id === (mapId ? projectOfMap(mapId) : projectId))));
  $('atlas-move').disabled = !mapId;
  $('proj-rename').disabled = $('proj-delete').disabled = !projectId;
  const here = maps.find(m => m.id === mapId), nameOf = id => maps.find(m => m.id === id)?.name ?? 'a deleted map';
  const parts = [];
  if (here?.links?.length) parts.push('Its places lead to: ' + here.links.map(nameOf).join(', ') + '.');
  if (here?.linked_from?.length) parts.push('Reached from: ' + here.linked_from.map(nameOf).join(', ') + '.');
  $('atlas-links').textContent = parts.join(' ');
  setTrail(trail().filter(s => maps.some(m => m.id === s.id)));        // never back to a deleted map
  const back = trail().at(-1);
  $('atlas-back').hidden = !back; $('atlas-back').textContent = back ? `Back to ${back.name}` : 'Back';
}
// GM 2026-10-24 ("The map should be able to be reset to original design"): each map keeps its original design, as it was
// made, imported or first opened (maps from before this keep the design they had then). Its picture is kept only once it
// is replaced; until then the original's picture is the map's own. Reset puts all of it back, except that the party is
// not placed (GM: "The Party should not be placed after reset"): no party, no fog cleared, no travels, Day 1 again.
function designOf(r) {
  const { original, picture, ...rest } = r;
  return structuredClone(rest);
}
function keepOriginal(r, force = false) {
  if ((force || !r.original) && worth(r)) r.original = designOf(r);
  return r;
}
function resetRegion() {
  const o = region.original;
  if (!o) return;
  if (tool) setTool(tool);
  const back = structuredClone(o);
  back.picture = 'picture' in o ? o.picture : region.picture;
  const fresh = newRegion();
  Object.assign(back, { party: { ...fresh.party, pace: back.party?.pace ?? fresh.party.pace }, visited: [], revealed: [], log: [] });
  region = numbered(checkRegion({ ...back, original: o })); pictureSize = region.size ?? [1000, 700]; view = null; trip = null; cache = {};
  if (region.design?.made) paintPicture(region);                     // a made region's picture is drawn from its terrain
  for (const s of SCALES) $('show-' + s.miles).checked = region.grids?.[s.miles] !== false;
  $('go').hidden = $('go-fast').hidden = true; $('trip').textContent = '';
  changed();
}
function useRegion(r, id) {
  region = keepOriginal(numbered(checkRegion(r))); mapId = id; pictureSize = region.size ?? [1000, 700]; view = null; trip = null; cache = {};
  if (tool) setTool(tool);
  for (const s of SCALES) $('show-' + s.miles).checked = region.grids?.[s.miles] !== false;
  try { if (id) localStorage.setItem(CURRENT, id); } catch { /* fine */ }
}
async function openMap(id, { back = false, arrive = null, party = null } = {}) {
  if (keeping) await keeping;
  if (worth(region) || mapId) await keepNow();
  const from = { id: mapId, name: region.name };                       // after keeping: the map we came from has its id
  const out = await post('/api/atlas/get', { id });
  if (!out.ok) { status(out.error || 'That map could not be opened.', true); return; }
  if (back && from.id) setTrail([...trail(), from]);
  useRegion(out.map, id);
  showProject(projectOfMap(id));                                       // the list shows the open map's project
  let said = `${region.name}: ${clockText(region.party)}.`;
  if (arrive) {                                                        // a portal: look at where it comes out
    const [x, y] = hexCenter(region.grid, ...unkey(arrive)), w = pictureSize[0] / 2.5, h = pictureSize[1] / 2.5;
    view = [x - w / 2, y - h / 2, w, h];
    if (party) {                                                       // the party stepped through: it is here now, same day and hour
      region = placeParty(region, unkey(arrive));
      Object.assign(region.party, { day: party.day, hour: party.hour, pace: party.pace, today: party.today ?? 0, sinceWatch: party.sinceWatch ?? 0 });
      said = `Through the portal: ${region.name}, ${clockText(region.party)}.`;
    }
  }
  status(said); cache = {}; draw(); save(); await refreshAtlas();
}

// ------------------------------------------------------------------ portals (GM 2026-10-22)
// "let's make portals the allow a spot in the map to jump to another map that's part of the database": a portal is a
// place of kind "portal" (place.to = {map, hex}): click it on the map to jump there; when the party travels onto it,
// Step through takes the party along. Two-way: the GM clicks where it comes out, and a portal back is put there.
let portalEnd = null;                                                  // {fromMap, fromHex, fromName}: waiting for its far end
function jump(p, withParty = false) {
  if (!p?.to?.map) { status('This portal leads nowhere yet: Edit it (Places list) and choose where it goes.', true); return; }
  if (!maps.some(m => m.id === p.to.map)) { status('The map this portal led to was deleted.', true); return; }
  openMap(p.to.map, { back: true, arrive: p.to.hex ?? null, party: withParty ? { ...region.party } : null });
}
async function placePortalEnd(h) {
  const end = portalEnd; portalEnd = null; setTool('portal-end');
  const here = key(...h);
  const back = { hex: here, number: nextNumber(region.locations), name: '', kind: 'portal', note: '', map: null, to: { map: end.fromMap, hex: end.fromHex } };
  region.locations = [...region.locations.filter(l => l.hex !== here), back];
  changed('party');
  const src = await post('/api/atlas/get', { id: end.fromMap });       // the first end learns where it comes out
  if (src.ok) {
    const s = src.map.locations.find(l => l.hex === end.fromHex);
    if (s) { s.to = { map: mapId, hex: here }; await post('/api/atlas/save', { id: end.fromMap, map: src.map }); }
  }
  await keepNow();
  status(`Two-way portal: ${end.fromName} and ${region.name} are joined. Click a portal to jump through it.`);
}
/** Places without a number (made before numbering) get the next ones. */
function numbered(r) {
  for (const p of r.locations) if (!p.number) p.number = nextNumber(r.locations);
  return r;
}
async function load() {
  try { const d = await db(); return await new Promise(ok => { const r = d.transaction('regions').objectStore('regions').get('current'); r.onsuccess = () => ok(r.result ?? null); r.onerror = () => ok(null); }); }
  catch { return null; }
}
function changed(what = 'all') { if (what !== 'party') cache = {}; else delete cache.fog; draw(); save(); }

// ------------------------------------------------------------------ drawing
function scaleDash(miles) { const u = region.grid.pxPerMile * miles / 30; return miles === 1 ? `${(1.2 * u).toFixed(1)} ${(3 * u).toFixed(1)}` : `${(6 * u / 6).toFixed(1)} ${(4 * u / 6).toFixed(1)}`; }
function draw() {
  const root = $('region'), [W, H] = pictureSize, g = region.grid;
  if (!view) view = [0, 0, W, H];
  root.setAttribute('viewBox', view.join(' '));
  root.replaceChildren();
  const k = view[2] / (root.getBoundingClientRect().width || 1000);   // picture pixels per screen pixel: markers stay readable at any zoom
  // the players see only the hexes the party has seen: the picture, terrain and grids are clipped to them
  const base = svg('g');
  if (PLAYER) {
    const defs = svg('defs'), clip = svg('clipPath', { id: 'seen' });
    clip.append(svg('path', { d: hexesPath(g, region.revealed) })); defs.append(clip); root.append(defs, svg('rect', { x: -1e5, y: -1e5, width: 2e5, height: 2e5, fill: '#07080a' }));
    base.setAttribute('clip-path', 'url(#seen)');
  }
  root.append(base);
  if (region.picture) base.append(svg('image', { href: region.picture, x: 0, y: 0, width: W, height: H, preserveAspectRatio: 'none' }));
  else base.append(svg('rect', { x: 0, y: 0, width: W, height: H, fill: '#1c2420' }));
  if ($('show-terrain').checked && !PLAYER && !region.design?.made) {   // a made region's picture is drawn from its terrain
    const by = {};
    for (const [k, t] of Object.entries(region.terrain)) (by[t] ??= []).push(k);
    for (const [t, keys] of Object.entries(by)) base.append(svg('path', { d: hexesPath(g, keys), fill: TERRAIN[t].color, 'fill-opacity': .45, stroke: 'none' }));
  }
  const line = Math.max(.6, g.pxPerMile / 40);
  for (const s of SCALES) {
    if (!(PLAYER ? region.grids?.[s.miles] !== false : $('show-' + s.miles).checked)) continue;   // GM 2026-10-22: the GM's ticks pick the players' grids
    cache['grid' + s.miles] ??= gridPath(g, W, H, s.miles);
    base.append(svg('path', { d: cache['grid' + s.miles], fill: 'none', stroke: s.miles === 24 ? '#f3e7c8' : '#efe3c4', 'stroke-opacity': s.miles === 1 ? .55 : .8,
      'stroke-width': line * (s.miles === 1 ? 1 : s.miles === 6 ? 1.8 : 2.6), 'stroke-dasharray': s.miles === 24 ? 'none' : scaleDash(s.miles), 'stroke-linecap': 'round' }));
  }
  if ($('show-fog').checked && !PLAYER) {                                // unrevealed hexes shaded for the GM
    if (!cache.fog) { const seen = new Set(region.revealed); cache.fog = hexesPath(g, hexesCovering(g, W, H, 1).map(h => key(...h)).filter(k => !seen.has(k))); }
    root.append(svg('path', { d: cache.fog, fill: '#07080a', 'fill-opacity': .38, stroke: 'none' }));
  }
  if (trip?.path?.length > 1) {
    root.append(svg('polyline', { points: trip.path.map(h => hexCenter(g, ...h).join(',')).join(' '), fill: 'none', stroke: trip.fast ? '#8fd0ff' : '#f2c94c',
      'stroke-width': line * 3, 'stroke-dasharray': trip.fast ? `${line * 4} ${line * 3}` : 'none', 'stroke-linejoin': 'round', 'stroke-linecap': 'round' }));
  }
  const seen = new Set(region.revealed);
  for (const p of region.locations) {
    if (PLAYER && !seen.has(p.hex)) continue;
    const [x, y] = hexCenter(g, ...unkey(p.hex)), gr = svg('g', { 'data-place': p.hex });
    const pr = Math.max(g.pxPerMile * .28, 6 * k);
    if (p.kind === 'portal') {                                          // a portal: a violet swirl, a bright rim
      gr.append(svg('circle', { cx: x, cy: y, r: pr * 1.25, fill: '#6b3fa0', stroke: '#e7d6ff', 'stroke-width': line * 1.4 }));
      gr.append(svg('circle', { cx: x, cy: y, r: pr * .62, fill: 'none', stroke: '#e7d6ff', 'stroke-width': line, 'stroke-dasharray': `${pr * .6} ${pr * .35}` }));
      gr.style.cursor = 'pointer';
    } else gr.append(svg('circle', { cx: x, cy: y, r: pr, fill: p.kind === 'site' ? '#b0503c' : p.map ? '#c5a56b' : '#e6dcc2', stroke: '#1b1710', 'stroke-width': line }));   // MAPGEN-01: sites in red
    gr.append(svg('text', { x: x + Math.max(g.pxPerMile * .4, 9 * k), y: y + 4 * k, class: 'r-label', 'font-size': 13 * k, 'stroke-width': 3 * k }, placeLabel(p)));
    gr.append(svg('title', {}, (p.kind === 'portal' ? 'Portal ' : '') + placeLabel(p) + (p.to ? ` · leads to ${maps.find(m => m.id === p.to.map)?.name ?? 'another map'}` : '') + (p.map ? ` · tactical map ${p.map}` : '') + (p.note && !PLAYER ? ` · ${p.note}` : '') + (PLAYER ? '' : p.kind === 'portal' ? ' · click to jump; Edit in Places' : ' · click to name it')));
    root.append(gr);
  }
  if (region.party.at) {
    const [x, y] = hexCenter(g, ...region.party.at), r = Math.max(g.pxPerMile * .38, 10 * k);
    root.append(svg('circle', { cx: x, cy: y, r, fill: '#3d6fb5', stroke: '#f6edd4', 'stroke-width': line * 1.5 }));
    root.append(svg('text', { x, y: y + r * .38, 'text-anchor': 'middle', 'font-size': r * 1.1, fill: '#f6edd4', 'font-weight': 700 }, 'P'));
  }
  drawPanel();
}

function drawPanel() {
  if (PLAYER) return;
  $('name').value = region.name;
  $('clock').textContent = clockText(region.party) + (region.party.at ? ` · ${where(terrainOf(region, key(...region.party.at)))}` : '');
  $('pace').value = region.party.pace;
  const here = region.party.at ? key(...region.party.at) : null, kept = here ? paceIn(region, here) : region.party.pace;
  $('pace-effect').textContent = `${PACES[kept].label} pace: ${PACES[kept].effect}.` + (kept !== region.party.pace ? ` (${TERRAIN[terrainOf(region, here)].label}: at most ${PACES[kept].label}.)` : '') +
    (region.party.today ? ` ${region.party.today.toFixed(1)} of ${HOURS_PER_DAY} travel hours today.` : '');
  const env = region.environment ?? {};
  for (const k of ['cold', 'heat', 'wind', 'sand', 'rain', 'altitude']) $('w-' + k).checked = !!env[k];
  $('w-water').checked = env.water !== false;
  $('enc-chance').value = region.encounters?.chance ?? 3;
  $('places').replaceChildren(...[...region.locations].sort((a, b) => (a.number ?? 0) - (b.number ?? 0)).map(p => {
    const li = el('li', '', `${p.kind === 'portal' ? 'Portal ' : ''}${p.number ?? ''}${p.name ? ' · ' + p.name : ''}${p.note && !p.name ? ' · ' + p.note : ''}`);
    const open = el('button', 'small quiet', 'Open map'), edit = el('button', 'small quiet', 'Edit'), go = el('button', 'small quiet', 'Travel');
    const toName = p.to ? maps.find(m => m.id === p.to.map)?.name : null;
    open.disabled = !p.map && !p.to;
    open.title = p.to ? `Open ${toName ?? 'the map it leads to'}` : p.map ? `Open ${p.map} in Play live` : 'It leads nowhere yet (Edit: Leads to)';
    if (p.kind === 'portal') { open.textContent = 'Jump'; open.disabled = !p.to; }
    open.onclick = () => p.kind === 'portal' ? jump(p) : p.to ? openMap(p.to.map, { back: true })
      : window.open('./play.html?scenario=' + encodeURIComponent(p.map), '_blank');
    edit.onclick = () => editPlace(p.hex);
    go.onclick = () => plan(unkey(p.hex));
    li.append(go, edit, open);
    return li;
  }));
  $('log').replaceChildren(...region.log.slice(-30).reverse().map(t => el('li', '', t)));
  for (const b of document.querySelectorAll('[data-tool]')) b.classList.toggle('on', b.dataset.tool === tool);
}

function drawPalette() {
  $('palette').replaceChildren(...Object.entries(TERRAIN).map(([id, t]) => {
    const b = el('button', 'tool small'); b.dataset.tool = 'paint:' + id;
    const sw = el('span', 'swatch'); sw.style.background = t.color; b.append(sw, t.label);
    b.title = t.impassable ? 'Open water: not on foot' : `SRD 5.2.1 ${t.srd}: at most a ${PACES[t.maxPace].label} pace`;
    b.onclick = () => setTool('paint:' + id); return b;
  }));
}

// ------------------------------------------------------------------ tools
const HELP = {
  centres: 'Click the centre of one printed 1-mile hex, then the centre of another hex straight across from it; give the number of hexes between them.',
  survey: 'Click two points a known distance apart (a scale bar, two towns); give the miles between them. Hex 0,0 goes on the first point; nudge it after.',
};
// 2026-10-22 (GM: "The Add a place button doesn't function"): a map tool only waits for a click on the map, so each
// one says what to do, above and under the map, and brings the map into view; Esc puts the tool down.
const MAP_HINT = 'Wheel to zoom · right- or middle-drag to pan (or drag with no tool chosen).';
function toolHint(t) {
  if (!t) return '';
  if (t.startsWith('paint:')) return `Paint ${TERRAIN[t.slice(6)]?.label ?? ''}: click or drag over hexes on the map. Esc stops.`;
  return { place: 'Add a place: click a hex on the map, then name it. Esc stops.', party: 'Place the party: click a hex on the map. Esc stops.',
    travel: 'Travel to: click the hex to go to on the map. Esc stops.', 'portal-end': 'Two-way portal: click where it comes out on this map. Esc: one-way only.', reveal: 'Reveal: click or drag over hexes the players may see. Esc stops.',
    hide: 'Hide: click or drag over hexes to hide from the players. Esc stops.', centres: HELP.centres, survey: HELP.survey }[t] ?? '';
}
function setTool(t) {
  tool = tool === t ? null : t; clicks = [];
  const hint = toolHint(tool);
  $('hint').textContent = hint || MAP_HINT; $('hint').classList.toggle('tool-on', !!hint);
  if (hint) status(hint);   // REGION-FRAME: the map is always in view now
  $('align-input').hidden = !['centres', 'survey'].includes(tool);
  $('align-label').textContent = tool === 'survey' ? 'Miles between them' : 'Hexes between them';
  $('align-help').textContent = HELP[tool] ?? '';
  if (tool !== 'travel') { trip = null; $('go').hidden = $('go-fast').hidden = true; $('trip').textContent = ''; }
  draw();
}
function pointAt(e) {
  const p = $('region').createSVGPoint(); p.x = e.clientX; p.y = e.clientY;
  const q = p.matrixTransform($('region').getScreenCTM().inverse()); return [q.x, q.y];
}
function brushAt(pt) { const h = hexAt(region.grid, ...pt); return hexesWithin(h, Number($('brush').value)).map(x => key(...x)); }
function applyBrush(pt) {
  if (tool?.startsWith('paint:')) { const t = tool.slice(6); for (const k of brushAt(pt)) { if (t === DEFAULT_TERRAIN) delete region.terrain[k]; else region.terrain[k] = t; } }
  else if (tool === 'reveal') region.revealed = [...new Set([...region.revealed, ...brushAt(pt)])];
  else if (tool === 'hide') { const off = new Set(brushAt(pt)); region.revealed = region.revealed.filter(k => !off.has(k)); }
  cache = {}; draw();
}
function onClick(pt) {
  const h = hexAt(region.grid, ...pt);
  if (tool === 'centres' || tool === 'survey') {
    clicks.push(pt);
    if (clicks.length < 2) { status('Now the second point.'); return; }
    try {
      const n = Number($('align-n').value);
      region.grid = tool === 'centres' ? gridFromCentres(clicks[0], clicks[1], n) : gridFromSurvey(clicks[0], clicks[1], n);
      status(`Grid set: ${region.grid.pxPerMile.toFixed(1)} pixels a mile. Nudge it to fit if needed.`);
    } catch (e) { status(e.message, true); }
    clicks = []; tool = null; $('align-input').hidden = true; $('align-help').textContent = ''; changed(); return;
  }
  if (tool === 'place') { editPlace(key(...h)); return; }
  if (tool === 'party') { region = placeParty(region, h); trip = null; status('The party is here.'); changed('party'); return; }
  if (tool === 'travel') { plan(h); return; }
  if (tool === 'portal-end' && portalEnd) { placePortalEnd(h); return; }
  const p = region.locations.find(l => l.hex === key(...h));
  if (p?.kind === 'portal') { jump(p); return; }                       // a portal: through it (Edit it from the Places list)
  if (p) editPlace(p.hex);                                            // GM: "allow the places to be named on the map manually"
}

// ------------------------------------------------------------------ travel
function plan(to) {
  if (!region.party.at) { status('Place the party first.', true); return; }
  tool = 'travel';
  const walk = route(region, region.party.at, to), fast = fastRoute(region, to);
  trip = walk ? { ...walk, to } : null;
  const text = h => `${h.toFixed(1)} hours (${(h / 8).toFixed(1)} travel days)`;
  const slower = walk ? [...new Set(walk.path.slice(1).map(h => paceIn(region, key(...h))))].filter(p => p !== region.party.pace) : [];
  $('trip').textContent = !walk ? 'No way there on foot (open water).' :
    `${walk.path.length - 1} miles, ${text(walk.hours)} at a ${PACES[region.party.pace].label.toLowerCase()} pace${slower.length ? ` (${slower.map(p => PACES[p].label.toLowerCase()).join(' and ')} where the terrain allows no faster)` : ''}; an encounter check every 4 hours.` +
    (fast ? ` Fast travel (places you have been, no encounters): ${text(fast.hours)}.` : ' No fast travel: the party has not been there.');
  $('go').hidden = !walk; $('go-fast').hidden = !fast;
  $('go-fast').onclick = () => { trip = { ...fast, fast: true }; draw(); go(fast.path, true); };
  draw();
}
// HAZARDS-01 (GM 2026-10-26): the loaded adventure's day (Mythastria sim/hazards.py travel): its clock runs with the
// journey; the region's weather asks its saves each hour, Extended Travel past 8 hours, and Slower Travelers (a member at
// half Speed or less) holds the party to a Slow pace. Without a loaded adventure the region travels on its own.
const PACE_SLOWER = (a, b) => ['slow', 'normal', 'fast'].indexOf(a) <= ['slow', 'normal', 'fast'].indexOf(b) ? a : b;
async function adventureDay(op, extra = {}) {
  const st = await post('/api/adventures/state', {}).catch(() => null);
  const pack = (st?.packs ?? []).find(p => p.loaded)?.id;
  if (!pack) return null;
  const tp = await post('/api/party', { op: 'get' }).catch(() => null), party = tp?.party;
  if (!party || !((party.members ?? []).length || (party.characters ?? []).length)) return null;
  return post('/api/adventures/day', { pack, op, members: party.members ?? [], level: party.level || 1,
    ...((party.characters ?? []).length ? { characters: party.characters } : {}), ...extra });
}
async function go(path, fast) {
  const before = await adventureDay('state');
  const rule = before?.day?.pace;
  if (rule?.forced && region.party.pace !== rule.forced && !fast) {            // Slower Travelers (SRD 5.2.1)
    region.party.pace = rule.forced; save(); drawPanel();
    status(rule.why + ' The pace is set to Slow: plan the trip again.', true); plan(trip?.to ?? path.at(-1)); return;
  }
  const out = travel(region, path, { fast, push: $('push').checked });
  region = out.region; trip = null; $('go').hidden = $('go-fast').hidden = true;
  const met = out.events.find(e => e.kind === 'encounter');
  const place = region.locations.find(l => l.hex === key(...region.party.at));
  $('trip').textContent = met ? `Encounter (${met.when}, d20 ${met.d20}): ${met.text}.${met.distance ? ` It starts ${met.distance.feet} feet away (${met.distance.dice}).` : ''} At a ${PACES[met.pace].label} pace: ${met.effect}.` : out.stopped ?? (fast ? 'Arrived by fast travel.' : `Arrived. ${out.events.length} watch${out.events.length === 1 ? '' : 'es'}, no encounter.`);
  if (out.hours > 0 && before) {
    const env = region.environment ?? {};
    const kept = out.paces.includes(region.party.pace) || !out.paces.length ? region.party.pace : out.paces.reduce((a, b) => PACE_SLOWER(a, b));
    const day = await adventureDay('travel', { hours: out.hours, pace: kept,
      today_before: out.todayBefore, today_after: out.todayAfter, weather: regionWeather(region), water: env.water !== false, fast: !!fast,
      where: place ? placeLabel(place) : region.name });
    const said = day?.day?.log?.filter(e => /Exhaustion|Extended Travel|an hour:/.test(e.text)).slice(-4).map(e => e.text).join(' ') ?? '';
    $('day-link').textContent = day?.ok ? `The adventure day: ${day.day.clock}.${said ? ' ' + said : ''}` : (day?.refused || day?.error || '');
    if (day && !day.ok) status('The adventure day: ' + (day.refused || day.error), true);
  } else if (!before) $('day-link').textContent = 'No adventure is loaded: the journey keeps the region\'s own clock (no saves rolled).';
  if (place?.kind === 'portal' && place.to) {
    $('trip').textContent += ` A portal (${placeLabel(place)}).`;
    const step = el('button', 'small', 'Step through'); step.onclick = () => jump(place, true); $('trip').append(step);
  } else if (place?.map || place?.to) $('trip').textContent += ` ${placeLabel(place)} leads to another map: Places → Open map.`;
  status(clockText(region.party)); changed('party');
  if (met) battle(met.at, `Encounter ${where(met.terrain)} (${met.when}): ${met.text}`);
}

// ------------------------------------------------------------------ a standard terrain battle map (GM 2026-10-20)
// "The outdoor map can simply create a popup of a standard terrain battle map": the service builds one for the terrain
// (tools/terrain_battle.py) and it opens in Play live, in its own window.
let service = null;
async function hello() { service = await (await fetch('/api/hello')).json(); return service; }
async function post(path, body) {
  if (!service?.token) await hello();
  const res = await fetch(path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ ...body, token: service.token }) });
  const out = await res.json().catch(() => ({ ok: false, error: 'The service sent no answer.' }));
  return res.ok ? out : { ...out, ok: false };
}
let battleTerrain = null, battleContext = {};
// MAPGEN-01 (GM 2026-10-22: outdoor maps "and their corresponding battle-maps"): the battle map matches its hex: its
// terrain, a road through it, a river across it, the sea's side; the same hex gives the same field (its own number),
// laid out by the GM's preferences (open, normal or dense; small, normal or large), kept with the region.
async function battle(at, what) {
  const ctx = hexContext(region, at), terrain = ctx.terrain;
  battleTerrain = terrain; battleContext = { road: ctx.road, river: ctx.river, sea: ctx.sea };
  $('bd-title').textContent = `Battle: ${TERRAIN[terrain].label}`;
  $('bd-what').textContent = what;
  const has = [ctx.road && 'a road', ctx.river && 'a river (with a ford)', ctx.sea && `the sea to the ${ctx.sea}`].filter(Boolean);
  $('bd-hex').textContent = has.length ? `On this hex: ${has.join(', ')}.` : '';
  $('bd-density').value = region.design?.battle?.density ?? 'normal';
  $('bd-size').value = region.design?.battle?.size ?? 'normal';
  $('bd-night').checked = region.party.hour < 6 || region.party.hour >= 20;
  $('bd-seed').value = hexSeed(region, at);
  try {
    const out = await post('/api/terrain-battle/suggest', { terrain });
    const names = service.creatures ?? [], first = out.suggested ?? [];
    $('bd-creature').replaceChildren(...[...first, ...names.filter(n => !first.includes(n))].map(n => new Option(n, n)));
  } catch { status('Battle maps need Mythastria running (Start_Mythastria.bat).', true); return; }
  $('battle-dialog').showModal();
}
$('bd-fight').addEventListener('click', async e => {
  e.preventDefault();
  const design = { density: $('bd-density').value, size: $('bd-size').value };
  region.design = { ...region.design, battle: design };
  const out = await post('/api/terrain-battle', { terrain: battleTerrain, creature: $('bd-creature').value, count: Number($('bd-count').value) || 4,
    seed: Number($('bd-seed').value) || 1, night: $('bd-night').checked, design, context: battleContext });
  if (!out.ok) { $('bd-what').textContent = out.error || 'The battle map could not be made.'; return; }
  $('battle-dialog').close();
  region.log = [...region.log, `${clockText(region.party)}: battle map ${out.scenario}`]; save(); drawPanel();
  window.open('./play.html?scenario=' + encodeURIComponent(out.scenario), 'mythastria-battle', 'width=1400,height=900');
});
$('battle-here').onclick = () => {
  if (!region.party.at) { status('Place the party first.', true); return; }
  const t = terrainOf(region, key(...region.party.at));
  battle(region.party.at, `The party is ${where(t)}, ${clockText(region.party)}.`);
};

// ------------------------------------------------------------------ MAPGEN-02: a site drawn as indoor maps
// GM 2026-10-26 (goal 19, "in LM Studio"): a site on a made region (dungeon, cave, ruin, lair) drawn as indoor maps from
// the GM's preferences. The local model designs the rooms; the service lays them out and checks them
// (Mythastria tools/site_maps.py); each level is a map in Play live, filed under Region sites > project > region. The
// place leads to level 1. A model that gives nothing usable says so here: the GM tries again, never a scripted map.
const SD = ['kind', 'size', 'layout', 'walls', 'doors'];
let siteHex = null;
$('pd-site').onclick = async () => {
  const p = region.locations.find(l => l.hex === editing);
  if (!p) return;
  siteHex = p.hex;
  $('place-dialog').close();
  const at = unkey(p.hex), ctx = hexContext(region, at), last = region.design?.site ?? {};
  $('sd-title').textContent = `Draw ${placeLabel(p)}${p.site ? ` (a ${p.site})` : ''}`;
  for (const k of SD) $('sd-' + k).value = last[k] ?? $('sd-' + k).value;
  if (p.site) $('sd-kind').value = p.site;
  if (!last.walls) $('sd-walls').value = p.site === 'cave' || p.site === 'lair' ? 'natural cave' : 'cut stone';
  $('sd-levels').value = last.levels ?? 1;
  $('sd-theme').value = p.site_map?.theme ?? '';
  $('sd-seed').value = p.site_map?.seed ?? hexSeed(region, at);
  $('sd-what').textContent = p.site_map ? `Drawn before: ${p.site_map.name} (map ${p.site_map.seed}). Draw it again to replace the link.` : '';
  $('sd-model').textContent = 'Asking LM Studio…';
  try {
    const out = await post('/api/terrain-battle/suggest', { terrain: ctx.terrain === 'water' ? 'coast' : ctx.terrain });
    const names = service.creatures ?? [], first = out.suggested ?? [];
    $('sd-creature').replaceChildren(...[...first, ...names.filter(n => !first.includes(n))].map(n => new Option(n, n)));
  } catch { status('Site maps need Mythastria running (Start_Mythastria.bat).', true); return; }
  $('site-dialog').showModal();
  const m = await post('/api/site-map/model', {}).catch(() => ({ ok: false }));
  $('sd-model').textContent = !m.ok ? 'The service did not say whether the model is there.'
    : m.ready ? `Designed by ${m.model} in LM Studio (${m.url}).` : `${m.why} Start it, then Draw it.`;
};
$('sd-another').onclick = () => { $('sd-seed').value = Math.floor(Math.random() * 99999) + 1; };
$('sd-go').addEventListener('click', async e => {
  e.preventDefault();
  const place = region.locations.find(l => l.hex === siteHex);
  if (!place) { $('site-dialog').close(); return; }
  const at = unkey(place.hex), ctx = hexContext(region, at);
  const towns = region.locations.filter(l => l.kind === 'town' || l.kind === 'village');
  const prefs = { theme: $('sd-theme').value.trim(), levels: Math.min(3, Math.max(1, Number($('sd-levels').value) || 1)),
    seed: Number($('sd-seed').value) || 1 };
  for (const k of SD) prefs[k] = $('sd-' + k).value;
  region.design = { ...region.design, site: { kind: prefs.kind, size: prefs.size, layout: prefs.layout, walls: prefs.walls, doors: prefs.doors, levels: prefs.levels } };
  const body = { prefs, creature: $('sd-creature').value, count: Number($('sd-count').value) || 4,
    context: { terrain: ctx.terrain, road: ctx.road, river: ctx.river, sea: ctx.sea, climate: region.design?.prefs?.climate ?? 'temperate',
      region: region.name, place: placeLabel(place), note: place.note ?? '',
      town_miles: towns.length ? Math.min(...towns.map(t => distance(unkey(t.hex), at))) : null },
    project: projects.find(p => p.id === projectOfMap(mapId))?.name ?? 'Spare maps', region: region.name,
    place: `Place ${place.number}` };
  $('sd-go').disabled = true;
  const started = Date.now();
  const tick = setInterval(() => { $('sd-what').textContent = `The model is designing the site… ${Math.round((Date.now() - started) / 1000)} s`; }, 1000);
  const out = await post('/api/site-map', body).catch(() => ({ ok: false, error: 'The service did not answer.' }));
  clearInterval(tick); $('sd-go').disabled = false;
  if (!out.ok) { $('sd-what').textContent = `${out.error || 'The site could not be drawn.'} Nothing was made: try again, or another map number.`; return; }
  const kept = region.locations.find(l => l.hex === siteHex) ?? place;
  kept.map = out.scenarios[0];
  kept.site_map = { name: out.name, seed: prefs.seed, theme: prefs.theme, scenarios: out.scenarios, summary: out.summary };
  const made = `A ${prefs.kind}: ${out.name} (${out.rooms} rooms, ${out.levels} level${out.levels === 1 ? '' : 's'})`;
  if (!kept.note || /^A \w+(: click it, then Draw this site| \(the indoor generator will draw it\)|: .+ \(\d+ rooms, \d levels?\)$)/.test(kept.note)) kept.note = made;   // the made note, never the GM's own
  scenarios = [...new Set([...scenarios, ...out.scenarios])];
  region.log = [...region.log, `${clockText(region.party)}: ${placeLabel(kept)} drawn as ${out.name} (${out.rooms} rooms, ${out.levels} level${out.levels === 1 ? '' : 's'})`];
  $('site-dialog').close(); changed('party');
  const changedBy = out.fixes.length ? ` Mythastria changed: ${out.fixes.join(' ')}` : '';
  status(`${placeLabel(kept)} is ${out.name}: ${out.rooms} rooms on ${out.levels} level${out.levels === 1 ? '' : 's'}, designed by ${out.model?.model ?? 'the model'} in ${out.model?.seconds ?? '?'} s. Level 1 opens in Play live; the place leads to it (Places: Open map).${changedBy}`);
  await save();                                                        // kept before Play live opens (a reused tab would lose it)
  window.open('./play.html?scenario=' + encodeURIComponent(out.scenarios[0]), 'mythastria-battle', 'width=1400,height=900');
});

// ------------------------------------------------------------------ MAPGEN-01: a region from design preferences
// GM 2026-10-22: "the design preference seems do-able now for outdoor maps": generateRegion() (region-gen.mjs) makes
// it and draws its own picture in the table's miniature style, so a made region needs no picture of its own.
const MK = ['rugged', 'forest', 'wet', 'settlements', 'sites'];
function paintPicture(r) {
  const canvas = document.createElement('canvas');
  canvas.width = r.size[0]; canvas.height = r.size[1];
  renderRegionPicture(r, canvas.getContext('2d'));
  let pic = canvas.toDataURL('image/webp', .9);
  if (!pic.startsWith('data:image/webp')) pic = canvas.toDataURL('image/png');
  r.picture = pic;
}
const fillsHere = () => !!mapId && !worth(region);                   // an empty map in Maps (a place leads to it): fill it
$('make-region').onclick = () => {
  const p = { ...DEFAULT_PREFS, ...(region.design?.prefs ?? {}), ...(fillsHere() ? { name: region.name } : {}) };
  $('mk-climate').replaceChildren(...Object.entries(CLIMATES).map(([v, l]) => new Option(l, v)));
  $('mk-land').replaceChildren(...Object.entries(LANDS).map(([v, l]) => new Option(l, v)));
  $('mk-name').value = p.name || 'New region'; $('mk-size').value = p.size; $('mk-climate').value = p.climate; $('mk-land').value = p.land;
  for (const k of MK) $('mk-' + k).value = p[k];
  $('mk-roads').checked = p.roads !== false;
  $('mk-seed').value = region.design?.prefs ? p.seed : Math.floor(Math.random() * 99999) + 1;
  $('make-dialog').showModal();
};
$('mk-another').onclick = () => { $('mk-seed').value = Math.floor(Math.random() * 99999) + 1; };
$('mk-go').addEventListener('click', async e => {
  e.preventDefault();
  const prefs = { name: $('mk-name').value.trim() || 'New region', size: $('mk-size').value, climate: $('mk-climate').value,
    land: $('mk-land').value, roads: $('mk-roads').checked, seed: Number($('mk-seed').value) || 1 };
  for (const k of MK) prefs[k] = Math.max(0, Number($('mk-' + k).value) || 0);
  status('Making the region…');
  const made = generateRegion(prefs);
  paintPicture(made);
  made.design = { ...made.design, battle: region.design?.battle };
  if (keeping) await keeping;
  if (worth(region) && keepTimer) await keepNow();
  const here = fillsHere();
  region = keepOriginal(checkRegion(made), true); pictureSize = region.size; view = null; trip = null;
  $('make-dialog').close();
  const towns = region.locations.filter(l => l.kind !== 'site').length, sites = region.locations.length - towns;
  status(`${region.name}: ${towns} settlement${towns === 1 ? '' : 's'}, ${sites} site${sites === 1 ? '' : 's'}, ${(region.rivers ?? []).length} river${(region.rivers ?? []).length === 1 ? '' : 's'}; the party starts at place 1. Click a place to name it.`);
  if (!here) { mapId = null; setTrail([]); }                           // a new map in Maps; the one before stays there
  changed();
});
$('go').onclick = () => { if (trip) go(trip.path, false); };
$('rest').onclick = () => { const p = region.party, hours = (p.hour < 8 ? 8 - p.hour : 32 - p.hour); Object.assign(p, nextMorning(p)); region.log = [...region.log, `${clockText(p)}: rested ${Math.round(hours)} hours`]; $('trip').textContent = ''; changed('party'); };

// ------------------------------------------------------------------ places
let editing = null;
let scenarios = [];
function leadsOptions(p, portal = p?.kind === 'portal') {
  const sel = $('pd-map');
  const proj = projectOfMap(mapId), mine = maps.filter(m => m.id !== mapId && (m.project ?? null) === proj), others = maps.filter(m => m.id !== mapId && (m.project ?? null) !== proj);
  const groups = [['Maps in this project', mine.map(m => [`region:${m.id}`, m.name])], ['Other maps', others.map(m => [`region:${m.id}`, m.name])],
    ['', [['new-region', 'A new region map…']]], ['Tactical maps', portal ? [] : scenarios.map(n => [`scenario:${n}`, n])]];
  $('pd-leads').textContent = portal ? 'Jumps to' : 'Leads to';
  $('pd-portal').hidden = !portal;
  sel.replaceChildren(new Option('(nowhere)', ''), ...groups.filter(([, opts]) => opts.length).map(([label, opts]) => {
    const g = document.createElement('optgroup'); g.label = label || 'New'; for (const [v, l] of opts) g.append(new Option(l, v)); return g;
  }));
  sel.value = p?.to ? `region:${p.to.map}` : p?.map ? `scenario:${p.map}` : '';
}
function editPlace(hex) {
  editing = hex;
  const p = region.locations.find(l => l.hex === hex);
  $('pd-title').textContent = p ? `Place ${p.number}` : `Place ${nextNumber(region.locations)} (new)`;
  $('pd-name').value = p?.name ?? ''; $('pd-note').value = p?.note ?? '';
  $('pd-kind').value = p?.kind === 'portal' ? 'portal' : 'place';
  $('pd-twoway').checked = !p?.to?.hex;
  leadsOptions(p);
  $('pd-site-row').hidden = p?.kind !== 'site';
  $('pd-delete').hidden = !p; $('place-dialog').showModal(); $('pd-name').focus();
}
$('pd-kind').onchange = () => leadsOptions(region.locations.find(l => l.hex === editing), $('pd-kind').value === 'portal');
$('pd-save').addEventListener('click', async e => {
  e.preventDefault();
  const old = region.locations.find(l => l.hex === editing);
  const portal = $('pd-kind').value === 'portal';
  const place = { ...(old ?? {}), hex: editing, number: old?.number ?? nextNumber(region.locations), name: $('pd-name').value.trim(),
    note: $('pd-note').value.trim(), map: null, to: null, kind: portal ? 'portal' : (old?.kind === 'portal' ? undefined : old?.kind) };
  if (!place.kind) delete place.kind;
  const lead = $('pd-map').value;
  if (lead.startsWith('scenario:') && !portal) place.map = lead.slice(9);
  else if (lead.startsWith('region:')) place.to = { map: lead.slice(7), ...(old?.to?.map === lead.slice(7) && old.to.hex ? { hex: old.to.hex } : {}) };
  else if (lead === 'new-region') {                                   // a new, empty region map, filed in this map's project
    const fresh = newRegion(`${placeLabel(place)} (from ${region.name})`);
    const out = await post('/api/atlas/save', { map: fresh, project: projectOfMap(mapId) ?? projectId });
    if (!out.ok) { status(out.error || 'The new map could not be kept.', true); return; }
    place.to = { map: out.id };
  }
  region.locations = [...region.locations.filter(l => l.hex !== editing), place];
  $('place-dialog').close(); changed('party');
  if (tool === 'place') setTool('place');                             // one place at a time: the tool goes down
  status(`${portal ? 'Portal' : 'Place'} ${placeLabel(place)} is on the map${place.to ? (portal ? ': click it to jump' : ' and leads to another map (Places: Open map)') : ''}.`);
  if (portal && place.to && $('pd-twoway').checked && !place.to.hex) {  // two-way: go there and click where it comes out
    if (keeping) await keeping;
    await keepNow();
    const from = { fromMap: mapId, fromHex: place.hex, fromName: region.name };
    await openMap(place.to.map, { back: true });
    portalEnd = from; setTool('portal-end');
  }
});
$('pd-delete').addEventListener('click', e => {
  e.preventDefault();
  region.locations = region.locations.filter(l => l.hex !== editing);
  $('place-dialog').close(); changed('party');
});

// ------------------------------------------------------------------ pointer: tools, pan and zoom
let drag = null, zoomTimer = 0;
$('region').addEventListener('pointerdown', e => {
  e.preventDefault(); $('region').setPointerCapture(e.pointerId);
  const brush = e.button === 0 && (tool?.startsWith('paint:') || tool === 'reveal' || tool === 'hide') && !PLAYER;
  drag = { x: e.clientX, y: e.clientY, view: [...view], moved: false, pan: e.button !== 0 || (!tool && true), brush };
  if (brush) applyBrush(pointAt(e));
});
$('region').addEventListener('pointermove', e => {
  if (!drag) return;
  if (Math.hypot(e.clientX - drag.x, e.clientY - drag.y) > 4) drag.moved = true;
  if (drag.brush) { applyBrush(pointAt(e)); return; }
  if (drag.pan && drag.moved) {
    const r = $('region').getBoundingClientRect(), k = Math.max(view[2] / r.width, view[3] / r.height);
    view = [drag.view[0] - (e.clientX - drag.x) * k, drag.view[1] - (e.clientY - drag.y) * k, view[2], view[3]];
    $('region').setAttribute('viewBox', view.join(' '));
  }
});
$('region').addEventListener('pointerup', e => {
  const d = drag; drag = null;
  if (!d) return;
  if (d.brush) { if (region.design?.made) { paintPicture(region); cache = {}; draw(); } save(); return; }   // MAPGEN-01: repaint
  if (!d.moved && e.button === 0 && !PLAYER) onClick(pointAt(e));
});
function zoomAt(x, y, f) {                                         // f < 1 zooms in, about the picture point (x, y)
  if (!view) return;
  view = [x - (x - view[0]) * f, y - (y - view[1]) * f, view[2] * f, view[3] * f];
  $('region').setAttribute('viewBox', view.join(' '));
  clearTimeout(zoomTimer); zoomTimer = setTimeout(draw, 120);        // markers re-sized for the new zoom
}
$('region').addEventListener('wheel', e => {
  e.preventDefault();
  const [x, y] = pointAt(e);
  zoomAt(x, y, Math.exp(e.deltaY * .0012));
}, { passive: false });
// MAP-ZOOM-01 (GM 2026-10-28: "every map needs a zoom out and in"): + and − about the middle of the view, Fit the whole picture
const middle = f => view && zoomAt(view[0] + view[2] / 2, view[1] + view[3] / 2, f);
zoomButtons($('region'), { zoomIn: () => middle(.8), zoomOut: () => middle(1.25), reset: () => { view = null; draw(); } });
$('region').addEventListener('contextmenu', e => e.preventDefault());
addEventListener('keydown', e => {
  if (e.key === 'Escape' && tool && !document.querySelector('dialog[open]')) { const one = tool === 'portal-end'; portalEnd = null; setTool(tool); status(one ? 'A one-way portal: it leads here, with no way back.' : 'Tool put down.'); }
});

// ------------------------------------------------------------------ controls
for (const b of document.querySelectorAll('[data-tool]')) if (!b.dataset.tool.startsWith('paint:')) b.onclick = () => setTool(b.dataset.tool);
for (const b of document.querySelectorAll('[data-nudge]')) b.onclick = () => { const [dx, dy] = b.dataset.nudge.split(',').map(Number), s = region.grid.pxPerMile / 10; region.grid = nudgeGrid(region.grid, dx * s, dy * s); changed(); };
for (const b of document.querySelectorAll('[data-scale]')) b.onclick = () => { region.grid = nudgeGrid(region.grid, 0, 0, Number(b.dataset.scale)); changed(); };
for (const id of ['show-terrain', 'show-fog']) $(id).onchange = () => draw();
for (const s of SCALES) $('show-' + s.miles).onchange = () => {   // kept with the region, so the players' window shows the same grids
  region.grids = { ...region.grids, [s.miles]: $('show-' + s.miles).checked }; draw(); save();
};
$('name').onchange = () => { region.name = $('name').value.trim() || 'Region'; save(); };
$('pace').onchange = () => { region.party.pace = $('pace').value; save(); drawPanel(); if (trip?.to) plan(trip.to); };
for (const k of ['cold', 'heat', 'water', 'wind', 'sand', 'rain', 'altitude']) $('w-' + k).onchange = () => {   // HAZARDS-01
  region.environment = { ...(region.environment ?? {}), [k]: $('w-' + k).checked }; save(); drawPanel(); if (trip?.to) plan(trip.to);
};
$('enc-chance').onchange = () => { region.encounters = { ...region.encounters, chance: Math.max(0, Math.min(20, Number($('enc-chance').value) || 0)) }; save(); };
$('pick-picture').onclick = () => $('picture').click();
$('picture').onchange = () => {
  const f = $('picture').files[0]; if (!f) return;
  const reader = new FileReader();
  reader.onload = () => { const img = new Image(); img.onload = () => {
    if (region.original && !('picture' in region.original)) region.original.picture = region.picture ?? null;   // Reset brings it back
    region.picture = reader.result; region.size = [img.naturalWidth, img.naturalHeight]; pictureSize = region.size; view = null;
    keepOriginal(region);                                              // a first picture on an empty map: its design starts here
    status('Picture loaded. Align the hex grid: "Align to printed hexes" if the picture has hexes, else "Survey".'); changed(); }; img.src = reader.result; };
  reader.readAsDataURL(f);
};
function exportRegion() {
  const a = document.createElement('a'); a.href = URL.createObjectURL(new Blob([JSON.stringify(region)], { type: 'application/json' }));
  a.download = (region.name || 'region').replace(/[^\w -]/g, '') + '.region.json'; a.click(); setTimeout(() => URL.revokeObjectURL(a.href), 5000);
  return a.download;
}
$('export').onclick = () => exportRegion();

// 2026-10-22 (GM: "the Region map needs a new button that clears the screen but offers to save first"): Clear... asks
// first, and can save a copy (the same file as Export) before it starts an empty region map.
function clearRegion() {
  if (tool) setTool(tool);
  region = newRegion(); mapId = null; setTrail([]); pictureSize = [1000, 700]; view = null; trip = null; cache = {};
  try { localStorage.removeItem(CURRENT); } catch { /* fine */ }
  $('go').hidden = $('go-fast').hidden = true; $('trip').textContent = '';
  $('clear-dialog').close(); changed(); refreshAtlas();
}
$('reset-region').onclick = () => {
  if (!region.original) { status('This map has no original design to go back to yet (make, import or load a picture first).', true); return; }
  const o = region.original, places = o.locations?.length ?? 0;
  $('rs-what').textContent = `${region.name || 'The region'} goes back to its original design` + (o.name && o.name !== region.name ? ` (${o.name})` : '') +
    `: ${places} place${places === 1 ? '' : 's'}. The party is taken off the map (place it again to begin).`;
  $('reset-dialog').showModal();
};
$('rs-go').addEventListener('click', e => {
  e.preventDefault(); $('reset-dialog').close();
  resetRegion(); status(`${region.name} is back to its original design. Place the party to begin.`);
});
$('clear-region').onclick = () => {
  const places = region.locations.length;
  $('cl-what').textContent = `This replaces ${region.name || 'the region'}` + (region.picture ? ', its picture' : '') +
    (places ? `, ${places} place${places === 1 ? '' : 's'}` : '') + ' and the party\'s travels with an empty region map.';
  $('clear-dialog').showModal();
};
$('cl-save').addEventListener('click', async e => {
  e.preventDefault(); const name = region.name;
  if (keeping) await keeping;
  if (worth(region)) await keepNow();
  clearRegion(); status(`${name} is kept in Maps; this is a new, empty map.`);
});
$('cl-clear').addEventListener('click', async e => {
  e.preventDefault();
  if (keeping) await keeping;
  clearTimeout(keepTimer);
  if (mapId) await post('/api/atlas/delete', { id: mapId });
  clearRegion(); status('Deleted and cleared. Load a picture, or Make a region...');
});
$('atlas-open').onclick = () => { const id = $('atlas-list').value; if (id && id !== mapId) { setTrail([]); openMap(id); } };
$('atlas-project').onchange = () => { showProject(pid($('atlas-project').value)); refreshAtlas(); };
$('atlas-move').onchange = async () => {
  if (!mapId) return;
  const to = pid($('atlas-move').value);
  await post('/api/atlas/move', { id: mapId, project: to }); showProject(to); await refreshAtlas();
  status(`${region.name} is filed in ${projects.find(p => p.id === to)?.name ?? 'Spare maps'}.`);
};
let projectAction = null;
function projectDialog(title, name, action) { $('pj-title').textContent = title; $('pj-name').value = name; projectAction = action; $('proj-dialog').showModal(); $('pj-name').focus(); }
$('pj-go').addEventListener('click', async e => {
  e.preventDefault();
  const name = $('pj-name').value.trim(); if (!name) { $('pj-name').focus(); return; }
  $('proj-dialog').close(); await projectAction(name); await refreshAtlas();
});
$('proj-new').onclick = () => projectDialog('New project', '', async name => {
  const out = await post('/api/atlas/project', { action: 'create', name });
  if (out.ok) { showProject(out.project); status(`${name}: a new project. New maps are filed here; "File this map in" moves the open one.`); }
  else status(out.error, true);
});
$('proj-rename').onclick = () => { const p = projects.find(x => x.id === projectId); if (p) projectDialog('Rename the project', p.name, async name => { await post('/api/atlas/project', { action: 'rename', project: p.id, name }); }); };
$('proj-delete').onclick = () => {
  const p = projects.find(x => x.id === projectId); if (!p) return;
  $('dl-title').textContent = 'Delete this project?';
  $('dl-what').textContent = `${p.name} goes; its ${p.maps} map${p.maps === 1 ? '' : 's'} move${p.maps === 1 ? 's' : ''} to Spare maps (no map is deleted).`;
  $('dl-go').onclick = async ev => { ev.preventDefault(); $('delete-dialog').close(); await post('/api/atlas/project', { action: 'delete', project: p.id }); showProject(null); await refreshAtlas(); status(`${p.name} deleted; its maps are in Spare maps.`); };
  $('delete-dialog').showModal();
};
$('proj-export').onclick = async () => {
  if (keeping) await keeping;
  if (worth(region) || mapId) await keepNow();
  const out = await post('/api/atlas/export', { project: projectId });
  if (!out.ok) { status(out.error, true); return; }
  const a = document.createElement('a'); a.href = URL.createObjectURL(new Blob([JSON.stringify(out.bundle)], { type: 'application/json' }));
  a.download = out.bundle.name.replace(/[^\w -]/g, '') + '.project.json'; a.click(); setTimeout(() => URL.revokeObjectURL(a.href), 5000);
  status(`${out.bundle.name}: ${out.bundle.maps.length} map${out.bundle.maps.length === 1 ? '' : 's'} saved as ${a.download}.`);
};
$('proj-import').onclick = () => $('proj-import-file').click();
$('proj-import-file').onchange = async () => {
  const f = $('proj-import-file').files[0]; if (!f) return;
  try {
    const out = await post('/api/atlas/import', { bundle: JSON.parse(await f.text()) });
    if (!out.ok) throw new Error(out.error);
    showProject(out.project); await refreshAtlas(); status('Project imported: open its maps from the list.');
  } catch (err) { status('Could not import: ' + err.message, true); }
};
$('atlas-back').onclick = () => { const t = trail(), back = t.pop(); setTrail(t); if (back?.id) openMap(back.id); };
$('atlas-delete').onclick = () => {
  const id = $('atlas-list').value, m = maps.find(x => x.id === id);
  if (!m) return;
  $('dl-title').textContent = 'Delete this map?';
  $('dl-what').textContent = `${m.name} will be deleted from Maps` + (m.linked_from.length ? `; ${m.linked_from.length} map${m.linked_from.length === 1 ? '' : 's'} lead${m.linked_from.length === 1 ? 's' : ''} to it and will lead nowhere.` : '.');
  $('dl-go').onclick = async ev => {
    ev.preventDefault(); $('delete-dialog').close();
    await post('/api/atlas/delete', { id });
    if (id === mapId) clearRegion(); else await refreshAtlas();
    status(`${m.name} is deleted.`);
  };
  $('delete-dialog').showModal();
};
$('import').onclick = () => $('import-file').click();
$('import-file').onchange = async () => {
  const f = $('import-file').files[0]; if (!f) return;
  try {
    if (keeping) await keeping;
    if (worth(region) && keepTimer) await keepNow();
    const here = fillsHere();
    region = keepOriginal(numbered(checkRegion(JSON.parse(await f.text()))), true); if (!here) { mapId = null; setTrail([]); }
    pictureSize = region.size ?? [1000, 700]; view = null;
    status(here ? 'Region imported into this map.' : 'Region imported as a new map in Maps.'); changed();
  }
  catch (e) { status('Could not import: ' + e.message, true); }
};
$('player-view').onclick = () => window.open('./region.html?view=player', 'mythastria-region-player', 'width=1200,height=850');
channel && (channel.onmessage = async () => { if (!PLAYER) return; const r = await load(); if (r) { region = r; pictureSize = r.size ?? pictureSize; cache = {}; draw(); } });

addEventListener('DOMContentLoaded', async () => {
  if (PLAYER) { document.body.classList.add('player-view'); document.title = 'Mythastria — Region (players)'; $('status').hidden = true; }
  drawPalette();
  const kept = await load();
  if (kept) { try { useRegion(kept, null); status(region.picture ? `${region.name}: ${clockText(region.party)}.` : 'Load a picture of the region to begin.'); } catch { region = newRegion(); } }
  draw();
  if (PLAYER) return;
  try { const h = await hello(); scenarios = (h.scenarios ?? []).filter(n => !n.startsWith('test/')); } catch { scenarios = []; }
  let want = null;
  try { want = localStorage.getItem(CURRENT); } catch { /* fine */ }
  await refreshAtlas();
  if (want && maps.some(m => m.id === want)) {                       // the map open last time, from Maps
    const out = await post('/api/atlas/get', { id: want });
    if (out.ok) { useRegion(out.map, want); showProject(projectOfMap(want)); draw(); await refreshAtlas(); status(`${region.name}: ${clockText(region.party)}.`); }
  } else if (want) {                                                   // the map open last time was deleted: never bring it back
    region = newRegion(); mapId = null; setTrail([]); pictureSize = [1000, 700]; view = null; cache = {};
    try { localStorage.removeItem(CURRENT); } catch { /* fine */ }
    draw(); await refreshAtlas(); status('The map open last time was deleted. Open one from Maps, or start a new one.');
  } else if (worth(region)) await keepNow();                          // this browser's region joins Maps the first time
});
