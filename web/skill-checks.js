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
   const skill=sources.reduce((sum,s)=>sum+s.value*.5,0),attribute=value(attributes[definition.attribute]),bonus=Math.floor(attribute/3+.5),dice=Math.max(0,Math.floor(skill/10));
   return [definition.name,{...definition,sources,value:skill,attributeValue:attribute,attributeBonus:bonus,diceCount:dice,formula:`${bonus} + ${dice}d6`,minimum:bonus+dice,maximum:bonus+dice*6}];
  }));
 }
 function render(checks){
  if(!checks||!Object.keys(checks).length)return '';
  const icons={'Живучесть':'health','Смекалка':'wits','Быстрота':'quickness','Стойкость':'resolve','Искусность':'finesse'};
  return `<section class="box check-skills" data-no-game-help aria-label="Вне-боевые проверки"><header><h2>Вне-боевые проверки</h2></header><div class="check-skill-grid">${Object.values(checks).map(row=>{
   return `<article class="check-skill-card" data-check-skill="${escape(row.name)}">
    <header><h3>${escape(row.name)}</h3><b class="check-skill-value">${number(row.value)}</b></header>
    <p class="check-skill-formula">${row.sources.map(s=>`<span>${escape(s.name)} <b>${number(s.value)}</b> × 0,5</span>`).join('<i> + </i>')}</p>
    <div class="check-skill-roll"><img src="assets/game-combat/icon_attribute_${icons[row.attribute]||'wits'}.png" alt=""><span>${escape(row.attribute)} <b>${number(row.attributeBonus)}</b></span><strong>+ ${row.diceCount}d6</strong></div>
    <small class="check-skill-range">Без модификатора: ${number(row.minimum)}${row.minimum!==row.maximum?'–'+number(row.maximum):''}</small>
    </article>`;
  }).join('')}</div></section>`;
 }
 return {calculate,render};
})();
