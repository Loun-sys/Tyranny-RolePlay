"""Sanitized inspection data built from the same source components as combat."""
import copy
import json
from functools import lru_cache
from pathlib import Path
from consumables import effect_text, profile
from item_effects import game_data, armor_by_type, equip_modifiers, SKILLS, DAMAGE_TYPES


@lru_cache(maxsize=1)
def inspection_source():
    return json.loads((Path(__file__).parent/'catalog/item_inspection_source.json').read_text(encoding='utf-8'))


def inspection_effect(effect):
    """Extra equipment-only ModifiedStat members from Assembly-CSharp.dll.

    This formats source rules; it does not pretend unsupported procs execute.
    """
    stat=effect.get('AffectsStat');value=float(effect.get('Value',0))
    extra=float(effect.get('ExtraValue',0));text=''
    percentages={104:'Задевания становятся промахами',107:'Попадания становятся критическими',74:'Критические попадания становятся обычными'}
    multipliers={153:'Сила заклинаний',170:'Получаемый урон критических попаданий',2169:'Урон ночью'}
    if stat==184:
        text=inspection_source()['guiStrings'].get(str(int(value)), '')
    elif stat in percentages:
        text=f'{percentages[stat]}: {(value*100 if abs(value)<=1 else value):+.4g}%'
    elif stat in multipliers:
        text=f'{multipliers[stat]}: {(value-1)*100:+.4g}%'
    elif stat==136:
        text=f'Урон при здоровье ниже {extra*100:g}%: {(value-1)*100:+.4g}%'
    elif stat==2137:
        text=f'Попадания становятся критическими против целей с менее {extra:g}% здоровья: {value:g}%'
    elif stat in {5,2098,2112}:
        label={5:'Точность дальних атак',2098:'Все навыки',2112:'Обнаружение ловушек'}[stat]
        text=f'{label}: {value:+g}'
    else:
        text=effect_text(effect)
    if text and (effect.get('ApplicationPrerequisites') or effect.get('TriggerAdjustment',{}).get('Type')):
        text='Условный эффект: '+text
    return text


def _unique(values):
    return list(dict.fromkeys(v.strip() for v in values if v and v.strip()))


def modifier_details(mod, prefab=''):
    lines = []
    graphs = mod.get('triggerGraphs', [])
    conditions = [g for g in graphs if g.get('stat') == 2057]
    condition_index = 0
    for field, label in [('StatusEffectsOnEquip', ''), ('StatusEffectsOnAttack', 'При попадании оружием'),
                         ('StatusEffectsOnCrit', 'При критическом попадании оружием'),
                         ('StatusEffectsOnLaunch', 'При применении')]:
        for raw in mod.get(field, []):
            effect = copy.deepcopy(raw)
            stat = effect.get('AffectsStat')
            if stat == 2057:
                graph = conditions[condition_index]['graph'] if condition_index < len(conditions) else []
                condition_index += 1
                name = next((g['localizedName'] for g in graph if g.get('localizedName')), '')
                if name:
                    lines.append(f'Урон по целям под воздействием «{name}»: {(float(effect.get("Value", 1))-1)*100:+.4g}%')
                    continue
            for key in ['AttackPrefab', 'AfflictionPrefab', 'AbilityPrefab']:
                if effect.get(key, {}).get('m_PathID'):
                    effect[key+'Graph'] = [n for g in graphs if g.get('stat') == stat for n in g['graph']]
            if stat in {2156, 2159, 2097}:
                graph = effect.get('AttackPrefabGraph', effect.get('AbilityPrefabGraph', []))
                nested = _unique(inspection_effect(s) for n in graph for s in n.get('StatusEffects', [])
                                 if s.get('AffectsStat') not in {2156, 2159})
                if nested:
                    trigger = 'При критическом попадании оружием' if stat == 2156 else 'При попадании оружием' if stat == 2159 else 'Дополнительная способность'
                    lines.append(trigger + ':')
                    if any('AttackDistance' in node and node.get('ValidTargets') == 12 for node in graph):
                        lines.append('Союзники (в области действия):')
                    lines.extend(nested)
                    for node in graph:
                        radius = node.get('BlastRadius') or node.get('AOERadius')
                        if radius:
                            lines.append(f'Радиус: {float(radius):g} м')
                    continue
            text = inspection_effect(effect)
            if text:
                lines.append((label + ': ' if label else '') + text)
    # Granted abilities and damage procs need not have a StatusEffectsOnEquip
    # record. Inspect their resolved source graphs instead of showing a name only.
    for resolved in graphs:
        if resolved.get('stat') not in {2097,2158}:
            continue
        graph=resolved['graph']
        name=next((n['localizedName'] for n in graph if n.get('localizedName')), '')
        if name:
            lines.append(('При получении критического попадания: ' if resolved['stat']==2158 else 'Способность: ')+name)
        for node in graph:
            damage=node.get('DamageData',{})
            if damage.get('Maximum'):
                lines.append(f"Урон: {damage.get('Minimum',0):g}–{damage['Maximum']:g} {DAMAGE_TYPES.get(damage.get('Type'),'')}")
            if damage.get('WeaponDamageMult'):
                lines.append(f"Урон оружия: {float(damage['WeaponDamageMult'])*100:g}%")
            if node.get('Tag') and node.get('localizedName'):
                lines.append(node['localizedName'])
            lines.extend(inspection_effect(s) for s in node.get('StatusEffects',[])
                         if s.get('AffectsStat') not in {2156,2158,2159})
            if node.get('BlastRadius'):
                lines.append(f"Радиус: {node['BlastRadius']:g} м")
    for proc in mod.get('DamageProcs',[]):
        kind=DAMAGE_TYPES.get(proc.get('Type'),{11:'Чистый',12:'Физический',13:'Случайный'}.get(proc.get('Type'),''))
        lines.append(f"Добавочный урон ({kind}): {float(proc['PercentOfBaseDamage']):g}% исходного урона")
    targets=inspection_source()['abilityTargets'].get(prefab+'|'+mod.get('localizedName',''), [])
    if targets and mod.get('AbilityModsOnEquip'):
        lines.append('Изменяет способности: '+', '.join(targets))
        for ability_mod in mod['AbilityModsOnEquip']:
            kind=ability_mod['Type'];value=float(ability_mod.get('Value',0))
            if kind==10:
                lines.append(f'Перезарядка способности: {(value-1)*100:+.4g}%')
            elif kind==2001:
                lines.append(f'Дистанция: {value:+g} м')
    return {'name': mod.get('localizedName', ''),
            'description': mod.get('localizedDescription', ''), 'effects': _unique(lines)}


def readout(item):
    game = game_data(item)
    armor = game.get('armor', {})
    skill = game.get('sourceItem', {}).get('SkillType')
    details = {'type': item.get('category', ''), 'skill': SKILLS.get(skill, ''),
               'modifiers': [modifier_details(m, game.get('prefab','')) for m in game.get('mods', [])]}
    if armor:
        category = {0: 'Легкая броня', 1: 'Тяжелая броня'}.get(armor.get('ArmorCategory'), 'Броня')
        material = {2:'Ткань',3:'Кожа',4:'Дерево',5:'Железо',6:'Бронза',7:'Сталь'}.get(armor.get('Material'), '')
        details['type'] = category + (f' ({material})' if material else '')
        groups = {}
        for damage_type, value in armor_by_type(item).items():
            groups.setdefault(value, []).append(damage_type)
        details['armorGroups'] = [{'value': value, 'types': names} for value, names in groups.items()]
    mods = equip_modifiers(item)
    details['bonuses'] = {name: round(value, 4) for name, value in mods['flat'].items() if value}
    details['percentBonuses'] = {name: round(value, 4) for name, value in mods['percent'].items() if value}
    details['multipliers'] = {name: round((value-1)*100, 4) for name, value in mods['multiply'].items() if value != 1}
    info = profile(item)
    if info:
        details['useEffects'] = _unique(effect_text(e) for e in info['effects'])
    return details
