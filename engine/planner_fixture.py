"""FG-EXIT-01 step 4 (GM 2026-10-26): the old bridge's record model, kept for the planner's own tests.

The planner (mythastria_core/ai_turn.py) reads combatants and actions in the shape the old bridge built from Fantasy
Grounds' synced records (normalize_combatant, rank_powparse_state); sim/creature_turns.py now builds that shape from the
fight state. The planner's tests were written against the bridge's records, so these pieces of the bridge (no HTTP, no
FG connection) were cut out of mythastria_core/core_service.py when it was archived (archive/fg_exit_2026-10-26/) and
live on here as a test fixture: the same code, the same state dictionaries."""
import re, sys, threading
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "mythastria_core"))
import test_support  # noqa: E402,F401  (temporary settings, rules cache and plan cache, as before)
import ai_turn  # noqa: E402
import map_walls  # noqa: E402
from diagnostics import Recorder  # noqa: E402

diagnostics = Recorder()
lock = threading.Lock()
combat = {"actors": {}, "distances": {}, "reported_count": None, "updated": None}
powparse = {"records": {}, "reported_count": None, "updated": None}
awareness = {"aware": set(), "search": {}, "noise": {}}
ai_turns = {"mode": "off", "model": "", "pending": None, "seq": 0, "open_maps": []}
narration_queue, mechanical_action_queue, held_narration = [], [], {}

def now(): return datetime.now().isoformat(timespec="seconds")

def score_powparse_attempt(att):
    """Rank a parseNPCPower return without inventing mechanics."""
    if att.get("ok") != "1":
        return -1000
    score=1
    for f in att.get("fields",[]):
        k=(f.get("key") or "").lower()
        v=(f.get("value") or "").lower()
        # Strongest evidence: an explicit returned action type.
        if k.endswith(".type") or k=="type":
            if v=="attack": score += 100
            elif v=="damage": score += 70
            elif v in ("save","heal","effect"): score += 20
        if "attack" in k: score += 12
        if "damage" in k or "dmg" in k: score += 10
        if k.endswith(".modifier") or k.endswith(".mod") or k in ("modifier","mod"): score += 8
        if "range" in k: score += 5
        if "dice" in k: score += 5
        if "label" in k or k.endswith(".name"): score += 3
        if v=="attack": score += 25
        if v=="damage": score += 20
    return score

def rank_powparse_state(state):
    ranked=[]
    for _,rec in state.get("records",{}).items():
        for sig,att in rec.get("attempts",{}).items():
            ranked.append({
                "score":score_powparse_attempt(att),
                "ctpath":rec.get("ctpath",""),
                "actor_name":rec.get("actor_name",""),
                "power_name":rec.get("power_name",""),
                "origin":rec.get("origin",""),
                "node_path":rec.get("node_path",""),
                "description":rec.get("description",""),
                "signature":sig,
                "ok":att.get("ok","0"),
                "error":att.get("error",""),
                "fields":att.get("fields",[]),
            })
    ranked.sort(key=lambda r:r["score"],reverse=True)
    return ranked

def ensure_combatant(ctpath):
    if ctpath not in combat["actors"]:
        combat["actors"][ctpath]={"name":"","fields":{}}
    return combat["actors"][ctpath]

def combat_field_value(actor, *names):
    fields=actor.get("fields",{})
    for name in names:
        v=fields.get(name,{}).get("value","")
        if v!="":
            return v
    return ""

def _ct_raw(actor):
    return {k:v.get("value","") for k,v in actor.get("fields",{}).items()}

def _records_under(actor, root):
    """Group CT leaf fields below root.<recordid>.* without assuming record IDs."""
    raw=_ct_raw(actor)
    groups={}
    pattern=re.compile(r"^"+re.escape(root)+r"\.([^.]+)(?:\.(.+))?$")
    for rel,value in raw.items():
        m=pattern.match(rel)
        if not m:
            continue
        rec=root+"."+m.group(1)
        leaf=m.group(2) or ""
        groups.setdefault(rec,{})
        if leaf:
            groups[rec][leaf]=value
    return groups

def normalize_effects(actor):
    effects=[]
    for path,data in sorted(_records_under(actor,"effects").items()):
        effect={"path":path,"raw_fields":data}
        for outkey,candidates in {
            "label":["label","name","effect"],
            "active":["isactive","active"],
            "gm_only":["isgmonly","gmonly"],
            "duration":["duration"],
            "duration_unit":["durunit","durationunit"],
            "source":["source_name","source","source_name"],
        }.items():
            for key in candidates:
                if data.get(key,"")!="":
                    effect[outkey]=data[key]
                    break
        effects.append(effect)
    return effects

def normalize_targets(actor):
    targets=[]
    # Different CoreRPG/ruleset versions/extensions can use different roots.
    for rootname in ("targets","targeting","targetlist"):
        for path,data in sorted(_records_under(actor,rootname).items()):
            target={"path":path,"root":rootname,"raw_fields":data}
            for outkey,candidates in {
                "target_ref":["noderef","node","recordname","target","ctnode"],
                "name":["name","targetname"],
            }.items():
                for key in candidates:
                    if data.get(key,"")!="":
                        target[outkey]=data[key]
                        break
            targets.append(target)
    return targets

def normalize_combatant(ctpath,actor):
    fields=actor.get("fields",{})
    raw=_ct_raw(actor)
    return {
        "path":ctpath,
        "name":actor.get("name",""),
        "active":combat_field_value(actor,"active"),
        "friend_foe":combat_field_value(actor,"friendfoe"),
        "initiative":combat_field_value(actor,"initresult","initiative"),
        "visible":combat_field_value(actor,"tokenvis","visible"),
        "hp_total":combat_field_value(actor,"hptotal","hp.total"),
        "wounds":combat_field_value(actor,"wounds","hp.wounds"),
        "temporary_hp":combat_field_value(actor,"hptemp","hp.temporary"),
        "token": {
            "ref_node":combat_field_value(actor,"tokenrefnode"),
            "ref_id":combat_field_value(actor,"tokenrefid"),
            "asset":combat_field_value(actor,"token"),
            "scale":combat_field_value(actor,"tokenscale"),
            "visible":combat_field_value(actor,"tokenvis","visible"),
        },
        "actor_link": {
            "value":combat_field_value(actor,"link"),
            "class":(
                combat_field_value(actor,"link.class")
                or (combat_field_value(actor,"link").split(":",1)[0]
                    if ":" in combat_field_value(actor,"link") else "")
            ),
            "recordname":(
                combat_field_value(actor,"link.recordname")
                or (combat_field_value(actor,"link").split(":",1)[1]
                    if ":" in combat_field_value(actor,"link") else "")
            ),
            "source_class":combat_field_value(actor,"sourcelink.class"),
            "source_recordname":combat_field_value(actor,"sourcelink.recordname"),
        },
        "effects":normalize_effects(actor),
        "targets":normalize_targets(actor),
        "raw_fields":raw
    }

def _set_field(actor,key,value):
    actor.setdefault("fields",{})[key]={"datatype":"number","value":str(value),"childcount":"0","depth":"1"}

def _set_effects(actor,items):
    """v0.7.35: bring a combatant's synced effects up to date from a turn notice.
    v0.7.35 (reviewer finding): items are "<FG effect node id>=<label>". Effects keep their real FG ids
    (the page's Queue remove button names that node) and their other synced fields (duration,
    active status); only the label is refreshed. Effects FG no longer lists are dropped; new ones are
    added under their real id. Items without a valid id are ignored."""
    fields=actor.setdefault("fields",{})
    current={}
    for item in items:
        eid,sep,label=item.partition("=")
        if sep and re.fullmatch(r"[A-Za-z0-9_-]{1,40}",eid):
            current[eid]=label.replace("\x1f",";")[:200]  # FG sends ";" as byte 31
    for k in [k for k in fields if k.startswith("effects.") and k.split(".")[1] not in current]:
        del fields[k]
    for eid,label in current.items():
        off=label.startswith("\x1e")   # v0.7.58: FG marks an effect switched off (isactive 0) with byte 30
        fields["effects.%s.label"%eid]={"datatype":"string","value":label.lstrip("\x1e"),"childcount":"0","depth":"3"}
        fields["effects.%s.isactive"%eid]={"datatype":"number","value":"0" if off else "1","childcount":"0","depth":"3"}

def _set_daily_uses(actor,packed):
    """v0.7.36: the acting NPC's N/day spell use counts from the turn notice, "^id=used^id=used"."""
    fields=actor.setdefault("fields",{})
    for item in (packed or "").split("^"):
        sid,sep,used=item.partition("=")
        if sep and re.fullmatch(r"[A-Za-z0-9_-]{1,40}",sid) and re.fullmatch(r"\d{1,3}",used):
            fields["innatespells.%s.aibridge_used"%sid]={"datatype":"number","value":used,"childcount":"0","depth":"3"}

def _set_pos(actor,x,y,mapname):
    """v0.7.45: token centre (map pixels) and map of a combatant, from the turn notice."""
    try: fx,fy=float(x),float(y)
    except (TypeError,ValueError): return
    if abs(fx)<1e7 and abs(fy)<1e7:
        f=actor.setdefault("fields",{})
        f["pos.x"]={"datatype":"number","value":str(fx),"childcount":"0","depth":"1"}
        f["pos.y"]={"datatype":"number","value":str(fy),"childcount":"0","depth":"1"}
        f["pos.map"]={"datatype":"string","value":str(mapname)[:300],"childcount":"0","depth":"1"}

def apply_turn_notice(ctpath,name,friendfoe,wounds,hptotal,packed,effects=None,daily=None,round_no=None,bonus=None,
                      slot=None,space=None,multi=None,rx=None):
    """Update synced state from FG's turn-start notice: active flag, wounds/HP, distances from the actor,
    and (v0.7.34) every combatant's current effect labels."""
    with lock:
        actors=combat["actors"]
        for p,a in actors.items():
            _set_field(a,"active",1 if p==ctpath else 0)
        me=actors.setdefault(ctpath,{"name":name,"fields":{}})
        me["name"]=name or me.get("name","")
        if friendfoe: me.setdefault("fields",{})["friendfoe"]={"datatype":"string","value":friendfoe,"childcount":"0","depth":"1"}
        _set_field(me,"wounds",wounds); _set_field(me,"hptotal",hptotal)
        if effects is not None: _set_effects(me,effects.split("^"))
        if daily is not None: _set_daily_uses(me,daily)
        if round_no is not None and re.fullmatch(r"\d{1,5}",round_no):
            if combat.get("round") and combat["round"]>1 and int(round_no)==1:
                forget_awareness("the combat round went back to 1 (new encounter)")   # v0.7.78
            combat["round"]=int(round_no)
        # v0.7.39: FG says whether this NPC already used its bonus action this turn
        combat["bonus_used"]=ctpath if bonus=="1" else None
        combat["slot_used"]=ctpath if slot=="1" else None  # v0.7.40: one spell slot per turn
        if rx is not None:   # v0.7.57: FG lists the CT ids whose reaction is used (opportunity attacks)
            used={x.strip() for x in rx.split(",") if re.fullmatch(r"[\w-]{1,40}",x.strip())}
            for p,a in actors.items(): _set_field(a,"reaction",1 if p.rsplit(".",1)[-1] in used else 0)
        # v0.7.52: the Multiattack attacks this NPC already made this turn (FG's list of action names)
        items=[n[:121] for n in (multi or "").split("~") if n][:8]   # v0.7.60: "+" marks an attack that hit
        combat["multi_done"]=(ctpath,[n[:-1] if n.endswith("+") else n for n in items],[n.endswith("+") for n in items])
        if space:  # v0.7.45: the actor's token, the map grid, FG's diagonal rule and the actor's speed
            mapname=space.get("map","")
            _set_pos(me,space.get("ax"),space.get("ay"),mapname)
            if space.get("speed"):
                me.setdefault("fields",{})["speed"]={"datatype":"string","value":space["speed"][:80],"childcount":"0","depth":"1"}
            try: grid=float(space.get("grid") or 0); units=float(space.get("units") or 0)
            except ValueError: grid=units=0
            try: grid_h=float(space.get("gridh") or 0) or grid   # v0.7.73: row height (rectangular grids)
            except ValueError: grid_h=grid
            diag=space.get("diag") if space.get("diag") in ("1","1.5","*") else "1"
            try: moved=max(0.0,min(10000.0,float(space.get("moved") or 0)))   # v0.7.56: feet moved this turn
            except ValueError: moved=0.0
            try: moved_diag=max(0,min(1000,int(space.get("mdiag") or 0)))   # v0.8.4 R083-05: diagonals moved this turn
            except ValueError: moved_diag=0
            combat["space"]={"map":mapname[:300],"mapname":space.get("mapname","")[:120],"grid":grid,"grid_h":grid_h,"units":units,
                             "diag":diag,"moved":moved,"moved_diag":moved_diag}
        dist=combat.setdefault("distances",{})
        for k in [k for k in dist if k.startswith(ctpath+"|")]: del dist[k]
        for item in (packed or "").split(";"):
            bits=item.split("~")
            if len(bits) not in (4,5,7) or not bits[0].startswith("combattracker.list."): continue
            other,ft,w,hp=bits[:4]
            if other in actors:
                _set_field(actors[other],"wounds",w); _set_field(actors[other],"hptotal",hp)
                if len(bits)>=5: _set_effects(actors[other],bits[4].split("^"))
                if len(bits)==7 and space: _set_pos(actors[other],bits[5],bits[6],space.get("map",""))
            try:
                f=float(ft)
                if 0<=f<100000: dist[ctpath+"|"+other]=f
            except ValueError:
                pass
        combat["updated"]=now()

def recent_noise():
    """v0.7.93: CT paths that fought this round or the last (never a later round: an earlier combat's leftovers)."""
    rnd=combat.get("round") or 0
    return [p for p,r in (awareness.get("noise") or {}).items() if rnd-1<=r<=rnd]

def forget_awareness(reason):
    """v0.7.78: NPCs forget the party (new encounter, Test lab Reset, or the GM's button). Call with lock held."""
    if awareness["aware"] or awareness["search"] or awareness.get("noise"):
        awareness["aware"].clear(); awareness["search"].clear(); awareness.setdefault("noise",{}).clear()
        diagnostics.event("ai-npc-turn","NPCs forget the party: "+reason)

def awareness_flags(ctpath,tseq):
    """Space flags for one decision (call with lock held, or accept a racy read)."""
    seen=awareness["search"].get(ctpath)
    return {"aware":ctpath in awareness["aware"],"searched":seen[1] if seen and seen[0]==str(tseq) else None,
            "noise":recent_noise(),   # v0.7.93 HEAR-01
            "perception_dc":ai_turns.get("perception_dc",ai_turn.DEFAULT_PERCEPTION_DC)}

def manual_space(combatants,actor):
    """v0.7.73: the one-off suggestion tool has no turn notice (no speed or grid), so it never moves tokens; on a map
    with confirmed walls it still refuses targets behind a wall or closed door."""
    raw=(combatants.get(actor) or {}).get("raw_fields") or {}
    walls=map_walls.for_map(raw.get("pos.map"))
    # aware: the GM asked for this NPC's attack, so no Search (v0.7.77)
    out={"map":raw.get("pos.map"),"allow_move":False,"walls":map_walls.blocking_segments(walls) if walls else None,
         "lighting":map_walls.lighting(walls),"aware":True,"manual":True}
    # v0.7.85 (gpt-5.5 review of v0.7.84): the last turn notice's grid for the same map, so lighting can be measured
    sp=combat.get("space") or {}
    if sp.get("map") and sp.get("map")==raw.get("pos.map"):
        out.update({k:sp.get(k) for k in ("grid","grid_h","units","diag")})
    return out

def turn_space(space,mode,open_maps):
    """Movement settings for one AI decision. v0.7.45: Autopilot moves tokens only on open-ground maps; v0.7.57:
    Autopilot avoids provoking moves; v0.7.73 WALLS-01b: a map with confirmed walls (map_walls) counts too, and its
    blocking walls/closed doors go to the planner."""
    space=dict(space or {})
    walls=map_walls.for_map(space.get("map"))
    space["walls"]=map_walls.blocking_segments(walls) if walls else None
    space["doors"]=map_walls.closed_door_segments(walls) if walls else None   # v0.7.93 HEAR-01
    space["door_list"]=map_walls.closed_doors(walls) if walls else None       # v0.7.95 DOORS-01
    space["lighting"]=map_walls.lighting(walls)   # v0.7.81 LIGHT-01
    space["water"]=map_walls.water(walls)         # SWIM-01 (2026-10-19): Swim Speed in the map's water areas
    space["avoid_provoking"]=mode=="auto"
    space["allow_move"]=bool(space.get("map")) and (mode!="auto" or space.get("map") in open_maps or bool(walls))
    return space
