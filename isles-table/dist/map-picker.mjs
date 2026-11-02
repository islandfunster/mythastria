// GM 2026-10-25 ("let's organize the adventure selection. There needs to be folders and subfolders"): the map list as
// folders and subfolders (the service's scenario_tree: Adventures > Seven Isles > Level 4 > ..., Test > Labs, ...). The
// page's own <select> stays the value every other script reads; this draws one menu per folder level beside it.
const FOLDER = '▸ ';                                            // ▸ marks a folder in a menu

export function folderChildren(tree, path) {
  const folders = [], maps = [];
  for (const t of tree) {
    if (t.path.length < path.length || path.some((p, i) => t.path[i] !== p)) continue;
    if (t.path.length === path.length) maps.push(t);
    else if (!folders.includes(t.path[path.length])) folders.push(t.path[path.length]);
  }
  return { folders, maps };
}

export function mountMapPicker(select, tree) {
  if (!select || !tree?.length) return null;
  const box = document.createElement('span');
  box.className = 'map-picker';
  select.hidden = true;
  select.after(box);
  const byName = new Map(tree.map(t => [t.name, t]));
  const firstUnder = path => tree.find(t => path.every((p, i) => t.path[i] === p));
  function pick(name) {
    select.value = name;
    select.dispatchEvent(new Event('change', { bubbles: true }));
    draw();
  }
  function draw() {
    const at = byName.get(select.value);
    box.replaceChildren();
    const path = [];
    for (let d = 0; ; d++) {
      const { folders, maps } = folderChildren(tree, path);
      const menu = document.createElement('select');
      menu.setAttribute('aria-label', d ? 'Subfolder or map' : 'Folder');
      menu.disabled = select.disabled;
      menu.title = select.title || '';
      if (!at) menu.append(new Option('Choose a map…', '', true, true));
      for (const f of folders) menu.append(new Option(FOLDER + f, 'f:' + f));
      for (const m of maps) menu.append(new Option(m.label, 'm:' + m.name));
      if (at) menu.value = d < at.path.length ? 'f:' + at.path[d] : 'm:' + at.name;
      menu.addEventListener('change', () => {
        const v = menu.value;
        if (v.startsWith('m:')) pick(v.slice(2));
        else if (v) pick(firstUnder([...path.slice(0, d), v.slice(2)]).name);
      });
      box.append(menu);
      if (!at || d >= at.path.length) break;
      path.push(at.path[d]);
    }
  }
  select.addEventListener('change', draw);
  draw();
  return { refresh: draw };
}
