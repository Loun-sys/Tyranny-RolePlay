"""Map actor identities inside persisted effects, not only their dictionary keys."""
import copy

FIELDS={'sourceId','transferOwner','bondPartner','summonedBy','targetId'}
def remap(value,old,new):
    if isinstance(value,list):return [remap(v,old,new) for v in value]
    if not isinstance(value,dict):return copy.deepcopy(value)
    return {key:new if key in FIELDS and v==old else remap(v,old,new) for key,v in value.items()}
