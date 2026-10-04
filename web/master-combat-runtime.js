/* The master plays through the exact same arena renderer and targeting handlers. */
const q=new URLSearchParams(location.search),fragment=new URLSearchParams(location.hash.slice(1));
const api=(q.get('api')||localStorage.getItem('tyranny_api')||'').replace(/\/$/,''),token=fragment.get('token')||'',masterBattleId=Number(q.get('battle'));
const $=s=>document.querySelector(s),esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const roundText=value=>`${Number(value).toLocaleString('ru-RU',{maximumFractionDigits:2})} раунд.`;
let masterScene=null,masterMissing=false,masterPollPending=false,training=null,data={character:{name:'НПС',level:1},spells:[],talentLibrary:[],combatQuickbar:[]},tab='training',combatPicker='',quickbarEditing=0,trainingLoading=false;
function toast(message){const node=$('#toast');node.textContent=message||'';node.classList.add('show');clearTimeout(toast.timer);toast.timer=setTimeout(()=>node.classList.remove('show'),4000)}
function masterBattlePath(){return `/api/admin/${encodeURIComponent(token)}/battles/${masterBattleId}?mode=play`}
function masterAdministrationUrl(){return `admin.html?api=${encodeURIComponent(api)}&battle=${masterBattleId}#token=${encodeURIComponent(token)}`}
async function masterFetch(path,options={}){
 const response=await fetch(api+path,{...options,headers:{'Content-Type':'application/json',...(options.headers||{})}}),result=await response.json().catch(()=>({}));
 if(!response.ok){const error=Error(result.error||`Ошибка ${response.status}`);error.status=response.status;throw error}
 return result;
}
function adoptMasterBattle(battle){
 if(masterScene&&battle.revision<masterScene.revision)return {training,battle:masterScene};
 const changed=masterScene?.controller?.actorId!==battle.controller?.actorId;
 masterScene=battle;training=battle.training||null;
 data={character:{...training?.character,name:battle.controller?.name||training?.character?.name||'НПС',level:battle.controller?.level||1},spells:[],talentLibrary:[],combatQuickbar:battle.combatQuickbar||[]};
 if(changed){combatPicker='';quickbarEditing=0;if(typeof clearCombatAim==='function')clearCombatAim()}
 return {training,battle};
}
async function request(path,options={}){
 // Never send an admin credential to personal training/reset endpoints.
 const read=options.method===undefined||options.method==='GET';
 if(!read&&!path.endsWith('/training/action'))throw Error('Правки сцены доступны в администрировании.');
 let payload;
 if(!read){
  if(!masterScene?.controller?.canAct)throw Error('Сейчас ход игрока — мастер наблюдает.');
  payload={...JSON.parse(options.body||'{}'),mode:'play',operation:'act',actorId:masterScene.controller.actorId,revision:masterScene.revision};
 }
 const result=await masterFetch(masterBattlePath(),read?{}:{method:'POST',body:JSON.stringify(payload)});
 const adopted=adoptMasterBattle(result.battle);
 return {...result,...adopted,message:read?'':undefined};
}
async function mutate(path,body){
 if(path!=='combat-quickbar'||!masterScene?.controller?.canAct||combatBusy)return;
 setCombatBusy(true);
 try{
  const result=await masterFetch(masterBattlePath(),{method:'POST',body:JSON.stringify({...body,operation:'quickbar',mode:'play',actorId:masterScene.controller.actorId,revision:masterScene.revision})});
  adoptMasterBattle(result.battle);renderTraining($('#panel'),data.character);
 }catch(error){toast(error.message)}finally{setCombatBusy(false)}
}
