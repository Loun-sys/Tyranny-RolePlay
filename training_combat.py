"""Клеточная пошаговая тренировка персонажа против неподвижного манекена."""

from __future__ import annotations

import math
import random
import re
from dataclasses import dataclass, field
from typing import Any

from constants import ABILITY_DETAILS
from sigil_data import spell_runtime_profile
from tactical_grid import BASE_MOVEMENT, TACTICAL_MAPS, TacticalGrid, initiative_bonus


DUMMY = {
    "name": "Укреплённый тренировочный манекен",
    "healthMax": 180,
    "armor": 4,
    "defenses": {"Парирование": 35, "Уклонение": 30, "Выносливость": 32, "Воля": 28, "Магия": 32},
}

TRAINING_TARGETS = {
    "dummy": {**DUMMY, "name": "Укреплённый тренировочный манекен", "healthMax": 180, "position": (10, 4)},
    "dummy_left": {**DUMMY, "name": "Левый манекен", "healthMax": 100, "position": (10, 2)},
    "dummy_right": {**DUMMY, "name": "Правый манекен", "healthMax": 100, "position": (10, 6)},
}

ATTACKING_ABILITIES = {
    "Удар щитом": (1.0, 0), "Раскол": (1.5, 0), "Секущий удар": (.8, 5),
    "Выстрел в сердце": (1.2, 0), "Хромота": (1.0, 0), "Шквал ударов": (2.0, 0),
    "Рассечение": (1.2, 0), "Удар ладонью": (1.0, 0), "Заряженный кулак": (1.0, 2),
    "Ледяная хватка": (1.0, 1), "Рывок": (1.2, 0), "Удар в прыжке": (1.4, 0),
}
RANGED_ABILITIES = {"Выстрел в сердце": 12, "Хромота": 10, "Рывок": 10, "Удар в прыжке": 6}
FORCED_MOVEMENT = {"Удар ладонью": ("push", 3), "Заряженный кулак": ("push", 2), "Ледяная хватка": ("pull", 2)}
MOBILITY_ABILITIES = {
    "Рывок": {"description": "Перемещает персонажа к цели на расстоянии до 10 м и наносит 120% урона.",
               "type": "Ловкость · рывок", "cooldown": "3 раунда", "icon": ""},
    "Удар в прыжке": {"description": "Телепортационное перемещение на свободную клетку рядом с целью и мощный удар.",
                       "type": "Ловкость · телепортация", "cooldown": "4 раунда", "icon": ""},
}

CORE_SKILLS = {
    "Истощение": "Управление истощением", "Эмоции": "Управление рвением",
    "Огонь": "Управление огнём", "Сила": "Управление силой",
    "Холод": "Управление холодом", "Иллюзия": "Управление иллюзиями",
    "Жизнь": "Управление жизнью", "Молния": "Управление молниями",
    "Камень": "Управление камнем", "Терратус": "Управление могильным светом",
    "Рвение": "Управление рвением",
}
CORE_DAMAGE = {
    "Огонь": "огненного", "Холод": "ледяного", "Молния": "электрического",
    "Сила": "дробящего", "Камень": "дробящего", "Жизнь": "магического",
    "Истощение": "магического", "Эмоции": "магического", "Иллюзия": "магического",
    "Терратус": "магического", "Рвение": "магического",
}


def _number(value: Any, default: float = 0) -> float:
    match = re.search(r"\d+(?:[.,]\d+)?", str(value or ""))
    return float(match.group().replace(",", ".")) if match else default


def _round_word(value: int) -> str:
    if value % 10 == 1 and value % 100 != 11:
        return "раунд"
    if value % 10 in {2, 3, 4} and value % 100 not in {12, 13, 14}:
        return "раунда"
    return "раундов"


@dataclass
class TrainingSession:
    character_id: int
    round_number: int = 1
    dummy_health: int = DUMMY["healthMax"]
    damage_total: int = 0
    attacks: int = 0
    hits: int = 0
    active_weapon_set: int = 1
    cooldowns: dict[str, int] = field(default_factory=dict)
    log: list[str] = field(default_factory=list)
    map_key: str = "training_grounds"
    player_position: tuple[int, int] = (2, 4)
    dummy_position: tuple[int, int] = (10, 4)
    movement_remaining: int = BASE_MOVEMENT
    action_available: bool = True
    initialized: bool = False
    initiative: list[dict[str, Any]] = field(default_factory=list)
    selected_target_id: str = "dummy"
    target_healths: dict[str, int] = field(default_factory=lambda: {
        key: int(row["healthMax"]) for key, row in TRAINING_TARGETS.items()
    })
    target_positions: dict[str, tuple[int, int]] = field(default_factory=lambda: {
        key: tuple(row["position"]) for key, row in TRAINING_TARGETS.items()
    })
    player_health: int = 0
    player_health_max: int = 0
    disengaged: bool = False
    preview_cells: set[tuple[int, int]] = field(default_factory=set)
    active_stance: str = ""
    aim_point: tuple[int, int] | None = None

    def __post_init__(self) -> None:
        spec = TACTICAL_MAPS[self.map_key]
        self.grid = TacticalGrid(spec["width"], spec["height"], set(spec["blocked"]))

    @property
    def finished(self) -> bool:
        return not any(value > 0 for value in self.target_healths.values())

    def _initialize(self, character: dict[str, Any]) -> None:
        if self.initialized:
            return
        quickness = int(character.get("attributes", {}).get("Быстрота", 10))
        self.player_health_max = int(character.get("health_max", character.get("health", 1)))
        self.player_health = int(character.get("health", self.player_health_max))
        bonus = initiative_bonus(quickness)
        player_roll = random.randint(1, 20)
        self.initiative = [
            {"id": "player", "name": character.get("name", "Персонаж"), "roll": player_roll,
             "bonus": bonus, "total": player_roll + bonus},
        ]
        for target_id in self._alive_targets():
            roll = random.randint(1, 20)
            self.initiative.append({"id": target_id, "name": TRAINING_TARGETS[target_id]["name"],
                                    "roll": roll, "bonus": 0, "total": roll})
        self.initiative.sort(key=lambda row: (-row["total"], row["id"] != "player"))
        self.initialized = True
        self.log.append("Инициатива: " + " → ".join(row["name"] for row in self.initiative) + ".")
        for entry in self.initiative:
            if entry['id'] == 'player':
                break
            self.log.append(f"Раунд 1: {entry['name']} неподвижен и пропускает ход.")
        self.log.append("Тренировка началась. Перед атакой приблизьтесь к цели, если она вне дальности.")

    def remaining(self, key: str) -> int:
        return max(0, int(self.cooldowns.get(key, 0)) - self.round_number)

    def _cooldown(self, base: float, multiplier: float) -> int:
        return max(1, math.ceil(max(0, base) * max(.1, multiplier)))

    @staticmethod
    def _weapon_range(attack: dict[str, Any]) -> int:
        return {"Луки": 12, "Дротики": 6, "Волшебные посохи": 10}.get(attack.get("skill"), 1)

    def _distance(self) -> int:
        return self.grid.distance(self.player_position, self.target_positions[self.selected_target_id])

    def _alive_targets(self) -> list[str]:
        return [key for key, health in self.target_healths.items() if health > 0]

    def _target(self, target_id: str | None = None) -> dict[str, Any]:
        key = target_id or self.selected_target_id
        row = TRAINING_TARGETS[key]
        return {**row, "id": key, "health": self.target_healths[key],
                "x": self.target_positions[key][0], "y": self.target_positions[key][1]}

    def _require_action(self, distance: int) -> None:
        if not self.action_available:
            raise ValueError("Основное действие в этом ходу уже потрачено.")
        if distance == 0:
            return
        target = self.aim_point or self.target_positions[self.selected_target_id]
        actual = self.grid.distance(self.player_position, target)
        if actual > distance:
            raise ValueError(f"Цель в {actual} м, а дальность действия — {distance} м.")
        if distance > 1 and not self.grid.line_of_sight(self.player_position, target):
            raise ValueError("Линию обзора перекрывает препятствие.")

    def _roll_attack(
        self, *, name: str, accuracy: int, low: int, high: int, defense: int,
        armor: int, penetration: int = 0, multiplier: float = 1.0, damage_type: str = "физического",
        target_id: str | None = None, cover_bonus: int = 0,
    ) -> dict[str, Any]:
        target_id = target_id or self.selected_target_id
        target_name = TRAINING_TARGETS[target_id]["name"]
        roll = random.randint(1, 100)
        score = roll + accuracy - defense - cover_bonus
        if score <= 15:
            result, quality = "Промах", 0
        elif score <= 50:
            result, quality = "Скользящий удар", .5
        elif score <= 100:
            result, quality = "Попадание", 1
        else:
            result, quality = "Критическое попадание", 1.5
        self.attacks += 1
        if not quality:
            line = f"Раунд {self.round_number}: {name} по цели «{target_name}» — промах ({roll} + {accuracy} − {defense + cover_bonus})."
            self.log.append(line)
            return {"result": result, "damage": 0, "roll": roll, "line": line}
        raw = max(1, round(random.randint(max(1, low), max(low, high)) * quality * multiplier))
        effective_armor = max(0, armor - penetration)
        damage = max(1, raw - effective_armor)
        self.target_healths[target_id] = max(0, self.target_healths[target_id] - damage)
        if target_id == "dummy":
            self.dummy_health = self.target_healths[target_id]
        self.damage_total += damage
        self.hits += 1
        line = (
            f"Раунд {self.round_number}: {name} по цели «{target_name}» — {result.lower()}, {damage} {damage_type} урона "
            f"(бросок {roll}, точность {accuracy}, защита {defense + cover_bonus}, броня {effective_armor})."
        )
        if self.finished:
            line += " Манекен разрушен."
        self.log.append(line)
        return {"result": result, "damage": damage, "roll": roll, "line": line}

    def _end_turn(self) -> dict[str, Any]:
        line = f"Раунд {self.round_number}: ход персонажа завершён."
        self.log.append(line)
        player_index = next(i for i, entry in enumerate(self.initiative) if entry['id'] == 'player')
        next_entries = self.initiative[player_index + 1:] + self.initiative[:player_index]
        for entry in next_entries:
            if entry['id'] in self._alive_targets():
                self.log.append(f"{entry['name']}: тренировочная цель пропускает ход.")
        self.round_number += 1
        self.movement_remaining = BASE_MOVEMENT
        self.action_available = True
        self.disengaged = False
        return {"result": "Новый раунд", "damage": 0, "line": line}

    def _spell_cells(self, profile: dict[str, Any]) -> set[tuple[int, int]]:
        target = self.aim_point or self.target_positions[self.selected_target_id]
        targeting = profile.get("targeting", "unit")
        if targeting == "area":
            return self.grid.radius_cells(target, int(profile.get("area", 0)))
        if targeting == "line":
            return set(self.grid.line_cells(self.player_position, target, int(profile.get("range", 1))))
        if targeting == "cone":
            return self.grid.cone_cells(
                self.player_position, target, int(profile.get("range", 1)), float(profile.get("angle", 90) or 90)
            )
        if targeting == "aura":
            return self.grid.radius_cells(self.player_position, max(1, int(profile.get("area", 1))))
        if targeting == "self":
            return {self.player_position}
        return {target}

    def _spell_targets(self, profile: dict[str, Any]) -> list[str]:
        cells = self._spell_cells(profile)
        return [key for key in self._alive_targets() if self.target_positions[key] in cells]

    def act(
        self, payload: dict[str, Any], character: dict[str, Any], derived: dict[str, Any],
        spells: list[dict[str, Any]], weapon_sets: int,
    ) -> dict[str, Any]:
        previous_target = self.selected_target_id
        kind = str(payload.get("kind", ""))
        target_id = payload.get("targetId")
        try:
            if kind in {"attack", "ability", "spell"} and target_id:
                if target_id not in self._alive_targets():
                    raise ValueError("Эта цель недоступна.")
                self.selected_target_id = str(target_id)
            if kind == "spell" and "x" in payload and "y" in payload:
                point = (int(payload["x"]), int(payload["y"]))
                if not self.grid.inside(point) or point in self.grid.blocked:
                    raise ValueError("Нельзя применить заклинание в этой клетке.")
                self.aim_point = point
            return self._act(payload, character, derived, spells, weapon_sets)
        except Exception:
            self.selected_target_id = previous_target
            raise
        finally:
            self.aim_point = None

    def _act(
        self, payload: dict[str, Any], character: dict[str, Any], derived: dict[str, Any],
        spells: list[dict[str, Any]], weapon_sets: int,
    ) -> dict[str, Any]:
        self._initialize(character)
        if self.finished:
            raise ValueError("Манекен уже разрушен. Начните новую тренировку.")
        kind, name = str(payload.get("kind", "")), str(payload.get("name", ""))
        attack = derived["attack"]
        attrs = derived.get("effectiveAttributes", character.get("attributes", {}))
        multiplier = float(derived.get("cooldownMultiplier", 1))
        if kind == "select_target":
            target_id = str(payload.get("targetId", ""))
            if target_id not in self.target_healths or self.target_healths[target_id] <= 0:
                raise ValueError("Эта цель недоступна.")
            self.selected_target_id = target_id
            target = self._target()
            line = f"Выбрана цель «{target['name']}» на расстоянии {self._distance()} м."
            return {"result": "Цель выбрана", "damage": 0, "line": line}
        if kind == "move":
            target = (int(payload.get("x", -1)), int(payload.get("y", -1)))
            occupied = {self.target_positions[key] for key in self._alive_targets()}
            reachable = self.grid.reachable(self.player_position, self.movement_remaining, occupied)
            if target not in reachable or target == self.player_position:
                raise ValueError("Эта клетка недостижима в текущем ходу.")
            spent = reachable[target]
            old_position = self.player_position
            self.player_position = target
            self.movement_remaining -= spent
            line = f"Раунд {self.round_number}: персонаж перемещается на {spent} м."
            controllers = [
                key for key in self._alive_targets()
                if self.grid.distance(old_position, self.target_positions[key]) <= 1
                and self.grid.distance(target, self.target_positions[key]) > 1
            ]
            if controllers and not self.disengaged:
                attacker = TRAINING_TARGETS[controllers[0]]["name"]
                roll = random.randint(1, 100)
                dodge = int(derived.get("defenses", {}).get("Уклонение", 20))
                if roll + 35 > dodge:
                    damage = max(1, random.randint(4, 8) - int(derived.get("armor", 0)))
                    self.player_health = max(0, self.player_health - damage)
                    line += f" {attacker} проводит атаку по возможности и наносит {damage} урона."
                else:
                    line += f" {attacker} проводит атаку по возможности, но промахивается."
            self.disengaged = False
            self.log.append(line)
            return {"result": "Перемещение", "damage": 0, "line": line}
        if kind == "disengage":
            if not self.action_available:
                raise ValueError("Основное действие в этом ходу уже потрачено.")
            self.action_available = False
            self.disengaged = True
            line = f"Раунд {self.round_number}: персонаж осторожно выходит из боя; атаки по возможности отключены до конца хода."
            self.log.append(line)
            return {"result": "Отход", "damage": 0, "line": line}
        if kind in {"wait", "end_turn"}:
            return self._end_turn()
        if kind == "weapon_set":
            number = int(payload.get("number", 0))
            if not 1 <= number <= weapon_sets:
                raise ValueError("Этот комплект оружия недоступен.")
            self.active_weapon_set = number
            line = f"Раунд {self.round_number}: выбран комплект оружия {number}; основное действие не потрачено."
            self.log.append(line)
            return {"result": "Комплект сменён", "damage": 0, "line": line}
        if kind == "stance":
            stances = {
                talent["name"] for talent in character.get("talents", [])
                if str(talent.get("name", "")).startswith("Стойка:")
            }
            if name not in stances:
                raise ValueError("Эта стойка не изучена персонажем.")
            self.active_stance = name
            line = f"Раунд {self.round_number}: персонаж принимает стойку «{name.removeprefix('Стойка:').strip()}»."
            self.log.append(line)
            return {"result": "Стойка изменена", "damage": 0, "line": line}

        result: dict[str, Any]
        if kind == "attack":
            action_range = self._weapon_range(attack)
            self._require_action(action_range)
            defense_name = "Уклонение" if action_range > 1 else "Парирование"
            cover_name, cover_bonus = self.grid.cover(self.player_position, self.target_positions[self.selected_target_id])
            cover_bonus = cover_bonus if action_range > 1 else 0
            result = self._roll_attack(
                name="Обычная атака", accuracy=int(attack.get("accuracy", 0)),
                low=int(attack.get("damageMin", 1)), high=int(attack.get("damageMax", 2)),
                defense=DUMMY["defenses"][defense_name], armor=DUMMY["armor"], cover_bonus=cover_bonus,
            )
        elif kind == "ability":
            details = ABILITY_DETAILS.get(name) or MOBILITY_ABILITIES.get(name)
            owned = {talent["name"] for talent in character.get("talents", [])}
            if not details or name not in owned:
                raise ValueError("Эта способность не изучена персонажем.")
            key = f"ability:{name}"
            if self.remaining(key):
                raise ValueError(f"Способность будет готова через {self.remaining(key)} {_round_word(self.remaining(key))}.")
            action_range = RANGED_ABILITIES.get(name, 1 if name in ATTACKING_ABILITIES else 0)
            self._require_action(action_range)
            if name in MOBILITY_ABILITIES:
                destination = min(
                    (cell for cell in self.grid.neighbors(self.target_positions[self.selected_target_id])
                     if cell not in {self.target_positions[key] for key in self._alive_targets()}),
                    key=lambda cell: self.grid.distance(self.player_position, cell), default=None,
                )
                if destination is None or not self.grid.can_teleport(
                    self.player_position, destination, action_range,
                    {self.target_positions[key] for key in self._alive_targets()},
                ):
                    raise ValueError("Рядом с целью нет свободной клетки для перемещения.")
                old_position = self.player_position
                self.player_position = destination
                moved = self.grid.distance(old_position, destination)
                self.log.append(
                    f"Раунд {self.round_number}: персонаж {'телепортируется' if name == 'Удар в прыжке' else 'совершает рывок'} на {moved} м."
                )
            self.cooldowns[key] = self.round_number + self._cooldown(_number(details.get("cooldown"), 1), multiplier) + 1
            if name in ATTACKING_ABILITIES:
                damage_multiplier, penetration = ATTACKING_ABILITIES[name]
                defense_name = "Уклонение" if action_range > 1 else "Парирование"
                result = self._roll_attack(
                    name=name, accuracy=int(attack.get("accuracy", 0)) + 5,
                    low=int(attack.get("damageMin", 1)), high=int(attack.get("damageMax", 2)),
                    defense=DUMMY["defenses"][defense_name], armor=DUMMY["armor"],
                    penetration=penetration, multiplier=damage_multiplier,
                )
                movement = FORCED_MOVEMENT.get(name)
                if movement and self.target_healths[self.selected_target_id] > 0:
                    old = self.target_positions[self.selected_target_id]
                    occupied = {self.target_positions[key] for key in self._alive_targets() if key != self.selected_target_id}
                    new = self.grid.displace(self.player_position, old, movement[1], occupied, pull=movement[0] == "pull")
                    self.target_positions[self.selected_target_id] = new
                    moved = self.grid.distance(old, new)
                    if moved:
                        result["line"] += f" Цель {'притянута' if movement[0] == 'pull' else 'отброшена'} на {moved} м."
                        self.log[-1] = result["line"]
            else:
                line = f"Раунд {self.round_number}: применена способность «{name}»."
                self.log.append(line)
                result = {"result": "Способность применена", "damage": 0, "line": line}
        elif kind == "spell":
            spell = next((row for row in spells if row["name"] == name), None)
            if not spell:
                raise ValueError("Заклинание не найдено в гримуаре.")
            key = f"spell:{name}"
            if self.remaining(key):
                raise ValueError(f"Заклинание будет готово через {self.remaining(key)} {_round_word(self.remaining(key))}.")
            skill = CORE_SKILLS.get(spell.get("core"), "Знания")
            profile = spell_runtime_profile(
                spell, skill=int(character.get("skills", {}).get(skill, {}).get("value", 0)),
                wits=int(attrs.get("Смекалка", 10)), cooldown_multiplier=multiplier,
            )
            if profile["targeting"] == "unit" and self.aim_point is not None:
                target_id = next((key for key in self._alive_targets() if self.target_positions[key] == self.aim_point), None)
                if not target_id:
                    raise ValueError("Выберите вражеский токен для этого заклинания.")
                self.selected_target_id = target_id
            if profile["targeting"] in {"self", "aura"}:
                self.aim_point = self.player_position
            self._require_action(profile["range"])
            if profile["targeting"] == "self":
                self.cooldowns[key] = self.round_number + profile["cooldown"] + 1
                line = f"Раунд {self.round_number}: персонаж применяет на себя «{name}»."
                self.log.append(line)
                self.action_available = False
                return {"result": "Заклинание применено", "damage": 0, "line": line}
            affected = [target_id for target_id in self._spell_targets(profile)
                        if self.grid.cover(self.player_position, self.target_positions[target_id])[0] != "полное"]
            if not affected:
                raise ValueError("В области заклинания нет доступных целей.")
            self.cooldowns[key] = self.round_number + profile["cooldown"] + 1
            results = []
            for target_id in affected:
                cover_name, cover_bonus = self.grid.cover(self.player_position, self.target_positions[target_id])
                if cover_name == "полное":
                    continue
                results.append(self._roll_attack(
                    name=name, accuracy=profile["accuracy"], low=profile["damage_min"], high=profile["damage_max"],
                    defense=DUMMY["defenses"][profile["defense"]], armor=DUMMY["armor"],
                    penetration=profile["penetration"], damage_type=CORE_DAMAGE.get(spell.get("core"), "магического"),
                    target_id=target_id, cover_bonus=cover_bonus if profile["targeting"] in {"unit", "line"} else 0,
                ))
            if not results:
                raise ValueError("В области заклинания нет доступных целей.")
            result = {"result": results[0]["result"], "damage": sum(row["damage"] for row in results),
                      "line": " ".join(row["line"] for row in results)}
            if profile.get("enhancement") == "Столкновение":
                for target_id in affected:
                    old = self.target_positions[target_id]
                    occupied = {self.target_positions[key] for key in self._alive_targets() if key != target_id}
                    self.target_positions[target_id] = self.grid.displace(self.player_position, old, 4, occupied)
        else:
            raise ValueError("Неизвестное тренировочное действие.")
        if self.target_healths.get(self.selected_target_id, 0) <= 0 and self._alive_targets():
            self.selected_target_id = self._alive_targets()[0]
        self.action_available = False
        return result

    def view(
        self, character: dict[str, Any], derived: dict[str, Any], spells: list[dict[str, Any]],
        weapon_sets: int,
    ) -> dict[str, Any]:
        self._initialize(character)
        attack = derived.get("attack", {})
        attrs = derived.get("effectiveAttributes", character.get("attributes", {}))
        owned = {talent["name"] for talent in character.get("talents", [])}
        stances = [
            {"name": talent["name"], "description": talent.get("description", ""),
             "icon": (ABILITY_DETAILS.get(talent["name"]) or {}).get("icon", "")}
            for talent in character.get("talents", [])
            if str(talent.get("name", "")).startswith("Стойка:")
        ]
        distance, weapon_range = self._distance(), self._weapon_range(attack)
        selected_target = self._target()
        cover_name, cover_bonus = self.grid.cover(self.player_position, self.target_positions[self.selected_target_id])

        def reason(action_range: int) -> str:
            if not self.action_available:
                return "Основное действие потрачено"
            if action_range == 0:
                return ""
            if action_range > 1 and cover_name == "полное":
                return "Цель полностью закрыта от прямой видимости"
            return f"Цель вне дальности: {distance}/{action_range} м" if distance > action_range else ""

        actions = [{"kind": "attack", "name": "Обычная атака", "description": "Атака активным оружейным комплектом.",
                    "remaining": 0, "range": weapon_range, "disabledReason": reason(weapon_range),
                    "cells": [{"x": selected_target["x"], "y": selected_target["y"]}]}]
        for name, details in {**ABILITY_DETAILS, **MOBILITY_ABILITIES}.items():
            if name in owned:
                action_range = RANGED_ABILITIES.get(name, 1 if name in ATTACKING_ABILITIES else 0)
                actions.append({"kind": "ability", "name": name, "description": details.get("description", ""),
                                "targeting": "unit" if action_range else "self",
                                "icon": details.get("icon", ""), "remaining": self.remaining(f"ability:{name}"),
                                "cooldown": details.get("cooldown", "Не указана"), "range": action_range,
                                "disabledReason": reason(action_range),
                                "cells": [{"x": selected_target["x"], "y": selected_target["y"]}]})
        for spell in spells:
            skill = CORE_SKILLS.get(spell.get("core"), "Знания")
            profile = spell_runtime_profile(
                spell, skill=int(character.get("skills", {}).get(skill, {}).get("value", 0)),
                wits=int(attrs.get("Смекалка", 10)), cooldown_multiplier=float(derived.get("cooldownMultiplier", 1)),
            )
            actions.append({"kind": "spell", "name": spell["name"],
                            "core": spell["core"], "angle": profile.get("angle", 90),
                            "cooldown": profile["cooldown"], "damageMin": profile["damage_min"],
                            "damageMax": profile["damage_max"], "defense": profile["defense"],
                            "description": f"{spell['core']} + {spell['expression']}",
                            "remaining": self.remaining(f"spell:{spell['name']}"), "range": profile["range"],
                            "area": profile["area"], "targeting": profile["targeting"],
                            "disabledReason": "Основное действие потрачено" if not self.action_available else "",
                            "cells": [{"x": x, "y": y} for x, y in self._spell_cells(profile)]})

        controlled = self.grid.control_zone(self.target_positions[key] for key in self._alive_targets())
        if self.player_position in controlled:
            actions.insert(0, {"kind": "disengage", "name": "Осторожный отход",
                               "description": "Отключает атаки по возможности до конца текущего хода.",
                               "remaining": 0, "range": 0,
                               "disabledReason": "Основное действие потрачено" if not self.action_available else "",
                                "cells": []})

        # The client previews these server-computed shapes without spending an action.
        for action in actions:
            action["aims"] = {}
            for y in range(self.grid.height):
                for x in range(self.grid.width):
                    point = (x, y)
                    self.aim_point = point
                    targeting = action.get("targeting", "unit")
                    shape = self._spell_cells(action) if action["kind"] == "spell" else {point}
                    effective_point = self.player_position if targeting in {"self", "aura"} else point
                    valid = self.grid.distance(self.player_position, effective_point) <= action.get("range", 0)
                    valid = valid and point not in self.grid.blocked and self.grid.line_of_sight(self.player_position, effective_point)
                    if targeting == "unit":
                        valid = valid and any(self.target_positions[key] == point for key in self._alive_targets())
                    if targeting in {"self", "aura"}:
                        valid = valid and point == self.player_position
                    if action["kind"] == "spell" and targeting != "self":
                        valid = valid and any(self.target_positions[key] in shape and
                            self.grid.cover(self.player_position, self.target_positions[key])[0] != "полное"
                            for key in self._alive_targets())
                    action["aims"][f"{x}:{y}"] = {"valid": valid, "cells": [{"x": cx, "y": cy} for cx, cy in sorted(shape)]}
            self.aim_point = None

        map_spec = TACTICAL_MAPS[self.map_key]
        occupied = {self.target_positions[key] for key in self._alive_targets()}
        reachable = self.grid.reachable(self.player_position, self.movement_remaining, occupied)
        grid_payload = self.grid.payload()
        grid_payload.update({
            "name": map_spec["name"], "image": map_spec["image"], "source": map_spec["source"],
            "movementPerTurn": BASE_MOVEMENT,
            "reachable": [{"x": x, "y": y, "cost": cost} for (x, y), cost in reachable.items() if cost],
            "controlZones": [{"x": x, "y": y} for x, y in controlled],
            "selectedTargetId": self.selected_target_id,
            "tokens": [
                {"id": "player", "name": character["name"], "team": "player", "x": self.player_position[0],
                 "y": self.player_position[1], "portraitUrl": character.get("portrait_url", ""), "active": True,
                 "health": self.player_health, "healthMax": self.player_health_max},
                *[{"id": key, "name": TRAINING_TARGETS[key]["name"], "team": "enemy",
                   "x": self.target_positions[key][0], "y": self.target_positions[key][1],
                   "active": key == self.selected_target_id, "selected": key == self.selected_target_id,
                   "health": self.target_healths[key], "healthMax": TRAINING_TARGETS[key]["healthMax"]}
                  for key in self._alive_targets()],
            ],
        })
        return {
            "active": True, "finished": self.finished, "round": self.round_number,
            "dummy": selected_target,
            "targets": [self._target(key) for key in self._alive_targets()],
            "character": {"name": character["name"], "portraitUrl": character.get("portrait_url", ""),
                          "health": self.player_health, "healthMax": self.player_health_max,
                          "activeWeaponSet": self.active_weapon_set, "weaponSets": weapon_sets},
            "turn": {"actorId": "player", "movementRemaining": self.movement_remaining,
                     "movementMax": BASE_MOVEMENT, "actionAvailable": self.action_available,
                     "distanceToTarget": distance, "inControlZone": self.player_position in controlled,
                     "cover": cover_name, "coverBonus": cover_bonus, "disengaged": self.disengaged},
            "initiative": self.initiative, "grid": grid_payload,
            "derived": derived, "actions": actions, "stances": stances, "activeStance": self.active_stance,
            "cooldowns": self.cooldowns,
            "log": self.log[-40:][::-1],
            "summary": {"damage": self.damage_total, "attacks": self.attacks, "hits": self.hits,
                        "accuracy": round(self.hits / self.attacks * 100) if self.attacks else 0},
            "rewards": {"experience": 0, "skillExperience": 0, "loot": []},
        }
