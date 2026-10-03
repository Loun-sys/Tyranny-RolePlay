import copy
import json
import unittest
from pathlib import Path
from item_effects import equip_bonuses,equip_modifiers,armor_by_type
from item_texts import catalog_texts,normalize_item_text
from crafting import normalize_quality
from registration_api import _derived,_apply_property

class EquipmentStatsTests(unittest.TestCase):
    def item(self,name):return copy.deepcopy(catalog_texts()[1][name.casefold()])
    def test_source_coverage_and_icons(self):
        audit=json.loads(Path('catalog/game_item_audit.json').read_text(encoding='utf-8'))
        self.assertEqual(audit['sourcePrefabs'],audit['imported']+len(audit['excluded']))
        self.assertEqual(audit['missingImported'],[])
        for row in catalog_texts()[0].values():
            self.assertEqual(row['properties']['gameData']['statsVersion'],2,row['name'])
            self.assertTrue((Path('web')/row['image_url']).is_file(),row['name'])
    def test_fractional_heavy_helmet_not_zero(self):
        item=self.item('Тяжелый бронзовый шлем с гребнем')
        self.assertEqual(item['armor'],.5)
        self.assertGreater(armor_by_type(item)['Рубящий'],0)
    def test_cloth_zero_armor_still_has_deflection(self):
        item=self.item('Суконные обмотки для ног')
        self.assertEqual(item['armor'],0)
        self.assertEqual(equip_bonuses(item)['Отражение'],1)
    def test_actual_school_skill_and_attribute(self):
        bonus=equip_bonuses(self.item('Загадка Книгочея'))
        self.assertEqual(bonus['Смекалка'],1)
        self.assertEqual(bonus['Управление иллюзиями'],10)
    def test_typed_resistance_not_global_armor(self):
        item=self.item('Обугленный кожаный ремень')
        self.assertEqual(equip_bonuses(item).get('Броня',0),0)
        self.assertEqual(equip_modifiers(item)['armorByType']['Огненный'],10)
    def test_multipliers_and_probability_units(self):
        item=self.item('Дубленая шкура кровокогтя')
        self.assertAlmostEqual(_apply_property(100,[item],'Максимум здоровья'),110,places=3)
        crit=self.item('Самоцвет удачи')
        self.assertAlmostEqual(equip_bonuses(crit)['Критический шанс'],5,places=3)
    def test_inactive_weapon_and_quick_item_do_not_grant_stats(self):
        char={'attributes':dict.fromkeys(['Сила','Искусность','Быстрота','Живучесть','Смекалка','Стойкость'],10),'skills':{'Безоружный бой':{'value':20},'Управление иллюзиями':{'value':20}},'active_weapon_set':1,'health_max':20}
        helmet=self.item('Загадка Книгочея')
        for slot in ['Оружие II — правая рука','Быстрый предмет 1','Мастерская']:
            helmet['equipped_slot']=slot
            self.assertEqual(_derived(char,[helmet])['effectiveSkills']['Управление иллюзиями'],20)
        helmet['equipped_slot']='Голова'
        # +10 skill and +1 Wits -> +2 attribute contribution after game rounding.
        self.assertEqual(_derived(char,[helmet])['effectiveSkills']['Управление иллюзиями'],32)
    def test_upgrade_preserves_components_and_round_units(self):
        upgraded=normalize_quality(self.item('Суконные обмотки для ног'),5)
        self.assertEqual(equip_bonuses(upgraded)['Отражение'],upgraded['properties']['gameData']['qualityStats']['Defensive_DeflectionBonus'])
        self.assertEqual(upgraded['recovery'],upgraded['properties']['gameData']['qualityStats']['RecoveryModifier']/10)
    def test_legacy_variant_gets_new_source_and_keeps_quality(self):
        item=self.item('Тяжелый бронзовый шлем с гребнем')
        item.update(source_url='craft://test',quality='Безупречное',armor=999)
        game=item['properties']['gameData'];game['craftQuality']['level']=5;game.pop('statsVersion')
        result=normalize_item_text(item)
        self.assertEqual(result['quality'],'Безупречное')
        self.assertNotEqual(result['armor'],999)
        self.assertEqual(result['properties']['gameData']['statsVersion'],2)
    def test_discord_and_site_use_same_stats_without_double_application(self):
        from combat import Combatant,apply_equipment
        item=self.item('Загадка Книгочея');item['equipped_slot']='Голова'
        attrs=dict.fromkeys(['Сила','Искусность','Быстрота','Живучесть','Смекалка','Стойкость'],10)
        unit=Combatant(key='test',name='test',team='test',health=100,health_max=100,attributes=attrs,skills={'Безоружный бой':20,'Управление иллюзиями':20},inventory=[item])
        apply_equipment(unit);self.assertEqual(unit.attributes['Смекалка'],11)
        self.assertEqual(unit.skills['Управление иллюзиями'],32)
        apply_equipment(unit);self.assertEqual(unit.skills['Управление иллюзиями'],32)

if __name__=='__main__':unittest.main()
