// Seitengerüst (plaene/einstellungen-neu.md, Paket 1): every settings page looks the same. The rows between two
// section headings (h3.sec) go into one box (.sgrp) under a small heading, short choices (2 to 4 options) become
// segment buttons, and the save bar floats at the bottom only while something is unsaved. Only the look changes:
// ids, order and siblings of the rows stay as they are, so loading, saving, the search and "Mehr" work unchanged.
(()=>{
// a child that ends a box: the page head, a heading, the save bar, "Erweitert" and blocks that bring their own headings
const EDGE='h2.pt,.pintro,h3.sec,.savebar,details.adv,details.fgrp,.fbar,.cfgback,.ptabs,.sgrp,summary,#chatdefaults,.setpane';
function grp(root){
  if(!root||root.dataset.sgrp)return;root.dataset.sgrp='1';let box=null;
  for(const el of [...root.children]){
    if(el.matches(EDGE)||el.querySelector(':scope h3.sec')){box=null;
      if(el.matches('details.adv'))grp(el);else if(!el.matches(EDGE))grp(el);continue}
    if(el.tagName==='SCRIPT')continue;
    if(!box){box=document.createElement('div');box.className='sgrp';el.before(box)}
    box.append(el)}}
// a select with 2 to 4 short options in a setting row: segment buttons in front of it, the select stays (hidden)
// and keeps its value, events and id; setting .value from code (loadCfg) redraws the buttons too
const PROTO=Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype,'value');
function seg(s){
  if(s.dataset.seg||s.multiple||s.id===''||/voice|model/i.test(s.id)||s.closest('[data-noseg]'))return;const o=[...s.options];
  if(o.length<2||o.length>4||o.some(x=>x.text.length>14)||o.reduce((n,x)=>n+x.text.length,0)>34)return;
  s.dataset.seg='1';const box=document.createElement('span');box.className='segc';box.setAttribute('role','radiogroup');
  const lab=s.closest('.setrow')&&s.closest('.setrow').querySelector('.lbl b');if(lab)box.setAttribute('aria-label',lab.textContent);
  const draw=()=>{const ok=s.options.length>1&&s.options.length<5;box.hidden=!ok;s.classList.toggle('segsel',ok);if(!ok)return;box.innerHTML='';[...s.options].forEach(x=>{const b=document.createElement('button');b.type='button';b.textContent=x.text;
    b.dataset.v=x.value;b.setAttribute('role','radio');const on=x.value===PROTO.get.call(s);b.setAttribute('aria-checked',on);b.className=on?'on':'';
    b.disabled=s.disabled;box.appendChild(b)})};
  box.addEventListener('click',e=>{const b=e.target.closest('button');if(!b||s.disabled)return;PROTO.set.call(s,b.dataset.v);draw();
    s.dispatchEvent(new Event('input',{bubbles:true}));s.dispatchEvent(new Event('change',{bubbles:true}))});
  Object.defineProperty(s,'value',{configurable:true,get(){return PROTO.get.call(s)},set(v){PROTO.set.call(s,v);draw()}});
  s.addEventListener('change',draw);new MutationObserver(draw).observe(s,{childList:true,attributes:true,attributeFilter:['disabled']});
  s.before(box);draw()}
// only choices that are fixed: the selects of the page itself (first pass) and of the drawn settings rows (.setpane);
// lists filled from data (profiles, voices, models) stay a select, however short they are today
function segs(root,later){root.querySelectorAll(later?'.setpane .setrow select':'.setrow select').forEach(seg)}
window.pageFrame=root=>{if(!root)return;root.querySelectorAll('.pane').forEach(p=>{if(p.id!=='pane-feat')grp(p)});segs(root)};
function all(){pageFrame($('cfg'))}
// the changed rows carry a line on the left, and the floating bar names them ("Ungespeichert: Temperatur, …")
function names(p){const n=[...p.querySelectorAll('.setrow.dirtyrow .lbl>b')].map(b=>b.firstChild&&b.firstChild.nodeValue?b.firstChild.nodeValue.trim():b.textContent.trim()).filter(Boolean);
  const u=p.querySelector(':scope>.savebar .unsaved');if(!u)return;
  u.textContent=!n.length?t('Ungespeicherte Änderungen','Unsaved changes'):(n.length===1?t('1 Änderung: ','1 change: '):n.length+t(' Änderungen: ',' changes: '))+n.slice(0,3).join(', ')+(n.length>3?' …':'')}
const mark=e=>{const p=e.target.closest&&e.target.closest('#cfg .pane');if(!p||!p.querySelector('.savebtn')||/^pw/.test(e.target.id)||e.target.closest('[data-nodirty]'))return;
  const r=e.target.closest('.setrow');if(r)r.classList.add('dirtyrow');setTimeout(()=>names(p),0)};
$('cfg').addEventListener('input',mark);$('cfg').addEventListener('change',mark);
// saved or discarded: the pane loses "dirty", the lines go
new MutationObserver(ms=>ms.forEach(m=>{const p=m.target;if(p.classList.contains('pane')&&!p.classList.contains('dirty'))p.querySelectorAll('.dirtyrow').forEach(r=>r.classList.remove('dirtyrow'))}))
  .observe($('cfg'),{subtree:true,attributes:true,attributeFilter:['class']});
// rows that other scripts draw later (Vorgaben: renderSet on every load) get their boxes and segments as they arrive
// (at most every 60 ms, but never put off: pages that change all the time must not keep the boxes away)
new MutationObserver(()=>{if(all.t)return;all.t=setTimeout(()=>{all.t=0;$('cfg').querySelectorAll('.setpane:not([data-sgrp])').forEach(grp);segs($('cfg'),true)},60)}).observe($('cfg'),{childList:true,subtree:true});
all();
// symbols in the settings menu, the second column of Zustand, Funktionen and Personen und Geräte, the groups of
// Funktionen and the pages of Ich: names from icons.js (one source, line symbols in the text colour, Redesign Stufe 3);
// appended after the text so code that reads the button's first text node (dirty pages, the search) keeps working,
// CSS puts them in front
const IC={start:'grid',feat:'all',talk:'sliders',ai:'brain',asr:'mic',tts:'vol',voices:'wave',sec:'lock',sysc:'cpu',upd:'download',bak:'box',
  // the pages of Zustand (base.js subnav)
  'z:mon':'mon','z:live':'radio','z:logs':'logs','z:test':'check','z:werk':'wrench','z:verb':'bulb','z:praxis':'clipboard',
  'z:usage':'bars','z:models':'brain','z:tech':'cpu',
  // Funktionen and Personen und Geräte the same way (Dominik 2026-10-17: „durchgängigen Style verwenden“)
  'z:feat':'all','z:route':'route','z:int':'book','z:prof':'prof','z:apps':'grid'};
function icon(k){const n=IC[k];if(!n)return null;const sp=document.createElement('span');sp.className='cic';sp.setAttribute('aria-hidden','true');
  sp.appendChild(icNode(n));return sp}
document.querySelectorAll('#cfgnav button[data-p]').forEach(b=>{if(b.querySelector('.cic'))return;const i=icon(b.dataset.p);if(i){b.appendChild(i);b.classList.add('hasic')}});
window.pageIcon=icon;
// the pages of Ich get symbols too: one per group (as on the Funktionen page), a few pages their own symbol
const MEG={talk:'bubble',speed:'bolt',data:'db',day:'cal',post:'mail',home:'home',go:'mobile',sec:'lock'};
const MEI={overbox:'grid',gobox:'flag',kannbox:'bulb',setbox:'bubble',loginbox:'user',bgbox:'mon',usebox:'bars',telbox:'tel',logbox:'logs',
  secbox:'lock',voicebox:'wave',rpbox:'warn'};
function featGroupIcons(){document.querySelectorAll('#pane-feat .fgrp>summary b').forEach(b=>{const g=b.closest('.fgrp').dataset.grp,d=MEG[g];
  if(!d||b.querySelector('.cic'))return;IC['g:'+g]=d;b.appendChild(icon('g:'+g))})}
featGroupIcons();
function meIcons(){const nav=$('ptabs');if(!nav)return;nav.querySelectorAll('button[data-t]').forEach(b=>{if(b.querySelector('.cic'))return;
  const id=b.dataset.t,g=typeof meGroup==='function'?meGroup(id):null,d=MEI[id]||MEG[g];if(!d)return;
  IC['me:'+id]=d;const i=icon('me:'+id);b.appendChild(i);b.classList.add('hasic')})}
if($('ptabs')){new MutationObserver(meIcons).observe($('ptabs'),{childList:true});meIcons()}
window.pageGroup=grp;window.pageSeg=root=>root.querySelectorAll('.setpane .setrow select').forEach(seg);
})();
