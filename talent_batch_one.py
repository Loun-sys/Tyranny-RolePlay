"""First 30 of the remaining 110: exact source keys, not translated-name guesses."""
BATCH_KEYS=(
 'PSV_PC_Defense_BladeWall_1of2','PSV_PC_Defense_BladeWall_2of2',
 'PSV_Comp_Defender_SeasonedVeteran_1','PSV_Comp_Defender_SeasonedVeteran_2','PSV_Comp_Beastwoman_PackLeader',
 'PSV_Comp_Defender_EngagementAttack_1','PSV_Comp_Defender_EngagementAttack_2','PSV_Comp_Defender_EngagementAttack_3',
 'PSV_Comp_Defender_GloryToTheBold','PSV_Comp_Sirin_GuiseOfInnocence','PSV_Comp_Sirin_GuiseOfInnocence_2of2',
 'PSV_Comp_Beastwoman_BestialConstitution','PSV_Comp_Lantry_LearnedInstructor_01',
 'PSV_Comp_Sirin_Inspiration','PSV_Comp_Beastwoman_WildInstinct','PSV_Comp_Verse_BattleMind_01',
 'PSV_Comp_Defender_TrainingGround','PSV_PC_Power_Rampage','PSV_PC_Defense_PinningStrike',
 'PSV_PC_Power_ExposeWeakness','PSV_PC_Leadership_SeizeTheInitiative','PSV_PC_Magic_EnfeeblingTouch',
 'PSV_PC_Agility_UnseenAdvantage','PSV_PC_Ranged_TerrorShot','PSV_Comp_Beastwoman_TasteOfBlood',
 'PSV_Comp_Lantry_ChargedThrow','Abl_PC_Defense_StaggeringForce','Abl_PC_Leadership_ToArms',
 'Abl_Comp_Defender_SoundOfWar','PSV_Comp_RngMagic_SurgingWaters',
)

def family(key):
    import re
    return re.sub(r'_(?:\d+of\d+|\d+)$','',key)

def roots(talents):
    from ability_rules import resolve
    for talent in talents:
        row=resolve(talent)
        if row and row['passive'] and not row.get('modal') and not row.get('isTalentUpgrade'):
            for node in row['nodes']:
                if node['phase']=='root' and node['side']=='self':
                    for effect in node['statuses']:yield row,effect

def skill_xp_bonuses(talents):
    from ability_rules import SKILLS
    # Original SkillType: Stealth=1, MagicStaff=11 (8 is spell attack skill).
    source_skills={**SKILLS,1:'Хитроумие',11:'Волшебный посох',24:'Управление эмоциями',
                   26:'Управление эмоциями',27:'Управление могильным светом'}
    ranks={}
    for row,effect in roots(talents):
        if effect['AffectsStat']!=2113 or row['key'] not in BATCH_KEYS:continue
        name=source_skills.get(effect.get('Skill'))
        if name:
            key=(family(row['key']),name)
            ranks[key]=max(ranks.get(key,1),float(effect['Value']))
    result={}
    for (_,name),value in ranks.items():result[name]=result.get(name,0)+value-1
    return result

def party_xp_multiplier(members,skill):
    # CharacterStats.GatherPartySkillXPMultiplier adds each member's bonus.
    return 1+sum(skill_xp_bonuses(m.get('talents',m.get('abilities',[]))).get(skill,0) for m in members)

def engagement_level(talents):
    return max(((int(e['Value']),float(e.get('ExtraValue',0))/100)
                for _,e in roots(talents) if e['AffectsStat']==2126),default=(0,0))

def kill_effects(talents):
    for row,e in roots(talents):
        if e['AffectsStat']==185 and e.get('TriggerAdjustment',{}).get('Type')==7:yield row,e

def condition_supported(effect):
    return effect['AffectsStat']==185 and effect.get('TriggerAdjustment',{}).get('Type')==7

def reactive_profiles(talents,derived):
    from ability_rules import resolve,profile
    for talent in talents:
        row=resolve(talent)
        if not row or row['key']!='PSV_Comp_RngMagic_SurgingWaters':continue
        rule=profile(row,derived)
        if rule['supported']:yield rule,float(row['source']['activation'][0]['Value'])
