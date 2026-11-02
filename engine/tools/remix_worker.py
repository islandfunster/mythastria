"""Paired Remix proof in a disposable process; no adventure writes or model calls."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT / 'tools'), str(ROOT / 'sim'), str(ROOT / 'mythastria_core')]
import encounter_tuner as tuner


def prove(payload):
    import rests
    runs = {}
    # GM 2026-10-24: a pregen at its own level joins as its build at that level (as a saved character does)
    extra = {n: rests.pregen_build(n, lv) for n, lv in (payload.get('levels') or {}).items()}
    for key in ('original', 'remixed'):
        sc = tuner.with_party(payload[key], payload['members'], payload['level'], extra=extra or None)
        r = tuner.simulate(sc, payload['seeds'], payload['rounds'], instant=True)
        r['plays_as'] = 'not rated' if r['issues'] or r.get('stuck') or r['timeout'] >= r['runs'] / 2 else tuner.verdict(r)
        runs[key] = r
    before, after = runs['original'], runs['remixed']
    reliable = all(r['runs'] >= 3 and r['issues'] == 0 and not r.get('stuck')
                   and r['timeout'] < r['runs'] / 2 for r in runs.values())
    matched = after['plays_as'] == payload['target']
    if payload['difficulty'] == 'same':
        matched = matched and abs(after['drops_per_run'] - before['drops_per_run']) <= .4
    return dict(format='mythastria-remix-proof/1', **runs, seeds=payload['seeds'], rounds=payload['rounds'],
                members=payload['members'], level=payload['level'], levels=payload.get('levels') or {}, target=payload['target'],
                qualified=bool(reliable and matched),
                note='Sampled combat result only. Unimplemented features, dialogue, hazards and party differences still need GM review.')


if __name__ == '__main__':
    report = prove(json.loads(Path(sys.argv[1]).read_text(encoding='utf-8')))
    Path(sys.argv[2]).write_text(json.dumps(report, allow_nan=False), encoding='utf-8')
