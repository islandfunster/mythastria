import {createThirdPerson} from './third-person.mjs';
import {SKINS,savedSkin,saveSkin} from './site.mjs';
import {createTableUI} from './table-ui.mjs';
import {createVisualQueue,visualGraphic} from './effect-events.mjs';
import {createEffects} from './effects.mjs';
import {RustEngine} from './engine.mjs';import {loadCatalog} from './catalog.mjs';import {createRosterPort} from './character-roster.mjs';
import {createRustPort} from './engine-port.mjs';
import {keyMove,dragTarget,mapPoint} from './movement.mjs';
const $=id=>document.getElementById(id),NS='http://www.w3.org/2000/svg';
let characterWorkshop,characterOpening=false;
let thirdPerson,cameraMode='topdown',cameraRestored=false,ui,fx,engine,view,catalog=[],byId=new Map(),selected=null,zoom=1,working=false,suggestion=null,drag=null,suppressClickUntil=0,measureMode=false,measurement=null;
const element=(tag,cls,text)=>{const e=document.createElement(tag);if(cls)e.className=cls;if(text!==undefined)e.textContent=String(text);return e;};
const svg=(tag,attrs={},text)=>{const e=document.createElementNS(NS,tag);for(const [k,v]of Object.entries(attrs))e.setAttribute(k,String(v));if(text!==undefined)e.textContent=String(text);return e;};
const token=a=>byId.get(a.token_id);
function request(payload){const response=engine.call(payload);if(!response.ok)throw Error(response.error??'Engine rejected the request');return response;}
function error(err){$('error').textContent=err.message??String(err);$('error').hidden=false;}
function notify(text){$('toast').textContent=text;$('toast').hidden=false;clearTimeout(notify.timer);notify.timer=setTimeout(()=>$('toast').hidden=true,3500);}
function retain(){try{const session=request({op:'save'});localStorage.setItem('isles-table-session-v1',JSON.stringify(session));}catch{ /* Saving to a file remains available if browser storage is full. */ }}
function update(next,{silentEffects=false}={}){fx?.onUpdate(next,{silent:silentEffects});clearRuler();if(drag){suppressClickUntil=Date.now()+500;releaseDrag();}view=next;if(!selected||!view.state.combatants.some(a=>a.id===selected))selected=view.state.active??view.state.combatants[0]?.id;suggestion=null;$('error').hidden=true;render();retain();if(!cameraRestored){cameraRestored=true;try{if(localStorage.getItem('isles-table-camera')==='third-person')setCameraMode('third-person');}catch{}}}
function act(offerId,revision=view.state.revision){if(working)return;working=true;try{update(request({op:'command',id:crypto.randomUUID(),revision,offer_id:offerId}));}catch(e){error(e);}finally{working=false;}}
function render(){if(!view)return;$('scene-title').textContent=view.map.name;$('map-label').textContent=view.map.name;$('round').textContent='ROUND '+view.state.round;$('scene').value=view.scene;$('outcome').hidden=!view.winner;$('outcome').textContent=view.winner?view.winner+' wins the training encounter':'';drawLedger();drawMap();drawCharacter();drawActions();drawLog();fx?.refresh();ui?.sync();$('suggestion').hidden=true;}
function drawLedger(){const root=$('initiative');root.replaceChildren();for(const a of view.state.combatants){const b=element('button',`actor-row ${a.side==='foe'?'foe':''} ${a.id===view.state.active?'active':''} ${a.id===selected?'selected':''} ${a.down?'down':''}`);b.setAttribute('aria-pressed',String(a.id===selected));const num=element('span','initiative-num',a.initiative),im=element('img','avatar');im.src=token(a).path;im.alt='';const info=element('span','actor-text');info.append(element('div','actor-name',a.name));const sub=element('div','actor-sub');sub.append(element('span','',a.down?'DEFEATED':a.id===view.state.active?'ACTING':a.side==='friend'?'PARTY':'OPPOSITION'),element('span','',`${a.hp}/${a.hp_max}`));const bar=element('div','hp-bar'),fill=element('i');fill.style.width=Math.max(0,a.hp/a.hp_max)*100+'%';bar.append(fill);info.append(sub,bar);b.append(num,im,info);b.onclick=()=>{selected=a.id;render();};root.append(b);}}
function drawMap(){const root=$('map'),m=view.map,css=getComputedStyle(document.body),color=k=>css.getPropertyValue(k).trim();root.replaceChildren();root.setAttribute('viewBox',`-0.55 -0.55 ${m.cols+1.1} ${m.rows+1.1}`);root.style.aspectRatio=`${m.cols+1.1}/${m.rows+1.1}`;$('map-wrap').style.width=100*zoom+'%';const defs=svg('defs');const pattern=svg('pattern',{id:'tiles',width:2,height:2,patternUnits:'userSpaceOnUse'});pattern.append(svg('rect',{width:2,height:2,fill:color('--map-floor')}),svg('rect',{width:1,height:1,fill:color('--map-tile')}),svg('rect',{x:1,y:1,width:1,height:1,fill:color('--map-tile')}));const grid=svg('pattern',{id:'grid-pattern',width:1,height:1,patternUnits:'userSpaceOnUse'});grid.append(svg('path',{d:'M1 0H0V1',fill:'none',stroke:color('--map-grid'),'stroke-width':.025}));defs.append(pattern,grid);root.append(defs,svg('rect',{width:m.cols,height:m.rows,fill:'url(#tiles)'}));
 // Original decorative masonry, not collision geometry. Only Rust walls govern movement.
 for(let y=0;y<m.rows;y++)for(let x=0;x<m.cols;x++){if((x*17+y*31)%19===0)root.append(svg('path',{d:`M${x+.18} ${y+.2}l.2 .25 -.08 .22 .25 .2`,fill:'none',stroke:color('--map-grid'),'stroke-width':.025,'pointer-events':'none'}));}
 for(const glyph of [{x:4,y:2,t:'VII'},{x:13,y:9,t:'✧'}])root.append(svg('text',{x:glyph.x,y:glyph.y,fill:color('--map-wall'),opacity:.25,'font-size':.65,'text-anchor':'middle','pointer-events':'none'},glyph.t));
 if($('grid').checked)root.append(svg('rect',{width:m.cols,height:m.rows,fill:'url(#grid-pattern)','pointer-events':'none'}));
 for(const o of view.movement_targets??[]){const r=svg('rect',{x:o.x+.05,y:o.y+.05,width:.9,height:.9,fill:color('--brass'),'fill-opacity':.12,stroke:color('--brass'),'stroke-width':.03,'stroke-dasharray':'.08 .06',class:'step',role:'button',tabindex:0,'aria-label':`Move ${o.cost_ft} ft`});r.append(svg('title',{},`Move ${o.cost_ft} ft`));r.onclick=()=>{if(!fx?.active&&!measureMode&&Date.now()>=suppressClickUntil)act(o.id);};r.onkeydown=e=>{if(['Enter',' '].includes(e.key)){e.preventDefault();act(o.id);}};root.append(r);}
 fx?.draw();
 for(const w of m.walls){const points=w.points.map(([x,y])=>`${x+.5},${y+.5}`).join(' ');const line=svg('polyline',{points,fill:'none',stroke:w.door?color('--brass'):color('--map-wall'),'stroke-width':w.door?.16:.13,'stroke-linecap':'square','stroke-dasharray':w.open?'.15 .18':'none',opacity:w.open?.6:1});line.append(svg('title',{},w.door?`Gate · ${w.open?'open':'closed'}`:w.id));root.append(line);if(w.door){const available=view.offers.find(o=>o.id==='door:'+w.id);if(available){const hit=svg('polyline',{points,fill:'none',stroke:'transparent','stroke-width':.6,style:'cursor:pointer',role:'button',tabindex:0,'aria-label':available.label});hit.onclick=()=>{if(!fx?.active&&!measureMode&&Date.now()>=suppressClickUntil)act(available.id);};hit.onkeydown=e=>{if(['Enter',' '].includes(e.key)){e.preventDefault();act(available.id);}};root.append(hit);}}}
 for(let x=0;x<m.cols;x+=2)root.append(svg('text',{x:x+.5,y:-.15,fill:color('--muted'),'font-size':.18,'text-anchor':'middle'},x));for(let y=0;y<m.rows;y+=2)root.append(svg('text',{x:-.3,y:y+.56,fill:color('--muted'),'font-size':.18,'text-anchor':'middle'},y));
 for(const a of view.state.combatants){const t=token(a),size=a.space_ft/m.square_ft,x=a.x+.5,y=a.y+.5,c=color(a.side==='friend'?'--friend':'--foe'),active=a.id===view.state.active;const g=svg('g',{class:'unit'+(active?' draggable':''),role:'button',tabindex:0,'data-actor':a.id,'aria-pressed':a.id===selected,'aria-label':`${a.name}, ${a.hp}/${a.hp_max} hit points`});g.append(svg('rect',{x:x-size/2,y:y-size/2,width:size,height:size,rx:.06,fill:c,'fill-opacity':active?.14:.035,stroke:a.id===selected?color('--brass'):c,'stroke-width':a.id===selected?.06:.025,opacity:a.down?.35:1}));if(active)g.append(svg('path',{d:`M${x-.13} ${y-size/2-.18}L${x+.13} ${y-size/2-.18}L${x} ${y-size/2-.03}Z`,fill:color('--brass')}));g.append(svg('image',{href:t.path,x:x-size*.47,y:y-size*.47,width:size*.94,height:size*.94,preserveAspectRatio:'xMidYMid meet',opacity:a.down?.3:1}));if(a.down)g.append(svg('text',{x,y:y+.15,'text-anchor':'middle',fill:c,'font-size':.6},'×'));if($('labels').checked)g.append(svg('text',{x,y:y-size/2-.26,fill:color('--map-ink'),'font-size':.2,'text-anchor':'middle',stroke:color('--map-floor'),'stroke-width':.045,'paint-order':'stroke'},a.name));g.append(svg('rect',{x:x-size*.35,y:y+size/2-.025,width:size*.7,height:.055,fill:color('--ink')}),svg('rect',{x:x-size*.35,y:y+size/2-.025,width:size*.7*a.hp/a.hp_max,height:.055,fill:c}));g.onpointerdown=e=>beginDrag(e,a,g);g.onclick=()=>{if(fx?.active||measureMode||Date.now()<suppressClickUntil)return;selected=a.id;render();};g.onkeydown=e=>{if(['Enter',' '].includes(e.key)){e.preventDefault();selected=a.id;render();}};root.append(g);}drawRuler();fx?.handles();}
function drawCharacter(){const root=$('character');root.replaceChildren();const a=view.state.combatants.find(c=>c.id===selected);if(!a)return;const t=token(a);$('selected-label').textContent=a.name;$('selected-side').textContent=a.side==='friend'?'PARTY':'OPPOSITION';const top=element('div','character-top'),im=element('img');im.src=t.path;im.alt=t.name+' token art';const info=element('div');info.append(element('div','character-name',a.name),element('div','character-caption',`Art: ${t.name}\n${t.footprint} squares · ${t.pixels} px`));top.append(im,info);root.append(top);const stats=element('div','stats');for(const [v,label]of [[a.hp+'/'+a.hp_max,'HIT POINTS'],[a.ac,'ARMOUR'],[a.space_ft+' ft','SPACE']]){const d=element('div');d.append(element('strong','',v),element('small','',label));stats.append(d);}root.append(stats);if(a.character){const sheet=element('button','quiet','Open character sheet');sheet.onclick=()=>openCharacterWorkshop(request({op:'character_actor_sheet',actor:a.id}).character);root.append(sheet);}if(a.conditions.length)root.append(element('p','footprint-hint',a.conditions.join(' · ')));}
function drawActions(){const a=view.state.combatants.find(c=>c.id===view.state.active);$('active-name').textContent=a?.name??'Encounter concluded';const r=$('resources');r.replaceChildren(element('span','',view.winner?'No further actions':`${view.movement} ft remaining`),element('span','',view.action_available?'Action ready':'Action used'),element('span','diagonal-hint',`Next diagonal: ${view.next_diagonal_ft??5} ft`));const root=$('actions');root.replaceChildren();for(const o of view.offers.filter(o=>o.kind!=='end'&&o.kind!=='move'&&o.kind!=='undo')){const b=element('button',o.kind==='attack'?'attack':'',o.label);b.onclick=()=>act(o.id);root.append(b);}$('end').disabled=!view.offers.some(o=>o.kind==='end');$('suggest').disabled=!!view.winner;$('undo-move').disabled=!view.offers.some(o=>o.id==='undo_move');}
function drawLog(){const root=$('log');root.replaceChildren();view.log.forEach((text,i)=>{const r=element('div','log-line');r.append(element('small','',String(i+1).padStart(2,'0')),element('span','',text));root.append(r);});root.scrollTop=root.scrollHeight;}
function download(name,value){const u=URL.createObjectURL(new Blob([JSON.stringify(value,null,2)],{type:'application/json'})),a=element('a');a.href=u;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(u),1000);}
function drawCatalog(){const q=$('search').value.toLowerCase().trim(),size=$('size').value;const matches=catalog.filter(t=>(size==='all'||Number(size)===t.squares)&&t.name.toLowerCase().includes(q));$('matches').textContent=matches.length+' creatures';const root=$('token-grid');root.replaceChildren();const actor=view.state.combatants.find(a=>a.id===selected);$('assignment').textContent=`Selected actor: ${actor?.name??'none'}. Choose matching-size artwork to assign it. Larger creatures remain available to inspect in the collection.`;for(const t of matches){const b=element('button','token-card');b.setAttribute('aria-label',`Assign ${t.name} artwork, ${t.footprint} squares`);const im=element('img');im.src=t.path;im.alt=t.name;im.loading='lazy';b.append(im,element('strong','',t.name),element('small','',`${t.footprint} · ${t.pixels}px`));b.onclick=()=>{try{update(request({op:'skin',actor:selected,token_id:t.id}));$('collection').close();notify('Artwork assigned. Combat statistics unchanged.');}catch(e){$('assignment').textContent=e.message;}};root.append(b);}}
function applySkin(name){if(!SKINS.includes(name))name=SKINS[0];document.body.dataset.skin=name;$('skin').value=name;saveSkin(name);if(view)drawMap();}   // site.mjs: Tabletop by default (GM 2026-10-20)
const skinLink=element('link');skinLink.rel='stylesheet';skinLink.href='skins.css';document.head.append(skinLink);skinLink.onload=()=>{if(view)drawMap();};
$('skin').onchange=e=>applySkin(e.target.value);applySkin(savedSkin());

async function openCharacterWorkshop(profile){if(characterOpening)return;characterOpening=true;try{if(!engine)throw Error('The engine is still loading.');if(!characterWorkshop){const {createCharacterUI}=await import('./character-ui.mjs');characterWorkshop=await createCharacterUI({send:request,roster:createRosterPort({rust:request}).call,getView:()=>view,getSelected:()=>selected,update,tokens:catalog,notify});}if(profile)characterWorkshop.openActor(profile);else characterWorkshop.open();}catch(e){error(e);}finally{characterOpening=false;}}
$('characters').onclick=()=>openCharacterWorkshop();
$('end').onclick=()=>act('end');$('new').onclick=()=>{try{const seed=crypto.getRandomValues(new Uint32Array(1))[0];selected=null;update(request({op:'new',seed,scene:$('scene').value}));}catch(e){error(e);}};$('grid').onchange=drawMap;$('labels').onchange=drawMap;$('plus').onclick=()=>{zoom=Math.min(3,zoom+.25);drawMap();};$('minus').onclick=()=>{zoom=Math.max(1,zoom-.25);drawMap();};$('fit').onclick=()=>{zoom=1;drawMap();};$('library').onclick=()=>{drawCatalog();$('collection').showModal();};$('close-library').onclick=()=>$('collection').close();$('search').oninput=drawCatalog;$('size').onchange=drawCatalog;$('about').onclick=$('rules').onclick=()=>$('information').showModal();$('close-about').onclick=()=>$('information').close();$('save').onclick=()=>{try{download('isles-session.json',request({op:'save'}));}catch(e){error(e);}};$('export').onclick=()=>{try{download('isles-encounter-messages.json',request({op:'export'}).messages);}catch(e){error(e);}};$('load').onclick=()=>$('file').click();$('file').onchange=async e=>{try{const file=e.target.files[0];if(!file)return;if(file.size>1_800_000)throw Error('Session file exceeds the 1.8 MB prototype limit.');const data=JSON.parse(await file.text());update(request({op:'load',session:data.session??data}),{silentEffects:true});notify('Session restored by the Rust engine.');}catch(err){error(err);}finally{e.target.value='';}};
$('suggest').onclick=()=>{try{const s=request({op:'suggest'});if(!s.offer)return;suggestion=s.offer;$('suggestion').replaceChildren(element('span','',s.offer.label));const b=element('button','', 'Take this action');b.onclick=()=>act(s.offer.id);$('suggestion').append(b);$('suggestion').hidden=false;}catch(e){error(e);}};

function beginDrag(e,actor,group){
 if(fx?.active||measureMode||!view||working||drag||e.button!==0||e.isPrimary===false||$('collection').open||$('information').open)return;
 selected=actor.id;
 if(actor.id!==view.state.active||actor.down){render();notify('Only the current-turn token can move.');return;}
 const root=$('map');e.preventDefault();
 drag={pointer:e.pointerId,actor,start:mapPoint(root,e),clientX:e.clientX,clientY:e.clientY,group,revision:view.state.revision,moved:false,target:null,pins:[]};
 root.setPointerCapture(e.pointerId);root.focus({preventScroll:true});drawLedger();drawCharacter();
}
function previewDrag(e){
 if(!drag||e.pointerId!==drag.pointer)return;
 e.preventDefault();
 if(!drag.moved&&Math.hypot(e.clientX-drag.clientX,e.clientY-drag.clientY)<4)return;
 drag.moved=true;suppressClickUntil=Date.now()+500;
 const point=mapPoint($('map'),e),target=dragTarget(drag.actor,drag.start,point,view.movement_targets??[]);
 if(drag.pins.length){const preview=engine.call({op:'path_preview',revision:drag.revision,waypoints:[...drag.pins,[target.x,target.y]]});target.offer=preview.ok?preview.route:null;target.unchanged=false;}
 drag.target=target;
 if(!drag.layer){drag.layer=svg('g',{'pointer-events':'none','aria-hidden':true});$('map').append(drag.layer);}
 drag.layer.replaceChildren();
 const css=getComputedStyle(document.body),valid=!!target.offer||target.unchanged,color=css.getPropertyValue(valid?'--brass':'--rust').trim();
 if(target.offer){const path=[[drag.actor.x,drag.actor.y],...target.offer.path];drag.layer.append(svg('polyline',{points:path.map(([x,y])=>`${x+.5},${y+.5}`).join(' '),fill:'none',stroke:color,'stroke-width':.075,'stroke-dasharray':'.12 .09'}));}
 for(const [x,y] of drag.pins)drag.layer.append(svg('circle',{cx:x+.5,cy:y+.5,r:.13,fill:color}));
 const size=drag.actor.space_ft/view.map.square_ft;
 drag.layer.append(svg('rect',{x:target.x+.5-size/2,y:target.y+.5-size/2,width:size,height:size,fill:color,'fill-opacity':.17,stroke:color,'stroke-width':.06}));
 const ghost=drag.group.cloneNode(true);ghost.setAttribute('transform',`translate(${point.x-drag.start.x} ${point.y-drag.start.y})`);ghost.setAttribute('opacity',.65);ghost.setAttribute('class','drag-ghost');ghost.removeAttribute('tabindex');ghost.removeAttribute('role');drag.layer.append(ghost);
 drag.layer.append(svg('text',{x:target.x+.5,y:target.y-size/2+.1,fill:color,'font-size':.28,'text-anchor':'middle'},target.unchanged?'':target.offer?`${target.offer.cost_ft} ft`:'Blocked / too far'));
}
function releaseDrag(){const current=drag;drag=null;if(current&&$('map').hasPointerCapture(current.pointer))$('map').releasePointerCapture(current.pointer);return current;}
function cancelDrag(e){if(!drag||(e?.pointerId!=null&&e.pointerId!==drag.pointer))return;suppressClickUntil=Date.now()+500;releaseDrag();drawMap();}
function finishDrag(e){
 if(!drag||e.pointerId!==drag.pointer)return;
 if(drag.moved)previewDrag(e);
 const finished=releaseDrag();suppressClickUntil=Date.now()+500;
 if(!finished.moved){render();return;}
 if(finished.target?.offer){act(finished.target.offer.id,finished.revision);}else{drawMap();if(!finished.target?.unchanged)notify('That destination is blocked or beyond remaining movement.');}
}
// Rulers are geometric measurements only; token route costs remain engine-owned.
function drawRuler(){
 const root=$('map');if(!measurement)return;
 if(measurement.layer)measurement.layer.remove();
 const g=svg('g',{'pointer-events':'none','aria-hidden':true});measurement.layer=g;
 const points=[...measurement.pins,measurement.end];
 const color=getComputedStyle(document.body).getPropertyValue('--brass').trim();
 let distance=0;for(let i=1;i<points.length;i++)distance+=Math.hypot(points[i].x-points[i-1].x,points[i].y-points[i-1].y)*view.map.square_ft;
 g.append(svg('polyline',{points:points.map(p=>`${p.x},${p.y}`).join(' '),fill:'none',stroke:color,'stroke-width':.06,'stroke-dasharray':'.13 .08'}));
 for(const p of points)g.append(svg('circle',{cx:p.x,cy:p.y,r:.09,fill:color}));
 const end=measurement.end;g.append(svg('text',{x:end.x,y:end.y-.25,fill:color,'font-size':.26,'text-anchor':'middle',stroke:getComputedStyle(document.body).getPropertyValue('--map-floor').trim(),'stroke-width':.06,'paint-order':'stroke'},`${distance.toFixed(1)} ft · geometric`));root.append(g);
}
function clearRuler(){const m=measurement;measurement=null;if(m?.layer)m.layer.remove();if(m?.pointer!=null&&$('map').hasPointerCapture(m.pointer))$('map').releasePointerCapture(m.pointer);}
$('measure').onclick=()=>{if(fx?.active)fx.exit();cancelDrag();clearRuler();measureMode=!measureMode;$('measure').setAttribute('aria-pressed',String(measureMode));$('map').classList.toggle('measuring',measureMode);if(measureMode)notify('Drag to measure. Right-click while dragging adds a waypoint. Escape clears.');};
$('undo-move').onclick=()=>act('undo_move');
$('map').onpointerdown=e=>{if(fx?.down(e))return;if(!measureMode||e.button!==0||!view)return;e.preventDefault();clearRuler();const p=mapPoint($('map'),e);measurement={pointer:e.pointerId,pins:[p],end:p};$('map').setPointerCapture(e.pointerId);$('map').focus({preventScroll:true});drawRuler();};
$('map').onpointermove=e=>{if(fx?.move(e))return;if(measurement?.pointer===e.pointerId){e.preventDefault();measurement.end=mapPoint($('map'),e);drawRuler();}else previewDrag(e);};
$('map').onpointerup=e=>{if(fx?.up(e)){suppressClickUntil=Date.now()+500;return;}if(measurement?.pointer===e.pointerId){measurement.end=mapPoint($('map'),e);measurement.pointer=null;suppressClickUntil=Date.now()+500;if($('map').hasPointerCapture(e.pointerId))$('map').releasePointerCapture(e.pointerId);drawRuler();}else finishDrag(e);};
// mousedown sees a second mouse button while the left button is already held.
$('map').onmousedown=e=>{if(e.button!==2)return;if(drag){e.preventDefault();previewDrag({...e,pointerId:drag.pointer,clientX:e.clientX,clientY:e.clientY,preventDefault:()=>e.preventDefault()});if(drag.target?.offer&&drag.pins.length<31){drag.pins.push([drag.target.x,drag.target.y]);previewDrag({...e,pointerId:drag.pointer,clientX:e.clientX,clientY:e.clientY,preventDefault:()=>e.preventDefault()});}}else if(measurement?.pointer!=null){e.preventDefault();measurement.end=mapPoint($('map'),e);if(measurement.pins.length<32)measurement.pins.push(measurement.end);drawRuler();}};
$('map').oncontextmenu=e=>{if(drag||measureMode)e.preventDefault();};
$('map').onpointercancel=e=>{if(fx?.dragging){fx.cancel();drawMap();}cancelDrag(e);if(measurement?.pointer===e.pointerId)clearRuler();};
$('map').onlostpointercapture=()=>{if(fx?.dragging){fx.cancel();drawMap();}if(drag)cancelDrag();if(measurement?.pointer!=null)clearRuler();};
window.addEventListener('blur',()=>{if(fx?.dragging){fx.cancel();drawMap();}cancelDrag();if(measurement?.pointer!=null)clearRuler();});
document.addEventListener('keydown',e=>{
 if(ui?.handleKey(e))return;
 if($('character-workshop').open)return;
 if(e.key==='Escape'){fx?.escape();if(drag)cancelDrag();clearRuler();return;}
 if(!view||fx?.active||drag||measurement?.pointer!=null||$('collection').open||$('information').open||$('character-workshop').open)return;
 if(e.target?.isContentEditable||['INPUT','SELECT','TEXTAREA'].includes(e.target?.tagName))return;
 if((e.ctrlKey||e.metaKey)&&!e.altKey&&!e.shiftKey&&String(e.key).toLowerCase()==='z'){if(view.offers.some(o=>o.id==='undo_move')){e.preventDefault();act('undo_move');}return;}
 const id=keyMove(e);if(!id)return;e.preventDefault();if(view.offers.some(o=>o.id===id))act(id);
});
function setCameraMode(mode){
 mode=mode==='third-person'?'third-person':'topdown';
 if(mode==='third-person'){
  if(fx?.active||measureMode){fx?.exit();cancelDrag();clearRuler();measureMode=false;$('measure').setAttribute('aria-pressed','false');$('map').classList.toggle('measuring',false);}
  if(!thirdPerson)thirdPerson=createThirdPerson({canvas:$('third-person-canvas'),getView:()=>view,getSelected:()=>selected,getToken:id=>byId.get(id),getEvents:()=>eventPlayer.entries(),status:$('camera-status'),showGrid:()=>$('grid').checked,animate:()=>$('fx-animate').checked&&!(globalThis.matchMedia?.('(prefers-reduced-motion: reduce)').matches),onSelect:id=>{selected=id;render();},onMove:act,onFailure:message=>{setCameraMode('topdown');notify(message);}});
  $('third-person-wrap').hidden=false;$('map-scroll').hidden=true;
  thirdPerson.setQuality($('camera-quality').value);if(!thirdPerson.enable()){mode='topdown';}
 }
 if(mode==='topdown'){thirdPerson?.disable();$('third-person-wrap').hidden=true;$('map-scroll').hidden=false;}
 cameraMode=mode;$('camera-mode').value=mode;try{localStorage.setItem('isles-table-camera',mode);}catch{}ui?.sync();
}
function prepareTactical(id){const original=$(id).onclick;$(id).onclick=e=>{if(cameraMode==='third-person')setCameraMode('topdown');original?.(e);};}

const eventPlayer=createVisualQueue({onChange:()=>{if(view&&!drag)drawMap();}});
fx=createEffects({eventPlayer,renderEvent:(event,svg,options)=>visualGraphic(event,svg,{...options,resolveToken:id=>byId.get(id)}),getView:()=>view,getSelected:()=>selected,root:$('map'),mapPoint,svg,notify,redraw:drawMap,onMode:active=>{if(active){cancelDrag();clearRuler();measureMode=false;$('measure').setAttribute('aria-pressed','false');$('map').classList.toggle('measuring',false);}ui?.sync();},send:action=>update(request({op:'effect',id:crypto.randomUUID(),revision:view.state.revision,action}))});
ui=createTableUI({getCamera:()=>cameraMode==='third-person',editEffects:()=>fx.edit(),getMode:()=>fx?.placing?'place-effects':fx?.active?'effects':measureMode?'measure':'move',done:()=>{fx.exit();cancelDrag();clearRuler();measureMode=false;$('measure').setAttribute('aria-pressed','false');$('map').classList.toggle('measuring',false);}});
$('camera-mode').onchange=e=>setCameraMode(e.target.value);$('camera-back').onclick=()=>setCameraMode('topdown');$('camera-reset').onclick=()=>thirdPerson?.reset();$('camera-quality').onchange=e=>thirdPerson?.setQuality(e.target.value);for(const id of ['measure','fx-place','fx-tool','fx-place-exact'])prepareTactical(id);
try{const res=await fetch('isles_engine.wasm');if(!res.ok)throw Error('Could not load the Rust engine. Reload or serve the local folder over HTTP.');engine=createRustPort(await RustEngine.create(await res.arrayBuffer()));catalog=await loadCatalog()??request({op:'catalog'}).tokens;byId=new Map(catalog.map(t=>[t.id,t]));$('token-count').textContent=catalog.length;let resumed=false;try{const saved=localStorage.getItem('isles-table-session-v1');if(saved){const loaded=engine.call({op:'load',session:JSON.parse(saved).session});if(loaded.ok){update(loaded);resumed=true;}}}catch{}if(!resumed)update(request({op:'new',seed:7,scene:'harbor'}));}catch(e){error(e);}
