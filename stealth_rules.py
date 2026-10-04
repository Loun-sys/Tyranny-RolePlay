"""Tyranny suspicion, adapted to a 10-second grid round (see docs/stealth-qa.md)."""
import math
from functools import lru_cache
import json
from pathlib import Path

ROUND_SECONDS = 10.0
INVESTIGATING = 100.0
DETECTED = 200.0
BASE_RATE = 20.0
DECAY_RATE = 15.0
DECAY_DELAY = .75
PERCEPTION_TYPES = {0: (9.0, 1.75), 1: (6.0, 1.25), 2: (5.0, 1.0),
                    3: (3.0, .5), 4: (1.0, .1)}


@lru_cache(maxsize=1)
def game_perception():
    return json.loads((Path(__file__).parent / 'catalog/npc_perception.json').read_text(encoding='utf-8'))


def observer_profile(npc):
    original = game_perception().get(npc.get('sourceKey') or npc.get('key'), {})
    kind = int(npc.get('perceptionType', original.get('perceptionType', 2)))
    radius, multiplier = PERCEPTION_TYPES.get(kind, PERCEPTION_TYPES[2])
    scale = float(npc.get('perceptionDistanceMultiplier', original.get('perceptionDistanceMultiplier', 1)))
    return {'radius': radius * max(.1, scale),
            'perception': (20 + max(1, int(npc.get('level', 1))) * 4) * multiplier,
            'type': kind}


def detection_rate(distance, radius, perception, skill):
    """AIController.InvestigationSuspicionRate, normal difficulty, two .5m tokens.

    The original combat-mode distance override is intentionally not used: the
    tabletop action must remain useful in combat. Contact still detects instantly.
    """
    if distance <= 1.0:
        return math.inf
    if distance >= radius:
        return 0.0
    fraction = min(1.0, max(0.0, (distance - 1) / max(1, radius - 1)))
    raw = min(3.0, max(.1, max(0, skill) / max(.1, perception)))
    detection = 2 - raw if raw < 1 else 1 / raw
    return BASE_RATE * detection * (2 - 1.5 * fraction)


def advance_memory(memory, seconds, rate=0):
    """Pure deterministic update; suspicion and the .75s decay grace are per foe."""
    value = float(memory.get('value', 0))
    idle = float(memory.get('idle', 0))
    seconds = max(0, seconds)
    if rate > 0:
        value = DETECTED if math.isinf(rate) else min(DETECTED, value + rate * seconds)
        idle = 0
    else:
        decay_seconds = max(0, idle + seconds - DECAY_DELAY) - max(0, idle - DECAY_DELAY)
        value = max(0, value - DECAY_RATE * decay_seconds)
        idle += seconds
    return {'value': value, 'idle': idle}
