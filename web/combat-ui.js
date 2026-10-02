/* Targeting and original-game HUD. All highlighted cells come from the server. */
let armedCombatAction=null,combatAim=null,combatBusy=false;
const gameCombatRoot='assets/game-combat/';
const coreTexture={Огонь:'Core-Fire',Холод:'Core-Frost',Молния:'Core-Shock',Жизнь:'Core-Heal',Истощение:'Core-Weaken',Эмоции:'Core-Passion',Рвение:'Core-Passion',Сила:'Core-Strength',Камень:'Core-Stone',Терратус:'Core-Gravelight',Иллюзия:'Core-Illusion'};
const existingRenderTraining=renderTraining;
const originalCombatPickerPanel=combatPickerPanel;
combatPickerPanel=function(t){return combatPicker==='initiative'?'':originalCombatPickerPanel(t).replace('Нажатие применяет его сразу.','Нажатие включает прицеливание; затем выберите цель на карте.')};
function combatGlyph(action){
 if(action.kind==='spell')return `<img src="${gameCombatRoot}${coreTexture[action.core]||'Core-Strength'}.png" alt="">`;
 if(action.icon)return `<img src="${esc(localTalentIcon(action.icon))}" alt="" onerror="this.remove()">`;
 const talent=(data?.talentLibrary||[]).find(t=>t.name===action.name);
 if(talent?.icon_url)return `<img src="${esc(localTalentIcon(talent.icon_url))}" alt="" onerror="this.remove()">`;
 return `<img src="assets/stat-icons/${action.kind==='attack'?'damage':'accuracy'}.png" alt="">`;
}
renderTraining=function(panel,character){
 existingRenderTraining(panel,character);
 if(!training?.active)return;
 const t=training,d=t.derived||{},a=d.attack||{},turn=t.turn||{},player=(t.grid.tokens||[]).find(x=>x.id==='player'),hud=panel.querySelector('.tyranny-combat-hud');
 const stat=(icon,value,label)=>`<span title="${esc(label)}"><img src="assets/stat-icons/${icon}.png" alt="">${esc(value)}</span>`;
 const slots=Array.from({length:5},(_,i)=>{const x=quickbarAction(i+1,t.actions||[]);return `<button class="original-quick ${x?.remaining?'cooling':''}" data-quick-slot="${i+1}" ${x?`data-training-kind="${esc(x.kind)}" data-training-name="${esc(x.name)}"`:''} title="${esc(x?.name||'Назначить действие')}" ${t.finished?'disabled':''}>${x?combatGlyph(x):'<span>+</span>'}<kbd>${i+1}</kbd>${x?.remaining?`<i>${x.remaining}</i>`:''}</button>`}).join('');
 const portrait=t.character.portraitUrl?`<img src="${esc(t.character.portraitUrl)}" alt="${esc(character.name)}">`:`<span>${esc(character.name[0])}</span>`;
 const menu=(key,icon,label)=>`<button data-combat-picker="${key}" title="${label}" aria-label="${label}"><img src="${icon}" alt=""></button>`;
 hud.innerHTML=`<div class="original-hud-name">${esc(character.name)}</div><div class="original-hotkeys">${slots}<button class="edit-hotkeys" data-combat-picker="ability" title="Назначить быстрые действия">+</button></div><div class="original-hud-body"><div class="original-portrait">${portrait}<div class="original-hp" style="--hp:${Math.max(0,(player?.health||0)/Math.max(1,player?.healthMax||1)*100)}%"></div><i>${character.level||1}</i></div><div class="original-hud-values"><div class="original-stat-row">${stat('health',player?.health||0,'Здоровье')}${stat('accuracy',a.accuracy||0,'Точность')}${stat('damage',`${a.damageMin}–${a.damageMax}`,'Урон оружия')}</div><div class="original-stat-row">${stat('endurance',d.defenses?.Выносливость||0,'Защита Выносливостью')}${stat('will',d.defenses?.Воля||0,'Защита Волей')}${stat('magic',d.defenses?.Магия||0,'Защита Магией')}</div><div class="original-stat-row">${stat('dodge',d.defenses?.Уклонение||0,'Уклонение')}${stat('parry',d.defenses?.Парирование||0,'Парирование')}${stat('armor',d.armor||0,'Броня')}</div><div class="original-turn">${turn.movementRemaining} / ${turn.movementMax} м · ${turn.actionAvailable?'Действие готово':'Действие потрачено'}</div><div class="original-menus"><button data-training-kind="attack" data-training-name="Обычная атака" title="Атаковать"><img src="assets/stat-icons/damage.png" alt=""></button>${menu('ability','assets/stat-icons/accuracy.png','Умения')}${menu('spell',gameCombatRoot+'Core-Shock.png','Заклинания')}${menu('stance','assets/stat-icons/parry.png','Стойки')}${menu('initiative','assets/stat-icons/will.png','Инициатива и журнал')}<button data-training-kind="end_turn" title="Завершить ход"><img src="assets/stat-icons/recovery.png" alt=""></button></div></div></div><div class="original-sets">${Array.from({length:t.character.weaponSets||2},(_,i)=>`<button class="${t.character.activeWeaponSet===i+1?'active':''}" data-training-set="${i+1}">${['I','II','III','IV'][i]}</button>`).join('')}<small>${t.activeStance?esc(t.activeStance):'Стойка не выбрана'}</small></div>`;
 panel.querySelector('.tactical-map').insertAdjacentHTML('beforeend','<div class="combat-targeting-banner" hidden></div><div class="combat-action-tooltip" hidden></div><div class="combat-vfx-layer" aria-hidden="true"></div>');
 // Distant targets must not prevent entering targeting mode.
 panel.querySelectorAll('[data-training-kind]').forEach(button=>{const x=(t.actions||[]).find(x=>x.kind===button.dataset.trainingKind&&x.name===button.dataset.trainingName);if(x){button.disabled=!quickbarEditing&&!!(t.finished||x.remaining||!turn.actionAvailable);button.removeAttribute('data-effect-cells');button.title=x.description||x.name;const status=button.querySelector('em');if(status)status.textContent=x.remaining?`Готово через ${x.remaining} раунд.`:`Дальность: ${x.range||0} м · выберите цель`;}});
 panel.querySelectorAll('[data-action-kind]').forEach(button=>{const x=(t.actions||[]).find(x=>x.kind===button.dataset.actionKind&&x.name===button.dataset.actionName);if(x)button.querySelector('img, .sigil-icon, span')?.replaceWith(document.createRange().createContextualFragment(combatGlyph(x)))});
 if(armedCombatAction){armedCombatAction=(t.actions||[]).find(x=>x.kind===armedCombatAction.kind&&x.name===armedCombatAction.name)||null;if(!turn.actionAvailable||armedCombatAction?.remaining)clearCombatAim();else showCombatAim(combatAim||{x:player.x,y:player.y})}
};
function clearCombatAim(){armedCombatAction=null;combatAim=null;document.querySelectorAll('.aim-range,.aim-effect,.aim-target,.aim-invalid').forEach(e=>e.classList.remove('aim-range','aim-effect','aim-target','aim-invalid'));document.querySelectorAll('[data-aim-enabled]').forEach(cell=>{cell.disabled=true;delete cell.dataset.aimEnabled});document.querySelector('.tactical-map')?.classList.remove('targeting');const banner=document.querySelector('.combat-targeting-banner');if(banner)banner.hidden=true;document.querySelector('.spell-trajectory')?.classList.remove('visible')}
function showCombatAim(point){
 if(!armedCombatAction||!training?.active)return;
 combatAim=point;const action=armedCombatAction,aim=action.aims?.[`${point.x}:${point.y}`],player=training.grid.tokens.find(t=>t.id==='player'),map=document.querySelector('.tactical-map');
 map.classList.add('targeting');map.dataset.previewTargeting=action.targeting||'unit';
 document.querySelectorAll('.aim-range,.aim-effect,.aim-target,.aim-invalid').forEach(e=>e.classList.remove('aim-range','aim-effect','aim-target','aim-invalid'));
 document.querySelectorAll('[data-cell]').forEach(cell=>{if(cell.disabled){cell.dataset.aimEnabled='1';cell.disabled=false}const [x,y]=cell.dataset.cell.split(':').map(Number);if(Math.max(Math.abs(x-player.x),Math.abs(y-player.y))<=(action.range||0))cell.classList.add('aim-range')});
 for(const cell of aim?.cells||[])document.querySelector(`[data-cell="${cell.x}:${cell.y}"]`)?.classList.add('aim-effect');
 document.querySelector(`[data-cell="${point.x}:${point.y}"]`)?.classList.add(aim?.valid?'aim-target':'aim-invalid');
 const banner=document.querySelector('.combat-targeting-banner');banner.hidden=false;banner.classList.toggle('invalid',!aim?.valid);banner.textContent=`${action.name} · ${aim?.valid?'Нажмите для применения':'Недоступная цель или клетка'} · Esc / ПКМ — отмена`;
 const line=document.querySelector('.spell-trajectory line');if(line){line.setAttribute('x2',point.x+.5);line.setAttribute('y2',point.y+.5);line.parentElement.classList.add('visible')}
}
function armCombatAction(action){if(combatBusy)return;if(action.remaining||!training.turn.actionAvailable){toast(action.remaining?`Перезарядка: ${action.remaining} раунд.`:'Основное действие потрачено');return}armedCombatAction=action;combatPicker='';quickbarEditing=0;renderTraining($('#panel'),data.character);const player=training.grid.tokens.find(t=>t.id==='player');showCombatAim(action.targeting==='self'||action.targeting==='aura'?player:training.grid.tokens.find(t=>t.selected)||player)}
async function confirmCombatAim(point){
 if(combatBusy||!armedCombatAction)return;const action=armedCombatAction,aim=action.aims?.[`${point.x}:${point.y}`];if(!aim?.valid){toast('Выберите доступную цель или клетку.');return}
 const target=training.grid.tokens.find(t=>t.x===point.x&&t.y===point.y&&t.team==='enemy');
 const oldGrid=training.grid;combatBusy=true;
 try{const j=await request(`/api/portal/${encodeURIComponent(token)}/training/action`,{method:'POST',body:JSON.stringify({kind:action.kind,name:action.name,x:point.x,y:point.y,targetId:target?.id})});training=j.training;clearCombatAim();renderTraining($('#panel'),data.character);playCombatEffect(action,point,oldGrid,aim.cells||[]);toast(j.message)}catch(error){toast(error.message)}finally{combatBusy=false}
}
function playCombatEffect(action,point,grid,cells){
 const layer=document.querySelector('.combat-vfx-layer');if(!layer)return;const player=grid.tokens.find(t=>t.id==='player'),core=action.core||'Сила';
 const textures={Огонь:'fx_fireball_00',Холод:'fx_ice_shards01',Молния:'fx_lightning_bolt04',Истощение:'fx_smoke_warp02',Терратус:'fx_smoke_mist02',Иллюзия:'fx_smoke_warp01',Жизнь:'fx_flare01',Рвение:'fx_flare05',Эмоции:'fx_flare05',Сила:'fx_flare03',Камень:'fx_smoke_cloud01'};
 const color={Огонь:'#ff6c1d',Холод:'#82e4ff',Молния:'#71adff',Истощение:'#bd50ff',Терратус:'#50edce',Жизнь:'#78ee73',Рвение:'#ff4d66',Камень:'#bca37a'}[core]||'#e5cf95';
 const x=(point.x+.5)/grid.width*100,y=(point.y+.5)/grid.height*100,sx=(player.x+.5)/grid.width*100,sy=(player.y+.5)/grid.height*100;
 layer.style.setProperty('--vfx-color',color);
 const reduced=matchMedia('(prefers-reduced-motion: reduce)').matches;
 if(!reduced&&action.kind==='spell'&&core==='Молния'){
  const bounds=layer.getBoundingClientRect(),dx=(x-sx)*bounds.width/100,dy=(y-sy)*bounds.height/100;
  const beam=document.createElement('div');beam.className='combat-lightning';beam.style.left=`${sx}%`;beam.style.top=`${sy}%`;beam.style.width=`${Math.hypot(dx,dy)}px`;beam.style.transform=`translateY(-50%) rotate(${Math.atan2(dy,dx)}rad)`;layer.append(beam);
  beam.animate([{opacity:0},{opacity:1,offset:.18},{opacity:.25,offset:.38},{opacity:1,offset:.5},{opacity:0}],{duration:650}).finished.then(()=>beam.remove());
 }
 if(!reduced&&action.kind==='spell'&&action.targeting!=='self'&&action.targeting!=='aura'){
  const projectile=document.createElement('img');projectile.className='combat-projectile';projectile.src=`${gameCombatRoot}${textures[core]||'fx_flare03'}.png`;layer.append(projectile);
  projectile.animate([{left:`${sx}%`,top:`${sy}%`,opacity:0,transform:'translate(-50%,-50%) scale(.3)'},{left:`${sx}%`,top:`${sy}%`,opacity:1,offset:.12},{left:`${x}%`,top:`${y}%`,opacity:1,transform:'translate(-50%,-50%) scale(1)'}],{duration:550,easing:'ease-in'}).finished.then(()=>projectile.remove());
 }
 const impact=document.createElement('img');impact.className='combat-impact';impact.src=`${gameCombatRoot}${textures[core]||'fx_flare03'}.png`;impact.style.left=`${x}%`;impact.style.top=`${y}%`;layer.append(impact);
 impact.animate([{opacity:0,transform:'translate(-50%,-50%) scale(.3)'},{opacity:1,offset:.25},{opacity:0,transform:'translate(-50%,-50%) scale(1.8)'}],{duration:reduced?180:1200,delay:reduced?0:500}).finished.then(()=>impact.remove());
 if(!reduced&&action.kind==='spell'&&['area','cone','line','aura'].includes(action.targeting))for(const target of grid.tokens.filter(t=>t.team==='enemy'&&cells.some(c=>c.x===t.x&&c.y===t.y))){
  const burst=impact.cloneNode();burst.style.left=`${(target.x+.5)/grid.width*100}%`;burst.style.top=`${(target.y+.5)/grid.height*100}%`;layer.append(burst);burst.animate([{opacity:0,transform:'translate(-50%,-50%) scale(.2)'},{opacity:1,offset:.3},{opacity:0,transform:'translate(-50%,-50%) scale(1.2)'}],{duration:1000,delay:550}).finished.then(()=>burst.remove());
 }
 for(const point of cells){const cell=document.querySelector(`[data-cell="${point.x}:${point.y}"]`);cell?.animate([{background:color+'b0',boxShadow:`inset 0 0 24px ${color}`},{background:'transparent',boxShadow:'none'}],{duration:reduced?150:900,delay:reduced?0:500})}
}
document.addEventListener('click',e=>{
 if(tab!=='training'||!training?.active)return;
 if(combatBusy&&e.target.closest('.combat-game-screen')){e.stopImmediatePropagation();return}
 const cell=e.target.closest('[data-cell]');if(cell&&armedCombatAction){e.preventDefault();e.stopImmediatePropagation();const [x,y]=cell.dataset.cell.split(':').map(Number);confirmCombatAim({x,y});return}
 if(e.target.closest('[data-tab],[data-view],.training-reset,[data-training-set],[data-stance-name]'))clearCombatAim();
 const button=e.target.closest('[data-training-kind]');if(!button||button.disabled)return;
 if(['end_turn','wait','disengage'].includes(button.dataset.trainingKind))clearCombatAim();
 if(button.matches('[data-picker-action]')&&quickbarEditing)return;
 if(!['attack','ability','spell'].includes(button.dataset.trainingKind))return;
 const action=training.actions.find(x=>x.kind===button.dataset.trainingKind&&x.name===button.dataset.trainingName);if(action){e.preventDefault();e.stopImmediatePropagation();armCombatAction(action)}
},true);
document.addEventListener('pointerover',e=>{if(!armedCombatAction)return;const cell=e.target.closest('[data-cell]');if(cell){const [x,y]=cell.dataset.cell.split(':').map(Number);showCombatAim({x,y})}},true);
document.addEventListener('contextmenu',e=>{if(armedCombatAction&&e.target.closest('.combat-game-screen')){e.preventDefault();e.stopImmediatePropagation();clearCombatAim()}},true);
document.addEventListener('keydown',e=>{if(e.key==='Escape'&&armedCombatAction){e.preventDefault();clearCombatAim()}},true);
document.addEventListener('pointerover',e=>{const button=e.target.closest('[data-training-kind]');if(!button)return;const action=(training?.actions||[]).find(x=>x.kind===button.dataset.trainingKind&&x.name===button.dataset.trainingName),tip=document.querySelector('.combat-action-tooltip');if(!action||!tip)return;tip.hidden=false;tip.innerHTML=`<strong>${esc(action.name)}</strong><p>${esc(action.description||'')}</p><div>Дальность: ${action.range||0} м${action.area?` · область ${action.area} м`:''}</div><div>${action.remaining?`Перезарядка: ${action.remaining} раунд.`:'Выберите умение, затем цель на карте'}</div>`});
document.addEventListener('pointerout',e=>{const button=e.target.closest('[data-training-kind]');if(button&&!button.contains(e.relatedTarget)){const tip=document.querySelector('.combat-action-tooltip');if(tip)tip.hidden=true}});
