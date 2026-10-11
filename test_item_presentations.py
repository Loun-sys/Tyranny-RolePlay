"""Every source item can be inspected without exposing raw Unity component trees."""
import copy
import json
import unittest
from item_presentations import readout
from item_texts import catalog_texts
from registration_api import _clean_inventory


class ItemPresentationTests(unittest.TestCase):
    def item(self, name):
        return copy.deepcopy(catalog_texts()[1][name.casefold()])

    def test_all_source_items_have_serializable_inspection(self):
        for item in catalog_texts()[0].values():
            with self.subTest(item=item['name']):
                result=readout(item)
                self.assertTrue(result['type'])
                text=json.dumps(result, ensure_ascii=False)
                self.assertNotIn('m_PathID', text)
                self.assertNotIn('AttackPrefab', text)

    def test_thief_armor_matches_grouped_source_resistances_and_ten_conditions(self):
        item=self.item('Доспехи вора')
        details=readout(item)
        self.assertEqual(details['type'], 'Легкая броня (Кожа)')
        self.assertIn({'value':5.25,'types':['Рубящий','Дробящий']},details['armorGroups'])
        self.assertIn({'value':0,'types':['Колющий','Огненный']},details['armorGroups'])
        self.assertEqual(details['bonuses']['Отражение'],12)
        mod=details['modifiers'][0]
        self.assertEqual(mod['name'],'Авантюрист')
        self.assertEqual(len(mod['effects']),10)
        self.assertTrue(all(line.endswith('+20%') for line in mod['effects']))
        self.assertIn('«Повреждение брони»',mod['effects'][-1])

    def test_phalanster_crit_buff_is_explicit_and_round_adapted(self):
        result=readout(self.item('Фаланстер'))
        mod=result['modifiers'][0]
        self.assertEqual(mod['name'],'Защитный удар')
        self.assertIn('При критическом попадании оружием:',mod['effects'])
        self.assertIn('Парирование: +5 на 1 раунд',mod['effects'])
        self.assertIn('Радиус: 2.5 м',mod['effects'])
        self.assertEqual(result['skill'],'Одноручное оружие')

    def test_no_description_is_not_replaced_with_filler(self):
        item=_clean_inventory([self.item('Бронзовый кинжал')])[0]
        self.assertEqual(item['description'],'')
        self.assertEqual(item['lore'],'')
        self.assertEqual(item['inspection']['modifiers'],[])
        self.assertTrue(item['weaponStats']['accuracyBonus'])

    def test_consumables_show_same_effects_as_the_runtime(self):
        from consumables import profile
        item=self.item('Зелье героев')
        result=readout(item)
        self.assertTrue(result['useEffects'])
        self.assertEqual('; '.join(result['useEffects']),profile(item)['description'])

    def test_gui_display_only_effects_and_modified_abilities_are_not_empty(self):
        result=readout(self.item('Морозный Укус'))
        mod=next(m for m in result['modifiers'] if m['name']=='Холод')
        self.assertIn('крадете у противника +3 к броне',mod['effects'][0])
        result=readout(self.item('Нагрудник Командира'))
        mod=next(m for m in result['modifiers'] if m['name']=='Властность')
        self.assertIn('Перезарядка способности: -20%',mod['effects'])
        self.assertIn('Дистанция: +4 м',mod['effects'])
        for item in catalog_texts()[0].values():
            for modifier in readout(item)['modifiers']:
                self.assertTrue(modifier['effects'] or modifier['description'], (item['name'],modifier['name']))

    def test_cloth_and_heavy_categories_are_game_enums_not_invented(self):
        self.assertEqual(readout(self.item('Одежда из ткани'))['type'],'Легкая броня (Ткань)')
        self.assertEqual(readout(self.item('Тяжелый бронзовый шлем с гребнем'))['type'],'Тяжелая броня (Бронза)')


if __name__ == '__main__':
    unittest.main()
