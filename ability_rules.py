"""Source-keyed ability rules shared by NPCs and players; names are presentation only."""
import copy,json,math
from functools import lru_cache
from pathlib import Path
from item_effects import STATS
from localization import localize_game_text

SKILLS={2:'Атлетика',3:'Знания',4:'Хитроумие',5:'Одноручное оружие',6:'Парное оружие',7:'Двуручное оружие',8:'Волшебный посох',9:'Безоружный бой',10:'Луки',14:'Парирование',15:'Уклонение',18:'Управление огнём',19:'Управление холодом',20:'Управление молниями',22:'Управление рвением',23:'Управление истощением',25:'Управление жизнью',28:'Управление иллюзиями',30:'Управление могильным светом',32:'Управление силой',33:'Управление камнем',37:'Дротики'}
CONTROL={'dazed':'daze','prone':'prone','stun':'stun','paralyzed':'paralyze','petrified':'petrif','frozen':'freeze','asleep':'sleep','rooted':'root','hobbled':'hobble','Silenced':'silence','Disarm':'disarm','blinded':'blind','terrified':'fear','fear':'fear','confused':'confus','taunted':'taunt'}
RAW_SUPPORTED=set(STATS)|{7,8,9,14,18,24,25,45,53,75,84,107,116,121,140,150,151,169,176,181,188,2000,2004,2013,2046,2072,2085,226,2145,2157,2166}

@lru_cache(maxsize=1)
def library():
    path=Path(__file__).parent/'catalog/ability_rules.json'
    return json.loads(path.read_text(encoding='utf-8'))['abilities'] if path.exists() else []

@lru_cache(maxsize=1)
def index():
    result={}
    for row in sorted(library(),key=lambda a:('_PC_' in a['key'],bool(a['description']),not a['passive'],-len(a['key']))):
        for key in (row['key'],row['name'],row.get('name_en','')):
            if key:result[key.casefold()]=row
    # The DB retains original talent names. Resolve those to source keys as well.
    from talent_data import TALENTS
    for talent in TALENTS:
        canonical=result.get(str(talent.get('name_en','')).casefold())
        if canonical:
            result[talent['name'].casefold()]=canonical
            result[talent.get('legacyName',talent['name']).casefold()]=canonical
    audit=Path(__file__).parent/'catalog/talent_mechanics_audit.json'
    if audit.is_file():
        for talent in json.loads(audit.read_text(encoding='utf-8')):
            canonical=result.get(str(talent.get('sourceKey','')).casefold())
            if canonical and talent.get('legacyName'):result[talent['legacyName'].casefold()]=canonical
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
    return {**talent,'legacyName':talent.get('legacyName',talent['name']),'name':row['name'],'description':row['description'] or talent.get('description',''),'prefab':row['key'],'icon_url':row['icon'],'mechanics':talent_mechanics(row)} if row else {**talent,'mechanics':{'effects':[],'limitation':'Не найдено соответствие в игровых файлах; механика требует проверки.'}}


def talent_mechanics(row):
    """Readable source values and execution coverage, not invented tooltip bonuses."""
    from consumables import effect_text
    from item_effects import passive_descriptions, equip_modifiers
    result={'effects':[], 'type':'Стойка' if row.get('modal') else 'Пассивный талант' if row['passive'] else 'Активная способность'}
    if row.get('bonusDamageMult',1)!=1:
        result['effects'].append(f"Урон подходящего оружия: {(row['bonusDamageMult']-1)*100:+.0f}%")
    if not row['passive']:
        p=profile(row)
        result.update(details=p['details'],limitation=p['limitation'])
        result['effects'].extend(f"На {'себя' if e['side']=='self' else 'цель'}: {e['name']} на {e['rounds']} раунд." for e in p['effects'] if e.get('control'))
        result['effects'].extend(filter(None,[
            'Навык атаки: '+', '.join(SKILLS[s] for s in row.get('skills',[]) if s in SKILLS) if row.get('skills') else '',
            'Защита цели: '+row.get('defense','') if row.get('targeting')!='self' else '',
            'Область: '+str(row['area'])+' м' if row.get('area') else '',
            'Отталкивание: '+str(row['push'])+' м' if row.get('push') else '',
            'Требуется щит' if row.get('weaponMask')==4 else '',
        ]))
    else:
        root=[s for n in row['nodes'] if n['phase']=='root' and n['side']=='self' for s in n['statuses'] if s['AffectsStat'] not in {25,116}]
        item={'properties':{'gameData':{'statusEffects':root}}}
        implemented=passive_descriptions(item)
        result['effects'].extend(implemented)
        from talent_runtime import SUPPORTED,DISPLAY_ONLY
        recognized=set(STATS)|SUPPORTED|DISPLAY_ONLY|{7,8,9,14,107,104,74,140,2000,181,2166,45,153,226,188,169,2046,2005,2168,2172,2122,2123,2161}
        procs=proc_profiles(row)
        if procs:recognized|={2156,2159}
        missing=any(s.get('AffectsStat') not in recognized for s in root)
        from talent_runtime import equipment_condition_supported
        conditional=any(not equipment_condition_supported(e) for e in equip_modifiers(item)['conditional'])
        result['limitation']='Есть условные или специальные эффекты, ещё не подключённые к расчётам.' if missing or conditional else ''
    for node in row['nodes']:
        if node.get('tag') in CONTROL:
            seconds=max((s.get('Duration',0) for s in node['statuses']),default=10)
            result['effects'].append(f"На {'себя' if node['side']=='self' else 'цель'}: {node['name']} на {max(1,math.ceil(seconds/10))} раунд.")
        for effect in node['statuses']:
            text=effect_text(effect)
            if not text: text=effect.get('localizedDescription') or node.get('description') or ''
            if not text:continue
            prefix=('На себя: ' if node['side']=='self' else 'На цель: ')+('условный эффект — ' if effect.get('ApplicationPrerequisites') or effect.get('TriggerAdjustment',{}).get('Type') else '')
            result['effects'].append(prefix+text)
    result['effects']=list(dict.fromkeys(result['effects']))
    if not result['effects'] and row['passive']:
        result['limitation']=result.get('limitation') or 'Специальная механика этого таланта ещё не подключена к расчётам.'
    if row.get('modal'):
        equipped=stance_equipment(row['key'])
        result['limitation']='' if equipped else 'Эффекты этой стойки ещё не подключены к боевому обработчику.'
        result['details']='Действует только выбранная стойка. Переключение не тратит основное действие.'
    if row.get('isTalentUpgrade'):
        result['type']='Улучшение способности'
        result['limitation']=upgrade_limitation(row)
        for key in row.get('grantedAbilities',[]):
            ability=index().get(key.casefold())
            if ability:result['effects'].append('Изменяет способность: '+ability['name'])
        labels={3:'Точность',7:'Пробивание брони',2001:'Дальность',2002:'Отталкивание',2003:'Прерывание'}
        for mod in row.get('abilityMods',[]):
            if mod['Type'] in labels:result['effects'].append(f"{labels[mod['Type']]}: {mod['Value']:+g}")
            elif mod['Type'] in {10,2000}:result['effects'].append(f"{'Перезарядка' if mod['Type']==10 else 'Урон'}: {(mod['Value']-1)*100:+g}%")
    return result


def upgrade_limitation(row):
    supported_types={1,2,3,7,10,2000,2001,2002,12}
    if any(m['Type'] not in supported_types for m in row.get('abilityMods',[])):
        return 'Некоторые изменения этой способности ещё не подключены к боевому обработчику.'
    for key in row.get('grantedAbilities',[]):
        base=resolve(key)
        if not base or not profile(apply_upgrades(base,[row]))['supported']:
            return 'Некоторые эффекты улучшения ещё не подключены к боевому обработчику.'
    return ''

def profile(row,derived=None,weapon_range=1):
    row=copy.deepcopy(row);derived=derived or {};skills=derived.get('effectiveSkills',{})
    attack=derived.get('attack',{});row['range']=max(1,weapon_range) if row.get('weaponRange') else row.get('range',0)
    if row['targeting']=='cone':row['range']=max(row['range'],row.get('area',0))
    row['accuracy']=max([skills.get(SKILLS[s],0) for s in row.get('skills',[]) if s in SKILLS]+([attack.get('accuracy',0)] if 31 in row.get('skills',[]) or not row.get('skills') else []),default=0)+row.get('accuracyBonus',0)
    row['cooldown']=0 if row.get('cooldown',0)==0 else max(1,math.ceil(round(row['cooldown']*derived.get('cooldownMultiplier',1),6)))
    row['effects']=[];unsupported=[];seen=set()
    primary=next((n['attack'] for n in row.get('nodes',[]) if n.get('attack') and n['phase'] in {'root','attack'}),{})
    row['targetType']=primary.get('ValidTargets',1)
    row['targetTeam']='ally' if row['targetType'] in {2,3,11,12,13,19,102,104} else 'enemy'
    for node in row.get('nodes',[]):
        for s in node.get('statuses',[]):
            if s['AffectsStat'] in RAW_SUPPORTED and not s.get('ApplicationPrerequisites') and not s.get('TriggerAdjustment',{}).get('Type'):
                identity=(node['side'],s['AffectsStat'],s.get('Value'),s.get('Duration'),s.get('affliction'),s.get('DmgType'),s.get('DefType'),s.get('Skill'))
                if identity not in seen:
                    from consumables import effect_text
                    side='target' if row['targeting']=='self' and row.get('area') and s.get('IsHostile') and row.get('damageMax') else node['side']
                    row['effects'].append({**s,'side':side,'affliction':s.get('affliction',''),'kind':'source','name':effect_text(s),'value':s.get('Value',0),'rounds':max(1,math.ceil(s.get('Duration',0)/10))});seen.add(identity)
            elif s['AffectsStat'] not in {184,2077,2001,2011} and node.get('tag') not in CONTROL:unsupported.append(s['AffectsStat'])
        if node.get('tag') in CONTROL:
            seconds=max((s.get('Duration',0) for s in node.get('statuses',[])),default=0)
            row['effects'].append({'control':CONTROL[node['tag']],'name':node['name'],'side':node['side'],'Duration':seconds or 10,'rounds':max(1,math.ceil((seconds or 10)/10)),'value':0})
    row['movementEffect']='swap' if row['key']=='Abl_PC_Leadership_SwapPositions' else ''
    row['supported']=bool(row.get('damageMax') or row.get('weaponMultiplier') or row['effects'] or row.get('push') or row['movementEffect'])
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
    rows=[];seen=set();upgrades=[];candidates=[]
    for talent in talents:
        row=resolve(talent)
        if not row:continue
        if row.get('isTalentUpgrade'):
            upgrades.append(row)
            candidates.extend(filter(None,(resolve(key) for key in row.get('grantedAbilities',[]))))
        elif not row['passive'] and not row.get('modal'):candidates.append(row)
    for row in candidates:
        if row['key'] in seen:continue
        rows.append(profile(apply_upgrades(row,upgrades),derived,weapon_range));seen.add(row['key'])
    return rows


UPGRADE_FIELDS={3:'accuracyBonus',7:'penetration',2001:'range',2002:'push',2003:'interrupt'}

def apply_upgrades(row,upgrades):
    """AbilityModType values from Assembly-CSharp, applied only to listed abilities."""
    row=copy.deepcopy(row)
    row['upgrades']=[]
    for upgrade in upgrades:
        if row['key'] not in upgrade.get('grantedAbilities',[]):continue
        row['upgrades'].append(upgrade['key'])
        for mod in upgrade.get('abilityMods',[]):
            kind=mod['Type'];value=float(mod.get('Value',0))
            if kind in UPGRADE_FIELDS:
                field=UPGRADE_FIELDS[kind];row[field]=row.get(field,0)+value
            elif kind==2000:
                row['weaponMultiplier']*=value
                row['damageMin']*=value;row['damageMax']*=value
            elif kind==10:
                row['cooldownSeconds']*=value
                row['cooldown']=math.ceil(row['cooldownSeconds']/10)
            elif kind in {1,2,12}:
                side='self' if kind in {1,12} else 'target'
                # Wrapper graphs are already exported; do not flatten their triggers.
                statuses=[copy.deepcopy(s) for s in mod.get('StatusEffects',[])]
                row['nodes'].append({'prefab':upgrade['key'],'phase':'upgrade','side':side,
                                     'name':upgrade['name'],'tag':'','attack':{},'statuses':statuses})
        row['nodes'].extend(copy.deepcopy(n) for n in upgrade['nodes'] if n['phase']!='upgrade')
    return row

def passive_equipment(talents, inventory=None, active_set=1):
    from talent_runtime import equipment_condition_supported,equipped_effect
    from item_effects import active_equipment,unconditional
    effects=[];conditional={}
    for talent in talents:
        row=resolve(talent)
        if not row or not row['passive'] or row.get('modal'):continue
        if row.get('abilityClass') in {'TriggeredOnKillAbility','TriggeredOnDeathAbility'}:continue
        if inventory is not None and weapon_requirement(row,inventory,active_set):continue
        for node in row['nodes']:
            if node['side']!='self' or node['phase']!='root':continue
            for s in node['statuses']:
                if s['AffectsStat'] in {25,116}:continue
                if unconditional(s):effects.append(s)
                elif inventory is not None and equipment_condition_supported(s):
                    applied=equipped_effect(s,active_equipment(inventory,active_set))
                    if applied:
                        identity=(s['AffectsStat'],s.get('DmgType'),tuple(p['Type'] for p in s.get('ApplicationPrerequisites',[])),s.get('TriggerAdjustment',{}).get('Type'))
                        old=conditional.get(identity)
                        if not old or (applied['Value']<old['Value'] if s['AffectsStat']==2000 else applied['Value']>old['Value']):conditional[identity]=applied
    effects.extend(conditional.values())
    return [{'name':'Эффекты талантов','category':'Эффекты','equipped_slot':'Эффект','armor':0,'properties':{'gameData':{'statusEffects':effects}}}] if effects else []


def weapon_mastery(talents, inventory, active_set=1):
    categories={};chances={}
    for talent in talents:
        row=resolve(talent)
        if not row or not row['passive'] or row.get('modal') or weapon_requirement(row,inventory,active_set):continue
        bonus=row.get('bonusDamageMult',1)
        category=row.get('specializationCategory')
        if bonus!=1:categories[category]=max(categories.get(category,1),bonus)
        for node in row['nodes']:
            if node['side']!='self' or node['phase']!='root':continue
            for effect in node['statuses']:
                if effect['AffectsStat']==2168:
                    count=int(effect['Value']);chances[count]=max(chances.get(count,0),float(effect.get('ExtraValue',0)))
    return math.prod(categories.values()),chances


def stance_equipment(name):
    from item_effects import unconditional
    row=resolve(name)
    if not row or not row.get('modal'):return []
    effects=[s for n in row['nodes'] if n['side']=='self' and n['phase']=='root' for s in n['statuses'] if s['AffectsStat'] not in {184,2001,2011}]
    allowed=set(STATS)|{7,8,9,14,107,104,74,140,2000,181,2166,45,153,226,188,169,2046}
    if proc_profiles(row):allowed|={2156,2159}
    if not effects or any(not unconditional(s) or s['AffectsStat'] not in allowed for s in effects):return []
    return [{'name':row['name'],'category':'Эффекты','equipped_slot':'Эффект','armor':0,'properties':{'gameData':{'statusEffects':effects}}}]


def proc_profiles(row,derived=None):
    """A single unconditional weapon-hit graph; complex/stealth graphs stay blocked."""
    triggers=[s for n in row['nodes'] if n['phase']=='root' and n['side']=='self'
              for s in n['statuses'] if s['AffectsStat'] in {2156,2159}]
    if len(triggers)!=1:return []
    trigger=triggers[0]
    if trigger.get('ApplicationPrerequisites') or trigger.get('TriggerAdjustment',{}).get('Type'):return []
    nodes=[n for n in row['nodes'] if n['phase'] not in {'root','upgrade'}]
    attacks=[n['attack'] for n in nodes if n.get('attack')]
    if not attacks or any(1 in a.get('m_attackSkills',[]) or a.get('BlastRadius',0) for a in attacks):return []
    a=attacks[0];damage=a.get('DamageData',{})
    child={**row,'nodes':nodes,'passive':False,'modal':False,'targeting':'unit',
           'range':1,'weaponRange':False,'area':0,'damageMin':damage.get('Minimum',0),
           'damageMax':damage.get('Maximum',0),'weaponMultiplier':damage.get('WeaponDamageMult',0)*a.get('DamageMultiplier',1),
           'accuracyBonus':a.get('AccuracyBonus',0),'skills':a.get('m_attackSkills',[]),
           'defense':{0:'Парирование',1:'Выносливость',2:'Воля',3:'Магия',5:'Нет'}.get(a.get('DefendedBy',0),'Парирование'),
           'damageType':damage.get('Type',9),'penetration':a.get('DTBypass',0),'push':a.get('PushDistance',0)}
    result=profile(child,derived)
    if not result['supported']:return []
    result['triggerStat']=trigger['AffectsStat'];result['weaponTrigger']=trigger.get('AttackTypeTriggerForLaunchAttack',2)
    return [result]


def shield_mastery_bonuses(talents, inventory):
    from item_effects import active_equipment, component_bonuses, game_data, unconditional
    values=[float(s['Value']) for t in talents for row in [resolve(t)] if row and row['passive']
            for n in row['nodes'] if n['side']=='self' and n['phase']=='root'
            for s in n['statuses'] if s['AffectsStat']==2005 and unconditional(s)]
    multiplier=max(values,default=0)/100
    bonuses={}
    for item in inventory:
        if item.get('category')!='Щиты':continue
        for name,value in component_bonuses(game_data(item)).items():
            if name in {'Парирование','Уклонение','Выносливость','Отражение'}:
                bonuses[name]=bonuses.get(name,0)+value*multiplier
    return bonuses

def weapon_requirement(row,inventory,active_set=1):
    from item_effects import active_equipment
    mask=row.get('weaponMask',0)
    if not mask:return ''
    categories={'Луки':32,'Щиты':4,'Одноручное оружие':2,'Двуручное оружие':16,'Парное оружие':8,'Посохи':128,'Метательное оружие':512,'Безоружное оружие':256}
    weapons=[i for i in active_equipment(inventory,active_set) if i.get('equipped_slot','').startswith('Оружие')]
    equipped=0 if weapons else 256
    for item in weapons:equipped|=categories.get(item.get('category'),0)
    if len(weapons)>1 and all(i.get('category')!='Щиты' for i in weapons):equipped|=8
    return '' if mask & equipped else 'Требуется подходящий тип оружия в активном комплекте.'
