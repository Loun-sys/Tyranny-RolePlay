"""Parameterized, paginated item browsing shared by master catalog filters."""
async def browse(db,query='',category='',quality='',offset=0,sort='name',min_price=0,max_price=2000000000):
    clauses=['value>=?','value<=?'];values=[min_price,max_price]
    if query:clauses.append('(name LIKE ? OR description LIKE ?)');values.extend(['%'+query+'%']*2)
    if category:clauses.append('category=?');values.append(category)
    if quality:clauses.append('quality=?');values.append(quality)
    order={'name':'name,id','price_asc':'value,name,id','price_desc':'value DESC,name,id'}.get(sort,'name,id')
    async with db.connect() as c:
        total=(await c.execute_fetchall('SELECT COUNT(*) AS n FROM item_catalog WHERE '+' AND '.join(clauses),values))[0]['n']
        rows=await c.execute_fetchall('SELECT * FROM item_catalog WHERE '+' AND '.join(clauses)+' ORDER BY '+order+' LIMIT 50 OFFSET ?',(*values,offset))
        categories=await c.execute_fetchall('SELECT DISTINCT category FROM item_catalog ORDER BY category')
        qualities=await c.execute_fetchall('SELECT DISTINCT quality FROM item_catalog ORDER BY quality')
    return {'items':[dict(r) for r in rows],'total':total,'offset':offset,'categories':[r['category'] for r in categories],
        'qualities':[r['quality'] for r in qualities]}
