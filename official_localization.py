"""Доступ к канонической русской локализации установленной Tyranny."""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

from localization import localize_game_text


DATA_FILE = Path(__file__).resolve().parent / "catalog" / "official_game_localization.json"


def _plain(value: str) -> str:
    value = re.sub(r"\[/?url(?:=[^]]+)?\]", "", value)
    return re.sub(r"\s+", " ", value).strip()


def _key(value: str) -> str:
    return _plain(value).replace("’", "'").casefold()


@lru_cache(maxsize=1)
def payload() -> dict:
    try:
        return json.loads(DATA_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"tables": {}, "spell_formulas": []}


@lru_cache(maxsize=1)
def translations() -> dict[str, str]:
    result: dict[str, str] = {}
    # При конфликте выигрывает первая каноническая запись. Порядок таблиц в
    # снимке намеренно ставит способности и состояния раньше GUI-текста.
    for rows in payload().get("tables", {}).values():
        for row in rows:
            english, russian = str(row.get("en", "")), str(row.get("ru", ""))
            if english.strip() and russian.strip():
                result.setdefault(_key(english), _plain(russian))
    return result


def official_text(english: str, fallback: str = "") -> str:
    """Вернуть официальную RU-строку и применить правила пошаговой версии."""
    translated = translations().get(_key(english))
    return localize_game_text(translated if translated else (fallback or english))


def official_spell_names() -> dict[tuple[str, str], str]:
    return {
        (row["core"], row["expression"]): localize_game_text(row["title_ru"])
        for row in payload().get("spell_formulas", [])
        if row.get("title_ru")
    }


def official_spell_details() -> dict[tuple[str, str], dict]:
    return {
        (row["core"], row["expression"]): {
            "name": localize_game_text(row.get("title_ru", "")),
            "description": localize_game_text(row.get("description_ru", "")),
        }
        for row in payload().get("spell_formulas", [])
        if row.get("title_ru")
    }


@lru_cache(maxsize=1)
def entities_by_english_name() -> dict[str, dict]:
    result: dict[str, dict] = {}
    def rank(row: dict) -> int:
        internal = str(row.get("internal_name", "")).casefold()
        score = 2 if row.get("description_ru") else 0
        if "abl_pc_" in internal or "psv_pc_" in internal:
            score += 8
        if row.get("kind") == "GenericTalent":
            score += 3
        if any(part in internal for part in ("_trap_", "_fx", "_control")):
            score -= 5
        return score
    for row in payload().get("entities", []):
        name = str(row.get("name_en", ""))
        if not name:
            continue
        key = _key(name)
        current = result.get(key)
        # Предпочитать объект с полноценным описанием, а не технический дубль.
        if current is None or rank(row) > rank(current):
            result[key] = row
    return result


def official_entity(english_name: str) -> dict | None:
    row = entities_by_english_name().get(_key(english_name))
    if not row:
        return None
    cleaned = dict(row)
    for field in ("name_en", "name_ru", "description_en", "description_ru"):
        cleaned[field] = _plain(str(cleaned.get(field, "")))
    return cleaned


def official_entries(table: str) -> list[dict]:
    """Полный список локализованных строк таблицы для аудита/админки."""
    return list(payload().get("tables", {}).get(table, []))
