import copy
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch
from constants import ATTRIBUTES, SKILLS
from skill_checks import configuration, check_skills, roll_check, character_checks


def character():
    return {'id':1,'attributes':{name:10 for name in ATTRIBUTES},
            'skills':{name:{'value':20,'experience':3} for name in SKILLS},
            'health_max':20,'talents':[],'active_weapon_set':1}


class SkillCheckTests(unittest.TestCase):
    def setUp(self):
        self.c=character()

    def checks(self):return check_skills(self.c['attributes'],self.c['skills'])

    def test_exact_five_formulas_and_attributes(self):
        expected={'Запугивание':('Живучесть',['Атлетика','@combatMax']),
                  'Влияние':('Смекалка',['Хитроумие','Знания']),
                  'Наблюдательность':('Быстрота',['Знания','Хитроумие']),
                  'Выносливость':('Стойкость',['Атлетика','Парирование']),
                  'Проницательность':('Искусность',['Хитроумие','Уклонение'])}
        self.assertEqual({d['name']:(d['attribute'],d['sources']) for d in configuration()['definitions']},expected)
        self.assertNotIn('Влияние',SKILLS,'Derived checks must not enter XP/creation allocation tables')

    def test_half_points_are_preserved_and_attributes_only_enter_the_roll(self):
        self.c['skills']['Хитроумие']['value']=39
        self.c['skills']['Знания']['value']=20
        self.c['attributes']['Смекалка']=5
        c=self.checks()['Влияние']
        self.assertEqual(c['value'],29.5)
        self.assertEqual(c['diceCount'],2)
        self.assertEqual(c['formula'],'2 + 2d6')
        self.assertEqual(c['attributeBonus'],2)
        self.assertEqual((c['minimum'],c['maximum']),(4,14))

    def test_full_tens_not_nearest_tens_or_minimum_die(self):
        for value,dice in [(0,0),(9.5,0),(10,1),(19.5,1),(20,2),(29.5,2),(30,3)]:
            self.c['skills']['Хитроумие']['value']=value
            self.c['skills']['Знания']['value']=value
            self.assertEqual(self.checks()['Влияние']['diceCount'],dice)

    def test_attribute_third_is_rounded_before_the_roll(self):
        self.assertEqual(configuration()['attributeDivisor'],3)
        for attribute,bonus in [(8,3),(9,3),(10,3),(11,4),(12,4),(13,4),(14,5),(10.5,4)]:
            self.c['attributes']['Смекалка']=attribute
            check=self.checks()['Влияние']
            self.assertEqual(check['attributeValue'],attribute)
            self.assertEqual(check['attributeBonus'],bonus)
            result=roll_check(check,-2,Mock(randint=Mock(side_effect=[2,6])))
            self.assertEqual(result['total'],bonus+6)
            self.assertIsInstance(result['total'],int)

    def test_strongest_combat_includes_magic_but_not_defenses_or_knowledge(self):
        self.c['skills']['Управление огнём']['value']=80
        self.c['skills']['Парирование']['value']=999
        self.c['skills']['Знания']['value']=999
        c=self.checks()['Запугивание']
        self.assertEqual(c['sources'][1]['name'],'Управление огнём')
        self.assertEqual(c['value'],50)
        self.c['skills']['Луки']['value']=90
        self.assertEqual(self.checks()['Запугивание']['value'],55)

    def test_equal_maxima_are_deterministic(self):
        self.c['skills']['Одноручное оружие']['value']=40
        self.c['skills']['Луки']['value']=40
        source=self.checks()['Запугивание']['sources'][1]
        self.assertEqual(source['name'],'Одноручное оружие')
        self.assertEqual(source['tiedSkills'],['Одноручное оружие','Луки'])

    def test_roll_example_and_signed_flat_modifiers(self):
        self.c['attributes']['Смекалка']=6
        check=self.checks()['Влияние']
        for modifier,total in [(0,10),(3,13),(-2,8)]:
            rng=Mock(randint=Mock(side_effect=[2,6]))
            result=roll_check(check,modifier,rng)
            self.assertEqual(result,{'rolls':[2,6],'modifier':modifier,'total':total})
            self.assertEqual(rng.randint.call_count,2)
            rng.randint.assert_called_with(1,6)

    def test_zero_dice_uses_attribute_and_modifier_only(self):
        self.c['skills']['Знания']['value']=0
        self.c['skills']['Хитроумие']['value']=0
        rng=Mock()
        result=roll_check(self.checks()['Влияние'],-2,rng)
        self.assertEqual(result['rolls'],[])
        self.assertEqual(result['total'],1)
        rng.randint.assert_not_called()

    def test_invalid_modifier_is_rejected(self):
        for value in (True,1.5,1001,-1001,'2'):
            with self.assertRaises(ValueError):roll_check(self.checks()['Влияние'],value)

    def test_calculation_does_not_mutate_character_or_xp(self):
        original=copy.deepcopy(self.c)
        self.checks()
        self.assertEqual(self.c,original)

    def test_effective_equipment_and_noncombat_endurance_are_separate(self):
        from registration_api import _derived
        self.c['skills']['Атлетика']['value']=100
        self.c['skills']['Парирование']['value']=60
        base=_derived(self.c,[])
        self.assertEqual(base['checkSkills']['Выносливость']['value'],80)
        self.assertEqual(base['defenses']['Выносливость'],20)
        item={'name':'Тестовый аксессуар','equipped_slot':'Аксессуар 1','properties':{'Хитроумие':10,'Смекалка':2},'category':'Аксессуары'}
        effective=_derived(self.c,[item])
        check=effective['checkSkills']['Влияние']
        self.assertEqual(check['attributeValue'],12)
        self.assertEqual(check['attributeBonus'],4)
        self.assertEqual(check['value'],sum(effective['effectiveSkills'][n]*.5 for n in ['Знания','Хитроумие']))
        self.assertGreater(check['value'],base['checkSkills']['Влияние']['value'])


class DiscordSkillCheckTests(unittest.IsolatedAsyncioTestCase):
    async def test_roll_is_public_uses_effective_values_and_does_not_write(self):
        import bot as module
        import discord
        c=character();c['name']='Герой';c['attributes']['Смекалка']=5
        checks=check_skills(c['attributes'],c['skills'])
        interaction=SimpleNamespace(response=SimpleNamespace(defer=AsyncMock()),followup=SimpleNamespace(send=AsyncMock()))
        with patch.object(module,'require_character',AsyncMock(return_value=c)), \
             patch.object(module,'character_checks',AsyncMock(return_value=checks)) as effective, \
             patch.object(module,'roll_check',return_value={'total':11,'rolls':[2,6],'modifier':-2}):
            await module.skill_check.callback(interaction,discord.app_commands.Choice(name='Влияние',value='Влияние'),-2)
        effective.assert_awaited_once_with(module.bot.db,c)
        interaction.response.defer.assert_awaited_once_with(thinking=True)
        embed=interaction.followup.send.await_args.kwargs['embed']
        self.assertEqual(embed.title,'Влияние · 11')
        self.assertIn('2d6',embed.description)
        self.assertIn('**2**',embed.description)
        self.assertIn('-2',embed.description)
        self.assertNotIn('УСПЕХ',embed.title)
        self.assertFalse(embed.footer.text)

    async def test_missing_character_never_rolls(self):
        import bot as module
        with patch.object(module,'require_character',AsyncMock(return_value=None)),patch.object(module,'roll_check') as roll:
            await module.skill_check.callback(SimpleNamespace(),SimpleNamespace(value='Влияние'),0)
        roll.assert_not_called()

    async def test_check_command_is_retained_and_exposes_only_derived_choices(self):
        import bot as module
        tree=Mock(get_commands=Mock(return_value=[SimpleNamespace(name='проверка'),SimpleNamespace(name='бой')]))
        module.restrict_commands(tree)
        tree.remove_command.assert_called_once_with('бой')
        parameters={p.name:p for p in module.skill_check.parameters}
        self.assertEqual(len(parameters['навык'].choices),5)
        self.assertEqual(parameters['модификатор'].default,0)

    async def test_discord_and_dossier_share_the_same_equipment_projection(self):
        c=character();db=SimpleNamespace(inventory=AsyncMock(return_value=[]))
        from registration_api import _derived
        with patch('consumable_store.states',AsyncMock(return_value={})):
            self.assertEqual(await character_checks(db,c),_derived(c,[])['checkSkills'])


if __name__=='__main__':unittest.main()
