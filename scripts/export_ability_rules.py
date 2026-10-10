"""Export combat rules from serialized abilities, preserving reference edge context."""
import copy,json,math,re,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts.game_asset_index import GameIndex,localized_tables
from localization import localize_game_text

COMBAT_REFS={'Afflictions','AfflictionPrefab','AttackPrefab','AbilityPrefab','ExtraAOE','SecondAOE','FollowUpAttacks','AttackPrefabTriggeredOn','ChildAttacks','AbilityMods','StatusEffects','m_afflictionData','AoeOnKill','SummonPrefab'}
ATTACK_FIELDS={'DamageData','DamageMultiplier','AttackDistance','OverrideAttackDistance','UsePrimaryWeaponRange','AccuracyBonus','DTBypass','DefendedBy','SecondaryDefense','ValidTargets','ApplyToSelfOnly','PushDistance','BlastRadius','ExcludeTarget','DamageAngleDegrees','ConeAngle','TargetAngle','m_attackSkills','UsePrimaryAttack','UseFullAttack','Bounces','BounceRange','BounceMultiplier','BaseInterruptValue','RecoveryTime','PersonalCooldownModifier','AttackVariation'}
DEFENSE={0:'Парирование',1:'Выносливость',2:'Воля',3:'Магия',5:'Нет'}
ATTACK_FIELDS|={'SummonFileList','SummonedLifetime','DestroyExistingSummons','ReplaceTargettedBy','HowManyToSummon','SummonType','Duration','OverrideInterval'}

def main():
    g=GameIndex();ru=localized_tables();en=localized_tables('en')
    def text(ref,tables=ru,adapt=True):
        if not isinstance(ref,dict):return ''
        table={5:'items',6:'abilities',19:'afflictions'}.get(ref.get('StringTable'))
        result=tables.get(table,{}).get(ref.get('StringID'),'') or ref.get('OverrideString','')
        result=re.sub(r'\[/?url(?:=[^]]+)?\]|</?(?:b|i)>','',result).strip()
        return localize_game_text(result) if adapt else result
    def walk(root):
        queue=[(o,t,0,'self','root') for o,t in g.components(root)];seen=set();nodes=[]
        while queue and len(nodes)<200:
            obj,t,inherited,side,phase=queue.pop(0);ident=(obj.assets_file.name,obj.path_id,inherited,side,phase)
            if ident in seen:continue
            seen.add(ident);prefab=g.name(obj)
            attack='DamageData' in t or 'SummonFileList' in t
            local_side=('self' if t.get('ApplyToSelfOnly') else 'target') if attack else side
            node={'prefab':prefab,'phase':phase,'side':local_side,'name':text(t.get('DisplayName',{})),'tag':t.get('Tag',''),
                  'attack':{k:copy.deepcopy(v) for k,v in t.items() if k in ATTACK_FIELDS} if attack else {},'statuses':[], 'edges':[]}
            for s in t.get('StatusEffects',t.get('m_phraseData',[])):
                s=copy.deepcopy(s)
                for field in ('AttackPrefab','AbilityPrefab','AfflictionPrefab'):
                    s[field+'Key']=g.name(g.resolve(obj,s.get(field)))
                if inherited and not s.get('Duration'):s['Duration']=inherited
                s['phase']=phase;s['side']=local_side;s['affliction']=prefab if phase=='affliction' else ''
                node['statuses'].append(s)
            if attack or node['statuses'] or phase=='affliction':nodes.append(node)
            def follow(value,edge,key):
                if isinstance(value,list):
                    for v in value:follow(v,edge,key)
                elif isinstance(value,dict):
                    if 'm_PathID' in value:
                        target=g.resolve(obj,value)
                        child_name=g.name(target)
                        if child_name:node['edges'].append({'kind':key,'key':child_name})
                        child_side=local_side if local_side=='self' and phase!='root' else ('target' if attack else local_side)
                        if t.get('AbilityMods') and key in {'AfflictionPrefab','AttackPrefab'}:child_side='target'
                        child_phase='affliction' if key in {'AfflictionPrefab','m_afflictionData'} else 'followup' if key=='FollowUpAttacks' else 'attack' if key in {'AttackPrefab','ExtraAOE','SecondAOE','AoeOnKill','SummonPrefab'} else phase
                        duration=float(edge.get('Duration',inherited) or inherited)
                        for co,ct in g.components(target):queue.append((co,ct,duration,child_side,child_phase))
                    else:
                        for k,v in value.items():
                            if k in COMBAT_REFS:follow(v,value,k)
            for key,value in t.items():
                if key in COMBAT_REFS:follow(value,t,key)
            for s in t.get('StatusEffects',t.get('m_phraseData',[])):
                for key in COMBAT_REFS:
                    if key in s:follow(s[key],s,key)
        return nodes
    rows=[];icons=ROOT/'web/assets/ability-icons';icons.mkdir(parents=True,exist_ok=True)
    for group,components in g.groups.items():
        prefab=g.names.get(group,'')
        candidates=[(o,t) for o,t in components if 'DisplayName' in t and ('CooldownType' in t or 'AbilityMods' in t)]
        if not candidates:continue
        obj,t=max(candidates,key=lambda p:bool(text(p[1].get('Description',{}))))
        name=text(t['DisplayName'])
        if not name:continue
        nodes=walk(obj);attacks=[n['attack'] for n in nodes if n['attack'] and n['phase'] in {'root','attack'}]
        primary=attacks[0] if attacks else {};damage=primary.get('DamageData',{})
        is_talent='AbilityMods' in t and 'CooldownType' not in t
        ability_mods=copy.deepcopy(t.get('AbilityMods',[]))
        for mod in ability_mods:
            for status in mod.get('StatusEffects',[]):
                for field in ('AttackPrefab','AbilityPrefab','AfflictionPrefab'):
                    status[field+'Key']=g.name(g.resolve(obj,status.get(field)))
        if is_talent:
            nodes.append({'prefab':prefab,'phase':'upgrade','side':'target','name':name,'tag':'','attack':{},
                          'statuses':[s for mod in ability_mods for s in mod.get('StatusEffects',[])]})
        mode=t.get('CooldownType',0);seconds=float(t.get('CooldownTimerDuration',0) if mode==3 else t.get('Cooldown',0))
        icon='';texture=g.resolve(obj,t.get('Icon'))
        if texture and texture.type.name=='Texture2D':
            tx=texture.read();filename=re.sub('[^a-zA-Z0-9_-]','_',tx.m_Name)+'.png';dest=icons/filename
            if not dest.exists():tx.image.save(dest)
            icon='assets/ability-icons/'+filename
        radius=max((float(a.get('BlastRadius',0)) for a in attacks),default=0)
        angle=float(primary.get('DamageAngleDegrees',primary.get('ConeAngle',primary.get('TargetAngle',0))))
        targeting='self' if not attacks or primary.get('ApplyToSelfOnly') else 'cone' if 0<angle<360 and radius>0 else 'area' if radius>0 else 'unit'
        row={'key':prefab,'prefab':prefab,'name':name,'name_en':text(t['DisplayName'],en,False),'description':text(t.get('Description',{})),
            'abilityClass':str(g.resolve(obj,t.get('m_Script')).read().m_ClassName) if g.resolve(obj,t.get('m_Script')) else '',
            'passive':bool(t.get('Passive')) or is_talent,'modal':bool(t.get('Modal')),'icon':icon or 'assets/game-combat/icon_option_talents.png',
            'isTalentUpgrade':is_talent,'abilityMods':ability_mods,'skillBonuses':t.get('SkillBonuses',[]),
            'grantedAbilities':[g.name(g.resolve(obj,ref)) for ref in t.get('Abilities',[])],
            'triggerOnPartyKill':bool(t.get('TriggerOnPartyKill')),
            'bonusDamageMult':float(t.get('BonusDamageMult',1)),'specializationCategory':t.get('SpecializationCategory'),
            'cooldown':math.ceil(seconds/10),'cooldownSeconds':seconds,'oncePerBattle':mode in {1,2},'cooldownMode':mode,
            'range':math.ceil(float(primary.get('OverrideAttackDistance') or primary.get('AttackDistance',0))),
            'weaponRange':bool(primary.get('UsePrimaryWeaponRange')),'area':math.ceil(radius),'angle':angle,'targeting':targeting,
            'damageMin':float(damage.get('Minimum',0)),'damageMax':float(damage.get('Maximum',0)),
            'weaponMultiplier':float(damage.get('WeaponDamageMult',0))*float(primary.get('DamageMultiplier',1)),
            'damageType':damage.get('Type',9),'accuracyBonus':primary.get('AccuracyBonus',0),
            'defense':DEFENSE.get(primary.get('DefendedBy',0),'Парирование'),'penetration':primary.get('DTBypass',0),
            'push':primary.get('PushDistance',0),'weaponMask':t.get('PermittedWeaponTypes',0),'skills':primary.get('m_attackSkills',[]),
            'attackCount':2 if 'FlurryOfBlows' in prefab else 1,'sourceVersion':1,'source':{'archive':g.asset_bundles[obj.assets_file.name.casefold()],'nameRef':t['DisplayName'],
               'descriptionRef':t.get('Description'),'activation':t.get('ActivationPrerequisites',[]),'application':t.get('ApplicationPrerequisites',[])},'nodes':nodes}
        row['breathCost']=max((int(p.get('Value',0)) for p in t.get('ActivationPrerequisites',[]) if p.get('Type')==9 and p.get('IsConsumed')),default=0)
        row['aura']={field:t.get(field,0) for field in ('FriendlyRadius','AuraType','AuraIntervalSpeed','TriggerOnHit','TriggerOnWounded','RemoveWhenDeactivated')}
        row['phrases']=[]
        for ref in t.get('PhraseTemplates',[]):
            phrase=g.resolve(obj,ref)
            component=next((ct for co,ct in g.components(phrase) if 'm_phraseData' in ct),None)
            if not component:continue
            row['phrases'].append({'key':g.name(phrase),'name':text(component.get('DisplayName')),
                'description':text(component.get('Description')),'level':component.get('Level',1),
                'defense':DEFENSE.get(component.get('DefendedBy',5),'Нет'),'nodes':walk(phrase)})
        if row['phrases']:
            # Assembly-CSharp: AttackData..ctor, Phrase.get_Recitation/CalculateLinger.
            row['song']={'type':t.get('SongType',0),'radius':4,'recitationPerLevel':2,'recitationBase':2,'lingerBase':1}
        rows.append(row)
    # Same prefab across bundles must prefer the canonical abilities archive.
    unique={}
    for row in sorted(rows,key=lambda r:r['source']['archive']=='abilities'):unique[row['key']]=row
    rows=sorted(unique.values(),key=lambda r:r['key'])
    (ROOT/'catalog/ability_rules.json').write_text(json.dumps({'abilities':rows},ensure_ascii=False,indent=2),encoding='utf-8')
    print('Original ability rules:',len(rows),'active:',sum(not r['passive'] for r in rows))
if __name__=='__main__':main()
