"""Скачивает полный английский источник Tyranny Wiki для последующего ручного перевода.

Модуль не публикует английский текст в Discord и не изменяет рабочий каталог.
Он создаёт проверяемый исходный снимок, который переводится средствами проекта.
"""

from __future__ import annotations

import argparse
import json
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

API = "https://tyranny.fandom.com/api.php"
USER_AGENT = "TyrannyDiscordArchive/2.0 (bilingual source mirror)"

ROOT_CATEGORIES = (
    "Tyranny items",
    "Fatebinder talents",
    "Sigils",
    "Skills",
    "Attributes",
    "Game mechanics",
    "Reputation",
    "Edicts",
    "Factions",
    "Spires",
)
SKIP_CATEGORIES = {
    "Tyranny cut items", "Item images", "Quest item images",
    "Bastard's Wound item images", "Images", "Files",
}


def request(params: dict[str, Any], attempts: int = 4) -> dict[str, Any]:
    query = urllib.parse.urlencode({"format": "json", "formatversion": 2, **params})
    req = urllib.request.Request(API + "?" + query, headers={"User-Agent": USER_AGENT})
    for attempt in range(attempts):
        try:
            with urllib.request.urlopen(req, timeout=45) as response:
                return json.load(response)
        except Exception:
            if attempt + 1 == attempts:
                raise
            time.sleep(1.5 * (attempt + 1))
    return {}


def category_members(category: str) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    continuation: dict[str, Any] = {}
    while True:
        data = request({
            "action": "query", "list": "categorymembers",
            "cmtitle": f"Category:{category}", "cmtype": "page|subcat",
            "cmlimit": "max", **continuation,
        })
        result.extend(data.get("query", {}).get("categorymembers", []))
        if "continue" not in data:
            return result
        continuation = data["continue"]


def walk_categories(roots: tuple[str, ...]) -> tuple[dict[int, str], list[str]]:
    pages: dict[int, str] = {}
    visited: set[str] = set()
    pending = list(roots)
    while pending:
        category = pending.pop(0)
        if category in visited or category in SKIP_CATEGORIES:
            continue
        visited.add(category)
        try:
            members = category_members(category)
        except Exception as exc:
            print(f"Предупреждение: категория {category}: {exc}")
            continue
        for member in members:
            if member["ns"] == 0:
                pages[int(member["pageid"])] = member["title"]
            elif member["ns"] == 14:
                child = member["title"].removeprefix("Category:")
                if child not in visited and child not in SKIP_CATEGORIES:
                    pending.append(child)
        print(f"Категорий: {len(visited)}; найдено страниц: {len(pages)}")
    return pages, sorted(visited)


def fetch_pages(page_ids: list[int]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for offset in range(0, len(page_ids), 50):
        batch = page_ids[offset:offset + 50]
        data = request({
            "action": "query", "pageids": "|".join(map(str, batch)),
            "prop": "extracts|revisions|images|categories", "explaintext": 1,
            "exsectionformat": "plain", "imlimit": "max", "cllimit": "max",
            "rvprop": "content", "rvslots": "main",
        })
        for page in data.get("query", {}).get("pages", []):
            revisions = page.get("revisions") or []
            slots = revisions[0].get("slots", {}) if revisions else {}
            source = slots.get("main", {}).get("content", "")
            result.append({
                "pageid": page.get("pageid"),
                "title_en": page.get("title", ""),
                "text_en": (page.get("extract") or "").strip(),
                "wikitext_en": source,
                "files": [item["title"] for item in page.get("images", [])],
                "categories": [item["title"].removeprefix("Category:") for item in page.get("categories", [])],
                "source_url": "https://tyranny.fandom.com/wiki/" + urllib.parse.quote(page.get("title", "").replace(" ", "_")),
            })
        print(f"Загружено страниц: {min(offset + len(batch), len(page_ids))}/{len(page_ids)}")
    return sorted(result, key=lambda row: row["title_en"].casefold())


def main() -> None:
    parser = argparse.ArgumentParser(description="Снимок английского источника Tyranny Wiki")
    parser.add_argument("--output", default="catalog/tyranny_wiki_en.json")
    parser.add_argument("--reuse-index", action="store_true", help="Не обходить категории повторно")
    args = parser.parse_args()
    target = Path(args.output)
    if args.reuse_index and target.exists():
        previous = json.loads(target.read_text(encoding="utf-8"))
        pages = {int(page["pageid"]): page["title_en"] for page in previous["pages"]}
        categories = previous.get("categories", [])
    else:
        pages, categories = walk_categories(ROOT_CATEGORIES)
    records = fetch_pages(list(pages))
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps({"categories": categories, "pages": records}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"Сохранено английских страниц: {len(records)} в {target}")


if __name__ == "__main__":
    main()
