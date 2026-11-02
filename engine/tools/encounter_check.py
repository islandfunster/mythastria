"""ENCOUNTER-CHECK-01 (GM 2026-10-28: "before running a game, the GM can make sure the encounters are winnable"; "It's
for the GM only. Players don't need to see it."; the report: win chance and risk). On the Play an adventure page the GM
checks the loaded adventure's encounters against the table's own party (the saved characters ticked there, each at its
own level, and any test characters): each encounter's map, with the campaign's saved Remix when it fits this party, is
fought a few times by the simulator (both sides played by its tactics, instant dice, the party fresh: full Hit Points,
slots and uses). Per encounter: wins out of the runs, characters dropped and killed per run, rounds, and a verdict:
- winnable: the party won every run and nobody died;
- risky: the party won at least half the runs, but lost some, or a character died, or one dropped per run or more;
- deadly: the party won fewer than half;
- not rated: the simulator could not settle most runs (a creature that can't reach the party, nobody hostile).
A sampled estimate for the GM's prep, never shown to players; Remix (on the same page) changes an encounter that is too
hard or too easy. The fights run in a separate process, one encounter at a time, so the live table is never touched.
"""
import copy
import json
import subprocess
import sys
import tempfile
import threading
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RUNS, ROUNDS, TIMEOUT = 5, 10, 240                               # per encounter: runs, rounds per run, seconds


def verdict(r):
    if r["runs"] == 0 or r["timeout"] * 2 >= r["runs"]:            # most fights unsettled (a creature that can't
        return "not rated"                                       # reach the party, or no one hostile)
    if r["won"] * 2 < r["runs"]:
        return "deadly"
    if r["won"] < r["runs"] or r["dead"] or r["drops_per_run"] >= 1:
        return "risky"
    return "winnable"


class Checks:
    def __init__(self, runner=None):
        self.lock = threading.Lock()
        self.jobs = {}
        self.busy = False
        self.runner = runner or run_one

    def start(self, fights, party, level, extra, notes=None):
        """fights: [{scenario, place, raw}] (each raw map with its saved Remix applied when it fits); party: every
        character's name (a saved character's too, as Play live's party); extra: the saved characters' builds."""
        with self.lock:
            if self.busy:
                raise ValueError("A check is already running: wait for it to finish.")
            job = {"id": uuid.uuid4().hex, "status": "running", "done": 0, "of": len(fights), "results": [],
                   "party": list(party), "level": level, "notes": list(notes or []),
                   "runs": RUNS, "rounds": ROUNDS}
            self.jobs = {k: v for k, v in list(self.jobs.items())[-7:]}
            self.jobs[job["id"]] = job
            self.busy = True
        threading.Thread(target=self._run, args=(job["id"], copy.deepcopy(fights), list(party), level, copy.deepcopy(extra)),
                         daemon=True).start()
        return self.view(job["id"])

    def _run(self, jid, fights, party, level, extra):
        try:
            for f in fights:
                try:
                    r = self.runner({"raw": f["raw"], "party": party, "level": level, "extra": extra,
                                     "seeds": list(range(1, RUNS + 1)), "rounds": ROUNDS})
                    row = {"scenario": f["scenario"], "place": f["place"], "remix": f.get("remix"), "verdict": verdict(r),
                           "won": r["won"], "lost": r["lost"], "timeout": r["timeout"], "runs": r["runs"],
                           "drops_per_run": round(r["drops_per_run"], 2), "dead": r["dead"],
                           "avg_rounds": None if r["avg_rounds"] is None else round(r["avg_rounds"], 1)}
                except Exception as e:                           # one encounter that can't be fought: say so, go on
                    row = {"scenario": f["scenario"], "place": f["place"], "verdict": "not rated",
                           "error": str(e)[:300]}
                with self.lock:
                    job = self.jobs[jid]
                    job["results"].append(row)
                    job["done"] += 1
            with self.lock:
                self.jobs[jid]["status"] = "complete"
        except Exception as e:
            with self.lock:
                self.jobs[jid].update(status="failed", error=str(e)[:300])
        finally:
            with self.lock:
                self.busy = False

    def view(self, jid):
        with self.lock:
            job = self.jobs.get(jid) if isinstance(jid, str) else None
            if not job:
                raise ValueError("No such check (checks are forgotten when Mythastria restarts).")
            return copy.deepcopy(job)


def run_one(payload):
    """One encounter's runs in a disposable process (two simulators in one process collide)."""
    with tempfile.TemporaryDirectory(prefix="mythastria-check-") as tmp:
        source, output = Path(tmp) / "in.json", Path(tmp) / "out.json"
        source.write_text(json.dumps(payload), encoding="utf-8")
        try:
            run = subprocess.run([sys.executable, str(Path(__file__).resolve()), str(source), str(output)],
                                 cwd=str(ROOT), capture_output=True, text=True, timeout=TIMEOUT)
        except subprocess.TimeoutExpired:
            raise RuntimeError("the runs took longer than %d seconds" % TIMEOUT) from None
        if run.returncode or not output.exists():
            raise RuntimeError((run.stderr.strip().splitlines() or ["no result"])[-1])
        return json.loads(output.read_text(encoding="utf-8"))


def fight(payload):
    import encounter_tuner as tuner
    sc = tuner.with_party(payload["raw"], payload["party"], payload["level"], extra=payload.get("extra") or None)
    r = tuner.simulate(sc, payload["seeds"], payload["rounds"], instant=True)
    r.pop("rounds", None)
    return r


if __name__ == "__main__":
    sys.path[:0] = [str(ROOT / "tools"), str(ROOT / "sim"), str(ROOT / "mythastria_core")]
    out = fight(json.loads(Path(sys.argv[1]).read_text(encoding="utf-8")))
    Path(sys.argv[2]).write_text(json.dumps(out), encoding="utf-8")
