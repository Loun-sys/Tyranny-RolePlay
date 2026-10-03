"""Discord adapter for the same source-backed executor used on the tactical site."""
import copy
from ability_rules import resolve,profile

def actor_derived(actor,include_effects=True):
    from registration_api import _derived,_clean_inventory
    from consumables import virtual_equipment
    c={'attributes':getattr(actor,'equipment_base_attributes',actor.attributes),
       'skills':{k:{'value':v} for k,v in getattr(actor,'equipment_base_skills',actor.skills).items()},
       'health_max':getattr(actor,'equipment_base_health_max',actor.health_max),'talents':actor.talents,
       'active_weapon_set':getattr(actor,'active_weapon_set',1)}
    effects=virtual_equipment(getattr(actor,'consumable_states',{}),getattr(actor,'consumable_round',1)) if include_effects else []
    result=_derived(c,_clean_inventory(actor.inventory)+effects)
    if actor.character_id is None and not actor.inventory:
        from registration_api import _apply_property
        result['armor']+=actor.armor
        result['armorByType']={k:v+actor.armor for k,v in result['armorByType'].items()}
        result['attack']['damageMin']=actor.damage_min;result['attack']['damageMax']=actor.damage_max
        result['attack']['accuracy']=round(_apply_property(actor.accuracy,effects,'Точность'))
        for name in ('Парирование','Уклонение'):
            if name not in c['skills']:result['defenses'][name]=round(_apply_property(actor.accuracy,effects,name))
    return result

def find_owned(actor,name):
    return next((t for t in actor.talents if t['name']==name or (resolve(t) or {}).get('name')==name),None)

def actor_ability(actor,talent):
    row=resolve(talent)
    if not row:return None
    from combat import weapon_range
    return profile(row,actor_derived(actor),weapon_range(actor))

def execute(session,actor,target,talent):
    from training_combat import TrainingSession
    from registration_api import _clean_inventory
    from combat import apply_equipment
    rule=actor_ability(actor,talent)
    if not rule or rule['passive'] or not rule['supported']:raise ValueError((rule or {}).get('limitation') or 'У способности нет боевого обработчика.')
    battle=TrainingSession(actor.character_id or 0);battle.grid=session.grid;battle.round_number=session.round_number
    battle.player_position=(actor.x,actor.y);battle.player_health=actor.health;battle.player_health_max=actor.health_max
    battle.initialized=True;battle.cooldowns={'ability:'+rule['key']:actor.cooldowns.get(talent['name'],0)}
    battle.targets={u.key:{'name':u.name,'healthMax':u.health_max,'armor':actor_derived(u,False)['armor'],'defenses':actor_derived(u,False)['defenses'],'team':'enemy' if u.team!=actor.team else 'ally'} for u in session.combatants.values() if u is not actor}
    battle.target_healths={u.key:u.health for u in session.combatants.values() if u is not actor}
    battle.target_positions={u.key:(u.x,u.y) for u in session.combatants.values() if u is not actor}
    battle.conditions={u.key:copy.deepcopy(getattr(u,'consumable_states',{})) for u in session.combatants.values() if u is not actor}
    battle.conditions['player']=copy.deepcopy(getattr(actor,'consumable_states',{}))
    battle.selected_target_id=target.key;battle.aim_point=(target.x,target.y)
    before={u.key:u.health for u in session.combatants.values()}
    result=battle._execute_ability(rule,actor_derived(actor),_clean_inventory(actor.inventory))
    actor.health=battle.player_health;actor.x,actor.y=battle.player_position;actor.consumable_states=battle.conditions.get('player',{})
    actor.cooldowns[talent['name']]=battle.cooldowns['ability:'+rule['key']]
    for u in session.combatants.values():
        if u is not actor:
            u.health=battle.target_healths[u.key];u.x,u.y=battle.target_positions[u.key];u.consumable_states=battle.conditions.get(u.key,{})
        u.consumable_round=session.round_number
        if u.character_id is None and not u.inventory:
            effective=actor_derived(u);u.equipment_defenses=effective['defenses'];u.equipment_armor_by_type=effective['armorByType']
        else:apply_equipment(u)
    changes=[(u,before[u.key]) for u in session.combatants.values() if u is not target and u.health!=before[u.key]]
    return result['line'],changes
