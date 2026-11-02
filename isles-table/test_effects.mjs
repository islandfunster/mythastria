import fs from 'node:fs';import assert from 'node:assert/strict';
import {RustEngine} from './dist/engine.mjs';import {effectBoundary,effectDescription,aimEffect,effectGraphic,presets,palettes} from './dist/effects.mjs';
const html=fs.readFileSync(new URL('./dist/training.html',import.meta.url),'utf8');assert(html.includes('href="effects.css"'));const css=['style.css','effects.css'].map(f=>fs.readFileSync(new URL('./dist/'+f,import.meta.url),'utf8')).join('\n');assert(css.startsWith('@import'));assert(css.includes('.fx-projectile'));assert(css.includes('prefers-reduced-motion'));assert(!css.includes('export const'));
const engine=await RustEngine.create(fs.readFileSync(new URL('./dist/isles_engine.wasm',import.meta.url)));
let view=engine.call({op:'new',seed:7,scene:'harbor'}),serial=0;
const call=(action,id=`effect-${serial++}`,revision=view.state.revision)=>{const r=engine.call({op:'effect',id,revision,action});if(r.ok)view=r;return r;};
const snapshot=()=>engine.call({op:'save'}).session;
const player={...presets.cloud,id:'client',origin:[4,4],angle_deg:0,source:'player',control:'movable',source_actor:null,expires_round:null};
const initial=snapshot();assert(call({kind:'create',effect:player}).ok);assert.equal(view.effects.length,1);let fx=view.effects[0];assert.equal(fx.source,'player');assert.equal(fx.radius_ft,15);
assert(call({kind:'edit',effect_id:fx.id,origin:[6,3],radius_ft:10,angle_deg:45}).ok);assert.deepEqual(view.effects[0].origin,[6,3]);assert.equal(view.effects[0].radius_ft,10);
assert.equal(view.movement,initial.movement);assert.equal(view.action_available,initial.action_available);assert.equal(snapshot().rng,initial.rng);assert.deepEqual(snapshot().actors,initial.actors);
let before=snapshot();assert(!call({kind:'edit',effect_id:fx.id,origin:[999,0]}).ok);assert.deepEqual(snapshot(),before);
const stale=view.state.revision-1;assert(!call({kind:'remove',effect_id:fx.id},'stale',stale).ok);assert.deepEqual(snapshot(),before);
const revision=view.state.revision;assert(call({kind:'trigger',preset:'npc_breath'},'once',revision).ok);const once=snapshot();assert(call({kind:'trigger',preset:'npc_breath'},'once',revision).ok);assert.deepEqual(snapshot(),once);
assert(!call({kind:'trigger',preset:'spell_cloud'},'once',revision).ok);
for(const preset of ['trap_flames','spell_cloud','spell_blast','ranged_hit','melee_hit','spell_aura'])assert(call({kind:'trigger',preset}).ok);
for(const e of view.effects.filter(e=>e.source!=='player')){before=snapshot();assert(!call({kind:'edit',effect_id:e.id,origin:[1,1]}).ok);assert(!call({kind:'remove',effect_id:e.id}).ok);assert.deepEqual(snapshot(),before);}
// An attached aura follows its source; a committed cone preserves its origin and aim.
let aura=view.effects.find(e=>e.control==='attached'),cone=view.visual_events.find(e=>e.effect.shape==='cone').effect;const conePosition=[...cone.origin],coneAngle=cone.angle_deg;
let session=snapshot();session.active=session.actors.findIndex(a=>a.id===aura.source_actor);session.movement=30;session.undo_move=null;assert(engine.call({op:'load',session}).ok);view=engine.call({op:'state'});
const route=view.movement_targets.find(t=>t.cost_ft===5);assert(route);view=engine.call({op:'command',id:'walk',revision:view.state.revision,offer_id:route.id});assert(view.ok);assert.deepEqual(view.effects.find(e=>e.id===aura.id).origin,[route.x,route.y]);assert.deepEqual(view.visual_events.find(e=>e.effect.id===cone.id).effect.origin,conePosition);assert.equal(view.visual_events.find(e=>e.effect.id===cone.id).effect.angle_deg,coneAngle);
view=engine.call({op:'command',id:'undo',revision:view.state.revision,offer_id:'undo_move'});assert(view.ok);const a=view.state.combatants.find(a=>a.id===aura.source_actor);assert.deepEqual(view.effects.find(e=>e.id===aura.id).origin,[a.x,a.y]);
const saved=snapshot();assert(engine.call({op:'load',session:saved}).ok);assert.deepEqual(snapshot(),saved);
// Expiry is round-based, not browser animation time.
session=snapshot();session.round+=3;assert(engine.call({op:'load',session}).ok);view=engine.call({op:'state'});assert(view.effects.every(e=>e.expires_round===null));
assert(call({kind:'clear_triggers'}).ok);assert(view.effects.every(e=>e.source==='player'));assert(call({kind:'remove',effect_id:fx.id}).ok);assert.equal(view.effects.length,0);
// Old saves without effects still load. Malformed effects do not replace current state.
const legacy=snapshot();delete legacy.effects;assert(engine.call({op:'load',session:legacy}).ok);
before=snapshot();const bad=structuredClone(before);bad.effects=[{...player,control:'movable',source:'npc'}];assert(!engine.call({op:'load',session:bad}).ok);assert.deepEqual(snapshot(),before);
for(const effect of [{...player,radius_ft:-5},{...player,shape:'<script>'},{...player,control:'attached',source_actor:'missing'}]){assert(!call({kind:'create',effect}).ok);assert.deepEqual(snapshot(),before);}
// Geometry uses feet / 5 exactly. Flat-ended cone width equals its length.
assert.equal(effectBoundary({...player,shape:'cone',length_ft:30}).attrs.d,'M0 0 L6 -3 L6 3 Z');assert.equal(effectBoundary({...player,radius_ft:15}).attrs.r,3);assert.equal(effectBoundary({...player,shape:'rectangle',length_ft:30,width_ft:10}).attrs.width,6);
assert.equal(effectDescription({...player,shape:'ranged',length_ft:30}),'30 ft visual trajectory');
const aimed=aimEffect({...player,shape:'cone'},{x:2.5,y:2.5},{x:2.5,y:8.5});assert.deepEqual(aimed.origin,[2,2]);assert.equal(aimed.angle_deg,90);assert.equal(aimed.length_ft,30);
// Render every material and shape with numeric geometry and non-interactive art.
const svg=(tag,attrs={},text)=>({tag,attrs,children:[],text,setAttribute(k,v){this.attrs[k]=v;},append(...children){this.children.push(...children);}});
for(const appearance of Object.keys(palettes))for(const shape of ['line','cone','circle','rectangle','ranged','melee']){const g=effectGraphic({...player,id:appearance+shape,appearance,shape},svg);assert.equal(g.attrs['pointer-events'],'none');assert(!JSON.stringify(g).includes('NaN'));}
console.log('PASS: actual WASM effect geometry, placement permissions, fixed/attached sources, expiry, save/load, stale/duplicate commands, no combat-resource changes; 78 SVG material/shape combinations.');
