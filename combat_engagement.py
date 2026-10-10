"""Directed, capacity-limited melee engagements shared by preview and execution."""
from talent_runtime import weapon_mode

BLOCKED={'sleep','prone','freeze','frozen','stun','paralyze','paralyzed','petrif','petrified','disarm'}

def graph(session,previous=None):
    units={'player':{'team':'player','attack':getattr(session,'runtime_derived',{}).get('attack',{})},**session.targets}
    positions={'player':session.player_position,**session.target_positions}
    health={'player':session.player_health,**session.target_healths}
    prior=previous if previous is not None else getattr(session,'engagements',{})
    result={}
    def hostile(a,b):
        if a=='player' or b=='player':return units[b if a=='player' else a].get('team','enemy')=='enemy'
        return units[a].get('team','enemy')!=units[b].get('team','enemy')
    def immune(key):
        rules=session._target_talent_rules(key)
        return 24 in rules or 2145 in rules or any(s.get('source',{}).get('AffectsStat') in {24,151,2145}
                 for s in session.conditions.get(key,{}).values())
    for key,unit in units.items():
        states=session.conditions.get(key,{})
        attack=unit.get('attack',{})
        if health.get(key,0)<=0 or weapon_mode(attack)!='melee' or any(k.removeprefix('special:') in BLOCKED for k in states):continue
        rules=session._target_talent_rules(key)
        base=unit.get('memoryEngagementLimit',getattr(session,'runtime_character',{}).get('memoryEngagementLimit',1) if key=='player' else 1) or 1
        capacity=max(0,base+int(rules.get(20,0)))
        radius=session._weapon_range(attack)
        candidates=[other for other in units if other!=key and health.get(other,0)>0 and hostile(key,other) and not immune(other)
                    and session.grid.distance(positions[key],positions[other])<=radius
                    and session.grid.line_of_sight(positions[key],positions[other])
                    and (other!='player' or session.visible_to(key))
                    and not units[other].get('hidden',False)]
        # Retain existing engagements until they actually break, then fill vacancies.
        selected=[other for other in prior.get(key,[]) if other in candidates][:capacity]
        preferred=getattr(session,'selected_target_id','') if key=='player' else unit.get('selectedTargetId','')
        candidates.sort(key=lambda other:(other!=preferred,session.grid.distance(positions[key],positions[other]),other))
        selected.extend(other for other in candidates if other not in selected and len(selected)<capacity)
        result[key]=selected
    return result

def incoming_count(session,key):
    return sum(key in victims for victims in graph(session).values())

def refresh(session,reactions=False):
    old=getattr(session,'engagements',{});current=graph(session,old);session.engagements=current
    if not reactions:return
    from talent_batch_one import engagement_level
    from talent_reactions import free_attack
    for source,victims in current.items():
        for victim in victims:
            if victim in old.get(source,[]):continue
            # The engaged defender, not the controller, launches the entry attack.
            if victim=='player':talents=getattr(session,'runtime_talents',[])
            else:talents=session.targets[victim].get('abilities',[])
            level,chance=engagement_level(talents)
            if level:
                bonus=session.targets.get(victim,{}).get('disengagementDamageBonus',0)*level
                free_attack(session,victim,source,'Вступление в бой',chance=chance,damage_bonus=bonus)
