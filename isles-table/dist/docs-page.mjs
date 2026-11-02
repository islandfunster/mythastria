// DOCS-01 (GM 2026-10-22: "Let's maintain a list of features to be included in a documents page in the game."): the
// Documents page. It shows dist/features.json, which every piece of work keeps up to date.
const $ = id => document.getElementById(id);
const el = (tag, cls, text) => { const e = document.createElement(tag); if (cls) e.className = cls; if (text != null) e.textContent = text; return e; };
const LABEL = { built: 'Built', partly: 'Partly built', planned: 'Planned' };
let data = null;

/** The features that match a search and a status, by group (empty groups left out). */
export function filtered(doc, query = '', status = '') {
  const q = query.trim().toLowerCase();
  return doc.groups.map(g => ({ group: g.group, features: g.features.filter(f => (!status || f.status === status)
    && (!q || [f.name, f.what, f.how, f.limits, g.group].some(s => (s ?? '').toLowerCase().includes(q)))) }))
    .filter(g => g.features.length);
}

function draw() {
  const groups = filtered(data, $('find').value, $('status-filter').value);
  $('groups').replaceChildren(...groups.map(g => {
    const sec = el('section', 'panel');
    sec.append(el('h2', '', g.group));
    for (const f of g.features) {
      const box = el('div', 'feature'), h = el('h3');
      h.append(f.page ? Object.assign(el('a', '', f.name), { href: f.page }) : el('span', '', f.name), el('span', 'tag ' + f.status, LABEL[f.status] ?? f.status));
      if (f.since) h.append(el('span', 'since', 'since ' + f.since));
      box.append(h, el('p', '', f.what));
      if (f.how) box.append(el('p', 'how', 'How: ' + f.how));
      if (f.limits) box.append(el('p', 'limits', 'Not yet: ' + f.limits));
      sec.append(box);
    }
    return sec;
  }));
  const all = data.groups.flatMap(g => g.features), n = s => all.filter(f => f.status === s).length;
  $('counts').textContent = `${all.length} features: ${n('built')} built, ${n('partly')} partly built, ${n('planned')} planned. Updated ${data.updated}.`;
}

async function load() {
  try {
    data = await (await fetch('./features.json', { cache: 'no-cache' })).json();
  } catch { $('status').textContent = 'The feature list could not be read.'; $('status').className = 'error'; return; }
  $('status').textContent = 'Mythastria: SRD 5.2.1 (CC-BY-4.0) rules; your homebrew and rulings stay on your PC.';
  draw();
}
if ($('groups')) {                                                  // on the Documents page (the tests import filtered() only)
  for (const id of ['find', 'status-filter']) $(id).addEventListener('input', draw);
  load();
}
