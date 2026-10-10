// The "Ich" window: profile login, the profile's own pages and the conversation settings.
// ---------------------------------------------------------------- profile of this browser
function setProfile(p){const changed=(p&&p.id)!==(PROFILE&&PROFILE.id);PROFILE=p||null;
  $('profname').textContent=PROFILE?PROFILE.name:t('Gast','Guest');
  if(changed){stopListening(true);stopAnswer();convos.cache=[];openConvo(null);convos.sync().then(()=>{if(!chat.msgs.length)openConvo(latestConvo())})}
  loadSettings();rem.load();if(window.room)room.show();guestLock()}
// Guests change no settings and cannot use room mode: they get the admin's defaults (the admin's own browser may).
const isGuest=()=>!PROFILE&&!ADMIN;
function guestLock(){const g=isGuest();['chathands','chatwake'].forEach(id=>{const l=$(id).closest('label');if(l)l.style.display=g?'none':''});
  if(g)stopWake();else if($('chatwake').checked&&!wake.on)startWake()}   // "Hey Spark" only for profiles (and the admin)
window.closeProf=()=>{$('profmodal').style.display='none';endEnroll()};
async function showFacts(){const r=await api('/api/profile/memory');const d=await r.json();
  $('profhead').textContent=d.profile.name;showTidy(d.tidy);
  $('factlist').innerHTML=d.facts.slice().reverse().map(f=>`<li><span>${esc(f.text)}${f.auto?` <em class="auto">${t('automatisch','automatic')}</em>`:''}</span><button class="b" onclick="forgetFact('${escq(f.id)}')">${t('Löschen','Delete')}</button></li>`).join('')||`<li class="mut">${t('Noch nichts gemerkt.','Nothing remembered yet.')}</li>`}
// Documents (documents.py, wissen.py): the list with its state, the profile's own switches (only those
// the admin allows), a search to try without the language model, and the kept originals.
const docSize=n=>n<1048576?Math.max(1,Math.round(n/1024))+' KB':(n/1048576).toFixed(1)+' MB';
const DOCSW=[['pictures',t('Bilder und Scans lesen lassen','Let pictures and scans be read'),t('Fotos und Seiten ohne Text liest das Sprachmodell in Gesprächspausen ab.','The language model reads photos and pages without text in quiet moments.')],
  ['semantic',t('Bedeutungssuche','Meaning search'),t('Findet auch Stellen mit anderen Worten.','Also finds passages in other words.')],
  ['originals',t('Originale aufbewahren','Keep originals'),t('Die Datei bleibt auf dem Spark und lässt sich wieder öffnen (neue Uploads).','The file stays on the Spark and can be opened again (new uploads).')],
  ['shared',t('Gemeinsame Dokumente','Shared documents'),t('Eigene Dokumente mit „Für alle“ freigeben und die freigegebenen der anderen nutzen.','Share own documents with "For everyone" and use the ones the others share.')],
  ['brief',t('Steckbrief und Tags','Document card and tags'),t('Das Sprachmodell notiert in Pausen Titel, Art, Absender, Frist und Schlagwörter; der Assistent sucht damit gezielter.','In quiet minutes the language model notes title, kind, sender, deadline and keywords; the assistant searches more precisely with them.')],
  ['due',t('Fristen anbieten','Offer deadlines'),t('Hat ein Dokument eine Frist, gibt es den Knopf „Erinnern“. Eine Erinnerung entsteht nur auf deinen Klick.','When a document has a deadline there is a "Remind" button. A reminder is only set on your click.')]];
let DOCTAG='';
// the "Steckbrief" of a document (V01.0.244): kind, sender, deadline and the tags as chips (filter on click)
const docCard=(d,chips=true)=>{const bits=[d.art,d.sender,d.date&&t('vom ','of ')+d.date,d.due&&t('Frist ','deadline ')+d.due].filter(Boolean).map(esc).join(' · ');
  const tg=(d.tags||[]).map(x=>chips?`<button type="button" class="dtag${x.toLowerCase()===DOCTAG.toLowerCase()?' on':''}" data-doctag="${esc(x)}">${esc(x)}</button>`:`<span class="dtag">${esc(x)}</span>`).join('');
  return (bits?`<br><small class="mut">${bits}</small>`:'')+(tg?`<br><span class="dtags">${tg}</span>`:'')};
const docHas=(d,tag)=>!tag||(d.tags||[]).some(x=>x.toLowerCase()===tag.toLowerCase());
let DOCINFO=null;
// progress of one document (V01.0.232): pages read of all pages, then pieces with a meaning, and why it
// waits (switch off, daily limit, someone is talking, the model waits for memory). [text, percent or null]
function docState(d){const I=DOCINFO,pics=I&&I.allow.pictures&&I.on.pictures,mean=I&&I.vectors&&I.on.semantic;
  if(d.state==='reading'){const done=d.pages-d.todo,pct=d.pages?Math.round(100*done/d.pages):0;let why;
    if(!pics)why=t('wartet, „Bilder und Scans lesen“ ist aus','waiting, "Read pictures and scans" is off');
    else if(I.reading&&I.reading.doc===d.id)why=t(`liest gerade Seite ${I.reading.page}`,`reading page ${I.reading.page} now`);
    else if(I.night&&!I.night.long_ok&&d.pages>I.night.long)why=t(`langes Dokument, wird nachts ab ${I.night.from} gelesen`,`long document, read at night from ${I.night.from}`);
    else if(!(I.night&&I.night.active)&&I.today>=I.day_pages)why=I.night?t(`Tagesgrenze erreicht, geht nachts ab ${I.night.from} weiter`,`daily limit reached, continues at night from ${I.night.from}`):t('Tagesgrenze erreicht, geht morgen weiter','daily limit reached, continues tomorrow');
    else if(!I.quiet)why=t('wartet auf eine ruhige Minute','waits for a quiet minute');
    else why=t('ist gleich dran','next in line');
    return [t(`Seite ${done} von ${d.pages} gelesen`,`page ${done} of ${d.pages} read`)+' · '+why,pct]}
  if(d.state==='error')return [t('nicht lesbar','not readable'),null];
  const base=`${d.chunks} ${t('Abschnitte','sections')}`;
  if(mean&&d.chunks&&d.vecs<d.chunks){const m=I.model;
    const why=m==='waiting'?t(' · wartet auf freien Arbeitsspeicher',' · waits for free memory'):m==='error'?t(' · Bedeutungs-Modell hat einen Fehler',' · the meaning model has an error'):m==='starting'?t(' · Modell startet',' · model starting'):'';
    return [base+' · '+t(`Bedeutung ${d.vecs} von ${d.chunks}`,`meaning ${d.vecs} of ${d.chunks}`)+why,Math.round(100*d.vecs/d.chunks)]}
  return [base,null]}
// while something is still being read, the list refreshes itself as long as it is on screen
let docTimer=null;
function docAgain(l){clearTimeout(docTimer);const I=DOCINFO;
  const busy=l.some(d=>d.state==='reading'||(I&&I.vectors&&I.on.semantic&&d.chunks&&d.vecs<d.chunks));
  if(busy)docTimer=setTimeout(()=>{const box=$('docbox');if(box&&box.offsetParent!==null&&!document.hidden)showDocs();else docAgain(l)},10e3)}
async function showDocs(){if(!DOCS_ON){$('docbox').style.display='none';return}$('docbox').style.display='';
  const l=await (await api('/api/profile/docs')).json();
  try{DOCINFO=await (await api('/api/profile/wissen')).json()}catch{DOCINFO=null}
  const I=DOCINFO;
  $('docsw').innerHTML=I?DOCSW.filter(([k])=>k==='due'?I.allow.brief&&I.on.brief:I.allow[k]).map(([k,l,h])=>`<div class="setrow"><div class="lbl"><b>${esc(l)}</b><span>${esc(h)}</span></div><label class="tgl"><input type="checkbox" data-docsw="${k}"${I.on[k]?' checked':''}><i></i></label></div>`).join(''):'';
  const brief=!!(I&&I.allow.brief&&I.on.brief),due=brief&&I.on.due,today=new Date().toISOString().slice(0,10);
  const o=I&&I.others||[];
  // all tags of the own and the shared documents, to filter the lists
  const all={};if(brief)for(const d of l.concat(o))for(const x of d.tags||[]){const k=x.toLowerCase();all[k]=all[k]||[x,0];all[k][1]++}
  if(DOCTAG&&!all[DOCTAG.toLowerCase()])DOCTAG='';
  const tags=Object.values(all).sort((a,b)=>b[1]-a[1]||a[0].localeCompare(b[0]));$('doctagbar').hidden=!tags.length;
  $('doctagbar').innerHTML=tags.length?`<button type="button" class="dtag${DOCTAG?'':' on'}" data-doctag="">${t('Alle','All')}</button>`+tags.map(([x,n])=>`<button type="button" class="dtag${x.toLowerCase()===DOCTAG.toLowerCase()?' on':''}" data-doctag="${esc(x)}">${esc(x)} <small>${n}</small></button>`).join(''):'';
  $('doclist').innerHTML=l.filter(d=>!brief||docHas(d,DOCTAG)).map(d=>{const [st,pct]=docState(d);return `<li><span>${esc(brief&&d.title||d.name)}<br><small class="mut">${brief&&d.title?esc(d.name)+' · ':''}${docSize(d.size)} · ${esc(st)}${d.note?' · '+esc(d.note):''}</small>`+(brief?docCard(d):'')+
    (pct===null?'':`<span class="qbar docbar" role="progressbar" aria-valuemin="0" aria-valuemax="100" aria-valuenow="${pct}"><i style="width:${pct}%"></i></span>`)+`</span>`+
    (I&&I.allow.shared&&I.on.shared&&d.state==='ready'?`<label class="docshare" title="${esc(t('Alle Profile mit „Gemeinsame Dokumente“ finden und öffnen es','Every profile with "Shared documents" finds and opens it'))}"><input type="checkbox" data-docshare="${esc(d.id)}"${d.shared?' checked':''}> ${t('Für alle','For everyone')}</label>`:'')+
    `<label class="tgl" title="${esc(t('Der Assistent sucht darin','The assistant searches it'))}"><input type="checkbox" data-docuse="${esc(d.id)}"${d.use?' checked':''}><i></i></label>`+
    `<button class="b" type="button" data-docview="${esc(d.id)}">${t('Ansehen','View')}</button>`+
    (brief&&d.state==='ready'?`<button class="b" type="button" data-doctags="${esc(d.id)}" data-tags="${esc((d.tags||[]).join(', '))}" title="${esc(t('Eigene Schlagwörter; leer = die automatischen','Own keywords; empty = the automatic ones'))}">${t('Tags','Tags')}</button>`:'')+
    (due&&d.due&&(d.due.length===7?d.due>=today.slice(0,7):d.due>=today)?`<button class="b" type="button" data-docremind="${esc(d.id)}" title="${esc(t('Erinnerung sechs Wochen vor der Frist (oder am Tag davor)','Reminder six weeks before the deadline (or the day before)'))}">${t('Erinnern','Remind')}</button>`:'')+
    (d.file&&d.state!=='reading'?`<button class="b" type="button" data-docreread="${esc(d.id)}" title="${esc(t('Aus dem aufbewahrten Original neu einlesen','Read again from the kept original'))}">${t('Neu einlesen','Read again')}</button>`:'')+
    `<button class="b" type="button" data-docdel="${esc(d.id)}" data-name="${esc(d.name)}">${t('Löschen','Delete')}</button></li>`}).join('')||`<li class="mut">${t('Noch keine Dokumente.','No documents yet.')}</li>`;
  const bits=[];
  if(I&&I.space){const pct=Math.min(100,Math.round(100*I.used/I.space));$('docspace').hidden=false;
    $('docspacet').textContent=t(`Belegt: ${docSize(I.used)} von ${docSize(I.space)} (${pct} %)`,`Used: ${docSize(I.used)} of ${docSize(I.space)} (${pct} %)`)+(I.quota?t(`, davon Originale ${docSize(I.usage)}`,`, originals ${docSize(I.usage)}`):'');
    const bar=$('docspace').querySelector('i');bar.style.width=pct+'%';$('docspace').classList.toggle('full',pct>=90)}
  if(I&&I.allow.pictures&&I.on.pictures)bits.push(t(`heute ${I.today} von ${I.day_pages} Seiten gelesen`,`${I.today} of ${I.day_pages} pages read today`));
  if(I&&I.vectors&&I.on.semantic)bits.push(t(`Bedeutungssuche: ${I.vectors[0]} von ${I.vectors[1]} Abschnitten vorbereitet`,`Meaning search: ${I.vectors[0]} of ${I.vectors[1]} sections prepared`));
  $('docuse').textContent=bits.join(' · ');docAgain(l);
  $('docothers').hidden=!o.length;
  $('docotherlist').innerHTML=o.filter(d=>!brief||docHas(d,DOCTAG)).map(d=>`<li><span>${esc(brief&&d.title||d.name)}<br><small class="mut">${t('von ','from ')}${esc(d.owner)}</small>${brief?docCard(d,false):''}</span><button class="b" type="button" data-docview="${esc(d.id)}">${t('Ansehen','View')}</button></li>`).join('');
  const pics=I&&I.allow.pictures&&I.on.pictures;
  $('docfile').accept='.pdf,.txt,.md,.docx,.html,.htm,.csv,.xlsx,.pptx,.odt,.ods,.odp,.eml'+(pics?',.jpg,.jpeg,.png,.webp':'')}
$('docsw').onchange=async e=>{const k=e.target.dataset.docsw;if(!k)return;
  try{await api('/api/profile/settings',{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({['doc_'+k]:e.target.checked})})}
  catch(x){$('docmsg').innerHTML=`<span class="err">${esc(x.message)}</span>`}showDocs()};
$('doctagbar').onclick=e=>{const c=e.target.closest('[data-doctag]');if(c){DOCTAG=c.dataset.doctag;showDocs()}};
$('docotherlist').onclick=e=>{const v=e.target.closest('[data-docview]');if(v)docView(v.dataset.docview)};
$('doclist').onchange=async e=>{const sh=e.target.dataset.docshare;
  if(sh){try{await api('/api/profile/wissen/'+encodeURIComponent(sh),{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({shared:e.target.checked})})}
    catch(x){$('docmsg').innerHTML=`<span class="err">${esc(x.message)}</span>`;showDocs()}return}
  const id=e.target.dataset.docuse;if(!id)return;
  try{await api('/api/profile/wissen/'+encodeURIComponent(id),{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({use:e.target.checked})})}
  catch(x){$('docmsg').innerHTML=`<span class="err">${esc(x.message)}</span>`;showDocs()}};
// a document read again: the kept original (pictures and PDFs in the browser, the rest as a download)
// and its stored text, built with textContent only
async function docView(id){const box=$('docview');box.hidden=false;box.textContent=t('Lade …','Loading …');
  try{const d=await (await api('/api/profile/wissen/'+encodeURIComponent(id)+'/text')).json();box.textContent='';
    const head=document.createElement('div');head.className='dvhead';const nm=document.createElement('b');nm.textContent=d.name+(d.owner?' · '+t('von ','from ')+d.owner:'');head.appendChild(nm);
    const right=document.createElement('span');
    if(d.file){const a=document.createElement('a');a.className='b';const pdf=/\.pdf$/i.test(d.name),pic=d.kind==='picture';
      a.href='/api/profile/wissen/'+encodeURIComponent(id)+'/file'+(pdf||pic?'?view=1':'');if(pdf)a.target='_blank';a.rel='noopener';
      a.textContent=pdf?t('PDF öffnen','Open PDF'):pic?t('Bild öffnen','Open picture'):t('Original herunterladen','Download original');right.appendChild(a);
      if(pic){const img=document.createElement('img');img.alt='';img.src=a.href;box.appendChild(img)}}
    const x=document.createElement('button');x.type='button';x.className='b';x.textContent='✕';x.onclick=()=>{box.hidden=true;box.textContent=''};right.appendChild(x);
    head.appendChild(right);box.prepend(head);
    let page;const show=parts=>{for(const p of parts){if(p.page&&p.page!==page){page=p.page;const h=document.createElement('div');h.className='dvpage';h.textContent=t('Seite ','Page ')+p.page;box.appendChild(h)}
      const tx=document.createElement('p');tx.className='dvtext';tx.textContent=p.text;box.appendChild(tx)}};show(d.parts);
    if(d.related&&d.related.length){const r=document.createElement('div');r.className='dvrel';const h=document.createElement('small');h.className='mut';h.textContent=t('Dazu gehören: ','Belongs with: ');r.appendChild(h);
      for(const x of d.related){const b=document.createElement('button');b.type='button';b.className='dtag';b.textContent=x.title||x.name;
        b.title={Nummer:t('gleiche Nummer','same number'),Absender:t('gleicher Absender','same sender'),Tags:t('gleiche Schlagwörter','same keywords')}[x.why]||'';b.onclick=()=>docView(x.id);r.appendChild(b)}
      box.appendChild(r)}
    if(!d.parts.length){const m=document.createElement('p');m.className='mut';m.textContent=d.state==='reading'?t('Wird noch gelesen.','Still being read.'):t('Kein Text.','No text.');box.appendChild(m)}
    if(!d.file&&!d.owner){const m=document.createElement('p');m.className='mut';m.textContent=t('Original nicht aufbewahrt: Zum Neu-Einlesen die Datei neu hochladen.','Original not kept: to read it again, upload the file again.');box.appendChild(m)}
    // long documents come a part at a time; the assistant always searches the whole text
    const more=next=>{if(next==null)return;const b=document.createElement('button');b.type='button';b.className='b';b.textContent=t('Weiterlesen','Read on');
      b.onclick=async()=>{b.disabled=true;try{const n=await (await api('/api/profile/wissen/'+encodeURIComponent(id)+'/text?start='+next)).json();b.remove();show(n.parts);more(n.next)}
        catch(x){b.disabled=false;b.textContent=x.message}};box.appendChild(b)};more(d.next);
    box.scrollIntoView({block:'nearest'})}
  catch(x){box.textContent=x.message}}
$('doclist').onclick=async e=>{const v=e.target.closest('[data-docview]');if(v){docView(v.dataset.docview);return}
  const c=e.target.closest('[data-doctag]');if(c){DOCTAG=c.dataset.doctag;showDocs();return}
  const tg=e.target.closest('[data-doctags]');
  if(tg){const s=prompt(t('Schlagwörter, mit Komma getrennt (leer = die automatischen):','Keywords separated by commas (empty = the automatic ones):'),tg.dataset.tags);if(s===null)return;
    const list=s.split(',').map(x=>x.trim()).filter(Boolean);
    try{await api('/api/profile/wissen/'+encodeURIComponent(tg.dataset.doctags),{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({tags:list.length?list:null})})}
    catch(x){$('docmsg').innerHTML=`<span class="err">${esc(x.message)}</span>`}showDocs();return}
  const rm=e.target.closest('[data-docremind]');
  if(rm){rm.disabled=true;try{const r=await (await api('/api/profile/wissen/'+encodeURIComponent(rm.dataset.docremind)+'/remind',{method:'POST'})).json();
      $('docmsg').textContent=t('Erinnerung angelegt für ','Reminder set for ')+new Date(r.due).toLocaleString(L==='en'?'en-GB':'de-DE',{dateStyle:'medium',timeStyle:'short'})}
    catch(x){$('docmsg').innerHTML=`<span class="err">${esc(x.message)}</span>`;rm.disabled=false}return}
  const rr=e.target.closest('[data-docreread]');
  if(rr){rr.disabled=true;try{const r=await (await api('/api/profile/wissen/'+encodeURIComponent(rr.dataset.docreread)+'/reread',{method:'POST'})).json();
      $('docmsg').textContent=r.todo?t(`Wird neu gelesen: ${r.todo} Seiten warten.`,`Being read again: ${r.todo} pages waiting.`):t(`Neu eingelesen: ${r.chunks} Abschnitte.`,`Read again: ${r.chunks} sections.`)}
    catch(x){$('docmsg').innerHTML=`<span class="err">${esc(x.message)}</span>`}showDocs();return}
  const b=e.target.closest('[data-docdel]');if(!b)return;
  if(!confirm(t('Dokument „','Delete document "')+b.dataset.name+t('“ löschen?','"?')))return;await api('/api/profile/docs/'+encodeURIComponent(b.dataset.docdel),{method:'DELETE'});showDocs()};
async function docTry(){const q=$('docq').value.trim();if(!q)return;$('dochits').innerHTML=`<li class="mut">${t('Suche …','Searching …')}</li>`;
  try{const r=await (await api('/api/profile/wissen/search',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({q})})).json();
    $('dochits').innerHTML=r.hits.map(h=>`<li><span><b>${esc(h.name)}${h.page?' · '+t('Seite ','page ')+h.page:''}</b><br><small>${esc(h.text)}</small></span></li>`).join('')||`<li class="mut">${t('Nichts gefunden.','Nothing found.')}</li>`}
  catch(x){$('dochits').innerHTML=`<li class="err">${esc(x.message)}</li>`}}
$('docqgo').onclick=docTry;$('docq').onkeydown=e=>{if(e.key==='Enter')docTry()};
let DOCS_ON=true,SPK_ON=false,CAL_ON=true,HA_ON=false,MAIL_ON=false;
// The "Ich" window: conversation settings for everyone, plus the profile's own pages once logged in.
// On phones the window opens as a list of its pages (like the iPhone settings); a page then fills the
// screen with a back arrow. Wider screens keep the side bar.
const PHONE=matchMedia('(max-width:760px)');
function ptab(id,page=true){document.querySelectorAll('#ptabs button').forEach(b=>{b.classList.toggle('on',b.dataset.t===id);if(b.dataset.t===id)$('mepage').textContent=b.firstChild.textContent});
  document.querySelectorAll('#profmodal .ptab').forEach(x=>x.classList.toggle('on',x.id===id));
  if(typeof guidesMe==='function')guidesMe(id);
  $('profmodal').classList.toggle('sub',page);if(page)document.querySelector('#profmodal .mebody').scrollTop=0}
$('meback').onclick=()=>ptab(meLast,false);
function meTabs(){const items=[['overbox',t('Überblick','Overview'),!!PROFILE&&!PHONE.matches],['setbox',t('Gespräch','Conversation'),!GATE&&!isGuest()],['loginbox',t('Anmelden','Sign in'),!PROFILE],
    ['factbox',t('Gedächtnis','Memory'),!!PROFILE],['docbox',t('Dokumente','Documents'),PROFILE&&DOCS_ON],['logbox',t('Protokoll','Log'),!!PROFILE],
    ['calbox',t('Kalender','Calendar'),PROFILE&&CAL_ON],['taskbox',t('Aufgaben','Tasks'),PROFILE&&TASK_ON],['agentbox',t('Aufträge','Jobs'),PROFILE&&AGENT_ON],['msgbox',t('Nachrichten','Messages'),PROFILE&&MSG_ON],['wxbox',t('Wetter','Weather'),PROFILE&&WX_ON],['probox',t('Von selbst','Proactive'),PROFILE&&PRO_ON],['notebox',t('Mitteilungen','Notifications'),PROFILE&&REM_ON],
    ['mailbox',t('E-Mail','E-mail'),PROFILE&&MAIL_ON],['parbox',t('Pakete','Parcels'),PROFILE&&PAR_ON],['conbox',t('Kontakte','Contacts'),PROFILE&&CON_ON],
    ['habox',t('Smart Home','Smart home'),PROFILE&&HA_ON],['roombox',t('Raum-Modus','Room mode'),PROFILE&&ROOM_ON],['espbox',t('Lautsprecher','Speakers'),PROFILE&&ESP_ON],
    ['trbox',t('Bus und Bahn','Bus and train'),PROFILE&&TR_ON],['tgbox',t('Telegram','Telegram'),PROFILE&&TG_ON],['appbox',t('iPhone-App','iPhone app'),PROFILE&&APP_ON],['pebbox',t('Pebble-Uhr','Pebble watch'),PROFILE&&PEB_ON],
    ['secbox',t('Sicherheit','Security'),!!PROFILE],['voicebox',t('Sprechererkennung','Speaker identification'),PROFILE&&SPK_ON]].filter(x=>x[2]);
  // pages in the same groups as everywhere else (guides.js), with a small header per group
  let grp=null;$('ptabs').innerHTML=items.map(([id,l])=>{const g=typeof meGroup==='function'?meGroup(id):null,gg=g&&GGROUPS.find(x=>x[0]===g);
    const head=g&&g!==grp?`<div class="mgrp">${esc(t(gg[1],gg[2]))}</div>`:'';if(g)grp=g;
    return head+`<button type="button" data-t="${id}">${esc(l)}<small class="mst" data-st="${id}"></small></button>`}).join('');
  $('ptabs').querySelectorAll('button').forEach(b=>b.onclick=()=>{meLast=b.dataset.t;ptab(b.dataset.t)});ME_ITEMS=items;
  $('profmodal').classList.toggle('one',items.length<2);if(typeof meSearchMount==='function')meSearchMount();return items.map(x=>x[0])}
let meLast='overbox',ME_ITEMS=[];
// "Überblick": one line per page with its state, read from the pages just loaded (no extra requests)
function meState(){const n=id=>[...document.querySelectorAll('#'+id+'>li')].filter(x=>!x.classList.contains('mut')).length;
  const cnt=(k,de1,deN,en1,enN)=>k?t(k+' '+(k===1?de1:deN),k+' '+(k===1?en1:enN)):t('noch nichts','nothing yet');
  const txt=id=>{const e=$(id);return e?e.textContent.trim():''};
  return {factbox:cnt(n('factlist'),'Eintrag','Einträge','entry','entries'),docbox:cnt(n('doclist'),'Dokument','Dokumente','document','documents'),
    calbox:n('callist')?cnt(n('callist'),'Kalender verbunden','Kalender verbunden','calendar connected','calendars connected'):t('nicht verbunden','not connected'),
    mailbox:n('maillist')?cnt(n('maillist'),'Postfach','Postfächer','mailbox','mailboxes'):t('nicht verbunden','not connected'),
    habox:$('hadel')&&$('hadel').style.display!=='none'?t('verbunden','connected'):t('nicht verbunden','not connected'),
    voicebox:$('voicedel')&&$('voicedel').style.display!=='none'?t('eingelernt','enrolled'):t('nicht eingelernt','not enrolled'),
    secbox:n('secdev')?cnt(n('secdev'),'Gerät mit Schlüssel','Geräte mit Schlüssel','device with a key','devices with a key'):'',
    notebox:$('pushoff')&&$('pushoff').style.display!=='none'?t('auf diesem Gerät an','on for this device'):t('auf diesem Gerät aus','off for this device'),
    setbox:S.hands?t('freihändig','hands-free'):''}}
function showOver(){const st=meState(),box=$('overbox');
  document.querySelectorAll('#ptabs .mst').forEach(e=>e.textContent=st[e.dataset.st]||'');
  if(!box)return;let grp=null;
  box.innerHTML=`<div class="intro">${esc(t('Alles, was du für dich eingerichtet hast. Antippen öffnet die Seite.','Everything you set up for yourself. Tap to open the page.'))}</div><div class="overlist">`+
    ME_ITEMS.filter(([id])=>id!=='overbox'&&id!=='loginbox').map(([id,l])=>{const g=typeof meGroup==='function'?meGroup(id):null,gg=g&&GGROUPS.find(x=>x[0]===g);
      const head=g&&g!==grp?`<div class="mgrp">${esc(t(gg[1],gg[2]))}</div>`:'';if(g)grp=g;
      return head+`<button type="button" class="overrow" data-go="${id}"><b>${esc(l)}</b><span>${esc(st[id]||'')}</span></button>`}).join('')+'</div>';
  box.querySelectorAll('[data-go]').forEach(b=>b.onclick=()=>{meLast=b.dataset.go;ptab(b.dataset.go)})}
const TZ=()=>{try{return Intl.DateTimeFormat().resolvedOptions().timeZone}catch{return ''}};
const CALKIND={icloud:{name:'iCloud',url:'https://caldav.icloud.com',user:1,h:t('Benutzer: deine Apple-ID. Passwort: ein app-spezifisches Passwort von appleid.apple.com.','User: your Apple ID. Password: an app-specific password from appleid.apple.com.')},
  nextcloud:{name:'Nextcloud',url:'',ph:'https://cloud.example.de/remote.php/dav',user:1,h:t('Adresse mit /remote.php/dav, am besten mit App-Passwort.','Address with /remote.php/dav, best with an app password.')},
  caldav:{name:'',url:'',ph:'https://server.example.de/dav/',user:1,h:t('Server-, Konto- oder Kalender-Adresse.','Server, account or calendar address.')},
  ics:{name:'',url:'',ph:'webcal://… oder https://…/basic.ics',user:0,h:t('Ohne Benutzer. Google: „Privatadresse im iCal-Format“, iCloud: „Öffentlicher Kalender“.','No user. Google: "Secret address in iCal format", iCloud: "Public calendar".')}};
function calKind(){const k=CALKIND[$('calkind').value];$('calhint').textContent=k.h;$('calurl').placeholder=k.ph||k.url;
  if(!$('calurl').value||Object.values(CALKIND).some(x=>x.url&&x.url===$('calurl').value))$('calurl').value=k.url;
  if(!$('calname').value||Object.values(CALKIND).some(x=>x.name&&x.name===$('calname').value))$('calname').value=k.name;
  $('caluser').closest('.two2').style.display=k.user?'':'none';if(!k.user){$('caluser').value='';$('calpw').value=''}}
$('calkind').onchange=calKind;
function calRender(d){$('callist').innerHTML=d.calendars.map(c=>`<li><span><b>${esc(c.name)}</b><br><small class="mut">${esc(c.url.replace(/^\w+:\/\//,'').slice(0,48))}</small></span><button class="b" onclick="calRemove('${escq(c.id)}','${escq(c.name)}')">${t('Entfernen','Remove')}</button></li>`).join('')||`<li class="mut">${t('Noch kein Kalender verbunden.','No calendar connected yet.')}</li>`;
  $('caltopics').value=(d.topics||[]).join(', ');calKind();$('caltest').style.display=d.calendars.length?'':'none';$('caladd').open=!d.calendars.length}
async function showCal(){if(!CAL_ON)return;calRender(await (await api('/api/profile/calendar')).json());$('calmsg').textContent='';$('calmsg').className=''}
async function calRemove(id,name){if(!confirm(t('Kalender „','Remove calendar "')+name+t('“ entfernen?','"?')))return;calRender(await (await api('/api/profile/calendar/'+encodeURIComponent(id),{method:'DELETE'})).json())}
const calMsg=(x,err,list)=>{const m=$('calmsg');m.className=err?'err':'';m.innerHTML=esc(x)+(list&&list.length?'<ul class="facts small">'+list.map(e=>`<li>${esc(e)}</li>`).join('')+'</ul>':'')};
$('calsave').onclick=async()=>{calMsg(t('Prüfe den Kalender …','Checking the calendar …'));
  const r=await fetch('/api/profile/calendar',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name:$('calname').value,url:$('calurl').value.trim(),user:$('caluser').value.trim(),password:$('calpw').value,tz:TZ()})});
  const d=await r.json();if(!r.ok){calMsg(t('Nicht hinzugefügt: ','Not added: ')+(d.detail||r.status),true);return}
  ['calname','calurl','caluser','calpw'].forEach(i=>$(i).value='');calRender(d);
  calMsg(t('Hinzugefügt. ','Added. ')+(d.check.events.length?t('Die nächsten Termine:','Next appointments:'):t('Keine Termine in den nächsten 14 Tagen.','No appointments in the next 14 days.')),false,d.check.events)};
$('caltopsave').onclick=async()=>{const d=await (await api('/api/profile/calendar/topics',{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({topics:$('caltopics').value.split(',').map(x=>x.trim()).filter(Boolean)})})).json();calRender(d);calMsg(t('Themen gespeichert.','Topics saved.'))};
$('caltest').onclick=async()=>{calMsg(t('Lese die Kalender …','Reading the calendars …'));
  const r=await fetch('/api/profile/calendar/test',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({tz:TZ()})});const d=await r.json();
  if(!r.ok){calMsg(d.detail||r.status,true);return}
  calMsg(d.events.length?t('Die nächsten Termine:','Next appointments:'):t('Keine Termine in den nächsten 14 Tagen.','No appointments in the next 14 days.'),d.errors.length>0,[...d.events,...d.errors.map(e=>'⚠ '+e)])};
// E-mail per profile, read only; the password is never sent back.
const MAILKIND={icloud:t('Benutzer: deine iCloud-Mailadresse. Passwort: ein neues app-spezifisches Passwort von appleid.apple.com.','User: your iCloud mail address. Password: a new app-specific password from appleid.apple.com.'),
  gmail:t('Benutzer: deine Gmail-Adresse. Passwort: ein App-Passwort (Google-Konto → Sicherheit, braucht die Bestätigung in zwei Schritten).','User: your Gmail address. Password: an app password (Google account → Security, needs 2-step verification).'),
  gmx:t('Vorher in GMX unter E-Mail-Einstellungen → POP3/IMAP-Abruf den Zugriff erlauben.','First allow access in GMX under mail settings → POP3/IMAP.'),
  webde:t('Vorher in web.de unter E-Mail-Einstellungen → POP3/IMAP-Abruf den Zugriff erlauben.','First allow access in web.de under mail settings → POP3/IMAP.'),
  other:t('Nur verschlüsselt (TLS), meist Port 993.','Encrypted (TLS) only, usually port 993.')};
function mailKind(){const k=$('mailkind').value;$('mailhint').textContent=MAILKIND[k];$('mailsrv').style.display=k==='other'?'':'none'}
$('mailkind').onchange=mailKind;
const mailMsg=(x,err,list)=>{const m=$('mailmsg');m.className=err?'err':'';m.innerHTML=esc(x)+(list&&list.length?'<ul class="facts small">'+list.map(e=>`<li>${esc(e)}</li>`).join('')+'</ul>':'')};
function mailRender(d){if(window.showMailTidy&&d&&TIDY&&d.accounts.length!==TIDY.accounts.length)showMailTidy().catch(()=>{});$('maillist').innerHTML=d.accounts.map(a=>`<li><span><b>${esc(a.name)}</b><br><small class="mut">${esc(a.user)} · ${esc(a.host)}</small></span><button class="b" onclick="mailRemove('${escq(a.id)}','${escq(a.name)}')">${t('Entfernen','Remove')}</button></li>`).join('')||`<li class="mut">${t('Noch kein Postfach verbunden.','No mailbox connected yet.')}</li>`;
  mailKind();$('mailtest').style.display=d.accounts.length?'':'none';$('mailadd').open=!d.accounts.length}
async function showMail(){if(!MAIL_ON)return;mailRender(await (await api('/api/profile/mail')).json());mailMsg('')}
async function mailRemove(id,name){if(!confirm(t('Postfach „','Remove mailbox "')+name+t('“ entfernen?','"?')))return;mailRender(await (await api('/api/profile/mail/'+encodeURIComponent(id),{method:'DELETE'})).json())}
$('mailsave').onclick=async()=>{mailMsg(t('Prüfe das Postfach …','Checking the mailbox …'));
  const r=await fetch('/api/profile/mail',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({kind:$('mailkind').value,name:$('mailname').value,host:$('mailhost').value.trim(),port:$('mailport').value.trim(),user:$('mailuser').value.trim(),password:$('mailpw').value})});
  const d=await r.json();if(!r.ok){mailMsg(t('Nicht hinzugefügt: ','Not added: ')+(d.detail||r.status),true);return}
  ['mailname','mailhost','mailuser','mailpw'].forEach(i=>$(i).value='');mailRender(d);
  mailMsg(t('Hinzugefügt. ','Added. ')+d.check.unread+t(' ungelesen, ',' unread, ')+d.check.total+t(' Mails in den letzten ',' mails in the last ')+d.check.days+t(' Tagen.',' days.'))};
$('mailtest').onclick=async()=>{mailMsg(t('Lese die Postfächer …','Reading the mailboxes …'));
  const r=await fetch('/api/profile/mail/test',{method:'POST'});const d=await r.json();if(!r.ok){mailMsg(d.detail||r.status,true);return}
  mailMsg('',d.accounts.some(a=>!a.ok),d.accounts.map(a=>a.name+': '+(a.ok?a.unread+t(' ungelesen',' unread'):'⚠ '+a.error)))};
// Home Assistant per profile; the token is never sent back, only whether one is stored.
const haMsg=(x,err)=>{$('hamsg').textContent=x;$('hamsg').className='fh'+(err?' err':'')};
function haRender(d){$('haurl').value=d.url||'';$('hatoken').value='';$('hanoverify').checked=d.verify===false;$('haagent').value=d.agent||'';
  $('hatoken').placeholder=d.has_token?t('gespeichert, leer lassen zum Behalten','stored, leave empty to keep'):'';
  $('hastate').textContent=d.has_token?t('Verbunden mit ','Connected to ')+d.url:t('Noch nicht verbunden.','Not connected yet.');$('hadel').style.display=d.has_token?'':'none';
  $('hacodebox').style.display=d.has_token?'':'none';$('hacode').value='';$('hacode').placeholder=d.code_old?t('bitte neu eingeben und speichern','please enter and save again'):d.has_code?t('gesetzt, leer speichern zum Entfernen','set, save empty to remove'):t('kein Codewort','no code word')}
async function showHa(){if(!HA_ON)return;haRender(await (await api('/api/profile/homeassistant')).json());haMsg('')}
$('hasave').onclick=async()=>{haMsg(t('Prüfe die Verbindung …','Checking the connection …'));
  const r=await fetch('/api/profile/homeassistant',{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({url:$('haurl').value.trim(),token:$('hatoken').value.trim(),verify:!$('hanoverify').checked,agent:$('haagent').value.trim()})});
  const d=await r.json();if(!r.ok){haMsg(t('Nicht gespeichert: ','Not saved: ')+(d.detail||r.status),true);return}haRender(d);haMsg(t('Verbunden und gespeichert.','Connected and saved.'))};
$('hadel').onclick=async()=>{if(!confirm(t('Home Assistant trennen?','Disconnect Home Assistant?')))return;haRender(await (await api('/api/profile/homeassistant',{method:'DELETE'})).json());haMsg(t('Getrennt.','Disconnected.'))};
$('hacodesave').onclick=async()=>{const r=await fetch('/api/profile/homeassistant/code',{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({code:$('hacode').value})});
  const d=await r.json();if(!r.ok){haMsg(d.detail||r.status,true);return}haRender(d);haMsg(d.has_code?t('Codewort gespeichert.','Code word saved.'):t('Codewort entfernt.','Code word removed.'))};
$('hatrygo').onclick=async()=>{const text=$('hatry').value.trim();if(!text)return;haMsg(t('Frage Home Assistant …','Asking Home Assistant …'));
  const r=await fetch('/api/profile/homeassistant/test',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({text})});const d=await r.json();
  if(!r.ok){haMsg(d.detail||r.status,true);return}haMsg((d.targets&&d.targets.length?d.targets.join(', ')+': ':'')+d.answer,!d.ok)};
// Voice enrollment for speaker identification: three sentences, each recorded and sent as WAV.
const ENROLL=[['Der Herbstwind treibt bunte Blätter über die stille Straße, und irgendwo bellt ein Hund.','The autumn wind drives colourful leaves across the quiet street, and somewhere a dog barks.'],
  ['Kannst du mir bitte sagen, wie das Wetter morgen wird und ob ich einen Schirm brauche?','Could you please tell me what the weather will be like tomorrow and whether I need an umbrella?'],
  ['Zweiundvierzig Äpfel, sieben Birnen und ein Korb voller Pflaumen stehen auf dem Küchentisch.','Forty-two apples, seven pears and a basket full of plums are on the kitchen table.']];
const enr={i:-1,rec:null,parts:[],stream:null};
async function showVoice(){if(!SPK_ON){$('voicebox').style.display='none';return}$('voicebox').style.display='';
  const d=await (await api('/api/profile/voice')).json();
  $('voicestate').textContent=d.samples?t('Eingelernt: ','Enrolled: ')+d.samples+t(' Aufnahmen. Mehr Aufnahmen machen die Erkennung sicherer.',' recordings. More recordings make recognition more reliable.'):t('Noch nicht eingelernt.','Not enrolled yet.');
  $('voicedel').style.display=d.samples?'':'none';if(enr.i<0)$('voicego').textContent=d.samples?t('Weitere Aufnahmen','More recordings'):t('Stimme einlernen','Enroll voice')}
async function enrollStep(){
  if(enr.rec){const rec=enr.rec;enr.rec=null;await new Promise(r=>{rec.onstop=r;rec.stop()});
    $('voicemsg').textContent=t('Speichere …','Saving …');
    try{const fd=new FormData();fd.append('file',await toWav(new Blob(enr.parts,{type:rec.mimeType})),'voice.wav');
      await api('/api/profile/voice',{method:'POST',body:fd});$('voicemsg').textContent=''}
    catch(e){$('voicemsg').innerHTML=`<span class="err">${esc(e.message)}</span>`;enr.i--}
    await showVoice();if(enr.i>=ENROLL.length-1){endEnroll();$('voicemsg').textContent=t('Fertig.','Done.');return}}
  enr.i++;$('voicesay').style.display='';$('voicesay').textContent=t(...ENROLL[enr.i]);
  enr.parts=[];const mime=['audio/webm;codecs=opus','audio/webm','audio/mp4'].find(m=>MediaRecorder.isTypeSupported(m))||'';
  enr.rec=new MediaRecorder(enr.stream,mime?{mimeType:mime}:{});enr.rec.ondataavailable=e=>{if(e.data.size)enr.parts.push(e.data)};enr.rec.start();
  $('voicego').textContent=(enr.i<ENROLL.length-1?t('Weiter','Next'):t('Fertig','Finish'))+` (${enr.i+1}/${ENROLL.length})`;
  $('voicemsg').textContent=t('● Aufnahme läuft, lies den Satz vor.','● Recording, read the sentence aloud.')}
function endEnroll(){if(enr.rec){try{enr.rec.stop()}catch{}enr.rec=null}if(enr.stream){enr.stream.getTracks().forEach(x=>x.stop());enr.stream=null}
  enr.i=-1;$('voicesay').style.display='none';$('voicego').textContent=$('voicedel').style.display==='none'?t('Stimme einlernen','Enroll voice'):t('Weitere Aufnahmen','More recordings')}
$('voicego').onclick=async()=>{if(enr.i<0){
    if(!window.isSecureContext||!navigator.mediaDevices){$('voicemsg').innerHTML=`<span class="err">${t('Das Mikrofon braucht https.','The microphone needs https.')}</span>`;return}
    try{enr.stream=await navigator.mediaDevices.getUserMedia({audio:{echoCancellation:true,noiseSuppression:true,autoGainControl:true}})}
    catch(e){$('voicemsg').innerHTML=`<span class="err">${esc(e.message)}</span>`;return}}
  enrollStep()};
$('voicedel').onclick=async()=>{if(!confirm(t('Gespeicherte Stimme löschen?','Delete the stored voice?')))return;await api('/api/profile/voice',{method:'DELETE'});showVoice()};
$('docadd').onclick=()=>$('docfile').click();
$('docfile').onchange=async()=>{const files=[...$('docfile').files];$('docfile').value='';
  for(const f of files){const most=/\.pdf$/i.test(f.name)?(DOCINFO&&DOCINFO.max_mb||100):(DOCINFO&&DOCINFO.other_mb||20);
    if(f.size>most*1048576){$('docmsg').innerHTML=`<span class="err">${esc(f.name)}: ${t(`größer als ${most} MB`,`larger than ${most} MB`)}</span>`;continue}
    $('docmsg').textContent=t('Lade hoch: ','Uploading: ')+f.name+' …';
    try{const fd=new FormData();fd.append('file',f,f.name);const r=await (await api('/api/profile/docs',{method:'POST',body:fd})).json();
      $('docmsg').textContent=(r.state==='reading'?t('Wird gelesen: ','Being read: '):t('Hinzugefügt: ','Added: '))+r.name}
    catch(e){$('docmsg').innerHTML=`<span class="err">${esc(f.name)}: ${esc(e.message)}</span>`;}}
  showDocs()};
function showTidy(p){const b=$('tidybox');if(!p||!(p.merge.length+p.drop.length)){b.style.display='none';b.innerHTML='';return}
  b.style.display='';
  b.innerHTML=`<b>${t('Vorschlag zum Aufräumen','Cleanup proposal')}</b><ul>`+
    p.merge.map(m=>`<li>${t('Zusammenfassen','Merge')}: ${m.old.map(x=>'„'+esc(x)+'“').join(' + ')}<br>→ „${esc(m.text)}“</li>`).join('')+
    p.drop.map(x=>`<li>${t('Entfernen','Remove')}: „${esc(x.old)}“${x.why?` <small class="mut">(${esc(x.why)})</small>`:''}</li>`).join('')+
    `</ul><div class="row"><button class="b p" onclick="tidyDo('accept')">${t('Übernehmen','Apply')}</button><button class="b" onclick="tidyDo('reject')">${t('Verwerfen','Discard')}</button></div>`}
window.tidyDo=async what=>{$('factmsg').textContent=what==='check'?t('Der Assistent sieht sich dein Gedächtnis an …','The assistant is looking at your memory …'):'';
  try{const r=await (await api('/api/profile/memory/tidy',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({do:what})})).json();
    if(what==='check')$('factmsg').textContent=r.tidy?'':t('Nichts aufzuräumen.','Nothing to tidy up.');
    if(what==='accept')$('factmsg').textContent=t('Aufgeräumt.','Tidied up.');
    await showFacts()}
  catch(e){$('factmsg').innerHTML=`<span class="err">${esc(e.message)}</span>`}};
$('facttidy').onclick=()=>tidyDo('check');
window.forgetFact=async id=>{await api('/api/profile/memory/'+encodeURIComponent(id),{method:'DELETE'});showFacts()};
async function openMe(tab){$('profmsg').textContent='';$('profmodal').style.display='grid';
  const tabs=meTabs(),list=tab==='list'&&PHONE.matches&&tabs.length>1;ptab(tabs.includes(tab)?tab:tabs.includes(meLast)?meLast:tabs[0],!list);
  $('profhead').textContent=PROFILE?PROFILE.name:GATE?t('Anmelden','Sign in'):t('Gast','Guest');
  $('setscope').textContent=GATE?'':PROFILE?t('Einstellungen gelten auf jedem Gerät dieses Profils; „Hey Spark“ stellt jedes Gerät selbst ein.','Settings apply on every device of this profile; "Hey Spark" is set per device.'):isGuest()?t('Als Gast gelten die Vorgaben des Admins. Mit einem Profil kannst du Einstellungen ändern, und der Assistent merkt sich Dinge nur für dich.','As a guest the admin\'s defaults apply. With a profile you can change settings, and the assistant remembers things just for you.'):t('Als Gast gelten die Einstellungen nur in diesem Browser. Mit einem Profil merkt sich der Assistent Dinge nur für dich.','As a guest the settings apply only in this browser. With a profile the assistant remembers things just for you.');
  $('proflogout').style.display=PROFILE?'':'none';$('profclose').style.display=GATE?'none':'';
  if(!GATE&&!isGuest())renderSet($('setform'),S,saveSet);
  if(PROFILE){try{await showFacts();await showDocs();await showVoice();await showCal();await showMail();await showMailTidy().catch(()=>{});await showHa();await showSecurity();await showToolLog();await showPro().catch(()=>{});await showExtras();showRoom();await showPush().catch(()=>{});showOver()}catch{setProfile(null);openMe('loginbox')}return}
  $('profpin').value='';if(tab==='loginbox')setTimeout(()=>$($('profuser').value?'profpin':'profuser').focus(),50)}
window.openMe=openMe;
$('profbtn').onclick=()=>openMe(PHONE.matches?'list':meLast);
$('navme').onclick=()=>openMe(meLast);   // phones: the list of pages; else the last page (first time: Überblick)
$('profuser').onkeydown=e=>{if(e.key==='Enter')$('profpin').focus()};
$('profpin').onkeydown=e=>{if(e.key==='Enter')$('proflogin').click()};
$('profcode').onkeydown=e=>{if(e.key==='Enter')$('proflogin').click()};
$('proflogin').onclick=async()=>{try{const r=await (await api('/api/profile/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name:$('profuser').value,pin:$('profpin').value,code:$('profcode').value,trust:$('proftrust').checked})})).json();
    if(r.code){$('profcodebox').style.display='';$('profmsg').textContent='';$('profcode').focus();return}  // second step: code next
    $('profcode').value='';$('profcodebox').style.display='none';
    if(GATE){location.reload();return}
    const who=await (await fetch('/api/whoami')).json();setProfile(who.profile);closeProf()}
  catch(e){$('profmsg').textContent=/too many/.test(e.message)?t('Zu viele falsche Versuche. Bitte später noch einmal (','Too many wrong attempts. Please try again later (')+(e.message.match(/in (.+)$/)||['',''])[1]+').':/wrong code/.test(e.message)?t('Code falsch.','Wrong code.'):t('Name oder PIN falsch.','Wrong name or PIN.')}};
$('proflogout').onclick=async()=>{await fetch('/api/profile/logout',{method:'POST'});if(!PUBLIC&&!ADMIN){location.reload();return}setProfile(null);closeProf()};
$('factclear').onclick=async()=>{if(!confirm(t('Alles vergessen, was sich der Assistent über dich gemerkt hat?','Forget everything the assistant remembered about you?')))return;
  await api('/api/profile/memory',{method:'DELETE'});showFacts()};
// ---------------------------------------------------------------- conversation settings
let ALLOW={};
const SETF=[
  {g:t('Zuhören','Listening'),k:'hands',type:'bool',l:t('Freihändig','Hands-free'),h:t('Nach der Antwort automatisch wieder zuhören.','Listen again automatically after each answer.')},
  {k:'follow',type:'sel',prof:1,need:'follow',l:t('Rückfrage ohne Weckwort','Follow-up without wake word'),h:t('Nach der Antwort auf eine gesprochene Frage hört der Assistent noch kurz zu, z. B. für „Und morgen?“. Danach braucht es wieder „Hey Spark“ oder „Sprechen“.','After answering a spoken question the assistant keeps listening briefly, e.g. for "And tomorrow?". After that it needs "Hey Spark" or "Speak" again.'),o:[['0',t('aus','off')],['4',t('4 Sekunden','4 seconds')],['6',t('6 Sekunden','6 seconds')],['8',t('8 Sekunden','8 seconds')],['10',t('10 Sekunden','10 seconds')]]},
  {k:'echo',type:'bool',prof:1,need:'echo',l:t('Eigene Stimme überhören','Ignore my own voice'),h:t('Hört dieses Gerät, wie ein anderes Gerät gerade antwortet (Lautsprecher, iPhone), nimmt der Assistent das nicht als Frage.','When this device hears another device answering (speaker, iPhone), the assistant does not take it as a question.')},
  {k:'auto',type:'bool',l:t('Bei Stille beenden','Stop on silence'),h:t('Die Aufnahme endet von selbst, wenn du aufhörst zu sprechen.','Recording ends by itself when you stop talking.')},
  {k:'turn',type:'bool',l:t('Natürlicher Sprecherwechsel','Natural turn-taking'),h:t('Erkennt am Satz, ob du fertig bist: Ein fertiger Satz wird sofort beantwortet, bei „und …“, „weil …“ oder „ähm“ wartet der Assistent länger.','Tells from the sentence whether you are done: a finished sentence is answered at once, after "and …", "because …" or "um" the assistant waits longer.')},
  {k:'live',type:'bool',l:t('Live-Transkript','Live transcript'),h:t('Text schon beim Sprechen zeigen; die Antwort kommt etwas früher.','Show the text while you speak; the answer comes a little sooner.')},
  {k:'barge',type:'bool',l:t('Ins Wort fallen','Barge in'),h:t('Losreden unterbricht die Antwort (am besten mit Kopfhörer).','Start talking to interrupt the answer (best with headphones).')},
  {k:'barge_level',type:'sel',l:t('Empfindlichkeit','Sensitivity'),h:t('Wie leicht Geräusche die Antwort unterbrechen.','How easily sounds interrupt the answer.'),o:[['low',t('gering','low')],['mid',t('mittel','medium')],['high',t('hoch','high')]]},
  {g:t('Antwort','Answer'),k:'voice',type:'voice',l:t('Stimme','Voice'),h:t('Leer = Standardstimme des Servers.','Empty = the server\'s default voice.')},
  {k:'speed',type:'range',l:t('Sprechtempo','Speaking rate'),h:t('Schneller oder langsamer, ohne die Stimmlage zu ändern.','Faster or slower without changing the pitch.'),min:0.7,max:1.4,step:0.05},
  {k:'length',type:'sel',l:t('Antwortlänge','Answer length'),h:t('Wie ausführlich der Assistent antwortet.','How detailed the assistant answers.'),o:[['short',t('kurz','short')],['normal',t('normal','normal')],['long',t('ausführlich','detailed')]]},
  {k:'learn',type:'bool',prof:1,l:t('Aus Gesprächen lernen','Learn from conversations'),h:t('Nach einem Gespräch merkt sich der Assistent wenige dauerhafte Dinge über dich. Du siehst und löschst sie unter Ich.','After a conversation the assistant remembers a few lasting things about you. You can see and delete them under the Me.')},
  {k:'tool_think',type:'bool',prof:1,need:'tool_think',l:t('Bei Werkzeugen nachdenken','Think before using tools'),h:t('Bevor der Assistent nachsieht (Kalender, Mails, Suche …), denkt er kurz nach, welches Werkzeug passt. Zuverlässiger, aber die Antwort beginnt etwas später.','Before the assistant looks something up (calendar, mail, search …) it thinks briefly about which tool fits. More reliable, but the answer starts a little later.')},
  {k:'route',type:'bool',prof:1,need:'route',l:t('Gezielte Werkzeugwahl','Targeted tool choice'),h:t('Das Panel erkennt an festen Regeln, worum es dir geht (Licht, Termin, Wetter …), und zeigt dem Sprachmodell nur die passenden Werkzeuge. Weniger Fehlgriffe, etwas schneller. Eine neue Bitte in eigenen Worten hebt die Sperre nach einer Web- oder Bild-Antwort auf; „Setz das auf die Liste“ bleibt gesperrt.','The panel recognizes by fixed rules what you are after (light, appointment, weather …) and shows the language model only the matching tools. Fewer wrong picks, a little faster. A new request in your own words lifts the lock after a web or picture answer; "Put that on the list" stays locked.')},
  {k:'images_on',type:'bool',prof:1,need:'images',l:t('Bilder an den Assistenten','Pictures to the assistant'),h:t('Im Assistenten ein Foto anhängen (Knopf, Einfügen oder Hineinziehen) und dazu fragen. Das Sprachmodell auf dem Spark sieht es sich an; das Bild bleibt nur im Arbeitsspeicher, ohne Ort und Kameradaten. In dieser Antwort schaltet und speichert der Assistent nichts.','Attach a photo in the assistant (button, paste or drop) and ask about it. The language model on the Spark looks at it; the picture stays in memory only, without location or camera data. In this answer the assistant switches and stores nothing.')},
  {k:'fix_learn',type:'bool',prof:1,need:'fix_learn',l:t('Aus Korrekturen lernen','Learn from corrections'),h:t('Korrigierst du den Assistenten, fragt er, ob er sich einen kurzen Satz dazu merken soll. Gespeichert wird erst nach deinem „Ja“.','When you correct the assistant, it asks whether to remember a short sentence about it. It is stored only after your "yes".')},
  {k:'style',type:'text',prof:1,need:'style',max:500,l:t('So soll der Assistent mit mir reden','How the assistant should talk to me'),h:t('In eigenen Worten, z. B. „Sprich mich mit Dominik an und antworte locker.“ Ändert nur den Ton, nie die Regeln. Leer = aus.','In your own words, e.g. "Call me Dominik and answer casually." Changes the tone only, never the rules. Empty = off.')},
  {k:'roles_on',type:'bool',prof:1,need:'roles',l:t('Rollen per Sprache','Roles by voice'),h:t('„Sei jetzt der Butler“ wechselt in eine deiner Rollen, „Sei wieder normal“ zurück, „Welche Rollen hast du?“ nennt sie. Gilt auf allen deinen Geräten, bis du wechselst.','"Be the butler now" switches to one of your roles, "Be normal again" back, "Which roles do you have?" lists them. Applies on all your devices until you switch.')},
  {k:'roles',type:'text',prof:1,need:'roles',max:1500,l:t('Meine Rollen','My roles'),h:t('Eine Rolle pro Zeile, höchstens 8: „Name: wie der Assistent dann antwortet“, z. B. „Butler: höflich, trocken, mit britischem Understatement“. Ändert nur den Ton, nie die Regeln.','One role per line, at most 8: "Name: how the assistant then answers", e.g. "Butler: polite, dry, with British understatement". Changes the tone only, never the rules.')},
  {k:'wiki_on',type:'bool',prof:1,need:'wiki',l:t('Wikipedia direkt','Wikipedia straight away'),h:t('Bei Wissensfragen („Was ist …?“, „Wer war …?“) liest der Assistent die Einleitung des passenden Wikipedia-Artikels statt im Web zu suchen. Die Antwort beginnt meist früher. Nur die Suchwörter gehen an Wikipedia.','For knowledge questions ("What is …?", "Who was …?") the assistant reads the intro of the matching Wikipedia article instead of searching the web. The answer usually starts sooner. Only the search words go to Wikipedia.')},
  {k:'kiwix_on',type:'bool',prof:1,need:'kiwix',l:t('Eigenes Archiv (Kiwix)','Own archive (Kiwix)'),h:t('Der Assistent schlägt zuerst im Kiwix-Archiv des Hauses nach (Wikipedia, Reiseführer, Anleitungen). Geht auch ohne Internet; fällt die Websuche aus, antwortet er aus dem Archiv und sagt das dazu.','The assistant looks things up in the household\'s Kiwix archive first (Wikipedia, travel guides, manuals). Works without internet; if the web search fails, it answers from the archive and says so.')},
  {g:t('Anzeige','Display'),k:'daily',type:'bool',l:t('Jeden Tag neues Gespräch','New conversation every day'),h:t('Am nächsten Tag beginnt automatisch ein neues Gespräch; die alten bleiben im Verlauf.','The next day a new conversation starts by itself; older ones stay in the history.')},
  {k:'timing',type:'bool',l:t('Zeiten anzeigen','Show timings'),h:t('Wie lange Erkennung, Modell und erster Ton gebraucht haben.','How long recognition, model and first audio took.')},
  {g:t('Datenschutz','Privacy'),k:'trace_name',type:'bool',prof:1,need:'trace',l:t('Mein Name im Anfragen-Log','My name in the request log'),h:t('Unter Zustand → Logs → Anfragen sieht der Admin, welchen Weg deine Anfragen nehmen (Werkzeuge, Zeiten), nie was du fragst oder was die Antwort war. Mit diesem Schalter stehen dort dein Name und dein Gerät, sonst nur „Profil“. Ändern nur in deiner eigenen Anmeldung im Browser.','Under State → Logs → Requests the admin sees which way your requests take (tools, times), never what you ask or what the answer was. With this switch your name and device show there, otherwise only "Profile". Can only be changed in your own browser login.')}];
{let g;SETF.forEach(f=>{g=f.g||g;f.grp=g})}
// asked again each time the settings open: an empty answer (TTS still loading) must not stick for the page's life,
// and the admin's list is not the profile's
async function voiceList(admin){if(!PROFILE&&!admin)return [];try{const r=await fetch(admin?'/api/tts/voices':'/api/assistant/voices');
  return r.ok?((await r.json()).voices||[]).filter(x=>typeof x==='string'):[]}catch{return []}}
// Builds the settings rows into el; onchange(key, value) after each change. Returns a getter.
async function renderSet(el,vals,onchange){const admin=!onchange,voices=await voiceList(admin);const v={...vals};
  const fields=SETF.filter(f=>(!(f.k==='voice'||f.prof)||admin||PROFILE)&&(!f.need||(!admin&&ALLOW[f.need])));   // guests: default voice, nothing learned; need: only when the admin allows it
  let prev;el.innerHTML=fields.map(f=>{let ctl;const id='set_'+el.id+'_'+f.k;
    if(f.type==='bool')ctl=`<label class="tgl"><input type="checkbox" id="${id}"${v[f.k]?' checked':''}><i></i></label>`;
    else if(f.type==='sel')ctl=`<select id="${id}">${f.o.map(([a,b])=>`<option value="${a}"${v[f.k]===a?' selected':''}>${esc(b)}</option>`).join('')}</select>`;
    else if(f.type==='text')ctl=`<textarea id="${id}" rows="3" maxlength="${f.max}">${esc(v[f.k]||'')}</textarea>`;
    else if(f.type==='voice')ctl=(voices.length?'':'<div>')+`<select id="${id}"><option value="">${t('Standard','Default')}</option>${[...new Set([...voices,...(v.voice?[v.voice]:[])])].map(x=>`<option${x===v.voice?' selected':''}>${esc(x)}</option>`).join('')}</select>`+(voices.length?'':`<div class="fh">${t('Die Sprachausgabe nennt gerade keine Stimmen (startet noch?). Später erneut öffnen.','The speech output lists no voices right now (still starting?). Open again later.')}</div></div>`);
    else ctl=`<input type="range" id="${id}" min="${f.min}" max="${f.max}" step="${f.step}" value="${v[f.k]}"><output id="${id}_o">${Number(v[f.k]).toFixed(2)}×</output>`;
    const head=f.grp!==prev;prev=f.grp;
    return (head?`${f===fields[0]?'':'</div>'}<div class="setpane${f===fields[0]||admin?' on':''}" data-g="${esc(f.grp)}">${admin?`<h3 class="sec">${esc(f.grp)}</h3>`:''}`:'')+`<div class="setrow"><div class="lbl"><b>${esc(f.l)}</b><span>${esc(f.h)}</span></div>${ctl}</div>`}).join('')+'</div>';
  // one group at a time, so the window stays short; the admin page (Vorgaben) shows all groups as sections
  const groups=[...new Set(fields.map(f=>f.grp))],bar=document.createElement('div');bar.className='ptabs';
  if(!admin){
  bar.innerHTML=groups.map((g,i)=>`<button type="button"${i?'':' class="on"'}>${esc(g)}</button>`).join('');el.prepend(bar);
  bar.querySelectorAll('button').forEach((b,i)=>b.onclick=()=>{bar.querySelectorAll('button').forEach(x=>x.classList.toggle('on',x===b));
    el.querySelectorAll('.setpane').forEach(x=>x.classList.toggle('on',x.dataset.g===groups[i]))})}
  fields.forEach(f=>{const e=$('set_'+el.id+'_'+f.k);e.oninput=e.onchange=ev=>{
    const val=f.type==='bool'?e.checked:f.type==='range'?Number(e.value):f.type==='text'?e.value.replace(/<<<|>>>|[\x00-\x09\x0b-\x1f\x7f]/g,'').slice(0,f.max):e.value;
    if(f.type==='text'&&ev.type==='input')return;   // saved when the field is left
    if(f.type==='range')$(e.id+'_o').textContent=val.toFixed(2)+'×';
    if(v[f.k]===val||(f.type==='range'&&ev.type==='input'))return;v[f.k]=val;onchange&&onchange(f.k,val)}});
  return()=>({...v})}
function applySet(){$('chathands').checked=!!S.hands;$('chattiming').style.display=S.timing?'':'none';if(typeof picsShow==='function')picsShow();if(typeof msgBar==='function')msgBar()}
async function loadSettings(){let d=null;try{d=await (await fetch('/api/profile/settings')).json()}catch{}
  SDEF={...SDEF,...(d&&d.defaults||{})};S={...SDEF,...(d&&d.settings||{})};ALLOW=(d&&d.allow)||{};
  if(!PROFILE&&!isGuest()){try{S={...S,...JSON.parse(localStorage.getItem('chatset')||'{}')}}catch{}}
  applySet();if(!S.daily&&!chat.cid&&!chat.msgs.length)openConvo((convos.load()[0]||{}).id||null)}
let setTimer=null;
function saveSet(k,val){if(isGuest())return;S[k]=val;applySet();
  if(!PROFILE){try{const o=JSON.parse(localStorage.getItem('chatset')||'{}');o[k]=val;localStorage.setItem('chatset',JSON.stringify(o))}catch{}return}
  clearTimeout(setTimer);setTimer=setTimeout(()=>api('/api/profile/settings',{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify(S)}).catch(()=>{}),300)}
$('chathands').onchange=()=>saveSet('hands',$('chathands').checked);
const openSet=()=>openMe('setbox');   // the settings icon below the face: straight to the conversation settings
$('chatset').onclick=openSet;
$('setreset').onclick=async()=>{for(const k of Object.keys(SDEF))S[k]=SDEF[k];
  if(PROFILE)await api('/api/profile/settings',{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify(SDEF)}).catch(()=>{});
  else try{localStorage.removeItem('chatset')}catch{}
  applySet();renderSet($('setform'),S,saveSet)};
// ---------------------------------------------------------------- security: devices and logins
const when=s=>s?new Date(s*1000).toLocaleString([], {dateStyle:'short',timeStyle:'short'}):t('noch nie','never');
async function showSecurity(){if(typeof coadmMe==='function')coadmMe();const d=await (await api('/api/profile/security')).json();secRender(d.devices);mfaShow('profmfa','/api/profile/mfa');secSessions();
  const ev={profile_login:t('Anmeldung','Sign-in'),profile_login_failed:t('Falsche PIN','Wrong PIN'),profile_logout_all:t('Überall abgemeldet','Logged out everywhere'),profile_code_failed:t('Falscher Code','Wrong code'),profile_mfa_on:t('Zweiter Schritt an','Second step on'),profile_mfa_off:t('Zweiter Schritt aus','Second step off'),profile_mfa_reset:t('Zweiter Schritt vom Admin zurückgesetzt','Second step reset by the admin'),profile_device_removed:t('Gerät gesperrt','Device blocked'),profile_session_end:t('Browser abgemeldet','Browser signed out')};
  $('secev').innerHTML=d.events.map(e=>`<li><span>${esc(ev[e.event]||e.event)} <small class="mut">${when(e.t)} · ${esc(e.ip||'')}</small></span></li>`).join('')||`<li class="mut">–</li>`}
function secRender(devs){$('secdev').innerHTML=devs.map(x=>`<li><span>${esc(x.name)}<br><small class="mut">${x.speaker?t('Lautsprecher, verwaltet unter Ich → Lautsprecher · ','Speaker, managed under Me → Speakers · '):''}${t('zuletzt','last used')}: ${x.last?when(x.last.t)+' · '+esc(x.last.ip||''):t('noch nie','never')}</small></span><button class="b" onclick="secDrop('${escq(x.id)}','${escq(x.name)}','${escq(x.speaker?'1':'')}')">${t('Sperren','Block')}</button></li>`).join('')||`<li class="mut">${t('Keine Geräte mit Schlüssel.','No devices with a key.')}</li>`}
// every signed-in browser of this profile, with its short name and last use; "Abmelden" ends just that one (V01.0.262)
async function secSessions(){const box=$('secsess');let d={sessions:[],days:30};try{d=await (await api('/api/profile/sessions')).json()}catch{}
  $('secdays').textContent=d.days;box.textContent='';
  for(const x of d.sessions){const li=document.createElement('li'),sp=document.createElement('span'),sm=document.createElement('small');
    sp.textContent=x.agent+(x.this?t(' (dieser Browser)',' (this browser)'):'');sm.className='mut';sm.textContent=t('angemeldet ','signed in ')+when(x.first)+' · '+t('zuletzt ','last used ')+when(x.last);
    sp.append(document.createElement('br'),sm);li.appendChild(sp);
    if(!x.this){const b=document.createElement('button');b.type='button';b.className='b';b.textContent=t('Abmelden','Sign out');
      b.onclick=async()=>{await api('/api/profile/sessions/'+encodeURIComponent(x.id),{method:'DELETE'}).catch(()=>{});showSecurity()};li.appendChild(b)}
    box.appendChild(li)}
  if(!d.sessions.length)box.innerHTML=`<li class="mut">${t('Ältere Anmeldungen erscheinen nach ihrer nächsten Nutzung.','Older sign-ins appear after their next use.')}</li>`}
window.secDrop=async(id,n,spk)=>{if(!confirm(t('Gerät „','Block device "')+n+t('“ sperren? Sein Schlüssel gilt dann nicht mehr.','"? Its key stops working.')+(spk?t(' Der Lautsprecher muss danach neu eingerichtet werden.',' The speaker then has to be set up again.'):'')))return;
  await api('/api/profile/devices/'+encodeURIComponent(id),{method:'DELETE'});showSecurity()};
$('seclogoutall').onclick=async()=>{if(!confirm(t('Dein Profil in allen anderen Browsern abmelden?','Log your profile out in all other browsers?')))return;
  try{await api('/api/profile/logout-all',{method:'POST'});$('secmsg').textContent=t('Erledigt.','Done.');showSecurity()}catch(e){$('secmsg').textContent=e.message}};
// ---------------------------------------------------------------- reminders as push notifications
// Only with https and a trusted certificate (e.g. behind a reverse proxy); iPhone: from the home screen.
const pushOk=()=>'serviceWorker' in navigator&&'PushManager' in window&&window.isSecureContext;
async function pushSub(){try{const r=await navigator.serviceWorker.getRegistration();return r&&await r.pushManager.getSubscription()}catch{return null}}
async function showPush(){const box=$('pushbox');box.style.display=PROFILE&&REM_ON?'':'none';if(!PROFILE||!REM_ON)return;
  $('briefat').value=S.briefing_at||'';
  if(!pushOk()){$('pushstate').textContent=/iPhone|iPad/.test(navigator.userAgent)&&!navigator.standalone?t('Auf dem iPhone: die Seite über „Teilen → Zum Home-Bildschirm“ als App anlegen und dort einschalten.','On an iPhone: add the page to the home screen ("Share → Add to Home Screen") and switch it on there.'):t('Geht nur über https mit gültigem Zertifikat (z. B. hinter deinem Proxy). Hier klingeln Erinnerungen, solange die Seite offen ist.','Needs https with a valid certificate (e.g. behind your proxy). Here reminders ring while the page is open.');
    $('pushgo').style.display=$('pushoff').style.display='none';return}
  const s=await pushSub();$('pushgo').style.display=s?'none':'';$('pushoff').style.display=s?'':'none';
  $('pushstate').textContent=s?t('An: Erinnerungen kommen als Mitteilung, auch wenn die Seite zu ist.','On: reminders arrive as notifications, also when the page is closed.'):t('Aus: Erinnerungen klingeln nur, solange die Seite offen ist.','Off: reminders ring only while the page is open.')}
$('briefat').onchange=()=>{saveSet('tz',TZ());saveSet('briefing_at',$('briefat').value||'')};
$('briefoff').onclick=()=>{$('briefat').value='';saveSet('briefing_at','')};
$('pushgo').onclick=async()=>{try{if(await Notification.requestPermission()!=='granted'){$('pushstate').textContent=t('Mitteilungen sind für diese Seite nicht erlaubt (Browser- oder Systemeinstellungen).','Notifications are not allowed for this page (browser or system settings).');return}
    const reg=await navigator.serviceWorker.register(SW_URL);await navigator.serviceWorker.ready;
    const {key}=await (await api('/api/profile/push')).json();
    const raw=Uint8Array.from(atob(key.replace(/-/g,'+').replace(/_/g,'/')+'='.repeat((4-key.length%4)%4)),c=>c.charCodeAt(0));
    const sub=await reg.pushManager.subscribe({userVisibleOnly:true,applicationServerKey:raw});
    await api('/api/profile/push',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({subscription:sub.toJSON(),name:navigator.userAgent.slice(0,60)})});showPush()}
  catch(e){$('pushstate').textContent=t('Hat nicht geklappt: ','Did not work: ')+e.message}};
$('pushoff').onclick=async()=>{const s=await pushSub();if(s){try{await api('/api/profile/push',{method:'DELETE',headers:{'Content-Type':'application/json'},body:JSON.stringify({endpoint:s.endpoint})})}catch{}await s.unsubscribe().catch(()=>{})}showPush()};
// ---------------------------------------------------------------- tool log (own turns, a few days)
async function showToolLog(){const d=await (await api('/api/profile/toollog')).json();$('logdays').textContent=d.days;
  $('loglist').innerHTML=d.items.map(x=>`<li style="display:block"><small class="mut">${esc(new Date(x.t).toLocaleString())}</small><br><b>${esc(x.q)}</b>`+
    (x.calls.length?x.calls.map(c=>`<details><summary>🔧 ${esc(c.name)} <small class="mut">${esc(c.args)}</small></summary><pre style="white-space:pre-wrap;margin:4px 0">${esc(c.result)}</pre></details>`
      +(c.name==='Korrektur'&&c.args?`<button class="b" type="button" data-qcase="${x.t}">${t('Frage als Testfall an den Admin','Send the question to the admin as a test case')}</button>`:'')).join('')
      :`<div class="mut">${t('kein Werkzeug','no tool')}</div>`)+
    `<div>→ ${esc(x.answer||'–')}</div></li>`).join('')||`<li class="mut">${t('Noch keine Einträge.','No entries yet.')}</li>`}
$('logreload').onclick=()=>showToolLog();
// a corrected question as a quality-test case (quality.py): the panel takes the text from the log itself
$('loglist').addEventListener('click',async e=>{const b=e.target.closest('[data-qcase]');if(!b)return;b.disabled=true;
  try{await api('/api/profile/quality-case',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({t:Number(b.dataset.qcase)})});b.textContent=t('Übergeben','Handed over')}
  catch(err){b.textContent=err.message;b.disabled=false}});
$('logclear').onclick=async()=>{if(!confirm(t('Protokoll leeren?','Clear the log?')))return;await api('/api/profile/toollog',{method:'DELETE'});showToolLog()};
