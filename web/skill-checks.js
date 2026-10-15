/* Shared creation/dossier projection. Definitions come from the server; there
 * are no allocatable points, XP counters or combat-defense overrides here. */
const SkillChecks=(()=>{
 const escape=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
 const number=v=>Number(v).toLocaleString('ru-RU',{maximumFractionDigits:1});
 const value=v=>Number(typeof v==='object'&&v!==null?v.value??0:v??0);
 function calculate(rules,attributes,skills){
  if(!rules?.definitions?.length||!rules.combatSkills?.length)return {};
  const candidates=rules.combatSkills,maximum=Math.max(...candidates.map(n=>value(skills[n]))),tied=candidates.filter(n=>value(skills[n])===maximum);
  return Object.fromEntries(rules.definitions.map(definition=>{
   const sources=definition.sources.map(source=>({name:source==='@combatMax'?tied[0]:source,value:value(skills[source==='@combatMax'?tied[0]:source]),weight:.5,...(source==='@combatMax'?{combatMaximum:true,tiedSkills:tied}:{})}));
   const skill=sources.reduce((sum,s)=>sum+s.value*.5,0),attribute=value(attributes[definition.attribute]),dice=Math.max(0,Math.floor(skill/10));
   return [definition.name,{...definition,sources,value:skill,attributeValue:attribute,diceCount:dice,formula:`${attribute} + ${dice}d6`,minimum:attribute+dice,maximum:attribute+dice*6}];
  }));
 }
 function render(checks,{preview=false}={}){
  if(!checks||!Object.keys(checks).length)return '';
  const icons={'Живучесть':'health','Смекалка':'wits','Быстрота':'quickness','Стойкость':'resolve','Искусность':'finesse'};
  return `<section class="box check-skills" aria-label="Навыки проверок вне боя"><header><div><small>ПРОВЕРКИ ВНЕ БОЯ</small><h2>Влияние, восприятие и стойкость</h2></div><p>Рассчитываются автоматически. Отдельных очков и опыта нет.${preview?' Меняйте характеристики и подготовку — значения обновятся. Предпросмотр без бонусов экипировки.':' Учитываются текущие характеристики, навыки и активная экипировка.'}</p></header><div class="check-skill-grid">${Object.values(checks).map(row=>{
   const formula=row.sources.map(s=>`${s.name} ${number(s.value)} × 0,5`).join(' + '),maximum=row.sources.find(s=>s.combatMaximum);
   const ties=maximum?.tiedSkills?.length>1?`\nРавные максимумы: ${maximum.tiedSkills.join(', ')}.`:'';
   const text=`${row.description}\n\n${formula} = ${number(row.value)}.\nБросок: ${row.attribute} ${number(row.attributeValue)} + ${row.diceCount}d6.\nЗа каждые полные 10 навыка даётся 1d6. При навыке ниже 10 бросок равен характеристике плюс модификатор.${ties}`;
   return `<article class="check-skill-card" data-check-skill="${escape(row.name)}">
    <header><h3 tabindex="0" data-help-title="${escape(row.name)} · проверка вне боя" data-help-text="${escape(text)}">${escape(row.name)}</h3><b class="check-skill-value">${number(row.value)}</b></header>
    <p class="check-skill-formula">${row.sources.map(s=>`<span>${escape(s.name)} <b>${number(s.value)}</b> × 0,5</span>`).join('<i> + </i>')}</p>
    ${maximum?`<p class="check-skill-source-note">Максимум среди оружейных навыков и магических школ.${maximum.tiedSkills?.length>1?` Равных максимумов: ${maximum.tiedSkills.length}.`:''}</p>`:''}
    <p class="check-skill-description">${escape(row.description)}</p>
    <div class="check-skill-roll"><img src="assets/game-combat/icon_attribute_${icons[row.attribute]||'wits'}.png" alt=""><span>${escape(row.attribute)} <b>${number(row.attributeValue)}</b></span><strong>+ ${row.diceCount}d6</strong></div>
    <small class="check-skill-range">Без модификатора: ${number(row.minimum)}${row.minimum!==row.maximum?'–'+number(row.maximum):''}</small></article>`;
  }).join('')}</div><footer><p><b>Бросок:</b> характеристика + 1d6 за каждые полные 10 навыка + модификатор. Например: навык 20 и характеристика 5 → 5 + 2d6. Значение навыка сохраняет половинки; число кубиков округляется вниз.</p><p>В Дискорде: <code>/проверка навык:Влияние модификатор:-2</code>. Положительный модификатор прибавляется к итогу, отрицательный вычитается. Результат оценивает мастер.</p></footer></section>`;
 }
 return {calculate,render};
})();
