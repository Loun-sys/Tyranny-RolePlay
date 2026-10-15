"""Canonical command scopes, safe migration and restart idempotence."""
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import discord
from bot import sync_application_commands
from discord import app_commands
from discord_servers import game_guild_ids


def remote(name, kind=discord.AppCommandType.chat_input):
    return SimpleNamespace(name=name, type=kind, delete=AsyncMock())


class DiscordCommandSyncTests(unittest.IsolatedAsyncioTestCase):
    def tree(self):
        commands = [SimpleNamespace(name=n) for n in
                    ['админ', 'регистрация', 'персонаж', 'удалить-персонажа', 'старт-боя', 'начать-бой', 'проверка', 'бой']]
        canonical = [remote(c.name) for c in commands if c.name != 'бой']
        tree = Mock(get_commands=Mock(return_value=commands),
                    sync=AsyncMock(return_value=canonical), fetch_commands=AsyncMock(return_value=[]))
        check = Mock(name='check', to_dict=Mock(return_value={'name': 'проверка', 'type': 1}))
        tree.get_command.return_value = check
        tree.client.application_id = 456
        tree._http.upsert_guild_command = AsyncMock(return_value={'id': '789', 'name': 'проверка'})
        return tree

    async def test_no_guild_only_publishes_the_allowlisted_global_set(self):
        tree = self.tree()
        result = await sync_application_commands(tree)
        self.assertEqual(len(result), 7)
        tree.remove_command.assert_called_once_with('бой')
        tree.sync.assert_awaited_once_with()
        tree.fetch_commands.assert_not_awaited()
        tree.copy_global_to.assert_not_called()
        tree.clear_commands.assert_not_called()

    async def test_cleanup_only_exact_remote_scope_and_type_duplicates(self):
        tree = self.tree()
        tree.sync.return_value = [c for c in tree.sync.return_value if c.name != 'проверка']
        duplicate = remote('регистрация')
        guild_only = remote('локальная-команда')
        guild_check = remote('проверка')
        context_menu = remote('регистрация', discord.AppCommandType.user)
        tree.fetch_commands.return_value = [duplicate, guild_only, context_menu, guild_check]
        await sync_application_commands(tree, 123)
        guild = tree.fetch_commands.await_args.kwargs['guild']
        self.assertEqual(guild.id, 123)
        duplicate.delete.assert_awaited_once_with()
        guild_only.delete.assert_not_awaited()
        context_menu.delete.assert_not_awaited()
        guild_check.delete.assert_not_awaited()
        tree._http.upsert_guild_command.assert_awaited_once_with(
            456, 123, payload={'name': 'проверка', 'type': 1})
        tree.add_command.assert_called_once_with(tree.get_command.return_value, guild=guild, override=True)
        tree.remove_command.assert_any_call('регистрация', guild=guild, type=discord.AppCommandType.chat_input)
        tree.sync.assert_awaited_once_with()
        tree.copy_global_to.assert_not_called()
        tree.clear_commands.assert_not_called()

    async def test_failed_global_publication_never_deletes_anything(self):
        tree = self.tree()
        tree.sync.side_effect = RuntimeError('unavailable')
        with self.assertRaises(RuntimeError):
            await sync_application_commands(tree, 123)
        tree.fetch_commands.assert_not_awaited()
        tree._http.upsert_guild_command.assert_awaited_once()

    async def test_failed_guild_publication_preserves_global_registration(self):
        tree = self.tree()
        tree._http.upsert_guild_command.side_effect = RuntimeError('unavailable')
        with self.assertRaises(RuntimeError):
            await sync_application_commands(tree, 123)
        tree.sync.assert_not_awaited()
        self.assertNotIn(('проверка',), [c.args for c in tree.remove_command.call_args_list])
        tree.add_command.assert_not_called()

    async def test_restart_finds_handler_in_guild_tree(self):
        tree = self.tree()
        check = tree.get_command.return_value
        tree.get_command.side_effect = [None, check]
        await sync_application_commands(tree, 123)
        self.assertEqual(tree.get_command.call_count, 2)
        self.assertEqual(tree.get_command.call_args.kwargs['guild'].id, 123)

    async def test_missing_handler_aborts_without_removing_remote_commands(self):
        tree = self.tree()
        tree.get_command.return_value = None
        with self.assertRaises(RuntimeError):
            await sync_application_commands(tree, 123)
        tree.sync.assert_not_awaited()
        tree._http.upsert_guild_command.assert_not_awaited()

    async def test_restart_with_no_duplicates_is_a_no_op_for_guild_scope(self):
        tree = self.tree()
        guild_only = remote('локальная-команда')
        tree.fetch_commands.return_value = [guild_only]
        await sync_application_commands(tree, 123)
        await sync_application_commands(tree, 123)
        guild_only.delete.assert_not_awaited()
        self.assertEqual(tree.sync.await_count, 2)
        tree.copy_global_to.assert_not_called()

    async def test_failed_cleanup_is_reported_not_silently_ignored(self):
        tree = self.tree()
        duplicate = remote('регистрация')
        duplicate.delete.side_effect = RuntimeError('unavailable')
        tree.fetch_commands.return_value = [duplicate]
        with self.assertRaises(RuntimeError):
            await sync_application_commands(tree, 123)

    async def test_real_tree_keeps_handlers_in_both_guilds_without_global_copy(self):
        async with discord.Client(intents=discord.Intents.none()) as client:
            client._connection.application_id = 456
            tree = app_commands.CommandTree(client)

            @tree.command(name='проверка', description='test')
            async def check(interaction: discord.Interaction):
                pass

            tree._http.upsert_guild_command = AsyncMock(return_value={'id': '789'})
            tree.sync = AsyncMock(return_value=[])
            tree.fetch_commands = AsyncMock(return_value=[remote('проверка'), remote('посторонняя')])
            await sync_application_commands(tree, [123, 980168851473985596, 123])
            self.assertIsNone(tree.get_command('проверка'))
            for guild_id in (123, 980168851473985596):
                self.assertIs(tree.get_command('проверка', guild=discord.Object(id=guild_id)), check)
            self.assertEqual(tree._http.upsert_guild_command.await_count, 2)
            await sync_application_commands(tree, [123, 980168851473985596])
            self.assertEqual(tree._http.upsert_guild_command.await_count, 4)
            for command in tree.fetch_commands.return_value:
                command.delete.assert_not_awaited()

    async def test_not_invited_server_does_not_break_existing_guild(self):
        tree = self.tree()
        tree.sync.return_value = [c for c in tree.sync.return_value if c.name != 'проверка']
        tree._http.upsert_guild_command.side_effect = [
            {'id': '789'}, discord.Forbidden(SimpleNamespace(status=403, reason='Forbidden'), 'Missing Access')]
        await sync_application_commands(tree, [123, 980168851473985596])
        self.assertEqual(tree.add_command.call_count, 2)
        tree.sync.assert_awaited_once()
        self.assertEqual(tree.fetch_commands.await_count, 1)
        self.assertEqual(tree.fetch_commands.await_args.kwargs['guild'].id, 123)

    async def test_server_configuration_preserves_primary_and_deduplicates(self):
        with patch.dict('os.environ', {'DISCORD_GUILD_ID': '123',
                                     'DISCORD_GUILD_IDS': '456,123, 980168851473985596,invalid,0'}):
            self.assertEqual(game_guild_ids(), (123, 456, 980168851473985596))


if __name__ == '__main__':
    unittest.main()
