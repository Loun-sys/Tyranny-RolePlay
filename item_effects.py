"""Original equipment components and typed modifiers; never flatten multipliers."""
import json

STATS = {56:'Стойкость',57:'Сила',58:'Искусность',59:'Быстрота',99:'Смекалка',100:'Живучесть',
         6:'Парирование',161:'Магия',185:'Точность',2026:'Парирование',2027:'Уклонение',
         90:'Знания',89:'Атлетика',12:'Хитроумие',91:'Хитроумие',0:'Максимум здоровья',
         2017:'Одноручное оружие',2018:'Парное оружие',2019:'Двуручное оружие',2020:'Волшебный посох',
         2021:'Безоружный бой',2022:'Луки',2030:'Управление огнём',2031:'Управление холодом',
         2032:'Управление молниями',2034:'Управление рвением',2035:'Управление истощением',
         2036:'Управление эмоциями',2037:'Управление жизнью',2038:'Управление эмоциями',
         2039:'Управление истощением',2040:'Управление иллюзиями',2045:'Управление могильным светом',
         2064:'Управление силой',2065:'Управление камнем',2104:'Исполнение',
         2133:'Ячейки заклинаний',206:'Комплекты оружия',207:'Быстрые предметы',84:'Пробивание брони'}
SKILLS = {2:'Атлетика',3:'Знания',4:'Хитроумие',5:'Одноручное оружие',6:'Парное оружие',7:'Двуручное оружие',8:'Волшебный посох',9:'Безоружный бой',
          10:'Луки',14:'Парирование',15:'Уклонение',18:'Управление огнём',19:'Управление холодом',
          20:'Управление молниями',22:'Управление рвением',23:'Управление истощением',25:'Управление жизнью',
          28:'Управление иллюзиями',32:'Управление силой',33:'Управление камнем',37:'Дротики'}
DAMAGE_TYPES={0:'Рубящий',1:'Дробящий',2:'Колющий',3:'Огненный',4:'Ледяной',5:'Электрический',6:'Разъедающий',7:'Магический'}
ARMOR_FIELDS={0:'Piercing',1:'Crushing',2:'Piercing',3:'Burning',4:'Freezing',5:'Shocking',6:'Corroding',7:'Arcane'}
ARMOR_FIELDS[0]='Slashing'

def game_data(item):
    props=item.get('properties') or {}
    if isinstance(props,str):props=json.loads(props)
    return props.get('gameData',{})

def active_equipment(items,active_set=1):
    roman=['I','II','III','IV'][max(1,min(4,int(active_set)))-1]
    return [i for i in items if i.get('equipped_slot') and i['equipped_slot']!='Мастерская' and not i['equipped_slot'].startswith('Быстрый предмет') and (not i['equipped_slot'].startswith('Оружие') or i['equipped_slot'].startswith(f'Оружие {roman} '))]

def unconditional(effect):
    return effect.get('Apply')==0 and not effect.get('ApplicationPrerequisites') and not effect.get('TriggerAdjustment',{}).get('Type')

def component_bonuses(game):
    result={};quality=game.get('qualityStats',{})
    def add(label,value):
        if value:result[label]=result.get(label,0)+float(value)
    for t in game.get('equipmentComponents',[]):
        if 'ParryBonus' in t and 'DodgeBonus' in t:
            for field,scaled,label in [('ParryBonus','Helmet_ParryBonus','Парирование'),('DodgeBonus','Helmet_DodgeBonus','Уклонение'),('AccuracyBonus','Helmet_AccuracyBonus','Точность')]:add(label,quality.get(scaled,t.get(field,0)))
        if 'BaseParryBonus' in t:
            for field,label in [('BaseParryBonus','Парирование'),('BaseDodgeBonus','Уклонение'),('BaseAccuracyBonus','Точность'),('BaseEnduranceBonus','Выносливость')]:add(label,quality.get(field,t.get(field,0)))
        if 'AthleticsBonus' in t:
            for field,scaled,label in [('AthleticsBonus','Boots_Athletics','Атлетика'),('StealthBonus','Boots_StealthBonus','Хитроумие'),('DisengagementDefenseBonus','Boots_DisengagementBonus','Защита от атак по возможности')]:add(label,quality.get(scaled,t.get(field,0)))
        if 'MeleeDamageBonus' in t:
            add('Точность',quality.get('Gloves_Accuracy',t.get('AccuracyBonus',0)))
            add('Урон ближнего боя',quality.get('Gloves_BonusMeleeDamage',t.get('MeleeDamageBonus',0)))
            add('Критический шанс',quality.get('Gloves_PrecisionBonus',t.get('PrecisionBonus',0))*100)
        if 'DeflectionBonus' in t:add('Отражение',quality.get('Defensive_DeflectionBonus',t['DeflectionBonus']))
    attack=game.get('attack',{})
    add('Точность',attack.get('AccuracyBonus',0));add('Пробивание брони',attack.get('DTBypass',0))
    return result

def equip_modifiers(item):
    game=game_data(item);flat=component_bonuses(game);percent={};multiply={};typed={};conditional=[]
    def add(target,key,value):target[key]=target.get(key,0)+value
    for e in game.get('statusEffects',[]):
        if not unconditional(e):conditional.append(e);continue
        stat=e.get('AffectsStat');value=float(e.get('Value',0));key=STATS.get(stat)
        if stat==2046:key=SKILLS.get(e.get('Skill'))
        if stat==14:
            if e.get('DmgType') in DAMAGE_TYPES:add(typed,DAMAGE_TYPES[e['DmgType']],value)
            else:add(flat,'Броня',value)
        elif stat in {7,8,9}:add(percent,{7:'Выносливость',8:'Магия',9:'Воля'}[stat],value*100)
        elif stat in {107,104,74,140}:
            add(flat,{107:'Критический шанс',104:'Отражение промахов',74:'Отражение критических ударов',140:'Отражение попаданий'}[stat],value*100)
        elif stat in {2000,181,2166,45,153,226,188,169}:
            label={2000:'Перезарядка',181:'Максимум здоровья',2166:'Передвижение',45:'Урон',153:'Сила заклинаний',226:'Урон ближнего боя',188:'Получаемый урон',169:'Получаемое лечение'}[stat]
            multiply[label]=multiply.get(label,1)*value
        elif key:add(flat,key,value)
    return {'flat':flat,'percent':percent,'multiply':multiply,'armorByType':typed,'conditional':conditional}


def equip_bonuses(item):
    return equip_modifiers(item)['flat']

def unarmed_damage(item):
    game=game_data(item);q=game.get('qualityStats',{})
    gloves=next((t for t in game.get('equipmentComponents',[]) if 'MeleeDamageBonus' in t),{})
    damage=gloves.get('DamageData',{})
    return (float(q.get('Gloves_DamageData_DamageMin',damage.get('Minimum',0))),float(q.get('Gloves_DamageData_DamageMax',damage.get('Maximum',0))))

def armor_by_type(item):
    game=game_data(item);armor=game.get('armor',{});quality=game.get('qualityStats',{})
    base=float(item.get('armor',0));mods=equip_modifiers(item)
    return {name:round(base*float(quality.get('DTPerc'+ARMOR_FIELDS[k],armor.get('DtPerc'+ARMOR_FIELDS[k],100)))/100+mods['armorByType'].get(name,0)+mods['flat'].get('Броня',0),4) for k,name in DAMAGE_TYPES.items()}


def passive_descriptions(item):
    game=game_data(item)
    modifiers=equip_modifiers(item);bonuses=modifiers['flat']
    entries=[f'{name}: {value:+g}' for name,value in bonuses.items()]
    entries += [f'{name}: {value:+g}%' for name,value in modifiers['percent'].items()]
    entries += [f'{name}: {(value-1)*100:+g}%' for name,value in modifiers['multiply'].items() if value!=1]
    entries += [f'Броня ({name.lower()} урон): {value:+g}' for name,value in modifiers['armorByType'].items()]
    for mod in game.get('mods',[]):
        for trigger,label in [('StatusEffectsOnAttack','При атаке'),('StatusEffectsOnCrit','При критическом попадании'),('StatusEffectsOnLaunch','При применении')]:
            if mod.get(trigger): entries.append(label+': особый эффект предмета (см. описание)')
    return entries

def refresh_item_properties(item):
    """Readable Russian values from the exact same rules used during equipment."""
    p=item['properties'];game=game_data(item)
    # These fields were formerly copied from Wiki or emitted by quality scaling.
    for key in list(p):
        if key not in {'gameData','При использовании'}:p.pop(key)
    entries=passive_descriptions(item)
    if entries:p['Эффекты']='; '.join(entries)
    mods=list(dict.fromkeys(m.get('localizedName','') for m in game.get('mods',[]) if m.get('localizedName')))
    if mods:p['Модификаторы']='; '.join(mods)
    descriptions=list(dict.fromkeys(s.get('localizedDescription','') for s in game.get('statusEffects',[]) if s.get('localizedDescription')))
    if descriptions:p['Особые эффекты']='; '.join(descriptions)
    if game.get('armor'):
        p['Броня по типу урона']='; '.join(f'{name}: {value:g}' for name,value in armor_by_type(item).items())
    low,high=unarmed_damage(item)
    if high:p['Безоружный урон']=f'{low:g}–{high:g}'
    if game.get('attack'):
        damage=game['attack'].get('DamageData',{})
        if damage.get('Type') in DAMAGE_TYPES:p['Тип урона']=DAMAGE_TYPES[damage['Type']]
        if game['attack'].get('AttackDistance'):p['Дальность']=f"{game['attack']['AttackDistance']:g} м"
    return item
