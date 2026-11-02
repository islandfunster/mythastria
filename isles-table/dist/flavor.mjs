// Flavor is free (GM 2026-10-20, the AI assistant's Flavor package; installed 2026-10-21 with the GM's "descriptions of pets,
// familiars, mounts or for the dm to change the artwork for a creature as well as non-statblock related description in a
// flavor footnote"): this module owns presentation overrides, never engine state or commands. A creature keeps its rules
// name, statistics and footprint; Flavor changes only the name shown, the picture, a role (pet, familiar, mount) and a
// footnote. The Python simulator stays the rules authority: nothing here is sent to it.
import { palettes } from './effects.mjs';
export const FLAVOR_KEY = 'mythastria-flavor-v1', MAX_FLAVORS = 2000, EVERY_MAP = '*';
export const ROLES = { pet: 'Pet', familiar: 'Familiar', mount: 'Mount', companion: 'Companion' };
// GM 2026-10-23 (after the 3D minis pilot: "Keep the flat standees. Include them to be edited in flavor"): how a
// creature's standee stands in the 3D view: on a round base (base) and as tall as its picture (true_height; without it
// the standee is drawn 40% taller, as before). Yes/no settings, like share. GM 2026-10-23 ("It would have to be in the
// narrative of an adventure for it to have a rider ... flavor is used to add a rider to the camel horse or any other
// creature that can be mounted"): rider, a picture from the catalog shown on the creature's back. A look only: the
// creature fights with its own stat block (DECISIONS: MOUNTS ARE DOMESTIC ANIMALS).
const fields = { actor: ['name', 'description', 'token_id', 'role', 'share', 'base', 'true_height', 'rider', 'mask', 'paint', 'paint_on', 'paint_until'], attack: ['name', 'description'], spell: ['name', 'description', 'appearance'] };
const YES_NO = ['share', 'base', 'true_height'];
const text = (v, max) => typeof v === 'string' ? v.trim().slice(0, max) : '';
// GM 2026-10-21: "maybe we should add a simple paint to put a temporary mask on a copy of a creature". The paint is a
// small picture made in this browser (flavor-paint.mjs): the strokes alone (mask, to paint on later) and the creature's
// picture with the strokes on it (paint, shown on the token). The token files themselves never change.
export const MAX_PAINT = 400000;
const PICTURE = /^data:image\/(png|webp);base64,[A-Za-z0-9+/]+=*$/;
const picture = v => typeof v === 'string' && v.length <= MAX_PAINT && PICTURE.test(v) ? v : '';
// A short mark of the picture painted over (a sheet photo is too big to keep twice): paint on another picture is not shown.
export function pictureMark(path = '') {
  let h = 0x811c9dc5;
  for (let i = 0; i < path.length; i++) h = Math.imul(h ^ path.charCodeAt(i), 0x01000193) >>> 0;
  return 'p' + h.toString(16) + '-' + path.length;
}
export const emptyFlavor = () => ({ version: 1, entries: {} });
export function flavorKey(scope, actor, kind, key = '') {
  if (![scope, actor].every(v => typeof v === 'string' && v.length && v.length <= 256) || !Object.hasOwn(fields, kind) || typeof key !== 'string' || key.length > 256) throw Error('Choose a map, character and Flavor subject.');
  return JSON.stringify([scope, actor, kind, key]);
}
function clean(kind, value, strict = false) {
  if (!value || typeof value !== 'object' || Array.isArray(value)) throw Error('Invalid Flavor.');
  if (strict && Object.keys(value).some(k => !fields[kind].includes(k))) throw Error('Flavor can change presentation only.');
  const out = {};
  for (const f of fields[kind]) {
    if (YES_NO.includes(f)) { if (value[f] === true) out[f] = true; continue; }   // share: the players' window may show the footnote
    if (f === 'mask' || f === 'paint') {
      const v = picture(value[f]);
      if (!v && value[f] && strict) throw Error('The paint is not a picture this table can keep (PNG or WebP, under 400 KB).');
      if (v) out[f] = v;
      continue;
    }
    const v = text(value[f], f === 'description' ? 1000 : f === 'token_id' || f === 'rider' ? 160 : 80);
    if (!v) continue;
    if (f === 'appearance' && !Object.hasOwn(palettes, v)) { if (strict) throw Error('Choose an existing visual effect.'); continue; }
    if (f === 'role' && !Object.hasOwn(ROLES, v)) { if (strict) throw Error('Choose a listed role.'); continue; }
    out[f] = v;
  }
  if (!out.paint) { delete out.mask; delete out.paint_on; delete out.paint_until; }   // no paint, no paint details
  if (Object.keys(out).length === 1 && out.share) return {};             // "players may read" alone is no Flavor
  return out;
}
export function setFlavor(state, scope, actor, kind, key, value) {
  const id = flavorKey(scope, actor, kind, key), record = clean(kind, value, true), entries = { ...state.entries };
  if (Object.keys(record).length) {
    if (!Object.hasOwn(entries, id) && Object.keys(entries).length >= MAX_FLAVORS) throw Error('This browser’s Flavor collection is full. Restore a subject before adding another.');
    entries[id] = record;
  } else delete entries[id];
  return { version: 1, entries };
}
// Where a subject's Flavor is kept: this map, every map (a pet, familiar or mount travels with the party), or nowhere.
// This map's own Flavor comes first.
export function flavorWhere(state, scope, actor, kind, key = '') {
  for (const s of [scope, EVERY_MAP]) {
    try { if (s && Object.hasOwn(state.entries, flavorKey(s, actor, kind, key))) return s; } catch { /* no map yet */ }
  }
  return null;
}
export function flavorOf(state, scope, actor, kind, key = '') {
  const where = flavorWhere(state, scope, actor, kind, key);
  try { return where ? clean(kind, state.entries[flavorKey(where, actor, kind, key)]) : {}; } catch { return {}; }
}
export function loadFlavor(storage = globalThis.localStorage) {
  try {
    const data = JSON.parse(storage?.getItem(FLAVOR_KEY) || 'null'), out = emptyFlavor();
    if (data?.version !== 1 || !data.entries || typeof data.entries !== 'object' || Array.isArray(data.entries)) return out;
    for (const [id, record] of Object.entries(data.entries).slice(0, MAX_FLAVORS)) {
      try { const [scope, actor, kind, key] = JSON.parse(id); if (flavorKey(scope, actor, kind, key) !== id) continue; const r = clean(kind, record); if (Object.keys(r).length) out.entries[id] = r; } catch { /* ignore corrupt entries */ }
    }
    return out;
  } catch { return emptyFlavor(); }
}
export function saveFlavor(state, storage = globalThis.localStorage) {
  try { if (!storage) return false; storage.setItem(FLAVOR_KEY, JSON.stringify(state)); return true; } catch { return false; }
}
export function flavorLabel(record, canonical) { return record.name && record.name !== canonical ? `${record.name} · ${canonical}` : canonical; }
// A creature by its rules name: the simulator numbers creatures afresh in every fight (id-00021 ...), while a map's
// "Goblin Warrior 1" or a party member's name stays the same, so Flavor is still there after a new fight or a restart.
export const actorFlavorKey = actor => actor?.rules_name ?? actor?.name;
// The footnote under a creature's sheet and on its token: its role and description, never statistics.
export function flavorFootnote(record) {
  return [record.role ? ROLES[record.role] + '.' : '', record.description ?? ''].filter(Boolean).join(' ');
}
// A view copy of one creature with its Flavor. The players' window shows the name and picture (they are on the map),
// and the footnote only when the GM let the players read it.
// How long a paint lasts (GM 2026-10-21: "Really I wanted it for adventure, not fight."): in an adventure, until the
// adventure ends (the Adventure page's End, or its Start again: endAdventurePaint); in a fight outside an adventure, that
// fight; '' when the GM keeps it.
export const paintUntil = ({ adventure = null, fightId = null } = {}) => adventure ? 'adventure:' + adventure : 'fight:' + (fightId ?? '');
export const paintLasts = (record, now) => !record.paint_until || record.paint_until === paintUntil(now);
// The paint shows while the picture under it is the one painted over, and while it lasts (paintUntil).
export function flavorActor(actor, state, scope, registry = [], { player = false, fightId = null, adventure = null } = {}) {
  const record = flavorOf(state, scope, actorFlavorKey(actor), 'actor'), art = registry.find(t => t.id === record.token_id),
    rider = record.rider && (actor.space_ft ?? 5) >= 10 ? registry.find(t => t.id === record.rider) : null;   // Large or bigger carries a rider
  const foot = !player || record.share ? flavorFootnote(record) : '', base = art ? art.path : actor.token_path;
  const painted = record.paint && record.paint_on === pictureMark(base ?? '') && paintLasts(record, { adventure, fightId });
  return { ...actor, rules_name: actor.rules_name ?? actor.name, name: record.name || actor.name, flavor_description: foot,
    ...(record.base ? { standee_base: true } : {}), ...(record.true_height ? { standee_true_height: true } : {}),
    ...(rider ? { rider_id: rider.id, rider_path: rider.path } : {}),
    ...(art ? { token_id: art.id, token_path: art.path } : {}),
    ...(painted ? { token_id: 'paint:' + JSON.stringify([scope, actorFlavorKey(actor)]), token_path: record.paint } : {}) };
}
// PLAYER-FLAVOR-01: what a player's own screen shows while the GM decides: the look asked for, over the approved one. A
// refused look drops out of `pending`, and the approved one is back.
export function overlayPending(state, pending = {}) {
  const entries = { ...state.entries };
  for (const [actor, value] of Object.entries(pending)) {
    for (const id of Object.keys(entries)) { const [, who, kind] = JSON.parse(id); if (who === actor && kind === 'actor') delete entries[id]; }
    const record = clean('actor', value);
    if (Object.keys(record).length) entries[flavorKey(EVERY_MAP, actor, 'actor')] = record;
  }
  return { version: 1, entries };
}
export function flavorEffect(effect, state, scope, actor, spell) {
  if (!effect) return effect;
  const record = flavorOf(state, scope, actorFlavorKey(actor), 'spell', spell);
  // No spreading user records onto an effect: geometry, targets and duration remain authoritative.
  return { ...effect, ...(record.appearance ? { appearance: record.appearance } : {}) };
}
// An adventure ended or started again: its paint comes off every creature (the rest of their Flavor stays).
export function endAdventurePaint(state, adventure) {
  const entries = {};
  for (const [id, r] of Object.entries(state.entries)) {
    if (r.paint_until !== 'adventure:' + adventure) { entries[id] = r; continue; }
    const { mask, paint, paint_on, paint_until, ...rest } = r;
    if (Object.keys(rest).length && !(Object.keys(rest).length === 1 && rest.share)) entries[id] = rest;
  }
  return { version: 1, entries };
}
export function dropAdventurePaint(adventure, storage = globalThis.localStorage) {
  const state = loadFlavor(storage), next = endAdventurePaint(state, adventure);
  return JSON.stringify(next) === JSON.stringify(state) || saveFlavor(next, storage);
}
// GM 2026-10-21: "allow flavor to be erased and redone": every Flavor kept for one map (names, footnotes, pictures,
// paint, attacks and spells); every-map Flavor stays (it is erased creature by creature).
export function eraseMap(state, scope) {
  return { version: 1, entries: Object.fromEntries(Object.entries(state.entries).filter(([id]) => { try { return JSON.parse(id)[0] !== scope; } catch { return true; } })) };
}
