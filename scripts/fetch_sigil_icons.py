"""Загрузить канонические иконки сигилов через MediaWiki API Tyranny Wiki."""

from __future__ import annotations

import json
import sys
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sigil_data import SIGIL_LIBRARY  # noqa: E402


API = "https://tyranny.fandom.com/api.php"
ROOT = Path(__file__).resolve().parents[1]
HEADERS = {"User-Agent": "Tyranny-RolePlay/1.0 (community game tool)"}


def fetch(url: str) -> bytes:
    return urllib.request.urlopen(urllib.request.Request(url, headers=HEADERS), timeout=30).read()


def main() -> int:
    unique = {entry["wiki_image"]: entry["image_url"] for entry in SIGIL_LIBRARY}
    resolved: dict[str, str] = {}
    filenames = list(unique)
    for start in range(0, len(filenames), 25):
        batch = filenames[start:start + 25]
        params = urllib.parse.urlencode({
            "action": "query", "format": "json", "formatversion": 2,
            "prop": "imageinfo", "iiprop": "url", "iiurlwidth": 128,
            "titles": "|".join(f"File:{name}" for name in batch),
        })
        payload = json.loads(fetch(f"{API}?{params}"))
        for page in payload.get("query", {}).get("pages", []):
            if page.get("missing") or not page.get("imageinfo"):
                continue
            title = str(page["title"]).removeprefix("File:")
            info = page["imageinfo"][0]
            resolved[title.casefold()] = info.get("thumburl") or info["url"]
    target = ROOT / "web" / "assets" / "sigil-icons"
    target.mkdir(parents=True, exist_ok=True)
    missing = []
    for filename, relative in unique.items():
        url = resolved.get(filename.casefold())
        if not url:
            missing.append(filename)
            continue
        path = ROOT / "web" / relative
        path.write_bytes(fetch(url))
        print(f"{filename} -> {path.name}")
    if missing:
        print("Не найдены:", ", ".join(missing), file=sys.stderr)
    print(f"Загружено {len(unique) - len(missing)} из {len(unique)} уникальных иконок.")
    return 1 if missing else 0


if __name__ == "__main__":
    raise SystemExit(main())
