// Assistent layout: phones (< 760 px) like a messenger, computers as one card that starts with the face.
// ---------------------------------------------------------------- phone and computer layout
// Below 760 px the conversation is laid out like a messenger: a slim top bar (small face, state,
// profile, menu), the history in the middle and a fixed bar at the bottom (text field, mic). The
// elements are moved, not copied, so all handlers keep working; they move back on wider screens.
const MOBILE=matchMedia('(max-width:760px)');
const mtog=document.createElement('div');mtog.className='mtoggles';
const MOVES=[[()=>$('chatstate'),()=>$('mslot').nextElementSibling,'after'],[()=>$('profbtn'),()=>$('mmenu'),'before'],
  [()=>$('chatwake').closest('label'),()=>$('msetwake'),'in'],[()=>document.querySelector('.opts.toggles'),()=>mtog,'in'],[()=>$('chattiming'),()=>mtog,'in'],[()=>$('remlist'),()=>mtog,'in'],
  [()=>$('talk'),()=>document.querySelector('.composer'),'in'],[()=>$('cvlbtn'),()=>$('mconvo'),'row'],[()=>$('convodel'),()=>$('mconvo'),'row']];
// Computers (Assistent-Seite entschlacken, Vorschlag 3 „Sprechen zuerst“, Dominik 2026-11-16): one card instead of
// face column, list and conversation. The microphone sits in the text field (a stop while an answer runs), „Neu“ in
// the head, the switches, „Gespräch einstellen“ and „Löschen“ in its ⋯ menu, times and reminders above the text field;
// face, state and „lauscht“ stand big in the start view while the conversation is empty and small in the head after
const DMOVES=[[()=>$('talk'),()=>document.querySelector('.composer'),'in'],[()=>$('chatnew'),()=>$('dzahl').parentNode,'before'],
  [()=>document.querySelector('.opts.toggles'),()=>$('dpop'),'in'],[()=>$('convodel'),()=>$('dpop'),'in'],
  [()=>$('chattiming'),()=>$('dfoot'),'in'],[()=>$('remlist'),()=>$('dfoot'),'in']];
const homes=new Map();
function park(e,tg,how){if(!e||!tg||homes.has(e))return;const mark=document.createComment('home');e.parentNode.insertBefore(mark,e);homes.set(e,mark);
  if(how==='after')tg.after(e);else if(how==='before')tg.before(e);else if(how==='row')tg.querySelector('.rowin').appendChild(e);else tg.appendChild(e)}
function unpark(e){const mark=e&&homes.get(e);if(!mark)return;mark.parentNode.insertBefore(e,mark);mark.remove();homes.delete(e)}
// Phones open on the face alone (view "face"); "Verlauf" switches to the messenger view ("log").
let MVIEW='face';try{MVIEW=localStorage.getItem('mview')==='log'?'log':'face'}catch{}
function setView(v){MVIEW=v;try{localStorage.setItem('mview',v)}catch{}placeFace();if(v==='log')$('chatlog').scrollTop=1e9}
$('mlog').onclick=()=>setView('log');$('mback').onclick=()=>setView('face');$('mset').onclick=()=>openSet();
function placeFace(){if(window.apFace&&apFace())return;   // the app view (appview.js) has its own place for the face
  const f=$('face'),B=document.body;
  if(!MOBILE.matches){const msgs=!!$('chatlog').querySelector('.msg');B.classList.remove('mempty');B.classList.toggle('dempty',!msgs);
    if(homes.has(f)&&f.parentNode!==$('dslot'))unpark(f);   // from the phone's bar
    if(msgs){park(f,$('dslot'),'in');park($('chatstate'),$('convotitle'),'after');park($('wakeind'),$('chatstate'),'after');park($('roomothers'),$('wakeind'),'after')}
    else [f,$('chatstate'),$('wakeind'),$('roomothers')].forEach(unpark);
    return}
  B.classList.remove('dempty');
  const big=MVIEW==='face';
  B.classList.toggle('mempty',big);
  if(!big){park(f,$('mslot'),'in')}else unpark(f)}
let MODE='';
function layout(){const m=MOBILE.matches?'m':'d';
  if(MODE&&MODE!==m)for(const e of [...homes.keys()])if(e!==$('face'))unpark(e);
  MODE=m;
  if(m==='m'&&!mtog.parentNode){const conv=document.querySelector('.convo');conv.insertBefore(mtog,document.querySelector('.composer'));
    let row=$('mconvo').querySelector('.rowin');if(!row){row=document.createElement('div');row.className='rowin';$('mconvo').appendChild(row)}}
  if(m==='d'&&mtog.parentNode)mtog.remove();
  for(const [el,target,how] of m==='m'?MOVES:DMOVES)park(el(),target(),how);
  placeFace()}
new MutationObserver(placeFace).observe($('chatlog'),{childList:true});
// the two small menus of the computer's head: ⋯ (switches, Gespräch einstellen, Löschen) and „● N“ (what needs one
// under Offen, the list of offen.js vgStrip); one open at a time, a click elsewhere, Escape or a button in it closes
const DPOPS=[['dmore','dpop'],['dzahl','dsoffen']];
function dPop(which){for(const [b,p] of DPOPS){const open=b===which&&$(p).hidden;$(p).hidden=!open;$(b).setAttribute('aria-expanded',String(open))}}
for(const [b,p] of DPOPS){$(b).addEventListener('click',e=>{e.stopPropagation();dPop(b)});
  $(p).addEventListener('click',e=>{if(e.target.closest('button'))setTimeout(()=>dPop(''),0)})}
document.addEventListener('click',e=>{if(!e.target.closest('.dmenu,.dzmenu'))dPop('')});
document.addEventListener('keydown',e=>{if(e.key==='Escape'&&DPOPS.some(([,p])=>!$(p).hidden))dPop('')});
MOBILE.addEventListener('change',layout);
// the class only when it changes (empty ↔ text), not a class write in every keystroke; "hastext", not "typing":
// .typing::after are the answer's moving dots, which redrew the whole page sixty times a second while text stood here
{const box=document.querySelector('.composer'),ti=$('chattext');let on=null;
 const sync=v=>{if(v!==on){on=v;box.classList.toggle('hastext',v)}};
 ti.addEventListener('input',()=>sync(!!ti.value.trim()));
 $('chatsend').addEventListener('click',()=>setTimeout(()=>sync(!!ti.value.trim()),0))}   // Enter sendet über feld.js mit einem Klick auf chatsend
// menu sheet: conversation actions, admin pages, language, theme, login
const closeSheet=()=>{$('msheet').style.display='none'};
$('msheet').onclick=e=>{if(e.target===$('msheet'))closeSheet()};
$('mmenu').onclick=()=>{const inchat=document.body.classList.contains('inchat');$('mchatitems').style.display=inchat?'':'none';
  // the pages of the menu: an admin all of them, a profile its own pages above „Ich“ (Kalender, E-Mail …), so a phone in
  // the computer layout reaches every page in portrait too (Dominik 2026-11-14)
  const me=$('navme'),mine=b=>!!(me&&b.compareDocumentPosition(me)&Node.DOCUMENT_POSITION_FOLLOWING);
  $('madmin').innerHTML=ADMIN||PROFILE?[...document.querySelectorAll('nav button[data-s]:not([hidden])')].filter(b=>ADMIN||mine(b)).map(b=>`<button class="mi${b.classList.contains('on')?' on':''}" data-s="${b.dataset.s}">${esc([...b.childNodes].filter(n=>n.nodeType===3).map(n=>n.textContent).join('').trim())}</button>`).join(''):'';
  $('madmin').querySelectorAll('button').forEach(x=>x.onclick=()=>{closeSheet();document.querySelector(`nav button[data-s=${x.dataset.s}]`).click();window.scrollTo(0,0)});
  $('mifind').style.display=ADMIN||PROFILE?'':'none';$('milang').textContent=$('langbtn').textContent;$('milogout').style.display=ADMIN&&$('logoutbtn').style.display!=='none'?'':'none';
  $('msheet').style.display='grid'};
$('minew').onclick=()=>{closeSheet();$('chatnew').click()};$('miset').onclick=()=>{closeSheet();openSet()};
$('milang').onclick=()=>$('langbtn').click();$('mifind').onclick=()=>{closeSheet();palOpen()};$('mitheme').onclick=()=>$('themebtn').click();
$('milogout').onclick=()=>$('logoutbtn').click();
layout();
// ---------------------------------------------------------------- phone layout, all pages
// header height for the sticky bars below it; the voice button steps aside while the keyboard is up
const hdrH=()=>document.documentElement.style.setProperty('--hdrh',document.querySelector('header').offsetHeight+'px');
addEventListener('resize',hdrH);hdrH();
// the conversation's column is as high as what one really sees (Web-App aufräumen 4a, Dominik 2026-11-16): iOS 26 Safari
// counts the room under its floating bar into 100dvh, so the tab bar at the bottom was cut off; the smaller of the
// window's and the visible part's height (not while zoomed), 100dvh stays the fallback in app.css
let appHv=0;
const appH=()=>{const v=window.visualViewport,h=Math.round(v&&v.scale<1.05?Math.min(innerHeight,v.height):innerHeight);
  if(h>200&&h!==appHv){appHv=h;document.documentElement.style.setProperty('--apph',h+'px')}};
addEventListener('resize',appH);if(window.visualViewport)visualViewport.addEventListener('resize',appH);appH();
// the side menu shows only symbols between 761 and 1100 px (app.css, Web-App aufräumen 6a): each entry names itself in
// its title, read from its words when the pointer comes (so it follows a change of language)
document.querySelector('header nav').addEventListener('pointerover',e=>{const b=e.target.closest('button');if(!b||b.classList.contains('navfind'))return;
  const n=[...b.childNodes].filter(x=>x.nodeType===3).map(x=>x.textContent).join('').trim();if(n&&b.title!==n)b.title=n});
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
