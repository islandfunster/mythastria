"""v0.7.77 (Halls rehearsal, door 34, seed 3): qwen3.5 ran out of room inside a text field ("The AI did not return
valid JSON. The model ran out of room."). The reply schema caps the text fields (Ollama turns the schema into a
grammar), and one invalid reply is retried once, cooler, before the turn reports an error."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent / "mythastria_core"))
import unittest
import test_support  # noqa: F401  (paths)
import ai_turn, ollama_client


class ReplySchema(unittest.TestCase):
    def test_text_fields_are_capped(self):
        sch = ai_turn.schema({"choices": [{"id": "C1"}, {"id": "C2"}]})
        self.assertEqual(sch["properties"]["reason"]["maxLength"], 300)
        self.assertEqual(sch["properties"]["narration"]["maxLength"], 600)
        self.assertEqual(sch["properties"]["choice"]["enum"], ["C1", "C2"])


ATTACK = {"id": "C1", "kind": "attack", "power_name": "Bite", "target_name": "Pally", "atktype": "melee",
          "distance_ft": 5, "spell": False, "level": 0, "node_path": "n", "target": "t"}
HEAL = dict(ATTACK, id="C2", kind="heal", power_name="Cure Wounds", spell=True)


class TwoOutcomes(unittest.TestCase):
    """v0.7.86 (field test 2026-10-13 13:15): the model writes a hit and a miss narration for attacks and save spells
    in the same reply; the bridge posts the one matching FG's result."""
    def opts(self, *choices):
        return {"choices": [dict(c) for c in choices], "source": "s", "source_name": "Gobliez 3",
                "distances_known": True}

    def test_schema_asks_for_a_miss_narration_when_an_attack_is_offered(self):
        sch = ai_turn.schema(self.opts(ATTACK, HEAL))
        self.assertEqual(sch["properties"]["narration_miss"], {"type": "string", "minLength": 20, "maxLength": 600})
        self.assertIn("narration_miss", sch["required"])
        self.assertIn("narration_miss", ai_turn.messages(self.opts(ATTACK))[0]["content"])

    def test_no_miss_narration_without_an_attack_or_save(self):
        sch = ai_turn.schema(self.opts(HEAL))
        self.assertNotIn("narration_miss", sch["properties"])
        self.assertNotIn("narration_miss", ai_turn.messages(self.opts(HEAL))[0]["content"])
        moving = dict(ATTACK, move_only=True)
        self.assertNotIn("narration_miss", ai_turn.schema(self.opts(moving))["properties"])

    def test_validate_keeps_and_caps_the_miss_narration(self):
        s = ai_turn.validate({"choice": "C1", "reason": "r", "narration": "Teeth sink in.",
                              "narration_miss": "  Pally  sidesteps. " + "x" * 700}, self.opts(ATTACK))
        self.assertTrue(s["narration_miss"].startswith("Pally sidesteps. x"))
        self.assertEqual(len(s["narration_miss"]), 600)
        s = ai_turn.validate({"choice": "C1", "reason": "r", "narration": "n"}, self.opts(ATTACK))
        self.assertEqual(s["narration_miss"], "")   # an older reply without it

    def test_healing_words_in_the_miss_narration_get_the_plain_line(self):
        s = ai_turn.validate({"choice": "C1", "reason": "r", "narration": "Teeth sink in.",
                              "narration_miss": "The bite heals Pally."}, self.opts(ATTACK))
        self.assertEqual(s["narration_miss"], "Gobliez 3 attacks Pally with Bite.")


class RetryOnce(unittest.TestCase):
    def setUp(self):
        self.real = (ollama_client.request_json, ollama_client.list_models)
        ollama_client.list_models = lambda: ["m"]
        self.calls = []

    def tearDown(self):
        ollama_client.request_json, ollama_client.list_models = self.real

    def fake(self, replies):
        def request_json(path, payload, timeout=0):
            self.calls.append(payload["options"]["temperature"])
            return replies.pop(0)
        ollama_client.request_json = request_json

    def test_one_bad_reply_is_retried_cooler(self):
        self.fake([{"message": {"content": '{"choice": "C1", "reason": "aaaa'}, "done_reason": "length"},
                   {"message": {"content": '{"choice": "C1", "reason": "r", "narration": "n"}'}, "done_reason": "stop"}])
        self.assertEqual(ollama_client.choose("m", [], {"type": "object"})["choice"], "C1")
        self.assertEqual(len(self.calls), 2)
        self.assertLess(self.calls[1], self.calls[0])

    def test_two_bad_replies_report_the_error(self):
        bad = {"message": {"content": "not json"}, "done_reason": "stop"}
        self.fake([dict(bad), dict(bad)])
        with self.assertRaises(ollama_client.OllamaError):
            ollama_client.choose("m", [], {"type": "object"})
        self.assertEqual(len(self.calls), 2)


if __name__ == "__main__":
    unittest.main()
