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
// symbols in the settings menu (one colour per block, like the iPhone settings); appended after the text so code
// that reads the button's first text node (dirty pages, the search) keeps working, CSS puts them in front
const IC={start:['gray','M4 4h7v7H4zM13 4h7v7h-7zM4 13h7v7H4zM13 13h7v7h-7z'],feat:['violet','M4 6h16M4 12h16M4 18h16'],
  talk:['violet','M4 6h16M4 12h16M4 18h16M8 4v4M15 10v4M10 16v4'],ai:['blue','M12 3a4 4 0 00-4 4 4 4 0 00-3 6.5A4 4 0 009 20h6a4 4 0 004-6.5A4 4 0 0016 7a4 4 0 00-4-4zM12 3v17'],
  asr:['teal','M9 3h6v11H9zM5 11a7 7 0 0014 0M12 18v3'],tts:['teal','M4 9h4l5-4v14l-5-4H4zM16 9a4 4 0 010 6M19 6a8 8 0 010 12'],
  voices:['teal','M3 12h2M7 8v8M11 5v14M15 8v8M19 11v2'],sec:['red','M5 11h14v10H5zM8 11V7a4 4 0 018 0v4'],
  sysc:['gray','M6 6h12v12H6zM9 2v4M15 2v4M9 18v4M15 18v4M2 9h4M2 15h4M18 9h4M18 15h4'],upd:['green','M12 3v12M7 10l5 5 5-5M4 20h16'],
  bak:['green','M3 7l9-4 9 4v10l-9 4-9-4zM3 7l9 4 9-4M12 11v10']};
const NS='http://www.w3.org/2000/svg';
function icon(k){const d=IC[k];if(!d)return null;const sp=document.createElement('span');sp.className='cic c-'+d[0];sp.setAttribute('aria-hidden','true');
  const sv=document.createElementNS(NS,'svg');sv.setAttribute('viewBox','0 0 24 24');const pa=document.createElementNS(NS,'path');pa.setAttribute('d',d[1]);sv.appendChild(pa);sp.appendChild(sv);return sp}
document.querySelectorAll('#cfgnav button[data-p]').forEach(b=>{if(b.querySelector('.cic'))return;const i=icon(b.dataset.p);if(i){b.appendChild(i);b.classList.add('hasic')}});
window.pageIcon=icon;
// the pages of Ich get symbols too: a colour per group (as on the Funktionen page), a few pages their own symbol
const MEG={talk:['violet','M4 5h16v11H9l-5 4z'],speed:['violet','M13 3L5 14h6l-1 7 8-11h-6z'],data:['blue','M5 6c0-1.7 3-3 7-3s7 1.3 7 3-3 3-7 3-7-1.3-7-3zM5 6v12c0 1.7 3 3 7 3s7-1.3 7-3V6M5 12c0 1.7 3 3 7 3s7-1.3 7-3'],
  day:['amber','M4 6h16v14H4zM4 10h16M9 3v4M15 3v4'],post:['blue','M3 6h18v12H3zM3 7l9 6 9-6'],home:['green','M4 11l8-7 8 7M6 10v10h12V10'],
  go:['teal','M8 3h8v18H8zM11 18h2'],sec:['red','M5 11h14v10H5zM8 11V7a4 4 0 018 0v4']};
const MEI={overbox:['gray','M4 4h7v7H4zM13 4h7v7h-7zM4 13h7v7H4zM13 13h7v7h-7z'],gobox:['green','M5 21V4h11l-2 4 2 4H5'],kannbox:['amber','M9 18h6M10 21h4M12 3a6 6 0 00-3.5 10.9c.6.5 1 1.2 1 2.1h5c0-.9.4-1.6 1-2.1A6 6 0 0012 3z'],setbox:['violet','M4 5h16v11H9l-5 4z'],
  loginbox:['gray','M12 12a4 4 0 100-8 4 4 0 000 8zM4 21a8 8 0 0116 0'],bgbox:['red','M3 12h4l3-7 4 14 3-7h4'],usebox:['blue','M4 20V10M10 20V4M16 20v-7M22 20H2'],telbox:['green','M5 4h4l2 5-2.5 1.5a11 11 0 005 5L15 13l5 2v4a2 2 0 01-2 2A16 16 0 013 6a2 2 0 012-2'],logbox:['gray','M8 6h12M8 12h12M8 18h12M4 6h.01M4 12h.01M4 18h.01'],
  secbox:['red','M5 11h14v10H5zM8 11V7a4 4 0 018 0v4'],voicebox:['teal','M3 12h2M7 8v8M11 5v14M15 8v8M19 11v2'],rpbox:['amber','M12 8v5M12 16h.01M10.3 3.9L2 18a2 2 0 001.7 3h16.6a2 2 0 001.7-3L13.7 3.9a2 2 0 00-3.4 0z']};
function meIcons(){const nav=$('ptabs');if(!nav)return;nav.querySelectorAll('button[data-t]').forEach(b=>{if(b.querySelector('.cic'))return;
  const id=b.dataset.t,g=typeof meGroup==='function'?meGroup(id):null,d=MEI[id]||MEG[g];if(!d)return;
  IC['me:'+id]=d;const i=icon('me:'+id);b.appendChild(i);b.classList.add('hasic')})}
if($('ptabs')){new MutationObserver(meIcons).observe($('ptabs'),{childList:true});meIcons()}
window.pageGroup=grp;window.pageSeg=root=>root.querySelectorAll('.setpane .setrow select').forEach(seg);
})();
