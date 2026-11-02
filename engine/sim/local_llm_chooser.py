"""LOCAL-LLM-01 (2026-10-14): any LOCAL OpenAI-compatible model server as the monsters' decision maker (simulator).

  py sim/run_sim.py sim/scenarios/ward_chamber.json --party srd_pregens --llm-url http://127.0.0.1:1234/v1 --model <name>

LM Studio, llama.cpp's server, Jan, LocalAI, vLLM and Ollama (http://127.0.0.1:11434/v1) all answer the same
"/chat/completions" request. This drop-in replacement for ollama_client.choose sends the bridge's messages and answer
schema there; the bridge still builds the legal options and checks the reply, and the fake FG rolls the dice.
Offline by design: the URL must point at this PC (127.0.0.1, localhost or ::1); anything else is refused, so a cloud
service cannot be reached this way (GM decision NO-OPENAI-NPC). No API key is sent.
"""
import json, time
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

import ollama_client

LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1"}
STATS = {"calls": 0, "failures": 0, "truncated": 0, "prompt_tokens": 0, "completion_tokens": 0, "seconds": 0.0}


def check_local(url):
    host = (urlparse(url).hostname or "").lower()
    if host not in LOCAL_HOSTS:
        raise SystemExit("Refused: %s is not on this PC. Only a local model server may play the monsters." % url)
    return url.rstrip("/")


def make_choose(base_url, model, timeout=300, reasoning=None, max_tokens=None):
    """reasoning (2026-10-16): None leaves the model's own default (Gemma 4 in LM Studio thinks first); "none", "low",
    "medium" or "high" is sent as LM Studio's reasoning_effort ("none" = no thinking, like the bridge's Ollama path,
    think: False). A thinking model gets a 4096-token budget, otherwise 1024: at level 3 Gemma spent all 1024 thinking
    and returned nothing (finish_reason "length"); such a reply is counted in STATS["truncated"] and named."""
    base = check_local(base_url)
    budget = max_tokens or (1024 if reasoning == "none" else 4096)

    def choose(_ollama_model, messages, json_schema):
        last = None
        for temperature in (0.6, 0.2):    # like the Ollama chooser: one cooler retry for a reply that is not JSON
            payload = {"model": model, "messages": messages, "temperature": temperature, "max_tokens": budget,
                       "stream": False,
                       "response_format": {"type": "json_schema",
                                           "json_schema": {"name": "npc_decision", "schema": json_schema, "strict": False}}}
            if reasoning:
                payload["reasoning_effort"] = reasoning
            req = Request(base + "/chat/completions", data=json.dumps(payload).encode(), method="POST",
                          headers={"Content-Type": "application/json"})
            started = time.time()
            STATS["calls"] += 1
            try:
                with urlopen(req, timeout=timeout) as r:
                    resp = json.loads(r.read().decode())
            except HTTPError as e:
                STATS["failures"] += 1
                raise ollama_client.OllamaError("Local model server HTTP %s: %s" % (e.code, e.read().decode(errors="replace")[:200]))
            except (URLError, TimeoutError) as e:
                STATS["failures"] += 1
                raise ollama_client.OllamaError("Local model server not reachable at %s: %s" % (base, e))
            finally:
                STATS["seconds"] += time.time() - started
            usage = resp.get("usage") or {}
            STATS["prompt_tokens"] += int(usage.get("prompt_tokens") or 0)
            STATS["completion_tokens"] += int(usage.get("completion_tokens") or 0)
            choice = (resp.get("choices") or [{}])[0]
            content = (choice.get("message") or {}).get("content") or ""
            try:
                reply = ollama_client._extract_json(content)
            except ValueError as e:
                last = e
                if choice.get("finish_reason") == "length":
                    STATS["truncated"] += 1
                    think = ((usage.get("completion_tokens_details") or {}).get("reasoning_tokens"))
                    last = ValueError("the reply hit the %d-token budget before its answer%s" % (
                        budget, " (%s tokens spent thinking)" % think if think else ""))
                continue
            if isinstance(reply, dict):
                return reply
        STATS["failures"] += 1
        if last is not None and "token budget" in str(last):
            raise ollama_client.OllamaError("The local model did not return a JSON object: %s." % last) from last
        raise ollama_client.OllamaError("The local model did not return a JSON object.") from last

    return choose
