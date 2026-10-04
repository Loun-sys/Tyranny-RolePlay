/* Presentation uses only the resolved server state; no predicted damage. */
function combatHealthChanges(before,after){
 if(!before?.tokens||!after?.tokens)return [];
 const current=new Map(after.tokens.map(token=>[token.id,token]));
 return before.tokens.flatMap(previous=>{
  const token=current.get(previous.id),health=token?Number(token.health):0,delta=health-Number(previous.health);
  return Number.isFinite(delta)&&delta!==0?[{id:previous.id,name:previous.name,x:token?.x??previous.x,y:token?.y??previous.y,delta}]:[];
 });
}
function combatStatusDuration(state,round){
 const remaining=Number(state.until)-Number(round)+1;
 return remaining>=999000?'до конца боя':Number.isFinite(remaining)&&remaining>0?roundText(remaining):'';
}
function combatStatusLabel(state,round){
 const duration=combatStatusDuration(state,round);
 const name=duration?String(state.name||'Воздействие').replace(/\s+на\s+\d+(?:[.,]\d+)?\s+раунд(?:а|ов)?(?=\s|[.,;)]|$)/gi,'').trim():state.name||'Воздействие';
 return `${name}${state.stacks>1?` ×${state.stacks}`:''}${duration?` · ${duration}`:''}`;
}
function combatTargetCard(t){
 const target=t.dummy;if(!target?.name)return '';
 const key=t.grid?.selectedTargetId,token=t.grid?.tokens?.find(x=>x.id===key);
 const hp=Number(target.health??token?.health??0),max=Math.max(1,Number(target.healthMax??token?.healthMax??1));
 const states=Object.values(t.conditions?.[key]||{});
 const statuses=states.slice(0,3).map(state=>`<span tabindex="0" data-ui-tip="${esc(combatStatusLabel(state,t.round))}">${esc(combatStatusLabel(state,t.round))}</span>`).join('');
 return `<section class="combat-target-card" aria-label="Выбранная цель"><header><span>ЦЕЛЬ</span><b>${esc(target.name)}</b><small>${hp}/${max}</small></header><div class="combat-target-health" role="progressbar" aria-label="Здоровье выбранной цели" aria-valuenow="${hp}" aria-valuemin="0" aria-valuemax="${max}"><i style="width:${Math.max(0,Math.min(100,hp/max*100))}%"></i></div><div class="combat-target-values"><span>${esc(t.turn?.distanceToTarget??'—')} м</span><span>Броня ${esc(target.armor??0)}</span><span>${t.turn?.cover&&t.turn.cover!=='нет'?`Укрытие: ${esc(t.turn.cover)}`:'Без укрытия'}</span></div>${states.length?`<div class="combat-target-statuses">${statuses}${states.length>3?`<span tabindex="0" data-ui-tip="${esc(states.slice(3).map(s=>s.name).join('\n'))}">+${states.length-3}</span>`:''}</div>`:''}</section>`;
}
const renderTrainingBeforeFeedback=renderTraining;
renderTraining=function(panel,character){
 renderTrainingBeforeFeedback(panel,character);
 if(!training?.active)return;
 const hud=panel.querySelector('.tyranny-combat-hud');
 hud?.insertAdjacentHTML('afterend',combatTargetCard(training));
 const banner=panel.querySelector('.combat-targeting-banner'),viewport=panel.querySelector('.tactical-map-wrap');
 if(banner&&viewport){
  const overlay=document.createElement('div');overlay.className='combat-aim-overlay';
  overlay.append(banner);viewport.prepend(overlay);
 }
 const statuses=Object.values(training.conditions?.player||{});
 hud?.querySelectorAll('.combat-hud-statuses > span').forEach((element,index)=>{
  const state=statuses[index];if(!state)return;
  element.textContent=combatStatusLabel(state,training.round);element.dataset.uiTip=element.textContent;
 });
 for(const token of training.grid?.tokens||[]){
  const element=panel.querySelector(`[data-cell="${token.x}:${token.y}"] .combat-token`);if(!element)continue;
  element.dataset.uiTip=`${token.name} · ${token.health}/${token.healthMax}\n${Object.values(training.conditions?.[token.id]||{}).map(state=>combatStatusLabel(state,training.round)).join('\n')}`;
 }
 panel.querySelector('.combat-arena')?.insertAdjacentHTML('beforeend','<div class="combat-live-feedback" role="status" aria-live="polite" aria-atomic="true"></div>');
};
async function showCombatHealthFeedback(before,after){
 const changes=combatHealthChanges(before,after),layer=document.querySelector('.combat-vfx-layer');
 if(!layer||!changes.length||tab!=='training')return;
 const reduced=matchMedia('(prefers-reduced-motion: reduce)').matches;
 const live=document.querySelector('.combat-live-feedback');
 if(live)live.textContent=changes.map(change=>`${change.name}: ${change.delta>0?'восстановлено':'потеряно'} ${Math.abs(change.delta)} здоровья`).join('. ');
 await Promise.all(changes.map(async change=>{
  const node=document.createElement('span');node.className='combat-floating-result '+(change.delta>0?'healing':'damage');
  node.textContent=(change.delta>0?'+':'−')+Math.abs(change.delta);node.setAttribute('aria-hidden','true');
  node.style.left=(change.x+.5)/after.width*100+'%';node.style.top=(change.y+.5)/after.height*100+'%';layer.append(node);
  if(change.delta>0){
   const ring=document.createElement('i');ring.className='combat-healing-ring';ring.style.left=node.style.left;ring.style.top=node.style.top;layer.append(ring);
   ring.animate(reduced?[{opacity:.6},{opacity:0}]:[{opacity:0,transform:'translate(-50%,-50%) scale(.8)'},{opacity:.6,offset:.3},{opacity:0,transform:'translate(-50%,-50%) scale(1.25)'}],{duration:reduced?200:600}).finished.catch(()=>{}).finally(()=>ring.remove());
  }
  try{await node.animate(reduced?[{opacity:1},{opacity:0}]:[{opacity:0,transform:'translate(-50%,-70%)'},{opacity:1,offset:.15},{opacity:1,offset:.65},{opacity:0,transform:'translate(-50%,-150%)'}],{duration:reduced?350:950,easing:'ease-out'}).finished}catch{}finally{node.remove()}
 }));
}
const playCombatEffectBeforeFeedback=playCombatEffect;
playCombatEffect=async function(action,point,grid,cells){
 const after=training?.grid;
 await playCombatEffectBeforeFeedback(action,point,grid,cells);
 void showCombatHealthFeedback(grid,after);
};
const trainingMutateBeforeFeedback=trainingMutate;
trainingMutate=async function(path,body={}){
 const before=training?.grid;
 await trainingMutateBeforeFeedback(path,body);
 if(path==='action'&&['move','wait','end_turn','ability','item'].includes(body.kind))void showCombatHealthFeedback(before,training?.grid);
};
