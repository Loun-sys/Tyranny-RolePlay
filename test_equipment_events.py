import copy
import unittest
from unittest.mock import patch

from consumables import virtual_equipment
from equipment_runtime import on_death
from merchant_rules import runtime_warnings
from registration_api import _derived
from test_armor_runtime import armor
from test_talent_reactions import session


class EquipmentEventTests(unittest.TestCase):
    def test_gamblers_boots_keep_base_speed_and_apply_single_wound_penalty(self):
        item=armor('UNIQUE_Leather_BOOTS_GamblersTreads')
        c,d,s=session(inventory=[item])
        self.assertEqual(d['movementMultiplier'],1.5)
        c['wounds']=1
        self.assertEqual(_derived(c,[item])['movementMultiplier'],.25)
        c['wounds']=5
        self.assertEqual(_derived(c,[item])['movementMultiplier'],.25)
        self.assertFalse(runtime_warnings(item))

    def test_cowards_boots_speed_appears_only_with_wound(self):
        item=armor('UNIQUE_Cloth_BOOTS_CowardsContingency')
        c,d,s=session(inventory=[item])
        self.assertEqual(d['movementMultiplier'],1)
        c['wounds']=1
        self.assertEqual(_derived(c,[item])['movementMultiplier'],1.5)
        item['equipped_slot']=''
        self.assertEqual(_derived(c,[item])['movementMultiplier'],1)

    def test_bloodthirsty_on_kill_applies_real_timed_buffs_without_action(self):
        item=armor('UNIQUE_Leather_GLOVE_CrimsonStuddedLeatherGloves')
        c,d,s=session(inventory=[item]);s.target_healths['enemy']=0
        s._after_enemy_kill('enemy',1)
        states=s.conditions['player'];effects=virtual_equipment(states,s.round_number)
        modified=_derived(c,effects)
        self.assertAlmostEqual(modified['cooldownMultiplier'],.75)
        self.assertAlmostEqual(modified['healthMax'],230)
        self.assertEqual(modified['defenses']['Воля'],17)
        self.assertTrue(s.action_available);self.assertFalse(s.cooldowns)
        self.assertFalse(virtual_equipment(states,s.round_number+3))

    def test_actual_killing_weapon_hit_triggers_gloves_but_not_hit_on_living_target(self):
        item=armor('UNIQUE_Leather_GLOVE_CrimsonStuddedLeatherGloves')
        _,_,s=session(inventory=[item])
        s._after_enemy_kill('enemy',10)
        self.assertFalse(s.conditions.get('player'))
        s.target_healths['enemy']=1
        with patch('training_combat.random.randint',side_effect=lambda lo,hi:hi):
            s._roll_attack(name='Убийство',accuracy=0,low=20,high=20,defense=0,armor=0,target_id='enemy')
        self.assertTrue(any(e.get('source',{}).get('AffectsStat')==2000 for e in s.conditions['player'].values()))

    def test_commanders_will_cleans_only_nearby_allies(self):
        item=armor('UNIQUE_Leather_BOOTS_PDXPreOrder')
        _,_,s=session(inventory=[item])
        from tactical_grid import TacticalGrid
        s.grid=TacticalGrid(30,30)
        for key,team,position in [('ally','ally',(3,1)),('far','ally',(29,29)),('other','enemy',(3,2))]:
            s.targets[key]={**copy.deepcopy(s.targets['enemy']),'team':team}
            s.target_positions[key]=position;s.target_healths[key]=100
        for key in ['player','ally','far','other']:
            s.conditions[key]={'stun':{'beneficial':False,'until':3},'blessing':{'beneficial':True,'until':3}}
        s.target_healths['enemy']=0;s._after_enemy_kill('enemy',1)
        for key in ['player','ally']:
            self.assertNotIn('stun',s.conditions[key]);self.assertIn('blessing',s.conditions[key])
        for key in ['far','other']:self.assertIn('stun',s.conditions[key])

    def test_martyr_heals_nearby_live_allies_not_owner_enemies_or_fallen(self):
        item=armor('UNIQUE_Iron_Armor_DyingWish')
        _,_,s=session(inventory=[item])
        for key,team,position,hp in [('ally','ally',(3,1),500),('far','ally',(11,11),500),('fallen','ally',(2,2),0)]:
            s.targets[key]={**copy.deepcopy(s.targets['enemy']),'team':team,'healthMax':1000}
            s.target_positions[key]=position;s.target_healths[key]=hp
        s.player_health=0
        on_death(s,'player',1)
        self.assertEqual(s.player_health,0)
        self.assertEqual(s.target_healths['ally'],850)
        self.assertEqual(s.target_healths['far'],500)
        self.assertEqual(s.target_healths['fallen'],0)
        self.assertEqual(s.target_healths['enemy'],1000)
        on_death(s,'player',1)
        self.assertEqual(s.target_healths['ally'],850)

    def test_martyr_npc_only_heals_its_own_team(self):
        item=armor('UNIQUE_Iron_Armor_DyingWish')
        _,_,s=session();s.targets['enemy']['inventory']=[item]
        s.targets['friend']={**copy.deepcopy(s.targets['enemy']),'inventory':[]}
        s.target_positions['friend']=(3,1);s.target_healths['friend']=500
        s.target_healths['enemy']=0
        hp=s.player_health;on_death(s,'enemy',1)
        self.assertEqual(s.target_healths['friend'],850)
        self.assertEqual(s.player_health,hp)


if __name__=='__main__':unittest.main()
