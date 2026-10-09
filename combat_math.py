"""Deterministic previews of the combat roll. Never consumes random numbers."""
import math


def roll_quality(score):
    return 0 if score <= 15 else 1 if score <= 50 else 2 if score <= 100 else 3


def percent_roll(value):
    # Runtime rolls an integer d100, so a fractional threshold is floored.
    return max(0, min(100, math.floor(value or 0))) / 100


def outcome_distribution(accuracy, defense, critical=0, graze_to_hit=0, conversions=None, reflections=None, spell_conversions=None):
    probabilities = [0.0] * 4
    for roll in range(1, 101):
        probabilities[roll_quality(roll + accuracy - defense)] += .01
    unchanged=probabilities.copy()
    promote = probabilities[2] * percent_roll(critical)
    probabilities[2] -= promote
    probabilities[3] += promote
    unchanged[2] *= 1-percent_roll(critical)
    promote = probabilities[1] * max(0, min(1, graze_to_hit))
    probabilities[1] -= promote
    probabilities[2] += promote
    unchanged[1] *= 1-max(0,min(1,graze_to_hit))
    for index, key in [(3, 'critToHit'), (2, 'hitToGraze'), (1, 'grazeToMiss')]:
        converted = probabilities[index] * percent_roll((conversions or {}).get(key, 0))
        probabilities[index] -= converted
        probabilities[index - 1] += converted
        unchanged[index] *= 1-percent_roll((conversions or {}).get(key,0))
    # Already converted attacks cannot undergo a second spell-specific conversion.
    for index,key in [(3,'critToHit'),(2,'hitToGraze')]:
        converted=unchanged[index]*percent_roll((spell_conversions or {}).get(key,0))
        probabilities[index]-=converted
        probabilities[index-1]+=converted
    reflected = 0
    for index in range(1, 4):
        amount = probabilities[index] * max(0, min(1, (reflections or {}).get(index, 0)))
        probabilities[index] -= amount
        reflected += amount
    return {'miss': probabilities[0], 'graze': probabilities[1], 'hit': probabilities[2],
            'critical': probabilities[3], 'reflected': reflected}
