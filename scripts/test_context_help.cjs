const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const source=fs.readFileSync('web/app.js','utf8').replace(/\nboot\(\);\s*$/,'');
const events={},nodes={},timers=new Map();let timerId=0;
function setTimeoutMock(fn){timers.set(++timerId,fn);return timerId}
function clearTimeoutMock(id){timers.delete(id)}
function node(selector){return nodes[selector]??={hidden:true,innerHTML:'',textContent:'',dataset:{},style:{},offsetHeight:180,value:'',classList:{},addEventListener(){},contains(value){return value===this},querySelector(part){return node(selector+' '+part)}}}
const skills=['Одноручное оружие','Двуручное оружие','Парное оружие','Луки','Безоружный бой','Волшебный посох','Атлетика','Парирование','Уклонение','Знания','Хитроумие','Управление истощением','Управление эмоциями','Управление огнём','Управление силой','Управление холодом','Управление могильным светом','Управление иллюзиями','Управление жизнью','Управление молниями','Управление камнем','Управление рвением'];
const attributes=['Сила','Искусность','Быстрота','Живучесть','Смекалка','Стойкость'];
const config={skills,attributes,attributeDetails:Object.fromEntries(attributes.map(name=>[name,{summary:name+': описание',effects:name+' +3: точный модификатор'}])),skillAttributes:Object.fromEntries(skills.map(name=>[name,['Сила','Искусность']])),skillPoints:20,attributeTotal:68,attributeMin:8,attributeMax:18,backgrounds:['Книгочей'],backgroundDetails:{Книгочей:{description:'Поддержка',bonuses:{Знания:6}}},specializations:['Меч и щит'],specializationDetails:{'Меч и щит':{description:'Описание подготовки',bonuses:{Парирование:5},abilities:[{name:'Удар щитом',description:'Удар',cooldown:'3 раунда',duration:'2 раунда',effects:['Оглушение'],requirements:'Нужен щит',icon:'test.png'}]}}};
const ctx=vm.createContext({config,entries:JSON.parse(fs.readFileSync('web/data/encyclopedia.json','utf8')).entries,setTimeout:setTimeoutMock,clearTimeout:clearTimeoutMock,document:{querySelector:node,addEventListener(name,fn){(events[name]??=[]).push(fn)}},window:{addEventListener(){}},location:{search:''},URLSearchParams,innerWidth:500,innerHeight:600});
vm.runInContext(source,ctx);
vm.runInContext('state.config=config;config.attributes.forEach(n=>state.attributes[n]=10);config.skills.forEach(n=>state.skills[n]=0);applyCreationGlossary(entries)',ctx);
for(const name of skills){
 const help=vm.runInContext(`glossary[${JSON.stringify(name)}]`,ctx);
 assert(help?.text.length>30,name);assert(!help.text.includes('Навык применения заклинаний:'),name);
 assert(ctx.skillRow(name).includes('data-help-text='));
}
assert(vm.runInContext("glossary['Управление силой'].text",ctx).includes('Сигил Мощи'));
assert(vm.runInContext("glossaryLookup.get(glossaryKey('Управление огнем'))",ctx));
assert(!vm.runInContext("glossary['Оглушение'].text",ctx).includes('[url='));
for(const name of attributes)assert(vm.runInContext(`glossary[${JSON.stringify(name)}].text`,ctx).includes('точный модификатор'));
ctx.renderBackgrounds();ctx.renderSpecializations(0);ctx.renderAttributes();ctx.renderSkills();
assert(node('#backgrounds').innerHTML.includes('data-help-title="Книгочей"'));
assert(node('#primary-specializations').innerHTML.includes('data-help-text='));
assert(node('#primary-detail').innerHTML.includes('Перезарядка: 3 раунда.'));
assert(node('#skill-counter').dataset.helpText.includes('20'));
assert(ctx.helpAttrs('<img>', '"onclick="bad').includes('&lt;img&gt;'));
ctx.bindEvents();
const term={dataset:{glossary:'Оглушение'},getBoundingClientRect:()=>({left:470,bottom:580,top:550}),contains:()=>false};
events.focusin[0]({target:{closest:()=>term}});
assert(!node('#glossary-tooltip').hidden);assert(node('#glossary-tooltip p').textContent.includes('30'));
assert.equal(node('#glossary-tooltip').style.left,'68px');assert.equal(node('#glossary-tooltip').style.top,'360px');
events.keydown[0]({key:'Escape'});assert(node('#glossary-tooltip').hidden);
const custom={...term,dataset:{helpTitle:'Расчёт',helpText:'+4 к навыку'}};ctx.showGlossary(custom);
assert.equal(node('#glossary-tooltip p').textContent,'+4 к навыку');
events.scroll[0]({target:node('#glossary-tooltip')});assert(!node('#glossary-tooltip').hidden);
events.scroll[0]({target:{}});assert(node('#glossary-tooltip').hidden);
custom.contains=value=>value===custom;ctx.document.activeElement=custom;ctx.showGlossary(custom);
events.scroll[0]({target:{}});assert(!node('#glossary-tooltip').hidden,'automatic scroll must not hide keyboard-focused help');
ctx.document.activeElement=null;ctx.scheduleHideGlossary();assert(!node('#glossary-tooltip').hidden,'pointer can cross the gap into the tooltip');
events.pointerover[0]({target:{closest:selector=>selector==='#glossary-tooltip'?node('#glossary-tooltip'):null}});assert.equal(timers.size,0,'entering tooltip cancels pending hide');
ctx.scheduleHideGlossary();for(const callback of [...timers.values()])callback();assert(node('#glossary-tooltip').hidden);
const archiveSource=fs.readFileSync('web/archive.js','utf8'),popover={style:{},offsetHeight:200,hidden:true};
const archive=vm.createContext({$:()=>popover,esc:s=>String(s||'').replaceAll('<','&lt;'),findEncyclopedia:()=>null,encyclopediaEntry:()=>null,glossaryPlain:ctx.glossaryText,contextHideTimer:null,clearTimeout:clearTimeoutMock,innerWidth:500,innerHeight:600});
for(const name of ['tip','showContextPopover'])vm.runInContext(archiveSource.split('\n').find(line=>line.startsWith(`function ${name}(`)),archive);
const fallback=archive.tip('Броня','<эффект>');assert(fallback.includes('data-context-text="&lt;эффект>"'));assert(fallback.includes('tabindex="0"'));
archive.showContextPopover({...term,dataset:{contextTitle:'Броня',contextText:'Поглощает урон'}});assert(popover.innerHTML.includes('Поглощает урон'));
assert(archiveSource.includes("document.addEventListener('focusin'"));
console.log('Context help: all 22 creation skills, exact attribute effects, source statuses, class/spec/ability hints, escaping, viewport bounds, keyboard and fallback popovers OK');
