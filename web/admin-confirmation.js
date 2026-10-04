/* In-page confirmation works in regular and embedded browsers alike. */
let masterDeleteResolve=null,masterDeleteName='';
function askMasterDeletion({title,name,warning}){
 if(masterDeleteResolve)return Promise.resolve(false);
 const dialog=document.querySelector('#master-delete-dialog');
 document.querySelector('#master-delete-title').textContent=title;
 document.querySelector('#master-delete-name').textContent=name;
 document.querySelector('#master-delete-warning').textContent=warning;
 document.querySelector('#master-delete-confirm-name').value='';
 document.querySelector('#master-delete-submit').disabled=true;
 masterDeleteName=name;dialog.showModal();
 return new Promise(resolve=>{masterDeleteResolve=resolve});
}
function finishMasterDeletion(confirmed){
 const resolve=masterDeleteResolve;masterDeleteResolve=null;masterDeleteName='';
 document.querySelector('#master-delete-dialog').close();if(resolve)resolve(confirmed);
}
document.addEventListener('input',event=>{if(event.target.id==='master-delete-confirm-name')document.querySelector('#master-delete-submit').disabled=event.target.value!==masterDeleteName});
document.addEventListener('click',event=>{
 if(event.target.closest('[data-master-delete-cancel]'))finishMasterDeletion(false);
 if(event.target.closest('#master-delete-submit')&&masterDeleteResolve&&document.querySelector('#master-delete-confirm-name').value===masterDeleteName)finishMasterDeletion(true);
});
document.querySelector('#master-delete-dialog').addEventListener('cancel',event=>{event.preventDefault();finishMasterDeletion(false)});
