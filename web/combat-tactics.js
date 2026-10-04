/* Tactical presentation: only server routes, hit distributions and resolved events. */
let pendingCombatMove=null;
function combatShapePath(cells){
 const set=new Set(cells.map(p=>`${p.x}:${p.y}`)),edges=[];
 for(const {x,y} of cells){
  if(!set.has(`${x}:${y-1}`))edges.push(`M${x},${y}h1`);
  if(!set.has(`${x+1}:${y}`))edges.push(`M${x+1},${y}v1`);
  if(!set.has(`${x}:${y+1}`))edges.push(`M${x+1},${y+1}h-1`);
  if(!set.has(`${x-1}:${y}`))edges.push(`M${x},${y+1}v-1`);
 }
 return edges.join('');
}
function combatShapeMarkup(cells,grid,cls,color='#d984a1'){
 return `<svg class="combat-shape-outline ${cls}" viewBox="0 0 ${grid.width} ${grid.height}" preserveAspectRatio="none" aria-hidden="true" style="--shape-color:${color}"><path d="${combatShapePath(cells)}"></path></svg>`;
}
function combatPreviewMarkup(aim,action){
 const rows=aim?.previews||[];
 return `${rows.map(row=>`<article><header><b>${esc(row.name)}</b><strong>${row.hitChance}%</strong></header><div class="combat-chance-bar" aria-label="Вероятность попадания ${row.hitChance}%"><i style="width:${row.hitChance}%"></i></div><p>Точность ${row.accuracy} → ${esc(row.defenseName)} ${row.defense}${row.cover?` + укрытие ${row.cover}`:''}</p><p>Урон при попадании: <b>${row.damageMin}–${row.damageMax}</b>${row.strikeCount>1?` · ${row.strikeCount} удара`:''}</p><small>Промах ${row.outcomes.miss}% · скользящий ${row.outcomes.graze}% · попадание ${row.outcomes.hit}% · крит ${row.outcomes.critical}%${row.outcomes.reflected?` · отражение ${row.outcomes.reflected}%`:''}</small></article>`).join('')}${rows.length?'<footer>Шанс включает скользящие удары. Урон — за один удар, без дополнительных эффектов. Бросок выполняется только после применения.</footer>':''}`;
}
function clearCombatRoute(){
 pendingCombatMove=null;
 document.querySelectorAll('.combat-route-svg,.combat-route-note').forEach(node=>node.remove());
 document.querySelectorAll('.route-step,.route-danger,.route-attacker').forEach(node=>node.classList.remove('route-step','route-danger','route-attacker'));
}
function showCombatRoute(point,confirm=false){
 if(armedCombatAction||combatBusy||!training?.active)return;
 const route=training.grid.movementPreviews?.[`${point.x}:${point.y}`];if(!route)return;
 document.querySelectorAll('.combat-route-svg,.combat-route-note').forEach(node=>node.remove());
 document.querySelectorAll('.route-step,.route-danger,.route-attacker').forEach(node=>node.classList.remove('route-step','route-danger','route-attacker'));
 const danger=route.opportunities.length>0,map=document.querySelector('.tactical-map'),overlay=document.querySelector('.combat-aim-overlay');
 const points=route.path.map(p=>`${p.x+.5},${p.y+.5}`).join(' ');
 map?.insertAdjacentHTML('beforeend',`<svg class="combat-route-svg ${danger?'danger':''}" viewBox="0 0 ${training.grid.width} ${training.grid.height}" preserveAspectRatio="none" aria-hidden="true"><polyline points="${points}"></polyline></svg>`);
 for(const p of route.path.slice(1))document.querySelector(`[data-cell="${p.x}:${p.y}"]`)?.classList.add(danger?'route-danger':'route-step');
 for(const attacker of route.opportunities){const t=training.grid.tokens.find(t=>t.id===attacker.id);if(t)document.querySelector(`[data-cell="${t.x}:${t.y}"] .combat-token`)?.classList.add('route-attacker')}
 overlay?.insertAdjacentHTML('beforeend',`<div class="combat-route-note ${danger?'danger':''}" role="status"><span>${route.cost} / ${training.turn.movementRemaining} м${route.stealthDetected?' · Враг обнаружит вас':''}${danger?` · Атака по возможности: ${esc(route.opportunities.map(x=>x.name).join(', '))}`:''}</span>${confirm?'<div><button data-confirm-combat-move>Идти</button><button data-cancel-combat-move>Отмена</button></div>':''}</div>`);
}
const showCombatAimBeforeTactics=showCombatAim;
showCombatAim=function(point){
 clearCombatRoute();showCombatAimBeforeTactics(point);
 if(!armedCombatAction)return;
 const aim=armedCombatAction.aims?.[`${point.x}:${point.y}`],map=document.querySelector('.tactical-map');
 map?.querySelector('.combat-shape-outline.aim-outline')?.remove();
 if(aim?.cells?.length)map?.insertAdjacentHTML('beforeend',combatShapeMarkup(aim.cells,training.grid,'aim-outline',aim.valid?'#d984a1':'#dc4154'));
 const preview=document.querySelector('.combat-intent-panel');
 if(preview){preview.innerHTML=combatPreviewMarkup(aim,armedCombatAction);preview.hidden=!preview.innerHTML}
 const banner=document.querySelector('.combat-targeting-banner');
 if(banner){
  banner.textContent=`${armedCombatAction.displayName||armedCombatAction.name} · ${aim?.valid?'Нажмите для применения':'Недоступная цель'}${aim?.targetIds?.length?` · целей: ${aim.targetIds.length}`:''}`;
  if(aim?.previews?.length){const first=aim.previews[0];banner.textContent+=` · ${first.hitChance}% · урон ${first.damageMin}–${first.damageMax}`}
 }
};
const clearCombatAimBeforeTactics=clearCombatAim;
clearCombatAim=function(){clearCombatAimBeforeTactics();clearCombatRoute();document.querySelector('.aim-outline')?.remove();const panel=document.querySelector('.combat-intent-panel');if(panel)panel.hidden=true};
const renderTrainingBeforeTactics=renderTraining;
renderTraining=function(panel,character){
 clearCombatRoute();renderTrainingBeforeTactics(panel,character);
 if(!training?.active)return;
 const sidebar=panel.querySelector('.combat-sidebar'),hud=sidebar?.querySelector('.tyranny-combat-hud');
 sidebar?.querySelector('.combat-target-card')?.insertAdjacentHTML('afterend','<section class="combat-intent-panel" aria-label="Предпросмотр действия" hidden></section>');
 hud?.insertAdjacentHTML('afterend',`<nav class="combat-tactical-controls" aria-label="Тактические приёмы">${training.actions.filter(a=>a.kind==='tactic').map(a=>`<button draggable="true" data-action-kind="tactic" data-action-name="${esc(a.name)}" data-training-kind="tactic" data-training-name="${esc(a.name)}" aria-disabled="${!!combatActionBlock(a)}" ${training.finished?'disabled':''}>${combatGlyph(a)}<span>${esc(a.name)}</span></button>`).join('')}</nav>`);
 if(training.stealth?.active)hud?.querySelector('.combat-hud-statuses')?.insertAdjacentHTML('beforeend',`<span class="combat-stealth-status" data-ui-tip="Скрытность. Подозрение ${training.stealth.suspicion}/200. На 100 враги ищут вас, на 200 обнаруживают. Хитроумие: ${training.stealth.skill}. Движение стоит 2 м за клетку.">Скрытность · ${Math.round(training.stealth.suspicion/2)}%</span>`);
 for(const token of training.grid.tokens){
  const element=panel.querySelector(`[data-cell="${token.x}:${token.y}"] .combat-token`);if(!element)continue;
  element.classList.toggle('is-current',token.id===training.turn.actorId);
  element.classList.toggle('is-stealthed',token.id==='player'&&!!training.stealth?.active);
  if(token.id==='player'&&training.stealth?.active)element.insertAdjacentHTML('beforeend',`<span class="combat-token-stealth" data-ui-tip="Вы скрываетесь. Подозрение: ${training.stealth.suspicion}/200"><img src="assets/game-combat/icon_option_stealth.png" alt="Скрытность"></span>`);
  const observer=training.stealth?.observers?.find(o=>o.id===token.id);
  if(observer?.suspicion>0){const search=observer.suspicion>=100,color=search?'#d06b78':'#d8bf75';element.insertAdjacentHTML('beforeend',`<i class="combat-suspicion-ring" style="--suspicion:${Math.min(100,search?observer.suspicion-100:observer.suspicion)}%;--suspicion-color:${color}" aria-label="${search?'Поиск':'Подозрение'}: ${observer.suspicion}/200"></i>`)}
  element.style.setProperty('--token-health',`${Math.max(0,Math.min(100,token.health/Math.max(1,token.healthMax)*100))}%`);
  const states=Object.values(training.conditions?.[token.id]||{}).sort((a,b)=>Number(!!a.beneficial)-Number(!!b.beneficial));
  const badges=states.slice(0,3).map(state=>{
   const name=String(state.name||'Эффект').split(/[:·]/)[0],rounds=Math.max(1,Number(state.until)-training.round+1),caption=name.slice(0,3).toUpperCase();
   return `<span class="${state.beneficial?'beneficial':''}" data-ui-tip="${esc(combatStatusLabel(state,training.round))}">${esc(caption)}<b>${rounds>=999000?'∞':rounds}</b></span>`;
  }).join('');
  element.insertAdjacentHTML('beforeend',`<i class="combat-token-health"></i>${badges?`<span class="combat-token-states">${badges}${states.length>3?`<span data-ui-tip="${esc(states.slice(3).map(s=>combatStatusLabel(s,training.round)).join('\n'))}">+${states.length-3}</span>`:''}</span>`:''}`);
 }
 const map=panel.querySelector('.tactical-map'),colors={Холод:'#80c6dc',Огонь:'#ce6841',Жизнь:'#7eb877',Истощение:'#a47ec4'};
 for(const area of training.areas||[])map?.insertAdjacentHTML('beforeend',combatShapeMarkup(area.cells,training.grid,'area-outline',colors[area.core]||'#a3a6c7'));
 if(armedCombatAction&&combatAim)showCombatAim(combatAim);
};
async function showCombatOutcomeFeedback(events,grid){
 const layer=document.querySelector('.combat-vfx-layer');if(!layer||!events?.length)return;
 const reduced=matchMedia('(prefers-reduced-motion: reduce)').matches;
 await Promise.all(events.map(async event=>{
  const token=grid?.tokens.find(t=>t.id===event.targetId);if(!token)return;
  const miss=event.result==='Промах',block=event.result==='Отражено'||event.absorbed,crit=event.result==='Критическое попадание';
  const node=document.createElement('span');node.className=`combat-outcome ${miss?'miss':block?'block':crit?'critical':'hit'}`;
  node.textContent=miss?'Промах':block?(event.absorbed?'Поглощено':'Отражено'):crit?'Критический удар':event.result==='Скользящий удар'?'Скользящий удар':'';
  node.style.left=(token.x+.5)/grid.width*100+'%';node.style.top=(token.y+.5)/grid.height*100+'%';layer.append(node);
  const portrait=document.querySelector(`[data-cell="${token.x}:${token.y}"] .combat-token`);
  if(portrait){const dx=miss?6:crit?3:1;portrait.animate(reduced?[{opacity:.6},{opacity:1}]:[{transform:'translate(-50%,-50%)'},{transform:`translate(calc(-50% + ${dx}px),-50%)`,filter:block?'brightness(1.5)':crit?'brightness(1.6)':'brightness(1.15)'},{transform:'translate(-50%,-50%)'}],{duration:reduced?150:280}).finished.catch(()=>{})}
  try{await node.animate([{opacity:0,transform:'translate(-50%,-140%)'},{opacity:1,offset:.15},{opacity:1,offset:.65},{opacity:0,transform:`translate(-50%,${reduced?'-140%':'-210%'})`}],{duration:reduced?300:900}).finished}catch{}finally{node.remove()}
 }));
}
const playCombatEffectBeforeTactics=playCombatEffect;
playCombatEffect=async function(action,point,grid,cells){await playCombatEffectBeforeTactics(action,point,grid,cells);const after=training?.grid||grid;void showCombatOutcomeFeedback(training?.events,{...after,tokens:[...after.tokens,...grid.tokens.filter(old=>!after.tokens.some(token=>token.id===old.id))]})};
const trainingMutateBeforeTactics=trainingMutate;
trainingMutate=async function(path,body={}){clearCombatRoute();const before=training;await trainingMutateBeforeTactics(path,body);if(path==='action'&&before!==training)void showCombatOutcomeFeedback(training?.events,training?.grid)};
function previewCombatMovement(event){
 if(armedCombatAction||pendingCombatMove||combatBusy||tab!=='training')return;
 const cell=event.target.closest('[data-cell]');if(!cell)return;
 const [x,y]=cell.dataset.cell.split(':').map(Number);clearCombatRoute();showCombatRoute({x,y});
}
document.addEventListener('pointerover',previewCombatMovement);
document.addEventListener('focusin',previewCombatMovement);
document.addEventListener('pointerout',event=>{if(!pendingCombatMove&&event.target.closest('.tactical-map')&&!event.relatedTarget?.closest?.('.tactical-map'))clearCombatRoute()});
document.addEventListener('click',event=>{
 if(tab!=='training'||!training?.active||combatBusy)return;
 if(event.target.closest('[data-cancel-combat-move]')){event.preventDefault();event.stopImmediatePropagation();clearCombatRoute();return}
 if(event.target.closest('[data-confirm-combat-move]')){event.preventDefault();event.stopImmediatePropagation();const point=pendingCombatMove;if(point)trainingMutate('action',{kind:'move',...point});return}
 const cell=event.target.closest('[data-move-x]');if(!cell||armedCombatAction)return;
 const point={x:+cell.dataset.moveX,y:+cell.dataset.moveY},route=training.grid.movementPreviews?.[`${point.x}:${point.y}`];
 if(route?.opportunities.length){event.preventDefault();event.stopImmediatePropagation();pendingCombatMove=point;showCombatRoute(point,true)}
},true);
document.addEventListener('keydown',event=>{if(event.key==='Escape'&&pendingCombatMove){event.preventDefault();clearCombatRoute()}});
