/* One accessible glossary on every screen, including dialog top layers. */
const GameHelp=(()=>{
 const entries=new Map(),key=v=>String(v||'').toLocaleLowerCase('ru-RU').replace(/ё/g,'е').replace(/[^a-zа-я0-9]+/g,' ').trim();
 const escape=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
 const plain=v=>String(v||'').replace(/\[url=glossary:[^\]]+]([\s\S]*?)\[\/url]/gi,'$1').replace(/\[\/?[^\]]+]/g,'').trim();
 const aliases={'Урон':'Типы урона','Рубящий':'Типы урона','Дробящий':'Типы урона','Колющий':'Типы урона','Огненный':'Типы урона','Ледяной':'Типы урона','Электрический':'Типы урона','Разъедающий':'Типы урона','Магический':'Типы урона','Крит. шанс':'Критическое попадание','Критический шанс':'Критическое попадание','Выносливость':'Защита Выносливостью','Воля':'Защита Волей','Перезарядка':'Перезарядка способности','Ранг навыка':'Ранг навыка','Прерывание':'Упреждение','Быстрый доступ':'Расходуемые предметы','Аксессуары':'Аксессуар','Восстановление оружия':'Восстановление','Управление силой':'Управление силами','Поглощение':'Броня','Поглощение брони':'Броня','Дротики':'Метательное оружие','Обычное':'Качество','Хорошее':'Качество','Превосходное':'Качество','Выдающееся':'Качество','Безупречное':'Качество'};
 const fallbacks={
  'Восстановление':'Дополнительное восстановление от надетой брони и оружия, влияющее на итоговую перезарядку способностей и талантов. Дробные значения сохраняются. Не отнимает действие и не блокирует обычную атаку.',
  'Дистанция':'Дальность применения в метрах. На поле 1 клетка = 1 метр; дробная дальность округляется вверх. Если указана минимальная дистанция, ближе неё атаковать нельзя.',
  'Дальность':'Дальность применения в метрах. На поле 1 клетка = 1 метр. Для применения нужны допустимая цель и свободная линия видимости.',
  'Радиус':'Расстояние от центра области до её границы. В область попадают допустимые видимые цели.',
  'Цена':'100 медных колец = 1 бронзовое; 100 бронзовых = 1 железное.',
  'Передвижение':'Оставшееся перемещение в текущем ходу. Преграды перекрывают путь; выход из зоны контроля противника может вызвать ответную атаку.',
  'Инициатива':'Порядок ходов определяется броском d20 с бонусом Быстроты. После последнего участника начинается новый раунд.',
  'Голова':'Слот головного убора. Характеристики надетого предмета применяются к персонажу; он не занимает место в сумке.',
  'Торс':'Слот доспеха или одежды. Броня защищает от соответствующих типов урона; экипировка может увеличивать восстановление.',
  'Руки':'Слот перчаток. Их бонусы действуют только при экипировке.',
  'Ноги':'Слот обуви. Её бонусы действуют только при экипировке.',
  'П. рука':'Правая рука активного комплекта. Двуручное оружие занимает обе руки; второе оружие или щит одновременно надеть нельзя.',
  'Л. рука':'Левая рука активного комплекта: одноручное оружие или щит. Недоступна, пока в правой руке двуручное оружие.',
  'Сравнить':'Сопоставить этот предмет с надетым предметом того же слота или оружием активного комплекта. Предметы при сравнении не меняются.',
  'Улучшить':'Повысить качество на одну ступень по игровому рецепту. Материалы и кольца расходуются; улучшение мгновенное, надетый предмет остаётся в своём слоте.',
  'Приготовить':'Изготовить указанное количество расходников за материалы и кольца. Для закрытого рецепта сначала нужно изучить соответствующий свиток.',
  'Купить':'Купить указанное количество за кольца. Учитываются уровень доступа, остаток товара и свободное место в сумке.',
  'Продать':'Продать указанный предмет по цене выкупа лавки. Надетую вещь сначала нужно снять.',
  'Уничтожить':'Безвозвратно удалить выбранное количество предметов. Кольца за уничтожение не выдаются.',
  'Применить':'Применить расходник. На себя — без траты основного действия; на соседнего союзника — с тратой действия.',
  'Снять':'Переместить надетый предмет в сумку. Его бонусы перестают действовать; в сумке нужно свободное место.',
  'Разное':'Материалы, ценности, задания и другие предметы без действия применения.',
  'Материалы':'Используются в рецептах кузни и расходников. Требуемое количество указано рядом с результатом изготовления.'
 };
 let pattern=null,popup=null,active=null,timer=null,observer=null;
 function find(term){return entries.get(key(term))||entries.get(key(aliases[term]||''))||Object.entries(aliases).map(([a,b])=>key(a)===key(term)?entries.get(key(b)):null).find(Boolean)||null}
 function help(term){const entry=find(term);return entry?{title:entry.title,text:plain(entry.body)}:fallbacks[term]?{title:term,text:fallbacks[term]}:null}
 function span(term,label){return `<span class="game-term" tabindex="0" data-game-help="${escape(term)}">${escape(label)}</span>`}
 function markPlain(text){
  if(!pattern)return escape(text).replace(/\n/g,'<br>');
  let result='',last=0,match;pattern.lastIndex=0;
  while((match=pattern.exec(text))){const start=match.index+match[1].length;result+=escape(text.slice(last,start));result+=span(match[2],match[2]);last=start+match[2].length;pattern.lastIndex=last}
  return (result+escape(text.slice(last))).replace(/\n/g,'<br>');
 }
 function markup(value){
  const text=String(value||''),links=/\[url=glossary:([^\]]+)]([\s\S]*?)\[\/url]/gi;let result='',last=0,match;
  while((match=links.exec(text))){result+=markPlain(plain(text.slice(last,match.index)));result+=span(match[1],plain(match[2]));last=links.lastIndex}
  return result+markPlain(plain(text.slice(last)));
 }
 function loadEntries(rows){
  entries.clear();const terms=new Set(Object.keys(fallbacks));
  const mechanical=rows.filter(e=>[0,1,2,3,8].includes(Number(e.category)));
  // Canonical titles take precedence over aliases from another article.
  for(const row of mechanical)for(const canonical of [row.title,row.key,row.asset])if(canonical)entries.set(key(canonical),row);
  for(const row of mechanical)for(const alias of [row.title,...(row.aliases||[])]){const k=key(alias);if(k&&!entries.has(k))entries.set(k,row);if(/[а-яё]/i.test(alias)&&alias.length>=4)terms.add(alias)}
  for(const [a,b] of Object.entries(aliases))if(entries.has(key(b)))terms.add(a);
  pattern=new RegExp(`(^|[^А-Яа-яЁёA-Za-z0-9])(${[...terms].sort((a,b)=>b.length-a.length).map(s=>s.replace(/[.*+?^${}()|[\]\\]/g,'\\$&').replace(/[её]/gi,'[её]')).join('|')})(?=$|[^А-Яа-яЁёA-Za-z0-9])`,'giu');
 }
 function position(){
  if(!active?.isConnected){hide();return}
  // Child icons/text share their control's safe rectangle: a large help card
  // must not cover the button that the pointer is about to select.
  const anchor=active.closest('button,input,select,summary,[role="button"]')||active;
  const rect=anchor.getBoundingClientRect(),screen=document.documentElement.clientWidth,width=Math.min(400,screen-24);
  popup.style.width=width+'px';popup.style.maxHeight=Math.max(80,innerHeight-24)+'px';popup.style.pointerEvents='';
  let left=Math.max(12,Math.min(rect.left,screen-width-12)),height=popup.offsetHeight,top;
  if(rect.bottom+9+height<=innerHeight-12)top=rect.bottom+9;
  else if(rect.top-height-9>=12)top=rect.top-height-9;
  else if(rect.left-width-9>=12){left=rect.left-width-9;top=rect.top}
  else if(rect.right+9+width<=screen-12){left=rect.right+9;top=rect.top}
  else{
   const above=Math.max(0,rect.top-21),below=Math.max(0,innerHeight-rect.bottom-21),available=Math.max(above,below);
   popup.style.maxHeight=Math.max(48,available)+'px';height=popup.offsetHeight;
   top=below>=above?rect.bottom+9:rect.top-height-9;
   if(available<48)popup.style.pointerEvents='none';
  }
  popup.style.left=left+'px';popup.style.top=Math.max(12,Math.min(top,innerHeight-height-12))+'px';
 }
 function show(target,title,text){
  clearTimeout(timer);active?.removeAttribute('aria-describedby');active=target;
  if(!popup){popup=document.createElement('div');popup.id='game-help-popover';popup.className='game-help-popover';popup.setAttribute('role','tooltip');popup.setAttribute('popover','manual');document.body.append(popup)}
  popup.innerHTML=`<b>${escape(title)}</b><div>${markup(text)}</div>`;popup.hidden=false;
  if(popup.showPopover){if(!popup.matches(':popover-open'))popup.showPopover()}else{const dialog=target.closest('dialog[open]');if(popup.parentElement!==(dialog||document.body))(dialog||document.body).append(popup)}
  position();target.setAttribute('aria-describedby',popup.id);
 }
 function hide(){clearTimeout(timer);if(popup){if(popup.matches(':popover-open'))popup.hidePopover?.();popup.hidden=true}active?.removeAttribute('aria-describedby');active=null}
 function later(){clearTimeout(timer);timer=setTimeout(()=>{if(!active?.contains(document.activeElement)&&!popup?.contains(document.activeElement))hide()},200)}
 function targetHelp(target){
  const d=target.dataset;
  if(d.gameHelpText){const source=help(d.gameHelp);return {title:d.gameHelp||d.contextTitle||'Пояснение',text:source&&key(d.gameHelpText)===key(d.gameHelp)?source.text:d.gameHelpText}}
  if(d.helpText)return {title:d.helpTitle,text:d.helpText};
  if(d.contextText)return {title:d.contextTitle,text:d.contextText};
  if(d.uiTip)return {title:d.uiTip.split('\n')[0],text:d.uiTip};
  const term=d.gameHelp||d.encyclopediaTip||d.glossary||d.encyclopediaTerm;
  return help(term);
 }
 const selector='[data-game-help],[data-help-text],[data-context-text],[data-encyclopedia-tip],[data-glossary],[data-encyclopedia-term],[data-training-kind],[data-ui-tip]';
 function onShow(event){if(event.target.closest('#game-help-popover')){clearTimeout(timer);event.stopImmediatePropagation();return}const target=event.target.closest(selector),info=target&&targetHelp(target);if(info){show(target,info.title,info.text);event.stopImmediatePropagation()}}
 function annotate(root){
  if(!root?.querySelectorAll||root.closest?.('#game-help-popover,.encyclopedia-popover,.glossary-tooltip,.game-icon-tooltip'))return;
  // Existing control help becomes a real popup instead of a browser title.
  for(const control of root.querySelectorAll('[title]'))if(!control.closest('[data-training-kind],#game-help-popover')&&!control.matches(selector)){const text=control.getAttribute('title');if(text){control.dataset.gameHelp=control.getAttribute('aria-label')||text.split('\n')[0];control.dataset.gameHelpText=text;control.removeAttribute('title')}}
  for(const control of root.querySelectorAll('button,summary,label,output'))if(!control.matches(selector)&&!control.closest('[data-training-kind]')){const label=control.getAttribute('aria-label')||control.textContent.trim();if(help(label)){control.dataset.gameHelp=label;if(control.tagName==='LABEL')control.tabIndex=0}}
  const walker=document.createTreeWalker(root,NodeFilter.SHOW_TEXT),nodes=[];
  while(walker.nextNode()){const n=walker.currentNode,p=n.parentElement;if(!p||p.closest('script,style,textarea,input,select,option,h1,h2,.item-name,.catalog-card,.craft-choice,.combat-cell,.battle-map-cell,.game-help-popover,.encyclopedia-popover,.glossary-tooltip,.game-icon-tooltip,'+selector))continue;if(n.nodeValue.trim())nodes.push(n)}
  for(const node of nodes){const html=markPlain(node.nodeValue);if(!html.includes('data-game-help='))continue;const template=document.createElement('template');template.innerHTML=html;node.replaceWith(template.content)}
  for(const term of root.querySelectorAll('[data-game-help]'))if(!targetHelp(term)){const parent=term.parentElement;term.replaceWith(document.createTextNode(term.textContent));if(parent?.classList.contains('game-item-type'))parent.classList.add('no-help')}
 }
 function start(){
  document.addEventListener('pointerover',onShow,true);document.addEventListener('focusin',onShow,true);
  document.addEventListener('pointerout',e=>{const target=e.target.closest(selector);if(target&&!target.contains(e.relatedTarget)&&!popup?.contains(e.relatedTarget))later();if(e.target.closest('#game-help-popover')&&!popup.contains(e.relatedTarget)&&!e.relatedTarget?.closest?.(selector))later()},true);
  document.addEventListener('focusout',e=>{if(e.target.closest(selector)&&!popup?.contains(e.relatedTarget))later()},true);
  document.addEventListener('click',e=>{const target=e.target.closest(selector);if(target){const info=targetHelp(target);if(info){show(target,info.title,info.text);return}}if(!e.target.closest('#game-help-popover'))hide()},true);
  document.addEventListener('keydown',e=>{if(e.key==='Escape'&&active){e.preventDefault();e.stopImmediatePropagation();hide()}},true);
  document.addEventListener('scroll',e=>{if(popup?.contains(e.target))return;if(active?.contains(document.activeElement))position();else hide()},true);
  document.addEventListener('close',hide,true);window.addEventListener('resize',hide);
  const pending=new Set();let scheduled=false;
  observer=new MutationObserver(records=>{for(const r of records)for(const n of r.addedNodes)if(n.nodeType===1&&!n.closest('#game-help-popover')&&!n.matches('.game-term'))pending.add(n);if(pending.size&&!scheduled){scheduled=true;requestAnimationFrame(()=>{scheduled=false;const roots=[...pending];pending.clear();roots.forEach(annotate)})}});
  observer.observe(document.body,{childList:true,subtree:true});
  fetch('data/encyclopedia.json?v=20261012-3').then(r=>{if(!r.ok)throw Error('glossary');return r.json()}).then(d=>{loadEntries(d.entries);annotate(document.body)}).catch(()=>{loadEntries([]);annotate(document.body)});
 }
 if(typeof document!=='undefined')document.addEventListener('DOMContentLoaded',start,{once:true});
 return {help,markup,loadEntries,show,hide,annotate,owns(target){return active===target},hideCombat(){if(active?.closest('.combat-game-screen,.combat-action-picker'))hide()}};
})();
