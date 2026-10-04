/* Shared battles reuse the combat HUD; training remains separate and unchanged. */
let sharedBattle=null,sharedBattleId=Number(q.get('battle')||0),sharedBattleMode=false,sharedBattleLoading=false;
const requestBeforeBattle=request,renderTabBeforeBattle=renderTab,renderTrainingBeforeBattle=renderTraining;
request=async function(path,options={}){
 if(sharedBattleMode&&sharedBattleId&&path.includes('/training')){
  if(path.endsWith('/reset')||path.endsWith('/start'))throw Error('Общий бой запускает и завершает мастер.');
  const opts={...options};
  if(opts.body)opts.body=JSON.stringify({...JSON.parse(opts.body),revision:sharedBattle?.revision});
  const j=await requestBeforeBattle(`/api/portal/${encodeURIComponent(token)}/battles/${sharedBattleId}`,opts);
  sharedBattle=j.battle;return {...j,training:j.battle.training||{active:false}};
 }
 return requestBeforeBattle(path,options);
};
function ensureBattleTab(){const tabs=document.querySelector('#tabs');if(tabs&&!tabs.querySelector('[data-tab="battle"]'))tabs.insertAdjacentHTML('beforeend','<button data-tab="battle">БОЙ</button>')}
renderTab=function(){ensureBattleTab();if(tab==='battle'){sharedBattleMode=true;tab='training';openSharedBattle();return}renderTabBeforeBattle()};
async function openSharedBattle(){
 if(sharedBattleLoading)return;sharedBattleLoading=true;
 try{
  const j=await requestBeforeBattle(`/api/portal/${encodeURIComponent(token)}/battles`);
  const battles=j.battles.filter(b=>b.status!=='ended');
  if(!sharedBattleId||!battles.some(b=>b.id===sharedBattleId))sharedBattleId=battles[0]?.id||0;
  if(!sharedBattleId){$('#panel').innerHTML='<section class="box"><h2>Общий бой</h2><p>Мастер приглашает участников через /старт-боя. Чтобы вступить, используйте /начать-бой в Дискорде.</p></section>';return}
  sharedBattle=(await requestBeforeBattle(`/api/portal/${encodeURIComponent(token)}/battles/${sharedBattleId}`)).battle;
  training=sharedBattle.training||{active:false};renderSharedBattle();
 }catch(e){toast(e.message);$('#panel').textContent=e.message}finally{sharedBattleLoading=false}
}
function renderSharedBattle(){
 const p=$('#panel'),b=sharedBattle;
 if(!b)return;
 if(b.status==='ended'){p.innerHTML='<section class="box"><h2>Бой завершён мастером</h2></section>';return}
 if(b.status==='lobby'||!b.training){
  p.innerHTML=`<section class="box battle-lobby"><h2>${esc(b.name)} · сбор участников</h2><p>Мастер размещает персонажей и противников. Бой начнётся после его подтверждения.</p><div>${Object.values(b.participants).map(m=>`<p>${esc(m.name)} — ${m.joined?'готов':'не вступил'}</p>`).join('')}</div>${Object.values(b.participants).some(m=>!m.joined)?'<button class="action" data-shared-battle-join>ВСТУПИТЬ В БОЙ</button>':''}<button class="dark-button" data-shared-battle-refresh>ОБНОВИТЬ</button></section>`;return;
 }
 renderTraining(p,data.character);
}
renderTraining=function(panel,c){
 renderTrainingBeforeBattle(panel,c);
 if(!sharedBattleMode||!sharedBattle?.training)return;
 const t=sharedBattle.training,current=t.initiative.find(x=>x.id===t.turn.actorId);
 const reset=panel.querySelector('.training-reset');if(reset){reset.classList.remove('training-reset');reset.dataset.sharedBattleRefresh='';reset.textContent='ОБНОВИТЬ'}
 const header=panel.querySelector('.training-header h2');if(header)header.textContent=`${sharedBattle.name} · Раунд ${t.round}`;
 const status=panel.querySelector('.combat-turn-resources>span');if(status&&t.turn.actorId!=='player')status.textContent=`Сейчас ходит: ${current?.name||'участник'}`;
 if(t.turn.actorId!=='player')panel.querySelectorAll('[data-training-kind],[data-training-set]').forEach(b=>{b.disabled=true});
};
document.addEventListener('click',async e=>{
 const button=e.target.closest('[data-tab]');if(button){if(button.dataset.tab!=='battle')sharedBattleMode=false;else sharedBattleMode=true}
 if(e.target.closest('[data-shared-battle-refresh]')){await openSharedBattle();return}
 if(e.target.closest('[data-shared-battle-join]')){try{await requestBeforeBattle(`/api/portal/${encodeURIComponent(token)}/battles/${sharedBattleId}`,{method:'POST',body:JSON.stringify({operation:'join'})});await openSharedBattle()}catch(error){toast(error.message)}}
},true);
let sharedBattlePollPending=false;
setInterval(async()=>{
 ensureBattleTab();
 if(!data||!token||!api||sharedBattlePollPending||sharedBattleLoading||typeof combatBusy!=='undefined'&&combatBusy)return;
 if(q.get('battle')&&sharedBattleId&&!sharedBattleMode&&!document.querySelector('[data-tab="battle"]')?.dataset.opened){
  const button=document.querySelector('[data-tab="battle"]');if(button){button.dataset.opened='1';button.click()}return;
 }
 if(!sharedBattleMode||tab!=='training'||!sharedBattleId)return;
 sharedBattlePollPending=true;
 try{const j=await requestBeforeBattle(`/api/portal/${encodeURIComponent(token)}/battles/${sharedBattleId}?afterRevision=${sharedBattle?.revision||0}`);
  if(!j.unchanged&&j.battle.revision!==sharedBattle?.revision){const old=training?.grid;sharedBattle=j.battle;training=sharedBattle.training||{active:false};renderSharedBattle();if(old&&training.grid)await animateTokenMovement(old,training.grid,training.movementPath)}
 }catch(e){
  if(e.message.includes('не принадлежит')){
   sharedBattle=null;sharedBattleId=0;training={active:false};clearCombatAim();
   $('#panel').innerHTML='<section class="box"><h2>Бой удалён или недоступен</h2><p>Мастер может пригласить вас в другой бой. Ваш персонаж и инвентарь сохранены.</p></section>';
  }else toast(e.message);
 }finally{sharedBattlePollPending=false}
},2000);
