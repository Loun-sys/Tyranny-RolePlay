"""Repair every catalogue row from installed game components, preserving identities."""
import copy
import hashlib
import json
import re
import sys
from pathlib import Path
from game_asset_index import GameIndex, localized_tables, GAME

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from localization import localize_game_text
from crafting import normalize_quality
from item_effects import refresh_item_properties

def main():
    sys.stdout.reconfigure(encoding='utf-8')
    index=GameIndex();tables=localized_tables()
    rows=json.loads((ROOT/'catalog/game_items.json').read_text(encoding='utf-8'))
    known={i['properties']['gameData']['prefab']:i for i in rows}
    def text(ref):
        table={5:'items',6:'abilities',16:'itemmods',13:'recipes',19:'afflictions'}.get((ref or {}).get('StringTable'))
        return localize_game_text(re.sub(r'\[/?url(?:=[^]]+)?\]','',tables.get(table,{}).get((ref or {}).get('StringID'),''))).strip()
    def clean(tree):return {k:copy.deepcopy(v) for k,v in tree.items() if not k.startswith('m_')}
    def graph(source,ptr):
        pending=[(o,t,0) for o,t in index.components(index.resolve(source,ptr))];result=[];seen=set()
        while pending:
            obj,t,inherited=pending.pop(0);key=(obj.assets_file.name,obj.path_id)
            if key in seen:continue
            seen.add(key);out=clean(t);out['prefab']=index.name(obj)
            out['localizedName']=text(t.get('DisplayName'));out['localizedDescription']=text(t.get('Description'))
            result.append(out)
            if inherited:
                for effect in out.get('StatusEffects',[]):
                    if not effect.get('Duration'):effect['sourceDuration']=0;effect['Duration']=inherited
            for effect in t.get('StatusEffects',[]):
                for field in ['AttackPrefab','AfflictionPrefab','AbilityPrefab']:
                    pending.extend((o,s,effect.get('Duration',0) or inherited) for o,s in index.components(index.resolve(obj,effect.get(field))))
            for field in ['AttackPrefab','AfflictionPrefab','AbilityPrefab','ExtraAOE','SecondAOE','FollowUpAttacks','Afflictions']:
                refs=t.get(field,[]);refs=refs if isinstance(refs,list) else [refs]
                for ref in refs:
                    if isinstance(ref,dict):
                        pending.extend((o,s,ref.get('Duration',0) or inherited) for o,s in index.components(index.resolve(obj,ref.get('AfflictionPrefab',ref))))
        return result
    excluded=[];changes=[];all_prefabs=[];added=[]
    for (asset,pid),item in index.trees.items():
        if 'Value' not in item or 'DisplayName' not in item:continue
        obj=index.assets[asset].objects[pid];prefab=index.name(obj);bundle=index.asset_bundles[asset]
        name=text(item['DisplayName']);all_prefabs.append(prefab)
        reason='Вырезанный предмет' if item.get('CutFromGame') else 'Служебный объект' if item.get('IsProp') or re.search(r'(^test|_test|^debug|^npc_|^prop_)',prefab,re.I) else 'Нет локализованного названия' if not name else ''
        if prefab not in known and reason:
            excluded.append({'prefab':prefab,'archive':bundle,'reason':reason,'nameRef':item['DisplayName']});continue
        row=known.get(prefab)
        if row is None:
            slot=next((label for key,label in [('HeadSlot','Голова'),('ArmorSlot','Торс'),('HandSlot','Руки'),('FeetSlot','Ноги'),('NeckSlot','Аксессуар'),('RingRightHandSlot','Аксессуар'),('RingLeftHandSlot','Аксессуар'),('CapeSlot','Аксессуар'),('WaistSlot','Аксессуар')] if item.get(key)),'')
            category={5:'Одноручное оружие',6:'Парное оружие',7:'Двуручное оружие',8:'Посохи',9:'Безоружное оружие',10:'Луки',37:'Метательное оружие'}.get(item.get('SkillType')) or ('Броня' if slot in {'Торс','Голова','Руки','Ноги'} else 'Аксессуары' if slot else 'Прочее')
            if item.get('SecondaryWeaponSlot') and not item.get('PrimaryWeaponSlot'):category='Щиты'
            base=name;n=2
            while any(r['name']==name for r in rows):name=f'{base} (вариант {n})';n+=1
            row={'name':name,'category':category,'slot':slot,'source_url':'game://'+prefab,'quality':'Обычное','description':'','lore':text(item.get('DescriptionText')),'weight':1,'properties':{},'image_url':'assets/game-combat/icon_option_inventory.png'}
            rows.append(row);known[prefab]=row;added.append(prefab)
        before={k:row.get(k) for k in ['armor','damage_min','damage_max','recovery']}
        game=row['properties'].setdefault('gameData',{})
        game.update(prefab=prefab,archive=bundle,localizedText=True,statsVersion=2)
        components=[(o,clean(t)) for o,t in index.components(obj)]
        game['sourceComponents']=[t for _,t in components]
        game['equipmentComponents']=[t for _,t in components if any(k in t for k in ['DamageThreshold','ParryBonus','AthleticsBonus','BaseParryBonus','AccuracyBonus','MeleeDamageBonus','DeflectionBonus','DamageData'])]
        game['sourceItem']=clean(item)
        # Usable objects carry a GenericAbility and sometimes a separate attack.
        usable=int(item.get('FilterType',0))==16 and not any(item.get(k,{}).get('m_PathID') for k in ['ScrollSymbol','ScrollShape','ScrollModifier'])
        game['useComponents']=[]
        if usable:
            for source,component in index.components(obj):
                if 'Cooldown' in component or 'AttackDistance' in component:
                    entry=clean(component);entry['localizedDescription']=text(component.get('Description'))
                    entry['graphs']=[]
                    for effect in entry.get('StatusEffects',[]):
                        if effect.get('AffectsStat')==184:effect['localizedDescription']=localize_game_text(tables.get('abilities',{}).get(int(effect.get('Value',0)),''))
                        for key in ['AttackPrefab','AfflictionPrefab','AbilityPrefab']:
                            if effect.get(key,{}).get('m_PathID'):
                                resolved=graph(source,effect[key]);effect[key+'Graph']=resolved;entry['graphs'].extend(resolved)
                    game['useComponents'].append(entry)
        if row['category'] in {'Расходуемые предметы','Зелья','Еда'} and not usable:row['category']='Разное'
        if row['category'] in {'Прочее','Мусор','Драгоценности','Квестовые предметы'}:row['category']='Разное'
        game['armor']=next((t for _,t in components if 'DamageThreshold' in t),{})
        game['attack']=next((t for _,t in components if 'DamageData' in t and 'AttackDistance' in t),{})
        mods=[]
        for ptr in item.get('ItemMods',[]):
            modobj=index.resolve(obj,ptr);t=index.tree(modobj)
            if not t:continue
            mod=clean(t);mod['localizedName']=text(t.get('DisplayName'));mod['localizedDescription']=text(t.get('Description'))
            mod['triggerGraphs']=[]
            for effect in t.get('StatusEffectsOnEquip',[]):
                if effect.get('AffectsStat')==184:effect['localizedDescription']=localize_game_text(tables.get('abilities',{}).get(int(effect.get('Value',0)),''))
                for key in ['AttackPrefab','AfflictionPrefab','AbilityPrefab']:
                    if effect.get(key,{}).get('m_PathID'):mod['triggerGraphs'].append({'stat':effect['AffectsStat'],'graph':graph(modobj,effect[key])})
            if t.get('AbilityPrefab',{}).get('m_PathID'):mod['triggerGraphs'].append({'stat':2097,'graph':graph(modobj,t['AbilityPrefab'])})
            mods.append(mod)
        game['mods']=mods;game['modReferences']=item.get('ItemMods',[])
        game['statusEffects']=[*item.get('StatusEffects',[]),*(s for m in mods for s in m.get('StatusEffectsOnEquip',[]))]
        row.update(value=round(item['Value']['InitialValue']),hands=2 if item.get('BothPrimaryAndSecondarySlot') else 1 if item.get('PrimaryWeaponSlot') else 0,
            armor=round(float(game['armor'].get('DamageThreshold',0)),4),recovery=round(float(game['armor'].get('RecoveryModifier',game['attack'].get('RecoveryTime',0)))/10,4))
        damage=game['attack'].get('DamageData',{})
        row['damage_min']=round(damage.get('Minimum',0));row['damage_max']=round(damage.get('Maximum',0))
        txobj=index.resolve(obj,item.get('IconTexture'))
        if txobj and txobj.type.name=='Texture2D':
            tx=txobj.read();filename=re.sub(r'[^a-zA-Z0-9_-]','_',tx.m_Name)+'.png';dest=ROOT/'web/assets/item-icons'/filename
            if not dest.exists():tx.image.save(dest)
            row['image_url']='assets/item-icons/'+filename
        normalized=normalize_quality(row);row.clear();row.update(normalized);refresh_item_properties(row)
        from consumables import refresh_consumable
        refresh_consumable(row)
        after={k:row.get(k) for k in before}
        if before!=after:changes.append({'prefab':prefab,'before':before,'after':after})
    (ROOT/'catalog/game_items.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding='utf-8')
    report={'sourcePrefabs':len(all_prefabs),'imported':len(rows),'added':added,'excluded':excluded,'changedStats':changes,
            'missingImported':[name for name in all_prefabs if name not in known and not any(e['prefab']==name for e in excluded)],
            'sourceHashes':{name:hashlib.sha256((GAME/(name+'.unity3d')).read_bytes()).hexdigest() for name in sorted(set(index.asset_bundles.values()))}}
    from consumables import profile
    report['consumables']=sum(bool(profile(i)) for i in rows)
    report['categories']={name:sum(i['category']==name for i in rows) for name in sorted({i['category'] for i in rows})}
    report['runtimeLimits']='Сложные условные модификаторы сохранены из игры; не все имеют исполняемый обработчик. Применение специальных воздействий зависит от поддерживаемых правил боя.'
    (ROOT/'catalog/game_item_audit.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print('Items:',len(rows),'added:',added,'corrected stats:',len(changes),'excluded:',len(excluded),'unaccounted:',report['missingImported'])
if __name__=='__main__':main()
