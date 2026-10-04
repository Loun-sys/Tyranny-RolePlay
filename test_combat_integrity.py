import copy
import unittest
from unittest.mock import patch

from ability_rules import resolve
from registration_api import _derived
from tactical_grid import TacticalGrid
from test_talent_runtime import actor
from training_combat import DUMMY, TrainingSession


class CombatIntegrityTests(unittest.TestCase):
    def setup_battle(self, *keys):
        c=actor(*keys);c.update(health=100,health_max=100)
        s=TrainingSession(1);s.grid=TacticalGrid(12,12)
        s.player_position=(1,1)
        s.targets={'enemy':{**copy.deepcopy(DUMMY),'healthMax':1000,'armor':0},
                   'ally':{**copy.deepcopy(DUMMY),'name':'Союзник','team':'ally','healthMax':100}}
        s.target_positions={'enemy':(2,1),'ally':(3,1)}
        s.target_healths={'enemy':1000,'ally':100}
        s.selected_target_id='enemy'
        d=_derived(c,[]);s.view(c,d,[],2)
        return c,s,d

    def act(self,c,s,d,payload,spells=None):
        return s.act(payload,c,d,spells or [],2)

    def spell(self,expression='Дальний удар',core='Огонь'):
        return {'name':'Испытание','core':core,'expression':expression,'accents':[],'enhancements':[]}

    def test_fractional_boolean_missing_and_outside_coordinates_rejected_without_resources(self):
        c,s,d=self.setup_battle()
        for point in [{'x':1.9,'y':2},{'x':True,'y':2},{'x':1},{'x':-1,'y':2},{'x':99,'y':2},{'x':'bad','y':2}]:
            with self.subTest(point=point),self.assertRaises(ValueError):self.act(c,s,d,{'kind':'move',**point})
            self.assertEqual(s.player_position,(1,1));self.assertEqual(s.movement_remaining,5)
            self.assertTrue(s.action_available);self.assertIsNone(s.aim_point)

    def test_living_ally_blocks_movement_and_preview(self):
        c,s,d=self.setup_battle()
        with self.assertRaises(ValueError):self.act(c,s,d,{'kind':'move','x':3,'y':1})
        self.assertEqual(s.player_position,(1,1))
        self.assertNotIn((3,1),s.grid.reachable(s.player_position,s.movement_remaining,s._occupied('player')))

    def test_attack_aim_uses_clicked_enemy_not_previous_selection(self):
        c,s,d=self.setup_battle();s.targets['other']=copy.deepcopy(s.targets['enemy'])
        s.target_positions['other']=(1,2);s.target_healths['other']=1000
        with patch('training_combat.random.randint',side_effect=lambda lo,hi:hi):
            self.act(c,s,d,{'kind':'attack','x':1,'y':2})
        self.assertEqual(s.target_healths['enemy'],1000)
        self.assertLess(s.target_healths['other'],1000)
        self.assertEqual(s.selected_target_id,'other');self.assertFalse(s.action_available)

    def test_empty_attack_cell_and_conflicting_target_are_rejected(self):
        c,s,d=self.setup_battle()
        for payload in [{'kind':'attack','x':1,'y':2},{'kind':'attack','targetId':'enemy','x':1,'y':2}]:
            with self.assertRaises(ValueError):self.act(c,s,d,payload)
        self.assertEqual(s.target_healths['enemy'],1000);self.assertTrue(s.action_available)

    def test_unknown_and_friendly_attack_ids_cannot_damage_tokens(self):
        c,s,d=self.setup_battle()
        for target in ['missing','ally','player']:
            with self.assertRaises(ValueError):self.act(c,s,d,{'kind':'attack','targetId':target})
        self.assertEqual(s.target_healths,{'enemy':1000,'ally':100})

    def test_self_spell_accepts_player_id_from_ui_and_spends_one_action(self):
        c,s,d=self.setup_battle();spell=self.spell('Охранная форма')
        self.act(c,s,d,{'kind':'spell','name':spell['name'],'targetId':'player','x':1,'y':1},[spell])
        self.assertFalse(s.action_available);self.assertGreater(s.remaining('spell:'+spell['name']),0)
        self.assertIsNone(s.aim_point)

    def test_friendly_unit_preview_and_server_both_target_ally(self):
        key='Abl_PC_Leadership_SwapPositions'
        c,s,d=self.setup_battle(key)
        action=next(a for a in s.view(c,d,[],2)['actions'] if a.get('key')==key)
        self.assertTrue(action['aims']['3:1']['valid'])
        self.assertEqual(action['aims']['3:1']['targetIds'],['ally'])
        self.assertFalse(action['aims']['2:1']['valid'])
        self.act(c,s,d,{'kind':'ability','name':key,'targetId':'ally','x':3,'y':1})
        self.assertEqual(s.player_position,(3,1));self.assertEqual(s.target_positions['ally'],(1,1))
        self.assertFalse(s.action_available)

    def test_friendly_unit_cannot_swap_with_enemy_and_preserves_budget(self):
        key='Abl_PC_Leadership_SwapPositions'
        c,s,d=self.setup_battle(key)
        with self.assertRaises(ValueError):self.act(c,s,d,{'kind':'ability','name':key,'targetId':'enemy'})
        self.assertEqual(s.player_position,(1,1));self.assertTrue(s.action_available)
        self.assertFalse(s.cooldowns)

    def test_previous_distant_target_does_not_disable_nearby_friendly_aim(self):
        key='Abl_PC_Leadership_SwapPositions'
        c,s,d=self.setup_battle(key);s.target_positions['enemy']=(11,11)
        action=next(a for a in s.view(c,d,[],2)['actions'] if a.get('key')==key)
        self.assertFalse(action['disabledReason'])
        self.assertTrue(action['aims']['3:1']['valid'])
        self.assertEqual(action['aims']['3:1']['targetIds'],['ally'])

    def test_push_stops_before_ally_occupied_cell(self):
        key='Abl_Comp_RngMagic_RepellingBlast'
        c,s,d=self.setup_battle(key)
        with patch('training_combat.random.randint',side_effect=lambda lo,hi:hi):
            self.act(c,s,d,{'kind':'ability','name':key,'targetId':'enemy'})
        self.assertEqual(s.target_positions['enemy'],(2,1))
        self.assertEqual(s.target_positions['ally'],(3,1))

    def test_partial_executor_failure_rolls_back_damage_cooldown_position_and_log(self):
        key='Abl_Comp_RngMagic_RepellingBlast'
        c,s,d=self.setup_battle(key);before=copy.deepcopy(s.__dict__)
        with patch('training_combat.random.randint',side_effect=lambda lo,hi:hi),patch.object(TrainingSession,'_apply_ability_effects',side_effect=RuntimeError('effect failure')):
            with self.assertRaises(RuntimeError):self.act(c,s,d,{'kind':'ability','name':key,'targetId':'enemy'})
        for field in ['target_healths','target_positions','conditions','action_available','cooldowns','damage_total','attacks','hits','log','breath']:
            self.assertEqual(getattr(s,field),before[field],field)
        self.assertIsNone(s.aim_point)

    def test_move_through_and_out_of_control_zone_triggers_opportunity(self):
        c,s,d=self.setup_battle();s.player_position=(0,1);s.target_positions['ally']=(10,10)
        with patch('training_combat.random.randint',side_effect=lambda lo,hi:hi):
            result=self.act(c,s,d,{'kind':'move','x':4,'y':1})
        self.assertIn('атаку по возможности',result['line'])
        self.assertLess(s.player_health,s.player_health_max)
        self.assertEqual(s.player_position,(4,1))

    def test_each_enemy_has_only_one_opportunity_per_round(self):
        c,s,d=self.setup_battle();s.target_positions['ally']=(10,10)
        with patch('training_combat.random.randint',return_value=1):
            first=self.act(c,s,d,{'kind':'move','x':0,'y':1})
            self.act(c,s,d,{'kind':'move','x':1,'y':1})
            second=self.act(c,s,d,{'kind':'move','x':0,'y':1})
        self.assertIn('атаку по возможности',first['line']);self.assertNotIn('атаку по возможности',second['line'])
        self.act(c,s,d,{'kind':'end_turn'})
        self.assertFalse(s.opportunity_used)
        self.assertEqual(s.movement_remaining,5);self.assertTrue(s.action_available)

    def test_disengage_protects_every_move_until_end_of_turn(self):
        c,s,d=self.setup_battle();s.target_positions['ally']=(10,10)
        self.act(c,s,d,{'kind':'disengage'})
        for x in [0,1,0]:
            result=self.act(c,s,d,{'kind':'move','x':x,'y':1})
            self.assertNotIn('атаку по возможности',result['line'])
        self.assertTrue(s.disengaged)
        self.act(c,s,d,{'kind':'end_turn'});self.assertFalse(s.disengaged)

    def test_stunned_character_cannot_disengage(self):
        c,s,d=self.setup_battle();s.conditions['player']={'stun':{'until':2}}
        with self.assertRaises(ValueError):self.act(c,s,d,{'kind':'disengage'})
        self.assertTrue(s.action_available);self.assertFalse(s.disengaged)

    def test_healing_aura_affects_player_and_ally_but_not_enemy(self):
        c,s,d=self.setup_battle();s.target_positions['ally']=(1,2);s.target_healths['ally']=20;s.player_health=20
        spell=self.spell('Ближнее действие','Жизнь')
        action=next(a for a in s.view(c,d,[spell],2)['actions'] if a['kind']=='spell')
        self.assertEqual(action['aims']['1:1']['targetIds'],['player','ally'])
        self.act(c,s,d,{'kind':'spell','name':spell['name'],'targetId':'player','x':1,'y':1},[spell])
        self.assertEqual(s.player_health,30);self.assertEqual(s.target_healths['ally'],30)
        self.assertEqual(s.target_healths['enemy'],1000)
        self.act(c,s,d,{'kind':'end_turn'},[spell])
        self.assertEqual(s.target_healths['ally'],40)

    def test_new_session_has_no_previous_cooldowns_conditions_songs_or_areas(self):
        c,s,d=self.setup_battle();s.cooldowns['spell:old']=999;s.conditions['player']={'stun':{'until':9}}
        s.breath=5;s.areas.append({'id':'old'});s.opportunity_used.add('enemy')
        fresh=TrainingSession(1)
        self.assertFalse(fresh.cooldowns);self.assertFalse(fresh.conditions);self.assertFalse(fresh.areas)
        self.assertFalse(fresh.active_songs);self.assertFalse(fresh.opportunity_used);self.assertEqual(fresh.breath,0)

    def test_self_aoe_preview_keeps_enemy_ids_and_actual_radius(self):
        key='Abl_Comp_RngMagic_RepellingNova'
        c,s,d=self.setup_battle(key)
        s.targets['far']=copy.deepcopy(s.targets['enemy']);s.target_positions['far']=(11,11);s.target_healths['far']=1000
        action=next(a for a in s.view(c,d,[],2)['actions'] if a.get('key')==key)
        aim=action['aims']['1:1']
        self.assertTrue(aim['valid']);self.assertEqual(aim['targetIds'],['enemy'])
        cells={(p['x'],p['y']) for p in aim['cells']}
        self.assertIn(s.target_positions['enemy'],cells);self.assertNotIn(s.target_positions['far'],cells)
        with patch('training_combat.random.randint',side_effect=lambda lo,hi:hi):
            self.act(c,s,d,{'kind':'ability','name':key,'targetId':'player','x':1,'y':1})
        self.assertLess(s.target_healths['enemy'],1000);self.assertEqual(s.target_healths['far'],1000)
        self.assertEqual(s.target_healths['ally'],100);self.assertEqual(s.player_health,s.player_health_max)

    def test_unsupported_aria_preview_invalid_and_executor_preserves_all_resources(self):
        key='Abl_Comp_Sirin_AriaOfResolve'
        c,s,d=self.setup_battle(key);s.breath=5
        action=next(a for a in s.view(c,d,[],2)['actions'] if a.get('key')==key)
        self.assertFalse(action['supported']);self.assertTrue(action['disabledReason'])
        self.assertTrue(all(not aim['valid'] for aim in action['aims'].values()))
        before=copy.deepcopy(s.__dict__)
        with self.assertRaises(ValueError):self.act(c,s,d,{'kind':'ability','name':key,'targetId':'ally','x':3,'y':1})
        for field in ['breath','cooldowns','action_available','movement_remaining','target_healths','conditions','log']:
            self.assertEqual(getattr(s,field),before[field],field)


if __name__=='__main__':unittest.main()
