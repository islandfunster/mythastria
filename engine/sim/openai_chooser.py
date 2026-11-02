"""OPENAI-NPC-01 (2026-10-14): an OpenAI model as the monsters' decision maker in the simulator only.

  py sim/run_sim.py sim/scenarios/ward_chamber.json --party srd_pregens --openai gpt-5.5 [--seed N]

The bridge asks for every NPC decision through ollama_client.choose(model, messages, json_schema); this module gives
the simulator a drop-in replacement that sends the same messages and the same answer schema to the OpenAI Responses
API instead of the local Ollama model. Everything else is unchanged: the bridge builds the legal options, checks the
reply, and the fake FG rolls the dice. Nothing here is used by the live bridge.

What is sent per decision: the bridge's prompt for that turn (creature names, hit-point descriptions, positions and
distances, the legal options, rules notes from SRD 5.2.1 stat blocks). The API key is read as review_openai.py does
(environment or the Windows user environment) and never printed. Calls, tokens and time are counted in STATS.
"""
import json, time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import ollama_client

API = "https://api.openai.com/v1/responses"
STATS = {"calls": 0, "failures": 0, "input_tokens": 0, "output_tokens": 0, "seconds": 0.0}


def api_key():
    import os, sys
    key = os.environ.get("OPENAI_API_KEY", "")
    if not key and sys.platform == "win32":
        import winreg
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as k:
                key = winreg.QueryValueEx(k, "OPENAI_API_KEY")[0]
        except OSError:
            key = ""
    return key


def make_choose(model, effort="low", timeout=180, key=None):
    """A choose(model, messages, json_schema) that answers with `model` on the OpenAI API."""
    key = key or api_key()
    if not key:
        raise SystemExit("OPENAI_API_KEY is not set: the OpenAI chooser cannot run.")

    def choose(_ollama_model, messages, json_schema):
        system = "\n\n".join(m["content"] for m in messages if m.get("role") == "system")
        rest = [{"role": m["role"], "content": m["content"]} for m in messages if m.get("role") != "system"]
        payload = {"model": model, "instructions": system, "input": rest,
                   "text": {"format": {"type": "json_schema", "name": "npc_decision", "schema": json_schema,
                                       "strict": False}}}
        if effort:
            payload["reasoning"] = {"effort": effort}
        req = Request(API, data=json.dumps(payload).encode(), method="POST",
                      headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"})
        started = time.time()
        STATS["calls"] += 1
        try:
            with urlopen(req, timeout=timeout) as r:
                resp = json.loads(r.read().decode())
        except HTTPError as e:
            STATS["failures"] += 1
            raise ollama_client.OllamaError("OpenAI HTTP %s: %s" % (e.code, e.read().decode(errors="replace")[:200]))
        except (URLError, TimeoutError) as e:
            STATS["failures"] += 1
            raise ollama_client.OllamaError("OpenAI request failed: %s" % e)
        finally:
            STATS["seconds"] += time.time() - started
        usage = resp.get("usage") or {}
        STATS["input_tokens"] += int(usage.get("input_tokens") or 0)
        STATS["output_tokens"] += int(usage.get("output_tokens") or 0)
        text = "".join(c.get("text", "") for item in resp.get("output") or [] if item.get("type") == "message"
                       for c in item.get("content") or [] if c.get("type") == "output_text")
        try:
            reply = json.loads(text)
        except ValueError:
            STATS["failures"] += 1
            raise ollama_client.OllamaError("OpenAI did not return valid JSON.")
        if not isinstance(reply, dict):
            STATS["failures"] += 1
            raise ollama_client.OllamaError("OpenAI did not return a JSON object.")
        return reply

    return choose
