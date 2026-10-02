"""Export stat symbols from the original NGUI Fallen_UI atlas."""
import json
import re
import struct
from pathlib import Path
import UnityPy

SYMBOLS = {'health':'icon_attribute_health', 'critical':'icon_attribute_accuracy',
    'accuracy':'icon_attribute_weapon_skill', 'damage':'icon_attribute_weapon',
    'recovery':'icon_attribute_recovery', 'endurance':'icon_attribute_endurance',
    'will':'icon_attribute_will', 'magic':'icon_attribute_spirit',
    'dodge':'icon_attribute_dodge', 'parry':'icon_attribute_parry',
    'armor':'icon_attribute_dmg_threshold', 'deflection':'icon_attribute_deflection'}

ROOT = Path(__file__).resolve().parents[1]

def main():
    env = UnityPy.load('C:/Games/Tyranny/Data/resources.assets')
    metadata = next(o.get_raw_data() for o in env.objects if o.type.name == 'MonoBehaviour'
                    and b'icon_attribute_health' in o.get_raw_data())
    rectangles = {}
    # NGUI stores aligned sprite names followed by outer and inner Rect floats.
    for match in re.finditer(rb'icon_[A-Za-z_0-9]+', metadata):
        offset = (match.end() + 3) // 4 * 4
        x, y, w, h = struct.unpack_from('<4f', metadata, offset)
        if 0 <= x < 1024 and 0 <= y < 1024 and 0 < w <= 128 and 0 < h <= 128:
            rectangles[match.group().decode()] = (int(x), int(y), int(x+w), int(y+h))
    for obj in env.objects:
        if obj.type.name == 'Texture2D' and obj.read().m_Name == 'Fallen_UI':
            atlas = obj.read().image.convert('RGBA')
            atlas.save(ROOT / 'web/assets/game-combat/Fallen_UI.png')
            output = ROOT / 'web/assets/stat-icons'
            for name, sprite in SYMBOLS.items():
                icon = atlas.crop(rectangles[sprite])
                # HUD's tint is applied to a monochrome atlas mask in the game.
                for y in range(icon.height):
                    for x in range(icon.width):
                        r, g, b, a = icon.getpixel((x, y))
                        luminance = max(r, g, b) / 255
                        icon.putpixel((x, y), (int(190*luminance), int(167*luminance), int(101*luminance), a))
                icon.save(output / (name + '.png'))
            for name, bounds in rectangles.items():
                if name.startswith(('icon_option_', 'icon_hud_', 'icon_weaponset_', 'icon_attribute_')):
                    atlas.crop(bounds).save(ROOT / 'web/assets/game-combat' / (name + '.png'))
            (output / 'manifest.json').write_text(json.dumps({'source': 'resources.assets/Fallen_UI', 'symbols': SYMBOLS, 'rectangles': rectangles}, indent=2), encoding='utf-8')
            print('Exported original HUD stat symbols')
            break

if __name__ == '__main__':
    main()
