"""Canonical item copy, separated from stats and internal provenance identifiers."""
import copy
import json
import re
from functools import lru_cache
from pathlib import Path
from urllib.parse import unquote
from official_localization import official_entity

@lru_cache(maxsize=1)
def catalog_texts():
    rows = json.loads((Path(__file__).parent/'catalog/game_items.json').read_text(encoding='utf-8'))
    for row in rows:
        if row['properties']['gameData']['prefab']=='WPN_1H_IR_Dagger_Lantry':row['name']='Перо Книгочея'
        if row['category']=='Одноручное оружие' and row['hands']==2:row['category']='Двуручное оружие'
    return {r['properties']['gameData']['prefab']:r for r in rows}, {r['name'].casefold():r for r in rows}

def clean_copy(text):
    text = str(text or '')
    if re.search(r'предмет из (?:игры|Tyranny|Тирании)', text, re.I): return ''
    text = re.sub(r'https?://[^\s<>]*?(?:fandom\.com|wiki)[^\s<>]*', '', text, flags=re.I)
    return text.strip()

def normalize_item_text(item):
    item = copy.deepcopy(item)
    p = item.get('properties') or {}
    if isinstance(p, str):
        try: p = json.loads(p)
        except (TypeError, ValueError): p = {}
    game = p.get('gameData', {})
    by_prefab, by_name = catalog_texts()
    canonical = by_prefab.get(game.get('prefab'))
    if canonical is None and 'fandom.com' in str(item.get('source_url', '')):
        slug = unquote(item['source_url'].rsplit('/',1)[-1]).replace('_',' ')
        entity = official_entity(slug)
        if entity and entity.get('table') == 'items':
            item['name'] = entity['name_ru'] or item['name']
            item['lore'] = entity['description_ru'] or ''
        canonical = by_name.get(item.get('name','').casefold())
        if canonical is None:
            # Unmatched legacy Wiki prose is not an authoritative translation.
            item['description'] = ''
            item['lore'] = entity.get('description_ru','') if entity and entity.get('table') == 'items' else ''
            p = {k:v for k,v in p.items() if k == 'gameData' or not re.search(r'[А-Яа-яA-Za-z]', str(v))}
    if canonical:
        item['category']=canonical['category']
        item['hands'],item['slot']=canonical['hands'],canonical['slot']
        item['description'], item['lore'] = canonical['description'], canonical['lore']
        source=canonical['properties']['gameData']
        if source.get('statsVersion')==2 and game.get('statsVersion')!=2:
            retained={k:copy.deepcopy(game[k]) for k in ['craftQuality','craftBaseName'] if k in game}
            game={**copy.deepcopy(source),**retained}
            p={'gameData':game,**{k:copy.deepcopy(v) for k,v in canonical['properties'].items() if k!='gameData'}}
            for field in ['armor','damage_min','damage_max','recovery']:item[field]=canonical[field]
            from crafting import normalize_quality
            item['properties']=p
            item=normalize_quality(item)
            p=item['properties'];game=p['gameData']
        if str(item.get('source_url','')).startswith('craft://'):
            game['craftBaseName'] = canonical['name']
            item['name'] = canonical['name'] + ' (' + item.get('quality','Обычное') + ')'
        else: item['name'] = canonical['name']
        if not game.get('localizedText'):
            p = {**canonical['properties'], 'gameData':game or canonical['properties']['gameData']}
            p['gameData']['localizedText'] = True
    item['description'] = clean_copy(item.get('description'))
    item['lore'] = clean_copy(item.get('lore'))
    if item['lore'] == item['description']: item['description'] = ''
    item['properties'] = p
    if game.get('statsVersion')==2:
        from consumables import refresh_consumable
        refresh_consumable(item)
    if item.get('category') in {'Одноручное оружие','Двуручное оружие','Парное оружие','Луки','Метательное оружие','Посохи','Щиты'}:
        item['properties']['Хват']='Двуручное оружие · занимает обе руки' if int(item.get('hands') or 0)>=2 else ('Щит · занимает одну руку' if item['category']=='Щиты' else 'Одноручное оружие · занимает одну руку')
    return item
