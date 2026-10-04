import copy
import unittest
from unittest.mock import patch

from combat_math import outcome_distribution, roll_quality
from training_combat import TrainingSession, DUMMY
from tactical_grid import TacticalGrid
from registration_api import _derived
from test_talent_runtime import actor


class TacticalCombatTests(unittest.TestCase):
    def battle(self):
        character=actor();character.update(health=200,health_max=200)
        derived=_derived(character,[])
        derived['attack'].update(accuracy=20,damageMin=10,damageMax=15,criticalChance=0,skill='Одноручное оружие',range=1)
        session=TrainingSession(1);session.grid=TacticalGrid(12,12)
        session.player_position=(1,1)
        session.targets={'enemy':{**copy.deepcopy(DUMMY),'healthMax':1000,'armor':0}}
        session.target_positions={'enemy':(2,1)};session.target_healths={'enemy':1000};session.selected_target_id='enemy'
        session.view(character,derived,[],2)
        return character,derived,session

    def act(self,c,d,s,**payload):return s.act(payload,c,d,[],2)

    def test_roll_boundaries_and_distribution(self):
        self.assertEqual([roll_quality(x) for x in [15,16,50,51,100,101]],[0,1,1,2,2,3])
        result=outcome_distribution(0,0)
        for name,expected in [('miss',.15),('graze',.35),('hit',.5),('critical',0)]:self.assertAlmostEqual(result[name],expected)
        self.assertAlmostEqual(sum(result.values()),1)

    def test_sequential_conversions_and_reflection(self):
        converted=outcome_distribution(0,0,critical=100,conversions={'critToHit':100,'hitToGraze':100,'grazeToMiss':100})
        self.assertAlmostEqual(converted['miss'],1)
        reflected=outcome_distribution(0,0,reflections={1:1,2:1,3:1})
        self.assertAlmostEqual(reflected['reflected'],.85)
        self.assertAlmostEqual(sum(reflected.values()),1)

    def test_d100_fractional_threshold_and_order_of_promotions(self):
        result=outcome_distribution(0,0,critical=10.9,graze_to_hit=1)
        self.assertAlmostEqual(result['critical'],.05)
        self.assertAlmostEqual(result['hit'],.8)

    def test_guard_multiplies_all_current_defenses_and_expires(self):
        c,d,s=self.battle();before=d['defenses'].copy()
        self.act(c,d,s,kind='tactic',name='Защита',targetId='player',x=1,y=1)
        self.assertFalse(s.action_available)
        view=s.view(c,d,[],2)
        self.assertEqual(view['derived']['defenses'],{k:round(v*1.2) for k,v in before.items()})
        self.act(c,d,s,kind='end_turn')
        self.assertEqual(s.view(c,d,[],2)['derived']['defenses'],before)
        self.assertNotIn('tactical:guard',s.conditions['player'])

    def test_guard_cannot_stack_or_apply_to_enemy(self):
        c,d,s=self.battle()
        with self.assertRaises(ValueError):self.act(c,d,s,kind='tactic',name='Защита',x=2,y=1)
        self.assertTrue(s.action_available)
        self.act(c,d,s,kind='tactic',name='Защита')
        with self.assertRaises(ValueError):self.act(c,d,s,kind='tactic',name='Защита')
        self.assertEqual(s.conditions['player']['tactical:guard']['value'],1.2)

    def test_guard_on_defending_npc_is_applied_after_other_modifiers(self):
        c,d,s=self.battle();s.targets['enemy']['defenses']['Парирование']=25
        s.conditions['enemy']={'guard':{'kind':'guard','value':1.2,'until':1},'bonus':{'kind':'Парирование','value':5,'until':1}}
        self.assertEqual(s._defense('Парирование','enemy'),36)
        s.targets['enemy']['talentRuntime']={2143:5}
        parameters=s._attack_parameters(accuracy=20,defense=25,armor=0,target_id='enemy',defense_name='Парирование')
        self.assertEqual(parameters['defense'],42) # (25 + 5 timed + 5 adjacent) * 1.2

    def test_dash_spends_action_not_movement_and_resets(self):
        c,d,s=self.battle();self.act(c,d,s,kind='move',x=1,y=3)
        self.act(c,d,s,kind='tactic',name='Спринт',x=1,y=3)
        self.assertEqual(s.movement_remaining,8);self.assertFalse(s.action_available)
        self.assertEqual(s.view(c,d,[],2)['turn']['movementMax'],10)
        self.assertFalse(s.disengaged)
        self.act(c,d,s,kind='end_turn');self.assertEqual(s.movement_remaining,5)
        self.assertFalse(s.dash_used)

    def test_dash_cannot_bypass_root_or_repeat(self):
        c,d,s=self.battle();s.conditions['player']={'root':{'until':1,'name':'Корни'}}
        with self.assertRaises(ValueError):self.act(c,d,s,kind='tactic',name='Спринт')
        self.assertEqual(s.movement_remaining,5);self.assertTrue(s.action_available)
        s.conditions['player']={};self.act(c,d,s,kind='tactic',name='Спринт');s.action_available=True
        with self.assertRaises(ValueError):self.act(c,d,s,kind='tactic',name='Спринт')

    def test_preview_is_read_only_and_consumes_no_random_values(self):
        c,d,s=self.battle();before=copy.deepcopy(s.__dict__)
        with patch('training_combat.random.randint',side_effect=AssertionError('preview rolled')),patch('training_combat.random.random',side_effect=AssertionError('preview rolled')):
            view=s.view(c,d,[],2)
        for field in ['conditions','target_healths','log','events','cooldowns','action_available','movement_remaining']:
            self.assertEqual(getattr(s,field),before[field],field)
        preview=next(a for a in view['actions'] if a['kind']=='attack')['aims']['2:1']['previews'][0]
        self.assertEqual(preview['defenseName'],'Парирование');self.assertEqual(preview['defense'],35)
        self.assertEqual(preview['hitChance'],70);self.assertEqual(preview['damageMin'],5);self.assertEqual(preview['damageMax'],15)

    def test_preview_outcomes_match_every_possible_actual_roll(self):
        c,d,s=self.battle();preview=s._attack_preview({'kind':'attack'},'enemy',d)
        counts={'miss':0,'graze':0,'hit':0,'critical':0}
        names={'Промах':'miss','Скользящий удар':'graze','Попадание':'hit','Критическое попадание':'critical'}
        for roll in range(1,101):
            clone=copy.deepcopy(s)
            with patch('training_combat.random.randint',side_effect=lambda lo,hi:roll if hi==100 else lo):
                hit=clone._roll_attack(name='Испытание',accuracy=20,low=10,high=15,defense=35,armor=0,target_id='enemy',defense_name='Парирование')
            counts[names[hit['result']]]+=1
        for label,count in counts.items():self.assertEqual(preview['outcomes'][label],count)

    def test_preview_and_execution_share_conversion_and_armor(self):
        c,d,s=self.battle();s.targets['enemy']['incomingConversions']={'hitToGraze':100,'grazeToMiss':100}
        preview=s._attack_preview({'kind':'attack'},'enemy',d)
        self.assertEqual(preview['hitChance'],0);self.assertEqual(preview['damageMax'],0)
        with patch('training_combat.random.randint',return_value=100):
            result=self.act(c,d,s,kind='attack',targetId='enemy')
        self.assertEqual(result['damage'],0);self.assertEqual(s.events[0]['result'],'Промах')

    def test_movement_route_matches_executed_path_and_opportunity(self):
        c,d,s=self.battle();s.player_position=(0,1)
        route=s.view(c,d,[],2)['grid']['movementPreviews']['4:1']
        self.assertEqual(route['opportunities'],[{'id':'enemy','name':DUMMY['name']}])
        with patch('training_combat.random.randint',side_effect=lambda lo,hi:hi):self.act(c,d,s,kind='move',x=4,y=1)
        self.assertEqual(route['path'],[{'x':x,'y':y} for x,y in s.movement_path])
        self.assertEqual(route['cost'],len(s.movement_path)-1)
        self.assertTrue(s.events[0]['opportunity'])

    def test_disengaged_used_controlled_and_ranged_targets_do_not_warn(self):
        c,d,s=self.battle();path=[(1,1),(0,1)]
        self.assertEqual(s._opportunity_controllers(path),['enemy'])
        s.disengaged=True;self.assertEqual(s._opportunity_controllers(path),[])
        s.disengaged=False;s.opportunity_used.add('enemy');self.assertEqual(s._opportunity_controllers(path),[])
        s.opportunity_used.clear();s.conditions['enemy']={'stun':{'until':1}};self.assertEqual(s._opportunity_controllers(path),[])
        s.conditions['enemy']={};s.targets['enemy']['attack']={'range':12};self.assertEqual(s._opportunity_controllers(path),[])

    def test_prepared_attack_removed_and_rejected_atomically(self):
        c,d,s=self.battle()
        self.assertNotIn('Подготовить атаку',[a['name'] for a in s.view(c,d,[],2)['actions']])
        with self.assertRaises(ValueError):self.act(c,d,s,kind='tactic',name='Подготовить атаку')
        self.assertTrue(s.action_available)

    def test_rooted_actor_has_no_reachable_preview(self):
        c,d,s=self.battle();s.conditions['player']={'root':{'until':1,'name':'Корни'}}
        grid=s.view(c,d,[],2)['grid'];self.assertEqual(grid['reachable'],[]);self.assertEqual(grid['movementPreviews'],{})

    def test_actual_master_npc_attack_does_not_trigger_removed_reaction(self):
        from npc_store import ability_library
        ability=next(a for a in ability_library() if a['key']=='ABL_DIS_BloodBound_DisablingKick')
        c,d,s=self.battle()
        s.targets['enemy'].update(kind='npc',abilities=[ability],attributes=c['attributes'],skills={'Атлетика':80},
            attack={'accuracy':20,'damageMin':4,'damageMax':8,'range':1})
        with patch('training_combat.random.randint',side_effect=lambda lo,hi:hi):
            result=s.master_npc_ability('enemy',ability['key'],'player',c,d)
        self.assertNotIn('reaction',result);self.assertEqual(s.target_healths['enemy'],1000)
        self.assertTrue(s.action_available)
        self.assertTrue(any(e['targetId']=='player' and e['sourceId']=='enemy' for e in s.events))

    def test_master_guard_and_failed_detection_update_is_atomic(self):
        from npc_store import ability_library
        ability=next(a for a in ability_library() if a['key']=='ABL_DIS_BloodBound_DisablingKick')
        c,d,s=self.battle();s.targets['enemy'].update(kind='npc',abilities=[ability],attributes=c['attributes'],
            skills={'Атлетика':80},attack={'accuracy':20,'damageMin':4,'damageMax':8,'range':1})
        self.act(c,d,s,kind='tactic',name='Защита')
        before=copy.deepcopy(s.__dict__)
        with patch('training_combat.random.randint',side_effect=lambda lo,hi:hi),patch.object(TrainingSession,'_advance_stealth',side_effect=RuntimeError('detection failed')):
            with self.assertRaises(RuntimeError):s.master_npc_ability('enemy',ability['key'],'player',c,d)
        for field in ['player_health','target_healths','conditions','log','events','action_available']:
            self.assertEqual(getattr(s,field),before[field])


if __name__=='__main__':unittest.main()
