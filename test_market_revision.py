"""Campaign exclusions, complete distribution, starter balance and bag occupancy."""
import copy,json,tempfile,unittest
from pathlib import Path
from item_texts import catalog_texts,normalize_item_text
from merchant_rules import excluded_from_trade,is_artifact,market_profile,shop_accepts,SHOPS
from player_possessions import STARTS
from database import Database
from database import SCHEMA as BASE_SCHEMA
from campaign_store import CampaignStore,SCHEMA as CAMPAIGN_SCHEMA


class MarketRevisionTests(unittest.TestCase):
    def test_named_artifacts_and_their_copies_are_never_sold(self):
        for prefab in ['WPN_1H_SK_Dagger_BledenMark','WPN_1H_SK_Dagger_BledenMark_Small',
                       'WPN_ENEMY_1H_IR_Dagger_BloodBound','WPN_STF_Tunon']:
            item=copy.deepcopy(catalog_texts()[0][prefab])
            self.assertEqual(item['quality'],'Артефакт')
            for crafted in [False,True]:
                if crafted:
                    item['properties']['gameData']['craftBaseName']=item['name']
                    item['name']+=' (Безупречное)';item['quality']='Обычное'
                self.assertTrue(is_artifact(item))
                self.assertFalse(market_profile(item)['purchasable'])
                self.assertTrue(all(not shop_accepts(item,key) for key in SHOPS))
                self.assertEqual(normalize_item_text(item)['quality'],'Артефакт')

    def test_only_masterwork_bronze_greatsword_is_removed(self):
        item=copy.deepcopy(catalog_texts()[0]['WPN_2H_Starter_Sword'])
        self.assertTrue(market_profile(item)['purchasable'])
        item['properties']['gameData']['craftBaseName']=item['name']
        item['name']+=' (Безупречное)';item['quality']='Безупречное'
        self.assertIn('двуручный меч',excluded_from_trade(item))
        self.assertFalse(shop_accepts(item,'custom'))

    def test_no_quest_item_can_be_added_to_master_shop(self):
        item={'name':'Задание','quality':'Обычное','properties':{'gameData':{'sourceItem':{'IsQuestItem':1}}}}
        self.assertEqual(excluded_from_trade(item),'Квестовый предмет')
        self.assertFalse(shop_accepts(item,'custom'))

    def test_nonquest_companion_equipment_has_a_shop(self):
        for prefab in ['Cloth_Armor_Lantry','Cloth_GLOVE_Lantry','Cloth_BOOTS_Lantry','WPN_1H_IR_Dagger_Lantry']:
            self.assertTrue(market_profile(catalog_texts()[0][prefab])['purchasable'])

    def test_recruit_bundle_items_are_imported_with_quality_source_and_price(self):
        recruits=[i for k,i in catalog_texts()[0].items() if k.startswith('KenrickRecruit_')]
        self.assertEqual(len(recruits),18)
        for i in recruits:
            game=i['properties']['gameData']
            self.assertEqual(game['archive'],'recipes')
            self.assertTrue(game['sourceItem'])
            self.assertIn(i['quality'],{'Хорошее','Превосходное','Выдающееся'})
            self.assertTrue(market_profile(i)['purchasable'],i['name'])
            if i['hands']:self.assertGreater(i['damage_max'],0)
            upgraded=copy.deepcopy(i);upgraded.update(source_url='craft://recruit-test',quality='Безупречное')
            self.assertEqual(normalize_item_text(upgraded)['name'],game['sourceName']+' (Безупречное)')

    def test_reduced_new_character_grants(self):
        expected={'Книгочей':180,'Заклинатель':120,'Зверолюд':0,'Певчий':180,
                  'Танцующий':120,'Авангард':180,'Скованный Ремеслом':360}
        self.assertEqual({k:v[0] for k,v in STARTS.items()},expected)
        supplies={k:q for k,q in STARTS['Скованный Ремеслом'][1] if k.startswith('RES_')}
        self.assertEqual(supplies,{'RES_SkyPillar_Ingot_Iron':5,'RES_SkyPillar_Ingot_Bronze':5,
                                   'RES_SkyPillar_Hide':5,'RES_SkyPillar_AlchemySupplies':7})

    def test_all_equipment_positions_are_free_but_workshop_reservation_is_not(self):
        for slot in ['Голова','Торс','Руки','Ноги','Аксессуар 1','Аксессуар 2',
                     'Оружие I — правая рука','Оружие II — левая рука','Быстрый предмет 1']:
            self.assertFalse(Database._item_consumes_slot('Тяжёлая вещь','Броня',10,slot),slot)
        self.assertTrue(Database._item_consumes_slot('Тяжёлая вещь','Броня',10))
        self.assertTrue(Database._item_consumes_slot('Тяжёлая вещь','Броня',10,'Мастерская'))

    def test_credit_is_small_translucent_and_scoped_to_page_footer(self):
        css=Path('web/responsive.css').read_text(encoding='utf-8')
        self.assertIn('body>footer>.site-credit{font:9px',css);self.assertIn('opacity:.4',css)
        for page in ['archive','index']:
            self.assertIn('class="site-credit"',Path(f'web/{page}.html').read_text(encoding='utf-8'))


class MarketRevisionStoreTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.db=Database(Path(self.tmp.name)/'market.db')
        async with self.db.connect() as c:
            await c.executescript(BASE_SCHEMA+CAMPAIGN_SCHEMA)
            await c.execute("INSERT INTO characters(id,guild_id,user_id,name,background,specialization_1,specialization_2) VALUES(1,1,1,'Тест','Книгочей','Меч и щит','Дротик')")
            await c.commit()
        self.store=CampaignStore(self.db)

    async def asyncTearDown(self):self.tmp.cleanup()

    async def test_every_tradeable_item_and_legacy_exclusions_without_loss(self):
        await self.db.upsert_catalog(list(catalog_texts()[0].values()))
        bronze=copy.deepcopy(catalog_texts()[0]['WPN_2H_Starter_Sword'])
        bronze['quality']='Безупречное';bronze['name']+=' (Безупречное)';bronze['source_url']='craft://test-blacklist'
        bronze['properties']['gameData']['craftBaseName']='Бронзовый двуручный меч'
        await self.db.upsert_catalog([bronze])
        async with self.db.connect() as c:
            all_items=[dict(r) for r in await c.execute_fetchall('SELECT * FROM item_catalog')]
            banned=[r for r in all_items if is_artifact(r) or r['source_url']=='craft://test-blacklist']
            for i in banned:
                await c.execute('INSERT INTO shop_stock VALUES(1,?,9,123,61,1,?)',(i['id'],'custom'))
                await c.execute('INSERT INTO shop_stock_customized VALUES(1,?)',(i['id'],))
            await c.execute('INSERT INTO inventory(character_id,item_id,quantity) VALUES(1,?,1)',(banned[0]['id'],))
            await c.execute('INSERT INTO shop_balance_seeded VALUES(1,4)');await c.commit()
        await self.store.set_wallet(1,333)
        await self.store.ensure_shops(1)
        async with self.db.connect() as c:
            active=await c.execute_fetchall('SELECT item_id,shop_key FROM shop_stock WHERE enabled=1')
            preserved=await c.execute_fetchall('SELECT item_id,stock,buy_price,sell_price,enabled FROM shop_stock WHERE item_id IN ('+','.join('?' for _ in banned)+')',[i['id'] for i in banned])
        expected={i['id']:market_profile(i)['shopKey'] for i in all_items if market_profile(i)['purchasable']}
        self.assertEqual({i['item_id']:i['shop_key'] for i in active},expected)
        self.assertGreater(len(expected),700)
        self.assertTrue(all((i['stock'],i['buy_price'],i['sell_price'],i['enabled'])==(9,123,61,0) for i in preserved))
        self.assertEqual((await self.store.wallet(1))['totalCopper'],333)
        self.assertEqual(len(await self.db.inventory(1)),1)
        for i in banned[:2]:
            with self.assertRaises(ValueError):await self.store.trade(1,{'action':'buy','itemId':i['id']})
            with self.assertRaises(ValueError):await self.store.edit_shop(1,{'itemId':i['id'],'shopKey':'custom','stock':1})

    async def test_equipping_and_removing_changes_bag_usage(self):
        await self.db.upsert_catalog([catalog_texts()[0]['Leather_Armor_02']])
        async with self.db.connect() as c:
            item=(await c.execute_fetchall('SELECT id FROM item_catalog'))[0]
            cursor=await c.execute('INSERT INTO inventory(character_id,item_id,quantity) VALUES(1,?,1)',(item['id'],))
            ident=cursor.lastrowid;await c.commit()
        self.assertEqual((await self.db.inventory_capacity(1))['used'],1)
        self.assertTrue((await self.db.equip(1,ident,'Торс'))[0])
        self.assertEqual((await self.db.inventory_capacity(1))['used'],0)
        self.assertTrue(await self.db.unequip(1,ident))
        self.assertEqual((await self.db.inventory_capacity(1))['used'],1)

    async def test_source_import_does_not_overwrite_same_named_forged_record(self):
        item=copy.deepcopy(next(i for k,i in catalog_texts()[0].items() if k.startswith('KenrickRecruit_')))
        async with self.db.connect() as c:
            cursor=await c.execute("INSERT INTO item_catalog(name,source_url,quality,damage_min,damage_max,properties) VALUES(?,'craft://owned-name-collision','Хорошее',777,888,'{}')",(item['name'],))
            old_id=cursor.lastrowid
            await c.execute('INSERT INTO inventory(character_id,item_id,quantity) VALUES(1,?,1)',(old_id,))
            before=dict((await c.execute_fetchall('SELECT * FROM item_catalog WHERE id=?',(old_id,)))[0]);await c.commit()
        await self.db.upsert_catalog([item]);await self.db.upsert_catalog([item])
        async with self.db.connect() as c:
            after=dict((await c.execute_fetchall('SELECT * FROM item_catalog WHERE id=?',(old_id,)))[0])
            imported=await c.execute_fetchall('SELECT id FROM item_catalog WHERE source_url=?',(item['source_url'],))
            owned=(await c.execute_fetchall('SELECT item_id FROM inventory WHERE character_id=1'))[0]
        self.assertEqual(after,before)
        self.assertEqual(owned['item_id'],old_id)
        self.assertEqual(len(imported),1)
        self.assertNotEqual(imported[0]['id'],old_id)

    async def test_forge_upgrade_only_replaces_selected_owned_instance(self):
        from crafting import CraftingStore,SCHEMA,ORIGIN,upgrade_recipe
        base=copy.deepcopy(next(i for i in catalog_texts()[0].values() if i['slot']=='Торс' and upgrade_recipe(i) and not is_artifact(i)))
        recipe=upgrade_recipe(base);self.assertIsNotNone(recipe)
        await self.db.upsert_catalog([base,*[catalog_texts()[0][x['prefab']] for x in recipe['ingredients']]])
        async with self.db.connect() as c:
            await c.executescript(SCHEMA)
            await c.execute('UPDATE characters SET background=? WHERE id=1',(ORIGIN,))
            await c.execute("INSERT INTO characters(id,guild_id,user_id,name,background,specialization_1,specialization_2) VALUES(2,1,2,'Другой','Книгочей','Меч и щит','Дротик')")
            original=dict((await c.execute_fetchall('SELECT * FROM item_catalog WHERE name=?',(base['name'],)))[0])
            selected=(await c.execute("INSERT INTO inventory(character_id,item_id,quantity,equipped_slot) VALUES(1,?,1,'Торс')",(original['id'],))).lastrowid
            spare=(await c.execute('INSERT INTO inventory(character_id,item_id,quantity) VALUES(1,?,1)',(original['id'],))).lastrowid
            other=(await c.execute("INSERT INTO inventory(character_id,item_id,quantity,equipped_slot) VALUES(2,?,1,'Торс')",(original['id'],))).lastrowid
            await c.commit()
        await self.store.edit_shop(1,{'itemId':original['id'],'shopKey':'custom','stock':3,'buyPrice':222,'sellPrice':111})
        await self.store.set_wallet(1,10000)
        for ingredient in recipe['ingredients']:
            if ingredient['consumed']:await self.db.admin_give_item(1,catalog_texts()[0][ingredient['prefab']]['name'],ingredient['quantity'])
        craft=CraftingStore(self.db)
        with self.assertRaises(ValueError):await craft.act(1,{'action':'upgrade','inventoryId':other})
        await craft.act(1,{'action':'upgrade','inventoryId':selected})
        async with self.db.connect() as c:
            inventory={i['id']:dict(i) for i in await c.execute_fetchall('SELECT * FROM inventory')}
            after=dict((await c.execute_fetchall('SELECT * FROM item_catalog WHERE id=?',(original['id'],)))[0])
            stock=(await c.execute_fetchall('SELECT stock,buy_price,sell_price FROM shop_stock WHERE item_id=?',(original['id'],)))[0]
        self.assertEqual(original,after,'Source catalogue row must remain byte-for-byte unchanged')
        self.assertNotEqual(inventory[selected]['item_id'],original['id'])
        self.assertEqual(inventory[selected]['equipped_slot'],'Торс')
        self.assertEqual(inventory[spare]['item_id'],original['id'])
        self.assertEqual(inventory[other]['item_id'],original['id'])
        self.assertEqual(inventory[other]['equipped_slot'],'Торс')
        self.assertEqual(tuple(stock),(3,222,111))


if __name__=='__main__':unittest.main()
