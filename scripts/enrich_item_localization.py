"""Дополнить каталоги предметов официальными названиями и предысторией."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from urllib.parse import unquote, urlparse


def key(value: str) -> str:
    value = re.sub(r"\[/?url(?:=[^]]+)?\]", "", value)
    return re.sub(r"\s+", " ", value).strip().replace("’", "'").casefold()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("catalogs", nargs="+", type=Path)
    parser.add_argument("--localization", type=Path, default=Path("catalog/official_game_localization.json"))
    args = parser.parse_args()
    payload = json.loads(args.localization.read_text(encoding="utf-8"))
    translations: dict[str, str] = {}
    for rows in payload.get("tables", {}).values():
        for row in rows:
            if row.get("en") and row.get("ru"):
                translations.setdefault(key(row["en"]), re.sub(r"\[/?url(?:=[^]]+)?\]", "", row["ru"]).strip())
    entities: dict[str, dict] = {}
    for row in payload.get("entities", []):
        if row.get("table") != "items" or not row.get("name_en"):
            continue
        current = entities.get(key(row["name_en"]))
        if current is None or (not current.get("description_ru") and row.get("description_ru")):
            entities[key(row["name_en"])] = row

    for path in args.catalogs:
        items = json.loads(path.read_text(encoding="utf-8"))
        matched = 0
        for item in items:
            slug = unquote(urlparse(str(item.get("source_url", ""))).path.rsplit("/", 1)[-1]).replace("_", " ")
            entity = entities.get(key(slug))
            original_description = str(item.get("description", "")).strip()
            lore = ""
            if entity:
                matched += 1
                item["name"] = re.sub(r"\[/?url(?:=[^]]+)?\]", "", entity.get("name_ru", "")) or item["name"]
                lore = re.sub(r"\[/?url(?:=[^]]+)?\]", "", entity.get("description_ru", ""))
            elif translations.get(key(slug)):
                matched += 1
                item["name"] = translations[key(slug)]
            # Русская Wiki часто уже содержит полноценный раздел «Описание».
            # Он остаётся безопасным резервом, если у объекта нет DescriptionText.
            item["lore"] = re.sub(r"\s+", " ", lore).strip() or original_description
        path.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"{path}: официально сопоставлено {matched}/{len(items)}, поле предыстории заполнено у всех")


if __name__ == "__main__":
    main()
