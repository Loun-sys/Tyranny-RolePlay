"""Resolve exported attack edges without flattening sibling attacks into one buff."""
import copy

GRAPH_KEYS={
 'PSV_PC_Defense_PinningStrike','PSV_PC_Power_ExposeWeakness','PSV_PC_Leadership_SeizeTheInitiative',
 'PSV_PC_Magic_EnfeeblingTouch','PSV_PC_Agility_UnseenAdvantage','PSV_PC_Ranged_TerrorShot',
 'PSV_Comp_Beastwoman_TasteOfBlood','PSV_Comp_Lantry_ChargedThrow',
}
UPGRADE_GRAPH_KEYS={'Abl_PC_Defense_StaggeringForce','Abl_PC_Leadership_ToArms','Abl_Comp_Defender_SoundOfWar'}

def branch(row,key,derived=None):
    from ability_rules import profile
    nodes=[];queue=[key];seen=set();extra=[]
    while queue:
        current=queue.pop(0)
        if current in seen:continue
        seen.add(current)
        for node in row['nodes']:
            if node['prefab']!=current:continue
            nodes.append({**copy.deepcopy(node),'side':'target'})
            for edge in node.get('edges',[]):
                if edge['kind'] in {'ExtraAOE','SecondAOE','FollowUpAttacks','ChildAttacks'}:
                    if edge['key'] not in extra:extra.append(edge['key'])
                elif edge['kind'] not in {'AttackPrefab','AbilityPrefab'}:queue.append(edge['key'])
    attack=next((n['attack'] for n in nodes if n.get('attack')),None)
    if not attack:return None
    damage=attack.get('DamageData',{});target=attack.get('ValidTargets',1);radius=attack.get('BlastRadius',0)
    child={**copy.deepcopy(row),'nodes':nodes,'graphResolved':True,'passive':False,'modal':False,
        'isTalentUpgrade':False,'source':{},'range':0 if target==101 else max(1,row.get('range',1)),
        'targeting':'self' if target==101 else 'area' if radius else 'unit','area':radius,
        'weaponRange':False,'angle':360,'excludeTarget':bool(attack.get('ExcludeTarget')),'damageMin':damage.get('Minimum',0),'damageMax':damage.get('Maximum',0),
        'weaponMultiplier':damage.get('WeaponDamageMult',0)*attack.get('DamageMultiplier',1),
        'accuracyBonus':attack.get('AccuracyBonus',0),'skills':attack.get('m_attackSkills',[]),
        'defense':{0:'Парирование',1:'Выносливость',2:'Воля',3:'Магия',5:'Нет'}.get(attack.get('DefendedBy',0),'Парирование'),
        'damageType':damage.get('Type',9),'penetration':attack.get('DTBypass',0),'push':attack.get('PushDistance',0)}
    result=profile(child,derived)
    if attack.get('BaseInterruptValue'):
        result['effects'].append({'control':'interrupt','name':'Подготовка атаки прервана','side':'target','Duration':.1,'rounds':1})
        result['supported']=True;result['limitation']=''
    result['secondaryGraphs']=[p for k in extra if (p:=branch(row,k,derived))]
    return result

def procs(row,derived=None):
    if row['key'] not in GRAPH_KEYS:return None
    result=[]
    stealth=any(p['Type']==25 for p in row.get('source',{}).get('activation',[]))
    for node in row['nodes']:
        if node['phase']!='root' or node['side']!='self':continue
        for trigger in node['statuses']:
            if trigger['AffectsStat'] not in {2156,2159}:continue
            child=branch(row,trigger.get('AttackPrefabKey',''),derived)
            if not child or not child['supported']:return []
            child.update(triggerStat=trigger['AffectsStat'],weaponTrigger=trigger.get('AttackTypeTriggerForLaunchAttack',2),
                         stealthOnly=stealth,maxTriggers=trigger.get('TriggerAdjustment',{}).get('MaxTriggerCount',0))
            result.append(child)
    return result

def upgrade_launches(row,derived):
    result=[]
    for node in row['nodes']:
        if node['phase']!='upgrade' or node['prefab'] not in UPGRADE_GRAPH_KEYS:continue
        for status in node['statuses']:
            if status['AffectsStat'] not in {178,2159}:continue
            child=branch(row,status.get('AttackPrefabKey',''),derived)
            if child:child.update(onWeaponHit=status['AffectsStat']==2159);result.append(child)
    return result
