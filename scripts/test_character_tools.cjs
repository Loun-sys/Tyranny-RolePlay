const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
function environment(extra){
 const nodes={},events={},messages=[],requests=[];
 const node=key=>nodes[key]??={innerHTML:'',textContent:'',value:'',hidden:false,disabled:false,open:false,insertAdjacentHTML(_,v){this.innerHTML+=v},focus(){},showModal(){this.open=true},close(){this.open=false},addEventListener(k,fn){this[k]=fn}};
 let resolve,reject;
 const ctx=vm.createContext({$:node,document:{addEventListener(k,fn){(events[k]??=[]).push(fn)}},toast:m=>messages.push(m),request:(url,opt)=>{requests.push({url,opt});return new Promise((a,b)=>{resolve=a;reject=b})},...extra});
 return {ctx,node,events,messages,requests,resolve:v=>resolve(v),reject:v=>reject(v)};
}
(async()=>{
 const admin=environment({renderTab(){},tab:'identity',detail:{character:{id:1,name:'Герой'}},currentId:1,roster:[{id:1},{id:2}],base:()=>'/admin/secret',renderRoster(){}});
 vm.runInContext(fs.readFileSync('web/admin-character-tools.js','utf8'),admin.ctx);
 admin.ctx.renderTab();assert(admin.node('#admin-panel').innerHTML.includes('data-delete-character'));
 admin.ctx.openCharacterDeletion();assert(admin.node('#delete-character-submit').disabled);
 admin.node('#delete-character-confirm-name').value='Другой';await admin.ctx.submitCharacterDeletion();assert.equal(admin.requests.length,0);
 admin.node('#delete-character-confirm-name').value='Герой';
 const pending=admin.ctx.submitCharacterDeletion();await admin.ctx.submitCharacterDeletion();
 assert.equal(admin.requests.length,1);assert.equal(JSON.parse(admin.requests[0].opt.body).confirmName,'Герой');
 admin.resolve({deletedId:1,characters:[{id:2}],message:'Удалён'});await pending;
 assert.equal(admin.ctx.currentId,0);assert(admin.node('#editor').hidden);assert.equal(admin.ctx.roster.length,1);assert(!admin.node('#delete-character-dialog').open);
 const portrait=environment({data:{character:{portrait_url:'old.png'}},normalize:v=>v,renderCabinet(){},token:'test',FileReader:class{readAsDataURL(){this.result='data:image/png;base64,dGVzdA==';this.onload()}}});
 vm.runInContext(fs.readFileSync('web/player-portrait.js','utf8'),portrait.ctx);
 portrait.ctx.openPortraitEditor();assert(portrait.node('#portrait-save').disabled);assert.equal(portrait.node('#portrait-preview').src,'old.png');
 portrait.events.change[0]({target:{id:'portrait-file',files:[{type:'text/plain',size:1}]}});
 assert(portrait.node('#portrait-error').textContent);assert(portrait.node('#portrait-save').disabled);
 portrait.events.change[0]({target:{id:'portrait-file',files:[{type:'image/png',size:100}]}});
 assert(!portrait.node('#portrait-save').disabled);
 const saving=portrait.ctx.savePortrait();await portrait.ctx.savePortrait();assert.equal(portrait.requests.length,1);
 portrait.reject(Error('Нет связи'));await saving;assert.equal(portrait.node('#portrait-error').textContent,'Нет связи');assert(!portrait.node('#portrait-save').disabled);
 const retry=portrait.ctx.savePortrait();portrait.resolve({character:{portrait_url:'new.png'},message:'Портрет обновлён.'});await retry;
 assert.equal(portrait.ctx.data.character.portrait_url,'new.png');assert(!portrait.node('#portrait-dialog').open);
 console.log('Character tools: named delete confirmation, duplicate guards, roster cleanup, image validation and upload retry OK');
})().catch(e=>{console.error(e);process.exitCode=1});
