// RULES-MONITOR-01 (GM 2026-10-28: "Watch every action"): the GM's Rules monitor in Play live. LM Studio reads every
// action of the live fight beside play (Mythastria sim/rules_monitor.py, POST /api/rules/monitor) and says whether the
// engine followed the SRD 5.2.1 rules, with what should have happened when it thinks not. It never changes a result
// and the players never see it. GM: "If lm studio doesn't find a resolution, I'll ask claude to fix it": every action
// has Copy for Claude (the log lines, the SRD text, the monitor's comment).
import { api } from './server.mjs';

const LABEL = { ok: 'OK', question: 'Doubtful', break: 'Rule break' };

function port(fetchFn) {
  let token = null;
  async function post(body, retry = true) {
    if (!token) token = (await (await fetchFn(api('/api/hello'))).json()).token ?? null;
    const res = await fetchFn(api('/api/rules/monitor'), { method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ ...body, token }) });
    const out = await res.json().catch(() => ({ ok: false, error: 'The service sent no answer.' }));
    if (res.status === 403 && retry && /token/i.test(out.error || '')) { token = null; return post(body, false); }
    if (res.status === 404) out.error = 'Restart Mythastria (the Desktop Start_Mythastria.bat) to get the Rules monitor.';
    return res.ok ? out : { ...out, ok: false };
  }
  return { post };
}

// What Copy for Claude puts on the clipboard: everything Claude needs to look at the action
export function forClaude(r) {
  return [`Mythastria Rules monitor, action ${r.n} (${r.when}): ${r.actor}, ${r.action}`,
    `LM Studio's verdict: ${LABEL[r.verdict] ?? r.verdict}. ${r.comment}`,
    r.resolution ? `Its resolution: ${r.resolution}` : 'It found no resolution.',
    r.quote ? `It relied on: "${r.quote}"${r.quote_found === false ? ' (not found in the SRD text it was sent)' : ''}` : '',
    '', 'Fight log:', ...r.lines, '',
    ...(r.srd ?? []).flatMap(t => [`SRD 5.2.1, ${t.name}:`, t.text, '']),
    'Please check this against SRD 5.2.1 and fix the engine if it is wrong.'].filter(l => l !== null).join('\n');
}

export function mountMonitor({ document: doc = globalThis.document, button, status = () => {}, fetch: fetchFn = globalThis.fetch, every = 2500 }) {
  const make = (tag, text, cls, attrs = {}) => {
    const e = doc.createElement(tag);
    if (text != null) e.textContent = text;
    if (cls) e.className = cls;
    for (const [k, v] of Object.entries(attrs)) if (v != null && v !== false) e.setAttribute(k, v === true ? '' : v);
    return e;
  };
  const dialog = make('dialog', null, 'monitor-dialog', { id: 'monitor-dialog', 'aria-labelledby': 'monitor-title' });
  doc.body.append(dialog);
  const api_ = port(fetchFn);
  let state = null, model = null, seen = 0, drawn = '', showOk = false, error = '';

  async function act(body) {
    const out = await api_.post(body).catch(() => ({ ok: false, error: 'The simulator service stopped.' }));
    if (out.ok) { state = out; error = ''; } else error = out.error || 'Refused.';
    badge(); draw(true);
    return out;
  }
  function badge() {
    const fresh = state ? state.results.filter(r => r.verdict !== 'ok' && r.n > seen).length : 0;
    button.replaceChildren('Rules monitor…');
    if (fresh) button.append(make('span', String(fresh), 'monitor-count'));
    button.title = state?.on ? `LM Studio is watching every action: ${state.flags} flagged of ${state.checked} checked.` : 'Rules monitor: off. LM Studio watches every action and flags rule breaks (GM only).';
    button.setAttribute('aria-pressed', String(!!state?.on));
  }
  function item(r) {
    const li = make('li', null, 'monitor-item ' + r.verdict);
    const head = make('div', null, 'monitor-head');
    head.append(make('span', LABEL[r.verdict] ?? r.verdict, 'monitor-tag ' + r.verdict), make('strong', `${r.actor}: ${r.action}`), make('span', r.when, 'monitor-when'));
    li.append(head, make('p', r.comment));
    if (r.unbacked) li.append(make('p', 'LM Studio called it a rule break but quoted no SRD words that back it: likely a false alarm.', 'monitor-quote'));
    if (r.resolution) li.append(make('p', 'Should be: ' + r.resolution, 'monitor-fix'));
    if (r.quote) li.append(make('p', `“${r.quote}”` + (r.quote_found === false ? ' (not found in the SRD text: the model may have made it up)' : ''), 'monitor-quote'));
    const det = make('details');
    det.append(make('summary', `The log (${r.lines.length} lines)`), make('pre', r.lines.join('\n')));
    const copy = make('button', 'Copy for Claude', 'quiet', { type: 'button', title: 'Copy the action, the SRD text and this comment, to paste into a Claude session' });
    copy.addEventListener('click', async () => {
      try { await navigator.clipboard.writeText(forClaude(r)); copy.textContent = 'Copied'; }
      catch { copy.textContent = 'Copy refused by the browser'; }
      setTimeout(() => { copy.textContent = 'Copy for Claude'; }, 2000);
    });
    const row = make('div', null, 'row');
    row.append(copy);
    li.append(det, row);
    return li;
  }
  function draw(force = false) {
    if (!dialog.open || !state) return;
    const key = JSON.stringify([state.rev, showOk, error, model?.ready]);
    if (!force && key === drawn) return;
    drawn = key;
    const top = make('div', null, 'row');
    const toggle = make('button', state.on ? 'Turn off' : 'Turn on', state.on ? 'quiet' : '', { type: 'button' });
    toggle.addEventListener('click', () => act({ op: state.on ? 'off' : 'on' }));
    const clear = make('button', 'Clear', 'quiet', { type: 'button', title: 'Forget the results shown' });
    clear.addEventListener('click', () => act({ op: 'clear' }));
    const okBox = make('label', null, 'monitor-ok');
    const cb = make('input', null, null, { type: 'checkbox' }); cb.checked = showOk;
    cb.addEventListener('change', () => { showOk = cb.checked; draw(true); });
    okBox.append(cb, ' Show the OK ones too');
    const close = make('button', 'Close', 'quiet', { type: 'button' });
    close.addEventListener('click', () => dialog.close());
    top.append(toggle, clear, okBox, close);
    const line = state.on
      ? `${state.status === 'watching' ? 'Watching' : state.status[0].toUpperCase() + state.status.slice(1)}… ${state.checked} checked, ${state.flags} flagged`
        + (state.waiting ? `, ${state.waiting} waiting` : '') + (state.skipped ? `, ${state.skipped} skipped (LM Studio fell behind)` : '') + '.'
      : 'Off. Turn it on and LM Studio reads every action of the live fight, a few seconds behind play.';
    const info = [make('p', line, 'note')];
    if (model && !model.ready) info.push(make('p', model.why || 'LM Studio is not ready.', 'error'));
    if (state.error) info.push(make('p', 'Last check failed: ' + state.error, 'error'));
    if (error) info.push(make('p', error, 'error'));
    const rows = state.results.filter(r => showOk || r.verdict !== 'ok');
    const list = make('ul', null, 'monitor-list');
    list.append(...rows.map(item));
    if (!rows.length) list.append(make('li', state.results.length ? 'Nothing flagged.' : 'No actions checked yet.', 'note'));
    dialog.replaceChildren(make('h2', 'Rules monitor', null, { id: 'monitor-title' }), top, ...info, list,
      make('p', 'GM only. LM Studio gives a second opinion beside the Referee; it never changes a result. When it finds no resolution, Copy for Claude.', 'note'));
    if (state.results.length) seen = Math.max(seen, state.results[0].n);
    badge();
  }
  async function refresh() {
    const out = await api_.post({ op: 'state' }).catch(() => null);
    if (out?.ok) {
      const before = state ? state.flags : 0;
      state = out; badge();
      if (state.flags > before && !dialog.open) status(`Rules monitor: ${state.flags - before} new flag${state.flags - before === 1 ? '' : 's'} (Rules monitor…).`);
      draw();
    }
  }
  button.addEventListener('click', async () => {
    if (!dialog.open) dialog.show();
    model = (await api_.post({ op: 'model' }).catch(() => null)) ?? { ready: false, why: 'The service stopped.' };
    await refresh(); draw(true);
  });
  refresh();
  setInterval(refresh, every);
}
