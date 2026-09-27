import tempfile
import unittest
from pathlib import Path

from card_renderer import render_character_card
from database import Database
from combat import Combatant, CombatSession, resolve_attack
from registration_api import _validate_payload
from constants import ATTRIBUTES, BACKGROUNDS, SKILLS, SPECIALIZATIONS


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
            skills={"Парирование": 30}, attributes={"Живучесть": 10, "Решимость": 10, "Смекалка": 10},
        )
        target = Combatant(
            key="b", name="Страж", team="Враги", health=30, health_max=30,
            armor=2, skills={"Парирование": 1},
            attributes={"Живучесть": 10, "Решимость": 10, "Смекалка": 10},
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
        self.assertTrue(await self.db.consume_registration_token(token))
        self.assertIsNone(await self.db.registration_token_owner(token))
        self.assertFalse(await self.db.consume_registration_token(token))


if __name__ == "__main__":
    unittest.main()
