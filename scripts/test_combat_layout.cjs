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
const map={style:{}},label={},out={dataset:{combatZoom:'out'}},inside={dataset:{combatZoom:'in'}};
context.testPanel={querySelector:s=>s==='.tactical-map'?map:label,querySelectorAll:()=>[out,inside]};
context.$=()=>context.testPanel;
vm.runInContext('applyCombatMapZoom(testPanel,training)',context);
assert.equal(map.style.width,'975px');assert.equal(map.style.height,'675px');assert.equal(label.textContent,'125%');
function zoom(direction){context.testEvent={target:{closest:()=>({dataset:{combatZoom:direction}})},preventDefault(){},stopImmediatePropagation(){}};vm.runInContext('handleCombatMapZoom(testEvent)',context)}
zoom('in');assert.equal(label.textContent,'150%');assert.equal(map.style.width,'1170px');assert.equal(map.style.height,'810px');
for(let i=0;i<20;i++)zoom('in');assert.equal(label.textContent,'250%');assert.equal(inside.disabled,true);
for(let i=0;i<20;i++)zoom('out');assert.equal(label.textContent,'75%');assert.equal(out.disabled,true);
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
