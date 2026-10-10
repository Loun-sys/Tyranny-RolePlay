"""Final twenty source-reviewed talents. Stateful rules are not equipment bonuses."""
import copy
import math
import random
from pathlib import PurePosixPath

BATCH_KEYS=(
 'PSV_PC_Leadership_KillingRush','Abl_Comp_RngMagic_TerratusCall','Abl_Comp_RngMagic_TerratusGate',
 'Abl_Comp_Sirin_Song_BaneOfNight','Abl_Comp_Sirin_AriaOfMemories','Abl_Comp_Sirin_AriaOfNightmares',
 'ABL_Comp_Verse_Stance_ThreeWhispers','ABL_Comp_Verse_Stance_SeekingSheath','ABL_Comp_Verse_Stance_RedGeyser',
 'PSV_Comp_Verse_ScarletVengeance','PSV_Comp_Verse_SprintingDeath','PSV_BledenMark_NoWeaponSwapCD',
 'ABL_Comp_Verse_Unbound','Abl_Comp_Defender_LegsOfIron','PSV_Comp_Defender_DefendersWatch_01',
 'PSV_Comp_Defender_DefendersWatch_02','PSV_Comp_Defender_DefendersWatch_03',
 'Abl_Comp_Defender_BloodBond','PSV_Comp_Defender_VigilantProtector','Abl_Comp_Defender_ShieldOfSuffering',
)
GRAPH_ACTIVE={'Abl_Comp_RngMagic_TerratusCall'}
SPECIAL_ACTIVE={'Abl_Comp_RngMagic_TerratusGate','ABL_Comp_Verse_Unbound',
                'Abl_Comp_Sirin_AriaOfMemories','Abl_Comp_Sirin_AriaOfNightmares'}
STANCE_STATS={2059,2060,2071,150,18}
SUPPORTED={178,2059,2060,2071,2073,2074,2075,2076,2058,215}

def rows(talents):
    from ability_rules import resolve
    from talent_batch_one import family
    ranks={}
    for t in talents:
        r=resolve(t)
        if r and r['key'] in BATCH_KEYS:
            f=family(r['key'])
            if r['key']>ranks.get(f,{}).get('key',''):ranks[f]=r
    return list(ranks.values())

def stance_statuses(stance):
    from ability_rules import resolve
    row=resolve(stance)
    return [e for n in row['nodes'] if n['phase']=='root' and n['side']=='self' for e in n['statuses']] if row and row['key'] in BATCH_KEYS and row.get('modal') else []

def stance_upgrades(stance):
    from ability_rules import resolve
    return [row for e in stance_statuses(stance) if e['AffectsStat']==2059
            and (row:=resolve(PurePosixPath(e.get('ExtraObject','')).stem))]

def immobile(session,target='player'):
    stance=session.active_stance if target=='player' else session.targets[target].get('combatStance','')
    return any(e['AffectsStat']==18 for e in stance_statuses(stance))

def push_immune(session,target):
    stance=session.active_stance if target=='player' else session.targets[target].get('combatStance','')
    return any(e['AffectsStat']==2071 for e in stance_statuses(stance))

def condition_immune(session,target,effect):
    stance=session.active_stance if target=='player' else session.targets[target].get('combatStance','')
    affliction=effect.get('affliction') or ('Aff_Prone' if effect.get('control')=='prone' else '')
    return bool(affliction) and any(e['AffectsStat']==150 and e.get('AfflictionPrefabKey')==affliction for e in stance_statuses(stance))

def watch(session):
    """Position-scoped continuous aura; strongest rank/caster replaces, not stacks."""
    actors={'player':{'talents':getattr(session,'runtime_talents',[]),'team':'ally','health':session.player_health,'position':session.player_position}}
    actors.update({k:{'talents':t.get('abilities',[]),'team':t.get('team','enemy'),'health':session.target_healths[k],'position':session.target_positions[k]}
                   for k,t in session.targets.items()})
    for key,target in actors.items():
        states=session.conditions.get(key,{})
        states.pop('defenders-watch',None)
        values=[]
        for caster in actors.values():
            if caster['health']<=0 or caster['team']!=target['team']:continue
            for row in rows(caster['talents']):
                if 'DefendersWatch' not in row['key']:continue
                node=next(n for n in row['nodes'] if n.get('attack'))
                if session.grid.distance(caster['position'],target['position'])<=node['attack']['BlastRadius'] and session.grid.line_of_sight(caster['position'],target['position']):
                    values.extend(e['Value'] for e in node['statuses'] if e['AffectsStat']==188)
        if values:session.conditions.setdefault(key,{})['defenders-watch']={'name':'Дозор защитника','source':{'AffectsStat':188,'Value':min(values)},'beneficial':True,'until':999999}
    memory_pressure(session)

def memory_pressure(session):
    """Adapt native memory's three engagements to explicit target pressure, not AI."""
    positions={'player':session.player_position,**session.target_positions}
    teams={'player':'ally',**{k:t.get('team','enemy') for k,t in session.targets.items()}}
    health={'player':session.player_health,**session.target_healths}
    limits={'player':getattr(session,'runtime_character',{}).get('memoryEngagementLimit',0),**{k:t.get('memoryEngagementLimit',0) for k,t in session.targets.items()}}
    for states in session.conditions.values():states.pop('memory-taunt',None)
    for source,limit in limits.items():
        if not limit or health[source]<=0:continue
        victims=[k for k in positions if k!=source and teams[k]!=teams[source] and health[k]>0
                 and session.grid.distance(positions[k],positions[source])<=1 and session.grid.line_of_sight(positions[k],positions[source])]
        for key in sorted(victims)[:limit]:
            session.conditions.setdefault(key,{})['memory-taunt']={'name':'Воплощение воспоминаний — провокация','kind':'taunt','sourceId':source,'beneficial':False,'until':session.round_number}

def on_damage(session,target,damage):
    if damage<=0:return
    stance=session.active_stance if target=='player' else session.targets[target].get('combatStance','')
    multiplier=next((e['Value'] for e in stance_statuses(stance) if e['AffectsStat']==2060),0)
    if multiplier:
        states=session.conditions.setdefault(target,{})
        old=states.get('saved-damage',{})
        states['saved-damage']={'name':'Алый Гейзер — накопленный урон','value':old.get('value',0)+damage*multiplier,'beneficial':True,'until':999999}

def saved_damage(session,landed=True):
    states=session.conditions.get('player',{})
    if not any(e['AffectsStat']==2060 for e in stance_statuses(session.active_stance)):
        states.pop('saved-damage',None);return 0
    return states.pop('saved-damage',{}).get('value',0) if landed else states.get('saved-damage',{}).get('value',0)

def share_damage(session,target,damage):
    """Split post-mitigation damage once, never recursively share or reapply armor."""
    for state in session.conditions.get(target,{}).values():
        partner=state.get('bondPartner')
        if not partner or state.get('until',0)<session.round_number:continue
        alive=session.player_health if partner=='player' else session.target_healths.get(partner,0)
        if alive<=0:continue
        amount=math.floor(damage*state['value'])
        if not amount:return damage
        # The partner's shields can intercept transferred damage; armor is not doubled.
        from consumables import receive_damage
        received=receive_damage(session.conditions.setdefault(partner,{}),amount)
        before=alive
        if partner=='player':session.player_health=max(0,alive-received)
        else:session.target_healths[partner]=max(0,alive-received)
        on_damage(session,partner,received)
        from talent_batch_two import on_damage as event_damage
        event_damage(session,partner,received)
        session.events.append({'sourceId':target,'targetId':partner,'result':'Узы чести','damage':received})
        on_death(session,partner,before)
        return damage-amount
    return damage

def bind(session,target,value,duration):
    # Recasting replaces the old pair without leaving a reverse link behind.
    for key,states in session.conditions.items():
        if key=='player' or states.get('blood-bond',{}).get('bondPartner')=='player':states.pop('blood-bond',None)
    until=session.round_number+math.ceil(duration/10)-1
    for key,partner in [('player',target),(target,'player')]:
        session.conditions.setdefault(key,{})['blood-bond']={'name':'Узы чести','bondPartner':partner,'value':value,'beneficial':True,'until':until}

def heal_and_shield(session,rule,targets):
    effect=next(e for e in rule['effects'] if e.get('AffectsStat')==2073)
    amount=0
    for target in targets:
        maximum=session.player_health_max if target=='player' else session.targets[target]['healthMax']
        health=session.player_health if target=='player' else session.target_healths[target]
        healing=min(maximum-health,math.ceil(maximum*round(effect['Value'],6))) if health>0 else 0
        if target=='player':session.player_health+=healing
        else:session.target_healths[target]+=healing
        amount+=healing
        session.events.append({'sourceId':'player','targetId':target,'result':'Щит страданий — лечение','damage':-healing})
    session.conditions.setdefault('player',{})['shield-of-suffering']={'name':'Щит страданий','shieldRemaining':amount*effect['ExtraValue'],
                'beneficial':True,'until':session.round_number+math.ceil(effect['Duration']/10)-1}
    session.log.append(f"Щит страданий: восстановлено {amount} ХП отряду; поглощение {amount*effect['ExtraValue']:g} урона у заклинателя.")

def party_kill(session):
    team=[('player',getattr(session,'runtime_talents',[]),session.player_health),
          *((k,t.get('abilities',[]),session.target_healths[k]) for k,t in session.targets.items() if t.get('team','enemy')=='ally')]
    sources=[r for _,talents,h in team if h>0 for r in rows(talents) if r['key']=='PSV_PC_Leadership_KillingRush']
    for row in sources:
        effect=next(e for n in row['nodes'] for e in n['statuses'] if e['AffectsStat']==116)
        for key,_,h in team:
            if h<=0:continue
            maximum=session.player_health_max if key=='player' else session.targets[key]['healthMax']
            healing=math.ceil(maximum*round(effect['Value'],6))
            if key=='player':session.player_health=min(maximum,h+healing)
            else:session.target_healths[key]=min(maximum,session.target_healths[key]+healing)
        session.log.append('Смертоносный натиск: живые союзники восстанавливают 5% максимального здоровья.')

def on_death(session,target,before):
    health=session.player_health if target=='player' else session.target_healths.get(target,0)
    if before<=0 or health>0:return
    talents=getattr(session,'runtime_talents',[]) if target=='player' else session.targets[target].get('abilities',[])
    source=next((r for r in rows(talents) if r['key']=='PSV_Comp_Verse_ScarletVengeance'),None)
    states=session.conditions.setdefault(target,{})
    if not source or 'scarlet-death-used' in states:return
    states['scarlet-death-used']={'name':'Алое возмездие сработало','beneficial':True,'until':999999}
    from ability_graphs import branch
    derived=getattr(session,'runtime_derived',{}) if target=='player' else session.targets[target].get('combatDerived',{})
    graph=branch(source,source['key'],derived);graph['launchOrigin']='caster'
    if target=='player':session._resolve_graph_attack(graph,session.selected_target_id)
    elif session.player_health>0:
        from talent_reactions import free_attack
        free_attack(session,target,'player',source['name'],ability=graph,allow_dead_source=True)

def expire_summons(session):
    for key,t in list(session.targets.items()):
        if t.get('summonedBy') and (t['expiresRound']<=session.round_number or session.target_healths.get(key,0)<=0):
            session.targets.pop(key);session.target_positions.pop(key,None);session.target_healths.pop(key,None);session.conditions.pop(key,None)
            session.initiative=[i for i in session.initiative if i['id']!=key]
            session.log.append('Призыв «'+t['name']+'» исчезает.')

def summon_node(rule):return next((n['attack'] for n in rule['nodes'] if n.get('attack',{}).get('SummonFileList')),None)

def free_cell(session,near,include_center=True):
    cells=[(x,y) for x in range(near[0]-1,near[0]+2) for y in range(near[1]-1,near[1]+2)
           if (include_center or (x,y)!=near) and session.grid.inside((x,y)) and (x,y) not in session.grid.blocked and (x,y) not in session._occupied()
           and session.grid.line_of_sight(near,(x,y))]
    if not cells:raise ValueError('Рядом нет свободной клетки для призыва/перемещения.')
    return min(cells,key=lambda p:(session.grid.distance(near,p),p[1],p[0]))

def spawn(session,rule,point):
    from npc_store import templates
    node=summon_node(rule)
    prefab=PurePosixPath(random.choice(node['SummonFileList'])).stem
    original=next((r for r in templates() if r['source']['prefab']==prefab),None)
    if original is None:raise ValueError('Игровой шаблон призыва не найден.')
    if node.get('DestroyExistingSummons'):
        for k,t in session.targets.items():
            if t.get('summonedBy')=='player':t['expiresRound']=session.round_number
        expire_summons(session)
    key='summon_'+__import__('uuid').uuid4().hex[:12]
    token={**copy.deepcopy(original),'id':key,'kind':'npc','team':'ally','summonedBy':'player',
           'expiresRound':session.round_number+max(1,math.ceil(node['SummonedLifetime']/10)),
           'sourceAbilityKey':rule['key'],'health':original['healthMax'],'x':point[0],'y':point[1]}
    # The native nightmare applies its fear attack on a weapon hit (2119).
    if prefab=='CRE_Sirin_EmbodiedMemory_Nightmare':token['nightmareHitFear']=True
    if prefab=='CRE_Sirin_EmbodiedMemory_Memory':token['memoryEngagementLimit']=3
    session.targets[key]=token;session.target_positions[key]=point;session.target_healths[key]=token['healthMax']
    session.initiative.append({'id':key,'name':token['name'],'roll':0,'bonus':0,'total':0})
    session.log.append(f"Призван «{token['name']}» на {max(1,math.ceil(node['SummonedLifetime']/10))} раундов; ходом управляет мастер.")
    return key

def execute_special(session,rule,derived):
    """Return None for the ordinary pipeline, otherwise an executed result."""
    k=rule.get('sourceAbilityKey',rule['key'])
    if k not in SPECIAL_ACTIVE and k!='Abl_Comp_Verse_Rush':return None
    from ability_rules import resolve
    from ability_graphs import branch
    source=resolve(k)
    target=session.selected_target_id
    origin=session.player_position
    if k=='Abl_Comp_Verse_Rush':
        destination=session.aim_point
        reachable=session.grid.reachable(origin,rule['range'],session._occupied('player'))
        if destination not in reachable or destination==origin:raise ValueError('Для рывка выберите достижимую свободную клетку.')
        if immobile(session):raise ValueError('Железные ноги запрещают рывок.')
        path=session.grid.path(origin,destination,session._occupied('player'))
        sprinting_death(session,path)
        session.player_position=destination;session.movement_path=path
        session.disengaged=True
    elif k=='Abl_Comp_RngMagic_TerratusGate':
        destination=session.aim_point
        if destination is None or not session.grid.inside(destination) or destination in session.grid.blocked or destination in session._occupied():
            raise ValueError('Для врат выберите свободную проходимую клетку.')
        graph=branch(source,k+'_AOE',derived)
        for point in [origin,destination]:
            graph['launchCenter']=list(point);session._resolve_graph_attack(graph,target)
        session.player_position=destination;session.movement_path=[origin,destination]
    elif k=='ABL_Comp_Verse_Unbound':
        if target not in session.targets or session.target_healths[target]<=0 or session.targets[target].get('team','enemy')!='enemy':raise ValueError('Выберите живого противника.')
        destination=free_cell(session,session.target_positions[target],False)
        graph=branch(source,k+'_FollowUp_AttackAOE',derived);graph['launchCenter']=list(origin)
        session._resolve_graph_attack(graph,target)
        session.player_position=destination;session.movement_path=[origin,destination]
        spawn(session,{**source,'nodes':rule['nodes']},origin)
    else:
        point=free_cell(session,origin,False)
        spawn(session,source,point)
    session.cooldowns['ability:'+rule['key']]=999999 if rule['oncePerBattle'] else session.round_number+rule['cooldown']+1
    session.breath-=rule.get('breathCost',0)
    return {'result':'Способность применена','damage':0,'line':session.log[-1] if session.log else rule['name']}

def sprinting_death(session,path):
    from ability_rules import resolve
    if not any(r['key']=='PSV_Comp_Verse_SprintingDeath' for r in rows(getattr(session,'runtime_talents',[]))):return
    from item_effects import active_equipment,game_data
    torso=next((i for i in active_equipment(getattr(session,'consumable_inventory',[]),session.active_weapon_set) if i.get('equipped_slot')=='Торс'),{})
    data=game_data(torso)
    if any(game_data(i).get('armor',{}).get('ArmorCategory')==1 for i in active_equipment(getattr(session,'consumable_inventory',[]),session.active_weapon_set)):return
    row=resolve('PSV_Comp_Verse_SprintingDeath')
    from ability_graphs import branch
    graph=branch(row,'PSV_Comp_Verse_SprintingDeath_AOE',getattr(session,'runtime_derived',{}))
    seen=set();origin=session.player_position
    try:
        for point in path:
            session.player_position=point
            for target in session._alive_targets():
                if target in seen or session.grid.distance(point,session.target_positions[target])>graph['area'] or not session.grid.line_of_sight(point,session.target_positions[target]):continue
                seen.add(target)
                single={**graph,'area':0,'launchCenter':list(point)}
                session._resolve_graph_attack(single,target)
    finally:session.player_position=origin

def describe(row):
    k=row['key']
    if 'DefendersWatch' in k:
        value=next(e['Value'] for n in row['nodes'] for e in n['statuses'] if e['AffectsStat']==188)
        return f'Живой персонаж и союзники в радиусе 3 клеток получают на {(1-value)*100:.0f}% меньше урона. При выходе из области бонус пропадает. Старший ранг и пересекающиеся ауры не складываются.'
    return {
      'PSV_PC_Leadership_KillingRush':'Убийство врага любым союзником восстанавливает живым бойцам отряда 5% максимальных ХП. Не воскрешает павших.',
      'Abl_Comp_RngMagic_TerratusCall':'Проверка Выносливости по могильному свету; только при успехе — 18–26 дробящего урона последующим ударом. Дальность 8 клеток.',
      'Abl_Comp_RngMagic_TerratusGate':'Перенос в свободную клетку до 8 клеток; у входа и выхода область 2,5 клетки, проверка Магии по могильному свету. Вытягивает 24 ХП и лечит на 40% вытянутого здоровья.',
      'Abl_Comp_Sirin_AriaOfMemories':'8 дыхания: воплощение воспоминаний на 6 раундов с игровыми характеристиками. Удерживает до 3 соседних врагов; управляется мастером в инициативе. Новый призыв заменяет предыдущий.',
      'Abl_Comp_Sirin_AriaOfNightmares':'8 дыхания: воплощение кошмаров на 6 раундов с игровыми характеристиками. Оружейное попадание проверяет Волю и накладывает ужас на 4 секунды (1 раунд). Управляет мастер; новый призыв заменяет предыдущий.',
      'ABL_Comp_Verse_Stance_ThreeWhispers':'Уклонение +20; Вне оков получает +4 дальности, Насмешка понижает Парирование цели на 20 на 2 раунда. Улучшения работают только в этой стойке.',
      'ABL_Comp_Verse_Stance_SeekingSheath':'Точность +10; Шампур, Могильщик и Свинья на вертеле получают ещё +10 точности. Только при активной стойке и парном оружии/луке.',
      'ABL_Comp_Verse_Stance_RedGeyser':'Парирование и Уклонение −10. Накапливает 50% действительно полученного урона и добавляет его к следующему успешному попаданию; промах не расходует накопление.',
      'PSV_Comp_Verse_ScarletVengeance':'При переходе от положительных ХП к нулю один раз наносит ближайшим врагам 18–26 рубящего урона, радиус 2,5 клетки, проверка Парирования. Срабатывает и у НПС, без действия.',
      'PSV_Comp_Verse_SprintingDeath':'Рывок Фурии перемещает до 7 клеток (базовое движение ×1,5) за действие без атаки по возможности. В лёгкой броне/без брони наносит по пути 50% оружейного урона, радиус 2,5; не повторяет удар по одному токену внутри пути.',
      'PSV_BledenMark_NoWeaponSwapCD':'Восстановление смены оружия −20 секунд, до нуля. Бонус точности не добавляется: в игровом компоненте его нет.',
      'ABL_Comp_Verse_Unbound':'Атака соседних врагов 100% оружейного урона, радиус 1,5 клетки; перенос в свободную клетку рядом с выбранным врагом до 8 клеток и фантом Фурии на старом месте на 1 раунд.',
      'Abl_Comp_Defender_LegsOfIron':'Выносливость +40%; иммунитет к отталкиванию и сбиванию с ног. Передвижение и спринт недоступны, пока стойка включена.',
      'Abl_Comp_Defender_BloodBond':'На 6 раундов обоим +2 Силы и Живучести. Половина входящего урона передаётся живому связанному союзнику; связь не передаёт урон по кругу. Повторное применение заменяет пару.',
      'PSV_Comp_Defender_VigilantProtector':'Узы чести дополнительно дают обоим щит на 50 урона на 6 раундов. Щиты не складываются от повторного применения.',
      'Abl_Comp_Defender_ShieldOfSuffering':'Союзникам в радиусе 10 клеток восстанавливает до 35% максимальных ХП. Заклинателю — щит на суммарное действительно восстановленное здоровье, на 15 секунд (2 раунда). При полном здоровье щит не создаётся.',
    }.get(k,'')
