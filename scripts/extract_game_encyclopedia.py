"""Extract Tyranny's canonical glossary from the installed game files.

The Unity bundle contains the glossary structure while localized stringtable
files contain the official Russian and English copy.  This script only reads
the game installation and writes a compact JSON file for the web client.
"""

from __future__ import annotations

import argparse
import json
import re
import unicodedata
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path

import UnityPy


GLOSSARY_SCRIPT = 8918563285009618511
TERM_LIST_SCRIPT = -5946694925631846127
TABLES = {
    1: "gui.stringtable",
    6: "abilities.stringtable",
    7: "tutorial.stringtable",
    14: "factions.stringtable",
    17: "maps.stringtable",
    19: "afflictions.stringtable",
    20: "cyclopedia.stringtable",
    22: "edicts.stringtable",
}
CATEGORIES = {
    0: "Статистика персонажа",
    1: "Игровая механика",
    2: "Воздействия и травмы",
    3: "Снаряжение",
    4: "Решения завоевания",
    5: "Места",
    6: "Мир и история",
    7: "Советы",
    8: "Благословения",
}
RUSSIAN_TITLE_FIXES = {
    "GL_Binders 2": "Мудрец",
    "GL_Tunon": "Тунон",
    "GL_Wardens_Key": "Ключ Хранителя",
}
REMOVED_ASSETS = {
    "GL_Binders 2",
    "GL_GameMechanics_CompanionCombo",
    "GL_GameMechanics_Engagement",
    "GL_GameMechanics_Scouting",
    "GL_GameMechanics_DPS",
    "GL_GameMechanics_DisengagementDefense",
}
REMOVED_CATEGORIES = {4, 7}  # Решения завоевания и советы не используются в ролевой версии.
RUSSIAN_BODY_OVERRIDES = {
    "GL_GameMechanics_Breath": """[url=glossary:дыхание]Дыхание[/url] – характеристика, определяющая, сколько раз за бой Певчий может спеть свои арии. Каждая песня разбита на стансы, и когда станс пропет, Певчий получает одно дыхание. Для каждой арии требуется определенное количество дыхания.

По окончании боя накопленное дыхание теряется.

Таланты «Быстрое дыхание» и «Спокойное дыхание» позволяют Певчему получить одно дыхание в начале боя и сохранять его между столкновениями.""",
    "GL_GameMechanics_Song": """Песни – мощные магические способности Певчего. Певчий начинает петь в начале боя. Его песни состоят из нескольких стансов, каждый из которых оказывает магические эффекты или воздействия на окружающих.

Во время пения Певчий может выполнять и другие действия. Поскольку песни магические по своей природе, их мощность зависит от Смекалки, а не от Силы.""",
    "GL_GameMechanics_Stanza": """Каждая песня Певчего состоит из нескольких стансов. В начале каждого своего хода Певчий исполняет следующий станс, после чего его эффект сразу применяется к окружающим.

Некоторые стансы благотворно влияют на союзников Певчего, другие наносят урон или накладывают воздействия на ближайших врагов. Состав и порядок стансов указываются в описании песни.""",
    "GL_GameMechanics_Cooldown": """Частота использования активной способности зависит от ее перезарядки, измеряемой в раундах. После применения счетчик уменьшается в конце каждого хода персонажа. Когда он достигает нуля, способность снова становится доступна.

Характеристика «[url=glossary:быстрота]Быстрота[/url]», таланты, предметы и другие эффекты могут сократить перезарядку. Отдых полностью восстанавливает все способности.""",
    "GL_GameMechanics_Recovery": """Период восстановления показывает, через сколько раундов персонаж сможет снова использовать действие, зависящее от экипировки. На него влияют доспехи и оружие: чем тяжелее броня и чем мощнее оружие, тем больше восстановление.

Быстрота, таланты, заклинания, предметы и зелья могут сократить восстановление, но не ниже установленного для действия минимума.""",
    "GL_GameMechanics_Interrupt": """Некоторые способности могут упреждать цель и сорвать ее действие. Упрежденный персонаж теряет подготовленное действие и получает восстановление на указанное число раундов.

Упреждающие способности бывают слабой, обычной и высокой мощности. Чем выше мощность, тем дольше цель не сможет повторить действие. Повторное упреждение не действует, пока уже наложенное восстановление не завершилось.""",
    "GL_GameMechanics_Modal": """Модальный талант – это способность, эффект которой можно включать или выключать. Одновременно может действовать только одна модальная способность.

При смене боевой стойки прежняя отключается, а новая начинает действовать с текущего хода. Если у стойки указана перезарядка, повторно включить ее можно после окончания соответствующего числа раундов.""",
    "GL_GameMechanics_Reputation": """[url=glossary:репутация]Репутация[/url] определяет отношение других персонажей и фракций к Персонажу игрока. Она измеряется по двум направлениям: благосклонность и гнев.

[url=glossary:репутация]Репутация[/url] влияет на отношение персонажей, доступные задания и уникальные способности. Благосклонность и гнев открывают разные способности.""",
    "GL_GameMechanics_Favor": """Благосклонность – одно из двух направлений шкалы репутации, определяющих, как данный персонаж или фракция относятся к Персонажу игрока.

Благосклонность растет, когда Персонаж игрока помогает представителям фракции, выполняет их задания и принимает одобряемые ими решения. По мере ее роста открываются новые фракционные способности.""",
    "GL_GameMechanics_Wrath": """Гнев – одно из двух направлений шкалы репутации, определяющих, как данный персонаж или фракция относятся к Персонажу игрока.

Гнев растет, когда Персонаж игрока выступает против представителей фракции, помогает их врагам или принимает неодобряемые ими решения. По мере его роста открываются отдельные фракционные способности.""",
    "GL_Boon_Invigorated": "В начале каждого раунда исцеляет 2% от максимума здоровья.",
}
LINK_RE = re.compile(r"\[url=glossary:([^\]]+)](.*?)\[/url]", re.I | re.S)
TAG_RE = re.compile(r"\[/?(?:url|color|b|i|u)[^\]]*]", re.I)


def normalize(value: str) -> str:
    value = unicodedata.normalize("NFKC", value or "").casefold().replace("ё", "е")
    return re.sub(r"[^a-zа-я0-9]+", " ", value).strip()


def clean_title(value: str) -> str:
    value = LINK_RE.sub(lambda match: match.group(2), value or "")
    return TAG_RE.sub("", value).strip()


def entry_aliases(title_ru: str, title_en: str, asset: str,
                  title_ru_raw: str = "", title_en_raw: str = "") -> list[str]:
    """An article's links are references, not aliases for that article.

    Including body-link targets here made e.g. Accuracy open Magic Staff and
    Critical Hit open Deflection: the browser keeps the first matching alias.
    Title markup may contain the official glossary spelling of this entry.
    """
    aliases = {title_ru, title_en, asset}
    for text in (title_ru_raw, title_en_raw):
        for match in LINK_RE.finditer(text or ""):
            if normalize(clean_title(match.group(2))) in {
                normalize(title_ru), normalize(title_en)
            }:
                aliases.update((match.group(1), clean_title(match.group(2))))
    return sorted({alias for alias in aliases if alias}, key=str.casefold)


def load_table(root: Path, filename: str) -> dict[int, str]:
    matches = list(root.rglob(filename))
    if not matches:
        return {}
    tree = ET.parse(matches[0])
    result: dict[int, str] = {}
    for entry in tree.findall(".//Entry"):
        raw_id = entry.findtext("ID")
        if raw_id is None:
            continue
        result[int(raw_id)] = entry.findtext("DefaultText") or entry.findtext("FemaleText") or ""
    return result


def load_locale(root: Path) -> dict[int, dict[int, str]]:
    return {number: load_table(root, filename) for number, filename in TABLES.items()}


def resolve(reference: dict, tables: dict[int, dict[int, str]]) -> str:
    return tables.get(int(reference.get("StringTable", -1)), {}).get(int(reference.get("StringID", -1)), "")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--game-data", type=Path, required=True, help="Tyranny Data directory")
    parser.add_argument("--en", type=Path, required=True, help="English localized directory")
    parser.add_argument("--ru", type=Path, required=True, help="Russian localized directory")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    bundle = args.game_data / "bundles" / "lists.unity3d"
    if not bundle.exists():
        raise SystemExit(f"Bundle not found: {bundle}")
    en_tables, ru_tables = load_locale(args.en), load_locale(args.ru)
    environment = UnityPy.load(str(bundle))

    raw_entries: dict[int, dict] = {}
    canonical_order: list[int] = []
    for obj in environment.objects:
        if obj.type.name != "MonoBehaviour":
            continue
        try:
            value = obj.read_typetree()
        except Exception:
            continue
        script = value.get("m_Script", {}).get("m_PathID")
        if script == GLOSSARY_SCRIPT:
            raw_entries[obj.path_id] = value
        elif script == TERM_LIST_SCRIPT and value.get("m_Name") == "GlossaryEntries":
            canonical_order = [int(ref.get("m_PathID", 0)) for ref in value.get("Entries", [])]

    raw_entries = {path_id: value for path_id, value in raw_entries.items() if value.get("m_Name") not in REMOVED_ASSETS and int(value.get("Category", 0)) not in REMOVED_CATEGORIES}
    order = [path_id for path_id in canonical_order if path_id in raw_entries]
    order.extend(path_id for path_id in raw_entries if path_id not in set(order))
    key_by_path = {path_id: raw_entries[path_id].get("m_Name", f"entry_{path_id}").casefold() for path_id in order}
    entries = []
    for path_id in order:
        source = raw_entries[path_id]
        title_ru_raw = resolve(source.get("Title", {}), ru_tables)
        body_ru = resolve(source.get("Body", {}), ru_tables)
        title_en_raw = resolve(source.get("Title", {}), en_tables)
        body_en = resolve(source.get("Body", {}), en_tables)
        title_ru, title_en = clean_title(title_ru_raw), clean_title(title_en_raw)
        title_ru = RUSSIAN_TITLE_FIXES.get(source.get("m_Name", ""), title_ru)
        body_ru = RUSSIAN_BODY_OVERRIDES.get(source.get("m_Name", ""), body_ru)
        if int(source.get("Category", 0)) == 1:
            body_ru = body_ru.replace("к Вершителю судеб", "к Персонажу игрока").replace("к Вершителю", "к Персонажу игрока").replace("Вершителю судеб", "Персонажу игрока").replace("Вершителя судеб", "Персонажа игрока")
        if source.get("m_Name") == "GL_Boon_Quality_Alone_Time":
            body_ru = body_ru.replace("с одноручным оружием", "с оружием")
        aliases = entry_aliases(title_ru, title_en, source.get("m_Name", ""),
                                title_ru_raw, title_en_raw)
        category = int(source.get("Category", 0))
        entries.append({
            "key": key_by_path[path_id],
            "asset": source.get("m_Name", ""),
            "title": title_ru or title_en or source.get("m_Name", ""),
            "titleEn": title_en,
            "body": body_ru or body_en,
            "bodyEn": body_en,
            "category": category,
            "categoryName": CATEGORIES.get(category, "Прочее"),
            "related": [key_by_path[ref["m_PathID"]] for ref in source.get("LinkedEntries", []) if ref.get("m_PathID") in key_by_path],
            "aliases": aliases,
            "search": normalize(" ".join(aliases + [body_ru, body_en])),
            "showInJournal": bool(source.get("ShowInJournal", 0)),
            "journalOnly": bool(source.get("JournalOnly", 0)),
            "notInConversation": bool(source.get("NotInConversation", 0)),
        })

    payload = {
        "version": 1,
        "source": "Tyranny game localization and lists.unity3d",
        "languages": ["ru", "en"],
        "categories": [{"id": key, "name": value, "count": sum(e["category"] == key for e in entries)} for key, value in CATEGORIES.items() if any(e["category"] == key for e in entries)],
        "entries": entries,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"Wrote {len(entries)} entries to {args.output}")
    print("Categories:", dict(sorted(Counter(entry["category"] for entry in entries).items())))


if __name__ == "__main__":
    main()
