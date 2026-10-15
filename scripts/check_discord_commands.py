"""Read-only audit of Discord command scopes; never connects to the gateway/DB."""
import asyncio
import json
import os
import sys
from pathlib import Path

import discord
from discord import app_commands
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from discord_servers import game_guild_ids


async def main():
    load_dotenv(Path(__file__).resolve().parents[1] / '.env')
    token = os.getenv('DISCORD_TOKEN', '').strip()
    guild_ids = game_guild_ids()
    if not token:
        raise SystemExit('DISCORD_TOKEN is not configured; no requests made.')
    async with discord.Client(intents=discord.Intents.none()) as client:
        tree = app_commands.CommandTree(client)
        await client.login(token)
        global_commands = await tree.fetch_commands()
        signatures = {(c.name, c.type) for c in global_commands}
        guilds, failed = [], False
        for guild_id in guild_ids:
            try:
                guild_commands = await tree.fetch_commands(guild=discord.Object(id=guild_id))
            except (discord.Forbidden, discord.NotFound):
                guilds.append({'id': str(guild_id), 'status': 'not_invited_or_no_access'})
                continue
            duplicates = [c.name for c in guild_commands if (c.name, c.type) in signatures]
            check_ready = False
            for command in guild_commands:
                if command.name != 'проверка' or command.type != discord.AppCommandType.chat_input:
                    continue
                modifier = next((option for option in command.to_dict().get('options', [])
                                 if option['name'] == 'модификатор'), {})
                check_ready = modifier.get('min_value') == -1000 and modifier.get('max_value') == 1000
            guilds.append({'id': str(guild_id), 'commands': sorted(c.name for c in guild_commands),
                           'duplicates': sorted(duplicates), 'checkReady': check_ready})
            failed = failed or bool(duplicates) or not check_ready
        print(json.dumps({'application': client.user.name,
                          'global': sorted(c.name for c in global_commands),
                          'guilds': guilds}, ensure_ascii=False))
        if failed:
            raise SystemExit(1)


if __name__ == '__main__':
    asyncio.run(main())
