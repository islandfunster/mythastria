import fs from 'node:fs';import assert from 'node:assert/strict';import {RustEngine} from './dist/engine.mjs';import {createVisualQueue,visualGraphic} from './dist/effect-events.mjs';
const engine=await RustEngine.create(fs.readFileSync(new URL('./dist/isles_engine.wasm',import.meta.url)));
let view=engine.call({op:'new',seed:7,scene:'harbor'}),serial=0;
const save=()=>engine.call({op:'save'}).session;
const effect=action=>{const r=engine.call({op:'effect',id:`event-${serial++}`,revision:view.state.revision,action});assert(r.ok,r.error);view=r;return r;};
for(const [preset,kind] of [['npc_breath','breath'],['ranged_hit','projectile'],['melee_hit','melee'],['spell_blast','burst']]){
 const before=save();effect({kind:'trigger',preset});assert.equal(view.effects.length,0);assert.equal(view.visual_events.at(-1).kind,kind);assert.equal(view.visual_events.at(-1).effect.control,'fixed');const after=save();assert.deepEqual(after.actors,before.actors);assert.equal(after.movement,before.movement);assert.equal(after.action_available,before.action_available);assert.equal(after.rng,before.rng);
}
effect({kind:'trigger',preset:'spell_cloud'});assert.equal(view.effects.length,1);
const event=view.visual_events.at(-1);const before=save();effect({kind:'replay',event_id:event.id});const replayed=save();assert.deepEqual(replayed.actors,before.actors);assert.equal(replayed.movement,before.movement);assert.equal(replayed.action_available,before.action_available);assert.equal(replayed.rng,before.rng);assert.equal(view.visual_events.length,5);assert.deepEqual(view.visual_events.at(-1).effect,event.effect);assert.notEqual(view.visual_events.at(-1).id,event.id);
// Additional materials and explicit source/target selection stay visual-only.
const actors=view.state.combatants.filter(a=>!a.down),source=actors.find(a=>a.side==='friend'),target=actors.find(a=>a.side==='foe');
for(const [preset,kind,appearance]of [['acid_jet','breath','acid'],['thunder_burst','burst','thunder'],['healing_pulse','pulse','healing'],['transport','teleport','transport']]){
 const before=save();effect({kind:'trigger',preset,source_actor:source.id,target_actor:target.id});const v=view.visual_events.at(-1);assert.equal(v.kind,kind);assert.equal(v.effect.appearance,appearance);assert.equal(v.effect.source_actor,source.id);assert.equal(v.effect.control,'fixed');
 const after=save();assert.deepEqual(after.actors,before.actors);for(const key of ['rng','movement','action_available','diagonal_steps'])assert.equal(after[key],before[key]);
 if(kind==='teleport'){assert.deepEqual(v.effect.origin,[source.x,source.y]);assert.deepEqual(v.target_origin,[target.x,target.y]);assert.equal(v.token_id,source.token_id);const saved=save();assert(engine.call({op:'load',session:saved}).ok);assert.deepEqual(save(),saved);const bad=structuredClone(saved);bad.visual_events.at(-1).token_id='missing';assert(!engine.call({op:'load',session:bad}).ok);assert.deepEqual(save(),saved);}
}
effect({kind:'trigger',preset:'shadow_cloud',source_actor:source.id,target_actor:target.id});assert(view.effects.some(e=>e.appearance==='shadow'&&e.control==='fixed'));
for(const action of [{kind:'trigger',preset:'transport',source_actor:'missing',target_actor:target.id},{kind:'trigger',preset:'transport',source_actor:source.id,target_actor:source.id},{kind:'trigger',preset:'healing_pulse',source_actor:source.id,target_actor:'missing'}]){const before=save();const r=engine.call({op:'effect',id:'invalid-'+serial++,revision:view.state.revision,action});assert(!r.ok);assert.deepEqual(save(),before);}

// Real resolved melee emits accurate hit/miss/critical once, with no extra RNG calls.
const outcomes=new Set();
for(let seed=1;seed<=80&&outcomes.size<3;seed++){
 view=engine.call({op:'new',seed,scene:'harbor'});let s=save();const a=s.actors[s.active],target=s.actors.find(t=>t.side!==a.side);a.x=4;a.y=4;target.x=5;target.y=4;s.map.walls=[];s.rng=seed;s.undo_move=null;
 const loaded=engine.call({op:'load',session:s});assert(loaded.ok,loaded.error);view=loaded;
 const attack=view.offers.find(o=>o.kind==='attack'&&o.target===target.id);assert(attack);const revision=view.state.revision,id='real-attack-'+seed;
 view=engine.call({op:'command',id,revision,offer_id:attack.id});assert(view.ok,view.error);assert.equal(view.visual_events.length,1);const v=view.visual_events[0];outcomes.add(v.outcome);assert.equal(v.effect.source_actor,a.id);assert.deepEqual(v.effect.origin,[target.x,target.y]);
 const result=engine.call({op:'export'}).messages.filter(m=>m.type==='result').at(-1);assert.equal(result.visual_events[0].id,v.id);const text=result.log[0].text;assert(text.includes(v.outcome==='critical'?'critical hit':v.outcome==='miss'?'miss.':'→ hit.'));
 const hp=view.state.combatants.find(t=>t.id===target.id).hp;assert(v.outcome==='miss'?hp===target.hp:hp<target.hp);
 const completed=save();const duplicate=engine.call({op:'command',id,revision,offer_id:attack.id});assert(duplicate.ok);assert.deepEqual(save(),completed);assert.equal(duplicate.visual_events.length,1);
 const rngAfter=completed.rng;effect({kind:'replay',event_id:v.id});assert.equal(save().rng,rngAfter);assert.equal(view.state.combatants.find(t=>t.id===target.id).hp,hp);assert.equal(view.action_available,false);
}
assert.deepEqual([...outcomes].sort(),['critical','hit','miss']);
// Recent events are bounded and old saves load without them.
for(let i=0;i<30;i++)effect({kind:'trigger',preset:'melee_hit'});assert.equal(view.visual_events.length,24);assert(engine.call({op:'load',session:save()}).ok);
let legacy=save();delete legacy.visual_events;assert(engine.call({op:'load',session:legacy}).ok);assert.equal(engine.call({op:'state'}).visual_events.length,0);
// Virtual clock checks one-shot expiry, deduplication, bounded concurrency and silent load.
let clock=0,tid=0,changes=0;const timers=new Map();const queue=createVisualQueue({now:()=>clock,schedule:(fn,ms)=>{const id=++tid;timers.set(id,{fn,at:clock+ms});return id;},unschedule:id=>timers.delete(id),onChange:()=>changes++});
const sample={...event,id:'initial'};queue.ingest([sample]);assert.equal(queue.entries().length,0);
const fresh={...sample,id:'fresh'};queue.ingest([sample,fresh]);assert.equal(queue.entries().length,1);const timersBefore=timers.size;queue.ingest([sample,fresh]);assert.equal(timers.size,timersBefore);
clock=500;assert.equal(queue.entries()[0].elapsed,500);clock=fresh.duration_ms;for(const [id,t]of [...timers])if(t.at<=clock){timers.delete(id);t.fn();}assert.equal(queue.entries().length,0);assert(changes>0);
queue.ingest([{...sample,id:'loaded'}],{silent:true});assert.equal(queue.entries().length,0);
queue.ingest(Array.from({length:12},(_,i)=>({...sample,id:'many-'+i})));assert.equal(queue.entries().length,8);queue.ingest([]);assert.equal(queue.entries().length,0);assert.equal(timers.size,0);
const svg=(tag,attrs={},text)=>({tag,attrs,text,children:[],setAttribute(k,v){this.attrs[k]=v;},append(...items){this.children.push(...items);}});
for(const kind of ['projectile','melee','burst','breath','pulse'])for(const outcome of ['hit','miss','critical','demo']){const g=visualGraphic({...sample,kind,outcome},svg,{elapsed:400});assert.equal(g.attrs['pointer-events'],'none');assert(g.attrs.style.includes('-0.4s'));assert(!JSON.stringify(g).includes('NaN'));}
const transporter={...sample,kind:'teleport',effect:{...sample.effect,appearance:'transport',origin:[4,4],angle_deg:0,length_ft:10},target_origin:[8,6],token_id:source.token_id};
const graphic=visualGraphic(transporter,svg,{resolveToken:()=>({path:'tokens/'+source.token_id+'.png'})});const serialized=JSON.stringify(graphic);assert(serialized.includes('mask-type:alpha'));assert(serialized.includes('vfx-transport-in'));assert(serialized.includes('tokens/'));assert(serialized.includes('translate(4 2)'));assert(!serialized.includes('NaN'));
console.log('PASS: actual WASM one-shot triggers and real melee hit/miss/critical, idempotency, damage-free replay, bounded/save-compatible event log; virtual-clock expiry/dedupe/silent load and 20 SVG outcome/kind pairs, selected-actor acid/thunder/healing/transport triggers, shadow zones, rejected invalid actors and alpha-masked transporter artwork.');
