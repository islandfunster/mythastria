# Flavor — "Flavor is free!"

GM (2026-10-20, the AI assistant's Flavor package; installed 2026-10-21): "let's add that flavor that allows descriptions of
pets, familiars, mounts or for the dm to change the artwork for a creature as well as non-statblock related description
in a flavor footnote."

Flavor changes how a creature, attack or spell looks and reads. It never changes the rules: HP, AC, size, footprint,
speed, attacks, damage, areas and costs stay as the Python simulator says. Nothing in Flavor is sent to the simulator.

## Using it (Play live, the GM's console)

**Flavor…** (beside Notes) opens the dialog. Choose a creature, then a subject:

- **Creature**: display name, role (Pet, Familiar, Mount, Companion), the **Flavor footnote** (up to 1000 characters,
  not the stat block), artwork from the creature catalog (creatures.json, with a preview) or the newer token art
  (flavor-art.json, names marked "newer art"), **Players may read the footnote**, and **Keep on every map** (for a pet,
  familiar or mount that travels with the party).
- **The standee in the 3D view** (GM 2026-10-23, after the 3D minis pilot: "Keep the flat standees. Include them to be
  edited in flavor"): **Stand on a round base** (a dark base like a miniature's) and **True height** (as tall as the
  picture; without it the standee is drawn 40% taller, as before). The newer art: the 20 finished SRD Bestiary tokens
  (Troll, Camel, Polar Bear, Cloaker ...; none has a Retro token), offered as a choice only, never a creature's default
  picture.
- **Rider** (GM 2026-10-23: "flavor is used to add a rider to the camel horse or any other creature that can be
  mounted"): on a Large or bigger creature (the SRD: a mount is at least one size larger than its rider), a catalog
  picture shown on its back: a small picture on its token on the map, a Medium standee on top of it in the 3D view.
  A look only: the creature fights with its own stat block. A mounted foe belongs to an adventure's story (Mythastria
  DECISIONS, "Mounts are domestic animals"); Remix never offers a mount as a foe.
- **Attack** / **Spell** of the character whose turn it is: display name, description; spells also take a visual
  palette (frost, fire, transport ...). Range, area, damage and timing do not change.

Where it shows:

- the map: the shown name and picture on the token (drawn at the creature's own footprint); the token's tooltip adds
  the rules name (GM's console only) and the footnote;
- the character sheet: the shown name with the rules name ("Ash Witch · Ilsa"), the footnote in italics under the
  stat lines, attack and spell cards with their Flavor names;
- under the board: the footnote of the creature whose turn it is;
- third person: the bar labels and the pointer's label; the standee on its base and at its height (players too);
- the players' window (Pop out the map): the shown name and picture always; the footnote only when "Players may read
  the footnote" is ticked; never the rules name. The Flavor button is hidden there. A save shows there at once.

Erase and redo (GM 2026-10-21: "allow flavor to be erased and redone"): **Erase this Flavor** puts back the original
for the chosen subject (this map and every map, paint too); **Erase all Flavor on this map…** (asks first) puts back
every creature, attack and spell on this map; Flavor kept on every map stays and is erased creature by creature.
Then make it again as before.

## Paint a mask

GM (2026-10-21): "maybe we should add a simple paint to put a temporary mask on a copy of a creature". For a creature,
**Paint a mask…** opens a paint box over a copy of its picture (the chosen artwork, else its own picture or sheet
photo): colour, brush size, eraser, Clear the paint, **Use this paint** or Cancel. The token shows the painted copy
on the map, in third person and in the players' window. The token files never change.

- **For this adventure only** (ticked at first; GM: "Really I wanted it for adventure, not fight."): the paint stays
  through the adventure's fights and restarts, and comes off when the GM ends the adventure on the Adventure page (or
  starts it again). In a fight outside an adventure the tick reads **For this fight only**. Untick it to keep the paint
  until removed.
- **Remove paint** takes it off; painting again starts from the earlier strokes (the eraser takes them off).
- Paint on another picture: when the creature's artwork is changed, the old paint is not shown; paint again.
- Kept as two small WebP pictures (the strokes, and the picture with the strokes; about 25 KB) in the creature's
  Flavor. Only pictures made by the paint box are accepted (PNG or WebP, under 400 KB).

## A player's own Flavor

PLAYER-FLAVOR-01 (the Player Client Plan, item 7): **My Flavor…** on a seated player's screen opens the same dialog, for the
looks of their own character and what it summoned (a familiar, a steed, the undead it raised): name, role, footnote,
picture, the standee's base and height, a rider, and paint. Looks only, never stats, and no attack or spell.

- **Ask the GM** sends the look; a new request replaces the one before. **Ask for the original look** asks for the old one.
- Until the GM answers, the look shows on that player's screen alone, with a Pending note beside the button.
- The GM sees it in **Asked of the GM** with its picture: **Approve** and everyone sees it, on every map, with the footnote;
  **Refuse** and the previous look is back, with no note (the GM explains in person if needed).
- A footnote the GM wrote and never shared stays private when the player asks for none of their own.
- The service checks it all again: only a creature that seat controls, only the looks in table_flavor.ASKABLE, paint under
  400 KB. Requests are kept with the Flavor, so they survive a restart.

## Where it is kept

In Mythastria itself (Mythastria tools/table_flavor.py, sim/flavor/flavor.json on this PC), so it survives restarts
and reaches players on their own devices through the players' door: a seat gets only the creatures it sees on this map,
a footnote only when shared, never the paint strokes. The GM's browser keeps a copy for the pop-out; Flavor made before
this moves into Mythastria the first time the page meets it. Two consoles (the GM and a stand-in) save on a revision: a
save made on top of someone else's newer one is refused with the newer Flavor shown. A creature is found by its rules
name ("Goblin Warrior 1", "Ilsa") on a map, or on every map; the simulator's fight numbers change every fight and are
not used. A test service keeps its own file. With a Mythastria from before this (not restarted), Flavor stays in the
browser.

## Files and checks

- `dist/flavor.mjs`: the allowlisted fields, every-map lookup, the view copy of a creature, spell visuals.
- `dist/flavor-ui.mjs`, `dist/flavor.css`: the dialog.
- `dist/flavor-paint.mjs`: the paint box.
- `dist/catalog.mjs` (loadFlavorArt), `dist/flavor-art.json`, `dist/tokens/newer/` (its own LICENSE): the newer art.
- `dist/third-person.mjs`: the standee's base and true height.
- `dist/play-ui.mjs`, `dist/play.html`: Play live; `dist/adventure-ui.mjs`: End / Start take an adventure's paint off.
- `test_flavor.mjs` (26 checks; runs in `tests/node_tests.html`, no Node needed): mechanics never change, footprint
  kept, unknown art refused, new fights keep Flavor, every-map Flavor, the players' window, persistence, the dialog,
  paint (pictures only, the picture painted on, for the adventure or fight, ended with the adventure, remove),
  erase and redo, kept by Mythastria (saves, another screen first, moving in, a players' page, an old Mythastria).
- Mythastria `test_table_flavor.py`: the allowlist, a seat's view, revisions, restarts, an adventure's paint, the
  standee settings (yes or no only; players see them).
