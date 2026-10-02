import json
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

from card_renderer import render_character_card
from database import Database
from combat import Combatant, CombatSession, resolve_attack
from registration_api import _configuration, _validate_payload
from talent_data import TALENTS
from extended_talent_data import parse_faction_talents, parse_talent_page
from localization import localize_game_text, seconds_to_rounds
from official_localization import official_spell_details
from training_combat import TrainingSession
from tactical_grid import BASE_MOVEMENT, TacticalGrid, initiative_bonus
from sigil_data import SIGIL_LIBRARY, sigil_key_from_scroll_url, spell_runtime_profile, validate_formula
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

    async def test_official_game_encyclopedia_export(self):
        payload = json.loads((Path(__file__).parent / "web" / "data" / "encyclopedia.json").read_text(encoding="utf-8"))
        self.assertEqual(len(payload["entries"]), 203)
        self.assertEqual(len(payload["categories"]), 7)
        athletics = next(entry for entry in payload["entries"] if entry["titleEn"] == "Athletics")
        self.assertEqual(athletics["title"], "Атлетика")
        self.assertIn("пересеченной местности", athletics["body"])
        self.assertEqual(len(athletics["related"]), 3)
        self.assertFalse(any(title in {"Sage", "GL_Wardens_Key", "Тyнон"} for title in (entry["title"] for entry in payload["entries"])))
        assets = {entry["asset"] for entry in payload["entries"]}
        self.assertFalse({"GL_Binders 2", "GL_GameMechanics_CompanionCombo", "GL_GameMechanics_Engagement", "GL_GameMechanics_Scouting", "GL_GameMechanics_DPS", "GL_GameMechanics_DisengagementDefense"} & assets)
        self.assertFalse({4, 7} & {entry["category"] for entry in payload["entries"]})
        mechanical = "\n".join(entry["body"] for entry in payload["entries"] if entry["category"] == 1)
        self.assertNotIn("Сирин", mechanical)
        self.assertNotIn("Вершител", mechanical)
        self.assertNotIn("режиме паузы", mechanical)
        self.assertIn("Певчий может спеть свои арии", mechanical)
        reputation = next(entry for entry in payload["entries"] if entry["asset"] == "GL_GameMechanics_Reputation")
        self.assertIn("к Персонажу игрока", reputation["body"])
        alone = next(entry for entry in payload["entries"] if entry["asset"] == "GL_Boon_Quality_Alone_Time")
        self.assertIn("с оружием", alone["body"])
        self.assertNotIn("с одноручным оружием", alone["body"])

    async def test_complete_catalog_and_turn_localization(self):
        async with self.db.connect() as db:
            total = (await db.execute_fetchall("SELECT COUNT(*) AS total FROM item_catalog"))[0]["total"]
            without_image = (await db.execute_fetchall(
                "SELECT COUNT(*) AS total FROM item_catalog WHERE image_url=''"
            ))[0]["total"]
            without_lore = (await db.execute_fetchall(
                "SELECT COUNT(*) AS total FROM item_catalog WHERE lore=''"
            ))[0]["total"]
        self.assertGreaterEqual(total, 1143)
        self.assertEqual(without_image, 0)
        # Some plain equipment prefabs genuinely have no lore in the game.
        self.assertLess(without_lore, total)
        spell_details = official_spell_details()
        self.assertEqual(len(spell_details), 64)
        self.assertTrue(all(row["name"] and row["description"] for row in spell_details.values()))
        self.assertEqual(spell_details[("Огонь", "Дальний удар")]["name"], "Огненный шар")
        self.assertEqual(seconds_to_rounds(10), "1 раунд")
        self.assertEqual(seconds_to_rounds(25), "2,5 раунда")
        localized = localize_game_text("Барик получает эффект на 30 секунд")
        self.assertEqual(localized, "персонаж получает эффект на 3 раунда")

    async def test_training_combat_is_turn_based_and_reward_free(self):
        character = {
            "name": "Испытатель", "portrait_url": "", "experience": 125,
            "attributes": {"Сила": 12, "Смекалка": 11, "Быстрота": 10},
            "skills": {"Одноручное оружие": {"value": 42}},
            "talents": [
                {"name": "Удар щитом"},
                {"name": "Стойка: Страж", "description": "+2 брони против физических атак."},
            ],
        }
        derived = {
            "attack": {"accuracy": 42, "damageMin": 8, "damageMax": 12, "skill": "Одноручное оружие"},
            "effectiveAttributes": character["attributes"], "cooldownMultiplier": 1,
            "armor": 3,
        }
        session = TrainingSession(character_id=1)
        stance = session.act({"kind": "stance", "name": "Стойка: Страж"}, character, derived, [], 2)
        self.assertEqual(session.active_stance, "Стойка: Страж")
        self.assertIn("принимает стойку", stance["line"])
        session.act({"kind": "move", "x": 8, "y": 4}, character, derived, [], 2)
        self.assertEqual(session.movement_remaining, 0)
        session.act({"kind": "end_turn"}, character, derived, [], 2)
        session.act({"kind": "move", "x": 9, "y": 4}, character, derived, [], 2)
        session.act({"kind": "ability", "name": "Удар щитом"}, character, derived, [], 2)
        self.assertEqual(session.round_number, 2)
        self.assertFalse(session.action_available)
        self.assertGreater(session.remaining("ability:Удар щитом"), 0)
        self.assertEqual(character["experience"], 125)
        view = session.view(character, derived, [], 2)
        self.assertEqual(view["rewards"], {"experience": 0, "skillExperience": 0, "loot": []})
        self.assertEqual(view["grid"]["cellMeters"], 1)
        self.assertEqual(view["turn"]["movementMax"], BASE_MOVEMENT)
        self.assertEqual(len(view["initiative"]), 4)
        self.assertEqual({row['id'] for row in view['initiative']}, {'player', 'dummy', 'dummy_left', 'dummy_right'})
        self.assertEqual([row['total'] for row in view['initiative']], sorted((row['total'] for row in view['initiative']), reverse=True))
        self.assertEqual(len(view["targets"]), 3)
        opportunity = session.act({"kind": "move", "x": 8, "y": 4}, character, derived, [], 2)
        self.assertIn("атаку по возможности", opportunity["line"])
        session.act({"kind": "select_target", "targetId": "dummy_left"}, character, derived, [], 2)
        self.assertEqual(session.selected_target_id, "dummy_left")

    async def test_combat_quickbar_is_persistent_and_replaceable(self):
        async with self.db.connect() as db:
            await db.execute(
                "INSERT INTO characters(guild_id,user_id,name,background,specialization_1,specialization_2) "
                "VALUES(1,2,'Герой','Книгочей','Меч и щит','Заклинания льда')"
            )
            await db.commit()
            character_id = int((await db.execute_fetchall("SELECT id FROM characters"))[0]["id"])
        await self.db.set_combat_quickbar(character_id, 1, "attack", "Обычная атака")
        await self.db.set_combat_quickbar(character_id, 2, "spell", "Ледяное копьё")
        rows = await self.db.combat_quickbar(character_id)
        self.assertEqual([(row["slot"], row["action_kind"]) for row in rows], [(1, "attack"), (2, "spell")])
        await self.db.set_combat_quickbar(character_id, 2, "ability", "Удар щитом")
        self.assertEqual((await self.db.combat_quickbar(character_id))[1]["action_name"], "Удар щитом")
        await self.db.set_combat_quickbar(character_id, 1)
        self.assertEqual([row["slot"] for row in await self.db.combat_quickbar(character_id)], [2])
        bindings = [{'slot': i, 'kind': '', 'name': ''} for i in range(1, 10)]
        bindings[0].update(kind='spell', name='Ледяное копьё')
        bindings[1].update(kind='attack', name='Обычная атака')
        await self.db.replace_combat_quickbar(character_id, bindings)
        saved = await self.db.combat_quickbar(character_id)
        self.assertEqual(len(saved), 9)
        self.assertEqual(saved[0]['action_name'], 'Ледяное копьё')
        self.assertEqual(saved[4]['action_kind'], '')
        with self.assertRaises(ValueError):
            await self.db.replace_combat_quickbar(character_id, bindings[:2])
        self.assertEqual(await self.db.combat_quickbar(character_id), saved)

    async def test_legacy_quickbar_migration_preserves_bindings(self):
        async with self.db.connect() as db:
            await db.execute("INSERT INTO characters(guild_id,user_id,name,background,specialization_1,specialization_2) VALUES(1,2,'Герой','Книгочей','Меч и щит','Заклинания льда')")
            cid = int((await db.execute_fetchall('SELECT id FROM characters'))[0]['id'])
            await db.execute('DROP TABLE combat_quickbar')
            await db.execute('CREATE TABLE combat_quickbar (character_id INTEGER NOT NULL REFERENCES characters(id) ON DELETE CASCADE, slot INTEGER NOT NULL CHECK(slot BETWEEN 1 AND 5), action_kind TEXT NOT NULL, action_name TEXT NOT NULL, PRIMARY KEY(character_id,slot))')
            await db.execute("INSERT INTO combat_quickbar VALUES(?,5,'attack','Обычная атака')", (cid,))
            await db.commit()
        await self.db.initialize()
        await self.db.set_combat_quickbar(cid, 9, 'spell', 'Ледяное копьё')
        self.assertEqual([row['slot'] for row in await self.db.combat_quickbar(cid)], [5, 9])
        await self.db.initialize()
        self.assertEqual([row['slot'] for row in await self.db.combat_quickbar(cid)], [5, 9])
        with self.assertRaises(ValueError):
            await self.db.set_combat_quickbar(cid, 10, 'attack', 'Обычная атака')

    async def test_spell_ground_targeting_preview_and_failure_do_not_spend_action(self):
        character = {"name": "Маг", "health": 100, "health_max": 100,
                     "attributes": {"Смекалка": 12, "Быстрота": 10},
                     "skills": {"Управление огнём": {"value": 60}}, "talents": []}
        derived = {"attack": {"accuracy": 30}, "effectiveAttributes": character["attributes"]}
        spells = [{"name": "Огненная область", "core": "Огонь", "expression": "Область влияния",
                   "accents": [], "enhancements": []}]
        session = TrainingSession(character_id=1, player_position=(8, 4))
        view = session.view(character, derived, spells, 2)
        action = next(row for row in view["actions"] if row["kind"] == "spell")
        self.assertTrue(action["aims"]["10:2"]["valid"])
        self.assertFalse(action["aims"]["7:3"]["valid"])
        self.assertIn({"x": 10, "y": 4}, action["aims"]["10:2"]["cells"])
        self.assertTrue(session.action_available)
        self.assertFalse(session.cooldowns)
        with self.assertRaises(ValueError):
            session.act({"kind": "spell", "name": spells[0]["name"], "x": -1, "y": 4}, character, derived, spells, 2)
        self.assertTrue(session.action_available)
        self.assertFalse(session.cooldowns)
        self.assertIsNone(session.aim_point)
        with patch('training_combat.random.randint', side_effect=lambda lo, hi: hi):
            result = session.act({"kind": "spell", "name": spells[0]["name"], "x": 10, "y": 2}, character, derived, spells, 2)
        self.assertEqual(result['result'], 'Область создана')
        self.assertEqual(len(session.areas), 1)
        self.assertIn('fatigue',session.conditions['dummy'])
        self.assertEqual(session.target_healths["dummy_right"], 100)
        self.assertFalse(session.action_available)
        self.assertIsNone(session.aim_point)

    async def test_tactical_grid_movement_obstacles_and_initiative(self):
        grid = TacticalGrid(7, 5, {(3, 1), (3, 2), (3, 3)})
        cells = grid.reachable((1, 2), 3, {(2, 2)})
        self.assertNotIn((2, 2), cells)
        self.assertNotIn((4, 2), cells)
        self.assertIn((2, 1), cells)
        self.assertFalse(grid.line_of_sight((1, 2), (5, 2)))
        self.assertEqual(grid.distance((1, 1), (4, 4)), 3)
        self.assertEqual(initiative_bonus(14), 2)
        self.assertIn((2, 2), grid.control_zone({(3, 2)}))
        self.assertIn((5, 2), grid.radius_cells((4, 2), 1))
        cone = grid.cone_cells((1, 2), (6, 2), 4, 90)
        self.assertIn((2, 2), cone)
        self.assertNotIn((4, 2), cone)  # конус не проходит сквозь стену
        self.assertNotIn((0, 2), cone)
        self.assertEqual(grid.cover((1, 2), (5, 2))[0], "полное")
        self.assertEqual(grid.displace((1, 2), (2, 2), 4), (2, 2))  # сразу упирается в стену
        self.assertTrue(grid.can_teleport((1, 2), (2, 4), 3, {(2, 2)}))
        self.assertFalse(grid.can_teleport((1, 2), (2, 2), 3, {(2, 2)}))

    async def test_spell_runtime_uses_real_sigil_modifiers(self):
        profile = spell_runtime_profile({
            "expression": "Дальний удар",
            "accents": ["Точное действие 2", "Мощность 2", "Циклические энергии 2", "Пробивающая сила 2"],
            "enhancements": ["Залпы"],
        }, skill=62, wits=10, cooldown_multiplier=1)
        self.assertEqual(profile["accuracy"], 92)
        self.assertEqual((profile["damage_min"], profile["damage_max"]), (14, 22))
        self.assertEqual(profile["cooldown"], 3)
        self.assertEqual(profile["penetration"], 8)
        self.assertEqual(profile["projectiles"], 3)

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
        self.assertEqual(
            await self.db.equipment_limits(character_id),
            {"weaponSets": 2, "quickSlots": 4, "spellSlots": 4},
        )
        locked, _ = await self.db.equip(character_id, inventory[0]["inventory_id"], "Оружие III — правая рука")
        self.assertFalse(locked)
        await self.db.add_talent(character_id, {
            "tree": "Лидерство", "tier": 0, "name": "Изобилие оружия I", "description": "+1 комплект."
        })
        await self.db.add_talent(character_id, {
            "tree": "Лидерство", "tier": 0, "name": "Патронташ", "description": "+2 быстрых слота."
        })
        self.assertEqual(
            await self.db.equipment_limits(character_id),
            {"weaponSets": 3, "quickSlots": 6, "spellSlots": 4},
        )
        switched, _ = await self.db.set_active_weapon_set(character_id, 3)
        self.assertTrue(switched)
        self.assertEqual((await self.db.get_character_by_id(character_id))["active_weapon_set"], 3)
        success, _ = await self.db.equip(character_id, inventory[0]["inventory_id"], "Оружие I — правая рука")
        self.assertTrue(success)
        await self.db.create_spell(
            character_id, "Грозовая печать", "Молния", "Сосредоточенная сила", ["Дальность"], [], 35
        )
        spell_names = {spell["name"] for spell in await self.db.spells(character_id)}
        self.assertEqual(spell_names, {"Заряженный кулак", "Грозовая печать"})
        spells = await self.db.spells(character_id)
        self.assertEqual({spell["equipped_slot"] for spell in spells}, {1, None})
        reserve = next(spell for spell in spells if spell["equipped_slot"] is None)
        equipped, _ = await self.db.set_spell_equipped(character_id, reserve["id"], True)
        self.assertTrue(equipped)
        self.assertEqual({spell["equipped_slot"] for spell in await self.db.spells(character_id)}, {1, 2})
        unequipped, _ = await self.db.set_spell_equipped(character_id, reserve["id"], False)
        self.assertTrue(unequipped)
        self.assertIsNone(next(spell for spell in await self.db.spells(character_id) if spell["id"] == reserve["id"])["equipped_slot"])
        self.assertTrue(await self.db.update_spell(
            character_id, reserve["id"], "Исправленная печать", "Молния", "Дальний удар",
            ["Точное действие 1"], [], 45,
        ))
        edited = next(spell for spell in await self.db.spells(character_id) if spell["id"] == reserve["id"])
        self.assertEqual(edited["name"], "Исправленная печать")
        self.assertIsNone(edited["equipped_slot"])
        await self.db.add_talent(character_id, {
            "tree": "Магия", "tier": 1, "name": "Расширенный разум I", "description": "+2 ячейки."
        })
        self.assertEqual((await self.db.equipment_limits(character_id))["spellSlots"], 6)
        await self.db.add_talent(character_id, {
            "tree": "Магия", "tier": 4, "name": "Расширенный разум II", "description": "+4 ячейки."
        })
        await self.db.add_talent(character_id, {
            "tree": "Лидерство", "tier": 2, "name": "Арбитр знаний", "description": "+2 ячейки."
        })
        self.assertEqual((await self.db.equipment_limits(character_id))["spellSlots"], 10)
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
        attacker.x, attacker.y = 1, 2
        target.x, target.y = 2, 2
        ally = Combatant(key="c", name="Союзник", team="Герои", health=20, health_max=20, x=3, y=2)
        session.combatants["c"] = ally
        self.assertEqual(session.flanking_bonus(attacker, target), 15)

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

    async def test_sigil_scrolls_starting_spell_and_server_formula_validation(self):
        self.assertEqual(len(SIGIL_LIBRARY), 71)
        self.assertFalse(any(s["key"] == "accent:Прыгающие заряды:3" for s in SIGIL_LIBRARY))
        self.assertTrue(any(s["key"] == "accent:Циклические энергии:4" for s in SIGIL_LIBRARY))
        for sigil in SIGIL_LIBRARY:
            self.assertTrue((Path("web") / sigil["image_url"]).is_file(), sigil["key"])
        character_id = await self.db.create_character(
            111, 222, "Кайрос", "Заклинатель", "Заклинания молний", "Меч и щит",
        )
        known = await self.db.known_sigils(character_id)
        self.assertIn("core:Молния", known)
        self.assertIn("expression:Сосредоточенное намерение", known)
        self.assertIn("Заряженный кулак", {spell["name"] for spell in await self.db.spells(character_id)})
        async with self.db.connect() as db:
            rows = await db.execute_fetchall(
                "SELECT name,source_url FROM item_catalog WHERE source_url LIKE '%Sigil_of_Fire_%' LIMIT 1"
            )
        self.assertEqual(sigil_key_from_scroll_url(rows[0]["source_url"]), "core:Огонь")
        self.assertTrue(await self.db.give_item(character_id, rows[0]["name"]))
        scroll = next(item for item in await self.db.inventory(character_id) if item["name"] == rows[0]["name"])
        ok, _ = await self.db.learn_sigil_from_scroll(character_id, scroll["inventory_id"])
        self.assertTrue(ok)
        known = await self.db.known_sigils(character_id)
        self.assertIn("core:Огонь", known)
        self.assertFalse(any(item["inventory_id"] == scroll["inventory_id"] for item in await self.db.inventory(character_id)))
        formula = validate_formula(
            "core:Огонь", "expression:Сосредоточенное намерение", [], [], known, 99,
        )
        self.assertEqual((formula["default_name"], formula["difficulty"]), ("Горящая ладонь", 15))
        with self.assertRaisesRegex(ValueError, "Сначала изучите"):
            validate_formula("core:Камень", "expression:Сосредоточенное намерение", [], [], known, 99)

    async def test_admin_session_and_full_character_mutations(self):
        character_id = await self.db.create_character(
            555, 777, "Админская проверка", "Книгочей", "Меч и щит", "Короткий лук",
        )
        token = await self.db.create_admin_token(555, 999)
        self.assertEqual(await self.db.admin_token_owner(token), (555, 999))
        self.assertEqual((await self.db.admin_characters(555))[0]["id"], character_id)
        self.assertTrue(await self.db.character_belongs_to_guild(character_id, 555))
        self.assertFalse(await self.db.character_belongs_to_guild(character_id, 556))
        await self.db.admin_update_character(character_id, {
            "name": "Исправленное дело", "attribute_points": 9, "talent_points": 8,
            "health": 17, "health_max": 25, "wounds": 2,
        })
        await self.db.admin_set_skill(character_id, "Знания", 88, 123)
        gained = await self.db.admin_level_up(character_id, 2)
        self.assertEqual(gained, 2)
        await self.db.admin_set_reputation(character_id, "Опальные", 77, 12)
        await self.db.admin_set_sigil(character_id, "core:Огонь", True)
        async with self.db.connect() as db:
            item = (await db.execute_fetchall("SELECT name FROM item_catalog ORDER BY name LIMIT 1"))[0]["name"]
        self.assertTrue(await self.db.admin_give_item(character_id, item, 2))
        await self.db.record_admin_action(555, 999, character_id, "test", {"ok": True})
        character = await self.db.get_character_by_id(character_id)
        self.assertEqual(character["name"], "Исправленное дело")
        self.assertEqual((character["level"], character["attribute_points"], character["talent_points"]), (3, 11, 10))
        self.assertEqual(character["skills"]["Знания"], {"value": 88, "experience": 123})
        self.assertIn("core:Огонь", await self.db.known_sigils(character_id))
        self.assertEqual((await self.db.reputations(character_id))[0]["favor"], 77)
        async with self.db.connect() as db:
            audit = await db.execute_fetchall("SELECT action FROM admin_audit WHERE character_id=?", (character_id,))
        self.assertEqual(audit[0]["action"], "test")


if __name__ == "__main__":
    unittest.main()
