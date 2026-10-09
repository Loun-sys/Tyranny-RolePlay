/* Touch users choose between moving the viewport and painting the map. */
let mapTouchPan = !!globalThis.matchMedia?.('(pointer: coarse)').matches;
let mapTouchDrag = null;
function setMapTouchPan(enabled) {
  mapTouchPan = enabled;
  document.querySelector('.map-scroll')?.classList.toggle('map-pan', enabled);
  const button = document.querySelector('[data-map-touch-pan]');
  button?.classList.toggle('active', enabled);
  button?.setAttribute('aria-pressed', String(enabled));
}
const renderMapEditorBeforeTouch = renderMapEditor;
renderMapEditor = function (...args) {
  renderMapEditorBeforeTouch(...args);
  const viewport = document.querySelector('.map-scroll'), tools = document.querySelector('.map-tools');
  if (!viewport || !tools) return;
  viewport.classList.toggle('map-pan', mapTouchPan);
  const button = document.createElement('button');
  button.type = 'button'; button.className = `dark-button ${mapTouchPan ? 'active' : ''}`;
  button.dataset.mapTouchPan = '1'; button.textContent = 'ПРОКРУТКА КАРТЫ';
  button.setAttribute('aria-pressed', String(mapTouchPan));
  button.title = 'Включите для перемещения карты пальцем; выключите для рисования и размещения токенов.';
  tools.prepend(button);
};
document.addEventListener('click', event => {
  const button = event.target.closest('[data-map-touch-pan]');
  if (!button) {
    if (event.target.closest('[data-map-tool]')) {
      setMapTouchPan(false);
    }
    return;
  }
  event.preventDefault(); event.stopImmediatePropagation();
  setMapTouchPan(!mapTouchPan);
}, true);

for (const name of ['change', 'input']) document.addEventListener(name, event => {
  if (['map-token-choice', 'map-token-filter'].includes(event.target.id)) setMapTouchPan(false);
}, true);
document.addEventListener('pointerdown', event => {
  if (!mapTouchPan || !event.target.closest('[data-map-cell]')) return;
  event.stopImmediatePropagation();
  if (event.pointerType !== 'touch' && event.button === 0) {
    event.preventDefault();
    const viewport = document.querySelector('.map-scroll');
    mapTouchDrag = { viewport, x: event.clientX, y: event.clientY, left: viewport.scrollLeft, top: viewport.scrollTop };
  }
}, true);
document.addEventListener('pointermove', event => {
  if (mapTouchDrag) {
    event.preventDefault();
    const drag = mapTouchDrag;
    drag.viewport.scrollLeft = drag.left + drag.x - event.clientX;
    drag.viewport.scrollTop = drag.top + drag.y - event.clientY;
    return;
  }
  if (event.pointerType !== 'touch' || !mapPainting || mapRectangle || mapTouchPan) return;
  const cell = document.elementFromPoint(event.clientX, event.clientY)?.closest('[data-map-cell]');
  if (!cell || cell.dataset.mapCell === mapLastCell) return;
  mapLastCell = cell.dataset.mapCell;
  paintMap(...cell.dataset.mapCell.split(':').map(Number)); drawMapGrid();
}, true);
document.addEventListener('pointerup', event => {
  mapTouchDrag = null;
  if (event.pointerType !== 'touch' || !mapRectangle || mapTouchPan) return;
  const cell = document.elementFromPoint(event.clientX, event.clientY)?.closest('[data-map-cell]');
  if (cell) {
    const [x, y] = cell.dataset.mapCell.split(':').map(Number);
    for (let yy = Math.min(y, mapRectangle.y); yy <= Math.max(y, mapRectangle.y); yy++)
      for (let xx = Math.min(x, mapRectangle.x); xx <= Math.max(x, mapRectangle.x); xx++) paintMap(xx, yy);
    drawMapGrid();
  }
  mapPainting = false; mapRectangle = null;
}, true);
document.addEventListener('pointercancel', () => { mapTouchDrag = null; mapPainting = false; mapRectangle = null; });
