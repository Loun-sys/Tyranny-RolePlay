"""Асинхронное хранилище русской текстовой адаптации Tyranny."""

from __future__ import annotations

import json
import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import aiosqlite

from constants import (
    ATTRIBUTES, BACKGROUND_BONUSES, EQUIPMENT_SLOTS, SKILLS, SKILL_ATTRIBUTES,
    SPECIALIZATION_ABILITIES, SPECIALIZATION_ABILITY_CHOICES, SPECIALIZATION_BONUSES,
)


SCHEMA = """
PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS characters (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    background TEXT NOT NULL,
    specialization_1 TEXT NOT NULL,
    specialization_2 TEXT NOT NULL,
    level INTEGER NOT NULL DEFAULT 1 CHECK(level >= 1),
    experience INTEGER NOT NULL DEFAULT 0 CHECK(experience >= 0),
    health INTEGER NOT NULL DEFAULT 20,
    health_max INTEGER NOT NULL DEFAULT 20,
    wounds INTEGER NOT NULL DEFAULT 0,
    portrait_url TEXT NOT NULL DEFAULT '',
    notes TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(guild_id, user_id)
);
CREATE TABLE IF NOT EXISTS attributes (
    character_id INTEGER NOT NULL REFERENCES characters(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    value INTEGER NOT NULL DEFAULT 10 CHECK(value BETWEEN 1 AND 30),
    PRIMARY KEY(character_id, name)
);
CREATE TABLE IF NOT EXISTS skills (
    character_id INTEGER NOT NULL REFERENCES characters(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    value INTEGER NOT NULL DEFAULT 0 CHECK(value BETWEEN 0 AND 300),
    experience INTEGER NOT NULL DEFAULT 0 CHECK(experience >= 0),
    PRIMARY KEY(character_id, name)
);
CREATE TABLE IF NOT EXISTS talents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    character_id INTEGER NOT NULL REFERENCES characters(id) ON DELETE CASCADE,
    tree_name TEXT NOT NULL,
    tier INTEGER NOT NULL DEFAULT 1,
    name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    UNIQUE(character_id, name)
);
CREATE TABLE IF NOT EXISTS item_catalog (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL COLLATE NOCASE UNIQUE,
    category TEXT NOT NULL DEFAULT 'Прочее',
    slot TEXT NOT NULL DEFAULT '',
    quality TEXT NOT NULL DEFAULT 'Обычное',
    description TEXT NOT NULL DEFAULT '',
    image_url TEXT NOT NULL DEFAULT '',
    source_url TEXT NOT NULL DEFAULT '',
    value INTEGER NOT NULL DEFAULT 0,
    weight REAL NOT NULL DEFAULT 0,
    hands INTEGER NOT NULL DEFAULT 0,
    damage_min INTEGER NOT NULL DEFAULT 0,
    damage_max INTEGER NOT NULL DEFAULT 0,
    armor INTEGER NOT NULL DEFAULT 0,
    recovery REAL NOT NULL DEFAULT 0,
    properties TEXT NOT NULL DEFAULT '{}',
    wiki_page_id INTEGER,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_catalog_category ON item_catalog(category);
CREATE TABLE IF NOT EXISTS inventory (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    character_id INTEGER NOT NULL REFERENCES characters(id) ON DELETE CASCADE,
    item_id INTEGER NOT NULL REFERENCES item_catalog(id) ON DELETE CASCADE,
    quantity INTEGER NOT NULL DEFAULT 1 CHECK(quantity > 0),
    equipped_slot TEXT,
    notes TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_inventory_character ON inventory(character_id);
CREATE UNIQUE INDEX IF NOT EXISTS idx_equipment_slot
ON inventory(character_id, equipped_slot) WHERE equipped_slot IS NOT NULL;
CREATE TABLE IF NOT EXISTS sigils (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL COLLATE NOCASE UNIQUE,
    sigil_type TEXT NOT NULL,
    school TEXT NOT NULL DEFAULT '',
    description TEXT NOT NULL DEFAULT '',
    image_url TEXT NOT NULL DEFAULT '',
    source_url TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS spells (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    character_id INTEGER NOT NULL REFERENCES characters(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    core TEXT NOT NULL,
    expression TEXT NOT NULL,
    accents TEXT NOT NULL DEFAULT '[]',
    enhancements TEXT NOT NULL DEFAULT '[]',
    difficulty INTEGER NOT NULL DEFAULT 0,
    notes TEXT NOT NULL DEFAULT '',
    UNIQUE(character_id, name)
);
CREATE TABLE IF NOT EXISTS reputation (
    character_id INTEGER NOT NULL REFERENCES characters(id) ON DELETE CASCADE,
    faction TEXT NOT NULL,
    favor INTEGER NOT NULL DEFAULT 0 CHECK(favor BETWEEN 0 AND 100),
    wrath INTEGER NOT NULL DEFAULT 0 CHECK(wrath BETWEEN 0 AND 100),
    PRIMARY KEY(character_id, faction)
);
CREATE TABLE IF NOT EXISTS edicts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    region TEXT NOT NULL,
    ending_condition TEXT NOT NULL,
    deadline TEXT NOT NULL DEFAULT '',
    effects TEXT NOT NULL DEFAULT '',
    active INTEGER NOT NULL DEFAULT 1,
    created_by INTEGER NOT NULL,
    UNIQUE(guild_id, name)
);
CREATE TABLE IF NOT EXISTS spires (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    location TEXT NOT NULL DEFAULT '',
    upgrade_name TEXT NOT NULL DEFAULT 'Без улучшения',
    notes TEXT NOT NULL DEFAULT '',
    UNIQUE(guild_id, name)
);
CREATE TABLE IF NOT EXISTS registration_tokens (
    token_hash TEXT PRIMARY KEY,
    guild_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    expires_at TEXT NOT NULL,
    used_at TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_registration_tokens_owner
ON registration_tokens(guild_id, user_id);
"""


class Database:
    def __init__(self, path: Path):
        self.path = path

    @asynccontextmanager
    async def connect(self):
        db = await aiosqlite.connect(self.path)
        db.row_factory = aiosqlite.Row
        await db.execute("PRAGMA foreign_keys = ON")
        try:
            yield db
        finally:
            await db.close()

    async def initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        async with self.connect() as db:
            await db.executescript(SCHEMA)
            # Каноническое русское название Resolve — «Стойкость»; сохраняем значения старых персонажей.
            await db.execute(
                "INSERT OR IGNORE INTO attributes(character_id,name,value) "
                "SELECT character_id,'Стойкость',value FROM attributes WHERE name='Решимость'"
            )
            await db.execute("DELETE FROM attributes WHERE name='Решимость'")
            await db.commit()
            count = int((await db.execute_fetchall("SELECT COUNT(*) AS total FROM item_catalog"))[0]["total"])
        if count == 0:
            bundled = Path(__file__).resolve().parent / "catalog" / "tyranny_catalog.json"
            bundled_english = Path(__file__).resolve().parent / "catalog" / "tyranny_catalog_en_ru.json"
            persistent = self.path.parent / "tyranny_catalog.json"
            # Английский перевод расширяет каталог, русская Wiki имеет приоритет при совпадении названий.
            snapshots = [bundled_english, persistent if persistent.exists() else bundled]
            for snapshot in snapshots:
                if snapshot.exists():
                    await self.upsert_catalog(json.loads(snapshot.read_text(encoding="utf-8")))

    async def create_registration_token(self, guild_id: int, user_id: int, lifetime_minutes: int = 120) -> str:
        """Создать одноразовый секрет регистрации; в БД хранится только его хеш."""
        token = secrets.token_urlsafe(32)
        digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
        expires = datetime.now(timezone.utc) + timedelta(minutes=max(10, lifetime_minutes))
        async with self.connect() as db:
            await db.execute(
                "UPDATE registration_tokens SET used_at=CURRENT_TIMESTAMP WHERE guild_id=? AND user_id=? AND used_at IS NULL",
                (guild_id, user_id),
            )
            await db.execute(
                "INSERT INTO registration_tokens(token_hash,guild_id,user_id,expires_at) VALUES(?,?,?,?)",
                (digest, guild_id, user_id, expires.isoformat()),
            )
            await db.commit()
        return token

    async def registration_token_owner(self, token: str) -> tuple[int, int] | None:
        digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
        async with self.connect() as db:
            rows = await db.execute_fetchall(
                "SELECT guild_id,user_id,expires_at,used_at FROM registration_tokens WHERE token_hash=?", (digest,)
            )
        if not rows or rows[0]["used_at"]:
            return None
        try:
            expires = datetime.fromisoformat(rows[0]["expires_at"])
        except ValueError:
            return None
        if expires <= datetime.now(timezone.utc):
            return None
        return int(rows[0]["guild_id"]), int(rows[0]["user_id"])

    async def consume_registration_token(self, token: str) -> bool:
        digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
        async with self.connect() as db:
            cursor = await db.execute(
                "UPDATE registration_tokens SET used_at=CURRENT_TIMESTAMP WHERE token_hash=? AND used_at IS NULL",
                (digest,),
            )
            await db.commit()
            return bool(cursor.rowcount)

    @staticmethod
    def _skill_base(name: str, attrs: dict[str, int]) -> int:
        primary, secondary = SKILL_ATTRIBUTES[name]
        return round(attrs[primary] * 1.5 + attrs[secondary] * 0.5)

    async def create_character(
        self, guild_id: int, user_id: int, name: str, background: str,
        specialization_1: str, specialization_2: str, abilities: list[str] | None = None,
    ) -> int:
        async with self.connect() as db:
            await db.execute(
                """INSERT INTO characters(guild_id,user_id,name,background,specialization_1,specialization_2)
                   VALUES(?,?,?,?,?,?)
                   ON CONFLICT(guild_id,user_id) DO UPDATE SET
                   name=excluded.name,background=excluded.background,
                   specialization_1=excluded.specialization_1,specialization_2=excluded.specialization_2,
                   updated_at=CURRENT_TIMESTAMP""",
                (guild_id, user_id, name.strip(), background, specialization_1, specialization_2),
            )
            row = await db.execute_fetchall(
                "SELECT id FROM characters WHERE guild_id=? AND user_id=?", (guild_id, user_id)
            )
            character_id = int(row[0]["id"])
            await db.execute("DELETE FROM attributes WHERE character_id=?", (character_id,))
            await db.execute("DELETE FROM skills WHERE character_id=?", (character_id,))
            await db.execute("DELETE FROM talents WHERE character_id=?", (character_id,))
            attrs = {name: 10 for name in ATTRIBUTES}
            await db.executemany(
                "INSERT INTO attributes(character_id,name,value) VALUES(?,?,?)",
                [(character_id, name, value) for name, value in attrs.items()],
            )
            bonuses: dict[str, int] = dict(BACKGROUND_BONUSES.get(background, {}))
            for specialization in (specialization_1, specialization_2):
                for skill, bonus in SPECIALIZATION_BONUSES[specialization].items():
                    bonuses[skill] = bonuses.get(skill, 0) + bonus
            await db.executemany(
                "INSERT INTO skills(character_id,name,value) VALUES(?,?,?)",
                [(character_id, skill, self._skill_base(skill, attrs) + bonuses.get(skill, 0)) for skill in SKILLS],
            )
            selected_abilities = abilities or [
                SPECIALIZATION_ABILITIES[specialization_1], SPECIALIZATION_ABILITIES[specialization_2]
            ]
            valid_abilities = []
            for specialization, ability in zip((specialization_1, specialization_2), selected_abilities):
                chosen = ability if ability in SPECIALIZATION_ABILITY_CHOICES[specialization] else SPECIALIZATION_ABILITIES[specialization]
                if chosen not in valid_abilities:
                    valid_abilities.append(chosen)
            await db.executemany(
                "INSERT INTO talents(character_id,tree_name,tier,name,description) VALUES(?,?,?,?,?)",
                [
                    (character_id, "Специализация", 0, ability, "Стартовая способность, выбранная при создании персонажа.")
                    for ability in valid_abilities
                ],
            )
            await self._recalculate_health(db, character_id)
            await db.commit()
            return character_id

    async def _recalculate_health(self, db: aiosqlite.Connection, character_id: int) -> None:
        rows = await db.execute_fetchall(
            "SELECT value FROM attributes WHERE character_id=? AND name='Живучесть'", (character_id,)
        )
        if not rows:
            return
        level_row = await db.execute_fetchall("SELECT level,health,health_max FROM characters WHERE id=?", (character_id,))
        if not level_row:
            return
        current = level_row[0]
        maximum = 10 + int(rows[0]["value"]) + max(0, int(current["level"]) - 1) * 2
        lost = max(0, int(current["health_max"]) - int(current["health"]))
        await db.execute(
            "UPDATE characters SET health_max=?,health=? WHERE id=?",
            (maximum, max(0, maximum - lost), character_id),
        )

    async def get_character(self, guild_id: int, user_id: int) -> dict[str, Any] | None:
        async with self.connect() as db:
            rows = await db.execute_fetchall(
                "SELECT * FROM characters WHERE guild_id=? AND user_id=?", (guild_id, user_id)
            )
            if not rows:
                return None
            character = dict(rows[0])
            cid = int(character["id"])
            character["attributes"] = {
                row["name"]: int(row["value"])
                for row in await db.execute_fetchall("SELECT name,value FROM attributes WHERE character_id=?", (cid,))
            }
            character["skills"] = {
                row["name"]: {"value": int(row["value"]), "experience": int(row["experience"])}
                for row in await db.execute_fetchall("SELECT name,value,experience FROM skills WHERE character_id=?", (cid,))
            }
            character["talents"] = [
                dict(row) for row in await db.execute_fetchall(
                    "SELECT tree_name,tier,name,description FROM talents WHERE character_id=? ORDER BY tree_name,tier,name", (cid,)
                )
            ]
            return character

    async def delete_character(self, guild_id: int, user_id: int) -> bool:
        async with self.connect() as db:
            cursor = await db.execute("DELETE FROM characters WHERE guild_id=? AND user_id=?", (guild_id, user_id))
            await db.commit()
            return bool(cursor.rowcount)

    async def update_character_text(self, character_id: int, field: str, value: str) -> None:
        if field not in {"portrait_url", "notes", "name"}:
            raise ValueError("Недопустимое поле персонажа")
        async with self.connect() as db:
            await db.execute(f"UPDATE characters SET {field}=?,updated_at=CURRENT_TIMESTAMP WHERE id=?", (value, character_id))
            await db.commit()

    async def set_attribute(self, character_id: int, name: str, value: int) -> None:
        value = max(1, min(30, int(value)))
        async with self.connect() as db:
            await db.execute("UPDATE attributes SET value=? WHERE character_id=? AND name=?", (value, character_id, name))
            attrs = {
                row["name"]: int(row["value"])
                for row in await db.execute_fetchall("SELECT name,value FROM attributes WHERE character_id=?", (character_id,))
            }
            specializations = await db.execute_fetchall(
                "SELECT background,specialization_1,specialization_2 FROM characters WHERE id=?", (character_id,)
            )
            bonuses: dict[str, int] = dict(BACKGROUND_BONUSES.get(specializations[0]["background"], {})) if specializations else {}
            if specializations:
                for specialization in (specializations[0]["specialization_1"], specializations[0]["specialization_2"]):
                    for skill_name, bonus in SPECIALIZATION_BONUSES[specialization].items():
                        bonuses[skill_name] = bonuses.get(skill_name, 0) + bonus
            for skill in SKILLS:
                await db.execute(
                    "UPDATE skills SET value=? WHERE character_id=? AND name=?",
                    (self._skill_base(skill, attrs) + bonuses.get(skill, 0), character_id, skill),
                )
            await self._recalculate_health(db, character_id)
            await db.commit()

    async def set_skill(self, character_id: int, name: str, value: int) -> None:
        async with self.connect() as db:
            await db.execute(
                "UPDATE skills SET value=? WHERE character_id=? AND name=?",
                (max(0, min(300, int(value))), character_id, name),
            )
            await db.commit()

    async def add_skill_experience(self, character_id: int, name: str, amount: int = 1) -> int:
        """Начислить опыт применённому навыку и вернуть его новое значение опыта."""
        async with self.connect() as db:
            await db.execute(
                "UPDATE skills SET experience=experience+? WHERE character_id=? AND name=?",
                (max(0, int(amount)), character_id, name),
            )
            rows = await db.execute_fetchall(
                "SELECT experience FROM skills WHERE character_id=? AND name=?", (character_id, name)
            )
            await db.commit()
            return int(rows[0]["experience"]) if rows else 0

    async def adjust_health(self, character_id: int, delta: int) -> tuple[int, int]:
        async with self.connect() as db:
            rows = await db.execute_fetchall("SELECT health,health_max FROM characters WHERE id=?", (character_id,))
            before, maximum = int(rows[0]["health"]), int(rows[0]["health_max"])
            after = max(0, min(maximum, before + int(delta)))
            await db.execute("UPDATE characters SET health=? WHERE id=?", (after, character_id))
            await db.commit()
            return before, after

    async def adjust_experience(self, character_id: int, delta: int) -> tuple[int, int, int]:
        async with self.connect() as db:
            rows = await db.execute_fetchall("SELECT experience,level FROM characters WHERE id=?", (character_id,))
            experience = max(0, int(rows[0]["experience"]) + int(delta))
            level = max(1, min(21, 1 + experience // 1000))
            await db.execute("UPDATE characters SET experience=?,level=? WHERE id=?", (experience, level, character_id))
            await self._recalculate_health(db, character_id)
            await db.commit()
            return experience, level, (level * 1000)

    async def add_talent(self, character_id: int, talent: dict[str, Any]) -> bool:
        async with self.connect() as db:
            cursor = await db.execute(
                "INSERT OR IGNORE INTO talents(character_id,tree_name,tier,name,description) VALUES(?,?,?,?,?)",
                (character_id, talent["tree"], talent["tier"], talent["name"], talent["description"]),
            )
            await db.commit()
            return bool(cursor.rowcount)

    async def remove_talent(self, character_id: int, name: str) -> bool:
        async with self.connect() as db:
            cursor = await db.execute("DELETE FROM talents WHERE character_id=? AND name=?", (character_id, name))
            await db.commit()
            return bool(cursor.rowcount)

    async def upsert_catalog(self, items: list[dict[str, Any]]) -> int:
        async with self.connect() as db:
            for item in items:
                source_url = item.get("source_url", "")
                if source_url:
                    source_rows = await db.execute_fetchall(
                        "SELECT id,name FROM item_catalog WHERE source_url=?", (source_url,)
                    )
                    if source_rows:
                        row_id = int(source_rows[0]["id"])
                        conflict = await db.execute_fetchall(
                            "SELECT id FROM item_catalog WHERE name=? COLLATE NOCASE AND id<>?",
                            (item["name"], row_id),
                        )
                        name = source_rows[0]["name"] if conflict else item["name"]
                        await db.execute(
                            """UPDATE item_catalog SET name=?,category=?,slot=?,quality=?,description=?,
                               image_url=?,value=?,weight=?,hands=?,damage_min=?,damage_max=?,armor=?,
                               recovery=?,properties=?,wiki_page_id=?,updated_at=CURRENT_TIMESTAMP WHERE id=?""",
                            (
                                name, item.get("category", "Прочее"), item.get("slot", ""),
                                item.get("quality", "Обычное"), item.get("description", ""), item.get("image_url", ""),
                                int(item.get("value", 0) or 0), float(item.get("weight", 0) or 0), int(item.get("hands", 0) or 0),
                                int(item.get("damage_min", 0) or 0), int(item.get("damage_max", 0) or 0),
                                int(item.get("armor", 0) or 0), float(item.get("recovery", 0) or 0),
                                json.dumps(item.get("properties", {}), ensure_ascii=False), item.get("wiki_page_id"), row_id,
                            ),
                        )
                        continue
                await db.execute(
                    """INSERT INTO item_catalog(
                       name,category,slot,quality,description,image_url,source_url,value,weight,hands,
                       damage_min,damage_max,armor,recovery,properties,wiki_page_id)
                       VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                       ON CONFLICT(name) DO UPDATE SET category=excluded.category,slot=excluded.slot,
                       quality=excluded.quality,description=excluded.description,image_url=excluded.image_url,
                       source_url=excluded.source_url,value=excluded.value,weight=excluded.weight,
                       hands=excluded.hands,damage_min=excluded.damage_min,damage_max=excluded.damage_max,
                       armor=excluded.armor,recovery=excluded.recovery,properties=excluded.properties,
                       wiki_page_id=excluded.wiki_page_id,updated_at=CURRENT_TIMESTAMP""",
                    (
                        item["name"], item.get("category", "Прочее"), item.get("slot", ""),
                        item.get("quality", "Обычное"), item.get("description", ""), item.get("image_url", ""),
                        source_url, int(item.get("value", 0) or 0), float(item.get("weight", 0) or 0),
                        int(item.get("hands", 0) or 0), int(item.get("damage_min", 0) or 0),
                        int(item.get("damage_max", 0) or 0), int(item.get("armor", 0) or 0),
                        float(item.get("recovery", 0) or 0), json.dumps(item.get("properties", {}), ensure_ascii=False),
                        item.get("wiki_page_id"),
                    ),
                )
            await db.commit()
            return len(items)

    async def catalog_search(self, query: str = "", category: str = "", limit: int = 25) -> list[dict[str, Any]]:
        async with self.connect() as db:
            clauses, params = [], []
            if query:
                clauses.append("(name LIKE ? OR description LIKE ?)")
                params.extend([f"%{query}%", f"%{query}%"])
            if category:
                clauses.append("category=?")
                params.append(category)
            where = " WHERE " + " AND ".join(clauses) if clauses else ""
            rows = await db.execute_fetchall(
                f"SELECT * FROM item_catalog{where} ORDER BY name LIMIT ?", (*params, max(1, min(100, limit)))
            )
            return [dict(row) for row in rows]

    async def give_item(self, character_id: int, item_name: str, quantity: int = 1) -> bool:
        async with self.connect() as db:
            rows = await db.execute_fetchall("SELECT id,category FROM item_catalog WHERE name=? COLLATE NOCASE", (item_name,))
            if not rows:
                return False
            item_id, category = int(rows[0]["id"]), rows[0]["category"]
            stackable = category in {"Расходуемые предметы", "Зелья", "Еда", "Материалы"}
            if stackable:
                existing = await db.execute_fetchall(
                    "SELECT id FROM inventory WHERE character_id=? AND item_id=? AND equipped_slot IS NULL", (character_id, item_id)
                )
                if existing:
                    await db.execute("UPDATE inventory SET quantity=quantity+? WHERE id=?", (quantity, existing[0]["id"]))
                else:
                    await db.execute("INSERT INTO inventory(character_id,item_id,quantity) VALUES(?,?,?)", (character_id, item_id, quantity))
            else:
                await db.executemany(
                    "INSERT INTO inventory(character_id,item_id,quantity) VALUES(?,?,1)",
                    [(character_id, item_id) for _ in range(max(1, quantity))],
                )
            await db.commit()
            return True

    async def remove_item(self, character_id: int, inventory_id: int, quantity: int = 1) -> bool:
        async with self.connect() as db:
            rows = await db.execute_fetchall(
                "SELECT quantity FROM inventory WHERE id=? AND character_id=?", (inventory_id, character_id)
            )
            if not rows:
                return False
            current = int(rows[0]["quantity"])
            if quantity >= current:
                await db.execute("DELETE FROM inventory WHERE id=?", (inventory_id,))
            else:
                await db.execute("UPDATE inventory SET quantity=quantity-? WHERE id=?", (max(1, quantity), inventory_id))
            await db.commit()
            return True

    async def inventory(self, character_id: int) -> list[dict[str, Any]]:
        async with self.connect() as db:
            rows = await db.execute_fetchall(
                """SELECT inventory.id AS inventory_id,inventory.quantity,inventory.equipped_slot,inventory.notes,
                          item_catalog.* FROM inventory JOIN item_catalog ON item_catalog.id=inventory.item_id
                   WHERE inventory.character_id=? ORDER BY inventory.equipped_slot IS NULL,item_catalog.category,item_catalog.name""",
                (character_id,),
            )
            return [dict(row) for row in rows]

    async def equip(self, character_id: int, inventory_id: int, slot: str) -> tuple[bool, str]:
        if slot not in EQUIPMENT_SLOTS:
            return False, "Неизвестный слот экипировки."
        async with self.connect() as db:
            rows = await db.execute_fetchall(
                """SELECT inventory.id,item_catalog.category,item_catalog.hands FROM inventory
                   JOIN item_catalog ON item_catalog.id=inventory.item_id
                   WHERE inventory.id=? AND inventory.character_id=?""", (inventory_id, character_id)
            )
            if not rows:
                return False, "Предмет не найден в инвентаре."
            category = rows[0]["category"]
            if slot.startswith("Оружие") and category not in {
                "Одноручное оружие", "Двуручное оружие", "Парное оружие", "Луки", "Метательное оружие", "Посохи", "Щиты"
            }:
                return False, "Этот предмет нельзя поместить в оружейный набор."
            if slot in {"Голова", "Торс", "Руки", "Ноги"}:
                if category != "Броня":
                    return False, "В этот слот помещается только броня."
                item_rows = await db.execute_fetchall(
                    "SELECT item_catalog.slot FROM inventory JOIN item_catalog ON item_catalog.id=inventory.item_id WHERE inventory.id=?",
                    (inventory_id,),
                )
                native_slot = item_rows[0]["slot"] if item_rows else ""
                if native_slot and native_slot != slot:
                    return False, f"Этот предмет предназначен для слота «{native_slot}»."
            if slot.startswith("Аксессуар") and category != "Аксессуары":
                return False, "В этот слот помещаются только аксессуары."
            if slot.startswith("Быстрый предмет") and category not in {"Расходуемые предметы", "Зелья", "Еда"}:
                return False, "В быстрый слот помещаются только расходуемые предметы."
            if slot.startswith("Оружие") and "левая рука" in slot:
                right_slot = slot.replace("левая", "правая")
                occupied = await db.execute_fetchall(
                    """SELECT item_catalog.hands FROM inventory JOIN item_catalog ON item_catalog.id=inventory.item_id
                       WHERE inventory.character_id=? AND inventory.equipped_slot=?""",
                    (character_id, right_slot),
                )
                if occupied and int(occupied[0]["hands"] or 0) >= 2:
                    return False, "Правая рука этого набора занята двуручным оружием."
            if int(rows[0]["hands"] or 0) >= 2 and "левая рука" in slot:
                return False, "Двуручное оружие экипируется через слот правой руки и занимает обе руки."
            await db.execute("UPDATE inventory SET equipped_slot=NULL WHERE character_id=? AND equipped_slot=?", (character_id, slot))
            await db.execute("UPDATE inventory SET equipped_slot=? WHERE id=?", (slot, inventory_id))
            if int(rows[0]["hands"] or 0) >= 2 and "правая рука" in slot:
                other = slot.replace("правая", "левая")
                await db.execute("UPDATE inventory SET equipped_slot=NULL WHERE character_id=? AND equipped_slot=?", (character_id, other))
            await db.commit()
            return True, f"Предмет помещён в слот «{slot}»."

    async def unequip(self, character_id: int, inventory_id: int) -> bool:
        async with self.connect() as db:
            cursor = await db.execute(
                "UPDATE inventory SET equipped_slot=NULL WHERE id=? AND character_id=?", (inventory_id, character_id)
            )
            await db.commit()
            return bool(cursor.rowcount)

    async def create_spell(
        self, character_id: int, name: str, core: str, expression: str,
        accents: list[str], enhancements: list[str], difficulty: int, notes: str = "",
    ) -> None:
        async with self.connect() as db:
            await db.execute(
                """INSERT INTO spells(character_id,name,core,expression,accents,enhancements,difficulty,notes)
                   VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(character_id,name) DO UPDATE SET
                   core=excluded.core,expression=excluded.expression,accents=excluded.accents,
                   enhancements=excluded.enhancements,difficulty=excluded.difficulty,notes=excluded.notes""",
                (character_id, name, core, expression, json.dumps(accents, ensure_ascii=False),
                 json.dumps(enhancements, ensure_ascii=False), max(0, difficulty), notes),
            )
            await db.commit()

    async def spells(self, character_id: int) -> list[dict[str, Any]]:
        async with self.connect() as db:
            rows = await db.execute_fetchall("SELECT * FROM spells WHERE character_id=? ORDER BY name", (character_id,))
            result = []
            for row in rows:
                spell = dict(row)
                spell["accents"] = json.loads(spell["accents"])
                spell["enhancements"] = json.loads(spell["enhancements"])
                result.append(spell)
            return result

    async def adjust_reputation(
        self, character_id: int, faction: str, axis: str, delta: int,
    ) -> tuple[int, int]:
        if axis not in {"favor", "wrath"}:
            raise ValueError("Неизвестная шкала репутации")
        async with self.connect() as db:
            await db.execute(
                "INSERT OR IGNORE INTO reputation(character_id,faction) VALUES(?,?)",
                (character_id, faction),
            )
            rows = await db.execute_fetchall(
                f"SELECT {axis} AS value FROM reputation WHERE character_id=? AND faction=?",
                (character_id, faction),
            )
            before = int(rows[0]["value"])
            after = max(0, min(100, before + int(delta)))
            await db.execute(
                f"UPDATE reputation SET {axis}=? WHERE character_id=? AND faction=?",
                (after, character_id, faction),
            )
            await db.commit()
            return before, after

    async def reputations(self, character_id: int) -> list[dict[str, Any]]:
        async with self.connect() as db:
            rows = await db.execute_fetchall(
                "SELECT faction,favor,wrath FROM reputation WHERE character_id=? ORDER BY faction",
                (character_id,),
            )
            return [dict(row) for row in rows]

    async def save_edict(
        self, guild_id: int, name: str, region: str, ending_condition: str,
        deadline: str, effects: str, created_by: int,
    ) -> None:
        async with self.connect() as db:
            await db.execute(
                """INSERT INTO edicts(guild_id,name,region,ending_condition,deadline,effects,created_by)
                   VALUES(?,?,?,?,?,?,?) ON CONFLICT(guild_id,name) DO UPDATE SET
                   region=excluded.region,ending_condition=excluded.ending_condition,
                   deadline=excluded.deadline,effects=excluded.effects,active=1,created_by=excluded.created_by""",
                (guild_id, name, region, ending_condition, deadline, effects, created_by),
            )
            await db.commit()

    async def edicts(self, guild_id: int, active_only: bool = True) -> list[dict[str, Any]]:
        async with self.connect() as db:
            where = " AND active=1" if active_only else ""
            rows = await db.execute_fetchall(
                f"SELECT * FROM edicts WHERE guild_id=?{where} ORDER BY name", (guild_id,)
            )
            return [dict(row) for row in rows]

    async def resolve_edict(self, guild_id: int, name: str) -> bool:
        async with self.connect() as db:
            cursor = await db.execute(
                "UPDATE edicts SET active=0 WHERE guild_id=? AND name=?", (guild_id, name)
            )
            await db.commit()
            return bool(cursor.rowcount)

    async def save_spire(self, guild_id: int, name: str, location: str, upgrade: str, notes: str) -> None:
        async with self.connect() as db:
            await db.execute(
                """INSERT INTO spires(guild_id,name,location,upgrade_name,notes) VALUES(?,?,?,?,?)
                   ON CONFLICT(guild_id,name) DO UPDATE SET location=excluded.location,
                   upgrade_name=excluded.upgrade_name,notes=excluded.notes""",
                (guild_id, name, location, upgrade, notes),
            )
            await db.commit()

    async def spires(self, guild_id: int) -> list[dict[str, Any]]:
        async with self.connect() as db:
            rows = await db.execute_fetchall(
                "SELECT * FROM spires WHERE guild_id=? ORDER BY name", (guild_id,)
            )
            return [dict(row) for row in rows]
