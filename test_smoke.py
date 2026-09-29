import tempfile
import unittest
from pathlib import Path

from card_renderer import render_character_card
from database import Database
from combat import Combatant, CombatSession, resolve_attack
from registration_api import _configuration, _validate_payload
from talent_data import TALENTS
from extended_talent_data import parse_faction_talents, parse_talent_page
from constants import (
    ABILITY_DETAILS, ATTRIBUTES, BACKGROUNDS, SKILLS, SPECIALIZATIONS,
    SPECIALIZATION_ABILITY_CHOICES,
)


class TyrannySmokeTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = Database(Path(self.temp.name) / "test.sqlite3")
        await self.db.initialize()

    async def asyncTearDown(self):
        self.temp.cleanup()

    async def test_character_inventory_equipment_spell_and_card(self):
        character_id = await self.db.create_character(
            1, 2, "Атли", "Дипломат", "Меч и щит", "Заклинания молний"
        )
        character = await self.db.get_character(1, 2)
        self.assertEqual(len(character["attributes"]), 6)
        self.assertEqual(len(character["skills"]), 22)
        self.assertEqual(len(await self.db.catalog_search(limit=100)), 100)
        self.assertGreater(character["skills"]["Управление молниями"]["value"], 20)
        await self.db.set_attribute(character_id, "Живучесть", 14)
        character = await self.db.get_character(1, 2)
        self.assertEqual(character["health_max"], 24)
        await self.db.upsert_catalog([{
            "name": "Меч Вершителя", "category": "Одноручное оружие", "hands": 1,
            "description": "Клинок для проверки.", "quality": "Добротное",
        }])
        self.assertTrue(await self.db.give_item(character_id, "Меч Вершителя"))
        inventory = await self.db.inventory(character_id)
        success, _ = await self.db.equip(character_id, inventory[0]["inventory_id"], "Оружие I — правая рука")
        self.assertTrue(success)
        await self.db.create_spell(
            character_id, "Грозовая печать", "Молния", "Сосредоточенная сила", ["Дальность"], [], 35
        )
        self.assertEqual(len(await self.db.spells(character_id)), 1)
        self.assertEqual(await self.db.adjust_reputation(character_id, "Опальные", "favor", 25), (0, 25))
        self.assertEqual(await self.db.adjust_reputation(character_id, "Опальные", "wrath", 10), (0, 10))
        self.assertEqual(len(await self.db.reputations(character_id)), 1)
        await self.db.save_edict(1, "Эдикт Бурь", "Долина", "Захватить цитадель", "Три дня", "Вечная гроза", 99)
        self.assertEqual(len(await self.db.edicts(1)), 1)
        self.assertTrue(await self.db.resolve_edict(1, "Эдикт Бурь"))
        await self.db.save_spire(1, "Горный Шпиль", "Каменное море", "Кузница", "Главная база")
        self.assertEqual((await self.db.spires(1))[0]["upgrade_name"], "Кузница")
        card = render_character_card(character, await self.db.inventory(character_id))
        self.assertGreater(len(card.getvalue()), 10_000)

    async def test_automated_combat_resolution(self):
        attacker = Combatant(
            key="a", name="Вершитель", team="Герои", health=30, health_max=30,
            accuracy=80, damage_min=8, damage_max=8,
            skills={"Парирование": 30}, attributes={"Живучесть": 10, "Стойкость": 10, "Смекалка": 10},
        )
        target = Combatant(
            key="b", name="Страж", team="Враги", health=30, health_max=30,
            armor=2, skills={"Парирование": 1},
            attributes={"Живучесть": 10, "Стойкость": 10, "Смекалка": 10},
        )
        text = resolve_attack(attacker, target)
        self.assertIn("Вершитель", text)
        self.assertLess(target.health, 30)
        session = CombatSession(1, 1, 1, self.db, {"a": attacker, "b": target}, started=True)
        self.assertEqual(session.current.name, "Вершитель")
        session.advance(attacker, 3)
        self.assertEqual(session.current.name, "Страж")

    async def test_private_web_registration_token_and_payload(self):
        token = await self.db.create_registration_token(55, 77)
        self.assertEqual(await self.db.registration_token_owner(token), (55, 77))
        payload = {
            "name": "Калио", "background": BACKGROUNDS[0],
            "specialization1": SPECIALIZATIONS[0], "specialization2": SPECIALIZATIONS[1],
            "attributes": {name: 10 for name in ATTRIBUTES},
            "skills": {name: 0 for name in SKILLS},
        }
        payload["attributes"][ATTRIBUTES[0]] = 18
        payload["skills"][SKILLS[0]] = 20
        clean, problem = _validate_payload(payload)
        self.assertFalse(problem)
        self.assertEqual(clean["name"], "Калио")
        payload["ability1"] = "Несуществующая способность"
        clean, problem = _validate_payload(payload)
        self.assertIsNone(clean)
        self.assertIn("способность", problem)
        self.assertTrue(await self.db.consume_registration_token(token))
        self.assertIsNone(await self.db.registration_token_owner(token))
        self.assertFalse(await self.db.consume_registration_token(token))

    async def test_selected_starting_abilities_and_background_bonus(self):
        abilities = [
            SPECIALIZATION_ABILITY_CHOICES["Меч и щит"][1],
            SPECIALIZATION_ABILITY_CHOICES["Двуручный меч"][0],
        ]
        character_id = await self.db.create_character(
            9, 10, "Нерат", "Солдат", "Меч и щит", "Двуручный меч", abilities,
        )
        character = await self.db.get_character(9, 10)
        self.assertEqual(character_id, character["id"])
        self.assertIn("Раскол", {talent["name"] for talent in character["talents"]})
        # 20 от характеристик +2 от происхождения +6 от основной специализации.
        self.assertEqual(character["skills"]["Одноручное оружие"]["value"], 28)

    async def test_ability_reference_data_and_wiki_icons(self):
        config = _configuration()
        configured = {
            ability["name"]
            for specialization in config["specializationDetails"].values()
            for ability in specialization["abilities"]
        }
        self.assertEqual(configured, set(ABILITY_DETAILS))
        for name, details in ABILITY_DETAILS.items():
            self.assertTrue(details["effects"], name)
            self.assertTrue(details["source"].startswith("https://tyranny.fandom.com/wiki/"), name)
            self.assertTrue((Path("web") / details["icon"]).is_file(), name)
        self.assertEqual(len(TALENTS), 121)
        for talent in TALENTS:
            self.assertTrue(talent.get("icon_url", "").startswith("https://static.wikia.nocookie.net/tyranny_gamepedia_en/images/"), talent["name"])
            self.assertTrue(talent.get("source_url", "").startswith("https://tyranny.fandom.com/wiki/"), talent["name"])

    async def test_legacy_resolve_name_migrates_to_stoikost(self):
        character_id = await self.db.create_character(
            3, 4, "Клеон", "Солдат", "Меч и щит", "Двуручный меч",
        )
        async with self.db.connect() as db:
            await db.execute("DELETE FROM attributes WHERE character_id=? AND name='Стойкость'", (character_id,))
            await db.execute(
                "INSERT INTO attributes(character_id,name,value) VALUES(?,?,?)",
                (character_id, "Решимость", 14),
            )
            await db.commit()
        await self.db.initialize()
        character = await self.db.get_character(3, 4)
        self.assertEqual(character["attributes"]["Стойкость"], 14)
        self.assertNotIn("Решимость", character["attributes"])
        self.assertEqual(character["background"], "Авангард")

    async def test_portal_level_rewards_and_safe_progression(self):
        character_id = await self.db.create_character(
            77, 88, "Лантри", "Дипломат", "Меч и щит", "Заклинания молний",
        )
        await self.db.set_skill(character_id, "Одноручное оружие", 47)
        before = (await self.db.get_character(77, 88))["skills"]["Одноручное оружие"]["value"]
        experience, level, _ = await self.db.adjust_experience(character_id, 1000)
        self.assertEqual((experience, level), (1000, 2))
        character = await self.db.get_character(77, 88)
        self.assertEqual(character["attribute_points"], 1)
        self.assertEqual(character["talent_points"], 1)
        ok, _ = await self.db.spend_attribute_point(character_id, "Сила")
        self.assertTrue(ok)
        after = (await self.db.get_character(77, 88))["skills"]["Одноручное оружие"]["value"]
        self.assertGreaterEqual(after, before)
        tier_zero = next(talent for talent in TALENTS if talent["tier"] == 0)
        ok, _ = await self.db.spend_talent_point(character_id, tier_zero)
        self.assertTrue(ok)
        token = await self.db.create_portal_token(77, 88)
        self.assertEqual(await self.db.portal_character_id(token), character_id)
        replacement = await self.db.create_portal_token(77, 88)
        self.assertIsNone(await self.db.portal_character_id(token))
        self.assertEqual(await self.db.portal_character_id(replacement), character_id)

    async def test_inventory_capacity_depends_on_athletics_and_tiny_items_are_free(self):
        character_id = await self.db.create_character(
            90, 91, "Калеб", "Солдат", "Меч и щит", "Двуручный меч",
        )
        await self.db.upsert_catalog([
            {"name": "Чернильница суда", "category": "Прочее", "weight": .1},
            {"name": "Тяжёлый трофей", "category": "Прочее", "weight": 2},
        ])
        self.assertTrue(await self.db.give_item(character_id, "Чернильница суда", 5))
        capacity = await self.db.inventory_capacity(character_id)
        self.assertEqual(capacity["used"], 0)
        self.assertEqual(capacity["capacity"], 8 + capacity["athletics"] // 5)
        self.assertTrue(await self.db.give_item(character_id, "Тяжёлый трофей", capacity["capacity"]))
        self.assertFalse(await self.db.give_item(character_id, "Тяжёлый трофей"))

    async def test_background_and_faction_wiki_talent_parsers(self):
        page = """\n==Quill==\n{|class=\"wikitable\"\n|-\n! {{ficon|abl_lantry_quill_strike.png|Quill Strike|60px}}\n| 100% Damage attack with +20 Accuracy<br/>Weak Interrupt\n|0\n|}\n"""
        talents = parse_talent_page(page, "Книгочей", "Lantry talents")
        self.assertEqual(len(talents), 1)
        self.assertEqual(talents[0]["tree"], "Книгочей · Перо")
        self.assertIn("Удар", talents[0]["name"])
        self.assertTrue(talents[0]["icon_url"].startswith("https://static.wikia.nocookie.net/"))
        reputation = """==Unlocked abilities==\n{|class=\"wikitable\"\n|-\n! {{ficon|psv_rep_fallen_leader.png|Fallen Leader|60px}}\n| On defeat: Grant +3 Quickness to allies\n|[[Stonestalker Tribe]]<br/>Favor 3\n|}\n"""
        faction = parse_faction_talents(reputation)
        self.assertEqual(faction[0]["faction"], "Каменные Сталкеры")
        self.assertEqual((faction[0]["axis"], faction[0]["tier"]), ("favor", 3))


if __name__ == "__main__":
    unittest.main()
