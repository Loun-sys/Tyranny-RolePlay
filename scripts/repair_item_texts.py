"""Replace Wiki/transliterated item copy with original Russian string references."""
import json
import re
import sys
from pathlib import Path
import UnityPy
from game_asset_index import localized_tables

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from localization import localize_game_text, seconds_to_rounds
from item_effects import passive_descriptions, STATS, SKILLS

def main():
    tables = localized_tables()
    def text(ref):
        table = {5:'items', 6:'abilities', 16:'itemmods'}.get(ref.get('StringTable'))
        value = tables.get(table, {}).get(ref.get('StringID'), '')
        return localize_game_text(re.sub(r'\[/?url(?:=[^]]+)?\]', '', value)).strip()
    path = ROOT/'catalog/game_items.json'
    items = json.loads(path.read_text(encoding='utf-8'))
    refs, abilities = {}, {}
    for archive in {i['properties']['gameData']['archive'] for i in items}:
        env = UnityPy.load(f'C:/Games/Tyranny/Data/bundles/{archive}.unity3d')
        names, components, ability_components = {}, {}, {}
        for obj in env.objects:
            if obj.type.name == 'GameObject': names[obj.path_id] = obj.read().m_Name
            elif obj.type.name == 'MonoBehaviour':
                tree = obj.read_typetree()
                if 'DisplayName' in tree and 'Value' in tree:
                    components[tree['m_GameObject']['m_PathID']] = tree
                elif 'DisplayName' in tree and 'StatusEffects' in tree:
                    ability_components.setdefault(tree['m_GameObject']['m_PathID'], []).append(tree)
        for ident, tree in components.items(): refs[(archive,names.get(ident))] = tree
        for ident, trees in ability_components.items(): abilities[(archive,names.get(ident))] = trees
    for item in items:
        game = item['properties']['gameData']
        tree = refs[(game['archive'],game['prefab'])]
        name = text(tree['DisplayName'])
        variant = re.search(r' \(вариант \d+\)$', item['name'])
        item['name'] = name + (variant.group() if variant else '')
        item['lore'] = text(tree.get('DescriptionText', {}))
        mods = list(dict.fromkeys(text(m.get('Description', m.get('DescriptionText', {}))) for m in game.get('mods', [])))
        item['description'] = '\n\n'.join(m for m in mods if m and m != item['lore'])
        # Old Wiki properties contain transliteration; actual numerical effects
        # remain in gameData and are described from the extracted status records.
        item['properties'] = {'gameData':game}
        effects = passive_descriptions(item)
        if effects: item['properties']['Эффекты'] = '; '.join(effects)
        active_text = []
        for ability in abilities.get((game['archive'],game['prefab']), []):
            description = text(ability.get('Description', {}))
            if description: active_text.append(description)
            for effect in ability.get('StatusEffects', []):
                stat = STATS.get(effect.get('AffectsStat'))
                if effect.get('AffectsStat') == 2046: stat = SKILLS.get(effect.get('Skill'))
                if stat and effect.get('Apply') == 0 and not effect.get('HideFromUI'):
                    line = f"{stat}: {effect.get('Value',0):+g}"
                    if effect.get('Duration',0)>0: line += ' на ' + seconds_to_rounds(effect['Duration'])
                    active_text.append(line)
        if active_text: item['properties']['При использовании'] = '; '.join(dict.fromkeys(active_text))
        game['localizedText'] = True
        if game.get('statsVersion')==2:
            from item_effects import refresh_item_properties
            from consumables import refresh_consumable
            refresh_item_properties(item);refresh_consumable(item)
    path.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'Original Russian item references restored: {len(items)}')

if __name__ == '__main__': main()
