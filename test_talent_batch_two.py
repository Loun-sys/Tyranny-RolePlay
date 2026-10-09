"""Each reviewed position has source checks and executable behavior coverage."""
import copy
import unittest
from unittest.mock import patch
from ability_rules import resolve,profile,owned_actions,talent_mechanics,stance_equipment
from consumables import virtual_equipment
from registration_api import _derived
from talent_batch_two import BATCH_KEYS,on_damage,contextual,retaliation_profiles
from talent_batch_one import skill_xp_bonuses
from talent_reactions import free_attack,react_to_damage
from test_talent_batch_one import prepared,add,maxroll
from test_talent_runtime import actor
from test_talent_reactions import SWORD


class ManifestTests(unittest.TestCase):
    def test_exactly_thirty(self):self.assertEqual(len(set(BATCH_KEYS)),30)

def check_source(key):
    def test(self):
        row=resolve(key);self.assertEqual(row['source']['archive'],'abilities')
        m=talent_mechanics(row);self.assertFalse(m['limitation']);self.assertTrue(m['effects'])
    return test
for key in BATCH_KEYS:setattr(ManifestTests,'test_source_'+key,check_source(key))


class EventTests(unittest.TestCase):
    def test_elemental_proc_survives_fully_absorbed_physical_hit(self):
        _,d,s=prepared('PSV_PC_Magic_ImbueTheElementsFire')
        d['attack']['criticalChance']=0
        s.targets['enemy']['armorByType']={'Огненный':0,'Рубящий':0}
        s.conditions['enemy']={'shield':{'shieldRemaining':40}}
        with patch('training_combat.random.randint',side_effect=lambda lo,hi:80 if hi==100 else hi):
            h=s._roll_attack(name='Удар',accuracy=0,low=40,high=40,defense=0,armor=0,target_id='enemy',damage_type='Рубящий')
        self.assertEqual(h['damage'],10)

    def test_all_three_elements_have_separate_armor_and_no_spell_proc(self):
        for suffix,kind in [('Fire','Огненный'),('Frost','Ледяной'),('Shock','Электрический')]:
            with self.subTest(suffix=suffix):
                _,d,s=prepared('PSV_PC_Magic_ImbueTheElements'+suffix)
                d['attack']['criticalChance']=0;s.targets['enemy']['armorByType']={kind:4}
                with patch('training_combat.random.randint',side_effect=lambda lo,hi:80 if hi==100 else hi):
                    h=s._roll_attack(name='Удар',accuracy=0,low=40,high=40,defense=0,armor=0,target_id='enemy')
                    self.assertEqual(h['damage'],46);self.assertEqual(s.events[-1]['elemental'],[{'type':kind,'damage':6}])
                    h=s._roll_attack(name='Заклинание',accuracy=0,low=40,high=40,defense=0,armor=0,target_id='enemy',weapon_attack=False)
                    self.assertEqual(h['damage'],40);self.assertNotIn('elemental',s.events[-1])

    def test_know_enemy_each_rank_damage_stack_and_graze(self):
        for rank in (1,2):
            c,d,s=prepared(f'PSV_Comp_Verse_KnowYourEnemy_0{rank}')
            on_damage(s,'player',0);self.assertFalse(s.conditions)
            for _ in range(22):on_damage(s,'player',1)
            new=_derived(c,[SWORD,*virtual_equipment(s.conditions['player'],1)])
            self.assertEqual(new['defenses']['Парирование']-d['defenses']['Парирование'],40)
            self.assertEqual(new['defenses']['Уклонение']-d['defenses']['Уклонение'],40)
            with patch('training_combat.random.randint',return_value=50):
                s._roll_attack(name='Задевание',accuracy=0,low=10,high=10,defense=0,armor=0,target_id='enemy')
            accuracy_states=[v for v in s.conditions['player'].values() if v.get('source',{}).get('AffectsStat')==185]
            self.assertEqual(len(accuracy_states),1 if rank==2 else 0)
            if rank==2:self.assertEqual(accuracy_states[0]['source']['Value'],2)

    def test_know_ranks_replace_not_double_and_do_not_leak_to_new_battle(self):
        _,_,s=prepared('PSV_Comp_Verse_KnowYourEnemy_01','PSV_Comp_Verse_KnowYourEnemy_02');on_damage(s,'player',1)
        self.assertEqual(len(s.conditions['player']),2)
        _,_,fresh=prepared('PSV_Comp_Verse_KnowYourEnemy_02');self.assertFalse(fresh.conditions)

    def test_scar_requires_wound_not_missing_health(self):
        c,d,s=prepared('PSV_Comp_Beastwoman_ScarsOfBattle');s.player_health=1
        self.assertEqual(contextual(s,d)['attack']['damageMin'],10)
        c['wounds']=1;self.assertEqual(contextual(s,d)['attack']['damageMin'],12)
        c['wounds']=4;self.assertEqual(contextual(s,d)['attack']['damageMin'],12)

    def test_dual_claw_strict_threshold_and_healing(self):
        _,d,s=prepared('PSV_Comp_Beastwoman_DualClaw')
        s.player_health=140;self.assertEqual(contextual(s,d)['talentRuntime'].get(2157,1),1)
        s.player_health=139;self.assertEqual(contextual(s,d)['talentRuntime'][2157],2)
        s.player_health=141;self.assertEqual(contextual(s,d)['talentRuntime'].get(2157,1),1)

    def test_clear_mind_loses_both_bonuses_on_damage_and_recovers_next_round(self):
        _,d,s=prepared('PSV_Comp_RngMagic_ClearMind');d['attack']['recovery']=2
        active=contextual(s,d);self.assertEqual(active['talentRuntime'][2157],2);self.assertAlmostEqual(active['cooldownMultiplier'],d['cooldownMultiplier']*.8)
        self.assertAlmostEqual(active['attack']['recovery'],1.6)
        on_damage(s,'player',10);self.assertEqual(contextual(s,d)['talentRuntime'].get(2157,1),1)
        s.round_number+=1;self.assertEqual(contextual(s,d)['talentRuntime'][2157],2)

    def test_lethal_opening_all_melee_weapons_not_only_single_sword(self):
        _,_,s=prepared();s.targets['enemy'].update(abilities=[{'key':'PSV_Comp_Verse_LethalOpening'}],
            inventory=[SWORD,{**SWORD,'equipped_slot':'Оружие I — левая рука'}],attack={'accuracy':200,'damageMin':10,'damageMax':10,'range':1,'skill':'Парное оружие'})
        with patch('training_combat.random.randint',side_effect=lambda lo,hi:1 if hi==100 else hi),patch('talent_reactions.random.random',return_value=0):
            s._roll_attack(name='Промах',accuracy=-500,low=10,high=10,defense=0,armor=0,target_id='enemy')
        self.assertLess(s.player_health,200);self.assertTrue(s.action_available)
        self.assertEqual(len([e for e in s.events if e.get('reaction')]),1)

    def test_opportunity_attack_bonuses_are_not_permanent(self):
        _,d,s=prepared('PSV_Comp_Beastwoman_SeizePrey');d['attack']['accuracy']=0
        with patch('training_combat.random.randint',side_effect=lambda lo,hi:50 if hi==100 else hi):
            h=free_attack(s,'player','enemy','Выход',opportunity=True)
        self.assertEqual(h['damage'],25);self.assertEqual(d['attack']['accuracy'],0)
        _,_,s=prepared('PSV_Comp_Sirin_DisarmingGuise');s.targets['enemy'].update(attack={'accuracy':0,'damageMin':10,'damageMax':10,'range':1})
        with patch('training_combat.random.randint',side_effect=lambda lo,hi:50 if hi==100 else hi):h=free_attack(s,'enemy','player','Выход',opportunity=True)
        self.assertEqual(h['damage'],0)

    def test_erase_seal_fires_once_only_on_alive_below_threshold(self):
        _,_,s=prepared();rule=profile(resolve('Abl_Comp_Lantry_EraseTheRecord'))
        s._apply_ability_effects(rule,'player','target');self.assertEqual(s.player_health,200)
        s.player_health=70;on_damage(s,'player',1);self.assertEqual(s.player_health,70)
        s.player_health=69;on_damage(s,'player',1);self.assertEqual(s.player_health,139)
        on_damage(s,'player',1);self.assertEqual(s.player_health,139)
        s._apply_ability_effects(rule,'player','target');s.player_health=0;on_damage(s,'player',1);self.assertEqual(s.player_health,0)

    def test_teacher_covers_actual_existing_schools_once(self):
        bonuses=skill_xp_bonuses([{'key':'PSV_Comp_RngMagic_RunicTeacher_1of2'}])
        for skill in ['Знания','Волшебный посох','Управление огнём','Управление холодом','Управление эмоциями','Управление могильным светом']:
            self.assertAlmostEqual(bonuses[skill],.2)
        self.assertNotIn('Кислота',bonuses)


class GraphTests(unittest.TestCase):
    def cast(self,key,s=None):
        c,d,s=prepared(key) if s is None else s
        for skill in d['effectiveSkills']:d['effectiveSkills'][skill]=200
        d['attack']['accuracy']=200
        rule=owned_actions(c['talents'],d)[0];rule['accuracy']=200
        with patch('training_combat.random.randint',side_effect=maxroll):s._execute_ability(rule,d,s.consumable_inventory)
        return c,d,s,rule

    def test_renewal_both_ranks_equipment_only_armor_and_penetration(self):
        for key,bonus,penetration in [('Abl_Comp_Lantry_Renewal',.5,1),('ABL_Comp_Lantry_GreaterRenewal',1,2)]:
            _,_,s=prepared();rule=profile(resolve(key));s._apply_ability_effects(rule,'player','target')
            item={'name':'Кожа','equipped_slot':'Торс','armor':4,'properties':{'gameData':{'armor':{'ArmorCategory':1}}}}
            c=actor();d=_derived(c,[SWORD,item,*virtual_equipment(s.conditions['player'],1)])
            self.assertEqual(d['armor'],4*(1+bonus));self.assertEqual(d['armorByType']['Огненный'],4*(1+bonus))
            self.assertEqual(d['attack']['penetration'],penetration)
            self.assertEqual(_derived(c,virtual_equipment(s.conditions['player'],1))['armor'],0)
            self.assertTrue(all(e['until']==6 for e in s.conditions['player'].values()))

    def test_resolve_extends_existing_seconds_and_adds_stats(self):
        c,d,s=prepared();s.conditions['player']={'short':{'beneficial':True,'until':1,'source':{'Duration':6},'remainingSeconds':6},
            'hostile':{'beneficial':False,'until':1,'source':{'Duration':6}}}
        s._apply_ability_effects(profile(resolve('Abl_Comp_Sirin_AriaOfResolve')),'player','target')
        self.assertEqual(s.conditions['player']['short']['until'],2);self.assertEqual(s.conditions['player']['hostile']['until'],1)
        new=_derived(c,[SWORD,*virtual_equipment(s.conditions['player'],1)])
        self.assertEqual(new['effectiveAttributes']['Стойкость'],d['effectiveAttributes']['Стойкость']+4)
        self.assertEqual(new['defenses']['Парирование'],d['defenses']['Парирование']+22) # +20 and attribute-to-skill +2

    def test_primal_scream_selects_stealth_graph_and_cone(self):
        for hidden in (False,True):
            c,d,s=prepared('ABL_Comp_Beastwoman_PrimalScream');s.stealthed=hidden;add(s,'behind',(0,1));add(s,'ally',(2,2),'ally')
            self.cast('ABL_Comp_Beastwoman_PrimalScream',(c,d,s))
            self.assertEqual(s.conditions['enemy']['fear']['until'],1 if hidden else 2)
            self.assertEqual('confus' in s.conditions['enemy'],hidden)
            self.assertFalse(s.conditions.get('behind'));self.assertFalse(s.conditions.get('ally'))

    def test_watchers_breach_always_paralysis_only_stealth(self):
        for hidden in (False,True):
            c,d,s=prepared('Abl_Comp_Lantry_WatchersJudgement');s.stealthed=hidden
            _,_,s,rule=self.cast('Abl_Comp_Lantry_WatchersJudgement',(c,d,s))
            armor_states={e['source'].get('DmgType') for e in s.conditions['enemy'].values() if e.get('source',{}).get('AffectsStat')==14}
            self.assertEqual(armor_states,{3,4,5,7});self.assertEqual('paralyze' in s.conditions['enemy'],hidden)
            self.assertTrue(rule['supported'])

    def test_arcane_upgrade_own_aoe_and_three_defenses(self):
        c,d,s=prepared('TLN_Comp_Lantry_ArcaneJudgment');add(s,'near',(3,1));add(s,'ally',(2,2),'ally')
        self.cast('TLN_Comp_Lantry_ArcaneJudgment',(c,d,s))
        self.assertLess(s.target_healths['near'],1000);self.assertEqual(s.target_healths['ally'],1000)
        for t in ['enemy','near']:self.assertTrue({7,8,9}<={e.get('source',{}).get('AffectsStat') for e in s.conditions[t].values()})

    def test_reviving_upgrade_only_dead_allies_and_original_breath_cost(self):
        c,d,s=prepared('PSV_Comp_Sirin_RevivingSong');s.breath=100;add(s,'fallen',(2,1),'ally');s.target_healths['fallen']=0
        add(s,'living',(2,2),'ally');s.target_healths['living']=500;add(s,'far',(8,8),'ally');s.target_healths['far']=0
        _,_,s,rule=self.cast('PSV_Comp_Sirin_RevivingSong',(c,d,s))
        self.assertEqual(s.target_healths['fallen'],350);self.assertEqual(s.target_healths['far'],0)
        self.assertEqual(s.breath,100-rule['breathCost']);self.assertEqual(s.target_healths['enemy'],1000)

    def test_mark_applies_to_only_hit_target_and_is_not_permanent_actor_bonus(self):
        c,d,s=prepared('Abl_PC_Leadership_MarkEnemy');add(s,'other',(1,2));self.cast('Abl_PC_Leadership_MarkEnemy',(c,d,s))
        def accuracy(t):return s._attack_parameters(accuracy=0,defense=0,armor=0,target_id=t)['accuracy']
        self.assertEqual(accuracy('enemy'),20);self.assertEqual(accuracy('other'),0)
        self.assertEqual(_derived(c,[SWORD])['attack']['accuracy'],_derived(actor(),[SWORD])['attack']['accuracy'])

    def test_shadow_upgrade_critical_bonus_only_triggering_ability_and_self_buff(self):
        c,d,s=prepared('ABL_Comp_Beastwoman_ShadowOfDeath');rule=owned_actions(c['talents'],d)[0];rule['accuracy']=200
        with patch('training_combat.random.randint',side_effect=maxroll):result=s._execute_ability(rule,d,[SWORD])
        self.assertEqual(result['damage'],round(10*rule['weaponMultiplier']*3))
        self.assertTrue(any(e.get('source',{}).get('AffectsStat')==45 and e['until']==999999 for e in s.conditions['player'].values()))
        self.assertFalse(any(e.get('source',{}).get('AffectsStat')==101 for e in s.conditions.get('enemy',{}).values()))

    def test_gravestrike_drains_armor_independent_and_heals_caster_not_enemy(self):
        c,d,s=prepared('Abl_Comp_RngMagic_Gravestrike');s.player_health=100;s.targets['enemy']['armor']=500
        self.cast('Abl_Comp_RngMagic_Gravestrike',(c,d,s))
        self.assertEqual(s.target_healths['enemy'],988);self.assertEqual(s.player_health,106)

    def test_channel_strength_race_filter_and_followup_runs_once(self):
        c,d,s=prepared('Abl_PC_Magic_ChannelStrength');s.consumable_inventory=[{**SWORD,'category':'Посохи'}]
        add(s,'scourge',(3,1),race=3);s.player_health=100
        self.cast('Abl_PC_Magic_ChannelStrength',(c,d,s))
        self.assertTrue(any(e['targetId']=='scourge' and e['result']=='Вытягивание здоровья' and e['damage']==20 for e in s.events))
        self.assertFalse(any(e['targetId']=='enemy' and e['result']=='Вытягивание здоровья' for e in s.events))
        self.assertEqual(s.player_health,120)

    def test_call_to_grave_once_strictly_below_35_percent_and_free(self):
        _,d,s=prepared('PSV_Comp_RngMagic_CallToTheGrave');d['effectiveSkills']['Управление могильным светом']=200
        s.player_health=70;react_to_damage(s,'player');self.assertEqual(s.target_healths['enemy'],1000)
        s.player_health=69
        with patch('training_combat.random.randint',side_effect=maxroll):react_to_damage(s,'player')
        self.assertEqual(s.target_healths['enemy'],984);self.assertEqual(s.player_health,85);self.assertTrue(s.action_available)
        s.player_health=69;react_to_damage(s,'player');self.assertEqual(s.target_healths['enemy'],984)

    def test_health_transfer_kill_uses_same_kill_handlers(self):
        c,d,s=prepared('Abl_Comp_RngMagic_Gravestrike','PSV_PC_Power_Rampage');s.target_healths['enemy']=1
        self.cast('Abl_Comp_RngMagic_Gravestrike',(c,d,s))
        self.assertEqual(s.target_healths['enemy'],0)
        self.assertEqual(s.conditions['player']['talent-kills:PSV_PC_Power_Rampage']['source']['Value'],15)

    def test_blood_calls_crit_melee_area_not_normal_or_ranged(self):
        _,d,s=prepared('PSV_Comp_Verse_BloodCallsToBlood');add(s,'near',(3,1));add(s,'far',(8,8))
        with patch('training_combat.random.randint',side_effect=maxroll):
            s._weapon_talent_procs('enemy','Попадание');self.assertEqual(s.target_healths['near'],1000)
            d['attack']['skill']='Луки';s._weapon_talent_procs('enemy','Критическое попадание');self.assertEqual(s.target_healths['near'],1000)
            d['attack']['skill']='Одноручное оружие';s._weapon_talent_procs('enemy','Критическое попадание')
        self.assertLess(s.target_healths['near'],1000);self.assertEqual(s.target_healths['far'],1000)


class RetaliationTests(unittest.TestCase):
    def test_player_retaliation_inside_npc_executor_does_not_chain(self):
        c,d,s=prepared('PSV_Comp_Sirin_VengefulPitch')
        d['effectiveSkills']['Исполнение']=200
        s.targets['enemy'].update(attack={'accuracy':200,'damageMin':10,'damageMax':10,'range':1})
        with patch('training_combat.random.randint',side_effect=maxroll):free_attack(s,'enemy','player','НПС')
        # Primary free attacks deliberately do not trigger a new reaction chain.
        self.assertFalse(s.conditions.get('enemy'));self.assertEqual(len(s.events),1)

    def test_player_damage_stack_inside_npc_executor_persists(self):
        c,d,s=prepared('PSV_Comp_Verse_KnowYourEnemy_02')
        s.targets['enemy'].update(attack={'accuracy':200,'damageMin':10,'damageMax':10,'range':1})
        with patch('training_combat.random.randint',side_effect=maxroll):free_attack(s,'enemy','player','НПС')
        self.assertEqual({v['source']['Value'] for v in s.conditions['player'].values() if v.get('source',{}).get('AffectsStat') in {2026,2027}},{2})

    def test_vengeful_phalanx_dissonance_last_stand_react_only_to_melee_hit(self):
        shield={**SWORD,'category':'Щиты','equipped_slot':'Оружие I — левая рука'}
        for key in ['PSV_Comp_Sirin_VengefulPitch','Abl_Comp_Defender_Stance_Phalanx_02','Abl_Comp_Sirin_AriaOfDissonance','ABL_HH_Sentinel_Last_Stand']:
            with self.subTest(key=key):
                c,d,s=prepared();row=resolve(key)
                s.targets['enemy'].update(inventory=[SWORD,shield],attack={'accuracy':200,'damageMin':10,'damageMax':10,'range':1},
                    skills={'Исполнение':200,'Одноручное оружие':200})
                if row.get('modal'):s.targets['enemy']['combatStance']=row['name']
                if key=='Abl_Comp_Sirin_AriaOfDissonance':s._apply_ability_effects(profile(row),'enemy','target')
                else:s.targets['enemy']['abilities']=[{'key':key}]
                if 'Last_Stand' in key:s.target_healths['enemy']=400
                before=s.player_health
                with patch('training_combat.random.randint',side_effect=maxroll):
                    s._roll_attack(name='Стрела',accuracy=200,low=10,high=10,defense=0,armor=0,target_id='enemy',attack_mode='ranged')
                    self.assertEqual(s.player_health,before)
                    s._roll_attack(name='Меч',accuracy=200,low=10,high=10,defense=0,armor=0,target_id='enemy')
                if key=='PSV_Comp_Sirin_VengefulPitch':self.assertTrue(any(e.get('source',{}).get('Value')==row['nodes'][1]['statuses'][0]['Value'] for e in s.conditions['player'].values()))
                else:self.assertLess(s.player_health,before)
                self.assertTrue(s.action_available);self.assertEqual(len([e for e in s.events if e.get('reaction')]),1)

    def test_last_stand_parry_is_conditional_not_permanent(self):
        c,d,s=prepared('ABL_HH_Sentinel_Last_Stand');base=_derived(actor(),[SWORD])
        self.assertEqual(d['defenses']['Парирование'],base['defenses']['Парирование'])
        s.player_health=100;self.assertEqual(contextual(s,d)['defenses']['Парирование'],base['defenses']['Парирование'])
        s.player_health=99;self.assertEqual(contextual(s,d)['defenses']['Парирование'],base['defenses']['Парирование']+20)


if __name__=='__main__':unittest.main()
