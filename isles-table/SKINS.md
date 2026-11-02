# Skin authoring

The selector uses body[data-skin]. Add an option in dist/training.html (the old table; site.mjs SKINS for the other pages), whitelist the id in applySkin in dist/app.mjs and add a body[data-skin="your-id"] block in dist/skins.css. No Rust changes are required.

Semantic properties: --ink (page), --panel, --line, --paper (primary text), --muted, --brass (focus/accent), --rust (opposition/alerts), --sage (party), --surface-low, --button, --display-font and --body-font. Tactical properties: --map-floor, --map-tile, --map-wall, --map-grid, --friend, --foe, --map-ink. SVG reads these values when the skin changes. Retain readable text and party/opposition contrast; active state also uses borders and labels rather than colour alone.

Only presentation changes. Never hide a reaction prompt, essential warning or legal-action control as part of a theme. Do not put scripts, remote textures or game state into skins. For new licensed assets, record provenance first. Player-facing theme settings are stored separately from Rust session saves.

The style guide (dist/style-guide.html, on the Documents page) gathers the words, screen and art rules in one place.

## Art direction (GM 2026-10-19)

Style 1: the Retro tokens' cartoon look (thick ink outlines, two or three flat tones per surface) in softer, muted
colours, so the tokens stay the brightest thing on screen. The tokens themselves are never recoloured ("leave the tokens
bright coloured"). The 3D world's palette is dist/world-style.mjs (WORLD): ink, warm sandstone floor, cool grey walls,
wooden doors, a soft dusk background. First pass done: flagstone floors (the seams are the grid), outlined walls with
block courses and a lighter cap, plank doors, outlined zones, a contact shadow under every prop. Next passes: the
Effects (2026-10-20): ink outline under the coloured edge, a flat rim, inked flames, drops, crystals and bolts; comic
hit stars (bigger for a critical), a swoosh with puffs for a miss, inked captions; an ink ring under 3D effects. Play live
now uses the same effect art; the animations moved to dist/effects.css for every page. Interface panels (2026-10-20): the Tabletop skin (skins.css, the default; site.mjs keeps the choice under
mythastria-skin): ink outlines, rounded panels with a hard offset shadow, pressable buttons, Fredoka headings, sandstone
tactical maps with dark walls and solid creature chips. One look for all pages (2026-10-20): dist/site.css + site.mjs give Play live, Simulator
fights and The Stage the main table's header (logo slot, page name, links to every page), buttons, panels and skin.
GM 2026-10-20: the world should look like a tabletop miniature setup, not realistic (maybe CNC models someday).
