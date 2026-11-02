// JOIN-01 (GM 2026-10-21: "let's work on the handshaking protocol to connect players with the main DM engine"; chose
// "over the internet" and "GM approves each"): the players' join page. Hello, ask (name, character), wait for the GM,
// then keep the seat ticket and check in; a dropped connection reconnects with the same ticket. The service decides
// everything (Mythastria tools/table_seats.py; docs/development/JOIN_PROTOCOL.md).
import { api } from './server.mjs';                            // PLAYER-SITE-01: the GM's Mythastria
import { loadSeat, saveSeat, clearSeat } from './seat-ticket.mjs';
import { loadNotice, mountNotice } from './notice-ui.mjs';     // JOIN-01 notice (GM 2026-10-22): privacy, 18+, table rules

const $ = id => document.getElementById(id);
const ASK_KEY = 'mythastria-join-ask';                          // a request still waiting (this tab survives a reload)
const INVITE_KEY = 'mythastria-join-invite';                    // the code from the GM's invite link (#invite=...)
let hello = null, timer = null, lost = 0, notice = null, again = null;
const noticeReady = loadNotice().then(n => { notice = mountNotice($('join-notice'), n); return n; });

function show(part) { for (const id of ['join-ask', 'join-wait', 'join-seated', 'join-again']) $(id).hidden = id !== part; }
function status(text, isError = false) { $('join-status').textContent = text; $('join-status').className = isError ? 'error' : ''; }
function later(fn, seconds) { clearTimeout(timer); timer = setTimeout(fn, seconds * 1000); }

async function post(op, body = {}) {
  const res = await fetch(api('/api/join'), { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ op, ...body }) });
  const out = await res.json().catch(() => ({ ok: false, error: 'The table sent no answer.' }));
  return { ...out, http: res.status, ok: res.ok && out.ok };
}
const pending = () => { try { return JSON.parse(sessionStorage.getItem(ASK_KEY) ?? 'null'); } catch { return null; } };
const setPending = p => { try { p ? sessionStorage.setItem(ASK_KEY, JSON.stringify(p)) : sessionStorage.removeItem(ASK_KEY); } catch {} };

// Hello: is this the players' door, is it open, which characters are in the fight
async function knock() {
  try { hello = await (await fetch(api('/api/hello'))).json(); } catch { hello = null; }
  if (!hello?.ok) { status('The table does not answer. Is Mythastria running? Trying again…', true); later(start, 5); return false; }
  if (hello.door !== 'players') { status("This is the GM's own address. Players join at the players' door the GM gives them.", true); return false; }
  $('join-characters').replaceChildren(...(hello.characters ?? []).map(n => Object.assign(document.createElement('option'), { value: n })));
  return true;
}

function rememberInvite() {
  const code = new URLSearchParams(location.hash.slice(1)).get('invite');
  if (code) { try { sessionStorage.setItem(INVITE_KEY, code); } catch {} history.replaceState(null, '', location.pathname); }
  try { $('join-invite').value = sessionStorage.getItem(INVITE_KEY) ?? ''; } catch {}
  $('join-invite-row').hidden = !!$('join-invite').value;      // the link brought it: nothing to type
}

async function start() {
  rememberInvite();
  if (!(await knock())) return;
  if (loadSeat()) return beat();
  if (pending()) return wait();
  askForm();
}

function askForm(note = '') {
  show('join-ask');
  $('join-go').disabled = !hello.open;
  status(note || (hello.open ? 'Say who you are and which character you play.' : "The GM hasn't opened the door yet. This page checks again by itself."), !!note);
  if (!hello.open) later(async () => { if (await knock() && !loadSeat() && !pending()) askForm(note); }, 5);
}

$('join-ask').addEventListener('submit', async e => {
  e.preventDefault();
  $('join-go').disabled = true;
  await noticeReady;
  const out = await post('ask', { name: $('join-name').value.trim(), character: $('join-character').value.trim(), invite: $('join-invite').value.trim(),
    notice: notice?.value() }).catch(() => null);
  if (!out?.ok) {
    $('join-go').disabled = false;
    if (/invite/i.test(out?.error || '')) $('join-invite-row').hidden = false;   // an old link: let them type the new code
    return status(out?.error || 'The table does not answer.', true);
  }
  setPending({ ask: out.ask, key: out.key });
  wait();
});

async function wait() {
  show('join-wait');
  status('Asked. The GM sees your request on their screen.');
  const p = pending();
  const out = await post('wait', p ?? {}).catch(() => null);
  if (!out?.ok) { status('Lost touch with the table; still asking…', true); return later(wait, 3); }
  if (out.status === 'waiting') return later(wait, 2);
  setPending(null);
  if (out.status === 'approved') {
    saveSeat({ ticket: out.ticket, ...out.seat });
    return beat();
  }
  askForm(out.status === 'refused' ? 'The GM said no' + (out.reason ? ': ' + out.reason : '.') : 'That request is no longer waiting; ask again.');
}
$('join-cancel').addEventListener('click', async () => {
  clearTimeout(timer);
  await post('cancel', pending() ?? {}).catch(() => null);
  setPending(null);
  askForm();
});

// Seated: check in every few seconds; a lost connection keeps the ticket and tries again
async function beat() {
  const seat = loadSeat();
  if (!seat) return askForm();
  show('join-seated');
  $('join-who').textContent = seat.character ? `You're at the table as ${seat.name}, playing ${seat.character}.` : `You're at the table as ${seat.name}, watching.`;
  const out = await post('beat', { ticket: seat.ticket }).catch(() => null);
  if (out?.no_seat) { clearSeat(); return askForm(out.error); }
  if (!out?.ok) {
    lost += 1;
    $('join-dot').className = 'join-dot away'; $('join-link').textContent = 'Reconnecting…';
    status('The connection dropped; reconnecting with your seat…', true);
    return later(beat, Math.min(15, 2 * lost));
  }
  lost = 0;
  if (out.notice_ok === false) {                                  // a new notice: accept it again, the seat waits
    if ($('join-again').hidden) { show('join-again'); again = mountNotice($('join-again-notice'), await loadNotice()); }
    status('The notice changed: accept it to keep your seat.', true);
    return later(beat, out.beat || 5);
  }
  if (out.seat.character !== seat.character) saveSeat({ ...seat, character: out.seat.character });   // the GM changed it
  $('join-who').textContent = out.seat.character ? `You're at the table as ${out.seat.name}, playing ${out.seat.character}.` : `You're at the table as ${out.seat.name}, watching.`;
  $('join-dot').className = 'join-dot'; $('join-link').textContent = 'Connected';
  status('You are in.');
  later(beat, out.beat || 5);
}
$('join-again').addEventListener('submit', async e => {
  e.preventDefault();
  const seat = loadSeat();
  const out = seat ? await post('accept', { ticket: seat.ticket, notice: again?.value() }).catch(() => null) : null;
  if (!out?.ok) return status(out?.error || 'The table does not answer.', true);
  beat();
});
$('join-leave').addEventListener('click', async () => {
  clearTimeout(timer);
  const seat = loadSeat();
  if (seat) await post('leave', { ticket: seat.ticket }).catch(() => null);
  clearSeat();
  await knock();
  askForm();
});

start();
