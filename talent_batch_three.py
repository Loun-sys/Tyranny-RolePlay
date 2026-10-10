"""Third source-reviewed group; timed graphs and party rules retain their scope."""
import copy
import math

BATCH_KEYS=(
 'Abl_PC_Defense_StanceShieldbanger','PSV_PC_Defense_BloodBringsVictory',
 'PSV_PC_Leadership_Bandolier_2of2','Abl_PC_Leadership_RefusePain',
 'PSV_PC_Leadership_AbundantArms_1of2','PSV_PC_Leadership_AbundantArms_2of2',
 'Abl_PC_Leadership_Undying','Abl_PC_Ranged_Escape','PSV_PC_Ranged_Ricochet',
 'PSV_PC_Magic_CounterSpell','TLN_Comp_Lantry_SwiftQuill','PSV_Comp_Lantry_BouncingBlades',
 'PSV_Comp_Lantry_Accelerate','Abl_Comp_Lantry_PassageOfHours','Abl_Comp_Lantry_TheftOfMoments',
 'PSV_Comp_RngMagic_CascadingEmbrace','Abl_Comp_RngMagic_BreathOfMother',
 'PSV_Comp_RngMagic_EmpoweredElements','PSV_Comp_RngMagic_MoonlitWay_1of3',
 'Abl_Comp_RngMagic_TerratusGrip','PSV_Comp_RngMagic_MoonlitWay_2of3','PSV_Comp_RngMagic_MoonlitWay_3of3',
 'PSV_Comp_Beastwoman_Relentless_1of2','PSV_Comp_Sirin_SustainedBreath_1of2',
 'PSV_Comp_Sirin_SustainedBreath_2of2','PSV_Comp_Sirin_ResonantField_1of3',
 'PSV_Comp_Sirin_ResonantField_2of3','PSV_Comp_Sirin_ResonantField_3of3',
 'PSV_Comp_Verse_BornOfBloodAndFire','PSV_Comp_Verse_MobileRecovery',
)
GRAPH_ACTIVE={'Abl_Comp_RngMagic_BreathOfMother','Abl_Comp_Lantry_TheftOfMoments',
              'Abl_PC_Leadership_RefusePain','Abl_PC_Leadership_Undying'}
UPGRADE_GRAPHS={'PSV_Comp_RngMagic_CascadingEmbrace'}
SUPPORTED={17,172,2004,2015,2042,2078,2083,2085,2097,2100,2115,2117,2142,215,2158,2162,2171,223,150,204}

def rows(talents):
    from ability_rules import resolve
    from talent_batch_one import family
    ranks={}
    for t in talents:
        row=resolve(t)
        if row and row['key'] in BATCH_KEYS:
            group=family(row['key'])
            if row['key']>ranks.get(group,{}).get('key',''):ranks[group]=row
    return list(ranks.values())

def roots(talents):
    for row in rows(talents):
        if not row['passive'] or row.get('isTalentUpgrade'):continue
        for node in row['nodes']:
            if node['phase']=='root' and node['side']=='self':
                for e in node['statuses']:yield row,e

def conditional_supported(e):
    return (e['AffectsStat'] in {107,2000} and e.get('TriggerAdjustment',{}).get('Type')==12
            or e['AffectsStat']==2085 and e.get('TriggerAdjustment',{}).get('Type')==6)

def party_equipment(talents):
    statuses=[]
    for row in rows(talents):
        if row['key'] not in {'PSV_PC_Leadership_Bandolier_2of2','PSV_PC_Leadership_AbundantArms_1of2','PSV_PC_Leadership_AbundantArms_2of2'}:continue
        statuses.extend(copy.deepcopy(e) for n in row['nodes'] for e in n['statuses'] if e['AffectsStat'] in {204,215})
    return [{'name':'Отрядные таланты','category':'Эффекты','equipped_slot':'Эффект','armor':0,
             'properties':{'gameData':{'statusEffects':statuses}}}] if statuses else []

def contextual(session,derived):
    for row,e in roots(getattr(session,'runtime_talents',[])):
        if e.get('TriggerAdjustment',{}).get('Type')==12 and getattr(session,'runtime_character',{}).get('wounds',0)>0:
            value=round(e['TriggerAdjustment']['ValueAdjustment'],6)
            if e['AffectsStat']==2000:
                derived['cooldownMultiplier']*=value
                derived['attack']['recovery']=derived['attack'].get('recovery',0)*value
            if e['AffectsStat']==107:derived['attack']['criticalChance']=derived['attack'].get('criticalChance',0)+value*100
    for state in session.conditions.get('player',{}).values():
        e=state.get('source',{})
        if e.get('AffectsStat')==2015 and state.get('until',0)>=session.round_number:
            speed=max(.1,1+e['Value']/100)
            derived['cooldownMultiplier']/=speed
            derived['attack']['recovery']=derived['attack'].get('recovery',0)/speed
    return derived

def immune(talents,affliction):
    return bool(affliction) and any(e.get('AfflictionPrefabKey')==affliction for _,e in roots(talents) if e['AffectsStat']==150)

def effective_consumable(item,multiplier):
    from consumables import MULTIPLIERS
    result=copy.deepcopy(item)
    from item_effects import game_data
    data=game_data(result)
    # Native CalculateDuration scales potions/food (Ingestible.Type 0/4).
    # ApplyEffectHelper explicitly excludes periodic value from strength scaling.
    timed=data.get('sourceItem',{}).get('Type') in {0,4}
    for component in data.get('useComponents',[]):
        for e in component.get('StatusEffects',[]):
            if timed and e.get('Duration',0)>.11:e['Duration']*=multiplier
            if e.get('IntervalRate'):continue
            if e['AffectsStat'] in MULTIPLIERS:e['Value']=1+(e['Value']-1)*multiplier
            elif e['AffectsStat'] not in {18,19,75,150,151,176,184,2004,2077,2097,2156} and e.get('Value'):e['Value']*=multiplier
    return result

def shield(session,target,hit=False):
    talents=getattr(session,'runtime_talents',[]) if target=='player' else session.targets[target].get('abilities',[])
    source=next(((r,e) for r,e in roots(talents) if e['AffectsStat']==2085),None)
    if not source:return
    row,e=source;states=session.conditions.setdefault(target,{})
    marker=states.get('resonance-delay',{})
    if 'resonance-shield' not in states and marker.get('readyRound',0)<=session.round_number:
        states['resonance-shield']={'name':row['name'],'shieldRemaining':e['Value'],'beneficial':True,'until':999999}
    if hit:
        # Any real damage attempt, including one absorbed in full, delays recovery.
        states['resonance-delay']={'name':'Восстановление резонансного поля','beneficial':True,'until':999999,
                                   'readyRound':session.round_number+1+max(1,math.ceil(row['cooldownSeconds']/10))}

def after_shield_hit(session,target):
    if 'resonance-delay' in session.conditions.get(target,{}):session.conditions[target].pop('resonance-shield',None)

def blood_retaliation(session,target,result):
    if result!='Критическое попадание':return
    talents=getattr(session,'runtime_talents',[]) if target=='player' else session.targets[target].get('abilities',[])
    row=next((r for r in rows(talents) if r['key']=='PSV_PC_Defense_BloodBringsVictory'),None)
    stance=session.active_stance if target=='player' else session.targets[target].get('combatStance','')
    from ability_rules import resolve
    active=resolve(stance)
    if not row or not active:return
    suffix='ShieldbangerAttack' if active['key']=='Abl_PC_Defense_StanceShieldbanger' else 'GuardAttack' if active['key']=='Abl_PC_Defense_StanceGuarded' else ''
    if not suffix:return
    from ability_graphs import branch
    from talent_reactions import free_attack
    derived=getattr(session,'runtime_derived',{}) if target=='player' else session.targets[target].get('combatDerived',{})
    graph=branch(row,row['key']+'_'+suffix,derived)
    graph.update(launchOrigin='caster',freeReaction=True,weaponMask=0)
    victim=next(iter(session._alive_targets()),None) if target=='player' else 'player'
    if victim:
        if target=='player':
            graph['launchCenter']=list(session.player_position)
            session._resolve_graph_attack(graph,victim)
        else:free_attack(session,target,victim,row['name'],ability=graph)

def ricochet(session,target,result,attack):
    if result not in {'Промах','Скользящий удар'}:return
    from ability_rules import weapon_requirement
    from talent_runtime import weapon_mode
    if weapon_mode(attack)=='melee' or getattr(session,'resolving_ricochet',False):return
    eligible=[r for r in rows(getattr(session,'runtime_talents',[])) if r['key'] in {'PSV_PC_Ranged_Ricochet','PSV_Comp_Lantry_BouncingBlades'}
              and not weapon_requirement(r,getattr(session,'consumable_inventory',[]),session.active_weapon_set)]
    if not eligible:return
    # Source straight bounces use dot >= .7071, range 5 and multiplier .5.
    start=session.player_position;anchor=session.target_positions[target];dx,dy=anchor[0]-start[0],anchor[1]-start[1]
    length=math.hypot(dx,dy);candidates=[]
    if not length:return
    for key in session._alive_targets():
        if key==target:continue
        p=session.target_positions[key];x,y=p[0]-anchor[0],p[1]-anchor[1];distance=math.hypot(x,y)
        if distance and distance<=5 and (dx*x+dy*y)/(length*distance)>=.7071 and session.grid.line_of_sight(anchor,p):candidates.append(key)
    if not candidates:return
    victim=min(candidates,key=lambda k:session.grid.distance(anchor,session.target_positions[k]))
    session.resolving_ricochet=True
    try:
        h=session._roll_attack(name='Рикошет',accuracy=attack.get('accuracy',0),low=round(attack.get('damageMin',1)*.5),
            high=round(attack.get('damageMax',2)*.5),defense=session._defense('Уклонение',victim),defense_name='Уклонение',
            armor=session.targets[victim].get('armor',0),penetration=round(attack.get('penetration',0)),target_id=victim,
            attack_mode='ranged',allow_reactions=False)
        session._weapon_talent_procs(victim,h['result'])
    finally:session.resolving_ricochet=False

def queue_launch(session,row,effect,target):
    from ability_graphs import branch
    child=branch(row,effect.get('AttackPrefabKey',''),getattr(session,'runtime_derived',{}))
    if not child or not child.get('supported'):return
    seconds=round(effect.get('Duration',0),4)
    launch={'graph':child,'remaining':seconds,'delay':seconds if effect.get('Apply')==2 else 0,
            'interval':1 if effect.get('IntervalRate') else 0,'targetId':target,'center':list(session.player_position if target=='player' else session.target_positions[target]),
            'aura':target=='player','originKey':row['key'],'onOriginEnd':effect.get('Apply')==2}
    pending=getattr(session,'pending_graphs',[])
    pending[:]=[p for p in pending if not(p['originKey']==row['key'] and p['targetId']==target)]
    pending.append(launch);session.pending_graphs=pending

def advance_graphs(session,seconds=10):
    pending=getattr(session,'pending_graphs',[]);keep=[]
    for p in pending:
        p['remaining']=round(p['remaining']-seconds,4);p['delay']=round(p['delay']-seconds,4)
        if p.get('onOriginEnd') and p['delay']>0:
            origin=session.conditions.get(p['targetId'],{})
            if not any(key.startswith('consumable:'+p['originKey']+':') or state.get('abilityKey')==p['originKey'] for key,state in origin.items()):
                p['remaining']=p['delay']=0
        fire=(p['interval'] and (p['remaining']>0 or p['interval']<10)) or (not p['interval'] and p['delay']<=0)
        if fire:
            graph=copy.deepcopy(p['graph']);graph['launchCenter']=list(session.player_position) if p['aura'] else list(session.target_positions.get(p['targetId'],p['center'])) if p.get('onOriginEnd') else p['center']
            repeats=max(1,min(seconds,seconds+int(p['remaining'])))/p['interval'] if p['interval'] else 1
            for _ in range(int(repeats)):session._resolve_graph_attack(graph,p['targetId'])
        if p['remaining']>0:keep.append(p)
    session.pending_graphs=keep
    from ability_rules import resolve
    active=resolve(session.active_stance)
    if active and active['key']=='Abl_PC_Defense_StanceShieldbanger' and session.player_health>0:
        from ability_graphs import branch
        graph=branch(active,'Abl_PC_Defense_StanceShieldbanger_AOE',getattr(session,'runtime_derived',{}))
        graph['launchCenter']=list(session.player_position)
        session._resolve_graph_attack(graph,session.selected_target_id)

def describe(row):
    k=row['key']
    if 'ResonantField' in k:
        value=next(e['Value'] for n in row['nodes'] for e in n['statuses'] if e['AffectsStat']==2085)
        return f'Поглощает {value:g} урона. Любое попадание приостанавливает восстановление; поле возвращается после полного раунда без попаданий. Старший ранг заменяет младший.'
    if 'MoonlitWay' in k:
        statuses=[e for n in row['nodes'] if n['phase']=='root' for e in n['statuses']]
        bonus=next(e['Value'] for e in statuses if e['AffectsStat']==2039)
        multiplier=next(e['Value'] for e in statuses if e['AffectsStat']==2115)
        return f'Навык могильного света +{bonus:g}; его урон ночью ×{multiplier:.1f}. Ночь задаётся мастером для боя, не определяется часами сервера. Старший ранг заменяет младший.'
    if 'SustainedBreath' in k:
        e=next(e for n in row['nodes'] for e in n['statuses'] if e['AffectsStat']==2100)
        return f"После завершения настоящего боя сохраняет не более {e['Value']:g} дыхания на {e['ExtraValue']:g} секунд. Новая тренировка не изменяет сохранённый запас. Старший ранг заменяет младший."
    return {
      'PSV_Comp_Verse_MobileRecovery':'Передвижение ×1,25 (6 клеток вместо 5). Движение не накладывает отдельного штрафа восстановления в нашей пошаговой модели.',
      'PSV_Comp_Beastwoman_Relentless_1of2':'При настоящей ране: восстановление ×0,85 и +10 процентных пунктов преобразования попадания в крит; потерянные ХП не считаются раной.',
      'TLN_Comp_Lantry_SwiftQuill':'Три способности пера: перезарядка ×0,75; восстановление −2 секунды до перевода в десятисекундные раунды.',
      'PSV_Comp_Lantry_Accelerate':'Крит метательным оружием: восстановление ×0,85 на 2 раунда. Не срабатывает от заклинания.',
      'PSV_PC_Ranged_Ricochet':'Промах или задевание дистанционным оружием: один отскок за цель, конус ±45°, до 5 клеток, 50% базового урона. Союзники и цели за стеной исключены.',
      'PSV_Comp_Lantry_BouncingBlades':'Промах или задевание метательным оружием: один прямой отскок за цель до 5 клеток с 50% урона. Не складывается с тем же отскоком Рикошета.',
      'PSV_Comp_Verse_BornOfBloodAndFire':'Не позволяет наложить Кровотечение, Горение и Волшебный огонь. Не защищает от прямого огненного урона.',
      'PSV_Comp_RngMagic_EmpoweredElements':'Радиус областей способностей и созданных заклинаний ×1,2; единичные цели не превращаются в область.',
      'PSV_PC_Leadership_Bandolier_2of2':'Отряду +2 быстрые ячейки и +50% силы разовых эффектов расходников. Длительность зелий и еды ×1,5; величина периодического эффекта не усиливается. Старший ранг заменяет младший.',
      'PSV_PC_Leadership_AbundantArms_1of2':'Отряду +1 комплект оружия; восстановление смены комплекта −0,25 секунды.',
      'PSV_PC_Leadership_AbundantArms_2of2':'Отряду +2 комплекта оружия; восстановление смены −0,5 секунды. Не складывается с рангом I.',
      'Abl_Comp_Lantry_PassageOfHours':'На 2 раунда: движение ×0,25; скорость действий −75% адаптирована как восстановление ×4, не отменяет сам ход.',
      'Abl_Comp_RngMagic_TerratusGrip':'На 2 раунда цель удерживается в воздухе: не двигается и не действует, не сбивается и не оглушается; оружейное попадание возможно только с дистанции.',
      'Abl_PC_Defense_StanceShieldbanger':'В конце своего раунда провоцирует врагов в радиусе 3 клеток на 1 раунд. Провокация ограничивает выбор цели, но не заставляет мастера атаковать автоматически.',
      'PSV_PC_Defense_BloodBringsVictory':'После критического попадания по персонажу: в Претенденте соседние враги получают +20% входящего урона; в Стражнике союзники получают +4 брони. Радиус 3, длительность 2 раунда.',
      'Abl_PC_Leadership_RefusePain':'Аура 5 клеток на 12 секунд: каждую секунду снимает по одному вредному эффекту с себя и союзников. Тики суммируются внутри раунда, а не превращаются в постоянный иммунитет.',
      'Abl_PC_Leadership_Undying':'Знамя в выбранной клетке: союзникам в радиусе 5 на 3 раунда +50% урона и восстановление 10% максимальных ХП за секунду. Положение знамени фиксировано.',
      'Abl_Comp_Lantry_TheftOfMoments':'На 12 секунд исчезает, недоступен для выбора и поглощает до 999 урона, восстанавливая 10% максимальных ХП за секунду. По окончании: ближайшим союзникам обнуляет восстановление на 12 секунд.',
      'PSV_Comp_RngMagic_CascadingEmbrace':'После окончания Объятий матери: область 5 клеток вокруг удержанной цели накладывает Захлебывание на 3 раунда (6 урона в секунду, немота).',
      'Abl_Comp_RngMagic_BreathOfMother':'Туман в выбранной области на 3 раунда: врагам −10 точности и обнаружение ×0,8; союзникам +25 Хитроумия. Эффекты обновляются, пока токен в тумане.',
      'Abl_PC_Ranged_Escape':'Выпад дополнительно обездвиживает цель на 1 раунд; самому персонажу движение ×1,5 и выход из зоны контроля на 1 раунд.',
      'PSV_PC_Magic_CounterSpell':'Энергетический щит на 6 раундов получает 50% отражения враждебных созданных заклинаний. Не отражает обычный удар посоха.',
    }.get(k,'')
