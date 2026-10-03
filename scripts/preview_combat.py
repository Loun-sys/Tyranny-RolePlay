"""Isolated local combat QA: never opens the production database or Discord."""
import asyncio
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from aiohttp import web
from database import Database
import registration_api as api


async def main():
    with tempfile.TemporaryDirectory(prefix="tyranny-combat-qa-") as folder:
        db = Database(Path(folder) / "qa.sqlite3")
        await db.initialize()
        cid = await db.create_character(1, 2, "Испытатель", "Заклинатель", "Заклинания молний", "Заклинания льда")
        await db.create_spell(cid, "Огненный взрыв", "Огонь", "Направленная сила", [], [], 0)
        await db.normalize_spell_slots(cid, fill_empty=True)
        token = await db.create_portal_token(1, 2)
        app = web.Application(middlewares=[api.cors_middleware])
        app["db"], app["data_dir"] = db, Path(folder)
        app["extended_talents"] = {"backgrounds": {}, "factions": []}
        app["training_sessions"], app["training_locks"] = {}, {}
        app.router.add_get("/api/archive", api.archive_list)
        app.router.add_get("/api/portal/{token}", api.portal_info)
        app.router.add_get("/api/portal/{token}/training", api.training_info)
        for path, handler in [("start", api.training_start), ("action", api.training_action), ("reset", api.training_reset)]:
            app.router.add_post("/api/portal/{token}/training/" + path, handler)
        app.router.add_post("/api/portal/{token}/combat-quickbar", api.portal_combat_quickbar)
        async def index(_):
            # API middleware formats raised HTTP exceptions as JSON; retain Location.
            return web.Response(status=302, headers={"Location": f"/archive.html?api=http://127.0.0.1:8766#token={token}"})
        app.router.add_get("/", index)
        app.router.add_static("/", ROOT / "web")
        runner = web.AppRunner(app)
        await runner.setup()
        await web.TCPSite(runner, "127.0.0.1", 8766).start()
        print("Local isolated QA: http://127.0.0.1:8766/", flush=True)
        try:
            await asyncio.Event().wait()
        finally:
            await runner.cleanup()


if __name__ == "__main__":
    asyncio.run(main())
