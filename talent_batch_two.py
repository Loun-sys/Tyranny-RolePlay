"""Second reviewed batch: event-driven bonuses and directed ability graphs."""
import copy
import math

BATCH_KEYS=(
 'PSV_PC_Magic_ImbueTheElementsFire','PSV_PC_Magic_ImbueTheElementsFrost','PSV_PC_Magic_ImbueTheElementsShock',
 'PSV_Comp_Verse_KnowYourEnemy_01','PSV_Comp_Verse_KnowYourEnemy_02','PSV_Comp_Verse_LethalOpening',
 'Abl_Comp_Lantry_Renewal','ABL_Comp_Lantry_GreaterRenewal','PSV_Comp_Beastwoman_SeizePrey',
 'PSV_Comp_Sirin_DisarmingGuise','Abl_Comp_Defender_Stance_Phalanx_02','PSV_Comp_Sirin_VengefulPitch',
 'Abl_Comp_Sirin_AriaOfDissonance','ABL_HH_Sentinel_Last_Stand','PSV_Comp_Beastwoman_ScarsOfBattle',
 'Abl_Comp_Lantry_WatchersJudgement','Abl_PC_Leadership_MarkEnemy','PSV_Comp_Sirin_RevivingSong',
 'TLN_Comp_Lantry_ArcaneJudgment','PSV_Comp_Verse_BloodCallsToBlood','PSV_Comp_RngMagic_ClearMind',
 'PSV_Comp_Beastwoman_DualClaw','ABL_Comp_Beastwoman_ShadowOfDeath','Abl_Comp_Lantry_EraseTheRecord',
 'Abl_Comp_Sirin_AriaOfResolve','ABL_Comp_Beastwoman_PrimalScream','Abl_PC_Magic_ChannelStrength',
 'Abl_Comp_RngMagic_Gravestrike','PSV_Comp_RngMagic_CallToTheGrave','PSV_Comp_RngMagic_RunicTeacher_1of2',
)
GRAPH_ACTIVE={'Abl_Comp_Lantry_WatchersJudgement','ABL_Comp_Beastwoman_PrimalScream',
              'Abl_PC_Magic_ChannelStrength','Abl_Comp_RngMagic_Gravestrike'}
UPGRADE_GRAPHS={'PSV_Comp_Sirin_RevivingSong','TLN_Comp_Lantry_ArcaneJudgment'}
HEALTH_REACTION='PSV_Comp_RngMagic_CallToTheGrave'

def roots(talents,stance=''):
    from ability_rules import resolve
    from talent_batch_one import family
    ranks={}
    for talent in talents:
        row=resolve(talent)
        if not row or row['key'] not in BATCH_KEYS or row.get('isTalentUpgrade'):continue
        if row.get('modal') and row['name']!=stance:continue
        if not row.get('passive') and not row.get('modal'):continue
        group=family(row['key'])
        if row['key']>ranks.get(group,{}).get('key',''):ranks[group]=row
    for row in ranks.values():
        for node in row['nodes']:
            if node['phase']=='root' and node['side']=='self':
                for effect in node['statuses']:yield row,effect

def conditional_supported(e):
    return (e['AffectsStat'] in {2026,2027,185} and e.get('TriggerAdjustment',{}).get('Type') in {6,14}
            or e['AffectsStat']==45 and e.get('TriggerAdjustment',{}).get('Type')==12
            or e['AffectsStat']==2157 and e.get('TriggerAdjustment',{}).get('Type') in {6,8}
            or e['AffectsStat']==2000 and e.get('TriggerAdjustment',{}).get('Type')==6)

def state_key(row,e):return 'talent-event:'+row['key']+':'+str(e['AffectsStat'])

def on_damage(session,target,damage):
    if damage<=0:return
    actor=getattr(session,'runtime_character',{}) if target=='player' else session.targets[target].get('character',session.targets[target])
    talents=getattr(session,'runtime_talents',[]) if target=='player' else session.targets[target].get('abilities',[])
    stance=session.active_stance if target=='player' else session.targets[target].get('combatStance','')
    states=session.conditions.setdefault(target,{})
    for row,e in roots(talents,stance):
        trigger=e.get('TriggerAdjustment',{})
        health=session.player_health if target=='player' else session.target_healths[target]
        maximum=session.player_health_max if target=='player' else session.targets[target]['healthMax']
        if trigger.get('Type')==8 and 0<health/maximum<round(trigger['TriggerValue'],6):
            states[state_key(row,e)]={'name':row['name'],'beneficial':True,'until':999999,'value':e['Value']+trigger['ValueAdjustment']}
        if trigger.get('Type')!=6:continue
        key=state_key(row,e)
        if trigger.get('RemoveEffectAtMax'):
            # Source ClearMind cooldown is four seconds: one ten-second round.
            states[key]={'name':row['name']+' — восстановление','beneficial':False,
                         'until':session.round_number+max(1,math.ceil(row['cooldownSeconds']/10))-1}
        else:stack_state(states,key,row,e,session.round_number)
    # The preservation seal is attached to the recipient, not its original caster.
    health=session.player_health if target=='player' else session.target_healths[target]
    maximum=session.player_health_max if target=='player' else session.targets[target]['healthMax']
    for key,state in list(states.items()):
        e=state.get('source',{});trigger=e.get('TriggerAdjustment',{})
        if e.get('AffectsStat')!=116 or trigger.get('Type')!=2 or state.get('until',0)<session.round_number:continue
        if 0<health/maximum<round(trigger['TriggerValue'],6):
            amount=math.ceil(maximum*trigger['ValueAdjustment']);health=min(maximum,health+amount);states.pop(key)
            session.log.append(f"{state['name']}: восстановлено {amount} ХП; печать исчезла.")
    if target=='player':session.player_health=health
    else:session.target_healths[target]=health

def stack_state(states,key,row,e,round_number):
    trigger=e['TriggerAdjustment'];old=states.get(key,{})
    stacks=min(int(trigger['MaxTriggerCount']),old.get('stacks',0)+1)
    source={**copy.deepcopy(e),'Value':e['Value']+stacks*trigger['ValueAdjustment'],
            'TriggerAdjustment':{},'runtimeEventBonus':True}
    if e['AffectsStat']==185:source['runtimeKillBonus']=True
    states[key]={'name':row['name'],'consumable':True,'beneficial':True,'source':source,
                 'until':999999,'stacks':stacks,'remainingSeconds':0}

def on_graze(session):
    states=session.conditions.setdefault('player',{})
    for row,e in roots(getattr(session,'runtime_talents',[]),session.active_stance):
        if e.get('TriggerAdjustment',{}).get('Type')==14:stack_state(states,state_key(row,e),row,e,session.round_number)

def contextual(session,derived):
    result=copy.deepcopy(derived);attack=result['attack'];rules=result.setdefault('talentRuntime',{})
    talents=getattr(session,'runtime_talents',[]);states=session.conditions.get('player',{})
    health=session.player_health/max(1,session.player_health_max)
    for row,e in roots(talents,session.active_stance):
        stat=e['AffectsStat'];trigger=e.get('TriggerAdjustment',{});kind=trigger.get('Type',0)
        if kind==12 and getattr(session,'runtime_character',{}).get('wounds',0)>0:
            if stat==45:
                for k in ('damageMin','damageMax'):attack[k]=round(attack[k]*round(e['Value']*trigger['ValueAdjustment'],6))
        if row['key']=='PSV_Comp_RngMagic_ClearMind' and states.get(state_key(row,e),{}).get('until',0)<session.round_number:
            if stat==2157:rules[2157]=max(rules.get(2157,1),e['Value'])
            if stat==2000:
                result['cooldownMultiplier']*=e['Value'];attack['recovery']=attack.get('recovery',0)*e['Value']
        if stat==2157 and kind==8 and health<round(trigger['TriggerValue'],6):
            rules[2157]=max(rules.get(2157,1),e['Value']+trigger['ValueAdjustment'])
        if row['key']=='ABL_HH_Sentinel_Last_Stand' and stat==2026 and health<.5:
            result['defenses']['Парирование']+=e['Value']
    return result

def retaliation_profiles(session,target,derived):
    from ability_rules import resolve
    from ability_graphs import branch
    talents=getattr(session,'runtime_talents',[]) if target=='player' else session.targets[target].get('abilities',[])
    stance=session.active_stance if target=='player' else session.targets[target].get('combatStance','')
    health=(session.player_health/max(1,session.player_health_max) if target=='player'
            else session.target_healths[target]/max(1,session.targets[target]['healthMax']))
    sources=[(row,e) for row,e in roots(talents,stance) if e['AffectsStat']==87]
    for state in session.conditions.get(target,{}).values():
        e=state.get('source',{})
        if e.get('AffectsStat')==87 and state.get('until',0)>=session.round_number:
            row=resolve(state.get('abilityKey') or state.get('originKey',''))
            if row:sources.append((row,e))
    for row,e in sources:
        from ability_rules import weapon_requirement
        inventory=getattr(session,'consumable_inventory',[]) if target=='player' else __import__('talent_reactions').actor_inventory(session.targets[target])
        if weapon_requirement(row,inventory):continue
        if row['key']=='ABL_HH_Sentinel_Last_Stand' and health>=.5:continue
        p=branch(row,e.get('AttackPrefabKey',''),derived)
        if p and p['supported']:yield p

def profile_prepared(row,derived):
    """Select attack/affliction edges, never merge sibling target/self effects."""
    from ability_graphs import branch
    if row.get('graphResolved') or row['key'] not in GRAPH_ACTIVE:return row
    result=branch(row,row['key'],derived)
    from ability_graphs import upgrade_launches
    result['launches'].extend(upgrade_launches(row,derived))
    if any(not p['supported'] for p in result['launches']):result['supported']=False;result['limitation']='Не подключена часть дополнительного графа.'
    # Keep original ability geometry and weapon range on its primary attack.
    for field in ('range','weaponRange','targeting','area','angle','upgrades'):result[field]=row.get(field,result.get(field))
    return result

def condition_applies(e,session,target):
    actor=getattr(session,'runtime_character',{}) if target=='player' else session.targets[target]
    for p in e.get('ApplicationPrerequisites',[]):
        if p['Type']==25 and not session.stealthed:return False
        if p['Type']==34 and session.stealthed:return False
        race=actor.get('race',actor.get('raceType',actor.get('rawStats',{}).get('CharacterRace')))
        if p['Type']==22 and race!=p.get('RaceValue'):return False
    return True

def describe(row):
    key=row['key']
    specific={
     'PSV_Comp_Beastwoman_SeizePrey':'Только атаки по возможности: +30 точности и +15 урона; обычные атаки не усиливаются.',
     'PSV_Comp_Sirin_DisarmingGuise':'Против атаки по возможности: +50 к проверяемой защите, не постоянная защита.',
     'PSV_Comp_Verse_LethalOpening':'При промахе ближней оружейной атаки: бесплатный ответный удар, 100%. Любое ближнее оружие, в том числе парное; реакции не вызывают реакции.',
     'PSV_Comp_Verse_KnowYourEnemy_01':'При получении положительного урона: +2 Парирования и Уклонения, до +40 каждого до конца боя.',
     'PSV_Comp_Verse_KnowYourEnemy_02':'При получении урона: +2 Парирования и Уклонения; при своём скользящем ударе: +2 точности. До +40 каждого, до конца боя; заменяет ранг I.',
     'PSV_Comp_Beastwoman_ScarsOfBattle':'При наличии хотя бы одной настоящей раны: +15% урона. Потерянные ХП не считаются раной.',
     'PSV_Comp_Beastwoman_DualClaw':'При живом персонаже строго ниже 70% ХП: две обычные атаки за действие. Лечение выше порога отключает бонус. Не дублирует заклинания.',
     'PSV_Comp_RngMagic_ClearMind':'Без полученного урона: две обычные атаки и восстановление ×0,8. Получение урона отключает бонусы на 1 раунд (исходные 4 секунды).',
     'Abl_Comp_Lantry_EraseTheRecord':'Печать на 3 раунда: один раз при живой цели ниже 35% ХП восстанавливает 35% её максимальных ХП и исчезает. Не воскрешает павшего.',
     'Abl_Comp_Sirin_AriaOfResolve':'На 3 раунда: +4 Стойкости, +20 Парирования и Уклонения. Уже действующие полезные эффекты продлеваются на 5 секунд до округления в раунды.',
     'Abl_Comp_Lantry_Renewal':'На 6 раундов: +1 пробивания, +50% брони экипировки; не добавляет броню без экипировки. Износ в нашей модели отсутствует.',
     'ABL_Comp_Lantry_GreaterRenewal':'На 6 раундов: +2 пробивания, +100% брони экипировки. Износ в нашей модели отсутствует.',
     'ABL_HH_Sentinel_Last_Stand':'Ниже 50% ХП: +20 Парирования и ответная колющая атака 8–12 при попадании врага в ближнем бою.',
     'ABL_Comp_Beastwoman_PrimalScream':'Конус 5 клеток, проверка Воли по Атлетике: открыто — испуг 2 раунда; из скрытности — ужас 1 раунд. Воля −30%; ужас также запрещает управляемое действие.',
     'PSV_Comp_Sirin_RevivingSong':'Ария отдыха дополнительно воскрешает павших союзников в радиусе 3 клеток с 35% максимальных ХП; дыхание списывается один раз.',
     'PSV_Comp_RngMagic_CallToTheGrave':'Один раз за бой строго ниже 35% ХП: вытягивает 16 ХП у врагов в радиусе 5 клеток и восстанавливает 16 за каждого; без основного действия.',
     'PSV_Comp_RngMagic_RunicTeacher_1of2':'Союзникам в действующем бою: +20% опыта Знаний, Волшебного посоха и всех существующих школ магии. Неиспользуемые игровые школы кислоты и призыва духов не создают новых навыков.',
    }
    if key.startswith('PSV_PC_Magic_ImbueTheElements'):return 'Оружейное попадание добавляет 25% исходного урона соответствующей стихией с её отдельной бронёй. Не усиливает созданные заклинания.'
    return specific.get(key,'')
