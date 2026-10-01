"""Серверная пошаговая тренировка персонажа против неподвижного манекена."""

from __future__ import annotations

import math
import random
import re
from dataclasses import dataclass, field
from typing import Any

from constants import ABILITY_DETAILS
from sigil_data import spell_runtime_profile


DUMMY = {
    "name": "Укреплённый тренировочный манекен",
    "healthMax": 180,
    "armor": 4,
    "defenses": {"Парирование": 35, "Уклонение": 30, "Выносливость": 32, "Воля": 28, "Магия": 32},
}

ATTACKING_ABILITIES = {
    "Удар щитом": (1.0, 0), "Раскол": (1.5, 0), "Секущий удар": (.8, 5),
    "Выстрел в сердце": (1.2, 0),
    "Хромота": (1.0, 0), "Шквал ударов": (2.0, 0), "Режущий удар": (1.2, 0),
    "Удар ладонью": (1.0, 0), "Заряженный кулак": (1.0, 2), "Ледяная хватка": (1.0, 1),
}

CORE_SKILLS = {
    "Истощение": "Управление истощением", "Эмоции": "Управление рвением",
    "Огонь": "Управление огнём", "Сила": "Управление силой",
    "Холод": "Управление холодом", "Иллюзия": "Управление иллюзиями",
    "Жизнь": "Управление жизнью", "Молния": "Управление молниями",
    "Камень": "Управление камнем", "Терратус": "Управление могильным светом",
    "Энергия": "Управление энергией",
}

CORE_DAMAGE = {
    "Огонь": "огненного", "Холод": "ледяного", "Молния": "электрического",
    "Сила": "дробящего", "Камень": "дробящего", "Жизнь": "магического",
    "Истощение": "магического", "Эмоции": "магического", "Иллюзия": "магического",
    "Терратус": "магического", "Энергия": "магического",
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
    log: list[str] = field(default_factory=lambda: ["Тренировка началась. Манекен ожидает первого удара."])

    @property
    def finished(self) -> bool:
        return self.dummy_health <= 0

    def remaining(self, key: str) -> int:
        return max(0, int(self.cooldowns.get(key, 0)) - self.round_number)

    def _cooldown(self, base: float, multiplier: float) -> int:
        return max(1, math.ceil(max(0, base) * max(.1, multiplier)))

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

    def act(
        self, payload: dict[str, Any], character: dict[str, Any], derived: dict[str, Any],
        spells: list[dict[str, Any]], weapon_sets: int,
    ) -> dict[str, Any]:
        if self.finished:
            raise ValueError("Манекен уже разрушен. Начните новую тренировку.")
        kind = str(payload.get("kind", ""))
        name = str(payload.get("name", ""))
        attack = derived["attack"]
        attrs = derived.get("effectiveAttributes", character.get("attributes", {}))
        multiplier = float(derived.get("cooldownMultiplier", 1))
        result: dict[str, Any]
        if kind == "attack":
            defense_name = "Уклонение" if attack.get("skill") in {"Луки", "Дротики"} else "Парирование"
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
            base = _number(details.get("cooldown"), 1)
            cooldown = self._cooldown(base, multiplier)
            self.cooldowns[key] = self.round_number + cooldown + 1
            if name in ATTACKING_ABILITIES:
                damage_multiplier, penetration = ATTACKING_ABILITIES[name]
                defense_name = "Магия" if "Заклинание" in details.get("type", "") else (
                    "Уклонение" if attack.get("skill") in {"Луки", "Дротики"} else "Парирование"
                )
                result = self._roll_attack(
                    name=name, accuracy=int(attack.get("accuracy", 0)) + 5,
                    low=int(attack.get("damageMin", 1)), high=int(attack.get("damageMax", 2)),
                    defense=DUMMY["defenses"][defense_name], armor=DUMMY["armor"],
                    penetration=penetration, multiplier=damage_multiplier,
                    damage_type="магического" if defense_name == "Магия" else "физического",
                )
            else:
                line = f"Раунд {self.round_number}: применена способность «{name}». Эффект записан без урона по манекену."
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
                spell,
                skill=int(character.get("skills", {}).get(skill, {}).get("value", 0)),
                wits=int(attrs.get("Смекалка", 10)),
                cooldown_multiplier=multiplier,
            )
            cooldown = profile["cooldown"]
            self.cooldowns[key] = self.round_number + cooldown + 1
            result = self._roll_attack(
                name=name, accuracy=profile["accuracy"], low=profile["damage_min"],
                high=profile["damage_max"], defense=DUMMY["defenses"][profile["defense"]],
                armor=DUMMY["armor"], penetration=profile["penetration"],
                damage_type=CORE_DAMAGE.get(spell.get("core"), "магического"),
            )
        elif kind == "weapon_set":
            number = int(payload.get("number", 0))
            if not 1 <= number <= weapon_sets:
                raise ValueError("Этот комплект оружия недоступен.")
            self.active_weapon_set = number
            line = f"Раунд {self.round_number}: выбран комплект оружия {number}."
            self.log.append(line)
            result = {"result": "Комплект сменён", "damage": 0, "line": line}
        elif kind == "wait":
            line = f"Раунд {self.round_number}: персонаж выжидает и сохраняет позицию."
            self.log.append(line)
            result = {"result": "Ход пропущен", "damage": 0, "line": line}
        else:
            raise ValueError("Неизвестное тренировочное действие.")
        # Восстановление экипировки из оригинала становится задержкой хода:
        # каждые десять секунд равны одному полному раунду.
        action_delay = 1 if kind in {"weapon_set", "wait"} else max(
            1, math.ceil(float(attack.get("recovery", 0) or 0) / 10)
        )
        self.round_number += action_delay
        if action_delay > 1:
            self.log.append(f"Тяжёлая экипировка задерживает следующее действие на {action_delay} {_round_word(action_delay)}.")
        return result

    def view(
        self, character: dict[str, Any], derived: dict[str, Any], spells: list[dict[str, Any]],
        weapon_sets: int,
    ) -> dict[str, Any]:
        owned = {talent["name"] for talent in character.get("talents", [])}
        actions = [{"kind": "attack", "name": "Обычная атака", "description": "Атака активным оружейным комплектом.", "remaining": 0}]
        for name, details in ABILITY_DETAILS.items():
            if name in owned:
                actions.append({
                    "kind": "ability", "name": name, "description": details.get("description", ""),
                    "icon": details.get("icon", ""), "remaining": self.remaining(f"ability:{name}"),
                    "cooldown": details.get("cooldown", "Не указана"),
                })
        for spell in spells:
            actions.append({
                "kind": "spell", "name": spell["name"],
                "description": f"{spell['core']} + {spell['expression']}",
                "remaining": self.remaining(f"spell:{spell['name']}"),
            })
        return {
            "active": True, "finished": self.finished, "round": self.round_number,
            "dummy": {**DUMMY, "health": self.dummy_health},
            "character": {
                "name": character["name"], "portraitUrl": character.get("portrait_url", ""),
                "activeWeaponSet": self.active_weapon_set, "weaponSets": weapon_sets,
            },
            "derived": derived, "actions": actions, "cooldowns": self.cooldowns,
            "log": self.log[-30:][::-1],
            "summary": {
                "damage": self.damage_total, "attacks": self.attacks, "hits": self.hits,
                "accuracy": round(self.hits / self.attacks * 100) if self.attacks else 0,
            },
            "rewards": {"experience": 0, "skillExperience": 0, "loot": []},
        }
