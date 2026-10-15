"""Equipment must change real attacks, not only the character sheet."""
import copy
import unittest
from unittest.mock import patch

from combat_math import outcome_distribution
from item_effects import armor_by_type, equip_bonuses
from item_texts import catalog_texts
from registration_api import _derived
from talent_reactions import free_attack
from test_consumables import character
from test_talent_reactions import session


def armor(prefab, slot=None):
    item = copy.deepcopy(catalog_texts()[0][prefab])
    item['equipped_slot'] = slot or item['slot']
    return item


class ArmorRuntimeTests(unittest.TestCase):
    def test_every_armor_typed_absorption_and_deflection_reach_derived(self):
        checked = 0
        for item in catalog_texts()[0].values():
            if item['category'] != 'Броня':continue
            checked += 1
            d = _derived(character(), [{**copy.deepcopy(item), 'equipped_slot': item['slot']}])
            self.assertEqual(d['armorByType'], armor_by_type(item), item['name'])
            for key in ['critToHit','hitToGraze','grazeToMiss']:
                self.assertGreaterEqual(d['incomingConversions'][key], d['deflection'], item['name'])
        self.assertEqual(checked, 402)

    def test_cloth_outfit_protects_and_unequipping_removes_bonus(self):
        gear = [armor(p) for p in ['Cloth_Armor_Lantry','Cloth_GLOVE_Lantry','Cloth_BOOTS_Lantry']]
        d = _derived(character(), gear)
        self.assertEqual(d['armor'], 0)
        self.assertEqual(d['deflection'], 3)
        self.assertEqual((d['attack']['damageMin'],d['attack']['damageMax']),(8,11))
        self.assertEqual(d['incomingConversions'], dict.fromkeys(['critToHit','hitToGraze','grazeToMiss'],3))
        for item in gear:item['equipped_slot'] = ''
        self.assertEqual(_derived(character(), gear)['incomingConversions'],dict.fromkeys(d['incomingConversions'],0))

    def test_all_magic_skill_modifiers_no_longer_disappear(self):
        c = character()
        c['skills']['Знания']={'value':25}
        d = _derived(c,[armor('Cloth_Armor_Rare')])
        self.assertEqual(d['effectiveSkills']['Управление огнём'],23)
        self.assertEqual(d['effectiveSkills']['Знания'],25)
        self.assertEqual(d['effectiveSkills']['Безоружный бой'],20)

    def test_deflection_changes_real_attack_but_downgrades_only_once(self):
        c,d,s = session()
        s.targets['enemy']['incomingConversions'] = dict.fromkeys(['critToHit','hitToGraze','grazeToMiss'],100)
        with patch('training_combat.random.randint', side_effect=lambda lo,hi:hi):
            hit=s._roll_attack(name='Удар',accuracy=100,low=10,high=10,defense=0,armor=0,target_id='enemy')
        self.assertEqual(hit['result'],'Попадание')
        self.assertEqual(hit['damage'],10)
        probabilities=outcome_distribution(100,0,conversions=s.targets['enemy']['incomingConversions'])
        self.assertAlmostEqual(probabilities['hit'],1)
        self.assertAlmostEqual(probabilities['miss'],0)

    def test_boot_bonus_is_used_on_real_opportunity_not_normal_attack(self):
        boots=armor('Cloth_BOOTS_Lantry')
        c,d,s=session(inventory=[boots])
        bonus=equip_bonuses(boots)['Защита от атак по возможности']
        with patch('training_combat.TrainingSession._roll_attack',return_value={'result':'Промах','damage':0,'line':''}) as roll, \
             patch('training_combat.TrainingSession._weapon_talent_procs'):
            # _roll_attack normally appends the event itself.
            s.events=[{'sourceId':'enemy','targetId':'player'}]
            def rolled(**kwargs):
                return {'result':'Промах','damage':0,'line':''}
            roll.side_effect=rolled
            free_attack(s,'enemy','player','Отход',opportunity=True)
            opportunity=roll.call_args.kwargs['defense']
            free_attack(s,'enemy','player','Обычный удар')
            normal=roll.call_args.kwargs['defense']
        self.assertEqual(opportunity-normal, bonus)

    def test_equipment_damage_reduction_is_applied_once_in_shared_roll(self):
        c,d,s=session()
        s.targets['enemy']['incomingDamageMultiplier']=.5
        p=s._attack_parameters(accuracy=0,defense=0,armor=2,target_id='enemy')
        p['armor']=2
        self.assertEqual(s._attack_damage(22,1,p,0,'enemy')[0],10)
        s.conditions['enemy']={'potion':{'source':{'AffectsStat':188,'Value':.5},'until':2,'consumable':True}}
        self.assertEqual(s._attack_damage(22,1,p,0,'enemy')[0],5)

    def test_real_immunity_is_applied_and_removed_with_gear(self):
        gloves=armor('UNIQUE_Iron_GLOVE_LockedIronGauntlets')
        c,d,s=session(inventory=[gloves])
        rule={'key':'test','effects':[{'control':'disarm','affliction':'Aff_Disarm','side':'target','Duration':10,'name':'Разоружение'}]}
        s._apply_ability_effects(rule,'player','target')
        self.assertNotIn('disarm',s.conditions['player'])
        s.consumable_inventory=[]
        s._apply_ability_effects(rule,'player','target')
        self.assertIn('disarm',s.conditions['player'])

    def test_night_damage_and_low_health_critical_use_same_preview_parameters(self):
        gear=[armor('UNIQUE_Leather_HELM_NightwalkerCoif'),armor('Leather_BOOTS_Rare')]
        c,d,s=session(inventory=gear)
        s.custom_map={'timeOfDay':'night'};s.target_healths['enemy']=300
        p=s._attack_parameters(accuracy=0,defense=0,armor=0,target_id='enemy')
        self.assertAlmostEqual(p['multiplier'],1.2)
        self.assertEqual(p['equipmentCriticalChance'],25)
        s.custom_map['timeOfDay']='day';s.target_healths['enemy']=350
        p=s._attack_parameters(accuracy=0,defense=0,armor=0,target_id='enemy')
        self.assertEqual(p['multiplier'],1)
        self.assertEqual(p['equipmentCriticalChance'],0)

    def test_critical_damage_bonus_reaches_attack_context(self):
        gear=armor('Leather_Armor_Rare')
        c,d,s=session(inventory=[gear])
        p=s._attack_parameters(accuracy=0,defense=0,armor=0,target_id='enemy')
        self.assertAlmostEqual(p['criticalMultiplier'],1.65)

    def test_item_bonus_and_highest_talent_rank_do_not_double_count(self):
        from test_talent_runtime import actor
        from item_effects import unarmed_damage
        c=actor('PSV_Comp_Beastwoman_NaturalWeaponry_1of5','PSV_Comp_Beastwoman_NaturalWeaponry_4of5')
        gear=armor('UNIQUE_Leather_GLOVE_RockbiterVambraces')
        d=_derived(c,[gear]);low,high=unarmed_damage(gear)
        bonus=equip_bonuses(gear)['Добавочный безоружный урон']
        self.assertEqual(d['attack']['damageMin'],low+bonus+13)
        self.assertEqual(d['attack']['damageMax'],high+bonus+13)

    def test_reflection_uses_new_victims_damage_reduction(self):
        c,d,s=session()
        s.targets['enemy'].update(incomingDamageMultiplier=.5,talentRuntime={2138:100})
        before=s.player_health
        with patch('training_combat.random.randint',side_effect=lambda lo,hi:hi),patch('training_combat.random.random',return_value=0):
            s._roll_attack(name='Стрела',accuracy=0,low=20,high=20,defense=0,armor=0,target_id='enemy',attack_mode='ranged')
        self.assertEqual(before-s.player_health,20)


class ArmorSharedBattleTests(unittest.IsolatedAsyncioTestCase):
    from test_shared_battles import SharedBattleTests as _Setup
    asyncSetUp=_Setup.asyncSetUp
    asyncTearDown=_Setup.asyncTearDown

    async def test_shared_engine_receives_real_armor_and_updates_after_unequip(self):
        gear=armor('Cloth_BOOTS_Lantry')
        await self.db.upsert_catalog([gear])
        async with self.db.connect() as conn:
            item=(await conn.execute_fetchall('SELECT id FROM item_catalog WHERE name=?',(gear['name'],)))[0]
            await conn.execute("INSERT INTO inventory(character_id,item_id,quantity,equipped_slot) VALUES(2,?,1,'Ноги')",(item['id'],))
            await conn.commit()
        profiles=await self.store._profiles(self.row)
        engine=self.store._engine(self.row,'pc_1',profiles)
        target=engine.targets['pc_2']
        self.assertEqual(target['incomingConversions'],dict.fromkeys(['critToHit','hitToGraze','grazeToMiss'],1))
        self.assertEqual(target['disengagementDefenseBonus'],1)
        self.assertEqual(target['armorByType'],armor_by_type(gear))
        async with self.db.connect() as conn:
            await conn.execute('UPDATE inventory SET equipped_slot=NULL WHERE character_id=2')
            await conn.commit()
        profiles=await self.store._profiles(self.row)
        target=self.store._engine(self.row,'pc_1',profiles).targets['pc_2']
        self.assertEqual(target['incomingConversions'],dict.fromkeys(['critToHit','hitToGraze','grazeToMiss'],0))
        self.assertEqual(target['disengagementDefenseBonus'],0)


if __name__ == '__main__':unittest.main()
