/* No HP forms or scene overrides here: current NPC, normal action budget, next turn. */
const renderMasterArena=renderTraining;
renderTraining=function(panel,character){
 if(!training){panel.innerHTML='<section class="master-combat-empty"><h2>На поле нет участников</h2><p>Вернитесь в администрирование и разместите токены.</p></section>';updateMasterTurn();return}
 renderMasterArena(panel,character);
 panel.querySelector('.training-reset')?.remove();
 const header=panel.querySelector('.training-header');if(header)header.hidden=true;
 const canAct=!!masterScene?.controller?.canAct;
 panel.classList.toggle('master-waiting',!canAct);
 if(!canAct){
  panel.querySelectorAll('[data-training-kind],[data-stance-name],[data-training-set],[data-quick-slot],[data-target-id],[data-move-x],[data-picker-action]').forEach(button=>{button.disabled=true;button.setAttribute('aria-disabled','true');button.draggable=false});
  const resources=panel.querySelector('.original-turn');if(resources)resources.textContent=masterScene?.status==='active'?'Ожидание хода игрока':masterScene?.status==='ended'?'Бой завершён':'Бой ещё не начался';
 }
 updateMasterTurn();
};
// Viewer id "player" is rebound at each initiative step. Never animate one NPC
// into another, or report their different starting HP as combat damage.
const animateMasterMovement=animateTokenMovement;
animateTokenMovement=async function(before,after){if(before?.controllerId!==after?.controllerId)return;return animateMasterMovement(before,after)};
const masterHealthChanges=combatHealthChanges;
combatHealthChanges=function(before,after){if(before?.controllerId!==after?.controllerId)return [];return masterHealthChanges(before,after)};
function updateMasterTurn(){
 const battle=masterScene,controller=battle?.controller,node=$('#master-turn');
 $('#battle-title').textContent=battle?`${battle.name} · №${battle.id}`:'Поле боя';
 $('#battle-admin-link').href=masterAdministrationUrl();
 const waiting=!controller?.canAct;node.classList.toggle('waiting',waiting);
 node.textContent=!battle?'':battle.status==='lobby'?'Расстановка. Запустите бой в администрировании.':battle.status==='ended'?'Бой завершён.':controller?.canAct?`Ваш ход: ${controller.name} · Раунд ${battle.round}`:controller?`Ход игрока: ${controller.name} · Ожидание`: 'Нет участников, способных ходить.';
}
async function refreshMasterBattle(force=false){
 if(masterPollPending||combatBusy||masterMissing)return;
 masterPollPending=true;
 try{
  const result=await masterFetch(masterBattlePath()+(!force&&masterScene?`&afterRevision=${masterScene.revision}`:''));
  if(!result.unchanged){
   const before=training?.grid;adoptMasterBattle(result.battle);renderTraining($('#panel'),data.character);
   if(before?.controllerId===training?.grid?.controllerId&&armedCombatAction){armedCombatAction=training.actions.find(a=>a.kind===armedCombatAction.kind&&a.name===armedCombatAction.name)||null;if(armedCombatAction&&combatAim)showCombatAim(combatAim)}
  }
  $('#battle-sync').textContent='СИНХРОНИЗИРОВАНО';
 }catch(error){
  $('#battle-sync').textContent='НЕТ СОЕДИНЕНИЯ';
  if(error.status===410||error.message.includes('не принадлежит')){
   masterMissing=true;clearCombatAim();masterScene=null;training=null;
   $('#panel').innerHTML=`<section class="master-combat-empty"><h2>Бой недоступен</h2><p>${esc(error.message)}</p><p>Бой мог быть удалён. Вернитесь в администрирование.</p></section>`;$('#master-turn').textContent='Управление отключено';
  }else if(force)toast(error.message);
 }finally{masterPollPending=false}
}
// Shared capture handlers provide aiming, quickbar bindings and safe movement
// confirmation. Only the cabinet's ordinary bubbling controls are wired here.
document.addEventListener('click',event=>{
 if(event.target.closest('[data-master-refresh]')){refreshMasterBattle(true);return}
 if(!training?.active||combatBusy)return;
 const picker=event.target.closest('[data-combat-picker]');
 if(picker){combatPicker=combatPicker===picker.dataset.combatPicker?'':picker.dataset.combatPicker;quickbarEditing=0;renderTraining($('#panel'),data.character);return}
 if(event.target.closest('[data-combat-picker-close]')){combatPicker='';quickbarEditing=0;renderTraining($('#panel'),data.character);return}
 if(!masterScene?.controller?.canAct)return;
 const button=event.target.closest('button');if(!button||button.disabled)return;
 if(button.hasAttribute('data-quick-slot')&&!button.dataset.trainingKind){quickbarEditing=+button.dataset.quickSlot;combatPicker='ability';renderTraining($('#panel'),data.character);return}
 if(button.dataset.stanceName){combatPicker='';trainingMutate('action',{kind:'stance',name:button.dataset.stanceName});return}
 if(button.dataset.trainingSet){trainingMutate('action',{kind:'weapon_set',number:+button.dataset.trainingSet});return}
 if(button.dataset.trainingKind){trainingMutate('action',{kind:button.dataset.trainingKind,name:button.dataset.trainingName||''});return}
 if(button.dataset.targetId){trainingMutate('action',{kind:'select_target',targetId:button.dataset.targetId});return}
 if(button.hasAttribute('data-move-x'))trainingMutate('action',{kind:'move',x:+button.dataset.moveX,y:+button.dataset.moveY});
});
document.addEventListener('DOMContentLoaded',()=>{
 $('#battle-admin-link').href=masterAdministrationUrl();
 if(!api||!token||!Number.isInteger(masterBattleId)||masterBattleId<1){$('#panel').textContent='Откройте «Ведение боя» из мастерской.';return}
 refreshMasterBattle(true);
});
setInterval(()=>{if(!document.hidden)refreshMasterBattle()},2000);
document.addEventListener('visibilitychange',()=>{if(!document.hidden)refreshMasterBattle(true)});
