import asyncio
import copy
import json
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path
from aiohttp import web
from aiohttp.test_utils import TestClient,TestServer
from database import Database,SCHEMA as DB_SCHEMA
from campaign_store import CampaignStore,SCHEMA as MAP_SCHEMA
from npc_store import NPCStore,SCHEMA as NPC_SCHEMA
from battle_store import BattleStore,SCHEMA
from battle_api import register_battle_routes
from registration_api import cors_middleware
from consumable_store import SCHEMA as EFFECT_SCHEMA
from player_possessions import SCHEMA as POSSESSION_SCHEMA


class SharedBattleTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp=tempfile.TemporaryDirectory();self.db=Database(Path(self.temp.name)/'battle.db')
        async with self.db.connect() as c:
            await c.executescript(DB_SCHEMA+MAP_SCHEMA+NPC_SCHEMA+SCHEMA+EFFECT_SCHEMA+POSSESSION_SCHEMA)
            for user,name in [(1,'Первый'),(2,'Второй'),(3,'Не приглашён')]:
                await c.execute("INSERT INTO characters(guild_id,user_id,name,background,specialization_1,specialization_2,health,health_max) VALUES(1,?,?,'Книгочей','Меч и щит','Дротик',100,100)",(user,name))
                cid=user
                await c.executemany('INSERT INTO attributes VALUES(?,?,?)',[(cid,k,10) for k in ['Сила','Искусность','Быстрота','Живучесть','Смекалка','Стойкость']])
                await c.executemany('INSERT INTO skills VALUES(?,?,?,?)',[(cid,k,30,0) for k in ['Атлетика','Хитроумие','Знания','Парирование','Уклонение','Одноручное оружие','Безоружный бой']])
            await c.commit()
        self.npcs=NPCStore(self.db)
        self.npc=await self.npcs.save(1,99,{'spec':{'name':'Разбойник','healthMax':100,'level':1,'defenses':{},'abilities':[],
            'attributes':{'Быстрота':10},'attack':{'accuracy':20,'damageMin':4,'damageMax':8,'range':1}}})
        self.map_id=await CampaignStore(self.db).save_map(1,99,{'spec':{'name':'Поле','width':10,'height':8,'blocked':[{'x':0,'y':0}],
            'tokens':[{'kind':'player','id':1,'x':1,'y':1},{'kind':'player','id':2,'x':2,'y':1},{'kind':'npc','id':self.npc,'x':5,'y':1}]}})
        self.store=BattleStore(self.db);self.row=await self.store.create(1,99,self.map_id,[1,2]);self.ident=self.row['id']

    async def asyncTearDown(self):self.temp.cleanup()
    async def edit(self,**p):return await self.store.action(self.ident,1,owner=99,payload=p)
    async def start(self):
        for cid in [1,2]:await self.store.join(self.ident,1,cid)
        return await self.edit(operation='start')

    async def test_create_and_access_are_scoped(self):
        self.assertEqual(self.row['status'],'lobby')
        with self.assertRaises(ValueError):await self.store.get(self.ident,2,99)
        with self.assertRaises(ValueError):await self.store.get(self.ident,1,100)
        with self.assertRaises(ValueError):await self.store.join(self.ident,1,3)
        with self.assertRaises(ValueError):await self.store.create(1,100,self.map_id,[1])

    async def test_start_requires_join_and_placement(self):
        with self.assertRaises(ValueError):await self.edit(operation='start')
        await self.store.join(self.ident,1,1)
        with self.assertRaises(ValueError):await self.edit(operation='start')
        await self.store.join(self.ident,1,2)
        await self.edit(operation='remove_token',tokenId='pc_2')
        with self.assertRaises(ValueError):await self.edit(operation='start')
        await self.edit(operation='place_player',characterId=2,x=2,y=2)
        self.assertEqual((await self.edit(operation='start'))['status'],'active')

    async def test_turn_permissions_and_shared_positions(self):
        await self.start();await self.edit(operation='turn',tokenId='pc_1')
        with self.assertRaisesRegex(ValueError,'другого'):await self.store.action(self.ident,1,cid=2,payload={'kind':'move','x':2,'y':2})
        await self.store.action(self.ident,1,cid=1,payload={'kind':'move','x':1,'y':2})
        row=await self.store.get(self.ident,1,cid=2);v=await self.store.view(row,cid=2)
        self.assertEqual(next(t for t in v['training']['grid']['tokens'] if t['id']=='pc_1')['y'],2)
        self.assertFalse(v['training']['turn']['actionAvailable'])

    async def test_master_can_move_any_token_and_reject_blocked_or_occupied(self):
        await self.edit(operation='move',tokenId='pc_2',x=3,y=3)
        for point in [(0,0),(5,1),(10,0),(-1,3)]:
            with self.assertRaises(ValueError):await self.edit(operation='move',tokenId='pc_1',x=point[0],y=point[1])
        self.assertEqual((await self.store.get(self.ident,1,99))['state']['tokens']['pc_1']['x'],1)

    async def test_master_hp_persists_to_character_and_reload(self):
        await self.start();await self.edit(operation='health',tokenId='pc_1',delta=-15)
        self.assertEqual((await self.db.get_character_by_id(1))['health'],85)
        other=BattleStore(Database(self.db.path));row=await other.get(self.ident,1,99)
        self.assertEqual(row['state']['tokens']['pc_1']['health'],85)
        with self.assertRaises(ValueError):await self.edit(operation='health',tokenId='pc_1',health=-1)

    async def test_equipment_max_health_applies_at_creation_and_after_unequip(self):
        props={'gameData':{'statusEffects':[{'AffectsStat':0,'Value':5,'Apply':0}]}}
        async with self.db.connect() as c:
            item=await c.execute('INSERT INTO item_catalog(name,category,properties) VALUES(?,?,?)',('Проверочная одежда','Легкая броня',json.dumps(props)))
            await c.execute("INSERT INTO inventory(character_id,item_id,quantity,equipped_slot) VALUES(1,?,1,'Торс')",(item.lastrowid,));await c.commit()
        row=await self.store.create(1,99,self.map_id,[1,2])
        self.assertEqual(row['state']['tokens']['pc_1']['healthMax'],105)
        self.assertEqual((await self.store._profiles(row))['pc_1'][1]['healthMax'],105)
        async with self.db.connect() as c:
            await c.execute('UPDATE inventory SET equipped_slot=NULL WHERE character_id=1');await c.commit()
        self.assertEqual((await self.store._profiles(row))['pc_1'][1]['healthMax'],100)

    async def test_effect_is_functional_and_expires_once_per_round(self):
        await self.start();await self.edit(operation='turn',tokenId='pc_1')
        await self.edit(operation='effect',tokenId='pc_1',effect='stun',rounds=1)
        with self.assertRaisesRegex(ValueError,'контрол'):await self.store.action(self.ident,1,cid=1,payload={'kind':'tactic','name':'Спринт','targetId':'pc_1','x':1,'y':1})
        for _ in range(3):
            row=await self.store.get(self.ident,1,99);await self.edit(operation='act',actorId=row['state']['currentId'],kind='end_turn')
        row=await self.store.get(self.ident,1,99)
        self.assertEqual(row['state']['round'],2);self.assertNotIn('stun',row['state']['conditions']['pc_1'])

    async def test_order_validation_and_current_turn_preserved(self):
        row=await self.start();order=[i['id'] for i in row['state']['initiative']]
        with self.assertRaises(ValueError):await self.edit(operation='order',order=[order[0]]*len(order))
        row=await self.edit(operation='order',order=order[::-1])
        self.assertEqual([i['id'] for i in row['state']['initiative']],order[::-1])

    async def test_add_npc_independent_copy_and_archive_ownership(self):
        row=await self.edit(operation='add_npc',npcId=self.npc,x=7,y=1)
        self.assertEqual(len([t for t in row['state']['tokens'].values() if t['kind']=='npc']),2)
        await self.edit(operation='health',tokenId='npc_2',health=30)
        row=await self.store.get(self.ident,1,99);self.assertEqual(row['state']['tokens']['npc_1']['health'],100)
        with self.assertRaises(ValueError):await self.edit(operation='add_npc',npcId=999,x=8,y=1)
        view=await self.store.view(row,master=True)
        self.assertEqual({t['id'] for t in view['tokens']},{'pc_1','pc_2','npc_1','npc_2'})

    async def test_stale_revision_is_atomic_and_concurrent_action_spends_once(self):
        row=await self.start();await self.edit(operation='turn',tokenId='pc_1')
        stale=row['revision']
        with self.assertRaisesRegex(ValueError,'изменился'):await self.edit(operation='health',tokenId='pc_1',health=1,revision=stale)
        results=await asyncio.gather(*[self.store.action(self.ident,1,cid=1,payload={'kind':'tactic','name':'Спринт','targetId':'pc_1','x':1,'y':1}) for _ in range(2)],return_exceptions=True)
        self.assertEqual(sum(isinstance(r,Exception) for r in results),1)
        row=await self.store.get(self.ident,1,99);self.assertEqual(row['state']['personal']['pc_1']['movement_remaining'],10)

    async def test_one_joined_battle_per_character(self):
        await self.store.join(self.ident,1,1)
        other=await self.store.create(1,99,self.map_id,[1])
        with self.assertRaises(ValueError):await self.store.join(other['id'],1,1)
        await self.edit(operation='finish');await self.store.join(other['id'],1,1)

    async def test_real_consumable_last_stack_and_action_cost(self):
        from test_consumables import item
        potion=item('IT_CONS_PotionOfHeroes')
        async with self.db.connect() as c:
            cur=await c.execute('INSERT INTO item_catalog(name,category,properties) VALUES(?,?,?)',(potion['name'],'Зелья',json.dumps(potion['properties'],ensure_ascii=False)))
            inv=await c.execute('INSERT INTO inventory(character_id,item_id,quantity) VALUES(?,?,1)',(1,cur.lastrowid));inv_id=inv.lastrowid
            await c.commit()
        await self.start();await self.edit(operation='turn',tokenId='pc_1')
        await self.store.action(self.ident,1,cid=1,payload={'kind':'item','name':str(inv_id),'targetId':'pc_1','x':1,'y':1})
        row=await self.store.get(self.ident,1,99)
        self.assertTrue(row['state']['personal']['pc_1']['action_available'])
        self.assertFalse(await self.db.inventory(1))
        with self.assertRaises(ValueError):await self.store.action(self.ident,1,cid=1,payload={'kind':'item','name':str(inv_id),'targetId':'pc_1','x':1,'y':1})

    async def test_dot_pulses_once_per_round_and_recovery_works(self):
        await self.start();await self.edit(operation='effect',tokenId='pc_1',effect='poison',name='Яд',value=7,rounds=2)
        for _ in range(3):
            row=await self.store.get(self.ident,1,99);await self.edit(operation='act',actorId=row['state']['currentId'],kind='end_turn')
        row=await self.store.get(self.ident,1,99)
        self.assertEqual(row['state']['tokens']['pc_1']['health'],93)
        await self.edit(operation='remove_effect',tokenId='pc_1',effectId='master:poison')
        await self.edit(operation='effect',tokenId='pc_1',effect='heal',name='Регенерация',value=3,rounds=1)
        for _ in range(3):
            row=await self.store.get(self.ident,1,99);await self.edit(operation='act',actorId=row['state']['currentId'],kind='end_turn')
        self.assertEqual((await self.store.get(self.ident,1,99))['state']['tokens']['pc_1']['health'],96)

    async def test_real_consumable_stack_is_not_subtracted_twice_and_master_spends_it(self):
        from test_consumables import item
        potion=item('IT_CONS_PotionOfHeroes')
        async with self.db.connect() as c:
            cur=await c.execute('INSERT INTO item_catalog(name,category,properties) VALUES(?,?,?)',(potion['name'],'Зелья',json.dumps(potion['properties'],ensure_ascii=False)))
            inv=await c.execute('INSERT INTO inventory(character_id,item_id,quantity) VALUES(?,?,2)',(1,cur.lastrowid));inv_id=inv.lastrowid
            await c.commit()
        await self.start();await self.edit(operation='turn',tokenId='pc_1')
        await self.store.action(self.ident,1,cid=1,payload={'kind':'item','name':str(inv_id),'targetId':'pc_1','x':1,'y':1})
        self.assertEqual((await self.db.inventory(1))[0]['quantity'],1)
        # Reset only the cooldown to test another use without waiting for its original duration.
        row=await self.store.get(self.ident,1,99);row['state']['personal']['pc_1']['cooldowns']={};await self.store._save(row)
        await self.edit(operation='act',actorId='pc_1',kind='item',name=str(inv_id),targetId='pc_1',x=1,y=1)
        self.assertFalse(await self.db.inventory(1))

    async def test_npc_ability_runs_same_executor_and_spends_own_action(self):
        from npc_store import ability_library
        a=next(a for a in ability_library() if a['key']=='ABL_DIS_BloodBound_DisablingKick')
        row=await self.start();row['state']['tokens']['npc_1']['abilities']=[a];await self.store._save(row)
        await self.edit(operation='move',tokenId='npc_1',x=1,y=2)
        with patch('training_combat.random.randint',return_value=100):
            row=await self.edit(operation='act',actorId='npc_1',kind='ability',name=a['key'],targetId='pc_1',x=1,y=1)
        self.assertLess(row['state']['tokens']['pc_1']['health'],100)
        self.assertFalse(row['state']['personal']['npc_1']['action_available'])
        with self.assertRaises(ValueError):await self.edit(operation='act',actorId='npc_1',kind='ability',name=a['key'],targetId='pc_1',x=1,y=1)

    async def test_hidden_token_unit_attack_rejected_and_contact_drag_reveals(self):
        await self.start();await self.edit(operation='turn',tokenId='pc_1')
        row=await self.store.action(self.ident,1,cid=1,payload={'kind':'tactic','name':'Уйти в скрытность','targetId':'pc_1','x':1,'y':1})
        self.assertTrue(row['state']['personal']['pc_1']['stealthed'])
        row=await self.edit(operation='add_npc',npcId=self.npc,x=8,y=7)
        self.assertIn('npc_2',row['state']['tokens'])
        with self.assertRaisesRegex(ValueError,'скрыта'):await self.edit(operation='act',actorId='npc_1',kind='attack',targetId='pc_1',x=1,y=1)
        row=await self.edit(operation='move',tokenId='npc_1',x=1,y=2)
        self.assertFalse(row['state']['personal']['pc_1']['stealthed'])

    async def test_master_attribute_shield_and_expiry_are_real_modifiers(self):
        row=await self.start()
        baseline=await self.store._profiles(row)
        await self.edit(operation='effect',tokenId='pc_1',effect='Стойкость',value=4,rounds=1)
        await self.edit(operation='effect',tokenId='pc_1',effect='Живучесть',value=6,rounds=1)
        await self.edit(operation='effect',tokenId='npc_1',effect='Искусность',value=5,rounds=1)
        await self.edit(operation='effect',tokenId='pc_1',effect='shield',value=10,rounds=2)
        row=await self.store.get(self.ident,1,99);profiles=await self.store._profiles(row)
        self.assertEqual(profiles['pc_1'][1]['defenses']['Магия'],baseline['pc_1'][1]['defenses']['Магия']+6)
        self.assertEqual(profiles['pc_1'][1]['healthMax'],106)
        self.assertEqual(profiles['npc_1'][1]['attack']['accuracy'],baseline['npc_1'][1]['attack']['accuracy']+5)
        from consumables import receive_damage
        states=copy.deepcopy(row['state']['conditions']['pc_1']);self.assertEqual(receive_damage(states,13),3)
        self.assertEqual(states['master:shield']['shieldRemaining'],0)
        for _ in range(3):
            row=await self.store.get(self.ident,1,99);await self.edit(operation='act',actorId=row['state']['currentId'],kind='end_turn')
        row=await self.store.get(self.ident,1,99);profiles=await self.store._profiles(row)
        self.assertEqual(profiles['pc_1'][1]['healthMax'],100)
        self.assertEqual(profiles['npc_1'][1]['attack']['accuracy'],baseline['npc_1'][1]['attack']['accuracy'])

    async def test_dead_current_actor_cannot_stall_queue(self):
        await self.start();await self.edit(operation='turn',tokenId='pc_1')
        row=await self.edit(operation='health',tokenId='pc_1',health=0)
        self.assertNotEqual(row['state']['currentId'],'pc_1')

    async def test_api_players_cannot_gain_master_authority(self):
        token=await self.db.create_portal_token(1,1);admin=await self.db.create_admin_token(1,99)
        app=web.Application(middlewares=[cors_middleware]);app['db']=self.db;register_battle_routes(app)
        async with TestClient(TestServer(app)) as client:
            r=await client.get(f'/api/portal/{token}/battles');self.assertEqual(r.status,200)
            r=await client.get(f'/api/portal/{token}/battles/{self.ident}');self.assertEqual(r.status,200)
            data=await r.json();self.assertNotIn('tokens',data['battle'])
            r=await client.post(f'/api/portal/{token}/battles/{self.ident}',json={'operation':'health','owner':99,'tokenId':'pc_1','health':1})
            self.assertEqual(r.status,409)
            r=await client.get(f'/api/admin/{admin}/battles/{self.ident}');self.assertEqual(r.status,200)
            data=await r.json();r=await client.get(f'/api/admin/{admin}/battles/{self.ident}?afterRevision={data["battle"]["revision"]}')
            self.assertTrue((await r.json())['unchanged'])
            r=await client.get('/api/admin/invalid/battles');self.assertEqual(r.status,410)


if __name__=='__main__':unittest.main()
