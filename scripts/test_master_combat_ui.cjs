const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const calls=[],listeners={},nodes=new Map();
function node(selector){if(!nodes.has(selector))nodes.set(selector,{textContent:'',innerHTML:'',classList:{add(){},remove(){},toggle(){}},querySelector(){return null},querySelectorAll(){return []}});return nodes.get(selector)}
const first={id:1,name:'Поле',revision:4,status:'active',round:1,controller:{actorId:'npc_1',name:'Первый НПС',level:2,kind:'npc',canAct:true},combatQuickbar:[],training:{active:true,character:{name:'Первый НПС'},grid:{controllerId:'npc_1',tokens:[]},actions:[]}};
let response={battle:first};
const context=vm.createContext({URLSearchParams,encodeURIComponent,location:{search:'?api=http://localhost:8768&battle=1',hash:'#token=qa-admin'},localStorage:{getItem(){return ''}},
 document:{hidden:false,querySelector:node,addEventListener(type,fn){(listeners[type]??=[]).push(fn)}},
 setInterval(){},setTimeout(){},clearTimeout(){},fetch:async(path,options)=>{calls.push({path,options});return {ok:true,json:async()=>response}},
 renderTraining(){},animateTokenMovement(){},combatHealthChanges(){return [{delta:5}]},combatBusy:false,setCombatBusy(value){context.combatBusy=value},clearCombatAim(){context.cleared=true},showCombatAim(){},armedCombatAction:null,combatAim:null});
vm.runInContext(fs.readFileSync('web/master-combat-runtime.js','utf8'),context);
vm.runInContext(fs.readFileSync('web/master-combat.js','utf8'),context);
async function main(){
 vm.runInContext('adoptMasterBattle(testBattle)',Object.assign(context,{testBattle:first}));
 const editorUrl=new URL(vm.runInContext('masterAdministrationUrl()',context),'http://localhost/');
 assert.equal(editorUrl.searchParams.get('battle'),'1');assert.equal(editorUrl.searchParams.get('actor'),'npc_1');assert.equal(editorUrl.hash,'#token=qa-admin');
 await vm.runInContext('request("/api/portal/qa-admin/training/action",{method:"POST",body:JSON.stringify({kind:"move",x:3,y:4,actorId:"npc_99",mode:"edit"})})',context);
 assert(calls[0].path.includes('/api/admin/qa-admin/battles/1?mode=play'));
 assert.deepEqual(JSON.parse(calls[0].options.body),{kind:'move',x:3,y:4,actorId:'npc_1',mode:'play',operation:'act',revision:4});
 await assert.rejects(vm.runInContext('request("/api/portal/qa-admin/training/reset",{method:"POST"})',context));
 assert.equal(calls.length,1,'Admin credentials must not be sent to training/reset');
 vm.runInContext('combatPicker="ability";quickbarEditing=3',context);
 const next={...first,revision:5,controller:{...first.controller,actorId:'npc_2',name:'Второй НПС'},training:{...first.training,grid:{controllerId:'npc_2',tokens:[]}}};context.nextBattle=next;
 vm.runInContext('adoptMasterBattle(nextBattle)',context);
 assert.equal(vm.runInContext('combatPicker',context),'');assert.equal(vm.runInContext('quickbarEditing',context),0);assert(context.cleared);
 vm.runInContext('adoptMasterBattle(testBattle)',context);
 assert.equal(vm.runInContext('masterScene.revision',context),5,'Late polls must not roll the scene back');
 assert.equal(vm.runInContext('combatHealthChanges({controllerId:"npc_1"},{controllerId:"npc_2"}).length',context),0);
 const waiting={...next,revision:6,controller:{actorId:'pc_1',name:'Игрок',kind:'player',canAct:false}};context.waiting=waiting;
 vm.runInContext('adoptMasterBattle(waiting);updateMasterTurn()',context);assert(node('#master-turn').textContent.includes('Ход игрока'));
 await assert.rejects(vm.runInContext('request("/api/portal/qa-admin/training/action",{method:"POST",body:"{}"})',context));
 assert.equal(calls.length,1);
 const html=fs.readFileSync('web/master-combat.html','utf8'),admin=fs.readFileSync('web/admin-battles.js','utf8');
 for(const file of ['combat-base.js','combat-ui.js','combat-feedback.js','combat-tactics.js'])assert(html.includes(file));
 assert(!html.includes('src="archive.js'));assert(!html.includes('battle-health'));assert(!admin.includes('<h3>Способности</h3>'));
 assert(admin.includes('data-battle-delete'));assert(admin.includes("method:'DELETE'"));assert(admin.includes('revision:battle.revision'));assert(admin.includes('admin-ready'));
 console.log('Master combat: shared HUD, turn-only authority, polling race, actor swap, admin return and confirmed deletion OK');
}
main().catch(error=>{console.error(error);process.exitCode=1});
