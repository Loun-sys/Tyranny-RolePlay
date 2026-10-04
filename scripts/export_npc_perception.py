"""Read perception directly from the three original actor bundles, no game writes."""
import json
from pathlib import Path
import UnityPy

ROOT = Path(__file__).resolve().parents[1]
GAME = Path('C:/Games/Tyranny/Data/bundles')


def main():
    actors = json.loads((ROOT / 'catalog/game_npcs.json').read_text(encoding='utf-8'))
    result = {}
    for archive in sorted({n['source']['archive'] for n in actors}):
        env = UnityPy.load(str(GAME / archive))
        by_id = {o.path_id: o for o in env.objects if o.type.name == 'MonoBehaviour'}
        for npc in (n for n in actors if n['source']['archive'] == archive):
            obj = by_id[int(npc['key'].rsplit(':', 1)[1])]
            tree = obj.read_typetree()
            result[npc['key']] = {'perceptionType': int(tree['PerceptionType']),
                                  'perceptionDistanceMultiplier': float(tree.get('PerceptionDistanceMultiplier', 1))}
        print(archive, len(result), flush=True)
    (ROOT / 'catalog/npc_perception.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print('Exported', len(result), 'original perception profiles', flush=True)


if __name__ == '__main__':
    main()
