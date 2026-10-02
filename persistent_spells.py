"""Original field/aura lifetimes, adapted to discrete 10-second rounds."""
import math

PERSISTENT_SPELLS = {
    ('Огонь', 'Область влияния'): (20, 'fatigue', 'Усталость: −5 к точности'),
    ('Холод', 'Область влияния'): (12, 'frost', 'Штраф восстановления +10%, проверка падения'),
    ('Жизнь', 'Область влияния'): (14, 'restore', 'Максимум здоровья +20%, снимает отрицательное состояние'),
    ('Эмоции', 'Область влияния'): (12, 'sleep', 'Сон: цель не действует; атака пробуждает'),
    ('Жизнь', 'Ближнее действие'): (30, 'heal', 'Восстанавливает 10% максимального здоровья за раунд'),
    ('Истощение', 'Ближнее действие'): (30, 'decay', 'Броня −1 и Стойкость −1, накапливаются'),
    ('Огонь', 'Ближнее действие'): (30, 'fire', 'Огненный урон противникам в области'),
    ('Камень', 'Ближнее действие'): (30, 'stone', 'Дробящий урон противникам в области'),
    ('Рвение', 'Ближнее действие'): (30, 'guidance', 'Точность союзника +10'),
    ('Сила', 'Ближнее действие'): (30, 'stance', 'Сопротивление падению и отталкиванию'),
    ('Терратус', 'Ближнее действие'): (30, 'magic', 'Защита Магией союзника +10'),
    ('Эмоции', 'Ближнее действие'): (30, 'fear', 'Страх: точность противника −10'),
}
# Round-level magnitudes above are tabletop adaptations; original lifetimes are
# from spells.unity3d. Healing Aura original: 3% / 3s => 10% / 10s.


def persistent_profile(spell):
    entry = PERSISTENT_SPELLS.get((spell.get('core'), spell.get('expression')))
    if not entry:
        return None
    seconds, effect, description = entry
    tier = next((int(name.rsplit(' ', 1)[1]) if name.rsplit(' ', 1)[-1].isdigit() else 1
                 for name in spell.get('accents', []) if name.startswith('Вневременная форма')), 0)
    multiplier = (1, 1.25, 1.5, 1.75)[min(tier, 3)]
    return {'rounds': max(1, math.ceil(seconds * multiplier / 10)), 'effect': effect,
            'description': description, 'aura': spell.get('expression') == 'Ближнее действие'}
