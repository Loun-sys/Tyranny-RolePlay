"""Equipment-scoped artifact library. Unsupported effects are never fake attacks."""
import json
from functools import lru_cache
from pathlib import Path
from item_effects import passive_descriptions
from special_effects import adapted_effects,artifact_shape


@lru_cache(maxsize=1)
def library():
    return json.loads((Path(__file__).parent/'catalog/artifact_abilities.json').read_text(encoding='utf-8'))['items']


def equipped_artifacts(items):
    result=[]
    for item in items:
        base=((item.get('properties') or {}).get('gameData',{}).get('craftBaseName') or item['name']).split(' (вариант ')[0]
        ability=library().get(base)
        if not ability: continue
        effects=adapted_effects(ability)
        supported=bool(ability['damageMax'] or ability.get('weaponMultiplier') or effects or 'Redeploy' in ability['prefab']) and not ability['passive']
        result.append({**ability,**artifact_shape(ability),'effects':effects,'description':ability['description']+'\nОригинальное ограничение: '+ability['cooldownMode']+'\nПошаговая версия: реализованы базовый урон и перечисленные временные эффекты; условные срабатывания, рикошеты и рост от известности пока не рассчитаны.','item':item['name'],'passives':passive_descriptions(item),
                       'supported':supported,
                       'limitation':'' if supported else 'Особый эффект пока доступен для просмотра, но не реализован в тренировочном бою.'})
    return result
