import fs from 'node:fs';import assert from 'node:assert/strict';import crypto from 'node:crypto';import {RustEngine} from './dist/engine.mjs';
const bytes=fs.readFileSync(new URL('./dist/isles_engine.wasm',import.meta.url));const engine=await RustEngine.create(bytes);const registry=engine.call({op:'catalog'}).tokens;assert.equal(registry.length,306);
for(const t of registry){const b=fs.readFileSync(new URL('./dist/'+t.path,import.meta.url));assert.equal(crypto.createHash('sha256').update(b).digest('hex'),t.sha256);}
let v=engine.call({op:'new',seed:7,scene:'temple'});assert(v.ok);assert(v.state.combatants.some(c=>c.space_ft===10));
const original=structuredClone(v.state);let result=engine.call({op:'command',id:'one',revision:v.state.revision,offer_id:'dodge'});assert(result.ok);const revision=result.state.revision;result=engine.call({op:'command',id:'one',revision:0,offer_id:'dodge'});assert.equal(result.state.revision,revision);assert.equal(engine.call({op:'command',id:'stale',revision:0,offer_id:'end'}).ok,false);
const save=engine.call({op:'save'});engine.call({op:'new',seed:22,scene:'harbor'});assert(engine.call({op:'load',session:save.session}).ok);assert.deepEqual(engine.call({op:'state'}).state,result.state);
const actor=result.state.combatants[0];const mismatch=registry.find(t=>t.squares*5!==actor.space_ft);assert.equal(engine.call({op:'skin',actor:actor.id,token_id:mismatch.id}).ok,false);assert.deepEqual(engine.call({op:'state'}).state,result.state);
const candidate=registry.find(t=>t.squares*5===actor.space_ft&&t.id!==actor.token_id);assert(engine.call({op:'skin',actor:actor.id,token_id:candidate.id}).ok);assert.equal(engine.call({op:'state'}).state.combatants[0].hp,actor.hp);
const exported=engine.call({op:'export'}).messages;assert.equal(exported[0].format,'sim-messages/1');assert(exported.some(m=>m.type==='result'&&m.map_update));
let commands=0;v=engine.call({op:'new',seed:1,scene:'harbor'});
for(let i=0;i<500&&!v.winner;i++){const choice=engine.call({op:'suggest'}).offer;assert(choice);v=engine.call({op:'command',id:'auto-'+i,revision:v.state.revision,offer_id:choice.id});assert(v.ok);commands++;}
assert(v.winner, "The simple helper must finish the training encounter within 500 commands.");
assert(engine.call({op:'load',session:engine.call({op:'save'}).session}).ok);
for(let i=0;i<100;i++){const r=engine.call({op:'catalog'});assert.equal(r.tokens.length,306);}
console.log(`PASS: actual WASM ABI; 306 PNG hashes; seeded session, duplicate/stale commands, save/load, footprint-safe art assignment, recording export; ${commands} legal helper commands; repeated allocation/free.`);
