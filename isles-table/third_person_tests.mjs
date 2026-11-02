// Browser versions of test_third_person.mjs (Node is not installed on the GM's PC) plus the 2026-10-19 additions:
// follow-behind yaw, remappable keys, 3D effect volumes, standees for characters without art, terrain tint, the
// orbit/zoom/pick API. GL calls are mocked here; the real GPU view is checked in the browser by eye.
import { multiply, perspective, lookAt, invert, transform, screenRay, groundHit, cameraPose, pickActor, wallFraction, behindYaw, ceilingAt, elevation } from './dist/scene-math.mjs';
import { createThirdPerson, sceneMesh, effectMesh, ZONE_TINT, wallTop } from './dist/third-person.mjs';
import { ACTIONS, DEFAULT_KEYS, comboOf, actionFor, rebind, clearKeys, loadKeymap, saveKeymap, label } from './dist/camera-keys.mjs';
import { WORLD, tileTone } from './dist/world-style.mjs';

// vertex layout: x, y, z, u, v, r, g, b, a
const vertices = m => { const out = []; for (let i = 0; i < m.length; i += 9) out.push({ y: m[i + 1], c: [m[i + 5], m[i + 6], m[i + 7]] }); return out; };
const near = (a, b, e = .002) => a.every((v, i) => Math.abs(v - b[i]) < e);

function assert(cond, text) { if (!cond) throw new Error('FAILED: ' + text); }
const finite = m => [...m].every(Number.isFinite);

function mockGL() {
  const calls = [], constants = {};
  let constant = 1;
  const gl = new Proxy({ getShaderParameter: () => true, getProgramParameter: () => true, getAttribLocation: (p, k) => ({ aPosition: 0, aUV: 1, aColor: 2 }[k]),
    getUniformLocation: (p, k) => k, drawArrays: (...a) => calls.push(a), createShader: () => ({}), createProgram: () => ({}), createBuffer: () => ({}),
    createTexture: () => ({}), isContextLost: () => false, bufferData: (t, data) => calls.push(['data', data.length]) }, {
    get(o, k) { if (k in o) return o[k]; if (/^[A-Z_0-9]+$/.test(String(k))) return constants[k] ?? (constants[k] = constant++); return () => {}; } });
  const handlers = {};
  const canvas = { width: 0, height: 0, getContext: () => gl, getBoundingClientRect: () => ({ left: 0, top: 0, width: 600, height: 400 }),
    addEventListener() {}, focus() {}, setPointerCapture() {}, hasPointerCapture: () => false, releasePointerCapture() {} };
  return { gl, canvas, calls, handlers };
}

export function run() {
  const results = [];
  const test = (name, fn) => { try { fn(); results.push([name, true, '']); } catch (e) { results.push([name, false, e.message]); } };
  const actor = { id: 'a', x: 4, y: 4, space_ft: 5, side: 'friend' };

  test('3d: camera matrices invert and a floor point unprojects to itself (from test_third_person)', () => {
    const pose = cameraPose(actor, 0, .4, 7, []), vp = multiply(perspective(Math.PI / 3, 1.5), lookAt(pose.eye, pose.target)), id = multiply(vp, invert(vp));
    for (let i = 0; i < 16; i++) assert(Math.abs(id[i] - (i % 5 === 0 ? 1 : 0)) < 1e-4, 'identity');
    const p = transform(vp, [5, 0, 5]), g = groundHit(screenRay(vp, p[0], p[1]));
    assert(Math.hypot(g[0] - 5, g[2] - 5) < 1e-3, 'unproject');
    const wall = { id: 'w', points: [[3, 5], [5, 5]], open: false, door: false };
    assert(pickActor({ origin: [4, .7, 10], direction: [0, 0, -1] }, [actor], 0, [])?.id === 'a', 'pick');
    assert(pickActor({ origin: [4, .7, 10], direction: [0, 0, -1] }, [actor], 0, [wall]) === null, 'a wall hides it');
    assert(wallFraction([4, 1, 10], [4, 1, 4], { ...wall, open: true }) === null, 'open door');
    const walled = cameraPose(actor, 0, .12, 7, [wall]);              // 2026-10-19: it rises over the wall instead of stopping
    assert(walled.eye[2] < 5 || wallFraction(walled.target, walled.eye, wall, 2.05) === null, 'never behind a wall that blocks the view');
  });

  test('3d: a ray from the real camera picks the figure under the pointer, not the last one in the list', () => {
    // 2026-10-19 (GM: "can't move characters"): screenRay returned 4-number vectors (the w left over from the
    // projection); in pickActor that made every comparison NaN, so the LAST combatant was always picked and a drag on
    // your own figure orbited the camera instead of moving it. The old tests built 3-number rays by hand.
    const me = { id: 'me', x: 12, y: 13, space_ft: 5, side: 'friend' }, far = { id: 'far', x: 9.5, y: 4.5, space_ft: 10, side: 'foe' };
    const yaw = behindYaw(me, [me, far]), pose = cameraPose(me, yaw, .64, 11.9, []);
    const vp = multiply(perspective(Math.PI / 3, 864 / 560, .08, 100), lookAt(pose.eye, pose.target));
    const ray = screenRay(vp, 0, 0);
    assert(ray.origin.length === 3 && ray.direction.length === 3, 'a 3D ray: ' + ray.direction.length + ' numbers');
    const at = transform(vp, [me.x, .7, me.y]);
    assert(pickActor(screenRay(vp, at[0], at[1]), [me, far], yaw, [])?.id === 'me', 'the figure under the pointer');
    assert(pickActor(screenRay(vp, .95, .95), [me, far], yaw, []) === null, 'empty sky: nobody');
  });

  test('3d: a wall right behind the character lifts the camera over it instead of pushing it into the party', () => {
    // 2026-10-19 (found in the browser): the party starts against the harbour lane's south wall; the camera behind
    // Hero 3 was pushed to just behind the figures and they filled the view.
    const me = { id: 'a', x: 4, y: 4, space_ft: 5 }, wall = { id: 'w', points: [[0, 5.5], [9, 5.5]], open: false, door: false };
    const pose = cameraPose(me, 0, .42, 9, [wall]);
    const back = Math.hypot(pose.eye[0] - pose.target[0], pose.eye[2] - pose.target[2]), up = pose.eye[1] - pose.target[1];
    assert(Math.hypot(back, up) > 6, 'the camera keeps its distance: ' + Math.hypot(back, up).toFixed(2));
    assert(pose.eye[1] > 2.05, 'above the wall top');
    const open = cameraPose(me, 0, .42, 9, []);
    assert(Math.abs(open.eye[1] - (open.target[1] + Math.sin(.42) * 9)) < 1e-9, 'no wall: the pitch the player chose');
  });

  test('3d: follow-behind puts the camera on the far side from the nearest foe', () => {
    const foe = { id: 'f', x: 4, y: 1, space_ft: 5, side: 'foe' }, far = { id: 'g', x: 12, y: 4, side: 'foe' };
    const yaw = behindYaw(actor, [actor, foe, far]);
    const eye = cameraPose(actor, yaw, .42, 7, []).eye;
    assert(eye[2] > actor.y + 2, 'the camera is south of the character, the foe north: ' + eye.map(v => v.toFixed(1)));
    assert(Math.abs(eye[0] - actor.x) < .01, 'straight behind');
    assert(behindYaw(actor, [actor, { ...foe, down: true }, { id: 'b', x: 1, y: 1, side: 'friend' }]) === null, 'no living foe: no turn');
  });

  test('3d: effects are volumes (dome, cone solid, beam, slab) with finite vertices, still for every shape', () => {
    const base = { appearance: 'fire', origin: [2, 3], angle_deg: 90, length_ft: 30, width_ft: 5, radius_ft: 20 };
    for (const shape of ['line', 'cone', 'circle', 'rectangle', 'ranged', 'melee']) {
      const m = effectMesh({ ...base, shape }, 1);
      assert(m.length > 0 && m.length % 27 === 0 && finite(m), shape);
      let top = 0;
      for (let i = 1; i < m.length; i += 9) top = Math.max(top, m[i]);
      const want = { circle: 3.9, cone: 1.5, line: .9, rectangle: .85, ranged: .95, melee: .85 }[shape];
      assert(top >= want, `${shape} rises to ${top.toFixed(2)} (want ${want})`);
      for (let i = 1; i < m.length; i += 9) assert(m[i] >= 0, `${shape}: nothing below the floor`);
    }
  });

  test('3d: terrain zones are tinted on the floor', () => {
    const map = { cols: 4, rows: 4, square_ft: 5, walls: [], zones: [{ id: 'z', kind: 'water', rect: [0, 0, 1, 1] }, { id: 'q', kind: 'unknown', rect: [2, 2, 2, 2] }] };
    const plain = sceneMesh({ ...map, zones: [] }), tinted = sceneMesh(map);
    assert(tinted.length - plain.length === 54 * 5, 'the water: a fill and an ink outline (4 sides); none for an unknown kind');
    assert(ZONE_TINT.water && finite(tinted), 'tint');
  });

  // GM 2026-10-19: art style 1, the tokens' cartoon look in softer colours
  test('3d style: flagstone floor, each square a tile on dark seams, the grid shown by the seams', () => {
    const map = { cols: 3, rows: 2, square_ft: 5, walls: [], zones: [] };
    const v = vertices(sceneMesh(map)), off = vertices(sceneMesh(map, { grid: false }));
    // 2026-10-20 (GM: the grid lines were "distracting"): with the grid on, the seams are a soft ink, between ink and mortar
    const soft = WORLD.ink.map((c, i) => c * .4 + WORLD.mortar[i] * .6);
    assert(v.some(p => near(p.c, soft)) && !v.some(p => near(p.c, WORLD.ink)), 'soft ink seams with the grid on, never full ink');
    assert(!off.some(p => near(p.c, WORLD.ink)) && off.some(p => near(p.c, WORLD.mortar)), 'grid off: softer mortar seams, no ink');
    for (const [x, y] of [[0, 0], [2, 1]]) assert(v.some(p => near(p.c, tileTone(x, y), .03)), `tile ${x},${y} in its tone`);
    assert(new Set(v.map(p => p.c.map(c => c.toFixed(3)).join())).size > 4, 'more than one tone: tiles vary');
    assert(v.every(p => p.y >= 0 && p.y < .05), 'all flat on the floor');
  });

  test('3d style: walls are outlined in ink with a lighter cap; doors are planks', () => {
    const base = { cols: 6, rows: 6, square_ft: 5, zones: [], ceilings: [] };
    const empty = vertices(sceneMesh({ ...base, walls: [] })).length;
    const wall = vertices(sceneMesh({ ...base, walls: [{ id: 'w', points: [[.5, 0], [.5, 5]] }] })).slice(empty);
    assert(wall.some(p => near(p.c, WORLD.ink) && p.y > 1.5), 'ink along the top edge');
    assert(wall.some(p => near(p.c, WORLD.ink) && p.y < .05), 'ink along the foot');
    assert(wall.some(p => near(p.c, WORLD.wallCap, .05) && p.y > 1.8), 'a lighter cap');
    const door = vertices(sceneMesh({ ...base, walls: [{ id: 'd', door: true, points: [[.5, 0], [.5, 1]] }] })).slice(empty);
    assert(door.some(p => near(p.c, WORLD.doorDark, .05)) && door.some(p => near(p.c, WORLD.door, .08)), 'plank colours (shaded by face)');
  });

  test('3d style: the background is the soft dusk, not near-black', () => {
    const { gl, canvas } = mockGL(), cleared = [];
    gl.clearColor = (...c) => cleared.push(c);
    const view = createThirdPerson({ canvas, getView: () => null, getSelected: () => null, getToken: () => null, getEvents: () => [],
      onSelect() {}, onMove() {}, status() {}, onFailure() {} });
    view.enable();
    assert(cleared.length > 0 && cleared.every(c => near(c.slice(0, 3), WORLD.sky)), 'clear colour is WORLD.sky');
  });

  test('3d: ceilings: found by square, walls rise to the higher ceiling beside them, open sky keeps the plain height', () => {
    const map = { cols: 10, rows: 10, square_ft: 5, zones: [], walls: [],
      ceilings: [{ room: 'hall', rect: [0, 0, 4, 9], ft: 30, description: 'A 30-ft hall.' },
        { room: 'yard', rect: [5, 0, 9, 9], ft: null, description: 'Open sky.' }] };
    assert(ceilingAt(map, 2, 3).room === 'hall' && ceilingAt(map, 7, 3).room === 'yard' && ceilingAt(map, 20, 3) === null, 'by square');
    assert(Math.abs(wallTop(map, { points: [[4.5, 0], [4.5, 9]] }) - 6) < 1e-9, 'between hall and yard: the 30-ft hall');
    assert(wallTop(map, { points: [[7.5, 0], [7.5, 9]] }) === 1.85, 'open sky on both sides: as before');
    assert(wallTop({ ...map, ceilings: [] }, { points: [[4.5, 0], [4.5, 9]] }) === 1.85, 'no ceilings: as before');
    const tall = sceneMesh(map), plain = sceneMesh({ ...map, walls: [{ id: 'w', points: [[4.5, 0], [4.5, 9]] }], ceilings: [] }),
      raised = sceneMesh({ ...map, walls: [{ id: 'w', points: [[4.5, 0], [4.5, 9]] }] });
    assert(raised.length > plain.length && finite(raised) && finite(tall), 'the raised part is drawn');
  });

  test('3d: fliers are drawn raised (aloft 10 ft, hovering 3 ft), never through the ceiling, and can still be picked', () => {
    const map = { ceilings: [{ room: 'tube', rect: [0, 0, 3, 3], ft: 10, description: 'A 10-ft tube.' }] };
    const g = { id: 'g', x: 6, y: 6, space_ft: 5, side: 'foe' };
    assert(elevation({ ...g, flying: true, aloft: true }, map) === 2, 'aloft in the open: 10 ft');
    assert(elevation({ ...g, flying: true }, map) === .6, 'able to fly: a hover');
    assert(elevation({ ...g, flying: true, down: true }, map) === 0 && elevation(g, map) === 0, 'down or no fly: on the floor');
    const low = elevation({ ...g, x: 1, y: 1, flying: true, aloft: true }, map);
    assert(low >= 0 && low + 1.4 <= 2 + 1e-9, 'under a 10-ft ceiling the figure stays below it: ' + low);
    const raised = { ...g, x: 4, y: 4, elev: 2 };
    assert(pickActor({ origin: [4, 2.7, 10], direction: [0, 0, -1] }, [raised], 0, [])?.id === 'g', 'picked in the air');
    assert(pickActor({ origin: [4, .5, 10], direction: [0, 0, -1] }, [raised], 0, []) === null, 'not under it');
    assert(cameraPose(raised, 0, .4, 7, []).target[1] > 2, 'the camera follows a raised figure up');
  });

  test('keys: defaults, combinations, rebinding moves a key away from its old action', () => {
    assert(actionFor(DEFAULT_KEYS, 'q') === 'rotate_left' && actionFor(DEFAULT_KEYS, 'shift+enter') === 'end_turn', 'defaults');
    assert(comboOf({ key: 'Q', shiftKey: false }) === 'q' && comboOf({ key: 'Enter', shiftKey: true }) === 'shift+enter', 'combos');
    assert(comboOf({ key: '+', shiftKey: true }) === '+' && comboOf({ key: 'Shift', shiftKey: true }) === null, 'shifted symbol; bare modifier');
    assert(comboOf({ key: ' ' }) === 'space', 'space');
    const { keymap, displaced } = rebind(DEFAULT_KEYS, 'recenter', 'q');
    assert(displaced === 'rotate_left' && keymap.recenter[0] === 'q' && !keymap.rotate_left.includes('q'), 'moved');
    assert(keymap.rotate_left.includes('arrowleft'), 'the other key stays');
    assert(rebind(keymap, 'recenter', 'x').keymap.recenter.length === 2, 'at most two keys');
    assert(clearKeys(keymap, 'end_turn').end_turn.length === 0, 'clear');
    assert(rebind(DEFAULT_KEYS, 'fly', 'z').keymap === DEFAULT_KEYS, 'unknown action ignored');
    assert(label('shift+enter') === 'Shift + Enter' && label('arrowleft') === '←', 'labels');
    assert(Object.keys(ACTIONS).every(a => Array.isArray(DEFAULT_KEYS[a])), 'every action has a default list');
  });

  test('keys: saved per browser; a broken or blocked store gives the defaults', () => {
    const store = new Map(), storage = { getItem: k => store.get(k) ?? null, setItem: (k, v) => store.set(k, v) };
    const { keymap } = rebind(DEFAULT_KEYS, 'recenter', 'b');
    assert(saveKeymap(keymap, storage) && loadKeymap(storage).recenter[0] === 'b', 'round trip');
    store.set('isles-camera-keys', '{bad json');
    assert(loadKeymap(storage).recenter[0] === 'c', 'broken: defaults');
    assert(loadKeymap({ getItem() { throw new Error('blocked'); } }).rotate_left[0] === 'q', 'blocked: defaults');
    assert(saveKeymap(keymap, { setItem() { throw new Error('blocked'); } }) === false, 'blocked save says so');
  });

  test('3d: the renderer draws standees for characters without art, orbits, zooms and picks (GL mocked)', () => {
    const { canvas, calls } = mockGL();
    const frames = new Map(); let next = 0;
    const raf = globalThis.requestAnimationFrame, caf = globalThis.cancelAnimationFrame;
    globalThis.requestAnimationFrame = fn => { frames.set(++next, fn); return next; };
    globalThis.cancelAnimationFrame = id => frames.delete(id);
    try {
      const view = { map: { cols: 8, rows: 8, square_ft: 5, walls: [], zones: [] }, movement_targets: [],
        state: { active: 'pc', combatants: [{ id: 'pc', name: 'Hero 1', x: 2, y: 2, space_ft: 5, side: 'friend', token_id: null, hp: 9, hp_max: 9 },
          { id: 'g', name: 'Goblin', x: 2, y: 5, space_ft: 5, side: 'foe', token_id: null, hp: 7, hp_max: 7 }] } };
      let ground = null;
      const tp = createThirdPerson({ canvas, getView: () => view, getSelected: () => 'pc', getToken: () => null, getEvents: () => [],
        onSelect() {}, onMove() {}, onGround: (x, y) => { ground = [x, y]; }, status: { textContent: '' }, onFailure: m => { throw new Error(m); },
        followBehind: () => true, ringFor: a => a.id === 'g' ? [.5, .9, .5, 1] : null });
      assert(tp.enable(), 'enable');
      for (let k = 0; k < 3; k++) { const [id, f] = frames.entries().next().value; frames.delete(id); f(1000 + k * 100); }
      const standees = calls.filter(c => c[0] === 'data' && c[1] === 2 * 6 * 9).length;
      assert(standees >= 2, 'two standee panels drawn (got ' + standees + ')');
      assert(tp.following, 'following');
      tp.orbit(.3, 0);
      assert(!tp.following, 'orbiting stops the auto-follow');
      tp.recenter(); assert(tp.following, 'recenter');
      tp.zoomBy(100); tp.zoomBy(.0001);
      const [id, f] = frames.entries().next().value; frames.delete(id); f(2000);
      const picked = tp.pick(300, 200);
      assert(picked === null || picked === 'pc' || picked === 'g', 'pick returns an actor id or null');
      tp.disable();
      assert(frames.size === 0 && ground === null, 'disabled; no stray move');
    } finally { globalThis.requestAnimationFrame = raf; globalThis.cancelAnimationFrame = caf; }
  });
  return results;
}
