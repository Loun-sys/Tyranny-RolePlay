"""Read every weapon from installed bundles; never use Wiki values."""
import argparse,copy,csv,io,json,sys
from pathlib import Path
import UnityPy
from game_asset_index import GameIndex

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
FIELDS=('AttackDistance','OverrideAttackDistance','MinAttackDistance','AccuracyBonus','DTBypass',
    'DefendedBy','SecondaryDefense','PersonalCooldownModifier','UsePersonalCooldown','ZeroAttackRecovery',
    'BaseInterruptValue','AttackSpeed','UiAttackSpeed','SpeedFactor','DamageMultiplier')

def extract():
    index=GameIndex(extra_bundles=['recipes'])
    records={};timing={}
    for tree in index.trees.values():
        if 'ShortAttackSpeed' in tree:timing.update({k:v for k,v in tree.items() if 'AttackSpeed' in k})
        if 'GlobalMinimumPersonalCooldown' in tree:timing['minimumRecovery']=tree['GlobalMinimumPersonalCooldown']
    for (asset,pid),item in index.trees.items():
        if 'Value' not in item or not (item.get('PrimaryWeaponSlot') or item.get('SecondaryWeaponSlot')):continue
        obj=index.assets[asset].objects[pid];name=index.name(obj);components=index.components(obj)
        primary=next((t for _,t in components if 'DamageData' in t and 'AttackDistance' in t),{})
        thrown=next(((o,t) for o,t in components if t.get('RangedAttack',{}).get('m_PathID')),None)
        ranged={}
        if thrown:
            ranged=next((t for _,t in index.components(index.resolve(thrown[0],thrown[1]['RangedAttack'])) if 'DamageData' in t and 'AttackDistance' in t),{})
        def attack(t):
            return {**{k:t[k] for k in FIELDS if k in t},'DamageData':{k:t.get('DamageData',{})[k] for k in ('Minimum','Maximum','Type','BestOfType') if k in t.get('DamageData',{})}} if t else {}
        quality=next((t for _,t in components if t.get('QualityScaleID')),None)
        records[name]={'attack':attack(ranged or primary),'meleeAttack':attack(primary) if ranged else {},
            'thrown':bool(ranged),'hands':2 if item.get('BothPrimaryAndSecondarySlot') else 1 if item.get('PrimaryWeaponSlot') else 0,
            'quality':{'id':quality['QualityScaleID'],'level':quality.get('QualityScaleLevel',1)} if quality else None}
    env=UnityPy.load('C:/Games/Tyranny/Data/resources.assets');tables={}
    for obj in env.objects:
        if obj.type.name=='MonoBehaviour':
            try:tree=obj.read_typetree()
            except (ValueError,KeyError):continue
            if 'ShortAttackSpeed' in tree:timing.update({k:v for k,v in tree.items() if 'AttackSpeed' in k})
            if 'GlobalMinimumPersonalCooldown' in tree:timing['minimumRecovery']=tree['GlobalMinimumPersonalCooldown']
        if obj.type.name=='TextAsset':
            text=obj.read()
            if text.m_Name=='QualityScalingWeapons':
                rows=list(csv.reader(io.StringIO(text.m_Script)))
                tables={r[0]:{k:float(v) for k,v in zip(rows[0][1:],r[1:])} for r in rows[1:] if r}
    return {'source':'Installed items/DLC bundles + resources.assets/QualityScalingWeapons','timing':timing,'weapons':records},tables

def main():
    sys.stdout.reconfigure(encoding='utf-8');parser=argparse.ArgumentParser();parser.add_argument('--export',action='store_true');args=parser.parse_args()
    source,tables=extract()
    if args.export:
        print(json.dumps(source,ensure_ascii=False,separators=(',',':')));return
    from item_texts import catalog_texts,normalize_item_text
    from crafting import normalize_quality,quality_info,scale_row,library
    from item_effects import game_data
    errors=[];count=0
    snapshot=json.loads((ROOT/'catalog/weapon_source.json').read_text(encoding='utf-8'))
    extra=ROOT/'catalog/weapon_source_extra.json'
    if extra.exists():snapshot['weapons'].update(json.loads(extra.read_text(encoding='utf-8')))
    for prefab,raw in catalog_texts()[0].items():
        original=source['weapons'].get(prefab)
        if not original or not original['attack']:continue
        count+=1;item=normalize_item_text(normalize_quality(raw));game=game_data(item)
        melee=original['thrown'] and 'javelin' not in prefab.lower()
        original_attack=original['meleeAttack'] if melee else original['attack']
        prefix='Weapon_MeleeAttack_AttackBase_' if melee else 'AttackBase_'
        if snapshot['weapons'].get(prefab)!=original:errors.append((prefab,'snapshot differs from installed prefab'))
        q=quality_info(item)
        scaling={}
        if q:
            key=library()['qualityEnums']['WeaponQualityID'].get(str(q['id']))
            suffix={1:'Common',2:'Fine',3:'Superior',4:'Exquisite',5:'Masterwork'}[q['level']]
            scaling=tables.get(f'{key}_{suffix}',{})
            if scaling!=scale_row(q,q['level']):errors.append((prefab,'quality table differs from resources.assets'))
            if original['quality']!={'id':q['id'],'level':q['level']}:errors.append((prefab,'quality identity differs'))
        for field,column in [('AccuracyBonus','AccuracyBonus'),('DTBypass','DTBypass'),('PersonalCooldownModifier','PersonalCooldownModifier'),('BaseInterruptValue','BaseInterrupt')]:
            expected=scaling.get(prefix+column,original_attack.get(field,0))
            if abs(float(game['attack'].get(field,0))-expected)>1e-5:errors.append((prefab,field,expected,game['attack'].get(field)))
        expected_recovery=scaling.get(prefix+'PersonalCooldownModifier',original_attack.get('PersonalCooldownModifier',0))/10
        if abs(item['recovery']-expected_recovery)>1e-4:errors.append((prefab,'recovery',expected_recovery,item['recovery']))
        for key in ('Type','BestOfType'):
            if game['attack']['DamageData'].get(key)!=original_attack['DamageData'].get(key):errors.append((prefab,key))
        if item['hands']!=original['hands']:errors.append((prefab,'hands'))
        for field in set(FIELDS)-{'AccuracyBonus','DTBypass','PersonalCooldownModifier','BaseInterruptValue'}:
            if game['attack'].get(field)!=original_attack.get(field):errors.append((prefab,field))
        for bound,column in [('damage_min','DamageData_DamageMin'),('damage_max','DamageData_DamageMax')]:
            expected=round(scaling.get(prefix+column,original_attack['DamageData']['Minimum' if bound=='damage_min' else 'Maximum']))
            if item[bound]!=expected:errors.append((prefab,bound,expected,item[bound]))
            source_field='Minimum' if bound=='damage_min' else 'Maximum'
            if abs(game['attack']['DamageData'][source_field]-scaling.get(prefix+column,original_attack['DamageData'][source_field]))>1e-5:errors.append((prefab,'damage precision',source_field))
    print(json.dumps({'weaponsChecked':count,'timing':source['timing'],'mismatches':len(errors),'examples':errors[:15]},ensure_ascii=False))
    if errors:raise SystemExit(1)

if __name__=='__main__':main()
