"""Adapt item recovery once; round the active equipment sum, not each item.

Imported/source values stay unchanged. Recovery extends cooldowns and never
locks the actor's next action.
"""
import math
import re

ITEM_RECOVERY_MULTIPLIER = 1.5


def item_recovery(item):
    return round(float(item.get('recovery') or 0) * ITEM_RECOVERY_MULTIPLIER, 6)


def recovery_rounds(value):
    return max(0, math.ceil(round(float(value or 0), 6)))


def finalize_recovery(derived):
    """Call after all equipment/conditional modifiers, before showing totals."""
    raw = max(0, derived['attack'].get('recovery', 0))
    derived['equipmentRecoveryRaw'] = raw
    derived['equipmentRecovery'] = recovery_rounds(raw)
    derived['attack']['recovery'] = derived['equipmentRecovery']
    return derived


def cooldown_recovery(derived, adjustment_seconds=0):
    raw = derived.get('equipmentRecoveryRaw', derived.get('equipmentRecovery',
                      derived.get('attack', {}).get('recovery', 0)))
    raw += derived.get('weaponSwitchRecoverySeconds', 0) / 10
    return recovery_rounds(raw + adjustment_seconds / 10)


def with_recovery(action, derived):
    """Idempotent: previews and execution can reuse/recalculate one profile."""
    result = dict(action)
    if action.get('song') or action.get('modal') or action.get('passive') or action.get('oncePerBattle'):
        return result
    base = action.get('cooldownBase', action.get('cooldown', 0))
    extra = cooldown_recovery(derived, action.get('recoveryAdjustmentSeconds', 0))
    result.update(cooldownBase=base, equipmentRecovery=extra, cooldown=base + extra)
    if 'details' in action:
        result['details'] = re.sub(
            r'Перезарядка: \d+ раундов(?: \(база \d+ \+ восстановление \d+\))?',
            f'Перезарядка: {base + extra} раундов' +
            (f' (база {base} + восстановление {extra})' if extra else ''),
            action['details'], count=1)
    return result
