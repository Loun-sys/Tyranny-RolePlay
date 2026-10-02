// Browser-independent regression tests for the capture handlers and targeting flow.
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const handlers={},messages=[],requests=[];
const context=vm.createContext({
 document:{addEventListener(type,handler){(handlers[type]??=[]).push(handler)},querySelector(){return null},querySelectorAll(){return []}},
 renderTraining(){},combatPickerPanel(){return ''},tab:'training',combatPicker:'',quickbarEditing:0,
 data:{character:{name:'QA'}},token:'isolated-qa',encodeURIComponent,
 toast(message){messages.push(message)},$:()=>({}),
 request:async(path,options)=>{requests.push(JSON.parse(options.body));return {training:{active:true,turn:{actionAvailable:false}},message:'OK'}},
 training:{active:true,turn:{actionAvailable:true},grid:{tokens:[{id:'player',x:2,y:4,team:'player'},{id:'dummy_left',x:10,y:2,team:'enemy'}]},actions:[]},
});
vm.runInContext(fs.readFileSync('web/combat-ui.js','utf8'),context);
const action={kind:'spell',name:'QA spell',range:10,remaining:0,targeting:'area',aims:{'10:2':{valid:true,cells:[{x:10,y:2}]},'0:0':{valid:false,cells:[]}}};
context.testAction=action;
vm.runInContext('training.actions=[testAction];renderTraining=()=>{};showCombatAim=()=>{};playCombatEffect=()=>{};',context);
function click(target){const event={target,preventDefault(){this.prevented=true},stopImmediatePropagation(){this.stopped=true}};handlers.click[0](event);return event}
async function main(){
 const button={disabled:false,dataset:{trainingKind:'spell',trainingName:action.name},matches(){return false}};
 const event=click({closest(selector){return selector==='[data-training-kind]'?button:null}});
 assert(event.stopped);assert.equal(requests.length,0,'Selecting a spell must never POST an action');
 assert.equal(vm.runInContext('armedCombatAction.name',context),action.name);
 await vm.runInContext('confirmCombatAim({x:0,y:0})',context);
 assert.equal(requests.length,0,'Invalid aiming must never POST');
 await vm.runInContext('confirmCombatAim({x:10,y:2})',context);
 assert.equal(requests.length,1);assert.equal(requests[0].targetId,'dummy_left');
 assert.equal(requests[0].x,10);assert.equal(requests[0].y,2);
 assert.equal(vm.runInContext('armedCombatAction',context),null);
 context.training={active:true,turn:{actionAvailable:true}};
 vm.runInContext('armedCombatAction=testAction;combatAim={x:10,y:2}',context);
 handlers.keydown[0]({key:'Escape',preventDefault(){}});
 assert.equal(vm.runInContext('armedCombatAction',context),null);
 assert.equal(requests.length,1,'Cancel must never POST');
 vm.runInContext('armedCombatAction=testAction',context);
 const cancel={target:{closest(){return true}},preventDefault(){},stopImmediatePropagation(){}};
 handlers.contextmenu[0](cancel);
 assert.equal(vm.runInContext('armedCombatAction',context),null);
 console.log('Combat UI: selection, invalid aim, explicit confirmation, target ID, Esc and right-click OK');
}
main().catch(error=>{console.error(error);process.exitCode=1});
