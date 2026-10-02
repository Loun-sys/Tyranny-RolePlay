"""Extract artifact ability icons, localization and serialized combat data."""
import collections
import json
import re
import sys
from pathlib import Path
import UnityPy

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from official_localization import official_entity, official_text, payload

PAIRS='''Deathbringer|Scythe of Years;Dauntless|Stalwart Surge;Final Scream|Blast of Confusion;Heart\'s Blood|Heartseeker;Sunlance|Sun\'s Rage;Tempest|Stormwheel;Peacemaker|Bladestorm;Gravebow|Chromatic Arrow;Staff of Hours|Slowing the Sands;Staff of Cairn|Evocation of Cairn;Hammer of Sunder|Shockwave;Snowfang|Winter\'s Fang;Penumbra|Shadow\'s Treachery;Edict\'s Crescent|Echoes of the Storm;Edict\'s Mallet|Echoes of the Storm;Wave\'s Crest|Sanguine Gift;Circular Reason|Rebounding Blade;Steadfast Insignia|Steadfast Stand;Scales of Mercy|Tipping the Scales;Banner of Ardent|Force of Peace;Commander\'s Plate|Redeploy;Hierarch\'s Robes|Aspect of Nightmares;Infused Shadows|Drowned in Darkness;Nightwalker\'s Boots|Shadow Stride;Bindings of Shadows|Shadow\'s Embrace;Alchemist\'s Gloves|Orb of Life;Songbird\'s Encore|Resounding Crescendo;Weeping Whispers|The Quick and the Dead;Helm of the First Regent|Bend the Knee;Face of Judgment|Archon\'s Judgment;Magebane Helm|Arcane Unravelling;Azure Shield|Champion\'s Boon;The Baneward|Leech Energy'''


def main():
    result={}; destination=ROOT/'web/assets/artifact-icons';destination.mkdir(parents=True,exist_ok=True)
    tables={name:{r['id']:r for r in rows} for name,rows in payload()['tables'].items()}
    pairs=[pair.split('|') for pair in PAIRS.split(';')]
    wanted={ability.casefold():item for item,ability in pairs}
    def text(ref):return tables['abilities'].get(ref.get('StringID'),{}).get('ru','')
    for bundle in ['abilities','dlc00','dlc01','dlc02','dlc03']:
        env=UnityPy.load(f'C:/Games/Tyranny/Data/bundles/{bundle}.unity3d')
        objects={o.path_id:o for o in env.objects};groups=collections.defaultdict(list);names={};components={}
        for obj in env.objects:
            if obj.type.name=='GameObject':names[obj.path_id]=obj.read().m_Name
            if obj.type.name=='MonoBehaviour':
                t=obj.read_typetree();components[obj.path_id]=t;groups[t.get('m_GameObject',{}).get('m_PathID')].append(t)
        for ident,trees in groups.items():
            name=names.get(ident,'')
            ability=next((t for t in trees if 'Cooldown' in t and 'DisplayName' in t),None)
            if not ability or 'legacy' in name.casefold():continue
            row=tables['abilities'].get(ability['DisplayName'].get('StringID'),{})
            english=re.sub(r'\[/?url(?:=[^]]+)?\]','',row.get('en',''))
            title=english.casefold()
            if title not in wanted:continue
            def related(ptr):
                path=ptr.get('m_PathID');return groups.get(path) or ([components[path]] if path in components else [])
            data=list(trees)
            for tree in list(data):
                for key in ['ExtraAOE','SecondAOE']:
                    for child in related(tree.get(key,{})):
                        data.append(child)
            attack=next((t for t in data if t.get('DamageData',{}).get('Maximum',0)>0 or t.get('DamageData',{}).get('WeaponDamageMult',0)>0),{})
            area=next((t for t in data if t.get('BlastRadius',0)>0),{})
            image=''; obj=objects.get(ability.get('Icon',{}).get('m_PathID'))
            if obj and obj.type.name=='Texture2D':
                tx=obj.read();filename=re.sub('[^a-zA-Z0-9_-]','_',tx.m_Name)+'.png';tx.image.save(destination/filename);image='assets/artifact-icons/'+filename
            damage=attack.get('DamageData',{})
            result[title]={'name':official_text(row.get('ru',''),row.get('ru','')),'description':official_text(text(ability['Description']),text(ability['Description'])),
                'icon':image,'prefab':name,'passive':bool(ability.get('Passive')),'oncePerBattle':ability.get('CooldownType') in {1,2},
                'cooldownMode':{0:'Нет',1:'Раз за бой',2:'Раз до отдыха',3:'Перезарядка',4:'Заряды'}.get(ability.get('CooldownType'),'Неизвестно'),
                'range':max(1,round(attack.get('AttackDistance',0))),'area':round(area.get('BlastRadius',0)),
                'weaponMultiplier':damage.get('WeaponDamageMult',0),
                'damageMin':round(damage.get('Minimum',0)),'damageMax':round(damage.get('Maximum',0)),
                'penetration':round(attack.get('DTBypass',0)),'push':round(attack.get('PushDistance',0)),
                'statuses':[*ability.get('StatusEffects',[]),*attack.get('StatusEffects',[])],
                'cooldown':max(1,__import__('math').ceil(ability.get('Cooldown',0)/10))}
    items={}
    for item,ability in pairs:
        row=official_entity(item) or {}; title=ability.casefold()
        if title in result:items[row.get('name_ru',official_text(item))]=result[title]
    output={'items':items,'missing':[pair for pair in pairs if pair[1].casefold() not in result]}
    (ROOT/'catalog/artifact_abilities.json').write_text(json.dumps(output,ensure_ascii=False,indent=2),encoding='utf-8')
    print('Artifacts:',len(items),'missing:',output['missing'])


if __name__=='__main__':main()
