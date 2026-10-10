"""Editor overrides never leak into the ordinary NPC-turn endpoint."""
import test_shared_battles as fixtures


class BattleEditorTests(fixtures.SharedBattleTests):
    async def test_switching_views_keeps_turn_round_and_spent_resources(self):
        await self.start()
        await self.edit(operation='turn',tokenId='npc_1')
        await self.edit(operation='act',mode='play',actorId='npc_1',kind='move',x=4,y=1)
        before=await self.store.get(self.ident,1,99)
        for _ in range(2):
            editor=await self.store.view(before,actor_id='pc_2',master=True)
            play=await self.store.view(before,master=True,play=True)
            self.assertEqual(editor['currentId'],'npc_1')
            self.assertEqual(play['controller']['actorId'],'npc_1')
            self.assertEqual(play['training']['turn']['movementRemaining'],4)
        after=await self.store.get(self.ident,1,99)
        self.assertEqual(before['state'],after['state'])
        self.assertEqual(before['revision'],after['revision'])

    async def test_team_editor_is_scoped_and_play_cannot_change_sides(self):
        await self.start()
        await self.edit(operation='turn',tokenId='npc_1')
        with self.assertRaisesRegex(ValueError,'Правки сцены'):
            await self.edit(operation='team',mode='play',actorId='npc_1',tokenId='npc_1',team='party')
        with self.assertRaises(ValueError):await self.edit(operation='team',tokenId='npc_1',team='invalid')
        row=await self.edit(operation='team',tokenId='npc_1',team='party')
        self.assertEqual(row['state']['tokens']['npc_1']['team'],'party')
        self.assertEqual(row['state']['currentId'],'npc_1')
        template=next(n for n in await self.npcs.list(1,99) if n['id']==self.npc)
        self.assertEqual(template['spec'].get('team'),None)

    async def test_editor_health_delta_clamps_but_absolute_invalid_health_rejected(self):
        row=await self.edit(operation='health',tokenId='npc_1',delta=-1000)
        self.assertEqual(row['state']['tokens']['npc_1']['health'],0)
        row=await self.edit(operation='health',tokenId='npc_1',delta=1000)
        self.assertEqual(row['state']['tokens']['npc_1']['health'],100)
        with self.assertRaises(ValueError):await self.edit(operation='health',tokenId='npc_1',health=101)

    async def test_refresh_turn_respects_modifiers_without_clearing_cooldowns(self):
        await self.start()
        await self.edit(operation='turn',tokenId='npc_1')
        row=await self.edit(operation='effect',tokenId='npc_1',effect='movement',value=1.5,rounds=2)
        row['state']['personal'].setdefault('npc_1',{}).update(action_available=False,movement_remaining=0,recovery_seconds=30,cooldowns={'ability:test':99})
        await self.store._save(row)
        row=await self.edit(operation='refresh_turn',tokenId='npc_1')
        resources=row['state']['personal']['npc_1']
        self.assertTrue(resources['action_available'])
        self.assertEqual(resources['movement_remaining'],7)
        self.assertEqual(resources['recovery_seconds'],0)
        self.assertEqual(resources['cooldowns'],{'ability:test':99})
