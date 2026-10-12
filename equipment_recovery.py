"""Rebalance each item's recovery; preserve fractional equipment totals.

Imported/source values stay unchanged. Recovery extends cooldowns and never
locks the actor's next action.
"""
from decimal import Decimal, ROUND_HALF_UP
import re

# The current item readouts already used 1.5 times the imported source value.
# Increase those current values by another 50%, without mutating source data.
ITEM_RECOVERY_MULTIPLIER = Decimal('1.5') * Decimal('1.5')


def item_recovery(item):
    value = Decimal(str(item.get('recovery') or 0)) * ITEM_RECOVERY_MULTIPLIER
    return float(value.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP))


def recovery_rounds(value):
    """Normalize fractional rounds, never ceil an item or equipment total."""
    return max(0, round(float(value or 0), 6))


def finalize_recovery(derived):
    """Call after all equipment/conditional modifiers, before showing totals."""
    raw = recovery_rounds(derived['attack'].get('recovery', 0))
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
    total = round(base + extra, 6)
    result.update(cooldownBase=base, equipmentRecovery=extra, cooldown=total)
    if 'details' in action:
        number = lambda value: f'{value:g}'.replace('.', ',')
        result['details'] = re.sub(
            r'Перезарядка: \d+(?:[.,]\d+)? раундов(?: \(база \d+(?:[.,]\d+)? \+ восстановление \d+(?:[.,]\d+)?\))?',
            f'Перезарядка: {number(total)} раундов' +
            (f' (база {number(base)} + восстановление {number(extra)})' if extra else ''),
            action['details'], count=1)
    return result
