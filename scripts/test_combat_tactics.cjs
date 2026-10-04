const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const listeners={},removed=[],appended=[];
const elements={
 '.tactical-map':{insertAdjacentHTML(_where,html){appended.push(html)},querySelector(){return null}},
 '.combat-aim-overlay':{insertAdjacentHTML(_where,html){appended.push(html)}},
 '.combat-intent-panel':{hidden:true,innerHTML:''},
};
let armed=null,calls=[];
const context=vm.createContext({
 document:{addEventListener(type,handler){(listeners[type]||=[]).push(handler)},querySelector:s=>elements[s]||null,
  querySelectorAll(){return []}},
 renderTraining(){},showCombatAim(){},clearCombatAim(){},playCombatEffect(){},trainingMutate(path,body){calls.push([path,body])},
 esc:v=>String(v??'').replaceAll('<','&lt;').replaceAll('"','&quot;'),combatStatusLabel(){},
 armedCombatAction:null,combatBusy:false,tab:'training',
 training:{active:true,turn:{movementRemaining:5},grid:{width:10,height:10,tokens:[{id:'e',x:4,y:1}],
  movementPreviews:{'5:1':{cost:4,path:[{x:1,y:1},{x:5,y:1}],opportunities:[{id:'e',name:'<Враг>'}]}}}},
});
vm.runInContext(fs.readFileSync('web/combat-tactics.js','utf8'),context);
const path=vm.runInContext('combatShapePath([{x:1,y:1},{x:2,y:1}])',context);
assert.equal((path.match(/M/g)||[]).length,6,'No shared internal edge in the area contour');
assert(!path.includes('M2,1v1'),'Internal vertical border is omitted');
assert.equal(vm.runInContext('combatShapePath([])',context),'');
context.aim={previews:[{name:'<Цель>',accuracy:20,defenseName:'Магия',defense:30,cover:15,hitChance:60,
 damageMin:3,damageMax:12,strikeCount:2,outcomes:{miss:40,graze:35,hit:24.8,critical:.2,reflected:0}}]};
const html=vm.runInContext('combatPreviewMarkup(aim,{kind:"spell"})',context);
assert(html.includes('&lt;Цель>'));assert(html.includes('60%'));assert(html.includes('Магия 30 + укрытие 15'));
assert(html.includes('3–12'));assert(html.includes('2 удара'));assert(html.includes('Бросок выполняется только после применения'));
assert(!fs.readFileSync('web/combat-tactics.js','utf8').includes('combat-ready-trigger'));
assert(fs.readFileSync('web/combat-tactics.js','utf8').includes('training.stealth?.active'));
vm.runInContext('showCombatRoute({x:5,y:1})',context);
assert(appended.some(html=>html.includes('Атака по возможности: &lt;Враг>')));
assert(appended.some(html=>html.includes('danger')&&html.includes('polyline')));
const cell={dataset:{moveX:'5',moveY:'1'}},event={target:{closest:s=>s==='[data-move-x]'?cell:null},preventDefault(){this.prevented=true},stopImmediatePropagation(){this.stopped=true}};
for(const listener of listeners.click)listener(event);
assert(event.prevented&&event.stopped,'Dangerous movement intercepts the immediate move');
assert.equal(calls.length,0,'Preview does not submit an action');
assert(appended.some(html=>html.includes('data-confirm-combat-move')));
const confirm={target:{closest:s=>s==='[data-confirm-combat-move]'?{}:null},preventDefault(){},stopImmediatePropagation(){}};
for(const listener of listeners.click)listener(confirm);
assert.equal(calls.length,1);assert.deepEqual(JSON.parse(JSON.stringify(calls[0])),['action',{kind:'move',x:5,y:1}]);
vm.runInContext('clearCombatRoute()',context);assert.equal(vm.runInContext('pendingCombatMove',context),null);
const page=fs.readFileSync('web/archive.html','utf8'),css=fs.readFileSync('web/combat-tactics.css','utf8');
assert(page.indexOf('combat-tactics.js')>page.indexOf('combat-feedback.js'));
assert(css.includes('vector-effect:non-scaling-stroke'));assert(css.includes('.combat-token-states'));
assert(css.includes('.combat-token.is-current:after'));assert(css.includes('prefers-reduced-motion'));
console.log('Combat tactics: contours, probability previews, stealth indicators and confirmed dangerous movement OK');
