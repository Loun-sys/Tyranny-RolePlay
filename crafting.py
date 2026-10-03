"""Character-scoped crafting from extracted game recipes; no client-supplied costs."""
import json,copy,hashlib
from datetime import datetime,timezone
from functools import lru_cache
from pathlib import Path
ORIGIN='Скованный Ремеслом'
QUALITIES={1:'Обычное',2:'Хорошее',3:'Превосходное',4:'Выдающееся',5:'Безупречное'}
SUFFIX={1:'Common',2:'Fine',3:'Superior',4:'Exquisite',5:'Masterwork'}
SCHEMA='''
CREATE TABLE IF NOT EXISTS crafting_known(character_id INTEGER NOT NULL REFERENCES characters(id) ON DELETE CASCADE,recipe_key TEXT NOT NULL,PRIMARY KEY(character_id,recipe_key));
CREATE TABLE IF NOT EXISTS crafting_jobs(id INTEGER PRIMARY KEY AUTOINCREMENT,character_id INTEGER NOT NULL REFERENCES characters(id) ON DELETE CASCADE,payload TEXT NOT NULL,ready_at TEXT NOT NULL,claimed INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS crafting_shop_seeded(guild_id INTEGER PRIMARY KEY);
'''
@lru_cache(maxsize=1)
def library():return json.loads((Path(__file__).parent/'catalog/crafting.json').read_text(encoding='utf-8'))
def props(item):
    p=item.get('properties') or {}
    return json.loads(p) if isinstance(p,str) else copy.deepcopy(p)
def prefab(item):return props(item).get('gameData',{}).get('prefab','')
def quality_info(item):
    p=props(item);game=p.get('gameData',{})
    return game.get('craftQuality') or library()['items'].get(game.get('prefab',''))
def scale_row(info,level):
    kind=info['kind'];enum={'weapon':'WeaponQualityID','armor':'ArmorQualityID','shield':'ShieldQualityID'}[kind]
    base=library()['qualityEnums'][enum].get(str(info['id']))
    return library()['qualityTables'][{'weapon':'QualityScalingWeapons','armor':'QualityScalingArmor','shield':'QualityScalingShield'}[kind]].get(f'{base}_{SUFFIX[level]}')
def normalize_quality(item,level=None):
    item=copy.deepcopy(item)
    if prefab(item).startswith('RES_SkyPillar_'):item['category']='Материалы';item['weight']=0
    info=quality_info(item)
    if not info:return item
    level=level or info['level'];row=scale_row(info,level)
    if not row:return item
    p=props(item);game=p.setdefault('gameData',{});game['craftQuality']={**info,'level':level};game['qualityStats']=row
    item['quality']=QUALITIES[level]
    if info['kind']=='weapon':
        item['damage_min']=round(row['AttackBase_DamageData_DamageMin']);item['damage_max']=round(row['AttackBase_DamageData_DamageMax'])
        item['value']=round(row['Weapon_Value'])
        attack=game.setdefault('attack',{});attack['AccuracyBonus']=row['AttackBase_AccuracyBonus'];attack['DTBypass']=row['AttackBase_DTBypass']
        attack['DamageData']={**attack.get('DamageData',{}),'Minimum':item['damage_min'],'Maximum':item['damage_max']}
        p['Точность']=f"{attack['AccuracyBonus']:+g}";p['Пробивание брони']=f"{attack['DTBypass']:g}"
    else:
        item['value']=round(row['Equippable_Value']);item['recovery']=round(row['RecoveryModifier']/10,4)
        if info['kind']=='armor':
            item['armor']=round(row['DamageThreshold'],4);game.setdefault('armor',{})['DamageThreshold']=item['armor']
            game['armor']['DeflectionBonus']=row.get('Defensive_DeflectionBonus',0)
        fields={'BaseParryBonus':'Парирование','BaseDodgeBonus':'Уклонение','BaseAccuracyBonus':'Точность','BaseEnduranceBonus':'Выносливость',
            'Helmet_ParryBonus':'Парирование','Helmet_DodgeBonus':'Уклонение','Helmet_AccuracyBonus':'Точность','Gloves_Accuracy':'Точность',
            'Boots_Athletics':'Атлетика','Boots_StealthBonus':'Хитроумие','Defensive_DeflectionBonus':'Отражение'}
        for field,label in fields.items():
            if row.get(field):p[label]=f"{row[field]:+g}"
    item['properties']=p
    if game.get('statsVersion')==2:
        from item_effects import refresh_item_properties
        refresh_item_properties(item)
    return item
def upgrade_recipe(item):
    info=quality_info(item)
    if not info or info['level']>=5:return None
    for r in library()['recipes']:
        if r['kind']=='upgrade' and r['from']==info['level'] and r['scales'].get(info['kind'])==info['id']:
            if not r['target'] or r['target']==prefab(item):return r
    return None

class CraftingStore:
    def __init__(self,db):self.db=db
    async def ensure_supplies(self,guild):
        async with self.db.connect() as c:
            await c.execute('BEGIN IMMEDIATE')
            if await c.execute_fetchall('SELECT 1 FROM crafting_shop_seeded WHERE guild_id=?',(guild,)):return
            wanted={i['prefab'] for r in library()['recipes'] for i in r['ingredients'] if i['consumed'] and i['prefab'].startswith('RES_SkyPillar_')}
            wanted.update(s for r in library()['recipes'] if r['kind']=='consumable' for s in r['scrolls'])
            items=await self._items(c)
            for name in wanted:
                if name not in items:continue
                i=items[name];price=max(1,int(i['value']))
                await c.execute('INSERT OR IGNORE INTO shop_stock(guild_id,item_id,stock,buy_price,sell_price,enabled,shop_key) VALUES(?,?,?,?,?,1,?)',(guild,i['id'],15,price,price//2,'custom'))
            await c.execute('INSERT INTO crafting_shop_seeded VALUES(?)',(guild,));await c.commit()
    async def _check(self,c,cid):
        rows=await c.execute_fetchall('SELECT background FROM characters WHERE id=?',(cid,))
        if not rows or rows[0]['background']!=ORIGIN:raise ValueError('Мастерская доступна только происхождению «Скованный Ремеслом».')
    async def _items(self,c):
        return {prefab(dict(i)):dict(i) for i in await c.execute_fetchall('SELECT * FROM item_catalog') if prefab(dict(i)) and not str(i['source_url']).startswith('craft://')}
    async def snapshot(self,cid):
        async with self.db.connect() as c:
            await self._check(c,cid)
            known={r['recipe_key'] for r in await c.execute_fetchall('SELECT recipe_key FROM crafting_known WHERE character_id=?',(cid,))}
            items=await self._items(c)
            jobs=[{**dict(r),'payload':json.loads(r['payload'])} for r in await c.execute_fetchall('SELECT * FROM crafting_jobs WHERE character_id=? ORDER BY id DESC LIMIT 30',(cid,))]
        inventory=await self.db.inventory(cid);recipes=[];upgrades=[];scrolls=[]
        for r in library()['recipes']:
            if r['kind']!='consumable' or not r['output'] or r['output'][0]['prefab'] not in items:continue
            output=items[r['output'][0]['prefab']]
            ingredients=[{**x,'item':items.get(x['prefab'])} for x in r['ingredients']]
            if any(not x['item'] for x in ingredients):continue
            recipes.append({**r,'originalHours':r['hours'],'hours':0,'outputItem':output,'ingredients':ingredients,'known':not r['unlocks'] or r['key'] in known})
        for inv in inventory:
            r=upgrade_recipe(inv)
            if r and not inv['equipped_slot'] and all(x['prefab'] in items for x in r['ingredients']):
                upgrades.append({'inventoryId':inv['inventory_id'],'item':normalize_quality(inv),'recipe':{**r,'originalHours':r['hours'],'hours':0},
                    'result':normalize_quality(inv,r['to']),'ingredients':[{**x,'item':items.get(x['prefab'])} for x in r['ingredients']]})
            matches=[r for r in recipes if prefab(inv) in r['scrolls']]
            if matches:scrolls.append({'inventoryId':inv['inventory_id'],'item':inv,'recipes':[r['key'] for r in matches],'known':all(r['known'] for r in matches)})
        for j in jobs:j['ready']=True
        return {'recipes':recipes,'upgrades':upgrades,'scrolls':scrolls,'jobs':jobs}
    async def act(self,cid,payload):
        async with self.db.connect() as c:
            await c.execute('BEGIN IMMEDIATE');await self._check(c,cid)
            action=payload.get('action');items=await self._items(c)
            if action=='learn':
                inv=await c.execute_fetchall('SELECT item_catalog.*,inventory.id AS inventory_id FROM inventory JOIN item_catalog ON item_id=item_catalog.id WHERE inventory.id=? AND character_id=?',(int(payload.get('inventoryId',0)),cid))
                if not inv:raise ValueError('Рецепта нет в инвентаре.')
                matches=[r for r in library()['recipes'] if prefab(dict(inv[0])) in r['scrolls'] and r['kind']=='consumable']
                if not matches:raise ValueError('Это не рецепт расходника.')
                for r in matches:await c.execute('INSERT OR IGNORE INTO crafting_known VALUES(?,?)',(cid,r['key']))
                await c.commit();return 'Рецепт изучен. Свиток сохранён.'
            if action=='claim':
                jobs=await c.execute_fetchall('SELECT * FROM crafting_jobs WHERE id=? AND character_id=? AND claimed=0',(int(payload.get('jobId',0)),cid))
                if not jobs:raise ValueError('Работа не найдена или уже получена.')
                job=json.loads(jobs[0]['payload'])
                await self._deliver(c,cid,job)
                await c.execute('UPDATE crafting_jobs SET claimed=1 WHERE id=?',(jobs[0]['id'],));await c.commit();return 'Работа получена.'
            if action not in {'craft','upgrade'}:raise ValueError('Неизвестная операция мастерской.')
            if await c.execute_fetchall('SELECT id FROM crafting_jobs WHERE character_id=? AND claimed=0',(cid,)):raise ValueError('Сначала получите предыдущую работу.')
            quantity=int(payload.get('quantity',1))
            if not 1<=quantity<=15:raise ValueError('Количество: 1–15.')
            if action=='upgrade':
                inv=await c.execute_fetchall('SELECT item_catalog.*,inventory.id AS inventory_id,inventory.equipped_slot,inventory.quantity FROM inventory JOIN item_catalog ON item_id=item_catalog.id WHERE inventory.id=? AND character_id=?',(int(payload.get('inventoryId',0)),cid))
                if not inv or inv[0]['equipped_slot'] or inv[0]['quantity']!=1:raise ValueError('Сначала снимите предмет. Улучшается один экземпляр.')
                item=dict(inv[0]);recipe=upgrade_recipe(item);quantity=1
                if not recipe:raise ValueError('Нет доступного улучшения для этого предмета.')
                result=normalize_quality(item,recipe['to']);game=result['properties']['gameData']
                game.setdefault('craftBaseName',item['name']);game.setdefault('craftBaseId',item['id'])
                result['name']=game['craftBaseName']+' ('+result['quality']+')'
                result['source_url']='craft://'+hashlib.sha256((str(game['craftBaseId'])+':'+str(recipe['to'])).encode()).hexdigest()
                job={'kind':'upgrade','inventoryId':item['inventory_id'],'result':result,'name':item['name']}
            else:
                recipe=next((r for r in library()['recipes'] if r['key']==payload.get('recipeKey') and r['kind']=='consumable'),None)
                if not recipe:raise ValueError('Рецепт не найден.')
                if recipe['unlocks'] and not await c.execute_fetchall('SELECT 1 FROM crafting_known WHERE character_id=? AND recipe_key=?',(cid,recipe['key'])):raise ValueError('Приобретите и изучите рецепт.')
                if any(o['prefab'] not in items for o in recipe['output']):raise ValueError('Предмет рецепта отсутствует в каталоге.')
                job={'kind':'consumable','outputs':[{'itemId':items[o['prefab']]['id'],'quantity':o['quantity']*quantity} for o in recipe['output']],'name':recipe['name']}
            cost=recipe['cost']*quantity
            balance=await c.execute_fetchall('SELECT copper FROM wallets WHERE character_id=?',(cid,))
            if not balance or balance[0]['copper']<cost:raise ValueError('Недостаточно колец.')
            for ingredient in recipe['ingredients']:
                if action=='upgrade' and not ingredient['consumed'] and ingredient['prefab']==prefab(job['result']):continue
                item=items.get(ingredient['prefab'])
                if not item:raise ValueError('Материал отсутствует в каталоге.')
                stacks=await c.execute_fetchall('SELECT id,quantity FROM inventory WHERE character_id=? AND item_id=? AND equipped_slot IS NULL',(cid,item['id']))
                need=ingredient['quantity']*quantity
                if sum(s['quantity'] for s in stacks)<need:raise ValueError('Недостаточно материала: '+item['name'])
                if not ingredient['consumed']:continue
                for stack in stacks:
                    used=min(need,stack['quantity']);need-=used
                    if used==stack['quantity']:await c.execute('DELETE FROM inventory WHERE id=?',(stack['id'],))
                    else:await c.execute('UPDATE inventory SET quantity=quantity-? WHERE id=?',(used,stack['id']))
                    if not need:break
            # Reserve the upgraded item so it cannot be sold/equipped while work is underway.
            if action=='upgrade':await c.execute('UPDATE inventory SET equipped_slot=? WHERE id=?',('Мастерская',job['inventoryId']))
            await c.execute('UPDATE wallets SET copper=copper-? WHERE character_id=?',(cost,cid))
            await self._deliver(c,cid,copy.deepcopy(job))
            ready=datetime.now(timezone.utc)
            await c.execute('INSERT INTO crafting_jobs(character_id,payload,ready_at,claimed) VALUES(?,?,?,1)',(cid,json.dumps(job,ensure_ascii=False),ready.isoformat()))
            await c.commit();return 'Предмет улучшен.' if action=='upgrade' else 'Расходники изготовлены.'

    async def _deliver(self,c,cid,job):
        if job['kind']=='upgrade':
            if not await c.execute_fetchall("SELECT id FROM inventory WHERE id=? AND character_id=? AND equipped_slot='Мастерская'",(job['inventoryId'],cid)):raise ValueError('Предмет мастерской изменён. Обратитесь к мастеру.')
            cols=['name','category','slot','quality','description','lore','image_url','value','weight','hands','damage_min','damage_max','armor','recovery','properties','source_url']
            result=job['result'];result['properties']=json.dumps(result['properties'],ensure_ascii=False)
            existing=await c.execute_fetchall('SELECT id FROM item_catalog WHERE source_url=?',(result['source_url'],))
            if existing:item_id=existing[0]['id']
            else:
                if await c.execute_fetchall('SELECT id FROM item_catalog WHERE name=?',(result['name'],)):result['name']+=' · '+result['source_url'][-8:]
                cursor=await c.execute('INSERT INTO item_catalog('+','.join(cols)+') VALUES('+','.join('?' for _ in cols)+')',[result.get(k,'') for k in cols]);item_id=cursor.lastrowid
            await c.execute('UPDATE inventory SET item_id=?,equipped_slot=NULL WHERE id=? AND character_id=?',(item_id,job['inventoryId'],cid))
        else:
            inventory=await c.execute_fetchall('SELECT item_catalog.*,inventory.equipped_slot FROM inventory JOIN item_catalog ON item_catalog.id=item_id WHERE character_id=?',(cid,))
            athletics=await c.execute_fetchall("SELECT value FROM skills WHERE character_id=? AND name='Атлетика'",(cid,))
            capacity=min(40,8+(await self.db.effective_skill_in_connection(c,cid,'Атлетика'))//5)
            used=sum(self.db._item_consumes_slot(i['name'],i['category'],i['weight'],i['equipped_slot']) for i in inventory)
            for out in job['outputs']:
                existing=await c.execute_fetchall('SELECT id FROM inventory WHERE character_id=? AND item_id=? AND equipped_slot IS NULL',(cid,out['itemId']))
                if existing:await c.execute('UPDATE inventory SET quantity=quantity+? WHERE id=?',(out['quantity'],existing[0]['id']))
                else:
                    if used>=capacity:raise ValueError('Освободите место в инвентаре, чтобы забрать работу.')
                    await c.execute('INSERT INTO inventory(character_id,item_id,quantity) VALUES(?,?,?)',(cid,out['itemId'],out['quantity']));used+=1
