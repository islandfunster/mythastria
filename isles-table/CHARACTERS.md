# Characters: import, review, build and reuse

## The Characters page (CHARACTERS-01, 2026-10-21)

**Characters** is a page in the page row (`dist/characters.html`, `dist/characters-page.mjs`, `dist/characters-page.css`), served by the simulator service (Python, the rules authority). Tabs: Saved characters, Import, Build, Sheet. A sheet is saved through `POST /api/characters` (`sim/character_roster.py`); the browser keeps its copy under the same key as before (`isles-character-roster-v1`), so sheets saved on the old training table appear unchanged. A saved sheet the service refuses is never dropped: it stays in the browser, marked "Needs fixing", until it is fixed and saved or deleted. Photos (up to 4 per sheet, browser only, `character-photos.mjs`) are added on the sheet; the chosen one is the token picture in Play live. The old workshop (`character-ui.mjs`) stays only for the deprecated `training.html`.

### Importers (phase 2)

| From | File | Read by |
| --- | --- | --- |
| Foundry VTT / The Forge | actor Export Data (.json, dnd5e `system` or older `data`) | `character-formats.mjs` `fromFoundry` |
| D&D Beyond | character JSON from its character service (`{data: ...}` or bare), and its PDF export | `fromDDB`; PDF: `character-import.mjs` `parsePDF` + `pdfReport` |
| Fantasy Grounds | character XML export | `parseXML` + `hardenFG` (a weapon's `attackbonus` is only the extra: the attack is worked out from proficiency, the ability and dice) |
| Roll20 | journal-exporter JSON (VTTES `attribs`) | `fromRoll20` |
| Shard, others | PDF, CSV, pasted cells/text; any other JSON matched by field names (and says so) | `fromFields`, `fromGenericJSON` |

D&D Beyond PDF (its export as of 2026-10, made with PDFsharp): the values are named widgets on the pages but the file has no AcroForm, so pdf.js lists no form fields. `parsePDF` then reads the widgets from each page's annotations (`widgetFields`), and `pdfReport` maps D&D Beyond's own field names (`ddbPdf`): CharacterName, CLASS  LEVEL, RACE, BACKGROUND, STR..CHA, the save and skill marks, AC, MaxHP, Speed, Wpn rows, spellName under each spellHeader (by position), FeaturesTraits, Eq Name/Qty, ProficienciesLang, AdditionalSenses, Defenses. Before this (GM 2026-10-22: "the import character sheet pdf from dnd beyond doesn't read the file") such a PDF opened as a blank sheet with everything "missing". Test: `tests/fixtures/ddb-widgets-no-acroform.pdf` (`tools/make_ddb_fixture.py`, made-up values, built the same way).

Google Sheets laid out as a character sheet: Iain McEwen's "5e Character Sheet - Google Sheets" (https://www.iainmcewen.com/projects/google-character-sheet). Its cell map (`IAIN_MCEWEN` in `character-formats.mjs`) was taken from the published template on 2026-10-21 ("Character Sheet - Master"; tabs Welcome, Character, Additional, Spells, Behind the scenes, Supplemental) and checked against that template's own .xlsx export. Read from the GM's own copy: File > Download > Microsoft Excel (.xlsx; `readXlsx`, no library), or its Character, Additional and Spells tabs as CSV chosen together, or a public link (the whole workbook first, then the tab). It is recognised only by its labels in their cells (Race I1, Class AB1, Subclass AD1, Levels AH1, Ability A6, Strength D6, Proficiency Bonus C25, Armor Class K25); a copy whose layout has moved is not read by guesswork. Saves and skill proficiencies are not marked on the Character tab, so they are worked out (bonus minus ability modifier) and said so. Not used: hit dice, death saves, current/temporary HP, conditions, exhaustion, coins, jump and other speeds, the Behind the scenes and Supplemental tabs. Test fixture: `tests/fixtures/iain-mcewen-sample.xlsx` (`tools/make_iain_mcewen_fixture.py`, made-up values in the template's cells).

Every import carries `import`: what was read (and from where), what was worked out (and how), what is missing (left empty, never guessed), what was not used, and the pictures found. Pictures: `data:` images in the file and the images in a PDF (pdf.js, including a picture field such as D&D Beyond's character image) are offered as "Use this as the token picture?"; a web address (a D&D Beyond or Roll20 avatar) is fetched only when the GM presses its button; a file path (Foundry, FG) is only named. Picture data is not stored on the saved sheet (the photo store holds it).

Content policy: the service checks every opened and saved sheet (`POST /api/characters {op: character_check}`, `sim/character_rules.py` with `sim/srd_character_rules.json`) and lists anything not SRD 5.2.1 (2014 rules, other species, classes, subclasses, feats, spells, features) as "homebrew, GM rules it". Nothing is refused, nothing leaves the browser, nothing imported is added to shipped data or used to train or prepare anything.

Tests: `character_formats_tests.mjs` (browser: `tests/character_formats_tests.html` on a file server of `isles-table`), Mythastria `test_character_rules.py`.

### The builder (phase 3)

Build tab (`character-builder-ui.mjs`): the page only collects choices (`mythastria-build/1`); after every change the simulator service works out and checks the whole character (`POST /api/characters {op: character_build}`, `sim/character_build.py`). SRD 5.2.1: levels 1-20 one at a time ("Level up", or "straight to level N" with Auto-fill), multiclassing (13+ in the primary abilities, the proficiencies a new class gives, the Multiclass Spellcaster table, Pact Magic apart), each class's SRD subclass at level 3, Ability Score Improvements / feats / Epic Boons, Fighting Styles (and Blessed/Druidic Warrior), Expertise, Divine/Primal Order, Circle of the Land, invocations with their prerequisites, Metamagic, cantrips and prepared spells per class (a Wizard's spellbook), always-prepared subclass and species spells, equipment, Weapon Mastery, hit points by the average or a rolled die. The side panel lists what is still to choose and what is not allowed (each with its level), and shows the readable sheet (`character-sheet-view.mjs`). "Auto-fill the rest" fills whatever is open (spells the simulator plays first). A saved built sheet keeps its choices (`build`) and opens again with "Change in the builder".

Fight numbers (HP, AC, speed, initiative, attacks with mastery, saves, skills, spell DC/attack, slots, resources) are the service's. `{op: character_member}` turns any sheet (built or imported) into the simulator party member the pregens use (`sim/run_sim.py apply_party` format) and lists everything the simulator can't play as "GM rules this" on the sheet; an imported sheet that lacks a fight number says so. Tests: Mythastria `test_character_build.py`.

Point buy (GM 2026-10-21): 27 points is the default, shown highlighted (SRD 5.2.1); − / + set another budget (10-45) for survival or heroic games, marked "table option (house rule)" on the build and in the service's warnings (`point_budget`).

### Test in Play live (phase 4)

Every saved character has "Test in Play live" (on its card and on its sheet): choose a practice map (remembered) and the pregens who come along (none: alone), and Play live opens and starts the fight at once (`play.html?characters=<id>&members=...&level=...&scenario=...&start=1`). The character fights at its own level; pregens join at the same level (8 at most, their highest build). Play live's Party box has "Saved characters" (checkboxes) beside the pregens, so Start live fight tries it again or with others. The sheets go with `POST /api/live/new {characters}`; the service makes each one a party member (`character_build.member`) and refuses one that can't fight yet, saying what it lacks; its photo goes on its token. Check: Mythastria `tools/play_live_check.py` (steps "A saved character ...").

### The Mythastria character sheet (phase 5)

`dist/character-sheet-pdf.mjs` makes the sheet in the browser (our own small PDF writer, no library): US Letter, two pages, printer-friendly, the Mythastria logo, the SRD 5.2.1 fields (identity, abilities and saves, the fight numbers, six attacks, skills with proficiency/expertise marks, proficiencies and languages, senses and resistances, uses, feats, equipment; page 2: spellcasting, slots, cantrips and spells by level, features with "[GM rules]", notes) and a portrait box (the picture field "Portrait", holding the token photo). Every field is fillable in a PDF reader and printed as filled. Buttons: "Mythastria sheet (PDF)" on a sheet, "Blank character sheet (PDF)" on the saved characters list. MIT (see `CREDITS.md`).

Importing it back (Import, choose the PDF): the hidden field `mythastria_data` carries the character, so it returns whole (same identity: saving replaces it); every field changed in the PDF since is applied and listed under "Worked out", and a changed fight number sets the builder's working-out aside. A blank sheet filled in by hand is read field by field. The portrait comes from the known box (field "Portrait") and is offered as the token picture. Tests: `character_formats_tests.mjs` (`runAsync`: made, read back, edited in a reader, filled by hand).

## The old training-table workshop (deprecated)

Open **Characters** in the table header. This is a separate reusable roster, not a rules profile inferred from artwork. The default build is an editable level 1 Human Fighter foundation. The collection is stored locally in this browser; export JSON for backup or another device. No character file is sent to an AI service.

## Import sources

| Source | Supported route | Review boundary |
| --- | --- | --- |
| XML | Local `.xml`; common FG character/NPC exports, generic leaf fields; multiple characters; FG class, inventory, feat and spell lists | Vendor schemas vary. Unknown fields remain in the extract. DTDs/custom entities are rejected. |
| PDF | Local `.pdf`, through vendored PDF.js; text fields and readable page text | PDF layout has no universal character schema. Missing or ambiguous numbers remain blank. Image-only scans require OCR before import. No OCR engine is bundled. |
| Google Sheets | Download CSV, paste copied cells, or read a publicly readable standard `docs.google.com/spreadsheets/d/...` link | Private sheets use export/copy, not account credentials. Browser CORS/access policy can block even public URL reads; CSV and paste work independently. No Google OAuth integration is implied. |
| CSV / TSV | Local file or pasted cells; Field/Value rows or wide rows with headers | CSV quoting and embedded newlines supported. Multiple rows become selectable characters. Use semicolons or newlines within list cells. |
| Text | Pasted or local `.txt`, labels such as `Armor Class: 16` | Unlabeled or unusual layouts need manual entry. |
| Isles JSON | Single character or exported collection | Uses `isles-character/1`; other vendors' arbitrary JSON schemas are not silently interpreted. Imported sheets get new IDs. |

Useful headers: `Name`, `Class`, `Level`, `Species`, `Background`, `STR`, `DEX`, `CON`, `INT`, `WIS`, `CHA`, `HPMax`, `AC`, `Speed`, `AttackBonus`, `Damage` (for example `2d6+4`), `DamageBonus`, `Reach`, `Proficiencies`, `Feats`, `Features`, `Spells`, `Equipment`, `Notes`.

Review displays source mapping and an extract (up to 80,000 characters), and lets the user correct every combat field and sheet list before saving. Keep the original source file; this extract is not a lossless document conversion. Maximum XML/CSV/text/JSON input is 2 MB. PDF input is limited to 20 MB / 30 pages. Imports do not overwrite existing table actors.

## SRD builder scope

SRD 5.2.1: all 12 classes, nine species, four backgrounds, its Origin feat choices and 84 cantrip/level 1 spell identities. It creates level 1, single-class foundations with standard array, 27-point buy or player-entered rolled scores. Background ability increases, legal armor/weapon choices, core equipment costs, species size, basic skill duplication, class spell counts, Wizard spellbook/preparation and Magic Initiate spell-list choices are checked.

Calculated: ability modifiers, first-level HP, armor/shield/unarmored AC, walking speed including heavy armor Strength penalty and Wood Elf/Goliath speed, proficiency, skill/save bonuses, selected melee weapon attack/damage/reach, spell save DC/attack and first-level spell slots. Dwarf Toughness, Alert initiative and Defense style are reflected in these sheet values. These calculations are a sheet snapshot; direct edits in Review do not recalculate dependent values. Reopen/recalculate the builder to revise a build consistently.

This is a **foundation builder, not a complete character-rules validator**. Tool kinds, mastery/invocation details, class-feature options, lineage details and additional purchases need the user's rules review using the linked SRD. The core-loadout shop does not account for freely described additional purchases; record them and deduct costs manually. Higher-level advancement, multiclass creation, feature prerequisites/choices in full, spell effects, weapon property resolution and magic item benefits are future work. Higher-level/multiclass source sheets can already be imported and reviewed without being converted to level 1.

## Rust boundary

The Rust module owns validated roster records and a small combat projection. `character_save`, `character_list`, `character_roster_load`, `character_delete` manage sheets. Browser persistence/export stores the returned records. `character_place` requires the current state revision and an existing saved ID. It atomically adds a combatant at the first free matching footprint or replaces the selected actor at its existing location. A failed fit or stale revision changes nothing. Adding appends to turn order with initiative 0; replacing keeps initiative and starts at full HP, without refreshing spent action/movement. Movement is clamped to the replacement speed.

Only max HP, AC, walking speed, one basic melee attack (including multiple damage dice), reach, artwork/space and side are projected. The prototype limits HP to 1–1000, AC 1–40, speed 5–60 in multiples of 5, reach 5–15 in multiples of 5 and 1–10 damage dice of 1–100 sides. Larger profiles need a later engine increment rather than silent clamping. One-sided dice represent fixed 1 damage. Spells, skills, feats, resources, resistances and class features remain sheet data, not legal-action implementations.

The full profile is embedded once in each actor's session save. Routine state/history messages contain only character identity, avoiding repeated source extracts every turn. `character_actor_sheet` retrieves the attached full sheet. Changes to a saved roster sheet do not retroactively alter already placed combatants; explicitly replace to apply. Removing a roster sheet does not remove an actor. An attached sheet can be reopened and saved back to the roster after loading a session on another device.

Bounds: 100 reusable sheets and 40 encounter actors. Browser storage and the existing 1.8 MB session-file limit still apply; export sheets separately when needed. This remains local GM/hotseat, without network ownership or per-player secrecy.

## Evidence

- `test_characters.mjs`: source catalog sanity, valid foundations for all 12 classes, creation arithmetic and invalid choices, XML multiclass/lists/entities, malformed XML, quoted CSV/TSV, unknown fields, Google URL restriction, actual PDF.js extraction against original form/text/no-text fixtures, real WASM CRUD/placement/stale requests/session roundtrip.
- `test_character_ui.mjs`: actual WASM plus a DOM harness; paste/import/review/art assignment/roster persistence/placement/reopen/lazy SRD catalog/incomplete-builder save guard.
- Native Rust and existing UI/movement/effects/WASM suites remain required after engine changes.
- No browser visual or physical tablet QA was available. PDF text/form extraction is tested in Node; native browser file pickers and public-Sheets CORS still need user verification.

## Source maintenance

`dist/srd-creation.json` is a reviewed, small metadata catalog, adapted from the official SRD PDF. `tools/srd_spells_521.json` records the 84 low-level spell identities/class lists/page references extracted from that PDF's heading fonts and checked for duplicates/missing headings. `tools/build_character_catalog.py <pdftotext-flow.txt>` regenerates the catalog; do not use unrelated proprietary compendia as an implicit replacement. See `dist/SRD_ATTRIBUTION.md`.
