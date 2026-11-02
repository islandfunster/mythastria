"""SRD imports stay immutable; corrections alter only read projections, and come from the SRD alone."""
import json
import os
import shutil
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "mythastria_core"))
import test_support
import rules_cache
import rules_overlay


def source():
    return {"source_id": "srd521-player", "module": "DNDSRD521PLAYER", "display_name": "SRD 5.2.1",
            "kind": "offline_srd", "declared_edition": "2024", "policy": "cloud_allowed",
            "attribution": "CC-BY-4.0", "license": "CC-BY-4.0", "fingerprint": None,
            "file_size": None, "file_mtime": None, "importer_version": rules_cache.IMPORTER_VERSION, "issues": "[]"}


def record(kind, name, fields):
    return {"record_type": kind, "fg_path": "%s.%s@DNDSRD521PLAYER" % (kind, name.lower().replace(" ", "")),
            "edition": "2024", "edition_reason": "source declaration", "name": name, "fields": fields,
            "readable_text": "Synthetic source text.", "raw_text": None}


class OfficialRulesOverlay(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.db = self.root / "rules.sqlite"
        os.environ["MYTHASTRIA_RULES_DB"] = str(self.db)
        rules_cache.apply_import(source(), [record("spell", "Flaming Sphere", {"school": "Conjuration"}),
                                            record("rule", "Stabilizing a Creature", {"section": 1})], partial=True)

    def tearDown(self):
        os.environ["MYTHASTRIA_RULES_DB"] = test_support.TEST_RULES_DB
        shutil.rmtree(self.root, ignore_errors=True)

    def test_a_correction_changes_projection_not_immutable_revision(self):
        spell = rules_cache.lookup("Flaming Sphere", "spell")["results"][0]
        self.assertEqual(spell["fields"]["school"], "Evocation")
        self.assertEqual(spell["corrections"][0]["id"], "srd-flaming-sphere-school")
        con = sqlite3.connect(str(self.db))
        stored = json.loads(con.execute("SELECT fields_json FROM revisions WHERE revision_id=?",
                                        (spell["revision_id"],)).fetchone()[0])
        con.close()
        self.assertEqual(stored["school"], "Conjuration")

    def test_only_the_srd_corrects_the_srd(self):
        self.assertEqual(rules_overlay.baseline()["label"], "SRD 5.2.1")
        rule = rules_cache.lookup("Stabilizing a Creature", "rule")["results"][0]
        self.assertNotIn("corrections", rule)
        self.assertEqual({c["layer"] for c in rules_overlay.load()["corrections"]}, {"srd_tables"})
        self.assertNotIn("adjudications", rules_overlay.load())


if __name__ == "__main__":
    unittest.main()
