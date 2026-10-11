const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const source=fs.readFileSync('web/combat-ui.js','utf8');
const start=source.indexOf('function hudRecoveryStatus('),end=source.indexOf('\nfunction combatJournal(',start);
const context=vm.createContext({esc:v=>String(v)});
vm.runInContext(source.slice(start,end),context);
assert.equal(context.hudRecoveryStatus(undefined),'');
assert.equal(context.hudRecoveryStatus({equipmentRecovery:0}),'');
assert.equal(context.hudRecoveryStatus({recoverySeconds:30}),''); // Legacy busy timer is no longer an action lock.
assert(context.hudRecoveryStatus({equipmentRecovery:2}).includes('+2 раунд. к перезарядке'));
assert(!context.hudRecoveryStatus({equipmentRecovery:2}).includes('50%'));
assert(context.hudRecoveryStatus({equipmentRecovery:2}).includes('округляется вверх один раз'));
assert(context.hudRecoveryStatus({equipmentRecovery:2}).includes('Не отнимает действие'));
assert(!source.includes('основное действие недоступно'));
assert(source.includes("insertAdjacentHTML('afterend',hudRecoveryStatus(turn))"));
console.log('Equipment recovery HUD: summed/rounded cooldown surcharge, no action lock OK');
