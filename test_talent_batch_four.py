import copy
import json
import unittest
from unittest.mock import patch
from ability_rules import resolve,profile,owned_actions,talent_mechanics,stance_equipment
from talent_batch_four import BATCH_KEYS,watch,party_kill,on_damage,bind,share_damage,expire_summons,stance_upgrades
from test_talent_batch_one import prepared,add,armor
from test_talent_reactions import SWORD
from registration_api import _derived

def roll(lo,hi):return 80 if hi==100 else hi

def weapon(c,s,category):
    item={**SWORD,'category':category}
    s.consumable_inventory=[item]
    d=_derived(c,[item]);s.runtime_derived=d;s.talent_runtime=d['talentRuntime'];return d

class ManifestTests(unittest.TestCase):
    def test_twenty_unique(self):self.assertEqual(len(set(BATCH_KEYS)),20)
    def test_fifty_remaining_are_distinct(self):
        from talent_batch_three import BATCH_KEYS as previous
        self.assertEqual(len(set((*previous,*BATCH_KEYS))),50)
    def test_whole_audit_has_no_known_unimplemented_talents(self):
        from pathlib import Path
        report=json.loads((Path(__file__).parent/'catalog/talent_mechanics_audit.json').read_text(encoding='utf-8'))
        self.assertEqual(len(report),351);self.assertTrue(all(r['sourceKey'] and not r.get('limitation') for r in report))

def source_test(key):
    def test(self):
        source=resolve(key);self.assertEqual(source['source']['archive'],'abilities')
        mechanics=talent_mechanics(source)
        self.assertFalse(mechanics['limitation']);self.assertTrue(mechanics['effects'])
    return test
for key in BATCH_KEYS:setattr(ManifestTests,'test_source_'+key,source_test(key))

class BehaviorTests(unittest.TestCase):
    def test_switching_from_red_geyser_clears_saved_damage_immediately(self):
        c,d,s=prepared('ABL_Comp_Verse_Stance_RedGeyser','ABL_Comp_Verse_Stance_ThreeWhispers')
        s.active_stance=resolve('ABL_Comp_Verse_Stance_RedGeyser')['name'];on_damage(s,'player',40)
        s.act({'kind':'stance','name':'ABL_Comp_Verse_Stance_ThreeWhispers'},c,d,[],2)
        self.assertNotIn('saved-damage',s.conditions['player'])

    def test_suspended_and_untargetable_tokens_do_not_show_valid_melee_aim(self):
        c,d,s=prepared();s.target_positions['enemy']=(2,1)
        s.conditions['enemy']={'suspend':{'until':2,'beneficial':False}}
        action=next(a for a in s.view(c,d,[],2)['actions'] if a['kind']=='attack')
        self.assertFalse(action['aims']['2:1']['valid'])
        s.conditions['enemy']={'hidden':{'source':{'AffectsStat':17},'until':2,'beneficial':True}}
        action=next(a for a in s.view(c,d,[],2)['actions'] if a['kind']=='attack')
        self.assertFalse(action['aims']['2:1']['valid'])

    def test_health_drain_shares_damage_through_blood_bond(self):
        c,d,s=prepared();add(s,'second',(3,1));bind(s,'enemy',.5,60)
        # Bind this enemy to its own partner rather than the caster.
        s.conditions['enemy']['blood-bond']['bondPartner']='second'
        before=s.target_healths.copy()
        s._apply_ability_effects({'key':'drain','name':'Проверка','effects':[{'side':'target','AffectsStat':61,'Value':24,'ExtraValue':.4}]},'enemy','target')
        self.assertEqual(s.target_healths['enemy'],before['enemy']-12)
        self.assertEqual(s.target_healths['second'],before['second']-12)

    def test_party_kill_heals_when_ally_owns_talent_not_killer(self):
        c,d,s=prepared();add(s,'ally',(1,2),'ally',abilities=[resolve('PSV_PC_Leadership_KillingRush')])
        s.player_health=10;s.target_healths['ally']=100;s.target_healths['enemy']=0
        s._after_enemy_kill('enemy',1)
        self.assertEqual(s.player_health,10+__import__('math').ceil(s.player_health_max*.05))
        self.assertEqual(s.target_healths['ally'],150)
        s.target_healths['ally']=0;party_kill(s);self.assertEqual(s.target_healths['ally'],0)

    def test_watch_every_rank_is_a_real_position_scoped_damage_reduction(self):
        for rank,value in [(1,.95),(2,.9),(3,.85)]:
            c,d,s=prepared(*['PSV_Comp_Defender_DefendersWatch_0'+str(n) for n in range(1,rank+1)])
            add(s,'ally',(1,2),'ally');s.target_positions['enemy']=(9,1)
            watch(s);self.assertAlmostEqual(s.conditions['ally']['defenders-watch']['source']['Value'],value,places=6)
            from consumables import receive_damage
            self.assertEqual(receive_damage(s.conditions['ally'],100),round(value*100))
            s.target_positions['ally']=(7,1);watch(s);self.assertNotIn('defenders-watch',s.conditions['ally'])

    def test_three_whispers_modifies_only_two_granted_abilities_while_active(self):
        c,d,s=prepared('ABL_Comp_Verse_Stance_ThreeWhispers','ABL_Comp_Verse_Unbound','ABL_Comp_Verse_MockingIron')
        s.active_stance=resolve('ABL_Comp_Verse_Stance_ThreeWhispers')['name']
        d=_derived(c,[SWORD,*stance_equipment(s.active_stance)])
        self.assertEqual(d['defenses']['Уклонение']-_derived(c,[SWORD])['defenses']['Уклонение'],20)
        s.runtime_derived=d;d=s._combat_derived(d)
        actions={a['key']:a for a in owned_actions(c['talents'],d)}
        self.assertEqual(actions['ABL_Comp_Verse_Unbound']['range'],12)
        self.assertTrue(any(e.get('AffectsStat')==2026 and e['Value']==-20 for e in actions['ABL_Comp_Verse_MockingIron']['effects']))
        self.assertFalse(stance_upgrades(''))

    def test_seeking_sheath_adds_accuracy_only_to_listed_attacks(self):
        c,d,s=prepared('ABL_Comp_Verse_Stance_SeekingSheath','Abl_Comp_Verse_Skewer','ABL_Comp_Verse_Gravedigger','ABL_Comp_Verse_PigOnASpit')
        s.active_stance=resolve('ABL_Comp_Verse_Stance_SeekingSheath')['name']
        d=_derived(c,[SWORD,*stance_equipment(s.active_stance)])
        baseline=_derived(c,[SWORD]);self.assertEqual(d['attack']['accuracy']-baseline['attack']['accuracy'],10)
        d['activeStance']=s.active_stance
        for a in owned_actions(c['talents'],d):
            if a['key'] in {'Abl_Comp_Verse_Skewer','ABL_Comp_Verse_Gravedigger','ABL_Comp_Verse_PigOnASpit'}:
                self.assertEqual(a['accuracyBonus']-resolve(a['key'])['accuracyBonus'],10)

    def test_red_geyser_accumulates_received_damage_and_only_landed_hit_spends(self):
        c,d,s=prepared('ABL_Comp_Verse_Stance_RedGeyser')
        s.active_stance=resolve('ABL_Comp_Verse_Stance_RedGeyser')['name']
        on_damage(s,'player',40);on_damage(s,'player',20)
        self.assertEqual(s.conditions['player']['saved-damage']['value'],30)
        with patch('training_combat.random.randint',side_effect=lambda lo,hi:1):s._roll_attack(name='Промах',accuracy=0,defense=1000,armor=0,low=10,high=10,target_id='enemy')
        self.assertIn('saved-damage',s.conditions['player'])
        with patch('training_combat.random.randint',side_effect=roll):h=s._roll_attack(name='Удар',accuracy=0,defense=0,armor=0,low=10,high=10,target_id='enemy')
        self.assertEqual(h['damage'],40);self.assertNotIn('saved-damage',s.conditions['player'])

    def test_scarlet_death_triggers_once_for_npc_without_resurrection(self):
        c,d,s=prepared();s.targets['enemy'].update(abilities=[resolve('PSV_Comp_Verse_ScarletVengeance')],combatDerived=d)
        s.target_healths['enemy']=1;s.target_positions['enemy']=(2,1);s.player_health=100
        with patch('training_combat.random.randint',side_effect=roll):s._roll_attack(name='Удар',accuracy=0,defense=0,armor=0,low=10,high=10,target_id='enemy')
        self.assertEqual(s.target_healths['enemy'],0);self.assertLess(s.player_health,100)
        self.assertIn('scarlet-death-used',s.conditions['enemy'])

    def test_blood_bond_splits_without_recursion_and_breaks_with_dead_partner(self):
        c,d,s=prepared('Abl_Comp_Defender_BloodBond');add(s,'ally',(1,2),'ally')
        s.selected_target_id='ally';s.aim_point=(1,2)
        s._execute_ability(profile(resolve('Abl_Comp_Defender_BloodBond'),d),d,[SWORD])
        self.assertEqual(s.conditions['player']['blood-bond']['bondPartner'],'ally')
        hp=s.player_health;damage=share_damage(s,'ally',40)
        self.assertEqual(damage,20);self.assertEqual(s.player_health,hp-20)
        s.player_health=0;self.assertEqual(share_damage(s,'ally',40),40)

    def test_vigilant_protector_gives_two_50_point_shields_not_100_each(self):
        c,d,s=prepared('PSV_Comp_Defender_VigilantProtector');add(s,'ally',(1,2),'ally')
        s.selected_target_id='ally';s.aim_point=(1,2)
        rule=owned_actions(c['talents'],d)[0];s._execute_ability(rule,d,[SWORD])
        for target in ['player','ally']:self.assertEqual(sum(v.get('shieldRemaining',0) for v in s.conditions[target].values()),50)

    def test_suffering_heals_actual_missing_health_and_shields_caster_only(self):
        c,d,s=prepared('Abl_Comp_Defender_ShieldOfSuffering');add(s,'ally',(1,2),'ally');add(s,'far',(12,8),'ally')
        s.player_health=s.player_health_max;s.target_healths['ally']=990;s.target_healths['far']=10
        s._execute_ability(profile(resolve('Abl_Comp_Defender_ShieldOfSuffering'),d),d,[SWORD])
        self.assertEqual(s.target_healths['ally'],1000);self.assertEqual(s.target_healths['far'],10)
        self.assertEqual(s.conditions['player']['shield-of-suffering']['shieldRemaining'],10)
        self.assertNotIn('shield-of-suffering',s.conditions.get('ally',{}))

    def test_iron_legs_blocks_real_movement_push_and_prone(self):
        c,d,s=prepared('Abl_Comp_Defender_LegsOfIron');s.active_stance=resolve('Abl_Comp_Defender_LegsOfIron')['name']
        d=_derived(c,[SWORD,*stance_equipment(s.active_stance)]);baseline=_derived(c,[SWORD])
        self.assertEqual(d['defenses']['Выносливость'],round(baseline['defenses']['Выносливость']*1.4))
        self.assertEqual(s._movement_limit(),0)
        for payload in [{'kind':'move','x':1,'y':2},{'kind':'tactic','name':'Спринт'}]:
            with self.assertRaises(ValueError):s.act(payload,c,d,[],2)
        s._apply_ability_effects({'key':'test','effects':[{'control':'prone','side':'target','Duration':10,'name':'Падение'}]},'player','target')
        self.assertNotIn('prone',s.conditions['player'])
        from talent_batch_four import push_immune
        self.assertTrue(push_immune(s,'player'))

    def test_no_swap_cooldown_uses_source_minus_twenty_seconds(self):
        c,d,s=prepared('PSV_BledenMark_NoWeaponSwapCD');self.assertEqual(d['weaponSwitchRecoveryBonus'],-20)
        s.act({'kind':'weapon_set','number':2},c,d,[],2);self.assertEqual(s.recovery_seconds,0)
        c,d,s=prepared();s.act({'kind':'weapon_set','number':2},c,d,[],2);self.assertEqual(s.recovery_seconds,2)

    def test_call_requires_primary_defense_success_before_followup(self):
        for defense,damaged in [(1000,False),(0,True)]:
            c,d,s=prepared('Abl_Comp_RngMagic_TerratusCall');d=weapon(c,s,'Посохи')
            s.targets['enemy']['defenses']['Выносливость']=defense;s.aim_point=s.target_positions['enemy']
            with patch('training_combat.random.randint',side_effect=roll):s._execute_ability(profile(resolve('Abl_Comp_RngMagic_TerratusCall'),d),d,s.consumable_inventory)
            self.assertEqual(s.target_healths['enemy']<1000,damaged)

    def test_gate_pulses_both_ends_and_heals_actual_drain_not_allies(self):
        c,d,s=prepared('Abl_Comp_RngMagic_TerratusGate');d=weapon(c,s,'Посохи')
        add(s,'exit',(6,2));add(s,'ally',(6,1),'ally');s.aim_point=(6,1);s.target_positions['ally']=(6,0)
        s.player_health=10
        with patch('training_combat.random.randint',side_effect=roll):s._execute_ability(profile(resolve('Abl_Comp_RngMagic_TerratusGate'),d),d,s.consumable_inventory)
        self.assertEqual(s.player_position,(6,1));self.assertEqual(s.target_healths['enemy'],976);self.assertEqual(s.target_healths['exit'],976)
        self.assertEqual(s.target_healths['ally'],1000);self.assertEqual(s.player_health,30)

    def test_unbound_attacks_old_position_leaves_source_fury_and_moves(self):
        c,d,s=prepared('ABL_Comp_Verse_Unbound');add(s,'destination',(6,1));s.selected_target_id='destination';s.aim_point=(6,1)
        with patch('training_combat.random.randint',side_effect=roll):s._execute_ability(profile(resolve('ABL_Comp_Verse_Unbound'),d),d,[SWORD])
        summons=[(k,t) for k,t in s.targets.items() if t.get('summonedBy')]
        self.assertEqual(len(summons),1);key,token=summons[0]
        self.assertEqual(s.target_positions[key],(1,1));self.assertEqual(token['expiresRound'],2)
        self.assertNotEqual(s.player_position,(1,1));self.assertLess(s.target_healths['enemy'],1000)
        s.round_number=2;expire_summons(s);self.assertNotIn(key,s.targets)

    def test_both_arias_spawn_original_npc_spend_breath_replace_and_expire(self):
        c,d,s=prepared('Abl_Comp_Sirin_AriaOfMemories','Abl_Comp_Sirin_AriaOfNightmares');s.breath=16
        for key in ['Abl_Comp_Sirin_AriaOfMemories','Abl_Comp_Sirin_AriaOfNightmares']:
            s._execute_ability(profile(resolve(key),d),d,[SWORD])
            summons=[(k,t) for k,t in s.targets.items() if t.get('summonedBy')]
            self.assertEqual(len(summons),1);self.assertEqual(summons[0][1]['expiresRound'],7)
            self.assertIn('CRE_Sirin_EmbodiedMemory_',summons[0][1]['source']['prefab'])
            s.action_available=True
        self.assertEqual(s.breath,0)
        s.round_number=7;expire_summons(s);self.assertFalse(any(t.get('summonedBy') for t in s.targets.values()))

    def test_summon_failure_does_not_spend_breath_or_turn(self):
        c,d,s=prepared('Abl_Comp_Sirin_AriaOfMemories');s.breath=8
        s.grid.blocked.update((x,y) for x in range(0,3) for y in range(0,3) if (x,y)!=s.player_position)
        before=copy.deepcopy(s.__dict__)
        with self.assertRaises(ValueError):s.act({'kind':'ability','name':'Abl_Comp_Sirin_AriaOfMemories'},c,d,[],2)
        self.assertEqual(s.breath,8);self.assertEqual(s.cooldowns,before['cooldowns']);self.assertTrue(s.action_available)

    def test_sprinting_death_walks_real_path_and_respects_heavy_armor(self):
        for heavy in [False,True]:
            c,d,s=prepared('PSV_Comp_Verse_SprintingDeath');s.consumable_inventory=[SWORD,*([armor(1)] if heavy else [])]
            s.aim_point=(1,6);rule=owned_actions(c['talents'],d)[0]
            with patch('training_combat.random.randint',side_effect=roll):s._execute_ability(rule,d,s.consumable_inventory)
            self.assertEqual(s.player_position,(1,6));self.assertGreater(len(s.movement_path),2)
            self.assertEqual(s.target_healths['enemy']<1000,not heavy)
            self.assertLessEqual(len([e for e in s.events if e['targetId']=='enemy']),1)

    def test_bane_of_night_fourth_stanza_drains_each_elapsed_second(self):
        c,d,s=prepared('Abl_Comp_Sirin_Song_BaneOfNight');s.player_health=10
        song=resolve('Abl_Comp_Sirin_Song_BaneOfNight')
        with patch('training_combat.random.randint',side_effect=roll):s._song_phrase(song,3,d,offset=0)
        s._pulse_conditions('enemy',2,elapsed_seconds=2)
        self.assertEqual(s.target_healths['enemy'],984);self.assertEqual(s.player_health,26)

    def test_bane_every_stanza_has_real_effect_values(self):
        from song_rules import song_profile
        song=song_profile(resolve('Abl_Comp_Sirin_Song_BaneOfNight'))
        self.assertTrue(song['supported']);self.assertEqual(len(song['phraseProfiles']),4)
        self.assertEqual([next(e['Value'] for e in p['effects'] if e.get('AffectsStat') in {25,9,61}) for p in song['phraseProfiles']],[8,8,__import__('unittest').mock.ANY,8])

    def test_nightmare_hit_checks_will_and_applies_source_terror(self):
        c,d,s=prepared('PSV_Comp_Sirin_EmbodiedNightmare_Terror')
        d['effectiveSkills']['Исполнение']=200
        with patch('training_combat.random.randint',side_effect=roll):s._weapon_talent_procs('enemy','Попадание')
        self.assertIn('fear',s.conditions['enemy']);self.assertIn('confus',s.conditions['enemy'])
        self.assertEqual(s.conditions['enemy']['fear']['until'],1)

    def test_memory_pressure_is_adjacent_capped_and_ends_after_leaving(self):
        c,d,s=prepared();add(s,'memory',(3,1),'ally',memoryEngagementLimit=3)
        for i,p in enumerate([(3,0),(4,0),(4,1),(4,2)]):add(s,str(i),p)
        watch(s)
        self.assertEqual(sum('memory-taunt' in v for v in s.conditions.values()),3)
        s.target_positions['memory']=(10,8);watch(s)
        self.assertFalse(any('memory-taunt' in v for v in s.conditions.values()))

    def test_cooldown_scales_original_seconds_before_rounding(self):
        row=resolve('Abl_Comp_Lantry_QuillStrike');row.update(cooldown=2,cooldownSeconds=12)
        self.assertEqual(profile(row,{'cooldownMultiplier':.5})['cooldown'],1)

    def test_banner_buff_is_active_between_rounds_and_expires_after_three(self):
        c,d,s=prepared('Abl_PC_Leadership_Undying');s.aim_point=(1,2)
        s._execute_ability(profile(resolve('Abl_PC_Leadership_Undying'),d),d,[SWORD])
        for round_number in [2,3]:
            s._end_turn();self.assertEqual(s.round_number,round_number)
            from consumables import virtual_equipment
            items=virtual_equipment(s.conditions.get('player',{}),s.round_number)
            self.assertTrue(any(e['AffectsStat']==45 for i in items for e in i['properties']['gameData']['statusEffects']))
        s._end_turn();self.assertFalse(s.pending_graphs)
        self.assertFalse(any(st.get('source',{}).get('AffectsStat')==45 for st in s.conditions.get('player',{}).values()))

    def test_resonance_absorbs_periodic_damage_and_damage_delays_recharge(self):
        c,d,s=prepared('PSV_Comp_Sirin_ResonantField_2of3')
        s.conditions.setdefault('player',{})['bleed']={'consumable':True,'source':{'AffectsStat':25,'Value':10,'IntervalRate':1},'remainingSeconds':4,'until':1}
        before=s.player_health;s._pulse_conditions('player',2)
        self.assertEqual(s.player_health,before);self.assertNotIn('resonance-shield',s.conditions['player'])
        self.assertGreater(s.conditions['player']['resonance-delay']['readyRound'],1)

    def test_deferred_embrace_triggers_after_early_dispel(self):
        c,d,s=prepared('PSV_Comp_RngMagic_CascadingEmbrace');add(s,'neighbor',(3,1))
        rule=owned_actions(c['talents'],d)[0]
        with patch('training_combat.random.randint',side_effect=roll):s._execute_ability(rule,d,[SWORD])
        s.conditions['enemy']={}
        from talent_batch_three import advance_graphs
        with patch('training_combat.random.randint',side_effect=roll):advance_graphs(s)
        self.assertFalse(s.pending_graphs);self.assertIn('silence',s.conditions['neighbor'])

    def test_taunt_restricts_hostile_single_target_but_not_healing(self):
        c,d,s=prepared();add(s,'provoker',(3,1));s.conditions['player']={'taunt':{'sourceId':'provoker','until':1,'beneficial':False}}
        s.aim_point=s.target_positions['enemy']
        with self.assertRaisesRegex(ValueError,'Провокация'):s._require_action(8)
        s._require_action(8,hostile=False)

from test_shared_battles import SharedBattleTests
class PersistenceTests(SharedBattleTests):
    async def grant(self,cid,key):
        source=resolve(key);await self.db.add_talent(cid,{'name':source['name'],'tree':'Тест','tier':1,'description':''})

    async def force_next_round(self):
        row=await self.store.get(self.ident,1,99)
        row['state']['currentId']='pc_1';row['state']['acted']=[k for k in row['state']['tokens'] if k!='pc_1']
        await self.store._save(row)
        return await self.store.action(self.ident,1,cid=1,payload={'kind':'end_turn'})

    async def test_two_pcs_bond_persists_with_global_ids_and_npc_turn_splits_damage(self):
        await self.grant(1,'PSV_Comp_Defender_VigilantProtector')
        await self.start();await self.edit(operation='turn',tokenId='pc_1')
        row=await self.store.action(self.ident,1,cid=1,payload={'kind':'ability','name':'Abl_Comp_Defender_BloodBond','targetId':'pc_2'})
        self.assertEqual(row['state']['conditions']['pc_2']['blood-bond']['bondPartner'],'pc_1')
        self.assertEqual(row['state']['conditions']['pc_1']['blood-bond']['bondPartner'],'pc_2')
        await self.edit(operation='move',tokenId='npc_1',x=3,y=1)
        await self.edit(operation='remove_effect',tokenId='pc_1',effectId='consumable:Abl_Comp_Defender_BloodBond:2')
        row=await self.store.get(self.ident,1,99)
        for key in ['pc_1','pc_2']:
            row['state']['conditions'][key]={k:v for k,v in row['state']['conditions'][key].items() if 'shieldRemaining' not in v}
        row['state']['tokens']['npc_1']['attack'].update(accuracy=200,damageMin=20,damageMax=20)
        await self.store._save(row)
        await self.edit(operation='turn',tokenId='npc_1')
        with patch('training_combat.random.randint',side_effect=roll):
            row=await self.edit(operation='act',mode='play',actorId='npc_1',kind='attack',targetId='pc_2')
        self.assertLess(row['state']['tokens']['pc_1']['health'],100)
        self.assertLess(row['state']['tokens']['pc_2']['health'],100)
        self.assertEqual(row['state']['conditions']['pc_1']['blood-bond']['bondPartner'],'pc_2')

    async def test_summon_is_persisted_in_initiative_can_be_controlled_and_expires(self):
        await self.grant(1,'Abl_Comp_Sirin_AriaOfNightmares')
        await self.start();await self.edit(operation='turn',tokenId='pc_1')
        row=await self.store.get(self.ident,1,99);row['state']['personal']['pc_1']['breath']=8;await self.store._save(row)
        row=await self.store.action(self.ident,1,cid=1,payload={'kind':'ability','name':'Abl_Comp_Sirin_AriaOfNightmares'})
        key=next(k for k,t in row['state']['tokens'].items() if t.get('summonedBy'))
        self.assertEqual(row['state']['tokens'][key]['summonedBy'],'pc_1')
        self.assertIn(key,[i['id'] for i in row['state']['initiative']])
        await self.edit(operation='turn',tokenId=key)
        view=await self.store.view(await self.store.get(self.ident,1,99),master=True,play=True)
        self.assertTrue(view['controller']['canAct'])
        row=await self.edit(operation='act',mode='play',actorId=key,kind='move',x=3,y=2)
        self.assertEqual((row['state']['tokens'][key]['x'],row['state']['tokens'][key]['y']),(3,2))
        for _ in range(6):row=await self.force_next_round()
        self.assertNotIn(key,row['state']['tokens']);self.assertNotIn(key,[i['id'] for i in row['state']['initiative']])

    async def test_retained_breath_both_ranks_and_ttl_plus_starting_breath(self):
        for rank in [1,2]:
            await self.grant(1,'PSV_Comp_Sirin_SustainedBreath_'+str(rank)+'of2')
            await self.grant(1,'Abl_Comp_Sirin_AriaOfMemories')
            await self.grant(1,'PSV_Comp_Sirin_QuickBreath_2of2')
            if rank==1:await self.start()
            row=await self.store.get(self.ident,1,99);row['state']['personal']['pc_1']['breath']=6;row['status']='ended';await self.store._save(row)
            async with self.db.connect() as c:
                saved=await c.execute_fetchall('SELECT * FROM retained_breath WHERE character_id=1')
            self.assertEqual(saved[0]['amount'],rank)
            row=await self.store.create(1,99,self.map_id,[1,2]);self.ident=row['id'];await self.start()
            row=await self.store.get(self.ident,1,99)
            self.assertEqual(row['state']['personal']['pc_1']['breath'],rank+2)
        await self.edit(operation='finish')
        async with self.db.connect() as c:
            await c.execute('UPDATE retained_breath SET expires=0');await c.commit()
        row=await self.store.create(1,99,self.map_id,[1,2]);self.ident=row['id'];await self.start()
        self.assertEqual((await self.store.get(self.ident,1,99))['state']['personal']['pc_1']['breath'],2)

    async def test_cancelling_unstarted_lobby_does_not_overwrite_retained_breath(self):
        async with self.db.connect() as c:
            await c.execute('INSERT INTO retained_breath VALUES(1,2,9999999999)');await c.commit()
        await self.edit(operation='finish')
        async with self.db.connect() as c:
            saved=await c.execute_fetchall('SELECT amount FROM retained_breath WHERE character_id=1')
        self.assertEqual(saved[0]['amount'],2)

    async def test_bane_songs_and_owner_healing_survive_other_actor_perspective(self):
        await self.grant(1,'Abl_Comp_Sirin_Song_BaneOfNight')
        await self.edit(operation='move',tokenId='npc_1',x=3,y=1)
        await self.start()
        row=await self.store.get(self.ident,1,99);profiles=await self.store._profiles(row)
        e=self.store._engine(row,'pc_1',profiles);e.player_health=10;e.runtime_derived['effectiveSkills']['Исполнение']=200
        with patch('training_combat.random.randint',side_effect=roll):e._song_phrase(resolve('Abl_Comp_Sirin_Song_BaneOfNight'),3,e.runtime_derived)
        self.store._collect(row,'pc_1',e);await self.store._save(row)
        transfer=next(v for v in row['state']['conditions']['npc_1'].values() if v.get('transferOwner'))
        self.assertEqual(transfer['transferOwner'],'pc_1')
        row=await self.force_next_round()
        self.assertLess(row['state']['tokens']['npc_1']['health'],100)
        self.assertGreater(row['state']['tokens']['pc_1']['health'],10)

    async def test_theft_invisibility_hides_from_npc_play_not_owner_allies_or_admin(self):
        await self.grant(1,'Abl_Comp_Lantry_TheftOfMoments');await self.start()
        await self.edit(operation='turn',tokenId='pc_1')
        row=await self.store.action(self.ident,1,cid=1,payload={'kind':'ability','name':'Abl_Comp_Lantry_TheftOfMoments','targetId':'player'})
        await self.edit(operation='turn',tokenId='npc_1');row=await self.store.get(self.ident,1,99)
        view=await self.store.view(row,master=True,play=True)
        self.assertNotIn('pc_1',[t['id'] for t in view['training']['grid']['tokens']])
        self.assertNotIn('pc_1',[t['id'] for t in view['training']['targets']])
        view=await self.store.view(row,master=True)
        self.assertIn('pc_1',[t['id'] for t in view['training']['grid']['tokens']])
        view=await self.store.view(row,cid=1)
        self.assertIn('player',[t['id'] for t in view['training']['grid']['tokens']])
        view=await self.store.view(row,cid=2)
        self.assertIn('pc_1',[t['id'] for t in view['training']['grid']['tokens']])

if __name__=='__main__':unittest.main()
