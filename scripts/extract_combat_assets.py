"""Export original HUD and VFX textures without changing the installed game."""
import argparse
import json
import re
from pathlib import Path

import UnityPy

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--game', type=Path, default=Path('C:/Games/Tyranny/Data'))
    parser.add_argument('--output', type=Path, default=Path('web/assets/game-combat'))
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    manifest = {}
    files = [args.game / 'resources.assets', *sorted(args.game.glob('sharedassets*.assets'))]
    pattern = re.compile(r'hud|atlas|actionbar|abilitybar|quickbar|portrait_frame|fx_fire|fx_lightning|fx_ice|fx_flare|fx_smoke|fx_spellicon|Core-|Journal-Menu|ICO_|GUI', re.I)
    for path in files:
        try:
            env = UnityPy.load(str(path))
            for obj in env.objects:
                if obj.type.name not in {'Texture2D', 'Sprite'}:
                    continue
                texture = obj.read()
                name = texture.m_Name
                selected = pattern.search(name) or obj.type.name == 'Sprite' and re.search(r'MenuFrame|ui_button_square_frame', name)
                if name in manifest or not selected:
                    continue
                filename = re.sub(r'[^a-zA-Z0-9_-]', '_', name) + '.png'
                try:
                    image = texture.image
                    image.save(args.output / filename)
                    manifest[name] = {'file': filename, 'source': path.name, 'width': image.width, 'height': image.height}
                    print(path.name, name, image.width, image.height, flush=True)
                except Exception as error:
                    print('SKIP', name, str(error)[:100], flush=True)
        except Exception as error:
            print('SKIP ARCHIVE', path.name, str(error)[:100], flush=True)
    (args.output / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')

if __name__ == '__main__':
    main()
