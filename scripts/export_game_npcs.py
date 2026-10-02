"""Audit every installed bundle; export every stat-bearing actor, not a wiki shortlist."""
import gc
import json
import re
import sys
from pathlib import Path
import UnityPy
from game_asset_index import GameIndex, GAME,localized_tables

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from official_localization import payload,official_text
from localization import localize_game_text
from item_effects import SKILLS

ATTRS={'Might':'Сила','Finesse':'Искусность','Quickness':'Быстрота','Vitality':'Живучесть','Wits':'Смекалка','Resolve':'Стойкость'}
SKILL_FIELDS={'Athletics':'Атлетика','Lore':'Знания','Mechanics':'Хитроумие','OneHanded':'Одноручное оружие',
    'DualWield':'Парное оружие','TwoHanded':'Двуручное оружие','Staff':'Волшебные посохи','Unarmed':'Безоружный бой',
    'Bows':'Луки','Parry':'Парирование','Dodge':'Уклонение','Thrown':'Дротики',
    'Spell_Fire':'Управление огнём','Spell_Frost':'Управление холодом','Spell_Lightning':'Управление молниями',
    'Spell_Weaken':'Управление истощением','Spell_Heal':'Управление жизнью','Spell_Strengthen':'Управление рвением',
    'Spell_Gravity':'Управление силой','Spell_Stone':'Управление камнем','Spell_Hallucination':'Управление иллюзиями'}


def main():
    index=GameIndex();tables=localized_tables()
    table_names={4:'characters',6:'abilities',5:'items'}
    def text(ref):
        row=tables.get(table_names.get(ref.get('StringTable')),{}).get(ref.get('StringID'),'')
        return localize_game_text(re.sub(r'\[/?url(?:=[^]]+)?\]','',row))
    items=json.loads((ROOT/'catalog/game_items.json').read_text(encoding='utf-8'))
    by_prefab={i['properties']['gameData']['prefab']:i for i in items}
    out=[];scanned=[];seen=set()
    for path in sorted(GAME.glob('*.unity3d')):
        env=next((e for e in index.environments if str(path) in e.files),None)
        if env is None:env=UnityPy.load(str(path))
        count=0
        for obj in env.objects:
            if obj.type.name!='MonoBehaviour' or not obj.serialized_type.node:continue
            if not any(n.m_Name=='BaseMaxHealth' for n in obj.serialized_type.node.m_Children):continue
            stats=obj.read_typetree();name=index.name(obj)
            if not name:
                go=index.resolve(obj,stats.get('m_GameObject',{}))
                name=go.read().m_Name if go else f'Actor_{obj.path_id}'
            ident=path.stem+':'+name+':'+str(obj.path_id)
            if ident in seen:continue
            seen.add(ident);count+=1
            attrs={ru:int(stats.get('Base'+en,10)+stats.get(en+'Bonus',0)) for en,ru in ATTRS.items()}
            skills={ru:int(stats.get(en+'Skill',0)+stats.get(en+'Bonus',0)) for en,ru in SKILL_FIELDS.items()}
            components=index.components(obj)
            equipment=next((t.get('DefaultEquippedItems',{}) for _,t in components if 'DefaultEquippedItems' in t),{})
            equipped=[]
            for slot,ptr in equipment.items():
                if not isinstance(ptr,dict):continue
                prefab=index.name(index.resolve(obj,ptr));item=by_prefab.get(prefab)
                if item:equipped.append({'slot':slot,'name':item['name'],'prefab':prefab,'icon':item['image_url'],
                    'armor':item['armor'],'damageMin':item['damage_min'],'damageMax':item['damage_max'],'category':item['category']})
            abilities=[]
            for ptr in [*stats.get('Abilities',[]),*stats.get('Talents',[])]:
                target=index.resolve(obj,ptr)
                for _,tree in index.components(target):
                    if 'DisplayName' in tree and 'Cooldown' in tree:
                        ability_name=text(tree['DisplayName'])
                        if ability_name and not any(a['name']==ability_name for a in abilities):
                            abilities.append({'name':ability_name,'description':text(tree.get('Description',{})),
                                'passive':bool(tree.get('Passive')),'prefab':index.name(target)})
            attack=next((t for _,t in components if 'DamageData' in t),{})
            weapons=[i for i in equipped if i['slot'] in {'PrimaryWeapon','SecondaryWeapon'}]
            low=sum(i['damageMin'] for i in weapons) or round(attack.get('DamageData',{}).get('Minimum',0))
            high=sum(i['damageMax'] for i in weapons) or round(attack.get('DamageData',{}).get('Maximum',0))
            weapon_skills={'Одноручное оружие':'Одноручное оружие','Двуручное оружие':'Двуручное оружие','Парное оружие':'Парное оружие','Луки':'Луки','Метательное оружие':'Дротики','Посохи':'Волшебные посохи'}
            attack_skill=weapon_skills.get(weapons[0]['category'],'Безоружный бой') if weapons else 'Безоружный бой'
            title=text(stats.get('DisplayName',{})) or 'Неименованный противник'
            if stats.get('OverrideName'):title=official_text(stats['OverrideName'],title)
            service=bool(re.search(r'proto|test|temp|dummy|debug',name,re.I))
            companion=bool(re.search(r'companion|pc_hero|player',name,re.I))
            team=next((t.get('CurrentTeam') for _,t in components if 'CurrentTeam' in t),None)
            out.append({'key':ident,'name':title,'level':max(1,int(stats.get('Level',1))),
                'healthMax':max(1,round(stats.get('BaseMaxHealth',100)*stats.get('MaxHealthMultiplier',1))),
                'armor':sum(i['armor'] for i in equipped),'movement':5,'attributes':attrs,'skills':skills,
                'defenses':{'Парирование':skills['Парирование'],'Уклонение':skills['Уклонение'],
                    'Выносливость':round(stats.get('BaseEnduranceDefense',30)+stats.get('EnduranceDefenseBonus',0)),
                    'Воля':round(stats.get('BaseWillDefense',30)+stats.get('WillDefenseBonus',0)),
                    'Магия':round(stats.get('BaseMagicDefense',30)+stats.get('SpellDefenseBonus',0))},
                'attack':{'damageMin':low,'damageMax':high,'accuracy':skills.get(attack_skill,0),
                    'range':round(attack.get('AttackDistance',1)) or 1},'equipment':equipped,'abilities':abilities,
                'portrait':'','color':'#a92339','category':'Служебные' if service else 'Спутники' if companion else 'Противники и НПС',
                'source':{'archive':path.name,'prefab':name,'team':team,
                    'note':'Базовые параметры префаба. Масштабирование уровня и сложности сцены не включено.'},
                'rawStats':{k:v for k,v in stats.items() if k.startswith('Base') or k in ['CharacterRace','CharacterDefenseCategory','Level','AfflictionImmunities']}})
        scanned.append({'archive':path.name,'actors':count})
        if len(scanned)%20==0:print('Scanned',len(scanned),'actors',len(out),flush=True)
        if env not in index.environments:del env;gc.collect()
    destination=ROOT/'catalog/game_npcs.json'
    destination.write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8')
    audit={'scanned':scanned,'actors':len(out),'service':sum(n['category']=='Служебные' for n in out),
           'unnamed':sum(n['name']=='Неименованный противник' for n in out)}
    (ROOT/'catalog/game_npc_audit.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2),encoding='utf-8')
    print('Exported',len(out),'actors from',len(scanned),'bundles',flush=True)


if __name__=='__main__':main()
