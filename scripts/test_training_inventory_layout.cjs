// Regression checks for the deliberately minimal training intro and portrait layout.
const fs = require('node:fs');
const assert = require('node:assert/strict');
const source = fs.readFileSync('web/archive.js', 'utf8');
const css = fs.readFileSync('web/archive-icons.css', 'utf8');
const intro = source.match(/if\(!training\.active\)\{p\.innerHTML=`([^`]+)`;return\}/)[1];
assert(intro.includes('Выводит токен персонажа на арену с манекенами, где можно зарамсится и посмотреть че делают кнопки.'));
assert.equal((intro.match(/<p>/g) || []).length, 1);
assert(!intro.includes('<h') && !intro.includes('<small') && !intro.includes('rune'));
assert(intro.includes('training-start'));
assert(!source.includes('Наведение показывает дальность'));
assert(!source.includes('ПОШАГОВЫЙ БОЙ · 1 КЛЕТКА = 1 МЕТР · НАГРАДЫ ОТКЛЮЧЕНЫ'));
assert.match(css, /\.paperdoll-character\s*\{[^}]*object-fit:\s*cover/);
assert.match(css, /\.paperdoll-character\s*\{[^}]*inset:\s*0;\s*width:\s*100%;\s*height:\s*100%/);
assert.equal((css.match(/\.paperdoll-character\s*\{/g)||[]).length,1,'mobile must not shrink portrait again');
assert.match(css, /\.paper-slot b\s*\{[^}]*background:\s*rgba\(0,0,0,\.82\)/);
assert(!css.includes('.paper-slot b{display:none}'));
console.log('Training intro, arena text, portrait fill and slot-label backplates: OK');
