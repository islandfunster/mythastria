// MARKET-01 (GM 2026-10-21: "I want to add a marketspace activated only by the DM"; chose: players add to a shopping cart
// and the GM approves or rejects line items with select all or none; shops tied to adventure places; gold kept by
// Mythastria). Two windows on Play live:
// - the GM's Market dialog (mountMarket): shops at the loaded adventures' places, open one at a time, stock from the SRD
//   5.2.1 list (or homebrew), gold and bags, and the carts waiting for approval, line by line;
// - the players' Market (mountMarketPlayer), in play.html?view=player: shown only while a shop is open; a seat at the
//   players' door fills and sends its own character's cart (the service reads the character from the seat's ticket).
// The service decides everything (Mythastria sim/market.py, POST /api/market): prices, gold, stock, who may do what.
import { api } from './server.mjs';                            // PLAYER-SITE-01: the GM's Mythastria
import { seatPart, loadSeat } from './seat-ticket.mjs';

export function money(cp) {
  cp = Math.round(Number(cp) || 0);
  const neg = cp < 0; cp = Math.abs(cp);
  const gp = Math.floor(cp / 100), sp = Math.floor(cp % 100 / 10), c = cp % 10;
  const parts = [gp ? `${gp.toLocaleString('en-US')} GP` : '', sp ? `${sp} SP` : '', c ? `${c} CP` : ''].filter(Boolean);
  return (neg ? '-' : '') + (parts.join(' ') || '0 GP');
}
// LOOT-01: the party loot's coins and their shares, in words (the GM's tab and the players' window)
const COIN_ORDER = ['pp', 'gp', 'ep', 'sp', 'cp'];
export function lootSummary(loot) {
  const coins = COIN_ORDER.filter(c => loot?.coins?.[c]).map(c => `${loot.coins[c].toLocaleString('en-US')} ${c.toUpperCase()}`);
  if (!coins.length) return { coins: 'No coins in the party loot.', share: '' };
  const n = loot.who?.length ?? 0;
  return { coins: `Coins: ${coins.join(', ')}${coins.join(', ') !== loot.total ? ` = ${loot.total}` : ''}.`,
    share: !n ? 'The GM chooses who shares the coins.' : !loot.each_cp ? `Too few coins to share ${n} ways.` : `${n} way${n === 1 ? '' : 's'}: ${loot.each} each${
      loot.left_cp ? ` (${loot.left} doesn't divide evenly: it stays in the party loot)` : ''}.` };
}
export const KIND_NAMES = { gear: 'Adventuring gear', tool: 'Tools', ammunition: 'Ammunition', focus: 'Spellcasting foci',
  weapon: 'Weapons', armor: 'Armor', potion: 'Potions', scroll: 'Spell scrolls', magic: 'Magic items', homebrew: 'Homebrew' };
const KIND_ORDER = Object.keys(KIND_NAMES);
const ago = s => s < 60 ? 'just now' : s < 3600 ? `${Math.floor(s / 60)} min ago` : `${Math.floor(s / 3600)} h ago`;
// A shop line, said shortly: rarity, attunement, homebrew
export function lineTags(l) {
  return [l.rarity ? l.rarity.toLowerCase() : '', l.attunement ? 'attunement' : '', l.homebrew ? 'homebrew' : '',
    l.qty === 0 ? 'sold out' : Number.isInteger(l.qty) ? `${l.qty} left` : ''].filter(Boolean).join(' · ');
}
// The catalog's matches for what the GM typed (name words, any order), at most `max`
export function search(items, text, kind = '', max = 40) {
  const words = String(text || '').toLowerCase().split(/\s+/).filter(Boolean);
  const out = [];
  for (const i of items) {
    if (kind && i.kind !== kind) continue;
    const name = i.name.toLowerCase();
    if (words.every(w => name.includes(w))) out.push(i);
    if (out.length >= max) break;
  }
  return out;
}

function port(fetchFn, seat) {
  let token = null;
  async function hello() {
    const out = await (await fetchFn(api('/api/hello'))).json();
    token = out.token ?? null;
    return out;
  }
  async function post(body, retry = true) {
    if (!token && !seat && retry) await hello();
    const res = await fetchFn(api('/api/market'), { method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ ...body, ...(token ? { token } : {}), ...(seat ? seatPart() : {}) }) });
    const out = await res.json().catch(() => ({ ok: false, error: 'The service sent no answer.' }));
    if (res.status === 403 && retry && /token/i.test(out.error || '')) { token = null; return post(body, false); }
    if (res.status === 403 && /unsupported|not found/i.test(out.error || '')) out.error = 'Restart Mythastria (the Desktop Start_Mythastria.bat) to get the market.';
    return res.ok ? out : { ...out, ok: false, status: res.status };
  }
  return { post };
}

function maker(doc) {
  return (tag, text, cls, attrs = {}) => {
    const e = doc.createElement(tag);
    if (text !== undefined && text !== null) e.textContent = text;
    if (cls) e.className = cls;
    for (const [k, v] of Object.entries(attrs)) if (v !== undefined && v !== null && v !== false) e.setAttribute(k, v === true ? '' : v);
    return e;
  };
}

// ======================================================================== the GM's Market dialog
export function mountMarket({ document: doc = globalThis.document, button, status = () => {}, fetch: fetchFn = globalThis.fetch, every = 3000 }) {
  const make = maker(doc);
  const btn = (text, fn, cls, title) => { const b = make('button', text, cls, { type: 'button', title }); b.addEventListener('click', fn); return b; };
  const dialog = make('dialog', undefined, 'market-dialog', { id: 'market-dialog', 'aria-labelledby': 'market-title' });
  doc.body.append(dialog);
  const api = port(fetchFn, false);
  let state = null, catalog = null, tab = 'requests', editing = null, error = '', note = '', drawn = '';
  const ticks = new Map(), prices = new Map();                   // per cart line: ticked (default yes), price typed

  async function act(body) {
    note = '';
    const out = await api.post(body).catch(() => ({ ok: false, error: 'The simulator service stopped.' }));
    if (out.ok && out.shops) apply(out);
    else if (out.market) apply(out.market);
    error = out.ok ? '' : (out.error || 'Refused.');
    draw(true);
    return out;
  }
  function apply(next) {
    const before = state?.asked ?? 0;
    state = next;
    button.replaceChildren('Market…');
    if (state.asked) button.append(make('span', String(state.asked), 'market-count'));
    const open = state.shops.find(s => s.id === state.open);
    button.title = (open ? `Open: ${open.name}. ` : 'No shop open. ') + (state.asked ? `${state.asked} cart(s) waiting for you.` : 'Shops, gold and carts.');
    if (state.asked > before) status(`Market: ${state.asked} cart${state.asked === 1 ? '' : 's'} waiting for your approval (Market…).`);
  }
  async function loadCatalog() {
    if (catalog) return catalog;
    const out = await api.post({ op: 'catalog' });
    if (out.ok) catalog = out.items;
    return catalog || [];
  }
  const typing = () => dialog.contains(doc.activeElement) && /^(INPUT|SELECT|TEXTAREA)$/.test(doc.activeElement.tagName);

  function draw(force = false) {
    if (!state || !dialog.open) return;
    const key = JSON.stringify([state.rev, tab, !!editing, error, note]);
    if (!force && (key === drawn || typing() || editing)) return;   // keep what the GM is typing
    drawn = key;
    const open = state.shops.find(s => s.id === state.open);
    const title = make('h2', 'Market', '', { id: 'market-title' });
    const bar = make('p', '', 'market-open-line');
    if (open) bar.append(make('strong', `Open now: ${open.name}`), ` (${open.kind_name}, ${open.where}). Players see it. `,
      btn('Close the shop', () => act({ op: 'close' })));
    else bar.append(make('strong', 'No shop is open.'), ' Players see nothing until you open one.');
    const tabs = make('div', '', 'market-tabs', { role: 'tablist' });
    for (const [id, label] of [['requests', `Carts${state.asked ? ` (${state.asked})` : ''}`], ['shops', 'Shops'], ['gold', 'Gold and bags'],
      ['loot', `Party loot${state.loot?.finds.length ? ` (${state.loot.finds.length})` : ''}`], ['log', 'Log']]) {
      const t = btn(label, () => { tab = id; editing = null; error = ''; note = ''; draw(true); }, tab === id ? 'on' : 'quiet');
      t.setAttribute('role', 'tab'); t.setAttribute('aria-selected', String(tab === id));
      tabs.append(t);
    }
    const body = make('div', '', 'market-body');
    if (editing) body.append(editor());
    else if (tab === 'requests') body.append(...requests(open));
    else if (tab === 'shops') body.append(...shops());
    else if (tab === 'gold') body.append(...gold());
    else if (tab === 'loot') body.append(...partyLoot());
    else body.append(logView());
    const err = make('p', error, 'market-error', { role: 'alert' }); err.hidden = !error;
    const ok = make('p', note, 'note', { role: 'status' }); ok.hidden = !note || !!error;
    dialog.replaceChildren(title, bar, tabs, err, ok, body, make('p', '', 'market-foot').appendChild(btn('Close', () => dialog.close(), 'quiet')).parentNode);
  }

  // ---------------------------------------------------------------- carts waiting for the GM
  function requests(open) {
    const out = [];
    const waiting = state.carts.filter(c => c.lines.length);
    if (!waiting.length) out.push(make('p', 'No carts are waiting. Players add to a cart from their own screen and send it to you.', 'note'));
    for (const c of waiting) {
      const box = make('section', '', 'market-cart');
      const purse = state.purses.find(p => p.name.toLowerCase() === c.name.toLowerCase());
      box.append(make('h3', `${c.name} · has ${purse?.gold ?? '0 GP'}`),
        make('p', `${c.sent ? (c.by === 'GM' ? 'Added by you' : `Sent by ${c.by || 'the player'}`) : 'Still being filled (not sent yet)'} · ${c.shop_name || ''}`, 'note'));
      const table = make('table', '', 'market-lines');
      for (const l of c.lines) {
        if (!ticks.has(l.id)) ticks.set(l.id, true);
        const tr = make('tr');
        const tick = make('input', undefined, '', { type: 'checkbox', 'aria-label': `Approve ${l.name}` });
        tick.checked = ticks.get(l.id); tick.addEventListener('change', () => ticks.set(l.id, tick.checked));
        const price = make('input', undefined, 'market-price', { type: 'number', min: '0', step: '0.01', 'aria-label': `Price of one ${l.name} in GP`,
          title: 'Price of one, in GP: change it after a haggle (a Persuasion check)' });
        price.value = prices.get(l.id) ?? String(l.price_cp / 100);
        price.addEventListener('input', () => prices.set(l.id, price.value));
        const warn = make('td', '', 'market-warn');
        for (const w of l.warnings || []) warn.append(make('div', w));
        tr.append(make('td').appendChild(tick).parentNode, make('td', l.op === 'sell' ? 'Sell' : 'Buy', l.op === 'sell' ? 'market-sell' : ''),
          make('td', l.qty > 1 ? `${l.name} ×${l.qty}` : l.name), make('td').appendChild(price).parentNode, make('td', `= ${l.total}`), warn);
        table.append(tr);
      }
      const all = btn('All', () => { c.lines.forEach(l => ticks.set(l.id, true)); draw(true); }, 'quiet');
      const none = btn('None', () => { c.lines.forEach(l => ticks.set(l.id, false)); draw(true); }, 'quiet');
      const why = make('input', undefined, '', { maxlength: '200', placeholder: 'Reason for what you refuse (optional)', 'aria-label': `Reason for ${c.name}` });
      const approve = btn('Approve ticked, refuse the rest', () => {
        const lines = c.lines.filter(l => ticks.get(l.id)).map(l => l.id);
        const changed = {};
        for (const l of c.lines) if (prices.has(l.id) && Number(prices.get(l.id)) * 100 !== l.price_cp) changed[l.id] = Number(prices.get(l.id));
        act({ op: 'decide', character: c.name, lines, prices: changed, reason: why.value.trim() }).then(o => {
          if (o.ok) { c.lines.forEach(l => { ticks.delete(l.id); prices.delete(l.id); }); note = `${c.name}: done.`; draw(true); }
        });
      });
      const refuse = btn('Refuse all', () => act({ op: 'refuse', character: c.name, reason: why.value.trim() }), 'quiet');
      box.append(table, make('p', '', 'market-actions'));
      box.lastChild.append(all, none, approve, refuse, why);
      out.push(box);
    }
    if (open) {                                                  // the GM buys for a character too (it waits here like a cart)
      const who = make('select', '', '', { 'aria-label': 'Character' });
      for (const p of state.purses) who.append(Object.assign(make('option', p.name), { value: p.name }));
      const what = make('select', '', '', { 'aria-label': 'Item' });
      for (const l of open.stock) what.append(Object.assign(make('option', `${l.name} · ${l.price}${l.qty != null ? ` (${l.qty} left)` : ''}`), { value: l.id }));
      const qty = make('input', undefined, 'market-qty', { type: 'number', min: '1', max: '999', value: '1', 'aria-label': 'How many' });
      const add = btn('Add to their cart', () => act({ op: 'cart_add', character: who.value, stock: what.value, qty: Number(qty.value) || 1 }));
      const p = make('p', '', 'market-row'); p.append(make('strong', `Buy for a character at ${open.name}: `), who, what, qty, add);
      out.push(make('h3', 'Buy for a character'), state.purses.length ? p : make('p', 'Give a character gold first (Gold and bags).', 'note'));
    }
    out.push(make('p', 'Approving takes the gold and puts the items in the character\'s bag; the table chat says what was bought (not the price). Warnings never block: attunement (3 at most), class and spell list.', 'note'));
    return out;
  }

  // ---------------------------------------------------------------- shops at the adventures' places
  function shops() {
    const out = [];
    const packs = Object.entries(state.places || {});
    if (!packs.length) {
      out.push(make('p', 'Shops belong to places in an adventure: load one on the Adventure page first.', 'note'));
    }
    for (const [pack, info] of packs) {
      out.push(make('h3', info.name));
      const mine = state.shops.filter(s => s.pack === pack);
      if (!mine.length) out.push(make('p', 'No shops in this adventure yet.', 'note'));
      const list = make('ul', '', 'market-shops');
      for (const s of mine) {
        const li = make('li');
        const isOpen = s.id === state.open;
        li.append(make('span', isOpen ? 'OPEN' : '', isOpen ? 'market-badge' : ''), make('strong', s.name), make('span', `${s.kind_name} · ${s.where} · ${s.stock.length} lines`, 'grow note'),
          isOpen ? btn('Close', () => act({ op: 'close' })) : btn('Open', () => act({ op: 'open', id: s.id }), '', 'Players see this shop until you close it (one shop at a time)'),
          btn('Edit', () => { editing = structuredClone(s); draw(true); }, 'quiet'),
          btn('Delete', () => { if (globalThis.confirm?.(`Delete ${s.name} and its stock?`) !== false) act({ op: 'shop_delete', id: s.id }); }, 'quiet'));
        list.append(li);
      }
      out.push(list);
      const kind = make('select', '', '', { 'aria-label': 'Kind of shop' });
      for (const [k, n] of Object.entries(state.kinds)) kind.append(Object.assign(make('option', n), { value: k }));
      const place = make('select', '', '', { 'aria-label': 'Place' });
      for (const p of info.places) place.append(Object.assign(make('option', p.title), { value: p.key }));
      place.append(Object.assign(make('option', 'Another place (type it)…'), { value: '' }));
      const where = make('input', undefined, '', { maxlength: '60', placeholder: 'e.g. Harbor market square', 'aria-label': 'Another place' });
      where.hidden = true; place.addEventListener('change', () => { where.hidden = !!place.value; });
      const make1 = btn('New shop with suggested stock', async () => {
        const t = await api.post({ op: 'template', kind: kind.value, seed: Math.floor(Math.random() * 1e6) });
        if (!t.ok) { error = t.error; draw(true); return; }
        const title = place.value ? info.places.find(p => p.key === place.value).title : where.value.trim();
        editing = { name: `${t.name}${title ? ` (${title.split(' - ').pop()})` : ''}`, kind: kind.value, pack, place: place.value, where: title,
          buyback: 50, note: '', stock: t.stock, picked: t.picked, rarities: t.rarities, party: t.party, level: t.level };
        error = ''; draw(true);
      });
      const row = make('p', '', 'market-row'); row.append(kind, place, where, make1);
      out.push(row);
    }
    out.push(make('p', 'Stock comes from the SRD 5.2.1 price list (equipment at its listed cost; magic items by rarity: Common 100 GP, Uncommon 400, Rare 4,000, Very Rare 40,000, Legendary 200,000, potions half; spell scrolls at twice their scribing cost). Your own items go in as homebrew.', 'note'));
    return out;
  }

  function editor() {
    const s = editing;
    const box = make('section', '', 'market-editor');
    const name = make('input', undefined, '', { maxlength: '60', 'aria-label': 'Shop name' }); name.value = s.name;
    name.addEventListener('input', () => { s.name = name.value; });
    const kind = make('select', '', '', { 'aria-label': 'Kind' });
    for (const [k, n] of Object.entries(state.kinds)) kind.append(Object.assign(make('option', n), { value: k, selected: k === s.kind }));
    kind.addEventListener('change', () => { s.kind = kind.value; });
    const buy = make('input', undefined, 'market-qty', { type: 'number', min: '0', max: '100', 'aria-label': 'Buy-back percent' }); buy.value = s.buyback ?? 50;
    buy.addEventListener('input', () => { s.buyback = Number(buy.value); });
    const head = make('p', '', 'market-row');
    const label = (text, input, after = '') => { const l = make('label', text); l.append(input, after); return l; };
    head.append(label('Name ', name), label('Kind ', kind), label('Buys back at ', buy, '% of value'));
    box.append(make('h3', `${s.id ? 'Edit' : 'New'} shop · ${s.where}`), head);
    if (s.picked?.length) box.append(make('p', `Picked for ${s.party?.length ? s.party.join(', ') : 'the party'}${s.level ? ` (level ${s.level}, ${s.rarities.join(', ').toLowerCase()})` : ''}: ${s.picked.join('; ')}.`, 'note'));
    if (!s.party?.length && s.picked) box.append(make('p', 'No live fight is running, so the magic picks are not matched to the party. Start the fight first for picks that fit it.', 'note'));
    const table = make('table', '', 'market-stock');
    table.append(make('tr', '', '', {}));
    table.lastChild.append(make('th', 'Item'), make('th', 'List price'), make('th', 'Price (GP)'), make('th', 'How many'), make('th', 'Note'), make('th', ''));
    s.stock.forEach((l, n) => {
      const tr = make('tr');
      const price = make('input', undefined, 'market-price', { type: 'number', min: '0', step: '0.01', placeholder: 'list', 'aria-label': `Price of ${l.name}` });
      price.value = l.price_gp ?? (l.list_cp != null && l.price_cp != null && l.price_cp !== l.list_cp ? l.price_cp / 100 : '');
      price.addEventListener('input', () => { l.price_gp = price.value === '' ? null : Number(price.value); });
      const qty = make('input', undefined, 'market-qty', { type: 'number', min: '0', max: '999', placeholder: 'any', 'aria-label': `How many ${l.name}` });
      qty.value = l.qty ?? '';
      qty.addEventListener('input', () => { l.qty = qty.value === '' ? null : Number(qty.value); });
      const nt = make('input', undefined, '', { maxlength: '200', 'aria-label': `Note for ${l.name}` }); nt.value = l.note ?? '';
      nt.addEventListener('input', () => { l.note = nt.value; });
      const item = make('td', l.name + (l.homebrew ? ' (homebrew)' : ''));
      if (l.why) item.append(make('div', `Picked ${l.why} (only you see this)`, 'note'));
      tr.append(item, make('td', l.list_cp != null ? money(l.list_cp) : '—'),
        make('td').appendChild(price).parentNode, make('td').appendChild(qty).parentNode, make('td').appendChild(nt).parentNode,
        make('td').appendChild(btn('Remove', () => { s.stock.splice(n, 1); draw(true); }, 'quiet')).parentNode);
      table.append(tr);
    });
    box.append(make('div', '', 'market-scroll').appendChild(table).parentNode,
      make('p', 'Blank price: the SRD list price. Blank "how many": as many as they want.', 'note'));

    // add from the SRD list
    const find = make('input', undefined, '', { placeholder: 'Find an SRD item: e.g. longsword, healing, fireball', 'aria-label': 'Find an SRD item' });
    const kindF = make('select', '', '', { 'aria-label': 'Kind of item' });
    kindF.append(Object.assign(make('option', 'Any kind'), { value: '' }));
    for (const k of KIND_ORDER.filter(k => k !== 'homebrew')) kindF.append(Object.assign(make('option', KIND_NAMES[k]), { value: k }));
    const results = make('ul', '', 'market-results');
    const show = async () => {
      const items = search(await loadCatalog(), find.value, kindF.value, 30);
      results.replaceChildren(...items.map(i => {
        const li = make('li');
        const base = make('select', '', '', { 'aria-label': `What ${i.name} is made from` });
        for (const b of i.bases || []) base.append(Object.assign(make('option', b), { value: b }));
        li.append(make('span', `${i.name} · ${money(i.cost_cp)}${i.bases ? ' + the base item' : ''}${i.rarity ? ` · ${i.rarity.toLowerCase()}` : ''}${i.attunement ? ' · attunement' : ''}`, 'grow'));
        if (i.bases) li.append(base);
        li.append(btn('Add', () => {
          const b = i.bases ? base.value : null;
          s.stock.push({ item: i.id, base: b, name: i.name + (b ? ` (${b})` : ''), qty: null, price_gp: null, note: '',
            list_cp: i.cost_cp + (b ? (catalog.find(x => x.name === b)?.cost_cp ?? 0) : 0) });
          draw(true);
        }));
        return li;
      }));
    };
    find.addEventListener('input', show); kindF.addEventListener('change', show);
    const fr = make('p', '', 'market-row'); fr.append(find, kindF);
    box.append(make('h3', 'Add from the SRD 5.2.1 list'), fr, results);

    // homebrew
    const hn = make('input', undefined, '', { maxlength: '60', placeholder: 'Your item\'s name', 'aria-label': 'Homebrew item name' });
    const hp = make('input', undefined, 'market-price', { type: 'number', min: '0', step: '0.01', placeholder: 'GP', 'aria-label': 'Homebrew price in GP' });
    const ha = make('label', ' needs attunement'); const hat = make('input', undefined, '', { type: 'checkbox' }); ha.prepend(hat);
    const hr = make('p', '', 'market-row');
    hr.append(hn, hp, ha, btn('Add homebrew', () => {
      if (!hn.value.trim() || hp.value === '') { error = 'A homebrew item needs a name and a price.'; draw(true); return; }
      s.stock.push({ item: null, name: hn.value.trim(), price_gp: Number(hp.value), attunement: hat.checked, homebrew: true, qty: null, note: '' });
      error = ''; draw(true);
    }, 'quiet'));
    box.append(make('h3', 'Add your own (homebrew)'), hr, make('p', 'Homebrew is marked as such for you and the players. Only SRD 5.2.1 ships with Mythastria.', 'note'));

    const save = btn('Save the shop', async () => {
      const shop = { id: s.id, name: s.name, kind: s.kind, pack: s.pack, place: s.place, where: s.where, buyback: s.buyback ?? 50, note: s.note,
        stock: s.stock.map(l => ({ id: l.id, item: l.item, base: l.base ?? null, name: l.name, qty: l.qty ?? null, note: l.note || '',
          why: l.why || '', price_gp: l.price_gp !== undefined ? l.price_gp : l.price_cp != null && (l.homebrew || l.price_cp !== l.list_cp) ? l.price_cp / 100 : null,
          attunement: l.attunement })) };
      const out = await act({ op: 'shop_save', rev: state.rev, shop });
      if (out.ok) { editing = null; tab = 'shops'; note = `${s.name} saved.`; draw(true); }
    });
    const cancel = btn('Cancel', () => { editing = null; error = ''; draw(true); }, 'quiet');
    box.append(make('p', '', 'market-actions'));
    box.lastChild.append(save, cancel);
    return box;
  }

  // ---------------------------------------------------------------- LOOT-01: the party loot
  // (GM 2026-10-29: "a special loot inventory" that "calculates and divides all the coins per person"). The GM adds
  // finds, gives items to bags, chooses who shares and pays the shares into the purses; Mythastria adds up the coins
  // and divides them (sim/market.py loot_*). The players see it, read only.
  let lootText = '';
  function partyLoot() {
    const L = state.loot ?? { finds: [], who: [] }, names = state.purses.map(p => p.name);
    const add = make('section', '', 'market-purse market-loot');
    const text = make('textarea', undefined, 'market-loot-text', { rows: '3', maxlength: '4000', 'aria-label': 'What the party found',
      placeholder: 'What the party found, one find per line:\n1,200 gp, 35 sp, 2 pp\n40 silver pieces\nRope, Hempen (50 feet)' });
    text.value = lootText;
    text.addEventListener('input', () => { lootText = text.value; });
    add.append(make('h3', 'Add what the party found'), text, make('p', '', 'market-actions'));
    add.lastChild.append(btn('Add to the party loot', () => act({ op: 'loot_add', text: lootText }).then(o => {
      if (o.ok) { lootText = ''; draw(true); }
    })));
    const list = make('section', '', 'market-purse market-loot');
    list.append(make('h3', `Party loot${L.finds.length ? ` (${L.finds.length})` : ''}`));
    const ul = make('ul', '', 'market-bag');
    for (const f of L.finds) {
      const li = make('li');
      li.append(make('span', f.text, 'grow'), make('span', f.coins ? 'coins' : 'item', 'market-loot-tag'));
      if (!f.coins && names.length) {
        const to = make('select', '', '', { 'aria-label': `Who gets ${f.text}` });
        for (const n of names) to.append(Object.assign(make('option', n), { value: n }));
        li.append(to, btn('Give', () => act({ op: 'loot_item', id: f.id, character: to.value }), 'quiet', "Into that character's bag"));
      }
      li.append(btn('Remove', () => act({ op: 'loot_remove', id: f.id }), 'quiet', 'Take it off the list (nobody gets it)'));
      ul.append(li);
    }
    list.append(L.finds.length ? ul : make('p', 'Nothing yet: add what the party finds above.', 'note'));
    const share = make('section', '', 'market-purse market-loot');
    const who = make('p', '', 'market-row');
    who.append(make('span', 'Shared by:'));
    for (const n of names) {
      const tick = make('input', undefined, '', { type: 'checkbox', 'aria-label': `${n} shares the coins` });
      tick.checked = L.who.includes(n);
      tick.addEventListener('change', () => act({ op: 'loot_who', characters: names.filter(x => x === n ? tick.checked : L.who.includes(x)) }));
      const label = make('label'); label.append(tick, ' ' + n); who.append(label);
    }
    const s = lootSummary(L);
    share.append(make('h3', 'Share the coins'), names.length ? who : make('p', 'Make a purse first (Gold and bags).', 'note'), make('p', s.coins));
    if (s.share) share.append(make('p', s.share, 'market-loot-each'));
    if (L.each_cp) {
      share.append(make('p', '', 'market-actions'));
      share.lastChild.append(btn(`Pay ${L.each} into each purse`, () => act({ op: 'loot_give', characters: L.who }).then(o => {
        if (o.ok) { note = `Paid ${L.each} to ${L.who.join(', ')}.`; draw(true); }
      }), '', 'Add each share to each purse (Gold and bags); the coins leave the party loot'));
    }
    return [add, list, share, make('p', 'The players see the party loot and their share on their own screen (Market), read only.', 'note')];
  }

  // ---------------------------------------------------------------- gold and bags
  function gold() {
    const out = [];
    const list = make('div', '', 'market-purses');
    if (!state.purses.length) out.push(make('p', 'Nobody has a purse yet. Characters in the live fight and seated players appear here; or type a name below.', 'note'));
    for (const p of state.purses) {
      const box = make('section', '', 'market-purse');
      const amount = make('input', undefined, 'market-price', { type: 'number', step: '0.01', placeholder: 'GP', 'aria-label': `Gold for ${p.name}` });
      const why = make('input', undefined, '', { maxlength: '120', placeholder: 'Why (optional): loot, reward…', 'aria-label': `Reason for ${p.name}` });
      const row = make('p', '', 'market-row');
      row.append(amount,
        btn('Give', () => act({ op: 'purse', character: p.name, add_gp: Number(amount.value) || 0, reason: why.value.trim() }), '', 'Add this much gold'),
        btn('Take', () => act({ op: 'purse', character: p.name, add_gp: -(Number(amount.value) || 0), reason: why.value.trim() }), 'quiet', 'Take this much gold'),
        btn('Set to', () => act({ op: 'purse', character: p.name, set_gp: Number(amount.value) || 0, reason: why.value.trim() }), 'quiet', 'Set the purse to exactly this'),
        why);
      box.append(make('h3', `${p.name} · ${p.gold}${p.attuned ? ` · ${p.attuned} item${p.attuned === 1 ? '' : 's'} needing attunement` : ''}`), row);
      const bag = make('ul', '', 'market-bag');
      for (const b of p.bag) {
        const li = make('li');
        li.append(make('span', `${b.name}${b.qty > 1 ? ` ×${b.qty}` : ''}${b.homebrew ? ' (homebrew)' : ''}${b.attunement ? ' · attunement' : ''} · worth ${b.value}`, 'grow'),
          btn('Remove one', () => act({ op: 'bag_remove', character: p.name, entry: b.id, qty: 1, reason: 'used up or lost' }), 'quiet', 'Used up, lost or given away'));
        bag.append(li);
      }
      const give = make('input', undefined, '', { list: 'market-catalog-names', placeholder: 'Give an item (found treasure): SRD name or your own', 'aria-label': `Give ${p.name} an item` });
      const gr = make('p', '', 'market-row');
      gr.append(give, btn('Give item', async () => {
        const cat = await loadCatalog();
        const i = cat.find(x => x.name.toLowerCase() === give.value.trim().toLowerCase());
        if (i?.bases) { error = `${i.name}: add it to a shop to choose what it is made from, or give it as your own item.`; draw(true); return; }
        act(i ? { op: 'bag_add', character: p.name, item: i.id } : { op: 'bag_add', character: p.name, name: give.value.trim(), value_gp: 0 });
      }, 'quiet'));
      box.append(p.bag.length ? bag : make('p', 'The bag is empty.', 'note'), gr);
      list.append(box);
    }
    const names = make('datalist', '', '', { id: 'market-catalog-names' });
    loadCatalog().then(c => names.replaceChildren(...c.filter(i => !i.bases).map(i => Object.assign(make('option'), { value: i.name }))));
    const nn = make('input', undefined, '', { maxlength: '40', placeholder: 'Another character\'s name', 'aria-label': 'New character name' });
    const ng = make('input', undefined, 'market-price', { type: 'number', step: '0.01', min: '0', placeholder: 'GP', 'aria-label': 'Their gold' });
    const nr = make('p', '', 'market-row');
    nr.append(nn, ng, btn('Make a purse', () => act({ op: 'purse', character: nn.value.trim(), set_gp: Number(ng.value) || 0 }), 'quiet'));
    out.push(list, names, make('h3', 'Another character'), nr,
      make('p', 'Gold and bags are kept by Mythastria on this PC, the same on every screen. The Characters page sheet is not changed.', 'note'));
    return out;
  }

  function logView() {
    const ul = make('ul', '', 'market-log');
    for (const e of [...state.log].reverse()) ul.append(make('li', `${e.at} · ${e.text}`));
    return state.log.length ? ul : make('p', 'Nothing has happened in the market yet.', 'note');
  }

  async function refresh() {
    const out = await api.post({ op: 'state' }).catch(() => null);
    if (out?.ok) { apply(out); draw(); }
    return out;
  }
  button.addEventListener('click', async () => {
    const out = await refresh();
    if (!out?.ok) { status('Market: ' + (out?.error || 'the simulator service stopped.'), true); return; }
    error = ''; note = ''; dialog.showModal(); draw(true);
  });
  dialog.addEventListener('close', () => { editing = null; });
  refresh();
  const poll = setInterval(refresh, every);
  return { dialog, refresh, stop: () => clearInterval(poll), get state() { return state; } };
}

// ======================================================================== the players' Market
export function mountMarketPlayer({ document: doc = globalThis.document, fetch: fetchFn = globalThis.fetch, every = 4000 } = {}) {
  const make = maker(doc);
  const btn = (text, fn, cls, title) => { const b = make('button', text, cls, { type: 'button', title }); b.addEventListener('click', fn); return b; };
  const seated = !!loadSeat();
  const api = port(fetchFn, seated);
  const fab = make('button', 'Market', '', { id: 'market-fab', type: 'button', 'aria-haspopup': 'dialog' });
  fab.hidden = true;
  const dialog = make('dialog', undefined, 'market-dialog market-player', { id: 'market-player', 'aria-labelledby': 'market-player-title' });
  doc.body.append(fab, dialog);
  let view = null, error = '', drawn = '', filter = '';
  const qtys = new Map();

  async function act(body) {
    const out = await api.post(body).catch(() => ({ ok: false, error: 'Mythastria stopped.' }));
    if (out.ok) view = out;
    error = out.ok ? '' : (out.error || 'Refused.');
    show(); draw(true);
  }
  function show() {
    const answer = view?.cart?.answer, loot = view?.loot?.finds?.length;   // LOOT-01: the party loot shows too
    fab.hidden = !(view?.open || answer || loot);
    fab.replaceChildren(view?.open ? `Market: ${view.shop.name}` : loot ? 'Party loot' : 'Market');
    if (answer) fab.append(make('span', '!', 'market-count'));
    if (!view?.open && !answer && !loot && dialog.open) dialog.close();
  }
  const typing = () => dialog.contains(doc.activeElement) && /^(INPUT|SELECT)$/.test(doc.activeElement.tagName);
  function draw(force = false) {
    if (!view || !dialog.open) return;
    const key = JSON.stringify([view.shop, view.purse, view.cart, view.loot, error]);
    if (!force && (key === drawn || typing())) return;
    drawn = key;
    const parts = [make('h2', view.open ? view.shop.name : 'Market', '', { id: 'market-player-title' })];
    if (view.open) parts.push(make('p', `${view.shop.kind_name} · ${view.shop.where}`, 'note'));
    if (view.purse) parts.push(make('p', `${view.purse.name} has ${view.purse.gold}.`, 'market-gold'));
    else if (view.note) parts.push(make('p', view.note, 'note'));
    else if (!seated) parts.push(make('p', 'Players shop from their own seat (join from the players\' door).', 'note'));
    const a = view.cart?.answer;
    if (a) {
      const box = make('section', '', 'market-answer');
      box.append(make('h3', 'The GM answered'));
      if (a.bought.length) box.append(make('p', `Bought: ${a.bought.join(', ')}.`));
      if (a.sold.length) box.append(make('p', `Sold: ${a.sold.join(', ')}.`));
      if (a.refused.length) box.append(make('p', `Refused: ${a.refused.join(', ')}.${a.reason ? ` (${a.reason})` : ''}`, 'market-no'));
      box.append(make('p', `Gold now: ${a.gold}.`), btn('OK', () => act({ op: 'dismiss' }), 'quiet'));
      parts.push(box);
    }
    const err = make('p', error, 'market-error', { role: 'alert' }); err.hidden = !error;
    parts.push(err);
    if (view.open) parts.push(...stock(), ...cart(), ...bag());
    parts.push(...partyLoot());
    parts.push(make('p', '', 'market-foot').appendChild(btn('Close', () => dialog.close(), 'quiet')).parentNode);
    dialog.replaceChildren(...parts);
  }
  function stock() {
    const sent = view.cart?.sent;
    const find = make('input', undefined, '', { placeholder: 'Find…', 'aria-label': 'Find in this shop', value: filter });
    const out = [make('h3', 'For sale'), find];
    const narrow = () => {                                        // hides what doesn't match, without redrawing the list
      filter = find.value;
      const words = filter.toLowerCase().split(/\s+/).filter(Boolean);
      for (const ul of dialog.querySelectorAll('.market-stock-list')) {
        let any = false;
        for (const li of ul.children) { li.hidden = !words.every(w => li.dataset.name.includes(w)); any ||= !li.hidden; }
        ul.hidden = ul.previousSibling.hidden = !any;
      }
    };
    find.addEventListener('input', narrow);
    queueMicrotask(narrow);
    const groups = new Map();
    for (const l of view.shop.stock) {
      const k = l.homebrew ? 'homebrew' : l.kind;
      if (!groups.has(k)) groups.set(k, []);
      groups.get(k).push(l);
    }
    for (const k of KIND_ORDER.filter(k => groups.has(k))) {
      const ul = make('ul', '', 'market-stock-list');
      for (const l of groups.get(k)) {
        const li = make('li'); li.dataset.name = l.name.toLowerCase();
        const qty = make('input', undefined, 'market-qty', { type: 'number', min: '1', max: String(l.qty ?? 999), 'aria-label': `How many ${l.name}` });
        qty.value = qtys.get(l.id) ?? '1'; qty.addEventListener('input', () => qtys.set(l.id, qty.value));
        const tags = lineTags(l);
        li.append(make('span', l.name, 'grow'), make('span', l.price, 'market-p'), tags ? make('span', tags, 'note') : '', l.note ? make('span', l.note, 'note') : '');
        if (view.purse && l.qty !== 0) {
          const add = btn('Add to cart', () => act({ op: 'cart_add', stock: l.id, qty: Number(qty.value) || 1 }), 'quiet');
          add.disabled = !!sent;
          li.append(qty, add);
        }
        ul.append(li);
      }
      out.push(make('h4', KIND_NAMES[k]), ul);
    }
    return out;
  }
  function cart() {
    const c = view.cart;
    if (!view.purse) return [];
    const out = [make('h3', 'Your cart')];
    if (!c.lines.length) return [...out, make('p', 'Empty. Add what you want, then send it to the GM.', 'note')];
    const ul = make('ul', '', 'market-cart-list');
    for (const l of c.lines) {
      const li = make('li');
      li.append(make('span', `${l.op === 'sell' ? 'Sell ' : ''}${l.name}${l.qty > 1 ? ` ×${l.qty}` : ''}`, 'grow'), make('span', l.total, 'market-p'));
      if (!c.sent) li.append(btn('Remove', () => act({ op: 'cart_remove', line: l.id }), 'quiet'));
      ul.append(li);
    }
    out.push(ul, make('p', `Cost ${money(c.buy_cp)}${c.sell_cp ? `, selling for ${money(c.sell_cp)}` : ''}.`));
    out.push(c.sent ? make('p', 'With the GM, waiting for an answer. ', 'market-wait') : make('p'));
    out[out.length - 1].append(c.sent ? btn('Take it back', () => act({ op: 'take_back' }), 'quiet')
      : btn('Send to the GM', () => act({ op: 'send' })));
    return out;
  }
  function bag() {
    const p = view.purse;
    if (!p) return [];
    const out = [make('h3', 'Your bag')];
    if (!p.bag.length) return [...out, make('p', 'Nothing yet.', 'note')];
    const ul = make('ul', '', 'market-bag');
    for (const b of p.bag) {
      const li = make('li');
      const back = Math.floor(b.value_cp * view.shop.buyback / 100);
      li.append(make('span', `${b.name}${b.qty > 1 ? ` ×${b.qty}` : ''}`, 'grow'));
      if (!view.cart.sent) li.append(btn(`Sell one for ${money(back)}`, () => act({ op: 'cart_sell', entry: b.id, qty: 1 }), 'quiet'));
      ul.append(li);
    }
    return [...out, ul, make('p', `This shop buys back at ${view.shop.buyback}% of an item's value.`, 'note')];
  }
  function partyLoot() {                                          // LOOT-01: what the party found, and this character's share
    const L = view.loot;
    if (!L?.finds?.length) return [];
    const ul = make('ul', '', 'market-bag');
    for (const f of L.finds) ul.append(make('li', f.text));
    const s = lootSummary(L), mine = view.purse && L.who.some(n => n.toLowerCase() === view.purse.name.toLowerCase());
    const out = [make('h3', 'Party loot'), ul, make('p', s.coins)];
    if (s.share) out.push(make('p', s.share, 'market-loot-each'));
    if (mine && L.each_cp) out.push(make('p', `Your share: ${L.each}. The GM pays it into your purse.`, 'market-gold'));
    return out;
  }
  async function refresh() {
    const out = await api.post({ op: 'view' }).catch(() => null);
    if (out?.ok) { view = out; show(); draw(); }
    return out;
  }
  fab.addEventListener('click', () => { error = ''; if (!dialog.open) dialog.showModal(); draw(true); });
  refresh();
  const poll = setInterval(refresh, every);
  return { dialog, fab, refresh, stop: () => clearInterval(poll), get view() { return view; } };
}
