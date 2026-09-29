"""HTTP-мост между статическим конструктором GitHub Pages и Discord-ботом."""

from __future__ import annotations

import base64
import asyncio
import hashlib
import io
import os
import re
from pathlib import Path
from typing import Any
from urllib.parse import quote, unquote, urlsplit

import aiohttp
from aiohttp import web
from PIL import Image

from constants import (
    ABILITY_DETAILS, ACCENT_SIGILS, ATTRIBUTE_DETAILS, ATTRIBUTES, BACKGROUND_BONUSES,
    BACKGROUND_DESCRIPTIONS, BACKGROUNDS, SKILLS,
    BACKGROUND_TALENT_SOURCES,
    CORE_SIGILS, ENHANCEMENT_SIGILS, EQUIPMENT_SLOTS, EXPRESSION_SIGILS,
    SKILL_ATTRIBUTES, SPECIALIZATIONS, SPECIALIZATION_ABILITIES,
    SPECIALIZATION_ABILITY_CHOICES, SPECIALIZATION_BONUSES, SPECIALIZATION_DESCRIPTIONS,
)
from mechanics_data import MECHANICS
from talent_data import TALENT_BY_NAME, TALENTS
from extended_talent_data import load_extended_talents


MAX_IMAGE_BYTES = 5 * 1024 * 1024
ATTRIBUTE_TOTAL = 68  # шесть базовых значений 10 + восемь очков Tyranny
SKILL_POINTS = 20


def _cors(request: web.Request, response: web.StreamResponse) -> web.StreamResponse:
    allowed = os.getenv("TYRANNY_WEB_ORIGIN", "*").strip() or "*"
    origin = request.headers.get("Origin", "")
    if allowed == "*" or origin in {item.strip() for item in allowed.split(",")}:
        response.headers["Access-Control-Allow-Origin"] = origin or "*"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type"
    response.headers["Access-Control-Allow-Methods"] = "GET,POST,PATCH,OPTIONS"
    response.headers["Vary"] = "Origin"
    return response


@web.middleware
async def cors_middleware(request: web.Request, handler):
    if request.method == "OPTIONS":
        return _cors(request, web.Response(status=204))
    try:
        response = await handler(request)
    except web.HTTPException as error:
        response = web.json_response({"ok": False, "error": error.reason}, status=error.status)
    return _cors(request, response)


def _configuration() -> dict[str, Any]:
    return {
        "attributes": list(ATTRIBUTES), "backgrounds": list(BACKGROUNDS),
        "specializations": list(SPECIALIZATIONS), "skills": list(SKILLS),
        "attributeTotal": ATTRIBUTE_TOTAL, "skillPoints": SKILL_POINTS,
        "attributeMin": 8, "attributeMax": 18,
        "specializationDetails": {
            name: {
                "description": SPECIALIZATION_DESCRIPTIONS[name],
                "bonuses": SPECIALIZATION_BONUSES[name],
                "abilities": [
                    {"name": ability, **ABILITY_DETAILS[ability]}
                    for ability in SPECIALIZATION_ABILITY_CHOICES[name]
                ],
            }
            for name in SPECIALIZATIONS
        },
        "attributeDetails": ATTRIBUTE_DETAILS,
        "abilityDetails": ABILITY_DETAILS,
        "skillAttributes": {name: list(pair) for name, pair in SKILL_ATTRIBUTES.items()},
        "backgroundDetails": {
            name: {"description": BACKGROUND_DESCRIPTIONS[name], "bonuses": BACKGROUND_BONUSES[name],
                   "talentSource": BACKGROUND_TALENT_SOURCES[name]}
            for name in BACKGROUNDS
        },
    }


def _validate_payload(payload: dict[str, Any]) -> tuple[dict[str, Any] | None, str]:
    name = str(payload.get("name", "")).strip()
    background = str(payload.get("background", ""))
    first = str(payload.get("specialization1", ""))
    second = str(payload.get("specialization2", ""))
    if not 2 <= len(name) <= 80:
        return None, "Имя должно содержать от 2 до 80 символов."
    if background not in BACKGROUNDS:
        return None, "Выберите происхождение из списка."
    if first not in SPECIALIZATIONS or second not in SPECIALIZATIONS:
        return None, "Выберите основную и дополнительную специализации."
    ability1 = str(payload.get("ability1", SPECIALIZATION_ABILITIES.get(first, "")))
    ability2 = str(payload.get("ability2", SPECIALIZATION_ABILITIES.get(second, "")))
    if ability1 not in SPECIALIZATION_ABILITY_CHOICES[first] or ability2 not in SPECIALIZATION_ABILITY_CHOICES[second]:
        return None, "Выберите допустимую стартовую способность для каждой специализации."
    raw_attributes = payload.get("attributes")
    raw_skills = payload.get("skills")
    if not isinstance(raw_attributes, dict) or not isinstance(raw_skills, dict):
        return None, "Распределение характеристик или навыков повреждено."
    try:
        attributes = {name: int(raw_attributes[name]) for name in ATTRIBUTES}
        skills = {name: int(raw_skills.get(name, 0)) for name in SKILLS}
    except (KeyError, TypeError, ValueError):
        return None, "Все значения должны быть целыми числами."
    if any(value < 8 or value > 18 for value in attributes.values()) or sum(attributes.values()) != ATTRIBUTE_TOTAL:
        return None, f"Характеристики должны быть от 8 до 18, общая сумма — {ATTRIBUTE_TOTAL}."
    if any(value < 0 or value > SKILL_POINTS for value in skills.values()) or sum(skills.values()) != SKILL_POINTS:
        return None, f"Распределите ровно {SKILL_POINTS} дополнительных очков навыков."
    return {
        "name": name, "background": background, "specialization1": first,
        "specialization2": second, "ability1": ability1, "ability2": ability2,
        "attributes": attributes, "skills": skills,
        "portrait": str(payload.get("portrait", "")),
    }, ""


def _save_portrait(data_url: str, data_dir: Path, guild_id: int, user_id: int) -> str:
    if not data_url:
        return ""
    if not data_url.startswith("data:image/") or ";base64," not in data_url:
        raise ValueError("Портрет должен быть изображением PNG, JPEG или WEBP.")
    header, encoded = data_url.split(",", 1)
    try:
        raw = base64.b64decode(encoded, validate=True)
    except (ValueError, base64.binascii.Error) as error:
        raise ValueError("Не удалось прочитать изображение.") from error
    if len(raw) > MAX_IMAGE_BYTES:
        raise ValueError("Портрет превышает лимит 5 МБ.")
    try:
        image = Image.open(io.BytesIO(raw))
        image.verify()
        image = Image.open(io.BytesIO(raw)).convert("RGB")
    except Exception as error:
        raise ValueError("Файл не является корректным изображением.") from error
    image.thumbnail((1600, 1600), Image.Resampling.LANCZOS)
    portraits = data_dir / "portraits"
    portraits.mkdir(parents=True, exist_ok=True)
    path = portraits / f"{guild_id}_{user_id}.webp"
    image.save(path, "WEBP", quality=90, method=6)
    return f"local://{path.resolve().as_posix()}"


async def registration_info(request: web.Request) -> web.Response:
    token = request.match_info["token"]
    owner = await request.app["db"].registration_token_owner(token)
    if not owner:
        raise web.HTTPGone(reason="Ссылка недействительна, уже использована или истекла.")
    return web.json_response({"ok": True, "config": _configuration()})


async def registration_submit(request: web.Request) -> web.Response:
    token = request.match_info["token"]
    owner = await request.app["db"].registration_token_owner(token)
    if not owner:
        raise web.HTTPGone(reason="Ссылка недействительна, уже использована или истекла.")
    try:
        payload = await request.json()
    except Exception as error:
        raise web.HTTPBadRequest(reason="Некорректный формат анкеты.") from error
    clean, problem = _validate_payload(payload)
    if not clean:
        raise web.HTTPBadRequest(reason=problem)
    guild_id, user_id = owner
    portrait = _save_portrait(clean["portrait"], request.app["data_dir"], guild_id, user_id)
    db = request.app["db"]
    character_id = await db.create_character(
        guild_id, user_id, clean["name"], clean["background"],
        clean["specialization1"], clean["specialization2"], [clean["ability1"], clean["ability2"]],
    )
    for name, value in clean["attributes"].items():
        await db.set_attribute(character_id, name, value)
    character = await db.get_character(guild_id, user_id)
    for name, extra in clean["skills"].items():
        await db.set_skill(character_id, name, character["skills"][name]["value"] + extra)
    if portrait:
        await db.update_character_text(character_id, "portrait_url", portrait)
    if not await db.consume_registration_token(token):
        raise web.HTTPConflict(reason="Эта ссылка уже была использована.")
    try:
        user = request.app["bot"].get_user(user_id) or await request.app["bot"].fetch_user(user_id)
        await user.send(f"Личное дело **{clean['name']}** сохранено. Откройте его командой `/персонаж`.")
    except Exception:
        pass
    return web.json_response({"ok": True, "name": clean["name"]})


def _portrait_url(request: web.Request, value: str) -> str:
    if not value:
        return ""
    if value.startswith("local://"):
        scheme = request.headers.get("X-Forwarded-Proto", request.scheme).split(",", 1)[0].strip()
        return f"{scheme}://{request.host}/media/portraits/{Path(value[8:]).name}"
    return value if value.startswith("https://") else ""


def _public_base(request: web.Request) -> str:
    scheme = request.headers.get("X-Forwarded-Proto", request.scheme).split(",", 1)[0].strip()
    return f"{scheme}://{request.host}"


def _proxied_talent(request: web.Request, talent: dict[str, Any]) -> dict[str, Any]:
    """Serve Wiki art through our API so browser hot-link protection cannot break it."""
    result = dict(talent)
    icon_url = str(result.get("icon_url", ""))
    parts = unquote(urlsplit(icon_url).path).split("/")
    try:
        filename = re.sub(r"[\s_]+", "_", Path(parts[parts.index("revision") - 1]).name)
    except (ValueError, IndexError):
        return result
    if re.fullmatch(r"[\w .()'’-]+\.(?:png|jpe?g|webp)", filename, flags=re.I):
        result["icon_url"] = f"{_public_base(request)}/media/wiki-icons/{quote(filename)}"
    return result


def _wiki_cdn_url(filename: str) -> str:
    filename = re.sub(r"[\s_]+", "_", filename.strip())
    normalized = filename[0].upper() + filename[1:]
    digest = hashlib.md5(normalized.encode("utf-8")).hexdigest()
    return (
        "https://static.wikia.nocookie.net/tyranny_gamepedia_en/images/"
        f"{digest[0]}/{digest[:2]}/{quote(normalized)}/revision/latest"
    )


def _derived(character: dict[str, Any], inventory: list[dict[str, Any]]) -> dict[str, Any]:
    attrs = character["attributes"]
    quickness = attrs.get("Быстрота", 10)
    resolve = attrs.get("Стойкость", 10)
    return {
        "defenses": {
            "Выносливость": round(resolve * 1.5 + attrs.get("Сила", 10) * .5),
            "Воля": round(resolve * 1.5 + attrs.get("Живучесть", 10) * .5),
            "Магия": round(resolve * 1.5 + attrs.get("Смекалка", 10) * .5),
            "Парирование": character["skills"].get("Парирование", {}).get("value", 0),
            "Уклонение": character["skills"].get("Уклонение", {}).get("value", 0),
        },
        "cooldownMultiplier": round(max(.1, 1 - (quickness - 10) * .03), 3),
        "cooldownPercent": round((1 - max(.1, 1 - (quickness - 10) * .03)) * 100),
        "equipmentRecovery": round(sum(float(item.get("recovery") or 0) for item in inventory if item.get("equipped_slot")), 2),
    }


def _clean_inventory(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result = []
    for row in rows:
        item = dict(row)
        try:
            item["properties"] = __import__("json").loads(item.get("properties") or "{}")
        except (TypeError, ValueError):
            item["properties"] = {}
        result.append(item)
    return result


async def _dashboard(request: web.Request, character_id: int) -> dict[str, Any]:
    db = request.app["db"]
    character = await db.get_character_by_id(character_id)
    if not character:
        raise web.HTTPNotFound(reason="Персонаж не найден.")
    inventory = _clean_inventory(await db.inventory(character_id))
    character["portrait_url"] = _portrait_url(request, character.get("portrait_url", ""))
    character.pop("guild_id", None)
    character.pop("user_id", None)
    background_talents = request.app["extended_talents"]["backgrounds"].get(character["background"], [])
    reputations = {row["faction"]: row for row in await db.reputations(character_id)}
    return {
        "character": character,
        "inventory": inventory,
        "capacity": await db.inventory_capacity(character_id),
        "spells": await db.spells(character_id),
        "derived": _derived(character, inventory),
        "equipmentSlots": list(EQUIPMENT_SLOTS),
        "talentLibrary": [_proxied_talent(request, item) for item in [*TALENTS, *background_talents]],
        "reputations": reputations,
        "factionTalents": [_proxied_talent(request, item) for item in request.app["extended_talents"]["factions"]],
        "sigils": {
            "cores": list(CORE_SIGILS), "expressions": list(EXPRESSION_SIGILS),
            "accents": list(ACCENT_SIGILS), "enhancements": list(ENHANCEMENT_SIGILS),
        },
        "attributeDetails": ATTRIBUTE_DETAILS,
        "abilityDetails": ABILITY_DETAILS,
        "skillAttributes": {name: list(pair) for name, pair in SKILL_ATTRIBUTES.items()},
        "mechanics": MECHANICS,
    }


async def archive_list(request: web.Request) -> web.Response:
    rows = await request.app["db"].archive_characters()
    for row in rows:
        row["portrait_url"] = _portrait_url(request, row.get("portrait_url", ""))
    return web.json_response({"ok": True, "characters": rows})


async def archive_character(request: web.Request) -> web.Response:
    character_id = int(request.match_info["character_id"])
    payload = await _dashboard(request, character_id)
    for field in ("notes", "attribute_points", "talent_points", "rewarded_level"):
        payload["character"].pop(field, None)
    payload.pop("talentLibrary", None)
    payload.pop("sigils", None)
    return web.json_response({"ok": True, **payload})


async def portal_info(request: web.Request) -> web.Response:
    character_id = await request.app["db"].portal_character_id(request.match_info["token"])
    if not character_id:
        raise web.HTTPGone(reason="Личная ссылка истекла или была заменена новой.")
    return web.json_response({"ok": True, **await _dashboard(request, character_id)})


async def _portal_payload(request: web.Request) -> tuple[int, dict[str, Any]]:
    character_id = await request.app["db"].portal_character_id(request.match_info["token"])
    if not character_id:
        raise web.HTTPGone(reason="Личная ссылка истекла или была заменена новой.")
    try:
        payload = await request.json()
    except Exception as error:
        raise web.HTTPBadRequest(reason="Некорректные данные.") from error
    return character_id, payload


async def portal_attribute(request: web.Request) -> web.Response:
    cid, payload = await _portal_payload(request)
    ok, message = await request.app["db"].spend_attribute_point(cid, str(payload.get("name", "")))
    if not ok:
        raise web.HTTPConflict(reason=message)
    return web.json_response({"ok": True, "message": message, **await _dashboard(request, cid)})


async def portal_talent(request: web.Request) -> web.Response:
    cid, payload = await _portal_payload(request)
    character = await request.app["db"].get_character_by_id(cid)
    library = [*TALENTS, *request.app["extended_talents"]["backgrounds"].get(character["background"], [])]
    talent = next((item for item in library if item["name"].casefold() == str(payload.get("name", "")).casefold()), None)
    if not talent:
        raise web.HTTPBadRequest(reason="Талант не найден.")
    if talent.get("automatic_level"):
        raise web.HTTPConflict(reason="Этот талант открывается автоматически с уровнем.")
    ok, message = await request.app["db"].spend_talent_point(cid, talent)
    if not ok:
        raise web.HTTPConflict(reason=message)
    return web.json_response({"ok": True, "message": message, **await _dashboard(request, cid)})


async def portal_spell(request: web.Request) -> web.Response:
    cid, payload = await _portal_payload(request)
    core, expression = str(payload.get("core", "")), str(payload.get("expression", ""))
    accents = [str(x) for x in payload.get("accents", [])]
    enhancements = [str(x) for x in payload.get("enhancements", [])]
    if core not in CORE_SIGILS or expression not in EXPRESSION_SIGILS:
        raise web.HTTPBadRequest(reason="Выберите допустимые сигилы основы и выражения.")
    if any(x not in ACCENT_SIGILS for x in accents) or any(x not in ENHANCEMENT_SIGILS for x in enhancements):
        raise web.HTTPBadRequest(reason="В формуле есть неизвестный сигил.")
    difficulty = int(payload.get("difficulty", 0))
    character = await request.app["db"].get_character_by_id(cid)
    if difficulty > character["skills"]["Знания"]["value"]:
        raise web.HTTPConflict(reason="Знаний персонажа недостаточно для этой сложности.")
    name = str(payload.get("name", "")).strip()
    if not 2 <= len(name) <= 80:
        raise web.HTTPBadRequest(reason="Введите название заклинания.")
    await request.app["db"].create_spell(cid, name, core, expression, accents, enhancements, difficulty)
    return web.json_response({"ok": True, "message": f"Заклинание «{name}» записано.", **await _dashboard(request, cid)})


async def portal_equip(request: web.Request) -> web.Response:
    cid, payload = await _portal_payload(request)
    if payload.get("unequip"):
        ok = await request.app["db"].unequip(cid, int(payload.get("inventoryId", 0)))
        message = "Предмет снят." if ok else "Предмет не найден."
    else:
        ok, message = await request.app["db"].equip(cid, int(payload.get("inventoryId", 0)), str(payload.get("slot", "")))
    if not ok:
        raise web.HTTPConflict(reason=message)
    return web.json_response({"ok": True, "message": message, **await _dashboard(request, cid)})


async def portrait_media(request: web.Request) -> web.StreamResponse:
    name = Path(request.match_info["name"]).name
    path = (request.app["data_dir"] / "portraits" / name).resolve()
    root = (request.app["data_dir"] / "portraits").resolve()
    if path.parent != root or not path.is_file():
        raise web.HTTPNotFound()
    return web.FileResponse(path)


async def wiki_icon_media(request: web.Request) -> web.Response:
    filename = unquote(request.match_info["name"])
    if Path(filename).name != filename or not re.fullmatch(r"[\w .()'’-]+\.(?:png|jpe?g|webp)", filename, flags=re.I):
        raise web.HTTPNotFound()
    cached = request.app["wiki_icon_cache"].get(filename)
    if cached is None:
        timeout = aiohttp.ClientTimeout(total=20)
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(_wiki_cdn_url(filename), headers={"User-Agent": "Mozilla/5.0 Tyranny-RolePlay"}) as response:
                    if response.status != 200:
                        raise web.HTTPNotFound()
                    body = await response.read()
                    if not body or len(body) > 2 * 1024 * 1024:
                        raise web.HTTPNotFound()
                    cached = (body, response.headers.get("Content-Type", "image/webp").split(";", 1)[0])
                    request.app["wiki_icon_cache"][filename] = cached
        except (aiohttp.ClientError, asyncio.TimeoutError):
            raise web.HTTPBadGateway(reason="Tyranny Wiki временно не отдала иконку.")
    return web.Response(body=cached[0], content_type=cached[1], headers={"Cache-Control": "public, max-age=604800"})


async def health(_: web.Request) -> web.Response:
    return web.json_response({"ok": True, "service": "tyranny-registration"})


async def start_registration_api(bot: Any, db: Any, data_dir: Path) -> web.AppRunner | None:
    if os.getenv("TYRANNY_ENABLE_WEB", "1").strip().casefold() in {"0", "false", "no"}:
        return None
    app = web.Application(middlewares=[cors_middleware], client_max_size=7 * 1024 * 1024)
    app["bot"], app["db"], app["data_dir"] = bot, db, data_dir
    app["wiki_icon_cache"] = {}
    app["extended_talents"] = await load_extended_talents(data_dir)
    app.router.add_get("/health", health)
    app.router.add_get("/api/registration/{token}", registration_info)
    app.router.add_post("/api/registration/{token}", registration_submit)
    app.router.add_options("/api/registration/{token}", lambda _: web.Response(status=204))
    app.router.add_get("/api/archive", archive_list)
    app.router.add_get("/api/archive/{character_id}", archive_character)
    app.router.add_get("/api/portal/{token}", portal_info)
    app.router.add_post("/api/portal/{token}/attribute", portal_attribute)
    app.router.add_post("/api/portal/{token}/talent", portal_talent)
    app.router.add_post("/api/portal/{token}/spell", portal_spell)
    app.router.add_post("/api/portal/{token}/equipment", portal_equip)
    app.router.add_get("/media/portraits/{name}", portrait_media)
    app.router.add_get("/media/wiki-icons/{name}", wiki_icon_media)
    app.router.add_route("OPTIONS", "/api/{tail:.*}", lambda _: web.Response(status=204))
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, os.getenv("HOST", "0.0.0.0"), int(os.getenv("PORT", "8080")))
    await site.start()
    return runner
