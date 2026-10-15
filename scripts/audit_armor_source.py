"""Read-only comparison of every imported armor prefab and all quality levels."""
import copy
import csv
import io
import json
import sys
from pathlib import Path

import UnityPy
from game_asset_index import GameIndex

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def audit():
    from crafting import library, normalize_quality, quality_info
    from item_effects import armor_by_type, component_bonuses, game_data
    from item_texts import catalog_texts
    index = GameIndex()
    originals = {}
    for (asset, pid), tree in index.trees.items():
        if 'Value' not in tree or 'DisplayName' not in tree:
            continue
        obj = index.assets[asset].objects[pid]
        originals[index.name(obj)] = (obj,tree,[
            {k: copy.deepcopy(v) for k, v in t.items() if not k.startswith('m_')}
            for _, t in index.components(obj)])
    tables = {}
    for obj in UnityPy.load('C:/Games/Tyranny/Data/resources.assets').objects:
        if obj.type.name != 'TextAsset':
            continue
        text = obj.read()
        if text.m_Name == 'QualityScalingArmor':
            rows = list(csv.reader(io.StringIO(text.m_Script)))
            tables = {r[0]: {k: float(v) for k, v in zip(rows[0][1:], r[1:])}
                      for r in rows[1:] if r}
    errors = []
    checked = levels = 0
    absent_levels = []
    fields = {'Рубящий': 'Slashing', 'Дробящий': 'Crushing', 'Колющий': 'Piercing',
              'Огненный': 'Burning', 'Ледяной': 'Freezing', 'Электрический': 'Shocking',
              'Разъедающий': 'Corroding', 'Магический': 'Arcane'}
    for prefab, item in catalog_texts()[0].items():
        if item['category'] != 'Броня':
            continue
        checked += 1
        entry = originals.get(prefab)
        source = entry[2] if entry else []
        game = game_data(item)
        armor = next((t for t in source if 'DamageThreshold' in t), {})
        if not source:
            errors.append((prefab, 'missing installed prefab'))
            continue
        obj,source_item,_=entry
        original_mods=[index.tree(index.resolve(obj,p)) for p in source_item.get('ItemMods',[])]
        original_mods=[m for m in original_mods if m]
        actual_mods=game.get('mods',[])
        if len(original_mods)!=len(actual_mods):errors.append((prefab,'modifier count differs'))
        def source_values(value):
            if isinstance(value,dict):
                return {k:source_values(v) for k,v in value.items() if k!='localizedDescription'}
            if isinstance(value,list):return [source_values(v) for v in value]
            return value
        for original,actual in zip(original_mods,actual_mods):
            for field,value in original.items():
                if not field.startswith('m_') and source_values(value)!=source_values(actual.get(field)):
                    errors.append((prefab,'modifier field differs',field))
        effects=source_item.get('StatusEffects',[])+[e for m in original_mods for e in m.get('StatusEffectsOnEquip',[])]
        if source_values(effects)!=source_values(game.get('statusEffects',[])):
            errors.append((prefab,'on-equip effects differ'))
        components = [t for t in source if any(k in t for k in
            ['DamageThreshold', 'ParryBonus', 'AthleticsBonus', 'BaseParryBonus',
             'AccuracyBonus', 'MeleeDamageBonus', 'DeflectionBonus', 'DamageData'])]
        quality = next((t for t in source if t.get('QualityScaleID')), None)
        q = quality_info(item)
        if q and quality and (q['id'], q['level']) != (quality['QualityScaleID'], quality['QualityScaleLevel']):
            errors.append((prefab, 'quality identity differs'))
        for level in range(1, 6) if q else [None]:
            normalized = normalize_quality(copy.deepcopy(item), level) if q else item
            levels += 1
            suffix = {1: 'Common', 2: 'Fine', 3: 'Superior', 4: 'Exquisite', 5: 'Masterwork'}.get(level)
            key = library()['qualityEnums']['ArmorQualityID'].get(str(q['id'])) if q else None
            scaling = tables.get(f'{key}_{suffix}', {})
            if q and not scaling:
                absent_levels.append((prefab, level))
                levels -= 1
                continue  # Some unique items have no common-quality variant.
            if q and scaling != game_data(normalized).get('qualityStats'):
                errors.append((prefab, level, 'quality table differs from installed game'))
            expected = scaling.get('DamageThreshold', armor.get('DamageThreshold', 0))
            recovery = scaling.get('RecoveryModifier', armor.get('RecoveryModifier', 0))/10
            if abs(normalized['armor'] - expected) > .0001:
                errors.append((prefab, level, 'armor', expected, normalized['armor']))
            if abs(normalized['recovery'] - recovery) > .0001:
                errors.append((prefab, level, 'recovery', recovery, normalized['recovery']))
            # Compare scaled component values independently, rather than calling
            # the production scaler to derive our expected values.
            expected_components = copy.deepcopy(components)
            mappings = [('ParryBonus', 'Helmet_ParryBonus'), ('DodgeBonus', 'Helmet_DodgeBonus'),
                        ('AthleticsBonus', 'Boots_Athletics'), ('StealthBonus', 'Boots_StealthBonus'),
                        ('DisengagementDefenseBonus', 'Boots_DisengagementBonus'),
                        ('MeleeDamageBonus', 'Gloves_BonusMeleeDamage'),
                        ('PrecisionBonus', 'Gloves_PrecisionBonus'), ('DeflectionBonus', 'Defensive_DeflectionBonus')]
            for component in expected_components:
                for field, column in mappings:
                    if field in component and column in scaling:
                        component[field] = scaling[column]
                if 'AccuracyBonus' in component:
                    column = 'Helmet_AccuracyBonus' if 'ParryBonus' in component else 'Gloves_Accuracy'
                    component['AccuracyBonus'] = scaling.get(column, component['AccuracyBonus'])
                if 'DamageThreshold' in component:
                    component['DamageThreshold'] = expected
            expected_bonus = component_bonuses({'equipmentComponents': expected_components})
            actual_bonus = component_bonuses(game_data(normalized))
            if expected_bonus != actual_bonus:
                errors.append((prefab, level, 'component bonuses', expected_bonus, actual_bonus))
            for label, field in fields.items():
                percent = scaling.get('DTPerc'+field, armor.get('DtPerc'+field, 100))
                # No source status modifiers: these are checked separately.
                plain = copy.deepcopy(normalized)
                plain['properties'] = {'gameData': {**game_data(normalized), 'statusEffects': []}}
                actual = armor_by_type(plain)[label]
                if abs(actual - expected*percent/100) > .0001:
                    errors.append((prefab, level, label, expected*percent/100, actual))
        # Armor DT/deflection are intentionally replaced by its quality table.
        # Validate every other original component field as well.
        def comparable(rows):
            return sorted(json.dumps({k: v for k, v in t.items()
                if k not in {'DamageThreshold', 'DeflectionBonus'}}, sort_keys=True) for t in rows)
        if comparable(components) != comparable(game.get('equipmentComponents', [])):
            errors.append((prefab, 'non-scaled equipment components differ'))
    from merchant_rules import runtime_warnings
    manual=[{'prefab':prefab,'name':item['name']} for prefab,item in catalog_texts()[0].items()
            if item['category']=='Броня' and any('вручную' in note for note in runtime_warnings(item))]
    return {'armorChecked': checked, 'qualityVariantsChecked': levels, 'unavailableQualityVariants':absent_levels,
            'specialRulesStillRequireManualReview':manual,
            'mismatches': len(errors), 'examples': errors[:30]}


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    report = audit()
    print(json.dumps(report, ensure_ascii=False))
    raise SystemExit(bool(report['mismatches']))
