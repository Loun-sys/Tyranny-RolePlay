import asyncio,copy,json,tempfile,unittest
from pathlib import Path
from database import Database,SCHEMA as BASE_SCHEMA
from campaign_store import SCHEMA as CAMPAIGN_SCHEMA,CampaignStore
from player_possessions import SCHEMA,STARTS,SPECIALIZATION_STARTS,starting_items,operate,grant_start
from item_texts import catalog_texts
from registration_api import _validate_payload,_configuration

class PossessionTests(unittest.IsolatedAsyncioTestCase):
    def test_beast_registration_bonus_and_no_initial_cap(self):
        from constants import SKILLS,ATTRIBUTES,SPECIALIZATION_ABILITIES
        payload={'name':'Зверь','background':'Зверолюд','specialization1':'Меч и щит','specialization2':'Дротик','attributes':dict.fromkeys(ATTRIBUTES,8),'skills':dict.fromkeys(SKILLS,0)}
        payload['attributes']['Сила']=32;payload['skills']['Атлетика']=20
        self.assertIsNotNone(_validate_payload(payload)[0])
        payload['background']='Книгочей';self.assertIsNone(_validate_payload(payload)[0])
    async def asyncSetUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.db=Database(Path(self.tmp.name)/'qa.db')
        async with self.db.connect() as conn:
            await conn.executescript(BASE_SCHEMA+CAMPAIGN_SCHEMA+SCHEMA)
            for cid,guild in [(1,1),(2,1),(3,2)]:
                await conn.execute("INSERT INTO characters(id,guild_id,user_id,name,background,specialization_1,specialization_2) VALUES(?,?,?,'Герой','Книгочей','Меч и щит','Дротик')",(cid,guild,cid))
            await conn.execute("INSERT INTO skills(character_id,name,value) VALUES(2,'Атлетика',20)")
            await conn.commit()
        prefabs={k for _,items in STARTS.values() for k,_ in items}
        prefabs.update(k for items in SPECIALIZATION_STARTS.values() for k,_ in items)
        await self.db.upsert_catalog([copy.deepcopy(catalog_texts()[0][k]) for k in prefabs])
    async def asyncTearDown(self):self.tmp.cleanup()
    async def test_every_start_exactly_once(self):
        for n,(origin,(coins,items)) in enumerate(STARTS.items(),10):
            cid=await self.db.create_character(1,n,origin,origin,'Меч и щит','Дротик')
            before=await self.db.inventory(cid)
            self.assertEqual(sum(i['quantity'] for i in before),sum(q for _,q in starting_items(origin,('Меч и щит','Дротик'))))
            self.assertEqual((await CampaignStore(self.db).wallet(cid))['totalCopper'],coins)
            self.assertEqual((await self.db.get_character_by_id(cid))['attribute_points'],4 if origin=='Зверолюд' else 0)
            async with self.db.connect() as conn:await grant_start(conn,cid,origin);await conn.commit()
            self.assertEqual(await self.db.inventory(cid),before)
            self.assertEqual((await CampaignStore(self.db).wallet(cid))['totalCopper'],coins)
    async def test_beast_limits_and_armor(self):
        cid=await self.db.create_character(1,20,'Зверь','Зверолюд','Меч и щит','Дротик')
        await self.db.set_attribute(cid,'Сила',30)
        async with self.db.connect() as conn:await conn.execute('UPDATE characters SET attribute_points=10 WHERE id=?',(cid,));await conn.commit()
        self.assertTrue((await self.db.spend_attribute_point(cid,'Сила'))[0])
        self.assertEqual((await self.db.get_character_by_id(cid))['attributes']['Сила'],31)
        await self.db.admin_give_item(cid,'Одежда из ткани')
        inv=next(i for i in await self.db.inventory(cid) if i['name']=='Одежда из ткани')
        self.assertFalse((await self.db.equip(cid,inv['inventory_id'],'Торс'))[0])
        normal=await self.db.create_character(1,21,'Человек','Книгочей','Меч и щит','Дротик')
        await self.db.set_attribute(normal,'Сила',100)
        self.assertEqual((await self.db.get_character_by_id(normal))['attributes']['Сила'],30)
    def test_all_specialization_kits_are_normal_game_items(self):
        from constants import SPECIALIZATIONS
        self.assertEqual(set(SPECIALIZATION_STARTS),set(SPECIALIZATIONS))
        for specialization,items in SPECIALIZATION_STARTS.items():
            for prefab,quantity in items:
                row=catalog_texts()[0][prefab]
                self.assertEqual(row['quality'],'Обычное',specialization)
                self.assertTrue(row['image_url'],specialization)
                self.assertLessEqual(row['value'],375,specialization)
        self.assertEqual(SPECIALIZATION_STARTS['Безоружные атаки'],[])
        self.assertEqual(SPECIALIZATION_STARTS['Парное оружие'],[('WPN_1H_Starter_Dagger',2)])
        for origin,(_,items) in STARTS.items():
            weapons=[key for key,_ in items if key.startswith('WPN_')]
            self.assertEqual(weapons,['WPN_1H_IR_Dagger_Lantry'] if origin=='Книгочей' else [],origin)
    async def test_both_specializations_grant_exact_weapon_kits(self):
        from collections import Counter
        specs=list(SPECIALIZATION_STARTS)
        for n,first in enumerate(specs,100):
            second=specs[(n-100+1)%len(specs)]
            cid=await self.db.create_character(1,n,'Испытатель','Заклинатель',first,second)
            expected=Counter({catalog_texts()[0][prefab]['name']:q for prefab,q in starting_items('Заклинатель',(first,second))})
            actual=Counter()
            for item in await self.db.inventory(cid):actual[item['name']]+=item['quantity']
            self.assertEqual(actual,expected,(first,second))
    async def test_existing_characters_are_not_regranted_or_stripped(self):
        cid=await self.db.create_character(1,200,'Хранитель','Книгочей','Парное оружие','Заклинания рвения')
        await self.db.admin_give_item(cid,'Бронзовый меч')
        before=await self.db.inventory(cid)
        async with self.db.connect() as conn:
            await conn.execute("UPDATE characters SET specialization_1='Короткий лук',specialization_2='Заклинания льда' WHERE id=?",(cid,))
            await grant_start(conn,cid,'Книгочей');await conn.commit()
        self.assertEqual(await self.db.inventory(cid),before)
        self.assertEqual((await CampaignStore(self.db).wallet(cid))['totalCopper'],300)
    async def test_money_atomic_transfer_destroy_and_scope(self):
        store=CampaignStore(self.db);await store.set_wallet(1,300)
        results=await asyncio.gather(*(operate(self.db,1,{'action':'transfer','kind':'money','quantity':200,'recipientId':2}) for _ in range(2)),return_exceptions=True)
        self.assertEqual(sum(isinstance(r,ValueError) for r in results),1)
        self.assertEqual((await store.wallet(1))['totalCopper'],100);self.assertEqual((await store.wallet(2))['totalCopper'],200)
        for target in [1,3,999]:
            with self.assertRaises(ValueError):await operate(self.db,1,{'action':'transfer','kind':'money','quantity':1,'recipientId':target})
        with self.assertRaises(ValueError):await operate(self.db,1,{'action':'destroy','kind':'money','quantity':1})
        await operate(self.db,1,{'action':'destroy','kind':'money','quantity':50,'confirmed':True})
        self.assertEqual((await store.wallet(1))['totalCopper'],50)
    async def test_partial_item_transfer_and_destroy(self):
        await self.db.admin_give_item(1,'Железный слиток',10)
        ident=(await self.db.inventory(1))[0]['inventory_id']
        await operate(self.db,1,{'action':'transfer','kind':'item','quantity':4,'recipientId':2,'inventoryId':ident})
        self.assertEqual((await self.db.inventory(1))[0]['quantity'],6);self.assertEqual((await self.db.inventory(2))[0]['quantity'],4)
        with self.assertRaises(ValueError):await operate(self.db,2,{'action':'destroy','kind':'item','quantity':1,'inventoryId':ident,'confirmed':True})
        await operate(self.db,1,{'action':'destroy','kind':'item','quantity':6,'inventoryId':ident,'confirmed':True})
        self.assertFalse(await self.db.inventory(1))
    async def test_equipped_item_must_be_removed(self):
        await self.db.admin_give_item(1,'Одежда из ткани')
        ident=(await self.db.inventory(1))[0]['inventory_id'];self.assertTrue((await self.db.equip(1,ident,'Торс'))[0])
        for action in ['transfer','destroy']:
            with self.assertRaises(ValueError):await operate(self.db,1,{'action':action,'kind':'item','quantity':1,'recipientId':2,'inventoryId':ident,'confirmed':True})
        await self.db.admin_update_character(1,{'background':'Зверолюд'})
        self.assertIsNone((await self.db.inventory(1))[0]['equipped_slot'])
    async def test_full_recipient_inventory_rolls_back(self):
        await self.db.admin_give_item(2,'Бронзовый меч',12);await self.db.admin_give_item(1,'Бронзовый меч')
        ident=(await self.db.inventory(1))[0]['inventory_id']
        with self.assertRaises(ValueError):await operate(self.db,1,{'action':'transfer','kind':'item','quantity':1,'recipientId':2,'inventoryId':ident})
        self.assertEqual(len(await self.db.inventory(1)),1);self.assertEqual(len(await self.db.inventory(2)),12)
    async def test_negative_and_fractional_amounts_rejected(self):
        for value in [0,-1,1.5,True,'abc']:
            with self.assertRaises(ValueError):await operate(self.db,1,{'action':'destroy','kind':'money','quantity':value,'confirmed':True})
    async def test_portal_endpoint_rejects_forged_tokens(self):
        from aiohttp import web
        from aiohttp.test_utils import TestClient,TestServer
        from registration_api import portal_possessions,cors_middleware
        app=web.Application(middlewares=[cors_middleware]);app['db']=self.db
        app.router.add_post('/api/portal/{token}/possessions',portal_possessions)
        async with TestClient(TestServer(app)) as client:
            response=await client.post('/api/portal/invalid/possessions',json={'action':'destroy','kind':'money','quantity':10,'confirmed':True})
            self.assertEqual(response.status,410)

class LegacyAttributeTests(unittest.IsolatedAsyncioTestCase):
    async def test_legacy_attribute_constraint_is_migrated_without_data_loss(self):
        with tempfile.TemporaryDirectory() as folder:
            db=Database(Path(folder)/'legacy.db')
            async with db.connect() as conn:
                await conn.executescript(BASE_SCHEMA.replace('CHECK(value >= 1)','CHECK(value BETWEEN 1 AND 30)'))
                await conn.execute("INSERT INTO characters(id,guild_id,user_id,name,background,specialization_1,specialization_2) VALUES(1,1,1,'Зверь','Зверолюд','Меч и щит','Дротик')")
                from constants import ATTRIBUTES
                await conn.executemany('INSERT INTO attributes VALUES(1,?,30)',[(n,) for n in ATTRIBUTES]);await conn.commit()
            await db.initialize()
            c=await db.get_character_by_id(1);self.assertEqual(c['attributes']['Сила'],30)
            await db.set_attribute(1,'Сила',31)
            self.assertEqual((await db.get_character_by_id(1))['attributes']['Сила'],31)

if __name__=='__main__':unittest.main()
