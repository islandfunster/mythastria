// VIEW-01 (GM 2026-10-20: "character sheets will need to be attached to player tokens. Character sheet needs photo(s)
// which will appear on the token."): photos for the saved character sheets (the Characters workshop's roster), and which
// sheet each Play live party member is. Photos are pictures the GM picks, scaled down and kept in this browser only
// (never sent to the simulator service, never in a Remix test copy: DECISIONS, game numbers only). Display only.

export const PHOTO_KEY = 'mythastria-photos-v1', MAX_PHOTOS = 4, PHOTO_PX = 256;

export function emptyPhotos() { return { sheets: {}, links: {} }; }

const copy = s => ({ sheets: { ...s.sheets }, links: { ...s.links } });

export function addPhoto(state, sheetId, url) {
  if (!sheetId || typeof url !== 'string' || !url.startsWith('data:image/') && !url.startsWith('data:')) return state;
  const s = copy(state), cur = s.sheets[sheetId] ?? { photos: [], active: 0 };
  if (cur.photos.length >= MAX_PHOTOS) return state;
  s.sheets[sheetId] = { ...cur, photos: [...cur.photos, url] };
  return s;
}

export function removePhoto(state, sheetId, index) {
  const cur = state.sheets[sheetId];
  if (!cur || index < 0 || index >= cur.photos.length) return state;
  const s = copy(state), photos = cur.photos.filter((_, i) => i !== index);
  const active = index === cur.active ? 0 : index < cur.active ? cur.active - 1 : cur.active;
  if (photos.length) s.sheets[sheetId] = { photos, active: Math.min(active, photos.length - 1) };
  else delete s.sheets[sheetId];
  return s;
}

export function setActive(state, sheetId, index) {
  const cur = state.sheets[sheetId];
  if (!cur || index < 0 || index >= cur.photos.length) return state;
  const s = copy(state);
  s.sheets[sheetId] = { ...cur, active: index };
  return s;
}

export function photoOf(state, sheetId) {
  const cur = sheetId && state.sheets[sheetId];
  return cur?.photos.length ? cur.photos[cur.active] ?? cur.photos[0] : null;
}

// A party member's sheet: the GM's choice (null = deliberately none), else a saved sheet whose first name matches.
export function linkSheet(state, member, sheetId) {
  const s = copy(state);
  s.links[member] = sheetId ?? null;
  return s;
}

export function sheetFor(state, roster, member) {
  const ids = new Set((roster ?? []).map(c => c.id));
  if (member in state.links) return state.links[member] && ids.has(state.links[member]) ? state.links[member] : null;
  const first = n => String(n ?? '').trim().split(/\s+/)[0].toLowerCase();
  return (roster ?? []).find(c => first(c.name) === first(member))?.id ?? null;
}

export function tokenPhoto(state, roster, member) { return photoOf(state, sheetFor(state, roster, member)); }

// The view with each party member's chosen photo as its token (2D: token_path; 3D: a token entry with that path).
export function decorate(view, state, roster) {
  const tokens = new Map();
  if (!view) return { view, tokens };
  const combatants = view.state.combatants.map(c => {
    if (!c.pc) return c;
    const sheet = sheetFor(state, roster, c.name), url = photoOf(state, sheet);
    if (!url) return c;
    const id = `photo:${sheet}:${state.sheets[sheet].active}`;
    tokens.set(id, { id, path: url, squares: 1 });
    return { ...c, token_id: id, token_path: url };
  });
  return { view: { ...view, state: { ...view.state, combatants } }, tokens };
}

export function loadPhotos(storage = globalThis.localStorage) {
  try {
    const s = JSON.parse(storage?.getItem(PHOTO_KEY) || 'null');
    return s && typeof s.sheets === 'object' && typeof s.links === 'object' ? s : emptyPhotos();
  } catch { return emptyPhotos(); }
}

export function savePhotos(state, storage = globalThis.localStorage) {
  try { storage?.setItem(PHOTO_KEY, JSON.stringify(state)); return true; } catch { return false; }
}

// A picture file scaled down to a token-sized square-fitting image (browser only).
export async function photoFromFile(file, px = PHOTO_PX) {
  const bitmap = await createImageBitmap(file);
  const k = Math.min(1, px / Math.max(bitmap.width, bitmap.height));
  const canvas = document.createElement('canvas');
  canvas.width = Math.max(1, Math.round(bitmap.width * k)); canvas.height = Math.max(1, Math.round(bitmap.height * k));
  canvas.getContext('2d').drawImage(bitmap, 0, 0, canvas.width, canvas.height);
  return canvas.toDataURL('image/webp', .85);
}

export function rosterFrom(storage = globalThis.localStorage) {
  try { const r = JSON.parse(storage?.getItem('isles-character-roster-v1') || '[]'); return Array.isArray(r) ? r : []; } catch { return []; }
}
