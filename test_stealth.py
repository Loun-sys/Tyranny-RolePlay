import copy
import math
import unittest
from unittest.mock import patch

from stealth_rules import advance_memory, detection_rate, observer_profile, game_perception
import test_combat_tactics
from npc_store import ability_library


class StealthTests(unittest.TestCase):
    def battle(self, distance=4, skill=24):
        c,d,s=test_combat_tactics.TacticalCombatTests().battle()
        d['effectiveSkills']['Хитроумие']=skill
        s.targets['enemy'].update(kind='npc',level=1,perceptionType=2,
            abilities=[next(a for a in ability_library() if a['key']=='ABL_DIS_BloodBound_DisablingKick')],
            attributes=c['attributes'],skills={'Атлетика':80},attack={'range':1,'accuracy':20,'damageMin':4,'damageMax':8})
        s.target_positions['enemy']=(1+distance,1)
        s.runtime_derived=d
        return c,d,s

    def act(self,c,d,s,**p):return s.act(p,c,d,[],2)
    def hide(self,c,d,s):return self.act(c,d,s,kind='tactic',name='Уйти в скрытность',targetId='player',x=1,y=1)

    def test_original_perception_profiles_are_complete(self):
        self.assertEqual(len(game_perception()),1023)
        for row in game_perception().values():self.assertIn(row['perceptionType'],range(5))

    def test_original_formula_and_types(self):
        self.assertEqual(detection_rate(4,5,24,24),17.5)
        self.assertTrue(math.isinf(detection_rate(1,5,24,24)))
        self.assertEqual(detection_rate(5,5,24,24),0)
        self.assertLess(detection_rate(4,5,24,72),detection_rate(4,5,24,24))
        self.assertEqual(observer_profile({'level':1,'perceptionType':0})['perception'],42)

    def test_decay_grace_and_chunking(self):
        memory={'value':100,'idle':0}
        self.assertEqual(advance_memory(memory,.5)['value'],100)
        whole=advance_memory(memory,3)
        chunks=advance_memory(advance_memory(memory,1),2)
        self.assertEqual(whole,chunks);self.assertEqual(whole['value'],66.25)

    def test_hide_spends_action_and_blocks_hostile_direct_targeting(self):
        c,d,s=self.battle();self.hide(c,d,s)
        self.assertTrue(s.stealthed);self.assertFalse(s.action_available)
        self.assertFalse(s.visible_to('enemy'))
        before=copy.deepcopy(s.__dict__)
        with self.assertRaisesRegex(ValueError,'скрыт'):
            s.master_npc_ability('enemy',s.targets['enemy']['abilities'][0]['key'],'player',c,d)
        self.assertEqual(s.player_health,before['player_health']);self.assertFalse(getattr(s,'npc_spent',{}))

    def test_ally_still_sees_player(self):
        c,d,s=self.battle();self.hide(c,d,s);s.targets['enemy']['team']='ally'
        self.assertTrue(s.visible_to('enemy'))

    def test_adjacent_enemy_prevents_hide_without_spending_action(self):
        c,d,s=self.battle(1)
        with self.assertRaisesRegex(ValueError,'вблизи'):self.hide(c,d,s)
        self.assertFalse(s.stealthed);self.assertTrue(s.action_available)

    def test_wall_blocks_detection_and_decay_is_per_observer(self):
        c,d,s=self.battle(3);s.grid.sight_blocked={(2,1)}
        self.hide(c,d,s);s.suspicion={'enemy':{'value':120,'idle':0}}
        self.act(c,d,s,kind='end_turn')
        self.assertTrue(s.stealthed);self.assertFalse(s.suspicion)

    def test_suspicion_crosses_search_then_detect_at_rounds(self):
        c,d,s=self.battle();self.hide(c,d,s)
        self.act(c,d,s,kind='end_turn')
        self.assertTrue(s.stealthed);self.assertEqual(s.suspicion['enemy']['value'],175)
        self.assertEqual(s.view(c,d,[],2)['stealth']['observers'][0]['state'],'investigating')
        self.act(c,d,s,kind='end_turn');self.assertFalse(s.stealthed)
        self.assertTrue(s.visible_to('enemy'));self.assertTrue(any('обнаруживает' in line for line in s.log))

    def test_view_and_previews_do_not_advance_suspicion_or_rng(self):
        c,d,s=self.battle();self.hide(c,d,s)
        before=copy.deepcopy(s.suspicion)
        with patch('training_combat.random.randint',side_effect=AssertionError('preview rolled')):
            one=s.view(c,d,[],2);two=s.view(c,d,[],2)
        self.assertEqual(one['stealth'],two['stealth']);self.assertEqual(s.suspicion,before)
        self.assertEqual(s.stealth_elapsed,0)
        self.assertEqual(one['grid']['tokens'][0]['id'],'player')

    def test_sneaking_movement_cost_and_exposure_budget(self):
        c,d,s=self.battle(8);self.hide(c,d,s)
        self.act(c,d,s,kind='move',x=1,y=3)
        self.assertEqual(s.movement_remaining,1);self.assertEqual(s.stealth_elapsed,8)
        self.assertTrue(s.stealthed)
        with self.assertRaises(ValueError):self.act(c,d,s,kind='move',x=1,y=4)
        self.act(c,d,s,kind='end_turn')
        self.assertEqual(s.movement_remaining,5);self.assertEqual(s.stealth_elapsed,0)

    def test_path_predictions_warn_before_reveal(self):
        c,d,s=self.battle();self.hide(c,d,s)
        view=s.view(c,d,[],2)
        route=view['grid']['movementPreviews']['3:1']
        self.assertTrue(route['stealthDetected'])
        self.assertTrue(s.stealthed)
        self.act(c,d,s,kind='move',x=3,y=1)
        self.assertFalse(s.stealthed)

    def test_attack_breaks_stealth_and_invalid_attack_does_not(self):
        c,d,s=self.battle();self.hide(c,d,s);s.action_available=True
        with self.assertRaises(ValueError):self.act(c,d,s,kind='attack',targetId='enemy')
        self.assertTrue(s.stealthed)
        s.target_positions['enemy']=(2,1)
        self.act(c,d,s,kind='attack',targetId='enemy');self.assertFalse(s.stealthed)

    def test_sprint_breaks_stealth_and_adds_five_once(self):
        c,d,s=self.battle();self.hide(c,d,s);self.act(c,d,s,kind='end_turn')
        self.act(c,d,s,kind='tactic',name='Спринт',targetId='player',x=1,y=1)
        self.assertFalse(s.stealthed);self.assertEqual(s.movement_remaining,10)

    def test_observers_have_independent_memory(self):
        c,d,s=self.battle();s.targets['other']=copy.deepcopy(s.targets['enemy'])
        s.target_healths['other']=1000;s.target_positions['other']=(9,9)
        self.hide(c,d,s);self.act(c,d,s,kind='end_turn')
        self.assertGreater(s.suspicion['enemy']['value'],0);self.assertNotIn('other',s.suspicion)

    def test_dummy_never_detects_and_hide_cannot_be_spammed(self):
        c,d,s=self.battle(1);s.targets['enemy'].pop('kind');self.hide(c,d,s)
        s.action_available=True
        with self.assertRaises(ValueError):self.hide(c,d,s)
        self.assertTrue(s.stealthed);self.assertTrue(s.action_available)


if __name__=='__main__':unittest.main()
