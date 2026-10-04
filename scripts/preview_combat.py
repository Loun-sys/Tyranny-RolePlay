"""Isolated local combat QA: never opens the production database or Discord."""
import asyncio
import sys
import shutil
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from aiohttp import web
from database import Database
import registration_api as api


async def main():
    port = int(sys.argv[1]) if len(sys.argv)>1 else 8766
    with tempfile.TemporaryDirectory(prefix="tyranny-combat-qa-") as folder:
        db = Database(Path(folder) / "qa.sqlite3")
        await db.initialize()
        background='Скованный Ремеслом' if 'craft' in sys.argv[2:] else 'Заклинатель'
        cid = await db.create_character(1, 2, "Испытатель", background, "Заклинания молний", "Заклинания льда")
        portraits = Path(folder) / "portraits"
        portraits.mkdir()
        shutil.copyfile(ROOT / "web/assets/npc-portraits/verse_sm.png", portraits / "qa.png")
        await db.update_character_text(cid, "portrait_url", "local://qa.png")
        await db.create_character(1,3,'Получатель','Книгочей','Меч и щит','Дротик')
        await db.create_spell(cid, "Огненный взрыв", "Огонь", "Направленная сила", [], [], 0)
        await db.normalize_spell_slots(cid, fill_empty=True)
        for name in ['Тяжелый бронзовый шлем с гребнем','Зелье героев','Слабое зелье исцеления','Алый яд']:
            await db.admin_give_item(cid,name,2)
        helmet=next(i for i in await db.inventory(cid) if i['name']=='Тяжелый бронзовый шлем с гребнем')
        await db.equip(cid,helmet['inventory_id'],'Голова')
        if background=='Скованный Ремеслом':
            from crafting import CraftingStore,quality_info,upgrade_recipe
            craft=CraftingStore(db)
            async with db.connect() as connection:
                items=await craft._items(connection)
            for kind in ['armor','weapon']:
                sample=next(i for i in items.values() if (quality_info(i) or {}).get('kind')==kind and upgrade_recipe(i))
                await db.admin_give_item(cid,sample['name'])
                for ingredient in upgrade_recipe(sample)['ingredients']:
                    if ingredient['consumed']:
                        await db.admin_give_item(cid,items[ingredient['prefab']]['name'],ingredient['quantity']*3)
            from campaign_store import CampaignStore
            await CampaignStore(db).set_wallet(cid,25000)
        token = await db.create_portal_token(1, 2)
        admin_token=await db.create_admin_token(1,99)
        app = web.Application(middlewares=[api.cors_middleware],client_max_size=7*1024*1024)
        app["db"], app["data_dir"] = db, Path(folder)
        app["extended_talents"] = {"backgrounds": {}, "factions": []}
        app["training_sessions"], app["training_locks"] = {}, {}
        app.router.add_get("/api/archive", api.archive_list)
        app.router.add_get("/media/portraits/{name}", api.portrait_media)
        app.router.add_get("/api/portal/{token}", api.portal_info)
        app.router.add_get("/api/portal/{token}/training", api.training_info)
        app.router.add_get("/api/portal/{token}/shop", api.portal_shop)
        for path, handler in [("start", api.training_start), ("action", api.training_action), ("reset", api.training_reset)]:
            app.router.add_post("/api/portal/{token}/training/" + path, handler)
        app.router.add_post("/api/portal/{token}/combat-quickbar", api.portal_combat_quickbar)
        app.router.add_post('/api/portal/{token}/item/use',api.portal_use_item)
        app.router.add_post('/api/portal/{token}/possessions',api.portal_possessions)
        app.router.add_get('/api/portal/{token}/crafting',api.portal_crafting)
        app.router.add_post('/api/portal/{token}/crafting',api.portal_crafting)
        app.router.add_post('/api/portal/{token}/portrait',api.portal_portrait)
        app.router.add_post('/api/portal/{token}/equipment',api.portal_equip)
        app.router.add_get('/api/admin/{token}',api.admin_home)
        app.router.add_get('/api/admin/{token}/character/{character_id}',api.admin_character)
        app.router.add_post('/api/admin/{token}/character/{character_id}',api.admin_mutation)
        async def admin_index(_):
            return web.Response(status=302,headers={'Location':f'/admin.html?api=http://127.0.0.1:{port}#token={admin_token}'})
        app.router.add_get('/qa-admin',admin_index)
        async def index(_):
            # API middleware formats raised HTTP exceptions as JSON; retain Location.
            return web.Response(status=302, headers={"Location": f"/archive.html?api=http://127.0.0.1:{port}#token={token}"})
        app.router.add_get("/", index)
        app.router.add_static("/", ROOT / "web")
        runner = web.AppRunner(app)
        await runner.setup()
        await web.TCPSite(runner, "127.0.0.1", port).start()
        print(f"Local isolated QA: http://127.0.0.1:{port}/", flush=True)
        try:
            await asyncio.Event().wait()
        finally:
            await runner.cleanup()


if __name__ == "__main__":
    asyncio.run(main())
