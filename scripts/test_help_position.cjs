const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const source=fs.readFileSync('web/game-help.js','utf8'),start=source.indexOf(' function position(){'),end=source.indexOf('\n function show(',start);
function position(screen,viewport,rect,naturalHeight){
 const popup={style:{},get offsetHeight(){return Math.min(naturalHeight,parseFloat(this.style.maxHeight)||Infinity)}};
 const anchor={getBoundingClientRect:()=>rect};
 const context=vm.createContext({popup,active:{isConnected:true,closest:()=>anchor,getBoundingClientRect(){throw Error('Use the whole button, not its child icon')}},document:{documentElement:{clientWidth:screen}},innerHeight:viewport,hide(){throw Error('Unexpected hide')}});
 vm.runInContext(source.slice(start,end),context);context.position();
 return {left:parseFloat(popup.style.left),top:parseFloat(popup.style.top),height:popup.offsetHeight,width:parseFloat(popup.style.width),pointerEvents:popup.style.pointerEvents};
}
const normal=position(900,650,{left:100,right:250,top:50,bottom:100},100);assert.equal(normal.top,109);
const above=position(900,650,{left:100,right:250,top:500,bottom:550},150);assert.equal(above.top,341);
const side=position(1280,720,{left:620,right:1180,top:180,bottom:535},384);assert(side.left+side.width<620,'Large ability help stays beside the entire button');
const phone=position(390,650,{left:20,right:370,top:100,bottom:500},400);assert(phone.top>=500);assert(phone.top+phone.height<=638);assert.equal(phone.pointerEvents,'');
const covered=position(390,650,{left:20,right:370,top:0,bottom:650},500);assert.equal(covered.pointerEvents,'none','With no safe space, help cannot intercept selection');
console.log('Help placement: whole-control anchor, above/below/sides, scrollable phone card and non-intercepting full-height fallback OK');
