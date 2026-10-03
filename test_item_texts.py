import copy
import json
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from item_texts import normalize_item_text, catalog_texts
from registration_api import master_faction_talents

class ItemTextTests(unittest.TestCase):
    def test_all_game_copy_has_no_placeholders_or_transliteration(self):
        for item in catalog_texts()[0].values():
            text = json.dumps({k:v for k,v in item.items() if k in {'name','description','lore'}},ensure_ascii=False)
            self.assertNotIn('предмет из игры',text.lower())
            self.assertNotIn('fandom.com',text)
            self.assertNotIn('Аттрибуте',json.dumps({k:v for k,v in item['properties'].items() if k!='gameData'},ensure_ascii=False))

    def test_potion_effects_are_actual_russian_attributes(self):
        potion = catalog_texts()[1]['зелье героев']
        self.assertIn('Сила: +2 на 6 раундов',potion['properties']['При использовании'])
        self.assertIn('Живучесть: +2',potion['properties']['При использовании'])

    def test_absent_history_is_empty_not_copied_stats(self):
        item = copy.deepcopy(catalog_texts()[1]['короткий лук'])
        item['lore'] = item['description'] = 'Варренс короткий лук — предмет из игры «Тирания». Урон: 11–14'
        item['properties']['Эффект'] = 'еверй Аттрибуте'
        item['properties']['gameData'].pop('localizedText')
        result = normalize_item_text(item)
        self.assertEqual(result['name'],'Короткий лук')
        self.assertEqual(result['lore'],'')
        self.assertEqual(result['description'],'')
        self.assertNotIn('Эффект',result['properties'])

    def test_crafted_variant_preserves_stats_and_cleans_history(self):
        item = copy.deepcopy(catalog_texts()[1]['короткий лук'])
        item.update(source_url='craft://123',quality='Безупречное',damage_min=99,lore='мусор')
        item['properties']['gameData']['craftBaseName']='Варренс короткий лук'
        result = normalize_item_text(item)
        self.assertEqual(result['name'],'Короткий лук (Безупречное)')
        self.assertEqual(result['damage_min'],99)
        self.assertEqual(result['lore'],'')

    def test_faction_catalog_can_be_granted_as_regular_talent(self):
        row = {'name':'Талант','faction':'Фракция','tier':2,'description':'Эффект'}
        result = master_faction_talents(SimpleNamespace(app={'extended_talents':{'factions':[row]}}))
        self.assertEqual(result[0]['tree'],'Фракционные · Фракция')
        self.assertNotIn('tree',row)

    def test_player_tabs_and_source_links_removed(self):
        html = Path('web/archive.html').read_text(encoding='utf-8')
        self.assertNotIn('data-tab="factions"',html)
        self.assertNotIn('player-npcs.js',html)
        self.assertNotIn('wiki-link',Path('web/archive.js').read_text(encoding='utf-8'))

class MasterTalentApiTests(unittest.IsolatedAsyncioTestCase):
    async def test_faction_grants_are_available_to_master(self):
        from registration_api import admin_character
        row = {'name':'Дар','faction':'Опальные','tier':1,'description':'Эффект'}
        db = SimpleNamespace(get_character_by_id=AsyncMock(return_value={'user_id':5}))
        request = SimpleNamespace(app={'db':db,'extended_talents':{'factions':[row]}})
        with patch('registration_api._admin_character',AsyncMock(return_value=(1,5,7))), patch('registration_api._dashboard',AsyncMock(return_value={'character':{}})):
            response = await admin_character(request)
        data = json.loads(response.text)
        self.assertEqual(data['masterFactionTalents'][0]['tree'],'Фракционные · Опальные')

    async def test_public_archive_does_not_receive_master_catalog(self):
        from registration_api import archive_character
        request = SimpleNamespace(match_info={'character_id':'7'})
        with patch('registration_api._dashboard',AsyncMock(return_value={'character':{}})):
            response = await archive_character(request)
        self.assertNotIn('masterFactionTalents',json.loads(response.text))

if __name__ == '__main__': unittest.main()
