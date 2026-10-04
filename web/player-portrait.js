let portraitDraft='',portraitBusy=false,portraitReading=0;
function openPortraitEditor(){
  if(portraitBusy)return;
  portraitDraft='';portraitReading++;
  $('#portrait-file').value='';$('#portrait-error').textContent='';$('#portrait-save').disabled=true;
  $('#portrait-preview').src=data.character.portrait_url||'';
  $('#portrait-preview').hidden=!data.character.portrait_url;
  $('#portrait-dialog').showModal();
}
async function savePortrait(){
  if(!portraitDraft||portraitBusy)return;
  portraitBusy=true;$('#portrait-save').disabled=true;$('#portrait-file').disabled=true;
  try{
    const result=await request(`/api/portal/${encodeURIComponent(token)}/portrait`,{method:'POST',body:JSON.stringify({portrait:portraitDraft})});
    data=normalize(result);portraitDraft='';renderCabinet();$('#portrait-dialog').close();toast(result.message);
  }catch(error){$('#portrait-error').textContent=error.message}
  finally{portraitBusy=false;$('#portrait-file').disabled=false;$('#portrait-save').disabled=!portraitDraft}
}
document.addEventListener('click',e=>{
  if(e.target.closest('[data-edit-portrait]'))openPortraitEditor();
  if(e.target.closest('#portrait-save'))savePortrait();
  if(e.target.closest('[data-portrait-cancel]')&&!portraitBusy){portraitReading++;portraitDraft='';$('#portrait-dialog').close()}
});
document.addEventListener('change',e=>{
  if(e.target.id!=='portrait-file'||portraitBusy)return;
  const file=e.target.files?.[0],version=++portraitReading;portraitDraft='';$('#portrait-save').disabled=true;$('#portrait-error').textContent='';
  if(!file)return;
  if(!['image/png','image/jpeg','image/webp'].includes(file.type)||file.size>5*1024*1024){$('#portrait-error').textContent='Выберите PNG, JPEG или WEBP до 5 МБ.';return}
  const reader=new FileReader();
  reader.onload=()=>{if(version!==portraitReading)return;portraitDraft=String(reader.result);$('#portrait-preview').src=portraitDraft;$('#portrait-preview').hidden=false;$('#portrait-save').disabled=false};
  reader.onerror=()=>{if(version===portraitReading)$('#portrait-error').textContent='Не удалось прочитать изображение.'};
  reader.readAsDataURL(file);
});
$('#portrait-dialog').addEventListener('cancel',e=>{if(portraitBusy)e.preventDefault();else{portraitReading++;portraitDraft=''}});
