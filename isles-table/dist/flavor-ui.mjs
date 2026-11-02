import { asset } from './server.mjs';   // PLAYER-SITE-01: pictures from the GM's PC
import { FLAVOR_KEY, EVERY_MAP, ROLES, emptyFlavor, overlayPending, loadFlavor, saveFlavor, flavorKey, flavorOf, flavorWhere, setFlavor, flavorLabel, actorFlavorKey, pictureMark, paintUntil, paintLasts, eraseMap } from './flavor.mjs';
import { palettes } from './effects.mjs';

// The Flavor dialog (Play live, the GM's console): a creature's shown name, picture, role and footnote, and an attack's
// or spell's name, description and visuals. Kept in this browser, shared with the players' window on the same PC.
// painter (flavor-paint.mjs paintPicture): the paint box for a mask on a copy of the creature's picture.
// remote (FLAVOR-01, GM 2026-10-21: Flavor for players on their own devices): Mythastria keeps the table's Flavor
// ({ load(rev), save(flavor, rev) }, Mythastria tools/table_flavor.py); this browser keeps a copy for its pop-out.
// A players' page loads, and asks with remote.ask(actor, record). Without remote, this browser alone (as before).
// player (PLAYER-FLAVOR-01, the Player Client Plan, item 7): the same dialog on a player's screen, for the looks of the
// creatures they control. Asking the GM replaces saving; the look shows on this screen, marked as pending, until the GM
// answers (remote.rule on the GM's console, which holds the requests in `asks`). A refused look just drops away.
export function mountFlavor({ document: doc = globalThis.document, button, context, changed, storage = globalThis.localStorage, listen = globalThis.addEventListener?.bind(globalThis), painter = null, ask = text => globalThis.confirm?.(text) ?? true, remote = null, player = false }) {
  let state = loadFlavor(storage), subjects = [], editing = null, paintNow = {}, rev = null, syncing = false;
  let mine = { actors: [], pending: {} }, asks = [], asksRev = null;
  const make = (tag, text) => { const e = doc.createElement(tag); if (text !== undefined) e.textContent = text; return e; };
  const dialog = make('dialog'); dialog.id = 'flavor-dialog'; dialog.setAttribute('aria-labelledby', 'flavor-title');
  const title = make('h2', 'Flavor is free!'); title.id = 'flavor-title';
  const help = make('p', player ? 'Change how your character, pet or familiar looks: a new name or picture, paint, how its standee stands in the 3D view, a footnote. The rules stay the same.' :
    'Change the look and the story: a pet, familiar or mount, a new picture, how its standee stands in the 3D view, a footnote. The rules stay the same.');
  const local = make('p', player ? 'The GM approves each change. Until then your new look shows on your screen, marked as pending. Once approved, everyone at the table sees it.' :
    'Kept in this browser on this PC (also after a restart) and shown in the players’ window. The simulator and the log keep the rules names. Attacks and spells come from the sheet of the character whose turn it is.'); local.className = 'note';
  const actor = make('select'), subject = make('select'), name = make('input'), description = make('textarea'), appearance = make('select'), art = make('select'), role = make('select');
  const preview = make('img'), share = make('input'), everywhere = make('input');
  share.type = everywhere.type = 'checkbox';
  preview.className = 'flavor-art'; preview.alt = ''; preview.hidden = true;
  name.maxLength = 80; description.maxLength = 1000; description.rows = 4;
  description.setAttribute('aria-label', 'Flavor footnote');
  const field = (text, control) => { const label = make('label', text); label.append(control); return label; };
  const tick = (control, text) => { const label = make('label'); label.className = 'flavor-tick'; label.append(control, make('span', text)); return label; };
  const paletteField = field('Spell visuals', appearance), artField = field('Creature artwork', art), roleField = field('Role', role);
  const descText = make('span', 'Flavor footnote'), descField = make('label'), shareField = tick(share, 'Players may read the footnote (players’ window)');
  descField.append(descText, description);
  const everywhereField = tick(everywhere, 'Keep on every map (a pet, familiar or mount that travels with the party)');
  // GM 2026-10-23 ("Keep the flat standees. Include them to be edited in flavor"): the creature's standee in the 3D view
  const onBase = make('input'), trueHeight = make('input');
  onBase.type = trueHeight.type = 'checkbox';
  const standeeField = make('div'); standeeField.className = 'flavor-standee';
  standeeField.append(tick(onBase, 'Stand on a round base (3D view)'), tick(trueHeight, 'True height (3D view): as tall as the picture, not 40% taller'));
  // a rider on a Large or bigger creature (a camel, a horse ...): a picture only; the creature keeps its own stat block
  const riderSel = make('select'), riderField = field('Rider (a picture on its back; Large or bigger creatures)', riderSel);
  standeeField.append(riderField);
  // the paint: a mask on a copy of the picture (GM 2026-10-21), for this fight only unless the tick is taken off
  const paintOpen = make('button', 'Paint a mask…'), paintOff = make('button', 'Remove paint'), limited = make('input'), limitText = make('span'), paintNote = make('span');
  paintOpen.type = paintOff.type = 'button'; paintOff.className = 'quiet'; limited.type = 'checkbox'; limited.checked = true; paintNote.className = 'note';
  const paintField = make('div'); paintField.className = 'flavor-paint';
  const limitField = make('label'); limitField.className = 'flavor-tick'; limitField.append(limited, limitText);
  paintField.append(paintOpen, paintOff, limitField, paintNote);
  if (!painter) paintField.hidden = true;
  const rules = make('p'), message = make('p'); rules.className = 'flavor-rules'; message.setAttribute('role', 'status');
  const actions = make('div'); actions.className = 'flavor-actions';
  // erase and redo (GM 2026-10-21): one subject back to the original, or the whole map's Flavor
  const save = make('button', 'Save Flavor'), reset = make('button', 'Erase this Flavor'), eraseAll = make('button', 'Erase all Flavor on this map…'), close = make('button', 'Close');
  for (const b of [save, reset, eraseAll, close]) b.type = 'button';
  reset.title = 'Back to the original name, picture and words for this subject, here and on every map; then make it again'; eraseAll.className = 'quiet';
  actions.append(save, reset, eraseAll, close);
  const subjectField = field('Subject', subject);
  dialog.append(title, help, local, field('Character / creature', actor), subjectField, rules, field('Display name', name), roleField, descField, shareField,
    paletteField, artField, preview, standeeField, paintField, everywhereField, message, actions);
  if (player) {
    subjectField.hidden = everywhereField.hidden = limitField.hidden = eraseAll.hidden = true;
    save.textContent = 'Ask the GM'; reset.textContent = 'Ask for the original look';
    reset.title = 'Ask the GM to put back the original name, picture and words';
  }
  doc.body.append(dialog);
  const option = (text, value) => { const e = make('option', text); e.value = value; return e; };
  const current = () => { const c = editing ?? context(), a = c.actors?.find(a => a.id === actor.value); return { c, a, s: subjects[Number(subject.value)] }; };
  // the picture the paint goes on: the chosen artwork, else the creature's own (its sheet photo or catalog picture)
  function baseNow() {
    const { c, a } = current(), t = (c.registry ?? []).find(t => t.id === art.value);
    return t ? t.path : a ? c.basePicture?.(a.id) ?? '' : '';
  }
  const paintShows = c => paintNow.paint && paintNow.paint_on === pictureMark(baseNow()) && paintLasts(paintNow, c);
  function showArt() {
    const { c } = current(), t = (c.registry ?? []).find(t => t.id === art.value), painted = paintShows(c);
    preview.hidden = !(painted || t) || artField.hidden; if (painted) preview.src = asset(paintNow.paint); else if (t) preview.src = asset(t.path);
    paintOff.hidden = !paintNow.paint;
    limitText.textContent = c.adventure ? 'For this adventure only (it comes off when the adventure ends)' : 'For this fight only (not in an adventure)';
    paintNote.textContent = !paintNow.paint ? '' : painted ? (!paintNow.paint_until ? 'Painted, kept until removed.' : c.adventure ? 'Painted for this adventure.' : 'Painted for this fight.') :
      !paintLasts(paintNow, c) ? (paintNow.paint_until.startsWith('adventure:') ? 'The paint was for another adventure.' : 'The paint was for an earlier fight.') : 'The paint was on another picture: paint again to use it.';
  }
  function showRecord() {
    const { c, a, s } = current(); if (!a || !s) return;
    const record = flavorOf(state, c.scope, actorFlavorKey(a), s.kind, s.key), isActor = s.kind === 'actor';
    name.value = record.name || ''; name.placeholder = s.name; description.value = record.description || '';
    paletteField.hidden = s.kind !== 'spell'; artField.hidden = roleField.hidden = standeeField.hidden = !isActor; shareField.hidden = player || !isActor; paintField.hidden = !isActor || !painter;
    paintNow = isActor && record.paint ? { mask: record.mask, paint: record.paint, paint_on: record.paint_on, paint_until: record.paint_until } : {};
    limited.checked = !paintNow.paint || !!paintNow.paint_until;
    descText.textContent = isActor ? 'Flavor footnote (not the stat block)' : 'Description';
    appearance.replaceChildren(option('Original spell visuals', ''), ...Object.keys(palettes).map(k => option(k, k))); appearance.value = record.appearance || '';
    const pictures = [...(c.registry ?? [])].sort((x, y) => x.name.localeCompare(y.name));
    art.replaceChildren(option('Original artwork / sheet photo', ''), ...pictures.map(t => option(t.name, t.id))); art.value = record.token_id || '';
    role.replaceChildren(option('None', ''), ...Object.entries(ROLES).map(([k, v]) => option(v, k))); role.value = record.role || '';
    share.checked = !!record.share; onBase.checked = !!record.base; trueHeight.checked = !!record.true_height;
    riderSel.replaceChildren(option('No rider', ''), ...pictures.map(t => option(t.name, t.id))); riderSel.value = record.rider || '';
    riderField.hidden = !isActor || (a.space_ft ?? 5) < 10;
    everywhere.checked = flavorWhere(state, c.scope, actorFlavorKey(a), s.kind, s.key) === EVERY_MAP;
    rules.textContent = isActor ? `Rules: ${a.name} · ${a.space_ft ?? 5} ft footprint · HP, AC, size, speed and actions unchanged. A new picture is drawn at this size.` : `Rules: ${s.name}. Original damage, range, area, saves, targets, components, resource costs and timing apply.`;
    message.textContent = player && Object.hasOwn(mine.pending, actorFlavorKey(a)) ? 'Waiting for the GM: this look is pending.' : '';
    showArt();
  }
  function showSubjects() {
    const { c, a } = current(); if (!a) return;
    subjects = [{ kind: 'actor', key: '', name: a.name }];
    if (!player && c.offers?.actor === a.id) {
      subjects.push(...(c.offers.attacks ?? []).map(v => ({ kind: 'attack', key: v.key, name: v.name })), ...(c.offers.spells ?? []).map(v => ({ kind: 'spell', key: v.name, name: v.name })));
    }
    subject.replaceChildren(...subjects.map((s, i) => option(`${s.kind === 'actor' ? 'Creature' : s.kind === 'attack' ? 'Attack' : 'Spell'}: ${s.name}`, String(i)))); subject.value = '0';
    showRecord();
  }
  const choices = c => player ? c.actors.filter(a => mine.actors.includes(actorFlavorKey(a))) : c.actors;
  function showActors(pick) {
    const c = editing;
    actor.replaceChildren(...choices(c).map(a => option(flavorLabel(flavorOf(state, c.scope, actorFlavorKey(a), 'actor'), a.name), a.id)));
    actor.value = pick;
  }
  button.addEventListener('click', () => {
    const c = context(); if (!c.scope || !c.actors?.length || !choices(c).length) { changed(player ? 'Flavor opens once your character is on the map.' : 'Start a fight to choose a Flavor subject.'); return; }
    editing = c;
    showActors(player ? choices(c)[0].id : c.offers?.actor || c.actors[0].id); showSubjects(); dialog.showModal();
  });
  actor.addEventListener('change', showSubjects); subject.addEventListener('change', showRecord); art.addEventListener('change', showArt);
  // the service's answer becomes this page's Flavor (checked again, as from storage) and the browser's copy
  const adopt = out => {
    state = loadFlavor({ getItem: () => JSON.stringify(out.flavor) }); rev = out.rev; saveFlavor(state, storage);
    if (out.mine) { mine = out.mine; state = overlayPending(state, mine.pending); }   // this screen alone shows a pending look
  };
  // while a save is on its way the dialog waits (a slow link must not let the answer land on another subject)
  const controls = () => [actor, subject, name, description, appearance, art, role, share, onBase, trueHeight, riderSel, everywhere, limited, save, reset, eraseAll, paintOpen, paintOff];
  async function keepRemote(next) {
    controls().forEach(e => { e.disabled = true; }); message.textContent = 'Saving to Mythastria…';
    try { return await keepRemoteNow(next); } finally { controls().forEach(e => { e.disabled = false; }); }
  }
  async function keepRemoteNow(next) {
    if (rev === null) await sync();                               // not read from Mythastria yet
    if (rev === 'old') return keepLocal(next);                    // a Mythastria from before FLAVOR-01 (not restarted): this browser
    if (rev === null) return 'Could not reach Mythastria: Flavor not saved.';
    const out = await remote.save(next, rev).catch(() => null);
    if (out?.status === 409 && out.flavor) { adopt(out); changed(); return out.error; }   // changed on another screen
    if (!out?.ok) return 'Could not reach Mythastria: Flavor not saved.' + (out?.error ? ' ' + out.error : '');
    adopt(out); return '';
  }
  const keepLocal = next => { if (!saveFlavor(next, storage)) return 'Could not save Flavor in this browser. No changes applied.'; state = next; return ''; };
  // the service's Flavor, when it changed (the GM, the Adventure page's End); this browser's Flavor moves
  // into Mythastria once, the first time the service has none
  async function sync() {
    if (!remote?.load || syncing) return;
    syncing = true;
    try {
      const out = await remote.load(rev === 'old' ? null : rev, asksRev).catch(() => null);
      if (out?.status === 404) { rev = 'old'; return; }             // no Flavor route yet: keep Flavor in this browser
      if (out?.asks) { asks = out.asks; asksRev = out.asks_rev; changed(); }   // the GM: players' requests changed
      if (!out?.ok || out.unchanged || !out.flavor) return;
      if (remote.save && out.rev === 0 && !Object.keys(out.flavor.entries ?? {}).length && Object.keys(state.entries).length) {
        const moved = await remote.save(state, 0).catch(() => null);
        if (moved?.ok) { adopt(moved); changed(); }
        return;
      }
      adopt(out); changed();
    } finally { syncing = false; }
  }
  // PLAYER-FLAVOR-01: the look goes to the GM (the service keeps looks only, and sets who may read them)
  async function askGM(a, value, remove) {
    const who = actorFlavorKey(a), { paint_until, ...record } = remove ? {} : flavorOf(setFlavor(emptyFlavor(), EVERY_MAP, who, 'actor', '', value), EVERY_MAP, who, 'actor');
    controls().forEach(e => { e.disabled = true; }); message.textContent = 'Sending to the GM…';
    const out = await remote.ask(who, record).catch(() => null);
    controls().forEach(e => { e.disabled = false; });
    if (!out?.ok) { message.textContent = out?.error || 'Could not reach the GM: nothing was sent.'; return; }
    mine = { ...mine, pending: { ...mine.pending, [who]: record } }; state = overlayPending(state, { [who]: record });
    changed(); showActors(a.id); showRecord();
    message.textContent = 'Sent to the GM. This look is pending until the GM approves it.';
  }
  async function rule(who, approve) {                               // the GM's answer to a player's look
    const out = await remote.rule(who, approve).catch(() => null);
    if (out?.ok) { adopt(out); asksRev = null; await sync(); changed(); }
    return out;
  }
  async function commit(remove = false, note = '') {
    const { c, a, s } = current(); if (!a || !s) return;
    const latest = context();
    if (latest.scope !== c.scope || latest.fightId !== c.fightId || !latest.actors?.some(v => v.id === a.id && v.name === a.name)) { message.textContent = 'The fight changed. Close and reopen Flavor before saving.'; return; }
    const value = remove ? {} : { name: name.value, description: description.value, ...(s.kind === 'spell' ? { appearance: appearance.value } :
      s.kind === 'actor' ? { token_id: art.value, role: role.value, base: onBase.checked, true_height: trueHeight.checked, rider: riderField.hidden ? '' : riderSel.value, ...paintNow,
        ...(player ? {} : { share: share.checked, ...(paintNow.paint ? { paint_until: limited.checked ? paintUntil(c) : '' } : {}) }) } : {}) };
    const who = actorFlavorKey(a), target = everywhere.checked ? EVERY_MAP : c.scope;
    try {
      if (player) { await askGM(a, value, remove); return; }
      let next = setFlavor(state, target, who, s.kind, s.key, value);
      // Every map: this map's own copy would hide it here. Restore clears both.
      if (remove || target === EVERY_MAP) next = setFlavor(next, c.scope, who, s.kind, s.key, {});
      if (remove) next = setFlavor(next, EVERY_MAP, who, s.kind, s.key, {});
      const error = remote?.save ? await keepRemote(next) : keepLocal(next);
      if (error) { message.textContent = error; return; }
      changed(); showActors(a.id); showRecord();
      message.textContent = remove ? 'Flavor erased: the original is back. Make it again any time.' : (note || 'Flavor saved. Mechanics unchanged.') +
        (target !== EVERY_MAP && Object.hasOwn(state.entries, flavorKey(EVERY_MAP, who, s.kind, s.key)) ? ' This map only: the every-map Flavor still shows on other maps.' : '');
    } catch (e) { message.textContent = e.message; }
  }
  paintOpen.addEventListener('click', async () => {
    const { a } = current(); if (!a || !painter) return;
    const base = baseNow(), out = await painter({ document: doc, base, mask: paintNow.paint_on === pictureMark(base) ? paintNow.mask : '', name: name.value || a.name });
    if (!out) return;                                             // Cancel: nothing changes
    paintNow = out.paint ? { mask: out.mask, paint: out.paint, paint_on: pictureMark(base) } : {};
    if (player) { showArt(); message.textContent = 'Press Ask the GM to send this look.'; return; }
    commit(false, out.paint ? 'Paint saved. Mechanics unchanged.' : 'Paint removed.');
  });
  paintOff.addEventListener('click', () => {
    paintNow = {};
    if (player) { showArt(); message.textContent = 'Press Ask the GM to send this look.'; return; }
    commit(false, 'Paint removed.');
  });
  limited.addEventListener('change', () => { if (paintNow.paint) commit(false, limited.checked ? limitText.textContent.replace(/ \(.*/, '') + '.' : 'Paint kept until removed.'); });
  eraseAll.addEventListener('click', async () => {
    const { c } = current(); if (!c?.scope) return;
    if (!ask(`Erase all Flavor on ${c.scope}? Every creature, attack and spell here goes back to the original (paint too). Flavor kept on every map stays: erase it creature by creature.`)) return;
    const error = remote?.save ? await keepRemote(eraseMap(state, c.scope)) : keepLocal(eraseMap(state, c.scope));
    if (error) { message.textContent = error; return; }
    changed(); showActors(current().a?.id ?? c.actors[0].id); showSubjects();
    message.textContent = 'All Flavor on this map erased. Make it again any time.';
  });
  save.addEventListener('click', () => commit()); reset.addEventListener('click', () => commit(true)); close.addEventListener('click', () => dialog.close());
  listen?.('storage', e => { if (e.key === FLAVOR_KEY || e.key === null) { state = overlayPending(loadFlavor(storage), mine.pending); changed(); if (dialog.open) showSubjects(); } });
  return { get state() { return state; }, get mine() { return mine; }, get asks() { return asks; }, get asksRev() { return asksRev; }, rule, sync, dialog, controls: { actor, subject, name, description, appearance, art, role, share, onBase, trueHeight, riderSel, everywhere, paintOpen, paintOff, limited, paintNote, save, reset, eraseAll, close, message } };
}
