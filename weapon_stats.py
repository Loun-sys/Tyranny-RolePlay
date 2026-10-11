"""Weapon readouts and combat metadata from installed prefabs and quality CSVs."""
import copy,json,math
from functools import lru_cache
from pathlib import Path

@lru_cache(maxsize=1)
def source():
    return json.loads((Path(__file__).parent/'catalog/weapon_source.json').read_text(encoding='utf-8'))['weapons']

def source_attack(prefab):
    record=source().get(prefab,{})
    # Daggers remain melee weapons; javelins use their actual projectile prefab.
    melee=record.get('thrown') and 'javelin' not in prefab.lower()
    return copy.deepcopy(record.get('meleeAttack') if melee else record.get('attack')) or {},bool(melee)

def restore_weapon(item):
    p=item.get('properties') or {}
    if isinstance(p,str):p=json.loads(p)
    game=p.get('gameData',{});prefab=game.get('prefab','');attack,melee=source_attack(prefab)
    if not attack:return item
    game['attack']={**game.get('attack',{}),**attack,
        'DamageData':{**game.get('attack',{}).get('DamageData',{}),**attack['DamageData']}}
    game['weaponStatsVersion']=1
    if 'javelin' in prefab.lower() and source().get(prefab,{}).get('thrown'):item['category']='Метательное оружие'
    q=game.get('qualityStats',{});prefix='Weapon_MeleeAttack_AttackBase_' if melee else 'AttackBase_'
    for field,column in [('AccuracyBonus','AccuracyBonus'),('DTBypass','DTBypass'),('BaseInterruptValue','BaseInterrupt'),('PersonalCooldownModifier','PersonalCooldownModifier')]:
        if prefix+column in q:game['attack'][field]=q[prefix+column]
    damage=game['attack']['DamageData']
    for field,column in [('Minimum','DamageData_DamageMin'),('Maximum','DamageData_DamageMax')]:
        if prefix+column in q:damage[field]=q[prefix+column]
    item['damage_min']=round(damage.get('Minimum',0));item['damage_max']=round(damage.get('Maximum',0))
    item['recovery']=round(float(game['attack'].get('PersonalCooldownModifier',0))/10,4)
    item['properties']=p
    return item

def readout(item):
    from item_effects import game_data,DAMAGE_TYPES,equip_modifiers
    game=game_data(item);attack=game.get('attack',{})
    if not attack or not item.get('hands'):return None
    damage=attack.get('DamageData',{});random_type=damage.get('Type')==13
    types=list(DAMAGE_TYPES.values()) if random_type else list(dict.fromkeys(DAMAGE_TYPES[t] for t in (damage.get('Type'),damage.get('BestOfType')) if t in DAMAGE_TYPES))
    distance=float(attack.get('OverrideAttackDistance') or attack.get('AttackDistance') or .5)
    minimum=float(attack.get('MinAttackDistance') or 0)
    ranged=item.get('category') in {'Луки','Метательное оружие','Посохи'}
    defense={0:'Уклонение' if ranged else 'Парирование',1:'Выносливость',2:'Воля',3:'Магия',5:'Нет'}
    mods=equip_modifiers(item)['flat']
    return {'damageMin':item['damage_min'],'damageMax':item['damage_max'],'damageTypes':types or ['Дробящий'],
        'randomDamage':random_type,'accuracyBonus':mods.get('Точность',0),'penetration':mods.get('Пробивание брони',0),
        'rangeMeters':distance,'rangeCells':max(1,math.ceil(distance)),
        'minRangeMeters':minimum,'minRangeCells':math.ceil(minimum),'defense':defense.get(attack.get('DefendedBy',0),'Парирование'),
        'secondaryDefense':defense.get(attack.get('SecondaryDefense',5),'Нет'),
        'recoverySeconds':round(item.get('recovery',0)*10,4),'recoveryRounds':item.get('recovery',0),
        'interrupt':float(attack.get('BaseInterruptValue',0)),'hands':int(item.get('hands') or 0),
        'attackSpeed':{0:'Мгновенная',1:'Быстрая',2:'Медленная',3:'Бесконечная'}.get(attack.get('AttackSpeed'),'—')}
