"""GM 2026-11-01 ("Yes, rebuild it"): the spell sheet holds the official SRD 5.2.1 PDF's words, read by tools/srd_spells.py.
  py -3 -m unittest test_srd_spells
"""
import json, re, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SPELLS = {s["name"]: s for s in json.loads((ROOT / "sim" / "spells" / "srd_spells.json").read_text(encoding="utf-8"))["spells"]}


class Sheet(unittest.TestCase):
    def test_the_pdfs_spells_and_no_others(self):
        self.assertEqual(len(SPELLS), 339)
        self.assertNotIn("Circle of Power", SPELLS)
        self.assertNotIn("Telepathy", SPELLS)

    def test_no_spell_names_a_book(self):
        for name, s in SPELLS.items():
            self.assertNotRegex(json.dumps(s), r"(?i)\b(manual|handbook)\b", name)

    def test_the_words_are_the_pdfs(self):
        self.assertIn('in "Monsters."', SPELLS["Awaken"]["text"])
        self.assertIn('See "Monsters" for these stat blocks.', SPELLS["Create Undead"]["text"])

    def test_what_the_old_text_had_wrong(self):
        self.assertEqual((SPELLS["Barkskin"]["components"]["v"], SPELLS["Barkskin"]["components"]["m"]), (True, True))
        self.assertEqual(SPELLS["Planar Binding"]["components"]["cost_gp"], 1000)
        self.assertTrue(SPELLS["Planar Binding"]["components"]["consumed"])
        self.assertFalse(SPELLS["Aid"]["ritual"])
        self.assertEqual(SPELLS["Sorcerous Burst"]["attack"], "ranged")
        self.assertEqual(SPELLS["Plant Growth"]["casting_time_text"], "Action (Overgrowth) or 8 hours (Enrichment)")
        for name in ("Hideous Laughter", "Spider Climb"):
            self.assertEqual(SPELLS[name]["scaling"]["extra_targets_per_level"], 1, name)

    def test_the_rules_the_engine_reads_survived_the_pdfs_layout(self):
        self.assertEqual(SPELLS["Cure Wounds"]["scaling"]["dice_per_level"], "2d8")           # "in-" + "creases"
        self.assertEqual(SPELLS["Sunburst"]["damage"], [{"dice": "12d6", "type": "radiant", "plus_mod": False}])   # "Ra-" + "diant"
        self.assertEqual(SPELLS["Spirit Guardians"]["area"]["size_ft"], 15)                   # "Ema-" + "nation"
        self.assertEqual(SPELLS["Globe of Invulnerability"]["area"]["size_ft"], 10)           # "10-" + "foot"
        self.assertEqual(SPELLS["Prismatic Spray"]["conditions"], ["Blinded", "Petrified", "Restrained"])   # a table's wrapped rows
        self.assertEqual(SPELLS["Antipathy/Sympathy"]["damage"], [])                          # not the stat block beside it
        self.assertEqual(SPELLS["Antipathy/Sympathy"]["conditions"], ["Charmed", "Frightened"])

    def test_tables_and_stat_blocks_keep_their_own_lines(self):
        self.assertIn("\n5 Gnome 10 Tiefling\n", SPELLS["Reincarnate"]["text"])
        self.assertIn("\nAC 10 + 1 per spell level\n", SPELLS["Find Steed"]["text"])
        self.assertIn("\nStr 18 +4 +4 Dex 12 +1 +1 Con 14 +2 +2\n", SPELLS["Find Steed"]["text"])

    def test_nothing_of_the_page_is_left_in_the_text(self):
        for name, s in SPELLS.items():
            self.assertNotIn("Reference Document", s["text"], name)
            self.assertNotRegex(s["text"], r" -\n|-\n[a-z]", name)
            self.assertFalse(re.search(r"\n[a-z]", s["text"]), name)                         # no paragraph opens mid-sentence

    def test_the_tool_reads_the_pdf_and_nothing_else(self):
        tool = (ROOT / "tools" / "srd_spells.py").read_text(encoding="utf-8")
        self.assertNotIn(".mod", tool)
        self.assertNotIn("Fantasy Grounds", tool)


if __name__ == "__main__":
    unittest.main()
