"""Contextual armor modifiers, keyed by original stat IDs and resolved prefabs."""
import copy
from item_effects import active_equipment, game_data, unconditional

WEAPON_CRIT_PROCS={
    'MOD_Acc_Suffering_Attack','MOD_ACC_Rare_MultiStrike_OnCrit',
    'MOD_ACC_Rending_OnCrit','MOD_ACC_Weighted_OnCrit','MOD_ACC_Kindling_OnCrit',
}
GRANTED_PASSIVES={'MOD_UNIQUE_ACC_LightfootGambit_Passive','MOD_ACC_Fleeing_Passive'}
GRANTED_EVENTS={'MOD_UNIQUE_ACC_CommandersWill_Abl','MOD_ACC_Martyr_OnDeath','MOD_ACC_Bloodthirsty_OnKill'}


def granted_rules(inventory,active_set=1):
    from ability_rules import resolve
    for item in active_equipment(inventory,active_set):
        if item.get('equipped_slot')=='Эффект':continue
        for mod in game_data(item).get('mods',[]):
            graphs=[g for g in mod.get('triggerGraphs',[]) if g.get('stat')==2097]
            effects=[e for e in mod.get('StatusEffectsOnEquip',[]) if e.get('AffectsStat')==2097]
            for effect,graph in zip(effects,graphs):
                if not unconditional(effect) or not graph['graph']:continue
                key=graph['graph'][0].get('prefab')
                if key in GRANTED_PASSIVES|GRANTED_EVENTS:
                    row=resolve(key)
                    if row:yield item,row


def grant_supported(game):
    graphs=[g for m in game.get('mods',[]) for g in m.get('triggerGraphs',[]) if g.get('stat')==2097]
    return bool(graphs) and all(g['graph'] and g['graph'][0].get('prefab') in GRANTED_PASSIVES|GRANTED_EVENTS for g in graphs)


def crit_procs_supported(game):
    groups=[g for mod in game.get('mods',[]) for g in mod.get('triggerGraphs',[]) if g.get('stat')==2156]
    return bool(groups) and all(g['graph'] and g['graph'][0].get('prefab') in WEAPON_CRIT_PROCS for g in groups)


def weapon_crit_procs(inventory,derived,active_set=1,mode='melee'):
    from ability_rules import resolve
    from ability_graphs import branch
    for item in active_equipment(inventory,active_set):
        if item.get('equipped_slot')=='Эффект':continue
        for mod in game_data(item).get('mods',[]):
            effects=[e for e in mod.get('StatusEffectsOnEquip',[]) if e.get('AffectsStat')==2156]
            graphs=[g for g in mod.get('triggerGraphs',[]) if g.get('stat')==2156]
            for effect,graph in zip(effects,graphs):
                if not unconditional(effect) or not graph['graph']:continue
                weapon=effect.get('AttackTypeTriggerForLaunchAttack',2)
                ranged=mode=='ranged'
                if weapon in {0,1} and ranged!=(weapon==1):continue
                key=graph['graph'][0].get('prefab')
                if key not in WEAPON_CRIT_PROCS:continue
                row=resolve(key)
                proc=branch(row,key,derived) if row else None
                if proc and proc['supported']:
                    yield {**proc,'name':item.get('name','Экипировка')+' — '+mod.get('localizedName',proc['name'])}


def source_effects(inventory, active_set=1):
    for item in active_equipment(inventory, active_set):
        if item.get('equipped_slot')=='Эффект':continue
        game=game_data(item)
        for effect in game.get('statusEffects', []):
            if unconditional(effect):yield item,effect


def rules(inventory, active_set=1):
    result={}
    for _,effect in source_effects(inventory,active_set):
        stat=effect['AffectsStat'];value=float(effect.get('Value',0))
        if stat in {101,2099}:result[stat]=result.get(stat,0)+value
        elif stat==2116:result[stat]=result.get(stat,1)*value
    return result


def conditional_equipment(inventory, health_fraction=1, wounds=0, active_set=1):
    """StatusEffectTrigger: 8/9 = health threshold; 12 = any wounds.

    GetCurrentAppliedValue adds ValueAdjustment once (MaxTriggerCount=1),
    subtracting its neutral 1 for a multiplier. Wounds do not stack this bonus.
    """
    result=[]
    for item,row in granted_rules(inventory,active_set):
        if row['key'] not in GRANTED_PASSIVES:continue
        effects=[]
        for node in row['nodes']:
            for effect in node['statuses']:
                if effect.get('AffectsStat')!=2166:continue
                trigger=effect.get('TriggerAdjustment',{})
                value=float(effect['Value'])
                if trigger.get('Type')==12 and wounds>0:value+=float(trigger.get('ValueAdjustment',1))-1
                effects.append({**copy.deepcopy(effect),'Value':value,'TriggerAdjustment':{}})
        if effects:result.append({'name':item.get('name','Экипировка'),'category':'Эффекты','equipped_slot':'Эффект','armor':0,'properties':{'gameData':{'statusEffects':effects}}})
    for item in active_equipment(inventory,active_set):
        if item.get('equipped_slot')=='Эффект':continue
        effects=[]
        for effect in game_data(item).get('statusEffects',[]):
            trigger=effect.get('TriggerAdjustment',{});kind=trigger.get('Type',0)
            if kind not in {8,9,12} or effect.get('ApplicationPrerequisites') or effect.get('Apply')!=0:continue
            active=(kind==8 and health_fraction<float(trigger.get('TriggerValue',0)) or
                    kind==9 and health_fraction>float(trigger.get('TriggerValue',0)) or kind==12 and wounds>0)
            if not active:continue
            value=float(effect.get('Value',0))+float(trigger.get('ValueAdjustment',0))
            if effect['AffectsStat'] in {45,188,2000,181,2166,153,226,169}:value-=1
            effects.append({**copy.deepcopy(effect),'Value':value,'TriggerAdjustment':{}})
        if effects:
            result.append({'name':item.get('name','Экипировка'),'category':'Эффекты','equipped_slot':'Эффект',
                           'armor':0,'properties':{'gameData':{'statusEffects':effects}}})
    return result


def on_kill(session,target):
    from ability_rules import profile
    from ability_graphs import branch
    derived=getattr(session,'runtime_derived',getattr(session,'reaction_source_derived',{}))
    for item,row in granted_rules(getattr(session,'consumable_inventory',[]),session.active_weapon_set):
        if row.get('abilityClass')!='TriggeredOnKillAbility':continue
        attack=next((n for n in row['nodes'] if n.get('attack')),None)
        if attack:
            proc=branch(row,attack['prefab'],derived)
            if proc and proc['supported']:session._resolve_graph_attack(proc,target)
        else:
            proc=profile(row,derived)
            if proc['supported']:session._apply_ability_effects(proc,'player','self')
        session.log.append(item.get('name','Экипировка')+': эффект при победе над противником.')


def reset_death_triggers(session,target):
    health=session.player_health if target=='player' else session.target_healths.get(target,0)
    if health>0:
        states=session.conditions.get(target,{})
        for key in list(states):
            if key.startswith('equipment-death:'):states.pop(key)


def on_death(session,target,before):
    from ability_rules import profile
    from talent_reactions import actor_inventory
    health=session.player_health if target=='player' else session.target_healths.get(target,0)
    if before<=0 or health>0:return
    actor={} if target=='player' else session.targets[target]
    inventory=getattr(session,'consumable_inventory',[]) if target=='player' else actor_inventory(actor)
    active_set=session.active_weapon_set if target=='player' else actor.get('active_weapon_set',1)
    derived=getattr(session,'runtime_derived',getattr(session,'reaction_source_derived',{})) if target=='player' else actor.get('combatDerived',{})
    center=session.player_position if target=='player' else session.target_positions[target]
    team='ally' if target=='player' else actor.get('team','enemy')
    states=session.conditions.setdefault(target,{})
    for item,row in granted_rules(inventory,active_set):
        if row.get('abilityClass')!='TriggeredOnDeathAbility':continue
        key='equipment-death:'+row['key']
        if key in states:continue
        proc=profile(row,derived)
        if not proc['supported']:continue
        states[key]={'name':item.get('name','Экипировка'),'until':999999,'beneficial':True}
        effects=[{**e,'side':'target'} for e in proc['effects']]
        recipients=[k for k,h in session.target_healths.items() if h>0 and session.targets[k].get('team','enemy')==team]
        if team=='ally' and session.player_health>0:recipients.append('player')
        for recipient in recipients:
            position=session.player_position if recipient=='player' else session.target_positions[recipient]
            if session.grid.distance(center,position)<=proc['area'] and session.grid.line_of_sight(center,position):
                session._apply_ability_effects({**proc,'effects':effects},recipient,'target')
        session.log.append(item.get('name','Экипировка')+': при поражении исцеляет ближайших живых союзников.')


def regeneration(inventory, health_fraction=1, wounds=0, active_set=1):
    effects=[e for _,e in source_effects(inventory,active_set)]
    effects += [e for item in conditional_equipment(inventory,health_fraction,wounds,active_set)
                for e in game_data(item)['statusEffects']]
    return sum(float(e.get('Value',0)) for e in effects if e.get('AffectsStat')==116 and e.get('IntervalRate'))


def spell_reflection(inventory,active_set=1):
    return sum(float(e.get('Value',0)) for _,e in source_effects(inventory,active_set) if e.get('AffectsStat')==2130)/100


def skill_xp_multiplier(inventory,skill,active_set=1):
    from ability_rules import SKILLS
    source_skills={**SKILLS,1:'Хитроумие',8:'',11:'Волшебный посох'}
    per_item={}
    for item,effect in source_effects(inventory,active_set):
        if effect.get('AffectsStat')!=2113:continue
        if effect.get('Skill') and source_skills.get(effect['Skill'])!=skill:continue
        identity=id(item)
        per_item[identity]=max(per_item.get(identity,0),round(float(effect.get('Value',1))-1,6))
    return 1+sum(per_item.values())


def affliction_tags(inventory, stat, active_set=1):
    """Resolved references avoid guessing an immunity from an item name."""
    result=set()
    for item in active_equipment(inventory,active_set):
        for mod in game_data(item).get('mods',[]):
            if not any(e.get('AffectsStat')==stat and unconditional(e) for e in mod.get('StatusEffectsOnEquip',[])):
                continue
            for entry in mod.get('triggerGraphs',[]):
                if entry.get('stat')!=stat:continue
                for node in entry['graph']:
                    if node.get('prefab'):result.add(node['prefab'].casefold())
                    if node.get('Tag'):result.add(node['Tag'].casefold())
    return result


def immune(inventory,effect,active_set=1):
    aliases={'root':'rooted','stun':'stun','prone':'prone','freeze':'frozen',
             'silence':'silenced','paralyze':'paralyzed','petrif':'petrified',
             'sleep':'asleep','blind':'blinded','disarm':'disarm','hobble':'hobbled'}
    keys=affliction_tags(inventory,150,active_set)
    return bool(keys & {str(effect.get('affliction','')).casefold(),
                        str(effect.get('control','')).casefold(),
                        aliases.get(effect.get('control'),'')})


def afflicted_damage_bonus(inventory,states,active_set=1):
    aliases={'prone':'aff_prone','stun':'aff_stunned','paralyze':'aff_paralyzed',
             'daze':'aff_dazed','hobble':'aff_hobbled','bleed':'aff_bleeding',
             'burn':'aff_burning','poison':'aff_poisoned','sunder':'aff_sundered'}
    present=set()
    for key,state in states.items():
        short=key.removeprefix('special:').casefold()
        present.update({short,aliases.get(short,'')})
        for source in (state,state.get('source',{})):
            present.update(str(source.get(field,'')).casefold() for field in ('affliction','AfflictionPrefabKey','Tag'))
    bonus=0.
    for item in active_equipment(inventory,active_set):
        if item.get('equipped_slot')=='Эффект':continue
        for mod in game_data(item).get('mods',[]):
            graphs=[g for g in mod.get('triggerGraphs',[]) if g.get('stat')==2057]
            effects=[e for e in mod.get('StatusEffectsOnEquip',[]) if e.get('AffectsStat')==2057]
            for effect,graph in zip(effects,graphs):
                if not unconditional(effect):continue
                required={str(node.get(field,'')).casefold() for node in graph['graph'] for field in ('prefab','Tag')}
                required.discard('')
                if required & present:bonus+=float(effect.get('Value',1))-1
    # StatusEffect.BeforeHits calls SDK.DamageInfo.DamageMult once per matching
    # source effect; DamageMult adds value-1. Repeated copies of one affliction
    # therefore cannot multiply the same effect again.
    return bonus


def attack_modifiers(inventory, *, target_fraction=1, night=False, active_set=1,target_states=None):
    multiplier=1.;critical=0.
    for _,effect in source_effects(inventory,active_set):
        stat=effect['AffectsStat'];value=float(effect.get('Value',0))
        if stat==2169 and night:multiplier+=value-1
        elif stat==2137 and target_fraction*100<float(effect.get('ExtraValue',0)):
            critical+=value
    multiplier+=afflicted_damage_bonus(inventory,target_states or {},active_set)
    return {'multiplier':multiplier,'criticalChance':critical}
