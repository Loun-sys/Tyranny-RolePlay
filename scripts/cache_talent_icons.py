"""Скачать канонические иконки талантов Tyranny Wiki для GitHub Pages."""

from __future__ import annotations

import asyncio
import io
import json
import re
import sys
import tempfile
from pathlib import Path
from urllib.parse import quote, unquote, urlsplit
from urllib.request import Request, urlopen

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from extended_talent_data import load_extended_talents  # noqa: E402
from talent_data import TALENTS  # noqa: E402


STAT_ICON_FILES = {
    "health.png": "Potion_of_minor_endurance_L.png",
    "accuracy.png": "SPELLMOD_accuracy_i.png",
    "critical.png": "Psv_agility_stealth_accuracy.png",
    "recovery.png": "SPELLMOD_recovery_i.png",
    "damage.png": "Abl_power_cleave.png",
    "endurance.png": "Psv_defense_heavy_guard_i.png",
    "will.png": "Psv_sirin_defensive_cry.png",
    "magic.png": "Psv_magic_ward_master.png",
    "parry.png": "Psv_defense_blade_wall_i.png",
    "dodge.png": "Psv_range_evasive.png",
    "armor.png": "Shape-Armor.png",
    "deflection.png": "Secondary_deflecting.png",
}


def filename_from_url(url: str) -> str:
    parts = unquote(urlsplit(url).path).split("/")
    if "revision" in parts:
        filename = Path(parts[parts.index("revision") - 1]).name
    else:
        filename = Path(parts[-1]).name
    return re.sub(r"[\s_]+", "_", filename)


async def main() -> None:
    target = ROOT / "web" / "assets" / "talent-icons"
    target.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as temp:
        extended = await load_extended_talents(Path(temp))
    talents = [*TALENTS, *extended["factions"]]
    for rows in extended["backgrounds"].values():
        talents.extend(rows)
    by_name = {filename_from_url(item["icon_url"]): item["icon_url"] for item in talents if item.get("icon_url")}
    semaphore = asyncio.Semaphore(10)
    headers = {"User-Agent": "Mozilla/5.0 Tyranny-RolePlay icon cache"}

    def download(path: Path, url: str) -> None:
        with urlopen(Request(url, headers=headers), timeout=40) as response:
            image = Image.open(io.BytesIO(response.read()))
            image.save(path, format="PNG", optimize=True)

    async def fetch(filename: str, url: str) -> None:
        path = target / filename
        if path.is_file() and path.stat().st_size > 100:
            return
        async with semaphore:
            await asyncio.to_thread(download, path, url)

    results = await asyncio.gather(*(fetch(name, url) for name, url in by_name.items()), return_exceptions=True)
    failures = [(name, result) for name, result in zip(by_name, results) if isinstance(result, Exception)]
    print(f"Сохранено: {len(by_name) - len(failures)} / {len(by_name)}")
    for name, error in failures:
        print(f"ОШИБКА {name}: {error}")
    if failures:
        raise SystemExit(1)

    stat_target = ROOT / "web" / "assets" / "stat-icons"
    stat_target.mkdir(parents=True, exist_ok=True)

    def fetch_stat_icon(alias: str, filename: str) -> None:
        api = (
            "https://tyranny.fandom.com/api.php?action=query&prop=imageinfo&iiprop=url&format=json&titles="
            + quote("File:" + filename)
        )
        with urlopen(Request(api, headers=headers), timeout=40) as response:
            payload = json.loads(response.read().decode("utf-8"))
        page = next(iter(payload["query"]["pages"].values()))
        url = page["imageinfo"][0]["url"]
        download(stat_target / alias, url)

    stat_results = await asyncio.gather(
        *(asyncio.to_thread(fetch_stat_icon, alias, filename) for alias, filename in STAT_ICON_FILES.items()),
        return_exceptions=True,
    )
    stat_failures = [(alias, result) for alias, result in zip(STAT_ICON_FILES, stat_results) if isinstance(result, Exception)]
    print(f"Иконки показателей: {len(STAT_ICON_FILES) - len(stat_failures)} / {len(STAT_ICON_FILES)}")
    for alias, error in stat_failures:
        print(f"ОШИБКА {alias}: {error}")
    if stat_failures:
        raise SystemExit(1)


if __name__ == "__main__":
    asyncio.run(main())
