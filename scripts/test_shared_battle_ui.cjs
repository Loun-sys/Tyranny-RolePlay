const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const calls=[],intervals=[],panel={innerHTML:'',querySelector(){return null},querySelectorAll(){return []}},tabs={querySelector(){return null},insertAdjacentHTML(_,html){this.html=html}};
const context=vm.createContext({q:new URLSearchParams(''),encodeURIComponent,token:'test',api:'test',data:{character:{name:'Hero'}},
 training:null,tab:'development',combatBusy:false,renderTab(){},renderTraining(){},request:async(path,opts)=>{calls.push([path,opts]);return {battle:{id:1,revision:2,status:'lobby',participants:{1:{name:'Hero',joined:true}},training:{active:true}}}},
 document:{addEventListener(){},querySelector:s=>s==='#tabs'?tabs:null,activeElement:null},$:()=>panel,toast(){},esc:x=>String(x),setInterval(fn){intervals.push(fn)},animateTokenMovement(){}});
vm.runInContext(fs.readFileSync('web/player-battle.js','utf8'),context);
vm.runInContext('ensureBattleTab()',context);assert(tabs.html.includes('data-tab="battle"'));
async function main(){
 vm.runInContext('sharedBattleMode=true;sharedBattleId=1;sharedBattle={revision:1}',context);
 const j=await vm.runInContext('request("/api/portal/test/training/action",{method:"POST",body:JSON.stringify({kind:"tactic",name:"Спринт"})})',context);
 assert(calls[0][0].includes('/battles/1'));assert.equal(JSON.parse(calls[0][1].body).revision,1);assert(j.training.active);
 await assert.rejects(vm.runInContext('request("/api/portal/test/training/reset",{method:"POST"})',context));
 assert.equal(calls.length,1,'Player cannot finish or reset the shared battle');
 vm.runInContext('renderSharedBattle()',context);assert(panel.innerHTML.includes('сбор участников'));
 vm.runInContext('sharedBattleMode=false',context);
 await vm.runInContext('request("/api/portal/test/training/action")',context);assert(calls[1][0].endsWith('/training/action'));
 const admin=fs.readFileSync('web/admin-battles.js','utf8');
 for(const operation of ['place_player','add_npc','move','health','effect','remove_effect','order','turn','refresh_turn','start','finish','remove_token'])assert(admin.includes(operation),operation);
 assert(admin.includes('revision:masterBattle.revision'));
 const masterCalls=[];
 const masterContext=vm.createContext({document:{querySelector(){return null},querySelectorAll(){return []},addEventListener(){}},setInterval(){},encodeURIComponent,
  base:()=>'/api/admin/test',toast(){},request:async(path,opts)=>{masterCalls.push([path,opts]);if(opts&&masterCalls.length===1)throw Error('Бой изменился. Обновите экран.');return {battle:{id:1,revision:opts?3:2,tokens:[]},message:'OK'}}});
 vm.runInContext(admin,masterContext);vm.runInContext('masterBattle={id:1,revision:1,tokens:[]};renderMasterBattle=()=>{}',masterContext);
 await vm.runInContext('battleEdit({operation:"add_npc",npcId:1,x:9,y:6})',masterContext);
 assert.equal(masterCalls.length,3);assert.equal(masterCalls[1][1],undefined);assert.equal(JSON.parse(masterCalls[2][1].body).revision,2);
 console.log('Shared battle UI: runtime boot, tab, authenticated routes, revision, no player reset and master controls OK');
}
main().catch(e=>{console.error(e);process.exitCode=1});
