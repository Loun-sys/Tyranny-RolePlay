"""Equipment-scoped artifact library. Unsupported effects are never fake attacks."""
import json
from functools import lru_cache
from pathlib import Path
from item_effects import passive_descriptions


@lru_cache(maxsize=1)
def library():
    return json.loads((Path(__file__).parent/'catalog/artifact_abilities.json').read_text(encoding='utf-8'))['items']


def equipped_artifacts(items):
    result=[]
    for item in items:
        base=item['name'].split(' (вариант ')[0]
        ability=library().get(base)
        if not ability: continue
        supported=bool(ability['damageMax'] or ability.get('weaponMultiplier')) and not ability['passive']
        result.append({**ability,'description':ability['description']+'\nОригинальное ограничение: '+ability['cooldownMode']+('\nТренировка: разовые способности доступны один раз до перезапуска; пока рассчитывается только урон, вторичные особые эффекты не применяются.' if supported else ''),'item':item['name'],'passives':passive_descriptions(item),
                       'supported':supported,
                       'limitation':'' if supported else 'Особый эффект пока доступен для просмотра, но не реализован в тренировочном бою.'})
    return result
