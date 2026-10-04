let craftingData=null,craftingKind='upgrade',craftingSelection=null,craftingBusy=false,craftingLoading=false,craftingQuery='';
const beforeCraftCabinet=renderCabinet;
renderCabinet=function(){beforeCraftCabinet();let button=document.querySelector('[data-tab="crafting"]');if(!button){$('#tabs').insertAdjacentHTML('beforeend','<button data-tab="crafting">МАСТЕРСКАЯ</button>');button=document.querySelector('[data-tab="crafting"]')}button.hidden=data.character.background!=='Скованный Ремеслом'};
const beforeCraftTab=renderTab;
renderTab=function(){if(tab==='crafting'){renderCrafting();return}beforeCraftTab()};
async function loadCrafting(){if(craftingLoading||craftingBusy)return;craftingLoading=true;try{const [snapshot,profile]=await Promise.all([request(`/api/portal/${encodeURIComponent(token)}/crafting`),request(`/api/portal/${encodeURIComponent(token)}`)]);craftingData=snapshot;data=normalize(profile);if(tab==='crafting')renderCrafting()}catch(e){toast(e.message);if(tab==='crafting')$('#panel').innerHTML=`<section class="box"><p>${esc(e.message)}</p><button class="action" data-refresh-crafting>ПОВТОРИТЬ</button></section>`}finally{craftingLoading=false}}
function craftMaterialCount(r){return data.inventory.filter(i=>!i.equipped_slot&&Number(i.id)===Number(r.item?.id)).reduce((n,i)=>n+Number(i.quantity||0),0)}
function craftBalance(){const w=craftingData?.wallet||{};return Number(w.totalCopper??(Number(w.iron||0)*10000+Number(w.bronze||0)*100+Number(w.copper||0)))}
function craftQuantity(value){const n=Number(value);return Number.isInteger(n)&&n>=1&&n<=15?n:null}
function craftCost(row){return Number(craftingKind==='upgrade'?row.recipe.cost:row.cost)}
function craftBlocked(row,quantity=1){
  if(craftingBusy)return 'Идёт изготовление…';
  if((craftingData.jobs||[]).some(j=>!j.claimed))return 'Сначала заберите готовую работу.';
  if(craftingKind==='consumable'&&!row.known)return 'Сначала изучите рецепт.';
  if(craftQuantity(quantity)===null)return 'Количество должно быть целым числом от 1 до 15.';
  if(craftBalance()<craftCost(row)*quantity)return 'Недостаточно колец.';
  const missing=row.ingredients.find(r=>craftMaterialCount(r)<Number(r.quantity)*quantity);
  return missing?'Недостаточно материала: '+(missing.item?.name||'Неизвестный материал'):'';
}
function craftIngredients(rows,quantity=1){return rows.map(r=>{const count=craftMaterialCount(r),need=Number(r.quantity)*quantity;return `<span class="craft-material ${count<need?'missing':''}"><img src="${esc(r.item?.image_url||'assets/game-combat/icon_option_inventory.png')}" alt=""><span>${esc(r.item?.name||'Неизвестный материал')}<small>${count} / ${need}${r.consumed===false?' · не расходуется':''}</small></span></span>`}).join('')}
function craftNumber(value){return Number(value||0).toLocaleString('ru',{maximumFractionDigits:4})}
function craftForgeCost(row){
  let remaining=Number(row.recipe.cost),coins='';
  for(const [divisor,label,icon] of [[10000,'железных','Iron'],[100,'бронзовых','Bronze'],[1,'медных','Copper']]){
    const count=Math.floor(remaining/divisor);remaining%=divisor;
    if(count)coins+=`<span class="craft-cost-token" title="${label} колец"><b>${craftNumber(count)}</b><img src="assets/item-icons/Imperial${icon}Ring_S.png" alt="${label} колец"></span>`;
  }
  return (coins||'<span>Бесплатно</span>')+row.ingredients.filter(r=>r.consumed).map(r=>`<span class="craft-cost-token" title="${esc(r.item?.name)}"><b>${craftNumber(r.quantity)}</b><img src="${esc(r.item?.image_url)}" alt="${esc(r.item?.name)}"></span>`).join('');
}
function craftForgeMaterials(){return (craftingData.materials||[]).map(i=>`<span class="craft-stock" title="${esc(i.name)}"><b>${craftNumber(i.quantity)}</b><img src="${esc(i.image_url)}" alt="${esc(i.name)}"></span>`).join('')}
function craftStats(i){
  const props=Object.entries(i.properties||{}).filter(([k,v])=>k!=='gameData'&&v!==null&&v!==''&&typeof v!=='object');
  const stat=(label,value)=>`<div class="craft-stat"><dt>${esc(label)}</dt><dd>${esc(value)}</dd></div>`;
  const recovery=typeof roundText==='function'?roundText(Number(i.recovery||0)):craftNumber(i.recovery)+' раундов';
  return `<div class="craft-stats"><p class="craft-category">${esc(i.category)}</p><dl>${stat('Качество',i.quality)}${Number(i.damage_max)?stat('Урон',craftNumber(i.damage_min)+'–'+craftNumber(i.damage_max)):''}${Number(i.armor)?stat('Броня',craftNumber(i.armor)):''}${Number(i.recovery)?stat('Восстановление',recovery):''}${props.map(([k,v])=>stat(k,v)).join('')}</dl></div>`;
}
function craftForge(row){
  const reason=craftBlocked(row);
  return `<section class="craft-forge" aria-label="Кузня"><h2>Кузня</h2><header class="craft-forge-item">${itemVisual(row.item)}<h3>${esc(row.item.name)}</h3></header><div class="craft-forge-body"><div class="craft-compare"><section aria-label="В данный момент"><h4>В ДАННЫЙ МОМЕНТ:</h4><div class="craft-stat-scroll">${craftStats(row.item)}</div></section><section aria-label="После улучшения"><h4>ПОСЛЕ УЛУЧШЕНИЯ:</h4><div class="craft-stat-scroll">${craftStats(row.result)}</div></section></div><aside class="craft-forge-materials" aria-label="Запасы материалов">${craftForgeMaterials()}</aside></div><div class="craft-forge-footer"><div class="craft-forge-price"><span>ЦЕНА:</span><div class="craft-cost">${craftForgeCost(row)}</div></div><p class="craft-instant">Улучшение мгновенно${row.item.equipped_slot?' · экипировка сохраняется':''}</p><p class="craft-locked" id="craft-blocked" role="status">${esc(reason)}</p><div class="craft-forge-actions"><button data-craft-back>НАЗАД</button><button class="action" data-craft-action="upgrade" data-inventory="${Number(row.inventoryId)}" ${reason?'disabled':''}>УЛУЧШИТЬ</button></div></div></section>`;
}
function craftRecipe(row){
  const reason=craftBlocked(row);
  return `<div class="craft-recipe-head">${itemVisual(row.outputItem)}<h2>${esc(row.outputItem.name)}</h2></div>${craftStats(row.outputItem)}${row.outputItem.description?`<p class="item-description">${esc(row.outputItem.description)}</p>`:''}${row.outputItem.lore?`<p class="item-description">${esc(row.outputItem.lore)}</p>`:''}<div id="craft-materials">${craftIngredients(row.ingredients)}</div><p>За 1 шт.: ${craftNumber(row.cost)} медных · Мгновенно</p>${row.known?`<label>Количество <input id="craft-quantity" type="number" min="1" max="15" step="1" value="1"></label><p id="craft-total">Итого: ${craftNumber(row.cost)} медных · Мгновенно</p><p id="craft-blocked" class="craft-locked" role="status">${esc(reason)}</p><button class="action" data-craft-action="craft" data-recipe="${esc(row.key)}" ${reason?'disabled':''}>ПРИГОТОВИТЬ</button>`:'<p class="craft-locked">Сначала приобретите и изучите рецепт в лавке мастера.</p>'}`;
}
function renderCrafting(){
  if(data.character.background!=='Скованный Ремеслом'){$('#panel').innerHTML='<section class="box">Мастерская недоступна этому происхождению.</section>';return}
  if(!craftingData){$('#panel').innerHTML='<section class="box">Загружаем мастерскую…</section>';loadCrafting();return}
  const rows=craftingKind==='upgrade'?craftingData.upgrades:craftingData.recipes;
  const selected=rows.find(r=>(craftingKind==='upgrade'?String(r.inventoryId):r.key)===craftingSelection);
  const pending=(craftingData.jobs||[]).find(j=>!j.claimed);
  const header=`<header class="craft-workshop-header"><h2>Мастерская</h2><p>${moneyText(craftingData.wallet)}</p><nav class="merchant-nav"><button data-craft-mode="upgrade" class="${craftingKind==='upgrade'?'active':''}">КУЗНЯ</button><button data-craft-mode="consumable" class="${craftingKind==='consumable'?'active':''}">РАСХОДНИКИ</button><button data-tab="shop">КУПИТЬ МАТЕРИАЛЫ И РЕЦЕПТЫ</button><button data-refresh-crafting>ОБНОВИТЬ</button></nav></header>`;
  const job=pending?`<div class="craft-job"><b>Готовая работа: ${esc(pending.payload.name)}</b><button class="action" data-craft-action="claim" data-job="${Number(pending.id)}">ЗАБРАТЬ РАБОТУ</button></div>`:'';
  if(craftingKind==='upgrade'&&selected){$('#panel').innerHTML=`<section class="box crafting-workshop">${header}${job}${craftForge(selected)}</section>`;return}
  const choices=rows.filter(r=>String(r.item?.name||r.outputItem?.name||r.name||'').toLocaleLowerCase('ru').includes(craftingQuery.toLocaleLowerCase('ru'))).map(r=>{const i=r.item||r.outputItem,id=craftingKind==='upgrade'?r.inventoryId:r.key;return `<button class="craft-choice ${String(id)===craftingSelection?'active':''}" data-craft-select="${esc(id)}">${itemVisual(i)}<span><b>${esc(i.name)}</b><small>${craftingKind==='upgrade'?esc(i.quality)+(i.equipped_slot?' · '+esc(i.equipped_slot):''):r.known?'Рецепт известен':'Требуется рецепт'}</small></span></button>`}).join('')||'<p>Нет подходящих предметов. Предметы максимального качества не требуют улучшения.</p>';
  const scrolls=craftingKind==='consumable'?`<h3>Рецепты в инвентаре</h3>${craftingData.scrolls.map(s=>`<div class="craft-scroll">${itemVisual(s.item)}<b>${esc(s.item.name)}</b><button data-craft-action="learn" data-inventory="${Number(s.inventoryId)}" ${s.known?'disabled':''}>${s.known?'ИЗУЧЕН':'ИЗУЧИТЬ'}</button></div>`).join('')||'<p>Неизученных свитков нет.</p>'}`:'';
  $('#panel').innerHTML=`<section class="box crafting-workshop">${header}${job}${craftingKind==='upgrade'?'<p class="craft-note">Выберите предмет, чтобы сравнить характеристики до и после улучшения.</p>':''}<div class="craft-layout ${craftingKind==='upgrade'?'craft-pick-layout':''}"><aside><input id="craft-search" aria-label="Поиск предмета или рецепта" placeholder="Поиск" value="${esc(craftingQuery)}">${choices}</aside>${craftingKind==='consumable'?`<div class="craft-preview">${selected?craftRecipe(selected):'<p>Выберите рецепт слева.</p>'}</div>`:''}</div>${scrolls}</section>`;
}
document.addEventListener('click',async e=>{
  if(e.target.closest('[data-tab="crafting"]')){loadCrafting();return}
  const mode=e.target.closest('[data-craft-mode]');if(mode){craftingKind=mode.dataset.craftMode;craftingSelection=null;renderCrafting();return}
  if(e.target.closest('[data-craft-back]')){craftingSelection=null;renderCrafting();return}
  const selected=e.target.closest('[data-craft-select]');if(selected){craftingSelection=selected.dataset.craftSelect;renderCrafting();return}
  if(e.target.closest('[data-refresh-crafting]')){loadCrafting();return}
  const action=e.target.closest('[data-craft-action]');if(!action||action.disabled||craftingBusy)return;
  const kind=action.dataset.craftAction,quantity=kind==='craft'?craftQuantity($('#craft-quantity')?.value??1):1;
  if(kind==='craft'||kind==='upgrade'){
    const row=(kind==='upgrade'?craftingData.upgrades:craftingData.recipes).find(r=>kind==='upgrade'?String(r.inventoryId)===String(action.dataset.inventory):r.key===action.dataset.recipe);
    if(!row||quantity===null){toast('Выберите предмет и корректное количество.');return}
    const reason=craftBlocked(row,quantity);if(reason){toast(reason);return}
  }
  craftingBusy=true;action.disabled=true;
  try{
    const result=await request(`/api/portal/${encodeURIComponent(token)}/crafting`,{method:'POST',body:JSON.stringify({action:kind,inventoryId:Number(action.dataset.inventory||0),recipeKey:action.dataset.recipe,jobId:Number(action.dataset.job||0),quantity})});
    craftingData=result;craftingSelection=null;
    data=normalize(await request(`/api/portal/${encodeURIComponent(token)}`));
    craftingBusy=false;renderCabinet();toast(result.message);
  }catch(error){toast(error.message);craftingBusy=false;renderCrafting()}
  finally{craftingBusy=false}
});
document.addEventListener('input',e=>{
  if(e.target.id==='craft-search'){craftingQuery=e.target.value;renderCrafting();const field=$('#craft-search');field.focus();field.setSelectionRange(field.value.length,field.value.length)}
  if(e.target.id==='craft-quantity'){
    const r=craftingData.recipes.find(r=>r.key===craftingSelection);if(!r)return;
    const quantity=craftQuantity(e.target.value),reason=quantity===null?'Количество должно быть целым числом от 1 до 15.':craftBlocked(r,quantity);
    $('#craft-materials').innerHTML=craftIngredients(r.ingredients,quantity||0);
    $('#craft-total').textContent=quantity===null?'Укажите количество от 1 до 15.':`Итого: ${craftNumber(r.cost*quantity)} медных · Мгновенно`;
    $('#craft-blocked').textContent=reason;document.querySelector('[data-craft-action="craft"]').disabled=Boolean(reason);
  }
});
