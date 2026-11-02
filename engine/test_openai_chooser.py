"""OPENAI-NPC-01: the simulator's OpenAI chooser sends the bridge's prompt and schema and returns the reply (no network)."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent / "mythastria_core"))
import io, json, sys, unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent / "sim"))
import test_support  # noqa: F401  (paths)
import ollama_client
import openai_chooser


class _Resp(io.BytesIO):
    def __enter__(self): return self
    def __exit__(self, *a): return False


class Chooser(unittest.TestCase):
    def setUp(self):
        openai_chooser.STATS.update(calls=0, failures=0, input_tokens=0, output_tokens=0, seconds=0.0)
        self.choose = openai_chooser.make_choose("gpt-test", key="k")
        self.msgs = [{"role": "system", "content": "You run NPC turns."}, {"role": "user", "content": "Situation: ..."}]
        self.schema = {"type": "object", "properties": {"choice": {"type": "string"}}}

    def test_sends_the_bridges_prompt_and_schema_and_returns_the_reply(self):
        sent = {}
        def fake(req, timeout):
            sent.update(json.loads(req.data.decode())); sent["auth"] = req.get_header("Authorization")
            body = {"output": [{"type": "message", "content": [{"type": "output_text", "text": '{"choice": "C2"}'}]}],
                    "usage": {"input_tokens": 900, "output_tokens": 40}}
            return _Resp(json.dumps(body).encode())
        with mock.patch.object(openai_chooser, "urlopen", fake):
            self.assertEqual(self.choose("qwen", self.msgs, self.schema), {"choice": "C2"})
        self.assertEqual((sent["model"], sent["instructions"], sent["input"][0]["content"]), ("gpt-test", "You run NPC turns.", "Situation: ..."))
        self.assertEqual(sent["text"]["format"]["schema"], self.schema)
        self.assertEqual(sent["auth"], "Bearer k")
        self.assertEqual((openai_chooser.STATS["calls"], openai_chooser.STATS["input_tokens"]), (1, 900))

    def test_a_bad_reply_is_a_failed_decision_not_a_crash(self):
        def fake(req, timeout):
            return _Resp(json.dumps({"output": [{"type": "message", "content": [{"type": "output_text", "text": "nope"}]}]}).encode())
        with mock.patch.object(openai_chooser, "urlopen", fake):
            with self.assertRaises(ollama_client.OllamaError):
                self.choose("qwen", self.msgs, self.schema)
        self.assertEqual(openai_chooser.STATS["failures"], 1)


if __name__ == "__main__":
    unittest.main()
