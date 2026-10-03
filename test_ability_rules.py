import copy,unittest,asyncio
from unittest.mock import patch,AsyncMock
from ability_rules import resolve,profile,owned_actions,weapon_requirement,library
from training_combat import TrainingSession
from test_consumables import character,item
from registration_api import _derived,training_action

class AbilityResponseTests(unittest.IsolatedAsyncioTestCase):
    async def test_potion_modifiers_visible_in_same_response(self):
        from types import SimpleNamespace
        from consumables import virtual_equipment
        c=character();s=TrainingSession(1);i=item('IT_CONS_PotionOfHeroes');i.update(inventory_id=1,quantity=1);s.consumable_inventory=[i]
        s.view(c,_derived(c,[]),[],2)
        async def snapshot(*args):return c,[i]+virtual_equipment(s.conditions.get('player',{}),s.round_number),[],{'weaponSets':2}
        request=SimpleNamespace(app={'training_locks':{},'training_sessions':{1:s}})
        with patch('registration_api._portal_payload',new=AsyncMock(return_value=(1,{'kind':'item','name':'1'}))),patch('registration_api._training_character',new=snapshot):
            response=await training_action(request)
        import json
        result=json.loads(response.body)['training']
        self.assertTrue(result['turn']['actionAvailable']);self.assertEqual(result['derived']['effectiveAttributes']['Сила'],12)
        self.assertGreater(result['derived']['defenses']['Выносливость'],20)

class AbilityRulesTests(unittest.TestCase):
    def test_source_cooldowns_and_affliction_edge_duration(self):
        a=profile(resolve('Abl_PC_Defense_ShieldSlam'))
        self.assertEqual(a['name'],'Удар щитом');self.assertEqual(a['cooldown'],3)
        self.assertEqual((a['damageMin'],a['damageMax']),(10,15))
        effect=next(s for s in a['effects'] if s.get('AffectsStat')==2000)
        self.assertEqual(effect['Duration'],20);self.assertEqual(effect['side'],'target')
    def test_source_cone_and_skill_and_weapon_restriction(self):
        a=profile(resolve('Abl_PC_Cleave'));self.assertEqual(a['targeting'],'cone');self.assertEqual(a['angle'],210)
        a=profile(resolve('Abl_PC_Defense_ShieldSlam'),{'effectiveSkills':{'Атлетика':45},'attack':{'accuracy':7}})
        self.assertEqual(a['accuracy'],45);self.assertTrue(weapon_requirement(a,[]))
        self.assertFalse(weapon_requirement(a,[{'category':'Щиты','equipped_slot':'Оружие I — левая рука'}]))
    def test_extra_player_abilities_are_exposed_by_source_not_whitelist(self):
        a=next(a for a in library() if '_PC_' in a['key'] and not a['passive'] and 'HeadStrike' in a['key'])
        rows=owned_actions([{'prefab':a['key'],'name':'Старое имя'}],{'attack':{'accuracy':30}})
        self.assertEqual(rows[0]['key'],a['key']);self.assertEqual(rows[0]['name'],a['name'])
    def test_sunder_actually_changes_all_three_physical_armor_types(self):
        c=character();c['talents']=[{'name':'Раскол'}];d=_derived(c,[]);s=TrainingSession(1)
        s.player_position=(9,4)
        with patch('training_combat.random.randint',return_value=100):s.act({'kind':'ability','name':'Раскол'},c,d,[],2)
        from consumables import virtual_equipment
        from item_effects import armor_by_type
        effects=virtual_equipment(s.conditions['dummy'],s.round_number)
        for damage in ('Рубящий','Дробящий','Колющий'):
            self.assertEqual(sum(armor_by_type(i)[damage] for i in effects),-5)
    def test_flurry_has_two_separate_attack_rolls(self):
        c=character();c['talents']=[{'name':'Шквал ударов'}];s=TrainingSession(1);s.player_position=(9,4)
        with patch('training_combat.random.randint',return_value=100):s.act({'kind':'ability','name':'Шквал ударов'},c,_derived(c,[]),[],2)
        self.assertEqual(s.attacks,2)
    def test_self_consumable_free_even_after_action_spent(self):
        c=character();s=TrainingSession(1);i=item('IT_CONS_PotionOfHeroes');i.update(inventory_id=1,quantity=1);s.consumable_inventory=[i]
        s.view(c,_derived(c,[]),[],2);s.action_available=False
        result=s.act({'kind':'item','name':'1','targetId':'player'},c,_derived(c,[]),[],2)
        self.assertFalse(s.action_available);self.assertEqual(i['quantity'],1)
        self.assertIn('Предмет',result['result'])
    def test_neighbor_consumable_spends_action_and_heals_target(self):
        c=character();s=TrainingSession(1);i=item('IT_CONS_HealingPotionCommon');i.update(inventory_id=1,quantity=1);s.consumable_inventory=[i]
        s.view(c,_derived(c,[]),[],2);s.player_position=(9,4);s.target_healths['dummy']=20
        s.act({'kind':'item','name':'1','targetId':'dummy'},c,_derived(c,[]),[],2)
        self.assertFalse(s.action_available);self.assertGreater(s.target_healths['dummy'],20)
        self.assertEqual(s.player_health,c['health'])
    def test_distant_consumable_rejected_without_consumption(self):
        c=character();s=TrainingSession(1);i=item('IT_CONS_HealingPotionCommon');i.update(inventory_id=1,quantity=1);s.consumable_inventory=[i]
        s.view(c,_derived(c,[]),[],2)
        with self.assertRaises(ValueError):s.act({'kind':'item','name':'1','targetId':'dummy'},c,_derived(c,[]),[],2)
        self.assertTrue(s.action_available);self.assertFalse(getattr(s,'consumable_used',{}))
    def test_neighbor_consumable_requires_unspent_action(self):
        c=character();s=TrainingSession(1);i=item('IT_CONS_HealingPotionCommon');i.update(inventory_id=1,quantity=1);s.consumable_inventory=[i]
        s.view(c,_derived(c,[]),[],2);s.player_position=(9,4);s.target_healths['dummy']=20;s.action_available=False
        with self.assertRaises(ValueError):s.act({'kind':'item','name':'1','targetId':'dummy'},c,_derived(c,[]),[],2)
        self.assertEqual(s.target_healths['dummy'],20);self.assertFalse(getattr(s,'consumable_used',{}))
    def test_npc_master_uses_source_executor_and_separate_action_budget(self):
        from npc_store import ability_library
        a=next(a for a in ability_library() if a['key']=='ABL_DIS_BloodBound_DisablingKick')
        c=character();s=TrainingSession(1);s.view(c,_derived(c,[]),[],2)
        s.targets['dummy'].update(kind='npc',abilities=[a],attributes=c['attributes'],skills={'Атлетика':80},attack={'accuracy':80,'damageMin':4,'damageMax':8,'range':1})
        s.target_positions['dummy']=(3,4);before=s.player_health
        with patch('training_combat.random.randint',return_value=100):s.master_npc_ability('dummy',a['key'],'player',c,_derived(c,[]))
        self.assertLess(s.player_health,before);self.assertTrue(s.action_available)
        with self.assertRaises(ValueError):s.master_npc_ability('dummy',a['key'],'player',c,_derived(c,[]))
    def test_unsupported_ability_cannot_report_success(self):
        c=character();a=next(a for a in owned_actions([{'key':a['key']} for a in library()],_derived(c,[])) if not a['supported'])
        c['talents']=[{'key':a['key']}];s=TrainingSession(1)
        with self.assertRaises(ValueError):s.act({'kind':'ability','name':a['name']},c,_derived(c,[]),[],2)
        self.assertTrue(s.action_available)

    def test_discord_uses_same_source_sunder_and_keeps_custom_npc_armor(self):
        from combat import Combatant,CombatSession
        from ability_combat import execute
        c=character();actor=Combatant('p','Игрок','players',100,100,character_id=1,attributes=c['attributes'],skills={'Безоружный бой':80},talents=[{'name':'Раскол'}],x=9,y=4)
        target=Combatant('e','НПС','enemies',100,100,armor=4,x=10,y=4)
        session=CombatSession(1,1,1,None);session.combatants={'p':actor,'e':target}
        with patch('training_combat.random.randint',return_value=100):execute(session,actor,target,actor.talents[0])
        self.assertEqual(target.armor,4);self.assertEqual(target.equipment_armor_by_type['Дробящий'],-1)
        self.assertTrue(target.consumable_states)

if __name__=='__main__':unittest.main()
