"""Extract recipes, unlock-scroll globals and quality CSVs from original assets."""
import csv,io,json,sys
from pathlib import Path
import UnityPy,dnfile
from game_asset_index import GameIndex,localized_tables
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from localization import localize_game_text

def main():
    index=GameIndex(['recipes']);loc=localized_tables();catalog=json.loads((ROOT/'catalog/game_items.json').read_text(encoding='utf-8'))
    items={r['properties']['gameData']['prefab']:r for r in catalog}
    def ref(obj,p):return index.name(index.resolve(obj,p))
    recipes=[];item_scales={};scrolls={}
    for (asset,pid),t in index.trees.items():
        obj=index.assets[asset].objects[pid];name=index.name(obj)
        if name in items:
            if t.get('QualityScaleID'):
                kind='armor' if 'DamageThreshold' in t else 'shield' if 'BaseParryBonus' in t else 'weapon'
                item_scales[name]={'kind':kind,'id':t['QualityScaleID'],'level':t.get('QualityScaleLevel',1)}
            # Scrolls set the same globals that recipe visibility tests.
            if 'Recipe' in name or name.startswith('LibraryResearch_'):
                tags=[]
                def scan(v):
                    if isinstance(v,str) and '/' not in v and ('Scroll_' in v or 'recipe_acquired' in v or 'Potion_Research_' in v):tags.append(v)
                    elif isinstance(v,dict):
                        for x in v.values():scan(x)
                    elif isinstance(v,list):
                        for x in v:scan(x)
                scan(t)
                if tags:scrolls.setdefault(name,[]).extend(tags)
        if 'CraftingLocation' not in t:continue
        if not (t['CraftingLocation']==4 and (name.startswith('Potion_') or name.startswith('vx1_Potion_')) or t['CraftingLocation']==2 and t['ModifiesTo']>t['ModifiesFrom']>0):continue
        def refs(key):return [{'prefab':ref(obj,x['RecipeItem']),'quantity':x['Quantity'],'consumed':bool(x.get('Destroyed',1))} for x in t[key]]
        requirements=t['ModRequirements'];scales={}
        for x in requirements:
            for k,field in [('weapon','WeaponQualityScaleID'),('armor','ArmorQualityScaleID'),('shield','ShieldQualityScaleID')]:
                if x.get(field):scales[k]=x[field]
        outputs=refs('Output');cost=round(t['Cost']['InitialValue'])
        if not cost and outputs:cost=sum(items.get(o['prefab'],{}).get('value',0)*o['quantity'] for o in outputs)
        r=t['DisplayName'];label=loc.get({5:'items',13:'recipes'}.get(r['StringTable'],''),{}).get(r['StringID'],name)
        recipes.append({'key':name,'name':localize_game_text(label),'kind':'consumable' if outputs else 'upgrade',
            'cost':cost,'costRaw':t['Cost']['InitialValue'],'hours':t['GameHoursToCreate'],'ingredients':refs('Ingredients'),
            'output':outputs,'from':t['ModifiesFrom'],'to':t['ModifiesTo'],'scales':scales,
            'target':next((ref(obj,x['ItemPrefab']) for x in requirements if x['Type']==11),''),
            'unlocks':[x['Tag'] for x in t['VisibilityRequirements'] if x['Type']==3],
            'workers':max([x['Value'] for x in t['CreationRequirements'] if x['Type']==6] or [0]),
            'originalRequirements':t['CreationRequirements']})
    pe=dnfile.dnPE('C:/Games/Tyranny/Data/Managed/Assembly-CSharp.dll')
    fieldnames={id(f.row):(str(t.TypeName),str(f.row.Name)) for t in pe.net.mdtables.TypeDef for f in t.FieldList if str(t.TypeName) in ['WeaponQualityID','ArmorQualityID','ShieldQualityID']}
    enums={}
    for c in pe.net.mdtables.Constant:
        pair=fieldnames.get(id(c.Parent.row))
        if pair:enums.setdefault(pair[0],{})[str(int.from_bytes(c.Value.value,'little'))]=pair[1]
    tables={};env=UnityPy.load('C:/Games/Tyranny/Data/resources.assets')
    for obj in env.objects:
        if obj.type.name!='TextAsset':continue
        a=obj.read()
        if not a.m_Name.startswith('QualityScaling'):continue
        rows=list(csv.reader(io.StringIO(a.m_Script)));tables[a.m_Name]={r[0]:{k:float(v) for k,v in zip(rows[0][1:],r[1:])} for r in rows[1:] if r}
    for recipe in recipes:
        recipe['scrolls']=[name for name,tags in scrolls.items() if set(tags)&set(recipe['unlocks'])]
        if recipe['unlocks'] and not recipe['scrolls']:
            recipe['scrolls']=[name for name,item in items.items() if item['name'].casefold()=='рецепт: '+recipe['name'].casefold()]
    result={'source':'recipes.unity3d + resources.assets/QualityScaling + Assembly-CSharp enums','recipes':recipes,'items':item_scales,'qualityTables':tables,'qualityEnums':enums,'scrolls':scrolls,'qualityLabels':{str(level):loc['gui'][2541+level] for level in range(1,6)}}
    (ROOT/'catalog/crafting.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print('Extracted',len(recipes),'recipes;',len(item_scales),'quality items;',len(scrolls),'unlock scrolls')
    print('Recipe scroll links:',sum(bool(r['scrolls']) for r in recipes),'/',sum(bool(r['unlocks']) for r in recipes))
if __name__=='__main__':main()
