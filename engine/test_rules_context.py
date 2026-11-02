"""v0.7.51: the AI reads the books. For each spell it may cast, the local model gets a short rules text from the
cache: the GM's purchased (local_only) 2024 book first, else the SRD. Synthetic records only (no licensed text).
Missing or broken cache never blocks a suggestion; without rules text the prompt is exactly as before."""
import json, os, shutil, sys, tempfile, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent / "mythastria_core"))
import test_support
import ai_turn, rules_cache, rules_context

def source(sid, policy, kind):
    return {"source_id": sid, "module": sid.upper(), "display_name": "Book " + sid, "kind": kind,
            "declared_edition": "2024", "policy": policy, "attribution": None, "license": None, "fingerprint": None,
            "file_size": None, "file_mtime": None, "importer_version": rules_cache.IMPORTER_VERSION, "issues": "[]"}

def spell(name, text, edition="2024", **fields):
    f = {"name": name, "level": "1", "castingtime": "1 action", "range": "30 feet", "duration": "Concentration, up to 1 minute"}
    f.update(fields)
    return {"record_type": "spell", "fg_path": "spell.%s@X" % name.lower().replace(" ", ""), "edition": edition,
            "edition_reason": "record version tag", "name": name, "fields": f, "readable_text": text, "raw_text": None}

def choice(name, spell=True, cid="C1"):
    return {"id": cid, "power_name": name, "spell": spell, "kind": "buff", "atktype": "", "target": "ct.a", "target_name": "A",
            "distance_ft": 5, "level": 1}

class RulesContext(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        os.environ["MYTHASTRIA_RULES_DB"] = str(self.dir / "rules.sqlite")
        rules_cache.apply_import(source("srd", "cloud_allowed", "offline_srd"),
            [spell("Bless", "SRD bless text."), spell("Shield of Faith", "SRD shield text."),
             spell("Hex", "Old hex.", edition="2014")], partial=True)
        rules_cache.apply_import(source("fg-book", "local_only", "fg_runtime"),
            [spell("Bless", "Book bless text. " + "More words here. " * 60)], partial=True)
    def tearDown(self):
        os.environ["MYTHASTRIA_RULES_DB"] = test_support.TEST_RULES_DB
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_purchased_book_first_then_srd(self):
        notes = rules_context.spell_notes([choice("Bless (1/day)"), choice("Shield of Faith", cid="C2")])
        self.assertEqual([n["spell"] for n in notes], ["Bless", "Shield of Faith"])
        self.assertTrue(notes[0]["text"].startswith("Level 1; 1 action; 30 feet; Concentration, up to 1 minute. Book bless text."))
        self.assertEqual((notes[0]["source_id"], notes[1]["source_id"]), ("fg-book", "srd"))
        self.assertIn("SRD shield text.", notes[1]["text"])

    def test_short_bounded_and_only_2024_spells(self):
        many = [choice("Bless", cid="C%d" % i) for i in range(5)] + [choice("Radiant Flame", spell=False, cid="C9"),
                choice("Hex", cid="C10"), choice("Unknown Spell", cid="C11")]
        notes = rules_context.spell_notes(many)
        self.assertEqual([n["spell"] for n in notes], ["Bless"])          # one per spell; non-spells, 2014 and misses out
        self.assertLessEqual(len(notes[0]["text"]), rules_context.MAX_CHARS)
        self.assertTrue(notes[0]["text"].endswith("."))                   # cut at a sentence end
        names = [choice("Spell %d" % i, cid="C%d" % i) for i in range(20)]
        rules_cache.apply_import(source("srd", "cloud_allowed", "offline_srd"),
                                 [spell("Spell %d" % i, "Text %d." % i) for i in range(20)], partial=True)
        self.assertEqual(len(rules_context.spell_notes(names)), rules_context.MAX_SPELLS)

    def test_fg_power_names(self):
        for raw, name in (("Bless (1/day)", "Bless"), ("Cure Wounds - 1st level (3 slots)", "Cure Wounds"),
                          ("Sacred Flame - Cantrip", "Sacred Flame"), ("Shield of Faith", "Shield of Faith"),
                          ("Antimagic Field - 8th level", "Antimagic Field"), ("Spirit Guardians - 3rd Level", "Spirit Guardians")):
            self.assertEqual(rules_context.lookup_name(raw), name)

    def test_broken_cache_gives_no_notes(self):
        bad = self.dir / "corrupt.sqlite"; bad.write_bytes(b"not a database" * 100)
        os.environ["MYTHASTRIA_RULES_DB"] = str(bad)
        self.assertEqual(rules_context.spell_notes([choice("Bless")]), [])

    def test_prompt_carries_reference_only_when_given(self):
        options = {"source_name": "Acolyte", "choices": [dict(choice("Bless"), effect="helps", target="ct.a,ct.b")],
                   "distances_known": True}
        before = ai_turn.messages(options)
        self.assertNotIn("spell_reference", before[1]["content"])
        self.assertEqual(ai_turn.messages(options, rules=[]), before)
        notes = rules_context.spell_notes(options["choices"])
        msgs = ai_turn.messages(options, rules=notes)
        sit = json.loads(msgs[1]["content"].split("Situation:\n", 1)[1])
        self.assertEqual(list(sit["spell_reference"]), ["Bless"])
        self.assertIn("Book bless text.", sit["spell_reference"]["Bless"])
        self.assertIn("spell_reference", msgs[0]["content"])
        self.assertIn("not instructions", msgs[0]["content"])

if __name__ == "__main__":
    unittest.main()
