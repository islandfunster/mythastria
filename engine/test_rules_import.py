"""v0.7.47 RULES-CACHE-01 Stage A: offline importer and durable SQLite cache, on synthetic module archives
(no licensed text in fixtures). Covers new/old spell roots, categories, reference sections, editions, duplicates,
atomic refresh, idempotent repeat, restart persistence, revision history, removed records, malformed/oversized
input, exact action preservation, attribution/policy and edition resolution."""
import json, os, shutil, sqlite3, sys, tempfile, unittest, zipfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent / "mythastria_core"))
import rules_cache, rules_import

DEF = '<?xml version="1.0" encoding="utf-8"?><root><name>TESTSRD</name><displayname>Test SRD</displayname></root>'
LEGAL = ('<id-00009><name type="string">Legal Information</name><blocks><id-00001><text type="formattedtext">'
         '<p>This work includes material from the System Reference Document 5.2.1 by Example, licensed under '
         'CC-BY-4.0, available at https://example.invalid/ legalcode.</p></text></id-00001></blocks></id-00009>')

def spell(tag, name, rng="30 feet", version="2024", extra=""):
    v = '<version type="string">%s</version>' % version if version else ""
    return ('<%s><name type="string">%s</name><level type="number">1</level><range type="string">%s</range>%s'
            '<description type="formattedtext"><p>Synthetic text for %s.</p><list><li>one</li><li>two</li></list></description>'
            '<actions><id-00001><type type="string">cast</type><targeting type="string">targets</targeting>'
            '<targetingval type="number">3</targetingval></id-00001><id-00002><type type="string">effect</type>'
            '<label type="string">%s; (C); ATK: 1d4; SAVE: 1d4</label><durmod type="number">1</durmod>'
            '<durunit type="string">minute</durunit></id-00002></actions>%s</%s>') % (tag, name, rng, v, name, name, extra, tag)

def client(spells_new="", spells_old="", legal=True, rules=True):
    ref = ""
    pages = (LEGAL if legal else "") + (
        '<id-00010><name type="string">Casting Things</name><blocks><id-00002><order type="number">2</order>'
        '<text type="formattedtext"><h>Second Rule</h><p>Second body.</p></text></id-00002><id-00001>'
        '<order type="number">1</order><text type="formattedtext"><p>Intro.</p><h>First Rule</h><p>On a turn, one '
        'thing.</p><table><tr><td>a</td><td>b</td></tr></table></text></id-00001></blocks></id-00010>' if rules else "")
    if pages:
        ref = ('<reference><refmanualdata>%s</refmanualdata><refmanualindex><chapters><id-00001><name type="string">'
               'Chapter</name><subchapters><id-00001><name type="string">Sub</name><refpages><id-00001>'
               '<name type="string">Casting Things</name><listlink type="windowreference"><class>x</class>'
               '<recordname>reference.refmanualdata.id-00010</recordname></listlink></id-00001></refpages>'
               '</id-00001></subchapters></id-00001></chapters></refmanualindex></reference>') % pages
    old = '<reference><spelldata>%s</spelldata></reference>' % spells_old if spells_old else ""
    body = '<spell><category name="A">%s</category></spell>%s%s' % (spells_new, ref.replace("<reference>", "<reference>" + old.replace("<reference>", "").replace("</reference>", "")) if ref else old, "")
    return '<?xml version="1.0" encoding="utf-8"?><root>%s</root>' % body

class Base(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        (self.dir / "modules").mkdir()
        self.db = self.dir / "cache" / "rules.sqlite"
        os.environ["MYTHASTRIA_FG_DIR"] = str(self.dir)
        self.cfg = {"source_id": "test-srd", "kind": "offline_srd", "file": "modules/TEST.mod", "module": "TESTSRD",
                    "member": "client.xml", "declared_edition": "2024", "policy": "cloud_allowed", "license": "CC-BY-4.0"}
        self.limits = dict(rules_import.LIMITS)
    def tearDown(self):
        os.environ.pop("MYTHASTRIA_FG_DIR", None)
        rules_import.LIMITS.update(self.limits)
        shutil.rmtree(self.dir, ignore_errors=True)
    def write(self, xml, definition=DEF, raw=None):
        p = self.dir / "modules" / "TEST.mod"
        if raw is not None:
            p.write_bytes(raw); return
        with zipfile.ZipFile(p, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("definition.xml", definition); z.writestr("client.xml", xml)
        st = p.stat(); os.utime(p, (st.st_atime, st.st_mtime + 1))   # a new mtime for every rewrite
    def imp(self, force=False):
        return rules_import.import_source(self.cfg, force, self.db)
    def look(self, *a, **k):
        return rules_cache.lookup(*a, path=self.db, **k)

class ImportTests(Base):
    def test_roots_categories_sections_and_exact_actions(self):
        self.write(client(spell("bless", "Bless") + spell("aid", "Aid"), spell("oldbolt", "Old Bolt", version="")))
        r = self.imp()
        self.assertEqual((r["status"], r["new"]), ("ok", 7), r)                # 3 spells + 2 rule sections + intro + legal
        b = self.look("Bless", "spell")
        self.assertEqual(b["status"], "ok")
        res = b["results"][0]
        self.assertEqual(res["fg_path"], "spell.bless@TESTSRD")
        self.assertEqual(res["fields"]["actions"]["id-00002"]["label"], "Bless; (C); ATK: 1d4; SAVE: 1d4")
        self.assertEqual(res["fields"]["actions"]["id-00001"]["targetingval"], 3)
        self.assertEqual(res["text"], "Synthetic text for Bless.\n\n- one\n- two")
        self.assertIn("<p>Synthetic text for Bless.</p>", res["fields"]["description"]["raw"])
        old = self.look("Old Bolt", "spell")["results"][0]
        self.assertEqual((old["fg_path"], old["edition"]), ("reference.spelldata.oldbolt@TESTSRD", "2024"))
        self.assertIn("source declaration", old["edition_reason"])
        rule = self.look("First Rule", "rule")["results"][0]
        self.assertEqual(rule["title"], "Casting Things > First Rule")
        self.assertEqual(rule["text"], "First Rule\n\nOn a turn, one thing.\n\na | b")
        self.assertEqual(rule["fields"]["index_path"], ["Chapter", "Sub", "Casting Things"])
        self.assertEqual(self.look("Second Rule", "rule")["results"][0]["fields"]["section"], 3)   # block order kept

    def test_editions_never_fall_back_and_conflicts_are_flagged(self):
        self.write(client(spell("bless", "Bless") + spell("blessold", "Bless", version="2014")))
        self.imp()
        self.assertEqual(self.look("Bless", "spell")["results"][0]["edition"], "2024")
        self.assertEqual(self.look("Bless", "spell", edition="2014")["results"][0]["fg_path"], "spell.blessold@TESTSRD")
        self.assertEqual(self.look("Bless", "spell", edition="2014")["status"], "ok")
        self.assertEqual(self.look("Aid", "spell", edition="2014")["status"], "miss")
        issues = json.loads(rules_cache.source_row("test-srd", self.db)["issues"])
        self.assertTrue(any("differs from the source declaration" in i for i in issues))
        self.cfg["declared_edition"] = None
        self.write(client(spell("x", "Untagged", version="")))
        self.imp()
        self.assertEqual(self.look("Untagged", "spell", edition="unknown")["status"], "ok")   # not assumed 2014

    def test_duplicates_are_ambiguous_until_a_source_is_named(self):
        self.write(client(spell("cure1", "Cure Wounds") + spell("cure2", "Cure Wounds", rng="Touch")))
        self.imp()
        r = self.look("Cure Wounds", "spell")
        self.assertEqual((r["status"], len(r["results"])), ("ambiguous", 2))
        self.assertEqual(self.look("Cure Wounds", "spell", source_id="nope")["status"], "miss")
        rid = r["results"][0]["record_id"]
        self.assertEqual(rules_cache.get_record(rid, path=self.db)["status"], "ok")

    def test_repeat_is_a_noop_and_survives_a_restart(self):
        self.write(client(spell("bless", "Bless")))
        self.imp()
        self.assertEqual(self.imp()["status"], "unchanged")
        r = self.imp(force=True)                                     # same bytes: hash equal -> unchanged
        self.assertEqual(r["status"], "unchanged")
        con = sqlite3.connect(str(self.db))                          # "restart": a fresh connection reads it back
        self.assertEqual(con.execute("SELECT count(*) FROM records").fetchone()[0], 5)
        con.close()
        self.assertEqual(self.look("Bless", "spell")["status"], "ok")

    def test_changed_record_keeps_history_and_removed_records_become_unavailable(self):
        self.write(client(spell("bless", "Bless") + spell("aid", "Aid")))
        self.imp()
        before = self.look("Bless", "spell")["results"][0]
        self.write(client(spell("bless", "Bless", rng="60 feet")))
        r = self.imp()
        self.assertEqual((r["changed"], r["removed"]), (1, 1), r)
        after = self.look("Bless", "spell")["results"][0]
        self.assertEqual(after["record_id"], before["record_id"])
        self.assertNotEqual(after["revision_id"], before["revision_id"])
        self.assertEqual(after["fields"]["range"], "60 feet")
        con = sqlite3.connect(str(self.db))
        self.assertEqual(con.execute("SELECT count(*) FROM revisions WHERE record_id=?", (before["record_id"],)).fetchone()[0], 2)
        con.close()
        self.assertEqual(self.look("Aid", "spell")["status"], "miss")
        aid = rules_cache.connect(self.db).execute("SELECT record_id FROM records WHERE name='Aid'").fetchone()[0]
        self.assertEqual(rules_cache.get_record(aid, path=self.db)["status"], "unavailable")

    def test_failed_imports_change_nothing(self):
        self.write(client(spell("bless", "Bless")))
        self.imp()
        bad = [("broken xml", client(spell("bless", "Bless")).replace("</root>", ""), DEF, None),
               ("dtd", '<?xml version="1.0"?><!DOCTYPE x [<!ENTITY a "b">]><root/>', DEF, None),
               ("wrong module", client(spell("bless", "Bless")), DEF.replace("TESTSRD", "OTHER"), None),
               ("not a zip", None, None, b"ENCRYPTED-VAULT-LIKE-BYTES")]
        for label, xml, d, raw in bad:
            self.write(xml, d, raw)
            r = self.imp(force=True)
            self.assertEqual(r["status"], "error", label)
            self.assertEqual(self.look("Bless", "spell")["status"], "ok", label + ": previous cache intact")
        self.cfg["file"] = "modules/MISSING.mod"
        self.assertIn("not found", self.imp()["error"])

    def test_size_depth_and_text_limits(self):
        deep = "<a>" * 70 + "</a>" * 70
        self.write('<?xml version="1.0"?><root>%s</root>' % deep)
        self.assertIn("nesting", self.imp(force=True)["error"])
        rules_import.LIMITS["archive_bytes"] = 10
        self.write(client(spell("bless", "Bless")))
        self.assertIn("archive larger", self.imp(force=True)["error"])
        rules_import.LIMITS.update(self.limits)
        rules_import.LIMITS["record_text_chars"] = 50
        self.write(client(spell("bless", "Bless")))
        self.imp(force=True)
        self.assertEqual(self.look("Bless", "spell")["status"], "too_large")   # not silently truncated

    def test_policy_needs_attribution_and_cloud_projection_hides_local_sources(self):
        self.write(client(spell("bless", "Bless"), legal=False))
        self.imp()
        row = rules_cache.source_row("test-srd", self.db)
        self.assertEqual(row["policy"], "local_only")
        self.assertIn("lowered to local_only", row["issues"])
        self.assertEqual(rules_cache.export("Bless", "spell", path=self.db)["status"], "miss")
        self.assertEqual(rules_cache.lookup("Bless", "spell", audience="cloud", path=self.db)["status"], "miss")
        self.write(client(spell("bless", "Bless")))
        self.imp()
        r = rules_cache.export("Bless", "spell", path=self.db)
        self.assertEqual(r["status"], "ok"); self.assertIn("CC-BY-4.0", r["results"][0]["attribution"])

    def test_query_bounds_and_wildcards(self):
        self.write(client(spell("bless", "Bless") + spell("x", "100% Sure_Thing")))
        self.imp()
        self.assertEqual(self.look("x" * 200, "spell")["status"], "miss")
        self.assertEqual(self.look("%", "spell")["status"], "ok")          # literal %, not "match everything"
        self.assertEqual(self.look("_", "spell")["results"][0]["name"], "100% Sure_Thing")
        self.assertEqual(self.look("Bless", "npc")["status"], "miss")
        self.assertEqual(len(self.look("s", "spell", limit=999)["results"]), 2)

if __name__ == "__main__":
    unittest.main()
