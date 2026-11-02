"""CHAT-MODEL-01 (GM 2026-11-01: "make sure chat allows you to load an llm"; asked, "Yes, build it"): the GM chooses a local
model server and a model in the chat window, loads it and asks it things. The model that is loaded is the service's
llm_url and llm_model, so the Rules monitor and the map-site designer use it too.

GM only: the route is on the GM door, never a door route, and the talk is kept apart from the table chat (sim/table_chat.py),
so no seat can see it. Local only, as the Rules monitor is: a frontier model reads the engine instead (GM 2026-11-01).
The model never touches a fight: it answers the GM, and rules stay with the engine.
"""
import json
import re
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

SERVERS = (("LM Studio", "http://127.0.0.1:1234/v1"), ("Ollama", "http://127.0.0.1:11434/v1"))
LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1"}
MAX_QUESTION, MAX_TALK, MAX_TOKENS = 1000, 20, 1200
GUIDE = ("You help the GM of a tabletop game played under the SRD 5.2.1 rules (the 2024 rules) on Mythastria. Answer in a few "
         "plain sentences. Rules questions go by the SRD 5.2.1; say so when you are not sure. You can't see or change the fight.")


class ModelError(ValueError):
    pass


def check_local(url):
    host = (urlparse(url or "").hostname or "").lower() if isinstance(url, str) else ""
    if host not in LOCAL_HOSTS:
        raise ModelError("Refused: %s is not on this PC. Only a local model server loads here." % url)
    return url.rstrip("/")


def list_models(url, timeout=3):
    """The chat models a server offers (embedding models can't answer, so they stay out)."""
    base = check_local(url)
    try:
        with urlopen(base + "/models", timeout=timeout) as r:
            ids = [m.get("id") for m in json.loads(r.read().decode()).get("data", [])]
    except (OSError, ValueError):
        raise ModelError("No model server answers at %s: start it, then try again." % base)
    return [i for i in ids if i and "embed" not in i.lower()]


def servers():
    """Each known server: its name, address, whether it answers and its models."""
    out = []
    for name, url in SERVERS:
        try:
            out.append({"name": name, "url": url, "up": True, "models": list_models(url)})
        except ModelError:
            out.append({"name": name, "url": url, "up": False, "models": []})
    return out


def _clean(text):
    """A thinking model's reply, without its thinking."""
    return re.sub(r"<think>.*?(</think>|$)", "", str(text or ""), flags=re.S).strip()


def complete(messages, url, model, max_tokens=MAX_TOKENS, timeout=240):
    base = check_local(url)
    payload = {"model": model, "messages": messages, "temperature": 0.3, "max_tokens": max_tokens, "stream": False}
    req = Request(base + "/chat/completions", data=json.dumps(payload).encode(), method="POST", headers={"Content-Type": "application/json"})
    try:
        with urlopen(req, timeout=timeout) as r:
            resp = json.loads(r.read().decode())
    except HTTPError as e:
        raise ModelError("The model server answered HTTP %s: %s" % (e.code, e.read().decode(errors="replace")[:200]))
    except (URLError, TimeoutError, OSError):
        raise ModelError("No model server answers at %s: start it, then try again." % base)
    except ValueError:
        raise ModelError("The model server's answer could not be read.")
    try:
        return _clean(resp["choices"][0]["message"].get("content"))
    except (KeyError, IndexError, TypeError, AttributeError):
        raise ModelError("The model server sent no answer.")


def load(url, model):
    """A server loads a model at its first request, so a short one loads it (a big model can take a minute)."""
    if not isinstance(model, str) or not model:
        raise ModelError("Choose a model first.")
    if model not in list_models(url):
        raise ModelError("%s is not on that server." % model)
    complete([{"role": "user", "content": "Say OK."}], url, model, max_tokens=8)


def ask(talk, question, url, model):
    """The model's answer to the GM, with the talk so far ({who, text}, the GM's lines marked who: GM)."""
    if not isinstance(question, str) or not question.strip():
        raise ModelError("Type a question first.")
    if len(question) > MAX_QUESTION:
        raise ModelError("A question can be %d characters at most." % MAX_QUESTION)
    msgs = [{"role": "system", "content": GUIDE}]
    msgs += [{"role": "user" if t["who"] == "GM" else "assistant", "content": t["text"]} for t in talk[-MAX_TALK:]]
    answer = complete(msgs + [{"role": "user", "content": question.strip()}], url, model)
    if not answer:
        raise ModelError("The model gave no answer. Try again, or load another model.")
    return answer
