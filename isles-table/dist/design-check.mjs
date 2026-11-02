// DESIGN-CHECK-01 (GM 2026-10-26: "create a design tool that looks at playability so it can be intuitive to play";
// then "Aesthetics. Let's start adding shading, style, consistency with menus and tabs"): every Mythastria page is
// opened in a frame, and each kind of control on it (buttons, menus, tabs, panels, headings, fields) is read as the
// browser draws it. Controls of one kind that look the same are grouped; a kind with many looks is where the pages
// drift apart. Colours that are not the skin's own, and buttons or panels without shading, are flagged. Read only.
export const PAGES = ['index', 'adventure', 'play', 'characters', 'replay', 'stage', 'region', 'oneshot', 'remix', 'spells', 'docs',
  'rules-social', 'join'];
export const KINDS = {
  button: 'button, .site-nav a, a.sim-link',
  menu: 'select, .tray-menu>summary, details>summary',
  tab: '[role=tab], [class*="tab"]:is(button,a)',
  panel: 'section, dialog, aside>section, .panel, .card',
  heading: 'h1, h2, h3',
  field: 'input:not([type=checkbox]):not([type=radio]):not([type=hidden]), textarea',
};
const SKIN_VARS = ['--ink', '--panel', '--line', '--paper', '--muted', '--brass', '--rust', '--sage', '--ok', '--no', '--ally', '--well',
  '--button', '--surface-low', '--band', '--face',
  '--gold-hi', '--quiet', '--pressed', '--row-hover', '--friend', '--foe'];   // pass 3: the Gilded skin's own names too

const rgb = c => { const m = /rgba?\(([^)]+)\)/.exec(c || ''); if (!m) return null; const p = m[1].split(/[ ,/]+/).filter(Boolean).map(Number); return { r: p[0], g: p[1], b: p[2], a: p.length > 3 ? p[3] : 1 }; };
const near = (a, b) => a && b && Math.abs(a.r - b.r) + Math.abs(a.g - b.g) + Math.abs(a.b - b.b) <= 24;

// the skin's colours on that page, as the browser computes them
export function palette(doc) {
  const probe = doc.createElement('span'); doc.body.append(probe);
  const out = [];
  for (const v of SKIN_VARS) { probe.style.color = `var(${v})`; const c = rgb(getComputedStyle(probe).color); if (c && probe.style.color) out.push(c); }
  probe.remove();
  return out.concat([{ r: 0, g: 0, b: 0 }, { r: 255, g: 255, b: 255 }]);
}

// what one control looks like (the parts that make a look)
export function look(el) {
  const s = el.ownerDocument.defaultView.getComputedStyle(el);
  const font = s.fontFamily.split(',')[0].replace(/["']/g, '').trim();
  return {
    font, size: Math.round(parseFloat(s.fontSize)), weight: s.fontWeight, color: s.color,
    background: s.backgroundImage !== 'none' ? 'image/gradient' : s.backgroundColor,
    border: `${s.borderTopWidth} ${s.borderTopStyle}`, borderColors: [s.borderTopColor, s.borderBottomColor],
    radius: s.borderTopLeftRadius, shadow: s.boxShadow !== 'none', padding: `${s.paddingTop} ${s.paddingLeft}`,
    caps: s.textTransform === 'uppercase',
  };
}
const key = l => [l.font, l.size, l.weight, l.color, l.background, l.border, l.borderColors.join('/'), l.radius, l.shadow, l.padding, l.caps].join('|');
// shading: a bevel (top and bottom edges differ), a shadow, or a gradient face
const shaded = l => l.shadow || l.background === 'image/gradient' || (l.borderColors[0] !== l.borderColors[1] && parseFloat(l.border) > 0);

export function inventory(doc, page) {
  const pal = palette(doc), out = {};
  for (const [kind, sel] of Object.entries(KINDS)) {
    for (const el of doc.querySelectorAll(sel)) {
      if (!el.getClientRects().length) continue;                 // only what is drawn
      const l = look(el), k = key(l);
      const g = (out[kind] ??= {})[k] ??= { look: l, count: 0, pages: new Set(), sample: (el.textContent || el.value || el.getAttribute('aria-label') || '').trim().slice(0, 30),
        offPalette: [l.color, l.background].filter(c => c && c.startsWith('rgb') && rgb(c).a > 0.1 && !pal.some(p => near(p, rgb(c)))),
        unshaded: (kind === 'button' || kind === 'panel' || kind === 'menu') && !shaded(l) };
      g.count++; g.pages.add(page);
    }
  }
  return out;
}

export function merge(all, one) {
  for (const [kind, groups] of Object.entries(one))
    for (const [k, g] of Object.entries(groups)) {
      const t = (all[kind] ??= {})[k] ??= { ...g, count: 0, pages: new Set() };
      t.count += g.count; g.pages.forEach(p => t.pages.add(p));
    }
  return all;
}
