// CHARACTERS-01 phase 5 (GM 2026-10-21: an official Mythastria character sheet): the Mythastria character sheet, a
// printable, fillable two-page PDF (US Letter) of our own design: the Mythastria logo, the SRD 5.2.1 sheet fields and a
// portrait box (a picture field holding the character's token photo). Made here in the browser by a small PDF writer
// (no PDF library), filled from a saved character, or blank for pencil and paper.
//
// The sheet carries the character it was made from (a hidden field, mythastria_data), so importing it back restores
// everything; anything changed in the PDF's fields since (a PDF reader can edit them) wins and is reported. A sheet filled
// by hand without that field is read field by field. The portrait comes back from the known box (field "Portrait").
// Design and code: (c) 2026 islandfunster, MIT License (see LICENSE). Game terms from SRD 5.2.1 (CC-BY-4.0).
export const SHEET_MARK = 'Mythastria character sheet 1';
const W = 612, H = 792;
const INK = '0.13 0.12 0.10', BRASS = '0.62 0.49 0.25', SOFT = '0.45 0.42 0.36', PAPER = '0.985 0.975 0.95';
const AB = [['str', 'STR', 'Strength'], ['dex', 'DEX', 'Dexterity'], ['con', 'CON', 'Constitution'], ['int', 'INT', 'Intelligence'], ['wis', 'WIS', 'Wisdom'], ['cha', 'CHA', 'Charisma']];
export const SKILLS = { Acrobatics: 'dex', 'Animal Handling': 'wis', Arcana: 'int', Athletics: 'str', Deception: 'cha', History: 'int', Insight: 'wis', Intimidation: 'cha', Investigation: 'int', Medicine: 'wis', Nature: 'int', Perception: 'wis', Performance: 'cha', Persuasion: 'cha', Religion: 'int', 'Sleight of Hand': 'dex', Stealth: 'dex', Survival: 'wis' };
const ORD = ['', '1st', '2nd', '3rd', '4th', '5th', '6th', '7th', '8th', '9th'];
export const skillField = s => 'Skill_' + s.replace(/[^A-Za-z]/g, '');
const signed = n => (n === null || n === undefined || n === '' ? '' : (Number(n) >= 0 ? '+' : '') + n);
const mod = s => Math.floor((Number(s) - 10) / 2);

// ------------------------------------------------------------------ the values a character puts in the sheet's fields
export function sheetValues(c) {
  if (!c) return {};
  const d = c.derived ?? null, k = c.combat ?? {}, v = {};
  const level = d?.level ?? (c.classes ?? []).reduce((n, x) => n + (x.level || 0), 0);
  const pb = d?.proficiency_bonus ?? (level ? 2 + Math.floor((level - 1) / 4) : null);
  v.Name = c.name ?? '';
  v.Species = [c.species, c.lineage && !String(c.species).includes(c.lineage) ? `(${c.lineage})` : ''].filter(Boolean).join(' ');
  v.Class = (c.classes ?? []).map(x => `${x.name}${x.level ? ' ' + x.level : ''}${x.subclass ? ' (' + x.subclass + ')' : ''}`).join(' / ');
  v.Background = c.background ?? ''; v.Size = c.size ?? ''; v.Level = level ? String(level) : ''; v.Rules = c.ruleset ?? 'SRD 5.2.1';
  const saves = new Set(c.saves ?? []);
  for (const [a, A] of AB) {
    const s = c.abilities?.[a];
    v[A] = s ?? ''; v[A + '_mod'] = s != null ? signed(mod(s)) : '';
    v[A + '_save'] = d?.saves?.[a] != null ? signed(d.saves[a]) : s != null ? signed(mod(s) + (saves.has(a) && pb ? pb : 0)) : '';
    v[A + '_saveprof'] = saves.has(a) ? '•' : '';
  }
  v.AC = k.ac ?? ''; v.HPMax = k.hp_max ?? ''; v.HPCurrent = ''; v.HPTemp = ''; v.Speed = k.speed != null ? `${k.speed} ft` : '';
  v.Initiative = d ? signed(d.initiative) : c.abilities?.dex != null ? signed(mod(c.abilities.dex)) : '';
  v.Proficiency = pb ? signed(pb) : ''; v.Passive = d?.passive_perception ?? '';
  v.HitDice = d?.hit_dice ? Object.entries(d.hit_dice).map(([die, n]) => `${n}${die}`).join(' + ') : '';
  v.AttacksPer = d?.attacks_per_action ? String(d.attacks_per_action) : '';
  const atks = d?.attacks ?? (k.attack_bonus != null ? [{ name: (c.equipment ?? []).find(x => typeof x === 'string') ?? 'Attack', atk: k.attack_bonus, count: k.damage_count ?? 1, die: k.damage_die, bonus: k.damage_bonus, reach: k.reach ?? 5 }] : []);
  atks.slice(0, 6).forEach((a, i) => {
    const n = i + 1;
    v[`Atk${n}_Name`] = a.name; v[`Atk${n}_Bonus`] = a.atk != null ? signed(a.atk) : a.save_dc ? `DC ${a.save_dc}` : '';
    v[`Atk${n}_Damage`] = `${a.count}d${a.die}${a.bonus ? (a.bonus > 0 ? '+' : '') + a.bonus : ''}${a.type ? ' ' + a.type : ''}`;
    v[`Atk${n}_Notes`] = [`${a.reach} ft`, a.mastery ? a.mastery : '', a.beams > 1 ? a.beams + ' beams' : ''].filter(Boolean).join(', ');
  });
  const profs = new Set((c.proficiencies ?? []).map(p => String(p).replace(' (expertise)', '')));
  const expert = new Set((c.proficiencies ?? []).filter(p => String(p).endsWith('(expertise)')).map(p => String(p).replace(' (expertise)', '')));
  for (const [s, a] of Object.entries(SKILLS)) {
    const b = d?.skills?.[s] ?? (c.abilities?.[a] != null ? mod(c.abilities[a]) + (expert.has(s) ? 2 * (pb ?? 2) : profs.has(s) ? pb ?? 2 : 0) : null);
    v[skillField(s)] = b != null ? signed(b) : ''; v[skillField(s) + '_prof'] = expert.has(s) ? '••' : profs.has(s) ? '•' : '';
  }
  v.Proficiencies = [['Armor and weapons', (c.proficiencies ?? []).filter(p => !SKILLS[String(p).replace(' (expertise)', '')]).join(', ')], ['Tools', (c.tools ?? []).join(', ')], ['Languages', (c.languages ?? []).join(', ')]].filter(([, x]) => x).map(([l, x]) => `${l}: ${x}`).join('\n');
  v.Senses = [c.senses, (c.damage_resistances ?? []).length ? 'Resistances: ' + c.damage_resistances.join(', ') : ''].filter(Boolean).join('\n');
  v.Resources = (d?.resources ?? []).map(([n, x]) => `${n}: ${x}`).join('\n');
  v.Feats = (c.feats ?? []).map(f => typeof f === 'string' ? f : f?.name).join(', ');
  v.Equipment = (c.equipment ?? []).map(e => typeof e === 'string' ? e : e?.name).join(', ');
  const casting = d?.casting ?? [];
  v.SpellClass = casting.map(x => `${x.class} (${x.ability.toUpperCase()})`).join(', ');
  v.SpellDC = casting.map(x => x.dc).join(' / '); v.SpellAtk = casting.map(x => signed(x.attack)).join(' / ');
  v.Pact = d?.pact ? `${d.pact.slots} slot${d.pact.slots > 1 ? 's' : ''} of level ${d.pact.level}` : '';
  for (let i = 1; i <= 9; i++) v['Slots' + i] = d?.slots?.[i - 1] ? String(d.slots[i - 1]) : '';
  for (let i = 0; i <= 9; i++) v['Spells' + i] = (c.spells ?? []).filter(s => (typeof s === 'string' ? (i === 0 ? false : i === 1) : (s.level ?? 1) === i)).map(s => typeof s === 'string' ? s : s.name + (s.always ? '*' : '')).join(', ');
  const gm = new Set((c.gm_rules ?? []).map(String));
  const byLv = d?.features_by_level ?? [];
  v.Features = (byLv.length ? byLv.map(([lv, src, n]) => `${n} (${src} ${lv})${gm.has(n) ? ' [GM rules]' : ''}`) : (c.features ?? []).map(f => (typeof f === 'string' ? f : f?.name) + (gm.has(f) ? ' [GM rules]' : ''))).join('; ');
  v.Notes = c.notes ?? '';
  return v;
}

// ------------------------------------------------------------------ text
// Helvetica widths (thousandths of an em) for ASCII 32-126; other characters count as 556
const HW = [278, 278, 355, 556, 556, 889, 667, 191, 333, 333, 389, 584, 278, 333, 278, 278, 556, 556, 556, 556, 556, 556, 556, 556, 556, 556, 278, 278, 584, 584, 584, 556, 1015, 667, 667, 722, 722, 667, 611, 778, 722, 278, 500, 667, 556, 833, 722, 778, 667, 778, 722, 667, 611, 722, 667, 944, 667, 667, 611, 278, 278, 278, 469, 556, 333, 556, 556, 500, 556, 556, 278, 556, 556, 222, 222, 500, 222, 833, 556, 556, 556, 556, 333, 500, 278, 556, 500, 722, 500, 500, 500, 334, 260, 334, 584];
const width = (s, size) => [...s].reduce((n, ch) => n + (HW[ch.charCodeAt(0) - 32] ?? 556), 0) * size / 1000;
const WIN = { '’': 0x92, '‘': 0x91, '“': 0x93, '”': 0x94, '•': 0x95, '–': 0x96, '—': 0x97, '×': 0xd7, '·': 0xb7, '…': 0x85 };
function winAnsi(s) {                     // a PDF literal string in WinAnsiEncoding (the standard fonts' encoding)
  let out = '(';
  for (const ch of String(s)) {
    let c = ch.charCodeAt(0);
    if (WIN[ch]) c = WIN[ch]; else if (c > 255) c = 63;
    out += c === 40 || c === 41 || c === 92 ? '\\' + ch : c < 32 || c > 126 ? '\\' + c.toString(8).padStart(3, '0') : ch;
  }
  return out + ')';
}
function utf16(s) {                       // a PDF text string (field values): UTF-16BE with its byte-order mark
  let hex = 'FEFF';
  for (const ch of String(s)) for (const unit of ch.length === 2 ? [ch.charCodeAt(0), ch.charCodeAt(1)] : [ch.charCodeAt(0)]) hex += unit.toString(16).padStart(4, '0');
  return '<' + hex.toUpperCase() + '>';
}
function wrap(text, w, size) {
  const lines = [];
  for (const para of String(text).split(/\n/)) {
    let line = '';
    for (const word of para.split(/\s+/).filter(Boolean)) {
      const next = line ? line + ' ' + word : word;
      if (width(next, size) <= w || !line) line = next; else { lines.push(line); line = word; }
    }
    lines.push(line);
  }
  return lines;
}

// ------------------------------------------------------------------ a tiny PDF writer
class Pdf {
  constructor() { this.objs = []; }
  add(body) { this.objs.push(body); return this.objs.length; }
  set(n, body) { this.objs[n - 1] = body; }
  reserve() { return this.add(null); }
  stream(dict, data) {              // data: string (bytes as char codes) or Uint8Array
    const bytes = typeof data === 'string' ? Uint8Array.from(data, ch => ch.charCodeAt(0) & 255) : data;
    return this.add({ dict, bytes });
  }
  bytes(rootRef, infoRef) {
    const enc = new TextEncoder(), parts = [], offsets = [];
    let len = 0;
    const put = x => { const b = typeof x === 'string' ? Uint8Array.from(x, ch => ch.charCodeAt(0) & 255) : x; parts.push(b); len += b.length; };
    put('%PDF-1.7\n%\xe2\xe3\xcf\xd3\n');
    this.objs.forEach((o, i) => {
      offsets.push(len);
      if (o && o.bytes) { put(`${i + 1} 0 obj\n<< ${o.dict} /Length ${o.bytes.length} >>\nstream\n`); put(o.bytes); put('\nendstream\nendobj\n'); }
      else put(`${i + 1} 0 obj\n${o ?? 'null'}\nendobj\n`);
    });
    const xref = len;
    put(`xref\n0 ${this.objs.length + 1}\n0000000000 65535 f \n` + offsets.map(o => String(o).padStart(10, '0') + ' 00000 n \n').join(''));
    put(`trailer\n<< /Size ${this.objs.length + 1} /Root ${rootRef} 0 R /Info ${infoRef} 0 R >>\nstartxref\n${xref}\n%%EOF\n`);
    void enc;
    const out = new Uint8Array(len); let at = 0;
    for (const p of parts) { out.set(p, at); at += p.length; }
    return out;
  }
}

// A picture (data: URL or image URL) as a JPEG for the PDF: drawn on a canvas over the paper colour, at most `px` wide.
async function jpeg(src, px, fill = '#fbf9f2') {
  try {
    const img = await new Promise((ok, no) => { const i = new Image(); i.onload = () => ok(i); i.onerror = no; i.src = src; });
    const k = Math.min(1, px / Math.max(img.naturalWidth, img.naturalHeight)), cv = document.createElement('canvas');
    cv.width = Math.max(1, Math.round(img.naturalWidth * k)); cv.height = Math.max(1, Math.round(img.naturalHeight * k));
    const ctx = cv.getContext('2d'); ctx.fillStyle = fill; ctx.fillRect(0, 0, cv.width, cv.height); ctx.drawImage(img, 0, 0, cv.width, cv.height);
    const bin = atob(cv.toDataURL('image/jpeg', .9).split(',')[1]);
    return { w: cv.width, h: cv.height, bytes: Uint8Array.from(bin, ch => ch.charCodeAt(0)) };
  } catch { return null; }
}

// ------------------------------------------------------------------ the sheet
export async function sheetPDF(c = null, { photo = null, logo = 'logo.png' } = {}) {
  const v = sheetValues(c), pdf = new Pdf();
  const catalog = pdf.reserve(), pagesRef = pdf.reserve();
  const helv = pdf.add('<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>');
  const bold = pdf.add('<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>');
  const serif = pdf.add('<< /Type /Font /Subtype /Type1 /BaseFont /Times-Bold /Encoding /WinAnsiEncoding >>');
  const fonts = `/Font << /Helv ${helv} 0 R /HeBo ${bold} 0 R /TiBo ${serif} 0 R >>`;
  const logoImg = await jpeg(logo, 240), photoImg = photo ? await jpeg(photo, 420, '#ffffff') : null;
  const logoRef = logoImg ? pdf.stream(`/Type /XObject /Subtype /Image /Width ${logoImg.w} /Height ${logoImg.h} /ColorSpace /DeviceRGB /BitsPerComponent 8 /Filter /DCTDecode`, logoImg.bytes) : null;
  const photoRef = photoImg ? pdf.stream(`/Type /XObject /Subtype /Image /Width ${photoImg.w} /Height ${photoImg.h} /ColorSpace /DeviceRGB /BitsPerComponent 8 /Filter /DCTDecode`, photoImg.bytes) : null;
  const fields = [], pages = [];

  function page(draw) {
    const ops = [], annots = [], self = pdf.reserve();
    const P = {
      ops, annots, self,
      y: top => H - top,
      text(x, top, s, size = 7, font = 'Helv', color = SOFT) { ops.push(`BT /${font} ${size} Tf ${color} rg ${x} ${H - top} Td ${winAnsi(s)} Tj ET`); },
      rect(x, top, w, h, { stroke = BRASS, fill = null, lw = .6, r = 0 } = {}) {
        const y = H - top - h;
        ops.push(`q ${lw} w ${stroke} RG ${fill ? fill + ' rg ' : ''}${x} ${y} ${w} ${h} re ${fill ? 'B' : 'S'} Q`);
      },
      line(x1, t1, x2, t2, color = BRASS, lw = .6) { ops.push(`q ${lw} w ${color} RG ${x1} ${H - t1} m ${x2} ${H - t2} l S Q`); },
      // a fillable text field with its label above, its value drawn (so any reader prints it) and kept as /V
      field(name, x, top, w, h, { label = null, size = 9, multi = false, align = 0, boxed = true, labelSize = 6 } = {}) {
        if (label) P.text(x + 1, top - 2, label.toUpperCase(), labelSize, 'HeBo', SOFT);
        if (boxed) P.rect(x, top, w, h, { stroke: '0.78 0.72 0.6', fill: '1 1 1', lw: .5 });
        const value = v[name] ?? '', y = H - top - h;
        const fs = multi ? size : Math.min(size, Math.max(5, h - 6));
        let ap = '/Tx BMC q BT /Helv ' + fs + ' Tf ' + INK + ' rg ';
        if (String(value)) {
          if (multi) {
            const lines = wrap(value, w - 6, fs), lead = fs * 1.18;
            let ty = h - 2 - fs;
            ap += `3 ${ty} Td ${lead} TL `;
            for (const ln of lines) { if (ty < 1) break; ap += `${winAnsi(ln)} Tj T* `; ty -= lead; }
          } else {
            const s = String(value), tw = width(s, fs), tx = align === 1 ? Math.max(2, (w - tw) / 2) : 3;
            ap += `${tx} ${(h - fs * .72) / 2} Td ${winAnsi(s)} Tj `;
          }
        }
        ap += 'ET Q EMC';
        const apRef = pdf.stream(`/Type /XObject /Subtype /Form /BBox [0 0 ${w} ${h}] /Resources << ${fonts} >>`, ap);
        const ref = pdf.add(`<< /Type /Annot /Subtype /Widget /FT /Tx /T ${utf16(name)} /V ${utf16(value)} /DA (/Helv ${multi ? fs : 0} Tf 0 g) /Q ${align} /Rect [${x} ${y} ${x + w} ${y + h}] /F 4 /P ${self} 0 R /Ff ${multi ? 4096 : 0} /AP << /N ${apRef} 0 R >> /MK << >> >>`);
        annots.push(ref); fields.push(ref);
      },
      image(ref, x, top, w, h) { ops.push(`q ${w} 0 0 ${h} ${x} ${H - top - h} cm /${ref === logoRef ? 'Logo' : 'Im'} Do Q`); },
    };
    draw(P);
    pages.push(P);
    return P;
  }

  const frame = P => {
    P.rect(0, 0, W, H, { stroke: PAPER, fill: PAPER, lw: 0 });
    P.rect(22, 22, W - 44, H - 44, { lw: 1.2 }); P.rect(26, 26, W - 52, H - 52, { lw: .4 });
    P.text(34, H - 30, 'Mythastria Character Sheet (c) 2026 islandfunster, MIT License. Game terms from the System Reference Document 5.2.1 (CC-BY-4.0).', 5.5, 'Helv', SOFT);
  };

  // page 1: who, abilities, the fight, skills
  page(P => {
    frame(P);
    if (logoRef) P.image(logoRef, 34, 34, 56, 56);
    P.text(98, 54, 'MYTHASTRIA', 24, 'TiBo', INK);
    P.text(99, 66, 'CHARACTER SHEET  ·  SRD 5.2.1', 7, 'HeBo', BRASS);
    P.field('Name', 98, 80, 310, 20, { label: 'Name', size: 13 });
    P.field('Species', 98, 112, 150, 17, { label: 'Species' });
    P.field('Class', 253, 112, 155, 17, { label: 'Class and levels (subclass)', size: 8 });
    P.field('Background', 98, 140, 95, 17, { label: 'Background' });
    P.field('Size', 198, 140, 55, 17, { label: 'Size' });
    P.field('Level', 258, 140, 40, 17, { label: 'Level', align: 1 });
    P.field('Rules', 303, 140, 105, 17, { label: 'Rules' });
    // the portrait box: a picture field; the label sits outside it so an empty box reads as empty
    P.text(420, 32, 'PORTRAIT (THE TOKEN PICTURE)', 6, 'HeBo', SOFT);
    P.rect(420, 36, 158, 178, { lw: 1 });
    {
      const x = 421, top = 37, w = 156, h = 176, y = H - top - h;
      let ap = '';
      if (photoRef) {
        const k = Math.min(w / photoImg.w, h / photoImg.h), iw = photoImg.w * k, ih = photoImg.h * k;
        ap = `q ${iw.toFixed(2)} 0 0 ${ih.toFixed(2)} ${((w - iw) / 2).toFixed(2)} ${((h - ih) / 2).toFixed(2)} cm /Im Do Q`;
      }
      const apRef = pdf.stream(`/Type /XObject /Subtype /Form /BBox [0 0 ${w} ${h}] /Resources << ${photoRef ? `/XObject << /Im ${photoRef} 0 R >>` : ''} >>`, ap);
      const ref = pdf.add(`<< /Type /Annot /Subtype /Widget /FT /Btn /Ff 65536 /T ${utf16('Portrait')} /Rect [${x} ${y} ${x + w} ${y + h}] /F 4 /P ${P.self} 0 R /AP << /N ${apRef} 0 R >> /MK << /TP 1 >> >>`);
      P.annots.push(ref); fields.push(ref);
    }
    // abilities
    AB.forEach(([, A, name], i) => {
      const top = 168 + i * 84;
      P.rect(34, top, 74, 78, { lw: .8, fill: '1 1 1' });
      P.text(38, top + 10, name.toUpperCase(), 6, 'HeBo', BRASS);
      P.field(A, 46, top + 14, 50, 24, { size: 16, align: 1, boxed: false });
      P.field(A + '_mod', 52, top + 40, 38, 14, { size: 10, align: 1 });
      P.text(38, top + 66, 'SAVE', 5.5, 'HeBo', SOFT);
      P.field(A + '_saveprof', 56, top + 59, 12, 10, { size: 8, align: 1 });
      P.field(A + '_save', 70, top + 59, 32, 12, { size: 8, align: 1 });
    });
    // the fight
    const box = (name, label, x, top, w = 64) => { P.field(name, x, top, w, 26, { label, size: 13, align: 1 }); };
    box('AC', 'Armor Class', 118, 168); box('HPMax', 'Hit points', 186, 168); box('HPCurrent', 'Current HP', 254, 168); box('HPTemp', 'Temp HP', 322, 168, 86);
    box('Speed', 'Speed', 118, 214); box('Initiative', 'Initiative', 186, 214); box('Proficiency', 'Proficiency', 254, 214); box('Passive', 'Passive Perception', 322, 214, 86);
    P.field('HitDice', 118, 258, 140, 16, { label: 'Hit dice' });
    P.field('AttacksPer', 263, 258, 145, 16, { label: 'Attacks per Attack action', align: 1 });
    P.text(119, 290, 'ATTACKS AND CANTRIPS', 6.5, 'HeBo', BRASS);
    for (const [x, lab] of [[119, 'NAME'], [211, 'TO HIT / DC'], [255, 'DAMAGE'], [347, 'NOTES']]) P.text(x, 299, lab, 5.5, 'HeBo', SOFT);
    for (let n = 1; n <= 6; n++) {
      const top = 302 + (n - 1) * 17;
      P.field(`Atk${n}_Name`, 118, top, 90, 15, { size: 8 }); P.field(`Atk${n}_Bonus`, 210, top, 42, 15, { size: 8, align: 1 });
      P.field(`Atk${n}_Damage`, 254, top, 90, 15, { size: 7.5 }); P.field(`Atk${n}_Notes`, 346, top, 62, 15, { size: 6.5 });
    }
    P.text(119, 418, 'SKILLS  (• PROFICIENT, •• EXPERTISE)', 6.5, 'HeBo', BRASS);
    Object.entries(SKILLS).forEach(([s, a], i) => {
      const col = i < 9 ? 0 : 1, row = i % 9, x = 118 + col * 147, top = 424 + row * 26;
      P.field(skillField(s) + '_prof', x, top, 14, 18, { size: 9, align: 1 });
      P.text(x + 18, top + 12, `${s} (${a.toUpperCase()})`, 7, 'Helv', INK);
      P.field(skillField(s), x + 108, top, 32, 18, { size: 9, align: 1 });
    });
    // right column
    P.field('Proficiencies', 420, 240, 158, 152, { label: 'Proficiencies, tools, languages', multi: true, size: 7 });
    P.field('Senses', 420, 406, 158, 40, { label: 'Senses and resistances', multi: true, size: 7 });
    P.field('Resources', 420, 460, 158, 200, { label: 'Uses and resources', multi: true, size: 7 });
    P.field('Feats', 34, 682, 544, 18, { label: 'Feats', size: 8 });
    P.field('Equipment', 34, 712, 544, 44, { label: 'Equipment', multi: true, size: 7.5 });
  });

  // page 2: spells, features, notes
  page(P => {
    frame(P);
    if (logoRef) P.image(logoRef, 34, 34, 32, 32);
    P.text(72, 52, 'MYTHASTRIA', 14, 'TiBo', INK);
    P.text(160, 52, String(v.Name || ''), 12, 'HeBo', INK);
    P.text(72, 62, 'SPELLS, FEATURES AND NOTES', 6.5, 'HeBo', BRASS);
    P.field('SpellClass', 34, 84, 220, 18, { label: 'Spellcasting class (ability)', size: 8 });
    P.field('SpellDC', 260, 84, 70, 18, { label: 'Spell save DC', align: 1 });
    P.field('SpellAtk', 336, 84, 70, 18, { label: 'Spell attack', align: 1 });
    P.field('Pact', 412, 84, 166, 18, { label: 'Pact Magic', size: 8 });
    P.text(35, 116, 'SPELL SLOTS', 6.5, 'HeBo', BRASS);
    for (let i = 1; i <= 9; i++) { const x = 34 + (i - 1) * 60.5; P.field('Slots' + i, x, 128, 54, 18, { label: ORD[i], align: 1 }); }
    P.field('Spells0', 34, 164, 544, 40, { label: 'Cantrips', multi: true, size: 7.5 });
    for (let i = 1; i <= 9; i++) {
      const col = (i - 1) % 3, row = Math.floor((i - 1) / 3), x = 34 + col * 183, top = 222 + row * 84;
      P.field('Spells' + i, x, top, 178, 72, { label: `Level ${i} spells`, multi: true, size: 7 });
    }
    P.text(35, 474, '* always prepared', 5.5, 'Helv', SOFT);
    P.field('Features', 34, 486, 544, 190, { label: 'Features and traits ([GM rules] = the simulator does not play it; the GM rules it)', multi: true, size: 7 });
    P.field('Notes', 34, 690, 544, 66, { label: 'Notes', multi: true, size: 7.5 });
  });

  // the character itself (hidden): importing the sheet back restores it, then takes any field changed since
  const exported = {};
  for (const [k, x] of Object.entries(v)) exported[k] = String(x ?? '');
  const data = c ? { format: 'mythastria-sheet-data/1', character: lighten(c), fields: exported } : null;
  for (const [name, value] of [['mythastria_sheet', SHEET_MARK], ['mythastria_data', data ? b64(JSON.stringify(data)) : '']]) {
    const ref = pdf.add(`<< /Type /Annot /Subtype /Widget /FT /Tx /T ${utf16(name)} /V ${utf16(value)} /Rect [0 0 0 0] /F 2 /P ${pages[0].self} 0 R /Ff 1 >>`);
    pages[0].annots.push(ref); fields.push(ref);
  }

  for (const P of pages) {
    const content = pdf.stream('', P.ops.join('\n'));
    const xo = [logoRef ? `/Logo ${logoRef} 0 R` : ''].join(' ');
    pdf.set(P.self, `<< /Type /Page /Parent ${pagesRef} 0 R /MediaBox [0 0 ${W} ${H}] /Contents ${content} 0 R /Resources << ${fonts} /XObject << ${xo} >> >> /Annots [${P.annots.map(r => r + ' 0 R').join(' ')}] >>`);
  }
  pdf.set(pagesRef, `<< /Type /Pages /Kids [${pages.map(P => P.self + ' 0 R').join(' ')}] /Count ${pages.length} >>`);
  pdf.set(catalog, `<< /Type /Catalog /Pages ${pagesRef} 0 R /AcroForm << /Fields [${fields.map(r => r + ' 0 R').join(' ')}] /NeedAppearances false /DA (/Helv 0 Tf 0 g) /DR << /Font << /Helv ${helv} 0 R >> >> >> >>`);
  const info = pdf.add(`<< /Title ${utf16((c?.name ? c.name + ' - ' : '') + 'Mythastria character sheet')} /Creator ${utf16('Mythastria Characters page')} /Producer ${utf16('Mythastria (MIT)')} >>`);
  return new Blob([pdf.bytes(catalog, info)], { type: 'application/pdf' });
}
function b64(s) { const bytes = new TextEncoder().encode(s); let bin = ''; for (let i = 0; i < bytes.length; i += 0x8000) bin += String.fromCharCode(...bytes.subarray(i, i + 0x8000)); return btoa(bin); }
function unb64(s) { const bin = atob(s); return new TextDecoder().decode(Uint8Array.from(bin, ch => ch.charCodeAt(0))); }
// the sheet without its import extract (the PDF carries the character, not the file it once came from)
function lighten(c) { const out = structuredClone(c); if (out.provenance) { delete out.provenance.raw; delete out.provenance.fields; } if (out.import) delete out.import.portraits; return out; }

// ------------------------------------------------------------------ reading a Mythastria sheet back
// form: pdf.js getFieldObjects(). Returns {character, changed: [[field, was, now]], hand: bool} or null (another PDF).
export function readSheet(form) {
  const val = n => { const it = form?.[n]?.find(i => i.value !== undefined && i.value !== null); return it ? String(it.value) : ''; };
  if (val('mythastria_sheet') !== SHEET_MARK) return null;
  let data = null;
  try { data = val('mythastria_data') ? JSON.parse(unb64(val('mythastria_data'))) : null; } catch { data = null; }
  const now = {};
  for (const name of Object.keys(form)) if (!['mythastria_sheet', 'mythastria_data', 'Portrait'].includes(name)) now[name] = val(name);
  if (data?.format === 'mythastria-sheet-data/1' && data.character?.format === 'isles-character/1') {
    const changed = Object.entries(now).filter(([k, x]) => (data.fields[k] ?? '') !== x).map(([k, x]) => [k, data.fields[k] ?? '', x]);
    return { character: data.character, changed, now, hand: false };
  }
  return { character: null, changed: [], now, hand: true };
}
