"""Source-keyed ability rules shared by NPCs and players; names are presentation only."""
import copy,json,math
from functools import lru_cache
from pathlib import Path
from item_effects import STATS
from localization import localize_game_text

SKILLS={2:'Атлетика',3:'Знания',4:'Хитроумие',5:'Одноручное оружие',6:'Парное оружие',7:'Двуручное оружие',8:'Волшебный посох',9:'Безоружный бой',10:'Луки',14:'Парирование',15:'Уклонение',18:'Управление огнём',19:'Управление холодом',20:'Управление молниями',22:'Управление рвением',23:'Управление истощением',25:'Управление жизнью',28:'Управление иллюзиями',30:'Управление могильным светом',32:'Управление силой',33:'Управление камнем',37:'Дротики'}
CONTROL={'dazed':'daze','prone':'prone','stun':'stun','paralyzed':'paralyze','petrified':'petrif','frozen':'freeze','asleep':'sleep','rooted':'root','hobbled':'hobble','Silenced':'silence','Disarm':'disarm','blinded':'blind','terrified':'fear','fear':'fear','confused':'confus','taunted':'taunt'}
RAW_SUPPORTED=set(STATS)|{7,8,9,14,25,53,75,84,107,116,140,150,151,169,176,181,188,2000,2004,2046,2085,226,2166}

@lru_cache(maxsize=1)
def library():
    path=Path(__file__).parent/'catalog/ability_rules.json'
    return json.loads(path.read_text(encoding='utf-8'))['abilities'] if path.exists() else []

@lru_cache(maxsize=1)
def index():
    result={}
    for row in sorted(library(),key=lambda a:('_PC_' in a['key'],bool(a['description']),not a['passive'])):
        for key in (row['key'],row['name'],row.get('name_en','')):
            if key:result[key.casefold()]=row
    return result

def resolve(value):
    if isinstance(value,str):value={'name':value}
    for key in ('prefab','key','sourceKey','name_en','name'):
        if str(value.get(key,'')).casefold() in index():return copy.deepcopy(index()[str(value[key]).casefold()])
    # Compatibility for older hand-translated starting abilities.
    from constants import ABILITY_DETAILS
    old=ABILITY_DETAILS.get(value.get('name'),{})
    english=__import__('urllib.parse',fromlist=['unquote']).unquote(old.get('source','').rsplit('/',1)[-1]).replace('_',' ')
    return copy.deepcopy(index().get(english.casefold()))

def normalize_talent(talent):
    row=resolve(talent)
    return {**talent,'name':row['name'],'description':row['description'] or talent.get('description',''),'prefab':row['key'],'icon_url':row['icon']} if row else talent

def profile(row,derived=None,weapon_range=1):
    row=copy.deepcopy(row);derived=derived or {};skills=derived.get('effectiveSkills',{})
    attack=derived.get('attack',{});row['range']=max(1,weapon_range) if row.get('weaponRange') else row.get('range',0)
    if row['targeting']=='cone':row['range']=max(row['range'],row.get('area',0))
    row['accuracy']=max([skills.get(SKILLS[s],0) for s in row.get('skills',[]) if s in SKILLS]+([attack.get('accuracy',0)] if 31 in row.get('skills',[]) or not row.get('skills') else []),default=0)+row.get('accuracyBonus',0)
    row['cooldown']=0 if row.get('cooldown',0)==0 else max(1,math.ceil(round(row['cooldown']*derived.get('cooldownMultiplier',1),6)))
    row['effects']=[];unsupported=[];seen=set()
    for node in row.get('nodes',[]):
        for s in node.get('statuses',[]):
            if s['AffectsStat'] in RAW_SUPPORTED and not s.get('ApplicationPrerequisites') and not s.get('TriggerAdjustment',{}).get('Type'):
                identity=(node['side'],s['AffectsStat'],s.get('Value'),s.get('Duration'),s.get('affliction'),s.get('DmgType'),s.get('DefType'),s.get('Skill'))
                if identity not in seen:
                    from consumables import effect_text
                    row['effects'].append({**s,'side':node['side'],'affliction':s.get('affliction',''),'kind':'source','name':effect_text(s),'value':s.get('Value',0),'rounds':max(1,math.ceil(s.get('Duration',0)/10))});seen.add(identity)
            elif s['AffectsStat'] not in {184,2077} and node.get('tag') not in CONTROL:unsupported.append(s['AffectsStat'])
        if node.get('tag') in CONTROL:
            seconds=max((s.get('Duration',0) for s in node.get('statuses',[])),default=0)
            row['effects'].append({'control':CONTROL[node['tag']],'name':node['name'],'side':node['side'],'Duration':seconds or 10})
    row['supported']=bool(row.get('damageMax') or row.get('weaponMultiplier') or row['effects'] or row.get('push'))
    row['limitation']='Для этой способности ещё нет боевого обработчика.' if not row['supported'] else ''
    row['unsupportedStats']=sorted(set(unsupported))
    if unsupported:
        row['supported']=False
        row['limitation']='Эта способность содержит условные эффекты, для которых ещё нет боевого обработчика.'
    row['details']=f"Дальность: {row['range']} клеток · Перезарядка: {'один раз за бой' if row.get('oncePerBattle') else str(row['cooldown'])+' раундов'}"
    if row['damageMax']:row['details']+=f" · Урон: {row['damageMin']:g}–{row['damageMax']:g}"
    elif row.get('weaponMultiplier'):row['details']+=f" · Урон оружия: {row['weaponMultiplier']*100:g}%"
    return row

def owned_actions(talents,derived,weapon_range=1):
    rows=[];seen=set()
    for talent in talents:
        row=resolve(talent)
        if not row or row['passive'] or row.get('modal') or row['key'] in seen:continue
        rows.append(profile(row,derived,weapon_range));seen.add(row['key'])
    return rows

def passive_equipment(talents):
    effects=[]
    for talent in talents:
        row=resolve(talent)
        if not row or not row['passive']:continue
        for node in row['nodes']:
            if node['side']=='self' and node['phase']=='root':effects.extend(s for s in node['statuses'] if s['AffectsStat'] not in {25,116})
    return [{'equipped_slot':'Эффект','armor':0,'properties':{'gameData':{'statusEffects':effects}}}] if effects else []

def weapon_requirement(row,inventory,active_set=1):
    from item_effects import active_equipment
    mask=row.get('weaponMask',0)
    if not mask:return ''
    categories={'Луки':32,'Щиты':4,'Одноручное оружие':2,'Двуручное оружие':16,'Парное оружие':8,'Посохи':128,'Метательное оружие':512,'Безоружное оружие':256}
    weapons=[i for i in active_equipment(inventory,active_set) if i.get('equipped_slot','').startswith('Оружие')]
    equipped=sum(categories.get(i.get('category'),0) for i in weapons) if weapons else 256
    if len(weapons)>1 and all(i.get('category')!='Щиты' for i in weapons):equipped|=8
    return '' if mask & equipped else 'Требуется подходящий тип оружия в активном комплекте.'
