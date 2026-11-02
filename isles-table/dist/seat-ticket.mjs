// JOIN-01 (GM 2026-10-21: the handshake connecting players with the engine; chose "over the internet" and "GM approves
// each"; Mythastria docs/development/JOIN_PROTOCOL.md): the seat this browser was given at the players' door. The
// ticket is the seat's key: every players'-door request carries it, and the service reads the seat (name, character)
// from it, never from the page. Kept per address, so the GM's own pages (the GM door) never have one.
export const SEAT_KEY = 'mythastria-seat';

export function loadSeat(storage = globalThis.localStorage) {
  try {
    const s = JSON.parse(storage?.getItem(SEAT_KEY) ?? 'null');
    return typeof s?.ticket === 'string' && s.ticket ? s : null;
  } catch { return null; }
}
export function saveSeat(seat, storage = globalThis.localStorage) {
  try { storage?.setItem(SEAT_KEY, JSON.stringify({ ticket: seat.ticket, name: seat.name, character: seat.character ?? '' })); } catch {}
}
export function clearSeat(storage = globalThis.localStorage) {
  try { storage?.removeItem(SEAT_KEY); } catch {}
}
// What a port adds to a request beside the token: the ticket, when this browser has a seat here.
export function seatPart(storage = globalThis.localStorage) {
  const s = loadSeat(storage);
  return s ? { ticket: s.ticket } : {};
}

// BETA-B (GM 2026-10-22): a players' page says plainly when its seat has closed, when the notice must be accepted again,
// or when it is asked to slow down, with the way back to the join page. Shown once, over the page.
export function seatNotice(out, doc = globalThis.document) {
  if (!doc?.body || !out || !(out.no_seat || out.notice || out.slow_down)) return;
  if (out.no_seat) clearSeat();
  let bar = doc.getElementById('seat-notice');
  if (!bar) {
    bar = doc.createElement('div'); bar.id = 'seat-notice'; bar.setAttribute('role', 'alert');
    bar.style.cssText = 'position:fixed;left:50%;top:16px;transform:translateX(-50%);z-index:90;max-width:min(560px,calc(100vw - 32px));' +
      'padding:12px 16px;border:1px solid #c5a56b;border-radius:8px;background:#20211d;color:#e6dcc2;font:15px/1.4 Georgia,serif;box-shadow:0 8px 24px rgba(0,0,0,.5)';
    doc.body.append(bar);
  }
  const text = out.no_seat ? 'Your seat at the table has closed (you left, the GM removed it, or the table restarted).'
    : out.notice ? "The table's notice has changed. Accept it again to keep your seat." : 'Slow down a little: the table will answer again in a moment.';
  bar.replaceChildren(text + ' ');
  if (!out.slow_down) {
    const a = doc.createElement('a'); a.href = 'join.html'; a.textContent = out.no_seat ? 'Join again' : 'Open the join page';
    a.style.color = '#c5a56b'; bar.append(a);
  } else setTimeout(() => bar.remove(), 8000);
}
