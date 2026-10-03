/* Character development retains base values; previews and readouts use equipment. */
function equippedCharacter(c){
 const d=data?.derived||{};
 return {...c,health_max:d.healthMax??c.health_max,attributes:{...c.attributes,...d.effectiveAttributes},skills:Object.fromEntries(Object.entries(c.skills||{}).map(([name,row])=>[name,{...row,value:d.effectiveSkills?.[name]??row.value}]))};
}
const baseSkillsBox=skillsBox;
const baseEquipmentInventory=renderInventory;
renderInventory=function(p,c){baseEquipmentInventory(p,equippedCharacter(c));if(Object.keys(data.itemEffects||{}).length)p.querySelector('.combat-sheet')?.insertAdjacentHTML('beforeend',`<h3>Эффекты предметов</h3>${Object.values(data.itemEffects).map(s=>`<p>${esc(s.name)}</p>`).join('')}`)};
const equipmentStatIcon=statIcon;
statIcon=function(file,label,value,help=''){return equipmentStatIcon(file,label,file==='recovery.png'?scaledRoundText(data.derived?.attack?.recovery||0):value,help)};
skillsBox=function(c){return baseSkillsBox(equippedCharacter(c))};
const baseSpellFormulaState=spellFormulaState;
spellFormulaState=function(c){return baseSpellFormulaState(equippedCharacter(c))};
const baseSpellNumbers=spellNumbers;
spellNumbers=function(state,c){const numbers=baseSpellNumbers(state,equippedCharacter(c));return {...numbers,power:Math.round(numbers.power*(data?.derived?.spellPowerMultiplier??1))}};
const equipmentItemDetails=openItemDetails;
openItemDetails=function(id){
 equipmentItemDetails(id);
 const item=data.inventory.find(i=>Number(i.inventory_id)===Number(id));if(!item)return;
 if(item.category==='Броня'&&!item.armor)document.querySelector('#item-dialog-body ul')?.insertAdjacentHTML('afterbegin','<li><span>Броня</span><b>0</b></li>');
 const recovery=[...document.querySelectorAll('#item-dialog-body li')].find(e=>e.querySelector('span')?.textContent==='Восстановление');if(recovery)recovery.querySelector('b').textContent=scaledRoundText(item.recovery);
 if(item.properties?.gameData?.useComponents?.length){
  document.querySelector('.item-dialog-actions')?.insertAdjacentHTML('beforeend',`<button class="action" data-consume-item="${item.inventory_id}">ПРИМЕНИТЬ</button>`);
 }
};
const equipmentActionButton=combatActionButton;
combatActionButton=function(action,extra=''){const html=equipmentActionButton(action,extra);return action.displayName?html.replace(`<b>${esc(action.name)}</b>`,`<b>${esc(action.displayName)}</b>`):html};
document.addEventListener('click',async e=>{
 const button=e.target.closest('[data-consume-item]');if(!button)return;
 button.disabled=true;
 try{await mutate('item/use',{inventoryId:Number(button.dataset.consumeItem)});document.querySelector('#item-dialog').close()}finally{button.disabled=false}
});
