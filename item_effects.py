"""Safe equip-time subset of original status effects (not on-hit triggers)."""
STATS = {56:'Стойкость',57:'Сила',58:'Искусность',59:'Быстрота',99:'Смекалка',100:'Живучесть',
         6:'Парирование',7:'Выносливость',9:'Воля',161:'Магия',162:'Уклонение',185:'Точность',
         14:'Броня',90:'Знания',107:'Критический шанс',0:'Максимум здоровья'}
SKILLS = {2:'Атлетика',3:'Знания',4:'Хитроумие',5:'Одноручное оружие',6:'Парное оружие',7:'Двуручное оружие',8:'Волшебные посохи',9:'Безоружный бой',
          10:'Луки',14:'Парирование',15:'Уклонение',18:'Управление огнём',19:'Управление холодом',
          20:'Управление молниями',22:'Управление рвением',23:'Управление истощением',25:'Управление жизнью',
          28:'Управление иллюзиями',32:'Управление силой',33:'Управление камнем',37:'Дротики'}


def equip_bonuses(item):
    result={}
    for effect in (item.get('properties') or {}).get('gameData',{}).get('statusEffects',[]):
        # Conditional/multiplicative effects must not silently become flat stats.
        if effect.get('Apply')!=0 or effect.get('ApplicationPrerequisites'):
            continue
        key=STATS.get(effect.get('AffectsStat'))
        if effect.get('AffectsStat')==2046: key=SKILLS.get(effect.get('Skill'))
        if key: result[key]=result.get(key,0)+float(effect.get('Value',0))
    return result


def passive_descriptions(item):
    game=(item.get('properties') or {}).get('gameData',{})
    bonuses=equip_bonuses(item)
    entries=[f'{name}: {value:+g}' for name,value in bonuses.items()]
    for mod in game.get('mods',[]):
        for trigger,label in [('StatusEffectsOnAttack','При атаке'),('StatusEffectsOnCrit','При критическом попадании'),('StatusEffectsOnLaunch','При применении')]:
            if mod.get(trigger): entries.append(label+': особый эффект предмета (см. описание)')
    return entries
