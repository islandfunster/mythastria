"""GM 2026-11-01: Sorcerous Burst's types, and the rules that went to Ask the GM, in real fights.
  py -3 -m unittest test_rulings_ask_gm
"""
import copy, json, sys, threading, unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent
sys.path[:0] = [str(ROOT / "sim"), str(ROOT / "tools"), str(ROOT / "mythastria_core")]
import character_build as cb
import encounter_tuner
import live_play
import martial_high
import rests
import run_sim
import sim_service
import traps

BURST = {"name": "Sorcerous Burst", "atk": 7, "dmg": "1d8", "dmgtype": "acid", "reach": 120, "cantrip": True, "crit": 20,
         "dmg_choices": list(cb.CANTRIP_CHOICES["Sorcerous Burst"])}
HERO = {"class": "sorcerer", "level": 5, "hp": 40, "ac": 15, "speed": "30", "init": 30, "abilities": {"str": 10, "dex": 14, "con": 14, "int": 10, "wis": 10, "cha": 18},
        "skills": [], "tools": [], "attacks": 1, "slots": [4, 3, 2], "weapon": {"name": "Dagger", "atk": 5, "dmg": "1d4+2", "dmgtype": "piercing", "reach": 5, "crit": 20}, "ranged": BURST,
        "spell_list": [{"name": "Chromatic Orb", "level": 1}, {"name": "Spirit Guardians", "level": 3}], "feature_list": []}


def start(scenario="test/live_keep.json", build=None):
    raw = json.loads((ROOT / "sim" / "scenarios" / scenario).read_text(encoding="utf-8"))
    sc = encounter_tuner.with_party(raw, ["Mage"], 5, extra={"Mage": copy.deepcopy(build or HERO)})
    sim = run_sim.Sim(sc, "scripted", True, 1, True, True)
    fight = live_play.LiveFight(sim, rounds=3).start()
    assert fight.wait_ready(120), "the fight never reached a character's turn"
    return fight


class Fight(unittest.TestCase):
    scenario, build = "test/live_keep.json", None

    def setUp(self):
        self.f = start(self.scenario, self.build)
        self.me = next(c["id"] for c in self.f.sim.sc["combatants"] if c["name"] == "Mage")

    def tearDown(self):
        self.f.quit(); self.f.thread.join(30)

    def offers(self):
        return self.f.snapshot(999999)["offers"]

    def asks(self):
        return {a["name"]: a for a in self.offers()["asks"]}

    def act(self, **cmd):
        return self.f.act(dict(cmd, revision=self.f.snapshot(999999)["revision"]))


class NoFreeze(Fight):
    """Found by the 2026-11-02 Seven Isles play-test: a timed condition ending while a player's offers were built wrote to
    the log under the fight's lock, and the table froze for everyone."""

    def test_the_log_can_be_written_under_the_fights_lock(self):
        done = []

        def write():
            with self.f.lock:
                self.f.sim.say("turn", "A condition ends")
            done.append(True)
        import threading
        t = threading.Thread(target=write, daemon=True)
        with self.f.lock:
            self.f.sim.say("turn", "Under the lock")
        t.start()
        t.join(5)
        self.assertTrue(done, "the log waited on the lock it was under")
        self.assertIn("Under the lock", "\n".join(e["text"] for e in self.f.snapshot(0)["log"]))


class ArmorStealth(Fight):
    """Found by the 2026-11-02 Seven Isles play-test: Chain Mail rolled Stealth with one die."""
    build = dict(copy.deepcopy(HERO), stealth_disadvantage=True)

    def test_heavy_armor_rolls_two_dice_and_keeps_the_low_one(self):
        import stealth
        rolls = iter([18, 3])
        self.f.sim.rng.randint = lambda a, b: next(rolls)
        total, text = stealth.of(self.f).roll(self.me)
        self.assertIn("armor: Disadvantage", text)
        self.assertEqual(total, 3 + stealth.stealth_bonus(self.f.sim.by_id(self.me)))

    def test_a_sheet_in_chain_mail_carries_it(self):
        sheet = {"name": "A", "classes": [{"name": "Fighter", "level": 1}], "abilities": {"str": 16, "dex": 10, "con": 14, "int": 10, "wis": 10, "cha": 10},
                 "combat": {"hp_max": 12, "ac": 16, "speed": 30, "attack_bonus": 5, "damage_count": 1, "damage_die": 8, "damage_bonus": 3, "reach": 5},
                 "equipment": ["Chain Mail", "Longsword"], "spells": [], "features": []}
        self.assertTrue(cb.member(sheet)["build"].get("stealth_disadvantage"))


class SpellMessage(Fight):
    build = dict(copy.deepcopy(HERO), spell_list=[{"name": "Mage Armor", "level": 1}])

    def test_a_sheet_spell_the_table_cant_play_points_to_ask_the_gm(self):
        out = self.act(op="cast", spell="Mage Armor")
        self.assertIn("Ask the GM", out.get("refused") or out.get("error") or "")


class FreeShield(Fight):
    """Found by the 2026-11-02 play-test: with its slots gone, Magic Initiate's free Shield was not offered."""
    build = dict(HERO, spell_list=HERO["spell_list"] + [{"name": "Shield", "level": 1, "always": True, "free": 1}])

    def test_it_is_offered_without_a_slot_once(self):
        r, party = self.f.reactions, self.f.sim.party
        r.asking, r.thread, r.ask = True, threading.current_thread(), lambda *a, **k: {"cast": True}
        while party.slot_free(self.me, 1):
            party.spend_slot(self.me, 1)
        self.assertEqual(r.shield_hit(self.me, 17, 12, False), (5, True))
        self.assertTrue(any("once a Long Rest" in e["text"] for e in self.f.snapshot(0)["log"]))
        self.assertIn("no level 1+ slot", r.why_not(self.me, "Shield"))


class DeathSaves(unittest.TestCase):
    """Found by the 2026-11-02 play-test: a dying character's turn came and went with no Death Saving Throw, a natural
    20 lost the rest of the turn, and nothing in a fight could stabilize anyone."""

    def setUp(self):
        raw = json.loads((ROOT / "sim" / "scenarios" / "test/live_keep.json").read_text(encoding="utf-8"))
        sc = encounter_tuner.with_party(raw, ["Mage", "Friend"], 5, extra={"Mage": copy.deepcopy(HERO), "Friend": dict(copy.deepcopy(HERO), init=1)})
        self.f = f = live_play.LiveFight(run_sim.Sim(sc, "scripted", True, 1, True, True), rounds=3).start()
        self.assertTrue(f.wait_ready(120))
        self.friend = next(c for c in f.sim.sc["combatants"] if c["name"] == "Friend")
        with f.lock:
            f.sim.S.setField(self.friend["id"], "wounds", self.friend["hp"])
            f.sim.S.setField(self.friend["id"], "sim_dying", 1)

    def tearDown(self):
        self.f.quit(); self.f.thread.join(30)

    def texts(self):
        return [e["text"] for e in self.f.snapshot(0)["log"]]

    def turns_until(self, done):
        for _ in range(8):
            if done() or self.f.done or self.f.waiting is None:
                break
            self.f.act(dict(op="end", actor=self.f.waiting, revision=self.f.snapshot(999999)["revision"]))
            self.assertTrue(self.f.wait_ready(120))

    def test_a_dying_character_rolls_on_its_turn(self):
        saved = lambda: any("Friend death saving throw" in t for t in self.texts())
        self.turns_until(saved)
        self.assertTrue(saved(), [t for t in self.texts() if "Friend" in t])

    def test_a_natural_20_keeps_the_rest_of_the_turn(self):
        self.f.sim.rng.randint = lambda a, b: b
        self.turns_until(lambda: self.f.waiting == self.friend["id"])
        self.assertEqual(self.f.waiting, self.friend["id"], [t for t in self.texts() if "Friend" in t])

    def test_an_ally_beside_can_stabilize(self):
        f, party = self.f, self.f.sim.party
        self.turns_until(lambda: f.waiting != self.friend["id"])
        party.dist = lambda *a: 5
        with f.lock:
            f._publish_locked()
        f.sim.rng.randint = lambda a, b: b
        ops = {o["op"]: o for o in f.snapshot(999999)["offers"]["actions"]}
        self.assertIn(self.friend["id"], [t if isinstance(t, str) else t.get("id") for t in ops["stabilize"]["targets"]])
        f.act(dict(op="stabilize", actor=f.waiting, target=self.friend["id"], revision=f.snapshot(999999)["revision"]))
        self.assertTrue(party.deaths[self.friend["id"]]["stable"])
        self.assertTrue(any("vs DC 10 -> Stable" in t for t in self.texts()))


class Scholar(unittest.TestCase):
    """Found by the 2026-11-02 play-test: a Wizard's Scholar Expertise (level 2) was never asked for or counted."""

    def test_a_wizard_chooses_expertise_at_level_2(self):
        self.assertEqual(cb.EXPERTISE["Wizard"], {2: 1})
        self.assertIn("Arcana", cb.SCHOLAR)
        self.assertNotIn("Perception", cb.SCHOLAR)


class BlessedHealer(Fight):
    """Found by the 2026-11-02 play-test: a Healing Word cast on oneself gave Blessed Healer as well."""
    build = dict(HERO, blessed_healer=True)

    def test_only_healing_another_counts(self):
        party = self.f.sim.party
        self.assertEqual(party.healing_bonus(self.me, self.f.sim.by_id(self.me), 1, False), 0)
        self.assertFalse(any("Blessed Healer" in e["text"] for e in self.f.snapshot(0)["log"]))


class SheetStaysTheOriginal(unittest.TestCase):
    """GM 2026-11-02: a character the GM uses for prep, Remix or a fight is a copy; the saved sheet never changes."""

    def test_using_a_sheet_leaves_it_as_it_was(self):
        sheet = {"id": "a", "name": "A", "classes": [{"name": "Fighter", "level": 5}], "abilities": {"str": 18, "dex": 10, "con": 14, "int": 10, "wis": 10, "cha": 10},
                 "combat": {"hp_max": 50, "ac": 18, "speed": 30, "attack_bonus": 7, "damage_count": 1, "damage_die": 8, "damage_bonus": 4, "reach": 5},
                 "equipment": ["Longsword"], "spells": [], "features": ["Second Wind"]}
        before = copy.deepcopy(sheet)
        made = sim_service.Service.saved_characters({"characters": [sheet]}, [])
        self.assertIn("A", made)
        made["A"]["hp"] = 1
        for value in made["A"].values():
            if isinstance(value, list):
                value.append("changed in play")
            elif isinstance(value, dict):
                value["changed"] = "in play"
        self.assertEqual(sheet, before)


class TwoHands(unittest.TestCase):
    """Found by the 2026-11-02 play-test: Great Weapon Fighting applied with a shield on the arm."""

    def sheet(self, gear):
        return {"name": "A", "classes": [{"name": "Fighter", "level": 7}], "abilities": {"str": 18, "dex": 10, "con": 14, "int": 10, "wis": 10, "cha": 10},
                "combat": {"hp_max": 50, "ac": 18, "speed": 30, "attack_bonus": 7, "damage_count": 1, "damage_die": 8, "damage_bonus": 4, "reach": 5},
                "equipment": gear, "spells": [], "features": ["Great Weapon Fighting"], "feats": ["Great Weapon Fighting"]}

    def test_a_shield_turns_it_off(self):
        self.assertFalse(cb.member(self.sheet(["Longsword", "Shield"]))["build"].get("gwf"))


class CureWoundsLife(Fight):
    """Found by the 2026-11-02 play-test: Healing Word showed Disciple of Life and Cure Wounds didn't."""
    build = dict(HERO, disciple_of_life=True)

    def test_disciple_of_life_adds(self):
        party = self.f.sim.party
        c = self.f.sim.by_id(self.me)
        party.resolve_cure_wounds(self.me, c, self.me)
        self.assertTrue(any("+ 3 Disciple of Life" in e["text"] for e in self.f.snapshot(0)["log"]))


class NothingUnusable(Fight):
    """Found by the 2026-11-02 play-test: a Cleric's Channel Divinity had no control and no Ask the GM row either."""

    def test_channel_divinity_stays_on_ask_the_gm(self):
        sheet = {"name": "A", "classes": [{"name": "Cleric", "level": 2}], "abilities": {"str": 10, "dex": 10, "con": 14, "int": 10, "wis": 16, "cha": 10},
                 "combat": {"hp_max": 15, "ac": 16, "speed": 30, "attack_bonus": 5, "damage_count": 1, "damage_die": 6, "damage_bonus": 0, "reach": 5},
                 "equipment": ["Mace"], "spells": [], "features": ["Channel Divinity"]}
        self.assertIn("Channel Divinity", [f["name"] for f in cb.member(sheet)["build"]["feature_list"]])


class CunningStrike(Fight):
    """GM 2026-11-02: a Rogue chooses Trip, Poison or Withdraw on the attack row; nothing is spent unasked."""
    scenario = "test/live_spells.json"
    build = dict(HERO, **{"class": "rogue", "sneak": "3d6", "cunning_strike": 15, "spell_list": [],
                          "ranged": {"name": "Shortbow", "atk": 40, "dmg": "1d6+3", "dmgtype": "piercing", "reach": 320, "crit": 20}})

    def shot(self, **cmd):
        row = next(a for a in self.offers()["attacks"] if a["key"] == "ranged")
        with mock.patch("party.sneak_attack_ok", lambda *a: True):
            out = self.act(op="attack", weapon="ranged", target=row["targets"][0], **cmd)
        return row, out, " | ".join(out.get("lines", []))

    def test_the_row_offers_three_options(self):
        row = next(a for a in self.offers()["attacks"] if a["key"] == "ranged")
        self.assertEqual([o["name"] for o in row["cunning_strike"]["options"]], ["Trip", "Poison", "Withdraw"])
        self.assertEqual((row["cunning_strike"]["dc"], row["cunning_strike"]["two"]), (15, False))

    def test_nothing_is_spent_unasked(self):
        self.assertNotIn("Cunning Strike", self.shot()[2])

    def test_poison_costs_a_die_and_a_save(self):
        lines = self.shot(strike=["poison"])[2]
        self.assertIn("Cunning Strike: Poison, one die forgone", lines)
        foe = next(c["id"] for c in self.f.sim.sc["combatants"] if c.get("side") == "foe" and not self.f.sim.down(c["id"]))
        martial_high.poison_strike(self.f.sim.party, self.me, foe)
        self.assertIn("Cunning Strike (Poison)", " ".join(e["text"] for e in self.f.snapshot(0)["log"]))

    def test_withdraw_gives_half_the_speed(self):
        self.shot(strike=["withdraw"])
        t = self.f.turn_state
        self.assertEqual((t["shift_ft"], t["shift_name"]), (15, "Withdraw"))
        self.assertEqual(self.offers()["movement"], 45)

    def test_two_options_need_rogue_11(self):
        self.assertIn("Rogue 11", str(self.shot(strike=["trip", "poison"])[1]))

    def test_it_left_ask_the_gm(self):
        sheet = {"name": "A", "classes": [{"name": "Rogue", "level": 5}], "abilities": {"str": 10, "dex": 16, "con": 14, "int": 10, "wis": 10, "cha": 10},
                 "combat": {"hp_max": 33, "ac": 14, "speed": 30, "attack_bonus": 6, "damage_count": 1, "damage_die": 6, "damage_bonus": 3, "reach": 5},
                 "equipment": ["Rapier"], "spells": [], "features": ["Cunning Strike"]}
        built = cb.member(sheet)["build"]
        self.assertNotIn("Cunning Strike", [f["name"] for f in built["feature_list"]])
        self.assertEqual(built["cunning_strike"], 14)


class ActionSurge(Fight):
    """Found by the 2026-11-02 play-test: a Fighter played at the table had no Action Surge."""
    build = dict(copy.deepcopy(HERO), action_surge=1, spell_list=[], slots=[])
    build["class"] = "fighter"

    def row(self):
        return next((a for a in self.offers()["actions"] if a["op"] == "action_surge"), None)

    def test_it_waits_for_the_action(self):
        self.assertFalse(self.row()["ready"])
        self.assertIn("first", self.act(op="action_surge")["refused"])

    def test_it_gives_one_more_action_once(self):
        self.assertTrue(self.act(op="dodge")["ok"])
        self.assertTrue(self.act(op="action_surge")["ok"])
        self.assertEqual(self.f.sim.party.surges[self.me], 0)
        self.assertTrue(self.act(op="dash")["ok"])
        self.assertIn("left", self.act(op="action_surge")["refused"])


class SheetSpells(Fight):
    """Found by the 2026-11-02 play-test: a Cleric was offered spells it never prepared."""
    scenario = "test/live_spells.json"
    build = dict(copy.deepcopy(HERO), spell_list=[{"name": "Healing Word", "level": 1}])
    build["class"] = "cleric"

    def test_a_built_sheet_offers_only_its_own_spells(self):
        import live_spells
        c = self.f.sim.by_id(self.me)
        self.assertIn("Healing Word", live_spells.known(c))
        self.assertNotIn("Guiding Bolt", live_spells.known(c))


class Burst(Fight):
    scenario = "test/live_spells.json"

    def test_a_cast_picks_one_of_the_srd_types(self):
        row = next(a for a in self.offers()["attacks"] if a["name"] == "Sorcerous Burst")
        self.assertEqual(row["choices"], ["acid", "cold", "fire", "lightning", "poison", "psychic", "thunder"])
        self.assertNotIn("force", row["choices"])
        self.assertTrue(row["targets"], "a creature in range")
        self.f.sim.rng.randint = lambda a, b: b
        out = self.act(op="attack", weapon="ranged", target=row["targets"][0], dmgtype="cold")
        self.assertTrue(out["ok"], out)
        text = "\n".join(e["text"] for e in out["snapshot"]["log"]).lower()
        self.assertIn("cold", text)
        self.assertNotIn("acid", text)

    def test_force_is_refused(self):
        row = next(a for a in self.offers()["attacks"] if a["name"] == "Sorcerous Burst")
        target = (row["targets"] or [c["id"] for c in self.f.sim.sc["combatants"] if c["side"] == "foe"])[0]
        out = self.act(op="attack", weapon="ranged", target=target, dmgtype="force")
        self.assertIn("no choice of force damage", out["refused"])

    def test_the_weapon_alone_has_no_choice(self):
        row = next(a for a in self.offers()["attacks"] if a["name"] == "Dagger")
        self.assertNotIn("choices", row)


class Social(Fight):
    scenario = "test/live_spells.json"

    def buttons(self):
        return {a["mode"]: a for a in self.f.actions.lore.offers(self.me) if a["op"] == "influence"}

    def test_five_buttons_each_spend_the_action_and_go_to_the_gm_with_the_skill(self):
        b = self.buttons()
        self.assertEqual(set(b), {"deception", "intimidation", "performance", "persuasion", "animal_handling"})
        target = b["persuasion"]["targets"][0]
        out = self.act(op="influence", mode="persuasion", target=target, urge="Stand down")
        self.assertTrue(out["ok"], out)
        self.assertTrue(self.f.turn_state["action_used"])
        ask = self.f.snapshot(999999)["asks_open"][0]
        self.assertEqual((ask["what"], ask["kind"]), ("Influence (Persuasion)", "action"))
        self.assertIn("Stand down", ask["note"])
        self.assertIn("the GM rules it", "\n".join(e["text"] for e in out["snapshot"]["log"]))
        self.assertNotIn("d20", "\n".join(e["text"] for e in out["snapshot"]["log"] if "Influence" in e["text"]))
        self.assertIn("Action is used", self.act(op="influence", mode="deception", target=target)["refused"])

    def test_the_gm_turns_them_off_and_on(self):
        lore = self.f.actions.lore
        target = self.buttons()["persuasion"]["targets"][0]
        lore.set_off(True)
        self.assertTrue(self.f.snapshot(999999)["social_off"])
        shown = next(a for a in self.offers()["actions"] if a.get("mode") == "persuasion")   # what a screen gets
        self.assertFalse(shown["ready"])
        self.assertIn("turned the Influence buttons off", shown["why"])
        self.assertFalse(self.buttons()["persuasion"]["ready"])
        self.assertFalse(self.buttons()["persuasion"]["targets"])
        self.assertIn("turned the Influence buttons off", self.act(op="influence", mode="persuasion", target=target)["refused"])
        self.assertFalse(self.f.turn_state["action_used"])
        lore.set_off(False)
        self.assertFalse(self.f.snapshot(999999)["social_off"])
        self.assertTrue(next(a for a in self.offers()["actions"] if a.get("mode") == "persuasion")["ready"])
        self.assertTrue(self.act(op="influence", mode="persuasion", target=target)["ok"])

    def test_animal_handling_is_for_a_beast_or_monstrosity(self):
        b = self.buttons()["animal_handling"]
        self.assertFalse(b["targets"])


class Asks(Fight):
    def test_chromatic_orb_without_its_diamond_is_not_cast_or_asked(self):
        self.assertNotIn("Chromatic Orb", self.asks())
        orb = next((s for s in self.offers()["spells"] if s["name"] == "Chromatic Orb"), None)
        self.assertIsNotNone(orb, "a Cast card, not ready")
        self.assertFalse(orb["ready"])
        self.assertIn("diamond", orb["why"])

    def test_spirit_guardians_can_be_taken_to_the_gm(self):
        a = self.asks()["Spirit Guardians"]
        self.assertIn("ask the GM whether you can choose", a["note"])

    def test_no_ending_a_spell_at_will(self):
        import more_spells
        self.assertNotIn("end_spell", more_spells.MODULES)
        self.assertFalse([a for a in self.offers()["actions"] if a["op"] == "end_spell"])
        self.assertFalse(hasattr(traps.Traps, "notice"))


class Pit(Fight):
    scenario = "test/live_traps.json"

    def pit(self):
        tr = traps.of(self.f.sim)
        t = next(t for t in tr.traps if t["kind"] == "hidden_pit")
        tr.in_pit[self.me] = t["id"]
        tr.held[self.me] = {"at": (0, 0), "trap": t["id"], "why": "fell", "until": "climb"}
        return tr, t

    def test_a_character_who_falls_is_told_to_ask_the_gm(self):
        tr = traps.of(self.f.sim)
        t = next(t for t in tr.traps if t["kind"] == "hidden_pit")
        tr.in_pit[self.me] = t["id"]
        tr.fall(t, self.me, {"trap": t, "dc": None, "victims": {}, "start_hurt": 0})
        text = "\n".join(e["text"] for e in self.f.snapshot(0)["log"])
        self.assertIn("goes to the GM (Ask the GM)", text)
        self.assertNotIn("climbing gear", text)

    def test_the_wall_is_the_gms_and_a_yes_lets_it_climb(self):
        tr, t = self.pit()
        self.assertIn("Climb out of the pit", {a["name"] for a in self.f.asks.offers(self.me)})
        self.assertFalse([w for w in tr.ways(self.me, t) if w[0] == "climb"])
        out = self.act(op="ask_gm", kind="action", name="Climb out of the pit", note="Rope from the pack")
        self.assertTrue(out["ok"], out)
        self.assertFalse(self.f.turn_state["action_used"])                 # the ask itself costs no action
        n = self.f.snapshot(999999)["asks_open"][0]["n"]
        self.f.rule_ask(n, "", True)
        self.assertIn(self.me, tr.allowed)
        self.assertNotIn("Climb out of the pit", {a["name"] for a in self.f.asks.offers(self.me)})
        self.assertTrue([w for w in tr.ways(self.me, t) if w[0] == "climb"])
        res = tr.climb_core(self.me, t, 200)
        self.assertEqual(res["status"], "out")
        self.assertNotIn(self.me, tr.allowed)
        self.assertNotIn(self.me, tr.in_pit)


class Tools(Fight):
    scenario = "test/live_traps.json"

    def test_without_proficiency_the_gm_rules_it(self):
        tr = traps.of(self.f.sim)
        c = self.f.sim.by_id(self.me)
        self.assertTrue(tr.untrained(c))
        need = tr.tools_proficient(c)
        ready, rows = __import__("requirements").check([need])
        self.assertFalse(ready)
        self.assertIn("Ask the GM", __import__("requirements").first_why(rows))
        self.assertFalse(hasattr(tr, "tried"))


class Trained(Fight):
    scenario, build = "test/live_traps.json", dict(HERO, tools=["Thieves' Tools"])

    def test_proficient_tools_still_work_as_the_srd_says(self):
        tr = traps.of(self.f.sim)
        c = self.f.sim.by_id(self.me)
        self.assertFalse(tr.untrained(c))
        self.assertTrue(__import__("requirements").check([tr.tools_proficient(c)])[0])
        self.assertNotIn("Thieves' Tools", tr.asks(self.me))


class HitPoints(unittest.TestCase):
    def test_a_new_maximum_applies_now_and_damage_stays(self):
        b = dict(HERO, hp=40)
        day = {"party": {}, "log": [], "hour": 8}
        rests.ensure(day, {"Mage": (b, "saved")})
        day["party"]["Mage"]["hp"] = 25
        rests.ensure(day, {"Mage": (dict(b, hp=50), "saved")})
        e = day["party"]["Mage"]
        self.assertEqual((e["hp_max"], e["hp"]), (50, 25))
        self.assertNotIn("pending_hp_max", e)


class Sheet(unittest.TestCase):
    def test_a_built_sorcerer_gets_the_choices(self):
        self.assertEqual(cb.DAMAGE_CANTRIPS["Sorcerous Burst"], (8, True, "acid"))
        self.assertEqual(len(cb.CANTRIP_CHOICES["Sorcerous Burst"]), 7)


if __name__ == "__main__":
    unittest.main()
