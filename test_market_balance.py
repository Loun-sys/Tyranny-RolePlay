"""Whole-catalog source/stat audit and authoritative merchant level gates."""
import copy,json,math,unittest
from pathlib import Path
from aiohttp import web
from aiohttp.test_utils import TestClient,TestServer
from test_campaign import CampaignTests
from merchant_rules import market_profile,SHOPS,SHOP_BALANCE_VERSION,MATERIAL_PRICES,consumable_costs,recipe_outputs,is_artifact,shop_accepts
from item_texts import catalog_texts,normalize_item_text
from item_effects import game_data,armor_by_type,equip_modifiers
from crafting import normalize_quality,quality_info,scale_row
from consumables import profile,apply,virtual_equipment
from registration_api import player_catalog,portal_shop,_derived
from catalog_browser import browse

class MarketSourceTests(unittest.TestCase):
    def test_every_source_item_keeps_numeric_stats_and_functional_readouts(self):
        rows=catalog_texts()[0]
        self.assertEqual(len(rows),1233)
        character={'attributes':dict.fromkeys(['Сила','Искусность','Быстрота','Живучесть','Смекалка','Стойкость'],10),
            'skills':{name:{'value':30} for name in ['Атлетика','Хитроумие','Знания','Парирование','Уклонение','Одноручное оружие','Двуручное оружие','Волшебный посох','Луки','Парное оружие','Безоружный бой']},'health_max':100}
        for raw in rows.values():
            with self.subTest(item=raw['name']):
                item=normalize_quality(normalize_item_text(raw));g=game_data(item);info=quality_info(item)
                self.assertEqual(g['statsVersion'],2)
                if info and (scaling:=scale_row(info,info['level'])):
                    if info['kind']=='weapon':
                        from weapon_stats import source_attack
                        _,melee=source_attack(g['prefab'])
                        prefix='Weapon_MeleeAttack_AttackBase_' if melee else 'AttackBase_'
                        self.assertEqual(item['damage_min'],round(scaling[prefix+'DamageData_DamageMin']))
                        self.assertEqual(item['damage_max'],round(scaling[prefix+'DamageData_DamageMax']))
                    if info['kind']=='armor':self.assertAlmostEqual(item['armor'],scaling['DamageThreshold'])
                else:
                    self.assertEqual(item['damage_max'],round(g.get('attack',{}).get('DamageData',{}).get('Maximum',0)))
                    self.assertAlmostEqual(item['armor'],g.get('armor',{}).get('DamageThreshold',0),places=4)
                if item['hands']:self.assertIn(item['category'],SHOPS['weapons']['categories'])
                item['equipped_slot']='Оружие I — правая рука' if item['hands'] else item['slot'] or 'Эффект'
                d=_derived(character,[item]);mods=equip_modifiers(item)
                for kind,value in armor_by_type(item).items():
                    if not any(e.get('AffectsStat')==32 for e in g.get('statusEffects',[])):self.assertAlmostEqual(d['armorByType'][kind],value)
                for stat,value in mods['flat'].items():
                    if stat in character['attributes']:self.assertEqual(d['effectiveAttributes'][stat],round(10+value))
                self.assertTrue(all(math.isfinite(v) for v in d['armorByType'].values()))
                self.assertGreaterEqual(d['attack']['damageMax'],d['attack']['damageMin'])
                self.assertTrue((Path('web')/item['image_url']).is_file())

    def test_all_consumables_execute_and_special_limits_are_visible(self):
        usable=[i for i in catalog_texts()[0].values() if profile(i)]
        self.assertEqual(len(usable),55)
        for i in usable:
            with self.subTest(item=i['name']):
                info=profile(i);self.assertEqual(i['category'],'Расходуемые предметы')
                self.assertTrue(info['description']);states={}
                hp=apply(i,states,1,0 if any(e.get('AffectsStat')==176 for e in info['effects']) else 50,100)
                self.assertTrue(0<=hp<=100)
                virtual_equipment(states,1)
                if info['permanent']:
                    m=market_profile(i);self.assertEqual(m['minLevel'],20);self.assertEqual(m['initialStock'],1);self.assertGreaterEqual(m['buyPrice'],5000)

    def test_prices_stock_and_tiers(self):
        for raw in catalog_texts()[0].values():
            i=normalize_quality(raw);m=market_profile(i)
            if not m['purchasable']:continue
            self.assertIn(m['minLevel'],[1,5,10,15,20])
            self.assertEqual(SHOPS[m['shopKey']]['minLevel'],m['minLevel'])
            self.assertLess(m['sellPrice'],m['buyPrice'])
            if game_data(i)['prefab'] not in MATERIAL_PRICES:self.assertGreaterEqual(m['buyPrice'],i['value'])
            if i['category']=='Аксессуары':self.assertGreaterEqual(m['minLevel'],5)
        for prefab,cost in consumable_costs().items():
            m=market_profile(catalog_texts()[0][prefab])
            self.assertGreater(m['buyPrice'],cost);self.assertLess(m['sellPrice'],cost)
        for prefab,output in recipe_outputs().items():
            m=market_profile(catalog_texts()[0][prefab]);self.assertTrue(m['purchasable'])
            self.assertGreaterEqual(m['minLevel'],market_profile(output)['minLevel'])

    def test_artifact_families_are_catalogue_only_even_at_other_qualities(self):
        from artifact_rules import library
        artifacts=[i for i in catalog_texts()[0].values() if is_artifact(i)]
        self.assertGreater(len(artifacts),50)
        self.assertTrue(any(i['quality']!='Артефакт' for i in artifacts))
        for item in artifacts:
            with self.subTest(item=item['name']):
                self.assertFalse(market_profile(item)['purchasable'])
                self.assertIn('Артефакты',market_profile(item)['unavailableReason'])
                self.assertFalse(any(shop_accepts(item,key) for key in SHOPS))
                upgraded=copy.deepcopy(item)
                upgraded['name']+=' (Безупречное)'
                upgraded['properties']['gameData']['craftBaseName']=item['name']
                self.assertTrue(is_artifact(upgraded))
        for name in library():
            self.assertTrue(is_artifact({'name':name,'quality':'Обычное','properties':{}}))

    def test_numbered_variants_stay_in_catalog_but_not_any_shop(self):
        variants=[i for i in catalog_texts()[0].values() if 'вариант ' in i['name']]
        self.assertEqual(len(variants),323)
        for i in variants:
            self.assertFalse(market_profile(i)['purchasable'],i['name'])
            self.assertFalse(any(shop_accepts(i,key) for key in SHOPS),i['name'])


class MarketStoreTests(CampaignTests):
    async def seed(self):
        await self.db.upsert_catalog([normalize_quality(i) for i in catalog_texts()[0].values()])
        await self.store.ensure_shops(1)

    async def test_numbered_variant_migration_preserves_owned_item_and_manual_stock(self):
        await self.seed();await self.store.set_wallet(1,10000)
        source=next(i for i in catalog_texts()[0].values() if '(вариант 2)' in i['name'] and not is_artifact(i))
        async with self.db.connect() as c:
            i=dict((await c.execute_fetchall('SELECT * FROM item_catalog WHERE name=?',(source['name'],)))[0])
            await c.execute('INSERT INTO shop_stock(guild_id,item_id,stock,buy_price,sell_price,enabled,shop_key) VALUES(1,?,7,111,55,1,?)',(i['id'],'custom'))
            await c.execute('INSERT INTO shop_stock_customized VALUES(1,?)',(i['id'],))
            await c.execute('UPDATE shop_balance_seeded SET version=3');await c.commit()
        await self.db.admin_give_item(1,i['name'])
        owned=next(r for r in await self.db.inventory(1) if r['id']==i['id'])
        for payload in [{'action':'buy','itemId':i['id']},{'action':'sell','inventoryId':owned['inventory_id']}]:
            with self.assertRaisesRegex(ValueError,'Нумерованные'):await self.store.trade(1,payload)
        with self.assertRaisesRegex(ValueError,'Нумерованные'):
            await self.store.edit_shop(1,{'itemId':i['id'],'shopKey':'custom','stock':1,'enabled':True})
        await self.store.ensure_shops(1)
        self.assertFalse(any(r['id']==i['id'] for r in (await self.store.shop(1,shop_key='custom'))['items']))
        self.assertFalse(any(r['id']==i['id'] for r in await self.store.sale_offers(1,1,'custom')))
        async with self.db.connect() as c:
            r=(await c.execute_fetchall('SELECT * FROM shop_stock WHERE item_id=?',(i['id'],)))[0]
            self.assertEqual((r['enabled'],r['stock'],r['buy_price'],r['sell_price']),(0,7,111,55))
            self.assertTrue(await c.execute_fetchall('SELECT 1 FROM item_catalog WHERE id=?',(i['id'],)))
        self.assertEqual((await self.store.wallet(1))['totalCopper'],10000)
        self.assertTrue(any(r['inventory_id']==owned['inventory_id'] for r in await self.db.inventory(1)))

    async def test_all_tradeable_items_distributed_once_and_pagination(self):
        await self.seed()
        async with self.db.connect() as c:
            rows=[dict(r) for r in await c.execute_fetchall('SELECT * FROM item_catalog')]
            stock=await c.execute_fetchall('SELECT item_id,shop_key FROM shop_stock WHERE guild_id=1')
        wanted={r['id']:market_profile(r)['shopKey'] for r in rows if market_profile(r)['purchasable']}
        self.assertEqual({r['item_id']:r['shop_key'] for r in stock},wanted)
        result=await self.store.shop(1,shop_key='armor');self.assertGreater(result['total'],50)
        next_page=await self.store.shop(1,shop_key='armor',offset=50)
        self.assertFalse({r['id'] for r in result['items']} & {r['id'] for r in next_page['items']})

    async def test_level_gate_cannot_be_bypassed_and_is_atomic(self):
        await self.seed();await self.store.set_wallet(1,1000000)
        for level in [5,10,15,20]:
            shop=await self.store.shop(1,shop_key=f'level_{level}',level=1);self.assertTrue(shop['settings']['locked'])
            item=shop['items'][0]
            with self.assertRaisesRegex(ValueError,'уровня'):await self.store.trade(1,{'action':'buy','itemId':item['id']})
            self.assertEqual((await self.store.wallet(1))['totalCopper'],1000000)
            async with self.db.connect() as c:
                await c.execute('UPDATE characters SET level=? WHERE id=1',(level,));await c.commit()
            await self.store.trade(1,{'action':'buy','itemId':item['id'],'shopKey':f'level_{level}'})
            await self.store.set_wallet(1,1000000)
            async with self.db.connect() as c:
                await c.execute('UPDATE characters SET level=1 WHERE id=1');await c.commit()

    async def test_migration_preserves_explicit_edits_and_does_not_refill(self):
        await self.seed();s=await self.store.shop(1,shop_key='consumables');i=s['items'][0]
        await self.store.edit_shop(1,{'itemId':i['id'],'shopKey':'consumables','stock':0,'buyPrice':432,'sellPrice':123,'enabled':False})
        async with self.db.connect() as c:
            await c.execute('UPDATE shop_balance_seeded SET version=0');await c.commit()
        await self.store.ensure_shops(1)
        row=next(r for r in (await self.store.shop(1,admin=True,shop_key='consumables'))['items'] if r['id']==i['id'])
        self.assertEqual((row['stock'],row['buy_price'],row['sell_price'],row['enabled']),(0,432,123,0))
        await self.store.edit_shop(1,{'action':'settings','shopKey':'consumables','minLevel':7,'name':'Припасы','enabled':True})
        with self.assertRaisesRegex(ValueError,'7 уровня'):await self.store.trade(1,{'action':'buy','itemId':s['items'][1]['id']})

    async def test_public_catalog_and_server_gates(self):
        await self.seed();app=web.Application();app['db']=self.db
        app.router.add_get('/api/catalog',player_catalog);app.router.add_get('/api/portal/{token}/shop',portal_shop)
        app.router.add_post('/api/portal/{token}/shop',portal_shop)
        token=await self.db.create_portal_token(1,1)
        async with TestClient(TestServer(app)) as client:
            response=await client.get('/api/catalog?category=Посохи&minLevel=20&availability=buyable')
            self.assertEqual(response.status,200);result=await response.json();self.assertGreater(result['total'],0)
            for i in result['items']:
                self.assertEqual(i['market']['minLevel'],20);self.assertNotIn('gameData',i['properties']);self.assertNotIn('source_url',i)
            self.assertEqual((await client.get('/api/catalog?offset=oops')).status,400)
            self.assertEqual((await (await client.get('/api/catalog')).json())['total'],1233)
            self.assertEqual((await client.post('/api/catalog',json={})).status,405)
            s=await (await client.get(f'/api/portal/{token}/shop?shopKey=level_20')).json()
            self.assertTrue(s['settings']['locked'])
            response=await client.post(f'/api/portal/{token}/shop',json={'action':'buy','itemId':s['items'][0]['id']})
            self.assertEqual(response.status,409)
        page=await browse(self.db,availability='buyable',min_level=5,sort='price_asc')
        self.assertTrue(all(i['market']['minLevel']==5 for i in page['items']))
        self.assertEqual([i['catalogPrice'] for i in page['items']],sorted(i['catalogPrice'] for i in page['items']))

    async def test_purchased_armor_equips_and_potion_actually_heals(self):
        await self.seed();await self.store.set_wallet(1,10000)
        async with self.db.connect() as c:
            armor=dict((await c.execute_fetchall("SELECT * FROM item_catalog WHERE category='Броня' AND slot='Торс' AND armor>0 ORDER BY value LIMIT 1"))[0])
            potion=dict((await c.execute_fetchall("SELECT * FROM item_catalog WHERE name='Слабое зелье исцеления'"))[0])
            await c.execute('UPDATE characters SET health=10,health_max=100 WHERE id=1');await c.commit()
        for item in [armor,potion]:await self.store.trade(1,{'action':'buy','itemId':item['id']})
        inv=await self.db.inventory(1);armor_inv=next(i for i in inv if i['id']==armor['id'])
        await self.db.equip(1,armor_inv['inventory_id'],'Торс')
        actual=next(i for i in await self.db.inventory(1) if i['id']==armor['id'])
        self.assertEqual(actual['armor'],armor['armor']);self.assertEqual(actual['equipped_slot'],'Торс')
        from consumable_store import use
        await use(self.db,1,next(i['inventory_id'] for i in inv if i['id']==potion['id']))
        self.assertEqual((await self.db.get_character_by_id(1))['health'],35)
        self.assertFalse(any(i['id']==potion['id'] for i in await self.db.inventory(1)))

    async def test_crafted_quality_can_be_sold_without_refilling_other_stock(self):
        await self.seed()
        source=next(i for i in catalog_texts()[0].values() if i['category']=='Броня' and (quality_info(i) or {}).get('level')==1 and market_profile(i)['purchasable'])
        upgraded=normalize_quality(source,2);upgraded['source_url']='craft://market-test'
        await self.db.upsert_catalog([upgraded])
        async with self.db.connect() as c:
            actual=dict((await c.execute_fetchall("SELECT * FROM item_catalog WHERE source_url='craft://market-test'"))[0])
            await c.execute('UPDATE characters SET level=20 WHERE id=1');await c.commit()
        await self.db.admin_give_item(1,actual['name'])
        p=market_profile(actual)
        self.assertTrue(any(i['id']==actual['id'] for i in await self.store.sale_offers(1,1,p['shopKey'])))
        item=next(i for i in await self.db.inventory(1) if i['id']==actual['id'])
        await self.store.trade(1,{'action':'sell','inventoryId':item['inventory_id'],'shopKey':p['shopKey']})
        self.assertEqual((await self.store.wallet(1))['totalCopper'],p['sellPrice'])
        async with self.db.connect() as c:
            sold=(await c.execute_fetchall('SELECT stock FROM shop_stock WHERE item_id=?',(actual['id'],)))[0]
            self.assertEqual(sold['stock'],1)

    async def test_artifact_migration_and_direct_trade_cannot_bypass_exclusion(self):
        await self.seed();await self.store.set_wallet(1,10000)
        source=next(i for i in catalog_texts()[0].values() if is_artifact(i) and not i['name'].endswith(')') and i['hands'])
        async with self.db.connect() as c:
            item=dict((await c.execute_fetchall('SELECT * FROM item_catalog WHERE name=?',(source['name'],)))[0])
            await c.execute('INSERT INTO shop_stock(guild_id,item_id,stock,buy_price,sell_price,enabled,shop_key) VALUES(1,?,2,6000,3000,1,?)',(item['id'],'custom'))
            await c.execute('INSERT INTO shop_stock_customized VALUES(1,?)',(item['id'],))
            await c.execute('UPDATE characters SET level=20 WHERE id=1')
            await c.execute('UPDATE shop_balance_seeded SET version=2');await c.commit()
        await self.db.admin_give_item(1,item['name'])
        inventory=await self.db.inventory(1);owned=next(i for i in inventory if i['id']==item['id'])
        # Even legacy/custom enabled stock is untradeable before migration runs.
        for payload in [{'action':'buy','itemId':item['id']},{'action':'sell','inventoryId':owned['inventory_id']}]:
            with self.assertRaisesRegex(ValueError,'Артефакты'):await self.store.trade(1,payload)
        self.assertEqual((await self.store.wallet(1))['totalCopper'],10000)
        self.assertFalse(any(i['id']==item['id'] for i in await self.store.sale_offers(1,1,'custom')))
        with self.assertRaisesRegex(ValueError,'Артефакты'):
            await self.store.edit_shop(1,{'itemId':item['id'],'shopKey':'custom','stock':2,'buyPrice':6000,'sellPrice':3000,'enabled':True})
        await self.store.ensure_shops(1)
        self.assertFalse(any(i['id']==item['id'] for i in (await self.store.shop(1,shop_key='custom'))['items']))
        async with self.db.connect() as c:
            row=(await c.execute_fetchall('SELECT * FROM shop_stock WHERE guild_id=1 AND item_id=?',(item['id'],)))[0]
            self.assertEqual((row['enabled'],row['stock'],row['buy_price'],row['sell_price']),(0,2,6000,3000))
            self.assertTrue(await c.execute_fetchall('SELECT 1 FROM item_catalog WHERE id=?',(item['id'],)))
        self.assertTrue(any(i['inventory_id']==owned['inventory_id'] for i in await self.db.inventory(1)))
