// Tests for dist/stage-view.mjs (the Stage page's view of the simulator service). Browser runner: tests/replay_tests.html.
import { fmt, liveElapsed, cue, tableNames, createStagePort } from './dist/stage-view.mjs';

function assert(cond, text) { if (!cond) throw new Error('FAILED: ' + text); }

export function run() {
  const results = [];
  const test = (name, fn) => { try { fn(); results.push([name, true, '']); } catch (e) { results.push([name, false, e.message]); } };

  test('stage: times read m:ss like the simulator', () => {
    assert(fmt(0) === '0:00' && fmt(30) === '0:30' && fmt(90.4) === '1:30' && fmt(3600) === '60:00' && fmt(-5) === '0:00', 'fmt');
  });

  test('stage: the clock runs on screen only while the spotlight runs', () => {
    const v = { holder: 'Ann', running: true, elapsed: 30, discussion: false };
    assert(liveElapsed(v, 1000, 6000) === 35, 'running adds the time since the fetch');
    assert(liveElapsed({ ...v, running: false }, 1000, 60000) === 30, 'paused holds');
    assert(liveElapsed({ holder: null, elapsed: 0 }, 0, 9999) === 0, 'no holder');
  });

  test('stage: the banner shows ON AIR, Dialogue and pause from the service view', () => {
    const v = { holder: 'Ann', running: true, elapsed: 30, discussion: false };
    const a = cue(v, 0, 0);
    assert(a.label === 'ON AIR' && a.line === 'Ann · Spotlight - please listen' && a.time === '0:30' && !a.discussion, 'on air');
    const d = cue({ ...v, discussion: true }, 0, 0);
    assert(d.label === 'Dialogue' && d.line === "Ann's spotlight · join in character" && d.discussion, 'dialogue');
    assert(cue({ ...v, running: false }, 0, 0).time === '0:30 (paused)', 'paused');
    assert(cue({ holder: null }, 0, 0) === null, 'nobody');
  });

  test('stage: names offered come from the Stage and the seats, never the GM, once each', () => {
    const v = { participants: [{ name: 'Ann', stage: true }, { name: 'bob', stage: false }] };
    const names = tableNames(v, ['Bob', 'GM', 'Cid', 'ann']);
    assert(JSON.stringify(names) === JSON.stringify(['Ann', 'bob', 'Cid']), JSON.stringify(names));
  });
  return results;
}

export async function runAsync() {
  const results = [];
  const test = async (name, fn) => { try { await fn(); results.push([name, true, '']); } catch (e) { results.push([name, false, e.message]); } };

  await test('stage: the port says hello, then sends the token, the seat and a fresh id with every command', async () => {
    const sent = [];
    const fake = async (path, init) => {
      if (!init) return { ok: true, json: async () => ({ ok: true, token: 'T' }) };
      const body = JSON.parse(init.body);
      sent.push([path, body]);
      if (path === '/api/stage/state') return { ok: false, status: 403, json: async () => ({ ok: false, error: 'Invalid session token' }) };
      return { ok: true, json: async () => ({ ok: true, public: 'x', stage: { holder: null } }) };
    };
    const port = createStagePort({ fetch: fake });
    await port.hello();
    await port.command('Ann', { op: 'join' });
    await port.command('Ann', { op: 'join' });
    const [p1, b1] = sent[0], [, b2] = sent[1];
    assert(p1 === '/api/stage' && b1.token === 'T' && b1.seat === 'Ann' && b1.cmd.op === 'join', 'command body');
    assert(b1.cmd.id && b2.cmd.id && b1.cmd.id !== b2.cmd.id, 'a new id for each click');
    const st = await port.state('GM');
    assert(st.ok === false && st.status === 403 && st.error.includes('token'), 'refusals come back as errors');
  });
  return results;
}
