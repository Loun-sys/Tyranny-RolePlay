"""Forge previews must match the actual delivered equipment and server costs."""
import copy
import json
import unittest

import test_campaign as campaign
import test_crafting as fixtures
from crafting import normalize_quality, quality_info, upgrade_recipe
from registration_api import _derived
from test_consumables import character


class ForgePreviewTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = campaign.CampaignTests.asyncSetUp
    asyncTearDown = campaign.CampaignTests.asyncTearDown
    setup_crafter = fixtures.CraftTests.setup_crafter
    give_materials = fixtures.CraftTests.give_materials

    async def test_equipped_item_is_visible_and_keeps_its_slot_after_upgrade(self):
        await self.setup_crafter()
        async with self.db.connect() as connection:
            items=await self.craft._items(connection)
        original=next(i for i in items.values() if i['slot']=='Торс' and (quality_info(i) or {}).get('kind')=='armor' and upgrade_recipe(i))
        await self.db.admin_give_item(1,original['name'])
        inventory=next(i for i in await self.db.inventory(1) if i['id']==original['id'])
        self.assertTrue((await self.db.equip(1,inventory['inventory_id'],'Торс'))[0])
        recipe=upgrade_recipe(inventory)
        await self.give_materials(recipe['ingredients'],3)
        preview=next(u for u in (await self.craft.snapshot(1))['upgrades'] if u['inventoryId']==inventory['inventory_id'])
        self.assertEqual(preview['item']['equipped_slot'],'Торс')
        await self.craft.act(1,{'action':'upgrade','inventoryId':inventory['inventory_id']})
        delivered=next(i for i in await self.db.inventory(1) if i['inventory_id']==inventory['inventory_id'])
        self.assertEqual(delivered['equipped_slot'],'Торс')
        self.assertEqual(delivered['armor'],preview['result']['armor'])
        second=next(u for u in (await self.craft.snapshot(1))['upgrades'] if u['inventoryId']==inventory['inventory_id'])
        self.assertEqual(second['item']['quality'],delivered['quality'])
        self.assertEqual(quality_info(second['result'])['level'],recipe['to']+1)

    async def test_owned_item_is_not_a_second_required_material(self):
        from crafting import prefab
        await self.setup_crafter()
        async with self.db.connect() as connection:
            items=await self.craft._items(connection)
        original=next(i for i in items.values() if upgrade_recipe(i))
        await self.db.admin_give_item(1,original['name'])
        inventory=next(i for i in await self.db.inventory(1) if i['id']==original['id'])
        recipe=upgrade_recipe(inventory)
        await self.give_materials([x for x in recipe['ingredients'] if x['consumed']],1)
        # Some item-specific recipes retain a base-item requirement. Exercise
        # the equivalent equipped/private-item case without needing a duplicate.
        from unittest.mock import patch
        recipe={**recipe,'ingredients':[*recipe['ingredients'],{'prefab':prefab(inventory),'quantity':1,'consumed':False}]}
        with patch('crafting.upgrade_recipe',return_value=recipe):
            preview=next(u for u in (await self.craft.snapshot(1))['upgrades'] if u['inventoryId']==inventory['inventory_id'])
            self.assertFalse(any(not x['consumed'] and x['prefab']==prefab(inventory) for x in preview['ingredients']))
            await self.craft.act(1,{'action':'upgrade','inventoryId':inventory['inventory_id']})
        self.assertTrue((await self.craft.snapshot(1))['materials'])

    async def test_server_preview_matches_delivered_weapon_and_armor(self):
        await self.setup_crafter()
        async with self.db.connect() as connection:
            items = await self.craft._items(connection)
        for kind, slot in [('weapon', 'Оружие I — правая рука'), ('armor', 'Торс')]:
            with self.subTest(kind=kind):
                original = next(i for i in items.values()
                                if (quality_info(i) or {}).get('kind') == kind
                                and upgrade_recipe(i))
                await self.db.admin_give_item(1, original['name'])
                inventory = next(i for i in await self.db.inventory(1) if i['id'] == original['id'])
                recipe = upgrade_recipe(inventory)
                await self.give_materials(recipe['ingredients'], 1)
                preview = next(u for u in (await self.craft.snapshot(1))['upgrades']
                               if u['inventoryId'] == inventory['inventory_id'])
                before = (await self.store.wallet(1))['totalCopper']
                # Client price/results are not authoritative.
                await self.craft.act(1, {'action': 'upgrade', 'inventoryId': inventory['inventory_id'],
                                       'cost': 0, 'result': {'armor': 9999}, 'quantity': 15})
                delivered = next(i for i in await self.db.inventory(1)
                                 if i['inventory_id'] == inventory['inventory_id'])
                delivered['properties'] = json.loads(delivered['properties']) if isinstance(delivered['properties'], str) else delivered['properties']
                self.assertEqual((await self.store.wallet(1))['totalCopper'], before - recipe['cost'])
                self.assertIsNone(delivered['equipped_slot'])
                for field in ['quality', 'damage_min', 'damage_max', 'armor', 'recovery', 'value']:
                    self.assertEqual(delivered[field], preview['result'][field], field)
                expected = _derived(character(), [{**copy.deepcopy(preview['result']), 'equipped_slot': slot}])
                actual = _derived(character(), [{**delivered, 'equipped_slot': slot}])
                for field in ['attack', 'armor', 'armorByType', 'deflection', 'defenses']:
                    self.assertEqual(actual[field], expected[field], field)
                self.assertNotEqual(delivered['id'], original['id'])
                self.assertEqual(quality_info(delivered)['level'], recipe['to'])
                unchanged = normalize_quality(items[next(k for k, v in items.items() if v['id'] == original['id'])])
                self.assertEqual(unchanged['quality'], preview['item']['quality'])


if __name__ == '__main__':
    unittest.main()
