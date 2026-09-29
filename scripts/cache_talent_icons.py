"""Скачать канонические иконки талантов Tyranny Wiki для GitHub Pages."""

from __future__ import annotations

import asyncio
import io
import re
import sys
import tempfile
from pathlib import Path
from urllib.parse import unquote, urlsplit
from urllib.request import Request, urlopen

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from extended_talent_data import load_extended_talents  # noqa: E402
from talent_data import TALENTS  # noqa: E402


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


if __name__ == "__main__":
    asyncio.run(main())
