"""Contextual armor modifiers, keyed by original stat IDs and resolved prefabs."""
from item_effects import active_equipment, game_data, unconditional


def source_effects(inventory, active_set=1):
    for item in active_equipment(inventory, active_set):
        if item.get('equipped_slot')=='Эффект':continue
        game=game_data(item)
        for effect in game.get('statusEffects', []):
            if unconditional(effect):yield item,effect


def rules(inventory, active_set=1):
    result={}
    for _,effect in source_effects(inventory,active_set):
        stat=effect['AffectsStat'];value=float(effect.get('Value',0))
        if stat==101:result[stat]=result.get(stat,0)+value
        elif stat==2116:result[stat]=result.get(stat,1)*value
    return result


def affliction_tags(inventory, stat, active_set=1):
    """Resolved references avoid guessing an immunity from an item name."""
    result=set()
    for item in active_equipment(inventory,active_set):
        for mod in game_data(item).get('mods',[]):
            if not any(e.get('AffectsStat')==stat and unconditional(e) for e in mod.get('StatusEffectsOnEquip',[])):
                continue
            for entry in mod.get('triggerGraphs',[]):
                if entry.get('stat')!=stat:continue
                for node in entry['graph']:
                    if node.get('prefab'):result.add(node['prefab'].casefold())
                    if node.get('Tag'):result.add(node['Tag'].casefold())
    return result


def immune(inventory,effect,active_set=1):
    aliases={'root':'rooted','stun':'stun','prone':'prone','freeze':'frozen',
             'silence':'silenced','paralyze':'paralyzed','petrif':'petrified',
             'sleep':'asleep','blind':'blinded','disarm':'disarm','hobble':'hobbled'}
    keys=affliction_tags(inventory,150,active_set)
    return bool(keys & {str(effect.get('affliction','')).casefold(),
                        str(effect.get('control','')).casefold(),
                        aliases.get(effect.get('control'),'')})


def attack_modifiers(inventory, *, target_fraction=1, night=False, active_set=1):
    multiplier=1.;critical=0.
    for _,effect in source_effects(inventory,active_set):
        stat=effect['AffectsStat'];value=float(effect.get('Value',0))
        if stat==2169 and night:multiplier*=value
        elif stat==2137 and target_fraction*100<float(effect.get('ExtraValue',0)):
            critical+=value
    return {'multiplier':multiplier,'criticalChance':critical}
