// GM 2026-10-24 (SRD_GAPS_PLAN.md group 3): the party's day on the adventure home page. The simulator service keeps one
// day per loaded adventure (Mythastria sim/rests.py, POST /api/adventures/day): the clock, each character's Hit Points,
// Hit Point Dice, slots, uses and Exhaustion carried from one fight to the next, and the Short and Long Rests (SRD 5.2.1).
// The service checks every prerequisite; this page only shows what it says: a rest it can't offer is greyed with the
// reason and a link to what fixes it. The party is this page's (the pregens at the party level, the saved characters).
const el = (tag, text, cls) => { const e = document.createElement(tag); if (text !== undefined) e.textContent = text; if (cls) e.className = cls; return e; };
const ORD = ['', '1st', '2nd', '3rd', '4th', '5th', '6th', '7th', '8th', '9th'];

export function mountDay({ root, post, party, status, onChange = () => {} }) {
  let pack = null, view = null, busy = false;
  const $ = sel => root.querySelector(sel);

  async function send(op, extra = {}) {
    if (!pack || busy) return null;
    const p = party();
    if (!p.members.length && !p.characters.length) { view = null; draw(); return null; }
    busy = true; root.classList.add('busy');
    try {
      const out = await post('/api/adventures/day', { pack, op, members: p.members, level: p.level, ...(p.characters.length ? { characters: p.characters } : {}), ...extra });
      if (out.day) { view = out.day; draw(); }
      if (!out.ok) status(out.refused || out.error || 'Refused.', true);
      else if (op !== 'state') onChange();                          // GM 2026-10-26: Downtime follows the day
      return out;
    } catch { status('The simulator service is not answering.', true); return null; }
    finally { busy = false; root.classList.remove('busy'); }
  }

  function needLink(link) {
    if (!link) return null;
    const b = el('button', '→ ' + link.label, 'quiet day-link');
    b.addEventListener('click', () => {
      if (link.page === 'market') window.open('./play.html#market', 'mythastria-battle');   // GM 2026-10-26: the GM's Market dialog
      else if (link.page.startsWith('#')) { const t = root.querySelector(link.page) || document.querySelector(link.page); t?.scrollIntoView({ block: 'center' }); t?.querySelector('input,button')?.focus(); }
      else window.open(link.page, link.page.includes('play') ? 'mythastria-battle' : '_blank');
    });
    return b;
  }

  function restButton(kind, label, offer) {
    const box = el('div', undefined, 'day-offer'), b = el('button', label, 'day-rest-btn');
    b.id = 'day-' + kind; b.disabled = !offer.ready;
    b.title = offer.ready ? (kind === 'short' ? 'One hour: spend Hit Point Dice, short-rest features come back' : 'Eight hours: all Hit Points, Hit Point Dice, slots and uses; Exhaustion one less') : offer.why;
    b.addEventListener('click', () => send(kind));
    box.append(b);
    if (!offer.ready) { const why = el('p', offer.why, 'day-why'); const l = needLink(offer.link); if (l) why.append(' ', l); box.append(why); }
    return box;
  }

  function line(label, text) { const p = el('p', undefined, 'day-line'); p.append(el('span', label, 'day-label'), ' ' + text); return p; }

  function card(c, rest) {
    const box = el('div', undefined, 'day-char' + (c.status !== 'ok' ? ' day-' + c.status : ''));
    const head = el('div', undefined, 'day-head');
    head.append(el('strong', c.name), el('span', ` ${c.class.charAt(0).toUpperCase() + c.class.slice(1)} ${c.level}`, 'note'));
    if (c.status !== 'ok') head.append(el('span', ' ' + c.status, 'day-status'));
    box.append(head);
    const hp = el('div', undefined, 'day-hp'), bar = el('div', undefined, 'day-bar'), fill = el('span');
    fill.style.width = Math.round(100 * c.hp / Math.max(1, c.hp_max)) + '%'; bar.append(fill);
    hp.append(bar, el('span', `${c.hp}/${c.hp_max} HP` + (c.temp_hp ? ` (+${c.temp_hp} temporary)` : '')));
    box.append(hp);
    box.append(line('Hit Point Dice', c.hit_dice.map(d => `${d.die} ${d.left}/${d.total}`).join(' · ') + ` (Con ${c.con_mod >= 0 ? '+' : ''}${c.con_mod})`));
    if (c.slots.length) box.append(line(c.pact ? 'Pact Magic' : 'Spell slots', c.slots.map(s => `${ORD[s.level]} ${s.left}/${s.max}`).join(' · ')));
    const uses = [...c.uses.map(u => `${u.label} ${u.left}/${u.max}`), ...c.features.map(f => `${f.name} ${f.left}/${f.max}`)];
    if (uses.length) box.append(line('Uses', uses.join(' · ')));
    const ex = el('label', 'Exhaustion ', 'day-ex'), pick = el('select');
    for (let n = 0; n <= 6; n++) pick.append(new Option(String(n), String(n), n === c.exhaustion, n === c.exhaustion));
    pick.title = 'Exhaustion level (SRD 5.2.1: −2 per level to d20 Tests, −5 ft Speed per level; 6 is death). A Long Rest removes one.';
    // HAZARDS-01: its own field (the request's "level" is the party level)
    pick.addEventListener('change', () => send('exhaustion', { name: c.name, exhaustion: Number(pick.value), why: 'set on the adventure page' }));
    ex.append(pick); box.append(ex);
    if (c.dying) box.append(dyingBox(c));
    if (c.resting) box.append(restingLine(c, rest));
    if (c.hazards) box.append(...hazardLines(c));
    if (c.resilience_choice) {                                   // group 3 (GM 2026-10-27): Fiendish Resilience, SRD 5.2.1
      const l = el('label', 'Fiendish Resilience as the rest ends: Resistance to ', 'day-choice'), pick = el('select');
      pick.dataset.resilience = c.name;
      pick.append(new Option(c.resilience ? `keep ${c.resilience}` : 'choose a damage type', ''));
      for (const t of c.resilience_choice) pick.append(new Option(t, t));
      l.append(pick); box.append(l);
    } else if (c.resilience) box.append(line('Fiendish Resilience', `Resistance to ${c.resilience} damage`));
    if (c.magical_cunning) {                                       // CASTER-HIGH (GM 2026-10-28): Warlock 2, Eldritch Master 20
      const m = c.magical_cunning, row = el('div', undefined, 'day-row'), b = el('button', 'Magical Cunning (1-minute rite)', 'quiet day-small');
      b.disabled = !m.ready; b.title = m.ready ? `Once per Long Rest: regains ${m.regains}` : m.why;
      b.addEventListener('click', () => send('magical_cunning', { name: c.name }).then(out => out?.ok && status(out.day.log.at(-1)?.text || '')));
      row.append(b);
      if (!m.ready) { const why = el('span', ' ' + m.why, 'day-why'); const l = needLink(m.link); if (l) why.append(' ', l); row.append(why); }
      box.append(row);
    }
    if (c.status !== 'dead') box.append(castRow(c));
    if (c.status === 'ok' && c.hp < c.hp_max) { const more = el('details', undefined, 'day-more'); more.append(el('summary', 'Heal'), healRow(c)); box.append(more); }
    if (!c.can_rest.met && !c.dying) box.append(el('p', c.can_rest.why, 'day-why'));
    if (rest?.kind === 'short' && c.dice_offers) {
      const dice = el('div', undefined, 'day-dice');
      for (const d of c.dice_offers) {
        const b = el('button', `Spend a ${d.die} (${d.die} ${c.con_mod >= 0 ? '+' : '−'} ${Math.abs(c.con_mod)})`, 'day-die');
        b.disabled = !d.ready; b.title = d.ready ? 'Roll one Hit Point Die; decide on another after the roll' : d.why;
        b.addEventListener('click', () => send('die', { name: c.name, die: d.die }));
        dice.append(b);
      }
      box.append(dice);
      const no = c.dice_offers.find(d => !d.ready);                     // The GM's rule: the reason, and a link when one helps
      if (no && c.dice_offers.every(d => !d.ready)) { const why = el('p', no.why, 'day-why'); const l = needLink(no.link); if (l) why.append(' ', l); box.append(why); }
      if (c.pending?.length) box.append(el('p', 'Rolled: ' + c.pending.map(p => `${p.die} ${p.roll} ${p.con >= 0 ? '+' : '−'} ${Math.abs(p.con)} = ${p.hp}`).join(', ') + ` → +${c.pending.reduce((n, p) => n + p.hp, 0)} HP when the rest ends`, 'day-pending'));
      const ch = c.short_choices || {};
      for (const [key, label] of [['arcane_recovery', 'Arcane Recovery'], ['natural_recovery', 'Natural Recovery']]) {   // RESTS-02: Natural Recovery (Druid 6)
        if (!ch[key]?.spent.length) continue;
        const ar = el('div', undefined, 'day-choice'); ar.dataset.recovery = c.name; ar.dataset.kind = key;
        ar.append(el('span', `${label} (once per Long Rest): slots of combined level up to ${ch[key].budget}, none of level 6+. `, 'note'));
        for (const s of ch[key].spent) {
          const l = el('label', ` ${ORD[s.level]} `), n = el('input'); n.type = 'number'; n.min = '0'; n.max = String(s.spent); n.value = '0'; n.dataset.level = String(s.level);
          l.append(n); ar.append(l);
        }
        box.append(ar);
      }
      if (ch.sorcerous_restoration?.most > 0) {
        const l = el('label', undefined, 'check day-choice'), b = el('input'); b.type = 'checkbox'; b.dataset.restoration = c.name;
        l.append(b, ` Sorcerous Restoration: +${ch.sorcerous_restoration.most} Sorcery Points (once per Long Rest)`); box.append(l);
      }
    }
    return box;
  }

  // ---------------------------------------------------------------- RESTS-02 (GM 2026-10-26, goal 16; Mythastria sim/rests.py)
  // Death saves on the day (SRD 5.2.1): a dying character rolls them here one at a time, or as time passes; a conscious
  // ally stabilizes it with a DC 10 Wisdom (Medicine) check, a Healer's Kit or Spare the Dying; a potion or a spell heals.
  const POTION = [['potion-of-healing', 'Potion of Healing (2d4+2)'], ['potion-of-healing-greater', 'Greater (4d4+4)'],
    ['potion-of-healing-superior', 'Superior (8d4+8)'], ['potion-of-healing-supreme', 'Supreme (10d4+20)']];
  function dyingBox(c) {
    const d = c.dying, box = el('div', undefined, 'day-dying-box');
    if (d.status === 'stable') {
      box.append(el('p', `Stable at 0 Hit Points: regains 1 Hit Point ${d.wakes ? 'at ' + d.wakes : 'after 1d4 hours'} (as time passes). Damage makes it dying again.`, 'day-effects'));
    } else {
      const marks = el('p', undefined, 'day-death');
      marks.append(el('strong', 'Dying: '), `death saves ${'✔'.repeat(d.successes)}${'·'.repeat(3 - d.successes)} successes, ${'✖'.repeat(d.failures)}${'·'.repeat(3 - d.failures)} failures. `,
        el('span', 'Time passing rolls them until stable, conscious or dead.', 'note'));
      box.append(marks);
      const row = el('div', undefined, 'day-row'), save = el('button', 'Roll a death save', 'day-small');
      save.title = 'd20: 10 or more a success, a 1 two failures, a 20 regains 1 Hit Point; three successes: stable; three failures: dead';
      save.addEventListener('click', () => send('death_save', { name: c.name }).then(out => out?.ok && status(out.day.log.at(-1)?.text || '')));
      row.append(save); box.append(row);
      if (!d.helpers.length) box.append(el('p', 'No one conscious in the party can stabilize it.', 'day-why'));
      for (const h of d.helpers) {
        const r = el('div', undefined, 'day-row'); r.append(el('span', h.name + ':', 'day-label'));
        const med = el('button', `Medicine (${h.medicine >= 0 ? '+' : ''}${h.medicine})`, 'quiet day-small');
        med.title = 'A DC 10 Wisdom (Medicine) check; on a failure a round goes by (its death save)';
        med.addEventListener('click', () => send('stabilize', { name: c.name, helper: h.name, how: 'medicine' }).then(out => out?.ok && status(out.day.log.at(-1)?.text || '')));
        const kit = el('button', "Healer's Kit", 'quiet day-small'); kit.title = 'One use of a Healer\'s Kit in ' + h.name + '\'s bag: stable, no check';
        kit.addEventListener('click', () => send('stabilize', { name: c.name, helper: h.name, how: 'kit' }).then(out => out && showLink(out)));
        r.append(med, kit);
        if (h.spare) { const sp = el('button', 'Spare the Dying', 'quiet day-small'); sp.title = 'The cantrip: stable'; sp.addEventListener('click', () => send('stabilize', { name: c.name, helper: h.name, how: 'spare' })); r.append(sp); }
        box.append(r);
      }
    }
    box.append(healRow(c));
    return box;
  }

  function healRow(c) {
    const r = el('div', undefined, 'day-row'), pick = el('select');
    for (const [k, n] of POTION) pick.append(new Option(n, k));
    const give = el('button', 'Give', 'quiet day-small'); give.title = 'A potion from the giver\'s bag (the Market)';
    give.addEventListener('click', () => {
      const by = prompt('Whose bag is the potion in?', view.characters.find(x => x.name !== c.name && x.status === 'ok')?.name ?? c.name);
      if (by) send('heal', { name: c.name, by: by.trim(), item: pick.value }).then(out => out && showLink(out));
    });
    const gm = el('button', 'Heal (GM)…', 'quiet day-small'); gm.title = 'Hit Points regained another way (the GM)';
    gm.addEventListener('click', () => { const hp = prompt(`Hit Points ${c.name} regains:`, '5'); if (hp) send('heal', { name: c.name, hp: Number(hp), why: prompt('From what?', 'the GM') || 'the GM' }); });
    r.append(pick, give, gm);
    return r;
  }

  function showLink(out) {                                             // a refusal's link (the Market for a kit or a potion)
    if (out.ok || !out.link) return;
    const why = el('p', out.refused, 'day-why'); why.append(' ', needLink(out.link));
    $('#day-rest').append(why);
  }

  function restingLine(c, rest) {
    const s = c.resting;
    if (s.lost) return el('p', `Not resting now: interrupted (${s.lost}), no benefits from this Short Rest.`, 'day-why');
    const p = el('p', undefined, s.done ? 'day-effects' : 'day-line');
    if (s.done) p.append(`Rested by ${s.ends}${s.trance ? ' (Trance, 4 hours)' : ''}: done, keeps watch.`);
    else p.append(el('span', 'Resting', 'day-label'), ` until ${s.ends}${s.trance ? ' (Trance: 4 hours, conscious)' : ''}${s.extra ? ` (+${s.extra} hour${s.extra === 1 ? '' : 's'}: interrupted)` : ''}`);
    if (!s.done) {
      const walk = el('button', 'Walked or toiled…', 'quiet day-small');
      walk.title = rest.kind === 'long' ? 'SRD 5.2.1: 1 hour of walking or other physical exertion interrupts a Long Rest (1 more hour)' : 'An hour of walking takes the Short Rest: no benefits';
      walk.addEventListener('click', () => { const h = prompt(`How many hours did ${c.name} walk or toil?`, '1'); if (h) send('exert', { names: [c.name], hours: Number(h), why: prompt('Doing what?', 'walking') || 'walking' }); });
      p.append(' ', walk);
    }
    return p;
  }

  function castRow(c) {
    const r = el('div', undefined, 'day-row'), b = el('button', 'Cast a spell…', 'quiet day-small');
    b.title = 'A spell cast on the day spends its slot; a spell other than a cantrip interrupts the caster\'s rest (SRD 5.2.1). Healing dice heal a target.';
    b.addEventListener('click', () => {
      const spell = prompt('Which spell?', 'Cure Wounds'); if (!spell) return;
      const level = Number(prompt('Slot level (0 for a cantrip):', '1')); if (!Number.isInteger(level)) return;
      const dice = (prompt('Healing dice, if it heals (2d8+3), else empty:', '') || '').trim();
      const target = dice ? prompt('Who is healed?', c.name) : null;
      send('cast', { name: c.name, level, spell, dice, target: target || undefined }).then(out => out && showLink(out));
    });
    const dmg = el('button', 'Hazard damage…', 'quiet day-small');
    dmg.title = 'A fall, burning, a collapsing roof (SRD 5.2.1 Hazards): Resistance and Immunity apply; damage interrupts a rest; at 0 Hit Points death saves begin';
    dmg.addEventListener('click', () => {
      const dice = prompt(`Damage to ${c.name} (dice):`, '2d6'); if (!dice) return;
      const type = prompt('Damage type (bludgeoning, fire, cold ...):', 'bludgeoning'); if (type === null) return;
      send('damage', { names: [c.name], dice: dice.trim(), type: type.trim(), why: prompt('What hurts them?', 'a fall') || 'a hazard' })
        .then(out => out?.ok && status(out.day.log.at(-1)?.text || ''));
    });
    r.append(b, dmg);
    return r;
  }

  // ---------------------------------------------------------------- HAZARDS-01 (GM 2026-10-26; Mythastria sim/hazards.py)
  // Exhaustion's effects, contagions, lasting mental stress, food and water on each card; the GM gives a contagion here.
  // The service rolls every save (SRD 5.2.1) and says what happened in the day's log.
  const CONTAGION = { cackle_fever: 'Cackle Fever', sewer_plague: 'Sewer Plague', sight_rot: 'Sight Rot' };
  const openMore = new Set();
  function hazardLines(c) {
    const h = c.hazards, out = [];
    if (h.effects) out.push(el('p', h.effects + (h.locked ? ` · ${h.locked} level${h.locked === 1 ? '' : 's'} held (${Object.keys(h.locks).map(k => k.replace('_', ' ')).join(', ')}: a Long Rest can't remove ${h.locked === 1 ? 'it' : 'them'})` : ''), 'day-effects'));
    for (const k of h.contagions) {
      const p = el('p', undefined, 'day-contagion'); p.append(el('strong', k.name), ` ${k.state}`); p.title = k.text;
      if (k.key === 'sight_rot') {
        const magic = el('button', 'Heal or Lesser Restoration', 'quiet day-small'); magic.title = 'Either spell ends Sight Rot (SRD 5.2.1)';
        magic.addEventListener('click', () => send('cure', { name: c.name, key: k.key, how: 'magic' }));
        const oint = el('button', 'Ointment…', 'quiet day-small'); oint.title = 'One dose: made in 1 hour by someone proficient with an Herbalism Kit; it holds Sight Rot off for 24 hours (72 hours end it)';
        oint.addEventListener('click', () => { const who = prompt('Who makes the ointment (proficient with an Herbalism Kit, with one in the bag)?', view.characters.find(x => x.hazards?.traits)?.name ?? ''); if (who) send('ointment', { name: c.name, maker: who.trim() }); });
        p.append(' ', magic, ' ', oint);
      }
      const end = el('button', 'End (GM)', 'quiet day-small'); end.title = 'The GM ends it (a cure the SRD leaves to you)';
      end.addEventListener('click', () => { if (confirm(`End ${k.name} on ${c.name}?`)) send('cure', { name: c.name, key: k.key, how: 'gm' }); });
      p.append(' ', end); out.push(p);
    }
    h.stress.forEach((s, n) => {
      const p = el('p', `${s.text}${s.until_text ? ' until ' + s.until_text : ''} (${s.why})`, 'day-contagion');
      for (const [how, label] of s.kind === 'indefinite' ? [['greater', 'Greater Restoration']] : [['lesser', 'Lesser Restoration'], ['gm', 'End (GM)']]) {
        const b = el('button', label, 'quiet day-small'); b.addEventListener('click', () => send('stress_end', { name: c.name, n, how })); p.append(' ', b);
      }
      out.push(p);
    });
    const more = el('details', undefined, 'day-more'), sum = el('summary', 'Food, water and contagions');
    more.open = openMore.has(c.name);                                    // kept open across the page's redraws
    more.addEventListener('toggle', () => { if (more.open) openMore.add(c.name); else openMore.delete(c.name); });
    const row = el('div', undefined, 'day-row');
    const water = el('select'), food = el('select');
    for (const [v, t] of [['full', 'Water: enough'], ['short', 'Water: less than half']]) water.append(new Option(t, v, false, h.rations.water === v));
    for (const [v, t] of [['full', 'Food: enough'], ['short', 'Food: less than half'], ['none', 'Food: none']]) food.append(new Option(t, v, false, h.rations.food === v));
    water.title = 'Checked at the end of each day (SRD 5.2.1 Dehydration): less than half the water: 1 Exhaustion level, held until it drinks its fill';
    food.title = 'Checked at the end of each day (Malnutrition): less than half: a DC 10 Constitution save; nothing for 5 days: a level each day';
    water.addEventListener('change', () => send('rations', { name: c.name, water: water.value }));
    food.addEventListener('change', () => send('rations', { name: c.name, food: food.value }));
    row.append(water, food);
    const give = el('div', undefined, 'day-row'), which = el('select');
    for (const [k, n] of Object.entries(CONTAGION)) which.append(new Option(n, k));
    const expose = el('button', 'Expose (its save)', 'quiet day-small'), infect = el('button', 'Infect', 'quiet day-small');
    expose.title = 'A Constitution save: Cackle Fever DC 10, Sewer Plague DC 11, Sight Rot DC 15'; infect.title = 'No save (a tainted potion, the GM\'s ruling)';
    expose.addEventListener('click', () => send('contagion', { name: c.name, key: which.value, mode: 'expose', why: 'given by the GM' }));
    infect.addEventListener('click', () => send('contagion', { name: c.name, key: which.value, mode: 'infect', why: 'given by the GM' }));
    give.append(which, expose, infect);
    more.append(sum, row, give, el('p', `Speed ${h.speed_now}/${h.speed} ft${h.traits.species ? ' · ' + h.traits.species : ''}${h.traits.armor ? ' · ' + h.traits.armor + ' armor' : ''}${h.traits.resist.length ? ' · Resistance: ' + h.traits.resist.join(', ') : ''}`, 'note'));
    out.push(more);
    return out;
  }

  const WEATHER = [['extreme_cold', 'Extreme cold (0 °F or lower)'], ['extreme_heat', 'Extreme heat (100 °F or higher)'], ['deep_water', 'Swimming in deep water'],
    ['strong_wind', 'Strong wind (fights)'], ['sandstorm', 'Sandstorm (fights)'], ['heavy_precipitation', 'Heavy rain or snow (fights)']];
  const WEATHER_TIP = {
    extreme_cold: 'A DC 10 Constitution save at the end of each hour or 1 Exhaustion level; Resistance or Immunity to Cold: automatic success',
    extreme_heat: 'Without drinkable water: a Constitution save at the end of each hour (DC 5, +1 each hour) or 1 Exhaustion level; Medium or Heavy armor: Disadvantage; Resistance or Immunity to Fire: automatic success',
    deep_water: 'After each hour of swimming, without a Swim Speed: DC 10 Constitution save or 1 Exhaustion level',
    strong_wind: 'Over the adventure\'s fights: Disadvantage on ranged weapon attacks; fliers land or fall; fog disperses; flames go out',
    sandstorm: 'Strong wind, and Disadvantage on Wisdom (Perception) checks', heavy_precipitation: 'Over the adventure\'s fights: Lightly Obscured, Disadvantage on Wisdom (Perception) checks; rain puts out flames' };
  function drawEnv() {
    const box = $('#day-env-body'); if (!box || !view?.environment) return;
    const env = view.environment, grid = el('div', undefined, 'day-env-grid');
    const sendEnv = () => send('environment', { weather: [...box.querySelectorAll('[data-weather]:checked')].map(b => b.dataset.weather),
      shelter: box.querySelector('#day-shelter').checked, water: box.querySelector('#day-water').checked });
    for (const [k, label] of WEATHER) {
      const l = el('label', undefined, 'check'), b = el('input'); b.type = 'checkbox'; b.dataset.weather = k; b.checked = env.weather.includes(k);
      l.title = WEATHER_TIP[k]; b.addEventListener('change', sendEnv); l.append(b, ' ' + label); grid.append(l);
    }
    for (const [id, label, on, tip] of [['day-shelter', 'Sheltered (no exposure while time passes or the party rests)', env.shelter, 'Travel is always exposed'],
      ['day-water', 'Drinkable water at hand (no Extreme Heat saves)', env.water, 'SRD 5.2.1: Extreme Heat asks its save only without access to drinkable water']]) {
      const l = el('label', undefined, 'check'), b = el('input'); b.type = 'checkbox'; b.id = id; b.checked = on; l.title = tip;
      b.addEventListener('change', sendEnv); l.append(b, ' ' + label); grid.append(l);
    }
    const pace = view.pace?.last ? `Last travel: a ${view.pace.last.pace} pace (${view.pace.last.effect}).` : 'No travel yet today (Region map).';
    const stress = el('button', 'Mental stress…', 'quiet'); stress.title = 'A Wisdom, Intelligence or Charisma save; Psychic damage; a lasting effect on a failure (SRD 5.2.1 Fear and Mental Stress)';
    stress.addEventListener('click', openStress);
    box.replaceChildren(grid, el('p', pace + (view.pace?.forced ? ' ' + view.pace.why : ''), view.pace?.forced ? 'day-why' : 'note'), stress,
      el('p', `Each hour of exposure asks its save as time passes (Pass time, rests, travel). Dawn is ${'06:00'}; a day's end checks food and water.`, 'note'));
  }

  function openStress() {
    const dlg = document.getElementById('stress-dialog'); if (!dlg || !view) return;
    const who = dlg.querySelector('#stress-who');
    who.replaceChildren(...view.characters.map(c => { const l = el('label', undefined, 'check'), b = el('input'); b.type = 'checkbox'; b.value = c.name; b.checked = true; l.append(b, ' ' + c.name); return l; }));
    dlg.showModal();
  }
  document.getElementById('stress-dialog')?.addEventListener('close', e => {
    const dlg = e.target; if (dlg.returnValue !== 'go') return;
    const f = k => dlg.querySelector('#stress-' + k);
    send('stress', { names: [...f('who').querySelectorAll('input:checked')].map(b => b.value), save: f('save').value, dc: Number(f('dc').value),
      dice: f('dice').value.trim(), half: f('half').checked, effect: f('effect').value, condition: f('condition').value, ability: f('ability').value, why: f('why').value.trim() })
      .then(out => out?.ok && status('Mental stress: ' + (out.day.log.at(-1)?.text || '')));
  });

  function choices() {
    const out = {};
    for (const box of root.querySelectorAll('[data-recovery]')) {
      const levels = [];
      for (const n of box.querySelectorAll('input')) for (let k = 0; k < Number(n.value || 0); k++) levels.push(Number(n.dataset.level));
      if (levels.length) (out[box.dataset.kind] ??= {})[box.dataset.recovery] = levels;
    }
    for (const b of root.querySelectorAll('[data-restoration]:checked')) (out.sorcerous_restoration ??= {})[b.dataset.restoration] = true;
    for (const s of root.querySelectorAll('[data-resilience]')) if (s.value) (out.fiendish_resilience ??= {})[s.dataset.resilience] = s.value;
    return out;
  }

  function draw() {
    root.hidden = !pack;
    if (!pack) return;
    const clock = $('#day-clock'), rest = $('#day-rest'), chars = $('#day-chars'), log = $('#day-log');
    if (!view) { clock.textContent = 'Choose the party (on the left) to see its day.'; rest.replaceChildren(); chars.replaceChildren(); log.replaceChildren(); return; }
    clock.textContent = view.clock + (view.last_long_rest ? ` · last Long Rest ended ${view.last_long_rest}` : ' · no Long Rest yet this adventure') + (view.fights ? ` · ${view.fights} fight${view.fights === 1 ? '' : 's'}` : '');
    const r = view.rest;
    if (r) {
      const box = el('div', undefined, 'day-under');
      box.append(el('p', `${r.kind === 'short' ? 'Short' : 'Long'} Rest under way: from ${r.started} to ${r.ends} (${r.hours} hour${r.hours === 1 ? '' : 's'}${r.interruptions ? `, ${r.interruptions} interruption${r.interruptions === 1 ? '' : 's'}` : ''})${r.from_long ? ' — the benefits of a Short Rest after a stopped Long Rest' : ''}. Resting: ${r.names.join(', ') || 'no one'}${r.lost?.length ? ` (interrupted: ${r.lost.join(', ')})` : ''}.` +
        (r.elapsed > 0 ? ` ${r.elapsed} hour${r.elapsed === 1 ? '' : 's'} rested so far.` : '')));
      box.append(el('p', 'Damage, a spell other than a cantrip, Initiative and (in a Long Rest) an hour of walking interrupt the one it happens to; each character’s own end is on its card.', 'note'));
      if (r.kind === 'short') box.append(el('p', 'Each character may spend Hit Point Dice (below), one at a time, deciding after each roll. The Hit Points come when the rest ends.', 'note'));
      const row = el('div', undefined, 'day-row');
      const fin = el('button', r.kind === 'short' ? 'Finish the Short Rest' : 'Finish the Long Rest', 'day-rest-btn'); fin.id = 'day-finish';
      fin.addEventListener('click', () => send('finish', choices()).then(out => out?.ok && status('The rest is over. ' + (out.day.log.at(-1)?.text || ''))));
      row.append(fin);
      if (r.kind === 'long') {                                          // RESTS-02: hour by hour (Trance finishes on the way)
        const on = el('button', 'Rest 1 hour', 'quiet'); on.id = 'day-rest-on';
        on.title = 'The rest goes on one hour: that hour’s hazards; a character with Trance is done after 4 hours and keeps watch';
        on.addEventListener('click', () => send('rest_on', { hours: 1 }).then(out => out?.ok && status(`It is ${out.day.clock}. ` + (out.day.log.at(-1)?.text || ''))));
        row.append(on);
      }
      if (r.kind === 'long') {
        const again = el('button', 'Interrupted, keep resting (+1 hour)', 'quiet');
        again.title = 'Something interrupted the rest (damage, a spell, strenuous activity); they resume at once: 1 more hour (SRD 5.2.1)';
        again.addEventListener('click', () => { const why = prompt('What interrupted the rest?', 'a noise in the night'); if (why !== null) send('interrupt', { why }); });
        row.append(again);
      }
      const stop = el('button', 'Stop resting', 'quiet');
      stop.title = r.kind === 'long' ? 'They stop: after at least 1 hour, the benefits of a Short Rest' : 'An interrupted Short Rest confers no benefits';
      stop.addEventListener('click', () => {
        let hours = 0;
        if (r.kind === 'long') { const h = prompt('How many hours did they rest before stopping? (1 or more: the benefits of a Short Rest)', String(Math.max(1, r.elapsed || 0))); if (h === null) return; hours = Number(h); }
        const why = prompt('Why do they stop?', r.kind === 'long' ? 'an attack' : 'interrupted'); if (why === null) return;
        send('stop', { hours, why });
      });
      row.append(stop); box.append(row); rest.replaceChildren(box);
    } else {
      const row = el('div', undefined, 'day-row');
      row.append(restButton('short', 'Short Rest (1 hour)', view.offers.short), restButton('long', 'Long Rest (8 hours)', view.offers.long));
      rest.replaceChildren(row);
      if (view.fight_running) {                                          // the GM may end it (the foes fled, the party left)
        const end = el('button', 'End the fight', 'quiet'); end.id = 'day-end-fight';
        end.title = 'Stop the live fight now; what the characters have left is written into the day';
        end.addEventListener('click', () => { if (confirm('End the fight now? The creatures stop; the characters keep what they have left.')) send('end_fight').then(out => { if (!out?.ok) return; status('The fight is over. ' + (out.day.log.at(-1)?.text || '')); const banner = document.getElementById('adv-fight'); if (banner) banner.hidden = true; }); });
        rest.append(el('p', 'A fight is running on this adventure. ', 'note'));
        rest.lastChild.append(end);
      }
    }
    chars.replaceChildren(...view.characters.map(c => card(c, r)));
    drawEnv();                                                           // HAZARDS-01: the environment and travel pace
    log.replaceChildren(...view.log.slice().reverse().map(e => { const li = el('li'); li.append(el('span', e.when, 'day-when'), ' ' + e.text); return li; }));
    const pass = $('#day-pass button'); if (pass) pass.disabled = !!r;
  }

  $('#day-pass button').addEventListener('click', () => {
    const hours = Number($('#day-hours').value), why = $('#day-why').value.trim();
    send('pass', { hours, why }).then(out => out?.ok && status(`${hours} hour${hours === 1 ? '' : 's'} pass. It is ${out.day.clock}.`));
  });
  $('#day-restore').addEventListener('click', () => {                // GM 2026-10-25: the GM's rest at the start of a map
    send('restore').then(out => out?.ok && status('The party is restored: full health, slots and uses (a Long Rest, no time passes).'));
  });
  $('#day-reset').addEventListener('click', () => {
    if (confirm('Start a new adventure day? The clock goes back to Day 1, 08:00 and everyone is at full strength (the bags are kept).')) send('reset');
  });

  return {
    show(id) { pack = id; draw(); return send('state'); },
    hide() { pack = null; view = null; draw(); },
    refresh() { return pack ? send('state') : null; },
  };
}
