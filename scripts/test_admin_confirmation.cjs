const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const listeners={},elements=new Map();
function element(selector){if(!elements.has(selector))elements.set(selector,{value:'',textContent:'',disabled:false,open:false,showModal(){this.open=true},close(){this.open=false},addEventListener(type,fn){listeners['dialog:'+type]=fn}});return elements.get(selector)}
const context=vm.createContext({document:{querySelector:element,addEventListener(type,fn){listeners[type]=fn}}});
vm.runInContext(fs.readFileSync('web/admin-confirmation.js','utf8'),context);
async function main(){
 const promise=vm.runInContext('askMasterDeletion({title:"Удалить бой?",name:"<Поле>",warning:"Карта и персонажи сохранятся"})',context);
 assert(element('#master-delete-dialog').open);assert.equal(element('#master-delete-name').textContent,'<Поле>');assert(element('#master-delete-submit').disabled);
 assert.equal(await vm.runInContext('askMasterDeletion({name:"Другое"})',context),false,'Must not replace an existing confirmation');
 element('#master-delete-confirm-name').value='Поле';listeners.input({target:{id:'master-delete-confirm-name',value:'Поле'}});
 assert(element('#master-delete-submit').disabled);
 listeners.click({target:{closest(selector){return selector==='#master-delete-submit'}}});assert(element('#master-delete-dialog').open);
 listeners.click({target:{closest(selector){return selector==='[data-master-delete-cancel]'}}});assert.equal(await promise,false);
 const accepted=vm.runInContext('askMasterDeletion({title:"Удалить карту?",name:"Поле",warning:"Бои сохранятся"})',context);
 element('#master-delete-confirm-name').value='Поле';listeners.input({target:{id:'master-delete-confirm-name',value:'Поле'}});
 assert(!element('#master-delete-submit').disabled);listeners.click({target:{closest(selector){return selector==='#master-delete-submit'}}});assert.equal(await accepted,true);
 const escape=vm.runInContext('askMasterDeletion({name:"Поле"})',context);listeners['dialog:cancel']({preventDefault(){}});assert.equal(await escape,false);
 assert(!element('#master-delete-dialog').open);
 console.log('Admin deletion dialog: exact-name confirmation, duplicate guard, cancel/Escape, safe text and disabled submit OK');
}
main().catch(error=>{console.error(error);process.exitCode=1});
