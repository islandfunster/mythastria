"""Bounded local diagnostics; never polls campaign routes."""
from collections import OrderedDict
from datetime import datetime
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
import re, threading, uuid
import json

VERSION = "0.8.7"
MAX_EVENTS, MAX_REPORT = 120, 12000

def damage_evidence_report(record, parser_state, capabilities):
    """Export one existing parser record. No native calls or inferred dice."""
    signature = "parseNPCPower(nodePower,false)"
    attempt = record.get("attempts", {}).get(signature)
    if attempt is None:
        raise ValueError("Verified-signature attempt not present. Run /aibridge probepowparser.")
    fields = attempt.get("fields", [])
    prefixes = sorted({f.get("key", "").rsplit(".", 1)[0] for f in fields
                       if f.get("key", "").rsplit(".", 1)[-1].lower() in ("type", "stype")
                       and str(f.get("value", "")).lower() == "damage"})
    def is_damage(field):
        key = field.get("key", "")
        return any(key == prefix or key.startswith(prefix + ".") for prefix in prefixes)
    # Preserve every captured scalar's original path/type/value. Damage subtrees
    # come first so a long report retains the mechanics evidence.
    ordered = sorted(fields, key=lambda f: (not is_damage(f), f.get("key", "")))
    relevant_caps = sorted(x for x in capabilities
                           if x.split("|", 1)[0] in ("ActionDamage", "ActionDamageD20", "ActionsManager", "PowerManager"))
    lines = ["# Native NPC damage parser evidence", "",
             "Service version: " + VERSION,
             "Actor: " + clean(record.get("actor_name", "")),
             "Action: " + clean(record.get("power_name", "")),
             "Source CT: " + clean(record.get("ctpath", "")),
             "Action node: " + clean(record.get("node_path", "")),
             "Origin: " + clean(record.get("origin", "")),
             "Parser: " + signature,
             "Parser OK: " + clean(attempt.get("ok", "0")),
             "Parser error: " + clean(attempt.get("error", "")),
             "Snapshot updated: " + clean(parser_state.get("updated")),
             "Probe complete marker received: " + str(parser_state.get("reported_count") is not None),
             "Captured damage action prefixes: " + repr(prefixes),
             "Captured fields: " + str(len(fields)),
             "Read only: no roll, queue pull, campaign write, or guessed damage.",
             "No captured damage type does not prove damage is absent. The existing",
             "probe is bounded to depth 5 and 150 entries per table; deeper data may be missing.",
             "Capability names indicate presence only; they do not verify call signatures.",
             "Review before sharing. Prose, sheets and unrelated actors are omitted.", "",
             "## Relevant native capabilities"]
    lines.extend(clean(x) for x in relevant_caps[:60])
    if not relevant_caps:
        lines.append("Not captured. Run /aibridge capabilities and export again.")
    if len(relevant_caps) > 60:
        lines.append("Additional capability entries omitted: " + str(len(relevant_caps)-60))
    lines.extend(["", "## Captured structured fields (one JSON object per line)"])
    report = "\n".join(lines) + "\n"
    omitted = 0
    for index, field in enumerate(ordered):
        line = json.dumps({k: clean(field.get(k, ""), 700)
                           for k in ("key", "type", "value")}, ensure_ascii=False) + "\n"
        if len(report) + len(line) > MAX_REPORT - 150:
            omitted = len(ordered) - index
            break
        report += line
    report += f"\nFields omitted from this export: {omitted}\n"
    return report

def clean(value, limit=900):
    value = str(value).replace("\r", " ").replace("\n", " ")
    value = re.sub(r"(https?://[^\s?]+)\?[^\s]+", r"\1?[query omitted]", value)
    value = re.sub(r"(?i)\b(api[_-]?key|token|password|secret|authorization)\s*[:=]\s*\S+",
                   r"\1=[redacted]", value)
    return value[:limit] + (" [truncated]" if len(value) > limit else "")

class Recorder:
    def __init__(self):
        self.lock = threading.Lock()
        self.test = None
        self.logger = logging.getLogger("aibridge.local")
        self.logger.setLevel(logging.INFO)
        self.logger.addHandler(logging.NullHandler())

    def enable_file(self, directory):
        directory = Path(directory)
        directory.mkdir(parents=True, exist_ok=True)
        handler = RotatingFileHandler(directory / "bridge.log", maxBytes=1000000,
                                      backupCount=3, encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s %(message)s"))
        self.logger.addHandler(handler)

    def begin(self, label, queue):
        with self.lock:
            self.test = {"id": uuid.uuid4().hex[:12],
                         "started": datetime.now().astimezone().isoformat(),
                         "label": clean(label, 160),
                         "queue_at_start": [clean(x) for x in queue[:5]],
                         "events": OrderedDict(), "omitted": 0}
            return self.test["id"]

    def event(self, kind, message):
        kind, message = clean(kind, 60), clean(message)
        self.logger.info("%s %s", kind, message)
        with self.lock:
            if self.test is None:
                return
            key = (kind, message)
            events = self.test["events"]
            if key in events:
                events[key]["count"] += 1
            elif len(events) < MAX_EVENTS:
                events[key] = {"at": datetime.now().astimezone().isoformat(), "count": 1}
            else:
                self.test["omitted"] += 1

    def report(self, snapshot):
        with self.lock:
            if self.test is None:
                return "No test marker. Click Begin test, reproduce once, then collect.\n"
            t = self.test
            lines = ["# AI Bridge focused diagnostic report", "",
                     "Service version: " + VERSION, "Test: " + t["id"],
                     "Started: " + t["started"], "Label: " + t["label"],
                     "Queue at start: " + repr(t["queue_at_start"]),
                     "FG extension version: reported with captured fg-bridge events; otherwise unknown",
                     "Capture covers bridge messages, not native hit/miss or unrelated FG console errors.",
                     "Redaction is best effort; review before sharing.", "",
                     "## Current snapshot (does not pull or reset queues)"]
            lines.extend(clean(line, 1100) for line in snapshot)
            lines.extend(["", "## New bridge events"])
            for (kind, message), item in t["events"].items():
                lines.append(f'{item["at"]} [{kind}] {message} (x{item["count"]})')
            lines.extend(["", f'Events omitted after limit: {t["omitted"]}',
                          "Redaction is best effort. Queries and credential assignments are masked;",
                          "messages and snapshot fields are bounded. Review before sharing.",
                          "FG console errors outside bridge messages and native hit/miss results",
                          "are not captured. Add the first new console error if needed.",
                          "Observed roll/hit/miss, damage, and target-arrow changes: [fill in]"])
            report = "\n".join(lines) + "\n"
            if len(report) > MAX_REPORT:
                suffix = "\n[Report truncated to 12000 characters; local rotating logs may retain additional bridge events.]\n"
                report = report[:MAX_REPORT-len(suffix)] + suffix
            return report
