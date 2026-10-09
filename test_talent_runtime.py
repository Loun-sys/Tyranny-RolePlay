import unittest
from unittest.mock import patch
from ability_rules import resolve,owned_actions,talent_mechanics,weapon_requirement,passive_equipment
from registration_api import _derived
from test_consumables import character
from training_combat import TrainingSession
from talent_runtime import effects,attack_context


def actor(*keys):
    c=character();c['talents']=[{'prefab':key,'name':resolve(key)['name']} for key in keys]
    return c


class TalentRuntimeTests(unittest.TestCase):
    def test_focused_strike_modifies_thrust_and_not_other_actions(self):
        d=_derived(character(),[])
        actions=owned_actions([{'key':'Abl_PC_Thrust'},{'key':'Abl_PC_Power_FocusedStrike'},{'key':'Abl_PC_Power_Sunder'}],d)
        thrust=next(a for a in actions if a['key']=='Abl_PC_Thrust')
        self.assertEqual(thrust['accuracy'],d['attack']['accuracy']+15)
        self.assertEqual(thrust['penetration'],resolve('Abl_PC_Thrust')['penetration']+6)
        self.assertEqual(next(a for a in actions if a['key']=='Abl_PC_Power_Sunder')['penetration'],resolve('Abl_PC_Power_Sunder')['penetration'])

    def test_upgrade_grants_base_once_even_when_already_owned(self):
        actions=owned_actions([{'key':'Abl_PC_Thrust'},{'key':'Abl_PC_Power_FocusedStrike'}],_derived(character(),[]))
        self.assertEqual([a['key'] for a in actions],['Abl_PC_Thrust'])

    def test_concentrated_force_stuns_only_after_hit(self):
        c=actor('Abl_PC_Power_ConcentratedForce');s=TrainingSession(1);s.player_position=(9,4)
        with patch('training_combat.random.randint',side_effect=lambda lo,hi:hi):s.act({'kind':'ability','name':'Abl_PC_Power_Sunder'},c,_derived(c,[]),[],2)
        self.assertIn('stun',s.conditions['dummy'])
        self.assertEqual(s.conditions['dummy']['stun']['until'],1)

    def test_feint_blinds_and_expires_next_round(self):
        c=actor('Abl_PC_Agility_Feint');s=TrainingSession(1);s.player_position=(9,4)
        with patch('training_combat.random.randint',side_effect=lambda lo,hi:hi):s.act({'kind':'ability','name':'Abl_PC_Thrust'},c,_derived(c,[]),[],2)
        self.assertIn('blind',s.conditions['dummy'])
        s._end_turn();self.assertIn('blind',s.conditions['dummy'])
        s._end_turn();self.assertNotIn('blind',s.conditions['dummy'])

    def test_missed_upgrade_does_not_apply_blind(self):
        c=actor('Abl_PC_Agility_Feint');s=TrainingSession(1);s.player_position=(9,4)
        d=_derived(c,[]);d['attack']['accuracy']=-100
        with patch('training_combat.random.randint',return_value=1):s.act({'kind':'ability','name':'Abl_PC_Thrust'},c,d,[],2)
        self.assertNotIn('blind',s.conditions.get('dummy',{}))

    def test_natural_weaponry_uses_highest_rank_not_sum(self):
        c=actor('PSV_Comp_Beastwoman_NaturalWeaponry_1of5','PSV_Comp_Beastwoman_NaturalWeaponry_4of5')
        d=_derived(c,[]);base=_derived(character(),[])
        self.assertEqual(d['attack']['damageMin'],base['attack']['damageMin']+13)
        self.assertEqual(d['attack']['damageMax'],base['attack']['damageMax']+13)

    def test_unarmed_bonus_does_not_apply_to_sword(self):
        sword={'name':'Меч','category':'Одноручное оружие','damage_min':5,'damage_max':7,'equipped_slot':'Оружие I — правая рука'}
        c=actor('PSV_Comp_Beastwoman_NaturalWeaponry_4of5','PSV_Comp_Beastwoman_RendingClaws_2of2')
        self.assertEqual(_derived(c,[sword])['attack'],_derived(character(),[sword])['attack'])
        self.assertEqual(_derived(c,[])['attack']['penetration'],6)

    def test_throw_range_and_penetration(self):
        c=actor('PSV_Comp_Lantry_PenetratingThrow_01','PSV_Comp_Lantry_PenetratingThrow_03')
        quill={'name':'Перо','category':'Метательное оружие','damage_min':5,'damage_max':7,'equipped_slot':'Оружие I — правая рука'}
        d=_derived(c,[quill]);self.assertEqual(d['attack']['range'],12);self.assertEqual(d['attack']['penetration'],8)

    def test_two_one_handed_weapons_do_not_count_as_shield(self):
        weapons=[{'category':'Одноручное оружие','equipped_slot':f'Оружие I — {hand} рука'} for hand in ['правая','левая']]
        self.assertTrue(weapon_requirement({'weaponMask':4},weapons))
        self.assertFalse(weapon_requirement({'weaponMask':2},weapons))
        self.assertFalse(weapon_requirement({'weaponMask':8},weapons))

    def test_critical_damage_changes_actual_damage(self):
        def hit(c):
            s=TrainingSession(1);s.player_position=(9,4)
            s.targets['dummy']['armor']=0
            s.targets['dummy']['defenses']['Парирование']=0
            d=_derived(c,[]);d['attack'].update(damageMin=10,damageMax=10)
            with patch('training_combat.random.randint',side_effect=lambda lo,hi:hi):s.act({'kind':'attack'},c,d,[],2)
            return s.damage_total
        self.assertGreater(hit(actor('PSV_PC_Power_MassiveBlow_2of2')),hit(character()))

    def test_killing_spree_runs_three_attacks_and_spends_one_action(self):
        c=actor('PSV_Comp_Verse_KillingSpree_01','PSV_Comp_Verse_KillingSpree_02');s=TrainingSession(1);s.player_position=(9,4)
        s.target_healths['dummy']=1
        with patch('training_combat.random.randint',side_effect=lambda lo,hi:hi):s.act({'kind':'attack'},c,_derived(c,[]),[],2)
        self.assertEqual(s.attacks,1)
        self.assertTrue(any(state.get('source',{}).get('AffectsStat')==2157 for state in s.conditions['player'].values()))
        s._end_turn();target=next(k for k in s._alive_targets());s.target_positions[target]=(10,4)
        with patch('training_combat.random.randint',side_effect=lambda lo,hi:hi):s.act({'kind':'attack','targetId':target},c,_derived(c,[]),[],2)
        self.assertEqual(s.attacks,4);self.assertFalse(s.action_available)

    def test_killing_spree_does_not_grant_three_hits_before_kill(self):
        c=actor('PSV_Comp_Verse_KillingSpree_02');s=TrainingSession(1);s.player_position=(9,4)
        with patch('training_combat.random.randint',side_effect=lambda lo,hi:hi):s.act({'kind':'attack'},c,_derived(c,[]),[],2)
        self.assertEqual(s.attacks,1)

    def test_context_bonus_requires_actual_condition(self):
        r=effects(actor('PSV_Comp_Beastwoman_PackAggression')['talents'])
        self.assertEqual(attack_context(r,{},1,1,0)['multiplier'],1)
        self.assertAlmostEqual(attack_context(r,{'blind':{'beneficial':False}},1,1,0)['multiplier'],1.4,places=5)

    def test_blood_rage_scales_with_missing_health_not_permanently(self):
        c=actor('PSV_Comp_Beastwoman_BloodRage');s=TrainingSession(1);d=_derived(c,[]);s.view(c,d,[],2)
        s.player_health=s.player_health_max
        self.assertEqual(s._combat_derived(d)['cooldownMultiplier'],1)
        s.player_health=s.player_health_max//2
        self.assertAlmostEqual(s._combat_derived(d)['cooldownMultiplier'],.75)

    def test_heavy_guard_requires_exclusively_heavy_armor(self):
        c=actor('PSV_PC_Defense_HeavyGuard_1of2','PSV_PC_Defense_HeavyGuard_2of2')
        def armor(category):return {'name':'Броня','equipped_slot':'Торс','armor':0,'properties':{'gameData':{'armor':{'ArmorCategory':category}}}}
        self.assertEqual(_derived(c,[])['armor'],0)
        self.assertEqual(_derived(c,[armor(1)])['armor'],2)
        self.assertAlmostEqual(_derived(c,[armor(1)])['cooldownMultiplier'],.9)
        mixed=[armor(1),{**armor(0),'equipped_slot':'Ноги'}]
        self.assertEqual(_derived(c,mixed)['armor'],0)

    def test_light_and_no_armor_conditions_are_exclusive(self):
        c=actor('PSV_Comp_RngMagic_RunicBarrier_3of3')
        light={'name':'Лёгкая','equipped_slot':'Торс','armor':0,'properties':{'gameData':{'armor':{'ArmorCategory':0}}}}
        heavy={'name':'Тяжёлая','equipped_slot':'Торс','armor':0,'properties':{'gameData':{'armor':{'ArmorCategory':1}}}}
        self.assertEqual(_derived(c,[])['armor'],6)
        self.assertEqual(_derived(c,[light])['armor'],6)
        self.assertEqual(_derived(c,[heavy])['armor'],0)

    def test_unsupported_upgrades_still_report_real_limitations(self):
        self.assertTrue(talent_mechanics(resolve('PSV_PC_Magic_CounterSpell'))['limitation'])

    def test_frozen_stance_triggers_on_hit_only_while_selected(self):
        c=actor('Abl_Comp_Lantry_StanceFrozen');s=TrainingSession(1);s.player_position=(9,4)
        d=_derived(c,[])
        with patch('training_combat.random.randint',side_effect=lambda lo,hi:hi):s.act({'kind':'attack'},c,d,[],2)
        self.assertNotIn('freeze',s.conditions.get('dummy',{}))
        s._end_turn();s.act({'kind':'stance','name':resolve('Abl_Comp_Lantry_StanceFrozen')['name']},c,d,[],2)
        with patch('training_combat.random.randint',side_effect=lambda lo,hi:hi):s.act({'kind':'attack'},c,d,[],2)
        self.assertIn('freeze',s.conditions['dummy'])

    def test_headshot_requires_critical_and_ranged_weapon(self):
        c=actor('PSV_PC_Ranged_Headshot_1of2');s=TrainingSession(1);s.player_position=(9,4)
        d=_derived(c,[]);d['attack'].update(accuracy=200,range=12)
        s.consumable_inventory=[{'category':'Луки','equipped_slot':'Оружие I — правая рука'}]
        with patch('training_combat.random.randint',side_effect=lambda lo,hi:hi):s.act({'kind':'attack'},c,d,[],2)
        self.assertIn('stun',s.conditions['dummy'])

    def test_stealth_proc_has_explicit_stealth_condition(self):
        from ability_rules import proc_profiles
        procs=proc_profiles(resolve('PSV_PC_Defense_PinningStrike'))
        self.assertEqual(len(procs),1)
        self.assertTrue(procs[0]['stealthOnly'])

    def test_energy_shield_can_target_self_but_not_hostile_dummy(self):
        c=actor('Abl_PC_Magic_EnergyShield');s=TrainingSession(1)
        s.act({'kind':'ability','name':'Abl_PC_Magic_EnergyShield','targetId':'player'},c,_derived(c,[]),[],2)
        self.assertTrue(any(state.get('source',{}).get('AffectsStat')==14 for state in s.conditions['player'].values()))
        s=TrainingSession(1);s.player_position=(9,4)
        with self.assertRaises(ValueError):s.act({'kind':'ability','name':'Abl_PC_Magic_EnergyShield','targetId':'dummy'},c,_derived(c,[]),[],2)
        self.assertTrue(s.action_available)

    def test_swap_positions_swaps_ally_tokens_and_spends_one_action(self):
        c=actor('Abl_PC_Leadership_SwapPositions');s=TrainingSession(1)
        s.view(c,_derived(c,[]),[],2);s.targets['dummy']['team']='ally';s.target_positions['dummy']=(3,4)
        before=(s.player_position,s.target_positions['dummy'])
        s.act({'kind':'ability','name':'Abl_PC_Leadership_SwapPositions','targetId':'dummy'},c,_derived(c,[]),[],2)
        self.assertEqual((s.player_position,s.target_positions['dummy']),tuple(reversed(before)))
        self.assertFalse(s.action_available)

    def test_slot_talents_use_source_and_highest_rank(self):
        from database import Database
        names={resolve(k)['name'] for k in ['PSV_Comp_Lantry_LearnedInstructor_01','PSV_PC_Leadership_ArbiterOfKnowledge']}
        self.assertEqual(Database._equipment_limits_from_talents(names)['spellSlots'],7)

    def test_root_prevents_movement_without_spending_movement(self):
        c=character();s=TrainingSession(1);s.view(c,_derived(c,[]),[],2)
        s.conditions['player']={'root':{'kind':'root','until':3}}
        before=s.movement_remaining
        with self.assertRaises(ValueError):s.act({'kind':'move','x':3,'y':4},c,_derived(c,[]),[],2)
        self.assertEqual(s.movement_remaining,before)

    def test_silence_prevents_casting_before_any_action_or_cooldown(self):
        c=character();s=TrainingSession(1);s.view(c,_derived(c,[]),[],2)
        s.conditions['player']={'silence':{'kind':'silence','until':3}}
        with self.assertRaisesRegex(ValueError,'Немота'):s.act({'kind':'spell','name':'test'},c,_derived(c,[]),[],2)
        self.assertTrue(s.action_available);self.assertFalse(s.cooldowns)

    def test_nova_damages_and_roots_enemies_not_caster(self):
        c=actor('Abl_Comp_RngMagic_RepellingNova');s=TrainingSession(1);s.player_position=(9,4)
        hp=s.target_healths['dummy']
        with patch('training_combat.random.randint',side_effect=lambda lo,hi:hi):s.act({'kind':'ability','name':'Abl_Comp_RngMagic_RepellingNova'},c,_derived(c,[]),[],2)
        self.assertLess(s.target_healths['dummy'],hp)
        self.assertIn('root',s.conditions['dummy']);self.assertNotIn('root',s.conditions.get('player',{}))

    def test_striking_iron_bonus_only_in_melee_zone(self):
        c=actor('Abl_Comp_Defender_StrikingIron')
        sword={'name':'Меч','category':'Одноручное оружие','damage_min':10,'damage_max':10,'equipped_slot':'Оружие I — правая рука'}
        d=_derived(c,[sword]);s=TrainingSession(1);s.player_position=(9,4);s.consumable_inventory=[sword]
        s.targets['dummy']['armor']=0
        with patch('training_combat.random.randint',side_effect=lambda lo,hi:hi):s.act({'kind':'ability','name':'Abl_Comp_Defender_StrikingIron'},c,d,[],2)
        self.assertGreaterEqual(s.damage_total,20)

    def test_weapon_specialization_does_not_apply_same_multiplier_twice(self):
        c=actor('PSV_Comp_Defender_ArtOfTheBlade_03')
        sword={'name':'Меч','category':'Одноручное оружие','damage_min':10,'damage_max':10,'equipped_slot':'Оружие I — правая рука'}
        self.assertEqual(_derived(c,[sword])['attack']['damageMax'],13)

    def test_original_ability_class_preserved_for_triggered_talents(self):
        self.assertEqual(resolve('PSV_Comp_Verse_KillingSpree_02')['abilityClass'],'TriggeredOnKillAbility')

    def test_incoming_graze_to_miss_conversion_removes_damage(self):
        c=character();s=TrainingSession(1);s.player_position=(9,4);s.view(c,_derived(c,[]),[],2)
        s.targets['dummy']['incomingConversions']={'grazeToMiss':100}
        with patch('training_combat.random.randint',return_value=50):
            result=s._roll_attack(name='Тест',accuracy=0,low=10,high=10,defense=20,armor=0)
        self.assertEqual(result['result'],'Промах');self.assertEqual(result['damage'],0)

    def test_crit_modifier_probability_units_and_actual_conversion(self):
        c=actor('PSV_Comp_Verse_AndYouShallTriumph')
        self.assertEqual(_derived(c,[])['incomingConversions']['grazeToMiss'],15)
        d=_derived(character(),[]);d['attack'].update(criticalChance=100,damageMin=10,damageMax=10)
        s=TrainingSession(1);s.player_position=(9,4);s.targets['dummy']['armor']=0
        with patch('training_combat.random.randint',side_effect=lambda lo,hi:80 if hi==100 else lo):
            result=s.act({'kind':'attack'},character(),d,[],2)
        self.assertEqual(result['result'],'Критическое попадание');self.assertEqual(result['damage'],15)

    def test_second_breath_with_moment_of_peace_revives_fallen_ally(self):
        c=actor('Abl_Comp_Lantry_MomentOfPeace');s=TrainingSession(1);s.view(c,_derived(c,[]),[],2)
        s.targets['dummy']['team']='ally';s.target_healths['dummy']=0;s.target_positions['dummy']=(3,4)
        s.act({'kind':'ability','name':'Abl_Comp_Lantry_SecondBreath','targetId':'dummy'},c,_derived(c,[]),[],2)
        self.assertGreater(s.target_healths['dummy'],0)
        self.assertTrue(any(state.get('source',{}).get('AffectsStat')==188 for state in s.conditions['dummy'].values()))


if __name__=='__main__':unittest.main()
