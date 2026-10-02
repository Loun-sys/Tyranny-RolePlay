"""Explicit tabletop semantics for serialized effects (10 seconds = one round)."""
import math

STAT_NAMES={14:'armor',57:'Сила',58:'Искусность',59:'Быстрота',56:'Стойкость',99:'Смекалка',100:'Живучесть',
    185:'accuracy',188:'incoming',2000:'cooldown',2166:'movement',7:'Выносливость',9:'Воля',109:'extraDamage'}
CONTROL={'daze':'Ошеломление','confus':'Замешательство','terrify':'Ужас','freeze':'Заморозка',
    'frozen':'Заморозка','disarm':'Обезоруживание','fatigue':'Усталость','weaken':'Ослабление',
    'stun':'Оглушение','paralyze':'Паралич','petrif':'Окаменение','blind':'Слепота'}

def adapted_effects(ability):
    effects=[];seen=set()
    for s in ability.get('statuses',[]):
        stat=s.get('AffectsStat');tag=str(s.get('Tag','')).lower();value=float(s.get('Value',0))
        rounds=999999 if s.get('LastsUntilCombatEnds') else max(1,math.ceil(float(s.get('Duration',0))/10))
        side='enemy' if s.get('IsHostile') else 'self'
        if stat==124:kind='purge'
        elif stat==61:kind='drain'
        elif stat==2085:kind='shield'
        elif stat==116:kind='healPercent'
        elif stat==25:kind='delayedDamage'
        elif stat==87:kind='retaliateParalyze'
        elif stat==2077:
            kind=next((k for k in CONTROL if k in tag),'')
            if not kind:continue
        elif stat in STAT_NAMES:kind=STAT_NAMES[stat]
        else:continue
        key=(kind,value,rounds,side)
        if key in seen:continue
        seen.add(key);effects.append({'kind':kind,'value':value,'rounds':rounds,'side':side,
            'name':CONTROL.get(kind,{'armor':'Изменение брони','shield':'Щит','incoming':'Изменение входящего урона',
                'movement':'Изменение скорости','accuracy':'Изменение точности','cooldown':'Изменение перезарядки',
                'drain':'Поглощение здоровья','delayedDamage':'Отложенный урон','purge':'Снятие полезных эффектов',
                'healPercent':'Лечение','extraDamage':'Дополнительный магический урон'}.get(kind,kind))})
    return effects

def artifact_shape(ability):
    p=ability['prefab'].lower()
    if 'scytheofyears' in p:return {'targeting':'cone','angle':210,'range':3}
    if 'shockwave' in p or 'hammerofsunder' in p:return {'targeting':'line','range':8}
    if 'visageofterror' in p or 'leechenergy' in p:return {'targeting':'cone','angle':120,'range':5}
    if any(k in p for k in ['steadfaststand','forceofpeace','shadows embrace','shadowsembrace','championsboon']):return {'targeting':'self','range':0}
    if 'redeploy' in p:return {'targeting':'ally','range':8}
    return {'targeting':'area' if ability.get('area') else 'unit'}
