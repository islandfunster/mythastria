"""LOCAL-LLM-01: the local OpenAI-compatible chooser (no network): local addresses only, the bridge's prompt and
schema are sent, a JSON reply comes back, a bad reply is a failed decision."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent / "mythastria_core"))
import io, json, sys, unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent / "sim"))
import test_support  # noqa: F401  (paths)
import ollama_client
import local_llm_chooser as L


class _Resp(io.BytesIO):
    def __enter__(self): return self
    def __exit__(self, *a): return False


def reply(text):
    return _Resp(json.dumps({"choices": [{"message": {"content": text}}], "usage": {"prompt_tokens": 800, "completion_tokens": 30}}).encode())


class LocalChooser(unittest.TestCase):
    msgs = [{"role": "system", "content": "You run NPC turns."}, {"role": "user", "content": "Situation: ..."}]
    schema = {"type": "object", "properties": {"choice": {"type": "string"}}}

    def test_only_this_pc(self):
        for url in ("http://127.0.0.1:1234/v1", "http://localhost:11434/v1", "http://[::1]:1234/v1"):
            L.check_local(url)
        for url in ("https://api.openai.com/v1", "http://192.168.1.20:1234/v1", "http://example.com/v1"):
            with self.assertRaises(SystemExit):
                L.check_local(url)

    def test_sends_prompt_and_schema_returns_reply(self):
        sent = {}
        def fake(req, timeout):
            sent.update(json.loads(req.data.decode())); sent["url"] = req.full_url; sent["auth"] = req.get_header("Authorization")
            return reply('{"choice": "C1"}')
        with mock.patch.object(L, "urlopen", fake):
            self.assertEqual(L.make_choose("http://127.0.0.1:1234/v1/", "gemma")("qwen", self.msgs, self.schema), {"choice": "C1"})
        self.assertEqual(sent["url"], "http://127.0.0.1:1234/v1/chat/completions")
        self.assertEqual((sent["model"], sent["messages"], sent["response_format"]["json_schema"]["schema"]), ("gemma", self.msgs, self.schema))
        self.assertIsNone(sent["auth"])                                   # no key is ever sent

    def test_retries_once_then_fails_cleanly(self):
        calls = []
        def fake(req, timeout):
            calls.append(json.loads(req.data.decode())["temperature"]); return reply("not json")
        with mock.patch.object(L, "urlopen", fake):
            with self.assertRaises(ollama_client.OllamaError):
                L.make_choose("http://127.0.0.1:1234/v1", "m")("q", self.msgs, self.schema)
        self.assertEqual(calls, [0.6, 0.2])


class Reasoning(unittest.TestCase):
    """2026-10-16: Gemma 4 in LM Studio thinks before answering; at level 3 it spent the whole 1024-token budget thinking
    (finish_reason "length", empty content) and the turn failed. reasoning="none" turns thinking off (LM Studio
    reasoning_effort), the bridge's Ollama path already does (think: False); left on, the budget is larger."""
    msgs, schema = LocalChooser.msgs, LocalChooser.schema

    def sent_with(self, **kw):
        sent = []
        def fake(req, timeout):
            sent.append(json.loads(req.data.decode())); return reply('{"choice": "C1"}')
        with mock.patch.object(L, "urlopen", fake):
            L.make_choose("http://127.0.0.1:1234/v1", "gemma", **kw)("q", self.msgs, self.schema)
        return sent[0]

    def test_thinking_off_is_sent_to_lm_studio(self):
        body = self.sent_with(reasoning="none")
        self.assertEqual(body["reasoning_effort"], "none")
        self.assertEqual(body["max_tokens"], 1024)

    def test_thinking_left_on_gets_room_to_finish(self):
        body = self.sent_with()
        self.assertNotIn("reasoning_effort", body)
        self.assertEqual(body["max_tokens"], 4096)

    def test_a_reply_cut_off_while_thinking_is_named(self):
        def fake(req, timeout):
            return _Resp(json.dumps({"choices": [{"finish_reason": "length", "message": {"content": ""}}],
                                     "usage": {"prompt_tokens": 1700, "completion_tokens": 1024,
                                               "completion_tokens_details": {"reasoning_tokens": 1021}}}).encode())
        before = dict(L.STATS)
        with mock.patch.object(L, "urlopen", fake):
            with self.assertRaises(ollama_client.OllamaError) as cm:
                L.make_choose("http://127.0.0.1:1234/v1", "gemma")("q", self.msgs, self.schema)
        self.assertIn("token budget", str(cm.exception))
        self.assertEqual(L.STATS["truncated"] - before.get("truncated", 0), 2)


if __name__ == "__main__":
    unittest.main()
