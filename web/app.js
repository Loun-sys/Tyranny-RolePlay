"use strict";

const $ = (selector) => document.querySelector(selector);
const screens = ["История", "Основа", "Доп.", "Имя", "Характеристики", "Навыки", "Итог"];
const weaponSkills = ["Волшебный посох", "Луки", "Безоружный бой", "Двуручное оружие", "Одноручное оружие", "Парное оружие"];
const supportSkills = ["Знания", "Уклонение", "Хитроумие", "Атлетика", "Парирование"];
const glossary = {
  "Удерживание": { aliases: ["Удерживание", "Удерживания", "Удерживаемые"], text: "Удерживаемые цели не могут свободно перемещаться без риска получить удар при выходе из ближнего боя. Удерживание создаётся противником, способным контролировать область рядом с собой." },
  "Одноручное оружие": { aliases: ["Одноручное оружие", "одноручного оружия", "одноручным оружием"], text: "Определяет эффективность одноручного оружия: мечей, топоров, кинжалов и булав. Чем больше уровень навыка, тем выше точность атак и шанс нанесения критических попаданий." },
  "Парирование": { aliases: ["Парирование", "Парированием", "Парирования"], text: "Парирование используется для защиты от атак и заклинаний ближнего боя. Чем выше уровень навыка, тем меньше урона наносят вражеские атаки и тем выше вероятность их промаха." },
  "Атлетика": { aliases: ["Атлетика", "Атлетики", "Атлетикой"], text: "Определяет способность персонажа к перемещению по пересечённой местности, а также к выполнению сложных движений в бою. Кроме того, в разговорах Атлетика используется для запугивания или угроз физической расправой над собеседником." },
  "Уклонение": { aliases: ["Уклонение", "Уклонением", "Уклонения"], text: "Уклонение используется для защиты от атак из луков, дротиками и заклинаний дальнего боя. Чем выше уровень навыка, тем меньше урона наносят вражеские атаки и тем выше вероятность их промаха." },
  "Парное оружие": { aliases: ["Парное оружие", "парного оружия", "парным оружием"], text: "Определяет эффективность парного оружия. Чем больше уровень навыка, тем выше точность атак и шанс нанесения критических попаданий." },
  "Хитроумие": { aliases: ["Хитроумие", "Хитроумия", "Хитроумием"], text: "Хитроумие определяет способность персонажа к скрытному перемещению, обнаружению ловушек и скрытых устройств и взаимодействию с ними, а также способность вскрывать запертые сундуки и двери. В разговорах Хитроумие используется для обмана или одурачивания собеседника." },
  "Луки": { aliases: ["Луки", "луков", "луками"], text: "Определяет эффективность применения луков. Чем больше уровень навыка, тем выше точность атак и шанс нанесения критических попаданий." },
  "Безоружный бой": { aliases: ["Безоружный бой", "безоружного боя", "безоружных атак"], text: "Определяет эффективность безоружных атак. Чем больше уровень навыка, тем выше точность атак и шанс нанесения критических попаданий." },
  "Управление молниями": { aliases: ["Управление молниями"], text: "Определяет способность персонажа к применению заклинаний, использующих Сигил Молнии. Чем больше уровень навыка, тем выше шанс попаданий и критических попаданий." },
  "Волшебный посох": { aliases: ["Волшебный посох", "Волшебные посохи", "магических посохов", "волшебными посохами"], text: "Определяет эффективность применения магических посохов. Чем больше уровень навыка, тем выше точность атак и шанс нанесения критических попаданий. Точность магических атак определяется как уровнем навыка, так и свойствами оружия." },
  "Знания": { aliases: ["Знания", "Знаний", "Знаниями"], text: "Знания определяют способность персонажа к расшифровке тайных сведений и восстановлению общей картины по найденным клочкам информации. Этот навык критически важен для магов, которые хотят изучать новые руны для усиления заклинаний. В разговорах Знания используются для определения того, что вы знаете об истории мира, а также чтобы впечатлить собеседников уровнем вашего интеллекта." },
  "Управление холодом": { aliases: ["Управление холодом"], text: "Определяет способность персонажа к применению заклинаний, использующих Сигил Льда. Чем больше уровень навыка, тем выше шанс попаданий и критических попаданий." },
  "Управление рвением": { aliases: ["Управление рвением"], text: "Определяет способность персонажа к применению заклинаний, использующих Сигил Рвения. Чем больше уровень навыка, тем выше шанс попаданий и критических попаданий." },
  "Управление истощением": { aliases: ["Управление истощением"], text: "Определяет способность персонажа к применению заклинаний, использующих Сигил Истощения. Чем больше уровень навыка, тем выше шанс попаданий и критических попаданий, которые, в свою очередь, продлевают действие штрафов Истощения для противников." },
  "Сила": { aliases: ["Сила", "Силы", "Силой", "Силу", "Силе"], text: "Сила определяет физическую мощь персонажа. Чем выше Сила, тем больше урона наносят атаки и тем мощнее действие способностей. Кроме того, она повышает защиту Выносливостью." },
  "Защита Выносливостью": { aliases: ["Защита Выносливостью", "защите Выносливостью", "Выносливость", "Выносливостью"], text: "Выносливость противостоит атакам, цель которых — внутренние органы персонажа: яду, болезни, оглушению и подобным воздействиям. Прежде всего она определяется Стойкостью и Силой персонажа, но также на неё могут повлиять снаряжённые предметы, таланты и эффекты зелий и заклинаний." },
  "Искусность": { aliases: ["Искусность", "Искусности", "Искусностью"], text: "Искусность определяет точность физических и ментальных способностей персонажа и используется для проверки точности атак и заклинаний. Кроме того, Искусность увеличивает шанс того, что доспех снизит результативность удара: критическое попадание станет попаданием, попадание — задеванием, а задевание — промахом." },
  "Точность": { aliases: ["Точность", "точности", "точностью"], text: "Во время атаки точность нападающего сравнивается с одной из пяти защит цели: Парированием в ближнем бою, Уклонением при дальней атаке, Выносливостью при оглушении и ошеломлении, Волей при ментальной атаке и Магией при атаке заклинанием.\n\nВ первую очередь точность определяется навыком нападающего в этом виде атаки. На неё могут влиять Искусность, таланты и активные эффекты заклинаний или предметов.\n\nЕсли точность выше защиты, результат чаще становится попаданием или критическим попаданием, а не задеванием или промахом." },
  "Отражение": { aliases: ["Отражение", "Отражения", "отражением"], text: "После определения результата атаки происходит проверка отражения. Оно может снизить результат на один ранг: критическое попадание станет попаданием, попадание — задеванием, задевание — промахом.\n\nОтражение зависит от одежды, брони, талантов и способностей. Искусность увеличивает общий показатель отражения, даваемого бронёй." },
  "Быстрота": { aliases: ["Быстрота", "Быстроты", "Быстротой"], text: "Быстрота сокращает перезарядку способностей и определяет скорость действий персонажа в бою." },
  "Живучесть": { aliases: ["Живучесть", "Живучести", "Живучестью"], text: "Живучесть определяет физическое здоровье персонажа и силу его духа. Кроме того, она увеличивает защиту Волей." },
  "Защита Волей": { aliases: ["Защита Волей", "защите Воли", "защиту Волей", "Воля", "Волей", "Воли"], text: "Защита Волей оберегает от атак на разум, например от дезориентации. Она определяется Стойкостью и Смекалкой персонажа, но также на неё могут повлиять снаряжённые предметы, таланты и эффекты зелий и заклинаний." },
  "Смекалка": { aliases: ["Смекалка", "Смекалки", "Смекалкой"], text: "Смекалка определяет способность персонажа наблюдать за окружающим миром и обнаруживать следы и улики. Кроме того, Смекалка увеличивает силу заклинаний и защиту Магией." },
  "Защита Магией": { aliases: ["Защита Магией", "защите Магии", "защиту Магией", "Магическая защита", "Магической защите"], text: "Защита Магией даёт сопротивление заклинаниям и атакам, наносящим магический урон. Она определяется Стойкостью и Живучестью персонажа, но также на неё могут повлиять снаряжённые предметы, таланты и эффекты зелий и заклинаний." },
  "Стойкость": { aliases: ["Стойкость", "Стойкости", "Стойкостью"], text: "Стойкость определяет способность персонажа переносить тяготы и невзгоды физического и ментального характера. Это основная характеристика для определения защиты Выносливостью, Волей и Магией. Кроме того, она повышает длительность воздействий, которые накладывает персонаж." },
};

const skillDescriptions = Object.fromEntries(Object.entries(glossary).map(([name, details]) => [name, details.text]));

const state = {
  config: null, screen: 0, furthest: 0, background: "", specs: ["", ""], abilities: ["", ""],
  name: "", portrait: "", attributes: {}, skills: {}, focusedAttribute: "Сила", focusedSkill: "Одноручное оружие",
};

const params = new URLSearchParams(location.search);
const token = params.get("token") || "";
const apiBase = (params.get("api") || "https://tyranny-roleplay-production.up.railway.app").replace(/\/$/, "");

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, (character) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  })[character]);
}

const glossaryAliases = Object.entries(glossary).flatMap(([name, details]) => details.aliases.map((alias) => ({ alias, name })))
  .sort((left, right) => right.alias.length - left.alias.length);
const glossaryLookup = new Map(glossaryAliases.map(({ alias, name }) => [alias.toLocaleLowerCase("ru-RU"), name]));
const glossaryPattern = glossaryAliases.map(({ alias }) => alias.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")).join("|");

function annotateGlossary(root = $("#form")) {
  if (!root || !glossaryPattern) return;
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
  const nodes = [];
  while (walker.nextNode()) {
    const parent = walker.currentNode.parentElement;
    if (!parent || parent.closest(".glossary-term,.glossary-tooltip,script,style,textarea,input,option")) continue;
    if (walker.currentNode.nodeValue.trim()) nodes.push(walker.currentNode);
  }
  const letters = "А-Яа-яЁёA-Za-z0-9";
  const matcher = new RegExp(`(^|[^${letters}])(${glossaryPattern})(?=$|[^${letters}])`, "giu");
  nodes.forEach((node) => {
    const text = node.nodeValue; let match; let last = 0; let changed = false;
    matcher.lastIndex = 0; const fragment = document.createDocumentFragment();
    while ((match = matcher.exec(text))) {
      const start = match.index + match[1].length; const found = match[2];
      fragment.append(text.slice(last, start));
      const term = document.createElement("span");
      term.className = "glossary-term"; term.tabIndex = 0; term.textContent = found;
      term.dataset.glossary = glossaryLookup.get(found.toLocaleLowerCase("ru-RU"));
      fragment.append(term); last = start + found.length; matcher.lastIndex = last; changed = true;
    }
    if (changed) { fragment.append(text.slice(last)); node.replaceWith(fragment); }
  });
}

function showGlossary(term) {
  const entry = glossary[term.dataset.glossary]; if (!entry) return;
  const tooltip = $("#glossary-tooltip"); tooltip.querySelector("b").textContent = term.dataset.glossary;
  tooltip.querySelector("p").textContent = entry.text; tooltip.hidden = false;
  const rect = term.getBoundingClientRect(); const width = Math.min(420, innerWidth - 24);
  tooltip.style.width = `${width}px`; tooltip.style.left = `${Math.max(12, Math.min(innerWidth - width - 12, rect.left))}px`;
  const height = tooltip.offsetHeight; const below = rect.bottom + 10;
  tooltip.style.top = `${below + height <= innerHeight - 10 ? below : Math.max(10, rect.top - height - 10)}px`;
}

function hideGlossary() { $("#glossary-tooltip").hidden = true; }

function bonusesHtml(bonuses = {}) {
  const entries = Object.entries(bonuses);
  return entries.length ? `<div class="bonus-list">${entries.map(([name, value]) => `<span class="bonus-chip">${escapeHtml(name)} <b>+${value}</b></span>`).join("")}</div>` : "";
}

function renderProgress() {
  $("#creation-progress").innerHTML = screens.map((label, index) => `
    <button type="button" class="progress-item ${index === state.screen ? "active" : ""} ${index < state.screen ? "done" : ""}"
      data-progress="${index}" ${index > state.furthest ? "disabled" : ""}>
      <span>${escapeHtml(label)}</span><i class="progress-dot"></i>
    </button>`).join("");
}

function renderBackgrounds() {
  const details = state.config.backgroundDetails;
  $("#backgrounds").innerHTML = state.config.backgrounds.map((name) => `
    <button type="button" class="choice-option ${state.background === name ? "selected" : ""}" data-background="${escapeHtml(name)}">
      <span>${escapeHtml(name)}</span>
    </button>`).join("");
  const name = state.background || state.config.backgrounds[0];
  const detail = details[name];
  $("#background-detail").innerHTML = `<p>ПРОИСХОЖДЕНИЕ</p><h3>${escapeHtml(name)}</h3><div class="lore-rule"></div><p class="lore-copy">${escapeHtml(detail.description)}</p><h4>ЛИЧНОЕ ДРЕВО</h4><p class="lore-copy">Таланты: <b>${escapeHtml(detail.talentSource||"—")}</b>. После регистрации ветка появится в личном деле вместе с базовыми деревьями Вершителя.</p><h4>НАЧАЛЬНАЯ ПОДГОТОВКА</h4>${bonusesHtml(detail.bonuses)}`;
}

function renderSpecializations(slot) {
  const prefix = slot === 0 ? "primary" : "secondary";
  const selected = state.specs[slot];
  $("#" + prefix + "-specializations").innerHTML = state.config.specializations.map((name) => `
    <button type="button" class="choice-option ${selected === name ? "selected" : ""}" data-spec-slot="${slot}" data-spec-name="${escapeHtml(name)}">
      <span>${escapeHtml(name)}</span>
    </button>`).join("");
  const name = selected || state.config.specializations[0];
  const detail = state.config.specializationDetails[name];
  $("#" + prefix + "-detail").innerHTML = `
    <p>${slot === 0 ? "ОСНОВНАЯ" : "ДОПОЛНИТЕЛЬНАЯ"} СПЕЦИАЛИЗАЦИЯ</p><h3>${escapeHtml(name)}</h3><div class="lore-rule"></div>
    <p class="lore-copy">${escapeHtml(detail.description)}</p><h4>БОНУСЫ К НАВЫКАМ</h4>${bonusesHtml(detail.bonuses)}
    <h4>ВЫБЕРИТЕ СТАРТОВУЮ СПОСОБНОСТЬ</h4><div class="ability-grid">${detail.abilities.map((ability) => `
      <button type="button" class="ability-choice ${state.abilities[slot] === ability.name ? "selected" : ""}" data-ability-slot="${slot}" data-ability-name="${escapeHtml(ability.name)}">
        <img src="${escapeHtml(ability.icon)}" alt="" width="72" height="72" loading="lazy">
        <span class="ability-body"><span class="ability-name">${escapeHtml(ability.name)}</span><span class="ability-type">${escapeHtml(ability.type)}</span>
          <span class="ability-description">${escapeHtml(ability.description)}</span>
          <span class="ability-meta"><span><i>ПЕРЕЗАРЯДКА</i><b>${escapeHtml(ability.cooldown)}</b></span><span><i>ДЛИТЕЛЬНОСТЬ</i><b>${escapeHtml(ability.duration)}</b></span></span>
          <span class="ability-effects">${ability.effects.map((effect) => `<em>${escapeHtml(effect)}</em>`).join("")}</span>
          <span class="ability-requirements">${escapeHtml(ability.requirements)}</span>
        </span>
      </button>`).join("")}</div>`;
}

function renderIdentity() {
  const input = $("#name");
  if (input.value !== state.name) input.value = state.name;
}

function attributeRelated(name, index) {
  return Object.entries(state.config.skillAttributes).filter(([, pair]) => pair[index] === name).map(([skill]) => skill);
}

function renderAttributes() {
  const used = Object.values(state.attributes).reduce((sum, value) => sum + value, 0);
  const left = state.config.attributeTotal - used;
  $("#attribute-counter").className = `counter ${left === 0 ? "done" : left < 0 ? "over" : ""}`;
  $("#attribute-counter").innerHTML = `<b>${left}</b><span>/ 8</span><small>${left === 0 ? "РАСПРЕДЕЛЕНО" : "ОСТАЛОСЬ"}</small>`;
  $("#attributes").innerHTML = state.config.attributes.map((name) => `
    <div class="stat-row ${state.focusedAttribute === name ? "focused" : ""}" data-focus-kind="attribute" data-focus-name="${escapeHtml(name)}">
      <span><b>${escapeHtml(name)}</b><small>${escapeHtml(state.config.attributeDetails[name].summary)}</small></span>
      <div class="stepper"><button type="button" data-step-kind="attribute" data-step-name="${escapeHtml(name)}" data-delta="-1" ${state.attributes[name] <= state.config.attributeMin ? "disabled" : ""}>‹</button><output>${state.attributes[name]}</output><button type="button" data-step-kind="attribute" data-step-name="${escapeHtml(name)}" data-delta="1" ${state.attributes[name] >= state.config.attributeMax || left <= 0 ? "disabled" : ""}>›</button></div>
    </div>`).join("");
  const name = state.focusedAttribute;
  const detail = state.config.attributeDetails[name];
  $("#attribute-detail").innerHTML = `<p>ХАРАКТЕРИСТИКА</p><h3>${escapeHtml(name)}</h3><div class="lore-rule"></div><p class="lore-copy">${escapeHtml(detail.summary)}</p><h4>ЭФФЕКТ КАЖДОГО ПУНКТА</h4><p class="effect-copy">${escapeHtml(detail.effects)}</p><h4>ОСНОВНЫЕ НАВЫКИ · ×1,5</h4><p class="related-skills">${attributeRelated(name, 0).map(escapeHtml).join(" · ") || "—"}</p><h4>ДОПОЛНИТЕЛЬНЫЕ НАВЫКИ · ×0,5</h4><p class="related-skills">${attributeRelated(name, 1).map(escapeHtml).join(" · ") || "—"}</p>`;
}

function skillBase(name) {
  const [primary, secondary] = state.config.skillAttributes[name];
  return Math.round(state.attributes[primary] * 1.5 + state.attributes[secondary] * 0.5);
}

function sourceBonuses(name) {
  const background = state.config.backgroundDetails[state.background]?.bonuses?.[name] || 0;
  const primary = state.config.specializationDetails[state.specs[0]]?.bonuses?.[name] || 0;
  const secondary = state.config.specializationDetails[state.specs[1]]?.bonuses?.[name] || 0;
  return { background, primary, secondary };
}

function skillTotal(name) {
  const bonus = sourceBonuses(name);
  return skillBase(name) + bonus.background + bonus.primary + bonus.secondary + state.skills[name];
}

function skillRow(name) {
  const [primary, secondary] = state.config.skillAttributes[name];
  const left = state.config.skillPoints - Object.values(state.skills).reduce((sum, value) => sum + value, 0);
  return `<div class="stat-row ${state.focusedSkill === name ? "focused" : ""}" data-focus-kind="skill" data-focus-name="${escapeHtml(name)}">
    <span><b>${escapeHtml(name)}</b><small>${escapeHtml(primary)} ×1,5 · ${escapeHtml(secondary)} ×0,5</small></span>
    <div class="stepper"><button type="button" data-step-kind="skill" data-step-name="${escapeHtml(name)}" data-delta="-1" ${state.skills[name] <= 0 ? "disabled" : ""}>‹</button><output>${skillTotal(name)}</output><button type="button" data-step-kind="skill" data-step-name="${escapeHtml(name)}" data-delta="1" ${left <= 0 ? "disabled" : ""}>›</button></div>
  </div>`;
}

function renderSkills() {
  const used = Object.values(state.skills).reduce((sum, value) => sum + value, 0);
  const left = state.config.skillPoints - used;
  $("#skill-counter").className = `counter ${left === 0 ? "done" : left < 0 ? "over" : ""}`;
  $("#skill-counter").innerHTML = `<b>${left}</b><span>/ ${state.config.skillPoints}</span><small>${left === 0 ? "РАСПРЕДЕЛЕНО" : "ОСТАЛОСЬ"}</small>`;
  const magicSkills = state.config.skills.filter((name) => !weaponSkills.includes(name) && !supportSkills.includes(name));
  $("#skills").innerHTML = `
    <div class="mundane-skills">
      <section class="skill-group"><h3>НАВЫКИ ОРУЖИЯ</h3>${weaponSkills.map(skillRow).join("")}</section>
      <section class="skill-group"><h3>НАВЫКИ ПОДДЕРЖКИ</h3>${supportSkills.map(skillRow).join("")}</section>
    </div>
    <section class="skill-group magic-skills"><header><span>СИГИЛЫ КАЙРОС</span><h3>НАВЫКИ ЗАКЛИНАНИЙ</h3><p>Магические школы отделены от оружейной и вспомогательной подготовки.</p></header>${magicSkills.map(skillRow).join("")}</section>`;
  const name = state.focusedSkill;
  const [primaryAttribute, secondaryAttribute] = state.config.skillAttributes[name];
  const bonus = sourceBonuses(name);
  const lines = [
    [`Базовое значение (${primaryAttribute} ${state.attributes[primaryAttribute]} × 1,5 + ${secondaryAttribute} ${state.attributes[secondaryAttribute]} × 0,5)`, skillBase(name)],
    [`Происхождение: ${state.background}`, bonus.background],
    [`Основная специализация: ${state.specs[0]}`, bonus.primary],
    [`Дополнительная специализация: ${state.specs[1]}`, bonus.secondary],
    ["Распределённые очки", state.skills[name]],
  ];
  const description = skillDescriptions[name] || `Определяет способность персонажа применять заклинания школы «${name.replace("Управление ", "") }». Чем выше навык, тем выше точность и шанс критического попадания.`;
  $("#skill-detail").innerHTML = `<p>НАВЫК</p><h3>${escapeHtml(name)}</h3><div class="lore-rule"></div><p class="lore-copy">${escapeHtml(description)}</p><h4>РАСЧЁТ ЗНАЧЕНИЯ</h4><div class="formula">${lines.map(([label, value]) => `<div><span>${escapeHtml(label)}</span><b>${value > 0 ? "+" : ""}${value}</b></div>`).join("")}<strong><span>ИТОГО</span><b>${skillTotal(name)}</b></strong></div><p class="formula-note">Навык растёт и во время игры при успешном применении.</p>`;
}

function validation() {
  const attrUsed = Object.values(state.attributes).reduce((sum, value) => sum + value, 0);
  const skillUsed = Object.values(state.skills).reduce((sum, value) => sum + value, 0);
  return [
    ["Происхождение", Boolean(state.background)], ["Основная специализация и способность", Boolean(state.specs[0] && state.abilities[0])],
    ["Дополнительная специализация и способность", Boolean(state.specs[1] && state.abilities[1])], ["Имя персонажа", state.name.trim().length >= 2],
    ["Характеристики", attrUsed === state.config.attributeTotal], ["Навыки", skillUsed === state.config.skillPoints],
  ];
}

function canAdvance(screen = state.screen) {
  const rules = validation();
  return screen >= 6 ? rules.every(([, ok]) => ok) : rules[screen][1];
}

function renderResult() {
  const rules = validation();
  $("#checks").innerHTML = rules.map(([label, ok]) => `<span class="${ok ? "ok" : ""}">${ok ? "✓" : "×"} ${escapeHtml(label)}</span>`).join("");
  $("#submit").disabled = !rules.every(([, ok]) => ok);
  const strongest = [...state.config.skills].sort((a, b) => skillTotal(b) - skillTotal(a)).slice(0, 6);
  $("#summary").textContent = [
    state.name.trim() || "Безымянный житель Империи", `Происхождение: ${state.background || "—"}`, "",
    `I. ${state.specs[0] || "—"} — ${state.abilities[0] || "—"}`, `II. ${state.specs[1] || "—"} — ${state.abilities[1] || "—"}`, "",
    "ХАРАКТЕРИСТИКИ", ...state.config.attributes.map((name) => `${name}: ${state.attributes[name]}`), "", "ВЕДУЩИЕ НАВЫКИ",
    ...strongest.map((name) => `${name}: ${skillTotal(name)}`),
  ].join("\n");
}

function renderNavigation() {
  $("#back").disabled = state.screen === 0;
  $("#next").hidden = state.screen === screens.length - 1;
  $("#step-status").textContent = `${state.screen + 1} / ${screens.length}`;
}

function renderAll() {
  document.querySelectorAll(".wizard-step").forEach((element, index) => { element.hidden = index !== state.screen; });
  renderProgress(); renderBackgrounds(); renderSpecializations(0); renderSpecializations(1); renderIdentity(); renderAttributes(); renderSkills(); renderResult(); renderNavigation(); annotateGlossary();
}

function moveTo(screen) {
  state.screen = Math.max(0, Math.min(screens.length - 1, screen));
  state.furthest = Math.max(state.furthest, state.screen);
  renderAll();
  $("#builder").scrollIntoView({ behavior: "smooth", block: "start" });
}

function pulseCurrent() {
  const current = document.querySelector(`.wizard-step[data-screen="${state.screen}"]`);
  current.classList.remove("shake"); void current.offsetWidth; current.classList.add("shake");
}

async function submitCharacter() {
  if (!canAdvance(6)) return;
  const button = $("#submit"); const status = $("#submit-status");
  button.disabled = true; status.textContent = "Сохраняем личное дело…";
  try {
    const response = await fetch(`${apiBase}/api/registration/${encodeURIComponent(token)}`, {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({
        name: state.name.trim(), background: state.background, specialization1: state.specs[0], specialization2: state.specs[1],
        ability1: state.abilities[0], ability2: state.abilities[1], attributes: state.attributes, skills: state.skills, portrait: state.portrait,
      }),
    });
    if (!response.ok) {
      const problem = await response.json().catch(() => ({}));
      throw new Error(problem.error || problem.reason || `Ошибка ${response.status}`);
    }
    const result = await response.json();
    $("#result-title").textContent = "Личное дело сохранено";
    $("#result-text").textContent = `Персонаж ${result.name} уже доступен в Дискорде по команде /персонаж.`;
    status.textContent = "Готово. Эту одноразовую страницу можно закрыть."; button.textContent = "СОХРАНЕНО";
  } catch (error) {
    status.textContent = error.message || "Не удалось сохранить персонажа."; button.disabled = false;
  }
}

function bindEvents() {
  document.addEventListener("click", (event) => {
    const background = event.target.closest("[data-background]");
    if (background) { state.background = background.dataset.background; renderAll(); return; }
    const spec = event.target.closest("[data-spec-slot]");
    if (spec) {
      const slot = Number(spec.dataset.specSlot); state.specs[slot] = spec.dataset.specName;
      const abilities = state.config.specializationDetails[state.specs[slot]].abilities;
      state.abilities[slot] = abilities.length === 1 ? abilities[0].name : ""; renderAll(); return;
    }
    const ability = event.target.closest("[data-ability-slot]");
    if (ability) { state.abilities[Number(ability.dataset.abilitySlot)] = ability.dataset.abilityName; renderAll(); return; }
    const step = event.target.closest("[data-step-kind]");
    if (step && !step.disabled) {
      const target = step.dataset.stepKind === "attribute" ? state.attributes : state.skills;
      if (step.dataset.stepKind === "attribute") state.focusedAttribute = step.dataset.stepName;
      else state.focusedSkill = step.dataset.stepName;
      target[step.dataset.stepName] += Number(step.dataset.delta); renderAll(); return;
    }
    const focus = event.target.closest("[data-focus-kind]");
    if (focus) {
      if (focus.dataset.focusKind === "attribute") state.focusedAttribute = focus.dataset.focusName;
      else state.focusedSkill = focus.dataset.focusName; renderAll(); return;
    }
    const progress = event.target.closest("[data-progress]");
    if (progress && !progress.disabled) moveTo(Number(progress.dataset.progress));
  });
  $("#name").addEventListener("input", (event) => { state.name = event.target.value; });
  $("#portrait").addEventListener("change", (event) => {
    const file = event.target.files[0]; if (!file) return;
    if (file.size > 5 * 1024 * 1024) { alert("Портрет должен быть меньше 5 МБ."); event.target.value = ""; return; }
    const reader = new FileReader(); reader.onload = () => { state.portrait = reader.result; $("#portrait-preview").src = reader.result; $("#portrait-preview").hidden = false; $("#portrait-empty").hidden = true; }; reader.readAsDataURL(file);
  });
  $("#back").addEventListener("click", () => moveTo(state.screen - 1));
  $("#next").addEventListener("click", () => canAdvance() ? moveTo(state.screen + 1) : pulseCurrent());
  $("#submit").addEventListener("click", submitCharacter);
  document.addEventListener("pointerover", (event) => { const term = event.target.closest?.(".glossary-term"); if (term) showGlossary(term); });
  document.addEventListener("pointerout", (event) => { const term = event.target.closest?.(".glossary-term"); if (term && !term.contains(event.relatedTarget)) hideGlossary(); });
  document.addEventListener("focusin", (event) => { const term = event.target.closest?.(".glossary-term"); if (term) showGlossary(term); });
  document.addEventListener("focusout", (event) => { if (event.target.closest?.(".glossary-term")) hideGlossary(); });
}

async function boot() {
  if (!token) { $("#connection").className = "connection error"; $("#connection").textContent = "Откройте личную ссылку, которую бот выдаёт командой /регистрация."; return; }
  try {
    const response = await fetch(`${apiBase}/api/registration/${encodeURIComponent(token)}`);
    if (!response.ok) throw new Error(response.status === 410 ? "Ссылка уже использована или истекла." : "Не удалось проверить личную ссылку.");
    const data = await response.json(); state.config = data.config;
    state.config.attributes.forEach((name) => { state.attributes[name] = 10; });
    state.config.skills.forEach((name) => { state.skills[name] = 0; });
    $("#connection").hidden = true; $("#form").hidden = false; bindEvents(); renderAll();
  } catch (error) { $("#connection").className = "connection error"; $("#connection").textContent = error.message; }
}

boot();
