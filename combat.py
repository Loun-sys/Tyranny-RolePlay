"""Кнопочный боевой интерфейс для текстовой адаптации Tyranny.

Игроки не вводят боевые команды: после создания сцены все действия выбираются
кнопками и выпадающими списками. Состояние активной сцены хранится в памяти,
а здоровье персонажей сразу синхронизируется с базой.
"""

from __future__ import annotations

import math
import random
import re
from dataclasses import dataclass, field
from typing import Any, Callable

import discord

from constants import ABILITY_DETAILS
from sigil_data import spell_runtime_profile
from tactical_grid import BASE_MOVEMENT, TACTICAL_MAPS, TacticalGrid, initiative_bonus


CRIMSON = discord.Color.from_rgb(111, 27, 25)
BRONZE = discord.Color.from_rgb(139, 79, 42)

CORE_SKILLS = {
    "Истощение": "Управление истощением", "Эмоции": "Управление рвением",
    "Огонь": "Управление огнём", "Сила": "Управление силой",
    "Холод": "Управление холодом", "Иллюзия": "Управление иллюзиями",
    "Жизнь": "Управление жизнью", "Молния": "Управление молниями",
    "Камень": "Управление камнем", "Терратус": "Управление могильным светом",
    "Рвение": "Управление рвением",
}

CORE_DAMAGE = {
    "Огонь": "Огненный", "Холод": "Ледяной", "Молния": "Электрический",
    "Истощение": "Магический", "Эмоции": "Магический", "Сила": "Дробящий",
    "Иллюзия": "Магический", "Камень": "Дробящий", "Терратус": "Магический",
    "Рвение": "Магический", "Жизнь": "Магический",
}

RANGED_TALENT_RANGES = {"Выстрел в сердце": 12, "Хромота": 10}


@dataclass
class Combatant:
    key: str
    name: str
    team: str
    health: int
    health_max: int
    user_id: int | None = None
    character_id: int | None = None
    attributes: dict[str, int] = field(default_factory=dict)
    skills: dict[str, int] = field(default_factory=dict)
    talents: list[dict[str, Any]] = field(default_factory=list)
    spells: list[dict[str, Any]] = field(default_factory=list)
    inventory: list[dict[str, Any]] = field(default_factory=list)
    armor: int = 0
    accuracy: int = 25
    damage_min: int = 3
    damage_max: int = 7
    damage_type: str = "Дробящий"
    recovery: float = 3.0
    ready_at: float = 1.0
    active_weapon_set: int = 1
    conditions: list[str] = field(default_factory=list)
    cooldowns: dict[str, int] = field(default_factory=dict)
    x: int = 0
    y: int = 0
    initiative_roll: int = 0
    initiative_total: int = 0
    movement_remaining: int = BASE_MOVEMENT

    @property
    def alive(self) -> bool:
        return self.health > 0

    def defense(self, kind: str) -> int:
        if kind == "Парирование":
            return self.skills.get("Парирование", self.accuracy)
        if kind == "Уклонение":
            return self.skills.get("Уклонение", self.accuracy)
        if kind in {"Выносливость", "Стойкость"}:
            return round(self.attributes.get("Стойкость", 10) * 1.5 + self.attributes.get("Сила", 10) * .5)
        if kind == "Воля":
            return round(self.attributes.get("Стойкость", 10) * 1.5 + self.attributes.get("Живучесть", 10) * .5)
        return round(self.attributes.get("Стойкость", 10) * 1.5 + self.attributes.get("Смекалка", 10) * .5)


@dataclass
class CombatSession:
    guild_id: int
    channel_id: int
    owner_id: int
    db: Any
    combatants: dict[str, Combatant] = field(default_factory=dict)
    started: bool = False
    round_number: int = 1
    log: list[str] = field(default_factory=list)
    message: discord.Message | None = None
    turn_order: list[str] = field(default_factory=list)
    turn_index: int = 0

    def __post_init__(self) -> None:
        spec = TACTICAL_MAPS["training_grounds"]
        self.grid = TacticalGrid(spec["width"], spec["height"], set(spec["blocked"]))
        if self.started and self.combatants and not self.turn_order:
            self.turn_order = list(self.combatants)

    @property
    def current(self) -> Combatant | None:
        if not self.started:
            return next((unit for unit in self.combatants.values() if unit.alive), None)
        if not self.turn_order:
            return None
        for offset in range(len(self.turn_order)):
            index = (self.turn_index + offset) % len(self.turn_order)
            unit = self.combatants.get(self.turn_order[index])
            if unit and unit.alive:
                self.turn_index = index
                return unit
        return None

    @property
    def enemies_alive(self) -> list[Combatant]:
        current = self.current
        return [unit for unit in self.combatants.values() if unit.alive and current and unit.team != current.team]

    def winner(self) -> str | None:
        teams = {unit.team for unit in self.combatants.values() if unit.alive}
        return next(iter(teams)) if len(teams) == 1 and self.started else None

    def advance(self, actor: Combatant, recovery: float) -> None:
        """Основное действие завершает ход; recovery оставлен для совместимости вызовов."""
        if not self.turn_order:
            return
        previous = self.turn_index
        for step in range(1, len(self.turn_order) + 1):
            candidate = (previous + step) % len(self.turn_order)
            unit = self.combatants.get(self.turn_order[candidate])
            if unit and unit.alive:
                self.turn_index = candidate
                if candidate <= previous:
                    self.round_number += 1
                unit.movement_remaining = BASE_MOVEMENT
                return

    def distance(self, first: Combatant, second: Combatant) -> int:
        return self.grid.distance((first.x, first.y), (second.x, second.y))

    def embed(self) -> discord.Embed:
        winner = self.winner()
        title = "Бой завершён" if winner else f"Боевая сцена · раунд {self.round_number}"
        embed = discord.Embed(title=title, color=discord.Color.green() if winner else CRIMSON)
        if winner:
            embed.description = f"Победила сторона **{winner}**."
        elif not self.started:
            embed.description = "Лобби открыто. Игроки присоединяются одной кнопкой, противников добавляет мастер."
        else:
            actor = self.current
            embed.description = f"Сейчас действует: **{actor.name}**" if actor else "Нет способных действовать участников."
        by_team: dict[str, list[Combatant]] = {}
        for unit in self.combatants.values():
            by_team.setdefault(unit.team, []).append(unit)
        for team, units in by_team.items():
            lines = []
            for unit in units:
                marker = "▶" if self.started and unit is self.current and not winner else "•"
                state = "💀" if not unit.alive else f"❤️ {unit.health}/{unit.health_max} · клетка {unit.x + 1}:{unit.y + 1}"
                initiative = f" · инициатива {unit.initiative_total}" if self.started else ""
                lines.append(f"{marker} **{unit.name}** — {state}{initiative}")
            embed.add_field(name=team, value="\n".join(lines)[:1024], inline=False)
        if self.log:
            embed.add_field(name="Последние события", value="\n".join(self.log[-6:])[-1024:], inline=False)
        embed.set_footer(text="1 клетка = 1 метр · 6 м движения за ход · действия выбираются кнопками")
        return embed

    async def refresh(self) -> None:
        if self.message:
            winner = self.winner()
            if winner:
                SESSIONS.pop((self.guild_id, self.channel_id), None)
            view: discord.ui.View | None = None if winner else (BattleView(self) if self.started else LobbyView(self))
            await self.message.edit(embed=self.embed(), view=view)

    async def add_player(self, character: dict[str, Any]) -> tuple[bool, str]:
        key = f"p:{character['user_id']}"
        if key in self.combatants:
            return False, "Вы уже участвуете в этой сцене."
        inventory = await self.db.inventory(character["id"])
        spells = [spell for spell in await self.db.spells(character["id"]) if spell.get("equipped_slot") is not None]
        unit = Combatant(
            key=key, name=character["name"], team="Вершители Судеб",
            user_id=character["user_id"], character_id=character["id"],
            health=character["health"], health_max=character["health_max"],
            attributes=character["attributes"],
            skills={name: data["value"] for name, data in character["skills"].items()},
            talents=character["talents"], spells=spells, inventory=inventory,
        )
        player_count = sum(1 for row in self.combatants.values() if row.team == "Вершители Судеб")
        unit.x, unit.y = 1, min(self.grid.height - 1, 2 + player_count * 2)
        apply_equipment(unit)
        self.combatants[key] = unit
        return True, f"**{unit.name}** присоединяется к сцене."

    async def persist_damage(self, target: Combatant, before: int) -> None:
        if target.character_id is not None and target.health != before:
            await self.db.adjust_health(target.character_id, target.health - before)


def apply_equipment(unit: Combatant) -> None:
    unit.armor = sum(int(item.get("armor") or 0) for item in unit.inventory if item.get("equipped_slot") in {"Голова", "Торс", "Руки", "Ноги"})
    prefix = f"Оружие {['I', 'II', 'III', 'IV'][unit.active_weapon_set - 1]}"
    weapons = [item for item in unit.inventory if (item.get("equipped_slot") or "").startswith(prefix)]
    weapon = next((item for item in weapons if int(item.get("damage_max") or 0) > 0), None)
    if not weapon:
        unit.accuracy = unit.skills.get("Безоружный бой", 25)
        return
    category = weapon.get("category", "")
    skill = {
        "Одноручное оружие": "Одноручное оружие", "Двуручное оружие": "Двуручное оружие",
        "Парное оружие": "Парное оружие", "Луки": "Луки", "Метательное оружие": "Одноручное оружие",
        "Посохи": "Волшебный посох",
    }.get(category, "Одноручное оружие")
    unit.accuracy = unit.skills.get(skill, 25)
    unit.damage_min = int(weapon.get("damage_min") or 3)
    unit.damage_max = max(unit.damage_min, int(weapon.get("damage_max") or 7))
    unit.recovery = float(weapon.get("recovery") or 3)
    props = weapon.get("properties") or "{}"
    props_text = str(props).casefold()
    for damage_type in ("Рубящий", "Колющий", "Дробящий", "Огненный", "Ледяной", "Электрический", "Магический"):
        if damage_type.casefold() in props_text:
            unit.damage_type = damage_type
            break


def weapon_skill(unit: Combatant) -> str:
    """Определить развиваемый навык текущего комплекта оружия."""
    prefix = f"Оружие {['I', 'II', 'III', 'IV'][unit.active_weapon_set - 1]}"
    weapon = next((item for item in unit.inventory if (item.get("equipped_slot") or "").startswith(prefix)
                   and int(item.get("damage_max") or 0) > 0), None)
    if not weapon:
        return "Безоружный бой"
    return {
        "Одноручное оружие": "Одноручное оружие", "Двуручное оружие": "Двуручное оружие",
        "Парное оружие": "Парное оружие", "Луки": "Луки",
        "Метательное оружие": "Одноручное оружие", "Посохи": "Волшебный посох",
    }.get(weapon.get("category", ""), "Одноручное оружие")


def weapon_range(unit: Combatant) -> int:
    return {"Луки": 12, "Дротики": 6, "Волшебный посох": 10}.get(weapon_skill(unit), 1)


def resolve_attack(attacker: Combatant, target: Combatant, *, accuracy: int | None = None,
                   damage: tuple[int, int] | None = None, defense: str = "Парирование",
                   damage_type: str | None = None, penetration: int = 0) -> str:
    roll = random.randint(1, 100)
    attack_accuracy = attacker.accuracy if accuracy is None else accuracy
    score = roll + attack_accuracy - target.defense(defense)
    if score <= 15:
        quality, multiplier = "промах", 0
    elif score <= 50:
        quality, multiplier = "скользящий удар", .5
    elif score <= 100:
        quality, multiplier = "попадание", 1
    else:
        quality, multiplier = "критическое попадание", 1.5
    if multiplier == 0:
        return f"**{attacker.name}** → **{target.name}**: промах ({roll} + {attack_accuracy} − {target.defense(defense)})."
    low, high = damage or (attacker.damage_min, attacker.damage_max)
    raw = max(1, round(random.randint(low, high) * multiplier))
    armor = max(0, target.armor - penetration)
    dealt = max(1, raw - armor)
    target.health = max(0, target.health - dealt)
    kind = damage_type or attacker.damage_type
    fallen = " Цель повержена." if not target.alive else ""
    return f"**{attacker.name}** → **{target.name}**: {quality}, **{dealt} {kind.lower()} урона** (бросок {roll}, броня {armor}).{fallen}"


class TargetSelect(discord.ui.Select):
    def __init__(self, session: CombatSession, action: str, payload: str = ""):
        self.session, self.action, self.payload = session, action, payload
        actor = session.current
        targets = [unit for unit in session.combatants.values() if unit.alive and actor and unit.team != actor.team]
        super().__init__(placeholder="Выберите цель", min_values=1, max_values=1, options=[
            discord.SelectOption(label=unit.name[:100], value=unit.key, description=f"{session.distance(actor, unit)} м · здоровье {unit.health}/{unit.health_max}")
            for unit in targets[:25]
        ])

    async def callback(self, interaction: discord.Interaction):
        actor = self.session.current
        target = self.session.combatants.get(self.values[0])
        if not actor or not target or not actor.alive or not target.alive:
            await interaction.response.send_message("Состояние боя уже изменилось.", ephemeral=True)
            return
        if actor.user_id != interaction.user.id and interaction.user.id != self.session.owner_id:
            await interaction.response.send_message("Сейчас ход другого участника.", ephemeral=True)
            return
        if self.action == "attack":
            action_range = weapon_range(actor)
        elif self.action == "talent":
            action_range = RANGED_TALENT_RANGES.get(self.payload, 1)
        else:
            selected_spell = next((item for item in actor.spells if item["name"] == self.payload), None)
            skill_name = CORE_SKILLS.get((selected_spell or {}).get("core"), "Знания")
            action_range = spell_runtime_profile(
                selected_spell or {}, skill=actor.skills.get(skill_name, 25),
                wits=actor.attributes.get("Смекалка", 10), cooldown_multiplier=1,
            )["range"]
        distance = self.session.distance(actor, target)
        if distance > action_range:
            await interaction.response.send_message(
                f"Цель находится в {distance} м, дальность действия — {action_range} м. Сначала переместитесь.",
                ephemeral=True,
            )
            return
        if action_range > 1 and not self.session.grid.line_of_sight((actor.x, actor.y), (target.x, target.y)):
            await interaction.response.send_message("Между токенами нет прямой видимости.", ephemeral=True)
            return
        before = target.health
        if self.action == "attack":
            line = resolve_attack(actor, target)
            recovery = actor.recovery
            used_skill = weapon_skill(actor)
        elif self.action == "talent":
            talent = next((item for item in actor.talents if item["name"] == self.payload), None)
            if not talent:
                await interaction.response.send_message("Способность больше недоступна.", ephemeral=True)
                return
            if actor.cooldowns.get(talent["name"], 0) > self.session.round_number:
                remaining = actor.cooldowns[talent["name"]] - self.session.round_number
                await interaction.response.send_message(
                    f"Способность ещё восстанавливается: {remaining} раунд.", ephemeral=True
                )
                return
            line = resolve_attack(actor, target, accuracy=actor.accuracy + 5,
                                  damage=(actor.damage_min + 2, actor.damage_max + 4), penetration=2)
            line = f"✨ **{talent['name']}**: " + line
            recovery = actor.recovery + 1
            used_skill = weapon_skill(actor)
            details = ABILITY_DETAILS.get(talent["name"], {})
            base_cooldown = next(iter(re.findall(r"\d+(?:[.,]\d+)?", str(details.get("cooldown", "1")))), "1")
            rounds = max(1, math.ceil(float(base_cooldown.replace(",", ".")) * max(.1, 1 - (actor.attributes.get("Быстрота", 10) - 10) * .03)))
            actor.cooldowns[talent["name"]] = self.session.round_number + rounds + 1
        else:
            spell = next((item for item in actor.spells if item["name"] == self.payload), None)
            if not spell:
                await interaction.response.send_message("Заклинание больше недоступно.", ephemeral=True)
                return
            cooldown_key = f"заклинание:{spell['name']}"
            if actor.cooldowns.get(cooldown_key, 0) > self.session.round_number:
                remaining = actor.cooldowns[cooldown_key] - self.session.round_number
                await interaction.response.send_message(
                    f"Заклинание ещё восстанавливается: {remaining} раунд.", ephemeral=True
                )
                return
            skill = CORE_SKILLS.get(spell["core"], "Знания")
            profile = spell_runtime_profile(
                spell,
                skill=actor.skills.get(skill, actor.skills.get("Знания", 25)),
                wits=actor.attributes.get("Смекалка", 10),
                cooldown_multiplier=max(.1, 1 - (actor.attributes.get("Быстрота", 10) - 10) * .03),
            )
            line = resolve_attack(
                actor, target, accuracy=profile["accuracy"],
                damage=(profile["damage_min"], profile["damage_max"]),
                defense=profile["defense"], damage_type=CORE_DAMAGE.get(spell["core"], "Магический"),
                penetration=profile["penetration"],
            )
            line = f"🔮 **{spell['name']}**: " + line
            recovery = max(2, 3 + spell["difficulty"] / 25)
            used_skill = skill
            spell_rounds = profile["cooldown"]
            actor.cooldowns[cooldown_key] = self.session.round_number + spell_rounds + 1
        self.session.log.append(line)
        self.session.advance(actor, recovery)
        await self.session.persist_damage(target, before)
        if actor.character_id is not None:
            await self.session.db.add_skill_experience(actor.character_id, used_skill, 1)
        await interaction.response.send_message(line, ephemeral=True)
        await self.session.refresh()


class TargetView(discord.ui.View):
    def __init__(self, session: CombatSession, action: str, payload: str = ""):
        super().__init__(timeout=90)
        self.add_item(TargetSelect(session, action, payload))


class ChoiceSelect(discord.ui.Select):
    def __init__(self, session: CombatSession, kind: str, rows: list[dict[str, Any]]):
        self.session, self.kind = session, kind
        super().__init__(placeholder="Выберите действие", options=[
            discord.SelectOption(label=row["name"][:100], value=row["name"], description=(row.get("description") or row.get("core") or "")[:100])
            for row in rows[:25]
        ])

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.edit_message(content="Теперь выберите цель:", view=TargetView(self.session, self.kind, self.values[0]))


class ChoiceView(discord.ui.View):
    def __init__(self, session: CombatSession, kind: str, rows: list[dict[str, Any]]):
        super().__init__(timeout=90)
        self.add_item(ChoiceSelect(session, kind, rows))


class DirectionButton(discord.ui.Button):
    def __init__(self, session: CombatSession, dx: int, dy: int, label: str):
        super().__init__(label=label, style=discord.ButtonStyle.secondary)
        self.session, self.dx, self.dy = session, dx, dy

    async def callback(self, interaction: discord.Interaction):
        actor = self.session.current
        if not actor or interaction.user.id not in {actor.user_id, self.session.owner_id}:
            await interaction.response.send_message("Сейчас ход другого участника.", ephemeral=True)
            return
        if actor.movement_remaining <= 0:
            await interaction.response.send_message("Перемещение в этом ходу исчерпано.", ephemeral=True)
            return
        target = (actor.x + self.dx, actor.y + self.dy)
        occupied = {(unit.x, unit.y) for unit in self.session.combatants.values() if unit.alive and unit is not actor}
        if not self.session.grid.inside(target) or target in self.session.grid.blocked or target in occupied:
            await interaction.response.send_message("Эта клетка занята или недоступна.", ephemeral=True)
            return
        actor.x, actor.y = target
        actor.movement_remaining -= 1
        self.session.log.append(f"👣 **{actor.name}** перемещается в клетку {actor.x + 1}:{actor.y + 1}.")
        await interaction.response.edit_message(
            content=f"Позиция **{actor.x + 1}:{actor.y + 1}** · осталось движения: **{actor.movement_remaining} м**.",
            view=MoveView(self.session),
        )
        await self.session.refresh()


class MoveView(discord.ui.View):
    def __init__(self, session: CombatSession):
        super().__init__(timeout=180)
        for dx, dy, label in ((-1, -1, "↖"), (0, -1, "↑"), (1, -1, "↗"),
                              (-1, 0, "←"), (1, 0, "→"),
                              (-1, 1, "↙"), (0, 1, "↓"), (1, 1, "↘")):
            self.add_item(DirectionButton(session, dx, dy, label))


class BattleView(discord.ui.View):
    def __init__(self, session: CombatSession):
        super().__init__(timeout=3600)
        self.session = session

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        actor = self.session.current
        if not actor or (interaction.user.id not in {actor.user_id, self.session.owner_id}):
            await interaction.response.send_message(f"Сейчас действует **{actor.name if actor else 'никто'}**.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Атака", emoji="⚔️", style=discord.ButtonStyle.danger, row=0)
    async def attack(self, interaction: discord.Interaction, _: discord.ui.Button):
        await interaction.response.send_message("Выберите цель обычной атаки:", view=TargetView(self.session, "attack"), ephemeral=True)

    @discord.ui.button(label="Способность", emoji="✨", style=discord.ButtonStyle.primary, row=0)
    async def ability(self, interaction: discord.Interaction, _: discord.ui.Button):
        actor = self.session.current
        available = [
            talent for talent in (actor.talents if actor else [])
            if talent["name"] in ABILITY_DETAILS and actor.cooldowns.get(talent["name"], 0) <= self.session.round_number
        ]
        if not actor or not available:
            await interaction.response.send_message("У персонажа нет доступных способностей.", ephemeral=True)
            return
        await interaction.response.send_message("Выберите способность:", view=ChoiceView(self.session, "talent", available), ephemeral=True)

    @discord.ui.button(label="Заклинание", emoji="🔮", style=discord.ButtonStyle.primary, row=0)
    async def spell(self, interaction: discord.Interaction, _: discord.ui.Button):
        actor = self.session.current
        available = [
            spell for spell in (actor.spells if actor else [])
            if actor.cooldowns.get(f"заклинание:{spell['name']}", 0) <= self.session.round_number
        ]
        if not actor or not available:
            await interaction.response.send_message("В гримуаре нет собранных заклинаний.", ephemeral=True)
            return
        await interaction.response.send_message("Выберите заклинание:", view=ChoiceView(self.session, "spell", available), ephemeral=True)

    @discord.ui.button(label="Предмет", emoji="🧪", style=discord.ButtonStyle.secondary, row=1)
    async def item(self, interaction: discord.Interaction, _: discord.ui.Button):
        actor = self.session.current
        usable = [item for item in actor.inventory if item.get("category") in {"Зелья", "Еда", "Расходуемые предметы"} and item.get("quantity", 0) > 0]
        if not usable:
            await interaction.response.send_message("В инвентаре нет доступных расходников.", ephemeral=True)
            return
        await interaction.response.send_message("Выберите предмет:", view=ItemView(self.session, usable), ephemeral=True)

    @discord.ui.button(label="Перемещение", emoji="👣", style=discord.ButtonStyle.secondary, row=1)
    async def move(self, interaction: discord.Interaction, _: discord.ui.Button):
        actor = self.session.current
        await interaction.response.send_message(
            f"Позиция **{actor.x + 1}:{actor.y + 1}**. Осталось **{actor.movement_remaining} м**. "
            "Каждое нажатие перемещает токен на одну клетку.",
            view=MoveView(self.session), ephemeral=True,
        )

    @discord.ui.button(label="Смена оружия", emoji="🔁", style=discord.ButtonStyle.secondary, row=1)
    async def weapon(self, interaction: discord.Interaction, _: discord.ui.Button):
        actor = self.session.current
        actor.active_weapon_set = actor.active_weapon_set % 4 + 1
        apply_equipment(actor)
        self.session.log.append(f"🔁 **{actor.name}** переключается на комплект оружия {actor.active_weapon_set} без траты действия.")
        await interaction.response.send_message(f"Выбран комплект оружия {actor.active_weapon_set}. Ход продолжается.", ephemeral=True)
        await self.session.refresh()

    @discord.ui.button(label="Пропустить", emoji="⏭️", style=discord.ButtonStyle.secondary, row=1)
    async def skip(self, interaction: discord.Interaction, _: discord.ui.Button):
        actor = self.session.current
        self.session.log.append(f"⏭️ **{actor.name}** выжидает.")
        self.session.advance(actor, 2)
        await interaction.response.send_message("Ход пропущен.", ephemeral=True)
        await self.session.refresh()

    @discord.ui.button(label="Завершить бой", emoji="⛔", style=discord.ButtonStyle.secondary, row=2)
    async def finish(self, interaction: discord.Interaction, _: discord.ui.Button):
        if interaction.user.id != self.session.owner_id:
            await interaction.response.send_message("Завершить сцену может только её создатель.", ephemeral=True)
            return
        SESSIONS.pop((self.session.guild_id, self.session.channel_id), None)
        await interaction.response.edit_message(embed=self.session.embed(), view=None)


class ItemSelect(discord.ui.Select):
    def __init__(self, session: CombatSession, rows: list[dict[str, Any]]):
        self.session = session
        self.rows = {str(item["inventory_id"]): item for item in rows}
        super().__init__(placeholder="Выберите расходник", options=[
            discord.SelectOption(label=item["name"][:100], value=str(item["inventory_id"]), description=f"Количество: {item['quantity']}")
            for item in rows[:25]
        ])

    async def callback(self, interaction: discord.Interaction):
        actor = self.session.current
        item = self.rows[self.values[0]]
        before = actor.health
        healing = max(3, 5 + actor.attributes.get("Живучесть", 10) // 2)
        actor.health = min(actor.health_max, actor.health + healing)
        restored = actor.health - before
        await self.session.db.remove_item(actor.character_id, item["inventory_id"], 1)
        item["quantity"] -= 1
        line = f"🧪 **{actor.name}** использует **{item['name']}** и восстанавливает {restored} здоровья."
        self.session.log.append(line)
        self.session.advance(actor, 2)
        await self.session.persist_damage(actor, before)
        await interaction.response.edit_message(content=line, view=None)
        await self.session.refresh()


class ItemView(discord.ui.View):
    def __init__(self, session: CombatSession, rows: list[dict[str, Any]]):
        super().__init__(timeout=90)
        self.add_item(ItemSelect(session, rows))


class EnemyModal(discord.ui.Modal, title="Добавить противника"):
    name = discord.ui.TextInput(label="Имя", max_length=80)
    health = discord.ui.TextInput(label="Здоровье", default="30", max_length=4)
    combat = discord.ui.TextInput(label="Точность / защита", default="30/30", max_length=7)
    armor = discord.ui.TextInput(label="Броня", default="3", max_length=3)
    damage = discord.ui.TextInput(label="Урон (например 4-9)", default="4-9", max_length=9)

    def __init__(self, session: CombatSession):
        super().__init__()
        self.session = session

    async def on_submit(self, interaction: discord.Interaction):
        try:
            hp = max(1, int(self.health.value))
            accuracy, defense = [int(part.strip()) for part in self.combat.value.replace("/", " ").split()[:2]]
            low, high = [int(part.strip()) for part in self.damage.value.replace("–", "-").split("-", 1)]
            armor = max(0, int(self.armor.value))
        except (ValueError, IndexError):
            await interaction.response.send_message("Используйте числа: точность/защита `30/30`, урон `4-9`.", ephemeral=True)
            return
        key = f"npc:{len(self.session.combatants) + 1}:{self.name.value}"
        self.session.combatants[key] = Combatant(
            key=key, name=self.name.value, team="Противники", health=hp, health_max=hp,
            accuracy=accuracy, damage_min=max(1, low), damage_max=max(low, high), armor=armor,
            skills={"Парирование": defense, "Уклонение": defense},
            attributes={"Живучесть": defense // 2, "Стойкость": defense // 2, "Смекалка": defense // 2},
        )
        unit = self.session.combatants[key]
        enemy_count = sum(1 for row in self.session.combatants.values() if row.team == "Противники") - 1
        unit.x, unit.y = self.session.grid.width - 2, min(self.session.grid.height - 1, 2 + enemy_count * 2)
        await interaction.response.send_message(f"Добавлен противник **{self.name.value}**.", ephemeral=True)
        await self.session.refresh()


class LobbyView(discord.ui.View):
    def __init__(self, session: CombatSession):
        super().__init__(timeout=3600)
        self.session = session

    @discord.ui.button(label="Присоединиться", emoji="➕", style=discord.ButtonStyle.success)
    async def join(self, interaction: discord.Interaction, _: discord.ui.Button):
        character = await self.session.db.get_character(interaction.guild_id, interaction.user.id)
        if not character:
            await interaction.response.send_message("Сначала создайте персонажа командой `/регистрация`.", ephemeral=True)
            return
        added, message = await self.session.add_player(character)
        await interaction.response.send_message(message, ephemeral=True)
        if added:
            await self.session.refresh()

    @discord.ui.button(label="Добавить противника", emoji="👹", style=discord.ButtonStyle.secondary)
    async def enemy(self, interaction: discord.Interaction, _: discord.ui.Button):
        if interaction.user.id != self.session.owner_id:
            await interaction.response.send_message("Противников добавляет создатель сцены.", ephemeral=True)
            return
        await interaction.response.send_modal(EnemyModal(self.session))

    @discord.ui.button(label="Начать", emoji="▶️", style=discord.ButtonStyle.danger)
    async def start(self, interaction: discord.Interaction, _: discord.ui.Button):
        if interaction.user.id != self.session.owner_id:
            await interaction.response.send_message("Начать бой может только создатель сцены.", ephemeral=True)
            return
        teams = {unit.team for unit in self.session.combatants.values()}
        if len(teams) < 2:
            await interaction.response.send_message("Нужен хотя бы один персонаж и один противник.", ephemeral=True)
            return
        self.session.started = True
        for unit in self.session.combatants.values():
            unit.initiative_roll = random.randint(1, 20)
            unit.initiative_total = unit.initiative_roll + initiative_bonus(unit.attributes.get("Быстрота", 10))
            unit.movement_remaining = BASE_MOVEMENT
        ordered = sorted(
            self.session.combatants.values(),
            key=lambda unit: (-unit.initiative_total, -unit.attributes.get("Быстрота", 10), unit.key),
        )
        self.session.turn_order = [unit.key for unit in ordered]
        self.session.turn_index = 0
        initiative_line = " → ".join(f"{unit.name} ({unit.initiative_total})" for unit in ordered)
        self.session.log.append(f"⚔️ Бой начинается. Инициатива: {initiative_line}.")
        await interaction.response.edit_message(embed=self.session.embed(), view=BattleView(self.session))

    @discord.ui.button(label="Отменить", emoji="🗑️", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, _: discord.ui.Button):
        if interaction.user.id != self.session.owner_id:
            await interaction.response.send_message("Отменить сцену может только её создатель.", ephemeral=True)
            return
        SESSIONS.pop((self.session.guild_id, self.session.channel_id), None)
        await interaction.response.edit_message(content="Боевая сцена отменена.", embed=None, view=None)


SESSIONS: dict[tuple[int, int], CombatSession] = {}


async def create_combat(interaction: discord.Interaction, db: Any) -> tuple[bool, str | CombatSession]:
    if interaction.guild_id is None or interaction.channel_id is None:
        return False, "Бой можно создать только в канале сервера."
    key = (interaction.guild_id, interaction.channel_id)
    if key in SESSIONS:
        return False, "В этом канале уже есть активная боевая сцена."
    session = CombatSession(interaction.guild_id, interaction.channel_id, interaction.user.id, db)
    SESSIONS[key] = session
    character = await db.get_character(interaction.guild_id, interaction.user.id)
    if character:
        await session.add_player(character)
    return True, session
