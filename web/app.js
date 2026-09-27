const params = new URLSearchParams(location.search);
const token = params.get("token") || "";
const api = (params.get("api") || "").replace(/\/$/, "");
const state = { config:null, background:"", specs:[], name:"", portrait:"", attributes:{}, skills:{} };

const descriptions = {
  backgrounds:{
    "Военная знать":"Воспитание в традициях командования, риторики и военного искусства.","Гильдейский подмастерье":"Образование в магической гильдии и раннее знакомство с тайнами сигилов.",
    "Охотник в пустошах":"Следопыт, привыкший выживать вдали от закона и цивилизации.","Беззаконный":"Знание преступного мира, уловок и слабостей имперского порядка.",
    "Целитель":"Опыт сохранения жизни, лечения ран и распознавания телесных недугов.","Дипломат":"Риторика, наблюдательность и умение превращать обвинение в преимущество.",
    "Ученик войны":"Служба в армии Кайрос и дисциплина строевого бойца.","Маг-законотворец":"Сочетание права Тунона с практикой магии и исследованиями сигилов."
  },
  specs:{
    "Меч и щит":"Надёжная передовая защита, Парирование и контроль противника.","Двуручный меч":"Медленные, тяжёлые удары с высоким уроном и пробиванием.",
    "Короткий лук":"Дальний бой, мобильность и атаки вне зоны поражения врага.","Заклинания молний":"Электрический урон и прерывание вражеских действий.",
    "Заклинания рвения":"Усиление себя и союзников магией жизненной энергии.","Дротик":"Сочетание ближнего и метательного боя, хромота и преследование.",
    "Парное оружие":"Серия быстрых атак и гибкий выбор типов урона.","Безоружные атаки":"Высокая скорость, манёвренность и контроль ударами тела.",
    "Заклинания льда":"Холод замедляет и удерживает противников.","Заклинания истощения":"Ослабление характеристик и боевой эффективности врага."
  },
  attrs:{"Сила":"Физическая мощь и урон оружием.","Искусность":"Точность атак, заклинаний и отклонение брони.","Быстрота":"Скорость действий и сокращение перезарядок.","Живучесть":"Запас здоровья и сила личности.","Смекалка":"Обучаемость, знания и магический потенциал.","Решимость":"Сопротивление физическим и ментальным испытаниям."}
};
const tips={attributes:{title:"Характеристики",text:"В Tyranny каждая характеристика начинает со значения 10. При создании доступно ещё 8 очков. Значения можно снизить до 8, чтобы перенести освободившиеся очки в другие характеристики. Первичная характеристика даёт навыку 1,5 пункта за единицу, вторичная — 0,5."}};
const skillInfo={"Одноручное оружие":"Мечи, копья и другое оружие в одной руке.","Двуручное оружие":"Тяжёлые клинки и дробящее оружие.","Парное оружие":"Одновременное применение двух оружий.","Луки":"Точность и эффективность стрельбы.","Безоружный бой":"Удары без оружия.","Волшебный посох":"Атаки магическими посохами.","Атлетика":"Сложные движения, сила и запугивание.","Парирование":"Защита от атак ближнего боя.","Уклонение":"Защита от дальних атак.","Знания":"Сигилы, история и интеллектуальные проверки.","Хитроумие":"Скрытность, обман и обход препятствий."};

const $=selector=>document.querySelector(selector);
const esc=value=>String(value).replace(/[&<>"']/g,char=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[char]));

async function boot(){
  if(!token||!api){ return fail("Эта страница открыта без личной ссылки из Discord. Выполните /регистрация и используйте выданную кнопку."); }
  try{
    const response=await fetch(`${api}/api/registration/${encodeURIComponent(token)}`);
    const data=await response.json(); if(!response.ok||!data.ok) throw new Error(data.error||"Ссылка недействительна.");
    state.config=data.config;
    data.config.attributes.forEach(name=>state.attributes[name]=10);
    data.config.skills.forEach(name=>state.skills[name]=0);
    $("#connection").hidden=true; $("#form").hidden=false; renderAll();
  }catch(error){ fail(`Не удалось открыть личное дело: ${error.message}`); }
}
function fail(text){const box=$("#connection");box.className="connection error";box.textContent=text;}
function card(item,kind,index){const selected=kind==="background"?state.background===item:state.specs.includes(item);const desc=kind==="background"?descriptions.backgrounds[item]:descriptions.specs[item];return `<article class="card ${selected?"selected":""}"><span class="tag">${kind==="background"?"ПРОИСХОЖДЕНИЕ":`ПОДГОТОВКА ${String(index+1).padStart(2,"0")}`}</span><strong>${esc(item)}</strong><p>${esc(desc||"Описание будет дополнено архивом Тунона.")}</p><button data-kind="${kind}" data-value="${esc(item)}">${selected?"✓ ВЫБРАНО":"ВЫБРАТЬ →"}</button></article>`;}
function renderCards(){
  $("#backgrounds").innerHTML=state.config.backgrounds.map((x,i)=>card(x,"background",i)).join("");
  $("#specializations").innerHTML=state.config.specializations.map((x,i)=>card(x,"spec",i)).join("");
  $("#spec-counter").textContent=`Выбрано ${state.specs.length} из 2`;
}
function stepper(name,value,min,max,kind,description){return `<div class="stat-row"><span><b>${esc(name)}</b><small>${esc(description||"Дополнительная подготовка")}</small></span><div class="stepper"><button data-step-kind="${kind}" data-step-name="${esc(name)}" data-delta="-1" ${value<=min?"disabled":""}>−</button><output>${value}</output><button data-step-kind="${kind}" data-step-name="${esc(name)}" data-delta="1" ${value>=max?"disabled":""}>+</button></div></div>`;}
function renderAllocations(){
  $("#attributes").innerHTML=state.config.attributes.map(x=>stepper(x,state.attributes[x],state.config.attributeMin,state.config.attributeMax,"attribute",descriptions.attrs[x])).join("");
  $("#skills").innerHTML=state.config.skills.map(x=>stepper(x,state.skills[x],0,state.config.skillPoints,"skill",skillInfo[x]||"Магическая школа: точность и сила соответствующих заклинаний.")).join("");
  counter("#attribute-counter",Object.values(state.attributes).reduce((a,b)=>a+b,0),state.config.attributeTotal,"РАСПРЕДЕЛЕНО");
  counter("#skill-counter",Object.values(state.skills).reduce((a,b)=>a+b,0),state.config.skillPoints,"ДОПОЛНИТЕЛЬНЫХ ОЧКОВ");
}
function counter(selector,used,total,label){const box=$(selector);box.className=`counter ${used===total?"done":used>total?"over":""}`;box.innerHTML=`<b>${used}</b><span>/ ${total}</span><small>${used===total?"ГОТОВО":used>total?"ЛИШНИЕ ОЧКИ":label}</small>`;}
function ready(){return state.background&&state.specs.length===2&&state.name.trim().length>=2&&Object.values(state.attributes).reduce((a,b)=>a+b,0)===state.config.attributeTotal&&Object.values(state.skills).reduce((a,b)=>a+b,0)===state.config.skillPoints;}
function renderResult(){
  const checks=[["Происхождение",!!state.background],["Две специализации",state.specs.length===2],["Имя",state.name.trim().length>=2],["68 характеристик",Object.values(state.attributes).reduce((a,b)=>a+b,0)===68],["20 навыков",Object.values(state.skills).reduce((a,b)=>a+b,0)===20]];
  $("#checks").innerHTML=checks.map(([name,ok])=>`<span class="${ok?"ok":""}">${ok?"✓ ":""}${name}</span>`).join("");
  $("#submit").disabled=!ready();$("#result-title").textContent=ready()?"Дело готово к печати":"Завершите личное дело";$("#result-text").textContent=ready()?"Проверки пройдены. После сохранения ссылка станет недействительной, а персонаж появится в Discord.":"Заполните все разделы и распределите очки без остатка.";
  const topSkills=Object.entries(state.skills).filter(([,v])=>v>0).map(([n,v])=>`— ${n}: +${v}`).join("\n")||"— очки ещё не распределены";
  $("#summary").textContent=`⚖ АРХИВ ВЕРШИТЕЛЕЙ СУДЕБ\n══════════════════════════\n\nИмя: ${state.name||"Не указано"}\nПроисхождение: ${state.background||"Не выбрано"}\nСпециализации: ${state.specs.join(" · ")||"Не выбраны"}\n\n[ ХАРАКТЕРИСТИКИ ]\n${Object.entries(state.attributes).map(([n,v])=>`— ${n}: ${v}`).join("\n")}\n\n[ ДОПОЛНИТЕЛЬНАЯ ПОДГОТОВКА ]\n${topSkills}`;
}
function renderAll(){renderCards();renderAllocations();renderResult();}

document.addEventListener("click",event=>{
  const choice=event.target.closest("[data-kind]");if(choice){const value=choice.dataset.value;if(choice.dataset.kind==="background")state.background=value;else if(state.specs.includes(value))state.specs=state.specs.filter(x=>x!==value);else if(state.specs.length<2)state.specs.push(value);else state.specs=[state.specs[1],value];renderAll();return;}
  const step=event.target.closest("[data-step-kind]");if(step){const key=step.dataset.stepName,delta=Number(step.dataset.delta);if(step.dataset.stepKind==="attribute"){const next=state.attributes[key]+delta;if(next>=state.config.attributeMin&&next<=state.config.attributeMax)state.attributes[key]=next;}else{const next=state.skills[key]+delta;if(next>=0&&next<=state.config.skillPoints)state.skills[key]=next;}renderAllocations();renderResult();return;}
  const term=event.target.closest("[data-tip]");if(term){const tip=tips[term.dataset.tip];$("#tooltip-title").textContent=tip.title;$("#tooltip-text").textContent=tip.text;$("#tooltip").showModal();}
});
$("#tooltip-close").addEventListener("click",()=>$("#tooltip").close());
$("#name").addEventListener("input",event=>{state.name=event.target.value;renderResult();});
$("#portrait").addEventListener("change",event=>{const file=event.target.files[0];if(!file)return;if(file.size>5*1024*1024){alert("Максимальный размер портрета — 5 МБ.");event.target.value="";return;}const reader=new FileReader();reader.onload=()=>{state.portrait=reader.result;$("#portrait-preview").src=reader.result;$("#portrait-preview").hidden=false;$("#portrait-empty").hidden=true;};reader.readAsDataURL(file);});
$("#submit").addEventListener("click",async()=>{
  if(!ready())return;const button=$("#submit"),status=$("#submit-status");button.disabled=true;button.textContent="СОХРАНЯЕМ…";status.textContent="Отправляем личное дело в архив Тунона.";
  try{const response=await fetch(`${api}/api/registration/${encodeURIComponent(token)}`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({name:state.name.trim(),background:state.background,specialization1:state.specs[0],specialization2:state.specs[1],attributes:state.attributes,skills:state.skills,portrait:state.portrait})});const data=await response.json();if(!response.ok||!data.ok)throw new Error(data.error||"Ошибка сохранения.");button.textContent="✓ СОХРАНЕНО В DISCORD";status.textContent=`Личное дело «${data.name}» создано. Вернитесь в Discord и используйте /персонаж.`;}catch(error){button.disabled=false;button.textContent="ПОВТОРИТЬ СОХРАНЕНИЕ";status.textContent=error.message;}
});
boot();
