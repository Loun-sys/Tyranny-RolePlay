"""Original NPC ability graphs and icons, with tabletop durations."""
import json, math, re, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts.game_asset_index import GameIndex,localized_tables
from localization import localize_game_text
from special_effects import adapted_effects

def main():
    g=GameIndex();ru=localized_tables()
    npcs=json.loads((ROOT/'catalog/game_npcs.json').read_text(encoding='utf-8'))
    wanted={a['prefab'] for n in npcs for a in n['abilities'] if a.get('prefab')}
    uses={p:sorted({n['name'] for n in npcs if any(a.get('prefab')==p for a in n['abilities'])}) for p in wanted}
    def text(ref):
        table={6:'abilities',19:'afflictions'}.get(ref.get('StringTable'),'abilities')
        return localize_game_text(re.sub(r'\[/?url(?:=[^]]+)?\]','',ru.get(table,{}).get(ref.get('StringID'),'')))
    out={};dest=ROOT/'web/assets/npc-ability-icons';dest.mkdir(parents=True,exist_ok=True)
    for group,components in g.groups.items():
        prefab=g.names.get(group,'')
        # Include referenced actor abilities plus NPC/enemy-specific prefabs
        # even when no default actor lists them (scripted encounters).
        if prefab not in wanted and not re.search(r'(?:ABL|PSV)_(?:NPC|ENEMY|CREATURE|BM|BB|DA|SC)_',prefab,re.I):continue
        for obj,t in components:
            if 'Cooldown' not in t or 'DisplayName' not in t:continue
            name=text(t['DisplayName'])
            if not name:continue
            queue=list(components);seen=set();graph=[]
            while queue and len(graph)<150:
                source,tree=queue.pop(0);key=(source.assets_file.name,source.path_id)
                if key in seen:continue
                seen.add(key);graph.append(tree)
                refs=[p for s in tree.get('StatusEffects',[]) for k in ['AttackPrefab','AfflictionPrefab','AbilityPrefab'] for p in [s.get(k)]]
                for key in ['ExtraAOE','SecondAOE','FollowUpAttacks','Afflictions','AttackPrefab','AfflictionPrefab','AbilityPrefab','AttackPrefabTriggeredOn']:
                    value=tree.get(key,[]);refs.extend(value if isinstance(value,list) else [value])
                for ptr in refs:
                    if isinstance(ptr,dict):queue.extend(g.components(g.resolve(source,ptr)))
            attack=next((x for x in graph if x.get('DamageData',{}).get('Maximum') or x.get('DamageData',{}).get('WeaponDamageMult')),{})
            damage=attack.get('DamageData',{});icon=''
            texture=g.resolve(obj,t.get('Icon'))
            if texture and texture.type.name=='Texture2D':
                tx=texture.read();file=re.sub('[^a-zA-Z0-9_-]','_',tx.m_Name)+'.png';tx.image.save(dest/file);icon='assets/npc-ability-icons/'+file
            row={'key':prefab,'prefab':prefab,'name':name,'description':text(t.get('Description',{})),
                'passive':bool(t.get('Passive')),'icon':icon or 'assets/game-combat/icon_option_talents.png',
                'cooldown':max(0,math.ceil(float(t.get('Cooldown',0))/10)),
                'oncePerBattle':t.get('CooldownType') in {1,2},
                'range':max(1,math.ceil(float(attack.get('AttackDistance',1)))),
                'area':math.ceil(max((float(x.get('BlastRadius',0)) for x in graph),default=0)),
                'damageMin':round(damage.get('Minimum',0)),'damageMax':round(damage.get('Maximum',0)),
                'weaponMultiplier':damage.get('WeaponDamageMult',0),'penetration':round(attack.get('DTBypass',0)),
                'users':uses.get(prefab,[]),'statuses':[s for x in graph for s in x.get('StatusEffects',[])]}
            row['effects']=adapted_effects(row)
            row['targeting']='area' if row['area'] else 'unit'
            # Store compact combat semantics, not Unity object pointers.
            row.pop('statuses')
            if prefab not in out or len(row['description'])>len(out[prefab]['description']):out[prefab]=row
    result={'abilities':sorted(out.values(),key=lambda x:(x['name'],x['key'])),'missing':sorted(wanted-set(out))}
    (ROOT/'catalog/npc_abilities.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print('NPC abilities:',len(out),'unresolved references:',len(result['missing']),flush=True)

if __name__=='__main__':main()
