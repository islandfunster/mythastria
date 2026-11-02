// DM-SWAP-01 (GM 2026-10-25: "There is only one Mythastria ... You can also request a DM key and when receiving that,
// your screen becomes the full DM version and the original DM becomes a player, except he also has a take back button on
// his player screen"; chose: the current GM approves; the old GM plays one of his own characters or watches). Four
// screens, one module (the service decides everything: tools/dm_handoff.py):
// - a seated player: Ask to be the GM; once approved the page takes the role and opens the full GM console;
// - the owning GM: the request, with the character he will play, Approve or Refuse;
// - the owning GM while another is the GM (play.html?view=player&dm=handed): his player screen and Take back the GM;
// - the new GM's console (players' door): Give the GM back, and back to the player screen when the role is taken back.
// GM 2026-10-28 ("I don't want the request on the client-only version"; "Let's leave out the Stand-in key"): the players'
// door is never a GM console and refuses the request, so only the GM's own two screens are left here.
const make = (tag, text, cls) => { const e = document.createElement(tag); if (text != null) e.textContent = text; if (cls) e.className = cls; return e; };

export function mountDmSwap({ port, hello, player, seated, oldDm, status, anchor }) {
  const bar = make('div', null, 'dm-swap');
  bar.id = 'dm-swap';
  anchor.before(bar);
  const every = (fn, ms) => { fn(); return setInterval(fn, ms); };

  if (oldDm) {                                                    // the owning GM, handed over: Take back
    const who = hello.handed?.to ?? 'another player', mine = hello.handed?.character;
    const back = make('button', 'Take back the GM');
    back.title = 'End the other GM’s session now: your screen is the full GM console again';
    back.addEventListener('click', async () => {
      const out = await port.dm({ op: 'take_back' }).catch(() => null);
      if (out?.ok || out?.error?.includes('GM already')) location.href = '/play.html';
      else status(out?.error || 'The table did not answer.', true);
    });
    bar.append(make('span', `${who} is the GM. You ${mine ? 'play ' + mine : 'watch'}. `), back);
    every(async () => {                                           // the new GM gave it back: the full console again
      const s = await port.dm({ op: 'state' }).catch(() => null);
      if (s?.ok && !s.held) location.href = '/play.html';
    }, 5000);
    return;
  }

  if (!player) {                                                  // the owning GM: a request to answer
    bar.hidden = true;
    let shown = '';
    every(async () => {
      const s = await port.dm({ op: 'state' }).catch(() => null);
      if (!s?.ok) return;
      const key = JSON.stringify([s.asked, s.characters]);
      if (key === shown) return;
      shown = key;
      bar.replaceChildren();
      bar.hidden = !s.asked;
      if (!s.asked) return;
      const pick = make('select');
      pick.setAttribute('aria-label', 'The character you will play');
      pick.append(new Option('Just watch', ''), ...(s.characters ?? []).map(n => new Option(n, n)));
      const yes = make('button', 'Approve'), no = make('button', 'Refuse', 'quiet');
      yes.addEventListener('click', async () => {
        const out = await port.dm({ op: 'approve', character: pick.value }).catch(() => null);
        if (out?.ok) location.href = '/play.html?view=player&dm=handed';
        else status(out?.error || 'The table did not answer.', true);
      });
      no.addEventListener('click', async () => {
        const out = await port.dm({ op: 'refuse' }).catch(() => null);
        if (!out?.ok) status(out?.error || 'The table did not answer.', true);
      });
      bar.append(make('b', `${s.asked.seat}${s.asked.character ? ' (' + s.asked.character + ')' : ''} asks to be the GM. `),
        make('span', 'You will play: '), pick, ' ', yes, ' ', no,
        make('span', ' Their screen becomes the GM console for the loaded adventure; yours a player screen with Take back.', 'note'));
    }, 3000);
  }
}
