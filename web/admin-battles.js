/* Scene edits and ordinary NPC turns are deliberately separate entry points. */
let battleIndex=null,masterBattle=null,battleToken='',battleMoveMode=false,battleZoom=48,battleRequestPending=false;
let battleInspector='token',battleTool='select',battleTokenQuery='',battleTokenKind='all',battleNpcQuery='',battlePlacement=null,battleLoadTicket=0;
const battleEffectNames={stun:'Оглушение',paralyze:'Паралич',petrif:'Окаменение',freeze:'Заморозка',sleep:'Сон',root:'Обездвиживание',prone:'Сбит с ног',silence:'Немота',blind:'Слепота',fear:'Страх',fatigue:'Усталость',poison:'Яд',burn:'Горение',bleed:'Кровотечение',heal:'Лечение за раунд',shield:'Щит',guard:'Защиты ×',accuracy:'Точность +',armor:'Броня +',movement:'Передвижение ×',damage:'Урон ×',incoming:'Получаемый урон ×',Сила:'Сила +',Искусность:'Искусность +',Быстрота:'Быстрота +',Живучесть:'Живучесть +',Смекалка:'Смекалка +',Стойкость:'Стойкость +',Парирование:'Парирование +',Уклонение:'Уклонение +',Выносливость:'Выносливость +',Воля:'Воля +',Магия:'Магия +'};
const battleStatusNames={lobby:'Расстановка',active:'Бой идёт',ended:'Завершён'};
const battleNumber=id=>{const value=document.querySelector(id)?.value;return value===undefined||value.trim()===''?NaN:Number(value)};
function battlePlayUrl(id){return `master-combat.html?api=${encodeURIComponent(api)}&battle=${id}#token=${encodeURIComponent(token)}`}
function battlePicture(t){const picture=t.portrait||t.portraitUrl;return picture?`<img src="${esc(picture)}" alt="" loading="lazy">`:`<b aria-hidden="true">${esc((t.name||'?')[0])}</b>`}
function battleSetTool(tool){battleTool=tool;battleMoveMode=tool==='move';if(['place_player','add_npc'].includes(tool))battleInspector='add';renderMasterBattle()}
function battleAdopt(b){
 if(masterBattle?.id===b.id&&b.revision<masterBattle.revision)return false;
 if(masterBattle?.id!==b.id){battlePlacement=null;battleTool='select';battleMoveMode=false;battleInspector='token';battleTokenQuery='';battleTokenKind='all'}
 masterBattle=b;return true;
}
function battleBusy(busy){
 battleRequestPending=busy;
 document.querySelector('.master-battle-editor')?.setAttribute('aria-busy',String(busy));
 document.querySelectorAll('.master-battle-editor button,.master-battle-editor input,.master-battle-editor select').forEach(node=>{
  if(busy){node.dataset.battleWasDisabled=String(node.disabled);node.disabled=true}
  else if(node.dataset.battleWasDisabled!==undefined){node.disabled=node.dataset.battleWasDisabled==='true';delete node.dataset.battleWasDisabled}
 });
}
async function deleteMasterBattle(id){
 if(battleRequestPending)return;
 const battle=masterBattle?.id===id?masterBattle:battleIndex?.battles.find(b=>b.id===id);if(!battle)return;
 const confirmed=await askMasterDeletion({title:`Удалить бой №${id}?`,name:battle.name,warning:'Удаляется только бой. Персонажи, их инвентарь и деньги, карта и архив НПС сохранятся.'});if(!confirmed)return;
 battleBusy(true);
 try{
  const result=await request(`${base()}/battles/${id}`,{method:'DELETE',body:JSON.stringify({confirmName:battle.name,revision:battle.revision})});
  masterBattle=null;await openMasterBattles();toast(result.message);
 }catch(error){toast(error.message);if(masterBattle?.id===id)await loadMasterBattle(id);else await openMasterBattles()}finally{battleBusy(false)}
}
document.querySelector('.admin-top>div')?.insertAdjacentHTML('afterbegin','<button data-open-battles>БОИ</button>');
async function openMasterBattles(){
 const ticket=++battleLoadTicket;
 try{const index=await request(`${base()}/battles`);if(ticket!==battleLoadTicket)return;battleIndex=index;masterBattle=null;battleWorkspace()}catch(error){if(ticket===battleLoadTicket)toast(error.message)}
}
function battleWorkspace(){
 const maps=battleIndex.maps,characters=roster||[];
 campaignWorkspace(`<div class="battle-editor-index"><header class="admin-heading"><small>МАСТЕР · БОИ</small><h1>Боевые сцены</h1><p>Подготовьте поле в редакторе, затем переключитесь на ходы НПС по инициативе.</p></header><section class="admin-box"><h2>Создать бой</h2><label class="field">Карта<select id="battle-map-choice">${maps.map(m=>`<option value="${m.id}">${esc(m.name)}</option>`).join('')}</select></label>${maps.length?'':'<p>Сначала сохраните карту в редакторе карт.</p>'}<div class="battle-participant-choices">${characters.map(c=>`<label><input type="checkbox" name="battle-participant" value="${c.id}"> ${esc(c.name)}</label>`).join('')}</div><button class="action" data-battle-create ${maps.length&&characters.length?'':'disabled'}>СОЗДАТЬ БОЙ</button><p class="battle-help">Приглашённые игроки вступают через /начать-бой.</p></section><section class="admin-box"><h2>Сохранённые бои</h2><div class="battle-scenes">${battleIndex.battles.map(b=>`<article class="battle-scene-row"><button class="dark-button" data-open-battle="${b.id}"><b>${esc(b.name)}</b><span>№${b.id} · ${battleStatusNames[b.status]} · раунд ${b.round}</span></button><a class="dark-button battle-play-link" href="${esc(battlePlayUrl(b.id))}">ХОДЫ НПС</a><button class="dark-button danger" data-battle-delete="${b.id}" aria-label="Удалить бой ${esc(b.name)}">×</button></article>`).join('')||'<p>Сохранённых боёв пока нет.</p>'}</div></section></div>`);
}
async function loadMasterBattle(id){
 const ticket=++battleLoadTicket;
 try{const result=await request(`${base()}/battles/${id}?actorId=${encodeURIComponent(battleToken)}`);if(ticket!==battleLoadTicket)return;if(battleAdopt(result.battle))renderMasterBattle()}catch(error){if(ticket===battleLoadTicket)toast(error.message)}
}
async function battleEdit(payload){
 if(battleRequestPending||!masterBattle)return;
 const id=masterBattle.id,selected=battleToken;let oldTokens=new Set(masterBattle.tokens.map(t=>t.id));++battleLoadTicket;battleBusy(true);
 try{
  const path=`${base()}/battles/${id}?actorId=${encodeURIComponent(selected)}`;
  const send=()=>request(path,{method:'POST',body:JSON.stringify({...payload,revision:masterBattle.revision})});
  let result;
  try{result=await send()}catch(error){
   // A revision conflict is rejected before mutation. Never retry a combat
   // action or an ambiguous network failure (especially NPC creation).
   if(payload.operation==='act'||!error.message.startsWith('Бой изменился.'))throw error;
   battleAdopt((await request(path)).battle);oldTokens=new Set(masterBattle.tokens.map(t=>t.id));result=await send();
  }
  if(masterBattle?.id!==id)return;
  battleAdopt(result.battle);
  if(payload.operation==='add_npc')battleToken=masterBattle.tokens.find(t=>!oldTokens.has(t.id))?.id||battleToken;
  if(payload.operation==='place_player')battleToken=`pc_${payload.characterId}`;
  renderMasterBattle();toast(result.message);
 }catch(error){toast(error.message);if(masterBattle?.id===id)await loadMasterBattle(id)}finally{battleBusy(false)}
}
function battleRosterRows(){
 const tokens=masterBattle.tokens.filter(t=>(battleTokenKind==='all'||t.kind===battleTokenKind)&&t.name.toLocaleLowerCase('ru').includes(battleTokenQuery.toLocaleLowerCase('ru')));
 return tokens.map(t=>`<button class="battle-token-row ${t.id===battleToken?'selected':''} ${t.id===masterBattle.currentId?'current':''}" data-battle-select="${esc(t.id)}" aria-pressed="${t.id===battleToken}"><span class="battle-avatar ${t.team==='enemy'?'enemy':'party'}">${battlePicture(t)}</span><span><b>${esc(t.name)}</b><small>${t.kind==='player'?'Игрок':'НПС'} · ${t.team==='enemy'?'Противник':'Союзник'}${t.id===masterBattle.currentId?' · Ходит':''}</small></span><span class="battle-token-health ${t.health<=0?'defeated':''}">${t.health}/${t.healthMax}</span></button>`).join('')||'<p class="battle-help">Нет подходящих токенов.</p>';
}
function battleTokenInspector(selected){
 if(!selected)return '<p class="battle-help">Выберите токен на карте или в списке.</p>';
 const training=masterBattle.training,turn=training?.viewerId===selected.id?training.turn:null;
 const actions=training?.viewerId===selected.id?training.actions.filter(a=>a.kind==='ability'):[];
 return `<div class="battle-selected-heading"><span class="battle-avatar ${selected.team==='enemy'?'enemy':'party'}">${battlePicture(selected)}</span><div><h2>${esc(selected.name)}</h2><small>${selected.kind==='player'?'Персонаж игрока':'НПС'} · ${selected.x}, ${selected.y}</small></div></div>${turn?`<div class="battle-resource-summary"><span>${turn.actionAvailable?'Действие готово':'Действие потрачено'}</span><span>Движение: ${turn.movementRemaining??0} клеток</span></div>`:''}<div class="fields"><label class="field">ХП<input id="battle-health" type="number" min="0" max="100000" value="${selected.health}"></label><label class="field">Максимум ХП<input id="battle-health-max" type="number" min="1" max="100000" value="${selected.healthMax}"></label></div><button class="dark-button battle-full" data-battle-hp>СОХРАНИТЬ ХП</button><div class="battle-hp-adjust"><button class="dark-button" data-battle-damage aria-label="Нанести указанное количество урона">− ХП</button><label class="field">Количество<input id="battle-health-delta" type="number" min="1" max="100000" value="5"></label><button class="dark-button" data-battle-heal aria-label="Восстановить указанное количество здоровья">+ ХП</button></div><label class="field">Сторона<select id="battle-token-team"><option value="party" ${selected.team!=='enemy'?'selected':''}>Союзник</option><option value="enemy" ${selected.team==='enemy'?'selected':''}>Противник</option></select></label><div class="fields battle-coordinate-fields"><label class="field">Клетка X<input id="battle-token-x" type="number" min="0" max="${masterBattle.map.width-1}" value="${selected.x}"></label><label class="field">Клетка Y<input id="battle-token-y" type="number" min="0" max="${masterBattle.map.height-1}" value="${selected.y}"></label></div><button class="dark-button battle-full" data-battle-move>ПЕРЕМЕСТИТЬ БЕЗ ЗАТРАТ</button><p class="battle-help">Это правка мастера. Обычное движение НПС доступно в режиме «Ходы по инициативе».</p>${actions.length?`<details class="battle-fold"><summary>Назначенные способности · ${actions.length}</summary><ul>${actions.map(a=>`<li>${esc(a.name)}${a.disabledReason?` — ${esc(a.disabledReason)}`:''}</li>`).join('')}</ul></details>`:''}<details class="battle-fold"><summary>Ручные правки хода</summary><p class="battle-help">Не изменяются при переключении режимов. Используйте только для исправления сцены.</p><button class="dark-button" data-battle-operation="turn" ${selected.health>0&&masterBattle.status==='active'?'':'disabled'}>ПЕРЕДАТЬ ХОД ЭТОМУ ТОКЕНУ</button><button class="dark-button" data-battle-operation="refresh_turn" ${masterBattle.status==='active'?'':'disabled'}>ВЕРНУТЬ ДЕЙСТВИЕ И ДВИЖЕНИЕ</button></details><button class="dark-button danger battle-full" data-battle-operation="remove_token">УБРАТЬ ИЗ БОЯ</button>`;
}
function battleEffectInspector(selected){
 if(!selected)return '<p class="battle-help">Сначала выберите токен.</p>';
 const conditions=Object.entries(masterBattle.conditions[battleToken]||{});
 return `<h2>Эффекты · ${esc(selected.name)}</h2><div class="battle-active-effects">${conditions.map(([key,e])=>`<div class="battle-effect"><span><b>${esc(e.name||key)}</b><small>${e.shieldRemaining!==undefined?`${e.shieldRemaining} поглощения · `:e.value!==undefined?`Сила: ${e.value} · `:''}${Math.max(0,e.until-masterBattle.round+1)} раунд.</small></span><button data-battle-remove-effect="${esc(key)}" aria-label="Снять ${esc(e.name||key)}">×</button></div>`).join('')||'<p class="battle-help">Активных эффектов нет.</p>'}</div><div class="battle-effect-presets">${[['stun','Оглушить',0],['burn','Горение',5],['shield','Щит',20],['guard','Защиты ×1,2',1.2]].map(([key,title,value])=>`<button class="dark-button" data-battle-effect-preset="${key}" data-value="${value}">${title}</button>`).join('')}</div><label class="field">Добавить эффект<select id="battle-effect">${Object.entries(battleEffectNames).map(([id,name])=>`<option value="${id}">${esc(name)}</option>`).join('')}</select></label><div class="fields"><label class="field">Сила / множитель<input id="battle-effect-value" type="number" step="any" value="0"></label><label class="field">Длительность, раунды<input id="battle-effect-rounds" type="number" min="1" max="1000" value="1"></label></div><label class="battle-effect-classification"><input id="battle-effect-beneficial" type="checkbox"> Положительный эффект</label><p id="battle-effect-hint" class="battle-help">Оглушение запрещает действия. 1 раунд = 10 секунд.</p><button class="action battle-full" data-battle-add-effect>ПРИМЕНИТЬ К ТОКЕНУ</button>`;
}
function battleInitiativeInspector(){
 const b=masterBattle;
 return `<h2>Очередь · раунд ${b.round}</h2><p class="battle-help">Стрелки меняют порядок, не сбрасывая текущий ход и потраченные действия.</p>${b.initiative.map((i,n)=>{const t=b.tokens.find(t=>t.id===i.id);return `<div class="battle-order-row ${i.id===b.currentId?'current':''}"><button data-battle-select="${esc(i.id)}"><span>${n+1}. ${esc(i.name)}</span><small>${t?.health<=0?'Выведен из боя':i.id===b.currentId?'Сейчас ходит':`Инициатива ${i.total}`}</small></button><button data-battle-reorder="${n}:up" ${n===0?'disabled':''} aria-label="Поднять ${esc(i.name)} в очереди">↑</button><button data-battle-reorder="${n}:down" ${n===b.initiative.length-1?'disabled':''} aria-label="Опустить ${esc(i.name)} в очереди">↓</button></div>`}).join('')||'<p>Очередь появится после запуска боя.</p>'}${b.status==='active'?'<button class="dark-button battle-full" data-battle-next>ПРОПУСТИТЬ ТЕКУЩИЙ ХОД</button>':''}<a class="action battle-full battle-play-link" href="${esc(battlePlayUrl(b.id))}">ХОДЫ ПО ИНИЦИАТИВЕ →</a>`;
}
function battleAddInspector(){
 const b=masterBattle,npcs=battleIndex?.npcs||[],players=Object.entries(b.participants);
 return `<h2>Разместить токен</h2><p class="battle-help">Выберите игрока или НПС, затем укажите свободную клетку на поле. Можно добавлять несколько экземпляров одного НПС.</p><div class="battle-tools"><button class="dark-button ${battleTool==='place_player'?'active':''}" data-battle-tool="place_player">ИГРОК</button><button class="dark-button ${battleTool==='add_npc'?'active':''}" data-battle-tool="add_npc">НПС</button></div><label class="field">Приглашённый игрок<select id="battle-place-player">${players.map(([id,c])=>`<option value="${id}">${esc(c.name)} · ${c.joined?'вступил':'ожидание'}</option>`).join('')}</select></label><button class="dark-button battle-full" data-battle-place-player ${players.length?'':'disabled'}>ПОСТАВИТЬ ИГРОКА</button><label class="field">Поиск в архиве НПС<input id="battle-npc-search" value="${esc(battleNpcQuery)}" placeholder="Имя НПС" autocomplete="off"></label><label class="field">НПС из архива<select id="battle-place-npc">${npcs.map(n=>`<option value="${n.id}" ${n.spec.name.toLocaleLowerCase('ru').includes(battleNpcQuery.toLocaleLowerCase('ru'))?'':'hidden'}>${esc(n.spec.name)}</option>`).join('')}</select></label><label class="field">Сторона нового НПС<select id="battle-place-team"><option value="enemy">Противник</option><option value="party">Союзник</option></select></label><button class="action battle-full" data-battle-add-npc ${npcs.length?'':'disabled'}>ДОБАВИТЬ НПС</button>${npcs.length?'':'<p class="battle-help">Сначала создайте НПС в архиве мастерской.</p>'}<div class="fields"><label class="field">Клетка X<input id="battle-place-x" type="number" min="0" max="${b.map.width-1}" value="${battlePlacement?.x??''}"></label><label class="field">Клетка Y<input id="battle-place-y" type="number" min="0" max="${b.map.height-1}" value="${battlePlacement?.y??''}"></label></div><p class="battle-help" id="battle-placement-hint">${battlePlacement?`Выбрана клетка ${battlePlacement.x}, ${battlePlacement.y}.`:'Нажмите свободную клетку на карте.'}</p><details class="battle-fold"><summary>Приглашённые игроки</summary>${players.map(([id,c])=>`<p>${esc(c.name)} · ${c.joined?'Вступил':'Ожидается /начать-бой'} · ${b.tokens.some(t=>t.id===`pc_${id}`)?'Размещён':'Не размещён'}</p>`).join('')}</details>`;
}
function renderMasterBattle(){
 if(!masterBattle)return;
 const viewport=document.querySelector('.master-battle-viewport'),scroll=viewport?{x:viewport.scrollLeft,y:viewport.scrollTop}:null;
 const asideScroll=document.querySelector('.battle-inspector-body')?.scrollTop||0;
 const b=masterBattle,m=b.map,tokens=b.tokens,selected=tokens.find(t=>t.id===battleToken)||tokens.find(t=>t.id===b.currentId)||tokens[0];battleToken=selected?.id||'';
 const current=tokens.find(t=>t.id===b.currentId),ended=b.status==='ended';
 const has=(key,x,y)=>(m[key]||[]).some(p=>p.x===x&&p.y===y);
 const cells=Array.from({length:m.width*m.height},(_,i)=>{const x=i%m.width,y=Math.floor(i/m.width),stack=tokens.filter(t=>t.x===x&&t.y===y),t=stack.find(t=>t.id===battleToken)||stack.find(t=>t.health>0)||stack[0],blocked=has('blocked',x,y);
  return `<button class="master-battle-cell ${blocked?'blocked':''} ${has('sightBlocked',x,y)?'sight-blocked':''} ${has('cover',x,y)?'cover':''} ${t?.id===battleToken?'selected':''} ${battlePlacement?.x===x&&battlePlacement?.y===y?'placement':''}" data-master-battle-cell="${x}:${y}" aria-label="Клетка ${x}, ${y}${t?` · ${esc(t.name)} · ${t.health}/${t.healthMax}`:''}" title="${x}, ${y}${t?` · ${esc(t.name)}`:''}" ${blocked?'disabled':''}>${t?`<span class="master-battle-token ${t.team==='enemy'?'enemy':'party'} ${t.health<=0?'defeated':''} ${t.id===b.currentId?'current':''}" draggable="${!ended}" data-battle-token="${esc(t.id)}">${battlePicture(t)}<small>${t.health}/${t.healthMax}</small>${stack.length>1?`<em class="battle-stack-count">${stack.length}</em>`:''}</span>`:''}</button>`;
 }).join('');
 const tools=[['select','Выбрать'],['move','Передвинуть'],['place_player','Поставить игрока'],['add_npc','Добавить НПС']];
 const inspector={token:()=>battleTokenInspector(selected),effects:()=>battleEffectInspector(selected),initiative:battleInitiativeInspector,add:battleAddInspector};
 campaignWorkspace(`<div class="master-battle-editor"><header class="battle-editor-heading"><div><small>МАСТЕР · РЕДАКТОР БОЯ</small><h1>${esc(b.name)}</h1><p>№${b.id} · ${battleStatusNames[b.status]} · раунд ${b.round}</p></div><nav class="battle-mode-switch" aria-label="Режим управления боем"><span aria-current="page">РЕДАКТОР</span><a class="battle-play-link" href="${esc(battlePlayUrl(b.id))}">ХОДЫ ПО ИНИЦИАТИВЕ →</a></nav><div class="battle-toolbar"><button class="dark-button" data-open-battles>ВСЕ БОИ</button><button class="dark-button" data-battle-refresh>ОБНОВИТЬ</button>${b.status==='lobby'?'<button class="action" data-battle-operation="start">НАЧАТЬ БОЙ</button>':''}<details class="battle-scene-menu"><summary>⋯</summary>${b.status==='active'?'<button class="dark-button" data-battle-operation="finish">ЗАВЕРШИТЬ БОЙ</button>':''}<button class="dark-button danger" data-battle-delete="${b.id}">УДАЛИТЬ БОЙ</button></details></div></header><div class="battle-scene-status"><span>${current?`${current.kind==='npc'?'Ход НПС':'Ход игрока'}: ${esc(current.name)}`:b.status==='lobby'?'Разместите токены и дождитесь игроков.':'Нет активного хода.'}</span><label>Время сцены <select id="battle-time-of-day" ${ended?'disabled':''}><option value="day" ${m.timeOfDay!=='night'?'selected':''}>День</option><option value="night" ${m.timeOfDay==='night'?'selected':''}>Ночь</option></select></label><span class="battle-editor-sync" role="status">СОХРАНЕНО НА СЕРВЕРЕ</span></div><div class="master-battle-layout"><section class="master-battle-board"><div class="battle-board-toolbar"><nav class="battle-tools" aria-label="Инструменты редактора">${tools.map(([key,title])=>`<button class="dark-button ${battleTool===key?'active':''}" data-battle-tool="${key}" aria-pressed="${battleTool===key}" ${ended&&key!=='select'?'disabled':''}>${title}</button>`).join('')}</nav><div class="battle-zoom"><button class="dark-button" data-battle-zoom="-8" aria-label="Отдалить">−</button><output>${Math.round(battleZoom/48*100)}%</output><button class="dark-button" data-battle-zoom="8" aria-label="Приблизить">+</button><button class="dark-button" data-battle-fit>ВМЕСТИТЬ</button><button class="dark-button" data-battle-focus ${selected?'':'disabled'}>К ТОКЕНУ</button></div></div><p class="battle-tool-hint">${{select:'Выберите токен на поле или в списке справа.',move:'Выберите токен, затем нажмите свободную клетку. Это перемещение мастера без затрат.',place_player:'Нажмите свободную клетку, выберите игрока справа и подтвердите размещение.',add_npc:'Нажмите свободную клетку, выберите НПС справа и подтвердите добавление.'}[battleTool]}</p><div class="master-battle-viewport"><div class="master-battle-grid" style="--battle-size:${battleZoom}px;grid-template-columns:repeat(${m.width},var(--battle-size));width:${m.width*battleZoom}px;height:${m.height*battleZoom}px;background-size:${(m.imageScale||1)*100}% auto;background-position:calc(50% + ${m.offsetX||0}px) calc(50% + ${m.offsetY||0}px)">${cells}</div></div><details class="battle-editor-journal"><summary><span>${esc(b.log[0]||'Нет действий.')}</span> ЖУРНАЛ ▾</summary>${b.log.map(line=>`<p>${esc(line)}</p>`).join('')}</details></section><aside class="master-battle-controls"><section class="battle-token-list"><div class="battle-token-list-heading"><h2>Токены <span>${tokens.length}</span></h2><input id="battle-token-search" placeholder="Найти токен" aria-label="Поиск токена" value="${esc(battleTokenQuery)}" autocomplete="off"><select id="battle-token-filter" aria-label="Тип токена">${[['all','Все'],['player','Игроки'],['npc','НПС']].map(([key,label])=>`<option value="${key}" ${battleTokenKind===key?'selected':''}>${label}</option>`).join('')}</select></div><div id="battle-token-rows">${battleRosterRows()}</div></section><nav class="battle-inspector-tabs" aria-label="Панель редактора">${[['token','Токен'],['effects','Эффекты'],['initiative','Очередь'],['add','Добавить']].map(([key,label])=>`<button data-battle-inspector="${key}" class="${battleInspector===key?'active':''}" aria-pressed="${battleInspector===key}">${label}</button>`).join('')}</nav><section class="battle-inspector-body">${inspector[battleInspector]()}</section></aside></div></div>`);
 const grid=document.querySelector('.master-battle-grid');if(grid)grid.style.backgroundImage=m.image?`url("${m.image.replace(/["\\\n\r]/g,'')}")`:'';
 const nextViewport=document.querySelector('.master-battle-viewport');if(scroll&&nextViewport){nextViewport.scrollLeft=scroll.x;nextViewport.scrollTop=scroll.y}
 const nextAside=document.querySelector('.battle-inspector-body');if(nextAside)nextAside.scrollTop=asideScroll;
 if(ended)document.querySelectorAll('.battle-inspector-body input,.battle-inspector-body select,.battle-inspector-body button:not([data-battle-select])').forEach(node=>node.disabled=true);
 if(battleInspector==='add')filterBattleNpcs();
}
function filterBattleNpcs(){
 const selector=document.querySelector('#battle-place-npc');if(!selector)return;
 for(const option of selector.options)option.hidden=!option.textContent.toLocaleLowerCase('ru').includes(battleNpcQuery.toLocaleLowerCase('ru'));
 if(selector.selectedOptions[0]?.hidden)selector.value=Array.from(selector.options).find(o=>!o.hidden)?.value||'';
}
function battleChooseCell(x,y){
 const m=masterBattle.map;
 if(!Number.isInteger(x)||!Number.isInteger(y)||x<0||y<0||x>=m.width||y>=m.height||(m.blocked||[]).some(p=>p.x===x&&p.y===y)){toast('Выберите проходимую клетку внутри карты.');return false}
 battlePlacement={x,y};
 document.querySelectorAll('.master-battle-cell.placement').forEach(node=>node.classList.remove('placement'));
 document.querySelector(`[data-master-battle-cell="${x}:${y}"]`)?.classList.add('placement');
 for(const key of ['x','y']){const node=document.querySelector(`#battle-place-${key}`);if(node)node.value=battlePlacement[key]}
 const hint=document.querySelector('#battle-placement-hint');if(hint)hint.textContent=`Выбрана клетка ${x}, ${y}.`;return true;
}
function battleZoomTo(size){
 const viewport=document.querySelector('.master-battle-viewport');if(!viewport)return;
 const center={x:(viewport.scrollLeft+viewport.clientWidth/2)/battleZoom,y:(viewport.scrollTop+viewport.clientHeight/2)/battleZoom};
 battleZoom=Math.max(16,Math.min(112,size));renderMasterBattle();
 const next=document.querySelector('.master-battle-viewport');next.scrollLeft=center.x*battleZoom-next.clientWidth/2;next.scrollTop=center.y*battleZoom-next.clientHeight/2;
}
function battleEffectDefaults(kind){
 const multiplier=['guard','movement','damage','incoming'].includes(kind),control=['stun','paralyze','petrif','freeze','sleep','root','prone','silence','blind','fear','fatigue'].includes(kind);
 return {value:multiplier?1.2:control?0:kind==='shield'?20:5,beneficial:!control&&!['poison','burn','bleed','incoming'].includes(kind),hint:multiplier?'Множитель: 1 = без изменений, 1,2 = +20%.':control?'Воздействие действует указанное число раундов; сила не требуется.':'Значение добавляется к показателю; периодические эффекты срабатывают раз за раунд.'};
}
function battleSetEffect(kind,value){
 const defaults=battleEffectDefaults(kind);$('#battle-effect').value=kind;$('#battle-effect-value').value=value??defaults.value;$('#battle-effect-beneficial').checked=defaults.beneficial;$('#battle-effect-hint').textContent=defaults.hint+' 1 раунд = 10 секунд.';
}
async function battleApplyHealthDelta(sign){
 const selected=masterBattle.tokens.find(t=>t.id===battleToken),amount=battleNumber('#battle-health-delta');
 if(!selected||!Number.isInteger(amount)||amount<1||amount>100000){toast('Укажите целое количество ХП от 1 до 100000.');return}
 await battleEdit({operation:'health',tokenId:battleToken,delta:sign*amount});
}
let battleReturnLoaded=false;
document.addEventListener('admin-ready',async()=>{
 const id=Number(params.get('battle'));if(battleReturnLoaded||!Number.isInteger(id)||id<1)return;
 battleReturnLoaded=true;battleToken=params.get('actor')||'';
 try{battleIndex=await request(`${base()}/battles`);await loadMasterBattle(id)}catch(error){toast(error.message)}
});
document.addEventListener('click',async event=>{
 if(event.target.closest('.battle-play-link')&&battleRequestPending){event.preventDefault();toast('Дождитесь сохранения правки.');return}
 const button=event.target.closest('button');if(!button||button.disabled||battleRequestPending)return;
 if(button.hasAttribute('data-open-battles')){await openMasterBattles();return}
 if(button.dataset.openBattle){await loadMasterBattle(Number(button.dataset.openBattle));return}
 if(button.dataset.battleDelete){await deleteMasterBattle(Number(button.dataset.battleDelete));return}
 if(button.hasAttribute('data-battle-create')){
  battleBusy(true);try{const participants=[...document.querySelectorAll('[name="battle-participant"]:checked')].map(n=>Number(n.value));if(!participants.length)throw Error('Выберите хотя бы одного игрока.');battleAdopt((await request(`${base()}/battles`,{method:'POST',body:JSON.stringify({mapId:battleNumber('#battle-map-choice'),participants})})).battle);renderMasterBattle()}catch(error){toast(error.message)}finally{battleBusy(false)}return;
 }
 if(!masterBattle)return;
 if(button.hasAttribute('data-battle-refresh')){await loadMasterBattle(masterBattle.id);return}
 if(button.dataset.battleSelect){battleToken=button.dataset.battleSelect;battleInspector='token';await loadMasterBattle(masterBattle.id);return}
 if(button.dataset.battleInspector){battleInspector=button.dataset.battleInspector;renderMasterBattle();return}
 if(button.dataset.battleZoom){battleZoomTo(battleZoom+Number(button.dataset.battleZoom));return}
 if(button.hasAttribute('data-battle-fit')){const viewport=document.querySelector('.master-battle-viewport');battleZoomTo(Math.floor(Math.min(viewport.clientWidth/masterBattle.map.width,viewport.clientHeight/masterBattle.map.height)));return}
 if(button.hasAttribute('data-battle-focus')){const selected=masterBattle.tokens.find(t=>t.id===battleToken),viewport=document.querySelector('.master-battle-viewport');if(selected){viewport.scrollLeft=(selected.x+.5)*battleZoom-viewport.clientWidth/2;viewport.scrollTop=(selected.y+.5)*battleZoom-viewport.clientHeight/2}return}
 if(button.dataset.masterBattleCell&&battleTool==='select'){const [x,y]=button.dataset.masterBattleCell.split(':').map(Number),t=masterBattle.tokens.find(t=>t.x===x&&t.y===y&&t.health>0)||masterBattle.tokens.find(t=>t.x===x&&t.y===y);if(t){battleToken=t.id;battleInspector='token';await loadMasterBattle(masterBattle.id)}return}
 if(masterBattle.status==='ended')return;
 if(button.dataset.battleTool){battleSetTool(button.dataset.battleTool);return}
 if(button.dataset.masterBattleCell){
  const [x,y]=button.dataset.masterBattleCell.split(':').map(Number),t=masterBattle.tokens.find(t=>t.x===x&&t.y===y&&t.health>0)||masterBattle.tokens.find(t=>t.x===x&&t.y===y);
  if(t){battleToken=t.id;if(!['place_player','add_npc'].includes(battleTool))battleInspector='token';await loadMasterBattle(masterBattle.id)}
  else if(battleMoveMode&&battleToken)await battleEdit({operation:'move',tokenId:battleToken,x,y});
  else battleChooseCell(x,y);return;
 }
 if(button.hasAttribute('data-battle-place-player')||button.hasAttribute('data-battle-add-npc')){
  const x=battleNumber('#battle-place-x'),y=battleNumber('#battle-place-y');if(!battleChooseCell(x,y))return;
  if(button.hasAttribute('data-battle-place-player'))await battleEdit({operation:'place_player',characterId:battleNumber('#battle-place-player'),x,y});
  else {const npcId=battleNumber('#battle-place-npc');if(!Number.isInteger(npcId)||npcId<1){toast('Выберите НПС из архива.');return}await battleEdit({operation:'add_npc',npcId,team:$('#battle-place-team').value,x,y})}return;
 }
 if(button.dataset.battleOperation){
  const prompts={finish:'Завершить бой для всех участников?',remove_token:'Убрать выбранный токен из этого боя? Персонаж или шаблон НПС останется в архиве.',turn:'Вручную передать ход выбранному токену? Действия и движение не сбрасываются.',refresh_turn:'Вернуть действие и движение выбранному токену? Это мастерская правка, а не обычный ход.'};
  if(prompts[button.dataset.battleOperation]&&!confirm(prompts[button.dataset.battleOperation]))return;
  await battleEdit({operation:button.dataset.battleOperation,tokenId:battleToken});return;
 }
 if(button.hasAttribute('data-battle-next')){if(confirm('Пропустить текущий ход без действий?'))await battleEdit({operation:'act',actorId:masterBattle.currentId,kind:'end_turn'});return}
 if(button.dataset.battleReorder){const [n,way]=button.dataset.battleReorder.split(':'),order=masterBattle.initiative.map(i=>i.id),i=Number(n),j=i+(way==='up'?-1:1);if(j<0||j>=order.length)return;[order[i],order[j]]=[order[j],order[i]];await battleEdit({operation:'order',order});return}
 if(button.hasAttribute('data-battle-hp')){const health=battleNumber('#battle-health'),healthMax=battleNumber('#battle-health-max');if(!Number.isInteger(health)||!Number.isInteger(healthMax)||health<0||health>healthMax||healthMax<1||healthMax>100000){toast('ХП: целое число от 0 до максимума; максимум — от 1 до 100000.');return}await battleEdit({operation:'health',tokenId:battleToken,health,healthMax});return}
 if(button.hasAttribute('data-battle-heal')||button.hasAttribute('data-battle-damage')){await battleApplyHealthDelta(button.hasAttribute('data-battle-damage')?-1:1);return}
 if(button.hasAttribute('data-battle-move')){const x=battleNumber('#battle-token-x'),y=battleNumber('#battle-token-y');if(battleChooseCell(x,y))await battleEdit({operation:'move',tokenId:battleToken,x,y});return}
 if(button.dataset.battleEffectPreset){battleSetEffect(button.dataset.battleEffectPreset,Number(button.dataset.value));return}
 if(button.hasAttribute('data-battle-add-effect')){const effect=$('#battle-effect').value;await battleEdit({operation:'effect',tokenId:battleToken,effect,name:battleEffectNames[effect],value:battleNumber('#battle-effect-value'),rounds:battleNumber('#battle-effect-rounds'),beneficial:$('#battle-effect-beneficial').checked});return}
 if(button.dataset.battleRemoveEffect)await battleEdit({operation:'remove_effect',tokenId:battleToken,effectId:button.dataset.battleRemoveEffect});
});
document.addEventListener('change',async event=>{
 if(!masterBattle||battleRequestPending)return;
 const input=event.target;
 if(input.id==='battle-token-filter'){battleTokenKind=input.value;$('#battle-token-rows').innerHTML=battleRosterRows()}
 if(masterBattle.status==='ended')return;
 if(input.id==='battle-time-of-day')await battleEdit({operation:'time_of_day',timeOfDay:input.value});
 if(input.id==='battle-token-team')await battleEdit({operation:'team',tokenId:battleToken,team:input.value});
 if(input.id==='battle-effect')battleSetEffect(input.value);
 if(['battle-place-x','battle-place-y'].includes(input.id)){const x=battleNumber('#battle-place-x'),y=battleNumber('#battle-place-y');if(Number.isInteger(x)&&Number.isInteger(y))battleChooseCell(x,y)}
});
document.addEventListener('input',event=>{
 if(!masterBattle)return;
 if(event.target.id==='battle-token-search'){battleTokenQuery=event.target.value;$('#battle-token-rows').innerHTML=battleRosterRows()}
 if(event.target.id==='battle-npc-search'){battleNpcQuery=event.target.value;filterBattleNpcs()}
});
document.addEventListener('click',event=>{
 if(!event.target.closest('[data-campaign],[data-open-npcs],[data-open-catalog],#reload'))return;
 if(battleRequestPending){event.preventDefault();event.stopImmediatePropagation();toast('Дождитесь сохранения правки.');return}
 ++battleLoadTicket;masterBattle=null;
},true);
document.addEventListener('dragstart',event=>{const node=event.target.closest('[data-battle-token]');if(node&&masterBattle?.status!=='ended'&&!battleRequestPending)event.dataTransfer.setData('application/x-tyranny-token',node.dataset.battleToken)});
document.addEventListener('dragover',event=>{if(event.target.closest('[data-master-battle-cell]'))event.preventDefault()});
document.addEventListener('drop',async event=>{
 const cell=event.target.closest('[data-master-battle-cell]'),id=event.dataTransfer.getData('application/x-tyranny-token');if(!cell||!id)return;event.preventDefault();
 if(!masterBattle||masterBattle.status==='ended'||battleRequestPending||!masterBattle.tokens.some(t=>t.id===id))return;
 const [x,y]=cell.dataset.masterBattleCell.split(':').map(Number);if(battleChooseCell(x,y))await battleEdit({operation:'move',tokenId:id,x,y});
});
setInterval(async()=>{
 if(!masterBattle||battleRequestPending||document.hidden||!document.querySelector('.master-battle-grid')||document.activeElement?.matches('input,select'))return;
 const id=masterBattle.id,ticket=battleLoadTicket;
 try{const result=await request(`${base()}/battles/${id}?actorId=${encodeURIComponent(battleToken)}&afterRevision=${masterBattle.revision}`);if(ticket!==battleLoadTicket||battleRequestPending||masterBattle?.id!==id||!document.querySelector('.master-battle-grid'))return;if(!result.unchanged&&battleAdopt(result.battle))renderMasterBattle();const sync=document.querySelector('.battle-editor-sync');if(sync)sync.textContent='СОХРАНЕНО НА СЕРВЕРЕ'}catch{const sync=document.querySelector('.battle-editor-sync');if(sync)sync.textContent='НЕТ СОЕДИНЕНИЯ'}
},2500);
