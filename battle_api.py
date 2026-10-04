"""Authenticated shared-battle endpoints. Never trust guild, owner or actor from players."""
from aiohttp import web
from battle_store import BattleStore


def battle_portrait(request,value):
    from registration_api import _portrait_url
    if value.startswith('assets/npc-portraits/'):return value
    return _portrait_url(request,value)


async def player_battles(request):
    from registration_api import _portrait_url
    cid=await request.app['db'].portal_character_id(request.match_info['token'])
    if not cid:raise web.HTTPGone(reason='Личная ссылка истекла или была заменена.')
    character=await request.app['db'].get_character_by_id(cid)
    store=BattleStore(request.app['db']);guild=character['guild_id']
    if 'battle_id' not in request.match_info:
        return web.json_response({'ok':True,'battles':await store.list(guild,cid=cid)})
    ident=int(request.match_info['battle_id'])
    try:
        if request.method=='POST':
            p=await request.json()
            if p.get('operation')=='join':row=await store.join(ident,guild,cid)
            else:row=await store.action(ident,guild,cid=cid,payload=p)
        else:
            row=await store.get(ident,guild,cid=cid)
            if request.query.get('afterRevision')==str(row['revision']):return web.json_response({'ok':True,'unchanged':True})
        result=await store.view(row,cid)
        # No enemy mechanics, master notes or archive IDs in a player's payload.
        result.pop('tokens',None);result.pop('conditions',None)
        result['map']={k:v for k,v in result['map'].items() if k!='tokens'}
        if result.get('training'):
            safe_fields={'id','name','health','healthMax','armor','x','y'}
            result['training']['dummy']={k:v for k,v in result['training']['dummy'].items() if k in safe_fields}
            result['training']['targets']=[{k:v for k,v in t.items() if k in safe_fields} for t in result['training']['targets']]
            for token in result['training']['grid']['tokens']:
                token['portraitUrl']=battle_portrait(request,token.get('portraitUrl',''))
            result['training']['character']['portraitUrl']=battle_portrait(request,result['training']['character'].get('portraitUrl',''))
        return web.json_response({'ok':True,'battle':result,'message':'Бой обновлён.'})
    except (ValueError,TypeError,KeyError) as e:raise web.HTTPConflict(reason=str(e)) from e


async def admin_battles(request):
    from registration_api import _admin_owner,_portrait_url
    from campaign_store import CampaignStore
    from npc_store import NPCStore
    guild,owner=await _admin_owner(request);store=BattleStore(request.app['db'])
    try:
        if 'battle_id' not in request.match_info:
            if request.method=='POST':
                p=await request.json();row=await store.create(guild,owner,int(p['mapId']),p['participants'])
                return web.json_response({'ok':True,'battle':await store.view(row,master=True)})
            return web.json_response({'ok':True,'battles':await store.list(guild,owner),
                'maps':await CampaignStore(request.app['db']).maps(guild,owner),
                'npcs':await NPCStore(request.app['db']).list(guild,owner)})
        ident=int(request.match_info['battle_id'])
        if request.method=='DELETE':
            if request.query.get('mode')=='play':raise ValueError('Удаление боя доступно только в администрировании.')
            p=await request.json()
            await store.delete(ident,guild,owner,p.get('confirmName'),p.get('revision'))
            return web.json_response({'ok':True,'message':'Бой удалён. Персонажи, карта и архив НПС сохранены.'})
        if request.method=='POST':
            p=await request.json()
            if request.query.get('mode')=='play':p['mode']='play'
            row=await store.action(ident,guild,owner=owner,payload=p)
        else:
            row=await store.get(ident,guild,owner)
            if request.query.get('afterRevision')==str(row['revision']):return web.json_response({'ok':True,'unchanged':True})
        actor=request.query.get('actorId','')
        result=await store.view(row,actor_id=actor,master=True,play=request.query.get('mode')=='play')
        for token in result.get('tokens',[]):token['portrait']=battle_portrait(request,token.get('portrait',''))
        if result.get('training'):
            for token in result['training']['grid']['tokens']:token['portraitUrl']=battle_portrait(request,token.get('portraitUrl',''))
            result['training']['character']['portraitUrl']=battle_portrait(request,result['training']['character'].get('portraitUrl',''))
        return web.json_response({'ok':True,'battle':result,'message':'Бой обновлён.'})
    except (ValueError,TypeError,KeyError) as e:raise web.HTTPConflict(reason=str(e)) from e


def register_battle_routes(app):
    app.router.add_get('/api/portal/{token}/battles',player_battles)
    app.router.add_get('/api/portal/{token}/battles/{battle_id}',player_battles)
    app.router.add_post('/api/portal/{token}/battles/{battle_id}',player_battles)
    app.router.add_get('/api/admin/{token}/battles',admin_battles)
    app.router.add_post('/api/admin/{token}/battles',admin_battles)
    app.router.add_get('/api/admin/{token}/battles/{battle_id}',admin_battles)
    app.router.add_post('/api/admin/{token}/battles/{battle_id}',admin_battles)
    app.router.add_delete('/api/admin/{token}/battles/{battle_id}',admin_battles)
