// CHARACTERS-01 phase 3: a readable character sheet (built or imported), drawn from an isles-character/1 record. The numbers
// of a built sheet are the simulator service's (sim/character_build.py `derived`); an imported sheet shows its own.
// Features the simulator can't play are marked "GM rules this" (the sheet's `gm_rules`, also from the service).
const el = (tag, text, cls) => { const n = document.createElement(tag); if (text !== undefined && text !== null) n.textContent = text; if (cls) n.className = cls; return n; };
const signed = n => (n >= 0 ? '+' : '') + n;
const mod = s => Math.floor((Number(s) - 10) / 2);
const AB = [['str', 'Strength'], ['dex', 'Dexterity'], ['con', 'Constitution'], ['int', 'Intelligence'], ['wis', 'Wisdom'], ['cha', 'Charisma']];
const SKILL_AB = { Acrobatics: 'dex', 'Animal Handling': 'wis', Arcana: 'int', Athletics: 'str', Deception: 'cha', History: 'int', Insight: 'wis', Intimidation: 'cha', Investigation: 'int', Medicine: 'wis', Nature: 'int', Perception: 'wis', Performance: 'cha', Persuasion: 'cha', Religion: 'int', 'Sleight of Hand': 'dex', Stealth: 'dex', Survival: 'wis' };
const ORD = ['', '1st', '2nd', '3rd', '4th', '5th', '6th', '7th', '8th', '9th'];

export function classLine(c) { return (c.classes ?? []).map(k => `${k.name}${k.level ? ' ' + k.level : ''}${k.subclass ? ' (' + k.subclass + ')' : ''}`).join(' / '); }

function box(title, ...kids) { const b = el('section', undefined, 'sheet-box'); b.append(el('h4', title), ...kids.filter(Boolean)); return b; }
// GM 2026-10-28 ("there needs to be a full character sheet with collapsed menues"): with `fold` (a key for this browser's memory) each
// section is a fold, closed until opened; the browser remembers which are open
function foldBox(key, title, ...kids) {
  const b = el('details', undefined, 'sheet-box sheet-fold'), s = el('summary'), id = `mythastria-sheet-fold:${key}:${title.split(' (')[0]}`;
  s.append(el('h4', title)); b.append(s, ...kids.filter(Boolean));
  try { b.open = localStorage.getItem(id) === '1'; } catch { /* closed */ }
  b.addEventListener('toggle', () => { try { localStorage.setItem(id, b.open ? '1' : '0'); } catch { /* this visit only */ } });
  return b;
}
const ATTACK_DIE = /^(\d+)d(\d+)([+-]\d+)?$/;
// the fight's own attacks (sim/character_build.py member(): weapon, offhand, ranged) in the sheet's row shape
function buildRows(b) {
  return ['weapon', 'offhand', 'ranged'].map(k => [k, b?.[k]]).filter(([, w]) => w).map(([k, w]) => {
    const m = ATTACK_DIE.exec(String(w.dmg).replace(/\s/g, ''));
    return { name: w.name, atk: w.atk, count: m ? +m[1] : 1, die: m ? +m[2] : 0, bonus: m && m[3] ? +m[3] : 0, type: w.dmgtype, reach: w.reach,
      melee: !w.cantrip && w.reach <= 10, note: k === 'offhand' ? 'Bonus Action (Light)' : w.cantrip ? 'cantrip' : '' };
  });
}
function stat(label, value, sub) { const s = el('div', undefined, 'sheet-stat'); s.append(el('b', value), el('span', label)); if (sub) s.title = sub; return s; }

// fold: a key (this sheet's id) to fold each section; build: the fight's member (its attacks and slots, for a sheet
// without worked-out numbers, an imported one)
export function renderSheet(c, { gmRules = c.gm_rules ?? [], head: withHead = true, fold = null, build = null } = {}) {
  const d = c.derived ?? null, k = c.combat ?? {}, root = el('div', undefined, 'sheet-view' + (fold ? ' sheet-folded' : ''));
  const section = fold ? (title, ...kids) => foldBox(fold, title, ...kids) : box;
  const level = d?.level ?? (c.classes ?? []).reduce((n, x) => n + (x.level || 0), 0);
  const pb = d?.proficiency_bonus ?? (level ? 2 + Math.floor((level - 1) / 4) : null);
  const head = el('div', undefined, 'sheet-head');
  head.append(el('h3', c.name || 'Unnamed'), el('p', [c.species + (c.lineage ? ` (${c.lineage})` : ''), classLine(c), c.background].filter(Boolean).join(' · '), 'char-note'));
  if (withHead) root.append(head);

  // the fight numbers
  const nums = el('div', undefined, 'sheet-stats');
  nums.append(stat('Hit points', k.hp_max ?? '?', d?.hp_how), stat('Armor Class', k.ac ?? '?', d?.ac_how), stat('Speed', (k.speed ?? '?') + ' ft', d?.speed_how),
    stat('Initiative', d ? signed(d.initiative) : c.abilities?.dex != null ? signed(mod(c.abilities.dex)) : '?'), stat('Proficiency', pb ? signed(pb) : '?'));
  if (d?.passive_perception) nums.append(stat('Passive Perception', d.passive_perception));
  root.append(nums);

  const abil = el('div', undefined, 'sheet-abilities');
  for (const [a, name] of AB) {
    const v = c.abilities?.[a], cell = el('div', undefined, 'sheet-ability');
    const save = d?.saves?.[a] ?? (v != null ? mod(v) + ((c.saves ?? []).includes(a) && pb ? pb : 0) : null);
    cell.append(el('span', name), el('b', v ?? '?'), el('i', v != null ? signed(mod(v)) : ''), el('small', save != null ? `save ${signed(save)}${(c.saves ?? []).includes(a) ? ' •' : ''}` : ''));
    abil.append(cell);
  }
  root.append(fold ? section('Abilities and saving throws', abil) : abil);

  // attacks
  const atk = el('table', undefined, 'char-table'), head2 = el('tr');
  for (const h of ['Attack', 'To hit / DC', 'Damage', 'Range', 'Notes']) head2.append(el('th', h));
  atk.append(head2);
  const rows = d?.attacks ?? (build ? buildRows(build) : null) ?? (k.attack_bonus != null ? [{ name: c.attack_name ?? 'Attack', atk: k.attack_bonus, count: k.damage_count ?? 1, die: k.damage_die, bonus: k.damage_bonus, reach: k.reach ?? 5, melee: true }] : []);
  for (const a of rows) {
    const tr = el('tr'), dmg = `${a.count}d${a.die}${a.bonus ? (a.bonus > 0 ? '+' : '') + a.bonus : ''}${a.type ? ' ' + a.type : ''}`;
    const notes = [a.note ?? '', a.mastery ? 'Mastery: ' + a.mastery : '', a.beams > 1 ? a.beams + ' beams' : '', a.proficient === false ? 'not proficient' : '', a.two_handed ? 'two-handed' : ''].filter(Boolean).join(', ');
    tr.append(el('td', a.name), el('td', a.atk != null ? signed(a.atk) : `DC ${a.save_dc}`), el('td', dmg), el('td', a.melee ? `${a.reach} ft` : `${a.reach} ft`), el('td', notes));
    atk.append(tr);
  }
  const per = d?.attacks_per_action ?? build?.attacks;
  const atkBox = section(`Attacks${per > 1 ? ` (${per} per Attack action)` : ''}${d?.crit && d.crit < 20 ? ` · critical hit on ${d.crit}-20` : ''}`, atk);
  root.append(atkBox);

  // skills
  const skills = el('div', undefined, 'sheet-skills');
  const profs = new Set((c.proficiencies ?? []).map(p => String(p).replace(' (expertise)', '')));
  const expert = new Set((c.proficiencies ?? []).filter(p => String(p).endsWith('(expertise)')).map(p => String(p).replace(' (expertise)', '')));
  for (const [s, a] of Object.entries(SKILL_AB)) {
    const v = d?.skills?.[s] ?? (c.abilities?.[a] != null ? mod(c.abilities[a]) + (expert.has(s) ? 2 * (pb ?? 2) : profs.has(s) ? pb ?? 2 : 0) : null);
    skills.append(el('span', `${expert.has(s) ? '◆' : profs.has(s) ? '●' : '○'} ${s} ${v != null ? signed(v) : ''}`, profs.has(s) ? 'on' : ''));
  }
  root.append(section('Skills (● proficient, ◆ expertise)', skills));

  // spellcasting
  if (d?.casting?.length || (c.spells ?? []).length) {
    const sp = el('div');
    for (const k2 of d?.casting ?? []) sp.append(el('p', `${k2.class}: ${k2.ability.toUpperCase()}, save DC ${k2.dc}, spell attack ${signed(k2.attack)}; ${k2.cantrips} cantrips, ${k2.prepared} prepared, up to level ${k2.max_level}`, 'char-note'));
    const slots = d?.slots ?? build?.slots;
    if (!d && build?.spell_atk != null) sp.append(el('p', `Spell attack ${signed(build.spell_atk)}, save DC ${build.spell_dc}`, 'char-note'));
    if (slots?.length) sp.append(el('p', 'Spell slots: ' + slots.map((n, i) => `${ORD[i + 1]} ${n}`).join(' · '), 'char-note'));
    if (d?.pact) sp.append(el('p', `Pact Magic: ${d.pact.slots} slot${d.pact.slots > 1 ? 's' : ''} of level ${d.pact.level}`, 'char-note'));
    const byLevel = new Map();
    for (const s of c.spells ?? []) { const lv = typeof s === 'string' ? '?' : s.level ?? '?'; if (!byLevel.has(lv)) byLevel.set(lv, []); byLevel.get(lv).push(s); }
    for (const [lv, list] of [...byLevel.entries()].sort((a, b) => (a[0] === '?' ? 99 : a[0]) - (b[0] === '?' ? 99 : b[0]))) {
      const p = el('p'); p.append(el('b', lv === 0 ? 'Cantrips: ' : lv === '?' ? 'Spells: ' : `Level ${lv}: `));
      p.append(list.map(s => typeof s === 'string' ? s : s.name + (s.always ? '*' : '') + (s.source && !['Wizard', 'Cleric', 'Druid', 'Bard', 'Sorcerer', 'Warlock', 'Paladin', 'Ranger'].includes(s.source) ? ` (${s.source})` : '')).join(', '));
      sp.append(p);
    }
    if ((c.spells ?? []).some(s => s?.always)) sp.append(el('p', '* always prepared', 'char-note'));
    root.append(section('Spellcasting', sp));
  }

  // features: plays in the simulator, or the GM rules it
  const gm = new Set(gmRules.map(g => String(g).replace(/ \((spell|feat)\)$/, '')));
  const feat = el('div');
  const byLv = d?.features_by_level ?? [];
  const list = byLv.length ? byLv.map(([lv, src, n]) => [`${src} ${lv}`, n]) : (c.features ?? []).map(f => ['', typeof f === 'string' ? f : f?.name]);
  const ul = el('ul', undefined, 'sheet-features');
  for (const [where, n] of list) {
    if (!n) continue;
    const li = el('li'); li.append(el('span', n), ' ');
    if (where) li.append(el('small', where + ' '));
    li.append(el('span', gm.has(n) ? 'GM rules this' : 'plays in the simulator', gm.has(n) ? 'tag gm' : 'tag ok'));
    ul.append(li);
  }
  feat.append(ul);
  if ((c.feats ?? []).length) feat.append(el('p', 'Feats: ' + c.feats.join(', '), 'char-note'));
  if (d?.resources?.length) feat.append(el('p', 'Uses: ' + d.resources.map(([n, v]) => `${n} ${v}`).join(' · '), 'char-note'));
  const gmOnly = gmRules.filter(g => !list.some(([, n]) => n === String(g)));
  if (gmOnly.length) feat.append(el('p', 'GM rules this too: ' + gmOnly.join(', '), 'char-note'));
  root.append(section('Features and traits', feat));

  const misc = el('div');
  for (const [label, v] of [['Equipment', c.equipment], ['Languages', c.languages], ['Tools', c.tools], ['Resistances', c.damage_resistances]])
    if (v?.length) misc.append(el('p', `${label}: ${v.map(x => typeof x === 'string' ? x : x?.name).join(', ')}`, 'char-note'));
  if (c.senses) misc.append(el('p', 'Senses: ' + c.senses, 'char-note'));
  if (misc.childNodes.length) root.append(section('Gear and more', misc));
  if (fold && c.notes) root.append(section('Notes', el('p', c.notes, 'char-note')));
  return root;
}
