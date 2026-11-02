import assert from 'node:assert/strict';
import fs from 'node:fs';
import {keyMove,dragTarget,mapPoint} from './dist/movement.mjs';
import {RustEngine} from './dist/engine.mjs';
for(const [key,expected] of [['w','North'],['W','North'],['a','West'],['s','South'],['d','East'],['ArrowUp','North'],['ArrowRight','East'],['ArrowDown','South'],['ArrowLeft','West']])assert.equal(keyMove({key,target:{tagName:'svg'}}),'move:'+expected);
for(const target of [{tagName:'INPUT'},{tagName:'SELECT'},{tagName:'TEXTAREA'},{isContentEditable:true}])assert.equal(keyMove({key:'w',target}),null);
assert.equal(keyMove({key:'w',ctrlKey:true}),null);assert.equal(keyMove({key:'a',metaKey:true}),null);
const large={x:13.5,y:7.5};const targets=[{x:15.5,y:8.5,id:'valid',cost_ft:15}];assert.equal(dragTarget(large,{x:13.8,y:7.1},{x:15.8,y:8.1},targets).offer.id,'valid');assert(dragTarget(large,{x:0,y:0},{x:.1,y:.1},targets).unchanged);assert.equal(dragTarget(large,{x:0,y:0},{x:50,y:50},targets).offer,null);
const root={getScreenCTM:()=>({inverse:()=>({scale:0.05,dx:-5,dy:-2})}),createSVGPoint:()=>({x:0,y:0,matrixTransform(m){return {x:this.x*m.scale+m.dx,y:this.y*m.scale+m.dy};}})};assert.deepEqual(mapPoint(root,{clientX:220,clientY:100}),{x:6,y:3});
const engine=await RustEngine.create(fs.readFileSync(new URL('./dist/isles_engine.wasm',import.meta.url)));
let v=engine.call({op:'new',seed:7,scene:'harbor'});let a=v.state.combatants.find(c=>c.id===v.state.active);assert(v.movement_targets.length>4);
const target=v.movement_targets.find(t=>t.cost_ft>=15);assert(target);const before=structuredClone(v);v=engine.call({op:'command',id:'drag',revision:v.state.revision,offer_id:target.id});assert(v.ok);assert.equal(v.movement,before.movement-target.cost_ft);a=v.state.combatants.find(c=>c.id===v.state.active);assert.equal(a.x,target.x);assert.equal(a.y,target.y);assert.equal(v.state.revision,before.state.revision+1);
let duplicate=engine.call({op:'command',id:'drag',revision:before.state.revision,offer_id:target.id});assert.deepEqual(duplicate.state,v.state);assert.equal(duplicate.movement,v.movement);
let invalid=engine.call({op:'command',id:'bad',revision:v.state.revision,offer_id:'move_to:99:99'});assert.equal(invalid.ok,false);assert.deepEqual(engine.call({op:'state'}).state,v.state);
const messages=engine.call({op:'export'}).messages;assert.deepEqual(messages.find(m=>m.type==='result').movement_path,target.path);
// Real Large token: all destinations preserve grid-corner centres and body clearance.
v=engine.call({op:'new',seed:7,scene:'temple'});for(let i=0;i<4&&v.state.combatants.find(c=>c.id===v.state.active).space_ft!==10;i++)v=engine.call({op:'command',id:'end-'+i,revision:v.state.revision,offer_id:'end'});assert.equal(v.state.combatants.find(c=>c.id===v.state.active).space_ft,10);for(const t of v.movement_targets){assert.equal(t.x%1,.5);assert.equal(t.y%1,.5);assert(t.cost_ft<=v.movement);}
console.log('PASS: arrow/WASD input, typing/modifier exclusion, zoom/scroll coordinates, Large-token grab offsets; actual WASM multi-step moves, costs, duplicate/invalid drops and exported paths.');
