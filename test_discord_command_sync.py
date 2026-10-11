"""One Discord scope, safe legacy cleanup, and restart idempotence."""
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import discord
from bot import sync_application_commands


def remote(name, kind=discord.AppCommandType.chat_input):
    return SimpleNamespace(name=name, type=kind, delete=AsyncMock())


class DiscordCommandSyncTests(unittest.IsolatedAsyncioTestCase):
    def tree(self):
        commands = [SimpleNamespace(name=n) for n in
                    ['админ', 'регистрация', 'персонаж', 'удалить-персонажа', 'старт-боя', 'начать-бой', 'бой']]
        canonical = [remote(c.name) for c in commands if c.name != 'бой']
        return Mock(get_commands=Mock(return_value=commands),
                    sync=AsyncMock(return_value=canonical), fetch_commands=AsyncMock(return_value=[]))

    async def test_no_guild_only_publishes_the_allowlisted_global_set(self):
        tree = self.tree()
        result = await sync_application_commands(tree)
        self.assertEqual(len(result), 6)
        tree.remove_command.assert_called_once_with('бой')
        tree.sync.assert_awaited_once_with()
        tree.fetch_commands.assert_not_awaited()
        tree.copy_global_to.assert_not_called()
        tree.clear_commands.assert_not_called()

    async def test_cleanup_only_exact_remote_scope_and_type_duplicates(self):
        tree = self.tree()
        duplicate = remote('регистрация')
        guild_only = remote('локальная-команда')
        context_menu = remote('регистрация', discord.AppCommandType.user)
        tree.fetch_commands.return_value = [duplicate, guild_only, context_menu]
        await sync_application_commands(tree, 123)
        guild = tree.fetch_commands.await_args.kwargs['guild']
        self.assertEqual(guild.id, 123)
        duplicate.delete.assert_awaited_once_with()
        guild_only.delete.assert_not_awaited()
        context_menu.delete.assert_not_awaited()
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


if __name__ == '__main__':
    unittest.main()
