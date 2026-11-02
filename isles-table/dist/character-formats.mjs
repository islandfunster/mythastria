// CHARACTERS-01 phase 2 (GM 2026-10-21: "I would like it able to import formats like forge, dnd beyond, fantasy grounds,
// etc."): character files from other programs, read in the browser into isles-character/1 sheets.
//
//   Foundry VTT / The Forge  an actor exported as JSON (dnd5e system, `system` or the older `data`)
//   D&D Beyond               the character JSON (as saved from its character service; `{data: {...}}` or the bare object)
//   Roll20                   a character exported as JSON by a journal exporter (VTTES: `attribs` [{name, current, max}])
//   anything else            generic JSON: matched by field names only, and said so
// (Fantasy Grounds XML and PDFs, D&D Beyond's PDF too, are read in character-import.mjs.)
//
// Every importer fills `c.import`: what it read, what it worked out (and how), what is missing, what it did not use, and
// the pictures it found. It never guesses silently: a number it could not read stays empty and is listed as missing; a
// number it worked out from other values says so. Pictures: one carried in the file as data is offered at once; a web
// address is only fetched when the GM presses the button (third-party sites are never contacted on their own).
// Content policy: third-party and 2014-rules content on an imported sheet is the user's own homebrew. It stays on their
// sheet in this browser; the service flags it "homebrew, GM rules it" (sim/character_rules.py) and it never ships.
import { blankCharacter, fromFields, ABILITIES } from './character-import.mjs';
import { readSheet, SKILLS, skillField } from './character-sheet-pdf.mjs';

const FULL = { str: 'strength', dex: 'dexterity', con: 'constitution', int: 'intelligence', wis: 'wisdom', cha: 'charisma' };
const mod = n => Math.floor((Number(n) - 10) / 2);
const profFor = level => 2 + Math.floor((Math.max(1, level) - 1) / 4);
const num = v => { const n = typeof v === 'number' ? v : Number.parseFloat(String(v ?? '').replace(/[^0-9.+-]/g, '')); return Number.isFinite(n) ? n : null; };
const title = s => String(s).replace(/(^|[\s-])\w/g, m => m.toUpperCase());
const RAW_MAX = 80000;

export function startReport(c, source) {
  c.import = { source, read: [], worked: [], missing: [], unmapped: [], portraits: [] };
  c.provenance = { kind: source, fields: {} };
  return c.import;
}
const read = (c, label, value, from) => { if (value !== null && value !== undefined && value !== '') c.import.read.push([label, String(value), from]); };
const worked = (c, label, value, how) => c.import.worked.push([label, String(value), how]);

// What a sheet still lacks for a fight: listed, never filled in by guessing.
export function finishReport(c, raw) {
  const r = c.import;
  for (const a of ABILITIES) if (c.abilities[a] === null || c.abilities[a] === undefined) r.missing.push(a.toUpperCase());
  const k = c.combat;
  for (const [f, label] of [['hp_max', 'Hit points'], ['ac', 'Armor Class'], ['speed', 'Speed'], ['attack_bonus', 'Attack bonus'], ['damage_die', 'Damage dice'], ['damage_bonus', 'Damage bonus']])
    if (k[f] === null || k[f] === undefined) r.missing.push(label);
  if (!c.name) r.missing.push('Name');
  if (!c.classes?.length) r.missing.push('Class and level');
  r.unmapped = r.unmapped.slice(0, 80);
  const text = typeof raw === 'string' ? raw : JSON.stringify(raw, null, 1);
  c.provenance.raw = text.slice(0, RAW_MAX);
  c.provenance.truncated = text.length > RAW_MAX;
  c.warnings = [`Imported from ${r.source}. Check the sheet against the original before using it in a fight.`];
  if (r.missing.length) c.warnings.push('Missing (fill these in on the sheet): ' + r.missing.join(', ') + '.');
  if (r.worked.length) c.warnings.push('Worked out from the file (check them): ' + r.worked.map(w => w[0]).join(', ') + '.');
  return c;
}

// A picture the file names. `data:` images are kept as they are; anything else is an address, fetched only on a click.
function portrait(c, src, label) {
  if (typeof src !== 'string' || !src.trim()) return;
  const v = src.trim();
  if (/^data:image\/(png|jpe?g|webp|gif);base64,/i.test(v)) c.import.portraits.push({ kind: 'data', value: v, label });
  else if (/^https?:\/\//i.test(v)) c.import.portraits.push({ kind: 'url', value: v, label });
  else c.import.portraits.push({ kind: 'path', value: v, label });
}

// The attack a sheet shows in a fight: the weapon's numbers, with how they were reached.
function setAttack(c, w, how) {
  c.combat.attack_bonus = w.atk;
  c.combat.damage_count = w.count;
  c.combat.damage_die = w.die;
  c.combat.damage_bonus = w.bonus;
  c.combat.reach = w.reach ?? 5;
  worked(c, 'Attack', `${w.name}: ${w.atk >= 0 ? '+' : ''}${w.atk} to hit, ${w.count}d${w.die}${w.bonus ? (w.bonus > 0 ? '+' : '') + w.bonus : ''}`, how);
}
const diceOf = s => { const m = String(s ?? '').match(/(\d+)\s*d\s*(\d+)/i); return m ? { count: +m[1], die: +m[2] } : null; };

// ------------------------------------------------------------------ which program made this JSON
export function detectJSON(v) {
  if (!v || typeof v !== 'object') return 'unknown';
  if (v.format === 'isles-character/1' || v.format === 'isles-character-collection/1' || v.character?.format === 'isles-character/1') return 'isles';
  const ddb = v.data && typeof v.data === 'object' && !Array.isArray(v.data) ? v.data : v;
  if (Array.isArray(ddb.stats) && Array.isArray(ddb.classes) && ('baseHitPoints' in ddb || 'race' in ddb)) return 'ddb';
  const sys = v.system ?? v.data;
  if (sys && typeof sys === 'object' && sys.abilities && Array.isArray(v.items) && typeof v.name === 'string') return 'foundry';
  if (Array.isArray(v.attribs) || Array.isArray(v.character?.attribs)) return 'roll20';
  return 'unknown';
}

export function parseOtherJSON(text) {
  if (text.length > 2_000_000) throw Error('That JSON file is over 2 MB. Export a single character.');
  let v;
  try { v = JSON.parse(text); } catch { throw Error('That file is not readable JSON. Export the character again.'); }
  const kind = detectJSON(v);
  if (kind === 'foundry') return [fromFoundry(v)];
  if (kind === 'ddb') return [fromDDB(v)];
  if (kind === 'roll20') return [fromRoll20(v.character?.attribs ? v.character : v)];
  if (kind === 'isles') return null;                                         // the caller reads Mythastria's own format
  return [fromGenericJSON(v)];
}

// ------------------------------------------------------------------ Foundry VTT / The Forge (dnd5e actor)
const FOUNDRY_SKILLS = { acr: 'Acrobatics', ani: 'Animal Handling', arc: 'Arcana', ath: 'Athletics', dec: 'Deception', his: 'History', ins: 'Insight', itm: 'Intimidation', inv: 'Investigation', med: 'Medicine', nat: 'Nature', prc: 'Perception', prf: 'Performance', per: 'Persuasion', rel: 'Religion', slt: 'Sleight of Hand', ste: 'Stealth', sur: 'Survival' };
const fProps = s => { const p = s?.properties; return Array.isArray(p) ? new Set(p) : new Set(Object.entries(p ?? {}).filter(([, v]) => v).map(([k]) => k)); };

export function fromFoundry(a) {
  const c = blankCharacter(), sys = a.system ?? a.data ?? {}, items = Array.isArray(a.items) ? a.items : [];
  startReport(c, a._stats?.systemId === 'dnd5e' || sys.abilities ? 'Foundry VTT / The Forge (dnd5e)' : 'Foundry VTT / The Forge');
  const is = (it, type) => it?.type === type;
  const S = it => it.system ?? it.data ?? {};
  c.name = String(a.name ?? '').trim(); read(c, 'Name', c.name, 'name');
  c.kind = a.type === 'npc' ? 'npc' : 'pc';
  for (const k of ABILITIES) { const v = num(sys.abilities?.[k]?.value); c.abilities[k] = v; read(c, k.toUpperCase(), v, `system.abilities.${k}.value`); }

  // classes with their subclasses (matched by the class identifier, as Foundry links them)
  const subs = items.filter(it => is(it, 'subclass'));
  c.classes = items.filter(it => is(it, 'class')).map(it => {
    const s = S(it), ident = s.identifier ?? it.name.toLowerCase();
    const sub = subs.find(x => (S(x).classIdentifier ?? '') === ident);
    const hd = num(String(s.hitDice ?? s.hd?.denomination ?? '').replace(/^d/, ''));
    return { name: it.name, level: num(s.levels) ?? 1, ...(sub ? { subclass: sub.name } : {}), ...(hd ? { hit_die: hd } : {}) };
  });
  for (const k of c.classes) read(c, 'Class', `${k.name} ${k.level}${k.subclass ? ' (' + k.subclass + ')' : ''}`, 'items (class)');
  const level = c.classes.reduce((n, k) => n + (k.level || 0), 0) || num(sys.details?.level) || 1;
  const race = items.find(it => is(it, 'race'));
  c.species = race?.name ?? (typeof sys.details?.race === 'string' ? sys.details.race : '');
  read(c, 'Species', c.species, race ? 'items (race)' : 'system.details.race');
  const bg = items.find(it => is(it, 'background'));
  c.background = bg?.name ?? (typeof sys.details?.background === 'string' ? sys.details.background : '');
  read(c, 'Background', c.background, bg ? 'items (background)' : 'system.details.background');
  const rules = items.map(it => S(it).source?.rules).find(Boolean);
  c.ruleset = rules === '2014' ? 'D&D 5e (2014)' : rules === '2024' ? 'D&D 2024' : 'Unconfirmed';
  if (rules) read(c, 'Rules', c.ruleset, 'items: system.source.rules');

  // hit points: the file's maximum, else worked out from the classes' hit dice (Foundry leaves it blank when it computes it)
  const hpMax = num(sys.attributes?.hp?.max);
  if (hpMax) { c.combat.hp_max = hpMax; read(c, 'Hit points', hpMax, 'system.attributes.hp.max'); }
  else if (c.classes.every(k => k.hit_die) && c.classes.length && c.abilities.con !== null) {
    let hp = 0, first = true;
    for (const k of c.classes) for (let i = 0; i < k.level; i++) { hp += first ? k.hit_die : k.hit_die / 2 + 1; first = false; }
    hp += mod(c.abilities.con) * level + (num(sys.attributes?.hp?.bonuses?.level) ?? 0) * level + (num(sys.attributes?.hp?.bonuses?.overall) ?? 0);
    c.combat.hp_max = Math.max(1, Math.round(hp));
    worked(c, 'Hit points', c.combat.hp_max, 'hit dice: the first level in full, then the average per level, plus Constitution');
  }

  // Armor Class: Foundry stores how to calculate it, not the number
  const ac = sys.attributes?.ac ?? {}, dex = mod(c.abilities.dex ?? 10), calc = ac.calc ?? 'default';
  const equipped = items.filter(it => S(it).equipped);
  const armorType = it => S(it).type?.value ?? S(it).armor?.type;
  const armor = equipped.find(it => is(it, 'equipment') && ['light', 'medium', 'heavy'].includes(armorType(it)));
  const shield = equipped.find(it => is(it, 'equipment') && armorType(it) === 'shield');
  const acBonus = num(ac.bonus) ?? 0;
  let acValue = null, acHow = '';
  if (['flat', 'natural'].includes(calc) && num(ac.flat) !== null) { acValue = num(ac.flat); acHow = 'system.attributes.ac.flat'; }
  else if (calc === 'mage') { acValue = 13 + dex; acHow = 'Mage Armor: 13 + Dexterity'; }
  else if (calc === 'draconic') { acValue = 13 + dex; acHow = 'Draconic Resilience: 13 + Dexterity'; }
  else if (calc === 'unarmoredBarb') { acValue = 10 + dex + mod(c.abilities.con ?? 10); acHow = 'Unarmored Defense: 10 + Dexterity + Constitution'; }
  else if (calc === 'unarmoredMonk') { acValue = 10 + dex + mod(c.abilities.wis ?? 10); acHow = 'Unarmored Defense: 10 + Dexterity + Wisdom'; }
  else if (['default', 'equipment'].includes(calc)) {
    if (armor) {
      const s = S(armor), base = num(s.armor?.value) ?? 10, cap = s.armor?.dex ?? (armorType(armor) === 'heavy' ? 0 : armorType(armor) === 'medium' ? 2 : null);
      acValue = base + (num(s.armor?.magicalBonus ?? s.magicalBonus) ?? 0) + (cap === null || cap === undefined ? dex : Math.min(dex, Number(cap)));
      acHow = `worn armor (${armor.name}) + Dexterity${cap !== null && cap !== undefined ? ' (at most ' + cap + ')' : ''}`;
    } else { acValue = 10 + dex; acHow = 'no armor worn: 10 + Dexterity'; }
  } else c.import.unmapped.push(`Armor Class is calculated by "${calc}" in Foundry; enter it by hand.`);
  if (acValue !== null) {
    if (shield && calc !== 'flat') { acValue += (num(S(shield).armor?.value) ?? 2) + (num(S(shield).armor?.magicalBonus ?? S(shield).magicalBonus) ?? 0); acHow += ' + Shield'; }
    if (acBonus) { acValue += acBonus; acHow += ` + ${acBonus} bonus`; }
    c.combat.ac = acValue; worked(c, 'Armor Class', acValue, acHow);
  }

  const walk = num(sys.attributes?.movement?.walk);
  if (walk) { c.combat.speed = walk; read(c, 'Speed', walk, 'system.attributes.movement.walk'); }
  const prof = num(sys.attributes?.prof) ?? profFor(level);

  // the attack: the first equipped weapon (else the first weapon)
  const weapons = items.filter(it => is(it, 'weapon'));
  const w = weapons.find(it => S(it).equipped) ?? weapons[0];
  if (w) {
    const s = S(w), props = fProps(s), ranged = /R$/.test(s.type?.value ?? s.weaponType ?? '') || props.has('amm');
    const base = s.damage?.base ?? null, parts = s.damage?.parts?.[0];
    const dice = base?.number && base?.denomination ? { count: +base.number, die: +base.denomination } : diceOf(parts?.[0]);
    const abil = s.ability || (props.has('fin') ? (mod(c.abilities.dex ?? 10) >= mod(c.abilities.str ?? 10) ? 'dex' : 'str') : ranged ? 'dex' : 'str');
    const m = mod(c.abilities[abil] ?? 10), magic = num(s.magicalBonus ?? s.attackBonus) ?? 0;
    const proficient = s.proficient === undefined || s.proficient === null ? true : Boolean(s.proficient);
    if (dice) setAttack(c, { name: w.name, atk: (proficient ? prof : 0) + m + magic, count: dice.count, die: dice.die, bonus: m + magic, reach: props.has('rch') ? 10 : 5 },
      `${abil.toUpperCase()} ${m >= 0 ? '+' : ''}${m}${proficient ? ', proficiency +' + prof : ', not proficient'}${magic ? ', magic +' + magic : ''}`);
    else c.import.unmapped.push(`${w.name}: its damage could not be read.`);
  }

  // lists
  const spells = items.filter(it => is(it, 'spell'));
  c.spells = spells.map(it => ({ name: it.name, level: num(S(it).level) ?? 0 }));
  c.feats = items.filter(it => is(it, 'feat') && (S(it).type?.value === 'feat')).map(it => it.name);
  c.features = items.filter(it => is(it, 'feat') && S(it).type?.value !== 'feat').map(it => it.name);
  c.equipment = items.filter(it => ['weapon', 'equipment', 'consumable', 'tool', 'loot', 'container', 'backpack'].includes(it.type))
    .map(it => (num(S(it).quantity) > 1 ? `${it.name} ×${num(S(it).quantity)}` : it.name));
  c.proficiencies = Object.entries(sys.skills ?? {}).filter(([, v]) => num(v?.value) >= 1).map(([k, v]) => FOUNDRY_SKILLS[k] + (num(v.value) >= 2 ? ' (expertise)' : '')).filter(s => !s.startsWith('undefined'));
  c.saves = ABILITIES.filter(k => num(sys.abilities?.[k]?.proficient) >= 1);
  const langs = sys.traits?.languages;
  c.languages = [...(Array.isArray(langs?.value) ? langs.value.map(title) : []), ...String(langs?.custom ?? '').split(/[;,]/).map(s => s.trim()).filter(Boolean)];
  const dv = num(sys.attributes?.senses?.darkvision ?? sys.attributes?.senses?.ranges?.darkvision);
  if (dv) c.senses = `Darkvision ${dv} ft.`;
  c.notes = String(sys.details?.biography?.value ?? '').replace(/<[^>]+>/g, ' ').replace(/\s+/g, ' ').trim().slice(0, 4000);
  for (const [label, n] of [['spells', c.spells.length], ['features', c.features.length], ['feats', c.feats.length], ['items', c.equipment.length]]) if (n) read(c, title(label), n + ' listed', 'items');
  const used = new Set(['class', 'subclass', 'race', 'background', 'spell', 'feat', 'weapon', 'equipment', 'consumable', 'tool', 'loot', 'container', 'backpack']);
  for (const it of items.filter(it => !used.has(it.type))) c.import.unmapped.push(`${it.name} (${it.type})`);
  if (Array.isArray(a.effects) && a.effects.length) c.import.unmapped.push(`${a.effects.length} active effect(s): their changes are not applied here.`);
  portrait(c, a.img, 'The actor picture');
  portrait(c, a.prototypeToken?.texture?.src ?? a.token?.img, 'The token picture');
  return finishReport(c, a);
}

// ------------------------------------------------------------------ D&D Beyond (character service JSON)
const DDB_ABILITY = { 1: 'str', 2: 'dex', 3: 'con', 4: 'int', 5: 'wis', 6: 'cha' };
const DDB_ARMOR = { 1: 'light', 2: 'medium', 3: 'heavy', 4: 'shield' };

export function fromDDB(v) {
  const d = v.data && typeof v.data === 'object' && !Array.isArray(v.data) ? v.data : v;
  const c = blankCharacter();
  startReport(c, 'D&D Beyond');
  c.name = String(d.name ?? '').trim(); read(c, 'Name', c.name, 'name');
  const inv = Array.isArray(d.inventory) ? d.inventory : [];
  const live = new Set(inv.filter(it => it.equipped && (!it.definition?.canAttune || it.isAttuned)).map(it => it.definition?.id));
  const mods = [];
  for (const [src, list] of Object.entries(d.modifiers ?? {})) for (const m of list ?? []) if (src !== 'item' || live.has(m.componentId)) mods.push({ ...m, src });
  const sum = sub => mods.filter(m => m.type === 'bonus' && m.subType === sub).reduce((n, m) => n + (num(m.value ?? m.fixedValue) ?? 0), 0);

  // ability scores: base + chosen bonus + species/background/feat bonuses; "set" items (as Gauntlets) raise to their value
  for (const [id, k] of Object.entries(DDB_ABILITY)) {
    const over = num(d.overrideStats?.find(s => s.id === +id)?.value);
    if (over) { c.abilities[k] = over; read(c, k.toUpperCase(), over, 'overrideStats'); continue; }
    const base = num(d.stats?.find(s => s.id === +id)?.value);
    if (base === null) continue;
    const bonus = num(d.bonusStats?.find(s => s.id === +id)?.value) ?? 0, extra = sum(FULL[k] + '-score');
    let score = base + bonus + extra;
    for (const m of mods) if (m.type === 'set' && m.subType === FULL[k] + '-score') score = Math.max(score, num(m.value) ?? 0);
    c.abilities[k] = score;
    if (bonus || extra) worked(c, k.toUpperCase(), score, `base ${base}${bonus ? ' + ' + bonus : ''}${extra ? ' + ' + extra + ' from species, background or feats' : ''}`);
    else read(c, k.toUpperCase(), score, 'stats');
  }

  c.classes = (d.classes ?? []).map(k => ({ name: k.definition?.name ?? '?', level: num(k.level) ?? 1, ...(k.subclassDefinition?.name ? { subclass: k.subclassDefinition.name } : {}), hit_die: num(k.definition?.hitDice) ?? undefined }));
  for (const k of c.classes) read(c, 'Class', `${k.name} ${k.level}${k.subclass ? ' (' + k.subclass + ')' : ''}`, 'classes');
  const level = c.classes.reduce((n, k) => n + k.level, 0) || 1;
  c.species = d.race?.fullName ?? d.race?.baseName ?? ''; read(c, 'Species', c.species, 'race');
  c.background = d.background?.definition?.name ?? d.background?.customBackground?.name ?? ''; read(c, 'Background', c.background, 'background');
  const legacy = [d.race, ...(d.classes ?? []).map(k => k.definition), d.background?.definition].some(x => x?.isLegacy === true);
  c.ruleset = legacy ? 'D&D 5e (2014)' : 'Unconfirmed';
  if (legacy) read(c, 'Rules', c.ruleset, 'isLegacy on the species, class or background');

  const con = mod(c.abilities.con ?? 10);
  if (num(d.overrideHitPoints)) { c.combat.hp_max = num(d.overrideHitPoints); read(c, 'Hit points', c.combat.hp_max, 'overrideHitPoints'); }
  else if (num(d.baseHitPoints) !== null && c.abilities.con !== null) {
    c.combat.hp_max = num(d.baseHitPoints) + (num(d.bonusHitPoints) ?? 0) + (con + sum('hit-points-per-level')) * level;
    worked(c, 'Hit points', c.combat.hp_max, `rolled/fixed ${d.baseHitPoints}${d.bonusHitPoints ? ' + bonus ' + d.bonusHitPoints : ''} + (Constitution${sum('hit-points-per-level') ? ' and per-level bonuses' : ''}) × level ${level}`);
  }

  // Armor Class from what is worn (D&D Beyond computes it on its site; the file holds the parts)
  const dex = mod(c.abilities.dex ?? 10), worn = inv.filter(it => it.equipped && it.definition?.filterType === 'Armor');
  const armor = worn.find(it => [1, 2, 3].includes(it.definition.armorTypeId)), shield = worn.find(it => it.definition.armorTypeId === 4);
  const features = (d.classes ?? []).flatMap(k => (k.classFeatures ?? []).filter(f => (f.definition?.requiredLevel ?? 1) <= k.level).map(f => f.definition?.name)).filter(Boolean);
  let ac, how;
  if (armor) {
    const t = DDB_ARMOR[armor.definition.armorTypeId], base = num(armor.definition.armorClass) ?? 10;
    ac = base + (t === 'heavy' ? 0 : t === 'medium' ? Math.min(2, dex) : dex); how = `${armor.definition.name}` + (t === 'heavy' ? ' (heavy: no Dexterity)' : t === 'medium' ? ' + Dexterity (at most 2)' : ' + Dexterity');
  } else if (features.includes('Unarmored Defense') && c.classes.some(k => k.name === 'Barbarian')) { ac = 10 + dex + con; how = 'Unarmored Defense: 10 + Dexterity + Constitution'; }
  else if (features.includes('Unarmored Defense') && c.classes.some(k => k.name === 'Monk') && !shield) { ac = 10 + dex + mod(c.abilities.wis ?? 10); how = 'Unarmored Defense: 10 + Dexterity + Wisdom'; }
  else { ac = 10 + dex; how = 'no armor worn: 10 + Dexterity'; }
  if (shield) { ac += num(shield.definition.armorClass) ?? 2; how += ' + Shield'; }
  const acBonus = sum('armor-class') + (armor ? sum('armored-armor-class') : 0);
  if (acBonus) { ac += acBonus; how += ` + ${acBonus} from features or items`; }
  if (c.abilities.dex !== null) { c.combat.ac = ac; worked(c, 'Armor Class', ac, how); }
  if ((d.characterValues ?? []).length) c.import.unmapped.push(`${d.characterValues.length} custom value(s) set on D&D Beyond (overrides such as a custom Armor Class are not applied).`);

  const walk = num(d.race?.weightSpeeds?.normal?.walk);
  if (walk) {
    const extra = sum('speed') + sum('speed-walking') + (armor ? 0 : sum('unarmored-movement'));
    c.combat.speed = walk + extra;
    (extra ? worked : read)(c, 'Speed', c.combat.speed, extra ? `species ${walk} + ${extra} from features` : 'race.weightSpeeds.normal.walk');
  }

  // the attack: the first equipped weapon
  const w = inv.find(it => it.equipped && it.definition?.filterType === 'Weapon') ?? inv.find(it => it.definition?.filterType === 'Weapon');
  if (w) {
    const def = w.definition, props = new Set((def.properties ?? []).map(p => p.name));
    const ranged = def.attackType === 2, magic = (def.grantedModifiers ?? []).filter(m => m.type === 'bonus' && m.subType === 'magic').reduce((n, m) => n + (num(m.value) ?? 0), 0);
    const abil = props.has('Finesse') ? (mod(c.abilities.dex ?? 10) >= mod(c.abilities.str ?? 10) ? 'dex' : 'str') : ranged ? 'dex' : 'str';
    const m = mod(c.abilities[abil] ?? 10), prof = profFor(level);
    const dice = def.damage?.diceCount ? { count: def.damage.diceCount, die: def.damage.diceValue } : diceOf(def.damage?.diceString);
    if (dice) setAttack(c, { name: def.name, atk: prof + m + magic, count: dice.count, die: dice.die, bonus: m + magic, reach: props.has('Reach') ? 10 : 5 },
      `${abil.toUpperCase()} ${m >= 0 ? '+' : ''}${m}, proficiency +${prof} (assumed: check)${magic ? ', magic +' + magic : ''}`);
  }

  c.feats = (d.feats ?? []).map(f => f.definition?.name).filter(Boolean);
  c.features = [...features, ...(d.race?.racialTraits ?? []).map(t => t.definition?.name).filter(Boolean)];
  const spellList = [...(d.classSpells ?? []).flatMap(k => k.spells ?? []), ...Object.values(d.spells ?? {}).flatMap(x => x ?? [])];
  const seen = new Set();
  c.spells = spellList.map(s => s.definition).filter(s => s?.name && !seen.has(s.name) && seen.add(s.name)).map(s => ({ name: s.name, level: num(s.level) ?? 0 }));
  c.equipment = inv.map(it => it.definition?.name && (num(it.quantity) > 1 ? `${it.definition.name} ×${it.quantity}` : it.definition.name)).filter(Boolean);
  c.proficiencies = [...new Set(mods.filter(m => ['proficiency', 'expertise'].includes(m.type) && m.friendlySubtypeName).map(m => m.friendlySubtypeName + (m.type === 'expertise' ? ' (expertise)' : '')))];
  c.languages = [...new Set(mods.filter(m => m.type === 'language').map(m => m.friendlySubtypeName).filter(Boolean))];
  c.notes = [d.notes?.backstory, d.traits?.personalityTraits].filter(Boolean).join('\n\n').slice(0, 4000);
  for (const [label, n] of [['Spells', c.spells.length], ['Features', c.features.length], ['Feats', c.feats.length], ['Items', c.equipment.length]]) if (n) read(c, label, n + ' listed', 'D&D Beyond lists');
  if ((d.customItems ?? []).length) c.import.unmapped.push(`${d.customItems.length} custom item(s).`);
  if ((d.customActions ?? []).length) c.import.unmapped.push(`${d.customActions.length} custom action(s).`);
  for (const o of [...(d.options?.class ?? []), ...(d.options?.race ?? []), ...(d.options?.feat ?? [])]) if (o.definition?.name) c.import.unmapped.push(`Option chosen: ${o.definition.name}`);
  portrait(c, d.decorations?.avatarUrl ?? d.avatarUrl, 'The D&D Beyond portrait');
  return finishReport(c, d);
}

// ------------------------------------------------------------------ Roll20 (journal exporter JSON, 5e by Roll20 sheet)
export function fromRoll20(v) {
  const c = blankCharacter(), at = new Map((v.attribs ?? []).map(a => [String(a.name), a]));
  startReport(c, 'Roll20 (exported character)');
  const cur = n => at.get(n)?.current, used = new Set();
  const take = (n, label, into) => { const x = cur(n); if (x !== undefined && x !== '') { used.add(n); read(c, label, x, n); into?.(x); } return x; };
  c.name = String(v.name ?? '').trim(); read(c, 'Name', c.name, 'name');
  for (const k of ABILITIES) take(FULL[k], k.toUpperCase(), x => { c.abilities[k] = num(x); });
  const cls = cur('class'), lvl = num(cur('base_level') ?? cur('level'));
  if (cls) { used.add('class'); c.classes.push({ name: cls, level: lvl ?? null, ...(cur('subclass') ? { subclass: cur('subclass') } : {}) }); }
  for (const i of [1, 2, 3]) if (num(cur(`multiclass${i}_flag`)) === 1 && cur(`multiclass${i}`)) c.classes.push({ name: title(cur(`multiclass${i}`)), level: num(cur(`multiclass${i}_lvl`)) });
  for (const k of c.classes) read(c, 'Class', `${k.name} ${k.level ?? '?'}`, 'class / multiclass');
  c.species = take('race_display', 'Species') ?? take('race', 'Species') ?? '';
  c.background = take('background', 'Background') ?? '';
  const hp = num(at.get('hp')?.max); if (hp) { used.add('hp'); c.combat.hp_max = hp; read(c, 'Hit points', hp, 'hp (max)'); }
  take('ac', 'Armor Class', x => { c.combat.ac = num(x); });
  take('speed', 'Speed', x => { c.combat.speed = num(x); });
  // the first attack row: its name, the bonus the sheet shows, and its damage
  const row = [...at.keys()].map(k => k.match(/^repeating_attack_([^_]+)_atkname$/)?.[1]).find(Boolean);
  if (row) {
    const p = `repeating_attack_${row}_`, name = cur(p + 'atkname'), atk = num(cur(p + 'atkbonus')), dmg = String(cur(p + 'dmgbase') ?? '');
    const dice = diceOf(dmg), flat = dmg.match(/[+-]\s*\d+\s*$/), attr = String(cur(p + 'dmgattr') ?? '').match(/@\{(\w+)_mod\}/)?.[1];
    const bonus = flat ? num(flat[0]) : attr && FULL_KEYS[attr] && c.abilities[FULL_KEYS[attr]] !== null ? mod(c.abilities[FULL_KEYS[attr]]) : null;
    if (atk !== null && dice && bonus !== null) setAttack(c, { name, atk, count: dice.count, die: dice.die, bonus, reach: 5 }, 'the attack row: its shown bonus, damage dice and damage ability');
    else c.import.unmapped.push(`Attack ${name}: its numbers are formulas Roll20 works out; enter them by hand.`);
  }
  const rows = re => [...at.entries()].filter(([k]) => re.test(k)).map(([k, a]) => (used.add(k), a.current)).filter(Boolean);
  c.spells = [...at.keys()].map(k => k.match(/^repeating_spell-(cantrip|\d)_[^_]+_spellname$/)).filter(Boolean).map(m => (used.add(m[0]), { name: cur(m[0]), level: m[1] === 'cantrip' ? 0 : +m[1] })).filter(s => s.name);
  c.features = rows(/^repeating_traits_[^_]+_name$/);
  c.equipment = rows(/^repeating_inventory_[^_]+_itemname$/);
  c.proficiencies = Object.keys(SKILL_KEYS).filter(k => { const x = String(cur(k + '_prof') ?? ''); return x && x !== '0'; }).map(k => SKILL_KEYS[k]);
  const left = [...at.keys()].filter(k => !used.has(k) && !/^repeating_/.test(k) && cur(k) !== '' && cur(k) !== undefined);
  if (left.length) c.import.unmapped.push(`${left.length} other Roll20 fields (kept in the extract): ${left.slice(0, 12).join(', ')}${left.length > 12 ? '…' : ''}`);
  portrait(c, v.avatar, 'The Roll20 avatar');
  return finishReport(c, v);
}
const FULL_KEYS = Object.fromEntries(Object.entries(FULL).map(([k, v]) => [v, k]));
const SKILL_KEYS = { acrobatics: 'Acrobatics', animal_handling: 'Animal Handling', arcana: 'Arcana', athletics: 'Athletics', deception: 'Deception', history: 'History', insight: 'Insight', intimidation: 'Intimidation', investigation: 'Investigation', medicine: 'Medicine', nature: 'Nature', perception: 'Perception', performance: 'Performance', persuasion: 'Persuasion', religion: 'Religion', sleight_of_hand: 'Sleight of Hand', stealth: 'Stealth', survival: 'Survival' };

// ------------------------------------------------------------------ any other JSON: matched by field names, and said so
export function fromGenericJSON(v) {
  const fields = [];
  (function flat(x, path, depth) {
    if (fields.length > 5000 || depth > 8) return;
    if (x && typeof x === 'object') { for (const [k, y] of Object.entries(x)) flat(y, path ? path + '.' + k : k, depth + 1); }
    else if (x !== null && x !== undefined && x !== '') fields.push([path, String(x)]);
  })(v, '', 0);
  const c = fromFields(fields, 'JSON (unknown layout)'), matched = c.provenance.fields ?? {};
  startReport(c, 'JSON (unknown layout: matched by field names only)');
  for (const [k, f] of Object.entries(matched)) read(c, k, f.value, f.path);
  c.import.unmapped.push('This program\'s layout is not known here: every value above was matched by its field name. Check each one.');
  const pic = fields.find(([k, x]) => /avatar|portrait|image|img/i.test(k) && /^(data:image|https?:)/.test(x));
  if (pic) portrait(c, pic[1], 'A picture named in the file (' + pic[0] + ')');
  finishReport(c, v);
  c.provenance.fields = matched;
  return c;
}

// ------------------------------------------------------------------ pictures inside a PDF (pdf.js)
// The images a PDF draws, page content and form-field pictures alike (a D&D Beyond or Mythastria sheet's portrait box is
// a picture button), largest first, as small data: URLs. `box` (optional): {page, rect: [x1, y1, x2, y2]} in PDF units,
// the portrait box of a known sheet: the page is drawn and that box cut out, whatever the picture is made of.
export async function pdfPictures(pdfjs, pdf, { max = 4, px = 256, box = null } = {}) {
  const out = [];
  if (box) {
    try {
      const page = await pdf.getPage(box.page), scale = 2, view = page.getViewport({ scale });
      const canvas = document.createElement('canvas'); canvas.width = Math.ceil(view.width); canvas.height = Math.ceil(view.height);
      // intent print: drawn without waiting for animation frames (a hidden window gives none); printed widgets included
      await page.render({ canvasContext: canvas.getContext('2d'), viewport: view, intent: 'print', annotationMode: pdfjs.AnnotationMode.ENABLE_FORMS }).promise;
      const [x1, y1, x2, y2] = view.convertToViewportRectangle(box.rect).map(Math.round);
      const sx = Math.min(x1, x2) + 3, sy = Math.min(y1, y2) + 3, w = Math.abs(x2 - x1) - 6, h = Math.abs(y2 - y1) - 6;
      const data = canvas.getContext('2d').getImageData(sx, sy, w, h).data;
      let ink = 0; for (let i = 0; i < data.length; i += 16) if (data[i] + data[i + 1] + data[i + 2] < 700) ink++;
      if (ink > data.length / 16 * 0.04) out.push({ kind: 'data', value: scaled(canvas, sx, sy, w, h, px), label: 'The portrait box of the sheet' });
    } catch { /* fall back to the pictures themselves */ }
  }
  const found = [];
  for (let n = 1; n <= Math.min(pdf.numPages, 6); n++) {
    const page = await pdf.getPage(n), ops = await page.getOperatorList();
    for (let i = 0; i < ops.fnArray.length && found.length < 24; i++) {
      const fn = ops.fnArray[i];
      if (fn === pdfjs.OPS.paintImageXObject || fn === pdfjs.OPS.paintImageXObjectRepeat) {
        const img = await objectOf(page, ops.argsArray[i][0]);
        if (img) found.push({ img, page: n });
      } else if (fn === pdfjs.OPS.paintInlineImageXObject) found.push({ img: ops.argsArray[i][0], page: n });
    }
  }
  const seen = new Set();
  for (const { img, page } of found.sort((a, b) => b.img.width * b.img.height - a.img.width * a.img.height)) {
    if (out.length >= max) break;
    const w = img.width, h = img.height;
    if (!w || !h || w < 64 || h < 64 || w / h > 3 || h / w > 3 || seen.has(w + 'x' + h + ':' + page)) continue;
    seen.add(w + 'x' + h + ':' + page);
    const url = imageURL(img, px);
    if (url) out.push({ kind: 'data', value: url, label: `Picture on page ${page} (${w}×${h})` });
  }
  return out;
}
function objectOf(page, id) {
  return new Promise(resolve => {
    const store = String(id).startsWith('g_') ? page.commonObjs : page.objs, timer = setTimeout(() => resolve(null), 3000);
    try {
      if (store.has(id)) { clearTimeout(timer); resolve(store.get(id)); }
      else store.get(id, v => { clearTimeout(timer); resolve(v); });
    } catch { clearTimeout(timer); resolve(null); }
  });
}
function scaled(source, sx, sy, w, h, px) {
  const k = Math.min(1, px / Math.max(w, h)), out = document.createElement('canvas');
  out.width = Math.max(1, Math.round(w * k)); out.height = Math.max(1, Math.round(h * k));
  out.getContext('2d').drawImage(source, sx, sy, w, h, 0, 0, out.width, out.height);
  return out.toDataURL('image/webp', .85);
}
function imageURL(img, px) {
  const w = img.width, h = img.height;
  let src = img.bitmap;
  if (!src && img.data) {
    src = document.createElement('canvas'); src.width = w; src.height = h;
    const ctx = src.getContext('2d'), id = ctx.createImageData(w, h), o = id.data, d = img.data;
    if (img.kind === 3) o.set(d.subarray(0, o.length));
    else if (img.kind === 2) for (let i = 0, j = 0; i < w * h; i++) { o[j++] = d[i * 3]; o[j++] = d[i * 3 + 1]; o[j++] = d[i * 3 + 2]; o[j++] = 255; }
    else if (img.kind === 1) { const row = (w + 7) >> 3; for (let y = 0; y < h; y++) for (let x = 0; x < w; x++) { const on = (d[y * row + (x >> 3)] >> (7 - (x & 7))) & 1, j = (y * w + x) * 4; o[j] = o[j + 1] = o[j + 2] = on ? 255 : 0; o[j + 3] = 255; } }
    else return null;
    ctx.putImageData(id, 0, 0);
  }
  if (!src) return null;
  try { return scaled(src, 0, 0, w, h, px); } catch { return null; }
}

// A picture address fetched on the GM's click: only images, at most 5 MB, without cookies. Many sites refuse a page from
// another address (CORS); then the GM saves the picture and adds it as a photo instead.
export async function fetchPortrait(url, fetchFn = globalThis.fetch) {
  const u = new URL(url);
  if (!['https:', 'http:'].includes(u.protocol)) throw Error('Only web addresses can be fetched.');
  let res;
  try { res = await fetchFn(u.href, { credentials: 'omit', referrerPolicy: 'no-referrer', signal: AbortSignal.timeout(15000) }); }
  catch { throw Error(`${u.hostname} would not send the picture to this page. Open the address, save the picture, then use Add photo.`); }
  if (!res.ok) throw Error(`${u.hostname} answered ${res.status}. Save the picture yourself, then use Add photo.`);
  const blob = await res.blob();
  if (!/^image\//.test(blob.type) || blob.size > 5_000_000) throw Error('That address is not a picture of 5 MB or less.');
  return blob;
}

// ------------------------------------------------------------------ the readers in character-import.mjs, reported the same way
// XML, PDF, CSV and text sheets are matched by field names (character-import.mjs fromFields); this lists what was matched
// and what is missing, as the other importers do.
export function reportFromFields(c, source) {
  const matched = c.provenance?.fields ?? {}, raw = c.provenance?.raw ?? '', truncated = c.provenance?.truncated;
  const keepWarnings = (c.warnings ?? []).filter(w => /PDF text layout|truncated/.test(w));
  startReport(c, source);
  for (const [k, f] of Object.entries(matched)) read(c, k.replace(/_/g, ' '), f.value, f.path);
  c.import.unmapped.push('Fields not listed here are kept in the extract below, unused.');
  finishReport(c, raw);
  c.provenance.fields = matched; c.provenance.raw = raw; c.provenance.truncated = truncated;
  c.warnings.push(...keepWarnings);
  return c;
}

// Fantasy Grounds (5E ruleset) XML: hp.total, defenses.ac.total and speed.total are totals, but a weapon's attackbonus is only
// the extra on top of proficiency and the ability, and its damage dice are "d6,d6". The weapon is worked out here instead of
// taking that extra as the whole bonus.
export function hardenFG(c) {
  const fields = c._fields ?? [];
  const root = fields[0]?.[0].split('.')[0] ?? '';
  const get = p => fields.find(([q]) => q === root + '.' + p)?.[1];
  const fg = fields.some(([q]) => q.startsWith(root + '.weaponlist.') || q.startsWith(root + '.defenses.ac.'));
  c.provenance ??= { fields: {} };
  const matched = c.provenance.fields ?? {};
  if (matched.attack_bonus && /weaponlist/.test(matched.attack_bonus.path)) { c.combat.attack_bonus = null; delete matched.attack_bonus; }
  if (matched.damage_die && /weaponlist|damagelist/.test(matched.damage_die.path)) { c.combat.damage_die = null; c.combat.damage_count = 1; delete matched.damage_die; }
  if (matched.damage_bonus && /weaponlist|damagelist/.test(matched.damage_bonus.path)) { c.combat.damage_bonus = null; delete matched.damage_bonus; }
  reportFromFields(c, fg ? 'Fantasy Grounds (XML)' : 'XML');
  if (!fg) return c;
  const level = (c.classes ?? []).reduce((n, k) => n + (k.level || 0), 0) || num(get('level')) || 1;
  const prof = num(get('profbonus')) ?? profFor(level);
  const ids = [...new Set(fields.map(([q]) => q.match(new RegExp('^' + root + '\.weaponlist\.([^.]+)\.'))?.[1]).filter(Boolean))];
  const wf = (id, k) => get(`weaponlist.${id}.${k}`);
  const id = ids.find(i => num(wf(i, 'carried')) === 2) ?? ids[0];
  if (id) {
    const name = wf(id, 'name') ?? 'Weapon', ranged = num(wf(id, 'type')) === 1, props = String(wf(id, 'properties') ?? '').toLowerCase();
    const best = (a, b) => (mod(c.abilities[a] ?? 10) >= mod(c.abilities[b] ?? 10) ? a : b);
    const statName = String(wf(id, 'attackstat') ?? '').toLowerCase();
    const stat = FULL_KEYS[statName] ?? (props.includes('finesse') ? best('dex', 'str') : ranged ? 'dex' : 'str');
    const dmgId = [...new Set(fields.map(([q]) => q.match(new RegExp('^' + root + `\.weaponlist\.${id}\.damagelist\.([^.]+)\.`))?.[1]).filter(Boolean))][0];
    const df = k => wf(id, `damagelist.${dmgId}.${k}`);
    const dice = String(df('dice') ?? '').split(',').map(s => s.trim()).filter(Boolean).map(s => s.match(/^(\d*)d(\d+)$/i)).filter(Boolean);
    const sizes = new Set(dice.map(m => +m[2]));
    if (c.abilities[stat] === null || c.abilities[stat] === undefined) c.import.unmapped.push(`${name}: the ${stat.toUpperCase()} score is missing, so its attack can't be worked out.`);
    else if (!dice.length || sizes.size !== 1) c.import.unmapped.push(`${name}: its damage dice "${df('dice') ?? ''}" can't be read as one kind of die; enter the attack by hand.`);
    else {
      const m = mod(c.abilities[stat]), proficient = num(wf(id, 'prof')) !== 0, extra = num(wf(id, 'attackbonus')) ?? 0;
      const dstat = String(df('stat') ?? 'base').toLowerCase(), dm = dstat === 'base' ? m : FULL_KEYS[dstat] ? mod(c.abilities[FULL_KEYS[dstat]] ?? 10) : 0;
      setAttack(c, { name, atk: (proficient ? prof : 0) + m + extra, count: dice.reduce((n, d) => n + (+d[1] || 1), 0), die: [...sizes][0],
        bonus: dm + (num(df('bonus')) ?? 0), reach: props.includes('reach') ? 10 : 5 },
        `${stat.toUpperCase()} ${m >= 0 ? '+' : ''}${m}${proficient ? ', proficiency +' + prof : ', not proficient'}${extra ? ', weapon bonus ' + extra : ''} (Fantasy Grounds weapon list)`);
      c.import.missing = c.import.missing.filter(x => !['Attack bonus', 'Damage dice', 'Damage bonus'].includes(x));
      c.warnings = c.warnings.map(w => w.startsWith('Missing') ? (c.import.missing.length ? 'Missing (fill these in on the sheet): ' + c.import.missing.join(', ') + '.' : '') : w).filter(Boolean);
    }
  }
  const powers = fields.filter(([q]) => new RegExp('^' + root + '\.powers\.[^.]+\.name$').test(q));
  if (powers.length) c.spells = powers.map(([q, v]) => ({ name: v, level: num(get(q.slice(root.length + 1).replace(/name$/, 'level'))) ?? 0 }));
  const featuresList = fields.filter(([q]) => new RegExp('^' + root + '\.(featurelist|traitlist)\.[^.]+\.name$').test(q)).map(([, v]) => v);
  if (featuresList.length) c.features = [...new Set([...(c.features ?? []), ...featuresList])];
  const tok = get('token');
  if (tok) c.import.portraits.push({ kind: 'path', value: tok, label: 'The Fantasy Grounds token (a file in FG\'s own folder)' });
  return c;
}

// A PDF: the field-name match, plus D&D Beyond's and the official sheet's numbered lists, plus the pictures found.
// D&D Beyond's character sheet PDF (its export as of 2026-10: PDFsharp, the values in named widgets, no AcroForm; the
// widgets come through character-import.mjs widgetFields). Read by D&D Beyond's own field names, never by guesswork.
const DDB_SKILLS = { Acrobatics: 'Acrobatics', Animal: 'Animal Handling', Arcana: 'Arcana', Athletics: 'Athletics', Deception: 'Deception', History: 'History', Insight: 'Insight', Intimidation: 'Intimidation', Investigation: 'Investigation', Medicine: 'Medicine', Nature: 'Nature', Perception: 'Perception', Performance: 'Performance', Persuasion: 'Persuasion', Religion: 'Religion', SleightofHand: 'Sleight of Hand', Stealth: 'Stealth', Survival: 'Survival' };
const DDB_ABBR = { str: 'Str', dex: 'Dex', con: 'Con', int: 'Int', wis: 'Wis', cha: 'Cha' };
export function isDDBPdf(form) { const names = Object.keys(form ?? {}).map(n => n.replace(/\s+/g, ' ').trim()); return names.includes('CLASS LEVEL') && (names.includes('CharacterName') || names.some(n => /^spellName\d+$/.test(n))); }
function ddbPdf(base, extra) {
  const form = extra.form, keys = new Map(Object.keys(form).map(k => [k.replace(/\s+/g, ' ').trim().toLowerCase(), k])), used = new Set();
  const item = n => { const k = keys.get(n.toLowerCase()); if (!k) return null; used.add(k); return form[k].find(i => i.value !== undefined && i.value !== null && String(i.value).trim() !== '' && String(i.value) !== 'Off') ?? null; };
  const val = n => { const it = item(n); return it ? String(it.value).replace(/\s+/g, ' ').trim() : ''; };
  const c = blankCharacter();
  startReport(c, 'D&D Beyond PDF');
  const take = (label, n, into) => { const v = val(n); if (v) { into(v); read(c, label, v, 'field ' + n); } return v; };
  take('Name', 'CharacterName', v => { c.name = v; });
  take('Class and level', 'CLASS LEVEL', v => { c.classes = v.split('/').map(s => s.trim()).filter(Boolean).map(s => { const m = s.match(/^(.*?)\s+(\d+)\s*(?:\((.+)\))?$/); return m ? { name: m[1], level: +m[2], ...(m[3] ? { subclass: m[3] } : {}) } : { name: s, level: null }; }); });
  take('Species', 'RACE', v => { c.species = v; }) || take('Species', 'SPECIES', v => { c.species = v; });
  take('Background', 'BACKGROUND', v => { c.background = v; });
  take('Size', 'SIZE', v => { c.size = v; });
  for (const a of ABILITIES) take(a.toUpperCase(), a.toUpperCase(), v => { c.abilities[a] = num(v); });
  for (const n of ['STRmod', 'DEXmod', 'CONmod', 'INTmod', 'WISmod', 'CHamod', 'CHAmod', 'ST Strength', 'ST Dexterity', 'ST Constitution', 'ST Intelligence', 'ST Wisdom', 'ST Charisma']) val(n);   // worked out from the scores
  c.saves = ABILITIES.filter(a => val(DDB_ABBR[a] + 'Prof') !== '');          // the box holds a mark (•) when proficient
  if (c.saves.length) read(c, 'Saving throw proficiencies', c.saves.map(a => a.toUpperCase()).join(', '), 'the • marks (StrProf ... ChaProf)');
  for (const [k, skill] of Object.entries(DDB_SKILLS)) { const m = val(k + 'Prof'); val(k); val(k + 'Mod'); if (/^E/i.test(m)) c.proficiencies.push(skill + ' (expertise)'); else if (/^P/i.test(m)) c.proficiencies.push(skill); }
  if (c.proficiencies.length) read(c, 'Skill proficiencies', c.proficiencies.join(', '), 'the P / E marks beside the skills');
  take('Armor Class', 'AC', v => { c.combat.ac = num(v); });
  take('Hit points', 'MaxHP', v => { c.combat.hp_max = num(v); });
  take('Speed', 'Speed', v => { c.combat.speed = num(String(v).match(/\d+/)?.[0]); });
  take('Initiative', 'Init', () => {}); take('Proficiency bonus', 'ProfBonus', () => {});
  take('Senses', 'AdditionalSenses', v => { c.senses = v; });
  const defenses = take('Defenses', 'Defenses', () => {}), resist = defenses.match(/resistances?:?\s*([^.;]+)/i);
  if (resist) c.damage_resistances = resist[1].split(/,\s*/).map(x => x.trim()).filter(Boolean);
  for (let i = 1; i <= 8; i++) {
    const name = val(i === 1 ? 'Wpn Name' : 'Wpn Name ' + i), hit = val(`Wpn${i} AtkBonus`), dmg = val(`Wpn${i} Damage`);
    val('Wpn Notes ' + i);
    if (!name) continue;
    const m = dmg.match(/(\d+)\s*d\s*(\d+)\s*([+-]\s*\d+)?/i);
    if (c.combat.attack_bonus === null && m && /^[+-]?\d+$/.test(hit)) {
      c.attack_name = name;
      c.combat.attack_bonus = num(hit); c.combat.damage_count = +m[1]; c.combat.damage_die = +m[2]; c.combat.damage_bonus = m[3] ? num(m[3].replace(/\s/g, '')) : 0;
      read(c, 'Attack', `${name}: ${hit} to hit, ${dmg}`, `fields Wpn Name${i > 1 ? ' ' + i : ''}, Wpn${i} AtkBonus, Wpn${i} Damage`);
    } else c.import.unmapped.push(`Attack also on the sheet: ${name} ${hit} ${dmg}`.trim());
  }
  // spells: each name under the nearest level heading above it on its page ("=== CANTRIPS ===", "=== 1st LEVEL ===")
  const indexed = re => [...keys.values()].map(k => [k, k.trim().match(re)]).filter(([, m]) => m).map(([k, m]) => ({ k, i: +m[1], it: form[k].find(x => x.value !== undefined) }));
  const headers = indexed(/^spellHeader(\d+)$/).filter(h => h.it?.value).map(h => { used.add(h.k); return { ...h, level: /cantrip/i.test(h.it.value) ? 0 : num(String(h.it.value).match(/(\d+)/)?.[1]) }; });
  const y = it => (it?.rect ? it.rect[1] : 0), x = it => (it?.rect ? it.rect[0] : 0);
  for (const s of indexed(/^spellName(\d+)$/).sort((a, b) => a.i - b.i)) {
    used.add(s.k);
    const name = String(s.it?.value ?? '').replace(/\s*\[[A-Z]+\]\s*$/, '').trim();    // "[R]": D&D Beyond's ritual tag
    if (!name || c.spells.some(x => x.name === name)) continue;
    const above = headers.filter(h => h.it.page === s.it.page && y(h.it) >= y(s.it) && x(h.it) <= x(s.it) + 30).sort((a, b) => y(a.it) - y(b.it))[0]
      ?? headers.filter(h => h.it.page < s.it.page || (h.it.page === s.it.page && h.i <= s.i)).sort((a, b) => b.it.page - a.it.page || b.i - a.i)[0];
    const source = val('spellSource' + s.i);
    c.spells.push({ name, level: above ? above.level : null, ...(source ? { source } : {}) });
  }
  if (c.spells.length) read(c, 'Spells', c.spells.length + ' listed, each under its level heading', 'fields spellName0, spellName1, ...');
  for (const n of ['spellCastingClass0', 'spellCastingAbility0', 'spellSaveDC0', 'spellAtkBonus0']) take(n.replace(/0$/, '').replace(/([A-Z])/g, ' $1').toLowerCase(), n, () => {});
  // features: "* Name • <book>-2024 91 ..." in the FeaturesTraits boxes
  const ft = indexed(/^FeaturesTraits(\d+)$/).sort((a, b) => a.i - b.i).map(f => { used.add(f.k); return String(f.it?.value ?? ''); }).join('\n');
  c.features = [...new Set([...ft.matchAll(/\*\s*([^•*\n]+?)\s*•/g)].map(m => m[1].replace(/^\d+:\s*/, '').trim()))]
    .filter(f => !/^(core .+ traits|creature type|size|speed|ability score increases?|languages?|hit points|proficiencies)$/i.test(f));   // headings
  if (c.features.length) read(c, 'Features', c.features.length + ' listed', 'fields FeaturesTraits1, 2, ...');
  for (const e of indexed(/^Eq Name(\d+)$/).sort((a, b) => a.i - b.i)) {
    used.add(e.k);
    const n = String(e.it?.value ?? '').trim(), q = num(val('Eq Qty' + e.i));
    val('Eq Weight' + e.i);
    if (n) c.equipment.push(q > 1 ? `${n} x${q}` : n);
  }
  if (c.equipment.length) read(c, 'Equipment', c.equipment.length + ' items', 'fields Eq Name0, Eq Qty0, ...');
  const pl = val('ProficienciesLang');
  for (const [, head, body] of pl.matchAll(/===\s*([A-Z ]+?)\s*===\s*([^=]*)/g)) {
    const items = body.split(',').map(s => s.trim()).filter(Boolean);
    if (/LANGUAGE/.test(head)) c.languages = items; else c.proficiencies.push(...items.map(s => `${s} (${head.trim().toLowerCase()})`));
  }
  if (defenses && !resist) c.import.unmapped.push('Defenses: ' + defenses);
  c.notes = ['PersonalityTraits', 'Ideals', 'Bonds', 'Flaws', 'Backstory'].map(n => [n, val(n)]).filter(([, v]) => v).map(([n, v]) => `${n.replace(/([A-Z])/g, ' $1').trim()}: ${v}`).join('\n\n').slice(0, 4000);
  const all = Object.values(form).flat().map(i => String(i?.value ?? '')).join(' ');
  c.ruleset = /PHB-2024|2024/.test(all) ? 'D&D 2024 (D&D Beyond)' : /PHB-2014|PHB \d/.test(all) ? 'D&D 5e (2014)' : 'Unconfirmed';
  if (c.ruleset !== 'Unconfirmed') read(c, 'Rules', c.ruleset, 'the book references on the sheet');
  const left = [...keys.values()].filter(k => !used.has(k) && form[k].some(i => String(i.value ?? '').trim() && String(i.value) !== 'Off') && !/\d$/.test(k.trim()));
  if (left.length) c.import.unmapped.push(`Not used: ${left.slice(0, 20).map(k => k.trim()).join(', ')}${left.length > 20 ? ', …' : ''}`);
  c.import.unmapped.push('Not used: the second and third page repeats, coins, weights, passive scores, the actions text.');
  for (const p of extra?.pictures ?? []) c.import.portraits.push(p);
  return finishReport(c, (base.provenance?.raw ?? '') + '\n\n' + Object.entries(form).map(([k, v]) => `${k.trim()}: ${v.map(i => i.value).filter(Boolean).join(' / ')}`).filter(l => !/: $/.test(l)).join('\n'));
}

export function pdfReport(c, extra) {
  if (isDDBPdf(extra?.form)) return ddbPdf(c, extra);
  const form = extra?.form ?? {}, names = Object.keys(form);
  const values = re => names.filter(n => re.test(n)).sort((a, b) => (num(a.match(/\d+/)?.[0]) ?? 0) - (num(b.match(/\d+/)?.[0]) ?? 0))
    .map(n => form[n].find(i => i.value)?.value).filter(v => typeof v === 'string' && v.trim()).map(v => v.trim());
  const ddb = names.some(n => /^CLASS\s+LEVEL$/i.test(n)) || names.some(n => /^spellName\d+$/i.test(n));
  reportFromFields(c, ddb ? 'D&D Beyond PDF' : names.length ? 'PDF form' : 'PDF text');
  const spells = values(/^spellName\d+$/i);
  if (spells.length) c.spells = spells.map(n => ({ name: n.replace(/\s*\[.*$/, '') }));
  const feats = values(/^(FeaturesTraits|Features and Traits|FEATURES TRAITS)\d*$/i).flatMap(t => t.split(/\n|\r/)).map(s => s.replace(/^[•*\-=]+\s*/, '').trim()).filter(s => /^[A-Z][\w' ’-]+(?:\s*[•:(]|$)/.test(s)).map(s => s.split(/\s*[•:(]/)[0]).slice(0, 60);
  if (feats.length) c.features = [...new Set(feats)];
  const gear = values(/^(Equipment|EQUIPMENT|Eq Name\d+)$/i).flatMap(t => t.split(/\n|,/)).map(s => s.trim()).filter(Boolean);
  if (gear.length) c.equipment = gear.slice(0, 80);
  for (const p of extra?.pictures ?? []) c.import.portraits.push(p);
  return c;
}

// ------------------------------------------------------------------ the Mythastria character sheet PDF (phase 5)
// A sheet made by the Characters page carries its character (character-sheet-pdf.mjs): that comes back whole, and every
// field changed in the PDF since is applied and listed. A blank sheet filled in by hand is read field by field. The
// portrait comes from the sheet's known box (the "Portrait" field).
const NUM_FIELDS = { HPMax: ['hp_max', 'Hit points'], AC: ['ac', 'Armor Class'], Speed: ['speed', 'Speed'] };
export function fromMythastriaSheet(form, pictures = []) {
  const got = readSheet(form);
  if (!got) return null;
  const v = got.now, c = got.character ? structuredClone(got.character) : blankCharacter();
  startReport(c, got.hand ? 'Mythastria character sheet (filled in by hand)' : 'Mythastria character sheet');
  const fight = new Set();
  const apply = (k, value) => {
    const s = String(value ?? '').trim();
    if (k === 'Name') c.name = s;
    else if (k === 'Species') c.species = s.replace(/\s*\(.*\)$/, '');
    else if (k === 'Background') c.background = s;
    else if (k === 'Size') c.size = s;
    else if (k === 'Rules') c.ruleset = s || c.ruleset;
    else if (k === 'Class') { c.classes = s.split('/').map(x => x.trim()).filter(Boolean).map(x => { const m = x.match(/^(.*?)(?:\s+(\d+))?(?:\s*\((.+)\))?$/); return { name: m[1].trim(), level: m[2] ? +m[2] : null, ...(m[3] ? { subclass: m[3] } : {}) }; }); fight.add('Class'); }
    else if (NUM_FIELDS[k]) { c.combat[NUM_FIELDS[k][0]] = num(s); fight.add(NUM_FIELDS[k][1]); }
    else if (/^(STR|DEX|CON|INT|WIS|CHA)$/.test(k)) { c.abilities[k.toLowerCase()] = num(s); fight.add(k); }
    else if (k === 'Atk1_Bonus') { c.combat.attack_bonus = num(s); fight.add('Attack'); }
    else if (k === 'Atk1_Damage') { const m = s.match(/(\d+)d(\d+)\s*([+-]\s*\d+)?/); if (m) { c.combat.damage_count = +m[1]; c.combat.damage_die = +m[2]; c.combat.damage_bonus = m[3] ? num(m[3]) : 0; } fight.add('Attack'); }
    else if (k === 'Feats') c.feats = s.split(/,\s*/).filter(Boolean);
    else if (k === 'Equipment') c.equipment = s.split(/,\s*|\n/).map(x => x.trim()).filter(Boolean);
    else if (k === 'Features') c.features = s.split(/;\s*|\n/).map(x => x.replace(/\s*\[GM rules\]$/, '').replace(/\s*\([^)]*\d+\)$/, '').trim()).filter(Boolean);
    else if (k === 'Notes') c.notes = s;
    else if (/^Spells\d$/.test(k)) return 'spells';
    else if (/_prof$/.test(k) && k.startsWith('Skill_')) return 'skills';
    else return false;
    return true;
  };
  const respells = () => {
    c.spells = [];
    for (let i = 0; i <= 9; i++) for (const n of String(v['Spells' + i] ?? '').split(/,\s*|\n/).map(x => x.trim()).filter(Boolean)) c.spells.push({ name: n.replace(/\*$/, ''), level: i, ...(n.endsWith('*') ? { always: true } : {}) });
  };
  const reskills = () => {
    const list = [];
    for (const s of Object.keys(SKILLS)) { const m = String(v[skillField(s) + '_prof'] ?? ''); if (m.includes('•') || /[xX*]/.test(m)) list.push(s + (m.replace(/\s/g, '').length >= 2 ? ' (expertise)' : '')); }
    c.proficiencies = [...list, ...(c.proficiencies ?? []).filter(p => !SKILLS[String(p).replace(' (expertise)', '')])];
  };
  if (got.hand) {
    let spells = false, skills = false;
    for (const [k, x] of Object.entries(v)) {
      if (!String(x ?? '').trim()) continue;
      const r = apply(k, x);
      if (r === 'spells') spells = true; else if (r === 'skills') skills = true;
      if (r) read(c, k, x, 'the sheet\'s field ' + k);
    }
    if (spells) respells();
    if (skills) reskills();
    c.ruleset = c.ruleset === 'Unconfirmed' ? 'SRD 5.2.1' : c.ruleset;
  } else {
    let spells = false, skills = false;
    for (const [k, was, now] of got.changed) {
      const r = apply(k, now);
      if (r === 'spells') spells = true; else if (r === 'skills') skills = true;
      if (r) worked(c, k, now || '(empty)', `changed in the PDF (was ${was || 'empty'})`);
      else if (['HPCurrent', 'HPTemp'].includes(k)) c.import.unmapped.push(`${k === 'HPCurrent' ? 'Current' : 'Temporary'} hit points ${now} on the PDF: play state, not kept on the saved sheet.`);
      else c.import.unmapped.push(`${k}: changed in the PDF to "${now}" (was "${was}"). It is worked out from the rest; change what it comes from instead.`);
    }
    if (spells) respells();
    if (skills) reskills();
    if (fight.size && c.derived) {
      delete c.derived;
      c.warnings = ['Fight numbers were changed in the PDF (' + [...fight].join(', ') + '): the sheet keeps them as written. "Change in the builder" is off until you build it again.'];
    }
    if (!got.changed.length) read(c, 'Character', c.name, 'the sheet carries it; nothing was changed in the PDF');
  }
  for (const p of pictures) c.import.portraits.push(p);
  const raw = Object.entries(v).filter(([, x]) => String(x ?? '').trim()).map(([k, x]) => `${k}: ${x}`).join('\n');
  const warnings = c.warnings ?? [];
  finishReport(c, raw);
  if (!got.hand) c.warnings = [...warnings.filter(w => w.startsWith('Fight numbers')), 'From a Mythastria character sheet. Saving it replaces the saved character with the same identity, if there is one.'];
  return c;
}

// ------------------------------------------------------------------ spreadsheets laid out as a sheet (fixed cells)
// GM 2026-10-21: "there's also a popular google sheets character sheet used by many": Iain McEwen's "5e Character Sheet -
// Google Sheets" (https://www.iainmcewen.com/projects/google-character-sheet). Its values sit in fixed cells, not a table.
// Read from the GM's own copy: downloaded as .xlsx (File > Download > Microsoft Excel), as CSV per tab, or a public link.
// The cell map below was taken from the published template on 2026-10-21 (Google Sheet "Character Sheet - Master", tabs
// Welcome, Character, Additional, Spells, Behind the scenes, Supplemental). The template changes over time: a copy whose
// labels have moved is not read by guesswork; the import says the layout was not recognised.

// An .xlsx workbook -> [{name, cells: Map('A1' -> text)}] (zip read here; deflate by the browser's DecompressionStream).
export async function readXlsx(buffer) {
  const b = new Uint8Array(buffer), dv = new DataView(b.buffer, b.byteOffset, b.byteLength);
  if (b.length > 20_000_000) throw Error('That workbook is over 20 MB.');
  let eocd = -1;
  for (let i = b.length - 22; i >= Math.max(0, b.length - 70000); i--) if (dv.getUint32(i, true) === 0x06054b50) { eocd = i; break; }
  if (eocd < 0) throw Error('That file is not an .xlsx workbook.');
  const files = new Map();
  let p = dv.getUint32(eocd + 16, true);
  for (let n = dv.getUint16(eocd + 10, true); n > 0; n--) {
    if (dv.getUint32(p, true) !== 0x02014b50) break;
    const method = dv.getUint16(p + 10, true), size = dv.getUint32(p + 20, true), nameLen = dv.getUint16(p + 28, true);
    const extra = dv.getUint16(p + 30, true), comment = dv.getUint16(p + 32, true), local = dv.getUint32(p + 42, true);
    files.set(new TextDecoder().decode(b.subarray(p + 46, p + 46 + nameLen)), { method, size, local });
    p += 46 + nameLen + extra + comment;
  }
  let total = 0;
  async function text(name) {
    const f = files.get(name);
    if (!f) return null;
    const start = f.local + 30 + dv.getUint16(f.local + 26, true) + dv.getUint16(f.local + 28, true), raw = b.subarray(start, start + f.size);
    const out = f.method === 0 ? raw : new Uint8Array(await new Response(new Blob([raw]).stream().pipeThrough(new DecompressionStream('deflate-raw'))).arrayBuffer());
    if ((total += out.length) > 60_000_000) throw Error('That workbook is too large once unpacked.');
    return new TextDecoder().decode(out);
  }
  const xml = s => new DOMParser().parseFromString(s, 'application/xml');
  const shared = [...xml(await text('xl/sharedStrings.xml') ?? '<sst/>').getElementsByTagName('si')].map(si => [...si.getElementsByTagName('t')].map(t => t.textContent).join(''));
  const book = xml(await text('xl/workbook.xml') ?? '<workbook/>'), rels = xml(await text('xl/_rels/workbook.xml.rels') ?? '<Relationships/>');
  const target = new Map([...rels.getElementsByTagName('Relationship')].map(r => [r.getAttribute('Id'), r.getAttribute('Target')]));
  const sheets = [];
  for (const s of [...book.getElementsByTagName('sheet')].slice(0, 40)) {
    const id = [...s.attributes].find(a => a.name === 'r:id' || a.name.endsWith(':id'))?.value;
    const path = String(target.get(id) ?? '').replace(/^\/?(xl\/)?/, 'xl/');
    const doc = xml(await text(path) ?? '<worksheet/>'), cells = new Map();
    for (const cell of doc.getElementsByTagName('c')) {
      const t = cell.getAttribute('t'), v = cell.getElementsByTagName('v')[0]?.textContent;
      const value = t === 's' ? shared[Number(v)] : t === 'inlineStr' ? [...cell.getElementsByTagName('t')].map(x => x.textContent).join('') : t === 'b' ? (v === '1' ? 'TRUE' : 'FALSE') : v;
      if (value !== undefined && value !== null && String(value).trim() !== '') cells.set(cell.getAttribute('r'), String(value).trim());
    }
    sheets.push({ name: s.getAttribute('name') ?? '', cells });
  }
  return sheets;
}

// CSV rows (one tab) -> Map('A1' -> text)
export function gridFromRows(rows) {
  const cells = new Map(), col = i => { let s = ''; for (i++; i > 0; i = Math.floor((i - 1) / 26)) s = String.fromCharCode(65 + (i - 1) % 26) + s; return s; };
  rows.forEach((row, r) => row.forEach((v, c) => { if (String(v ?? '').trim() !== '') cells.set(col(c) + (r + 1), String(v).trim()); }));
  return cells;
}

export const IAIN_MCEWEN = {
  name: 'Iain McEwen 5e Character Sheet (Google Sheets; template as published 2026-10-21)',
  // labels that must be where the template has them, so the cells beside them mean what the map says
  signature: { I1: 'Race', AB1: 'Class', AD1: 'Subclass', AH1: 'Levels', A6: 'Ability', D6: 'Strength', C25: 'Proficiency Bonus', K25: 'Armor Class' },
  abilities: { str: 'D7', dex: 'H7', con: 'L7', int: 'P7', wis: 'T7', cha: 'X7' },
  saves: { str: 'D12', dex: 'H12', con: 'L12', int: 'P12', wis: 'T12', cha: 'X12' },
  skills: [['B', 'F', 'H'], ['K', 'O', 'Q'], ['T', 'X', 'Z']],                 // label, ability, bonus columns, rows 16-21
};
const ABIL_NAME = { strength: 'str', dexterity: 'dex', constitution: 'con', intelligence: 'int', wisdom: 'wis', charisma: 'cha' };

export function isIainMcEwen(cells) { return Object.entries(IAIN_MCEWEN.signature).every(([ref, label]) => String(cells.get(ref) ?? '').toLowerCase() === label.toLowerCase()); }

// sheets: [{name, cells}] (an .xlsx, or CSV tabs named by their file). A character, or null when no tab has the layout.
export function fromIainMcEwen(sheets) {
  const main = sheets.find(s => isIainMcEwen(s.cells));
  if (!main) return null;
  const tab = n => sheets.find(s => s !== main && s.name.toLowerCase().endsWith(n))?.cells ?? new Map();
  const ch = main.cells, c = blankCharacter(), M = IAIN_MCEWEN;
  startReport(c, M.name);
  const take = (label, ref, into) => { const v = ch.get(ref); if (v) { into(v); read(c, label, v, 'Character!' + ref); } return v; };
  const nameV = ch.get('A1');
  if (nameV && nameV !== 'Name') { c.name = nameV; read(c, 'Name', nameV, 'Character!A1'); }
  take('Species', 'L1', v => { c.species = v; });
  take('Background', 'L2', v => { c.background = v; });
  take('Size', 'L3', v => { c.size = v; });
  for (const r of [2, 3, 4]) {
    const name = ch.get('AB' + r), sub = ch.get('AD' + r), lv = num(ch.get('AH' + r));
    if (name) { c.classes.push({ name, level: lv, ...(sub ? { subclass: sub } : {}) }); read(c, 'Class', `${name} ${lv ?? '?'}${sub ? ' (' + sub + ')' : ''}`, `Character!AB${r}, AD${r}, AH${r}`); }
  }
  for (const [a, ref] of Object.entries(M.abilities)) take(a.toUpperCase(), ref, v => { c.abilities[a] = num(v); });
  take('Hit points', 'AH6', v => { c.combat.hp_max = num(v) || null; });
  take('Armor Class', 'K23', v => { c.combat.ac = num(v); });
  take('Speed', 'P23', v => { c.combat.speed = num(v); });
  const pb = num(ch.get('C23'));
  if (pb) read(c, 'Proficiency bonus', ch.get('C23'), 'Character!C23');
  // proficiencies are not marked on this tab (they live on "Behind the scenes"): worked out from bonus minus modifier
  if (pb) {
    c.saves = ABILITIES.filter(a => c.abilities[a] !== null && num(ch.get(M.saves[a])) === mod(c.abilities[a]) + pb);
    if (c.saves.length) worked(c, 'Saving throw proficiencies', c.saves.map(a => a.toUpperCase()).join(', '), 'each save minus its ability modifier is the proficiency bonus (Character!D12:X12)');
    const profs = [];
    for (const [labelCol, abCol, valCol] of M.skills) for (let r = 16; r <= 21; r++) {
      const skill = ch.get(labelCol + r), ab = ABIL_NAME[String(ch.get(abCol + r) ?? '').toLowerCase()], bonus = num(ch.get(valCol + r));
      if (!skill || !ab || bonus === null || c.abilities[ab] === null) continue;
      const extra = bonus - mod(c.abilities[ab]);
      if (extra >= 2 * pb) profs.push(skill + ' (expertise)'); else if (extra >= pb) profs.push(skill);
    }
    if (profs.length) { c.proficiencies = profs; worked(c, 'Skill proficiencies', profs.join(', '), 'each skill bonus minus its ability modifier (Character!H16:Z21)'); }
  }
  // the attack: the first row that is a real weapon (the template's own Unarmed Strike, Grapple, Shove, Offhand rows skipped)
  const builtin = /^(unarmed strike|grapple|shove|offhand weapon)$/i;
  for (let r = 30; r <= 49; r++) {
    const name = ch.get('A' + r), hit = ch.get('E' + r), dmg = ch.get('G' + r);
    if (!name || builtin.test(name)) continue;
    const m = String(dmg ?? '').match(/(\d+)\s*d\s*(\d+)\s*([+-]\s*\d+)?/i), atk = /^[+-]?\d+$/.test(String(hit ?? '').trim()) ? num(hit) : null;
    if (m && atk !== null) {
      c.combat.attack_bonus = atk; c.combat.damage_count = +m[1]; c.combat.damage_die = +m[2]; c.combat.damage_bonus = m[3] ? num(m[3].replace(/\s/g, '')) : 0;
      read(c, 'Attack', `${name}: ${hit} to hit, ${dmg}`, `Character!A${r}, E${r}, G${r}`);
      break;
    }
    c.import.unmapped.push(`Attack row ${r} (${name}: ${hit ?? ''} ${dmg ?? ''}) is not a to-hit bonus with damage dice.`);
  }
  const list = (cells, col, from, to) => { const out = []; for (let r = from; r <= to; r++) { const v = cells.get(col + r); if (v) out.push(v); } return out; };
  const inv = [];
  for (let r = 31; r <= 49; r++) { const item = ch.get('U' + r), qty = num(ch.get('T' + r)); if (item) inv.push(qty > 1 ? `${item} x${qty}` : item); }
  if (inv.length) { c.equipment = inv; read(c, 'Equipment', inv.length + ' items', 'Character!U31:U49'); }
  const other = list(ch, 'AB', 35, 60);
  if (other.length) { c.proficiencies = [...c.proficiencies, ...other]; read(c, 'Other proficiencies', other.join(', '), 'Character!AB35:AB60'); }
  const senses = list(ch, 'AB', 28, 33);
  if (senses.length) { c.senses = senses.join('; '); read(c, 'Resistances and senses', c.senses, 'Character!AB28:AB33'); }
  const resources = []; for (let r = 19; r <= 26; r++) if (ch.get('AB' + r)) resources.push(`${ch.get('AB' + r)} ${ch.get('AE' + r) ?? ''}/${ch.get('AG' + r) ?? ''} (${ch.get('AH' + r) ?? ''})`);
  const look = [['Alignment', 'L4'], ['Age', 'R1'], ['Gender', 'R2'], ['Height', 'R3'], ['Weight', 'R4'], ['Skin', 'X1'], ['Eyes', 'X2'], ['Hair', 'X3']].filter(([, ref]) => ch.get(ref)).map(([l, ref]) => `${l}: ${ch.get(ref)}`);
  const add = tab('additional'), spells = tab('spells');
  const features = list(add, 'A', 2, 300), notes = list(add, 'F', 2, 300);
  if (features.length) { c.features = features; read(c, 'Features', features.length + ' listed', 'Additional!A2:A300'); }
  c.notes = [look.join(', '), resources.length ? 'Resources: ' + resources.join('; ') : '', ...notes].filter(Boolean).join('\n');
  if (spells.size) {
    ['B', 'D', 'F', 'H', 'J', 'L', 'N', 'P', 'R', 'T'].forEach((col, level) => { for (const n of list(spells, col, 9, 300)) c.spells.push({ name: n, level }); });
    if (c.spells.length) read(c, 'Spells', c.spells.length + ' listed', 'Spells!B9:T300 (cantrips, then levels 1-9)');
    if (spells.get('F2') && spells.get('F2') !== 'None') read(c, 'Spellcasting ability', spells.get('F2'), 'Spells!F2');
  } else c.import.unmapped.push('No Spells tab came with the file: download the whole workbook as .xlsx, or add the Spells tab CSV.');
  if (!add.size) c.import.unmapped.push('No Additional tab came with the file (features and notes).');
  c.import.unmapped.push('Not used: hit dice, death saves, current and temporary hit points, conditions, exhaustion, coins, jump, swim/climb/fly speeds, the "Behind the scenes" and "Supplemental" tabs.');
  const raw = sheets.map(s => `[${s.name}]\n` + [...s.cells].map(([k, v]) => `${k}: ${v}`).join('\n')).join('\n\n');
  return finishReport(c, raw);
}
