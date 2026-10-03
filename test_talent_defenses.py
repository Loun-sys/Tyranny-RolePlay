"""Behavioral coverage for source-keyed ranged defenses and status duration talents."""
import unittest
from unittest.mock import patch
from ability_rules import resolve,profile,talent_mechanics,owned_actions
from registration_api import _derived
from training_combat import TrainingSession
from talent_runtime import incoming_defense,incoming_conversions,reflection_chance,hostile_duration,weapon_mode
from test_talent_runtime import actor
from test_consumables import character


class TalentDefenseTests(unittest.TestCase):
    def test_target_defenses_are_isolated_between_tokens_and_sessions(self):
        a=TrainingSession(1);b=TrainingSession(2)
        original=b.targets['dummy']['defenses']['Парирование']
        a.targets['dummy']['defenses']['Парирование']=999
        self.assertEqual(b.targets['dummy']['defenses']['Парирование'],original)
        self.assertEqual(a.targets['dummy_left']['defenses']['Парирование'],original)

    def target(self,*keys):
        c=character();s=TrainingSession(1);s.view(c,_derived(c,[]),[],2)
        s.player_position=(9,4)
        s.targets['dummy']['abilities']=[{'key':key} for key in keys]
        s.targets['dummy']['armor']=0
        return s

    def shot(self,s,mode='ranged',score=80):
        with patch('training_combat.random.randint',side_effect=lambda lo,hi:score if hi==100 else lo),patch('training_combat.random.random',return_value=0):
            return s._roll_attack(name='Проверка',accuracy=0,low=10,high=10,defense=0,armor=0,
                                  attack_mode=mode,defense_name='Уклонение')

    def test_arrow_shield_uses_better_parry_for_projectile(self):
        s=self.target('PSV_PC_Agility_ArrowShield');s.targets['dummy']['defenses'].update(Парирование=100,Уклонение=0)
        self.assertEqual(self.shot(s)['result'],'Промах')

    def test_arrow_shield_does_not_replace_spell_defense(self):
        s=self.target('PSV_PC_Agility_ArrowShield');s.targets['dummy']['defenses'].update(Парирование=100,Уклонение=0)
        self.assertEqual(self.shot(s,'spell')['damage'],10)

    def test_arrow_shield_never_lowers_dodge(self):
        self.assertEqual(incoming_defense({2146:0},{'Парирование':10,'Уклонение':50},'Уклонение','ranged'),50)

    def test_blade_dancing_parry_per_adjacent_enemy(self):
        rules={2143:5};defenses={'Парирование':20}
        self.assertEqual(incoming_defense(rules,defenses,'Парирование','melee',2),30)
        self.assertEqual(incoming_defense(rules,defenses,'Парирование','melee',0),20)

    def test_blade_dancing_conversions_only_melee(self):
        self.assertEqual(incoming_conversions({2147:.1,2148:.1},'melee'),{'hitToGraze':10,'grazeToMiss':10})
        self.assertEqual(incoming_conversions({2147:.1,2148:.1},'spell'),{})

    def test_blade_dancing_actual_damage_is_reduced(self):
        s=self.target('PSV_PC_Agility_BladeDancing');s.targets['dummy']['defenses']['Уклонение']=0
        # First roll hits, conversion rolls fall below 10%: hit -> graze -> miss.
        with patch('training_combat.random.randint',side_effect=[80,1,1]):
            hit=s._roll_attack(name='Удар',accuracy=0,low=10,high=10,defense=0,armor=0,attack_mode='melee')
        self.assertEqual(hit['damage'],0)

    def test_arrowcatch_reflects_into_attacker_health(self):
        s=self.target('PSV_PC_Ranged_Arrowcatch');s.targets['dummy']['defenses']['Уклонение']=0
        before=s.player_health;target=s.target_healths['dummy']
        result=self.shot(s)
        self.assertEqual(result['result'],'Отражено')
        self.assertEqual(s.player_health,before-10);self.assertEqual(s.target_healths['dummy'],target)
        self.assertEqual(s.damage_total,0)

    def test_arrowcatch_does_not_reflect_spell(self):
        s=self.target('PSV_PC_Ranged_Arrowcatch');s.targets['dummy']['defenses']['Уклонение']=0
        self.assertEqual(self.shot(s,'spell')['damage'],10)
        self.assertEqual(weapon_mode({'skill':'Волшебный посох'}),'magic-ranged')
        self.assertEqual(reflection_chance({2138:100},'magic-ranged','Попадание'),0)

    def test_lightning_reflexes_only_reflect_graze(self):
        self.assertEqual(reflection_chance({2121:.5},'ranged','Скользящий удар'),.5)
        self.assertEqual(reflection_chance({2121:.5},'ranged','Попадание'),0)
        self.assertEqual(reflection_chance({2121:.5},'melee','Скользящий удар'),0)
        self.assertEqual(reflection_chance({2121:.5},'magic-ranged','Скользящий удар'),.5)

    def test_lightning_reflexes_actual_graze_reflection(self):
        s=self.target('PSV_Comp_Verse_LightningReflexes');s.targets['dummy']['defenses']['Уклонение']=0
        before=s.player_health
        self.assertEqual(self.shot(s,score=40)['result'],'Отражено')
        self.assertEqual(s.player_health,before-5)

    def test_reaching_claws_stays_melee_and_grants_ability_range(self):
        c=actor('PSV_Comp_Beastwoman_ReachingClaws','Abl_PC_Thrust');d=_derived(c,[])
        self.assertEqual(d['attack']['range'],2);self.assertEqual(weapon_mode(d['attack']),'melee')
        thrust=next(a for a in owned_actions(c['talents'],d,2) if a['key']=='Abl_PC_Thrust')
        self.assertEqual(thrust['range'],resolve('Abl_PC_Thrust')['range']+.5)

    def test_bow_penetration_uses_highest_rank_and_not_sword(self):
        c=actor('PSV_Comp_Verse_PiercingArrows_01','PSV_Comp_Verse_PiercingArrows_02')
        bow={'name':'Лук','category':'Луки','equipped_slot':'Оружие I — правая рука'}
        self.assertEqual(_derived(c,[bow])['attack']['penetration'],4)
        sword={**bow,'category':'Одноручное оружие'}
        self.assertEqual(_derived(c,[sword])['attack']['penetration'],0)

    def test_duration_scales_seconds_before_rounding(self):
        effect={'control':'freeze','Duration':12}
        self.assertEqual(hostile_duration(effect,{}, {2120:.8})['rounds'],1)
        self.assertEqual(effect['Duration'],12)
        self.assertEqual(hostile_duration({'control':'stun','Duration':20},{2116:1.2},{})['rounds'],3)

    def test_beneficial_duration_is_unchanged(self):
        e={'AffectsStat':57,'Duration':20,'IsHostile':0}
        self.assertEqual(hostile_duration(e,{2116:1.2},{2120:.8}),e)

    def test_fluid_body_actual_received_control_duration(self):
        s=self.target('PSV_Comp_RngMagic_FluidBody')
        s._apply_ability_effects({'key':'qa','effects':[{'side':'target','control':'freeze','Duration':12,'name':'Холод'}]},'dummy','target')
        self.assertEqual(s.conditions['dummy']['freeze']['until'],s.round_number)

    def test_empowered_affliction_actual_outgoing_control_duration(self):
        c=actor('PSV_Comp_RngMagic_EmpoweredAfflictions');s=TrainingSession(1);s.view(c,_derived(c,[]),[],2)
        s._apply_ability_effects({'key':'qa','effects':[{'side':'target','control':'stun','Duration':20,'name':'Оглушение'}]},'dummy','target')
        self.assertEqual(s.conditions['dummy']['stun']['until'],s.round_number+2)

    def test_iron_light_as_air_removes_recovery_and_allows_double_attack(self):
        c=actor('Abl_PC_Defense_IronLightAsAir');s=TrainingSession(1);d=_derived(c,[])
        d['equipmentRecovery']=1;d['attack']['recovery']=1
        s.act({'kind':'ability','name':'Abl_PC_Defense_IronLightAsAir'},c,d,[],2)
        self.assertEqual(s._combat_derived(d)['equipmentRecovery'],0)
        s._end_turn();s.player_position=(9,4)
        with patch('training_combat.random.randint',side_effect=lambda lo,hi:lo):
            s.act({'kind':'attack'},c,d,[],2)
        self.assertEqual(s.attacks,2)
        s._end_turn()
        self.assertEqual(s._combat_derived(d)['equipmentRecovery'],1)

    def test_covered_talents_have_no_missing_handler_warning(self):
        for key in ['PSV_PC_Agility_ArrowShield','PSV_PC_Agility_BladeDancing','PSV_PC_Ranged_Arrowcatch',
                    'PSV_Comp_Verse_LightningReflexes','PSV_Comp_RngMagic_FluidBody','PSV_Comp_RngMagic_EmpoweredAfflictions',
                    'PSV_Comp_Verse_PiercingArrows_01','PSV_Comp_Verse_PiercingArrows_02',
                    'PSV_Comp_Beastwoman_ReachingClaws','Abl_PC_Defense_IronLightAsAir']:
            with self.subTest(key=key):self.assertEqual(talent_mechanics(resolve(key)).get('limitation',''),'')

    def test_tooltip_percentages_match_executor_units(self):
        from consumables import effect_text
        self.assertIn('+10%',effect_text({'AffectsStat':2147,'Value':.1}))
        self.assertIn('+20%',effect_text({'AffectsStat':2138,'Value':20}))
        self.assertIn('+50%',effect_text({'AffectsStat':2121,'Value':.5}))

    def test_master_npc_projectile_can_be_reflected_by_player(self):
        c=actor('PSV_PC_Ranged_Arrowcatch');s=TrainingSession(1);d=_derived(c,[]);s.view(c,d,[],2)
        key='Abl_Comp_Verse_Hobble'
        s.targets['dummy'].update(kind='npc',abilities=[resolve(key)],attributes=c['attributes'],skills={'Луки':80},
                                  attack={'accuracy':80,'damageMin':10,'damageMax':10,'range':12},
                                  equipment=[{'name':'Лук','category':'Луки','slot':'PrimaryWeapon'}])
        s.target_positions['dummy']=(4,4);before=s.player_health;enemy=s.target_healths['dummy']
        with patch('training_combat.random.randint',side_effect=lambda lo,hi:80 if hi==100 else lo),patch('training_combat.random.random',return_value=0):
            result=s.master_npc_ability('dummy',key,'player',c,d)
        self.assertEqual(result['damage'],0)
        self.assertEqual(s.player_health,before);self.assertLess(s.target_healths['dummy'],enemy)
        self.assertNotIn('hobble',s.conditions.get('player',{}))


if __name__=='__main__':unittest.main()
