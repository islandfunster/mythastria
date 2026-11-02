// CHARACTERS-01 phase 3 (GM 2026-10-21: "a first rate character builder that can quickly be tested in live"): the SRD 5.2.1
// builder on the Characters page. This page only collects choices ("mythastria-build/1"); the simulator service works out
// and checks the whole character after every change (POST /api/characters {op: character_build}, sim/character_build.py):
// levels 1-20, multiclassing, the SRD subclasses, Ability Score Improvements and feats, spells, equipment, and the numbers
// that matter in a fight. What is still to choose and what is not allowed are listed beside the sheet as you go.
// "Auto-fill the rest" fills whatever is still open with sensible picks (spells the simulator plays come first), so a
// character can be tried in Play live within seconds; every pick stays changeable.
import { renderSheet } from './character-sheet-view.mjs';

export const BUILD_FORMAT = 'mythastria-build/1';
const AB = ['str', 'dex', 'con', 'int', 'wis', 'cha'];
const ARRAY = [15, 14, 13, 12, 10, 8];
const STYLES = ['Archery', 'Defense', 'Great Weapon Fighting', 'Two-Weapon Fighting'];
const STYLE_AT = { Fighter: [1, 7], Paladin: [2], Ranger: [2] }, STYLE_OPTION = { Paladin: ['Blessed Warrior', 'Cleric'], Ranger: ['Druidic Warrior', 'Druid'] };
const EXPERTISE = { Rogue: { 1: 2, 6: 2 }, Bard: { 2: 2, 9: 2 }, Ranger: { 2: 1, 9: 2 }, Wizard: { 2: 1 } };
const SCHOLAR = ['Arcana', 'History', 'Investigation', 'Medicine', 'Nature', 'Religion'];   // the Wizard's Expertise
const METAMAGIC_AT = { 2: 2, 10: 2, 17: 2 };
const LANGS = ['Common Sign Language', 'Draconic', 'Dwarvish', 'Elvish', 'Giant', 'Gnomish', 'Goblin', 'Halfling', 'Orc'];
const ORIGIN = ['Alert', 'Magic Initiate (Cleric)', 'Magic Initiate (Druid)', 'Magic Initiate (Wizard)', 'Savage Attacker', 'Skilled'];
// spells and cantrips the simulator plays, offered first by Auto-fill (sim/character_build.py SIM_SPELL_FLAGS and class spells)
const SIM_FIRST = ['Fire Bolt', 'Eldritch Blast', 'Sacred Flame', 'Ray of Frost', 'Vicious Mockery', 'Shillelagh', 'Starry Wisp', 'Produce Flame',
  'Fireball', 'Spirit Guardians', 'Scorching Ray', 'Shatter', 'Spiritual Weapon', 'Hold Person', 'Misty Step', 'Mass Healing Word',
  'Healing Word', 'Cure Wounds', 'Bless', 'Guiding Bolt', 'Shield', 'Shield of Faith', 'Sleep', 'Burning Hands', 'Thunderwave', 'Ice Knife',
  'Command', 'Hex', 'Hellish Rebuke', 'Hideous Laughter', 'Magic Missile', 'Searing Smite', 'Mage Armor', 'Detect Magic'];
const CLASS_ART = { Barbarian: 'gladiator', Bard: 'noble', Cleric: 'priest', Druid: 'druid', Fighter: 'knight', Monk: 'gladiator', Paladin: 'knight', Ranger: 'scout', Rogue: 'spy', Sorcerer: 'mage', Warlock: 'mage', Wizard: 'mage' };

export function starterBuild() {
  return { format: BUILD_FORMAT, id: globalThis.crypto.randomUUID(), name: 'New adventurer', species: 'Human', size: 'Medium', species_skill: 'Perception',
    human_feat: 'Skilled', background: 'Soldier', background_tool: 'Dice', method: 'array', base: { str: 15, dex: 13, con: 14, int: 8, wis: 12, cha: 10 },
    boosts: { str: 2, dex: 0, con: 1, int: 0, wis: 0, cha: 0 }, languages: ['Dwarvish', 'Elvish'], feat_choices: { Skilled: ['Insight', 'Survival', 'Medicine'] },
    levels: [{ class: 'Fighter', skills: ['Acrobatics', 'History'], fighting_style: 'Defense' }], spells: {},
    equipment: { armor: 'Chain Mail', shield: false, weapons: ['Greatsword', 'Javelin'], focus: false, spellbook: false, other: '' },
    masteries: ['Greatsword', 'Javelin', 'Longbow'], notes: '', token_id: 'knight' };
}

const el = (tag, text, cls) => { const n = document.createElement(tag); if (text !== undefined && text !== null) n.textContent = text; if (cls) n.className = cls; return n; };
const button = (text, fn, cls = 'quiet') => { const b = el('button', text, cls); b.type = 'button'; b.onclick = fn; return b; };
function select(label, value, options, change) {
  const w = el('label', label), s = el('select');
  for (const o of options) { const [v, t, off] = Array.isArray(o) ? o : [o, o]; const op = el('option', t); op.value = v; op.disabled = Boolean(off); op.selected = String(v) === String(value ?? ''); s.append(op); }
  s.onchange = () => change(s.value); w.append(s); return w;
}
function input(label, value, change, type = 'text', extra = {}) {
  const w = el('label', label), i = el('input'); i.type = type; i.value = value ?? ''; Object.assign(i, extra);
  i.onchange = () => change(type === 'number' ? (i.value === '' ? null : Number(i.value)) : i.value); w.append(i); return w;
}
// a checkbox list with a count: "3 of 4 chosen"
// SPELLS-4-9 (SRD 5.2.1 Warlock): the Mystic Arcanum levels a Warlock of this level has (6 at 11, 7 at 13, 8 at 15, 9 at 17)
const arcanumLevels = n => [[6, 11], [7, 13], [8, 15], [9, 17]].filter(([, at]) => n >= at).map(([lv]) => lv);
function picks(title, options, chosen, max, change, { group } = {}) {
  const box = el('fieldset', undefined, 'pick-box'), legend = el('legend');
  const count = () => `${title}: ${chosen.length}${max != null ? ' of ' + max : ''} chosen`;
  legend.textContent = count(); box.append(legend);
  const groups = new Map();
  for (const o of options) { const g = group ? group(o) : ''; if (!groups.has(g)) groups.set(g, []); groups.get(g).push(o); }
  for (const [g, list] of groups) {
    const wrap = g ? el('details') : el('div');
    if (g) { wrap.append(el('summary', g)); wrap.open = list.some(o => chosen.includes(Array.isArray(o) ? o[0] : o)) || groups.size <= 2; }
    const grid = el('div', undefined, 'pick-grid');
    for (const o of list) {
      const [v, t] = Array.isArray(o) ? o : [o, o], lab = el('label', undefined, 'pick'), cb = el('input');
      cb.type = 'checkbox'; cb.checked = chosen.includes(v);
      cb.onchange = () => { const next = cb.checked ? [...chosen, v] : chosen.filter(x => x !== v); change(next); };
      lab.append(cb, ' ' + t); grid.append(lab);
    }
    wrap.append(grid); box.append(wrap);
  }
  return box;
}
const sect = (root, title, id) => { const s = el('section', undefined, 'build-step'); s.id = id; s.append(el('h2', title)); root.append(s); return s; };

export function createBuilder({ port, tokens = [], storage = globalThis.localStorage, key = 'mythastria-build-v2', onSheet, status }) {
  let rules = null, choices = null, result = null, timer = null, busy = false, root = null;
  try { const b = JSON.parse(storage?.getItem(key) || 'null'); if (b?.format === BUILD_FORMAT) choices = b; } catch { /* a fresh build */ }
  choices ??= starterBuild();
  const save = () => { try { storage?.setItem(key, JSON.stringify(choices)); } catch { /* a convenience */ } };

  async function loadRules() {
    if (rules) return rules;
    rules = (await port.call({ op: 'character_srd' })).rules;
    return rules;
  }
  async function check() {
    busy = true;
    try { result = await port.call({ op: 'character_build', choices }); }
    catch (e) { status?.(e.message, true); }
    finally { busy = false; }
  }
  // every change: kept, then checked by the service, then drawn again
  function changed(redraw = true) {
    save();
    clearTimeout(timer);
    timer = setTimeout(async () => { await check(); if (redraw && root?.isConnected) draw(root); }, 120);
  }

  const R = () => rules;
  const counts = () => { const n = {}; for (const e of choices.levels) n[e.class] = (n[e.class] ?? 0) + 1; return n; };
  const spellsOf = (cls, lv) => R().spells.filter(s => s.classes.includes(cls) && (lv === 0 ? s.level === 0 : s.level >= 1 && s.level <= lv));
  const maxSpell = (cls, n) => { const k = R().classes[cls].caster; return k === 'full' ? Math.min(9, Math.ceil(n / 2)) : k === 'half' ? Math.min(5, Math.ceil(n / 4)) : k === 'pact' ? R().classes.Warlock.resources.pact_level[n - 1] : 0; };
  const order = list => [...list].sort((a, b) => { const ia = SIM_FIRST.indexOf(a.name ?? a), ib = SIM_FIRST.indexOf(b.name ?? b); return (ia < 0 ? 999 : ia) - (ib < 0 ? 999 : ib) || String(a.name ?? a).localeCompare(String(b.name ?? b)); });

  // ------------------------------------------------------------ Auto-fill: whatever is open gets a sensible pick
  function autofill() {
    const r = R(), c = choices, sp = r.species[c.species];
    if (sp?.lineages && !(c.lineage in sp.lineages)) c.lineage = Object.keys(sp.lineages)[0];
    if (['Elf', 'Gnome', 'Tiefling'].includes(c.species) && !c.lineage_ability) c.lineage_ability = 'int';
    const first = c.levels[0]?.class ?? 'Fighter', prim = r.classes[first].primary;
    const bg = r.backgrounds[c.background];
    if (bg) {
      const vals = Object.values(c.boosts ?? {}).filter(Boolean).sort().join();
      if (!['1,2', '1,1,1'].includes(vals) || AB.some(a => c.boosts[a] && !bg.abilities.includes(a))) {
        c.boosts = Object.fromEntries(AB.map(a => [a, 0]));
        const two = bg.abilities.find(a => prim.includes(a)) ?? bg.abilities.find(a => a === 'con') ?? bg.abilities[0];
        c.boosts[two] = 2; c.boosts[bg.abilities.find(a => a !== two && (a === 'con' || prim.includes(a))) ?? bg.abilities.find(a => a !== two)] = 1;
      }
    }
    const skillsHave = new Set([...(bg?.skills ?? [])]);
    const take = (list, n, from) => { const out = [...list]; for (const s of from) { if (out.length >= n) break; if (!out.includes(s) && !skillsHave.has(s)) out.push(s); } out.forEach(s => skillsHave.add(s)); return out; };
    if (c.species === 'Human') { if (!ORIGIN.includes(c.human_feat)) c.human_feat = 'Skilled'; if (!c.species_skill) c.species_skill = take([], 1, ['Perception', ...Object.keys(r.skills)])[0]; else skillsHave.add(c.species_skill); }
    if (c.species === 'Elf') { if (!['Insight', 'Perception', 'Survival'].includes(c.species_skill)) c.species_skill = take([], 1, ['Perception', 'Insight', 'Survival'])[0]; else skillsHave.add(c.species_skill); }
    if ((c.languages ?? []).length !== 2) c.languages = LANGS.filter(l => !['Common Sign Language'].includes(l)).slice(1, 3);
    const seen = {};
    let scores = Object.fromEntries(AB.map(a => [a, (c.base[a] ?? 10) + (c.boosts[a] ?? 0)]));
    c.levels.forEach((e, i) => {
      const C = r.classes[e.class], n = seen[e.class] = (seen[e.class] ?? 0) + 1;
      if (n === 1 && i === 0 && (e.skills ?? []).length !== C.skill_count) e.skills = take(e.skills ?? [], C.skill_count, C.skills);
      else (e.skills ?? []).forEach(s => skillsHave.add(s));
      if (n === 1 && i > 0 && C.multiclass.skills && (e.skills ?? []).length !== C.multiclass.skills) e.skills = take([], C.multiclass.skills, C.skills);
      if (e.class === 'Bard' && n === 3 && (e.skills ?? []).length !== 3) e.skills = take([], 3, Object.keys(r.skills));
      if ((STYLE_AT[e.class] ?? []).includes(n) && !(STYLES.includes(e.fighting_style) || e.fighting_style === STYLE_OPTION[e.class]?.[0]))
        e.fighting_style = STYLES.find(s => !c.levels.some(x => x !== e && x.fighting_style === s)) ?? 'Defense';
      if (n === 1 && e.class === 'Cleric' && !['Protector', 'Thaumaturge'].includes(e.order)) e.order = 'Protector';
      if (n === 1 && e.class === 'Druid' && !['Magician', 'Warden'].includes(e.order)) e.order = 'Magician';
      if (e.class === 'Druid' && n === 3 && !e.land) e.land = 'temperate';
      if (e.class === 'Sorcerer' && n === 6 && !e.affinity) e.affinity = 'fire';      // GM 2026-10-23: Elemental Affinity
      const ex = EXPERTISE[e.class]?.[n];
      if (ex && (e.expertise ?? []).length !== ex) {
        const used = new Set(c.levels.flatMap(x => x === e ? [] : x.expertise ?? []));
        e.expertise = [...skillsHave].filter(s => !used.has(s) && r.skills[s] && (e.class !== 'Wizard' || SCHOLAR.includes(s))).sort((a, b) => ['Stealth', 'Perception', 'Athletics', 'Persuasion'].indexOf(b) - ['Stealth', 'Perception', 'Athletics', 'Persuasion'].indexOf(a)).slice(0, ex);
      }
      if (e.class === 'Warlock') {
        const t = C.resources.invocations, gain = t[n - 1] - (n > 1 ? t[n - 2] : 0);
        if ((e.invocations ?? []).length !== gain) {
          const have = c.levels.flatMap(x => x === e ? [] : x.invocations ?? []);
          const wish = ['Agonizing Blast', 'Armor of Shadows', 'Repelling Blast', "Devil's Sight", 'Eldritch Mind', 'Fiendish Vigor', 'Mask of Many Faces', 'Misty Visions', 'Otherworldly Leap', 'Ascendant Step', 'One with Shadows', 'Gaze of Two Minds', 'Master of Myriad Forms', 'Whispers of the Grave', 'Visions of Distant Realms', 'Witch Sight'];
          const lvNeed = { 'Agonizing Blast': 2, 'Repelling Blast': 2, "Devil's Sight": 2, 'Fiendish Vigor': 2, 'Mask of Many Faces': 2, 'Misty Visions': 2, 'Otherworldly Leap': 2, 'Ascendant Step': 5, 'One with Shadows': 5, 'Gaze of Two Minds': 5, 'Master of Myriad Forms': 5, 'Whispers of the Grave': 7, 'Visions of Distant Realms': 9, 'Witch Sight': 15 };
          e.invocations = wish.filter(x => !have.includes(x) && (lvNeed[x] ?? 1) <= n).slice(0, gain);
        }
      }
      if (e.class === 'Sorcerer' && METAMAGIC_AT[n] && (e.metamagic ?? []).length !== METAMAGIC_AT[n]) {
        const have = c.levels.flatMap(x => x === e ? [] : x.metamagic ?? []);
        e.metamagic = ['Quickened Spell', 'Twinned Spell', 'Careful Spell', 'Empowered Spell', 'Subtle Spell', 'Heightened Spell', 'Distant Spell', 'Extended Spell', 'Seeking Spell', 'Transmuted Spell'].filter(x => !have.includes(x)).slice(0, 2);
      }
      if (C.asi.includes(n) || n === 19) {
        if (!e.asi?.feat) {
          if (n === 19) { const a = prim.find(x => scores[x] < 30) ?? 'con'; e.asi = { feat: 'Boon of Combat Prowess', abilities: { [a]: 1 } }; scores[a] += 1; }
          else {
            const odd = [...prim, 'con'].find(x => scores[x] === 19), a = [...prim, 'con', 'dex'].find(x => scores[x] <= 18);
            if (odd) { const b = ['con', 'dex', ...AB].find(x => x !== odd && scores[x] < 20); e.asi = { feat: 'Ability Score Improvement', abilities: { [odd]: 1, [b]: 1 } }; scores[odd]++; scores[b]++; }
            else if (a) { e.asi = { feat: 'Ability Score Improvement', abilities: { [a]: 2 } }; scores[a] += 2; }
            else { const two = AB.filter(x => scores[x] < 20).slice(0, 2); e.asi = { feat: 'Ability Score Improvement', abilities: Object.fromEntries(two.map(x => [x, 1])) }; two.forEach(x => scores[x]++); }
          }
        } else for (const [a, v] of Object.entries(e.asi.abilities ?? {})) scores[a] += v;
      }
    });
    // feats' own choices
    c.feat_choices ??= {};
    const feats = [bg?.feat, c.species === 'Human' ? c.human_feat : null].filter(Boolean);
    if (feats.includes('Skilled') && (c.feat_choices.Skilled ?? []).length !== 3 * feats.filter(f => f === 'Skilled').length)
      c.feat_choices.Skilled = take([], 3 * feats.filter(f => f === 'Skilled').length, Object.keys(r.skills));
    for (const f of feats.filter(f => f.startsWith('Magic Initiate'))) {
      const list = f.match(/\((\w+)\)/)[1], m = c.feat_choices[f] ??= {};
      if ((m.cantrips ?? []).length !== 2) m.cantrips = order(spellsOf(list, 0)).slice(0, 2).map(s => s.name);
      if (!m.spell) m.spell = order(spellsOf(list, 1)).find(s => s.level === 1)?.name;
      if (!m.ability) m.ability = { Cleric: 'wis', Druid: 'wis', Wizard: 'int' }[list];
    }
    // spells, per caster class
    c.spells ??= {};
    for (const [cls, n] of Object.entries(counts())) {
      const C = r.classes[cls];
      if (C.caster === 'none') continue;
      const mine = c.spells[cls] ??= {}, top = maxSpell(cls, n);
      const extra = cls === 'Cleric' && c.levels.find(e => e.class === 'Cleric')?.order === 'Thaumaturge' || cls === 'Druid' && c.levels.find(e => e.class === 'Druid')?.order === 'Magician' ? 1 : 0;
      const canN = C.cantrips[n - 1] + extra, prepN = C.prepared[n - 1];
      if ((mine.cantrips ?? []).length !== canN) mine.cantrips = [...new Set([...(mine.cantrips ?? []), ...order(spellsOf(cls, 0)).map(s => s.name)])].slice(0, canN);
      const pool = order(spellsOf(cls, top)).sort((a, b) => { const ia = SIM_FIRST.indexOf(a.name), ib = SIM_FIRST.indexOf(b.name); return (ia < 0 ? 999 : ia) - (ib < 0 ? 999 : ib) || b.level - a.level; });
      if (cls === 'Wizard') {
        const bookN = 6 + 2 * (n - 1);
        if ((mine.book ?? []).length < bookN) mine.book = [...new Set([...(mine.book ?? []), ...pool.map(s => s.name)])].slice(0, bookN);
        if ((mine.prepared ?? []).length !== prepN) mine.prepared = [...new Set([...(mine.prepared ?? []).filter(x => mine.book.includes(x)), ...mine.book])].slice(0, prepN);
      } else if ((mine.prepared ?? []).length !== prepN) mine.prepared = [...new Set([...(mine.prepared ?? []), ...pool.map(s => s.name)])].slice(0, prepN);
      if (cls === 'Bard' && n >= 6 && (mine.discoveries ?? []).length !== 2)
        mine.discoveries = order(r.spells.filter(s => s.level <= top && s.classes.some(k => ['Cleric', 'Druid', 'Wizard'].includes(k)) && !s.classes.includes('Bard'))).slice(0, 2).map(s => s.name);
      if (cls === 'Warlock' && n >= 11 && (mine.arcanum ?? []).length !== arcanumLevels(n).length)   // SPELLS-4-9
        mine.arcanum = arcanumLevels(n).map(lv => order(spellsOf(cls, 9).filter(s => s.level === lv))[0]?.name).filter(Boolean);
    }
    for (const e of c.levels) {
      const opt = STYLE_OPTION[e.class];
      if (opt && e.fighting_style === opt[0] && (e.style_cantrips ?? []).length !== 2) e.style_cantrips = order(spellsOf(opt[1], 0)).slice(0, 2).map(s => s.name);
    }
    // equipment: armor and weapons the class can use
    const eq = c.equipment ??= {};
    const train = new Set(r.classes[first].armor);
    for (const e of c.levels) { if (e.order === 'Protector') train.add('heavy'); if (e.order === 'Warden') train.add('medium'); }
    if (!eq.armor || eq.armor === 'None') {
      const want = first === 'Barbarian' || first === 'Monk' || first === 'Sorcerer' && c.levels.length >= 3 ? 'None'
        : train.has('heavy') && scores.str >= 13 ? 'Chain Mail' : train.has('medium') ? (scores.dex >= 14 ? 'Scale Mail' : 'Scale Mail') : train.has('light') ? 'Studded Leather Armor' : 'None';
      eq.armor = want;
    }
    if (!(eq.weapons ?? []).length) {
      eq.weapons = ({ Barbarian: ['Greataxe', 'Handaxe'], Bard: ['Rapier', 'Dagger'], Cleric: ['Mace'], Druid: ['Quarterstaff', 'Sling'], Fighter: ['Greatsword', 'Javelin'],
        Monk: ['Spear', 'Dart'], Paladin: ['Longsword', 'Javelin'], Ranger: ['Longbow', 'Shortsword'], Rogue: ['Rapier', 'Shortbow'], Sorcerer: ['Dagger'], Warlock: ['Dagger'], Wizard: ['Dagger'] })[first];
      if (['Cleric', 'Paladin'].includes(first) && train.has('shield')) eq.shield = true;
    }
    if (c.levels.some(e => e.class === 'Wizard')) eq.spellbook = true;
    if (c.levels.some(e => r.classes[e.class].caster !== 'none')) eq.focus = true;
    const mastN = Math.max(0, ...c.levels.map(e => e.class).filter((v, i, a) => a.indexOf(v) === i).map(k => { const n = counts()[k], res = r.classes[k].resources ?? {}; return res.weapon_mastery ? res.weapon_mastery[n - 1] : ['Paladin', 'Ranger', 'Rogue'].includes(k) ? 2 : 0; }));
    if ((c.masteries ?? []).length !== mastN) {
      const ok = w => r.classes[first].weapons.includes(w.category) || (w.category === 'martial' && (r.classes[first].weapons.includes('martial finesse-or-light') && (w.finesse || w.light) || r.classes[first].weapons.includes('martial light') && w.light));
      c.masteries = [...new Set([...(c.masteries ?? []).slice(0, mastN), ...eq.weapons, ...r.weapons.filter(ok).map(w => w.name)])].filter(n => r.weapons.some(w => w.name === n && ok(w))).slice(0, mastN);
    }
    if (!c.token_id || !tokens.some(t => t.id === c.token_id)) c.token_id = CLASS_ART[first] ?? 'warrior_veteran';
    if (!c.name?.trim()) c.name = 'New ' + first.toLowerCase();
  }

  // ------------------------------------------------------------ drawing
  async function draw(container) {
    root = container;
    if (!rules) {
      container.replaceChildren(el('p', 'Loading the SRD 5.2.1 rules from the simulator service…', 'char-note'));
      try { await loadRules(); await check(); } catch (e) { container.replaceChildren(el('p', 'The builder needs the simulator service: ' + e.message, 'char-error')); return; }
      if (container.isConnected) draw(container);
      return;
    }
    if (!result) { await check(); }
    const keepY = window.scrollY;
    container.replaceChildren();
    const layout = el('div', undefined, 'build-layout'), form = el('div', undefined, 'build-form'), side = el('aside', undefined, 'build-side');
    layout.append(form, side); container.append(layout);
    drawSide(side);
    drawWho(form); drawScores(form); drawLevels(form); drawSpells(form); drawEquipment(form);
    window.scrollTo(0, keepY);
  }

  function drawSide(side) {
    const r = result ?? {}, s = r.sheet;
    const top = el('div', undefined, 'char-actions');
    top.append(button('Auto-fill the rest', () => { autofill(); changed(); status?.('Filled in what was still open. Change anything you like.'); }, ''),
      button('Start over', () => { if (confirm('Start a new character? The current build is replaced.')) { choices = starterBuild(); result = null; changed(); } }));
    side.append(top);
    const todo = r.todo ?? [], bad = r.errors ?? [];
    if (bad.length) { const b = el('div', undefined, 'char-warning bad'); b.append(el('strong', 'Not allowed')); for (const p of bad) b.append(el('p', `${p.where}: ${p.text}`)); side.append(b); }
    if (todo.length) { const b = el('div', undefined, 'char-warning'); b.append(el('strong', `Still to choose (${todo.length})`)); for (const p of todo) b.append(el('p', `${p.where}: ${p.text}`)); side.append(b); }
    if (r.warnings?.length) { const b = el('div', undefined, 'char-warning'); for (const p of r.warnings) b.append(el('p', `${p.where}: ${p.text}`)); side.append(b); }
    if (r.done) side.append(el('p', '✓ Every choice is made and allowed. Checked by the simulator service.', 'char-note ok-note'));
    const act = el('div', undefined, 'char-actions');
    act.append(button(r.done ? 'Use this character →' : 'Finish the choices to save', () => { if (r.done && s) onSheet?.(s, choices); }, r.done ? '' : 'quiet'));
    side.append(act);
    if (s) side.append(renderSheet(s));
  }

  function drawWho(form) {
    const r = R(), c = choices, f = sect(form, '1. Who', 'step-who'), row = el('div', undefined, 'char-fields');
    f.append(row);
    row.append(input('Name', c.name, v => { c.name = v; changed(); }));
    row.append(select('Species', c.species, Object.keys(r.species), v => { c.species = v; c.size = r.species[v].sizes.at(-1); c.lineage = ''; c.species_skill = ''; changed(); }));
    const sp = r.species[c.species];
    if (sp?.lineages) row.append(select(['Dragonborn', 'Goliath'].includes(c.species) ? 'Ancestry' : 'Lineage', c.lineage, [['', 'Choose…'], ...Object.keys(sp.lineages).map(l => [l, `${l}${['Dragonborn'].includes(c.species) ? ' (' + sp.lineages[l] + ')' : ''}`])], v => { c.lineage = v; changed(); }));
    if (sp && sp.sizes.length > 1) row.append(select('Size', c.size, sp.sizes, v => { c.size = v; changed(); }));
    if (['Elf', 'Gnome', 'Tiefling'].includes(c.species)) row.append(select('Lineage spells use', c.lineage_ability ?? 'int', [['int', 'Intelligence'], ['wis', 'Wisdom'], ['cha', 'Charisma']], v => { c.lineage_ability = v; changed(); }));
    if (c.species === 'Elf' && c.lineage === 'High Elf') row.append(select('High Elf cantrip', c.high_elf_cantrip ?? 'Prestidigitation', r.spells.filter(s => s.level === 0 && s.classes.includes('Wizard')).map(s => s.name), v => { c.high_elf_cantrip = v; changed(); }));
    if (c.species === 'Human') {
      row.append(select('Skillful: one skill', c.species_skill, [['', 'Choose…'], ...Object.keys(r.skills)], v => { c.species_skill = v; changed(); }));
      row.append(select('Versatile: an Origin feat', c.human_feat, [['', 'Choose…'], ...ORIGIN], v => { c.human_feat = v; changed(); }));
    }
    if (c.species === 'Elf') row.append(select('Keen Senses', c.species_skill, [['', 'Choose…'], 'Insight', 'Perception', 'Survival'], v => { c.species_skill = v; changed(); }));
    row.append(select('Background', c.background, Object.keys(r.backgrounds), v => { c.background = v; c.boosts = Object.fromEntries(AB.map(a => [a, 0])); changed(); }));
    row.append(select('Alignment', c.alignment ?? '', [['', 'Not set'], ...['Lawful Good', 'Neutral Good', 'Chaotic Good', 'Lawful Neutral', 'Neutral', 'Chaotic Neutral', 'Lawful Evil', 'Neutral Evil', 'Chaotic Evil'].map(a => [a, a])], v => { c.alignment = v; changed(); }));
    const bg = r.backgrounds[c.background];
    if (bg) f.append(el('p', `${c.background}: ${bg.skills.join(' and ')}, ${bg.tool}, and the ${bg.feat} feat.`, 'char-note'));
    if (c.background === 'Soldier') row.append(select('Gaming set', c.background_tool ?? 'Dice', ['Dice', 'Dragonchess', 'Playing cards', 'Three-dragon ante'], v => { c.background_tool = v; changed(); }));
    f.append(picks('Languages besides Common', LANGS, c.languages ?? [], 2, v => { c.languages = v; changed(); }));
    drawFeatChoices(f);
    const art = el('div', undefined, 'char-fields');
    art.append(select('Fallback token art (a photo replaces it)', c.token_id, tokens.filter(t => t.squares === 1).map(t => [t.id, t.name]), v => { c.token_id = v; changed(false); }));
    f.append(art);
  }

  function drawFeatChoices(f) {
    const r = R(), c = choices, bg = r.backgrounds[c.background];
    const feats = [bg?.feat, c.species === 'Human' ? c.human_feat : null].filter(Boolean);
    c.feat_choices ??= {};
    const skilled = feats.filter(x => x === 'Skilled').length;
    if (skilled) f.append(picks('Skilled: skills', Object.keys(r.skills), c.feat_choices.Skilled ?? [], 3 * skilled, v => { c.feat_choices.Skilled = v; changed(); }));
    for (const feat of [...new Set(feats.filter(x => x.startsWith('Magic Initiate')))]) {
      const list = feat.match(/\((\w+)\)/)[1], m = c.feat_choices[feat] ??= { cantrips: [], spell: '', ability: '' };
      const box = el('div', undefined, 'char-fields');
      box.append(select(`${feat}: level 1 spell`, m.spell, [['', 'Choose…'], ...spellsOf(list, 1).filter(s => s.level === 1).map(s => s.name)], v => { m.spell = v; changed(); }),
        select('Its spellcasting ability', m.ability, [['', 'Choose…'], ['int', 'Intelligence'], ['wis', 'Wisdom'], ['cha', 'Charisma']], v => { m.ability = v; changed(); }));
      f.append(box, picks(`${feat}: cantrips`, spellsOf(list, 0).map(s => s.name), m.cantrips ?? [], 2, v => { m.cantrips = v; changed(); }));
    }
  }

  function drawScores(form) {
    const r = R(), c = choices, f = sect(form, '2. Ability scores', 'step-scores'), bg = r.backgrounds[c.background];
    const row = el('div', undefined, 'char-fields');
    row.append(select('How the scores were made', c.method, [['array', 'Standard Array (15, 14, 13, 12, 10, 8)'], ['point', '27-point buy'], ['rolled', 'Rolled (the GM approves)']], v => { c.method = v; changed(); }));
    f.append(row);
    if (c.method === 'point') {
      // GM 2026-10-21: 27 points (SRD 5.2.1) is the default, shown highlighted; - / + for survival or heroic games
      const cost = { 8: 0, 9: 1, 10: 2, 11: 3, 12: 4, 13: 5, 14: 7, 15: 9 }, budget = c.point_budget ?? 27;
      const row2 = el('div', undefined, 'char-actions budget-row');
      const kind = budget === 27 ? 'Standard (SRD 5.2.1)' : budget < 27 ? 'Survival (table option)' : 'Heroic (table option)';
      row2.append(el('span', 'Point budget:'), button('−', () => { c.point_budget = Math.max(10, budget - 1); changed(); }),
        el('b', String(budget), 'budget' + (budget === 27 ? ' srd' : ' house')), button('+', () => { c.point_budget = Math.min(45, budget + 1); changed(); }),
        el('span', kind, budget === 27 ? 'tag ok' : 'tag gm'));
      if (budget !== 27) row2.append(button('Back to 27', () => { c.point_budget = 27; changed(); }));
      f.append(row2, el('p', `Points spent: ${AB.reduce((n, a) => n + (cost[c.base[a]] ?? 99), 0)} of ${budget}.`, 'char-note'));
    }
    const grid = el('table', undefined, 'char-table score-table'), h = el('tr');
    for (const t of ['', ...AB.map(a => a.toUpperCase())]) h.append(el('th', t));
    grid.append(h);
    const rowBase = el('tr'), rowBoost = el('tr'), rowFinal = el('tr');
    rowBase.append(el('th', 'Score'));
    rowBoost.append(el('th', bg ? `${c.background} +2/+1 or +1/+1/+1` : 'Background'));
    rowFinal.append(el('th', 'Final (with levels)'));
    for (const a of AB) {
      const tdB = el('td');
      if (c.method === 'array') {
        const s = el('select');
        for (const v of ARRAY) { const o = el('option', v); o.value = v; o.selected = c.base[a] === v; s.append(o); }
        s.onchange = () => { const v = Number(s.value), other = AB.find(x => x !== a && c.base[x] === v); if (other) c.base[other] = c.base[a]; c.base[a] = v; changed(); };
        tdB.append(s);
      } else {
        const i = el('input'); i.type = 'number'; i.min = c.method === 'point' ? 8 : 3; i.max = c.method === 'point' ? 15 : 18; i.value = c.base[a];
        i.onchange = () => { c.base[a] = Number(i.value); changed(); }; tdB.append(i);
      }
      rowBase.append(tdB);
      const tdP = el('td');
      if (bg?.abilities.includes(a)) {
        const s = el('select');
        for (const v of [0, 1, 2]) { const o = el('option', '+' + v); o.value = v; o.selected = (c.boosts[a] ?? 0) === v; s.append(o); }
        s.onchange = () => { c.boosts[a] = Number(s.value); changed(); }; tdP.append(s);
      } else tdP.textContent = '—';
      rowBoost.append(tdP);
      const fin = result?.sheet?.abilities?.[a];
      rowFinal.append(el('td', fin != null ? `${fin} (${fin >= 10 ? '+' : ''}${Math.floor((fin - 10) / 2)})` : '?'));
    }
    grid.append(rowBase, rowBoost, rowFinal);
    f.append(grid);
  }

  function drawLevels(form) {
    const r = R(), c = choices, f = sect(form, `3. Levels (${c.levels.length})`, 'step-levels');
    f.append(el('p', 'Add levels one at a time; each level asks only what that level gives. Hit points: the average, or a rolled die.', 'char-note'));
    const seen = {};
    c.levels.forEach((e, i) => {
      const n = seen[e.class] = (seen[e.class] ?? 0) + 1, C = r.classes[e.class];
      const card = el('div', undefined, 'level-card'), head = el('div', undefined, 'level-head');
      head.append(el('b', `Level ${i + 1}`), ' ', select('Class', e.class, Object.keys(r.classes).map(k => [k, k, i > 0 && !canTake(k, i)]), v => { c.levels[i] = { class: v }; changed(); }), el('span', `${e.class} ${n}`, 'tag'));
      if (i > 0) head.append(input(`HP (blank: average ${C.hit_die / 2 + 1})`, e.hp ?? '', v => { e.hp = v; changed(); }, 'number', { min: 1, max: C.hit_die }));
      card.append(head);
      const feats = [...C.features.filter(([lv]) => lv === n).map(([, x]) => x), ...(n >= 3 ? C.subclass.features.filter(([lv]) => lv === n).map(([, x]) => x) : [])];
      if (feats.length) card.append(el('p', 'Gains: ' + feats.map(x => x === e.class + ' Subclass' ? `${C.subclass.name} (subclass)` : x).join(', '), 'char-note'));
      const body = el('div', undefined, 'char-fields'); card.append(body);
      if (n === 1 && i === 0) card.append(picks(`${e.class} skills`, C.skills, e.skills ?? [], C.skill_count, v => { e.skills = v; changed(); }));
      if (n === 1 && i > 0) {
        card.append(el('p', `Multiclass: ${e.class} gives ${[C.multiclass.armor.length ? C.multiclass.armor.join(', ') + ' armor training' : '', C.multiclass.weapons.length ? 'martial weapons' : '', C.multiclass.skills ? 'one skill' : '', C.multiclass.tools].filter(Boolean).join(', ') || 'no proficiencies'}.`, 'char-note'));
        if (C.multiclass.skills) card.append(picks(`${e.class} skill`, C.skills, e.skills ?? [], C.multiclass.skills, v => { e.skills = v; changed(); }));
      }
      if (e.class === 'Bard' && n === 3) card.append(picks('Bonus Proficiencies: skills', Object.keys(r.skills), e.skills ?? [], 3, v => { e.skills = v; changed(); }));
      if (n === 1 && e.class === 'Cleric') body.append(select('Divine Order', e.order, [['', 'Choose…'], ['Protector', 'Protector (martial weapons, heavy armor)'], ['Thaumaturge', 'Thaumaturge (one more cantrip)']], v => { e.order = v; changed(); }));
      if (n === 1 && e.class === 'Druid') body.append(select('Primal Order', e.order, [['', 'Choose…'], ['Magician', 'Magician (one more cantrip)'], ['Warden', 'Warden (martial weapons, medium armor)']], v => { e.order = v; changed(); }));
      if (e.class === 'Druid' && n === 3) body.append(select('Circle of the Land: land', e.land, [['', 'Choose…'], 'arid', 'polar', 'temperate', 'tropical'], v => { e.land = v; changed(); }));
      if (e.class === 'Sorcerer' && n === 6) body.append(select('Elemental Affinity: damage type', e.affinity, [['', 'Choose…'], 'acid', 'cold', 'fire', 'lightning', 'poison'], v => { e.affinity = v; changed(); }));
      if ((STYLE_AT[e.class] ?? []).includes(n)) {
        const opt = STYLE_OPTION[e.class];
        body.append(select(n === 7 ? 'Additional Fighting Style' : 'Fighting Style', e.fighting_style, [['', 'Choose…'], ...STYLES, ...(opt ? [[opt[0], `${opt[0]} (two ${opt[1]} cantrips)`]] : [])], v => { e.fighting_style = v; changed(); }));
        if (opt && e.fighting_style === opt[0]) card.append(picks(`${opt[0]}: ${opt[1]} cantrips`, spellsOf(opt[1], 0).map(s => s.name), e.style_cantrips ?? [], 2, v => { e.style_cantrips = v; changed(); }));
      }
      const ex = EXPERTISE[e.class]?.[n];
      if (ex) card.append(picks('Expertise', (result?.sheet?.proficiencies ?? []).filter(p => !p.endsWith('(expertise)') && r.skills[p] && (e.class !== 'Wizard' || SCHOLAR.includes(p))).concat(e.expertise ?? []).filter((v, k, a) => a.indexOf(v) === k), e.expertise ?? [], ex, v => { e.expertise = v; changed(); }));
      if (e.class === 'Warlock') {
        const t = C.resources.invocations, gain = t[n - 1] - (n > 1 ? t[n - 2] : 0);
        if (gain) {
          const opts = result?.options?.invocations ?? {};
          card.append(picks(`Eldritch Invocations (Warlock ${n})`, Object.entries(opts).filter(([, o]) => o.level <= n).map(([k, o]) => [k, k + (o.needs ? ` (needs ${o.needs})` : '')]), e.invocations ?? [], gain, v => { e.invocations = v; changed(); }));
        }
      }
      if (e.class === 'Sorcerer' && METAMAGIC_AT[n]) card.append(picks('Metamagic', ['Careful Spell', 'Distant Spell', 'Empowered Spell', 'Extended Spell', 'Heightened Spell', 'Quickened Spell', 'Seeking Spell', 'Subtle Spell', 'Transmuted Spell', 'Twinned Spell'], e.metamagic ?? [], 2, v => { e.metamagic = v; changed(); }));
      if (C.asi.includes(n) || n === 19) drawAsi(card, e, n, i + 1);
      if (i === c.levels.length - 1 && i > 0) card.append(button('Remove this level', () => { c.levels.pop(); changed(); }));
      f.append(card);
    });
    if (c.levels.length < 20) {
      const add = el('div', undefined, 'char-actions level-up');
      const opts = result?.options?.classes ?? Object.keys(r.classes).map(k => [k, true, '']);
      const last = c.levels.at(-1)?.class ?? 'Fighter';
      let pick = last;
      add.append(select(`Level ${c.levels.length + 1}: class`, pick, opts.map(([k, ok, why]) => [k, k + (k === last ? ' (same class)' : ok ? '' : ` (${why})`), !ok]), v => { pick = v; }));
      add.append(button('Level up →', () => { c.levels.push({ class: pick }); changed(); status?.(`Level ${c.levels.length}: the new choices are in its card.`); }, ''));
      let to = Math.min(20, c.levels.length + 1);
      add.append(input('Or straight to level', to, v => { to = Math.max(1, Math.min(20, Number(v) || 1)); }, 'number', { min: 1, max: 20, style: 'width:5em' }),
        button('Go (Auto-fill)', () => { while (c.levels.length < to) c.levels.push({ class: last }); while (c.levels.length > to) c.levels.pop(); autofill(); changed(); status?.(`Now level ${to}. Auto-fill picked the open choices; change any of them.`); }));
      f.append(add);
    }
  }
  function canTake(cls, i) {
    const r = R(), scores = result?.sheet?.abilities ?? {}, C = r.classes[cls];
    const ok = k => { const K = r.classes[k]; return K.primary_any ? K.primary.some(a => scores[a] >= 13) : K.primary.every(a => scores[a] >= 13); };
    const before = new Set(choices.levels.slice(0, i).map(e => e.class));
    return before.has(cls) || (ok(cls) && [...before].every(ok)) || !C;
  }

  function drawAsi(card, e, n, lv) {
    const r = R(), a = e.asi ??= {};
    const box = el('div', undefined, 'char-fields');
    const feats = Object.entries(r.feats).filter(([k, f]) => (n === 19 ? true : f.category !== 'epic boon') && (f.level ?? 0) <= lv).map(([k, f]) => [k, `${k}${f.category === 'epic boon' ? ' (Epic Boon)' : f.category === 'origin' ? ' (Origin)' : f.category === 'fighting style' ? ' (Fighting Style)' : ''}`]);
    box.append(select(n === 19 ? 'Epic Boon (or another feat)' : 'Ability Score Improvement or a feat', a.feat, [['', 'Choose…'], ...feats.flatMap(([k, t]) => k === 'Magic Initiate' ? ['Cleric', 'Druid', 'Wizard'].map(l => [`Magic Initiate (${l})`, `Magic Initiate (${l}) (Origin)`]) : [[k, t]])], v => { e.asi = { feat: v, abilities: {} }; changed(); }));
    card.append(box);
    const f = a.feat;
    if (f === 'Ability Score Improvement') {
      const row = el('div', undefined, 'char-fields six');
      for (const ab of AB) row.append(select(ab.toUpperCase(), a.abilities?.[ab] ?? 0, [[0, '+0'], [1, '+1'], [2, '+2']], v => { a.abilities = { ...a.abilities, [ab]: Number(v) }; if (!a.abilities[ab]) delete a.abilities[ab]; changed(); }));
      card.append(row, el('p', '+2 to one score, or +1 to two (20 at most).', 'char-note'));
    } else if (f === 'Grappler' || f?.startsWith('Boon of')) {
      const allowed = f === 'Grappler' || f === 'Boon of Irresistible Offense' ? ['str', 'dex'] : f === 'Boon of Spell Recall' ? ['int', 'wis', 'cha'] : AB;
      const cur = Object.keys(a.abilities ?? {})[0] ?? '';
      card.append(select('+1 to', cur, [['', 'Choose…'], ...allowed.map(x => [x, x.toUpperCase()])], v => { a.abilities = v ? { [v]: 1 } : {}; changed(); }));
    }
    if (f?.startsWith('Magic Initiate') || f === 'Skilled') card.append(el('p', `${f}: its choices are in step 1 under the background feat when it is the same feat; for this level, note them in Notes (the GM rules them).`, 'char-note'));
  }

  function drawSpells(form) {
    const r = R(), c = choices, n = counts();
    const casters = Object.entries(n).filter(([cls]) => r.classes[cls].caster !== 'none');
    const f = sect(form, '4. Spells', 'step-spells');
    if (!casters.length) { f.append(el('p', 'No spellcasting class yet (species and feat spells are listed on the sheet).', 'char-note')); return; }
    c.spells ??= {};
    const info = Object.fromEntries((result?.sheet?.derived?.casting ?? []).map(k => [k.class, k]));
    for (const [cls, lv] of casters) {
      const mine = c.spells[cls] ??= {}, k = info[cls] ?? { cantrips: r.classes[cls].cantrips?.[lv - 1] ?? 0, prepared: r.classes[cls].prepared?.[lv - 1] ?? 0, max_level: maxSpell(cls, lv) };
      f.append(el('h3', `${cls} ${lv}: up to level ${k.max_level} spells${k.dc ? ` · save DC ${k.dc}, spell attack +${k.attack}` : ''}`));
      const grp = s => s.level === 0 ? 'Cantrips' : `Level ${s.level}`;
      if (k.cantrips) f.append(picks(`${cls} cantrips`, spellsOf(cls, 0).map(s => s.name), mine.cantrips ?? [], k.cantrips, v => { mine.cantrips = v; changed(); }));
      if (cls === 'Wizard') {
        const bookN = 6 + 2 * (lv - 1);
        f.append(picks('Spellbook', spellsOf(cls, k.max_level).map(s => [s.name, s.name]), mine.book ?? [], bookN, v => { mine.book = v; mine.prepared = (mine.prepared ?? []).filter(x => v.includes(x)); changed(); }, { group: o => grp(r.spells.find(s => s.name === o[0])) }));
        f.append(picks('Prepared (from the spellbook)', (mine.book ?? []).map(x => [x, x]), mine.prepared ?? [], k.prepared, v => { mine.prepared = v; changed(); }));
      } else f.append(picks(`${cls} prepared spells`, spellsOf(cls, k.max_level).map(s => [s.name, s.name]), mine.prepared ?? [], k.prepared, v => { mine.prepared = v; changed(); }, { group: o => grp(r.spells.find(s => s.name === o[0])) }));
      if (cls === 'Warlock' && lv >= 11) {                      // SPELLS-4-9: Mystic Arcanum, one Warlock spell of each level
        const want = arcanumLevels(lv);
        f.append(picks(`Mystic Arcanum (one Warlock spell of level ${want.join(', ')}; each cast once per Long Rest without a slot)`,
          spellsOf(cls, 9).filter(s => want.includes(s.level)).map(s => [s.name, s.name]), mine.arcanum ?? [], want.length,
          v => { mine.arcanum = v; changed(); }, { group: o => grp(r.spells.find(s => s.name === o[0])) }));
      }
      if (cls === 'Bard' && lv >= 6) f.append(picks('Magical Discoveries (Cleric, Druid or Wizard spells)', r.spells.filter(s => s.level <= k.max_level && s.classes.some(x => ['Cleric', 'Druid', 'Wizard'].includes(x))).map(s => [s.name, s.name]), mine.discoveries ?? [], 2, v => { mine.discoveries = v; changed(); }, { group: o => grp(r.spells.find(s => s.name === o[0])) }));
    }
    f.append(el('p', 'Spells the simulator plays in a fight are marked on the sheet; the rest the GM rules.', 'char-note'));
  }

  function drawEquipment(form) {
    const r = R(), c = choices, eq = c.equipment ??= {}, f = sect(form, '5. Equipment', 'step-equipment');
    // KITS-01: a level 1 character takes the class's and the background's SRD kit, or their gold, and buys the rest
    const first = c.levels?.[0]?.class, K = r.kits;
    if (K && first && (c.levels?.length ?? 0) === 1) {
      const gear = k => [k.armor, k.shield && 'Shield', ...k.weapons.filter(([n]) => !k.items.some(x => x.includes(`(${n})`))).map(([n, q]) => q > 1 ? `${q} ${n}s` : n), ...k.items].filter(Boolean).join(', ');
      const ck = K.classes[first] ?? {}, bk = K.backgrounds[c.background];
      const fill = () => {                                       // a kit puts its armour, weapons and focus on the sheet
        const a = ck[eq.class_kit], b = eq.background_kit === 'kit' ? bk : null;
        if (a) Object.assign(eq, { armor: a.armor ?? 'None', shield: a.shield, focus: a.focus, spellbook: a.spellbook });
        if (a || b) eq.weapons = [...new Set([...(a ? [] : eq.weapons ?? []), ...(a?.weapons ?? []).map(w => w[0]), ...(b?.weapons ?? []).map(w => w[0])])];
      };
      const kr = el('div', undefined, 'char-fields');
      kr.append(select(`${first} equipment`, eq.class_kit ?? 'gold', [...Object.entries(ck).map(([id, k]) => [id, `${id}: ${gear(k)}, ${k.gp} GP`]), ['gold', `Gold: ${K.class_gold[first]} GP, buy your own`]], v => { eq.class_kit = v; fill(); changed(); }));
      if (bk) kr.append(select(`${c.background} equipment`, eq.background_kit ?? 'gold', [['kit', `Kit: ${gear(bk)}, ${bk.gp} GP`], ['gold', `Gold: ${K.background_gold} GP`]], v => { eq.background_kit = v; fill(); changed(); }));
      f.append(kr);
    }
    const row = el('div', undefined, 'char-fields');
    row.append(select('Armor', eq.armor ?? 'None', [['None', 'None'], ...r.armor.map(a => [a.name, `${a.name} (${a.category}, AC ${a.ac}${a.strength ? ', STR ' + a.strength : ''})`])], v => { eq.armor = v; changed(); }));
    row.append(select('Shield', String(Boolean(eq.shield)), [['false', 'No'], ['true', 'Yes (+2 AC)']], v => { eq.shield = v === 'true'; changed(); }));
    row.append(select('Component pouch or focus', String(Boolean(eq.focus)), [['false', 'No'], ['true', 'Yes']], v => { eq.focus = v === 'true'; changed(); }));
    row.append(select('Spellbook', String(Boolean(eq.spellbook)), [['false', 'No'], ['true', 'Yes']], v => { eq.spellbook = v === 'true'; changed(); }));
    f.append(row);
    const label = w => `${w.name} (${w.dice} ${w.type}${w.finesse ? ', finesse' : ''}${w.two_handed ? ', two-handed' : ''}${w.reach ? ', reach' : ''}${w.ammunition ? ', range ' + w.ammunition.join('/') : ''}; ${w.mastery})`;
    f.append(picks('Weapons', r.weapons.map(w => [w.name, label(w)]), eq.weapons ?? [], null, v => { eq.weapons = v; changed(); }, { group: o => { const w = r.weapons.find(x => x.name === o[0]); return `${w.category === 'simple' ? 'Simple' : 'Martial'} ${w.kind}`; } }));
    const mastN = result?.todo?.find(t => t.where === 'Weapon Mastery')?.text.match(/Choose (\d+)/)?.[1] ?? c.masteries?.length ?? 0;
    if (Number(mastN)) f.append(picks('Weapon Mastery: kinds of weapons', r.weapons.map(w => [w.name, `${w.name} (${w.mastery})`]), c.masteries ?? [], Number(mastN), v => { c.masteries = v; changed(); }, { group: o => { const w = r.weapons.find(x => x.name === o[0]); return w.category === 'simple' ? 'Simple' : 'Martial'; } }));
    const g = result?.sheet?.derived?.gold_remaining;
    if (g != null) f.append(el('p', `Starting gold left: ${g} GP (${result.sheet.derived.gold_how || "the class's gold + the background's 50 GP"}). Kit gear is free; anything else is bought.`, 'char-note'));
    const notes = el('div', undefined, 'char-fields');
    const ta = el('label', 'Other gear, one per line'), t = el('textarea'); t.rows = 3; t.value = eq.other ?? ''; t.onchange = () => { eq.other = t.value; changed(false); }; ta.append(t);
    const nb = el('label', 'Notes (appearance, story, choices the GM rules)'), n2 = el('textarea'); n2.rows = 3; n2.value = c.notes ?? ''; n2.onchange = () => { c.notes = n2.value; changed(false); }; nb.append(n2);
    notes.append(ta, nb); f.append(notes);
  }

  return {
    draw,
    get choices() { return choices; },
    get result() { return result; },
    // a saved built sheet opened again in the builder (its choices travel with it)
    edit(build) { if (build?.format === BUILD_FORMAT) { choices = structuredClone(build); result = null; save(); } },
    fresh() { choices = starterBuild(); result = null; save(); },
  };
}
