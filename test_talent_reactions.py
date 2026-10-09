"""Behavioral tests for Ward Master and all three Duelist ranks."""
import copy
import unittest
from unittest.mock import patch

import test_shared_battles as shared
from ability_rules import resolve,profile,owned_actions,talent_mechanics
from combat_math import outcome_distribution
from consumables import effect_text,virtual_equipment
from item_effects import armor_by_type
from registration_api import _derived
from sigil_data import spell_runtime_profile
from tactical_grid import TacticalGrid
from talent_runtime import effects,riposte_chance,single_weapon_bonus,spell_conversions
from talent_reactions import actor_inventory,npc_attack
from test_consumables import character
from test_talent_runtime import actor
from training_combat import TrainingSession,DUMMY

WARD='PSV_PC_Magic_WardMaster'
DUELISTS=[f'PSV_PC_Agility_Duelist_{rank}of3' for rank in (1,2,3)]
SWORD={'name':'Меч','category':'Одноручное оружие','damage_min':10,'damage_max':10,
       'equipped_slot':'Оружие I — правая рука'}
SPELL={'id':1,'name':'Искра','core':'Молнии','expression':'Сосредоточенное намерение','accents':[],
       'enhancements':[],'equipped_slot':0}


def session(c=None,inventory=None):
    c=c or character();c.update(health=200,health_max=200)
    d=_derived(c,inventory or []);d['attack']['criticalChance']=0
    s=TrainingSession(1);s.grid=TacticalGrid(12,12);s.player_position=(1,1)
    s.targets={'enemy':{**copy.deepcopy(DUMMY),'name':'Дуэлянт','armor':0,'healthMax':1000,
                        'defenses':dict.fromkeys(['Парирование','Уклонение','Магия'],0)}}
    s.target_positions={'enemy':(2,1)};s.target_healths={'enemy':1000};s.selected_target_id='enemy'
    s.consumable_inventory=copy.deepcopy(inventory or [])
    s.view(c,d,[],2)
    return c,d,s


def duelist(s,rank=3):
    s.targets['enemy'].update(abilities=[{'key':DUELISTS[rank-1]}],inventory=[copy.deepcopy(SWORD)],
                             attack={'accuracy':0,'damageMin':10,'damageMax':10,'range':1},
                             attributes=dict(character()['attributes']))
    return s


def strike(s,roll=1,chance=0,counter_roll=80,**kwargs):
    options=dict(name='Проверка',accuracy=0,low=10,high=10,defense=0,armor=0,target_id='enemy')
    options.update(kwargs)
    # The incoming strike misses; a successful reaction gets its own roll.
    rolls=iter([roll,counter_roll])
    with patch('training_combat.random.randint',side_effect=lambda lo,hi:next(rolls) if hi==100 else lo), \
         patch('training_combat.random.random',return_value=chance):
        return s._roll_attack(**options)


class WardMasterTests(unittest.TestCase):
    def ward(self,s,target='enemy'):
        c=actor(WARD);a=owned_actions(c['talents'],_derived(c,[]))[0]
        s._apply_ability_effects(a,target,'target')
        return a

    def test_upgrade_grants_supported_shield_once(self):
        c=actor(WARD,'Abl_PC_Magic_EnergyShield');actions=owned_actions(c['talents'],_derived(c,[]))
        self.assertEqual([a['key'] for a in actions],['Abl_PC_Magic_EnergyShield'])
        self.assertTrue(actions[0]['supported']);self.assertFalse(talent_mechanics(resolve(WARD))['limitation'])

    def test_not_a_permanent_armor_or_conversion_bonus(self):
        d=_derived(actor(WARD),[]);base=_derived(character(),[])
        self.assertEqual(d['armorByType'],base['armorByType'])
        self.assertNotIn(2127,d['talentRuntime']);self.assertNotIn(2128,d['talentRuntime'])

    def test_actual_self_cast_adds_source_effects_for_six_rounds(self):
        c,d,s=session(actor(WARD));s.act({'kind':'ability','name':'Abl_PC_Magic_EnergyShield','targetId':'player'},c,d,[],2)
        states=s.conditions['player'];self.assertTrue(states)
        self.assertTrue(all(e['until']==6 for e in states.values()))
        for damage in ['Рубящий','Дробящий','Колющий','Огненный','Ледяной','Электрический']:
            self.assertEqual(sum(armor_by_type(i)[damage] for i in virtual_equipment(states,1)),4)
        self.assertEqual(spell_conversions(states,1),{'critToHit':50,'hitToGraze':50})
        self.assertFalse(s.action_available)

    def test_cast_on_ally_not_enemy(self):
        c,d,s=session(actor(WARD));s.targets['enemy']['team']='ally'
        s.targets['hostile']=copy.deepcopy(DUMMY);s.target_positions['hostile']=(8,8);s.target_healths['hostile']=1000
        s.act({'kind':'ability','name':'Abl_PC_Magic_EnergyShield','targetId':'enemy'},c,d,[],2)
        self.assertEqual(spell_conversions(s.conditions['enemy'],1)['critToHit'],50)
        c,d,s=session(actor(WARD))
        with self.assertRaises(ValueError):s.act({'kind':'ability','name':'Abl_PC_Magic_EnergyShield','targetId':'enemy'},c,d,[],2)
        self.assertFalse(s.conditions.get('enemy'));self.assertTrue(s.action_available)

    def test_duration_expires_and_recast_refreshes_without_stacking(self):
        _,_,s=session();self.ward(s);s.round_number=4;self.ward(s)
        self.assertEqual(spell_conversions(s.conditions['enemy'],9),{'critToHit':50,'hitToGraze':50})
        self.assertEqual(spell_conversions(s.conditions['enemy'],10),{})
        self.assertEqual(sum(armor_by_type(i)['Рубящий'] for i in virtual_equipment(s.conditions['enemy'],4)),4)

    def test_shield_blocks_physical_damage_and_does_not_leak_to_another_token(self):
        _,_,s=session();self.ward(s)
        self.assertEqual(strike(s,80,weapon_attack=False)['damage'],6)
        s.conditions['enemy']={}
        self.assertEqual(strike(s,80,weapon_attack=False)['damage'],10)

    def test_50_percent_boundary_not_5000_percent(self):
        for conversion_roll,result in [(50,'Скользящий удар'),(51,'Попадание')]:
            with self.subTest(conversion_roll=conversion_roll):
                _,_,s=session();self.ward(s)
                with patch('training_combat.random.randint',side_effect=[80,conversion_roll,10]):
                    hit=s._roll_attack(name='Магия',accuracy=0,low=10,high=10,defense=0,armor=0,
                                       attack_mode='spell',crafted_spell=True,weapon_attack=False,damage_type='магического')
                self.assertEqual(hit['result'],result)
        for stat in [2127,2128]:
            self.assertIn('+50%',effect_text({'AffectsStat':stat,'Value':50}));self.assertNotIn('5000',effect_text({'AffectsStat':stat,'Value':50}))

    def test_critical_is_downgraded_only_once(self):
        _,_,s=session();self.ward(s)
        with patch('training_combat.random.randint',side_effect=[100,1,10]) as rng:
            hit=s._roll_attack(name='Магия',accuracy=10,low=10,high=10,defense=0,armor=0,
                               crafted_spell=True,weapon_attack=False,attack_mode='spell',damage_type='магического')
        self.assertEqual(hit['result'],'Попадание');self.assertEqual(rng.call_count,3)

    def test_generic_conversion_prevents_a_second_special_conversion(self):
        _,_,s=session();self.ward(s);s.targets['enemy']['incomingConversions']={'critToHit':100}
        with patch('training_combat.random.randint',side_effect=[100,1,10]) as rng:
            hit=s._roll_attack(name='Магия',accuracy=10,low=10,high=10,defense=0,armor=0,
                               crafted_spell=True,weapon_attack=False,attack_mode='spell',damage_type='магического')
        self.assertEqual(hit['result'],'Попадание');self.assertEqual(rng.call_count,3)

    def test_promoted_hit_is_not_special_converted(self):
        _,_,s=session();self.ward(s);s.runtime_derived={'attack':{'criticalChance':100}}
        with patch('training_combat.random.randint',side_effect=[80,1,10]):
            hit=s._roll_attack(name='Магия',accuracy=0,low=10,high=10,defense=0,armor=0,
                               crafted_spell=True,weapon_attack=False,attack_mode='spell',damage_type='магического')
        self.assertEqual(hit['result'],'Критическое попадание')

    def test_noncrafted_spells_staff_and_songs_do_not_use_special_conversion(self):
        for mode in ['spell','magic-ranged','ranged','melee']:
            with self.subTest(mode=mode):
                _,_,s=session();self.ward(s)
                self.assertEqual(strike(s,80,attack_mode=mode,weapon_attack=False)['result'],'Попадание')

    def test_distribution_single_conversion_and_conservation(self):
        p=outcome_distribution(50,0,spell_conversions={'critToHit':50,'hitToGraze':50})
        self.assertAlmostEqual(p['critical'],.25);self.assertAlmostEqual(p['hit'],.5)
        self.assertAlmostEqual(p['graze'],.25);self.assertAlmostEqual(sum(p.values()),1)
        p=outcome_distribution(50,0,conversions={'critToHit':100},spell_conversions={'hitToGraze':100})
        self.assertAlmostEqual(p['hit'],.5);self.assertAlmostEqual(p['graze'],.5)

    def test_distribution_matches_executor_for_every_attack_roll(self):
        _,_,s=session();self.ward(s)
        counts=dict.fromkeys(['Промах','Скользящий удар','Попадание','Критическое попадание'],0)
        for initial in range(1,101):
            for conversion in [1,100]:
                s.target_healths['enemy']=1000
                with patch('training_combat.random.randint',side_effect=[initial,conversion,10]):
                    hit=s._roll_attack(name='Магия',accuracy=50,low=10,high=10,defense=0,armor=0,
                                       crafted_spell=True,weapon_attack=False,damage_type='магического')
                counts[hit['result']]+=1
                s.log.clear();s.events.clear()
        p=outcome_distribution(50,0,spell_conversions={'critToHit':50,'hitToGraze':50})
        for name,label in zip(counts,['miss','graze','hit','critical']):self.assertAlmostEqual(counts[name]/200,p[label])

    def test_preview_uses_created_spell_flag_without_mutating_states(self):
        _,d,s=session();self.ward(s);before=copy.deepcopy(s.conditions)
        a={'kind':'spell','accuracy':50,'damageMin':10,'damageMax':10,'core':'Молнии',
           'defense':'Магия','targeting':'unit','range':5,'penetration':0}
        p=s._attack_preview(a,'enemy',d)
        self.assertAlmostEqual(p['outcomes']['critical'],25)
        self.assertEqual(s.conditions,before)
        a['kind']='ability';a.update(targetTeam='enemy',attackCount=1)
        self.assertAlmostEqual(s._attack_preview(a,'enemy',d)['outcomes']['critical'],50)

    def test_actual_created_spell_and_persistent_pulse_use_shield(self):
        c,d,s=session();self.ward(s)
        with patch('training_combat.random.randint',side_effect=[80,1,10]):
            s.act({'kind':'spell','name':SPELL['name'],'targetId':'enemy'},c,d,[SPELL],2)
        self.assertEqual(s.events[0]['result'],'Скользящий удар')
        s.events=[]
        with patch('training_combat.random.randint',side_effect=[80,1,10]):
            s._pulse_area({'effect':'fire','aura':False,'center':(2,1),'radius':0,'name':'Огонь','accuracy':0,'damageMin':10,'damageMax':10})
        self.assertEqual(s.events[0]['result'],'Скользящий удар')

    def test_master_npc_upgrade_grants_and_modifies_its_shield(self):
        c,d,s=session()
        s.targets['enemy'].update(kind='npc',abilities=[resolve(WARD)],attributes=character()['attributes'],skills={})
        s.master_npc_ability('enemy','Abl_PC_Magic_EnergyShield','enemy',c,d)
        self.assertEqual(spell_conversions(s.conditions['enemy'],1),{'critToHit':50,'hitToGraze':50})
        self.assertTrue(s.action_available)


class DuelistTests(unittest.TestCase):
    def test_all_ranks_bonus_and_chance_from_source(self):
        for key,bonus,chance in zip(DUELISTS,[10,20,30],[.5,.75,1]):
            with self.subTest(key=key):
                c=actor(key);r=effects(c['talents'],[SWORD]);d=_derived(c,[SWORD]);base=_derived(character(),[SWORD])
                self.assertEqual(d['attack']['accuracy']-base['attack']['accuracy'],bonus)
                self.assertEqual(d['abilityAccuracyBonus'],bonus)
                self.assertEqual(riposte_chance(r,[SWORD],d['attack'],{}),chance)
                self.assertEqual(d['effectiveSkills'],base['effectiveSkills'])
                self.assertFalse(talent_mechanics(resolve(key))['limitation'])
                self.assertIn(f'+{chance*100:g}%',effect_text({'AffectsStat':2044,'Value':chance*100}))

    def test_ranks_replace_instead_of_adding(self):
        c=actor(*DUELISTS);r=effects(c['talents'],[SWORD]);self.assertEqual(r[2150],30);self.assertEqual(r[2044],100)
        self.assertEqual(_derived(c,[SWORD])['abilityAccuracyBonus'],30)

    def test_only_primary_one_handed_weapon_qualifies(self):
        c=actor(DUELISTS[2]);offhand={**SWORD,'equipped_slot':'Оружие I — левая рука'}
        for inventory in [[],[offhand],[{**SWORD,'category':'Двуручное оружие'}],
                          [{**SWORD,'category':'Луки'}],[{**SWORD,'category':'Щиты'}],[{**SWORD,'category':'Метательное оружие'}],
                          [SWORD,offhand],[SWORD,{**offhand,'category':'Щиты'}]]:
            with self.subTest(inventory=inventory):
                self.assertEqual(_derived(c,inventory)['abilityAccuracyBonus'],0)
                self.assertEqual(_derived(c,inventory)['attack']['accuracy'],_derived(character(),inventory)['attack']['accuracy'])

    def test_inactive_weapon_set_is_excluded(self):
        c=actor(DUELISTS[2]);c['active_weapon_set']=2
        inventory=[SWORD,{**SWORD,'equipped_slot':'Оружие II — правая рука'},
                   {**SWORD,'category':'Щиты','equipped_slot':'Оружие I — левая рука'}]
        d=_derived(c,inventory);self.assertEqual(d['abilityAccuracyBonus'],30)
        self.assertEqual(single_weapon_bonus(d['talentRuntime'],inventory,2),30)
        self.assertEqual(riposte_chance(d['talentRuntime'],inventory,d['attack'],{},2),1)
        c['active_weapon_set']=1;self.assertEqual(_derived(c,inventory)['abilityAccuracyBonus'],0)

    def test_skill_and_weapon_ability_accuracy_bonus_applies_once(self):
        c=actor(DUELISTS[2]);c['skills']['Атлетика']={'value':40};d=_derived(c,[SWORD]);base=_derived(character(),[SWORD])
        self.assertEqual(profile(resolve('Abl_PC_Thrust'),d)['accuracy'],base['attack']['accuracy']+30)
        self.assertEqual(profile(resolve('Abl_PC_Defense_ShieldSlam'),d)['accuracy'],70)

    def test_created_spell_accuracy_changes_but_not_skill(self):
        c,d,s=session(actor(DUELISTS[2]),[SWORD]);base=spell_runtime_profile(SPELL,skill=20,wits=10)
        p=spell_runtime_profile(SPELL,skill=20,wits=10,accuracy_bonus=d['abilityAccuracyBonus'])
        self.assertEqual(p['accuracy'],base['accuracy']+30)
        view=s.view(c,d,[SPELL],2);action=next(a for a in view['actions'] if a['kind']=='spell')
        self.assertEqual(action['accuracy'],30)
        self.assertNotIn('Управление молниями',c['skills'])

    def test_npc_primary_normalization_and_melee_reach(self):
        npc={'attack':{'accuracy':10,'range':2},'equipment':[{**SWORD,'slot':'PrimaryWeapon','equipped_slot':None}]}
        inv=actor_inventory(npc);r=effects(actor(DUELISTS[2])['talents'],inv)
        a=npc_attack(npc,r,inv);self.assertEqual(a['accuracy'],40);self.assertEqual(a['skill'],'Одноручное оружие')
        self.assertEqual(riposte_chance(r,inv,a,{}),1)
        self.assertEqual(npc['attack']['accuracy'],10)


class RiposteTests(unittest.TestCase):
    def test_missed_melee_strike_triggers_free_reaction(self):
        _,_,s=session();duelist(s);old=s.player_health
        action=s.action_available;movement=s.movement_remaining;initiative=copy.deepcopy(s.initiative);cooldowns=copy.deepcopy(s.cooldowns)
        hit=strike(s)
        self.assertEqual(hit['result'],'Промах');self.assertLess(s.player_health,old)
        self.assertEqual(s.target_healths['enemy'],1000);self.assertEqual(s.action_available,action)
        self.assertEqual(s.movement_remaining,movement);self.assertEqual(s.initiative,initiative);self.assertEqual(s.cooldowns,cooldowns)
        self.assertEqual(s.events[-1]['sourceId'],'enemy');self.assertEqual(s.events[-1]['targetId'],'player')
        self.assertTrue(s.events[-1]['reaction']);self.assertEqual(s.attacks,1)

    def test_probability_boundaries_for_all_ranks(self):
        for rank,chance in [(1,.5),(2,.75),(3,1)]:
            for roll,triggers in [(chance-.001,True),(chance,False)]:
                with self.subTest(rank=rank,roll=roll):
                    _,_,s=session();duelist(s,rank);before=s.player_health
                    strike(s,chance=roll);self.assertEqual(s.player_health<before,triggers)

    def test_no_reaction_on_hit_graze_crit_or_reflection(self):
        for roll,accuracy in [(40,0),(80,0),(100,10)]:
            _,_,s=session();duelist(s);before=s.player_health
            strike(s,roll,accuracy=accuracy);self.assertEqual(s.player_health,before)

    def test_no_reaction_to_spell_projectile_staff_or_graph_followup(self):
        for kwargs in [{'attack_mode':'spell'},{'attack_mode':'ranged'},{'attack_mode':'magic-ranged'},
                       {'weapon_attack':False},{'allow_reactions':False}]:
            with self.subTest(kwargs=kwargs):
                _,_,s=session();duelist(s);before=s.player_health;strike(s,**kwargs)
                self.assertEqual(s.player_health,before);self.assertEqual(len(s.events),1)

    def test_disabled_alive_range_and_los_checks(self):
        for problem in ['stun','prone','sleep','paralyze','freeze','disarm','special:frozen','dead_target','dead_attacker','distance','wall','ally']:
            with self.subTest(problem=problem):
                _,_,s=session();duelist(s)
                if problem=='dead_target':s.target_healths['enemy']=0
                elif problem=='dead_attacker':s.player_health=0
                elif problem=='distance':s.target_positions['enemy']=(5,1)
                elif problem=='wall':s.target_positions['enemy']=(3,1);s.targets['enemy']['attack']['range']=2;s.grid.sight_blocked={(2,1)}
                elif problem=='ally':s.targets['enemy']['team']='ally'
                else:s.conditions['enemy']={problem:{'until':1}}
                before=s.player_health;strike(s);self.assertEqual(s.player_health,before)

    def test_expired_disabling_state_does_not_block(self):
        _,_,s=session();duelist(s);s.conditions['enemy']={'stun':{'until':0}}
        before=s.player_health;strike(s);self.assertLess(s.player_health,before)

    def test_offhand_shield_pair_and_wrong_weapon_block_reaction(self):
        for inventory in [[SWORD,{**SWORD,'category':'Щиты','equipped_slot':'Оружие I — левая рука'}],
                          [SWORD,{**SWORD,'equipped_slot':'Оружие I — левая рука'}],
                          [{**SWORD,'category':'Двуручное оружие'}],[],
                          [{**SWORD,'equipped_slot':'Оружие I — левая рука'}]]:
            with self.subTest(inventory=inventory):
                _,_,s=session();duelist(s);s.targets['enemy']['inventory']=inventory
                before=s.player_health;strike(s);self.assertEqual(s.player_health,before)

    def test_melee_thrown_weapon_can_riposte_but_gains_no_accuracy_bonus(self):
        _,_,s=session();duelist(s);s.targets['enemy']['inventory'][0]['category']='Метательное оружие'
        rules=s._target_talent_rules('enemy');self.assertEqual(single_weapon_bonus(rules,actor_inventory(s.targets['enemy'])),0)
        before=s.player_health;strike(s);self.assertLess(s.player_health,before)
        _,_,s=session();duelist(s);s.targets['enemy']['inventory'][0]['category']='Метательное оружие';s.targets['enemy']['attack']['range']=6
        before=s.player_health;strike(s);self.assertEqual(s.player_health,before)

    def test_both_duelists_cannot_enter_reaction_loop(self):
        c,d,s=session(actor(DUELISTS[2]),[SWORD]);duelist(s)
        s.targets['enemy']['attack']['accuracy']=-100;s.runtime_derived=d
        with patch('training_combat.random.randint',return_value=1),patch('training_combat.random.random',return_value=0):
            s._roll_attack(name='Удар',accuracy=-100,low=10,high=10,defense=0,armor=0)
        self.assertEqual(len(s.events),2);self.assertEqual([e['result'] for e in s.events],['Промах','Промах'])

    def test_player_armor_and_shields_are_applied_once(self):
        c,d,s=session(inventory=[{'name':'Броня','category':'Легкая броня','armor':4,'equipped_slot':'Торс'}]);duelist(s)
        s.conditions['player']={'shield':{'kind':'masterShield','shieldRemaining':5,'until':1}}
        # Reaction critical: 15 damage, minus four armor and five shield = six.
        before=s.player_health;strike(s,counter_roll=100);self.assertEqual(s.player_health,before-6)
        self.assertEqual(s.conditions['player']['shield']['shieldRemaining'],0)

    def test_temporary_npc_strength_modifies_reaction_without_mutating_source(self):
        _,_,s=session();duelist(s)
        s.conditions['enemy']={'power':{'name':'Сила','consumable':True,'until':1,'source':{'AffectsStat':57,'Value':10,'Apply':0}}}
        before=s.player_health;strike(s);self.assertEqual(s.player_health,before-13)
        self.assertEqual(s.targets['enemy']['attack']['damageMin'],10)

    def test_other_target_state_does_not_leak_into_reaction(self):
        _,_,s=session();duelist(s)
        s.targets['other']=copy.deepcopy(s.targets['enemy']);s.target_positions['other']=(8,8);s.target_healths['other']=800
        s.conditions['other']={'stun':{'until':9}};before=copy.deepcopy(s.conditions['other'])
        strike(s);self.assertEqual(s.conditions['other'],before);self.assertEqual(s.target_healths['other'],800)

    def test_reaction_does_not_inherit_attackers_stance(self):
        _,_,s=session();duelist(s);s.active_stance='Стойка атакующего'
        with patch('training_combat.TrainingSession._weapon_talent_procs',autospec=True) as procs:
            strike(s)
        self.assertEqual(procs.call_count,1)
        self.assertEqual(procs.call_args.args[0].active_stance,'')
        # The source's stance remains untouched after the cloned reaction.
        self.assertEqual(s.active_stance,'Стойка атакующего')

    def test_missed_attack_does_not_wake_sleeping_duelist(self):
        _,_,s=session();duelist(s);s.conditions['enemy']={'sleep':{'name':'Сон','until':1}}
        before=s.player_health;strike(s)
        self.assertEqual(s.player_health,before);self.assertIn('sleep',s.conditions['enemy'])

    def test_counterkill_stops_remaining_weapon_ability_attacks(self):
        c,d,s=session(actor('Abl_PC_Agility_FlurryOfBlows'),[SWORD]);duelist(s);s.player_health=1;d['attack']['accuracy']=-100
        with patch('training_combat.random.randint',side_effect=[1,80,10]),patch('training_combat.random.random',return_value=0):
            s.act({'kind':'ability','name':'Abl_PC_Agility_FlurryOfBlows'},c,d,[],2)
        self.assertEqual(s.player_health,0);self.assertEqual(s.attacks,1);self.assertFalse(s.action_available)

    def test_master_npc_attack_can_trigger_player_riposte_with_npc_armor(self):
        c,d,s=session(actor(DUELISTS[2]),[SWORD]);key='Abl_PC_Thrust'
        s.targets['enemy'].update(kind='npc',abilities=[resolve(key)],armor=8,attributes=character()['attributes'],skills={},
                                 attack={'accuracy':-100,'damageMin':10,'damageMax':10,'range':1},equipment=[{**SWORD,'slot':'PrimaryWeapon'}])
        before=s.target_healths['enemy']
        with patch('training_combat.random.randint',side_effect=[1,70,100,10]),patch('training_combat.random.random',return_value=0):
            s.master_npc_ability('enemy',key,'player',c,d)
        self.assertEqual(s.target_healths['enemy'],before-2)
        self.assertTrue(s.action_available);self.assertEqual(s.events[-1]['sourceId'],'player');self.assertEqual(s.events[-1]['targetId'],'enemy')

    def test_master_player_riposte_uses_current_temporary_strength(self):
        c,d,s=session(actor(DUELISTS[2]),[SWORD]);key='Abl_PC_Thrust'
        s.targets['enemy'].update(kind='npc',abilities=[resolve(key)],attributes=character()['attributes'],skills={},
                                 attack={'accuracy':-100,'damageMin':10,'damageMax':10,'range':1},equipment=[{**SWORD,'slot':'PrimaryWeapon'}])
        s.conditions['player']={'power':{'name':'Сила','consumable':True,'until':1,'source':{'AffectsStat':57,'Value':10,'Apply':0}}}
        before=s.target_healths['enemy']
        with patch('training_combat.random.randint',side_effect=[1,70,100,13]),patch('training_combat.random.random',return_value=0):
            s.master_npc_ability('enemy',key,'player',c,d)
        self.assertEqual(s.target_healths['enemy'],before-13)

    def test_final_converted_miss_triggers_reaction(self):
        _,_,s=session();duelist(s);s.targets['enemy']['incomingConversions']={'hitToGraze':100,'grazeToMiss':100}
        before=s.player_health
        with patch('training_combat.random.randint',side_effect=[80,1,1,80,10]),patch('training_combat.random.random',return_value=0):
            hit=s._roll_attack(name='Удар',accuracy=0,low=10,high=10,defense=0,armor=0)
        self.assertEqual(hit['result'],'Промах');self.assertLess(s.player_health,before)


class TalentSharedBattleTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp=shared.SharedBattleTests.asyncSetUp
    asyncTearDown=shared.SharedBattleTests.asyncTearDown
    edit=shared.SharedBattleTests.edit
    start=shared.SharedBattleTests.start

    async def prepare(self,player_defends=False):
        async with self.db.connect() as conn:
            item=await conn.execute('INSERT INTO item_catalog(name,category,damage_min,damage_max) VALUES(?,?,?,?)',('Меч для проверки','Одноручное оружие',10,10))
            await conn.execute("INSERT INTO inventory(character_id,item_id,quantity,equipped_slot) VALUES(1,?,1,'Оружие I — правая рука')",(item.lastrowid,))
            if player_defends:await conn.execute('INSERT INTO talents(character_id,tree_name,name) VALUES(?,?,?)',(1,'Ловкость',resolve(DUELISTS[2])['name']))
            await conn.commit()
        row=await self.store.get(self.ident,1,99);npc=row['state']['tokens']['npc_1']
        npc.update(attack={'accuracy':-100 if player_defends else 0,'damageMin':10,'damageMax':10,'range':1},
                   equipment=[{**SWORD,'slot':'PrimaryWeapon'}],abilities=[] if player_defends else [resolve(DUELISTS[2])])
        await self.store._save(row);await self.start()
        await self.edit(operation='move',tokenId='npc_1',x=1,y=2)
        await self.edit(operation='turn',tokenId='npc_1' if player_defends else 'pc_1')
        return await self.store.get(self.ident,1,99)

    async def test_reaction_persists_health_events_but_no_extra_action_or_initiative(self):
        before=await self.prepare();order=copy.deepcopy(before['state']['initiative'])
        # Force the player's attack to miss without weakening the defender.
        await self.edit(operation='effect',tokenId='pc_1',effect='accuracy',value=-100,rounds=1)
        with patch('training_combat.random.randint',side_effect=[1,80,10]),patch('training_combat.random.random',return_value=0):
            await self.store.action(self.ident,1,cid=1,payload={'kind':'attack','targetId':'npc_1'})
        row=await self.store.get(self.ident,1,99);s=row['state']
        self.assertLess(s['tokens']['pc_1']['health'],100)
        self.assertEqual((await self.db.get_character_by_id(1))['health'],s['tokens']['pc_1']['health'])
        self.assertEqual(s['initiative'],order);self.assertEqual(s['currentId'],'pc_1');self.assertEqual(s['round'],1)
        self.assertFalse(s['personal']['pc_1']['action_available'])
        self.assertTrue(s['personal'].get('npc_1',{}).get('action_available',True))
        self.assertEqual(s['events'][-1]['sourceId'],'npc_1');self.assertEqual(s['events'][-1]['targetId'],'pc_1')
        self.assertTrue(s['events'][-1]['reaction']);self.assertNotIn('combatDerived',s['tokens']['npc_1'])

    async def test_npc_turn_triggers_player_reaction_and_preserves_players_action(self):
        await self.prepare(player_defends=True)
        with patch('training_combat.random.randint',side_effect=[1,80,10]),patch('training_combat.random.random',return_value=0):
            await self.store.action(self.ident,1,owner=99,payload={'operation':'act','kind':'attack','actorId':'npc_1','targetId':'pc_1'})
        row=await self.store.get(self.ident,1,99);s=row['state']
        self.assertLess(s['tokens']['npc_1']['health'],100);self.assertEqual(s['tokens']['pc_1']['health'],100)
        self.assertEqual(s['currentId'],'npc_1');self.assertTrue(s['personal'].get('pc_1',{}).get('action_available',True))
        self.assertFalse(s['personal']['npc_1']['action_available'])
        self.assertEqual(s['events'][-1]['sourceId'],'pc_1');self.assertEqual(s['events'][-1]['targetId'],'npc_1')

    async def test_npc_upgrade_casts_granted_shield_in_shared_battle(self):
        row=await self.store.get(self.ident,1,99);row['state']['tokens']['npc_1']['abilities']=[resolve(WARD)]
        await self.store._save(row);await self.start();await self.edit(operation='turn',tokenId='npc_1')
        view=await self.store.view(await self.store.get(self.ident,1,99),master=True,play=True)
        shield=next(a for a in view['training']['actions'] if a['name']==resolve('Abl_PC_Magic_EnergyShield')['name'])
        self.assertFalse(shield['disabledReason'])
        await self.store.action(self.ident,1,owner=99,payload={'operation':'act','kind':'ability','actorId':'npc_1','targetId':'npc_1','name':'Abl_PC_Magic_EnergyShield'})
        s=(await self.store.get(self.ident,1,99))['state']
        self.assertEqual(spell_conversions(s['conditions']['npc_1'],1),{'critToHit':50,'hitToGraze':50})
        self.assertEqual(s['tokens']['npc_1']['health'],100);self.assertFalse(s['personal']['npc_1']['action_available'])


if __name__=='__main__':unittest.main()
