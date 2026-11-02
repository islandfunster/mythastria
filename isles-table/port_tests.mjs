// Tests for dist/engine-port.mjs (one door to one rules engine). Shared by test_port.mjs (Node) and the browser runner.
import { createRustPort, createReadOnlyPort, bindSession, createSimServicePort } from './dist/engine-port.mjs';

function assert(cond, text) { if (!cond) throw new Error('FAILED: ' + text); }

export function run(rustEngine) {
  const results = [];
  const test = (name, fn) => { try { fn(); results.push([name, true, '']); } catch (e) { results.push([name, false, e.message]); } };

  test('the Rust port passes requests through unchanged (training mode as before)', () => {
    const port = createRustPort(rustEngine);
    const v = port.call({ op: 'new', seed: 7, scene: 'temple' });
    assert(v.ok && v.state.revision === 0, 'a new training session');
    const again = createRustPort(rustEngine).call({ op: 'state' });
    assert(JSON.stringify(again.state) === JSON.stringify(v.state), 'the same engine state through a second port');
    assert(port.kind === 'rust' && !port.readOnly, 'kind');
  });

  test('a read-only port answers state and refuses every change, naming the authority', () => {
    const view = { state: { round: 2, combatants: [{ id: 'a', hp: 5 }] }, map: { name: 'm' } };
    const port = createReadOnlyPort(view, { authority: 'the simulator' });
    const s = port.call({ op: 'state' });
    assert(s.ok && s.state.round === 2, 'state answered');
    s.state.round = 99;
    assert(port.call({ op: 'state' }).state.round === 2, 'callers cannot change the snapshot');
    for (const op of ['command', 'new', 'load', 'skin', 'move']) {
      const r = port.call({ op, id: 'x', revision: 0, offer_id: 'end' });
      assert(r.ok === false && r.error.includes('the simulator decides'), op + ' refused');
    }
  });

  test('a session keeps the authority it started with', () => {
    const rust = createRustPort(rustEngine), ro = createReadOnlyPort({ state: {} });
    const session = bindSession(rust);
    let refused = false;
    try { session.replace(ro); } catch { refused = true; }
    assert(refused && session.port === rust, 'no second authority mid-session');
    assert(session.replace(createRustPort(rustEngine)).kind === 'rust', 'the same kind may be re-bound (a reload)');
  });

  return results;
}

// A stand-in for tools/sim_service.py with the same protocol: hello gives a token; new returns [scenario, state];
// step must name the current revision (else 409 with the current one); every POST must carry the token.
export function fakeService({ turns = 2, delay = 0 } = {}) {
  const token = 'tok', calls = [];
  let revision = 0, shown = 0;
  const json = (status, body) => ({ ok: status < 400, status, json: async () => body });
  const wait = () => new Promise(r => setTimeout(r, delay));
  const fetch = async (path, init = {}) => {
    calls.push(path);
    await wait();
    if (path === '/api/hello') return json(200, { ok: true, token, scenarios: ['walls_door_ui.json'], members: [], authority: 'fake' });
    const body = JSON.parse(init.body ?? '{}');
    if (body.token !== token) return json(403, { ok: false, error: 'token' });
    if (path === '/api/new') { revision = 0; shown = 0; return json(200, { ok: true, session: 's1', revision: 0, messages: [{ type: 'scenario' }, { type: 'state' }], done: false }); }
    if (path === '/api/step') {
      if (body.revision !== revision) return json(409, { ok: false, error: 'Stale step', revision });
      shown++; revision++;
      return json(200, { ok: true, revision, messages: [{ type: 'action' }, { type: 'result' }, { type: 'state' }], done: shown >= turns });
    }
    if (path === '/api/messages') return json(200, { ok: true, revision, messages: [], done: shown >= turns });
    return json(404, { ok: false, error: 'Not found' });
  };
  return { fetch, calls, bump() { revision++; } };
}

export async function runAsync() {
  const results = [];
  const test = async (name, fn) => { try { await fn(); results.push([name, true, '']); } catch (e) { results.push([name, false, e.message]); } };

  await test('the simulator port steps a fight one turn at a time and keeps the revision', async () => {
    const svc = fakeService();
    const port = createSimServicePort({ fetch: svc.fetch });
    assert(port.readOnly && port.kind === 'sim-service', 'kind');
    assert((await port.step()).ok === false, 'no step before a fight');
    assert((await port.newFight({ scenario: 'walls_door_ui.json' })).ok === false, 'no fight before hello (no token)');
    assert((await port.hello()).ok, 'hello');
    const f = await port.newFight({ scenario: 'walls_door_ui.json' });
    assert(f.ok && port.revision === 0 && f.messages.length === 2, 'a fight');
    const a = await port.step();
    assert(a.ok && port.revision === 1 && a.messages.length === 3 && !port.done, 'first turn');
    const b = await port.step();
    assert(b.ok && port.revision === 2 && port.done, 'last turn');
    const c = await port.step();
    assert(c.ok && c.messages.length === 0 && c.done, 'nothing after the end');
    assert(svc.calls.filter(x => x === '/api/step').length === 2, 'no request after the end');
  });

  await test('a second step while one is in flight is refused locally (a double click sends one request)', async () => {
    const svc = fakeService({ delay: 20 });
    const port = createSimServicePort({ fetch: svc.fetch });
    await port.hello(); await port.newFight({ scenario: 'walls_door_ui.json' });
    const [one, two] = await Promise.all([port.step(), port.step()]);
    assert(one.ok && !two.ok && two.status === 0, 'the second is refused');
    assert(svc.calls.filter(x => x === '/api/step').length === 1, 'one request sent');
    assert(port.revision === 1, 'one turn spent');
  });

  await test('a stale step (the service moved on) is surfaced as 409 and the port resyncs its revision', async () => {
    const svc = fakeService({ turns: 3 });
    const port = createSimServicePort({ fetch: svc.fetch });
    await port.hello(); await port.newFight({ scenario: 'walls_door_ui.json' });
    svc.bump();                                                     // another tab stepped
    const r = await port.step();
    assert(!r.ok && r.status === 409 && !r.messages, 'refused, nothing revealed');
    assert(port.revision === 1, 'resynced to the service');
    assert((await port.step()).ok, 'the next step works');
  });

  await test('the simulator port never answers call() (no rules resolved locally)', async () => {
    const port = createSimServicePort({ fetch: fakeService().fetch });
    assert(port.call({ op: 'command' }).ok === false, 'refused');
  });
  return results;
}
