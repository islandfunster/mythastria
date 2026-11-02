// Presentation-only input mapping. Reachability and path costs come from Rust.
const directions={ArrowUp:'North',ArrowRight:'East',ArrowDown:'South',ArrowLeft:'West',w:'North',d:'East',s:'South',a:'West',q:'NorthWest',e:'NorthEast',z:'SouthWest',c:'SouthEast'};
const numpad={Numpad7:'NorthWest',Numpad9:'NorthEast',Numpad1:'SouthWest',Numpad3:'SouthEast'};
export function keyMove(event){
 if(event.altKey||event.ctrlKey||event.metaKey)return null;
 const target=event.target;
 if(target?.isContentEditable||['INPUT','SELECT','TEXTAREA'].includes(target?.tagName))return null;
 const direction=numpad[event.code]??directions[event.key]??directions[String(event.key).toLowerCase()];
 return direction?'move:'+direction:null;
}
export function dragTarget(actor,start,point,targets){
 // Preserve where the token was grabbed; Large tokens retain half-grid centres.
 const x=actor.x+Math.round(point.x-start.x),y=actor.y+Math.round(point.y-start.y);
 return {x,y,unchanged:Math.abs(x-actor.x)<1e-8&&Math.abs(y-actor.y)<1e-8,
   offer:targets.find(t=>Math.abs(t.x-x)<1e-8&&Math.abs(t.y-y)<1e-8)??null};
}
export function mapPoint(root,event){
 const matrix=root.getScreenCTM();if(!matrix)throw Error('Map is not ready');
 const point=root.createSVGPoint();point.x=event.clientX;point.y=event.clientY;
 return point.matrixTransform(matrix.inverse());
}
