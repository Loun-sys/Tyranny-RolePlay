"""Atomic use of owned consumables; durations advance by rounds, never a clock."""
import json
from consumables import profile,apply,duration
from item_effects import STATS

SCHEMA='''CREATE TABLE IF NOT EXISTS character_item_effects (
character_id INTEGER PRIMARY KEY REFERENCES characters(id) ON DELETE CASCADE,
states TEXT NOT NULL DEFAULT '{}');'''

async def states(db,cid):
    async with db.connect() as conn:
        await conn.executescript(SCHEMA)
        rows=await conn.execute_fetchall('SELECT states FROM character_item_effects WHERE character_id=?',(cid,))
        return json.loads(rows[0]['states']) if rows else {}

async def use(db,cid,inventory_id):
    async with db.connect() as conn:
        await conn.executescript(SCHEMA)
        await conn.execute('BEGIN IMMEDIATE')
        rows=await conn.execute_fetchall('SELECT item_catalog.*,inventory.quantity,inventory.equipped_slot FROM inventory JOIN item_catalog ON item_catalog.id=inventory.item_id WHERE inventory.id=? AND character_id=?',(inventory_id,cid))
        if not rows or rows[0]['equipped_slot']=='Мастерская':raise ValueError('Предмет недоступен.')
        from item_texts import normalize_item_text
        item=normalize_item_text(dict(rows[0]));info=profile(item)
        if not info:raise ValueError('Этот предмет не является расходником.')
        if info['targeting']!='self':raise ValueError('Зелье воскрешения нужно применить в бою к павшему союзнику.')
        character=(await conn.execute_fetchall('SELECT health,health_max FROM characters WHERE id=?',(cid,)))[0]
        old=await conn.execute_fetchall('SELECT states FROM character_item_effects WHERE character_id=?',(cid,))
        current=json.loads(old[0]['states']) if old else {}
        from registration_api import _derived,_clean_inventory
        from consumables import virtual_equipment
        actor=await db.get_character_by_id(cid)
        equipped=await db.inventory(cid)
        maximum=_derived(actor,_clean_inventory(equipped)+virtual_equipment(current,1))['healthMax']
        health=apply(item,current,1,character['health'],maximum)
        for n,e in enumerate(info['effects']):
            if e.get('AffectsStat') in {56,57,58,59,99,100} and duration(e)==0:
                name=STATS[e['AffectsStat']];value=round(e['Value'])
                attrs=await conn.execute_fetchall('SELECT value FROM attributes WHERE character_id=? AND name=?',(cid,name))
                if not attrs or not 1<=attrs[0]['value']+value<=30:raise ValueError('Характеристика уже достигла допустимого предела.')
                await conn.execute('UPDATE attributes SET value=value+? WHERE character_id=? AND name=?',(value,cid,name))
                current.pop(f"consumable:{item['properties']['gameData']['prefab']}:{n}",None)
        await conn.execute('UPDATE characters SET health=?,updated_at=CURRENT_TIMESTAMP WHERE id=?',(health,cid))
        await conn.execute('INSERT OR REPLACE INTO character_item_effects(character_id,states) VALUES(?,?)',(cid,json.dumps(current,ensure_ascii=False)))
        if rows[0]['quantity']>1:await conn.execute('UPDATE inventory SET quantity=quantity-1 WHERE id=?',(inventory_id,))
        else:await conn.execute('DELETE FROM inventory WHERE id=?',(inventory_id,))
        await conn.commit()
        return f"«{item['name']}»: {info['description']}"
