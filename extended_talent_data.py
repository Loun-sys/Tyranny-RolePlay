"""Ветки предысторий и фракционные таланты из английской Tyranny Wiki."""

from __future__ import annotations

import asyncio
import hashlib
import html
import json
import re
from pathlib import Path
from typing import Any
from urllib.parse import quote

import aiohttp

from localization import localize_game_text
from russian_translation import translate_title as translate_generic


BACKGROUND_TALENT_PAGES = {
    "Книгочей": "Lantry talents",
    "Заклинатель": "Eb talents",
    "Зверолюд": "Kills-in-Shadow talents",
    "Певчий": "Sirin talents",
    "Танцующий": "Verse talents",
    "Авангард": "Barik talents",
}

TREE_TRANSLATIONS = {
    "Quill": "Перо", "Sage": "Книгочей", "Preservation": "Сохранение",
    "Tidecasting": "Магия приливов", "Tidal": "Магия приливов", "Gravelight": "Могильный свет",
    "Ravager": "Опустошитель", "Titan": "Титан", "Songs": "Песни", "Peace": "Мир", "War": "Война",
    "Duelist": "Дуэлянт", "Skirmisher": "Застрельщик", "Punisher": "Каратель", "Sentinel": "Страж",
    "Starting talents": "Начальные таланты",
}

FACTION_TRANSLATIONS = {
    "Stonestalker Tribe": "Каменные Сталкеры", "Forge-Bound": "Кузнецы Судьбы",
    "Disfavored": "Опальные", "Scarlet Chorus": "Алый Хор", "Vendrien Guard": "Гвардия Вендриенов",
    "Unbroken": "Несломленные", "Sages' Guild": "Школа Чернил и Пера", "Tunon": "Тунон",
    "Graven Ashe": "Грейвен Эш", "Voices of Nerat": "Голоса Нерата", "Bleden Mark": "Бледен Марк",
    # В таблице Reputation названия части фракций сокращены или записаны с артиклем.
    "Bronze Brotherhood": "Бронзовое Братство", "Dis": "Опальные",
    "Sage's Guild": "Школа Чернил и Пера", "The Unbroken": "Несломленные",
}

TITLE_PHRASES = {
    "Shield Wall": "Стена щитов", "Last Stand": "Последний рубеж", "Second Breath": "Второе дыхание",
    "Heart Shot": "Выстрел в сердце", "Blood Rage": "Кровавая ярость", "Wild Strength": "Дикая сила",
    "Flesh to Stone": "Обращение в камень", "Broken Earth": "Расколотая земля",
    "Ignore the Elements": "Игнорирование стихий", "Elemental Shield": "Стихийный щит",
    "Arcane Missile": "Мистический снаряд", "Energy Shield": "Энергетический щит",
    "Spell Barrier": "Магический барьер", "Runic Barrier": "Рунический барьер",
    "Quill Strike": "Удар пером", "Quill Flurry": "Шквал перьев", "Quillstorm": "Буря перьев",
    "Watcher’s Judgment": "Суд Наблюдателя", "Watcher's Judgment": "Суд Наблюдателя",
    "Aria of": "Ария", "Stance:": "Стойка:", "Mastery": "Мастерство",
    "Gifted": "Дар", "Loremaster": "Мастер знаний", "Defender": "Защитник", "Defense": "Защита",
    "Strike": "Удар", "Throw": "Бросок", "Death": "Смерть", "Blood": "Кровь", "Iron": "Железо",
    "Blade": "Клинок", "Claw": "Коготь", "Song": "Песнь", "Breath": "Дыхание",
    "Storm": "Буря", "Winter": "Зима", "Pain": "Боль", "Nightmares": "Кошмары",
    "Strength": "Сила", "Justice": "Правосудие", "Victory": "Победа", "Glory": "Слава",
    "Quick": "Быстрый", "Swift": "Стремительный", "Greater": "Великий", "Ancient": "Древний",
    "Natural Weaponry": "Природное оружие", "Thick Hide": "Толстая шкура", "Primal Scream": "Первобытный крик",
    "Fallen Leader": "Павший вождь", "Smelting Ore": "Плавка руды", "Extinguish": "Угасание",
}

TITLE_WORDS = {
    "accelerate":"Ускорение","adaptation":"Адаптация","arms":"Оружие","art":"Искусство","battle":"Битва",
    "bestial":"Звериная","blade":"Клинок","body":"Тело","bone":"Кость","bouncing":"Рикошетящие",
    "breaking":"Разрушение","call":"Зов","canvas":"Полотно","charged":"Заряженный","clash":"Столкновение",
    "clear":"Чистый","concealing":"Скрывающие","constitution":"Телосложение","control":"Контроль",
    "crystalline":"Кристаллический","cry":"Крик","deadeye":"Меткий глаз","deeds":"Деяния","disarming":"Обезоруживающий",
    "disembowel":"Потрошение","dissonance":"Диссонанс","dual":"Парный","elemental":"Стихийная","embrace":"Объятие",
    "empowered":"Усиленные","engagement":"Сдерживание","eternal":"Вечное","evasive":"Уклончивость","fierce":"Свирепый",
    "flame":"Пламя","fluid":"Текучее","focused":"Сосредоточенная","fury":"Ярость","gaze":"Взгляд","gift":"Дар",
    "ground":"Поле","guise":"Облик","healer":"Целитель","heroic":"Героическая","hobbled":"Хромая","honor":"Честь",
    "improvised":"Импровизированные","inspiration":"Вдохновение","instinct":"Инстинкт","instructor":"Наставник",
    "languorous":"Томный","leader":"Вождь","leaping":"Прыжок","lightning":"Молниеносные","mind":"Разум",
    "mobile":"Подвижное","mocking":"Насмешливое","moonlit":"Лунный","mother's":"Материнское","nimble":"Проворство",
    "overpower":"Превосходство","overrun":"Натиск","pack":"Стая","passage":"Течение","peace":"Покой",
    "penetrating":"Пробивающий","piercing":"Пронзающие","prey":"Добыча","purifying":"Очищающие","raking":"Рвущий",
    "rapid":"Стремительный","reaching":"Длинные","record":"Летопись","reflexes":"Рефлексы","relentless":"Неумолимость",
    "renewal":"Обновление","repelling":"Отталкивающий","resilient":"Стойкий","resonance":"Резонанс","retribution":"Возмездие",
    "reviving":"Возрождающая","runic":"Рунический","scars":"Шрамы","seasoned":"Закалённый","seeking":"Ищущие",
    "shadow":"Тень","sheath":"Ножны","skewer":"Пронзание","skull":"Череп","snapping":"Ломающий","sorrow":"Скорбь",
    "sprinting":"Стремительная","student":"Ученик","subtle":"Незаметный","suffering":"Страдание","surging":"Бушующие",
    "sustained":"Долгое","sweeping":"Сметающая","talons":"Когти","taste":"Вкус","tempo":"Темп","terratus'":"Терратуса",
    "three":"Три","tooth":"Клык","training":"Тренировка","trample":"Топот","untamed":"Неукрощённая","vigilant":"Бдительный",
    "vigor":"Рвение","wary":"Осторожный","waters":"Воды","way":"Путь","whispers":"Шёпота","wild":"Дикий",
    "wounded":"Раненый","of":"","the":"","and":"и","to":"к","i":"I","ii":"II","iii":"III","iv":"IV",
}

EFFECT_PHRASES = {
    "Ashe Aegis": "защиты Эша",
    "do not benefit from": "не получают преимуществ от", "does not benefit from": "не получает преимуществ от",
    "Damage attack": "урона атакой", "Armor penetration": "пробивания брони", "Armor Penetration": "пробивания брони",
    "Target is": "Цель получает состояние", "Targets are": "Цели получают состояние", "Foes are": "Враги получают состояние",
    "Allies receive": "Союзники получают", "On critical hit": "При критическом попадании",
    "At beginning of combat": "В начале боя", "On defeat": "При поражении", "On hit": "При попадании",
    "Recovery time": "времени восстановления", "Move Speed": "скорости передвижения",
    "Magic Defense": "защиты Магией", "Health": "здоровья", "Accuracy": "Точности", "Damage": "урона",
    "Dodge": "Уклонения", "Parry": "Парирования", "Endurance": "Выносливости", "Will": "Воли",
    "Magic": "Магии", "Resolve": "Стойкости", "Might": "Силы", "Finesse": "Искусности",
    "Quickness": "Быстроты", "Vitality": "Живучести", "Wits": "Смекалки", "Lore": "Знаний",
    "allies": "союзников", "foes": "врагов", "target": "цели", "enemy": "противника", "enemies": "противников",
    "damage": "урона", "range": "дальности", "radius": "радиусе", "seconds": "секунд", "until damaged": "до получения урона",
    "bleeding": "Кровотечение", "burning": "Горение", "stunned": "Оглушение", "dazed": "Ошеломление",
    "frightened": "Испуг", "weakened": "Слабость", "immobilized": "Обездвиживание", "pushed back": "Отбрасывание",
    "frozen": "Заморозка", "sundered": "Расколотая броня", "interrupted": "Прерывание",
}

EFFECT_WORDS = {
    "grant":"даёт","with":"с","to":"для","in":"в","a":"","an":"","the":"","and":"и","or":"или","for":"на",
    "from":"от","when":"когда","while":"пока","after":"после","before":"до","every":"каждые","all":"все",
    "additional":"дополнительный","attack":"атака","attacks":"атаки","ability":"способности","abilities":"способности",
    "affliction":"негативное состояние","afflictions":"негативные состояния","armor":"брони","arcane":"магического",
    "area":"области","beginning":"начале","beneficial":"положительные","bonus":"бонус","chance":"шанс",
    "combat":"боя","cone":"конусе","corrode":"разъедающего","critical":"критическом","crush":"дробящего",
    "current":"текущего","duration":"длительности","effect":"эффект","effects":"эффекты","elemental":"стихийного",
    "experience":"опыта","fire":"огненного","frost":"ледяного","gain":"получаемого","hostile":"враждебных",
    "immunity":"невосприимчивость","increased":"увеличивается","light":"лёгкой","magic":"магического",
    "melee":"ближнего боя","moving":"движении","only":"только","path":"линии","piece":"элемент",
    "precision":"точности","projectile":"снаряда","random":"случайный","ranged":"дальнего боя","reduce":"снижает",
    "reduced":"сокращается","remove":"снимает","retained":"сохраняемого","shock":"электрического","skill":"навыка",
    "skills":"навыков","speed":"скорости","spell":"заклинания","spells":"заклинаний","times":"раза","weapon":"оружия",
    "weapons":"оружия","wearing":"при ношении","around":"вокруг","against":"против","hits":"попадания","hit":"попадании",
    "petrified":"Окаменение","rooted":"Обездвиживание","silenced":"Безмолвие","poisoned":"Отравление",
    "confused":"Замешательство","prone":"Сбит с ног","shielded":"Щит","drain":"поглощает","heal":"исцеляет",
    "s":"сек.","m":"м","on":"при","vs":"против","of":"","modifies":"изменяет","thrown":"метательного",
    "control":"управления","by":"на","are":"получают","shield":"щита","is":"получает","two":"дважды",
    "three":"трижды","unarmed":"безоружного боя","that":"который","defense":"защиты","defenses":"защит",
    "if":"если","gravelight":"могильным светом","engaged":"сдерживает","unlocked":"открыто","default":"изначально",
    "strike":"удар","subterfuge":"Хитроумия","party":"отряда","members":"участников","per":"за","ally":"союзника",
    "breath":"дыхание","taken":"полученного","pierce":"колющего","interrupt":"прерывание","grazes":"задевания",
    "terrified":"Ужас","below":"ниже","staff":"посоха","recovery":"восстановления","at":"при","slash":"рубящего",
    "leaves":"оставляет","fatebinder":"Вершителя Судеб","deal":"наносит","barik":"Барика","weak":"слабое",
    "quill":"перо","vigor":"Рвения","life":"Жизни","return":"возвращает","mother":"матери","terratus":"Терратуса",
    "night":"ночью","stealth":"скрытности","one":"один","maximum":"максимум","disengaging":"выходе из сдерживания",
    "defensive":"защитной","song":"песни","engagement":"сдерживания","not":"не","resonant":"резонансное","field":"поле",
    "sent":"сбивает","taunted":"Провокация","dual":"парного","wield":"оружия","verse":"Фуги","bows":"Луков",
    "watch":"дозор","within":"в пределах","bond":"связь","using":"при использовании","misses":"промахи","have":"имеют",
    "left":"оставляет","paralyzed":"Паралич","knowledge":"знания","slots":"ячеек","worn":"надетый","drops":"падает",
    "revived":"возрождённый","drowning":"Утопление","grave":"могилы","bane":"Погибели","amount":"объём","drained":"поглощённого",
    "basic":"базовых","rending":"разрывающие","hobbled":"Хромота","them":"их","back":"назад","sends":"сбивает",
    "rage":"ярость","penalty":"штрафа","sword":"меч","red":"красная","affected":"затронутых","singing":"пения",
    "respite":"передышки","innocence":"невинности","heavy":"тяжёлой","deflection":"отражения","aria":"ария","summons":"призывает",
    "embodied":"воплощённый","force":"силы","attacker":"нападающего","know":"знание","your":"своего","killing":"убийства",
    "spree":"серия","kill":"убийства","rush":"рывок","dancer":"танцор","each":"каждый","scarlet":"алой","fury":"ярости",
    "primary":"основного","arrows":"стрел","athletics":"Атлетики","splitter":"раскалыватель","attackers":"нападающих",
    "cannot":"не может","be":"быть","delay":"отсрочивает","unconsciousness":"потерю сознания","clash":"столкновение",
    "iron":"железа","veteran":"ветеран","phalanx":"фаланга","total":"всего","degree":"градусов","transfer":"переносит",
    "blows":"ударов","aura":"аура","stand":"рубеж","ashe":"Эша","aegis":"защиты",
    "benefit":"преимущество","benefits":"преимущества","do":"","does":"","strikes":"удары","reduces":"сокращает",
    "cooldown":"перезарядку","flurry":"шквала","quillstorm":"бури перьев","other":"другие","projectiles":"снарядов",
    "breached":"пробитая магическая защита","judgment":"суда","raw":"чистого","d":"","i":"I","ii":"II","iii":"III","iv":"IV",
}


def _translate_title(value: str) -> str:
    result = value.replace("\u00a0", " ").strip()
    for source, target in sorted(TITLE_PHRASES.items(), key=lambda item: len(item[0]), reverse=True):
        result = re.sub(re.escape(source), target, result, flags=re.IGNORECASE)
    result = re.sub(r"([A-Za-z]+)['’]s\b", r"\1", result)
    tokens = re.split(r"(\s+|[-–:,'’])", result)
    translated = []
    for token in tokens:
        replacement = TITLE_WORDS.get(token.casefold())
        if replacement is None and re.search(r"[A-Za-z]", token):
            replacement = translate_generic(token)
        translated.append(token if replacement is None else replacement)
    return localize_game_text(re.sub(r"\s+", " ", "".join(translated)).strip())


def _translate_effect(value: str) -> str:
    value = re.sub(r"([A-Za-z]+)['’]s\b", r"\1", value)
    result = re.sub(r"(?<=\d)m\b", " м", value)
    result = re.sub(r"(?<=\d)s\b", " сек.", result)
    for source, target in sorted(EFFECT_PHRASES.items(), key=lambda item: len(item[0]), reverse=True):
        result = re.sub(re.escape(source), target, result, flags=re.IGNORECASE)
    tokens = re.split(r"(\s+|[-–:;,().'’])", result)
    words = {**TITLE_WORDS, **EFFECT_WORDS}
    translated = []
    for token in tokens:
        replacement = words.get(token.casefold())
        if replacement is None and re.search(r"[A-Za-z]", token):
            replacement = translate_generic(token)
        translated.append(token if replacement is None else replacement)
    result = "".join(translated)
    return localize_game_text(re.sub(r"\s+", " ", result).strip(" ;")) or "Описание эффекта отсутствует."


def _clean_wiki(value: str) -> str:
    value = html.unescape(value)
    value = re.sub(r"<br\s*/?>", "; ", value, flags=re.I)
    value = re.sub(r"\[\[[^]|]+\|([^]]+)]]", r"\1", value)
    value = re.sub(r"\[\[([^]]+)]]", r"\1", value)
    value = re.sub(r"\{\{[^}]+}}", "", value)
    value = re.sub(r"<[^>]+>", "", value)
    return re.sub(r"\s+", " ", value).strip()


def _icon_url(filename: str) -> str:
    filename = re.sub(r"[\s_]+", "_", filename.strip())
    normalized = filename[0].upper() + filename[1:]
    digest = hashlib.md5(normalized.encode("utf-8")).hexdigest()
    return f"https://static.wikia.nocookie.net/tyranny_gamepedia_en/images/{digest[0]}/{digest[:2]}/{quote(normalized)}/revision/latest"


def parse_talent_page(wikitext: str, background: str, page_title: str) -> list[dict[str, Any]]:
    chunks = re.split(r"\n==([^=]+)==\n", wikitext)
    result: list[dict[str, Any]] = []
    for index in range(1, len(chunks), 2):
        section_en, body = chunks[index].strip(), chunks[index + 1]
        tree = f"{background} · {TREE_TRANSLATIONS.get(section_en, _translate_title(section_en))}"
        for row in re.split(r"\n\|-\s*\n", body):
            icon = re.search(r"\{\{ficon\|([^|}]+)\|([^|}]+)", row)
            if not icon:
                continue
            cells = re.findall(r"(?:^|\n)\|\s*(?![-}])(.*?)(?=\n\||\n!|\n\|-|\n\|}|$)", row, flags=re.S)
            effect = _clean_wiki(cells[0]) if cells else ""
            requirement = _clean_wiki(cells[1]) if len(cells) > 1 else "0"
            tier_match = re.search(r"\d+", requirement)
            tier = int(tier_match.group()) if tier_match else 0
            english_name = _clean_wiki(icon.group(2))
            result.append({
                "tree": tree, "tier": tier, "name": _translate_title(english_name),
                "description": _translate_effect(effect),
                "requires": _translate_effect(requirement), "background": background,
                "automatic_level": tier if section_en == "Songs" and tier else 0,
                "icon_url": _icon_url(icon.group(1)),
                "source_url": f"https://tyranny.fandom.com/wiki/{quote(english_name.replace(' ', '_'))}",
            })
    return result


def parse_faction_talents(wikitext: str) -> list[dict[str, Any]]:
    marker = re.search(r"==\s*Unlocked abilities\s*==", wikitext, flags=re.I)
    body = wikitext[marker.end():] if marker else wikitext
    result = []
    for row in re.split(r"\n\|-\s*\n", body):
        icon = re.search(r"\{\{ficon\|([^|}]+)\|([^|}]+)", row)
        cells = re.findall(r"(?:^|\n)\|\s*(?![-}])(.*?)(?=\n\||\n!|\n\|-|\n\|}|$)", row, flags=re.S)
        if not icon or len(cells) < 2:
            continue
        requirement = _clean_wiki(cells[-1])
        axis = "favor" if re.search(r"Favor", requirement, re.I) else "wrath" if re.search(r"Wrath", requirement, re.I) else ""
        tier_match = re.search(r"(?:Favor|Wrath)\s*(\d+)", requirement, re.I)
        faction_en = re.sub(r"\s*(?:Favor|Wrath).*", "", requirement, flags=re.I).strip(" ;")
        if not axis or not tier_match or not faction_en:
            continue
        english_name = _clean_wiki(icon.group(2))
        result.append({
            "name": _translate_title(english_name),
            "description": _translate_effect(_clean_wiki(cells[-2])),
            "faction": FACTION_TRANSLATIONS.get(faction_en, faction_en), "axis": axis,
            "tier": int(tier_match.group(1)),
            "icon_url": _icon_url(icon.group(1)),
            "source_url": f"https://tyranny.fandom.com/wiki/{quote(english_name.replace(' ', '_'))}",
        })
    return result


async def load_extended_talents(data_dir: Path) -> dict[str, Any]:
    cache = data_dir / "extended_talents_cache_v2.json"
    pages = [*BACKGROUND_TALENT_PAGES.values(), "Reputation"]
    texts: dict[str, str] = {}
    timeout = aiohttp.ClientTimeout(total=20)
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async def fetch(title: str) -> tuple[str, str]:
                async with session.get("https://tyranny.fandom.com/api.php", params={
                    "action": "parse", "page": title, "prop": "wikitext", "format": "json", "origin": "*",
                }) as response:
                    response.raise_for_status()
                    payload = await response.json()
                    return title, payload["parse"]["wikitext"]["*"]
            texts = dict(await asyncio.gather(*(fetch(title) for title in pages)))
    except (aiohttp.ClientError, asyncio.TimeoutError, KeyError, ValueError):
        if cache.is_file():
            try:
                return json.loads(cache.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                pass
        return {"backgrounds": {}, "factions": []}
    backgrounds = {
        background: parse_talent_page(texts[page], background, page)
        for background, page in BACKGROUND_TALENT_PAGES.items()
    }
    payload = {"backgrounds": backgrounds, "factions": parse_faction_talents(texts["Reputation"])}
    try:
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass
    return payload
