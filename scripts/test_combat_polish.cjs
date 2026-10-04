const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const handlers={},messages=[],requests=[],bindings=[];
const screen={setAttribute(name,value){this[name]=value}},map={style:{}},viewport={style:{},scrollLeft:100,scrollTop:60,clientWidth:400,clientHeight:200},label={};
const panel={querySelector(selector){return selector==='.tactical-map'?map:selector==='.tactical-map-wrap'?viewport:selector==='.combat-zoom-value'?label:null},querySelectorAll(){return []}};
const context=vm.createContext({
 document:{addEventListener(type,handler){(handlers[type]??=[]).push(handler)},querySelector:s=>s==='.combat-game-screen'?screen:null,querySelectorAll:()=>[]},
 renderTraining(){},loadTraining(){},combatPickerPanel(){return ''},combatActionButton:x=>x.name,statsBox(){return ''},localTalentIcon:x=>x,sigilIcon(){return ''},
 tab:'training',combatPicker:'',quickbarEditing:0,data:{character:{name:'QA'}},token:'qa',encodeURIComponent,
 esc:String,toast:x=>messages.push(x),$:()=>panel,quickbarAction:(slot,actions)=>actions[slot-1],mutate:(path,body)=>bindings.push(body),
 training:{active:true,turn:{actionAvailable:false},grid:{width:13,height:9,tokens:[{id:'player',team:'player',x:2,y:2},{id:'friend',team:'ally',x:3,y:2}]},actions:[]},
});
vm.runInContext(fs.readFileSync('web/combat-ui.js','utf8'),context);
context.testOriginalVFX=vm.runInContext('playCombatEffect',context);
vm.runInContext('renderTraining=()=>{};showCombatAim=()=>{};animateTokenMovement=async()=>{};playCombatEffect=async()=>{}',context);
context.song={kind:'ability',name:'Песня',song:{type:1},targeting:'self',aims:{'2:2':{valid:true,cells:[]}}};
context.potion={kind:'item',name:'Зелье',freeOnSelf:true,aims:{'2:2':{valid:true,cells:[]},'3:2':{valid:true,cells:[]}}};
context.heal={kind:'spell',name:'Лечение',targetTeam:'ally',aims:{'3:2':{valid:true,cells:[]}}};
context.request=async(path,options)=>{requests.push(JSON.parse(options.body));if(context.failRequest)throw Error('Сеть недоступна');return {training:context.training,message:'OK'}};
function run(code){return vm.runInContext(code,context)}
function key(key,extra={}){const e={key,target:{matches:()=>false,closest:()=>null},preventDefault(){this.prevented=true},stopImmediatePropagation(){this.stopped=true},...extra};handlers.keydown[0](e);return e}
async function main(){
 assert.equal(run('combatActionBlock(song)'),'', 'Songs stay available after the main action is spent');
 assert.equal(run('combatActionBlock(potion)'),'', 'Self consumables can still be aimed');
 assert.equal(run('combatActionBlock(heal)'),'Основное действие потрачено');
 context.rangeAction={kind:'attack',disabledReason:'Цель вне дальности: 9/1 м'};
 context.training.turn.actionAvailable=true;assert.equal(run('combatActionBlock(rangeAction)'),'', 'A distant selected target does not prevent selecting a different target');
 context.training.turn.actionAvailable=false;
 run('armCombatAction(song)');assert.equal(run('armedCombatAction.name'),'Песня');
 await run('confirmCombatAim({x:2,y:2})');assert.equal(requests[0].targetId,'player');assert.equal(screen['aria-busy'],'false');
 run('armCombatAction(potion)');await run('confirmCombatAim({x:3,y:2})');assert.equal(requests.length,1,'Applying to an ally is not free');
 context.training.turn.actionAvailable=true;run('armCombatAction(heal)');await run('confirmCombatAim({x:3,y:2})');assert.equal(requests[1].targetId,'friend','Ally target ID must be sent, not filtered as an enemy');
 context.failRequest=true;run('armCombatAction(heal)');await run('confirmCombatAim({x:3,y:2})');assert.equal(run('combatBusy'),false);assert.equal(run('armedCombatAction.name'),'Лечение','Network error preserves the selected action for retry');context.failRequest=false;
 context.training.actions=Array.from({length:9},(_,i)=>({...context.heal,name:'Кнопка '+(i+1)}));
 let event=key('9');assert(event.stopped);assert.equal(run('armedCombatAction.name'),'Кнопка 9');
 run('clearCombatAim()');key('1',{ctrlKey:true});assert.equal(run('armedCombatAction'),null);
 key('1',{target:{matches:()=>true,closest:()=>null}});assert.equal(run('armedCombatAction'),null,'Typing a digit in an input cannot select an attack');
 context.combatPicker='spell';key('Escape');assert.equal(context.combatPicker,'');
 const slot={dataset:{quickSlot:'2'},classList:{remove(){}}};
 async function drop(payload){await handlers.drop[0]({target:{closest:()=>slot},dataTransfer:{getData:()=>JSON.stringify(payload)},preventDefault(){},stopImmediatePropagation(){}})}
 await drop({kind:'ability',name:'Не существующее умение'});assert.equal(bindings.length,0);
 await drop({kind:'spell',name:'Кнопка 1',sourceSlot:9});assert.equal(bindings.length,0,'Stale source slots cannot swap the wrong action');
 await drop({kind:'spell',name:'Кнопка 1',sourceSlot:1});assert.equal(bindings.length,1);assert.equal(bindings[0].bindings[0].name,'Кнопка 2');assert.equal(bindings[0].bindings[1].name,'Кнопка 1');
 context.zoomEvent={target:{closest:()=>({dataset:{combatZoom:'in'}})},preventDefault(){},stopImmediatePropagation(){}};
 run('handleCombatMapZoom(zoomEvent)');assert.equal(viewport.scrollLeft,160);assert.equal(viewport.scrollTop,92,'Zoom must preserve the viewed center, not jump to the top-left');
 handlers.pointerdown[0]({button:1,target:{closest:()=>viewport},clientX:100,clientY:100,preventDefault(){}});
 handlers.pointermove[0]({clientX:140,clientY:120,preventDefault(){}});assert.equal(viewport.scrollLeft,120);assert.equal(viewport.scrollTop,72);
 handlers.pointerup[0]();assert.equal(viewport.style.cursor,'');
 viewport.clientWidth=400;viewport.clientHeight=360;
 run('combatFitMapKey="";combatZoomManual=false;fitCombatMap($("#panel"),training)');
 assert(Math.abs(run('combatMapZoom')-398/624)<1e-8,'Initial fit honors the real viewport width');
 assert.equal(viewport.scrollLeft,0);assert.equal(viewport.scrollTop,0);
 viewport.clientWidth=600;run('handleCombatViewportResize()');assert(Math.abs(run('combatMapZoom')-332/432)<1e-8,'Automatic resize honors viewport height minus footer');
 const automatic=run('combatMapZoom');viewport.clientHeight=400;run('fitCombatMap($("#panel"),training)');assert.equal(run('combatMapZoom'),automatic,'Action rerenders do not make automatic fit drift with footer height');
 context.zoomEvent.target.closest=()=>({dataset:{combatZoom:'in'}});run('handleCombatMapZoom(zoomEvent)');const chosen=run('combatMapZoom');
 viewport.clientWidth=320;viewport.clientHeight=280;run('handleCombatViewportResize()');assert.equal(run('combatMapZoom'),chosen,'Resizing preserves manually chosen zoom');
 run('fitCombatMap($("#panel"),training)');assert.equal(run('combatMapZoom'),chosen,'Action rerender cannot reset a manual zoom');
 context.training.grid.name='Другая карта';run('fitCombatMap($("#panel"),training)');assert.equal(run('combatZoomManual'),false);assert(Math.abs(run('combatMapZoom')-318/624)<1e-8,'Switching maps restores automatic fit');
 viewport.clientWidth=40;viewport.clientHeight=40;run('handleCombatViewportResize()');assert.equal(run('combatMapZoom'),.5,'Automatic fit respects the 50% floor');
 let mapScrolls=0;viewport.scrollIntoView=()=>{mapScrolls++};viewport.getBoundingClientRect=()=>({top:100,bottom:400});context.innerHeight=800;
 context.document.querySelector=s=>s==='.tactical-map-wrap'?viewport:null;run('ensureCombatMapVisible()');assert.equal(mapScrolls,0,'Visible desktop maps are not scrolled unnecessarily');
 viewport.getBoundingClientRect=()=>({top:-500,bottom:-200});run('ensureCombatMapVisible()');assert.equal(mapScrolls,1,'Closing a long palette returns the user to an offscreen map');
 let casterFrames=null,cancelled=0;
 const layer={style:{setProperty(){}},isConnected:true,getBoundingClientRect:()=>({width:650,height:450}),append(){}},caster={animate(frames){casterFrames=frames;return {finished:Promise.resolve(),cancel(){cancelled++}}}};
 context.document.querySelector=s=>s==='.combat-vfx-layer'?layer:s.endsWith('.combat-token')?caster:null;
 context.document.createElement=()=>({style:{},remove(){},animate(){return {finished:Promise.resolve()}}});
 context.matchMedia=()=>({matches:false});
 context.vfxGrid={width:13,height:9,tokens:[{id:'player',x:2,y:2}]};
 await run('testOriginalVFX({kind:"attack",range:1},{x:3,y:2},vfxGrid,[])');
 assert.equal(casterFrames[0].transform,'translate(-50%,-50%)');assert.equal(casterFrames[2].transform,'translate(-50%,-50%)');assert(casterFrames[1].transform.includes('calc(-50% +'));
 assert.equal(cancelled,1,'Casting animation restores CSS transforms after completion');
 casterFrames=null;context.matchMedia=()=>({matches:true});await run('testOriginalVFX({kind:"attack",range:1},{x:3,y:2},vfxGrid,[])');assert.equal(casterFrames,null,'Reduced motion never bounces the caster token');
 assert(messages.includes('Сеть недоступна'));
 console.log('Combat polish: free songs, self/ally consumables, ally targeting, keyboard safety, atomic validated drop, retry after failure, centered zoom, map panning and centered/reduced-motion VFX OK');
}
main().catch(error=>{console.error(error);process.exitCode=1});
