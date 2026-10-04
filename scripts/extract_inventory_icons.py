"""Extract original empty equipment slots and inventory tabs from Fallen_UI."""
import json
import re
import struct
from pathlib import Path
import UnityPy

ROOT=Path(__file__).resolve().parents[1]
SPRITES={
    'slot-head':'Inventory-ItemSlot-Helm','slot-torso':'Inventory-ItemSlot-Torso',
    'slot-hands':'Inventory-ItemSlot-Glove','slot-feet':'Inventory-ItemSlot-Boots',
    'slot-accessory':'Inventory-ItemSlot-Accessories','slot-weapon':'Inventory-ItemSlot-Weapon',
    'slot-shield':'Inventory-ItemSlot-Shield','slot-quick':'Inventory_EmptyItemSlot',
    'filter-all':'icon_inventory_all','filter-weapons':'icon_inventory_weapons',
    'filter-armor':'icon_inventory_armor','filter-consumables':'icon_inventory_consumables',
    'filter-other':'icon_inventory_other','filter-materials':'icon_inventory_ingredients',
}

def main():
    env=UnityPy.load('C:/Games/Tyranny/Data/resources.assets')
    raw=next(o.get_raw_data() for o in env.objects if o.type.name=='MonoBehaviour' and b'icon_attribute_health' in o.get_raw_data())
    atlas=next(o.read().image.convert('RGBA') for o in env.objects if o.type.name=='Texture2D' and o.read().m_Name=='Fallen_UI')
    output=ROOT/'web/assets/inventory-icons';output.mkdir(parents=True,exist_ok=True)
    manifest={}
    for name,sprite in SPRITES.items():
        match=re.search(re.escape(sprite.encode())+rb'(?![A-Za-z0-9_-])',raw)
        if not match:raise ValueError('Sprite not found: '+sprite)
        offset=(match.end()+3)//4*4
        x,y,w,h=struct.unpack_from('<4f',raw,offset)
        if not (0<=x<atlas.width and 0<=y<atlas.height and 0<w<=128 and 0<h<=128):raise ValueError('Invalid rectangle: '+sprite)
        bounds=(int(x),int(y),int(x+w),int(y+h))
        atlas.crop(bounds).save(output/(name+'.png'))
        manifest[name]={'sprite':sprite,'bounds':bounds}
    (output/'manifest.json').write_text(json.dumps({'source':'resources.assets/Fallen_UI','sprites':manifest},indent=2),encoding='utf-8')
    print('Original inventory icons extracted:',len(manifest))

if __name__=='__main__':main()
