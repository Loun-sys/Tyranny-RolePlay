"""Клеточная пошаговая тренировка персонажа против неподвижного манекена."""

from __future__ import annotations

import math
import copy
import random
import re
from dataclasses import dataclass, field
from typing import Any

from constants import ABILITY_DETAILS
from sigil_data import spell_runtime_profile
from persistent_spells import persistent_profile
from tactical_grid import BASE_MOVEMENT, TACTICAL_MAPS, TacticalGrid, initiative_bonus


DUMMY = {
    "name": "Укреплённый тренировочный манекен",
    "healthMax": 180,
    "armor": 4,
    "defenses": {"Парирование": 35, "Уклонение": 30, "Выносливость": 32, "Воля": 28, "Магия": 32},
}

TRAINING_TARGETS = {
    "dummy": {**DUMMY, "name": "Укреплённый тренировочный манекен", "healthMax": 180, "position": (10, 4)},
    "dummy_left": {**DUMMY, "name": "Левый манекен", "healthMax": 100, "position": (10, 2)},
    "dummy_right": {**DUMMY, "name": "Правый манекен", "healthMax": 100, "position": (10, 6)},
}

ATTACKING_ABILITIES = {
    "Удар щитом": (1.0, 0), "Раскол": (1.5, 0), "Секущий удар": (.8, 5),
    "Выстрел в сердце": (1.2, 0), "Хромота": (1.0, 0), "Шквал ударов": (2.0, 0),
    "Рассечение": (1.2, 0), "Удар ладонью": (1.0, 0), "Заряженный кулак": (1.0, 2),
    "Ледяная хватка": (1.0, 1), "Рывок": (1.2, 0), "Удар в прыжке": (1.4, 0),
}
RANGED_ABILITIES = {"Выстрел в сердце": 12, "Хромота": 10, "Рывок": 10, "Удар в прыжке": 6}
FORCED_MOVEMENT = {"Удар ладонью": ("push", 3), "Заряженный кулак": ("push", 2), "Ледяная хватка": ("pull", 2)}
MOBILITY_ABILITIES = {
    "Рывок": {"description": "Перемещает персонажа к цели на расстоянии до 10 м и наносит 120% урона.",
               "type": "Ловкость · рывок", "cooldown": "3 раунда", "icon": ""},
    "Удар в прыжке": {"description": "Телепортационное перемещение на свободную клетку рядом с целью и мощный удар.",
                       "type": "Ловкость · телепортация", "cooldown": "4 раунда", "icon": ""},
}

CORE_SKILLS = {
    "Истощение": "Управление истощением", "Эмоции": "Управление рвением",
    "Огонь": "Управление огнём", "Сила": "Управление силой",
    "Холод": "Управление холодом", "Иллюзия": "Управление иллюзиями",
    "Жизнь": "Управление жизнью", "Молния": "Управление молниями",
    "Камень": "Управление камнем", "Терратус": "Управление могильным светом",
    "Рвение": "Управление рвением",
}
CORE_DAMAGE = {
    "Огонь": "огненного", "Холод": "ледяного", "Молния": "электрического",
    "Сила": "дробящего", "Камень": "дробящего", "Жизнь": "магического",
    "Истощение": "магического", "Эмоции": "магического", "Иллюзия": "магического",
    "Терратус": "магического", "Рвение": "магического",
}


def _number(value: Any, default: float = 0) -> float:
    match = re.search(r"\d+(?:[.,]\d+)?", str(value or ""))
    return float(match.group().replace(",", ".")) if match else default


def _round_word(value: int) -> str:
    if value % 10 == 1 and value % 100 != 11:
        return "раунд"
    if value % 10 in {2, 3, 4} and value % 100 not in {12, 13, 14}:
        return "раунда"
    return "раундов"


@dataclass
class TrainingSession:
    character_id: int
    round_number: int = 1
    dummy_health: int = DUMMY["healthMax"]
    damage_total: int = 0
    attacks: int = 0
    hits: int = 0
    active_weapon_set: int = 1
    cooldowns: dict[str, int] = field(default_factory=dict)
    log: list[str] = field(default_factory=list)
    map_key: str = "training_grounds"
    player_position: tuple[int, int] = (2, 4)
    dummy_position: tuple[int, int] = (10, 4)
    movement_remaining: int = BASE_MOVEMENT
    action_available: bool = True
    initialized: bool = False
    initiative: list[dict[str, Any]] = field(default_factory=list)
    selected_target_id: str = "dummy"
    target_healths: dict[str, int] = field(default_factory=lambda: {
        key: int(row["healthMax"]) for key, row in TRAINING_TARGETS.items()
    })
    target_positions: dict[str, tuple[int, int]] = field(default_factory=lambda: {
        key: tuple(row["position"]) for key, row in TRAINING_TARGETS.items()
    })
    player_health: int = 0
    player_health_max: int = 0
    player_base_health_max: int = 0
    disengaged: bool = False
    preview_cells: set[tuple[int, int]] = field(default_factory=set)
    active_stance: str = ""
    active_songs: list[dict[str, Any]] = field(default_factory=list)
    breath: int = 0
    aim_point: tuple[int, int] | None = None
    opportunity_used: set[str] = field(default_factory=set)
    areas: list[dict[str, Any]] = field(default_factory=list)
    conditions: dict[str, dict[str, Any]] = field(default_factory=dict)
    movement_path: list[tuple[int, int]] = field(default_factory=list)
    targets: dict[str, Any] = field(default_factory=lambda: {k: copy.deepcopy(v) for k,v in TRAINING_TARGETS.items()})
    custom_map: dict[str, Any] | None = None

    def __post_init__(self) -> None:
        spec = self.custom_map or TACTICAL_MAPS[self.map_key]
        coordinates = lambda rows: {(int(p['x']),int(p['y'])) if isinstance(p,dict) else tuple(p) for p in rows}
        self.grid = TacticalGrid(spec["width"], spec["height"], coordinates(spec['blocked']),
                                 coordinates(spec['sightBlocked']) if 'sightBlocked' in spec else None,
                                 coordinates(spec.get('cover',[])))
        if self.custom_map:
            if 'resolvedTokens' in spec and not spec.get('spawns'):
                tokens = spec['resolvedTokens']
                player = next(p for p in tokens if p.get('kind')=='player' and p['id']==self.character_id)
                self.player_position = (player['x'],player['y'])
                self.targets = {f"token_{i}": {**p,'healthMax':int(p['healthMax']),
                    'armor':int(p.get('armor',0)), 'defenses':{**DUMMY['defenses'],**p.get('defenses',{})}}
                    for i,p in enumerate(tokens) if p is not player}
                self.target_positions = {k:(p['x'],p['y']) for k,p in self.targets.items()}
                self.target_healths = {k:p['healthMax'] for k,p in self.targets.items()}
                enemies = self._alive_targets()
                self.selected_target_id = enemies[0] if enemies else next(iter(self.targets),'')
            else:
                spawns = spec.get('spawns',{})
                if 'player' in spawns:self.player_position=(spawns['player']['x'],spawns['player']['y'])
                self.target_positions={key:(spawns[key]['x'],spawns[key]['y']) for key in self.targets if key in spawns}
                self.targets={key:row for key,row in self.targets.items() if key in self.target_positions}
                self.target_healths={key:row['healthMax'] for key,row in self.targets.items()}

    @property
    def finished(self) -> bool:
        return not self._alive_targets()

    def _initialize(self, character: dict[str, Any]) -> None:
        if self.initialized:
            return
        quickness = int(character.get("attributes", {}).get("Быстрота", 10))
        self.player_health_max = int(character.get("health_max", character.get("health", 1)))
        self.player_base_health_max = self.player_health_max
        self.player_health = int(character.get("health", self.player_health_max))
        bonus = initiative_bonus(quickness)
        player_roll = random.randint(1, 20)
        self.initiative = [
            {"id": "player", "name": character.get("name", "Персонаж"), "roll": player_roll,
             "bonus": bonus, "total": player_roll + bonus},
        ]
        for target_id in [k for k,h in self.target_healths.items() if h>0]:
            roll = random.randint(1, 20)
            self.initiative.append({"id": target_id, "name": self.targets[target_id]["name"],
                                    "roll": roll, "bonus": initiative_bonus(int(self.targets[target_id].get("attributes",{}).get("Быстрота",10))), "total": roll + initiative_bonus(int(self.targets[target_id].get("attributes",{}).get("Быстрота",10)))})
        self.initiative.sort(key=lambda row: (-row["total"], row["id"] != "player"))
        self.initialized = True
        from song_rules import breath_limit
        from talent_runtime import effects
        self.breath=min(breath_limit(character.get('talents',[])),int(effects(character.get('talents',[])).get(2099,0)))
        self.movement_remaining=self._movement_limit()
        self.log.append("Инициатива: " + " → ".join(row["name"] for row in self.initiative) + ".")
        for entry in self.initiative:
            if entry['id'] == 'player':
                break
            self.log.append(f"Раунд 1: {entry['name']} неподвижен и пропускает ход.")
        self.log.append("Тренировка началась. Перед атакой приблизьтесь к цели, если она вне дальности.")

    def remaining(self, key: str) -> int:
        if key.startswith('ability:'):
            from ability_rules import resolve
            row=resolve(key.removeprefix('ability:'))
            if row:key='ability:'+row['key']
        return max(0, int(self.cooldowns.get(key, 0)) - self.round_number)

    def _cooldown(self, base: float, multiplier: float) -> int:
        return max(1, math.ceil(max(0, base) * max(.1, multiplier)))

    @staticmethod
    def _weapon_range(attack: dict[str, Any]) -> int:
        if attack.get('range'):return max(1,math.ceil(attack['range']))
        return {"Луки": 12, "Дротики": 6, "Волшебный посох": 10, "Волшебные посохи": 10}.get(attack.get("skill"), 1)

    def _distance(self) -> int:
        return self.grid.distance(self.player_position, self.target_positions.get(self.selected_target_id,self.player_position))

    def _alive_targets(self) -> list[str]:
        return [key for key, health in self.target_healths.items() if health > 0 and self.targets[key].get("team","enemy")=="enemy"]

    def _occupied(self, exclude=None):
        """All living tokens occupy a cell, including allies and the acting player."""
        cells={self.target_positions[k] for k,h in self.target_healths.items() if h>0 and k!=exclude}
        if exclude!='player' and self.player_health>0:cells.add(self.player_position)
        return cells

    @staticmethod
    def _cell(payload):
        values=[]
        for name in ('x','y'):
            value=payload.get(name)
            try:
                coordinate=int(value)
                if isinstance(value,bool) or isinstance(value,float) and value!=coordinate:
                    raise ValueError
                if isinstance(value,str) and str(coordinate)!=value.strip():raise ValueError
            except (TypeError,ValueError,OverflowError):
                raise ValueError('Координаты клетки должны быть целыми числами.') from None
            values.append(coordinate)
        return tuple(values)

    def _target(self, target_id: str | None = None) -> dict[str, Any]:
        key = target_id or self.selected_target_id
        if key not in self.targets:
            return {**DUMMY,'id':'','health':0,'x':self.player_position[0],'y':self.player_position[1]}
        row = self.targets[key]
        return {**row, "id": key, "health": self.target_healths[key],
                "x": self.target_positions[key][0], "y": self.target_positions[key][1]}

    def _defense(self, name, target_id=None):
        target=target_id or self.selected_target_id
        base=self.targets[target]['defenses'].get(name,30)
        from consumables import virtual_equipment
        from registration_api import _apply_property
        base=_apply_property(base,virtual_equipment(self.conditions.get(target,{}),self.round_number),name)
        for state in self.conditions.get(target,{}).values():
            if state.get('kind')==name:
                value=state['value'];base=base*(1+value) if abs(value)<1 else base+value
        return max(0,round(base))

    def _apply_special(self, effect, target):
        from talent_runtime import hostile_duration
        if effect.get('side')!='self':
            scaled=hostile_duration({**effect,'IsHostile':True,'Duration':effect['rounds']*10},
                                    getattr(self,'talent_runtime',{}),self._target_talent_rules(target))
            effect={**effect,'rounds':scaled['rounds']}
        kind,value=effect['kind'],effect['value']
        states=self.conditions.setdefault(target,{})
        if kind=='purge':
            for key in list(states):
                if states[key].get('beneficial'):states.pop(key)
        elif kind=='drain':
            amount=min(self.target_healths.get(target,0),max(0,round(value)))
            self.target_healths[target]=max(0,self.target_healths[target]-amount)
            self.player_health=min(self.player_health_max,self.player_health+amount)
            self.damage_total+=amount
        elif kind=='healPercent':
            self.player_health=min(self.player_health_max,self.player_health+math.ceil(self.player_health_max*value))
        else:
            states['special:'+kind]={**effect,'stacks':1,'beneficial':effect['side']=='self',
                'until':self.round_number+effect['rounds']-1,'triggerRound':self.round_number+effect['rounds']}
        self.log.append(f"{effect['name']}: {self.targets.get(target,{}).get('name','Персонаж')}; длительность {effect['rounds'] if effect['rounds']<999999 else 'до конца боя'}.")

    def _apply_ability_effects(self, rule, target, side):
        from consumables import apply
        from talent_runtime import hostile_duration
        raw=[];states=self.conditions.setdefault(target,{})
        for effect in rule.get('effects',[]):
            if effect['side']!=side:continue
            effect=hostile_duration(effect,getattr(self,'talent_runtime',{}),self._target_talent_rules(target))
            if effect.get('control') or effect.get('AffectsStat') in {18,121}:
                effect={**effect,'control':effect.get('control') or {18:'root',121:'silence'}[effect['AffectsStat']]}
                key=effect['control'];rounds=max(1,math.ceil(effect.get('Duration',10)/10))
                states[key]={'name':effect['name'] or key,'kind':key,'until':self.round_number+rounds-1,'stacks':1,'beneficial':False,
                             'abilityKey':rule['key'],'durationSeconds':effect.get('Duration',10)}
            else:raw.append(effect)
        if not raw:return
        synthetic={'properties':{'gameData':{'prefab':rule['key'],'useComponents':[{'StatusEffects':raw}]}}}
        if target=='player':
            self.player_health=apply(synthetic,states,self.round_number,self.player_health,self.player_health_max)
        else:
            before=self.target_healths[target]
            self.target_healths[target]=apply(synthetic,states,self.round_number,before,self.targets[target]['healthMax'])
            self.damage_total+=max(0,before-self.target_healths[target])

    def _target_talent_rules(self,target):
        from talent_runtime import effects
        if target=='player':return getattr(self,'talent_runtime',{})
        actor=self.targets.get(target,{})
        if 'talentRuntime' in actor:return {int(k):v for k,v in actor['talentRuntime'].items()}
        equipment=[]
        for item in actor.get('equipment',[]):
            slot=item.get('slot','')
            if slot in {'PrimaryWeapon','SecondaryWeapon'}:
                equipment.append({**item,'equipped_slot':'Оружие I — '+('правая рука' if slot=='PrimaryWeapon' else 'левая рука')})
            elif slot:equipment.append({**item,'equipped_slot':slot})
        return effects(actor.get('abilities',[]),equipment)

    def _execute_ability(self, rule, derived, inventory):
        from ability_rules import weapon_requirement
        requirement=weapon_requirement(rule,inventory,self.active_weapon_set)
        if requirement:raise ValueError(requirement)
        if not rule['supported']:raise ValueError(rule['limitation'])
        if rule.get('song'):return self._toggle_song(rule,derived)
        if rule.get('breathCost',0)>self.breath:raise ValueError('Недостаточно дыхания для этой арии.')
        self._require_action(0 if rule['targeting']=='self' else rule['range'])
        key='ability:'+rule['key']
        if self.remaining(key):raise ValueError('Способность ещё перезаряжается.')
        friendly=rule.get('targetTeam')=='ally'
        targets=self._ability_targets(rule)
        if rule['targeting']!='self' and not targets:raise ValueError('В области нет доступной цели.')
        if rule.get('movementEffect')=='swap':
            target=next((k for k in targets if k!='player'),None)
            if target is None:raise ValueError('Выберите союзника, чтобы поменяться местами.')
            self.player_position,self.target_positions[target]=self.target_positions[target],self.player_position
        attack=derived['attack'];total=0;lines=[]
        from item_effects import DAMAGE_TYPES
        for target in targets:
            if friendly:
                self._apply_ability_effects(rule,target,'target')
                continue
            landed=False
            for _ in range(rule.get('attackCount',1)):
                factor=rule.get('weaponMultiplier',0)
                low=round(attack['damageMin']*factor) if factor else round(rule['damageMin'])
                high=round(attack['damageMax']*factor) if factor else round(rule['damageMax'])
                engaged=sum(self.grid.distance(self.player_position,self.target_positions[k])<=1 for k in self._alive_targets())
                for effect in rule['effects']:
                    if effect.get('AffectsStat')==2072 and self.grid.distance(self.player_position,self.target_positions[target])<=1:
                        low=round(low*effect['Value']);high=round(high*effect['Value'])
                    elif effect.get('AffectsStat')==2013:
                        mult=1+effect['Value']/100*engaged;low=round(low*mult);high=round(high*mult)
                cover_name,cover_bonus=self.grid.cover(self.player_position,self.target_positions[target])
                if cover_name=='полное':continue
                result=self._roll_attack(name=rule['name'],accuracy=rule['accuracy'],low=low,high=high,
                    defense=self._defense(rule['defense'],target) if rule['defense']!='Нет' else 0,
                    armor=self.targets[target]['armor'],penetration=rule['penetration'],target_id=target,
                    cover_bonus=cover_bonus if rule['targeting']=='unit' and rule['range']>1 else 0,
                    damage_type=DAMAGE_TYPES.get(rule.get('damageType'),'физического').lower(),
                    attack_mode=__import__('talent_runtime').weapon_mode(attack,rule) if factor else 'spell',defense_name=rule['defense'])
                total+=result['damage'];lines.append(result['line']);landed|=result['result'] not in {'Промах','Отражено'}
                if factor:self._weapon_talent_procs(target,result['result'])
            if landed:
                self._apply_ability_effects(rule,target,'target')
                if rule.get('push') and self.target_healths[target]>0:
                    self.target_positions[target]=self.grid.displace(self.player_position,self.target_positions[target],max(1,math.ceil(abs(rule['push']))),self._occupied(target),pull=rule['push']<0)
        self._apply_ability_effects(rule,'player','self')
        self.cooldowns[key]=999999 if rule['oncePerBattle'] else self.round_number+rule['cooldown']+1
        self.breath-=rule.get('breathCost',0)
        line=' '.join(lines) or f"Применена способность «{rule['name']}»."
        if not lines:self.log.append(line)
        return {'result':'Способность применена','damage':total,'line':line}

    def _ability_targets(self, rule):
        cells=self._spell_cells(rule)
        friendly=rule.get('targetTeam')=='ally'
        if friendly:
            unconscious=rule.get('targetType') in {3,104,102}
            targets=[k for k,h in self.target_healths.items() if (h<=0 if unconscious else h>0)
                     and self.targets[k].get('team','enemy')!='enemy' and self.target_positions[k] in cells]
            if self.player_position in cells and rule.get('targetType')!=13 and (self.player_health<=0 if unconscious else self.player_health>0):targets.append('player')
        else:
            if rule['targeting']=='self' and rule.get('area') and (rule.get('damageMax') or rule.get('weaponMultiplier') or rule.get('push')):
                cells=self.grid.radius_cells(self.player_position,rule['area'])
                targets=[k for k in self._alive_targets() if self.target_positions[k] in cells]
            else:targets=[] if rule['targeting']=='self' else [k for k in self._alive_targets() if self.target_positions[k] in cells]
        return [k for k in targets if self.grid.line_of_sight(self.player_position,self.player_position if k=='player' else self.target_positions[k])]

    def _song_tempo(self):
        from ability_rules import resolve
        stance=resolve(self.active_stance)
        return sum(s['Value'] for n in stance['nodes'] for s in n['statuses'] if s['AffectsStat']==2114) if stance else 0

    def _song_phrase(self,song,index,derived,offset=0):
        from song_rules import phrase_profile
        p=phrase_profile(song,song['phrases'][index],derived,self._song_tempo())
        if not p['supported']:raise ValueError('Этот станс содержит неподключённые эффекты.')
        for target in ['player',*self.target_healths]:
            if (self.player_health if target=='player' else self.target_healths[target])<=0:continue
            position=self.player_position if target=='player' else self.target_positions[target]
            if self.grid.distance(self.player_position,position)>p['area']:continue
            if not self.grid.line_of_sight(self.player_position,position):continue
            enemy=target!='player' and self.targets[target].get('team','enemy')=='enemy'
            chosen=[e for e in p['effects'] if bool(e.get('control') or e.get('IsHostile'))==enemy]
            if not chosen:continue
            if enemy and p['defense']!='Нет':
                hit=self._roll_attack(name=p['name'],accuracy=p['accuracy'],low=0,high=0,
                    defense=self._defense(p['defense'],target),armor=0,target_id=target,
                    attack_mode='spell',defense_name=p['defense'])
                if hit['result'] in {'Промах','Отражено'}:continue
            # A fast song can loop within a round. Tick the previous copy before
            # refreshing it; otherwise its elapsed damage/healing would be lost.
            from consumables import pulse
            previous={k:s for k,s in self.conditions.get(target,{}).items() if k.startswith('consumable:'+p['key']+':')}
            if previous and offset:
                before=self.player_health if target=='player' else self.target_healths[target]
                after=pulse(previous,self.round_number+1,before,
                            self.player_health_max if target=='player' else self.targets[target]['healthMax'],elapsed_seconds=offset)
                if target=='player':self.player_health=after
                else:
                    self.target_healths[target]=after
                    self.damage_total+=max(0,before-after)
            self._apply_ability_effects({**p,'effects':[{**e,'side':'target'} for e in chosen]},target,'target')
            for key,state in self.conditions.get(target,{}).items():
                if key.startswith('consumable:'+p['key']+':') or state.get('abilityKey')==p['key']:
                    duration=state.get('source',{}).get('Duration',state.get('durationSeconds',0))
                    state['until']=self.round_number+max(1,math.ceil((offset+duration)/10))-1
                    state['pulseDelaySeconds']=offset
        self.log.append(p['name'])
        return p['recitationSeconds']

    def _toggle_song(self,song,derived):
        if any(k in self.conditions.get('player',{}) for k in ('silence','stun','paralyze','petrif','freeze','sleep')):
            raise ValueError('Под этим воздействием нельзя петь.')
        previous=next((s for s in self.active_songs if s['key']==song['key']),None)
        if previous:
            self.active_songs.remove(previous)
            return {'result':'Пение остановлено','damage':0,'line':song['name'],'consumesAction':False}
        capacity=2 if 2101 in getattr(self,'talent_runtime',{}) else 1
        if len(self.active_songs)>=capacity:
            raise ValueError('Сначала остановите активную песню: доступно '+str(capacity)+' одновременно.')
        seconds=self._song_phrase(song,0,derived)
        self.active_songs.append({'key':song['key'],'phrase':0,'phraseCount':len(song['phrases']),'remainingSeconds':seconds})
        return {'result':'Пение начато','damage':0,'line':song['name'],'consumesAction':False}

    def _advance_songs(self):
        from song_rules import advance,phrase_profile,breath_limit
        from ability_rules import resolve
        if self.player_health<=0:return
        if any(k in self.conditions.get('player',{}) for k in ('silence','stun','paralyze','petrif','freeze','sleep')):return
        derived=getattr(self,'runtime_derived',{})
        for active in self.active_songs:
            song=resolve(active['key'])
            if not song:continue
            def duration(i):return phrase_profile(song,song['phrases'][i],derived,self._song_tempo())['recitationSeconds']
            for index,offset in advance(active,10,duration):
                self.breath=min(breath_limit(getattr(self,'runtime_talents',[])),self.breath+1)
                self._song_phrase(song,index,derived,offset)

    def master_npc_ability(self, actor_id, ability_key, target_id, player, player_derived):
        """Master-only simulation; NPCs use the same executor as player abilities."""
        import copy
        from ability_rules import profile
        from npc_store import refresh_ability
        if actor_id not in self.targets or self.targets[actor_id].get('kind')!='npc':raise ValueError('Выберите токен НПС на карте.')
        if self.target_healths[actor_id]<=0:raise ValueError('НПС выведен из боя.')
        if getattr(self,'npc_spent',{}).get(actor_id)==self.round_number:raise ValueError('НПС уже потратил действие в этом раунде.')
        npc=self.targets[actor_id]
        ability=next((a for a in npc.get('abilities',[]) if ability_key in {a.get('key'),a.get('prefab')}),None)
        if not ability or ability.get('passive'):raise ValueError('Эта активная способность не назначена НПС.')
        derived={'attack':npc.get('attack',{}),'effectiveSkills':npc.get('skills',{}),'effectiveAttributes':npc.get('attributes',{}),
                 'cooldownMultiplier':max(.1,1-(npc.get('attributes',{}).get('Быстрота',10)-10)*.03)}
        rule=profile(refresh_ability(ability),derived,npc.get('attack',{}).get('range',1))
        if rule.get('song'):raise ValueError('Автоматическое пение НПС ещё не подключено; эта песня доступна персонажу игрока.')
        clone=copy.deepcopy(self);player_target='master_player'
        clone.targets={k:v for k,v in clone.targets.items() if k!=actor_id}
        for n in clone.targets.values():n['team']='ally' if n.get('team','enemy')==npc.get('team','enemy') else 'enemy'
        clone.targets[player_target]={'name':player['name'],'healthMax':self.player_health_max,'armor':player_derived['armor'],
            'armorByType':player_derived.get('armorByType',{}),'defenses':player_derived['defenses'],
            'incomingConversions':player_derived.get('incomingConversions',{}),
            'talentRuntime':player_derived.get('talentRuntime',{}),
            'team':'enemy' if npc.get('team','enemy')=='enemy' else 'ally'}
        clone.target_healths={k:v for k,v in clone.target_healths.items() if k!=actor_id};clone.target_healths[player_target]=self.player_health
        clone.target_positions={k:v for k,v in clone.target_positions.items() if k!=actor_id};clone.target_positions[player_target]=self.player_position
        clone.conditions={k:v for k,v in clone.conditions.items() if k not in {'player',actor_id}}
        clone.conditions[player_target]=copy.deepcopy(self.conditions.get('player',{}));clone.conditions['player']=copy.deepcopy(self.conditions.get(actor_id,{}))
        clone.player_position=self.target_positions[actor_id];clone.player_health=self.target_healths[actor_id];clone.player_health_max=npc['healthMax']
        clone.action_available=True;clone.cooldowns=copy.deepcopy(getattr(self,'npc_cooldowns',{}).get(actor_id,{}))
        clone.selected_target_id=player_target if target_id=='player' else target_id
        if rule['targeting']=='self':clone.aim_point=clone.player_position
        else:
            if clone.selected_target_id not in clone.targets or clone.target_healths[clone.selected_target_id]<=0:raise ValueError('Выберите живую цель.')
            clone.aim_point=clone.target_positions[clone.selected_target_id]
        equipped=[]
        for i in npc.get('equipment',[]):
            if i.get('slot') in {'PrimaryWeapon','SecondaryWeapon'}:equipped.append({**i,'equipped_slot':'Оружие I — '+('правая рука' if i['slot']=='PrimaryWeapon' else 'левая рука')})
        from talent_runtime import effects as talent_effects
        clone.talent_runtime=talent_effects(npc.get('abilities',[]),equipped)
        clone.runtime_talents=npc.get('abilities',[]);clone.runtime_derived=derived
        clone.consumable_inventory=equipped
        before_log=len(clone.log);result=clone._execute_ability(rule,derived,equipped)
        self.player_health=clone.target_healths[player_target];self.player_position=clone.target_positions[player_target]
        self.conditions['player']=clone.conditions.get(player_target,{})
        self.target_healths[actor_id]=clone.player_health;self.target_positions[actor_id]=clone.player_position;self.conditions[actor_id]=clone.conditions.get('player',{})
        for key in self.targets:
            if key!=actor_id:
                self.target_healths[key]=clone.target_healths[key];self.target_positions[key]=clone.target_positions[key];self.conditions[key]=clone.conditions.get(key,{})
        self.log.extend(f"{npc['name']}: {line}" for line in clone.log[before_log:])
        self.npc_cooldowns={**getattr(self,'npc_cooldowns',{}),actor_id:clone.cooldowns}
        self.npc_spent={**getattr(self,'npc_spent',{}),actor_id:self.round_number}
        return result

    def _combat_derived(self, derived):
        import copy
        result=copy.deepcopy(derived)
        self.talent_runtime={int(k):v for k,v in result.get('talentRuntime',{}).items()}
        health_fraction=self.player_health/max(1,self.player_health_max) if self.initialized else 1
        result['cooldownMultiplier']=result.get('cooldownMultiplier',1)*max(.1,1-self.talent_runtime.get(2109,0)*(1-health_fraction))
        self.equipment_movement_multiplier=result.get('movementMultiplier',1)
        attrs=result.setdefault('effectiveAttributes',{})
        attack=result.setdefault('attack',{})
        for state in self.conditions.get('player',{}).values():
            kind,value=state.get('kind'),state.get('value',0)
            if kind in {'Сила','Искусность','Быстрота','Живучесть','Смекалка','Стойкость'}:
                old=attrs.get(kind,10);attrs[kind]=max(1,old+round(value))
                if kind=='Сила':
                    ratio=max(.1,1+(attrs[kind]-10)*.03)/max(.1,1+(old-10)*.03)
                    for k in ['damageMin','damageMax']:attack[k]=round(attack.get(k,1)*ratio)
                if kind=='Искусность':attack['accuracy']=attack.get('accuracy',20)+round(value)
                if kind=='Быстрота':result['cooldownMultiplier']=max(.1,result.get('cooldownMultiplier',1)-value*.03)
                if kind=='Стойкость':
                    for defense in ['Выносливость','Воля','Магия']:
                        result.setdefault('defenses',{})[defense]=result.get('defenses',{}).get(defense,20)+round(value*1.5)
            elif kind=='accuracy':attack['accuracy']=attack.get('accuracy',20)+round(value)
            elif kind=='armor':result['armor']=max(0,result.get('armor',0)+round(value))
            elif kind=='cooldown':result['cooldownMultiplier']=result.get('cooldownMultiplier',1)*value
        if any(s.get('source',{}).get('AffectsStat')==2129 for s in self.conditions.get('player',{}).values()):
            result['equipmentRecovery']=0
            attack['recovery']=0
        if self.initialized:
            self.player_base_health_max = int(result.get('healthMax', self.player_base_health_max))
            if not self.conditions.get('player', {}).get('restore'):
                self.player_health_max = self.player_base_health_max
                self.player_health = min(self.player_health, self.player_health_max)
        return result

    def _weapon_talent_procs(self,target_id,result):
        from ability_rules import resolve,proc_profiles,weapon_requirement
        if getattr(self,'resolving_talent_proc',False) or result in {'Промах','Отражено'}:return
        if self.target_healths[target_id]<=0:return
        self.resolving_talent_proc=True
        try:
            for talent in getattr(self,'runtime_talents',[]):
                row=resolve(talent)
                if not row or row.get('isTalentUpgrade'):continue
                if row.get('modal') and row['name']!=self.active_stance:continue
                if not row['passive'] and not row.get('modal'):continue
                if weapon_requirement(row,getattr(self,'consumable_inventory',[]),self.active_weapon_set):continue
                for proc in proc_profiles(row,getattr(self,'runtime_derived',{})):
                    if proc['triggerStat']==2156 and result!='Критическое попадание':continue
                    ranged=self._weapon_range(getattr(self,'runtime_derived',{}).get('attack',{}))>1
                    if proc['weaponTrigger'] in {0,1} and ranged!=(proc['weaponTrigger']==1):continue
                    hit=self._roll_attack(name=proc['name'],accuracy=proc['accuracy'],low=round(proc['damageMin']),
                        high=round(proc['damageMax']),defense=self._defense(proc['defense'],target_id) if proc['defense']!='Нет' else 0,
                        armor=self.targets[target_id]['armor'],target_id=target_id,penetration=proc['penetration'])
                    if hit['result'] not in {'Промах','Отражено'}:
                        self._apply_ability_effects(proc,target_id,'target');self._apply_ability_effects(proc,'player','self')
        finally:self.resolving_talent_proc=False

    def _movement_limit(self):
        multiplier=getattr(self,'equipment_movement_multiplier',1)
        for state in self.conditions.get('player',{}).values():
            if state.get('kind')=='movement':multiplier*=state['value']
        return max(1,math.floor(BASE_MOVEMENT*multiplier))

    def _require_action(self, distance: int) -> None:
        controls=self.conditions.get('player',{})
        if any(controls.get(k) for k in ('stun','paralyze','petrif','freeze','sleep','prone')):
            raise ValueError('Персонаж под воздействием контроля: завершите ход.')
        if not self.action_available:
            raise ValueError("Основное действие в этом ходу уже потрачено.")
        if distance == 0:
            return
        target = self.aim_point or self.target_positions.get(self.selected_target_id,self.player_position)
        actual = self.grid.distance(self.player_position, target)
        if actual > distance:
            raise ValueError(f"Цель в {actual} м, а дальность действия — {distance} м.")
        if distance > 1 and not self.grid.line_of_sight(self.player_position, target):
            raise ValueError("Линию обзора перекрывает препятствие.")

    def _roll_attack(
        self, *, name: str, accuracy: int, low: int, high: int, defense: int,
        armor: int, penetration: int = 0, multiplier: float = 1.0, damage_type: str = "физического",
        target_id: str | None = None, cover_bonus: int = 0,
        attack_mode: str = 'melee', defense_name: str | None = None,
    ) -> dict[str, Any]:
        target_id = target_id or self.selected_target_id
        statuses = self.conditions.get(target_id, {})
        from talent_runtime import incoming_defense,incoming_conversions,reflection_chance
        defender_rules=self._target_talent_rules(target_id)
        engaged=sum(self.grid.distance(self.target_positions[target_id],position)<=1
                    for key,position in self.target_positions.items()
                    if key!=target_id and self.target_healths.get(key,0)>0
                    and self.targets[key].get('team','enemy')!=self.targets[target_id].get('team','enemy'))
        if self.grid.distance(self.target_positions[target_id],self.player_position)<=1:engaged+=1
        if defense_name:
            defenses={name:self._defense(name,target_id) for name in self.targets[target_id]['defenses']}
            defense=incoming_defense(defender_rules,defenses,defense_name,attack_mode,engaged)
        from talent_runtime import attack_context
        context=attack_context(getattr(self,'talent_runtime',{}),statuses,
            self.grid.distance(self.player_position,self.target_positions[target_id]),
            self.player_health/max(1,self.player_health_max),0)
        accuracy+=round(context['accuracy']);multiplier*=context['multiplier']
        from consumables import virtual_equipment
        from item_effects import armor_by_type
        damage_key={'физического':'Дробящий','дробящего':'Дробящий','колющего':'Колющий','рубящего':'Рубящий','огненного':'Огненный','ледяного':'Ледяной','электрического':'Электрический','магического':'Магический'}.get(damage_type,damage_type.capitalize())
        armor=self.targets[target_id].get('armorByType',{}).get(damage_key,armor)
        armor+=sum(armor_by_type(i).get(damage_key,0) for i in virtual_equipment(statuses,self.round_number))
        defense = max(0, defense - statuses.get('decay', {}).get('stacks', 0) * 2)
        armor = max(0, armor - statuses.get('decay', {}).get('stacks', 0))
        if statuses.get('prone') and defense == self._defense('Парирование',target_id):
            defense = max(0,defense-10)
        accuracy += 10 if self.conditions.get('player', {}).get('guidance') else 0
        self.conditions.get(target_id, {}).pop('sleep', None)
        target_name = self.targets[target_id]["name"]
        roll = random.randint(1, 100)
        score = roll + accuracy - defense - cover_bonus
        if score <= 15:
            result, quality = "Промах", 0
        elif score <= 50:
            result, quality = "Скользящий удар", .5
        elif score <= 100:
            result, quality = "Попадание", 1
        else:
            result, quality = "Критическое попадание", context['criticalMultiplier']
        critical_chance=getattr(self,'runtime_derived',{}).get('attack',{}).get('criticalChance',0)
        if result=='Попадание' and critical_chance and random.randint(1,100)<=critical_chance:
            result,quality='Критическое попадание',context['criticalMultiplier']
        if result=='Скользящий удар' and getattr(self,'talent_runtime',{}).get(102,0):
            if random.random()<self.talent_runtime[102]:result,quality='Попадание',1
        from item_effects import equip_modifiers
        conversions=dict(self.targets[target_id].get('incomingConversions',{}))
        for key,value in incoming_conversions(defender_rules,attack_mode).items():
            conversions[key]=conversions.get(key,0)+value
        for item in virtual_equipment(statuses,self.round_number):
            mods=equip_modifiers(item)['flat']
            for key,label in [('critToHit','Отражение критических ударов'),('hitToGraze','Отражение попаданий'),('grazeToMiss','Отражение промахов')]:
                conversions[key]=conversions.get(key,0)+mods.get(label,0)
        for current,key,new,new_quality in [('Критическое попадание','critToHit','Попадание',1),('Попадание','hitToGraze','Скользящий удар',.5),('Скользящий удар','grazeToMiss','Промах',0)]:
            if result==current and conversions.get(key,0) and random.randint(1,100)<=conversions[key]:result,quality=new,new_quality
        self.attacks += 1
        if not quality:
            line = f"Раунд {self.round_number}: {name} по цели «{target_name}» — промах ({roll} + {accuracy} − {defense + cover_bonus})."
            self.log.append(line)
            return {"result": result, "damage": 0, "roll": roll, "line": line}
        raw = max(1, round(random.randint(max(1, low), max(1, low, high)) * quality * multiplier)) if high>0 else 0
        for state in statuses.values():
            if state.get('kind')=='incoming':raw=round(raw*state['value'])
            if state.get('kind')=='armor':armor=max(0,armor+round(state['value']))
        for state in self.conditions.get('player',{}).values():
            if state.get('kind')=='extraDamage':raw+=round(raw*state['value']/100)
        effective_armor = max(0, armor - penetration)
        damage = max(1,round(raw - effective_armor)) if raw else 0
        from consumables import receive_damage
        damage=receive_damage(statuses,damage)
        chance=reflection_chance(defender_rules,attack_mode,result)
        if chance and random.random()<chance:
            reflected=receive_damage(self.conditions.setdefault('player',{}),damage)
            self.player_health=max(0,self.player_health-reflected)
            line=f"Раунд {self.round_number}: «{target_name}» отражает «{name}»: атакующий получает {reflected} урона."
            self.log.append(line)
            return {'result':'Отражено','damage':0,'roll':roll,'line':line}
        self.target_healths[target_id] = max(0, self.target_healths[target_id] - damage)
        if target_id == "dummy":
            self.dummy_health = self.target_healths[target_id]
        self.damage_total += damage
        self.hits += 1
        line = (
            f"Раунд {self.round_number}: {name} по цели «{target_name}» — {result.lower()}, {damage} {damage_type} урона "
            f"(бросок {roll}, точность {accuracy}, защита {defense + cover_bonus}, броня {effective_armor})."
        )
        if self.finished:
            line += " Манекен разрушен."
        self.log.append(line)
        if self.target_healths[target_id]==0:
            from ability_rules import resolve,profile
            for talent in getattr(self,'runtime_talents',[]):
                source=resolve(talent)
                if not source or source.get('abilityClass')!='TriggeredOnKillAbility':continue
                proc=profile(source,getattr(self,'runtime_derived',{}))
                if proc['supported']:self._apply_ability_effects(proc,'player','self')
        if result=='Критическое попадание' and name=='Обычная атака':
            from consumables import crit_effects,apply
            triggered=crit_effects(self.conditions.get('player',{}))
            if triggered:
                pseudo={'properties':{'gameData':{'prefab':'weapon_poison','useComponents':[{'StatusEffects':triggered}]}}}
                self.target_healths[target_id]=apply(pseudo,self.conditions.setdefault(target_id,{}),self.round_number,self.target_healths[target_id],self.targets[target_id]['healthMax'])
                self.log.append('Критическое попадание активировало нанесённый на оружие состав.')
        if name in {'Обычная атака','Дополнительный удар'}:
            before_proc=self.target_healths[target_id];before_log=len(self.log)
            self._weapon_talent_procs(target_id,result)
            damage+=max(0,before_proc-self.target_healths[target_id])
            if len(self.log)>before_log:line+=' '+' '.join(self.log[before_log:])
        return {"result": result, "damage": damage, "roll": roll, "line": line}

    def _end_turn(self) -> dict[str, Any]:
        self._advance_songs()
        line = f"Раунд {self.round_number}: ход персонажа завершён."
        self.log.append(line)
        player_index = next(i for i, entry in enumerate(self.initiative) if entry['id'] == 'player')
        next_entries = self.initiative[player_index + 1:] + self.initiative[:player_index]
        for entry in next_entries:
            if entry['id'] in self._alive_targets():
                self.log.append(f"{entry['name']}: тренировочная цель пропускает ход.")
        self.round_number += 1
        from consumables import pulse
        self.player_health=pulse(self.conditions.get('player',{}),self.round_number,self.player_health,self.player_health_max)
        for key in self.target_healths:
            before=self.target_healths[key]
            self.target_healths[key]=pulse(self.conditions.get(key,{}),self.round_number,before,self.targets[key]['healthMax'])
            self.damage_total+=max(0,before-self.target_healths[key])
        for target,states in self.conditions.items():
            for key,state in list(states.items()):
                if state.get('kind')=='delayedDamage' and state['triggerRound']<=self.round_number:
                    if target in self.target_healths:
                        amount=min(self.target_healths[target],max(0,round(state['value'])))
                        self.target_healths[target]-=amount;self.damage_total+=amount
                        self.log.append(f"Отложенный урон по «{self.targets[target]['name']}»: {amount}.")
                    states.pop(key)
        for area in list(self.areas):
            self._pulse_area(area)
            area['remaining'] -= 1
        self.areas = [area for area in self.areas if area['remaining'] > 0]
        for target, states in list(self.conditions.items()):
            self.conditions[target] = {key: value for key, value in states.items() if value['until'] >= self.round_number}
        if not self.conditions.get('player',{}).get('restore'):
            self.player_health_max = self.player_base_health_max
            self.player_health = min(self.player_health,self.player_health_max)
        for target,row in self.targets.items():
            if 'baseHealthMax' in row and not self.conditions.get(target,{}).get('restore'):
                row['healthMax']=row['baseHealthMax']
                self.target_healths[target]=min(self.target_healths[target],row['healthMax'])
        self.log.append('Новый раунд: оставшиеся области обновили свои эффекты.')
        self.movement_remaining = self._movement_limit()
        self.action_available = True
        self.disengaged = False
        self.opportunity_used.clear()
        return {"result": "Новый раунд", "damage": 0, "line": line}

    def _pulse_area(self, area):
        if area['aura']:
            area['center'] = self.player_position
        cells = self.grid.radius_cells(tuple(area['center']), area['radius'])
        effect = area['effect']
        friendly = effect in {'heal', 'restore', 'guidance', 'stance', 'magic'}
        targets = ['player'] if friendly and self.player_health>0 and self.player_position in cells and self.grid.line_of_sight(tuple(area['center']),self.player_position) else []
        if friendly:
            targets += [key for key,health in self.target_healths.items() if health>0
                        and self.targets[key].get('team','enemy')!='enemy' and self.target_positions[key] in cells
                        and self.grid.line_of_sight(tuple(area['center']),self.target_positions[key])]
        if not friendly:
            targets = [key for key in self._alive_targets() if self.target_positions[key] in cells
                       and self.grid.line_of_sight(tuple(area['center']), self.target_positions[key])]
        for target in targets:
            if effect == 'heal':
                maximum=self.player_health_max if target=='player' else self.targets[target]['healthMax']
                amount = math.ceil(maximum * .1)
                if target=='player':self.player_health = min(maximum,self.player_health+amount)
                else:self.target_healths[target]=min(maximum,self.target_healths[target]+amount)
            elif effect == 'restore':
                states=self.conditions.setdefault(target,{})
                negative=next((key for key in states if key in {'fatigue','fear','decay','frost','prone','sleep'}),None)
                if negative: states.pop(negative)
                states['restore']={'name':area['description'],'stacks':1,'until':self.round_number}
                if target=='player':self.player_health_max=math.ceil(self.player_base_health_max*1.2)
                else:
                    row=self.targets[target];base=row.setdefault('baseHealthMax',row['healthMax'])
                    row['healthMax']=math.ceil(base*1.2)
            elif effect in {'fire', 'stone'}:
                self._roll_attack(name=area['name'], accuracy=area['accuracy'], low=area['damageMin'],
                                  high=area['damageMax'], defense=self._defense('Магия', target),
                                  armor=self.targets[target]['armor'], target_id=target,
                                  damage_type='огненного' if effect == 'fire' else 'дробящего',
                                  attack_mode='spell',defense_name='Магия')
            else:
                states = self.conditions.setdefault(target, {})
                stacks = min(5, states.get(effect, {}).get('stacks', 0) + 1) if effect in {'decay','frost'} else 1
                states[effect] = {'name': area['description'], 'stacks': stacks, 'until': self.round_number}
                if effect == 'frost' and random.randint(1,100) + area['accuracy'] > self._defense('Выносливость', target) + 50:
                    states['prone'] = {'name': 'Сбит с ног: Парирование −10', 'stacks': 1, 'until': self.round_number}
        self.log.append(f"Раунд {self.round_number}: «{area['name']}» повторяет эффект в области; целей: {len(targets)}.")

    def _spell_cells(self, profile: dict[str, Any]) -> set[tuple[int, int]]:
        target = self.aim_point or self.target_positions.get(self.selected_target_id,self.player_position)
        targeting = profile.get("targeting", "unit")
        if targeting == "area":
            return self.grid.radius_cells(target, int(profile.get("area", 0)))
        if targeting == "line":
            return set(self.grid.line_cells(self.player_position, target, int(profile.get("range", 1))))
        if targeting == "cone":
            return self.grid.cone_cells(
                self.player_position, target, int(profile.get("range", 1)), float(profile.get("angle", 90) or 90)
            )
        if targeting == "aura":
            return self.grid.radius_cells(self.player_position, max(1, int(profile.get("area", 1))))
        if targeting == "self":
            if profile.get('targetTeam')!='ally' and profile.get('area') and (profile.get('damageMax') or profile.get('weaponMultiplier') or profile.get('push')):
                return self.grid.radius_cells(self.player_position,profile['area'])
            return {self.player_position}
        return {target}

    def _spell_targets(self, profile: dict[str, Any]) -> list[str]:
        cells = self._spell_cells(profile)
        return [key for key in self._alive_targets() if self.target_positions[key] in cells]

    def act(
        self, payload: dict[str, Any], character: dict[str, Any], derived: dict[str, Any],
        spells: list[dict[str, Any]], weapon_sets: int,
    ) -> dict[str, Any]:
        previous=copy.deepcopy(self.__dict__)
        self.movement_path = []
        kind = str(payload.get("kind", ""))
        target_id = payload.get("targetId")
        try:
            if kind in {'ability','spell','artifact'} and target_id=='player':
                self.aim_point=self.player_position
            elif kind in {"attack", "ability", "spell", "artifact"} and target_id:
                if target_id not in (self._alive_targets() if kind=='attack' else self.target_healths):
                    raise ValueError("Эта цель недоступна.")
                self.selected_target_id = str(target_id)
            if kind in {"attack","spell", "artifact", "ability", "item","move"} and ('x' in payload or 'y' in payload):
                point = self._cell(payload)
                if not self.grid.inside(point) or point in self.grid.blocked:
                    raise ValueError("Нельзя применить заклинание в этой клетке.")
                self.aim_point = point
                if kind=='attack':
                    aimed=next((k for k in self._alive_targets() if self.target_positions[k]==point),None)
                    if not aimed or target_id and str(target_id)!=aimed:raise ValueError('Выберите вражеский токен для атаки.')
                    self.selected_target_id=aimed
            return self._act(payload, character, derived, spells, weapon_sets)
        except Exception:
            self.__dict__.clear();self.__dict__.update(previous)
            raise
        finally:
            self.aim_point = None

    def _act(
        self, payload: dict[str, Any], character: dict[str, Any], derived: dict[str, Any],
        spells: list[dict[str, Any]], weapon_sets: int,
    ) -> dict[str, Any]:
        self.runtime_talents=character.get('talents',[])
        self.runtime_derived=derived
        derived=self._combat_derived(derived)
        self._initialize({**character,'attributes':derived.get('effectiveAttributes',character.get('attributes',{})),'health_max':derived.get('healthMax',character.get('health_max',character.get('health',20)))})
        if self.finished:
            raise ValueError("Манекен уже разрушен. Начните новую тренировку.")
        kind, name = str(payload.get("kind", "")), str(payload.get("name", ""))
        controls=self.conditions.get('player',{})
        if kind=='spell' and (controls.get('silence') or any(s.get('source',{}).get('AffectsStat')==121 for s in controls.values())):
            raise ValueError('Немота: нельзя применять заклинания.')
        attack = derived["attack"]
        attrs = derived.get("effectiveAttributes", character.get("attributes", {}))
        multiplier = float(derived.get("cooldownMultiplier", 1))
        if kind=='item':
            from consumables import apply,profile
            item=next((i for i in getattr(self,'consumable_inventory',[]) if str(i['inventory_id'])==name),None)
            used=getattr(self,'consumable_used',{})
            if not item or int(item['quantity'])<=used.get(name,0):raise ValueError('Расходник недоступен.')
            info=profile(item)
            if not info:raise ValueError('Этот предмет не является расходником.')
            if self.remaining('item:'+name):raise ValueError('Расходник ещё перезаряжается.')
            recipient=str(payload.get('targetId') or 'player')
            if self.aim_point is not None:
                recipient='player' if self.aim_point==self.player_position else next((k for k,p in self.target_positions.items() if p==self.aim_point),'')
            if recipient!='player':
                if recipient not in self.targets or self.grid.distance(self.player_position,self.target_positions[recipient])>1:
                    raise ValueError('Расходник можно применить на себя или на соседний токен (1 клетка).')
                self._require_action(0)
                if not self.grid.line_of_sight(self.player_position,self.target_positions[recipient]):raise ValueError('Цель за препятствием.')
                health=self.target_healths[recipient]
                self.target_healths[recipient]=apply(item,self.conditions.setdefault(recipient,{}),self.round_number,health,self.targets[recipient]['healthMax'])
                self.action_available=False
            else:
                if info['targeting']=='ally':raise ValueError('Для воскрешения выберите павшего соседнего персонажа.')
                self.player_health=apply(item,self.conditions.setdefault('player',{}),self.round_number,self.player_health,self.player_health_max)
            used[name]=used.get(name,0)+1;self.consumable_used=used
            self.cooldowns['item:'+name]=self.round_number+info['cooldown']+1
            line=f"«{item['name']}»: {info['description']} (тренировка — настоящий предмет не расходуется)."
            self.log.append(line)
            return {'result':'Предмет применён','damage':0,'line':line}
        if kind == "select_target":
            target_id = str(payload.get("targetId", ""))
            if target_id not in self._alive_targets():
                raise ValueError("Эта цель недоступна.")
            self.selected_target_id = target_id
            target = self._target()
            line = f"Выбрана цель «{target['name']}» на расстоянии {self._distance()} м."
            return {"result": "Цель выбрана", "damage": 0, "line": line}
        if kind == "move":
            if any(controls.get(k) for k in ('root','stun','paralyze','petrif','freeze','sleep','prone')):
                raise ValueError('Персонаж обездвижен: перемещение недоступно.')
            target = self._cell(payload)
            occupied = {p for key,p in self.target_positions.items() if self.target_healths[key]>0}
            reachable = self.grid.reachable(self.player_position, self.movement_remaining, occupied)
            if target not in reachable or target == self.player_position:
                raise ValueError("Эта клетка недостижима в текущем ходу.")
            spent = reachable[target]
            old_position = self.player_position
            self.movement_path = self.grid.path(old_position, target, occupied)
            self.player_position = target
            self.movement_remaining -= spent
            line = f"Раунд {self.round_number}: персонаж перемещается на {spent} м."
            controllers = [
                key for key in self._alive_targets()
                if key not in self.opportunity_used
                and float(self.targets[key].get('attack',{}).get('range',1))<=1
                and any(self.grid.distance(a,self.target_positions[key])<=1 and self.grid.distance(b,self.target_positions[key])>1
                        and self.grid.line_of_sight(self.target_positions[key],a)
                        for a,b in zip(self.movement_path,self.movement_path[1:]))
                and not any(self.conditions.get(key,{}).get(state) for state in ('sleep','prone','freeze','stun','paralyze','petrif','disarm','special:freeze','special:frozen','special:stun','special:paralyze','special:petrif','special:disarm'))
            ]
            for controller in controllers:
                if self.player_health<=0 or self.disengaged or any(s.get('source',{}).get('AffectsStat') in {24,151,2145} for s in self.conditions.get('player',{}).values()):continue
                self.opportunity_used.add(controller)
                attacker = self.targets[controller]["name"]
                roll = random.randint(1, 100)
                dodge = int(derived.get("defenses", {}).get("Уклонение", 20))
                states=self.conditions.get(controller,{})
                penalty=(5 if states.get('fatigue') else 0)+(10 if states.get('fear') else 0)
                npc_attack=self.targets[controller].get('attack',{})
                if roll + int(npc_attack.get('accuracy',35)) - penalty > dodge:
                    damage = max(1, round(random.randint(int(npc_attack.get('damageMin',4)),int(npc_attack.get('damageMax',8))) - float(derived.get("armor", 0))))
                    from consumables import receive_damage
                    shield_states={key:state for key,state in self.conditions.get('player',{}).items() if state.get('source',{}).get('AffectsStat')!=188}
                    damage=receive_damage(shield_states,round(damage*derived.get('incomingDamageMultiplier',1)))
                    for state in self.conditions.get('player',{}).values():
                        if state.get('kind')=='incoming':damage=round(damage*state['value'])
                        if state.get('kind')=='shield':
                            absorbed=min(damage,max(0,round(state['value'])));damage-=absorbed;state['value']-=absorbed
                    self.player_health = max(0, self.player_health - damage)
                    retaliation=self.conditions.get('player',{}).get('special:retaliateParalyze')
                    if retaliation:self._apply_special({**retaliation,'kind':'paralyze','name':'Паралич','side':'enemy'},controller)
                    line += f" {attacker} проводит атаку по возможности и наносит {damage} урона."
                else:
                    line += f" {attacker} проводит атаку по возможности, но промахивается."
            self.log.append(line)
            return {"result": "Перемещение", "damage": 0, "line": line}
        if kind == "disengage":
            self._require_action(0)
            self.action_available = False
            self.disengaged = True
            line = f"Раунд {self.round_number}: персонаж осторожно выходит из боя; атаки по возможности отключены до конца хода."
            self.log.append(line)
            return {"result": "Отход", "damage": 0, "line": line}
        if kind in {"wait", "end_turn"}:
            return self._end_turn()
        if kind == "weapon_set":
            number = int(payload.get("number", 0))
            if not 1 <= number <= weapon_sets:
                raise ValueError("Этот комплект оружия недоступен.")
            self.active_weapon_set = number
            line = f"Раунд {self.round_number}: выбран комплект оружия {number}; основное действие не потрачено."
            self.log.append(line)
            return {"result": "Комплект сменён", "damage": 0, "line": line}
        if kind == "stance":
            from ability_rules import resolve,stance_equipment
            stance=next((r for talent in character.get('talents',[]) for r in [resolve(talent)]
                         if r and r.get('modal') and not r.get('song') and name in {r['name'],r['key'],talent.get('name')}),None)
            if not stance:
                raise ValueError("Эта стойка не изучена персонажем.")
            if not stance_equipment(stance['key']):
                raise ValueError('Эффекты этой стойки ещё не подключены; переключение отменено.')
            self.active_stance = stance['name']
            line = f"Раунд {self.round_number}: персонаж принимает стойку «{name.removeprefix('Стойка:').strip()}»."
            self.log.append(line)
            return {"result": "Стойка изменена", "damage": 0, "line": line}

        result: dict[str, Any]
        if kind == "attack":
            from talent_runtime import weapon_mode
            mode=weapon_mode(attack)
            action_range = self._weapon_range(attack)
            self._require_action(action_range)
            defense_name = "Парирование" if mode=='melee' else "Уклонение"
            cover_name, cover_bonus = self.grid.cover(self.player_position, self.target_positions[self.selected_target_id])
            cover_bonus = cover_bonus if action_range > 1 else 0
            result = self._roll_attack(
                name="Обычная атака", accuracy=int(attack.get("accuracy", 0)),
                low=int(attack.get("damageMin", 1)), high=int(attack.get("damageMax", 2)),
                defense=self._defense(defense_name), armor=self.targets[self.selected_target_id]["armor"], cover_bonus=cover_bonus,
                penetration=round(attack.get('penetration',0)),
                attack_mode=mode,defense_name=defense_name,
            )
            chances=dict(attack.get('splitChances',{}))
            fixed_count=max(1,int(getattr(self,'talent_runtime',{}).get(2157,1)))
            for state in self.conditions.get('player',{}).values():
                if state.get('source',{}).get('AffectsStat')==2157:fixed_count=max(fixed_count,int(state['source']['Value']))
                if state.get('source',{}).get('AffectsStat')==2168:
                    effect=state['source'];count=int(effect['Value'])
                    chances[count]=max(chances.get(count,0),float(effect.get('ExtraValue',0)))
            if fixed_count>1:chances={fixed_count:100}
            if chances:
                roll=random.randint(1,100);cutoff=0;count=1
                for hits,chance in sorted(chances.items(),key=lambda pair:int(pair[0]),reverse=True):
                    cutoff+=float(chance)
                    if roll<=cutoff:count=int(hits);break
                for _ in range(count-1):
                    if self.target_healths[self.selected_target_id]<=0 or self.player_health<=0:break
                    extra=self._roll_attack(name='Дополнительный удар',accuracy=int(attack.get('accuracy',0)),
                        low=int(attack.get('damageMin',1)),high=int(attack.get('damageMax',2)),
                        defense=self._defense(defense_name),armor=self.targets[self.selected_target_id]['armor'],
                        cover_bonus=cover_bonus,penetration=round(attack.get('penetration',0)),
                        attack_mode=mode,defense_name=defense_name)
                    result['damage']+=extra['damage'];result['line']+=' '+extra['line']
        elif kind == "ability":
            from ability_rules import owned_actions
            rule=next((a for a in owned_actions(character.get('talents',[]),derived,self._weapon_range(attack)) if name in {a['name'],a['key']}),None)
            if not rule:
                raise ValueError("Эта способность не изучена персонажем.")
            result=self._execute_ability(rule,derived,getattr(self,'consumable_inventory',[]))
            if result.get('consumesAction') is False:return result
        elif kind == "artifact":
            ability=next((a for a in derived.get('artifactAbilities',[]) if a['name']==name),None)
            if not ability:raise ValueError('Артефакт не экипирован в активном комплекте.')
            if not ability['supported']:raise ValueError(ability['limitation'])
            key='artifact:'+name
            if self.remaining(key):raise ValueError('Способность артефакта уже использована или перезаряжается.')
            targeting=ability.get('targeting','unit')
            point=self.aim_point or self.target_positions.get(self.selected_target_id,self.player_position)
            if targeting=='self':self.aim_point=self.player_position
            self._require_action(ability['range'])
            cells=self._spell_cells(ability)
            targets=[k for k in self._alive_targets() if self.target_positions[k] in cells and self.grid.line_of_sight(self.player_position,self.target_positions[k])]
            if targeting=='ally':
                ally=next((k for k,p in self.target_positions.items() if p==point and self.targets[k].get('team')=='ally' and self.target_healths[k]>0),None)
                if not ally:raise ValueError('Выберите союзный токен для обмена позициями.')
                self.player_position,self.target_positions[ally]=self.target_positions[ally],self.player_position
                targets=[]
            elif targeting!='self' and not targets:raise ValueError('Выберите доступную цель.')
            weapon=ability.get('weaponMultiplier',0)
            low=ability['damageMin'] or round(attack.get('damageMin',2)*weapon)
            high=ability['damageMax'] or round(attack.get('damageMax',4)*weapon)
            results=[]
            for target in targets:
                hit=self._roll_attack(name=name,accuracy=attack.get('accuracy',20),low=low,high=high,
                    defense=self._defense('Магия',target),armor=self.targets[target]['armor'],
                    penetration=ability['penetration'],target_id=target)
                results.append(hit)
                if hit['result']!='Промах':
                    for effect in ability.get('effects',[]):
                        if effect['side']=='enemy':self._apply_special(effect,target)
                    if ability.get('push'):
                        occupied={p for k,p in self.target_positions.items() if k!=target and self.target_healths[k]>0}|{self.player_position}
                        destination=self.grid.displace(self.player_position,self.target_positions[target],ability['push'],occupied)
                        self.target_positions[target]=destination
            for effect in ability.get('effects',[]):
                if effect['side']=='self':self._apply_special(effect,'player')
            self.movement_remaining=min(self._movement_limit(),self.movement_remaining+max(0,self._movement_limit()-BASE_MOVEMENT))
            self.cooldowns[key]=999999 if ability['oncePerBattle'] else self.round_number+ability['cooldown']+1
            result={'result':'Артефакт применён','damage':sum(r['damage'] for r in results),'line':' '.join(r['line'] for r in results) or name}
        elif kind == "spell":
            spell = next((row for row in spells if row["name"] == name), None)
            if not spell:
                raise ValueError("Заклинание не найдено в гримуаре.")
            key = f"spell:{name}"
            if self.remaining(key):
                raise ValueError(f"Заклинание будет готово через {self.remaining(key)} {_round_word(self.remaining(key))}.")
            skill = CORE_SKILLS.get(spell.get("core"), "Знания")
            profile = spell_runtime_profile(
                spell, skill=int(derived.get('effectiveSkills',{}).get(skill,character.get("skills", {}).get(skill, {}).get("value", 0))),
                wits=int(attrs.get("Смекалка", 10)), cooldown_multiplier=multiplier,
            )
            for field in ['damage_min','damage_max']:profile[field]=round(profile[field]*derived.get('spellPowerMultiplier',1))
            if profile["targeting"] == "unit" and self.aim_point is not None:
                target_id = next((key for key in self._alive_targets() if self.target_positions[key] == self.aim_point), None)
                if not target_id:
                    raise ValueError("Выберите вражеский токен для этого заклинания.")
                self.selected_target_id = target_id
            if profile["targeting"] in {"self", "aura"}:
                self.aim_point = self.player_position
            self._require_action(profile["range"])
            persistent = persistent_profile(spell)
            if persistent:
                center = self.player_position if persistent['aura'] else self.aim_point or self.target_positions.get(self.selected_target_id,self.player_position)
                area = {**persistent, 'id': f'{self.round_number}:{len(self.areas)}:{name}', 'name': name,
                        'core': spell['core'], 'center': center, 'radius': max(1, profile['area']),
                        'remaining': persistent['rounds'] - 1, 'accuracy': profile['accuracy'],
                        'damageMin': profile['damage_min'], 'damageMax': profile['damage_max']}
                self._pulse_area(area)
                if area['remaining']:
                    self.areas.append(area)
                self.cooldowns[key] = self.round_number + profile['cooldown'] + 1
                self.action_available = False
                return {'result': 'Область создана', 'damage': 0, 'line': f"«{name}»: {persistent['rounds']} раунда, первый эффект применён."}
            if profile["targeting"] == "self":
                self.cooldowns[key] = self.round_number + profile["cooldown"] + 1
                line = f"Раунд {self.round_number}: персонаж применяет на себя «{name}»."
                self.log.append(line)
                self.action_available = False
                return {"result": "Заклинание применено", "damage": 0, "line": line}
            affected = [target_id for target_id in self._spell_targets(profile)
                        if self.grid.cover(self.player_position, self.target_positions[target_id])[0] != "полное"]
            if not affected:
                raise ValueError("В области заклинания нет доступных целей.")
            self.cooldowns[key] = self.round_number + profile["cooldown"] + 1
            results = []
            for target_id in affected:
                cover_name, cover_bonus = self.grid.cover(self.player_position, self.target_positions[target_id])
                if cover_name == "полное":
                    continue
                results.append(self._roll_attack(
                    name=name, accuracy=profile["accuracy"], low=profile["damage_min"], high=profile["damage_max"],
                    defense=self._defense(profile["defense"],target_id), armor=self.targets[target_id]["armor"],
                    penetration=profile["penetration"], damage_type=CORE_DAMAGE.get(spell.get("core"), "магического"),
                    target_id=target_id, cover_bonus=cover_bonus if profile["targeting"] in {"unit", "line"} else 0,
                    attack_mode='spell',defense_name=profile['defense'],
                ))
            if not results:
                raise ValueError("В области заклинания нет доступных целей.")
            result = {"result": results[0]["result"], "damage": sum(row["damage"] for row in results),
                      "line": " ".join(row["line"] for row in results)}
            if profile.get("enhancement") == "Столкновение":
                for target_id in affected:
                    old = self.target_positions[target_id]
                    self.target_positions[target_id] = self.grid.displace(self.player_position, old, 4, self._occupied(target_id))
        else:
            raise ValueError("Неизвестное тренировочное действие.")
        if self.target_healths.get(self.selected_target_id, 0) <= 0 and self._alive_targets():
            self.selected_target_id = self._alive_targets()[0]
        self.action_available = False
        return result

    def view(
        self, character: dict[str, Any], derived: dict[str, Any], spells: list[dict[str, Any]],
        weapon_sets: int,
    ) -> dict[str, Any]:
        derived=self._combat_derived(derived)
        self._initialize({**character,'attributes':derived.get('effectiveAttributes',character.get('attributes',{})),'health_max':derived.get('healthMax',character.get('health_max',character.get('health',20)))})
        attack = derived.get("attack", {})
        attrs = derived.get("effectiveAttributes", character.get("attributes", {}))
        owned = {talent["name"] for talent in character.get("talents", [])}
        stances = [
            {"name": talent["name"], "description": talent.get("description", ""),
             "icon": (ABILITY_DETAILS.get(talent["name"]) or {}).get("icon", "")}
            for talent in character.get("talents", [])
            if (lambda r:bool(r and r.get('modal') and not r.get('song')))(__import__('ability_rules').resolve(talent))
        ]
        distance, weapon_range = self._distance(), self._weapon_range(attack)
        selected_target = self._target()
        cover_name, cover_bonus = self.grid.cover(self.player_position, self.target_positions.get(self.selected_target_id,self.player_position))

        def reason(action_range: int) -> str:
            if not self.action_available:
                return "Основное действие потрачено"
            if action_range == 0:
                return ""
            if action_range > 1 and cover_name == "полное":
                return "Цель полностью закрыта от прямой видимости"
            return f"Цель вне дальности: {distance}/{action_range} м" if distance > action_range else ""

        actions = [{"kind": "attack", "name": "Обычная атака", "description": "Атака активным оружейным комплектом.",
                    "remaining": 0, "range": weapon_range, "weaponSkill": attack.get("skill", ""), "disabledReason": reason(weapon_range),
                    "cells": [{"x": selected_target["x"], "y": selected_target["y"]}]}]
        from consumables import profile
        for item in getattr(self,'consumable_inventory',[]):
            info=profile(item)
            if not info:continue
            used=getattr(self,'consumable_used',{}).get(str(item['inventory_id']),0)
            if info and int(item['quantity'])>used:
                actions.append({'kind':'item','name':str(item['inventory_id']),'displayName':item['name'],
                    'description':info['description']+f" · На себя: без действия. На соседнюю цель (1 клетка): основное действие. Осталось в тренировке: {int(item['quantity'])-used}",
                    'icon':item['image_url'],'targeting':'unit','range':1,'freeOnSelf':True,'includeSelf':info['targeting']=='self','requiresFallen':info['targeting']=='ally',
                    'remaining':self.remaining('item:'+str(item['inventory_id'])), 'disabledReason':'','limitation':'','cells':[]})
        for ability in derived.get('artifactAbilities',[]):
            actions.append({**ability,'kind':'artifact',
                'remaining':self.remaining('artifact:'+ability['name']),
                'disabledReason':ability['limitation'] or reason(ability['range']),
                'description':ability['description']+'\n'+ability['limitation']+'\n'+'; '.join(ability['passives'])})
        from ability_rules import owned_actions,weapon_requirement
        from song_rules import breath_limit
        song_capacity=2 if 2101 in getattr(self,'talent_runtime',{}) else 1
        for rule in owned_actions(character.get('talents',[]),derived,weapon_range):
            song_active=any(s['key']==rule['key'] for s in self.active_songs)
            resource_reason=('Недостаточно дыхания' if rule.get('breathCost',0)>self.breath else '')
            if rule.get('song') and not song_active and len(self.active_songs)>=song_capacity:
                resource_reason='Сначала остановите активную песню'
            actions.append({**{k:v for k,v in rule.items() if k not in {'nodes','source'}},'kind':'ability',
                'description':rule['description']+'\n'+rule['details'],'remaining':self.remaining('ability:'+rule['key']),
                'disabledReason':rule['limitation'] or resource_reason or weapon_requirement(rule,getattr(self,'consumable_inventory',[]),self.active_weapon_set) or ('' if rule.get('song') or self.action_available else 'Основное действие потрачено'),
                'cells':[]})
        for spell in spells:
            skill = CORE_SKILLS.get(spell.get("core"), "Знания")
            profile = spell_runtime_profile(
                spell, skill=int(derived.get('effectiveSkills',{}).get(skill,character.get("skills", {}).get(skill, {}).get("value", 0))),
                wits=int(attrs.get("Смекалка", 10)), cooldown_multiplier=float(derived.get("cooldownMultiplier", 1)),
            )
            for field in ['damage_min','damage_max']:profile[field]=round(profile[field]*derived.get('spellPowerMultiplier',1))
            actions.append({"kind": "spell", "name": spell["name"],
                            "core": spell["core"], "angle": profile.get("angle", 90),
                            "cooldown": profile["cooldown"], "damageMin": profile["damage_min"],
                            "damageMax": profile["damage_max"], "defense": profile["defense"],
                            "description": f"{spell['core']} + {spell['expression']}" +
                                (f" · {persistent_profile(spell)['description']} · {persistent_profile(spell)['rounds']} раунда" if persistent_profile(spell) else ''),
                            "persistent": persistent_profile(spell),
                            "remaining": self.remaining(f"spell:{spell['name']}"), "range": profile["range"],
                            "area": profile["area"], "targeting": profile["targeting"],
                            "disabledReason": "Основное действие потрачено" if not self.action_available else "",
                            "cells": [{"x": x, "y": y} for x, y in self._spell_cells(profile)]})

        controlled = self.grid.control_zone(self.target_positions[key] for key in self._alive_targets())
        if self.player_position in controlled:
            actions.insert(0, {"kind": "disengage", "name": "Осторожный отход",
                               "description": "Отключает атаки по возможности до конца текущего хода.",
                               "remaining": 0, "range": 0,
                               "disabledReason": "Основное действие потрачено" if not self.action_available else "",
                                "cells": []})

        # The client previews these server-computed shapes without spending an action.
        for action in actions:
            action["aims"] = {}
            for y in range(self.grid.height):
                for x in range(self.grid.width):
                    point = (x, y)
                    self.aim_point = point
                    targeting = action.get("targeting", "unit")
                    shape = self._spell_cells(action) if action["kind"] in {"spell","artifact","ability"} else {point}
                    effective_point = self.player_position if targeting in {"self", "aura"} else point
                    valid = self.grid.distance(self.player_position, effective_point) <= action.get("range", 0)
                    valid = valid and point not in self.grid.blocked and self.grid.line_of_sight(self.player_position, effective_point)
                    if action['kind']=='artifact' and not action['supported']: valid=False
                    if action['kind']=='ability' and not action['supported']:valid=False
                    if targeting == "ally":
                        valid = valid and any(p == point and self.targets[k].get("team")=="ally" for k,p in self.target_positions.items())
                    if targeting == "unit":
                        if action['kind']=='ability':
                            valid = valid and bool(self._ability_targets(action))
                        else:valid = valid and any(self.target_positions[key] == point for key in self._alive_targets())
                    if action['kind']=='ability' and targeting not in {'self','unit'}:
                        valid = valid and bool(self._ability_targets(action))
                    if action['kind']=='item':
                        recipient='player' if point==self.player_position else next((k for k,p in self.target_positions.items() if p==point),'')
                        valid=bool(recipient) and self.grid.distance(self.player_position,point)<=1 and self.grid.line_of_sight(self.player_position,point)
                        if recipient=='player':valid=valid and action['includeSelf']
                        else:valid=valid and self.action_available and (self.target_healths.get(recipient,0)<=0 if action['requiresFallen'] else self.target_healths.get(recipient,0)>0)
                    if targeting in {"self", "aura"}:
                        valid = valid and point == self.player_position
                    if action["kind"] == "spell" and targeting != "self" and not action.get('persistent'):
                        valid = valid and any(self.target_positions[key] in shape and
                            self.grid.cover(self.player_position, self.target_positions[key])[0] != "полное"
                            for key in self._alive_targets())
                    affected=self._ability_targets(action) if action['kind']=='ability' else [k for k in self._alive_targets() if self.target_positions[k] in shape]
                    if action['kind']=='spell':
                        persistent=action.get('persistent')
                        if persistent and persistent['effect'] in {'heal','restore','guidance','stance','magic'}:
                            affected=[k for k,h in self.target_healths.items() if h>0 and self.targets[k].get('team','enemy')!='enemy'
                                      and self.target_positions[k] in shape and self.grid.line_of_sight(effective_point,self.target_positions[k])]
                            if self.player_health>0 and self.player_position in shape and self.grid.line_of_sight(effective_point,self.player_position):affected.insert(0,'player')
                        elif persistent:
                            affected=[k for k in affected if self.grid.line_of_sight(effective_point,self.target_positions[k])]
                        else:affected=[k for k in affected if self.grid.cover(self.player_position,self.target_positions[k])[0]!='полное']
                    if action['kind']=='item':affected=[recipient] if recipient else []
                    if targeting=='self' and not (action['kind']=='ability' and affected):affected=['player']
                    action["aims"][f"{x}:{y}"] = {"valid": valid, "targetIds":affected,"cells": [{"x": cx, "y": cy} for cx, cy in sorted(shape)]}
            self.aim_point = None

        map_spec = self.custom_map or TACTICAL_MAPS[self.map_key]
        occupied = {p for key,p in self.target_positions.items() if self.target_healths[key]>0}
        reachable = self.grid.reachable(self.player_position, self.movement_remaining, occupied)
        grid_payload = self.grid.payload()
        grid_payload.update({
            "name": map_spec["name"], "image": map_spec["image"], "source": map_spec.get("source", "Карта мастера"),
            "layout": {key:map_spec.get(key,default) for key,default in [('cellSize',48),('offsetX',0),('offsetY',0),('imageScale',1),('gridOpacity',.3)]},
            "movementPerTurn": BASE_MOVEMENT,
            "reachable": [{"x": x, "y": y, "cost": cost} for (x, y), cost in reachable.items() if cost],
            "controlZones": [{"x": x, "y": y} for x, y in controlled],
            "selectedTargetId": self.selected_target_id,
            "tokens": [
                {"id": "player", "name": character["name"], "team": "player", "x": self.player_position[0],
                 "y": self.player_position[1], "portraitUrl": character.get("portrait_url", ""), "active": True,
                 "health": self.player_health, "healthMax": self.player_health_max},
                *[{"id": key, "name": self.targets[key]["name"], "team": self.targets[key].get("team","enemy"), "portraitUrl": self.targets[key].get("portrait",""),
                   "x": self.target_positions[key][0], "y": self.target_positions[key][1],
                   "active": key == self.selected_target_id, "selected": key == self.selected_target_id,
                   "health": self.target_healths[key], "healthMax": self.targets[key]["healthMax"]}
                  for key in self.target_healths if self.target_healths[key]>0],
            ],
        })
        return {
            "active": True, "finished": self.finished, "round": self.round_number,
            "dummy": selected_target,
            "targets": [self._target(key) for key in self._alive_targets()],
            "character": {"name": character["name"], "portraitUrl": character.get("portrait_url", ""),
                          "health": self.player_health, "healthMax": self.player_health_max,
                          "activeWeaponSet": self.active_weapon_set, "weaponSets": weapon_sets},
            "turn": {"actorId": "player", "movementRemaining": self.movement_remaining,
                     "movementMax": self._movement_limit(), "actionAvailable": self.action_available,
                     "distanceToTarget": distance, "inControlZone": self.player_position in controlled,
                     "cover": cover_name, "coverBonus": cover_bonus, "disengaged": self.disengaged},
            "initiative": self.initiative, "grid": grid_payload,
            "songs": {"available":any(a.get('song') or a.get('breathCost') for a in actions),
                      "breath":self.breath,"limit":breath_limit(character.get('talents',[])),"capacity":song_capacity,
                      "active":[{"key":s['key'],"name":__import__('ability_rules').resolve(s['key'])['name'],
                                 "phraseName":__import__('ability_rules').resolve(s['key'])['phrases'][s['phrase']]['name'],
                                 "remainingSeconds":round(s['remainingSeconds'],4)} for s in self.active_songs]},
            "derived": derived, "actions": actions, "stances": stances, "activeStance": self.active_stance,
            "cooldowns": self.cooldowns,
            "areas": [{**area, 'center':{'x':area['center'][0],'y':area['center'][1]},
                       'cells':[{'x':x,'y':y} for x,y in self.grid.radius_cells(tuple(area['center']),area['radius'])]}
                      for area in self.areas],
            "conditions": self.conditions,
            "movementPath": [{'x':x,'y':y} for x,y in self.movement_path],
            "log": self.log[-40:][::-1],
            "summary": {"damage": self.damage_total, "attacks": self.attacks, "hits": self.hits,
                        "accuracy": round(self.hits / self.attacks * 100) if self.attacks else 0},
            "rewards": {"experience": 0, "skillExperience": 0, "loot": []},
        }
