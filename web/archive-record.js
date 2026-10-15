/* Public dossiers have independent data and no owner mutation controls. */
let archiveRecord = null, archiveRecordTab = 'overview', archiveRecordCategory = 'all', archiveRecordSet = 1, archiveRecordLoad = 0;

async function openArchiveRecord(id) {
 const load = ++archiveRecordLoad, dialog = $('#record');
 archiveRecord = null;
 $('#record-body').innerHTML = '<p role="status">Открываем личное дело…</p>';
 if (!dialog.open) dialog.showModal();
 try {
  const dossier = normalize(await request('/api/archive/' + encodeURIComponent(id)));
  if (load !== archiveRecordLoad || !dialog.open) return;
  archiveRecord = dossier;
  archiveRecordTab = 'overview'; archiveRecordCategory = 'all';
  archiveRecordSet = Number(dossier.derived.activeWeaponSet || 1);
  renderArchiveRecord();
 } catch (error) {
  if (load === archiveRecordLoad && dialog.open) $('#record-body').innerHTML = `<p role="alert">${esc(error.message)}</p>`;
 }
}

function renderArchiveRecord() {
 if (!archiveRecord) return;
 const c = archiveRecord.character;
 $('#record-body').innerHTML = `<header class="record-head">${c.portrait_url ? `<img src="${esc(c.portrait_url)}" alt="">` : ''}<div><small>ЛИЧНОЕ ДЕЛО · УРОВЕНЬ ${esc(c.level)}</small><h1>${esc(c.name)}</h1><p>${esc(c.background)}</p><span>${esc(c.health)}/${esc(archiveRecord.derived.healthMax ?? c.health_max)} здоровья</span></div></header><nav class="record-tabs" aria-label="Разделы личного дела">${[['overview','Характеристики'],['inventory','Инвентарь'],['talents','Деревья талантов']].map(([key,label]) => `<button data-record-tab="${key}" aria-pressed="${archiveRecordTab === key}">${label}</button>`).join('')}</nav><div id="record-panel"></div>`;
 renderArchiveRecordPanel();
}

function renderArchiveRecordPanel() {
 const d = archiveRecord, c = d.character, panel = $('#record-panel');
 if (archiveRecordTab === 'inventory') panel.innerHTML = archiveRecordInventory(d);
 else if (archiveRecordTab === 'talents') panel.innerHTML = archiveRecordTalents(d);
 else panel.innerHTML = `<div class="grid">${statsBox(c,d,false)}${skillsBox(c,false,d)}</div>${checkSkillsBox(c,d)}`;
}

function archiveRecordItem(item) {
 return `<button class="record-item" data-record-item="${Number(item.inventory_id)}">${itemVisual(item)}<span><b>${esc(item.name)}</b><small>${esc(item.category)} · ${esc(item.quality)}${Number(item.quantity) > 1 ? ` · ×${Number(item.quantity)}` : ''}</small>${item.equipped_slot ? `<small>${esc(item.equipped_slot)}</small>` : ''}</span></button>`;
}

function archiveRecordInventory(d) {
 const c = d.character, bySlot = Object.fromEntries(d.inventory.filter(i => i.equipped_slot).map(i => [i.equipped_slot,i]));
 const roman = ['I','II','III','IV'][archiveRecordSet - 1] || 'I';
 const weapon = bySlot[`Оружие ${roman} — правая рука`];
 if (Number(weapon?.hands) >= 2) bySlot[`Оружие ${roman} — левая рука`] = weapon;
 // Only the inspect action is carried over from the player's paperdoll.
 const slot = (key,label,position) => equipmentSlot(key,label,position,bySlot).replaceAll('data-item-details=', 'data-record-item=');
 const slots = [['Голова','Голова','head'],['Торс','Торс','torso'],['Аксессуар 1','Аксессуар','accessory-one'],['Руки','Руки','hands'],['Ноги','Ноги','feet'],['Аксессуар 2','Аксессуар','accessory-two'],[`Оружие ${roman} — правая рука`,'П. рука','weapon-main'],[`Оружие ${roman} — левая рука`,'Л. рука','weapon-off']].map(args => slot(...args)).join('');
 const quick = Array.from({length:d.equipmentLimits.quickSlots}, (_,n) => slot(`Быстрый предмет ${n+1}`,String(n+1),`quick q${n+1}`)).join('');
 const bag = d.inventory.filter(i => !i.equipped_slot), filtered = bag.filter(i => inventoryCategoryMatches(i,archiveRecordCategory));
 const equipped = d.inventory.filter(i => i.equipped_slot);
 return `<div class="record-inventory"><section class="paperdoll"><div class="paperdoll-frame">${c.portrait_url ? `<img class="paperdoll-character" src="${esc(c.portrait_url)}" alt="${esc(c.name)}">` : `<div class="paperdoll-silhouette">${esc(c.name?.[0] || '?')}</div>`}${slots}<div class="quick-title">Быстрый доступ</div><div class="quick-slots">${quick}</div></div><h3>Комплекты оружия</h3><div class="weapon-sets">${Array.from({length:d.equipmentLimits.weaponSets},(_,n) => `<button class="weapon-set ${archiveRecordSet === n+1 ? 'active' : ''}" data-record-set="${n+1}" aria-pressed="${archiveRecordSet === n+1}"><b>${['I','II','III','IV'][n]}</b></button>`).join('')}</div></section><section class="record-bag"><header><h2>Инвентарь</h2><span>Занято ${esc(d.capacity.used)} из ${esc(d.capacity.capacity)}</span></header><nav class="inventory-filters" aria-label="Категории чужого инвентаря">${inventoryGroups.map(([key,label,icon]) => `<button data-record-category="${key}" aria-pressed="${archiveRecordCategory === key}" class="${archiveRecordCategory === key ? 'active' : ''}"><img src="assets/inventory-icons/filter-${icon}.png" alt="">${label}</button>`).join('')}</nav><div class="record-bag-items">${filtered.map(archiveRecordItem).join('') || '<p>В этой категории нет предметов.</p>'}</div><details class="record-equipped"><summary>Вся экипировка (${equipped.length})</summary>${equipped.map(archiveRecordItem).join('') || '<p>Ничего не надето.</p>'}</details></section></div>`;
}

function archiveRecordTalentLibrary(d) {
 const rows = [...d.talentLibrary];
 for (const talent of d.learnedTalents || []) {
  const index = rows.findIndex(t => t.name === talent.name || t.legacyName === talent.name || (talent.legacyName && t.name === talent.legacyName));
  if (index < 0) rows.push(talent);
 }
 for (const talent of d.character.talents || []) {
  if (!rows.some(t => t.name === talent.name || t.legacyName === talent.name)) rows.push(talent);
 }
 return rows;
}

function archiveRecordOwns(d,talent) {
 return (d.character.talents || []).some(t => t.name === talent.name || t.name === talent.legacyName || (talent.legacyName && t.legacyName === talent.legacyName)) || (Number(talent.automatic_level) > 0 && Number(d.character.level) >= Number(talent.automatic_level));
}

function archiveRecordTalents(d) {
 const trees = new Map();
 for (const t of archiveRecordTalentLibrary(d)) {
  const name = t.tree || t.tree_name || 'Другие способности';
  if (!trees.has(name)) trees.set(name,[]);
  trees.get(name).push(t);
 }
 if (!trees.size) return '<section class="box"><p>Деревья талантов пока недоступны.</p></section>';
 return `<p class="record-tree-legend"><span>● Изучен</span><span>○ Не изучен</span></p><div class="record-trees">${[...trees].map(([name,rows]) => {
  const owned = rows.filter(t => archiveRecordOwns(d,t)).length;
  const tiers = [...new Set(rows.map(t => Number(t.tier || 0)))].sort((a,b) => a-b);
  return `<details class="record-tree" open><summary><span>${esc(name)}</span><b>${owned}/${rows.length}</b></summary>${tiers.map(tier => `<div class="record-tier"><small>СТУПЕНЬ ${tier}</small><div>${rows.filter(t => Number(t.tier || 0) === tier).map(t => `<button class="record-talent ${archiveRecordOwns(d,t) ? 'owned' : ''}" data-record-talent="${esc(t.name)}" aria-label="${esc(t.name)} · ${archiveRecordOwns(d,t) ? 'Изучен' : 'Не изучен'}">${talentIcon(t)}<span>${esc(t.name)}<small>${archiveRecordOwns(d,t) ? 'Изучен' : 'Не изучен'}</small></span></button>`).join('')}</div></div>`).join('')}</details>`;
 }).join('')}</div>`;
}

function openArchiveRecordDetail(kind,key) {
 if (!archiveRecord) return;
 const body = $('#record-detail-body');
 if (kind === 'item') {
  const item = archiveRecord.inventory.find(i => Number(i.inventory_id) === Number(key));
  if (!item) return;
  body.innerHTML = gameItemDetails(item);
 } else {
  const t = archiveRecordTalentLibrary(archiveRecord).find(t => t.name === key);
  if (!t) return;
  body.innerHTML = `<div class="talent-dialog-head">${talentIcon(t,'large')}<div><small>${esc(t.tree || t.tree_name || '')}</small><h2>${esc(t.name)}</h2></div></div><p class="talent-dialog-requirement">${archiveRecordOwns(archiveRecord,t) ? 'Изучен' : 'Не изучен'}</p>${t.description ? `<p>${esc(t.description)}</p>` : ''}${talentMechanics(t)}`;
 }
 $('#record-detail').showModal();
}

$('#record-detail .close').onclick = () => $('#record-detail').close();
$('#record').addEventListener('close', () => { ++archiveRecordLoad; archiveRecord = null; });
$('#record').addEventListener('click', event => {
 if (!archiveRecord) return;
 const button = event.target.closest('button');
 if (!button) return;
 if (button.dataset.recordTab) {
  archiveRecordTab = button.dataset.recordTab;
  $('#record').querySelectorAll('[data-record-tab]').forEach(b => b.setAttribute('aria-pressed', b === button));
  renderArchiveRecordPanel();
 } else if (button.dataset.recordCategory) {
  archiveRecordCategory = button.dataset.recordCategory; renderArchiveRecordPanel();
 } else if (button.dataset.recordSet) {
  archiveRecordSet = Number(button.dataset.recordSet); renderArchiveRecordPanel();
 } else if (button.dataset.recordItem) openArchiveRecordDetail('item',button.dataset.recordItem);
 else if (button.dataset.recordTalent) openArchiveRecordDetail('talent',button.dataset.recordTalent);
});
