"""Cross-bundle artifact extraction; prefer real artifact over cutscene duplicates."""
import json, math, re, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.game_asset_index import GameIndex,localized_tables
from scripts.export_artifacts import PAIRS
from official_localization import official_text, official_entity

def main():
    g=GameIndex();ru=localized_tables();en=localized_tables('en');pairs=[p.split('|') for p in PAIRS.split(';')]
    clean=lambda s:re.sub(r'\[/?url(?:=[^]]+)?\]','',s)
    text=lambda ref,lang,table='abilities':lang.get(table,{}).get(ref.get('StringID'), '')
    wanted={a.casefold() for _,a in pairs};candidates={}
    for group,components in g.groups.items():
        prefab=g.names.get(group,'')
        for obj,t in components:
            if 'Cooldown' not in t or 'DisplayName' not in t:continue
            title=clean(text(t['DisplayName'],en)).casefold()
            if title not in wanted:continue
            rank=(prefab.startswith('ABL_ART_'),not any(s in prefab.lower() for s in ['legacy','cutscene','_aoe']),bool(text(t.get('Description',{}),ru)))
            if title not in candidates or rank>candidates[title][0]:candidates[title]=(rank,obj,t,prefab)
    result={};destination=ROOT/'web/assets/artifact-icons';destination.mkdir(parents=True,exist_ok=True)
    for title,(_,obj,ability,prefab) in candidates.items():
        queue=list(g.components(obj));seen=set();graph=[]
        while queue and len(graph)<100:
            source,tree=queue.pop(0);key=(source.assets_file.name,source.path_id)
            if key in seen:continue
            seen.add(key);graph.append(tree)
            for effect in tree.get('StatusEffects',[]):
                for key in ['AttackPrefab','AfflictionPrefab']:
                    queue.extend(g.components(g.resolve(source,effect.get(key))))
            for key in ['ExtraAOE','SecondAOE','FollowUpAttacks','Afflictions','AttackPrefab','AfflictionPrefab','AbilityPrefab','AttackPrefabTriggeredOn']:
                refs=tree.get(key,[]);refs=refs if isinstance(refs,list) else [refs]
                for ptr in refs:
                    if isinstance(ptr,dict):queue.extend(g.components(g.resolve(source,ptr)))
        attack=next((t for t in graph if t.get('DamageData',{}).get('Maximum') or t.get('DamageData',{}).get('WeaponDamageMult')),{})
        damage=attack.get('DamageData',{});area=max((float(t.get('BlastRadius',0)) for t in graph),default=0)
        statuses=[s for t in graph for s in t.get('StatusEffects',[])]
        icon='';texture=g.resolve(obj,ability.get('Icon'))
        if texture and texture.type.name=='Texture2D':
            tx=texture.read();filename=re.sub('[^a-zA-Z0-9_-]','_',tx.m_Name)+'.png';tx.image.save(destination/filename);icon='assets/artifact-icons/'+filename
        result[title]={'name':official_text(text(ability['DisplayName'],ru)),'description':official_text(text(ability.get('Description',{}),ru)),
            'icon':icon,'prefab':prefab,'passive':bool(ability.get('Passive')),'oncePerBattle':ability.get('CooldownType') in {1,2},
            'cooldownMode':{0:'Нет',1:'Раз за бой',2:'Раз до отдыха',3:'Перезарядка',4:'Заряды'}.get(ability.get('CooldownType'),'Неизвестно'),
            'range':max(1,math.ceil(attack.get('AttackDistance',0))),'area':math.ceil(area),'angle':float(attack.get('TargetAngle',90)),
            'weaponMultiplier':damage.get('WeaponDamageMult',0),'damageMin':round(damage.get('Minimum',0)),'damageMax':round(damage.get('Maximum',0)),
            'penetration':round(attack.get('DTBypass',0)),'push':round(attack.get('PushDistance',0)),'statuses':statuses,
            'cooldown':max(1,math.ceil(ability.get('Cooldown',0)/10)),
            'graph':[{'prefab':t.get('m_prefabPath',''),**{k:t[k] for k in ['Duration','BlastRadius','Bounces','AfflictionType','DamageData','StatusEffects','IntervalRate'] if k in t}} for t in graph]}
    names={clean(v).casefold():ru.get('items',{}).get(i,v) for i,v in en.get('items',{}).items()}
    items={(names.get(item.casefold()) or (official_entity(item) or {}).get('name_ru') or item):result[ability.casefold()] for item,ability in pairs if ability.casefold() in result}
    output={'items':items,'missing':[p for p in pairs if p[1].casefold() not in result]}
    (ROOT/'catalog/artifact_abilities.json').write_text(json.dumps(output,ensure_ascii=False,indent=2),encoding='utf-8')
    print('Artifacts:',len(items),'missing:',output['missing'])
if __name__=='__main__':main()
