/* Ergonomics layer; all writes still go through the revisioned battle editor API. */
let battleCockpitMode='edit',battlePlacementArmed=false,battleEmbeddedBusy=true;
let battleNpcChoice='',battlePlayerChoice='',battleNewTeam='enemy',battleDelta='5';
const battleFormDrafts=new Map();
let battleSceneQuery='',battleSceneStatus='';
const battleCoreBusy=battleBusy;
battleBusy=function(busy){
 battleCoreBusy(busy);
 const sync=document.querySelector('.battle-editor-sync');if(sync)sync.textContent=busy?'СОХРАНЯЕМ…':'СОХРАНЕНО';
 document.querySelectorAll('.battle-editor-index button,.battle-editor-index input,.battle-editor-index select').forEach(node=>{
  if(busy){node.dataset.battleWasDisabled=String(node.disabled);node.disabled=true}
  else if(node.dataset.battleWasDisabled!==undefined){node.disabled=node.dataset.battleWasDisabled==='true';delete node.dataset.battleWasDisabled}
 });
};
function battleRememberLocation(scene=null){
 if(typeof history==='undefined'||typeof location==='undefined')return;
 const address=new URL(location.href);
 if(scene){address.searchParams.set('battle',scene.id);if(battleToken)address.searchParams.set('actor',battleToken);else address.searchParams.delete('actor')}
 else{address.searchParams.delete('battle');address.searchParams.delete('actor')}
 history.replaceState(null,'',address);
}
battleWorkspace=function(){
 battleRememberLocation();
 const maps=battleIndex.maps,characters=roster||[];
 campaignWorkspace(`<div class="battle-editor-index"><header class="admin-heading"><small>МАСТЕР · БОИ</small><h1>Боевые сцены</h1></header><section class="admin-box"><div class="battle-index-heading"><h2>Ваши бои</h2><input id="battle-scene-search" class="catalog-search" value="${esc(battleSceneQuery)}" placeholder="Название или номер боя"><select id="battle-scene-filter" aria-label="Статус боя">${[['','Все'],['lobby','Расстановка'],['active','Идут'],['ended','Завершены']].map(([key,label])=>`<option value="${key}" ${key===battleSceneStatus?'selected':''}>${label}</option>`).join('')}</select></div><div class="battle-scenes">${battleIndex.battles.map(b=>`<article class="battle-scene-row" data-battle-scene-name="${esc(`${b.name} ${b.id}`.toLocaleLowerCase('ru'))}" data-battle-scene-status="${b.status}"><button class="dark-button" data-open-battle="${b.id}"><b>${esc(b.name)}</b><span>№${b.id} · ${battleStatusNames[b.status]} · раунд ${b.round}</span></button><button class="dark-button" data-battle-open-play="${b.id}">Ходы НПС →</button><button class="dark-button danger" data-battle-delete="${b.id}" aria-label="Удалить бой ${esc(b.name)}">×</button></article>`).join('')||'<p>Сохранённых боёв пока нет.</p>'}</div><p class="battle-help" id="battle-scene-empty" hidden>Нет боёв по этим фильтрам.</p></section><details class="admin-box battle-create-fold" ${battleIndex.battles.length?'':'open'}><summary>+ Создать новый бой</summary><label class="field">Карта<select id="battle-map-choice">${maps.map(m=>`<option value="${m.id}">${esc(m.name)}</option>`).join('')}</select></label>${maps.length?'':'<p>Сначала сохраните карту.</p>'}<div class="battle-participant-toolbar"><input id="battle-participant-search" class="catalog-search" placeholder="Найти персонажа"><button class="dark-button" data-battle-participants="all">Выбрать всех</button><button class="dark-button" data-battle-participants="none">Снять выбор</button><output id="battle-participant-count">Выбрано: 0</output></div><div class="battle-participant-choices">${characters.map(c=>`<label data-battle-participant-name="${esc(c.name.toLocaleLowerCase('ru'))}"><input type="checkbox" name="battle-participant" value="${c.id}"> ${esc(c.name)}</label>`).join('')}</div><button class="action" data-battle-create ${maps.length&&characters.length?'':'disabled'}>Создать бой</button><p class="battle-help">Приглашённые игроки вступают через /начать-бой.</p></details></div>`);
 battleFilterScenes();
};
function battleFilterScenes(){
 const rows=[...document.querySelectorAll('[data-battle-scene-name]')];
 rows.forEach(row=>row.hidden=!row.dataset.battleSceneName.includes(battleSceneQuery.toLocaleLowerCase('ru'))||(battleSceneStatus&&row.dataset.battleSceneStatus!==battleSceneStatus));
 const empty=document.querySelector('#battle-scene-empty');if(empty)empty.hidden=!rows.length||rows.some(row=>!row.hidden);
}
battleInitiativeInspector=function(){
 const b=masterBattle;
 return `<h2>Очередь · раунд ${b.round}</h2><p class="battle-help">Перетащите строку или используйте стрелки. Текущий ход не сбрасывается.</p>${b.initiative.map((i,n)=>{const t=b.tokens.find(t=>t.id===i.id);return `<div class="battle-order-row ${i.id===b.currentId?'current':''}" draggable="${b.status!=='ended'}" data-battle-order-id="${esc(i.id)}"><button data-battle-select="${esc(i.id)}"><span>⠿ ${n+1}. ${esc(i.name)}</span><small>${t?.health<=0?'Выведен из боя':i.id===b.currentId?'Сейчас ходит':`Инициатива ${i.total}`} · ${t?.health??0} ХП</small></button><button data-battle-reorder="${n}:up" ${n===0?'disabled':''} aria-label="Поднять ${esc(i.name)} в очереди">↑</button><button data-battle-reorder="${n}:down" ${n===b.initiative.length-1?'disabled':''} aria-label="Опустить ${esc(i.name)} в очереди">↓</button></div>`}).join('')||'<p>Очередь появится после запуска боя.</p>'}${b.status==='active'?'<button class="dark-button battle-full" data-battle-next>Пропустить текущий ход</button>':''}<button class="action battle-full" data-battle-mode="play">Ходить за текущего НПС →</button>`;
};
const battleCoreAdopt=battleAdopt;
battleAdopt=function(scene){
 const changed=masterBattle?.id!==scene.id,result=battleCoreAdopt(scene);
 if(result&&changed){battleCockpitMode='edit';battlePlacementArmed=false;battleFormDrafts.clear();battleNpcChoice='';battlePlayerChoice=''}
 return result;
};
const battleCoreEdit=battleEdit;
battleEdit=async function(payload){
 const id=masterBattle?.id,actor=battleToken;
 const saved=await battleCoreEdit(payload);
 if(saved&&masterBattle?.id===id&&payload.operation==='health'){
  battleFormDrafts.delete(`${actor}:battle-health`);battleFormDrafts.delete(`${actor}:battle-health-max`);
  if(battleCockpitMode==='edit')renderMasterBattle();
 }
 return saved;
};
function battleModeButtons(){return `<nav class="battle-mode-switch" aria-label="Режим управления боем"><button data-battle-mode="edit" ${battleCockpitMode==='edit'?'aria-current="page"':''}>Редактор</button><button data-battle-mode="play" ${battleCockpitMode==='play'?'aria-current="page"':''}>Ходы по инициативе</button></nav>`}
function battleEffectChips(selected){
 return Object.entries(masterBattle.conditions[selected.id]||{}).map(([key,e])=>`<span class="battle-effect-chip" title="${esc(e.name||key)}: ${e.shieldRemaining!==undefined?`${e.shieldRemaining} поглощения`:e.value??''}"><span>${esc(e.name||key)} <small>${Math.max(0,e.until-masterBattle.round+1)}р</small></span><button data-battle-remove-effect="${esc(key)}" aria-label="Снять ${esc(e.name||key)}">×</button></span>`).join('')||'<span class="battle-help">Нет воздействий</span>';
}
battleTokenInspector=function(selected){
 if(!selected)return '<p class="battle-help">Нажмите токен на поле или выберите его во вкладке «Список».</p>';
 const training=masterBattle.training,turn=training?.viewerId===selected.id?training.turn:null;
 const actions=training?.viewerId===selected.id?(training.actions||[]).filter(a=>a.kind==='ability'):[];
 return `<header class="battle-selected-heading"><span class="battle-avatar ${selected.team==='enemy'?'enemy':'party'}">${battlePicture(selected)}</span><div><h2>${esc(selected.name)}</h2><small>${selected.kind==='player'?'Игрок':'НПС'} · клетка ${selected.x}, ${selected.y}</small></div><button class="dark-button" data-battle-focus title="Показать на карте · F">◎</button></header>
 <div class="battle-health-readout"><strong>${selected.health}<small> / ${selected.healthMax} ХП</small></strong><meter min="0" max="${selected.healthMax}" value="${selected.health}" aria-label="Здоровье"></meter></div>
 <div class="battle-hp-adjust"><button class="dark-button danger" data-battle-damage>− Урон</button><label class="field">Количество<input id="battle-health-delta" type="number" min="1" max="100000" value="${esc(battleDelta)}"></label><button class="dark-button" data-battle-heal>+ Лечение</button></div>
 ${turn?`<div class="battle-resource-summary"><span>${turn.actionAvailable?'Действие готово':'Действие потрачено'}</span><span>Движение: ${turn.movementRemaining??0} клеток</span></div>`:''}
 <div class="battle-token-actions"><button class="dark-button ${battleTool==='move'?'active':''}" data-battle-tool="move" title="Затем нажмите клетку · M">↗ Передвинуть</button><label class="field">Сторона<select id="battle-token-team"><option value="party" ${selected.team!=='enemy'?'selected':''}>Союзник</option><option value="enemy" ${selected.team==='enemy'?'selected':''}>Противник</option></select></label></div>
 <h3 class="battle-section-title">Воздействия</h3><div class="battle-effect-chips">${battleEffectChips(selected)}</div>
 <div class="battle-quick-effects">${[['stun','Оглушить',0],['burn','Горение 5',5],['shield','Щит 20',20],['guard','Защиты ×1,2',1.2]].map(([key,label,value])=>`<button class="dark-button" data-battle-quick-effect="${key}" data-value="${value}" title="${label}: применить на 1 раунд">${label}<small>1 раунд</small></button>`).join('')}</div>
 <details class="battle-fold" data-battle-fold="custom-effect"><summary>Другой эффект / длительность</summary>${battleEffectInspector(selected)}</details>
 <details class="battle-fold" data-battle-fold="exact-health"><summary>Задать точное ХП и максимум</summary><div class="fields"><label class="field">ХП<input id="battle-health" type="number" min="0" max="100000" value="${selected.health}"></label><label class="field">Максимум ХП<input id="battle-health-max" type="number" min="1" max="100000" value="${selected.healthMax}"></label></div><p data-battle-unsaved hidden class="battle-help">Значения ещё не сохранены.</p><button class="dark-button battle-full" data-battle-hp>Сохранить ХП</button></details>
 <details class="battle-fold" data-battle-fold="coordinates"><summary>Точные координаты</summary><div class="fields"><label class="field">X<input id="battle-token-x" type="number" min="0" max="${masterBattle.map.width-1}" value="${selected.x}"></label><label class="field">Y<input id="battle-token-y" type="number" min="0" max="${masterBattle.map.height-1}" value="${selected.y}"></label></div><button class="dark-button battle-full" data-battle-move>Переместить без затрат</button></details>
 ${actions.length?`<details class="battle-fold" data-battle-fold="abilities"><summary>Способности · ${actions.length}</summary><ul>${actions.map(a=>`<li>${esc(a.name)}${a.disabledReason?` — ${esc(a.disabledReason)}`:''}</li>`).join('')}</ul></details>`:''}
 <details class="battle-fold" data-battle-fold="override"><summary>Правки хода и удаление токена</summary><p class="battle-help">Только для исправления сцены. Обычные действия — в режиме инициативы.</p><button class="dark-button" data-battle-operation="turn" ${selected.health>0&&masterBattle.status==='active'?'':'disabled'}>Передать ход этому токену</button><button class="dark-button" data-battle-operation="refresh_turn" ${masterBattle.status==='active'?'':'disabled'}>Вернуть действие и движение</button><button class="dark-button danger" data-battle-operation="remove_token">Убрать из боя</button></details>`;
};
function battleListInspector(){return `<div class="battle-token-list-heading"><h2>Участники · ${masterBattle.tokens.length}</h2><input id="battle-token-search" placeholder="Найти токен · /" aria-label="Поиск токена" value="${esc(battleTokenQuery)}" autocomplete="off"><select id="battle-token-filter" aria-label="Тип токена">${[['all','Все'],['player','Игроки'],['npc','НПС']].map(([key,label])=>`<option value="${key}" ${battleTokenKind===key?'selected':''}>${label}</option>`).join('')}</select></div><div id="battle-token-rows">${battleRosterRows()}</div>`}
battleAddInspector=function(){
 const b=masterBattle,npcs=battleIndex?.npcs||[],players=Object.entries(b.participants),player=battleTool==='place_player';
 if(!battleNpcChoice||!npcs.some(n=>String(n.id)===battleNpcChoice))battleNpcChoice=String(npcs[0]?.id||'');
 if(!battlePlayerChoice||!players.some(([id])=>id===battlePlayerChoice))battlePlayerChoice=players.find(([id])=>!b.tokens.some(t=>t.id===`pc_${id}`))?.[0]||players[0]?.[0]||'';
 return `<h2>${player?'Расстановка игроков':'Добавление НПС'}</h2><div class="battle-tools"><button class="dark-button ${player?'active':''}" data-battle-tool="place_player">Игрок</button><button class="dark-button ${player?'':'active'}" data-battle-tool="add_npc">НПС</button></div>${player?`<label class="field">Игрок<select id="battle-place-player">${players.map(([id,c])=>`<option value="${id}" ${id===battlePlayerChoice?'selected':''}>${esc(c.name)} · ${b.tokens.some(t=>t.id===`pc_${id}`)?'на поле':c.joined?'вступил':'ожидание'}</option>`).join('')}</select></label>`:`<label class="field">Поиск в архиве<input id="battle-npc-search" value="${esc(battleNpcQuery)}" placeholder="Имя НПС" autocomplete="off"></label><div class="battle-npc-palette">${npcs.filter(n=>n.spec.name.toLocaleLowerCase('ru').includes(battleNpcQuery.toLocaleLowerCase('ru'))).map(n=>`<button class="battle-npc-card ${String(n.id)===battleNpcChoice?'selected':''}" data-battle-npc-choice="${n.id}" aria-pressed="${String(n.id)===battleNpcChoice}"><span class="battle-avatar">${battlePicture(n.spec)}</span><span><b>${esc(n.spec.name)}</b><small>${n.spec.healthMax} ХП · ур. ${n.spec.level||1}</small></span></button>`).join('')||'<p class="battle-help">НПС не найдены. Создайте шаблон в архиве НПС.</p>'}</div><select id="battle-place-npc" hidden aria-label="Выбранный НПС">${npcs.map(n=>`<option value="${n.id}" ${String(n.id)===battleNpcChoice?'selected':''}>${esc(n.spec.name)}</option>`).join('')}</select><label class="field">Сторона<select id="battle-place-team"><option value="enemy" ${battleNewTeam==='enemy'?'selected':''}>Противник</option><option value="party" ${battleNewTeam==='party'?'selected':''}>Союзник</option></select></label>`}
 <button class="${battlePlacementArmed?'dark-button':'action'} battle-full" data-battle-arm-placement ${player?!players.length?'disabled':'':!npcs.length?'disabled':''}>${battlePlacementArmed?'Остановить расстановку · Esc':'Размещать нажатием на карту'}</button>
 <p class="battle-placement-instruction" role="status">${battlePlacementArmed?player?'Нажмите свободную клетку — игрок будет размещён.':'Каждое нажатие на свободную клетку добавит копию выбранного НПС.':'Выберите токен, затем включите расстановку.'}</p>
 <details class="battle-fold" data-battle-fold="placement-coordinates"><summary>Разместить по координатам</summary><div class="fields"><label class="field">X<input id="battle-place-x" type="number" value="${battlePlacement?.x??''}"></label><label class="field">Y<input id="battle-place-y" type="number" value="${battlePlacement?.y??''}"></label></div><button class="dark-button battle-full" ${player?'data-battle-place-player':'data-battle-add-npc'}>Разместить</button></details><p id="battle-placement-hint" class="battle-help">${battlePlacement?`Клетка ${battlePlacement.x}, ${battlePlacement.y}`:''}</p>`;
};
const battleCoreSetTool=battleSetTool;
battleSetTool=function(tool){
 battlePlacementArmed=false;battleCoreSetTool(tool);
 if(window.innerWidth<=800)document.querySelector(tool==='move'?'.master-battle-board':['place_player','add_npc'].includes(tool)?'.master-battle-controls':'.master-battle-board')?.scrollIntoView({block:'start',behavior:'smooth'});
};
function battleCaptureForms(){
 const editor=document.querySelector('.master-battle-editor');if(!editor||Number(editor.dataset.scene)!==masterBattle?.id)return;
 const scope=editor.dataset.actor;
 editor.querySelectorAll('[data-battle-fold]').forEach(node=>battleFormDrafts.set(`${scope}:fold:${node.dataset.battleFold}`,node.open));
 editor.querySelectorAll('#battle-effect,#battle-effect-value,#battle-effect-rounds,#battle-effect-beneficial').forEach(node=>battleFormDrafts.set(`${scope}:${node.id}`,node.type==='checkbox'?node.checked:node.value));
}
function battleRestoreForms(){
 const editor=document.querySelector('.master-battle-editor');if(!editor)return;
 editor.querySelectorAll('[data-battle-fold]').forEach(node=>node.open=battleFormDrafts.get(`${battleToken}:fold:${node.dataset.battleFold}`)||false);
 for(const id of ['battle-health','battle-health-max','battle-effect','battle-effect-value','battle-effect-rounds','battle-effect-beneficial']){
  const node=document.getElementById(id),value=battleFormDrafts.get(`${battleToken}:${id}`);if(node&&value!==undefined){if(node.type==='checkbox')node.checked=value;else node.value=value}
 }
 const dirty=battleFormDrafts.has(`${battleToken}:battle-health`)||battleFormDrafts.has(`${battleToken}:battle-health-max`);
 const warning=editor.querySelector('[data-battle-unsaved]');if(warning)warning.hidden=!dirty;
}
renderMasterBattle=function(){
 if(!masterBattle||battleCockpitMode==='play')return;
 battleCaptureForms();
 const viewport=document.querySelector('.master-battle-viewport'),scroll=viewport?{x:viewport.scrollLeft,y:viewport.scrollTop}:null;
 const body=document.querySelector('.battle-inspector-body'),oldActor=body?.dataset.actor,oldPanel=body?.dataset.panel,asideScroll=body?.scrollTop||0;
 const b=masterBattle,m=b.map,selected=b.tokens.find(t=>t.id===battleToken)||b.tokens.find(t=>t.id===b.currentId)||b.tokens[0];battleToken=selected?.id||'';
 battleRememberLocation(b);
 const ended=b.status==='ended',current=b.tokens.find(t=>t.id===b.currentId),has=(key,x,y)=>(m[key]||[]).some(p=>p.x===x&&p.y===y);
 const cells=Array.from({length:m.width*m.height},(_,i)=>{const x=i%m.width,y=Math.floor(i/m.width),stack=b.tokens.filter(t=>t.x===x&&t.y===y),t=stack.find(t=>t.id===battleToken)||stack.find(t=>t.health>0)||stack[0],blocked=has('blocked',x,y);return `<button class="master-battle-cell ${blocked?'blocked':''} ${has('sightBlocked',x,y)?'sight-blocked':''} ${has('cover',x,y)?'cover':''} ${t?.id===battleToken?'selected':''}" data-master-battle-cell="${x}:${y}" aria-label="Клетка ${x}, ${y}${t?` · ${esc(t.name)} · ${t.health}/${t.healthMax}`:''}" ${blocked?'disabled':''}>${t?`<span class="master-battle-token ${t.team==='enemy'?'enemy':'party'} ${t.health<=0?'defeated':''} ${t.id===b.currentId?'current':''}" draggable="${!ended}" data-battle-token="${esc(t.id)}">${battlePicture(t)}<small>${t.health}/${t.healthMax}</small>${stack.length>1?`<em class="battle-stack-count">${stack.length}</em>`:''}</span>`:''}</button>`}).join('');
 const tools=[['select','Выбрать · V'],['move','Передвинуть · M'],['place_player','Игрок'],['add_npc','НПС']];
 const inspector={token:()=>battleTokenInspector(selected),effects:()=>battleEffectInspector(selected),initiative:battleInitiativeInspector,add:battleAddInspector,list:battleListInspector};
 campaignWorkspace(`<div class="master-battle-editor battle-cockpit" data-actor="${esc(battleToken)}"><header class="battle-editor-heading"><div><h1>${esc(b.name)}</h1><p>№${b.id} · ${battleStatusNames[b.status]} · раунд ${b.round}</p></div>${battleModeButtons()}<div class="battle-toolbar"><button class="dark-button" data-open-battles>Все бои</button><button class="dark-button" data-battle-refresh title="Обновить без потери правок">↻</button>${b.status==='lobby'?'<button class="action" data-battle-operation="start">Начать бой</button>':''}<details class="battle-scene-menu"><summary aria-label="Действия с боем">⋯</summary>${b.status==='active'?'<button class="dark-button" data-battle-operation="finish">Завершить бой</button>':''}<button class="dark-button danger" data-battle-delete="${b.id}">Удалить бой</button></details></div></header>
 <div class="battle-scene-status"><button class="battle-current-turn" data-battle-current title="Выбрать текущий токен · C">${current?`${current.kind==='npc'?'Ход НПС':'Ход игрока'}: ${esc(current.name)} ◎`:'Расстановка участников'}</button><label><select id="battle-time-of-day" aria-label="Время суток" ${ended?'disabled':''}><option value="day" ${m.timeOfDay!=='night'?'selected':''}>День</option><option value="night" ${m.timeOfDay==='night'?'selected':''}>Ночь</option></select></label><span class="battle-editor-sync" role="status">СОХРАНЕНО</span></div>
 <div class="master-battle-layout"><section class="master-battle-board"><div class="battle-board-toolbar"><nav class="battle-tools">${tools.map(([key,title])=>`<button class="dark-button ${battleTool===key?'active':''}" data-battle-tool="${key}" aria-pressed="${battleTool===key}" ${ended&&key!=='select'?'disabled':''}>${title}</button>`).join('')}</nav><div class="battle-zoom"><button class="dark-button" data-battle-zoom="-8" aria-label="Отдалить">−</button><output>${Math.round(battleZoom/48*100)}%</output><button class="dark-button" data-battle-zoom="8" aria-label="Приблизить">+</button><button class="dark-button" data-battle-fit title="Вместить карту · 0">Вместить</button><button class="dark-button" data-battle-focus title="К выбранному токену · F">◎</button></div></div>
 <p class="battle-tool-hint">${battlePlacementArmed?'Расстановка включена: нажмите свободную клетку. Esc — остановить.':battleTool==='move'?'Нажмите клетку назначения. Другой токен можно выбрать нажатием.':'Токен → правки справа. Перетащите токен или Shift + нажмите клетку, чтобы передвинуть.'}</p>
 <div class="master-battle-viewport"><div class="master-battle-grid" style="--battle-size:${battleZoom}px;grid-template-columns:repeat(${m.width},var(--battle-size));width:${m.width*battleZoom}px;height:${m.height*battleZoom}px;background-size:${(m.imageScale||1)*100}% auto;background-position:calc(50% + ${m.offsetX||0}px) calc(50% + ${m.offsetY||0}px)">${cells}</div></div>
 <details class="battle-editor-journal"><summary><span>${esc(b.log[0]||'Нет действий.')}</span>Журнал ▾</summary>${b.log.map(line=>`<p>${esc(line)}</p>`).join('')}</details></section>
 <aside class="master-battle-controls"><nav class="battle-inspector-tabs">${[['token','Токен'],['list','Список'],['initiative','Очередь'],['add','Добавить']].map(([key,label])=>`<button data-battle-inspector="${key}" class="${battleInspector===key?'active':''}" aria-pressed="${battleInspector===key}">${label}</button>`).join('')}</nav><section class="battle-inspector-body" data-actor="${esc(battleToken)}" data-panel="${battleInspector}">${(inspector[battleInspector]||inspector.token)()}</section></aside></div>
 <footer class="battle-shortcuts">V — выбор · M — перемещение · F — к токену · C — текущий ход · / — поиск · Esc — отмена <span>Правки сохраняются сразу</span></footer></div>`);
 const grid=document.querySelector('.master-battle-grid');if(grid)grid.style.backgroundImage=m.image?`url("${m.image.replace(/["\\\n\r]/g,'')}")`:'';
 const editor=document.querySelector('.master-battle-editor');if(editor)editor.dataset.scene=String(b.id);
 const next=document.querySelector('.master-battle-viewport');if(scroll&&next){next.scrollLeft=scroll.x;next.scrollTop=scroll.y}
 const aside=document.querySelector('.battle-inspector-body');if(aside&&oldActor===battleToken&&oldPanel===battleInspector)aside.scrollTop=asideScroll;
 battleRestoreForms();
 if(ended)document.querySelectorAll('.battle-inspector-body input,.battle-inspector-body select,.battle-inspector-body button:not([data-battle-select]):not([data-battle-focus])').forEach(node=>node.disabled=true);
};
async function battleSwitchMode(mode){
 if(!masterBattle||battleRequestPending||mode===battleCockpitMode)return;
 if(mode==='edit'){
  const frame=document.querySelector('#battle-play-frame');
  // The child synchronously checks combatBusy before pausing; never unload an action in flight.
  frame?.contentWindow.postMessage({type:'tyranny-master-pause'},location.origin);return;
 }
 battleCaptureForms();battlePlacementArmed=false;battleCockpitMode='play';battleEmbeddedBusy=true;
 const editor=document.querySelector('.master-battle-editor');editor?.classList.add('battle-playing');
 editor?.querySelector('.master-battle-layout')?.setAttribute('hidden','');
 editor?.querySelector('.battle-scene-status')?.setAttribute('hidden','');
 editor?.querySelector('.battle-shortcuts')?.setAttribute('hidden','');
 const modeNode=editor?.querySelector('.battle-mode-switch');if(modeNode)modeNode.outerHTML=battleModeButtons();
 const returnButton=editor?.querySelector('[data-battle-mode="edit"]');if(returnButton)returnButton.disabled=true;
 const wrap=document.createElement('section');wrap.className='battle-play-stage';
 const frame=document.createElement('iframe');frame.id='battle-play-frame';frame.title='Ходы НПС по правилам игроков';frame.referrerPolicy='no-referrer';frame.src=battlePlayUrl(masterBattle.id).replace('#','&embed=1#');wrap.append(frame);editor?.append(wrap);
}
window.addEventListener('message',async event=>{
 const frame=document.querySelector('#battle-play-frame');if(event.source!==frame?.contentWindow||event.origin!==location.origin)return;
 if(event.data?.type==='tyranny-master-state'){
  const state=event.data;if(state.battleId!==masterBattle?.id||state.revision<masterBattle.revision||!Number.isInteger(state.round)||!battleStatusNames[state.status])return;
  const summary=document.querySelector('.battle-editor-heading p');if(summary)summary.textContent=`№${state.battleId} · ${battleStatusNames[state.status]} · раунд ${state.round}`;
  return;
 }
 if(event.data?.type==='tyranny-master-busy'){
  battleEmbeddedBusy=!!event.data.busy;
  const button=document.querySelector('[data-battle-mode="edit"]');if(button){button.disabled=battleEmbeddedBusy;button.title=battleEmbeddedBusy?'Дождитесь завершения действия':''}
  return;
 }
 if(event.data?.type!=='tyranny-master-paused')return;
 if(battleRequestPending)return;
 battleBusy(true);
 // Keep the paused HUD in place until the editor has fetched the latest turn.
 // Otherwise a stale editor briefly exposes the previous actor's HP/initiative.
 try{await loadMasterBattle(masterBattle.id)}finally{battleBusy(false)}
 battleCockpitMode='edit';battleEmbeddedBusy=false;frame.parentElement.remove();
 const editor=document.querySelector('.master-battle-editor');editor?.classList.remove('battle-playing');
 editor?.querySelectorAll('[hidden]').forEach(node=>{if(node.classList.contains('master-battle-layout')||node.classList.contains('battle-scene-status')||node.classList.contains('battle-shortcuts'))node.hidden=false});
 renderMasterBattle();
});
async function battleSelectQuick(id){
 if(!masterBattle.tokens.some(t=>t.id===id))return;
 battlePlacementArmed=false;if(['place_player','add_npc'].includes(battleTool)){battleTool='select';battleMoveMode=false}battleToken=id;battleInspector='token';renderMasterBattle();
 await loadMasterBattle(masterBattle.id);
 if(window.innerWidth<=800)document.querySelector('.master-battle-controls')?.scrollIntoView({block:'start',behavior:'smooth'});
}
// The illustrated palette is the only NPC selector in the cockpit.
filterBattleNpcs=function(){};
document.addEventListener('click',async event=>{
 const target=event.target,button=target.closest('button'),playLink=target.closest('.battle-play-link');
 const stop=()=>{event.preventDefault();event.stopImmediatePropagation()};
 if(button?.dataset.battleOpenPlay&&!battleRequestPending){stop();const id=Number(button.dataset.battleOpenPlay);await loadMasterBattle(id);if(masterBattle?.id===id)await battleSwitchMode('play');return}
 if(button?.dataset.battleParticipants){stop();document.querySelectorAll('[name="battle-participant"]').forEach(input=>input.checked=button.dataset.battleParticipants==='all');battleCountParticipants();return}
 if(masterBattle&&playLink){stop();await battleSwitchMode('play');return}
 if(button?.dataset.battleMode){stop();await battleSwitchMode(button.dataset.battleMode);return}
 if(battleCockpitMode==='play'&&masterBattle){
  if(target.closest('[data-open-battles],[data-campaign],[data-open-npcs],[data-open-catalog],#reload,[data-battle-refresh],[data-battle-operation],[data-battle-delete]')){stop();toast('Вернитесь в редактор перед изменением сцены.');return}
 }
 if(!masterBattle||battleRequestPending||!button||button.disabled||battleCockpitMode!=='edit')return;
 if(button.dataset.battleSelect){stop();await battleSelectQuick(button.dataset.battleSelect);return}
 if(button.hasAttribute('data-battle-current')){stop();if(masterBattle.currentId){await battleSelectQuick(masterBattle.currentId);document.querySelector('[data-battle-focus]')?.click()}return}
 if(button.dataset.battleInspector==='add'){stop();battleInspector='add';if(!['add_npc','place_player'].includes(battleTool))battleTool='add_npc';renderMasterBattle();return}
 if(button.dataset.battleInspector){battlePlacementArmed=false;if(['place_player','add_npc'].includes(battleTool)){battleTool='select';battleMoveMode=false}}
 if(button.dataset.battleNpcChoice){stop();battleNpcChoice=button.dataset.battleNpcChoice;renderMasterBattle();return}
 if(masterBattle.status==='ended')return;
 if(button.hasAttribute('data-battle-arm-placement')){stop();battlePlacementArmed=!battlePlacementArmed;renderMasterBattle();if(battlePlacementArmed&&window.innerWidth<=800)document.querySelector('.master-battle-board')?.scrollIntoView({block:'start',behavior:'smooth'});return}
 if(button.dataset.battleQuickEffect){stop();const effect=button.dataset.battleQuickEffect;await battleEdit({operation:'effect',tokenId:battleToken,effect,name:battleEffectNames[effect],value:Number(button.dataset.value),rounds:1,beneficial:battleEffectDefaults(effect).beneficial});return}
 if(button.dataset.masterBattleCell){
  const [x,y]=button.dataset.masterBattleCell.split(':').map(Number),occupied=masterBattle.tokens.some(t=>t.x===x&&t.y===y&&t.health>0);
  if(!battlePlacementArmed&&battleTool==='select'&&occupied&&!event.shiftKey){stop();await battleSelectQuick(masterBattle.tokens.find(t=>t.x===x&&t.y===y&&t.health>0).id);return}
  if(battlePlacementArmed){
   stop();if(occupied){toast('Эта клетка занята. Выберите свободную.');return}if(!battleChooseCell(x,y))return;
   if(battleTool==='place_player')await battleEdit({operation:'place_player',characterId:Number(battlePlayerChoice),x,y});
   else await battleEdit({operation:'add_npc',npcId:Number(battleNpcChoice),team:battleNewTeam,x,y});
   return;
  }
  if(event.shiftKey&&!occupied&&battleToken){stop();if(battleChooseCell(x,y))await battleEdit({operation:'move',tokenId:battleToken,x,y});return}
 }
},true);
document.addEventListener('input',event=>{
 if(event.target.id==='battle-scene-search'){battleSceneQuery=event.target.value;battleFilterScenes()}
 if(event.target.id==='battle-participant-search')document.querySelectorAll('[data-battle-participant-name]').forEach(row=>row.hidden=!row.dataset.battleParticipantName.includes(event.target.value.toLocaleLowerCase('ru')));
 if(!masterBattle)return;const input=event.target;
 if(input.id==='battle-health-delta')battleDelta=input.value;
 if(['battle-health','battle-health-max'].includes(input.id)){battleFormDrafts.set(`${battleToken}:${input.id}`,input.value);document.querySelector('[data-battle-unsaved]')?.removeAttribute('hidden')}
 if(input.id==='battle-npc-search'){
  const palette=document.querySelector('.battle-npc-palette');if(!palette)return;
  const q=input.value.toLocaleLowerCase('ru');
  palette.innerHTML=(battleIndex?.npcs||[]).filter(n=>n.spec.name.toLocaleLowerCase('ru').includes(q)).map(n=>`<button class="battle-npc-card ${String(n.id)===battleNpcChoice?'selected':''}" data-battle-npc-choice="${n.id}" aria-pressed="${String(n.id)===battleNpcChoice}"><span class="battle-avatar">${battlePicture(n.spec)}</span><span><b>${esc(n.spec.name)}</b><small>${n.spec.healthMax} ХП · ур. ${n.spec.level||1}</small></span></button>`).join('')||'<p class="battle-help">НПС не найдены.</p>';
 }
});
document.addEventListener('change',event=>{
 if(event.target.id==='battle-scene-filter'){battleSceneStatus=event.target.value;battleFilterScenes()}
 if(event.target.name==='battle-participant')battleCountParticipants();
 if(event.target.id==='battle-place-player')battlePlayerChoice=event.target.value;
 if(event.target.id==='battle-place-team')battleNewTeam=event.target.value;
});
document.addEventListener('click',event=>{if(event.target.closest('[data-campaign],[data-open-npcs],[data-open-catalog]'))battleRememberLocation()});
function battleCountParticipants(){const count=document.querySelector('#battle-participant-count');if(count)count.textContent=`Выбрано: ${document.querySelectorAll('[name="battle-participant"]:checked').length}`}
document.addEventListener('dragstart',event=>{
 const row=event.target.closest('[data-battle-order-id]');if(row&&masterBattle?.status!=='ended'&&!battleRequestPending&&battleCockpitMode==='edit')event.dataTransfer.setData('application/x-tyranny-order',row.dataset.battleOrderId);
});
document.addEventListener('dragover',event=>{if(event.target.closest('[data-battle-order-id]'))event.preventDefault()});
document.addEventListener('drop',async event=>{
 const row=event.target.closest('[data-battle-order-id]'),id=event.dataTransfer.getData('application/x-tyranny-order');
 if(!row||!id||!masterBattle||battleRequestPending||battleCockpitMode!=='edit'||masterBattle.status==='ended')return;
 event.preventDefault();const order=masterBattle.initiative.map(i=>i.id),from=order.indexOf(id),to=order.indexOf(row.dataset.battleOrderId);
 if(from<0||to<0||from===to)return;order.splice(from,1);order.splice(to,0,id);await battleEdit({operation:'order',order});
});
document.addEventListener('keydown',event=>{
 if(!masterBattle||battleRequestPending||battleCockpitMode!=='edit'||event.target.matches('input,select,textarea,[contenteditable]')||event.ctrlKey||event.metaKey||event.altKey||event.repeat)return;
 const key=({KeyF:'f',KeyC:'c',KeyV:'v',KeyM:'m'})[event.code]||event.key.toLowerCase(),buttons={f:'[data-battle-focus]',c:'[data-battle-current]','0':'[data-battle-fit]','+':'[data-battle-zoom="8"]','=':'[data-battle-zoom="8"]','-':'[data-battle-zoom="-8"]'};
 if(key==='escape'){event.preventDefault();battlePlacementArmed=false;battlePlacement=null;battleSetTool('select');return}
 if(key==='v'||key==='m'){event.preventDefault();if(masterBattle.status!=='ended')battleSetTool(key==='m'?'move':'select');return}
 if(key==='/'){event.preventDefault();battleInspector='list';renderMasterBattle();document.querySelector('#battle-token-search')?.focus();return}
 if(buttons[key]){event.preventDefault();document.querySelector(buttons[key])?.click()}
});
