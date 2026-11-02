// CHARACTERS-01 (GM 2026-10-21: "I would like it able to import formats like forge, dnd beyond, fantasy grounds, etc. as
// well as a having a first rate character builder that can quickly be tested in live"): the Characters page. Import,
// build, saved sheets and their photos, on the simulator service (Python, the rules authority). It replaces the
// Characters workshop of the old Rust training table (character-ui.mjs, still there for training.html).
//
// The saved sheets are the same isles-character/1 records under the same browser key as before, so every sheet saved on
// the training table is here as it was. The service checks each save (POST /api/characters, sim/character_roster.py).
// Photos stay in this browser only (character-photos.mjs), as on Play live.
import { loadCatalog } from './catalog.mjs';
import { createRosterPort } from './character-roster.mjs';
import { loadTableParty } from './party-store.mjs';             // GM 2026-10-28: Delete takes it out of the table's party too
import { parseXML, parsePDF, parseSheet, parseText, parseCharacterJSON, parseDelimited, sheetsCSVURL, ABILITIES } from './character-import.mjs';
import { createBuilder, BUILD_FORMAT } from './character-builder-ui.mjs';
import { renderSheet } from './character-sheet-view.mjs';
import { MAX_PHOTOS, loadPhotos, savePhotos, addPhoto, removePhoto, setActive, photoOf, photoFromFile } from './character-photos.mjs';
import { parseOtherJSON, hardenFG, reportFromFields, pdfReport, pdfPictures, fetchPortrait, fromMythastriaSheet, readXlsx, gridFromRows, isIainMcEwen, fromIainMcEwen } from './character-formats.mjs';
import { sheetPDF } from './character-sheet-pdf.mjs';

export const ROSTER_KEY = 'isles-character-roster-v1';
const TABS = { roster: 'Saved characters', minmax: 'Min-max', fun: 'Fun builds', import: 'Import', build: 'Build', sheet: 'Sheet' };
// GM 2026-10-23: "a button in the character builder called min max. People can save character sheets that they received
// from other people that ... optimized builds and then put in another button for fun ideas of characters that are not
// built for maximum effectiveness, but rather have synergistic capabilities that are terribly fun". Two shelves of
// sheets kept in this browser apart from the user's own characters (never in Mythastria's files: other people's builds are
// the user's own content); a sheet is copied to the characters through the same rules check as any save.
export const SHELVES = {
  minmax: { key: 'mythastria-shelf-minmax-v1', title: 'Min-max', about: 'Optimized builds people share with you: the strongest choices for a class or a plan.' },
  fun: { key: 'mythastria-shelf-fun-v1', title: 'Fun builds', about: 'Characters picked for fun and for abilities that work together, not for the biggest numbers.' },
};
export const SHELF_FORMAT = 'mythastria-build-shelf/1';
export function shelfEntry(sheet, note = '') {
  const copy = structuredClone(sheet);
  if (copy.import?.portraits) copy.import.portraits = copy.import.portraits.map(p => (p.kind === 'data' ? { kind: 'data', label: p.label } : p));
  return { id: globalThis.crypto.randomUUID(), note: String(note ?? '').slice(0, 500), added: new Date().toISOString(), sheet: copy };
}
// Entries from a shelf file, or from any character file the import reads (each sheet becomes an entry without a note).
export function shelfEntries(doc, readSheets) {
  if (doc?.format === SHELF_FORMAT && Array.isArray(doc.entries))
    return doc.entries.filter(e => e?.sheet && typeof e.sheet === 'object').map(e => ({ ...shelfEntry(e.sheet, e.note), added: e.added || new Date().toISOString() }));
  return (readSheets(JSON.stringify(doc)) ?? []).map(c => shelfEntry(c));
}
// A shelf sheet copied to the user's own characters: a new id, so it never replaces the original or another copy.
export function copyFromShelf(sheet) {
  const id = globalThis.crypto.randomUUID(), copy = { ...structuredClone(sheet), id };
  if (copy.build) copy.build = { ...copy.build, id };
  return copy;
}

// Artwork for a sheet that has none yet (the service wants registered 1-square art): a look that suits the class. The
// sheet's photo, when it has one, is what the token shows; this is only the fallback picture.
const CLASS_ART = { Barbarian: 'gladiator', Bard: 'noble', Cleric: 'priest', Druid: 'druid', Fighter: 'knight', Monk: 'gladiator',
  Paladin: 'knight', Ranger: 'scout', Rogue: 'spy', Sorcerer: 'mage', Warlock: 'mage', Wizard: 'mage' };
export function defaultArt(character, tokens) {
  const ok = id => tokens.some(t => t.id === id && t.squares * 5 === (character.space_ft ?? 5));
  const cls = character.classes?.[0]?.name?.trim().replace(/^./, s => s.toUpperCase()).replace(/\s.*$/, '');
  return [CLASS_ART[cls], 'warrior_veteran', 'commoner'].find(id => id && ok(id)) ?? tokens.find(t => t.squares * 5 === (character.space_ft ?? 5))?.id ?? '';
}

export function classLine(c) { return (c.classes ?? []).map(k => k.name + (k.level ? ' ' + k.level : '')).join(' / '); }
export function summaryLine(c) {
  const k = c.combat ?? {};
  return [`${k.hp_max ?? '?'} HP`, `AC ${k.ac ?? '?'}`, `${k.speed ?? '?'} ft`].join(' · ');
}

// ------------------------------------------------------------------ small DOM helpers
const el = (tag, text, cls) => { const n = document.createElement(tag); if (text !== undefined) n.textContent = text; if (cls) n.className = cls; return n; };
const button = (text, fn, cls = 'quiet') => { const b = el('button', text, cls); b.type = 'button'; b.onclick = fn; return b; };
const para = (root, text, cls = 'char-note') => root.appendChild(el('p', text, cls));
function field(root, label, value, change, { type = 'text', options, multiple = false, rows = 3, min, max } = {}) {
  const wrap = el('label', label);
  let input;
  if (options) {
    input = el('select'); input.multiple = multiple;
    for (const item of options) {
      const [v, t] = Array.isArray(item) ? item : [item, item], op = el('option', t);
      op.value = v; op.selected = multiple ? (value ?? []).includes(v) : String(v) === String(value ?? '');
      input.append(op);
    }
    if (multiple) input.size = Math.min(8, Math.max(3, options.length));
  } else {
    input = el(type === 'textarea' ? 'textarea' : 'input');
    if (type === 'textarea') input.rows = rows; else input.type = type;
    if (min !== undefined) input.min = min; if (max !== undefined) input.max = max;
    if (type !== 'file') input.value = value ?? '';
  }
  input.onchange = () => change(multiple ? [...input.selectedOptions].map(o => o.value) : input.value);
  wrap.append(input); root.append(wrap);
  return input;
}
function fold(root, title, open = false) {
  const d = el('details'); d.open = open; d.append(el('summary', title));
  const body = el('div'); d.append(body); root.append(d);
  return body;
}
function download(name, value) {
  const url = URL.createObjectURL(value instanceof Blob ? value : new Blob([JSON.stringify(value, null, 2)], { type: 'application/json' }));
  const a = el('a'); a.href = url; a.download = name; a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
export const fileName = name => (String(name || 'character').replace(/[^a-zA-Z0-9_-]+/g, '_').slice(0, 60) || 'character');

// ------------------------------------------------------------------ the page
export async function createCharactersPage({ root = document, fetch: fetchFn = globalThis.fetch, storage = globalThis.localStorage } = {}) {
  const $ = id => root.getElementById(id);
  const nav = root.querySelector('.char-tabs'), main = $('char-pane'), statusLine = $('char-status');
  // A service started before the Characters update answers its new requests with "Unsupported command": say what to do.
  const service = createRosterPort({ fetch: fetchFn });
  const port = { call: req => service.call(req).catch(e => {
    if (/Unsupported command/.test(e.message)) throw Error('Mythastria is running an older version of the simulator service. Close the Mythastria window, then double-click Start_Mythastria.bat again.');
    throw e;
  }), get checkedBy() { return service.checkedBy; } };
  const tokens = await loadCatalog(fetchFn) ?? [];
  let roster = [], photos = loadPhotos(storage), draft = null, candidates = [], tab = 'roster', builderErrors = [];

  function status(text, bad = false) { statusLine.textContent = text; statusLine.className = bad ? 'error' : ''; }
  function persist() {
    try { storage?.setItem(ROSTER_KEY, JSON.stringify(kept())); }
    catch { status('Saved for now, but this browser is out of room: use Export all to keep a copy.', true); }
  }
  function keepPhotos(next) {
    photos = next;
    if (!savePhotos(photos, storage)) status('This browser is out of room for photos: remove one, or use a smaller picture.', true);
    show(tab);
  }

  // The saved sheets: the browser's copy, checked again by the service. A sheet the service refuses is never dropped: it
  // stays in `refused` (kept in the browser, marked on the list) until it is fixed and saved, or deleted.
  let refused = [];
  async function loadRoster() {
    let saved = [];
    try { saved = JSON.parse(storage?.getItem(ROSTER_KEY) || '[]'); if (!Array.isArray(saved)) saved = []; } catch { saved = []; }
    refused = [];
    try {
      roster = (await port.call({ op: 'character_roster_load', characters: saved })).characters;
    } catch (e) {
      if (/not running/.test(e.message)) { roster = saved; status(e.message, true); return; }
      roster = (await port.call({ op: 'character_roster_load', characters: [] })).characters;   // one at a time instead
      for (const c of saved) {
        try { roster = (await port.call({ op: 'character_save', character: c })).characters; }
        catch (why) { if (c && typeof c === 'object') refused.push({ ...c, refused: why.message }); }
      }
    }
    status(refused.length ? `${refused.length} saved character${refused.length === 1 ? ' needs' : 's need'} fixing (marked below); nothing was lost.`
      : saved.length ? `${saved.length} saved character${saved.length === 1 ? '' : 's'}, checked by the simulator service.` : 'No saved characters yet: build one or import one.', refused.length > 0);
  }
  const kept = () => [...roster, ...refused.filter(r => !roster.some(c => c.id === r.id)).map(({ refused: _, ...c }) => c)];

  for (const [id, label] of Object.entries(TABS)) {
    const b = button(label, () => show(id)); b.dataset.tab = id; b.id = 'char-tab-' + id; b.setAttribute('role', 'tab');
    b.setAttribute('aria-controls', 'char-pane'); nav.append(b);
  }

  function show(id) {
    tab = id;
    for (const b of nav.children) { b.setAttribute('aria-selected', String(b.dataset.tab === id)); b.tabIndex = b.dataset.tab === id ? 0 : -1; }
    main.setAttribute('aria-labelledby', 'char-tab-' + id);
    main.replaceChildren();
    ({ roster: drawRoster, minmax: () => drawShelf('minmax'), fun: () => drawShelf('fun'), import: drawImport, build: drawBuild, sheet: drawSheet })[id]();
  }
  function open(c, from = null) {
    const { refused: why, ...sheet } = c;
    draft = structuredClone(sheet); builderErrors = []; candidates = from ?? []; pendingPhoto = null; flagsFor = null; testOpen = false; show('sheet');
    if (why) status('The service refused this saved sheet: ' + why + ' Fix it and save again.', true);
    checkFlags();
  }

  // The service says what on the sheet is not SRD 5.2.1 (sim/character_rules.py): homebrew the GM rules, never refused.
  let flagsFor = null, pendingPhoto = null, memberProblems = [];
  const isBuilt = c => c?.build?.format === BUILD_FORMAT && c?.derived?.attacks;
  async function checkFlags() {
    const id = draft?.id;
    try {
      const out = await port.call({ op: 'character_member', character: draft });
      if (draft?.id !== id) return;
      draft.homebrew = out.flags ?? [];
      if (!isBuilt(draft)) draft.gm_rules = out.gm_rules ?? [];
      memberProblems = out.problems ?? [];
      flagsFor = id;
      if (tab === 'sheet') show('sheet');
    } catch { /* without the service the sheet still opens; the check runs again on save */ }
  }

  // -------------------------------------------------------------- saved characters
  function picture(c) {
    const url = photoOf(photos, c.id) ?? tokens.find(t => t.id === c.token_id)?.path;
    if (!url) return el('div', '', 'no-art');
    const im = el('img'); im.src = url; im.alt = ''; return im;
  }
  function drawRoster() {
    const bar = el('div', undefined, 'char-actions');
    bar.append(button('Build a character', () => show('build'), ''), button('Import a character', () => show('import')),
      button('Export all', () => download('mythastria-characters.json', { format: 'isles-character-collection/1', characters: kept() })),
      button('Blank character sheet (PDF)', async () => download('mythastria-character-sheet.pdf', await sheetPDF(null))));
    main.append(bar);
    if (!roster.length && !refused.length) para(main, 'No saved characters yet. Build one, or import a sheet from another program.');
    for (const c of [...roster, ...refused.filter(r => !roster.some(k => k.id === r.id))]) {
      const row = el('article', undefined, 'char-card'), text = el('div'), acts = el('div', undefined, 'char-actions');
      text.append(el('h3', c.name));
      para(text, [c.species, classLine(c), c.kind === 'npc' ? 'NPC' : null].filter(Boolean).join(' · '));
      para(text, summaryLine(c));
      if (c.refused) para(text, 'Needs fixing: ' + c.refused, 'char-note char-error');
      acts.append(button('Open sheet', () => open(c)), button('Test in Play live', () => { open(c); testOpen = true; show('sheet'); document.getElementById('char-test')?.scrollIntoView({ block: 'center' }); }),
        button('Delete', () => remove(c)));                    // GM 2026-10-28: "a delete character button in all the characters tabs"
      row.append(picture(c), text, acts);
      main.append(row);
    }
  }

  // -------------------------------------------------------------- the build shelves (Min-max, Fun builds)
  function shelf(name) {
    try { const list = JSON.parse(storage?.getItem(SHELVES[name].key) || '[]'); return Array.isArray(list) ? list : []; } catch { return []; }
  }
  function keepShelf(name, list) {
    try { storage?.setItem(SHELVES[name].key, JSON.stringify(list)); return true; }
    catch { status('This browser is out of room: export the shelf, then remove a sheet.', true); return false; }
  }
  function putOnShelf(name) {
    if (!draft) return;
    const note = prompt(`A note for ${draft.name} on the ${SHELVES[name].title} shelf (who made it, why it is strong or fun):`, '');
    if (note === null) return;
    if (keepShelf(name, [...shelf(name), shelfEntry(draft, note)])) status(`${draft.name} is on the ${SHELVES[name].title} shelf.`);
  }
  async function copyToCharacters(entry) {
    try {
      const copy = copyFromShelf(entry.sheet);
      roster = (await port.call({ op: 'character_save', character: copy })).characters;
      persist();
      status(`${copy.name} is copied to your saved characters (checked by the rules).`);
    } catch (e) { status('Not copied: ' + e.message, true); }
  }
  function drawShelf(name) {
    const info = SHELVES[name], list = shelf(name);
    para(main, info.about + ' The shelf is kept in this browser, apart from your own characters. To add a sheet: import it ' +
      '(Import) or open one of your characters, then choose "Put on the ' + info.title + ' shelf" at the bottom of its sheet.');
    const bar = el('div', undefined, 'char-actions'), pick = el('input');
    pick.type = 'file'; pick.accept = '.json'; pick.hidden = true;
    pick.onchange = async () => {
      const file = pick.files?.[0]; pick.value = '';
      if (!file) return;
      try {
        const doc = JSON.parse(await file.text());
        const added = shelfEntries(doc, t => parseOtherJSON(t) ?? parseCharacterJSON(t));
        if (!added.length) throw Error('No character found in that file.');
        if (keepShelf(name, [...shelf(name), ...added])) { status(`${added.length} sheet${added.length === 1 ? '' : 's'} added to the ${info.title} shelf.`); show(name); }
      } catch (e) { status('Not added: ' + (e.message ?? e), true); }
    };
    bar.append(button('Add from a file (.json)', () => pick.click(), ''), pick,
      button('Export this shelf', () => download(fileName(info.title) + '-shelf.json', { format: SHELF_FORMAT, shelf: name, entries: list })));
    main.append(bar);
    if (!list.length) para(main, 'Nothing on this shelf yet.');
    for (const entry of list) {
      const c = entry.sheet, row = el('article', undefined, 'char-card'), text = el('div'), acts = el('div', undefined, 'char-actions');
      text.append(el('h3', c.name || 'Unnamed'));
      para(text, [c.species, classLine(c)].filter(Boolean).join(' · '));
      if (entry.note) para(text, entry.note, 'char-note char-shelf-note');
      acts.append(
        button('Open sheet', () => { open({ ...structuredClone(c), id: entry.id }); status(`From the ${info.title} shelf: "Save character" copies it into your characters.`); }),
        button('Copy to my characters', () => copyToCharacters(entry)),
        button('Edit note', () => {
          const note = prompt('Note:', entry.note ?? '');
          if (note !== null && keepShelf(name, shelf(name).map(e => e.id === entry.id ? { ...e, note: note.slice(0, 500) } : e))) show(name);
        }),
        button('Delete', () => {                               // GM 2026-10-28: a Delete on every characters tab
          if (confirm(`Delete ${c.name || 'this sheet'} from the ${info.title} shelf? Export the shelf first if you may want it again.`)
              && keepShelf(name, shelf(name).filter(e => e.id !== entry.id))) show(name);
        }));
      row.append(picture(c), text, acts);
      main.append(row);
    }
  }

  // -------------------------------------------------------------- import
  let importBusy = false;
  function take(list, source) {
    if (!list.length) throw Error('No character found in that ' + source + '.');
    for (const c of list) c.provenance = { ...c.provenance, filename: c.provenance?.filename ?? source };
    open(list[0], list);
    status(list.length > 1 ? `${list.length} characters found: choose one at the top of the sheet.` : 'Read. Check the sheet, then save it.');
  }
  // Spreadsheets laid out as a character sheet (Iain McEwen's 5e sheet): an .xlsx, or CSV tabs chosen together.
  const LAYOUT_UNKNOWN = 'This workbook is not laid out as a sheet I know (Iain McEwen\'s 5e Character Sheet, as published on 2026-10-21). Nothing was guessed. A table with a Name / Class / AC header row, or Field / Value rows, can be read as CSV.';
  async function readWorkbook(buffer) {
    const c = fromIainMcEwen(await readXlsx(buffer));
    if (!c) throw Error(LAYOUT_UNKNOWN);
    return [c];
  }
  async function readCsvTabs(files) {
    const sheets = [];
    for (const f of files) sheets.push({ name: f.name.replace(/\.(csv|tsv)$/i, ''), text: await f.text() });
    for (const sh of sheets) sh.cells = gridFromRows(parseDelimited(sh.text));
    if (sheets.some(sh => isIainMcEwen(sh.cells))) return [fromIainMcEwen(sheets)];
    if (files.length > 1) throw Error('Several CSV files are read together only as the tabs of one laid-out sheet. ' + LAYOUT_UNKNOWN);
    return parseSheet(sheets[0].text).map(c => reportFromFields(c, 'Spreadsheet'));
  }
  async function readFiles(files) {
    if (files.length === 1) return readFile(files[0]);
    if (importBusy) return;
    importBusy = true; status('Reading the tabs here in the browser…');
    try {
      if (!files.every(f => /\.(csv|tsv)$/i.test(f.name))) throw Error('Choose one file, or several CSV tabs of one sheet.');
      const list = await readCsvTabs(files);
      for (const c of list) c.provenance = { ...c.provenance, filename: files.map(f => f.name).join(', ') };
      take(list, 'those tabs');
    } catch (e) { status(e.message ?? String(e), true); }
    finally { importBusy = false; }
  }
  async function readFile(file) {
    if (importBusy) return;
    importBusy = true; status('Reading ' + file.name + ' here in the browser…');
    try {
      const ext = file.name.split('.').at(-1).toLowerCase();
      if (file.size > (ext === 'pdf' ? 20_000_000 : 2_000_000)) throw Error('That file is too large. Export just one character sheet.');
      let list;
      if (ext === 'xlsx') list = await readWorkbook(await file.arrayBuffer());
      else if (ext === 'pdf') {
        // the pictures in the PDF, and the portrait box when the sheet has a picture field (D&D Beyond, Mythastria)
        list = (await parsePDF(await file.arrayBuffer(), async (pdfjs, pdf, form) => ({ form, pictures: await pdfPictures(pdfjs, pdf, { box: portraitBox(form) }) })))
          // the Mythastria sheet comes back whole, its portrait from the known box; any other PDF by its fields and text
          .map(c => fromMythastriaSheet(c._pdf?.form, (c._pdf?.pictures ?? []).filter(p => p.label.startsWith('The portrait box'))) ?? pdfReport(c, c._pdf));
      } else {
        const text = await file.text();
        if (ext === 'xml') list = parseXML(text).map(hardenFG);
        else if (['csv', 'tsv'].includes(ext)) list = await readCsvTabs([file]);
        else if (ext === 'json') list = parseOtherJSON(text) ?? parseCharacterJSON(text);
        else list = parseText(text).map(c => reportFromFields(c, 'Text'));
      }
      for (const c of list) c.provenance = { ...c.provenance, filename: file.name };
      take(list, file.name);
    } catch (e) { status(e.message ?? String(e), true); }
    finally { importBusy = false; }
  }
  // A picture field of a known sheet (D&D Beyond's character image, the Mythastria sheet's Portrait): its page and box.
  function portraitBox(form) {
    for (const [name, items] of Object.entries(form ?? {})) {
      const it = items?.find(i => Array.isArray(i.rect) && Number.isInteger(i.page));
      if (it && /portrait|character ?image|picture|avatar|symbol image/i.test(name)) return { page: it.page + 1, rect: it.rect };
    }
    return null;
  }

  function drawImport() {
    para(main, 'Files are read here in your browser; nothing is sent anywhere else. Every import opens as a sheet for you to check before saving: it lists what was read, what was worked out, and what is missing.');
    const kinds = el('table', undefined, 'char-table'), body = el('tbody');
    kinds.append(body);
    for (const [from, how] of [
      ['Foundry VTT / The Forge', 'In Foundry: right-click the actor, Export Data (a .json file).'],
      ['D&D Beyond', 'The character JSON saved from its character service (.json), or its PDF export (.pdf).'],
      ['Fantasy Grounds', 'In FG: the character sheet, Export (a .xml file).'],
      ['Roll20', 'A character exported as JSON by a journal exporter such as VTTES (.json).'],
      ['Google Sheets: Iain McEwen\'s 5e sheet', 'Your copy: File, Download, Microsoft Excel (.xlsx); or its Character, Additional and Spells tabs as CSV, chosen together; or a public link below.'],
      ['Shard, other sheets', 'A PDF or CSV export, pasted cells or text; any other JSON is matched by field names.'],
      ['Mythastria', 'A sheet or collection exported from this page (.json), or the Mythastria character sheet PDF.']]) {
      const tr = el('tr'); tr.append(el('th', from), el('td', how)); body.append(tr);
    }
    main.append(kinds);
    const pick = field(main, 'Choose a character file (JSON, PDF, XML, Excel .xlsx, CSV/TSV or text; several CSV tabs of one sheet together)', '', () => {}, { type: 'file' });
    pick.accept = '.json,.pdf,.xml,.xlsx,.csv,.tsv,.txt';
    pick.multiple = true;
    pick.onchange = () => { if (pick.files.length) readFiles([...pick.files]); };
    let pasted = '';
    field(main, 'Or paste spreadsheet cells or sheet text', '', v => { pasted = v; }, { type: 'textarea', rows: 6 });
    main.append(button('Read the pasted text', () => {
      try {
        const t = pasted.trim();
        take(t.startsWith('{') ? parseOtherJSON(t) ?? parseCharacterJSON(t)
          : (t.includes('\t') || t.split('\n')[0].includes(',') ? parseSheet(t) : parseText(t)).map(c => reportFromFields(c, 'Pasted text')), 'pasted text');
      }
      catch (e) { status(e.message, true); }
    }));
    const sheets = fold(main, 'Google Sheets');
    para(sheets, 'A private sheet: copy the cells and paste them above, or use File → Download → CSV. This page never asks for your Google account.');
    let url = '';
    field(sheets, 'Public Google Sheets link', '', v => { url = v; }, { type: 'url' });
    sheets.append(button('Read the public sheet', async () => {
      try {
        status('Reading the public sheet…');
        const csvURL = sheetsCSVURL(url);
        // the whole workbook first (a laid-out sheet needs its Spells and Additional tabs too), then the one tab as CSV
        try {
          const book = await fetchFn(csvURL.replace(/export\?format=csv&gid=\d+$/, 'export?format=xlsx'), { credentials: 'omit', signal: AbortSignal.timeout(20000) });
          if (book.ok && /sheet|octet|zip/.test(book.headers.get('content-type') ?? '')) { take(await readWorkbook(await book.arrayBuffer()), 'Google sheet'); return; }
        } catch (e) { if (e.message === LAYOUT_UNKNOWN) throw e; /* then the CSV */ }
        const res = await fetchFn(csvURL, { credentials: 'omit', signal: AbortSignal.timeout(15000) });
        if (!res.ok) throw Error('The sheet cannot be read.');
        const text = await res.text();
        if (/^\s*</.test(text)) throw Error('The sheet answered with a sign-in page.');
        const cells = gridFromRows(parseDelimited(text));
        take(isIainMcEwen(cells) ? [fromIainMcEwen([{ name: 'Character', cells }])] : parseSheet(text).map(c => reportFromFields(c, 'Google Sheets')), 'Google sheet');
      } catch (e) { status('Could not read that sheet: ' + e.message + ' Download it as CSV or paste the cells instead.', true); }
    }));
  }

  // -------------------------------------------------------------- build (SRD 5.2.1, worked out by the service)
  const builder = createBuilder({ port, tokens, storage, status, onSheet(sheet, build) {
    draft = { ...structuredClone(sheet), id: build.id, build: structuredClone(build) };
    if (!tokens.some(t => t.id === draft.token_id)) draft.token_id = defaultArt(draft, tokens);
    const old = roster.find(c => c.id === draft.id);
    if (old?.reviewed_at) draft.reviewed_at = old.reviewed_at;
    builderErrors = []; candidates = []; pendingPhoto = null; flagsFor = null;
    show('sheet'); checkFlags();
    status(old ? 'The sheet is worked out again: Save changes to keep it.' : 'Worked out by the simulator service. Save the character to keep it.');
  } });
  function drawBuild() { builder.draw(main); }

  // -------------------------------------------------------------- the sheet (check, save, photos)
  function drawSheet() {
    if (!draft) { para(main, 'Open a saved character, import one, or build one.'); return; }
    if (candidates.length > 1) field(main, 'Characters in that file', String(Math.max(0, candidates.findIndex(c => c.id === draft.id))),
      v => { draft = structuredClone(candidates[+v]); show('sheet'); }, { options: candidates.map((c, i) => [String(i), c.name || 'Character ' + (i + 1)]) });
    const saved = roster.some(c => c.id === draft.id), stored = saved || refused.some(c => c.id === draft.id);
    const head = el('div', undefined, 'char-card'), text = el('div');
    text.append(el('h3', draft.name || 'Unnamed'));
    para(text, [draft.species, classLine(draft), draft.background].filter(Boolean).join(' · '));
    para(text, summaryLine(draft) + (saved ? '' : ' · not saved yet'));
    head.append(picture(draft), text, el('div'));
    main.append(head);
    if (builderErrors.length) {
      const box = el('div', undefined, 'char-warning bad');
      box.append(el('strong', 'Still to choose in the builder'));
      for (const t of builderErrors) para(box, t);
      box.append(button('Back to the builder', () => show('build')));
      main.append(box);
    }
    if (draft.warnings?.length) {
      const box = el('div', undefined, 'char-warning');
      for (const t of draft.warnings) para(box, t);
      main.append(box);
    }
    drawFlags();
    drawPortraitOffers();
    if (memberProblems.length && flagsFor === draft.id) {
      const box = el('div', undefined, 'char-warning bad');
      box.append(el('strong', 'Before it can fight in Play live'));
      for (const t of memberProblems) para(box, t);
      main.append(box);
    }
    main.append(renderSheet(draft, { head: false }));
    if (isBuilt(draft)) {
      const bar = el('div', undefined, 'char-actions');
      bar.append(button('Change in the builder', () => { builder.edit(draft.build); show('build'); }, ''));
      main.append(bar);
    }
    drawReport();

    const hand = fold(main, isBuilt(draft) ? 'Name and kind' : 'Edit the sheet by hand', !isBuilt(draft) && Boolean(draft.import?.missing?.length));
    const who = el('div', undefined, 'char-fields'); hand.append(who);
    field(who, 'Name', draft.name, v => { draft.name = v; });
    field(who, 'Type', draft.kind, v => { draft.kind = v; }, { options: [['pc', 'Player character'], ['npc', 'NPC / creature']] });
    if (!isBuilt(draft)) {
    field(who, 'Species', draft.species, v => { draft.species = v; });
    field(who, 'Background', draft.background, v => { draft.background = v; });
    field(who, 'Classes and levels (e.g. Fighter 3 / Wizard 1)', classLine(draft), v => {
      draft.classes = v.split('/').map(s => s.trim()).filter(Boolean).map(s => { const m = s.match(/^(.*?)(?:\s+(\d+))?$/); return { name: m[1], level: m[2] ? +m[2] : null }; });
    });
    field(who, 'Rules', draft.ruleset, v => { draft.ruleset = v; });

    const fight = fold(hand, 'In a fight', true);
    const nums = el('div', undefined, 'char-fields three'); fight.append(nums);
    for (const [k, label] of Object.entries({ hp_max: 'Hit points', ac: 'Armor Class', speed: 'Speed (ft)', attack_bonus: 'Attack bonus', damage_count: 'Damage dice', damage_die: 'Die size (d)', damage_bonus: 'Damage bonus', reach: 'Reach (ft)' }))
      field(nums, label, draft.combat?.[k], v => { draft.combat ??= {}; draft.combat[k] = v.trim() === '' ? null : Number(v); }, { type: 'number' });
    const scores = el('div', undefined, 'char-fields six'); fight.append(scores);
    for (const a of ABILITIES) field(scores, a.toUpperCase(), draft.abilities?.[a], v => { draft.abilities ??= {}; draft.abilities[a] = v === '' ? null : Number(v); }, { type: 'number' });

    const lists = fold(hand, 'Features, spells and equipment');
    for (const k of ['proficiencies', 'feats', 'features', 'spells', 'equipment']) {
      const values = draft[k] ?? [];
      field(lists, k[0].toUpperCase() + k.slice(1) + ' (one per line)', values.map(v => typeof v === 'string' ? v : v?.name ?? JSON.stringify(v)).join('\n'), v => {
        const old = new Map(values.filter(x => x && typeof x === 'object' && x.name).map(x => [x.name, x]));
        draft[k] = v.split('\n').map(s => s.trim()).filter(Boolean).map(s => old.get(s) ?? s);
      }, { type: 'textarea', rows: 4 });
    }
    field(lists, 'Notes', draft.notes, v => { draft.notes = v; }, { type: 'textarea' });
    }

    const art = fold(main, 'Token picture');
    if (saved) drawPhotos(art);
    else para(art, 'Save the character first, then add photos here; a photo shows on its token in Play live.');
    field(art, 'Fallback artwork (when there is no photo)', draft.token_id, v => { draft.token_id = v; draft.space_ft = (tokens.find(t => t.id === v)?.squares ?? 1) * 5; show('sheet'); },
      { options: [['', 'Choose artwork…'], ...tokens.map(t => [t.id, `${t.name} · ${t.footprint}`])] });

    const source = fold(main, 'Where the numbers came from');
    source.append(el('pre', draft.provenance?.raw || (draft.provenance?.kind === 'SRD builder' ? 'Made with the SRD 5.2.1 builder.' : 'Entered by hand.')));
    if (Object.keys(draft.provenance?.fields ?? {}).length) source.append(el('pre', JSON.stringify(draft.provenance.fields, null, 2)));

    drawTest();
    const acts = el('div', undefined, 'char-actions');
    acts.append(button(saved ? 'Save changes' : 'Save character', save, ''),
      button('Export this sheet', () => download(fileName(draft.name) + '.json', draft)),
      button('Mythastria sheet (PDF)', async () => {          // phase 5: printable and fillable; imports back
        status('Making the sheet…');
        try { download(fileName(draft.name) + '-sheet.pdf', await sheetPDF(draft, { photo: photoOf(photos, draft.id) ?? pendingPhoto })); status('The sheet is downloaded: print it, or fill it in a PDF reader and import it back.'); }
        catch (e) { status('The sheet could not be made: ' + e.message, true); }
      }));
    if (stored) acts.append(button('Delete', () => remove(draft)));
    acts.append(button('Put on the Min-max shelf', () => putOnShelf('minmax')), button('Put on the Fun builds shelf', () => putOnShelf('fun')));
    main.append(acts);
  }

  // Not SRD 5.2.1: the user's homebrew, kept on their sheet; the GM rules it (content policy, GM 2026-10-21).
  function drawFlags() {
    const flags = draft.homebrew ?? [];
    if (!flags.length) {
      if (flagsFor === draft.id) para(main, 'Everything named on this sheet is SRD 5.2.1.', 'char-note');
      return;
    }
    const box = el('div', undefined, 'char-warning');
    box.append(el('strong', `Not in SRD 5.2.1: ${flags.length}. Homebrew: the GM rules ${flags.length === 1 ? 'it' : 'them'}.`));
    const p = el('p');
    for (const f of flags) p.append(el('span', `${f.kind}: ${f.name}`, 'tag gm'), ' ');
    box.append(p);
    para(box, 'They stay on this sheet, in this browser only. Mythastria ships only its own and SRD 5.2.1 content, and never learns from imported sheets.');
    main.append(box);
  }

  // Pictures the file carried: offered for the token. An address on another site is fetched only when the GM clicks.
  function drawPortraitOffers() {
    const offers = (draft.import?.portraits ?? []).filter(p => p.value);
    if (!offers.length) return;
    const box = el('div', undefined, 'char-warning'), row = el('div', undefined, 'char-photos');
    box.append(el('strong', 'Pictures in the file'));
    const use = url => {
      if (roster.some(c => c.id === draft.id)) { keepPhotos(addPhoto(photos, draft.id, url)); status('The picture is on the token now.'); }
      else { pendingPhoto = url; show('sheet'); status('That picture goes on the token when you save the character.'); }
    };
    for (const p of offers) {
      const cell = el('div');
      if (p.kind === 'data') {
        const im = el('img'); im.src = p.value; im.alt = p.label; im.title = p.label;
        im.className = 'char-photo' + (pendingPhoto === p.value ? ' on' : '');
        cell.append(im, el('br'), button(pendingPhoto === p.value ? 'Chosen for the token' : 'Use this as the token picture?', () => use(p.value)));
      } else if (p.kind === 'url') {
        let host = 'that site';
        try { host = new URL(p.value).hostname; } catch { /* shown as it is */ }
        para(cell, `${p.label}: on ${host}. Not fetched.`);
        cell.append(button(`Fetch it from ${host}`, async () => {
          try { const url = await photoFromFile(await fetchPortrait(p.value, fetchFn)); p.kind = 'data'; p.value = url; show('sheet'); }
          catch (e) { status(e.message, true); }
        }));
      } else para(cell, `${p.label}: ${p.value}. That file is on the other program's side; if you have it, use Add photo under Token picture.`);
      row.append(cell);
    }
    box.append(row);
    main.append(box);
  }

  // What the importer read, worked out, could not find and did not use.
  function drawReport() {
    const r = draft.import;
    if (!r) return;
    const box = fold(main, `Import report: ${r.source}`, Boolean(r.missing?.length || r.worked?.length));
    const table = (title, rows, heads) => {
      if (!rows?.length) return;
      box.append(el('h2', title));
      const t = el('table', undefined, 'char-table'), head = el('tr'), body = el('tbody');
      for (const h of heads) head.append(el('th', h));
      t.append(head, body);
      for (const row of rows) { const tr = el('tr'); for (const v of row) tr.append(el('td', v)); body.append(tr); }
      box.append(t);
    };
    table('Read from the file', r.read, ['What', 'Value', 'From']);
    table('Worked out (check these)', r.worked, ['What', 'Value', 'How']);
    if (r.missing?.length) { box.append(el('h2', 'Missing: fill in on the sheet')); para(box, r.missing.join(', ')); }
    if (r.unmapped?.length) { box.append(el('h2', 'Not used')); for (const u of r.unmapped) para(box, u); }
  }

  // ------------------------------------------------------------ Test in Play live (phase 4)
  // GM 2026-10-21: "a first rate character builder that can quickly be tested in live": the character (saved first, so
  // Play live has it) on a practice map, alone or with pregens, at its own level; Play live starts the fight at once.
  // GM 2026-10-28 ("I only want to use characters saved in the saved characters tab"): the others who come along are the
  // other saved characters, each at its own level, not test characters.
  let hello = null, testOpen = false;
  const TEST_KEY = 'mythastria-test-fight';
  async function loadHello() {
    if (hello) return hello;
    try { const res = await fetchFn('/api/hello'); hello = res.ok ? await res.json() : null; } catch { hello = null; }
    return hello;
  }
  function drawTest() {
    const box = fold(main, 'Test in Play live', testOpen);
    box.parentElement.id = 'char-test';
    if (!hello) { para(box, 'Asking the simulator service for the maps…'); loadHello().then(h => { if (h && tab === 'sheet') show('sheet'); }); return; }
    let last = {};
    try { last = JSON.parse(storage?.getItem(TEST_KEY) || '{}') ?? {}; } catch { last = {}; }
    const maps = hello.scenarios ?? [], others = roster.filter(c => c.id !== draft.id);
    let map = maps.includes(last.map) ? last.map : maps.includes('test/live_keep.json') ? 'test/live_keep.json' : maps[0];
    let withThem = (last.with ?? []).filter(id => others.some(c => c.id === id));
    const level = (draft.classes ?? []).reduce((n, k) => n + (k.level || 0), 0) || 1;
    para(box, `${draft.name || 'This character'} fights at level ${level}. Each saved character who comes along fights at their own level.`);
    const row = el('div', undefined, 'char-fields');
    field(row, 'Practice map', map, v => { map = v; }, { options: maps });
    box.append(row);
    const who = el('fieldset', undefined, 'pick-box'); who.append(el('legend', 'Saved characters who come along (none: alone)'));
    const grid = el('div', undefined, 'pick-grid');
    for (const c of others.slice(0, 6)) {
      const lab = el('label', undefined, 'pick'), cb = el('input'); cb.type = 'checkbox'; cb.checked = withThem.includes(c.id);
      cb.onchange = () => { withThem = cb.checked ? [...withThem, c.id] : withThem.filter(x => x !== c.id); };
      lab.append(cb, ' ' + c.name); grid.append(lab);
    }
    if (!others.length) grid.append(el('p', 'No other saved characters.', 'note'));
    who.append(grid); box.append(who);
    box.append(button(roster.some(c => c.id === draft.id) ? 'Start the test fight →' : 'Save and start the test fight →', async () => {
      if (!(await save())) return;
      try { storage?.setItem(TEST_KEY, JSON.stringify({ map, with: withThem })); } catch { /* a convenience */ }
      const q = new URLSearchParams({ characters: [draft.id, ...withThem].join(','), level: String(Math.min(20, level)), scenario: map, start: '1' });
      location.href = 'play.html?' + q.toString();
    }, ''));
    para(box, 'Play live opens and starts the fight. Its Party box keeps the character, so Start live fight there tries it again.');
  }

  function drawPhotos(box) {
    const id = draft.id, cur = photos.sheets[id];
    const row = el('div', undefined, 'char-photos');
    for (const [i, url] of (cur?.photos ?? []).entries()) {
      const b = el('button', undefined, 'char-photo' + (cur.active === i ? ' on' : '')); b.type = 'button';
      b.title = cur.active === i ? 'On the token now' : 'Use this photo on the token';
      b.append(Object.assign(el('img'), { src: url, alt: `${draft.name}, photo ${i + 1}` }));
      b.onclick = () => keepPhotos(setActive(photos, id, i));
      row.append(b, button('Remove', () => keepPhotos(removePhoto(photos, id, i))));
    }
    if ((cur?.photos.length ?? 0) < MAX_PHOTOS) {
      const add = el('label', 'Add photo', 'photo-add'), input = Object.assign(el('input'), { type: 'file', accept: 'image/*', hidden: true });
      add.append(input);
      input.onchange = async () => { if (input.files[0]) keepPhotos(addPhoto(photos, id, await photoFromFile(input.files[0]))); };
      row.append(add);
    }
    box.append(row);
    para(box, `Up to ${MAX_PHOTOS} photos; the outlined one is on the token. Photos stay in this browser only.`);
  }

  function check() {
    if (builderErrors.length) throw Error('Finish the builder choices first (listed at the top).');
    if (draft.build?.format === BUILD_FORMAT && !isBuilt(draft)) throw Error('Open it in the builder and finish it there.');
    if (!draft.name?.trim()) throw Error('Give the character a name.');
    for (const [k, v] of Object.entries(draft.combat ?? {})) if (!Number.isInteger(v)) throw Error(`Fill in "${k.replace(/_/g, ' ')}" under In a fight (a whole number).`);
    if (!draft.token_id) draft.token_id = defaultArt(draft, tokens);
  }
  async function save() {
    try {
      check();
      draft.reviewed_at = new Date().toISOString();
      try { draft.homebrew = (await port.call({ op: 'character_check', character: draft })).flags ?? []; flagsFor = draft.id; } catch { /* kept as it was */ }
      const sheet = structuredClone(draft);                // picture data is not kept on the sheet (photos hold it)
      if (sheet.import?.portraits) sheet.import.portraits = sheet.import.portraits.map(p => (p.kind === 'data' ? { kind: 'data', label: p.label } : p));
      roster = (await port.call({ op: 'character_save', character: sheet })).characters;
      refused = refused.filter(r => r.id !== draft.id);
      if (pendingPhoto) { photos = addPhoto(photos, draft.id, pendingPhoto); savePhotos(photos, storage); pendingPhoto = null; }
      persist();
      status(draft.name + ' is saved.');
      show('sheet');
      return true;
    } catch (e) { status(e.message, true); return false; }
  }
  async function dropFromTable(id) {                          // the party Mythastria keeps (Play an adventure)
    try {
      const token = (await (await fetchFn('/api/hello')).json()).token;
      const post = (route, body) => fetchFn(route, { method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ...body, token }) }).then(r => r.json());
      const t = await loadTableParty(post);
      if (t?.characters?.some(k => k.id === id)) await post('/api/party', { op: 'save', party: { ...t, characters: t.characters.filter(k => k.id !== id) } });
    } catch { /* no service: only this browser's roster */ }
  }
  async function remove(c) {                                 // a saved character (its card, or its open sheet)
    if (!confirm(`Delete ${c.name}? Its photos go too. Export it first if you may want it again.`)) return;
    try {
      if (roster.some(k => k.id === c.id)) roster = (await port.call({ op: 'character_delete', character_id: c.id })).characters;
      refused = refused.filter(r => r.id !== c.id);
      persist();
      if (photos.sheets[c.id]) { const next = { sheets: { ...photos.sheets }, links: { ...photos.links } }; delete next.sheets[c.id]; photos = next; savePhotos(photos, storage); }
      await dropFromTable(c.id);
      status(c.name + ' was deleted.');
      if (draft?.id === c.id) draft = null;
      show('roster');
    } catch (e) { status(e.message, true); }
  }

  await loadRoster();
  addEventListener('storage', e => { if (e.key === ROSTER_KEY || e.key === 'mythastria-photos-v1') { photos = loadPhotos(storage); if (e.key === ROSTER_KEY) loadRoster().then(() => show(tab)); else show(tab); } });
  show(new URLSearchParams(location.search).get('tab') in TABS ? new URLSearchParams(location.search).get('tab') : 'roster');
  return { show, open, get roster() { return roster; }, get draft() { return draft; } };
}

if (typeof document !== 'undefined' && document.getElementById('characters-app')) createCharactersPage().catch(e => {
  const s = document.getElementById('char-status'); if (s) { s.textContent = 'The Characters page could not start: ' + e.message; s.className = 'error'; }
});
