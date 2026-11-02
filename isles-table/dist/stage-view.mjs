// STAGE-01 on the Isles Table (GM 2026-10-19: "I only have one computer ... FG is too slow ... add it there").
// The Stage's rules live in the simulator (Mythastria sim/stage.py) behind the local service (tools/sim_service.py):
// this module only talks to that service and turns its view into what the page shows. It decides nothing.
// Hotseat on one PC: the page names the seat; the service treats only the "GM" seat as the Director.
import { seatPart } from './seat-ticket.mjs';                  // JOIN-01: a seated player's ticket
import { SERVER } from './server.mjs';                         // PLAYER-SITE-01: the GM's Mythastria

export function fmt(seconds) {
  const s = Math.max(0, Math.round(seconds));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`;
}

// The spotlight time on screen: the service's elapsed time when the view was fetched, plus the time since, while running.
export function liveElapsed(view, fetchedAtMs, nowMs) {
  if (!view?.holder) return 0;
  return view.elapsed + (view.running ? Math.max(0, nowMs - fetchedAtMs) / 1000 : 0);
}

// The banner: null when no one holds the spotlight.
export function cue(view, fetchedAtMs, nowMs) {
  if (!view?.holder) return null;
  return {
    label: view.discussion ? 'Dialogue' : 'ON AIR',
    line: view.discussion ? `${view.holder}'s spotlight · join in character` : `${view.holder} · Spotlight - please listen`,
    time: fmt(liveElapsed(view, fetchedAtMs, nowMs)) + (view.running ? '' : ' (paused)'),
    discussion: !!view.discussion,
  };
}

// Who can be named in a command: the players the Stage knows plus the seats typed at this table, never the GM seat.
export function tableNames(view, seats) {
  const names = new Map();
  for (const n of [...(view?.participants ?? []).map(p => p.name), ...seats]) {
    if (n && n !== 'GM' && !names.has(n.toLowerCase())) names.set(n.toLowerCase(), n);
  }
  return [...names.values()].sort((a, b) => a.localeCompare(b));
}

export function newId() {
  return globalThis.crypto?.randomUUID?.() ?? `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;
}

// The service's Stage API (same origin): hello for the token, then command and state per seat.
export function createStagePort({ fetch: fetchFn = globalThis.fetch, base = SERVER } = {}) {
  let token = null;
  const post = async (path, body) => {
    const res = await fetchFn(base + path, { method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ ...body, token, ...seatPart() }) });   // JOIN-01: a seated player's ticket
    let out;
    try { out = await res.json(); } catch { out = { ok: false, error: 'The service sent no answer.' }; }
    return res.ok ? out : { ok: false, status: res.status, error: out.error || `HTTP ${res.status}` };
  };
  return {
    async hello() {
      const res = await fetchFn(base + '/api/hello');
      const out = await res.json();
      if (res.ok && out.ok) token = out.token;
      return out;
    },
    command: (seat, cmd) => post('/api/stage', { seat, cmd: { id: newId(), ...cmd } }),
    state: seat => post('/api/stage/state', { seat }),
  };
}
