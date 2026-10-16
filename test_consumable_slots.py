import copy
import json
import unittest
import aiosqlite
from inventory_rules import CONSUMABLE_CATEGORIES
import test_campaign as campaign
import test_shared_battles as shared
from test_consumables import item, character
from training_combat import TrainingSession
from registration_api import _derived


class ConsumableSlotRulesTests(unittest.TestCase):
    def test_each_consumable_uses_a_bag_slot_even_when_tiny_or_named_like_a_free_item(self):
        from database import Database
        for category in CONSUMABLE_CATEGORIES:
            self.assertTrue(Database._item_consumes_slot('Перо и руна', category, .01))
            self.assertFalse(Database._item_consumes_slot('Перо и руна', category, .01, 'Быстрый предмет 1'))

    def test_training_uses_only_prepared_items_and_spent_slot_does_not_refill(self):
        c=character();d=_derived(c,[])
        inventory=[{**item('IT_CONS_HealingPotionCommon'),'inventory_id':i,'quantity':1,
                    'equipped_slot':f'Быстрый предмет {i}' if i<3 else None} for i in [1,2,3]]
        s=TrainingSession(1);s.consumable_inventory=copy.deepcopy(inventory)
        def actions():return [a for a in s.view(c,d,[],2)['actions'] if a['kind']=='item']
        self.assertEqual({a['name'] for a in actions()},{'1','2'})
        s.act({'kind':'item','name':'1'},c,d,[],2)
        self.assertEqual([a['name'] for a in actions()],['2'])
        self.assertTrue(s.action_available)
        with self.assertRaises(ValueError):s.act({'kind':'item','name':'1'},c,d,[],2)
        with self.assertRaises(ValueError):s.act({'kind':'item','name':'3'},c,d,[],2)
        s.act({'kind':'item','name':'2'},c,d,[],2)
        self.assertFalse(actions())
        self.assertEqual(s.consumable_inventory,inventory)  # Training never spends real items.


class ConsumableInventoryTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp=campaign.CampaignTests.asyncSetUp
    asyncTearDown=campaign.CampaignTests.asyncTearDown

    async def test_migration_keeps_every_copy_original_slot_id_and_notes_even_over_capacity(self):
        async with self.db.connect() as c:
            selected=await c.execute("INSERT INTO inventory(character_id,item_id,quantity,equipped_slot,notes) VALUES(1,1,4,'Быстрый предмет 1','Личные заметки')")
            selected_id=selected.lastrowid
            await c.execute('INSERT INTO inventory(character_id,item_id,quantity) VALUES(1,1,10)')
            await c.commit()
        self.assertEqual(await self.db.normalize_consumable_inventory(),2)
        rows=await self.db.inventory(1)
        self.assertEqual(len(rows),14);self.assertTrue(all(i['quantity']==1 for i in rows))
        selected=next(i for i in rows if i['inventory_id']==selected_id)
        self.assertEqual(selected['equipped_slot'],'Быстрый предмет 1')
        self.assertEqual(sum(i['notes']=='Личные заметки' for i in rows),4)
        self.assertEqual((await self.db.inventory_capacity(1))['used'],13)
        self.assertEqual(await self.db.normalize_consumable_inventory(),0)
        self.assertEqual(await self.db.inventory(1),rows)

    async def test_database_rejects_consumable_stacks_but_keeps_material_stacks(self):
        await self.db.normalize_consumable_inventory()
        async with self.db.connect() as c:
            with self.assertRaises(aiosqlite.IntegrityError):await c.execute('INSERT INTO inventory(character_id,item_id,quantity) VALUES(1,1,2)')
            row=await c.execute('INSERT INTO inventory(character_id,item_id,quantity) VALUES(1,1,1)')
            with self.assertRaises(aiosqlite.IntegrityError):await c.execute('UPDATE inventory SET quantity=2 WHERE id=?',(row.lastrowid,))
            material=await c.execute("INSERT INTO item_catalog(name,category) VALUES('Алхимические припасы','Материалы')")
            await c.execute('INSERT INTO inventory(character_id,item_id,quantity) VALUES(1,?,40)',(material.lastrowid,))
            await c.commit()
        self.assertEqual(sum(i['quantity'] for i in await self.db.inventory(1)),41)

    async def test_giving_equipping_and_replacing_identical_potions_keep_individual_rows(self):
        await self.db.normalize_consumable_inventory()
        self.assertTrue(await self.db.give_item(1,'Зелье',2))
        first,second=await self.db.inventory(1)
        self.assertEqual((await self.db.inventory_capacity(1))['used'],2)
        self.assertTrue((await self.db.equip(1,first['inventory_id'],'Быстрый предмет 1'))[0])
        self.assertTrue((await self.db.equip(1,second['inventory_id'],'Быстрый предмет 2'))[0])
        self.assertEqual((await self.db.inventory_capacity(1))['used'],0)
        await self.db.admin_give_item(1,'Зелье',3)
        spare=next(i for i in await self.db.inventory(1) if not i['equipped_slot'])
        self.assertTrue((await self.db.equip(1,spare['inventory_id'],'Быстрый предмет 1'))[0])
        rows=await self.db.inventory(1)
        self.assertEqual(len(rows),5);self.assertTrue(all(i['quantity']==1 for i in rows))
        self.assertIsNone(next(i for i in rows if i['inventory_id']==first['inventory_id'])['equipped_slot'])

    async def test_shop_counts_each_bottle_and_rejects_purchase_without_enough_space(self):
        await self.db.normalize_consumable_inventory()
        await self.store.set_wallet(1,10000)
        await self.store.edit_shop(1,{'itemId':1,'stock':30,'buyPrice':100,'sellPrice':50})
        await self.store.trade(1,{'action':'buy','itemId':1,'quantity':7})
        before=await self.store.wallet(1)
        with self.assertRaises(ValueError):await self.store.trade(1,{'action':'buy','itemId':1,'quantity':2})
        self.assertEqual(await self.store.wallet(1),before)
        self.assertEqual(len(await self.db.inventory(1)),7)
        await self.store.trade(1,{'action':'buy','itemId':1,'quantity':1})
        self.assertEqual((await self.db.inventory_capacity(1))['used'],8)
        self.assertFalse(await self.db.give_item(1,'Зелье',1))

    async def test_transfer_one_potion_does_not_merge_with_recipient_potions(self):
        from player_possessions import SCHEMA,operate
        async with self.db.connect() as c:
            await c.executescript(SCHEMA)
            await c.execute("INSERT INTO characters(guild_id,user_id,name,background,specialization_1,specialization_2) VALUES(1,2,'Второй','Книгочей','','')")
            await c.commit()
        await self.db.normalize_consumable_inventory()
        await self.db.admin_give_item(1,'Зелье',2);await self.db.admin_give_item(2,'Зелье',1)
        row=(await self.db.inventory(1))[0]
        await operate(self.db,1,{'kind':'item','action':'transfer','inventoryId':row['inventory_id'],'quantity':1,'recipientId':2})
        self.assertEqual(len(await self.db.inventory(1)),1)
        self.assertEqual(len(await self.db.inventory(2)),2)
        self.assertTrue(all(i['quantity']==1 for i in await self.db.inventory(2)))


class ConsumableBattleTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp=shared.SharedBattleTests.asyncSetUp
    asyncTearDown=shared.SharedBattleTests.asyncTearDown
    start=shared.SharedBattleTests.start
    edit=shared.SharedBattleTests.edit

    async def test_api_returns_own_updated_inventory_after_using_a_quick_slot(self):
        from aiohttp import web
        from aiohttp.test_utils import TestClient, TestServer
        from battle_api import register_battle_routes
        await self.db.upsert_catalog([item('IT_CONS_HealingPotionCommon')])
        await self.db.admin_give_item(1,'Слабое зелье исцеления',2)
        await self.db.admin_give_item(2,'Слабое зелье исцеления',1)
        first,second=await self.db.inventory(1)
        await self.db.equip(1,first['inventory_id'],'Быстрый предмет 1')
        await self.db.equip(1,second['inventory_id'],'Быстрый предмет 2')
        await self.start();await self.edit(operation='turn',tokenId='pc_1')
        token=await self.db.create_portal_token(1,1)
        app=web.Application();app['db']=self.db;register_battle_routes(app)
        async with TestClient(TestServer(app)) as client:
            response=await client.post(f'/api/portal/{token}/battles/{self.ident}',
                json={'kind':'item','name':str(first['inventory_id']),'targetId':'pc_1'})
            self.assertEqual(response.status,200,await response.text())
            result=await response.json()
        self.assertEqual([i['inventory_id'] for i in result['inventory']],[second['inventory_id']])
        self.assertEqual(result['inventory'][0]['equipped_slot'],'Быстрый предмет 2')
        self.assertEqual(result['capacity']['used'],0)
        self.assertNotIn('tokens',result['battle'])
        self.assertEqual(len(await self.db.inventory(2)),1)

    async def test_consuming_first_slot_deletes_only_it_second_slot_remains_and_bag_cannot_be_used(self):
        await self.db.upsert_catalog([item('IT_CONS_HealingPotionCommon')])
        await self.db.admin_give_item(1,'Слабое зелье исцеления',3)
        rows=await self.db.inventory(1)
        first,second,bag=[i['inventory_id'] for i in rows]
        await self.db.equip(1,first,'Быстрый предмет 1');await self.db.equip(1,second,'Быстрый предмет 2')
        await self.start();await self.edit(operation='turn',tokenId='pc_1')
        await self.edit(operation='health',tokenId='pc_1',health=1)
        with self.assertRaises(ValueError):await self.store.action(self.ident,1,cid=1,payload={'kind':'item','name':str(bag),'targetId':'pc_1'})
        await self.store.action(self.ident,1,cid=1,payload={'kind':'item','name':str(first),'targetId':'pc_1'})
        rows=await self.db.inventory(1)
        self.assertEqual({i['inventory_id'] for i in rows},{second,bag})
        self.assertFalse(any(i['equipped_slot']=='Быстрый предмет 1' for i in rows))
        self.assertEqual(next(i for i in rows if i['inventory_id']==second)['equipped_slot'],'Быстрый предмет 2')
        row=await self.store.get(self.ident,1,cid=1)
        view=await self.store.view(row,cid=1)
        self.assertEqual([a['name'] for a in view['training']['actions'] if a['kind']=='item'],[str(second)])
        self.assertTrue(view['training']['turn']['actionAvailable'])
        await self.store.action(self.ident,1,cid=1,payload={'kind':'item','name':str(second),'targetId':'pc_1'})
        self.assertEqual([i['inventory_id'] for i in await self.db.inventory(1)],[bag])
        with self.assertRaises(ValueError):await self.store.action(self.ident,1,cid=1,payload={'kind':'item','name':str(first),'targetId':'pc_1'})


class ConsumableCraftSlotTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp=campaign.CampaignTests.asyncSetUp
    asyncTearDown=campaign.CampaignTests.asyncTearDown

    async def test_craft_checks_slots_for_every_bottle_and_never_merges_outputs(self):
        import test_crafting as fixtures
        from crafting import library
        await fixtures.CraftTests.setup_crafter(self)
        await self.db.normalize_consumable_inventory()
        recipe=next(r for r in library()['recipes'] if r['key']=='Potion_Health_Common')
        await fixtures.CraftTests.give_materials(self,recipe['ingredients'],3)
        inventory=await self.db.inventory(1);wallet=await self.store.wallet(1)
        with self.assertRaisesRegex(ValueError,'место'):
            await self.craft.act(1,{'action':'craft','recipeKey':recipe['key'],'quantity':2})
        self.assertEqual(await self.db.inventory(1),inventory)
        self.assertEqual(await self.store.wallet(1),wallet)
        await self.craft.act(1,{'action':'craft','recipeKey':recipe['key'],'quantity':1})
        bottles=[i for i in await self.db.inventory(1) if i['category'] in CONSUMABLE_CATEGORIES]
        self.assertEqual(len(bottles),5);self.assertTrue(all(i['quantity']==1 for i in bottles))
        inventory=await self.db.inventory(1);wallet=await self.store.wallet(1)
        with self.assertRaisesRegex(ValueError,'место'):
            await self.craft.act(1,{'action':'craft','recipeKey':recipe['key'],'quantity':1})
        self.assertEqual(await self.db.inventory(1),inventory)
        self.assertEqual(await self.store.wallet(1),wallet)


if __name__=='__main__':unittest.main()
