import json,asyncio
from pathlib import Path
from datetime import datetime,timedelta,timezone
from test_campaign import CampaignTests
from crafting import CraftingStore,SCHEMA,ORIGIN,library,normalize_quality,upgrade_recipe,quality_info
from registration_api import portal_crafting
from aiohttp import web
from aiohttp.test_utils import TestClient,TestServer

class CraftTests(CampaignTests):
    async def setup_crafter(self):
        async with self.db.connect() as c:
            await c.executescript(SCHEMA)
            await c.execute('UPDATE characters SET background=? WHERE id=1',(ORIGIN,));await c.commit()
        rows=json.loads(Path('catalog/game_items.json').read_text(encoding='utf-8'))
        await self.db.upsert_catalog([normalize_quality(i) for i in rows])
        await self.store.set_wallet(1,1000000)
        self.craft=CraftingStore(self.db)
    async def give_materials(self,ingredients):
        async with self.db.connect() as c:items=await self.craft._items(c)
        for x in ingredients:await self.db.admin_give_item(1,items[x['prefab']]['name'],x['quantity']*2)
    async def complete(self):
        async with self.db.connect() as c:
            await c.execute('UPDATE crafting_jobs SET ready_at=?',((datetime.now(timezone.utc)-timedelta(seconds=1)).isoformat(),));await c.commit()
    async def test_recipes_locked_and_class_gate(self):
        await self.setup_crafter()
        snapshot=await self.craft.snapshot(1)
        self.assertEqual(len(snapshot['recipes']),28)
        self.assertEqual(sum(not r['known'] for r in snapshot['recipes']),18)
        locked=next(r for r in snapshot['recipes'] if not r['known'])
        with self.assertRaises(ValueError):await self.craft.act(1,{'action':'craft','recipeKey':locked['key']})
        async with self.db.connect() as c:items=await self.craft._items(c)
        await self.db.admin_give_item(1,items[locked['scrolls'][0]]['name'])
        scroll=next(s for s in (await self.craft.snapshot(1))['scrolls'] if locked['key'] in s['recipes'])
        await self.craft.act(1,{'action':'learn','inventoryId':scroll['inventoryId']})
        self.assertTrue(next(r for r in (await self.craft.snapshot(1))['recipes'] if r['key']==locked['key'])['known'])
        async with self.db.connect() as c:
            await c.execute("UPDATE characters SET background='Книгочей' WHERE id=1");await c.commit()
        with self.assertRaises(ValueError):await self.craft.snapshot(1)
    async def test_crafting_atomic_queue_and_claim_once(self):
        await self.setup_crafter();r=next(r for r in library()['recipes'] if r['key']=='Potion_Health_Common')
        before=(await self.store.wallet(1))['totalCopper']
        with self.assertRaises(ValueError):await self.craft.act(1,{'action':'craft','recipeKey':r['key']})
        self.assertEqual((await self.store.wallet(1))['totalCopper'],before)
        await self.give_materials(r['ingredients'])
        responses=await asyncio.gather(*(self.craft.act(1,{'action':'craft','recipeKey':r['key']}) for _ in range(2)),return_exceptions=True)
        self.assertEqual(sum(not isinstance(x,Exception) for x in responses),1)
        self.assertEqual((await self.store.wallet(1))['totalCopper'],before-r['cost'])
        job=(await self.craft.snapshot(1))['jobs'][0]
        with self.assertRaises(ValueError):await self.craft.act(1,{'action':'claim','jobId':job['id']})
        await self.complete();await self.craft.act(1,{'action':'claim','jobId':job['id']})
        with self.assertRaises(ValueError):await self.craft.act(1,{'action':'claim','jobId':job['id']})
    async def test_upgrade_private_quality_and_item_reservation(self):
        await self.setup_crafter()
        rows=await self.db.catalog_search(limit=100)
        item=next(i for i in rows if upgrade_recipe(i))
        await self.db.admin_give_item(1,item['name']);inv=next(i for i in await self.db.inventory(1) if i['id']==item['id'])
        recipe=upgrade_recipe(inv);await self.give_materials(recipe['ingredients'])
        await self.craft.act(1,{'action':'upgrade','inventoryId':inv['inventory_id']})
        self.assertFalse(await self.db.unequip(1,inv['inventory_id']))
        self.assertFalse(await self.db.remove_item(1,inv['inventory_id']))
        self.assertFalse((await self.db.equip(1,inv['inventory_id'],'Торс'))[0])
        await self.complete();job=(await self.craft.snapshot(1))['jobs'][0]
        await self.craft.act(1,{'action':'claim','jobId':job['id']})
        result=next(i for i in await self.db.inventory(1) if i['inventory_id']==inv['inventory_id'])
        self.assertIsNone(result['equipped_slot'])
        self.assertNotEqual(result['id'],item['id'])
        self.assertEqual(quality_info(result)['level'],recipe['to'])
        original=next(i for i in await self.db.catalog_search(item['name']) if i['id']==item['id'])
        self.assertEqual(original['quality'],item['quality'])

    async def test_portal_and_material_recipe_shop(self):
        await self.setup_crafter();await self.craft.ensure_supplies(1)
        shop=await self.store.shop(1,shop_key='custom')
        self.assertTrue(any(i['category']=='Материалы' for i in shop['items']))
        self.assertTrue(any(i['name'].startswith('Рецепт:') for i in shop['items']))
        self.assertTrue(all(i['category'] in {'Материалы','Чертежи','Прочее'} for i in shop['items']))
        first=shop['items'][0]
        await self.store.edit_shop(1,{'itemId':first['id'],'stock':3,'buyPrice':5,'sellPrice':2})
        await self.craft.ensure_supplies(1)
        self.assertEqual(next(i['stock'] for i in (await self.store.shop(1,shop_key='custom'))['items'] if i['id']==first['id']),3)
        app=web.Application();app['db']=self.db;app.router.add_get('/api/portal/{token}/crafting',portal_crafting)
        token=await self.db.create_portal_token(1,1)
        async with TestClient(TestServer(app)) as client:
            self.assertEqual((await client.get('/api/portal/invalid/crafting')).status,410)
            r=await client.get(f'/api/portal/{token}/crafting');self.assertEqual(r.status,200)
            j=await r.json();self.assertEqual(len(j['recipes']),28)
            self.assertIsInstance(j['recipes'][0]['outputItem']['properties'],dict)
            self.assertIn('gameData',j['recipes'][0]['outputItem']['properties'])
