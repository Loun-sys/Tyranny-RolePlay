// Browser-independent regression tests for the capture handlers and targeting flow.
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const handlers={},messages=[],requests=[],bindings=[];
const context=vm.createContext({
 document:{addEventListener(type,handler){(handlers[type]??=[]).push(handler)},querySelector(){return null},querySelectorAll(){return []}},
 renderTraining(){},loadTraining(){},combatPickerPanel(){return ''},combatActionButton:x=>x.name,statsBox(){return ''},localTalentIcon:url=>'assets/talent-icons/'+url,sigilIcon(){return ''},tab:'training',combatPicker:'',quickbarEditing:0,
 data:{character:{name:'QA'}},token:'isolated-qa',encodeURIComponent,
 toast(message){messages.push(message)},$:()=>({}),
 esc:value=>String(value),mutate(path,body){bindings.push(body)},quickbarAction(slot,actions){return actions[slot-1]},
 request:async(path,options)=>{requests.push(JSON.parse(options.body));return {training:{active:true,turn:{actionAvailable:false}},message:'OK'}},
 training:{active:true,turn:{actionAvailable:true},grid:{tokens:[{id:'player',x:2,y:4,team:'player'},{id:'dummy_left',x:10,y:2,team:'enemy'}]},actions:[]},
});
vm.runInContext(fs.readFileSync('web/combat-ui.js','utf8'),context);
const action={kind:'spell',name:'QA spell',range:10,remaining:0,targeting:'area',aims:{'10:2':{valid:true,cells:[{x:10,y:2}]},'0:0':{valid:false,cells:[]}}};
context.testAction=action;
vm.runInContext('training.actions=[testAction];renderTraining=()=>{};showCombatAim=()=>{};playCombatEffect=()=>{};',context);
function click(target){const event={target,preventDefault(){this.prevented=true},stopImmediatePropagation(){this.stopped=true}};handlers.click[0](event);return event}
async function main(){
 // A master's cell size must control BOTH axes; legacy min-height stretched rows.
 const map={style:{setProperty(){}},closest(){return null},querySelector(){return null}};
 context.layoutPanel={querySelector(){return map}};
 for(const size of [32,48,60,96]){
  context.layoutTraining={grid:{source:'Карта мастера',width:13,height:9,layout:{cellSize:size},tokens:[]}};
  vm.runInContext('renderPersistentAreas(layoutPanel,layoutTraining)',context);
  assert.equal(map.style.width,`${13*size}px`);
  assert.equal(map.style.height,`${9*size}px`);
  assert.equal(map.style.minHeight,'0');
 }
 context.pickerActions={actions:[{kind:'spell',name:'ONLY SPELL'},{kind:'ability',name:'ONLY ABILITY'}]};
 vm.runInContext('combatPicker="ability"',context);
 const abilities=vm.runInContext('combatPickerPanel(pickerActions)',context);
 assert(abilities.includes('ONLY ABILITY'));assert(!abilities.includes('ONLY SPELL'));
 assert(!abilities.includes('В ячейку:'));
 vm.runInContext('combatPicker="spell"',context);
 const spells=vm.runInContext('combatPickerPanel(pickerActions)',context);
 assert(spells.includes('ONLY SPELL'));assert(!spells.includes('ONLY ABILITY'));
 const inner={closest:selector=>selector==='[data-training-kind]'?'ACTION':'ICON'};
 context.inner=inner;assert.equal(vm.runInContext('combatTooltipTarget(inner)',context),'ACTION','Nested icons must use the same action tooltip');
 assert.equal(vm.runInContext('localTalentIcon("assets/abilities/hobble.webp")',context),'assets/abilities/hobble.webp?v=20261002-game');
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
 context.training={active:true,turn:{actionAvailable:true},actions:[action,{kind:'attack',name:'Обычная атака'}]};
 vm.runInContext('saveQuickbarBinding(2,testAction.kind,testAction.name,1)',context);
 assert.equal(bindings.length,1,'Swap must use one atomic update');
 assert.equal(bindings[0].bindings.length,9);
 assert.equal(bindings[0].bindings[0].name,'Обычная атака');
 assert.equal(bindings[0].bindings[1].name,action.name);
 assert.equal(bindings[0].bindings[4].kind,'','Empty slots must remain intentionally empty');
 vm.runInContext('saveQuickbarBinding(9,testAction.kind,testAction.name)',context);
 assert.equal(bindings[1].bindings[0].name,action.name,'Assigning one slot preserves the other defaults');
 console.log('Combat UI: selection, invalid aim, explicit confirmation, target ID, Esc and right-click OK');
}
main().catch(error=>{console.error(error);process.exitCode=1});
