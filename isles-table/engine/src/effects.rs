//! Visual effect records only. These templates do not resolve spell rules or damage.
use super::*;
#[derive(Clone, Serialize, Deserialize, Debug)]
pub struct Effect {
    pub id: String, pub label: String, pub shape: String, pub appearance: String,
    pub origin: [f64;2], pub angle_deg: f64,
    pub length_ft: f64, pub width_ft: f64, pub radius_ft: f64,
    pub source: String, pub control: String, pub source_actor: Option<String>,
    pub expires_round: Option<u32>,
}
#[derive(Clone, Serialize, Deserialize, Debug)]
pub struct VisualEvent {
    pub id: String, pub kind: String, pub effect: Effect,
    pub outcome: String, pub duration_ms: u32,
    #[serde(default)] pub target_origin: Option<[f64;2]>,
    #[serde(default)] pub token_id: Option<String>,
}
impl Game {
    pub fn record_visual(&mut self, event: VisualEvent) {
        self.visual_events.push(event);
        if self.visual_events.len()>24 {self.visual_events.remove(0);}
    }
    pub fn validate_visual(&self,e:&VisualEvent)->Result<(),String>{
        self.validate_effect(&e.effect)?;
        if e.target_origin.map(|p|!p.iter().all(|n|n.is_finite())||p[0]< -0.5||p[1]< -0.5||p[0]>self.map.cols as f64-0.5||p[1]>self.map.rows as f64-0.5).unwrap_or(false)
            || e.token_id.as_ref().map(|id|!tokens().iter().any(|t|&t.id==id)).unwrap_or(false)
            || (e.kind=="teleport"&&(e.target_origin.is_none()||e.token_id.is_none())) {return Err("Invalid visual destination or token".into());}

        if e.id.is_empty() || e.id.len()>160 || !["projectile","melee","burst","breath","pulse","teleport"].contains(&e.kind.as_str()) || !["hit","miss","critical","demo"].contains(&e.outcome.as_str()) || !(300..=6000).contains(&e.duration_ms) || e.effect.control!="fixed" {return Err("Invalid visual event".into());} Ok(())
    }

    pub fn resolved_effects(&self)->Vec<Effect> {
        self.effects.iter().filter(|e|e.expires_round.map(|r|r>self.round).unwrap_or(true)).map(|e|{
            let mut e=e.clone();
            if e.control=="attached" {if let Some(a)=self.actors.iter().find(|a|Some(&a.id)==e.source_actor.as_ref()){e.origin=[a.x,a.y];}}
            e
        }).collect()
    }
    pub fn validate_effect(&self,e:&Effect)->Result<(),String>{
        if e.id.is_empty() || e.id.len()>100 || e.label.is_empty() || e.label.len()>100
            || !["line","cone","circle","rectangle","ranged","melee"].contains(&e.shape.as_str())
            || !["fire","frost","lightning","poison","smoke","arcane","physical","radiant","acid","thunder","healing","shadow","transport"].contains(&e.appearance.as_str())
            || !["player","npc","trap","spell"].contains(&e.source.as_str())
            || !["movable","fixed","attached"].contains(&e.control.as_str())
            || (e.source!="player" && e.control=="movable")
            || !e.origin.iter().all(|v|v.is_finite()) || !e.angle_deg.is_finite() || e.angle_deg.abs()>36000.
            || e.origin[0]< -0.5 || e.origin[1]< -0.5 || e.origin[0]>self.map.cols as f64-0.5 || e.origin[1]>self.map.rows as f64-0.5
            || ![e.length_ft,e.width_ft,e.radius_ft].iter().all(|v|v.is_finite()&&*v>=5.&&*v<=120.)
            || (e.control=="attached" && !self.actors.iter().any(|a|Some(&a.id)==e.source_actor.as_ref())) {
            return Err("Invalid effect geometry or placement policy".into());
        } Ok(())
    }
    pub fn effect_command(&mut self,id:&str,revision:u32,action:&Value)->Result<(),String>{
        let payload=json!(["effect",revision,action]);
        if let Some((_,old))=self.commands.iter().find(|(k,_)|k==id){return if *old==payload {Ok(())}else{Err("Command id reused with different content".into())};}
        if id.is_empty() || id.len()>100 || revision!=self.revision {return Err("Invalid command id or stale state".into());}
        let mut next=self.effects.clone();next.retain(|e|e.expires_round.map(|r|r>self.round).unwrap_or(true));
        let mut emitted=vec![];
        let kind=action["kind"].as_str().unwrap_or("");
        let line=match kind {
            "create"=>{
                if next.len()>=40{return Err("At most 40 active effects".into());}
                let mut e:Effect=serde_json::from_value(action["effect"].clone()).map_err(|_|"Incomplete effect")?;
                e.id=format!("fx:{}",id);e.source="player".into();
                if next.iter().any(|old|old.id==e.id){return Err("Effect id already exists".into());}
                self.validate_effect(&e)?;
                if e.expires_round.map(|r|r<=self.round || r>self.round+100).unwrap_or(false){return Err("Invalid effect duration".into());}
                let line=format!("Visual template placed: {} ({}).",e.label,e.control);next.push(e);line
            }
            "edit"|"remove"=>{
                let index=next.iter().position(|e|Some(e.id.as_str())==action["effect_id"].as_str()).ok_or("Unknown effect")?;
                let old=&next[index];
                if old.source!="player" || (kind=="edit"&&old.control!="movable"){return Err("Effect is engine-fixed; repositioning is not permitted".into());}
                if kind=="remove" {next.remove(index);"Player visual template removed.".into()}else{
                    let mut e=old.clone();
                    if let Some(v)=action.get("origin"){e.origin=serde_json::from_value(v.clone()).map_err(|_|"Invalid origin")?;}
                    for (name,value) in [("angle_deg",&mut e.angle_deg),("length_ft",&mut e.length_ft),("width_ft",&mut e.width_ft),("radius_ft",&mut e.radius_ft)] {
                        if let Some(v)=action.get(name){*value=v.as_f64().ok_or("Invalid dimension")?;}
                    }
                    self.validate_effect(&e)?;next[index]=e;"Player visual template repositioned.".into()
                }
            }
            "trigger"=>{
                let preset=action["preset"].as_str().unwrap_or("");
                let foe=if let Some(id)=action.get("source_actor"){self.actors.iter().find(|a|Some(a.id.as_str())==id.as_str()&&a.hp>0).ok_or("Unknown or defeated source")?}else{self.actors.iter().find(|a|a.side=="foe"&&a.hp>0).or_else(||self.actors.iter().find(|a|a.hp>0)).ok_or("No living source")?};
                let target=if let Some(id)=action.get("target_actor"){self.actors.iter().find(|a|Some(a.id.as_str())==id.as_str()&&a.hp>0).ok_or("Unknown or defeated target")?}else{self.actors.iter().find(|a|a.side=="friend"&&a.hp>0).or_else(||self.actors.iter().find(|a|a.hp>0)).ok_or("No living target")?};
                if ["ranged_hit","npc_breath","acid_jet","transport"].contains(&preset)&&foe.id==target.id{return Err("Choose different source and target combatants for this visual".into());}
                let aim=(target.y-foe.y).atan2(target.x-foe.x).to_degrees();
                let mut e=Effect{id:format!("fx:{}",id),label:String::new(),shape:"circle".into(),appearance:"arcane".into(),origin:[target.x,target.y],angle_deg:aim,length_ft:30.,width_ft:5.,radius_ft:10.,source:"spell".into(),control:"fixed".into(),source_actor:Some(foe.id.clone()),expires_round:Some(self.round+2)};
                match preset {
                    "npc_breath"=>{e.label="Burning breath preview".into();e.shape="cone".into();e.appearance="fire".into();e.origin=[foe.x,foe.y];e.source=if foe.side=="foe"{"npc".into()}else{"player".into()};e.expires_round=Some(self.round+1);}
                    "trap_flames"=>{e.label="Trap · flame jet".into();e.shape="rectangle".into();e.appearance="fire".into();e.origin=[8.,2.];e.angle_deg=90.;e.length_ft=20.;e.width_ft=10.;e.source="trap".into();e.source_actor=None;}
                    "spell_cloud"=>{e.label="Spell · lingering venom".into();e.appearance="poison".into();e.radius_ft=15.;e.expires_round=Some(self.round+3);}
                    "spell_blast"=>{e.label="Spell · frost burst".into();e.appearance="frost".into();e.radius_ft=10.;e.expires_round=Some(self.round+1);}
                    "spell_aura"=>{e.label="Spell · following ward".into();e.appearance="radiant".into();e.control="attached".into();e.source_actor=Some(target.id.clone());e.expires_round=Some(self.round+3);}
                    "ranged_hit"=>{e.label="Lightning bolt preview".into();e.shape="ranged".into();e.appearance="lightning".into();e.origin=[foe.x,foe.y];e.length_ft=((target.x-foe.x).hypot(target.y-foe.y)*5.).clamp(5.,120.);e.source=if foe.side=="foe"{"npc".into()}else{"player".into()};e.expires_round=Some(self.round+1);}
                    "melee_hit"=>{e.label="Melee impact preview".into();e.shape="melee".into();e.appearance="physical".into();e.length_ft=5.;e.radius_ft=5.;e.source=if foe.side=="foe"{"npc".into()}else{"player".into()};e.expires_round=Some(self.round+1);}
                    "acid_jet"=>{e.label="Acid jet preview".into();e.shape="line".into();e.appearance="acid".into();e.origin=[foe.x,foe.y];e.width_ft=5.;e.length_ft=30.;}
                    "thunder_burst"=>{e.label="Thunder pulse preview".into();e.appearance="thunder".into();e.radius_ft=10.;e.angle_deg=0.;}
                    "healing_pulse"=>{e.label="Healing light preview".into();e.appearance="healing".into();e.radius_ft=5.;e.angle_deg=0.;}
                    "shadow_cloud"=>{e.label="Spell · clinging shadow".into();e.appearance="shadow".into();e.radius_ft=10.;e.expires_round=Some(self.round+3);}
                    "transport"=>{e.label="Transporter shimmer · visual only".into();e.appearance="transport".into();e.origin=[foe.x,foe.y];e.angle_deg=0.;e.length_ft=foe.space_ft.max(5.);e.width_ft=foe.space_ft.max(5.);e.radius_ft=5.;}
                    _=>return Err("Unknown effect trigger".into())
                }
                if next.iter().any(|old|old.id==e.id){return Err("Effect id already exists".into());}
                self.validate_effect(&e)?;let line=format!("Test trigger: {}. Visual only; no damage resolved.",e.label);
                let transient=match preset {"ranged_hit"=>Some(("projectile",1800)),"melee_hit"=>Some(("melee",1100)),"spell_blast"=>Some(("burst",1600)),"npc_breath"=>Some(("breath",2600)),"acid_jet"=>Some(("breath",2300)),"thunder_burst"=>Some(("burst",1700)),"healing_pulse"=>Some(("pulse",2300)),"transport"=>Some(("teleport",3200)),_=>None};
                if let Some((kind,duration_ms))=transient {emitted.push(VisualEvent{id:format!("vfx:{}:{}",self.revision+1,id),kind:kind.into(),effect:e,outcome:"demo".into(),duration_ms,target_origin:if kind=="teleport"{Some([target.x,target.y])}else{None},token_id:if kind=="teleport"{Some(foe.token_id.clone())}else{None}});}else{if next.len()>=40{return Err("At most 40 active effects".into());}next.push(e);}line
            }
            "replay"=>{
                let mut event=self.visual_events.iter().find(|e|Some(e.id.as_str())==action["event_id"].as_str()).cloned().ok_or("Visual event is no longer in the replay list")?;
                event.id=format!("vfx:{}:{}",self.revision+1,id);let line=format!("Visual replay: {}. No action or roll repeated.",event.effect.label);emitted.push(event);line
            }
            "clear_triggers"=>{next.retain(|e|e.source=="player");"Test-trigger visuals cleared by the hotseat GM.".into()}
            _=>return Err("Unknown effect operation".into())
        };
        for event in &emitted {self.validate_visual(event)?;}
        self.effects=next;for event in &emitted {self.record_visual(event.clone());}self.revision+=1;self.log.push(line.clone());if self.log.len()>120{self.log.remove(0);}
        self.history.push(json!({"type":"result","round":self.round,"actor":null,"log":[{"kind":"visual_effect","text":line}],"changes":[],"effects":self.resolved_effects(),"visual_events":emitted}));
        self.history.push(self.state());self.commands.push((id.into(),payload));if self.commands.len()>256{self.commands.remove(0);}Ok(())
    }
}
