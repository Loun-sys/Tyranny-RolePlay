"""One-time, reversible user-requested NPC reset and training-map preparation."""
import json
import logging
from collections import deque

SCHEMA='''CREATE TABLE IF NOT EXISTS master_updates(key TEXT PRIMARY KEY,created_at TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS master_map_backups(id INTEGER PRIMARY KEY AUTOINCREMENT,map_id INTEGER NOT NULL,payload TEXT NOT NULL,reason TEXT NOT NULL,created_at TEXT DEFAULT CURRENT_TIMESTAMP);'''

def training_positions(spec):
    width,height=spec['width'],spec['height'];blocked={(p['x'],p['y']) for p in spec.get('blocked',[])}
    free={(x,y) for x in range(width) for y in range(height)}-blocked
    components=[]
    while free:
        start=next(iter(free));q=deque([start]);group={start};free.remove(start)
        while q:
            x,y=q.popleft()
            for dx,dy in ((1,0),(-1,0),(0,1),(0,-1)):
                p=(x+dx,y+dy)
                if p in free:free.remove(p);group.add(p);q.append(p)
        components.append(group)
    group=max(components,key=len,default=set())
    if len(group)<3:raise ValueError('На тренировочной карте нужно минимум три связанные свободные клетки.')
    center=(height-1)/2
    player=max(group,key=lambda p:(p[0],-abs(p[1]-center),-p[1]))
    remaining=group-{player}
    left=sorted(remaining,key=lambda p:(p[0],abs(p[1]-(center-2)),p[1]))[0]
    right=sorted(remaining-{left},key=lambda p:(p[0],abs(p[1]-(center+2)),p[1]))[0]
    return {name:{'x':p[0],'y':p[1]} for name,p in [('player',player),('dummy_left',left),('dummy_right',right)]}

async def apply_master_update(db,guild):
    if not guild:return
    async with db.connect() as c:
        await c.executescript(SCHEMA)
        await c.execute('BEGIN IMMEDIATE')
        key=f'npc-reset-20261003:{guild}'
        if not await c.execute_fetchall('SELECT 1 FROM master_updates WHERE key=?',(key,)):
            rows=await c.execute_fetchall('SELECT * FROM npc_tokens WHERE guild_id=?',(guild,))
            for row in rows:
                await c.execute('INSERT INTO npc_archive(guild_id,owner_id,original_id,payload,reason) VALUES(?,?,?,?,?)',
                    (guild,row['owner_id'],row['id'],json.dumps(dict(row),ensure_ascii=False),'Сброс НПС по запросу мастера 03.10.2026'))
            maps=await c.execute_fetchall('SELECT * FROM battle_maps WHERE guild_id=?',(guild,))
            for m in maps:
                spec=json.loads(m['spec'])
                if any(p.get('kind','npc')=='npc' for p in spec.get('tokens',spec.get('npcs',[]))):
                    await c.execute('INSERT INTO master_map_backups(map_id,payload,reason) VALUES(?,?,?)',(m['id'],json.dumps(dict(m),ensure_ascii=False),'До сброса НПС'))
                    spec['tokens']=[p for p in spec.get('tokens',spec.get('npcs',[])) if p.get('kind')=='player']
                    spec.pop('npcs',None)
                    await c.execute('UPDATE battle_maps SET spec=? WHERE id=?',(json.dumps(spec,ensure_ascii=False),m['id']))
            await c.execute('DELETE FROM npc_tokens WHERE guild_id=?',(guild,))
            await c.execute('INSERT INTO master_updates(key) VALUES(?)',(key,))
            logging.info('NPC reset: archived %s tokens in configured guild; backup retained.',len(rows))
        map_key=f'training-field-20261003:{guild}'
        if not await c.execute_fetchall('SELECT 1 FROM master_updates WHERE key=?',(map_key,)):
            maps=await c.execute_fetchall("SELECT * FROM battle_maps WHERE guild_id=? ORDER BY updated_at DESC,id DESC",(guild,))
            selected=next((m for m in maps if m['name'].strip().casefold()=='тренировочное поле'),None)
            if selected:
                spec=json.loads(selected['spec']);positions=training_positions(spec)
                await c.execute('INSERT INTO master_map_backups(map_id,payload,reason) VALUES(?,?,?)',(selected['id'],json.dumps(dict(selected),ensure_ascii=False),'До подготовки тренировки'))
                spec['tokens']=[];spec.pop('npcs',None);spec['spawns']=positions;spec['training']=True
                await c.execute('UPDATE battle_maps SET spec=?,published=1 WHERE id=?',(json.dumps(spec,ensure_ascii=False),selected['id']))
                await c.execute('INSERT INTO master_updates(key) VALUES(?)',(map_key,))
                logging.info('Training map prepared: %s id=%s positions=%s',selected['name'],selected['id'],positions)
            else:logging.warning('Training map not found by exact name: Тренировочное Поле')
        await c.commit()
