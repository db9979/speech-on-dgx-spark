// Phones look and feel like the iPhone app (plan handy-wie-app.md, V01.0.281). Below 760 px the page gets the app's tab
// bar (Spark, Heute, Dokumente, Ich, Verwalten), its chat (face, bubbles, a big microphone, the text field always
// there), lists like the iOS settings, pages that slide in with "‹ back" on top, sheets from below, and the phone's
// back gesture goes one level up. It is only a second drawing of the same page: the elements are moved, not copied,
// every switch and check stays where it is, and what a tab shows is still decided by the server (a hidden tab is not
// a right). "Am Rechner-Layout zeigen" turns it off for this browser (localStorage "appview" = "off").
const APV=(()=>{
const NAR=matchMedia('(max-width:760px)'),STAND=matchMedia('(display-mode: standalone)');
const B=document.body;
const wanted=()=>{try{return localStorage.getItem('appview')!=='off'}catch{return true}};
let ON=false,TAB='spark',hd=0,dirty=false;
const SV=p=>`<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${p}</svg>`;
const IC={spark:'<path d="M21 12a8 8 0 0 1-11.6 7.1L4 20l1-4.6A8 8 0 1 1 21 12z"/>',
  today:'<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/>',
  docs:'<path d="M14 3H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9z"/><path d="M14 3v6h6M8 13h8M8 17h5"/>',
  me:'<circle cx="12" cy="8" r="4"/><path d="M4 21a8 8 0 0 1 16 0"/>',
  manage:'<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z"/>',
  new:'<path d="M12 20h9"/><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4z"/>',
  hist:'<path d="M3 12a9 9 0 1 0 3-6.7M3 4v5h5"/><path d="M12 7.5V12l3 2"/>',
  set:'<path d="M4 6h10M18 6h2M4 12h4M12 12h8M4 18h12"/><circle cx="16" cy="6" r="2"/><circle cx="10" cy="12" r="2"/><circle cx="18" cy="18" r="2"/>',
  more:'<circle cx="5" cy="12" r="1.6"/><circle cx="12" cy="12" r="1.6"/><circle cx="19" cy="12" r="1.6"/>',
  back:'<path d="M15 5l-7 7 7 7"/>',find:'<circle cx="11" cy="11" r="7"/><path d="M20 20l-3.5-3.5"/>'};
const TABS=[['spark',t('Spark','Spark')],['today',t('Heute','Today')],['docs',t('Dokumente','Documents')],['me',t('Ich','Me')],['manage',t('Verwalten','Manage')]];
const mk=(tag,id,cls,html)=>{const e=document.createElement(tag);if(id)e.id=id;if(cls)e.className=cls;if(html!=null)e.innerHTML=html;return e};
const label=b=>b?[...b.childNodes].filter(n=>n.nodeType===3).map(n=>n.textContent).join('').trim():'';
const navBtn=s=>document.querySelector(`nav button[data-s=${s}]`);
const mainEl=()=>document.querySelector('main');
// ---------------------------------------------------------------- the pieces (built once, hidden without .appview)
const bar=mk('div','apbar','',`<button type="button" class="apnb" id="apback">${SV(IC.back)}<span></span></button><div class="aplead" id="aplead"></div><b id="aptitle"></b><div class="aptrail" id="aptrail"></div>`);
const tabs=mk('div','aptabs','',TABS.map(([k,l])=>`<button type="button" data-tab="${k}">${SV(IC[k])}<span>${esc(l)}</span>${k==='manage'?'<em class="apdot" hidden></em>':''}</button>`).join(''));
tabs.setAttribute('role','tablist');
const today=mk('div','aptoday','appg'),manage=mk('div','apmanage','appg');
const sheet=mk('div','apsheet','',`<div class="apshade"></div><div class="apscard" role="dialog" aria-modal="true"><div class="sheetgrip"></div><div class="apshead"><span></span><b></b><button type="button" class="apnb" data-close="1">${esc(t('Fertig','Done'))}</button></div><div class="apsbody"></div></div>`);
sheet.hidden=true;
const face=mk('div','apface'),hint=mk('div','aphint','',esc(t('Frag mich etwas, zum Beispiel: „Wie wird das Wetter morgen?“','Ask me something, for example: "What is the weather tomorrow?"')));
const mic=mk('div','apmic');
document.querySelector('main').before(bar);$('mbar').after(tabs);document.querySelector('main').append(today,manage);B.append(sheet);
const convo=document.querySelector('.convo');convo.prepend(face);face.appendChild(hint);convo.insertBefore(mic,document.querySelector('.composer'));
// the back label of the Ich window ("‹ Ich")
const mbl=mk('span','','apbl',esc(t('Ich','Me')));$('meback').appendChild(mbl);
// ---------------------------------------------------------------- moving the chat's parts into the app layout
const marks=new Map();
function moveIn(el,target,prepend){if(!el||marks.has(el))return;const m=document.createComment('apv');el.parentNode.insertBefore(m,el);marks.set(el,m);
  if(prepend)target.prepend(el);else target.appendChild(el)}
function moveOut(back){for(const [el,m] of marks){if(back&&m.parentNode)m.parentNode.insertBefore(el,m);m.remove()}marks.clear()}
// phone.js asks first where the face goes (see placeFace there)
window.apFace=()=>{if(!ON)return false;B.classList.remove('mempty');B.classList.toggle('apmsgs',$('chatlog').children.length>0);return true};
function enter(){ON=true;B.classList.add('appview');
  if(typeof MVIEW!=='undefined'){MVIEW='face';B.classList.remove('mempty')}
  // the face back to its place in the chat first (phone.js may have put it into the header), then into the app's spot
  const f=$('face');if(typeof homes!=='undefined'&&homes.has(f)){const h=homes.get(f);h.parentNode.insertBefore(f,h);h.remove();homes.delete(f)}
  moveIn(f,face,true);moveIn($('wakeind'),mic);moveIn($('roomothers'),mic);moveIn($('talk'),mic);moveIn($('chatstate'),mic);
  const ti=$('chattext');if(ti.dataset.ph==null)ti.dataset.ph=ti.placeholder;ti.placeholder=t('Oder schreiben …','Or type …');
  try{history.replaceState(Object.assign({},history.state||{},{ap:0}),'')}catch{}hd=0;pend=false;
  const sec=document.querySelector('main>section.on');TAB=!sec||sec.id==='chat'?'spark':'manage';
  apFace();render()}
function leave(stillPhone){const page=B.classList.contains('appage');ON=false;B.classList.remove('appview','appage','apmsgs','aptabs','apsub','aptab-docs');sheet.hidden=true;
  // on a wider screen phone.js has put its parts back already: only the face (never touched by phone.js here) moves
  const f=$('face'),fm=marks.get(f);if(fm){fm.parentNode.insertBefore(f,fm);fm.remove();marks.delete(f)}
  const ti=$('chattext');if(ti.dataset.ph!=null){ti.placeholder=ti.dataset.ph;delete ti.dataset.ph}
  moveOut(stillPhone);if(typeof placeFace==='function')placeFace();
  if(page)navBtn('chat').click()}
function apply(){const want=NAR.matches&&wanted();if(want&&!ON)enter();else if(!want&&ON)leave(NAR.matches)}
NAR.addEventListener('change',apply);
// ---------------------------------------------------------------- tabs
function visible(){const prof=typeof PROFILE!=='undefined'&&!!PROFILE,adm=typeof ADMIN!=='undefined'&&!!ADMIN;
  return {spark:true,today:prof,docs:prof&&typeof DOCS_ON!=='undefined'&&DOCS_ON,me:prof||adm,manage:adm}}
function showPage(pg){B.classList.add('appage');B.classList.remove('inchat');
  for(const p of [today,manage])p.classList.toggle('on',p===pg);window.scrollTo(0,0)}
function tab(k){if(!ON)return;closeSheet();const pm=$('profmodal').style.display==='grid';
  const prev=TAB;TAB=k;
  if(k!=='me'&&k!=='docs'&&pm&&window.closeProf)closeProf();
  if(k==='spark'){B.classList.remove('appage');navBtn('chat').click()}
  else if(k==='today'){showPage(today);renderToday()}
  else if(k==='manage'){showPage(manage);renderManage()}
  else if(k==='docs'){openMe('docbox')}
  else if(k==='me'){if(prev==='me'&&pm&&$('profmodal').classList.contains('sub'))$('meback').click();else openMe('list')}
  render()}
tabs.addEventListener('click',e=>{const b=e.target.closest('button[data-tab]');if(b)tab(b.dataset.tab)});
// other code opens a section (search, "Wer darf was", the start page): follow it
const _showSec=showSec;
showSec=function(s){_showSec(s);if(!ON)return;B.classList.remove('appage');for(const p of [today,manage])p.classList.remove('on');
  TAB=s==='chat'?'spark':'manage';render()};
// ---------------------------------------------------------------- the top bar
function manageNav(){const m=mainEl(),cw=document.querySelector('.cfgwrap'),sec=document.querySelector('main>section.on');
  if(sec&&sec.id==='cfg'&&cw.classList.contains('sub')&&!cw.classList.contains('featmode'))
    return {back:t('Einstellungen','Settings'),title:label(document.querySelector('#cfgnav button.on'))||((document.querySelector('#cfgnav button.on')||{}).textContent||''),act:()=>$('cfgback').click(),deep:2};
  if(m.classList.contains('hassub')&&!m.classList.contains('sublist'))
    return {back:$('subback').querySelector('span').textContent,title:label(document.querySelector('#subnav button.on')),act:()=>$('subback').click(),deep:2};
  return {back:t('Verwalten','Manage'),title:label(document.querySelector('nav button[data-s].on')),act:()=>tab('manage'),deep:1}}
function render(){if(!ON)return;if(manage.classList.contains('on')&&manageSig()!==mSig)renderManage();   // rights or Zustand arrived later
  const v=visible(),pm=$('profmodal').style.display==='grid',page=B.classList.contains('appage');
  if(pm&&TAB!=='me'&&TAB!=='docs')TAB='me';
  if(!pm&&(TAB==='me'||TAB==='docs')){const sec=document.querySelector('main>section.on');TAB=page?(manage.classList.contains('on')?'manage':'today'):!sec||sec.id==='chat'?'spark':'manage'}
  const shown=Object.keys(v).filter(k=>v[k]);B.classList.toggle('aptabs',shown.length>1);
  tabs.querySelectorAll('button').forEach(b=>{b.hidden=!v[b.dataset.tab];b.classList.toggle('on',b.dataset.tab===TAB);b.setAttribute('aria-selected',b.dataset.tab===TAB)});
  const hd2=$('hdot');tabs.querySelector('.apdot').hidden=!(hd2&&/\b(warn|bad)\b/.test(hd2.className));
  B.classList.toggle('aptab-docs',TAB==='docs');
  const back=$('apback'),lead=$('aplead'),trail=$('aptrail');let show=false,title='',bl='',lh='',th='';
  if(TAB==='spark'&&!pm&&!page){show=true;title='Spark';
    lh=`<button type="button" class="apib" data-ap="new" aria-label="${esc(t('Neues Gespräch','New conversation'))}">${SV(IC.new)}</button><button type="button" class="apib" data-ap="hist" aria-label="${esc(t('Verlauf','History'))}">${SV(IC.hist)}</button>`;
    th=isGuest()?`<button type="button" class="apib" data-ap="menu" aria-label="${esc(t('Menü','Menu'))}">${SV(IC.more)}</button>`
      :`<button type="button" class="apib" data-ap="set" aria-label="${esc(t('Gespräch einstellen','Conversation settings'))}">${SV(IC.set)}</button>`}
  else if(TAB==='manage'&&!page&&!pm){show=true;const n=manageNav();title=n.title;bl=n.back}
  bar.hidden=!show;$('aptitle').textContent=title;back.hidden=!bl;back.querySelector('span').textContent=bl;
  if(lead.dataset.h!==lh){lead.innerHTML=lh;lead.dataset.h=lh}if(trail.dataset.h!==th){trail.innerHTML=th;trail.dataset.h=th}
  B.classList.toggle('apsub',show&&!!bl);
  sync()}
bar.addEventListener('click',e=>{const b=e.target.closest('button');if(!b)return;
  if(b.id==='apback'){back();return}
  const a=b.dataset.ap;if(a==='new')$('chatnew').click();else if(a==='hist')openHist();else if(a==='set')openSet();else if(a==='menu')$('mmenu').click()});
// ---------------------------------------------------------------- one level back (top left, edge swipe, back gesture)
function depth(){if(!ON)return 0;let d=sheet.hidden&&$('msheet').style.display!=='grid'?0:1;const pm=$('profmodal');
  if(pm.style.display==='grid'&&TAB==='me'&&pm.classList.contains('sub')&&!pm.classList.contains('one'))d++;
  if(TAB==='manage'&&!B.classList.contains('appage')&&pm.style.display!=='grid')d+=manageNav().deep;
  return d}
function back(){if(!sheet.hidden){closeSheet();return true}
  if($('msheet').style.display==='grid'){$('msheet').style.display='none';return true}
  const pm=$('profmodal');if(pm.style.display==='grid'){if(TAB==='me'&&pm.classList.contains('sub')&&!pm.classList.contains('one')){$('meback').click();return true}return false}
  if(TAB==='manage'&&!B.classList.contains('appage')){manageNav().act();return true}
  return false}
// the browser history follows the depth, so Android's back gesture (and Safari's) goes one level up
function slide(cls){const pm=$('profmodal').style.display==='grid',el=pm?document.querySelector('#profmodal .mebody'):document.querySelector('main>section.on');
  if(!el||matchMedia('(prefers-reduced-motion: reduce)').matches)return;el.classList.remove('apin','apout');void el.offsetWidth;el.classList.add(cls);
  setTimeout(()=>el.classList.remove(cls),340)}
// hd is where the browser's history stands (state.ap). A step back is asynchronous: until its popstate has
// arrived (pend) nothing else moves the history, then sync catches up with taps made meanwhile. Without this
// fast taps could step back past the page's first entry.
let pend=false,popping=false;
function sync(){if(!ON||popping||pend)return;const d=depth();
  if(d>hd){slide('apin');while(hd<d)history.pushState({ap:++hd},'')}
  else if(d<hd){slide('apout');pend=true;history.go(d-hd)}}
addEventListener('popstate',e=>{if(!ON)return;const at=e.state&&typeof e.state.ap==='number'?e.state.ap:0;
  if(pend){pend=false;hd=at;sync();render();return}     // our own step back has arrived
  let n=6;popping=true;try{while(depth()>at&&n--&&back());}finally{popping=false}
  hd=at;const d=depth();if(d<at){pend=true;history.go(d-at)}render()});
// edge swipe from the left, only in the installed app (Safari itself already swipes back through the history)
let sx=null,sy=0;
document.addEventListener('touchstart',e=>{sx=null;if(!ON||!(STAND.matches||navigator.standalone))return;const p=e.touches[0];if(p.clientX<22){sx=p.clientX;sy=p.clientY}},{passive:true});
document.addEventListener('touchend',e=>{if(sx==null)return;const p=e.changedTouches[0];if(p.clientX-sx>70&&Math.abs(p.clientY-sy)<60&&depth()>0)history.back();sx=null},{passive:true});
// whatever a tap changed (a list row, "back", a sub page), the bar and the history follow
const later=()=>{if(dirty)return;dirty=true;requestAnimationFrame(()=>{dirty=false;render()})};
document.addEventListener('click',()=>setTimeout(later,30),true);
const mo=new MutationObserver(later);
mo.observe($('profmodal'),{attributes:true,attributeFilter:['style','class']});
mo.observe(document.querySelector('.cfgwrap'),{attributes:true,attributeFilter:['class']});
mo.observe(mainEl(),{attributes:true,attributeFilter:['class']});
mo.observe($('msheet'),{attributes:true,attributeFilter:['style']});
setInterval(()=>{if(ON&&!document.hidden)render()},5000);   // the dot on Verwalten (Zustand refreshes itself)
// ---------------------------------------------------------------- sheets from below (Verlauf)
function openSheet(title,html){sheet.querySelector('.apshead b').textContent=title;sheet.querySelector('.apsbody').innerHTML=html;sheet.hidden=false;render()}
function closeSheet(){if(sheet.hidden)return;sheet.hidden=true;if(ON)render()}
sheet.addEventListener('click',e=>{if(e.target.classList.contains('apshade')||e.target.closest('[data-close]')){closeSheet();return}
  const b=e.target.closest('[data-cid],[data-sa]');if(!b)return;closeSheet();
  if(b.dataset.sa==='new')$('chatnew').click();else if(b.dataset.sa==='find')$('convofind').click();else if(b.dataset.sa==='del')$('convodel').click();
  else{const s=$('convosel');s.value=b.dataset.cid;s.dispatchEvent(new Event('change'))}});
// pull the sheet down to close it
let gy=null;
sheet.addEventListener('touchstart',e=>{gy=e.target.closest('.apshead,.sheetgrip')?e.touches[0].clientY:null},{passive:true});
sheet.addEventListener('touchend',e=>{if(gy!=null&&e.changedTouches[0].clientY-gy>60)closeSheet();gy=null},{passive:true});
function day(ts){const d=new Date(ts),n=new Date(),y=new Date(n);y.setDate(n.getDate()-1);
  if(d.toDateString()===n.toDateString())return t('Heute','Today');if(d.toDateString()===y.toDateString())return t('Gestern','Yesterday');
  return d.toLocaleDateString(L==='en'?'en-GB':'de-DE',{weekday:'long',day:'numeric',month:'long'})}
function openHist(){let list=[];try{list=convos.load()}catch{}
  const hm=ts=>new Date(ts).toLocaleTimeString(L==='en'?'en-GB':'de-DE',{hour:'2-digit',minute:'2-digit'});
  let html=`<button type="button" class="apsearch" data-sa="find">${SV(IC.find)}<span>${esc(t('In Gesprächen suchen','Search conversations'))}</span></button>`+
    `<div class="apgrp"><div class="apgb"><button type="button" class="aprow" data-sa="new"><span class="apl apacc">${esc(t('Neues Gespräch','New conversation'))}</span></button></div></div>`;
  let cur=null,rows='';
  const flush=()=>{if(cur!==null&&rows)html+=`<div class="apgrp"><div class="apgh">${esc(cur)}</div><div class="apgb">${rows}</div></div>`;rows=''};
  for(const c of list.slice().sort((a,b)=>b.updated-a.updated)){const g=day(c.updated);if(g!==cur){flush();cur=g}
    const n=(c.msgs||[]).filter(m=>m.role==='user').length;
    rows+=`<button type="button" class="aprow${typeof chat!=='undefined'&&chat.cid===c.id?' on':''}" data-cid="${esc(c.id)}"><span class="apl">${esc(c.title||'…')}<small>${esc(hm(c.updated))} · ${n} ${esc(n===1?t('Frage','question'):t('Fragen','questions'))}</small></span><i class="apch"></i></button>`}
  flush();if(!list.length)html+=`<div class="apfoot">${esc(t('Noch keine früheren Gespräche.','No earlier conversations yet.'))}</div>`;
  if(typeof chat!=='undefined'&&chat.cid)html+=`<div class="apgrp"><div class="apgb"><button type="button" class="aprow" data-sa="del"><span class="apl apred">${esc(t('Dieses Gespräch löschen','Delete this conversation'))}</span></button></div></div>`;
  openSheet(t('Verlauf','History'),html)}
// ---------------------------------------------------------------- list helpers
const row=(attrs,l,v='',o={})=>`<button type="button" class="aprow" ${attrs}><span class="apl${o.cls?' '+o.cls:''}">${l}${o.sub?`<small>${o.sub}</small>`:''}</span>${v?`<span class="apv">${v}</span>`:''}${o.badge?`<em class="apbadge">${o.badge}</em>`:''}${o.nochev?'':'<i class="apch"></i>'}</button>`;
const grp=(head,rows)=>rows?`<div class="apgrp">${head?`<div class="apgh">${esc(head)}</div>`:''}<div class="apgb">${rows}</div></div>`:'';
const themeName=()=>{const th=document.documentElement.dataset.theme;return th==='dark'?t('Dunkel','Dark'):th==='light'?t('Hell','Light'):t('System','System')};
function lookRows(){return row('data-ax="lang"',esc(t('Sprache','Language')),esc(L==='en'?'English':'Deutsch'))+
  row('data-ax="theme"',esc(t('Hell / Dunkel','Light / dark')),esc(themeName()))+
  row('data-ax="desk"',esc(t('Am Rechner-Layout zeigen','Show the computer layout')),'',{sub:esc(t('Nur in diesem Browser','Only in this browser'))})}
function lookAct(a){if(a==='lang')$('langbtn').click();else if(a==='theme')$('themebtn').click();
  else if(a==='desk'||a==='app'){if(a==='desk'&&window.closeProf)closeProf();try{localStorage.setItem('appview',a==='desk'?'off':'on')}catch{}apply();
    if(a==='app'){if(window.closeProf)closeProf();tab('spark')}}
  else if(a==='login'){if(window.closeProf)closeProf();showLogin()}
  else if(a==='logout')$('logoutbtn').click();else if(a==='find')palOpen()}
// ---------------------------------------------------------------- Verwalten
let mSig='';
const manageSig=()=>['mon','feat','prof','cfg'].map(s=>{const b=navBtn(s);return b&&!b.hidden&&b.style.display!=='none'?1:0}).join('')+(($('ztitle')||{}).textContent||'')+(($('ztext')||{}).textContent||'');
function renderManage(){mSig=manageSig();const z=$('zhead'),lvl=(z&&z.dataset.lvl)||'',zt=(($('ztitle')||{}).textContent||'').trim(),zx=(($('ztext')||{}).textContent||'').trim();
  const can=s=>{const b=navBtn(s);return b&&!b.hidden&&b.style.display!=='none'};
  const ver=(document.querySelector('meta[name=spark-version]')||{}).content||'';
  const pages=[['mon',t('Zustand','Status')],['feat',t('Funktionen','Features')],['prof',t('Personen und Geräte','People and devices')],['cfg',t('Einstellungen','Settings')]]
    .filter(([s])=>can(s)).map(([s,l])=>row(`data-sec="${s}"`,esc(l),'')).join('')+
    (can('mon')?row('data-go="logs"',esc(t('Logs','Logs'))):'')+
    (can('cfg')?row('data-cfg="upd"',esc(t('Update und Sicherungen','Update and backups')),esc(ver)):'');
  manage.innerHTML=`<h1 class="aplt">${esc(t('Verwalten','Manage'))}</h1>`+
    `<button type="button" class="apsearch" data-ax="find">${SV(IC.find)}<span>${esc(t('Seite, Schalter oder Anleitung','Page, switch or guide'))}</span></button>`+
    (zt?`<button type="button" class="apstat" data-sec="mon" data-lvl="${esc(lvl)}"><b>${esc(zt)}</b>${zx?`<span>${esc(zx)}</span>`:''}</button>`:'')+
    grp('',pages)+grp(t('Darstellung','Appearance'),lookRows())+
    grp('',row('data-ax="logout"',esc(t('Admin abmelden','Sign out admin')),'',{cls:'apred',nochev:1}))}
manage.addEventListener('click',e=>{const b=e.target.closest('button');if(!b)return;
  if(b.dataset.sec){navBtn(b.dataset.sec).click();window.scrollTo(0,0)}else if(b.dataset.go)goSec(b.dataset.go);else if(b.dataset.cfg)goCfg(b.dataset.cfg);
  else if(b.dataset.ax){lookAct(b.dataset.ax);if(ON&&manage.classList.contains('on'))renderManage()}});
// ---------------------------------------------------------------- Ich: appearance, and "Spark verwalten" for a profile with an admin role
const _meTabs=meTabs;
meTabs=function(){const r=_meTabs(),p=$('ptabs');
  if(ON&&!GATE&&!(typeof ADMIN!=='undefined'&&ADMIN))
    p.insertAdjacentHTML('beforeend',`<div class="mgrp apx">${esc(t('Darstellung','Appearance'))}</div>`+
      [['lang',t('Sprache','Language'),L==='en'?'English':'Deutsch'],['theme',t('Hell / Dunkel','Light / dark'),themeName()],['desk',t('Am Rechner-Layout zeigen','Show the computer layout'),''],
       ...(B.classList.contains('mayadm')?[['login',t('Spark verwalten','Manage the Spark'),'']]:[])].map(([a,l,v])=>`<button type="button" class="apx" data-apx="${a}">${esc(l)}<small class="apxv">${esc(v)}</small></button>`).join(''));
  // the way back from "Am Rechner-Layout zeigen"
  if(!ON&&NAR.matches&&!GATE)p.insertAdjacentHTML('beforeend',`<button type="button" class="apon" data-apx="app">${esc(t('Wie die App anzeigen','Show like the app'))}</button>`);
  return r};
const appBtn=mk('button','miapp','mi',esc(t('Wie die App anzeigen','Show like the app')));appBtn.type='button';
$('milang').parentNode.before(appBtn);appBtn.onclick=()=>{$('msheet').style.display='none';lookAct('app')};
$('ptabs').addEventListener('click',e=>{const b=e.target.closest('button[data-apx]');if(!b)return;e.stopPropagation();lookAct(b.dataset.apx);
  if(ON&&b.dataset.apx==='theme')b.querySelector('small').textContent=themeName()});
$('mmenu').addEventListener('click',()=>{appBtn.hidden=ON||!NAR.matches});
// ---------------------------------------------------------------- Heute
// Heute: the same cards and sentences as Ich → Heute (today.js, /api/profile/today), here as a tab of its own
const _meToday=meToday;
meToday=async function(){if(!ON)return _meToday()};      // in the app view Heute is not on top of Ich
async function renderToday(){const loc=L==='en'?'en-GB':'de-DE',now=new Date();
  const su=typeof SETUP!=='undefined'&&SETUP&&SETUP.open>0?SETUP:null;
  const head=`<h1 class="aplt">${esc(t('Heute','Today'))}</h1><div class="apdate">${esc(now.toLocaleDateString(loc,{weekday:'long',day:'numeric',month:'long'}))}</div>`+
    (su?`<div class="apcards"><button type="button" class="apcard wide" data-me="gobox"><span class="apk">${esc(t('Einrichten','Setup'))}</span><b>${esc(`${su.done} ${t('von','of')} ${su.total} ${t('erledigt','done')}`)}</b>`+
      `<span class="aps">${esc(t('Antippen, um weiterzumachen','Tap to continue'))}</span><i class="aprog"><i data-w="${Math.round(su.total?su.done*100/su.total:0)}"></i></i></button></div>`:'');
  if(!ME_ITEMS.length)meTabs();                           // the cards only open pages the Ich list has
  await _meToday();                                       // builds #metoday (in the Ich window), then it moves here
  if(!today.classList.contains('on'))return;
  const box=$('metoday');today.innerHTML=head;if(box)today.appendChild(box);
  today.querySelectorAll('.aprog>i[data-w]').forEach(i=>i.style.width=i.dataset.w+'%')}   // no style attribute (strict CSP)
// a card of today.js names its Ich page in meLast (and calls ptab); the Ich window is closed here, so open it
let tdPrev='';
today.addEventListener('click',e=>{if(e.target.closest('.tcard')){tdPrev=meLast;meLast=''}},true);
today.addEventListener('click',e=>{const b=e.target.closest('button');if(!b)return;
  if(b.dataset.me){TAB='me';openMe(b.dataset.me);return}
  if(b.classList.contains('tcard')){if(meLast){TAB='me';openMe(meLast)}else meLast=tdPrev}});
apply();
return {apply,tab,back,depth,on:()=>ON,current:()=>TAB}})();
