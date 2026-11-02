import {xml2js} from './vendor/xml-js/xml.mjs';
export const ABILITIES=['str','dex','con','int','wis','cha'];
const full=['strength','dexterity','constitution','intelligence','wisdom','charisma'];
const key=s=>String(s).toLowerCase().replace(/[^a-z0-9]/g,'');
export const blankCharacter=()=>({format:'isles-character/1',id:globalThis.crypto.randomUUID(),name:'',kind:'pc',ruleset:'Unconfirmed',species:'',background:'',classes:[],abilities:Object.fromEntries(ABILITIES.map(k=>[k,null])),proficiencies:[],feats:[],features:[],spells:[],equipment:[],notes:'',token_id:'',space_ft:5,combat:{hp_max:null,ac:null,speed:null,attack_bonus:null,damage_count:1,damage_die:null,damage_bonus:null,reach:5},warnings:[],provenance:{kind:'manual',fields:{}}});
const aliases={name:['charactername','charname','name'],species:['species','race','ancestry'],background:['background'],class:['classlevel','classandlevel','classname','class'],level:['characterlevel','totallevel','level'],hp_max:['hitpointsmaximum','hitpointmaximum','maximumhitpoints','hpmax','maxhp','hpmaximum','hitpointstotal','hptotal','hitpoints','hp'],ac:['armorclass','armourclass','armorclasstotal','ac','actotal'],speed:['walkingspeed','walkspeed','speedtotal','speedbase','speed'],attack_bonus:['attackbonus','tohit','attackmod','atkbonus'],damage_die:['damagedie','damagedice','damage'],damage_bonus:['damagebonus','damagemod'],reach:['reach'],feats:['feats','feat'],proficiencies:['proficiencies','skillproficiencies','skills'],features:['features','traits','featuresandtraits'],spells:['spells','spellsknown','preparedspells'],equipment:['equipment','inventory','gear'],notes:['notes','backstory','personalitytraits'],ruleset:['ruleset','rulesversion','edition']};
const asNumber=s=>{const v=String(s??'').trim();return /^[+-]?\d+(?:\.\d+)?(?:\s*(?:feet|ft\.?))?$/.test(v)?Number.parseFloat(v):null;};
const list=s=>String(s??'').split(/[;\n]/).map(v=>v.trim()).filter(Boolean);
export function fromFields(fields,source,raw=''){
 const c=blankCharacter();c.provenance={kind:source,fields:{},raw:raw.slice(0,80000),truncated:raw.length>80000};const entries=fields.map(([k,v])=>({path:k,key:key(k),leaf:key(k.split(/[./]/).at(-1)),value:String(v??'').trim()})).filter(e=>e.value);
 function find(names){for(const n of names){let e=entries.find(e=>e.key===n);if(e)return e;}for(const n of names){let e=entries.find(e=>e.key.endsWith(n));if(e)return e;}return null;}
 function read(field,names=aliases[field]){const e=find(names);if(e)c.provenance.fields[field]={path:e.path,value:e.value,status:'extracted — verify'};return e?.value;}
 for(const f of ['name','species','background','ruleset']){const v=read(f);if(v)c[f]=v;}
 const cl=read('class'),lev=read('level');if(cl)c.classes=cl.split('/').map(s=>{const m=s.trim().match(/^(.*?)(?:\s+(\d+))?$/);return {name:m[1],level:asNumber(lev)??(m[2]?+m[2]:null)};});
 for(let i=0;i<6;i++){const a=ABILITIES[i],n=full[i];c.abilities[a]=asNumber(read('ability_'+a,[n+'score','abilities'+n+'score',a+'score',n,a]));}
 for(const f of ['hp_max','ac','speed','attack_bonus','damage_bonus','reach']){const v=asNumber(read(f));if(v!==null)c.combat[f]=v;}
 const dmg=read('damage_die');if(dmg){const m=dmg.match(/^(\d+)d(\d+)(?:\s*([+-])\s*(\d+))?(?:\s+[a-z]+)?$/i);if(m){c.combat.damage_count=+m[1];c.combat.damage_die=+m[2];if(m[3])c.combat.damage_bonus=(m[3]==='-'?-1:1)*+m[4];}else{c.combat.damage_die=asNumber(dmg);}}
 for(const f of ['proficiencies','feats','features','spells','equipment']){const v=read(f);if(v)c[f]=list(v);}
 c.notes=read('notes')??'';
 c.warnings=['Imported values need review. Unrecognized source fields remain in the source extract.','Spells, feats and class features are stored as sheet information; they do not add rules to the prototype.'];
 const missing=['hp_max','ac','speed','attack_bonus','damage_die','damage_bonus'].filter(k=>c.combat[k]===null);if(missing.length)c.warnings.push('Missing combat fields: '+missing.join(', ')+'.');if(c.provenance.truncated)c.warnings.push('Source extract exceeded 80,000 characters and was truncated. Keep your original file.');return c;
}
export function parseXML(text){
 if(text.length>2_000_000)throw Error('XML exceeds 2 MB. Export a single character.');if(/<!DOCTYPE|<!ENTITY/i.test(text))throw Error('XML DTDs and custom entities are not accepted. Export plain character XML.');
 let doc;try{doc=xml2js(text,{compact:false,ignoreComment:true,ignoreDeclaration:true});}catch{throw Error('The XML is malformed. Please export the character again.');}
 let candidates=[];let count=0;
 const getText=n=>(n.elements??[]).map(e=>e.text??e.cdata??getText(e)).join(' ').trim();
 function walk(n,parent='',depth=0){if(depth>60||++count>50000)throw Error('XML nesting or element count exceeds the import limit.');if(n.type==='element'&&(['character','npc','monster'].includes(n.name?.toLowerCase())||(['charsheet','npclist'].includes(parent)&&/^id-/.test(n.name))))candidates.push(n);else for(const e of n.elements??[])walk(e,n.name??'',depth+1);}
 walk(doc);if(!candidates.length)candidates=doc.elements?.filter(n=>n.type==='element')??[];if(!candidates.length)throw Error('No character records found in XML.');
 return candidates.slice(0,100).map(n=>{const fields=[];function flatten(node,path='',depth=0){if(depth>60)throw Error('XML is nested too deeply.');const els=(node.elements??[]).filter(e=>e.type==='element');const next=path?path+'.'+node.name:node.name;if(!els.length){const t=getText(node);if(t)fields.push([next,t]);}else{for(const el of els)flatten(el,next,depth+1);}}flatten(n);const c=fromFields(fields,'XML',fields.map(([k,v])=>k+': '+v).join('\n'));if(['npc','monster'].includes(n.name))c.kind='npc';// Preserve useful nested FG list entries without pretending to interpret their mechanics.
 for(const [tag,f]of [['featlist','feats'],['specialabilitylist','features'],['inventorylist','equipment'],['spellset','spells']]){const named=fields.filter(([p])=>p.includes(tag)&&/\.name$/.test(p)).map(([,v])=>v);if(named.length)c[f]=named;}
 const cls=fields.filter(([p])=>/classes\.[^.]+\.name$/.test(p)).map(([p,v])=>({name:v,level:asNumber(fields.find(([q])=>q===p.replace(/\.name$/,'.level'))?.[1])}));if(cls.length)c.classes=cls;
 Object.defineProperty(c,'_fields',{value:fields,enumerable:false});// CHARACTERS-01: character-formats.mjs hardenFG reads the FG fields again
 return c;});
}
export function parseDelimited(text,delimiter){
 if(text.length>2_000_000)throw Error('Spreadsheet exceeds 2 MB. Export the character tab only.');text=text.replace(/^\uFEFF/,'');delimiter??=(text.split(/\r?\n/,1)[0].includes('\t')?'\t':',');let rows=[],row=[],v='',quoted=false;
 for(let i=0;i<text.length;i++){const ch=text[i];if(ch==='"'){if(quoted&&text[i+1]==='"'){v+='"';i++;}else if(quoted)quoted=false;else if(!v)quoted=true;else v+=ch;}else if(ch===delimiter&&!quoted){row.push(v);v='';}else if((ch==='\n'||ch==='\r')&&!quoted){if(ch==='\r'&&text[i+1]==='\n')i++;row.push(v);if(row.some(s=>s.trim()))rows.push(row);row=[];v='';}else v+=ch;}if(quoted)throw Error('Unclosed quoted cell in the spreadsheet.');row.push(v);if(row.some(s=>s.trim()))rows.push(row);if(rows.length>5000)throw Error('Too many spreadsheet rows.');return rows;
}
export function parseSheet(text){const rows=parseDelimited(text);if(!rows.length)throw Error('No spreadsheet cells found.');const wide=rows[0].length>2||rows[0].some(v=>['charactername','charname','name'].includes(key(v)))&&rows[0].some(v=>['ac','armorclass','class','hpmax'].includes(key(v)));if(wide)return rows.slice(1,101).filter(r=>r.some(Boolean)).map(r=>fromFields(rows[0].map((h,i)=>[h,r[i]??'']),'Spreadsheet',JSON.stringify({headers:rows[0],row:r})));return [fromFields(rows.filter(r=>r.length>=2).map(r=>[r[0],r.slice(1).join(' ')]),'Spreadsheet',text)];}
export function parseText(text){
 if(text.length>2_000_000)throw Error('Extract exceeds 2 MB.');const fields=[];for(const line of text.split(/[\r\n]+/)){const m=line.match(/^\s*([\w ()/-]{2,40})\s*[:=\t]\s*(.+)$/);if(m)fields.push([m[1],m[2]]);}
 const c=fromFields(fields,'PDF / text',text);c.warnings.unshift('PDF text layout varies. Check every extracted value against the original sheet.');return [c];
}
// CHARACTERS-01 (GM 2026-10-22: "the import character sheet pdf from dnd beyond doesn't read the file"): D&D Beyond's PDF
// export keeps its fields as widgets on the pages but has no AcroForm, so pdf.js lists no form fields; they are read from
// each page's annotations instead, in getFieldObjects' shape ({name: [{value, rect, page}]}).
async function widgetFields(pdf){const out={};for(let n=1;n<=pdf.numPages;n++){const page=await pdf.getPage(n);for(const a of await page.getAnnotations()){if(a.subtype!=='Widget'||!a.fieldName)continue;(out[a.fieldName]??=[]).push({value:a.fieldValue??'',rect:a.rect,page:n-1,type:a.fieldType});}page.cleanup();}return out;}
// CHARACTERS-01: hook(pdfjs, pdf, form) runs while the document is open (pictures, a known sheet's fields); its answer is c._pdf
export async function parsePDF(bytes,hook=null){
 if(bytes.byteLength>20_000_000)throw Error('PDF exceeds 20 MB. Export just the character sheet.');const pdfjs=await import('./vendor/pdfjs/pdf.mjs');pdfjs.GlobalWorkerOptions.workerSrc=new URL('./vendor/pdfjs/pdf.worker.mjs',import.meta.url).href;
 const task=pdfjs.getDocument({data:new Uint8Array(bytes),isEvalSupported:false,useSystemFonts:true});let pdf;
 try{pdf=await task.promise;if(pdf.numPages>30)throw Error('PDF has more than 30 pages. Export just the character sheet.');let form=await pdf.getFieldObjects();if(!form||!Object.keys(form).length)form=await widgetFields(pdf);const fields=[];for(const [name,items]of Object.entries(form??{})){const item=items.find(i=>i.value!==undefined&&i.value!==null&&i.value!=='');if(item)fields.push([name,Array.isArray(item.value)?item.value.join('; '):item.value]);}
 let lines=[];for(let n=1;n<=pdf.numPages;n++){const page=await pdf.getPage(n),content=await page.getTextContent();let lastY=null,line='';for(const item of content.items){if(!('str'in item))continue;const y=Math.round(item.transform[5]);if(lastY!==null&&Math.abs(lastY-y)>3){lines.push(line);line='';}line+=(line?' ':'')+item.str;lastY=y;if(item.hasEOL){lines.push(line);line='';lastY=null;}}if(line)lines.push(line);page.cleanup();}
 const text=lines.join('\n');if(!text.trim()&&!fields.length)throw Error('This PDF has no readable text or form fields. Use OCR, then import the searchable PDF, or paste sheet values.');const c=parseText(text)[0];if(fields.length){const formC=fromFields(fields,'PDF form',fields.map(([k,v])=>k+': '+v).join('\n')+'\n\n'+text);for(const k of ['name','species','background','classes','ruleset','abilities','combat']){if(typeof formC[k]==='object'&&!Array.isArray(formC[k])){for(const [a,v]of Object.entries(formC[k]))if(v!==null&&v!==undefined&&formC.provenance.fields[a])c[k][a]=v;}else if(formC[k]?.length)c[k]=formC[k];}Object.assign(c.provenance.fields,formC.provenance.fields);c.provenance.raw=formC.provenance.raw;c.provenance.kind='PDF form + text';// Form combat and abilities override text only when the corresponding source key was found.
 for(const a of ABILITIES)if(formC.abilities[a]!==null)c.abilities[a]=formC.abilities[a];for(const a of Object.keys(c.combat))if(formC.combat[a]!==null&&formC.provenance.fields[a])c.combat[a]=formC.combat[a];if(formC.provenance.fields.damage_die){c.combat.damage_count=formC.combat.damage_count;if(/d\d+\s*[+-]/i.test(formC.provenance.fields.damage_die.value))c.combat.damage_bonus=formC.combat.damage_bonus;}}
 if(hook)Object.defineProperty(c,'_pdf',{value:await hook(pdfjs,pdf,form),enumerable:false});
 return [c];}finally{await task.destroy();}
}
export function sheetsCSVURL(input){const u=new URL(input);if(u.protocol!=='https:'||u.hostname!=='docs.google.com')throw Error('Use a docs.google.com spreadsheet URL.');const m=u.pathname.match(/^\/spreadsheets\/d\/([a-zA-Z0-9_-]+)(?:\/|$)/);if(!m)throw Error('Use a standard Google Sheets document link.');const gid=u.searchParams.get('gid')??new URLSearchParams(u.hash.slice(1)).get('gid')??'0';if(!/^\d+$/.test(gid))throw Error('Invalid sheet tab ID.');return `https://docs.google.com/spreadsheets/d/${m[1]}/export?format=csv&gid=${gid}`;}

export function parseCharacterJSON(text){
 if(text.length>2_000_000)throw Error('Character JSON exceeds 2 MB.');const value=JSON.parse(text),rows=value.characters??[value.character??value];
 if(!Array.isArray(rows)||rows.length>100||!rows.length)throw Error('Use an Isles character or character collection JSON export.');
 return rows.map(v=>{if(!v||v.format!=='isles-character/1'||typeof v.name!=='string'||typeof v.combat!=='object'||!v.combat||typeof v.abilities!=='object'||!v.abilities)throw Error('Use an Isles character JSON export.');for(const k of ['classes','proficiencies','feats','features','spells','equipment','warnings'])if(v[k]!==undefined&&!Array.isArray(v[k]))throw Error('Invalid character array: '+k);return {...blankCharacter(),...structuredClone(v),id:crypto.randomUUID()};});
}
