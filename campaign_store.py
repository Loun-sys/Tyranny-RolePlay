"""Owner-scoped maps, guild shops and atomic copper-ring accounting."""
import json
from urllib.parse import urlparse

SCHEMA = '''
CREATE TABLE IF NOT EXISTS wallets(character_id INTEGER PRIMARY KEY REFERENCES characters(id) ON DELETE CASCADE, copper INTEGER NOT NULL DEFAULT 0 CHECK(copper>=0));
CREATE TABLE IF NOT EXISTS battle_maps(id INTEGER PRIMARY KEY AUTOINCREMENT,guild_id INTEGER NOT NULL,owner_id INTEGER NOT NULL,name TEXT NOT NULL,spec TEXT NOT NULL,published INTEGER NOT NULL DEFAULT 0,updated_at TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS shop_settings(guild_id INTEGER PRIMARY KEY,name TEXT NOT NULL DEFAULT 'Имперская лавка',enabled INTEGER NOT NULL DEFAULT 1);
CREATE TABLE IF NOT EXISTS shop_stock(guild_id INTEGER NOT NULL,item_id INTEGER NOT NULL REFERENCES item_catalog(id),stock INTEGER NOT NULL CHECK(stock>=-1),buy_price INTEGER NOT NULL CHECK(buy_price>=0),sell_price INTEGER NOT NULL CHECK(sell_price>=0),enabled INTEGER NOT NULL DEFAULT 1,shop_key TEXT NOT NULL DEFAULT 'custom',PRIMARY KEY(guild_id,item_id));
CREATE TABLE IF NOT EXISTS shop_seeded(guild_id INTEGER PRIMARY KEY,created_at TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS shop_branches(guild_id INTEGER NOT NULL,shop_key TEXT NOT NULL,name TEXT NOT NULL,enabled INTEGER NOT NULL DEFAULT 1,PRIMARY KEY(guild_id,shop_key));
CREATE TABLE IF NOT EXISTS commerce_log(id INTEGER PRIMARY KEY AUTOINCREMENT,character_id INTEGER NOT NULL,guild_id INTEGER NOT NULL,operation TEXT NOT NULL,item_id INTEGER,quantity INTEGER NOT NULL,amount INTEGER NOT NULL,created_at TEXT DEFAULT CURRENT_TIMESTAMP);
'''


def money(total):
    total = int(total)
    return {'totalCopper': total, 'iron': total // 10000, 'bronze': total // 100 % 100, 'copper': total % 100}


def validate_map(payload):
    if not isinstance(payload,dict): raise ValueError('Ожидается объект карты.')
    width, height = int(payload.get('width', 13)), int(payload.get('height', 9))
    if not 6 <= width <= 40 or not 6 <= height <= 40:
        raise ValueError('Размер сетки должен быть от 6×6 до 40×40.')
    cell = int(payload.get('cellSize', 48))
    if not 16 <= cell <= 120:
        raise ValueError('Размер клетки: 16–120 пикселей.')
    image = str(payload.get('image', ''))
    if any(c in image for c in ('"', "'", '\\', '\n', '\r', '<', '>')):
        raise ValueError('Недопустимый адрес изображения.')
    if not (not image or (image.startswith('assets/maps/') and '..' not in image) or
            (urlparse(image).scheme == 'https' and urlparse(image).netloc) or
            (image.startswith(('data:image/png;base64,', 'data:image/jpeg;base64,', 'data:image/webp;base64,')) and len(image) <= 5_000_000)):
        raise ValueError('Фон: HTTPS-ссылка или загруженное PNG/JPEG/WebP до 3,5 МБ.')
    def cells(key):
        result = set()
        for row in payload.get(key, []):
            x,y = int(row['x']),int(row['y'])
            if not 0 <= x < width or not 0 <= y < height:
                raise ValueError('Препятствие вне сетки.')
            result.add((x,y))
        return [{'x':x,'y':y} for x,y in sorted(result)]
    blocked, sight, cover = cells('blocked'), cells('sightBlocked'), cells('cover')
    occupied = {(p['x'],p['y']) for p in blocked}
    spawns = dict(payload.get('spawns') or {})
    if not set(spawns).issubset({'player','dummy','dummy_left','dummy_right'}):
        raise ValueError('Неизвестный старый тип стартовой позиции.')
    points = []
    for name, row in spawns.items():
        point = (int(row['x']),int(row['y']))
        if not 0 <= point[0] < width or not 0 <= point[1] < height or point in occupied or point in points:
            raise ValueError('Стартовые клетки должны быть свободными и различными.')
        points.append(point)
        spawns[name] = {'x': point[0], 'y': point[1]}
    placements=[]
    tokens=payload.get('tokens',payload.get('npcs',[]))
    if not isinstance(tokens,list) or len(tokens)>100:raise ValueError('Не более 100 токенов на карту.')
    for row in tokens:
        if not isinstance(row,dict):raise ValueError('Некорректный токен.')
        x,y=int(row['x']),int(row['y'])
        if not 0<=x<width or not 0<=y<height or (x,y) in occupied or (x,y) in points:
            raise ValueError('Токен должен стоять в отдельной свободной клетке.')
        kind=row.get('kind','npc')
        if kind not in {'npc','player'}:raise ValueError('Неизвестный тип токена.')
        team=row.get('team','enemy' if kind=='npc' else 'ally')
        if team not in {'enemy','ally','neutral'}:raise ValueError('Неизвестная сторона токена.')
        if kind=='player' and any(p['kind']=='player' and p['id']==int(row['id']) for p in placements):
            raise ValueError('Персонаж игрока уже размещён на карте.')
        points.append((x,y));placements.append({'id':int(row['id']),'kind':kind,'x':x,'y':y,'team':team})
    return {'name': str(payload.get('name','Новая карта')).strip()[:100] or 'Новая карта',
            'width':width,'height':height,'cellSize':cell,'image':image,'blocked':blocked,
            'sightBlocked':sight,'cover':cover,'spawns':spawns,'tokens':placements,'training':bool(payload.get('training')),
            'offsetX': max(-2000,min(2000,int(payload.get('offsetX',0)))),
            'offsetY': max(-2000,min(2000,int(payload.get('offsetY',0)))),
            'imageScale': max(.1,min(5,float(payload.get('imageScale',1)))),
            'gridOpacity': max(0,min(1,float(payload.get('gridOpacity',.3))))}


class CampaignStore:
    def __init__(self, db): self.db = db

    async def ensure_shops(self,guild):
        from merchant_rules import common_item
        async with self.db.connect() as c:
            if await c.execute_fetchall('SELECT 1 FROM shop_seeded WHERE guild_id=?',(guild,)):return
        async with self.db.connect() as c:
            await c.execute('BEGIN IMMEDIATE')
            if await c.execute_fetchall('SELECT 1 FROM shop_seeded WHERE guild_id=?',(guild,)):return
            rows=[dict(r) for r in await c.execute_fetchall('SELECT * FROM item_catalog ORDER BY value,name,id')]
            for key in ['consumables','weapons','armor']:
                candidates=[r for r in rows if common_item(r,key)]
                groups={}
                for item in candidates:
                    group=item['category']+':'+item.get('slot','')
                    groups.setdefault(group,[]).append(item)
                selected=[]
                cap={'consumables':15,'weapons':10,'armor':12}[key]
                while len(selected)<cap and any(groups.values()):
                    for group in groups.values():
                        if group and len(selected)<cap:selected.append(group.pop(0))
                for item in selected:
                    stock=10+sum(map(ord,item['name']))%6 if key=='consumables' else 3+sum(map(ord,item['name']))%3
                    price=max(1,int(item['value']))
                    await c.execute('INSERT OR IGNORE INTO shop_stock(guild_id,item_id,stock,buy_price,sell_price,enabled,shop_key) VALUES(?,?,?,?,?,1,?)',
                        (guild,item['id'],stock,price,price//2,key))
            await c.execute('INSERT INTO shop_seeded(guild_id) VALUES(?)',(guild,))
            await c.commit()

    async def wallet(self,cid):
        async with self.db.connect() as conn:
            rows=await conn.execute_fetchall('SELECT copper FROM wallets WHERE character_id=?',(cid,))
            return money(rows[0]['copper'] if rows else 0)

    async def set_wallet(self,cid,total):
        if not 0 <= total <= 2_000_000_000: raise ValueError('Количество колец вне допустимого диапазона.')
        async with self.db.connect() as conn:
            await conn.execute('INSERT INTO wallets VALUES(?,?) ON CONFLICT(character_id) DO UPDATE SET copper=excluded.copper',(cid,total))
            await conn.commit()

    async def maps(self,guild,owner=None):
        async with self.db.connect() as conn:
            rows=await conn.execute_fetchall('SELECT * FROM battle_maps WHERE guild_id=? AND '+('owner_id=?' if owner is not None else 'published=1')+' ORDER BY updated_at DESC', (guild,owner) if owner is not None else (guild,))
            return [{**dict(row),'spec':json.loads(row['spec'])} for row in rows]

    async def save_map(self,guild,owner,payload):
        if not isinstance(payload,dict): raise ValueError('Некорректная карта.')
        spec=validate_map(payload.get('spec',{})); ident=int(payload.get('id',0))
        from npc_store import NPCStore
        await NPCStore(self.db).resolve_map(guild,owner,[p for p in spec['tokens'] if p['kind']=='npc'])
        async with self.db.connect() as conn:
            for placement in spec['tokens']:
                if placement['kind']=='player' and not await conn.execute_fetchall('SELECT id FROM characters WHERE id=? AND guild_id=?',(placement['id'],guild)):
                    raise ValueError('Персонаж игрока не принадлежит этому серверу.')
            if ident:
                cursor=await conn.execute('UPDATE battle_maps SET name=?,spec=?,published=?,updated_at=CURRENT_TIMESTAMP WHERE id=? AND guild_id=? AND owner_id=?',(spec['name'],json.dumps(spec),int(bool(payload.get('published'))),ident,guild,owner))
                if cursor.rowcount!=1: raise ValueError('Карта не принадлежит этому администратору.')
            else:
                cursor=await conn.execute('INSERT INTO battle_maps(guild_id,owner_id,name,spec,published) VALUES(?,?,?,?,?)',(guild,owner,spec['name'],json.dumps(spec),int(bool(payload.get('published')))))
                ident=cursor.lastrowid
            await conn.commit()
        return ident

    async def delete_map(self,guild,owner,ident):
        async with self.db.connect() as conn:
            cursor=await conn.execute('DELETE FROM battle_maps WHERE id=? AND guild_id=? AND owner_id=?',(ident,guild,owner))
            if cursor.rowcount!=1: raise ValueError('Карта не найдена.')
            await conn.commit()

    async def shop(self,guild,query='',admin=False,shop_key='',category='',quality=''):
        from merchant_rules import SHOPS
        if shop_key and shop_key not in SHOPS:raise ValueError('Неизвестный магазин.')
        await self.ensure_shops(guild)
        from crafting import CraftingStore
        async with self.db.connect() as conn:
            ready=await conn.execute_fetchall("SELECT name FROM sqlite_master WHERE name='crafting_shop_seeded'")
        if ready:await CraftingStore(self.db).ensure_supplies(guild)
        async with self.db.connect() as conn:
            settings=await conn.execute_fetchall('SELECT * FROM shop_settings WHERE guild_id=?',(guild,))
            branch=await conn.execute_fetchall('SELECT name,enabled FROM shop_branches WHERE guild_id=? AND shop_key=?',(guild,shop_key))
            clauses=['guild_id=?','(name LIKE ? OR category LIKE ?)'];values=[guild,'%'+query+'%','%'+query+'%']
            if not admin:clauses.append('shop_stock.enabled=1')
            if shop_key:clauses.append('shop_key=?');values.append(shop_key)
            if category:clauses.append('category=?');values.append(category)
            if quality:clauses.append('quality=?');values.append(quality)
            rows=await conn.execute_fetchall('SELECT item_catalog.*,shop_stock.stock,shop_stock.buy_price,shop_stock.sell_price,shop_stock.enabled,shop_stock.shop_key FROM shop_stock JOIN item_catalog ON item_catalog.id=shop_stock.item_id WHERE '+' AND '.join(clauses)+' ORDER BY name LIMIT 200',values)
            cats=await conn.execute_fetchall('SELECT DISTINCT category FROM shop_stock JOIN item_catalog ON item_catalog.id=item_id WHERE guild_id=?'+(' AND shop_key=?' if shop_key else '')+' ORDER BY category',(guild,shop_key) if shop_key else (guild,))
            config=dict(settings[0]) if settings else {'name':'Имперская лавка','enabled':1}
            if shop_key and shop_key!='custom':config={'name':SHOPS[shop_key]['name'],'enabled':1}
            if branch:config.update(dict(branch[0]))
            return {'settings':config,'items':[dict(row) for row in rows],'shopKey':shop_key,'shops':[{'key':k,**v} for k,v in SHOPS.items()],
                'categories':[r['category'] for r in cats],'qualities':['Обычное','Хорошее','Превосходное','Выдающееся','Безупречное','Артефакт','Добротное','Изысканное','Шедевр']}

    async def edit_shop(self,guild,payload):
        if not isinstance(payload,dict): raise ValueError('Некорректная настройка магазина.')
        async with self.db.connect() as conn:
            if payload.get('action')=='settings':
                key=str(payload.get('shopKey','custom'))
                from merchant_rules import SHOPS
                if key not in SHOPS:raise ValueError('Неизвестный магазин.')
                await conn.execute('INSERT INTO shop_branches VALUES(?,?,?,?) ON CONFLICT(guild_id,shop_key) DO UPDATE SET name=excluded.name,enabled=excluded.enabled',(guild,key,str(payload.get('name',SHOPS[key]['name']))[:100],int(bool(payload.get('enabled',True)))))
            else:
                ident=int(payload.get('itemId',0))
                items=await conn.execute_fetchall('SELECT * FROM item_catalog WHERE id=?',(ident,))
                if not items: raise ValueError('Предмет не найден.')
                from merchant_rules import SHOPS,common_item
                old=await conn.execute_fetchall('SELECT shop_key FROM shop_stock WHERE guild_id=? AND item_id=?',(guild,ident))
                key=str(payload.get('shopKey',old[0]['shop_key'] if old else 'custom'))
                if key not in SHOPS:raise ValueError('Неизвестный магазин.')
                if key!='custom' and not common_item(dict(items[0]),key):raise ValueError('В обычной лавке допустимы только обычные неуникальные товары её категории.')
                stock,buy,sell=(int(payload.get(k,0)) for k in ('stock','buyPrice','sellPrice'))
                if stock < -1 or stock > 999999 or not 0<=sell<=buy<=2_000_000_000: raise ValueError('Проверьте запас и цены. Цена продажи не должна превышать цену покупки.')
                await conn.execute('INSERT INTO shop_stock(guild_id,item_id,stock,buy_price,sell_price,enabled,shop_key) VALUES(?,?,?,?,?,?,?) ON CONFLICT(guild_id,item_id) DO UPDATE SET stock=excluded.stock,buy_price=excluded.buy_price,sell_price=excluded.sell_price,enabled=excluded.enabled,shop_key=excluded.shop_key',(guild,ident,stock,buy,sell,int(bool(payload.get('enabled',True))),key))
            await conn.commit()

    async def sale_offers(self,cid,guild,shop_key=''):
        async with self.db.connect() as conn:
            rows=await conn.execute_fetchall('SELECT DISTINCT shop_stock.item_id AS id,shop_stock.sell_price FROM shop_stock JOIN inventory ON inventory.item_id=shop_stock.item_id WHERE inventory.character_id=? AND shop_stock.guild_id=? AND shop_stock.enabled=1',(cid,guild))
            if shop_key:
                ids={r['item_id'] for r in await conn.execute_fetchall('SELECT item_id FROM shop_stock WHERE guild_id=? AND shop_key=?',(guild,shop_key))}
                rows=[r for r in rows if r['id'] in ids]
            return [dict(row) for row in rows]

    async def trade(self,cid,payload):
        if not isinstance(payload,dict): raise ValueError('Некорректная торговая операция.')
        quantity=int(payload.get('quantity',1))
        if not 1<=quantity<=99: raise ValueError('Количество: 1–99.')
        async with self.db.connect() as conn:
            await conn.execute('BEGIN IMMEDIATE')
            chars=await conn.execute_fetchall('SELECT guild_id FROM characters WHERE id=?',(cid,))
            if not chars: raise ValueError('Персонаж не найден.')
            guild=chars[0]['guild_id']
            settings=await conn.execute_fetchall('SELECT enabled FROM shop_settings WHERE guild_id=?',(guild,))
            await conn.execute('INSERT OR IGNORE INTO wallets VALUES(?,0)',(cid,))
            if payload.get('action')=='buy':
                ident=int(payload.get('itemId',0))
            elif payload.get('action')=='sell':
                inv=await conn.execute_fetchall('SELECT * FROM inventory WHERE character_id=? AND id=?',(cid,int(payload.get('inventoryId',0))))
                if not inv or inv[0]['equipped_slot'] or inv[0]['quantity']<quantity: raise ValueError('Сначала снимите предмет; количество должно быть доступно.')
                ident=inv[0]['item_id']
            else: raise ValueError('Неизвестная торговая операция.')
            rows=await conn.execute_fetchall('SELECT item_catalog.*,shop_stock.stock,shop_stock.buy_price,shop_stock.sell_price,shop_stock.shop_key FROM shop_stock JOIN item_catalog ON item_catalog.id=item_id WHERE guild_id=? AND item_id=? AND enabled=1',(guild,ident))
            if not rows: raise ValueError('Магазин не торгует этим предметом.')
            item=rows[0]
            key=str(payload.get('shopKey',''))
            if key and key!=item['shop_key']:raise ValueError('Предмет не продаётся в выбранной лавке.')
            branch=await conn.execute_fetchall('SELECT enabled FROM shop_branches WHERE guild_id=? AND shop_key=?',(guild,item['shop_key']))
            if item['shop_key']=='custom' and not branch and settings and not settings[0]['enabled']:raise ValueError('Магазин закрыт.')
            if branch and not branch[0]['enabled']:raise ValueError('Магазин закрыт.')
            if payload['action']=='buy':
                cost=item['buy_price']*quantity
                balance=(await conn.execute_fetchall('SELECT copper FROM wallets WHERE character_id=?',(cid,)))[0]['copper']
                if cost>balance: raise ValueError('Недостаточно колец.')
                if item['stock']!=-1 and quantity>item['stock']: raise ValueError('Недостаточный запас в лавке.')
                stackable=item['category'] in {'Расходуемые предметы','Зелья','Еда','Материалы','Сигилы'}
                existing=await conn.execute_fetchall('SELECT id FROM inventory WHERE character_id=? AND item_id=? AND equipped_slot IS NULL',(cid,ident))
                inventory=await conn.execute_fetchall('SELECT item_catalog.name,item_catalog.category,item_catalog.weight,inventory.equipped_slot FROM inventory JOIN item_catalog ON item_catalog.id=item_id WHERE character_id=?',(cid,))
                athletics=await conn.execute_fetchall("SELECT value FROM skills WHERE character_id=? AND name='Атлетика'",(cid,))
                capacity=min(40,8+(athletics[0]['value'] if athletics else 0)//5)
                used=sum(self.db._item_consumes_slot(r['name'],r['category'],r['weight'],r['equipped_slot']) for r in inventory)
                needed=0 if (stackable and existing) or not self.db._item_consumes_slot(item['name'],item['category'],item['weight']) else (1 if stackable else quantity)
                if used+needed>capacity: raise ValueError('Недостаточно места в инвентаре.')
                if stackable and existing:
                    await conn.execute('UPDATE inventory SET quantity=quantity+? WHERE id=?',(quantity,existing[0]['id']))
                else:
                    await conn.executemany('INSERT INTO inventory(character_id,item_id,quantity) VALUES(?,?,?)',[(cid,ident,quantity)] if stackable else [(cid,ident,1)]*quantity)
                await conn.execute('UPDATE wallets SET copper=copper-? WHERE character_id=?',(cost,cid))
                await conn.execute('UPDATE shop_stock SET stock=stock-? WHERE guild_id=? AND item_id=? AND stock>=0',(quantity,guild,ident))
                amount=-cost
            else:
                amount=item['sell_price']*quantity
                if inv[0]['quantity']==quantity: await conn.execute('DELETE FROM inventory WHERE id=?',(inv[0]['id'],))
                else: await conn.execute('UPDATE inventory SET quantity=quantity-? WHERE id=?',(quantity,inv[0]['id']))
                await conn.execute('UPDATE wallets SET copper=copper+? WHERE character_id=?',(amount,cid))
                await conn.execute('UPDATE shop_stock SET stock=stock+? WHERE guild_id=? AND item_id=? AND stock>=0',(quantity,guild,ident))
            await conn.execute('INSERT INTO commerce_log(character_id,guild_id,operation,item_id,quantity,amount) VALUES(?,?,?,?,?,?)',(cid,guild,payload['action'],ident,quantity,amount))
            await conn.commit()
        return 'Покупка совершена.' if payload['action']=='buy' else 'Предмет продан.'
