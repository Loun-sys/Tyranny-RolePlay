const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const handlers={},windowHandlers={},nodes=new Map(),writes=[],messages=[],notices=[];
function node(id){if(!nodes.has(id))nodes.set(id,{id,dataset:{},style:{},disabled:false,value:'',scrollLeft:0,scrollTop:0,clientWidth:800,clientHeight:400,classList:{add(){},remove(){},contains(){return false}},querySelectorAll(){return []},querySelector(){return null},setAttribute(){},removeAttribute(){},matches(){return false}});return nodes.get(id)}
const scene={id:1,revision:4,name:'Поле <опасное>',status:'active',round:2,currentId:'npc_1',participants:{1:{name:'Игрок',joined:true}},map:{width:13,height:9,image:'',blocked:[{x:0,y:0}],sightBlocked:[],cover:[]},conditions:{npc_1:{shield:{name:'Щит',value:20,until:3}}},log:[],initiative:[{id:'npc_1',name:'Разбойник',total:15},{id:'pc_1',name:'Игрок',total:12}],tokens:[{id:'npc_1',name:'Разбойник',kind:'npc',team:'enemy',health:50,healthMax:100,x:6,y:4},{id:'pc_1',name:'Игрок',kind:'player',team:'party',health:80,healthMax:100,x:2,y:4}],training:{viewerId:'npc_1',turn:{actionAvailable:false,movementRemaining:2},actions:[]}};
const ctx=vm.createContext({URLSearchParams,URL,Map,Set,encodeURIComponent,api:'http://qa',token:'qa-only',params:new URLSearchParams(''),roster:[],scene,writes,
 window:{innerWidth:1280,addEventListener(type,fn){windowHandlers[type]=fn}},location:{origin:'http://qa',href:'http://qa/admin.html#token=qa-only'},
 document:{activeElement:null,hidden:false,querySelector:selector=>nodes.get(selector)||null,querySelectorAll(){return []},getElementById:id=>nodes.get('#'+id)||null,createElement:tag=>({tag,append(){},setAttribute(){}}),addEventListener(type,fn,capture){(handlers[type]??=[]).push({fn,capture})}},
 $:id=>node(id),esc:s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])),base:()=>'/admin/qa',setInterval(){},campaignWorkspace(html){ctx.html=html},toast:msg=>notices.push(msg),confirm(){return true},request:async()=>({battle:{...scene,revision:5},message:'OK'})});
vm.runInContext(fs.readFileSync('web/admin-battles.js','utf8'),ctx);
vm.runInContext(fs.readFileSync('web/admin-battle-cockpit.js','utf8'),ctx);
vm.runInContext('battleIndex={npcs:[{id:9,spec:{name:"Ратник",healthMax:120}}],maps:[],battles:[]};battleAdopt(scene);renderMasterBattle()',ctx);
assert(ctx.html.includes('Поле &lt;опасное&gt;'));assert(ctx.html.includes('data-battle-current'));assert(ctx.html.includes('data-battle-quick-effect="shield"'));assert(ctx.html.includes('Действие потрачено'));assert(ctx.html.includes('Движение: 2 клеток'));assert(ctx.html.includes('data-battle-inspector="list"'));assert(!ctx.html.includes('data-training-kind'));
vm.runInContext('battleInspector="add";battleTool="add_npc";renderMasterBattle()',ctx);assert(ctx.html.includes('data-battle-arm-placement'));assert(!ctx.html.includes('id="battle-place-player"'),'Only the chosen type of placement is shown');
const click=handlers.click.findLast(h=>h.capture).fn;
function event(dataset,extras={}){const button={dataset,disabled:false,hasAttribute(key){return key==='data-battle-arm-placement'&&dataset.arm}};return {target:{closest:selector=>selector==='button'?button:null},preventDefault(){this.stopped=true},stopImmediatePropagation(){this.stopped=true},...extras}}
async function main(){
 vm.runInContext('battleEdit=async payload=>writes.push(payload);battlePlacementArmed=true;battleNpcChoice="9"',ctx);
 await click(event({masterBattleCell:'10:4'}));await click(event({masterBattleCell:'10:6'}));
 assert.equal(writes.length,2);assert.deepEqual(JSON.parse(JSON.stringify(writes[0])),{operation:'add_npc',npcId:9,team:'enemy',x:10,y:4});assert.equal(vm.runInContext('battlePlacementArmed',ctx),true);
 await click(event({masterBattleCell:'6:4'}));assert.equal(writes.length,2,'Occupied cells never add or overwrite a token');
 vm.runInContext('battlePlacementArmed=false;battleInspector="token";battleToken="npc_1"',ctx);
 await click(event({battleQuickEffect:'guard',value:'1.2'}));assert.equal(writes[2].value,1.2);assert.equal(writes[2].rounds,1);assert.equal(writes[2].beneficial,true);
 await click(event({masterBattleCell:'9:5'},{shiftKey:true}));assert.equal(writes[3].operation,'move');
 vm.runInContext('battleRequestPending=true',ctx);await click(event({masterBattleCell:'9:6'},{shiftKey:true}));assert.equal(writes.length,4);
 vm.runInContext('battleRequestPending=false;battleCockpitMode="play"',ctx);
 const modeEvent=event({battleMode:'edit'});const frame=node('#battle-play-frame');frame.contentWindow={postMessage:message=>messages.push(message)};
 await click(modeEvent);assert.equal(messages[0].type,'tyranny-master-pause');assert.equal(vm.runInContext('battleCockpitMode',ctx),'play','Wait for the child to acknowledge pausing before unloading');
 await windowHandlers.message({source:{},origin:'http://qa',data:{type:'tyranny-master-paused'}});assert.equal(vm.runInContext('battleCockpitMode',ctx),'play','Unrelated message source cannot switch modes');
 await windowHandlers.message({source:frame.contentWindow,origin:'http://malicious',data:{type:'tyranny-master-paused'}});assert.equal(vm.runInContext('battleCockpitMode',ctx),'play');
 ctx.fresh=false;vm.runInContext('loadMasterBattle=async()=>{fresh=true}',ctx);
 frame.parentElement={remove(){assert(ctx.fresh,'Fetch the latest turn before removing the paused HUD')}};
 await windowHandlers.message({source:frame.contentWindow,origin:'http://qa',data:{type:'tyranny-master-paused'}});assert.equal(vm.runInContext('battleCockpitMode',ctx),'edit');
 vm.runInContext('battleCockpitMode="edit"',ctx);
 const drop=handlers.drop.at(-1).fn;
 await drop({target:{closest:()=>({dataset:{battleOrderId:'npc_1'}})},dataTransfer:{getData:()=> 'pc_1'},preventDefault(){}});
 assert.deepEqual(Array.from(writes.at(-1).order),['pc_1','npc_1']);assert.equal(vm.runInContext('masterBattle.currentId',ctx),'npc_1','Reordering never changes the active actor');
 const key=handlers.keydown.at(-1).fn;let prevented=false;
 key({key:'m',target:{matches(){return true}},preventDefault(){prevented=true}});assert(!prevented,'Typing in inputs never triggers shortcuts');
 vm.runInContext('battlePlacementArmed=true',ctx);key({key:'Escape',target:{matches(){return false}},preventDefault(){}});assert.equal(vm.runInContext('battlePlacementArmed',ctx),false);assert.equal(vm.runInContext('battleTool',ctx),'select');
 const editor=node('.master-battle-editor');editor.dataset={scene:'1',actor:'npc_1'};
 const folds=[{dataset:{battleFold:'custom-effect'},open:true}],effect={id:'battle-effect-value',value:'17',type:'number'};
 editor.querySelectorAll=selector=>selector==='[data-battle-fold]'?folds:[effect];
 vm.runInContext('battleCaptureForms()',ctx);assert.equal(vm.runInContext('battleFormDrafts.get("npc_1:battle-effect-value")',ctx),'17');
 editor.dataset.scene='99';effect.value='888';vm.runInContext('battleCaptureForms()',ctx);assert.equal(vm.runInContext('battleFormDrafts.get("npc_1:battle-effect-value")',ctx),'17','Drafts from another scene never leak');
 console.log('Battle cockpit: unified inspector, repeat placement, occupied-cell safety, quick effects, shift-move, pending guards, authenticated mode handshake, shortcuts and scoped drafts OK');
}
main().catch(error=>{console.error(error);process.exitCode=1});
