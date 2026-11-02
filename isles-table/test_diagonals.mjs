import fs from 'node:fs';import assert from 'node:assert/strict';import {RustEngine} from './dist/engine.mjs';import {keyMove} from './dist/movement.mjs';
const engine=await RustEngine.create(fs.readFileSync(new URL('./dist/isles_engine.wasm',import.meta.url)));let view,serial=0;
const save=()=>engine.call({op:'save'}).session;
function fixture(diagonals=0,budget=30,large=false){engine.call({op:'new',seed:7,scene:large?'temple':'harbor'});const s=save();s.map.cols=30;s.map.rows=20;s.map.walls=[];s.active=large?s.actors.findIndex(a=>a.space_ft===10):s.actors.findIndex(a=>a.space_ft===5);s.actors.forEach((a,i)=>{const phase=a.space_ft===10?.5:0;a.x=18+i*3+phase;a.y=14+phase;});const a=s.actors[s.active],phase=large?.5:0;a.x=4+phase;a.y=4+phase;a.speed=30;s.diagonal_steps=diagonals;s.movement=budget;s.action_available=true;s.undo_move=null;view=engine.call({op:'load',session:s});assert(view.ok,view.error);return a;}
function cmd(id){const r=engine.call({op:'command',id:'d-'+serial++,revision:view.state.revision,offer_id:id});assert(r.ok,r.error);view=r;return r;}
function path(points){const r=engine.call({op:'path_preview',revision:view.state.revision,waypoints:points});assert(r.ok,r.error);return r.route;}
const position=()=>{const a=view.state.combatants.find(a=>a.id===view.state.active);return [a.x,a.y];};
fixture();for(const [cost,remaining,count]of [[5,25,1],[10,15,2],[5,10,3],[10,0,4]]){const o=view.offers.find(o=>o.id==='move:SouthEast');assert(o.label.includes(cost+' ft'));cmd(o.id);assert.equal(view.movement,remaining);assert.equal(view.diagonal_steps,count);assert.equal(view.next_diagonal_ft,count%2?10:5);}assert.deepEqual(position(),[8,8]);
// Straight steps, split commands and Dash do not reset parity.
fixture();cmd('move:SouthEast');cmd('move:East');assert.equal(view.diagonal_steps,1);assert.equal(view.next_diagonal_ft,10);cmd('dash');assert.equal(view.diagonal_steps,1);assert.equal(view.movement,50);cmd('move:SouthEast');assert.equal(view.movement,40);assert.equal(view.diagonal_steps,2);
cmd('undo_move');assert.equal(view.movement,50);assert.equal(view.diagonal_steps,1);assert.deepEqual(position(),[6,5]);
// A whole keyboard group restores its initial counter along with movement.
fixture();cmd('move:SouthEast');cmd('move:SouthEast');cmd('move:East');cmd('undo_move');assert.equal(view.movement,30);assert.equal(view.diagonal_steps,0);assert.deepEqual(position(),[4,4]);
// Waypoints carry parity through every segment; direct drags prefer fewer steps on cost ties.
fixture(0,20);let route=path([[5,5],[6,6],[7,7]]);assert.equal(route.cost_ft,20);assert.equal(route.diagonal_steps,3);assert.equal(route.path.length,3);cmd(route.id);assert.equal(view.diagonal_steps,3);assert.equal(view.movement,0);cmd('undo_move');assert.equal(view.diagonal_steps,0);
fixture(1);route=path([[5,4],[6,5]]);assert.equal(route.cost_ft,15);assert.equal(route.diagonal_steps,1);
fixture();route=view.movement_targets.find(t=>t.x===6&&t.y===6);assert.equal(route.cost_ft,15);assert.equal(route.path.length,2);assert.equal(route.diagonal_steps,2);cmd(route.id);assert.equal(view.next_diagonal_ft,5);
// Saved state preserves both current and undo parity; legacy saves default safely.
const saved=save();assert(engine.call({op:'load',session:saved}).ok);view=engine.call({op:'state'});cmd('undo_move');assert.equal(view.diagonal_steps,0);const legacy=save();delete legacy.diagonal_steps;assert(engine.call({op:'load',session:legacy}).ok);assert.equal(engine.call({op:'state'}).diagonal_steps,0);
// Expensive diagonal cannot be purchased with only one square of movement.
fixture(1,5);assert(!view.offers.some(o=>o.id==='move:SouthEast'));assert(!view.movement_targets.some(t=>t.x===5&&t.y===5));const before=save();let bad=engine.call({op:'command',id:'over-budget',revision:view.state.revision,offer_id:'route:[[5,5]]'});assert(!bad.ok);assert.deepEqual(save(),before);
// Occupied corners and wall tips cannot be cut, even if the destination is clear.
fixture();let s=save();let obstacle=s.actors.find((a,i)=>i!==s.active);obstacle.x=5;obstacle.y=4;view=engine.call({op:'load',session:s});assert(view.ok);assert(!view.offers.some(o=>o.id==='move:SouthEast'));route=view.movement_targets.find(t=>t.x===5&&t.y===5);assert(route&&route.path.length>1);
fixture();s=save();s.map.walls=[{id:'corner',points:[[4.5,3.5],[4.5,4.5]],door:false,open:false}];view=engine.call({op:'load',session:s});assert(view.ok);assert(!view.offers.some(o=>o.id==='move:SouthEast'));route=view.movement_targets.find(t=>t.x===5&&t.y===5);assert(route&&route.path.length>1);
// Large actors keep half-grid centres and cannot clip adjacent occupied corners.
fixture(0,30,true);route=view.movement_targets.find(t=>t.x===5.5&&t.y===5.5);assert(route);assert.equal(route.cost_ft,5);cmd(route.id);assert.equal(view.diagonal_steps,1);assert.deepEqual(position(),[5.5,5.5]);
fixture(0,30,true);s=save();obstacle=s.actors.find(a=>a.space_ft===5);obstacle.x=6;obstacle.y=4;view=engine.call({op:'load',session:s});assert(view.ok,view.error);assert(!view.offers.some(o=>o.id==='move:SouthEast'));
// End turn resets the counter; old command retries never double-charge it.
fixture();const revision=view.state.revision;const id='diag-once';view=engine.call({op:'command',id,revision,offer_id:'move:SouthEast'});assert(view.ok);const completed=save();assert(engine.call({op:'command',id,revision,offer_id:'move:SouthEast'}).ok);assert.deepEqual(save(),completed);cmd('end');assert.equal(view.diagonal_steps,0);assert.equal(view.next_diagonal_ft,5);
for(const [key,direction]of [['q','NorthWest'],['E','NorthEast'],['z','SouthWest'],['c','SouthEast']])assert.equal(keyMove({key}),`move:${direction}`);assert.equal(keyMove({key:'z',ctrlKey:true}),null);assert.equal(keyMove({key:'Home',code:'Numpad7'}),'move:NorthWest');
console.log('PASS: actual WASM alternating 5/10 diagonals, cardinal interleaving, Dash/split/waypoint continuity, weighted path costs, undo/save/load, budget atomicity, wall/actor corners, Large footprints, next-turn reset and command idempotency; diagonal keys.');
