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
from localization import localize_game_text, wiki_category_icon
from sigil_data import SIGILS_BY_KEY, sigil_key_from_scroll_url, starting_sigils_and_spells


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
    attribute_points INTEGER NOT NULL DEFAULT 0,
    talent_points INTEGER NOT NULL DEFAULT 0,
    rewarded_level INTEGER NOT NULL DEFAULT 1,
    active_weapon_set INTEGER NOT NULL DEFAULT 1 CHECK(active_weapon_set BETWEEN 1 AND 4),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(guild_id, user_id)
);
CREATE TABLE IF NOT EXISTS attributes (
    character_id INTEGER NOT NULL REFERENCES characters(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    value INTEGER NOT NULL DEFAULT 10 CHECK(value >= 1),
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
    lore TEXT NOT NULL DEFAULT '',
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
CREATE TABLE IF NOT EXISTS character_sigils (
    character_id INTEGER NOT NULL REFERENCES characters(id) ON DELETE CASCADE,
    sigil_key TEXT NOT NULL,
    learned_from TEXT NOT NULL DEFAULT '',
    learned_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY(character_id, sigil_key)
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
    equipped_slot INTEGER,
    UNIQUE(character_id, name)
);
CREATE TABLE IF NOT EXISTS combat_quickbar (
    character_id INTEGER NOT NULL REFERENCES characters(id) ON DELETE CASCADE,
    slot INTEGER NOT NULL CHECK(slot BETWEEN 1 AND 9),
    action_kind TEXT NOT NULL,
    action_name TEXT NOT NULL,
    PRIMARY KEY(character_id, slot)
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
CREATE TABLE IF NOT EXISTS portal_tokens (
    token_hash TEXT PRIMARY KEY,
    character_id INTEGER NOT NULL REFERENCES characters(id) ON DELETE CASCADE,
    guild_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    expires_at TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_portal_tokens_owner ON portal_tokens(guild_id,user_id);
CREATE TABLE IF NOT EXISTS admin_tokens (
    token_hash TEXT PRIMARY KEY,
    guild_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    expires_at TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_admin_tokens_owner ON admin_tokens(guild_id,user_id);
CREATE TABLE IF NOT EXISTS admin_audit (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id INTEGER NOT NULL,
    admin_user_id INTEGER NOT NULL,
    character_id INTEGER,
    action TEXT NOT NULL,
    details TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
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
            from player_possessions import SCHEMA as POSSESSION_SCHEMA
            await db.executescript(POSSESSION_SCHEMA)
            attribute_schema=await db.execute_fetchall("SELECT sql FROM sqlite_master WHERE name='attributes'")
            if attribute_schema and 'BETWEEN 1 AND 30' in attribute_schema[0]['sql']:
                await db.execute('BEGIN')
                await db.execute('ALTER TABLE attributes RENAME TO attributes_legacy')
                await db.execute('CREATE TABLE attributes(character_id INTEGER NOT NULL REFERENCES characters(id) ON DELETE CASCADE,name TEXT NOT NULL,value INTEGER NOT NULL DEFAULT 10 CHECK(value >= 1),PRIMARY KEY(character_id,name))')
                await db.execute('INSERT INTO attributes SELECT * FROM attributes_legacy')
                await db.execute('DROP TABLE attributes_legacy')
                await db.commit()
            from campaign_store import SCHEMA as CAMPAIGN_SCHEMA
            await db.executescript(CAMPAIGN_SCHEMA)
            from crafting import SCHEMA as CRAFTING_SCHEMA
            await db.executescript(CRAFTING_SCHEMA)
            shop_columns={r['name'] for r in await db.execute_fetchall('PRAGMA table_info(shop_stock)')}
            if 'shop_key' not in shop_columns:
                await db.execute("ALTER TABLE shop_stock ADD COLUMN shop_key TEXT NOT NULL DEFAULT 'custom'")
                await db.commit()
            quickbar_schema = await db.execute_fetchall("SELECT sql FROM sqlite_master WHERE name='combat_quickbar'")
            if quickbar_schema and 'BETWEEN 1 AND 5' in quickbar_schema[0]['sql']:
                # Preserve every binding while widening the legacy SQLite constraint.
                await db.execute('BEGIN')
                await db.execute('ALTER TABLE combat_quickbar RENAME TO combat_quickbar_legacy')
                await db.execute('CREATE TABLE combat_quickbar (character_id INTEGER NOT NULL REFERENCES characters(id) ON DELETE CASCADE, slot INTEGER NOT NULL CHECK(slot BETWEEN 1 AND 9), action_kind TEXT NOT NULL, action_name TEXT NOT NULL, PRIMARY KEY(character_id,slot))')
                await db.execute('INSERT INTO combat_quickbar SELECT * FROM combat_quickbar_legacy')
                await db.execute('DROP TABLE combat_quickbar_legacy')
            columns = {row["name"] for row in await db.execute_fetchall("PRAGMA table_info(characters)")}
            for name, definition in {
                "attribute_points": "INTEGER NOT NULL DEFAULT 0",
                "talent_points": "INTEGER NOT NULL DEFAULT 0",
                "rewarded_level": "INTEGER NOT NULL DEFAULT 1",
                "active_weapon_set": "INTEGER NOT NULL DEFAULT 1",
            }.items():
                if name not in columns:
                    await db.execute(f"ALTER TABLE characters ADD COLUMN {name} {definition}")
            spell_columns = {row["name"] for row in await db.execute_fetchall("PRAGMA table_info(spells)")}
            spell_slots_added = "equipped_slot" not in spell_columns
            if "equipped_slot" not in spell_columns:
                await db.execute("ALTER TABLE spells ADD COLUMN equipped_slot INTEGER")
            item_columns = {row["name"] for row in await db.execute_fetchall("PRAGMA table_info(item_catalog)")}
            if "lore" not in item_columns:
                await db.execute("ALTER TABLE item_catalog ADD COLUMN lore TEXT NOT NULL DEFAULT ''")
            await db.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_spell_equipped_slot "
                "ON spells(character_id,equipped_slot) WHERE equipped_slot IS NOT NULL"
            )
            # Каноническое русское название Resolve — «Стойкость»; сохраняем значения старых персонажей.
            await db.execute(
                "INSERT OR IGNORE INTO attributes(character_id,name,value) "
                "SELECT character_id,'Стойкость',value FROM attributes WHERE name='Решимость'"
            )
            await db.execute("DELETE FROM attributes WHERE name='Решимость'")
            # Старое ручное название школы Vigor заменено официальным «Рвение».
            await db.execute("UPDATE spells SET core='Рвение' WHERE core='Энергия'")
            await db.execute(
                "UPDATE character_sigils SET sigil_key='core:Рвение' WHERE sigil_key='core:Энергия' "
                "AND NOT EXISTS (SELECT 1 FROM character_sigils newer WHERE newer.character_id=character_sigils.character_id AND newer.sigil_key='core:Рвение')"
            )
            await db.execute("DELETE FROM character_sigils WHERE sigil_key='core:Энергия'")
            await db.execute(
                "INSERT OR IGNORE INTO skills(character_id,name,value,experience) "
                "SELECT character_id,'Управление рвением',value,experience FROM skills WHERE name='Управление энергией'"
            )
            await db.execute(
                "UPDATE skills SET value=MAX(value,COALESCE((SELECT old.value FROM skills old "
                "WHERE old.character_id=skills.character_id AND old.name='Управление энергией'),0)), "
                "experience=MAX(experience,COALESCE((SELECT old.experience FROM skills old "
                "WHERE old.character_id=skills.character_id AND old.name='Управление энергией'),0)) "
                "WHERE name='Управление рвением'"
            )
            await db.execute("DELETE FROM skills WHERE name='Управление энергией'")
            await db.execute(
                "UPDATE talents SET name='Рассечение' WHERE name='Режущий удар' "
                "AND NOT EXISTS (SELECT 1 FROM talents newer WHERE newer.character_id=talents.character_id AND newer.name='Рассечение')"
            )
            await db.execute("DELETE FROM talents WHERE name='Режущий удар'")
            await db.execute(
                "INSERT OR IGNORE INTO skills(character_id,name,value,experience) "
                "SELECT id,?,0,0 FROM characters", ("Управление эмоциями",)
            )
            # Старые происхождения переводятся в новые архетипы с личными деревьями развития.
            for old, new in {
                "Боец арены": "Танцующий", "Солдат": "Авангард", "Охотник": "Зверолюд",
                "Беззаконник": "Танцующий", "Подмастерье гильдии": "Книгочей",
                "Боевой маг": "Заклинатель", "Благородный отпрыск": "Авангард", "Дипломат": "Книгочей",
            }.items():
                await db.execute("UPDATE characters SET background=? WHERE background=?", (new, old))
            await db.commit()
        bundled = Path(__file__).resolve().parent / "catalog" / "tyranny_catalog.json"
        bundled_english = Path(__file__).resolve().parent / "catalog" / "tyranny_catalog_en_ru.json"
        persistent = self.path.parent / "tyranny_catalog.json"
        # Обновляем и уже существующую постоянную базу при каждом запуске.
        # Полный двуязычный снимок загружается последним: в нём больше страниц,
        # структурированных характеристик, цен и канонических изображений.
        snapshots = [persistent if persistent.exists() else bundled, bundled_english]
        for snapshot in snapshots:
            if snapshot.exists():
                await self.upsert_catalog(json.loads(snapshot.read_text(encoding="utf-8")))
        # Старые частичные снимки русской Wiki могли создавать дубли с иным
        # переводом названия. Полный английский снимок является каноническим;
        # неиспользуемые старые wiki-записи безопасно убираются, предметы в
        # инвентарях сохраняются.
        if bundled_english.exists():
            full_items = json.loads(bundled_english.read_text(encoding="utf-8"))
            source_urls = [item.get("source_url", "") for item in full_items if item.get("source_url")]
            async with self.connect() as db:
                if source_urls:
                    placeholders = ",".join("?" for _ in source_urls)
                    await db.execute(
                        f"""DELETE FROM item_catalog
                            WHERE source_url LIKE 'https://tyranny.fandom.com/%'
                              AND source_url NOT IN ({placeholders})
                              AND NOT EXISTS (SELECT 1 FROM inventory WHERE inventory.item_id=item_catalog.id)
                              AND NOT EXISTS (SELECT 1 FROM shop_stock WHERE shop_stock.item_id=item_catalog.id)
                              AND NOT EXISTS (SELECT 1 FROM commerce_log WHERE commerce_log.item_id=item_catalog.id)""",
                        source_urls,
                    )
                missing = await db.execute_fetchall(
                    "SELECT id,category FROM item_catalog WHERE image_url='' OR image_url IS NULL"
                )
                for row in missing:
                    await db.execute(
                        "UPDATE item_catalog SET image_url=? WHERE id=?",
                        (wiki_category_icon(row["category"]), row["id"]),
                    )
                await db.commit()
        game_items = Path(__file__).resolve().parent / 'catalog' / 'game_items.json'
        if game_items.exists():
            from crafting import normalize_quality
            await self.upsert_catalog([normalize_quality(i) for i in json.loads(game_items.read_text(encoding='utf-8'))])
        # Repair persisted crafted variants too, without changing IDs, inventory,
        # prices or the upgraded numerical quality values.
        async with self.connect() as db:
            from item_texts import normalize_item_text
            rows = await db.execute_fetchall('SELECT * FROM item_catalog')
            for row in rows:
                item = normalize_item_text(dict(row))
                from crafting import normalize_quality
                item = normalize_quality(item)
                await db.execute('UPDATE item_catalog SET description=?,lore=?,properties=?,armor=?,damage_min=?,damage_max=?,recovery=?,category=?,hands=?,slot=? WHERE id=?',
                    (item['description'],item['lore'],json.dumps(item['properties'],ensure_ascii=False),item['armor'],item['damage_min'],item['damage_max'],item['recovery'],item['category'],item['hands'],item['slot'],row['id']))
            await db.commit()
        from npc_store import SCHEMA as NPC_SCHEMA
        async with self.connect() as db:
            await db.executescript(NPC_SCHEMA)
            await db.execute("""UPDATE inventory SET equipped_slot=NULL WHERE character_id IN
                (SELECT id FROM characters WHERE background='Зверолюд') AND item_id IN
                (SELECT id FROM item_catalog WHERE category='Броня') AND equipped_slot IN ('Голова','Торс','Руки','Ноги')""")
            await db.commit()
        from master_update import apply_master_update
        await apply_master_update(self,int(__import__('os').getenv('DISCORD_GUILD_ID','0') or 0))
        await self.ensure_starting_sigils()
        if spell_slots_added:
            async with self.connect() as db:
                character_rows = await db.execute_fetchall("SELECT id FROM characters")
            for row in character_rows:
                await self.normalize_spell_slots(int(row["id"]), fill_empty=True)

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

    async def create_portal_token(self, guild_id: int, user_id: int, lifetime_days: int = 30) -> str | None:
        """Создать отзываемую ссылку кабинета; открытый токен никогда не хранится в БД."""
        async with self.connect() as db:
            rows = await db.execute_fetchall(
                "SELECT id FROM characters WHERE guild_id=? AND user_id=?", (guild_id, user_id)
            )
            if not rows:
                return None
            token = secrets.token_urlsafe(36)
            digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
            expires = datetime.now(timezone.utc) + timedelta(days=max(1, lifetime_days))
            await db.execute("DELETE FROM portal_tokens WHERE guild_id=? AND user_id=?", (guild_id, user_id))
            await db.execute(
                "INSERT INTO portal_tokens(token_hash,character_id,guild_id,user_id,expires_at) VALUES(?,?,?,?,?)",
                (digest, int(rows[0]["id"]), guild_id, user_id, expires.isoformat()),
            )
            await db.commit()
            return token

    async def portal_character_id(self, token: str) -> int | None:
        digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
        async with self.connect() as db:
            rows = await db.execute_fetchall(
                "SELECT character_id,expires_at FROM portal_tokens WHERE token_hash=?", (digest,)
            )
        if not rows:
            return None
        try:
            if datetime.fromisoformat(rows[0]["expires_at"]) <= datetime.now(timezone.utc):
                return None
        except ValueError:
            return None
        return int(rows[0]["character_id"])

    async def create_admin_token(self, guild_id: int, user_id: int, lifetime_hours: int = 8) -> str:
        token = secrets.token_urlsafe(48)
        digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
        expires = datetime.now(timezone.utc) + timedelta(hours=max(1, min(24, lifetime_hours)))
        async with self.connect() as db:
            await db.execute("DELETE FROM admin_tokens WHERE guild_id=? AND user_id=?", (guild_id, user_id))
            await db.execute(
                "INSERT INTO admin_tokens(token_hash,guild_id,user_id,expires_at) VALUES(?,?,?,?)",
                (digest, guild_id, user_id, expires.isoformat()),
            )
            await db.commit()
        return token

    async def admin_token_owner(self, token: str) -> tuple[int, int] | None:
        digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
        async with self.connect() as db:
            rows = await db.execute_fetchall(
                "SELECT guild_id,user_id,expires_at FROM admin_tokens WHERE token_hash=?", (digest,)
            )
        if not rows:
            return None
        try:
            if datetime.fromisoformat(rows[0]["expires_at"]) <= datetime.now(timezone.utc):
                return None
        except ValueError:
            return None
        return int(rows[0]["guild_id"]), int(rows[0]["user_id"])

    async def admin_characters(self, guild_id: int) -> list[dict[str, Any]]:
        async with self.connect() as db:
            rows = await db.execute_fetchall(
                """SELECT id,user_id,name,background,specialization_1,specialization_2,level,
                          experience,health,health_max,portrait_url,updated_at
                   FROM characters WHERE guild_id=? ORDER BY name""", (guild_id,)
            )
        return [dict(row) for row in rows]

    async def character_belongs_to_guild(self, character_id: int, guild_id: int) -> bool:
        async with self.connect() as db:
            rows = await db.execute_fetchall(
                "SELECT 1 FROM characters WHERE id=? AND guild_id=?", (character_id, guild_id)
            )
        return bool(rows)

    async def record_admin_action(
        self, guild_id: int, admin_user_id: int, character_id: int | None,
        action: str, details: dict[str, Any],
    ) -> None:
        async with self.connect() as db:
            await db.execute(
                "INSERT INTO admin_audit(guild_id,admin_user_id,character_id,action,details) VALUES(?,?,?,?,?)",
                (guild_id, admin_user_id, character_id, action, json.dumps(details, ensure_ascii=False)[:4000]),
            )
            await db.commit()

    @staticmethod
    def _skill_base(name: str, attrs: dict[str, int]) -> int:
        primary, secondary = SKILL_ATTRIBUTES[name]
        return round(attrs[primary] * 1.5 + attrs[secondary] * 0.5)

    @staticmethod
    def _item_consumes_slot(name: str, category: str, weight: float, equipped_slot: str | None = None) -> bool:
        tiny = ("чернил", "перо", "ключ", "руна", "самоцвет", "записка")
        return (
            (not equipped_slot or equipped_slot=='Мастерская') and category not in {"Материалы", "Сигилы"}
            and not any(part in name.casefold() for part in tiny)
            and not (0 < float(weight or 0) <= .25)
        )

    @staticmethod
    def _equipment_limits_from_talents(names: set[str]) -> dict[str, int]:
        from ability_rules import resolve
        import re
        bonuses={}
        for name in names:
            row=resolve(name)
            if not row or not row['passive'] or row.get('modal') or row.get('isTalentUpgrade'):continue
            family=re.sub(r'_(?:\d+of\d+|\d{2})$','',row['key'])
            for node in row['nodes']:
                if node['side']!='self' or node['phase']!='root':continue
                for effect in node['statuses']:
                    stat=effect['AffectsStat']
                    if stat not in {2122,2123,2133,2161}:continue
                    if effect.get('ApplicationPrerequisites') or effect.get('TriggerAdjustment',{}).get('Type'):continue
                    identity=(family,stat);bonuses[identity]=max(bonuses.get(identity,0),round(effect['Value']))
        total=lambda stats:sum(v for (_,stat),v in bonuses.items() if stat in stats)
        return {'weaponSets':min(4,2+total({2122})), 'quickSlots':4+total({2123}),
                'spellSlots':4+total({2133,2161})}

    async def equipment_limits(self, character_id: int) -> dict[str, int]:
        async with self.connect() as db:
            rows = await db.execute_fetchall("SELECT name FROM talents WHERE character_id=?", (character_id,))
            equipped = await db.execute_fetchall(
                """SELECT inventory.equipped_slot,item_catalog.name,item_catalog.source_url,item_catalog.properties
                   FROM inventory JOIN item_catalog ON item_catalog.id=inventory.item_id
                   WHERE inventory.character_id=? AND inventory.equipped_slot IS NOT NULL""", (character_id,)
            )
        limits = self._equipment_limits_from_talents({str(row["name"]) for row in rows})
        from item_effects import active_equipment,equip_bonuses
        character=await self.get_character_by_id(character_id)
        equipped=active_equipment([dict(i) for i in equipped],character.get('active_weapon_set',1))
        for item in equipped:
            original=equip_bonuses(item)
            limits['spellSlots']+=round(original.get('Ячейки заклинаний',0))
            limits['weaponSets']+=round(original.get('Комплекты оружия',0))
            limits['quickSlots']+=round(original.get('Быстрые предметы',0))
            if original.get('Ячейки заклинаний') or __import__('item_effects').game_data(item).get('statsVersion')==2:continue
            source = str(item["source_url"] or "").casefold()
            properties = str(item["properties"] or "").casefold()
            name = str(item["name"] or "").casefold()
            if (
                "kailor" in source or "каилор" in name or "spell slot" in properties
                or ("ячейк" in properties and "заклин" in properties)
            ):
                limits["spellSlots"] += 1
        limits["spellSlots"] = min(11, limits["spellSlots"])
        limits['weaponSets']=min(4,limits['weaponSets'])
        return limits

    async def set_active_weapon_set(self, character_id: int, number: int) -> tuple[bool, str]:
        number = int(number)
        limits = await self.equipment_limits(character_id)
        if number < 1 or number > limits["weaponSets"]:
            return False, "Этот комплект оружия ещё не открыт талантом «Изобилие оружия»."
        async with self.connect() as db:
            cursor = await db.execute(
                "UPDATE characters SET active_weapon_set=?,updated_at=CURRENT_TIMESTAMP WHERE id=?",
                (number, character_id),
            )
            await db.commit()
        return bool(cursor.rowcount), f"Активирован комплект оружия {('I', 'II', 'III', 'IV')[number - 1]}."

    async def create_character(
        self, guild_id: int, user_id: int, name: str, background: str,
        specialization_1: str, specialization_2: str, abilities: list[str] | None = None,
        *, allocate_start_bonus: bool = True,
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
            await db.execute("DELETE FROM spells WHERE character_id=?", (character_id,))
            await db.execute("DELETE FROM character_sigils WHERE character_id=?", (character_id,))
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
            await self._insert_starting_sigils(db, character_id, (specialization_1, specialization_2))
            await self._recalculate_health(db, character_id)
            from player_possessions import grant_start
            await grant_start(db, character_id, background,allocate_start_bonus)
            await db.commit()
        await self.normalize_spell_slots(character_id, fill_empty=True)
        return character_id

    @staticmethod
    async def _insert_starting_sigils(
        db: aiosqlite.Connection, character_id: int, specializations: tuple[str, str] | list[str],
    ) -> None:
        known, spells = starting_sigils_and_spells(specializations)
        await db.executemany(
            "INSERT OR IGNORE INTO character_sigils(character_id,sigil_key,learned_from) VALUES(?,?,?)",
            [(character_id, key, "Старт персонажа") for key in sorted(known)],
        )
        await db.executemany(
            """INSERT OR IGNORE INTO spells(
               character_id,name,core,expression,accents,enhancements,difficulty,notes)
               VALUES(?,?,?,?,?,?,?,?)""",
            [
                (
                    character_id, spell["name"], spell["core"], spell["expression"],
                    "[]", "[]", spell["difficulty"], "Стартовая формула специализации.",
                )
                for spell in spells
            ],
        )

    async def ensure_starting_sigils(self) -> None:
        """Дополнить старые сохранения обязательным выражением и стартовой магией."""
        async with self.connect() as db:
            rows = await db.execute_fetchall("SELECT id,specialization_1,specialization_2 FROM characters")
            for row in rows:
                await self._insert_starting_sigils(
                    db, int(row["id"]), (str(row["specialization_1"]), str(row["specialization_2"])),
                )
            await db.commit()

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

    async def get_character_by_id(self, character_id: int) -> dict[str, Any] | None:
        async with self.connect() as db:
            rows = await db.execute_fetchall("SELECT guild_id,user_id FROM characters WHERE id=?", (character_id,))
        if not rows:
            return None
        return await self.get_character(int(rows[0]["guild_id"]), int(rows[0]["user_id"]))

    async def archive_characters(self) -> list[dict[str, Any]]:
        async with self.connect() as db:
            rows = await db.execute_fetchall(
                """SELECT id,name,background,specialization_1,specialization_2,level,portrait_url,updated_at
                   FROM characters ORDER BY updated_at DESC,name"""
            )
            return [dict(row) for row in rows]

    async def delete_character(self, guild_id: int, user_id: int, *,
                               expected_character_id: int | None = None,
                               admin_user_id: int | None = None) -> bool:
        """Delete the confirmed owner/character atomically, retaining an audit entry."""
        async with self.connect() as db:
            await db.execute('BEGIN IMMEDIATE')
            rows = await db.execute_fetchall('SELECT id,name,background,level FROM characters WHERE guild_id=? AND user_id=?', (guild_id, user_id))
            if not rows or (expected_character_id is not None and rows[0]['id'] != expected_character_id):
                return False
            character = dict(rows[0])
            # Map placements are JSON, not foreign keys. Remove only this player's
            # placements; maps, NPCs and other players remain intact.
            for row in await db.execute_fetchall('SELECT id,spec FROM battle_maps WHERE guild_id=?', (guild_id,)):
                spec = json.loads(row['spec'])
                tokens = spec.get('tokens', [])
                remaining = [t for t in tokens if not (t.get('kind') == 'player' and t.get('id') == character['id'])]
                if len(remaining) != len(tokens):
                    spec['tokens'] = remaining
                    await db.execute('UPDATE battle_maps SET spec=?,updated_at=CURRENT_TIMESTAMP WHERE id=?', (json.dumps(spec, ensure_ascii=False), row['id']))
            await db.execute('DELETE FROM registration_tokens WHERE guild_id=? AND user_id=?', (guild_id, user_id))
            await db.execute('INSERT INTO admin_audit(guild_id,admin_user_id,character_id,action,details) VALUES(?,?,?,?,?)',
                             (guild_id, admin_user_id if admin_user_id is not None else user_id, character['id'],
                              'character_delete_admin' if admin_user_id is not None else 'character_delete_self',
                              json.dumps({**character, 'user_id': str(user_id)}, ensure_ascii=False)))
            # All character-owned tables (including portal links) cascade here.
            cursor = await db.execute('DELETE FROM characters WHERE id=? AND guild_id=? AND user_id=?', (character['id'], guild_id, user_id))
            await db.commit()
            return bool(cursor.rowcount)

    async def update_character_text(self, character_id: int, field: str, value: str) -> None:
        if field not in {"portrait_url", "notes", "name"}:
            raise ValueError("Недопустимое поле персонажа")
        async with self.connect() as db:
            await db.execute(f"UPDATE characters SET {field}=?,updated_at=CURRENT_TIMESTAMP WHERE id=?", (value, character_id))
            await db.commit()

    async def set_attribute(self, character_id: int, name: str, value: int) -> None:
        async with self.connect() as db:
            origin=await db.execute_fetchall('SELECT background FROM characters WHERE id=?',(character_id,))
            value=max(1,int(value)) if origin and origin[0]['background']=='Зверолюд' else max(1,min(30,int(value)))
            old_attrs = {
                row["name"]: int(row["value"])
                for row in await db.execute_fetchall("SELECT name,value FROM attributes WHERE character_id=?", (character_id,))
            }
            await db.execute("UPDATE attributes SET value=? WHERE character_id=? AND name=?", (value, character_id, name))
            attrs = {
                row["name"]: int(row["value"])
                for row in await db.execute_fetchall("SELECT name,value FROM attributes WHERE character_id=?", (character_id,))
            }
            for skill in SKILLS:
                delta = self._skill_base(skill, attrs) - self._skill_base(skill, old_attrs)
                await db.execute(
                    "UPDATE skills SET value=MAX(0,MIN(300,value+?)) WHERE character_id=? AND name=?",
                    (delta, character_id, skill),
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

    async def admin_set_skill(self, character_id: int, name: str, value: int, experience: int) -> None:
        async with self.connect() as db:
            await db.execute(
                "UPDATE skills SET value=?,experience=? WHERE character_id=? AND name=?",
                (max(0, min(300, int(value))), max(0, int(experience)), character_id, name),
            )
            await db.commit()

    async def admin_update_character(self, character_id: int, values: dict[str, Any]) -> None:
        allowed = {
            "name", "background", "specialization_1", "specialization_2", "level", "experience",
            "health", "health_max", "wounds", "portrait_url", "notes", "attribute_points",
            "talent_points", "active_weapon_set",
        }
        clean = {key: value for key, value in values.items() if key in allowed}
        if not clean:
            return
        numeric_bounds = {
            "level": (1, 99), "experience": (0, 99_000_000), "health": (0, 99_999),
            "health_max": (1, 99_999), "wounds": (0, 999), "attribute_points": (0, 999),
            "talent_points": (0, 999), "active_weapon_set": (1, 4),
        }
        for key, (minimum, maximum) in numeric_bounds.items():
            if key in clean:
                clean[key] = max(minimum, min(maximum, int(clean[key])))
        for key in ("name", "background", "specialization_1", "specialization_2", "portrait_url", "notes"):
            if key in clean:
                clean[key] = str(clean[key]).strip()[:2000 if key == "notes" else 1000]
        if "health" in clean and "health_max" in clean:
            clean["health"] = min(clean["health"], clean["health_max"])
        assignments = ",".join(f"{key}=?" for key in clean)
        async with self.connect() as db:
            await db.execute(
                f"UPDATE characters SET {assignments},updated_at=CURRENT_TIMESTAMP WHERE id=?",
                (*clean.values(), character_id),
            )
            if clean.get('background')=='Зверолюд':
                await db.execute("""UPDATE inventory SET equipped_slot=NULL WHERE character_id=? AND item_id IN
                    (SELECT id FROM item_catalog WHERE category='Броня') AND equipped_slot IN ('Голова','Торс','Руки','Ноги')""",(character_id,))
            await db.commit()

    async def admin_level_up(self, character_id: int, amount: int = 1) -> int:
        amount = max(1, min(20, int(amount)))
        async with self.connect() as db:
            rows = await db.execute_fetchall("SELECT level,experience FROM characters WHERE id=?", (character_id,))
            if not rows:
                return 0
            before = int(rows[0]["level"])
            after = min(99, before + amount)
            gained = after - before
            experience = max(int(rows[0]["experience"]), (after - 1) * 1000)
            await db.execute(
                """UPDATE characters SET level=?,experience=?,rewarded_level=MAX(rewarded_level,?),
                   attribute_points=attribute_points+?,talent_points=talent_points+?,updated_at=CURRENT_TIMESTAMP
                   WHERE id=?""",
                (after, experience, after, gained, gained, character_id),
            )
            await self._recalculate_health(db, character_id)
            await db.commit()
        return gained

    async def admin_set_reputation(self, character_id: int, faction: str, favor: int, wrath: int) -> None:
        async with self.connect() as db:
            await db.execute(
                """INSERT INTO reputation(character_id,faction,favor,wrath) VALUES(?,?,?,?)
                   ON CONFLICT(character_id,faction) DO UPDATE SET favor=excluded.favor,wrath=excluded.wrath""",
                (character_id, faction, max(0, min(100, int(favor))), max(0, min(100, int(wrath)))),
            )
            await db.commit()

    async def admin_set_sigil(self, character_id: int, sigil_key: str, known: bool) -> None:
        async with self.connect() as db:
            if known:
                await db.execute(
                    "INSERT OR IGNORE INTO character_sigils(character_id,sigil_key,learned_from) VALUES(?,?,?)",
                    (character_id, sigil_key, "Выдано администратором"),
                )
            else:
                await db.execute(
                    "DELETE FROM character_sigils WHERE character_id=? AND sigil_key=?", (character_id, sigil_key)
                )
            await db.commit()

    async def delete_spell(self, character_id: int, spell_id: int) -> bool:
        async with self.connect() as db:
            cursor = await db.execute(
                "DELETE FROM spells WHERE id=? AND character_id=?", (spell_id, character_id)
            )
            await db.commit()
            return bool(cursor.rowcount)

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
            rows = await db.execute_fetchall(
                "SELECT experience,level,rewarded_level FROM characters WHERE id=?", (character_id,)
            )
            experience = max(0, int(rows[0]["experience"]) + int(delta))
            level = max(1, min(99, 1 + experience // 1000))
            rewarded = int(rows[0]["rewarded_level"])
            gained = max(0, level - rewarded)
            await db.execute(
                """UPDATE characters SET experience=?,level=?,rewarded_level=MAX(rewarded_level,?),
                   attribute_points=attribute_points+?,talent_points=talent_points+?,updated_at=CURRENT_TIMESTAMP
                   WHERE id=?""",
                (experience, level, level, gained, gained, character_id),
            )
            await self._recalculate_health(db, character_id)
            await db.commit()
            return experience, level, (level * 1000)

    async def spend_attribute_point(self, character_id: int, name: str) -> tuple[bool, str]:
        if name not in ATTRIBUTES:
            return False, "Неизвестная характеристика."
        async with self.connect() as db:
            await db.execute("BEGIN IMMEDIATE")
            rows = await db.execute_fetchall(
                """SELECT attributes.value,characters.attribute_points,characters.background FROM attributes
                   JOIN characters ON characters.id=attributes.character_id
                   WHERE attributes.character_id=? AND attributes.name=?""", (character_id, name)
            )
            if not rows:
                await db.rollback(); return False, "Характеристика не найдена."
            current, points = int(rows[0]["value"]), int(rows[0]["attribute_points"])
            cost = 1 + max(0, current - 9) // 10
            if current >= 30 and rows[0]['background']!='Зверолюд':
                await db.rollback(); return False, "Достигнут предел характеристики."
            if points < cost:
                await db.rollback(); return False, f"Нужно очков: {cost}; доступно: {points}."
            old_attrs = {
                row["name"]: int(row["value"])
                for row in await db.execute_fetchall("SELECT name,value FROM attributes WHERE character_id=?", (character_id,))
            }
            new_attrs = dict(old_attrs)
            new_attrs[name] = current + 1
            await db.execute("UPDATE characters SET attribute_points=attribute_points-? WHERE id=?", (cost, character_id))
            await db.execute("UPDATE attributes SET value=? WHERE character_id=? AND name=?", (current + 1, character_id, name))
            for skill in SKILLS:
                delta = self._skill_base(skill, new_attrs) - self._skill_base(skill, old_attrs)
                await db.execute(
                    "UPDATE skills SET value=MAX(0,MIN(300,value+?)) WHERE character_id=? AND name=?",
                    (delta, character_id, skill),
                )
            await self._recalculate_health(db, character_id)
            await db.commit()
        return True, f"{name}: {current} → {current + 1}. Потрачено очков: {cost}."

    async def spend_talent_point(self, character_id: int, talent: dict[str, Any]) -> tuple[bool, str]:
        async with self.connect() as db:
            await db.execute("BEGIN IMMEDIATE")
            character = await db.execute_fetchall("SELECT talent_points FROM characters WHERE id=?", (character_id,))
            if not character or int(character[0]["talent_points"]) < 1:
                await db.rollback(); return False, "Нет свободных очков талантов."
            from ability_rules import resolve
            requested_source=resolve(talent)
            all_owned=await db.execute_fetchall('SELECT name FROM talents WHERE character_id=?',(character_id,))
            owned=[row for row in all_owned if row['name'] in {talent['name'],talent.get('legacyName')} or
                   (requested_source and (resolve(row['name']) or {}).get('key')==requested_source['key'])]
            if owned:
                await db.rollback(); return False, "Этот талант уже изучен."
            tree_points = int((await db.execute_fetchall(
                "SELECT COUNT(*) AS total FROM talents WHERE character_id=? AND tree_name=?",
                (character_id, talent["tree"]),
            ))[0]["total"])
            if tree_points < int(talent["tier"]):
                await db.rollback(); return False, f"Сначала вложите {talent['tier']} очк. в ветку «{talent['tree']}»."
            await db.execute(
                "INSERT INTO talents(character_id,tree_name,tier,name,description) VALUES(?,?,?,?,?)",
                (character_id, talent["tree"], talent["tier"], talent["name"], talent["description"]),
            )
            await db.execute("UPDATE characters SET talent_points=talent_points-1 WHERE id=?", (character_id,))
            await db.commit()
            return True, f"Изучен талант «{talent['name']}»."

    async def effective_skill_in_connection(self,db,character_id,name):
        from item_effects import active_equipment,equip_bonuses
        skill=await db.execute_fetchall('SELECT value FROM skills WHERE character_id=? AND name=?',(character_id,name))
        actor=await db.execute_fetchall('SELECT active_weapon_set FROM characters WHERE id=?',(character_id,))
        items=await db.execute_fetchall('SELECT inventory.equipped_slot,item_catalog.category,item_catalog.properties FROM inventory JOIN item_catalog ON inventory.item_id=item_catalog.id WHERE inventory.character_id=? AND inventory.equipped_slot IS NOT NULL',(character_id,))
        talents=await db.execute_fetchall('SELECT name FROM talents WHERE character_id=?',(character_id,))
        attrs={r['name']:r['value'] for r in await db.execute_fetchall('SELECT name,value FROM attributes WHERE character_id=?',(character_id,))}
        from ability_rules import passive_equipment
        from talent_runtime import attribute_skill_delta
        inventory=[dict(i) for i in items];active_set=actor[0]['active_weapon_set'] if actor else 1
        equipped=active_equipment(inventory+passive_equipment([dict(t) for t in talents],inventory,active_set),active_set)
        bonuses=[equip_bonuses(i) for i in equipped]
        effective={k:v+sum(b.get(k,0) for b in bonuses) for k,v in attrs.items()}
        bonus=sum(b.get(name,0) for b in bonuses)+attribute_skill_delta(name,attrs,effective)
        return max(0,round((skill[0]['value'] if skill else 0)+bonus))

    async def inventory_capacity(self, character_id: int) -> dict[str, int]:
        async with self.connect() as db:
            athletics=await self.effective_skill_in_connection(db,character_id,'Атлетика')
            rows = await db.execute_fetchall(
                """SELECT inventory.equipped_slot,item_catalog.category,item_catalog.name,item_catalog.weight
                   FROM inventory JOIN item_catalog ON item_catalog.id=inventory.item_id
                   WHERE inventory.character_id=?""", (character_id,)
            )
        capacity = min(40, 8 + athletics // 5)
        return {
            "used": sum(1 for row in rows if self._item_consumes_slot(
                row["name"], row["category"], row["weight"], row["equipped_slot"]
            )),
            "capacity": capacity, "athletics": athletics,
        }

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
            for source_item in items:
                from item_texts import normalize_item_text
                item = normalize_item_text(source_item)
                item["name"] = localize_game_text(str(item.get("name", ""))).replace("Tyranny", "Тирания")
                item["description"] = localize_game_text(str(item.get("description", ""))).replace("Tyranny", "Тирания")
                item["lore"] = localize_game_text(str(item.get("lore", ""))).replace("Tyranny", "Тирания")
                item["properties"] = {
                    localize_game_text(str(key)): value if key == 'gameData' else localize_game_text(str(value)).replace("Tyranny", "Тирания")
                    for key, value in dict(item.get("properties") or {}).items()
                    if key not in {"Техническое исходное название", "Игровой ID", "Непереведённый исходный эффект"}
                }
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
                            """UPDATE item_catalog SET name=?,category=?,slot=?,quality=?,description=?,lore=?,
                               image_url=?,value=?,weight=?,hands=?,damage_min=?,damage_max=?,armor=?,
                               recovery=?,properties=?,wiki_page_id=?,updated_at=CURRENT_TIMESTAMP WHERE id=?""",
                            (
                                name, item.get("category", "Прочее"), item.get("slot", ""),
                                item.get("quality", "Обычное"), item.get("description", ""), item.get("lore", ""), item.get("image_url", ""),
                                int(item.get("value", 0) or 0), float(item.get("weight", 0) or 0), int(item.get("hands", 0) or 0),
                                int(item.get("damage_min", 0) or 0), int(item.get("damage_max", 0) or 0),
                                float(item.get("armor", 0) or 0), float(item.get("recovery", 0) or 0),
                                json.dumps(item.get("properties", {}), ensure_ascii=False), item.get("wiki_page_id"), row_id,
                            ),
                        )
                        continue
                await db.execute(
                    """INSERT INTO item_catalog(
                       name,category,slot,quality,description,lore,image_url,source_url,value,weight,hands,
                       damage_min,damage_max,armor,recovery,properties,wiki_page_id)
                       VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                       ON CONFLICT(name) DO UPDATE SET category=excluded.category,slot=excluded.slot,
                       quality=excluded.quality,description=excluded.description,lore=excluded.lore,
                       image_url=CASE WHEN excluded.image_url='' THEN item_catalog.image_url ELSE excluded.image_url END,
                       source_url=excluded.source_url,value=excluded.value,weight=excluded.weight,
                       hands=excluded.hands,damage_min=excluded.damage_min,damage_max=excluded.damage_max,
                       armor=excluded.armor,recovery=excluded.recovery,properties=excluded.properties,
                       wiki_page_id=excluded.wiki_page_id,updated_at=CURRENT_TIMESTAMP""",
                    (
                        item["name"], item.get("category", "Прочее"), item.get("slot", ""),
                        item.get("quality", "Обычное"), item.get("description", ""), item.get("lore", ""), item.get("image_url", ""),
                        source_url, int(item.get("value", 0) or 0), float(item.get("weight", 0) or 0),
                        int(item.get("hands", 0) or 0), int(item.get("damage_min", 0) or 0),
                        int(item.get("damage_max", 0) or 0), float(item.get("armor", 0) or 0),
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
            rows = await db.execute_fetchall(
                "SELECT id,name,category,weight FROM item_catalog WHERE name=? COLLATE NOCASE", (item_name,)
            )
            if not rows:
                return False
            item_id, category = int(rows[0]["id"]), rows[0]["category"]
            stackable = category in {"Расходуемые предметы", "Зелья", "Еда", "Материалы"}
            existing = await db.execute_fetchall(
                "SELECT id FROM inventory WHERE character_id=? AND item_id=? AND equipped_slot IS NULL", (character_id, item_id)
            )
            if self._item_consumes_slot(rows[0]["name"], category, rows[0]["weight"]) and not (stackable and existing):
                athletics_rows = await db.execute_fetchall(
                    "SELECT value FROM skills WHERE character_id=? AND name='Атлетика'", (character_id,)
                )
                capacity = min(40, 8 + (await self.effective_skill_in_connection(db,character_id,'Атлетика')) // 5)
                current = await db.execute_fetchall(
                    """SELECT inventory.equipped_slot,item_catalog.name,item_catalog.category,item_catalog.weight
                       FROM inventory JOIN item_catalog ON item_catalog.id=inventory.item_id
                       WHERE inventory.character_id=?""", (character_id,)
                )
                used = sum(self._item_consumes_slot(
                    row["name"], row["category"], row["weight"], row["equipped_slot"]
                ) for row in current)
                needed = 1 if stackable else max(1, int(quantity))
                if used + needed > capacity:
                    return False
            if stackable:
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

    async def admin_give_item(self, character_id: int, item_name: str, quantity: int = 1) -> bool:
        """Выдать предмет без проверки вместимости — мастер может исправлять состояние анкеты."""
        quantity = max(1, min(999, int(quantity)))
        async with self.connect() as db:
            rows = await db.execute_fetchall(
                "SELECT id,category FROM item_catalog WHERE name=? COLLATE NOCASE", (item_name,)
            )
            if not rows:
                return False
            item_id, category = int(rows[0]["id"]), str(rows[0]["category"])
            stackable = category in {"Расходуемые предметы", "Зелья", "Еда", "Материалы", "Сигилы"}
            if stackable:
                existing = await db.execute_fetchall(
                    "SELECT id FROM inventory WHERE character_id=? AND item_id=? AND equipped_slot IS NULL",
                    (character_id, item_id),
                )
                if existing:
                    await db.execute("UPDATE inventory SET quantity=quantity+? WHERE id=?", (quantity, existing[0]["id"]))
                else:
                    await db.execute(
                        "INSERT INTO inventory(character_id,item_id,quantity) VALUES(?,?,?)",
                        (character_id, item_id, quantity),
                    )
            else:
                await db.executemany(
                    "INSERT INTO inventory(character_id,item_id,quantity) VALUES(?,?,1)",
                    [(character_id, item_id) for _ in range(quantity)],
                )
            await db.commit()
            return True

    async def remove_item(self, character_id: int, inventory_id: int, quantity: int = 1) -> bool:
        async with self.connect() as db:
            rows = await db.execute_fetchall(
                "SELECT quantity FROM inventory WHERE id=? AND character_id=? AND COALESCE(equipped_slot,'')!='Мастерская'", (inventory_id, character_id)
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
            await db.execute('BEGIN IMMEDIATE')
            talent_rows = await db.execute_fetchall("SELECT name FROM talents WHERE character_id=?", (character_id,))
            limits = self._equipment_limits_from_talents({str(row["name"]) for row in talent_rows})
            roman_sets = {"I": 1, "II": 2, "III": 3, "IV": 4}
            if slot.startswith("Оружие"):
                set_number = roman_sets.get(slot.split()[1], 99)
                if set_number > limits["weaponSets"]:
                    return False, "Этот комплект оружия ещё не открыт талантом «Изобилие оружия»."
            if slot.startswith("Быстрый предмет") and int(slot.rsplit(" ", 1)[1]) > limits["quickSlots"]:
                return False, "Дополнительные быстрые ячейки открывает талант «Патронташ»."
            rows = await db.execute_fetchall(
                """SELECT inventory.id,item_catalog.category,item_catalog.hands FROM inventory
                   JOIN item_catalog ON item_catalog.id=inventory.item_id
                   WHERE inventory.id=? AND inventory.character_id=? AND COALESCE(inventory.equipped_slot,'')!='Мастерская'""", (inventory_id, character_id)
            )
            if not rows:
                return False, "Предмет не найден в инвентаре."
            category = rows[0]["category"]
            if category=='Щиты' and slot.startswith('Оружие') and 'правая рука' in slot:
                return False,'Щит экипируется в левую руку.'
            if slot.startswith("Оружие") and category not in {
                "Одноручное оружие", "Двуручное оружие", "Парное оружие", "Луки", "Метательное оружие", "Посохи", "Щиты"
            }:
                return False, "Этот предмет нельзя поместить в оружейный набор."
            if slot in {"Голова", "Торс", "Руки", "Ноги"}:
                origin=await db.execute_fetchall('SELECT background FROM characters WHERE id=?',(character_id,))
                if origin and origin[0]['background']=='Зверолюд':return False,'Зверолюды не могут носить броню.'
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
                "UPDATE inventory SET equipped_slot=NULL WHERE id=? AND character_id=? AND COALESCE(equipped_slot,'')!='Мастерская'", (inventory_id, character_id)
            )
            await db.commit()
            return bool(cursor.rowcount)

    async def known_sigils(self, character_id: int) -> set[str]:
        async with self.connect() as db:
            rows = await db.execute_fetchall(
                "SELECT sigil_key FROM character_sigils WHERE character_id=?", (character_id,)
            )
        return {str(row["sigil_key"]) for row in rows if row["sigil_key"] in SIGILS_BY_KEY}

    async def learn_sigil_from_scroll(self, character_id: int, inventory_id: int) -> tuple[bool, str]:
        """Изучить сигил навсегда и израсходовать одну копию свитка атомарно."""
        async with self.connect() as db:
            rows = await db.execute_fetchall(
                """SELECT inventory.quantity,item_catalog.name,item_catalog.category,item_catalog.source_url
                   FROM inventory JOIN item_catalog ON item_catalog.id=inventory.item_id
                   WHERE inventory.id=? AND inventory.character_id=?""",
                (inventory_id, character_id),
            )
            if not rows:
                return False, "Свиток не найден в инвентаре."
            row = rows[0]
            if row["category"] != "Сигилы":
                return False, "Этот предмет не является свитком сигила."
            sigil_key = sigil_key_from_scroll_url(str(row["source_url"] or ""))
            sigil = SIGILS_BY_KEY.get(sigil_key or "")
            if not sigil:
                return False, "Этот свиток пока нельзя распознать как сигил."
            already = await db.execute_fetchall(
                "SELECT 1 FROM character_sigils WHERE character_id=? AND sigil_key=?",
                (character_id, sigil_key),
            )
            if already:
                return False, f"Сигил «{sigil['name']}» уже изучен."
            await db.execute(
                "INSERT INTO character_sigils(character_id,sigil_key,learned_from) VALUES(?,?,?)",
                (character_id, sigil_key, str(row["name"])),
            )
            if int(row["quantity"]) <= 1:
                await db.execute("DELETE FROM inventory WHERE id=?", (inventory_id,))
            else:
                await db.execute("UPDATE inventory SET quantity=quantity-1 WHERE id=?", (inventory_id,))
            await db.commit()
            return True, f"Изучен сигил «{sigil['name']}». Свиток израсходован."

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

    async def update_spell(
        self, character_id: int, spell_id: int, name: str, core: str, expression: str,
        accents: list[str], enhancements: list[str], difficulty: int, notes: str = "",
    ) -> bool:
        """Изменить существующую формулу, не сбрасывая её ячейку гримуара."""
        async with self.connect() as db:
            rows = await db.execute_fetchall(
                "SELECT id FROM spells WHERE id=? AND character_id=?", (spell_id, character_id)
            )
            if not rows:
                return False
            duplicate = await db.execute_fetchall(
                "SELECT id FROM spells WHERE character_id=? AND name=? AND id<>?", (character_id, name, spell_id)
            )
            if duplicate:
                raise ValueError(f"Формула с названием «{name}» уже существует.")
            await db.execute(
                """UPDATE spells SET name=?,core=?,expression=?,accents=?,enhancements=?,difficulty=?,notes=?
                   WHERE id=? AND character_id=?""",
                (name, core, expression, json.dumps(accents, ensure_ascii=False),
                 json.dumps(enhancements, ensure_ascii=False), max(0, difficulty), notes,
                 spell_id, character_id),
            )
            await db.commit()
            return True

    async def normalize_spell_slots(self, character_id: int, fill_empty: bool = False) -> None:
        """Оставить подготовленные формулы в допустимых уникальных ячейках."""
        limit = (await self.equipment_limits(character_id))["spellSlots"]
        async with self.connect() as db:
            rows = await db.execute_fetchall(
                "SELECT id,equipped_slot FROM spells WHERE character_id=? ORDER BY equipped_slot IS NULL,equipped_slot,id",
                (character_id,),
            )
            used: set[int] = set()
            reserve: list[int] = []
            for row in rows:
                slot = row["equipped_slot"]
                if slot is not None and 1 <= int(slot) <= limit and int(slot) not in used:
                    used.add(int(slot))
                else:
                    await db.execute("UPDATE spells SET equipped_slot=NULL WHERE id=?", (row["id"],))
                    reserve.append(int(row["id"]))
            free = [slot for slot in range(1, limit + 1) if slot not in used]
            if fill_empty:
                for spell_id, slot in zip(reserve, free):
                    await db.execute("UPDATE spells SET equipped_slot=? WHERE id=?", (slot, spell_id))
            await db.commit()

    async def set_spell_equipped(self, character_id: int, spell_id: int, equipped: bool) -> tuple[bool, str]:
        limit = (await self.equipment_limits(character_id))["spellSlots"]
        async with self.connect() as db:
            rows = await db.execute_fetchall(
                "SELECT name,equipped_slot FROM spells WHERE id=? AND character_id=?", (spell_id, character_id)
            )
            if not rows:
                return False, "Заклинание не найдено."
            if not equipped:
                await db.execute("UPDATE spells SET equipped_slot=NULL WHERE id=?", (spell_id,))
                await db.commit()
                return True, f"«{rows[0]['name']}» убрано в резерв."
            if rows[0]["equipped_slot"] is not None:
                return True, f"«{rows[0]['name']}» уже подготовлено."
            occupied = {
                int(row["equipped_slot"])
                for row in await db.execute_fetchall(
                    "SELECT equipped_slot FROM spells WHERE character_id=? AND equipped_slot IS NOT NULL",
                    (character_id,),
                )
            }
            free = next((slot for slot in range(1, limit + 1) if slot not in occupied), None)
            if free is None:
                return False, f"Все ячейки заклинаний заняты: {limit}/{limit}."
            await db.execute("UPDATE spells SET equipped_slot=? WHERE id=?", (free, spell_id))
            await db.commit()
            return True, f"«{rows[0]['name']}» подготовлено в ячейке {free}."

    async def spells(self, character_id: int) -> list[dict[str, Any]]:
        async with self.connect() as db:
            rows = await db.execute_fetchall(
                "SELECT * FROM spells WHERE character_id=? ORDER BY equipped_slot IS NULL,equipped_slot,name",
                (character_id,),
            )
            result = []
            for row in rows:
                spell = dict(row)
                spell["accents"] = json.loads(spell["accents"])
                spell["enhancements"] = json.loads(spell["enhancements"])
                result.append(spell)
            return result

    async def combat_quickbar(self, character_id: int) -> list[dict[str, Any]]:
        async with self.connect() as db:
            rows = await db.execute_fetchall(
                "SELECT slot,action_kind,action_name FROM combat_quickbar "
                "WHERE character_id=? ORDER BY slot", (character_id,),
            )
            return [dict(row) for row in rows]

    async def set_combat_quickbar(
        self, character_id: int, slot: int, action_kind: str = "", action_name: str = "",
    ) -> None:
        if not 1 <= int(slot) <= 9:
            raise ValueError("Номер быстрой ячейки должен быть от 1 до 9.")
        async with self.connect() as db:
            await db.execute(
                "DELETE FROM combat_quickbar WHERE character_id=? AND slot=?", (character_id, int(slot)),
            )
            if action_kind and action_name:
                await db.execute(
                    "INSERT INTO combat_quickbar(character_id,slot,action_kind,action_name) VALUES(?,?,?,?)",
                    (character_id, int(slot), action_kind, action_name),
                )
            await db.commit()

    async def replace_combat_quickbar(self, character_id: int, bindings: list[dict[str, Any]]) -> None:
        """Save all nine slots atomically, including intentionally empty slots."""
        if len(bindings) != 9 or {int(row['slot']) for row in bindings} != set(range(1, 10)):
            raise ValueError('Передайте ровно девять разных быстрых ячеек.')
        async with self.connect() as db:
            await db.execute('DELETE FROM combat_quickbar WHERE character_id=?', (character_id,))
            await db.executemany('INSERT INTO combat_quickbar(character_id,slot,action_kind,action_name) VALUES(?,?,?,?)',
                [(character_id, int(row['slot']), row['kind'], row['name']) for row in bindings])
            await db.commit()

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
