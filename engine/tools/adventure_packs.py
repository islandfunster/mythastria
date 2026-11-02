"""Data-only, explicitly mounted adventure packs. No imported adventure Python.

The CLI supplies a trusted pack library folder. HTTP may select registered IDs,
never arbitrary paths. Packs start unloaded, and are independent of engine code.
"""
import copy
import json
import re
import threading
from pathlib import Path

ID = re.compile(r'^[A-Za-z0-9][A-Za-z0-9_-]{0,47}$')


class Packs:
    def __init__(self, directory=None):
        self.directory = Path(directory).resolve() if directory else None
        self.loaded = {}
        self.lock = threading.RLock()

    @staticmethod
    def contained(root, relative):
        if not isinstance(relative, str):
            raise ValueError('Pack file path must be text.')
        p = (root / relative).resolve()
        if not p.is_relative_to(root.resolve()) or not p.is_file():
            raise ValueError('Pack file is missing or outside its folder.')
        return p

    def _manifest(self, pack):
        if not isinstance(pack, str) or not ID.fullmatch(pack) or self.directory is None:
            raise ValueError('Select an adventure from the configured pack library.')
        folder = (self.directory / pack).resolve()
        if not folder.is_relative_to(self.directory):
            raise ValueError('Pack folder is outside the configured library.')
        path = self.contained(folder, 'adventure.json')
        m = json.loads(path.read_text(encoding='utf-8'))
        if m.get('format') != 'mythastria-adventure/1' or m.get('id') != pack:
            raise ValueError('Unsupported adventure manifest or mismatched ID.')
        if not isinstance(m.get('encounters'), dict) or not m['encounters'] or len(m['encounters']) > 100:
            raise ValueError('Adventure needs 1-100 encounter entries.')
        for key, e in m['encounters'].items():
            if not ID.fullmatch(key) or not isinstance(e, dict):
                raise ValueError('Invalid encounter ID.')
            self.contained(folder, e.get('scenario'))
            if e.get('description'):
                self.contained(folder, e['description'])
        if m.get('lore'):                                            # GM 2026-10-24: the adventure's story (GM only)
            self.contained(folder, m['lore'])
        return folder, m

    def listing(self):
        with self.lock:
            items, errors = [], []
            for folder in sorted(self.directory.iterdir()) if self.directory and self.directory.is_dir() else []:
                if not folder.is_dir() or not ID.fullmatch(folder.name) or not (folder / 'adventure.json').is_file():
                    continue
                try:
                    _, m = self._manifest(folder.name)
                    items.append({'id': m['id'], 'name': m.get('name', m['id']), 'loaded': m['id'] in self.loaded,
                                  'version': m.get('version', '1')})
                except (OSError, ValueError, TypeError) as e:
                    errors.append({'id': folder.name, 'error': str(e)})
            return {'packs': items, 'unavailable': errors}

    def load(self, pack):
        with self.lock:
            folder, m = self._manifest(pack)
            # Validate JSON at mount; no executable content is loaded.
            for e in m['encounters'].values():
                sc = json.loads(self.contained(folder, e['scenario']).read_text(encoding='utf-8'))
                if not isinstance(sc.get('combatants'), list):
                    raise ValueError('Pack scenario needs combatants.')
                if e.get('description'):
                    json.loads(self.contained(folder, e['description']).read_text(encoding='utf-8'))
            self.loaded[pack] = (folder, copy.deepcopy(m))

    def unload(self, pack):
        with self.lock:
            if pack not in self.loaded:
                raise ValueError('Adventure is not loaded.')
            del self.loaded[pack]

    def names(self):
        with self.lock:
            return sorted('pack/%s/%s.json' % (pack, key) for pack, (_, m) in self.loaded.items() for key in m['encounters'])

    def encounters(self):
        with self.lock:
            return sorted(pack + ':' + key for pack, (_, m) in self.loaded.items() for key, e in m['encounters'].items() if e.get('description'))

    def source(self, encounter):
        with self.lock:
            if not isinstance(encounter, str) or encounter.count(':') != 1:
                raise ValueError('Choose an encounter from a loaded adventure.')
            pack, key = encounter.split(':')
            if pack not in self.loaded or not ID.fullmatch(key):
                raise ValueError('Adventure is unloaded or unknown; load it first.')
            folder, m = self.loaded[pack]
            e = m['encounters'].get(key)
            if not e:
                raise ValueError('Unknown encounter in this adventure.')
            if not e.get('description'):
                raise ValueError('This map is playable but does not yet have a Remix description.')
            desc = json.loads(self.contained(folder, e['description']).read_text(encoding='utf-8'))
            desc['scenario'] = 'pack/%s/%s.json' % (pack, key)
            sc = json.loads(self.contained(folder, e['scenario']).read_text(encoding='utf-8'))
            return desc, sc

    def plan(self, pack):
        """ADVENTURE-01 (GM 2026-10-21): a loaded adventure's places in the manifest's order (the pack has no play order
        of its own), each with its map and, where the pack describes them, its encounters. Read only."""
        with self.lock:
            if pack not in self.loaded:
                raise ValueError('Adventure is unloaded; load it first.')
            folder, m = self.loaded[pack]
            places = []
            for key, e in m['encounters'].items():
                if e.get('variant_of'):                              # GM 2026-10-25: a map's level version, not a place
                    continue
                sc = json.loads(self.contained(folder, e['scenario']).read_text(encoding='utf-8'))
                title = re.sub(r'\s*\([^)]*\)\s*$', '', str(sc.get('name') or key))
                isle, _, place = title.partition(' - ')
                fights = []
                if e.get('description'):
                    desc = json.loads(self.contained(folder, e['description']).read_text(encoding='utf-8'))
                    for x in desc.get('encounters') or []:
                        job = x.get('story_job') or {}
                        fights.append({'room': x.get('room'), 'name': x.get('name'), 'level': x.get('level'),
                                       'party_size': x.get('party_size'),
                                       'creatures': ['%s x%s' % (c.get('srd'), c.get('count')) for c in x.get('original') or []],
                                       'story': list(job.get('locked') or []) + list(job.get('open') or [])})
                places.append({'key': key, 'scenario': 'pack/%s/%s.json' % (pack, key), 'title': title,
                               'isle': isle if place else '', 'place': place or title, 'encounters': fights, 'notes': e.get('notes')})
            # GM 2026-10-24 ("use it and build on it"): a pack's lore (mythastria-lore/1) gives its story for the GM's screen
            # and its chapters' order; places it lists come in that order, each with its chapter and level.
            lore = json.loads(self.contained(folder, m['lore']).read_text(encoding='utf-8')) if m.get('lore') else None
            order = 'The order of the adventure file (the pack has no play order yet).'
            if lore and lore.get('format') == 'mythastria-lore/1':
                where = {k: (i, j, ch) for i, ch in enumerate(lore.get('chapters') or []) for j, k in enumerate(ch.get('places') or [])}
                for p in places:
                    if p['key'] in where:
                        ch = where[p['key']][2]
                        p.update(chapter=ch.get('chapter'), level=ch.get('level'))
                places.sort(key=lambda p: where.get(p['key'], (99, 99, None))[:2])
                order = "In the adventure's chapter order."
            else:
                lore = None
            return {'id': pack, 'name': m.get('name', pack), 'version': m.get('version', '1'), 'places': places,
                    'order': order, 'lore': lore}

    def folders(self):
        """GM 2026-10-25 (the map pickers' folders, tools/scenario_folders.py): {scenario name: ([adventure, 'Level n',
        place?], label, order)} for the loaded packs. A map's level is its lore chapter's level; a level version
        (variant_of) has its own; a place with floors (the entry's place) is a folder of its own."""
        out = {}
        with self.lock:
            for pack, (folder, m) in self.loaded.items():
                lore = json.loads(self.contained(folder, m['lore']).read_text(encoding='utf-8')) if m.get('lore') else {}
                where = {k: (i, j, ch.get('level')) for i, ch in enumerate(lore.get('chapters') or [])
                         for j, k in enumerate(ch.get('places') or [])}
                for n, (key, e) in enumerate(m['encounters'].items()):
                    base = e.get('variant_of') or key
                    i, j, lv = where.get(base, (99, n, None))
                    lv = e.get('level') or lv
                    try:
                        sc = json.loads(self.contained(folder, e['scenario']).read_text(encoding='utf-8'))
                    except (OSError, ValueError):
                        continue
                    label = re.sub(r'(\s*\([^)]*\))+\s*$', '', str(sc.get('name') or base)).split(' - ', 1)[-1].strip()
                    path = [m.get('name', pack), 'Level %d' % lv if isinstance(lv, int) else 'Maps']
                    if e.get('place'):
                        path.append(e['place'])
                        same = lambda s: s.lower().replace('-', ' ')
                        if same(label).startswith(same(e['place'])):
                            label = label[len(e['place']):].strip(' -:').capitalize() or label
                    if e.get('variant_of'):
                        label += ' (party level %d)' % lv
                    out['pack/%s/%s.json' % (pack, key)] = (path, label, (lv if isinstance(lv, int) else 99, i, j, key))
        return out

    def scenario(self, name):
        parts = name.split('/')
        if len(parts) != 3 or parts[0] != 'pack' or not parts[2].endswith('.json'):
            raise ValueError('Unknown pack scenario.')
        with self.lock:
            if parts[1] not in self.loaded:
                raise ValueError('Adventure is unloaded; load it first.')
            folder, m = self.loaded[parts[1]]
            e = m['encounters'].get(parts[2][:-5])
            if not e:
                raise ValueError('Unknown adventure map.')
            return json.loads(self.contained(folder, e['scenario']).read_text(encoding='utf-8'))

    def legacy_names(self):
        names = set()
        for item in self.listing()['packs']:
            _, m = self._manifest(item['id'])
            names.update(e['legacy_scenario'] for e in m['encounters'].values() if isinstance(e.get('legacy_scenario'), str))
        return names

    def aliases(self):
        with self.lock:
            return {e['legacy_scenario']: 'pack/%s/%s.json' % (pack, key)
                    for pack, (_, m) in self.loaded.items() for key, e in m['encounters'].items()
                    if isinstance(e.get('legacy_scenario'), str)}
