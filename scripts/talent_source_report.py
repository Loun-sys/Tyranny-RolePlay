"""Compact source inspection without dumping Unity pointers and VFX arrays."""
import json
import sys
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from ability_rules import resolve

STATUS_FIELDS={'Tag','AffectsStat','Value','ExtraValue','Duration','IntervalRate','Apply','DmgType','DefType','Skill',
               'ApplicationPrerequisites','TriggerAdjustment','LevelScaling','ContinuousApplicationAura',
               'OneHitUse','LastsUntilRest','MaxRestCycles','AttackPrefabKey','AbilityPrefabKey','AfflictionPrefabKey',
               'AttackTypeTriggerForLaunchAttack','UseTargetAsLaunchAttackOwner','IsHostile'}
ATTACK_FIELDS={'ValidTargets','AOEApplyToSelfOnly','BlastRadius','DefendedBy','DamageData','AccuracyBonus','Range',
               'm_attackSkills','SkipAnimation','IsWeaponAttack','AttackType','AttackMode'}

def compact(value):
    if isinstance(value,dict):return {k:compact(v) for k,v in value.items() if v not in (None,False,0,'',[],{})}
    if isinstance(value,list):return [compact(v) for v in value]
    return value

def report(key):
    row=resolve(key)
    if not row:return {'key':key,'missing':True}
    result={k:row.get(k) for k in ['key','name','description','weaponMask','abilityClass','passive','modal','range','targeting','grantedAbilities','source']}
    result['nodes']=[{**{k:n.get(k) for k in ['prefab','phase','side','tag','name']},
        'attack':{k:v for k,v in n.get('attack',{}).items() if k in ATTACK_FIELDS},
        'statuses':[{k:v for k,v in s.items() if k in STATUS_FIELDS} for s in n['statuses']]} for n in row['nodes']]
    result['abilityMods']=[{k:v for k,v in m.items() if k not in {'StatusEffects','m_deserializeInitialized'}} for m in row.get('abilityMods',[])]
    return compact(result)

if __name__=='__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    for key in sys.argv[1:]:print(json.dumps(report(key),ensure_ascii=False))
