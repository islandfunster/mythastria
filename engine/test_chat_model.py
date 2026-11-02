"""CHAT-MODEL-01: the GM's model in the chat window. A stand-in for the model server; no real model is asked."""
import json, sys, unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent
sys.path[:0] = [str(ROOT / "sim"), str(ROOT / "tools"), str(ROOT / "mythastria_core")]
import chat_model as cm
import sim_service


class Reply:
    def __init__(self, data):
        self.data = json.dumps(data).encode()

    def read(self):
        return self.data

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def stand_in(answer="A short answer.", models=("gemma", "text-embedding-nomic")):
    def opened(req, timeout=None):
        url = req if isinstance(req, str) else req.full_url
        if url.endswith("/models"):
            return Reply({"data": [{"id": m} for m in models]})
        stand_in.sent = json.loads(req.data.decode())
        return Reply({"choices": [{"message": {"content": answer}}]})
    return mock.patch.object(cm, "urlopen", opened)


class Model(unittest.TestCase):
    def test_only_a_server_on_this_pc(self):
        for url in ("https://api.openai.com/v1", "http://192.168.1.20:1234/v1", None, 7):
            with self.assertRaises(cm.ModelError):
                cm.check_local(url)
        self.assertEqual(cm.check_local("http://127.0.0.1:1234/v1/"), "http://127.0.0.1:1234/v1")

    def test_embedding_models_are_not_offered(self):
        with stand_in():
            self.assertEqual(cm.list_models(cm.SERVERS[0][1]), ["gemma"])

    def test_a_server_that_is_off_says_so(self):
        with mock.patch.object(cm, "urlopen", side_effect=OSError("off")):
            self.assertEqual({s["up"] for s in cm.servers()}, {False})

    def test_a_model_the_server_lacks_is_refused(self):
        with stand_in(), self.assertRaises(cm.ModelError):
            cm.load(cm.SERVERS[0][1], "nothing")

    def test_a_thinking_model_answers_without_its_thinking(self):
        with stand_in("<think>hm\nhm</think> Yes."):
            self.assertEqual(cm.ask([], "Why?", cm.SERVERS[0][1], "gemma"), "Yes.")
        with stand_in("<think>cut off"), self.assertRaises(cm.ModelError):
            cm.ask([], "Why?", cm.SERVERS[0][1], "gemma")

    def test_the_talk_goes_with_the_question(self):
        talk = [{"who": "GM", "text": "Hello"}, {"who": "gemma", "text": "Hi"}]
        with stand_in():
            cm.ask(talk, "And?", cm.SERVERS[0][1], "gemma")
        self.assertEqual([m["role"] for m in stand_in.sent["messages"]], ["system", "user", "assistant", "user"])


class Service(unittest.TestCase):
    def setUp(self):
        self.s = sim_service.Service()

    def test_load_moves_the_service_model(self):
        with stand_in():
            code, out = self.s.chat_model({"op": "load", "url": cm.SERVERS[1][1], "model": "gemma"})
        self.assertEqual((code, out["url"], out["model"], out["loaded"]), (200, cm.SERVERS[1][1], "gemma", True))
        self.assertEqual((self.s.llm_url, self.s.llm_model), (cm.SERVERS[1][1], "gemma"))

    def test_ask_needs_a_loaded_model_and_stays_out_of_the_table_chat(self):
        with self.assertRaises(ValueError):
            self.s.chat_model({"op": "ask", "text": "Hello"})
        before = json.dumps(self.s.chat)
        with stand_in():
            self.s.chat_model({"op": "load", "url": cm.SERVERS[0][1], "model": "gemma"})
            _, out = self.s.chat_model({"op": "ask", "text": "Hello"})
        self.assertEqual([t["who"] for t in out["talk"]], ["GM", "gemma"])
        self.assertEqual(json.dumps(self.s.chat), before)
        self.assertEqual(self.s.chat_model({"op": "clear"})[1]["talk"], [])

    def test_players_have_no_route_to_it(self):
        self.assertNotIn("/api/chat/model", sim_service.DOOR_ROUTES)


if __name__ == "__main__":
    unittest.main()
