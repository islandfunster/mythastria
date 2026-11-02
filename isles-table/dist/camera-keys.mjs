// LIVE-PLAY-01 3D (GM 2026-10-19: the third-person camera "will use the mouse buttons and roll button with key map
// options"). The keyboard map for the camera and turn: defaults, the player's own bindings (kept in this browser), and
// rebinding without two actions sharing a key. Keys are written as "q", "arrowleft", "shift+enter".

export const ACTIONS = {
  rotate_left: 'Turn camera left', rotate_right: 'Turn camera right', tilt_up: 'Tilt camera up', tilt_down: 'Tilt camera down',
  zoom_in: 'Zoom in', zoom_out: 'Zoom out', recenter: 'Camera behind my character', toggle_view: 'Tactical / third person',
  end_turn: 'End turn', undo: 'Undo my last choice',   // LIVE-UNDO-01 (GM 2026-10-21)
};

export const DEFAULT_KEYS = {
  rotate_left: ['q', 'arrowleft'], rotate_right: ['e', 'arrowright'], tilt_up: ['r', 'arrowup'], tilt_down: ['f', 'arrowdown'],
  zoom_in: ['=', '+'], zoom_out: ['-'], recenter: ['c'], toggle_view: ['v'], end_turn: ['shift+enter'], undo: ['ctrl+z'],
};

const STORE = 'isles-camera-keys';
const MODIFIERS = new Set(['shift', 'control', 'alt', 'meta']);

// A key event as a binding: null for a bare modifier (still being held for a combination).
export function comboOf(e) {
  const key = String(e.key || '').toLowerCase();
  if (!key || MODIFIERS.has(key)) return null;
  const name = key === ' ' ? 'space' : key;
  const shiftMatters = name.length > 1 || /[a-z0-9]/.test(name);     // "+" is already a shifted key
  return [e.ctrlKey && 'ctrl', e.altKey && 'alt', e.shiftKey && shiftMatters && 'shift', name].filter(Boolean).join('+');
}

export function actionFor(keymap, combo) {
  for (const [action, keys] of Object.entries(keymap)) if (keys.includes(combo)) return action;
  return null;
}

// Give `action` the key `combo` (added to its keys, at most two); any other action using it loses it.
export function rebind(keymap, action, combo) {
  if (!(action in ACTIONS) || !combo) return { keymap, displaced: null };
  const next = Object.fromEntries(Object.entries(keymap).map(([a, ks]) => [a, ks.filter(k => k !== combo)]));
  const displaced = Object.keys(keymap).find(a => a !== action && keymap[a].includes(combo)) ?? null;
  next[action] = [combo, ...next[action].filter(k => k !== combo)].slice(0, 2);
  return { keymap: next, displaced };
}

export function clearKeys(keymap, action) {
  return { ...keymap, [action]: [] };
}

export function loadKeymap(storage = globalThis.localStorage) {
  const base = structuredClone(DEFAULT_KEYS);
  try {
    const saved = JSON.parse(storage?.getItem(STORE) || 'null');
    if (saved && typeof saved === 'object') {
      for (const a of Object.keys(ACTIONS)) {
        if (Array.isArray(saved[a])) base[a] = saved[a].filter(k => typeof k === 'string' && k.length <= 24).slice(0, 2);
      }
    }
  } catch { /* unreadable or blocked: the defaults */ }
  return base;
}

export function saveKeymap(keymap, storage = globalThis.localStorage) {
  try { storage?.setItem(STORE, JSON.stringify(keymap)); return true; } catch { return false; }
}

export const label = combo => combo.split('+').map(p => ({ arrowleft: '←', arrowright: '→', arrowup: '↑', arrowdown: '↓',
  enter: 'Enter', space: 'Space', shift: 'Shift', ctrl: 'Ctrl', alt: 'Alt', escape: 'Esc' })[p] ?? p.toUpperCase()).join(' + ');
