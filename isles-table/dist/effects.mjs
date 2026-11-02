// Original SVG effect art. Geometry is shared by fill, clip and exact boundary.
// 2026-10-20 (GM: "spell and hit effects in the cartoon style"): an ink outline under the coloured edge, a flat rim
// band inside it, and ink edges on flames, drops, crystals and bolts, as the tokens are drawn.
import {INK_HEX as INK} from './world-style.mjs';
export const presets={
 breath:{label:'Burning breath',shape:'cone',appearance:'fire',length_ft:30,width_ft:5,radius_ft:10},
 lightning:{label:'Lightning line',shape:'line',appearance:'lightning',length_ft:30,width_ft:5,radius_ft:10},
 cloud:{label:'Venom cloud',shape:'circle',appearance:'poison',length_ft:20,width_ft:10,radius_ft:15},
 burst:{label:'Frost burst',shape:'circle',appearance:'frost',length_ft:20,width_ft:10,radius_ft:10},
 blast:{label:'Arcane blast',shape:'circle',appearance:'arcane',length_ft:20,width_ft:10,radius_ft:10},
 wall:{label:'Wall of flame',shape:'rectangle',appearance:'fire',length_ft:30,width_ft:5,radius_ft:10},
 bolt:{label:'Ranged bolt',shape:'ranged',appearance:'lightning',length_ft:30,width_ft:5,radius_ft:5},
 acid:{label:'Acid jet',shape:'line',appearance:'acid',length_ft:30,width_ft:5,radius_ft:10},
 thunder:{label:'Thunder pulse',shape:'circle',appearance:'thunder',length_ft:20,width_ft:10,radius_ft:10},
 healing:{label:'Healing light',shape:'circle',appearance:'healing',length_ft:5,width_ft:5,radius_ft:5},
 shadow:{label:'Clinging shadow',shape:'circle',appearance:'shadow',length_ft:20,width_ft:10,radius_ft:10},
 transport:{label:'Transport shimmer',shape:'circle',appearance:'transport',length_ft:5,width_ft:5,radius_ft:5},
 strike:{label:'Melee impact',shape:'melee',appearance:'physical',length_ft:5,width_ft:5,radius_ft:5}
};
export const palettes={fire:['#fa792f','#ffe29a','#a72f34'],frost:['#7dcfe8','#e9faff','#4384ac'],lightning:['#8da1ff','#eef6ff','#4b65b4'],poison:['#b0cb5d','#e4ed9d','#647843'],smoke:['#a19db8','#e3dbe4','#565368'],arcane:['#bf90e9','#f2d6fd','#775cb2'],physical:['#d8b382','#fff0c5','#8c6650'],radiant:['#ecd47c','#fff4cb','#ab8c48'],acid:['#b8d845','#f4ffc2','#718d24'],thunder:['#b9a0d9','#f0e9ff','#74627f'],healing:['#81cbb5','#eaffd9','#418d76'],shadow:['#8a7ba1','#c0b2d4','#322c45'],transport:['#e1b66a','#fff0ba','#8d754f'],darkness:['#2a2438','#4a4360','#07060b']};   // MAP-LAYERS-01: magical Darkness
export function effectBoundary(e){const l=e.length_ft/5,w=e.width_ft/5,r=e.radius_ft/5;
 if(e.shape==='circle')return {tag:'circle',attrs:{cx:0,cy:0,r}};
 if(e.shape==='melee')return {tag:'circle',attrs:{cx:0,cy:0,r:.5}};
 if(e.shape==='cone')return {tag:'path',attrs:{d:`M0 0 L${l} ${-l/2} L${l} ${l/2} Z`}};
 if(e.shape==='ranged')return {tag:'rect',attrs:{x:0,y:-.09,width:l,height:.18,rx:.09}};
 return {tag:'rect',attrs:{x:0,y:-w/2,width:l,height:w}};
}
export function effectDescription(e){if(e.shape==='circle')return `${e.radius_ft} ft radius`;if(e.shape==='melee')return '5 ft impact marker';if(e.shape==='cone')return `${e.length_ft} ft cone`;if(e.shape==='ranged')return `${e.length_ft} ft visual trajectory`;return `${e.length_ft} × ${e.width_ft} ft`;}
export function aimEffect(e,start,end){const dx=end.x-start.x,dy=end.y-start.y,dist=Math.hypot(dx,dy)*5;
 return {...e,origin:[start.x-.5,start.y-.5],angle_deg:Math.atan2(dy,dx)*180/Math.PI,
 ...(dist<2.5?{}:e.shape==='circle'?{radius_ft:Math.max(5,Math.min(120,Math.round(dist/5)*5))}:e.shape==='melee'?{}:{length_ft:Math.max(5,Math.min(120,Math.round(dist/5)*5))})};
}
export function effectGraphic(e,svg,{selected=false,preview=false,animate=true}={}){
 const [main,light,dark]=palettes[e.appearance]??palettes.arcane;
 const g=svg('g',{class:`fx-art ${animate?'':'fx-still'} ${preview?'fx-preview':''}`,'data-effect':e.id,transform:`translate(${e.origin[0]+.5} ${e.origin[1]+.5}) rotate(${e.angle_deg})`,'pointer-events':'none'});
 const geom=()=>{const b=effectBoundary(e);return svg(b.tag,b.attrs);};
 const key='clip-'+e.id.replace(/[^a-zA-Z0-9_-]/g,'');
 const defs=svg('defs'),clip=svg('clipPath',{id:key});clip.append(geom());defs.append(clip);g.append(defs);
 const base=geom();base.setAttribute('fill',main);base.setAttribute('fill-opacity',e.shape==='ranged'?.34:.22);g.append(base);
 const art=svg('g',{'clip-path':`url(#${key})`});{const rim=geom();rim.setAttribute('fill','none');rim.setAttribute('stroke',main);rim.setAttribute('stroke-width',.34);rim.setAttribute('stroke-opacity',.32);rim.setAttribute('class','fx-rim');art.append(rim);}
 const radius=e.shape==='circle'?e.radius_ft/5:e.shape==='melee'?.5:0,l=e.length_ft/5,w=e.shape==='cone'?l:e.width_ft/5;
 const bounds=radius?[-radius,-radius,radius*2,radius*2]:[0,-w/2,l,w];
 if(e.appearance==='acid'){
  for(let i=0;i<24;i++){const x=bounds[0]+(i*43%103)/102*bounds[2],y=bounds[1]+(i*31%97)/96*bounds[3];art.append(svg('path',{d:`M${x} ${y-.2}Q${x+.22} ${y+.08} ${x} ${y+.14}Q${x-.22} ${y+.08} ${x} ${y-.2}Z`,fill:i%3?main:light,stroke:INK,'stroke-width':.025,opacity:.8,class:'fx-acid',style:`--phase:${i*.19}s`}));}
 }else if(e.appearance==='healing'){
  for(let i=0;i<16;i++){const x=bounds[0]+(i*41%101)/100*bounds[2],y=bounds[1]+(i*67%97)/96*bounds[3];art.append(svg('path',{d:`M${x-.13} ${y}h.26 M${x} ${y-.13}v.26`,stroke:i%3?main:light,'stroke-width':.06,class:'fx-heal',style:`--phase:${i*.27}s`}));}
 }else if(e.appearance==='shadow'){
  for(let i=0;i<14;i++){const x=bounds[0]+(i*41%101)/100*bounds[2],y=bounds[1]+(i*67%97)/96*bounds[3];art.append(svg('path',{d:`M${x-.3} ${y+.3}Q${x+.7} ${y+.3} ${x+.2} ${y-.2}T${x-.1} ${y-.5}`,fill:'none',stroke:i%3?dark:main,'stroke-width':.09,opacity:.6,class:'fx-shadow',style:`--phase:${i*.3}s`}));}
 }else if(e.appearance==='thunder'){
  for(let i=0;i<4;i++)art.append(svg('ellipse',{cx:radius?0:l/2,cy:0,rx:radius?radius*(.2+i*.23):l*(.15+i*.1),ry:radius?radius*(.2+i*.23):w*(.15+i*.1),fill:'none',stroke:i%2?main:light,'stroke-width':.065,opacity:.55,class:'fx-ripple',style:`--phase:${i*.5}s`}));
 }else if(e.appearance==='transport'){
  for(let i=0;i<16;i++){const y=bounds[1]+i/15*bounds[3];art.append(svg('path',{d:`M${bounds[0]} ${y}h${bounds[2]}`,stroke:i%3?main:light,'stroke-width':.035,opacity:.35,class:'fx-scan',style:`--phase:${i*.1}s`}));}
 }else if(['poison','smoke'].includes(e.appearance)){
  for(let i=0;i<20;i++){const x=bounds[0]+((i*37%101)/100)*bounds[2],y=bounds[1]+((i*61%97)/96)*bounds[3];art.append(svg('circle',{cx:x,cy:y,r:.35+(i%4)*.13,fill:i%3===0?light:main,opacity:.18+(i%3)*.04,class:'fx-mist',style:`--phase:${i*.31}s`}));}
 }else if(e.appearance==='fire'){
  for(let i=0;i<32;i++){const x=bounds[0]+((i*43%103)/102)*bounds[2],y=bounds[1]+((i*29%97)/96)*bounds[3],h=.22+(i%4)*.09;art.append(svg('path',{d:`M${x-.11} ${y+h} Q${x-.17} ${y} ${x+.04} ${y-h} Q${x+.08} ${y+.08} ${x+.16} ${y+h}Z`,fill:i%3===0?light:main,stroke:INK,'stroke-width':.025,opacity:.85,class:'fx-flame',style:`--phase:${i*.17}s`}));}
 }else if(e.appearance==='lightning'){
  for(let j=0;j<3;j++){let path='';for(let i=0;i<=18;i++){const x=bounds[0]+i/18*bounds[2],y=(j-1)*.2+(i===0||i===18?0:((i*7+j)%5-2)*.13);path+=(i?'L':'M')+x+' '+y;}art.append(svg('path',{d:path,fill:'none',stroke:INK,'stroke-width':j===1?.13:.1,'stroke-linejoin':'round',class:'fx-spark',style:`--phase:${j*.4}s`}),svg('path',{d:path,fill:'none',stroke:j===1?light:main,'stroke-width':j===1?.07:.045,class:'fx-spark',style:`--phase:${j*.4}s`}));}
 }else if(e.appearance==='frost'){
  for(let i=0;i<23;i++){const x=bounds[0]+(i*41%101)/100*bounds[2],y=bounds[1]+(i*67%97)/96*bounds[3];art.append(svg('path',{d:`M${x} ${y-.18}L${x+.13} ${y}L${x} ${y+.18}L${x-.13} ${y}Z`,fill:i%2?light:main,stroke:INK,'stroke-width':.022,opacity:.85,class:'fx-glint',style:`--phase:${i*.22}s`}));}
 }else{
  const cx=radius?0:l/2;for(let i=0;i<3;i++)art.append(svg('ellipse',{cx,cy:0,rx:radius?radius*(.3+i*.28):l*(.18+i*.12),ry:radius?radius*(.3+i*.28):w*(.18+i*.12),fill:'none',stroke:i%2?light:main,'stroke-width':.05,opacity:.5,class:'fx-ring',style:`--phase:${i*.7}s`}));
  for(let i=0;i<14;i++){const x=bounds[0]+(i*41%101)/100*bounds[2],y=bounds[1]+(i*67%97)/96*bounds[3];art.append(svg('path',{d:`M${x-.08} ${y}h.16 M${x} ${y-.08}v.16`,stroke:light,'stroke-width':.035,class:'fx-glint',style:`--phase:${i*.2}s`}));}
 }
 if(e.shape==='melee')art.append(svg('path',{d:'M-.4 .25 Q.1 -.7 .4 -.2 M-.2 .4 Q.2 -.4 .5 -.35',fill:'none',stroke:light,'stroke-width':.08,class:'fx-spark'}));
 if(e.shape==='ranged'){
  art.append(svg('circle',{cx:0,cy:0,r:.085,fill:light,class:'fx-projectile',style:`--travel:${l}px`}));
  art.append(svg('circle',{cx:l,cy:0,r:.1,fill:light,class:'fx-glint'}));
 }
 g.append(art);const ink=geom();ink.setAttribute('fill','none');ink.setAttribute('stroke',INK);ink.setAttribute('stroke-width',selected?.15:.1);ink.setAttribute('stroke-linejoin','round');if(preview)ink.setAttribute('stroke-dasharray','.13 .1');g.append(ink);const outline=geom();outline.setAttribute('fill','none');outline.setAttribute('stroke',selected?light:main);outline.setAttribute('stroke-width',selected?.065:.035);if(preview)outline.setAttribute('stroke-dasharray','.13 .1');g.append(outline);
 return g;
}

export function createEffects({getView,send,getSelected,root,mapPoint,svg,notify,redraw,onMode,eventPlayer,renderEvent}){
 const $=id=>document.getElementById(id);let mode='off',selection=null,gesture=null,draft=null;
 const selected=()=>getView()?.effects?.find(e=>e.id===selection);
 const apply=action=>{try{send(action);if(action.kind==='create'){selection=getView().effects.at(-1)?.id;refresh();redraw();}}catch(e){notify(e.message);}};
 const getConfig=()=>{const preset=presets[$('fx-preset').value]??presets.breath,v=getView(),control=$('fx-control').value;
  return {id:'draft',label:preset.label,shape:$('fx-shape').value,appearance:$('fx-appearance').value,origin:[0,0],angle_deg:0,length_ft:Number($('fx-length').value),width_ft:Number($('fx-width').value),radius_ft:Number($('fx-radius').value),source:'player',control,source_actor:control==='attached'?getSelected():null,expires_round:Number($('fx-duration').value)?v.state.round+Number($('fx-duration').value):null};};
 function setMode(next){cancel();mode=next;$('fx-tool').setAttribute('aria-pressed',String(mode!=='off'));root.classList.toggle('effects-editing',mode!=='off');onMode(mode!=='off');refresh();redraw();}
 function cancel(){const g=gesture;gesture=null;draft=null;if(g&&root.hasPointerCapture(g.pointer))root.releasePointerCapture(g.pointer);}
 function drawSwatches(){const gallery=$('fx-gallery');gallery.replaceChildren();for(const [id,p]of Object.entries(presets)){const b=document.createElement('button');b.className='fx-swatch';b.setAttribute('aria-label',`Choose ${p.label}`);b.setAttribute('aria-pressed',String($('fx-preset').value===id));const icon=svg('svg',{viewBox:'-4 -3.6 8 7.2','aria-hidden':true});const directional=['line','cone','rectangle','ranged'].includes(p.shape);icon.append(effectGraphic({...p,id:'swatch-'+id,origin:[directional?-3.5:-.5,-.5],angle_deg:0},svg,{animate:$('fx-animate').checked}));b.append(icon);const text=document.createElement('span');text.textContent=p.label;b.append(text);b.onclick=()=>{$('fx-preset').value=id;choosePreset();};gallery.append(b);}}
 function choosePreset(){const p=presets[$('fx-preset').value]??presets.breath;for(const [id,value] of [['fx-shape',p.shape],['fx-appearance',p.appearance],['fx-length',p.length_ft],['fx-width',p.width_ft],['fx-radius',p.radius_ft]])$(id).value=String(value);drawSwatches();}
 function select(id){selection=id;const e=selected();if(e){for(const [key,value]of [['fx-length',e.length_ft],['fx-width',e.width_ft],['fx-radius',e.radius_ft],['fx-angle',Math.round(e.angle_deg)],['fx-x',e.origin[0]],['fx-y',e.origin[1]]])$(key).value=String(value);}refresh();redraw();}
 function refresh(){const view=getView();if(!view)return;const actors=view.state.combatants.filter(a=>!a.down);for(const [id,side]of [['fx-source','foe'],['fx-target','friend']]){const select=$(id),old=select.value;select.replaceChildren();for(const a of actors){const o=document.createElement('option');o.value=a.id;o.textContent=a.name;select.append(o);}select.value=actors.some(a=>a.id===old)?old:(actors.find(a=>a.side===side)?.id??actors[0]?.id??'');}const effects=view.effects??[];if(!effects.some(e=>e.id===selection))selection=null;
  $('fx-count').textContent=`${effects.length} on the table`;$('fx-instruction').textContent=mode==='place'?'Drag on the map to set origin, direction and size. Click uses the entered size. Escape cancels.':mode==='select'?'Select an effect below or on the map. Drag its centre handle to move, or its aim handle to rotate. Locked effects can only be inspected.':'Effects remain visible during play. Enable Edit effects to manipulate player templates.';
  const recent=$('fx-recent');recent.replaceChildren();for(const event of (view.visual_events??[]).slice(-4).reverse()){const b=document.createElement('button');b.className='fx-item';b.textContent=`↻ ${event.effect.label} · ${event.outcome==='demo'?'test visual':event.outcome}`;b.onclick=()=>apply({kind:'replay',event_id:event.id});recent.append(b);}
  const list=$('fx-list');list.replaceChildren();for(const e of effects){const b=document.createElement('button');b.className='fx-item';b.setAttribute('aria-pressed',String(e.id===selection));b.textContent=`${e.control==='movable'?'◇':'▣'} ${e.label} · ${effectDescription(e)} · ${e.control==='attached'?'follows token':e.control}${e.expires_round?` · ends R${e.expires_round}`:''}`;b.onclick=()=>select(e.id);list.append(b);}
  const e=selected();$('fx-selected').textContent=e?`${e.label} / ${e.source} / ${effectDescription(e)}. ${e.control==='movable'?'Player may reposition.':e.control==='attached'?'Follows its source token; no independent move.':'Origin and direction fixed by the source.'}`:'No effect selected.';
  $('fx-preview-once').disabled=!e;$('fx-remove').disabled=!e||e.source!=='player';$('fx-position').disabled=!e||e.source!=='player'||e.control!=='movable';$('fx-apply').disabled=!e||e.source!=='player'||e.control!=='movable';
 }
 function handleDown(event,e,kind){if(mode==='off'||e.control!=='movable'||e.source!=='player'||event.button!==0)return;event.preventDefault();event.stopPropagation?.();gesture={pointer:event.pointerId,kind,start:mapPoint(root,event),effect:e};draft={...e};root.setPointerCapture(event.pointerId);}
 function draw(){const view=getView();if(!view)return;const layer=svg('g',{'data-layer':'effects','aria-label':'Visual effects'});root.append(layer);
  for(const effect of view.effects??[]){const e=draft?.id===effect.id?draft:effect,g=effectGraphic(e,svg,{selected:e.id===selection,animate:$('fx-animate').checked});
   if(mode==='select'){g.setAttribute('pointer-events','visiblePainted');g.setAttribute('role','button');g.setAttribute('tabindex',0);g.setAttribute('aria-label',`${e.label}, ${e.control}`);g.onpointerdown=event=>{event.stopPropagation?.();select(e.id);};g.onkeydown=event=>{if(event.key==='Enter'){event.preventDefault();select(e.id);}};}layer.append(g);
  }
  if(draft?.id==='draft')layer.append(effectGraphic(draft,svg,{preview:true,animate:$('fx-animate').checked}));
 }
 function handles(){const animationLayer=svg('g',{'data-layer':'one-shot-effects','pointer-events':'none'});root.append(animationLayer);for(const {event,elapsed}of eventPlayer.entries())animationLayer.append(renderEvent(event,svg,{elapsed,animate:$('fx-animate').checked}));const e=draft?.id!=='draft'&&draft?draft:selected();if(mode!=='select'||!e)return;const layer=svg('g',{'data-layer':'effect-handles'});root.append(layer);const color=getComputedStyle(document.body).getPropertyValue('--brass').trim(),x=e.origin[0]+.5,y=e.origin[1]+.5;
  layer.append(svg('text',{x,y:y-.3,'text-anchor':'middle',fill:color,'font-size':.23,stroke:getComputedStyle(document.body).getPropertyValue('--map-floor').trim(),'stroke-width':.05,'paint-order':'stroke','pointer-events':'none'},`${e.control==='movable'?'◇':'▣'} ${effectDescription(e)}`));
  if(e.control!=='movable'||e.source!=='player')return;
  const angle=e.angle_deg*Math.PI/180,distance=e.shape==='circle'?e.radius_ft/5:e.shape==='melee'?1:e.length_ft/5;
  for(const [kind,cx,cy,label] of [['move',x,y,'Drag to move effect'],['rotate',x+Math.cos(angle)*distance,y+Math.sin(angle)*distance,'Drag to rotate effect']]){
   const h=svg('circle',{cx,cy,r:kind==='move'?.17:.13,fill:kind==='move'?color:'var(--panel)',stroke:color,'stroke-width':.05,class:'fx-handle',role:'button',tabindex:0,'aria-label':label});h.append(svg('title',{},label));h.onpointerdown=event=>handleDown(event,e,kind);layer.append(h);
  }
 }
 function down(event){if(mode==='off'||event.button!==0)return false;event.preventDefault();if(mode!=='place')return true;
  let p=mapPoint(root,event);const config=getConfig();if(config.control==='attached'){const actor=getView().state.combatants.find(a=>a.id===config.source_actor);if(actor)p={x:actor.x+.5,y:actor.y+.5};}gesture={pointer:event.pointerId,kind:'place',start:p};draft=aimEffect(config,p,p);root.setPointerCapture(event.pointerId);redraw();return true;
 }
 function move(event){if(!gesture||event.pointerId!==gesture.pointer)return false;event.preventDefault();const p=mapPoint(root,event),g=gesture;
  if(g.kind==='place')draft=aimEffect(getConfig(),g.start,p);
  else if(g.kind==='move')draft={...g.effect,origin:[g.effect.origin[0]+Math.round((p.x-g.start.x)*2)/2,g.effect.origin[1]+Math.round((p.y-g.start.y)*2)/2]};
  else draft={...g.effect,angle_deg:Math.atan2(p.y-g.effect.origin[1]-.5,p.x-g.effect.origin[0]-.5)*180/Math.PI};
  redraw();return true;
 }
 function up(event){if(!gesture||event.pointerId!==gesture.pointer)return false;move(event);const g=gesture,e=draft;cancel();mode='select';
  if(g.kind==='place')apply({kind:'create',effect:e});else apply({kind:'edit',effect_id:e.id,origin:e.origin,angle_deg:e.angle_deg});refresh();redraw();return true;
 }
 $('fx-tool').onclick=()=>setMode(mode==='off'?'select':'off');$('fx-place').onclick=()=>setMode('place');
 $('fx-place-exact').onclick=()=>{setMode('select');apply({kind:'create',effect:{...getConfig(),origin:[Number($('fx-x').value),Number($('fx-y').value)],angle_deg:Number($('fx-angle').value)}});};
 $('fx-preset').onchange=choosePreset;choosePreset();$('fx-control').value='movable';$('fx-duration').value='0';
 $('fx-remove').onclick=()=>{if(selected())apply({kind:'remove',effect_id:selection});};
 $('fx-apply').onclick=()=>{if(selected())apply({kind:'edit',effect_id:selection,length_ft:Number($('fx-length').value),width_ft:Number($('fx-width').value),radius_ft:Number($('fx-radius').value),angle_deg:Number($('fx-angle').value)});};
 $('fx-preview-once').onclick=()=>{const e=selected();if(!e){notify('Select a template to preview.');return;}eventPlayer.preview({id:'local-preview:'+crypto.randomUUID(),effect:e,kind:e.shape==='ranged'?'projectile':e.shape==='melee'?'melee':e.shape==='circle'?'burst':'pulse',duration_ms:1800,outcome:'demo'});};
 $('fx-trigger-preset').onchange=()=>{const trap=$('fx-trigger-preset').value==='trap_flames';$('fx-source').disabled=trap;$('fx-target').disabled=trap;};
 $('fx-trigger').onclick=()=>apply({kind:'trigger',preset:$('fx-trigger-preset').value,...($('fx-source').value?{source_actor:$('fx-source').value}:{}),...($('fx-target').value?{target_actor:$('fx-target').value}:{})});$('fx-clear-triggers').onclick=()=>{eventPlayer.clear();apply({kind:'clear_triggers'});};$('fx-stop-visuals').onclick=()=>{eventPlayer.clear();redraw();};$('fx-animate').onchange=()=>{drawSwatches();redraw();};
 // Keyboard and exact-coordinate access without dragging a handle.
 $('fx-position').onclick=()=>{if(selected())apply({kind:'edit',effect_id:selection,origin:[Number($('fx-x').value),Number($('fx-y').value)]});};
 return {draw,handles,refresh,down,move,up,cancel,get active(){return mode!=='off';},get placing(){return mode==='place';},get dragging(){return !!gesture;},edit:()=>setMode('select'),exit:()=>setMode('off'),escape(){if(gesture){cancel();redraw();}else if(mode!=='off')setMode('off');},onUpdate(next,{silent=false}={}){cancel();eventPlayer.ingest(next.visual_events??[],{silent:silent||!getView()});refresh();}};
}
