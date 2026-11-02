// JOIN-01 (GM 2026-10-21: "let's work on the handshaking protocol to connect players with the main DM engine"; chose
// "over the internet" and "GM approves each"): the GM's Players dialog on Play live. Open or close the players' door,
// approve or refuse who asks (and which character they play), see who is connected, remove a seat. The service keeps
// the seats and checks every answer (Mythastria tools/table_seats.py; docs/development/JOIN_PROTOCOL.md).

export function seatsSummary(state) {
  const n = state?.asks?.length ?? 0;
  return n ? `${n} player${n === 1 ? '' : 's'} asking to join` : '';
}

const askAgo = a => `asked ${a.waited}s ago`;
// BETA-B: who knocked, who was turned away, slowed down or blocked (names typed, or an anonymous visitor tag)
function doorLog(entries, doc = globalThis.document) {
  if (!entries?.length) { const p = doc.createElement('p'); p.className = 'note'; p.textContent = 'Nobody has knocked yet.'; return p; }
  const ul = doc.createElement('ul'); ul.className = 'door-log';
  for (const e of entries) {
    const li = doc.createElement('li');
    li.textContent = `${new Date(e.t * 1000).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })} · ${e.who}: ${e.text}`;
    ul.append(li);
  }
  return ul;
}
// CHEAT-LOG-01 (GM 2026-11-02: "A tool for the logs should find cheaters"; Mythastria tools/door_watch.py): what the door
// refused, by player. Timing never shows here; a refusal is a reason to look, not proof.
function watchList(entries, make, clear, doc = globalThis.document) {
  const box = doc.createElement('div');
  if (!entries?.length) { box.append(make('p', 'Nothing refused that matters.', 'note')); return box; }
  const ul = make('ul');
  for (const w of entries) {
    const li = make('li');
    const open = doc.createElement('details');
    const head = doc.createElement('summary');
    head.append(make('strong', w.who), ` ${w.not_allowed} not allowed, ${w.against_rules} against the rules `);
    if (w.look) head.append(make('span', 'Worth a look', 'seats-look'));
    const lines = make('ul', undefined, 'door-log');
    for (const e of w.lines) lines.append(make('li', `${new Date(e.t * 1000).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })} · ${e.sort}: ${e.what}${e.why ? ' (' + e.why + ')' : ''}`));
    open.append(head, lines);
    li.append(open);
    ul.append(li);
  }
  const wipe = make('button', 'Clear this list', 'quiet'); wipe.type = 'button'; wipe.addEventListener('click', clear);
  box.append(ul, wipe);
  return box;
}
const seatAgo = s => s.connected ? 'connected' : `away (last seen ${s.seen_ago}s ago)`;
// HINTS-01 step H3 (GM 2026-10-28): the table cap and each seat's limit. The GM can lower a seat's hints, never raise
// them: only the player turns hints on (Mythastria tools/table_seats.py).
const HINT_WORD = { off: 'Off', reminders: 'Reminders' };
const CAP_CHOICES = [['reminders', 'Players choose (up to Reminders)'], ['off', 'Off for everyone']];
const LIMIT_CHOICES = [['reminders', 'Player chooses'], ['off', 'Off']];

export function mountSeats({ document: doc = globalThis.document, button, status = () => {}, fetch: fetchFn = globalThis.fetch, every = 3000 }) {
  const make = (tag, text, cls) => { const e = doc.createElement(tag); if (text !== undefined) e.textContent = text; if (cls) e.className = cls; return e; };
  const dialog = make('dialog'); dialog.id = 'seats-dialog'; dialog.setAttribute('aria-labelledby', 'seats-title');
  doc.body.append(dialog);
  let token = null, state = null, drawn = '', error = '';
  const flagged = new Set();                                      // CHEAT-LOG-01: said once per player

  async function post(body, retry = true) {
    if (!token) token = (await (await fetchFn('/api/hello')).json()).token;
    const res = await fetchFn('/api/seats', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ ...body, token }) });
    const out = await res.json().catch(() => ({ ok: false, error: 'The service sent no answer.' }));
    if (res.status === 403 && retry && /token/i.test(out.error || '')) { token = null; return post(body, false); }
    return res.ok ? out : { ...out, ok: false };
  }
  async function act(body) {
    const out = await post(body).catch(() => ({ ok: false, error: 'The simulator service stopped.' }));
    error = out.ok ? '' : (out.error || 'Refused.');
    if (out.ok) apply(out);
    draw(true);
    return out;
  }
  function apply(next) {
    const before = state?.asks?.length ?? 0;
    state = next;
    const n = state.asks.length;
    button.replaceChildren('Players…');
    if (n) button.append(make('span', String(n), 'seats-count'));
    const looks = (state.watch ?? []).filter(w => w.look).map(w => w.who);   // CHEAT-LOG-01
    if (looks.length) button.append(make('span', '!', 'seats-look-dot'));
    for (const who of looks) if (!flagged.has(who)) { flagged.add(who); status(`${who}: worth a look. Players… shows what the table refused.`); }
    button.title = seatsSummary(state) || 'Let players join from their own screen: open the door, approve each one';
    if (n > before) status(seatsSummary(state) + ': Players… to let them in.');
  }
  function draw(force = false) {
    if (!state || !dialog.open) return;
    const key = JSON.stringify([state.open, state.link, state.invite, state.characters, state.door_log?.[0]?.t, state.door_log?.length, state.asks.map(a => [a.ask, a.character]),
      state.seats.map(s => [s.name, s.character, s.connected, s.notice, s.hints, s.hints_limit]), state.hints_cap,
      state.watch?.map(w => [w.who, w.not_allowed, w.against_rules, w.look])]);
    if (key === drawn && !force) {                                // only the times changed: keep what the GM is typing
      for (const a of state.asks) { const e = dialog.querySelector(`[data-ask="${CSS.escape(a.ask)}"]`); if (e) e.textContent = askAgo(a); }
      for (const s of state.seats) { const e = dialog.querySelector(`[data-seat="${CSS.escape(s.name)}"]`); if (e) e.textContent = seatAgo(s); }
      return;
    }
    drawn = key;
    const title = make('h2', 'Players'); title.id = 'seats-title';
    const list = make('datalist'); list.id = 'seats-characters';
    list.append(...state.characters.map(n => Object.assign(make('option'), { value: n })));
    const door = make('p');
    const toggle = make('button', state.open ? 'Close the door' : 'Open the door'); toggle.type = 'button';
    toggle.addEventListener('click', () => act({ op: 'door', open: !state.open }));
    door.append(make('strong', state.open ? 'The door is open: players can ask to join. ' : 'The door is closed: nobody can ask to join. '), toggle);
    const where = make('p', '', 'note');
    if (state.link && state.open) {                                // GM 2026-10-21: players join only with the GM's invite
      const again = make('button', 'New invite', 'quiet'); again.type = 'button';
      again.title = 'Make a new invite code: the old link stops working (seated players stay)';
      again.addEventListener('click', () => act({ op: 'invite' }));
      where.append('Send your players this invite link: ', make('span', `${state.link}join.html#invite=${state.invite}`, 'seats-link'),
        ` (code ${state.invite}) `, again);
    } else if (state.link) where.append('Open the door to get an invite link for your players.');
    else where.append("The players' door is not running: start Mythastria with the Desktop Start_Mythastria.bat (it opens the door's port).");

    const asks = make('ul');
    for (const a of state.asks) {
      const li = make('li');
      const who = make('input'); who.value = a.character; who.maxLength = 40; who.setAttribute('list', 'seats-characters');
      who.placeholder = 'watch only'; who.setAttribute('aria-label', `Character for ${a.name}`);
      const why = make('input'); why.maxLength = 200; why.placeholder = 'Reason (if refusing)'; why.setAttribute('aria-label', `Reason to refuse ${a.name}`);
      const yes = make('button', 'Approve'); yes.type = 'button';
      yes.addEventListener('click', () => act({ op: 'approve', ask: a.ask, character: who.value.trim() }));
      const no = make('button', 'Refuse', 'quiet'); no.type = 'button';
      no.addEventListener('click', () => act({ op: 'refuse', ask: a.ask, reason: why.value.trim() }));
      const ago = make('span', askAgo(a), 'note'); ago.dataset.ask = a.ask;
      li.append(make('strong', a.name), make('span', a.character ? `asks to play ${a.character}` : 'asks to watch', 'grow'), ago, who, yes, why, no);
      asks.append(li);
    }
    const seats = make('ul');
    for (const s of state.seats) {
      const li = make('li');
      const dot = make('span', '', 'join-dot' + (s.connected ? '' : ' away')); dot.title = s.connected ? 'Connected' : 'Away';
      const ago = make('span', seatAgo(s), 'note'); ago.dataset.seat = s.name;
      const who = make('input'); who.value = s.character; who.maxLength = 40; who.setAttribute('list', 'seats-characters');
      who.placeholder = 'watch only'; who.setAttribute('aria-label', `Character for ${s.name}`);
      const change = make('button', 'Change', 'quiet'); change.type = 'button';
      change.addEventListener('click', () => act({ op: 'assign', name: s.name, character: who.value.trim() }));
      const out = make('button', 'Remove', 'quiet'); out.type = 'button';
      out.addEventListener('click', () => act({ op: 'remove', name: s.name }));
      const ok = s.notice && s.notice === state.notice;            // JOIN-01 notice: accepted the current version
      const note = make('span', ok ? 'notice accepted' : 'notice not accepted yet', 'note');
      note.title = s.notice ? `Accepted notice ${s.notice} at ${new Date(s.accepted_at * 1000).toLocaleString()}` : 'Asked to accept the new notice';
      const hints = make('span', `hints ${HINT_WORD[s.hints] ?? s.hints}`, 'note');   // H3: the level the player chose
      hints.title = 'The player turns hints on from their own sheet; you can only lower them.';
      const limit = make('select'); limit.setAttribute('aria-label', `Hints limit for ${s.name}`);
      limit.title = `The most ${s.name} may turn on. Off lowers their hints now; Player chooses turns nothing on.`;
      for (const [v, text] of LIMIT_CHOICES) limit.append(Object.assign(make('option', text), { value: v, selected: v === (s.hints_limit ?? 'reminders') }));
      limit.addEventListener('change', () => act({ op: 'hints_limit', name: s.name, level: limit.value }));
      li.append(dot, make('strong', s.name), make('span', s.character ? `plays ${s.character}` : 'watching', 'grow'), ago, note, hints, limit, who, change, out);
      seats.append(li);
    }
    const capRow = make('p');                                      // H3: the table cap
    const cap = make('select'); cap.setAttribute('aria-label', 'Hints at this table');
    cap.title = "Off for everyone turns every player's hints off now, your own screen's too. Players choose turns nothing on: each player decides.";
    for (const [v, text] of CAP_CHOICES) cap.append(Object.assign(make('option', text), { value: v, selected: v === (state.hints_cap ?? 'reminders') }));
    cap.addEventListener('change', () => act({ op: 'hints_cap', level: cap.value }));
    capRow.append(make('strong', 'Turn hints at this table: '), cap);
    const err = make('p', error, 'seats-error'); err.setAttribute('role', 'alert'); err.hidden = !error;
    const close = make('button', 'Close', 'quiet'); close.type = 'button'; close.addEventListener('click', () => dialog.close());
    dialog.replaceChildren(title, list, door, where,
      make('h3', 'Asking to join'), state.asks.length ? asks : make('p', 'Nobody is waiting.', 'note'),
      make('h3', 'At the table'), capRow, state.seats.length ? seats : make('p', 'No players have joined.', 'note'),
      make('h3', 'Refused by the table'),
      make('p', "What the rules engine refused, by player. Timing, like a late click, isn't listed. Not allowed is what the table's own screen never sends; against the rules can be an honest mistake, so it counts when it piles up. A refusal is a reason to look, not proof.", 'note'),
      watchList(state.watch, make, () => { flagged.clear(); act({ op: 'watch_clear' }); }),
      make('h3', 'Door log'), doorLog(state.door_log),
      make('p', 'A player keeps their seat through a dropped connection. Restarting Mythastria closes the door and ends every seat; players then ask again.', 'note'),
      err, close);
  }
  async function refresh() {
    const out = await post({ op: 'state' }).catch(() => null);
    if (out?.ok) { apply(out); draw(); }
    return out;
  }
  button.addEventListener('click', async () => {
    const out = await refresh();
    if (!out?.ok) { status('Players: ' + (out?.error || 'the simulator service stopped.'), true); return; }
    error = ''; dialog.showModal(); draw(true);
  });
  refresh();
  const poll = setInterval(refresh, every);
  return { dialog, refresh, stop: () => clearInterval(poll), get state() { return state; } };
}
