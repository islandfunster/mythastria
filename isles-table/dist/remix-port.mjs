// Same-origin GM console; server-owned proposal IDs, never client-supplied statistics.
export function createRemixPort({fetch: fetchFn = globalThis.fetch} = {}) {
  let token = null;
  async function hello() {
    const r = await fetchFn('/api/hello');
    const out = await r.json();
    if (!r.ok || !out.ok) throw new Error(out.error || 'Simulator service unavailable.');
    token = out.token;
    return out;
  }
  async function post(route, request = {}, retry = true) {
    if (!token) await hello();
    const r = await fetchFn(route, {method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify({...request, token})});
    const out = await r.json();
    if (r.status === 403 && retry && /token/i.test(out.error || '')) { await hello(); return post(route, request, false); }
    if (!r.ok || !out.ok) throw new Error(out.error || `HTTP ${r.status}`);
    return out;
  }
  return {hello, catalog: () => post('/api/remix/catalog'), state: campaign => post('/api/remix/state', {campaign}),
    propose: q => post('/api/remix/propose', q), apply: q => post('/api/remix/apply', q), remove: q => post('/api/remix/remove', q),
    proof: q => post('/api/remix/proof/start', q), proofStatus: job => post('/api/remix/proof/status', {job}),
    load: pack => post('/api/adventures/load', {pack}), unload: pack => post('/api/adventures/unload', {pack}),
    traps: level => post('/api/remix/traps', {level}),          // GM 2026-10-24: SRD traps for the party's level band
    prep: q => post('/api/prep', q)};   // GM 2026-10-24: attitudes and morale (remix-prep-ui.mjs)
}
// GM 2026-10-24 ("Remix Prep suggests SRD traps by the party's level band"): one line per trap card (sim/traps.py suggest).
export function trapLines(out) {
  return (out?.traps ?? []).map(t => ({ title: `${t.name} — ${t.severity} (levels ${t.band})`,
    text: `${t.trigger}. ${t.effect[0].toUpperCase()}${t.effect.slice(1)}${numbersText(t.numbers)}. Detect: ${t.detect.join('; ')}. Make safe: ${t.disarm.join(', ')}.${t.escape ? ' ' + t.escape : ''}` }));
}
function numbersText(n) {
  if (!n) return '';
  const bits = [n.dc ? `DC ${n.dc}` : null, n.depth ? `${n.depth} ft deep` : null, n.dice ? n.dice + (n.spikes ? ` + ${n.spikes} spikes` : '') : null, n.cone ? `${n.cone}-ft Cone` : null].filter(Boolean);
  return bits.length ? ` (${bits.join(', ')})` : '';
}
export const membersOf = text => text.split(',').map(s => s.trim()).filter(Boolean);
// GM 2026-10-24 ("allow them to be selected at different levels"): "Hero 1:7" is Hero 1 at level 7; a name alone plays at
// the proposal's level. -> [{name, level|null}]
export const partyOf = text => membersOf(text).map(t => { const [name, lv] = t.split(':').map(s => s.trim()); const n = Number(lv);
  return { name, level: Number.isInteger(n) && n >= 1 && n <= 20 ? n : null }; });
export const partyText = party => party.map(p => p.level ? `${p.name}:${p.level}` : p.name).join(',');
export function proofText(proof) {
  if (!proof) return 'Not tested yet — estimate only.';
  return `${proof.qualified ? 'Sampled difficulty matched' : 'Estimate — proof did not qualify'}: ${proof.remixed.plays_as}; ${proof.remixed.drops_per_run.toFixed(2)} drops/run. GM review still applies.`;
}
// GM 2026-10-28 ("I imported a character but cannot include it in a play live remix fight"): no test characters in the
// link; Play live opens with the party to choose (saved characters, or test characters if ticked there)
export function playLink(p) {
  return './play.html?' + new URLSearchParams({scenario:p.source_scenario, campaign:p.campaign, remix:'1', level:String(p.level)});
}
