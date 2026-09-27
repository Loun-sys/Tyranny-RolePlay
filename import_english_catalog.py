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


def category_for(categories: list[str]) -> str | None:
    for source, translated in ITEM_CATEGORIES.items():
        if source in categories:
            return translated
    return None


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
    category = category_for(categories)
    if not category:
        return None
    title_en = page["title_en"]
    if title_en in {"Accessories", "Artifacts", "Bows", "Consumables", "Inventory"}:
        return None
    wikitext = page.get("wikitext_en", "")
    title_ru = translate_title(title_en)
    melee = plain(field(wikitext, "melee"))
    ranged = plain(field(wikitext, "ranged"))
    damage = melee or ranged or plain(field(wikitext, "damage"))
    damage_numbers = re.findall(r"\d+", damage)
    effect_en = plain(field(wikitext, "effect") or field(wikitext, "bonus") or field(wikitext, "ability"))
    effect_ru = translate_effect(effect_en)
    image_file = plain(field(wikitext, "image"))
    hands = 2 if category in {"Двуручное оружие", "Луки", "Посохи"} else (
        1 if category in {"Одноручное оружие", "Метательное оружие", "Щиты"} else 0
    )
    slot = armor_slot(title_en, categories) if category == "Броня" else ("Аксессуар" if category == "Аксессуары" else "")
    quality_en = plain(field(wikitext, "quality")).casefold()
    quality = "Артефакт" if plain(field(wikitext, "artifact")).casefold() == "yes" else QUALITY.get(quality_en, "Обычное")
    facts = []
    if damage:
        facts.append("Урон: " + translate_effect(damage))
    accuracy = plain(field(wikitext, "accuracy"))
    if accuracy:
        facts.append("Точность: " + accuracy)
    penetration = plain(field(wikitext, "penetration"))
    if penetration:
        facts.append("Пробивание брони: " + penetration)
    armor = plain(field(wikitext, "armor"))
    if armor:
        facts.append("Броня: " + armor)
    deflection = plain(field(wikitext, "deflection"))
    if deflection:
        facts.append("Отклонение: " + deflection)
    recovery = plain(field(wikitext, "recovery"))
    if recovery:
        facts.append("Восстановление: " + recovery)
    if effect_ru and not re.search(r"[A-Za-z]", effect_ru):
        facts.append("Эффект: " + effect_ru)
    facts = [fact for fact in facts if not re.search(r"[A-Za-z]", fact)]
    description = f"{title_ru} — предмет из игры «Тирания»."
    if facts:
        description += "\n\n" + "\n".join(facts)
    return {
        "name": title_ru,
        "category": category,
        "slot": slot,
        "quality": quality,
        "description": description,
        "image_url": (
            "https://tyranny.fandom.com/wiki/Special:Redirect/file/" + urllib.parse.quote(image_file)
            if image_file else ""
        ),
        "source_url": page["source_url"],
        "value": int(number(field(wikitext, "cost"))),
        "weight": number(field(wikitext, "weight")),
        "hands": hands,
        "damage_min": int(damage_numbers[0]) if damage_numbers else 0,
        "damage_max": int(damage_numbers[1]) if len(damage_numbers) > 1 else 0,
        "armor": int(number(armor)),
        "recovery": number(recovery),
        "properties": {
            "Техническое исходное название": title_en,
            "Игровой ID": plain(field(wikitext, "id")),
            "Непереведённый исходный эффект": effect_en,
        },
        "wiki_page_id": page.get("pageid"),
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
    Path(args.output).write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
    review = [
        {
            "title_en": item["properties"]["Техническое исходное название"],
            "title_ru": item["name"],
            "source_url": item["source_url"],
            "translation_mode": (
                "ручной" if item["properties"]["Техническое исходное название"] in EXACT_TITLES else "словарный — требует редакторской проверки"
            ),
        }
        for item in items
    ]
    Path("catalog/translation_review.json").write_text(
        json.dumps(review, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    database = Database(Path(args.database))
    await database.initialize()
    count = await database.upsert_catalog(items)
    russian_snapshot = Path("catalog/tyranny_catalog.json")
    if russian_snapshot.exists():
        await database.upsert_catalog(json.loads(russian_snapshot.read_text(encoding="utf-8")))
    print(f"Переведено и импортировано английских предметов: {count}")


if __name__ == "__main__":
    asyncio.run(main())
