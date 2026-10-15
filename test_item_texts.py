import copy
import json
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from item_texts import normalize_item_text, catalog_texts
from item_copy import adapt_item_copy, adapt_item_properties
from registration_api import master_faction_talents

class ItemTextTests(unittest.TestCase):
    def test_all_catalog_instructions_are_adapted_and_idempotent(self):
        forbidden = r'кузне Шпиля|лазарету Шпиля|библиотеке Шпиля|вашей библиотеке|ваши Книгочеи|достаточно веры'
        changed = 0
        for source in json.loads(Path('catalog/game_items.json').read_text(encoding='utf-8')):
            item = catalog_texts()[0][source['properties']['gameData']['prefab']]
            for field in ('description','lore'):
                with self.subTest(item=item['name'],field=field):
                    self.assertNotRegex(item[field], forbidden)
                    self.assertEqual(item[field], adapt_item_copy(item[field]))
                    changed += adapt_item_copy(source[field]) != source[field].strip()
        self.assertGreater(changed, 40)

    def test_recipe_crafting_uses_background_not_player_owned_facilities(self):
        rows = catalog_texts()[0]
        potion = rows['LibraryResearch_Potion_Invisibility']['lore']
        self.assertEqual(potion, 'По этому рецепту Скованный Ремеслом может изготовить зелье невидимости при наличии нужных ингредиентов.')
        self.assertIn('Скованный Ремеслом может изготовить', rows['Recipe_Book_Forge_Skorn']['lore'])
        self.assertIn('таинственный металл', rows['Recipe_Book_Forge_Skorn']['lore'])
        self.assertIn('Скованный Ремеслом может улучшить', rows['WPN_1H_IR_Dagger_Lantry']['lore'])
        self.assertIn('неполон и требует дальнейшего изучения', rows['Research_Scroll_Library_Baneward']['lore'])
        self.assertIn('нужные сигилы', rows['LibraryResearch_Artifact_HeartsBlood']['lore'])
        self.assertNotIn('нанесете', rows['LibraryResearch_Artifact_HeartsBlood']['lore'])

    def test_source_metadata_and_real_world_lore_are_not_removed(self):
        props = {'gameData':{'localizedDescription':'Изготовить в кузне Шпиля.', 'Value':2.5},
                 'Примечание':['Вы можете скрафтить меч в своей кузне.', {'Текст':'Вы можете изучить рецепт в своей библиотеке.'}],
                 'Броня':3}
        original = copy.deepcopy(props)
        result = adapt_item_properties(props)
        self.assertEqual(props, original)
        self.assertEqual(result['gameData'], original['gameData'])
        self.assertEqual(result['Броня'], 3)
        self.assertEqual(result['Примечание'][0], 'Скованный Ремеслом может скрафтить меч.')
        for text in ('Оружие выковано из материалов Горящей Библиотеки.',
                     'Легенды рассказывают о Шпиле, который множество раз поражало молнией.',
                     'Кузнец работал в кузне много лет.'):
            self.assertEqual(adapt_item_copy(text), text)

    def test_existing_crafted_and_custom_items_receive_adapted_copy(self):
        source = copy.deepcopy(catalog_texts()[0]['WPN_1H_IR_Dagger_Lantry'])
        source.update(source_url='craft://123', quality='Выдающееся', damage_min=99)
        result = normalize_item_text(source)
        self.assertIn('Скованный Ремеслом', result['lore'])
        self.assertNotIn('кузне Шпиля', result['lore'])
        self.assertEqual(result['damage_min'], 99)
        custom = normalize_item_text({'name':'Особый рецепт', 'lore':'Вы можете изготовить меч в своей кузне.',
                                      'properties':json.dumps({'Примечание':'Улучшите его в своей кузнице.'},ensure_ascii=False)})
        self.assertEqual(custom['lore'], 'Скованный Ремеслом может изготовить меч.')
        self.assertNotIn('своей кузнице', custom['properties']['Примечание'])

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
    async def test_public_catalog_adapts_legacy_stored_recipe_copy(self):
        from registration_api import player_catalog
        prefabs = {'LibraryResearch_Potion_Invisibility','Recipe_Book_Forge_Skorn','WPN_1H_IR_Dagger_Lantry'}
        # Simulate rows still containing the original game text in the DB.
        rows = [i for i in json.loads(Path('catalog/game_items.json').read_text(encoding='utf-8'))
                if i['properties']['gameData']['prefab'] in prefabs]
        original = copy.deepcopy(rows)
        request = SimpleNamespace(query={},app={'db':object()})
        with patch('catalog_browser.browse',AsyncMock(return_value={'items':rows})):
            response = await player_catalog(request)
        result = json.loads(response.text)
        self.assertEqual(rows, original)
        self.assertEqual(len(result['items']), 3)
        for item in result['items']:
            self.assertIn('Скованный Ремеслом', item['lore'])
            self.assertNotRegex(item['lore'], r'кузне Шпиля|лазарету Шпиля|библиотеке Шпиля')
            self.assertNotIn('gameData', item['properties'])

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
