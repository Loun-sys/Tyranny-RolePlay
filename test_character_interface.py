import io
import unittest
from pathlib import Path

from PIL import Image
from ability_rules import normalize_talent, resolve, passive_equipment
from card_renderer import render_inventory_card
from registration_api import _derived
from test_consumables import character


class CharacterInterfaceTests(unittest.TestCase):
    def test_registration_and_gameplay_text_do_not_label_players_fatebinders(self):
        from constants import ABILITY_DETAILS
        from ability_rules import library
        from npc_store import ability_library
        from localization import neutralize_player_reference, localize_game_text, localize_player_text
        import bot
        registration=bot.bot.tree.get_command('регистрация')
        self.assertEqual(registration.description,'Получить личную ссылку на создание персонажа')
        self.assertNotIn('Вершител',Path('web/archive.js').read_text(encoding='utf-8'))
        for detail in ABILITY_DETAILS.values():self.assertNotIn('Вершител',detail['requirements'])
        for row in [*library(),*ability_library()]:
            self.assertNotRegex(row['description'],r'(?i)Вершител\w*\b(?!\s+победы\b)')
        for original,expected in [('Вершитель Судеб','Персонаж'),('к Вершителю судеб','к Персонажу'),('Вершителя Судеб','Персонажа'),('Вершителем Судеб','Персонажем'),('вершители судеб','персонажи')]:
            self.assertEqual(neutralize_player_reference(original),expected)
        self.assertEqual(neutralize_player_reference('Вершитель победы'),'Вершитель победы')
        self.assertEqual(neutralize_player_reference('оружие Вершителя'),'оружие Персонажа')
        self.assertEqual(neutralize_player_reference('над Вершителем'),'над Персонажем')
        self.assertEqual(neutralize_player_reference("Fatebinder's weapon"),'персонажа weapon')
        self.assertEqual(localize_game_text('Печать Вершителя Судеб'),'Печать Вершителя Судеб')
        self.assertEqual(localize_player_text('оружие Вершителя Судеб'),'оружие Персонажа')

    def test_discord_allowlist_and_one_button(self):
        import bot
        commands = list(bot.bot.tree.get_commands())
        try:
            bot.restrict_commands(bot.bot.tree)
            self.assertEqual({c.name for c in bot.bot.tree.get_commands()}, {'админ','регистрация','персонаж','удалить-персонажа'})
        finally:
            for command in commands:
                bot.bot.tree.add_command(command, override=True)

    def test_only_portal_button(self):
        import asyncio
        from bot import CharacterView
        async def check():
            view = CharacterView({'user_id':1})
            self.assertEqual([c.label for c in view.children], ['Личное дело'])
        asyncio.run(check())

    def test_inventory_image_uses_derived_values(self):
        c = character()
        d = _derived(c, [])
        result = render_inventory_card(c, [], d, {'quickSlots':4,'weaponSets':2})
        with Image.open(result) as image:
            self.assertEqual(image.size, (1100,1090))
            self.assertGreater(len(result.getvalue()), 10000)

    def test_inventory_portrait_fills_equipment_and_quickbar_background(self):
        from unittest.mock import patch
        c=character();c['portrait_url']='local://fixture'
        with patch('card_renderer._load_portrait',return_value=Image.new('RGB',(400,300),'#287c5a')):
            result=render_inventory_card(c,[],_derived(c,[]),{'quickSlots':4,'weaponSets':2})
        with Image.open(result) as image:
            for point in [(310,85),(1068,85),(310,890),(1068,890),(700,400),(750,775)]:
                self.assertEqual(image.getpixel(point),(40,124,90),point)
            self.assertEqual(image.getpixel((410,128)),(0,0,0)) # head label backplate

    def test_details_preserve_source_and_modifiers(self):
        row = next(r for r in __import__('ability_rules').library() if r['passive'] and r.get('abilityClass')=='GenericAbility' and
                   any(s['AffectsStat']==57 and s.get('Apply')==0 and not s.get('ApplicationPrerequisites') for n in r['nodes'] if n['side']=='self' and n['phase']=='root' for s in n['statuses']))
        talent = normalize_talent({'name':'Старое имя','prefab':row['key']})
        self.assertEqual(talent['legacyName'], 'Старое имя')
        self.assertTrue(any('Сила:' in x for x in talent['mechanics']['effects']))
        c = character()
        c['talents'] = [{'prefab':row['key']}]
        self.assertNotEqual(_derived(c,[])['effectiveAttributes']['Сила'],10)

    def test_active_details_use_rounds_and_source_damage(self):
        t = normalize_talent({'name':'Удар щитом','prefab':'Abl_PC_Defense_ShieldSlam'})
        self.assertIn('3 раундов',t['mechanics']['details'])
        self.assertIn('10–15',t['mechanics']['details'])
        self.assertTrue(t['mechanics']['effects'])

    def test_shield_mastery_affects_equipped_shield_only_and_highest_rank(self):
        shield={'name':'Щит','category':'Щиты','equipped_slot':'Оружие I — левая рука','properties':{'gameData':{'equipmentComponents':[{'BaseParryBonus':10,'BaseDodgeBonus':5,'BaseEnduranceBonus':10,'BaseAccuracyBonus':0}]}}}
        c=character()
        base=_derived(c,[shield])
        c['talents']=[{'prefab':'PSV_PC_Shield_Mastery_01'}]
        self.assertEqual(_derived(c,[shield])['defenses']['Парирование'],base['defenses']['Парирование']+4)
        self.assertEqual(_derived(c,[])['defenses']['Парирование'],20)
        c['talents'].append({'prefab':'PSV_PC_Shield_Mastery_02'})
        self.assertEqual(_derived(c,[shield])['defenses']['Парирование'],base['defenses']['Парирование']+8)

    def test_mastery_matches_weapon_and_uses_highest_rank(self):
        from ability_rules import weapon_mastery
        sword={'name':'Меч','category':'Одноручное оружие','equipped_slot':'Оружие I — правая рука'}
        talents=[{'name':'Мастер одноручного оружия I'},{'name':'Мастер одноручного оружия II'}]
        multiplier,chances=weapon_mastery(talents,[sword])
        self.assertAlmostEqual(multiplier,1.1,places=5)
        self.assertEqual(chances,{3:4,2:6})
        self.assertEqual(weapon_mastery(talents,[]),(1,{}))

    def test_mastery_extra_hits_are_real_attacks(self):
        from training_combat import TrainingSession
        from unittest.mock import patch
        c=character();d=_derived(c,[]);d['attack']['splitChances']={3:100}
        s=TrainingSession(1);s.player_position=(9,4)
        with patch('training_combat.random.randint',side_effect=lambda low,high:100 if high==100 else low):s.act({'kind':'attack'},c,d,[],2)
        self.assertEqual(s.attacks,3)
        self.assertFalse(s.action_available)

    def test_canonical_names_unlock_same_equipment_slots(self):
        from database import Database
        self.assertEqual(Database._equipment_limits_from_talents({'Поясная сумка'})['quickSlots'],6)
        self.assertEqual(Database._equipment_limits_from_talents({'Множество рук I'})['weaponSets'],3)

    def test_stances_change_stats_only_when_active(self):
        from ability_rules import stance_equipment
        c=character();c['talents']=[{'name':'Стойка: блиц'}]
        self.assertEqual(_derived(c,[])['cooldownMultiplier'],1)
        self.assertAlmostEqual(_derived(c,stance_equipment('Стойка: блиц'))['cooldownMultiplier'],.85)
        self.assertEqual(_derived(c,stance_equipment('Стойка: несокрушимый'))['attack']['penetration'],4)
        d=_derived(c,stance_equipment('Стойка: стражник'))
        self.assertEqual(d['armorByType']['Рубящий'],2)
        self.assertEqual(d['armorByType']['Огненный'],0)

    def test_unresolved_talent_is_not_marked_working(self):
        t = normalize_talent({'name':'Нет в игровых файлах'})
        self.assertTrue(t['mechanics']['limitation'])

    def test_bandolier_resolves_parent_not_potion_child(self):
        self.assertEqual(resolve({'name_en':'Bandolier'})['key'],'PSV_PC_Leadership_Bandolier_2of2')
        self.assertEqual(resolve('Патронташ')['key'],'PSV_PC_Leadership_Bandolier_2of2')
        self.assertEqual(resolve('Мастер щита I')['key'],'PSV_PC_Shield_Mastery_01')

    def test_web_tabs_and_chargen(self):
        archive = Path('web/archive.html').read_text(encoding='utf-8')
        app = Path('web/app.js').read_text(encoding='utf-8')
        self.assertNotIn('data-tab="overview"',archive)
        self.assertIn('Здесь находятся все зарегистрированные персонажи.',archive)
        self.assertNotIn('<h4>ЛИЧНОЕ ДРЕВО</h4>',app)
        self.assertIn('Кем вы являетесь?',Path('web/index.html').read_text(encoding='utf-8'))


if __name__=='__main__':
    unittest.main()
