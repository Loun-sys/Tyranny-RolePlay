"""Print compact inspection-only localization from installed game files as JSON.

NoEffect.Value is a GUI string ID, not an ability string ID. AbilityModType is
read from Assembly-CSharp.dll; target abilities are resolved across bundles.
The runtime only uses this exported snapshot, never the player's installation.
"""
import json
from pathlib import Path
import sys
from game_asset_index import GameIndex, localized_tables

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from item_effects import game_data
from localization import localize_game_text


def main():
    rows=json.loads((ROOT/'catalog/game_items.json').read_text(encoding='utf-8'))
    tables=localized_tables()
    ids=set()
    for item in rows:
        game=game_data(item)
        for mod in game.get('mods',[]):
            for field in ['StatusEffectsOnEquip','StatusEffectsOnAttack','StatusEffectsOnCrit','StatusEffectsOnLaunch']:
                ids.update(int(e['Value']) for e in mod.get(field,[]) if e.get('AffectsStat')==184)
    index=GameIndex()
    wanted={game_data(i)['prefab'] for i in rows if any(m.get('AbilitiesToModOnEquip') for m in game_data(i).get('mods',[]))}
    targets={}
    for (asset,pid),tree in index.trees.items():
        if 'Value' not in tree or 'ItemMods' not in tree:
            continue
        obj=index.assets[asset].objects[pid];prefab=index.name(obj)
        if prefab not in wanted:
            continue
        for pointer in tree['ItemMods']:
            mod_obj=index.resolve(obj,pointer);mod=index.tree(mod_obj)
            if not mod.get('AbilitiesToModOnEquip'):
                continue
            ref=mod.get('DisplayName',{});name=tables['itemmods'].get(ref.get('StringID'),'')
            names=[]
            for ability_pointer in mod['AbilitiesToModOnEquip']:
                for _,ability in index.components(index.resolve(mod_obj,ability_pointer)):
                    title=tables['abilities'].get(ability.get('DisplayName',{}).get('StringID'),'')
                    if title:
                        names.append(localize_game_text(title))
            targets[prefab+'|'+localize_game_text(name)]=list(dict.fromkeys(names))
    print(json.dumps({'source':'Tyranny Russian gui.stringtable and item/ability prefabs',
                      'guiStrings':{str(i):localize_game_text(tables['gui'].get(i,'')) for i in sorted(ids)},
                      'abilityTargets':targets},ensure_ascii=False,indent=2))


if __name__=='__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    main()
