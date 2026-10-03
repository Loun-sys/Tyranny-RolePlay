"""Copy original game portraits; record explicit archetype fallbacks, not invented identities."""
import json,re,shutil
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
ART=Path('C:/Games/Tyranny/Data/data/art/gui')

def main():
    output={};dest=ROOT/'web/assets/npc-portraits';dest.mkdir(parents=True,exist_ok=True)
    def copy(relative):
        src=ART/relative
        if not src.exists():src=ART/'portraits/player/male/tankfighter_m_white_sm.png'
        shutil.copyfile(src,dest/src.name)
        return 'assets/npc-portraits/'+src.name
    fallback=copy('portraits/player/male/tankfighter_m_white_sm.png')
    rows=json.loads((ROOT/'catalog/game_npcs.json').read_text(encoding='utf-8'))
    for row in rows:
        prefab=row['source']['prefab'].lower();kind='archetype';note='Общий игровой портрет архетипа; собственного портрета в экспорте нет.'
        companion=next((n for n in ['barik','lantry','sirin','verse','killsinshadow'] if n in prefab),None)
        if companion:relative=f'portraits/companion/{companion}_sm.png';kind='personal';note='Оригинальный портрет персонажа.'
        elif re.search(r'(^|_)eb($|_)',prefab):relative='portraits/companion/eb_sm.png';kind='personal';note='Оригинальный портрет персонажа.'
        elif any(s in prefab for s in ['beast','beastman']):relative='portraits/companion/killsinshadow_sm.png'
        elif any(s in prefab for s in ['scourge','havoc','malice','bane','wisp']):
            relative='icons/abilities/abl-scourgedervish.png';kind='symbol';note='Оригинальная игровая иконка погибели; собственного портрета в экспорте нет.'
        else:
            female=bool(re.search(r'(_f_|female)',prefab));gender='female' if female else 'male';letter='f' if female else 'm'
            role='spellslinger' if any(s in prefab for s in ['mage','binder','caster','spell']) else 'loremaster' if any(s in prefab for s in ['sage','scribe','trainer']) else 'duelistfighter' if any(s in prefab for s in ['rogue','dual','archer','bow','scout']) else 'tankfighter'
            relative=f'portraits/player/{gender}/{role}_{letter}_white_sm.png'
        output[row['key']]={'portrait':copy(relative),'portraitKind':kind,'portraitNote':note}
    output['default']={'portrait':fallback,'portraitKind':'archetype','portraitNote':'Общий игровой портрет; можно заменить своим изображением.'}
    (ROOT/'catalog/npc_portraits.json').write_text(json.dumps(output,ensure_ascii=False,indent=2),encoding='utf-8')
    print('Portrait mappings:',len(rows),'original images:',len(list(dest.glob('*.png'))))
if __name__=='__main__':main()
