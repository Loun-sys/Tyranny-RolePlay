"""HTTP-мост между статическим конструктором GitHub Pages и Discord-ботом."""

from __future__ import annotations

import base64
import io
import os
from pathlib import Path
from typing import Any

from aiohttp import web
from PIL import Image

from constants import (
    ABILITY_DETAILS, ATTRIBUTE_DETAILS, ATTRIBUTES, BACKGROUND_BONUSES,
    BACKGROUND_DESCRIPTIONS, BACKGROUNDS, SKILLS,
    SKILL_ATTRIBUTES, SPECIALIZATIONS, SPECIALIZATION_ABILITIES,
    SPECIALIZATION_ABILITY_CHOICES, SPECIALIZATION_BONUSES, SPECIALIZATION_DESCRIPTIONS,
)


MAX_IMAGE_BYTES = 5 * 1024 * 1024
ATTRIBUTE_TOTAL = 68  # шесть базовых значений 10 + восемь очков Tyranny
SKILL_POINTS = 20


def _cors(request: web.Request, response: web.StreamResponse) -> web.StreamResponse:
    allowed = os.getenv("TYRANNY_WEB_ORIGIN", "*").strip() or "*"
    origin = request.headers.get("Origin", "")
    if allowed == "*" or origin in {item.strip() for item in allowed.split(",")}:
        response.headers["Access-Control-Allow-Origin"] = origin or "*"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type"
    response.headers["Access-Control-Allow-Methods"] = "GET,POST,OPTIONS"
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
        "skillAttributes": {name: list(pair) for name, pair in SKILL_ATTRIBUTES.items()},
        "backgroundDetails": {
            name: {"description": BACKGROUND_DESCRIPTIONS[name], "bonuses": BACKGROUND_BONUSES[name]}
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


async def health(_: web.Request) -> web.Response:
    return web.json_response({"ok": True, "service": "tyranny-registration"})


async def start_registration_api(bot: Any, db: Any, data_dir: Path) -> web.AppRunner | None:
    if os.getenv("TYRANNY_ENABLE_WEB", "1").strip().casefold() in {"0", "false", "no"}:
        return None
    app = web.Application(middlewares=[cors_middleware], client_max_size=7 * 1024 * 1024)
    app["bot"], app["db"], app["data_dir"] = bot, db, data_dir
    app.router.add_get("/health", health)
    app.router.add_get("/api/registration/{token}", registration_info)
    app.router.add_post("/api/registration/{token}", registration_submit)
    app.router.add_options("/api/registration/{token}", lambda _: web.Response(status=204))
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, os.getenv("HOST", "0.0.0.0"), int(os.getenv("PORT", "8080")))
    await site.start()
    return runner
