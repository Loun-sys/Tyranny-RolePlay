import json
from pathlib import Path
from test_campaign import CampaignTests
from merchant_rules import common_item,reliable_icon,SHOPS
from catalog_browser import browse
from registration_api import admin_catalog,admin_shop,portal_shop,_clean_inventory
from aiohttp import web
from aiohttp.test_utils import TestClient,TestServer

class ShopTests(CampaignTests):
    async def seed(self):
        rows=json.loads(Path('catalog/game_items.json').read_text(encoding='utf-8'))
        await self.db.upsert_catalog(rows)
        await self.store.ensure_shops(1)

    async def test_starter_stores_and_icons(self):
        await self.seed()
        for key,cap in [('consumables',15),('weapons',10),('armor',12)]:
            s=await self.store.shop(1,shop_key=key)
            self.assertGreater(len(s['items']),0)
            self.assertLessEqual(len(s['items']),cap)
            for i in s['items']:
                self.assertTrue(common_item(i,key))
                self.assertTrue(10<=i['stock']<=15 if key=='consumables' else 3<=i['stock']<=5)
                path,_=reliable_icon(i)
                self.assertTrue((Path('web')/path).is_file())
                self.assertNotEqual(i['category'],'Аксессуары')
        self.assertNotIn('accessories',SHOPS)
        async with self.db.connect() as c:
            rows=await c.execute_fetchall('SELECT * FROM item_catalog')
        for i in _clean_inventory([dict(r) for r in rows]):
            self.assertTrue((Path('web')/i['image_url']).is_file(),i['name'])

    async def test_stock_does_not_refill_and_shop_boundary(self):
        await self.seed();s=await self.store.shop(1,shop_key='consumables');i=s['items'][0]
        await self.store.set_wallet(1,1000000)
        with self.assertRaises(ValueError):
            await self.store.trade(1,{'action':'buy','itemId':i['id'],'shopKey':'armor'})
        await self.store.trade(1,{'action':'buy','itemId':i['id'],'shopKey':'consumables'})
        await self.store.ensure_shops(1)
        s=await self.store.shop(1,shop_key='consumables')
        self.assertEqual(next(r['stock'] for r in s['items'] if r['id']==i['id']),i['stock']-1)
        await self.store.edit_shop(1,{'action':'settings','shopKey':'armor','enabled':False})
        await self.store.trade(1,{'action':'buy','itemId':i['id'],'shopKey':'consumables'})
        armor=(await self.store.shop(1,shop_key='armor'))['items'][0]
        with self.assertRaises(ValueError):
            await self.store.trade(1,{'action':'buy','itemId':armor['id'],'shopKey':'armor'})

    async def test_catalog_filters_pagination_and_custom_preserved(self):
        await self.store.edit_shop(1,{'itemId':1,'stock':7,'buyPrice':100,'sellPrice':50})
        await self.seed()
        self.assertEqual((await self.store.shop(1,shop_key='custom'))['items'][0]['stock'],7)
        result=await browse(self.db,category='Броня',quality='Обычное')
        self.assertGreater(result['total'],50)
        self.assertTrue(all(i['category']=='Броня' and i['quality']=='Обычное' for i in result['items']))
        page=await browse(self.db,category='Броня',quality='Обычное',offset=50)
        self.assertFalse({i['id'] for i in page['items']} & {i['id'] for i in result['items']})
        price=await browse(self.db,min_price=0,max_price=100,sort='price_desc')
        self.assertTrue(all(i['value']<=100 for i in price['items']))

    async def test_legacy_shop_migration(self):
        async with self.db.connect() as c:
            await c.execute('DROP TABLE shop_stock')
            await c.execute('CREATE TABLE shop_stock(guild_id INTEGER,item_id INTEGER,stock INTEGER,buy_price INTEGER,sell_price INTEGER,enabled INTEGER,PRIMARY KEY(guild_id,item_id))')
            await c.execute('INSERT INTO shop_stock VALUES(1,1,7,100,50,1)')
            await c.commit()
        await self.db.initialize()
        async with self.db.connect() as c:
            row=(await c.execute_fetchall('SELECT stock,shop_key FROM shop_stock WHERE guild_id=1 AND item_id=1'))[0]
        self.assertEqual(row['stock'],7)
        self.assertEqual(row['shop_key'],'custom')

    async def test_shop_routes(self):
        await self.seed();await self.store.set_wallet(1,1000000)
        app=web.Application();app['db']=self.db
        app.router.add_get('/api/admin/{token}/catalog',admin_catalog)
        app.router.add_get('/api/admin/{token}/shop',admin_shop)
        app.router.add_get('/api/portal/{token}/shop',portal_shop)
        app.router.add_post('/api/portal/{token}/shop',portal_shop)
        admin=await self.db.create_admin_token(1,10)
        portal=await self.db.create_portal_token(1,1)
        async with TestClient(TestServer(app)) as client:
            r=await client.get(f'/api/admin/{admin}/catalog?category=Аксессуары')
            self.assertEqual(r.status,200);j=await r.json();self.assertGreater(j['total'],0)
            self.assertTrue(all(i['category']=='Аксессуары' for i in j['items']))
            r=await client.get(f'/api/portal/{portal}/shop?shopKey=weapons');self.assertEqual(r.status,200)
            j=await r.json();i=j['items'][0]
            r=await client.post(f'/api/portal/{portal}/shop?shopKey=weapons',json={'action':'buy','shopKey':'weapons','itemId':i['id'],'quantity':1})
            self.assertEqual(r.status,200)
            j=await r.json();self.assertEqual(j['shopKey'],'weapons')
            self.assertEqual(next(x['stock'] for x in j['items'] if x['id']==i['id']),i['stock']-1)
            r=await client.get(f'/api/portal/{portal}/shop?shopKey=accessories');self.assertEqual(r.status,400)
