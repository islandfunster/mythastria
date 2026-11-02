"""REMIX-02: deterministic proposals. Plain data; Python is the sole rules authority.

Never edit an adventure. Preserve original occupied slots and each slot's maximum
footprint; never synthesize attack statistics, hazards or mechanical dialogue outcomes.
"""
import copy
import hashlib
import json
import math
import random
import re
from pathlib import Path

import bestiary_catalog as bc
import remix_spec

ROOT = Path(__file__).resolve().parent.parent
BANDS = ['below low', 'low', 'moderate', 'high', 'above high']
SLUG = re.compile(r'^[a-zA-Z0-9][a-zA-Z0-9_-]{0,47}$')


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def integer(value, low, high, label):
    if type(value) is not int or not low <= value <= high:
        raise ValueError('%s must be an integer from %d to %d.' % (label, low, high))
    return value


def slug(value):
    if not isinstance(value, str) or not SLUG.fullmatch(value):
        raise ValueError('Campaign: 1-48 letters, digits, underscores or hyphens.')
    return value


def base_name(name):
    return re.sub(r'\s+\d+$', '', name).strip()


def footprint(c):
    return max(1, math.ceil(float(c.get('space') or 5) / 5))


def load_catalog():
    """Use the shipped SRD JSON even when no FG module is installed.

    Prefer the full SRD catalogue if present. Otherwise classify the converted
    blocks, marking absent habitat/language data for review rather than inventing it.
    """
    raw = json.loads((ROOT / 'sim/creatures/srd_library.json').read_text(encoding='utf-8'))
    blocks = raw['creatures']
    full = {}
    # Catalogue load() handles the actual filename used by CATALOG-01.
    try:
        full = {c['name']: c for c in bc.load() if c.get('source') == 'srd'}
    except (OSError, ValueError, TypeError, KeyError):
        pass
    out = {}
    for name, c in sorted(blocks.items()):
        meta = full.get(name)
        if meta is None:
            f = {k: c.get(k, '') for k in ('cr', 'xp', 'hp', 'ac', 'type', 'size', 'speed', 'senses', 'skills')}
            f['abilities'] = {'intelligence': {'score': c.get('int')}, 'wisdom': {'score': 10 + 2 * c.get('wis_mod', 0)}}
            f['actions'] = {str(i): a for i, a in enumerate(c.get('actions', []))}
            f['traits'] = {str(i): t for i, t in enumerate(c.get('traits', [])) if isinstance(t, dict)} if isinstance(c.get('traits'), list) else {}
            meta = bc.classify(bc.normalise({'name': name, 'source': 'srd', 'fields': f}))
            meta['incomplete_metadata'] = True
        out[name] = {'block': copy.deepcopy(c), 'meta': copy.deepcopy(meta)}
    return out


def measured(rows, name, level, arena):
    return next((r for r in rows if r.get('creature') == name and r.get('level') == level
                 and r.get('arena') == arena and r.get('runs', 0) >= 3 and not r.get('issues')
                 and not r.get('stuck') and r.get('plays_as') in BANDS
                 and r.get('timeout', 0) < r.get('runs', 1) / 2), None)


def match_groups(enc, sc):
    """Fail closed on drift; v1 remixes one complete described fight, not a subset."""
    foes = [c for c in sc['combatants'] if c.get('side') == 'foe' and not c.get('pc')]
    if len(foes) != sum(g['count'] for g in enc['original']):
        raise ValueError('Description does not cover this complete fight; refresh its encounter description.')
    groups = []
    for g in enc['original']:
        group = [c for c in foes if base_name(c['name']) == g['srd']]
        if len(group) != g['count'] or sorted((c['x'], c['y']) for c in group) != sorted(tuple(p) for p in g['start']):
            raise ValueError('Creature names or starting positions changed; refresh the encounter description.')
        groups.append(group)
    return groups


def target_band(enc, difficulty):
    current = enc['difficulty']['measured']['plays_as']
    if difficulty == 'same':
        return current
    if difficulty in ('easier', 'harder'):
        return BANDS[max(0, min(4, BANDS.index(current) + (-1 if difficulty == 'easier' else 1)))]
    if difficulty in ('low', 'moderate', 'high'):
        return difficulty
    raise ValueError('Difficulty: same, easier, harder, low, moderate or high.')


def propose(desc, sc, catalog, rows, *, seed=1, difficulty='same', freshness=True, level=None, tone=None):
    integer(seed, 0, 2**31 - 1, 'Seed')
    if type(freshness) is not bool:
        raise ValueError('Freshness is true or false.')
    if not isinstance(desc, dict) or remix_spec.check(desc):
        raise ValueError('Encounter description is incomplete or invalid.')
    if len(desc['encounters']) != 1:
        raise ValueError('This version needs one complete encounter per description.')
    enc = desc['encounters'][0]
    level = integer(level if level is not None else enc['level'], 1, 8, 'Level')
    integer(enc['party_size'], 1, 7, 'Party size')
    groups = match_groups(enc, sc)
    filters = enc['remix']['filters']
    tone = tone or filters['tone_cap']
    if tone not in bc.TONES or bc.TONES.index(tone) > bc.TONES.index(filters['tone_cap']):
        raise ValueError('Tone must be at or below the encounter tone cap.')
    target = target_band(enc, difficulty)
    # XP is only a prefilter; measured data ranks alternatives when it exists.
    current = enc['difficulty']['measured']['plays_as']
    scale = 0.65 if BANDS.index(target) < BANDS.index(current) else 1.5 if BANDS.index(target) > BANDS.index(current) else 1.0
    # A changed party level adjusts only the XP prefilter, never a stat block.
    scale *= bc.XP_BUDGET[level][1] / bc.XP_BUDGET[enc['level']][1]
    rng = random.Random(seed)
    result = copy.deepcopy(sc)
    replacements, warnings = [], []
    original_names = {g['srd'] for g in enc['original']}
    allow_substitution = any('creature' in str(v).lower() for v in enc['remix']['may_change'])
    arena = 'flooded' if any(z.get('kind') == 'water' for z in sc.get('zones', [])) else 'open'
    for g, actors in zip(enc['original'], groups):
        source = catalog.get(g['srd'])
        if not source:
            raise ValueError('Original creature is absent from the shipped SRD library: ' + g['srd'])
        wanted_xp = source['block']['xp'] * scale
        limit = min(footprint(c) for c in actors)
        source_measure = measured(rows, g['srd'], level, arena)
        options = []
        for name, item in sorted(catalog.items()):
            c, m = item['block'], item['meta']
            if (not allow_substitution and name != g['srd']) or footprint(c) != limit or c.get('xp', 0) <= 0 or not c.get('actions'):
                continue
            if name in remix_spec.SRD_MOUNTS and name != g['srd']:
                continue                                            # a mount is an animal, never a new foe (GM 2026-10-23)
            max_size = remix_spec.SIZES.index(filters['max_size'])
            size_rank = next((i for i, size in enumerate(remix_spec.SIZES) if size.lower() == str(c.get('size', '')).lower()), {1: 2, 2: 3, 3: 4}.get(footprint(c), 5))
            if size_rank > max_size or bc.TONES.index(m['tone']) > bc.TONES.index(tone):
                continue
            if filters.get('themes') and not set(filters['themes']) & set(m.get('themes', [])):
                continue
            if filters.get('roles') and not set(filters['roles']) & set(m.get('roles', [])):
                continue
            # Hard habitat mismatch is refused; missing/inferred metadata stays visible.
            habitats = m.get('habitat') or []
            if filters.get('habitats') and habitats and not any(h.lower().startswith(w.lower()) for h in habitats for w in filters['habitats']):
                continue
            speeds = bc.speeds(c.get('speed'))
            old_speeds = bc.speeds(source['block'].get('speed'))
            # Preserve flight/swimming-dependent starting slots, not merely the map theme.
            if (old_speeds.get('fly') or source['block'].get('fly') or any(a.get('flying') for a in actors)) and not (speeds.get('fly') or c.get('fly')):
                continue
            if old_speeds.get('swim') and not speeds.get('swim'):
                continue
            # 2026-10-21: a swimmer that barely moves on land (a Piranha's 5 ft) is only offered where there is water.
            if arena != 'flooded' and speeds.get('swim') and (speeds.get('walk') or 0) < 10 and not (speeds.get('fly') or c.get('fly')):
                continue
            if not 0.35 <= c['xp'] / max(1, wanted_xp) <= 2.5:
                continue
            row = measured(rows, name, level, arena)
            distance = abs(math.log(c['xp'] / max(1, wanted_xp)))
            if row and source_measure and enc['party_size'] == 4:
                # An arena proxy, never a claim about this mixed encounter.
                proxy = row['drops_per_run'] * g['count'] / row['count']
                reference = source_measure['drops_per_run'] * g['count'] / source_measure['count'] * scale
                distance += abs(proxy - reference) * .4
            distance += .8 if freshness and name in original_names else 0
            distance += .15 if set(g['roles']).isdisjoint(m.get('roles', [])) else 0
            options.append((distance + rng.random() * .6, name, row))
        if not options:
            chosen, row = g['srd'], source_measure
            warnings.append('No safe substitute for %s; original group retained.' % chosen)
        else:
            # 2026-10-21 (GM: "remix doesn't have ... variety in the seeds"): the seed picks among every close fit, not
            # only the best score, so different seeds offer different safe creatures.
            best = min(options)[0]
            _, chosen, row = rng.choice(sorted(o for o in options if o[0] <= best + .5))
        new = catalog[chosen]
        for actor in actors:
            replacement = copy.deepcopy(actor) if chosen == g['srd'] else {
                k: copy.deepcopy(v) for k, v in new['block'].items()
                if k not in ('name', 'source', 'made', 'played', 'text', 'gm_text', 'xp', 'cr')}
            replacement.update(id=actor['id'], name=actor['name'] if chosen == g['srd'] else _next_name(result, chosen, actor['id']),
                               srd_name=chosen, side='foe', x=actor['x'], y=actor['y'], init=new['block'].get('init', actor.get('init', 10)))
            # Token IDs belong to the old art; live-view resolves the new SRD name.
            if chosen != g['srd']:
                replacement.pop('token_id', None)
            idx = next(i for i, c in enumerate(result['combatants']) if c['id'] == actor['id'])
            result['combatants'][idx] = replacement
        limitations = list(new['block'].get('text') or []) + list(new['block'].get('gm_text') or [])
        if limitations:
            warnings.append('%s requires GM review: %s' % (chosen, '; '.join(str(x) for x in limitations)[:700]))
        if new['meta'].get('incomplete_metadata'):
            warnings.append('%s: theme/role/tone inferred from converted block; habitat/languages may be incomplete.' % chosen)
        replacements.append({'from': g['srd'], 'to': chosen, 'count': g['count'], 'xp_each': new['block']['xp'],
                             'roles': new['meta'].get('roles', []), 'measurement': copy.deepcopy(row),
                             'positions': [[c['x'], c['y']] for c in actors]})
    changed = any(g['from'] != g['to'] for g in replacements)
    if enc.get('events'):
        warnings.append('Hazards/events kept as authored; no new hazard automation or tuning in this slice.')
    warnings += list(enc.get('not_simulated', []))
    warnings.append('Whole-encounter difficulty is unverified until paired proof finishes; arena scores are proxies.')
    if level != enc['level']:
        warnings.append('Original published measurement was for level %d; re-prove this level.' % enc['level'])
    # Do not mechanically repurpose creature-specific bargains or songs.
    routes = copy.deepcopy(enc['routes']) if not changed else [{
        'id': 'remix-avoid', 'approach': 'avoid', 'who': [], 'condition': 'GM judges a viable route around the new creatures.',
        'success': 'Avoid this fight; GM preserves the locked clues and access below.',
        'failure': 'The encounter remains; no automatic conditions or penalties.', 'canon': '\n'.join(enc['story_job']['locked']),
        'clue_elsewhere': 'GM must place each required clue on an accessible route before accepting.', 'needs_review': True}, {
        'id': 'remix-distract', 'approach': 'distract', 'who': [g['to'] for g in replacements],
        'condition': 'GM agrees a distraction fitting the new creatures and terrain.',
        'success': 'GM adjudicates a crossing or advantage in position; no automatic mechanical effect.',
        'failure': 'The encounter remains; no automatic conditions or penalties.', 'canon': '\n'.join(enc['story_job']['locked']), 'needs_review': True}]
    if changed:
        warnings.append('Creature-specific dialogue replaced with GM-reviewed route drafts. No song, speech or new powers are invented.')
    names = ', '.join('%d %s' % (g['count'], g['to']) for g in replacements)
    result = materialize(desc, sc, catalog, {g['from']: g['to'] for g in replacements})
    proposal = {'format': 'mythastria-remix/1', 'seed': seed, 'level': level, 'party_size': enc['party_size'],
                'target': target, 'difficulty': difficulty, 'tone': tone, 'freshness': freshness,
                'room': enc['room'], 'base_hash': digest(sc), 'description_hash': digest(desc),
                'catalog_hash': digest(catalog), 'scenario': result, 'groups': replacements,
                'story_job': copy.deepcopy(enc['story_job']), 'must_keep': copy.deepcopy(enc['remix']['must_keep']),
                'routes': routes, 'read_aloud': 'Ahead: %s. Their presence changes the crossing; the place keeps its old secrets.' % names,
                'warnings': sorted(set(warnings)), 'estimate': {'xp': sum(g['count'] * g['xp_each'] for g in replacements),
                'basis': 'XP prefilter and available same-level arena measurements; not a mixed-encounter proof.'},
                'proof': None}
    proposal['id'] = digest(proposal)[:32]
    return proposal


def materialize(desc, sc, catalog, selected):
    """Rebuild a saved layer from mounted source data and server-owned SRD blocks."""
    groups = match_groups(desc['encounters'][0], sc)
    result = copy.deepcopy(sc)
    for g, actors in zip(desc['encounters'][0]['original'], groups):
        chosen = selected[g['srd']]
        if chosen == g['srd']:
            continue
        block = catalog[chosen]['block']
        for actor in actors:
            if footprint(block) > footprint(actor):
                raise ValueError('Saved replacement no longer fits its original slot.')
            c = {k: copy.deepcopy(v) for k, v in block.items()
                 if k not in ('name', 'source', 'made', 'played', 'text', 'gm_text', 'xp', 'cr')}
            index = next(i for i, old in enumerate(result['combatants']) if old['id'] == actor['id'])
            c.update(id=actor['id'], name=_next_name(result, chosen, actor['id']), srd_name=chosen,
                     side='foe', x=actor['x'], y=actor['y'], init=block.get('init', actor.get('init', 10)))
            result['combatants'][index] = c
    return result


def _next_name(scenario, kind, own_id):
    """2026-10-21 (GM): "Kind 1", "Kind 2" ... per creature kind (was the creature's place in the whole list: 5-8,
    9-12), skipping a name another creature on the map already has."""
    used = {c.get('name') for c in scenario.get('combatants', []) if c.get('id') != own_id}
    n = 1
    while '%s %d' % (kind, n) in used:
        n += 1
    return '%s %d' % (kind, n)
