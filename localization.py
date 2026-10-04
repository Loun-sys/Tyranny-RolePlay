"""Общие правила русской локализации настольной адаптации Tyranny."""

from __future__ import annotations

import re
import urllib.parse


COMPANION_NAMES = (
    "Смерть из Тени", "Kills-in-Shadow", "Kills in Shadow",
    "Лантри", "Lantry", "Эбб", "Eb", "Сирин", "Sirin",
    "Фуга", "Verse", "Барик", "Barik",
)

WIKI_CATEGORY_ICONS = {
    "Аксессуары": "ACC_Ashe_Favor.png", "Броня": "ART_Leather_GLOVE_AlchemistsGloves_L.png",
    "Двуручное оружие": "W 2H Sword01 L R.png", "Квестовые предметы": "OrangeCrystal_L.png",
    "Луки": "WPN_Bow_Fatefinder.png", "Материалы": "spire_resource_alchemy_supplies_L.png",
    "Одноручное оружие": "WPN_1H_BR_Sword_05_L.png", "Посохи": "WPN_Staff_CairnCrystal.png",
    "Прочее": "paper_01_L.png", "Расходуемые предметы": "azurebell_L.png",
    "Сигилы": "paper_03_L.png", "Ценности": "GEM_agate_L.png",
    "Чертежи": "RecipeBook_Forge_Skorn.png", "Щиты": "WPN ART SHLD AzureShield L.png",
}


def wiki_category_icon(category: str) -> str:
    filename = WIKI_CATEGORY_ICONS.get(category, "paper_01_L.png")
    return "https://tyranny.fandom.com/wiki/Special:Redirect/file/" + urllib.parse.quote(filename)


def _round_word(value: float) -> str:
    if value != int(value):
        return "раунда"
    number = int(value)
    if number % 10 == 1 and number % 100 != 11:
        return "раунд"
    if number % 10 in {2, 3, 4} and number % 100 not in {12, 13, 14}:
        return "раунда"
    return "раундов"


def seconds_to_rounds(value: float) -> str:
    """В текстовой версии один раунд равен десяти секундам оригинала."""
    rounds = value / 10
    rendered = f"{rounds:.2f}".rstrip("0").rstrip(".").replace(".", ",")
    return f"{rendered} {_round_word(rounds)}"


def turnify_text(value: str) -> str:
    """Заменить любые длительности в секундах на длительности в раундах."""
    if not value:
        return value
    # Показатель урона в секунду становится уроном за десятисекундный раунд.
    def damage_per_round(match: re.Match[str]) -> str:
        amount = float(match.group(1).replace(",", ".")) * 10
        rendered = f"{amount:.2f}".rstrip("0").rstrip(".").replace(".", ",")
        return f"урон/раунд: {rendered}"

    value = re.sub(
        r"урон\s*/\s*сек\.?\s*:\s*(\d+(?:[.,]\d+)?)",
        damage_per_round, value, flags=re.I,
    )
    pattern = re.compile(
        r"(?<![\w,.])(\d+(?:[.,]\d+)?)\s*"
        r"(?:seconds?|secs?\.?|s\b|секунд(?:а|ы|у|е)?|сек\.?)",
        flags=re.IGNORECASE,
    )

    def replace(match: re.Match[str]) -> str:
        return seconds_to_rounds(float(match.group(1).replace(",", ".")))

    return pattern.sub(replace, value)


def neutralize_companion_names(value: str) -> str:
    """Убрать имена игровых спутников из пользовательских описаний."""
    result = value or ""
    for name in sorted(COMPANION_NAMES, key=len, reverse=True):
        result = re.sub(
            rf"(?<!\w){re.escape(name)}(?:['’]s|а|у|ом|е|ы|и)?(?!\w)",
            "персонаж", result, flags=re.I,
        )
    result = re.sub(r"\bперсонаж(?:а|у|ом|е)\b", "персонаж", result, flags=re.I)
    return result


def neutralize_player_reference(value: str) -> str:
    """Adapt references to the original protagonist, without renaming lore entities."""
    endings={'ь':'персонаж','я':'персонажа','ю':'персонажу','ем':'персонажем','е':'персонаже',
             'и':'персонажи','ей':'персонажей','ям':'персонажам','ями':'персонажами','ях':'персонажах'}
    def replace(match: re.Match[str]) -> str:
        result=endings[match.group(1).casefold()]
        return result.capitalize() if match.group(0)[0].isupper() else result
    result=re.sub(r'\bВершител(ями|ям|ях|ей|ем|ь|я|ю|е|и)\b(?!\s+победы\b)(?:\s+Судеб\b)?',replace,value or '',flags=re.I)
    return re.sub(r"\bFatebinder(?:['’]s)?\b",lambda m:'персонажа' if m.group(0).endswith(("'s",'’s')) else 'персонаж',result,flags=re.I)


def localize_game_text(value: str) -> str:
    result = neutralize_companion_names(turnify_text(value))
    return re.sub(r"\bTyranny\b", "Тирания", result, flags=re.I)


def localize_player_text(value: str) -> str:
    """Gameplay prose only; item names and historical lore keep their identities."""
    return neutralize_player_reference(localize_game_text(value))
