// Funktionen → „Wer darf was“ (plan „Vereinheitlichen“ Phase 3, V01.0.269; plan „Freigabe vereinfachen“,
// Dominik 2026-10-13): every function as a row, columns Spark (the admin's switch) and each profile. What the Spark
// allows works at once for every profile; a profile cell only blocks it for that one profile (✓ may use, ⊘ blocked
// by the admin, a dash when the Spark is off or it is blocked through a function it builds on). Guests never get a
// function (one line below). Filter: Alle / An / Neu, noch nie an / Braucht dich. Phones get a list with the Spark
// switch and one chip per profile. Data from /api/admin/features (features.py), switching the Spark over
// /api/admin/switches and blocking a profile over /api/admin/features/<key>/profiles/<id> ({on:false} blocks).
let WHO=null,whoF='all',WHO_LAST=null,WHO_JUMP=0;   // WHO_LAST: the row the last name jumped to; WHO_JUMP: when, until the user moves
try{whoF=localStorage.getItem('whofilter')||'all'}catch{}
const WHOF=[['all',t('Alle','All')],['on',t('An','On')],['new',t('Neu, noch nie an','New, never on')],['need',t('Braucht dich','Needs you')]];
const whoName=f=>f.name[L==='en'?1:0];
const whoItem=f=>document.querySelector(`#pane-feat .fitem[data-sw="chat.${f.switch}"]`);
const whoNeed=f=>{const it=whoItem(f);return !!(f.spark&&it&&typeof featNeed==='function'&&featNeed(it))};
// indented below the function it builds on, when that one sits in the same group
const whoSub=f=>!!(f.parent&&WHO.features.some(x=>x.key===f.parent&&x.group===f.group));
function whoKeep(f){return whoF==='on'?f.spark:whoF==='new'?!f.seen:whoF==='need'?whoNeed(f):true}
async function loadWho(){const box=$('whobox');if(!box)return;
  // the settings and the switches side by side (plan seiten-laden.md), drawn when both are there
  const cfg=typeof loadCfg==='function'&&!document.body.classList.contains('mgr')?loadCfg().catch(()=>{}):null;
  try{WHO=await (await api('/api/admin/features')).json()}catch(e){await cfg;box.textContent=e.message;return}
  await cfg;if(typeof needsSet==='function')needsSet(WHO)
  drawWho()}
function whoGuest(){return t('Gäste bekommen nur Fragen und Antworten, keine Funktion.','Guests only get questions and answers, no function.')}   // never a function (Dominik 2026-10-13)
function whoBox(on,can,label,act){const b=document.createElement('button');b.type='button';b.className='wbox'+(on?' on':'')+(can?'':' no');
  b.setAttribute('aria-pressed',on?'true':'false');b.setAttribute('aria-label',label);b.title=label;b.disabled=!can;if(can&&act)b.onclick=act;return b}
// with what it builds on (needs.js): asks to switch the missing ones on too, and what goes off with it
async function whoSpark(f,on){try{const isOn=sw=>!!(WHO.states&&WHO.states[sw]);
    if(typeof needsSpark!=='function'||await needsSpark(f,on,isOn))await api('/api/admin/switches',xjson('PUT',{key:f.switch,on}));
    await loadWho();
    if(typeof loadCfg==='function'&&!document.body.classList.contains('mgr'))loadCfg()}catch(e){if(!LEAVING)alert(e.message)}}
async function whoSet(f,uid,on){try{
    await api(`/api/admin/features/${encodeURIComponent(f.key)}/profiles/${encodeURIComponent(uid)}`,xjson('PUT',{on}));
    f.cells[uid]=on;drawWho()}catch(e){alert(e.message)}}
// The name jumps to the function under Funktionen (V01.0.398): to its own switch row, also when it is a switch
// inside another function's item; when its row is hidden because the switch it builds on is off, to that switch
// (like the search). Waits for the settings to be loaded, opens what is folded and marks the row.
function whoRow(f){const el=$('chat.'+f.switch);if(!el)return null;let row=el.closest('.setrow')||el.closest('.fitem')||el;
  for(let i=0;i<5;i++){const dep=row.closest('[data-show]');if(!dep||dep.style.display!=='none')break;
    const sw=$(dep.dataset.show);if(!sw)break;row=sw.closest('.setrow')||sw.closest('.fitem')||sw}
  return row}
async function whoOpen(f){const me=whoOpen.n=(whoOpen.n||0)+1;goSec('feat');if(typeof loadCfg==='function')try{await loadCfg()}catch{}
  // a settings load started elsewhere (Wer darf was loads them too) may still be drawing the rows: wait for them,
  // on a busy machine up to 20 s; a newer jump wins
  let row=whoRow(f);for(let i=0;!row&&i<80&&me===whoOpen.n;i++){await new Promise(r=>setTimeout(r,250));row=whoRow(f)}
  if(me!==whoOpen.n)return;
  WHO_LAST=row;if(!row)return;whoJumped();const it=row.closest('#pane-feat .fitem');
  if(it&&typeof featShow==='function')featShow(it);
  for(let d=row.parentElement;d&&d!==document.body;d=d.parentElement)if(d.tagName==='DETAILS'&&!d.open)d.open=true;
  requestAnimationFrame(()=>{if(typeof sFlash==='function')sFlash(row);else row.scrollIntoView({block:'center'})})}
// boxes that fill in later (the profile chips of a function, slow with many profiles) push the row away: they scroll
// back to it until the user scrolls, taps or types himself, at most 15 s
function whoJumped(){WHO_JUMP=Date.now();clearInterval(whoJumped.t);
  const stop=()=>{WHO_JUMP=0;clearInterval(whoJumped.t);for(const e of WHO_STOP)removeEventListener(e,stop,true)};
  for(const e of WHO_STOP)addEventListener(e,stop,{capture:true,passive:true});
  // anything drawn later above the row (not only the chips) moves it: bring it back while it is out of view
  whoJumped.t=setInterval(()=>{if(!whoKeepJump()){clearInterval(whoJumped.t);return}
    const r=WHO_LAST.getBoundingClientRect();if(r.height&&(r.top<0||r.bottom>innerHeight))WHO_LAST.scrollIntoView({block:'center'})},400)}
const WHO_STOP=['wheel','touchstart','keydown','pointerdown'];
function whoKeepJump(){return !!(WHO_JUMP&&Date.now()-WHO_JUMP<15000&&WHO_LAST&&WHO_LAST.isConnected)}
// the function this one builds on that is blocked for the profile (its name for the title of the dash)
function whoVia(f,uid){let k=f.parent;for(let i=0;k&&i<10;i++){const x=WHO.features.find(y=>y.key===k);if(!x)break;
    if(x.cells&&x.cells[uid]===false)return whoName(x);k=x.parent}return ''}
// a profile's cell: ✓ may use it (tap blocks it), ⊘ blocked by the admin (tap allows again), a dash when it cannot
// be used anyway (Spark off, or blocked through a function it builds on). The dash is a disabled button, so the
// table and the chips keep one shape and its label says why.
function whoCell(f,p){const n=p.name,b=document.createElement('button');b.type='button';b.className='wbox wcell';
  const off=!f.spark,inh=!off&&!!(f.inherited&&f.inherited[p.id]),on=!!f.cells[p.id];
  let label;
  if(f.blockable===false){b.disabled=true;b.textContent='✓';b.classList.add('woff');b.setAttribute('aria-pressed','true');
    label=t('immer erlaubt, nicht sperrbar','always allowed, cannot be blocked')}
  else if(off||inh){b.disabled=true;b.textContent='–';b.classList.add('woff');b.setAttribute('aria-pressed','false');
    label=off?t('Spark aus','Spark off'):(()=>{const v=whoVia(f,p.id);return v?t(`gesperrt über „${v}“`,`blocked through "${v}"`):t('gesperrt über eine Vorstufe','blocked through a function it builds on')})()}
  else{b.textContent=on?'✓':'⊘';if(on)b.classList.add('on');else b.classList.add('wblk');b.setAttribute('aria-pressed',on?'true':'false');
    label=on?t('darf es, antippen sperrt','may use it, tap to block'):t('vom Admin gesperrt, antippen erlaubt wieder','blocked by the admin, tap to allow again');
    b.onclick=()=>whoSet(f,p.id,!on)}
  b.setAttribute('aria-label',`${whoName(f)} – ${n}: ${label}`);b.title=label;b.dataset.uid=p.id;return b}
function drawWho(){const box=$('whobox');if(!box||!WHO)return;box.textContent='';
  const bar=document.createElement('div');bar.className='ffilt wfilt';
  for(const [k,l] of WHOF){const b=document.createElement('button');b.type='button';b.dataset.f=k;b.className=k===whoF?'on':'';
    b.textContent=l+' ('+WHO.features.filter(f=>k==='all'||(k==='on'?f.spark:k==='new'?!f.seen:whoNeed(f))).length+')';
    b.onclick=()=>{whoF=k;try{localStorage.setItem('whofilter',k)}catch{}drawWho()};bar.appendChild(b)}
  box.appendChild(bar);
  const rows=WHO.features.filter(whoKeep);
  if(!rows.length){const p=document.createElement('p');p.className='mut';p.textContent=t('Keine Funktion in dieser Auswahl.','No function in this view.');box.appendChild(p);return}
  const mgr=document.body.classList.contains('mgr');
  if(NARROW()){for(const g of WHO.groups){const fs=rows.filter(f=>f.group===g.key);if(!fs.length)continue;
      const h=document.createElement('h3');h.className='sec';h.textContent=g.name[L==='en'?1:0];box.appendChild(h);
      for(const f of fs){const r=document.createElement('div');r.className='wcard'+(whoSub(f)?' sub':'');
        const top=document.createElement('div');top.className='wtop';const nm=document.createElement('button');nm.type='button';nm.className='wname';nm.textContent=whoName(f);
        if(!mgr)nm.onclick=()=>whoOpen(f);
        top.append(nm,whoBox(f.own,f.switchable,`${whoName(f)} – Spark: ${f.own?t('an','on'):t('aus','off')}`,()=>whoSpark(f,!f.own)));r.appendChild(top);
        const chips=document.createElement('div');chips.className='wchips';
        for(const p of WHO.profiles){const c=whoCell(f,p);c.classList.add('chip');c.textContent=c.textContent+' '+p.name;chips.appendChild(c)}
        if(!WHO.profiles.length){const s=document.createElement('span');s.className='mut';s.textContent=f.spark?t('Gilt für alle Profile','Applies to every profile'):t('Spark aus','Spark off');chips.appendChild(s)}
        r.appendChild(chips);box.appendChild(r)}}
    for(const x of whoNotes()){const n=document.createElement('p');n.className='mut wnote';n.textContent=x;box.appendChild(n)}
    return}
  const wrap=document.createElement('div');wrap.className='whowrap';const tb=document.createElement('table');tb.className='who';
  const hr=document.createElement('tr');const th=x=>{const c=document.createElement('th');c.textContent=x;hr.appendChild(c);return c};
  th(t('Funktion','Function'));th('Spark');for(const p of WHO.profiles){const c=th(p.name);if(p.role)c.title=t('Admin-Rechte','Admin rights')}
  const head=document.createElement('thead');head.appendChild(hr);tb.appendChild(head);const body=document.createElement('tbody');
  for(const g of WHO.groups){const fs=rows.filter(f=>f.group===g.key);if(!fs.length)continue;
    const gr=document.createElement('tr');gr.className='wgrp';const gc=document.createElement('td');gc.colSpan=WHO.profiles.length+2;gc.textContent=g.name[L==='en'?1:0];gr.appendChild(gc);body.appendChild(gr);
    for(const f of fs){const tr=document.createElement('tr');if(whoSub(f))tr.className='sub';
      const nc=document.createElement('td');const nm=document.createElement('button');nm.type='button';nm.className='wname';nm.textContent=whoName(f);if(!mgr)nm.onclick=()=>whoOpen(f);
      nc.appendChild(nm);if(!f.seen){const n=document.createElement('span');n.className='wnew';n.textContent=t('neu','new');nc.appendChild(n)}
      if(whoNeed(f)){const n=document.createElement('span');n.className='wneed';n.textContent=t('braucht dich','needs you');nc.appendChild(n)}
      tr.appendChild(nc);
      const sc=document.createElement('td');sc.appendChild(whoBox(f.own,f.switchable,`${whoName(f)} – Spark: ${f.own?t('an','on'):t('aus','off')}`,()=>whoSpark(f,!f.own)));tr.appendChild(sc);
      for(const p of WHO.profiles){const c=document.createElement('td');c.appendChild(whoCell(f,p));tr.appendChild(c)}
      body.appendChild(tr)}}
  tb.appendChild(body);wrap.appendChild(tb);box.appendChild(wrap);
  for(const x of whoNotes()){const n=document.createElement('p');n.className='mut wnote';n.textContent=x;box.appendChild(n)}}
// the lines below the table and the list
function whoNotes(){return [t(`Was im Spark an ist, gilt sofort für alle Profile. ✓ darf es, antippen sperrt es für dieses Profil; ⊘ hat der Admin gesperrt, antippen erlaubt es wieder. Ein Strich: der Spark ist aus oder es ist über eine Vorstufe gesperrt. Das Profil kann eine Sperre nicht selbst aufheben.`,
    `What is switched on in the Spark works at once for every profile. ✓ may use it, tap to block it for this profile; ⊘ is blocked by the admin, tap to allow it again. A dash: the Spark is off or it is blocked through a function it builds on. The profile cannot lift a block itself.`),
  whoGuest()]}
window.loadWho=loadWho;
if($('featwho'))$('featwho').onclick=()=>goSec('who');
