const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const handlers={},nodes=new Map(),calls=[],toasts=[];
function node(selector){if(!nodes.has(selector))nodes.set(selector,{value:'',textContent:'',style:{},scrollTop:0,scrollLeft:0,clientWidth:800,clientHeight:400,dataset:{},disabled:false,classList:{add(){},remove(){}},setAttribute(){},matches(){return false}});return nodes.get(selector)}
const scene={id:1,revision:4,name:'Поле <опасное>',status:'active',round:2,currentId:'npc_1',participants:{1:{name:'Игрок',joined:true}},
 map:{width:13,height:9,image:'',blocked:[{x:0,y:0}],sightBlocked:[],cover:[],tokens:[]},conditions:{},log:['Разбойник ходит'],
 initiative:[{id:'npc_1',name:'Разбойник',total:15},{id:'pc_1',name:'Игрок',total:12}],
 tokens:[{id:'npc_1',name:'Разбойник',kind:'npc',team:'enemy',health:50,healthMax:100,x:6,y:4},{id:'pc_1',name:'Игрок',kind:'player',team:'party',health:80,healthMax:100,x:2,y:4}],
 training:{viewerId:'npc_1',turn:{actionAvailable:false,movementRemaining:2},actions:[{kind:'ability',name:'Удар',disabledReason:'Действие потрачено'}]}};
const context=vm.createContext({encodeURIComponent,Set,URLSearchParams,api:'http://qa',token:'qa-only',params:new URLSearchParams(''),roster:[],
 document:{activeElement:null,hidden:false,querySelector:selector=>selector==='.admin-top>div'?null:node(selector),querySelectorAll(){return []},addEventListener(type,fn){(handlers[type]??=[]).push(fn)}},
 $:node,esc:s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])),base:()=>'/admin/qa',setInterval(){},
 campaignWorkspace(html){context.html=html},toast(message){toasts.push(message)},confirm(){return true},
 request:async(path,options)=>{calls.push([path,options]);return {battle:{...scene,revision:5},message:'OK'}}});
vm.runInContext(fs.readFileSync('web/admin-battles.js','utf8'),context);
context.scene=scene;vm.runInContext('battleIndex={npcs:[],maps:[],battles:[]};battleAdopt(scene);renderMasterBattle()',context);
assert(context.html.includes('ХОДЫ ПО ИНИЦИАТИВЕ'));
assert(context.html.includes('Поле &lt;опасное&gt;'));
assert(context.html.includes('data-battle-fit'));assert(context.html.includes('data-battle-focus'));
assert(context.html.includes('Действие потрачено'));assert(context.html.includes('Движение: 2 клеток'));
assert(!context.html.includes('data-training-kind'),'No player-like attacks in editor overrides');
assert.equal(vm.runInContext('masterBattle.currentId',context),'npc_1');
vm.runInContext('battleInspector="effects";renderMasterBattle()',context);assert(context.html.includes('data-battle-effect-preset="guard"'));
assert.equal(vm.runInContext('battleEffectDefaults("guard").value',context),1.2);
assert(vm.runInContext('battleEffectDefaults("shield").beneficial',context));assert(!vm.runInContext('battleEffectDefaults("burn").beneficial',context));
assert(context.html.includes('id="battle-effect-beneficial"'));
assert.equal(vm.runInContext('battleChooseCell(0,0)',context),false);
assert.equal(vm.runInContext('battleChooseCell(9,4)',context),true);
assert.equal(node('#battle-place-x').value,9);
vm.runInContext('battleTokenKind="player"',context);assert(!vm.runInContext('battleRosterRows()',context).includes('Разбойник'));
vm.runInContext('battleTokenKind="all";battleTokenQuery="разб"',context);assert(!vm.runInContext('battleRosterRows()',context).includes('Игрок'));
node('.master-battle-viewport').scrollLeft=120;node('.master-battle-viewport').scrollTop=60;
vm.runInContext('battleZoomTo(96)',context);assert.equal(node('.master-battle-viewport').scrollLeft,640);assert.equal(node('.master-battle-viewport').scrollTop,320);
node('#battle-health-delta').value='1000';
async function main(){
 await vm.runInContext('battleApplyHealthDelta(-1)',context);
 assert.deepEqual(JSON.parse(calls[0][1].body),{operation:'health',tokenId:'npc_1',delta:-1000,revision:4});
 node('#battle-health-delta').value='';await vm.runInContext('battleApplyHealthDelta(1)',context);assert.equal(calls.length,1,'Blank input must never become zero');
 context.stale={...scene,revision:1};assert.equal(vm.runInContext('battleAdopt(stale)',context),false);
 const click=handlers.click[0];let prevented=false;
 vm.runInContext('battleRequestPending=true',context);
 await click({target:{closest:selector=>selector==='.battle-play-link'?{}:null},preventDefault(){prevented=true}});
 assert(prevented,'Mode switch cannot interrupt a pending edit');
 const css=fs.readFileSync('web/battle.css','utf8');assert(css.includes(':has(.master-battle-editor)'));assert(css.includes('@media(max-width:800px)'));
 console.log('Battle editor: modes, escaped names, token filters, map placement, centered zoom, relative HP, pending guards and unchanged initiative OK');
}
main().catch(error=>{console.error(error);process.exitCode=1});
