import copy
import unittest
from unittest.mock import patch
from ability_rules import resolve,profile,owned_actions,talent_mechanics,stance_equipment
from talent_batch_three import BATCH_KEYS,party_equipment,contextual,shield,advance_graphs,effective_consumable
from test_talent_batch_one import prepared,add
from test_talent_reactions import SWORD
from consumables import virtual_equipment
from registration_api import _derived

class ManifestTests(unittest.TestCase):
    def test_thirty_distinct_positions(self):self.assertEqual(len(set(BATCH_KEYS)),30)
def check(key):
    def test(self):
        row=resolve(key);self.assertEqual(row['source']['archive'],'abilities')
        self.assertFalse(talent_mechanics(row)['limitation']);self.assertTrue(talent_mechanics(row)['effects'])
    return test
for key in BATCH_KEYS:setattr(ManifestTests,'test_source_'+key,check(key))

class BehaviorTests(unittest.TestCase):
    def test_all_resonance_ranks_absorb_without_permanent_flat_armor(self):
        for rank,value in [(1,20),(2,50),(3,80)]:
            c,d,s=prepared('PSV_Comp_Sirin_ResonantField_'+str(rank)+'of3')
            shield(s,'player');self.assertEqual(s.conditions['player']['resonance-shield']['shieldRemaining'],value)
            s.targets['enemy']['abilities']=c['talents'];s.targets['enemy']['armor']=0
            with patch('training_combat.random.randint',side_effect=lambda lo,hi:80 if hi==100 else hi):
                h=s._roll_attack(name='Удар',accuracy=0,defense=0,armor=0,low=10,high=10,target_id='enemy')
            self.assertEqual(h['damage'],0);self.assertNotIn('resonance-shield',s.conditions['enemy'])
            s.round_number=2;shield(s,'enemy');self.assertNotIn('resonance-shield',s.conditions['enemy'])
            s.round_number=3;shield(s,'enemy');self.assertEqual(s.conditions['enemy']['resonance-shield']['shieldRemaining'],value)

    def test_moonlit_skill_highest_rank_and_damage_only_night_gravelight(self):
        for rank,bonus in [(1,10),(2,20),(3,30)]:
            c,d,s=prepared(*['PSV_Comp_RngMagic_MoonlitWay_'+str(i)+'of3' for i in range(1,rank+1)])
            c['skills']['Управление могильным светом']={'value':0};d=_derived(c,[SWORD]);s.runtime_derived=d;s.talent_runtime=d['talentRuntime']
            baseline=_derived({**c,'talents':[]},[SWORD])
            self.assertEqual(d['effectiveSkills']['Управление могильным светом']-baseline['effectiveSkills']['Управление могильным светом'],bonus)
            s.custom_map={'timeOfDay':'night'}
            for grave,expected in [(True,40*(1+rank/10)),(False,40)]:
                with patch('training_combat.random.randint',side_effect=lambda lo,hi:80 if hi==100 else hi):h=s._roll_attack(name='Свет',accuracy=0,low=40,high=40,armor=0,defense=0,weapon_attack=False,gravelight=grave,target_id='enemy')
                self.assertEqual(h['damage'],round(expected))
            s.custom_map={'timeOfDay':'day'}
            with patch('training_combat.random.randint',side_effect=lambda lo,hi:80 if hi==100 else hi):h=s._roll_attack(name='Свет',accuracy=0,low=40,high=40,armor=0,defense=0,weapon_attack=False,gravelight=True,target_id='enemy')
            self.assertEqual(h['damage'],40)

    def test_relentless_requires_real_wound(self):
        c,d,s=prepared('PSV_Comp_Beastwoman_Relentless_1of2')
        s.player_health=1;self.assertEqual(contextual(s,copy.deepcopy(d))['attack']['criticalChance'],d['attack']['criticalChance'])
        c['wounds']=1;new=contextual(s,copy.deepcopy(d))
        self.assertEqual(new['attack']['criticalChance'],d['attack']['criticalChance']+10)
        self.assertAlmostEqual(new['cooldownMultiplier'],d['cooldownMultiplier']*.85)

    def test_mobile_recovery_increases_movement_without_action_cost(self):
        c,d,s=prepared('PSV_Comp_Verse_MobileRecovery');s._combat_derived(d)
        self.assertEqual(s._movement_limit(),6);self.assertTrue(s.action_available)

    def test_swift_quill_changes_exact_three_cooldowns_and_recovery(self):
        c,d,s=prepared('TLN_Comp_Lantry_SwiftQuill')
        actions=owned_actions(c['talents'],d)
        self.assertEqual(len(actions),3)
        for action in actions:
            base=resolve(action['key']);self.assertEqual(action['cooldownSeconds'],base['cooldownSeconds']*.75)
            self.assertEqual(action['recoveryAdjustmentSeconds'],-2)

    def test_ricochet_and_blades_use_back_cone_and_never_allies(self):
        for key,category in [('PSV_PC_Ranged_Ricochet','Луки'),('PSV_Comp_Lantry_BouncingBlades','Метательное оружие')]:
            _,d,s=prepared(key);s.consumable_inventory=[{**SWORD,'category':category}];d['attack'].update(skill='Луки' if category=='Луки' else 'Дротики',range=8)
            s.player_position=(1,1);s.target_positions['enemy']=(3,1);add(s,'behind',(5,1));add(s,'side',(3,4));add(s,'ally',(4,1),'ally')
            with patch('training_combat.random.randint',side_effect=lambda lo,hi:40 if hi==100 else hi):s._roll_attack(name='Выстрел',accuracy=0,low=20,high=20,armor=0,defense=0,target_id='enemy',attack_mode='ranged')
            self.assertLess(s.target_healths['behind'],1000);self.assertEqual(s.target_healths['side'],1000);self.assertEqual(s.target_healths['ally'],1000)
            self.assertEqual(len([e for e in s.events if e['targetId']=='behind']),1)

    def test_accelerate_proc_only_thrown_crit_and_self(self):
        c,d,s=prepared('PSV_Comp_Lantry_Accelerate');s.consumable_inventory=[{**SWORD,'category':'Метательное оружие'}]
        d['attack'].update(skill='Дротики',range=8)
        s._weapon_talent_procs('enemy','Попадание');self.assertFalse(s.conditions)
        s._weapon_talent_procs('enemy','Критическое попадание')
        states=[e['source'] for e in s.conditions['player'].values() if e.get('source')]
        self.assertTrue(any(e['AffectsStat']==2000 and round(e['Value'],2)==.85 for e in states))
        self.assertFalse(s.conditions.get('enemy'))

    def test_born_blood_fire_filters_affliction_not_direct_damage(self):
        c,d,s=prepared('PSV_Comp_Verse_BornOfBloodAndFire');s.targets['enemy']['abilities']=c['talents']
        effect={'side':'target','AffectsStat':25,'Value':6,'IntervalRate':1,'Duration':30,'affliction':'Aff_Bleeding','name':'Кровотечение'}
        s._apply_ability_effects({'key':'test','effects':[effect]},'enemy','target');self.assertFalse(s.conditions['enemy'])
        effect['affliction']='Aff_Poisoned';s._apply_ability_effects({'key':'test','effects':[effect]},'enemy','target');self.assertTrue(s.conditions['enemy'])

    def test_party_bonuses_use_senior_rank(self):
        c,d,s=prepared('PSV_PC_Leadership_Bandolier_2of2','PSV_PC_Leadership_AbundantArms_1of2','PSV_PC_Leadership_AbundantArms_2of2')
        self.assertEqual(d['consumableEffectiveness'],1.5);self.assertEqual(d['weaponSwitchRecoveryBonus'],-.5)
        ally=_derived({**c,'talents':[]},[SWORD,*party_equipment(c['talents'])])
        self.assertEqual(ally['consumableEffectiveness'],1.5);self.assertEqual(ally['weaponSwitchRecoveryBonus'],-.5)

    def test_effective_consumable_uses_copy_and_scales_heal(self):
        item={'properties':{'gameData':{'useComponents':[{'StatusEffects':[{'AffectsStat':116,'Value':.2}]}]}}}
        result=effective_consumable(item,1.5)
        self.assertAlmostEqual(result['properties']['gameData']['useComponents'][0]['StatusEffects'][0]['Value'],.3)
        self.assertEqual(item['properties']['gameData']['useComponents'][0]['StatusEffects'][0]['Value'],.2)

    def test_bandolier_scales_native_potion_duration_not_periodic_strength(self):
        item={'properties':{'gameData':{'sourceItem':{'Type':0},'useComponents':[{'StatusEffects':[
            {'AffectsStat':151,'Value':1,'Duration':60},
            {'AffectsStat':116,'Value':.1,'Duration':20,'IntervalRate':1}]}]}}}
        effects=effective_consumable(item,1.5)['properties']['gameData']['useComponents'][0]['StatusEffects']
        self.assertEqual(effects[0]['Value'],1);self.assertEqual(effects[0]['Duration'],90)
        self.assertEqual(effects[1]['Value'],.1);self.assertEqual(effects[1]['Duration'],30)

    def test_blood_victory_after_received_crit_has_different_stance_areas(self):
        from talent_batch_three import blood_retaliation
        for stance,stat in [('Abl_PC_Defense_StanceShieldbanger',188),('Abl_PC_Defense_StanceGuarded',14)]:
            c,d,s=prepared(stance,'PSV_PC_Defense_BloodBringsVictory');add(s,'ally',(1,2),'ally')
            s.active_stance=resolve(stance)['name']
            with patch('training_combat.random.randint',return_value=100):blood_retaliation(s,'player','Критическое попадание')
            victim='enemy' if stat==188 else 'ally'
            self.assertTrue(any(e.get('source',{}).get('AffectsStat')==stat for e in s.conditions.get(victim,{}).values()))
            s.conditions.clear();blood_retaliation(s,'player','Попадание');self.assertFalse(s.conditions)

    def test_empowered_area_multiplier_applies_abilities_not_single_targets(self):
        c,d,s=prepared('PSV_Comp_RngMagic_EmpoweredElements')
        row=resolve('Abl_PC_Leadership_ToArms')
        base=profile(row);new=profile(row,d)
        self.assertAlmostEqual(new['area'],base['area']*1.2,places=4)
        self.assertEqual(profile(resolve('Abl_Comp_Lantry_QuillStrike'),d)['targeting'],'unit')

    def test_counterspell_upgrade_reflects_crafted_spell_not_staff(self):
        c,d,s=prepared('PSV_PC_Magic_CounterSpell')
        rule=owned_actions(c['talents'],d)[0];s._apply_ability_effects(rule,'enemy','target')
        with patch('training_combat.random.randint',side_effect=lambda lo,hi:80 if hi==100 else hi),patch('training_combat.random.random',return_value=0):
            h=s._roll_attack(name='Магия',accuracy=0,low=10,high=10,defense=0,armor=0,target_id='enemy',crafted_spell=True,weapon_attack=False,attack_mode='spell')
            self.assertEqual(h['result'],'Отражено')
            h=s._roll_attack(name='Посох',accuracy=0,low=10,high=10,defense=0,armor=0,target_id='enemy',attack_mode='ranged')
            self.assertNotEqual(h['result'],'Отражено')

    def test_counterspell_redirects_before_target_shield_and_uses_caster_armor(self):
        c,d,s=prepared('PSV_PC_Magic_CounterSpell')
        rule=owned_actions(c['talents'],d)[0];s._apply_ability_effects(rule,'enemy','target')
        # Energy Shield is elemental armor in the source; a separate absorb
        # effect must survive reflection as well, rather than inventing one.
        s.conditions['enemy']['separate-shield']={'shieldRemaining':50,'until':6,'beneficial':True}
        shields={k:st['shieldRemaining'] for k,st in s.conditions['enemy'].items() if 'shieldRemaining' in st}
        self.assertTrue(shields)
        s.runtime_derived={**d,'armor':3,'armorByType':{}}
        before=s.player_health
        with patch('training_combat.random.randint',side_effect=lambda lo,hi:80 if hi==100 else hi),patch('training_combat.random.random',return_value=0):
            h=s._roll_attack(name='Магия',accuracy=0,low=10,high=10,defense=0,armor=100,target_id='enemy',crafted_spell=True,weapon_attack=False,attack_mode='spell')
        self.assertEqual(h['result'],'Отражено');self.assertEqual(s.player_health,before-7)
        self.assertEqual({k:st['shieldRemaining'] for k,st in s.conditions['enemy'].items() if 'shieldRemaining' in st},shields)

    def test_refuse_pain_pulses_in_area_not_global_immunity(self):
        _,d,s=prepared('Abl_PC_Leadership_RefusePain');add(s,'ally',(1,2),'ally');add(s,'far',(10,8),'ally')
        for target in ['player','ally','far']:s.conditions[target]={'poison':{'name':'Яд','beneficial':False,'until':5},'stun':{'name':'Оглушение','beneficial':False,'until':5},'buff':{'name':'Бонус','beneficial':True,'until':5}}
        s.conditions['player'].pop('stun');s._execute_ability(profile(resolve('Abl_PC_Leadership_RefusePain'),d),d,[SWORD])
        advance_graphs(s)
        self.assertEqual(set(s.conditions['ally']),{'buff'});self.assertIn('poison',s.conditions['far']);self.assertIn('buff',s.conditions['player'])

    def test_cascading_embrace_waits_thirty_seconds_and_then_hits_area(self):
        c,d,s=prepared('PSV_Comp_RngMagic_CascadingEmbrace');rule=owned_actions(c['talents'],d)[0]
        add(s,'near',(3,1))
        s._apply_ability_effects(rule,'enemy','target');self.assertTrue(s.pending_graphs)
        self.assertFalse(s.conditions.get('near'))
        advance_graphs(s);advance_graphs(s);self.assertTrue(s.pending_graphs)
        with patch('training_combat.random.randint',return_value=100):advance_graphs(s)
        self.assertFalse(s.pending_graphs);self.assertTrue(s.conditions['near'].get('silence'))

    def test_theft_deferred_ally_haste_not_immediate(self):
        _,d,s=prepared('Abl_Comp_Lantry_TheftOfMoments');add(s,'ally',(2,1),'ally');s.player_health=30
        s._execute_ability(profile(resolve('Abl_Comp_Lantry_TheftOfMoments'),d),d,[SWORD])
        self.assertTrue(s.pending_graphs);self.assertFalse(s.conditions.get('ally'))
        advance_graphs(s);self.assertFalse(s.conditions.get('ally'))
        advance_graphs(s);self.assertTrue(any(st.get('source',{}).get('AffectsStat')==2000 for st in s.conditions['ally'].values()))

    def test_passage_hours_slow_and_grip_restrict_melee(self):
        _,d,s=prepared();rule=profile(resolve('Abl_Comp_Lantry_PassageOfHours'),d)
        s._apply_ability_effects(rule,'player','target');new=s._combat_derived(_derived(s.runtime_character,[SWORD,*virtual_equipment(s.conditions['player'],1)]))
        self.assertAlmostEqual(new['cooldownMultiplier'],d['cooldownMultiplier']*4)
        self.assertEqual(s._movement_limit(),1)
        grip=profile(resolve('Abl_Comp_RngMagic_TerratusGrip'),d);s._apply_ability_effects(grip,'enemy','target')
        self.assertIn('suspend',s.conditions['enemy'])
        with patch('training_combat.random.randint',return_value=100):
            h=s._roll_attack(name='Меч',accuracy=0,low=10,high=10,defense=0,armor=0,target_id='enemy',attack_mode='melee');self.assertEqual(h['damage'],0)
            h=s._roll_attack(name='Стрела',accuracy=0,low=10,high=10,defense=0,armor=0,target_id='enemy',attack_mode='ranged');self.assertGreater(h['damage'],0)

    def test_escape_upgrade_separates_self_from_enemy(self):
        c,d,s=prepared('Abl_PC_Ranged_Escape');rule=owned_actions(c['talents'],d)[0]
        self.assertTrue(rule['supported'])
        s._apply_ability_effects(rule,'enemy','target');s._apply_ability_effects(rule,'player','self')
        self.assertTrue(s.conditions['enemy'].get('root'));self.assertTrue(s.disengaged)
        self.assertFalse(s.conditions['player'].get('root'))

    def test_banner_center_does_not_follow_player(self):
        _,d,s=prepared('Abl_PC_Leadership_Undying');s.aim_point=(4,1);add(s,'ally',(4,2),'ally')
        rule=profile(resolve('Abl_PC_Leadership_Undying'),d);s._execute_ability(rule,d,[SWORD])
        self.assertTrue(s.pending_graphs);self.assertEqual(s.pending_graphs[0]['center'],[4,1])
        s.player_position=(10,8);advance_graphs(s);self.assertEqual(s.pending_graphs[0]['center'],[4,1])

    def test_shieldbanger_and_blood_victory_only_active_stance(self):
        c,d,s=prepared('Abl_PC_Defense_StanceShieldbanger','PSV_PC_Defense_BloodBringsVictory')
        self.assertTrue(stance_equipment('Abl_PC_Defense_StanceShieldbanger'))
        s.active_stance=resolve('Abl_PC_Defense_StanceShieldbanger')['name']
        with patch('training_combat.random.randint',return_value=100):advance_graphs(s)
        self.assertIn('taunt',s.conditions['enemy'])
