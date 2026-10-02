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

ATTACKING_ABILITIES = {
    "Удар щитом": (1.0, 0), "Раскол": (1.5, 0), "Секущий удар": (.8, 5),
    "Выстрел в сердце": (1.2, 0), "Хромота": (1.0, 0), "Шквал ударов": (2.0, 0),
    "Рассечение": (1.2, 0), "Удар ладонью": (1.0, 0), "Заряженный кулак": (1.0, 2),
    "Ледяная хватка": (1.0, 1),
}
RANGED_ABILITIES = {"Выстрел в сердце": 12, "Хромота": 10}

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

    def __post_init__(self) -> None:
        spec = TACTICAL_MAPS[self.map_key]
        self.grid = TacticalGrid(spec["width"], spec["height"], set(spec["blocked"]))

    @property
    def finished(self) -> bool:
        return self.dummy_health <= 0

    def _initialize(self, character: dict[str, Any]) -> None:
        if self.initialized:
            return
        quickness = int(character.get("attributes", {}).get("Быстрота", 10))
        bonus = initiative_bonus(quickness)
        player_roll, dummy_roll = random.randint(1, 20), random.randint(1, 20)
        self.initiative = [
            {"id": "player", "name": character.get("name", "Персонаж"), "roll": player_roll,
             "bonus": bonus, "total": player_roll + bonus},
            {"id": "dummy", "name": DUMMY["name"], "roll": dummy_roll, "bonus": 0, "total": dummy_roll},
        ]
        self.initiative.sort(key=lambda row: (-row["total"], row["id"] != "player"))
        self.initialized = True
        self.log.append("Инициатива: " + " → ".join(row["name"] for row in self.initiative) + ".")
        if self.initiative[0]["id"] == "dummy":
            self.log.append("Раунд 1: манекен неподвижен и пропускает ход.")
        self.log.append("Тренировка началась. Перед атакой приблизьтесь к цели, если она вне дальности.")

    def remaining(self, key: str) -> int:
        return max(0, int(self.cooldowns.get(key, 0)) - self.round_number)

    def _cooldown(self, base: float, multiplier: float) -> int:
        return max(1, math.ceil(max(0, base) * max(.1, multiplier)))

    @staticmethod
    def _weapon_range(attack: dict[str, Any]) -> int:
        return {"Луки": 12, "Дротики": 6, "Волшебные посохи": 10}.get(attack.get("skill"), 1)

    def _distance(self) -> int:
        return self.grid.distance(self.player_position, self.dummy_position)

    def _require_action(self, distance: int) -> None:
        if not self.action_available:
            raise ValueError("Основное действие в этом ходу уже потрачено.")
        if distance == 0:
            return
        actual = self._distance()
        if actual > distance:
            raise ValueError(f"Цель в {actual} м, а дальность действия — {distance} м.")
        if distance > 1 and not self.grid.line_of_sight(self.player_position, self.dummy_position):
            raise ValueError("Линию обзора перекрывает препятствие.")

    def _roll_attack(
        self, *, name: str, accuracy: int, low: int, high: int, defense: int,
        armor: int, penetration: int = 0, multiplier: float = 1.0, damage_type: str = "физического",
    ) -> dict[str, Any]:
        roll = random.randint(1, 100)
        score = roll + accuracy - defense
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
            line = f"Раунд {self.round_number}: {name} — промах ({roll} + {accuracy} − {defense})."
            self.log.append(line)
            return {"result": result, "damage": 0, "roll": roll, "line": line}
        raw = max(1, round(random.randint(max(1, low), max(low, high)) * quality * multiplier))
        effective_armor = max(0, armor - penetration)
        damage = max(1, raw - effective_armor)
        self.dummy_health = max(0, self.dummy_health - damage)
        self.damage_total += damage
        self.hits += 1
        line = (
            f"Раунд {self.round_number}: {name} — {result.lower()}, {damage} {damage_type} урона "
            f"(бросок {roll}, точность {accuracy}, защита {defense}, броня {effective_armor})."
        )
        if self.finished:
            line += " Манекен разрушен."
        self.log.append(line)
        return {"result": result, "damage": damage, "roll": roll, "line": line}

    def _end_turn(self) -> dict[str, Any]:
        line = f"Раунд {self.round_number}: ход завершён. Манекен остаётся неподвижен."
        self.log.append(line)
        self.round_number += 1
        self.movement_remaining = BASE_MOVEMENT
        self.action_available = True
        return {"result": "Новый раунд", "damage": 0, "line": line}

    def act(
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
        if kind == "move":
            target = (int(payload.get("x", -1)), int(payload.get("y", -1)))
            reachable = self.grid.reachable(self.player_position, self.movement_remaining, {self.dummy_position})
            if target not in reachable or target == self.player_position:
                raise ValueError("Эта клетка недостижима в текущем ходу.")
            spent = reachable[target]
            self.player_position = target
            self.movement_remaining -= spent
            line = f"Раунд {self.round_number}: персонаж перемещается на {spent} м."
            self.log.append(line)
            return {"result": "Перемещение", "damage": 0, "line": line}
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

        result: dict[str, Any]
        if kind == "attack":
            action_range = self._weapon_range(attack)
            self._require_action(action_range)
            defense_name = "Уклонение" if action_range > 1 else "Парирование"
            result = self._roll_attack(
                name="Обычная атака", accuracy=int(attack.get("accuracy", 0)),
                low=int(attack.get("damageMin", 1)), high=int(attack.get("damageMax", 2)),
                defense=DUMMY["defenses"][defense_name], armor=DUMMY["armor"],
            )
        elif kind == "ability":
            details = ABILITY_DETAILS.get(name)
            owned = {talent["name"] for talent in character.get("talents", [])}
            if not details or name not in owned:
                raise ValueError("Эта способность не изучена персонажем.")
            key = f"ability:{name}"
            if self.remaining(key):
                raise ValueError(f"Способность будет готова через {self.remaining(key)} {_round_word(self.remaining(key))}.")
            action_range = RANGED_ABILITIES.get(name, 1 if name in ATTACKING_ABILITIES else 0)
            self._require_action(action_range)
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
            self._require_action(profile["range"])
            self.cooldowns[key] = self.round_number + profile["cooldown"] + 1
            result = self._roll_attack(
                name=name, accuracy=profile["accuracy"], low=profile["damage_min"], high=profile["damage_max"],
                defense=DUMMY["defenses"][profile["defense"]], armor=DUMMY["armor"],
                penetration=profile["penetration"], damage_type=CORE_DAMAGE.get(spell.get("core"), "магического"),
            )
        else:
            raise ValueError("Неизвестное тренировочное действие.")
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
        distance, weapon_range = self._distance(), self._weapon_range(attack)

        def reason(action_range: int) -> str:
            if not self.action_available:
                return "Основное действие потрачено"
            if action_range == 0:
                return ""
            return f"Цель вне дальности: {distance}/{action_range} м" if distance > action_range else ""

        actions = [{"kind": "attack", "name": "Обычная атака", "description": "Атака активным оружейным комплектом.",
                    "remaining": 0, "range": weapon_range, "disabledReason": reason(weapon_range)}]
        for name, details in ABILITY_DETAILS.items():
            if name in owned:
                action_range = RANGED_ABILITIES.get(name, 1 if name in ATTACKING_ABILITIES else 0)
                actions.append({"kind": "ability", "name": name, "description": details.get("description", ""),
                                "icon": details.get("icon", ""), "remaining": self.remaining(f"ability:{name}"),
                                "cooldown": details.get("cooldown", "Не указана"), "range": action_range,
                                "disabledReason": reason(action_range)})
        for spell in spells:
            skill = CORE_SKILLS.get(spell.get("core"), "Знания")
            profile = spell_runtime_profile(
                spell, skill=int(character.get("skills", {}).get(skill, {}).get("value", 0)),
                wits=int(attrs.get("Смекалка", 10)), cooldown_multiplier=float(derived.get("cooldownMultiplier", 1)),
            )
            actions.append({"kind": "spell", "name": spell["name"],
                            "description": f"{spell['core']} + {spell['expression']}",
                            "remaining": self.remaining(f"spell:{spell['name']}"), "range": profile["range"],
                            "area": profile["area"], "targeting": profile["targeting"],
                            "disabledReason": reason(profile["range"])})

        map_spec = TACTICAL_MAPS[self.map_key]
        reachable = self.grid.reachable(self.player_position, self.movement_remaining, {self.dummy_position})
        grid_payload = self.grid.payload()
        grid_payload.update({
            "name": map_spec["name"], "image": map_spec["image"], "source": map_spec["source"],
            "movementPerTurn": BASE_MOVEMENT,
            "reachable": [{"x": x, "y": y, "cost": cost} for (x, y), cost in reachable.items() if cost],
            "tokens": [
                {"id": "player", "name": character["name"], "team": "player", "x": self.player_position[0],
                 "y": self.player_position[1], "portraitUrl": character.get("portrait_url", ""), "active": True,
                 "health": character.get("health", 0), "healthMax": character.get("health_max", 0)},
                {"id": "dummy", "name": DUMMY["name"], "team": "enemy", "x": self.dummy_position[0],
                 "y": self.dummy_position[1], "active": False, "health": self.dummy_health,
                 "healthMax": DUMMY["healthMax"]},
            ],
        })
        return {
            "active": True, "finished": self.finished, "round": self.round_number,
            "dummy": {**DUMMY, "health": self.dummy_health},
            "character": {"name": character["name"], "portraitUrl": character.get("portrait_url", ""),
                          "activeWeaponSet": self.active_weapon_set, "weaponSets": weapon_sets},
            "turn": {"actorId": "player", "movementRemaining": self.movement_remaining,
                     "movementMax": BASE_MOVEMENT, "actionAvailable": self.action_available,
                     "distanceToTarget": distance},
            "initiative": self.initiative, "grid": grid_payload,
            "derived": derived, "actions": actions, "cooldowns": self.cooldowns,
            "log": self.log[-40:][::-1],
            "summary": {"damage": self.damage_total, "attacks": self.attacks, "hits": self.hits,
                        "accuracy": round(self.hits / self.attacks * 100) if self.attacks else 0},
            "rewards": {"experience": 0, "skillExperience": 0, "loot": []},
        }
