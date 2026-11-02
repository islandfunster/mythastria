"""GM 2026-10-24 (SRD_GAPS_PLAN.md group 3): Short and Long Rests and the adventure day.

The party's state is carried across an adventure instead of every fight starting fresh: Hit Points, Temporary Hit
Points, spell slots, Sorcery Points, Innate Sorcery, Rage, Second Wind, Action Surge, Channel Divinity, Lay On Hands,
Bardic Inspiration, Dark One's Own Luck, Indomitable, the Breath Weapon, the free Divine Smite and Hellish Rebuke, the
Ask the GM feature uses (sim/live_asks.py), Exhaustion and the Hit Point Dice spent. (The bags are the Market's, already
kept.) A loaded adventure keeps one "day" (tools/sim_service.py: sim/adventures/days/<pack>.json): the clock, the rest
under way, each character's carried state and a log. A live fight on the adventure's maps starts from it (prepare,
apply) and writes it back when it ends (capture).

SRD 5.2.1 (Rules Glossary "Short Rest", "Long Rest"; Playing the Game "Resting"; each class's text):
- Short Rest: 1 hour; at least 1 Hit Point to start. Spend Hit Point Dice: each one rolled + the Constitution modifier
  (at least 1 HP), deciding after each roll. Features recharge as their text says: Pact Magic slots (all), Second Wind
  (one), Action Surge, Channel Divinity (one), Rage (one), Wild Shape (one), Monk's Focus Points (all), Bardic Inspiration
  from Bard 5 (Font of Inspiration: all), Sorcerous Restoration (Sorcerer 5: up to half the Sorcerer level in Sorcery
  Points, once per Long Rest), Arcane Recovery (Wizard: slots of combined level up to half the Wizard level rounded up,
  none of level 6+, once per Long Rest). An interrupted Short Rest confers no benefits.
- Long Rest: 8 hours; at least 1 Hit Point to start; after finishing one, at least 16 hours before starting another.
  All lost Hit Points and all spent Hit Point Dice back; slots and uses back; Exhaustion one level less; Temporary Hit
  Points end. Interrupted after at least 1 hour: the benefits of a Short Rest. Resumed at once: 1 more hour for each
  interruption. Rolling Initiative interrupts a rest (here: a live fight on the adventure's maps).
The GM's rule (2026-10-23): every prerequisite is checked with sim/requirements.py before a rest is offered, with the reason
and a link when it is not met.

RESTS-02 (GM 2026-10-26, goal 16), SRD 5.2.1:
- The rest goes on hour by hour (rest_until): each hour's hazards (sim/hazards.py advance) come in order, and a character
  with Trance (an Elf: "You can finish a Long Rest in 4 hours ... during which you retain consciousness") gets the Long
  Rest's benefits after 4 hours and can keep watch while the others rest on.
- Interruptions are each character's own (Short Rest and Long Rest "Interrupting the Rest"): taking any damage (hurt: a
  hazard, mental stress), casting a spell other than a cantrip (cast), Initiative rolled for a fight the character is in
  (before_fight), and for a Long Rest 1 hour of walking or other physical exertion (exert). An interrupted Short Rest
  confers no benefits on that character; a Long Rest resumed at once needs 1 more hour for that character.
- Death saves on the day ("Death Saving Throws", "Stabilizing a Character"): a character at 0 Hit Points after a fight, a
  hazard or travel goes on making them as time passes (settle_dying: one each 6 seconds, so it is settled before the
  first minute is out) or one at a time on the page (death_save), until it is stable, healed or dead. A DC 10 Wisdom
  (Medicine) check, a Healer's Kit or Spare the Dying stabilizes it; a stable creature regains 1 Hit Point after 1d4
  hours (hazards.advance wakes it). Damage at 0 Hit Points is a failed death save; damage that leaves Hit Points of
  the creature's maximum or more after reaching 0 kills it outright.
- Tireless (Ranger 10): each finished Short Rest removes 1 Exhaustion level. Natural Recovery (Druid 6, Circle of the
  Land, the SRD's Druid subclass): on a Short Rest, expended slots of combined level up to half the Druid level (rounded
  up), none of level 6+, once per Long Rest.
"""
import copy, json, math, re, threading
from pathlib import Path

import hazards
import light_sources
import monk
import requirements as rq

FORMAT = "mythastria-adventure-day/1"
START_HOUR = 8.0                      # Day 1, 08:00
SHORT_HOURS, LONG_HOURS, LONG_GAP = 1, 8, 16
TRANCE_HOURS = 4                      # RESTS-02: Elf's Trance
KIT, KIT_USES = "healers-kit", 10     # a Healer's Kit (sim/live_items.py), ten uses
MAX_LOG = 200
HIT_DIE = {"barbarian": 12, "fighter": 10, "paladin": 10, "ranger": 10, "bard": 8, "cleric": 8, "druid": 8, "monk": 8,
           "rogue": 8, "warlock": 8, "sorcerer": 6, "wizard": 6}
# Where an unmet need is fixed on the adventure home page (adventure-ui.mjs draws each as a button)
LINKS = {"fight": {"page": "./play.html", "label": "Back to the fight"},
         "time": {"page": "#day-pass", "label": "Pass time"},
         "long": {"page": "#day-long", "label": "Long Rest"},
         "market": rq.LINKS["market"], "characters": rq.LINKS["characters"]}

# The uses the simulator spends in a fight: key -> (label, the build's field, Short Rest: "one" | "all" | None)
USES = {
    "second_wind": ("Second Wind", "second_wind", "one"),
    "action_surge": ("Action Surge", "action_surge", "all"),
    "rages": ("Rage", "rages", "one"),
    "channel": ("Channel Divinity", "channel", "one"),
    "lay_on_hands": ("Lay On Hands (HP)", "lay_on_hands", None),
    "inspiration": ("Bardic Inspiration", "inspiration", None),     # all on a Short Rest from Bard 5 (Font of Inspiration)
    "sorcery_points": ("Sorcery Points", "sorcery_points", None),  # Sorcerous Restoration: below
    "innate_sorcery": ("Innate Sorcery", "innate_sorcery", None),
    "focus_points": ("Focus Points", "focus_points", "all"),      # MONK-01: Monk's Focus, all on a Short Rest
    "own_luck": ("Dark One's Own Luck", "own_luck", None),
    "indomitable": ("Indomitable", "indomitable", None),
    "breath": ("Breath Weapon", "breath", None),
    "smite": ("Divine Smite without a slot", "smite", None),        # Paladin's Smite: once per Long Rest
    "rebuke": ("Hellish Rebuke without a slot", "hellish_rebuke", None),   # Infernal Legacy: once per Long Rest
    # SPELLS-4-9: Mystic Arcanum (Warlock 11, 13, 15, 17): each one once per Long Rest, without a slot
    "arcanum_6": ("Mystic Arcanum (level 6)", "arcanum_6", None),
    "arcanum_7": ("Mystic Arcanum (level 7)", "arcanum_7", None),
    "arcanum_8": ("Mystic Arcanum (level 8)", "arcanum_8", None),
    "arcanum_9": ("Mystic Arcanum (level 9)", "arcanum_9", None),
    "dragon_wings": ("Dragon Wings", "dragon_wings", None),       # SORCERER-20: Draconic Sorcery 14, once per Long Rest
    # MARTIAL-HIGH (sim/martial_high.py): Stroke of Luck (Short or Long Rest), Intimidating Presence, Holy Nimbus (Long)
    "stroke_of_luck": ("Stroke of Luck", "stroke_of_luck", "all"),
    "intimidating_presence": ("Intimidating Presence", "intimidating_presence", None),
    "holy_nimbus": ("Holy Nimbus", "holy_nimbus", None),
}
# Ask the GM features (sheet resources) that come back on a Short Rest; any other comes back on a Long Rest only
FEATURE_SHORT = {"Wild Shape": "one", "Channel Divinity": "one", "Second Wind": "one", "Rage": "one",
                 "Action Surge": "all", "Focus Points": "all", "Monk's Focus": "all"}


class RestError(ValueError):
    pass


def mod(score):
    return (int(score) - 10) // 2


def clock_text(hour):
    day, rest = divmod(float(hour), 24)
    h, m = divmod(int(round(rest * 60)), 60)
    if h == 24:
        day, h = day + 1, 0
    return "Day %d, %02d:%02d" % (int(day) + 1, h, m)


def die_sides(die):
    return int(str(die).lstrip("d"))


# ------------------------------------------------------------------ a character's carried state
def pregen_build(name, level, party_file=None):
    """A pregen at a level, as run_sim.apply_party builds it (its at_level changes up to the level)."""
    party_file = party_file or Path(__file__).resolve().parent / "parties" / "srd_pregens.json"
    team = json.loads(Path(party_file).read_text(encoding="utf-8"))["members"]
    b = dict(team[name])
    for lv, changes in sorted((b.pop("at_level", None) or {}).items(), key=lambda kv: int(kv[0])):
        if int(lv) <= int(level or 1):
            b.update(changes)
    return b


def sheet_extras(sheet):
    """From a saved character's sheet, what a build lacks for resting: its Hit Point Dice by die, its Pact Magic slots and
    its class levels (multiclass). Keys start with rest_ (dicts: never sent to the fake FG)."""
    out = {}
    d = sheet.get("derived") if isinstance(sheet.get("derived"), dict) else {}
    hd = d.get("hit_dice")
    if isinstance(hd, dict) and hd and all(re.fullmatch(r"d(6|8|10|12)", k) and isinstance(v, int) and v > 0 for k, v in hd.items()):
        out["rest_hit_dice"] = dict(hd)
    pact = d.get("pact")
    if isinstance(pact, dict) and isinstance(pact.get("level"), int) and isinstance(pact.get("slots"), int):
        out["rest_pact"] = {"level": pact["level"], "slots": pact["slots"]}
    classes = {}
    for c in sheet.get("classes") or []:
        if isinstance(c, dict) and c.get("name") and isinstance(c.get("level"), int):
            classes[str(c["name"]).strip().lower()] = c["level"]
    if classes:
        out["rest_classes"] = classes
    # HAZARDS-01: species and armor for the environment's rules (Cackle Fever spares gnomes; armor in Extreme Heat)
    traits = {"species": str(sheet.get("species") or "")[:40],
              "equipment": [str(x)[:80] for x in (sheet.get("equipment") or [])[:60] if isinstance(x, str)]}
    if traits["species"] or traits["equipment"]:
        out["rest_traits"] = traits
    return out


def _slots(b):
    s = b.get("slots", 0)
    pool = [int(x) for x in s] if isinstance(s, list) else ([int(s)] if s else [])
    return pool if any(pool) else []


def entry_from_build(name, b, kind="pregen"):
    """A character's full state (after a Long Rest) from its build (a pregen at its level, a saved character's member
    build, or a fight's combatant)."""
    cls = str(b.get("class") or "fighter").lower()
    level = int(b.get("level") or 1)
    classes = dict(b.get("rest_classes") or {cls: level})
    con = mod((b.get("abilities") or {}).get("con", 10))
    hit_dice = dict(b.get("rest_hit_dice") or {})
    if not hit_dice:
        for k, n in classes.items():
            die = "d%d" % HIT_DIE.get(k, 8)
            hit_dice[die] = hit_dice.get(die, 0) + n
    slots = _slots(b)
    pact = b.get("rest_pact")
    if not pact and cls == "warlock" and len(classes) == 1 and slots:
        lv = max(i + 1 for i, n in enumerate(slots) if n)
        pact = {"level": lv, "slots": slots[lv - 1]}
    uses = {}
    for key, (_, field, _) in USES.items():
        v = b.get(field)
        if v is True:
            uses[key] = 1
        elif isinstance(v, int) and not isinstance(v, bool) and v > 0:
            uses[key] = v
    feats = {str(f["name"]): int(f["uses"]) for f in b.get("feature_list") or []
             if isinstance(f, dict) and f.get("name") and isinstance(f.get("uses"), int)}
    hp = int(b.get("hp") or 1)
    fields = hazards.entry_fields(b)                             # HAZARDS-01: saves, traits, contagions
    return dict({"name": name, "kind": kind, "class": cls, "classes": classes, "level": level, "con_mod": con,
                 "hp_max": hp, "hp": hp, "temp_hp": 0, "hit_dice": hit_dice, "hit_dice_left": dict(hit_dice),
                 "slots_max": slots, "slots": list(slots), "pact": pact, "uses_max": uses, "uses": dict(uses),
                 "features_max": feats, "features": dict(feats), "once": {}, "exhaustion": 0, "status": "ok",
                 "sig": [cls, level, hp], "fiendish": fiendish(b)}, **fields, **sheet_powers(b, fields["traits"]),
                **__import__("high_levels").day_powers(b))       # CASTER-HIGH: Magical Cunning, Eldritch Master


# GM 2026-10-27 (group 3; SRD 5.2.1 Fiend Patron 10, Fiendish Resilience): "Choose one damage type, other than Force,
# whenever you finish a Short or Long Rest. You have Resistance to that damage type until you choose a different one":
# the player picks it as a rest ends (the adventure page); the day keeps it; the next fight gives the Resistance.
RESILIENCE_TYPES = ("acid", "bludgeoning", "cold", "fire", "lightning", "necrotic", "piercing", "poison", "psychic",
                    "radiant", "slashing", "thunder")


def fiendish(b):
    return bool(b.get("fiendish_resilience_ok")) or any(isinstance(f, dict) and f.get("name") == "Fiendish Resilience"
                                                        for f in b.get("feature_list") or [])


def sheet_powers(b, traits):
    """RESTS-02: what a character brings to resting and to the dying: Trance (an Elf, or a sheet feature named Trance),
    its Wisdom (Medicine) bonus and whether it knows Spare the Dying (a saved sheet's spell list, a pregen's note)."""
    note = str(b.get("note") or "")
    feats = [str(f.get("name") or "") for f in b.get("feature_list") or [] if isinstance(f, dict)]
    spells = [str(x.get("name") or "") for x in b.get("spell_list") or [] if isinstance(x, dict)]
    medicine = b.get("medicine")
    if not isinstance(medicine, int) or isinstance(medicine, bool):
        medicine = mod((b.get("abilities") or {}).get("wis", 10))
    return {"trance": traits.get("species") == "Elf" or "Trance" in feats or bool(re.search(r"Trance", note)),
            "medicine": medicine,
            "spare_the_dying": "Spare the Dying" in spells or bool(re.search(r"Spare the Dying", note))}


def powers(e):
    """An entry from a day file made before RESTS-02: Trance from its species, the Medicine bonus from Wisdom."""
    e.setdefault("trance", (e.get("traits") or {}).get("species") == "Elf")
    e.setdefault("medicine", int((e.get("saves") or {}).get("wis", 0)))
    e.setdefault("spare_the_dying", False)
    e.setdefault("death", {"successes": 0, "failures": 0})
    return e


def short_view(e):
    """The character's state in words for the page."""
    return {"name": e["name"], "class": e["class"], "level": e["level"], "hp": e["hp"], "hp_max": e["hp_max"],
            "temp_hp": e["temp_hp"], "hit_dice": [{"die": d, "left": e["hit_dice_left"].get(d, 0), "total": n}
                                                for d, n in sorted(e["hit_dice"].items(), key=lambda kv: -die_sides(kv[0]))],
            "con_mod": e["con_mod"], "slots": [{"level": i + 1, "left": e["slots"][i], "max": n}
                                                for i, n in enumerate(e["slots_max"]) if n],
            "pact": e.get("pact"),
            "uses": [{"key": k, "label": USES[k][0], "left": e["uses"].get(k, 0), "max": n} for k, n in e["uses_max"].items()],
            "features": [{"name": k, "left": e["features"].get(k, 0), "max": n} for k, n in e["features_max"].items()],
            "exhaustion": e["exhaustion"], "status": e["status"], "once": dict(e["once"]),
            "trance": bool(e.get("trance")), "death": dict(e.get("death") or {"successes": 0, "failures": 0}),
            "wakes": clock_text(e["wake_at"]) if e["status"] == "stable" and e.get("wake_at") is not None else None}


# ------------------------------------------------------------------ the day
def new_day(pack):
    return {"format": FORMAT, "pack": pack, "hour": START_HOUR, "last_long_rest_end": None, "rest": None,
            "party": {}, "log": [], "fights": 0}


def say(day, text):
    day["log"] = (day["log"] + [{"hour": day["hour"], "when": clock_text(day["hour"]), "text": text}])[-MAX_LOG:]


def ensure(day, builds):
    """builds: {name: (build, kind)}. A character the day doesn't know yet joins at full strength; one whose sheet
    changed (class, level or HP maximum) starts again from the new sheet. -> the names."""
    for name, (b, kind) in builds.items():
        fresh = entry_from_build(name, b, kind)
        old = day["party"].get(name)
        if old is None:
            day["party"][name] = fresh
        elif old.get("sig") != fresh["sig"]:
            # GM 2026-11-01: the new sheet applies now, damage kept; any change to its current Hit Points is the GM's
            changed_hp = fresh["hp_max"] != old["hp_max"]
            if changed_hp:
                fresh["hp"] = min(old["hp"], fresh["hp_max"])
            # HAZARDS-01: Exhaustion, contagions and lasting effects are the character's, not the sheet's
            fresh["exhaustion"] = int(old.get("exhaustion") or 0)
            if fresh.get("fiendish") and old.get("fiendish_resilience"):     # group 3: the type chosen stays
                fresh["fiendish_resilience"] = old["fiendish_resilience"]
            fresh.update({k: copy.deepcopy(old[k]) for k in hazards.KEEP if k in old})
            if old.get("status") in ("dying", "stable", "dead"):     # RESTS-02: the dying stay dying
                fresh["hp"], fresh["status"] = 0, old["status"]
                fresh.update({k: copy.deepcopy(old[k]) for k in ("death", "wake_at") if k in old})
            day["party"][name] = fresh
            say(day, "%s's sheet changed (%s %d): the new sheet applies now%s." % (
                name, fresh["class"].title(), fresh["level"],
                "; its Hit Point maximum is now %d (%d/%d HP): the GM decides any change to its current Hit Points" % (
                    fresh["hp_max"], fresh["hp"], fresh["hp_max"]) if changed_hp else ""))
    return list(builds)


def can_rest(e):
    """SRD 5.2.1: at least 1 Hit Point to start a rest."""
    if e["status"] == "dead":
        return rq.need("alive", False, "%s is dead: a rest does not bring a character back." % e["name"])
    return rq.need("at least 1 Hit Point", e["hp"] >= 1, "%s has 0 Hit Points: a creature needs at least 1 Hit Point to "
                   "start a rest (stabilize or heal them first)." % e["name"])


def rest_needs(day, kind, names, fight_running):
    needs = [rq.need("no fight running", not fight_running, "A fight is running: finish it before resting (rolling "
                     "Initiative interrupts a rest).", LINKS["fight"]),
             rq.need("no rest under way", not day.get("rest"), "A %s Rest is under way: finish or stop it first."
                     % ((day.get("rest") or {}).get("kind") or "").title())]
    party = [day["party"][n] for n in names if n in day["party"]]
    needs.append(rq.need("the party", bool(party), "Choose the party first (The party, on the left)."))
    if party:
        needs.append(rq.need("someone able to rest", any(can_rest(e)["met"] for e in party),
                             "No one can rest: " + " ".join(can_rest(e)["why"] for e in party)))
    if kind == "long" and day.get("last_long_rest_end") is not None:
        ready_at = day["last_long_rest_end"] + LONG_GAP
        needs.append(rq.need("16 hours since the last Long Rest", day["hour"] + 1e-9 >= ready_at,
                             "The last Long Rest ended %s; after a Long Rest a creature waits at least 16 hours before "
                             "starting another: the next can start %s." % (clock_text(day["last_long_rest_end"]),
                                                                            clock_text(ready_at)), LINKS["time"]))
    return needs


def die_needs(day, name, die):
    r = day.get("rest") or {}
    e = day["party"].get(name)
    needs = [rq.need("a Short Rest under way", r.get("kind") == "short", "Hit Point Dice are spent during a Short Rest: "
                     "start one first.")]
    if not e:
        return needs + [rq.need("the character", False, "%s is not in the party." % name)]
    needs.append(rq.need("resting", name in r.get("names", []), "%s is not resting (they had 0 Hit Points or joined "
                         "later)." % name))
    pending = [d for d in (r.get("dice") or {}).get(name, []) if d["die"] == die]
    left = e["hit_dice_left"].get(die, 0) - len(pending)
    needs.append(rq.need("a Hit Point Die left", left > 0, "%s has no %s Hit Point Dice left: spent dice come back with a "
                         "Long Rest." % (name, die) if die in e["hit_dice"] else "%s has no %s Hit Point Dice." % (name, die),
                         LINKS["long"] if die in e["hit_dice"] else None))
    healed = e["hp"] + sum(d["hp"] for d in (r.get("dice") or {}).get(name, []))
    needs.append(rq.need("Hit Points to regain", healed < e["hp_max"], "%s is at full Hit Points already (%d)." % (name, e["hp_max"])))
    return needs


def offers(day, names, fight_running):
    out = {}
    for kind in ("short", "long"):
        ready, rows = rq.check(rest_needs(day, kind, names, fight_running))
        out[kind] = {"ready": ready, "why": rq.first_why(rows), "link": rq.first_link(rows), "needs": rows}
    return out


def view(day, names, fight_running=False):
    """What the adventure home page shows: the clock, the rest under way, the offers, each character."""
    r = day.get("rest")
    chars = []
    for n in names:
        e = day["party"].get(n)
        if not e:
            continue
        v = short_view(e)
        v["can_rest"] = can_rest(e)
        v["hazards"] = hazards.entry_view(e, day["hour"])       # HAZARDS-01: Exhaustion's effects, contagions, stress
        if e["status"] in ("dying", "stable"):                   # RESTS-02: death saves and stabilizing on the day
            v["dying"] = dying_view(day, names, e)
        if r and n in r["names"]:                                # RESTS-02: this character's own rest
            done = (r.get("done") or {}).get(n)
            v["resting"] = {"ends": clock_text(done if done is not None else own_end(day, n)), "done": done is not None,
                            "extra": int((r.get("extra") or {}).get(n, 0)), "trance": r["kind"] == "long" and bool(e.get("trance"))}
        elif r and n in (r.get("lost") or {}):
            v["resting"] = {"lost": r["lost"][n]}
        if r and r["kind"] == "short" and n in r["names"]:
            v["pending"] = list((r.get("dice") or {}).get(n, []))
            v["dice_offers"] = []
            for d in e["hit_dice"]:
                ready, rows = rq.check(die_needs(day, n, d))
                v["dice_offers"].append({"die": d, "ready": ready, "why": rq.first_why(rows), "link": rq.first_link(rows)})
            v["short_choices"] = short_choices(e)
        if e.get("magical_cunning"):                             # CASTER-HIGH: Magical Cunning (Eldritch Master)
            v["magical_cunning"] = cunning_offer(day, e, fight_running)
        if e.get("fiendish"):                                    # group 3: Fiendish Resilience
            v["resilience"] = e.get("fiendish_resilience")
            if r and n in r["names"]:
                v["resilience_choice"] = list(RESILIENCE_TYPES)
        chars.append(v)
    rest = None
    if r:
        hours = rest_end(day) - r["start"]
        rest = dict(r, ends=clock_text(r["start"] + hours), hours=hours, started=clock_text(r["start"]),
                    elapsed=round(day["hour"] - r["start"], 4), lost=sorted(r.get("lost") or {}))
    ready_at = None if day.get("last_long_rest_end") is None else day["last_long_rest_end"] + LONG_GAP
    return {"pack": day["pack"], "hour": day["hour"], "clock": clock_text(day["hour"]), "rest": rest,
            "last_long_rest": None if day.get("last_long_rest_end") is None else clock_text(day["last_long_rest_end"]),
            "next_long_rest": None if ready_at is None else clock_text(ready_at),
            "offers": offers(day, names, fight_running), "characters": chars, "log": day["log"][-40:],
            "fights": day.get("fights", 0), "fight_running": bool(fight_running),
            "environment": {k: v for k, v in hazards.environment(day).items() if k != "exposure"},
            "pace": dict(hazards.pace_rule(day, names), last=day.get("travel")),
            "lights": light_sources.day_view(day)}                # LIGHTS-01: the lights each character holds


def short_choices(e):
    """The Short Rest choices a character has: Arcane Recovery (Wizard) and Sorcerous Restoration (Sorcerer 5)."""
    out = {}
    wiz = e["classes"].get("wizard", 0)
    if wiz and not e["once"].get("arcane_recovery"):
        budget = math.ceil(wiz / 2)
        spent = [{"level": i + 1, "spent": n - e["slots"][i]} for i, n in enumerate(e["slots_max"])
                 if i + 1 < 6 and n - e["slots"][i] > 0 and i + 1 <= budget]
        out["arcane_recovery"] = {"budget": budget, "spent": spent}
    sor = e["classes"].get("sorcerer", 0)
    if sor >= 5 and not e["once"].get("sorcerous_restoration") and "sorcery_points" in e["uses_max"]:
        missing = e["uses_max"]["sorcery_points"] - e["uses"].get("sorcery_points", 0)
        out["sorcerous_restoration"] = {"most": min(sor // 2, missing), "missing": missing}
    dru = e["classes"].get("druid", 0)
    if dru >= 6 and not e["once"].get("natural_recovery"):     # RESTS-02: Circle of the Land
        budget = math.ceil(dru / 2)
        spent = [{"level": i + 1, "spent": n - e["slots"][i]} for i, n in enumerate(e["slots_max"])
                 if i + 1 < 6 and n - e["slots"][i] > 0 and i + 1 <= budget]
        out["natural_recovery"] = {"budget": budget, "spent": spent}
    return out


# ------------------------------------------------------------------ resting
def start_rest(day, kind, names, fight_running):
    if kind not in ("short", "long"):
        raise RestError("A rest is short or long.")
    ready, rows = rq.check(rest_needs(day, kind, names, fight_running))
    if not ready:
        raise RestError(rq.first_why(rows))
    resting = [n for n in names if n in day["party"] and can_rest(day["party"][n])["met"]]
    left_out = [n for n in names if n in day["party"] and n not in resting]
    day["rest"] = {"kind": kind, "start": day["hour"], "names": resting, "interruptions": 0, "dice": {},
                   "extra": {}, "done": {}, "lost": {}}                 # RESTS-02: each character's own rest
    trance = [n for n in resting if kind == "long" and powers(day["party"][n])["trance"]]
    say(day, "%s Rest begins (%d hour%s): %s.%s%s" % (
        kind.title(), LONG_HOURS if kind == "long" else SHORT_HOURS, "s" if kind == "long" else "", ", ".join(resting),
        (" Trance: %s finish%s in %d hours, conscious all along, and can keep watch." % (
            ", ".join(trance), "es" if len(trance) == 1 else "", TRANCE_HOURS)) if trance else "",
        (" Not resting: " + " ".join(can_rest(day["party"][n])["why"] for n in left_out)) if left_out else ""))
    return day["rest"]


# ------------------------------------------------------------------ RESTS-02: each character's own rest
def own_end(day, n):
    """When this character's rest ends: a Short Rest 1 hour; a Long Rest 8 hours (4 with Trance), +1 hour per
    interruption (the GM's for everyone, and this character's own)."""
    r = day["rest"]
    if r["kind"] == "short":
        return r["start"] + SHORT_HOURS
    e = powers(day["party"].get(n) or {})
    return (r["start"] + (TRANCE_HOURS if e["trance"] else LONG_HOURS) + r.get("interruptions", 0)
            + (r.get("extra") or {}).get(n, 0))


def rest_end(day):
    r = day["rest"]
    done = r.get("done") or {}
    ends = [done[n] if n in done else own_end(day, n) for n in r["names"]]
    return max(ends) if ends else max(day["hour"], r["start"])


def _finish_early(day):
    """A character whose own Long Rest is over before the others' (Trance) gets its benefits now and keeps watch."""
    r = day["rest"]
    if r["kind"] != "long":
        return
    end = rest_end(day)
    for n in r["names"]:
        e = day["party"].get(n)
        mine = own_end(day, n)
        if n in r.setdefault("done", {}) or not e or e["status"] == "dead" or mine > day["hour"] + 1e-9 or mine >= end - 1e-9:
            continue
        r["done"][n] = mine
        say(day, "%s finishes the Long Rest after %g hours%s and can keep watch while the others rest: %s." % (
            n, mine - r["start"], " (Trance)" if e.get("trance") else "", _long_benefits(n, e, hour=mine)))


def rest_until(day, names, to, roll):
    """The rest goes on to `to` (at most its end): the hours' hazards in order (sim/hazards.py advance), a character with
    Trance finishing on the way. The clock moves with it."""
    r = day.get("rest")
    if not r:
        raise RestError("No rest is under way.")
    to = min(to, rest_end(day))
    while True:
        _finish_early(day)
        if day["hour"] >= to - 1e-9 or day.get("rest") is not r:
            break
        marks = [own_end(day, n) for n in r["names"] if r["kind"] == "long" and n not in r.get("done", {})]
        step = min([m for m in marks if day["hour"] + 1e-9 < m < to - 1e-9] + [to])
        hazards.advance(day, names, day["hour"], step, roll)
        day["hour"] = step


def interrupt_one(day, name, why):
    """SRD 5.2.1 "Interrupting the Rest", for one character: an interrupted Short Rest confers no benefits on it; its
    Long Rest, resumed at once, needs 1 more hour. A character whose rest is over already (Trance) is not interrupted.
    -> "lost", "resumed" or None."""
    r = day.get("rest")
    if not r or name not in r["names"] or name in (r.get("done") or {}):
        return None
    why = str(why or "an interruption").strip()[:120]
    if r["kind"] == "short":
        r["names"].remove(name)
        r.setdefault("lost", {})[name] = why
        (r.get("dice") or {}).pop(name, None)
        if r["names"]:
            say(day, "%s's Short Rest is interrupted (%s): no benefits for %s (an interrupted Short Rest confers none)."
                % (name, why, name))
        else:
            day["rest"] = None
            say(day, "The Short Rest is interrupted (%s): an interrupted Short Rest confers no benefits." % why)
        return "lost"
    r.setdefault("extra", {})[name] = r["extra"].get(name, 0) + 1
    say(day, "%s's Long Rest is interrupted (%s) and resumed at once: 1 more hour for %s (it now ends %s)." % (
        name, why, name, clock_text(own_end(day, name))))
    return "resumed"


def exert(day, names, hours, why):
    """Walking or other physical exertion during a rest (SRD 5.2.1 Long Rest: 1 hour of it interrupts the rest)."""
    r = day.get("rest")
    if not r:
        raise RestError("No rest is under way.")
    if not isinstance(hours, (int, float)) or isinstance(hours, bool) or not 0 < hours <= 24:
        raise RestError("How long they walked or toiled: more than 0, up to 24 hours.")
    why = str(why or "walking").strip()[:120]
    who = [n for n in names if n in r["names"] and n not in (r.get("done") or {})]
    if not who:
        raise RestError("No one named is resting now (a character done with its rest may keep watch, walk and work).")
    if hours < 1:
        say(day, "%s: %s for %g minutes: less than 1 hour of exertion does not interrupt the rest." % (
            ", ".join(who), why, round(hours * 60)))
        return []
    return [(n, interrupt_one(day, n, "%s, %g hour%s" % (why, hours, "" if hours == 1 else "s"))) for n in who]


def spend_die(day, name, die, roll):
    """One Hit Point Die rolled during a Short Rest (roll: sides -> 1..sides): die + Constitution modifier, at least 1 HP.
    Kept as pending until the rest finishes (an interrupted Short Rest confers no benefits)."""
    ready, rows = rq.check(die_needs(day, name, die))
    if not ready:
        raise RestError(rq.first_why(rows))
    e = day["party"][name]
    n = roll(die_sides(die))
    hp = max(1, n + e["con_mod"])
    weak = hazards.restless(hazards.fill(e), day["hour"])        # HAZARDS-01: Sewer Plague's Weakness
    if weak:
        hp //= 2
    entry = {"die": die, "roll": n, "con": e["con_mod"], "hp": hp}
    if weak:
        entry["half"] = True
    day["rest"].setdefault("dice", {}).setdefault(name, []).append(entry)
    say(day, "%s spends a Hit Point Die: %s %d %+d = %d HP%s (when the rest ends)." % (
        name, die, n, e["con_mod"], hp, " (half: Sewer Plague)" if weak else ""))
    return entry


def _short_benefits(day, e, dice, choices):
    """The benefits of a finished Short Rest for one character. -> what came back, in words."""
    got = []
    if dice:
        heal = sum(d["hp"] for d in dice)
        before = e["hp"]
        e["hp"] = min(e["hp_max"], e["hp"] + heal)
        for d in dice:
            e["hit_dice_left"][d["die"]] -= 1
        got.append("%d Hit Point Di%s: +%d HP (%d/%d)" % (len(dice), "e" if len(dice) == 1 else "ce", e["hp"] - before, e["hp"], e["hp_max"]))
    if e.get("pact"):
        lv = e["pact"]["level"]
        if lv <= len(e["slots"]) and e["slots"][lv - 1] < e["slots_max"][lv - 1]:
            e["slots"][lv - 1] = e["slots_max"][lv - 1]
            got.append("Pact Magic slots (level %d: %d)" % (lv, e["slots"][lv - 1]))
    for key, (label, _, rule) in USES.items():
        most, left = e["uses_max"].get(key), e["uses"].get(key)
        if most is None or left >= most:
            continue
        if key == "inspiration" and e["classes"].get("bard", 0) >= 5:
            rule = "all"                                        # Font of Inspiration (Bard 5)
        if rule == "one":
            e["uses"][key] = left + 1; got.append("one %s use (%d/%d)" % (label, e["uses"][key], most))
        elif rule == "all":
            e["uses"][key] = most; got.append("%s (%d)" % (label, most))
    for name, most in e["features_max"].items():
        rule, left = FEATURE_SHORT.get(name), e["features"].get(name, 0)
        if rule and left < most:
            e["features"][name] = most if rule == "all" else left + 1
            got.append("%s %s (%d/%d)" % ("one" if rule == "one" else "all", name, e["features"][name], most))
    ch = short_choices(e)
    for key, label, who in (("arcane_recovery", "Arcane Recovery", "a Wizard"),
                            ("natural_recovery", "Natural Recovery", "a Druid of level 6 or more")):   # RESTS-02
        want = (choices.get(key) or {}).get(e["name"])
        if not want:
            continue
        if key not in ch:
            raise RestError("%s can't use %s now (%s, once per Long Rest)." % (e["name"], label, who))
        levels = [int(x) for x in want] if isinstance(want, list) else []
        budget = ch[key]["budget"]
        if not levels or any(not 1 <= lv <= 5 for lv in levels) or sum(levels) > budget:
            raise RestError("%s: slots of combined level up to %d, none of level 6 or higher." % (label, budget))
        for lv in levels:
            if lv > len(e["slots"]) or e["slots"][lv - 1] >= e["slots_max"][lv - 1]:
                raise RestError("%s has no spent level %d slot to recover." % (e["name"], lv))
            e["slots"][lv - 1] += 1
        e["once"][key] = True
        got.append("%s: level %s slot%s" % (label, ", ".join(map(str, levels)), "s" if len(levels) > 1 else ""))
    if (choices.get("sorcerous_restoration") or {}).get(e["name"]):
        if "sorcerous_restoration" not in ch:
            raise RestError("%s can't use Sorcerous Restoration now (Sorcerer 5, once per Long Rest)." % e["name"])
        n = ch["sorcerous_restoration"]["most"]
        e["uses"]["sorcery_points"] += n
        e["once"]["sorcerous_restoration"] = True
        got.append("Sorcerous Restoration: +%d Sorcery Points (%d/%d)" % (n, e["uses"]["sorcery_points"], e["uses_max"]["sorcery_points"]))
    if (e.get("once") or {}).get("free_casts") and e.get("signature"):   # CASTER-HIGH: Signature Spells
        __import__("high_levels").short_rest(e)
        got.append("Signature Spells: %s without a slot again" % " and ".join(e["signature"]))
    if e["classes"].get("ranger", 0) >= 10 and e["exhaustion"]:  # RESTS-02: Tireless
        ex = e["exhaustion"]
        hazards.lose_exhaustion(e, 1)
        if e["exhaustion"] < ex:
            got.append("Tireless: Exhaustion %d -> %d" % (ex, e["exhaustion"]))
    return got


def finish_rest(day, choices=None):
    """The rest ends after its time; its benefits for each character who rested."""
    r = day.get("rest")
    if not r:
        raise RestError("No rest is under way.")
    choices = choices if isinstance(choices, dict) else {}
    work = copy.deepcopy(day["party"])                         # a refused choice changes nothing
    lines = []
    if r["kind"] == "short":
        for n in r["names"]:
            got = _short_benefits(day, work[n], (r.get("dice") or {}).get(n, []), choices)
            lines.append("%s: %s" % (n, "; ".join(got) if got else "nothing to regain"))
    else:
        end, done = rest_end(day), r.get("done") or {}
        for n in r["names"]:
            if n in done:                                        # RESTS-02: finished early (Trance)
                continue
            if work[n]["status"] == "dead":
                lines.append("%s: dead" % n)
                continue
            lines.append(_long_benefits(n, work[n], hour=end))
    for n in r["names"]:                                         # group 3: Fiendish Resilience, either rest
        want = (choices.get("fiendish_resilience") or {}).get(n)
        if not want:
            continue
        if not work[n].get("fiendish") or want not in RESILIENCE_TYPES:
            raise RestError("%s: Fiendish Resilience takes one damage type other than Force." % n)
        work[n]["fiendish_resilience"] = want
        lines.append("%s: Fiendish Resilience, Resistance to %s damage" % (n, want.title()))
    hours = rest_end(day) - r["start"]
    day["party"] = work
    day["hour"] = max(day["hour"], r["start"] + hours)
    if r["kind"] == "long":
        day["last_long_rest_end"] = day["hour"]
    day["rest"] = None
    say(day, "%s Rest ends (%s). %s" % (r["kind"].title(), "%g hour%s" % (hours, "" if hours == 1 else "s"), " ".join(l + "." for l in lines)))
    return lines


def _long_benefits(n, e, hour=None, dm=False):
    """A Long Rest's benefits for one character (SRD 5.2.1): all Hit Points and Hit Point Dice, slots and uses back,
    Temporary Hit Points end, Exhaustion one level less. HAZARDS-01: Sewer Plague's Restlessness (while it has any
    Exhaustion: no lost Hit Points back, no Exhaustion removed; the GM's restore (dm) still heals), and levels a source
    holds (Cackle Fever, dehydration, malnutrition) stay. Returns the log line."""
    hazards.fill(e)
    restless = hour is not None and hazards.restless(e, hour)
    if not restless or dm:
        e["hp"] = e["hp_max"]
    e["temp_hp"] = 0
    e["hit_dice_left"] = dict(e["hit_dice"])
    e["slots"], e["uses"], e["features"], e["once"] = list(e["slots_max"]), dict(e["uses_max"]), dict(e["features_max"]), {}
    __import__("high_levels").long_rest(e)                       # CASTER-HIGH: Greater Divine Intervention's 2d4
    ex = e["exhaustion"]
    if not restless:
        hazards.lose_exhaustion(e, 1)
    held = ""
    if restless:
        held = "; Sewer Plague: no Exhaustion removed%s" % (" (the GM restores the Hit Points)" if dm else
                                                           ", no lost Hit Points back")
    elif ex and e["exhaustion"] == ex and hazards.locked(e):
        held = "; %d Exhaustion level%s held (%s)" % (hazards.locked(e), "" if hazards.locked(e) == 1 else "s",
                                                      ", ".join(k.replace("_", " ") for k in e["locks"]))
    return "%s: %s Hit Point Dice, slots and uses%s%s" % (
        n, "all Hit Points," if (not restless or dm) else "all", ("; Exhaustion %d -> %d" % (ex, e["exhaustion"])) if ex else "",
        held)


def restore(day, names, fight_running=False):
    """GM 2026-10-25 ("DM should be able to restore party to full health and rest at the start of a map"): the GM gives
    the party a Long Rest's benefits now, before a map's fight: no time passes and no rest rule is checked (the GM's
    call); a rest under way ends. Not while a fight runs (its end writes the party back)."""
    if fight_running:
        raise RestError("A fight is running: restore the party before Start live fight, or end the fight first.")
    lines = [_long_benefits(n, day["party"][n], hour=day["hour"], dm=True) for n in names if n in day["party"]]
    day["rest"] = None
    day["last_long_rest_end"] = day["hour"]
    say(day, "The GM restores the party (a Long Rest's benefits, no time passes). %s" % " ".join(l + "." for l in lines))
    return lines


def interrupt(day, why):
    """Something interrupts the rest and the party goes on resting at once. A Short Rest is lost (no benefits); a Long
    Rest resumed needs 1 more hour per interruption."""
    r = day.get("rest")
    if not r:
        raise RestError("No rest is under way.")
    why = str(why or "an interruption").strip()[:120]
    if r["kind"] == "short":
        day["rest"] = None
        say(day, "The Short Rest is interrupted (%s): an interrupted Short Rest confers no benefits." % why)
        return "lost"
    r["interruptions"] = r.get("interruptions", 0) + 1
    say(day, "The Long Rest is interrupted (%s) and resumed: %d more hour%s to finish it." % (
        why, r["interruptions"], "" if r["interruptions"] == 1 else "s"))
    return "resumed"


def stop(day, hours, why):
    """The party stops resting after `hours` (None: the hours rested so far). A Long Rest stopped after at least 1 hour
    gives the benefits of a Short Rest: the rest becomes a Short Rest to finish (Hit Point Dice can be spent). Otherwise no
    benefits. RESTS-02: a character whose Long Rest is over already (Trance) keeps its benefits."""
    r = day.get("rest")
    if not r:
        raise RestError("No rest is under way.")
    elapsed = day["hour"] - r["start"]
    if hours is None:
        hours = elapsed
    if not isinstance(hours, (int, float)) or isinstance(hours, bool) or not 0 <= hours <= 24:
        raise RestError("How long they rested: 0 to 24 hours.")
    if hours < elapsed - 1e-9:
        raise RestError("They have rested %g hours already (it is %s)." % (round(elapsed, 2), clock_text(day["hour"])))
    why = str(why or "they stopped").strip()[:120]
    day["hour"] = r["start"] + hours
    done = r.get("done") or {}
    rest_on = [n for n in r["names"] if n not in done and day["party"][n]["status"] != "dead"]
    kept = (" %s finished the Long Rest already (%s)." % (", ".join(done), ", ".join(clock_text(h) for h in done.values()))
            if done else "")
    if r["kind"] == "long" and hours >= 1 and rest_on:
        day["rest"] = {"kind": "short", "start": day["hour"] - SHORT_HOURS, "names": rest_on, "interruptions": 0,
                       "dice": {}, "from_long": True, "extra": {}, "done": {}, "lost": {}}
        say(day, "The Long Rest stops after %g hour%s (%s): at least 1 hour rested, so the benefits of a Short Rest "
            "(spend Hit Point Dice, then finish it).%s" % (hours, "" if hours == 1 else "s", why, kept))
        return "short"
    if r["kind"] == "long" and done and not rest_on:
        day["last_long_rest_end"] = max(done.values())
    day["rest"] = None
    say(day, "The %s Rest stops after %g hour%s (%s): no benefits%s.%s" % (
        r["kind"].title(), hours, "" if hours == 1 else "s", why, " for the others" if done else "", kept))
    return "none"


def pass_time(day, hours, why=""):
    if day.get("rest"):
        raise RestError("A rest is under way: finish or stop it first.")
    if not isinstance(hours, (int, float)) or isinstance(hours, bool) or not 0 < hours <= 240:
        raise RestError("Time passes in hours: more than 0, up to 240.")
    day["hour"] += hours
    say(day, "%g hour%s pass%s." % (hours, "" if hours == 1 else "s", (" (%s)" % str(why).strip()[:120]) if why else ""))


# CASTER-HIGH (GM 2026-10-28; SRD 5.2.1 Warlock 2 and 20): Magical Cunning, "an esoteric rite for 1 minute. At the end of
# it, you regain expended Pact Magic spell slots but no more than a number equal to half your maximum (round up). Once
# you use this feature, you can't do so again until you finish a Long Rest"; Eldritch Master: all of them.
def cunning_needs(day, e, fight_running):
    once = e["once"].get("magical_cunning")
    pact = e.get("pact") or {}
    lv = int(pact.get("level") or 0)
    spent = e["slots_max"][lv - 1] - e["slots"][lv - 1] if 0 < lv <= len(e["slots"]) else 0
    return [rq.need("no fight running", not fight_running, "A fight is running: the 1-minute rite comes after it.",
                    LINKS["fight"]),
            rq.need("no rest under way", not day.get("rest"), "A rest is under way: finish or stop it first."),
            rq.need("conscious", e["status"] == "ok", "%s is %s." % (e["name"], e["status"])),
            rq.need("once per Long Rest", not once, "%s used Magical Cunning since the last Long Rest." % e["name"],
                    LINKS["long"]),
            rq.need("a spent Pact Magic slot", spent > 0, "%s has no expended Pact Magic slot to regain." % e["name"])]


def cunning_offer(day, e, fight_running):
    ready, rows = rq.check(cunning_needs(day, e, fight_running))
    pact = e.get("pact") or {}
    most = e["slots_max"][pact["level"] - 1] if pact.get("level") and pact["level"] <= len(e["slots_max"]) else 0
    return {"ready": ready, "why": rq.first_why(rows), "link": rq.first_link(rows),
            "regains": "all its Pact Magic slots (Eldritch Master)" if e.get("eldritch_master") else
            "up to %d Pact Magic slot%s (half the maximum, rounded up)" % (-(-most // 2), "" if -(-most // 2) == 1 else "s")}


def magical_cunning(day, name, fight_running=False):
    e = day["party"].get(name)
    if not e or not e.get("magical_cunning"):
        raise RestError("%s has no Magical Cunning (Warlock 2)." % name)
    ready, rows = rq.check(cunning_needs(day, e, fight_running))
    if not ready:
        raise RestError(rq.first_why(rows))
    back = __import__("high_levels").magical_cunning(e, e.get("eldritch_master"))
    e["once"]["magical_cunning"] = True
    day["hour"] += 1 / 60.0
    lv = e["pact"]["level"]
    say(day, "%s performs Magical Cunning's 1-minute rite: %d Pact Magic slot%s back%s (level %d: %d/%d)." % (
        name, back, "" if back == 1 else "s", ", Eldritch Master: all of them" if e.get("eldritch_master") else "",
        lv, e["slots"][lv - 1], e["slots_max"][lv - 1]))
    return back


def set_exhaustion(day, name, level, why=""):
    e = day["party"].get(name)
    if not e:
        raise RestError("%s is not in the party." % name)
    if not isinstance(level, int) or isinstance(level, bool) or not 0 <= level <= 6:
        raise RestError("Exhaustion is a level from 0 to 6.")
    old, e["exhaustion"] = e["exhaustion"], level
    if level == 6:
        e["status"], e["hp"] = "dead", 0
    say(day, "The GM sets %s's Exhaustion: %d -> %d%s%s." % (name, old, level, (" (%s)" % str(why).strip()[:120]) if why else "",
                                                                ": Exhaustion level 6 is death" if level == 6 else ""))


def reset(day):
    pack = day["pack"]
    day.clear()
    day.update(new_day(pack))
    say(day, "A new adventure day: the party starts at full strength.")


# ------------------------------------------------------------------ RESTS-02: damage, the dying and healing on the day
def _alive(day, name):
    e = day["party"].get(name)
    if not e:
        raise RestError("%s is not in the party." % name)
    if e["status"] == "dead":
        raise RestError("%s is dead." % name)
    return powers(hazards.fill(e))


def hurt(day, name, amount, kinds="", why="", crit=False, hour=None, interrupt=True, out=None):
    """Damage on the adventure day (a hazard, mental stress): Resistance halves it, Immunity stops it, Temporary Hit Points
    take it first. At 0 Hit Points it is a failed death save (two for a Critical Hit; damage of the Hit Point maximum or
    more kills); damage that leaves the maximum or more after reaching 0 kills outright (SRD 5.2.1 "Instant Death"). It
    interrupts the character's rest (interrupt=False: the caller does, after its line; out["taken"]: the damage taken).
    -> the line in words (the caller logs it)."""
    e = _alive(day, name)
    hour = day["hour"] if hour is None else hour
    t = e.get("traits") or {}
    types = [k for k in str(kinds or "").lower().replace(",", " ").split() if k]
    n = max(0, int(amount))
    note = ""
    if types and all(k in t.get("immune", []) for k in types):
        n, note = 0, " (Immunity)"
    elif types and any(k in t.get("resist", []) for k in types):
        n, note = n // 2, " (Resistance: halved)"
    text = "%s takes %d%s damage%s" % (name, n, (" " + "/".join(types).title()) if types else "", note)
    if out is not None:
        out["taken"] = n
    if n <= 0:
        return text
    soak = min(int(e.get("temp_hp") or 0), n)
    e["temp_hp"] -= soak
    left = n - soak
    death = e.setdefault("death", {"successes": 0, "failures": 0})
    if e["hp"] == 0 and left:
        was = e["status"]
        e["status"] = "dying"
        e.pop("wake_at", None)
        if left >= e["hp_max"]:
            e["status"] = "dead"
            text += ": at 0 Hit Points, damage of its Hit Point maximum or more: dead"
        else:
            death["failures"] += 2 if crit else 1
            text += ": at 0 Hit Points, %s (%d of 3)%s" % ("two failed death saves" if crit else "a failed death save",
                                                          min(3, death["failures"]), "; no longer Stable" if was == "stable" else "")
            if death["failures"] >= 3:
                e["status"] = "dead"
                text += ": dead"
    elif left:
        over = left - e["hp"]
        e["hp"] = max(0, e["hp"] - left)
        text += " (%d/%d HP%s)" % (e["hp"], e["hp_max"], ", %d to Temporary Hit Points" % soak if soak else "")
        if e["hp"] == 0:
            if over >= e["hp_max"]:
                e["status"] = "dead"
                text += ": the damage left over is its Hit Point maximum or more: dead (Instant Death)"
            else:
                e["status"], e["death"] = "dying", {"successes": 0, "failures": 0}
                text += ": 0 Hit Points, Unconscious and dying (death saves until stable, healed or dead)"
    else:
        text += " (all to Temporary Hit Points)"
    if interrupt and day.get("rest"):
        interrupt_one(day, name, why or "damage")
    return text


def damage(day, names, dice, kinds, why, roll):
    """The GM's hazard damage on the day (a fall, burning, a collapsing roof: SRD 5.2.1 Hazards): each named character
    rolls its own dice. -> the lines in words."""
    why = str(why or "a hazard").strip()[:120]
    who = [n for n in names if n in day["party"] and day["party"][n]["status"] != "dead"]
    if not who:
        raise RestError("Choose who takes the damage.")
    try:
        hazards.roll_dice(lambda s: 1, dice)                     # the form only
    except hazards.HazardError as err:
        raise RestError(str(err))
    lines = []
    for n in who:
        dealt, got = hazards.roll_dice(roll, dice), {}
        text = "%s%s, %s = %d: %s" % (why[:1].upper(), why[1:], dice, dealt,
                                       hurt(day, n, dealt, kinds, hour=day["hour"], interrupt=False, out=got))
        say(day, text + ".")
        if got.get("taken") and day.get("rest"):
            interrupt_one(day, n, "%s: damage" % why)
        lines.append(text)
    return lines


def _death_roll(e, roll):
    """One death save (SRD 5.2.1): 10+ a success, a 1 two failures, a 20 regains 1 Hit Point; Exhaustion's -2 per level
    applies (a D20 Test). -> (the outcome, the roll in words)."""
    d = roll(20)
    pen = 2 * int(e.get("exhaustion") or 0)
    st = e.setdefault("death", {"successes": 0, "failures": 0})
    if d == 20:
        e["death"] = {"successes": 0, "failures": 0}
        return "revive", "20"
    total = d - pen
    st["failures" if total < 10 else "successes"] += 2 if d == 1 else 1
    word = "%d%s" % (d, " -%d = %d" % (pen, total) if pen else "")
    if st["failures"] >= 3:
        return "dead", word
    if st["successes"] >= 3:
        return "stable", word
    return ("success" if total >= 10 else "failure"), word


def make_stable(day, e, hour, roll, how):
    e["status"], e["death"] = "stable", {"successes": 0, "failures": 0}
    e["wake_at"] = hour + roll(4)
    return "%s is stable (%s): it regains 1 Hit Point after 1d4 hours, at %s" % (e["name"], how, clock_text(e["wake_at"]))


def revive(e, hp):
    e["hp"], e["status"], e["death"] = min(e["hp_max"], max(1, int(hp))), "ok", {"successes": 0, "failures": 0}
    e.pop("wake_at", None)


def death_save(day, name, roll, hour=None):
    """One death save for a dying character on the day (a round goes by). -> the line in words."""
    e = _alive(day, name)
    if e["status"] != "dying":
        raise RestError("%s is not dying (%s)." % (name, "stable" if e["status"] == "stable" else "%d HP" % e["hp"]))
    hour = day["hour"] if hour is None else hour
    out, word = _death_roll(e, roll)
    st = e["death"]
    text = "%s's death save: %s -> %s" % (name, word, {"success": "a success", "failure": "a failure", "revive": "a 20",
                                                      "stable": "a third success", "dead": "a third failure"}[out])
    if out == "revive":
        revive(e, 1)
        text += ": regains 1 Hit Point and is conscious"
    elif out == "stable":
        text += ": " + make_stable(day, e, hour, roll, "three successes")
    elif out == "dead":
        e["status"] = "dead"
        text += ": dead"
    else:
        text += " (%d successes, %d failures)" % (st["successes"], min(3, st["failures"]))
    say(day, text + ".")
    return text


def settle_dying(day, names, roll, hour):
    """Time passes on the day: a dying character makes a death save each 6 seconds until it is stable, conscious or dead
    (it is settled within the first minute); a stable one without a waking time gets its 1d4 hours."""
    for n in names:
        e = day["party"].get(n)
        if not e or e["status"] not in ("dying", "stable"):
            continue
        powers(e)
        if e["status"] == "stable":
            if e.get("wake_at") is None:
                say(day, make_stable(day, e, hour, roll, "as before") + ".")
            continue
        rolls = []
        while True:
            out, word = _death_roll(e, roll)
            rolls.append(word)
            if out in ("revive", "stable", "dead"):
                break
        if out == "revive":
            revive(e, 1)
            end = "a 20: regains 1 Hit Point and is conscious"
        elif out == "stable":
            end = make_stable(day, e, hour, roll, "three successes")
        else:
            e["status"], end = "dead", "three failures: dead"
        _hazard_log(day, hour, "Time passes while %s is dying: death saves %s -> %s." % (n, ", ".join(rolls), end))


def _hazard_log(day, hour, text):
    day["log"] = (day["log"] + [{"hour": hour, "when": clock_text(hour), "text": text}])[-MAX_LOG:]


def wake(day, e, hour):
    """A stable creature regains 1 Hit Point after its 1d4 hours (hazards.advance calls this at the hour)."""
    revive(e, 1)
    _hazard_log(day, hour, "%s regains 1 Hit Point after 1d4 hours stable, and is conscious." % e["name"])


def stabilize_needs(day, patient, helper, how, bag=None):
    p, h = day["party"].get(patient), day["party"].get(helper)
    needs = [rq.need("the patient", p is not None, "%s is not in the party." % patient),
             rq.need("dying", bool(p and p["status"] == "dying"), "%s is not dying (%s)." % (
                 patient, "unknown" if not p else p["status"] if p["status"] != "ok" else "%d HP" % p["hp"])),
             rq.need("the helper", h is not None, "%s is not in the party." % helper)]
    if h is not None:
        needs.append(rq.need("a conscious helper", h["status"] == "ok" and h["hp"] > 0 and helper != patient,
                             "%s can't help: %s." % (helper, "it is the one dying" if helper == patient else
                                                    "at 0 Hit Points" if h["status"] != "dead" else "dead")))
        if how == "spare":
            needs.append(rq.need("Spare the Dying", powers(h)["spare_the_dying"], "%s doesn't know Spare the Dying (a "
                                 "Cleric or Druid cantrip on the sheet)." % helper, LINKS["characters"]))
        elif how == "kit" and bag is not None:
            needs.append(rq.in_bag(bag, KIT, "Healer's Kit"))
    needs.append(rq.need("a way", how in ("medicine", "kit", "spare"), "Stabilize with a Wisdom (Medicine) check, a "
                         "Healer's Kit or Spare the Dying."))
    return needs


def stabilize(day, patient, helper, how, roll, bag=None):
    """SRD 5.2.1 "Stabilizing a Character": a DC 10 Wisdom (Medicine) check (on a failure a round goes by: the patient's
    death save), a Healer's Kit (one use, no check) or Spare the Dying. -> the lines in words."""
    ready, rows = rq.check(stabilize_needs(day, patient, helper, how, bag))
    if not ready:
        err = RestError(rq.first_why(rows))
        err.link = rq.first_link(rows)
        raise err
    p, h, hour = powers(day["party"][patient]), powers(day["party"][helper]), day["hour"]
    if how == "kit":
        left = bag.use_charge(KIT, KIT_USES, "stabilize %s" % patient) if bag is not None else None
        text = make_stable(day, p, hour, roll, "%s's Healer's Kit%s" % (
            helper, "" if left is None else ", %d use%s left" % (left, "" if left == 1 else "s")))
    elif how == "spare":
        text = make_stable(day, p, hour, roll, "%s casts Spare the Dying" % helper)
    else:
        d, bonus = roll(20), int(h["medicine"]) - 2 * int(h.get("exhaustion") or 0)
        line = "%s's Wisdom (Medicine) check DC 10: d20 %d %+d = %d" % (helper, d, bonus, d + bonus)
        if d + bonus >= 10:
            text = make_stable(day, p, hour, roll, line + ", a success")
        else:
            say(day, line + ": a failure; a round goes by.")
            return [line + ": a failure", death_save(day, patient, roll)]
    say(day, text + ".")
    return [text]


def heal(day, name, hp, why):
    """Hit Points regained on the day (a potion, a spell, the GM): a creature at 0 Hit Points is conscious again."""
    e = _alive(day, name)
    if not isinstance(hp, int) or isinstance(hp, bool) or not 1 <= hp <= 999:
        raise RestError("Hit Points regained: 1 to 999.")
    before = e["hp"]
    if before == 0:
        revive(e, hp)
    else:
        e["hp"] = min(e["hp_max"], before + hp)
    text = "%s regains %d Hit Points (%s): %d/%d HP%s" % (name, hp, str(why or "healing")[:120], e["hp"], e["hp_max"],
                                                          ", conscious again" if before == 0 else "")
    say(day, text + ".")
    return text


def cast(day, name, level, spell, roll, target=None, dice=""):
    """A spell cast on the adventure day (SRD 5.2.1: a spell other than a cantrip interrupts the caster's rest): a slot
    of its level spent; healing dice heal the target. -> the lines in words."""
    e = _alive(day, name)
    if e["hp"] <= 0:
        raise RestError("%s is at 0 Hit Points and can't cast." % name)
    if not isinstance(level, int) or isinstance(level, bool) or not 0 <= level <= 9:
        raise RestError("A spell's level: 0 (a cantrip) to 9.")
    spell = str(spell or "a spell").strip()[:60]
    if level:
        if level > len(e["slots"]) or e["slots"][level - 1] <= 0:
            err = RestError("%s has no level %d spell slot left%s." % (name, level, " (Pact Magic slots come back with "
                            "a Short Rest)" if e.get("pact") else " (slots come back with a Long Rest)"))
            err.link = LINKS["long"]
            raise err
        e["slots"][level - 1] -= 1
    lines = ["%s casts %s%s" % (name, spell, " (a level %d slot: %d left)" % (level, e["slots"][level - 1]) if level
                                 else " (a cantrip)")]
    if dice:
        if not target:
            raise RestError("Healing needs a target.")
        try:
            n = hazards.roll_dice(roll, dice)
        except hazards.HazardError as err:
            raise RestError(str(err))
        say(day, lines[0] + ".")
        lines.append(heal(day, target, max(1, n), "%s's %s, %s" % (name, spell, dice)))
    else:
        say(day, lines[0] + ".")
    if level and day.get("rest"):
        interrupt_one(day, name, "casting %s, a spell other than a cantrip" % spell)
    return lines


def dying_view(day, names, e):
    """What the page offers for a dying or stable character: its death saves and who can stabilize it how."""
    out = {"status": e["status"], "successes": int((e.get("death") or {}).get("successes", 0)),
           "failures": int((e.get("death") or {}).get("failures", 0)),
           "wakes": clock_text(e["wake_at"]) if e.get("wake_at") is not None else None, "helpers": []}
    if e["status"] == "dying":
        for n in names:
            h = day["party"].get(n)
            if not h or n == e["name"] or h["status"] != "ok" or h["hp"] <= 0:
                continue
            powers(h)
            out["helpers"].append({"name": n, "medicine": int(h["medicine"]) - 2 * int(h.get("exhaustion") or 0),
                                   "spare": bool(h["spare_the_dying"])})
    return out


def after_fight(day, names, roll):
    """When a fight on the adventure ends: a character left stable gets its 1d4 hours; one still dying goes on making death
    saves on the day. -> lines for the day's log."""
    lines = []
    for n in names:
        e = day["party"].get(n)
        if not e:
            continue
        powers(e)
        if e["status"] == "stable" and e.get("wake_at") is None:
            e["death"] = {"successes": 0, "failures": 0}
            e["wake_at"] = day["hour"] + roll(4)
            lines.append("%s is stable: it regains 1 Hit Point at %s" % (n, clock_text(e["wake_at"])))
        elif e["status"] == "dying":
            d = e["death"]
            lines.append("%s is dying (%d successes, %d failures): death saves go on (Roll a death save, or stabilize it)"
                         % (n, d["successes"], d["failures"]))
    return lines


# ------------------------------------------------------------------ fights: start from the day, write back at the end
def before_fight(day, names):
    """A live fight on the adventure: rolling Initiative interrupts the rest of each character in it (RESTS-02: the
    others rest on). -> the names the day carries."""
    for n in names:
        if day.get("rest"):
            interrupt_one(day, n, "a fight: Initiative is rolled")
    return [n for n in names if n in day["party"]]


def prepare_scenario(sc, day):
    """Before the simulator starts: each carried character's Hit Points (as wounds)."""
    for c in sc["combatants"]:
        e = day["party"].get(c.get("name")) if c.get("pc") else None
        if e:
            c["wounds"] = max(0, int(c.get("hp") or e["hp_max"]) - e["hp"])
            if e.get("fiendish_resilience"):                     # group 3: Fiendish Resilience's chosen type
                c["fiendish_resilience"] = e["fiendish_resilience"]


def apply_to_sim(sim, day):
    """After the simulator (and its Party) started: the carried slots, uses, Temporary Hit Points, Exhaustion and death
    state, in the places the fight code spends them."""
    party = getattr(sim, "party", None)                  # a stand-in or partyless simulator carries nothing
    if not party:
        return []
    s = sim.S
    gm, env = sim.gm_rules, getattr(sim, "env", None)
    carried = []
    for c in sim.sc["combatants"]:
        e = day["party"].get(c["name"]) if c.get("pc") else None
        if not e:
            continue
        i = c["id"]
        carried.append(c["name"])
        if e["slots_max"]:
            party.init_slots(i, list(e["slots"]))
        u = e["uses"]
        for key, table in (("rages", party.rages), ("lay_on_hands", party.loh), ("inspiration", party.bi_uses),
                           ("action_surge", party.surges), ("channel", party.channel), ("sorcery_points", party.sorcery),
                           ("innate_sorcery", party.innate_left), ("breath", party.breaths),
                           ("focus_points", monk._state(party, "focus_left"))):
            if key in e["uses_max"]:
                table[i] = u.get(key, 0)
        monk.perfect_focus(party, i)                             # GM 2026-10-28: Perfect Focus (Monk 15), Initiative
        if "smite" in e["uses_max"]:
            party.free_smite[i] = u.get("smite", 0) > 0
        if "rebuke" in e["uses_max"]:
            party.rebuke_free[i] = u.get("rebuke", 0) > 0
        __import__("high_levels").superior_inspiration(party, i, c)   # Bard 18: two uses at least as the fight starts
        if "second_wind" in e["uses_max"]:
            sim.second_winds[i] = u.get("second_wind", 0)
        for lv in range(6, 10):                                  # SPELLS-4-9: the Mystic Arcanum uses left
            if "arcanum_%d" % lv in e["uses_max"]:
                party.__dict__.setdefault("arcanum_left", {}).setdefault(i, {})[lv] = u.get("arcanum_%d" % lv, 0)
        if "dragon_wings" in e["uses_max"]:                      # SORCERER-20: sim/live_sorcery.py wings_left
            party.__dict__.setdefault("wings_left", {})[i] = u.get("dragon_wings", 0)
        __import__("high_levels").from_day(party, i, e)          # CASTER-HIGH: Overchannel, Hurl, Divine Intervention
        __import__("martial_high").day_apply(party, i, e)        # MARTIAL-HIGH: Stroke of Luck and the rest
        if gm and "own_luck" in e["uses_max"]:
            gm.__dict__.setdefault("luck", {})[i] = u.get("own_luck", 0)
        if gm and "indomitable" in e["uses_max"]:
            gm.__dict__.setdefault("indomitable_left", {})[i] = u.get("indomitable", 0)
        if e["features_max"]:
            party.__dict__.setdefault("ask_uses", {})[i] = dict(e["features"])
        if e["temp_hp"] > (s.getField(i, "sim_temp_hp") or 0):
            s.setField(i, "sim_temp_hp", e["temp_hp"])
        if env is not None and e["exhaustion"]:
            env.exhaustion[i] = env.carried[i] = e["exhaustion"]
        if e["status"] == "dead":
            party.deaths[i]["dead"] = True
        elif e["status"] == "stable":
            party.deaths[i]["stable"] = True
        elif e["status"] == "dying":                             # RESTS-02: the death saves made on the day go on
            d = e.get("death") or {}
            party.deaths[i].update(successes=int(d.get("successes", 0)), failures=int(d.get("failures", 0)))
    hz = getattr(sim, "hazards", None)
    if hz is not None:
        hz.from_day(day)                                         # HAZARDS-01: contagions, Sight Rot, the day's weather
    lt = getattr(sim, "lights", None)
    if lt is not None:
        lt.from_day(day)                                         # LIGHTS-01: the lights each character holds
    return carried


def capture(sim, day):
    """When the fight ends: what each carried character has left. -> lines for the day's log."""
    party = getattr(sim, "party", None)                  # a stand-in or partyless simulator carries nothing
    if not party:
        return []
    s = sim.S
    gm, env = sim.gm_rules, getattr(sim, "env", None)
    lines = []
    for c in sim.sc["combatants"]:
        e = day["party"].get(c["name"]) if c.get("pc") else None
        if not e:
            continue
        i = c["id"]
        wounds = int(s.state(i)[0] or 0)
        e["hp"] = max(0, min(e["hp_max"], e["hp_max"] - wounds))
        e["temp_hp"] = int(s.getField(i, "sim_temp_hp") or 0)
        if e["slots_max"]:
            pool = list(party.pools.get(i) or [])
            e["slots"] = [max(0, min(int(pool[k]) if k < len(pool) else 0, n)) for k, n in enumerate(e["slots_max"])]
        for key, table in (("rages", party.rages), ("lay_on_hands", party.loh), ("inspiration", party.bi_uses),
                           ("action_surge", party.surges), ("channel", party.channel), ("sorcery_points", party.sorcery),
                           ("innate_sorcery", party.innate_left), ("breath", party.breaths),
                           ("focus_points", monk._state(party, "focus_left"))):
            if key in e["uses_max"] and i in table:
                e["uses"][key] = max(0, int(table[i]))
        if "smite" in e["uses_max"]:
            e["uses"]["smite"] = 1 if party.free_smite.get(i) else 0
        if "rebuke" in e["uses_max"]:
            e["uses"]["rebuke"] = 1 if party.rebuke_free.get(i, True) else 0
        if "second_wind" in e["uses_max"]:
            e["uses"]["second_wind"] = int(sim.second_winds.get(i, e["uses"]["second_wind"]))
        for lv in range(6, 10):
            key = "arcanum_%d" % lv
            if key in e["uses_max"]:
                e["uses"][key] = int((party.__dict__.get("arcanum_left") or {}).get(i, {}).get(lv, e["uses"][key]))
        if "dragon_wings" in e["uses_max"]:
            e["uses"]["dragon_wings"] = int((party.__dict__.get("wings_left") or {}).get(i, e["uses"]["dragon_wings"]))
        __import__("high_levels").to_day(party, i, e)            # CASTER-HIGH: Overchannel, Hurl, Divine Intervention
        __import__("martial_high").day_capture(party, i, e)      # MARTIAL-HIGH
        if gm and "own_luck" in e["uses_max"]:
            e["uses"]["own_luck"] = int(getattr(gm, "luck", {}).get(i, e["uses"]["own_luck"]))
        if gm and "indomitable" in e["uses_max"]:
            e["uses"]["indomitable"] = int(gm.__dict__.get("indomitable_left", {}).get(i, e["uses"]["indomitable"]))
        if e["features_max"]:
            left = (party.__dict__.get("ask_uses") or {}).get(i) or {}
            e["features"] = {k: int(left.get(k, e["features"].get(k, 0))) for k in e["features_max"]}
        if env is not None:
            e["exhaustion"] = int(env.exhaustion.get(i, 0))
        death = party.deaths.get(i) or {}
        e["status"] = "dead" if death.get("dead") else "ok" if e["hp"] > 0 else "stable" if death.get("stable") else "dying"
        e["death"] = ({"successes": int(death.get("successes", 0)), "failures": int(death.get("failures", 0))}
                      if e["status"] == "dying" else {"successes": 0, "failures": 0})       # RESTS-02
        if e["status"] != "stable":
            e.pop("wake_at", None)
        lines.append("%s %d/%d HP%s" % (c["name"], e["hp"], e["hp_max"], {"ok": "", "dead": " (dead)", "stable": " (stable)",
                                                                          "dying": " (dying)"}[e["status"]]))
    hz = getattr(sim, "hazards", None)
    if hz is not None:
        lines += hz.to_day(day)                                  # HAZARDS-01: contagions caught, lasting stress
    lt = getattr(sim, "lights", None)
    if lt is not None:
        lines += lt.to_day(day)                                  # LIGHTS-01: the lights each character holds
    return lines


# ------------------------------------------------------------------ the days kept on disk
class Days:
    """The adventure days, one file per pack in `folder()` (None: kept in memory only, e.g. a service without adventures)."""
    PACK = re.compile(r"^[A-Za-z0-9_.-]{1,80}$")

    def __init__(self, folder=lambda: None):
        self.folder, self.lock, self.memory = folder, threading.RLock(), {}

    def path(self, pack):
        f = self.folder()
        return Path(f) / ("%s.json" % pack) if f else None

    def get(self, pack):
        if not isinstance(pack, str) or not self.PACK.match(pack):
            raise RestError("An adventure is named by its pack id.")
        with self.lock:
            if pack in self.memory:
                return self.memory[pack]
            p, day = self.path(pack), None
            if p and p.is_file():
                try:
                    day = json.loads(p.read_text(encoding="utf-8"))
                except (OSError, ValueError):
                    day = None
                if not isinstance(day, dict) or day.get("format") != FORMAT:
                    raise RestError("The adventure day file %s can't be read." % p)
            self.memory[pack] = day or new_day(pack)
            return self.memory[pack]

    def save(self, pack):
        with self.lock:
            p = self.path(pack)
            if not p:
                return
            p.parent.mkdir(parents=True, exist_ok=True)
            tmp = p.with_suffix(".tmp")
            tmp.write_text(json.dumps(self.memory[pack], indent=1), encoding="utf-8")
            tmp.replace(p)
