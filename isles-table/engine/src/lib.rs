mod movement;
mod characters;
mod effects;
use effects::{Effect, VisualEvent};
// Standalone prototype, original kernel. No FG or Lua runtime.
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use std::cell::RefCell;

#[derive(Clone, Serialize, Deserialize, Debug)]
pub struct Token {
    pub id: String,
    pub name: String,
    pub path: String,
    pub squares: f64,
    pub pixels: u32,
    pub footprint: String,
    pub pack: String,
    pub sha256: String,
    pub approved: bool,
}
pub fn tokens() -> Vec<Token> {
    serde_json::from_str(include_str!("../tokens.json")).expect("built token registry")
}
#[derive(Clone, Serialize, Deserialize, Debug)]
pub struct Actor {
    pub id: String,
    pub name: String,
    pub side: String,
    pub token_id: String,
    pub x: f64,
    pub y: f64,
    pub space_ft: f64,
    pub hp: i32,
    pub hp_max: i32,
    pub ac: i32,
    pub speed: i32,
    pub attack_bonus: i32,
    pub damage_die: u32,
    #[serde(default="characters::one")]
    pub damage_count: u32,
    #[serde(default)]
    pub character: Option<characters::Character>,
    pub damage_bonus: i32,
    pub reach: i32,
    pub initiative: i32,
    pub dodge: bool,
}
#[derive(Clone, Serialize, Deserialize, Debug)]
pub struct Wall {
    pub id: String,
    pub points: [[f64; 2]; 2],
    pub door: bool,
    pub open: bool,
}
#[derive(Clone, Serialize, Deserialize, Debug)]
pub struct Map {
    pub name: String,
    pub cols: u32,
    pub rows: u32,
    pub square_ft: u32,
    pub walls: Vec<Wall>,
}
#[derive(Clone, Serialize, Deserialize, Debug)]
pub struct UndoMove { actor: usize, x: f64, y: f64, movement: i32, keyboard: bool, #[serde(default)] diagonal_steps:u32 }
#[derive(Clone, Serialize, Deserialize, Debug)]
pub struct Game {
    pub format: String,
    pub map: Map,
    pub actors: Vec<Actor>,
    pub round: u32,
    pub active: usize,
    pub revision: u32,
    pub movement: i32,
    #[serde(default)]
    pub diagonal_steps: u32,
    pub action_available: bool,
    pub rng: u32,
    pub log: Vec<String>,
    pub history: Vec<Value>,
    pub commands: Vec<(String, Value)>,
    pub scene: String,
    #[serde(default)]
    pub undo_move: Option<UndoMove>,
    #[serde(default)]
    pub effects: Vec<Effect>,
    #[serde(default)]
    pub visual_events: Vec<VisualEvent>,
}
#[derive(Clone, Serialize, Debug)]
pub struct Offer {
    pub id: String,
    pub label: String,
    pub kind: String,
    pub target: Option<String>,
    pub x: Option<f64>,
    pub y: Option<f64>,
}
#[derive(Clone, Serialize, Debug)]
pub struct MoveTarget {
    pub id: String,
    pub x: f64,
    pub y: f64,
    pub cost_ft: i32,
    pub diagonal_steps: u32,
    pub path: Vec<[f64; 2]>,
}
fn offer(
    id: &str,
    label: String,
    kind: &str,
    target: Option<String>,
    xy: Option<(f64, f64)>,
) -> Offer {
    Offer {
        id: id.into(),
        label,
        kind: kind.into(),
        target,
        x: xy.map(|v| v.0),
        y: xy.map(|v| v.1),
    }
}
impl Game {
    pub fn roll(&mut self, sides: u32) -> u32 {
        loop {
            self.rng ^= self.rng << 13;
            self.rng ^= self.rng >> 17;
            self.rng ^= self.rng << 5;
            let limit = u32::MAX - u32::MAX % sides;
            if self.rng < limit {
                return self.rng % sides + 1;
            }
        }
    }
    pub fn new(seed: u32, scene: &str) -> Self {
        let temple = scene == "temple";
        let wall = |id: &str, p: [[f64; 2]; 2], door: bool| Wall {
            id: id.into(),
            points: p,
            door,
            open: false,
        };
        let mut walls = vec![
            wall("north", [[-0.5, -0.5], [17.5, -0.5]], false),
            wall("south", [[-0.5, 11.5], [17.5, 11.5]], false),
            wall("west", [[-0.5, -0.5], [-0.5, 11.5]], false),
            wall("east", [[17.5, -0.5], [17.5, 11.5]], false),
        ];
        walls.extend([
            wall("divider-n", [[8.5, -0.5], [8.5, 4.5]], false),
            wall("gate", [[8.5, 4.5], [8.5, 6.5]], true),
            wall("divider-s", [[8.5, 6.5], [8.5, 11.5]], false),
        ]);
        if temple {
            walls.extend([
                wall("pillar-n", [[12.5, 2.5], [14.5, 2.5]], false),
                wall("pillar-w", [[12.5, 2.5], [12.5, 4.5]], false),
                wall("pillar-s", [[12.5, 4.5], [14.5, 4.5]], false),
                wall("pillar-e", [[14.5, 2.5], [14.5, 4.5]], false),
            ]);
        }
        let actor =
            |id: &str, name: &str, side: &str, token: &str, x: f64, y: f64, hp: i32, ac: i32| {
                Actor {
                    id: id.into(),
                    name: name.into(),
                    side: side.into(),
                    token_id: token.into(),
                    x,
                    y,
                    space_ft: 5.,
                    hp,
                    hp_max: hp,
                    ac,
                    speed: 30,
                    attack_bonus: 5,
                    damage_die: 6,
                    damage_count: 1,
                    character: None,
                    damage_bonus: 3,
                    reach: 5,
                    initiative: 0,
                    dodge: false,
                }
            };
        let mut actors = vec![
            actor("p1", "Mara", "friend", "warrior_veteran", 3., 5., 24, 16),
            actor("p2", "Finch", "friend", "spy", 3., 7., 20, 14),
            actor(
                "e1",
                "Practice Guard",
                "foe",
                "goblin_warrior",
                12.,
                5.,
                18,
                13,
            ),
            actor(
                "e2",
                "Practice Sentinel",
                "foe",
                "hobgoblin_warrior",
                13.,
                7.,
                22,
                15,
            ),
        ];
        if temple {
            actors[3].token_id = "ogre".into();
            actors[3].name = "Training Ogre".into();
            actors[3].x = 13.5;
            actors[3].y = 7.5;
            actors[3].space_ft = 10.;
            actors[3].hp = 32;
            actors[3].hp_max = 32;
        }
        let mut g = Self {
            format: "isles-session/1".into(),
            map: Map {
                name: if temple {
                    "The Watch Hall".into()
                } else {
                    "The Salt Gate".into()
                },
                cols: 18,
                rows: 12,
                square_ft: 5,
                walls,
            },
            actors,
            round: 1,
            active: 0,
            revision: 0,
            movement: 30,
            action_available: true,
            rng: seed.max(1),
            log: vec!["Training encounter. Synthetic profiles; core prototype rules only.".into()],
            history: vec![],
            commands: vec![],
            undo_move: None,
            diagonal_steps: 0,
            effects: vec![],
            visual_events: vec![],
            scene: scene.into(),
        };
        for i in 0..g.actors.len() {
            g.actors[i].initiative = g.roll(20) as i32;
        }
        g.actors
            .sort_by(|a, b| b.initiative.cmp(&a.initiative).then(a.id.cmp(&b.id)));
        g.history.push(json!({"type":"scenario","format":"sim-messages/1","source_scenario":"rust_training","party":["Mara","Finch"],"level":null,"items":false,"seed":seed.max(1),"rounds":null,"map":{"name":g.map.name,"cols":18,"rows":12,"square_ft":5,"walls":g.map.walls,"zones":[],"lighting":{"ambient":"bright","lights":[]}}}));
        g.history.push(g.state());
        g
    }
    pub fn validate(&self) -> Result<(), String> {
        let catalog = tokens();
        if self.visual_events.len()>24{return Err("Too many visual events".into());}
        let mut visual_ids=std::collections::HashSet::new();
        for e in &self.visual_events{self.validate_visual(e)?;if !visual_ids.insert(&e.id){return Err("Duplicate visual event id".into());}}
        if self.effects.len()>40 {return Err("Too many effects".into());}
        let mut effect_ids=std::collections::HashSet::new();
        for e in &self.effects {self.validate_effect(e)?;if !effect_ids.insert(&e.id){return Err("Duplicate effect id".into());}}
        if self.format != "isles-session/1"
            || self.actors.is_empty()
            || self.actors.len() > 40
            || self.active >= self.actors.len()
            || self.map.cols < 2
            || self.map.rows < 2
            || self.map.cols > 100
            || self.map.rows > 100
            || self.map.square_ft != 5
            || self.map.walls.len() > 500
            || self.history.len() > 10000
            || self.rng == 0
            || self.round == 0
            || self.diagonal_steps > 240
            || self.movement < 0
            || self.movement > 120
        {
            return Err("Invalid session bounds".into());
        }
        if self.actors[self.active].hp == 0 && self.winner().is_none() {
            return Err("Defeated active actor".into());
        }
        if let Some(u)=&self.undo_move {
            if u.diagonal_steps>self.diagonal_steps || u.actor!=self.active || !u.x.is_finite() || !u.y.is_finite() || u.movement<self.movement || u.movement>120 || !self.fits(u.actor,u.x,u.y) {return Err("Invalid move undo checkpoint".into());}
        }
        let mut ids = std::collections::HashSet::new();
        for w in &self.map.walls {
            if !w.points.iter().flatten().all(|n| n.is_finite())
                || (w.points[0][0] != w.points[1][0] && w.points[0][1] != w.points[1][1])
            {
                return Err("Only finite axis-aligned walls supported".into());
            }
        }
        for (i, a) in self.actors.iter().enumerate() {
            if !ids.insert(&a.id)
                || !["friend", "foe"].contains(&a.side.as_str())
                || !a.x.is_finite()
                || !a.y.is_finite()
                || a.hp < 0
                || a.hp > a.hp_max
                || a.hp_max > 1000
                || a.hp_max <= 0
                || a.ac < 1
                || a.ac > 40
                || a.damage_die < 1
                || a.damage_count < 1
                || a.damage_count > 10
                || a.damage_die > 100
                || a.attack_bonus.abs() > 30
                || a.damage_bonus.abs() > 100
                || a.speed < 5
                || a.speed > 60
                || a.reach < 5
                || a.reach > 15
            {
                return Err("Invalid actor".into());
            }
            if let Some(c)=&a.character{c.validate()?;}
            let Some(t) = catalog.iter().find(|t| t.id == a.token_id) else {
                return Err("Unregistered token".into());
            };
            if (t.squares * 5. - a.space_ft).abs() > 0.01 {
                return Err("Token/space mismatch".into());
            }
            if a.hp > 0 && !self.fits(i, a.x, a.y) {
                return Err("Actor overlaps wall, boundary or another actor".into());
            }
        }
        Ok(())
    }
    pub fn winner(&self) -> Option<String> {
        let friendly = self.actors.iter().any(|c| c.hp > 0 && c.side == "friend");
        let hostile = self.actors.iter().any(|c| c.hp > 0 && c.side == "foe");
        if !friendly {
            Some("Opposition".into())
        } else if !hostile {
            Some("Party".into())
        } else {
            None
        }
    }
    pub fn state(&self) -> Value {
        json!({"type":"state","round":self.round,"active":if self.winner().is_none(){Some(&self.actors[self.active].id)}else{None},"revision":self.revision,"effects":self.resolved_effects(),"diagonal_steps":self.diagonal_steps,"combatants":self.actors.iter().map(|a|json!({"id":a.id,"name":a.name,"side":a.side,"pc":a.character.as_ref().map(|c|c.kind=="pc").unwrap_or(false),"character":a.character.as_ref().map(|c|json!({"id":c.id,"name":c.name,"kind":c.kind})),"speed":a.speed,"attack_bonus":a.attack_bonus,"damage_count":a.damage_count,"damage_die":a.damage_die,"damage_bonus":a.damage_bonus,"reach":a.reach,"x":a.x,"y":a.y,"space_ft":a.space_ft,"hp":a.hp,"hp_max":a.hp_max,"ac":a.ac,"down":a.hp==0,"conditions":if a.dodge{vec!["Dodging"]}else{vec![]},"underwater":false,"aloft":false,"mount":null,"token_id":a.token_id,"initiative":a.initiative})).collect::<Vec<_>>()})
    }
    fn bounds(a: &Actor, x: f64, y: f64) -> [f64; 4] {
        let h = a.space_ft / 10.;
        [x - h, x + h, y - h, y + h]
    }
    fn wall_crosses(&self, b: [f64; 4]) -> bool {
        self.map.walls.iter().filter(|w| !w.open).any(|w| {
            let [[x1, y1], [x2, y2]] = w.points;
            if x1 == x2 {
                x1 > b[0] + 1e-8
                    && x1 < b[1] - 1e-8
                    && y1.min(y2) < b[3] - 1e-8
                    && y1.max(y2) > b[2] + 1e-8
            } else {
                y1 > b[2] + 1e-8
                    && y1 < b[3] - 1e-8
                    && x1.min(x2) < b[1] - 1e-8
                    && x1.max(x2) > b[0] + 1e-8
            }
        })
    }
    pub fn fits(&self, idx: usize, x: f64, y: f64) -> bool {
        let a = &self.actors[idx];
        let b = Self::bounds(a, x, y);
        if b[0] < -0.50001
            || b[2] < -0.50001
            || b[1] > self.map.cols as f64 - 0.49999
            || b[3] > self.map.rows as f64 - 0.49999
            || self.wall_crosses(b)
        {
            return false;
        }
        !self.actors.iter().enumerate().any(|(i, o)| {
            if i == idx || o.hp == 0 {
                return false;
            }
            let r = Self::bounds(o, o.x, o.y);
            b[0] < r[1] - 1e-8 && b[1] > r[0] + 1e-8 && b[2] < r[3] - 1e-8 && b[3] > r[2] + 1e-8
        })
    }
    fn can_step(&self, idx: usize, x: f64, y: f64) -> bool {
        let a = &self.actors[idx];
        self.can_step_from(idx, a.x, a.y, x, y)
    }
    fn can_step_from(&self, idx: usize, fx: f64, fy: f64, x: f64, y: f64) -> bool {
        let a = &self.actors[idx];
        let (dx,dy)=((x-fx).abs(),(y-fy).abs());
        if dx>1.00001||dy>1.00001||(dx<1e-8&&dy<1e-8){return false;}
        // A diagonal cannot squeeze through a blocked orthogonal corner.
        if dx>1e-8&&dy>1e-8&&(!self.fits(idx,fx,y)||!self.fits(idx,x,fy)){return false;}
        if !self.fits(idx, x, y) {
            return false;
        }
        let b = Self::bounds(a, fx, fy);
        let n = Self::bounds(a, x, y);
        !self.wall_crosses([
            b[0].min(n[0]),
            b[1].max(n[1]),
            b[2].min(n[2]),
            b[3].max(n[3]),
        ])
    }
    fn distance(a: &Actor, b: &Actor) -> f64 {
        let extra = (a.space_ft + b.space_ft) / 10. - 1.;
        ((a.x - b.x).abs().max((a.y - b.y).abs()) - extra).max(0.) * 5.
    }
    fn line_clear(&self, a: (f64, f64), b: (f64, f64)) -> bool {
        !self.map.walls.iter().filter(|w| !w.open).any(|w| {
            let [[x1, y1], [x2, y2]] = w.points;
            if x1 == x2 {
                if (b.0 - a.0).abs() < 1e-8 {
                    return false;
                }
                let t = (x1 - a.0) / (b.0 - a.0);
                let y = a.1 + t * (b.1 - a.1);
                t > 1e-8 && t < 1. - 1e-8 && y >= y1.min(y2) - 1e-8 && y <= y1.max(y2) + 1e-8
            } else {
                if (b.1 - a.1).abs() < 1e-8 {
                    return false;
                }
                let t = (y1 - a.1) / (b.1 - a.1);
                let x = a.0 + t * (b.0 - a.0);
                t > 1e-8 && t < 1. - 1e-8 && x >= x1.min(x2) - 1e-8 && x <= x1.max(x2) + 1e-8
            }
        })
    }
    pub fn offers(&self) -> Vec<Offer> {
        if self.winner().is_some() {
            return vec![];
        }
        let a = &self.actors[self.active];
        let mut out = vec![];
        if self.undo_move.is_some() {out.push(offer("undo_move", "Undo whole move".into(), "undo", None, None));}
        out.extend(self.move_offers());
        if self.action_available {
            for b in &self.actors {
                if a.side != b.side
                    && b.hp > 0
                    && Self::distance(a, b) <= a.reach as f64
                    && self.line_clear((a.x, a.y), (b.x, b.y))
                {
                    out.push(offer(
                        &format!("attack:{}", b.id),
                        format!("Attack {}", b.name),
                        "attack",
                        Some(b.id.clone()),
                        None,
                    ));
                }
            }
            out.push(offer("dodge", "Dodge".into(), "dodge", None, None));
            out.push(offer("dash", "Dash · +30 ft".into(), "dash", None, None));
        }
        for w in &self.map.walls {
            if !w.door {
                continue;
            }
            let [[x1, y1], [x2, y2]] = w.points;
            let x = a.x.clamp(x1.min(x2), x1.max(x2));
            let y = a.y.clamp(y1.min(y2), y1.max(y2));
            let b = Self::bounds(a, a.x, a.y);
            let intersects = x > b[0] && x < b[1] && y > b[2] && y < b[3];
            if (a.x - x).abs().max((a.y - y).abs()) <= 1.
                && !intersects
                && (!w.open
                    || !self.actors.iter().filter(|a| a.hp > 0).any(|a| {
                        let b = Self::bounds(a, a.x, a.y);
                        if x1 == x2 {
                            x1 > b[0] && x1 < b[1] && y1.min(y2) < b[3] && y1.max(y2) > b[2]
                        } else {
                            y1 > b[2] && y1 < b[3] && x1.min(x2) < b[1] && x1.max(x2) > b[0]
                        }
                    }))
            {
                out.push(offer(
                    &format!("door:{}", w.id),
                    format!("{} gate", if w.open { "Close" } else { "Open" }),
                    "door",
                    Some(w.id.clone()),
                    None,
                ));
            }
        }
        out.push(offer("end", "End turn".into(), "end", None, None));
        out
    }
    fn next_turn(&mut self) {
        self.diagonal_steps=0;
        let n = self.actors.len();
        for _ in 0..n {
            self.active = (self.active + 1) % n;
            if self.active == 0 {
                self.round += 1;
            }
            if self.actors[self.active].hp > 0 {
                break;
            }
        }
        self.actors[self.active].dodge = false;
        self.movement = self.actors[self.active].speed;
        self.action_available = true;
    }
    pub fn command(&mut self, id: &str, revision: u32, offer_id: &str) -> Result<(), String> {
        let payload = json!([revision, offer_id]);
        if let Some((_, old)) = self.commands.iter().find(|(k, _)| k == id) {
            return if *old == payload {
                Ok(())
            } else {
                Err("Command id reused with different content".into())
            };
        }
        if revision != self.revision {
            return Err("Stale state; refresh before acting".into());
        }
        if id.is_empty() || id.len() > 100 {
            return Err("Invalid command id".into());
        }
        let route = if let Some(raw)=offer_id.strip_prefix("route:") {
            Some(self.plan_route(serde_json::from_str(raw).map_err(|_|"Invalid waypoints")?)?)
        } else if offer_id.starts_with("move_to:") {
            Some(self.movement_targets().into_iter().find(|t| t.id == offer_id)
                .ok_or("Destination is blocked or beyond remaining movement")?)
        } else { None };
        let o = if let Some(t) = &route {
            offer(&t.id, format!("Move {} ft", t.cost_ft), "move", None, Some((t.x, t.y)))
        } else {
            self.offers().into_iter().find(|o| o.id == offer_id).ok_or("Action is not currently legal")?
        };
        let before = self.state();
        let actor = self.actors[self.active].clone();
        let mut line = String::new();
        let mut emitted=vec![];
        if o.kind=="move" {
            let keyboard=route.is_none();
            if !keyboard || !self.undo_move.as_ref().map(|u|u.keyboard).unwrap_or(false) {
                self.undo_move=Some(UndoMove{actor:self.active,x:actor.x,y:actor.y,movement:self.movement,keyboard,diagonal_steps:self.diagonal_steps});
            }
        } else if o.kind!="undo" {self.undo_move=None;}
        match o.kind.as_str() {
            "undo" => {
                let u=self.undo_move.take().ok_or("No move to undo")?;
                self.actors[u.actor].x=u.x;self.actors[u.actor].y=u.y;self.movement=u.movement;self.diagonal_steps=u.diagonal_steps;
                line=format!("{} undoes their whole move; movement restored.",actor.name);
            }
            "move" => {
                let diagonal=(o.x.unwrap()-actor.x).abs()>1e-8&&(o.y.unwrap()-actor.y).abs()>1e-8;
                let cost = route.as_ref().map(|t| t.cost_ft).unwrap_or(if diagonal{self.diagonal_cost()}else{5});
                self.diagonal_steps+=route.as_ref().map(|t|t.diagonal_steps).unwrap_or(diagonal as u32);
                self.actors[self.active].x = o.x.unwrap();
                self.actors[self.active].y = o.y.unwrap();
                self.movement -= cost;
                line = format!("{} moves {} ft to ({}, {}).", actor.name, cost, o.x.unwrap(), o.y.unwrap());
            }
            "attack" => {
                let ti = self
                    .actors
                    .iter()
                    .position(|a| Some(&a.id) == o.target.as_ref())
                    .unwrap();
                let first = self.roll(20);
                let rolled = if self.actors[ti].dodge {
                    first.min(self.roll(20))
                } else {
                    first
                };
                let hit = rolled == 20
                    || (rolled != 1 && rolled as i32 + actor.attack_bonus >= self.actors[ti].ac);
                let target=&self.actors[ti];
                let mut impact_label=format!("{} → {}",actor.name,target.name);while impact_label.len()>100{impact_label.pop();}
                emitted.push(VisualEvent{id:format!("vfx:{}:{}",self.revision+1,id),kind:"melee".into(),effect:Effect{id:format!("impact:{}",self.revision+1),label:impact_label,shape:"melee".into(),appearance:"physical".into(),origin:[target.x,target.y],angle_deg:(target.y-actor.y).atan2(target.x-actor.x).to_degrees(),length_ft:5.,width_ft:5.,radius_ft:5.,source:if actor.side=="foe"{"npc".into()}else{"player".into()},control:"fixed".into(),source_actor:Some(actor.id.clone()),expires_round:None},outcome:if !hit{"miss".into()}else if rolled==20{"critical".into()}else{"hit".into()},duration_ms:1200,target_origin:None,token_id:None});
                self.action_available = false;
                if hit {
                    let dice = actor.damage_count * if rolled == 20 && actor.damage_die > 1 { 2 } else { 1 };
                    let mut damage = actor.damage_bonus;
                    for _ in 0..dice {
                        damage += self.roll(actor.damage_die) as i32;
                    }
                    damage = damage.max(0);
                    self.actors[ti].hp = (self.actors[ti].hp - damage).max(0);
                    line = format!(
                        "{} attacks {}: d20 {} + {} = {} → {}. {} damage; {} HP remains.",
                        actor.name,
                        self.actors[ti].name,
                        rolled,
                        actor.attack_bonus,
                        rolled as i32 + actor.attack_bonus,
                        if rolled == 20 { "critical hit" } else { "hit" },
                        damage,
                        self.actors[ti].hp
                    );
                } else {
                    line = format!(
                        "{} attacks {}: d20 {} + {} = {} → miss.",
                        actor.name,
                        self.actors[ti].name,
                        rolled,
                        actor.attack_bonus,
                        rolled as i32 + actor.attack_bonus
                    );
                }
            }
            "dodge" => {
                self.actors[self.active].dodge = true;
                self.action_available = false;
                line = format!("{} Dodges until their next turn.", actor.name);
            }
            "dash" => {
                self.movement += actor.speed;
                self.action_available = false;
                line = format!("{} Dashes; {} ft remains.", actor.name, self.movement);
            }
            "door" => {
                let wi = self
                    .map
                    .walls
                    .iter()
                    .position(|w| Some(&w.id) == o.target.as_ref())
                    .unwrap();
                self.map.walls[wi].open = !self.map.walls[wi].open;
                line = format!(
                    "{} {} the gate.",
                    actor.name,
                    if self.map.walls[wi].open {
                        "opens"
                    } else {
                        "closes"
                    }
                );
            }
            "end" => {
                line = format!("{} ends their turn.", actor.name);
                self.next_turn();
            }
            _ => {}
        }
        for event in &emitted {self.record_visual(event.clone());}
        self.effects.retain(|e|e.expires_round.map(|r|r>self.round).unwrap_or(true));
        self.revision += 1;
        self.log.push(line.clone());
        if self.log.len() > 120 {
            self.log.remove(0);
        }
        let after = self.state();
        let old = before["combatants"].as_array().unwrap();
        let new = after["combatants"].as_array().unwrap();
        let changes = new
            .iter()
            .filter_map(|c| {
                let prev = old.iter().find(|p| p["id"] == c["id"])?;
                let mut changed = serde_json::Map::new();
                for (key, value) in c.as_object().unwrap() {
                    if prev[key] != *value {
                        changed.insert(key.clone(), json!([prev[key], value]));
                    }
                }
                if changed.is_empty() {
                    None
                } else {
                    Some(json!({"id":c["id"],"name":c["name"],"changed":changed}))
                }
            })
            .collect::<Vec<_>>();
        self.history.push(json!({"type":"action","round":before["round"],"actor":actor.id,"actor_name":actor.name,"controller":"human via Rust offers","decisions":[],"intent":[o.label]}));
        self.history.push(json!({"type":"result","round":before["round"],"actor":actor.id,"log":[{"kind":"turn","text":line}],"changes":changes,"movement_path":route.as_ref().map(|t| &t.path),"effects":self.resolved_effects(),"visual_events":emitted,"map_update":{"walls":self.map.walls}}));
        self.history.push(after);
        self.commands.push((id.into(), payload));
        if self.commands.len() > 256 {
            self.commands.remove(0);
        }
        Ok(())
    }
    pub fn suggest(&self) -> Option<Offer> {
        let choices = self.offers();
        if let Some(o) = choices.iter().find(|o| o.kind == "attack") {
            return Some(o.clone());
        }
        if !self.action_available || self.movement < 5 {
            return choices.iter().find(|o| o.kind == "end").cloned();
        }
        if let Some(o) = choices
            .iter()
            .find(|o| o.kind == "door" && o.label.starts_with("Open"))
        {
            return Some(o.clone());
        }
        let a = &self.actors[self.active];
        for seek_door in [false, true] {
            let mut queue = std::collections::VecDeque::new();
            let mut seen = std::collections::HashSet::new();
            queue.push_back((a.x, a.y, None::<String>));
            seen.insert(((a.x * 2.) as i32, (a.y * 2.) as i32));
            while let Some((x, y, first)) = queue.pop_front() {
                let mut imagined = a.clone();
                imagined.x = x;
                imagined.y = y;
                let goal = if seek_door {
                    self.map
                        .walls
                        .iter()
                        .filter(|w| w.door && !w.open)
                        .any(|w| {
                            let [[x1, y1], [x2, y2]] = w.points;
                            (x - x.clamp(x1.min(x2), x1.max(x2)))
                                .abs()
                                .max((y - y.clamp(y1.min(y2), y1.max(y2))).abs())
                                <= 1.
                        })
                } else {
                    self.actors
                        .iter()
                        .filter(|b| b.hp > 0 && b.side != a.side)
                        .any(|b| {
                            Self::distance(&imagined, b) <= a.reach as f64
                                && self.line_clear((x, y), (b.x, b.y))
                        })
                };
                if goal {
                    if let Some(id) = first {
                        return choices.iter().find(|o| o.id == id).cloned();
                    }
                }
                for (dx, dy, label) in [
                    (0., -1., "North"),
                    (1., 0., "East"),
                    (0., 1., "South"),
                    (-1., 0., "West"),
                ] {
                    let nx = x + dx;
                    let ny = y + dy;
                    let key = ((nx * 2.) as i32, (ny * 2.) as i32);
                    if !seen.contains(&key) && self.can_step_from(self.active, x, y, nx, ny) {
                        seen.insert(key);
                        queue.push_back((nx, ny, first.clone().or(Some(format!("move:{label}")))));
                    }
                }
            }
        }
        choices.iter().find(|o| o.kind == "end").cloned()
    }
    pub fn reply(&self) -> Value {
        json!({"ok":true,"engine":"isles-rust/0.1","state":self.state(),"map":self.map,"offers":self.offers(),"movement_targets":self.movement_targets(),"movement":self.movement,"diagonal_steps":self.diagonal_steps,"next_diagonal_ft":self.diagonal_cost(),"action_available":self.action_available,"log":self.log,"winner":self.winner(),"scene":self.scene,"effects":self.resolved_effects(),"visual_events":self.visual_events})
    }
}

thread_local! {static GAME:RefCell<Option<Game>>=const{RefCell::new(None)};}
pub fn dispatch(req: Value) -> Value {
    GAME.with(|cell|{let mut slot=cell.borrow_mut();let op=req["op"].as_str().unwrap_or("");match op{
 "character_actor_sheet"=>{if let Some(g)=slot.as_ref(){if let Some(c)=g.actors.iter().find(|a|Some(a.id.as_str())==req["actor"].as_str()).and_then(|a|a.character.as_ref()){json!({"ok":true,"character":c})}else{json!({"ok":false,"error":"No character sheet attached to this actor"})}}else{json!({"ok":false,"error":"No session"})}},
 "character_list"|"character_roster_load"|"character_save"|"character_delete"=>characters::roster(&req),
 "character_place"=>{if let Some(g)=slot.as_mut(){match g.place_character(&req){Ok(())=>g.reply(),Err(e)=>json!({"ok":false,"error":e})}}else{json!({"ok":false,"error":"No session"})}},
 "catalog"=>json!({"ok":true,"tokens":tokens()}),
 "new"=>{let seed=req["seed"].as_u64().unwrap_or(1) as u32;let scene=req["scene"].as_str().unwrap_or("harbor");if !["harbor","temple"].contains(&scene){return json!({"ok":false,"error":"Unknown training map"});}*slot=Some(Game::new(seed,scene));slot.as_ref().unwrap().reply()},
 "state"=>slot.as_ref().map(Game::reply).unwrap_or(json!({"ok":false,"error":"No session"})),
 "effect"=>{if let Some(g)=slot.as_mut(){let Some(rev)=req["revision"].as_u64().filter(|n|*n<=u32::MAX as u64)else{return json!({"ok":false,"error":"Missing revision"});};match g.effect_command(req["id"].as_str().unwrap_or(""),rev as u32,&req["action"]){Ok(())=>g.reply(),Err(e)=>json!({"ok":false,"error":e})}}else{json!({"ok":false,"error":"No session"})}},
 "path_preview"=>{if let Some(g)=slot.as_ref(){if req["revision"].as_u64()!=Some(g.revision as u64){return json!({"ok":false,"error":"Stale state"});}match serde_json::from_value::<Vec<[f64;2]>>(req["waypoints"].clone()).map_err(|_|"Invalid waypoints".to_string()).and_then(|p|g.plan_route(p)){Ok(route)=>json!({"ok":true,"route":route}),Err(e)=>json!({"ok":false,"error":e})}}else{json!({"ok":false,"error":"No session"})}},
 "command"=>{if let Some(g)=slot.as_mut(){let Some(rev)=req["revision"].as_u64().filter(|n|*n<=u32::MAX as u64)else{return json!({"ok":false,"error":"Missing revision"});};match g.command(req["id"].as_str().unwrap_or(""),rev as u32,req["offer_id"].as_str().unwrap_or("")){Ok(())=>g.reply(),Err(e)=>json!({"ok":false,"error":e})}}else{json!({"ok":false,"error":"No session"})}},
 "skin"=>{if let Some(g)=slot.as_mut(){let Some(t)=tokens().into_iter().find(|t|Some(t.id.as_str())==req["token_id"].as_str())else{return json!({"ok":false,"error":"Unknown token"});};let Some(a)=g.actors.iter_mut().find(|a|Some(a.id.as_str())==req["actor"].as_str())else{return json!({"ok":false,"error":"Unknown actor"});};if (a.space_ft-t.squares*5.).abs()>0.01{return json!({"ok":false,"error":"Art footprint must match actor space; appearance cannot change gameplay size"});}a.token_id=t.id;g.revision+=1;g.history.push(g.state());g.reply()}else{json!({"ok":false,"error":"No session"})}},
 "save"=>slot.as_ref().map(|g|json!({"ok":true,"session":g})).unwrap_or(json!({"ok":false,"error":"No session"})),
 "load"=>{match serde_json::from_value::<Game>(req["session"].clone()){Ok(g)=>{if let Err(e)=g.validate(){return json!({"ok":false,"error":e});}*slot=Some(g);slot.as_ref().unwrap().reply()},Err(_)=>json!({"ok":false,"error":"Invalid session file"})}},
 "suggest"=>{if let Some(g)=slot.as_ref(){json!({"ok":true,"offer":g.suggest(),"reason":"Simple legal-action helper; not an LLM"})}else{json!({"ok":false,"error":"No session"})}},
 "export"=>slot.as_ref().map(|g|json!({"ok":true,"messages":g.history})).unwrap_or(json!({"ok":false,"error":"No session"})),
 _=>json!({"ok":false,"error":"Unsupported command"})
}})
}

// C ABI: JS owns allocations and always frees request and reply buffers.
#[no_mangle]
pub extern "C" fn alloc(len: usize) -> *mut u8 {
    let bytes = vec![0u8; len].into_boxed_slice();
    Box::into_raw(bytes) as *mut u8
}
#[no_mangle]
pub unsafe extern "C" fn dealloc(ptr: *mut u8, len: usize) {
    if !ptr.is_null() {
        drop(Box::from_raw(std::ptr::slice_from_raw_parts_mut(ptr, len)));
    }
}
#[no_mangle]
pub unsafe extern "C" fn request(ptr: *const u8, len: usize) -> u64 {
    let response = if len > 2_000_000 {
        json!({"ok":false,"error":"Request too large"})
    } else {
        match serde_json::from_slice::<Value>(std::slice::from_raw_parts(ptr, len)) {
            Ok(v) => dispatch(v),
            Err(_) => json!({"ok":false,"error":"Invalid JSON"}),
        }
    };
    let bytes = serde_json::to_vec(&response).unwrap().into_boxed_slice();
    let n = bytes.len();
    let p = Box::into_raw(bytes) as *mut u8;
    (n as u64) << 32 | p as u64
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn registry_and_starting_states() {
        let ts = tokens();
        assert_eq!(ts.len(), 306);
        let ids = ts
            .iter()
            .map(|t| &t.id)
            .collect::<std::collections::HashSet<_>>();
        assert_eq!(ids.len(), 306);
        for scene in ["harbor", "temple"] {
            let g = Game::new(1, scene);
            g.validate().unwrap();
            for a in &g.actors {
                assert!(ts.iter().any(|t| t.id == a.token_id));
            }
        }
    }
    #[test]
    fn wall_and_closed_gate_block_movement() {
        let mut g = Game::new(1, "harbor");
        g.actors[g.active].x = 8.;
        g.actors[g.active].y = 5.;
        assert!(!g.offers().iter().any(|o| o.id == "move:East"));
        g.command("open", 0, "door:gate").unwrap();
        assert!(g.offers().iter().any(|o| o.id == "move:East"));
        g.command("cross", 1, "move:East").unwrap();
        assert_eq!(g.actors[g.active].x, 9.);
    }
    #[test]
    fn stale_and_duplicate_commands_do_not_mutate() {
        let mut g = Game::new(1, "harbor");
        g.command("a", 0, "dodge").unwrap();
        let s = g.state();
        assert!(g.command("b", 0, "end").is_err());
        g.command("a", 0, "dodge").unwrap();
        assert_eq!(g.state(), s);
        assert!(g.command("a", 0, "end").is_err());
        assert!(g.command("c", 1, "dodge").is_err());
    }
    #[test]
    fn movement_budget_does_not_reset_per_click() {
        let mut g = Game::new(1, "harbor");
        for i in 0..6 {
            let action = if i % 2 == 0 {
                "move:North"
            } else {
                "move:South"
            };
            g.command(&format!("m{i}"), g.revision, action).unwrap();
        }
        assert_eq!(g.movement, 0);
        assert!(!g.offers().iter().any(|o| o.kind == "move"));
        g.command("dash", g.revision, "dash").unwrap();
        assert_eq!(g.movement, 30);
    }
    #[test]
    fn blocked_attack_and_action_consumption() {
        let mut g = Game::new(1, "harbor");
        let idx = g.active;
        let target = g
            .actors
            .iter()
            .position(|a| a.side != g.actors[idx].side)
            .unwrap();
        g.actors[idx].x = 8.;
        g.actors[idx].y = 5.;
        g.actors[target].x = 9.;
        g.actors[target].y = 5.;
        assert!(!g.offers().iter().any(|o| o.kind == "attack"));
        g.map.walls.iter_mut().find(|w| w.door).unwrap().open = true;
        let atk = g.offers().into_iter().find(|o| o.kind == "attack").unwrap();
        g.command("hit", g.revision, &atk.id).unwrap();
        assert!(!g.action_available);
        assert!(!g.offers().iter().any(|o| o.kind == "attack"));
    }
    #[test]
    fn large_actor_clearance_and_gate_closing() {
        let mut g = Game::new(1, "temple");
        let large = g.actors.iter().position(|a| a.space_ft == 10.).unwrap();
        g.actors[large].x = 8.5;
        g.actors[large].y = 5.5;
        assert!(!g.fits(large, 8.5, 5.5));
        g.map.walls.iter_mut().find(|w| w.door).unwrap().open = true;
        assert!(g.fits(large, 8.5, 5.5));
        let other = (large + 1) % g.actors.len();
        g.active = other;
        g.actors[other].x = 7.;
        g.actors[other].y = 5.;
        assert!(!g.offers().iter().any(|o| o.id == "door:gate"));
    }
    #[test]
    fn deterministic_rolls_and_rounds() {
        let mut a = Game::new(42, "harbor");
        let mut b = Game::new(42, "harbor");
        for _ in 0..50 {
            assert_eq!(a.roll(20), b.roll(20));
        }
        for n in 0..4 {
            a.command(&format!("e{n}"), a.revision, "end").unwrap();
        }
        assert_eq!(a.round, 2);
    }
    #[test]
    fn defeated_actor_skipped_and_terminal_has_no_actions() {
        let mut g = Game::new(1, "harbor");
        let next = (g.active + 1) % 4;
        g.actors[next].hp = 0;
        g.command("end", 0, "end").unwrap();
        assert_ne!(g.active, next);
        for a in &mut g.actors {
            if a.side == "foe" {
                a.hp = 0;
            }
        }
        assert_eq!(g.winner(), Some("Party".into()));
        assert!(g.offers().is_empty());
    }
    #[test]
    fn drag_cannot_cross_closed_gate_or_exceed_budget() {
        let mut g = Game::new(1, "harbor");
        g.actors[g.active].x = 8.; g.actors[g.active].y = 5.;
        assert!(g.movement_targets().iter().all(|t| t.x <= 8.));
        let before = g.state();
        assert!(g.command("blocked", 0, "move_to:9:5").is_err());
        assert_eq!(g.state(), before);
        g.command("open", 0, "door:gate").unwrap();
        let route = g.movement_targets().into_iter().find(|t| t.x == 10. && t.y == 5.).unwrap();
        g.command("drag", 1, &route.id).unwrap();
        assert_eq!(g.movement, 20);
        assert_eq!(g.revision, 2);
    }
    #[test]
    fn drag_counts_the_route_around_a_pillar() {
        let mut g = Game::new(1, "temple");
        g.active = g.actors.iter().position(|a| a.space_ft == 5.).unwrap();
        g.actors[g.active].x = 12.; g.actors[g.active].y = 3.;
        let route = g.movement_targets().into_iter().find(|t| t.x == 15. && t.y == 3.).unwrap();
        assert_eq!(route.cost_ft, 25); // 15 ft straight-line distance is blocked.
        g.movement = 15;
        assert!(g.command("cut-corner", 0, &route.id).is_err());
        assert_eq!(g.movement, 15);
    }
    #[test]
    fn drag_large_token_through_two_square_gate() {
        let mut g = Game::new(1, "temple");
        g.active = g.actors.iter().position(|a| a.space_ft == 10.).unwrap();
        g.actors[g.active].x = 10.5; g.actors[g.active].y = 5.5;
        assert!(g.movement_targets().iter().all(|t| t.x >= 9.5));
        g.map.walls.iter_mut().find(|w| w.door).unwrap().open = true;
        let route = g.movement_targets().into_iter().find(|t| t.x == 8.5 && t.y == 5.5).unwrap();
        g.command("large-drag", 0, &route.id).unwrap();
        assert_eq!(g.actors[g.active].x, 8.5);
        assert_eq!(g.movement, 20);
    }
    #[test]
    fn invalid_saved_geometry_is_rejected() {
        let mut g = Game::new(1, "harbor");
        g.actors[0].token_id = "nope".into();
        assert!(g.validate().is_err());
        let mut g = Game::new(1, "harbor");
        g.map.walls[0].points[1] = [3., 4.];
        assert!(g.validate().is_err());
    }
    #[test]
    fn waypoint_route_is_atomic_and_undo_restores_whole_move() {
        let mut g=Game::new(7,"harbor");
        let a=g.actors[g.active].clone(); let budget=g.movement;
        let target=g.movement_targets().into_iter().find(|t|t.cost_ft==5).unwrap();
        let points=vec![[target.x,target.y],[a.x,a.y],[target.x,target.y]];
        let route=g.plan_route(points).unwrap();assert_eq!(route.cost_ft,15);assert_eq!(route.path.len(),3);
        let before=serde_json::to_value(&g).unwrap();
        assert!(g.command("bad",g.revision,"route:[[99,99]]").is_err());assert_eq!(before,serde_json::to_value(&g).unwrap());
        let revision=g.revision;g.command("route",revision,&route.id).unwrap();assert_eq!(g.movement,budget-15);
        g.command("undo",g.revision,"undo_move").unwrap();assert_eq!(g.movement,budget);assert_eq!((g.actors[g.active].x,g.actors[g.active].y),(a.x,a.y));
        let rev=g.revision;g.command("route",revision,&route.id).unwrap();assert_eq!(g.revision,rev);
        assert!(!g.offers().iter().any(|o|o.id=="undo_move"));
    }
    #[test]
    fn keyboard_group_undo_cannot_cross_actions() {
        let mut g=Game::new(7,"harbor");let a=g.actors[g.active].clone();let budget=g.movement;
        for id in ["one","two"] {let o=g.offers().into_iter().find(|o|o.kind=="move").unwrap();g.command(id,g.revision,&o.id).unwrap();}
        let mut restored:Game=serde_json::from_value(serde_json::to_value(&g).unwrap()).unwrap();restored.validate().unwrap();
        restored.command("undo",restored.revision,"undo_move").unwrap();assert_eq!(restored.movement,budget);assert_eq!(restored.actors[restored.active].x,a.x);assert_eq!(restored.actors[restored.active].y,a.y);
        g.command("dodge",g.revision,"dodge").unwrap();assert!(g.command("undo",g.revision,"undo_move").is_err());
    }

}
