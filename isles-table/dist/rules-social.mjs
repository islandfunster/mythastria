// GM 2026-10-25: the optional Social interaction rules pack's page. Reads GET /api/rules/social (Mythastria
// sim/social_pack.py): the creature-type table, instinct, factions and every SRD 5.2.1 creature's disposition. Every item
// has an anchor (type-<type>, instinct, faction-<id>, c-<creature>) so the GM's screen can link its asterisk to it.
import { api } from './server.mjs';                            // PLAYER-SITE-01: the GM's Mythastria
const $ = id => document.getElementById(id);
const el = (tag, cls, text) => { const e = document.createElement(tag); if (cls) e.className = cls; if (text != null) e.textContent = text; return e; };
const status = (text, error = false) => { $('status').textContent = text; $('status').className = error ? 'error' : ''; };
const ITEM = item => item?.startsWith('faction-') ? 'its faction' : item?.startsWith('type-') ? 'its type' : item === 'instinct' ? 'instinct' : 'the types table';
let creatures = [];

function cells(tr, ...values) { for (const v of values) tr.append(v instanceof Node ? (() => { const td = el('td'); td.append(v); return td; })() : el('td', null, v ?? '—')); return tr; }

function drawCreatures() {
  const q = $('find').value.trim().toLowerCase(), show = $('show').value;
  const rows = creatures.filter(c => (!q || c.name.toLowerCase().includes(q)) && (!show || c.attitude === show));
  $('counts').textContent = `${rows.length} of ${creatures.length} creatures`;
  $('creature-rows').replaceChildren(...rows.map(c => {
    const tr = el('tr'); tr.id = c.anchor;
    const why = el('span', null, c.why + ' ');
    const link = el('a', null, `(${ITEM(c.item)})`); link.href = '#' + c.item;
    why.append(link);
    return cells(tr, c.name, c.cr ?? '', el('span', 'att ' + c.attitude, c.attitude), why);
  }));
}

async function start() {
  let out;
  try { out = await (await fetch(api('/api/rules/social'))).json(); }
  catch { status('The Mythastria service did not answer: start Mythastria, then reload.', true); return; }
  if (!out.ok) { status(out.error || 'The pack could not be read.', true); return; }
  const p = out.pack;
  $('type-rows').replaceChildren(...Object.entries(p.types).map(([key, t]) => {
    const tr = el('tr'); tr.id = 'type-' + key;
    return cells(tr, key[0].toUpperCase() + key.slice(1), el('span', 'att ' + t.attitude, t.attitude), t.skill ?? 'None (immune)', t.helps, t.hurts);
  }));
  $('instinct-text').textContent = p.instinct.text;
  $('faction-list').replaceChildren(...Object.entries(p.factions).map(([key, f]) => {
    const d = el('div', 'faction'); d.id = 'faction-' + key;
    d.append(el('h3', null, f.name), el('p', null, f.text), el('p', 'counts', `Disposition: ${f.attitude}. Members by default: ${f.members.join(', ')}. ` +
      `A map or adventure can name the faction on any creature ("faction": "${key}").`));
    return d;
  }));
  creatures = out.creatures;
  $('credit').textContent = p.credit;
  drawCreatures();
  status('');
  if (location.hash) document.getElementById(location.hash.slice(1))?.scrollIntoView({ block: 'center' });
}
$('find').addEventListener('input', drawCreatures);
$('show').addEventListener('change', drawCreatures);
start();
