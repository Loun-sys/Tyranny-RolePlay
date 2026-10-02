"""Read original timing fields without treating every Duration as an area lifetime."""
import json
from pathlib import Path
import UnityPy

ROOT = Path(__file__).resolve().parents[1]
ARCHIVE = Path('C:/Games/Tyranny/Data/bundles/spells.unity3d')


def timing_fields(value, path=''):
    if isinstance(value, dict):
        for key, child in value.items():
            current = f'{path}.{key}'.lstrip('.')
            if key in {'Duration', 'DurationOverride', 'IntervalRate', 'AuraIntervalSpeed',
                       'NumberOfProjectiles', 'CooldownTimerDuration'} and isinstance(child, (int, float)) and child:
                yield {'field': current, 'value': round(child, 5)}
            else:
                yield from timing_fields(child, current)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from timing_fields(child, f'{path}[{index}]')


def main():
    env = UnityPy.load(str(ARCHIVE))
    names = {obj.path_id: obj.read().m_Name for obj in env.objects if obj.type.name == 'GameObject'}
    records = []
    for obj in env.objects:
        if obj.type.name != 'MonoBehaviour':
            continue
        tree = obj.read_typetree()
        name = names.get(tree.get('m_GameObject', {}).get('m_PathID'), '')
        fields = list(timing_fields(tree))
        modifiers = [{'tag': item.get('Tag'), 'type': item.get('EffectType'),
                      'multiplier': round(item.get('Multiplier', 1), 5)}
                     for item in tree.get('Effects', []) if 'Duration' in item.get('Tag', '')]
        if (fields or modifiers) and any(word in name.lower() for word in ['field', 'aura', 'rain', 'duration']):
            records.append({'prefab': name, 'component_path_id': obj.path_id,
                            'fields': fields, 'duration_modifiers': modifiers})
    output = ROOT / 'catalog' / 'spell_duration_audit.json'
    output.write_text(json.dumps({'source': 'Installed game: bundles/spells.unity3d',
                                 'note': 'Raw component fields. IntervalRate and AuraIntervalSpeed are enums, not seconds. Nested status durations are not area lifetimes.',
                                 'records': records}, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'Original timing audit: {len(records)} components')


if __name__ == '__main__':
    main()
