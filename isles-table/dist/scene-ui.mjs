// GM 2026-10-24 ("not all creatures are automatically hostiles"; "The scene should have the hostility selected in the
// creatures and change it depending on the actions of the party"; "Morale should also be part of the prep"): the
// Attitudes and morale panel on Play live. The simulator owns every rule (Mythastria sim/attitude.py): this panel
// shows each creature's attitude (SRD 5.2.1: Friendly, Indifferent, Hostile), the changes and why, the engine's morale
// suggestions, and sends the GM's choices; it decides nothing itself. Seated players get what their characters can
// tell (the service cuts prep sources, morale rules and the GM's suggestions).

export const ATTITUDES = ['Hostile', 'Indifferent', 'Friendly'];
export const STATUS_TEXT = { surrendered: 'surrendered', fled: 'fled', parley: 'bargaining' };
const RULE_TEXT = { surrender: 'They surrender', flee: 'They flee', bargain: 'They bargain' };
const STATUS_OPTIONS = [['', 'Status…'], ['surrendered', 'Surrenders'], ['fled', 'Flees'], ['parley', 'Bargains'], ['fighting', 'Fights again']];

// The colour a token's side is drawn in (Hostile red, out of the fight amber, with the party blue).
export const sideColour = side => side === 'friend' ? '#5aa0e0' : side === 'neutral' ? '#d8b25a' : '#e06a5a';

// GM 2026-10-25 ("add an asterisk to the SRD referring to the optional pack and link to the specific item"): beside each
// creature's attitude, a * that opens the Social rules pack's page at the item that would set its disposition.
export function packStar(pack, doc = document) {
  const a = doc.createElement('a');
  a.className = 'pack-star'; a.textContent = '*'; a.target = '_blank'; a.rel = 'noopener';
  a.href = `rules-social.html#${pack.item}`;
  a.title = `Optional Social rules pack: ${pack.attitude} (${pack.why})`;
  a.setAttribute('aria-label', `Social rules pack: ${pack.attitude}, ${pack.why}`);
  return a;
}

export function attitudeLine(c) {
  const what = c.joined ? `${c.attitude}, with the party` : c.attitude;
  return c.status ? `${what} · ${STATUS_TEXT[c.status] ?? c.status}` : what;
}

export function mountScene({ panel, body, port, take, result, gm }) {
  const el = (tag, cls, text) => { const e = document.createElement(tag); if (cls) e.className = cls; if (text !== undefined) e.textContent = String(text); return e; };
  let reason = '';
  async function send(choice) {
    const out = await port.scene({ ...choice, why: reason.trim() || undefined }).catch(() => ({ ok: false, error: 'The service stopped.' }));
    if (out?.live) take(out);
    if (!out?.ok) result(out?.refused || out?.error || 'Not done.', 'refused');
    else result('');
  }
  function button(text, choice, cls = 'quiet', title = '') {
    const b = el('button', cls, text); if (title) b.title = title;
    b.addEventListener('click', () => send(choice));
    return b;
  }
  function draw(snap) {
    const scene = snap?.scene;
    panel.hidden = !scene || !scene.creatures?.length;
    if (panel.hidden) return;
    const key = JSON.stringify([scene, snap.done, snap.pillar?.mode]);
    if (panel.dataset.key === key) return;
    panel.dataset.key = key;
    const parts = [];
    if (scene.outcome) parts.push(el('p', 'scene-outcome', scene.outcome));
    if (gm) for (const c of scene.cards ?? []) {
      const box = el('div', 'scene-card');
      box.append(el('div', '', c.text));
      if (c.kind === 'urge') {                                     // GM 2026-10-25 (ruling P3): the attitude follows the urge
        box.append(button('Stand down (Indifferent)', { op: 'urge', n: c.n, wants: 'stand_down' }, ''),
          ' ', button('Help us (Friendly)', { op: 'urge', n: c.n, wants: 'help' }, ''),
          ' ', button('Something else (no change)', { op: 'urge', n: c.n, wants: 'other' }));
      } else {
        box.append(button(RULE_TEXT[c.rule] ?? 'Accept', { op: 'morale', n: c.n, accept: true }, ''),
          ' ', button('They fight on', { op: 'morale', n: c.n, accept: false }));
      }
      parts.push(box);
    }
    const list = el('div', 'scene-list');
    for (const c of scene.creatures) {
      const row = el('div', 'scene-row att-' + c.attitude.toLowerCase());
      const name = el('span', 'scene-name', c.name);
      const badge = el('span', 'att-badge', attitudeLine(c));
      if (gm && c.from) badge.title = `From: ${c.from}\nMorale: ${c.morale}`;
      row.append(name, badge);
      if (gm && c.pack?.item) row.append(packStar(c.pack));      // GM 2026-10-25: the optional Social rules pack's item
      if (gm && !snap.done) {
        const pick = el('select'); pick.setAttribute('aria-label', `${c.name}'s attitude`);
        for (const a of ATTITUDES) pick.append(new Option(a, a, a === c.attitude, a === c.attitude));
        pick.addEventListener('change', () => send({ op: 'attitude', creature: c.id, attitude: pick.value }));
        const st = el('select'); st.setAttribute('aria-label', `${c.name}'s status`);
        for (const [v, t] of STATUS_OPTIONS) st.append(new Option(t, v));
        st.addEventListener('change', () => { if (st.value) send({ op: 'status', creature: c.id, status: st.value }); });
        row.append(pick, st);
        if (c.attitude === 'Friendly') row.append(c.joined ? button('Leaves the party', { op: 'leave', creature: c.id })
          : button('Joins the party', { op: 'join', creature: c.id }, 'quiet', 'A Friendly creature fights on the party\'s side'));
        if (c.morale && c.morale !== 'fights to the end') row.append(el('span', 'scene-morale', 'Morale: ' + c.morale));
      }
      list.append(row);
    }
    parts.push(list);
    if (gm && !snap.done) {
      const why = el('input'); why.placeholder = 'Why (optional): a gift, a kept promise…'; why.maxLength = 120; why.value = reason;
      why.addEventListener('input', () => { reason = why.value; });
      const ends = el('p', 'scene-ends');
      if (!snap.pillar || snap.pillar.mode === 'fight')            // GM 2026-10-26: in a social or exploration scene nothing to call off
        ends.append(button('Call a truce', { op: 'truce' }, 'quiet', 'Everyone fighting the party stands down (Indifferent): the fight ends with no winner'),
          ' ', button('The party retreats', { op: 'retreat' }, 'quiet', 'The fight ends with no winner; the scene goes on'), ' ');
      ends.append(button('End the scene', { op: 'end' }, 'quiet', snap.pillar ? 'The encounter ends' : 'For a scene where nobody fights'));
      parts.push(why, ends);
    }
    const changes = (scene.changes ?? []).slice(-4).map(e => el('div', 'scene-change',
      `${e.name}: ${e.status ? STATUS_TEXT[e.status] ?? e.status : `${e.from} → ${e.to}`} (${e.why}${e.by === 'GM' ? '; the GM' : ''})`));
    if (changes.length) parts.push(el('div', 'note', 'Changes:'), ...changes);
    if (gm) parts.push(el('p', 'note', 'The engine applies the rules (attacks provoke; Influence and help befriend); you can set anything. Morale is only suggested: you decide.'));
    body.replaceChildren(...parts);
  }
  return { draw };
}
