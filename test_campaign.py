import asyncio
import tempfile
import unittest
from pathlib import Path
from database import Database, SCHEMA as BASE_SCHEMA
from campaign_store import CampaignStore, SCHEMA, money, validate_map
from persistent_spells import persistent_profile
from tactical_grid import TacticalGrid
from training_combat import TrainingSession
from registration_api import _derived
from registration_api import admin_maps,admin_wallet,portal_shop
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer


class CampaignTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.db=Database(Path(self.temp.name)/'test.db')
        async with self.db.connect() as conn:
            await conn.executescript(BASE_SCHEMA+SCHEMA)
            await conn.execute("INSERT INTO characters(guild_id,user_id,name,background,specialization_1,specialization_2) VALUES(1,1,'Герой','Книгочей','Меч и щит','Дротик')")
            await conn.execute("INSERT INTO item_catalog(name,category,value,weight) VALUES('Зелье','Зелья',100,1)")
            await conn.commit()
        self.store=CampaignStore(self.db)

    async def asyncTearDown(self): self.temp.cleanup()

    async def test_atomic_last_item_and_sale(self):
        await self.store.set_wallet(1,10100)
        await self.store.edit_shop(1,{'itemId':1,'stock':1,'buyPrice':100,'sellPrice':50})
        results=await asyncio.gather(*(self.store.trade(1,{'action':'buy','itemId':1}) for _ in range(2)),return_exceptions=True)
        self.assertEqual(sum(not isinstance(r,Exception) for r in results),1)
        self.assertEqual((await self.store.wallet(1))['totalCopper'],10000)
        inv=await self.db.inventory(1)
        await self.store.trade(1,{'action':'sell','inventoryId':inv[0]['inventory_id']})
        self.assertEqual((await self.store.wallet(1))['totalCopper'],10050)
        with self.assertRaises(ValueError): await self.store.trade(1,{'action':'sell','inventoryId':999})
        self.assertEqual((await self.store.wallet(1))['totalCopper'],10050)

    async def test_maps_are_owner_and_guild_scoped(self):
        ident=await self.store.save_map(1,10,{'spec':{'name':'Карта'}})
        self.assertFalse(await self.store.maps(1))
        self.assertFalse(await self.store.maps(1,11))
        with self.assertRaises(ValueError):await self.store.save_map(1,11,{'id':ident,'spec':{}})
        await self.store.save_map(1,10,{'id':ident,'published':True,'spec':{}})
        self.assertEqual(len(await self.store.maps(1)),1)
        self.assertFalse(await self.store.maps(2))
        with self.assertRaises(ValueError): await self.store.delete_map(1,11,ident)

    async def test_insufficient_funds_roll_back(self):
        await self.store.edit_shop(1,{'itemId':1,'stock':5,'buyPrice':100,'sellPrice':50})
        with self.assertRaises(ValueError): await self.store.trade(1,{'action':'buy','itemId':1,'quantity':2})
        self.assertFalse(await self.db.inventory(1))
        self.assertEqual((await self.store.shop(1))['items'][0]['stock'],5)

    async def test_equipped_original_modifiers(self):
        character={'attributes':{'Сила':10,'Стойкость':10,'Искусность':10,'Быстрота':10,'Смекалка':10,'Живучесть':10},'skills':{},'talents':[]}
        item={'name':'Кольцо','equipped_slot':'Аксессуар','properties':{'gameData':{'statusEffects':[{'Apply':0,'Value':2,'AffectsStat':57,'ApplicationPrerequisites':[]}]}}}
        self.assertEqual(_derived(character,[item])['effectiveAttributes']['Сила'],12)
        item['equipped_slot']=None
        self.assertEqual(_derived(character,[item])['effectiveAttributes']['Сила'],10)

    async def test_routes_enforce_tokens_and_guilds(self):
        app=web.Application();app['db']=self.db
        app.router.add_get('/api/admin/{token}/maps',admin_maps)
        app.router.add_post('/api/admin/{token}/character/{character_id}/wallet',admin_wallet)
        app.router.add_get('/api/portal/{token}/shop',portal_shop)
        token=await self.db.create_admin_token(2,10)
        async with TestClient(TestServer(app)) as client:
            self.assertEqual((await client.get('/api/admin/invalid/maps')).status,410)
            self.assertEqual((await client.get('/api/portal/invalid/shop')).status,410)
            response=await client.post(f'/api/admin/{token}/character/1/wallet',json={'iron':100})
            self.assertEqual(response.status,404)
        self.assertEqual((await self.store.wallet(1))['totalCopper'],0)


class GridAndAreasTests(unittest.TestCase):
    def test_independent_barriers_and_path(self):
        grid=TacticalGrid(8,8,{(3,3)},set(),{(5,3)})
        self.assertTrue(grid.line_of_sight((1,3),(6,3)))
        self.assertNotIn((3,3),grid.path((1,3),(6,3)))
        grid.sight_blocked={(3,3)}
        self.assertFalse(grid.line_of_sight((1,3),(6,3)))
        grid.blocked=set()
        self.assertIn((3,3),grid.path((1,3),(6,3)))
        grid.sight_blocked=set()
        self.assertEqual(grid.cover((1,3),(5,3))[1],15)

    def test_area_immediate_then_once_then_expiration(self):
        character={'name':'Маг','health':100,'health_max':100,'attributes':{'Смекалка':10,'Быстрота':10},'skills':{},'talents':[]}
        derived={'attack':{'accuracy':50},'effectiveAttributes':character['attributes']}
        spell={'name':'Северная земля','core':'Холод','expression':'Область влияния','accents':[],'enhancements':[]}
        session=TrainingSession(1,player_position=(8,4))
        session.act({'kind':'spell','name':spell['name'],'x':10,'y':4},character,derived,[spell],2)
        self.assertEqual(session.conditions['dummy']['frost']['stacks'],1)
        self.assertEqual(session.areas[0]['remaining'],1)
        session.act({'kind':'end_turn'},character,derived,[spell],2)
        self.assertEqual(session.conditions['dummy']['frost']['stacks'],2)
        self.assertFalse(session.areas)
        session.act({'kind':'end_turn'},character,derived,[spell],2)
        self.assertNotIn('frost',session.conditions['dummy'])
        self.assertEqual(persistent_profile({**spell,'accents':['Вневременная форма 3']})['rounds'],3)

    def test_map_validation_and_currency(self):
        self.assertEqual(money(12345),{'totalCopper':12345,'iron':1,'bronze':23,'copper':45})
        with self.assertRaises(ValueError):validate_map({'width':500})
        with self.assertRaises(ValueError):validate_map({'image':'javascript:alert(1)'})
        with self.assertRaises(ValueError):validate_map({'image':'https://example.com/\"bad'})


if __name__=='__main__':unittest.main()
