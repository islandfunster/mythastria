// GM 2026-10-26 (goal 14: "Adventures as social, exploration and combat"): the scene panel on Play live and The Stage.
// The simulator owns every rule (Mythastria sim/scenes.py): a social or exploration scene has no turns and no
// initiative; each character acts when its player chooses; the engine suggests when a fight starts (a Hostile creature
// meets the party, a player tries a strike) and who is surprised; the GM decides. This panel shows the scene and sends
// the choices; it decides nothing itself. Seated players get no GM cards (the service cuts them).

export const MODE_TEXT = { social: 'Social scene', exploration: 'Exploration', fight: 'Fight' };
export const SKILLS = ['Acrobatics', 'Animal Handling', 'Arcana', 'Athletics', 'Deception', 'History', 'Insight', 'Intimidation',
  'Investigation', 'Medicine', 'Nature', 'Perception', 'Performance', 'Persuasion', 'Religion', 'Sleight of Hand', 'Stealth', 'Survival'];
export const ABILITIES = { str: 'Strength', dex: 'Dexterity', con: 'Constitution', int: 'Intelligence', wis: 'Wisdom', cha: 'Charisma' };

export function inScene(snap) { return !!snap?.pillar && snap.pillar.mode !== 'fight' && !snap.done; }

// the line the page's status shows in a scene (no round, no turn)
export function sceneStatus(snap, names) {
  const p = snap?.pillar;
  if (!p || p.mode === 'fight') return null;
  const who = names.get(snap.waiting);
  return `${p.label}: no initiative${who ? ` · ${who} acts` : ''}. Each character acts when its player chooses.`;
}

export function mountPillar({ panel, body, port, take, result, gm, mine = () => null, stage = false }) {
  const el = (tag, cls, text) => { const e = document.createElement(tag); if (cls) e.className = cls; if (text !== undefined) e.textContent = String(text); return e; };
  let snap = null, manual = false, about = '', skill = 'Perception', roll = '';
  const ticked = new Map();                                          // card n -> the surprised the GM has ticked
  async function scene(choice) {
    const out = await port.scene(choice).catch(() => ({ ok: false, error: 'The service stopped.' }));
    if (out?.live) take(out);
    result(out?.ok ? '' : out?.refused || out?.error || 'Not done.', out?.ok ? '' : 'refused');
    return out;
  }
  async function act(choice) {
    const out = await port.act({ ...choice, fight_id: snap.fight_id, revision: snap.revision }).catch(() => ({ ok: false, error: 'The service stopped.' }));
    if (out?.live) take(out);
    result(out?.ok ? '' : out?.refused || out?.error || 'Not done.', out?.ok ? '' : 'refused');
    return out;
  }
  const button = (text, fn, cls = 'quiet', title = '') => { const b = el('button', cls, text); if (title) b.title = title; b.addEventListener('click', fn); return b; };
  const pcs = () => (snap?.state?.combatants ?? []).filter(c => c.pc && !c.down && !c.dead);
  const others = () => (snap?.state?.combatants ?? []).filter(c => !c.pc && !c.down && !c.dead);

  function startBox(card) {                                          // who is surprised, then roll Initiative
    const box = el('div', 'scene-card');
    box.append(el('div', '', card.text));
    const key = card.n ?? 'manual';
    if (!ticked.has(key)) ticked.set(key, new Set(card.surprised ?? []));
    const picks = ticked.get(key), list = el('div', 'pillar-surprise');
    list.append(el('span', 'note', 'Surprised (Disadvantage on Initiative): '));
    for (const c of [...pcs(), ...others()]) {
      const label = el('label', 'check'), box2 = el('input');
      box2.type = 'checkbox'; box2.checked = picks.has(c.id);
      box2.addEventListener('change', () => { box2.checked ? picks.add(c.id) : picks.delete(c.id); });
      label.append(box2, ' ' + c.name); list.append(label);
    }
    box.append(list,
      button('Start the fight (roll Initiative)', () => scene({ op: 'fight', ...(card.n != null ? { n: card.n } : {}), surprised: [...picks] }).then(o => { if (o?.ok) { ticked.delete(key); manual = false; } }), '',
        'Initiative is rolled for everyone now (d20 + Dexterity); the surprised roll with Disadvantage'),
      ' ', card.n != null ? button('Not yet', () => scene({ op: 'not_yet', n: card.n }), 'quiet', 'Keep the scene going; the GM can start the fight any time')
        : button('Cancel', () => { manual = false; draw(snap); }));
    return box;
  }

  function checkForm(actor) {                                        // any other ability check, ruled by the GM
    const row = el('div', 'pillar-check');
    const pick = el('select'); pick.setAttribute('aria-label', 'Skill or ability');
    for (const s of SKILLS) pick.append(new Option(s, s, s === skill, s === skill));
    for (const [a, n] of Object.entries(ABILITIES)) pick.append(new Option(n + ' (no skill)', a, a === skill, a === skill));
    pick.addEventListener('change', () => { skill = pick.value; });
    const using = el('select'); using.setAttribute('aria-label', 'Ability, when the GM calls another one for this skill');
    using.append(new Option('usual ability', ''));
    for (const [a, n] of Object.entries(ABILITIES)) using.append(new Option(n, a));
    const how = el('select'); how.setAttribute('aria-label', 'Advantage');
    for (const [v, t] of [['', 'plain roll'], ['advantage', 'Advantage'], ['disadvantage', 'Disadvantage']]) how.append(new Option(t, v, v === roll, v === roll));
    how.addEventListener('change', () => { roll = how.value; });
    const what = el('input'); what.placeholder = 'What for (optional): is he lying?'; what.maxLength = 120; what.value = about;
    what.addEventListener('input', () => { about = what.value; });
    row.append(pick, ' ', using, ' ', how, ' ', what, ' ', button('Roll the check', () => act({ op: 'check', actor, ...(ABILITIES[skill] ? { ability: skill } : { skill, ...(using.value ? { ability: using.value } : {}) }),
      ...(roll ? { roll } : {}), ...(about.trim() ? { about: about.trim() } : {}) }), '', 'd20 + this character\'s bonus; the GM sets the DC and rules it'));
    return row;
  }

  function draw(next) {
    snap = next;
    const p = snap?.pillar;
    panel.hidden = !p;
    if (!p) return;
    const key = JSON.stringify([p, snap.waiting, snap.done, snap.revision, manual, gm]);
    if (panel.dataset.key === key) return;
    panel.dataset.key = key;
    const parts = [], scenic = inScene(snap), names = new Map((snap.state?.combatants ?? []).map(c => [c.id, c.name]));
    const head = el('p', 'pillar-mode pillar-' + p.mode, p.label);
    parts.push(head);
    const last = p.history?.[p.history.length - 1];
    if (last) parts.push(el('p', 'note', `Since: ${last.why}.`));
    const fought = [...(p.history ?? [])].reverse().find(h => h.outcome);
    if (fought && scenic) parts.push(el('p', 'scene-outcome', fought.outcome));
    if (snap.done) { parts.push(el('p', 'note', 'The encounter is over.')); body.replaceChildren(...parts); return; }
    if (scenic) {
      parts.push(el('p', 'note', p.mode === 'social'
        ? 'No turns, no initiative. Speak in character; use Influence (on the sheet or The Stage) and other checks; the GM rules each.'
        : 'No turns, no initiative. Move freely, Search, Study, open doors, use your gear. Initiative is rolled only when a fight starts.'));
      const own = gm ? pcs() : pcs().filter(c => c.id === mine());
      if (own.length) {
        const who = el('div', 'pillar-who');
        who.append(el('span', 'note', 'Acting: '));
        for (const c of own) who.append(button(c.name, () => act({ op: 'focus', actor: c.id }), c.id === snap.waiting ? 'act' : 'quiet',
          c.id === snap.waiting ? `${c.name} acts now` : `${c.name} steps forward to act`));
        parts.push(who);
        const actor = own.some(c => c.id === snap.waiting) ? snap.waiting : own[0].id;
        parts.push(el('div', 'note', `An ability check for ${names.get(actor)}:`), checkForm(actor));
      }
      if (gm) {
        for (const c of p.cards ?? []) parts.push(startBox(c));
        if (manual) parts.push(startBox({ text: 'Start the fight now: who is surprised?', surprised: [] }));
        const moves = el('p', 'scene-ends');
        if (p.mode !== 'social') moves.append(button('Talk (The Stage)', () => scene({ op: 'talk' }), 'quiet', 'A social scene: no turns; Influence and checks'), ' ');
        if (p.mode !== 'exploration') moves.append(button('Explore (the map)', () => scene({ op: 'explore' }), 'quiet', 'An exploration scene: move freely, Search, Study'), ' ');
        if (!manual) moves.append(button('Start a fight…', () => { manual = true; draw(snap); }, 'quiet', 'Roll Initiative now (choose who is surprised)'));
        parts.push(moves);
      }
      if (p.mode === 'social' && !stage) {
        const a = el('a', 'adv-go quiet', 'Open The Stage'); a.href = './stage.html'; a.target = 'mythastria-stage';
        a.title = 'The social scene: the creatures there, their attitudes, Influence and the spotlight';
        parts.push(el('p', '', ''), a);
      }
    } else if (gm) {
      parts.push(el('p', 'note', 'A fight, in Initiative order. It ends with Call a truce (back to talk), The party retreats (back to exploring) or End the scene, in Attitudes and morale; a surrender or a win goes back to the scene too.'));
    }
    const checks = (p.checks ?? []).slice(-4);
    if (checks.length) parts.push(el('div', 'note', 'Checks:'), ...checks.map(c => el('div', 'scene-change',
      `${c.who}: ${c.check} ${c.total}${c.about ? ` (${c.about})` : ''}`)));
    body.replaceChildren(...parts);
  }
  return { draw };
}
