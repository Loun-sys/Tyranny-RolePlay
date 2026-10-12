"""Item recovery increases; fractional equipment totals never force +1 round."""
import copy
import json
from decimal import Decimal, ROUND_HALF_UP
import unittest
from pathlib import Path
from unittest.mock import patch

from ability_rules import owned_actions, profile, resolve
from crafting import normalize_quality
from equipment_recovery import item_recovery, recovery_rounds, with_recovery
from item_texts import catalog_texts
from registration_api import _clean_inventory, _derived
from sigil_data import spell_runtime_profile
from talent_reactions import npc_derived
from test_talent_runtime import actor
import test_combat_tactics as fixtures


def gear(recovery=.8, slot='Торс'):
    return {'name':'Тестовая экипировка','category':'Броня','recovery':recovery,
            'equipped_slot':slot,'properties':{}}


class EquipmentRecoveryTests(unittest.TestCase):
    def battle(self, *keys, recovery=.8):
        _, _, session=fixtures.TacticalCombatTests().battle()
        character=actor(*keys)
        character.update(health=200,health_max=200)
        derived=_derived(character,[gear(recovery)])
        session.view(character,derived,[],2)
        return character,derived,session

    def test_increase_current_item_values_and_keep_fractional_sum(self):
        d=_derived(actor(),[gear(.2,'Голова'),gear(.2,'Торс')])
        self.assertEqual(d['equipmentRecoveryRaw'],.9)
        self.assertEqual(d['equipmentRecovery'],.9)
        self.assertEqual(d['attack']['recovery'],.9)
        self.assertEqual(_derived(actor(),[gear(.8)])['equipmentRecovery'],1.8)
        self.assertEqual(_derived(actor(),[])['equipmentRecovery'],0)
        self.assertEqual(recovery_rounds(1.0000000000000002),1)
        self.assertEqual(recovery_rounds(.14),.14)
        self.assertEqual(recovery_rounds(-.2),0)
        gloves=copy.deepcopy(catalog_texts()[1]['железные рукавицы'])
        self.assertEqual(gloves['recovery']*1.5,.09)  # Previous site value.
        self.assertEqual(item_recovery(gloves),.14)
        gloves['equipped_slot']='Руки'
        self.assertEqual(_derived(actor(),[gloves])['equipmentRecovery'],.14)

    def test_only_active_equipment_contributes(self):
        items=[gear(.2,'Торс'),gear(.2,'Оружие I — правая рука')]
        items.extend(gear(100,s) for s in [None,'Быстрый предмет 1','Мастерская','Оружие II — правая рука'])
        d=_derived(actor(),items)
        self.assertEqual(d['equipmentRecovery'],.9)
        c=actor();c['active_weapon_set']=2
        self.assertEqual(_derived(c,items)['equipmentRecovery'],225.45)

    def test_modifiers_and_conditional_talents_keep_fractional_recovery(self):
        item=gear(.8);item['properties']['Восстановление']='-50%'
        self.assertEqual(_derived(actor(),[item])['equipmentRecovery'],.9)
        c,d,s=self.battle('PSV_Comp_RngMagic_ClearMind',recovery=.75)
        self.assertEqual(d['equipmentRecovery'],1.69)
        s.runtime_talents=c['talents']
        final=s._combat_derived(d)
        self.assertAlmostEqual(final['equipmentRecoveryRaw'],1.352)
        self.assertEqual(final['equipmentRecovery'],1.352)
        self.assertEqual(s._combat_derived(d),final)  # No cumulative scaling.

    def test_every_imported_item_displays_the_increase_without_mutating_source(self):
        rows=[i for i in catalog_texts()[0].values() if i.get('recovery',0)>0]
        self.assertGreaterEqual(len(rows),600)
        cleaned=_clean_inventory(rows)
        for original,clean in zip(rows,cleaned):
            with self.subTest(item=original['name']):
                self.assertEqual(clean['recovery'],original['recovery'])
                expected=float((Decimal(str(original['recovery']))*Decimal('2.25')).quantize(Decimal('.01'),rounding=ROUND_HALF_UP))
                self.assertEqual(clean['recoveryAdapted'],expected)
                if clean.get('weaponStats'):
                    self.assertAlmostEqual(clean['weaponStats']['recoverySeconds'],expected*10,places=6)

    def test_repeated_api_and_quality_normalization_does_not_compound_increase(self):
        source=copy.deepcopy(catalog_texts()[1]['железный меч'])
        upgraded=normalize_quality(source,2)
        once=_clean_inventory([upgraded])[0]
        twice=_clean_inventory([normalize_quality(once,2)])[0]
        self.assertEqual(once['recovery'],twice['recovery'])
        self.assertEqual(once['recoveryAdapted'],twice['recoveryAdapted'])
        self.assertEqual(once['weaponStats'],twice['weaponStats'])

    def test_ability_preview_execution_and_next_turn_match(self):
        c,d,s=self.battle('Abl_PC_Thrust')
        base=profile(resolve('Abl_PC_Thrust'),_derived(c,[]))['cooldown']
        preview=next(a for a in s.view(c,d,[],2)['actions'] if a['kind']=='ability')
        self.assertEqual(preview['cooldown'],base+1.8)
        self.assertIn(f'база {base} + восстановление 1,8',preview['details'])
        with patch('training_combat.random.randint',side_effect=lambda lo,hi:hi):
            s.act({'kind':'ability','name':'Abl_PC_Thrust'},c,d,[],2)
        self.assertEqual(s.cooldowns['ability:Abl_PC_Thrust'],s.round_number+preview['cooldown']+1)
        self.assertFalse(s.action_available)  # Ability still spends its ordinary action.
        s._end_turn()
        self.assertTrue(s.action_available)
        self.assertGreater(s.remaining('ability:Abl_PC_Thrust'),0)
        with patch('training_combat.random.randint',side_effect=lambda lo,hi:hi):
            s.act({'kind':'attack'},c,d,[],2)  # No recovery action lock.

    def test_old_saved_busy_timer_does_not_block_action(self):
        c,d,s=self.battle()
        s.recovery_seconds=30
        with patch('training_combat.random.randint',side_effect=lambda lo,hi:hi):
            s.act({'kind':'attack'},c,d,[],2)
        self.assertFalse(s.action_available)
        s._end_turn()
        self.assertEqual(s.recovery_seconds,0)

    def test_recovery_reduction_and_profiles_are_idempotent(self):
        d=_derived(actor(),[gear(.75)])  # 1.69 fractional rounds, -0.2 -> 1.49.
        action={'cooldown':3,'details':'Перезарядка: 3 раундов','recoveryAdjustmentSeconds':-2}
        first=with_recovery(action,d)
        self.assertEqual(first['cooldown'],4.49)
        self.assertIn('база 3 + восстановление 1,49',first['details'])
        self.assertEqual(with_recovery(first,d),first)
        self.assertEqual(with_recovery(first,_derived(actor(),[]))['cooldown'],3)
        for exception in ['passive','modal','song','oncePerBattle']:
            self.assertEqual(with_recovery({**action,exception:True},d)['cooldown'],3)

    def test_graph_ability_adds_recovery_only_once(self):
        c,d,s=self.battle('Abl_Comp_Lantry_TheftOfMoments')
        base=owned_actions(c['talents'],_derived(c,[]))[0]
        rule=owned_actions(c['talents'],d)[0]
        self.assertEqual(rule['cooldown'],base['cooldown']+1.8)
        self.assertEqual(with_recovery(rule,d)['cooldown'],rule['cooldown'])

    def test_spell_modifiers_reduce_base_not_equipment_surcharge(self):
        spell={'name':'Молния','core':'Молния','expression':'Направленная сила','accents':[],'enhancements':[]}
        base=spell_runtime_profile(spell,skill=20,wits=10,cooldown_multiplier=.5)
        adapted=spell_runtime_profile(spell,skill=20,wits=10,cooldown_multiplier=.5,equipment_recovery=1.2)
        self.assertEqual(adapted['cooldown'],base['cooldown']+1.2)
        c,d,s=self.battle()
        preview=next(a for a in s.view(c,d,[spell],2)['actions'] if a['kind']=='spell')
        with patch('training_combat.random.randint',side_effect=lambda lo,hi:hi):
            s.act({'kind':'spell','name':'Молния'},c,d,[spell],2)
        self.assertEqual(s.cooldowns['spell:Молния'],s.round_number+preview['cooldown']+1)

    def test_consumable_cooldown_does_not_change_self_or_adjacent_action_cost(self):
        source=copy.deepcopy(catalog_texts()[0]['IT_CONS_HealingPotionCommon'])
        source.update(inventory_id=7,quantity=3,image_url='')
        for recipient,free in [('player',True),('enemy',False)]:
            c,d,s=self.battle()
            s.consumable_inventory=[source]
            preview=next(a for a in s.view(c,d,[],2)['actions'] if a['kind']=='item')
            s.act({'kind':'item','name':'7','targetId':recipient},c,d,[],2)
            self.assertEqual(s.action_available,free)
            self.assertEqual(s.cooldowns['item:7'],s.round_number+preview['cooldown']+1)
            self.assertEqual(preview['equipmentRecovery'],1.8)

    def test_weapon_switch_extends_cooldown_without_action_lock(self):
        c,d,s=self.battle('Abl_PC_Thrust',recovery=0)
        s.act({'kind':'weapon_set','number':2},c,d,[],2)
        self.assertTrue(s.action_available)
        self.assertEqual(s.weapon_switch_recovery_seconds,2)
        preview=next(a for a in s.view(c,d,[],2)['actions'] if a['kind']=='ability')
        self.assertEqual(preview['equipmentRecovery'],.2)
        s.act({'kind':'weapon_set','number':2},c,d,[],2)
        self.assertEqual(s.weapon_switch_recovery_seconds,2)
        s._end_turn()
        self.assertEqual(s.weapon_switch_recovery_seconds,0)

    def test_npc_uses_same_raw_sum_and_source_prefab_recovery(self):
        c=actor('Abl_PC_Thrust')
        npc={'healthMax':100,'attributes':c['attributes'],
             'skills':{'Одноручное оружие':20},'defenses':{},'armor':0,'attack':{},'abilities':c['talents']}
        derived=npc_derived(npc,{},[gear(.2,'Голова'),gear(.2)],{},1)
        self.assertEqual(derived['equipmentRecoveryRaw'],.9)
        self.assertEqual(derived['equipmentRecovery'],.9)
        source=copy.deepcopy(catalog_texts()[1]['железный меч'])
        prefab=source['properties']['gameData']['prefab']
        stub={'prefab':prefab,'equipped_slot':'Оружие I — правая рука'}
        derived=npc_derived(npc,{},[stub],{},1)
        self.assertAlmostEqual(derived['equipmentRecoveryRaw'],item_recovery(source))

    def test_small_item_does_not_add_a_whole_cooldown_turn(self):
        c,d,s=self.battle('Abl_PC_Thrust',recovery=.06)
        base=profile(resolve('Abl_PC_Thrust'),_derived(c,[]))['cooldown']
        preview=next(a for a in s.view(c,d,[],2)['actions'] if a['kind']=='ability')
        self.assertEqual(preview['equipmentRecovery'],.14)
        self.assertEqual(preview['cooldown'],base+.14)
        with patch('training_combat.random.randint',side_effect=lambda lo,hi:hi):
            s.act({'kind':'ability','name':'Abl_PC_Thrust'},c,d,[],2)
        for _ in range(base+1):s._end_turn()
        self.assertEqual(s.remaining('ability:Abl_PC_Thrust'),0)

    def test_glossary_explains_fractional_sum_and_no_action_cost(self):
        entries=json.loads(Path('web/data/encyclopedia.json').read_text(encoding='utf-8'))['entries']
        text=next(e['body'] for e in entries if e['asset']=='GL_GameMechanics_Recovery')
        self.assertNotIn('50%',text)
        self.assertNotIn('округляется',text)
        for phrase in ['сохраняют дробную часть','0,44 раунда','не отнимает основное действие','не блокирует обычную атаку']:
            self.assertIn(phrase,text)


if __name__=='__main__':unittest.main()
