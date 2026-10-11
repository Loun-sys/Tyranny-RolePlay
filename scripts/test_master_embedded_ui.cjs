const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const listeners={},messages=[],warnings=[],renders=[];
const parent={postMessage:(data,origin)=>messages.push({data,origin})};
const window={parent,addEventListener(type,fn){listeners[type]=fn},dispatchEvent(event){listeners.message(event)}};
const ctx=vm.createContext({q:new URLSearchParams('embed=1'),window,location:{origin:'http://qa'},document:{documentElement:{classList:{add(){}}},addEventListener(){}},
 masterEmbeddedPaused:false,combatBusy:false,masterScene:{controller:{canAct:true}},data:{character:{}},$:()=>({}),setCombatBusy(value){ctx.combatBusy=value},toast:m=>warnings.push(m),clearCombatAim(){ctx.cleared=true},renderTraining(){renders.push(true)}});
const code=fs.readFileSync('web/master-combat.js','utf8').split('// A separate document keeps')[1];
vm.runInContext('// A separate document keeps'+code,ctx);
assert.equal(messages[0].data.type,'tyranny-master-busy');assert.equal(messages[0].origin,'http://qa');
function pause(source=parent,origin='http://qa'){listeners.message({source,origin,data:{type:'tyranny-master-pause'}})}
pause({},'http://qa');pause(parent,'http://foreign');assert.equal(ctx.masterEmbeddedPaused,false);
vm.runInContext('setCombatBusy(true)',ctx);pause();assert.equal(ctx.masterEmbeddedPaused,false);assert.equal(messages.filter(m=>m.data.type==='tyranny-master-paused').length,0);assert.equal(warnings.length,1);
vm.runInContext('setCombatBusy(false)',ctx);pause();assert.equal(ctx.masterEmbeddedPaused,true);assert.equal(ctx.masterScene.controller.canAct,false);assert.equal(renders.length,1);assert(ctx.cleared);assert.equal(messages.at(-1).data.type,'tyranny-master-paused');
console.log('Embedded NPC turns: source/origin checks, pending action cannot be unloaded, explicit pause handshake, busy notification and fail-closed HUD OK');
