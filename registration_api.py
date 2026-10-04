"""HTTP-мост между статическим конструктором GitHub Pages и Discord-ботом."""

from __future__ import annotations

import base64
import asyncio
import io
import hashlib
import os
import re
from pathlib import Path
from typing import Any

from aiohttp import web
from PIL import Image

from constants import (
    ABILITY_DETAILS, ACCENT_SIGILS, ATTRIBUTE_DETAILS, ATTRIBUTES, BACKGROUND_BONUSES,
    BACKGROUND_DESCRIPTIONS, BACKGROUNDS, SKILLS,
    BACKGROUND_TALENT_SOURCES,
    CORE_SIGILS, ENHANCEMENT_SIGILS, EQUIPMENT_SLOTS, EXPRESSION_SIGILS, REPUTATION_FACTIONS,
    SKILL_ATTRIBUTES, SPECIALIZATIONS, SPECIALIZATION_ABILITIES,
    SPECIALIZATION_ABILITY_CHOICES, SPECIALIZATION_BONUSES, SPECIALIZATION_DESCRIPTIONS,
)
from mechanics_data import MECHANICS
from talent_data import TALENT_BY_NAME, TALENTS
from extended_talent_data import load_extended_talents
from training_combat import TrainingSession
from sigil_data import SPELL_NAMES, SIGIL_LIBRARY, SIGILS_BY_KEY, sigil_key_from_scroll_url, validate_formula
from official_localization import official_spell_details
from campaign_store import CampaignStore


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
    total=ATTRIBUTE_TOTAL+(4 if background=='Зверолюд' else 0)
    maximum=total-8*(len(ATTRIBUTES)-1) if background=='Зверолюд' else 18
    if any(value < 8 or value > maximum for value in attributes.values()) or sum(attributes.values()) != total:
        return None, f"Характеристики должны быть от 8 до {maximum}, общая сумма — {total}."
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
    if not isinstance(data_url, str) or not data_url.startswith(('data:image/png;base64,', 'data:image/jpeg;base64,', 'data:image/webp;base64,')):
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
        if image.format not in {'PNG','JPEG','WEBP'} or image.width*image.height>20_000_000:
            raise ValueError('Изображение слишком большое или имеет неподдерживаемый формат.')
        image.verify()
        image = Image.open(io.BytesIO(raw)).convert("RGB")
    except Exception as error:
        raise ValueError("Файл не является корректным изображением.") from error
    image.thumbnail((1600, 1600), Image.Resampling.LANCZOS)
    portraits = data_dir / "portraits"
    portraits.mkdir(parents=True, exist_ok=True)
    path = portraits / f"{guild_id}_{user_id}_{hashlib.sha256(raw).hexdigest()[:16]}.webp"
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
        allocate_start_bonus=False,
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


def _property_number(properties: dict[str, Any], *names: str) -> tuple[float, bool]:
    aliases = {name.casefold() for name in names}
    for key, value in properties.items():
        if str(key).strip().casefold() not in aliases:
            continue
        text = str(value).replace(",", ".")
        match = re.search(r"[-+]?\d+(?:\.\d+)?", text)
        if match:
            return float(match.group()), "%" in text
    return 0.0, False


def _apply_property(base: float, items: list[dict[str, Any]], *names: str) -> float:
    from item_effects import equip_modifiers
    flat = percent = 0.0
    multiplier=1.0
    aliases={name.casefold() for name in names}
    for item in items:
        modifiers=equip_modifiers(item);original=modifiers['flat']
        keys=[key for key in original if key.casefold() in aliases]
        source=item.get('properties') or {}
        if isinstance(source,str):source=__import__('json').loads(source)
        value, is_percent = (sum(original[key] for key in keys),False) if keys else _property_number(source, *names)
        if is_percent:
            percent += value
        else:
            flat += value
        percent+=sum(v for k,v in modifiers['percent'].items() if k.casefold() in aliases)
        for k,v in modifiers['multiply'].items():
            if k.casefold() in aliases:multiplier*=v
    return (base * (1 + percent / 100) + flat)*multiplier


def _derived(character: dict[str, Any], inventory: list[dict[str, Any]]) -> dict[str, Any]:
    from ability_rules import passive_equipment
    inventory=inventory+passive_equipment(character.get('talents',[]),inventory,character.get('active_weapon_set',1))
    active_set = max(1, min(4, int(character.get("active_weapon_set", 1))))
    roman = ("I", "II", "III", "IV")[active_set - 1]
    equipped = [item for item in inventory if item.get("equipped_slot") and item.get('equipped_slot')!='Мастерская']
    active_items = [
        item for item in equipped
        if not str(item.get("equipped_slot", "")).startswith("Быстрый предмет")
        and (
            not str(item.get("equipped_slot", "")).startswith("Оружие")
            or str(item.get("equipped_slot", "")).startswith(f"Оружие {roman} ")
        )
    ]
    attrs = dict(character["attributes"])
    for name in attrs:
        attrs[name] = round(_apply_property(attrs[name], active_items, name))
    from talent_runtime import attribute_skill_delta
    skills={name:round(_apply_property(row['value']+attribute_skill_delta(name,character['attributes'],attrs),active_items,name))
            for name,row in character['skills'].items()}
    quickness = attrs.get("Быстрота", 10)
    resolve = attrs.get("Стойкость", 10)
    base_defenses = {
        "Выносливость": resolve * 1.5 + attrs.get("Сила", 10) * .5,
        "Воля": resolve * 1.5 + attrs.get("Живучесть", 10) * .5,
        "Магия": resolve * 1.5 + attrs.get("Смекалка", 10) * .5,
        "Парирование": character["skills"].get("Парирование", {}).get("value", 0)+attribute_skill_delta('Парирование',character['attributes'],attrs),
        "Уклонение": character["skills"].get("Уклонение", {}).get("value", 0)+attribute_skill_delta('Уклонение',character['attributes'],attrs),
    }
    defenses = {
        name: round(_apply_property(value, active_items, name, f"Защита {name}", f"{name} defense"))
        for name, value in base_defenses.items()
    }
    from ability_rules import shield_mastery_bonuses
    shield_bonuses=shield_mastery_bonuses(character.get('talents',[]),active_items)
    for name in defenses:
        defenses[name]=round(defenses[name]+shield_bonuses.get(name,0))
    weapons = [item for item in active_items if str(item.get("equipped_slot", "")).startswith("Оружие")]
    primary = next((item for item in weapons if "правая рука" in item.get("equipped_slot", "")), None)
    skill_by_category = {
        "Одноручное оружие": "Одноручное оружие", "Двуручное оружие": "Двуручное оружие",
        "Парное оружие": "Парное оружие", "Луки": "Луки", "Метательное оружие": "Дротики",
        "Посохи": "Волшебный посох", "Щиты": "Одноручное оружие",
    }
    attack_skill = skill_by_category.get((primary or {}).get("category"), "Безоружный бой")
    accuracy = round(_apply_property(skills.get(attack_skill,0), active_items, "Точность", "Accuracy"))
    might_multiplier = max(.1, 1 + (attrs.get("Сила", 10) - 10) * .03)
    damage_min = round(sum(int(item.get("damage_min") or 0) for item in weapons) * might_multiplier)
    damage_max = round(sum(int(item.get("damage_max") or 0) for item in weapons) * might_multiplier)
    if not damage_max:
        from item_effects import unarmed_damage
        fists=next((unarmed_damage(i) for i in active_items if unarmed_damage(i)[1]>0),(2,4))
        damage_min, damage_max = max(1, round(fists[0] * might_multiplier)), max(2, round(fists[1] * might_multiplier))
    melee=(primary or {}).get('category') not in {'Луки','Метательное оружие','Посохи'}
    damage_min=round(_apply_property(damage_min,active_items,'Урон','Урон ближнего боя') if melee else _apply_property(damage_min,active_items,'Урон'))
    damage_max=round(_apply_property(damage_max,active_items,'Урон','Урон ближнего боя') if melee else _apply_property(damage_max,active_items,'Урон'))
    from ability_rules import weapon_mastery
    mastery_multiplier,split_chances=weapon_mastery(character.get('talents',[]),active_items,active_set)
    damage_min=round(damage_min*mastery_multiplier)
    damage_max=round(damage_max*mastery_multiplier)
    armor = sum(float(item.get("armor") or 0) for item in active_items)
    armor = round(_apply_property(armor, active_items, "Броня", "Armor"),4)
    from item_effects import armor_by_type,DAMAGE_TYPES
    typed_armor={name:round(sum(armor_by_type(item)[name] for item in active_items),4) for name in DAMAGE_TYPES.values()}
    deflection = max(0, attrs.get("Искусность", 10) - 10)
    deflection = round(_apply_property(deflection, active_items, "Отражение", "Deflection"))
    deflection=round(deflection+shield_bonuses.get('Отражение',0))
    recovery = sum(float(item.get("recovery") or 0) for item in active_items)
    recovery = _apply_property(recovery, active_items, "Восстановление", "Recovery")
    from talent_runtime import effects as talent_effects, equipment_attack
    runtime=talent_effects(character.get('talents',[]),active_items,active_set)
    if 2012 in runtime:defenses['Парирование']=defenses['Уклонение']
    attack_values=equipment_attack({"accuracy":accuracy,"damageMin":damage_min,"damageMax":damage_max,
        "splitChances":split_chances,"recovery":round(recovery,4),
        "criticalChance":max(1,round(_apply_property(attrs.get('Искусность',10)-9,active_items,'Критический шанс'))),
        "penetration":_apply_property(0,active_items,'Пробивание брони'),"skill":attack_skill,
        "range":{'Луки':12,'Дротики':6,'Волшебный посох':10}.get(attack_skill,1)},runtime,attack_skill,len(weapons))
    return {
        "defenses": defenses,
        "talentRuntime":runtime,
        "incomingConversions":{'critToHit':_apply_property(0,active_items,'Отражение критических ударов'),
            'hitToGraze':_apply_property(0,active_items,'Отражение попаданий'),
            'grazeToMiss':_apply_property(0,active_items,'Отражение промахов')},
        "artifactAbilities": __import__('artifact_rules').equipped_artifacts(active_items),
        "effectiveAttributes": attrs,
        "effectiveSkills":skills,"armorByType":typed_armor,
        "movementMultiplier":_apply_property(1,active_items,'Передвижение'),
        "spellPowerMultiplier":_apply_property(1,active_items,'Сила заклинаний'),
        "incomingDamageMultiplier":_apply_property(1,active_items,'Получаемый урон'),
        "healingMultiplier":_apply_property(1,active_items,'Получаемое лечение'),
        "attack":attack_values,
        "armor": armor, "deflection": deflection, "activeWeaponSet": active_set,
        "cooldownMultiplier": round(max(.1,_apply_property(1 - (quickness - 10) * .03,active_items,'Перезарядка')),3),
        "cooldownPercent": round((1 - max(.1,_apply_property(1 - (quickness - 10) * .03,active_items,'Перезарядка'))) * 100),
        "equipmentRecovery": round(recovery, 2),
        "healthMax": max(1, round(_apply_property(character.get('health_max',20) + attrs.get('Живучесть',10)-character['attributes'].get('Живучесть',10),active_items,'Максимум здоровья'))),
        "equipmentBonuses": [{"item":item['name'],"bonuses":__import__('item_effects').equip_bonuses(item)} for item in active_items],
    }


def _clean_inventory(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result = []
    for row in rows:
        item = dict(row)
        try:
            item["properties"] = item['properties'] if isinstance(item.get('properties'),dict) else __import__("json").loads(item.get("properties") or "{}")
        except (TypeError, ValueError):
            item["properties"] = {}
        from item_texts import normalize_item_text
        item = normalize_item_text(item)
        from merchant_rules import reliable_icon
        item['image_url'],item['iconFallback']=reliable_icon(item)
        result.append(item)
    return result


async def _dashboard(request: web.Request, character_id: int) -> dict[str, Any]:
    db = request.app["db"]
    character = await db.get_character_by_id(character_id)
    if not character:
        raise web.HTTPNotFound(reason="Персонаж не найден.")
    await db.normalize_spell_slots(character_id)
    inventory = _clean_inventory(await db.inventory(character_id))
    character["portrait_url"] = _portrait_url(request, character.get("portrait_url", ""))
    from consumable_store import states as item_states
    from consumables import virtual_equipment
    consumed_states=await item_states(db,character_id)
    character.pop("guild_id", None)
    character.pop("user_id", None)
    background_talents = request.app["extended_talents"]["backgrounds"].get(character["background"], [])
    reputations = {row["faction"]: row for row in await db.reputations(character_id)}
    known_sigils = await db.known_sigils(character_id)
    sigil_library = [{**entry, "known": entry["key"] in known_sigils} for entry in SIGIL_LIBRARY]
    sigil_scrolls = []
    for item in inventory:
        sigil_key = sigil_key_from_scroll_url(str(item.get("source_url") or ""))
        sigil = SIGILS_BY_KEY.get(sigil_key or "")
        if sigil:
            sigil_scrolls.append({
                "inventoryId": int(item["inventory_id"]), "quantity": int(item["quantity"]),
                "itemName": item["name"], "known": sigil_key in known_sigils, "sigil": sigil,
            })
    return {
        "character": character,
        "wallet": await CampaignStore(db).wallet(character_id),
        "inventory": inventory,
        "capacity": await db.inventory_capacity(character_id),
        "recipients": await __import__('player_possessions').recipients(db,character_id),
        "spells": await db.spells(character_id),
        "combatQuickbar": await db.combat_quickbar(character_id),
        "spellNames": {f"{core}|{expression}": name for (core, expression), name in SPELL_NAMES.items()},
        "spellDetails": {
            f"{core}|{expression}": details
            for (core, expression), details in official_spell_details().items()
        },
        "derived": _derived(character, inventory+virtual_equipment(consumed_states,1)),
        "itemEffects":consumed_states,
        "equipmentSlots": list(EQUIPMENT_SLOTS),
        "equipmentLimits": await db.equipment_limits(character_id),
        "talentLibrary": [__import__('ability_rules').normalize_talent(t) for t in [*TALENTS, *background_talents]],
        "reputations": reputations,
        "factionTalents": request.app["extended_talents"]["factions"],
        "sigils": {"library": sigil_library, "knownKeys": sorted(known_sigils), "scrolls": sigil_scrolls},
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


async def portal_portrait(request: web.Request) -> web.Response:
    cid, payload = await _portal_payload(request)
    if not isinstance(payload, dict) or not payload.get('portrait'):
        raise web.HTTPBadRequest(reason='Выберите изображение PNG, JPEG или WEBP.')
    db = request.app['db']
    character = await db.get_character_by_id(cid)
    if not character:
        raise web.HTTPGone(reason='Персонаж больше не существует.')
    try:
        portrait = await asyncio.to_thread(_save_portrait, payload['portrait'], request.app['data_dir'], character['guild_id'], character['user_id'])
    except ValueError as error:
        raise web.HTTPBadRequest(reason=str(error)) from error
    await db.update_character_text(cid, 'portrait_url', portrait)
    return web.json_response({'ok': True, 'message': 'Портрет обновлён.', **await _dashboard(request,cid)})


async def portal_attribute(request: web.Request) -> web.Response:
    cid, payload = await _portal_payload(request)
    ok, message = await request.app["db"].spend_attribute_point(cid, str(payload.get("name", "")))
    if not ok:
        raise web.HTTPConflict(reason=message)
    return web.json_response({"ok": True, "message": message, **await _dashboard(request, cid)})


async def portal_possessions(request):
    cid,payload=await _portal_payload(request)
    from player_possessions import operate
    try:message=await operate(request.app['db'],cid,payload)
    except (TypeError,ValueError) as error:raise web.HTTPConflict(reason=str(error)) from error
    return web.json_response({'ok':True,'message':message,**await _dashboard(request,cid)})


async def portal_talent(request: web.Request) -> web.Response:
    cid, payload = await _portal_payload(request)
    character = await request.app["db"].get_character_by_id(cid)
    library = [*TALENTS, *request.app["extended_talents"]["backgrounds"].get(character["background"], [])]
    from ability_rules import normalize_talent
    requested = str(payload.get('name','')).casefold()
    talent = next((item for item in library if requested in {item['name'].casefold(),str(item.get('legacyName','')).casefold(),normalize_talent(item)['name'].casefold()}), None)
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
    character = await request.app["db"].get_character_by_id(cid)
    effective=_derived(character,_clean_inventory(await request.app['db'].inventory(cid)))
    try:
        formula = validate_formula(
            core, expression, accents, enhancements,
            await request.app["db"].known_sigils(cid),effective['effectiveSkills'].get('Знания',0),
        )
    except ValueError as error:
        raise web.HTTPConflict(reason=str(error)) from error
    name = str(payload.get("name", "")).strip() or formula["default_name"]
    if not 2 <= len(name) <= 80:
        raise web.HTTPBadRequest(reason="Введите название заклинания.")
    try:
        spell_id = int(payload.get("spellId", 0) or 0)
    except (TypeError, ValueError) as error:
        raise web.HTTPBadRequest(reason="Некорректный номер формулы.") from error
    if spell_id:
        try:
            updated = await request.app["db"].update_spell(
                cid, spell_id, name, formula["core"], formula["expression"], formula["accents"],
                formula["enhancements"], formula["difficulty"],
            )
        except ValueError as error:
            raise web.HTTPConflict(reason=str(error)) from error
        if not updated:
            raise web.HTTPNotFound(reason="Формула не найдена.")
    else:
        await request.app["db"].create_spell(
            cid, name, formula["core"], formula["expression"], formula["accents"],
            formula["enhancements"], formula["difficulty"],
        )
    spells = await request.app["db"].spells(cid)
    created = next((spell for spell in spells if spell["name"] == name), None)
    # Новая формула сразу занимает свободную ячейку, как в игре. При правке
    # существующей формулы её прежнее состояние (гримуар/резерв) сохраняется.
    if not spell_id and created and created.get("equipped_slot") is None:
        await request.app["db"].set_spell_equipped(cid, int(created["id"]), True)
    verb = "изменено" if spell_id else "создано"
    return web.json_response({"ok": True, "message": f"Заклинание «{name}» {verb}.", **await _dashboard(request, cid)})


async def portal_spell_equip(request: web.Request) -> web.Response:
    cid, payload = await _portal_payload(request)
    try:
        spell_id = int(payload.get("spellId", 0))
    except (TypeError, ValueError) as error:
        raise web.HTTPBadRequest(reason="Некорректный номер заклинания.") from error
    ok, message = await request.app["db"].set_spell_equipped(cid, spell_id, bool(payload.get("equipped", True)))
    if not ok:
        raise web.HTTPConflict(reason=message)
    return web.json_response({"ok": True, "message": message, **await _dashboard(request, cid)})


async def portal_spell_delete(request: web.Request) -> web.Response:
    cid, payload = await _portal_payload(request)
    try:
        spell_id = int(payload.get("spellId", 0))
    except (TypeError, ValueError) as error:
        raise web.HTTPBadRequest(reason="Некорректный номер заклинания.") from error
    if not await request.app["db"].delete_spell(cid, spell_id):
        raise web.HTTPNotFound(reason="Заклинание не найдено.")
    return web.json_response({"ok": True, "message": "Формула удалена из гримуара.", **await _dashboard(request, cid)})


async def portal_learn_sigil(request: web.Request) -> web.Response:
    cid, payload = await _portal_payload(request)
    try:
        inventory_id = int(payload.get("inventoryId", 0))
    except (TypeError, ValueError) as error:
        raise web.HTTPBadRequest(reason="Некорректный номер свитка.") from error
    ok, message = await request.app["db"].learn_sigil_from_scroll(cid, inventory_id)
    if not ok:
        raise web.HTTPConflict(reason=message)
    return web.json_response({"ok": True, "message": message, **await _dashboard(request, cid)})


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


async def portal_weapon_set(request: web.Request) -> web.Response:
    cid, payload = await _portal_payload(request)
    try:
        number = int(payload.get("number", 0))
    except (TypeError, ValueError) as error:
        raise web.HTTPBadRequest(reason="Некорректный номер комплекта.") from error
    ok, message = await request.app["db"].set_active_weapon_set(cid, number)
    if not ok:
        raise web.HTTPConflict(reason=message)
    return web.json_response({"ok": True, "message": message, **await _dashboard(request, cid)})


async def portal_combat_quickbar(request: web.Request) -> web.Response:
    cid, payload = await _portal_payload(request)
    if 'bindings' in payload:
        bindings = payload['bindings']
        if not isinstance(bindings, list) or len(bindings) != 9 or not all(isinstance(row, dict) for row in bindings):
            raise web.HTTPBadRequest(reason='Некорректный список быстрых ячеек.')
        character = await request.app['db'].get_character_by_id(cid)
        inventory=_clean_inventory(await request.app['db'].inventory(cid))
        artifacts={a['name'] for a in _derived(character,inventory)['artifactAbilities'] if a['supported']}
        from consumables import profile
        usable={str(i['inventory_id']) for i in inventory if profile(i)}
        owned = {row['name'] for row in character.get('talents', [])}
        spells = {row['name'] for row in await request.app['db'].spells(cid) if row.get('equipped_slot') is not None}
        cleaned = []
        for row in bindings:
            kind, name = str(row.get('kind', '')), str(row.get('name', ''))
            valid = (not kind and not name) or (kind == 'attack' and name == 'Обычная атака')
            valid = valid or (kind == 'ability' and name in owned) or (kind == 'spell' and name in spells)
            valid = valid or (kind == 'artifact' and name in artifacts)
            valid = valid or (kind == 'item' and name in usable)
            valid = valid or (kind == 'disengage' and name == 'Осторожный отход')
            valid = valid or (kind == 'tactic' and name in {'Защита','Спринт','Подготовить атаку'})
            if not valid:
                raise web.HTTPConflict(reason='Это действие сейчас недоступно персонажу.')
            try:
                cleaned.append({'slot': int(row.get('slot', 0)), 'kind': kind, 'name': name})
            except (TypeError, ValueError) as error:
                raise web.HTTPBadRequest(reason='Некорректный номер ячейки.') from error
        try:
            await request.app['db'].replace_combat_quickbar(cid, cleaned)
        except ValueError as error:
            raise web.HTTPBadRequest(reason=str(error)) from error
        return web.json_response({'ok': True, 'message': 'Быстрые ячейки сохранены.', **await _dashboard(request, cid)})
    try:
        slot = int(payload.get("slot", 0))
    except (TypeError, ValueError) as error:
        raise web.HTTPBadRequest(reason="Некорректная ячейка быстрого доступа.") from error
    kind, name = str(payload.get("kind", "")).strip(), str(payload.get("name", "")).strip()
    if kind or name:
        if kind not in {"attack", "ability", "spell", "disengage", "artifact", "item", "tactic"} or not name:
            raise web.HTTPBadRequest(reason="Неизвестное боевое действие.")
        character = await request.app["db"].get_character_by_id(cid)
        owned = {row["name"] for row in character.get("talents", [])}
        spells = {row["name"] for row in await request.app["db"].spells(cid) if row.get("equipped_slot") is not None}
        valid = kind == "attack" and name == "Обычная атака"
        valid = valid or kind == "ability" and name in owned
        valid = valid or kind == "spell" and name in spells
        valid = valid or kind == "disengage" and name == "Осторожный отход"
        valid = valid or kind == 'tactic' and name in {'Защита','Спринт','Подготовить атаку'}
        inventory=_clean_inventory(await request.app['db'].inventory(cid))
        from consumables import profile
        valid = valid or kind=='item' and any(str(i['inventory_id'])==name and profile(i) for i in inventory)
        valid = valid or kind == 'artifact' and any(a['name']==name and a['supported'] for a in _derived(character,inventory)['artifactAbilities'])
        if not valid:
            raise web.HTTPConflict(reason="Это действие сейчас недоступно персонажу.")
    try:
        await request.app["db"].set_combat_quickbar(cid, slot, kind, name)
    except ValueError as error:
        raise web.HTTPBadRequest(reason=str(error)) from error
    return web.json_response({"ok": True, "message": "Быстрая ячейка сохранена.", **await _dashboard(request, cid)})


async def _admin_owner(request: web.Request) -> tuple[int, int]:
    owner = await request.app["db"].admin_token_owner(request.match_info["token"])
    if not owner:
        raise web.HTTPGone(reason="Администраторская ссылка истекла или была заменена.")
    return owner


async def _admin_character(request: web.Request) -> tuple[int, int, int]:
    guild_id, admin_user_id = await _admin_owner(request)
    try:
        character_id = int(request.match_info["character_id"])
    except (TypeError, ValueError) as error:
        raise web.HTTPBadRequest(reason="Некорректный номер персонажа.") from error
    if not await request.app["db"].character_belongs_to_guild(character_id, guild_id):
        raise web.HTTPNotFound(reason="Персонаж этого сервера не найден.")
    return guild_id, admin_user_id, character_id


async def _admin_roster(request: web.Request, guild_id: int) -> list[dict[str, Any]]:
    rows = await request.app['db'].admin_characters(guild_id)
    for row in rows:
        row['portrait_url'] = _portrait_url(request, row.get('portrait_url', ''))
    return rows


async def admin_home(request: web.Request) -> web.Response:
    guild_id, admin_user_id = await _admin_owner(request)
    return web.json_response({
        "ok": True, "adminUserId": str(admin_user_id),
        "characters": await _admin_roster(request, guild_id),
    })


def master_faction_talents(request):
    return [{**t, 'tree': 'Фракционные · ' + t['faction']} for t in request.app['extended_talents']['factions']]


async def admin_character(request: web.Request) -> web.Response:
    guild_id, _, character_id = await _admin_character(request)
    original = await request.app["db"].get_character_by_id(character_id)
    payload = await _dashboard(request, character_id)
    payload['masterFactionTalents'] = master_faction_talents(request)
    payload["character"]["user_id"] = str(original["user_id"])
    payload["adminConfig"] = {
        "backgrounds": list(BACKGROUNDS), "specializations": list(SPECIALIZATIONS),
        "attributes": list(ATTRIBUTES), "skills": list(SKILLS),
        "factions": list(REPUTATION_FACTIONS), "guildId": str(guild_id),
    }
    return web.json_response({"ok": True, **payload})


async def admin_catalog(request: web.Request) -> web.Response:
    await _admin_owner(request)
    query = str(request.query.get("q", ""))[:100]
    category = str(request.query.get("category", ""))[:100]
    from catalog_browser import browse
    try:
        result=await browse(request.app['db'],query,category,str(request.query.get('quality',''))[:100],
            max(0,int(request.query.get('offset',0))),str(request.query.get('sort','name')),
            max(0,int(request.query.get('minPrice',0))),int(request.query.get('maxPrice',2000000000)))
    except (ValueError,TypeError) as error:raise web.HTTPBadRequest(reason='Некорректные фильтры каталога.') from error
    result['items']=_clean_inventory(result['items'])
    return web.json_response({'ok':True,**result})


async def admin_mutation(request: web.Request) -> web.Response:
    guild_id, admin_user_id, cid = await _admin_character(request)
    try:
        payload = await request.json()
    except Exception as error:
        raise web.HTTPBadRequest(reason="Некорректные данные.") from error
    if not isinstance(payload, dict):
        raise web.HTTPBadRequest(reason="Ожидается объект с данными.")
    action = str(payload.get("action", ""))
    db = request.app["db"]
    message = "Изменения сохранены."
    if action == "character_delete":
        original = await db.get_character_by_id(cid)
        if not original:
            raise web.HTTPNotFound(reason="Персонаж не найден.")
        if payload.get('confirmName') != original['name']:
            raise web.HTTPBadRequest(reason="Для удаления введите точное имя персонажа.")
        deleted = await db.delete_character(guild_id, original['user_id'], expected_character_id=cid, admin_user_id=admin_user_id)
        if not deleted:
            raise web.HTTPConflict(reason="Персонаж изменился. Обновите список и подтвердите удаление заново.")
        request.app.get('training_sessions', {}).pop(cid, None)
        request.app.get('training_locks', {}).pop(cid, None)
        return web.json_response({'ok': True, 'deletedId': cid, 'message': 'Персонаж удалён.',
                                  'characters': await _admin_roster(request, guild_id)})
    elif action == "character":
        values = dict(payload.get("values") or {})
        if "background" in values and values["background"] not in BACKGROUNDS:
            raise web.HTTPBadRequest(reason="Неизвестная предыстория.")
        for field in ("specialization_1", "specialization_2"):
            if field in values and values[field] not in SPECIALIZATIONS:
                raise web.HTTPBadRequest(reason="Неизвестная специализация.")
        await db.admin_update_character(cid, values)
    elif action == "level_up":
        gained = await db.admin_level_up(cid, int(payload.get("amount", 1)))
        message = f"Получено уровней: {gained}. Начислены очки характеристик и талантов."
    elif action == "attribute":
        name = str(payload.get("name", ""))
        if name not in ATTRIBUTES:
            raise web.HTTPBadRequest(reason="Неизвестная характеристика.")
        await db.set_attribute(cid, name, int(payload.get("value", 10)))
    elif action == "skill":
        name = str(payload.get("name", ""))
        if name not in SKILLS:
            raise web.HTTPBadRequest(reason="Неизвестный навык.")
        await db.admin_set_skill(cid, name, int(payload.get("value", 0)), int(payload.get("experience", 0)))
    elif action == "talent_add":
        character = await db.get_character_by_id(cid)
        library = [*TALENTS, *request.app["extended_talents"]["backgrounds"].get(character["background"], []), *master_faction_talents(request)]
        talent = next((row for row in library if row["name"] == str(payload.get("name", ""))), None)
        if not talent:
            raise web.HTTPBadRequest(reason="Талант не найден в доступных деревьях персонажа.")
        if not await db.add_talent(cid, talent):
            raise web.HTTPConflict(reason="Этот талант уже добавлен.")
        message = f"Добавлен талант «{talent['name']}»."
    elif action == "talent_remove":
        if not await db.remove_talent(cid, str(payload.get("name", ""))):
            raise web.HTTPNotFound(reason="Талант не найден.")
        message = "Талант удалён."
    elif action == "item_give":
        if not await db.admin_give_item(cid, str(payload.get("name", "")), int(payload.get("quantity", 1))):
            raise web.HTTPNotFound(reason="Предмет не найден в каталоге.")
        message = "Предмет выдан."
    elif action == "item_remove":
        if not await db.remove_item(cid, int(payload.get("inventoryId", 0)), int(payload.get("quantity", 1))):
            raise web.HTTPNotFound(reason="Предмет не найден.")
        message = "Предмет удалён из инвентаря."
    elif action == "equipment":
        inventory_id = int(payload.get("inventoryId", 0))
        if payload.get("unequip"):
            ok, message = await db.unequip(cid, inventory_id), "Предмет снят."
        else:
            ok, message = await db.equip(cid, inventory_id, str(payload.get("slot", "")))
        if not ok:
            raise web.HTTPConflict(reason=message)
    elif action == "reputation":
        faction = str(payload.get("faction", ""))
        if faction not in REPUTATION_FACTIONS:
            raise web.HTTPBadRequest(reason="Неизвестная фракция.")
        await db.admin_set_reputation(cid, faction, int(payload.get("favor", 0)), int(payload.get("wrath", 0)))
    elif action == "sigil":
        key = str(payload.get("key", ""))
        if key not in SIGILS_BY_KEY:
            raise web.HTTPBadRequest(reason="Неизвестный сигил.")
        await db.admin_set_sigil(cid, key, bool(payload.get("known")))
        message = "Знание сигила изменено."
    elif action == "spell_delete":
        if not await db.delete_spell(cid, int(payload.get("spellId", 0))):
            raise web.HTTPNotFound(reason="Заклинание не найдено.")
        message = "Заклинание удалено из гримуара."
    elif action == "spell_equipment":
        ok, message = await db.set_spell_equipped(
            cid, int(payload.get("spellId", 0)), bool(payload.get("equipped", True))
        )
        if not ok:
            raise web.HTTPConflict(reason=message)
    else:
        raise web.HTTPBadRequest(reason="Неизвестное административное действие.")
    safe_log = {key: value for key, value in payload.items() if key not in {"token"}}
    await db.record_admin_action(guild_id, admin_user_id, cid, action, safe_log)
    original = await db.get_character_by_id(cid)
    refreshed = await _dashboard(request, cid)
    refreshed['masterFactionTalents'] = master_faction_talents(request)
    refreshed["character"]["user_id"] = str(original["user_id"])
    refreshed["adminConfig"] = {
        "backgrounds": list(BACKGROUNDS), "specializations": list(SPECIALIZATIONS),
        "attributes": list(ATTRIBUTES), "skills": list(SKILLS),
        "factions": list(REPUTATION_FACTIONS), "guildId": str(guild_id),
    }
    return web.json_response({"ok": True, "message": message, **refreshed})


async def _training_character(request: web.Request, character_id: int, session: TrainingSession):
    db = request.app["db"]
    character = await db.get_character_by_id(character_id)
    if not character:
        raise web.HTTPNotFound(reason="Персонаж не найден.")
    character["active_weapon_set"] = session.active_weapon_set
    character["portrait_url"] = _portrait_url(request, character.get("portrait_url", ""))
    inventory = _clean_inventory(await db.inventory(character_id))
    spells = [spell for spell in await db.spells(character_id) if spell.get("equipped_slot") is not None]
    session.consumable_inventory=inventory
    from consumables import virtual_equipment
    if not session.initialized:
        from consumable_store import states as item_states
        session.conditions.setdefault('player',{}).update(await item_states(db,character_id))
    inventory=inventory+virtual_equipment(session.conditions.get('player',{}),session.round_number)
    from ability_rules import stance_equipment
    inventory=inventory+stance_equipment(session.active_stance)
    limits = await db.equipment_limits(character_id)
    return character, inventory, spells, limits


async def training_info(request: web.Request) -> web.Response:
    cid = await request.app["db"].portal_character_id(request.match_info["token"])
    if not cid:
        raise web.HTTPGone(reason="Личная ссылка истекла или была заменена новой.")
    session = request.app["training_sessions"].get(cid)
    if not session:
        return web.json_response({
            "ok": True, "training": {"active": False}, "maps": await _player_maps(request,cid),
            "message": "Тренировка ещё не начата. Опыт, здоровье и расходники здесь не изменяются.",
        })
    character, inventory, spells, limits = await _training_character(request, cid, session)
    derived = _derived(character, inventory)
    return web.json_response({
        "ok": True, "training": session.view(character, derived, spells, limits["weaponSets"]),
    })


async def training_start(request: web.Request) -> web.Response:
    cid, payload = await _portal_payload(request)
    character = await request.app["db"].get_character_by_id(cid)
    custom_map = None
    if not payload.get('mapId'):
        default_map=next((m for m in await _player_maps(request,cid) if m['name'].strip().casefold()=='тренировочное поле'),None)
        if default_map:payload['mapId']=default_map['id']
    if payload.get('mapId'):
        choices = await _player_maps(request,cid)
        selected = next((row for row in choices if row['id']==int(payload['mapId'])),None)
        if not selected: raise web.HTTPNotFound(reason='Карта недоступна.')
        from npc_store import NPCStore
        spec = selected['spec']
        placements = spec.get('tokens', spec.get('npcs', []))
        resolved = await NPCStore(request.app['db']).resolve_map(character['guild_id'],selected['owner_id'],
            [p for p in placements if p.get('kind','npc')=='npc'])
        for p in placements:
            if p.get('kind')!='player': continue
            actor = await request.app['db'].get_character_by_id(p['id'])
            if not actor or actor['guild_id']!=character['guild_id']:
                raise web.HTTPConflict(reason='Персонаж на карте больше недоступен.')
            resolved.append({'id':p['id'],'kind':'player','name':actor['name'],'portrait':actor.get('portrait_url',''),
                'healthMax':actor['health_max'],'armor':0,'defenses':{},'attributes':actor['attributes'],**p})
        if not spec.get('spawns') and not any(p.get('kind')=='player' and p['id']==cid for p in placements):
            raise web.HTTPConflict(reason='Мастер должен разместить токен вашего персонажа на этой карте.')
        custom_map = {**spec,'resolvedTokens':resolved}
    session = TrainingSession(
        character_id=cid, active_weapon_set=max(1, min(4, int(character.get("active_weapon_set", 1)))), custom_map=custom_map
    )
    if custom_map:session.map_owner_id=selected['owner_id']
    request.app["training_sessions"][cid] = session
    character, inventory, spells, limits = await _training_character(request, cid, session)
    derived = _derived(character, inventory)
    return web.json_response({
        "ok": True, "message": "Тренировочный бой начат. Награды отключены.",
        "training": session.view(character, derived, spells, limits["weaponSets"]),
    })


async def training_action(request: web.Request) -> web.Response:
    cid, payload = await _portal_payload(request)
    lock = request.app["training_locks"].setdefault(cid, asyncio.Lock())
    async with lock:
        session = request.app["training_sessions"].get(cid)
        if not session:
            raise web.HTTPConflict(reason="Сначала начните тренировку.")
        character, inventory, spells, limits = await _training_character(request, cid, session)
        derived = _derived(character, inventory)
        try:
            result = session.act(payload, character, derived, spells, limits["weaponSets"])
        except (TypeError, ValueError) as error:
            raise web.HTTPConflict(reason=str(error)) from error
        # Смена комплекта влияет на расчёты немедленно, но не меняет личное дело.
        character["active_weapon_set"] = session.active_weapon_set
        # Rebuild timed modifiers after applying/removing an effect in this action.
        character, inventory, spells, limits = await _training_character(request, cid, session)
        derived = _derived(character, inventory)
        return web.json_response({
            "ok": True, "message": result["line"],
            "training": session.view(character, derived, spells, limits["weaponSets"]),
        })


async def training_reset(request: web.Request) -> web.Response:
    cid, _ = await _portal_payload(request)
    request.app["training_sessions"].pop(cid, None)
    request.app["training_locks"].pop(cid, None)
    return web.json_response({"ok": True, "message": "Тренировка завершена без опыта и наград.", "training": {"active": False}})

async def admin_training(request: web.Request) -> web.Response:
    guild,owner,cid=await _admin_character(request)
    session=request.app['training_sessions'].get(cid)
    if not session:return web.json_response({'ok':True,'active':False})
    if getattr(session,'map_owner_id',owner)!=owner:raise web.HTTPForbidden(reason='Карта принадлежит другому мастеру.')
    async with request.app['training_locks'].setdefault(cid,asyncio.Lock()):
        actor,inventory,spells,limits=await _training_character(request,cid,session)
        message=''
        if request.method=='POST':
            payload=await request.json()
            try:
                base=_derived(actor,[i for i in inventory if i.get('equipped_slot')!='Эффект'])
                result=session.master_npc_ability(str(payload.get('actorId','')),str(payload.get('abilityKey','')),str(payload.get('targetId','')),actor,base)
                message=result['line']
            except (TypeError,ValueError) as error:raise web.HTTPConflict(reason=str(error)) from error
        from ability_rules import profile
        from npc_store import refresh_ability
        npcs=[{'id':key,'name':n['name'],'abilities':[{k:v for k,v in profile(refresh_ability(a)).items() if k in {'key','name','description','icon','details','supported','limitation'}} for a in n.get('abilities',[]) if not a.get('passive')]}
              for key,n in session.targets.items() if n.get('kind')=='npc']
        return web.json_response({'ok':True,'active':True,'message':message,'npcs':npcs,'training':session.view(actor,_derived(actor,inventory),spells,limits['weaponSets'])})


async def portrait_media(request: web.Request) -> web.StreamResponse:
    name = Path(request.match_info["name"]).name
    path = (request.app["data_dir"] / "portraits" / name).resolve()
    root = (request.app["data_dir"] / "portraits").resolve()
    if path.parent != root or not path.is_file():
        raise web.HTTPNotFound()
    return web.FileResponse(path)


async def health(_: web.Request) -> web.Response:
    return web.json_response({"ok": True, "service": "tyranny-registration", "combatRulesVersion":"20261004-4", "characterToolsVersion":"20261004-10"})


async def _player_maps(request,cid):
    character=await request.app['db'].get_character_by_id(cid)
    return await CampaignStore(request.app['db']).maps(character['guild_id'])


async def admin_npcs(request):
    from npc_store import NPCStore,template_page,templates,ability_page
    guild,owner=await _admin_owner(request);store=NPCStore(request.app['db']);ident=None
    if request.method=='POST':
        try:
            payload=await request.json()
            if not isinstance(payload,dict):raise ValueError('Нужен объект НПС.')
            if payload.get('action')=='delete':await store.archive(guild,owner,int(payload['id']))
            elif payload.get('action')=='restore':ident=await store.restore(guild,owner,int(payload['archiveId']))
            else:ident=await store.save(guild,owner,payload)
            await request.app['db'].record_admin_action(guild,owner,None,'npc',{'id':ident})
        except (ValueError,TypeError,KeyError) as error:raise web.HTTPBadRequest(reason=str(error)) from error
    try:
        offset=max(0,int(request.query.get('offset',0)))
        ability_offset=max(0,int(request.query.get('abilityOffset',0)))
    except ValueError:raise web.HTTPBadRequest(reason='Некорректная страница.')
    return web.json_response({'ok':True,'id':ident,'npcs':await store.list(guild,owner),'archive':await store.archived(guild,owner),
        'abilities':ability_page(str(request.query.get('abilityQ',''))[:150],str(request.query.get('abilityKind','')),ability_offset),
        'templates':template_page(str(request.query.get('q',''))[:150],str(request.query.get('category',''))[:100],offset),
        'tokenTemplates':[{'key':t['key'],'name':t['name'],'portrait':t['portrait'],'category':t['category']} for t in templates()]})


async def public_npcs(request):
    from npc_store import NPCStore
    return web.json_response({'ok':True,'npcs':await NPCStore(request.app['db']).list(public=True)})


async def admin_maps(request):
    guild,owner=await _admin_owner(request)
    store=CampaignStore(request.app['db'])
    ident=None
    if request.method=='POST':
        try:
            payload=await request.json()
            if payload.get('action')=='delete': await store.delete_map(guild,owner,int(payload['id']))
            else: ident=await store.save_map(guild,owner,payload)
        except (ValueError,TypeError,KeyError) as error: raise web.HTTPBadRequest(reason=str(error)) from error
    return web.json_response({'ok':True,'id':ident,'maps':await store.maps(guild,owner)})


async def admin_shop(request):
    guild,owner=await _admin_owner(request)
    store=CampaignStore(request.app['db'])
    if request.method=='POST':
        try: await store.edit_shop(guild,await request.json())
        except (ValueError,TypeError) as error: raise web.HTTPBadRequest(reason=str(error)) from error
    try:shop=await store.shop(guild,str(request.query.get('q',''))[:100],True,str(request.query.get('shopKey','custom')),str(request.query.get('category',''))[:100],str(request.query.get('quality',''))[:100])
    except ValueError as error:raise web.HTTPBadRequest(reason=str(error)) from error
    shop['items']=_clean_inventory(shop['items'])
    return web.json_response({'ok':True,**shop})


async def admin_wallet(request):
    guild,owner,cid=await _admin_character(request)
    try:
        payload=await request.json()
        total=int(payload.get('copper',0))+100*int(payload.get('bronze',0))+10000*int(payload.get('iron',0))
        if any(int(payload.get(k,0))<0 for k in ('copper','bronze','iron')): raise ValueError('Количество колец не может быть отрицательным.')
        await CampaignStore(request.app['db']).set_wallet(cid,total)
        await request.app['db'].record_admin_action(guild,owner,cid,'wallet',{'totalCopper':total})
    except (ValueError,TypeError) as error: raise web.HTTPBadRequest(reason=str(error)) from error
    return web.json_response({'ok':True,'wallet':await CampaignStore(request.app['db']).wallet(cid)})


async def portal_shop(request):
    cid=await request.app['db'].portal_character_id(request.match_info['token'])
    if not cid: raise web.HTTPGone(reason='Личная ссылка недоступна.')
    store=CampaignStore(request.app['db']);message=''
    if request.method=='POST':
        try: message=await store.trade(cid,await request.json())
        except (ValueError,TypeError) as error: raise web.HTTPConflict(reason=str(error)) from error
    character=await request.app['db'].get_character_by_id(cid)
    key=str(request.query.get('shopKey','consumables'))
    try:shop=await store.shop(character['guild_id'],str(request.query.get('q',''))[:100],False,key,str(request.query.get('category',''))[:100],str(request.query.get('quality',''))[:100])
    except ValueError as error:raise web.HTTPBadRequest(reason=str(error)) from error
    shop['items']=_clean_inventory(shop['items'])
    return web.json_response({'ok':True,**shop,'saleOffers':await store.sale_offers(cid,character['guild_id'],key),'wallet':await store.wallet(cid),'message':message})


async def portal_crafting(request):
    from crafting import CraftingStore
    cid=await request.app['db'].portal_character_id(request.match_info['token'])
    if not cid:raise web.HTTPGone(reason='Личная ссылка недоступна.')
    store=CraftingStore(request.app['db']);message=''
    try:
        if request.method=='POST':message=await store.act(cid,await request.json())
        result=await store.snapshot(cid)
    except (ValueError,TypeError) as error:raise web.HTTPConflict(reason=str(error)) from error
    def clean(item):return _clean_inventory([item])[0] if item else None
    for r in result['recipes']:
        r['outputItem']=clean(r['outputItem'])
        for i in r['ingredients']:i['item']=clean(i['item'])
    for r in result['upgrades']:
        r['item']=clean(r['item']);r['result']=clean(r['result'])
        for i in r['ingredients']:i['item']=clean(i['item'])
    for r in result['scrolls']:r['item']=clean(r['item'])
    result['materials']=[clean(i) for i in result['materials']]
    return web.json_response({'ok':True,**result,'wallet':await CampaignStore(request.app['db']).wallet(cid),'message':message})

async def portal_use_item(request):
    cid,payload=await _portal_payload(request)
    try:
        from consumable_store import use
        message=await use(request.app['db'],cid,int(payload.get('inventoryId',0)))
    except (ValueError,TypeError) as error:raise web.HTTPConflict(reason=str(error)) from error
    return web.json_response({'ok':True,'message':message,**await _dashboard(request,cid)})


async def start_registration_api(bot: Any, db: Any, data_dir: Path) -> web.AppRunner | None:
    if os.getenv("TYRANNY_ENABLE_WEB", "1").strip().casefold() in {"0", "false", "no"}:
        return None
    app = web.Application(middlewares=[cors_middleware], client_max_size=7 * 1024 * 1024)
    app["bot"], app["db"], app["data_dir"] = bot, db, data_dir
    app["training_sessions"] = {}
    app["training_locks"] = {}
    app["extended_talents"] = await load_extended_talents(data_dir)
    app.router.add_get("/health", health)
    app.router.add_get("/api/registration/{token}", registration_info)
    app.router.add_post("/api/registration/{token}", registration_submit)
    app.router.add_options("/api/registration/{token}", lambda _: web.Response(status=204))
    app.router.add_get("/api/archive", archive_list)
    app.router.add_get("/api/archive/{character_id}", archive_character)
    app.router.add_get("/api/portal/{token}", portal_info)
    app.router.add_post("/api/portal/{token}/attribute", portal_attribute)
    app.router.add_post('/api/portal/{token}/portrait', portal_portrait)
    app.router.add_post("/api/portal/{token}/talent", portal_talent)
    app.router.add_post("/api/portal/{token}/spell", portal_spell)
    app.router.add_post("/api/portal/{token}/spell/equip", portal_spell_equip)
    app.router.add_post("/api/portal/{token}/spell/delete", portal_spell_delete)
    app.router.add_post("/api/portal/{token}/sigil/learn", portal_learn_sigil)
    app.router.add_post("/api/portal/{token}/equipment", portal_equip)
    app.router.add_post('/api/portal/{token}/item/use',portal_use_item)
    app.router.add_post('/api/portal/{token}/possessions',portal_possessions)
    app.router.add_post("/api/portal/{token}/weapon-set", portal_weapon_set)
    app.router.add_get("/api/portal/{token}/training", training_info)
    app.router.add_get('/api/portal/{token}/crafting',portal_crafting)
    app.router.add_post('/api/portal/{token}/crafting',portal_crafting)
    app.router.add_post("/api/portal/{token}/training/start", training_start)
    app.router.add_post("/api/portal/{token}/training/action", training_action)
    app.router.add_post("/api/portal/{token}/training/reset", training_reset)
    app.router.add_post("/api/portal/{token}/combat-quickbar", portal_combat_quickbar)
    app.router.add_get("/api/admin/{token}", admin_home)
    app.router.add_get("/api/admin/{token}/catalog", admin_catalog)
    app.router.add_get('/api/admin/{token}/maps',admin_maps)
    app.router.add_get('/api/admin/{token}/npcs',admin_npcs)
    app.router.add_post('/api/admin/{token}/npcs',admin_npcs)
    app.router.add_get('/api/archive/npcs',public_npcs)
    app.router.add_post('/api/admin/{token}/maps',admin_maps)
    app.router.add_get('/api/admin/{token}/shop',admin_shop)
    app.router.add_post('/api/admin/{token}/shop',admin_shop)
    app.router.add_post('/api/admin/{token}/character/{character_id}/wallet',admin_wallet)
    app.router.add_get('/api/portal/{token}/shop',portal_shop)
    app.router.add_post('/api/portal/{token}/shop',portal_shop)
    app.router.add_get("/api/admin/{token}/character/{character_id}", admin_character)
    app.router.add_post("/api/admin/{token}/character/{character_id}", admin_mutation)
    app.router.add_get('/api/admin/{token}/character/{character_id}/training',admin_training)
    app.router.add_post('/api/admin/{token}/character/{character_id}/training',admin_training)
    app.router.add_options("/api/admin/{token}/character/{character_id}", lambda _: web.Response(status=204))
    app.router.add_get("/media/portraits/{name}", portrait_media)
    app.router.add_route("OPTIONS", "/api/{tail:.*}", lambda _: web.Response(status=204))
    # Secret portal/admin tokens must never be written to access logs.
    runner = web.AppRunner(app,access_log_format='%a %t %s %b')
    await runner.setup()
    site = web.TCPSite(runner, os.getenv("HOST", "0.0.0.0"), int(os.getenv("PORT", "8080")))
    await site.start()
    return runner
