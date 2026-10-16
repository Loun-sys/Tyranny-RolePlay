import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import discord
import bot
from discord_permissions import master_user_ids


OWNER = 338639020664029190
GUILDS = (1553818433844551760, 980168851473985596)


def interaction(user_id=OWNER, guild_id=GUILDS[0], *, administrator=False, manage_guild=False, roles=()):
    member = Mock(spec=discord.Member)
    member.id = user_id
    member.guild = SimpleNamespace(id=guild_id)
    member.guild_permissions = SimpleNamespace(administrator=administrator, manage_guild=manage_guild)
    member.roles = [SimpleNamespace(id=role) for role in roles]
    return SimpleNamespace(user=member, guild_id=guild_id)


class MasterAccessTests(unittest.TestCase):
    def setUp(self):
        for name, value in [('MASTER_USER_IDS', frozenset({OWNER})), ('GAME_GUILD_IDS', GUILDS), ('MASTER_ROLE_IDS', {42})]:
            patcher = patch.object(bot, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_requested_account_can_open_both_game_servers(self):
        for guild in GUILDS:
            self.assertTrue(bot.is_master(interaction(guild_id=guild)))

    def test_other_account_is_not_granted_access(self):
        self.assertFalse(bot.is_master(interaction(user_id=OWNER + 1)))

    def test_personal_grant_does_not_extend_to_other_servers(self):
        self.assertFalse(bot.is_master(interaction(guild_id=123)))

    def test_direct_messages_and_mismatched_membership_are_rejected(self):
        self.assertFalse(bot.is_master(interaction(guild_id=None)))
        request = interaction()
        request.user = Mock(spec=discord.User, id=OWNER)
        self.assertFalse(bot.is_master(request))
        request = interaction()
        request.user.guild.id = GUILDS[1]
        self.assertFalse(bot.is_master(request))

    def test_existing_discord_administrators_managers_and_master_roles_keep_access(self):
        for options in [{'administrator': True}, {'manage_guild': True}, {'roles': [42]}]:
            self.assertTrue(bot.is_master(interaction(user_id=123, **options)))
        self.assertFalse(bot.is_master(interaction(user_id=123, roles=[43])))

    def test_explicit_empty_allowlist_can_revoke_default_grant(self):
        with patch.object(bot, 'MASTER_USER_IDS', frozenset()):
            self.assertFalse(bot.is_master(interaction()))

    def test_default_config_and_safe_custom_parsing(self):
        with patch.dict('os.environ', {}, clear=True):
            self.assertEqual(master_user_ids(), {OWNER})
        with patch.dict('os.environ', {'TYRANNY_MASTER_USER_IDS': ''}):
            self.assertFalse(master_user_ids())
        with patch.dict('os.environ', {'TYRANNY_MASTER_USER_IDS': '123, 456,123,0,-1,invalid'}):
            self.assertEqual(master_user_ids(), {123, 456})


class MasterCommandTests(unittest.IsolatedAsyncioTestCase):
    setUp = MasterAccessTests.setUp

    async def test_admin_command_issues_private_link_for_this_user_and_server_only(self):
        request = interaction()
        request.response = SimpleNamespace(send_message=AsyncMock())
        database = SimpleNamespace(create_admin_token=AsyncMock(return_value='test-only-access'))
        with patch.object(bot.bot, 'db', database), patch.object(bot, 'admin_site_url', return_value='https://example.invalid/admin.html'), patch.dict('os.environ', {'TYRANNY_PUBLIC_API_URL': 'https://example.invalid/api'}):
            await bot.admin_command.callback(request)
        database.create_admin_token.assert_awaited_once_with(GUILDS[0], OWNER)
        sent = request.response.send_message.await_args.kwargs
        self.assertTrue(sent['ephemeral'])
        self.assertEqual(sent['view'].children[0].label, 'Открыть мастерскую')
        self.assertIn('#token=test-only-access', sent['view'].children[0].url)

    async def test_unlisted_account_never_gets_an_admin_token(self):
        request = interaction(user_id=OWNER + 1)
        request.response = SimpleNamespace(send_message=AsyncMock())
        database = SimpleNamespace(create_admin_token=AsyncMock())
        with patch.object(bot.bot, 'db', database):
            await bot.admin_command.callback(request)
        database.create_admin_token.assert_not_awaited()
        self.assertTrue(request.response.send_message.await_args.kwargs['ephemeral'])


if __name__ == '__main__':
    unittest.main()
