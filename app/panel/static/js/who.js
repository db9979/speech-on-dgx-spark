// Personen und Geräte → Gesperrte Funktionen (plan „Vereinheitlichen“ Phase 3, V01.0.269; plan „Freigabe vereinfachen“,
// Dominik 2026-10-13; slimmed down, Dominik 2026-10-14 option 3 „Verschlanken“; a box under Personen und Geräte instead of the page Funktionen → „Wer darf was“ since
// Dominik 2026-10-16 option 1): what the Spark allows works at once
// for every profile, so the page lists only the functions the admin blocked for at least one profile: the name (jumps
// to the function) and one chip per blocked profile (tap lifts the block). New blocks are set in the function itself
// (fdetail.js „Wer darf es“). Nothing blocked: one sentence with a jump to Funktionen. Guests never get a function (one
// line below). Computers and phones get the same list. Data from /api/admin/features (features.py), lifting a block
// over /api/admin/features/<key>/profiles/<id> ({on:true}).
let WHO=null,WHO_LAST=null,WHO_JUMP=0;   // WHO_LAST: the row the last name jumped to; WHO_JUMP: when, until the user moves
const whoName=f=>f.name[L==='en'?1:0];
// blocked for this profile by the admin itself (not through a function it builds on: that one has its own row)
const whoBlocked=f=>WHO.profiles.filter(p=>f.blockable!==false&&f.cells[p.id]===false);
let WHO_SEQ=0;   // only the newest load draws: an older answer arriving late must not show an old state
async function loadWho(){const box=$('whobox');if(!box)return;const seq=++WHO_SEQ;
  // the settings side by side (plan seiten-laden.md): a name jumps into them
  const cfg=typeof loadCfg==='function'&&!document.body.classList.contains('mgr')?loadCfg().catch(()=>{}):null;
  let got;try{got=await (await api('/api/admin/features')).json()}catch(e){await cfg;if(seq===WHO_SEQ)box.textContent=e.message;return}
  await cfg;if(seq!==WHO_SEQ)return;WHO=got;if(typeof needsSet==='function')needsSet(WHO)
  drawWho()}
function whoGuest(){return t('Gäste bekommen nur Fragen und Antworten, keine Funktion.','Guests only get questions and answers, no function.')}   // never a function (Dominik 2026-10-13)
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
  // a settings load started elsewhere (Gesperrte Funktionen loads them too) may still be drawing the rows: wait for them,
  // on a busy machine up to 20 s; a newer jump wins
  let row=whoRow(f);for(let i=0;!row&&i<80&&me===whoOpen.n;i++){await new Promise(r=>setTimeout(r,250));row=whoRow(f)}
  if(me!==whoOpen.n)return;
  WHO_LAST=row;if(!row)return;whoJumped();const it=row.closest('#pane-feat .fitem');
  if(it&&typeof featShow==='function')featShow(it);
  for(let d=row.parentElement;d&&d!==document.body;d=d.parentElement)if(d.tagName==='DETAILS'&&!d.open)d.open=true;
  requestAnimationFrame(()=>{if(typeof sFlash==='function')sFlash(row);else row.scrollIntoView({block:'center'})})}
// boxes that fill in later (the profile chips of a function, slow with many profiles) push the row away: they scroll
// back to it until the user scrolls, taps or types himself, for 15 s after it last had to (at most a minute)
function whoJumped(){WHO_JUMP=whoJumped.t0=Date.now();clearInterval(whoJumped.t);
  const stop=()=>{WHO_JUMP=0;clearInterval(whoJumped.t);for(const e of WHO_STOP)removeEventListener(e,stop,true)};
  for(const e of WHO_STOP)addEventListener(e,stop,{capture:true,passive:true});
  // anything drawn later above the row (not only the chips) moves it: bring it back while it is out of view
  whoJumped.t=setInterval(()=>{if(!whoKeepJump()){clearInterval(whoJumped.t);return}
    // each time it had to bring the row back, 15 s more (a busy phone draws for longer), at most one minute in all
    const r=WHO_LAST.getBoundingClientRect();if(r.height&&(r.top<0||r.bottom>innerHeight)){WHO_LAST.scrollIntoView({block:'center'});
      WHO_JUMP=Math.min(Date.now(),whoJumped.t0+45000)}},400)}
const WHO_STOP=['wheel','touchstart','keydown','pointerdown'];
function whoKeepJump(){return !!(WHO_JUMP&&Date.now()-WHO_JUMP<15000&&WHO_LAST&&WHO_LAST.isConnected)}
// a blocked profile's chip: tap allows the function for it again
function whoChip(f,p){const b=document.createElement('button');b.type='button';b.className='wchip';b.dataset.uid=p.id;
  b.textContent='⊘ '+p.name;const label=t('gesperrt, antippen erlaubt wieder','blocked, tap to allow again');
  b.setAttribute('aria-label',`${whoName(f)} – ${p.name}: ${label}`);b.title=label;b.onclick=()=>whoSet(f,p.id,true);return b}
function drawWho(){const box=$('whobox');if(!box||!WHO)return;box.textContent='';
  const mgr=document.body.classList.contains('mgr'),rows=WHO.features.filter(f=>whoBlocked(f).length);
  if(!rows.length){const p=document.createElement('p');p.className='wempty';
    p.textContent=t('Kein Profil ist gesperrt. Sperren setzt du in der Funktion unter „Wer darf es“.','No profile is blocked. You set blocks in the function under "Who may use it".');
    // the jump to Funktionen (Sprung-Links): a Verwalter does not have that page
    if(!mgr){const b=document.createElement('button');b.type='button';b.className='wlink';b.textContent=t('Zu den Funktionen','To the features');b.onclick=()=>goSec('feat');p.append(' ',b)}
    box.appendChild(p)}
  for(const f of rows){const r=document.createElement('div');r.className='wrow';
    const nm=document.createElement('button');nm.type='button';nm.className='wname';nm.textContent=whoName(f);if(!mgr)nm.onclick=()=>whoOpen(f);
    const chips=document.createElement('div');chips.className='wchips';for(const p of whoBlocked(f))chips.appendChild(whoChip(f,p));
    r.append(nm,chips);box.appendChild(r)}
  const n=document.createElement('p');n.className='mut wnote';n.textContent=whoGuest();box.appendChild(n)}
window.loadWho=loadWho;
