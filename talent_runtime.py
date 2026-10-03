"""Context-dependent talent rules. Unsupported effects stay visible in the audit.

No name matching: source stat IDs and values drive these calculations.
"""
import math

SUPPORTED={27,101,137,70,2053,2052,112,2106,28,2157,80,2057,
           2108,2109,2012,102}
DISPLAY_ONLY={184,2001,2011,2172,225}

def attribute_skill_delta(name,base,effective):
    from constants import SKILL_ATTRIBUTES
    weights=SKILL_ATTRIBUTES.get(name)
    if not weights:return 0
    primary,secondary=weights
    before=round(base.get(primary,10)*1.5+base.get(secondary,10)*.5)
    after=round(effective.get(primary,10)*1.5+effective.get(secondary,10)*.5)
    return after-before

def equipment_condition_supported(effect):
    return (effect['AffectsStat'] in {14,2000,2026,2027}
            and effect.get('TriggerAdjustment',{}).get('Type',0) in {0,16,17,18}
            and all(p['Type'] in {30,31,32} for p in effect.get('ApplicationPrerequisites',[])))

def equipped_effect(effect,inventory):
    """Heavy/light/no-armour conditions and trigger values from the game enums."""
    from item_effects import game_data
    import copy
    armor=[game_data(i)['armor']['ArmorCategory'] for i in inventory
           if i.get('equipped_slot') and 'ArmorCategory' in game_data(i).get('armor',{})]
    flags={30:1 in armor and 0 not in armor,31:0 in armor and 1 not in armor,32:not armor}
    trigger=effect.get('TriggerAdjustment',{}).get('Type',0)
    if not all(flags[p['Type']] for p in effect.get('ApplicationPrerequisites',[])):return None
    if trigger and not flags[{16:30,17:31,18:32}[trigger]]:return None
    result=copy.deepcopy(effect)
    if trigger:
        adjustment=effect['TriggerAdjustment'].get('ValueAdjustment',0)
        result['Value']=result['Value']*adjustment if effect['AffectsStat']==2000 else result['Value']+adjustment
    result['ApplicationPrerequisites']=[];result['TriggerAdjustment']={}
    return result

def effects(talents,inventory=None,active_set=1):
    from ability_rules import resolve,weapon_requirement
    result={}
    for talent in talents:
        row=resolve(talent)
        if not row or not row['passive'] or row.get('modal') or row.get('isTalentUpgrade'):continue
        if row.get('abilityClass') in {'TriggeredOnKillAbility','TriggeredOnDeathAbility'}:continue
        if inventory is not None and weapon_requirement(row,inventory,active_set):continue
        for node in row['nodes']:
            if node['phase']!='root' or node['side']!='self':continue
            for effect in node['statuses']:
                stat=effect['AffectsStat']
                if stat not in SUPPORTED or effect.get('ApplicationPrerequisites') or effect.get('TriggerAdjustment',{}).get('Type'):continue
                # Successive ranks replace, rather than multiply, earlier ranks.
                result[stat]=max(result.get(stat,float('-inf')),float(effect['Value']))
    return result

def equipment_attack(attack,rules,category,weapon_count):
    attack=dict(attack)
    if category=='Безоружный бой':
        bonus=rules.get(27,0)
        attack['damageMin']+=bonus;attack['damageMax']+=bonus
        attack['penetration']+=rules.get(2106,0)
    if category=='Дротики':
        attack['range']+=rules.get(2052,0)
        attack['penetration']+=rules.get(2053,0)
    if attack.get('range',1)<=1 and 28 in rules:
        attack['range']=math.ceil(attack['range']*rules[28])
    multiplier=1
    if attack.get('range',1)>1:multiplier*=rules.get(112,1)
    attack['damageMin']=round(attack['damageMin']*multiplier)
    attack['damageMax']=round(attack['damageMax']*multiplier)
    return attack

def attack_context(rules,states,distance,health_fraction,engaged):
    multiplier=1
    if any(k in states for k in ('prone','stun','paralyze','petrif','freeze','sleep')):multiplier*=rules.get(137,1)
    if any(s.get('source',{}).get('AffectsStat')==25 for s in states.values()):multiplier*=rules.get(80,1)
    if any(not s.get('beneficial',False) for s in states.values()):multiplier*=rules.get(2057,1)
    multiplier*=1+rules.get(2108,0)*(1-health_fraction)
    return {'multiplier':multiplier,'accuracy':rules.get(70,0) if distance>5 else 0,
            'criticalMultiplier':1.5+rules.get(101,0)}
