// GM 2026-10-24 ("The adventure can have a default hostility for each level. or even encounter if it's written into
// the adventure as a narrative. Morale should also be part of the prep along-side hostility. That can be added to
// remix."): Remix Prep's Attitudes and morale. For a map: the GM's default attitude per level, this encounter's
// default, and each creature group's attitude and morale; saved with the campaign (POST /api/prep; the rules and every
// check live in Mythastria tools/remix_prep.py and sim/attitude.py). Play live uses them when Saved Remix Prep is on.
import { createRemixPort } from './remix-port.mjs';
import { packStar } from './scene-ui.mjs';

const LEVELS = [1, 2, 3, 4, 5, 6, 7, 8];
const WHEN_ORDER = ['half', 'quarter', 'leader', 'outnumbered'];

export function mountPrep(doc = document, port = createRemixPort()) {
  const $ = id => doc.getElementById(id);
  const el = (tag, text, cls) => { const e = doc.createElement(tag); if (text !== undefined) e.textContent = text; if (cls) e.className = cls; return e; };
  let st = null;
  const say = (text, error = false) => { $('prep-status').textContent = text; $('prep-status').className = error ? 'error' : ''; };
  const attitudeSelect = (value, label, blank) => {
    const s = el('select'); s.setAttribute('aria-label', label);
    s.append(new Option(blank, ''));
    for (const a of st.attitudes) s.append(new Option(a, a, a === value, a === value));
    return s;
  };
  function draw() {
    // GM 2026-10-25: the campaign's optional Social rules pack (creature dispositions on first meeting), Remix on or off
    const box = $('prep-optional');
    if (box) {
      const l = el('label'); const c = el('input'); c.type = 'checkbox'; c.id = 'prep-social'; c.checked = !!st.optional?.social;
      const link = el('a', 'about the pack'); link.href = 'rules-social.html'; link.target = '_blank'; link.rel = 'noopener';
      l.append(c, " Social rules pack: creatures start with their faction's or type's disposition (Intelligence 4+ is social) ");
      box.replaceChildren(l, '(', link, ')');
    }
    $('prep-levels').replaceChildren(...LEVELS.map(lv => {
      const l = el('label', `Level ${lv} `); const s = attitudeSelect(st.levels[String(lv)] || '', `Level ${lv} default`, '—');
      s.dataset.level = String(lv);
      if (st.pack?.levels?.[String(lv)]) s.title = `The adventure says ${st.pack.levels[String(lv)]}`;
      l.append(s); return l;
    }));
    const enc = attitudeSelect(st.encounter || '', 'This encounter\'s default', st.pack?.encounter ? `As the adventure says (${st.pack.encounter})` : 'As written');
    $('prep-encounter').replaceChildren(enc); enc.id = 'prep-encounter-pick';
    const kinds = st.kinds.map(k => k.kind);
    $('prep-groups').replaceChildren(...st.kinds.map(k => {
      const tr = el('tr'); tr.dataset.kind = k.kind;
      const att = attitudeSelect(k.attitude || '', `${k.kind} attitude`, 'Default');
      att.className = 'prep-att';
      const rule = el('select'); rule.className = 'prep-rule'; rule.setAttribute('aria-label', `${k.kind} morale`);
      for (const [v, t] of Object.entries(st.rules)) rule.append(new Option(t, v, v === (k.morale?.rule || 'fight'), v === (k.morale?.rule || 'fight')));
      const when = el('div', undefined, 'prep-when');
      for (const w of WHEN_ORDER) {
        const l = el('label'); const c = el('input'); c.type = 'checkbox'; c.value = w; c.checked = (k.morale?.when || []).includes(w);
        l.append(c, ' ' + st.when[w].replace('its leader is out of the fight', 'leader out')); when.append(l);
      }
      const lead = el('select'); lead.className = 'prep-leader'; lead.setAttribute('aria-label', `${k.kind} leader`);
      lead.append(new Option('Leader…', ''));
      for (const o of kinds.filter(o => o !== k.kind)) lead.append(new Option(o, o, o === k.morale?.leader, o === k.morale?.leader));
      when.append(lead);
      const starts = el('td', `${k.starts}`); starts.title = `From ${k.from}. Its nature: ${k.nature} (${k.nature_why}).`;
      if (k.pack?.item) starts.append(' ', packStar(k.pack, doc));   // GM 2026-10-25: the Social rules pack's item
      const name = el('td', `${k.kind} ×${k.count}`);
      const a = el('td'); a.append(att); const r = el('td'); r.append(rule, when);
      tr.append(name, a, starts, r, el('td', k.morale_text, 'note'));
      return tr;
    }));
  }
  function collect() {
    const levels = {};
    $('prep-levels').querySelectorAll('select').forEach(s => { if (s.value) levels[s.dataset.level] = s.value; });
    const groups = {};
    $('prep-groups').querySelectorAll('tr').forEach(tr => {
      const g = {}, att = tr.querySelector('.prep-att').value, rule = tr.querySelector('.prep-rule').value;
      if (att) g.attitude = att;
      if (rule !== 'fight') {
        g.morale = { rule, when: [...tr.querySelectorAll('.prep-when input:checked')].map(c => c.value) };
        if (g.morale.when.includes('leader')) g.morale.leader = tr.querySelector('.prep-leader').value;
      }
      if (Object.keys(g).length) groups[tr.dataset.kind] = g;
    });
    const social = $('prep-social');
    return { levels, prep: { attitude: $('prep-encounter-pick').value || null, groups },
             ...(social ? { optional: { social: social.checked } } : {}) };
  }
  const query = () => ({ campaign: $('campaign').value.trim(), scenario: $('prep-map').value, level: Number($('prep-level').value) || 1 });
  async function load() {
    if (!$('prep-map').value) return;
    try { st = await port.prep({ op: 'state', ...query() }); draw(); say(`Revision ${st.revision}. Starting attitudes shown for level ${st.level}.`); }
    catch (e) { say(e.message, true); }
  }
  async function save() {
    if (!st) return;
    try {
      st = await port.prep({ op: 'save', ...query(), revision: st.revision, ...collect() });
      draw(); say('Saved with the campaign. Play live uses it when Saved Remix Prep is ticked.');
    } catch (e) { say(e.message, true); }
  }
  async function start() {
    const hello = await port.hello();
    // GM 2026-10-25 ("The remix must only allow the chosen encounter in the Adventure loaded"): with an adventure loaded,
    // only its maps; opened for one encounter (?prep=<map>), that encounter only.
    const all = hello.scenarios ?? [], adventure = all.filter(n => n.startsWith('pack/') && !/_L\d+\.json$/.test(n));   // not a map's level versions (GM 2026-10-25)
    const names = adventure.length ? adventure : all;
    const wanted = new URLSearchParams(location.search).get('prep');
    const chosen = wanted && (all.includes(wanted) ? wanted : hello.scenario_aliases?.[wanted]);
    $('prep-map').replaceChildren(...(chosen ? [chosen] : names).map(n => new Option(n, n)));
    if (chosen) { $('prep-map').value = chosen; $('prep-map').disabled = true; $('prep-map').title = 'Chosen on Play an adventure: prep for this encounter only.'; }
    await load();
  }
  for (const id of ['prep-map', 'prep-level']) $(id).addEventListener('change', load);
  $('campaign').addEventListener('change', load);
  $('prep-save').addEventListener('click', save);
  $('prep-reload').addEventListener('click', load);
  const ready = start().catch(e => say(e.message, true));
  return { ready, collect, load };
}
if (typeof document !== 'undefined' && document.getElementById('prep-panel')) mountPrep();
