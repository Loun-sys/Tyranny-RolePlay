"""Read-only, cross-bundle PPtr resolver for installed game exports."""
from pathlib import Path
import collections
import UnityPy

GAME = Path('C:/Games/Tyranny/Data/bundles')


class GameIndex:
    def __init__(self,extra_bundles=()):
        self.assets={}; self.environments=[]; self.trees={}; self.groups=collections.defaultdict(list);self.names={}
        for name in ['characters','items','abilities','afflictions','spells','lists','progression_tables','dlc00','dlc01','dlc02','dlc03','vx1_characters','vx1_items',*extra_bundles]:
            env=UnityPy.load(str(GAME/(name+'.unity3d')));self.environments.append(env)
            for asset in env.assets:
                key=asset.name.casefold();self.assets[key]=asset
                for obj in asset.objects.values():
                    if obj.type.name=='GameObject':self.names[(key,obj.path_id)]=obj.read().m_Name
                    elif obj.type.name=='MonoBehaviour':
                        tree=obj.read_typetree(); self.trees[(key,obj.path_id)]=tree
                        self.groups[(key,tree.get('m_GameObject',{}).get('m_PathID'))].append((obj,tree))

    def resolve(self,obj,ptr):
        if not ptr or not ptr.get('m_PathID'):return None
        asset=obj.assets_file
        if ptr.get('m_FileID',0):
            index=ptr['m_FileID']-1
            if index>=len(asset.externals):return None
            asset=self.assets.get(asset.externals[index].path.rsplit('/',1)[-1].casefold())
        return asset.objects.get(ptr['m_PathID']) if asset else None

    def tree(self,obj):
        return self.trees.get((obj.assets_file.name.casefold(),obj.path_id),{}) if obj else {}

    def components(self,obj):
        if not obj:return []
        if obj.type.name=='MonoBehaviour':
            ref=self.tree(obj).get('m_GameObject',{})
            obj=self.resolve(obj,ref)
        return self.groups.get((obj.assets_file.name.casefold(),obj.path_id),[]) if obj else []

    def name(self,obj):
        if not obj:return ''
        if obj.type.name=='MonoBehaviour':obj=self.resolve(obj,self.tree(obj).get('m_GameObject',{}))
        return self.names.get((obj.assets_file.name.casefold(),obj.path_id),'') if obj else ''


def localized_tables(language='ru'):
    import xml.etree.ElementTree as ET
    result={}
    for folder in ['data','data_vx1','data_vx2','data_vx3']:
        directory=GAME.parent/folder/'exported/localized'/language/'text/game'
        for path in directory.glob('*.stringtable'):
            table=result.setdefault(path.stem,{})
            for row in ET.parse(path).getroot().findall('.//Entry'):
                table[int(row.findtext('ID'))]=row.findtext('DefaultText') or ''
    return result
