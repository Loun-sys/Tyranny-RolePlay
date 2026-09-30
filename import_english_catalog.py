"""Преобразует английские статьи предметов в русские структурированные записи."""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import urllib.parse
from pathlib import Path
from typing import Any

from database import Database
from localization import localize_game_text, neutralize_companion_names, wiki_category_icon
from russian_translation import EXACT_TITLES, translate_effect, translate_title

ITEM_CATEGORIES = {
    "One-handed weapons": "Одноручное оружие",
    "Two-handed weapons": "Двуручное оружие",
    "Bows": "Луки",
    "Thrown weapons": "Метательное оружие",
    "Magic staffs": "Посохи",
    "Shields": "Щиты",
    "Light armor": "Броня",
    "Heavy armor": "Броня",
    "Accessories": "Аксессуары",
    "Consumables": "Расходуемые предметы",
    "Potions": "Зелья",
    "Food": "Еда",
    "Artifacts": "Прочее",
    "Junk": "Прочее",
    "Miscellaneous items": "Прочее",
    "Scrolls": "Сигилы",
    "Quest items": "Квестовые предметы",
    "Bastard's Wound quest items": "Квестовые предметы",
    "Lore items": "Квестовые предметы",
    "Documents": "Квестовые предметы",
    "Spire recipes": "Чертежи",
    "Spire research items": "Материалы",
    "Spire resources": "Материалы",
    "Spire crafting resources": "Материалы",
    "Gems": "Ценности",
    "Tyranny items": "Прочее",
}
QUALITY = {
    "common": "Обычное", "fine": "Добротное", "superior": "Превосходное",
    "exquisite": "Изысканное", "masterwork": "Шедевр",
}


def field(wikitext: str, name: str) -> str:
    pattern = rf"^\s*\|\s*{re.escape(name)}\s*=\s*(.*?)(?=^\s*\|\s*[\w ]+\s*=|^\s*}}}})"
    match = re.search(pattern, wikitext or "", re.IGNORECASE | re.MULTILINE | re.DOTALL)
    return match.group(1).strip() if match else ""


def plain(value: str) -> str:
    value = re.sub(r"\[\[(?:[^\]|]+\|)?([^\]]+)]]", r"\1", value)
    value = re.sub(r"<br\s*/?>", "\n", value, flags=re.IGNORECASE)
    value = re.sub(r"'{2,}", "", value)
    value = re.sub(r"\{\{[^{}]*}}", "", value)
    return re.sub(r"\s+", " ", value).strip()


def number(value: str, index: int = 0) -> float:
    numbers = re.findall(r"-?\d+(?:[.,]\d+)?", plain(value))
    return float(numbers[index].replace(",", ".")) if len(numbers) > index else 0


def category_for(categories: list[str], template: str) -> str:
    priority = (
        "Quest items", "Bastard's Wound quest items", "Lore items", "Documents",
        "Spire recipes", "Spire research items", "Spire resources", "Spire crafting resources",
        "One-handed weapons", "Two-handed weapons", "Bows", "Thrown weapons", "Magic staffs", "Shields",
        "Light armor", "Heavy armor", "Accessories", "Consumables", "Potions", "Food", "Scrolls",
        "Gems", "Junk", "Miscellaneous items", "Artifacts", "Tyranny items",
    )
    for source in priority:
        if source in categories:
            return ITEM_CATEGORIES[source]
    if template == "weapon":
        return "Одноручное оружие"
    if template == "equipment":
        return "Броня"
    return "Прочее"


def infobox_template(wikitext: str) -> str:
    match = re.search(r"\{\{\s*Infobox\s+(item|equipment|weapon)\b", wikitext or "", re.I)
    return match.group(1).casefold() if match else ""


def is_stub_item(page: dict[str, Any]) -> bool:
    """Wiki содержит ряд настоящих предметов-заглушек без инфобокса."""
    wikitext = page.get("wikitext_en", "")
    categories = page.get("categories", [])
    return bool(re.search(r"\bis an item in\b", wikitext, re.I)) or (
        "Quest items" in categories and page.get("title_en") != "Quest items"
    )


def stub_category(title: str, categories: list[str]) -> str:
    folded = title.casefold()
    if "Quest items" in categories or any(word in folded for word in ("map", "missive", "note", "report", "message", "key", "fragment")):
        return "Квестовые предметы"
    if any(word in folded for word in ("boot", "sandal", "leather")):
        return "Броня"
    if "staff" in folded:
        return "Посохи"
    if "dagger" in folded:
        return "Одноручное оружие"
    if any(word in folded for word in ("necklace", "armlet", "token")):
        return "Аксессуары"
    if "scroll" in folded or "sigil" in folded:
        return "Сигилы"
    if "vial" in folded or "distillate" in folded:
        return "Расходуемые предметы"
    return "Прочее"


def price(value: str) -> tuple[int, str]:
    """Вернуть цену в медных кольцах и удобную русскую запись номиналов."""
    match = re.search(r"\{\{\s*rings\s*\|([^}]*)}}", value or "", re.I)
    if match:
        parts = [part.strip() for part in match.group(1).split("|")]
        parts = (parts + ["", "", ""])[:3]
        iron, bronze, copper = (int(part) if part.isdigit() else 0 for part in parts)
        total = iron * 10000 + bronze * 100 + copper
        labels = []
        if iron:
            labels.append(f"{iron} железн.")
        if bronze:
            labels.append(f"{bronze} бронз.")
        if copper:
            labels.append(f"{copper} медн.")
        return total, " ".join(labels) or "0 медных колец"
    amount = int(number(value))
    return amount, f"{amount} медных колец"


def translated_field(wikitext: str, name: str) -> str:
    return translated_text(plain(field(wikitext, name)))


def translated_text(value: str) -> str:
    value = neutralize_companion_names(value)
    result = translate_effect(value)
    # На Wiki встречаются редкие технические слова, отсутствующие в словаре.
    # В публичной карточке не оставляем латиницу: имена транслитерируются,
    # а игровые термины проходят через общий словарь translate_title.
    result = re.sub(r"[A-Za-z][A-Za-z'’.-]*", lambda match: translate_title(match.group()), result)
    return localize_game_text(result)


def armor_slot(title: str, categories: list[str]) -> str:
    folded = title.casefold()
    if "Headgear" in categories or any(word in folded for word in ("helm", "hood", "cowl", "cap", "hat", "headwrap")):
        return "Голова"
    if "Gloves" in categories or any(word in folded for word in ("glove", "gauntlet", "bracer", "handwrap")):
        return "Руки"
    if "Boots" in categories or any(word in folded for word in ("boot", "sandal", "shoe", "slipper", "greave")):
        return "Ноги"
    return "Торс"


def convert(page: dict[str, Any]) -> dict[str, Any] | None:
    categories = page.get("categories", [])
    wikitext = page.get("wikitext_en", "")
    template = infobox_template(wikitext)
    if not template and not is_stub_item(page):
        return None
    title_en = page["title_en"]
    category = category_for(categories, template) if template else stub_category(title_en, categories)
    title_ru = localize_game_text(translate_title(neutralize_companion_names(title_en)))
    melee = plain(field(wikitext, "melee"))
    ranged = plain(field(wikitext, "ranged"))
    damage = melee or ranged or plain(field(wikitext, "damage"))
    damage_numbers = re.findall(r"(?<![.,])\d+(?![.,])", damage)
    effect_en = plain(field(wikitext, "effect") or field(wikitext, "bonus") or field(wikitext, "ability"))
    effect_ru = translated_text(effect_en)
    image_file = plain(field(wikitext, "image") or field(wikitext, "icon"))
    hands = 2 if category in {"Двуручное оружие", "Луки", "Посохи"} else (
        1 if category in {"Одноручное оружие", "Метательное оружие", "Щиты"} else 0
    )
    slot = armor_slot(title_en, categories) if category == "Броня" else ("Аксессуар" if category == "Аксессуары" else "")
    quality_en = plain(field(wikitext, "quality")).casefold()
    quality = "Артефакт" if plain(field(wikitext, "artifact")).casefold() == "yes" else QUALITY.get(quality_en, "Обычное")
    facts: list[str] = []
    properties: dict[str, Any] = {}
    if damage:
        facts.append("Урон: " + translated_text(damage))
    labels = {
        "accuracy": "Точность", "penetration": "Пробивание брони", "armor": "Броня",
        "deflection": "Отражение", "recovery": "Восстановление", "range": "Дальность",
        "material": "Материал", "type": "Тип", "duration": "Длительность",
        "shield": "Защита щитом",
    }
    for source, label in labels.items():
        translated = translated_field(wikitext, source)
        if translated:
            properties[label] = translated
            facts.append(f"{label}: {translated}")
    if effect_ru:
        properties["Эффект"] = effect_ru
        facts.append("Эффект: " + effect_ru)
    item_value, price_text = price(field(wikitext, "cost"))
    properties["Цена"] = price_text
    if not image_file:
        properties["Иллюстрация"] = "Общая иконка раздела: отдельного изображения на вики нет"
    facts.append("Цена: " + price_text)
    description = f"{title_ru} — предмет из игры «Тирания»."
    if facts:
        description += "\n\n" + "\n".join(facts)
    description = localize_game_text(description)
    recovery = plain(field(wikitext, "recovery"))
    armor = plain(field(wikitext, "armor"))
    return {
        "name": title_ru,
        "category": category,
        "slot": slot,
        "quality": quality,
        "description": description,
        "image_url": (
            "https://tyranny.fandom.com/wiki/Special:Redirect/file/" + urllib.parse.quote(image_file)
            if image_file else wiki_category_icon(category)
        ),
        "source_url": page["source_url"],
        "value": item_value,
        "weight": number(field(wikitext, "weight")),
        "hands": hands,
        "damage_min": int(damage_numbers[0]) if damage_numbers else 0,
        "damage_max": int(damage_numbers[1]) if len(damage_numbers) > 1 else 0,
        "armor": int(number(armor)),
        "recovery": number(recovery),
        "properties": properties,
        "wiki_page_id": page.get("pageid"),
        "_title_en": title_en,
    }


async def main() -> None:
    parser = argparse.ArgumentParser(description="Русификация английского каталога Tyranny Wiki")
    parser.add_argument("--source", default="catalog/tyranny_wiki_en.json")
    parser.add_argument("--output", default="catalog/tyranny_catalog_en_ru.json")
    parser.add_argument("--database", default="data/tyranny.sqlite3")
    args = parser.parse_args()
    source = json.loads(Path(args.source).read_text(encoding="utf-8"))["pages"]
    items_by_name: dict[str, dict[str, Any]] = {}
    for page in source:
        item = convert(page)
        if item:
            items_by_name.setdefault(item["name"].casefold(), item)
    items = sorted(items_by_name.values(), key=lambda row: row["name"].casefold())
    review = [
        {
            "title_en": item["_title_en"],
            "title_ru": item["name"],
            "source_url": item["source_url"],
            "translation_mode": (
                "ручной" if item["_title_en"] in EXACT_TITLES else "словарный"
            ),
        }
        for item in items
    ]
    for item in items:
        item.pop("_title_en", None)
    Path(args.output).write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
    Path("catalog/translation_review.json").write_text(
        json.dumps(review, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    database = Database(Path(args.database))
    await database.initialize()
    count = await database.upsert_catalog(items)
    print(f"Переведено и импортировано английских предметов: {count}")


if __name__ == "__main__":
    asyncio.run(main())
