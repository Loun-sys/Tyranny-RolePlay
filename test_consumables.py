import copy
import json
import unittest
from unittest.mock import patch
from item_texts import catalog_texts
from consumables import profile,apply,pulse,virtual_equipment,crit_effects
from registration_api import _derived
from training_combat import TrainingSession
from test_campaign import CampaignTests

def item(prefab):return copy.deepcopy(catalog_texts()[0][prefab])
def character():return {'name':'Испытатель','level':1,'health':50,'health_max':100,'attributes':dict.fromkeys(['Сила','Искусность','Быстрота','Живучесть','Смекалка','Стойкость'],10),'skills':{'Безоружный бой':{'value':20},'Управление огнём':{'value':20},'Парирование':{'value':20}},'talents':[]}

class ConsumableRulesTests(unittest.TestCase):
    def test_consumable_multipliers_affect_derived_stats(self):
        states={str(stat):{'name':'Эффект','consumable':True,'until':6,'source':{'AffectsStat':stat,'Value':value}}
                for stat,value in [(188,.95),(169,1.5),(181,1.1),(2000,.9)]}
        derived=_derived(character(),virtual_equipment(states,1))
        self.assertAlmostEqual(derived['incomingDamageMultiplier'],.95)
        self.assertAlmostEqual(derived['healingMultiplier'],1.5)
        self.assertEqual(derived['healthMax'],110)
        self.assertAlmostEqual(derived['cooldownMultiplier'],.9)

    def test_every_consumable_has_effects_and_no_junk_is_consumable(self):
        rows=list(catalog_texts()[0].values());usable=[i for i in rows if profile(i)]
        self.assertEqual(len(usable),55)
        self.assertTrue(all(profile(i)['description'] for i in usable))
        for i in rows:
            if i['category'] in {'Расходуемые предметы','Зелья','Еда'}:self.assertIsNotNone(profile(i),i['name'])
        for prefab in ['Gem_Ruby','Junk_Tooth','Quest_Poison']:
            self.assertEqual(item(prefab)['category'],'Разное')
            self.assertIsNone(profile(item(prefab)))
    def test_healing_percent_not_generic_flat_heal(self):
        self.assertEqual(apply(item('IT_CONS_HealingPotionCommon'),{},1,10,100),35)
        self.assertEqual(apply(item('IT_CONS_HealingPotionSuperior'),{},1,10,100),85)
    def test_six_rounds_buff_and_expiration(self):
        states={};apply(item('IT_CONS_PotionOfHeroes'),states,1,50,100)
        c=character();d=_derived(c,virtual_equipment(states,1))
        self.assertEqual(d['effectiveAttributes']['Сила'],12)
        self.assertEqual(_derived(c,virtual_equipment(states,6))['effectiveAttributes']['Сила'],12)
        self.assertEqual(_derived(c,virtual_equipment(states,7))['effectiveAttributes']['Сила'],10)
    def test_typed_armor_and_all_magic_skills(self):
        states={};apply(item('IT_CONS_PotionOfArmor'),states,1,50,100)
        d=_derived(character(),virtual_equipment(states,1))
        self.assertEqual(d['armor'],0);self.assertEqual(d['armorByType']['Рубящий'],2)
        apply(item('IT_CONS_VialOfMentalPower'),states,1,50,100)
        self.assertEqual(_derived(character(),virtual_equipment(states,1))['effectiveSkills']['Управление огнём'],30)
    def test_regeneration_15_seconds_two_rounds_without_extra_ticks(self):
        states={};hp=apply(item('IT_CONS_DireRemedy'),states,1,1,100)
        hp=pulse(states,2,hp,100);self.assertEqual(hp,41)
        hp=pulse(states,3,hp,100);self.assertEqual(hp,61)
        self.assertEqual(pulse(states,4,hp,100),61)
    def test_poison_comes_from_resolved_game_attack_not_self_healing(self):
        states={};self.assertEqual(apply(item('IT_CONS_ScarletPoison'),states,1,50,100),50)
        e=crit_effects(states)
        self.assertTrue(any(s['AffectsStat']==25 for s in e))
        self.assertEqual(e[0]['Duration'],30)
    def test_training_simulates_stock_without_changing_owned_quantity(self):
        i=item('IT_CONS_PotionOfHeroes');i.update(inventory_id=1,quantity=1)
        session=TrainingSession(1);session.consumable_inventory=[i];c=character();d=_derived(c,[])
        session.view(c,d,[],2)
        session.act({'kind':'item','name':'1'},c,d,[],2)
        self.assertTrue(session.action_available);self.assertEqual(i['quantity'],1)
        self.assertEqual(len(session.conditions['player']),7)

class ConsumableStoreTests(CampaignTests):
    async def test_atomic_consumption_and_permanent_elixir(self):
        from consumable_store import use,states
        from database import SCHEMA
        await self.db.upsert_catalog([item('IT_CONS_ElixirOfMight'),item('IT_CONS_HealingPotionCommon')])
        async with self.db.connect() as c:
            await c.execute("INSERT INTO attributes(character_id,name,value) VALUES(1,'Сила',10)")
            await c.execute('UPDATE characters SET health=10,health_max=100 WHERE id=1');await c.commit()
        await self.db.admin_give_item(1,'Эликсир силы',1)
        row=next(i for i in await self.db.inventory(1) if i['name']=='Эликсир силы')
        await use(self.db,1,row['inventory_id'])
        async with self.db.connect() as c:
            self.assertEqual((await c.execute_fetchall('SELECT value FROM attributes WHERE character_id=1'))[0]['value'],11)
        self.assertEqual(await states(self.db,1),{})
        with self.assertRaises(ValueError):await use(self.db,1,row['inventory_id'])
        await self.db.admin_give_item(1,'Слабое зелье исцеления',1)
        row=next(i for i in await self.db.inventory(1) if i['name']=='Слабое зелье исцеления')
        await use(self.db,1,row['inventory_id'])
        self.assertEqual((await self.db.get_character_by_id(1))['health'],35)

if __name__=='__main__':unittest.main()
