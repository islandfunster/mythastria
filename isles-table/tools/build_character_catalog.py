"""Generate the small, reviewed SRD 5.2.1 creation catalog. Source PDF is external input."""
import json,re,sys
from pathlib import Path
text=Path(sys.argv[1]).read_text();pages=text.split('\f')
classes={}
rows=[
('Barbarian',12,'str con',2,'Animal Handling,Athletics,Intimidation,Nature,Perception,Survival','light medium shield','martial',75,28,0,0,None,'Rage,Unarmored Defense,Weapon Mastery'),
('Bard',8,'dex cha',3,'*','light','simple',90,31,2,4,'cha','Bardic Inspiration,Spellcasting'),
('Cleric',8,'wis cha',2,'History,Insight,Medicine,Persuasion,Religion','light medium shield','simple',110,36,3,4,'wis','Spellcasting,Divine Order'),
('Druid',8,'int wis',2,'Animal Handling,Arcana,Insight,Medicine,Nature,Perception,Religion,Survival','light shield','simple',50,41,2,4,'wis','Spellcasting,Druidic,Primal Order'),
('Fighter',10,'str con',2,'Acrobatics,Animal Handling,Athletics,History,Insight,Intimidation,Persuasion,Perception,Survival','light medium heavy shield','martial',155,47,0,0,None,'Fighting Style,Second Wind,Weapon Mastery'),
('Monk',8,'str dex',2,'Acrobatics,Athletics,History,Insight,Religion,Stealth','','monk',50,49,0,0,None,'Martial Arts,Unarmored Defense'),
('Paladin',10,'wis cha',2,'Athletics,Insight,Intimidation,Medicine,Persuasion,Religion','light medium heavy shield','martial',150,53,0,2,'cha','Lay On Hands,Spellcasting,Weapon Mastery'),
('Ranger',10,'str dex',3,'Animal Handling,Athletics,Insight,Investigation,Nature,Perception,Stealth,Survival','light medium shield','martial',150,57,0,2,'wis','Spellcasting,Favored Enemy,Weapon Mastery'),
('Rogue',8,'dex int',4,'Acrobatics,Athletics,Deception,Insight,Intimidation,Investigation,Perception,Persuasion,Sleight of Hand,Stealth','light','rogue',100,62,0,0,None,'Expertise,Sneak Attack,Thieves’ Cant,Weapon Mastery'),
('Sorcerer',6,'con cha',2,'Arcana,Deception,Insight,Intimidation,Persuasion,Religion','','simple',50,64,4,2,'cha','Spellcasting,Innate Sorcery'),
('Warlock',8,'wis cha',2,'Arcana,Deception,History,Intimidation,Investigation,Nature,Religion','light','simple',100,70,2,2,'cha','Eldritch Invocations,Pact Magic'),
('Wizard',6,'int wis',2,'Arcana,History,Insight,Investigation,Medicine,Nature,Religion','','simple',55,77,3,4,'int','Spellcasting,Ritual Adept,Arcane Recovery')]
skills='Acrobatics,Animal Handling,Arcana,Athletics,Deception,History,Insight,Intimidation,Investigation,Medicine,Nature,Perception,Performance,Persuasion,Religion,Sleight of Hand,Stealth,Survival'.split(',')
for name,hd,saves,n,sk,arm,weap,gold,page,can,prep,casting,features in rows:
 classes[name]={'hit_die':hd,'saves':saves.split(),'skill_count':n,'skills':skills if sk=='*' else sk.split(','),'armor':arm.split(),'weapons':weap,'gold':gold,'page':page,'cantrips':can,'prepared':prep,'casting':casting,'features':features.split(',')}
backgrounds={
 'Acolyte':{'abilities':['int','wis','cha'],'skills':['Insight','Religion'],'feat':'Magic Initiate (Cleric)','tool':'Calligrapher’s Supplies'},
 'Criminal':{'abilities':['dex','con','int'],'skills':['Sleight of Hand','Stealth'],'feat':'Alert','tool':'Thieves’ Tools'},
 'Sage':{'abilities':['con','int','wis'],'skills':['Arcana','History'],'feat':'Magic Initiate (Wizard)','tool':'Calligrapher’s Supplies'},
 'Soldier':{'abilities':['str','dex','con'],'skills':['Athletics','Intimidation'],'feat':'Savage Attacker','tool':'Gaming Set (choose kind)'}}
species={n:{'speed':35 if n=='Goliath' else 30,'sizes':['Small'] if n in ['Gnome','Halfling'] else ['Small','Medium'] if n in ['Human','Tiefling'] else ['Medium'],'page':p} for n,p in [('Dragonborn',84),('Dwarf',84),('Elf',84),('Gnome',85),('Goliath',85),('Halfling',86),('Human',86),('Orc',86),('Tiefling',86)]}
# Parse spell identity/level/class lists from descriptions, never from a non-SRD spell compendium.
spells=json.loads(Path(__file__).with_name('srd_spells_521.json').read_text())
assert len(spells)==84 and all(len(s['name'])<40 for s in spells)
# Melee weapon baseline; full sheet may hold additional equipment and ranged spells.
weapons=[]
for name,die,count,cost,martial,finesse,two,reach in [
 ('Unarmed Strike',1,1,0,False,False,False,5),('Club',4,1,.1,False,False,False,5),('Dagger',4,1,2,False,True,False,5),('Greatclub',8,1,.2,False,False,True,5),('Handaxe',6,1,5,False,False,False,5),('Javelin',6,1,.5,False,False,False,5),('Light Hammer',4,1,2,False,False,False,5),('Mace',6,1,5,False,False,False,5),('Quarterstaff',6,1,.2,False,False,False,5),('Sickle',4,1,1,False,False,False,5),('Spear',6,1,1,False,False,False,5),('Battleaxe',8,1,10,True,False,False,5),('Flail',8,1,10,True,False,False,5),('Glaive',10,1,20,True,False,True,10),('Greataxe',12,1,30,True,False,True,5),('Greatsword',6,2,50,True,False,True,5),('Halberd',10,1,20,True,False,True,10),('Longsword',8,1,15,True,False,False,5),('Maul',6,2,10,True,False,True,5),('Morningstar',8,1,15,True,False,False,5),('Pike',10,1,5,True,False,True,10),('Rapier',8,1,25,True,True,False,5),('Scimitar',6,1,25,True,True,False,5),('Shortsword',6,1,10,True,True,False,5),('Trident',8,1,5,True,False,False,5),('Warhammer',8,1,15,True,False,False,5),('War Pick',8,1,5,True,False,False,5),('Whip',4,1,2,True,True,False,10)]:
 weapons.append(dict(name=name,die=die,count=count,cost=cost,martial=martial,finesse=finesse,two=two,reach=reach,light=name in ['Club','Dagger','Handaxe','Light Hammer','Sickle','Scimitar','Shortsword']))
armor=[dict(name=n,ac=ac,category=cat,cost=cost,strength=st) for n,ac,cat,cost,st in [('None',10,'none',0,0),('Padded Armor',11,'light',5,0),('Leather Armor',11,'light',10,0),('Studded Leather Armor',12,'light',45,0),('Hide Armor',12,'medium',10,0),('Chain Shirt',13,'medium',50,0),('Scale Mail',14,'medium',50,0),('Breastplate',14,'medium',400,0),('Half Plate Armor',15,'medium',750,0),('Ring Mail',14,'heavy',30,0),('Chain Mail',16,'heavy',75,13),('Splint Armor',17,'heavy',200,15),('Plate Armor',18,'heavy',1500,15)]]
result=dict(version='SRD 5.2.1',url='https://media.dndbeyond.com/compendium-images/srd/5.2/SRD_CC_v5.2.1.pdf',classes=classes,backgrounds=backgrounds,species=species,skills=skills,spells=sorted(spells,key=lambda x:x['name']),weapons=weapons,armor=armor,origin_feats=['Alert','Magic Initiate (Cleric)','Magic Initiate (Druid)','Magic Initiate (Wizard)','Savage Attacker','Skilled'])
Path('dist/srd-creation.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
print('SRD catalog:',len(classes),'classes,',len(species),'species,',len(spells),'level 0–1 spells')
