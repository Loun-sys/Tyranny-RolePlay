"""Source-keyed free reactions. Never advance initiative or spend an action."""
import copy
import random

from talent_runtime import riposte_chance, single_weapon_bonus


def actor_inventory(actor):
    if 'inventory' in actor:return actor['inventory']
    result=[]
    for item in actor.get('equipment',[]):
        slot=item.get('slot','')
        if slot in {'PrimaryWeapon','SecondaryWeapon'}:
            slot='Оружие I — '+('правая рука' if slot=='PrimaryWeapon' else 'левая рука')
        result.append({**item,'equipped_slot':item.get('equipped_slot') or slot})
    return result


def npc_attack(actor,rules,inventory):
    attack=copy.deepcopy(actor.get('attack',{}))
    primary=next((i for i in inventory if 'правая рука' in (i.get('equipped_slot') or '')), {})
    skills={'Одноручное оружие':'Одноручное оружие','Двуручное оружие':'Двуручное оружие',
            'Парное оружие':'Парное оружие','Луки':'Луки','Посохи':'Волшебный посох'}
    skill=skills.get(primary.get('category'))
    if primary.get('category')=='Метательное оружие' and attack.get('range',1)>1:skill='Дротики'
    if skill:attack.setdefault('skill',skill)
    attack['accuracy']=attack.get('accuracy',20)+single_weapon_bonus(rules,inventory)
    return attack


def npc_derived(actor,rules,inventory,states,round_number):
    """Use the shared NPC stat calculation, including temporary attributes."""
    from consumables import virtual_equipment
    from battle_store import BattleStore
    base={'attack':npc_attack(actor,rules,inventory),'defenses':actor.get('defenses',{}),
          'armor':actor.get('armor',0),'armorByType':actor.get('armorByType',{}),
          'incomingConversions':actor.get('incomingConversions',{}),
          'healthMax':actor.get('baseHealthMax',actor['healthMax']),
          'effectiveAttributes':actor.get('attributes',{}),'effectiveSkills':actor.get('skills',{}),
          'talentRuntime':rules,'abilityAccuracyBonus':single_weapon_bonus(rules,inventory),
          'cooldownMultiplier':1}
    modifiers=virtual_equipment(states,round_number)
    attributes=virtual_equipment({k:v for k,v in states.items() if v.get('source',{}).get('AffectsStat') in {56,57,58,59,99,100}},round_number)
    derived=BattleStore._npc_modifiers(base,modifiers)
    derived['_baseDerived']=BattleStore._npc_modifiers(base,attributes)
    return derived


def reaction_derived(actor,rules,inventory,states,round_number):
    if 'combatDerived' in actor:return copy.deepcopy(actor['combatDerived'])
    return npc_derived(actor,rules,inventory,states,round_number)


def try_riposte(session,target_id):
    """A missed melee weapon strike may trigger one defender's primary strike.

    Atomic turns have no ongoing movement. Opportunity/disengagement strikes and
    graph follow-ups do not call this path. A reaction cannot trigger a reaction.
    """
    actor=session.targets[target_id]
    if session.player_health<=0 or session.target_healths.get(target_id,0)<=0 or actor.get('team','enemy')!='enemy':return None
    inventory=actor_inventory(actor);rules=session._target_talent_rules(target_id)
    states={k:v for k,v in session.conditions.get(target_id,{}).items() if v.get('until',session.round_number)>=session.round_number}
    derived=reaction_derived(actor,rules,inventory,states,session.round_number)
    attack=derived['attack']
    chance=riposte_chance(rules,inventory,attack,states,derived.get('activeWeaponSet',1))
    if not chance:return None
    distance=session.grid.distance(session.player_position,session.target_positions[target_id])
    if distance>session._weapon_range(attack) or not session.grid.line_of_sight(session.target_positions[target_id],session.player_position):return None
    if random.random()>=chance:return None

    return free_attack(session,target_id,'player','Ответный удар')


def free_attack(session,source_id,target_id,name,*,chance=1,damage_bonus=0,ability=None,opportunity=False):
    """A free primary strike; both directions share rolls, shields and procs."""
    from talent_runtime import weapon_mode
    if source_id=='player':
        if target_id not in session.targets or session.player_health<=0 or session.target_healths.get(target_id,0)<=0:return None
        derived=getattr(session,'runtime_derived',getattr(session,'reaction_source_derived',{}));attack=derived.get('attack',{})
        if ability:
            before=len(session.events)
            result=session._execute_ability({**ability,'freeReaction':True},derived,getattr(session,'consumable_inventory',[]))
            for event in session.events[before:]:event['reaction']=True
            return result
        states=session.conditions.get('player',{})
        if any(k.removeprefix('special:') in {'stun','prone','freeze','sleep','paralyze','petrif','disarm'} for k in states):return None
        if session.grid.distance(session.player_position,session.target_positions[target_id])>session._weapon_range(attack):return None
        if not session.grid.line_of_sight(session.player_position,session.target_positions[target_id]) or chance<1 and random.random()>=chance:return None
        if opportunity:damage_bonus+=session.talent_runtime.get(23,0)
        accuracy_bonus=session.talent_runtime.get(22,0) if opportunity else 0
        defense_bonus=session._target_talent_rules(target_id).get(160,0) if opportunity else 0
        hit=session._roll_attack(name=name,accuracy=attack.get('accuracy',20)+accuracy_bonus,low=attack.get('damageMin',2)+damage_bonus,
            high=attack.get('damageMax',4)+damage_bonus,defense=session._defense('Парирование',target_id)+defense_bonus,
            defense_name=None if opportunity else 'Парирование',armor=session.targets[target_id].get('armor',0),target_id=target_id,
            penetration=attack.get('penetration',0),allow_reactions=False)
        session.events[-1]['reaction']=True
        session._weapon_talent_procs(target_id,hit['result'])
        return hit
    if target_id!='player':return None
    actor=session.targets[source_id]
    if session.player_health<=0 or session.target_healths.get(source_id,0)<=0:return None
    inventory=actor_inventory(actor);rules=session._target_talent_rules(source_id)
    states={k:v for k,v in session.conditions.get(source_id,{}).items() if v.get('until',session.round_number)>=session.round_number}
    derived=reaction_derived(actor,rules,inventory,states,session.round_number)
    attack=derived['attack']
    if not ability:
        if any(k.removeprefix('special:') in {'stun','prone','freeze','sleep','paralyze','petrif','disarm'} for k in states):return None
        if session.grid.distance(session.player_position,session.target_positions[source_id])>session._weapon_range(attack):return None
        if not session.grid.line_of_sight(session.target_positions[source_id],session.player_position) or chance<1 and random.random()>=chance:return None
    target_id=source_id

    # Execute through the same roll, armor, shields and weapon-proc handlers.
    clone=copy.deepcopy(session);victim='__riposte_attacker__'
    original=getattr(session,'runtime_character',{})
    source_derived=getattr(session,'runtime_derived',getattr(session,'reaction_source_derived',{}))
    baseline=source_derived.get('_baseDerived',source_derived)
    if original.get('skills') and '_baseDerived' not in getattr(session,'runtime_derived',{}):
        from registration_api import _derived
        from consumables import virtual_equipment
        from ability_rules import stance_equipment
        attribute_states={k:v for k,v in session.conditions.get('player',{}).items() if v.get('source',{}).get('AffectsStat') in {56,57,58,59,99,100}}
        baseline=_derived({**original,'active_weapon_set':session.active_weapon_set},getattr(session,'consumable_inventory',[])+virtual_equipment(attribute_states,session.round_number)+stance_equipment(session.active_stance))
    clone.targets={k:v for k,v in clone.targets.items() if k!=target_id}
    for other in clone.targets.values():other['team']='ally' if other.get('team','enemy')==actor.get('team','enemy') else 'enemy'
    clone.targets[victim]={'name':original.get('name','Атакующий'),'healthMax':session.player_health_max,
        'armor':baseline.get('armor',0),'armorByType':baseline.get('armorByType',{}),
        'defenses':baseline.get('defenses',{}),'incomingConversions':baseline.get('incomingConversions',{}),
        'talentRuntime':getattr(session,'talent_runtime',{}),'team':'enemy',
        'attack':baseline.get('attack',{}),'combatDerived':source_derived,
        'inventory':getattr(session,'consumable_inventory',[]),'character':original,
        'abilities':getattr(session,'runtime_talents',original.get('talents',[])),
        'combatStance':session.active_stance}
    clone.target_healths={k:v for k,v in clone.target_healths.items() if k!=target_id};clone.target_healths[victim]=session.player_health
    clone.target_positions={k:v for k,v in clone.target_positions.items() if k!=target_id};clone.target_positions[victim]=session.player_position
    clone.conditions={k:v for k,v in clone.conditions.items() if k not in {'player',target_id}}
    clone.conditions['player']=copy.deepcopy(states);clone.conditions[victim]=copy.deepcopy(session.conditions.get('player',{}))
    clone.player_position=session.target_positions[target_id];clone.player_health=session.target_healths[target_id];clone.player_health_max=actor['healthMax']
    clone.talent_runtime=rules;clone.runtime_talents=actor.get('abilities',[]);clone.runtime_derived=derived
    clone.runtime_character=actor.get('character',{'name':actor['name']});clone.consumable_inventory=inventory
    clone.active_weapon_set=derived.get('activeWeaponSet',1);clone.active_stance=actor.get('combatStance','')
    clone.stealthed=False;clone.suspicion={};clone.events=[];clone.engagements={}
    clone.resolving_talent_proc=False;before_log=len(clone.log)
    attack=clone._combat_derived(derived)['attack']
    if ability:
        clone.selected_target_id=victim
        clone.aim_point=clone.target_positions[victim] if ability['targeting']=='unit' else clone.player_position
        hit=clone._execute_ability({**ability,'freeReaction':True},derived,inventory)
    else:
        if opportunity:damage_bonus+=rules.get(23,0)
        accuracy_bonus=rules.get(22,0) if opportunity else 0
        defense_bonus=clone._target_talent_rules(victim).get(160,0) if opportunity else 0
        hit=clone._roll_attack(name=name,accuracy=attack.get('accuracy',20)+accuracy_bonus,low=attack.get('damageMin',2)+damage_bonus,high=attack.get('damageMax',4)+damage_bonus,
            defense=clone._defense('Парирование',victim)+defense_bonus,defense_name=None if opportunity else 'Парирование',armor=clone.targets[victim]['armor'],
            penetration=attack.get('penetration',0),target_id=victim,attack_mode='melee',allow_reactions=False)
        clone._weapon_talent_procs(victim,hit['result'])
    session.player_health=clone.target_healths[victim];session.conditions['player']=clone.conditions.get(victim,{})
    session.target_healths[target_id]=clone.player_health;session.conditions[target_id]=clone.conditions.get('player',{})
    session.player_position=clone.target_positions[victim]
    for key in session.targets:
        if key==target_id:continue
        session.target_healths[key]=clone.target_healths[key];session.conditions[key]=clone.conditions.get(key,{})
        session.target_positions[key]=clone.target_positions[key]
    remap=lambda key:target_id if key=='player' else 'player' if key==victim else key
    session.events.extend({**e,'sourceId':remap(e['sourceId']),'targetId':remap(e['targetId']),'reaction':True} for e in clone.events)
    lines=[f"{actor['name']}: {line}" for line in clone.log[before_log:]]
    session.log.extend(lines)
    if session.player_health<=0:session._break_stealth(name+' выводит персонажа из боя.')
    return {**hit,'line':' '.join(lines)}


def react_to_damage(session,target_id):
    from talent_batch_one import reactive_profiles
    if target_id=='player':
        health=session.player_health;maximum=session.player_health_max
        talents=getattr(session,'runtime_talents',[]);derived=getattr(session,'runtime_derived',getattr(session,'reaction_source_derived',{}))
        victim=next(iter(session._alive_targets()),None)
    else:
        actor=session.targets[target_id];health=session.target_healths[target_id];maximum=actor['healthMax']
        talents=actor.get('abilities',[]);inventory=actor_inventory(actor)
        derived=reaction_derived(actor,session._target_talent_rules(target_id),inventory,session.conditions.get(target_id,{}),session.round_number)
        victim='player'
    if health<=0 or victim is None:return
    for rule,threshold in reactive_profiles(talents,derived):
        key='talent-used:'+rule['key'];states=session.conditions.setdefault(target_id,{})
        if health/maximum>=threshold or key in states:continue
        states[key]={'name':rule['name']+' использован','until':999999,'beneficial':True}
        free_attack(session,target_id,victim,rule['name'],ability=rule)
