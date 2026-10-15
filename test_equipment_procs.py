import copy
import unittest
from unittest.mock import patch

from consumables import virtual_equipment
from equipment_runtime import WEAPON_CRIT_PROCS,weapon_crit_procs
from merchant_rules import runtime_warnings
from registration_api import _derived
from test_armor_runtime import armor
from test_talent_reactions import session


def strike(s,critical=True,weapon=True):
    with patch('training_combat.random.randint',side_effect=lambda lo,hi:hi):
        return s._roll_attack(name='Проверка оружия',accuracy=100 if critical else 0,
                             low=20,high=20,defense=0,armor=0,target_id='enemy',weapon_attack=weapon)


class EquipmentCritTests(unittest.TestCase):
    def prepared(self,prefab):
        item=armor(prefab);c,d,s=session(inventory=[item])
        s.runtime_derived=d;d['attack'].update(damageMin=20,damageMax=20,accuracy=100,criticalChance=0)
        return item,c,d,s

    def test_all_five_reviewed_graphs_are_supported(self):
        prefabs=['Leather_GLOVE_Submission_Gloves','Leather_GLOVE_Rare','UNIQUE_Leather_GLOVE_RockbiterVambraces',
                 'UNIQUE_Iron_GLOVE_SlugfistGauntlets','UNIQUE_Cloth_GLOVE_CensorsFaith']
        keys=set()
        for prefab in prefabs:
            item,c,d,s=self.prepared(prefab)
            rows=list(weapon_crit_procs([item],d));self.assertEqual(len(rows),1,prefab)
            self.assertFalse(runtime_warnings(item),prefab)
            keys.add(rows[0]['key'])
        self.assertEqual(keys,WEAPON_CRIT_PROCS)

    def test_suffering_reduces_every_skill_and_parry_once(self):
        item,c,d,s=self.prepared('Leather_GLOVE_Submission_Gloves')
        strike(s)
        states=s.conditions['enemy']
        self.assertTrue(any(e.get('source',{}).get('AffectsStat')==2098 for e in states.values()))
        effects=virtual_equipment(states,s.round_number)
        victim=_derived(c,effects)
        base=_derived(c,[])
        for skill in base['effectiveSkills']:
            self.assertEqual(victim['effectiveSkills'][skill],base['effectiveSkills'][skill]-10)
        self.assertEqual(victim['defenses']['Парирование'],base['defenses']['Парирование']-10)
        self.assertEqual(s._defense('Парирование','enemy'),0)  # Test dummy starts at zero.

    def test_rending_reduces_actual_armor_and_does_not_spend_action(self):
        _,_,_,s=self.prepared('UNIQUE_Leather_GLOVE_RockbiterVambraces')
        s.targets['enemy'].update(armor=5,armorByType={'Дробящий':5})
        strike(s)
        actual=s._attack_parameters(accuracy=0,defense=0,armor=5,target_id='enemy')
        self.assertEqual(actual['armor'],4)
        self.assertTrue(s.action_available);self.assertFalse(s.cooldowns)

    def test_multistrike_is_one_extra_strike_without_recursion(self):
        _,_,_,s=self.prepared('Leather_GLOVE_Rare')
        before=s.target_healths['enemy']
        hit=strike(s)
        self.assertEqual(len(s.events),2)
        self.assertEqual(before-s.target_healths['enemy'],45)  # 30 primary + 15 extra.
        self.assertEqual(hit['damage'],45)

    def test_weighted_crit_applies_prone(self):
        _,_,_,s=self.prepared('UNIQUE_Iron_GLOVE_SlugfistGauntlets')
        strike(s)
        self.assertIn('prone',s.conditions['enemy'])

    def test_kindling_crit_applies_real_periodic_fire_damage(self):
        _,_,_,s=self.prepared('UNIQUE_Cloth_GLOVE_CensorsFaith')
        strike(s)
        self.assertTrue(any(e.get('source',{}).get('AffectsStat')==25 for e in s.conditions['enemy'].values()))
        before=s.target_healths['enemy'];s._pulse_conditions('enemy',s.round_number,elapsed_seconds=1)
        self.assertLess(s.target_healths['enemy'],before)

    def test_normal_hit_and_non_weapon_spell_do_not_trigger_proc(self):
        for critical,weapon in [(False,True),(True,False)]:
            _,_,_,s=self.prepared('UNIQUE_Iron_GLOVE_SlugfistGauntlets')
            strike(s,critical,weapon)
            self.assertNotIn('prone',s.conditions.get('enemy',{}))
            self.assertEqual(len(s.events),1)

    def test_unequipped_or_quick_slotted_gloves_cannot_trigger(self):
        item,c,d,s=self.prepared('UNIQUE_Iron_GLOVE_SlugfistGauntlets')
        for slot in ['', 'Быстрый предмет 1','Мастерская']:
            item['equipped_slot']=slot
            self.assertEqual(list(weapon_crit_procs([item],d)),[])


if __name__=='__main__':unittest.main()
