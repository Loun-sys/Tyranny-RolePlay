/* Show source-backed use effects before buying, not only after opening an item. */
function itemUseDescription(item){let props=item.properties||{};if(typeof props==='string'){try{props=JSON.parse(props)}catch{props={}}}return props['При использовании']||''}
function itemUseSummary(item){const text=itemUseDescription(item);return text?`<p class="item-use-summary"><b>При применении:</b> ${esc(text)}</p>`:''}
const inventoryCardWithoutEffects=inventoryItemCard;
inventoryItemCard=function(item){return inventoryCardWithoutEffects(item).replace('</article>',weaponSummary(item)+itemUseSummary(item)+'</article>')};
const shopRowWithoutEffects=shopRow;
shopRow=function(item,sell){return shopRowWithoutEffects(item,sell).replace('</article>',itemUseSummary(item)+'</article>')};
