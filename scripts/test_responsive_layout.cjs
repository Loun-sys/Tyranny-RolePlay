const fs = require('node:fs'), assert = require('node:assert/strict'), vm = require('node:vm');
const css = fs.readFileSync('web/responsive.css', 'utf8');
for (const page of ['index', 'archive', 'admin', 'master-combat']) {
  const html = fs.readFileSync(`web/${page}.html`, 'utf8');
  assert(html.includes('width=device-width,initial-scale=1'));
  assert(html.includes('responsive.css?v=20261005-1'));
  assert(html.indexOf('responsive.css') > html.lastIndexOf('stylesheet', html.indexOf('responsive.css') - 2));
}
assert(css.includes('@media (min-width: 1400px)'));
assert(css.includes('@media (max-width: 760px)'));
assert(css.includes('@media (max-width: 420px)'));
assert(css.includes('width: min(1920px, 100%)'));
assert(css.includes('minmax(min(100%, 280px), 1fr)'));
assert(css.includes('.inventory-screen .paperdoll { grid-row: 1;'));
assert(css.includes('.combat-sidebar .original-quick { flex: 0 0 44px;'));
assert(css.includes('grid-row: 2; order: initial; width: 100%;'));
assert(css.includes('font-size: 16px; } /* no iOS focus zoom */'));
assert(!css.includes('overflow-x: hidden'), 'Do not conceal page overflow instead of fixing it');

const events = {}, classes = new Set();
const classList = { toggle(name, enabled) { enabled ? classes.add(name) : classes.delete(name); }, remove(name) { classes.delete(name); } };
const viewport = { classList, scrollLeft: 15, scrollTop: 25 }, tools = { prepend(button) { this.button = button; } };
let renders = 0, draws = 0, paints = [];
const context = vm.createContext({
  matchMedia: () => ({ matches: true }), renderMapEditor() { renders++; },
  mapPainting: false, mapLastCell: '', mapRectangle: null, paintMap: (x, y) => paints.push([x, y]), drawMapGrid() { draws++; },
  document: { querySelector: selector => selector === '.map-scroll' ? viewport : selector === '[data-map-touch-pan]' ? tools.button : tools,
    createElement: () => ({ dataset: {}, classList, setAttribute(name, value) { this[name] = value; } }),
    addEventListener: (name, callback) => { events[name] = callback; },
    elementFromPoint: () => ({ closest: () => ({ dataset: { mapCell: '2:3' } }) }),
  },
});
vm.runInContext(fs.readFileSync('web/mobile-map-editor.js', 'utf8'), context);
vm.runInContext('renderMapEditor()', context);
assert.equal(renders, 1); assert(classes.has('map-pan')); assert.equal(tools.button['aria-pressed'], 'true');
const event = { target: { closest: selector => selector === '[data-map-touch-pan]' ? tools.button : null },
  prevented: false, stopped: false, preventDefault() { this.prevented = true; }, stopImmediatePropagation() { this.stopped = true; } };
events.click(event); assert(!classes.has('map-pan')); assert.equal(tools.button['aria-pressed'], 'false');
assert(event.prevented && event.stopped);
context.mapPainting = true;
events.pointermove({ pointerType: 'touch', clientX: 20, clientY: 30 });
assert.deepEqual(paints, [[2, 3]]); assert.equal(draws, 1);
events.pointermove({ pointerType: 'touch', clientX: 20, clientY: 30 }); assert.equal(draws, 1, 'No duplicate brush writes');
context.mapRectangle = { x: 1, y: 2 };
events.pointerup({ pointerType: 'touch', clientX: 20, clientY: 30 });
assert.deepEqual(paints.slice(1), [[1, 2], [2, 2], [1, 3], [2, 3]]);
assert.equal(context.mapRectangle, null); assert.equal(context.mapPainting, false);
context.mapPainting = true; context.mapRectangle = { x: 1, y: 1 };
events.pointercancel(); assert.equal(context.mapPainting, false); assert.equal(context.mapRectangle, null);
events.click(event); // pan on
const touch = { ...event, pointerType: 'touch', target: { closest: () => ({}) }, prevented: false, stopped: false };
events.pointerdown(touch); assert(touch.stopped); assert.equal(touch.prevented, false, 'Native finger scroll is not cancelled');
events.pointerdown({ ...touch, pointerType: 'mouse', button: 0, clientX: 50, clientY: 60 });
events.pointermove({ clientX: 40, clientY: 40, preventDefault() {} });
assert.equal(viewport.scrollLeft, 25); assert.equal(viewport.scrollTop, 45);
events.pointerup({ pointerType: 'mouse' });
events.click({ target: { closest: selector => selector === '[data-map-tool]' ? {} : null } });
assert(!classes.has('map-pan'), 'Choosing a drawing tool exits pan mode');
assert.equal(tools.button['aria-pressed'], 'false');
events.click(event);
events.change({ target: { id: 'map-token-choice' } });
assert(!classes.has('map-pan'), 'Choosing a token enables placement');
assert.equal(tools.button['aria-pressed'], 'false');
console.log('Responsive layout: all pages, wide/phone breakpoints, finger-sized HUD, isolated map scroll, touch brush/rectangle/cancel and mouse pan OK');
