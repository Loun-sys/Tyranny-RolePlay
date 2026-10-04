"""Original grip labels, occupied hands and free equipped bag slots."""
import unittest
from test_campaign import CampaignTests
from item_texts import catalog_texts,normalize_item_text

class InventoryToolsTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp=CampaignTests.asyncSetUp
    asyncTearDown=CampaignTests.asyncTearDown

    def test_every_source_weapon_has_consistent_grip_and_description(self):
        rows=list(catalog_texts()[0].values())
        weapons={'Одноручное оружие','Двуручное оружие','Парное оружие','Луки','Метательное оружие','Посохи','Щиты'}
        audited=0
        for source in rows:
            if source['category'] not in weapons:continue
            audited+=1;item=normalize_item_text(source)
            if item['category']=='Одноручное оружие':self.assertEqual(item['hands'],1,item['name'])
            if item['category'] in {'Двуручное оружие','Луки','Посохи'}:self.assertEqual(item['hands'],2,item['name'])
            self.assertIn('обе руки' if item['hands']==2 else 'одну руку',item['properties']['Хват'],item['name'])
        self.assertEqual(audited,318)

    async def test_two_handed_weapon_occupies_both_hands_and_equipment_is_free(self):
        async with self.db.connect() as conn:
            for name,category,hands,slot in [('Меч','Одноручное оружие',1,''),('Посох','Посохи',2,''),('Щит','Щиты',0,''),('Доспех','Броня',0,'Торс')]:
                cursor=await conn.execute('INSERT INTO item_catalog(name,category,hands,slot,weight) VALUES(?,?,?,?,1)',(name,category,hands,slot))
                await conn.execute('INSERT INTO inventory(character_id,item_id) VALUES(1,?)',(cursor.lastrowid,))
            await conn.commit()
        rows=await self.db.inventory(1);by_name={i['name']:i['inventory_id'] for i in rows}
        self.assertEqual((await self.db.inventory_capacity(1))['used'],4)
        self.assertTrue((await self.db.equip(1,by_name['Доспех'],'Торс'))[0])
        self.assertFalse((await self.db.equip(1,by_name['Доспех'],'Голова'))[0])
        self.assertTrue((await self.db.equip(1,by_name['Щит'],'Оружие I — левая рука'))[0])
        self.assertFalse((await self.db.equip(1,by_name['Щит'],'Оружие I — правая рука'))[0])
        self.assertEqual((await self.db.inventory_capacity(1))['used'],2)
        self.assertTrue((await self.db.equip(1,by_name['Посох'],'Оружие I — правая рука'))[0])
        inv=await self.db.inventory(1)
        self.assertIsNone(next(i['equipped_slot'] for i in inv if i['name']=='Щит'))
        self.assertFalse((await self.db.equip(1,by_name['Меч'],'Оружие I — левая рука'))[0])
        self.assertFalse((await self.db.equip(1,by_name['Посох'],'Оружие II — левая рука'))[0])
        self.assertTrue((await self.db.equip(1,by_name['Меч'],'Оружие II — левая рука'))[0])
        self.assertEqual((await self.db.inventory_capacity(1))['used'],1)
        self.assertTrue(await self.db.unequip(1,by_name['Посох']))
        self.assertEqual((await self.db.inventory_capacity(1))['used'],2)
