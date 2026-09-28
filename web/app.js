"use strict";

const $ = (selector) => document.querySelector(selector);
const screens = ["История", "Основа", "Доп.", "Имя", "Характеристики", "Навыки", "Итог"];
const weaponSkills = ["Волшебный посох", "Луки", "Безоружный бой", "Двуручное оружие", "Одноручное оружие", "Парное оружие"];
const supportSkills = ["Знания", "Уклонение", "Хитроумие", "Атлетика", "Парирование"];
const skillDescriptions = {
  "Одноручное оружие": "Определяет точность и критические попадания мечами, булавами, копьями и другим одноручным оружием.",
  "Двуручное оружие": "Определяет точность и критические попадания тяжёлым двуручным оружием.",
  "Парное оружие": "Определяет эффективность одновременной атаки оружием в обеих руках.",
  "Луки": "Определяет точность и критические попадания луками на дальней дистанции.",
  "Безоружный бой": "Определяет точность, критические попадания и эффективность атак без оружия.",
  "Волшебный посох": "Определяет точность и критические попадания при атаках волшебными посохами.",
  "Атлетика": "Используется для физических испытаний, силовых действий и ряда боевых способностей.",
  "Парирование": "Защищает от оружейных атак, позволяя отклонять удары оружием или щитом.",
  "Уклонение": "Защищает от атак движением и особенно полезно персонажам без тяжёлой брони.",
  "Знания": "Определяют сложность доступных заклинаний и помогают в учёных, магических и исторических проверках.",
  "Хитроумие": "Отвечает за скрытность, ловушки, замки и находчивые варианты в диалогах.",
};

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
      <span>${escapeHtml(name)}</span><small>${Object.entries(details[name].bonuses).map(([skill, value]) => `${skill} +${value}`).join(" · ")}</small>
    </button>`).join("");
  const name = state.background || state.config.backgrounds[0];
  const detail = details[name];
  $("#background-detail").innerHTML = `<p>ПРОИСХОЖДЕНИЕ</p><h3>${escapeHtml(name)}</h3><div class="lore-rule"></div><p class="lore-copy">${escapeHtml(detail.description)}</p><h4>НАЧАЛЬНАЯ ПОДГОТОВКА</h4>${bonusesHtml(detail.bonuses)}`;
}

function renderSpecializations(slot) {
  const prefix = slot === 0 ? "primary" : "secondary";
  const selected = state.specs[slot];
  $("#" + prefix + "-specializations").innerHTML = state.config.specializations.map((name) => `
    <button type="button" class="choice-option ${selected === name ? "selected" : ""}" data-spec-slot="${slot}" data-spec-name="${escapeHtml(name)}">
      <span>${escapeHtml(name)}</span><small>${Object.entries(state.config.specializationDetails[name].bonuses).map(([skill, value]) => `${skill} +${value}`).join(" · ")}</small>
    </button>`).join("");
  const name = selected || state.config.specializations[0];
  const detail = state.config.specializationDetails[name];
  $("#" + prefix + "-detail").innerHTML = `
    <p>${slot === 0 ? "ОСНОВНАЯ" : "ДОПОЛНИТЕЛЬНАЯ"} СПЕЦИАЛИЗАЦИЯ</p><h3>${escapeHtml(name)}</h3><div class="lore-rule"></div>
    <p class="lore-copy">${escapeHtml(detail.description)}</p><h4>БОНУСЫ К НАВЫКАМ</h4>${bonusesHtml(detail.bonuses)}
    <h4>ВЫБЕРИТЕ СТАРТОВУЮ СПОСОБНОСТЬ</h4><div class="ability-grid">${detail.abilities.map((ability) => `
      <button type="button" class="ability-choice ${state.abilities[slot] === ability.name ? "selected" : ""}" data-ability-slot="${slot}" data-ability-name="${escapeHtml(ability.name)}">
        <b>${escapeHtml(ability.name)}</b><span>${escapeHtml(ability.description)}</span>
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
  $("#skills").innerHTML = [
    ["НАВЫКИ ОРУЖИЯ", weaponSkills], ["НАВЫКИ ПОДДЕРЖКИ", supportSkills], ["НАВЫКИ МАГИИ", magicSkills],
  ].map(([label, names]) => `<section class="skill-group"><h3>${label}</h3>${names.map(skillRow).join("")}</section>`).join("");
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
  renderProgress(); renderBackgrounds(); renderSpecializations(0); renderSpecializations(1); renderIdentity(); renderAttributes(); renderSkills(); renderResult(); renderNavigation();
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
    $("#result-text").textContent = `Персонаж ${result.name} уже доступен в Discord по команде /персонаж.`;
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
