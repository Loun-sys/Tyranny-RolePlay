"""Reproducible catalog of localized item prefabs, including original textures.

Run only against a legitimately installed game. Original records are kept in
the audit so excluded developer/unused prefabs cannot masquerade as coverage.
"""
import collections
import json
import re
import sys
from pathlib import Path
import UnityPy
from game_asset_index import localized_tables

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from localization import localize_game_text


def main():
    loc = json.loads((ROOT/'catalog/official_game_localization.json').read_text(encoding='utf-8'))
    tables = localized_tables()
    enum_tables = {5: 'items', 6: 'abilities', 16: 'itemmods'}
    def text(ref):
        row = tables.get(enum_tables.get(ref.get('StringTable')), {}).get(ref.get('StringID'), '')
        return localize_game_text(re.sub(r'\[/?url(?:=[^]]+)?\]', '', row))
    base = json.loads((ROOT/'catalog/tyranny_catalog_en_ru.json').read_text(encoding='utf-8'))
    by_name = {i['name'].casefold(): i for i in base}
    out, audit, used, textures_done = [], [], set(), set()
    destination = ROOT/'web/assets/item-icons'
    destination.mkdir(exist_ok=True, parents=True)
    for archive in ['items', 'dlc00', 'dlc01', 'dlc02', 'dlc03','vx1_items']:
        env = UnityPy.load(f'C:/Games/Tyranny/Data/bundles/{archive}.unity3d')
        groups, names, objects, components = collections.defaultdict(list), {}, {o.path_id: o for o in env.objects}, {}
        for obj in env.objects:
            if obj.type.name == 'GameObject': names[obj.path_id] = obj.read().m_Name
            if obj.type.name == 'MonoBehaviour':
                try:
                    tree = obj.read_typetree()
                    components[obj.path_id] = tree
                    groups[tree.get('m_GameObject', {}).get('m_PathID')].append(tree)
                except (ValueError, KeyError): pass
        for ident, trees in groups.items():
            item = next((t for t in trees if 'DisplayName' in t and 'Value' in t), None)
            if not item: continue
            internal = names.get(ident, str(ident))
            name = text(item['DisplayName'])
            excluded = 'Вырезан из игры' if item.get('CutFromGame') else 'Нет русского названия' if not name else ''
            if re.search(r'(^test|_test|^debug|^npc_|^prop_)', internal, re.I): excluded = 'Служебный объект'
            audit.append({'archive': archive, 'prefab': internal, 'name': name, 'excluded': excluded})
            if excluded or internal in used: continue
            used.add(internal)
            existing = by_name.get(name.casefold())
            entry = dict(existing or {})
            # Preserve wiki URLs for already owned items. Distinct physical
            # variants need distinct records, not overwritten base equipment.
            if any(r['name'] == name for r in out):
                variant = sum(r['name'].startswith(name+' (вариант ') for r in out)+2
                name += f' (вариант {variant})'
                entry = {}
            slot = next((label for key, label in [('HeadSlot','Голова'), ('ArmorSlot','Торс'),
                ('HandSlot','Руки'), ('FeetSlot','Ноги'), ('NeckSlot','Аксессуар'),
                ('RingRightHandSlot','Аксессуар'), ('RingLeftHandSlot','Аксессуар'),
                ('CapeSlot','Аксессуар'), ('WaistSlot','Аксессуар') ] if item.get(key)), '')
            category = {5:'Одноручное оружие',6:'Парное оружие',7:'Двуручное оружие',8:'Посохи',
                        9:'Безоружное оружие',10:'Луки',37:'Метательное оружие'}.get(item.get('SkillType'))
            category = category or ('Броня' if slot in {'Торс','Голова','Руки','Ноги'} else
                'Аксессуары' if slot else 'Материалы' if item.get('IsIngredient') else
                'Расходуемые предметы' if item.get('MaxStackSize',1)>1 else entry.get('category','Прочее'))
            if item.get('SecondaryWeaponSlot') and not item.get('PrimaryWeaponSlot'): category='Щиты'
            attack = next((t for t in trees if 'DamageData' in t), {})
            armor = next((t for t in trees if 'DamageThreshold' in t), {})
            image = entry.get('image_url','')
            ptr = item.get('IconTexture', {})
            obj = objects.get(ptr.get('m_PathID')) if ptr.get('m_FileID',0)==0 else None
            if obj and obj.type.name=='Texture2D':
                tx=obj.read(); filename=re.sub(r'[^a-zA-Z0-9_-]', '_',tx.m_Name)+'.png'
                if filename not in textures_done:
                    tx.image.save(destination/filename); textures_done.add(filename)
                image='assets/item-icons/'+filename
            damage=attack.get('DamageData',{})
            properties=dict(entry.get('properties') or {})
            mods = [components.get(p.get('m_PathID'), {}) for p in item.get('ItemMods',[]) if p.get('m_FileID',0)==0]
            effects = [*item.get('StatusEffects',[]), *(s for mod in mods for s in mod.get('StatusEffectsOnEquip',[]))]
            properties['gameData']={'prefab':internal,'archive':archive,'statusEffects':effects,
                'mods':[{k:v for k,v in mod.items() if k not in {'m_Script','m_GameObject'}} for mod in mods],
                'modReferences':item.get('ItemMods',[]),'attack':{k:attack[k] for k in
                ['AccuracyBonus','DTBypass','AttackDistance','DamageData'] if k in attack},
                'armor':{k:armor[k] for k in ['DamageThreshold','RecoveryModifier','DeflectionBonus'] if k in armor}}
            entry.update(name=name,category=category,slot=slot,source_url=entry.get('source_url') or 'game://'+internal,
                quality=entry.get('quality','Обычное'), description=entry.get('description',''),
                lore=text(item['DescriptionText']) or entry.get('lore',''),image_url=image or 'assets/game-combat/icon_option_inventory.png',
                value=round(item['Value']['InitialValue']),weight=entry.get('weight',0 if item.get('IsIngredient') else 1),
                hands=2 if item.get('BothPrimaryAndSecondarySlot') else 1 if item.get('PrimaryWeaponSlot') else 0,
                damage_min=round(damage.get('Minimum',entry.get('damage_min',0))),
                damage_max=round(damage.get('Maximum',entry.get('damage_max',0))),
                armor=round(armor.get('DamageThreshold',entry.get('armor',0))),
                recovery=round(armor.get('RecoveryModifier',entry.get('recovery',0)),3),properties=properties)
            out.append(entry)
    (ROOT/'catalog/game_items.json').write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8')
    report={'prefabs':len(audit),'imported':len(out),'icons':len(textures_done),
            'excluded':[r for r in audit if r['excluded']],
            'missingIcons':[r['name'] for r in out if not r['image_url']],
            'note':'Conditional item mods and quality scaling are preserved as source data; not all are executable combat rules.'}
    (ROOT/'catalog/game_item_audit.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print({k:v for k,v in report.items() if k not in {'excluded','missingIcons'}})


if __name__ == '__main__': main()
