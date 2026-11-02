import fs from 'node:fs';import assert from 'node:assert/strict';import {RustEngine} from './dist/engine.mjs';
class Element{set textContent(v){this._text=String(v);}get textContent(){return this._text??'';}constructor(tag='div'){this.tagName=tag.toUpperCase();this.children=[];this.style={};this.attributes={};this.dataset={};this.value='';this.checked=true;this.hidden=false;this.captures=new Set();this.classList={toggle(){}};}append(...items){this.children.push(...items);}replaceChildren(...items){this.children=items;}setAttribute(k,v){this.attributes[k]=v;}removeAttribute(k){delete this.attributes[k];}cloneNode(){const n=new Element(this.tagName);n.attributes={...this.attributes};return n;}remove(){}contains(node){return node===this||this.children.some(c=>c?.contains?.(node));}focus(){this.focused=true;}setPointerCapture(id){this.captures.add(id);}hasPointerCapture(id){return this.captures.has(id);}releasePointerCapture(id){this.captures.delete(id);}getScreenCTM(){return {inverse:()=>({})};}createSVGPoint(){return {x:0,y:0,matrixTransform(){return {x:(this.x-100)/20,y:(this.y-40)/20};}};}click(){this.onclick?.({target:this});}showModal(){this.open=true;}close(){this.open=false;}}
const nodes={},html=fs.readFileSync(new URL('./dist/training.html',import.meta.url),'utf8');for(const m of html.matchAll(/id="([^"]+)"/g)){nodes[m[1]]=new Element();nodes[m[1]].id=m[1];}nodes.scene.value='harbor';nodes.size.value='all';
const body=new Element('body'),store=new Map(),listeners={};globalThis.window={addEventListener:(name,fn)=>listeners['window:'+name]=fn};globalThis.localStorage={getItem:k=>store.get(k)??null,setItem:(k,v)=>store.set(k,v)};globalThis.getComputedStyle=()=>({getPropertyValue:()=> '#aa9977'});globalThis.document={querySelector:()=>null,body,head:new Element('head'),createElement:t=>new Element(t),createElementNS:(ns,t)=>new Element(t),getElementById:id=>{assert(nodes[id],id);return nodes[id];},addEventListener:(name,fn)=>listeners[name]=fn};globalThis.fetch=async()=>({ok:true,arrayBuffer:async()=>{const b=fs.readFileSync(new URL('./dist/isles_engine.wasm',import.meta.url));return b.buffer.slice(b.byteOffset,b.byteOffset+b.byteLength);}});
await import('./dist/app.mjs');assert.equal(nodes.initiative.children.length,4);assert.equal(nodes['token-count'].textContent,'306');assert.equal(nodes.error.hidden,true);assert(nodes.map.children.some(x=>x.attributes['data-actor']));assert(!nodes.actions.children.some(x=>x.textContent.startsWith('Move ')));
const before=nodes['active-name'].textContent;nodes.end.click();assert.notEqual(nodes['active-name'].textContent,before);
nodes.library.click();assert(nodes.collection.open);assert.equal(nodes['token-grid'].children.length,306);nodes.search.value='dragon';nodes.search.oninput();assert(nodes['token-grid'].children.length>10);assert(nodes['token-grid'].children.length<306);nodes['close-library'].click();assert(!nodes.collection.open);
const mapBefore=nodes.map.children.length;nodes.skin.onchange({target:{value:'parchment'}});assert.equal(body.dataset.skin,'parchment');assert.equal(nodes.map.children.length,mapBefore);
nodes.scene.value='temple';nodes.new.click();assert.equal(nodes['scene-title'].textContent,'The Watch Hall');assert.equal(nodes.initiative.children.length,4);nodes.suggest.click();assert.equal(nodes.suggestion.hidden,false);nodes.suggestion.children[1].click();assert.equal(nodes.suggestion.hidden,true);nodes.about.click();assert(nodes.information.open);nodes['close-about'].click();assert(!nodes.information.open);

const bytes=fs.readFileSync(new URL('./dist/isles_engine.wasm',import.meta.url));const mirror=await RustEngine.create(bytes);
let session=JSON.parse(store.get('isles-table-session-v1')).session;let probe=mirror.call({op:'load',session});let current=probe.state.combatants.find(c=>c.id===probe.state.active);
const destination=probe.movement_targets.find(t=>t.cost_ft>=15);assert(destination);
const token=nodes.map.children.find(x=>x.attributes['data-actor']===current.id);
const event=(x,y,id=1)=>({pointerId:id,button:0,isPrimary:true,clientX:(x+.75)*20+100,clientY:(y+.75)*20+40,preventDefault(){}});
token.onpointerdown(event(current.x,current.y));assert(nodes.map.hasPointerCapture(1));
nodes.map.onpointermove(event(destination.x,destination.y));nodes.map.onpointerup(event(destination.x,destination.y));assert(!nodes.map.hasPointerCapture(1));
session=JSON.parse(store.get('isles-table-session-v1')).session;let moved=session.actors.find(c=>c.id===current.id);assert.equal(moved.x,destination.x);assert.equal(moved.y,destination.y);assert.equal(session.movement,probe.movement-destination.cost_ft);
// Invalid drop and canceled drag are presentation only and cannot charge movement.
let revision=session.revision;let live=nodes.map.children.find(x=>x.attributes['data-actor']===current.id);
live.onpointerdown(event(moved.x,moved.y));nodes.map.onpointermove(event(99,99));nodes.map.onpointerup(event(99,99));assert.equal(JSON.parse(store.get('isles-table-session-v1')).session.revision,revision);
live=nodes.map.children.find(x=>x.attributes['data-actor']===current.id);live.onpointerdown(event(moved.x,moved.y));nodes.map.onpointermove(event(moved.x+1,moved.y));listeners.keydown({key:'Escape'});assert.equal(JSON.parse(store.get('isles-table-session-v1')).session.revision,revision);assert(!nodes.map.hasPointerCapture(1));
// WASD operates even with the map focused; typing in a form and Ctrl shortcuts do not.
probe=mirror.call({op:'load',session:JSON.parse(store.get('isles-table-session-v1')).session});const step=probe.offers.find(o=>o.kind==='move');assert(step);const direction=step.id.split(':')[1];const key={North:'w',East:'d',South:'s',West:'a'}[direction];listeners.keydown({key,target:nodes.map,preventDefault(){}});assert.equal(JSON.parse(store.get('isles-table-session-v1')).session.revision,revision+1);revision++;
listeners.keydown({key:'w',target:{tagName:'INPUT'},preventDefault(){throw Error('typing intercepted');}});listeners.keydown({key:'a',ctrlKey:true,target:nodes.map,preventDefault(){throw Error('shortcut intercepted');}});assert.equal(JSON.parse(store.get('isles-table-session-v1')).session.revision,revision);

// Whole keyboard segment undo is issued to the real engine.
listeners.keydown({key:'z',ctrlKey:true,target:nodes.map,preventDefault(){}});
let undone=JSON.parse(store.get('isles-table-session-v1')).session;
assert.equal(undone.movement,session.movement);assert.equal(undone.actors.find(a=>a.id===current.id).x,moved.x);
// A ruler with a right-click bend never changes engine state or movement.
const stateBeforeRuler=store.get('isles-table-session-v1');
nodes.measure.click();assert.equal(nodes.measure.attributes['aria-pressed'],'true');
nodes.map.onpointerdown(event(1,1,7));nodes.map.onpointermove(event(4,1,7));
nodes.map.onmousedown({...event(4,1,7),button:2});nodes.map.onpointermove(event(4,5,7));nodes.map.onpointerup(event(4,5,7));
assert.equal(store.get('isles-table-session-v1'),stateBeforeRuler);assert(!nodes.map.hasPointerCapture(7));
const ruler=nodes.map.children.at(-1);assert(ruler.children.some(c=>c.textContent==='35.0 ft · geometric'));
listeners.keydown({key:'Escape'});nodes.measure.click();
// Optional token waypoint: out, back through origin, then out again costs 15 ft.
nodes.new.click();undone=JSON.parse(store.get('isles-table-session-v1')).session;
probe=mirror.call({op:'load',session:undone});current=probe.state.combatants.find(c=>c.id===probe.state.active);
const near=probe.movement_targets.find(t=>t.cost_ft===5);assert(near);
live=nodes.map.children.find(x=>x.attributes['data-actor']===current.id);
live.onpointerdown(event(current.x,current.y));nodes.map.onpointermove(event(near.x,near.y));
nodes.map.onmousedown({...event(near.x,near.y),button:2});nodes.map.onpointermove(event(current.x,current.y));
nodes.map.onmousedown({...event(current.x,current.y),button:2});nodes.map.onpointermove(event(near.x,near.y));nodes.map.onpointerup(event(near.x,near.y));
let routed=JSON.parse(store.get('isles-table-session-v1')).session;assert.equal(routed.movement,undone.movement-15);
nodes['undo-move'].click();const routeUndone=JSON.parse(store.get('isles-table-session-v1')).session;assert.equal(routeUndone.movement,undone.movement);assert.equal(routeUndone.actors.find(a=>a.id===current.id).x,current.x);

// Effects: actual map placement, movable handles, exact controls and fixed trigger policy.
nodes['fx-preset'].value='cloud';nodes['fx-preset'].onchange();nodes['fx-place'].click();
const combatBefore=JSON.parse(store.get('isles-table-session-v1')).session;
nodes.map.onpointerdown(event(4,4,9));nodes.map.onpointermove(event(6,4,9));nodes.map.onpointerup(event(6,4,9));
let withFx=JSON.parse(store.get('isles-table-session-v1')).session;assert.equal(withFx.effects.length,1);assert.equal(withFx.effects[0].radius_ft,10);assert.equal(withFx.movement,combatBefore.movement);assert.deepEqual(withFx.actors,combatBefore.actors);
nodes['fx-list'].children[0].click();assert.equal(nodes['fx-apply'].disabled,false);assert.equal(nodes['fx-position'].disabled,false);
let handles=nodes.map.children.find(c=>c.attributes['data-layer']==='effect-handles');assert(handles);
let handle=handles.children.find(c=>c.attributes['aria-label']==='Drag to move effect');assert(handle);
handle.onpointerdown(event(4,4,10));nodes.map.onpointermove(event(6,5,10));nodes.map.onpointerup(event(6,5,10));
let shifted=JSON.parse(store.get('isles-table-session-v1')).session;assert.equal(shifted.effects[0].origin[0],withFx.effects[0].origin[0]+2);assert.equal(shifted.effects[0].origin[1],withFx.effects[0].origin[1]+1);
nodes['fx-list'].children[0].click();nodes['fx-x'].value='3';nodes['fx-y'].value='3';nodes['fx-position'].click();assert.deepEqual(JSON.parse(store.get('isles-table-session-v1')).session.effects[0].origin,[3,3]);
nodes['fx-trigger-preset'].value='trap_flames';nodes['fx-trigger'].click();nodes['fx-list'].children.at(-1).click();assert(nodes['fx-apply'].disabled);assert(nodes['fx-position'].disabled);assert(nodes['fx-remove'].disabled);
handles=nodes.map.children.find(c=>c.attributes['data-layer']==='effect-handles');assert(!handles.children.some(c=>c.attributes['aria-label']==='Drag to move effect'));
nodes['fx-clear-triggers'].click();assert.equal(JSON.parse(store.get('isles-table-session-v1')).session.effects.length,1);
// Escape abandons a draft and leaving effects mode restores ordinary play controls.
nodes['fx-place'].click();nodes.map.onpointerdown(event(2,2,11));nodes.map.onpointermove(event(4,4,11));listeners.keydown({key:'Escape'});assert.equal(JSON.parse(store.get('isles-table-session-v1')).session.effects.length,1);assert(!nodes.map.hasPointerCapture(11));listeners.keydown({key:'Escape'});assert.equal(nodes['fx-tool'].attributes['aria-pressed'],'false');

// Instant visuals do not create lingering effect records; replay is graphics only.
const beforeShot=JSON.parse(store.get('isles-table-session-v1')).session;
nodes['fx-trigger-preset'].value='ranged_hit';nodes['fx-trigger'].click();
let shot=JSON.parse(store.get('isles-table-session-v1')).session;assert.equal(shot.effects.length,beforeShot.effects.length);assert.equal(shot.visual_events.at(-1).kind,'projectile');
let visuals=nodes.map.children.find(c=>c.attributes['data-layer']==='one-shot-effects');assert(visuals.children.length>0);assert(nodes['fx-recent'].children.length>0);
nodes['fx-recent'].children[0].click();let replayed=JSON.parse(store.get('isles-table-session-v1')).session;assert.deepEqual(replayed.actors,shot.actors);assert.equal(replayed.rng,shot.rng);assert.equal(replayed.action_available,shot.action_available);assert.equal(replayed.movement,shot.movement);
nodes['fx-stop-visuals'].click();visuals=nodes.map.children.find(c=>c.attributes['data-layer']==='one-shot-effects');assert.equal(visuals.children.length,0);

// Animated look cards populate the controls; selected actors drive the transporter preview.
assert.equal(nodes['fx-gallery'].children.length,13);nodes['fx-gallery'].children.find(b=>b.attributes['aria-label']==='Choose Acid jet').click();assert.equal(nodes['fx-appearance'].value,'acid');assert.equal(nodes['fx-shape'].value,'line');
const transportBefore=JSON.parse(store.get('isles-table-session-v1')).session;
const caster=transportBefore.actors.find(a=>a.side==='friend'&&a.hp>0),destinationActor=transportBefore.actors.find(a=>a.side==='foe'&&a.hp>0);
nodes['fx-source'].value=caster.id;nodes['fx-target'].value=destinationActor.id;nodes['fx-trigger-preset'].value='transport';nodes['fx-trigger'].click();
const transported=JSON.parse(store.get('isles-table-session-v1')).session;assert.deepEqual(transported.actors,transportBefore.actors);assert.equal(transported.rng,transportBefore.rng);assert.equal(transported.visual_events.at(-1).kind,'teleport');assert.equal(transported.visual_events.at(-1).effect.source_actor,caster.id);assert.deepEqual(transported.visual_events.at(-1).target_origin,[destinationActor.x,destinationActor.y]);assert.equal(nodes['fx-source'].value,caster.id);assert.equal(nodes['fx-target'].value,destinationActor.id);nodes['fx-stop-visuals'].click();

// Tap-first grouped controls reveal tools without altering the engine.
const beforeMenus=store.get('isles-table-session-v1');
nodes['session-toggle'].click();assert.equal(nodes['session-menu'].hidden,false);assert.equal(nodes['session-toggle'].attributes['aria-expanded'],'true');assert(nodes.save.focused);
nodes['session-toggle'].oncontextmenu({preventDefault(){}});assert.equal(nodes['session-menu'].hidden,false);nodes['session-toggle'].click();assert.equal(nodes['session-menu'].hidden,true);
nodes['session-toggle'].ondblclick({preventDefault(){}});assert.equal(nodes['session-menu'].hidden,false);
nodes['view-toggle'].click();assert.equal(nodes['session-menu'].hidden,true);assert.equal(nodes['view-menu'].hidden,false);listeners.keydown({key:'Escape',preventDefault(){}});assert(nodes['view-menu'].hidden);assert(nodes['view-toggle'].focused);
nodes['view-toggle'].click();listeners.pointerdown({target:body});assert(nodes['view-menu'].hidden);
assert.equal(store.get('isles-table-session-v1'),beforeMenus);
// Effect tabs, auto-dismiss for placement, and explicit Done are available with one tap.
nodes['effects-toggle'].click();assert.equal(nodes['effects-tray'].hidden,false);assert.equal(nodes['effects-pane-place'].hidden,false);assert.equal(nodes['effects-pane-test'].hidden,true);
listeners.keydown({key:'ArrowRight',target:nodes['effects-tab-place'],preventDefault(){}});assert.equal(nodes['effects-tab-map'].attributes['aria-selected'],'true');assert.equal(nodes['effects-pane-map'].hidden,false);
nodes['effects-tab-test'].click();assert.equal(nodes['effects-pane-test'].hidden,false);assert.equal(nodes['effects-pane-map'].hidden,true);
listeners.keydown({key:'Escape',preventDefault(){}});assert(nodes['effects-tray'].hidden);assert(nodes['effects-toggle'].focused);
nodes['effects-toggle'].click();nodes['effects-tab-place'].click();nodes['fx-place'].click();assert(nodes['effects-tray'].hidden);assert.equal(nodes['tool-done'].hidden,false);assert(nodes['mode-hint'].textContent.includes('Place effect'));
nodes['fx-tool'].click();assert.equal(nodes['fx-tool'].attributes['aria-pressed'],'true');nodes['fx-tool'].click();assert.equal(nodes['fx-tool'].attributes['aria-pressed'],'true');
nodes['tool-done'].click();assert.equal(nodes['tool-done'].hidden,true);assert.equal(nodes['pointer-tool'].attributes['aria-pressed'],'true');assert.equal(nodes['fx-tool'].attributes['aria-pressed'],'false');
nodes['measure'].click();assert.equal(nodes['tool-done'].hidden,false);assert(nodes['mode-hint'].textContent.includes('Measure:'));nodes['pointer-tool'].click();assert.equal(nodes.measure.attributes['aria-pressed'],'false');
nodes['effects-toggle'].click();nodes['effects-tab-map'].click();nodes['fx-configure-selected'].click();assert.equal(nodes['effects-pane-place'].hidden,false);assert(nodes['fx-custom'].open);nodes['effects-close'].click();assert(nodes['effects-tray'].hidden);

// If this device cannot start WebGL, the same game stays in the tactical view.
const beforeCamera=store.get('isles-table-session-v1');nodes['camera-mode'].onchange({target:{value:'third-person'}});assert.equal(nodes['camera-mode'].value,'topdown');assert(nodes['third-person-wrap'].hidden);assert.equal(nodes['map-scroll'].hidden,false);assert.equal(store.get('isles-table-session-v1'),beforeCamera);assert(nodes.toast.textContent.includes('WebGL is unavailable'));

console.log('PASS: real WASM-driven UI startup; turn progression, 306-token cabinet/search, theme isolation, new scene, helper confirmation, information dialog, multi-square pointer drag, invalid drops, Escape cancel, WASD and typing exclusion. ruler distance and right-click waypoints without state mutation, routed token drag and whole-move Ctrl+Z/button undo. Effects placement, movement handles, exact position, locked-source controls and Escape cancellation. One-shot playback, damage-free replay and stop control. Tap/right-click/double-click disclosures, outside/Escape dismissal, keyboard tabs, unobstructed placement and Done/Move controls. DOM harness only, not browser visual QA.');
