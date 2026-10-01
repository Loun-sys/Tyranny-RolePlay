"""Канонические русские данные конструктора заклинаний Tyranny.

Сигил хранится у персонажа по стабильному ключу. Это позволяет отличать уровни
одного акцента и не привязывает сохранения к отображаемому переводу.
"""

from __future__ import annotations

import math
import re
from urllib.parse import unquote, urlparse


WIKI = "https://tyranny.fandom.com/wiki/"


def _image(filename: str) -> str:
    safe_name = re.sub(r"[^a-z0-9]+", "-", filename.casefold()).strip("-")
    return f"assets/sigil-icons/{safe_name}.png"


def _page(slug: str) -> str:
    return f"{WIKI}Sigil_of_{slug}"


def _entry(
    kind: str, name: str, slug: str, effect: str, image: str, lore: int = 0,
    *, tier: int = 0, compatible_cores: tuple[str, ...] = (),
    compatible_expressions: tuple[str, ...] = (), family: str = "",
) -> dict:
    key = f"{kind}:{family or name}" + (f":{tier}" if tier else "")
    return {
        "key": key, "type": kind, "name": name, "family": family or name,
        "tier": tier, "lore": lore, "effect": effect, "image_url": _image(image), "wiki_image": image,
        "source_url": _page(slug), "compatibleCores": list(compatible_cores),
        "compatibleExpressions": list(compatible_expressions),
    }


CORE_ROWS = (
    ("Истощение", "Atrophy", "Ослабляет тело и волю противника.", "Core-Weaken.png"),
    ("Эмоции", "Emotions", "Подчиняет эмоции, страх и ярость цели.", "Core-Passion.png"),
    ("Огонь", "Fire", "Создаёт пламя и ожоги.", "Core-Fire.png"),
    ("Сила", "Force", "Управляет кинетической силой, толчками и сокрушением.", "Core-Gravity.png"),
    ("Холод", "Frost", "Создаёт лёд, мороз и замедление.", "Core-Frost.png"),
    ("Иллюзия", "Illusion", "Искажает восприятие и вводит врагов в заблуждение.", "Core-Illusion.png"),
    ("Жизнь", "Life", "Исцеляет и укрепляет живых существ.", "Core-Heal.png"),
    ("Молния", "Lightning", "Поражает электричеством и оглушает.", "Core-Shock.png"),
    ("Камень", "Stone", "Подчиняет землю и камень.", "Core-Stone.png"),
    ("Терратус", "Terratus", "Проводит свет и тьму Терратуса.", "Core-Gravelight.png"),
    ("Энергия", "Vigor", "Усиливает тело, оружие и боевой дух.", "Core-Strength.png"),
)

CORES = [_entry("core", name, slug, effect, image) for name, slug, effect, image in CORE_ROWS]

EXPRESSION_ROWS = (
    ("Область влияния", "Influential_Domain", "Круговая область вокруг выбранной точки.", "Shape-Field.png", 90,
     ("Холод", "Эмоции", "Огонь", "Жизнь")),
    ("Направленная сила", "Directed_Force", "Линия, проходящая через несколько целей.", "Shape-Trap.png", 70,
     ("Холод", "Камень", "Огонь", "Истощение", "Молния")),
    ("Хаотическое нисхождение", "Chaotic_Descent", "Дождь по случайным целям в области.", "Shape-Rain.png", 100,
     ("Камень", "Огонь", "Молния", "Истощение")),
    ("Сосредоточенное намерение", "Focused_Intent", "Одна цель рядом с заклинателем.", "SPELL LightningTouch L.png", 15,
     ("Иллюзия", "Энергия", "Холод", "Эмоции", "Камень", "Огонь", "Молния", "Жизнь", "Терратус", "Истощение")),
    ("Проводимая сила", "Channeled_Strength", "Конус, исходящий от заклинателя.", "Shape-Cone.png", 35,
     ("Иллюзия", "Энергия", "Холод", "Сила", "Эмоции", "Огонь", "Молния", "Терратус", "Истощение")),
    ("Охранная форма", "Guarded_Form", "Накладывает магическое воздействие на броню.", "Shape-Armor.png", 60,
     ("Иллюзия", "Энергия", "Холод", "Сила", "Камень", "Огонь", "Молния", "Жизнь")),
    ("Материальная сила", "Material_Force", "Накладывает магическое воздействие на оружие.", "Shape-Weapon.png", 50,
     ("Энергия", "Холод", "Камень", "Огонь", "Молния", "Терратус")),
    ("Ближнее действие", "Proximate_Action", "Создаёт ауру вокруг цели.", "Shape-Aura.png", 80,
     ("Энергия", "Сила", "Эмоции", "Камень", "Огонь", "Жизнь", "Терратус", "Истощение")),
    ("Дальний удар", "Distant_Impact", "Дальний магический снаряд с небольшой областью поражения.", "Shape-Bolt.png", 30,
     ("Иллюзия", "Холод", "Сила", "Эмоции", "Камень", "Огонь", "Молния", "Жизнь", "Терратус")),
)

EXPRESSIONS = [
    _entry("expression", name, slug, effect, image, lore, compatible_cores=cores)
    for name, slug, effect, image, lore, cores in EXPRESSION_ROWS
]

ACCENT_ROWS = (
    ("Прыгающие заряды", "Bounding_Bolts", "SPELLMOD chain", ((1, 30, "+1 снаряд с рикошетом в радиусе 5 м"), (2, 50, "+2 снаряда с рикошетом в радиусе 5 м"))),
    ("Циклические энергии", "Cyclical_Energies", "SPELLMOD recovery", ((1, 10, "Перезарядка −15%"), (2, 20, "Перезарядка −25%"), (3, 30, "Перезарядка −35%"), (4, 40, "Перезарядка −45%"))),
    ("Безграничные пределы", "Limitless_Boundaries", "SPELLMOD aoe", ((1, 25, "Область действия +1 м"), (2, 35, "Область действия +2 м"), (3, 45, "Область действия +3 м"))),
    ("Пробивающая сила", "Piercing_Strength", "SPELLMOD dt", ((1, 15, "+4 к пробиванию брони"), (2, 30, "+8 к пробиванию брони"), (3, 45, "+12 к пробиванию брони"))),
    ("Точное действие", "Precise_Action", "SPELLMOD accuracy", ((1, 15, "Точность +15"), (2, 25, "Точность +30"), (3, 35, "Точность +45"), (4, 45, "Точность +60"))),
    ("Длинная хватка", "Reaching_Grasp", "SPELLMOD range", ((1, 10, "Дальность +2 м"), (2, 20, "Дальность +4 м"), (3, 30, "Дальность +6 м"))),
    ("Ошеломляющая сила", "Staggering_Force", "SPELLMOD interrupt", ((1, 25, "Слабое прерывание"), (2, 35, "Среднее прерывание"), (3, 45, "Сильное прерывание"))),
    ("Мощность", "Strength", "SPELLMOD intensity", ((1, 20, "Сила эффектов +20%"), (2, 30, "Сила эффектов +30%"), (3, 40, "Сила эффектов +40%"), (4, 50, "Сила эффектов +50%"))),
    ("Вневременная форма", "Timeless_Form", "SPELLMOD duration", ((1, 15, "Длительность +25%"), (2, 25, "Длительность +35%"), (3, 35, "Длительность +45%"))),
)

ACCENTS: list[dict] = []
for family, slug, filename, levels in ACCENT_ROWS:
    for tier, lore, effect in levels:
        ACCENTS.append(_entry(
            "accent", f"{family} {tier}", slug, effect, f"{filename} i.png", lore,
            tier=tier, family=family,
        ))

ENHANCEMENT_ROWS = (
    ("Кровотечение", "Bleeding", "Добавляет кровотечение на 1 раунд.", 25),
    ("Магия крови", "Blood_Magic", "+30% урона; заклинатель получает не менее 15 чистого урона.", 20),
    ("Дезориентация", "Dazing", "Добавляет дезориентацию на 1 раунд.", 25),
    ("Отклонение", "Deflecting", "Получаемый критический урон −15% на время действия.", 25),
    ("Сосредоточенный дождь", "Focused_Rain", "+50% снарядов; область действия −50%.", 25),
    ("Ледяное пламя", "Frostfire", "Добавляет урон огнём и холодом, а также соответствующие состояния.", 35),
    ("Столкновение", "Impact", "Добавляет отбрасывание на 4 м.", 25),
    ("Добивающие удары", "Killing_Blows", "До 50 дополнительного урона раненым врагам.", 25),
    ("Метка", "Marking", "Добавляет состояние «Метка» на 2 раунда.", 25),
    ("Фазирование", "Phasing", "Накладывает стазис: паралич и неуязвимость примерно на 1,2 раунда.", 25),
    ("Пронзание", "Piercing", "Снаряд дальнего удара проходит сквозь цели по линии.", 30),
    ("Магия гордыни", "Pride_Magic", "Действует только на самого персонажа; сила эффектов +50%.", 35),
    ("Быстрое сотворение", "Rapid_Casting", "У заклинания отсутствует восстановление после применения.", 25),
    ("Обездвиживание", "Rooting", "Добавляет обездвиживание примерно на 1,2 раунда.", 25),
    ("Самоотверженная магия", "Selfless_Magic", "Действует только на союзников; сила эффектов +50%.", 35),
    ("Всплеск заклинаний", "Spellsurge", "Общее восстановление −10% на 0,6 раунда.", 30),
    ("Оглушение", "Stunning", "Добавляет состояние «Оглушение».", 25),
    ("Вулканическое оружие", "Volcanic_Weapon", "Оружие выпускает линию огненного урона.", 25),
    ("Залпы", "Volleys", "+2 снаряда.", 35),
    ("Дикая магия", "Wild_Magic", "При каждом применении выбирается случайный тип урона.", 20),
    ("Магическое усиление", "Magic_Boost", "Усиливает магические эффекты формулы.", 35),
    ("Внезапная смерть", "Sudden_Death", "Даёт формуле шанс мгновенно добить тяжело раненую цель.", 0),
)

_ENH_COMPAT = {
    "Отклонение": {"expressions": ("Охранная форма",)},
    "Сосредоточенный дождь": {"expressions": ("Хаотическое нисхождение",)},
    "Ледяное пламя": {"cores": ("Огонь", "Холод")},
    "Фазирование": {"cores": ("Терратус", "Иллюзия")},
    "Пронзание": {"expressions": ("Дальний удар",)},
    "Магия гордыни": {"expressions": ("Материальная сила", "Охранная форма")},
    "Быстрое сотворение": {"expressions": ("Материальная сила", "Охранная форма")},
    "Самоотверженная магия": {"expressions": ("Материальная сила", "Охранная форма")},
    "Оглушение": {"cores": ("Молния",)},
    "Вулканическое оружие": {"expressions": ("Материальная сила",)},
}

ENHANCEMENTS = []
_ENHANCEMENT_IMAGES = {
    "Killing_Blows": "Secondary killing blow.png", "Volleys": "Secondary volley.png",
    "Magic_Boost": "SPELLMOD intensity i.png",
}
for name, slug, effect, lore in ENHANCEMENT_ROWS:
    compatibility = _ENH_COMPAT.get(name, {})
    ENHANCEMENTS.append(_entry(
        "enhancement", name, slug, effect,
        _ENHANCEMENT_IMAGES.get(slug, f"Secondary {slug.replace('_', ' ').lower()}.png"), lore,
        compatible_cores=compatibility.get("cores", ()),
        compatible_expressions=compatibility.get("expressions", ()),
    ))

SIGIL_LIBRARY = [*CORES, *EXPRESSIONS, *ACCENTS, *ENHANCEMENTS]
SIGILS_BY_KEY = {entry["key"]: entry for entry in SIGIL_LIBRARY}

_BY_TYPE_NAME: dict[tuple[str, str], list[dict]] = {}
for _sigil in SIGIL_LIBRARY:
    _BY_TYPE_NAME.setdefault((_sigil["type"], _sigil["name"].casefold()), []).append(_sigil)
    _BY_TYPE_NAME.setdefault((_sigil["type"], _sigil["family"].casefold()), []).append(_sigil)

_ENGLISH_TO_RUSSIAN = {slug: name for name, slug, *_ in CORE_ROWS}
_ENGLISH_TO_RUSSIAN.update({slug: name for name, slug, *_ in EXPRESSION_ROWS})
_ENGLISH_TO_RUSSIAN.update({slug: name for name, slug, *_ in ACCENT_ROWS})
_ENGLISH_TO_RUSSIAN.update({slug: name for name, slug, *_ in ENHANCEMENT_ROWS})
_ENGLISH_TO_RUSSIAN.update({"Passion": "Эмоции", "Regeneration": "Жизнь", "Piercing_Force": "Пробивающая сила"})


def sigil_by_reference(reference: str, kind: str | None = None) -> dict | None:
    if reference in SIGILS_BY_KEY:
        result = SIGILS_BY_KEY[reference]
        return result if not kind or result["type"] == kind else None
    candidates = _BY_TYPE_NAME.get((kind or "", reference.casefold()), []) if kind else [
        value for (entry_kind, name), values in _BY_TYPE_NAME.items()
        if name == reference.casefold() for value in values
    ]
    unique = {item["key"]: item for item in candidates}
    return next(iter(unique.values())) if len(unique) == 1 else None


def sigil_key_from_scroll_url(url: str) -> str | None:
    """Сопоставить страницу предмета-свитка с изучаемым сигилом."""
    title = unquote(urlparse(url).path.rsplit("/", 1)[-1]).replace("%3A", ":")
    match = re.search(r"(?:Scroll:_)?(?:(Lesser|Greater|Exceptional)_)?Sigil_of_(.+?)_\((Core|Expression|Accent)\)", title)
    if not match:
        return None
    rank, english_name, declared_type = match.groups()
    russian = _ENGLISH_TO_RUSSIAN.get(english_name)
    if not russian:
        return None
    if declared_type == "Core":
        return f"core:{russian}"
    if declared_type == "Expression":
        return f"expression:{russian}"
    enhancement_key = f"enhancement:{russian}"
    if enhancement_key in SIGILS_BY_KEY:
        return enhancement_key
    tier = {"Lesser": 1, None: 2, "Greater": 3, "Exceptional": 4}.get(rank, 1)
    key = f"accent:{russian}:{tier}"
    return key if key in SIGILS_BY_KEY else None


STARTING_MAGIC = {
    "Заклинания молний": ("Молния", "Заряженный кулак"),
    "Заклинания рвения": ("Энергия", "Касание титана"),
    "Заклинания льда": ("Холод", "Ледяная хватка"),
    "Заклинания истощения": ("Истощение", "Касание истощения"),
}


def starting_sigils_and_spells(specializations: tuple[str, str] | list[str]) -> tuple[set[str], list[dict]]:
    known = {"expression:Сосредоточенное намерение"}
    spells = []
    for specialization in specializations:
        starting = STARTING_MAGIC.get(specialization)
        if not starting:
            continue
        core, name = starting
        known.add(f"core:{core}")
        spells.append({
            "name": name, "core": core, "expression": "Сосредоточенное намерение",
            "accents": [], "enhancements": [], "difficulty": 15,
        })
    return known, spells


SPELL_NAMES = {
    ("Истощение", "Проводимая сила"): "Калечащая спираль", ("Истощение", "Хаотическое нисхождение"): "Кислотный дождь",
    ("Истощение", "Направленная сила"): "Иссушающее облако", ("Истощение", "Сосредоточенное намерение"): "Касание истощения",
    ("Истощение", "Ближнее действие"): "Аура распада",
    ("Эмоции", "Проводимая сила"): "Волна отчаяния", ("Эмоции", "Дальний удар"): "Насмешливая шутка",
    ("Эмоции", "Сосредоточенное намерение"): "Разъярение разума", ("Эмоции", "Область влияния"): "Сон",
    ("Эмоции", "Ближнее действие"): "Аура страха",
    ("Огонь", "Проводимая сила"): "Вспышка огня", ("Огонь", "Хаотическое нисхождение"): "Обжигающие снаряды",
    ("Огонь", "Дальний удар"): "Огненный шар", ("Огонь", "Направленная сила"): "Извивающееся пламя",
    ("Огонь", "Сосредоточенное намерение"): "Обжигающая ладонь", ("Огонь", "Охранная форма"): "Сияющий барьер",
    ("Огонь", "Область влияния"): "Выжженная земля", ("Огонь", "Материальная сила"): "Воспламенённое оружие",
    ("Огонь", "Ближнее действие"): "Мантия пламени",
    ("Сила", "Проводимая сила"): "Приливная волна", ("Сила", "Дальний удар"): "Сотрясающий заряд",
    ("Сила", "Охранная форма"): "Ускорение", ("Сила", "Ближнее действие"): "Утяжелённая стойка",
    ("Холод", "Проводимая сила"): "Ледяная буря", ("Холод", "Дальний удар"): "Ледяной шип",
    ("Холод", "Направленная сила"): "Путь мороза", ("Холод", "Сосредоточенное намерение"): "Ледяная хватка",
    ("Холод", "Охранная форма"): "Вечная мерзлота", ("Холод", "Область влияния"): "Арктическая земля",
    ("Холод", "Материальная сила"): "Морозная хватка",
    ("Иллюзия", "Проводимая сила"): "Распутывание разума", ("Иллюзия", "Дальний удар"): "Ложная яма",
    ("Иллюзия", "Направленная сила"): "Озорное множество", ("Иллюзия", "Сосредоточенное намерение"): "Призрачное размытие",
    ("Иллюзия", "Охранная форма"): "Зеркальное отражение",
    ("Жизнь", "Дальний удар"): "Целительные огоньки", ("Жизнь", "Сосредоточенное намерение"): "Восстанавливающее касание",
    ("Жизнь", "Охранная форма"): "Живое тело", ("Жизнь", "Область влияния"): "Возрождение земли",
    ("Жизнь", "Ближнее действие"): "Аура исцеления",
    ("Молния", "Проводимая сила"): "Грозовой разряд", ("Молния", "Хаотическое нисхождение"): "Гроза",
    ("Молния", "Дальний удар"): "Электрический толчок", ("Молния", "Направленная сила"): "Шаровая молния",
    ("Молния", "Сосредоточенное намерение"): "Заряженный кулак", ("Молния", "Охранная форма"): "Заземляющее ядро",
    ("Молния", "Материальная сила"): "Статический заряд",
    ("Камень", "Хаотическое нисхождение"): "Челюсти земли", ("Камень", "Дальний удар"): "Каменный шип",
    ("Камень", "Направленная сила"): "Гигантский валун", ("Камень", "Сосредоточенное намерение"): "Окаменение",
    ("Камень", "Охранная форма"): "Дар голема", ("Камень", "Материальная сила"): "Скальное оружие",
    ("Камень", "Ближнее действие"): "Неспокойное ядро",
    ("Терратус", "Проводимая сила"): "Свет Терратуса", ("Терратус", "Дальний удар"): "Призрачный заряд",
    ("Терратус", "Сосредоточенное намерение"): "Могильная хватка", ("Терратус", "Материальная сила"): "Вампирическое оружие",
    ("Терратус", "Ближнее действие"): "Сумрачное сияние",
    ("Энергия", "Проводимая сила"): "Всплеск славы", ("Энергия", "Сосредоточенное намерение"): "Касание титана",
    ("Энергия", "Охранная форма"): "Удача чемпиона", ("Энергия", "Материальная сила"): "Полировка оружия",
    ("Энергия", "Ближнее действие"): "Наставление",
}


def default_spell_name(core: str, expression: str) -> str:
    return SPELL_NAMES.get((core, expression), f"{core}: {expression}")


EXPRESSION_RUNTIME = {
    "Область влияния": {"cooldown": 5, "defense": "Магия", "projectiles": 1},
    "Направленная сила": {"cooldown": 4, "defense": "Уклонение", "projectiles": 1},
    "Хаотическое нисхождение": {"cooldown": 6, "defense": "Уклонение", "projectiles": 3},
    "Сосредоточенное намерение": {"cooldown": 3, "defense": "Магия", "projectiles": 1},
    "Проводимая сила": {"cooldown": 4, "defense": "Уклонение", "projectiles": 1},
    "Охранная форма": {"cooldown": 5, "defense": "Магия", "projectiles": 1},
    "Материальная сила": {"cooldown": 5, "defense": "Магия", "projectiles": 1},
    "Ближнее действие": {"cooldown": 5, "defense": "Магия", "projectiles": 1},
    "Дальний удар": {"cooldown": 4, "defense": "Уклонение", "projectiles": 1},
}

_ACCENT_VALUES = {
    "Прыгающие заряды": (1, 2),
    "Циклические энергии": (15, 25, 35, 45),
    "Безграничные пределы": (1, 2, 3),
    "Пробивающая сила": (4, 8, 12),
    "Точное действие": (15, 30, 45, 60),
    "Длинная хватка": (2, 4, 6),
    "Ошеломляющая сила": (1, 2, 3),
    "Мощность": (20, 30, 40, 50),
    "Вневременная форма": (25, 35, 45),
}


def _accent_value(accents: list[str], family: str) -> int:
    """Вернуть каноническое значение выбранного уровня семейства штрихов."""
    values = _ACCENT_VALUES[family]
    for name in accents:
        if name == family:
            return values[0]
        if name.startswith(f"{family} "):
            match = re.search(r"(\d+)$", name)
            if match:
                tier = int(match.group(1))
                return values[tier - 1] if 1 <= tier <= len(values) else 0
    return 0


def spell_runtime_profile(
    spell: dict, *, skill: int, wits: int, cooldown_multiplier: float = 1,
) -> dict:
    """Единый пошаговый расчёт формулы для сайта, тренировки и Discord-боя."""
    accents = list(spell.get("accents") or [])
    enhancements = list(spell.get("enhancements") or [])
    enhancement = enhancements[0] if enhancements else ""
    shape = EXPRESSION_RUNTIME.get(
        spell.get("expression"), EXPRESSION_RUNTIME["Сосредоточенное намерение"]
    )
    accuracy = int(skill) + _accent_value(accents, "Точное действие")
    power_bonus = _accent_value(accents, "Мощность")
    if enhancement == "Магия крови":
        power_bonus += 30
    elif enhancement in {"Магия гордыни", "Самоотверженная магия"}:
        power_bonus += 50
    power = max(1, round((9 + int(wits) // 2) * (1 + power_bonus / 100)))
    recovery_cut = _accent_value(accents, "Циклические энергии")
    cooldown = max(1, math.ceil(
        shape["cooldown"] * (1 - recovery_cut / 100) * max(.1, float(cooldown_multiplier))
    ))
    projectiles = shape["projectiles"] + _accent_value(accents, "Прыгающие заряды")
    if enhancement == "Залпы":
        projectiles += 2
    return {
        "accuracy": accuracy,
        "damage_min": max(1, power - 4),
        "damage_max": power + 4,
        "cooldown": cooldown,
        "defense": shape["defense"],
        "penetration": _accent_value(accents, "Пробивающая сила"),
        "projectiles": projectiles,
        "range_bonus": _accent_value(accents, "Длинная хватка"),
        "area_bonus": _accent_value(accents, "Безграничные пределы"),
        "duration_bonus": _accent_value(accents, "Вневременная форма"),
        "interrupt": _accent_value(accents, "Ошеломляющая сила"),
        "enhancement": enhancement,
        "self_damage": 15 if enhancement == "Магия крови" else 0,
    }


def validate_formula(
    core_ref: str, expression_ref: str, accent_refs: list[str], enhancement_refs: list[str],
    known_keys: set[str], lore: int,
) -> dict:
    core = sigil_by_reference(core_ref, "core")
    expression = sigil_by_reference(expression_ref, "expression")
    if not core or not expression:
        raise ValueError("Выберите изученные сигилы основы и выражения.")
    accents = [sigil_by_reference(ref, "accent") for ref in accent_refs]
    enhancements = [sigil_by_reference(ref, "enhancement") for ref in enhancement_refs]
    if any(item is None for item in accents + enhancements):
        raise ValueError("В формуле есть неизвестный сигил.")
    if len(enhancements) > 1:
        raise ValueError("В одной формуле допустим только один сигил усиления.")
    selected = [core, expression, *accents, *enhancements]
    missing = [item["name"] for item in selected if item["key"] not in known_keys]
    if missing:
        raise ValueError("Сначала изучите свитки: " + ", ".join(missing) + ".")
    families = [item["family"] for item in accents]
    if len(families) != len(set(families)):
        raise ValueError("Нельзя использовать два уровня одного и того же акцента.")
    if expression["compatibleCores"] and core["name"] not in expression["compatibleCores"]:
        raise ValueError(f"«{expression['name']}» несовместимо с основой «{core['name']}».")
    for enhancement in enhancements:
        if enhancement["compatibleCores"] and core["name"] not in enhancement["compatibleCores"]:
            raise ValueError(f"Усиление «{enhancement['name']}» несовместимо с этой основой.")
        if enhancement["compatibleExpressions"] and expression["name"] not in enhancement["compatibleExpressions"]:
            raise ValueError(f"Усиление «{enhancement['name']}» несовместимо с этим выражением.")
    difficulty = expression["lore"] + sum(item["lore"] for item in [*accents, *enhancements])
    if difficulty > int(lore):
        raise ValueError(f"Нужно Знаний: {difficulty}; у персонажа: {lore}.")
    return {
        "core": core["name"], "expression": expression["name"],
        "accents": [item["name"] for item in accents],
        "enhancements": [item["name"] for item in enhancements],
        "difficulty": difficulty, "default_name": default_spell_name(core["name"], expression["name"]),
    }
