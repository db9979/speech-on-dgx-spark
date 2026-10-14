// "Funktionen vorschlagen" (tipps.py, plan plaene/funktionen-entdecken.md): the hint under an answer, the list under
// Ich → Überblick and the guided setup in the face's window. Which hint comes is the panel's rule; nothing here
// switches by itself: a plain own switch goes on the card ("Übernehmen", ten minutes "Rückgängig"), everything else
// is shown step by step on its Ich page, and "Prüfen" asks the panel whether it works now.
let TIPS_ON=false;
async function tipDo(id,what){const r=await apiTry('/api/profile/tipps/'+encodeURIComponent(id),{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({do:what,lang:L})});
  if(!r.r.ok)throw new Error(String(r.d.detail||t('Ging nicht.','Did not work.')).slice(0,200));return r.d}
const tipName=x=>(x.name||[])[L==='en'?1:0]||'';
function tipButtons(x,msg,gone){const row=document.createElement('span');row.className='tiprow';
  const add=(label,fn,main)=>{const b=document.createElement('button');b.type='button';b.className=main?'b p':'b';b.textContent=label;
    b.addEventListener('click',async e=>{e.stopPropagation();b.disabled=true;msg.textContent='';try{await fn()}catch(err){msg.textContent=err.message}b.disabled=false});row.appendChild(b)};
  if(x.how==='ask')add(t('Admin fragen','Ask the admin'),async()=>{const d=await tipDo(x.id,'ask');
    msg.textContent=d.reached?t('Gefragt: der Admin hat eine Mitteilung bekommen.','Asked: the admin got a notification.'):t('Gefragt; gerade ist kein Gerät eines Admins erreichbar.','Asked; no admin device can be reached right now.')},true);
  else add(t('Einrichten','Set up'),()=>tipSetup(x),true);
  add(t('Nicht mehr zeigen','Do not show again'),async()=>{await tipDo(x.id,'never');msg.textContent=t('Kommt nicht mehr.','Will not come again.');row.remove();if(gone)gone()});
  return row}
// under the answer: one line with the reason and the buttons (chat.js whyNote)
function tipNote(d,x){const box=document.createElement('div');box.className='tipnote';
  const why=document.createElement('span');why.textContent='💡 '+((x.why||[])[L==='en'?1:0]||'');box.appendChild(why);
  const msg=document.createElement('small');msg.className='mut';msg.setAttribute('role','status');
  box.appendChild(tipButtons(x,msg));box.appendChild(msg);d.appendChild(box)}
// the guided setup in the face's window: the guide's steps, the Ich page, "Prüfen" and "Fertig"
async function tipSetup(x){const d=await tipDo(x.id,'setup');let box=$('tipsetup');
  if(!box){box=document.createElement('div');box.id='tipsetup';box.className='tipsetup';$('fabcards').after(box)}
  box.textContent='';const h=document.createElement('h4');h.textContent=t('Einrichten: ','Set up: ')+tipName(d);box.appendChild(h);
  if(d.how==='admin'){const p=document.createElement('p');p.textContent=t('Auf dem Spark aus. Einschalten unter ','Off on the Spark. Switch it on under ')+d.admin_way+'.';box.appendChild(p)}
  if(d.card&&typeof hilfeCard==='function')box.appendChild(hilfeCard(d.card));
  if(d.steps&&d.steps.length){const ol=document.createElement('ol');for(const s of d.steps){const li=document.createElement('li');li.textContent=s;ol.appendChild(li)}box.appendChild(ol)}
  const msg=document.createElement('div');msg.className='hmsg mut tipmsg';msg.setAttribute('role','status');
  const row=document.createElement('div');row.className='row';
  const add=(label,fn,main)=>{const b=document.createElement('button');b.type='button';b.className=main?'b p':'b';b.textContent=label;b.addEventListener('click',e=>{e.stopPropagation();fn()});row.appendChild(b)};
  // the jump lands on the setting itself (way.js unfolds and marks the row); without a way the Ich page
  const way=d.how==='admin'?d.admin_way:d.way;
  const page=()=>{if(way&&typeof wayGo==='function'&&wayParse(way,0))wayGo(way);
    else if(d.how==='admin'){if(typeof goCfg==='function')goCfg('feat')}else if(d.me&&typeof openMe==='function')openMe(d.me)};
  if(d.me||d.how==='admin')add(t('Seite öffnen','Open the page'),page);
  add(t('Prüfen','Check'),async()=>{msg.textContent='';try{const r=await tipDo(x.id,'check');
    msg.textContent=r.ok?t('Eingerichtet, es geht.','Set up, it works.'):(r.why||t('Noch nicht eingerichtet.','Not set up yet.'));
    if(r.ok){tipGone(x.id);if(typeof whoSoon==='function')whoSoon()}}catch(e){msg.textContent=e.message}},true);
  add(t('Fertig','Done'),()=>{box.remove();$('fab').classList.remove('open')});
  box.appendChild(row);box.appendChild(msg);$('fab').classList.add('open');page()}
// set up: its entry under "Für dich vorgeschlagen" goes (the panel does not list it again either)
function tipGone(id){const sec=$('tipover');if(!sec)return;for(const it of sec.querySelectorAll('.tipitem'))if(it.dataset.tip===id)it.remove();
  if(!sec.querySelector('.tipitem'))sec.remove()}
// Ich → Überblick: "Für dich vorgeschlagen", at most three, each with its reason (on a phone, whose Ich has no
// Überblick page, above the list of Ich pages, like "Heute")
async function tipOver(box){const old=$('tipover');if(old)old.remove();if(!TIPS_ON||!PROFILE)return;
  let d;try{d=await (await api('/api/profile/tipps')).json()}catch{return}
  if(!d.on||!d.items||!d.items.length||!box.isConnected)return;if($('tipover'))$('tipover').remove();
  const sec=document.createElement('div');sec.id='tipover';sec.className='tipover';
  const head=document.createElement('div');head.className='mgrp';head.textContent=t('Für dich vorgeschlagen','Suggested for you');sec.appendChild(head);
  for(const x of d.items){const it=document.createElement('div');it.className='tipitem';it.dataset.tip=x.id;
    const b=document.createElement('b');b.textContent=tipName(x);const why=document.createElement('span');why.textContent=(x.why||[])[L==='en'?1:0]||'';
    const msg=document.createElement('small');msg.className='mut';msg.setAttribute('role','status');
    it.append(b,why,tipButtons(x,msg,()=>setTimeout(()=>it.remove(),1500)),msg);sec.appendChild(it)}
  const nav=$('ptabs');if(PHONE.matches&&nav){nav.parentNode.insertBefore(sec,nav);return}
  const list=box.querySelector('.overlist');box.insertBefore(sec,list?list.previousElementSibling||list:null)}
