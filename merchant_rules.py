"""Source-backed shop progression. Prices never alter combat item statistics."""
import json,re
import math
from functools import lru_cache
from pathlib import Path
ROOT=Path(__file__).parent
SHOPS={
 'consumables':{'name':'Лавка припасов','categories':['Расходуемые предметы','Зелья','Еда']},
 'weapons':{'name':'Оружейная лавка','categories':['Одноручное оружие','Двуручное оружие','Парное оружие','Луки','Метательное оружие','Посохи','Щиты']},
 'armor':{'name':'Лавка доспехов','categories':['Броня']},
 'misc':{'name':'Ремесло и разное','categories':['Материалы','Чертежи','Сигилы','Разное']},
 **{f'level_{level}':{'name':name,'categories':[],'minLevel':level} for level,name in
    [(5,'Торговый двор'),(10,'Гильдейский рынок'),(15,'Редкие товары'),(20,'Лавка высшего качества')]},
 'custom':{'name':'Лавка мастера','categories':[]}}
for shop in SHOPS.values():shop.setdefault('minLevel',1)
SHOP_BALANCE_VERSION=4
MATERIAL_PRICES={'RES_SkyPillar_AlchemySupplies':5,'RES_SkyPillar_Scrolls':10,
    'RES_SkyPillar_Hide':15,'RES_SkyPillar_Ingot_Iron':20,'RES_SkyPillar_Ingot_Bronze':40}
QUALITY_LEVELS={'Обычное':1,'Хорошее':5,'Добротное':5,'Превосходное':10,
 'Выдающееся':15,'Изысканное':15,'Безупречное':20,'Шедевр':20,'Артефакт':20}

def is_artifact(item):
    """Include artifact equipment/variants even when their quality is mundane."""
    from item_effects import game_data
    from artifact_rules import library
    game=game_data(item)
    base=(game.get('craftBaseName') or item.get('name','')).split(' (')[0]
    return (item.get('quality')=='Артефакт' or
        bool(re.search(r'(?:^|_)ART(?:_|$)',game.get('prefab',''),re.I)) or base in library())

def excluded_from_trade(item):
    from item_effects import game_data
    if is_artifact(item):return 'Артефакты и артефактные предметы не продаются'
    if any(re.search(r'\bвариант\s+\d+\b',str(name),re.I) for name in (item.get('name',''),game_data(item).get('craftBaseName',''))):
        return 'Нумерованные варианты предметов не продаются'
    return ''

@lru_cache(maxsize=1)
def recipe_outputs():
    from crafting import library
    from item_texts import catalog_texts
    rows=catalog_texts()[0]
    return {s:rows[r['output'][0]['prefab']] for r in library()['recipes'] if r['kind']=='consumable' and r['output'] and r['output'][0]['prefab'] in rows for s in r['scrolls']}

@lru_cache(maxsize=1)
def consumable_costs():
    from crafting import library
    return {r['output'][0]['prefab']:r['cost']+sum(MATERIAL_PRICES.get(i['prefab'],0)*i['quantity'] for i in r['ingredients'] if i['consumed']) for r in library()['recipes'] if r['kind']=='consumable' and r['output']}

def market_profile(item):
    """Every item has a catalogue entry; only verified, usable goods are seeded."""
    from item_effects import game_data
    from consumables import profile
    game=game_data(item);source=game.get('sourceItem',{});prefab=game.get('prefab','');recipe=recipe_outputs().get(prefab)
    reason=''
    if excluded_from_trade(item):reason=excluded_from_trade(item)
    elif not game.get('statsVersion'):reason='Нет подтверждённых игровых характеристик'
    elif prefab.startswith('MONEY_'):reason='Валюта хранится в кошельке'
    elif source.get('CutFromGame') or source.get('IsProp') or re.search(r'(?:test|debug|^Prop_)',prefab,re.I):reason='Служебный предмет'
    elif source.get('IsQuestItem') or re.search(r'^Quest_',prefab,re.I):reason='Квестовый предмет'
    elif (source.get('PlayerBound') or source.get('RestrictedToCharacter')) and not recipe:reason='Персональный предмет'
    elif item.get('category')=='Чертежи' and not recipe:reason='Этот чертёж пока не используется в мастерской'
    elif int(item.get('value',0))<=0 and not recipe:reason='Не продаётся в игре'
    elif item.get('category') in SHOPS['consumables']['categories'] and not profile(item):reason='Нет эффекта применения'
    level=QUALITY_LEVELS.get(item.get('quality'),1)
    original=source.get('Value',{});original=original.get('InitialValue',0) if isinstance(original,dict) else original
    price=max(1,round(float(item.get('value',0))),round(float(original or 0)))
    level=max(level,15 if price>=5000 else 10 if price>=2000 else 5 if price>=750 else 1)
    unique=bool(source.get('Unique') or source.get('OneOfAKind') or re.search(r'(?:_ART_|Unique)',prefab,re.I))
    if unique:level=max(level,15)
    artifact=is_artifact(item)
    if artifact:level=20;price=max(price,6000)
    if item.get('category')=='Аксессуары':level=max(level,5)
    if game.get('mods'):level=max(level,5)
    info=profile(item)
    if info and info['permanent']:level=20;price=max(price,5000)
    elif info:
        for effect in info['effects']:
            stat=effect.get('AffectsStat');value=float(effect.get('Value',0))
            if stat==116:
                healing=value*(max(1,float(effect.get('Duration',0))) if effect.get('IntervalRate') else 1)
                level=max(level,10 if healing>=.7 else 5 if healing>=.4 else 1)
            if stat in {56,57,58,59,99,100}:level=max(level,10 if value>=6 else 5 if value>=3 else 1)
            if stat in {45,112,226} and value>=1.25:level=max(level,10)
            if stat==14:level=max(level,10 if value>=10 else 5 if value>=4 else 1)
            if stat in {7,8,9} and value>=.2:level=max(level,5)
            if stat in {53,2085}:level=max(level,10 if value>=60 else 5 if value>=30 else 1)
            if stat in {150,151,2071,2087}:level=max(level,5)
            if stat in {176,2046}:level=max(level,10)
            if stat==2097:level=max(level,15)
            nested=[s for g in effect.get('AttackPrefabGraph',[]) for s in g.get('StatusEffects',[])] if stat==2156 else [effect]
            for damage in nested:
                if damage.get('AffectsStat')!=25 or float(damage.get('Value',0))<=0:continue
                total=float(damage['Value'])*(max(1,float(damage.get('Duration',0))) if damage.get('IntervalRate') else 1)
                level=max(level,15 if total>=200 else 10 if total>=100 else 5 if total>=30 else 1)
        price=max(price,{1:1,5:150,10:350,15:750,20:5000}[level])
    # A modified common prefab must not cost less than its mundane counterpart.
    if game.get('mods'):price=max(price,{1:100,5:400,10:1200,15:3000,20:6000}[level])
    if unique:price=max(price,6000 if level==20 else 3000)
    if recipe:
        output=market_profile(recipe);level=max(5,output['minLevel']);price=max(price,250,output['buyPrice']*3)
    if prefab in MATERIAL_PRICES:level=1;price=MATERIAL_PRICES[prefab]
    if info and prefab in consumable_costs():price=max(price,math.ceil(consumable_costs()[prefab]*1.25))
    category=item.get('category');key=next((k for k in ('consumables','weapons','armor','misc') if category in SHOPS[k]['categories']),'misc')
    if level>1:key=f'level_{level}'
    stock=(10+sum(map(ord,prefab))%6 if info else 25 if category=='Материалы' else 3 if category in {'Чертежи','Сигилы'} else 3+sum(map(ord,prefab))%3 if level==1 else 2 if level<=10 else 1)
    if info and not info['permanent'] and level>=10:stock=3 if level==10 else 2
    sell=price//2
    if info and prefab in consumable_costs():sell=min(sell,consumable_costs()[prefab]//2)
    return {'shopKey':key,'shopName':SHOPS[key]['name'],'minLevel':level,'purchasable':not reason,
        'unavailableReason':reason,'buyPrice':price,'sellPrice':sell,'initialStock':1 if unique or (info and info['permanent']) else stock}

def shop_accepts(item,key):
    if excluded_from_trade(item):return False
    if key=='custom':return True
    p=market_profile(item)
    return p['purchasable'] and p['shopKey']==key

def runtime_warnings(item):
    """Do not present stored source graphs as fully implemented combat effects."""
    from item_effects import game_data,equip_modifiers
    from consumables import profile
    game=game_data(item);notes=[]
    if equip_modifiers(item)['conditional'] or any(m.get(k) for m in game.get('mods',[]) for k in ('StatusEffectsOnAttack','StatusEffectsOnCrit','StatusEffectsOnLaunch')):
        notes.append('Условные эффекты и особые срабатывания этого предмета применяются мастером вручную.')
    info=profile(item)
    if info and info['limitations']:notes.append('Требуют контроля мастера: '+', '.join(info['limitations'])+'.')
    if re.search(r'_ART_',game.get('prefab',''),re.I):
        notes.append('Артефактная способность: базовые поддерживаемые эффекты автоматизированы; рикошеты и рост от известности требуют мастера.')
    return notes

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
