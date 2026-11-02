// GM 2026-10-26 (goal 13, "Crafting, brewing and scribing"): downtime on the adventure home page, beside the party's day.
// The simulator service is the rules authority (Mythastria sim/downtime.py, POST /api/adventures/downtime): it lists what
// can be made, checks every prerequisite of a project (proficiency, the tool in the bag, gold, days, a prepared spell, a
// component at hand, the GM's rulings) and answers each with why and a link when it is not met. Gold comes from the
// Market's purse and the item goes into the Market's bag. This page only shows what it says and sends the GM's choices.
const el = (tag, text, cls) => { const e = document.createElement(tag); if (text !== undefined) e.textContent = text; if (cls) e.className = cls; return e; };

export function mountDowntime({ root, post, party, status, onDay = () => {} }) {
  let pack = null, view = null, options = null, plan = null, busy = false, planTimer = 0;
  const again = new Map();                                          // a look asked for while busy: state, then plan
  const form = { who: '', kind: 'craft', item: '', spell: '', base: '', tool: '', helpers: [], place: '', gm_materials: false,
    gm_spells: false, gm_more_helpers: false };
  const $ = sel => root.querySelector(sel);

  async function send(op, extra = {}) {
    if (busy && (op === 'state' || op === 'plan')) { again.set(op, extra); return null; }   // the latest look, once free
    if (!pack || busy) return null;
    const p = party();
    if (!p.members.length && !p.characters.length) { view = null; draw(); return null; }
    busy = true; root.classList.add('busy');
    try {
      const out = await post('/api/adventures/downtime', { pack, op, members: p.members, level: p.level, ...(p.characters.length ? { characters: p.characters } : {}), ...extra });
      if (out.downtime) view = out.downtime;
      if (out.options) options = out.options;
      if (out.plan) plan = out.plan;
      if (!out.ok) status(out.refused || out.error || 'Refused.', true);
      else if (out.lines?.length) status(out.lines.join(' '));
      if (out.ok && op !== 'state' && op !== 'plan') onDay();
      draw();
      return out;
    } catch { status('The simulator service is not answering.', true); return null; }
    finally {
      busy = false; root.classList.remove('busy');
      const next = again.has('state') ? 'state' : again.has('plan') ? 'plan' : null;
      if (next) { const x = again.get(next); again.delete(next); send(next, x); }
    }
  }

  function needLink(link) {                                         // as the day's: the Market, Characters, a part of this page
    if (!link) return null;
    const b = el('button', '→ ' + link.label, 'quiet day-link');
    b.addEventListener('click', () => {
      if (link.page === 'market') window.open('./play.html#market', 'mythastria-battle');
      else if (link.page.startsWith('#')) { const t = document.querySelector(link.page); t?.scrollIntoView({ block: 'center' }); t?.querySelector('input,button')?.focus(); }
      else window.open(link.page, link.page.includes('play') ? 'mythastria-battle' : '_blank');
    });
    return b;
  }
  const why = (text, link) => { const p = el('p', text, 'day-why'); const l = needLink(link); if (l) p.append(' ', l); return p; };

  // ------------------------------------------------------------------ the projects
  function project(p) {
    const box = el('div', undefined, 'dt-project dt-' + p.status);
    const head = el('div', undefined, 'day-head');
    head.append(el('strong', `${p.who}: ${p.name}`), el('span', ` ${p.kind_name}`, 'note'));
    box.append(head);
    const bar = el('div', undefined, 'day-bar'), fill = el('span');
    fill.style.width = Math.round(100 * Math.min(1, p.done / Math.max(0.01, p.days))) + '%'; bar.append(fill); box.append(bar);
    const bits = [p.progress, p.tool ? `with ${p.tool}` : '', p.helpers.length ? `helped by ${p.helpers.join(', ')}` : '', `${p.cost}${p.paid ? ' paid' : ' when the materials are found'}`];
    box.append(el('p', bits.filter(Boolean).join(' · '), 'day-line'));
    if (p.status === 'working' && p.blocked) box.append(why(`No work until this is fixed: ${p.blocked}`, p.link));
    if (p.status === 'searching') {
      box.append(el('p', `Waiting for raw materials in ${view.places[p.place] ?? p.place}${p.look?.at ? `; look again from ${p.look.at}` : ''}.`, 'day-line'));
      const b = el('button', 'Look for materials again', 'quiet'); b.disabled = !p.look?.ready; b.title = p.look?.ready ? 'Roll d100 again (75 in a city, 25 in another settlement)' : p.look?.why;
      b.addEventListener('click', () => send('look_again', { id: p.id }));
      box.append(b);
      if (!p.look?.ready) box.append(why(p.look.why, p.look.link));
    }
    if (p.status === 'done') box.append(el('p', `Done ${p.finished}: in ${p.who}'s bag.`, 'day-line dt-done-line'));
    if (p.status === 'abandoned') box.append(el('p', 'Abandoned.', 'day-line'));
    if (p.status === 'working' || p.status === 'searching') {
      const stop = el('button', 'Abandon', 'quiet');
      stop.title = p.paid ? 'The raw materials already bought are spent' : 'Nothing was paid yet';
      stop.addEventListener('click', () => { if (confirm(`Abandon ${p.name}?${p.paid ? ' The gold paid for materials is spent.' : ''}`)) send('abandon', { id: p.id }); });
      box.append(stop);
    }
    if (p.log?.length) {
      const d = el('details', undefined, 'dt-log'); d.append(el('summary', 'Its log'));
      const ol = el('ol'); for (const e of p.log) { const li = el('li'); li.append(el('span', e.when, 'day-when'), ' ' + e.text); ol.append(li); }
      d.append(ol); box.append(d);
    }
    return box;
  }

  // ------------------------------------------------------------------ a new project
  function select(label, value, choices, onChange, title) {
    const l = el('label', label + ' ', 'dt-field'), s = el('select');
    for (const c of choices) {
      if (c.group) { const g = el('optgroup'); g.label = c.group; for (const o of c.options) g.append(new Option(o.label, o.value, false, o.value === value)); s.append(g); }
      else s.append(new Option(c.label, c.value, false, c.value === value));
    }
    if (title) s.title = title;
    s.addEventListener('change', () => onChange(s.value));
    l.append(s); return l;
  }
  function check(label, on, onChange, title) {
    const l = el('label', undefined, 'check dt-field'), b = el('input'); b.type = 'checkbox'; b.checked = on;
    if (title) l.title = title;
    b.addEventListener('change', () => onChange(b.checked)); l.append(b, ' ' + label); return l;
  }
  const set = (key, value) => { form[key] = value; if (key === 'kind' || key === 'who') { form.item = ''; form.spell = ''; form.base = ''; form.tool = ''; }
    if (key === 'item') { form.base = ''; form.tool = ''; } replan(); drawForm(); };

  function itemChoices() {
    if (form.kind === 'craft') {
      const listed = options.craft.filter(r => r.tools.length), gm = options.craft.filter(r => !r.tools.length);
      return [{ label: 'Choose an item…', value: '' }, { group: 'Its tool is in the SRD', options: listed.map(r => ({ label: `${r.name} (${r.cost}; ${r.tools.join(' or ')})`, value: r.id })) },
        { group: 'The GM assigns its tool', options: gm.map(r => ({ label: `${r.name} (${r.cost})`, value: r.id })) }];
    }
    if (form.kind === 'magic') {
      const by = {};
      for (const r of options.magic) (by[r.rarity] ??= []).push({ label: `${r.name}${r.consumable ? ' (consumable)' : ''}`, value: r.id });
      return [{ label: 'Choose a magic item…', value: '' }, ...Object.entries(by).map(([rarity, opts]) => ({ group: rarity, options: opts }))];
    }
    const spells = options.spells[form.who] ?? [];
    return [{ label: spells.length ? 'Choose a spell on the sheet…' : 'No spells on this sheet', value: '' },
      ...spells.map(s => ({ label: `${s.name} (${s.level ? 'level ' + s.level : 'cantrip'}: ${options.scroll_costs[s.level].days} day${options.scroll_costs[s.level].days === 1 ? '' : 's'}, ${options.scroll_costs[s.level].cost})`, value: s.name }))];
  }

  function drawForm() {
    const box = $('#dt-form');
    if (!view || !options) { box.replaceChildren(); return; }
    const names = view.chars.map(c => c.name);
    if (!names.includes(form.who)) form.who = names[0] ?? '';
    form.helpers = form.helpers.filter(h => names.includes(h) && h !== form.who);
    const rows = [
      select('Who', form.who, view.chars.map(c => ({ label: `${c.name} (${c.gold}${c.busy ? '; making ' + c.busy : ''})`, value: c.name })), v => set('who', v)),
      select('What', form.kind, Object.entries(view.kinds).map(([k, label]) => ({ label, value: k })), v => set('kind', v)),
    ];
    if (form.kind !== 'brew') rows.push(select(form.kind === 'scribe' ? 'Spell' : 'Item', form.kind === 'scribe' ? form.spell : form.item, itemChoices(),
      v => set(form.kind === 'scribe' ? 'spell' : 'item', v)));
    const magic = form.kind === 'magic' ? options.magic.find(r => r.id === form.item) : null;
    if (magic?.bases.length) rows.push(select('Made from', form.base, [{ label: 'Choose…', value: '' }, ...magic.bases.map(b => ({ label: b, value: b }))], v => set('base', v),
      'A magic weapon or armor: the item it is made from (its cost is paid too, and its kind decides the tool)'));
    if (plan && form.kind !== 'scribe' && (plan.tools?.length > 1 || (plan.tools && !plan.tools.length))) {
      const choices = plan.tools.length ? plan.tools : options.tools.map(t => t.id);
      rows.push(select(plan.tools.length ? 'Tool' : 'Tool (the GM assigns)', form.tool || plan.tool || '', [{ label: 'Choose…', value: '' },
        ...choices.map(id => ({ label: options.tools.find(t => t.id === id)?.name ?? id, value: id }))], v => set('tool', v)));
    }
    if (form.kind === 'craft' || form.kind === 'magic') {
      const help = el('div', undefined, 'dt-field dt-helpers'); help.append(el('span', 'Assistants ', 'day-label'));
      for (const n of names.filter(n => n !== form.who))
        help.append(check(n, form.helpers.includes(n), on => { form.helpers = on ? [...form.helpers, n] : form.helpers.filter(h => h !== n); replan(); }));
      rows.push(help);
      if (form.helpers.length > 1 || form.gm_more_helpers) rows.push(check('The GM allows more than one assistant', form.gm_more_helpers, on => set('gm_more_helpers', on)));
    }
    if (form.kind === 'craft') rows.push(check('The GM rules the raw materials are available', form.gm_materials, on => set('gm_materials', on),
      'SRD 5.2.1: "The GM determines whether appropriate raw materials are available."'));
    if (form.kind === 'magic') {
      rows.push(select('Where', form.place, [{ label: 'Choose where the party is…', value: '' }, ...Object.entries(view.places).map(([k, v]) => ({ label: `${v} (${k === 'city' ? 75 : 25}% for the materials)`, value: k }))], v => set('place', v)));
      rows.push(check('The GM checks the crafter has the item\'s spells prepared (or it casts none)', form.gm_spells, on => set('gm_spells', on)));
    }
    box.replaceChildren(...rows);
  }

  function drawPlan() {
    const box = $('#dt-plan');
    if (!plan || !view) { box.replaceChildren(); return; }
    const out = [];
    if (plan.name) {
      const days = plan.workers > 1 ? `${plan.days} days of work, ${plan.calendar_days} with ${plan.workers} at work` : `${plan.days} day${plan.days === 1 ? '' : 's'} of work`;
      out.push(el('p', `${plan.name}: ${plan.cost} (${plan.why_cost}) · ${days}${plan.tool ? ' · ' + (options.tools.find(t => t.id === plan.tool)?.name ?? plan.tool) : ''}${plan.chance ? ` · materials: ${plan.chance}% chance` : ''}.`, 'day-line dt-summary'));
    }
    const list = el('ul', undefined, 'dt-needs');
    for (const n of plan.needs) {
      const li = el('li', undefined, n.met ? 'dt-met' : 'dt-unmet');
      li.append(el('span', n.met ? '✓ ' : '✗ ', 'dt-mark'), n.met ? n.need : n.why);
      const l = n.met ? null : needLink(n.link); if (l) li.append(' ', l);
      list.append(li);
    }
    out.push(list);
    const go = el('button', 'Start the project', 'day-rest-btn'); go.id = 'dt-start'; go.disabled = !plan.ready;
    go.title = plan.ready ? 'Every prerequisite is met: pay and begin' : plan.why;
    go.addEventListener('click', () => send('start', body()).then(o => { if (o?.ok) { form.item = ''; form.spell = ''; form.helpers = []; plan = null; replan(); } }));
    out.push(go);
    box.replaceChildren(...out);
  }

  const body = () => ({ who: form.who, kind: form.kind, ...(form.item ? { item: form.item } : {}), ...(form.spell ? { spell: form.spell } : {}),
    ...(form.base ? { base: form.base } : {}), ...(form.tool ? { tool: form.tool } : {}), helpers: form.kind === 'craft' || form.kind === 'magic' ? form.helpers : [],
    ...(form.place ? { place: form.place } : {}), gm_materials: form.gm_materials, gm_spells: form.gm_spells, gm_more_helpers: form.gm_more_helpers });
  function replan() {
    clearTimeout(planTimer);
    const ready = form.kind === 'brew' || (form.kind === 'scribe' ? form.spell : form.item);
    if (!ready || !form.who) { plan = null; drawPlan(); return; }
    planTimer = setTimeout(() => send('plan', body()).then(() => drawForm()), 120);
  }

  function draw() {
    root.hidden = !pack;
    if (!pack) return;
    const list = $('#dt-projects');
    if (!view) { list.replaceChildren(el('p', 'Choose the party (on the left) to see its downtime.', 'note')); $('#dt-form').replaceChildren(); $('#dt-plan').replaceChildren(); return; }
    const open = view.projects.filter(p => p.status === 'working' || p.status === 'searching'), past = view.projects.filter(p => p.status === 'done' || p.status === 'abandoned');
    const items = open.length ? open.map(project) : [el('p', 'No project under way.', 'note')];
    if (past.length) { const d = el('details', undefined, 'dt-past'); d.append(el('summary', `Finished and abandoned (${past.length})`), ...past.map(project)); items.push(d); }
    list.replaceChildren(...items);
    const work = $('#dt-work-btn'); work.disabled = !view.work.ready; work.title = view.work.ready ? 'Each day: 8 hours of work on every project, then a Long Rest' : view.work.why;
    $('#dt-work-why').replaceChildren(...(view.work.ready ? [] : [why(view.work.why, view.work.link)]));
    drawForm(); drawPlan();
  }

  $('#dt-work-btn').addEventListener('click', () => {
    const days = Number($('#dt-days').value);
    send('work', { days }).then(o => { if (o?.ok) replan(); });
  });

  return {
    show(id) { pack = id; draw(); return send('state').then(() => replan()); },
    hide() { pack = null; view = null; plan = null; draw(); },
    refresh() { return pack ? send('state').then(() => replan()) : null; },
  };
}
