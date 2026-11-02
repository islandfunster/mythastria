//! Durable character sheets and a deliberately small projection into the combat kernel.
use crate::*;
#[derive(Clone, Serialize, Deserialize, Debug)]
pub struct Character {
 pub format:String, pub id:String, pub name:String, pub kind:String,
 pub token_id:String, pub space_ft:f64, pub combat:Combat,
 #[serde(flatten)] pub sheet:serde_json::Map<String,Value>,
}
#[derive(Clone, Serialize, Deserialize, Debug)]
pub struct Combat {pub hp_max:i32,pub ac:i32,pub speed:i32,pub attack_bonus:i32,pub damage_die:u32,#[serde(default="one")]pub damage_count:u32,pub damage_bonus:i32,pub reach:i32}
pub fn one()->u32{1}
impl Character {
 pub fn validate(&self)->Result<(),String>{
  if self.format!="isles-character/1"||self.id.is_empty()||self.id.len()>100||self.name.trim().is_empty()||self.name.len()>160||!["pc","npc"].contains(&self.kind.as_str()) {return Err("Invalid character identity".into());}
  let c=&self.combat;
  if !(1..=1000).contains(&c.hp_max)||!(1..=40).contains(&c.ac)||!(5..=60).contains(&c.speed)||c.speed%5!=0||c.attack_bonus.abs()>30||!(1..=100).contains(&c.damage_die)||!(1..=10).contains(&c.damage_count)||c.damage_bonus.abs()>100||!(5..=15).contains(&c.reach)||c.reach%5!=0{return Err("Combat values are outside this prototype's supported bounds".into());}
  if !tokens().iter().any(|t|t.id==self.token_id&&(t.squares*5.-self.space_ft).abs()<0.01){return Err("Choose registered artwork with the correct grid footprint".into());}
  if serde_json::to_vec(self).map_err(|_|"Invalid character")?.len()>180_000{return Err("Character record is too large".into());}Ok(())
 }
}
thread_local!{static ROSTER:RefCell<Vec<Character>>=const{RefCell::new(vec![])};}
pub fn roster(req:&Value)->Value{ROSTER.with(|cell|{let mut list=cell.borrow_mut();let result:Result<(),String>=(||{match req["op"].as_str().unwrap_or(""){
 "character_list"=>{},
 "character_roster_load"=>{let next:Vec<Character>=serde_json::from_value(req["characters"].clone()).map_err(|_|"Invalid character collection")?;if next.len()>100{return Err("Maximum 100 characters per browser".into());}let mut ids=std::collections::HashSet::new();for c in &next{c.validate()?;if !ids.insert(&c.id){return Err("Duplicate character ID".into());}}*list=next;},
 "character_save"=>{let c:Character=serde_json::from_value(req["character"].clone()).map_err(|_|"Invalid character sheet")?;c.validate()?;if let Some(i)=list.iter().position(|a|a.id==c.id){list[i]=c;}else{if list.len()>=100{return Err("Maximum 100 characters per browser".into());}list.push(c);}},
 "character_delete"=>{let id=req["character_id"].as_str().unwrap_or("");list.retain(|c|c.id!=id);},
 _=>return Err("Unknown character command".into()),}Ok(())})();match result{Ok(())=>json!({"ok":true,"characters":*list}),Err(e)=>json!({"ok":false,"error":e})}})}
pub fn find(id:&str)->Option<Character>{ROSTER.with(|l|l.borrow().iter().find(|c|c.id==id).cloned())}
impl Game {
 pub fn place_character(&mut self,req:&Value)->Result<(),String>{
  if req["revision"].as_u64()!=Some(self.revision as u64){return Err("The table changed; review the character placement again".into());}
  let c=find(req["character_id"].as_str().unwrap_or("")).ok_or("Character not saved")?;c.validate()?;
  let side=req["side"].as_str().unwrap_or("friend");if !["friend","foe"].contains(&side){return Err("Invalid side".into());}
  let mut next=self.clone();let target=req["replace_actor"].as_str();let replacing=target.is_some();
  let idx=if let Some(id)=target {next.actors.iter().position(|a|a.id==id).ok_or("Selected actor no longer exists")?}else{if next.actors.len()>=40{return Err("The table supports up to 40 combatants".into());}next.actors.push(next.actors[0].clone());next.actors.len()-1};
  let previous=next.actors[idx].clone();let co=c.combat.clone();
  let id=if replacing{previous.id.clone()}else{format!("character:{}:{}",c.id,next.revision+1)};
  next.actors[idx]=Actor{id,name:c.name.clone(),side:side.into(),token_id:c.token_id.clone(),space_ft:c.space_ft,x:previous.x,y:previous.y,hp:co.hp_max,hp_max:co.hp_max,ac:co.ac,speed:co.speed,attack_bonus:co.attack_bonus,damage_die:co.damage_die,damage_count:co.damage_count,damage_bonus:co.damage_bonus,reach:co.reach,initiative:if replacing{previous.initiative}else{0},dodge:false,character:Some(c)};
  let positions=if replacing{vec![(previous.x,previous.y)]}else{let space=next.actors[idx].space_ft;let offset=(space/5.-1.)/2.;let mut p=vec![];for y in 0..next.map.rows{for x in 0..next.map.cols{p.push((x as f64+offset,y as f64+offset));}}p};
  let Some((x,y))=positions.into_iter().find(|(x,y)|next.fits(idx,*x,*y))else{return Err(if replacing{"The new footprint does not fit here. Add separately or move the selected actor first."}else{"No free space for this character on the map"}.into());};
  next.actors[idx].x=x;next.actors[idx].y=y;next.undo_move=None;
  if idx==next.active{next.movement=next.movement.min(co.speed);}
  next.revision+=1;next.log.push(format!("{} {} with a reviewed character sheet. Only the basic combat profile is automated.",next.actors[idx].name,if replacing{"replaced"}else{"added"}));
  next.history.push(json!({"type":"roster_change","character_id":next.actors[idx].character.as_ref().map(|c|&c.id),"actor":next.actors[idx].id,"replacement":replacing}));next.history.push(next.state());next.validate()?;*self=next;Ok(())
 }
}
#[cfg(test)]mod tests{use super::*;
 fn sheet()->Value{json!({"format":"isles-character/1","id":"test","name":"Test","kind":"pc","token_id":"spy","space_ft":5,"combat":{"hp_max":12,"ac":14,"speed":30,"attack_bonus":4,"damage_die":6,"damage_count":2,"damage_bonus":2,"reach":5},"spells":["Light"],"source":"test"})}
 #[test]fn roster_and_atomic_placement(){assert_eq!(roster(&json!({"op":"character_save","character":sheet()}))["ok"],true);let mut g=Game::new(7,"harbor");g.place_character(&json!({"revision":0,"character_id":"test","side":"friend"})).unwrap();assert_eq!(g.actors.len(),5);assert_eq!(g.actors.last().unwrap().damage_count,2);let saved=serde_json::to_value(&g).unwrap();let back:Game=serde_json::from_value(saved.clone()).unwrap();back.validate().unwrap();assert_eq!(back.actors.last().unwrap().character.as_ref().unwrap().sheet["spells"][0],"Light");assert!(g.place_character(&json!({"revision":0,"character_id":"test"})).is_err());assert_eq!(serde_json::to_value(&g).unwrap(),saved);let mut bad=sheet();bad["combat"]["speed"]=json!(999);assert_eq!(roster(&json!({"op":"character_save","character":bad}))["ok"],false);}
 #[test]fn fixed_damage_is_not_doubled_on_a_critical(){let mut g=Game::new(7,"harbor");let ai=g.active;let ti=g.actors.iter().position(|a|a.side!=g.actors[ai].side).unwrap();g.actors[ai].x=4.;g.actors[ai].y=4.;g.actors[ti].x=5.;g.actors[ti].y=4.;g.actors[ti].hp=100;g.actors[ti].hp_max=100;g.actors[ti].dodge=false;g.actors[ai].damage_die=1;g.actors[ai].damage_count=1;g.actors[ai].damage_bonus=3;let seed=(1..10000).find(|seed|{let mut p=g.clone();p.rng=*seed;p.roll(20)==20}).unwrap();g.rng=seed;let offer=g.offers().into_iter().find(|o|o.kind=="attack"&&o.target.as_ref()==Some(&g.actors[ti].id)).unwrap();g.command("fixed-critical",g.revision,&offer.id).unwrap();assert_eq!(g.actors[ti].hp,96);}

}
