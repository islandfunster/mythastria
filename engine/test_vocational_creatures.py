"""2026-10-20 (GM: "goblins and kobolds are allowable player characters now. They should be replaced by goblins and kobolds
with vocational attachments. Like Kobold Warrior that can arbitrarily replace the small creatures' art."): Mythastria's
own simulator maps name no plain "Goblin" or "Kobold" creature (a goblin or kobold may be a player's character); the
creatures are SRD 5.2.1 ones with a vocation (Goblin Warrior, Kobold Warrior ...). And a Small creature reaches the
table with its real 5-ft space, so its 1-square art fits (the table refused a 3-ft goblin before).
The original FG bridge (mythastria_core, extension) is not covered: it reads the GM's FG campaign records."""
import json, re, sys, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path[:0] = [str(ROOT / "tools"), str(ROOT / "sim"), str(ROOT / "mythastria_core")]

PLAIN = re.compile(r"(?i)^(goblin|kobold)s?(\s+\d+)?$")


def scenarios():
    for f in sorted((ROOT / "sim" / "scenarios").rglob("*.json")):
        if "imported" in f.parts:
            continue
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
        except (ValueError, UnicodeDecodeError):
            continue
        if isinstance(d, dict) and isinstance(d.get("combatants"), list):
            yield f, d


class Vocations(unittest.TestCase):
    def test_no_simulator_map_has_a_plain_goblin_or_kobold_creature(self):
        plain = ["%s: %s" % (f.relative_to(ROOT), c.get("name")) for f, d in scenarios()
                 for c in d["combatants"] if not c.get("pc") and PLAIN.match(c.get("name", "").strip())]
        self.assertEqual(plain, [])

    def test_the_goblin_warriors_use_the_srd_5_2_1_block(self):
        lib = json.loads((ROOT / "sim" / "creatures" / "srd_library.json").read_text(encoding="utf-8"))["creatures"]
        want = lib["Goblin Warrior"]
        for f, d in scenarios():
            for c in d["combatants"]:
                if re.match(r"^Goblin Warrior( \d+)?$", c.get("name", "")) and f.parent.name == "test":
                    with self.subTest(map=f.name, creature=c["name"]):
                        self.assertEqual((c["hp"], c["ac"], [a["name"] for a in c["actions"]]),
                                         (want["hp"], want["ac"], [a["name"] for a in want["actions"]]))

    def test_the_map_importer_does_not_default_to_a_plain_goblin(self):
        src = (ROOT / "tools" / "map_import.py").read_text(encoding="utf-8")
        self.assertNotIn('ap.add_argument("--creature", default="Goblin")', src)


class SmallSpace(unittest.TestCase):
    def test_a_small_creature_reaches_the_table_with_a_5_ft_space(self):
        import sim_messages
        self.assertEqual(sim_messages.space_of({"space": 3.75}), 5)
        self.assertEqual(sim_messages.space_of({"size": "small"}), 5)
        self.assertEqual(sim_messages.space_of({"space": 10}), 10)
        self.assertEqual(sim_messages.space_of({"size": "tiny"}), 2.5)
        self.assertEqual(sim_messages.space_of({}), 5)


if __name__ == "__main__":
    unittest.main()
