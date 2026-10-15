"""Explicit campaign classifications not reliably marked in game prefabs."""
import json

ARTIFACT_NAMES={'сгущающаяся тьма','власть закона'}
ARTIFACT_PREFABS={'WPN_1H_SK_Dagger_BledenMark','WPN_1H_SK_Dagger_BledenMark_Small',
                  'WPN_ENEMY_1H_IR_Dagger_BloodBound','WPN_STF_Tunon'}


def explicit_artifact(item):
    props=item.get('properties') or {}
    if isinstance(props,str):
        try:props=json.loads(props)
        except (TypeError,ValueError):props={}
    game=props.get('gameData',{})
    names=(item.get('name',''),game.get('craftBaseName',''))
    return game.get('prefab') in ARTIFACT_PREFABS or any(
        str(name).split(' (')[0].casefold() in ARTIFACT_NAMES for name in names)
