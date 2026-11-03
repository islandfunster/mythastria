// GUEST-DIRECTOR-01 (GM 2026-10-21: "Yes, that's a good plan"; names from DECISIONS 2026-10-20): on this one PC the
// showrunner hands the GM console to a guest director (or a special guest director) with only the GM controls the
// showrunner ticks, and takes it back at any time (with the take-back code, if one was set). The simulator service
// enforces it (tools/director.py); this page locks the controls the showrunner kept and says who is directing.

// The GM controls on Play live, by what the showrunner can hand over (Remix Prep is its own page, refused by the service).
export const LOCKS = {
  fights: ['start', 'remix-open', 'scenario', 'seed', 'remix-campaign', 'remix-enabled', 'setup-clear', 'restore-party', 'scene-start', 'panic', 'gm-goon',
    'freeze', 'gm-take', 'trap-mode', 'hazard-mode', 'monitor-open', 'map-light', 'reaction-auto', 'social-on', 'srd-on', 'timer-on', 'stealth-call'],
  undo: ['undo-approve', 'undo-refuse', 'gm-undo'],
  reveal: ['fog-reveal', 'fog-reset'],
  notes: ['note-mode'],
  maps: ['import-open', 'paint-mode'],
  players: ['seats-open'],
  market: ['market-open'],
  flavor: ['flavor-open'],
};

// The element ids to lock for a director state: nothing for the showrunner, the kept controls for a guest.
export function kept(state) {
  if (!state?.directing) return [];
  return Object.entries(LOCKS).filter(([grant]) => !state.grants.includes(grant)).flatMap(([, ids]) => ids);
}

export function directorLine(state) {
  return state?.directing ? `Directing: ${state.directing} · ${state.title.toLowerCase()}. The showrunner can take the console back.` : '';
}

export function mountDirector({ document: doc = globalThis.document, button, line, status = () => {}, fetch: fetchFn = globalThis.fetch }) {
  const make = (tag, text, cls) => { const e = doc.createElement(tag); if (text !== undefined) e.textContent = text; if (cls) e.className = cls; return e; };
  const dialog = make('dialog'); dialog.id = 'director-dialog'; dialog.setAttribute('aria-labelledby', 'director-title');
  doc.body.append(dialog);
  let token = null, state = null, locked = [];

  async function post(body, retry = true) {
    if (!token) token = (await (await fetchFn('/api/hello')).json()).token;
    const res = await fetchFn('/api/director', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ ...body, token }) });
    const out = await res.json().catch(() => ({ ok: false, error: 'The service sent no answer.' }));
    if (res.status === 403 && retry && /token/i.test(out.error || '')) { token = null; return post(body, false); }
    return res.ok ? out : { ...out, ok: false };
  }
  function apply(next) {
    state = next;
    for (const id of locked) { const e = doc.getElementById(id); if (e) { e.inert = false; e.classList.remove('kept'); } }
    locked = kept(state);
    for (const id of locked) { const e = doc.getElementById(id); if (e) { e.inert = true; e.classList.add('kept'); } }
    line.textContent = directorLine(state);
    line.hidden = !state?.directing;
    button.textContent = state?.directing ? `Director: ${state.directing}…` : 'Director…';
  }
  function draw() {
    const title = make('h2', 'Director'); title.id = 'director-title';
    const err = make('p', '', 'director-error'); err.setAttribute('role', 'alert'); err.hidden = true;
    const fail = text => { err.textContent = text; err.hidden = false; };
    const parts = [title];
    if (!state.directing) {
      parts.push(make('p', 'The showrunner is directing. Hand the GM console to a guest for a session or a fight, with only the controls you tick.', 'note'));
      const name = make('input'); name.maxLength = 40; name.placeholder = "Guest director's name"; name.setAttribute('aria-label', "Guest director's name");
      const special = make('input'); special.type = 'checkbox';
      const sp = make('label'); sp.append(special, ' Special guest director (a Mythastria veteran or a GM of renown)');
      const box = make('fieldset', undefined, 'director-grants'); box.append(make('legend', 'Controls they get'));
      const ticks = state.choices.map(c => {
        const t = make('input'); t.type = 'checkbox'; t.value = c.id; t.checked = state.default.includes(c.id);
        const l = make('label'); l.append(t, ' ' + c.label); box.append(l); return t;
      });
      const code = make('input'); code.type = 'password'; code.maxLength = 32; code.autocomplete = 'off';
      code.placeholder = 'Take-back code (optional)'; code.setAttribute('aria-label', 'Take-back code (optional)');
      const go = make('button', 'Hand over'); go.type = 'button';
      go.addEventListener('click', async () => {
        const out = await post({ op: 'hand', name: name.value, special: special.checked, grants: ticks.filter(t => t.checked).map(t => t.value), code: code.value });
        if (!out.ok) return fail(out.error);
        apply(out); status(`${out.directing} is directing (${out.title.toLowerCase()}).`); dialog.close();
      });
      parts.push(name, sp, box, code, make('p', 'Without a code, anyone at the keyboard can take the console back. Restarting Mythastria always gives it back to the showrunner.', 'note'), go);
    } else {
      const have = state.choices.filter(c => state.grants.includes(c.id)).map(c => c.label);
      const keep = state.choices.filter(c => !state.grants.includes(c.id)).map(c => c.label);
      parts.push(make('p', `${state.directing} is directing as ${state.title.toLowerCase()}.`),
        make('p', 'They have: ' + (have.join('; ') || 'no GM controls'), 'note'), make('p', 'Kept by the showrunner: ' + (keep.join('; ') || 'nothing'), 'note'));
      const code = make('input'); code.type = 'password'; code.maxLength = 32; code.autocomplete = 'off';
      code.placeholder = 'Take-back code'; code.setAttribute('aria-label', 'Take-back code'); code.hidden = !state.code;
      const back = make('button', 'Take back'); back.type = 'button';
      back.addEventListener('click', async () => {
        const out = await post({ op: 'take_back', code: code.value });
        if (!out.ok) return fail(out.error);
        apply(out); status('The showrunner is directing again.'); dialog.close();
      });
      parts.push(code, back);
    }
    const close = make('button', 'Close', 'quiet'); close.type = 'button'; close.addEventListener('click', () => dialog.close());
    dialog.replaceChildren(...parts, err, close);
  }
  async function refresh() {
    const out = await post({ op: 'state' }).catch(() => null);
    if (out?.ok) apply(out);
    return out;
  }
  button.addEventListener('click', async () => {
    const out = await refresh();
    if (!out?.ok) { status('Director: ' + (out?.error || 'the simulator service stopped.'), true); return; }
    draw();
    dialog.showModal();
  });
  refresh();
  return { dialog, refresh, get state() { return state; } };
}
