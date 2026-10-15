"""Configured game servers; legacy single-server settings remain supported."""
import os


DEFAULT_GAME_GUILD_IDS = (980168851473985596,)


def game_guild_ids():
    values = [os.getenv('DISCORD_GUILD_ID', ''),
              *os.getenv('DISCORD_GUILD_IDS', '').split(','), *DEFAULT_GAME_GUILD_IDS]
    return tuple(dict.fromkeys(int(value) for value in values
                               if str(value).strip().isdigit() and int(value) > 0))
