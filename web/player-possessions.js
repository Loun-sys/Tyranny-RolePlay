/* Owned inventory and wallet operations; the server validates every transfer. */
function possessionRecipients(){return `<select name="recipientId" aria-label="Получатель"><option value="">Выберите получателя</option>${(data.recipients||[]).map(r=>`<option value="${Number(r.id)}">${esc(r.name)} · ${esc(r.background)}</option>`).join('')}</select>`}
function possessionControls(kind,id=0,maximum=1){return `<form class="possession-form" data-possession-kind="${kind}" data-inventory-id="${id}"><p>${kind==='item'?'Передать другому персонажу или безвозвратно уничтожить. Надетый предмет сначала снимите.':'100 медных = 1 бронзовое · 100 бронзовых = 1 железное.'}</p>${kind==='item'?`<label>Количество<input name="quantity" type="number" min="1" max="${maximum}" value="1" required></label>`:`<div class="possession-coins">${[['iron','Железные'],['bronze','Бронзовые'],['copper','Медные']].map(([n,label])=>`<label>${label}<input name="${n}" type="number" min="0" max="2000000000" value="0" required></label>`).join('')}</div>`}${possessionRecipients()}<div class="item-dialog-actions"><button type="button" class="action" data-possession-action="transfer">ПЕРЕДАТЬ</button><button type="button" class="dark-button" data-possession-action="destroy">УНИЧТОЖИТЬ</button></div></form>`}
const inventoryBeforePossessions=renderInventory;
renderInventory=function(p,c){inventoryBeforePossessions(p,c);p.insertAdjacentHTML('beforeend',`<section class="box possession-wallet"><h2>Кольца</h2><p>${esc(moneyText(data.wallet))}</p>${possessionControls('money')}</section>`)};
const detailsBeforePossessions=openItemDetails;
openItemDetails=function(id){detailsBeforePossessions(id);const item=data.inventory.find(i=>Number(i.inventory_id)===Number(id));if(item)$('#item-dialog-body').insertAdjacentHTML('beforeend',`<h3>Передача и уничтожение</h3>${possessionControls('item',Number(id),Number(item.quantity))}`)};
const compatibleBeforePossessions=compatibleSlots;
compatibleSlots=function(item){return data.character.background==='Зверолюд'&&item.category==='Броня'?[]:compatibleBeforePossessions(item)};
document.addEventListener('click',async event=>{
 const button=event.target.closest('[data-possession-action]');if(!button)return;
 const form=button.closest('form');if(!form.reportValidity())return;
 const fields=new FormData(form),kind=form.dataset.possessionKind,action=button.dataset.possessionAction;
 const quantity=kind==='item'?Number(fields.get('quantity')):10000*Number(fields.get('iron'))+100*Number(fields.get('bronze'))+Number(fields.get('copper'));
 const recipientId=Number(fields.get('recipientId'));
 if(!Number.isSafeInteger(quantity)||quantity<=0){toast('Укажите положительное целое количество.');return}
 if(action==='transfer'&&!recipientId){toast('Выберите получателя.');return}
 const item=data.inventory.find(i=>Number(i.inventory_id)===Number(form.dataset.inventoryId));
 const label=kind==='item'?`${item?.name} ×${quantity}`:`${quantity} медных колец`;
 const recipient=(data.recipients||[]).find(r=>r.id===recipientId);
 if(!confirm(action==='destroy'?`Безвозвратно уничтожить ${label}? Восстановить это действие нельзя.`:`Передать ${label} персонажу «${recipient?.name}»?`))return;
 button.disabled=true;
 try{const result=await request(`/api/portal/${encodeURIComponent(token)}/possessions`,{method:'POST',body:JSON.stringify({action,kind,quantity,recipientId,inventoryId:Number(form.dataset.inventoryId),confirmed:action==='destroy'})});data=normalize(result);$('#item-dialog').close();renderCabinet();toast(result.message)}catch(error){toast(error.message)}finally{button.disabled=false}
});
