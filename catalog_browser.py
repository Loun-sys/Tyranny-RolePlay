"""Parameterized, paginated item browsing shared by master catalog filters."""
async def browse(db,query='',category='',quality='',offset=0,sort='name',min_price=0,max_price=2000000000,min_level='',availability='',slot='',verified_only=False):
    clauses=['1=1'];values=[]
    if query:clauses.append('(name LIKE ? OR description LIKE ?)');values.extend(['%'+query+'%']*2)
    if category:clauses.append('category=?');values.append(category)
    if quality:clauses.append('quality=?');values.append(quality)
    if slot:clauses.append('slot=?');values.append(slot)
    order={'name':'name,id','price_asc':'value,name,id','price_desc':'value DESC,name,id'}.get(sort,'name,id')
    async with db.connect() as c:
        rows=await c.execute_fetchall('SELECT * FROM item_catalog WHERE '+' AND '.join(clauses)+' ORDER BY '+order,values)
        categories=await c.execute_fetchall('SELECT DISTINCT category FROM item_catalog ORDER BY category')
        qualities=await c.execute_fetchall('SELECT DISTINCT quality FROM item_catalog ORDER BY quality')
        slots=await c.execute_fetchall("SELECT DISTINCT slot FROM item_catalog WHERE slot<>'' ORDER BY slot")
    from merchant_rules import market_profile
    from item_effects import game_data
    items=[{**dict(r),'market':market_profile(dict(r))} for r in rows]
    if verified_only:items=[i for i in items if game_data(i).get('statsVersion')==2]
    for item in items:item['catalogPrice']=item['market']['buyPrice'] if item['market']['purchasable'] else item['value']
    items=[i for i in items if min_price<=i['catalogPrice']<=max_price]
    if sort in {'price_asc','price_desc'}:items.sort(key=lambda i:i['catalogPrice'],reverse=sort=='price_desc')
    if min_level:items=[i for i in items if i['market']['minLevel']==int(min_level)]
    if availability=='buyable':items=[i for i in items if i['market']['purchasable']]
    if availability=='unavailable':items=[i for i in items if not i['market']['purchasable']]
    total=len(items)
    if verified_only:
        async with db.connect() as c:
            all_rows=[dict(r) for r in await c.execute_fetchall('SELECT category,quality,slot,properties FROM item_catalog')]
        all_rows=[i for i in all_rows if game_data(i).get('statsVersion')==2]
        categories=[{'category':v} for v in sorted({i['category'] for i in all_rows})]
        qualities=[{'quality':v} for v in sorted({i['quality'] for i in all_rows})]
        slots=[{'slot':v} for v in sorted({i['slot'] for i in all_rows if i['slot']})]
    return {'items':items[offset:offset+50],'total':total,'offset':offset,'categories':[r['category'] for r in categories],
        'qualities':[r['quality'] for r in qualities],'slots':[r['slot'] for r in slots]}
