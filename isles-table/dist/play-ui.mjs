// The Play live page (LIVE-PLAY-01): a simulator fight in which the people at the table play the characters. The
// simulator runs the fight and waits on each character's turn; this page shows the acting character's sheet, lets an
// attack card be dragged (pointer: mouse or touch) onto a token, or a square be clicked to move, and sends the choice.
// Targets light up from the simulator's own offers; the simulator checks the choice again and rolls. See play-view.mjs.
import { asset, api } from './server.mjs';   // PLAYER-SITE-01: pictures from the GM's PC
import { liveSync, SYNC_CHANNEL } from './play-view.mjs';
import { liveView, targetLook, cardText, actionText, createLivePort, reachPath, reachOutline, SPELL_KEY, spellOf, spellCardText,
  slotsText, concentrationBreak, spellLook, aimPreview, spellExtras, effectFromCast, castEffects, newCastEffects, liveMoved, auraEffects, actionButtons, doorButtons, doorAim, doorText, ACT_KEY, actLook, actCommand, mergeExplored, fogCells, playerCombatants, withDoors,
  layerEffects, ZONE_LOOK, invisibleLook, layerOrder, mountButtons, mountText,
  notePins, upsertNote, deleteNote, noteAt, sorceryText, metamagicFields, metamagicNote, twinArmed, TRANSMUTE, fontButtons,
  itemButtons, bagText, FEATURE_OPS, turnLights, rollLine, trapMarks, squareCommand, attackExtras, focusText,
  AMBIENT_LABEL, VEIL, seenLights, lightRings, groundLights, conePath, lightButtons, lightText } from './play-view.mjs';
import { createChatPort } from './table-chat.mjs';
import { palettes, effectGraphic } from './effects.mjs';
import { mountFlavor } from './flavor-ui.mjs';
import { paintPicture } from './flavor-paint.mjs';
import { ROLES, actorFlavorKey, flavorOf, flavorLabel, flavorActor, flavorEffect } from './flavor.mjs';
import { loadCatalog, loadFlavorArt } from './catalog.mjs';
// PLAYER-PACKAGE-01: remix-panel.mjs, director-ui.mjs, map-picker.mjs and dm-swap-ui.mjs are the GM's alone, loaded only on the GM
// console (below); the players' door never serves them (player-client/build_player_client.py)
import { mountZoom, zoomButtons } from './map-zoom.mjs';   // MAP-ZOOM-01 (GM 2026-10-28: "every map needs a zoom out and in")
import { createThirdPerson } from './third-person.mjs';
import { ceilingAt } from './scene-math.mjs';
import { propMarker } from './props3d.mjs';
import { PHOTO_KEY, MAX_PHOTOS, loadPhotos, savePhotos, decorate, rosterFrom, sheetFor, addPhoto, removePhoto, setActive, linkSheet,
  photoFromFile } from './character-photos.mjs';
import { ACTIONS, comboOf, actionFor, rebind, clearKeys, loadKeymap, saveKeymap, DEFAULT_KEYS, label } from './camera-keys.mjs';
import { drawWalls2D, drawGround2D, drawWater2D } from './wall-art.mjs';
import { barItems, targetList, creatureTip, squareTip, reachEdge3D, BAR_KEYS } from './tp-bar.mjs';
import { gridFromCorners, gridFromDistance, nudge, gridSquares, squareAt as pictureSquare, squareLight, draftFromLight, newCells, paint, kindAt, cellLists,
  wallRound, imageType } from './map-survey.mjs';
import { consoleLevel, setConsoleLevel, seatLevel, setSeatLevel, mutedKinds, setMuted, hintLine, spellWarning, drawSwitch,
  drawLine, lowerLevel, attackFacts, reachFacts, areaFacts, drawFacts } from './hints-ui.mjs';   // HINTS-01: turn reminders, opt-in
import { loadSeat } from './seat-ticket.mjs';
import { createMapPaint } from './map-paint.mjs';     // MAP-PAINT-01: the GM's paint over the map
import { renderSheet } from './character-sheet-view.mjs';         // GM 2026-10-28: the Full sheet tab
import { mergeRoster, loadTableParty } from './party-store.mjs';   // GM 2026-10-25: the table's party follows the GM role
import { mountScene, sideColour } from './scene-ui.mjs';              // GM 2026-10-24: attitudes and morale (sim/attitude.py)
import { mountPillar, inScene, sceneStatus } from './pillar-ui.mjs';  // GM 2026-10-26: social and exploration scenes (sim/scenes.py)
import { trackerRows, trackerTitle, trackerMoved, drawTracker, mapHealth, attitudeColour, sightGrid, sightPicks, drawSightGrid } from './combat-tracker.mjs';   // COMBAT-TRACKER-01

const $ = id => document.getElementById(id), NS = 'http://www.w3.org/2000/svg';
const svg = (tag, attrs = {}, text) => {
  const e = document.createElementNS(NS, tag);
  for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, String(v));
  if (text !== undefined) e.textContent = String(text);
  return e;
};
const el = (tag, cls, text) => { const e = document.createElement(tag); if (cls) e.className = cls; if (text !== undefined) e.textContent = String(text); return e; };
let armed = { metas: [], transmute: 'cold' }, armedFor = null;   // GM 2026-10-23: Metamagic chosen before a spell
let lastRolls = {}, rollsFor = null, sheetTab = 'turn';          // GM 2026-10-24: the sheet's roll lines and tab
let attackPicks = {};                                              // GM 2026-10-26: an attack's mastery / Stealth Attack
const dicePort = createChatPort();
const LOOK = { 'legal-foe': ['#7fd08a', .1], 'legal-ally': ['#e0b050', .08], refused: ['#e07a6a', .05], self: [null, 0] };

const port = createLivePort();
let pointedActor = null;                                          // the token under the pointer (3D tips, HINTS-01 facts)
let casting = null, fx = [], fxSeen = new Set(), aimAt = null, routeTo = null, thirdPerson = null, mode = 'tactical', keymap = loadKeymap(), byId = new Map();
let mapPicker = null;                                            // GM 2026-10-25: map-picker.mjs
let standIn = null;                                              // GM 2026-10-28: the character the GM plays, in the pop-out (drawStandIn)
let registry = null, flavorArt = [], scenario = null, snap = null, view = null, held = null, logSince = 0, busy = false, poll = null, fightStarted = false;
// VIEW-01 (GM 2026-10-20): ?view=player is the players' window (map only, fog, unseen creatures left out, no clicks);
// the fog comes from the simulator's party sight; explored squares are kept per map in this browser.
const PLAYER = new URLSearchParams(location.search).get('view') === 'player';
const MAP_WINDOW = PLAYER && new URLSearchParams(location.search).get('window') === 'map';   // GM 2026-10-28: a player's map window
const mapPaint = createMapPaint({ port, player: PLAYER, onStatus: status, onChange: () => { drawMap(); paintBar(); } });   // MAP-PAINT-01
mapPaint.attach($('map'));
const mapZoom = mountZoom($('map'));                             // MAP-ZOOM-01: drawMap gives it the whole picture
if (PLAYER) setInterval(() => { if (view?.map?.name) mapPaint.follow(view.map.name); }, 3000);
// GM 2026-10-27 ("I need turn and action on left side in landscape"): on the GM console in landscape the turn sheet (turn
// bar, attacks, spells, actions) and the Result go to a column left of the map; in portrait, on a narrow screen and in the
// players' window they stay in the side column, before What happened, as before. The header's Layout picks it: Landscape
// always, Portrait never, Auto by the screen (landscape and 1000 px wide or more).
const TURN_LEFT = matchMedia('(orientation: landscape) and (min-width: 1000px)');
// GM 2026-10-28 ("the combat tracker needs to be a small table on the left of the map. The Turn and actions need to be on
// the right of the map. All other sections need to be collapsed"): the players' table (each player client, the pop-out)
// puts the tracker in the left column, the turn sheet first in the right one, and folds every other section there.
function foldable(section) {
  const key = 'mythastria-fold:' + section.id, h = section.querySelector(':scope > h2');
  if (!h || section.classList.contains('foldable')) return;
  let open = false;
  try { open = localStorage.getItem(key) === '1'; } catch { /* folded */ }
  section.classList.add('foldable');
  section.classList.toggle('folded', !open);
  h.tabIndex = 0; h.setAttribute('role', 'button'); h.setAttribute('aria-expanded', String(open));
  const flip = () => {
    const folded = section.classList.toggle('folded');
    h.setAttribute('aria-expanded', String(!folded));
    try { localStorage.setItem(key, folded ? '0' : '1'); } catch { /* this visit only */ }
  };
  h.addEventListener('click', flip);
  h.addEventListener('keydown', e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); flip(); } });
}
function placeTurnSide() {
  if (PLAYER) {
    document.querySelector('main').classList.add('player-3col');
    document.body.classList.toggle('map-window', MAP_WINDOW);
    $('turn-side').append($('tracker-panel'));
    document.querySelector('.side-col').prepend($('sheet-panel'));
    for (const s of document.querySelectorAll('.side-col > section.panel')) if (s.id !== 'sheet-panel') foldable(s);
    return;
  }
  const layout = document.documentElement.dataset.layout || 'auto';
  const left = !PLAYER && (layout === 'landscape' || (layout === 'auto' && TURN_LEFT.matches));
  const sheet = $('sheet-panel'), result = $('result-panel');
  document.querySelector('main').classList.toggle('turn-left', left);
  if (left) $('turn-side').append(sheet, result);
  else $('log-panel').before(sheet, result);
}
placeTurnSide();
TURN_LEFT.addEventListener('change', placeTurnSide);
new MutationObserver(placeTurnSide).observe(document.documentElement, { attributes: true, attributeFilter: ['data-layout'] });
// VIEW-02 (GM 2026-10-20: "I want the actual map with full functionality be able to pop out and the tokens fully functioning
// and draggable. The commands will still be on the main console."): the pop-out (?view=player) is this page's live map on
// the same live session; it moves tokens, opens doors and uses the main console's held attack or spell itself, and the
// two windows tell each other what changed (play-view.mjs liveSync). The pop-out keeps the fog and hides GM-only things.
const sync = typeof BroadcastChannel === 'function' ? liveSync({ channel: new BroadcastChannel(SYNC_CHANNEL), refresh: () => refresh(),
  onSelect: s => { if (!PLAYER) return; held = s.held; casting = s.casting; if (!casting) aimAt = null; drawMap(); },
  onUsed: () => { if (PLAYER) return; held = null; casting = null; aimAt = null; drawMap(); drawSheet(); },
  onResult: (text, cls) => { if (!PLAYER) result(text, cls); } }) : { changed() {}, select() {}, used() {}, result() {} };
let explored = [], fogKey = '', showFog = true, revealed = false;
// VIEW-01: each party member's character sheet (the Characters workshop's roster) and its photo on the token
let photos = loadPhotos(), photoTokens = new Map();
// VIEW-01: the GM's notes for this map (kept by the service), the Notes mode, the note being edited
let notes = [], notesMap = null, notesAt = 0, noteMode = false, editing = null;
// GM 2026-10-24 (SRD traps, sim/traps.py): a square pick waiting for a click (Search/Study a square, gear, climbing out),
// and the GM's trap tool (kind and band chosen; a click places; the statue and the stone take a second click)
let squarePick = null, trapMode = false, trapFirst = null, trapCatalog = null;
let hazardMode = false, hzPicks = [], hzCatalog = null;           // HAZARDS-01: the GM's hazard tool (squares picked)

// Flavor (flavor.mjs) is presentation only: read the simulator's creatures and offers; never decorate snap or a command.
// basePictures: each creature's picture before Flavor (catalog art or sheet photo), the one a paint goes on; paintTokens: painted copies for 3D
let basePictures = new Map(), paintTokens = new Map();
// the adventure this fight belongs to (its map is pack/<adventure>/...): a paint lasts for the adventure
const adventureOf = () => scenario?.source_scenario?.startsWith('pack/') ? scenario.source_scenario.split('/')[1] : null;
// Pictures Flavor may give a creature: the catalog's and the extra artwork (flavor-art.json). Default art still comes
// from the catalog alone (liveView).
const flavorPictures = () => [...(registry ?? []), ...flavorArt];
function flavorContext() { return { scope: view?.map.name, fightId: snap?.fight_id, actors: snap?.state?.combatants ?? [], offers: snap?.offers, registry: flavorPictures(),
  basePicture: id => basePictures.get(id) ?? '', adventure: adventureOf() }; }
// FLAVOR-01: Mythastria keeps the Flavor, so players on their own devices see it. PLAYER-FLAVOR-01: a player asks for a look
// for the creatures they control, and the GM approves it (Asked of the GM)
const flavor = mountFlavor({ button: $(PLAYER ? 'my-flavor' : 'flavor-open'), context: flavorContext, painter: paintPicture, player: PLAYER,
  remote: { load: (rev, asksRev) => port.flavor(rev, asksRev), save: PLAYER ? null : (state, rev) => port.saveFlavor(state, rev),
    ask: (actor, record) => port.askFlavor(actor, record), rule: (actor, approve) => port.ruleFlavor(actor, approve) }, changed: message => {
  if (message) { status(message); return; }
  if (snap) { buildView(); drawMap(); drawSheet(); }
  drawAsks(); drawMyFlavor();
} });
function drawMyFlavor() {                                           // a player's button, and the mark while a look waits
  if (!PLAYER) return;
  const waiting = Object.keys(flavor.mine.pending).length;
  $('my-flavor').hidden = !flavor.mine.actors.length;
  $('my-flavor-note').hidden = !waiting;
  $('my-flavor-note').textContent = waiting ? 'Pending: the GM has not approved your new look yet.' : '';
}
const rulesActor = id => snap?.state?.combatants.find(c => c.id === id);
function flavorFor(kind, key = '', actor = rulesActor(snap?.waiting)) {
  return actor ? flavorOf(flavor.state, view?.map.name, actorFlavorKey(actor), kind, key) : {};
}
const spellVisual = (effect, actor, spell) => flavorEffect(effect, flavor.state, view?.map.name, actor, spell);
// the rules name on the GM's console only: a creature the GM dressed up stays dressed up in the players' window
const flavorTip = c => (!PLAYER && c?.rules_name && c.rules_name !== c.name ? ' · Rules: ' + c.rules_name : '') + (c?.flavor_description ? ' · ' + c.flavor_description : '');

function status(text, isError = false) { $('status').textContent = text; $('status').className = isError ? 'error' : ''; }
function result(text, cls = '') {
  $('result').textContent = text; $('result').className = cls;
  if (PLAYER && text) sync.result(text, cls);                    // VIEW-02: the main console shows what the pop-out did
}

async function loadRegistry() {
  registry = await loadCatalog();                               // creatures.json (2026-10-20: no WASM for the art)
  flavorArt = await loadFlavorArt();                            // GM 2026-10-23: the newer token art, a Flavor choice only
  byId = new Map(flavorPictures().map(t => [t.id, t]));
}

function bounds(v) {
  const m = v.map, pts = v.state.combatants.filter(c => c.x > -50 && c.y > -50);
  if (!pts.length) return [0, 0, m.cols, m.rows];
  // 2026-10-20 (GM: a larger walled map): the whole map, widened only if a creature stands outside it
  const xs = pts.map(c => c.x), ys = pts.map(c => c.y);
  return [Math.min(0, Math.floor(Math.min(...xs))), Math.min(0, Math.floor(Math.min(...ys))),
    Math.max(m.cols, Math.ceil(Math.max(...xs)) + 1), Math.max(m.rows, Math.ceil(Math.max(...ys)) + 1)];
}

// GM 2026-10-24 ("corpses become barriers. They should not block movement or targeting"): a creature at 0 HP that is not
// a player character is dead, an object: under the living on the map, never the token a click or a drop lands on.
const corpse = c => !!c?.down && !c.pc;
// COMBAT-TRACKER-01 (GM 2026-10-27: "We need a combat tracker"): how a token or a tracker row looks while a card is held
function tokenLook(c, offers = snap?.offers) {
  return held ? lookFor(held, c) : casting?.shape === 'creatures' ? (casting.picks.includes(c.id) ? { cls: 'legal-foe', reason: '' } : spellLook(casting, c, offers)) : { cls: '', reason: '' };
}
let marked = null;                                                 // the token a tracker row highlights
function drawTrackerPanel() {
  const box = $('tracker-panel'), cs = view?.state.combatants ?? [];
  box.hidden = !snap?.tracker || !!snap.tracker.scene;
  if (box.hidden) return;
  if (marked && !cs.some(c => c.id === marked)) marked = null;
  drawTracker($('tracker-body'), trackerRows(snap, cs, { player: PLAYER }), { title: trackerTitle(snap, cs), marked, onRow: trackerPick,
    onAttitude: PLAYER ? null : setAttitude, onSight: PLAYER || snap.done ? null : openSight,
    look: id => { const c = cs.find(x => x.id === id); return c && (held || casting) ? tokenLook(c) : { cls: '', reason: '' }; } });
}
// A click on a row: with an attack or a spell held, that creature is its target (the map's own paths); else its token is marked
// GM 2026-10-27: a creature's disposition from the tracker (the engine's attitude, sim/attitude.py)
async function setAttitude(id, attitude) {
  const out = await port.scene({ op: 'attitude', creature: id, attitude }).catch(() => ({ ok: false, error: 'The service stopped.' }));
  if (out.live) take(out);
  if (!out.ok) result(out.refused || out.error || 'Refused.', 'refused');
}
// SIGHT-01 (GM 2026-10-27): which creatures each character sees; asked once when a fight starts, and on the tracker
let sightAsked = null, sightG = null, sightTicks = null;
function openSight() {
  sightG = sightGrid(snap, view?.state.combatants);
  if (!sightG?.pcs.length || !sightG.creatures.length) { result('No character is standing, or no creature is left to see.'); return; }
  sightTicks = new Set(sightG.ticked);
  drawSightGrid($('sight-grid'), sightG, sightTicks);
  $('sight-dialog').showModal();
}
$('sight-ok').addEventListener('click', async e => {
  e.preventDefault();
  const out = await port.sight(sightPicks(sightG, sightTicks)).catch(() => ({ ok: false, error: 'The service stopped.' }));
  $('sight-dialog').close();
  if (out.ok) take(out); else result(out.error || 'Not saved.', 'refused');
});
$('sight-cancel').addEventListener('click', e => { e.preventDefault(); $('sight-dialog').close(); });
function trackerPick(id) {
  if (held) { dropOn(id); return; }
  if (casting) {
    if (casting.shape === 'creatures') { pickForCast(id); return; }
    const c = view?.state.combatants.find(x => x.id === id);
    if (c) cast({ spell: casting.name, x: Math.round(c.x), y: Math.round(c.y) });   // an area: aimed at its square
    return;
  }
  marked = marked === id ? null : id;
  drawMap();
}
// GM 2026-10-28: a spell for up to N creatures dropped (or clicked) on a creature: that creature is picked; it is cast
// at once when the spell's creatures are all picked, else the next drop or click adds one and Cast sends it
// Bless upcast: one more creature for each level above its own (the Cast at dropdown)
const withLevel = s => s.extra_targets_per_level && spellLevelPick[s.name] > s.level
  ? { ...s, max_targets: s.max_targets + s.extra_targets_per_level * (spellLevelPick[s.name] - s.level) } : s;
function addToCast(s, id) {
  if (casting?.name !== s.name) casting = { ...withLevel(s), picks: [], points: [], points_max: s.points };
  pickForCast(id);
  const left = casting.max_targets - casting.picks.length;
  if (casting.picks.length && left <= 0) { cast({ spell: casting.name, targets: casting.picks }); return; }
  const names = casting.picks.map(i => view?.state.combatants.find(c => c.id === i)?.name ?? i).join(', ');
  if (casting.picks.length) result(`${s.name} on ${names}: drop it on up to ${left} more creature${left === 1 ? '' : 's'} (or click them), or press Cast ${s.name}. Esc cancels.`);
}
function pickForCast(id) {
  if (!casting.targets?.includes(id)) { result(casting.refused?.[id] ?? 'Not a legal target.', 'refused'); return; }
  casting.picks = casting.picks.includes(id) ? casting.picks.filter(x => x !== id) : casting.picks.length < casting.max_targets ? [...casting.picks, id] : casting.picks;
  drawMap(); drawSheet();
}
function drawMap() {
  const root = $('map');
  root.replaceChildren();
  if (!view) {                                        // 2026-10-20: an empty board looked like nothing had loaded
    mapZoom.view(0, 0, 10, 6);
    root.append(svg('text', { x: 5, y: 2.7, 'text-anchor': 'middle', 'font-size': .42, class: 'board-hint' }, 'No fight yet'),
      svg('text', { x: 5, y: 3.4, 'text-anchor': 'middle', 'font-size': .24, class: 'board-hint' }, PLAYER ? 'The GM starts the fight; it shows here.' : 'Choose a map and a party above, then press Start live fight.'));   // GM 2026-10-25: player words
    return;
  }
  const [x0, y0, x1, y1] = bounds(view), offers = snap?.offers;
  const solid = (view.map.wall_cells ?? []).length > 0, pad = solid ? 1.5 : .2;   // MAP RULE: room for the stone fading past the edge
  mapZoom.view(x0 - pad, y0 - pad, x1 - x0 + 2 * pad, y1 - y0 + 2 * pad);   // MAP-ZOOM-01: the part zoomed in on
  if (PLAYER) root.append(svg('rect', { x: x0, y: y0, width: x1 - x0 + 1, height: y1 - y0 + 1, style: 'fill:var(--map-floor)' }));   // VIEW-01: the floor only where the board is
  const bg = view.map.background;                                   // VIEW-01: an imported map's picture under the grid
  drawGround2D(root, view.map, svg);                   // REGION-01: a terrain battle's ground
  drawWater2D(root, view.map, svg);                    // MAPGEN-01: rivers, the sea, pools
  if (bg?.src) root.append(svg('image', { href: asset(bg.src), x: bg.x ?? 0, y: bg.y ?? 0, width: bg.w ?? bg.cols, height: bg.h ?? bg.rows,   // a picture's own grid: its corner in squares
    preserveAspectRatio: 'none', 'pointer-events': 'none' }));
  for (let x = x0; x <= x1; x++) for (let y = y0; y <= y1; y++) {
    const sq = svg('rect', { x, y, width: 1, height: 1, fill: 'transparent', stroke: '#2c2d29', 'stroke-width': .015, 'stroke-opacity': .45, 'data-square': `${x},${y}` });
    root.append(sq);
  }
  drawWalls2D(root, view.map, svg);                   // MAP RULE (GM 2026-10-20): walls at least a square thick, drawn as stone
  for (const w of view.map.walls) {
    if (solid && !w.door || w.natural) continue;      // the stone squares are the wall now; trees and rocks show their own
    const [[ax, ay], [bx, by]] = w.points;
    const ds = w.door ? snap?.door_states?.[w.id] : null;          // SPELL-OBJECTS-01: broken, burning, its Hit Points
    root.append(svg('line', { class: w.door ? 'door' : 'wall', x1: ax + .5, y1: ay + .5, x2: bx + .5, y2: by + .5, 'stroke-linecap': 'round', 'pointer-events': 'none',
      stroke: w.door ? (ds?.broken ? '#6d6a63' : w.open ? '#7fbf7f' : '#c08a3e') : '#d8d0c0', 'stroke-width': w.door ? .14 : .1,
      ...(ds?.broken ? { 'stroke-dasharray': '.12 .1' } : {}) }));
    if (ds?.burning) root.append(svg('line', { class: 'door-fire', x1: ax + .5, y1: ay + .5, x2: bx + .5, y2: by + .5, 'stroke-linecap': 'round',
      stroke: '#ff7a1a', 'stroke-opacity': .7, 'stroke-width': .3, 'pointer-events': 'none' }));
    const aim = w.door && snap?.waiting && held ? doorAim(snap.offers, held, armed.metas) : null;   // the held spell: click a door
    if (aim && (aim.ok.includes(w.id) || aim.refused[w.id])) {
      const ok = aim.ok.includes(w.id), hit = svg('line', { class: 'door-aim', 'data-door-aim': w.id, x1: ax + .5, y1: ay + .5, x2: bx + .5, y2: by + .5,
        'stroke-linecap': 'round', stroke: ok ? '#6fd36f' : '#c0504d', 'stroke-opacity': ok ? .7 : .45, 'stroke-width': .34, style: 'cursor:pointer' });
      hit.append(svg('title', {}, ok ? `Cast ${aim.spell} at the ${w.id} (${doorText(w.id, ds).replace(/^The [^:]+: /, '')})` : aim.refused[w.id]));
      root.append(hit);
      continue;
    }
    const near = w.door && snap?.waiting && !held && !casting && (snap.offers?.doors ?? []).find(d => d.id === w.id && d.near && d.ready);
    if (near) {                                         // slice 3: a door beside the character: click to open or close it
      const hit = svg('line', { class: 'door-near', 'data-door': w.id, x1: ax + .5, y1: ay + .5, x2: bx + .5, y2: by + .5, 'stroke-linecap': 'round',
        stroke: '#eab54e', 'stroke-opacity': .55, 'stroke-width': .34, style: 'cursor:pointer' });
      hit.append(svg('title', {}, `${near.open ? 'Close' : 'Open'} the ${w.id} (free object interaction)`));
      root.append(hit);
    }
  }
  // GM 2026-10-28 ("every spell with a range or area should show that shape before selecting targets"; "lit up is better"):
  // the chosen spell's reach lit up around the caster: its range, or a Cone's or Line's length, an aura's radius
  const rs = rangeShown();
  if (rs) {
    const [cx, cy] = rs.at, n = Math.floor(rs.ft / 5), colour = (palettes[rs.spell.appearance] ?? palettes.arcane)[0], sq = [];
    for (let x = Math.max(0, cx - n); x <= Math.min((view.map.cols ?? cx + n + 1) - 1, cx + n); x++)
      for (let y = Math.max(0, cy - n); y <= Math.min((view.map.rows ?? cy + n + 1) - 1, cy + n); y++) sq.push([x, y]);
    for (const [x, y] of sq) root.append(svg('rect', { x, y, width: 1, height: 1, fill: colour, 'fill-opacity': .13, 'pointer-events': 'none' }));
    for (const [x1, y1, x2, y2] of reachOutline(sq)) root.append(svg('line', { x1, y1, x2, y2, stroke: colour, 'stroke-width': .07, 'stroke-opacity': .9, 'pointer-events': 'none' }));
    const label = svg('text', { x: cx + .5, y: Math.max(.6, cy - n - .25), 'text-anchor': 'middle', 'font-size': .45, fill: colour, class: 'range-label', 'pointer-events': 'none' }, `${rs.spell.name}: ${rs.what}`);
    root.append(label);
  }
  const reach = !held && !casting && !rs && snap?.waiting ? snap.offers?.reach ?? [] : [];   // 2026-10-19: how far the character can move
  for (const r of reach) root.append(svg('rect', { x: r[0], y: r[1], width: 1, height: 1, fill: '#e0c060', 'fill-opacity': .07, 'pointer-events': 'none' }));
  for (const [x1, y1, x2, y2] of reachOutline(reach)) root.append(svg('line', { x1, y1, x2, y2, stroke: '#e0c060', 'stroke-width': .05, 'stroke-opacity': .8, 'pointer-events': 'none' }));
  // GM 2026-10-24 ("Couldn't move farther"): how far a Dash would take the character, fainter and dashed
  const dashReach = !held && !casting && snap?.waiting ? snap.offers?.dash_reach ?? [] : [];
  for (const r of dashReach) root.append(svg('rect', { x: r[0], y: r[1], width: 1, height: 1, fill: '#e0c060', 'fill-opacity': .03, 'pointer-events': 'none' }));
  for (const [x1, y1, x2, y2] of reachOutline([...reach, ...dashReach])) root.append(svg('line', { x1, y1, x2, y2, stroke: '#e0c060', 'stroke-width': .04, 'stroke-opacity': .55, 'stroke-dasharray': '.15 .12', 'pointer-events': 'none' }));
  for (const p of view.map.props ?? []) {                        // 2026-10-19: display-only props; a click still moves there
    const mk = propMarker(p.kind), g = svg('g', { 'data-square': `${p.x},${p.y}`, opacity: .85 });
    g.append(svg(mk.family === 'green' || mk.family === 'stone' ? 'circle' : 'rect', mk.family === 'green' || mk.family === 'stone'
      ? { cx: p.x + .5, cy: p.y + .5, r: .3, fill: mk.colour, stroke: '#1b1710', 'stroke-width': .03 }
      : { x: p.x + .2, y: p.y + .25, width: .6, height: .5, rx: .06, fill: mk.colour, stroke: '#1b1710', 'stroke-width': .03 }));
    g.append(svg('title', {}, p.label || p.kind));
    root.append(g);
  }
  for (const [id, st] of Object.entries(snap?.prop_states ?? {})) {   // SPELL-OBJECTS-01 step 6: props as objects
    if (st.broken) root.append(svg('path', { d: `M${st.x + .2} ${st.y + .2}L${st.x + .8} ${st.y + .8}M${st.x + .8} ${st.y + .2}L${st.x + .2} ${st.y + .8}`,
      stroke: '#6d6a63', 'stroke-width': .08, 'pointer-events': 'none' }));
    if (st.burning) root.append(svg('circle', { cx: st.x + .5, cy: st.y + .5, r: .42, fill: '#ff7a1a', 'fill-opacity': .35, 'pointer-events': 'none' }));
    const aim = snap?.waiting && held ? doorAim(snap.offers, held, armed.metas, 'props') : null;
    if (aim && (aim.ok.includes(id) || aim.refused[id])) {
      const ok = aim.ok.includes(id), ring = svg('circle', { class: 'object-aim', 'data-object-aim': id, cx: st.x + .5, cy: st.y + .5, r: .44,
        fill: 'transparent', stroke: ok ? '#6fd36f' : '#c0504d', 'stroke-opacity': ok ? .8 : .45, 'stroke-width': .07, style: 'cursor:pointer' });
      ring.append(svg('title', {}, ok ? `Cast ${aim.spell} at the ${doorText(id, st).replace(/^The /, '')}` : aim.refused[id]));
      root.append(ring);
    } else if (!st.broken) {
      const tip = svg('rect', { x: st.x, y: st.y, width: 1, height: 1, fill: 'transparent', 'pointer-events': 'none' });
      tip.append(svg('title', {}, doorText(id, st)));
      root.append(tip);
    }
  }
  drawLight(root);                                                 // LIGHTS-01: the map's light, the lit areas, the rings
  if (PLAYER) { drawHazards(root); drawTraps(root); drawNotes(root); }   // GM 2026-10-28: on the players' screens the paint covers these
  mapPaint.draw(root, view);                                       // MAP-PAINT-01: under the fog, over the map
  drawFog(root);
  if (!PLAYER) {
    drawHazards(root);                                             // HAZARDS-01: ice and frigid water on squares
    drawTraps(root);                                               // GM 2026-10-24: traps and gear (the GM sees all)
    drawNotes(root);
  }
  const perspective = PLAYER ? 'players' : 'gm';
  const order = layerOrder(view.state.combatants, snap?.layers);
  for (const c of [...order.filter(corpse), ...order.filter(c => !corpse(c))]) {   // MAP-LAYERS-01: mounts under their riders; corpses under all
    if (c.x < -50 || c.y < -50) continue;
    const ride = c.riding ? c.rider_scale : 1;
    const size = c.space_ft / view.map.square_ft * ride, x = c.x + .5, y = c.y + .5 - (c.riding ? .12 : 0);
    const col = attitudeColour(snap, c) ?? sideColour(c.side), active = c.id === snap?.waiting;   // GM 2026-10-27: disposition   // GM 2026-10-24: out of the fight: amber
    const look = tokenLook(c, offers);
    const g = svg('g', { ...(corpse(c) ? { 'pointer-events': 'none' } : { 'data-actor': c.id }), ...(c.pc ? { 'data-pc': 1 } : {}), class: 'token ' + look.cls, style: 'cursor:' + (held && look.cls.startsWith('legal') ? 'copy' : 'default') });
    const [ring, fillOp] = LOOK[look.cls] ?? [null, 0];
    g.append(svg('rect', { x: x - size / 2, y: y - size / 2, width: size, height: size, rx: .06, fill: ring ?? col,
      'fill-opacity': ring ? fillOp + .12 : active ? .2 : .06, stroke: ring ?? (active ? '#e0c060' : col),
      'stroke-width': ring ? .1 : active ? .07 : .03, opacity: c.down ? .4 : 1 }));
    const outline = PLAYER ? attitudeColour(snap, c) : null;     // GM 2026-10-27: "show the players their disposition color as an outline"
    if (outline) g.append(svg('rect', { x: x - size / 2 - .05, y: y - size / 2 - .05, width: size + .1, height: size + .1, rx: .1, fill: 'none',
      stroke: outline, 'stroke-width': .1, opacity: c.down ? .4 : 1, 'pointer-events': 'none', class: 'disposition-outline' }));
    if (c.id === marked) g.append(svg('rect', { x: x - size / 2 - .12, y: y - size / 2 - .12, width: size + .24, height: size + .24, rx: .12, fill: 'none',
      stroke: '#e0c060', 'stroke-width': .07, 'stroke-dasharray': '.2 .1', 'pointer-events': 'none' }));   // COMBAT-TRACKER-01: picked in the tracker
    if (c.token_path) g.append(svg('image', { href: asset(c.token_path), x: x - size * .47, y: y - size * .47, width: size * .94, height: size * .94, opacity: c.down ? .3 : 1 }));
    if (c.rider_path && !c.down) {                                // Flavor (GM 2026-10-23): a rider, a small picture on its back
      const r = size * .24, ry = y - size * .14;
      g.append(svg('circle', { cx: x, cy: ry, r, fill: '#151614', 'fill-opacity': .55, stroke: '#e0c060', 'stroke-width': .03 }));
      g.append(svg('image', { href: asset(c.rider_path), x: x - r, y: ry - r, width: r * 2, height: r * 2 }));
    }
    else g.append(svg('text', { x, y: y + .12, 'text-anchor': 'middle', 'font-size': .3 * Math.min(size, 1.6), fill: col }, c.name.split(/\s+/).map(w => w[0]).join('').slice(0, 3)));
    const health = mapHealth(c, PLAYER), frac = health.frac;      // GM 2026-10-27: words on a player's screen
    g.append(svg('rect', { x: x - size / 2, y: y + size / 2 - .1, width: size * frac, height: .08, fill: frac > .5 ? '#6c6' : frac > .25 ? '#dc6' : '#d55' }));
    g.append(svg('text', { x, y: y - size / 2 - .06, 'text-anchor': 'middle', 'font-size': .2, fill: '#ddd' }, c.name));
    const unseen = invisibleLook(c, perspective === 'gm' ? 'gm' : 'player');   // MAP-LAYERS-01 step 2
    if (unseen) {
      g.setAttribute('opacity', unseen.opacity);
      if (unseen.dashed) g.append(svg('rect', { x: x - size / 2 - .05, y: y - size / 2 - .05, width: size + .1, height: size + .1, rx: .1, fill: 'none',
        stroke: '#e8e2d0', 'stroke-width': .04, 'stroke-dasharray': '.12 .08', 'pointer-events': 'none' }));
    }
    if (c.riding) g.append(svg('path', { d: `M${x - size * .42} ${y + size / 2 + .02} q${size * .42} ${size * .22} ${size * .84} 0`, fill: 'none',
      stroke: '#e0c060', 'stroke-width': .04, 'pointer-events': 'none' }));   // a saddle line: this one rides
    const riding = c.riding ? ` · rides ${view.state.combatants.find(m => m.id === c.riding)?.name ?? 'its mount'}` : '';
    g.append(svg('title', {}, `${c.name}: ${health.text}${flavorTip(c)}${riding}` + (unseen ? ` · ${unseen.label}` : '') + (look.reason ? ` · ${look.reason}` : '')));
    root.append(g);
  }
  drawMapEffects();
  drawTrackerPanel();
  // the footnote of the creature whose turn it is, under the board (the players' window too, when the GM shares it)
  const turn = view.state.combatants.find(c => c.id === snap?.waiting) ?? view.state.combatants.find(c => c.id === view.state.active);
  $('flavor-foot').textContent = turn?.flavor_description ? `${turn.name}: ${turn.flavor_description}` : '';
}

// ------------------------------------------------------------------ saved characters in the party (CHARACTERS-01 phase 4)
// GM 2026-10-21: "a first rate character builder that can quickly be tested in live": the Party box takes saved sheets
// from the Characters page as well as pregens. The sheets go to the service, which makes each one a party member at its
// own level (sim/character_build.py member()); their photos are linked to the tokens by the names the service gave them.
const chosenChars = new Set((new URLSearchParams(location.search).get('characters') ?? '').split(',').filter(Boolean));
let tableParty = null;                                            // GM 2026-10-25: the sheets Mythastria keeps for the party
const partyRoster = () => mergeRoster(rosterFrom(), tableParty);
function drawPartyChars() {
  const list = $('party-chars-list'), roster = partyRoster();
  list.replaceChildren();
  for (const c of roster) {
    const lab = document.createElement('label'), cb = Object.assign(document.createElement('input'), { type: 'checkbox', checked: chosenChars.has(c.id) });
    const lv = (c.classes ?? []).reduce((n, k) => n + (k.level || 0), 0);
    cb.addEventListener('change', () => { if (cb.checked) chosenChars.add(c.id); else chosenChars.delete(c.id); drawPartyChars(); });
    lab.append(cb, `${c.name}${lv ? ' (level ' + lv + ')' : ''}${c.fromTable ? ' (kept by the table)' : ''}`);
    list.append(lab);
  }
  if (!roster.length) list.append(el('span', 'note', 'No saved characters yet.'));
  const n = roster.filter(c => chosenChars.has(c.id)).length;
  $('party-chars').querySelector('summary').textContent = n ? `Saved characters (${n})` : 'Saved characters';
  $('level').value = String(Math.max(1, ...roster.filter(c => chosenChars.has(c.id)).map(c => Math.min(20, (c.classes ?? []).reduce((t, k) => t + (k.level || 0), 0)))));   // GM 2026-10-28: traps, Remix
}
// what the service needs from a sheet to make it fight (not its import extract or builder choices)
function fightSheet(c) { const { provenance, import: _, build, ...rest } = c; return rest; }

// ------------------------------------------------------------------ sheets and photos on tokens (VIEW-01)
function keepPhotos(next) {
  photos = next;
  if (!savePhotos(photos)) status('This browser is out of room for photos: remove one, or use smaller pictures.', true);
  if (snap) { buildView(); drawMap(); drawSheet(); }
}
function drawSheetPhoto(offers) {
  const box = $('sheet-photo'), roster = rosterFrom(), member = offers.name, sheet = sheetFor(photos, roster, member);
  const pick = el('select'); pick.setAttribute('aria-label', 'Character sheet for ' + member);
  pick.append(new Option('No saved sheet', ''), ...roster.map(c => new Option(c.name, c.id, false, c.id === sheet)));
  pick.addEventListener('change', () => keepPhotos(linkSheet(photos, member, pick.value || null)));
  const row = el('div', 'photo-row');
  for (const [i, url] of (photos.sheets[sheet]?.photos ?? []).entries()) {
    const b = el('button', 'photo' + (photos.sheets[sheet].active === i ? ' on' : '')); b.title = 'Use this photo on the token';
    b.append(Object.assign(document.createElement('img'), { src: url, alt: `${member}, photo ${i + 1}` }));
    b.addEventListener('click', () => keepPhotos(setActive(photos, sheet, i)));
    const x = el('button', 'photo-x', '×'); x.title = 'Remove this photo';
    x.addEventListener('click', () => keepPhotos(removePhoto(photos, sheet, i)));
    row.append(b, x);
  }
  const add = el('label', 'quiet photo-add', 'Add photo'), file = Object.assign(document.createElement('input'), { type: 'file', accept: 'image/*', hidden: true });
  add.append(file);
  file.addEventListener('change', async () => { if (file.files[0]) keepPhotos(addPhoto(photos, sheet, await photoFromFile(file.files[0]))); });
  const full = (photos.sheets[sheet]?.photos.length ?? 0) >= MAX_PHOTOS;
  box.replaceChildren(el('span', 'note', 'Sheet'), pick, row, ...(sheet && !full ? [add] : []),
    el('span', 'note', sheet ? 'Photos stay in this browser only.' : roster.length ? 'Choose the saved sheet to add photos.' : 'Save a sheet on the Characters page to attach it.'));
}
addEventListener('storage', e => { if (e.key === PHOTO_KEY || e.key === 'isles-character-roster-v1') { photos = loadPhotos(); if (snap) { buildView(); drawMap(); drawSheet(); } } });

// ------------------------------------------------------------------ map import (VIEW-01): Universal VTT, our own reader
$('import-open').addEventListener('click', () => { $('imp-result').textContent = ''; $('import-dialog').showModal(); });
// 2026-10-21 (GM: "The map maker needs to allow hard cancels"): Cancel, or Esc, at any step drops the whole map in
// progress: the file, the name, the grid and the squares. A file still being read or a map still being imported is
// ignored when it comes back, so nothing opens or gets chosen after a cancel.
let mapJob = 0;
function cancelMapMaker() {
  mapJob++; ed = null;
  for (const id of ['import-dialog', 'map-editor']) if ($(id).open) $(id).close();
  $('imp-file').value = ''; $('imp-name').value = '';
  $('imp-result').textContent = $('ed-result').textContent = '';
  $('imp-go').disabled = $('ed-import').disabled = false;
  status('Map maker cancelled: nothing was imported.');
}
$('imp-cancel').addEventListener('click', e => { e.preventDefault(); cancelMapMaker(); });
for (const id of ['import-dialog', 'map-editor']) $(id).addEventListener('cancel', e => { e.preventDefault(); cancelMapMaker(); });

// The map editor (GM 2026-10-20: "maps will need a grid aligment tool. if an imported map already has grid marks, then the
// grid will need to be created by hand by a survey tool"; MAP RULE: walls at least one square thick). A picture: the grid
// first (two corners of a block of printed squares, or two points a known distance apart), then the squares drafted from
// its light. A Universal VTT file: its own grid, its thin walls drafted as squares by the service. Then painted by hand.
let ed = null;
const pictureOf = file => new Promise((ok, fail) => { const r = new FileReader(); r.onload = () => ok(r.result); r.onerror = fail; r.readAsDataURL(file); });
const imageFrom = src => new Promise((ok, fail) => { const i = new Image(); i.onload = () => ok(i); i.onerror = fail; i.src = src; });
const firstFloor = (c, last = false) => {
  const order = [...c.kind.keys()];
  if (last) order.reverse();
  const i = order.find(i => c.kind[i] === 'f');
  return i === undefined ? { x: 1, y: 1 } : { x: i % c.cols, y: Math.floor(i / c.cols) };
};

$('imp-go').addEventListener('click', async e => {
  e.preventDefault();
  const file = $('imp-file').files[0];
  if (!file) { $('imp-result').textContent = 'Choose a map file or a picture first.'; return; }
  $('imp-result').textContent = 'Reading…';
  const job = mapJob;
  $('imp-go').disabled = true;
  try {
    if (/\.(dd2vtt|uvtt|json)$/i.test(file.name)) {
      const data = await file.text(), u = JSON.parse(data);
      const draft = await port.importDraft({ data }).catch(() => null);
      if (job !== mapJob) return;
      if (!draft?.ok) { $('imp-result').textContent = 'Not imported: ' + (draft?.error ?? 'the service stopped.'); return; }
      const img = await imageFrom(`data:${imageType(u.image ?? '')};base64,${u.image}`);
      if (job !== mapJob) return;
      ed = { kind: 'uvtt', data, img, grid: { px: img.naturalWidth / draft.cols, ox: 0, oy: 0 }, cells: newCells(draft.cols, draft.rows, draft),
        notes: draft.notes.join(' '), history: [], clicks: [] };
      enterSquares();
    } else {
      const src = await pictureOf(file), img = await imageFrom(src);
      if (job !== mapJob) return;
      ed = { kind: 'picture', src, img, grid: { px: 50, ox: 0, oy: 0, skew: 0 }, cells: null, notes: '', history: [], clicks: [] };
      ed.step = 'grid';
    }
  } catch { if (job === mapJob) $('imp-result').textContent = 'That file could not be read as a map or a picture.'; return; }
  finally { if (job === mapJob) $('imp-go').disabled = false; }
  $('import-dialog').close();
  $('ed-result').textContent = '';
  showStep();
  $('map-editor').showModal();
  drawEditor();
});

function enterSquares() {
  const { cols, rows } = ed.kind === 'uvtt' ? ed.cells : gridSquares(ed.grid, ed.img.naturalWidth, ed.img.naturalHeight);
  if (!(cols >= 1 && rows >= 1 && cols <= 200 && rows <= 200)) { $('ed-result').textContent = `The grid makes ${cols} x ${rows} squares: 1-200 each way.`; return false; }
  if (ed.kind === 'picture') ed.cells = redraft(cols, rows);
  ed.party = firstFloor(ed.cells); ed.foes = firstFloor(ed.cells, true);
  ed.step = 'squares';
  return true;
}
function redraft(cols, rows) {
  const k = Math.min(1, 2000 / Math.max(ed.img.naturalWidth, ed.img.naturalHeight));       // read the light at most 2000 px across
  const c = document.createElement('canvas');
  c.width = Math.round(ed.img.naturalWidth * k); c.height = Math.round(ed.img.naturalHeight * k);
  const g = c.getContext('2d', { willReadFrequently: true });
  g.drawImage(ed.img, 0, 0, c.width, c.height);
  const light = squareLight(g.getImageData(0, 0, c.width, c.height), { px: ed.grid.px * k, ox: ed.grid.ox * k, oy: ed.grid.oy * k }, cols, rows);
  return draftFromLight(light, cols, rows, Number($('ed-thresh').value));
}
function showStep() {
  const grid = ed.step === 'grid';
  $('ed-grid-tools').hidden = !grid; $('ed-square-tools').hidden = grid;
  $('ed-redraft').hidden = $('ed-thresh-label').hidden = $('ed-back').hidden = ed.kind !== 'picture';
  $('ed-help').textContent = grid
    ? 'Grid: if the picture shows grid lines, click two opposite corners of a block of its squares (say how many across and down). If it has none, survey: click two points a known distance apart. Then nudge until the lines sit on the picture\'s squares.'
    : 'Squares (map rule: walls are whole squares): paint Floor, Wall and Door (a doorway square in a wall) by clicking or dragging; set where the party and the creatures start. ' + ed.notes;
}
function editorScale() { return Math.min(1, 1000 / ed.img.naturalWidth); }
function pictureXY(e) {
  const c = $('ed-canvas'), r = c.getBoundingClientRect(), s = editorScale();
  return { x: (e.clientX - r.left) * (c.width / r.width) / s, y: (e.clientY - r.top) * (c.height / r.height) / s };
}
function drawEditor() {
  const c = $('ed-canvas'), s = editorScale(), g = c.getContext('2d'), W = ed.img.naturalWidth, H = ed.img.naturalHeight;
  c.width = Math.round(W * s); c.height = Math.round(H * s);
  g.setTransform(s, 0, 0, s, 0, 0);
  g.drawImage(ed.img, 0, 0);
  const { px, ox, oy } = ed.grid, lw = 1 / s;
  if (ed.step === 'squares') {
    const colour = { w: 'rgba(52,46,38,.72)', d: 'rgba(214,150,62,.75)' };
    ed.cells.kind.forEach((k, i) => {
      if (k === 'f') return;
      g.fillStyle = colour[k];
      g.fillRect(ox + (i % ed.cells.cols) * px, oy + Math.floor(i / ed.cells.cols) * px, px, px);
    });
    for (const [who, fill, letter] of [['party', '#4f7fbf', 'P'], ['foes', '#bf4f4f', 'C']]) {
      const p = ed[who]; g.fillStyle = fill;
      g.beginPath(); g.arc(ox + (p.x + .5) * px, oy + (p.y + .5) * px, px * .38, 0, Math.PI * 2); g.fill();
      g.fillStyle = '#fff'; g.font = `bold ${px * .45}px sans-serif`; g.textAlign = 'center'; g.textBaseline = 'middle';
      g.fillText(letter, ox + (p.x + .5) * px, oy + (p.y + .5) * px);
    }
  }
  g.strokeStyle = 'rgba(255,240,200,.85)'; g.lineWidth = lw;
  g.beginPath();
  const cols = ed.step === 'squares' ? ed.cells.cols : Math.floor((W - ox) / px), rows = ed.step === 'squares' ? ed.cells.rows : Math.floor((H - oy) / px);
  for (let x = 0; x <= cols; x++) { g.moveTo(ox + x * px, oy); g.lineTo(ox + x * px, oy + rows * px); }
  for (let y = 0; y <= rows; y++) { g.moveTo(ox, oy + y * px); g.lineTo(ox + cols * px, oy + y * px); }
  g.stroke();
  g.fillStyle = '#ffd34d';
  for (const p of ed.clicks) { g.beginPath(); g.arc(p.x, p.y, 5 / s, 0, Math.PI * 2); g.fill(); }
  $('ed-read').textContent = `Square: ${px.toFixed(1)} px · ${cols} x ${rows} squares` + (ed.grid.skew > .03 ? ' · those squares are not square: check the count' : '');
}

$('ed-canvas').addEventListener('pointerdown', e => {
  if (!ed) return;
  const p = pictureXY(e);
  if (ed.step === 'grid') {
    ed.clicks.push(p);
    if (ed.clicks.length === 2) {
      const [a, b] = ed.clicks;
      const g = document.querySelector('input[name=ed-mode]:checked').value === 'corners'
        ? gridFromCorners(a, b, Number($('ed-across').value), Number($('ed-down').value))
        : gridFromDistance(a, b, Number($('ed-feet').value));
      $('ed-result').textContent = g ? '' : 'Those two points are too close for that many squares: try again.';
      if (g) ed.grid = g;
      ed.clicks = [];
    }
    drawEditor();
    return;
  }
  const brush = document.querySelector('input[name=ed-brush]:checked').value, q = pictureSquare(ed.grid, p);
  if (kindAt(ed.cells, q.x, q.y) === null) return;
  if (brush === 'party' || brush === 'foes') { ed[brush] = q; drawEditor(); return; }
  ed.history.push(ed.cells);
  ed.cells = paint(ed.cells, q.x, q.y, brush);
  ed.painting = true;
  $('ed-canvas').setPointerCapture(e.pointerId);
  drawEditor();
});
$('ed-canvas').addEventListener('pointermove', e => {
  if (!ed?.painting) return;
  const brush = document.querySelector('input[name=ed-brush]:checked').value, q = pictureSquare(ed.grid, pictureXY(e));
  const next = paint(ed.cells, q.x, q.y, brush);
  if (next !== ed.cells) { ed.cells = next; drawEditor(); }
});
$('ed-canvas').addEventListener('pointerup', () => { if (ed) ed.painting = false; });
for (const b of document.querySelectorAll('[data-nudge]')) b.addEventListener('click', e => {
  e.preventDefault();
  const [size, dx, dy] = b.dataset.nudge.split(',').map(Number), fine = e.shiftKey ? .1 : 1;
  ed.grid = nudge(ed.grid, { size: size * fine, dx: dx * fine, dy: dy * fine });
  drawEditor();
});
$('ed-next').addEventListener('click', e => { e.preventDefault(); if (enterSquares()) { showStep(); drawEditor(); } });
$('ed-back').addEventListener('click', e => { e.preventDefault(); ed.step = 'grid'; ed.history = []; showStep(); drawEditor(); });
$('ed-redraft').addEventListener('click', e => { e.preventDefault(); ed.history.push(ed.cells); ed.cells = redraft(ed.cells.cols, ed.cells.rows); drawEditor(); });
$('ed-round').addEventListener('click', e => { e.preventDefault(); ed.history.push(ed.cells); ed.cells = wallRound(ed.cells); drawEditor(); });
$('ed-undo').addEventListener('click', e => { e.preventDefault(); if (ed.history.length) { ed.cells = ed.history.pop(); drawEditor(); } });
$('ed-cancel').addEventListener('click', e => { e.preventDefault(); cancelMapMaker(); });
$('ed-import').addEventListener('click', async e => {
  e.preventDefault();
  const file = $('imp-file').files[0];
  const body = { name: $('imp-name').value || file.name.replace(/\.[^.]+$/, ''), cells: cellLists(ed.cells), party: [ed.party.x, ed.party.y],
    foes: { creature: $('imp-creature').value, count: Number($('imp-count').value) || 1, at: [ed.foes.x, ed.foes.y] } };
  if (ed.kind === 'uvtt') body.data = ed.data;
  else Object.assign(body, { picture: ed.src, ambient: $('imp-ambient').value,
    grid: { px: ed.grid.px, ox: ed.grid.ox, oy: ed.grid.oy, width: ed.img.naturalWidth, height: ed.img.naturalHeight } });
  $('ed-result').textContent = 'Importing…';
  const job = mapJob;
  $('ed-import').disabled = true;
  const out = await port.importMap(body).catch(() => null);
  if (job !== mapJob) return;
  $('ed-import').disabled = false;
  if (!out?.ok) { $('ed-result').textContent = 'Not imported: ' + (out?.error ?? 'the service stopped.'); return; }
  if (![...$('scenario').options].some(o => o.value === out.scenario)) $('scenario').append(new Option(out.scenario, out.scenario));
  $('scenario').value = out.scenario;
  mapPicker?.refresh(); drawRestore();
  $('map-editor').close(); ed = null;
  status(`Imported ${out.scenario}: ${out.walls} wall lines, ${out.lights} lights. Press Start live fight to play it.`);
});

// ------------------------------------------------------------------ notes pinned to the map (VIEW-01)
async function loadNotes(map) {
  notesMap = map; notesAt = Date.now();
  const out = await port.notes(map).catch(() => null);
  if (out?.ok && notesMap === map) { notes = out.notes; drawMap(); }
}
function drawNotes(root) {
  const g = svg('g', { class: 'notes', 'pointer-events': PLAYER ? 'none' : 'auto' });
  for (const n of notePins(notes, explored, PLAYER)) {
    const pin = svg('g', { class: 'note-pin' + (n.show_players ? ' shared' : '') });
    pin.append(svg('circle', { cx: n.x + .8, cy: n.y + .2, r: .17 }), svg('text', { x: n.x + .8, y: n.y + .27, 'text-anchor': 'middle', 'font-size': .2 }, 'i'));
    if (PLAYER) pin.append(svg('text', { x: n.x + 1.02, y: n.y + .26, 'font-size': .2, class: 'note-label' }, n.text.length > 40 ? n.text.slice(0, 39) + '…' : n.text));
    pin.append(svg('title', {}, n.text + (n.show_players ? '\n(shown to the players once found)' : '\n(GM only)')));
    g.append(pin);
  }
  root.append(g);
}
function openNote(x, y) {
  editing = noteAt(notes, x, y) ?? { x, y, text: '', show_players: false };
  $('note-where').textContent = `Square ${x}, ${y}`;
  $('note-text').value = editing.text; $('note-share').checked = editing.show_players;
  $('note-delete').hidden = !editing.id;
  $('note-dialog').showModal(); $('note-text').focus();
}
async function keepNotes(next) {
  const out = await port.saveNotes(view.map.name, next).catch(() => null);
  if (out?.ok) { notes = out.notes; drawMap(); status('Note saved.'); } else status('The note was not saved: ' + (out?.error ?? 'the service stopped.'), true);
}
$('note-save').addEventListener('click', e => { e.preventDefault(); const text = $('note-text').value.trim();
  $('note-dialog').close(); if (text) keepNotes(upsertNote(notes, { ...editing, text, show_players: $('note-share').checked })); });
$('note-delete').addEventListener('click', e => { e.preventDefault(); $('note-dialog').close(); keepNotes(deleteNote(notes, editing.id)); });
$('note-cancel').addEventListener('click', e => { e.preventDefault(); $('note-dialog').close(); });
$('note-mode').addEventListener('click', () => { noteMode = !noteMode; $('note-mode').setAttribute('aria-pressed', String(noteMode));
  $('map').classList.toggle('noting', noteMode); status(noteMode ? 'Notes: click a square to add, change or delete its note.' : ''); });

// ------------------------------------------------------------------ fog of war (VIEW-01)
function rememberSight() {
  const key = 'mythastria-fog:' + (view.map.name || 'map');
  if (key !== fogKey) { fogKey = key; try { explored = JSON.parse(localStorage.getItem(key) || '[]'); } catch { explored = []; } readReveal(); }
  explored = mergeExplored(explored, snap.party_sight);
  try { localStorage.setItem(fogKey, JSON.stringify(explored)); } catch { /* the fog is a convenience: it resets without storage */ }
}
// 2026-10-21 (GM: "Map reveal doesn't reveal on player view"): the Fog box only lifts the fog on this console. Reveal
// map to players lifts it in the players' window too, for this map, until pressed again (creatures still show only
// when the party sees them). Kept in this browser, so the pop-out follows at once.
const revealKey = () => 'mythastria-reveal:' + (view?.map.name || 'map');
function readReveal() {
  try { revealed = localStorage.getItem(revealKey()) === '1'; } catch { revealed = false; }
  $('fog-reveal').setAttribute('aria-pressed', String(revealed));
  $('fog-reveal').textContent = revealed ? 'Hide map from players' : 'Reveal map to players';
}
$('fog-reveal').addEventListener('click', () => {
  if (!view) return;
  try { if (revealed) localStorage.removeItem(revealKey()); else localStorage.setItem(revealKey(), '1'); } catch { /* none kept */ }
  readReveal(); drawMap();
  status(revealed ? "The map is revealed in the players' window." : "The players' window shows only what the party has seen.");
});
addEventListener('storage', e => { if (view && e.key === revealKey()) { readReveal(); drawMap(); } });
const fogOn = () => PLAYER ? !revealed : showFog;
function drawFog(root) {
  if (!snap?.party_sight || !fogOn()) return;
  const [, , x1, y1] = bounds(view);                               // the whole board drawn, edges beyond the map included
  const f = fogCells(Math.max(view.map.cols, x1 + 1), Math.max(view.map.rows, y1 + 1), snap.party_sight, explored), g = svg('g', { class: 'fog', 'pointer-events': 'none' });
  for (const [x, y] of f.hidden) g.append(svg('rect', { x, y, width: 1.02, height: 1.02, class: 'fog-hidden', 'fill-opacity': PLAYER ? 1 : .42 }));
  for (const [x, y] of f.dim) g.append(svg('rect', { x, y, width: 1.02, height: 1.02, class: 'fog-dim', 'fill-opacity': PLAYER ? .55 : .18 }));
  root.append(g);
}
$('fog-show').addEventListener('change', e => { showFog = e.target.checked; drawMap(); });
$('fog-reset').addEventListener('click', () => { explored = []; try { localStorage.removeItem(fogKey); } catch { /* none kept */ } if (snap) rememberSight(); drawMap(); });
$('player-view').addEventListener('click', () => window.open('play.html?view=player', 'mythastria-players', 'popup,width=1100,height=760'));
// GM 2026-10-28 ("The map should also have a popup"): a player's own map in a window of its own (same seat, same browser)
$('map-window').hidden = !PLAYER || MAP_WINDOW;
// GM 2026-10-28 ("player screen has no controls"): where the window opened in place of the table (a phone, the app's
// browser pane), Back to my turn brings the table back; a real second window just closes
$('map-back').hidden = !MAP_WINDOW;
$('map-back').addEventListener('click', () => {
  if (window.opener && !window.opener.closed) { window.close(); return; }
  location.href = 'play.html?view=player';
});
$('map-window').addEventListener('click', () => window.open('play.html?view=player&window=map', 'mythastria-map', 'popup,width=1100,height=800'));

// ------------------------------------------------------------------ spells and effects (slice 2)
function lookFor(key, c) {
  if (key?.startsWith(ACT_KEY)) return actLook(snap?.offers, key, c);   // slice 4: Help, Grapple, Shove, Lay on Hands
  const s = spellOf(snap?.offers, key);
  const far = s?.distant_targets && armed.metas.includes('Distant Spell') ? { ...s, targets: s.distant_targets } : s;   // Distant Spell
  return s ? spellLook(far, c, snap?.offers) : targetLook(snap?.offers, key, c);
}
function liveEffects() {
  const now = Date.now();
  fx = fx.filter(f => f.until > now);
  const preview = casting && aimAt ? spellVisual(aimPreview(casting, myPosition() ?? [0, 0], aimAt), rulesActor(snap?.waiting), casting.name) : null;
  const placed = (casting?.points ?? []).map(q => spellVisual(aimPreview(casting, myPosition() ?? [0, 0], q), rulesActor(snap?.waiting), casting.name));   // Meteor Swarm
  const auras = (snap?.auras ?? []).flatMap(a => auraEffects([a], view?.state.combatants).map(e => spellVisual(e, rulesActor(a.caster), a.spell)));
  const zones = layerEffects(snap?.layers);                         // MAP-LAYERS-01: Fog Cloud, Darkness, Stinking Cloud
  return [...zones, ...auras, ...fx.map(f => f.effect), ...placed, ...(preview ? [preview] : [])];
}
// 2026-10-20 (GM: cartoon effects): the table's own effect art (effects.mjs: inked edge, rim, flames, frost, sparks),
// so a cast here looks as it does on the main table; a preview is dashed and still, an aura stays softer.
function drawEffects(root) {
  liveEffects().forEach((e, i) => {
    const art = effectGraphic({ ...e, id: e.id ?? `live-${i}`, angle_deg: e.angle_deg ?? 0, length_ft: e.length_ft ?? 0,
      width_ft: e.width_ft ?? 5, radius_ft: e.radius_ft ?? 5 }, svg, { preview: !!e.preview, animate: !e.preview });
    if (e.aura) art.setAttribute('opacity', .6);
    if (e.lasting) {                                                // MAP-LAYERS-01: a zone on the air layer, over the tokens
      const look = ZONE_LOOK[PLAYER ? 'players' : 'gm'], [ox, oy] = e.origin, r = e.radius_ft / view.map.square_ft;
      const fill = e.darkness ? '#07060b' : e.appearance === 'poison' ? '#9fb25a' : e.appearance === 'frost' ? '#cfe3ee' : '#b9b4c4';
      const opacity = e.darkness ? look.dark : e.veil === 'light' ? look.fog / 2 : look.fog;
      if (e.veil !== 'none') {                                      // SPELL-EFFECTS-01: a ground spell hides nothing
        const veil = e.cube ? svg('rect', { x: e.cube[0] + .5, y: e.cube[1] + .5, width: e.cube[2] - e.cube[0], height: e.cube[3] - e.cube[1],
          fill, 'fill-opacity': opacity, class: 'zone-veil', 'data-layer': e.layer })
          : svg('circle', { cx: ox + .5, cy: oy + .5, r, fill, 'fill-opacity': opacity, class: 'zone-veil', 'data-layer': e.layer });
        root.append(veil);
      }
      art.setAttribute('opacity', e.darkness ? .5 : e.veil === 'none' ? .55 : .75);
    }
    root.append(art);
  });
}
function viewWithEffects() {                                         // the 3D view: zones as volumes, riders raised, the unseen faded
  if (!view) return null;
  const persp = PLAYER ? 'player' : 'gm';
  const combatants = layerOrder(view.state.combatants, snap?.layers).map(c => {
    const u = invisibleLook(c, persp);
    return u ? { ...c, faded: u.opacity } : c;
  });
  return { ...view, state: { ...view.state, combatants }, effects: liveEffects() };
}
function startCast(s) {
  if (!s.ready) { result(s.why, 'refused'); return; }
  if (twinArmed(s, armed)) s = { ...s, shape: 'creatures', max_targets: 2 };   // Twinned Spell: one more creature
  held = null; aimAt = null;
  if (s.shape === 'self') { cast({ spell: s.name }); return; }
  if (s.shape === 'door') {                                       // SPELL-OBJECTS-01: Knock: click a door
    held = SPELL_KEY + s.name; drawMap(); drawSheet();
    result(`${s.name}: click a door (green: it can go there; hover a red one to see why). Esc cancels.`); return;
  }
  if (s.shape === 'creature') { result(`${s.name}: drag it onto a creature, or click a lit creature. Esc cancels.`); return; }
  casting = { ...withLevel(s), picks: [], points: [], points_max: s.points };
  result(s.shape === 'creatures' ? `${s.name}: click up to ${casting.max_targets} lit creatures, then Cast. Esc cancels.` :
    s.shape === 'cone' ? `${s.name}: point where the Cone goes from ${snap.offers.name}, then click. Esc cancels.` :
    s.shape === 'line' ? `${s.name}: point where the ${s.length_ft}-ft Line goes from ${snap.offers.name}, then click. Esc cancels.` :
    s.shape === 'cube_self' ? `${s.name}: point to the side of ${snap.offers.name} for the ${s.size_ft}-ft Cube, then click. Esc cancels.` :
    s.shape === 'cube' ? `${s.name}: point at a square for the ${s.size_ft}-ft Cube, then click. Esc cancels.` :
    s.call || s.summoned ? `${s.name}: click the square where it appears. Esc cancels.` :   // SPELL-EFFECTS-01: a summons
    s.teleport ? `${s.name}: click an unoccupied square you can see within ${s.range_ft} ft to teleport there. Esc cancels.` :   // SPELL-BATCH-01
    s.shape === 'wall' ? `${s.name}: point at the square for the middle of the ${s.length_ft}-ft wall (it runs across your view), then click. Esc cancels.` :
    s.shape === 'spheres' ? `${s.name}: click up to ${s.points} squares for the ${s.radius_ft}-ft Spheres, then Cast. Esc cancels.` :
    s.shape === 'cubes' ? `${s.name}: click up to ${s.points} squares, each the top-left of a ${s.size_ft}-ft Cube touching another, then Cast. Esc cancels.` :   // group 2: Fire Storm
    `${s.name}: point at a square for the ${s.radius_ft}-ft Sphere, then click. Esc cancels.`);
  drawMap(); drawSheet();
}
// SPELL-OBJECTS-01 (GM 2026-10-27): the held spell card or attack cantrip cast at a door (the service checks it again)
function castAtDoor(door, which = 'doors') {
  const aim = doorAim(snap?.offers, held, armed.metas, which);
  if (!aim) return;
  if (!aim.ok.includes(door)) { result(aim.refused[door] ?? `Not at the ${door}.`, 'refused'); return; }
  const at = which === 'props' ? { object: door } : { door };       // step 6: a prop goes as object
  const key = held;
  held = null;
  if (PLAYER) sync.used();
  drawMap(); drawSheet();
  if (!key.startsWith(SPELL_KEY)) {                                // step 5: the armed Metamagic goes with it
    const a = snap?.offers?.attacks?.find(x => x.key === key);
    choose({ op: 'cast', spell: aim.spell, ...at, ...(a?.metamagic ? metamagicFields(armed) : {}) }); return;
  }
  if (!keepsGoing(aim.spell)) { result(''); return; }
  const extra = castExtras(aim.spell);
  if (extra) choose({ op: 'cast', spell: aim.spell, ...at, ...extra, ...metamagicFields(armed) });
}
function cancelCast() { casting = null; aimAt = null; held = null; result(''); drawMap(); drawSheet(); }
// GM 2026-10-25: true when the caster goes ahead (asked first when the spell ends the Concentration held)
function keepsGoing(spell) {
  const warn = concentrationBreak(snap?.offers, (snap?.offers?.spells ?? []).find(x => x.name === spell));
  return !warn || confirm(`${warn} Cast it anyway?`);
}
function cast(fields) {
  const s = casting; casting = null; aimAt = null; spellFocus = null;
  if (PLAYER) sync.used();                                        // VIEW-02: the main console lets go of the spell
  drawMap(); drawSheet();
  if (!keepsGoing(fields.spell)) { result(''); return; }          // GM 2026-10-25: kept the Concentration
  const extra = castExtras(fields.spell);
  if (!extra) { result(''); return; }                             // cancelled at the question: nothing is cast
  return choose({ op: 'cast', ...fields, ...extra, ...metamagicFields(armed) });
}
// SPELL-CASTER-01: a general spell's choice and slot (play-view.mjs spellExtras), asked like Ask the GM's note
function castExtras(name) {
  const s = (snap?.offers?.spells ?? []).find(x => x.name === name);
  return spellExtras(s && { ...s, chosen_slot: spellLevelPick[name] }, (q, d) => prompt(q, d));   // the Cast at dropdown
}
// GM 2026-10-28 ("The spells available can be a pull down menu. The spell will then display and spell slot pips will
// show what slots are left. If the spell can be upcast, there will be a dropdown menu for the level to cast."):
// the slots as pips per level (filled: left; hollow: spent), the spells in one dropdown with the chosen one's card under
// it, and a Cast at dropdown when the rules engine lets that spell use a higher slot (its slots_ok)
let spellPickName = null, spellPickFor = null;
const spellLevelPick = {};
const ORDINAL = ['', '1st', '2nd', '3rd', '4th', '5th', '6th', '7th', '8th', '9th'];
function drawSlotPips(offers) {
  const box = $('slots'), left = offers.slots ?? [], full = offers.slots_max ?? left, parts = [];
  for (let i = 0; i < Math.max(left.length, full.length); i++) {
    const n = left[i] ?? 0, of = Math.max(full[i] ?? 0, n);
    if (!of) continue;
    const lv = el('span', 'pip-level'); lv.title = `Level ${i + 1} spell slots: ${n} of ${of} left`;
    lv.append(el('span', 'pip-name', ORDINAL[i + 1]));
    for (let k = 0; k < of; k++) lv.append(el('span', 'pip' + (k < n ? ' on' : '')));
    parts.push(lv);
  }
  if (offers.concentrating) parts.push(el('span', 'note', `Concentrating on ${offers.concentrating}`));
  box.replaceChildren(...parts);
}
function drawSpellPick(offers) {
  const spells = offers.spells ?? [], pick = $('spell-pick');
  if (spellPickFor !== offers.actor) { spellPickFor = offers.actor; spellPickName = null; }
  if (!spells.some(s => s.name === spellPickName)) spellPickName = (spells.find(s => s.ready) ?? spells[0])?.name ?? null;
  if (casting?.name && spells.some(s => s.name === casting.name)) spellPickName = casting.name;
  const byLevel = [...spells].sort((a, b) => a.level - b.level || a.name.localeCompare(b.name));
  pick.replaceChildren(...byLevel.map(s => new Option(`${s.level ? ORDINAL[s.level] : 'Cantrip'} · ${s.name}${s.ready ? '' : ' (not now)'}`, s.name, false, s.name === spellPickName)));
  pick.hidden = !spells.length;
  pick.onchange = () => { spellPickName = pick.value; spellFocus = pick.value; casting = null; held = null; drawMap(); drawSheet(); };   // its reach lights up
  const s = spells.find(x => x.name === spellPickName), lv = $('spell-level'), ok = s?.upcast ? s.slots_ok ?? [] : [];
  $('spell-level-box').hidden = ok.length < 2;
  if (ok.length > 1) {
    if (!ok.includes(spellLevelPick[s.name])) spellLevelPick[s.name] = ok[0];
    lv.replaceChildren(...ok.map(n => new Option(`level ${n}${n === ok[0] ? '' : ' (upcast)'}`, String(n), false, n === spellLevelPick[s.name])));
    lv.onchange = () => { spellLevelPick[s.name] = Number(lv.value); if (casting?.name === s.name) casting.max_targets = withLevel(s).max_targets; };
  }
  return s ? [s] : [];
}

// GM 2026-10-23 (the Sorcerer): Metamagic is chosen before the spell or attack cantrip it changes ("armed"), then goes
// with that choice; a new character's turn starts with none.
function drawMetamagic(offers) {
  const row = $('metamagic-row'), s = offers?.sorcery;
  if (armedFor !== (offers?.actor ?? null)) { armed = { metas: [], transmute: 'cold' }; armedFor = offers?.actor ?? null; }
  row.hidden = !s;
  if (!s) { row.replaceChildren(); return; }
  const items = [el('div', 'sheet-line', sorceryText(offers))];
  for (const g of fontButtons(offers)) {                           // Font of Magic, both ways: one line each
    const line = el('div', 'act-row');
    line.append(el('span', 'note', 'Font of Magic, ' + g.title.toLowerCase() + ' '));
    for (const f of g.buttons) {
      const b = el('button', 'quiet act' + (f.ready ? '' : ' not-ready'), f.label);
      b.disabled = !f.ready; b.title = f.ready ? f.title : f.why;
      b.addEventListener('click', () => choose(f.cmd));
      line.append(b);
    }
    items.push(line);
  }
  const mm = el('div', 'act-row');
  if (s.metamagic?.length) mm.append(el('span', 'note', 'Metamagic: '));
  for (const m of s.metamagic ?? []) {
    const on = armed.metas.includes(m.name), b = el('button', 'quiet act' + (on ? ' held' : ''), `${m.name} (${m.cost})`);
    b.title = on ? 'Chosen: it goes with your next spell or attack cantrip. Click again to take it off.'
      : `Metamagic, ${m.cost} Sorcery Point${m.cost === 1 ? '' : 's'}: choose it, then cast`;
    b.addEventListener('click', () => { armed.metas = on ? armed.metas.filter(x => x !== m.name) : [...armed.metas, m.name]; drawSheet(); });
    mm.append(b);
  }
  if (armed.metas.includes('Transmuted Spell')) {
    const pick = el('select');
    for (const k of TRANSMUTE) pick.append(new Option(k[0].toUpperCase() + k.slice(1), k));
    pick.value = armed.transmute;
    pick.addEventListener('change', () => { armed.transmute = pick.value; });
    mm.append(el('span', 'note', ' Transmuted Spell: '), pick);
  }
  items.push(mm);
  row.replaceChildren(...items);
}

// AC-SHOWN-01 (GM 2026-10-28): the AC attacks are rolled against now, with what changed it ("AC 19 (Shield +5)")
const acText = c => `AC ${c.ac}` + (c.ac_why?.length ? ` (${c.ac_why.join(', ')})` : '');
function drawParty() {                                            // GM 2026-10-25: a watcher sees the whole party
  const box = $('party-panel');
  box.hidden = !WATCHER || !view;
  if (box.hidden) return;
  const pcs = (view.state.combatants ?? []).filter(c => c.pc);
  $('party-body').replaceChildren(...pcs.map(c => {
    const row = el('div', 'pc' + (c.id === snap?.waiting ? ' turn' : '') + (c.down || c.dead ? ' down' : ''));
    const state = c.dead ? 'dead' : c.down ? (c.stable ? 'stable at 0 HP' : 'down') : `${c.hp}/${c.hp_max} HP${c.temp_hp ? ' +' + c.temp_hp : ''}`;
    row.append(el('span', '', (c.id === snap?.waiting ? '▸ ' : '') + c.name),
      el('span', 'note', [state, acText(c), ...(c.conditions ?? []), ...(c.afflictions ?? [])].join(' · ')));
    return row;
  }));
}
function drawSheet() {
  if (!PLAYER) sync.select({ held, casting });                    // VIEW-02: the pop-out shows the same highlights
  drawParty();
  const offers = standIn && snap?.offers?.actor !== standIn ? null : snap?.offers, panel = $('sheet-panel');   // that player sees only its own turn
  panel.hidden = !offers;
  panel.querySelector('h2').textContent = offers?.watching ? `Watching: ${offers.name}'s turn` : 'Your turn · character sheet';
  drawHints(offers);
  if (!offers) { drawUndo(null); drawBar(); return; }
  const me = view?.state.combatants.find(c => c.id === offers.actor);
  $('sheet-name').textContent = flavorLabel(flavorFor('actor'), offers.name);
  $('sheet-stats').textContent = me ? `${me.hp}/${me.hp_max} HP · ${acText(me)} · ${offers.movement} ft of movement left` : '';
  $('sheet-afflictions').textContent = (me?.afflictions ?? []).join(' · ');   // HAZARDS-01: Exhaustion, contagions, stress
  $('sheet-flavor').textContent = me?.flavor_description ?? '';      // Flavor: the footnote under the stat lines
  $('sheet-action').textContent = actionText(offers);
  const roof = me && ceilingAt(view.map, me.x, me.y);                // 2026-10-19: the room's ceiling, as the map describes it
  drawSheetPhoto(offers);
  $('sheet-ceiling').textContent = roof ? (roof.ft == null ? `Open sky (${roof.room}). ` : `Ceiling ${roof.ft} ft (${roof.room}). `) + roof.description : '';
  if (rollsFor !== offers.actor) { lastRolls = {}; attackPicks = {}; rollsFor = offers.actor; }
  $('turn-lights').replaceChildren(...turnLights(offers).map(l => { const s = el('span', 'light' + (l.used ? ' used' : '')); s.append(el('i'), document.createTextNode(l.label)); return s; }));
  $('sheet-turn').hidden = sheetTab !== 'turn'; $('sheet-checks').hidden = sheetTab !== 'checks'; $('sheet-full').hidden = sheetTab !== 'full';
  $('tab-turn').classList.toggle('on', sheetTab === 'turn'); $('tab-checks').classList.toggle('on', sheetTab === 'checks');
  $('tab-full').classList.toggle('on', sheetTab === 'full');
  drawChecks(offers);
  drawFullSheet(offers);
  // GM 2026-10-24: each attack on a line, To hit beside it (then a creature on the map), the last roll beside that
  $('cards').replaceChildren(...offers.attacks.map(a => {
    const row = el('div', 'srow' + (held === a.key ? ' held' : '') + (a.targets.length ? '' : ' not-ready'));
    const style = flavorFor('attack', a.key), name = el('div', 'sname');
    name.title = style.description || '';
    const line = type => cardText({ ...a, name: '', type }).replace(/^ · /, ''), small = el('small', '', line(attackPicks[a.key]?.dmgtype ?? a.type));
    name.append(el('b', '', flavorLabel(style, a.name)), small);
    name.addEventListener('pointerdown', e => startDrag(e, a));
    const hit = el('button', 'quiet act' + (held === a.key ? ' held' : ''), held === a.key ? 'Pick a creature…' : 'To hit');
    hit.disabled = !a.targets.length && !a.doors?.length && !a.props?.length;   // SPELL-OBJECTS-01: a door or a prop
    hit.title = a.targets.length ? `${a.targets.length} legal target${a.targets.length === 1 ? '' : 's'} now${a.doors?.length ? ', or a door' : ''}` : a.doors?.length ? 'A door it can be cast at' : 'No legal target now';
    hit.addEventListener('click', () => { held = held === a.key ? null : a.key; casting = null; drawMap(); drawSheet();
      result(held ? `${a.name}: click a highlighted creature (green: foe). Hover a red one to see why it is refused. Esc cancels.` : ''); });
    row.append(name, hit);
    const r = lastRolls[a.key];
    if (r) row.append(el('span', 'roll ' + r.cls, r.text));
    const mm = a.metamagic ? metamagicNote(a, armed) : null;          // GM 2026-10-23: Metamagic on an attack cantrip
    if (mm) row.append(el('span', 'why', mm.why));
    const pick = attackPicks[a.key] ??= {};
    if (a.choices?.length) {                                         // GM 2026-11-01: Sorcerous Burst's type, chosen at each cast
      const s = el('select', 'quiet'); s.title = 'The damage type of this cast';
      s.setAttribute('aria-label', `${a.name}: damage type`);
      s.append(...a.choices.map(t => new Option(t[0].toUpperCase() + t.slice(1), t)));
      s.value = pick.dmgtype ?? a.type;
      s.addEventListener('change', () => { pick.dmgtype = s.value; small.textContent = line(s.value); });
      row.append(s);
    }
    if (a.masteries?.length) {                                       // GM 2026-10-26: Tactical Master (Fighter 9)
      const s = el('select', 'quiet'); s.title = 'Tactical Master: this attack\'s Weapon Mastery';
      s.setAttribute('aria-label', `${a.name}: Weapon Mastery`);
      s.append(new Option(a.own_mastery ? `Mastery: ${a.own_mastery}` : 'Its mastery', ''), ...a.masteries.map(m => new Option(m, m)));
      s.value = pick.mastery ?? '';
      s.addEventListener('change', () => { pick.mastery = s.value || null; });
      row.append(s);
    }
    if (a.stealth_attack) {                                          // GM 2026-10-26: Supreme Sneak (Thief 9)
      const l = el('label', 'check'), b = el('input'); b.type = 'checkbox'; b.checked = !!pick.stealth && a.stealth_attack.ready;
      b.disabled = !a.stealth_attack.ready; l.title = a.stealth_attack.ready ? 'Cunning Strike: one Sneak Attack die; stay hidden if the turn ends behind Three-Quarters or Total Cover' : a.stealth_attack.why;
      b.addEventListener('change', () => { pick.stealth = b.checked; });
      l.append(b, document.createTextNode(' Stealth Attack')); row.append(l);
    }
    if (a.stunning_strike) {                                         // MONK-01: Stunning Strike (Monk 5), on a hit
      const s = a.stunning_strike, l = el('label', 'check'), b = el('input'); b.type = 'checkbox'; b.checked = !!pick.stun && s.ready;
      b.disabled = !s.ready; l.title = s.ready ? `On a hit: 1 Focus Point (${s.points} left), DC ${s.dc} Constitution save or Stunned until the start of your next turn` : s.why;
      b.addEventListener('change', () => { pick.stun = b.checked; });
      l.append(b, document.createTextNode(' Stunning Strike')); row.append(l);
    }
    if (a.hurl_through_hell) {                                       // CASTER-HIGH: Hurl Through Hell (Fiend 14), on a hit
      const s = a.hurl_through_hell, l = el('label', 'check'), b = el('input'); b.type = 'checkbox'; b.checked = !!pick.hurl && s.ready;
      b.disabled = !s.ready; l.title = s.ready ? `On a hit (once per turn; ${s.pays}): DC ${s.dc} Charisma save or 8d10 Psychic and gone until the end of your next turn` : s.why;
      b.addEventListener('change', () => { pick.hurl = b.checked; });
      l.append(b, document.createTextNode(' Hurl Through Hell')); row.append(l);
    }
    if (a.devious) {                                                 // MARTIAL-HIGH: Devious Strikes (Rogue 14)
      const s = el('select', 'quiet'); s.title = `Devious Strikes: Cunning Strike on this Sneak Attack (save DC ${a.devious.dc}${a.devious.two ? '; with a Stealth Attack too: Improved Cunning Strike' : ''})`;
      s.setAttribute('aria-label', `${a.name}: Devious Strikes`);
      s.append(new Option('No Devious Strike', ''), ...a.devious.options.map(o => {
        const opt = new Option(`${o.name} (${o.dice} dice, ${o.save === 'con' ? 'Con' : 'Dex'} save)`, o.key); opt.disabled = !o.ready; opt.title = o.why || ''; return opt; }));
      s.value = pick.devious ?? '';
      s.addEventListener('change', () => { pick.devious = s.value || null; });
      row.append(s);
    }
    return row;
  }));
  // slice 2: the spells on the sheet
  drawSlotPips(offers);
  drawMetamagic(offers);
  const shown = drawSpellPick(offers);
  $('spell-cards').replaceChildren(...shown.map(s => {
    const key = SPELL_KEY + s.name, b = el('button', 'card spell' + (held === key || casting?.name === s.name ? ' held' : '') + (s.ready ? '' : ' not-ready'));
    const style = flavorFor('spell', s.name);
    b.title = [style.description, s.rider, s.gm_rules ? `The GM rules: ${s.gm_rules}` : '', OBJECTS[s.objects] ? `Targets ${OBJECTS[s.objects]}.` : ''].filter(Boolean).join('\n');
    b.style.borderColor = (palettes[style.appearance || s.appearance] ?? palettes.arcane)[0];
    b.append(document.createTextNode(spellCardText({ ...s, name: flavorLabel(style, s.name) })));
    if (s.moves && s.ready) b.append(el('span', 'hint', s.moves));     // Hex / Hunter's Mark: its creature dropped
    b.append(el('span', 'hint', !s.ready ? s.why : s.shape === 'door' ? (s.doors?.length ? `${s.doors.length} door${s.doors.length === 1 ? '' : 's'} it can go at now: click, then a door` : 'No door it can go at now') : s.shape === 'creature' ? (s.targets?.length ? `${s.targets.length} legal target${s.targets.length === 1 ? '' : 's'} now` : 'No legal target now') :
      s.shape === 'creatures' ? 'Click, then pick the creatures' : s.shape === 'self' ? 'Click to cast' : 'Click, then aim on the map'));
    const warn = spellWarning(offers, s.name, hintsLevel(offers), mutedKinds());   // HINTS-01: "Casting Bless ends your Hex."
    if (warn) b.append(el('span', 'hint hint-warn', warn));
    const mm = metamagicNote(s, armed);                              // GM 2026-10-23: the armed Metamagic on this spell
    if (mm) b.append(el('span', 'hint' + (mm.ok ? '' : ' hint-warn'), mm.why + (mm.ok && twinArmed(s, armed) ? ': click, then pick two creatures' : '')));
    // GM 2026-10-28 ("targeted spells can be dropped on the creature"; "casting bless didn't do anything from Keynan"): a
    // spell for up to N creatures (Bless, Bane, Magic Missile) drags and drops too, one creature at a time
    if ((s.shape === 'creature' || s.shape === 'creatures') && s.ready && !twinArmed(s, armed)) b.addEventListener('pointerdown', e => startDrag(e, { key, name: s.name }));
    else b.addEventListener('click', () => startCast(s));
    return b;
  }), ...askRows(offers, 'spell'));
  $('spells-h').hidden = !(offers.spells?.length || (offers.asks ?? []).some(a => a.kind === 'spell'));
  // slice 3: Dash, Disengage, Dodge (and a Rogue's Bonus Action ones), the doors beside the character
  const button = b => { const x = el('button', 'quiet act' + (b.ready ? '' : ' not-ready') + (b.pick && held === b.pick ? ' held' : ''), b.label);
    x.disabled = !b.ready; if (b.why) x.title = b.why;
    x.addEventListener('click', () => {
      if (b.square) { pickTrapSquare(b); return; }                   // GM 2026-10-24: then click a square
      if (b.readySpell) {                                            // GM 2026-10-25: holding a spell needs Concentration
        const held = offers.concentrating;
        if (held && !confirm(`Readying ${b.readySpell.name} ends your Concentration on ${held}. Ready it anyway?`)) return;
        const extra = spellExtras(b.readySpell, (q, d) => prompt(q, d));
        if (!extra) return;
        choose({ ...b.cmd, ...extra }); return;
      }
      if (!b.pick) { choose(b.cmd); return; }
      held = held === b.pick ? null : b.pick; casting = null; drawMap(); drawSheet();   // slice 4: then click a lit creature
      result(held ? `${b.label}: click a highlighted creature. Hover a red one to see why it is refused. Esc cancels.` : '');
    }); return x; };
  const acts = actionButtons(offers), isFeature = b => FEATURE_OPS.has(b.cmd?.op ?? b.square?.op ?? (b.pick ?? '').slice(ACT_KEY.length).split(':')[0]);   // EPIC-BOONS-01: Blink Steps' square
  const withLink = b => !b.ready && b.link ? [button(b), linkButton(b)] : [button(b)];        // a trap's tool: -> Market
  $('action-buttons').replaceChildren(...grouped(acts.filter(b => !isFeature(b)), withLink));
  drawMount(offers, button);                                        // MAP-LAYERS-01: Mount, Dismount, the mount's action
  const focus = focusText(offers);                                  // MONK-01: Focus Points, the Martial Arts die
  $('feature-buttons').replaceChildren(...(focus ? [el('div', 'sheet-line', focus)] : []),
    ...grouped(acts.filter(isFeature), b => [button(b)]), ...askRows(offers, 'feature'), ...askRows(offers, 'action'));
  $('features-h').hidden = !$('feature-buttons').children.length && !offers.sorcery;
  drawItems(offers);                                               // GM 2026-10-23: the bag's items, prerequisites checked
  drawLightButtons(offers);                                        // LIGHTS-01: torches, lanterns, the light spells
  $('door-buttons').replaceChildren(...doorButtons(offers).map(button));
  drawUndo(offers);
  const many = casting?.shape === 'spheres' || casting?.shape === 'cubes';   // Meteor Swarm's points, Fire Storm's Cubes
  $('cast-go').hidden = casting?.shape !== 'creatures' && !many;
  $('cast-go').textContent = casting?.shape === 'creatures' ? `Cast ${casting.name}` + (casting.picks.length ? ` on ${casting.picks.length}` : '') :
    many ? `Cast ${casting.name}` + (casting.points.length ? ` on ${casting.points.length} ${casting.shape === 'cubes' ? 'Cube' : 'point'}${casting.points.length === 1 ? '' : 's'}` : '') : 'Cast';
  drawBar();
}

// DESIGN-CHECK-01 (GM 2026-10-26: "fix anything you feel would look good and be intuitive"): actions of one kind in one row
// under their name, with short buttons ("Influence: Deception · Intimidation …", "Shove: Prone · Push", "A square: Search · Study")
// instead of a long column of look-alike buttons. The buttons and what they do are unchanged.
const ACT_GROUPS = [[/^Influence \((.+)\)$/, 'Influence'], [/^Shove \((.+)\)$/, 'Shove'], [/^(Search|Study) a square \(traps: .+\)$/, 'A square (traps)'],
  [/^Flurry of Blows: (.+)$/, 'Flurry of Blows (1 Focus, Bonus Action)'], [/^Patient Defense: (.+)$/, 'Patient Defense (Bonus Action)'],   // MONK-01
  [/^Step of the Wind: (.+)$/, 'Step of the Wind (Bonus Action)']];
function grouped(list, make) {
  const out = [], rows = new Map();
  for (const b of list) {
    const g = ACT_GROUPS.find(([re]) => re.test(b.label ?? ''));
    if (!g) { out.push(...make(b)); continue; }
    if (!rows.has(g[1])) { const row = el('div', 'act-group'); row.append(el('span', 'act-group-name', g[1])); rows.set(g[1], row); out.push(row); }
    const [btn, ...rest] = make({ ...b, label: (b.label.match(g[0]) ?? [])[1] ?? b.label });
    btn.title = (btn.title ? btn.title + ' — ' : '') + b.label;
    rows.get(g[1]).append(btn, ...rest);
  }
  return out;
}

// MAP-LAYERS-01 step 3 (GM 2026-10-24: "A rider uses the mount's movement until separated"): the Mount line. Each
// button is the engine's offer with its reason when it can't; the GM's console also picks controlled or independent.
function drawMount(offers, button) {
  const row = $('mount-buttons'), name = id => view?.state.combatants.find(c => c.id === id)?.name ?? id;
  const buttons = mountButtons(offers);
  row.replaceChildren(...buttons.map(button));
  const m = offers.mount, mount = m?.riding ?? (m?.candidates ?? []).find(c => c.ready)?.target;
  if (!PLAYER && mount) {                                           // the GM's choice per creature
    const sel = el('select', 'quiet'); sel.title = "Controlled: moves on its rider's turn (Dash, Disengage, Dodge). Independent: its own turn.";
    for (const v of ['controlled', 'independent']) sel.append(Object.assign(el('option', '', `${name(mount)}: ${v}`), { value: v }));
    sel.value = m.riding ? m.mode : (m.candidates.find(c => c.target === mount)?.mode ?? 'controlled');
    sel.addEventListener('change', async () => { const out = await port.mountMode(mount, sel.value); if (!out.ok) result(out.refused || out.error, 'refused'); refresh(); });
    row.append(sel);
  }
  $('mount-line').textContent = mountText(offers, name);
  $('mount-h').hidden = !buttons.length;
}

// GM 2026-10-24 ("they will need full access"): every other spell and feature on the sheet: Ask the GM. The engine
// checks and spends what it can (the action, a slot, a use); the GM rules the outcome from the GM's screen.
// SPELL-OBJECTS-01 (GM 2026-10-27: "Some spells only target creatures, some objects also"): the spell's own targets
const OBJECTS = { also: 'a creature or an object', only: 'an object, not a creature' };
function askRows(offers, kind) {
  return (offers.asks ?? []).filter(a => a.kind === kind).map(a => {
    const row = el('div', 'srow' + (a.ready ? '' : ' not-ready')), name = el('div', 'sname');
    const what = kind === 'spell' ? [a.level ? `level ${a.level}` : 'cantrip', { action: 'Action', bonus: 'Bonus Action', reaction: 'Reaction', long: 'longer than a turn' }[a.time] ?? a.time,
      a.concentration ? 'Concentration' : null, a.always ? 'always prepared' : null, OBJECTS[a.objects]].filter(Boolean).join(' · ')
      : a.uses != null ? `${a.uses} use${a.uses === 1 ? '' : 's'} left` : 'the GM rules it';
    name.append(el('b', '', a.name), el('small', '', what));
    const b = el('button', 'quiet act', 'Ask the GM'); b.disabled = !a.ready; b.title = a.why || 'The table does not play this yet: the GM rules what it does.';
    b.addEventListener('click', () => {
      const warn = kind === 'spell' ? concentrationBreak(offers, a) : '';   // GM 2026-10-25
      if (warn && !confirm(`${warn} Ask the GM anyway?`)) return;
      const spent = kind === 'spell' ? ' The slot and action are spent now.' : kind === 'feature' ? ' The use is spent now.' : a.time === 'action' ? ' The action is spent now.' : '';
      const note = prompt(`${a.name}: on whom, and what you want (the GM rules it).${spent}`, '');
      if (note === null) return;
      choose({ op: 'ask_gm', kind, name: a.name, note: note.slice(0, 200) });
    });
    row.append(name, b);
    if (!a.ready && a.why) row.append(el('span', 'why', a.why));
    return row;
  });
}
function lookRow(a) {                                               // PLAYER-FLAVOR-01: a player's look, for the GM to approve
  const r = a.flavor, pictures = flavorPictures(), art = pictures.find(t => t.id === r.token_id), rider = pictures.find(t => t.id === r.rider);
  const looks = [r.name && `the name ${r.name}`, r.role && ROLES[r.role], art && `the picture ${art.name}`, r.paint && 'paint', r.base && 'a round base', r.true_height && 'true height', rider && `the rider ${rider.name}`].filter(Boolean);
  const box = el('div', 'ask-item');
  box.append(el('div', '', `${a.seat} asks for a new look for ${a.actor}: ${looks.join(', ') || (r.description ? 'a footnote' : 'the original look')}`));
  if (r.description) box.append(el('div', 'ask-look-note', r.description));
  if (r.paint || art) { const img = el('img', 'ask-look'); img.src = asset(r.paint || art.path); img.alt = ''; box.append(img); }
  const answer = approve => async () => { const out = await flavor.rule(a.actor, approve); if (!out?.ok) result(out?.error || 'The service stopped.', 'refused'); };
  const yes = el('button', 'quiet', 'Approve'), no = el('button', 'quiet', 'Refuse');
  yes.title = 'Everyone at the table sees this look'; no.title = 'The old look comes back. The player gets no note: tell them in person if you want to';
  yes.addEventListener('click', answer(true)); no.addEventListener('click', answer(false));
  box.append(yes, no);
  return box;
}
function drawAsks() {                                               // the GM's list of requests to rule
  const open = PLAYER ? [] : (snap?.asks_open ?? []), looks = PLAYER ? [] : flavor.asks, panel = $('ask-panel');
  panel.hidden = !open.length && !looks.length;
  const key = JSON.stringify([open.map(a => a.n), flavor.asksRev]);
  if (panel.dataset.key === key) return;
  panel.dataset.key = key;
  $('ask-list').replaceChildren(...looks.map(lookRow), ...open.map(a => {
    const box = el('div', 'ask-item'), text = el('input'); text.placeholder = 'What happens (optional)'; text.maxLength = 300;
    const rule = allow => async () => {
      const out = await port.ruling(a.n, text.value, allow).catch(() => ({ ok: false, error: 'The service stopped.' }));
      if (out?.live) take(out); else result(out?.refused || out?.error || 'Not ruled.', 'refused');
    };
    const go = el('button', 'quiet', 'Ruled');
    go.addEventListener('click', rule(false));
    const verb = a.kind === 'spell' ? 'casts' : a.kind === 'action' ? 'asks about' : 'uses';
    box.append(el('div', '', `${a.name}: ${verb} ${a.what}${a.note ? ` — "${a.note}"` : ''}`), text, go);
    if (a.what === 'Climb out of the pit') {                         // GM 2026-11-01: a yes the fight acts on
      const yes = el('button', 'quiet', 'Let them climb'); yes.title = 'They climb out with their own movement on their turn';
      yes.addEventListener('click', rule(true));
      box.append(yes);
    }
    return box;
  }));
}
let sceneUi = null;
function scenePanel() {                                            // the GM's controls; a seated player only reads
  sceneUi ??= mountScene({ panel: $('scene-panel'), body: $('scene-body'), port, take, result, gm: !PLAYER });
  return sceneUi;
}
let pillarUi = null;
function pillarPanel() {                                           // GM 2026-10-26: the scene (no turns outside a fight)
  pillarUi ??= mountPillar({ panel: $('pillar-panel'), body: $('pillar-body'), port, take, result, gm: !PLAYER, mine: () => myCharacter()?.id ?? null });
  return pillarUi;
}
function drawChecks(offers) {                                       // the Checks & saves tab: rolled in the dice tower
  const ch = offers?.checks, body = $('checks-body');
  if (!ch || sheetTab !== 'checks') return;
  const sign = n => (n >= 0 ? '+' : '') + n, AB = { str: 'Strength', dex: 'Dexterity', con: 'Constitution', int: 'Intelligence', wis: 'Wisdom', cha: 'Charisma' };
  const roll = (label, bonus) => { const b = el('button', 'quiet act', `${label} ${sign(bonus)}`);
    b.addEventListener('click', async () => { const out = await dicePort.roll(offers.name, `1d20${bonus ? sign(bonus) : ''}`, `${offers.name}: ${label}`).catch(() => null);
      result(out?.ok === false ? out.error || 'Not rolled.' : `${offers.name}: ${label} rolled in the dice tower.`); }); return b; };
  const grid = (title, items) => { const g = el('div', 'checks-grid'); items.forEach(([l, n]) => g.append(roll(l, n))); return [el('h3', 'sheet-h', title), g]; };
  body.replaceChildren(
    ...grid('Saving throws', Object.entries(ch.saves).map(([a, n]) => [`${AB[a]} save`, n])),
    ...grid('Ability checks', Object.entries(ch.abilities).map(([a, n]) => [AB[a], n])),
    ...grid('Skills', Object.entries(ch.skills).map(([s, n]) => [s + ((ch.proficient ?? []).includes(s) ? ' ●' : ''), n])),
    // GM 2026-10-26: tools proficient (●) or carried; SRD 5.2.1: + Proficiency Bonus only when proficient
    ...(ch.tools?.length ? grid('Tools', ch.tools.map(t => [`${t.name} (${AB[t.ability].slice(0, 3)})${t.proficient ? ' ●' : ''}`, t.bonus])) : []),
    ...grid('Other', [['Death save', 0], ['Concentration (Con save)', ch.saves.con]]));
}
// GM 2026-10-28 ("there needs to be a full character sheet with collapsed menues"); "Yes, on Play live"): the Full sheet tab, the
// acting character's saved sheet (Characters page, or the table's party) with every section folded until opened; for an
// imported sheet the fight's own attacks, spell attack and slots (the rules engine's member: sim/character_build.py)
const memberCache = new Map();
async function memberOf(sheet) {
  const key = sheet.id + ':' + (sheet.reviewed_at ?? '') + ':' + JSON.stringify(sheet).length;
  if (!memberCache.has(key)) memberCache.set(key, (async () => {
    try {
      const token = (await (await fetch(api('/api/hello'))).json()).token;
      const out = await (await fetch(api('/api/characters'), { method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ op: 'character_member', character: fightSheet(sheet), token }) })).json();
      return out?.ok ? out : null;
    } catch { return null; }                                       // the players' door has no rules route: the sheet as saved
  })());
  return memberCache.get(key);
}
let fullFor = null;
async function drawFullSheet(offers) {
  const box = $('sheet-full');
  if (sheetTab !== 'full' || !offers) return;
  const roster = partyRoster(), id = sheetFor(photos, roster, offers.name), c = roster.find(x => x.id === id);
  const key = `${offers.actor}:${id}`;
  if (fullFor === key && box.childNodes.length) return;            // drawn already: keep the folds as they are
  fullFor = key;
  if (!c) { box.replaceChildren(el('p', 'note', `${offers.name} has no saved sheet here. Link one under Sheet above, or save it on the Characters page.`)); return; }
  box.replaceChildren(renderSheet(c, { fold: c.id, head: false }));
  const m = c.derived ? null : await memberOf(c);
  if (m && fullFor === key) box.replaceChildren(renderSheet(c, { fold: c.id, head: false, build: m.build, gmRules: m.gm_rules ?? c.gm_rules ?? [] }));
}
$('tab-full').addEventListener('click', () => { sheetTab = 'full'; fullFor = null; drawSheet(); });
$('tab-turn').addEventListener('click', () => { sheetTab = 'turn'; drawSheet(); });
$('tab-checks').addEventListener('click', () => { sheetTab = 'checks'; drawSheet(); });

// GM 2026-10-23: the bag's items in a fight; a missing prerequisite links to where it is fixed (the Market: the GM's
// dialog, or a player's open shop; Characters: a new tab).
function openLink(link) {
  if (link?.page === 'market') { const b = $('market-open'); const fab = document.getElementById('market-fab');
    if (b && !b.hidden) b.click(); else if (fab && !fab.hidden) fab.click(); else result('The Market opens when the GM opens a shop.', 'refused'); return; }
  if (link?.page) window.open(link.page, '_blank');
}
function drawItems(offers) {
  const line = $('bag-line'), row = $('item-buttons');
  line.textContent = bagText(offers);
  const items = [];
  for (const b of itemButtons(offers)) {
    const x = el('button', 'quiet act' + (b.ready ? '' : ' not-ready'), b.label);
    x.disabled = !b.ready; x.title = b.why || b.effect || '';
    x.addEventListener('click', () => b.square ? pickTrapSquare(b) : choose(b.cmd));
    items.push(x);
    if (!b.ready && b.link) {
      const go = el('button', 'quiet act', `→ ${b.link.label}`);
      go.title = b.why; go.addEventListener('click', () => openLink(b.link));
      items.push(go);
    }
  }
  if (offers?.items && !offers.items.fight_items) {                 // nothing for a fight in the bag: where to get it
    const go = el('button', 'quiet act', '→ Market');
    go.title = 'Nothing in the bag has a use in a fight here. Potions, Basic Poison, a Healer\'s Kit, Antitoxin: buy them at a shop the GM opens.';
    go.addEventListener('click', () => openLink(offers.items.link));
    items.push(go);
  }
  row.replaceChildren(...items);
}

// LIGHTS-01 (GM 2026-10-26): the map's own light as a veil with the lit areas cut out of it (Bright: clear; Dim: half),
// each light's rings (Bright solid, Dim dashed; a Bullseye Lantern's Cone) and the lights on the ground. The players'
// window keeps only the lights its party sees (the service cuts a seat's; the pop-out cuts here by the fog).
function shownLights() {
  const lights = snap?.lights;
  if (!PLAYER || !lights) return lights;
  return seenLights(lights, snap.party_sight, playerCombatants(view.state.combatants, snap.party_sight).map(c => c.id));
}
function drawLight(root) {
  const lights = shownLights();
  if (!lights) return;
  const [x0, y0, x1, y1] = bounds(view), sq = view.map.square_ft, rings = lightRings(lights, sq);
  const veil = VEIL[PLAYER ? 'players' : 'gm'][lights.ambient];
  const shape = (r, radius, attrs) => r.cone ? svg('path', { d: conePath(r.x + .5, r.y + .5, radius, r.aim), ...attrs })
    : svg('circle', { cx: r.x + .5, cy: r.y + .5, r: radius, ...attrs });
  if (veil) {
    const box = { x: x0 - 2, y: y0 - 2, width: x1 - x0 + 5, height: y1 - y0 + 5 };
    const mask = svg('mask', { id: 'light-mask', maskUnits: 'userSpaceOnUse', ...box });
    mask.append(svg('rect', { ...box, fill: '#fff' }));
    for (const r of rings) mask.append(shape(r, r.dim, { fill: '#808080' }));
    for (const r of rings) if (r.bright > 0) mask.append(shape(r, r.bright, { fill: '#000' }));
    const defs = svg('defs'); defs.append(mask); root.append(defs);
    root.append(svg('rect', { class: 'light-veil', ...box, fill: '#06070a', 'fill-opacity': veil, mask: 'url(#light-mask)', 'pointer-events': 'none' }));
  }
  const g = svg('g', { class: 'light-rings', 'pointer-events': 'none' });
  for (const r of rings) {
    const dim = shape(r, r.dim, { fill: 'none', stroke: '#f2c45a', 'stroke-width': .04, 'stroke-opacity': .5, 'stroke-dasharray': '.18 .12' });
    dim.append(svg('title', {}, r.title)); g.append(dim);
    if (r.bright > 0) g.append(shape(r, r.bright, { fill: '#f6c65b', 'fill-opacity': .05, stroke: '#f2c45a', 'stroke-width': .05, 'stroke-opacity': .8 }));
  }
  for (const m of groundLights(lights)) {                          // a dropped light: a small flame on its square
    const f = svg('g', { class: 'light-ground' });
    f.append(svg('circle', { cx: m.x + .5, cy: m.y + .62, r: .16, fill: m.lit ? '#f6b73c' : '#5c4c34', stroke: '#1b1710', 'stroke-width': .03 }));
    if (m.lit) f.append(svg('path', { d: `M${m.x + .5} ${m.y + .28} q.12 .2 0 .3 q-.12 -.1 0 -.3z`, fill: '#ffe08a' }));
    f.append(svg('title', {}, m.title)); g.append(f);
  }
  root.append(g);
}
function drawLightButtons(offers) {
  $('light-line').textContent = offers?.lights ? lightText(offers, snap?.lights) : '';
  const row = [];
  for (const b of lightButtons(offers)) {
    const x = el('button', 'quiet act' + (b.ready ? '' : ' not-ready'), b.label);
    x.disabled = !b.ready; x.title = b.why || '';
    x.addEventListener('click', () => b.square ? pickTrapSquare(b) : choose(b.cmd));
    row.push(x);
    if (!b.ready && b.link) row.push(linkButton(b));
  }
  $('light-buttons').replaceChildren(...row);
  $('light-h').hidden = !row.length && !(snap?.lights?.sources ?? []).some(l => l.holder === offers?.actor);
}
function drawAmbient() {                                           // the GM's Map light: what the fight runs with
  const sel = $('map-light');
  if (!sel || PLAYER) return;
  if (snap?.lights && document.activeElement !== sel) sel.value = snap.lights.ambient;
  $('map-light-note').textContent = '';
}
$('map-light')?.addEventListener('change', async e => {
  if (!snap?.lights || snap.done) { status(`The next fight starts in ${AMBIENT_LABEL[e.target.value] ?? "the map's own light"}.`); return; }
  const out = await port.light({ ambient: e.target.value }).catch(() => null);
  if (out?.live) take(out);
  status(out?.ok ? `The map's own light is now ${AMBIENT_LABEL[e.target.value]}.` : out?.refused || out?.error || 'Refused.', !out?.ok);
});

// HINTS-01 (GM 2026-10-22: "Hints are opt-in"): the Hints switch (Off / Reminders) and the quiet line by End turn. The
// GM console keeps a level per character in this browser, Off until turned on (hotseat); a seated phone's level is its
// seat's (the service sends hints only to that seat, and only at Reminders), remembered in this browser too.
// DM-SWAP-01: the owning GM's screen while another is the GM (the GM door sends its pages to ?view=player&dm=handed)
const OLD_DM = PLAYER && new URLSearchParams(location.search).get('dm') === 'handed';
let handedChar = '';                                              // the character the owning GM plays meanwhile
const SEATED = PLAYER && (!!loadSeat()?.character || OLD_DM);
// GM 2026-10-25: a seat with no character (watch only), or the owning GM watching while handed: every turn, read only
let WATCHER = PLAYER && !!loadSeat() && !loadSeat()?.character && !OLD_DM;   // the owning GM's case: set once hello says
// H3 (GM 2026-10-28): the highest level the GM allows: a seat's from the service (the table cap and its own limit), the
// console's from the table cap (it applies to the GM's own hotseat characters too)
let seatHints = null, seatMax = 'reminders', hintsCap = 'reminders', hintsDrawn = '', lineDrawn = '';
const hintsMax = () => SEATED ? seatMax : hintsCap;
const hintsLevel = offers => SEATED ? seatHints ?? 'off' : offers ? lowerLevel(consoleLevel(offers.name), hintsCap) : 'off';
function drawHints(offers) {
  const lvl = hintsLevel(offers), muted = mutedKinds(), box = $(SEATED ? 'pv-hints' : 'hints-row'), line = $(SEATED ? 'pv-hints-line' : 'hints-line');
  const key = JSON.stringify([lvl, [...muted], SEATED || offers?.name, hintsMax()]);   // redrawn only when it changes (a phone polls every second)
  if (key !== hintsDrawn && (SEATED || offers)) {
    hintsDrawn = key;
    drawSwitch(box, { lvl, muted, max: hintsMax(), change: v => setHints(offers?.name, v), mute: muteHint, label: SEATED ? 'Hints' : 'Hints for ' + offers.name });
  }
  box.hidden = SEATED ? !seatHints : !offers;
  // H8: once, while this screen's hints are off, where to turn them on (a tap on × and it stays away)
  const offLine = lvl === 'off' && (SEATED || offers) && !hintsOffSeen() ? [{ kind: 'off', text: 'Hints are off. You can turn on reminders from your sheet.' }] : [];
  const items = [...offLine, ...hintLine(offers, lvl, muted)], text = JSON.stringify(items.map(h => h.text));
  if (text !== lineDrawn) { lineDrawn = text; drawLine(line, items, kind => kind === 'off' ? seeHintsOff() : muteHint(kind)); }
  drawFact();
}
const HINTS_OFF_KEY = 'mythastria-hints-off-seen';
const hintsOffSeen = () => { try { return localStorage.getItem(HINTS_OFF_KEY) === '1'; } catch { return false; } };
function seeHintsOff() { try { localStorage.setItem(HINTS_OFF_KEY, '1'); } catch { /* shown again next time */ } lineDrawn = ''; drawSheet(); }
// H4-H6: the facts while pointing (an attack held over a target, a move's destination, an area aimed), Reminders only
let factDrawn = '', aimAsked = '', aimFact = null, aimTimer = null;
function drawFact() {
  const offers = snap?.offers, lvl = hintsLevel(offers), muted = mutedKinds(), cs = view?.state.combatants;
  let items = [];
  if (offers && lvl === 'reminders') {
    if (held && pointedActor) items = attackFacts(offers, held, pointedActor, lvl, muted);
    else if (casting && casting.shape !== 'creatures' && aimAt) items = areaFacts(askAim(casting, aimAt), offers.side, cs, lvl, muted);
    else if (!held && !casting && routeTo?.path?.length) { const [x, y] = routeTo.path.at(-1); items = reachFacts(offers, x, y, cs, lvl, muted); }
  }
  const text = JSON.stringify(items.map(h => h.text));
  if (text !== factDrawn) { factDrawn = text; drawFacts($(SEATED ? 'pv-hints-fact' : 'hints-fact'), items, muteHint); }
}
// who the aimed area catches: asked of the simulator (/api/live/aim, read only) once the pointer rests on a square
function askAim(s, at) {
  const slot = spellLevelPick[s.name] > s.level ? spellLevelPick[s.name] : undefined;
  const key = `${s.name}|${at[0]},${at[1]}|${slot ?? ''}|${snap?.revision}`;
  if (key !== aimAsked) {
    aimAsked = key; clearTimeout(aimTimer);
    aimTimer = setTimeout(async () => {
      const out = await port.aim({ spell: s.name, x: at[0], y: at[1], ...(slot ? { slot } : {}) }).catch(() => null);
      if (aimAsked !== key) return;
      aimFact = { key, aim: out?.ok ? out.aim : null }; drawFact();
    }, 150);
  }
  return aimFact?.key === key ? aimFact.aim : null;
}
function muteHint(kind, on = true) { setMuted(kind, on); drawSheet(); }
async function setHints(name, level) {
  if (!SEATED) { setConsoleLevel(name, level); drawSheet(); return; }
  const was = seatHints;
  seatHints = level; drawSheet();
  const out = await port.hints(level).catch(() => null);
  if (out?.ok) { seatHints = out.seat?.hints ?? level; setSeatLevel(seatHints); }   // kept in this browser once the table took it
  else { seatHints = was; status(out?.error || 'The table did not take the Hints choice.', true); }   // H3: the GM's limit
  refresh();
}
function takeSeat(seat) {                                           // a seat's level from the service; this browser's wins once
  const first = seatHints === null;
  seatHints = seat.hints ?? 'off';
  seatMax = seat.hints_max ?? 'reminders';                         // H3: the GM's table cap and this seat's limit
  if (first && seatLevel() && seatLevel() !== seatHints && lowerLevel(seatLevel(), seatMax) === seatLevel()) setHints(null, seatLevel());
}

// LIVE-UNDO-01 (GM 2026-10-21: "All the combat tools need an undo if they don't trigger any other event"; then "or rather
// approve an undo button"): the service says whether the turn's last choice can be taken back (it set nothing else going)
// and why not. The player's Undo asks; the GM's seat (never the player view) approves or refuses.
function drawUndo(offers) {
  const u = offers?.undo, keys = keymap.undo.map(label).join(' / ');
  const text = u?.ready ? `Undo ${u.label}` : u?.asked ? 'Undo asked: waiting for the GM' : 'Undo';
  const title = u?.ready ? `Ask the GM to take back the ${u.label} (${keys || 'no key'})` : u?.why ?? 'Nothing to undo this turn.';
  for (const b of [$('undo'), $('pv-undo')]) { b.disabled = !u?.ready; b.textContent = text; b.title = title; }
  $('pv-undo').hidden = !PLAYER || !offers;
  $('undo-why').textContent = u && !u.ready && u.op ? u.why : '';     // a reason only once there is a last choice
  $('undo-ask').hidden = PLAYER || !u?.asked;
  if (u?.asked) $('undo-ask-text').textContent = `${offers.name}: ${u.label} — undo?`;
}
function undoLast() {
  const u = snap?.offers?.undo;
  if (!snap?.waiting) return;
  if (!u?.ready) { result(u?.why ?? 'Nothing to undo this turn.', 'refused'); return; }
  held = null; casting = null;
  choose({ op: 'undo' });
}

// The simulator's own bookkeeping (the bridge's AI offers, FG messages): hidden unless "Show engine details" is ticked.
// GM 2026-10-25: and the bridge's start-up lines ("Prepared 373 sequential combat request(s)", "Found PC locally"), as the
// service's own _sync_noise; never on a player's screen (the tick box is GM-only there)
const ENGINE = /^(ai-|AUTO_DAMAGE|PARSED_|NEXT_ACTOR|AI turn complete|Active actor|Auto pickup|startup sync|Prepared |Found |Queued |Sent |Sync|PowerManager\.|AI Bridge|Requesting localhost|Localhost authorized|Fantasy Grounds found)/;
const engineLine = text => ENGINE.test(text);

function drawMapEffects() { const root = $('map'); root.querySelectorAll('.fx-shape').forEach(n => n.remove()); const g = svg('g', { class: 'fx-shape', 'pointer-events': 'none' }); drawEffects(g); root.append(g);
  if (PLAYER) root.querySelectorAll('[data-pc]').forEach(t => root.append(t)); }   // MAP-LAYERS-01: players always see their own characters over a cloud

function drawLog(entries) {
  const log = $('log');
  for (const e of entries) {
    if (!fightStarted && /^--- round /.test(e.text)) fightStarted = true;   // the simulator's startup lines are not the fight
    if (fightStarted) log.append(el('div', 'log-' + e.kind + (engineLine(e.text) ? ' engine' : ''), e.text));
  }
  while (log.childElementCount > 300) log.firstChild.remove();
  log.scrollTop = log.scrollHeight;
}

// ------------------------------------------------------------------ third person (LIVE-PLAY-01 3D)
const RING = { 'legal-foe': [.5, .9, .55, .95], 'legal-ally': [.95, .75, .3, .95], refused: [.9, .35, .3, .7] };
function ensureThirdPerson() {
  if (thirdPerson) return thirdPerson;
  thirdPerson = createThirdPerson({
    canvas: $('tp-canvas'), getView: () => viewWithEffects(), getSelected: () => snap?.waiting ?? null, getToken: id => byId.get(id) ?? photoTokens.get(id) ?? paintTokens.get(id) ?? null,
    getEvents: () => [], status: $('tp-status'), followBehind: () => true, dragToMove: () => !held && !!snap?.waiting,
    onSelect: id => { if (held) { dropOn(id); return; } togglePick(id); },                    // a tap on a figure while an attack is held
    pickRank: () => pickRank,                                     // 2026-10-21: a held attack picks a legal foe behind an ally
    onMove: () => {}, onGround: (x, y) => { if (casting && casting.shape !== 'creatures') { cast({ spell: casting.name, x, y }); return; } if (!held && !casting && snap?.waiting) moveTo(x, y); },
    ringFor: a => held ? RING[lookFor(held, a).cls] ?? null : casting?.shape === 'creatures' ? (casting.picks.includes(a.id) ? RING['legal-foe'] : RING[spellLook(casting, a, snap?.offers).cls] ?? null) : null,
    fog: () => {                                                  // 2026-10-21: the 2D map's fog, also in 3D
      if (!snap?.party_sight || !fogOn() || !view) return null;
      const [, , x1, y1] = bounds(view);
      return { ...fogCells(Math.max(view.map.cols, x1 + 1), Math.max(view.map.rows, y1 + 1), snap.party_sight, explored),
        hiddenAlpha: PLAYER ? .97 : .42, dimAlpha: PLAYER ? .55 : .18 };
    },
    floorMarks: () => !held && !casting && snap?.waiting ? { cells: snap.offers?.reach ?? [], path: routeTo?.path ?? null, edge: reachEdge3D(snap.offers?.reach),
      hover: hoverSquare && hoverSquare.tip ? { x: hoverSquare.x, y: hoverSquare.y, ok: hoverSquare.tip.ok } : null } : null,
    onHoverActor: id => { pointedActor = id; drawTip(); },
    onHover: (x, y) => { if (casting && casting.shape !== 'creatures') { aimAt = x == null ? null : [x, y]; routeTo = null; return; } const r = x == null ? null : reachPath(snap?.offers, x, y, myPosition()); routeTo = r;
      hoverSquare = x == null || held || casting || !snap?.waiting ? null : { x, y, tip: squareTip(snap.offers, x, y, myPosition()) }; drawTip(); },
    onFailure: message => { setMode('tactical'); result(message, 'refused'); },
  });
  thirdPerson.zoomBy(1.7); thirdPerson.orbit(0, .22);   // start back and above the party, so its own figures do not fill the view
  zoomButtons($('tp-canvas'), { zoomIn: () => thirdPerson.zoomBy(.8), zoomOut: () => thirdPerson.zoomBy(1.25), reset: () => thirdPerson.recenter() });   // MAP-ZOOM-01
  return thirdPerson;
}

function setMode(next) {
  mode = next === 'third' ? 'third' : 'tactical';
  if (mode === 'third' && !ensureThirdPerson().enable()) mode = 'tactical';
  if (mode === 'tactical') thirdPerson?.disable();
  $('tp-wrap').hidden = mode !== 'third';
  drawBar();
  $('map').toggleAttribute('hidden', mode === 'third');            // an SVG element has no .hidden property
  $('view-mode').value = mode;
  try { localStorage.setItem('isles-play-view', mode); } catch { /* not kept */ }
}

// ------------------------------------------------------------------ keys (remappable; see camera-keys.mjs)
const typing = e => flavor.dialog.open || /^(input|textarea|select)$/i.test(e.target?.tagName ?? '') || e.target?.isContentEditable;
addEventListener('keydown', e => {
  if (typing(e) || $('keys-dialog').open || e.repeat && !['rotate_left', 'rotate_right', 'tilt_up', 'tilt_down', 'zoom_in', 'zoom_out'].includes(actionFor(keymap, comboOf(e)))) return;
  const action = actionFor(keymap, comboOf(e));
  if (!action) return;
  const tp = mode === 'third' ? thirdPerson : null;
  const did = {
    rotate_left: () => tp?.orbit(.12, 0), rotate_right: () => tp?.orbit(-.12, 0), tilt_up: () => tp?.orbit(0, .06),
    tilt_down: () => tp?.orbit(0, -.06), recenter: () => tp?.recenter(),
    zoom_in: () => tp ? tp.zoomBy(.9) : mapZoom.by(1.25), zoom_out: () => tp ? tp.zoomBy(1.11) : mapZoom.by(.8),   // MAP-ZOOM-01: the 2D map too
    toggle_view: () => setMode(mode === 'third' ? 'tactical' : 'third'), end_turn: () => choose({ op: 'end' }),
    undo: () => undoLast(),
  }[action];
  if (did) { e.preventDefault(); did(); }
});

let capturing = null;
function drawKeys() {
  $('keys-table').replaceChildren(...Object.entries(ACTIONS).map(([action, text]) => {
    const tr = el('tr'), keys = el('td');
    if (capturing === action) keys.append(el('span', 'waiting', 'Press a key…'));
    else if (!keymap[action].length) keys.append(el('span', 'note', 'none'));
    else for (const k of keymap[action]) keys.append(el('kbd', '', label(k)));
    const change = el('button', '', 'Change'), clear = el('button', '', 'Clear');
    change.onclick = () => { capturing = action; drawKeys(); };
    clear.onclick = () => { keymap = clearKeys(keymap, action); saveKeymap(keymap); drawKeys(); };
    const tools = el('td'); tools.append(change, ' ', clear);
    tr.append(el('td', '', text), keys, tools);
    return tr;
  }));
  $('view-help').textContent = `Drag your character to move · right-, middle- or floor-drag to orbit · wheel to zoom · ${keymap.rotate_left.concat(keymap.rotate_right).map(label).join('/') || 'no keys'} turn · ${keymap.recenter.map(label).join('/') || 'no key'} behind my character`;
}
$('keys-dialog').addEventListener('keydown', e => {
  if (!capturing) return;
  e.preventDefault(); e.stopPropagation();
  if (e.key === 'Escape') { capturing = null; drawKeys(); return; }
  const combo = comboOf(e);
  if (!combo) return;                                            // a modifier alone: wait for the key
  const out = rebind(keymap, capturing, combo);
  keymap = out.keymap; saveKeymap(keymap);
  capturing = null; drawKeys();
  if (out.displaced) result(`${label(combo)} moved from "${ACTIONS[out.displaced]}" to the new action.`);
});
$('keys-open').addEventListener('click', () => { drawKeys(); $('keys-dialog').showModal(); });
$('keys-close').addEventListener('click', () => { capturing = null; $('keys-dialog').close(); });
$('keys-reset').addEventListener('click', () => { keymap = structuredClone(DEFAULT_KEYS); saveKeymap(keymap); drawKeys(); });
$('view-mode').addEventListener('change', e => setMode(e.target.value));

// The view drawn from the snapshot: doors as they are now, the fog remembered, the sheets' photos on the party's tokens,
// and in the player view only the creatures the party sees (VIEW-01).
function buildView() {
  view = liveView(scenario, snap, registry);
  if (!view) return;
  view = { ...view, map: withDoors(view.map, snap.open_doors) };
  rememberSight();
  ({ view, tokens: photoTokens } = decorate(view, photos, rosterFrom()));
  basePictures = new Map(view.state.combatants.map(c => [c.id, c.token_path ?? '']));
  view = { ...view, state: { ...view.state, combatants: view.state.combatants.map(c => flavorActor(c, flavor.state, view.map.name, flavorPictures(), { player: PLAYER, fightId: snap.fight_id, adventure: adventureOf() })) } };
  paintTokens = new Map(view.state.combatants.filter(c => c.token_id?.startsWith('paint:')).map(c => [c.token_id, { id: c.token_id, path: c.token_path, squares: c.space_ft / view.map.square_ft }]));
  if (view.map.name !== notesMap || (PLAYER && Date.now() - notesAt > 5000)) loadNotes(view.map.name);
  if (PLAYER) view = { ...view, state: { ...view.state, combatants: playerCombatants(view.state.combatants, snap.party_sight)
    .filter(c => c.pc || !mapPaint.blocks(c.x, c.y)) } };          // GM 2026-10-28: the shown paint blocks the players' vision
}
const contentChannel = typeof BroadcastChannel === 'function' ? new BroadcastChannel('mythastria-content') : null;
contentChannel?.addEventListener('message', e => { if (e.data?.type === 'packs-changed') location.reload(); });

// GM 2026-11-01: the Panic Button, the undo's steps, the turn timer (tools/sim_service.py, sim/live_play.py)
let stopped = false, steps = { steps: 0, last: null }, rewound = 0, clockAt = 0;
function noteControls(out) {
  if (typeof out?.panic === 'boolean') stopped = out.panic;
  if (out?.timeline) steps = out.timeline;
  $('panic').textContent = stopped ? 'Resume' : 'Panic';
  $('panic').classList.toggle('stopped', stopped);
  $('panic-bar').hidden = PLAYER || !stopped;
  $('panic-cover').hidden = !PLAYER || !stopped;
  $('gm-undo').hidden = PLAYER || !steps.steps;
  $('gm-undo').textContent = `Undo step (${steps.steps})`;
  $('gm-undo').title = steps.last ? `Take back: ${steps.last}. The fight waits, frozen, until you let it go on; the same choices give the same dice.` : '';
  $('gm-goon').hidden = PLAYER || stopped || !snap?.frozen || !!snap.done;
  drawTurnClock();
}
function drawTurnClock() {
  const clock = $('turn-timer'), on = !!snap?.turn_timer && snap.turn_seconds != null && !snap.done;
  clock.hidden = !on;
  if (!on) return;
  const still = !!snap.frozen || stopped, s = snap.turn_seconds + (still ? 0 : Math.floor((Date.now() - clockAt) / 1000));
  clock.textContent = `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`;
  clock.classList.toggle('paused', still);
}
setInterval(drawTurnClock, 1000);

function take(out) {
  if (out.scenario) scenario = out.scenario;
  if (SEATED && out.seat) takeSeat(out.seat);                     // HINTS-01: the seat's hint level
  if (!PLAYER && out.hints_cap) hintsCap = out.hints_cap;          // H3: the table cap on the GM's own console
  if (out.scenario?.remix?.groups && !PLAYER) result('Remix Prep: ' + out.scenario.remix.groups.map(g => `${g.count} ${g.to}`).join(', ') + '\n' + out.scenario.remix.read_aloud);
  if (!out.live) { noteControls(out); return; }
  if ((out.live.rewinds ?? 0) !== rewound) {                       // GM-UNDO-01: taken back: this screen's log starts again
    rewound = out.live.rewinds ?? 0;
    $('log').replaceChildren(); logSince = 0; fightStarted = false;
    port.state(0).then(o => { if (o?.ok) take(o); }).catch(() => {});
    return;
  }
  snap = out.live;
  clockAt = Date.now();
  noteControls(out);
  drawStandIn();                                                   // GM 2026-10-28: the pop-out shows the held character's screen
  buildView();
  showCastEffects();
  if (snap.log?.length) { drawLog(snap.log.filter(e => e.n > logSince)); logSince = snap.log[snap.log.length - 1].n; }
  drawAsks();                                                      // GM 2026-10-24: requests waiting for the GM
  drawAmbient();                                                   // LIGHTS-01: the GM's Map light
  scenePanel().draw(snap);                                         // GM 2026-10-24: attitudes and morale
  pillarPanel().draw(snap);                                        // GM 2026-10-26: the scene
  document.body.classList.toggle('in-scene', inScene(snap));
  if (held && (held.startsWith(ACT_KEY) ? !snap.offers?.actions?.some(a => a.op === held.slice(ACT_KEY.length).split(':')[0] && a.ready)
    : !snap.offers?.attacks.some(a => a.key === held))) held = null;
  if (casting && !snap.offers?.spells?.some(s => s.name === casting.name && s.ready)) casting = null;
  drawMap(); drawSheet();
  drawFrozen();
  if (!PLAYER && view && snap.tracker && !snap.tracker.scene && !snap.tracker.sight_confirmed && !snap.done && sightAsked !== snap.fight_id
      && !$('sight-dialog').open && !snap.reaction) { sightAsked = snap.fight_id; openSight(); }   // SIGHT-01: at the fight's start
                                                                   // (SPELL-BATCH-02: never over a Reaction asked)
  drawControl();
  const who = view?.state.combatants.find(c => c.id === snap.waiting)?.name;
  const scened = sceneStatus(snap, new Map((view?.state.combatants ?? []).map(c => [c.id, c.name])));
  status(snap.error ? 'The simulator stopped: ' + snap.error : snap.done ? 'The fight is over.' + (snap.scene?.outcome ? ' ' + snap.scene.outcome : '') :
    snap.frozen ? 'The GM has frozen the fight.' : scened ? scened :
    who ? `Round ${snap.round}: ${who}'s turn.` + (PLAYER ? '' : ' Your choice.') : 'The creatures are acting…', !!snap.error);
  drawReaction();                                                  // SPELL-BATCH-02: a Reaction asked (Shield, Counterspell)
  drawStealth();                                                   // STEALTH-01: declared stealth, the group check
  drawInitiative();                                                // INITIATIVE-01: the players roll Initiative
  if (!PLAYER && !$('reaction-auto').matches(':focus')) $('reaction-auto').checked = !!snap.reaction_auto;   // OA-AUTO-01
  if (!PLAYER && !$('social-on').matches(':focus')) $('social-on').checked = !snap.social_off;   // GM 2026-11-01
  if (!PLAYER && !$('timer-on').matches(':focus')) $('timer-on').checked = !!snap.turn_timer;    // GM 2026-11-01
  if (!PLAYER && !$('srd-on').matches(':focus')) $('srd-on').checked = !!snap.by_srd;            // BY-THE-SRD-01
  clearInterval(poll);
  if (!snap.done) poll = setInterval(refresh, 1000);   // every screen follows: a seated player may act on a phone
}
// GM 2026-10-24 ("Another option to freeze and make combat buttons inactive"): the service holds a frozen fight; the
// sheet's buttons wait and say why, and the GM's Freeze button lets it go on.
// GM 2026-10-24 ("let the DM take control of any character turns, presumably by permission, but not required"): the GM's
// Take over / Give back on the character whose turn it is; a seated player's Hand to the GM / Take back (only when they
// handed it); while the GM holds a character, its player's phone shows why and has no buttons.
function myCharacter() {
  const name = ((OLD_DM ? handedChar : loadSeat()?.character) ?? '').toLowerCase();
  return (snap?.state?.combatants ?? []).find(c => c.pc && name && c.name.toLowerCase() === name);
}
// GM 2026-10-28 ("when a DM takes over the player, the popup map shows the view of the player, not the DM"): while the GM
// plays a character (Take over, or its player's Hand to the GM), the pop-out shows that player's screen: the map, that
// character's turn and sheet read only, What happened; the map alone again when the GM gives the character back.
function drawStandIn() {
  if (!PLAYER || SEATED || OLD_DM || WATCHER) return;             // the pop-out only: a seat keeps its own character
  const held = snap?.done ? [] : Object.keys(snap?.gm_control ?? {});
  standIn = held.includes(snap?.waiting) ? snap.waiting : held.includes(standIn) ? standIn : held[0] ?? null;
  document.body.classList.toggle('seated', !!standIn);
  document.body.classList.toggle('watching', !!standIn);
  document.title = standIn ? `Mythastria — ${rulesActor(standIn)?.name ?? 'Map'}` : 'Mythastria — Map';
}
function drawControl() {
  const control = snap?.gm_control ?? {}, done = !snap || snap.done;
  if (!PLAYER) {
    const who = (snap?.state?.combatants ?? []).find(c => c.id === snap?.waiting && c.pc), by = who && control[who.id];
    $('gm-take').hidden = done || !who;
    if (who) $('gm-take').textContent = by ? `Give ${who.name} back` : `Take over ${who.name}`;
    $('gm-take-note').hidden = !by;
    if (by) $('gm-take-note').textContent = by === 'player' ? `${who.name}'s player handed the character to you.` : `You are playing ${who.name}; its player waits.`;
    return;
  }
  const me = SEATED ? myCharacter() : standIn && rulesActor(standIn), by = me && control[me.id];
  $('pv-hand').hidden = done || !me || by === 'gm';
  $('pv-hand').textContent = by === 'player' ? 'Take my character back' : 'Hand to the GM';
  $('pv-hand-note').hidden = !by;
  if (by) $('pv-hand-note').textContent = by === 'gm' ? `The GM is playing ${me.name} now.` : `The GM plays ${me.name} until you take it back.`;
}
// SPELL-BATCH-02 (GM 2026-10-28: Shield and Counterspell, "the fight asks the player live"): the fight waits on a
// Reaction question. The seat that plays the character answers (Cast / Don't cast); the GM console always can (Answer for
// them: a slow or absent player, a character nobody plays, one the GM holds), so a fight never hangs; the others see who
// decides. live: the snapshot (refresh draws it even while the console waits on its own choice).
function drawReaction(live = snap) {
  const r = live?.done ? null : live?.reaction, box = $('reaction-ask');
  const mode = !r ? '' : !PLAYER ? ((live.gm_control ?? {})[r.pc] ? 'gm-held' : 'gm') : r.mine && !WATCHER ? 'mine' : 'wait';
  box.hidden = !r;
  if (r) status(`The fight waits for ${r.name}'s Reaction: ${r.spell}?`);
  const key = r ? `${live.fight_id}:${r.n}:${mode}` : '';
  if (box.dataset.key === key) return;
  box.dataset.key = key;
  if (!r) { box.replaceChildren(); return; }
  if (mode === 'wait') {
    box.replaceChildren(el('h2', '', `${r.name}: ${r.spell}? (Reaction)`), el('p', 'note', `The fight waits for ${r.name}'s answer.`));
    return;
  }
  const slots = Object.entries(r.slots ?? {}).filter(([lv]) => +lv >= r.level).map(([lv, n]) => `${n} of level ${lv}`).join(', ');
  const whose = mode === 'mine' ? 'your' : `${r.name}'s`;
  // REACTIONS-LIVE-01: a feature (Uncanny Dodge) is used, a spell cast; no level: no slot (a feature, a free use)
  const verb = r.verb ?? 'cast', Verb = verb[0].toUpperCase() + verb.slice(1);
  const parts = [el('h2', '', mode === 'mine' ? `${Verb} ${r.spell}? (Reaction)` : `${r.name}: ${verb} ${r.spell}? (Reaction)`),
    el('p', '', `${r.trigger}.`)];
  if (r.note) parts.push(el('p', 'note', r.note));
  parts.push(el('p', 'note', r.level ? `It spends ${whose} Reaction and a level ${r.level}+ spell slot${slots ? ` (left: ${slots})` : ''}.`
    : r.cost ?? `It spends ${whose} Reaction.`));                    // MONK-01: a redirect spends a Focus Point
  if (mode === 'gm') parts.push(el('p', 'note', `${r.name}'s player is asked. If they are slow, away or not seated, answer for them.`));
  if (mode === 'gm-held') parts.push(el('p', 'note', `You are playing ${r.name}: the answer is yours.`));
  const yes = el('button', '', mode === 'gm' ? `Answer for them: ${verb} ${r.spell}` : `${Verb} ${r.spell}`);
  const no = el('button', 'quiet', mode === 'gm' ? 'Answer for them: no' : `Don't ${verb}`);
  const answer = async cast => {
    yes.disabled = no.disabled = true;
    const out = await port.reaction(r.n, cast).catch(() => ({ ok: false, error: 'The service stopped.' }));
    if (out?.live) take(out);
    else { result(out?.refused || out?.error || 'Not answered.', 'refused'); box.dataset.key = ''; refresh(); }
  };
  yes.addEventListener('click', () => answer(true));
  no.addEventListener('click', () => answer(false));
  const row = el('p', 'reaction-buttons');
  row.append(yes, ' ', no);
  box.replaceChildren(...parts, row);
}
// STEALTH-01 (GM 2026-10-28: "movement needs a stealth option ... The DM rolls perception ... a group stealth roll and each
// rolls stealth for their character on the popup itself"; Mythastria sim/stealth.py). A player's Hide opens the Stealth
// popup: Roll Stealth rolls it on the GM's Mythastria (the Hide action: the Action, or the Bonus Action by Cunning Action;
// free outside a fight) and the total waits for the GM's Perception. The GM's Group stealth puts a popup on each named
// player's screen; each rolls there. The GM's card: Roll Perception for a waiting stealth; the group check's rolls,
// Roll for them (a slow player, a character nobody plays), then Roll Perception.
let stealthAsk = null, stealthGo = false;
function drawStealth(live = snap) {
  const st = live?.done ? null : live?.stealth, box = $('stealth-ask');
  const me = PLAYER ? myCharacter()?.id ?? null : null, call = st?.call;
  const mineCall = PLAYER && !WATCHER && call?.mine ? call.who.find(w => w.id === me) : null;
  const sneaks = st?.sneaks ?? [];
  const key = JSON.stringify([live?.fight_id, stealthAsk, PLAYER, call, sneaks]);
  const show = !!stealthAsk || (PLAYER ? !!mineCall || sneaks.length > 0 : !!call || sneaks.length > 0);
  box.hidden = !show;
  if (box.dataset.key === key) return;
  box.dataset.key = key;
  if (!show) { box.replaceChildren(); return; }
  const send = async (body, b) => {
    b.disabled = true;
    const out = await port.stealth(body).catch(() => ({ ok: false, error: 'The service stopped.' }));
    if (out?.live) take(out);
    else { result(out?.refused || out?.error || 'Not done.', 'refused'); box.dataset.key = ''; refresh(); }
  };
  const btn = (text, fn, cls = '') => { const b = el('button', cls, text); b.addEventListener('click', () => fn(b)); return b; };
  const parts = [];
  if (stealthAsk) {                                                // a player's own Hide: the popup rolls it
    const who = (snap?.state?.combatants ?? []).find(c => c.id === snap?.waiting)?.name ?? 'Your character';
    const fight = !snap?.pillar?.mode || snap.pillar.mode === 'fight';
    const cost = !fight ? 'Outside a fight it costs nothing.' : stealthAsk.bonus ? 'It uses your Bonus Action (Cunning Action).' : 'It uses your Action (the Hide action).';
    parts.push(el('h2', '', 'Stealth'), el('p', '', snap?.by_srd ? `${who} tries to hide: a DC 15 Dexterity (Stealth) check. On a success the total is the DC to find ${who}.` : `${who} moves stealthily: roll Dexterity (Stealth). The total stays while ${who} moves; the GM rolls Perception for the creatures that might notice.`),
      el('p', 'note', cost));
    const row = el('p', 'reaction-buttons');
    row.append(btn('Roll Stealth', () => { const cmd = stealthAsk; stealthAsk = null; stealthGo = true; box.dataset.key = ''; choose(cmd); }), ' ',
      btn('Cancel', () => { stealthAsk = null; drawStealth(); }, 'quiet'));
    parts.push(row);
  } else if (PLAYER) {
    if (mineCall && !mineCall.rolled) {
      parts.push(el('h2', '', 'Group stealth check'), el('p', '', `The GM calls for a group Dexterity (Stealth) check. Roll for ${mineCall.name}.`));
      const row = el('p', 'reaction-buttons');
      row.append(btn('Roll Stealth', b => send({ op: 'roll', id: me }, b)));
      parts.push(row);
    } else if (mineCall) {
      const left = call.who.filter(w => !w.rolled).map(w => w.name).join(', ');
      parts.push(el('h2', '', 'Group stealth check'), el('p', '', `${mineCall.name} rolled ${mineCall.total}.`),
        el('p', 'note', left ? `Waiting for ${left}.` : 'Waiting for the GM’s Perception roll.'));
    }
    for (const s of sneaks) parts.push(el('p', '', `${s.name} moves stealthily (Stealth ${s.total}). The GM rolls Perception.`));
  } else {
    for (const s of sneaks) {
      const row = el('div', 'stealth-row');
      row.append(el('span', '', `${s.name} sneaks: Stealth ${s.total} (${s.rolls})`), btn('Roll Perception', b => send({ op: 'check', id: s.id }, b)));
      parts.push(row);
    }
    if (call) {
      parts.push(el('h2', '', 'Group stealth check'));
      for (const w of call.who) {
        const row = el('div', 'stealth-row');
        row.append(el('span', '', w.total != null ? `${w.name}: ${w.total}${w.by === 'gm' ? ' (you rolled)' : ''}` : `${w.name}: waiting`));
        if (w.total == null) row.append(btn('Roll for them', b => send({ op: 'roll', id: w.id }, b), 'quiet'));
        parts.push(row);
      }
      const all = call.who.every(w => w.total != null), row = el('p', 'reaction-buttons');
      const dc = el('input'); dc.type = 'number'; dc.min = '1'; dc.max = '40'; dc.placeholder = 'DC'; dc.setAttribute('aria-label', 'A written DC instead of Perception');
      const go = btn('Roll Perception', b => send({ op: 'resolve', ...(dc.value ? { dc: Number(dc.value) } : {}) }, b));
      go.disabled = !all;
      go.title = all ? 'The best roll among the creatures that might notice; at least half must beat it. With a DC, at least half must meet that instead' : 'Every character rolls first';
      row.append(dc, ' ', go, ' ', btn('Cancel', b => send({ op: 'cancel' }, b), 'quiet'));
      parts.push(row);
    }
  }
  box.replaceChildren(...parts);
}
// INITIATIVE-01 (GM 2026-10-28: "the gm will send all the players a popup for all their initiatives the same way as saving
// throws and all the rolls are checked by the rules engine"; Mythastria sim/initiative.py). When the GM starts a fight,
// each player's screen has an Initiative popup: Roll Initiative rolls it on the GM's Mythastria (d20 + Dexterity;
// Disadvantage when surprised). The GM's card: who has rolled, Roll for them (a slow player, a character nobody plays or
// the GM holds), Roll for everyone left. Round 1 starts when every character has rolled.
function drawInitiative(live = snap) {
  const call = live?.done ? null : live?.initiative, box = $('init-ask');
  const me = PLAYER ? myCharacter()?.id ?? null : null;
  const mine = PLAYER && !WATCHER && call?.mine ? call.who.find(w => w.id === me) : null;
  const held = !!(mine && (live.gm_control ?? {})[me]);
  const key = JSON.stringify([live?.fight_id, PLAYER, call, held]);
  box.hidden = !call;
  const left = call ? call.who.filter(w => !(w.rolled || w.total != null)).map(w => w.name) : [];
  if (call) status(left.length ? `The fight starts: Initiative. Waiting for ${left.join(', ')}.` : 'The fight starts: Initiative is in.');
  if (box.dataset.key === key) return;
  box.dataset.key = key;
  if (!call) { box.replaceChildren(); return; }
  const send = async (body, b) => {
    b.disabled = true;
    const out = await port.initiative(body).catch(() => ({ ok: false, error: 'The service stopped.' }));
    if (out?.live) take(out);
    else { result(out?.refused || out?.error || 'Not rolled.', 'refused'); box.dataset.key = ''; refresh(); }
  };
  const btn = (text, fn, cls = '') => { const b = el('button', cls, text); b.addEventListener('click', () => fn(b)); return b; };
  const parts = [el('h2', '', 'Initiative')];
  if (PLAYER) {
    if (mine && !mine.rolled && !held) {
      parts.push(el('p', '', `The fight starts! Roll Initiative for ${mine.name}: d20 + Dexterity.`));
      if (mine.surprised) parts.push(el('p', 'note', `${mine.name} is surprised: Disadvantage on this roll.`));
      const row = el('p', 'reaction-buttons');
      row.append(btn('Roll Initiative', b => send({ op: 'roll', id: me }, b)));
      parts.push(row);
    } else if (mine && held) {
      parts.push(el('p', '', `The GM is playing ${mine.name}: the GM rolls.`));
    } else if (mine) {
      parts.push(el('p', '', `${mine.name} rolled ${mine.total} (${mine.rolls}).`));
    } else {
      parts.push(el('p', '', 'The fight starts: the characters roll Initiative.'));
    }
    if (left.length) parts.push(el('p', 'note', `Waiting for ${left.join(', ')}.`));
  } else {
    parts.push(el('p', 'note', 'Each player rolls from a popup on their screen. Roll for a slow player, or a character nobody plays.'));
    for (const w of call.who) {
      const row = el('div', 'stealth-row');
      row.append(el('span', '', w.total != null ? `${w.name}: ${w.total} (${w.rolls})${w.by === 'gm' ? ' (you rolled)' : ''}`
        : `${w.name}${w.surprised ? ' (surprised)' : ''}: waiting`));
      if (w.total == null) row.append(btn('Roll for them', b => send({ op: 'roll', id: w.id }, b), 'quiet'));
      parts.push(row);
    }
    if (left.length) {
      const row = el('p', 'reaction-buttons');
      row.append(btn('Roll for everyone left', b => send({ op: 'rest' }, b)));
      parts.push(row);
    }
  }
  box.replaceChildren(...parts);
}
$('stealth-call').addEventListener('click', async () => {
  const out = await port.stealth({ op: 'call', who: 'all' }).catch(() => ({ ok: false, error: 'The service stopped.' }));
  if (out?.live) take(out); else result(out?.refused || out?.error || 'Not called.', 'refused');
});
function drawFrozen() {
  const frozen = !!snap?.frozen && !snap.done;
  $('sheet-turn').classList.toggle('frozen', frozen);
  $('frozen-banner').hidden = !frozen;
  $('sheet-turn').querySelectorAll('#end, #gm-take, #pv-hand').forEach(b => { b.disabled = false; });   // the turn bar's fixed buttons: no redraw turns them back on
  if (frozen) $('sheet-turn').querySelectorAll('button:not(#freeze)').forEach(b => { b.disabled = true; });
  $('freeze').hidden = PLAYER || !snap || snap.done;
  $('freeze').textContent = frozen ? 'Unfreeze' : 'Freeze';
}
// GM 2026-10-22 ("the phone display doesn't shows effects"): each cast's effect comes in the live state, so every screen
// (this console, the pop-out, each player's phone) draws it once, whoever cast it.
function showCastEffects() {
  const fresh = newCastEffects(snap, fxSeen);
  fresh.forEach(e => castEffects(e.effect).forEach(one => fx.push({ effect: spellVisual(one, rulesActor(e.caster), e.spell), until: Date.now() + 2800 })));
  if (fresh.length) setTimeout(() => drawMap(), 2900);
}

async function refresh() {
  const out = await port.state(logSince).catch(() => null);
  if (out) noteControls(out);
  if (out?.ok) { drawReaction(out.live); drawStealth(out.live); drawInitiative(out.live); }   // SPELL-BATCH-02, STEALTH-01, INITIATIVE-01: even while this console waits on a choice
  if (out?.ok && !PLAYER && out.hints_cap && out.hints_cap !== hintsCap) { hintsCap = out.hints_cap; if (snap) drawSheet(); }   // H3
  if (out?.ok && !PLAYER && (busy || drag || !(liveMoved(snap, out.live) || trackerMoved(snap?.tracker, out.live?.tracker)))) return;   // the GM console: only when the fight moved
  if (out?.ok) take(out);
  else if (out?.adventure_unloaded && scenario?.source_scenario?.startsWith('pack/' + out.adventure_unloaded + '/')) location.reload();
}

async function choose(choice) {
  const flavorSource = rulesActor(snap?.waiting);
  spellFocus = null;                                               // GM 2026-10-28: a choice ends the lit range
  if (busy || !snap?.waiting) return;
  if (choice.op === 'hide' && !stealthGo) { stealthAsk = choice; drawStealth(); return; }   // STEALTH-01: the popup rolls it
  stealthGo = false;
  if (WATCHER) { status('You are watching: the players make the choices.'); return; }   // GM 2026-10-25
  busy = true;
  const out = await port.act({ ...choice, fight_id: snap.fight_id, actor: snap.waiting, revision: snap.revision, since: logSince }).catch(() => ({ ok: false, error: 'The simulator service stopped.' }));
  busy = false;
  if (out.ok && choice.metamagic) armed = { metas: [], transmute: armed.transmute };   // spent with that spell
  if (out.ok && choice.op === 'attack') {                          // GM 2026-10-24: the roll on the sheet, a mark on the map
    lastRolls[choice.weapon] = rollLine(out);
    const t = view?.state.combatants.find(c => c.id === choice.target);
    if (t) { fx.push({ effect: spellVisual(effectFromCast({ shape: 'circle', origin: [t.x, t.y], radius_ft: out.result === 'crit' ? 5 : 3,
      appearance: out.result === 'miss' ? 'arcane' : out.result === 'crit' ? 'fire' : 'radiant' }), flavorSource, 'attack'), until: Date.now() + 1400 });
      setTimeout(() => drawMap(), 1500); }
  }
  if (out.live) take(out);
  if (out.ok) sync.changed();                                     // VIEW-02: the other window refreshes now
  if (out.ok) {
    const fxKey = `${snap.fight_id}:${out.effect_n}`;            // take() drew it from the live state; else draw it here
    if (out.effect && !fxSeen.has(fxKey)) { fxSeen.add(fxKey); castEffects(out.effect).forEach(one => fx.push({ effect: spellVisual(one, flavorSource, out.effect.spell ?? choice.spell), until: Date.now() + 2800 })); drawMapEffects(); setTimeout(() => drawMap(), 2900); }
    result(choice.op === 'cast' ? `${choice.spell}: ` + (out.lines ?? []).filter(x => !/^(ai-|AUTO_|PARSED_)/.test(x)).join('\n') :
      choice.op === 'attack' ? `${out.result === 'crit' ? 'Critical hit' : out.result === 'hit' ? 'Hit' : 'Miss'}. ` + (out.lines ?? []).slice(-2).join(' ') :
      choice.op === 'move' ? (out.dashed ? `Dashed (${out.dashed === 'bonus' ? 'Bonus Action' : 'Action'}), then moved` : out.crawled ? 'Crawled' : 'Moved') +
        ` ${out.moved_ft} ft.` + (out.stopped ? ` Stopped: ${out.stopped}` : '') :
      choice.op === 'undo' ? `Undo of the ${out.label} asked: waiting for the GM.` :
      choice.op === 'undo_approve' ? `The GM approved: ${snap.offers?.name ?? 'the character'} took back the ${out.label}. Choose again.` :
      choice.op === 'undo_refuse' ? `The GM refused the undo of the ${out.label}.` :
      ['dash', 'disengage', 'dodge', 'door', 'help', 'hide', 'search', 'ready', 'second_wind', 'action_surge', 'rage', 'lay_on_hands', 'grapple', 'shove', 'stand', 'drop_prone',
        'innate_sorcery', 'font_convert', 'font_create', 'use_item', 'study', 'influence', 'ask_gm', 'trap', 'mount', 'dismount', 'mount_action', 'mount_consent', 'shake', 'stabilize', 'spirit_strike', 'light',
        'martial_arts', 'flurry', 'patient_defense', 'step_of_the_wind', 'superior_defense', 'dragon_wings', 'fold_wings',
        'intimidating_presence', 'holy_nimbus', 'merge_shadows', 'blink_steps'].includes(choice.op) ? (out.lines ?? []).filter(x => !/^(ai-|AUTO_|PARSED_)/.test(x)).join('\n') : 'Turn ended.', 'done');
  } else {
    result(out.refused || out.error || 'Refused.', 'refused');
    if (out.status === 409) refresh();
  }
}

// ------------------------------------------------------------------ dragging an attack card onto a token
let drag = null;
function startDrag(e, a) {
  e.preventDefault();
  held = a.key;
  drag = { key: a.key, moved: false, x: e.clientX, y: e.clientY, pointer: e.pointerId };
  e.currentTarget.setPointerCapture?.(e.pointerId);
  $('ghost').textContent = a.name; $('ghost').hidden = true;
  drawMap(); drawSheet();
  result(`${a.name}: drop it on a highlighted token (green: foe, amber: ally). Hover a red one to see why it is refused.`);
}
addEventListener('pointermove', e => {
  if (!drag || e.pointerId !== drag.pointer) return;
  if (Math.hypot(e.clientX - drag.x, e.clientY - drag.y) > 6) drag.moved = true;
  const g = $('ghost');
  g.hidden = !drag.moved; g.style.left = e.clientX + 'px'; g.style.top = e.clientY + 'px';
  if (mode !== 'third') {                                         // HINTS-01 H5: the facts of the token under the drag
    pointedActor = document.elementFromPoint(e.clientX, e.clientY)?.closest?.('[data-actor]')?.dataset.actor ?? null;
    drawFact();
  }
});
addEventListener('pointerup', e => {
  if (!drag || e.pointerId !== drag.pointer) return;
  const d = drag; drag = null; $('ghost').hidden = true;
  if (!d.moved) return;                                          // a click: the card stays held; click a token next
  const under = document.elementFromPoint(e.clientX, e.clientY);
  if (mode === 'third' && under === $('tp-canvas')) { const id = thirdPerson?.pick(e.clientX, e.clientY); if (id) dropOn(id); return; }
  const hit = under?.closest?.('[data-actor]');
  if (hit) dropOn(hit.dataset.actor);
});

// 2026-10-21 (GM: Hero 4 "had 7 targets for firebolt but was unable to target any of them"): in the 3D view the party's
// tall figures stood in front of the goblins and took the click, so Fire Bolt went at an ally. While an attack or a spell
// is held, the 3D pick ranks legal foes first, then legal allies; an attack on an ally asks first (Help and the like don't).
const RANK = { 'legal-foe': 0, 'legal-ally': 1 };
function pickRank(c) {
  if (corpse(c)) return Infinity;                                  // GM 2026-10-24: a corpse never takes the click
  const cls = held ? lookFor(held, c).cls : casting?.shape === 'creatures' ? spellLook(casting, c, snap?.offers).cls : null;
  return cls ? RANK[cls] ?? 2 : 0;
}
// GM 2026-10-24 ("rules engine thinks healing word is an attack against an ally"): only an attack or a harmful spell
// asks before it goes at an ally; Healing Word, Cure Wounds, Bless, Shield of Faith and the like just go.
const HELPS = new Set(['Healing Word', 'Cure Wounds', 'Shield of Faith', 'Bless', 'Mass Healing Word', 'Hunter\'s Mark']);
const helpsAlly = key => {
  const s = key?.startsWith(SPELL_KEY) ? spellOf(snap?.offers, key) : null;
  return !!s && (s.appearance === 'healing' || s.kind === 'heal' || HELPS.has(s.name) || !!s.helps);   // helps: Haste
};
function dropOn(target) {
  const key = held;
  const who = view?.state.combatants.find(c => c.id === target);
  if (key && !key.startsWith(ACT_KEY) && !helpsAlly(key) && who && lookFor(key, who).cls === 'legal-ally'
      && !confirm(`${who.name} is on your side. Attack ${who.name}?`)) return;   // the card stays held: pick again
  held = null;
  if (PLAYER) sync.used();                                        // VIEW-02: the main console lets go of the card
  drawMap(); drawSheet();
  if (key?.startsWith(ACT_KEY)) {                                  // MONK-01: the Unarmed Strike line's Stunning Strike tick
    const unarmed = snap?.offers?.attacks?.find(x => x.key === 'unarmed');   // goes with Martial Arts and Flurry of Blows
    const stun = /^act:(flurry|martial_arts)(:|$)/.test(key) ? attackExtras(unarmed, attackPicks.unarmed).stun : undefined;
    choose({ ...actCommand(key, target), ...(stun ? { stun } : {}) });
  }
  else if (key?.startsWith(SPELL_KEY) && spellOf(snap?.offers, key)?.shape === 'creatures') addToCast(spellOf(snap.offers, key), target);
  else if (key?.startsWith(SPELL_KEY)) {
    if (!keepsGoing(key.slice(SPELL_KEY.length))) { result(''); return; }   // GM 2026-10-25: kept the Concentration
    const extra = castExtras(key.slice(SPELL_KEY.length));
    if (extra) choose({ op: 'cast', spell: key.slice(SPELL_KEY.length), target, ...extra, ...metamagicFields(armed) });
  }
  else if (key) {
    const a = snap?.offers?.attacks?.find(x => x.key === key);
    choose({ op: 'attack', weapon: key, target, ...(a?.metamagic ? metamagicFields(armed) : {}), ...attackExtras(a, attackPicks[key]) });
  }
}

// 2026-10-19 (GM: "the movement spline and area boundaries isn't showing"): the route to the square under the pointer,
// from the simulator's reach (the same search a move uses), with its cost in feet.
// the spell whose reach the map lights up: the one being cast or held, else the one chosen in the Spells dropdown (until
// it is cast, Esc, or another choice); its distance from the caster in feet, and what it is
let spellFocus = null;
function rangeShown() {
  const at = snap?.waiting && myPosition();
  if (!at) return null;
  const s = casting ?? spellOf(snap.offers, held) ?? (spellFocus && sheetTab === 'turn' ? (snap.offers?.spells ?? []).find(x => x.name === spellFocus) : null);
  if (!s) return null;
  const area = { cone: s.length_ft, line: s.length_ft, cube_self: s.size_ft }[s.shape] ?? (s.shape === 'self' ? s.radius_ft : null);
  const ft = area ?? (s.touch ? 5 : s.range_ft);
  if (!ft) return null;
  const what = area ? (s.shape === 'self' ? `${ft}-ft aura` : s.shape === 'cube_self' ? `${ft}-ft Cube beside you` : `${ft}-ft ${s.shape === 'cone' ? 'Cone' : 'Line'}`)
    : s.touch ? 'Touch' : `range ${ft} ft` + (s.radius_ft ? `, ${s.radius_ft}-ft-radius ${s.shape === 'spheres' ? 'Spheres' : 'Sphere'}` : s.size_ft ? `, ${s.size_ft}-ft Cube` : '');
  return { spell: s, at, ft, what };
}
function myPosition() {
  const me = view?.state.combatants.find(c => c.id === snap?.waiting);
  return me ? [Math.round(me.x), Math.round(me.y)] : null;
}
// GM 2026-10-24 ("Couldn't move farther"): a square past the movement left but within a Dash asks first, then the engine
// Dashes (the Action, or the Bonus Action with Cunning Action) and moves in one step.
function moveTo(x, y) {
  const o = snap?.offers, key = r => r[0] === x && r[1] === y;
  if (!(o?.reach ?? []).some(key) && (o?.dash_reach ?? []).some(key)) {
    const how = o.dash_by === 'bonus' ? 'your Bonus Action (Cunning Action)' : 'your Action';
    if (!confirm(`That square needs a Dash. Dash (using ${how}) and move there?`)) return;
    choose({ op: 'move', x, y, dash: true });
    return;
  }
  choose({ op: 'move', x, y });
}
function showRoute(sq) {
  $('map').querySelector('#route')?.remove();
  routeTo = null;
  if (!sq || held || !snap?.waiting) return;
  const r = reachPath({ reach: [...(snap.offers?.reach ?? []), ...(snap.offers?.dash_reach ?? [])] }, sq[0], sq[1], myPosition());
  if (!r) return;
  routeTo = r;
  const g = svg('g', { id: 'route', 'pointer-events': 'none' });
  g.append(svg('polyline', { points: r.path.map(([x, y]) => `${x + .5},${y + .5}`).join(' '), fill: 'none', stroke: '#e0c060', 'stroke-width': .09,
    'stroke-linejoin': 'round', 'stroke-linecap': 'round', 'stroke-dasharray': '.18 .1' }));
  const [ex, ey] = r.path[r.path.length - 1];
  g.append(svg('circle', { cx: ex + .5, cy: ey + .5, r: .16, fill: '#e0c060' }));
  g.append(svg('text', { x: ex + .5, y: ey + .08, 'text-anchor': 'middle', 'font-size': .32, fill: '#f1e6cc', stroke: '#151614', 'stroke-width': .05, 'paint-order': 'stroke' }, `${r.feet} ft`));
  $('map').append(g);
}
$('map').addEventListener('pointermove', e => {
  pointedActor = e.target.closest?.('[data-actor]')?.dataset.actor ?? null;   // HINTS-01 H5: the attack's facts on a token
  if (casting && casting.shape !== 'creatures') { aimAt = squareAt(e.clientX, e.clientY); drawMapEffects(); drawFact(); return; }
  if (!walk) showRoute(squareAt(e.clientX, e.clientY));
  drawFact();
});
$('map').addEventListener('pointerleave', () => { pointedActor = null; if (!walk) showRoute(null); drawFact(); });

// 2026-10-19 (GM: "can't move characters"): drag your own token to a square (as in other table tools); a click on the
// square still works. The simulator checks the route; a ghost square follows the pointer while dragging.
let walk = null, suppressClick = false;
function squareAt(clientX, clientY) {
  const map = $('map'), m = map.getScreenCTM();
  if (!m) return null;
  const p = new DOMPoint(clientX, clientY).matrixTransform(m.inverse());
  return [Math.floor(p.x), Math.floor(p.y)];
}
$('map').addEventListener('pointerdown', e => {
  if (e.button !== 0 || held || casting || noteMode || squarePick || trapMode || !snap?.waiting) return;   // aiming a spell: your own token is a pick, not a move
  const token = e.target.closest('[data-actor]');
  if (!token || token.dataset.actor !== snap.waiting) return;
  e.preventDefault();
  $('map').setPointerCapture?.(e.pointerId);
  walk = { pointer: e.pointerId, x: e.clientX, y: e.clientY, moved: false, ghost: null };
});
$('map').addEventListener('pointermove', e => {
  if (!walk || e.pointerId !== walk.pointer) return;
  if (Math.hypot(e.clientX - walk.x, e.clientY - walk.y) > 6) walk.moved = true;
  if (!walk.moved) return;
  const sq = squareAt(e.clientX, e.clientY);
  if (!sq) return;
  if (!walk.ghost) { walk.ghost = svg('rect', { width: 1, height: 1, fill: '#e0c060', 'fill-opacity': .18, stroke: '#e0c060', 'stroke-width': .06, 'pointer-events': 'none' }); $('map').append(walk.ghost); }
  walk.ghost.setAttribute('x', sq[0]); walk.ghost.setAttribute('y', sq[1]);
  showRoute(sq); $('map').append(walk.ghost);
});
function endWalk(e, cancel) {
  if (!walk || e.pointerId !== walk.pointer) return;
  const w = walk; walk = null;
  w.ghost?.remove(); showRoute(null);
  if (cancel || !w.moved) return;
  suppressClick = true; setTimeout(() => { suppressClick = false; }, 0);
  const sq = squareAt(e.clientX, e.clientY);
  if (sq) moveTo(sq[0], sq[1]);
}
$('map').addEventListener('pointerup', e => endWalk(e, false));
$('map').addEventListener('pointercancel', e => endWalk(e, true));

$('map').addEventListener('click', e => {
  if (drag || suppressClick) return;
  if (noteMode && !PLAYER) {                                       // VIEW-01: a note on the square clicked
    const sq = squareAt(e.clientX, e.clientY);
    if (sq) openNote(sq[0], sq[1]);
    return;
  }
  if (trapMode && !PLAYER) { const sq = squareAt(e.clientX, e.clientY); if (sq) placeTrap(sq); return; }   // GM 2026-10-24
  if (hazardMode && !PLAYER) { const sq = squareAt(e.clientX, e.clientY); if (sq) pickHazardSquare(sq); return; }   // HAZARDS-01
  if (squarePick) { const sq = squareAt(e.clientX, e.clientY), b = squarePick; squarePick = null; drawMap();
    if (sq) choose(squareCommand(b.square, sq[0], sq[1])); return; }
  const aimHit = e.target.closest?.('[data-door-aim]');
  if (aimHit && held) { castAtDoor(aimHit.dataset.doorAim); return; }   // SPELL-OBJECTS-01
  const objHit = e.target.closest?.('[data-object-aim]');
  if (objHit && held) { castAtDoor(objHit.dataset.objectAim, 'props'); return; }   // step 6: a prop
  const doorHit = e.target.closest?.('[data-door]');
  if (doorHit && !casting && !held) { choose({ op: 'door', door: doorHit.dataset.door }); return; }   // slice 3
  if (casting) {                                                  // slice 2: picking creatures or placing an area
    const token = e.target.closest('[data-actor]');
    if (casting.shape === 'creatures') {
      if (!token) return;
      pickForCast(token.dataset.actor); return;
    }
    const sq = squareAt(e.clientX, e.clientY);
    if (sq && (casting.shape === 'spheres' || casting.shape === 'cubes')) {   // SPELLS-4-9: Meteor Swarm's points; Fire Storm's Cubes
      const i = casting.points.findIndex(q => q[0] === sq[0] && q[1] === sq[1]);
      casting.points = i >= 0 ? casting.points.filter((_, k) => k !== i) : casting.points.length < casting.points_max ? [...casting.points, sq] : casting.points;
      drawMap(); drawSheet(); return;
    }
    if (sq) cast({ spell: casting.name, x: sq[0], y: sq[1] });
    return;
  }
  const token = e.target.closest('[data-actor]');
  if (held && token) { dropOn(token.dataset.actor); return; }
  if (held) { held = null; drawMap(); drawSheet(); result(''); return; }
  const sq = e.target.closest('[data-square]');
  if (sq && snap?.waiting) { const [x, y] = sq.dataset.square.split(',').map(Number); moveTo(x, y); }
});
addEventListener('keydown', e => { if (e.key === 'Escape' && !flavor.dialog.open && (held || casting)) cancelCast(); });
addEventListener('keydown', e => { if (e.key === 'Escape' && spellFocus && !held && !casting) { spellFocus = null; drawMap(); } });   // the lit range
addEventListener('keydown', e => { if (e.key === 'Escape' && (squarePick || trapFirst)) { squarePick = null; trapFirst = null; result(''); drawMap(); } });

// ------------------------------------------------------------------ GM 2026-10-24: traps (SRD 5.2.1; sim/traps.py)
function pickTrapSquare(b) {
  squarePick = squarePick?.label === b.label ? null : b; held = null; casting = null; drawMap();
  result(squarePick ? `${b.label}: click the square. Esc cancels.` : '');
}
function linkButton(b) {
  const go = el('button', 'quiet act', `\u2192 ${b.link.label}`);
  go.title = b.why; go.addEventListener('click', () => openLink(b.link));
  return go;
}
const TRAP_GLYPH = [['pit', '\u25bc'], ['wire', '\u2307'], ['statue', '\u265c'], ['stone', '\u25cf'], ['oil', '\u25cd'], ['rubble', '\u2591'], ['gear', '\u2731'], ['lock', '\u26bf']];
function drawTraps(root) {
  const g = svg('g', { class: 'traps', 'pointer-events': 'none' });
  for (const m of trapMarks(PLAYER ? (snap?.traps ?? []).filter(t => t.known) : snap?.traps)) {   // the players' screen: known ones only
    const n = m.size ?? 1, mk = svg('g', { class: m.cls });
    mk.append(svg('rect', { x: m.x + .08, y: m.y + .08, width: n - .16, height: n - .16, rx: m.cls.includes('stone') ? n / 2 : .08 }));
    const glyph = (TRAP_GLYPH.find(([k]) => m.cls.split(' ').includes(k)) ?? [null, '\u25a3'])[1];
    mk.append(svg('text', { x: m.x + n / 2, y: m.y + n / 2 + .1, 'text-anchor': 'middle', 'font-size': .28 }, glyph));
    mk.append(svg('title', {}, m.title));
    g.append(mk);
  }
  root.classList.toggle('picking', !!(squarePick && snap?.waiting) || trapMode);
  root.append(g);
}
async function loadTrapCatalog() {
  const lv = Math.min(20, Math.max(1, Number($('level')?.value) || 1));
  if (trapCatalog?.level === lv) return trapCatalog;
  const out = await port.traps({ op: 'catalog', level: lv }).catch(() => null);
  if (out?.ok) trapCatalog = out;
  return trapCatalog;
}
async function openTrapTool() {
  trapMode = !trapMode; trapFirst = null;
  $('trap-mode').setAttribute('aria-pressed', String(trapMode));
  $('trap-panel').hidden = !trapMode;
  drawMap();
  if (!trapMode) { status(''); return; }
  const cat = await loadTrapCatalog(), kind = $('trap-kind');
  if (cat && !kind.options.length) for (const [k, t] of Object.entries(cat.every)) kind.append(new Option(t.name, k));
  drawTrapBands(); drawTrapList();
  status('Traps: choose one and its levels, then click a square a creature can enter. The players see it only once they find it or it goes off.');
}
function drawTrapBands() {
  const t = trapCatalog?.every?.[$('trap-kind').value], band = $('trap-band'), keep = band.value;
  band.replaceChildren(...(t?.bands ?? []).map(b => new Option(`Levels ${b}`, b)));
  if ([...band.options].some(o => o.value === keep)) band.value = keep;
  else if (trapCatalog && [...band.options].some(o => o.value === trapCatalog.band)) band.value = trapCatalog.band;
  const card = trapCatalog?.traps?.find(c => c.kind === $('trap-kind').value);
  $('trap-card').textContent = card ? `${card.severity}. ${card.trigger}. ${card.effect[0].toUpperCase() + card.effect.slice(1)}. Detect: ${card.detect.join('; ')}. Make safe: ${card.disarm.join(', ')}.` +
    ($('trap-kind').value === 'fire_statue' ? ' Two clicks: the plate, then the statue.' : $('trap-kind').value === 'rolling_stone' ? ' Two clicks: the plate, then where the stone waits.' : '') : '';
}
function drawTrapList() {
  if ($('trap-panel').hidden) return;
  $('trap-list').replaceChildren(...(snap?.traps ?? []).filter(t => !t.gear).map(t => {
    const row = el('div', 'trap-row'), x = el('button', 'quiet', 'Remove');
    x.addEventListener('click', async () => { const out = await port.traps({ op: 'remove', trap: t.id }).catch(() => null);
      if (out?.live) { take(out); drawTrapList(); } else status(out?.refused || out?.error || 'Not removed.', true); });
    row.append(el('span', '', `${t.name} (${t.severity}, levels ${t.band}) at ${t.squares.map(q => '(' + q.join(', ') + ')').join(' ')}: ${t.disarmed ? 'made safe' : t.open ? 'open pit' : t.armed ? (t.found.length ? 'found by the party' : 'hidden') : 'gone off'}${t.foe_found?.length ? '; the creatures found it' : ''}`), x);
    return [row, trapKnowers(t)];
  }).flat());
}
// GM 2026-10-26 (goal 15, sim/creature_traps.py): which creatures know the trap (their lair's: they step round it or wait
// behind it). The players never see this.
function trapKnowers(t) {
  const row = el('div', 'trap-row hz-who'), kb = new Set(t.known_by ?? []);
  row.append(el('span', 'note', 'Who knows it:'));
  const foes = (snap?.state?.combatants ?? []).filter(c => !c.pc && c.side !== 'friend');
  for (const [value, label] of [['foes', 'The whole lair'], ...foes.map(c => [c.id, c.name])]) {
    const l = el('label', 'check'), b = el('input'); b.type = 'checkbox'; b.value = value;
    b.checked = kb.has(value) || kb.has(foes.find(c => c.id === value)?.name);
    b.addEventListener('change', async () => {
      const out = await port.traps({ op: 'know', trap: t.id, who: [value], on: b.checked }).catch(() => null);
      if (out?.live) { take(out); drawTrapList(); status(`${t.name}: ${label} ${b.checked ? 'knows' : 'no longer knows'} it.`); }
      else { b.checked = !b.checked; status(out?.refused || out?.error || 'Not changed.', true); }
    });
    l.append(b, ' ' + label); row.append(l);
  }
  return row;
}
async function placeTrap(sq) {
  const kind = $('trap-kind').value, band = $('trap-band').value;
  const two = kind === 'fire_statue' || kind === 'rolling_stone';
  if (two && !trapFirst) { trapFirst = sq; status(kind === 'fire_statue' ? 'Now click the statue (it faces the plate).' : 'Now click where the stone waits (it rolls toward the plate).'); return; }
  const spec = { op: 'place', kind, band, squares: [trapFirst ?? sq] };
  const [px, py] = spec.squares[0];
  if (kind === 'fire_statue') Object.assign(spec, { statue: sq, toward: [px, py] });
  if (kind === 'rolling_stone') Object.assign(spec, { stone: { at: sq, dir: [Math.sign(px - sq[0]), Math.sign(py - sq[1])] } });
  if (kind === 'poisoned_darts' || kind === 'collapsing_roof') {   // the darts' path, the ceiling: the 3 by 3 squares round it
    spec.area = [];
    for (let dx = -1; dx <= 1; dx++) for (let dy = -1; dy <= 1; dy++) spec.area.push([px + dx, py + dy]);
  }
  if (kind === 'poisoned_needle') {                                 // the lock of the door beside the square, if there is one
    const d = (view?.map.walls ?? []).find(w => w.door && w.points.some(([x, y]) => Math.abs(x - px) <= 1 && Math.abs(y - py) <= 1));
    if (d) spec.door = String(d.id);
  }
  trapFirst = null;
  let out = await port.traps(spec).catch(() => null);
  if (!out?.ok && spec.area) { delete spec.area; out = await port.traps(spec).catch(() => null); }   // a wall beside it: the square alone
  if (out?.live) { take(out); status(`${$('trap-kind').selectedOptions[0].text} placed (hidden from the players).`); drawTrapList(); }
  else status(out?.refused || out?.error || 'Not placed.', true);
}
$('trap-mode').addEventListener('click', openTrapTool);

// ------------------------------------------------------------------ MAP-PAINT-01: the GM paints on the map
function paintBar() {
  $('paint-undo').disabled = !mapPaint.canUndo;
  $('paint-shown').checked = mapPaint.shown;
  $('paint-note').textContent = mapPaint.map ? (mapPaint.shown ? 'The players see it.' : 'Only you see it.') : 'Start a fight to paint its map.';
}
function setPaint() {
  const size = Number($('paint-size').value);
  $('paint-size-out').textContent = size + ' sq';
  mapPaint.set({ tool: $('paint-tool').value, colour: $('paint-colour').value, size, opacity: Number($('paint-opacity').value) });
}
$('paint-mode').addEventListener('click', () => {
  mapPaint.on = !mapPaint.on;
  $('paint-mode').setAttribute('aria-pressed', String(mapPaint.on));
  $('paint-panel').hidden = !mapPaint.on; $('map').classList.toggle('painting', mapPaint.on);
  if (!mapPaint.on) mapPaint.flush();
  setPaint(); paintBar();
  status(mapPaint.on ? 'Paint: drag on the map to paint or erase. Press Paint again to go back to play.' : '');
});
for (const id of ['paint-tool', 'paint-colour', 'paint-size', 'paint-opacity']) $(id).addEventListener('input', setPaint);
$('paint-undo').addEventListener('click', () => { mapPaint.undo(); paintBar(); });
$('paint-clear').addEventListener('click', () => { if (confirm('Erase all the paint on this map?')) { mapPaint.clear(); paintBar(); } });
$('paint-shown').addEventListener('change', async () => { await mapPaint.show($('paint-shown').checked); paintBar(); });
$('trap-kind').addEventListener('change', drawTrapBands);

// ------------------------------------------------------------------ HAZARDS-01 (GM 2026-10-26): hazards (sim/hazards.py)
// The GM picks squares and places slippery ice, thin ice or frigid water; turns the weather on (strong wind, a sandstorm,
// heavy rain or snow); frightens or stresses the creatures ticked; exposes a character to a contagion or makes a creature
// a carrier. The simulator rolls every save on the fight's own turn order; the players see the ice and the water.
const HZ_NAME = { slippery_ice: 'Slippery ice', thin_ice: 'Thin ice', frigid_water: 'Frigid water' };
function drawHazards(root) {
  const g = svg('g', { class: 'hazards', 'pointer-events': 'none' });
  for (const z of snap?.hazards?.zones ?? []) for (const [x, y] of z.squares) {
    const mk = svg('g', { class: 'hz ' + z.kind }); mk.append(svg('rect', { x, y, width: 1, height: 1 }), svg('title', {}, z.name)); g.append(mk);
  }
  if (hazardMode && !PLAYER) for (const [x, y] of hzPicks) { const mk = svg('g', { class: 'hz pending' }); mk.append(svg('rect', { x: x + .06, y: y + .06, width: .88, height: .88 })); g.append(mk); }
  if (hazardMode) root.classList.add('picking');
  root.append(g);
}
function pickHazardSquare(sq) {
  const k = sq.join(); hzPicks = hzPicks.some(p => p.join() === k) ? hzPicks.filter(p => p.join() !== k) : [...hzPicks, sq];
  $('hz-place').disabled = !hzPicks.length; $('hz-place').textContent = hzPicks.length ? `Place on ${hzPicks.length} square${hzPicks.length === 1 ? '' : 's'}` : 'Place';
  drawMap();
}
async function hazardCall(request, done) {
  const out = await port.hazards(request).catch(() => null);
  if (out?.live) take(out);
  if (out?.ok) { if (done) status(done); } else status(out?.refused || out?.error || 'Refused.', true);
  drawHazardPanel();
  return out;
}
function hzTargets() { return [...document.querySelectorAll('#hz-targets input:checked')].map(b => b.value); }
function drawHazardPanel() {
  if ($('hazard-panel').hidden) return;
  const on = new Set(snap?.hazards?.weather ?? []);
  $('hz-weather').replaceChildren(...[['strong_wind', 'Strong wind'], ['sandstorm', 'Sandstorm'], ['heavy_precipitation', 'Heavy rain or snow']].map(([k, label]) => {
    const l = el('label', 'check'), b = el('input'); b.type = 'checkbox'; b.checked = on.has(k); l.title = hzCatalog?.weather?.[k]?.text ?? '';
    b.addEventListener('change', () => hazardCall({ op: 'weather', weather: [...document.querySelectorAll('#hz-weather input')].map((x, i) => x.checked ? ['strong_wind', 'sandstorm', 'heavy_precipitation'][i] : null).filter(Boolean) },
      b.checked ? `${label}: ${hzCatalog?.weather?.[k]?.text ?? ''}` : `${label} ends.`));
    l.append(b, ' ' + label); return l;
  }));
  $('hz-card').textContent = hzCatalog?.zones?.[$('hz-kind').value]?.text ?? '';
  $('hz-list').replaceChildren(...(snap?.hazards?.zones ?? []).map(z => {
    const row = el('div', 'trap-row'), x = el('button', 'quiet', 'Remove');
    x.addEventListener('click', () => hazardCall({ op: 'remove', zone: z.id }, `${z.name} removed.`));
    row.append(el('span', '', `${z.name}: ${z.squares.length} square${z.squares.length === 1 ? '' : 's'}${z.holds ? ' (holds ' + Object.values(z.holds).map(v => v + ' lb').join(', ') + ')' : ''}`), x);
    return row;
  }));
  const people = (view?.state?.combatants ?? []).filter(c => !c.down), keep = new Set(hzTargets());
  $('hz-targets').replaceChildren(...people.map(c => { const l = el('label', 'check'), b = el('input'); b.type = 'checkbox'; b.value = c.id; b.checked = keep.has(c.id);
    l.append(b, ' ' + c.name); return l; }));
  const src = $('hz-fear-source'), was = src.value;
  src.replaceChildren(...people.map(c => new Option(c.name, c.id)));
  if (was && people.some(c => c.id === was)) src.value = was;
}
async function openHazardTool() {
  hazardMode = !hazardMode; hzPicks = [];
  if (hazardMode && trapMode) openTrapTool();                        // one square tool at a time
  $('hazard-mode').setAttribute('aria-pressed', String(hazardMode));
  $('hazard-panel').hidden = !hazardMode;
  drawMap();
  if (!hazardMode) { status(''); return; }
  if (!hzCatalog) { const out = await port.hazards({ op: 'catalog' }).catch(() => null); if (out?.ok) hzCatalog = out; }
  drawHazardPanel();
  status('Hazards: click squares on the map, choose the hazard and Place; weather over the whole map; fear, stress and contagions for the creatures ticked.');
}
$('hazard-mode').addEventListener('click', openHazardTool);
$('hz-kind').addEventListener('change', drawHazardPanel);
$('hz-clear').addEventListener('click', () => { hzPicks = []; pickHazardSquare([-99, -99]); hzPicks = []; $('hz-place').disabled = true; $('hz-place').textContent = 'Place'; drawMap(); });
$('hz-place').addEventListener('click', async () => {
  const kind = $('hz-kind').value, n = hzPicks.length;
  const out = await hazardCall({ op: 'place', kind, squares: hzPicks }, `${HZ_NAME[kind]} on ${n} square${n === 1 ? '' : 's'}.`);
  if (out?.ok) { hzPicks = []; $('hz-place').disabled = true; $('hz-place').textContent = 'Place'; drawMap(); }
});
$('hz-fear').addEventListener('click', () => hazardCall({ op: 'fear', targets: hzTargets(), dc: Number($('hz-fear-dc').value), source: $('hz-fear-source').value,
  why: $('hz-why').value.trim() || 'a fear effect' }, 'Fear: the saves are in the log.'));
$('hz-stress').addEventListener('click', () => hazardCall({ op: 'stress', targets: hzTargets(), save: $('hz-st-save').value, dc: Number($('hz-st-dc').value),
  dice: $('hz-st-dice').value.trim(), half: $('hz-st-half').checked, effect: $('hz-st-effect').value, condition: $('hz-st-cond').value,
  ability: $('hz-st-ability').value, why: $('hz-why').value.trim() || 'mental stress' }, 'Mental stress: the saves are in the log.'));
for (const [id, mode] of [['hz-expose', 'expose'], ['hz-infect', 'infect']]) $(id).addEventListener('click', async () => {
  for (const t of hzTargets()) await hazardCall({ op: 'contagion', target: t, key: $('hz-cont').value, mode }, `${$('hz-cont').selectedOptions[0].text}: see the log.`);
});
$('hz-carrier').addEventListener('click', async () => {
  for (const t of hzTargets()) await hazardCall({ op: 'carrier', creature: t, key: $('hz-cont').value, on: true }, `${$('hz-cont').selectedOptions[0].text}: carried.`);
});
// ------------------------------------------------------------------ 3D action bar, targets, pointer label
// 2026-10-20 (GM: Play live "difficult to use in 3d": the actions too far away, targeting tokens, moving the character):
// in Third person the turn's choices sit on the view itself (number keys 1-0), a held attack or spell lists its legal
// targets as buttons, and the pointer says what a click will do. Logic in tp-bar.mjs; the simulator checks every choice.
let hoverSquare = null, tipAt = null;                             // pointedActor: with the other state, at the top
function togglePick(id) {
  if (!(casting?.shape === 'creatures' && casting.targets?.includes(id))) return;
  casting.picks = casting.picks.includes(id) ? casting.picks.filter(x => x !== id) : casting.picks.length < casting.max_targets ? [...casting.picks, id] : casting.picks;
  drawSheet();
}
function pickLook() {
  if (held) return c => lookFor(held, c);
  if (casting?.shape === 'creatures') return c => casting.picks.includes(c.id) ? { cls: 'legal-foe', reason: '' } : spellLook(casting, c, snap?.offers);
  return null;
}
function useBarItem(it) {
  if (!it?.ready) { if (it?.why) result(it.why, 'refused'); return; }
  if (it.kind === 'end') { choose({ op: 'end' }); return; }
  if (it.kind === 'cast') { startCast(it.spell); return; }
  if (it.kind === 'act') {
    const b = it.button;
    if (!b.pick) { choose(b.cmd); return; }
    held = held === b.pick ? null : b.pick; casting = null; drawMap(); drawSheet();
    result(held ? `${b.label}: pick a target below, or click a creature. Esc cancels.` : '');
    return;
  }
  held = held === it.key ? null : it.key; casting = null; aimAt = null; drawMap(); drawSheet();
  result(held ? `${it.label}: pick a target below, or click a creature. Esc cancels.` : '');
}
function drawBar() {
  const bar = $('tp-bar');
  const offers = snap?.waiting ? snap.offers : null;
  bar.hidden = PLAYER || mode !== 'third' || !offers;            // VIEW-02: the commands stay on the main console
  if (bar.hidden) { $('tp-tip').hidden = true; return; }
  const items = barItems(offers, [...actionButtons(offers), ...doorButtons(offers)], { held, casting });
  const row = el('div', 'tp-row');
  for (const it of items) {
    const b = el('button', 'tp-btn' + (it.kind === 'end' ? ' tp-end' : '') + (it.on ? ' held' : '') + (it.ready ? '' : ' not-ready'));
    if (it.hotkey) b.append(el('kbd', '', it.hotkey));
    const style = it.spellLike ? flavorFor('spell', it.spell.name) : it.key && !it.key.startsWith(SPELL_KEY) && !it.key.startsWith(ACT_KEY) ? flavorFor('attack', it.key) : {};
    b.append(document.createTextNode(flavorLabel(style, it.label)));
    b.title = it.why || it.title;
    if (it.spellLike) b.style.borderColor = (palettes[style.appearance || it.spell.appearance] ?? palettes.arcane)[0];
    b.addEventListener('click', () => useBarItem(it));
    row.append(b);
  }
  const u = offers.undo, undo = el('button', 'tp-btn' + (u?.ready ? '' : ' not-ready'), u?.ready ? `Undo ${u.label}` : u?.asked ? 'Undo asked: waiting for the GM' : 'Undo');
  undo.disabled = !u?.ready; undo.title = u?.ready ? `Ask the GM to take back the ${u.label} (${keymap.undo.map(label).join(' / ') || 'no key'})` : u?.why ?? '';
  undo.addEventListener('click', () => undoLast());
  row.append(undo);
  const rows = [row], look = pickLook();
  if (look) {
    const seen = snap?.party_sight ? playerCombatants(view?.state.combatants ?? [], snap.party_sight) : view?.state.combatants;   // never count an unseen creature
    const me = myPosition(), list = targetList(seen, look, me), tr = el('div', 'tp-row tp-targets');
    tr.append(el('span', 'tp-label', casting ? `${casting.name}: pick up to ${casting.max_targets}` : 'Target:'));
    for (const t of list.legal) {
      const b = el('button', 'tp-btn tp-target' + (t.ally ? ' ally' : '') + (casting?.picks.includes(t.id) ? ' held' : ''), `${t.name}${t.feet != null ? ` · ${t.feet} ft` : ''}`);
      b.addEventListener('click', () => { if (held) dropOn(t.id); else togglePick(t.id); });
      tr.append(b);
    }
    if (!list.legal.length) tr.append(el('span', 'tp-label', 'No legal target now.'));
    if (list.refused) tr.append(el('span', 'tp-label', `${list.refused} refused: point at one to see why`));
    if (casting?.shape === 'creatures') {
      const go = el('button', 'tp-btn tp-end', `Cast${casting.picks.length ? ` on ${casting.picks.length}` : ''}`);
      go.disabled = !casting.picks.length;
      go.addEventListener('click', () => cast({ spell: casting.name, targets: casting.picks }));
      tr.append(go);
    }
    const cancel = el('button', 'tp-btn', 'Cancel');
    cancel.addEventListener('click', cancelCast);
    tr.append(cancel);
    rows.unshift(tr);
  }
  bar.replaceChildren(...rows);
  drawTip();
}
function drawTip() {
  drawFact();                                                      // HINTS-01: the facts in 3D too
  const tip = $('tp-tip');
  const c = pointedActor ? view?.state.combatants.find(a => a.id === pointedActor) : null;
  const info = c ? creatureTip(c, pickLook()) : hoverSquare?.tip ?? null;
  if (mode !== 'third' || !info || !tipAt) { tip.hidden = true; return; }
  const r = $('tp-wrap').getBoundingClientRect();
  tip.hidden = false; tip.className = 'tp-tip ' + info.cls; tip.textContent = info.text + flavorTip(c);
  tip.style.left = Math.min(tipAt[0] - r.left + 14, r.width - 240) + 'px'; tip.style.top = (tipAt[1] - r.top + 16) + 'px';
}
$('tp-canvas').addEventListener('pointermove', e => { tipAt = [e.clientX, e.clientY]; });
addEventListener('keydown', e => {
  if (mode !== 'third' || typing(e) || e.ctrlKey || e.altKey || e.metaKey || $('keys-dialog').open || actionFor(keymap, comboOf(e))) return;
  const i = BAR_KEYS.indexOf(e.key);
  if (i < 0 || $('tp-bar').hidden) return;
  const offers = snap.offers, it = barItems(offers, [...actionButtons(offers), ...doorButtons(offers)], { held, casting })[i];
  if (it) { e.preventDefault(); useBarItem(it); }
});
$('cast-go').addEventListener('click', () => {
  if ((casting?.shape === 'spheres' || casting?.shape === 'cubes') && casting.points.length) cast({ spell: casting.name, points: casting.points });
  else if (casting?.picks.length) cast({ spell: casting.name, targets: casting.picks });
});
$('end').addEventListener('click', () => choose({ op: 'end' }));
$('gm-take').addEventListener('click', async () => {
  const who = snap?.waiting, held = (snap?.gm_control ?? {})[who];
  const out = await port.control(who, !held).catch(() => ({ ok: false, error: 'The service stopped.' }));
  if (!out.ok) return result(out.refused || out.error, 'refused');
  refresh();
});
$('pv-hand').addEventListener('click', async () => {
  const me = myCharacter(), held = me && (snap?.gm_control ?? {})[me.id];
  const out = await port.control(me?.id, !held).catch(() => ({ ok: false, error: 'The service stopped.' }));
  if (!out.ok) return result(out.refused || out.error, 'refused');
  refresh();
});
$('freeze').addEventListener('click', async () => {
  const out = await port.freeze(!snap?.frozen).catch(() => ({ ok: false, error: 'The service stopped.' }));
  if (!out.ok) return result(out.refused || out.error, 'refused');
  refresh();
});
// OA-AUTO-01 (GM 2026-10-28: "Auto mode for monsters and foes is available for fast live games"): on, the engine answers
// every player Reaction itself; off, each player is asked (the fight waits). Kept by the service for the next fights.
$('reaction-auto').addEventListener('change', async e => {
  const want = e.target.checked;
  const out = await port.reactionMode(want).catch(() => ({ ok: false, error: 'The service stopped.' }));
  if (!out.ok) { e.target.checked = !want; return result(out.refused || out.error, 'refused'); }
  result(want ? 'Auto Reactions on: the engine answers every player Reaction.' : 'Auto Reactions off: each player is asked.');
  if (out.live) take(out); else refresh();
});
// GM 2026-11-01 ("allow the GM to disable them"): the Influence buttons on or off, kept by the service for the next fights
$('social-on').addEventListener('change', async e => {
  const want = e.target.checked;
  const out = await port.socialMode(want).catch(() => ({ ok: false, error: 'The service stopped.' }));
  if (!out.ok) { e.target.checked = !want; return result(out.refused || out.error, 'refused'); }
  result(want ? 'Influence buttons on: each takes the Action and comes to you to rule.' : 'Influence buttons off.');
  if (out.live) take(out); else refresh();
});
// GM 2026-11-01 ("a Panic Button that stops everything"): the rules engine holds at its next step; Resume goes on from there
$('panic').addEventListener('click', async () => {
  const out = await port.panic(!stopped).catch(() => ({ ok: false, error: 'The service stopped.' }));
  if (!out.ok) return result(out.refused || out.error, 'refused');
  noteControls(out);
  result(out.panic ? 'Everything is stopped.' : 'Resumed.');
  refresh();
  sync.changed();
});
// GM-UNDO-01 (GM 2026-11-01: "an unlimited undo that tells the rules engine to go in reverse, one step at a time")
$('gm-undo').addEventListener('click', async () => {
  if (busy) return;
  if (snap?.done && !confirm('The fight is over. Taking it back also takes back what the adventure day and the bags did since it began, a rest included. Go back?')) return;
  busy = true; $('gm-undo').disabled = true;
  status('Taking the fight back…');
  const out = await port.undo().catch(() => ({ ok: false, error: 'The service stopped.' }));
  busy = false; $('gm-undo').disabled = false;
  if (!out.ok) return result(out.refused || out.error, 'refused');
  take(out);
  result(out.stopped ? `Taken back as far as it would go: ${out.stopped}` : `Taken back: ${out.undone}. The fight waits: press Go on when you're ready.`, out.stopped ? 'refused' : undefined);
  sync.changed();
});
$('gm-goon').addEventListener('click', async () => {
  const out = await port.freeze(false).catch(() => ({ ok: false, error: 'The service stopped.' }));
  if (!out.ok) return result(out.refused || out.error, 'refused');
  refresh();
});
// GM 2026-11-01 ("a small timer on the combat tracker for each turn, which the GM can disable and enable at will")
$('timer-on').addEventListener('change', async e => {
  const want = e.target.checked;
  const out = await port.timerMode(want).catch(() => ({ ok: false, error: 'The service stopped.' }));
  if (!out.ok) { e.target.checked = !want; return result(out.refused || out.error, 'refused'); }
  result(want ? 'Turn timer on.' : 'Turn timer off.');
  refresh();
});
// BY-THE-SRD-01 (GM 2026-11-02: "Yes, add the switch"): this table's rulings or the SRD as written, kept for the next fights
$('srd-on').addEventListener('change', async e => {
  const want = e.target.checked;
  const out = await port.srdMode(want).catch(() => ({ ok: false, error: 'The service stopped.' }));
  if (!out.ok) { e.target.checked = !want; return result(out.refused || out.error, 'refused'); }
  result(want ? 'By the SRD: Hide is a DC 15 check; Spirit Guardians follows the caster\'s alignment.' : 'By the SRD off: this table\'s rulings apply.');
  refresh();
});
$('undo').addEventListener('click', () => undoLast());
$('pv-undo').addEventListener('click', () => undoLast());
$('undo-approve').addEventListener('click', () => { if (!PLAYER) choose({ op: 'undo_approve' }); });
$('undo-refuse').addEventListener('click', () => { if (!PLAYER) choose({ op: 'undo_refuse' }); });

// 2026-10-21 (GM: "Training doesn't have a way to populate the combat table"): Remix's Add a creature can start the new
// creatures at a square the GM clicks on the board, when the board shows that map. Esc or a click off the map cancels.
function pickSquare(name) {
  if (scenario?.source_scenario !== name) { status('To pick a square, start a fight on this map first: the board shows the map being played.', true); return Promise.resolve(null); }
  status('Click a square on the map for the new creatures (Esc to cancel).');
  document.body.classList.add('remix-picking');
  return new Promise(done => {
    const finish = sq => { removeEventListener('pointerdown', down, true); removeEventListener('keydown', key, true); document.body.classList.remove('remix-picking'); status(sq ? `Square ${sq[0]}, ${sq[1]} picked.` : 'No square picked.'); done(sq); };
    const down = e => { e.preventDefault(); e.stopPropagation(); finish(e.target.closest?.('#map') ? squareAt(e.clientX, e.clientY) : null); };
    const key = e => { if (e.key === 'Escape') { e.preventDefault(); finish(null); } };
    addEventListener('pointerdown', down, true); addEventListener('keydown', key, true);
  });
}

// GM 2026-10-28 ("I only want to use characters saved in the saved characters tab"): no test characters; the party is the ticked
// saved characters
const partyMembers = () => [];
// GM 2026-10-25 ("DM should be able to restore party to full health and rest at the start of a map"): on an adventure's
// map, the party's day (sim/rests.py) gets a Long Rest's benefits now, before Start live fight
const mapPack = () => (/^pack\/([^/]+)\//.exec($('scenario').value) ?? [])[1] ?? null;
function drawRestore() { $('restore-party').hidden = PLAYER || !mapPack(); }
async function restoreParty() {
  const pack = mapPack(), members = partyMembers(), chars = partyRoster().filter(c => chosenChars.has(c.id));
  if (!pack) return;
  if (!members.length && !chars.length) { status('Choose the party first: tick your Saved characters.', true); return; }
  const out = await port.day({ pack, op: 'restore', members, level: Number($('level').value) || 1,
    ...(chars.length ? { characters: chars.map(fightSheet) } : {}) }).catch(() => ({ ok: false, error: 'The simulator service stopped.' }));
  status(out.ok ? 'The party is restored: full health, slots and uses (a Long Rest, no time passes). Start live fight when ready.'
    : (out.refused || out.error || 'Refused.'), !out.ok);
}
// GM 2026-10-22: Clear empties the set-up choices (not a fight in progress)
function clearSetup() {
  chosenChars.clear(); drawPartyChars();
  $('level').value = '1'; $('seed').value = '1';
  if (!$('scenario').disabled) { $('scenario').value = ''; mapPicker?.refresh(); drawRestore(); }   // the Adventure's chosen encounter stays
  status('Cleared. Choose a map and a party, then Start live fight.');
}

async function start(remix = null) {                              // REMIX-01: a remix for this fight only
  const members = partyMembers();
  const chars = partyRoster().filter(c => chosenChars.has(c.id));   // CHARACTERS-01 (GM 2026-10-25: or the table's sheets)
  if (!$('scenario').value) { status('Choose a map first.', true); return; }
  if (!members.length && !chars.length) { status('Choose the party: tick your Saved characters.', true); return; }
  status('The simulator is setting up the fight…');
  $('start').disabled = true; $('log').replaceChildren(); logSince = 0; fightStarted = false; result('');
  const out = await port.start({ scenario: $('scenario').value, members, level: Number($('level').value) || 1,
    seed: Number($('seed').value) || 1, campaign: $('remix-campaign').value.trim(), remix_enabled: $('remix-enabled').checked,
    scene: $('scene-start').value,                                 // GM 2026-10-26: a social or exploration scene, or a fight
    ...(chars.length ? { characters: chars.map(fightSheet) } : {}),
    ...(remix ? { remix } : {}), ...($('map-light')?.value ? { ambient: $('map-light').value } : {}) })   // LIGHTS-01
    .catch(() => ({ ok: false, error: 'The simulator service stopped.' }));
  $('start').disabled = false;
  if (!out.ok) { status('Refused: ' + out.error, true); return; }
  (out.scenario?.characters ?? []).forEach((name, i) => { if (chars[i]) photos = linkSheet(photos, name, chars[i].id); });
  if (chars.length) savePhotos(photos);
  take(out);
  sync.changed();
}

addEventListener('DOMContentLoaded', async () => {
  await loadRegistry();
  let hello = null;
  try { hello = await port.hello(); } catch { hello = null; }
  if (!hello?.ok) { status('Play live needs the simulator service: start Start_Mythastria.bat, then open http://127.0.0.1:8772/play.html', true); $('start').disabled = true; return; }
  flavor.sync(); setInterval(() => flavor.sync(), 4000);         // FLAVOR-01: Mythastria's Flavor (the GM's edits)
  const remixParams = new URLSearchParams(location.search);
  $('remix-campaign').value = remixParams.get('campaign') || 'default';
  $('remix-enabled').checked = remixParams.get('remix') !== '0';
  if (['fight', 'social', 'exploration'].includes(remixParams.get('scene'))) $('scene-start').value = remixParams.get('scene');   // GM 2026-10-26
  $('setup-clear').addEventListener('click', clearSetup);
  const rawAsked = new URLSearchParams(location.search).get('scenario');
  const asked = hello.scenario_aliases?.[rawAsked] || rawAsked;   // REGION-01: a place on the region map opens its tactical map
  const pick = hello.scenarios.includes(asked) ? asked : 'test/live_keep.json';
  for (const n of hello.scenarios) $('scenario').append(new Option(n, n, n === pick, n === pick));
  // GM 2026-10-25 ("The remix must only allow the chosen encounter in the Adventure loaded"): a map chosen on Play an
  // adventure stays the map: Start live fight and the Remix panel use only it (open Play live without a map to choose).
  if (rawAsked && !PLAYER && hello.scenarios.includes(asked)) {
    $('scenario').disabled = true;
    $('scenario').title = 'Chosen on Play an adventure (Fight here): this fight and its Remix use only this encounter.';
  }
  if (!PLAYER) mapPicker = (await import('./map-picker.mjs')).mountMapPicker($('scenario'), hello.scenario_tree);   // GM 2026-10-25: Folder > Subfolder > map
  for (const n of hello.creatures ?? []) $('imp-creature').append(new Option(n, n, n === 'Goblin Warrior', n === 'Goblin Warrior'));   // VIEW-01
  $('start').addEventListener('click', () => start());
  $('restore-party').addEventListener('click', restoreParty);         // GM 2026-10-25
  $('scenario').addEventListener('change', drawRestore); drawRestore();
  if (!PLAYER) tableParty = await loadTableParty((route, body) => port.party(body));   // GM 2026-10-25: the table's sheets
  drawPartyChars();                                               // CHARACTERS-01: saved characters in the party
  addEventListener('storage', e => { if (e.key === 'isles-character-roster-v1') drawPartyChars(); });
  if (!PLAYER) {                                                  // PLAYER-PACKAGE-01: the GM console only
    const [{ mountRemix: mountRemixPanel }, { mountDirector }] = await Promise.all([import('./remix-panel.mjs'), import('./director-ui.mjs')]);
    mountRemixPanel({ button: $('remix-open'), port, start, status, pickSquare,   // the quick panel; the Remix page is remix.html
      running: () => !!snap && !snap.done,                         // ON-THE-FLY-01: changes without starting again
      creatures: () => snap?.state?.combatants ?? [],
      current: name => scenario?.source_scenario === name ? scenario.remix?.quick ?? null : null,   // reopen with the fight's remix
      // GM 2026-10-28 ("I imported a character but cannot include it in a play live remix fight"): the ticked saved
      // characters count too, each at its own level
      settings: () => ({ scenario: $('scenario').value, members: partyMembers(), level: Number($('level').value) || 1,
        party_levels: partyRoster().filter(c => chosenChars.has(c.id)).map(c => Math.min(20, Math.max(1, (c.classes ?? []).reduce((n, k) => n + (k.level || 0), 0) || 1))) }) });
    mountDirector({ button: $('director-open'), line: $('director-line'), status });   // GUEST-DIRECTOR-01
  }
  drawKeys();
  let saved = 'tactical';
  try { saved = localStorage.getItem('isles-play-view') || 'tactical'; } catch { /* default */ }
  setMode(saved);
  if (PLAYER) {                                                   // VIEW-01: the players' window
    document.body.classList.add('player-view'); document.title = 'Mythastria — Map';   // VIEW-02: tactical or 3D, as chosen there
    if (SEATED) { document.body.classList.add('seated'); document.title = 'Mythastria — My character'; }   // GM 2026-10-25: the sheet too
    if (WATCHER) { document.body.classList.add('seated', 'watching'); document.title = 'Mythastria — Watching'; }
  }
  if (OLD_DM && !hello.handed) { location.href = '/play.html'; return; }   // DM-SWAP-01: no swap (any more): the GM console
  handedChar = hello.handed?.character ?? '';
  if (OLD_DM && !handedChar) { WATCHER = true; document.body.classList.add('watching'); }   // handed over, playing no character
  // GM 2026-10-28 ("I don't want the request on the client-only version"): no Ask to be the GM on the player client;
  // the module loads only on the GM's console and on the owning GM's handed-over screen (the GM's own door)
  if (!PLAYER || OLD_DM) (await import('./dm-swap-ui.mjs')).mountDmSwap({ port, hello, player: PLAYER, seated: SEATED || WATCHER, oldDm: OLD_DM, status, anchor: $('status') });
  if (remixParams.get('start') === '1' && !PLAYER) {             // CHARACTERS-01: "Test in Play live" starts at once
    history.replaceState(null, '', location.pathname + location.search.replace(/([?&])start=1(&|$)/, '$1').replace(/[?&]$/, ''));
    await start();
    return;
  }
  const out = await port.state(0).catch(() => null);
  // GM 2026-10-25 ("The live fight must match the fight chosen in the Adventure"): a link naming a map (the Adventure's
  // Fight here, a place on the region map) plays that map. No fight running: it starts now. The same map running: that
  // fight goes on. Another map running: the GM is asked before it ends; kept, the page says which fight it shows.
  const mapName = n => String(n ?? '').replace(/^pack\/[^/]+\//, '').replace(/\.json$/, '').replace(/_/g, ' ');
  const running = out?.ok && out.live && !out.live.done ? out.scenario?.source_scenario ?? null : null;
  if (rawAsked && !PLAYER && !hello.scenarios.includes(asked)) {
    status(`The chosen map (${mapName(rawAsked)}) is not available: load its adventure on Play an adventure, then press Fight here again.`, true);
    drawMap();
    return;
  }
  if (rawAsked && !PLAYER && running !== asked) {
    if (!running || confirm(`A fight on ${mapName(running)} is still running. End it and start the chosen fight on ${mapName(asked)}?`)) {
      await start();
      return;
    }
    take(out);
    status(`Still showing the running fight on ${mapName(running)}. Press Start live fight to play ${mapName(asked)}.`);
    return;
  }
  if (out?.ok) { take(out); } else { status(PLAYER ? 'Waiting for the GM to start a fight.' : 'Choose a map and a party, then Start live fight.'); drawMap(); }   // the board says so too
});
