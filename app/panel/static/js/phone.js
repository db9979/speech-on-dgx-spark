// Phone layout (< 760 px): messenger-style chat, face view and menu sheet.
// ---------------------------------------------------------------- phone layout
// Below 760 px the conversation is laid out like a messenger: a slim top bar (small face, state,
// profile, menu), the history in the middle and a fixed bar at the bottom (text field, mic). The
// elements are moved, not copied, so all handlers keep working; they move back on wider screens.
const MOBILE=matchMedia('(max-width:760px)');
const mtog=document.createElement('div');mtog.className='mtoggles';
const MOVES=[[()=>$('chatstate'),()=>$('mslot').nextElementSibling,'after'],[()=>$('profbtn'),()=>$('mmenu'),'before'],
  [()=>$('chatwake').closest('label'),()=>$('msetwake'),'in'],[()=>document.querySelector('.opts.toggles'),()=>mtog,'in'],[()=>$('chattiming'),()=>mtog,'in'],[()=>$('remlist'),()=>mtog,'in'],
  [()=>$('talk'),()=>document.querySelector('.composer'),'in'],[()=>$('convosel'),()=>$('mconvo'),'row'],[()=>$('convofind'),()=>$('mconvo'),'row'],[()=>$('convodel'),()=>$('mconvo'),'row']];
const homes=new Map();
// Phones open on the face alone (view "face"); "Verlauf" switches to the messenger view ("log").
let MVIEW='face';try{MVIEW=localStorage.getItem('mview')==='log'?'log':'face'}catch{}
function setView(v){MVIEW=v;try{localStorage.setItem('mview',v)}catch{}placeFace();if(v==='log')$('chatlog').scrollTop=1e9}
$('mlog').onclick=()=>setView('log');$('mback').onclick=()=>setView('face');$('mset').onclick=()=>openSet();
function placeFace(){if(window.apFace&&apFace())return;   // the app view (appview.js) has its own place for the face
  const big=!MOBILE.matches||MVIEW==='face';
  document.body.classList.toggle('mempty',MOBILE.matches&&big);
  const f=$('face'),home=homes.get(f);
  if(MOBILE.matches&&!big){if(!home){const m=document.createComment('face');f.parentNode.insertBefore(m,f);homes.set(f,m)}$('mslot').appendChild(f)}
  else if(home){home.parentNode.insertBefore(f,home);home.remove();homes.delete(f)}}
function layout(){const m=MOBILE.matches;
  if(m&&!mtog.parentNode){const conv=document.querySelector('.convo');conv.insertBefore(mtog,document.querySelector('.composer'));
    let row=$('mconvo').querySelector('.rowin');if(!row){row=document.createElement('div');row.className='rowin';$('mconvo').appendChild(row)}}
  for(const [el,target,how] of MOVES){const e=el(),tg=target();if(!e)continue;
    if(m&&!homes.has(e)){const mark=document.createComment('home');e.parentNode.insertBefore(mark,e);homes.set(e,mark);
      if(how==='after')tg.after(e);else if(how==='before')tg.before(e);else if(how==='row')tg.querySelector('.rowin').appendChild(e);else tg.appendChild(e)}
    else if(!m&&homes.has(e)){const mark=homes.get(e);mark.parentNode.insertBefore(e,mark);mark.remove();homes.delete(e)}}
  if(!m&&mtog.parentNode)mtog.remove();placeFace()}
new MutationObserver(placeFace).observe($('chatlog'),{childList:true});
MOBILE.addEventListener('change',layout);
$('chattext').addEventListener('input',()=>document.querySelector('.composer').classList.toggle('typing',!!$('chattext').value.trim()));
$('chatsend').addEventListener('click',()=>setTimeout(()=>document.querySelector('.composer').classList.toggle('typing',!!$('chattext').value.trim()),0));
$('chattext').addEventListener('keydown',e=>{if(e.key==='Enter')setTimeout(()=>document.querySelector('.composer').classList.remove('typing'),0)});
// menu sheet: conversation actions, admin pages, language, theme, login
const closeSheet=()=>{$('msheet').style.display='none'};
$('msheet').onclick=e=>{if(e.target===$('msheet'))closeSheet()};
$('mmenu').onclick=()=>{const inchat=document.body.classList.contains('inchat');$('mchatitems').style.display=inchat?'':'none';
  $('madmin').innerHTML=ADMIN?[...document.querySelectorAll('nav button[data-s]:not([hidden])')].map(b=>`<button class="mi${b.classList.contains('on')?' on':''}" data-s="${b.dataset.s}">${esc([...b.childNodes].filter(n=>n.nodeType===3).map(n=>n.textContent).join('').trim())}</button>`).join(''):'';
  $('madmin').querySelectorAll('button').forEach(x=>x.onclick=()=>{closeSheet();document.querySelector(`nav button[data-s=${x.dataset.s}]`).click();window.scrollTo(0,0)});
  $('mifind').style.display=ADMIN||PROFILE?'':'none';$('milang').textContent=$('langbtn').textContent;$('milogin').style.display=!ADMIN&&document.body.classList.contains('mayadm')?'':'none';$('milogout').style.display=ADMIN&&$('logoutbtn').style.display!=='none'?'':'none';
  $('msheet').style.display='grid'};
$('minew').onclick=()=>{closeSheet();$('chatnew').click()};$('miset').onclick=()=>{closeSheet();openSet()};
$('milang').onclick=()=>$('langbtn').click();$('mifind').onclick=()=>{closeSheet();palOpen()};$('mitheme').onclick=()=>$('themebtn').click();
$('milogin').onclick=()=>{closeSheet();showLogin()};$('milogout').onclick=()=>$('logoutbtn').click();
$('convosel').addEventListener('change',()=>{if(MOBILE.matches)closeSheet()});
layout();
// ---------------------------------------------------------------- phone layout, all pages
// header height for the sticky bars below it; the voice button steps aside while the keyboard is up
const hdrH=()=>document.documentElement.style.setProperty('--hdrh',document.querySelector('header').offsetHeight+'px');
addEventListener('resize',hdrH);hdrH();
const typingEl=e=>e&&e.matches&&e.matches('input:not([type=checkbox]):not([type=range]):not([type=file]),textarea,select');
document.addEventListener('focusin',e=>{if(typingEl(e.target))document.body.classList.add('kbd')});
document.addEventListener('focusout',()=>setTimeout(()=>{if(!typingEl(document.activeElement))document.body.classList.remove('kbd')},50));
// wide tables become one block per row on phones; each cell shows its column name (data-label)
let tblTimer=null;
const labelTables=()=>{for(const tb of document.querySelectorAll('table')){const hs=[...tb.querySelectorAll('thead th')].map(h=>h.textContent.trim());if(!hs.length)continue;
  tb.classList.add('stack');for(const tr of tb.querySelectorAll('tbody tr'))[...tr.children].forEach((td,i)=>{if(hs[i]&&td.dataset.label!==hs[i])td.dataset.label=hs[i]})}};
new MutationObserver(()=>{clearTimeout(tblTimer);tblTimer=setTimeout(labelTables,60)}).observe(document.querySelector('main'),{childList:true,subtree:true});
labelTables();
// ---------------------------------------------------------------- phone bar (admin)
// Assistent, Ich, Zustand and "Verwalten" (the menu sheet with all pages); gone while the keyboard is up.
$('mbar').querySelectorAll('button').forEach(b=>b.onclick=()=>{const m=b.dataset.m;
  if(m==='me'){openMe(PHONE.matches?'list':meLast);return}
  if(m==='more'){$('mmenu').click();return}
  document.querySelector(`nav button[data-s=${m}]`).click();if(m==='chat')setView('face');window.scrollTo(0,0)});
