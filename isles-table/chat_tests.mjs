// Tests for dist/table-chat.mjs (the chat window asks the simulator service; it never rolls or filters itself).
// Browser runner: tests/replay_tests.html.
import { buildExpr, modeLabel, describe, createChatPort } from './dist/table-chat.mjs';

function assert(cond, text) { if (!cond) throw new Error('FAILED: ' + text); }

export function run() {
  const results = [];
  const test = (name, fn) => { try { fn(); results.push([name, true, '']); } catch (e) { results.push([name, false, e.message]); } };

  test('chat: dice buttons ask for count, die and modifier', () => {
    assert(buildExpr(1, 20, 0) === '1d20', '1d20');
    assert(buildExpr(2, 6, 3) === '2d6+3', '2d6+3');
    assert(buildExpr(1, 8, -1) === '1d8-1', '1d8-1');
    assert(buildExpr('', 4, 'x') === '1d4', 'empty fields');
    assert(buildExpr(500, 6, 0) === '100d6', 'at most 100 dice');
  });

  test('chat: advantage and disadvantage only change a single d20', () => {
    assert(buildExpr(1, 20, 5, 'advantage') === '2d20kh1+5', 'advantage');
    assert(buildExpr(1, 20, 0, 'disadvantage') === '2d20kl1', 'disadvantage');
    assert(buildExpr(2, 20, 0, 'advantage') === '2d20', 'two d20s');
    assert(modeLabel(20, 1, 'advantage', ' Stealth ') === 'Stealth, advantage', 'label');
    assert(modeLabel(6, 1, 'advantage', '') === '', 'other dice');
  });

  test('chat: lines show who, the outcome and privacy as the service sent them', () => {
    const roll = describe({ n: 1, kind: 'roll', from: 'Hero 2', text: 'Hero 2 rolls 1d20: [20] = 20', total: 20, natural: 20 });
    assert(roll.total === 20 && roll.cls === 'roll nat20' && roll.tag === '', 'a public roll');
    const gm = describe({ n: 2, kind: 'gmroll', from: 'Hero 3', text: 'Hero 3 rolls 1d6: [3] = 3', total: 3, natural: null });
    assert(gm.total === 3 && gm.tag === 'GM only', 'the GM sees a private roll');
    const hidden = describe({ n: 3, kind: 'gmroll', from: 'Hero 3', text: 'Hero 3 rolls 1d6 privately for the GM.', hidden: true });
    assert(hidden.total === null && hidden.cls === 'gmroll hidden' && hidden.tag === 'private roll', 'the roller sees no result');
    const m = describe({ n: 4, kind: 'music', from: 'Hero 2', url: 'https://youtu.be/x', site: 'YouTube', caption: '', text: 'https://youtu.be/x' });
    assert(m.who === 'Hero 2' && m.tag === 'YouTube' && m.text === 'https://youtu.be/x' && m.url === 'https://youtu.be/x', 'a music link (CHAT-FUN-01)');
    const p = describe({ n: 5, kind: 'picture', from: 'Hero 3', url: '/chat-media/x.gif', caption: 'ha', text: 'ha' });
    assert(p.text === 'ha' && p.url === '/chat-media/x.gif' && p.cls === 'picture', 'a shared picture');
  });
  return results;
}

export async function runAsync() {
  const results = [];
  const test = async (name, fn) => { try { await fn(); results.push([name, true, '']); } catch (e) { results.push([name, false, e.message]); } };

  await test('chat: the page sends lines and rolls with the seat and token; the service answers', async () => {
    const sent = [];
    const fake = async (path, init) => {
      if (!init) return { ok: true, json: async () => ({ ok: true, token: 'T' }) };
      sent.push([path, JSON.parse(init.body)]);
      if (path === '/api/roll') return { ok: false, status: 400, json: async () => ({ ok: false, error: 'Dice: cannot read' }) };
      return { ok: true, json: async () => ({ ok: true, chat: [] }) };
    };
    const port = createChatPort({ fetch: fake });
    await port.hello();
    await port.say('Hero 2', 'hi all');
    const out = await port.roll('Hero 3', '2d6+fire', 'x', true);
    assert(out.ok === false && out.status === 400, 'refusal');
    assert(sent[0][0] === '/api/chat' && sent[0][1].text === 'hi all' && sent[0][1].token === 'T', 'chat body');
    assert(sent[1][0] === '/api/roll' && sent[1][1].private === true && sent[1][1].seat === 'Hero 3', 'roll body');
    assert((await port.log('GM')).ok && sent[2][0] === '/api/chat/log', 'log');
  });

  await test('chat: after the service restarts, the page takes the new token and tries once more', async () => {
    const tokens = ['OLD', 'NEW'], sent = [];
    const fake = async (path, init) => {
      if (!init) { const t = tokens.shift(); return { ok: true, json: async () => ({ ok: true, token: t }) }; }
      const body = JSON.parse(init.body);
      sent.push(body.token);
      if (body.token !== 'NEW') return { ok: false, status: 403, json: async () => ({ ok: false, error: 'Invalid session token; reload the page.' }) };
      return { ok: true, json: async () => ({ ok: true, chat: [] }) };
    };
    const port = createChatPort({ fetch: fake });
    await port.hello();
    const out = await port.say('Hero 2', 'hi');
    assert(out.ok && JSON.stringify(sent) === '["OLD","NEW"]', JSON.stringify(sent));
    const never = createChatPort({ fetch: async (p, init) => init ? { ok: false, status: 403, json: async () => ({ ok: false, error: 'Invalid session token' }) } : { ok: true, json: async () => ({ ok: true, token: 'X' }) } });
    assert((await never.say('Hero 2', 'hi')).status === 403, 'one retry, no loop');
  });
  return results;
}
