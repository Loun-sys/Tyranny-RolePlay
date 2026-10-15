"""Additive mechanical extraction of equipment stored in recipes.unity3d."""
import copy,json,re,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from game_asset_index import GameIndex,localized_tables
from audit_weapon_source import FIELDS
from crafting import QUALITIES,normalize_quality
from localization import localize_game_text


def extract():
    index=GameIndex(extra_bundles=['recipes']);tables=localized_tables();rows=[];weapons={}
    def clean(t):return {k:copy.deepcopy(v) for k,v in t.items() if not k.startswith('m_')}
    def text(ref):
        table={5:'items',6:'abilities',16:'itemmods'}.get((ref or {}).get('StringTable'))
        return localize_game_text(re.sub(r'\[/?url(?:=[^]]+)?\]','',tables.get(table,{}).get((ref or {}).get('StringID'),''))).strip()
    def attack(t):return {**{k:t[k] for k in FIELDS if k in t},'DamageData':{k:t.get('DamageData',{})[k] for k in ['Minimum','Maximum','Type','BestOfType'] if k in t.get('DamageData',{})}} if t else {}
    def graph(source,ptr):
        pending=[(o,t) for o,t in index.components(index.resolve(source,ptr))];seen=set();out=[]
        while pending:
            obj,t=pending.pop(0);key=(obj.assets_file.name,obj.path_id)
            if key in seen:continue
            seen.add(key);entry=clean(t);entry.update(prefab=index.name(obj),localizedName=text(t.get('DisplayName')),localizedDescription=text(t.get('Description')));out.append(entry)
            for nested in [t,*t.get('StatusEffects',[])]:
                for field in ['AttackPrefab','AfflictionPrefab','AbilityPrefab','ExtraAOE','SecondAOE','FollowUpAttacks','Afflictions']:
                    refs=nested.get(field,[]);refs=refs if isinstance(refs,list) else [refs]
                    for ref in refs:
                        if isinstance(ref,dict):pending.extend(index.components(index.resolve(obj,ref.get('AfflictionPrefab',ref))))
        return out
    for (asset,pid),item in index.trees.items():
        if 'Value' not in item or 'DisplayName' not in item:continue
        obj=index.assets[asset].objects[pid];prefab=index.name(obj)
        if not prefab.startswith('KenrickRecruit_'):continue
        components=index.components(obj);primary=next((t for _,t in components if 'DamageData' in t and 'AttackDistance' in t),{})
        thrown=next(((o,t) for o,t in components if t.get('RangedAttack',{}).get('m_PathID')),None)
        ranged=next((t for _,t in index.components(index.resolve(thrown[0],thrown[1]['RangedAttack'])) if 'DamageData' in t and 'AttackDistance' in t),{}) if thrown else {}
        q=next(t for _,t in components if t.get('QualityScaleID'))
        kind='shield' if not item.get('PrimaryWeaponSlot') else 'weapon'
        info={'id':q['QualityScaleID'],'level':q.get('QualityScaleLevel',1),'kind':kind}
        name=text(item['DisplayName'])+' ('+QUALITIES[info['level']]+')'
        tx=index.resolve(obj,item.get('IconTexture'));filename=re.sub(r'[^a-zA-Z0-9_-]','_',tx.read().m_Name)+'.png'
        image='assets/item-icons/'+filename
        if not (ROOT/'web'/image).is_file():raise ValueError('Missing source icon: '+image)
        category='Щиты' if kind=='shield' else {'5':'Одноручное оружие','7':'Двуручное оружие','10':'Луки'}[str(item['SkillType'])]
        mods=[]
        for ptr in item.get('ItemMods',[]):
            modobj=index.resolve(obj,ptr);t=index.tree(modobj)
            if not t:raise ValueError('Missing source mod: '+prefab)
            mod=clean(t);mod.update(localizedName=text(t.get('DisplayName')),localizedDescription=text(t.get('Description')),triggerGraphs=[])
            for effect in mod.get('StatusEffectsOnEquip',[]):
                for field in ['AttackPrefab','AfflictionPrefab','AbilityPrefab']:
                    if effect.get(field,{}).get('m_PathID'):mod['triggerGraphs'].append({'stat':effect['AffectsStat'],'graph':graph(modobj,effect[field])})
            if t.get('AbilityPrefab',{}).get('m_PathID'):mod['triggerGraphs'].append({'stat':2097,'graph':graph(modobj,t['AbilityPrefab'])})
            mods.append(mod)
        game={'prefab':prefab,'archive':'recipes','sourceName':text(item['DisplayName']),'localizedText':True,'statsVersion':2,'weaponStatsVersion':1,
              'sourceItem':clean(item),'sourceComponents':[clean(t) for _,t in components],
              'equipmentComponents':[clean(t) for _,t in components if any(k in t for k in ['DamageThreshold','BaseParryBonus','AccuracyBonus','DamageData'])],
              'craftQuality':info,'attack':attack(ranged or primary),'armor':{},'mods':mods,
              'statusEffects':[*item.get('StatusEffects',[]),*(s for m in mods for s in m.get('StatusEffectsOnEquip',[]))],
              'modReferences':item.get('ItemMods',[]),'useComponents':[]}
        hands=2 if item.get('BothPrimaryAndSecondarySlot') else 1 if item.get('PrimaryWeaponSlot') else 0
        weapons[prefab]={'attack':attack(ranged or primary),'meleeAttack':attack(primary) if ranged else {},'thrown':bool(ranged),
                          'hands':hands,'quality':{'id':info['id'],'level':info['level']}}
        rows.append({'name':name,'category':category,'slot':'','quality':QUALITIES[info['level']],
                     'source_url':'game://'+prefab,'description':'','lore':text(item.get('DescriptionText')),
                     'value':round(item['Value']['InitialValue']),'weight':1,'hands':hands,
                     'damage_min':0,'damage_max':0,'armor':0,'recovery':0,'properties':{'gameData':game},'image_url':image})
    return rows,weapons


if __name__=='__main__':
    rows,weapons=extract()
    # Generated additive snapshots; the existing base export is never rewritten.
    (ROOT/'catalog/weapon_source_extra.json').write_text(json.dumps(weapons,ensure_ascii=False,indent=2),encoding='utf-8')
    from weapon_stats import source
    source.cache_clear()
    rows=[normalize_quality(r) for r in rows]
    (ROOT/'catalog/game_items_extra.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding='utf-8')
    print('Added source-backed recruit items:',len(rows))
