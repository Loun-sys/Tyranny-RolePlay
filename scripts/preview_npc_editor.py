"""Loopback-only UI fixture; never connects to live player data."""
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from aiohttp import web
from npc_store import ability_page,template_page,validate_npc,templates

async def roster(request):return web.json_response({'characters':[]})
async def npcs(request):
    return web.json_response({'ok':True,'npcs':[{'id':1,'published':False,'spec':validate_npc({**templates()[0],'name':'Тестовый страж'})}],
        'archive':[],'templates':template_page(),'abilities':ability_page(request.query.get('abilityQ',''),request.query.get('abilityKind',''),int(request.query.get('abilityOffset',0)))})
app=web.Application()
app.router.add_get('/api/admin/preview',roster)
app.router.add_get('/api/admin/preview/npcs',npcs)
app.router.add_get('/api/archive',lambda request:web.json_response({'characters':[]}))
app.router.add_static('/',ROOT/'web',show_index=False)
if __name__=='__main__':web.run_app(app,host='127.0.0.1',port=8770)
