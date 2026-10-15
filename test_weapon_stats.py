"""Source precision, quality upgrades, API readouts and real typed weapon hits."""
import copy,json,unittest
from unittest.mock import patch
from crafting import normalize_quality,quality_info,scale_row
from item_texts import catalog_texts
from item_effects import game_data,DAMAGE_TYPES
from weapon_stats import source_attack,readout
from registration_api import _clean_inventory,_derived
from test_talent_runtime import actor
from test_combat_tactics import TacticalCombatTests

class WeaponStatsTests(unittest.TestCase):
    def item(self,name):return copy.deepcopy(catalog_texts()[1][name.casefold()])

    def test_all_source_weapons_preserve_types_ranges_and_quality_recovery(self):
        weapons=[i for i in catalog_texts()[0].values() if readout(i)]
        self.assertEqual(len(weapons),317)  # Includes the independently audited recruitment prefabs.
        for i in weapons:
            with self.subTest(item=i['name']):
                g=game_data(i);a,melee=source_attack(g['prefab']);s=readout(i)
                q=quality_info(i);row=scale_row(q,q['level']) if q else {}
                prefix='Weapon_MeleeAttack_AttackBase_' if melee else 'AttackBase_'
                self.assertAlmostEqual(i['recovery'],row.get(prefix+'PersonalCooldownModifier',a['PersonalCooldownModifier'])/10,places=4)
                for field in ['Type','BestOfType']:
                    self.assertEqual(g['attack']['DamageData'][field],a['DamageData'][field])
                self.assertEqual(s['rangeMeters'],a.get('OverrideAttackDistance') or a['AttackDistance'])
                self.assertTrue(s['damageTypes'])
                self.assertEqual(g['weaponStatsVersion'],1)
        self.assertEqual(sum(i['recovery']==0 for i in weapons),23)

    def test_mismatched_weapon_types_no_longer_share_generic_range_or_recovery(self):
        sword=readout(self.item('Железный меч'));knife=readout(self.item('Бронзовый кинжал'))
        staff=readout(self.item('Посох Каирна'))
        self.assertEqual((sword['accuracyBonus'],sword['penetration'],sword['recoverySeconds']),(0,3,1.7))
        self.assertEqual(sword['damageTypes'],['Рубящий','Колющий'])
        self.assertEqual((knife['accuracyBonus'],knife['penetration'],knife['recoverySeconds']),(10,0,0))
        self.assertEqual((staff['rangeCells'],staff['recoverySeconds'],staff['defense']),(8,5.6,'Уклонение'))

    def test_javelins_use_projectile_but_throwable_daggers_remain_melee(self):
        javelins=[i for i in catalog_texts()[0].values() if readout(i) and 'javelin' in game_data(i)['prefab'].lower()]
        self.assertTrue(javelins)
        for i in javelins:
            self.assertEqual(i['category'],'Метательное оружие')
            self.assertEqual(readout(i)['rangeCells'],8)
            self.assertEqual(readout(i)['defense'],'Уклонение')
        self.assertEqual(readout(self.item('Бронзовый кинжал'))['rangeCells'],1)

    def test_upgrade_retains_source_damage_precision_and_scales_cooldown(self):
        item=self.item('Железный меч')
        self.assertEqual(game_data(item)['attack']['DamageData']['Maximum'],10.5)
        for level in range(1,6):
            upgrade=normalize_quality(item,level);q=quality_info(upgrade);row=scale_row(q,level)
            self.assertAlmostEqual(upgrade['recovery'],row['AttackBase_PersonalCooldownModifier']/10,places=4)
            self.assertEqual(game_data(upgrade)['attack']['DamageData']['Maximum'],row['AttackBase_DamageData_DamageMax'])

    def test_api_and_equipment_both_use_the_weapon_source(self):
        for name in ['Железный меч','Посох Каирна','Лук Вендриенов']:
            i=self.item(name);i['equipped_slot']='Оружие I — правая рука';i['inventory_id']=1
            s=readout(i);d=_derived(actor(),[i])
            self.assertEqual(d['attack']['range'],s['rangeCells'])
            self.assertEqual(d['attack']['damageTypes'],s['damageTypes'])
            self.assertEqual(d['attack']['defense'],s['defense'])
            i['properties']=json.dumps(i['properties'])
            self.assertEqual(_clean_inventory([i])[0]['weaponStats'],s)

    def test_json_non_weapon_without_quality_does_not_break_normalization(self):
        i={'name':'Тест','category':'Разное','properties':'{}'}
        self.assertEqual(normalize_quality(i),i)

    def test_best_damage_type_changes_with_target_armor_and_executes(self):
        c,d,s=TacticalCombatTests().battle()
        d['attack'].update(damageTypes=['Рубящий','Колющий'],damageMin=10,damageMax=10)
        s.targets['enemy']['armorByType']={'Рубящий':20,'Колющий':0,'Дробящий':20}
        self.assertEqual(s._weapon_damage_type(d['attack'],'enemy'),'колющий')
        preview=s._attack_preview({'kind':'attack'},'enemy',d)
        with patch('training_combat.random.randint',side_effect=lambda lo,hi:75 if hi==100 else hi):
            result=s.act({'kind':'attack'},c,d,[],2)
        self.assertEqual(result['damage'],10)
        self.assertTrue(preview['damageMin']<=result['damage']<=preview['damageMax'])
        s.targets['enemy']['armorByType']['Колющий']=30
        self.assertEqual(s._weapon_damage_type(d['attack'],'enemy'),'рубящий')

    def test_random_damage_preview_includes_every_possible_typed_armor(self):
        c,d,s=TacticalCombatTests().battle()
        d['attack'].update(damageTypes=list(DAMAGE_TYPES.values()),randomDamage=True,damageMin=10,damageMax=10)
        s.targets['enemy']['armorByType']={name:0 if name=='Ледяной' else 20 for name in DAMAGE_TYPES.values()}
        p=s._attack_preview({'kind':'attack'},'enemy',d)
        self.assertEqual(p['damageMin'],1);self.assertGreaterEqual(p['damageMax'],10)
        with patch('training_combat.random.choice',return_value='Ледяной'):
            self.assertEqual(s._weapon_damage_type(d['attack'],'enemy',True),'ледяной')

    def test_minimum_weapon_range_rejected_in_preview_and_execution(self):
        c,d,s=TacticalCombatTests().battle();d['attack'].update(range=10,minRange=2)
        action=next(a for a in s.view(c,d,[],2)['actions'] if a['kind']=='attack')
        self.assertFalse(action['aims']['2:1']['valid'])
        with self.assertRaisesRegex(ValueError,'слишком близко'):s.act({'kind':'attack'},c,d,[],2)
        self.assertTrue(s.action_available);self.assertEqual(s.target_healths['enemy'],1000)

if __name__=='__main__':unittest.main()
