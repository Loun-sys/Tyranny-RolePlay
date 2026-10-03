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
        item['description'], item['lore'] = canonical['description'], canonical['lore']
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
    return item
