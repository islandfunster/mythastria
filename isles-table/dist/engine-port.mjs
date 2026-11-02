// The client's one door to a rules engine (merge handoff 2026-10-19, step 4, first part). The table talks to a port,
// not to the Rust kernel directly, so a second authority (the live FG bridge or a local simulator service) can be put
// behind the same door later without touching the drawing code. One port per session: the table never asks two
// engines to resolve the same turn.
//
// A port: { kind, authority, readOnly, call(message) -> reply }. Replies keep the Rust envelope ({ok, error, ...}).

export function createRustPort(rustEngine) {
  if (!rustEngine || typeof rustEngine.call !== 'function') throw new Error('A Rust engine is required.');
  return Object.freeze({
    kind: 'rust', authority: 'isles-rust (browser WASM, training mode)', readOnly: false,
    call: message => rustEngine.call(message),
  });
}

// A port that refuses every change: for replays and for showing another engine's state without acting on it.
// Reads it can answer itself (a fixed view) are answered; anything else is refused with a reason, never forwarded.
export function createReadOnlyPort(view, { authority = 'recording' } = {}) {
  const snapshot = structuredClone(view);
  return Object.freeze({
    kind: 'read-only', authority, readOnly: true,
    call(message) {
      if (message?.op === 'state') return { ok: true, ...structuredClone(snapshot) };
      return { ok: false, error: `Read-only: "${message?.op ?? '?'}" is not available here; ${authority} decides.` };
    },
  });
}

// Guard for the one-authority rule: a session keeps the port it started with.
export function bindSession(port) {
  let bound = port;
  return {
    get port() { return bound; },
    replace(next) {
      if (bound && next && bound !== next && bound.kind !== next.kind)
        throw new Error(`This session is played by ${bound.authority}; start a new session to use ${next.authority}.`);
      bound = next;
      return bound;
    },
  };
}

// The simulator as a local service (Mythastria tools/sim_service.py; merge step 4 B, first increment). The simulator
// plays the fight; this port only asks for it one turn at a time and keeps the revision the service expects. It never
// resolves anything itself, and it refuses a second request while one is in flight, so a double click cannot send two.
// Calls are async (HTTP), unlike the Rust port. Replies keep the service's envelope ({ok, error, ...}); a refused step
// (409 stale) comes back as {ok: false, status: 409, error, revision}.
export function createSimServicePort({ fetch: fetchFn = globalThis.fetch, base = '' } = {}) {
  let token = null, session = null, revision = 0, busy = false, done = false;
  const post = async (path, body) => {
    const res = await fetchFn(base + path, { method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ ...body, token }) });
    const out = await res.json();
    return res.ok ? out : { ...out, ok: false, status: res.status };
  };
  const once = async fn => {
    if (busy) return { ok: false, status: 0, error: 'A request is already on its way; wait for it.' };
    busy = true;
    try { return await fn(); } finally { busy = false; }
  };
  return Object.freeze({
    kind: 'sim-service', authority: 'simulator (Mythastria sim/)', readOnly: true,
    get session() { return session; },
    get revision() { return revision; },
    get done() { return done; },
    get busy() { return busy; },
    hello: () => once(async () => {
      const res = await fetchFn(base + '/api/hello');
      const out = await res.json();
      if (res.ok && out.ok) token = out.token;
      return res.ok ? out : { ...out, ok: false, status: res.status };
    }),
    newFight: settings => once(async () => {
      if (!token) return { ok: false, status: 0, error: 'Say hello to the service first.' };
      const out = await post('/api/new', settings);
      if (out.ok) { session = out.session; revision = out.revision; done = out.done; }
      return out;
    }),
    step: () => once(async () => {
      if (!session) return { ok: false, status: 0, error: 'Start a fight first.' };
      if (done) return { ok: true, messages: [], done: true, revision };
      const out = await post('/api/step', { session, revision });
      if (out.ok) { revision = out.revision; done = out.done; }
      else if (out.status === 409 && Number.isInteger(out.revision)) revision = out.revision;   // resync, reveal nothing
      return out;
    }),
    messages: () => once(async () => session ? post('/api/messages', { session }) : { ok: false, status: 0, error: 'No fight.' }),
    // the shared port shape: a synchronous call() is not possible over HTTP
    call: () => ({ ok: false, error: 'The simulator service is asynchronous: use hello(), newFight(), step().' }),
  });
}
