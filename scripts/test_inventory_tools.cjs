const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const source=fs.readFileSync('web/archive.js','utf8');
const funcs=['itemVisual','emptyEquipmentIcon','equipmentSlot','compatibleSlots','inventoryCategoryMatches','inventoryFilters','talentIcon','sigilIcon'];
const ctx=vm.createContext({esc:v=>String(v??'').replaceAll('<','&lt;'),localTalentIcon:v=>v,data:{equipmentLimits:{weaponSets:2,quickSlots:4}},inventoryCategory:'all',inventoryGroups:[['all','Все','all'],['weapons','Оружие','weapons']]});
for(const name of funcs)vm.runInContext(source.split('\n').find(line=>line.startsWith(`function ${name}(`)),ctx);
for(const name of ['itemVisual','talentIcon','sigilIcon']){
 const html=ctx[name]({name:'Доспех',image_url:'transparent.png',icon_url:'transparent.png'});
 assert(!html.includes('<i>Д')&&!html.includes('<b>Д')&&!html.includes('talent-fallback'));
 assert(html.includes('<img'));
}
for(const [slot,icon] of [['Голова','head'],['Торс','torso'],['Руки','hands'],['Ноги','feet'],['Аксессуар 1','accessory'],['Быстрый предмет 1','quick'],['Оружие I — правая рука','weapon'],['Оружие I — левая рука','shield']]){
 assert(ctx.emptyEquipmentIcon(slot).includes(`slot-${icon}.png`));
 assert(fs.existsSync(`web/assets/inventory-icons/slot-${icon}.png`));
 assert(!ctx.equipmentSlot(slot,'','',{}).includes('◇'));
}
const staff={category:'Посохи',hands:2};
assert.equal(ctx.compatibleSlots(staff).length,2);assert(ctx.compatibleSlots(staff).every(s=>s.includes('правая рука')));
assert.equal(ctx.compatibleSlots({category:'Одноручное оружие',hands:1}).length,4);
assert(ctx.compatibleSlots({category:'Щиты',hands:0}).every(s=>s.includes('левая рука')));
for(const [category,group] of [['Посохи','weapons'],['Щиты','weapons'],['Броня','armor'],['Аксессуары','accessories'],['Зелья','consumables'],['Материалы','materials'],['Сигилы','other'],['Разное','other']]){
 assert(ctx.inventoryCategoryMatches({category},group));assert(ctx.inventoryCategoryMatches({category},'all'));
 assert(!ctx.inventoryCategoryMatches({category},group==='weapons'?'other':'weapons'));
}
assert(ctx.inventoryFilters().includes('data-inventory-category="all" aria-pressed="true"'));
assert(source.includes('const twoHanded=bySlot'));
const render=source.slice(source.indexOf('function renderCabinet()'),source.indexOf('function renderTab('));
assert(render.includes('data-edit-portrait'));assert(!render.includes('specialization_1'));
console.log('Inventory: no letter layers, original empty slots, all category buttons, one/two-handed slots and class-only heading OK');
