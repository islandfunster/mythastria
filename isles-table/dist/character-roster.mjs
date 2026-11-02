// RUST-DEPRECATE-01 parity item 2 (GM 2026-10-20: "keep Python as the sole rules authority ... Archive Rust only after
// checking feature parity"): the Characters roster is checked by the Python simulator service (POST /api/characters,
// sim/character_roster.py, the same rules and messages as the old Rust check). Without the service (a plain file
// server, Start_Table.bat) the deprecated Rust engine still checks it, so the old table keeps working.
//
// `rust(request)` is the old engine's call (it returns the reply or throws its error). After the service accepts a
// change, the roster is copied into the Rust engine too, so the training table can still place the character.
export function createRosterPort({ fetch: fetchFn = globalThis.fetch, base = '', rust = null } = {}) {
  let token = null, service = null;                              // service: null = not asked yet, then true / false

  async function hello() {
    try {
      const res = await fetchFn(base + '/api/hello');
      if (!res?.ok) return false;
      token = (await res.json())?.token ?? null;
      return typeof token === 'string' && token.length > 0;
    } catch { return false; }
  }

  async function post(body, retry = true) {
    const res = await fetchFn(base + '/api/characters', { method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ ...body, token }) });
    let out;
    try { out = await res.json(); } catch { out = { ok: false, error: 'The simulator service sent no answer.' }; }
    if (res.status === 403 && retry && await hello()) return post(body, false);   // the service restarted: new token
    return out;
  }

  async function call(request) {
    if (service === null) service = await hello();
    if (!service) {
      if (!rust) throw new Error('The simulator service is not running: start Mythastria to keep characters.');
      return rust(request);
    }
    const out = await post(request);
    if (!out?.ok) throw new Error(out?.error || 'The simulator service refused the character.');
    if (rust && Array.isArray(out.characters)) {
      try { rust({ op: 'character_roster_load', characters: out.characters }); } catch { /* placement only; Python decided */ }
    }
    return out;
  }

  return { call, get checkedBy() { return service === null ? null : service ? 'python' : 'rust'; } };
}
