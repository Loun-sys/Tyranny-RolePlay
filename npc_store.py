"""Guild/owner-scoped NPC tokens; immutable original game templates."""
import json
from functools import lru_cache
from pathlib import Path
from campaign_store import validate_map

SCHEMA='''CREATE TABLE IF NOT EXISTS npc_tokens (
id INTEGER PRIMARY KEY AUTOINCREMENT,guild_id INTEGER NOT NULL,owner_id INTEGER NOT NULL,
name TEXT NOT NULL,spec TEXT NOT NULL,published INTEGER NOT NULL DEFAULT 1,
created_at TEXT DEFAULT CURRENT_TIMESTAMP,updated_at TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS npc_archive(id INTEGER PRIMARY KEY AUTOINCREMENT,guild_id INTEGER NOT NULL,owner_id INTEGER NOT NULL,original_id INTEGER NOT NULL,payload TEXT NOT NULL,reason TEXT NOT NULL,archived_at TEXT DEFAULT CURRENT_TIMESTAMP);
'''

@lru_cache(maxsize=1)
def ability_library():
    from ability_rules import resolve,profile
    old=legacy_abilities()
    return [{**a,**profile(resolve(a))} if resolve(a) else a for a in old]

def refresh_ability(a):
    from ability_rules import resolve,profile
    original=resolve(a)
    if not original:return a
    new=profile(original)
    old=next((r for r in legacy_abilities() if r['key']==original['key']),{})
    for field in ('name','description','range','area','damageMin','damageMax','cooldown','targeting','passive'):
        if a.get('sourceVersion') or (field in a and a[field]!=old.get(field)):
            new[field]=a.get(field,new[field])
    return {**a,**new}

@lru_cache(maxsize=1)
def legacy_abilities():
    return json.loads((Path(__file__).parent/'catalog/npc_abilities.json').read_text(encoding='utf-8'))['abilities']

def ability_page(query='',kind='',offset=0):
    rows=[a for a in ability_library() if (not kind or a['passive']==(kind=='passive')) and
          query.casefold() in (a['name']+' '+a['description']+' '+' '.join(a.get('users',[]))).casefold()]
    return {'total':len(rows),'items':rows[offset:offset+30]}


@lru_cache(maxsize=1)
def templates():
    rows=json.loads((Path(__file__).parent/'catalog/game_npcs.json').read_text(encoding='utf-8'))
    return [{**row,'abilities':[refresh_ability(a) for a in row['abilities']],**portrait_library().get(row['key'],portrait_library()['default'])} for row in rows]


@lru_cache(maxsize=1)
def portrait_library():
    return json.loads((Path(__file__).parent/'catalog/npc_portraits.json').read_text(encoding='utf-8'))


def template_page(query='',category='',offset=0):
    rows=[row for row in templates() if (not category or row['category']==category) and
          (query.casefold() in row['name'].casefold() or query.casefold() in row['source']['prefab'].casefold())]
    return {'total':len(rows),'items':rows[offset:offset+50], 'categories':sorted({row['category'] for row in templates()})}


def validate_npc(spec):
    if not isinstance(spec,dict):raise ValueError('Нужны параметры НПС.')
    def bounded(key,default,minimum,maximum):
        value=int(spec.get(key,default))
        if not minimum<=value<=maximum:raise ValueError(f'Недопустимое значение: {key}.')
        return value
    name=str(spec.get('name','')).strip()[:100]
    if not name:raise ValueError('Укажите имя НПС.')
    portrait=str(spec.get('portrait',''))
    if portrait.startswith('assets/npc-portraits/'):
        filename=portrait.removeprefix('assets/npc-portraits/')
        if not __import__('re').fullmatch(r'[a-zA-Z0-9_-]+\.png',filename) or not (Path(__file__).parent/'web/assets/npc-portraits'/filename).is_file():
            raise ValueError('Неизвестный игровой портрет НПС.')
    else:validate_map({'image':portrait})
    color=str(spec.get('color','#a92339'))
    if not __import__('re').fullmatch(r'#[0-9a-fA-F]{6}',color):raise ValueError('Нужен шестизначный цвет токена.')
    attrs={str(k)[:60]:int(v) for k,v in dict(spec.get('attributes',{})).items()}
    skills={str(k)[:60]:int(v) for k,v in dict(spec.get('skills',{})).items()}
    if not isinstance(spec.get('defenses',{}),dict) or not isinstance(spec.get('attack',{}),dict) or not isinstance(spec.get('equipment',[]),list):
        raise ValueError('Проверьте структуру защит, атаки и экипировки.')
    defenses={k:int(spec.get('defenses',{}).get(k,30)) for k in ['Парирование','Уклонение','Выносливость','Воля','Магия']}
    if len(attrs)>6 or len(skills)>40 or any(not 0<=v<=10000 for v in attrs.values()) or any(not -1000<=v<=10000 for v in [*skills.values(),*defenses.values()]):
        raise ValueError('Характеристики: 0–10000; навыки и защиты: −1000–10000.')
    abilities=spec.get('abilities',[])
    if not isinstance(abilities,list) or len(abilities)>100:raise ValueError('Слишком много способностей.')
    normalized=[];source={a['key']:a for a in ability_library()}
    for a in abilities:
        if not isinstance(a,dict) or not a.get('name'):continue
        key=a.get('key') or a.get('prefab')
        original=source.get(key,{})
        row={**original,'name':str(a.get('name',''))[:150],'description':str(a.get('description',''))[:4000],
             'passive':bool(a.get('passive'))}
        for field,default,maximum in [('cooldown',0,1000),('range',1,40),('area',0,40),('damageMin',0,10000),('damageMax',0,10000)]:
            value=int(a.get(field,original.get(field,default)))
            if not 0<=value<=maximum:raise ValueError('Некорректные параметры способности: '+field)
            row[field]=value
        if row['damageMax']<row['damageMin']:raise ValueError('Максимальный урон способности меньше минимального.')
        row['targeting']=str(a.get('targeting',original.get('targeting','unit')))
        if row['targeting'] not in {'unit','self','area','cone','line','ally'}:raise ValueError('Неизвестная форма способности.')
        normalized.append(row)
    abilities=normalized
    attack=spec.get('attack',{})
    low,high=int(attack.get('damageMin',2)),int(attack.get('damageMax',4))
    if not 0<=low<=high<=10000:raise ValueError('Проверьте диапазон урона.')
    accuracy=int(attack.get('accuracy',20));distance=int(attack.get('range',1))
    if not 0<=accuracy<=1000 or not 1<=distance<=40:raise ValueError('Проверьте точность и дальность.')
    return {'name':name,'portrait':portrait,'color':color,'level':bounded('level',1,1,10000),
            'healthMax':bounded('healthMax',100,1,100000),'armor':bounded('armor',0,0,1000),
            'movement':bounded('movement',5,0,40),'attributes':attrs,'skills':skills,'defenses':defenses,
            'attack':{'damageMin':low,'damageMax':high,'accuracy':accuracy,'range':distance},
            'abilities':abilities,'equipment':list(spec.get('equipment',[]))[:30],
            'description':str(spec.get('description',''))[:6000], 'notes':str(spec.get('notes',''))[:6000],
            'sourceKey':str(spec.get('sourceKey',''))[:250]}


class NPCStore:
    def __init__(self,db):self.db=db

    async def archive(self,guild,owner,ident):
        async with self.db.connect() as c:
            await c.execute('BEGIN IMMEDIATE')
            rows=await c.execute_fetchall('SELECT * FROM npc_tokens WHERE id=? AND guild_id=? AND owner_id=?',(ident,guild,owner))
            if not rows:raise ValueError('НПС не принадлежит этому мастеру.')
            await c.execute('INSERT INTO npc_archive(guild_id,owner_id,original_id,payload,reason) VALUES(?,?,?,?,?)',
                (guild,owner,ident,json.dumps(dict(rows[0]),ensure_ascii=False),'Удалён мастером'))
            maps=await c.execute_fetchall('SELECT id,spec FROM battle_maps WHERE guild_id=? AND owner_id=?',(guild,owner))
            for m in maps:
                spec=json.loads(m['spec'])
                for field in ('tokens','npcs'):
                    if field in spec:spec[field]=[p for p in spec[field] if not (p.get('kind','npc')=='npc' and p['id']==ident)]
                await c.execute('UPDATE battle_maps SET spec=? WHERE id=?',(json.dumps(spec,ensure_ascii=False),m['id']))
            await c.execute('DELETE FROM npc_tokens WHERE id=?',(ident,));await c.commit()

    async def restore(self,guild,owner,archive_id):
        async with self.db.connect() as c:
            await c.execute('BEGIN IMMEDIATE')
            rows=await c.execute_fetchall('SELECT * FROM npc_archive WHERE id=? AND guild_id=? AND owner_id=?',(archive_id,guild,owner))
            if not rows:raise ValueError('Резервная копия НПС не найдена.')
            old=json.loads(rows[0]['payload'])
            cursor=await c.execute('INSERT INTO npc_tokens(guild_id,owner_id,name,spec,published) VALUES(?,?,?,?,?)',(guild,owner,old['name'],old['spec'],old['published']))
            await c.execute('DELETE FROM npc_archive WHERE id=?',(archive_id,));await c.commit();return cursor.lastrowid

    async def archived(self,guild,owner):
        async with self.db.connect() as c:
            rows=await c.execute_fetchall('SELECT id,payload,archived_at FROM npc_archive WHERE guild_id=? AND owner_id=? ORDER BY id DESC',(guild,owner))
        return [{'id':r['id'],'name':json.loads(r['payload'])['name'],'date':r['archived_at']} for r in rows]

    async def list(self,guild=None,owner=None,public=False):
        clauses=[];values=[]
        if guild is not None:clauses.append('guild_id=?');values.append(guild)
        if owner is not None:clauses.append('owner_id=?');values.append(owner)
        if public:clauses.append('published=1')
        async with self.db.connect() as conn:
            rows=await conn.execute_fetchall('SELECT * FROM npc_tokens'+(' WHERE '+' AND '.join(clauses) if clauses else '')+' ORDER BY id DESC',values)
        result=[]
        for row in rows:
            spec=json.loads(row['spec'])
            spec['abilities']=[refresh_ability(a) for a in spec.get('abilities',[])]
            image=portrait_library().get(spec.get('sourceKey'),portrait_library()['default'])
            if not spec.get('portrait'):spec.update(image)
            elif spec['portrait']==image['portrait']:spec.update(image)
            if public:spec.pop('notes',None)
            result.append({'id':row['id'],'published':bool(row['published']),'spec':spec})
        return result

    async def save(self,guild,owner,payload):
        if not isinstance(payload,dict):raise ValueError('Нужен объект НПС.')
        if payload.get('action')=='fromTemplate':
            key=str(payload.get('key',''))
            template=next((t for t in templates() if t['key']==key),None)
            if not template:raise ValueError('Игровой шаблон не найден.')
            payload={'spec':{**template,'sourceKey':key},'published':False}
        spec=validate_npc(payload.get('spec',{}));ident=int(payload.get('id',0))
        async with self.db.connect() as conn:
            if ident:
                cursor=await conn.execute('UPDATE npc_tokens SET name=?,spec=?,published=?,updated_at=CURRENT_TIMESTAMP WHERE id=? AND guild_id=? AND owner_id=?',
                    (spec['name'],json.dumps(spec,ensure_ascii=False),int(bool(payload.get('published',True))),ident,guild,owner))
                if cursor.rowcount!=1:raise ValueError('НПС не принадлежит этому мастеру.')
            else:
                cursor=await conn.execute('INSERT INTO npc_tokens(guild_id,owner_id,name,spec,published) VALUES(?,?,?,?,?)',
                    (guild,owner,spec['name'],json.dumps(spec,ensure_ascii=False),int(bool(payload.get('published',True)))))
                ident=cursor.lastrowid
            await conn.commit()
        return ident

    async def resolve_map(self,guild,owner,placements):
        if not placements:return []
        available={row['id']:row['spec'] for row in await self.list(guild,owner)}
        resolved=[]
        for row in placements:
            spec=available.get(int(row['id']))
            if not spec:raise ValueError('НПС на карте не принадлежит этому мастеру.')
            resolved.append({**{k:v for k,v in spec.items() if k!='notes'},'kind':'npc','id':row['id'],'x':row['x'],'y':row['y'],'team':row.get('team','enemy')})
        return resolved
