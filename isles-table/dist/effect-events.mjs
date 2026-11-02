import {effectGraphic,palettes} from './effects.mjs';
import {INK_HEX as INK} from './world-style.mjs';
// 2026-10-20 (GM: cartoon effects): a hit is a comic star (bigger for a critical), a miss a swoosh with puffs, captions inked.
const star=(r,inner,n=10)=>Array.from({length:n*2},(_,i)=>{const a=i*Math.PI/n-Math.PI/2,k=i%2?inner:r;return `${(Math.cos(a)*k).toFixed(3)},${(Math.sin(a)*k).toFixed(3)}`;}).join(' ');
// A bounded presentation queue. Browser time removes pictures, never game effects.
export function createVisualQueue({now=()=>performance.now(),schedule=setTimeout,unschedule=clearTimeout,onChange=()=>{}}={}){
 const active=new Map(),seen=new Set();let primed=false;
 function clear(){for(const v of active.values())unschedule(v.timer);active.clear();}
 function play(event){if(active.size>=8){const first=active.keys().next().value;unschedule(active.get(first).timer);active.delete(first);}
  const item={event,start:now(),timer:null};active.set(event.id,item);item.timer=schedule(()=>{active.delete(event.id);onChange();},event.duration_ms);}
 return {ingest(events,{silent=false}={}){if(!primed||silent||!events.length){clear();if(silent||!events.length)seen.clear();for(const e of events)seen.add(e.id);primed=true;return;}
   for(const event of events){if(seen.has(event.id))continue;seen.add(event.id);play(event);}while(seen.size>256)seen.delete(seen.values().next().value);},
  preview(event){play(event);onChange();},clear,
  entries(){const time=now();return [...active.values()].filter(v=>time-v.start<v.event.duration_ms).map(v=>({event:v.event,elapsed:time-v.start}));}
 };
}
export function visualGraphic(event,svg,{elapsed=0,animate=true,resolveToken=()=>null}={}){
 const e=event.effect,l=e.length_ft/5;
 const g=svg('g',{'data-visual-event':event.id,class:`vfx-event ${animate?'':'fx-still'}`,'pointer-events':'none',style:`--elapsed:${-elapsed/1000}s;--life:${event.duration_ms/1000}s`,transform:`translate(${e.origin[0]+.5} ${e.origin[1]+.5}) rotate(${e.angle_deg})`});
 const [color,light]=palettes[e.appearance]??palettes.arcane;
 const impact=(x,y,delay=0)=>{const group=svg('g',{transform:`translate(${x} ${y})`,style:`--impact-delay:calc(${delay}s + var(--elapsed))`});
  if(event.outcome==='miss'){
   group.append(svg('path',{d:'M-.55 .3 Q0 -.65 .6 -.2',fill:'none',stroke:INK,'stroke-width':.14,'stroke-linecap':'round',class:'vfx-slash'}),svg('path',{d:'M-.55 .3 Q0 -.65 .6 -.2',fill:'none',stroke:light,'stroke-width':.07,'stroke-linecap':'round',class:'vfx-slash'}));
   for(const [px,py,pr]of [[.62,-.12,.11],[.78,.06,.08],[.5,.06,.07]])group.append(svg('circle',{cx:px,cy:py,r:pr,fill:light,'fill-opacity':.7,stroke:INK,'stroke-width':.025,class:'vfx-puff vfx-shock'}));
  }else{
   const size=event.outcome==='critical'?.85:.55;
   group.append(svg('polygon',{points:star(size,size*.52),fill:light,stroke:INK,'stroke-width':.05,'stroke-linejoin':'round',class:'vfx-star vfx-shock'}),svg('polygon',{points:star(size*.6,size*.32),fill:color,class:'vfx-shock'}));
   for(let i=0;i<8;i++){const a=i*Math.PI/4,x1=Math.cos(a)*.15,y1=Math.sin(a)*.15,x2=Math.cos(a)*size,y2=Math.sin(a)*size;group.append(svg('path',{d:`M${x1} ${y1}L${x2} ${y2}`,stroke:light,'stroke-width':i%2?.035:.07,class:'vfx-shock'}));}
   group.append(svg('path',{d:'M-.55 .35 Q-.1 -.6 .55 -.3 M-.3 .55 Q.1 -.2 .55 -.5',fill:'none',stroke:light,'stroke-width':.09,class:'vfx-slash'}));
  }
  const label=event.outcome==='critical'?'CRIT!':event.outcome==='miss'?'MISS':event.outcome==='hit'?'HIT':'';
  if(label)group.append(svg('text',{x:0,y:-.65,transform:`rotate(${-e.angle_deg})`,'text-anchor':'middle','font-size':.26,'font-weight':700,fill:light,stroke:INK,'stroke-width':.07,'paint-order':'stroke','stroke-linejoin':'round',class:'vfx-caption'},label));
  return group;
 };
 if(event.kind==='teleport'){
  const destination=event.target_origin??e.origin,dx=destination[0]-e.origin[0],dy=destination[1]-e.origin[1],token=resolveToken(event.token_id),size=token?.squares??e.length_ft/5;
  const maskId='transport-mask-'+event.id.replace(/[^a-zA-Z0-9_-]/g,'');
  const defs=svg('defs'),mask=svg('mask',{id:maskId,maskUnits:'userSpaceOnUse',x:-size/2-.2,y:-size/2-.2,width:size+.4,height:size+.4,style:'mask-type:alpha'});
  if(token)mask.append(svg('image',{href:token.path,x:-size/2,y:-size/2,width:size,height:size,preserveAspectRatio:'xMidYMid meet'}));else mask.append(svg('path',{d:`M0 ${-size/2}L${size/2} 0L0 ${size/2}L${-size/2} 0Z`,fill:'white'}));defs.append(mask);g.append(defs);
  for(const [x,y,arrival]of [[0,0,false],[dx,dy,true]]){
   const pad=svg('g',{transform:`translate(${x} ${y})`});
   pad.append(svg('ellipse',{cx:0,cy:size*.5,rx:size*.65,ry:size*.18,fill:color,'fill-opacity':.1,stroke:color,'stroke-width':.05,class:'vfx-transport-pad'}));
   const silhouette=svg('g',{class:arrival?'vfx-transport-in':'vfx-transport-out'});
   if(arrival&&token)silhouette.append(svg('image',{href:token.path,x:-size/2,y:-size/2,width:size,height:size,preserveAspectRatio:'xMidYMid meet',opacity:.65}));
   const shimmer=svg('g',{mask:`url(#${maskId})`});shimmer.append(svg('rect',{x:-size/2,y:-size/2,width:size,height:size,fill:color,opacity:.25}));
   for(let i=0;i<20;i++){const y=-size/2+i/19*size;shimmer.append(svg('path',{d:`M${-size/2} ${y}h${size}`,stroke:i%3?color:light,'stroke-width':size*.035,opacity:.7,class:'fx-scan',style:`--phase:${i*.12}s`}));}
   silhouette.append(shimmer);for(let i=0;i<18;i++){const x=(i*37%101)/100*size-size/2,y=(i*61%97)/96*size-size/2;silhouette.append(svg('path',{d:`M${x-.04} ${y}h.08M${x} ${y-.04}v.08`,stroke:light,'stroke-width':.025,class:'fx-glint',style:`--phase:${i*.17}s`}));}pad.append(silhouette);g.append(pad);
  }
 }else if(event.kind==='projectile'){
  g.append(svg('path',{d:`M0 0H${l}`,stroke:color,'stroke-width':.04,opacity:.3,class:'vfx-trail'}));
  const flight=svg('g',{class:'vfx-flight',style:`--travel:${l}px`});flight.append(svg('path',{d:'M-.65 0L-.18 -.08L.1 0L-.18 .08Z',fill:color,opacity:.7}),svg('circle',{cx:0,cy:0,r:.1,fill:light}));g.append(flight,impact(l,0,.65));
 }else if(event.kind==='melee')g.append(impact(0,0));
 else if(event.kind==='burst'){
  g.append(svg('circle',{cx:0,cy:0,r:e.radius_ft/5,fill:'none',stroke:INK,'stroke-width':.12,class:'vfx-burst',style:'--impact-delay:var(--elapsed)'}));
  for(let i=0;i<3;i++){const ring=svg('circle',{cx:0,cy:0,r:e.radius_ft/5*(1-i*.16),fill:i===0?color:'none','fill-opacity':.08,stroke:i===1?light:color,'stroke-width':.06,class:'vfx-burst',style:`--impact-delay:calc(${i*.12}s + var(--elapsed))`});g.append(ring);}
  for(let i=0;i<12;i++){const a=i*Math.PI/6,r=e.radius_ft/5;g.append(svg('path',{d:`M${Math.cos(a)*r*.25} ${Math.sin(a)*r*.25}L${Math.cos(a)*r*.8} ${Math.sin(a)*r*.8}`,stroke:light,'stroke-width':.04,class:'vfx-burst',style:'--impact-delay:var(--elapsed)'}));}
 }else{
  // Reuse the exact template art while the event envelope fades once.
  const local={...e,id:event.id,origin:[-.5,-.5],angle_deg:0};const art=effectGraphic(local,svg,{animate});art.setAttribute('class',`fx-art vfx-envelope ${animate?'':'fx-still'}`);g.append(art);
 }
 return g;
}
