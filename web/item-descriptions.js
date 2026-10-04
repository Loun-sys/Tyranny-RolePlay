/* Show source-backed use effects before buying, not only after opening an item. */
function itemUseDescription(item){let props=item.properties||{};if(typeof props==='string'){try{props=JSON.parse(props)}catch{props={}}}return props['При использовании']||''}
function itemUseSummary(item){const text=itemUseDescription(item);return text?`<p class="item-use-summary"><b>При применении:</b> ${esc(text)}</p>`:''}
const inventoryCardWithoutEffects=inventoryItemCard;
inventoryItemCard=function(item){return inventoryCardWithoutEffects(item).replace('</article>',itemUseSummary(item)+'</article>')};
const shopRowWithoutEffects=shopRow;
shopRow=function(item,sell){return shopRowWithoutEffects(item,sell).replace('</article>',itemUseSummary(item)+'</article>')};
document.addEventListener('click',event=>{
 const button=event.target.closest('[data-shop-inspect]');if(!button)return;
 const item=[...(playerShop?.items||[]),...data.inventory].find(i=>Number(i.id)===Number(button.dataset.shopInspect));
 if(item?.properties?.['Хват'])document.querySelector('#item-dialog-body h3')?.insertAdjacentHTML('beforebegin',`<p class="item-grip">${esc(item.properties['Хват'])}</p>`);
 if(item&&itemUseDescription(item))document.querySelector('#item-dialog-body h3')?.insertAdjacentHTML('beforebegin',`<h3>При применении</h3><p>${esc(itemUseDescription(item))}</p>`);
});
