"""Explicit game-master accounts, restricted to configured game servers."""
import os


DEFAULT_MASTER_USER_IDS = (338639020664029190,)


def master_user_ids():
    # An explicitly empty setting disables default account grants.
    values = os.getenv('TYRANNY_MASTER_USER_IDS', ','.join(map(str, DEFAULT_MASTER_USER_IDS)))
    return frozenset(int(value) for value in values.split(',')
                     if value.strip().isdigit() and int(value) > 0)
