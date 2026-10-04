/* Destructive character operations require an explicit, named confirmation. */
let characterDeleteTarget=null,characterDeleteBusy=false;
const beforeCharacterToolsTab=renderTab;
renderTab=function(){beforeCharacterToolsTab();if(tab==='identity'&&detail?.character){$('#admin-panel').insertAdjacentHTML('beforeend',`<section class="admin-box character-danger-zone"><h2>Удаление персонажа</h2><p>Личное дело, предметы, деньги и ссылки доступа будут удалены без возможности восстановления. Токен персонажа исчезнет с сохранённых карт.</p><button class="dark-button danger" data-delete-character>УДАЛИТЬ ПЕРСОНАЖА</button></section>`)}};
function openCharacterDeletion(){
  if(characterDeleteBusy||!detail?.character)return;
  characterDeleteTarget={id:detail.character.id,name:detail.character.name};
  $('#delete-character-name').textContent=characterDeleteTarget.name;
  $('#delete-character-confirm-name').value='';
  $('#delete-character-submit').disabled=true;
  $('#delete-character-error').textContent='';
  $('#delete-character-dialog').showModal();
  $('#delete-character-confirm-name').focus();
}
async function submitCharacterDeletion(){
  const target=characterDeleteTarget,value=$('#delete-character-confirm-name').value;
  if(characterDeleteBusy||!target||value!==target.name)return;
  characterDeleteBusy=true;$('#delete-character-submit').disabled=true;
  try{
    const result=await request(`${base()}/character/${target.id}`,{method:'POST',body:JSON.stringify({action:'character_delete',confirmName:value})});
    roster=result.characters||[];
    if(currentId===Number(result.deletedId)){currentId=0;detail=null;$('#editor').hidden=true;$('#editor').innerHTML='';$('#empty').hidden=false}
    renderRoster();$('#delete-character-dialog').close();characterDeleteTarget=null;toast(result.message);
  }catch(error){$('#delete-character-error').textContent=error.message}
  finally{characterDeleteBusy=false;$('#delete-character-submit').disabled=!characterDeleteTarget||$('#delete-character-confirm-name').value!==characterDeleteTarget.name}
}
document.addEventListener('click',e=>{
  if(e.target.closest('[data-delete-character]'))openCharacterDeletion();
  if(e.target.closest('#delete-character-submit'))submitCharacterDeletion();
  if(e.target.closest('[data-cancel-character-delete]')&&!characterDeleteBusy){$('#delete-character-dialog').close();characterDeleteTarget=null}
});
document.addEventListener('input',e=>{if(e.target.id==='delete-character-confirm-name')$('#delete-character-submit').disabled=characterDeleteBusy||!characterDeleteTarget||e.target.value!==characterDeleteTarget.name});
$('#delete-character-dialog').addEventListener('cancel',e=>{if(characterDeleteBusy)e.preventDefault();else characterDeleteTarget=null});
