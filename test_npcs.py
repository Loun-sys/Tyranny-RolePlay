import unittest
from unittest.mock import patch
from npc_store import NPCStore,SCHEMA,template_page
from campaign_store import validate_map
from test_campaign import CampaignTests
from training_combat import TrainingSession
from tactical_grid import BASE_MOVEMENT
from special_effects import adapted_effects
from artifact_rules import equipped_artifacts
from aiohttp import web
from aiohttp.test_utils import TestClient,TestServer
from registration_api import admin_npcs,public_npcs

class NPCTests(CampaignTests):
    async def asyncSetUp(self):
        await super().asyncSetUp()
        async with self.db.connect() as c:await c.executescript(SCHEMA)
        self.npcs=NPCStore(self.db)

    async def test_npc_visibility_and_ownership(self):
        ident=await self.npcs.save(1,10,{'spec':{'name':'Страж','notes':'Секрет'}})
        self.assertNotIn('notes',(await self.npcs.list(public=True))[0]['spec'])
        self.assertNotIn('notes',(await self.npcs.resolve_map(1,10,[{'id':ident,'x':0,'y':0}]))[0])
        with self.assertRaises(ValueError):await self.npcs.save(1,11,{'id':ident,'spec':{'name':'Чужой'}})
        with self.assertRaises(ValueError):await self.npcs.resolve_map(2,10,[{'id':ident,'x':0,'y':0}])
        await self.npcs.save(1,10,{'id':ident,'spec':{'name':'Страж'},'published':False})
        self.assertFalse(await self.npcs.list(public=True))

    async def test_arbitrary_tokens_without_fixed_spawns(self):
        ident=await self.npcs.save(1,10,{'spec':{'name':'Страж'}})
        spec={'tokens':[{'kind':'player','id':1,'x':0,'y':0},{'kind':'npc','id':ident,'x':2,'y':2}]}
        saved=await self.store.save_map(1,10,{'spec':spec})
        row=(await self.store.maps(1,10))[0]['spec']
        self.assertEqual(row['spawns'],{})
        self.assertEqual(len(row['tokens']),2)
        with self.assertRaises(ValueError):await self.store.save_map(2,10,{'spec':spec})
        with self.assertRaises(ValueError):validate_map({'tokens':[{'kind':'player','id':1,'x':0,'y':0},{'kind':'player','id':1,'x':1,'y':0}]})
        with self.assertRaises(ValueError):validate_map({'blocked':[{'x':0,'y':0}],'tokens':[{'id':1,'x':0,'y':0}]})

    async def test_training_uses_actual_npc_stats_and_allied_tokens(self):
        spec=validate_map({'tokens':[]})
        spec['resolvedTokens']=[{'kind':'player','id':1,'x':0,'y':0},
            {'kind':'npc','id':1,'name':'Враг','team':'enemy','healthMax':250,'armor':18,'defenses':{'Воля':99},'x':3,'y':3},
            {'kind':'npc','id':2,'name':'Союзник','team':'ally','healthMax':100,'x':1,'y':0}]
        session=TrainingSession(1,custom_map=spec)
        self.assertEqual(session.player_position,(0,0))
        self.assertEqual(len(session.targets),2)
        self.assertEqual(len(session._alive_targets()),1)
        self.assertEqual(session._defense('Воля'),99)
        self.assertEqual(session._target()['health'],250)
        self.assertEqual(BASE_MOVEMENT,5)
        view=session.view({'name':'Герой','health':100,'health_max':100,'attributes':{},'talents':[]},{'attack':{'accuracy':30}},[],2)
        self.assertEqual(len(view['grid']['tokens']),3)
        self.assertNotIn({'x':1,'y':0,'cost':1},view['grid']['reachable'])

    async def test_original_archive_and_round_effects(self):
        self.assertGreaterEqual(template_page()['total'],1023)
        effect=adapted_effects({'statuses':[{'AffectsStat':2077,'Tag':'Freeze Affliction','Duration':12,'IsHostile':1}]})[0]
        self.assertEqual(effect['rounds'],2)
        session=TrainingSession(1)
        session._apply_special(effect,'dummy')
        self.assertEqual(session.conditions['dummy']['special:freeze']['until'],2)
        delayed={'kind':'delayedDamage','value':50,'rounds':1,'name':'Урон','side':'enemy'}
        session._apply_special(delayed,'dummy')
        session._initialize({'name':'Тест','health':100})
        session._end_turn()
        self.assertEqual(session.target_healths['dummy'],130)
        self.assertNotIn('special:delayedDamage',session.conditions['dummy'])

    async def test_npc_routes(self):
        app=web.Application();app['db']=self.db
        app.router.add_get('/api/admin/{token}/npcs',admin_npcs)
        app.router.add_post('/api/admin/{token}/npcs',admin_npcs)
        app.router.add_get('/api/archive/npcs',public_npcs)
        token=await self.db.create_admin_token(1,10)
        async with TestClient(TestServer(app)) as client:
            self.assertEqual((await client.get('/api/admin/invalid/npcs')).status,410)
            reply=await client.post(f'/api/admin/{token}/npcs',json={'spec':{'name':'Страж','notes':'Скрыто'}})
            self.assertEqual(reply.status,200)
            payload=await reply.json()
            self.assertGreaterEqual(payload['templates']['total'],1023)
            template=payload['tokenTemplates'][0]
            self.assertTrue(template['portrait'].startswith('assets/npc-portraits/'))
            copied=await client.post(f'/api/admin/{token}/npcs',json={'action':'fromTemplate','key':template['key']})
            self.assertEqual(copied.status,200)
            data=await copied.json()
            row=next(r for r in data['npcs'] if r['id']==data['id'])
            self.assertFalse(row['published'])
            self.assertEqual(row['spec']['sourceKey'],template['key'])
            self.assertTrue(row['spec']['portrait'])
            await self.store.save_map(1,10,{'spec':{'tokens':[{'kind':'npc','id':row['id'],'x':2,'y':2}]}})
            public=await (await client.get('/api/archive/npcs')).json()
            self.assertNotIn('notes',public['npcs'][0]['spec'])
            bad=await client.post(f'/api/admin/{token}/npcs',json={'spec':{'name':'Страж','attack':[]}})
            self.assertEqual(bad.status,400)

    async def test_existing_npc_gains_default_portrait(self):
        ident=await self.npcs.save(1,10,{'spec':{'name':'Без портрета'}})
        row=(await self.npcs.list(1,10))[0]
        self.assertTrue(row['spec']['portrait'].startswith('assets/npc-portraits/'))
        resolved=await self.npcs.resolve_map(1,10,[{'id':ident,'x':2,'y':2}])
        self.assertEqual(resolved[0]['portrait'],row['spec']['portrait'])

    async def test_artifact_delayed_damage_and_expiration(self):
        session=TrainingSession(1,player_position=(9,4))
        character={'name':'Герой','health':100,'health_max':100,'attributes':{},'skills':{},'talents':[]}
        artifact=equipped_artifacts([{'name':'Снежный клык'}])[0]
        derived={'attack':{'accuracy':200,'damageMin':8,'damageMax':12},'artifactAbilities':[artifact]}
        with patch('training_combat.random.randint',return_value=100):
            session.act({'kind':'artifact','name':artifact['name'],'x':10,'y':4},character,derived,[],2)
        self.assertIn('special:freeze',session.conditions['dummy'])
        self.assertEqual(session.target_healths['dummy'],180)
        session.act({'kind':'end_turn'},character,derived,[],2)
        self.assertEqual(session.target_healths['dummy'],130)
        self.assertNotIn('special:freeze',session.conditions['dummy'])
        with self.assertRaises(ValueError):session.act({'kind':'artifact','name':artifact['name'],'x':10,'y':4},character,derived,[],2)

if __name__=='__main__':unittest.main()
