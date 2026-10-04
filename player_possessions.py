"""Atomic starting grants, player transfers and explicit destruction."""

SCHEMA="""
CREATE TABLE IF NOT EXISTS starting_grants(character_id INTEGER PRIMARY KEY REFERENCES characters(id) ON DELETE CASCADE);
CREATE TABLE IF NOT EXISTS possession_log(id INTEGER PRIMARY KEY, sender_id INTEGER NOT NULL, recipient_id INTEGER, kind TEXT NOT NULL, amount INTEGER NOT NULL, item_id INTEGER, created_at TEXT DEFAULT CURRENT_TIMESTAMP);
"""
STARTS={
 'Книгочей':(300,[('WPN_1H_IR_Dagger_Lantry',1),('Cloth_Armor_Lantry',1),('Cloth_GLOVE_Lantry',1),('Cloth_BOOTS_Lantry',1)]),
 'Заклинатель':(200,[('Cloth_Armor_MageRobes_01',1)]),
 'Зверолюд':(0,[]),
 'Певчий':(300,[('Cloth_Armor_MageRobes_01',1)]),
 'Танцующий':(200,[('Leather_Armor_02',1)]),
 'Авангард':(300,[('Bronze_Armor_02',1)]),
 'Скованный Ремеслом':(600,[('Cloth_Armor_MageRobes_01',1),('RES_SkyPillar_Ingot_Iron',10),('RES_SkyPillar_Ingot_Bronze',10),('RES_SkyPillar_Hide',10),('RES_SkyPillar_AlchemySupplies',15)]),
}
SPECIALIZATION_STARTS={
 'Меч и щит':[('WPN_1H_Starter_Sword',1),('WPN_SHLD_Starter_Buckler_Quartermaster_Store',1)],
 'Двуручный меч':[('WPN_2H_Starter_Sword',1)],
 'Короткий лук':[('WPN_BOW_WD_Shortbow_Starting',1)],
 'Заклинания молний':[('WPN_STF_WD_Staff_Starting_Shock',1)],
 'Заклинания рвения':[('WPN_STF_WD_Staff_Starting_Strength',1)],
 'Дротик':[('WPN_1H_Starter_Javelin',1)],
 'Парное оружие':[('WPN_1H_Starter_Dagger',2)],
 'Безоружные атаки':[],
 'Заклинания льда':[('WPN_STF_WD_Staff_Starting_Frost',1)],
 'Заклинания истощения':[('WPN_STF_WD_Staff_Starting_Weakness',1)],
}
STACKABLE={'Расходуемые предметы','Зелья','Еда','Материалы','Сигилы'}

def starting_items(background,specializations):
    """Class supplies plus both distinct specialization weapon kits."""
    items=dict(STARTS.get(background,(0,[]))[1])
    for specialization in dict.fromkeys(specializations):
        for prefab,quantity in SPECIALIZATION_STARTS.get(specialization,[]):
            items[prefab]=items.get(prefab,0)+quantity
    return list(items.items())

async def grant_start(conn,cid,background,allocate_start_bonus=True):
    if await conn.execute_fetchall('SELECT 1 FROM starting_grants WHERE character_id=?',(cid,)):return
    from item_texts import catalog_texts
    rows=await conn.execute_fetchall('SELECT specialization_1,specialization_2 FROM characters WHERE id=?',(cid,))
    if not rows:raise ValueError('Персонаж не найден.')
    coins=STARTS.get(background,(0,[]))[0]
    items=starting_items(background,(rows[0]['specialization_1'],rows[0]['specialization_2']))
    for prefab,quantity in items:
        name=catalog_texts()[0][prefab]['name']
        rows=await conn.execute_fetchall('SELECT id,category FROM item_catalog WHERE name=?',(name,))
        if not rows:raise ValueError('В каталоге отсутствует стартовый предмет: '+name)
        item=rows[0]
        await conn.executemany('INSERT INTO inventory(character_id,item_id,quantity) VALUES(?,?,?)',[(cid,item['id'],quantity)] if item['category'] in STACKABLE else [(cid,item['id'],1)]*quantity)
    await conn.execute('INSERT INTO wallets VALUES(?,?) ON CONFLICT(character_id) DO UPDATE SET copper=copper+excluded.copper',(cid,coins))
    if background=='Зверолюд' and allocate_start_bonus:await conn.execute('UPDATE characters SET attribute_points=attribute_points+4 WHERE id=?',(cid,))
    await conn.execute('INSERT INTO starting_grants VALUES(?)',(cid,))

async def recipients(db,cid):
    async with db.connect() as conn:
        return [dict(r) for r in await conn.execute_fetchall('SELECT id,name,background FROM characters WHERE guild_id=(SELECT guild_id FROM characters WHERE id=?) AND id<>? ORDER BY name',(cid,cid))]

def positive(value):
    if isinstance(value,bool):raise ValueError('Укажите целое положительное количество.')
    try:result=int(value)
    except (TypeError,ValueError):raise ValueError('Укажите целое положительное количество.')
    if str(value)!=str(result) or not 1<=result<=2_000_000_000:raise ValueError('Укажите целое положительное количество.')
    return result

async def operate(db,cid,payload):
    if not isinstance(payload,dict):raise ValueError('Некорректные данные операции.')
    action=payload.get('action');kind=payload.get('kind')
    if action not in {'transfer','destroy'} or kind not in {'item','money'}:raise ValueError('Неизвестная операция.')
    if action=='destroy' and payload.get('confirmed') is not True:raise ValueError('Подтвердите уничтожение.')
    quantity=positive(payload.get('quantity'))
    async with db.connect() as conn:
        await conn.execute('BEGIN IMMEDIATE')
        actor=await conn.execute_fetchall('SELECT guild_id FROM characters WHERE id=?',(cid,))
        if not actor:raise ValueError('Персонаж не найден.')
        recipient=None
        if action=='transfer':
            recipient=positive(payload.get('recipientId'))
            target=await conn.execute_fetchall('SELECT id FROM characters WHERE id=? AND guild_id=? AND id<>?',(recipient,actor[0]['guild_id'],cid))
            if not target:raise ValueError('Выберите другого персонажа этого сервера.')
        item_id=None
        if kind=='money':
            await conn.execute('INSERT OR IGNORE INTO wallets VALUES(?,0)',(cid,))
            balance=(await conn.execute_fetchall('SELECT copper FROM wallets WHERE character_id=?',(cid,)))[0]['copper']
            if quantity>balance:raise ValueError('Недостаточно колец.')
            await conn.execute('UPDATE wallets SET copper=copper-? WHERE character_id=?',(quantity,cid))
            if recipient:await conn.execute('INSERT INTO wallets VALUES(?,?) ON CONFLICT(character_id) DO UPDATE SET copper=copper+excluded.copper',(recipient,quantity))
            label=f'{quantity} медных колец'
        else:
            ident=positive(payload.get('inventoryId'))
            rows=await conn.execute_fetchall('SELECT inventory.*,item_catalog.name,item_catalog.category,item_catalog.weight FROM inventory JOIN item_catalog ON item_catalog.id=item_id WHERE inventory.id=? AND character_id=?',(ident,cid))
            if not rows or rows[0]['quantity']<quantity:raise ValueError('Предмет или количество недоступны.')
            item=rows[0];item_id=item['item_id'];label=f"{item['name']} ×{quantity}"
            if item['equipped_slot']:raise ValueError('Сначала снимите предмет с экипировки или быстрого слота.')
            if recipient:
                existing=await conn.execute_fetchall('SELECT id FROM inventory WHERE character_id=? AND item_id=? AND equipped_slot IS NULL',(recipient,item_id))
                stackable=item['category'] in STACKABLE
                inventory=await conn.execute_fetchall('SELECT inventory.equipped_slot,item_catalog.name,item_catalog.category,item_catalog.weight FROM inventory JOIN item_catalog ON item_catalog.id=item_id WHERE character_id=?',(recipient,))
                capacity=min(40,8+(await db.effective_skill_in_connection(conn,recipient,'Атлетика'))//5)
                used=sum(db._item_consumes_slot(r['name'],r['category'],r['weight'],r['equipped_slot']) for r in inventory)
                needed=0 if (stackable and existing) or not db._item_consumes_slot(item['name'],item['category'],item['weight']) else 1 if stackable else quantity
                if used+needed>capacity:raise ValueError('У получателя недостаточно места в инвентаре.')
                if stackable and existing:await conn.execute('UPDATE inventory SET quantity=quantity+? WHERE id=?',(quantity,existing[0]['id']))
                else:await conn.executemany('INSERT INTO inventory(character_id,item_id,quantity) VALUES(?,?,?)',[(recipient,item_id,quantity)] if stackable else [(recipient,item_id,1)]*quantity)
            if item['quantity']==quantity:await conn.execute('DELETE FROM inventory WHERE id=?',(ident,))
            else:await conn.execute('UPDATE inventory SET quantity=quantity-? WHERE id=?',(quantity,ident))
        await conn.execute('INSERT INTO possession_log(sender_id,recipient_id,kind,amount,item_id) VALUES(?,?,?,?,?)',(cid,recipient,action+':'+kind,quantity,item_id))
        await conn.commit()
    return ('Передано: ' if recipient else 'Уничтожено: ')+label
