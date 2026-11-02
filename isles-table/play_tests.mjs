// Tests for dist/play-view.mjs (the Play live page arranges the simulator's live fight; it decides nothing).
// Browser runner: tests/replay_tests.html.
import { liveView, targetLook, cardText, actionText, createLivePort, reachPath, reachOutline, SPELL_KEY, spellOf, spellCardText,
  slotsText, spellLook, aimPreview, spellExtras, effectFromCast, auraEffects, actionButtons, doorButtons, ACT_KEY, actLook, mergeExplored, fogCells,
  playerCombatants, withDoors, notePins, upsertNote, deleteNote, noteAt, liveSync, SYNC_CHANNEL, newCastEffects, liveMoved,
  layerEffects, invisibleLook, layerOrder, mountButtons, mountText, doorAim, doorText } from './dist/play-view.mjs';

function assert(cond, text) { if (!cond) throw new Error('FAILED: ' + text); }

const OFFERS = {
  actor: 'pc1', name: 'Hero 1', side: 'friend', movement: 30, action_used: false, attacks_left: 0, attacks_per_action: 1,
  attacks: [{ key: 'weapon', name: 'Greatsword', reach: 5, atk: 5, dmg: '2d6+3', type: 'slashing', ranged: false,
    targets: ['g1', 'pc2'], refused: { g2: "Goblin 2 is 30 ft away: out of Greatsword's reach (5 ft)." } }],
};

export function run() {
  const results = [];
  const test = (name, fn) => { try { fn(); results.push([name, true, '']); } catch (e) { results.push([name, false, e.message]); } };

  test('play: a held attack lights foes, warns on allies and shows the simulator reason on refusals', () => {
    const foe = targetLook(OFFERS, 'weapon', { id: 'g1', name: 'Goblin 1', side: 'foe' });
    assert(foe.cls === 'legal-foe' && foe.reason === '', 'foe');
    const ally = targetLook(OFFERS, 'weapon', { id: 'pc2', name: 'Hero 4', side: 'friend' });
    assert(ally.cls === 'legal-ally' && ally.reason.includes('your side'), 'ally (the SRD allows it)');
    const far = targetLook(OFFERS, 'weapon', { id: 'g2', name: 'Goblin 2', side: 'foe' });
    assert(far.cls === 'refused' && far.reason.includes("out of Greatsword's reach"), 'refused with the reason');
    assert(targetLook(OFFERS, 'weapon', { id: 'pc1', name: 'Hero 1', side: 'friend' }).cls === 'self', 'never itself');
    assert(targetLook(OFFERS, 'ranged', { id: 'g1', side: 'foe' }).cls === 'self', 'no such card: nothing lit');
  });

  test('play: sheet cards and the action line read like a character sheet', () => {
    assert(cardText(OFFERS.attacks[0]) === 'Greatsword · +5 to hit · 2d6+3 slashing · reach 5 ft', cardText(OFFERS.attacks[0]));
    assert(cardText({ name: 'Fire Bolt', atk: 5, dmg: '1d10', type: '', reach: 120, ranged: true }) === 'Fire Bolt · +5 to hit · 1d10 · range 120 ft', 'ranged');
    assert(actionText(OFFERS) === 'Action ready (Attack: 1 attack)', actionText(OFFERS));
    assert(actionText({ ...OFFERS, action_used: true, attacks_left: 1, attacks_per_action: 2 }) === 'Attack action: 1 attack left', 'extra attack');
    assert(actionText({ ...OFFERS, action_used: true, attacks_left: 0 }) === 'Action used', 'used');
  });

  test('play: the map view comes from the replay adapter (positions as the simulator sent them)', () => {
    const scenario = { type: 'scenario', format: 'sim-messages/1', map: { cols: 10, rows: 10, walls: [{ id: 'w1', points: [[0, 6.5], [6, 6.5]] }] } };
    const state = { type: 'state', round: 1, active: 'pc1', combatants: [
      { id: 'pc1', name: 'Hero 1', side: 'friend', pc: true, x: 2, y: 2, hp: 12, hp_max: 12, ac: 17, space_ft: 5 },
      { id: 'g1', name: 'Goblin 1', side: 'foe', x: 3, y: 2, hp: 7, hp_max: 7, ac: 15, space_ft: 5 }] };
    const v = liveView(scenario, { state });
    assert(v.state.combatants[1].x === 3 && v.map.walls.length === 1, 'view');
    assert(liveView(scenario, null) === null, 'no snapshot yet');
  });

  test('play: an imported map brings its picture to the board (VIEW-01)', () => {
    const bg = { src: 'maps/imported/old_mill.png', cols: 6, rows: 4 };
    const scenario = { type: 'scenario', format: 'sim-messages/1', map: { cols: 6, rows: 4, walls: [], background: bg } };
    const state = { type: 'state', round: 1, active: 'pc1', combatants: [{ id: 'pc1', name: 'Hero 1', side: 'friend', pc: true, x: 1, y: 1, hp: 12, hp_max: 12, ac: 17, space_ft: 5 }] };
    assert(JSON.stringify(liveView(scenario, { state }).map.background) === JSON.stringify(bg), 'background kept');
    assert(liveView({ ...scenario, map: { ...scenario.map, background: undefined } }, { state }).map.background === null, 'none: null');
  });
  return results;
}

export async function runAsync() {
  const results = [];
  const test = async (name, fn) => { try { await fn(); results.push([name, true, '']); } catch (e) { results.push([name, false, e.message]); } };

  await test('play: a choice goes to the simulator with the revision; its refusal comes back as said', async () => {
    const sent = [];
    const fake = async (path, init) => {
      if (!init) return { ok: true, json: async () => ({ ok: true, token: 'T' }) };
      sent.push([path, JSON.parse(init.body)]);
      if (path === '/api/live/act') return { ok: false, status: 409, json: async () => ({ ok: false, refused: 'Stale: the fight has moved on.' }) };
      return { ok: true, json: async () => ({ ok: true, live: {} }) };
    };
    const port = createLivePort({ fetch: fake });
    await port.hello();
    const out = await port.act({ op: 'attack', weapon: 'weapon', target: 'g1', revision: 3 });
    assert(out.ok === false && out.status === 409 && out.error === 'Stale: the fight has moved on.', JSON.stringify(out));
    assert(sent[0][0] === '/api/live/act' && sent[0][1].revision === 3 && sent[0][1].token === 'T', 'body');
  });
  await test('play: writes echo fight and actor identity; an explicit old identity is never rewritten', async () => {
    const sent = [];
    const fake = async (path, init) => {
      if (!init) return { ok: true, json: async () => ({ ok: true, token: 'T' }) };
      const body = JSON.parse(init.body);
      sent.push([path, body]);
      return { ok: true, json: async () => ({ ok: true, live: { fight_id: path.endsWith('/new') ? 'first' : 'second', waiting: 'pc2' } }) };
    };
    const port = createLivePort({ fetch: fake });
    await port.hello();
    await port.start({ scenario: 'fixture' });
    await port.act({ op: 'dodge', revision: 0 });
    assert(sent[1][1].fight_id === 'first' && sent[1][1].actor === 'pc2', 'snapshot identity echoed');
    await port.state(0);
    await port.act({ op: 'end', revision: 0, fight_id: 'first', actor: 'old-actor' });
    assert(sent.at(-1)[1].fight_id === 'first' && sent.at(-1)[1].actor === 'old-actor', 'do not retarget an obsolete choice');
  });
  return results;
}

export function runReach() {
  const results = [];
  const test = (name, fn) => { try { fn(); results.push([name, true, '']); } catch (e) { results.push([name, false, e.message]); } };
  test('play: the route to a square follows the simulator\'s previous squares back to the start', () => {
    const offers = { reach: [[3, 2, 5, 2, 2], [4, 2, 10, 3, 2], [4, 1, 15, 4, 2], [2, 1, 5, 2, 2]] };
    const r = reachPath(offers, 4, 1, [2, 2]);
    assert(JSON.stringify(r.path) === '[[2,2],[3,2],[4,2],[4,1]]' && r.feet === 15, JSON.stringify(r));
    assert(reachPath(offers, 9, 9, [2, 2]) === null, 'out of reach: no route');
    assert(reachPath({}, 3, 2) === null, 'no reach sent');
  });
  test('play: the reach outline is the border between reachable and other squares', () => {
    assert(reachOutline([[1, 1, 5, 0, 0]]).length === 4, 'one square: its four sides');
    const two = reachOutline([[1, 1, 5, 0, 0], [2, 1, 5, 0, 0]]);
    assert(two.length === 6 && !two.some(e => e[0] === 2 && e[2] === 2 && e[1] === 1 && e[3] === 2), 'the shared side is not a border');
    assert(reachOutline(undefined).length === 0, 'nothing');
  });
  return results;
}

// MAP-LAYERS-01 (GM 2026-10-24): spell zones, Invisibility per viewer, riders on their mounts (the engine decides;
// these only arrange what it sent: snapshot layers, party_sight, offers.mount)
export function runLayers() {
  const results = [];
  const test = (name, fn) => { try { fn(); results.push([name, true, '']); } catch (e) { results.push([name, false, e.message]); } };
  const LAYERS = { zones: [{ n: 1, spell: 'Fog Cloud', owner: 'i', owner_name: 'Hero 4', origin: [18, 7], radius_ft: 20, appearance: 'smoke', layer: 'air', darkness: false, rounds_left: 600 },
    { n: 2, spell: 'Darkness', owner: 'i', owner_name: 'Hero 4', origin: [5, 5], radius_ft: 15, appearance: 'darkness', layer: 'air', darkness: true, rounds_left: 99 }],
    mounts: [{ rider: 'c', mount: 'h', mode: 'controlled' }] };
  test('layers: each zone is a lasting circle effect on the air layer; Darkness has its own look', () => {
    const fx = layerEffects(LAYERS);
    assert(fx.length === 2 && fx[0].shape === 'circle' && fx[0].lasting && fx[0].layer === 'air' && fx[0].radius_ft === 20, JSON.stringify(fx[0]));
    assert(fx[1].darkness && fx[1].appearance === 'darkness', 'darkness');
    assert(layerEffects(null).length === 0, 'no layers: nothing');
  });
  test('layers: an Invisible creature is faded with a dashed outline for the GM, faded for a player', () => {
    const c = { id: 'g', conditions: ['Invisible'] };
    assert(invisibleLook(c, 'gm').dashed && invisibleLook(c, 'gm').opacity < .5, 'GM outline');
    assert(!invisibleLook(c, 'player').dashed && invisibleLook(c, 'player').opacity < .6, 'player faded');
    assert(invisibleLook({ id: 'x', conditions: [] }, 'gm') === null, 'visible: untouched');
  });
  test('layers: mounts are drawn before their riders, riders smaller and raised; each keeps its own id', () => {
    const cs = [{ id: 'c', name: 'Hero 1', space_ft: 5, x: 11, y: 10 }, { id: 'g', name: 'Goblin', space_ft: 5 }, { id: 'h', name: 'Horse', space_ft: 10, x: 11.5, y: 10.5 }];
    const out = layerOrder(cs, LAYERS);
    assert(out.map(c => c.id).join() === 'h,g,c', out.map(c => c.id).join());
    assert(out[2].riding === 'h' && out[2].rider_scale < 1 && out[2].rider_lift >= 1, JSON.stringify(out[2]));
    assert(out[2].x === 11.5 && out[2].square.join() === '11,10', 'drawn on the mount, its own square kept');
    assert(!out[0].riding && cs[0].riding === undefined, 'the snapshot itself is untouched');
  });
  test('layers: the Mount line: Mount buttons with the reason, or Dismount and the three mount actions', () => {
    const off = { mount: { riding: null, half_ft: 15, candidates: [{ target: 'h', name: 'Horse', ready: true, mode: 'controlled' },
      { target: 's', name: 'Hero 2', ready: false, why: 'Hero 2 is Medium and Hero 1 is Medium: a mount must be at least one size larger than its rider.' }] } };
    const b = mountButtons(off);
    assert(b.length === 2 && b[0].cmd.op === 'mount' && b[0].cmd.target === 'h' && b[0].label === 'Mount Horse (15 ft)', JSON.stringify(b[0]));
    assert(!b[1].ready && b[1].why.includes('one size larger'), 'greyed with the reason');
    const riding = { mount: { riding: 'h', mode: 'controlled', half_ft: 15, own_movement: 15, dismount: { ready: true }, actions: [
      { action: 'dash', ready: true }, { action: 'disengage', ready: true }, { action: 'dodge', ready: false, why: 'Horse already took its action this turn (dash).' }] } };
    const r = mountButtons(riding);
    assert(r.map(x => x.cmd.op).join() === 'dismount,mount_action,mount_action,mount_action' && r[3].why.includes('already'), JSON.stringify(r));
    assert(mountText(riding, () => 'Horse').startsWith('Riding Horse (controlled'), mountText(riding, () => 'Horse'));
    assert(mountButtons({}).length === 0 && mountText({}) === '', 'no mount offers: nothing');
  });
  return results;
}

export function runSpells() {
  const results = [];
  const test = (name, fn) => { try { fn(); results.push([name, true, '']); } catch (e) { results.push([name, false, e.message]); } };
  const offers = { side: 'friend', spells: [
    { name: 'Burning Hands', level: 1, time: 'action', shape: 'cone', length_ft: 15, appearance: 'fire', range_ft: 0, ready: true },
    { name: 'Healing Word', level: 1, time: 'bonus', shape: 'creature', range_ft: 60, appearance: 'healing', ready: true, targets: ['pc2'], refused: { g1: 'Not an ally' } },
    { name: 'Bless', level: 1, time: 'action', shape: 'creatures', max_targets: 3, range_ft: 30, appearance: 'radiant', concentration: true, ready: false, why: 'action used' }] };
  test('spells: cards read like a spell list; slots and keys', () => {
    assert(spellCardText(offers.spells[0]) === 'Burning Hands · level 1 · Action · 15-ft Cone', spellCardText(offers.spells[0]));
    assert(spellCardText(offers.spells[2]) === 'Bless · level 1 · Action · up to 3 creatures · range 30 ft · Concentration', spellCardText(offers.spells[2]));
    assert(slotsText([2, 1]) === 'Spell slots: level 1 ●● · level 2 ●', slotsText([2, 1]));
    assert(spellOf(offers, SPELL_KEY + 'Healing Word').name === 'Healing Word' && spellOf(offers, 'weapon') === null, 'keys');
  });
  test('spells: a held creature spell lights its legal targets with the simulator\'s reasons', () => {
    const hw = offers.spells[1];
    assert(spellLook(hw, { id: 'pc2', side: 'friend' }, offers).cls === 'legal-ally', 'ally');
    assert(spellLook(hw, { id: 'g1', side: 'foe' }, offers).reason === 'Not an ally', 'refused with the reason');
  });
  test('spells: aiming previews the cone from the caster and the sphere on the square; casts become effects', () => {
    const cone = aimPreview(offers.spells[0], [2, 4], [5, 4]);
    assert(cone.shape === 'cone' && cone.angle_deg === 0 && cone.length_ft === 15 && cone.preview, JSON.stringify(cone));
    assert(aimPreview(offers.spells[0], [2, 4], [2, 4]) === null, 'no direction');
    const sphere = aimPreview({ shape: 'sphere', radius_ft: 20, appearance: 'fire' }, [0, 0], [10, 4]);
    assert(sphere.shape === 'circle' && sphere.radius_ft === 20 && sphere.origin[0] === 10, JSON.stringify(sphere));
    const fxc = effectFromCast({ shape: 'circle', appearance: 'fire', origin: [10, 4], radius_ft: 20, targets: ['g'] });
    assert(fxc.shape === 'circle' && fxc.radius_ft === 20 && !('targets' in fxc), 'effect');
    const auras = auraEffects([{ caster: 'pc2', radius_ft: 15, appearance: 'radiant' }], [{ id: 'pc2', x: 3, y: 5 }]);
    assert(auras.length === 1 && auras[0].origin[0] === 3 && auras[0].aura, 'aura follows the caster');
  });
  // SPELL-CASTER-01: the general caster's cards (sim/live_general.py) use the same buttons
  test('spells: general spells read their Line and Cube, preview them, and ask their choice and slot', () => {
    const bolt = { name: 'Lightning Bolt', level: 3, time: 'action', shape: 'line', length_ft: 100, width_ft: 5, range_ft: 0, general: true };
    assert(spellCardText(bolt) === 'Lightning Bolt · level 3 · Action · 100-ft Line', spellCardText(bolt));
    const line = aimPreview(bolt, [2, 4], [2, 9]);
    assert(line.shape === 'line' && line.angle_deg === 90 && line.length_ft === 100, JSON.stringify(line));
    const ff = { name: 'Faerie Fire', shape: 'cube', size_ft: 20, appearance: 'arcane' };
    const box = aimPreview(ff, [0, 0], [4, 4]);
    assert(box.shape === 'rectangle' && box.origin[0] === 2.5 && box.origin[1] === 4.5 && box.length_ft === 20, JSON.stringify(box));
    const wave = aimPreview({ shape: 'cube_self', size_ft: 15 }, [2, 4], [3, 4]);
    assert(wave.origin[0] === 2.5 && wave.origin[1] === 4, JSON.stringify(wave));
    assert(aimPreview({ shape: 'cube_self', size_ft: 15 }, [2, 4], [2, 4]) === null, 'no side');
    const mm = { name: 'Magic Missile', level: 1, shape: 'creatures', strikes: 3, general: true, upcast: true, slots_ok: [1, 3] };
    assert(spellCardText(mm).includes('3 at one or several creatures'), spellCardText(mm));
    const inv = { name: 'Invisibility', level: 2, time: 'action', shape: 'creatures', max_targets: 2, range_ft: 5, touch: true, concentration: true };
    assert(spellCardText(inv) === 'Invisibility · level 2 · Action · up to 2 creatures · Touch · Concentration', spellCardText(inv));   // INVISIBILITY-01
    assert(JSON.stringify(spellExtras(mm, () => '3')) === '{"slot":3}', 'a higher slot');
    assert(JSON.stringify(spellExtras(mm, () => '1')) === '{}', 'the lowest: the simulator picks it');
    assert(spellExtras(mm, () => null) === null, 'cancelled');
    const orb = { name: 'Chromatic Orb', level: 1, general: true, choices: ['acid', 'cold', 'fire'], slots_ok: [1] };
    assert(spellExtras(orb, () => 'Fire').choice === 'fire', 'the choice');
    assert(JSON.stringify(spellExtras({ name: 'Bless' }, () => 'x')) === '{}', 'hand-written spells ask nothing');
  });
  // GM 2026-10-22: "the phone display doesn't shows effects"
  test('spells: every screen draws each cast effect from the live state once, whoever cast it', () => {
    const seen = new Set(), bh = { n: 1, caster: 'pc1', spell: 'Burning Hands', effect: { shape: 'cone', origin: [2, 4] } };
    const snap = { fight_id: 'f1', effects: [bh] };
    assert(newCastEffects(snap, seen).map(e => e.spell).join() === 'Burning Hands', 'new: drawn');
    assert(newCastEffects(snap, seen).length === 0, 'the next poll: not again');
    assert(newCastEffects({ ...snap, effects: [bh, { ...bh, n: 2, spell: 'Sleep' }] }, seen).map(e => e.n).join() === '2', 'only the new one');
    assert(newCastEffects({ fight_id: 'f2', effects: [bh] }, seen).length === 1, 'a new fight counts from 1 again');
    assert(newCastEffects({ fight_id: 'f2' }, seen).length === 0 && newCastEffects(null, seen).length === 0, 'none');
  });
  test('live: the GM console follows a player\'s turn on a phone, redrawing only when the fight moved', () => {
    const a = { fight_id: 'f', revision: 3, waiting: 'pc1', log_n: 10, done: false, round: 1 };
    assert(!liveMoved(a, { ...a, state: {} }), 'the same');
    for (const k of ['revision', 'log_n', 'waiting', 'round']) assert(liveMoved(a, { ...a, [k]: 99 }), k);
    assert(liveMoved(a, { ...a, done: true }) && liveMoved(null, a), 'done; first');
  });
  return results;
}

// LIVE-PLAY-01 slice 3 (GM 2026-10-20): Dash, Disengage, Dodge (a Rogue's Cunning Action as a Bonus Action) and doors.
export function runActions() {
  const results = [];
  const test = (name, fn) => { try { fn(); results.push([name, true, '']); } catch (e) { results.push([name, false, e.message]); } };
  const rogue = { actions: [{ op: 'dash', ready: true, bonus: true }, { op: 'disengage', ready: false, why: "Hero 3's action is used this turn.", bonus: true },
    { op: 'dodge', ready: true, bonus: false }],
    doors: [{ id: 'hall door west', open: true, near: true, ready: true, mid: [9.5, 11] }, { id: 'north room door', open: false, near: false, ready: false, mid: [21.5, 7] },
      { id: 'vault', open: false, near: true, locked: true, ready: false, mid: [3, 3.5] }], interaction_used: false };
  test('actions: one button each, plus the Bonus Action ones a Rogue has; refused ones say why', () => {
    const b = actionButtons(rogue);
    assert(b.map(x => x.label).join() === 'Dash,Disengage,Dodge,Dash (Bonus Action),Disengage (Bonus Action)', b.map(x => x.label).join());
    assert(b[0].ready && JSON.stringify(b[0].cmd) === '{"op":"dash"}', 'dash');
    assert(!b[1].ready && b[1].why === "Hero 3's action is used this turn.", 'disengage refused with why');
    assert(JSON.stringify(b[3].cmd) === '{"op":"dash","bonus":true}' && b[3].ready, 'bonus dash');
    assert(actionButtons({ actions: [{ op: 'dash', ready: true, bonus: false }] }).length === 1, 'no Cunning Action: no bonus buttons');
  });
  test('doors: only the doors beside you, open ones to close, locked ones refused', () => {
    const d = doorButtons(rogue);
    assert(d.map(x => x.label).join() === 'Close the hall door west,Open the vault', d.map(x => x.label).join());
    assert(d[0].ready && JSON.stringify(d[0].cmd) === '{"op":"door","door":"hall door west"}', 'close');
    assert(!d[1].ready && /locked/.test(d[1].why), 'locked');
    assert(doorButtons({ ...rogue, interaction_used: true }).every(x => !x.ready || x.why), 'one interaction a turn');
    assert(!doorButtons({ ...rogue, interaction_used: true })[0].ready && /object interaction/.test(doorButtons({ ...rogue, interaction_used: true })[0].why), 'used');
  });
  // SPELL-OBJECTS-01 (GM 2026-10-27): spells at doors
  test('doors: a held spell or attack cantrip lists the doors it may go at, and why not the others', () => {
    const o = { attacks: [{ key: 'ranged', name: 'Fire Bolt', spell: 'Fire Bolt', targets: [], doors: ['vault'], door_refused: { 'far door': "The far door is 130 ft away: out of Fire Bolt's range (120 ft)." } }],
      spells: [{ name: 'Knock', shape: 'door', doors: [], door_refused: { vault: 'The vault is not locked: Knock has nothing to open.' } },
        { name: 'Guiding Bolt', shape: 'creature', door_refused: { vault: 'Guiding Bolt targets a creature, not a door.' } }, { name: 'Bless', shape: 'creatures' }] };
    const a = doorAim(o, 'ranged');
    assert(a.spell === 'Fire Bolt' && a.ok.join() === 'vault' && /out of Fire Bolt's range/.test(a.refused['far door']), JSON.stringify(a));
    assert(/not locked/.test(doorAim(o, SPELL_KEY + 'Knock').refused.vault), 'Knock refused in words');
    assert(/targets a creature, not a door/.test(doorAim(o, SPELL_KEY + 'Guiding Bolt').refused.vault), 'creature-only spell');
    assert(doorAim(o, SPELL_KEY + 'Bless') === null && doorAim(o, 'weapon') === null, 'no door list: no door aim');
    const far = { attacks: [{ ...o.attacks[0], distant_doors: ['vault', 'far door'] }] };       // step 5: Distant Spell armed
    const d = doorAim(far, 'ranged', ['Distant Spell']);
    assert(d.ok.join() === 'vault,far door' && !d.refused['far door'], JSON.stringify(d));
    assert(doorAim(far, 'ranged').ok.join() === 'vault', 'not armed: the plain range');
    const props = { attacks: [{ key: 'ranged', name: 'Fire Bolt', targets: [], props: ['crate at (1, 3)'], prop_refused: { 'statue at (9, 9)': 'A wall blocks the line to the statue at (9, 9).' } }] };
    const pa = doorAim(props, 'ranged', [], 'props');                                 // step 6: props
    assert(pa.ok.join() === 'crate at (1, 3)' && /wall blocks/.test(pa.refused['statue at (9, 9)']) && doorAim(props, 'ranged') === null, JSON.stringify(pa));
  });
  test("doors: a door's AC, Hit Points and fire in words; a broken door can't be closed; putting out a fire carries its door", () => {
    assert(doorText('vault', { material: 'wood', ac: 15, hp: 12, max_hp: 18, burning: true }) === 'The vault: wood, AC 15, 12 of 18 Hit Points, burning (1d4 Fire each round)', 'text');
    assert(/broken, an open doorway/.test(doorText('vault', { broken: true })), 'broken');
    assert(doorText('vault', { material: 'iron', ac: 19, hp: 18, max_hp: 18, locked: true, arcane_lock: true, hot: true }) ===
      'The vault: iron, AC 19, 18 of 18 Hit Points, held by Arcane Lock, red-hot (Heat Metal)', 'Arcane Lock and Heat Metal');
    const d = doorButtons({ doors: [{ id: 'vault', open: true, near: true, ready: false, broken: true }] });
    assert(!d[0].ready && /broken/.test(d[0].why), JSON.stringify(d));
    const b = actionButtons({ actions: [{ op: 'douse_door', door: 'vault', label: 'Put out the fire on the vault', ready: true }] });
    assert(b[0].label === 'Put out the fire on the vault' && JSON.stringify(b[0].cmd) === '{"op":"douse_door","door":"vault"}', JSON.stringify(b));
  });
  // slice 4 (GM 2026-10-20): Help, Hide, Search, Ready, class Bonus Actions, Grapple and Shove
  const fighter = { actor: 'pc1', side: 'friend', actions: [
    { op: 'help', ready: true, targets: ['g1'], refused: { g4: 'Goblin 4 is 40 ft away: Help needs a creature within 5 ft.' } },
    { op: 'hide', ready: false, why: 'Goblin 1 can see Hero 1: there is no cover to hide behind.' },
    { op: 'search', ready: true }, { op: 'ready', ready: true, weapons: [{ key: 'weapon', name: 'Greatsword' }, { key: 'ranged', name: 'Javelin' }] },
    { op: 'second_wind', ready: true, time: 'bonus', uses: 2 }, { op: 'grapple', ready: true, targets: ['g1'], refused: {} },
    { op: 'shove', ready: true, targets: [], refused: { g1: 'No room' } }] };
  test('actions slice 4: buttons for every action; Ready per weapon; Shove twice; target ones pick a creature', () => {
    const b = actionButtons(fighter), byLabel = Object.fromEntries(b.map(x => [x.label, x]));
    assert(b.map(x => x.label).join() === 'Help,Hide,Search,Ready: Greatsword,Ready: Javelin,Second Wind (Bonus Action),Grapple,Shove (Prone),Shove (Push)', b.map(x => x.label).join());
    assert(byLabel.Help.pick === ACT_KEY + 'help' && !byLabel.Help.cmd, 'Help picks a creature');
    assert(JSON.stringify(byLabel['Ready: Javelin'].cmd) === '{"op":"ready","weapon":"ranged"}', 'Ready with the javelin');
    assert(JSON.stringify(byLabel.Search.cmd) === '{"op":"search"}' && JSON.stringify(byLabel['Second Wind (Bonus Action)'].cmd) === '{"op":"second_wind"}', 'instant ones');
    assert(!byLabel.Hide.ready && /can see/.test(byLabel.Hide.why), 'Hide refused with why');
    assert(byLabel['Shove (Push)'].pick === ACT_KEY + 'shove:push' && !byLabel['Shove (Push)'].ready && /No creature/.test(byLabel['Shove (Push)'].why), 'no one to shove');
  });
  test('actions slice 4: a picked action lights its legal creatures and explains the others', () => {
    const me = { id: 'pc1', side: 'friend', name: 'Hero 1' };
    assert(actLook(fighter, ACT_KEY + 'help', { id: 'g1', side: 'foe', name: 'Goblin 1' }).cls === 'legal-foe', 'legal');
    const no = actLook(fighter, ACT_KEY + 'help', { id: 'g4', side: 'foe', name: 'Goblin 4' });
    assert(no.cls === 'refused' && /40 ft/.test(no.reason), 'refused with why');
    assert(actLook(fighter, ACT_KEY + 'help', me).cls === 'self', 'self');
    assert(actLook({ actor: 'pc1', side: 'friend', actions: [{ op: 'lay_on_hands', targets: ['pc1', 'pc2'] }] }, ACT_KEY + 'lay_on_hands', me).cls === 'legal-ally', 'Lay On Hands on herself');
  });
  return results;
}

// VIEW-01 (GM 2026-10-20): fog of war from the simulator's own sight, a player view, the doors as they are now.
export function runFog() {
  const results = [];
  const test = (name, fn) => { try { fn(); results.push([name, true, '']); } catch (e) { results.push([name, false, e.message]); } };
  const sight = { squares: [[1, 1], [2, 1]], creatures: ['g1'] };
  test('fog: seen now is clear, seen before is dim, never seen is dark', () => {
    const explored = mergeExplored(['0,0', '1,1'], sight);
    assert(explored.length === 3 && explored.includes('2,1') && explored.includes('0,0'), 'explored grows, never shrinks');
    const f = fogCells(3, 2, sight, explored);
    const key = p => p.join();
    assert(f.dim.map(key).join('|') === '0,0', 'dim: explored, not seen now');
    assert(f.hidden.length === 3 && !f.hidden.map(key).includes('1,1') && !f.hidden.map(key).includes('0,0'), 'hidden: the rest');
    assert(fogCells(3, 2, null, []).hidden.length === 0, 'no sight reported: no fog drawn');
  });
  test('player view: only the creatures the party sees; the party always', () => {
    const cs = [{ id: 'pc1', pc: true }, { id: 'g1', side: 'foe' }, { id: 'g2', side: 'foe' }];
    assert(playerCombatants(cs, sight).map(c => c.id).join() === 'pc1,g1', 'g2 unseen');
    assert(playerCombatants(cs, null).length === 3, 'no sight reported: everyone');
  });
  test('doors: as they are now, not as the map began', () => {
    const map = { walls: [{ id: 'd1', door: true, open: true }, { id: 'd2', door: true, open: false }, { id: 'w', open: false }] };
    const m = withDoors(map, ['d2']);
    assert(!m.walls[0].open && m.walls[1].open && !m.walls[2].open && map.walls[0].open, 'd1 closed, d2 open, the map untouched');
    assert(withDoors(map, undefined) === map, 'no door list: as it was');
  });
  return results;
}

// VIEW-01 (GM 2026-10-20): notes pinned to the map; the player view shows only those marked for the players on squares
// the party has explored.
export function runNotes() {
  const results = [];
  const test = (name, fn) => { try { fn(); results.push([name, true, '']); } catch (e) { results.push([name, false, e.message]); } };
  const notes = [{ id: 'a', x: 1, y: 1, text: 'GM only', show_players: false }, { id: 'b', x: 2, y: 1, text: 'A carved hand', show_players: true },
    { id: 'c', x: 9, y: 9, text: 'Not yet found', show_players: true }];
  test('notes: the GM sees every pin; the players only theirs, once that square is explored', () => {
    assert(notePins(notes, ['2,1', '1,1'], false).length === 3, 'GM: all');
    assert(notePins(notes, ['2,1', '1,1'], true).map(n => n.id).join() === 'b', 'players: b only (c not explored, a GM only)');
  });
  test('notes: add, change and delete; one note per square', () => {
    let n = upsertNote([], { x: 3, y: 4, text: 'first' });
    assert(n.length === 1 && n[0].id && noteAt(n, 3, 4).text === 'first', 'added with an id');
    n = upsertNote(n, { ...noteAt(n, 3, 4), text: 'second', show_players: true });
    assert(n.length === 1 && noteAt(n, 3, 4).text === 'second' && noteAt(n, 3, 4).show_players, 'changed in place');
    assert(deleteNote(n, n[0].id).length === 0 && noteAt([], 3, 4) === null, 'deleted');
  });
  return results;
}

// VIEW-02 (GM 2026-10-20: "I want the actual map with full functionality be able to pop out and the tokens fully
// functioning and draggable. The commands will still be on the main console."): the pop-out and the main console are two
// windows on ONE live session (the service); each tells the other what it changed.
function fakeBus() {
  const ends = [];
  return () => {
    const end = { onmessage: null, postMessage: m => { for (const o of ends) if (o !== end && o.onmessage) o.onmessage({ data: structuredClone(m) }); }, close() {} };
    ends.push(end);
    return end;
  };
}
function fakeService() {
  const s = { revision: 1, at: [2, 2] };
  const reply = body => ({ ok: true, status: 200, json: async () => body });
  s.fetch = async (path, init) => {
    if (!init) return reply({ ok: true, token: 'T' });
    const b = JSON.parse(init.body), live = () => ({ revision: s.revision, waiting: 'pc1', state: { combatants: [{ id: 'pc1', x: s.at[0], y: s.at[1] }] } });
    if (path === '/api/live/state') return reply({ ok: true, live: live() });
    if (path === '/api/live/act') {
      if (b.revision !== s.revision) return { ok: false, status: 409, json: async () => ({ ok: false, refused: 'Stale: the fight has moved on.', live: live() }) };
      s.at = [b.x, b.y]; s.revision++;
      return reply({ ok: true, moved_ft: 5, live: live() });
    }
    return reply({ ok: true });
  };
  return s;
}

export async function runPopout() {
  const results = [];
  const test = async (name, fn) => { try { await fn(); results.push([name, true, '']); } catch (e) { results.push([name, false, e.message]); } };

  await test('pop-out: a token dragged in the pop-out moves through the live session and the main console updates', async () => {
    const service = fakeService(), bus = fakeBus();
    const mainPort = createLivePort({ fetch: service.fetch }), popPort = createLivePort({ fetch: service.fetch });
    await mainPort.hello(); await popPort.hello();
    let mainSnap = (await mainPort.state(0)).live;
    const refreshed = [];
    liveSync({ channel: bus(), refresh: async () => { mainSnap = (await mainPort.state(0)).live; refreshed.push(mainSnap.revision); } });
    const pop = liveSync({ channel: bus(), refresh: () => {} });
    const out = await popPort.act({ op: 'move', x: 3, y: 2, revision: 1 });     // the drag's drop, as the main page sends it
    assert(out.ok && out.live.state.combatants[0].x === 3, 'moved by the one session');
    pop.changed();
    await new Promise(r => setTimeout(r, 0));
    assert(refreshed.join() === '2' && mainSnap.state.combatants[0].x === 3, 'the main console followed: ' + JSON.stringify(mainSnap));
    const stale = await mainPort.act({ op: 'move', x: 5, y: 5, revision: 1 });  // a window behind the other is refused, not doubled
    assert(stale.status === 409 && service.at.join() === '3,2', 'one session, one revision');
  });

  await test("pop-out: the main console's held attack or spell shows in the pop-out; a pick there is used and handed back", () => {
    const bus = fakeBus(), seen = [], used = [];
    const main = liveSync({ channel: bus(), refresh: () => {}, onUsed: () => used.push('cleared') });
    const pop = liveSync({ channel: bus(), refresh: () => {}, onSelect: s => seen.push(s) });
    main.select({ held: 'weapon', casting: null });
    main.select({ held: 'weapon', casting: null });                               // unchanged: not sent again
    assert(seen.length === 1 && seen[0].held === 'weapon', JSON.stringify(seen));
    pop.used();
    assert(used.join() === 'cleared', 'the main console lets go of the card');
    let echoed = 0;
    const solo = liveSync({ channel: { postMessage() { echoed++; }, onmessage: null, close() {} }, refresh: () => { throw new Error('own message'); } });
    solo.changed();
    assert(echoed === 1 && SYNC_CHANNEL === 'mythastria-live', 'one channel name');
  });

  await test('pop-out: what a pick there did is shown on the main console', () => {
    const bus = fakeBus(), shown = [];
    liveSync({ channel: bus(), refresh: () => {}, onResult: (text, cls) => shown.push([text, cls]) });
    liveSync({ channel: bus(), refresh: () => {} }).result('Hit. Hero 1 deals 9 damage.', 'done');
    assert(shown.length === 1 && shown[0][0].startsWith('Hit.') && shown[0][1] === 'done', JSON.stringify(shown));
  });
  return results;
}
