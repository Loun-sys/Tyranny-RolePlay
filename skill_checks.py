"""Read-only exploration skills; deliberately separate from combat defenses/XP."""
import math
import random
from constants import WEAPON_SKILLS, MAGIC_SKILLS

COMBAT_CHECK_SKILLS = WEAPON_SKILLS + MAGIC_SKILLS
CHECK_DEFINITIONS = (
    {'name':'Запугивание','attribute':'Живучесть','sources':['Атлетика','@combatMax']},
    {'name':'Влияние','attribute':'Смекалка','sources':['Хитроумие','Знания']},
    {'name':'Наблюдательность','attribute':'Быстрота','sources':['Знания','Хитроумие']},
    {'name':'Выносливость','attribute':'Стойкость','sources':['Атлетика','Парирование']},
    {'name':'Проницательность','attribute':'Искусность','sources':['Хитроумие','Уклонение']},
)


def configuration():
    return {'definitions':[dict(d, sources=list(d['sources'])) for d in CHECK_DEFINITIONS],
            'combatSkills':list(COMBAT_CHECK_SKILLS),'pointsPerDie':10,'attributeDivisor':3}


def _value(value):
    value = value.get('value',0) if isinstance(value,dict) else value
    number = float(value)
    if not math.isfinite(number):
        raise ValueError('Значение навыка должно быть конечным числом.')
    return int(number) if number.is_integer() else number


def check_skills(attributes, skills):
    values = {name:_value(value) for name,value in skills.items()}
    strongest = max(COMBAT_CHECK_SKILLS,key=lambda name:values.get(name,0))
    maximum = values.get(strongest,0)
    tied = [name for name in COMBAT_CHECK_SKILLS if values.get(name,0)==maximum]
    result = {}
    for definition in CHECK_DEFINITIONS:
        sources = []
        for source in definition['sources']:
            name = strongest if source=='@combatMax' else source
            row = {'name':name,'value':values.get(name,0),'weight':.5}
            if source=='@combatMax':row.update(combatMaximum=True,tiedSkills=tied)
            sources.append(row)
        value = sum(source['value']*.5 for source in sources)
        dice = max(0,math.floor(value/10))
        attribute_value = _value(attributes.get(definition['attribute'],0))
        attribute_bonus = attribute_value / 3
        result[definition['name']] = {**definition,'sources':sources,'value':value,
            'attributeValue':attribute_value,'attributeBonus':attribute_bonus,'diceCount':dice,
            'formula':f'{attribute_value} / 3 + {dice}d6',
            'minimum':attribute_bonus+dice,'maximum':attribute_bonus+dice*6}
    return result


def roll_check(check, modifier=0, rng=None):
    if type(modifier) is not int or not -1000<=modifier<=1000:
        raise ValueError('Модификатор должен быть целым числом от −1000 до +1000.')
    dice = check['diceCount']
    if type(dice) is not int or not 0<=dice<=10000:
        raise ValueError('Недопустимое количество кубиков.')
    roller = rng or random.SystemRandom()
    rolls = [roller.randint(1,6) for _ in range(dice)]
    return {'rolls':rolls,'modifier':modifier,
            'total':check['attributeBonus']+sum(rolls)+modifier}


async def character_checks(db, character):
    # Exactly the same effective values as the dossier, including the active
    # weapon set, equipment, permanent talents and active consumable effects.
    from registration_api import _clean_inventory, _derived
    from consumable_store import states
    from consumables import virtual_equipment
    inventory = _clean_inventory(await db.inventory(character['id']))
    effects = await states(db,character['id'])
    return _derived(character,inventory+virtual_equipment(effects,1))['checkSkills']
