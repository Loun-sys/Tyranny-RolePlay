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
