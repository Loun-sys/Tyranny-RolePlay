"""Собрать канонический англо-русский словарь из установленной Tyranny.

Строки в английской и русской локализациях имеют одинаковые таблицу и ID,
поэтому такой импорт точнее любого машинного перевода и не зависит от Wiki.
"""

from __future__ import annotations

import argparse
import difflib
import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path


GAMEPLAY_TABLES = (
    "abilities", "afflictions", "backstory", "characterprogression", "characters",
    "cyclopedia", "edicts", "factions", "gui", "itemmods", "items", "lifepath",
    "recipes", "reputationchangereasons", "stronghold", "tutorial", "unassigned",
)

CORE_NAMES = {
    "Atrophy": "Истощение", "Emotions": "Эмоции", "Fire": "Огонь",
    "Force": "Сила", "Frost": "Холод", "Illusion": "Иллюзия",
    "Life": "Жизнь", "Lightning": "Молния", "Stone": "Камень",
    "Terratus": "Терратус", "Vigor": "Рвение",
}

EXPRESSION_NAMES = {
    "Influential": "Область влияния", "Directed": "Направленная сила",
    "Chaotic": "Хаотическое нисхождение", "FocusedExp": "Сосредоточенное намерение",
    "Channeled": "Проводимая сила", "Guarded": "Охранная форма",
    "Material": "Материальная сила", "Proximate": "Ближнее действие",
    "Distant": "Дальний удар",
}


def read_table(path: Path) -> dict[int, str]:
    root = ET.parse(path).getroot()
    return {
        int(entry.findtext("ID")): (entry.findtext("DefaultText") or "").strip()
        for entry in root.findall(".//Entry") if entry.findtext("ID") is not None
    }


def plain(value: str) -> str:
    value = re.sub(r"\[/?url(?:=[^]]+)?\]", "", value)
    return re.sub(r"\s+", " ", value).strip()


def normalized(value: str) -> str:
    return plain(value).replace("’", "'").casefold()


def spell_formulas(snapshot: Path, english: dict[int, str], russian: dict[int, str]) -> list[dict]:
    if not snapshot.is_file():
        return []
    pages = json.loads(snapshot.read_text(encoding="utf-8")).get("pages", [])
    candidates: dict[str, list[int]] = {}
    for string_id, value in english.items():
        if value:
            candidates.setdefault(normalized(value), []).append(string_id)

    def localized_long_text(value: str) -> tuple[int, str]:
        exact = candidates.get(normalized(value), [])
        if exact:
            return exact[0], plain(russian.get(exact[0], ""))
        wanted = normalized(value)
        likely = [
            (difflib.SequenceMatcher(None, wanted, key).ratio(), ids[0])
            for key, ids in candidates.items() if len(key) >= 30 and abs(len(key) - len(wanted)) < 80
        ]
        score, string_id = max(likely, default=(0.0, -1))
        if score >= 0.82:
            return string_id, plain(russian.get(string_id, ""))
        words = set(re.findall(r"[a-z]{4,}", wanted))
        overlaps = []
        for candidate, ids in candidates.items():
            candidate_words = set(re.findall(r"[a-z]{4,}", candidate))
            union = words | candidate_words
            if union:
                overlaps.append((len(words & candidate_words) / len(union), ids[0]))
        word_score, string_id = max(overlaps, default=(0.0, -1))
        return (string_id, plain(russian.get(string_id, ""))) if word_score >= 0.5 else (-1, "")

    result = []
    for page in pages:
        categories = " ".join(page.get("categories", [])).casefold()
        if "spells" not in categories or page.get("title_en") in {"Spells", "Spell creation"}:
            continue
        text = page.get("wikitext_en", "")
        core_match = re.search(r"\|\s*core\s*=\s*\{\{([^|}\n]+)", text, re.I)
        expression_match = re.search(r"\|\s*expression\s*=\s*\{\{([^|}\n]+)", text, re.I)
        if not core_match or not expression_match:
            continue
        title_en = page["title_en"].replace(" (Spell)", "")
        # В Wiki сохранена старая опечатка, тогда как в ресурсах игры она исправлена.
        lookup_title = title_en.replace("Mischevious", "Mischievous")
        ids = candidates.get(normalized(lookup_title), [])
        # Первое употребление обычно является основным названием способности;
        # более поздние дубликаты встречаются в списках интерфейса.
        string_id = ids[0] if ids else -1
        title_ru = plain(russian.get(string_id, "")) if string_id >= 0 else ""
        description_match = re.search(r"==\s*Description\s*==\s*(.*?)(?:\n\s*\n|\n==)", text, re.I | re.S)
        description_en = plain(description_match.group(1)) if description_match else ""
        description_id, description_ru = localized_long_text(description_en) if description_en else (-1, "")
        result.append({
            "core": CORE_NAMES.get(core_match.group(1), core_match.group(1)),
            "expression": EXPRESSION_NAMES.get(expression_match.group(1), expression_match.group(1)),
            "title_en": title_en,
            "title_ru": title_ru,
            "string_id": string_id,
            "description_en": description_en,
            "description_ru": description_ru,
            "description_id": description_id,
        })
    return sorted(result, key=lambda row: (row["core"], row["expression"]))


def unity_entities(bundles: Path, tables: dict[str, list[dict]]) -> list[dict]:
    """Связать названия и описания способностей через сериализованные объекты."""
    try:
        import UnityPy
    except ImportError:
        return []
    table_numbers = {5: "items", 6: "abilities", 19: "afflictions"}
    indexes = {
        name: {row["id"]: row for row in rows}
        for name, rows in tables.items()
    }
    result: list[dict] = []
    seen: set[tuple[str, str, int]] = set()
    accepted = {"GenericAbility", "GenericTalent", "Affliction", "Equippable", "Item", "Consumable"}
    for filename in ("abilities.unity3d", "spells.unity3d", "afflictions.unity3d", "items.unity3d"):
        path = bundles / filename
        if not path.is_file():
            continue
        environment = UnityPy.load(str(path))
        objects = {obj.path_id: obj for obj in environment.objects}
        for obj in environment.objects:
            if obj.type.name != "MonoBehaviour":
                continue
            try:
                script_name = obj.read().m_Script.read().m_Name
            except Exception:
                continue
            if filename != "items.unity3d" and script_name not in accepted:
                continue
            try:
                tree = obj.read_typetree()
            except Exception:
                continue
            display = tree.get("DisplayName", {})
            description = tree.get("Description") or tree.get("DescriptionText") or {}
            table_name = table_numbers.get(display.get("StringTable"))
            string_id = int(display.get("StringID", -1))
            if not table_name or string_id < 0:
                continue
            row = indexes.get(table_name, {}).get(string_id, {})
            description_row = indexes.get(table_numbers.get(description.get("StringTable"), ""), {}).get(
                int(description.get("StringID", -1)), {}
            )
            game_object_id = tree.get("m_GameObject", {}).get("m_PathID", 0)
            try:
                internal_name = objects[game_object_id].read().m_Name
            except Exception:
                internal_name = ""
            unique = (script_name, internal_name, string_id)
            if unique in seen:
                continue
            seen.add(unique)
            result.append({
                "kind": script_name,
                "internal_name": internal_name,
                "table": table_name,
                "name_id": string_id,
                "name_en": row.get("en", ""),
                "name_ru": row.get("ru", ""),
                "description_id": int(description.get("StringID", -1)),
                "description_en": description_row.get("en", ""),
                "description_ru": description_row.get("ru", ""),
            })
    return sorted(result, key=lambda row: (row["kind"], row["internal_name"], row["name_id"]))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--localized", type=Path, default=Path(r"C:/Games/Tyranny/Data/data/exported/localized"))
    parser.add_argument("--wiki", type=Path, default=Path("catalog/tyranny_wiki_en.json"))
    parser.add_argument("--bundles", type=Path, default=Path(r"C:/Games/Tyranny/Data/bundles"))
    parser.add_argument("--output", type=Path, default=Path("catalog/official_game_localization.json"))
    args = parser.parse_args()

    tables: dict[str, list[dict]] = {}
    for name in GAMEPLAY_TABLES:
        en_path = args.localized / "en" / "text" / "game" / f"{name}.stringtable"
        ru_path = args.localized / "ru" / "text" / "game" / f"{name}.stringtable"
        if not en_path.is_file() or not ru_path.is_file():
            continue
        en, ru = read_table(en_path), read_table(ru_path)
        tables[name] = [
            {"id": string_id, "en": en.get(string_id, ""), "ru": ru.get(string_id, "")}
            for string_id in sorted(en.keys() | ru.keys())
            if en.get(string_id, "").strip() or ru.get(string_id, "").strip()
        ]

    abilities_en = {row["id"]: row["en"] for row in tables.get("abilities", [])}
    abilities_ru = {row["id"]: row["ru"] for row in tables.get("abilities", [])}
    payload = {
        "format": 1,
        "source": "Tyranny/Data/data/exported/localized/{en,ru}/text/game",
        "tables": tables,
        "spell_formulas": spell_formulas(args.wiki, abilities_en, abilities_ru),
        "entities": unity_entities(args.bundles, tables),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    entry_count = sum(len(rows) for rows in tables.values())
    print(
        f"Сохранено {entry_count} официальных строк, {len(payload['entities'])} игровых сущностей "
        f"и {len(payload['spell_formulas'])} формул: {args.output}"
    )


if __name__ == "__main__":
    main()
