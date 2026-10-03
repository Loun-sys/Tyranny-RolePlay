"""Read original ability graphs and enum identities for reproducible diagnostics."""
import json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts.game_asset_index import GameIndex,localized_tables
import dnfile

def main():
    g=GameIndex();ru=localized_tables();en=localized_tables('en')
    query=sys.argv[1].casefold() if len(sys.argv)>1 else 'shieldslam'
    for group,components in g.groups.items():
        name=g.names.get(group,'')
        if query not in name.casefold():continue
        queue=list(components);seen=set();rows=[]
        while queue and len(rows)<60:
            obj,t=queue.pop(0);key=(obj.assets_file.name,obj.path_id)
            if key in seen:continue
            seen.add(key);rows.append({'prefab':g.name(obj),'tree':t})
            def refs(value):
                if isinstance(value,dict):
                    if 'm_PathID' in value:
                        if value.get('m_PathID'):queue.extend(g.components(g.resolve(obj,value)))
                    else:
                        for v in value.values():refs(v)
                elif isinstance(value,list):
                    for v in value:refs(v)
            for k,v in t.items():
                if not k.startswith('m_'):refs(v)
        print(json.dumps({'name':name,'rows':rows},ensure_ascii=False,indent=2));break
    pe=dnfile.dnPE('C:/Games/Tyranny/Data/Managed/Assembly-CSharp.dll')
    names={'AttackType','AttackMode','DamageType','DefenseType','TargetType','AbilityTargetType','CooldownType','EffectDurationType','ApplyType','IntervalRateType'}
    fields={id(f.row):(str(t.TypeName),str(f.row.Name)) for t in pe.net.mdtables.TypeDef for f in t.FieldList if str(t.TypeName) in names}
    enums={}
    for c in pe.net.mdtables.Constant:
        pair=fields.get(id(c.Parent.row))
        if pair:enums.setdefault(pair[0],{})[int.from_bytes(c.Value.value,'little')]=pair[1]
    print(json.dumps(enums,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
