"""Consumable rules read from original ability components, 10 seconds = 1 round."""
import copy
import math
from item_effects import game_data,STATS,SKILLS,DAMAGE_TYPES,equip_modifiers
from localization import seconds_to_rounds

LABELS={7:'Защита Выносливостью',8:'Защита Магией',9:'Защита Волей',19:'Сон',24:'Нельзя захватить в зону контроля',25:'Прямой урон',53:'Щит стазиса',75:'Длительность враждебных эффектов',
 84:'Пробивание брони',116:'Восстановление здоровья',122:'Сопротивление воздействию',
 141:'Длительность оглушения',150:'Иммунитет к воздействию',151:'Невидимость',156:'Отсрочка потери сознания',
 169:'Получаемое лечение',174:'Длительность сбивания с ног',176:'Воскрешение',188:'Получаемый урон',
 2042:'Дистанция обнаружения',2051:'Удаление раны',2071:'Иммунитет к отталкиванию',2077:'Воздействие',
 2085:'Поглощение урона щитом',2087:'Иммунитет к прерыванию',2091:'Размер персонажа',
 2097:'Дополнительная способность',2130:'Отражение заклинаний',2156:'При критическом попадании оружием',
 226:'Урон ближнего боя',2004:'Устранение усталости',140:'Попадания превращаются в скользящие',2000:'Перезарядка',181:'Максимум здоровья',2166:'Передвижение'}
MULTIPLIERS={75,141,169,174,188,2042,226,2166,181,2091}
LABELS.update({20:'Количество удерживаемых противников',27:'Дополнительный урон без оружия',
 28:'Дальность ближнего боя',45:'Урон',101:'Урон критического попадания',105:'Критические попадания становятся обычными',
 112:'Урон дальнобойного оружия',137:'Урон по сбитым с ног и оглушённым',160:'Защита от атак по возможности',
 172:'Размер области',178:'Дополнительная атака',2005:'Эффективность защиты щита',2012:'Уклонение заменяет парирование',
 204:'Эффективность расходников',2052:'Дальность метательного оружия',2053:'Пробивание брони метательным оружием',
 2054:'Дальность способностей',2057:'Урон по целям с воздействиями',2099:'Начальное дыхание',2100:'Сохранённое дыхание',
 2101:'Две песни одновременно',2102:'Радиус защитных песен',2103:'Точность атакующих песен',2106:'Пробивание брони без оружия',
 2113:'Получение опыта навыков отрядом',2115:'Урон могильного света ночью',2116:'Длительность накладываемых воздействий',
 2120:'Длительность получаемых воздействий',2122:'Дополнительные комплекты оружия',2123:'Дополнительные быстрые ячейки',
 2126:'Уровень атак по возможности',2138:'Отражение стрел',2142:'Дополнительные отскоки при промахе',
 2143:'Парирование за каждого удерживаемого врага',2145:'Невосприимчивость к зоне контроля',2146:'Парирование против дальних атак',
 2147:'Попадания в ближнем бою становятся скользящими',2148:'Скользящие удары в ближнем бою становятся промахами',
 2150:'Точность с единственным одноручным оружием',2157:'Количество атак',2159:'Дополнительная атака при попадании оружием',
 2161:'Дополнительные ячейки заклинаний',2168:'Вероятность дополнительной атаки',2172:'Бонус урона специализации оружия'})
LABELS.update({70:'Точность по целям дальше 5 клеток',80:'Урон по целям с периодическим уроном',
 102:'Вероятность превращения скользящего удара в попадание',
 213:'Пробивание брони дальнобойным оружием',2129:'Игнорирование штрафов восстановления брони и щита',
 2121:'Вероятность отражения скользящей дистанционной атаки',
 2012:'Вместо Парирования используется Уклонение',2013:'Дополнительный урон за каждого соседнего противника',
 2072:'Урон по противнику в своей зоне контроля',2108:'Бонус урона пропорционально потерянному здоровью',
 2109:'Снижение перезарядки пропорционально потерянному здоровью',225:'Урон подходящего оружия ближнего боя'})
MULTIPLIERS.update({80,2072,225})
MULTIPLIERS.update({28,45,112,137,172,2057,2113,2115,2116,2120,2172})

def duration(effect):
    if effect.get('LastsUntilRest'):return None
    if effect.get('LastsUntilCombatEnds'):return 999999
    seconds=float(effect.get('Duration',0))
    return max(1,math.ceil(round(seconds,4)/10)) if seconds>.11 else 0

def effects(item):
    result=[]
    for c in game_data(item).get('useComponents',[]):
        for e in c.get('StatusEffects',[]):
            if e.get('AffectsStat')==2077:
                children=[s for g in e.get('AfflictionPrefabGraph',[]) for s in g.get('StatusEffects',[])]
                for s in children:result.append({**s,'Duration':s.get('Duration') or e.get('Duration'), 'effectName':next((g.get('localizedName') for g in e.get('AfflictionPrefabGraph',[]) if g.get('localizedName')),'')})
                if not children:result.append(e)
            else:result.append(e)
    return result

def effect_text(e):
    stat=e.get('AffectsStat');v=float(e.get('Value',0));name=STATS.get(stat) or LABELS.get(stat)
    if stat==2168:return f"Вероятность {int(v)} ударов базовой атакой: {float(e.get('ExtraValue',0)):g}%"
    if stat==2172 and not v:return ''  # Display-only marker, not a -100% multiplier.
    if stat==2046:name=SKILLS.get(e.get('Skill'),'Все навыки магии')
    if stat==14:name='Броня'+(' ('+DAMAGE_TYPES[e['DmgType']].lower()+')' if e.get('DmgType') in DAMAGE_TYPES else '')
    if stat==184:return e.get('localizedDescription','')
    if stat in {122,150}:name += ' ('+next((g.get('localizedName') for g in e.get('AfflictionPrefabGraph',[]) if g.get('localizedName')),'воздействие')+')'
    if stat==75 and v<0:return 'Снимает враждебные воздействия'
    if stat==2156:
        graph=e.get('AttackPrefabGraph',[])
        texts=[g.get('localizedDescription','') for g in graph if g.get('localizedDescription')]
        names=[g.get('localizedName','') for g in graph if g.get('localizedName')]
        name=LABELS[stat]+': '+('; '.join(dict.fromkeys(texts or names)) or 'наносит эффект яда')
        details=[effect_text(s) for g in graph for s in g.get('StatusEffects',[])]
        if details:name+=' ('+'; '.join(dict.fromkeys(filter(None,details)))+')'
        value=''
    elif stat==116:value=f': {v*100:g}% максимального здоровья'+(' каждую секунду (суммируется за раунд)' if e.get('IntervalRate') else '')
    elif stat in MULTIPLIERS or stat==2000:value=f': {(v-1)*100:+g}%'
    elif stat in {7,8,9,140,104,107,74}:value=f': {(v*100 if abs(v)<=1 else v):+g}%'
    elif stat in {101,102,2108,2109,2147,2148,2121}:value=f': {v*100:+g}%'
    elif stat in {2005,204,2013,2138}:value=f': {v:+g}%'
    elif stat==2012:value=''
    elif stat==2157:value=f': {v:g}'
    elif stat in {19,24,150,151,176,2071,2087}:value=''
    elif stat==2097:
        value=': '+next((g.get('localizedName') for g in e.get('AbilityPrefabGraph',[]) if g.get('localizedName')),'')
    else:value=f': {v:+g}' if v else ''
    if stat==25:value+=' урона'+(' за секунду (суммируется за раунд)' if e.get('IntervalRate') else '')
    if not name:return e.get('effectName') or ''
    rounds=duration(e)
    suffix=' (постоянно)' if rounds is None or (rounds==0 and stat in {56,57,58,59,99,100}) else ' (до конца боя)' if rounds==999999 else ' на '+seconds_to_rounds(rounds*10) if rounds else ''
    return name+value+suffix

def profile(item):
    game=game_data(item);source=effects(item)
    if not game.get('useComponents'):return None
    limited={19:'Сон от предмета',122:'Сопротивление воздействиям',150:'Иммунитет к новым воздействиям',176:'Воскрешение союзника',2091:'Изменение размера токена',141:'Сокращение оглушения',174:'Сокращение сбивания с ног',
        156:'Отсрочка потери сознания',2042:'Обнаружение',2071:'Иммунитет к отталкиванию',
        2087:'Иммунитет к прерыванию',2097:'Полученная способность',2130:'Отражение заклинаний',2051:'Удаление раны'}
    return {'effects':source,'description':'; '.join(dict.fromkeys(filter(None,(effect_text(e) for e in source)))),
            'limitations':list(dict.fromkeys(limited[e['AffectsStat']] for e in source if e.get('AffectsStat') in limited)),
            'cooldown':max(1,math.ceil(max((c.get('Cooldown',0) for c in game['useComponents']),default=0)/10)),
            'targeting':'ally' if any(e.get('AffectsStat')==176 for e in source) else 'self',
            'permanent':any(duration(e) is None or (duration(e)==0 and e.get('AffectsStat') in {56,57,58,59,99,100}) for e in source)}

def refresh_consumable(item):
    info=profile(item)
    if info and info['description']:item['properties']['При использовании']=info['description']
    if info and info['limitations']:item['properties']['Пока не автоматизировано']='; '.join(info['limitations'])
    return item

def virtual_equipment(states,round_number):
    """Reuse equipment calculation for all static consumable modifiers."""
    active=[]
    for state in states.values():
        if state.get('consumable') and state['until']>=round_number:
            e=state.get('source',{})
            if e.get('AffectsStat') in STATS or e.get('AffectsStat') in {7,8,9,14,84,140,2046,226,2166,2000,181,45,153,188,169}:
                e=copy.deepcopy(e);e['Apply']=0;e['ApplicationPrerequisites']=[];e['TriggerAdjustment']={}
                if e['AffectsStat']==2046 and not e.get('Skill'):
                    for skill_id in {2030,2031,2032,2034,2035,2036,2037,2040,2045,2064,2065}:
                        active.append({'name':state['name'],'equipped_slot':'Эффект','armor':0,'properties':{'gameData':{'statusEffects':[{**e,'AffectsStat':skill_id}]}}})
                    continue
                active.append({'name':state['name'],'equipped_slot':'Эффект','armor':0,'properties':{'gameData':{'statusEffects':[e]}}})
    return active

def apply(item,states,round_number,health,health_max):
    info=profile(item)
    if not info:raise ValueError('Этот предмет не является расходником.')
    revived=False
    healing=math.prod(s.get('source',{}).get('Value',1) for s in states.values() if s.get('source',{}).get('AffectsStat')==169)
    for n,e in enumerate(info['effects']):
        stat=e.get('AffectsStat');v=float(e.get('Value',0));rounds=duration(e)
        if stat==116 and not e.get('IntervalRate'):health=min(health_max,health+math.ceil(health_max*v*healing));continue
        if stat==176:
            if health>0:raise ValueError('Воскрешение применяется к павшему союзнику.')
            health=0;revived=True;continue
        if stat==150:
            names={g.get('prefab','') for g in e.get('AfflictionPrefabGraph',[])}
            for key in list(states):
                if states[key].get('affliction') in names:states.pop(key)
        if stat==2004:
            states.pop('fatigue',None);continue
        if stat==75 and v<0:
            for key in list(states):
                if not states[key].get('beneficial'):states.pop(key)
            continue
        if stat==184:continue
        # Reusing the same consumable refreshes it, rather than stacking copies.
        key=f"consumable:{game_data(item)['prefab']}:{n}"
        states[key]={'consumable':True,'source':copy.deepcopy(e),'name':effect_text(e),
                    'until':round_number+(rounds or 999999)-1,'beneficial':not e.get('IsHostile'),
                    'stacks':1,'remainingSeconds':round(float(e.get('Duration',0)),4),'affliction':e.get('affliction','')}
        if stat==25 and not e.get('IntervalRate'):
            health=max(0,health-round(v));states[key]['remainingSeconds']=0
        if stat in {53,2085}:states[key]['shieldRemaining']=v
    return max(1,health) if revived else health

def receive_damage(states,damage):
    for state in states.values():
        e=state.get('source',{})
        if e.get('AffectsStat')==188:damage=round(damage*e['Value'])
        if 'shieldRemaining' in state:
            amount=min(damage,max(0,state['shieldRemaining']));state['shieldRemaining']-=amount;damage-=amount
    return max(0,round(damage))

def crit_effects(states):
    output=[]
    for state in states.values():
        e=state.get('source',{})
        if e.get('AffectsStat')==2156:
            for g in e.get('AttackPrefabGraph',[]):
                output.extend({**s,'effectName':g.get('localizedName',''),'affliction':g.get('prefab','')} for s in g.get('StatusEffects',[]))
    return output

def pulse(states,round_number,health,health_max):
    healing=math.prod(s.get('source',{}).get('Value',1) for s in states.values()
                      if s.get('source',{}).get('AffectsStat')==169 and s.get('until',0)>=round_number-1)
    for state in states.values():
        if not state.get('consumable') or state['until']<round_number-1:continue
        e=state['source']
        if e.get('AffectsStat')==116 and e.get('IntervalRate') and state['remainingSeconds']>0:
            seconds=min(10,state['remainingSeconds']);state['remainingSeconds']-=seconds
            health=min(health_max,health+math.ceil(health_max*e['Value']*seconds*healing))
        elif e.get('AffectsStat')==25 and state['remainingSeconds']>0:
            seconds=min(10,state['remainingSeconds']);state['remainingSeconds']-=seconds
            health=max(0,health-round(e['Value']*(seconds if e.get('IntervalRate') else 1)))
    return health
