/* One source-backed readout for inventory, player shops and master catalogue. */
function itemStatEntries(item){
 const s=item.weaponStats,rows=[];
 if(s){
  const type=s.randomDamage?'Случайный тип':s.damageTypes.join(' / ')+(s.damageTypes.length>1?' (лучший против цели)':'');
  rows.push(['Хват',s.hands===2?'Двуручное оружие':'Одноручное оружие'],
   ['Урон',`${s.damageMin}–${s.damageMax} · ${type}`],
   ['Точность',`${s.accuracyBonus>=0?'+':''}${s.accuracyBonus}`],['Пробивание брони',s.penetration],
   ['Защита цели',s.defense+(s.secondaryDefense!=='Нет'?' / '+s.secondaryDefense:'')],
   ['Дальность',`${s.minRangeMeters?s.minRangeMeters+'–':''}${s.rangeMeters} м · ${s.rangeCells} кл.`],['Скорость атаки',s.attackSpeed],
   ['Восстановление оружия',`${s.recoverySeconds} сек. · ${s.recoveryRounds} раунда`],['Прерывание',s.interrupt]);
 }else{
  if(item.damage_max)rows.push(['Урон',`${item.damage_min}–${item.damage_max}`]);
  if(item.category==='Броня'||item.armor)rows.push(['Броня',item.armor]);
  if(item.recovery)rows.push(['Восстановление',roundText(item.recovery)]);
 }
 if(item.weight!=null)rows.push(['Вес',item.weight]);
 return rows;
}
function itemPropertyEntries(item){
 const covered=item.weaponStats?new Set(['Хват','Тип урона','Точность','Пробивание брони','Защита цели','Дальность','Скорость атаки','Восстановление оружия','Прерывание']):new Set();
 return Object.entries(item.properties||{}).filter(([k,v])=>k!=='gameData'&&!covered.has(k)&&v!=null&&v!=='');
}
function itemStatList(item){return itemStatEntries(item).map(([k,v])=>`<li><span>${esc(k)}</span><b>${esc(v)}</b></li>`).join('')}
function itemStatDefinitionList(item){return `<dl class="market-stats">${itemStatEntries(item).map(([k,v])=>`<dt>${esc(k)}</dt><dd>${esc(v)}</dd>`).join('')}</dl>`}
function weaponSummary(item){const s=item.weaponStats;return s?`<p class="item-use-summary">${esc(`${s.damageMin}–${s.damageMax} · ${s.randomDamage?'Случайный':s.damageTypes.join(' / ')} · Точность ${s.accuracyBonus>=0?'+':''}${s.accuracyBonus} · ${s.rangeMeters} м · Восстановление +${s.recoverySeconds} сек.`)}</p>`:''}
