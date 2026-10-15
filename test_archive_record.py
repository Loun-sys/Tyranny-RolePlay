"""Public dossiers expose read-only inventories/trees, not owner controls/data."""
import copy
import unittest
from unittest.mock import AsyncMock, patch

from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

from registration_api import archive_character


class ArchiveRecordTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        app = web.Application()
        app.router.add_get('/api/archive/{character_id}', archive_character)
        self.client = TestClient(TestServer(app))
        await self.client.start_server()

    async def asyncTearDown(self):
        await self.client.close()

    async def test_public_projection_keeps_equipment_and_full_class_trees(self):
        payload = {
            'character': {'name': 'Чужой персонаж', 'notes': 'private',
                          'attribute_points': 2, 'talent_points': 1, 'rewarded_level': 4,
                          'talents': [{'name': 'Изученный талант'}]},
            'inventory': [{'inventory_id': 7, 'name': 'Меч', 'equipped_slot': 'Оружие I — правая рука',
                           'notes': 'private item note', 'weaponStats': {'damageMin': 9}},
                          {'inventory_id': 8, 'name': 'Зелье', 'quantity': 2}],
            'talentLibrary': [{'name': 'Изученный талант', 'tree': 'Сила'},
                              {'name': 'Неизученный талант', 'tree': 'Сила'}],
            'learnedTalents': [{'name': 'Изученный талант', 'mechanics': {'effects': ['+2 к Силе']}}],
            'sigils': {'knownKeys': ['private']}, 'recipients': [{'user_id': 99}],
            'combatQuickbar': [{'slot': 1}], 'derived': {'effectiveSkills': {'Атлетика': 42}},
        }
        with patch('registration_api._dashboard', AsyncMock(return_value=copy.deepcopy(payload))) as dashboard:
            response = await self.client.get('/api/archive/23')
        self.assertEqual(response.status, 200)
        dashboard.assert_awaited_once()
        self.assertEqual(dashboard.await_args.args[1], 23)
        actual = await response.json()
        self.assertEqual(len(actual['talentLibrary']), 2)
        self.assertEqual(actual['inventory'][0]['weaponStats']['damageMin'], 9)
        self.assertEqual(actual['inventory'][0]['equipped_slot'], 'Оружие I — правая рука')
        self.assertEqual(actual['inventory'][1]['quantity'], 2)
        self.assertEqual(actual['derived'], payload['derived'])
        self.assertEqual(actual['learnedTalents'], payload['learnedTalents'])
        for field in ('notes', 'attribute_points', 'talent_points', 'rewarded_level'):
            self.assertNotIn(field, actual['character'])
        self.assertNotIn('notes', actual['inventory'][0])
        for field in ('sigils', 'recipients', 'combatQuickbar'):
            self.assertNotIn(field, actual)

    async def test_public_url_never_accepts_character_mutations(self):
        with patch('registration_api._dashboard', AsyncMock()) as dashboard:
            response = await self.client.post('/api/archive/23', json={'kind': 'equipment', 'inventoryId': 7})
        self.assertEqual(response.status, 405)
        dashboard.assert_not_awaited()


if __name__ == '__main__':
    unittest.main()
