import unittest

from equipment_runtime import skill_xp_multiplier
from merchant_rules import runtime_warnings
from test_armor_runtime import armor


class EquipmentExperienceTests(unittest.IsolatedAsyncioTestCase):
    from test_shared_battles import SharedBattleTests as _Setup
    asyncSetUp=_Setup.asyncSetUp
    asyncTearDown=_Setup.asyncTearDown
    edit=_Setup.edit
    start=_Setup.start

    async def equip(self,cid):
        item=armor('UNIQUE_Iron_Armor_LieutenantsScarPittedBreastplate')
        await self.db.upsert_catalog([item])
        async with self.db.connect() as conn:
            ident=(await conn.execute_fetchall('SELECT id FROM item_catalog WHERE name=?',(item['name'],)))[0]['id']
            await conn.execute("INSERT INTO inventory(character_id,item_id,quantity,equipped_slot) VALUES(?,?,1,'Торс')",(cid,ident))
            await conn.commit()
        return item

    async def test_source_skill_mapping_and_no_duplicate_magic_staff_bonus(self):
        item=await self.equip(1)
        for name in ['Атлетика','Знания','Волшебный посох','Хитроумие','Управление огнём']:
            self.assertAlmostEqual(skill_xp_multiplier([item],name),1.1)
        self.assertEqual(skill_xp_multiplier([item],'Несуществующий навык'),1)
        self.assertFalse(runtime_warnings(item))

    async def test_actual_award_preserves_fractions_and_unequip_removes_bonus(self):
        await self.equip(1)
        for _ in range(10):xp=await self.db.add_skill_experience(1,'Атлетика',1)
        self.assertEqual(xp,11)
        async with self.db.connect() as conn:
            await conn.execute('UPDATE inventory SET equipped_slot=NULL WHERE character_id=1');await conn.commit()
        self.assertEqual(await self.db.add_skill_experience(1,'Атлетика',10),21)

    async def test_party_bonus_does_not_leak_into_lobby_or_other_characters(self):
        await self.equip(2)
        self.assertEqual(await self.db.add_skill_experience(1,'Атлетика',10),10)
        await self.start()
        self.assertEqual(await self.db.add_skill_experience(1,'Атлетика',10),21)
        self.assertEqual(await self.db.add_skill_experience(3,'Атлетика',10),10)


if __name__=='__main__':unittest.main()
