const fs = require('node:fs'), vm = require('node:vm'), assert = require('node:assert/strict');
const source = fs.readFileSync('web/registration-network.js', 'utf8');
const app = fs.readFileSync('web/app.js', 'utf8');
const bootSource = app.slice(app.indexOf('let connectionPending ='), app.lastIndexOf('boot();'));
const response = (status, data) => ({ ok: status < 400, status, json: async () => data });

function harness(fetch) {
  const context = vm.createContext({ fetch, AbortController,
    setTimeout: (fn, ms) => { if (ms < 3000) fn(); return 1; }, clearTimeout: () => {},
  });
  vm.runInContext(source, context);
  return context;
}

async function test() {
  let calls = 0, retries = [];
  let context = harness(async (_url, options) => {
    calls++;
    assert.equal(options.headers, undefined); // no needless GET preflight
    assert.equal(options.cache, 'no-store');
    assert.equal(options.referrerPolicy, 'no-referrer');
    if (calls < 3) throw new TypeError('Failed to fetch');
    return response(200, { ok: true });
  });
  context.onRetry = n => retries.push(n);
  assert.equal((await vm.runInContext("RegistrationNetwork.request('/registration', {}, onRetry)", context)).ok, true);
  assert.equal(calls, 3); assert.deepEqual(retries, [2, 3]);

  calls = 0;
  context = harness(async () => { calls++; return calls < 3 ? response(503, null) : response(200, { ok: true }); });
  await vm.runInContext("RegistrationNetwork.request('/registration')", context);
  assert.equal(calls, 3);
  context.fetch = async () => response(500, { error: 'Ошибка сервера' });
  await assert.rejects(() => vm.runInContext("RegistrationNetwork.request('/registration')", context), /Ошибка сервера.*Нажмите «Повторить»/);

  for (const status of [400, 403, 410]) {
    calls = 0;
    context = harness(async () => { calls++; return response(status, { error: 'Ссылка недействительна' }); });
    await assert.rejects(() => vm.runInContext("RegistrationNetwork.request('/registration')", context),
      error => error.status === status && !error.retryable && /Ссылка недействительна/.test(error.message));
    assert.equal(calls, 1);
  }

  calls = 0;
  context = harness(async () => { calls++; throw new TypeError('Failed to fetch'); });
  await assert.rejects(() => vm.runInContext("RegistrationNetwork.request('/registration')", context), /Нажмите «Повторить»/);
  assert.equal(calls, 3);
  calls = 0;
  await assert.rejects(() => vm.runInContext("RegistrationNetwork.request('/registration', {method:'POST', body:'{}'})", context), /проверьте \/персонаж/);
  assert.equal(calls, 1); // never automatically re-create a character
  context.fetch = async () => response(200, null);
  await assert.rejects(() => vm.runInContext("RegistrationNetwork.request('/registration', {method:'POST'})", context), /мог уже сохраниться/);

  // A hanging connection is aborted instead of leaving the constructor stuck.
  let abortTimer;
  context = harness(async (_url, options) => new Promise((_, reject) => {
    options.signal.addEventListener('abort', () => reject(Object.assign(new Error('Timed out'), { name: 'AbortError' })));
    queueMicrotask(() => abortTimer());
  }));
  context.setTimeout = (fn, ms) => { if (ms >= 3000) abortTimer = fn; else fn(); return 1; };
  await assert.rejects(() => vm.runInContext("RegistrationNetwork.request('/registration')", context), /Нажмите «Повторить»/);

  // Manual recovery doesn't reload the page, lose draft fields, or bind events twice.
  const nodes = new Map(['connection', 'connection-status', 'connection-retry', 'form'].map(id =>
    ['#' + id, { hidden: false, className: '', textContent: '', addEventListener() {} }]));
  const state = { config: null, name: 'Сохранённое имя', portrait: 'data:image/png;base64,draft', attributes: {}, skills: {} };
  calls = 0; let bindings = 0;
  context = harness(async () => { calls++; throw new TypeError('Failed to fetch'); });
  Object.assign(context, { $: selector => nodes.get(selector), state, token: 'test-only', apiBase: 'https://server.example',
    applyCreationGlossary() {}, bindEvents() { bindings++; }, renderAll() {}, loadCreationGlossary: async () => {},
  });
  vm.runInContext(bootSource, context);
  await vm.runInContext('boot()', context);
  assert.equal(nodes.get('#connection-retry').hidden, false);
  assert.match(nodes.get('#connection-status').textContent, /Нажмите «Повторить»/);
  context.fetch = async () => { calls++; return response(200, { config: { attributes: ['Сила'], skills: ['Знания'] } }); };
  await vm.runInContext('boot()', context);
  assert.equal(nodes.get('#connection').hidden, true);
  assert.equal(nodes.get('#form').hidden, false);
  assert.equal(state.name, 'Сохранённое имя'); assert.equal(state.portrait, 'data:image/png;base64,draft');
  await vm.runInContext('boot()', context);
  assert.equal(bindings, 1); assert.equal(calls, 4);

  const submitNodes = new Map(['submit', 'submit-status', 'result-title', 'result-text'].map(id => ['#' + id, {}]));
  const submitState = { name: 'Тест', specs: [], abilities: [] };
  let finishSave;
  calls = 0;
  context = harness(async () => { calls++; return new Promise(resolve => { finishSave = resolve; }); });
  Object.assign(context, { $: selector => submitNodes.get(selector), state: submitState, token: 'test-only',
    apiBase: 'https://server.example', canAdvance: () => true,
  });
  vm.runInContext(app.slice(app.indexOf('async function submitCharacter()'), app.indexOf('function bindEvents()')), context);
  const saving = vm.runInContext('submitCharacter()', context);
  await vm.runInContext('submitCharacter()', context);
  assert.equal(calls, 1); assert.equal(submitState.submissionPending, true);
  finishSave(response(200, { name: 'Тест' })); await saving;
  await vm.runInContext('submitCharacter()', context);
  assert.equal(calls, 1); assert.equal(submitState.submissionPending, false);
  assert.equal(submitState.submissionComplete, true);
  assert.equal(submitNodes.get('#submit').textContent, 'СОХРАНЕНО');

  console.log('Registration network: GET retry/recovery, HTTP authentication errors, no POST replay/duplicates, draft preserved OK');
}
test().catch(error => { console.error(error); process.exitCode = 1; });
