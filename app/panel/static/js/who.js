// Funktionen → „Wer darf was“ (plan „Vereinheitlichen“ Phase 3, V01.0.269): every function as a row, columns
// Spark (the admin's switch), each profile (its own switch) and Gäste. A box switches only there; a dashed box
// cannot be used (Spark off, or no own switch). Filter: Alle / An / Neu, noch nie an / Braucht dich. Phones get a
// list with the Spark switch and one chip per profile. Data from /api/admin/features (features.py), switching
// the Spark over /api/admin/switches and a profile over /api/admin/features/<key>/profiles/<id>.
let WHO=null,whoF='all';
try{whoF=localStorage.getItem('whofilter')||'all'}catch{}
const WHOF=[['all',t('Alle','All')],['on',t('An','On')],['new',t('Neu, noch nie an','New, never on')],['need',t('Braucht dich','Needs you')]];
const whoName=f=>f.name[L==='en'?1:0];
const whoItem=f=>document.querySelector(`#pane-feat .fitem[data-sw="chat.${f.switch}"]`);
const whoNeed=f=>{const it=whoItem(f);return !!(f.spark&&it&&typeof featNeed==='function'&&featNeed(it))};
// indented below the function it builds on, when that one sits in the same group
const whoSub=f=>!!(f.parent&&WHO.features.some(x=>x.key===f.parent&&x.group===f.group));
function whoKeep(f){return whoF==='on'?f.spark:whoF==='new'?!f.seen:whoF==='need'?whoNeed(f):true}
async function loadWho(){const box=$('whobox');if(!box)return;
  if(typeof loadCfg==='function'&&!document.body.classList.contains('mgr'))try{await loadCfg()}catch{}
  try{WHO=await (await api('/api/admin/features')).json()}catch(e){box.textContent=e.message;return}
  drawWho()}
function whoGuest(f){return f.guests?(WHO.public?t('ja','yes'):t('mit Gastzugang','with guest access')):t('nie','never')}
function whoBox(on,can,label,act){const b=document.createElement('button');b.type='button';b.className='wbox'+(on?' on':'')+(can?'':' no');
  b.setAttribute('aria-pressed',on?'true':'false');b.setAttribute('aria-label',label);b.title=label;b.disabled=!can;if(can&&act)b.onclick=act;return b}
async function whoSpark(f,on){try{await api('/api/admin/switches',xjson('PUT',{key:f.switch,on}));await loadWho();
    if(typeof loadCfg==='function'&&!document.body.classList.contains('mgr'))loadCfg()}catch(e){alert(e.message)}}
async function whoNew(f,on){try{await api(`/api/admin/features/${encodeURIComponent(f.key)}/new`,xjson('PUT',{on}));f.new=on;drawWho()}catch(e){alert(e.message)}}
const whoNewBox=f=>f.profile?whoBox(!!f.new,true,`${whoName(f)} – ${t('neue Profile','new profiles')}: ${f.new?t('an','on'):t('aus','off')}`,()=>whoNew(f,!f.new)):(()=>{const s=document.createElement('span');s.className='wdash';s.textContent='–';return s})();
async function whoSet(f,uid,on){try{await api(`/api/admin/features/${encodeURIComponent(f.key)}/profiles/${encodeURIComponent(uid)}`,xjson('PUT',{on}));
    f.cells[uid]=on;drawWho()}catch(e){alert(e.message)}}
function whoOpen(f){goSec('feat');setTimeout(()=>{const it=whoItem(f);if(it&&typeof featShow==='function'){featShow(it);it.scrollIntoView({block:'center'})}},150)}
function whoCell(f,p){const n=p.name;
  if(!f.profile){const s=document.createElement('span');s.className='wdash';s.textContent=f.spark?'✓':'–';
    s.title=f.spark?t('Kein eigener Schalter: gilt für alle Profile','No own switch: applies to every profile'):t('Spark aus','Spark off');return s}
  const on=!!f.cells[p.id];return whoBox(on,f.spark,`${whoName(f)} – ${n}: ${on?t('an','on'):t('aus','off')}`,()=>whoSet(f,p.id,!on))}
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
        if(f.profile){for(const p of WHO.profiles){const c=whoCell(f,p);c.classList.add('chip');c.textContent=p.name;chips.appendChild(c)}
          const nb=whoNewBox(f);nb.classList.add('chip','wnewchip');nb.textContent=t('Neue Profile','New profiles');chips.appendChild(nb)}
        else{const s=document.createElement('span');s.className='mut';s.textContent=f.spark?t('Gilt für alle Profile','Applies to every profile'):t('Spark aus','Spark off');chips.appendChild(s)}
        const gs=document.createElement('span');gs.className='mut wg';gs.textContent=t('Gäste: ','Guests: ')+whoGuest(f);chips.appendChild(gs);
        r.appendChild(chips);box.appendChild(r)}}
    return}
  const wrap=document.createElement('div');wrap.className='whowrap';const tb=document.createElement('table');tb.className='who';
  const hr=document.createElement('tr');const th=x=>{const c=document.createElement('th');c.textContent=x;hr.appendChild(c);return c};
  th(t('Funktion','Function'));th('Spark');for(const p of WHO.profiles){const c=th(p.name);if(p.role)c.title=t('Admin-Rechte','Admin rights')}
  th(t('Neue Profile','New profiles')).title=t('Für jedes neu angelegte Profil gleich an','On for every new profile from the start');th(t('Gäste','Guests'));
  const head=document.createElement('thead');head.appendChild(hr);tb.appendChild(head);const body=document.createElement('tbody');
  for(const g of WHO.groups){const fs=rows.filter(f=>f.group===g.key);if(!fs.length)continue;
    const gr=document.createElement('tr');gr.className='wgrp';const gc=document.createElement('td');gc.colSpan=WHO.profiles.length+4;gc.textContent=g.name[L==='en'?1:0];gr.appendChild(gc);body.appendChild(gr);
    for(const f of fs){const tr=document.createElement('tr');if(whoSub(f))tr.className='sub';
      const nc=document.createElement('td');const nm=document.createElement('button');nm.type='button';nm.className='wname';nm.textContent=whoName(f);if(!mgr)nm.onclick=()=>whoOpen(f);
      nc.appendChild(nm);if(!f.seen){const n=document.createElement('span');n.className='wnew';n.textContent=t('neu','new');nc.appendChild(n)}
      if(whoNeed(f)){const n=document.createElement('span');n.className='wneed';n.textContent=t('braucht dich','needs you');nc.appendChild(n)}
      tr.appendChild(nc);
      const sc=document.createElement('td');sc.appendChild(whoBox(f.own,f.switchable,`${whoName(f)} – Spark: ${f.own?t('an','on'):t('aus','off')}`,()=>whoSpark(f,!f.own)));tr.appendChild(sc);
      for(const p of WHO.profiles){const c=document.createElement('td');c.appendChild(whoCell(f,p));tr.appendChild(c)}
      const nc2=document.createElement('td');nc2.className='wnewc';nc2.appendChild(whoNewBox(f));tr.appendChild(nc2);
      const gc2=document.createElement('td');gc2.className='mut';gc2.textContent=whoGuest(f);tr.appendChild(gc2);body.appendChild(tr)}}
  tb.appendChild(body);wrap.appendChild(tb);box.appendChild(wrap);
  const n=document.createElement('p');n.className='mut wnote';
  n.textContent=t('Ein Kästchen schaltet nur dort. Gestrichelt geht nicht: der Spark ist aus oder die Funktion hat keinen eigenen Schalter. Das Profil sieht seinen Schalter unter Ich und kann ihn selbst ändern. „Neue Profile“: gleich an für jedes Profil, das ab jetzt angelegt wird.',
    'A box switches only there. Dashed cannot be used: the Spark is off or the function has no own switch. The profile sees its switch under Ich and can change it itself. "New profiles": on from the start for every profile created from now on.');
  box.appendChild(n)}
window.loadWho=loadWho;
if($('featwho'))$('featwho').onclick=()=>goSec('who');
