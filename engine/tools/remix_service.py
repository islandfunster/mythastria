"""REMIX-02 storage and proof jobs, used by the loopback simulator service.

One process owns a campaign store. JSON snapshots are atomic; concurrent/stale
web writes use a campaign revision. Proof runs in a separate process so it
cannot alter the live simulator's global Python/Lua state.
"""
import copy
import json
import subprocess
import sys
import tempfile
import threading
import uuid
from pathlib import Path

import remix_engine as engine

ROOT = Path(__file__).resolve().parent.parent


class Conflict(ValueError):
    pass


class Remix:
    def __init__(self, scenarios=None, descriptions=None, store=None, catalog=None, rows=None, runner=None, packs=None):
        from adventure_packs import Packs
        self.packs = packs or Packs()
        self.scenarios = Path(scenarios or ROOT / 'sim/scenarios')
        self.descriptions = Path(descriptions or ROOT / 'sim/remix_specs')
        self.store = Path(store or ROOT / 'sim/remixes')
        self._catalog, self._rows = catalog, rows
        self.runner = runner or self._run_proof
        self.lock = threading.RLock()
        self.proposals, self.jobs = {}, {}
        self.busy = False

    @property
    def catalog(self):
        if self._catalog is None:
            self._catalog = engine.load_catalog()
        return self._catalog

    @property
    def rows(self):
        if self._rows is None:
            p = ROOT / 'sim/threat/threat.json'
            self._rows = json.loads(p.read_text(encoding='utf-8'))['rows'] if p.exists() else []
        return self._rows

    def source(self, name):
        return self.packs.source(name)

    def catalog_view(self):
        items, unavailable = [], []
        for encounter in self.packs.encounters():
            try:
                desc, sc = self.source(encounter)
                problems = __import__('remix_spec').check(desc)
                if problems:
                    raise ValueError('; '.join(problems))
                engine.match_groups(desc['encounters'][0], sc)
                e = desc['encounters'][0]
                items.append({'id': encounter, 'scenario': desc['scenario'], 'name': e.get('name') or e['room'],
                              'level': e['level'], 'party_size': e['party_size'], 'tone': e['remix']['filters']['tone_cap']})
            except (OSError, ValueError, KeyError, TypeError) as e:
                unavailable.append({'id': encounter, 'error': str(e)})
        listing = self.packs.listing()
        return {'ok': True, 'encounters': items, 'unavailable': unavailable + listing.pop('unavailable'),
                **listing, 'scope': 'One described complete fight at a time; original map and adventure stay unchanged.'}

    def propose(self, req):
        campaign = engine.slug(req.get('campaign', 'default'))
        name = req.get('encounter')
        desc, sc = self.source(name)
        p = engine.propose(desc, sc, self.catalog, self.rows, seed=req.get('seed', 1), difficulty=req.get('difficulty', 'same'),
                           freshness=req.get('freshness', True), level=req.get('level'), tone=req.get('tone'))
        # Campaign/name are part of identity. A client can never submit statistics.
        p.update(encounter=name, campaign=campaign, source_scenario=desc['scenario'])
        p['id'] = engine.digest(p)[:32]
        with self.lock:
            if p['id'] not in self.proposals and len(self.proposals) >= 32:
                # Never evict a pending proof's proposal.
                old = next((k for k in self.proposals if not any(j['proposal'] == k and j['status'] == 'running' for j in self.jobs.values())), None)
                if old is None:
                    raise Conflict('Proposal cache busy; wait for the proof.')
                self.proposals.pop(old)
            self.proposals[p['id']] = p
            return {'ok': True, 'proposal': self.public(p), 'campaign': self.state(campaign)}

    @staticmethod
    def public(p):
        # The client gets no mutable stat block. Changes refer to server-owned IDs.
        return copy.deepcopy({k: v for k, v in p.items() if k != 'scenario'})

    def _campaign(self, campaign):
        campaign = engine.slug(campaign)
        path = self.store / (campaign + '.json')
        if not path.exists():
            return {'format': 'mythastria-remix-campaign/1', 'campaign': campaign, 'revision': 0, 'active': {}}
        state = json.loads(path.read_text(encoding='utf-8'))
        if state.get('format') != 'mythastria-remix-campaign/1':
            raise ValueError('Unrecognized campaign remix file; preserve it for review.')
        return state

    def state(self, campaign):
        with self.lock:
            st = self._campaign(campaign)
            return {'id': campaign, 'revision': st['revision'], 'active': [self.public(p) for p in st['active'].values()]}

    def _write(self, st):
        self.store.mkdir(parents=True, exist_ok=True)
        path = self.store / (st['campaign'] + '.json')
        temp = path.with_suffix('.' + uuid.uuid4().hex + '.tmp')
        try:
            temp.write_text(json.dumps(st, indent=1, allow_nan=False), encoding='utf-8')
            temp.replace(path)
        finally:
            temp.unlink(missing_ok=True)

    def fresh(self, p):
        desc, sc = self.source(p['encounter'])
        if p['base_hash'] != engine.digest(sc) or p['description_hash'] != engine.digest(desc) or p['catalog_hash'] != engine.digest(self.catalog):
            raise Conflict('Source changed since this proposal; generate a fresh Remix.')
        return sc

    def apply(self, req):
        campaign = engine.slug(req.get('campaign', 'default'))
        with self.lock:
            pid = req.get('proposal')
            if not isinstance(pid, str) or len(pid) != 32:
                raise ValueError('Choose a server-generated proposal ID.')
            p = self.proposals.get(pid)
            if not p or p['campaign'] != campaign:
                raise ValueError('Proposal expired or belongs to another campaign; generate it again.')
            st = self._campaign(campaign)
            revision = req.get('revision')
            if type(revision) is not int or revision != st['revision']:
                raise Conflict('Campaign changed in another window; refresh before applying.')
            self.fresh(p)
            if req.get('reviewed') is not True:
                raise ValueError('Review the story, creature limitations and route drafts before applying.')
            if not (p.get('proof') or {}).get('qualified') and req.get('allow_estimate') is not True:
                raise ValueError('Proof has not qualified this remix; explicitly accept an estimate or run proof.')
            kept = self.public(p)
            # Campaign deltas retain choices, not the original adventure or stat blocks.
            for key in ('story_job', 'must_keep', 'routes'):
                kept.pop(key, None)
            text = req.get('read_aloud', kept['read_aloud'])
            if not isinstance(text, str) or len(text) > 2000:
                raise ValueError('Read-aloud text is at most 2000 characters.')
            kept['read_aloud'] = text
            st['active'][p['source_scenario']] = kept
            st['revision'] += 1
            self._write(st)
            return {'ok': True, 'campaign': self.state(campaign), 'message': 'Saved for the next fight. The original adventure is unchanged.'}

    def remove(self, req):
        campaign = engine.slug(req.get('campaign', 'default'))
        with self.lock:
            st = self._campaign(campaign)
            if type(req.get('revision')) is not int or req['revision'] != st['revision']:
                raise Conflict('Campaign changed in another window; refresh before removing.')
            if not isinstance(req.get('scenario'), str) or req['scenario'] not in st['active']:
                raise ValueError('No saved Remix for that scenario.')
            st['active'].pop(req['scenario'])
            st['revision'] += 1
            self._write(st)
            return {'ok': True, 'campaign': self.state(campaign), 'message': 'Original encounter restored for the next fight.'}

    def resolve(self, scenario, raw, campaign, level, members):
        with self.lock:
            p = self._campaign(campaign)['active'].get(scenario)
            if not p:
                return copy.deepcopy(raw), None
            self.fresh(p)
            if p['level'] != level or p['party_size'] != len(members):
                raise Conflict('Saved Remix was prepared for level %d and %d characters. Match the party or disable saved Remix.' % (p['level'], p['party_size']))
            proof = p.get('proof') or {}
            exact = proof.get('members') == members and proof.get('level') == level and not proof.get('levels')
            meta = self.public(p)
            if proof and not exact:
                meta['warnings'].append('Proof used different characters; this party is an estimate.')
                meta['proof'] = dict(proof, qualified=False)
            desc, current = self.source(p['encounter'])
            # Reconstruct only while its source pack is mounted.
            selected = {g['from']: g['to'] for g in p['groups']}
            scenario = engine.materialize(desc, current, self.catalog, selected)
            return scenario, meta

    def start_proof(self, req, allowed_members):
        with self.lock:
            pid = req.get('proposal')
            if not isinstance(pid, str) or len(pid) != 32:
                raise ValueError('Choose a server-generated proposal ID.')
            p = self.proposals.get(pid)
            if not p:
                raise ValueError('Proposal expired; generate again.')
            members = req.get('members')
            if not isinstance(members, list) or len(members) != p['party_size'] or any(not isinstance(m, str) for m in members) or len(set(members)) != len(members) or any(m not in allowed_members for m in members):
                raise ValueError('Proof fights played test characters, which this SRD version leaves out.')
            # GM 2026-10-24 ("allow them to be selected at different levels"): a pregen's own level, else the proposal's
            levels = req.get('levels') or {}
            if not isinstance(levels, dict) or any(m not in members for m in levels) or                     any(type(v) is not int or not 1 <= v <= 20 for v in levels.values()):
                raise ValueError('A pregen level is 1-20, for a pregen in the party.')   # GM 2026-10-26: levels 10-20
            levels = {m: v for m, v in levels.items() if v != p['level']}
            seeds = req.get('seeds', [1, 2, 3])
            if not isinstance(seeds, list) or not 1 <= len(seeds) <= 5 or any(type(s) is not int for s in seeds) or len(set(seeds)) != len(seeds):
                raise ValueError('Proof uses 1-5 distinct integer seeds.')
            for seed in seeds:
                engine.integer(seed, 0, 2**31 - 1, 'Proof seed')
            rounds = engine.integer(req.get('rounds', 8), 1, 10, 'Rounds')
            if self.busy:
                raise Conflict('One proof is already running; wait for it to finish.')
            original = self.fresh(p)
            jobid = uuid.uuid4().hex
            self.jobs = {k: v for k, v in list(self.jobs.items())[-15:]}
            self.jobs[jobid] = {'id': jobid, 'proposal': p['id'], 'status': 'running'}
            self.busy = True
            payload = {'original': original, 'remixed': p['scenario'], 'members': list(members), 'level': p['level'], 'levels': levels,
                       'seeds': seeds, 'rounds': rounds, 'target': p['target'], 'difficulty': p['difficulty']}
            thread = threading.Thread(target=self._proof, args=(jobid, copy.deepcopy(payload)), daemon=True)
            thread.start()
            return {'ok': True, 'job': copy.deepcopy(self.jobs[jobid])}

    def _proof(self, jobid, payload):
        try:
            report = self.runner(payload)
            with self.lock:
                job = self.jobs[jobid]
                p = self.proposals.get(job['proposal'])
                if p:
                    self.fresh(p)
                    p['proof'] = report
                job.update(status='complete', report=report)
        except Exception as e:
            with self.lock:
                self.jobs[jobid].update(status='failed', error='Proof could not complete: ' + str(e)[:500])
        finally:
            with self.lock:
                self.busy = False

    def proof_status(self, req):
        with self.lock:
            jid = req.get('job')
            if not isinstance(jid, str):
                raise ValueError('Choose a proof job ID.')
            job = self.jobs.get(jid)
            if not job:
                raise ValueError('No such proof job (jobs expire on service restart).')
            p = self.proposals.get(job['proposal'])
            return {'ok': True, 'job': copy.deepcopy(job), 'proposal': self.public(p) if p else None}

    @staticmethod
    def _run_proof(payload):
        with tempfile.TemporaryDirectory(prefix='mythastria-remix-') as tmp:
            source, output = Path(tmp) / 'in.json', Path(tmp) / 'out.json'
            source.write_text(json.dumps(payload), encoding='utf-8')
            try:
                run = subprocess.run([sys.executable, str(ROOT / 'tools/remix_worker.py'), str(source), str(output)],
                                     cwd=str(ROOT), capture_output=True, text=True, timeout=300)
            except subprocess.TimeoutExpired:
                raise RuntimeError('Proof timed out after five minutes. Try fewer seeds or rounds; the remix remains an estimate.') from None
            if run.returncode or not output.exists():
                raise RuntimeError((run.stderr.strip().splitlines() or ['No proof report.'])[-1])
            return json.loads(output.read_text(encoding='utf-8'))
