import {createRemixPort, playLink, trapLines} from './remix-port.mjs';

export function mountRemix(doc = document, port = createRemixPort(), timers = globalThis) {
  const $ = id => doc.getElementById(id);
  const el = (tag, text) => { const e = doc.createElement(tag); if (text !== undefined) e.textContent = text; return e; };
  const channel = typeof BroadcastChannel === 'function' ? new BroadcastChannel('mythastria-content') : null;
  let catalog = [], proposal = null, campaign = null, generation = 0, poll = null, busy = false;
  const status = (text, error = false) => { $('remix-status').textContent = text; $('remix-status').className = error ? 'error' : ''; };
  const stopPoll = () => { if (poll !== null) timers.clearTimeout(poll); poll = null; };
  function invalidate() { generation++; proposal = null; stopPoll(); $('proposal-panel').hidden = true; }
  async function run(fn) {
    if (busy) return;
    busy = true;
    const buttons = [...doc.querySelectorAll('button')]; buttons.forEach(b => b.disabled = true);
    try { await fn(); } catch(e) { status(e.message, true); }
    finally { busy = false; buttons.forEach(b => b.disabled = false); }
  }
  function drawProposal() {
    if (!proposal) return;
    $('proposal-panel').hidden = false;
    $('summary').textContent = `Level ${proposal.level} · ${proposal.party_size} characters · target ${proposal.target} · ${proposal.estimate.xp} XP (prefilter only)`;
    $('groups').replaceChildren(...proposal.groups.map(g => { const tr = el('tr'); tr.append(...[g.from,g.to,String(g.count),g.measurement ? `Arena proxy: ${g.measurement.plays_as}`:`Not measured at level ${proposal.level} yet (XP estimate)`].map(v => el('td',v))); return tr; }));
    $('locked').replaceChildren(...[...proposal.story_job.locked,...proposal.must_keep].map(s => el('li',s)));
    $('warnings').replaceChildren(...proposal.warnings.map(s => el('li',s)));
    $('routes').replaceChildren(...proposal.routes.map(r => { const e = el('div'); e.append(el('h3',r.approach),el('p',r.when || r.condition || 'GM review'),el('p','Success: '+r.success),el('p','Failure: '+r.failure),el('p','Story: '+r.canon)); if(r.clue_elsewhere)e.append(el('p','Clues: '+r.clue_elsewhere)); return e; }));
  }
  async function readCampaign(guard = generation) {
    const out = await port.state($('campaign').value.trim());
    if (guard !== generation) return;
    campaign = out.campaign;
    $('saved').replaceChildren();
    if (!campaign.active.length) $('saved').append(el('p','No saved remixes in this campaign.'));
    for (const p of campaign.active) {
      const item = el('div'); item.className = 'saved-item';
      item.append(el('p',`${p.source_scenario} · seed ${p.seed} · ${p.proof?.qualified ? 'sampled' : 'estimate'}`));
      const a = el('a','Play this encounter'); a.href = playLink(p); item.append(a);
      const remove = el('button','Restore original'); remove.addEventListener('click',() => run(async () => {
        const out = await port.remove({campaign:campaign.id,revision:campaign.revision,scenario:p.source_scenario});
        status(out.message); await readCampaign();
      })); item.append(remove); $('saved').append(item);
    }
  }
  async function refreshCatalog() {
    const out = await port.catalog(); catalog = out.encounters;
    $('packs').replaceChildren(...out.packs.map(p => {
      const row = el('div'); row.className = 'pack-item'; row.append(el('span',`${p.name} · ${p.loaded ? 'loaded' : 'unloaded'} `));
      const b = el('button',p.loaded ? 'Unload':'Load'); b.addEventListener('click',() => run(async () => {
        await port[p.loaded ? 'unload':'load'](p.id); invalidate(); channel?.postMessage({type:'packs-changed'});
        await refreshCatalog(); await readCampaign(); status(p.loaded ? 'Adventure unloaded. Saved campaign choices remain.' : 'Adventure loaded.');
      })); row.append(b); return row;
    }));
    if (!out.packs.length) $('packs').append(el('p','No pack library configured. Start the service with --adventure-packs pointing to your external adventure folder.'));
    for(const x of out.unavailable) $('packs').append(el('p',`${x.id}: ${x.error}`));
    const selected = $('encounter').value;
    $('encounter').replaceChildren(...catalog.map(c => {const o=el('option',c.name);o.value=c.id;return o;}));
    if (catalog.some(c => c.id === selected)) $('encounter').value = selected;
    // GM 2026-10-25 ("The remix must only allow the chosen encounter in the Adventure loaded"): opened for one encounter
    // (remix.html?encounter=<its map or id>), the Remix works on that encounter only.
    const asked = new URLSearchParams(location.search).get('encounter');
    const chosen = asked && catalog.find(c => c.id === asked || c.scenario === asked || c.id.endsWith('/' + asked));
    if (chosen) { $('encounter').value = chosen.id; $('encounter').disabled = true; $('encounter').title = 'Chosen on Play an adventure: the Remix works on this encounter only.'; }
    else if (asked) status(`The chosen encounter (${asked}) is not in a loaded adventure: load it first.`);
    defaults();
  }
  function defaults() {
    const c = catalog.find(c => c.id === $('encounter').value);
    if (c) { $('level').value=String(c.level);$('tone').value=c.tone; }
    drawTraps();
  }
  async function drawTraps() {                                       // GM 2026-10-24: SRD traps for the level band
    const box = $('trap-suggest');
    if (!box) return;
    const out = await port.traps(Number($('level').value) || 1).catch(() => null);
    if (!out) { box.replaceChildren(el('p','The trap list is not available from this service.')); return; }
    box.replaceChildren(el('p', out.note), ...trapLines(out).map(t => { const d = el('details'); d.append(el('summary', t.title), el('p', t.text)); return d; }),
      el('p', 'Place one in Play live: GM tools → Traps, then click a square. An adventure pack can list them on its map.'));
  }
  async function propose() {
    invalidate(); const guard = generation;
    if (!$('encounter').value) throw new Error('Load an adventure and select a described encounter first.');
    const out = await port.propose({campaign:$('campaign').value.trim(),encounter:$('encounter').value,level:Number($('level').value),seed:Number($('seed').value),
      difficulty:$('difficulty').value,tone:$('tone').value,freshness:$('freshness').checked});
    if (guard !== generation) return;
    proposal=out.proposal;campaign=out.campaign;$('read-aloud').value=proposal.read_aloud;
    $('reviewed').checked=false;$('allow-estimate').checked=false;drawProposal();status('Proposal ready. Review it before saving.');await readCampaign(guard);
  }
  $('proposal-form').addEventListener('submit',e=>{e.preventDefault();run(propose);});
  $('again').addEventListener('click',()=>run(async()=>{$('seed').value=String((Number($('seed').value)+1)%2147483648);await propose();}));
  for (const id of ['campaign','encounter','level','seed','difficulty','tone','freshness']) $(id).addEventListener('change',()=>{invalidate();if(id==='encounter')defaults();if(id==='level')drawTraps();if(id==='campaign')run(()=>readCampaign());});
  $('refresh').addEventListener('click',()=>run(async()=>{invalidate();await refreshCatalog();await readCampaign();status('Refreshed.');}));
  $('apply').addEventListener('click',()=>run(async()=>{
    if(!proposal || !campaign) throw new Error('Generate a proposal first.');
    const out=await port.apply({campaign:campaign.id,revision:campaign.revision,proposal:proposal.id,reviewed:$('reviewed').checked,allow_estimate:$('allow-estimate').checked,read_aloud:$('read-aloud').value});
    status(out.message);await readCampaign();
  }));
  // GM 2026-10-28 ("I only want to use characters saved in the saved characters tab"; Remix's paired proof fought only
  // with test characters: "Remove the proof"): Check the encounters on Play an adventure judges winnability instead.
  const ready=run(async()=>{await port.hello();await refreshCatalog();await readCampaign();status('Ready. Load an adventure to begin.');});
  return {ready,dispose(){invalidate();channel?.close();}};
}
if(typeof document!=='undefined')mountRemix();
