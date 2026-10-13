const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const handlers={},windowHandlers={},writes=[],notices=[],nodes=new Map();
const rect=(x,y,width,height)=>({x,y,left:x,top:y,width,height,right:x+width,bottom:y+height});
function node(key){
 if(!nodes.has(key))nodes.set(key,{dataset:{},style:{setProperty(){}},classList:{add(){},remove(){}},scrollLeft:0,scrollTop:0,clientWidth:600,clientHeight:400,getBoundingClientRect:()=>rect(0,0,600,400),addEventListener(){},querySelectorAll:()=>[],remove(){},setPointerCapture(){}});
 return nodes.get(key);
}
const scene={id:1,revision:1,name:'Бой',round:2,status:'active',currentId:'npc_1',map:{width:13,height:9,blocked:[{x:0,y:0}]},tokens:[{id:'npc_1',name:'НПС <X>',kind:'npc',team:'enemy',health:80,healthMax:100,x:4,y:3},{id:'pc_1',name:'Игрок',kind:'player',team:'party',health:20,healthMax:20,x:6,y:3}],initiative:[{id:'npc_1',name:'НПС <X>',total:15},{id:'pc_1',name:'Игрок',total:11}],conditions:{npc_1:{burn:{name:'Горение',until:4}}}};
const ctx=vm.createContext({console,Date,Map,Set,Math,Number,String,scene,writes,
 window:{innerWidth:1280,addEventListener(type,fn){(windowHandlers[type]??=[]).push(fn)}},
 document:{body:{},querySelector:s=>nodes.get(s)||null,querySelectorAll:()=>[],addEventListener(type,fn){(handlers[type]??=[]).push(fn)}},
 toast:m=>notices.push(m),esc:s=>String(s??'').replace(/</g,'&lt;').replace(/>/g,'&gt;'),battlePicture:()=>'<img>',battleEffectChips:()=>'<span>Горение 3р</span>',battleEffectNames:{stun:'Оглушение',burn:'Горение'},battleEffectDefaults:()=>({value:0,beneficial:false}),
 renderMasterBattle(){},battleSelectQuick:async()=>true,battleEdit:async payload=>{writes.push(payload);vm.runInContext(`masterBattle={...masterBattle,revision:masterBattle.revision+${ctx.conflict?2:1}}`,ctx);return true}});
vm.runInContext('let masterBattle=scene,battleToken="npc_1",battleCockpitMode="edit",battleRequestPending=false,battleZoom=48,battleTool="select",battleMoveMode=false,battlePlacementArmed=false,battleIndex={npcs:[{id:9}]},battleInspector="token",battleNewTeam="enemy"',ctx);
vm.runInContext(fs.readFileSync('web/admin-battle-tabletop.js','utf8'),ctx);
const run=s=>vm.runInContext(s,ctx),json=value=>JSON.parse(JSON.stringify(value));
for(const [input,expected] of [['-10',{delta:-10}],['−10',{delta:-10}],['+10',{delta:10}],['80',{health:80}],['=80',{health:80}],[' =0 ',{health:0}],['100000',{health:100000}]])assert.deepEqual(json(run(`battleHpCommand(${JSON.stringify(input)})`)),expected);
for(const input of ['',' ','1.5','1e2','Infinity','--1','+','-100001','100001','=+1','3 мусор'])assert.equal(run(`battleHpCommand(${JSON.stringify(input)})`),null,input);
assert.equal(run('battleGridDistance({x:0,y:0},{x:3,y:3})'),3,'Diagonal distance matches TacticalGrid.distance, not Euclidean length');
for(const [x,y,id,valid] of [[4,3,'npc_1',true],[6,3,'npc_1',false],[0,0,'npc_1',false],[-1,2,'npc_1',false],[13,2,'npc_1',false],[1.5,2,'npc_1',false],[8,5,'npc_1',true]])assert.equal(run(`battleFreeCell(${x},${y},'${id}')`),valid);
assert(run('battleCompactQueue()').includes('НПС &lt;X&gt;'));assert(run('battleCompactQueue()').includes('data-battle-mode="play"'));assert(run('battleTokenHud()').includes('−10 / +10 / =80'));
node('.battle-tabletop');node('[data-tabletop-undo]');
const viewport=node('.master-battle-viewport'),grid=node('.master-battle-grid');
grid.getBoundingClientRect=()=>rect(-viewport.scrollLeft,-viewport.scrollTop,13*run('battleZoom'),9*run('battleZoom'));
run('battleZoomTo(96,{x:240,y:180})');assert.equal(viewport.scrollLeft,240);assert.equal(viewport.scrollTop,180);assert.equal(run('battleZoom'),96);
run('battleZoomTo(999)');assert.equal(run('battleZoom'),112);run('battleZoomTo(1)');assert.equal(run('battleZoom'),16);
async function main(){
 await run('battleMoveToken("npc_1",6,3)');await run('battleMoveToken("npc_1",-1,3)');assert.equal(writes.length,0,'Occupied/outside moves do not write');
 await run('battleMoveToken("npc_1",8,5)');assert.deepEqual(json(writes[0]),{operation:'move',tokenId:'npc_1',x:8,y:5});assert.equal(run('battleMoveUndo.x'),4);assert.equal(run('battleMoveUndo.revision'),2);
 await run('battleEdit({operation:"health",tokenId:"npc_1",delta:-10})');assert.equal(run('battleMoveUndo'),null,'An intervening HP edit invalidates undo');
 run('battleRequestPending=true');await run('battleMoveToken("npc_1",8,5)');assert.equal(writes.length,2);
 run('battleRequestPending=false;battleCockpitMode="play"');await run('battleMoveToken("npc_1",8,5)');assert.equal(writes.length,2,'Editor cannot mutate during ordinary NPC turns');
 run('battleCockpitMode="edit";masterBattle.status="ended"');await run('battleMoveToken("npc_1",8,5)');assert.equal(writes.length,2);
 run('masterBattle.status="active"');
 // Ruler only changes presentation. Cancelling it cannot submit a move.
 run('battleGesture={kind:"ruler",pointer:1,scene:1,revision:masterBattle.revision,start:{x:1,y:1},end:{x:5,y:5},moved:true}');
 await handlers.pointerup[0]({pointerId:1});assert.equal(writes.length,2);assert.equal(run('battleGesture'),null);
 run('battleGesture={kind:"npc",pointer:2,scene:1,revision:masterBattle.revision,npcId:9,team:"enemy",end:{x:8,y:5},moved:true}');
 await handlers.pointerup[0]({pointerId:2,clientX:100,clientY:100});assert.deepEqual(json(writes.at(-1)),{operation:'add_npc',npcId:9,team:'enemy',x:8,y:5},'Archive pointer drag adds an independent NPC');
 run('battleGesture={kind:"npc",pointer:2,scene:1,revision:masterBattle.revision,npcId:9,team:"enemy",end:{x:6,y:3},moved:true}');
 await handlers.pointerup[0]({pointerId:2,clientX:100,clientY:100});assert.equal(writes.length,3,'Occupied NPC placement never writes');
 run('battleGesture={kind:"token",pointer:2,scene:1,revision:0,id:"npc_1",end:{x:8,y:5},moved:true}');
 await handlers.pointerup[0]({pointerId:2,clientX:100,clientY:100});assert.equal(writes.length,3,'A gesture against an older revision cannot move a token');
 ctx.conflict=true;await run('battleEdit({operation:"move",tokenId:"npc_1",x:8,y:5})');assert.equal(run('battleMoveUndo'),null,'A conflict retry cannot offer an undo with stale coordinates');
 const css=fs.readFileSync('web/battle-tabletop.css','utf8');assert(css.includes('@media(max-width:800px)'));assert(css.includes('top:auto'));assert(css.includes('touch-action:none'));
 const html=fs.readFileSync('web/admin.html','utf8');assert(html.indexOf('admin-battle-tabletop.js')>html.indexOf('admin-battle-cockpit.js'));
 console.log('GM tabletop: strict HP commands, game distance, occupied/bounds/pending/play/ended guards, anchored zoom, revision-scoped undo, read-only ruler and responsive layout OK');
}
main().catch(error=>{console.error(error);process.exitCode=1});
