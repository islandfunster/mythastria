"""  py tools/make_icons_css.py   (writes dist/icons.css)

Build dist/icons.css: Mythastria's own button and heading icons (ICONS-01, GM 2026-10-27), as CSS masks so they take
the text's colour in every skin. Each icon was drawn from a written description (heraldic blazon, the old texts)."""
import sys
from pathlib import Path
from urllib.parse import quote

S = 'fill="none" stroke="#000" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"'
ICONS = {
    # name: (the description it was drawn from, the SVG body on a 24-unit square)
    "sword": ("a sword erect, cross hilt", f'<g {S}><path d="M12 2.2l1.6 2.6v10.4h-3.2V4.8z"/><path d="M7 15.2h10M12 15.2v4.3"/></g><circle cx="12" cy="20.8" r="1.3"/>'),
    "grimoire": ("an open book, a star rising", f'<g {S}><path d="M2.8 10c3-1 6-.7 9.2 1.2 3.2-1.9 6.2-2.2 9.2-1.2v10c-3-1-6-.7-9.2 1.2-3.2-1.9-6.2-2.2-9.2-1.2zM12 11.2v10"/></g>'
                 '<path d="M12 .8l1.1 2.3 2.5.3-1.8 1.7.5 2.5L12 6.4 9.7 7.6l.5-2.5-1.8-1.7 2.5-.3z"/>'),
    "helm": ("a helm affronté, visor barred", f'<g {S}><path d="M5 20.5V11c0-4.5 3-7.6 7-7.6s7 3.1 7 7.6v9.5zM7.2 11.2h9.6M9.6 13.6v4.6M12 13.6v4.6M14.4 13.6v4.6M12 3.4V1.8"/></g>'),
    "hand": ("a hand appaumé (open, the palm shown)", f'<g {S}><path d="M8.2 21c-1.6-1.5-2.7-4-2.7-6.5V9.6a1.4 1.4 0 0 1 2.8 0V12V4.6a1.4 1.4 0 0 1 2.8 0V11V3.4a1.4 1.4 0 0 1 2.8 0V11V4.6a1.4 1.4 0 0 1 2.8 0V12V7.8a1.4 1.4 0 0 1 2.8 0v6.3c0 3.3-1.4 5.6-3.4 6.9z"/></g>'),
    "horseshoe": ("a horseshoe, its points down", '<g fill="none" stroke="#000" stroke-width="2.8" stroke-linecap="round"><path d="M6.5 20.5V11c0-4.6 2.5-7.2 5.5-7.2s5.5 2.6 5.5 7.2v9.5"/></g>'),
    "purse": ("a purse, drawstrings tied", f'<g {S}><path d="M8.6 9.6c-3.6 1.8-4.4 6.4-3 9.1 1.4 2.7 11.4 2.7 12.8 0 1.4-2.7.6-7.3-3-9.1zM8.6 9.6 7.2 5.4c1.6.7 2.7.6 3.4-.2.8.8 2 .8 2.8 0 .7.8 1.8.9 3.4.2l-1.4 4.2M8.3 9.6h7.4"/></g>'),
    "lantern": ("a lantern lit", f'<g {S}><circle cx="12" cy="2.9" r="1.2"/><path d="M8.6 6.4h6.8l-1.6-2.1h-3.6z"/><rect x="8.2" y="6.4" width="7.6" height="10.6" rx="1"/><path d="M7.4 17h9.2v1.8H7.4z"/></g>'
                '<path d="M12 8.6c1.6 1.9 1.7 3.6 0 5.4-1.7-1.8-1.6-3.5 0-5.4z"/>'),
    "candle": ("a candle snuffed, smoke rising", f'<g {S}><rect x="9.6" y="11" width="4.8" height="8.6" rx=".6"/><path d="M5.5 20.2h13M12 11V9.2M12 8.6c-1.4-1.4 1.2-2.4 0-3.9-.9-1 .3-1.8 0-2.6"/></g>'),
    "key": ("a key erect, wards upward", f'<g {S}><circle cx="12" cy="18.2" r="3.2"/><path d="M12 15V2.8M12 3.6h3.4v2.6H12M12 8h2.6"/></g>'),
    "bezants": ("three bezants (gold coins)", '<g fill="none" stroke="#000" stroke-width="1.7"><circle cx="7.6" cy="8.2" r="3.8"/><circle cx="16.4" cy="8.2" r="3.8"/><circle cx="12" cy="16.2" r="3.8"/></g>'
                '<g><circle cx="7.6" cy="8.2" r="1.5"/><circle cx="16.4" cy="8.2" r="1.5"/><circle cx="12" cy="16.2" r="1.5"/></g>'),
}


def uri(body):
    svg = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">%s</svg>' % body
    return 'url("data:image/svg+xml,%s")' % quote(svg, safe=" =:/'")


out = ["/* ICONS-01 (GM 2026-10-27: \"adding some iconography for the buttons so that they can be recognized visually\"; then",
       "   \"Only put them where they don't look too busy\"). Mythastria's own icons (MIT), each drawn from a written description in",
       "   the old sources (heraldic blazon, the bestiaries' and alchemists' words), never from another artist's picture. Built by a",
       "   script from these descriptions; a CSS mask, so an icon takes the colour of the text it sits beside, in every skin.",
       "   Placed only where one icon names a whole area: the Play live sheet's section headings, End turn, the door buttons,",
       "   the floating Market button. The busy rows of actions, the spell cards and the menu bar keep their words alone. */",
       ":root{"]
for name, (desc, body) in ICONS.items():
    out.append(" --ico-%s:%s; /* %s */" % (name, uri(body), desc))
out.append("}")
out.append(".ico::before,[data-ico]::before{content:'';display:inline-block;width:1.05em;height:1.05em;margin-right:.42em;vertical-align:-.17em;"
           "background:currentColor;-webkit-mask:var(--ico) center/contain no-repeat;mask:var(--ico) center/contain no-repeat;flex:none}")
for name in ICONS:
    out.append('[data-ico="%s"]{--ico:var(--ico-%s)}' % (name, name))
# the places
out.append("/* the places: buttons made by the page's code get theirs here */")
out.append("#end{--ico:var(--ico-candle)}#end::before{content:'';display:inline-block;width:1.05em;height:1.05em;margin-right:.4em;vertical-align:-.17em;"
           "background:currentColor;-webkit-mask:var(--ico) center/contain no-repeat;mask:var(--ico) center/contain no-repeat}")
out.append("#door-buttons button{--ico:var(--ico-key)}#door-buttons button::before,#market-fab::before{content:'';display:inline-block;width:1.05em;height:1.05em;"
           "margin-right:.4em;vertical-align:-.17em;background:currentColor;-webkit-mask:var(--ico) center/contain no-repeat;mask:var(--ico) center/contain no-repeat}")
out.append("#market-fab{--ico:var(--ico-bezants)}")
out.append("@media (forced-colors:active){.ico::before,[data-ico]::before,#end::before,#door-buttons button::before,#market-fab::before{background:CanvasText}}")
OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parent.parent / "dist" / "icons.css"
OUT.write_text("\n".join(out) + "\n", encoding="utf-8")
print("wrote", OUT, len(ICONS), "icons")
