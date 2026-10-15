"""Read-only installed-game/catalogue/merchant reconciliation. No DB or rewrites."""
import collections
import json
import re
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from game_asset_index import GameIndex,localized_tables
from item_texts import catalog_texts
from merchant_rules import market_profile,SHOPS


def audit():
    index=GameIndex(extra_bundles=('recipes','edicts','missions','regions','skirmishes','teams','distrib_g'))
    tables=localized_tables();catalog=catalog_texts()[0]
    missing=[];excluded=[];source_count=0;source_mismatches=[];mod_mismatches=[]
    for (asset,pid),source in index.trees.items():
        if 'DisplayName' not in source or 'Value' not in source:continue
        source_count+=1
        obj=index.assets[asset].objects[pid];prefab=index.name(obj)
        name=tables.get('items',{}).get(source['DisplayName'].get('StringID'),'')
        if prefab not in catalog:
            reason=('Вырезанный предмет' if source.get('CutFromGame') else
                    'Служебный объект' if source.get('IsProp') or re.search(r'(^test|_test|^debug|^npc_|^prop_)',prefab,re.I) else
                    'Нет локализованного названия' if not name else '')
            (excluded if reason else missing).append({'prefab':prefab,'reason':reason})
            continue
        game=catalog[prefab]['properties']['gameData']
        clean={k:v for k,v in source.items() if not k.startswith('m_')}
        if game.get('sourceItem')!=clean:source_mismatches.append(prefab)
        mods=[index.tree(index.resolve(obj,p)) for p in source.get('ItemMods',[])]
        if len([m for m in mods if m])!=len([m for m in game.get('mods',[]) if m]):mod_mismatches.append(prefab)
    profiles={k:market_profile(i) for k,i in catalog.items()}
    invalid=[k for k,p in profiles.items() if p['purchasable'] and
             (p['shopKey'] not in SHOPS or p['buyPrice']<=p['sellPrice'] or p['buyPrice']<=0)]
    return {'sourcePrefabs':source_count,'catalogItems':len(catalog),
            'excluded':dict(collections.Counter(i['reason'] for i in excluded)),
            'missingPlayableItems':missing,'changedSourceRecords':source_mismatches,'lostModSets':mod_mismatches,
            'shops':dict(collections.Counter(p['shopKey'] for p in profiles.values() if p['purchasable'])),
            'catalogOnly':dict(collections.Counter(p['unavailableReason'] for p in profiles.values() if not p['purchasable'])),
            'invalidMerchantProfiles':invalid}


if __name__=='__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    report=audit();print(json.dumps(report,ensure_ascii=False,indent=2))
    raise SystemExit(bool(report['missingPlayableItems'] or report['changedSourceRecords'] or
                          report['lostModSets'] or report['invalidMerchantProfiles']))
