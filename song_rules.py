"""Source-exported songs: stanza timing in seconds, advanced ten seconds per round."""
import copy


def phrase_profile(song,phrase,derived=None,tempo=0):
    from ability_rules import profile,RAW_SUPPORTED,CONTROL
    derived=derived or {}
    level=phrase['level'];source=song['song']
    recitation=(level*source['recitationPerLevel']+source['recitationBase'])*max(.1,1-tempo/100)
    linger=(level+source['lingerBase'])*max(.1,1+(derived.get('effectiveAttributes',{}).get('Стойкость',10)-10)*.03)
    runtime={int(k):v for k,v in derived.get('talentRuntime',{}).items()}
    radius=source['radius']+(runtime.get(2102,0) if source['type']==1 else 0)
    nodes=copy.deepcopy(phrase['nodes'])
    unsupported=[]
    for node in nodes:
        node['side']='target'
        for effect in node['statuses']:
            effect['Duration']=recitation+linger
            effect['Apply']=0
            effect.setdefault('TriggerAdjustment',{})
            effect.setdefault('ApplicationPrerequisites',[])
            if effect['AffectsStat'] not in RAW_SUPPORTED|{184,2011,2077} and node.get('tag') not in CONTROL:
                unsupported.append(effect['AffectsStat'])
    synthetic={**song,'key':phrase['key'],'name':phrase['name'],'nodes':nodes,'passive':False,'modal':False,
               'phrases':[],'song':None,'targeting':'area','area':radius,'range':radius,'skills':[34],
               'accuracyBonus':runtime.get(2103,0),'damageMin':0,'damageMax':0,'weaponMultiplier':0,
               'defense':phrase['defense'],'breathCost':0}
    result=profile(synthetic,derived)
    result['recitationSeconds']=round(recitation,4)
    result['lingerSeconds']=round(linger,4)
    if unsupported:result['supported']=False
    return result


def song_profile(song,derived=None):
    phrases=[phrase_profile(song,p,derived) for p in song['phrases']]
    supported=bool(phrases) and all(p['supported'] for p in phrases)
    return {**copy.deepcopy(song),'targeting':'self','targetTeam':'ally','range':0,'area':song['song']['radius'],
            'effects':[],'supported':supported,'unsupportedStats':sorted({s for p in phrases for s in p.get('unsupportedStats',[])}),
            'limitation':'' if supported else 'Некоторые эффекты стансов этой песни ещё не подключены.',
            'details':'Песня · стансы: '+str(len(phrases))+' · радиус: '+str(song['song']['radius'])+' клеток · один станс даёт одно дыхание',
            'phraseProfiles':phrases}


def breath_limit(talents):
    from ability_rules import resolve
    return max([1]+[r.get('breathCost',0) for t in talents for r in [resolve(t)] if r])


def advance(active,seconds,duration):
    """Emit next-stanza indices and sub-round offsets without rounding each stanza."""
    events=[];clock=0
    while clock+active['remainingSeconds']<=seconds+1e-6:
        clock+=active['remainingSeconds']
        active['phrase']=(active['phrase']+1)%active['phraseCount']
        active['remainingSeconds']=duration(active['phrase'])
        events.append((active['phrase'],round(clock,4)))
        if len(events)>100:raise ValueError('Некорректная длительность станса.')
    active['remainingSeconds']-=seconds-clock
    return events
