/* One persistent location indicator across the independent workshop modules. */
const adminNavTargets='[data-open-battles],[data-open-npcs],[data-open-catalog],[data-campaign]';
function adminMarkNavigation(name){
 document.querySelectorAll(adminNavTargets).forEach(button=>{
  const key=button.hasAttribute('data-open-battles')?'battles':button.hasAttribute('data-open-npcs')?'npcs':button.hasAttribute('data-open-catalog')?'catalog':button.dataset.campaign;
  if(key===name)button.setAttribute('aria-current','page');else button.removeAttribute('aria-current');
 });
}
document.addEventListener('DOMContentLoaded',()=>{
 const top=document.querySelector('.admin-top>div');top?.setAttribute('aria-label','Разделы мастерской');
 document.querySelectorAll(adminNavTargets).forEach(button=>button.title=({battles:'Подготовка сцены и ходы НПС',npcs:'Создание НПС и назначение способностей',catalog:'Полный каталог предметов',maps:'Карты и преграды',shop:'Ассортимент и цены',characters:'Изменение персонажей игроков'})[button.hasAttribute('data-open-battles')?'battles':button.hasAttribute('data-open-npcs')?'npcs':button.hasAttribute('data-open-catalog')?'catalog':button.dataset.campaign]);
 const editor=document.querySelector('#editor');if(!editor)return;
 new MutationObserver(()=>{
  const view=editor.querySelector('.master-battle-editor,.battle-editor-index')?'battles':editor.querySelector('.npc-workspace')?'npcs':editor.querySelector('.map-settings,.campaign-map-list')?'maps':editor.querySelector('#master-shop-stock')?'shop':editor.querySelector('#master-catalog-filters')?'catalog':editor.querySelector('.editor-head')?'characters':'';
  adminMarkNavigation(view);
 }).observe(editor,{childList:true,subtree:false});
});
