"""Context-dependent talent rules. Unsupported effects stay visible in the audit.

No name matching: source stat IDs and values drive these calculations.
"""
import math

SUPPORTED={27,101,137,70,2053,2052,112,2106,28,2157,80,2057,
           2108,2109,2012,102,213,2054,2120,2116,2146,2143,2147,2148,2138,2121,2099,2101,2102,2103,2044,2150,
           20,24,2145,105,75,2125,2126,2113,22,23,160,2174}
SUPPORTED|={172,2100,2115,2117,2142}
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
    return (effect['AffectsStat'] in {14,2000,2026,2027,24,2145,105}
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
    from talent_batch_one import family
    from item_effects import active_equipment
    result={};capacities={}
    for talent in talents:
        row=resolve(talent)
        if not row or not row['passive'] or row.get('modal') or row.get('isTalentUpgrade'):continue
        if row.get('abilityClass') in {'TriggeredOnKillAbility','TriggeredOnDeathAbility'}:continue
        if row['key']=='ABL_HH_Sentinel_Last_Stand':continue
        if inventory is not None and weapon_requirement(row,inventory,active_set):continue
        for node in row['nodes']:
            if node['phase']!='root' or node['side']!='self':continue
            for effect in node['statuses']:
                stat=effect['AffectsStat']
                if stat not in SUPPORTED:continue
                if effect.get('ApplicationPrerequisites') or effect.get('TriggerAdjustment',{}).get('Type'):
                    if inventory is None or not equipment_condition_supported(effect):continue
                    effect=equipped_effect(effect,active_equipment(inventory,active_set))
                    if effect is None:continue
                if stat==2113:continue # Per-skill party bonuses, not a global multiplier.
                if stat==20:
                    group=family(row['key']);capacities[group]=max(capacities.get(group,0),effect['Value']);continue
                # Successive ranks replace, rather than multiply, earlier ranks.
                result[stat]=max(result.get(stat,float('-inf')),float(effect['Value']))
    if capacities:result[20]=sum(capacities.values())
    return result

def equipment_attack(attack,rules,category,weapon_count):
    attack=dict(attack)
    if category=='Одноручное оружие' and weapon_count==1:
        attack['accuracy']+=rules.get(2150,0)
    if category=='Безоружный бой':
        bonus=rules.get(27,0)
        attack['damageMin']+=bonus;attack['damageMax']+=bonus
        attack['penetration']+=rules.get(2106,0)
    if category=='Дротики':
        attack['range']+=rules.get(2052,0)
        attack['penetration']+=rules.get(2053,0)
    if category in {'Луки','Дротики','Волшебный посох'}:
        attack['penetration']+=rules.get(213,0)
    if attack.get('range',1)<=1 and 28 in rules:
        attack['range']=math.ceil(attack['range']*rules[28])
    multiplier=1
    if attack.get('range',1)>1:multiplier*=rules.get(112,1)
    attack['damageMin']=round(attack['damageMin']*multiplier)
    attack['damageMax']=round(attack['damageMax']*multiplier)
    return attack


def single_weapon_bonus(rules,inventory,active_set=1):
    from item_effects import active_equipment
    weapons=[i for i in active_equipment(inventory,active_set) if i.get('equipped_slot','').startswith('Оружие')]
    return rules.get(2150,0) if len(weapons)==1 and 'правая рука' in weapons[0]['equipped_slot'] and weapons[0].get('category')=='Одноручное оружие' else 0


def riposte_chance(rules,inventory,attack,states,active_set=1):
    """2044 has a different weapon filter from the 2150 accuracy bonus."""
    from item_effects import active_equipment
    weapons=[i for i in active_equipment(inventory,active_set) if i.get('equipped_slot','').startswith('Оружие')]
    if 2174 in rules and weapon_mode(attack)=='melee':
        if any(key.removeprefix('special:') in {'stun','prone','sleep','freeze','paralyze','petrif','disarm'} for key in states):return 0
        return max(0,min(1,rules[2174]/100))
    if len(weapons)!=1 or 'правая рука' not in weapons[0]['equipped_slot']:return 0
    if weapons[0].get('category') not in {'Одноручное оружие','Метательное оружие'} or weapon_mode(attack)!='melee':return 0
    blocked={'stun','prone','sleep','freeze','frozen','paralyze','paralyzed','petrif','petrified','disarm'}
    if any(key.removeprefix('special:') in blocked for key in states):return 0
    return max(0,min(1,rules.get(2044,0)/100))


def spell_conversions(states,round_number):
    """Serialized 50 means 50%, only for crafted spells; no permanent bonus."""
    result={}
    for state in states.values():
        effect=state.get('source',{})
        if state.get('until',0)<round_number:continue
        key={2127:'critToHit',2128:'hitToGraze'}.get(effect.get('AffectsStat'))
        if key:result[key]=max(result.get(key,0),float(effect.get('Value',0)))
    return result


def weapon_mode(attack,rule=None):
    # A two-cell unarmed reach is still melee, not a projectile.
    skill=attack.get('skill')
    if not skill and rule:
        skills=rule.get('skills',[])
        skill='Волшебный посох' if 8 in skills else 'Луки' if 10 in skills else 'Дротики' if 37 in skills else None
    if skill=='Волшебный посох':return 'magic-ranged'
    if skill:return 'ranged' if skill in {'Луки','Дротики'} else 'melee'
    return 'ranged' if attack.get('range',1)>1 else 'melee'


def incoming_defense(rules,defenses,name,mode,engaged=0):
    parry=defenses.get('Парирование',0)+rules.get(2143,0)*engaged
    value=parry if name=='Парирование' else defenses.get(name,0)
    if mode in {'ranged','magic-ranged'} and name=='Уклонение' and 2146 in rules:
        value=max(value,parry)
    return round(value)


def incoming_conversions(rules,mode):
    if mode!='melee':return {}
    return {'hitToGraze':rules.get(2147,0)*100,'grazeToMiss':rules.get(2148,0)*100}


def reflection_chance(rules,mode,result):
    if mode not in {'ranged','magic-ranged'} or result=='Промах':return 0
    arrow=max(0,min(1,rules.get(2138,0)/100)) if mode=='ranged' else 0
    graze=max(0,min(1,rules.get(2121,0))) if result=='Скользящий удар' else 0
    return 1-(1-arrow)*(1-graze)


def hostile_duration(effect,outgoing,incoming):
    """Scale original seconds BEFORE rounding to cells' ten-second rounds."""
    import copy
    result=copy.deepcopy(effect)
    if not (effect.get('control') or effect.get('IsHostile')):return result
    seconds=float(effect.get('Duration',10 if effect.get('control') else 0))
    if seconds>0:
        result['Duration']=round(seconds*outgoing.get(2116,1)*incoming.get(2120,1)*incoming.get(75,1),4)
        result['rounds']=max(1,math.ceil(result['Duration']/10))
    return result

def attack_context(rules,states,distance,health_fraction,engaged):
    multiplier=1
    if any(k in states for k in ('prone','stun','paralyze','petrif','freeze','sleep')):multiplier*=rules.get(137,1)
    if any(s.get('source',{}).get('AffectsStat')==25 for s in states.values()):multiplier*=rules.get(80,1)
    if any(not s.get('beneficial',False) for s in states.values()):multiplier*=rules.get(2057,1)
    multiplier*=1+rules.get(2108,0)*(1-health_fraction)
    if engaged>0:multiplier*=1+rules.get(2125,0)*engaged/100
    return {'multiplier':multiplier,'accuracy':rules.get(70,0) if distance>5 else 0,
            'criticalMultiplier':1.5+rules.get(101,0)}
