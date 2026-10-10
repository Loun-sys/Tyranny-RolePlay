"""Persistent, owner-scoped shared battles using the existing combat executor."""
import asyncio
import copy
import json
import random
import time

from training_combat import TrainingSession
from tactical_grid import TacticalGrid, initiative_bonus

SCHEMA = '''CREATE TABLE IF NOT EXISTS live_battles (
id INTEGER PRIMARY KEY AUTOINCREMENT,guild_id INTEGER NOT NULL,owner_id INTEGER NOT NULL,
name TEXT NOT NULL,status TEXT NOT NULL DEFAULT 'lobby',revision INTEGER NOT NULL DEFAULT 1,
spec TEXT NOT NULL,created_at TEXT DEFAULT CURRENT_TIMESTAMP,updated_at TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE INDEX IF NOT EXISTS live_battles_scope ON live_battles(guild_id,owner_id,status);'''
PERSONAL = ('cooldowns','active_weapon_set','movement_remaining','action_available','disengaged',
            'active_stance','active_songs','breath','opportunity_used','areas','stealthed','suspicion',
            'stealth_elapsed','dash_used','damage_total','attacks','hits','selected_target_id')
PERSONAL+=('pending_graphs','recovery_seconds')


class BattleEngine(TrainingSession):
    @property
    def finished(self):
        # Only the master finishes a shared scene, including scenes without enemies.
        return False

    def _movement_limit(self):
        return round(super()._movement_limit()*getattr(self,'token_movement',5)/5)


class BattleStore:
    def __init__(self, db):
        self.db=db
        if not hasattr(db,'battle_locks'):db.battle_locks={}

    def lock(self, ident):
        return self.db.battle_locks.setdefault(ident,asyncio.Lock())

    async def list(self,guild,owner=None,cid=None):
        async with self.db.connect() as c:
            rows=await c.execute_fetchall('SELECT * FROM live_battles WHERE guild_id=?'+(' AND owner_id=?' if owner is not None else '')+' ORDER BY id DESC LIMIT 100',
                (guild,owner) if owner is not None else (guild,))
        result=[]
        for row in rows:
            state=json.loads(row['spec'])
            if cid is not None and str(cid) not in state['participants']:continue
            result.append({'id':row['id'],'name':row['name'],'status':row['status'],'revision':row['revision'],
                           'round':state['round'],'participants':state['participants']})
        return result

    async def get(self,ident,guild,owner=None,cid=None):
        async with self.db.connect() as c:
            rows=await c.execute_fetchall('SELECT * FROM live_battles WHERE id=? AND guild_id=?',(ident,guild))
        if not rows or owner is not None and rows[0]['owner_id']!=owner:raise ValueError('Бой не принадлежит этому мастеру.')
        row=dict(rows[0]);row['state']=json.loads(row.pop('spec'))
        if cid is not None and str(cid) not in row['state']['participants']:raise ValueError('Персонаж не приглашён в этот бой.')
        return row

    async def delete(self,ident,guild,owner,confirmation,revision):
        """Delete only the selected scene, never its map, PCs or NPC archive."""
        async with self.lock(ident):
            row=await self.get(ident,guild,owner)
            if confirmation!=row['name']:raise ValueError('Введите точное название боя для удаления.')
            if revision is None or int(revision)!=row['revision']:raise ValueError('Бой изменился. Обновите экран и подтвердите удаление заново.')
            async with self.db.connect() as c:
                cur=await c.execute('DELETE FROM live_battles WHERE id=? AND guild_id=? AND owner_id=? AND revision=?',(ident,guild,owner,row['revision']))
                if cur.rowcount!=1:raise ValueError('Бой изменился. Обновите экран и подтвердите удаление заново.')
                await c.commit()

    async def create(self,guild,owner,map_id,participants):
        from campaign_store import CampaignStore
        from npc_store import NPCStore
        ids=list(dict.fromkeys(int(i) for i in participants))
        if not 1<=len(ids)<=25:raise ValueError('Выберите от 1 до 25 персонажей.')
        maps=await CampaignStore(self.db).maps(guild,owner)
        selected=next((m for m in maps if m['id']==int(map_id)),None)
        if not selected:raise ValueError('Выберите сохранённую карту этого мастера.')
        spec=copy.deepcopy(selected['spec']);tokens={};members={};taken=set()
        for cid in ids:
            actor=await self.db.get_character_by_id(cid)
            if not actor or actor['guild_id']!=guild:raise ValueError('Участник не принадлежит этому серверу.')
            point=next((p for p in spec['tokens'] if p['kind']=='player' and p['id']==cid),None)
            members[str(cid)]={'name':actor['name'],'joined':False}
            if point:
                maximum=await self._player_max_health(actor)
                key=f'pc_{cid}';tokens[key]={'kind':'player','characterId':cid,'team':'party','name':actor['name'],
                    'x':point['x'],'y':point['y'],'health':min(actor['health'],maximum),'healthMax':maximum,'baseHealthMax':maximum,'equipmentHealthMax':maximum}
                taken.add((point['x'],point['y']))
        for i,npc in enumerate(await NPCStore(self.db).resolve_map(guild,owner,[p for p in spec['tokens'] if p['kind']=='npc'])):
            tokens[f'npc_{i+1}']={**npc,'kind':'npc','team':'enemy' if npc.get('team','enemy')=='enemy' else 'party',
                'health':npc['healthMax'],'baseHealthMax':npc['healthMax']}
        state={'mapId':selected['id'],'map':spec,'participants':members,'tokens':tokens,'personal':{},
               'conditions':{},'initiative':[],'currentId':'','acted':[],'round':1,'log':['Мастер собирает участников.'],'events':[]}
        async with self.db.connect() as c:
            await c.execute('CREATE TABLE IF NOT EXISTS retained_breath(character_id INTEGER PRIMARY KEY REFERENCES characters(id) ON DELETE CASCADE,amount INTEGER NOT NULL,expires REAL NOT NULL)')
            for cid in ids:
                saved=await c.execute_fetchall('SELECT amount FROM retained_breath WHERE character_id=? AND expires>?',(cid,time.time()))
                if saved:state['personal'][f'pc_{cid}']={'breath':saved[0]['amount']}
            await c.commit()
        async with self.db.connect() as c:
            cur=await c.execute('INSERT INTO live_battles(guild_id,owner_id,name,spec) VALUES(?,?,?,?)',
                (guild,owner,selected['name'],json.dumps(state,ensure_ascii=False)))
            await c.commit()
        return await self.get(cur.lastrowid,guild,owner)

    async def _player_max_health(self,actor):
        from registration_api import _derived,_clean_inventory
        return _derived(actor,_clean_inventory(await self.db.inventory(actor['id'])))['healthMax']

    async def _save(self,row,inventory_deltas=None):
        state=row['state']
        async with self.db.connect() as c:
            await c.execute('BEGIN IMMEDIATE')
            cur=await c.execute('UPDATE live_battles SET spec=?,status=?,revision=revision+1,updated_at=CURRENT_TIMESTAMP WHERE id=? AND revision=?',
                (json.dumps(state,ensure_ascii=False),row['status'],row['id'],row['revision']))
            if cur.rowcount!=1:raise ValueError('Бой изменился. Обновите экран и повторите действие.')
            for inv_id,count,cid in inventory_deltas or []:
                items=await c.execute_fetchall('SELECT quantity FROM inventory WHERE id=? AND character_id=?',(inv_id,cid))
                if not items or items[0]['quantity']<count:raise ValueError('Расходник уже использован или передан.')
                if items[0]['quantity']==count:await c.execute('DELETE FROM inventory WHERE id=?',(inv_id,))
                else:await c.execute('UPDATE inventory SET quantity=quantity-? WHERE id=?',(count,inv_id))
            if row['status']!='lobby':
                for token in state['tokens'].values():
                    if token['kind']=='player':
                        await c.execute('UPDATE characters SET health=MIN(health_max,?),updated_at=CURRENT_TIMESTAMP WHERE id=? AND guild_id=?',
                            (token['health'],token['characterId'],row['guild_id']))
            if row['status']=='ended' and not state.get('breathSaved'):
                from talent_batch_three import roots
                await c.execute('CREATE TABLE IF NOT EXISTS retained_breath(character_id INTEGER PRIMARY KEY REFERENCES characters(id) ON DELETE CASCADE,amount INTEGER NOT NULL,expires REAL NOT NULL)')
                combatants={i['id'] for i in state['initiative']}
                for key,t in state['tokens'].items():
                    if t['kind']!='player' or key not in combatants:continue
                    actor=await self.db.get_character_by_id(t['characterId'])
                    effect=next((e for _,e in roots(actor.get('talents',[])) if e['AffectsStat']==2100),{})
                    amount=min(state['personal'].get(key,{}).get('breath',0),int(effect.get('Value',0)))
                    await c.execute('INSERT OR REPLACE INTO retained_breath VALUES(?,?,?)',(t['characterId'],amount,time.time()+effect.get('ExtraValue',0)))
                state['breathSaved']=True
                await c.execute('UPDATE live_battles SET spec=? WHERE id=?',(json.dumps(state,ensure_ascii=False),row['id']))
            await c.commit()
        row['revision']+=1

    async def join(self,ident,guild,cid):
        async with self.lock(ident):
            row=await self.get(ident,guild,cid=cid)
            if row['status']=='ended':raise ValueError('Бой уже завершён.')
            state=row['state'];member=state['participants'][str(cid)]
            if member['joined']:return row
            others=await self.list(guild,cid=cid)
            if any(b['id']!=ident and b['status']!='ended' and b['participants'][str(cid)]['joined'] for b in others):
                raise ValueError('Персонаж уже участвует в другом бою. Мастер должен завершить его.')
            member['joined']=True
            state['log'].append(f"{member['name']} присоединяется к бою.")
            # Mid-scene joining is supported only after the master placed the token.
            if row['status']=='active' and f'pc_{cid}' not in state['tokens']:
                raise ValueError('Мастер ещё не назначил стартовую клетку персонажа.')
            if row['status']=='active' and not any(i['id']==f'pc_{cid}' for i in state['initiative']):
                state['initiative'].append({'id':f'pc_{cid}','name':member['name'],'roll':0,'bonus':0,'total':0})
            await self._save(row);return row

    async def _profiles(self,row):
        from registration_api import _derived,_clean_inventory
        from consumables import virtual_equipment
        from ability_rules import stance_equipment
        result={}
        for key,t in row['state']['tokens'].items():
            personal=row['state']['personal'].get(key,{})
            if t['kind']=='player':
                actor=await self.db.get_character_by_id(t['characterId'])
                if not actor or actor['guild_id']!=row['guild_id']:raise ValueError('Персонаж участника удалён. Уберите его токен из боя.')
                actor['active_weapon_set']=personal.get('active_weapon_set',actor.get('active_weapon_set',1))
                inventory=_clean_inventory(await self.db.inventory(actor['id']))
                virtual=virtual_equipment(row['state']['conditions'].get(key,{}),row['state']['round'])+stance_equipment(personal.get('active_stance',''))
                derived=_derived(actor,inventory+virtual)
                baseline=_derived(actor,inventory+stance_equipment(personal.get('active_stance','')))
                attributes=virtual_equipment({k:v for k,v in row['state']['conditions'].get(key,{}).items()
                    if v.get('source',{}).get('AffectsStat') in {56,57,58,59,99,100}},row['state']['round'])
                derived['_baseDerived']=_derived(actor,inventory+stance_equipment(personal.get('active_stance',''))+attributes)
                derived['healthMax']=max(1,t.get('baseHealthMax',t['healthMax'])+derived['healthMax']-t.get('equipmentHealthMax',baseline['healthMax']))
                spells=[s for s in await self.db.spells(actor['id']) if s.get('equipped_slot') is not None]
                limits=await self.db.equipment_limits(actor['id'])
            else:
                from talent_runtime import effects
                from talent_reactions import actor_inventory,npc_derived
                inventory=actor_inventory(t)
                actor={'id':0,'name':t['name'],'attributes':t.get('attributes',{}),'talents':t.get('abilities',[]),
                       'health':t['health'],'health_max':t['healthMax'],'portrait_url':t.get('portrait',''),'level':t.get('level',1),'wounds':t.get('wounds',0),
                       'memoryEngagementLimit':t.get('memoryEngagementLimit',0)}
                states=row['state']['conditions'].get(key,{})
                derived=npc_derived({**t,'combatStance':personal.get('active_stance','')},effects(t.get('abilities',[]),inventory),inventory,states,row['state']['round'])
                spells=[];limits={'weaponSets':1}
            result[key]=(actor,derived,inventory,spells,limits)
        from talent_batch_three import party_equipment
        for key,(actor,derived,inventory,spells,limits) in list(result.items()):
            members=[profiles[0] for other,profiles in result.items() if other!=key and self._eligible(row['state'],other) and row['state']['tokens'][other]['team']==row['state']['tokens'][key]['team']]
            party=[effect for member in members for effect in party_equipment(member.get('talents',[]))]
            if party:
                if row['state']['tokens'][key]['kind']=='player':
                    modified=_derived(actor,inventory+virtual_equipment(row['state']['conditions'].get(key,{}),row['state']['round'])+stance_equipment(row['state']['personal'].get(key,{}).get('active_stance',''))+party)
                    modified['healthMax']=derived['healthMax'];modified['_baseDerived']=derived.get('_baseDerived',derived)
                    derived=modified
                else:derived=self._npc_modifiers(derived,party)
                result[key]=(actor,derived,inventory,spells,limits)
        return result

    @staticmethod
    def _npc_modifiers(derived,items):
        from registration_api import _apply_property
        from talent_runtime import attribute_skill_delta
        d=copy.deepcopy(derived);old={k:d['effectiveAttributes'].get(k,10) for k in ('Сила','Искусность','Быстрота','Живучесть','Смекалка','Стойкость')};attrs={k:round(_apply_property(v,items,k)) for k,v in old.items()}
        d['effectiveAttributes']=attrs;attack=d['attack']
        strength=attrs.get('Сила',10)-old.get('Сила',10);dexterity=attrs.get('Искусность',10)-old.get('Искусность',10)
        ratio=max(.1,1+(attrs.get('Сила',10)-10)*.03)/max(.1,1+(old.get('Сила',10)-10)*.03)
        for k in ('damageMin','damageMax'):attack[k]=round(_apply_property(attack.get(k,1)*ratio,items,'Урон'))
        attack['accuracy']=round(_apply_property(attack.get('accuracy',20)+dexterity,items,'Точность'))
        d['abilityAccuracyBonus']=d.get('abilityAccuracyBonus',0)+_apply_property(0,items,'Точность')
        d['killAccuracyBonus']=sum(float(e['Value']) for item in items for e in __import__('item_effects').game_data(item).get('statusEffects',[]) if e.get('runtimeKillBonus'))
        for name,value in d['effectiveSkills'].items():d['effectiveSkills'][name]=round(_apply_property(value+attribute_skill_delta(name,old,attrs),items,name))
        for name,value in d['defenses'].items():
            delta=(attrs.get('Стойкость',10)-old.get('Стойкость',10))*1.5
            if name=='Выносливость':delta+=strength*.5
            elif name=='Воля':delta+=(attrs.get('Живучесть',10)-old.get('Живучесть',10))*.5
            elif name=='Магия':delta+=(attrs.get('Смекалка',10)-old.get('Смекалка',10))*.5
            else:delta=attribute_skill_delta(name,old,attrs)
            d['defenses'][name]=round(_apply_property(value+delta,items,name))
        d['armor']=max(0,_apply_property(d['armor'],items,'Броня'))
        armor_bonus=sum(float(e.get('Value',0)) for item in items for e in __import__('item_effects').game_data(item).get('statusEffects',[]) if e.get('AffectsStat')==32)
        d['armor']+=derived.get('armor',0)*armor_bonus
        d['armorByType']={k:v*(1+armor_bonus) for k,v in derived.get('armorByType',{}).items()}
        d['healthMax']=max(1,round(_apply_property(d['healthMax']+attrs.get('Живучесть',10)-old.get('Живучесть',10),items,'Максимум здоровья')))
        d['cooldownMultiplier']=max(.1,1-(attrs.get('Быстрота',10)-10)*.03)*_apply_property(1,items,'Перезарядка')
        d['movementMultiplier']=_apply_property(1,items,'Передвижение')
        d['consumableEffectiveness']=1+_apply_property(0,items,'Эффективность расходников')/100
        d['weaponSwitchRecoveryBonus']=_apply_property(0,items,'Восстановление смены оружия')
        attack['recovery']=_apply_property(attack.get('recovery',0),items,'Восстановление')
        attack['criticalChance']=_apply_property(attack.get('criticalChance',0),items,'Критический шанс')
        return d

    def _engine(self,row,key,profiles):
        from combat_actor_refs import remap
        s=row['state'];t=s['tokens'][key];actor,derived,inventory,spells,limits=profiles[key]
        engine=BattleEngine(t.get('characterId',0));engine.initialized=True;engine.custom_map=s['map']
        points=lambda field:{(p['x'],p['y']) for p in s['map'].get(field,[])}
        engine.grid=TacticalGrid(s['map']['width'],s['map']['height'],points('blocked'),points('sightBlocked'),points('cover'))
        engine.player_position=(t['x'],t['y']);engine.player_health=t['health'];engine.player_health_max=t['healthMax'];engine.player_base_health_max=derived['healthMax'];engine.token_movement=t.get('movement',5)
        engine.targets={};engine.target_positions={};engine.target_healths={}
        for other,token in s['tokens'].items():
            if other==key:continue
            d=profiles[other][1].get('_baseDerived',profiles[other][1])
            engine.targets[other]={**remap(token,key,'player'),'baseHealthMax':profiles[other][1]['healthMax'],'portrait':profiles[other][0].get('portrait_url',''),'armor':d.get('armor',0),'defenses':d.get('defenses',{}),'attack':d.get('attack',{}),
                'armorByType':d.get('armorByType',{}),'incomingConversions':d.get('incomingConversions',{}),
                'talentRuntime':d.get('talentRuntime',{}),'team':'ally' if token['team']==t['team'] else 'enemy',
                'combatDerived':profiles[other][1],'inventory':profiles[other][2],
                'combatStance':s['personal'].get(other,{}).get('active_stance',''),
                'character':profiles[other][0],'abilities':profiles[other][0].get('talents',[])}
            engine.target_healths[other]=token['health'];engine.target_positions[other]=(token['x'],token['y'])
            if not s['conditions'].get(other,{}).get('restore'):
                engine.targets[other]['healthMax']=profiles[other][1]['healthMax']
                engine.target_healths[other]=min(engine.targets[other]['healthMax'],token['health'])
        engine.conditions={('player' if k==key else k):remap(v,key,'player') for k,v in s['conditions'].items()}
        engine.engagements={('player' if source==key else source):['player' if victim==key else victim for victim in victims]
                            for source,victims in s.get('engagements',{}).items()}
        engine.round_number=s['round'];engine.initiative=[{**i,'id':'player' if i['id']==key else i['id']} for i in s['initiative']]
        if not engine.initiative:engine.initiative=[{'id':'player','name':t['name'],'roll':0,'bonus':0,'total':0}]
        engine.selected_target_id=next(iter(engine._alive_targets()),next(iter(engine.targets),''))
        engine.runtime_talents=actor.get('talents',[]);engine.runtime_derived=derived
        engine.runtime_character=actor
        engine.talent_runtime={int(k):v for k,v in derived.get('talentRuntime',{}).items()}
        engine.consumable_inventory=inventory
        # Unlike training, real inventory has already been reduced on the last request.
        engine.consumable_used={}
        for field in PERSONAL:
            if field in s['personal'].get(key,{}):setattr(engine,field,remap(s['personal'][key][field],key,'player'))
        for pending in engine.pending_graphs:
            if pending['targetId']==key:pending['targetId']='player'
        engine.opportunity_used=set(engine.opportunity_used)
        engine.movement_remaining=min(engine.movement_remaining,engine._movement_limit()+(5 if engine.dash_used else 0))
        return engine

    def _collect(self,row,key,e,presentation=True):
        from combat_actor_refs import remap
        s=row['state'];t=s['tokens'][key];t.update(x=e.player_position[0],y=e.player_position[1],health=e.player_health,healthMax=e.player_health_max)
        for k,token in list(s['tokens'].items()):
            if k!=key and token.get('summonedBy') and k not in e.targets:
                s['tokens'].pop(k);s['personal'].pop(k,None);s['conditions'].pop(k,None)
                s['initiative']=[i for i in s['initiative'] if i['id']!=k]
        for k in e.targets:
            if k not in s['tokens']:
                token=remap(e.targets[k],'player',key)
                token['team']=t['team'] if token.get('team')=='ally' else 'enemy'
                token['baseHealthMax']=token['healthMax']
                s['tokens'][k]=token
                s['initiative'].append({'id':k,'name':token['name'],'roll':0,'bonus':0,'total':0})
            s['tokens'][k].update(x=e.target_positions[k][0],y=e.target_positions[k][1],health=e.target_healths[k],healthMax=e.targets[k]['healthMax'])
        s['conditions']={key if k=='player' else k:remap(v,'player',key) for k,v in e.conditions.items()}
        s['engagements']={(key if source=='player' else source):[key if victim=='player' else victim for victim in victims]
                          for source,victims in getattr(e,'engagements',{}).items()}
        s['personal'][key]={**s['personal'].get(key,{}),**{f:list(getattr(e,f)) if isinstance(getattr(e,f,None),set) else copy.deepcopy(getattr(e,f))
            for f in PERSONAL if hasattr(e,f)}}
        s['personal'][key]=remap(s['personal'][key],'player',key)
        for pending in s['personal'][key].get('pending_graphs',[]):
            if pending['targetId']=='player':pending['targetId']=key
        for event in e.events:
            if event.get('reaction') and event['sourceId']!='player':
                s['personal'].setdefault(event['sourceId'],{})['stealthed']=False
        s['log'].extend(line.replace('Манекен разрушен.','Цель выведена из боя.').replace(' (тренировка — настоящий предмет не расходуется).','.') for line in e.log)
        s['log']=s['log'][-100:]
        if presentation:
            s['events']=[{**ev,'sourceId':key if ev['sourceId']=='player' else ev['sourceId'],'targetId':key if ev['targetId']=='player' else ev['targetId']} for ev in e.events]
            if e.movement_path:s['movementPath']={'actorId':key,'path':[{'x':x,'y':y} for x,y in e.movement_path]}
            else:s.pop('movementPath',None)

    def _eligible(self,state,key):
        t=state['tokens'][key]
        return t['health']>0 and (t['kind']=='npc' or state['participants'].get(str(t['characterId']),{}).get('joined'))

    async def _next(self,row,profiles):
        s=row['state'];s['acted']=list(dict.fromkeys([*s['acted'],s['currentId']]))
        candidates=[i['id'] for i in s['initiative'] if i['id'] in s['tokens'] and self._eligible(s,i['id']) and i['id'] not in s['acted']]
        if not candidates:
            # Each 10-second round pulses every condition once and every caster area once.
            from consumables import pulse
            s['round']+=1;s['acted']=[]
            for key in list(s['tokens']):
                if key not in s['tokens']:continue
                t=s['tokens'][key]
                states=s['conditions'].get(key,{})
                before=t['health']
                e=self._engine(row,key,profiles);e.round_number=s['round']-1
                e._pulse_conditions('player',s['round'])
                self._collect(row,key,e,presentation=False)
                t=s['tokens'][key];states=s['conditions'].get(key,{})
                for name,effect in list(states.items()):
                    if effect.get('masterTick') and effect.get('until',0)>=s['round']-1 and t['health']>0:
                        value=round(effect.get('value',0))
                        t['health']=min(t['healthMax'],t['health']+value) if effect['kind']=='heal' else max(0,t['health']-value)
                        s['log'].append(f"{effect['name']}: «{t['name']}» {'восстанавливает' if effect['kind']=='heal' else 'теряет'} {value} ХП.")
                    if effect.get('kind')=='delayedDamage' and effect.get('triggerRound',0)<=s['round']:
                        t['health']=max(0,t['health']-round(effect['value']));states.pop(name)
                s['conditions'][key]={k:v for k,v in states.items() if v.get('until',0)>=s['round']}
            profiles=await self._profiles(row)
            for key in list(s['tokens']):
                if key not in s['tokens']:continue
                e=self._engine(row,key,profiles)
                e._combat_derived(profiles[key][1])
                from talent_batch_three import advance_graphs
                e.round_number=s['round']
                advance_graphs(e)
                e.recovery_seconds=max(0,e.recovery_seconds-10)
                e.round_number=s['round']
                from talent_batch_four import expire_summons
                expire_summons(e)
                for target,t in e.targets.items():
                    if not e.conditions.get(target,{}).get('restore'):
                        t['healthMax']=t['baseHealthMax'];e.target_healths[target]=min(t['healthMax'],e.target_healths[target])
                e._advance_stealth(max(0,10-e.stealth_elapsed));e.stealth_elapsed=0
                e._advance_songs()
                for area in e.areas:e._pulse_area(area);area['remaining']-=1
                e.areas=[a for a in e.areas if a['remaining']>0]
                e.action_available=True;e.dash_used=False;e.disengaged=False;e.opportunity_used.clear();e.movement_remaining=e._movement_limit()
                self._collect(row,key,e)
            s['log'].append(f"Начался раунд {s['round']}.")
            candidates=[i['id'] for i in s['initiative'] if i['id'] in s['tokens'] and self._eligible(s,i['id'])]
        s['currentId']=candidates[0] if candidates else ''

    async def action(self,ident,guild,owner=None,cid=None,payload=None):
        async with self.lock(ident):
            row=await self.get(ident,guild,owner,cid);s=row['state'];p=payload or {};operation=p.get('operation','act')
            if p.get('revision') is not None and int(p['revision'])!=row['revision']:raise ValueError('Бой изменился. Обновите экран.')
            if row['status']=='ended':raise ValueError('Бой завершён.')
            s['events']=[];s.pop('movementPath',None)
            profiles=await self._profiles(row);deltas=[]
            if owner is not None and p.get('mode')=='play':
                key=str(p.get('actorId',''))
                if row['status']!='active':raise ValueError('Мастер ещё не запустил бой или завершил его.')
                if key!=s['currentId'] or key not in s['tokens']:raise ValueError('Сейчас ход другого участника. Обновите боевой экран.')
                if s['tokens'][key]['kind']!='npc':raise ValueError('Сейчас ход игрока. Мастер наблюдает за боем.')
                if operation not in {'act','quickbar'}:raise ValueError('Правки сцены доступны только в администрировании.')
            if owner is not None and operation=='quickbar':
                key=str(p.get('actorId',''));bindings=p.get('bindings')
                if p.get('mode')!='play' or not isinstance(bindings,list) or len(bindings)!=9:raise ValueError('Укажите девять быстрых ячеек текущего НПС.')
                e=self._engine(row,key,profiles);c,d,inv,spells,limits=profiles[key]
                actions=e.view(c,d,spells,limits['weaponSets'])['actions']
                valid={(a['kind'],a['name']) for a in actions};seen=set();saved=[]
                for binding in bindings:
                    slot=int(binding.get('slot',0));kind=str(binding.get('kind',''));name=str(binding.get('name',''))
                    if not 1<=slot<=9 or slot in seen or (kind,name)!=('','') and (kind,name) not in valid:raise ValueError('Быстрая ячейка содержит недоступное действие.')
                    seen.add(slot);saved.append({'slot':slot,'action_kind':kind,'action_name':name})
                s['personal'].setdefault(key,{})['quickbar']=saved
                await self._save(row);return row
            if owner is not None and operation!='act':
                await self._master_edit(row,p,profiles)
                # Scene edits can add/remove actors and change their modifiers.
                profiles=await self._profiles(row)
            else:
                if row['status']!='active':raise ValueError('Мастер ещё не запустил бой.')
                key=str(p.get('actorId','')) if owner is not None else f'pc_{cid}'
                if key not in s['tokens'] or not self._eligible(s,key):raise ValueError('Участник не вступил в бой или выведен из боя.')
                if owner is None and s['currentId']!=key:raise ValueError('Сейчас ход другого участника.')
                if p.get('kind') in {'end_turn','wait'}:
                    if key!=s['currentId']:raise ValueError('Завершить можно только текущий ход.')
                    s['log'].append(s['tokens'][key]['name']+' завершает ход.');await self._next(row,profiles)
                else:
                    e=self._engine(row,key,profiles);actor,d,inv,spells,limits=profiles[key]
                    target=p.get('targetId');target='player' if target==key else target
                    if not target and 'x' in p and 'y' in p:
                        target=next((k for k,t in s['tokens'].items() if k!=key and (t['x'],t['y'])==(int(p['x']),int(p['y']))),None)
                    if target in s['tokens'] and s['tokens'][target]['team']!=s['tokens'][key]['team'] and self._hidden(s,target):
                        from ability_rules import resolve,profile
                        rule=profile(resolve(p.get('name'))) if p.get('kind')=='ability' and resolve(p.get('name')) else {}
                        if p.get('kind')=='spell':
                            from sigil_data import spell_runtime_profile
                            spell=next((sp for sp in spells if sp['name']==p.get('name')),None)
                            if spell:rule=spell_runtime_profile(spell,skill=0,wits=10)
                        if p.get('kind')=='attack' or rule.get('targeting')=='unit':raise ValueError('Цель скрыта и не обнаружена.')
                    before=dict(getattr(e,'consumable_used',{}))
                    data={**p,'targetId':target} if target else p
                    if s['tokens'][key]['kind']=='npc' and p.get('kind')=='ability':
                        from ability_rules import owned_actions
                        d=e._combat_derived(d)
                        rule=next((a for a in owned_actions(s['tokens'][key].get('abilities',[]),d,d['attack'].get('range',1)) if p.get('name') in {a['key'],a['name']}),None)
                        if not rule:raise ValueError('Способность не назначена НПС.')
                        e.selected_target_id=target or e.selected_target_id
                        e.aim_point=e.player_position if rule['targeting']=='self' or e.selected_target_id=='player' else self._cell(s,p) if 'x' in p and 'y' in p else e.target_positions.get(e.selected_target_id)
                        if e.aim_point is None:raise ValueError('Выберите цель способности.')
                        e._execute_ability(rule,d,inv)
                        if not rule.get('song'):e.action_available=False
                        e._break_stealth('Применение способности раскрывает токен.')
                        if e.target_healths.get(e.selected_target_id,0)<=0 and e._alive_targets():e.selected_target_id=e._alive_targets()[0]
                    else:e.act(data,actor,d,spells,limits['weaponSets'])
                    if s['tokens'][key]['kind']=='player':
                        deltas=[(int(i),count-before.get(i,0),s['tokens'][key]['characterId']) for i,count in getattr(e,'consumable_used',{}).items() if count>before.get(i,0)]
                    self._collect(row,key,e)
            # Moving ANY observer, including a master drag, checks contact.
            for hidden,personal in list(s['personal'].items()):
                if not personal.get('stealthed') or hidden not in profiles:continue
                hiding=self._engine(row,hidden,profiles)
                if any(ev['targetId']==hidden and ev.get('damage',0)>0 for ev in s['events']):hiding._break_stealth('Полученный урон раскрывает персонажа.')
                hiding._advance_stealth(0);self._collect(row,hidden,hiding,presentation=False)
            if row['status']=='active' and s['currentId'] in s['tokens'] and not self._eligible(s,s['currentId']):
                await self._next(row,await self._profiles(row))
            for key,(_,derived,*_) in (await self._profiles(row)).items():
                if not s['conditions'].get(key,{}).get('restore'):
                    t=s['tokens'][key];t['healthMax']=derived['healthMax'];t['health']=min(t['health'],t['healthMax'])
            await self._save(row,deltas);return row

    async def _master_edit(self,row,p,profiles):
        s=row['state'];op=p['operation'];key=str(p.get('tokenId',''))
        if op=='start':
            if row['status']!='lobby':raise ValueError('Бой уже запущен.')
            joined=[cid for cid,m in s['participants'].items() if m['joined']]
            if not joined:raise ValueError('Сначала участники должны вступить через /начать-бой.')
            if len(joined)!=len(s['participants']):raise ValueError('Не все приглашённые участники вступили в бой.')
            if any(f'pc_{cid}' not in s['tokens'] for cid in joined):raise ValueError('Назначьте стартовую клетку каждому вступившему персонажу.')
            occupied=[(t['x'],t['y']) for t in s['tokens'].values()]
            if len(occupied)!=len(set(occupied)):raise ValueError('Токены не могут начинать на одной клетке.')
            s['initiative']=[]
            for token,t in s['tokens'].items():
                if not self._eligible(s,token):continue
                from talent_runtime import effects
                from song_rules import breath_limit
                talents=profiles[token][0].get('talents',[])
                retained=0
                if t['kind']=='player':
                    async with self.db.connect() as c:
                        saved=await c.execute_fetchall('SELECT amount FROM retained_breath WHERE character_id=? AND expires>?',(t['characterId'],time.time()))
                        if saved:retained=saved[0]['amount']
                s['personal'].setdefault(token,{})['breath']=min(breath_limit(talents),retained+int(effects(talents).get(2099,0)))
                roll=random.randint(1,20);bonus=initiative_bonus(profiles[token][0].get('attributes',{}).get('Быстрота',10))
                s['initiative'].append({'id':token,'name':t['name'],'roll':roll,'bonus':bonus,'total':roll+bonus})
            s['initiative'].sort(key=lambda i:-i['total']);s['currentId']=s['initiative'][0]['id'];row['status']='active'
            s['log'].append('Мастер запускает бой.')
        elif op=='finish':row['status']='ended';s['log'].append('Мастер завершает бой.')
        elif op=='time_of_day':
            if p.get('timeOfDay') not in {'day','night'}:raise ValueError('Выберите день или ночь.')
            s['map']['timeOfDay']=p['timeOfDay'];s['log'].append('Мастер задаёт время: '+('ночь' if p['timeOfDay']=='night' else 'день'))
        elif op in {'place_player','add_npc'}:
            if op=='add_npc' and len(s['tokens'])>=100:raise ValueError('Не более 100 токенов в бою.')
            x,y=self._cell(s,p)
            if op=='place_player':
                cid=int(p['characterId'])
                if str(cid) not in s['participants']:raise ValueError('Персонаж не приглашён.')
                c=await self.db.get_character_by_id(cid)
                if not c or c['guild_id']!=row['guild_id']:raise ValueError('Персонаж не найден на сервере.')
                key=f'pc_{cid}';maximum=await self._player_max_health(c)
                t=s['tokens'].get(key,{'kind':'player','characterId':cid,'team':'party','name':c['name'],'health':min(c['health'],maximum),'healthMax':maximum,'baseHealthMax':maximum,'equipmentHealthMax':maximum})
            else:
                from npc_store import NPCStore
                available=await NPCStore(self.db).list(row['guild_id'],row['owner_id'])
                npc=next((n for n in available if n['id']==int(p['npcId'])),None)
                if not npc:raise ValueError('НПС не принадлежит мастеру.')
                key='npc_'+str(max([int(k[4:]) for k in s['tokens'] if k.startswith('npc_')]+[0])+1)
                t={**copy.deepcopy(npc['spec']),'kind':'npc','team':'party' if p.get('team')=='party' else 'enemy','health':npc['spec']['healthMax'],'baseHealthMax':npc['spec']['healthMax']}
            self._vacant(s,key,x,y);s['tokens'][key]={**t,'x':x,'y':y}
            if row['status']=='active' and not any(i['id']==key for i in s['initiative']):s['initiative'].append({'id':key,'name':t['name'],'roll':0,'bonus':0,'total':0})
            s['log'].append(f"Мастер размещает «{t['name']}» в клетке {x}, {y}.")
        elif op=='order':
            order=p.get('order',[])
            if len(order)!=len(s['initiative']) or set(order)!={i['id'] for i in s['initiative']}:raise ValueError('Укажите каждого участника инициативы ровно один раз.')
            by_id={i['id']:i for i in s['initiative']};s['initiative']=[by_id[k] for k in order]
            s['log'].append('Мастер меняет порядок инициативы.')
        elif key not in s['tokens']:raise ValueError('Токен не найден.')
        elif op=='team':
            if p.get('team') not in {'party','enemy'}:raise ValueError('Выберите сторону токена: союзник или противник.')
            s['tokens'][key]['team']=p['team']
            s['log'].append(f"Мастер меняет сторону «{s['tokens'][key]['name']}»: "+('союзник' if p['team']=='party' else 'противник'))
        elif op=='move':
            x,y=self._cell(s,p);self._vacant(s,key,x,y);s['tokens'][key].update(x=x,y=y)
            s['log'].append(f"Мастер передвигает «{s['tokens'][key]['name']}» в {x}, {y}.")
        elif op=='health':
            t=s['tokens'][key];maximum=int(p.get('healthMax',t['healthMax']))
            value=int(p.get('health',t['health']+int(p.get('delta',0))))
            if 'health' not in p and 'delta' in p:value=max(0,min(maximum,value))
            if not 1<=maximum<=100000 or not 0<=value<=maximum:raise ValueError('ХП: 0–максимум; максимум: 1–100000.')
            t.update(health=value,healthMax=maximum);s['log'].append(f"Мастер: ХП «{t['name']}» — {value}/{maximum}.")
            if 'healthMax' in p:t['baseHealthMax']=max(1,maximum-profiles[key][1]['healthMax']+t.get('baseHealthMax',t['healthMax']))
        elif op=='effect':
            kind=str(p.get('effect',''));name=str(p.get('name') or kind)[:100]
            if kind not in {'poison','burn','bleed','stun','paralyze','petrif','freeze','sleep','root','prone','silence','blind','fear','fatigue','heal','shield','guard','accuracy','armor','Сила','Искусность','Быстрота','Живучесть','Смекалка','Стойкость','Парирование','Уклонение','Выносливость','Воля','Магия','damage','movement','incoming'}:raise ValueError('Неизвестный эффект.')
            rounds=int(p.get('rounds',1));value=float(p.get('value',0))
            if not 1<=rounds<=1000 or not -10000<=value<=10000:raise ValueError('Проверьте длительность и силу эффекта.')
            if kind in {'guard','damage','movement','incoming'} and not .1<=value<=10:raise ValueError('Множитель: от 0,1 до 10.')
            if kind in {'poison','burn','bleed','heal','shield'} and value<0:raise ValueError('Сила этого эффекта не может быть отрицательной.')
            effect_id=kind if kind in {'stun','paralyze','petrif','freeze','sleep','root','prone','silence','blind','fear','fatigue'} else 'master:'+str(p.get('effectId') or kind)
            s['conditions'].setdefault(key,{})[effect_id]={'name':name,'kind':'extraDamage' if kind=='damage' else kind,'value':(value-1)*100 if kind=='damage' else value,'until':s['round']+rounds-1,
                'stat':str(p.get('stat',''))[:60],'beneficial':bool(p.get('beneficial'))}
            if kind in {'poison','burn','bleed','heal'}:s['conditions'][key][effect_id]['masterTick']=True
            state=s['conditions'][key][effect_id]
            if kind=='shield':state.update(kind='masterShield',shieldRemaining=value)
            attribute_stats={'Стойкость':56,'Сила':57,'Искусность':58,'Быстрота':59,'Смекалка':99,'Живучесть':100}
            if kind in attribute_stats:
                state.update(kind='masterAttribute',consumable=True,source={'AffectsStat':attribute_stats[kind],'Value':value,'Apply':0})
            s['log'].append(f"Мастер добавляет «{name}» персонажу «{s['tokens'][key]['name']}».")
        elif op=='remove_effect':s['conditions'].setdefault(key,{}).pop(str(p.get('effectId','')),None)
        elif op=='turn':
            if not self._eligible(s,key):raise ValueError('Токен не может ходить.')
            s['currentId']=key;s['log'].append('Мастер передаёт ход: '+s['tokens'][key]['name'])
        elif op=='refresh_turn':
            personal=s['personal'].setdefault(key,{})
            engine=self._engine(row,key,profiles)
            personal.update(action_available=True,movement_remaining=engine._movement_limit(),recovery_seconds=0,
                            dash_used=False,disengaged=False,opportunity_used=[])
        elif op=='remove_token':
            s['tokens'].pop(key);s['personal'].pop(key,None);s['conditions'].pop(key,None)
            s['initiative']=[i for i in s['initiative'] if i['id']!=key]
            if s['currentId']==key:s['currentId']=next((i['id'] for i in s['initiative'] if self._eligible(s,i['id'])),'')
        else:raise ValueError('Неизвестное действие мастера.')

    def _cell(self,s,p):
        x,y=int(p['x']),int(p['y']);m=s['map']
        if not 0<=x<m['width'] or not 0<=y<m['height'] or {'x':x,'y':y} in m['blocked']:raise ValueError('Нельзя поставить токен вне карты или в непроходимой клетке.')
        return x,y

    def _vacant(self,s,key,x,y):
        if any(k!=key and t['health']>0 and (t['x'],t['y'])==(x,y) for k,t in s['tokens'].items()):raise ValueError('Клетка занята другим токеном.')

    @staticmethod
    def _hidden(state,key):
        return bool(state['personal'].get(key,{}).get('stealthed') or any(
            e.get('source',{}).get('AffectsStat')==151 and e.get('until',0)>=state['round']
            for e in state['conditions'].get(key,{}).values()))

    async def view(self,row,cid=None,actor_id=None,master=False,play=False):
        s=row['state'];profiles=await self._profiles(row)
        key=actor_id if master and not play and actor_id in s['tokens'] else f'pc_{cid}' if cid is not None else s['currentId'] or next(iter(s['tokens']),'')
        result={k:row[k] for k in ('id','name','status','revision')};result.update(round=s['round'],participants=s['participants'],currentId=s['currentId'],initiative=s['initiative'],
            log=s['log'][-40:][::-1],map=s['map'],tokens=list({**t,'id':k,'portrait':profiles[k][0].get('portrait_url','')} for k,t in s['tokens'].items()),conditions=s['conditions'])
        if not key or key not in s['tokens']:return result
        e=self._engine(row,key,profiles);c,d,inv,spells,limits=profiles[key]
        if play and self._hidden(s,e.selected_target_id):
            e.selected_target_id=next((k for k in e._alive_targets() if not self._hidden(s,k)),'')
        view=e.view(c,d,spells,limits['weaponSets'])
        view['derived'].pop('_baseDerived',None)
        remap=lambda k:'player' if k==key else k
        view['initiative']=[{**i,'id':remap(i['id'])} for i in s['initiative']]
        view['turn']['actorId']=remap(s['currentId'])
        view['events']=[{**ev,'sourceId':remap(ev['sourceId']),'targetId':remap(ev['targetId'])} for ev in s['events']]
        view.update(mode='battle',battleId=row['id'],revision=row['revision'],viewerId=key,log=s['log'][-40:][::-1],finished=row['status']=='ended')
        if s.get('movementPath'):
            view['movementPath']=s['movementPath']['path'] if s['movementPath']['actorId']==key else []
        your_turn=row['status']=='active' and self._eligible(s,key) and (master and not play or s['currentId']==key and (not play or s['tokens'][key]['kind']=='npc'))
        if not your_turn:
            view['turn']['actionAvailable']=False;view['grid']['reachable']=[];view['grid']['movementPreviews']={}
            reason='Сейчас ход игрока — мастер наблюдает' if play and row['status']=='active' else 'Ожидание своего хода' if row['status']=='active' else 'Мастер ещё не запустил бой'
            for a in view['actions']:a['disabledReason']=reason
        view['grid']['tokens']=[t for t in view['grid']['tokens'] if master and not play or t['id']=='player' or not (s['tokens'][t['id']]['team']!=s['tokens'][key]['team'] and self._hidden(s,t['id']))]
        for token in view['grid']['tokens']:token['kind']=s['tokens'][key if token['id']=='player' else token['id']]['kind']
        if master and play:
            result['controller']={'actorId':key,'name':c['name'],'level':c.get('level',1),'kind':s['tokens'][key]['kind'],'canAct':your_turn}
            result['combatQuickbar']=s['personal'].get(key,{}).get('quickbar',[])
            view['grid']['controllerId']=key
            hidden={k for k,t in s['tokens'].items() if t['team']!=s['tokens'][key]['team'] and self._hidden(s,k)}
            view['targets']=[t for t in view['targets'] if t['id'] not in hidden]
            if view['dummy'].get('id') in hidden:view['dummy']={'name':'Цель не выбрана','health':0,'healthMax':1,'armor':0}
            for action in view['actions']:
                if action.get('targeting')=='unit':
                    for aim in action.get('aims',{}).values():
                        if any(t in hidden for t in aim.get('targetIds',[])):
                            aim.update(valid=False,targetIds=[],previews=[],reason='Цель скрыта и не обнаружена.')
        result['training']=view
        return result
