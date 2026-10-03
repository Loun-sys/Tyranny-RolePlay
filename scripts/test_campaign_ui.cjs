const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const nodes={};const element=id=>nodes[id]??={hidden:false,innerHTML:'',style:{},insertAdjacentHTML(where,html){this.innerHTML+=html}};
const ctx=vm.createContext({document:{querySelector:element,addEventListener(){}},$:element,
renderEditor(){},renderTab(){},renderRoster(){},request(){},base(){return '/api/admin/test'},toast(){},
esc:v=>String(v),tab:'identity',detail:{wallet:{copper:1},character:{}},currentId:1,openCharacter(){}});
vm.runInContext(fs.readFileSync('web/admin-campaign.js','utf8'),ctx);
vm.runInContext('newMap()',ctx);
assert(element('#editor').innerHTML.includes('Стена'));
assert(element('#map-edit-grid').innerHTML.includes('data-map-cell="12:8"'));
assert.equal(vm.runInContext('mapDraft.width*mapDraft.height',ctx),117);
assert(!element('#editor').innerHTML.includes('Цель 1'));
assert(!element('#editor').innerHTML.includes('Старт игрока'));
element('#map-token-choice').value='player:1';
element('#map-token-team').value='enemy';
vm.runInContext("mapTokenChoices=[{kind:'player',id:1,name:'Герой'}];mapTool='token';paintMap(1,1);paintMap(2,2);drawMapGrid()",ctx);
assert.equal(vm.runInContext('mapDraft.tokens.length',ctx),1);
assert.equal(vm.runInContext('mapDraft.tokens[0].team',ctx),'ally');
assert(element('#map-edit-grid').innerHTML.includes('Герой'));
vm.runInContext("mapTool='wall';paintMap(3,3)",ctx);
assert.equal(vm.runInContext('mapDraft.blocked.length',ctx),1);
assert.equal(vm.runInContext('mapDraft.sightBlocked.length',ctx),1);
vm.runInContext("mapTool='blocked';paintMap(3,3)",ctx);
assert.equal(vm.runInContext('mapDraft.sightBlocked.length',ctx),0);
vm.runInContext("rememberMap();mapTool='erase';paintMap(3,3)",ctx);
assert.equal(vm.runInContext('mapUndo.length',ctx),1);
vm.runInContext("renderTab()",ctx);
assert(element('#admin-panel').innerHTML.includes('Кольца персонажа'));
console.log('Campaign UI: map render, layer separation, history and wallet panel OK');
// A game template is instantiated as an owner-scoped NPC before placement.
(async()=>{
element('#map-token-choice').options=[];
element('#map-token-choice').prepend=o=>element('#map-token-choice').options.unshift(o);
ctx.document.createElement=()=>({});
ctx.request=async(path,opt)=>{assert.equal(JSON.parse(opt.body).action,'fromTemplate');return {id:22,npcs:[{id:22,spec:{name:'Страж',portrait:'assets/npc-portraits/tankfighter_m_white_sm.png',sourceKey:'game:test',color:'#a92339'}}]}};
vm.runInContext("mapTokenChoices=[{kind:'game',id:0,name:'Страж',templateKey:'game:test'}];mapTool='token'",ctx);
await vm.runInContext('placeGameMapToken(mapTokenChoices[0],4,4)',ctx);
assert.equal(vm.runInContext('mapDraft.tokens.find(t=>t.x===4&&t.y===4).id',ctx),22);
assert.equal(vm.runInContext('mapDraft.tokens.find(t=>t.x===4&&t.y===4).kind',ctx),'npc');
assert(element('#map-edit-grid').innerHTML.includes('assets/npc-portraits/tankfighter_m_white_sm.png'));
console.log('Game NPC template: clone, placement and original portrait OK');
})().catch(e=>{console.error(e);process.exitCode=1});
