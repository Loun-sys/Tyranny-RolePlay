import copy
import unittest
from unittest.mock import patch

from item_effects import armor_by_type
from item_presentations import readout
from merchant_rules import runtime_warnings
from registration_api import _derived
from test_armor_runtime import armor
from test_consumables import character
from test_talent_reactions import session


class ArmorConditionTests(unittest.TestCase):
    def test_low_health_parry_uses_actual_health_and_can_expire(self):
        gear=armor('Bronze_Armor_Rare')
        c=character();c['health']=49
        d=_derived(c,[gear]);base=_derived(c,[])
        self.assertEqual(d['defenses']['Парирование'],base['defenses']['Парирование']+15)
        c['health']=90
        self.assertEqual(_derived(c,[gear])['defenses']['Парирование'],base['defenses']['Парирование'])
        _,_,s=session()
        s.targets['enemy'].update(inventory=[gear],defenses={'Парирование':20},equipmentConditionalHealthFraction=1)
        s.target_healths['enemy']=400
        self.assertEqual(s._defense('Парирование','enemy'),35)
        s.target_healths['enemy']=900
        self.assertEqual(s._defense('Парирование','enemy'),20)

    def test_health_damage_bonus_activates_and_expires_without_double_counting(self):
        gear=armor('Cloth_HELM_Rare')
        c,d,s=session(inventory=[gear])
        # Derived already contains the full-health +10%; do not apply it twice.
        p=s._attack_parameters(accuracy=0,defense=0,armor=0,target_id='enemy')
        self.assertAlmostEqual(p['multiplier'],1)
        s.player_health=100
        p=s._attack_parameters(accuracy=0,defense=0,armor=0,target_id='enemy')
        self.assertAlmostEqual(p['multiplier'],1/1.1)
        self.assertFalse(runtime_warnings(gear))

    def test_wounded_preview_uses_its_own_derived_snapshot_not_previous_turn(self):
        gear=armor('Cloth_HELM_Rare')
        c,full,s=session(inventory=[gear])
        c['health']=100;s.player_health=100
        wounded=_derived(c,[gear]);s.runtime_derived=full
        p=s._attack_parameters(accuracy=0,defense=0,armor=0,target_id='enemy',source_derived=wounded)
        self.assertEqual(p['multiplier'],1)

    def test_wounds_enable_armor_once_not_per_wound(self):
        gear=armor('UNIQUE_Leather_Armor_GlorySeekersLeathers')
        c=character();base=_derived(c,[gear])
        c['wounds']=1;wounded=_derived(c,[gear])
        c['wounds']=4;more=_derived(c,[gear])
        self.assertEqual(wounded['armor'],base['armor']+2)
        self.assertEqual(wounded['armorByType'],{k:v+2 for k,v in base['armorByType'].items()})
        self.assertEqual(more['armor'],wounded['armor'])
        self.assertFalse(runtime_warnings(gear))

    def test_unbroken_legacy_grants_resolve_and_accuracy_only_while_wounded(self):
        gear=armor('UNIQUE_Bronze_Armor_UnbrokenLegacy')
        c=character();base=_derived(c,[gear]);c['wounds']=1
        d=_derived(c,[gear])
        self.assertEqual(d['effectiveAttributes']['Стойкость'],base['effectiveAttributes']['Стойкость']+2)
        self.assertEqual(d['attack']['accuracy'],base['attack']['accuracy']+10)
        c['wounds']=0
        self.assertEqual(_derived(c,[gear])['attack']['accuracy'],base['attack']['accuracy'])

    def test_periodic_healing_and_unequipping(self):
        gear=armor('Iron_BOOTS_Greaves_of_the_Endless_March')
        _,_,s=session(inventory=[gear]);s.player_health=100
        s._pulse_conditions('player',1,elapsed_seconds=10)
        self.assertEqual(s.player_health,120)
        s.consumable_inventory=[]
        s._pulse_conditions('player',2,elapsed_seconds=10)
        self.assertEqual(s.player_health,120)
        self.assertFalse(runtime_warnings(gear))

    def test_wound_regeneration_is_not_a_free_permanent_heal_or_resurrection(self):
        gear=armor('Bronze_GLOVE_Rare')
        _,_,s=session(inventory=[gear]);s.player_health=100
        s._pulse_conditions('player',1,elapsed_seconds=10)
        self.assertEqual(s.player_health,100)
        s.runtime_character['wounds']=1
        s._pulse_conditions('player',2,elapsed_seconds=10)
        self.assertEqual(s.player_health,140)
        s.player_health=0
        s._pulse_conditions('player',3,elapsed_seconds=10)
        self.assertEqual(s.player_health,0)

    def test_equipment_regeneration_respects_receiving_healing_multiplier(self):
        gear=armor('Iron_BOOTS_Greaves_of_the_Endless_March')
        _,_,s=session(inventory=[gear]);s.player_health=100
        s.conditions['player']={'healing':{'name':'Усиление лечения','consumable':True,'until':3,'source':{'AffectsStat':169,'Value':1.5,'Apply':0}}}
        s._pulse_conditions('player',1,elapsed_seconds=10)
        self.assertEqual(s.player_health,130)
        self.assertIn('экипировка восстанавливает 30',s.log[-1])

    def test_mirror_boots_reflect_real_crafted_spell_but_not_weapon(self):
        gear=armor('Bronze_BOOTS_Rare')
        _,_,s=session();s.targets['enemy']['inventory']=[gear]
        args=dict(accuracy=0,defense=0,armor=0,target_id='enemy',attack_mode='magic-ranged')
        p=s._attack_parameters(**args,crafted_spell=True)
        self.assertEqual(p['reflections'],{1:.1,2:.1,3:.1})
        self.assertFalse(any(s._attack_parameters(**args)['reflections'].values()))
        hp=s.player_health;target=s.target_healths['enemy']
        with patch('training_combat.random.randint',side_effect=lambda lo,hi:hi),patch('training_combat.random.random',return_value=0):
            result=s._roll_attack(name='Искра',low=20,high=20,crafted_spell=True,**args)
        self.assertEqual(s.player_health,hp-20)
        self.assertEqual(s.target_healths['enemy'],target)
        self.assertEqual(result['result'],'Отражено')

    def test_starting_breath_is_granted_once_from_helmet(self):
        gear=armor('vx1_art_Cloth_HELM_Songbirds_Encore')
        c,d,s=session(inventory=[gear])
        self.assertEqual(s.breath,1)
        s.view(c,d,[],2)
        self.assertEqual(s.breath,1)

    def test_inspection_displays_adjusted_value_and_real_condition(self):
        for key,text in [('Bronze_Armor_Rare','При здоровье ниже 50%: Парирование: +15'),
                         ('UNIQUE_Leather_Armor_GlorySeekersLeathers','При наличии травмы: Броня: +2')]:
            details=readout(armor(key))
            self.assertTrue(any(text in line for mod in details['modifiers'] for line in mod['effects']),key)

    def test_rogues_leathers_use_exact_afflictions_and_source_additive_stacking(self):
        gear=armor('UNIQUE_Leather_Armor_RoguesLeathers')
        _,_,s=session(inventory=[gear])
        def multiplier():return s._attack_parameters(accuracy=0,defense=0,armor=0,target_id='enemy')['multiplier']
        self.assertEqual(multiplier(),1)
        s.conditions['enemy']={'stun':{'until':2}}
        self.assertAlmostEqual(multiplier(),1.2)
        s.conditions['enemy']['bleeding']={'source':{'affliction':'Aff_Bleeding'},'until':2}
        self.assertAlmostEqual(multiplier(),1.4,places=6)
        s.conditions['enemy']['bleeding2']=copy.deepcopy(s.conditions['enemy']['bleeding'])
        self.assertAlmostEqual(multiplier(),1.4,places=6)
        s.conditions['enemy']={'curse':{'source':{'Value':-10,'AffectsStat':185},'until':2}}
        self.assertEqual(multiplier(),1)
        self.assertFalse(runtime_warnings(gear))


if __name__=='__main__':unittest.main()
