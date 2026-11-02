import assert from 'node:assert/strict';
import fs from 'node:fs';
import {createRemixPort,proofText,playLink} from './dist/remix-port.mjs';
import {mountRemix} from './dist/remix-ui.mjs';
let passed=0;
async function test(name,fn){await fn();passed++;console.log('PASS '+name);}
await test('Session token is attached and refreshed once on an expired token',async()=>{
 const sent=[];let hello=0,refused=false;
 const port=createRemixPort({fetch:async(path,options)=>{
  if(path==='/api/hello'){hello++;return{ok:true,json:async()=>({ok:true,token:'T'+hello})};}
  const q=JSON.parse(options.body);sent.push(q);
  if(!refused){refused=true;return{ok:false,status:403,json:async()=>({ok:false,error:'Invalid session token'})};}
  return{ok:true,json:async()=>({ok:true,campaign:{revision:0}})};
 }});
 await port.state('table');assert.equal(sent[0].token,'T1');assert.equal(sent[1].token,'T2');assert.equal(hello,2);
});
await test('HTTP conflict propagates without silently retrying a save',async()=>{
 let writes=0;const port=createRemixPort({fetch:async(path)=>path==='/api/hello'?{ok:true,json:async()=>({ok:true,token:'T'})}:{ok:false,status:409,json:async()=>{writes++;return{ok:false,error:'Campaign changed'};}}});
 await assert.rejects(()=>port.apply({proposal:'id'}),/Campaign changed/);assert.equal(writes,1);
});
await test('Play links bind the saved campaign, party and Remix selection; proof stays qualified only explicitly',()=>{
 const url=new URL(playLink({source_scenario:'pack/isles/bell.json',campaign:'my-table',level:3,party_size:4,proof:{members:['Hero 1','Hero 2','Hero 3','Hero 4']}}),'http://127.0.0.1:8772');
 assert.equal(url.searchParams.get('campaign'),'my-table');assert.equal(url.searchParams.get('remix'),'1');assert.equal(url.searchParams.get('members'),null);   // GM 2026-10-28: no test characters in the link
 assert.match(proofText(null),/estimate/);assert.match(proofText({qualified:false,remixed:{plays_as:'high',drops_per_run:2}}),/did not qualify/);
});
class Element{
 constructor(tag,doc){this.tagName=tag;this.doc=doc;this.children=[];this.listeners={};this.value='';this.checked=false;this.hidden=false;this.disabled=false;this.textContent='';}
 append(...children){this.children.push(...children);if(this.tagName==='select'&&!this.value&&children.length)this.value=children[0].value;}
 replaceChildren(...children){this.children=[];if(this.tagName==='select')this.value='';this.append(...children);}
 addEventListener(type,fn){this.listeners[type]=fn;}
 emit(type){return this.listeners[type]?.({target:this,preventDefault(){}});}
}
function fakeDoc(){
 const d={nodes:{},all:[],createElement(tag){const e=new Element(tag,d);d.all.push(e);return e;},getElementById(id){return d.nodes[id];},querySelectorAll(tag){return d.all.filter(e=>e.tagName===tag);}};
 const html=fs.readFileSync(new URL('./dist/remix.html',import.meta.url),'utf8');
 for(const m of html.matchAll(/<(\w+)\b[^>]*\bid="([^"]+)"[^>]*>/g)){
  const e=d.createElement(m[1]);d.nodes[m[2]]=e;const val=/\bvalue="([^"]*)"/.exec(m[0]);if(val)e.value=val[1];e.checked=/\bchecked\b/.test(m[0]);e.hidden=/\bhidden\b/.test(m[0]);
 }
 for(const [id,val]of Object.entries({difficulty:'same',tone:'dark'}))d.nodes[id].value=val;
 return d;
}
const settle=async()=>{for(let i=0;i<12;i++)await Promise.resolve();};
function sample(){return{id:'p1',campaign:'default',source_scenario:'pack/demo/dock.json',level:3,party_size:4,target:'moderate',seed:1,
 estimate:{xp:900},groups:[{from:'Harpy',to:'Merfolk',count:4}],story_job:{locked:['Keep <script>this is text</script>']},must_keep:['clue'],
 warnings:['GM review required'],read_aloud:'New trouble',routes:[{approach:'avoid',condition:'GM approves',success:'Cross',failure:'Stay',canon:'Clue'}],proof:null};}
function mounted(){
 const doc=fakeDoc(),requests=[];let saved=[],next=sample(),defer=null;
 const api={hello:async()=>({ok:true}),catalog:async()=>({encounters:[{id:'demo:dock',name:'Dock',level:3,tone:'dark'}],packs:[],unavailable:[]}),
 state:async campaign=>({campaign:{id:campaign,revision:saved.length,active:saved}}),
 propose:async q=>{requests.push(['propose',q]);if(defer)return await defer;return{proposal:structuredClone(next),campaign:{id:'default',revision:0,active:[]}};},
 apply:async q=>{requests.push(['apply',q]);saved=[structuredClone(next)];return{message:'Saved'};},
 remove:async q=>{requests.push(['remove',q]);saved=[];return{message:'Restored'};},
 proof:async q=>{requests.push(['proof',q]);return{job:{id:'job1'}};},
 proofStatus:async()=>({job:{status:'complete'},proposal:{...sample(),proof:{qualified:false,remixed:{plays_as:'high',drops_per_run:2}}}})};
 const timers={callbacks:[],setTimeout(fn){this.callbacks.push(fn);return this.callbacks.length;},clearTimeout(){}};
 const app=mountRemix(doc,api,timers);return{doc,$:id=>doc.nodes[id],app,requests,timers,defer(p){defer=p;}};
}
await test('Mounted page proposes server choices and renders story text without HTML interpretation',async()=>{
 const x=mounted();try{await x.app.ready;x.$('proposal-form').emit('submit');await settle();
 assert.equal(x.requests[0][0],'propose');assert.equal(x.requests[0][1].encounter,'demo:dock');assert.equal(x.$('proposal-panel').hidden,false);
 assert.equal(x.$('locked').children[0].textContent,'Keep <script>this is text</script>');assert.equal(x.$('locked').children[0].children.length,0);
 assert.equal(x.$('reviewed').checked,false);assert.equal(x.$('allow-estimate').checked,false);
 }finally{x.app.dispose();}
});
await test('Save submits review, estimate acknowledgement and revision, never creature statistics',async()=>{
 const x=mounted();try{await x.app.ready;x.$('proposal-form').emit('submit');await settle();x.$('reviewed').checked=true;x.$('allow-estimate').checked=true;x.$('read-aloud').value='My narration';
 await x.$('apply').emit('click');const q=x.requests.at(-1)[1];assert.equal(q.revision,0);assert.equal(q.proposal,'p1');assert.equal(q.reviewed,true);assert.equal(q.allow_estimate,true);assert.equal(q.read_aloud,'My narration');assert.equal(q.scenario,undefined);
 const saved=x.$('saved').children[0];assert(saved.children.some(e=>e.tagName==='a'&&e.href.includes('campaign=default')));
 await saved.children.find(e=>e.tagName==='button').emit('click');assert.equal(x.requests.at(-1)[0],'remove');
 }finally{x.app.dispose();}
});
await test('Late proposal cannot reappear after the campaign or settings change',async()=>{
 const x=mounted();try{await x.app.ready;let resolve;x.defer(new Promise(r=>resolve=r));x.$('proposal-form').emit('submit');await settle();
 x.$('seed').value='2';x.$('seed').emit('change');resolve({proposal:sample(),campaign:{id:'default',revision:0,active:[]}});await settle();assert.equal(x.$('proposal-panel').hidden,true);
 }finally{x.app.dispose();}
});
console.log(`${passed} Remix checks passed (mounted DOM/HTTP harness; no graphical-browser verification).`);
