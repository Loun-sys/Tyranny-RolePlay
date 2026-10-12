/* Game-style inspection shared by inventory, merchants, catalogue and forge. */
function itemNumber(value){return Number(value).toLocaleString('ru-RU',{maximumFractionDigits:4})}
function itemRecovery(item){return item.recoveryAdapted??Math.round((Number(item.recovery||0)*2.25+1e-10)*100)/100}
function itemHelp(term,text=term,fallback=''){return `<span class="game-term" tabindex="0" data-game-help="${esc(term)}"${fallback?` data-game-help-text="${esc(fallback)}"`:''}>${esc(text)}</span>`}
function itemRichText(value){return typeof GameHelp!=='undefined'?GameHelp.markup(value):esc(String(value||'').replace(/\[url=glossary:[^\]]+]([\s\S]*?)\[\/url]/gi,'$1').replace(/\[\/?(?:color|b|i|u)[^\]]*]/gi,''))}
function itemStatEntries(item){
 const s=item.weaponStats,rows=[];
 if(s){
  rows.push(['Урон',`${s.damageMin}–${s.damageMax} ${s.randomDamage?'Случайный тип':s.damageTypes.join(' / ')+(s.damageTypes.length>1?' (лучший против цели)':'')}`]);
  if(s.accuracyBonus)rows.push(['Точность',`${s.accuracyBonus>0?'+':''}${itemNumber(s.accuracyBonus)}`]);
  if(s.recoverySeconds)rows.push(['Восстановление',`+${itemNumber(s.recoverySeconds)} сек. (${itemNumber(s.recoveryRounds)} раунда)`]);
  if(s.rangeMeters>.5||s.minRangeMeters)rows.push(['Дистанция',`${s.minRangeMeters?itemNumber(s.minRangeMeters)+'–':''}${itemNumber(s.rangeMeters)} м`]);
  if(s.penetration)rows.push(['Пробивание брони',itemNumber(s.penetration)]);
  if(s.interrupt)rows.push(['Упреждение',itemNumber(s.interrupt)]);
 }else{
  if(item.damage_max)rows.push(['Урон',`${item.damage_min}–${item.damage_max}`]);
  if(item.armor)rows.push(['Броня',itemNumber(item.armor)]);
  const recovery=itemRecovery(item);
  if(recovery)rows.push(['Восстановление',`+${itemNumber(recovery*10)} сек. (${itemNumber(recovery)} раунда)`]);
 }
 return rows;
}
function itemPropertyEntries(item){
 let props=item.properties||{};if(typeof props==='string'){try{props=JSON.parse(props)}catch{props={}}}
 const covered=new Set(['gameData']);
 if(item.weaponStats)for(const name of ['Хват','Тип урона','Точность','Пробивание брони','Защита цели','Дальность','Скорость атаки','Восстановление оружия','Прерывание'])covered.add(name);
 if(item.inspection)for(const name of ['Эффекты','Модификаторы','Особые эффекты','Броня по типу урона','При использовании'])covered.add(name);
 return Object.entries(props).filter(([k,v])=>!covered.has(k)&&v!=null&&v!==''&&v!==0&&v!=='0');
}
function itemType(item){return item.weaponStats?(item.weaponStats.hands===2?'Двуручное оружие':'Одноручное оружие')+(item.category==='Посохи'?' (Волшебный посох)':item.category==='Луки'?' (Лук)':item.category==='Метательное оружие'?' (Дротик)':''):item.inspection?.type||item.category}
function itemStatList(item){return itemStatEntries(item).map(([k,v])=>`<li>${itemHelp(k)}: <span>${esc(v)}</span></li>`).join('')}
function itemStatDefinitionList(item){return `<div class="game-item-stats">${itemStatEntries(item).map(([k,v])=>`<div>${itemHelp(k)}: <span>${esc(v)}</span></div>`).join('')}</div>`}
function itemGameStats(item){
 const meta=item.inspection,s=item.weaponStats,lines=itemStatEntries(item).map(([k,v])=>`<div>${itemHelp(k)}: <span>${esc(v)}${k==='Урон'&&s?` / ${itemHelp(s.defense)}`:''}</span></div>`);
 if(meta){
  if(meta.armorGroups)lines.splice(item.armor?1:0,0,...meta.armorGroups.filter(g=>g.value!==Number(item.armor||0)).map(g=>`<div class="game-item-resistance">•${itemHelp('Броня',`${itemNumber(g.value)} к броне`)} (${g.types.map(t=>itemHelp('Типы урона',t)).join(' / ')} урон)</div>`));
  const covered=new Set(s?['Точность','Пробивание брони']:[]);covered.add('Броня');
  for(const [name,value] of Object.entries(meta.bonuses||{}))if(!covered.has(name)){const line=`<div>${itemHelp(name)}: <span>${value>0&&name!=='Отражение'?'+':''}${itemNumber(value)}${name==='Отражение'||name==='Критический шанс'?'%':''}</span></div>`;const beforeRecovery=!s?lines.findIndex(l=>l.includes('data-game-help="Восстановление"')):-1;if(beforeRecovery>=0)lines.splice(beforeRecovery,0,line);else lines.push(line)}
  for(const source of [meta.percentBonuses,meta.multipliers])for(const [name,value] of Object.entries(source||{}))lines.push(`<div>${itemHelp(name)}: <span>${value>0?'+':''}${itemNumber(value)}%</span></div>`);
 }
 const skill=meta?.skill;if(skill){const rank=typeof data!=='undefined'?data?.derived?.effectiveSkills?.[skill]??data?.character?.skills?.[skill]?.value:null;lines.push(`<div>${itemHelp('Ранг навыка','Навык(и) боя')}: ${itemHelp(skill)}${rank!=null?` <span>(${esc(rank)})</span>`:''}</div>`)}
 return `<div class="game-item-stats"><div class="game-item-type">${itemHelp(s?(s.hands===2?'Двуручное оружие':'Одноручное оружие'):'Снаряжение',itemType(item))}</div>${item.quality?`<div>${itemHelp('Качество')}: <span>${esc(item.quality)}</span></div>`:''}${lines.join('')}</div>`;
}
function itemGameEffects(item){
 const meta=item.inspection;let html='';
 if(meta){
  for(const mod of meta.modifiers||[])if(mod.name||mod.effects?.length||mod.description){const effects=mod.effects||[],prefix='Урон по целям под воздействием ';const copy=effects.length>1&&effects.every(t=>t.startsWith(prefix))?`<div>•Бонус к урону по целям под воздействием ${effects.map(t=>itemRichText(t.slice(prefix.length))).join(', ')}.</div>`:effects.map(text=>`<div>${text.endsWith(':')?'':'•'}${itemRichText(text)}</div>`).join('');html+=`<section class="game-item-mod">${mod.name?`<h3>${esc(mod.name)}:</h3>`:''}${copy}${mod.description&&!effects.includes(mod.description)?`<p>${itemRichText(mod.description)}</p>`:''}</section>`}
  if(meta.useEffects?.length)html+=`<section class="game-item-mod"><h3>${itemHelp('Расходуемые предметы','При применении')}:</h3>${meta.useEffects.map(text=>`<div>•${itemRichText(text)}</div>`).join('')}</section>`;
 }
 for(const [key,value] of itemPropertyEntries(item))html+=`<section class="game-item-property"><div>${itemHelp(key)}: ${itemRichText(typeof value==='object'?JSON.stringify(value):value)}</div></section>`;
 return html;
}
function itemPriceRings(value){let amount=Math.max(0,Math.round(Number(value)||0)),html='';for(const [divisor,label,icon] of [[10000,'Железное кольцо','Iron'],[100,'Бронзовое кольцо','Bronze'],[1,'Медное кольцо','Copper']]){const count=Math.floor(amount/divisor);amount%=divisor;if(count)html+=`<span class="game-item-coin" tabindex="0" data-game-help="${label}" data-game-help-text="${label}. 1 железное = 100 бронзовых = 10 000 медных колец."><span>${itemNumber(count)}</span><img src="assets/item-icons/Imperial${icon}Ring_S.png" alt="${label}"></span>`}return html}
function priceIcons(value){const amount=Math.max(0,Math.round(Number(value)||0));return `<span class="price-rings" aria-label="Цена: ${esc(amount)} медных колец">${amount?itemPriceRings(amount):'<span class="price-free">Бесплатно</span>'}</span>`}
function gameItemDetails(item,{market=false}={}){
 const description=String(item.description||'').trim(),lore=String(item.lore||'').trim();
 return `<article class="game-item-inspection"><header class="game-item-head"><img data-quality="${esc(item.quality||'')}" src="${esc(item.image_url||'assets/game-combat/icon_option_inventory.png')}" alt=""><div><h2>${esc(item.name)}</h2><div class="game-item-price" aria-label="Цена">${itemPriceRings(item.buy_price??(market?item.market?.buyPrice:null)??item.value)}</div></div></header><div class="game-item-copy">${itemGameStats(item)}${itemGameEffects(item)}${description?`<p class="game-item-lore">${itemRichText(description)}</p>`:''}${lore&&lore!==description?`<p class="game-item-lore">${itemRichText(lore)}</p>`:''}${(item.runtimeNotes||[]).map(note=>`<p class="game-item-warning">${esc(note)}</p>`).join('')}</div>${market&&item.market?`<p class="game-item-availability">${item.market.purchasable?`${esc(item.market.shopName)} · с ${item.market.minLevel} уровня`:`Не продаётся: ${esc(item.market.unavailableReason)}`}</p>`:''}</article>`;
}
function weaponSummary(item){const s=item.weaponStats;return s?`<p class="item-use-summary">${esc(`${s.damageMin}–${s.damageMax} · ${s.randomDamage?'Случайный':s.damageTypes.join(' / ')}${s.accuracyBonus?' · Точность '+(s.accuracyBonus>0?'+':'')+itemNumber(s.accuracyBonus):''} · ${itemNumber(s.rangeMeters)} м${s.recoverySeconds?' · Восстановление +'+itemNumber(s.recoverySeconds)+' сек.':''}`)}</p>`:''}
let inspectedItem=null;
function itemCompareTarget(item){
 if(typeof data==='undefined'||!data?.inventory)return null;
 const roman=['I','II','III','IV'][(data.character?.active_weapon_set||1)-1];
 const slot=item.weaponStats?`Оружие ${roman} — правая рука`:item.slot;
 return slot?data.inventory.find(i=>i.equipped_slot===slot&&Number(i.inventory_id)!==Number(item.inventory_id))||null:null;
}
function itemCompareButton(item){inspectedItem=item;return itemCompareTarget(item)?'<div class="game-item-compare"><button data-item-compare>СРАВНИТЬ</button></div>':''}
document.addEventListener('click',event=>{
 if(event.target.closest('[data-item-compare]')&&inspectedItem){
  const worn=itemCompareTarget(inspectedItem);if(!worn)return;
  $('#item-dialog-body').innerHTML=`<div class="item-compare-grid"><section class="item-compare-column"><h3>ВЫБРАННЫЙ ПРЕДМЕТ</h3>${gameItemDetails(inspectedItem)}</section><section class="item-compare-column"><h3>НАДЕТО НА ПЕРСОНАЖА</h3>${gameItemDetails(worn)}</section></div><button data-item-compare-back>НАЗАД</button>`;
 }
 if(event.target.closest('[data-item-compare-back]')&&inspectedItem){if(inspectedItem.inventory_id)openItemDetails(inspectedItem.inventory_id);else marketOpenDetails(inspectedItem)}
});
