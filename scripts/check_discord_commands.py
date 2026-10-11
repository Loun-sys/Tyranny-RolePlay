"""Read-only audit of Discord command scopes; never connects to the gateway/DB."""
import asyncio
import json
import os
from pathlib import Path

import discord
from discord import app_commands
from dotenv import load_dotenv


async def main():
    load_dotenv(Path(__file__).resolve().parents[1] / '.env')
    token = os.getenv('DISCORD_TOKEN', '').strip()
    guild_id = int(os.getenv('DISCORD_GUILD_ID', '0') or 0)
    if not token:
        raise SystemExit('DISCORD_TOKEN is not configured; no requests made.')
    async with discord.Client(intents=discord.Intents.none()) as client:
        tree = app_commands.CommandTree(client)
        await client.login(token)
        global_commands = await tree.fetch_commands()
        guild_commands = await tree.fetch_commands(guild=discord.Object(id=guild_id)) if guild_id else []
        signatures = {(c.name, c.type) for c in global_commands}
        duplicates = [c.name for c in guild_commands if (c.name, c.type) in signatures]
        print(json.dumps({'application': client.user.name,
                          'global': sorted(c.name for c in global_commands),
                          'guild': sorted(c.name for c in guild_commands),
                          'duplicates': sorted(duplicates),
                          'guildChecked': bool(guild_id)}, ensure_ascii=False))
        if duplicates:
            raise SystemExit(1)


if __name__ == '__main__':
    asyncio.run(main())
