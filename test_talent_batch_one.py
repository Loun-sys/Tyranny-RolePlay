"""Behavioral/source checks for each of the first 30 outstanding positions."""
import copy
import unittest
from unittest.mock import patch

from ability_rules import resolve,talent_mechanics,profile,owned_actions,proc_profiles
from combat_engagement import graph,refresh,incoming_count
from consumables import virtual_equipment,pulse
from registration_api import _derived
from talent_batch_one import BATCH_KEYS,party_xp_multiplier,skill_xp_bonuses,engagement_level
from talent_runtime import effects,hostile_duration
from talent_reactions import react_to_damage
from test_talent_reactions import session,SWORD
from test_talent_runtime import actor
import test_shared_battles as shared


def prepared(*keys):
    c,d,s=session(actor(*keys),[SWORD]);s.runtime_character=c;s.runtime_talents=c['talents'];s.runtime_derived=d
    s.talent_runtime=d['talentRuntime'];return c,d,s

def add(s,key,point,team='enemy',**kw):
    s.targets[key]={**copy.deepcopy(s.targets['enemy']),'team':team,**kw}
    s.target_positions[key]=point;s.target_healths[key]=s.targets[key]['healthMax']

def maxroll(lo,hi):return hi

def armor(category):return {'name':'Броня','equipped_slot':'Торс','armor':0,'properties':{'gameData':{'armor':{'ArmorCategory':category}}}}


class SourceManifestTests(unittest.TestCase):
    def test_exactly_thirty_unique_positions(self):self.assertEqual(len(set(BATCH_KEYS)),30)


def manifest_test(key):
    def test(self):
        row=resolve(key);self.assertIsNotNone(row);self.assertEqual(row['source']['archive'],'abilities')
        mechanics=talent_mechanics(row);self.assertFalse(mechanics['limitation']);self.assertTrue(mechanics['effects'])
    return test

for key in BATCH_KEYS:setattr(SourceManifestTests,'test_source_'+key,manifest_test(key))


class EngagementTests(unittest.TestCase):
    def test_every_capacity_talent_changes_real_control_limits(self):
        for key in BATCH_KEYS[:5]:
            with self.subTest(key=key):
                c,d,s=prepared(key);s.player_position=(5,5);s.target_positions['enemy']=(4,4)
                for i,point in enumerate([(5,4),(6,4),(4,5),(6,5),(4,6)]):add(s,str(i),point)
                expected=1+int(next(e['Value'] for n in resolve(key)['nodes'] for e in n['statuses'] if e['AffectsStat']==20))
                self.assertEqual(len(graph(s)['player']),expected)

    def test_ranks_replace_but_different_families_stack(self):
        keys=BATCH_KEYS[:5];r=effects([{'key':k} for k in keys],[SWORD])
        self.assertEqual(r[20],6) # BladeWall II + Veteran II + PackLeader (two)

    def test_control_requires_melee_los_alive_and_hostile(self):
        _,d,s=prepared();add(s,'ally',(1,2),'ally');add(s,'corpse',(0,1));s.target_healths['corpse']=0
        self.assertEqual(graph(s)['player'],['enemy'])
        d['attack'].update(skill='Луки',range=12);self.assertNotIn('player',graph(s))
        d['attack'].update(skill='Одноручное оружие',range=3);s.target_positions['enemy']=(4,1);s.grid.sight_blocked={(2,1)}
        self.assertEqual(graph(s).get('player'),[])

    def test_existing_engagement_keeps_its_capacity_slot(self):
        _,_,s=prepared();add(s,'other',(1,2));s.engagements={'player':['other']}
        self.assertEqual(graph(s)['player'],['other'])

    def test_each_entry_rank_source_chance_and_free_reaction(self):
        for rank,chance in [(1,.3),(2,.5),(3,.7)]:
            key=f'PSV_Comp_Defender_EngagementAttack_{rank}'
            with self.subTest(rank=rank):
                _,_,s=prepared();s.target_positions['enemy']=(3,1);refresh(s)
                s.targets['enemy'].update(abilities=[{'key':key}],attack={'accuracy':200,'damageMin':10,'damageMax':10,'range':1})
                self.assertEqual(engagement_level([{'key':key}]),(rank,chance))
                s.player_position=(2,1);before=s.player_health
                with patch('training_combat.random.randint',side_effect=maxroll),patch('talent_reactions.random.random',return_value=chance-.001):refresh(s,reactions=True)
                self.assertLess(s.player_health,before);self.assertTrue(s.action_available)
                self.assertEqual(s.round_number,1);self.assertTrue(any(e.get('reaction') for e in s.events))
                events=len(s.events);refresh(s,reactions=True);self.assertEqual(len(s.events),events)

    def test_entry_chance_boundary_does_not_trigger(self):
        _,_,s=prepared();s.target_positions['enemy']=(3,1);refresh(s)
        s.targets['enemy']['abilities']=[{'key':'PSV_Comp_Defender_EngagementAttack_1'}];s.player_position=(2,1)
        with patch('talent_reactions.random.random',return_value=.3):refresh(s,reactions=True)
        self.assertEqual(s.events,[])

    def test_player_can_react_to_incoming_engagement(self):
        _,d,s=prepared('PSV_Comp_Defender_EngagementAttack_3');s.target_positions['enemy']=(3,1);refresh(s)
        d['attack']['accuracy']=200;s.player_position=(2,1);before=s.target_healths['enemy']
        with patch('training_combat.random.randint',side_effect=maxroll),patch('talent_reactions.random.random',return_value=0):refresh(s,reactions=True)
        self.assertLess(s.target_healths['enemy'],before);self.assertTrue(s.action_available)

    def test_glory_counts_actual_incoming_controllers_not_friendly_neighbors(self):
        _,d,s=prepared('PSV_Comp_Defender_GloryToTheBold');s.player_position=(5,5);s.target_positions['enemy']=(4,5)
        s.targets['enemy']['selectedTargetId']='player'
        for i,p in enumerate([(5,4),(6,5),(5,6)]):add(s,'hostile'+str(i),p,attack={'range':1},selectedTargetId='player')
        add(s,'ally',(4,4),'ally');self.assertEqual(incoming_count(s,'player'),4)
        p=s._attack_parameters(accuracy=0,defense=0,armor=0,target_id='enemy');self.assertAlmostEqual(p['multiplier'],1.4)
        s.targets['hostile0']['attack']={'skill':'Луки','range':12}
        self.assertAlmostEqual(s._attack_parameters(accuracy=0,defense=0,armor=0,target_id='enemy')['multiplier'],1.3)

    def test_both_guise_ranks_disable_engagement_only_without_heavy_armor(self):
        for key in ['PSV_Comp_Sirin_GuiseOfInnocence','PSV_Comp_Sirin_GuiseOfInnocence_2of2']:
            for equipment,immune in [([],True),([armor(0)],True),([armor(1)],False),([armor(0),{**armor(1),'equipped_slot':'Ноги'}],False)]:
                with self.subTest(key=key,equipment=equipment):
                    c,d,s=prepared(key);s.runtime_derived=_derived(c,[SWORD,*equipment]);s.talent_runtime=s.runtime_derived['talentRuntime']
                    self.assertEqual('player' not in graph(s).get('enemy',[]),immune)

    def test_guise_second_rank_has_fifty_percent_critical_conversion(self):
        _,d,s=prepared();s.targets['enemy'].update(abilities=[{'key':'PSV_Comp_Sirin_GuiseOfInnocence_2of2'}],inventory=[])
        with patch('training_combat.random.randint',side_effect=[100,50,10]):hit=s._roll_attack(name='Тест',accuracy=0,low=10,high=10,defense=0,armor=0,target_id='enemy')
        self.assertEqual(hit['result'],'Попадание')
        s.targets['enemy']['inventory']=[armor(1)]
        self.assertEqual(s._attack_parameters(accuracy=0,defense=0,armor=0,target_id='enemy')['conversions']['critToHit'],0)

    def test_bestial_constitution_shortens_seconds_before_rounding(self):
        c,d,s=prepared('PSV_Comp_Beastwoman_BestialConstitution')
        changed=hostile_duration({'Duration':100,'IsHostile':1}, {},d['talentRuntime'])
        self.assertAlmostEqual(changed['Duration'],70,places=4);self.assertEqual(changed['rounds'],7)
        self.assertEqual(hostile_duration({'Duration':100},{},d['talentRuntime'])['Duration'],100)
        rule={'key':'Test','effects':[{'control':'stun','name':'Оглушение','side':'target','Duration':100}]}
        s._apply_ability_effects(rule,'player','target');self.assertEqual(s.conditions['player']['stun']['until'],7)


class StealthAndGraphTests(unittest.TestCase):
    STEALTH=('PSV_PC_Defense_PinningStrike','PSV_PC_Power_ExposeWeakness','PSV_PC_Leadership_SeizeTheInitiative',
             'PSV_PC_Magic_EnfeeblingTouch','PSV_PC_Agility_UnseenAdvantage','PSV_PC_Ranged_TerrorShot','PSV_Comp_Beastwoman_TasteOfBlood')

    def test_each_stealth_talent_requires_hidden_weapon_hit(self):
        for key in self.STEALTH:
            with self.subTest(key=key):
                c,d,s=prepared(key);s._weapon_talent_procs('enemy','Попадание');self.assertFalse(s.conditions)
                s.stealthed=True;s._weapon_talent_procs('enemy','Промах');self.assertFalse(s.conditions)
                d['attack']['accuracy']=200
                with patch('training_combat.random.randint',side_effect=maxroll):s._weapon_talent_procs('enemy','Попадание')
                self.assertTrue(any(s.conditions.values()),key)

    def test_pinning_root_lasts_three_rounds_and_survives_reveal(self):
        c,d,s=prepared(self.STEALTH[0]);d['attack']['accuracy']=200;s.stealthed=True
        with patch('training_combat.random.randint',side_effect=maxroll):s.act({'kind':'attack'},c,d,[],2)
        self.assertFalse(s.stealthed);self.assertEqual(s.conditions['enemy']['root']['until'],3)

    def test_expose_reduces_physical_armor_until_end_not_all_types(self):
        _,d,s=prepared(self.STEALTH[1]);s.stealthed=True;d['attack']['accuracy']=200
        with patch('training_combat.random.randint',side_effect=maxroll):s._weapon_talent_procs('enemy','Попадание')
        s.targets['enemy']['armor']=10
        for kind,wanted in [('рубящего',5),('дробящего',5),('колющего',5),('огненного',10)]:
            self.assertEqual(s._attack_parameters(accuracy=0,defense=0,armor=10,target_id='enemy',damage_type=kind)['armor'],wanted)
        self.assertTrue(all(e['until']>100 for e in s.conditions['enemy'].values()))

    def test_seize_applies_to_allies_in_eighteen_cells_not_enemy_or_blocked(self):
        _,d,s=prepared(self.STEALTH[2]);s.stealthed=True;d['attack']['accuracy']=200
        add(s,'ally',(3,1),'ally');add(s,'far',(11,11),'ally');s.grid.width=40;s.grid.height=40;s.target_positions['far']=(30,30)
        with patch('training_combat.random.randint',side_effect=maxroll):s._weapon_talent_procs('enemy','Попадание')
        self.assertTrue(any(e.get('source',{}).get('AffectsStat')==45 for e in s.conditions['ally'].values()))
        self.assertTrue(any(e.get('source',{}).get('AffectsStat')==45 for e in s.conditions['player'].values()))
        self.assertFalse(s.conditions.get('far'));self.assertFalse(s.conditions.get('enemy'))

    def test_enfeebling_touch_changes_actual_attributes(self):
        _,d,s=prepared(self.STEALTH[3]);s.stealthed=True;d['attack']['accuracy']=200
        with patch('training_combat.random.randint',side_effect=maxroll):s._weapon_talent_procs('enemy','Попадание')
        changed=_derived(actor(),virtual_equipment(s.conditions['enemy'],1))
        self.assertEqual(changed['effectiveAttributes']['Сила'],5)

    def test_unseen_poison_and_taste_blood_pulse_exact_seconds(self):
        for key,stat,value in [(self.STEALTH[4],25,12),(self.STEALTH[6],25,6)]:
            _,d,s=prepared(key);s.stealthed=True;d['attack']['accuracy']=200
            with patch('training_combat.random.randint',side_effect=maxroll):s._weapon_talent_procs('enemy','Попадание')
            self.assertEqual(pulse(s.conditions['enemy'],2,1000,1000),1000-value*10)
            if key==self.STEALTH[6]:self.assertEqual(pulse(s.conditions['player'],2,50,200),70)

    def test_terror_is_fear_and_reduces_will_for_two_rounds(self):
        _,d,s=prepared(self.STEALTH[5]);s.stealthed=True;d['attack']['accuracy']=200
        with patch('training_combat.random.randint',side_effect=maxroll):s._weapon_talent_procs('enemy','Попадание')
        self.assertEqual(s.conditions['enemy']['fear']['until'],2)
        self.assertEqual(_derived(actor(),virtual_equipment(s.conditions['enemy'],1))['defenses']['Воля'],14)

    def test_charged_throw_crit_hits_neighbor_excludes_primary_from_extra_aoe(self):
        key='PSV_Comp_Lantry_ChargedThrow';_,d,s=prepared(key);s.consumable_inventory=[{**SWORD,'category':'Метательное оружие'}]
        d['effectiveSkills']['Дротики']=200;add(s,'near',(3,1));add(s,'ally',(2,2),'ally');add(s,'far',(8,8))
        with patch('training_combat.random.randint',side_effect=maxroll):
            s._weapon_talent_procs('enemy','Попадание');self.assertFalse(s.events)
            s._weapon_talent_procs('enemy','Критическое попадание')
        self.assertEqual([e['targetId'] for e in s.events],['enemy','near'])
        self.assertEqual(s.target_healths['ally'],1000);self.assertEqual(s.target_healths['far'],1000)

    def test_lethal_hit_still_launches_explosion_and_own_regeneration(self):
        for key in ['PSV_Comp_Lantry_ChargedThrow','PSV_Comp_Beastwoman_TasteOfBlood']:
            with self.subTest(key=key):
                _,d,s=prepared(key);s.target_healths['enemy']=0;s.stealthed=True
                s.consumable_inventory=[{**SWORD,'category':'Метательное оружие'}] if 'Charged' in key else [SWORD]
                d['effectiveSkills']['Дротики']=200;add(s,'near',(3,1))
                with patch('training_combat.random.randint',side_effect=maxroll):s._weapon_talent_procs('enemy','Критическое попадание')
                self.assertEqual(s.target_healths['enemy'],0)
                self.assertFalse(s.conditions.get('enemy'))
                if 'Charged' in key:self.assertLess(s.target_healths['near'],1000)
                else:self.assertEqual(pulse(s.conditions['player'],2,50,200),70)

    def test_to_arms_and_sound_of_war_are_own_ally_areas_not_target_buffs(self):
        for key,radius,stat,value in [('Abl_PC_Leadership_ToArms',3,2026,10),('Abl_Comp_Defender_SoundOfWar',10,14,2)]:
            with self.subTest(key=key):
                c,d,s=prepared(key);s.targets['enemy']['defenses']=dict.fromkeys(['Парирование','Уклонение','Выносливость','Воля','Магия'],0)
                add(s,'ally',(1+radius,1),'ally');add(s,'far',(1+radius+1,3),'ally')
                rule=owned_actions(c['talents'],d)[0];s.aim_point=s.target_positions['enemy']
                with patch('training_combat.random.randint',side_effect=maxroll):s._execute_ability(rule,d,[SWORD])
                for recipient in ['player','ally']:
                    self.assertTrue(any(e.get('source',{}).get('AffectsStat')==stat and e['source']['Value']==value for e in s.conditions[recipient].values()))
                self.assertFalse(any(e.get('source',{}).get('AffectsStat')==stat and e['source']['Value']==value for e in s.conditions.get('enemy',{}).values()))
                self.assertFalse(s.conditions.get('far'))
                if key=='Abl_PC_Leadership_ToArms':
                    stats={e['source']['AffectsStat'] for e in s.conditions['ally'].values()}
                    self.assertTrue({2026,2027,2163,2164,2165}<=stats)

    def test_staggering_force_interrupts_only_after_hit(self):
        c,d,s=prepared('Abl_PC_Defense_StaggeringForce');rule=owned_actions(c['talents'],d)[0]
        with patch('training_combat.random.randint',side_effect=maxroll):s._execute_ability(rule,d,[SWORD])
        self.assertIn('interrupt',s.conditions['enemy'])
        s.conditions={};s.cooldowns={};rule['accuracy']=-500
        with patch('training_combat.random.randint',return_value=1):s._execute_ability(rule,d,[SWORD])
        self.assertNotIn('interrupt',s.conditions.get('enemy',{}))


class KillAndHealthTests(unittest.TestCase):
    def test_rampage_stacks_only_on_own_hostile_kills(self):
        c,d,s=prepared('PSV_PC_Power_Rampage');s.target_healths['enemy']=1;add(s,'second',(1,2));s.target_healths['second']=1
        d['attack']['accuracy']=200
        with patch('training_combat.random.randint',side_effect=maxroll):
            s._roll_attack(name='Тест',accuracy=200,low=20,high=20,defense=0,armor=0,target_id='enemy')
            self.assertEqual(s._attack_parameters(accuracy=200,defense=0,armor=0,target_id='second')['accuracy'],215)
            s._roll_attack(name='Тест',accuracy=200,low=20,high=20,defense=0,armor=0,target_id='second')
        states=s.conditions['player'];self.assertEqual(next(iter(states.values()))['stacks'],2)
        buffed=_derived(c,[SWORD,*virtual_equipment(states,1)]);self.assertEqual(buffed['attack']['accuracy'],_derived(c,[SWORD])['attack']['accuracy']+30)
        self.assertEqual(buffed['abilityAccuracyBonus']-d['abilityAccuracyBonus'],30)
        s.runtime_derived=buffed;add(s,'third',(0,1));self.assertEqual(s._attack_parameters(accuracy=buffed['attack']['accuracy'],defense=0,armor=0,target_id='third')['accuracy'],buffed['attack']['accuracy'])
        add(s,'ally',(0,2),'ally');s.target_healths['ally']=1
        with patch('training_combat.random.randint',side_effect=maxroll):s._roll_attack(name='Тест',accuracy=200,low=20,high=20,defense=0,armor=0,target_id='ally')
        self.assertEqual(next(iter(s.conditions['player'].values()))['stacks'],2)

    def test_surging_water_triggers_below_thirtyfive_only_once_free(self):
        c,d,s=prepared('PSV_Comp_RngMagic_SurgingWaters');d['effectiveSkills']['Управление могильным светом']=200
        s.player_health=70;react_to_damage(s,'player');self.assertFalse(s.events)
        s.player_health=69
        with patch('training_combat.random.randint',side_effect=maxroll):react_to_damage(s,'player')
        self.assertTrue(s.events);self.assertIn('root',s.conditions['enemy'])
        self.assertGreater(s.target_positions['enemy'][0],2);self.assertTrue(s.action_available);self.assertEqual(s.round_number,1)
        before=len(s.events);react_to_damage(s,'player');self.assertEqual(len(s.events),before)

    def test_surging_water_npc_reacts_to_received_damage_without_spending_action(self):
        _,d,s=prepared();s.targets['enemy'].update(abilities=[{'key':'PSV_Comp_RngMagic_SurgingWaters'}],skills={'Управление могильным светом':200})
        s.target_healths['enemy']=340
        with patch('training_combat.random.randint',side_effect=maxroll):s._roll_attack(name='Тест',accuracy=200,low=10,high=10,defense=0,armor=0,target_id='enemy')
        self.assertIn('root',s.conditions['player']);self.assertLess(s.player_health,200)
        self.assertIn('talent-used:PSV_Comp_RngMagic_SurgingWaters',s.conditions['enemy'])

    def test_player_surging_water_reacts_inside_npc_attack_executor(self):
        from talent_reactions import free_attack
        c,d,s=prepared('PSV_Comp_RngMagic_SurgingWaters');s.player_health=70
        d['effectiveSkills']['Управление могильным светом']=200
        s.targets['enemy']['attack']={'accuracy':200,'damageMin':10,'damageMax':10,'range':1}
        with patch('training_combat.random.randint',side_effect=maxroll):free_attack(s,'enemy','player','Тест НПС')
        self.assertIn('talent-used:PSV_Comp_RngMagic_SurgingWaters',s.conditions['player'])
        self.assertIn('root',s.conditions['enemy']);self.assertTrue(s.action_available)


class ExperienceTests(shared.SharedBattleTests):
    async def grant(self,cid,key):
        row=resolve(key)
        await self.db.add_talent(cid,{'name':row['name'],'tree':'Тест','tier':1,'description':''})

    async def test_each_training_aura_uses_source_skills(self):
        keys=['PSV_Comp_Lantry_LearnedInstructor_01','PSV_Comp_Beastwoman_WildInstinct','PSV_Comp_Verse_BattleMind_01','PSV_Comp_Defender_TrainingGround','PSV_Comp_Sirin_Inspiration']
        for key in keys:
            with self.subTest(key=key):
                bonuses=skill_xp_bonuses([{'key':key}]);self.assertTrue(bonuses)
                for skill in bonuses:self.assertAlmostEqual(party_xp_multiplier([{'talents':[{'key':key}]}],skill),1.2)
                self.assertEqual(party_xp_multiplier([{'talents':[{'key':key}]}],'Неподходящий навык'),1)

    async def test_actual_party_award_preserves_fraction_and_spell_slot(self):
        await self.grant(2,'PSV_Comp_Lantry_LearnedInstructor_01');await self.start()
        limits=await self.db.equipment_limits(1);self.assertEqual(limits['spellSlots'],5)
        for _ in range(5):await self.db.add_skill_experience(1,'Знания',1)
        c=await self.db.get_character_by_id(1);self.assertEqual(c['skills']['Знания']['experience'],6)
        self.assertEqual(await self.db.add_skill_experience(1,'Атлетика',10),10)
        self.assertEqual(await self.db.add_skill_experience(3,'Знания',10),10)

    async def test_same_aura_from_two_allies_adds_not_multiplies(self):
        await self.grant(1,'PSV_Comp_Lantry_LearnedInstructor_01');await self.grant(2,'PSV_Comp_Lantry_LearnedInstructor_01');await self.start()
        self.assertEqual(await self.db.add_skill_experience(1,'Знания',10),14)
        self.assertEqual((await self.db.equipment_limits(1))['spellSlots'],6)

    async def test_no_global_or_lobby_party_bonus(self):
        await self.grant(2,'PSV_Comp_Lantry_LearnedInstructor_01')
        self.assertEqual(await self.db.add_skill_experience(1,'Знания',10),10)
        self.assertEqual((await self.db.equipment_limits(1))['spellSlots'],4)

    async def test_enemy_npc_aura_is_not_shared(self):
        await self.start();row=await self.store.get(self.ident,1,99)
        row['state']['tokens']['npc_1']['abilities']=[{'key':'PSV_Comp_Defender_TrainingGround'}];await self.store._save(row)
        self.assertEqual(await self.db.add_skill_experience(1,'Атлетика',10),10)
        row['state']['tokens']['npc_1']['team']='party';await self.store._save(row)
        self.assertEqual(await self.db.add_skill_experience(1,'Атлетика',10),22)

    async def test_live_npc_entry_reaction_persists_without_spending_npc_action(self):
        await self.start();row=await self.store.get(self.ident,1,99)
        s=row['state'];s['currentId']='pc_1';s['tokens']['pc_2'].update(x=8,y=7)
        s['tokens']['npc_1'].update(x=3,y=1,abilities=[{'key':'PSV_Comp_Defender_EngagementAttack_3'}],
                                  attack={'accuracy':200,'damageMin':10,'damageMax':10,'range':1})
        await self.store._save(row)
        with patch('training_combat.random.randint',side_effect=maxroll),patch('talent_reactions.random.random',return_value=0):
            row=await self.store.action(self.ident,1,cid=1,payload={'operation':'act','kind':'move','x':2,'y':1})
        self.assertLess(row['state']['tokens']['pc_1']['health'],100)
        self.assertTrue(row['state']['personal']['pc_1']['action_available'])
        self.assertTrue(row['state']['personal'].get('npc_1',{}).get('action_available',True))
        self.assertEqual(row['state']['currentId'],'pc_1')
        self.assertTrue(any(e.get('reaction') and e['sourceId']=='npc_1' and e['targetId']=='pc_1' for e in row['state']['events']))
        self.assertIn('pc_1',row['state']['engagements']['npc_1'])


if __name__=='__main__':unittest.main()
