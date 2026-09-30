"""Импорт русских предметов и сигилов из Tyranny Wiki (Fandom MediaWiki API).

Изображения не копируются: в базе сохраняется прямая HTTPS-ссылка на оригинал.
Это экономит место и позволяет Discord отображать актуальную иллюстрацию.
"""

from __future__ import annotations

import asyncio
import html
import json
import re
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from database import Database
from localization import localize_game_text

API = "https://tyranny.fandom.com/ru/api.php"
WIKI = "https://tyranny.fandom.com/ru/wiki/"
USER_AGENT = "TyrannyDiscordArchive/1.0 (Russian roleplay catalog)"

CATEGORIES = {
    "Оружие": "Одноручное оружие",
    "Луки": "Луки",
    "Посохи": "Посохи",
    "Щиты": "Щиты",
    "Броня": "Броня",
    "Аксессуары": "Аксессуары",
    "Расходуемые предметы": "Расходуемые предметы",
    "Зелья": "Зелья",
    "Еда": "Еда",
    "Сигилы": "Сигилы",
    "Кристаллы": "Материалы",
    "Эликсиры": "Зелья",
}


def _request(params: dict[str, Any]) -> dict[str, Any]:
    params = {"format": "json", "formatversion": 2, **params}
    url = API + "?" + urllib.parse.urlencode(params)
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=40) as response:
        return json.load(response)


def _number(patterns: tuple[str, ...], text: str, default: float = 0) -> float:
    for pattern in patterns:
        found = re.search(pattern, text, re.IGNORECASE)
        if found:
            return float(found.group(1).replace(",", "."))
    return default


def _clean(text: str) -> str:
    text = html.unescape(text or "")
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()[:3900]


def _resolve_images(file_titles: list[str]) -> dict[str, str]:
    resolved: dict[str, str] = {}
    unique = list(dict.fromkeys(file_titles))
    for index in range(0, len(unique), 50):
        batch = unique[index:index + 50]
        data = _request({
            "action": "query", "titles": "|".join(batch), "prop": "imageinfo",
            "iiprop": "url", "iiurlwidth": 900,
        })
        for page in data.get("query", {}).get("pages", []):
            info = page.get("imageinfo") or []
            if info:
                resolved[page["title"]] = info[0].get("thumburl") or info[0].get("url", "")
    return resolved


def _infer_slot(category: str, text: str) -> str:
    folded = text.casefold()
    if category == "Броня":
        if any(word in folded for word in ("шлем", "капюшон", "голов")):
            return "Голова"
        if any(word in folded for word in ("перчат", "наруч", "рукавиц")):
            return "Руки"
        if any(word in folded for word in ("сапог", "понож", "обув")):
            return "Ноги"
        return "Торс"
    if category == "Аксессуары":
        return "Аксессуар"
    return ""


def _parse_page(page: dict[str, Any], category: str, image_urls: dict[str, str]) -> dict[str, Any] | None:
    title = page.get("title", "").strip()
    if not title or title.startswith(("Категория:", "Шаблон:")):
        return None
    text = _clean(page.get("extract", ""))
    image_titles = [image["title"] for image in page.get("images", [])]
    normalized_title = re.sub(r"[^а-яёa-z0-9]", "", title.casefold())
    preferred = next(
        (file_title for file_title in image_titles if normalized_title and normalized_title in re.sub(r"[^а-яёa-z0-9]", "", file_title.casefold())),
        "",
    )
    original = image_urls.get(preferred, "")
    quality_match = next(
        (name for name in ("Артефакт", "Шедевр", "Изысканное", "Превосходное", "Добротное", "Хорошее") if name.casefold() in text.casefold()),
        "Обычное",
    )
    quality = "Добротное" if quality_match == "Хорошее" else quality_match
    actual_category = category
    folded = text.casefold() + " " + title.casefold()
    if category == "Одноручное оружие":
        if any(word in folded for word in ("двуруч", "великий меч", "алебард")):
            actual_category = "Двуручное оружие"
        elif "дротик" in folded or "метатель" in folded:
            actual_category = "Метательное оружие"
    text = localize_game_text(text)
    properties: dict[str, Any] = {}
    for label in ("Точность", "Пробивание брони", "Дальность", "Задержка", "Восстановление"):
        match = re.search(rf"{label}\s*[:—-]\s*([^\n]+)", text, re.IGNORECASE)
        if match:
            properties[label] = localize_game_text(match.group(1).strip()[:200])
    return {
        "name": title,
        "category": actual_category,
        "slot": _infer_slot(actual_category, text),
        "quality": quality,
        "description": text or f"{title} — предмет из игры «Тирания».",
        "image_url": original,
        "source_url": WIKI + urllib.parse.quote(title.replace(" ", "_")),
        "value": int(_number((r"Стоимость\s*[:—-]\s*(\d+)", r"Цена\s*[:—-]\s*(\d+)"), text)),
        "weight": _number((r"Вес\s*[:—-]\s*([\d,.]+)",), text),
        "hands": 2 if actual_category in {"Двуручное оружие", "Луки", "Посохи"} else (1 if "оружие" in actual_category.casefold() or actual_category == "Щиты" else 0),
        "damage_min": int(_number((r"Урон\s*[:—-]\s*(\d+)\s*[-–]",), text)),
        "damage_max": int(_number((r"Урон\s*[:—-]\s*\d+\s*[-–]\s*(\d+)",), text)),
        "armor": int(_number((r"Броня\s*[:—-]\s*(\d+)",), text)),
        "recovery": _number((r"Восстановление\s*[:—-]\s*([\d,.]+)",), text),
        "properties": properties,
        "wiki_page_id": page.get("pageid"),
    }


def fetch_category(category_name: str, mapped_category: str) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    raw_pages: list[dict[str, Any]] = []
    continuation: dict[str, Any] = {}
    while True:
        data = _request({
            "action": "query",
            "generator": "categorymembers",
            "gcmtitle": f"Категория:{category_name}",
            "gcmnamespace": 0,
            "gcmlimit": "max",
            "prop": "extracts|images",
            "explaintext": 1,
            "exsectionformat": "plain",
            "imlimit": "max",
            **continuation,
        })
        raw_pages.extend(data.get("query", {}).get("pages", []))
        if "continue" not in data:
            break
        continuation = data["continue"]
    file_titles = [image["title"] for page in raw_pages for image in page.get("images", [])]
    image_urls = _resolve_images(file_titles)
    for page in raw_pages:
        parsed = _parse_page(page, mapped_category, image_urls)
        if parsed:
            items.append(parsed)
    return items


async def sync_wiki(database: Database, snapshot_path: Path | None = None) -> tuple[int, list[str]]:
    merged: dict[str, dict[str, Any]] = {}
    warnings: list[str] = []
    for wiki_category, local_category in CATEGORIES.items():
        try:
            pages = await asyncio.to_thread(fetch_category, wiki_category, local_category)
            for page in pages:
                merged.setdefault(page["name"].casefold(), page)
        except Exception as exc:  # импорт одной категории не должен обрушать весь каталог
            warnings.append(f"{wiki_category}: {exc}")
    items = sorted(merged.values(), key=lambda row: row["name"].casefold())
    if snapshot_path:
        snapshot_path.parent.mkdir(parents=True, exist_ok=True)
        snapshot_path.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
    return await database.upsert_catalog(items), warnings


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Импорт русского каталога Tyranny Wiki")
    parser.add_argument("--database", default="data/tyranny.sqlite3")
    parser.add_argument("--snapshot", default="data/tyranny_catalog.json")
    args = parser.parse_args()

    async def main() -> None:
        database = Database(Path(args.database))
        await database.initialize()
        count, warnings = await sync_wiki(database, Path(args.snapshot))
        print(f"Импортировано страниц: {count}")
        for warning in warnings:
            print(f"Предупреждение: {warning}")

    asyncio.run(main())
