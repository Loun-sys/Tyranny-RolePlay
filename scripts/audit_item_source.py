"""Read installed serialized prefabs, not Wiki-derived item descriptions."""
import collections
import json
import sys
from pathlib import Path
import dnfile
from game_asset_index import GameIndex

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding='utf-8')

def main():
    index = GameIndex()
    catalog = json.loads((ROOT/'catalog/game_items.json').read_text(encoding='utf-8'))
    existing = {i['properties']['gameData']['prefab']:i for i in catalog}
    pe = dnfile.dnPE('C:/Games/Tyranny/Data/Managed/Assembly-CSharp.dll')
    fields = {id(f.row):(str(t.TypeName),str(f.row.Name)) for t in pe.net.mdtables.TypeDef for f in t.FieldList if str(t.TypeName) in {'ModifiedStat','DamageType'}}
    enums = {}
    for c in pe.net.mdtables.Constant:
        pair = fields.get(id(c.Parent.row))
        if pair: enums.setdefault(pair[0],{})[int.from_bytes(c.Value.value,'little')]=pair[1]
    missing, mismatches, samples = [], [], []
    stats, applications, mod_fields = collections.Counter(),collections.Counter(),collections.Counter()
    count=0
    for (asset,pid),tree in index.trees.items():
        if 'DisplayName' not in tree or 'Value' not in tree: continue
        obj=index.assets[asset].objects[pid]; name=index.name(obj);count+=1
        if name not in existing:
            missing.append({'prefab':name,'archive':asset,'cut':tree.get('CutFromGame'),'nameRef':tree['DisplayName']})
            continue
        row=existing[name];game=row['properties']['gameData']
        mods=[index.tree(index.resolve(obj,p)) for p in tree.get('ItemMods',[])]
        mods=[m for m in mods if m]
        oldmods=[m for m in game.get('mods',[]) if m]
        if len(mods)!=len(oldmods):
            mismatches.append({'prefab':name,'oldMods':len(oldmods),'sourceMods':len(mods),'references':tree.get('ItemMods')})
        for m in mods:
            mod_fields.update(k for k,v in m.items() if v and k not in {'m_GameObject','m_Script'})
            for key in ['StatusEffectsOnEquip','StatusEffectsOnAttack','StatusEffectsOnCrit','StatusEffectsOnLaunch']:
                for effect in m.get(key,[]):
                    stats[(effect.get('AffectsStat'),key)]+=1;applications[effect.get('Apply')]+=1
        if row['category']=='Броня' and len(samples)<5:
            samples.append({'name':row['name'],'prefab':name,'components':[t for _,t in index.components(obj)],'mods':mods})
    report={'sourcePrefabs':count,'catalog':len(catalog),'missing':missing,'lostMods':mismatches,'stats':[{'id':s,'stat':enums.get('ModifiedStat',{}).get(s),'trigger':k,'count':v} for (s,k),v in stats.items()],'applications':dict(applications),'modFields':dict(mod_fields),'samples':samples,'enums':enums}
    (ROOT/'catalog/item_source_audit.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k not in {'samples','enums','missing','lostMods'}},ensure_ascii=False,indent=2))
    print('Missing:',len(missing),'lost mod sets:',len(mismatches))
if __name__=='__main__':main()
