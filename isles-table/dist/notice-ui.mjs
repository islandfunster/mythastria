// JOIN-01 notice (GM 2026-10-22: "Before connecting for a game, there needs to be legalese regarding private information
// ... i.e. age requirement"; chose players from anywhere, 18+ only, contact the GM at the table, 14 days for chat
// pictures): the privacy, age and table-rules notice on the join page. The text is
// table-notice.json (the service reads its version and asks again when it changes); this module only shows it and the
// two boxes. Links in the text are shown as plain text a player can copy, never followed by the page.
import { asset } from './server.mjs';                          // PLAYER-SITE-01: the GM's own notice, from the GM's PC
export async function loadNotice(fetchFn = globalThis.fetch) {
  try {
    const res = await fetchFn(asset('table-notice.json'));
    return res.ok ? await res.json() : null;
  } catch { return null; }
}

export function mountNotice(box, notice, doc = globalThis.document) {
  const make = (tag, text, cls) => { const e = doc.createElement(tag); if (text !== undefined) e.textContent = text; if (cls) e.className = cls; return e; };
  if (!notice) { box.replaceChildren(make('p', 'The table notice could not be read; reload the page.', 'error')); return { value: () => null }; }
  const text = make('details', undefined, 'notice-text'); text.open = true;
  text.append(make('summary', notice.title));
  for (const s of notice.sections) {
    text.append(make('h3', s.h));
    for (const p of s.p) text.append(make('p', p));
  }
  text.append(make('p', notice.footer, 'note'), make('p', `Notice version ${notice.version}`, 'note'));
  const tick = label => { const t = make('input'); t.type = 'checkbox'; t.required = true; const l = make('label', undefined, 'notice-tick'); l.append(t, ' ' + label); return [l, t]; };
  const [adultLabel, adult] = tick(notice.adult);
  const [acceptLabel, accept] = tick(notice.accept);
  box.replaceChildren(text, adultLabel, acceptLabel);
  return { value: () => ({ version: notice.version, adult: adult.checked, accept: accept.checked }) };
}
