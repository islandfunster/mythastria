# The Mythastria simulator

FG-EXIT-01 (2026-10-26): the fight is played in Python. `sim/fight_state.py` keeps the fight (combatants, Hit Points,
positions, turns, effects, attack and damage rolls) and `sim/creature_turns.py` plays every creature: the planner
(`mythastria_core/ai_turn.py`) lists its legal choices, your **local model** (or the scripted chooser) picks one, and the
move, attack, Search or opportunity attack is carried out with its rules checked again. The stat block's spellcasting,
legendary actions and traits plug in through `sim/creature_abilities.py`. Player characters follow a script
(sim/party.py) or a person (Play live). A transcript goes to `sim/runs/` (not in git or snapshots).

    py sim/run_sim.py sim/scenarios/test/grick_2024.json                  # your local model (qwen3.5 if installed)
    py sim/run_sim.py sim/scenarios/test/bandit_captain_2024.json --fake-model   # scripted chooser: fast, repeatable
    options: --model NAME  --rounds N  --seed N (dice)  --instant (dice resolve inside the roll call)  --quiet

Before FG-EXIT-01 the old FG extension (`extension_source/scripts/aibridge.lua`, Lua 5.4 through `lupa`) played the
creatures on a stand-in FG (`sim/fake_fg.lua`), talking over HTTP to the old bridge; all three are in
`archive/fg_exit_2026-10-26/` since step 4, and the simulator needs no `lupa`. The sections below that speak of FG
describe how the stand-in behaved; the Python engine plays the same rules (its turns recorded in `sim/parity/`, replayed
by test_engine_parity.py; the stand-in's own calls in `sim/parity/fight_state/calls.json`, by test_fight_state.py).

Exit code 1 when a turn stalled or a rule check refused something ("not run", ...): those are the bugs to look at.
`test_sim.py` plays both scenarios with the scripted model on every test run.

For the Seven Isles level 1–7 encounter sequence, use the root `Run_Seven_Isles.bat` launcher and `tools/seven_isles_campaign.py`. It selects one reproducible random party of four per run and preserves that roster across the island sequence. The LM Studio procedure and simulator boundaries are in the root `LM_STUDIO_RUN.md`.

Nothing touches your real settings, logs or stat-block plan cache (temporary files). The rules cache is read
for spell text but never written.

## Creature abilities (FG-EXIT-01 goals 6 and 7, 2026-10-27)

`sim/creature_abilities.py` plays the rest of a creature's SRD 5.2.1 stat block on the Python turns, checked by the
referee: its **Spellcasting** (spells cast from the rule sheet, sim/spell_rules.py, through the general caster of
sim/live_general.py: attacks and rays, saves in the SRD shapes, healing, Magic Missile, Bless, Shield as a Reaction,
At Will and N/Day uses, Concentration held with a save after damage; a cast ends the creature's own Invisibility),
**legendary actions** (one after each other creature's turn while uses remain, Legendary Resistance on a failed save)
and **traits** (Pack Tactics, Bloodied Frenzy/Fury, Sunlight and Light Sensitivity, Magic Resistance, Flyby and Agile,
Regeneration and what stops it, Undead Fortitude, Death Burst, start-of-turn auras, Evasion). What it does not play
(spells with no effect in a fight, summons, teleports, Charmed, lair actions, travel and sense traits) is said once at
the start of the fight as "The GM rules ...". A scenario with `"creature_abilities": false` plays the stat block as
before (tools/engine_parity.py's recordings do). `tools/srd_library.py add-srd-text` gives the hand-made blocks the SRD
actions they lack (a Mage's Spellcasting). Tests: test_creature_abilities.py.

## What is simulated (checked against the installed CoreRPG / 5E rulesets)

- Combat Tracker: initiative order, rounds, `setCustomTurnStart` handlers (added, not replaced), 5E clearing the
  reaction box at a creature's turn start, the active combatant.
- DB semantics the extension relies on: paths, child nodes, typed values, window references (`link` returns class,
  record), `DB.getValue(path, default)` with a non-string second argument as the default, change handlers
  (`onUpdate` on wounds, `onChildAdded`).
- Tokens on one map with a grid, FG's diagonal rule, positions, and `Token.addEventHandler("onMove")` firing on
  `setPosition` (player moves and the AI's NPC_MOVE).
- Attacks and damage: `parseNPCPower` returns the scenario's attack bonus/reach/damage; an attack is d20 + bonus vs AC
  (20 crits, 1 misses), resolved on the next step like FG's dice (or at once with `--instant`), then
  `onAttackPostResolve`; damage dice (doubled on a crit) are added to wounds.
- Damage Resistance, Immunity and Vulnerability (SIM-MECHANICS-01, 2026-10-18), as CoreRPG's
  `applyDamageAdjustMain`: damage summed per type, Immunity -> 0, Resistance halves (odd remainder carried),
  Vulnerability then doubles; untyped damage unchanged. A creature's `damageimmunities` / `damageresistances` /
  `damagevulnerabilities` come from the scenario, else from its SRD 5.2.1 bestiary record (name without the number,
  or `srd_name`); Rage adds B/P/S; the pregens carry their species resistances (Hero 5, Hero 4, Vex: Fire). Every party
  attack and spell names its damage type (`party.damage_type`).
- Monster saving-throw effects, played by the simulator as the GM (SIM-MECHANICS-01 b, `sim/gm_rules.py`; the live
  bridge does not offer them, the GM plays them in FG): Recharge breath (Magma Mephit Fire Breath, Steam Mephit Steam
  Breath: 1d6 at the start of the creature's turn once spent; used in place of its turn when the 15-ft Cone from where
  it stands catches a character and no ally it would harm) and Death Burst (Magma and Steam Mephit, Magmin: every
  creature in the Emanation when it drops). Each target saves with its own bonus: the pregens carry all six saves;
  Danger Sense, Aura of Protection, Bless and Evasion apply.
- Conditions, played by the simulator as the GM (SIM-MECHANICS-01 c, `gm_rules._Conditions`), mirrored as Combat
  Tracker effects: Grappled (Giant Crab Claw, escape DC 11, two claws; Speed 0, Disadvantage except against the
  grappler, which a grappled character then attacks; ends when the grappler drops or is out of reach), Prone (Rock
  Launch; Disadvantage on its attacks, Advantage within 5 ft / Disadvantage beyond against it; stands up for half its
  Speed), Charmed + Incapacitated (Luring Song: Wis DC 11, Fey Ancestry Advantage; walks toward the harpy; save again
  at the end of each turn and when hurt by another; ends with the harpy's Concentration), Frightened (Unsettling
  Visage, part of the Doppelganger's Multiattack; Disadvantage while it sees the source; the scripted character holds
  still rather than approach), Steam Breath's Speed -10 ft until the end of the mephit's next turn. Incapacitated
  ends Concentration and blocks Reactions (Shield, Uncanny Dodge, opportunity attacks) and Aura of Protection. Not
  yet: escaping a grapple with an ability check (the party fights the grappler instead).
- Shield of Faith and Spiritual Weapon (SIM-MECHANICS-01 f, 2026-10-19; Concentration, Bonus Action): Bless stays
  first; a caster holding no Concentration with a slot beyond the one it keeps (Healing Word for Hero 2, Divine Smite
  for Hero 6) casts Spiritual Weapon (Hero 2 3+: beside a foe she sees within 60 ft, a melee spell attack at once, 1d8 +
  modifier Force, +1d8 per slot above 2; later turns a Bonus Action moves it 20 ft and strikes; walls not checked
  for the force) or Shield of Faith (+2 AC: Hero 2 on the ally the most foes are next to from level 1, Hero 6 on herself
  from level 3 when a foe is within her move). Healing Word now takes Hero 2's Bonus Action.
- Spells that disable foes (SIM-MECHANICS-01 f slice 2, 2026-10-19; conditions played by the simulator as GM):
  Sleep (Hero 4 1: two foes or more in the 5-ft Sphere, not those immune to Exhaustion; Incapacitated, Unconscious
  after a second failed save at the end of its turn; damage wakes it; one slot stays for Shield), Hideous Laughter
  (Vex 1: a foe with 20 HP or more within 30 ft; Prone and Incapacitated; saves at the end of its turns and, with
  Advantage, when damaged), Hold Person (Vex 5: a Humanoid with 20 HP or more; Paralyzed; one target), Command
  (Grovel: Hero 6 when no foe is within her move and reach, Hero 2 2 when two allies are next to the focus). Attacks
  against Paralyzed, Petrified, Stunned or Unconscious creatures have Advantage, hits within 5 ft on Paralyzed or
  Unconscious ones are critical (fake FG, as 5E's ActionAttack), and they fail Strength and Dexterity saves. A Prone
  monster stands up at the start of its turn (the half Speed it costs is not passed to the bridge). Not modelled:
  someone shaking a sleeper awake, upcast extra targets.
- Damage spells (SIM-MECHANICS-01 f slice 3, 2026-10-19): Hero 4 Burning Hands (1), Ice Knife and Thunderwave (2),
  Shatter (3+; Fireball takes over at 5), Ray of Frost (when the target is known to resist or ignore Fire), Hellish
  Rebuke (3+, the Infernal Legacy's free casting once a day); Vex Burning Hands (3-4) and Hellish Rebuke (3+); Hero 6
  Searing Smite (3+, a sturdy target with 25 HP or more, before Divine Smite). Areas only when two located foes or
  more are caught and no ally; Hero 4 keeps a slot for Shield. Thunderwave pushes 10 ft (stops at walls and creatures).
- Features (SIM-MECHANICS-01 f slice 4, 2026-10-19): Hero 2's Channel Divinity from level 2 (2024): Turn Undead when
  two Undead or more are within 30 ft (Frightened and Incapacitated; damage ends it), Divine Spark on the focus with a
  spare use (one stays for Preserve Life from 3); Cure Wounds on a neighbour at a third of its HP or less (not
  fallen); Vex's Repelling Blast (2) pushes a foe off a fallen ally or himself; Misty Step (Hero 4, Vex 3) away from a
  foe beside the caster (teleport: no opportunity attack).
- Concentration (SIM-MECHANICS-01 e, SRD 5.2.1): the party's Bless, Hex and Spirit Guardians; one at a time per
  member (`Party.start_concentration`: a new one ends the old; `drop_concentration`: ended at will, no action); a
  Constitution save after each damage (DC 10 or half, up to 30); ends when Incapacitated (Paralyzed, Petrified,
  Stunned and Unconscious included) or dead, also for the deaths the simulator applies directly (Strength 0,
  suffocation). No monster in the encounters casts a Concentration spell; the harpy's Luring Song is played as GM.
- Monster traits (SIM-MECHANICS-01 d, `gm_rules._Traits`): Undead Fortitude (Zombie; FG automates it too:
  Con save DC 5 + damage, not Radiant or a Critical Hit), Fire Aura (Azer Sentinel, end of its turn), Parry (Knight,
  +2 AC against a melee hit), Regeneration (Shield Guardian), Blurred Form (Steam Mephit), the Doppelganger's
  first-round Advantage, the Minotaur Skeleton's Gore charge (20+ ft straight before the hit: +2d8 and Prone),
  Draining Swipe (Shadow: Strength -1d4; Strength attacks, damage and saves follow; death at 0; the pregens carry
  `str_score`), Burning from a Magmin's Touch (1d4 Fire at the start of each turn; at half HP or less the character
  rolls it out: an action and Prone), and the Azer's and Magmin's light on maps with lighting (the GM keeps magmins
  ablaze). Monster saves fill from the SRD record (ability bonus + savemodifier) unless the scenario gives them.
  Not simulated: Life Drain (the monster AI cannot replace an attack with it), Flyby, Earth Glide, Amorphous, Shadow
  Stealth, Protection (no amulet wearer); Sunlight Sensitivity/Weakness never applies (no sunlit map).
- Chat (GM) and delivered messages (players), so narration appears in the transcript.

## What is NOT simulated (FG remains the truth)

- FG's rules engine: effects and their modifiers, advantage, conditions applied by rolls, saving throws,
  healing, spells (spell actions are not in the scenarios yet), death saves.
- Walls and line of sight, token sizes on the map beyond the CT `space` value, map switching.
- Timing quirks of real FG dice and network delays beyond "one step later".

## Scenarios

`sim/scenarios/*.json`: grid, rounds, combatants (id, name, side, `pc`, hp, ac, init, x/y in squares, speed, reach,
space, effects, actions with `atk`, `atktype`, `reach`, `dmg` like "2d6+2", and a Multiattack `desc`), player
`script` per round (`"move X Y"`), and `fake_plan` (what the scripted model answers for the stat-block interpreter).
Use SRD creatures or your own; licensed stat-block text must not be committed.

Scenario creatures: Grick, Bandit Captain and Guard are from the System Reference Document 5.1 by Wizards of the
Coast, CC-BY-4.0.

## Found by the simulator so far

- v0.7.61: the 2014 Bandit Captain's "two ranged attacks with its daggers" alternative accepted a melee Dagger, so
  the Captain stopped after two attacks instead of three (fixed in `ai_turn._kind_ok`).
- v0.7.80: `walls_stub.json` reproduces field 2026-10-13 00:42 (a Gobliez stopped with a wall across its square):
  the audit now flags any stop within a quarter square of a wall; the pre-v0.7.79 planner fails it.
- Narration is written before the dice roll and can describe a hit that then misses (existing behaviour, open).

## v0.7.69 automatic rehearsal movement

Only inside Sim, build_options uses simulation=True: target-grid fallback for differently phased token centres, approach-only choices when no attack can reach, and end-turn handling for unreachable remaining Multiattack attacks. Defaults for native bridge calls are unchanged. Automatic approach choices retain parser-backed weapon/target identity, but queue NPC_MOVE then NEXT_ACTOR, never an out-of-range attack. They respect captured speed, remaining budget, terminal occupancy, faction and the existing avoid-provoking restriction. This is a wall-free endpoint abstraction, not pathfinding through walls or occupied intermediate squares.

Decision errors now stop promptly and count as problems. Watchdog resets on dice/turn/queued-action progress, local-model idle limit defaults to 200 seconds, seed/instant metadata reflect the actual run, and closing the simulator invalidates late workers/restores the planning function.

## v0.7.70 captured Savage Attacker

The linked PC feat snapshot enables 2024 Savage Attacker only when ownership/edition are confirmed. The isolated engine uses it on the first successful weapon hit each global combatant turn, including off-turn attacks, chooses one complete weapon-dice pool (including critical weapon dice), and adds modifiers once. Nonweapon damage/riders are excluded. Explicit scenario actions mark their weapon dice; NPC actions without this flag do not gain the feat. Spells/smites, saves, auras, mastery and native FG fidelity remain unsupported.

## v0.7.81 lighting and the 2024 goblin den

`goblin_den_2024.json`: SRD 5.2.1 Goblin Warrior x2 and Goblin Boss in a dark den against Hero 1 (Human Fighter 3,
Champion; sheet in `sim/characters/`). Scenario keys: `"lighting": {"ambient": "dark" | "dim" | "bright", "lights":
[{"x", "y"} or {"carrier": "<ct id>"}, "bright_ft", "dim_ft"]}`; combatant `"senses": "Darkvision 60 ft."`; PC
`"weapon": {"atk", "reach", "dmg", "crit", "graze"}`, `"savage_attacker"`, `"second_wind"` (uses); script verbs
`advance` (toward the nearest foe it can see, along the bridge's planner) and `attack` (nearest foe in reach, with
Advantage/Disadvantage from sight); `"*"` is the script for every round. The fake FG rolls two d20s for
`bADV`/`bDIS` as CoreRPG does. Blindsight counts (v0.7.92). NPCs hear the fighting (v0.7.93, the GM's distances). NPCs open doors (v0.7.95; scenario creatures need `type` and `int`; `locked_doors` lists locked door ids). Not simulated: magical Darkness, Hide/Invisible, the goblins' extra 1d4
when the attack had Advantage (FG's parser does not add it either), Disadvantage for ranged attacks in close combat.

## v0.7.89 practice twin: continue a saved fight

    py save_fight.py                      # or the bridge page's "Save this fight for a practice run" button
    py sim/run_sim.py --from-snapshot mythastria_core/cache/fight_snapshots/<file>.json [--rounds N] [--local-model] [--pcs pass|attack]

`mythastria_core/fight_snapshot.py` saves the bridge's live picture of the fight (local cache only); `sim/practice.py`
turns it into a scenario: positions and confirmed walls/lights are converted with the same token-frame transform the
bridge uses (`map_walls.placed`, e.g. the Kobold Pantry's top-left frame, walls confirmed `center_up`), wounds, used
reactions and effects are kept, and the fake FG resumes at the saved round and turn (`SIM.resumeCombat`; a turn
already under way in FG starts with the next combatant). The fake FG's initiative order now follows CoreRPG
`sortfuncDnD` (result, bonus, name, path). NPC attacks: the first attack FG parsed and the damage after it (what
PARSED_ATTACK uses live). Not simulated and listed before the run: spells, save/heal/effect actions, riders, mixed or
multi-part damage, Multiattack wording the parser cannot read, active effects, temporary HP (these stop the run when
reached), traits and unparsed actions (ignored, listed). A PC at 0 HP stops the run. Report:
`mythastria_core/cache/practice_runs/`. Nothing is written back to FG.


## PARTY-01 (2026-10-14): an optimized party that plays as a team

    py sim/run_sim.py sim/scenarios/watch_temple_interior.json --party level1_team [--fake-model] [--seed N]

`--party level1_team` replaces the scenario's Hero 1, Hero 6, Hero 3 and Hero 4 (same id, square and initiative) with the
builds in `sim/parties/level1_team.json` (SRD 5.2.1, 2024 rules, level 1: Fighter with Greatsword/Graze and Savage
Attacker; Protector Cleric with Bless, Healing Word, Guiding Bolt; Rogue with Rapier and Shortbow (Vex), Sneak Attack;
Wizard with Mage Armor cast before the day, Fire Bolt, Magic Missile, Shield) and plays them with `sim/party.py`:
focus fire on one foe (seen by any member who is up, or heard: an attacker is not hidden), the Fighter guards the
casters, the Rogue sets up Sneak Attack (an ally next to the target, or Advantage from Vex, Guiding Bolt or an unseen
attack), the Cleric opens with Bless and keeps one slot for Healing Word (moving until she can see a fallen ally), and
with no slot left stabilizes with the Help action (DC 10 Medicine); the Wizard keeps her slot for Shield unless Magic
Missile surely removes a foe on her or on a fallen ally. One Spell with a Spell Slot per Turn, Concentration saves, and
Death Saving Throws (with damage at 0 HP and the Unconscious automatic critical) are simulated for this party. Without
`--party` nothing changes. Measured 2026-10-14 (scripted monsters, seeds 1-20): watch temple simple 13 won / 2 lost /
5 out of rounds, 25 characters dropped; team 20 won, 11 dropped (8 of them Hero 1 in front), 6.5 rounds; ward chamber
simple 19/1, 12 dropped; team 20/0, 3 dropped. Ollama-played monsters, watch temple seeds 1-3: team won 3/3 (one death
before stabilizing was added).

## PARTY-02 (2026-10-14): the seven SRD pregenerated characters

    py sim/run_sim.py sim/scenarios/watch_temple_interior.json --party srd_pregens [--party-level 2] [--fake-model] [--seed N]

`sim/parties/srd_pregens.json` holds the seven characters of `AI_Adventures/pregens/builds.json` (Hero 1 Fighter, Hero 3
Rogue, Hero 5 Barbarian, Hero 4 Wizard, Hero 6 Paladin, Hero 2 Cleric, Vex Warlock). The scenario's Hero 1, Hero 6, Hero 3 and
Hero 4 are replaced as with PARTY-01 (Hero 6 is the Paladin here); Hero 5, Hero 2 and Vex join on free squares next to the
party, in sight of it, with the initiative in the party file. `--party-level 2` applies each member's `at_level` changes
(hit points; the Paladin's Defense, Lay On Hands 10 and Divine Smite; Reckless Attack; Agonizing Blast; more slots).
New tactics in `sim/party.py`: the Barbarian Rages on its first turn (Resistance to Bludgeoning, Piercing and Slashing
in the fake FG), steps to and uses its fire Breath Weapon when a 15-ft Cone or 30-ft Line catches two foes and no ally
(Dexterity saves from the scenario's `dex_save`), otherwise Greataxe with Cleave; the Paladin uses Lay On Hands on a
fallen or Bloodied ally, Bless when no one concentrates on it, Longsword with Sap (the struck foe's next attack roll has
Disadvantage), Divine Smite from level 2 on a Critical Hit or the focus target; the Warlock casts Hex on the focus target
and Eldritch Blast every turn from range. Bless now takes at most three creatures (the attackers first).

## SIM-INTERRUPT-01 (2026-10-14): players' opportunity attacks (first slice)

A scenario with `"gm_mode": "suggest"` runs the bridge in Suggest mode and the simulator plays the GM on the bridge
page (the same POST routes and session token as the page's buttons): it approves each NPC suggestion once; when the
move provokes (status `oa_wait`) it opens a reaction window for the players named in `provokes`, in initiative order
(SRD 5.2.1 Simultaneous Effects: on the NPC's turn the DM orders them; this is the recorded order). Each player is
checked again at the window (0 HP, Reaction used, incapacitating effect, mover already down, a weapon, sight of the
square the mover left) and answers from `"reaction_policy"` (`{"*": "accept"}`, per CT id, `"pass"` keeps the
Reaction). Then Continue, once; or End turn when the opportunity attack dropped the NPC (FG refuses an attack by a
creature at 0 HP, so Continue would leave the turn hanging; the page's card offers End turn for this). NPC
opportunity-attack cards are approved at once. `"fake_target"` makes the scripted chooser go for that character.
The report lists each window: trigger, responder, choice, Reaction before/after, outcome, resume point.
Scenario: sim/scenarios/pc_reactions.json (SRD 5.2.1 Bandit). Tests: test_sim_reactions.py (accept, pass, mixed,
Reaction already used and reset at her turn start, Disengage, the NPC dropped by the first attack, a second Continue
refused with 409). Autopilot scenarios are unchanged. Not yet: Shield as a decision window, NPC stat-block reactions,
Ready, legendary actions, a local-model player policy; the live bridge still never asks players automatically.

## PARTY-03 (2026-10-14): Bard tactics (the GM's Hero 1)

sim/parties/calix.json: Hero 1, Human Bard 5 (College of Valor), converted from the GM's D&D Beyond PDF.
`--party calix` adds him (combine with another party in code: apply_party twice, as test_party_bard.py does).
sim/party.py turn_bard: Cure Wounds on a fallen ally he can reach this turn (touch, 2d8 + 4, one slot); a front-liner
casts Shillelagh (Bonus Action, 1 minute; d10 at level 5) and closes in, otherwise gives Bardic Inspiration (Bonus
Action, 60 ft, one die per creature, d8 at level 5, uses = Charisma modifier) to the ally who attacks most; out of melee
reach he uses Vicious Mockery when the target's `wis_save` is known and +1 or lower (2d6 Psychic, Disadvantage on its
next attack roll: `sim_mocked` in the fake FG), else Starry Wisp (2d8, 60 ft). A holder rolls the die after a missed
attack roll when it can still turn the miss into a hit (fake FG hook SIM.inspireMiss); a Valor die can instead be used
when the holder is hit (Combat Inspiration: Defense, a Reaction, +die to AC against that attack only: reactHit now
returns (bonus, lasting)). Rules from SRD 5.2.1; Combat Inspiration from the character's sheet (College of Valor is not
in the SRD). Not modelled: his other slot spells, Font of Inspiration's slot-for-die, Combat Inspiration: Offense,
Heroic Inspiration, War Caster's Reactive Spell; slots are one pool of nine. Tests: test_party_bard.py (11).

## PARTY-04 (2026-10-15): the SRD pregens at levels 3-7

    py sim/run_sim.py sim/scenarios/road_forge.json --party srd_pregens --party-level 5 [--fake-model] [--seed N]
    py tools/encounter_tuner.py <scenario> --target moderate --level 5        # levels 1-7; 8+ is refused

`sim/parties/srd_pregens.json` has `at_level` "3".."7" for all seven, from `AI_Adventures/pregens/ROADMAPS.md` (ASIs and
subclass choices) and the SRD 5.2.1 class tables (checked in DNDSRD521PLAYER.mod): hit points (the class die's average +
Con per level; Hero 1 and Hero 5's Con 16 at 4 counts for every level), Proficiency Bonus +3 from 5, attack and damage
from the ASIs (Hero 1 Str 18/20 at 4/6, Hero 5 Str 18 at 4, Hero 3 Dex 19 at 4, Hero 4 Int 19, Hero 6 Cha 16, Hero 2 Wis 19,
Vex Cha 19 at 4), AC (Hero 3 15, Hero 5 14 at 4), spell attack/DC, `slots` as a list per slot level ([4, 3, 2]; the Warlock
[0, 0, 2] = two level 3 Pact slots; a plain number is still level 1 slots), Sneak Attack 2d6/3d6/4d6, Rages 3/4, Lay On
Hands 5 x level, Breath Weapon 2d10 x3 DC 14 at 5, Fast Movement 40 ft., Fire Bolt 2d10 and Sacred Flame 2d8 at 5.
Tests: test_party_levels.py (rules helpers, the data against them, slot pools, directed fights, fake FG hooks, tuner).

Modelled in `sim/party.py` (and the fake FG):
- Extra Attack (Fighter, Paladin, Barbarian 5): two attacks per Attack action; the move comes before the first, a second
  attack goes to the same foe or, once it drops, another foe already in reach (no movement between attacks). Riders per
  attack: Graze on each miss, Sap on each hit, Cleave once per turn, Divine Smite once per turn (Bonus Action; Paladin's
  Smite first, then the highest slot: 3d8 with a level 2 slot), Savage Attacker once per turn (fake FG).
- Hero 1: Improved Critical 19-20 (3); Action Surge (2; once a fight, on the turn a foe in reach is the toughest one left
  or three or more foes remain; no move); Second Wind x3 from 4.
- Hero 3: Steady Aim (3; Bonus Action before moving when no ally is next to the target and no Vex/Guiding Bolt: Advantage,
  then the attack); Uncanny Dodge (5; Reaction, halves a hit's damage from an attacker it sees: fake FG `SIM.dodgeHit`,
  `sim_halve_next`).
- Hero 5: the Breath Weapon replaces one of the two attacks (it still swings once after breathing); Frenzy (3; Reckless
  while raging: Rage Damage d6s = 2d6 on the first target hit in the turn).
- Hero 4: Potent Cantrip (3; half the Fire Bolt damage on a miss); Scorching Ray (3; level 2 slot only, three rays, an
  attack roll each, at a foe with 10+ HP, later rays to another foe once it drops; one slot always stays for Shield);
  Fireball (5; see below); Sculpt Spells (6; 1 + spell level allies she can see take nothing).
- Hero 6: Sacred Weapon (3; Channel Divinity, + Cha to attack rolls for the fight, taken with the first Attack action
  that has a foe in reach); Aura of Protection (6; + Cha to Concentration and death saving throws within 10 ft while
  she is up).
- Hero 2: Disciple of Life (3; + 2 + slot level to slot healing), Preserve Life (3; Magic action, 5 x level HP among
  Bloodied creatures within 30 ft, each up to half its maximum, a fallen ally first), Mass Healing Word (5; level 3 slot,
  two or more fallen allies in sight within 60 ft), Spirit Guardians (5; level 3 slot, Concentration, cast before Bless
  when a located foe is within her move + 15 ft, then she walks to the focus target; Wisdom save, 3d8 Radiant, half on a
  success: when her move brings the Emanation onto a foe (once per turn) and when a foe ends its turn in it (run loop
  hook `Party.turn_ended`); Concentration saves; ends at 0 HP), Sacred Flame 2d8 (5; Dexterity save; at 1-4 the
  Warhammer stays, it hits harder than a 1d8 cantrip), Blessed Healer (6).
- Vex: Eldritch Blast two beams (5; a separate attack roll each, Hex on each hit, the second beam to another foe if the
  first dropped it); Scorching Ray with a Pact slot (3; one slot stays for Fireball from 5; Hex adds to each ray hit);
  Fireball (5, level 3 Pact slots; level 4 at 7); Dark One's Blessing (3; Cha + level Temporary Hit Points when he drops
  a foe or one drops within 10 ft; the fake FG now takes damage from `sim_temp_hp` first, `SIM.getField`).
- Fireball (Hero 4, Vex): 150 ft, a point on a square's center or corner or between two foes, no wall on the way;
  20-ft-radius Sphere: a foe counts when its square's center is within 20 ft (walls block); cast only when two or more
  foes the party has located are inside and no ally (the caster, fallen allies too) is inside the 9 x 9-square box
  around the point (the stricter reading of a sphere on the grid); Dexterity save (`dex_save`, +0 when the scenario
  has none), 8d6 + 1d6 per slot level above 3, half on a success.

2026-10-15 level-1 audit (AI_Adventures/pregens, tools/sheets.py --sync-sim): Hero 3 wears Studded Leather (AC 15, 16 from
level 4), Hero 5 Scale Mail (AC 15); `--party srd_pregens_brakka_unarmored` keeps the unarmored Hero 5 for comparison.
Also not modelled from that audit: equipment, gold and carried weight, Stealth Disadvantage from Scale/Chain Mail,
Hero 4's Ice Knife (replaced Chromatic Orb), Vex's Hideous Laughter (replaced Protection from Evil and Good), tools,
languages, Healer's Kits, hands (drawing/stowing weapons to cast).

Not modelled (each build has it; the simulator does not use it):
- Everyone: movement between Extra Attack attacks; saving throws the party would make against monster effects (so
  Evasion, Danger Sense, Dark One's Own Luck, Aura of Devotion have nothing to act on); temporary flight; initiative
  features (Remarkable Athlete, Feral Instinct: initiative stays the scenario's); scenario creatures without `dex_save` /
  `wis_save` save at +0; a Large creature counts for an area by its own square's center only.
- Hero 1: Tactical Mind, Tactical Shift, Remarkable Athlete's move after a Critical Hit, the level 7 Additional Fighting
  Style (the roadmap leaves it open), Heroic Inspiration, Javelins.
- Hero 3: Cunning Action (Dash, Disengage, Hide), Cunning Strike, Longstrider, Pass without Trace (before the fight).
- Hero 5: Instinctive Pounce, Mindless Rage, Draconic Flight, the Handaxe (Vex).
- Hero 4: Magic Missile above level 1, Counterspell, Darkness (Infernal legacy); Ray of Frost's -10 ft
  Speed (the bridge is not told).
- Hero 6: Aid (8 hours: would have to be cast before the day with a slot), Protection from Evil and Good,
  Misty Step, Bless at a higher slot (a fourth creature), Faithful Steed.
- Hero 2: Aid, Revivify, Sear Undead, Blessed Strikes
  (7; the roadmap leaves the choice open), Spirit Guardians' halved Speed and a foe that only passes through it.
- Vex: Mirror Image, Counterspell, Darkness, Command, Suggestion,
  Stinking Cloud, the invocations of levels 5 and 7 (the roadmap leaves them open).

Level 2 changed too: Hero 1's Action Surge (a level 2 feature of his build) is now used from level 2. Chapter 2 tuning
measured before 2026-10-15 ran without it; rerun the tuner if those numbers matter.

Measured 2026-10-15 (scripted monsters): watch_temple_interior and road_forge with `--party srd_pregens --party-level`
3, 5 and 7, seeds 1-3: 18 runs, 0 stalls, 0 problems, 0 wall crossings; all won in 1-4 rounds without a character
dropping (level 1-2 encounters: a smoke test of the features, not a difficulty measure).
