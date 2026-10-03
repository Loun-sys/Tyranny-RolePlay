"""Common merchants and reliable local icons; unique loot is never starter stock."""
import json,re
from functools import lru_cache
from pathlib import Path
ROOT=Path(__file__).parent
SHOPS={
 'consumables':{'name':'Лавка припасов','categories':['Расходуемые предметы','Зелья','Еда']},
 'weapons':{'name':'Оружейная лавка','categories':['Одноручное оружие','Двуручное оружие','Парное оружие','Луки','Метательное оружие','Посохи','Щиты']},
 'armor':{'name':'Лавка доспехов','categories':['Броня']},
 'custom':{'name':'Лавка мастера','categories':[]}}

@lru_cache(maxsize=1)
def icon_index():
    rows=json.loads((ROOT/'catalog/game_items.json').read_text(encoding='utf-8'))
    names={};categories={}
    for i in rows:
        path=i.get('image_url','')
        if path.startswith('assets/') and (ROOT/'web'/path).is_file():
            names[i['name'].casefold()]=path;categories.setdefault(i['category'],path)
    return names,categories

def reliable_icon(item):
    path=item.get('image_url','') or ''
    if path.startswith('assets/') and '..' not in path and (ROOT/'web'/path).is_file():return path,False
    names,categories=icon_index()
    if item['name'].casefold() in names:return names[item['name'].casefold()],False
    return categories.get(item.get('category'),'assets/game-combat/icon_option_inventory.png'),True

def common_item(item,key):
    if item.get('quality')!='Обычное' or item['category'] not in SHOPS[key]['categories']:return False
    try:props=json.loads(item.get('properties') or '{}') if isinstance(item.get('properties'),str) else item.get('properties',{})
    except (ValueError,TypeError):return False
    prefab=props.get('gameData',{}).get('prefab','')
    if re.search(r'unique|_art_|quest|test|debug|fine|superior|exquisite|masterwork|legendary',prefab,re.I):return False
    if key=='consumables':return bool(props.get('gameData',{}).get('useComponents'))
    return bool(prefab) and not props.get('gameData',{}).get('mods') and '(вариант ' not in item['name']
