"""Deletion isolation, revoked access and owner-scoped portrait uploads."""
import base64
import io
import json
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock,patch

from aiohttp import web
from aiohttp.test_utils import TestClient,TestServer
from PIL import Image
from crafting import SCHEMA as CRAFT_SCHEMA
from player_possessions import SCHEMA as POSSESSION_SCHEMA
from consumable_store import SCHEMA as EFFECT_SCHEMA
from registration_api import admin_mutation,portal_portrait,portal_info,cors_middleware
from test_campaign import CampaignTests


class CharacterToolsTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp=CampaignTests.asyncSetUp
    asyncTearDown=CampaignTests.asyncTearDown

    async def prepare(self):
        async with self.db.connect() as conn:
            await conn.executescript(CRAFT_SCHEMA+POSSESSION_SCHEMA+EFFECT_SCHEMA)
            await conn.execute("INSERT INTO characters(guild_id,user_id,name,background,specialization_1,specialization_2) VALUES(1,2,'Другой','Книгочей','Меч и щит','Дротик'),(2,1,'Другой сервер','Книгочей','Меч и щит','Дротик')")
            await conn.execute("INSERT INTO attributes VALUES(1,'Сила',10)")
            await conn.execute("INSERT INTO skills VALUES(1,'Атлетика',20,0)")
            await conn.execute("INSERT INTO talents(character_id,tree_name,name) VALUES(1,'Сила','Талант')")
            await conn.execute('INSERT INTO inventory(character_id,item_id) VALUES(1,1),(2,1)')
            await conn.execute("INSERT INTO spells(character_id,name,core,expression) VALUES(1,'Заклинание','Огонь','Дальний удар')")
            await conn.execute("INSERT INTO character_sigils(character_id,sigil_key) VALUES(1,'core:Огонь')")
            await conn.execute("INSERT INTO reputation VALUES(1,'Опальные',10,0)")
            await conn.execute("INSERT INTO combat_quickbar VALUES(1,1,'attack','Обычная атака')")
            await conn.execute('INSERT INTO starting_grants VALUES(1)')
            await conn.execute("INSERT INTO crafting_known VALUES(1,'recipe')")
            await conn.execute("INSERT INTO crafting_jobs(character_id,payload,ready_at) VALUES(1,'{}','2099')")
            await conn.execute("INSERT INTO character_item_effects VALUES(1,'{}')")
            spec={'name':'Арена','tokens':[{'kind':'player','id':1,'x':1,'y':1},{'kind':'player','id':2,'x':2,'y':1},{'kind':'npc','id':1,'x':3,'y':1}]}
            await conn.execute('INSERT INTO battle_maps(guild_id,owner_id,name,spec) VALUES(1,99,?,?)',('Арена',json.dumps(spec)))
            await conn.commit()
        await self.store.set_wallet(1,900)
        self.portal=await self.db.create_portal_token(1,1)
        self.registration=await self.db.create_registration_token(1,1)
        self.admin=await self.db.create_admin_token(1,99)

    async def client(self):
        app=web.Application(middlewares=[cors_middleware],client_max_size=7*1024*1024)
        app['db']=self.db;app['data_dir']=Path(self.temp.name)
        app['extended_talents']={'backgrounds':{},'factions':[]}
        app['training_sessions']={1:object()};app['training_locks']={1:object()}
        app.router.add_post('/api/admin/{token}/character/{character_id}',admin_mutation)
        app.router.add_post('/api/portal/{token}/portrait',portal_portrait)
        app.router.add_get('/api/portal/{token}',portal_info)
        return TestClient(TestServer(app))

    async def test_deletion_cascades_but_preserves_other_players_maps_and_catalog(self):
        await self.prepare()
        self.assertFalse(await self.db.delete_character(1,1,expected_character_id=2))
        self.assertTrue(await self.db.delete_character(1,1,expected_character_id=1))
        self.assertIsNone(await self.db.portal_character_id(self.portal))
        self.assertIsNone(await self.db.registration_token_owner(self.registration))
        self.assertIsNotNone(await self.db.get_character(1,2))
        self.assertIsNotNone(await self.db.get_character(2,1))
        async with self.db.connect() as conn:
            for table in ['attributes','skills','talents','inventory','spells','character_sigils','reputation','combat_quickbar','wallets','starting_grants','crafting_known','crafting_jobs','character_item_effects','portal_tokens']:
                self.assertFalse(await conn.execute_fetchall(f'SELECT 1 FROM {table} WHERE character_id=1'),table)
            self.assertTrue(await conn.execute_fetchall('SELECT 1 FROM inventory WHERE character_id=2'))
            self.assertTrue(await conn.execute_fetchall('SELECT 1 FROM item_catalog WHERE id=1'))
            tokens=json.loads((await conn.execute_fetchall('SELECT spec FROM battle_maps'))[0]['spec'])['tokens']
            self.assertEqual([(t['kind'],t['id']) for t in tokens],[('player',2),('npc',1)])
            log=(await conn.execute_fetchall('SELECT * FROM admin_audit'))[0]
            self.assertEqual(log['action'],'character_delete_self')
            self.assertEqual(json.loads(log['details'])['name'],'Герой')
        self.assertFalse(await self.db.delete_character(1,1))

    async def test_admin_delete_requires_exact_confirmation_and_guild_authority(self):
        await self.prepare()
        async with await self.client() as client:
            path=f'/api/admin/{self.admin}/character/1'
            self.assertEqual((await client.post('/api/admin/invalid/character/1',json={'action':'character_delete','confirmName':'Герой'})).status,410)
            self.assertEqual((await client.post(f'/api/admin/{self.portal}/character/1',json={'action':'character_delete','confirmName':'Герой'})).status,410)
            self.assertEqual((await client.post(f'/api/admin/{self.admin}/character/3',json={'action':'character_delete','confirmName':'Другой сервер'})).status,404)
            for name in ['',None,'герой','Другой']:
                response=await client.post(path,json={'action':'character_delete','confirmName':name})
                self.assertEqual(response.status,400)
                self.assertIsNotNone(await self.db.get_character_by_id(1))
            response=await client.post(path,json={'action':'character_delete','confirmName':'Герой'})
            self.assertEqual(response.status,200)
            result=await response.json();self.assertEqual(result['deletedId'],1)
            self.assertEqual([c['id'] for c in result['characters']],[2])
            self.assertNotIn(1,client.app['training_sessions'])
            self.assertNotIn(1,client.app['training_locks'])
            self.assertEqual((await client.get(f'/api/portal/{self.portal}')).status,410)
            self.assertEqual((await client.post(path,json={'action':'character_delete','confirmName':'Герой'})).status,404)
        async with self.db.connect() as conn:
            log=(await conn.execute_fetchall('SELECT * FROM admin_audit'))[0]
            self.assertEqual((log['action'],log['admin_user_id']),('character_delete_admin',99))

    async def test_discord_deletes_only_the_caller_after_confirmation(self):
        import bot
        await self.prepare()
        interaction=SimpleNamespace(guild_id=1,user=SimpleNamespace(id=1),response=SimpleNamespace(send_message=AsyncMock(),defer=AsyncMock()),followup=SimpleNamespace(send=AsyncMock()))
        with patch.object(bot.bot,'db',self.db):
            await bot.delete_character_command.callback(interaction,'нет')
            self.assertIsNotNone(await self.db.get_character(1,1))
            interaction.response.send_message.assert_awaited_once()
            await bot.delete_character_command.callback(interaction,'УДАЛИТЬ')
        interaction.followup.send.assert_awaited_once()
        self.assertIsNone(await self.db.get_character(1,1))
        self.assertIsNotNone(await self.db.get_character(1,2))
        self.assertIsNotNone(await self.db.get_character(2,1))

    async def test_portrait_upload_is_validated_owner_scoped_and_cache_safe(self):
        await self.prepare()
        async with await self.client() as client:
            path=f'/api/portal/{self.portal}/portrait'
            self.assertEqual((await client.post('/api/portal/invalid/portrait',json={'portrait':'bad'})).status,410)
            for bad in ['', 'https://example.org/p.png','data:image/png;base64,???', 'data:image/svg+xml;base64,PHN2Zy8+',42]:
                self.assertEqual((await client.post(path,json={'portrait':bad})).status,400)
            urls=[]
            for color in ['red','blue']:
                stream=io.BytesIO();Image.new('RGB',(1800,1200),color).save(stream,'PNG')
                portrait='data:image/png;base64,'+base64.b64encode(stream.getvalue()).decode()
                # Ignore a supplied target ID: only the portal owner may change.
                response=await client.post(path,json={'portrait':portrait,'characterId':2})
                self.assertEqual(response.status,200)
                result=await response.json();urls.append(result['character']['portrait_url'])
                saved=Path((await self.db.get_character_by_id(1))['portrait_url'][8:])
                self.assertEqual(saved.parent,Path(self.temp.name)/'portraits')
                with Image.open(saved) as image:
                    self.assertEqual(image.format,'WEBP');self.assertLessEqual(max(image.size),1600)
            self.assertNotEqual(urls[0],urls[1])
            self.assertEqual((await self.db.get_character_by_id(2))['portrait_url'],'')
