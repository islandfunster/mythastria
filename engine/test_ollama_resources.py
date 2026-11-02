"""v0.7.71 local model resources (measured on the GM's PC: 1,394-token turn prompt vs Ollama's default 4,096 context;
cold load ~6 s vs ~1.3 s warm; default unload after 5 idle minutes). Every model call uses an 8,192-token context and
a 60-minute keep-alive, the model is warmed when the AI is switched on, and each decision logs its prompt size, with a
warning near the context limit."""
import unittest
from unittest.mock import patch
import planner_fixture as bridge
import ollama_client


class Payloads(unittest.TestCase):
    def setUp(self):
        self.sent = []
        def fake(path, payload=None, timeout=5):
            self.sent.append((path, payload))
            if path == "/api/tags": return {"models": [{"name": "m:1"}]}
            return {"message": {"content": '{"choice": "C1", "reason": "r", "narration": "n"}'},
                    "prompt_eval_count": self.prompt_tokens, "eval_count": 40, "load_duration": 0}
        self.prompt_tokens = 1394
        self.patch = patch.object(ollama_client, "request_json", side_effect=fake); self.patch.start()
        self.logged = []
        self.saved = ollama_client.ON_STATS
        ollama_client.ON_STATS = lambda text, warn: self.logged.append((text, warn))
    def tearDown(self):
        self.patch.stop(); ollama_client.ON_STATS = self.saved

    def chat_payloads(self):
        return [p for path, p in self.sent if path == "/api/chat"]

    def test_choose_and_draft_use_context_and_keep_alive(self):
        ollama_client.choose("m:1", [{"role": "user", "content": "x"}], {"type": "object"})
        ollama_client.generate("m:1", "describe the cave")
        for p in self.chat_payloads():
            self.assertEqual((p["keep_alive"], p["options"]["num_ctx"]), ("60m", 8192))

    def test_warm_loads_with_the_same_context(self):
        ollama_client.warm("m:1")
        path, p = self.sent[-1]
        self.assertEqual((path, p["model"], p["keep_alive"], p["options"]["num_ctx"]), ("/api/generate", "m:1", "60m", 8192))

    def test_each_decision_logs_its_prompt_size_and_warns_near_the_limit(self):
        ollama_client.choose("m:1", [{"role": "user", "content": "x"}], {"type": "object"})
        self.assertIn("1394 prompt tokens of 8192", self.logged[-1][0]); self.assertFalse(self.logged[-1][1])
        self.prompt_tokens = 7000
        ollama_client.choose("m:1", [{"role": "user", "content": "x"}], {"type": "object"})
        self.assertTrue(self.logged[-1][1]); self.assertIn("close to the context limit", self.logged[-1][0])


if __name__ == "__main__":
    unittest.main()
