const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict'),{execFileSync}=require('node:child_process');
const py=process.platform==='win32'?'.venv/Scripts/python.exe':(fs.existsSync('.venv/bin/python')?'.venv/bin/python':'python');
const payload=JSON.parse(execFileSync(py,['-c',`import json
from skill_checks import configuration,check_skills
from constants import ATTRIBUTES,SKILLS,SKILL_ATTRIBUTES
from database import Database
cases=[]
for i in range(15):
 a={n:5+i for n in ATTRIBUTES};s={n:(j*7+i*3)%100 for j,n in enumerate(SKILLS)}
 cases.append({'attributes':a,'skills':s,'expected':check_skills(a,s)})
base_cases=[]
for i in range(15):
 a={n:8+(j*3+i)%11 for j,n in enumerate(ATTRIBUTES)}
 base_cases.append({'attributes':a,'expected':{n:Database._skill_base(n,a) for n in SKILLS}})
print(json.dumps({'rules':configuration(),'cases':cases,'weights':SKILL_ATTRIBUTES,'baseCases':base_cases},ensure_ascii=True))`],{encoding:'utf8'}));
const ctx=vm.createContext({});vm.runInContext(fs.readFileSync('web/skill-checks.js','utf8'),ctx);const checks=vm.runInContext('SkillChecks',ctx);
for(const fixture of payload.cases)assert.deepEqual(JSON.parse(JSON.stringify(checks.calculate(payload.rules,fixture.attributes,fixture.skills))),fixture.expected,'Creation preview must match Python/API for every formula, maximum and half-point');
const rows=checks.calculate(payload.rules,payload.cases[0].attributes,payload.cases[0].skills),html=checks.render(rows,{preview:true});
for(const name of ['Запугивание','Влияние','Наблюдательность','Выносливость','Проницательность'])assert(html.includes(`data-check-skill="${name}"`));
assert(html.includes('<h2>Вне-боевые проверки</h2>'));assert(html.includes('data-no-game-help'));assert(!html.includes('data-step-kind='));
for(const removed of ['Это не боевая защита','модификатор:-2','Отдельных очков и опыта нет','data-help-text=','tabindex=','Влияние, восприятие и стойкость','Максимум среди','Бросок:','Без модификатора','check-skill-roll','check-skill-description','ПРОВЕРКИ ВНЕ БОЯ','<footer>'])assert(!html.includes(removed),removed);
rows.Влияние.sources[0].name='<script>bad</script>';assert(!checks.render(rows).includes('<script>bad</script>'));assert(checks.render(rows).includes('&lt;script&gt;'));
assert.deepEqual(JSON.parse(JSON.stringify(checks.calculate(null,{},{}))),{});
for(const path of ['web/index.html','web/archive.html']){const source=fs.readFileSync(path,'utf8');assert(source.includes('skill-checks.css?v=20261015-2'));assert(source.includes('skill-checks.js?v=20261015-2'));assert(source.includes('game-help.js?v=20261015-2'))}
const creation=fs.readFileSync('web/app.js','utf8'),archive=fs.readFileSync('web/archive.js','utf8');assert(creation.includes("checkTarget.innerHTML=SkillChecks.render(SkillChecks.calculate(state.config.checkSkills"));assert(archive.includes('${checkSkillsBox(c,data)}'));
assert(archive.includes('${checkSkillsBox(c,d)}'),'Public archive must use the opened record, not the signed-in character');
vm.runInContext(archive.split('\n').find(line=>line.startsWith('function checkSkillsBox(')),ctx);
assert.equal(ctx.checkSkillsBox({}, {derived:{checkSkills:rows}}),checks.render(rows));
vm.runInContext(creation.slice(creation.indexOf('function skillBase('),creation.indexOf('\nfunction sourceBonuses(')),ctx);
for(const fixture of payload.baseCases){ctx.state={attributes:fixture.attributes,config:{skillAttributes:payload.weights}};for(const [name,expected]of Object.entries(fixture.expected))assert.equal(ctx.skillBase(name),expected,`${name}: preview must match the database at exact halves`)}
const css=fs.readFileSync('web/skill-checks.css','utf8');assert(css.includes('@media(max-width:600px)'));assert(css.includes('@media(min-width:1700px)'));
const help=fs.readFileSync('web/game-help.js','utf8');assert(help.includes("p.closest('[data-no-game-help],script"));assert(help.includes("root.closest?.('[data-no-game-help]"));
console.log('Skill checks UI: one-third attribute parity across 15 builds, compact cards, no explanations/tooltips, creation/archive placement and phone/wide layout OK');
