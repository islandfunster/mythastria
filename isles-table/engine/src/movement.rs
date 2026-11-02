//! Alternating 5/10-ft diagonals. Path search includes parity and waypoint progress.
use super::*;
use std::{cmp::Reverse,collections::{BinaryHeap,HashMap,HashSet}};
type Key=(i32,i32,u8,usize);
const STEPS:[(f64,f64,&str);8]=[(0.,-1.,"North"),(1.,0.,"East"),(0.,1.,"South"),(-1.,0.,"West"),(1.,-1.,"NorthEast"),(1.,1.,"SouthEast"),(-1.,1.,"SouthWest"),(-1.,-1.,"NorthWest")];
impl Game {
    pub fn diagonal_cost(&self)->i32 {if self.diagonal_steps%2==0{5}else{10}}
    pub fn movement_targets(&self)->Vec<MoveTarget>{self.search_routes(&[])}
    fn search_routes(&self,pins:&[[f64;2]])->Vec<MoveTarget>{
        if self.winner().is_some()||self.movement<5{return vec![];}
        let a=&self.actors[self.active];
        let advance=|x:f64,y:f64,mut stage:usize|{while stage<pins.len()&&(pins[stage][0]-x).abs()<1e-8&&(pins[stage][1]-y).abs()<1e-8{stage+=1;}stage};
        let first:Key=((a.x*2.).round() as i32,(a.y*2.).round() as i32,(self.diagonal_steps%2) as u8,advance(a.x,a.y,0));
        let mut records:HashMap<Key,(i32,Vec<[f64;2]>,u32)>=HashMap::new();records.insert(first,(0,vec![],0));
        let mut heap=BinaryHeap::new();let mut sequence=0u32;heap.push(Reverse((0,0usize,sequence,first)));
        let mut emitted=HashSet::new();let mut targets=vec![];
        while let Some(Reverse((cost,steps,_,key)))=heap.pop(){
            let (best,path,diagonals)=records.get(&key).unwrap().clone();if cost!=best||steps!=path.len(){continue;}
            let (x,y)=(key.0 as f64/2.,key.1 as f64/2.);
            if !path.is_empty(){
                if !pins.is_empty()&&key.3==pins.len(){return vec![MoveTarget{id:String::new(),x,y,cost_ft:cost,path,diagonal_steps:diagonals}];}
                if pins.is_empty()&&emitted.insert((key.0,key.1))&&(x!=a.x||y!=a.y){targets.push(MoveTarget{id:format!("move_to:{x}:{y}"),x,y,cost_ft:cost,path:path.clone(),diagonal_steps:diagonals});}
            }
            for (dx,dy,_) in STEPS {
                let diagonal=dx!=0.&&dy!=0.;let extra=if diagonal&&key.2==1{10}else{5};
                if cost+extra>self.movement{continue;}
                let (nx,ny)=(x+dx,y+dy);if !self.can_step_from(self.active,x,y,nx,ny){continue;}
                let next:Key=((nx*2.).round() as i32,(ny*2.).round() as i32,key.2^(diagonal as u8),advance(nx,ny,key.3));
                if records.get(&next).map(|r|r.0<cost+extra||(r.0==cost+extra&&r.1.len()<=path.len()+1)).unwrap_or(false){continue;}
                let mut route=path.clone();route.push([nx,ny]);records.insert(next,(cost+extra,route,diagonals+diagonal as u32));sequence+=1;heap.push(Reverse((cost+extra,path.len()+1,sequence,next)));
            }
        }targets
    }
    pub fn plan_route(&self,points:Vec<[f64;2]>)->Result<MoveTarget,String>{
        let a=&self.actors[self.active];
        if points.is_empty()||points.len()>32||!points.iter().flatten().all(|n|n.is_finite())||points.iter().any(|[x,y]|(x-a.x).fract().abs()>1e-8||(y-a.y).fract().abs()>1e-8||!self.fits(self.active,*x,*y)){return Err("Invalid or blocked waypoints".into());}
        if points.iter().all(|[x,y]|(x-a.x).abs()<1e-8&&(y-a.y).abs()<1e-8){return Err("No movement".into());}
        let mut route=self.search_routes(&points).into_iter().next().ok_or("Route is blocked or beyond remaining movement")?;
        route.id=format!("route:{}",serde_json::to_string(&points).unwrap());Ok(route)
    }
    pub(super) fn move_offers(&self)->Vec<Offer>{
        let a=&self.actors[self.active];let mut offers=vec![];
        for (dx,dy,label) in STEPS {
            let cost=if dx!=0.&&dy!=0.{self.diagonal_cost()}else{5};let (x,y)=(a.x+dx,a.y+dy);
            if cost<=self.movement&&self.can_step(self.active,x,y){offers.push(offer(&format!("move:{label}"),format!("Move {label} · {cost} ft"),"move",None,Some((x,y))));}
        }offers
    }
}
