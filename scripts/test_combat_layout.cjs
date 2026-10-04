const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const source=fs.readFileSync('web/combat-ui.js','utf8'),css=fs.readFileSync('web/combat-layout.css','utf8');
const context=vm.createContext({
 document:{addEventListener(){},querySelector(){return null},querySelectorAll(){return []}},
 renderTraining(){},loadTraining(){},combatPickerPanel(){return ''},statsBox(){},localTalentIcon:x=>x,sigilIcon(){},
 esc:value=>String(value).replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('"','&quot;'),
 training:{active:true,grid:{width:13,height:9,layout:{cellSize:60}}},
});
vm.runInContext(source,context);
context.sample={log:['Последнее действие','Предыдущее действие']};
let html=vm.runInContext('combatJournal(sample)',context);
assert(html.startsWith('<details'),'Journal uses native accessible disclosure');
assert(html.includes('combat-journal-latest">Последнее действие</span>'));
assert(!html.includes('data-combat-journal open'));
vm.runInContext('combatJournalOpen=true',context);html=vm.runInContext('combatJournal(sample)',context);
assert(html.includes('data-combat-journal open'));
context.sample={log:['<script>not HTML']};assert(!vm.runInContext('combatJournal(sample)',context).includes('<script>'));
context.sample={round:2,grid:{tokens:[{id:'player',portraitUrl:'portrait.png'}]},turn:{actorId:'player'},initiative:[{id:'player',name:'<Игрок>',roll:12,bonus:3,total:15},{id:'fallen',name:'Павший',roll:9,bonus:0,total:9}]};
html=vm.runInContext('combatInitiative(sample)',context);
assert(html.startsWith('<details'),'Initiative is an accessible native disclosure');
assert(!html.includes('data-combat-initiative open'),'Initiative starts collapsed');
assert(html.includes('Раунд 2'));assert(html.includes('portrait.png'));assert(html.includes('&lt;Игрок>'));assert(html.includes('defeated'));
assert(html.includes('бросок 12 + бонус 3 = 15'));
vm.runInContext('combatInitiativeOpen=true',context);assert(vm.runInContext('combatInitiative(sample)',context).includes('data-combat-initiative open'));
assert(!source.includes('sidebar.innerHTML=combatOrderPanel(t)'),'No permanent initiative list on the left');
assert(source.includes('${combatInitiative(t)}`;arena.append(tools)'),'Initiative belongs in the right map toolbar');
assert(css.includes('@media(max-width:900px)'));
const disclosure={open:false},initiativeButton={attrs:{},setAttribute(name,value){this.attrs[name]=value}};
context.document.querySelector=()=>disclosure;context.document.querySelectorAll=()=>[initiativeButton];
context.initiativeEvent={target:{closest:()=>initiativeButton},preventDefault(){},stopImmediatePropagation(){this.stopped=true}};
vm.runInContext('combatInitiativeOpen=false;handleCombatInitiative(initiativeEvent)',context);
assert.equal(disclosure.open,true);assert.equal(initiativeButton.attrs['aria-expanded'],'true');assert(context.initiativeEvent.stopped);
vm.runInContext('handleCombatInitiative(initiativeEvent)',context);assert.equal(disclosure.open,false);assert.equal(initiativeButton.attrs['aria-expanded'],'false');
context.document.querySelector=()=>null;context.document.querySelectorAll=()=>[];
const map={style:{}},label={},out={dataset:{combatZoom:'out'}},inside={dataset:{combatZoom:'in'}};
context.testPanel={querySelector:s=>s==='.tactical-map'?map:label,querySelectorAll:()=>[out,inside]};
context.$=()=>context.testPanel;
vm.runInContext('applyCombatMapZoom(testPanel,training)',context);
assert.equal(map.style.width,'975px');assert.equal(map.style.height,'675px');assert.equal(label.textContent,'125%');
function zoom(direction){context.testEvent={target:{closest:()=>({dataset:{combatZoom:direction}})},preventDefault(){},stopImmediatePropagation(){}};vm.runInContext('handleCombatMapZoom(testEvent)',context)}
zoom('in');assert.equal(label.textContent,'150%');assert.equal(map.style.width,'1170px');assert.equal(map.style.height,'810px');
for(let i=0;i<20;i++)zoom('in');assert.equal(label.textContent,'250%');assert.equal(inside.disabled,true);
for(let i=0;i<20;i++)zoom('out');assert.equal(label.textContent,'50%');assert.equal(out.disabled,true);
assert(source.includes("['ability','spell','artifact','item']"),'Ability categories belong in the vertical rail');
assert(source.includes("rail.className='combat-hud-rail'"));
assert(source.includes('combat-hud-statuses'),'HUD has an effect strip below its stats');
assert(css.includes('grid-template-columns:44px minmax(0,1fr)'));
assert(css.includes('.combat-sidebar .original-portrait{width:96px;height:148px'));
assert(css.includes('grid-template-columns:560px minmax(0,1fr)'));
assert(css.includes('repeat(8,minmax(0,1fr))'),'Desktop action row retains all eight real controls');
assert(source.includes("['ability','spell','artifact','stance','move','attack','item','initiative']"));
context.data={character:{}};context.combatPicker='spell';context.quickbarEditing=3;
let cancelled=0,rerenders=0;context.clearCombatAim=()=>{cancelled++};context.renderTraining=()=>{rerenders++};
context.moveEvent={target:{closest:()=>({dataset:{combatMove:'1'}})},preventDefault(){},stopImmediatePropagation(){}};
vm.runInContext('handleCombatMovement(moveEvent)',context);
assert.equal(cancelled,1,'Movement button cancels aiming instead of opening a picker');
assert.equal(context.combatPicker,'');assert.equal(context.quickbarEditing,0);assert.equal(rerenders,1);
assert(css.includes('.combat-journal-latest{min-width:0;flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}'));
assert(css.includes('@media(max-width:900px)'),'Small screens must retain a usable scrollable map');
console.log('Combat layout: vertical HUD rail, enlarged portrait, latest-action journal, escaped text and bounded coordinate-safe zoom OK');
