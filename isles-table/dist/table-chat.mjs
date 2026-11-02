import { SERVER, asset } from './server.mjs';                  // PLAYER-SITE-01: the GM's Mythastria, and its pictures
import { createDiceTower } from './dice-tower.mjs';   // DICE-TOWER-01 (GM 2026-10-20)
import { seatPart, loadSeat } from './seat-ticket.mjs';   // JOIN-01: a seated player's ticket on the players' door
// TABLE-CHAT-01 + DICE-TOOL-01 (GM 2026-10-19: a dice tool for rolls outside the mechanics; "a small chat window for text
// messages, output all dice rolls with outcomes and the player making the rolls ... a private roll only seen by the
// GM"). A floating chat for any Isles Table page served by the simulator service (Mythastria tools/sim_service.py).
// The service rolls (secure dice) and decides what each seat sees (sim/table_chat.py); this page only sends and shows.
// Free rolls never change the fight.
// CHAT-FUN-01 (GM 2026-10-21: "private messages are unnecessary ... Let's use chat for fun stuff like gifs, sharing
// music"): no whispers; a picture or music link typed in the line is shared, and a picture or sound from the PC is sent
// to the service, which checks and keeps it. Pictures show scaled down (a click opens them full size); music links are
// cards with an Open button; sounds use the browser's own player. Nothing plays or opens by itself.
// CHAT-MODEL-01 (GM 2026-11-01: "make sure chat allows you to load an llm"): the Model section, on the GM's screen only: a
// local server and model to load, and a talk with it that stays out of the table chat (sim/chat_model.py).

export const SIDES = [4, 6, 8, 10, 12, 20, 100];
export const HINT = 'Message · paste a .gif or music link to share · /r 1d20+5 Stealth · /gmr 1d20 (GM only) · /help';
export const PICTURE_MAX = 5 * 1024 * 1024, AUDIO_MAX = 20 * 1024 * 1024;     // the service's limits, checked here first

// CHAT-FUN-01: a file chosen on the PC, before it is sent: 'picture', 'audio', or an error the person can act on.
export function fileCheck(file) {
  const type = String(file?.type || ''), size = Number(file?.size) || 0;
  const kind = /^image\/(gif|png|jpeg|webp)$/.test(type) ? 'picture' : /^audio\/(mpeg|mp3|ogg|wav|x-wav|wave|vnd\.wave)$/.test(type) ? 'audio' : null;
  if (!kind) return { error: 'Share a picture (GIF, PNG, JPEG, WebP) or a sound (MP3, Ogg, WAV).' };
  const max = kind === 'picture' ? PICTURE_MAX : AUDIO_MAX;
  if (size > max) return { error: `A ${kind === 'picture' ? 'picture' : 'sound file'} can be ${max / 1024 / 1024} MB at most.` };
  return { kind };
}

// The roll a dice button asks for: count, die and modifier; advantage/disadvantage only for a single d20.
export function buildExpr(count, sides, mod, mode = 'normal') {
  const n = Math.min(100, Math.max(1, Math.trunc(Number(count)) || 1));
  const m = Math.trunc(Number(mod)) || 0;
  let dice = `${n}d${sides}`;
  if (sides === 20 && n === 1 && mode === 'advantage') dice = '2d20kh1';
  if (sides === 20 && n === 1 && mode === 'disadvantage') dice = '2d20kl1';
  return dice + (m > 0 ? `+${m}` : m < 0 ? `${m}` : '');
}

export function modeLabel(sides, count, mode, label) {
  const extra = sides === 20 && Number(count) === 1 && mode !== 'normal' ? mode : '';
  return [label.trim(), extra].filter(Boolean).join(', ');
}

// DICE-POOL-01 (GM 2026-10-21: "make the dice roller allow you to mix dice and add fixed bonuses and a roll button"):
// a click on a die adds it to the pool ("2d6 + 1d8"), which can also be typed; Roll sends the pool and the bonus. The
// service checks and rolls (sim/dice_tool.py); a shift-click still rolls one die at once (the old quick roll).
const SIMPLE_DICE = /^(\d*)d(\d+)$/i;
export function addDie(pool, sides) {
  const text = String(pool ?? '').trim(), terms = text.replace(/\s+/g, '').split('+').filter(Boolean);
  if (!terms.every(t => SIMPLE_DICE.test(t))) return `${text} + 1d${sides}`;     // something typed by hand: add at the end
  const counts = new Map();
  for (const t of [...terms, `1d${sides}`]) {
    const [, n, s] = SIMPLE_DICE.exec(t);
    counts.set(Number(s), (counts.get(Number(s)) || 0) + (Number(n) || 1));
  }
  return [...counts].map(([s, n]) => `${n}d${s}`).join(' + ');
}

const ONE_D20 = /^1?d20(?=[+-]|$)/i;                          // the pool is a single d20 (and maybe a typed bonus)
export function poolExpr(pool, bonus, mode = 'normal') {
  let dice = String(pool ?? '').trim();
  const flat = dice.replace(/\s+/g, '');
  if (ONE_D20.test(flat) && !/d/i.test(flat.replace(ONE_D20, '')) && mode !== 'normal')
    dice = flat.replace(ONE_D20, mode === 'advantage' ? '2d20kh1' : '2d20kl1');
  const b = Math.trunc(Number(bonus)) || 0;
  return dice + (b > 0 ? ` + ${b}` : b < 0 ? ` - ${-b}` : '');
}

export function poolLabel(pool, mode, label) {
  const flat = String(pool ?? '').replace(/\s+/g, '');
  const one = ONE_D20.test(flat) && !/d/i.test(flat.replace(ONE_D20, ''));
  return [String(label ?? '').trim(), one && mode !== 'normal' ? mode : ''].filter(Boolean).join(', ');
}

// One chat line as this seat shows it (the service already removed what the seat may not see).
export function describe(entry) {
  const base = { n: entry.n, who: entry.from, text: entry.text, total: null, cls: entry.kind, tag: '' };
  if (entry.kind === 'picture' || entry.kind === 'audio')        // CHAT-FUN-01: shared for fun; the text is the caption
    return { ...base, text: entry.caption || (entry.kind === 'audio' ? entry.name || 'a sound' : ''), url: asset(entry.url) };
  if (entry.kind === 'music') return { ...base, text: entry.caption || entry.url, url: entry.url, tag: entry.site || 'Music' };
  if (entry.kind === 'roll' || (entry.kind === 'gmroll' && !entry.hidden)) {
    const nat = entry.natural === 20 ? ' nat20' : entry.natural === 1 ? ' nat1' : '';
    return { ...base, total: entry.total, cls: entry.kind + nat, tag: entry.kind === 'gmroll' ? 'GM only' : '' };
  }
  if (entry.kind === 'gmroll') return { ...base, cls: 'gmroll hidden', tag: 'private roll' };
  return base;
}

export function createChatPort({ fetch: fetchFn = globalThis.fetch, base = SERVER } = {}) {
  let token = null;
  async function hello() {
    const res = await fetchFn(base + '/api/hello');
    const out = await res.json();
    if (res.ok && out.ok) token = out.token;
    return out;
  }
  const post = async (path, body, retry = true) => {
    const res = await fetchFn(base + path, { method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ ...body, token, ...seatPart() }) });
    let out;
    try { out = await res.json(); } catch { out = { ok: false, error: 'The service sent no answer.' }; }
    if (res.status === 403 && retry && /token/i.test(out.error || '')) {   // the service restarted: a new token, once
      await hello().catch(() => null);
      return post(path, body, false);
    }
    return res.ok ? out : { ok: false, status: res.status, error: out.error || `HTTP ${res.status}` };
  };
  return {
    hello,
    say: (seat, text) => post('/api/chat', { seat, text }),
    roll: (seat, expr, label, priv = false) => post('/api/roll', { seat, expr, label, private: priv }),
    log: seat => post('/api/chat/log', { seat }),
    share: (seat, name, data, caption = '') => post('/api/chat/share', { seat, name, data, caption }),   // CHAT-FUN-01
    model: body => post('/api/chat/model', body),                  // CHAT-MODEL-01: the GM door only
    isGM: () => !!token,                                           // the players' door never hands out the token
  };
}

// ------------------------------------------------------------------ the window (mounted on load)
const NAME_KEY = 'isles-chat-name';
const CSS = `
#chat-fab{position:fixed;right:16px;bottom:16px;z-index:50;font:600 15px/1 Georgia,serif;padding:.7rem 1rem;border-radius:999px;
 background:#2a2419;color:#f1e6cc;border:1px solid #c9a35a;box-shadow:0 4px 14px rgba(0,0,0,.45);cursor:pointer}
#chat-fab[aria-expanded="true"]{background:#c9a35a;color:#1b1710}
#chat-fab .chat-unread{display:inline-block;min-width:1.3em;margin-left:.4rem;padding:.1rem .35rem;border-radius:999px;background:#b8402f;color:#fff;font-size:.8rem}
#chat-win{position:fixed;right:16px;bottom:72px;z-index:50;width:min(380px,calc(100vw - 32px));height:min(600px,calc(100vh - 96px));
 display:flex;flex-direction:column;background:#1f201d;color:#e8e2d4;border:1px solid #3a3a36;border-radius:10px;
 box-shadow:0 10px 30px rgba(0,0,0,.5);font:14px/1.4 Georgia,serif;overflow:hidden}
#chat-win[hidden]{display:none}
#chat-win .cw-head{display:flex;gap:.5rem;align-items:center;padding:.5rem .7rem;border-bottom:1px solid #3a3a36}
#chat-win .cw-head strong{letter-spacing:.12em;font-size:.8rem;color:#9a9384;margin-right:auto}
#chat-win button,#chat-win input,#chat-win select{background:#151614;color:#e8e2d4;border:1px solid #3a3a36;border-radius:4px;padding:.3rem .45rem;font:inherit}
#chat-win button{cursor:pointer}#chat-win button:hover{border-color:#c9a35a}
#chat-win .cw-log{flex:1;min-height:0;overflow:auto;list-style:none;margin:0;padding:.4rem .7rem}
#chat-win .cw-log li{padding:.3rem 0;border-bottom:1px solid #2a2a27;word-break:break-word}
#chat-win .cw-who{font-weight:700;color:#c9a35a;margin-right:.35rem}
#chat-win .cw-tag{font-size:.75rem;color:#1b1710;background:#9a9384;border-radius:3px;padding:0 .3rem;margin-right:.35rem}
#chat-win .cw-pic{display:block;margin-top:.3rem;width:fit-content;max-width:100%}
#chat-win .cw-pic img{display:block;max-width:100%;max-height:220px;border-radius:6px;border:1px solid #3a3a36;cursor:zoom-in}
#chat-win .cw-card{display:flex;gap:.5rem;align-items:center;margin-top:.3rem;padding:.4rem .5rem;border:1px solid #3a3a36;border-radius:6px;background:#151614}
#chat-win .cw-card .cw-title{flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
#chat-win .cw-open{color:#1b1710;background:#c9a35a;border-radius:4px;padding:.2rem .6rem;text-decoration:none;font-weight:700}
#chat-win .music .cw-tag{background:#7fa6c9}#chat-win audio{display:block;width:100%;margin-top:.3rem}
#chat-win .cw-share{display:flex;gap:.4rem;align-items:center;padding:0 .7rem .5rem}#chat-win .cw-share .cw-tip{margin:0}
#chat-win .gmroll .cw-tag{background:#c9a35a}#chat-win .hidden{color:#9a9384;font-style:italic}
#chat-win .cw-total{display:inline-block;min-width:2.2rem;text-align:center;font:700 1.1rem/1.2 ui-monospace,monospace;color:#c9a35a;
 border:1px solid #3a3a36;border-radius:4px;margin-right:.4rem;padding:0 .25rem}
#chat-win .nat20 .cw-total{color:#7fd08a;border-color:#7fd08a}#chat-win .nat1 .cw-total{color:#e07a6a;border-color:#e07a6a}
#chat-win .cw-line{display:flex;gap:.4rem;padding:.5rem .7rem;border-top:1px solid #3a3a36}
#chat-win .cw-line input{flex:1;min-width:0}
#chat-win .cw-note{min-height:1.3em;padding:0 .7rem;font-size:.8rem;color:#9a9384}#chat-win .cw-note.error{color:#e07a6a}
#chat-win details{border-top:1px solid #3a3a36;padding:.4rem .7rem .6rem}
#chat-win summary{cursor:pointer;color:#9a9384;letter-spacing:.1em;font-size:.8rem}
#chat-win .cw-row{display:flex;flex-wrap:wrap;gap:.35rem;align-items:center;margin-top:.4rem}
#chat-win .cw-die{min-width:2.9rem;font-weight:600}#chat-win .cw-num{width:3.6rem}#chat-win .cw-grow{flex:1;min-width:6rem}
#chat-win .cw-roll{flex:1;font-weight:700;letter-spacing:.08em;background:#c9a35a;color:#1b1710;border-color:#c9a35a}
#chat-win .cw-roll:hover{background:#dcb76c}#chat-win .cw-tip{margin:.35rem 0 0;font-size:.75rem;color:#9a9384}
#chat-win .cw-tip.error{color:#e07a6a}#chat-win .cw-talk{flex:none;max-height:190px;min-height:0;padding:0;margin-top:.35rem}
#chat-win select{background-repeat:no-repeat;background-position:right .45rem center;padding-right:1.4rem;text-overflow:ellipsis}
#chat-win #cw-model select{min-width:0;flex:1 1 7rem}#chat-win #cw-talk:empty{display:none}
`;

function el(tag, attrs = {}, text) {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, v);
  if (text !== undefined) e.textContent = text;
  return e;
}

export async function mountTableChat(doc = document) {
  const port = createChatPort();
  let online = false;
  try { online = !!(await port.hello())?.ok; } catch { online = false; }

  const style = el('style'); style.textContent = CSS; doc.head.append(style);
  const fab = el('button', { id: 'chat-fab', 'aria-expanded': 'false', 'aria-controls': 'chat-win', title: 'Chat and dice' }, 'Chat');
  const unread = el('span', { class: 'chat-unread', hidden: '' });
  fab.append(unread);
  const win = el('section', { id: 'chat-win', 'aria-label': 'Table chat', hidden: '' });
  win.innerHTML = `<div class="cw-head"><strong>TABLE CHAT</strong><label id="cw-who-row">As <input id="cw-who" maxlength="40" size="10"></label></div>
   <div class="cw-line"><input id="cw-text" maxlength="500" aria-label="Message"><button id="cw-send">Send</button></div>
   <p class="cw-note" id="cw-note" role="status"></p>
   <div class="cw-share"><button id="cw-file-btn" title="A picture (5 MB) or a sound (20 MB) from this PC, for everyone">Add picture or sound…</button>
    <input id="cw-file" type="file" accept="image/gif,image/png,image/jpeg,image/webp,audio/mpeg,audio/ogg,audio/wav,.mp3,.ogg,.wav" hidden>
    <span class="cw-tip">Text in the message box becomes its caption</span></div>
   <ul class="cw-log" id="cw-log" aria-live="polite"></ul>
   <details id="cw-dice" open><summary>DICE · OUTSIDE THE MECHANICS</summary>
    <div class="cw-row" id="cw-dice-row"></div>
    <div class="cw-row"><input id="cw-pool" class="cw-grow" maxlength="60" placeholder="Click dice or type 2d6 + 1d8" aria-label="Dice to roll">
     <label title="A fixed bonus (or a penalty with -), -100 to +100">Bonus <input id="cw-mod" class="cw-num" type="number" min="-100" max="100" value="0"></label></div>
    <div class="cw-row"><select id="cw-mode" aria-label="d20 mode" title="Advantage or disadvantage when the roll is one d20"><option value="normal">Normal</option><option value="advantage">Advantage</option><option value="disadvantage">Disadvantage</option></select>
     <button id="cw-roll" class="cw-roll">Roll</button><button id="cw-clear" title="Empty the dice and the bonus">Clear</button></div>
    <div class="cw-row"><input id="cw-label" class="cw-grow" maxlength="60" placeholder="What for? (optional)" aria-label="What the roll is for">
     <label title="Only the GM sees the result"><input id="cw-private" type="checkbox"> Private to GM</label></div>
    <p class="cw-tip">Click a die to add it · Shift-click rolls just that die · Enter rolls</p>
   </details>
   <details id="cw-model" hidden><summary>MODEL · GM ONLY</summary>
    <div class="cw-row"><select id="cw-model-server" aria-label="Model server"></select><select id="cw-model-name" aria-label="Model"></select>
     <button id="cw-model-load" title="Load this model. The Rules monitor uses it too.">Load</button></div>
    <p class="cw-tip" id="cw-model-state" role="status"></p>
    <ul class="cw-log cw-talk" id="cw-talk" aria-live="polite"></ul>
    <div class="cw-row"><input id="cw-ask" class="cw-grow" maxlength="1000" placeholder="Ask the loaded model" aria-label="Ask the loaded model">
     <button id="cw-ask-send">Ask</button><button id="cw-talk-clear" title="Empty this talk">Clear</button></div>
    <p class="cw-tip">Only you see this. It stays on this PC and changes nothing in a fight.</p>
   </details>`;
  doc.body.append(fab, win);
  const $ = id => win.querySelector('#' + id);
  $('cw-text').placeholder = HINT;
  for (const s of SIDES) $('cw-dice-row').append(el('button', { class: 'cw-die', 'data-sides': String(s), title: `Add a d${s} (shift-click: roll one now)` }, `d${s}`));

  const pageSeat = doc.getElementById('seat');                  // the Stage page's seat picker, when there is one
  if (pageSeat) $('cw-who-row').hidden = true;
  try { $('cw-who').value = localStorage.getItem(NAME_KEY) || 'GM'; } catch { $('cw-who').value = 'GM'; }
  const seated = loadSeat();                                    // JOIN-01: the service speaks as the seat anyway
  if (seated) { $('cw-who').value = seated.name; $('cw-who-row').hidden = true; }
  const who = () => (pageSeat ? pageSeat.value : $('cw-who').value.trim()) || 'GM';

  let newest = 0, seenWhileOpen = 0, shownSeat = '', primed = false, tower = null;   // DICE-TOWER-01: primed after the first list
  const note = (text, isError = false) => { $('cw-note').textContent = text || ''; $('cw-note').className = 'cw-note' + (isError ? ' error' : ''); };

  function line(e) {
    const d = describe(e), li = el('li', { class: d.cls });
    if (d.total !== null) li.append(el('span', { class: 'cw-total' }, String(d.total)));
    if (d.tag && e.kind !== 'music') li.append(el('span', { class: 'cw-tag' }, d.tag));
    if (['say', 'picture', 'music', 'audio'].includes(e.kind)) li.append(el('span', { class: 'cw-who' }, d.who));
    if (e.kind === 'music') {                                   // CHAT-FUN-01: a card; the link opens only on a click
      const card = el('div', { class: 'cw-card' });
      card.append(el('span', { class: 'cw-tag' }, d.tag), el('span', { class: 'cw-title', title: d.url }, d.text),
        el('a', { class: 'cw-open', href: d.url, target: '_blank', rel: 'noopener noreferrer' }, 'Open'));
      li.append(card);
      return li;
    }
    if (d.text) li.append(document.createTextNode(d.text));
    if (e.kind === 'picture') {                                 // scaled to fit; a click opens it full size in a new tab
      const a = el('a', { class: 'cw-pic', href: d.url, target: '_blank', rel: 'noopener noreferrer', title: 'Open full size' });
      const img = el('img', { src: d.url, alt: d.text || 'a shared picture', loading: 'lazy', referrerpolicy: 'no-referrer' });
      img.addEventListener('load', () => {                      // keep the newest line in view once the picture has a size
        const log = $('cw-log');
        if (log.scrollTop < img.clientHeight + 60) log.scrollTop = 0;
      });
      a.append(img);
      li.append(a);
    }
    if (e.kind === 'audio') li.append(el('audio', { controls: '', preload: 'none', src: d.url }));   // never autoplays
    return li;
  }

  const lines = new Map();                                      // CHAT-FUN-01: n -> its line, kept so a playing sound
  function show(chat) {                                         // or a loaded picture is not rebuilt at every poll
    const top = chat.length ? chat[chat.length - 1].n : 0;
    if (top < newest && who() === shownSeat) return;           // a slower, older answer: keep the newer list
    const log = $('cw-log'), atTop = log.scrollTop < 40;       // GM 2026-11-01: new posts stay on top
    if (who() !== shownSeat) { lines.clear(); log.replaceChildren(); }
    const keep = new Set(chat.map(e => e.n));
    for (const [n, li] of lines) if (!keep.has(n)) { li.remove(); lines.delete(n); }
    for (const e of chat) if (!lines.has(e.n)) { const li = line(e); lines.set(e.n, li); log.prepend(li); }
    if (atTop || who() !== shownSeat) log.scrollTop = 0;
    if (primed && who() === shownSeat)                      // DICE-TOWER-01: new rolls tumble down the tower (not the history)
      for (const e of chat) if (e.n > newest && (e.kind === 'roll' || e.kind === 'gmroll')) (tower ??= createDiceTower()).show(e);
    primed = true;
    newest = top; shownSeat = who();
    if (!win.hidden) seenWhileOpen = newest;
    const count = chat.filter(e => e.n > seenWhileOpen).length;
    unread.hidden = !win.hidden || !count;
    unread.textContent = String(count);
  }

  async function act(promise) {
    if (!online) { note('The chat needs the simulator service: start Start_Mythastria.bat.', true); return false; }
    const out = await promise().catch(() => ({ ok: false, error: 'The simulator service stopped.' }));
    if (!out.ok) { note(out.error, true); return false; }
    note(out.answer || '');
    show(out.chat);
    return true;
  }
  const send = async () => { const text = $('cw-text').value; if (await act(() => port.say(who(), text))) $('cw-text').value = ''; };

  $('cw-send').addEventListener('click', send);
  $('cw-text').addEventListener('keydown', e => { if (e.key === 'Enter') send(); });
  $('cw-file-btn').addEventListener('click', () => $('cw-file').click());
  $('cw-file').addEventListener('change', async () => {        // CHAT-FUN-01: a picture or a sound from this PC
    const file = $('cw-file').files[0];
    $('cw-file').value = '';
    if (!file) return;
    const check = fileCheck(file);
    if (check.error) { note(check.error, true); return; }
    note(`Sharing ${file.name}…`);
    const data = await new Promise((resolve, reject) => {
      const r = new FileReader();
      r.onload = () => resolve(String(r.result).replace(/^data:[^,]*,/, ''));
      r.onerror = () => reject(r.error);
      r.readAsDataURL(file);
    }).catch(() => null);
    if (data === null) { note('That file could not be read.', true); return; }
    if (await act(() => port.share(who(), file.name, data, $('cw-text').value.trim()))) $('cw-text').value = '';
  });
  $('cw-dice-row').addEventListener('click', e => {
    const b = e.target.closest('button[data-sides]');
    if (!b) return;
    const sides = Number(b.dataset.sides), mode = $('cw-mode').value;
    if (e.shiftKey) {                                         // the quick roll: one die (and the bonus) at once
      act(() => port.roll(who(), buildExpr(1, sides, $('cw-mod').value, mode), modeLabel(sides, 1, mode, $('cw-label').value), $('cw-private').checked));
      return;
    }
    $('cw-pool').value = addDie($('cw-pool').value, sides);
    note('');
  });
  const rollPool = () => {                                    // DICE-POOL-01: the pool and the bonus as one roll
    const pool = $('cw-pool').value, mode = $('cw-mode').value;
    if (!pool.trim()) { note('Click a die (or type a roll such as 2d6 + 1d8) first, then Roll.', true); return; }
    act(() => port.roll(who(), poolExpr(pool, $('cw-mod').value, mode), poolLabel(pool, mode, $('cw-label').value), $('cw-private').checked));
  };
  $('cw-roll').addEventListener('click', rollPool);
  for (const id of ['cw-pool', 'cw-mod', 'cw-label']) $(id).addEventListener('keydown', e => { if (e.key === 'Enter') rollPool(); });
  $('cw-clear').addEventListener('click', () => { $('cw-pool').value = ''; $('cw-mod').value = '0'; note(''); $('cw-pool').focus(); });
  $('cw-who').addEventListener('change', () => { try { localStorage.setItem(NAME_KEY, $('cw-who').value.trim()); } catch { /* not kept */ } refresh(); });
  pageSeat?.addEventListener('change', () => refresh());

  // CHAT-MODEL-01: the GM's model. The service lists what each local server offers and keeps the talk.
  let modelServers = [], modelNow = { url: '', model: '', loaded: false };
  const modelState = (text, isError = false) => { $('cw-model-state').textContent = text; $('cw-model-state').className = 'cw-tip' + (isError ? ' error' : ''); };
  function modelChoices() {
    const server = modelServers.find(s => s.url === $('cw-model-server').value);
    $('cw-model-name').replaceChildren(...(server?.models ?? []).map(m => el('option', { value: m }, m)));
    if (server?.models.includes(modelNow.model)) $('cw-model-name').value = modelNow.model;
    $('cw-model-load').disabled = !server?.models.length;
  }
  function drawModel(out) {
    modelNow = { url: out.url, model: out.model, loaded: out.loaded };
    if (out.servers) {
      const chosen = $('cw-model-server').value;
      modelServers = out.servers;
      $('cw-model-server').replaceChildren(...modelServers.map(s => el('option', { value: s.url }, s.up ? s.name : `${s.name} (not running)`)));
      const start = out.loaded ? out.url : chosen || (modelServers.find(s => s.url === out.url && s.up) ?? modelServers.find(s => s.up))?.url;
      if (start) $('cw-model-server').value = start;
      modelChoices();
    }
    const server = modelServers.find(s => s.url === out.url)?.name ?? out.url;
    modelState(out.loaded ? `Loaded: ${out.model} on ${server}. The Rules monitor uses it too.`
      : modelServers.some(s => s.up) ? 'Choose a model and press Load.' : 'Start LM Studio or Ollama, then open this section again.');
    const talk = $('cw-talk');
    talk.replaceChildren(...[...(out.talk ?? [])].reverse().map(t => { const li = el('li'); li.append(el('span', { class: 'cw-who' }, t.who), doc.createTextNode(t.text)); return li; }));
    talk.scrollTop = 0;
    $('cw-ask').disabled = $('cw-ask-send').disabled = !out.loaded;
  }
  async function modelAct(body, busy) {
    if (busy) modelState(busy);
    const out = await port.model(body).catch(() => ({ ok: false, error: 'The simulator service stopped.' }));
    if (out.ok) drawModel(out); else modelState(out.error, true);
    return out.ok;
  }
  const askModel = async () => {
    const text = $('cw-ask').value;
    if (!text.trim()) return;
    $('cw-ask-send').disabled = true;
    if (await modelAct({ op: 'ask', text }, 'Asking…')) $('cw-ask').value = '';
    $('cw-ask-send').disabled = !modelNow.loaded;
  };
  if (port.isGM()) {
    $('cw-model').hidden = false;
    $('cw-model').addEventListener('toggle', () => {
      if (!$('cw-model').open) return;
      $('cw-dice').open = false;
      modelAct({ op: 'state' }, 'Looking for LM Studio and Ollama…');
    });
    $('cw-model-server').addEventListener('change', modelChoices);
    $('cw-model-load').addEventListener('click', async () => {
      $('cw-model-load').disabled = true;
      await modelAct({ op: 'load', url: $('cw-model-server').value, model: $('cw-model-name').value }, 'Loading… a big model can take a minute.');
      $('cw-model-load').disabled = false;
    });
    $('cw-ask-send').addEventListener('click', askModel);
    $('cw-ask').addEventListener('keydown', e => { if (e.key === 'Enter') askModel(); });
    $('cw-talk-clear').addEventListener('click', () => modelAct({ op: 'clear' }));
  }

  async function refresh() {
    if (!online) return;
    const out = await port.log(who()).catch(() => null);
    if (out?.ok) show(out.chat);
  }
  fab.addEventListener('click', () => {
    const open = win.hidden;
    win.hidden = !open;
    fab.setAttribute('aria-expanded', String(open));
    if (open) {
      seenWhileOpen = newest; unread.hidden = true;
      if (!online) note('The chat needs the simulator service: start Start_Mythastria.bat.', true);
      $('cw-log').scrollTop = 0;
      $('cw-text').focus();
    }
  });
  doc.addEventListener('keydown', e => { if (e.key === 'Escape' && !win.hidden && win.contains(doc.activeElement)) fab.click(); });
  await refresh();
  setInterval(refresh, 2500);
}

if (typeof document !== 'undefined' && document.body && !globalThis.__noTableChat) mountTableChat();
