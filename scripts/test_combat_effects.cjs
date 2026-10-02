const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const events=[],nodes=[];
const layer={isConnected:true,style:{setProperty(){}},append(node){nodes.push(node);events.push(node.className)},getBoundingClientRect(){return {width:800,height:600}}};
const context=vm.createContext({
 document:{addEventListener(){},querySelector:s=>s==='.combat-vfx-layer'?layer:null,createElement(){return {style:{},animate(){return {finished:Promise.resolve()}},remove(){this.removed=true}}}},
 renderTraining(){},combatPickerPanel(){},statsBox(){},localTalentIcon(){},sigilIcon(){},
 matchMedia:()=>({matches:false}),
});
vm.runInContext(fs.readFileSync('web/combat-ui.js','utf8'),context);
context.grid={width:15,height:10,tokens:[{id:'player',x:2,y:4}]};
async function run(action){events.length=0;nodes.length=0;context.action=action;await vm.runInContext('playCombatEffect(action,{x:8,y:4},grid,[])',context);assert(nodes.every(n=>n.removed),'Every temporary effect must be cleaned up');return [...events]}
(async()=>{
 let result=await run({kind:'attack',range:1});assert(result.includes('combat-slash'));
 result=await run({kind:'attack',range:12,weaponSkill:'Луки'});assert(result.includes('combat-arrow'));assert(result.indexOf('combat-arrow')<result.indexOf('combat-hit-spark'));
 result=await run({kind:'spell',range:12,core:'Огонь',targeting:'unit'});assert(result.indexOf('combat-magic-orb')<result.indexOf('combat-spell-bloom'));
 result=await run({kind:'spell',range:12,core:'Молния',targeting:'unit'});assert(result.includes('combat-energy-beam'));
 result=await run({kind:'spell',range:0,core:'Жизнь',targeting:'self'});assert(!result.includes('combat-magic-orb'));
 console.log('Combat effects: melee, arrow, spell flight before impact, lightning, self-cast and cleanup OK');
})().catch(error=>{console.error(error);process.exitCode=1});
