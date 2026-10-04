/* Targeting and original-game HUD. All highlighted cells come from the server. */
let armedCombatAction=null,combatAim=null,combatBusy=false,trainingMaps=[];
let combatMapZoom=1.25,combatJournalOpen=false;
let combatZoomManual=false,combatFitMapKey='';
let combatMapPan=null;
function combatActionIsFree(action){return !!(action?.song||action?.freeAction||action?.consumesAction===false)}
function combatActionBlock(action){
 if(!action)return 'Действие недоступно';
 if(training?.finished)return 'Бой завершён';
 if(action.limitation)return action.limitation;
 if(action.remaining)return `Перезарядка: ${action.remaining} раунд.`;
 if(!training?.turn?.actionAvailable&&!action.freeOnSelf&&!combatActionIsFree(action))return 'Основное действие потрачено';
 const reason=action.disabledReason||'';
 return reason.startsWith('Цель вне дальности')||reason.startsWith('Цель полностью закрыта')||(reason==='Основное действие потрачено'&&(action.freeOnSelf||combatActionIsFree(action)))?'':reason;
}
function setCombatBusy(value){combatBusy=value;hideCombatTooltip();document.querySelector('.combat-game-screen')?.setAttribute('aria-busy',String(value))}
const gameCombatRoot='assets/game-combat/';
const coreTexture={Огонь:'Core-Fire',Холод:'Core-Frost',Молния:'Core-Shock',Жизнь:'Core-Heal',Истощение:'Core-Weaken',Эмоции:'Core-Passion',Рвение:'Core-Strength',Сила:'Core-Gravity',Камень:'Core-Stone',Терратус:'Core-Gravelight',Иллюзия:'Core-Illusion'};
const originalLocalTalentIcon=localTalentIcon;
localTalentIcon=function(url){if(!url)return '';if(String(url).startsWith('assets/'))return url+'?v=20261002-game';return originalLocalTalentIcon(url)+'?v=20261002-game'};
const originalSigilIcon=sigilIcon;
sigilIcon=function(s,size=''){return originalSigilIcon(s?.image_url?{...s,image_url:s.image_url+'?v=20261002-game'}:s,size)};
spellCoreIcon=function(spell,size='small'){const path=GAME_SPELL_ICONS[`${spell.core}|${spell.expression}`]||`${gameCombatRoot}fx_spellicon_${({Огонь:'fire',Холод:'frost',Молния:'shock',Рвение:'strength',Сила:'gravity'})[spell.core]||'arcane'}.png`;return `<span class="sigil-icon ${size}" data-ui-tip="${esc(spell.name)}\n${esc(spell.core)} · ${esc(spell.expression)}"><img src="${path}" alt="${esc(spell.name)}" loading="lazy"></span>`};
const existingRenderTraining=renderTraining;
const originalCombatPickerPanel=combatPickerPanel;
combatPickerPanel=function(t){
 if(!combatPicker||combatPicker==='initiative')return '';
 if(combatPicker==='stance')return originalCombatPickerPanel(t);
 const actions=(t.actions||[]).filter(x=>combatPicker==='item'?x.kind==='item':combatPicker==='spell'?x.kind==='spell':combatPicker==='artifact'?x.kind==='artifact':['ability','disengage'].includes(x.kind));
 return `<div class="combat-picker"><header><b>${combatPicker==='item'?'РАСХОДНИКИ':combatPicker==='spell'?'ГРИМУАР':combatPicker==='artifact'?'СПОСОБНОСТИ АРТЕФАКТОВ':'УМЕНИЯ'}</b><button data-combat-picker-close aria-label="Закрыть">×</button></header><nav class="combat-picker-tabs"><button data-combat-picker="ability">Умения</button><button data-combat-picker="spell">Заклинания</button><button data-combat-picker="item">Расходники</button></nav><p>${quickbarEditing?`Выберите действие для ячейки ${quickbarEditing} или перетащите его.`:'Нажмите для прицеливания. Перетащите в быстрые ячейки 1–9.'}</p><div class="combat-picker-list">${actions.map(x=>`<div class="combat-choice">${combatActionButton(x,'data-picker-action="1"')}</div>`).join('')||'<p>Нет доступных действий.</p>'}</div></div>`;
};
const statNames={health:'Здоровье',critical:'Критический шанс',accuracy:'Точность',damage:'Урон оружия',recovery:'Восстановление',endurance:'Защита Выносливостью',will:'Защита Волей',magic:'Защита Магией',dodge:'Уклонение',parry:'Парирование',armor:'Поглощение брони',deflection:'Отражение'};
function hudStat(icon,value,label=statNames[icon]){return `<span tabindex="0" data-ui-tip="${esc(label)}: ${esc(value)}" aria-label="${esc(label)}: ${esc(value)}"><img src="assets/stat-icons/${icon}.png?v=20261002-atlas" alt="${esc(label)}">${esc(value)}</span>`}
function hudSongStatus(songs){
 if(!songs?.available)return '';
 const active=songs.active||[],label=`Дыхание ${songs.breath??0} / ${songs.limit??1} · Песни ${active.length} / ${songs.capacity??1}`;
 const details=active.map(song=>`${song.name}${song.phraseName?` — ${song.phraseName}`:''}`).join('\n');
 return `<div class="original-turn combat-song-status" tabindex="0" aria-label="${esc(label)}" data-ui-tip="${esc(label)}${details?`\n${esc(details)}`:''}">${esc(label)}</div>`;
}
function combatJournal(t){
 const lines=t.log||[],latest=lines[0]||'—';
 return `<details class="combat-journal" data-combat-journal ${combatJournalOpen?'open':''}><summary aria-label="Раскрыть или свернуть журнал боя"><span class="combat-journal-latest">${esc(latest)}</span><span class="combat-journal-arrow" aria-hidden="true">▾</span></summary><ol>${lines.map(line=>`<li>${esc(line)}</li>`).join('')}</ol></details>`;
}
function applyCombatMapZoom(panel,t){
 const map=panel.querySelector('.tactical-map');if(!map)return;
 const size=t.grid.layout?.cellSize||48;
 map.style.width=`${t.grid.width*size*combatMapZoom}px`;map.style.height=`${t.grid.height*size*combatMapZoom}px`;
 panel.querySelectorAll('[data-combat-zoom]').forEach(button=>{button.disabled=button.dataset.combatZoom==='in'?combatMapZoom>=2.5:combatMapZoom<=.5});
 const label=panel.querySelector('.combat-zoom-value');if(label)label.textContent=`${Math.round(combatMapZoom*100)}%`;
}
function fitCombatMap(panel,t,force=false){
 const grid=t.grid,key=[grid.id||grid.mapId||'',grid.name||'',grid.image||'',grid.width,grid.height,grid.layout?.cellSize||48].join('|'),changed=key!==combatFitMapKey;
 if(changed)combatZoomManual=false;
 const viewport=panel.querySelector('.tactical-map-wrap');if(!viewport||!viewport.clientWidth||!viewport.clientHeight)return changed;
 combatFitMapKey=key;
 if(!combatZoomManual&&(changed||force)){
  const size=grid.layout?.cellSize||48;
  combatMapZoom=Math.max(.5,Math.min(2.5,(viewport.clientWidth-2)/(grid.width*size),(viewport.clientHeight-28)/(grid.height*size)));
  applyCombatMapZoom(panel,t);viewport.scrollLeft=0;viewport.scrollTop=0;
 }
 return changed;
}
statIcon=function(file,label,value,help=''){const canonical=statNames[file.replace('.png','')]||label;return `<div class="combat-stat" tabindex="0" data-ui-tip="${esc(canonical)}: ${esc(value)}${help?`\n${esc(help)}`:''}" aria-label="${esc(canonical)}: ${esc(value)}"><img src="assets/stat-icons/${file}?v=20261002-atlas" alt="${esc(canonical)}"><span>${esc(label)}</span><b>${esc(value)}</b></div>`};
const originalStatsBox=statsBox;
const attributeSprites={Сила:'might',Искусность:'finesse',Быстрота:'quickness',Живучесть:'health',Смекалка:'wits',Стойкость:'resolve'};
statsBox=function(c,d,editable=true){let index=0;const entries=Object.entries(c.attributes);return originalStatsBox(c,d,editable).replace(/<div class="stat"><div>/g,()=>{const [name,value]=entries[index++];return `<div class="stat"><div><img class="character-attribute-icon" src="${gameCombatRoot}icon_attribute_${attributeSprites[name]}.png" alt="${esc(name)}" data-ui-tip="${esc(name)}: ${value}\n${esc(d.attributeDetails?.[name]?.description||'')}">`})};
function combatOrderPanel(t){
 const player=t.grid.tokens.find(x=>x.id==='player'),alive=new Map(t.grid.tokens.map(x=>[x.id,x]));
 return `<aside class="combat-turn-order" aria-label="Очередность ходов"><header>ОЧЕРЕДНОСТЬ · РАУНД ${t.round}</header>${(t.initiative||[]).map((row,index)=>{const token=alive.get(row.id),active=row.id===t.turn.actorId,portrait=token?.portraitUrl;return `<div class="turn-order-row ${active?'current':''} ${token?'':'defeated'}" data-ui-tip="${esc(row.name)}\nИнициатива: бросок ${row.roll} + бонус ${row.bonus} = ${row.total}${!token?'\nВыведен из боя':row.id!=='player'?'\nТренировочный манекен пропускает ход':''}"><b>${index+1}</b><span class="order-token ${row.id==='player'?'player':'enemy'}">${portrait?`<img src="${esc(portrait)}" alt="${esc(row.name)}">`:esc(row.id==='player'?(row.name||'?')[0]:'♟')}</span><span><strong>${esc(row.name)}</strong><small>${!token?'Выведен из боя':active?'Сейчас ходит':row.id==='player'?'Персонаж':'Пропускает ход'}</small></span><em title="Итоговая инициатива">${row.total}</em></div>`}).join('')}</aside>`;
}
function saveQuickbarBinding(slot,kind,name,sourceSlot=0){if(!Number.isInteger(slot)||slot<1||slot>9||!Number.isInteger(sourceSlot)||sourceSlot<0||sourceSlot>9)return;const bindings=Array.from({length:9},(_,i)=>{const action=quickbarAction(i+1,training.actions);return {slot:i+1,kind:action?.kind||'',name:action?.name||''}});const previous={...bindings[slot-1]};bindings[slot-1]={slot,kind,name};if(sourceSlot)bindings[sourceSlot-1]={...previous,slot:sourceSlot};return mutate('combat-quickbar',{bindings})}
function combatGlyph(action){
 if(action.kind==='spell'){const spell=(data?.spells||[]).find(s=>s.name===action.name);if(spell)return spellCoreIcon(spell,'combat');return `<img src="${gameCombatRoot}${coreTexture[action.core]||'Core-Strength'}.png" alt="${esc(action.name)}">`}
 if(action.icon)return `<img src="${esc(localTalentIcon(action.icon))}" alt="" onerror="this.remove()">`;
 const talent=(data?.talentLibrary||[]).find(t=>t.name===action.name);
 if(talent?.icon_url)return `<img src="${esc(localTalentIcon(talent.icon_url))}" alt="" onerror="this.remove()">`;
 return `<img src="assets/stat-icons/${action.kind==='attack'?'damage':'accuracy'}.png" alt="">`;
}
renderTraining=function(panel,character){
 const oldViewport=panel.querySelector('.tactical-map-wrap'),scroll=oldViewport?{left:oldViewport.scrollLeft,top:oldViewport.scrollTop}:null;
 hideCombatTooltip();
 existingRenderTraining(panel,character);
 if(!training?.active){combatFitMapKey='';combatZoomManual=false;if(training&&trainingMaps.length)panel.querySelector('.training-start')?.insertAdjacentHTML('beforebegin',`<label class="training-map-select">Карта <select id="training-map"><option value="">${trainingMaps.some(m=>m.name.trim().toLowerCase()==='тренировочное поле')?'Тренировочное Поле (по умолчанию)':'Стандартная площадка'}</option>${trainingMaps.map(map=>`<option value="${map.id}">${esc(map.name)}</option>`).join('')}</select></label>`);return}
 const t=training,d=t.derived||{},a=d.attack||{},turn=t.turn||{},player=(t.grid.tokens||[]).find(x=>x.id==='player'),hud=panel.querySelector('.tyranny-combat-hud');
 const stat=hudStat;
 const slots=Array.from({length:9},(_,i)=>{const x=quickbarAction(i+1,t.actions||[]);return `<button draggable="${!!x}" class="original-quick ${x?.remaining?'cooling':''}" data-quick-slot="${i+1}" data-ui-tip="${esc(x?.name||'Назначить действие')}\nНажатие — прицелиться. ПКМ — заменить. Перетащите на другую ячейку для обмена." ${x?`data-training-kind="${esc(x.kind)}" data-training-name="${esc(x.name)}"`:''} aria-label="Ячейка ${i+1}: ${esc(x?.name||'пусто')}" ${t.finished?'disabled':''}>${x?combatGlyph(x):'<span>+</span>'}<kbd>${i+1}</kbd>${x?.remaining?`<i>${x.remaining}</i>`:''}</button>`}).join('');
 const portrait=t.character.portraitUrl?`<img src="${esc(t.character.portraitUrl)}" alt="${esc(character.name)}">`:`<span>${esc(character.name[0])}</span>`;
 const menu=(key,icon,label)=>`<button data-combat-picker="${key}" title="${label}" aria-label="${label}"><img src="${icon}" alt=""></button>`;
 hud.innerHTML=`<div class="original-hud-name">${esc(character.name)}</div><div class="original-hotkeys">${slots}<button class="edit-hotkeys" data-combat-picker="ability" title="Назначить быстрые действия">+</button></div><div class="original-hud-body"><div class="original-portrait">${portrait}<div class="original-hp" style="--hp:${Math.max(0,(player?.health||0)/Math.max(1,player?.healthMax||1)*100)}%"></div><i>${character.level||1}</i></div><div class="original-hud-values"><div class="original-stat-row">${stat('health',player?.health||0,'Здоровье')}${stat('accuracy',a.accuracy||0,'Точность')}${stat('damage',`${a.damageMin}–${a.damageMax}`,'Урон оружия')}</div><div class="original-stat-row">${stat('endurance',d.defenses?.Выносливость||0,'Защита Выносливостью')}${stat('will',d.defenses?.Воля||0,'Защита Волей')}${stat('magic',d.defenses?.Магия||0,'Защита Магией')}</div><div class="original-stat-row">${stat('dodge',d.defenses?.Уклонение||0,'Уклонение')}${stat('parry',d.defenses?.Парирование||0,'Парирование')}${stat('armor',d.armor||0,'Броня')}</div><div class="original-turn">${turn.movementRemaining} / ${turn.movementMax} м · ${turn.actionAvailable?'Действие готово':'Действие потрачено'}</div><div class="original-menus"><button data-training-kind="attack" data-training-name="Обычная атака" title="Атаковать"><img src="assets/stat-icons/damage.png" alt=""></button>${menu('ability','assets/stat-icons/accuracy.png','Умения')}${menu('spell',gameCombatRoot+'Core-Shock.png','Заклинания')}${menu('artifact',gameCombatRoot+'icon_option_reputation.png','Способности артефактов')}${menu('stance','assets/stat-icons/parry.png','Стойки')}${menu('initiative','assets/stat-icons/will.png','Инициатива и журнал')}<button data-training-kind="end_turn" title="Завершить ход"><img src="assets/stat-icons/recovery.png" alt=""></button></div></div></div><div class="original-sets">${Array.from({length:t.character.weaponSets||2},(_,i)=>`<button class="${t.character.activeWeaponSet===i+1?'active':''}" data-training-set="${i+1}">${['I','II','III','IV'][i]}</button>`).join('')}<small>${t.activeStance?esc(t.activeStance):'Стойка не выбрана'}</small></div>`;
 panel.querySelector('.tactical-map').insertAdjacentHTML('beforeend','<div class="combat-targeting-banner" hidden></div><div class="combat-vfx-layer" aria-hidden="true"></div>');
 renderPersistentAreas(panel,t);
 hud.querySelector('.original-stat-row').insertAdjacentHTML('beforeend',stat('critical',`${a.criticalChance||0}%`)+stat('recovery',roundText(a.recovery||0)));
 hud.querySelectorAll('.original-stat-row')[2]?.insertAdjacentHTML('beforeend',stat('deflection',`${d.deflection||0}%`));
 const end=hud.querySelector('[data-training-kind="end_turn"]');end.className='combat-end-turn';end.textContent='ЗАВЕРШИТЬ ХОД';end.disabled=!!t.finished;
 hud.querySelector('.original-turn').insertAdjacentHTML('afterend',hudSongStatus(t.songs));
 panel.querySelector('.training-reset').textContent='ЗАВЕРШИТЬ ТРЕНИРОВКУ';
 const edit=hud.querySelector('.edit-hotkeys');edit.textContent='⚙';edit.dataset.uiTip='Перетащите умение или заклинание из отдельного списка в ячейку 1–9';edit.setAttribute('aria-label','Настроить быстрые ячейки');edit.removeAttribute('title');
 // Controls belong to the arena sidebar, never to the scrolling map surface.
 const arena=panel.querySelector('.combat-arena'),sidebar=document.createElement('aside');
 sidebar.className='combat-sidebar';sidebar.setAttribute('aria-label','Управление боем');
 arena.prepend(sidebar);sidebar.innerHTML=combatOrderPanel(t);sidebar.append(hud);
 panel.querySelectorAll('.combat-picker,.combat-info-drawer').forEach(drawer=>sidebar.append(drawer));
 panel.querySelectorAll('.original-menus button').forEach(button=>{button.dataset.uiTip=button.title||button.textContent;button.querySelector('img')?.setAttribute('alt',button.title);button.removeAttribute('title');});
 const menus={ability:'icon_option_skilltree',spell:'icon_option_spell_creation',stance:'icon_hud_stance',initiative:'icon_option_formation',artifact:'icon_option_reputation'};
 hud.querySelectorAll('.original-menus [data-combat-picker]').forEach(button=>{button.querySelector('img').src=gameCombatRoot+menus[button.dataset.combatPicker]+'.png'});
 hud.querySelector('.original-menus [data-training-kind="attack"] img').src=gameCombatRoot+'icon_option_attack.png';
 hud.querySelector('.original-menus').insertAdjacentHTML('beforeend',menu('item',gameCombatRoot+'icon_option_inventory.png','Расходники'));
 hud.querySelectorAll('[data-training-set]').forEach(button=>{button.dataset.uiTip=`Комплект оружия ${button.dataset.trainingSet}`;button.innerHTML=`<img src="${gameCombatRoot}icon_weaponset_${button.dataset.trainingSet}.png" alt="Комплект ${button.dataset.trainingSet}">`});
 // Distant targets must not prevent entering targeting mode.
 panel.querySelectorAll('[data-training-kind]').forEach(button=>{const x=(t.actions||[]).find(x=>x.kind===button.dataset.trainingKind&&x.name===button.dataset.trainingName);if(x){button.disabled=!!t.finished;button.setAttribute('aria-disabled',String(!!combatActionBlock(x)));button.removeAttribute('data-effect-cells');button.removeAttribute('title');const status=button.querySelector('em');if(status)status.textContent=x.remaining?`Готово через ${x.remaining} раунд.`:`Дальность: ${x.range||0} м · выберите цель`;}});
 panel.querySelectorAll('[data-action-kind]').forEach(button=>{const x=(t.actions||[]).find(x=>x.kind===button.dataset.actionKind&&x.name===button.dataset.actionName);if(x)button.querySelector('img, .sigil-icon, span')?.replaceWith(document.createRange().createContextualFragment(combatGlyph(x)))});
 const rail=document.createElement('nav');rail.className='combat-hud-rail';rail.setAttribute('aria-label','Разделы боевых действий');
 for(const key of ['ability','spell','artifact','item']){const button=hud.querySelector(`.original-menus [data-combat-picker="${key}"]`);if(button)rail.append(button.cloneNode(true))}
 hud.prepend(rail);
 const bottom=hud.querySelector('.original-menus'),resource=hud.querySelector('.original-turn');
 resource.classList.add('combat-turn-resources');resource.innerHTML=`<span>${resource.innerHTML}</span>`;resource.append(end);
 const move=document.createElement('button');move.dataset.combatMove='1';move.dataset.uiTip='Передвижение';move.setAttribute('aria-label','Передвижение');move.innerHTML='<img src="assets/stat-icons/dodge.png" alt="Передвижение">';
 for(const key of ['ability','spell','artifact','stance','move','attack','item','initiative']){
  const button=key==='move'?move:key==='attack'?bottom.querySelector('[data-training-kind="attack"]'):bottom.querySelector(`[data-combat-picker="${key}"]`);if(button)bottom.append(button);
 }
 const statuses=Object.values(t.conditions?.player||{});
 hud.querySelector('.original-turn').insertAdjacentHTML('beforebegin',`<div class="combat-hud-statuses" aria-label="Эффекты персонажа">${statuses.map(state=>`<span tabindex="0" data-ui-tip="${esc(state.name)}${state.stacks>1?` ×${state.stacks}`:''}">${esc(state.name)}</span>`).join('')}</div>`);
 const tools=document.createElement('div');tools.className='combat-map-tools';tools.innerHTML=`${combatJournal(t)}<div class="combat-zoom-controls" aria-label="Масштаб карты"><button data-combat-zoom="out" aria-label="Уменьшить карту">−</button><output class="combat-zoom-value"></output><button data-combat-zoom="in" aria-label="Увеличить карту">+</button></div>`;arena.append(tools);
 panel.querySelector('.combat-info-drawer ol')?.remove();
 const initiativeButton=hud.querySelector('[data-combat-picker="initiative"]');if(initiativeButton){initiativeButton.dataset.uiTip='Инициатива';initiativeButton.setAttribute('aria-label','Инициатива')}
 applyCombatMapZoom(panel,t);
 const mapChanged=fitCombatMap(panel,t),viewport=panel.querySelector('.tactical-map-wrap');if(scroll&&viewport&&!mapChanged){viewport.scrollLeft=scroll.left;viewport.scrollTop=scroll.top}
 panel.querySelector('.combat-game-screen')?.setAttribute('aria-busy',String(combatBusy));
 if(armedCombatAction){armedCombatAction=(t.actions||[]).find(x=>x.kind===armedCombatAction.kind&&x.name===armedCombatAction.name)||null;if(combatActionBlock(armedCombatAction))clearCombatAim();else showCombatAim(combatAim||{x:player.x,y:player.y})}
};
document.addEventListener('toggle',event=>{if(event.target.matches?.('[data-combat-journal]'))combatJournalOpen=event.target.open},true);
function handleCombatMapZoom(event){
 const button=event.target.closest('[data-combat-zoom]');if(!button||!training?.active)return;
 event.preventDefault();event.stopImmediatePropagation();
 hideCombatTooltip();
 const panel=$('#panel'),viewport=panel.querySelector('.tactical-map-wrap'),oldZoom=combatMapZoom;
 const center=viewport?{x:(viewport.scrollLeft+viewport.clientWidth/2)/oldZoom,y:(viewport.scrollTop+viewport.clientHeight/2)/oldZoom}:null;
 combatZoomManual=true;combatMapZoom=Math.max(.5,Math.min(2.5,combatMapZoom+(button.dataset.combatZoom==='in'?.25:-.25)));
 applyCombatMapZoom(panel,training);
 if(center){viewport.scrollLeft=center.x*combatMapZoom-viewport.clientWidth/2;viewport.scrollTop=center.y*combatMapZoom-viewport.clientHeight/2}
}
function handleCombatMovement(event){
 const button=event.target.closest('[data-combat-move]');if(!button||!training?.active)return;
 event.preventDefault();event.stopImmediatePropagation();hideCombatTooltip();clearCombatAim();
 combatPicker='';quickbarEditing=0;renderTraining($('#panel'),data.character);
}
function clearCombatAim(){armedCombatAction=null;combatAim=null;document.querySelectorAll('.aim-range,.aim-effect,.aim-target,.aim-invalid,.original-quick.armed').forEach(e=>e.classList.remove('aim-range','aim-effect','aim-target','aim-invalid','armed'));document.querySelectorAll('[data-aim-enabled]').forEach(cell=>{cell.disabled=true;delete cell.dataset.aimEnabled});document.querySelector('.tactical-map')?.classList.remove('targeting');const banner=document.querySelector('.combat-targeting-banner');if(banner)banner.hidden=true;document.querySelector('.spell-trajectory')?.classList.remove('visible')}
function renderPersistentAreas(panel,t){
 const map=panel.querySelector('.tactical-map'),layout=t.grid.layout||{};
 if(t.grid.source==='Карта мастера'){
  map.style.width=`${t.grid.width*(layout.cellSize||48)}px`;map.style.height=`${t.grid.height*(layout.cellSize||48)}px`;map.style.minHeight='0';
  map.style.setProperty('--grid-opacity',layout.gridOpacity??.3);map.closest('.tactical-map-wrap')?.querySelector('footer a')?.remove();map.style.backgroundSize=`${(layout.imageScale||1)*100}% auto`;map.style.backgroundPosition=`calc(50% + ${layout.offsetX||0}px) calc(50% + ${layout.offsetY||0}px)`;
 }
 const colors={Холод:'#80c6dc',Огонь:'#ce6841',Жизнь:'#7eb877',Истощение:'#a47ec4',Эмоции:'#bc83a5'};
 for(const [key,cls] of [['sightBlocked','map-sight'],['cover','map-cover']])for(const p of t.grid[key]||[])map.querySelector(`[data-cell="${p.x}:${p.y}"]`)?.classList.add(cls);
 for(const area of t.areas||[]){const color=colors[area.core]||'#8999b1';for(const p of area.cells){map.insertAdjacentHTML('beforeend',`<div class="persistent-area-cell" style="left:${p.x/t.grid.width*100}%;top:${p.y/t.grid.height*100}%;width:${100/t.grid.width}%;height:${100/t.grid.height}%;--area-color:${color}"></div>`)}map.insertAdjacentHTML('beforeend',`<small class="persistent-area-label" style="left:${(area.center.x+.5)/t.grid.width*100}%;top:${(area.center.y+.5)/t.grid.height*100}%">${esc(area.name)} · ещё ${area.remaining} срабатыв.</small>`)}
 for(const token of t.grid.tokens){const element=map.querySelector(`[data-cell="${token.x}:${token.y}"] .combat-token`);if(element){element.removeAttribute('title');element.dataset.uiTip=`${token.name}\n${Object.values(t.conditions?.[token.id]||{}).map(s=>`${s.name}${s.stacks>1?' ×'+s.stacks:''}`).join('\n')}`}}
}
async function animateTokenMovement(oldGrid,newGrid,path=[]){
 if(!oldGrid||!newGrid||matchMedia('(prefers-reduced-motion: reduce)').matches)return;
 const map=document.querySelector('.tactical-map');if(!map)return;
 const rect=map.getBoundingClientRect(),cw=rect.width/newGrid.width,ch=rect.height/newGrid.height;
 await Promise.all((newGrid.tokens||[]).map(async token=>{const old=oldGrid.tokens.find(p=>p.id===token.id);if(!old||(old.x===token.x&&old.y===token.y))return;const element=map.querySelector(`[data-cell="${token.x}:${token.y}"] .combat-token`);if(!element)return;
 const points=token.id==='player'&&path?.length>1?path:[old,token],frames=points.map(p=>({transform:`translate(calc(-50% + ${(p.x-token.x)*cw}px),calc(-50% + ${(p.y-token.y)*ch}px))`}));element.style.zIndex='15';try{await element.animate(frames,{duration:Math.min(1200,Math.max(220,(points.length-1)*120)),easing:'linear'}).finished}catch{}finally{element.style.zIndex=''}
 }));
}
trainingMutate=async function(path,body={}){
 if(combatBusy)return;setCombatBusy(true);const oldGrid=training?.grid;
 if(path==='start'){const selected=document.querySelector('#training-map')?.value;if(selected)body.mapId=Number(selected)}
 try{const j=await request(`/api/portal/${encodeURIComponent(token)}/training/${path}`,{method:'POST',body:JSON.stringify(body)});training=j.training||{active:false};if(path==='start'){combatFitMapKey='';combatZoomManual=false}if(tab==='training'){renderTraining($('#panel'),data.character);if(path==='start')document.querySelector('.combat-game-screen')?.scrollIntoView({block:'start',behavior:'instant'})}await animateTokenMovement(oldGrid,training.grid,training.movementPath);toast(j.message)}catch(error){toast(error.message)}finally{setCombatBusy(false)}
};
const originalLoadTraining=loadTraining;
loadTraining=async function(){await originalLoadTraining();try{const j=await request(`/api/portal/${encodeURIComponent(token)}/training`);trainingMaps=j.maps||[];if(tab==='training'&&!training?.active)renderTraining($('#panel'),data.character)}catch{}};
function showCombatAim(point){
 if(!armedCombatAction||!training?.active)return;
 combatAim=point;const action=armedCombatAction,aim=action.aims?.[`${point.x}:${point.y}`],player=training.grid.tokens.find(t=>t.id==='player'),map=document.querySelector('.tactical-map');
 if(!map||!player)return;
 document.querySelectorAll('[data-quick-slot]').forEach(slot=>slot.classList.toggle('armed',slot.dataset.trainingKind===action.kind&&slot.dataset.trainingName===action.name));
 map.classList.add('targeting');map.dataset.previewTargeting=action.targeting||'unit';
 document.querySelectorAll('.aim-range,.aim-effect,.aim-target,.aim-invalid').forEach(e=>e.classList.remove('aim-range','aim-effect','aim-target','aim-invalid'));
 document.querySelectorAll('[data-cell]').forEach(cell=>{if(cell.disabled){cell.dataset.aimEnabled='1';cell.disabled=false}const [x,y]=cell.dataset.cell.split(':').map(Number);if(Math.max(Math.abs(x-player.x),Math.abs(y-player.y))<=(action.range||0))cell.classList.add('aim-range')});
 for(const cell of aim?.cells||[])document.querySelector(`[data-cell="${cell.x}:${cell.y}"]`)?.classList.add('aim-effect');
 document.querySelector(`[data-cell="${point.x}:${point.y}"]`)?.classList.add(aim?.valid?'aim-target':'aim-invalid');
 const affected=(aim?.targetIds||[]).map(id=>training.grid.tokens.find(token=>token.id===id)?.name).filter(Boolean),names=affected.slice(0,3).map(name=>name.length>24?name.slice(0,23)+'…':name).join(', ');
 const banner=document.querySelector('.combat-targeting-banner');banner.hidden=false;banner.classList.toggle('invalid',!aim?.valid);banner.textContent=`${action.displayName||action.name} · ${aim?.valid?'Нажмите для применения':'Недоступная цель или клетка'}${names?` · ${names}${affected.length>3?` +${affected.length-3}`:''}`:''} · Esc / ПКМ — отмена`;
 const line=document.querySelector('.spell-trajectory line');if(line){line.setAttribute('x2',point.x+.5);line.setAttribute('y2',point.y+.5);line.parentElement.classList.add('visible')}
}
function ensureCombatMapVisible(){const viewport=document.querySelector('.tactical-map-wrap'),rect=viewport?.getBoundingClientRect?.();if(rect&&(rect.bottom<48||rect.top>=(globalThis.innerHeight||900)-64))viewport.scrollIntoView({block:'nearest',behavior:'smooth'})}
function armCombatAction(action){if(combatBusy)return;const blocked=combatActionBlock(action);if(blocked){toast(blocked);return}armedCombatAction=action;combatPicker='';quickbarEditing=0;hideCombatTooltip();renderTraining($('#panel'),data.character);const player=training.grid.tokens.find(t=>t.id==='player');showCombatAim(action.targeting==='self'||action.targeting==='aura'||action.freeOnSelf?player:training.grid.tokens.find(t=>t.selected)||player);ensureCombatMapVisible()}
async function confirmCombatAim(point){
 if(combatBusy||!armedCombatAction)return;const action=armedCombatAction,aim=action.aims?.[`${point.x}:${point.y}`];if(!aim?.valid){toast('Выберите доступную цель или клетку.');return}
 const blocked=combatActionBlock(action);if(blocked){toast(blocked);return}
 const target=training.grid.tokens.find(t=>t.x===point.x&&t.y===point.y);
 if(!training.turn.actionAvailable&&action.freeOnSelf&&!combatActionIsFree(action)&&target?.id!=='player'){toast('Основное действие потрачено');return}
 const oldGrid=training.grid;setCombatBusy(true);
 try{const j=await request(`/api/portal/${encodeURIComponent(token)}/training/action`,{method:'POST',body:JSON.stringify({kind:action.kind,name:action.name,x:point.x,y:point.y,targetId:target?.id})});training=j.training;clearCombatAim();if(tab==='training'){renderTraining($('#panel'),data.character);await animateTokenMovement(oldGrid,training.grid,training.movementPath);await playCombatEffect(action,point,oldGrid,aim.cells||[])}toast(j.message)}catch(error){toast(error.message)}finally{setCombatBusy(false)}
}
async function playCombatEffect(action,point,grid,cells){
 const layer=document.querySelector('.combat-vfx-layer');if(!layer)return;
 const player=grid.tokens.find(t=>t.id==='player'),core=action.core||'Сила',reduced=matchMedia('(prefers-reduced-motion: reduce)').matches;
 const colors={Огонь:'#ff682b',Холод:'#8ceeff',Молния:'#75baff',Истощение:'#c673ff',Терратус:'#58edd0',Жизнь:'#98f58e',Рвение:'#ff6274',Камень:'#d6b38b',Сила:'#97baff',Эмоции:'#f4a6eb'};
 const color=colors[core]||'#dfdcce',x=(point.x+.5)/grid.width*100,y=(point.y+.5)/grid.height*100,sx=(player.x+.5)/grid.width*100,sy=(player.y+.5)/grid.height*100;
 const bounds=layer.getBoundingClientRect(),dx=(x-sx)*bounds.width/100,dy=(y-sy)*bounds.height/100,angle=Math.atan2(dy,dx),nodes=[];let casterAnimation=null;
 layer.style.setProperty('--vfx-color',color);
 function make(className,px,py){const node=document.createElement('div');node.className=className;node.style.left=px+'%';node.style.top=py+'%';layer.append(node);nodes.push(node);return node}
 async function animate(node,frames,options){try{await node.animate(frames,options).finished}catch{}}
 try{
 const caster=document.querySelector(`[data-cell="${player.x}:${player.y}"] .combat-token`);
 if(caster&&!reduced){casterAnimation=caster.animate([{transform:'translate(-50%,-50%)'},{transform:`translate(calc(-50% + ${Math.cos(angle)*5}px),calc(-50% + ${Math.sin(angle)*5}px))`,offset:.4},{transform:'translate(-50%,-50%)'}],{duration:320});casterAnimation.finished?.catch(()=>{})}
 const ranged=action.range>2,shooting=action.kind==='attack'&&['Луки','Дротики'].includes(action.weaponSkill);
 if(action.kind==='attack'&&!ranged){
 const slash=make('combat-slash',x,y);
 await animate(slash,[{opacity:0,transform:'translate(-50%,-50%) rotate(-65deg) scale(.4)'},{opacity:1,offset:.35},{opacity:0,transform:'translate(-50%,-50%) rotate(45deg) scale(1.3)'}],{duration:reduced?120:350});
 }else if(action.kind==='spell'||ranged){
 const aura=['self','aura'].includes(action.targeting);
 if(!reduced){
 const cast=make('combat-cast-ring',sx,sy);
 await animate(cast,[{opacity:0,transform:'translate(-50%,-50%) scale(.2)'},{opacity:.9,offset:.6},{opacity:0,transform:'translate(-50%,-50%) scale(1.2)'}],{duration:200});
 if(!layer.isConnected)return;
 if(!aura&&core==='Молния'&&!shooting){
 const beam=make('combat-energy-beam',sx,sy);beam.style.width=Math.hypot(dx,dy)+'px';beam.style.transform=`translateY(-50%) rotate(${angle}rad)`;
 await animate(beam,[{opacity:0},{opacity:1,offset:.2},{opacity:.4,offset:.5},{opacity:1,offset:.7},{opacity:0}],{duration:320});
 }else if(!aura){
 const projectile=make(shooting?'combat-arrow':'combat-magic-orb',sx,sy);
 const transform=`translate(-50%,-50%) rotate(${angle}rad)`;
 await animate(projectile,[{left:sx+'%',top:sy+'%',opacity:1,transform},{left:x+'%',top:y+'%',opacity:1,transform}],{duration:Math.min(650,240+Math.hypot(dx,dy)*.5),easing:'linear'});
 }
 }
 }
 if(!layer.isConnected)return;
 const impact=make(shooting||action.kind==='attack'?'combat-hit-spark':'combat-spell-bloom',x,y);
 await animate(impact,[{opacity:0,transform:'translate(-50%,-50%) scale(.2)'},{opacity:1,offset:.15},{opacity:0,transform:'translate(-50%,-50%) scale(1.5)'}],{duration:reduced?150:650});
 if(!reduced)for(const p of cells){
 const cell=document.querySelector(`[data-cell="${p.x}:${p.y}"]`);
 cell?.animate([{boxShadow:`inset 0 0 20px ${color}`,background:color+'66'},{boxShadow:'none',background:'transparent'}],{duration:700});
 }
 }finally{casterAnimation?.cancel();nodes.forEach(node=>node.remove())}
}
document.addEventListener('click',e=>{
 if(tab!=='training'||!training?.active)return;
 if(combatBusy&&e.target.closest('.combat-game-screen')){e.stopImmediatePropagation();return}
 const bind=e.target.closest('[data-bind-action]');if(bind){e.preventDefault();e.stopImmediatePropagation();clearCombatAim();saveQuickbarBinding(+bind.dataset.bindSlot,bind.dataset.bindKind,bind.dataset.bindAction);return}
 const assigning=e.target.closest('[data-picker-action]');if(assigning&&quickbarEditing){e.preventDefault();e.stopImmediatePropagation();const slot=quickbarEditing;quickbarEditing=0;clearCombatAim();saveQuickbarBinding(slot,assigning.dataset.actionKind,assigning.dataset.actionName);return}
 const cell=e.target.closest('[data-cell]');if(cell&&armedCombatAction){e.preventDefault();e.stopImmediatePropagation();const [x,y]=cell.dataset.cell.split(':').map(Number);confirmCombatAim({x,y});return}
 if(e.target.closest('[data-tab],[data-view],.training-reset,[data-training-set],[data-stance-name]'))clearCombatAim();
 const button=e.target.closest('[data-training-kind]');if(!button||button.disabled)return;
 if(['end_turn','wait','disengage'].includes(button.dataset.trainingKind))clearCombatAim();
 if(button.matches('[data-picker-action]')&&quickbarEditing)return;
 if(!['attack','ability','spell','artifact','item'].includes(button.dataset.trainingKind))return;
 const action=training.actions.find(x=>x.kind===button.dataset.trainingKind&&x.name===button.dataset.trainingName);if(action){e.preventDefault();e.stopImmediatePropagation();armCombatAction(action)}
},true);
document.addEventListener('pointerover',e=>{if(!armedCombatAction)return;const cell=e.target.closest('[data-cell]');if(cell){const [x,y]=cell.dataset.cell.split(':').map(Number);showCombatAim({x,y})}},true);
document.addEventListener('contextmenu',e=>{if(combatBusy&&e.target.closest('.combat-game-screen')){e.preventDefault();e.stopImmediatePropagation();return}if(armedCombatAction&&e.target.closest('.combat-game-screen')){e.preventDefault();e.stopImmediatePropagation();clearCombatAim();return}const slot=e.target.closest('[data-quick-slot]');if(slot){e.preventDefault();e.stopImmediatePropagation();quickbarEditing=+slot.dataset.quickSlot;combatPicker='ability';renderTraining($('#panel'),data.character)}},true);
document.addEventListener('keydown',e=>{
 if(tab!=='training'||!training?.active||e.repeat||e.altKey||e.ctrlKey||e.metaKey||e.target?.matches?.('input,textarea,select')||e.target?.closest?.('[contenteditable="true"]'))return;
 if(e.key==='Escape'&&(armedCombatAction||combatPicker)){e.preventDefault();e.stopImmediatePropagation?.();clearCombatAim();hideCombatTooltip();if(combatPicker){combatPicker='';quickbarEditing=0;renderTraining($('#panel'),data.character)}return}
 if(!/^[1-9]$/.test(e.key))return;
 if(document.querySelector('dialog[open]'))return;
 e.preventDefault();e.stopImmediatePropagation?.();if(combatBusy)return;
 const slot=Number(e.key),action=quickbarAction(slot,training.actions||[]);
 if(action)armCombatAction(action);else{clearCombatAim();quickbarEditing=slot;combatPicker='ability';renderTraining($('#panel'),data.character)}
},true);
document.addEventListener('dragstart',e=>{if(combatBusy&&e.target.closest('.combat-game-screen')){e.preventDefault();e.stopImmediatePropagation();return}const slot=e.target.closest('[data-quick-slot]');if(!slot?.dataset.trainingKind)return;e.stopImmediatePropagation();e.dataTransfer.setData('application/json',JSON.stringify({kind:slot.dataset.trainingKind,name:slot.dataset.trainingName,sourceSlot:+slot.dataset.quickSlot}));e.dataTransfer.effectAllowed='move'},true);
document.addEventListener('drop',async e=>{
 const slot=e.target.closest('[data-quick-slot]');if(!slot)return;e.preventDefault();e.stopImmediatePropagation();slot.classList.remove('drop-ready');
 if(combatBusy||!training?.active)return;
 try{const action=JSON.parse(e.dataTransfer.getData('application/json')),destination=Number(slot.dataset.quickSlot),source=Number(action.sourceSlot||0);
  if(!(training.actions||[]).some(x=>x.kind===action.kind&&x.name===action.name)||!Number.isInteger(destination)||destination<1||destination>9||!Number.isInteger(source)||source<0||source>9)return;
  if(source){const previous=quickbarAction(source,training.actions);if(previous?.kind!==action.kind||previous?.name!==action.name)return}
  if(destination===source)return;clearCombatAim();hideCombatTooltip();await saveQuickbarBinding(destination,action.kind,action.name,source);
 }catch(error){toast('Не удалось назначить действие.')}
},true);
function combatTooltipTarget(element){return element.closest('[data-training-kind]')||element.closest('[data-ui-tip]')}
function hideCombatTooltip(){const tip=document.querySelector('.game-icon-tooltip');if(tip)tip.hidden=true}
function showIconTooltip(target){
 if(combatBusy){hideCombatTooltip();return}
 if(!target){hideCombatTooltip();return}
 const action=(training?.actions||[]).find(x=>x.kind===target.dataset.trainingKind&&x.name===target.dataset.trainingName);
 const content=action?`${action.name}\n\n${action.description||''}\n\nДальность: ${action.range||0} м${action.area?` · область ${action.area} м`:''}\n${action.remaining?`Перезарядка: ${action.remaining} раунд.`:'Нажмите, затем выберите цель на карте.'}${target.dataset.quickSlot?'\nПеретащите на другую ячейку для обмена.':''}`:target.dataset.uiTip;
 if(!content){hideCombatTooltip();return}
 let popover=document.querySelector('.game-icon-tooltip');if(!popover){popover=document.createElement('div');popover.className='game-icon-tooltip';popover.setAttribute('role','tooltip');document.body.append(popover)}
 popover.textContent=content;popover.hidden=false;const rect=target.getBoundingClientRect(),width=Math.min(360,innerWidth-24);popover.style.width=`${width}px`;popover.style.maxHeight=`${innerHeight-24}px`;popover.style.left=`${Math.max(12,Math.min(rect.left,innerWidth-width-12))}px`;const above=rect.top-popover.offsetHeight-10;popover.style.top=`${above>=12?above:Math.max(12,Math.min(rect.bottom+10,innerHeight-popover.offsetHeight-12))}px`;
}
document.addEventListener('pointerover',e=>showIconTooltip(combatTooltipTarget(e.target)));
document.addEventListener('focusin',e=>showIconTooltip(combatTooltipTarget(e.target)));
document.addEventListener('pointerout',e=>{const target=combatTooltipTarget(e.target);if(target&&!target.contains(e.relatedTarget))hideCombatTooltip()});
document.addEventListener('focusout',hideCombatTooltip);
document.addEventListener('dragstart',hideCombatTooltip);
document.addEventListener('click',hideCombatTooltip);
document.addEventListener('scroll',hideCombatTooltip,true);
document.addEventListener('click',handleCombatMapZoom,true);
document.addEventListener('click',handleCombatMovement,true);
document.addEventListener('dragend',()=>document.querySelectorAll('.drop-ready').forEach(slot=>slot.classList.remove('drop-ready')));
document.addEventListener('pointerdown',e=>{
 const viewport=e.target.closest('.tactical-map-wrap');if(e.button!==1||!viewport)return;
 e.preventDefault();hideCombatTooltip();combatMapPan={viewport,x:e.clientX,y:e.clientY,left:viewport.scrollLeft,top:viewport.scrollTop};viewport.style.cursor='grabbing';
},true);
document.addEventListener('pointermove',e=>{if(!combatMapPan)return;e.preventDefault();const p=combatMapPan;p.viewport.scrollLeft=p.left+p.x-e.clientX;p.viewport.scrollTop=p.top+p.y-e.clientY},true);
function finishCombatMapPan(){if(combatMapPan)combatMapPan.viewport.style.cursor='';combatMapPan=null}
document.addEventListener('pointerup',finishCombatMapPan,true);
document.addEventListener('pointercancel',finishCombatMapPan,true);
function handleCombatViewportResize(){if(training?.active&&!combatZoomManual)fitCombatMap($('#panel'),training,true)}
globalThis.addEventListener?.('resize',handleCombatViewportResize);
