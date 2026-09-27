"""Генератор русской карточки Вершителя Судеб в стиле бронзового пергамента."""

from __future__ import annotations

import io
import urllib.request
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont

from constants import ATTRIBUTES

WIDTH, HEIGHT = 1400, 900
INK = (42, 29, 21)
MUTED = (91, 66, 47)
BRONZE = (139, 79, 42)
CRIMSON = (111, 27, 25)


def _font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    candidates = [
        Path("C:/Windows/Fonts") / ("georgiab.ttf" if bold else "georgia.ttf"),
        Path("C:/Windows/Fonts") / ("timesbd.ttf" if bold else "times.ttf"),
        Path("/usr/share/fonts/truetype/dejavu") / ("DejaVuSerif-Bold.ttf" if bold else "DejaVuSerif.ttf"),
    ]
    for path in candidates:
        if path.exists():
            return ImageFont.truetype(str(path), size)
    return ImageFont.load_default()


def _paper() -> Image.Image:
    image = Image.new("RGB", (WIDTH, HEIGHT), (210, 179, 127))
    pixels = image.load()
    for y in range(HEIGHT):
        for x in range(WIDTH):
            grain = ((x * 17 + y * 31 + (x * y) % 19) % 15) - 7
            edge = int(34 * max(abs(x - WIDTH / 2) / (WIDTH / 2), abs(y - HEIGHT / 2) / (HEIGHT / 2)) ** 2)
            pixels[x, y] = (max(0, 210 + grain - edge), max(0, 179 + grain - edge), max(0, 127 + grain - edge))
    return image.filter(ImageFilter.GaussianBlur(0.35))


def _load_portrait(url: str) -> Image.Image | None:
    if not url:
        return None
    try:
        if url.startswith("local://"):
            return Image.open(Path(url.removeprefix("local://"))).convert("RGB")
        request = urllib.request.Request(url, headers={"User-Agent": "TyrannyDiscordArchive/1.0"})
        with urllib.request.urlopen(request, timeout=8) as response:
            return Image.open(io.BytesIO(response.read())).convert("RGB")
    except Exception:
        return None


def _fit_crop(image: Image.Image, box: tuple[int, int]) -> Image.Image:
    target_ratio = box[0] / box[1]
    ratio = image.width / image.height
    if ratio > target_ratio:
        crop_w = int(image.height * target_ratio)
        left = (image.width - crop_w) // 2
        image = image.crop((left, 0, left + crop_w, image.height))
    else:
        crop_h = int(image.width / target_ratio)
        top = (image.height - crop_h) // 2
        image = image.crop((0, top, image.width, top + crop_h))
    return image.resize(box, Image.Resampling.LANCZOS)


def render_character_card(character: dict[str, Any], inventory: list[dict[str, Any]] | None = None) -> io.BytesIO:
    image = _paper()
    draw = ImageDraw.Draw(image)
    inventory = inventory or []
    draw.rounded_rectangle((25, 25, WIDTH - 25, HEIGHT - 25), 18, outline=INK, width=5)
    draw.rounded_rectangle((38, 38, WIDTH - 38, HEIGHT - 38), 14, outline=BRONZE, width=2)
    draw.line((55, 145, WIDTH - 55, 145), fill=CRIMSON, width=4)
    draw.text((65, 50), "ВЕРШИТЕЛЬ СУДЕБ", font=_font(25, True), fill=CRIMSON)
    draw.text((65, 86), character["name"].upper(), font=_font(43, True), fill=INK)
    draw.text((1030, 60), f'{character["level"]} УРОВЕНЬ', font=_font(27, True), fill=BRONZE)
    draw.text((1030, 102), f'ОПЫТ: {character["experience"]}', font=_font(20), fill=MUTED)

    portrait_box = (955, 175, 1325, 580)
    draw.rectangle(portrait_box, fill=(69, 55, 42), outline=INK, width=5)
    portrait = _load_portrait(character.get("portrait_url", ""))
    if portrait:
        portrait = ImageEnhance.Color(_fit_crop(portrait, (360, 395))).enhance(0.75)
        image.paste(portrait, (960, 180))
    else:
        draw.multiline_text((1023, 355), "ПОРТРЕТ\nНЕ ЗАДАН", font=_font(24, True), fill=(190, 163, 116), align="center")

    draw.text((65, 175), "ПРОИСХОЖДЕНИЕ", font=_font(18, True), fill=CRIMSON)
    draw.text((65, 202), character["background"], font=_font(25, True), fill=INK)
    draw.text((65, 252), "СПЕЦИАЛИЗАЦИИ", font=_font(18, True), fill=CRIMSON)
    draw.text((65, 280), f'{character["specialization_1"]}  •  {character["specialization_2"]}', font=_font(24, True), fill=INK)

    draw.text((65, 335), f'ЗДОРОВЬЕ  {character["health"]} / {character["health_max"]}', font=_font(23, True), fill=CRIMSON)
    left, top, width = 65, 373, 780
    draw.rounded_rectangle((left, top, left + width, top + 24), 8, outline=INK, width=2)
    ratio = character["health"] / max(1, character["health_max"])
    draw.rounded_rectangle((left + 3, top + 3, left + 3 + int((width - 6) * ratio), top + 21), 5, fill=CRIMSON)

    draw.text((65, 430), "ХАРАКТЕРИСТИКИ", font=_font(22, True), fill=CRIMSON)
    attrs = character.get("attributes", {})
    for index, name in enumerate(ATTRIBUTES):
        column, row = index % 3, index // 3
        x, y = 65 + column * 278, 475 + row * 75
        draw.ellipse((x, y, x + 54, y + 54), fill=(191, 151, 87), outline=INK, width=3)
        value = str(attrs.get(name, 10))
        bounds = draw.textbbox((0, 0), value, font=_font(21, True))
        draw.text((x + 27 - (bounds[2] - bounds[0]) / 2, y + 13), value, font=_font(21, True), fill=INK)
        draw.text((x + 66, y + 14), name, font=_font(20, True), fill=INK)

    equipped = [item for item in inventory if item.get("equipped_slot")]
    draw.text((65, 650), "ЭКИПИРОВКА", font=_font(22, True), fill=CRIMSON)
    if equipped:
        for index, item in enumerate(equipped[:7]):
            draw.text((65, 690 + index * 27), f'{item["equipped_slot"]}: {item["name"]}'[:64], font=_font(18), fill=INK)
    else:
        draw.text((65, 690), "Нет экипированных предметов", font=_font(18), fill=MUTED)

    top_skills = sorted(character.get("skills", {}).items(), key=lambda pair: pair[1]["value"], reverse=True)[:6]
    draw.text((955, 620), "ЛУЧШИЕ НАВЫКИ", font=_font(20, True), fill=CRIMSON)
    for index, (name, data) in enumerate(top_skills):
        draw.text((955, 658 + index * 32), f'{name[:25]}: {data["value"]}', font=_font(16, index < 2), fill=INK)
    draw.text((1040, 848), "АРХИВ КАЙРОС", font=_font(17, True), fill=CRIMSON)
    output = io.BytesIO()
    image.save(output, format="PNG", optimize=True)
    output.seek(0)
    return output


render_card = render_character_card
