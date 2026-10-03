"""Reproducible coverage report for all class and base talents."""
import json
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from ability_rules import normalize_talent
from talent_data import TALENTS

def audit():
    extended=json.loads((ROOT/'data/extended_talents_cache_v2.json').read_text(encoding='utf-8'))
    rows=[normalize_talent(t) for t in [*TALENTS,*sum(extended['backgrounds'].values(),[])]]
    report=[{'name':t['name'],'legacyName':t.get('legacyName',t['name']),'tree':t['tree'],'sourceKey':t.get('prefab'),**t['mechanics']} for t in rows]
    output=ROOT/'catalog/talent_mechanics_audit.json'
    output.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print('Audited:',len(report),'source matched:',sum(bool(t['sourceKey']) for t in report),
          'require further handlers:',sum(bool(t.get('limitation')) for t in report))

if __name__=='__main__':audit()
