/* Canvas-first GM controls. Mutations use the same authenticated, revisioned API.
 * This layer never grants an extra player action or bypasses the NPC turn HUD. */
let battleDrawerOpen=false,battleQueueOpen=window.innerWidth>800,battleHudOpen=true,battleSpaceHeld=false;
let battleGesture=null,battleSuppressClickUntil=0,battleMoveUndo=null,battleLastTap=null;
const battleViews=new Map();
const battleTabletopRender=renderMasterBattle,battleTabletopEdit=battleEdit;
const battleTabletopSelect=battleSelectQuick;
battleSelectQuick=async function(id){battleHudOpen=true;return battleTabletopSelect(id)};
function battleHpCommand(text){
 const value=String(text).trim().replace(/^−/,'-');
 if(!/^[+=-]?\d+$/.test(value))return null;
 const n=Number(value.replace(/^=/,''));
 if(!Number.isSafeInteger(n)||Math.abs(n)>100000)return null;
 return value.startsWith('=')||!/[+-]/.test(value[0])?{health:n}:{delta:n};
}
function battleFreeCell(x,y,id=''){
 const m=masterBattle?.map;
 return !!m&&Number.isInteger(x)&&Number.isInteger(y)&&x>=0&&y>=0&&x<m.width&&y<m.height&&
 !(m.blocked||[]).some(p=>p.x===x&&p.y===y)&&
 !masterBattle.tokens.some(t=>t.id!==id&&t.health>0&&t.x===x&&t.y===y);
}
function battleGridDistance(a,b){return Math.max(Math.abs(b.x-a.x),Math.abs(b.y-a.y))}
function battleArmNpcPalette(){
 document.querySelectorAll('.battle-npc-card').forEach(node=>{node.draggable=false;node.style.touchAction='none';node.title='Перетащите на свободную клетку или выберите и включите расстановку'});
}
function battleSaveView(){
 const viewport=document.querySelector('.master-battle-viewport');
 if(masterBattle&&viewport)battleViews.set(masterBattle.id,{zoom:battleZoom,x:viewport.scrollLeft,y:viewport.scrollTop});
}
function battleCompactQueue(){
 const b=masterBattle,current=b.tokens.find(t=>t.id===b.currentId);
 return `<section class="tabletop-queue ${battleQueueOpen?'expanded':''}" aria-label="Очередь боя"><header><button data-tabletop-queue aria-expanded="${battleQueueOpen}" title="Свернуть или развернуть инициативу"><span>${b.status==='lobby'?'Расстановка':`Раунд ${b.round}`}</span><b>${esc(current?.name||'Нет текущего хода')}</b><i>${battleQueueOpen?'▴':'▾'}</i></button>${b.status==='active'?'<button data-battle-next class="tabletop-next" title="Завершить текущий ход (с подтверждением)" aria-label="Следующий ход">→</button>':''}</header><div class="tabletop-queue-rows" ${battleQueueOpen?'':'hidden'}>${b.initiative.map((entry,index)=>{const t=b.tokens.find(t=>t.id===entry.id);return `<div class="tabletop-queue-row ${entry.id===b.currentId?'current':''} ${t?.health<=0?'defeated':''}" draggable="${b.status!=='ended'}" data-battle-order-id="${esc(entry.id)}"><button data-battle-select="${esc(entry.id)}" title="Выбрать ${esc(entry.name)}"><span class="battle-avatar ${t?.team==='enemy'?'enemy':'party'}">${battlePicture(t||entry)}</span><span><b>${esc(entry.name)}</b><small>${t?.health??0}/${t?.healthMax??0} ХП</small></span><em>${entry.total}</em></button><button data-battle-reorder="${index}:up" ${index===0||b.status==='ended'?'disabled':''} aria-label="Поднять ${esc(entry.name)}">↑</button><button data-battle-reorder="${index}:down" ${index===b.initiative.length-1||b.status==='ended'?'disabled':''} aria-label="Опустить ${esc(entry.name)}">↓</button></div>`}).join('')||'<p>Очередь появится при запуске боя.</p>'}</div>${b.status==='active'?`<button class="tabletop-npc-turn" data-battle-mode="play">${current?.kind==='npc'?'▶ Ходить за '+esc(current.name):'▶ Интерфейс хода / ожидание игрока'}</button>`:''}</section>`;
}
function battleTokenHud(){
 const t=masterBattle.tokens.find(t=>t.id===battleToken);if(!t)return '';
 const ended=masterBattle.status==='ended';
 return `<section class="tabletop-token-hud" data-hud-actor="${esc(t.id)}" aria-label="Быстрые правки токена" ${battleHudOpen?'':'hidden'}><header><b>${esc(t.name)}</b><span>${t.health}/${t.healthMax} ХП</span><button data-tabletop-hud-close aria-label="Скрыть быстрые правки">×</button></header><form data-tabletop-hp><label for="tabletop-hp">ХП</label><input id="tabletop-hp" inputmode="text" autocomplete="off" placeholder="−10 / +10 / =80" aria-label="ХП: минус урон, плюс лечение, равно точное значение" ${ended?'disabled':''}><button ${ended?'disabled':''} title="Применить изменение ХП">✓</button><button type="button" data-tabletop-details title="Полная карточка токена">⚙</button></form><details class="tabletop-status-menu"><summary>Воздействия <span>${Object.keys(masterBattle.conditions[t.id]||{}).length}</span></summary><div><label>Эффект<select id="tabletop-effect">${Object.entries(battleEffectNames).map(([key,name])=>`<option value="${esc(key)}">${esc(name)}</option>`).join('')}</select></label><label>Раунды<input id="tabletop-rounds" type="number" min="1" max="1000" value="1"></label><label>Сила<input id="tabletop-value" type="number" step="any" value="5"></label><button type="button" data-tabletop-effect ${ended?'disabled':''}>Добавить</button><div class="battle-effect-chips">${battleEffectChips(t)}</div></div></details></section>`;
}
function battlePositionHud(){
 const hud=document.querySelector('.tabletop-token-hud'),viewport=document.querySelector('.master-battle-viewport'),grid=document.querySelector('.master-battle-grid'),board=document.querySelector('.master-battle-board'),t=masterBattle?.tokens.find(t=>t.id===battleToken);
 if(!hud||!viewport||!grid||!board||!t)return;
 const v=viewport.getBoundingClientRect(),g=grid.getBoundingClientRect(),b=board.getBoundingClientRect();
 const x=g.left+(t.x+.5)*battleZoom,y=g.top+(t.y+1)*battleZoom;
 const visible=x>=v.left&&x<=v.right&&y>=v.top&&y-battleZoom<=v.bottom;
 hud.hidden=!battleHudOpen||!visible||['ruler','pan','add_npc','place_player'].includes(battleTool)||battlePlacementArmed;
 const rightLimit=b.width-(battleDrawerOpen?document.querySelector('.tabletop-dock')?.offsetWidth||0:0);
 hud.style.left=`${Math.max(8,Math.min(x-b.left-hud.offsetWidth/2,rightLimit-hud.offsetWidth-8))}px`;
 hud.style.top=`${Math.max(v.top-b.top+8,Math.min(y-b.top+12,v.bottom-b.top-hud.offsetHeight-10))}px`;
}
renderMasterBattle=function(){
 if(!masterBattle||battleCockpitMode==='play')return;
 const old=document.querySelector('.master-battle-editor'),same=Number(old?.dataset.scene)===masterBattle.id;
 if(same)battleSaveView();else{battleGesture=null;battleMoveUndo=null;battleDrawerOpen=false;battleHudOpen=true;const view=battleViews.get(masterBattle.id);if(view)battleZoom=view.zoom}
 // A pushed scene may invalidate a gesture; never drop against a replaced board.
 if(battleGesture&&battleGesture.revision!==masterBattle.revision)battleCancelGesture();
 battleTabletopRender();
 const editor=document.querySelector('.master-battle-editor');if(!editor)return;
 editor.classList.add('battle-tabletop');editor.classList.toggle('drawer-open',battleDrawerOpen);
 const layout=editor.querySelector('.master-battle-layout'),controls=editor.querySelector('.master-battle-controls'),board=editor.querySelector('.master-battle-board');
 const dock=document.createElement('div');dock.className='tabletop-dock';dock.innerHTML=battleCompactQueue();dock.append(controls);layout.append(dock);
 const toolbar=editor.querySelector('.battle-tools');
 toolbar.insertAdjacentHTML('beforeend','<button class="dark-button" data-battle-tool="pan" title="Перетаскивать поле · P">✋ Поле</button><button class="dark-button" data-battle-tool="ruler" title="Измерить дистанцию · R / Ctrl + перетаскивание">⌁ Линейка</button>');
 for(const tool of ['pan','ruler'])toolbar.insertBefore(toolbar.querySelector(`[data-battle-tool="${tool}"]`),toolbar.querySelector('[data-battle-tool="move"]'));
 toolbar.querySelectorAll('[data-battle-tool]').forEach(button=>{const active=button.dataset.battleTool===battleTool;button.classList.toggle('active',active);button.setAttribute('aria-pressed',String(active));if(['ruler','pan'].includes(button.dataset.battleTool))button.disabled=false});
 editor.querySelector('.battle-zoom').insertAdjacentHTML('beforeend',`<button class="dark-button" data-tabletop-drawer aria-expanded="${battleDrawerOpen}" title="Карточки токенов, архив НПС и расстановка">${battleDrawerOpen?'Скрыть панель':'☷ Панель'}</button><button class="dark-button" data-tabletop-undo ${battleMoveUndo?.revision===masterBattle.revision?'':'disabled'} title="Отменить последнее перемещение, если бой с тех пор не менялся">↶</button>`);
 const hint=editor.querySelector('.battle-tool-hint');hint.textContent=battlePlacementArmed?'Нажимайте свободные клетки для расстановки · Esc — закончить':battleTool==='ruler'?'Потяните от клетки к клетке: расстояние по правилам боя. Линейка не передвигает токены.':battleTool==='pan'?'Потяните карту. Колесо — масштаб.': 'Тяните токены · ПКМ — правки · ПКМ + движение / пробел — сдвиг поля · колесо — масштаб';
 board.insertAdjacentHTML('beforeend',battleTokenHud()+'<output class="tabletop-measure" hidden></output>');
 editor.querySelectorAll('[data-battle-token]').forEach(node=>{node.draggable=false;const t=masterBattle.tokens.find(t=>t.id===node.dataset.battleToken);node.title=`${t.name} · ${t.health}/${t.healthMax} ХП\nЛКМ: выбрать · потянуть: переместить · ПКМ: быстрые правки · двойной щелчок: карточка`;node.style.setProperty('--token-health',`${Math.max(0,Math.min(100,t.health/t.healthMax*100))}%`);const effects=Object.values(masterBattle.conditions[t.id]||{});if(effects.length)node.insertAdjacentHTML('beforeend',`<span class="tabletop-token-status" title="${esc(effects.map(e=>e.name).join(', '))}">${effects.length}</span>`)});
 battleArmNpcPalette();
 const viewport=editor.querySelector('.master-battle-viewport'),view=battleViews.get(masterBattle.id);
 if(view){viewport.scrollLeft=view.x;viewport.scrollTop=view.y}
 else{battleTabletopZoom(Math.max(window.innerWidth<=800?48:16,Math.min(80,Math.floor(Math.min(viewport.clientWidth/masterBattle.map.width,viewport.clientHeight/masterBattle.map.height)))));const selected=masterBattle.tokens.find(t=>t.id===battleToken);if(selected){viewport.scrollLeft=(selected.x+.5)*battleZoom-viewport.clientWidth/2;viewport.scrollTop=(selected.y+.5)*battleZoom-viewport.clientHeight/2}battleSaveView()}
 viewport.addEventListener('scroll',()=>{battleSaveView();battlePositionHud()},{passive:true});
 viewport.addEventListener('wheel',battleWheelZoom,{passive:false});
 const effect=document.querySelector('#tabletop-effect');if(effect){const defaults=battleEffectDefaults(effect.value);document.querySelector('#tabletop-value').value=defaults.value}
 battlePositionHud();
};
// Zoom without rebuilding the grid: a wheel gesture must not steal focus or lose a drag.
function battleTabletopZoom(size,anchor=null){
 const viewport=document.querySelector('.master-battle-viewport'),grid=document.querySelector('.master-battle-grid');if(!viewport||!grid)return;
 const v=viewport.getBoundingClientRect(),g=grid.getBoundingClientRect(),x=anchor?.x??v.left+v.width/2,y=anchor?.y??v.top+v.height/2;
 const world={x:(x-g.left)/battleZoom,y:(y-g.top)/battleZoom};battleZoom=Math.max(16,Math.min(112,Math.round(size)));
 grid.style.setProperty('--battle-size',`${battleZoom}px`);grid.style.width=`${masterBattle.map.width*battleZoom}px`;grid.style.height=`${masterBattle.map.height*battleZoom}px`;
 const next=grid.getBoundingClientRect();viewport.scrollLeft+=next.left+world.x*battleZoom-x;viewport.scrollTop+=next.top+world.y*battleZoom-y;
 const output=document.querySelector('.battle-zoom output');if(output)output.textContent=`${Math.round(battleZoom/48*100)}%`;
 battleSaveView();battlePositionHud();
}
battleZoomTo=battleTabletopZoom;
function battleWheelZoom(event){if(battleCockpitMode!=='edit'||battleGesture)return;event.preventDefault();battleTabletopZoom(battleZoom*(event.deltaY<0?1.12:1/1.12),{x:event.clientX,y:event.clientY})}
battleEdit=async function(payload){
 const b=masterBattle,t=b?.tokens.find(t=>t.id===payload.tokenId),before=t&&{id:t.id,x:t.x,y:t.y},scene=b?.id;
 const saved=await battleTabletopEdit(payload);
 if(saved&&masterBattle?.id===scene){battleMoveUndo=payload.operation==='move'&&before&&masterBattle.revision===b.revision+1?{...before,scene,revision:masterBattle.revision}:null;const undo=document.querySelector('[data-tabletop-undo]');if(undo)undo.disabled=!battleMoveUndo}
 return saved;
};
async function battleMoveToken(id,x,y){
 if(!masterBattle||battleCockpitMode!=='edit'||masterBattle.status==='ended'||battleRequestPending)return;
 const t=masterBattle.tokens.find(t=>t.id===id);if(!t||t.x===x&&t.y===y)return;
 if(!battleFreeCell(x,y,id)){toast('Клетка занята, непроходима или находится за границей карты.');return}
 battleToken=id;battleHudOpen=true;await battleEdit({operation:'move',tokenId:id,x,y});
}
function battleCanvasCell(clientX,clientY){
 const grid=document.querySelector('.master-battle-grid');if(!grid)return null;
 const g=grid.getBoundingClientRect();return {x:Math.floor((clientX-g.left)/battleZoom),y:Math.floor((clientY-g.top)/battleZoom)};
}
function battleCancelGesture(){
 document.querySelector('.tabletop-drag-ghost')?.remove();document.querySelectorAll('.tabletop-drop-good,.tabletop-drop-bad').forEach(n=>n.classList.remove('tabletop-drop-good','tabletop-drop-bad'));
 document.querySelector('.tabletop-ruler-line')?.remove();const measure=document.querySelector('.tabletop-measure');if(measure)measure.hidden=true;
 document.querySelector('.master-battle-viewport')?.classList.remove('tabletop-panning');battleGesture=null;
}
function battleEditable(){return masterBattle&&battleCockpitMode==='edit'&&!battleRequestPending&&!!document.querySelector('.battle-tabletop')}
document.addEventListener('pointerdown',event=>{
 if(battleGesture&&event.button===2){event.preventDefault();battleSuppressClickUntil=Date.now()+400;battleCancelGesture();return}
 const npc=event.target.closest('.battle-npc-card');
 if(npc&&event.button===0&&battleEditable()&&masterBattle.status!=='ended'&&!battleGesture){
  event.preventDefault();battleGesture={kind:'npc',pointer:event.pointerId,scene:masterBattle.id,revision:masterBattle.revision,npcId:Number(npc.dataset.battleNpcChoice),team:battleNewTeam,x:event.clientX,y:event.clientY,moved:false};npc.setPointerCapture(event.pointerId);return;
 }
 const viewport=event.target.closest('.master-battle-viewport');if(!viewport||!battleEditable()||event.target.closest('.tabletop-token-hud')||battleGesture)return;
 const cell=battleCanvasCell(event.clientX,event.clientY),token=event.target.closest('[data-battle-token]');
 const kind=event.button===1||event.button===2||battleSpaceHeld||battleTool==='pan'?'pan':event.ctrlKey||battleTool==='ruler'?'ruler':token&&!battlePlacementArmed&&masterBattle.status!=='ended'?'token':event.pointerType==='touch'&&!battlePlacementArmed&&battleTool==='select'?'pan':null;
 if(!kind||![0,1,2].includes(event.button))return;
 event.preventDefault();battleGesture={kind,pointer:event.pointerId,scene:masterBattle.id,revision:masterBattle.revision,id:token?.dataset.battleToken,start:cell,end:cell,x:event.clientX,y:event.clientY,scrollX:viewport.scrollLeft,scrollY:viewport.scrollTop,moved:false,context:event.button===2};
 viewport.setPointerCapture(event.pointerId);
},true);
document.addEventListener('pointermove',event=>{
 const gesture=battleGesture;if(!gesture||gesture.pointer!==event.pointerId)return;
 if(gesture.scene!==masterBattle?.id||battleCockpitMode!=='edit'){battleCancelGesture();return}
 const dx=event.clientX-gesture.x,dy=event.clientY-gesture.y;
 if(!gesture.moved&&Math.hypot(dx,dy)<6)return;gesture.moved=true;event.preventDefault();
 const viewport=document.querySelector('.master-battle-viewport'),board=document.querySelector('.master-battle-board');
 if(gesture.kind==='pan'){viewport.classList.add('tabletop-panning');viewport.scrollLeft=gesture.scrollX-dx;viewport.scrollTop=gesture.scrollY-dy;return}
 gesture.end=battleCanvasCell(event.clientX,event.clientY);
 const rect=board.getBoundingClientRect();
 if(gesture.kind==='token'||gesture.kind==='npc'){
  let ghost=document.querySelector('.tabletop-drag-ghost');if(!ghost){ghost=document.createElement('span');ghost.className='tabletop-drag-ghost';ghost.innerHTML=battlePicture(gesture.kind==='npc'?battleIndex.npcs.find(n=>n.id===gesture.npcId).spec:masterBattle.tokens.find(t=>t.id===gesture.id));board.append(ghost)}
  ghost.style.left=`${event.clientX-rect.left}px`;ghost.style.top=`${event.clientY-rect.top}px`;ghost.style.width=ghost.style.height=`${battleZoom-8}px`;
  document.querySelectorAll('.tabletop-drop-good,.tabletop-drop-bad').forEach(n=>n.classList.remove('tabletop-drop-good','tabletop-drop-bad'));
  document.querySelector(`[data-master-battle-cell="${gesture.end.x}:${gesture.end.y}"]`)?.classList.add(battleFreeCell(gesture.end.x,gesture.end.y,gesture.id)?'tabletop-drop-good':'tabletop-drop-bad');
 }
 const measure=document.querySelector('.tabletop-measure');measure.hidden=false;measure.textContent=gesture.kind==='npc'?'Отпустите над свободной клеткой':`${battleGridDistance(gesture.start,gesture.end)} м${gesture.kind==='token'?' · перемещение мастера':''}`;
 if(gesture.kind==='ruler'){
  let line=document.querySelector('.tabletop-ruler-line');if(!line){line=document.createElement('span');line.className='tabletop-ruler-line';board.append(line)}
  const g=document.querySelector('.master-battle-grid').getBoundingClientRect(),sx=g.left+(gesture.start.x+.5)*battleZoom-rect.left,sy=g.top+(gesture.start.y+.5)*battleZoom-rect.top;
  const ex=g.left+(gesture.end.x+.5)*battleZoom-rect.left,ey=g.top+(gesture.end.y+.5)*battleZoom-rect.top;
  line.style.cssText=`left:${sx}px;top:${sy}px;width:${Math.hypot(ex-sx,ey-sy)}px;transform:rotate(${Math.atan2(ey-sy,ex-sx)}rad)`;
 }
},true);
document.addEventListener('pointerup',async event=>{
 const gesture=battleGesture;if(!gesture||gesture.pointer!==event.pointerId)return;
 battleCancelGesture();
 if(gesture.moved){
  battleSuppressClickUntil=Date.now()+400;
  if(['token','npc'].includes(gesture.kind)&&gesture.scene===masterBattle?.id&&gesture.revision===masterBattle.revision&&battleEditable()&&masterBattle.status!=='ended'){
   const v=document.querySelector('.master-battle-viewport').getBoundingClientRect();
   if(event.clientX>=v.left&&event.clientX<=v.right&&event.clientY>=v.top&&event.clientY<=v.bottom){
    if(gesture.kind==='token')await battleMoveToken(gesture.id,gesture.end.x,gesture.end.y);
    else if(battleFreeCell(gesture.end.x,gesture.end.y))await battleEdit({operation:'add_npc',npcId:gesture.npcId,team:gesture.team,x:gesture.end.x,y:gesture.end.y});
    else toast('Выберите свободную проходимую клетку.');
   }
  }return;
 }
 if(gesture.kind==='npc'){battleSuppressClickUntil=Date.now()+400;battleNpcChoice=String(gesture.npcId);renderMasterBattle();return}
 // Pointer capture changes the click target; choose the original token explicitly.
 if(gesture.id&&(gesture.kind==='token'||gesture.context)){
  battleSuppressClickUntil=Date.now()+400;battleHudOpen=true;
  if(gesture.kind==='token'&&battleLastTap?.id===gesture.id&&Date.now()-battleLastTap.time<350){battleDrawerOpen=true;battleQueueOpen=false;battleInspector='token';battleLastTap=null}
  else battleLastTap={id:gesture.id,time:Date.now()};
  await battleSelectQuick(gesture.id);
 }
},true);
document.addEventListener('pointercancel',battleCancelGesture,true);
window.addEventListener('blur',()=>{battleSpaceHeld=false;battleCancelGesture()});
window.addEventListener('resize',battlePositionHud);
document.addEventListener('contextmenu',event=>{if(event.target.closest('.master-battle-viewport'))event.preventDefault()});
document.addEventListener('dblclick',event=>{const t=event.target.closest('[data-battle-token]');if(t&&battleEditable()){battleDrawerOpen=true;battleQueueOpen=false;battleToken=t.dataset.battleToken;battleInspector='token';renderMasterBattle()}});
document.addEventListener('submit',async event=>{
 const form=event.target.closest('[data-tabletop-hp]');if(!form)return;event.preventDefault();
 if(!battleEditable()||masterBattle.status==='ended')return;
 const command=battleHpCommand(form.querySelector('input').value),id=form.closest('[data-hud-actor]').dataset.hudActor;
 if(!command){toast('Введите −10 для урона, +10 для лечения или =80 для точного ХП.');return}
 const saved=await battleEdit({operation:'health',tokenId:id,...command});if(saved)document.querySelector('#tabletop-hp')?.focus();
});
document.addEventListener('click',async event=>{
 if(event.target.closest('.master-battle-viewport,.battle-npc-card')&&Date.now()<battleSuppressClickUntil){event.preventDefault();event.stopImmediatePropagation();return}
 const button=event.target.closest('button');if(!button||!battleEditable())return;
 const stop=()=>{event.preventDefault();event.stopImmediatePropagation()};
 if(button.hasAttribute('data-tabletop-drawer')||button.hasAttribute('data-tabletop-details')){stop();battleDrawerOpen=button.hasAttribute('data-tabletop-details')||!battleDrawerOpen;if(battleDrawerOpen)battleQueueOpen=false;if(button.hasAttribute('data-tabletop-details'))battleInspector='token';renderMasterBattle();return}
 if(button.hasAttribute('data-tabletop-queue')){stop();battleQueueOpen=!battleQueueOpen;renderMasterBattle();return}
 if(button.hasAttribute('data-tabletop-hud-close')){stop();battleHudOpen=false;battlePositionHud();return}
 if(button.hasAttribute('data-tabletop-undo')){stop();const undo=battleMoveUndo;if(undo&&undo.scene===masterBattle.id&&undo.revision===masterBattle.revision){if(battleFreeCell(undo.x,undo.y,undo.id))await battleEdit({operation:'move',tokenId:undo.id,x:undo.x,y:undo.y,strictRevision:true});battleMoveUndo=null;document.querySelector('[data-tabletop-undo]').disabled=true}return}
 if(button.hasAttribute('data-tabletop-effect')){
  stop();if(masterBattle.status==='ended')return;
  const effect=document.querySelector('#tabletop-effect').value,rounds=Number(document.querySelector('#tabletop-rounds').value),value=Number(document.querySelector('#tabletop-value').value);
  if(!Number.isInteger(rounds)||rounds<1||rounds>1000||!Number.isFinite(value)||document.querySelector('#tabletop-value').value.trim()===''){toast('Проверьте силу эффекта и длительность (1–1000 раундов).');return}
  await battleEdit({operation:'effect',tokenId:button.closest('[data-hud-actor]').dataset.hudActor,effect,name:battleEffectNames[effect],rounds,value,beneficial:battleEffectDefaults(effect).beneficial});return;
 }
 if(button.dataset.battleTool){battleDrawerOpen=['add_npc','place_player'].includes(button.dataset.battleTool);if(battleDrawerOpen)battleQueueOpen=false;if(['pan','ruler'].includes(button.dataset.battleTool)){stop();battleCancelGesture();battleTool=button.dataset.battleTool;battleMoveMode=false;battlePlacementArmed=false;renderMasterBattle();return}}
 if(button.dataset.battleInspector)battleDrawerOpen=true;
 if(button.dataset.battleSelect||button.hasAttribute('data-battle-current')||button.dataset.masterBattleCell)battleHudOpen=true;
},true);
document.addEventListener('change',event=>{if(event.target.id==='tabletop-effect')document.querySelector('#tabletop-value').value=battleEffectDefaults(event.target.value).value});
document.addEventListener('input',event=>{if(event.target.id==='battle-npc-search')battleArmNpcPalette()});
document.addEventListener('dragstart',event=>{
 if(event.target.closest('[data-battle-token]')){event.preventDefault();return}
 const npc=event.target.closest('.battle-npc-card');if(npc&&battleEditable()&&masterBattle.status!=='ended')event.dataTransfer.setData('application/x-tyranny-npc',npc.dataset.battleNpcChoice);
},true);
document.addEventListener('drop',async event=>{
 const cell=event.target.closest('[data-master-battle-cell]'),id=event.dataTransfer.getData('application/x-tyranny-npc');if(!cell||!id||!battleEditable()||masterBattle.status==='ended')return;
 event.preventDefault();event.stopImmediatePropagation();const [x,y]=cell.dataset.masterBattleCell.split(':').map(Number);
 if(!battleFreeCell(x,y)){toast('Выберите свободную проходимую клетку.');return}
 if(!battleIndex?.npcs.some(n=>String(n.id)===id))return;
 await battleEdit({operation:'add_npc',npcId:Number(id),team:battleNewTeam,x,y});
},true);
document.addEventListener('keydown',event=>{
 if(!battleEditable()||event.target.matches('input,select,textarea,[contenteditable]')||event.metaKey||event.altKey)return;
 if(event.code==='Space'){event.preventDefault();battleSpaceHeld=true;return}
 if(event.repeat)return;
 const stop=()=>{event.preventDefault();event.stopImmediatePropagation()};
 if(event.key==='Escape'){stop();battleCancelGesture();battleSpaceHeld=false;battleHudOpen=false;battleDrawerOpen=false;battlePlacementArmed=false;battleTool='select';renderMasterBattle();return}
 if(event.ctrlKey&&(event.code==='KeyZ')){stop();document.querySelector('[data-tabletop-undo]')?.click();return}
 if(event.ctrlKey)return;
 if(event.code==='KeyR'||event.code==='KeyP'){stop();document.querySelector(`[data-battle-tool="${event.code==='KeyR'?'ruler':'pan'}"]`)?.click();return}
 if(event.code==='KeyH'){stop();battleHudOpen=true;battlePositionHud();document.querySelector('#tabletop-hp')?.focus();return}
 if((event.code==='Tab'||event.key==='Tab')&&(event.target===document.body||event.target.closest('.master-battle-viewport'))){stop();const all=masterBattle.tokens,index=all.findIndex(t=>t.id===battleToken),next=all[(index+(event.shiftKey?-1:1)+all.length)%all.length];if(next)battleSelectQuick(next.id);return}
 const delta={ArrowLeft:[-1,0],ArrowRight:[1,0],ArrowUp:[0,-1],ArrowDown:[0,1]}[event.key];
 if(delta&&masterBattle.status!=='ended'){stop();const t=masterBattle.tokens.find(t=>t.id===battleToken);if(t)battleMoveToken(t.id,t.x+delta[0],t.y+delta[1])}
},true);
document.addEventListener('keyup',event=>{if(event.code==='Space')battleSpaceHeld=false});
