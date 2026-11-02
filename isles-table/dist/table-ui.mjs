// Disclosure controls use a normal tap. Alternate mouse gestures are optional.
export function createTableUI({done,editEffects,getCamera=()=>false,getMode=()=> 'move'}){
 const $=id=>document.getElementById(id);let menu=null,tab='place';
 const groups=[['session-toggle','session-menu'],['view-toggle','view-menu']];
 function closeMenus({focus=false}={}){const old=menu;menu=null;for(const [button,panel]of groups){$(panel).hidden=true;$(button).setAttribute('aria-expanded','false');}if(focus&&old)$(old).focus();}
 function openMenu(button,panel,force=false){const opening=force||menu!==button;closeMenus();if(!opening)return;menu=button;$(panel).hidden=false;$(button).setAttribute('aria-expanded','true');$(button==='session-toggle'?'save':'grid').focus();}
 function bindDisclosure(id,open){const b=$(id);b.onclick=()=>open(false);b.oncontextmenu=e=>{e.preventDefault();open(true);};b.ondblclick=e=>{e.preventDefault();open(true);};}
 for(const [button,panel]of groups)bindDisclosure(button,force=>openMenu(button,panel,force));
 function closeEffects({focus=false}={}){$('effects-tray').hidden=true;$('effects-toggle').setAttribute('aria-expanded','false');if(focus)$('effects-toggle').focus();}
 function showTab(name,{focus=false}={}){tab=name;for(const key of ['place','map','test']){const b=$('effects-tab-'+key),active=key===name;b.setAttribute('aria-selected',String(active));b.setAttribute('tabindex',active?'0':'-1');$('effects-pane-'+key).hidden=!active;}if(focus)$('effects-tab-'+name).focus();}
 function openEffects(force=false){const opening=force||$('effects-tray').hidden;closeMenus();if(!opening){closeEffects();return;}$('effects-tray').hidden=false;$('effects-toggle').setAttribute('aria-expanded','true');showTab(tab,{focus:true});}
 bindDisclosure('effects-toggle',openEffects);$('effects-close').onclick=()=>closeEffects({focus:true});
 for(const name of ['place','map','test'])$('effects-tab-'+name).onclick=()=>showTab(name);
 function sync(){const mode=getMode(),moving=mode==='move';$('pointer-tool').setAttribute('aria-pressed',String(moving));$('effects-toggle').setAttribute('data-active',String(mode.includes('effects')));$('tool-done').hidden=moving;$('mode-hint').textContent=mode==='measure'?'Measure: drag a ruler · Escape clears':mode==='place-effects'?'Place effect: drag to position and aim':mode==='effects'?'Effects: select a template, then drag its handles':getCamera()?'Drag to orbit · tap highlighted ground to move':'Drag a token to move · tap to inspect';}
 const finish=()=>{done();closeMenus();closeEffects();sync();};$('pointer-tool').onclick=finish;$('tool-done').onclick=finish;
 function wrap(id,after){const original=$(id).onclick;$(id).onclick=e=>{original?.(e);after();};}
 for(const id of ['save','load','export','new'])wrap(id,()=>closeMenus());
 for(const id of ['library','about','rules'])wrap(id,()=>{closeMenus();closeEffects();});
 wrap('measure',()=>{closeMenus();closeEffects();sync();});
 wrap('fx-place',()=>{closeEffects();sync();});
 $('fx-tool').onclick=()=>{editEffects();closeEffects();sync();};
 $('fx-configure-selected').onclick=()=>{showTab('place');$('fx-custom').open=true;$('fx-custom').scrollIntoView?.({block:'nearest',behavior:'smooth'});};
 $('fx-angle-apply').onclick=()=>{if(!$('fx-apply').disabled)$('fx-apply').click();};
 document.addEventListener('pointerdown',e=>{if(!menu)return;const group=groups.find(([button])=>button===menu);if(group&&!$(group[0]).contains(e.target)&&!$(group[1]).contains(e.target))closeMenus();});
 function handleKey(e){
  if(e.key==='Escape'){if(menu){e.preventDefault();closeMenus({focus:true});return true;}if(!$('effects-tray').hidden){e.preventDefault();closeEffects({focus:true});return true;}return false;}
  const names=['place','map','test'];if(e.target?.id?.startsWith('effects-tab-')&&['ArrowLeft','ArrowRight','Home','End'].includes(e.key)){e.preventDefault();const i=names.indexOf(tab),next=e.key==='Home'?0:e.key==='End'?2:(i+(e.key==='ArrowRight'?1:2))%3;showTab(names[next],{focus:true});return true;}
  // Disclosure forms retain native editing/navigation; do not move a token behind them.
  return !!menu||!$('effects-tray').hidden;
 }
 closeMenus();closeEffects();showTab('place');sync();
 return {sync,handleKey,closeMenus,closeEffects,showTab};
}
