// REMIX-01 on Play live (GM 2026-10-20: "We need the remix built"; "As long as the encounters are customizable and
// recommendations are offered by Remix then it's okay to attach."). The Remix panel: the map's encounter by kind, a
// count and a replacement for each (recommendations first, then any creature), quick remixes (fresh faces, easier,
// harder), the XP total and its band as you edit, and Start remixed fight. The Python simulator service makes the
// offer (/api/remix) and applies the remix to one fight (/api/live/new with `remix`); the map file never changes.
// 2026-10-21 (GM: "Training doesn't have a way to populate the combat table"): Add a creature, any SRD 5.2.1 creature
// from the library and a count, placed by the service on free floor near the map's foe start or a square the GM clicks.
// 2026-10-21, creature lineups: Save this lineup keeps the fight's creatures by kind under a name (the service's
// /api/lineups, SRD 5.2.1 library creatures only); Load puts a lineup onto any map, replacing its creatures or added.

export function bandOf(xp, budget) {
  return xp < budget.low ? 'below Low' : xp < budget.moderate ? 'Low' : xp < budget.high ? 'Moderate' : xp <= budget.high ? 'High' : 'above High';
}

// The changes for the service from the editor rows: only kinds that changed (count or creature).
export function changesOf(rows) {
  return rows.filter(r => r.count !== r.original.count || r.to !== r.original.name)
    .map(r => ({ from: r.original.name, to: r.to, count: r.count }));
}

export function totalXp(rows, xpOf, added = []) {
  return rows.reduce((sum, r) => sum + (xpOf(r.to) ?? 0) * r.count, 0) + added.reduce((sum, a) => sum + (xpOf(a.name) ?? 0) * a.count, 0);
}

// The remix for the service: the changed kinds and the added ones (the square only when the GM picked one); null for none.
export function remixOf(rows, added, seed) {
  const changes = changesOf(rows), add = added.map(a => ({ name: a.name, count: a.count, ...(a.at ? { at: a.at } : {}) }));
  return changes.length || add.length ? { seed, changes, ...(add.length ? { add } : {}) } : null;
}

// A lineup from the panel: every kind the fight would have (the map's kinds kept after changes, then the added ones).
export function lineupOf(rows, added) {
  const out = new Map();
  for (const r of rows) if (r.count > 0) out.set(r.to, (out.get(r.to) ?? 0) + r.count);
  for (const a of added) out.set(a.name, (out.get(a.name) ?? 0) + a.count);
  return [...out].map(([name, count]) => ({ name, count }));
}

// Loading a lineup: 'replace' sets every map kind to 0 (as made) and adds the lineup's kinds; 'add' only adds them.
// Returns the new added list (the rows are changed in place).
export function withLineup(rows, added, creatures, mode) {
  if (mode === 'replace') { for (const r of rows) { r.to = r.original.name; r.count = 0; } added = []; }
  return [...added, ...creatures.map(c => ({ name: c.name, count: c.count, at: null }))];
}

export const describeLineup = creatures => creatures.map(c => `${c.count} ${c.name}`).join(', ');

// Creatures whose name has the typed text (any case), in the library's order.
export function matching(creatures, text) {
  const t = text.trim().toLowerCase();
  return t ? creatures.filter(c => c.name.toLowerCase().includes(t)) : creatures;
}

export function mountRemix({ document: doc = globalThis.document, button, port, settings, start, status = () => {}, pickSquare = null, current = () => null, running = () => false, creatures = () => [] }) {
  const make = (tag, text, cls) => { const e = doc.createElement(tag); if (text !== undefined) e.textContent = text; if (cls) e.className = cls; return e; };
  const dialog = make('dialog'); dialog.id = 'remix-dialog'; dialog.setAttribute('aria-labelledby', 'remix-title');
  doc.body.append(dialog);
  let offer = null, rows = [], added = [], seed = 1, builtFor = null, fromFight = false, adding = { name: 'Wolf', count: 1, at: null, filter: '' };
  let lineups = [], lineup = { name: '', mode: 'replace', note: '' };
  const lineupCall = q => (port.lineups ? port.lineups(q) : Promise.reject()).catch(() => ({ ok: false, error: 'The simulator service stopped.' }));
  const xp = new Map();
  const xpOf = name => xp.get(name);

  function option(text, value, selected) { const o = make('option', text); o.value = value; o.selected = !!selected; return o; }
  function draw() {
    const enc = offer.encounter;
    const head = make('div', undefined, 'remix-head');
    const title = make('h2', 'Remix Live'); title.id = 'remix-title';
    const party = enc.levels && new Set(enc.levels).size > 1 ? `levels ${enc.levels.join(', ')}` : `level ${enc.levels?.[0] ?? enc.level}`;   // GM 2026-10-28: saved characters at their own levels
    head.append(title, make('p', `${offer.scenario} · a party of ${enc.party_size} at ${party} · as made: ${enc.xp} XP, ${enc.band}`, 'note'));
    if (fromFight) head.append(make('p', 'Showing the remix of the fight being played: change it or add more, then Start remixed fight (it starts again).', 'note'));
    const tips = make('div', undefined, 'remix-suggestions');
    tips.append(make('span', 'Recommended:', 'note'));
    for (const s of offer.suggestions) {
      const b = make('button', `${s.label} · ${s.xp} XP, ${s.band}`, 'quiet'); b.type = 'button';
      b.addEventListener('click', () => { for (const c of s.changes) { const r = rows.find(r => r.original.name === c.from); if (r) { r.to = c.to; r.count = c.count; } } draw(); });
      tips.append(b);
    }
    const roll = make('button', 'Roll again', 'quiet'); roll.type = 'button';
    roll.addEventListener('click', () => { seed += 1; open(); });
    tips.append(roll);
    const table = make('div', undefined, 'remix-rows');
    for (const r of rows) {
      const row = make('div', undefined, 'remix-row');
      const count = make('input'); count.type = 'number'; count.min = '0'; count.max = '12'; count.value = String(r.count);
      count.setAttribute('aria-label', `How many (was ${r.original.count} ${r.original.name})`);
      count.addEventListener('change', () => { r.count = Math.max(0, Math.min(12, Math.round(Number(count.value) || 0))); count.value = String(r.count); total(); });
      const pick = make('select'); pick.setAttribute('aria-label', `Replace ${r.original.name}`);
      pick.append(option(`${r.original.name} (as made, ${r.original.xp} XP)`, r.original.name, r.to === r.original.name));
      const recs = offer.recommendations[r.original.name] ?? [];
      if (recs.length) {
        const g = make('optgroup'); g.label = 'Recommended';
        for (const c of recs) g.append(option(`${c.name} — ${c.why}`, c.name, r.to === c.name));
        pick.append(g);
      }
      const all = make('optgroup'); all.label = 'Any creature (by XP)';
      for (const c of offer.creatures) if (c.name !== r.original.name && !recs.some(x => x.name === c.name)) all.append(option(`${c.name} (${c.xp} XP)`, c.name, r.to === c.name));
      pick.append(all);
      pick.addEventListener('change', () => { r.to = pick.value; total(); });
      row.append(make('span', `${r.original.name} ×${r.original.count}`, 'remix-was'), count, make('span', 'as', 'note'), pick);
      table.append(row);
    }
    for (const a of added) {
      const row = make('div', undefined, 'remix-row remix-added');
      const count = make('input'); count.type = 'number'; count.min = '1'; count.max = '12'; count.value = String(a.count);
      count.setAttribute('aria-label', `How many ${a.name} (added)`);
      count.addEventListener('change', () => { a.count = Math.max(1, Math.min(12, Math.round(Number(count.value) || 1))); count.value = String(a.count); total(); });
      const drop = make('button', 'Remove', 'quiet'); drop.type = 'button'; drop.setAttribute('aria-label', `Remove the added ${a.name}`);
      drop.addEventListener('click', () => { added = added.filter(x => x !== a); draw(); });
      row.append(make('span', `Added: ${a.name}`, 'remix-was'), count, make('span', a.at ? `at square ${a.at[0]}, ${a.at[1]}` : "near the foes' start", 'note'), drop);
      table.append(row);
    }
    table.append(...(running() ? [flyBox()] : []), addRow(), lineupBox());
    const sum = make('p', '', 'remix-total'); sum.id = 'remix-total'; sum.setAttribute('role', 'status');
    const actions = make('div', undefined, 'remix-actions');
    const go = make('button', 'Start remixed fight'), reset = make('button', 'Reset', 'quiet'), close = make('button', 'Close', 'quiet');
    for (const b of [go, reset, close]) b.type = 'button';
    go.addEventListener('click', async () => {
      const remix = remixOf(rows, added, seed);
      dialog.close();
      await start(remix);
    });
    reset.addEventListener('click', () => { for (const r of rows) { r.to = r.original.name; r.count = r.original.count; } added = []; fromFight = false; lineup.note = ''; draw(); });
    close.addEventListener('click', () => dialog.close());
    actions.append(go, reset, close);
    dialog.replaceChildren(head, tips, table, sum, actions,
      make('p', 'Estimates by XP and, where measured, by threat. Some creatures have abilities the GM rules. The map itself never changes: a remix applies to the next fight.', 'note'));
    total();
  }
  // ON-THE-FLY-01 (GM 2026-11-02: "Those tools should be able to handle on-the-fly- adventuring and available through remix"):
  // into the fight being played, with no restart: a creature or person joins now, or the GM's words go to everyone's log (a
  // location read aloud, a puzzle put to the table). Both are steps on Undo. Traps stay on Play live's own trap tool.
  function flyBox() {
    const box = make('fieldset', undefined, 'remix-add');
    box.append(make('legend', 'On the fly: change this fight now'));
    const note = make('p', 'No restart: the fight goes on, and Undo step takes it back.', 'note'); note.setAttribute('role', 'status');
    const say = async (text, q) => {
      const out = await port.fly(q).catch(() => ({ ok: false, error: 'The simulator service stopped.' }));
      note.textContent = out.ok ? text(out) : (out.error || 'Refused.');
    };
    const pick = make('select'); pick.setAttribute('aria-label', 'Creature to bring in now');
    for (const c of offer.creatures) pick.append(option(`${c.name} (CR ${c.cr ?? '?'})`, c.name, c.name === adding.name));
    const count = make('input'); count.type = 'number'; count.min = '1'; count.max = '12'; count.value = '1'; count.setAttribute('aria-label', 'How many to bring in now');
    const mood = make('select'); mood.setAttribute('aria-label', 'Their attitude');
    for (const a of ['Hostile', 'Indifferent', 'Friendly']) mood.append(option(a, a, a === 'Hostile'));
    const now = make('button', 'Bring in now'); now.type = 'button';
    now.addEventListener('click', () => say(out => `${out.made.join(', ')} joined.`, { op: 'creature', name: pick.value, count: Math.max(1, Math.min(12, Math.round(Number(count.value) || 1))), attitude: mood.value, ...(adding.at ? { at: adding.at } : {}) }));
    const words = make('textarea'); words.maxLength = 2000; words.rows = 2; words.placeholder = 'Words for the table: a place, a puzzle, what happens next';
    words.setAttribute('aria-label', 'Words for the table');
    const send = make('button', 'Read to the table'); send.type = 'button';
    send.addEventListener('click', () => { const text = words.value.trim(); if (text) say(() => 'In everyone\'s log.', { op: 'announce', text }); });
    const line = make('div', undefined, 'remix-add-line'), talk = make('div', undefined, 'remix-add-line'), armor = make('div', undefined, 'remix-add-line');
    line.append(count, pick, mood, now);
    talk.append(words, send);
    // A spell cast between scenes (Mage Armor) doesn't carry into a new fight: the GM sets the AC for this one.
    const who = make('select'); who.setAttribute('aria-label', 'Whose AC to set');
    for (const c of creatures()) who.append(option(`${c.name} (AC ${c.ac ?? '?'})`, c.id));
    const ac = make('input'); ac.type = 'number'; ac.min = '1'; ac.max = '30'; ac.value = '14'; ac.setAttribute('aria-label', 'New AC');
    const why = make('input'); why.type = 'text'; why.maxLength = 80; why.placeholder = 'Why (e.g. Mage Armor)'; why.setAttribute('aria-label', 'Why the AC changes');
    const set = make('button', 'Set AC'); set.type = 'button';
    set.addEventListener('click', () => { if (who.value) say(() => 'AC set for this fight.', { op: 'ac', target: who.value, ac: Number(ac.value) || 10, why: why.value }); });
    armor.append(who, ac, why, set);
    // What a ruling allows: a ruling alone changes nothing on the table.
    const care = make('div', undefined, 'remix-add-line');
    const whom = make('select'); whom.setAttribute('aria-label', 'Who to heal or stabilize');
    for (const c of creatures()) whom.append(option(c.name, c.id));
    const hp = make('input'); hp.type = 'number'; hp.min = '1'; hp.max = '500'; hp.value = '5'; hp.setAttribute('aria-label', 'Hit Points to give');
    const heal = make('button', 'Heal'), steady = make('button', 'Stabilize', 'quiet'); heal.type = steady.type = 'button';
    heal.addEventListener('click', () => { if (whom.value) say(() => 'Healed.', { op: 'heal', target: whom.value, hp: Number(hp.value) || 1 }); });
    steady.addEventListener('click', () => { if (whom.value) say(() => 'Stable.', { op: 'stabilize', target: whom.value }); });
    const extra = make('button', 'Temporary HP', 'quiet'); extra.type = 'button';
    extra.addEventListener('click', () => { if (whom.value) say(() => 'Given.', { op: 'temp', target: whom.value, hp: Number(hp.value) || 1 }); });
    care.append(whom, hp, heal, extra, steady);
    // A check in a fight: the player's control is for scenes.
    const call = make('div', undefined, 'remix-add-line');
    const roller = make('select'); roller.setAttribute('aria-label', 'Who makes the check');
    for (const c of creatures().filter(c => c.pc)) roller.append(option(c.name, c.id));
    const skill = make('select'); skill.setAttribute('aria-label', 'Skill or ability');
    for (const s of ['Athletics', 'Arcana', 'Medicine', 'Perception', 'Investigation', 'Persuasion']) skill.append(option(s, s));
    for (const [v, n] of [['str', 'Strength'], ['dex', 'Dexterity'], ['con', 'Constitution'], ['int', 'Intelligence'], ['wis', 'Wisdom'], ['cha', 'Charisma']]) skill.append(option(`${n} (no skill)`, v));
    const dc = make('input'); dc.type = 'number'; dc.min = '1'; dc.max = '40'; dc.placeholder = 'DC'; dc.setAttribute('aria-label', 'DC');
    const roll = make('button', 'Call a check'); roll.type = 'button';
    roll.addEventListener('click', () => { if (roller.value) say(() => 'Rolled: see the log.', { op: 'check', target: roller.value, ...(skill.value.length === 3 ? { ability: skill.value } : { skill: skill.value }), ...(dc.value ? { dc: Number(dc.value) } : {}) }); });
    call.append(roller, skill, dc, roll);
    box.append(line, talk, armor, care, call, note, make('p', "For a trap, close this and use the trap tool in GM tools. Bring in now uses the square picked under Add a creature, if any.", 'note'));
    return box;
  }
  // Add a creature: a name filter, the library (by XP), a count, where (the foes' start or a clicked square) and Add.
  function addRow() {
    const box = make('fieldset', undefined, 'remix-add');
    box.append(make('legend', 'Add a creature'));
    const find = make('input'); find.type = 'search'; find.placeholder = 'Type to find (e.g. wolf)'; find.value = adding.filter;
    find.setAttribute('aria-label', 'Find a creature by name');
    const pick = make('select'); pick.setAttribute('aria-label', 'Creature to add');
    const add = make('button', 'Add'); add.type = 'button';
    const fill = () => {
      const list = matching(offer.creatures, adding.filter);
      if (list.length && !list.some(c => c.name === adding.name)) adding.name = list[0].name;
      pick.replaceChildren(...list.map(c => option(`${c.name} (CR ${c.cr ?? '?'}, ${c.xp} XP)`, c.name, c.name === adding.name)));
      add.disabled = !list.length;
    };
    find.addEventListener('input', () => { adding.filter = find.value; fill(); });
    pick.addEventListener('change', () => { adding.name = pick.value; });
    const count = make('input'); count.type = 'number'; count.min = '1'; count.max = '12'; count.value = String(adding.count);
    count.setAttribute('aria-label', 'How many to add');
    count.addEventListener('change', () => { adding.count = Math.max(1, Math.min(12, Math.round(Number(count.value) || 1))); count.value = String(adding.count); });
    const from = offer.foe_start ? ` (square ${offer.foe_start[0]}, ${offer.foe_start[1]})` : '';
    const where = make('span', adding.at ? `at square ${adding.at[0]}, ${adding.at[1]}` : `near the foes' start${from}`, 'note');
    const spot = make('button', adding.at ? "Use the foes' start" : 'Pick a square on the map', 'quiet'); spot.type = 'button';
    spot.hidden = !pickSquare && !adding.at;
    spot.addEventListener('click', async () => {
      if (adding.at) { adding.at = null; draw(); return; }
      dialog.close();
      const sq = await pickSquare(settings().scenario);
      if (sq) adding.at = sq;
      draw();
      dialog.showModal();
    });
    add.addEventListener('click', () => {
      if (!pick.value) return;
      added.push({ name: pick.value, count: adding.count, at: adding.at });
      adding.at = null;
      draw();
    });
    fill();
    const line = make('div', undefined, 'remix-add-line'), place = make('div', undefined, 'remix-add-line');
    line.append(count, pick, add);
    place.append(where, spot);
    box.append(find, line, place);
    return box;
  }
  // Creature lineups: a name and Save this lineup; the saved ones with Load (replacing the map's creatures or added
  // to them) and Delete. The service checks every name against the SRD 5.2.1 library on saving and on loading.
  function lineupBox() {
    const box = make('fieldset', undefined, 'remix-add remix-lineups');
    box.append(make('legend', 'Creature lineups'));
    const name = make('input'); name.type = 'text'; name.maxLength = 40; name.placeholder = 'Name (e.g. Wolf pack)'; name.value = lineup.name;
    name.setAttribute('aria-label', 'Name of this lineup');
    name.addEventListener('input', () => { lineup.name = name.value; });
    const save = make('button', 'Save this lineup'); save.type = 'button';
    save.addEventListener('click', async () => {
      const creatures = lineupOf(rows, added);
      if (!creatures.length) { lineup.note = 'Nothing to save: every count is 0.'; draw(); return; }
      const out = await lineupCall({ op: 'save', name: lineup.name, creatures });
      if (out.ok) lineups = out.lineups;
      lineup.note = out.ok ? `Saved "${lineup.name.trim()}": ${describeLineup(creatures)}.` : out.error;
      draw();
    });
    const line = make('div', undefined, 'remix-add-line');
    line.append(name, save);
    box.append(line);
    if (lineups.length) {
      const mode = make('select'); mode.setAttribute('aria-label', 'Loading a lineup');
      mode.append(option("Replace the map's creatures", 'replace', lineup.mode === 'replace'), option('Add to them', 'add', lineup.mode === 'add'));
      mode.addEventListener('change', () => { lineup.mode = mode.value; });
      const how = make('div', undefined, 'remix-add-line');
      how.append(make('span', 'Load a lineup:', 'note'), mode);
      const list = make('ul', undefined, 'remix-lineup-list');
      for (const l of lineups) {
        const item = make('li'), load = make('button', 'Load', 'quiet'), drop = make('button', 'Delete', 'quiet');
        load.type = drop.type = 'button';
        load.setAttribute('aria-label', `Load the lineup ${l.name}`); drop.setAttribute('aria-label', `Delete the lineup ${l.name}`);
        load.addEventListener('click', async () => {
          const out = await lineupCall({ op: 'load', name: l.name });
          if (out.ok) {
            added = withLineup(rows, added, out.lineup.creatures, lineup.mode);
            lineup.note = `Loaded "${out.lineup.name}" (${lineup.mode === 'replace' ? "replacing the map's creatures" : 'added to them'}). Start remixed fight when ready.`;
          } else lineup.note = out.error;
          draw();
        });
        drop.addEventListener('click', async () => {
          if (!(globalThis.confirm?.(`Delete the lineup "${l.name}"?`) ?? true)) return;
          const out = await lineupCall({ op: 'delete', name: l.name });
          if (out.ok) lineups = out.lineups;
          lineup.note = out.ok ? `Deleted "${l.name}".` : out.error;
          draw();
        });
        const gone = l.missing?.length ? ` — ${l.missing.join(', ')} no longer in the SRD 5.2.1 library` : '';
        item.append(make('span', `${l.name}: ${describeLineup(l.creatures)} · ${l.xp} XP${gone}`, 'note'), load, drop);
        list.append(item);
      }
      box.append(how, list);
    } else box.append(make('p', 'No lineups saved yet.', 'note'));
    if (lineup.note) { const msg = make('p', lineup.note, 'note'); msg.setAttribute('role', 'status'); box.append(msg); }
    return box;
  }
  function total() {
    const n = totalXp(rows, xpOf, added), el = dialog.querySelector('#remix-total');
    if (el) el.textContent = `This remix: ${n} XP, ${bandOf(n, offer.encounter.budget)} (Low from ${offer.encounter.budget.low}, Moderate from ${offer.encounter.budget.moderate}, High up to ${offer.encounter.budget.high})`;
  }
  async function open() {
    const [out, saved] = await Promise.all([port.remix({ ...settings(), seed }).catch(() => ({ ok: false, error: 'The simulator service stopped.' })),
      lineupCall({ op: 'list' })]);
    if (!out.ok) { status('Remix Live: ' + (out.error || 'refused'), true); return; }
    if (saved.ok) lineups = saved.lineups;
    offer = out; xp.clear();
    for (const c of out.creatures) xp.set(c.name, c.xp);
    for (const k of out.encounter.kinds) if (!xp.has(k.name)) xp.set(k.name, k.xp);
    if (builtFor !== out.scenario) {                             // a fresh panel: the map as made, or the fight being played
      builtFor = out.scenario;
      rows = out.encounter.kinds.map(k => ({ scenario: out.scenario, original: k, to: k.name, count: k.count }));
      added = [];
      const now = current(out.scenario);
      fromFight = !!now;
      for (const ch of now?.changes ?? []) { const r = rows.find(r => r.original.name === ch.from); if (r) { r.to = ch.to; r.count = ch.count; } }
      added = (now?.add ?? []).map(a => ({ name: a.name, count: a.count, at: a.at ?? null }));
    }
    draw();
    if (!dialog.open) dialog.showModal();
  }
  button.addEventListener('click', () => { builtFor = null; adding.at = null; seed = 1; lineup.note = ''; open(); });
  return { dialog, open, get rows() { return rows; }, get added() { return added; } };
}
