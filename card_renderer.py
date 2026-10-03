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


def render_inventory_card(character, inventory, derived, limits):
    """Discord inventory snapshot, using the same calculated values as the site."""
    from PIL import ImageOps
    image = Image.new('RGB', (1100, 1090), '#080708')
    draw = ImageDraw.Draw(image)
    gold, muted = '#dfc790', '#a99874'
    root = Path(__file__).parent / 'web'

    def icon(path, xy, size):
        # Icons are shipped game assets, not remote images or user-supplied paths.
        asset = (root / path).resolve()
        if root.resolve() not in asset.parents or not asset.is_file():
            return
        with Image.open(asset) as original:
            pic = ImageOps.contain(original.convert('RGBA'), (size, size))
            image.paste(pic, (xy[0] + (size-pic.width)//2, xy[1] + (size-pic.height)//2), pic)

    draw.rectangle((12, 12, 1087, 1077), outline='#6a512a', width=2)
    draw.text((30, 25), str(character['name'])[:40], font=_font(30, True), fill=gold)
    draw.text((850, 32), f"Уровень {character['level']}", font=_font(20), fill=gold)
    draw.rectangle((22, 80, 285, 1060), outline='#584126')
    draw.rectangle((306, 80, 1074, 1060), outline='#584126')
    draw.text((38, 98), 'Показатели', font=_font(24, True), fill=gold)
    attack = derived['attack']
    rows = [('health', 'Здоровье', f"{character['health']}/{derived.get('healthMax',character['health_max'])}"),
            ('accuracy', 'Точность', attack['accuracy']), ('critical', 'Крит. шанс', f"{attack['criticalChance']}%"),
            ('recovery', 'Восстановление', f"{attack['recovery']:g} раунд."),
            ('damage', 'Урон', f"{attack['damageMin']}–{attack['damageMax']}")]
    def stat_rows(rows, y):
        for filename, label, value in rows:
            icon(f'assets/stat-icons/{filename}.png', (35, y), 25)
            draw.text((69, y+3), label, font=_font(14), fill=gold)
            draw.text((270, y+30), str(value), font=_font(19, True), fill=gold, anchor='ra')
            y += 66
        return y
    y = stat_rows(rows, 143)
    draw.line((38, y, 270, y), fill='#584126')
    draw.text((38, y+15), 'Защиты', font=_font(24, True), fill=gold)
    y = stat_rows([(f, n, derived['defenses'].get(n, 0)) for f, n in
                  [('endurance','Выносливость'),('will','Воля'),('magic','Магия'),('parry','Парирование'),('dodge','Уклонение')]], y+58)
    draw.text((38, y+5), 'Броня', font=_font(24, True), fill=gold)
    stat_rows([('armor','Поглощение',derived.get('armor',0)),('deflection','Отражение',f"{derived.get('deflection',0)}%")], y+44)
    portrait = _load_portrait(character.get('portrait_url',''))
    if portrait:
        pic = ImageOps.contain(portrait, (500, 450))
        image.paste(pic, (690-pic.width//2, 280+(450-pic.height)//2))
    else:
        draw.text((690, 460), character['name'][:22], font=_font(25), fill=muted, anchor='mm')
    by_slot = {i['equipped_slot']: i for i in inventory if i.get('equipped_slot')}

    def slot(key, label, x, y, label_side='right'):
        draw.rectangle((x, y, x+66, y+66), fill='#161416', outline='#993040', width=2)
        item = by_slot.get(key)
        if item:
            quality_color = {'Хорошее':'#60a164','Превосходное':'#679de0','Выдающееся':'#a659e8','Безупречное':'#f1a847'}.get(item.get('quality'),'#9b9582')
            draw.rectangle((x+5,y+5,x+61,y+61), outline=quality_color, width=2)
            icon(item.get('image_url',''), (x+8,y+8), 50)
        else:
            draw.polygon([(x+33,y+19),(x+47,y+33),(x+33,y+47),(x+19,y+33)], outline='#625a4c', width=2)
        if label_side=='right': draw.text((x+80,y+24), label, font=_font(17,True), fill=gold)
        elif label_side=='left': draw.text((x-14,y+24), label, font=_font(17,True), fill=gold, anchor='ra')
        elif label: draw.text((x+33,y+74), label, font=_font(16,True), fill=gold, anchor='ma')

    for n,(left,right,ll,rl) in enumerate([('Голова','Руки','Голова','Руки'),('Торс','Ноги','Торс','Ноги'),('Аксессуар 1','Аксессуар 2','Аксессуар','Аксессуар')]):
        slot(left,ll,325,102+n*84)
        slot(right,rl,989,102+n*84,'left')
    roman = ['I','II','III','IV'][derived.get('activeWeaponSet',1)-1]
    slot(f'Оружие {roman} — правая рука','П. рука',390,685,'bottom')
    slot(f'Оружие {roman} — левая рука','Л. рука',923,685,'bottom')
    draw.text((690,790), 'Быстрый доступ', font=_font(22,True), fill=gold, anchor='mm')
    quick_count = int(limits.get('quickSlots',4))
    for n in range(quick_count):
        columns = min(6,quick_count)
        slot(f'Быстрый предмет {n+1}','',690-columns*38+(n%columns)*76,818+(n//columns)*72,'bottom')
    draw.text((330,900), 'Комплекты оружия: '+ ' / '.join(['I','II','III','IV'][:limits.get('weaponSets',2)]), font=_font(16), fill=muted)
    output = io.BytesIO()
    image.save(output, format='PNG')
    output.seek(0)
    return output
