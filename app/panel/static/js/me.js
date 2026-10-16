// The "Ich" window: profile login, the profile's own pages and the conversation settings.
// ---------------------------------------------------------------- profile of this browser
const ME_LOAD={p:null,next:null};   // Ich's boxes: the load running now and the one queued after it (openMe)
function setProfile(p){const changed=(p&&p.id)!==(PROFILE&&PROFILE.id);PROFILE=p||null;
  $('profname').textContent=PROFILE?PROFILE.name:t('Gast','Guest');
  if(changed){stopListening(true);stopAnswer();syncStop();if(!PROFILE)offlineWipe(true);convos.cache=[];openConvo(null);convos.sync().then(()=>{if(!chat.msgs.length)openConvo(latestConvo())})}
  loadSettings();rem.load();if(window.room)room.show();guestLock()}
// Guests change no settings and cannot use room mode: they get the admin's defaults (the admin's own browser may).
const isGuest=()=>!PROFILE&&!ADMIN;
// Without a profile the assistant only answers, without any tool (Dominik 2026-10-13); the note says so with the way in
function guestNote(){const n=$('guestnote');if(!n)return;n.hidden=!!PROFILE;if(PROFILE)return;
  n.textContent=t('Ohne Profil: nur Fragen und Antworten, ohne Werkzeuge (keine Websuche, keine Timer, kein Gedächtnis). ','Without a profile: questions and answers only, no tools (no web search, no timers, no memory). ');
  const b=document.createElement('button');b.type='button';b.className='mlink';b.textContent=t('Anmelden','Sign in');
  b.onclick=()=>{if(typeof openMe==='function')openMe('loginbox')};n.appendChild(b)}
function guestLock(){guestNote();const g=isGuest();['chathands','chatwake'].forEach(id=>{const l=$(id).closest('label');if(l)l.style.display=g?'none':''});
  if(g)stopWake();else if($('chatwake').checked&&!wake.on)startWake()}   // "Hey Spark" only for profiles (and the admin)
window.closeProf=()=>{$('profmodal').style.display='none';endEnroll()};
ON.closeProf=()=>closeProf();
// Ich → Gedächtnis (ich-aufraeumen/plan.md, Paket 4a): search and filters above, one row per fact with its date,
// "Ändern" (own wording, no model) and "Löschen"; "Auswählen" removes several at once; "Alles vergessen" sits in the
// danger zone below. The page scrolls, the list shows the first entries and "Weitere … zeigen".
// Gedächtnis prüfen (gedaechtnis.py, plan gedaechtnis-pruefen): with the switches on every row shows its mark
// (bestätigt, gelernt, veraltet?, Widerspruch) set by the panel's fixed rules; a click opens where the fact came from,
// why it is marked and "Stimmt noch". Nothing is deleted by the rules.
let FACTS=[],FQ='',FF='all',FSEL=null,FMORE=false,FEDIT=null,FCHECK=false,FMONTHS=6,FOPEN=null,FTOP=null;
async function showFacts(){const r=await api('/api/profile/memory');const d=await r.json();
  $('profhead').textContent=d.profile.name;showTidy(d.tidy);FACTS=d.facts||[];FCHECK=!!d.check;FMONTHS=d.months||6;FTOP=d.topics||null;
  if(!FCHECK&&['ok','learned','stale'].includes(FF))FF='all';factDraw()}
const fdate=x=>x?new Date(x*1000).toLocaleDateString(L==='en'?'en-GB':'de-DE',{day:'2-digit',month:'2-digit',year:'2-digit'}):'';
const FMARK={ok:['ok',t('bestätigt','confirmed')],learned:['',t('gelernt','learned')],stale:['warn',t('veraltet?','outdated?')],contra:['bad',t('Widerspruch','contradiction')]};
const FSRC={said:t('von dir im Gespräch','from you in a conversation'),fix:t('aus deiner Korrektur','from your correction'),auto:t('automatisch gelernt','learned automatically'),
  hand:t('von dir hier geändert','changed by you here'),tidy:t('aus dem Aufräumen','from tidying up')};
const fstale=f=>f.mark==='stale'||f.mark==='contra';
function factWhy(f){const by=f.by&&FACTS.find(x=>x.id===f.by);
  return f.rule==='datum'?t('Das genannte Datum ist vorbei.','The date it names has passed.'):
    f.rule==='zeitwort'?t('Es klingt nach „gerade“ oder „nächste Woche“ und ist schon älter.','It sounds like "right now" or "next week" and is older than that.'):
    f.rule==='alt'?t(`Automatisch gelernt und seit mehr als ${FMONTHS} Monaten nicht bestätigt.`,`Learned automatically and not confirmed for more than ${FMONTHS} months.`):
    f.rule==='widerspruch'?t('Ein neuerer Eintrag sagt etwas anderes','A newer entry says something else')+(by?': „'+by.text+'“':'.'):''}
const FWHY={fix:t('Korrektur im Gespräch','correction in a conversation'),nachfrage:t('Nachfrage im Gespräch','question in a conversation'),hand:t('von dir geändert','changed by you'),zurueck:t('zurückgeholt','brought back')};
function factDetail(f){const E=icEl,d=E('div','ic-row factdet');const m=E('div','ic-rmid');
  if(fstale(f)){const w=E('div','factwhy');w.textContent='⚑ '+factWhy(f)+' '+t('Der Assistent nennt es nur vorsichtig, nie als Tatsache.','The assistant only mentions it carefully, never as a fact.');m.appendChild(w)}
  const dl=E('dl','ld-facts');const add=(k,v)=>{dl.append(E('dt','',k));const dd=E('dd');if(typeof v==='string')dd.textContent=v;else dd.appendChild(v);dl.appendChild(dd)};
  const known=f.convo&&typeof convos!=='undefined'&&convos.load().some(c=>c.id===f.convo);
  let from=FSRC[f.src]||FSRC.said;
  if(f.convo){if(known){const a=icLink(t('Gespräch öffnen','Open the conversation'),()=>{closeProf();openConvo(f.convo,true)});const sp=E('span','',from+' · ');sp.appendChild(a);add(t('Woher','Where from'),sp)}
    else add(t('Woher','Where from'),from+' · '+t('Gespräch nicht mehr da','conversation gone'))}
  else add(t('Woher','Where from'),from);
  add(t('Gemerkt','Remembered'),fdate(f.created)||'–');add(t('Bestätigt','Confirmed'),f.confirmed?fdate(f.confirmed):t('nie','never'));
  add(t('Beim Antworten','When answering'),fstale(f)?t('nur als „unsicher, nicht als Tatsache nennen“','only as "unsure, never say it as a fact"'):f.mark==='ok'?t('als sicher','as sure'):t('als „gelernt, nicht bestätigt“','as "learned, not confirmed"'));
  m.appendChild(dl);
  const prev=(f.prev||[]).filter(p=>p&&p.text);if(prev.length){m.appendChild(E('div','factprevh',t('Frühere Fassungen','Earlier versions')));
    prev.forEach((p,i)=>{const v=E('div','factprev');const tx=E('span','',p.text);const why=E('small','',' · '+(FWHY[p.why]||'')+(p.until?' · '+t('bis ','until ')+fdate(p.until):''));
      const b=E('button','b',t('Zurückholen','Bring back'));b.type='button';b.onclick=async()=>{b.disabled=true;
        try{const x=await (await api('/api/profile/memory/'+encodeURIComponent(f.id)+'/restore',xjson('POST',{i}))).json();FACTS=x.facts;factDraw()}catch(e){b.disabled=false;$('factmsg').textContent=e.message}};
      v.append(tx,why,b);m.appendChild(v)})}
  if(FTOP){const sel=document.createElement('select');sel.className='factopic';sel.setAttribute('aria-label',t('Thema','Topic'));
    if(!FTOP[f.topic]){const o=document.createElement('option');o.value='';o.textContent=t('Noch ohne Thema','No topic yet');sel.appendChild(o)}
    Object.entries(FTOP).forEach(([k,v])=>{const o=document.createElement('option');o.value=k;o.textContent=t(v[0],v[1]);if(f.topic===k)o.selected=true;sel.appendChild(o)});
    sel.onchange=async()=>{if(!sel.value)return;sel.disabled=true;try{const x=await (await api('/api/profile/memory/'+encodeURIComponent(f.id)+'/topic',xjson('POST',{topic:sel.value}))).json();FACTS=x.facts;factDraw()}catch(e){sel.disabled=false;$('factmsg').textContent=e.message}};
    const lb=E('div','facttopic');lb.append(E('span','',t('Thema','Topic')+(f.topic_by==='hand'?'':' · '+t('vom Sprachmodell vorgeschlagen, änderbar','suggested by the language model, you can change it'))),sel);m.appendChild(lb)}
  const row=E('div','row');
  if(f.mark!=='ok'){const ok=E('button','b p',t('✓ Stimmt noch','✓ Still right'));ok.type='button';ok.onclick=async()=>{ok.disabled=true;
    try{const x=await (await api('/api/profile/memory/'+encodeURIComponent(f.id)+'/confirm',xjson('POST',{}))).json();FACTS=x.facts;factDraw()}catch(e){ok.disabled=false;$('factmsg').textContent=e.message}};row.appendChild(ok)}
  const ch=E('button','b',t('✎ Ändern','✎ Change'));ch.type='button';ch.onclick=()=>{FEDIT=f.id;factDraw()};
  const del=E('button','b ic-red',t('Vergessen','Forget'));del.type='button';del.onclick=()=>forgetFact(f.id);row.append(ch,del);m.appendChild(row);d.appendChild(m);return d}
function factDraw(){const E=icEl,tools=$('facttools'),box=$('factlist');if(!tools||!box)return;
  const nAuto=FACTS.filter(f=>f.auto).length;tools.textContent='';
  const s=icSearch(t(`In ${FACTS.length} Einträgen suchen …`,`Search ${FACTS.length} entries …`),FQ,v=>{FQ=v;FMORE=false;list()},'factfind');
  const n=k=>FACTS.filter(f=>k==='stale'?fstale(f):f.mark===k).length;
  const chips=FCHECK?[['all',t(`Alle ${FACTS.length}`,`All ${FACTS.length}`)],['ok',t(`Bestätigt ${n('ok')}`,`Confirmed ${n('ok')}`)],['learned',t(`Gelernt ${n('learned')}`,`Learned ${n('learned')}`)],['stale',t(`Veraltet ${n('stale')}`,`Outdated ${n('stale')}`)]]
    :[['all',t(`Alle ${FACTS.length}`,`All ${FACTS.length}`)],['own',t(`Von dir ${FACTS.length-nAuto}`,`From you ${FACTS.length-nAuto}`)],['auto',t(`Automatisch ${nAuto}`,`Automatic ${nAuto}`)]];
  tools.append(s,...chips.map(([k,l])=>icChip(l,FF===k,()=>{FF=k;FMORE=false;factDraw()},k==='stale'&&n('stale')?'warn':'')));
  if(FACTS.length){const pick=E('button','b',FSEL?t('Fertig','Done'):t('Auswählen','Select'));pick.type='button';pick.id='factpick';pick.onclick=()=>{FSEL=FSEL?null:new Set();factDraw()};tools.appendChild(pick)}
  const note=$('factcheck');if(note){note.textContent='';const ns=FCHECK?n('stale'):0;note.hidden=!ns;
    if(ns){const b=E('button','b p',t('Durchgehen','Go through'));b.type='button';b.onclick=()=>{FF='stale';FMORE=false;factDraw()};
      note.appendChild(icNote(t(`${ns} ${ns===1?'Eintrag ist':'Einträge sind'} vielleicht veraltet`,`${ns} ${ns===1?'entry is':'entries are'} maybe out of date`),
        t('Gefunden mit festen Regeln (Datum vorbei, „zurzeit“, lange nicht bestätigt, Widerspruch). Gelöscht wird nichts.','Found with fixed rules (date passed, "currently", not confirmed for long, contradiction). Nothing is deleted.'),[b]))}}
  list();
  function keep(f){return FF==='all'||(FF==='auto'?!!f.auto:FF==='own'?!f.auto:FF==='stale'?fstale(f):f.mark===FF)}
  function list(){box.textContent='';const q=FQ.trim().toLowerCase();
    const fs=FACTS.slice().reverse().filter(f=>keep(f)&&(!q||f.text.toLowerCase().includes(q)));
    const tk=f=>FTOP&&FTOP[f.topic]?f.topic:'',tord=f=>{const k=Object.keys(FTOP||{}).indexOf(tk(f));return k<0?99:k};
    if(FTOP&&!FSEL)fs.sort((a,b)=>tord(a)-tord(b));
    if(!fs.length){box.appendChild(icList([icEmpty(FACTS.length?t('Nichts gefunden.','Nothing found.'):t('Noch nichts gemerkt. Sag „Merk dir …“.','Nothing remembered yet. Say "Remember …".'))]));return}
    const rows=[];fs.forEach(f=>{
      if(FEDIT===f.id){const r=E('div','ic-row');const ta=document.createElement('textarea');ta.value=f.text;ta.maxLength=300;ta.rows=2;ta.className='factedit';ta.setAttribute('aria-label',t('Eintrag ändern','Change entry'));
        const ok=E('button','b p',t('Speichern','Save')),no=E('button','b',t('Abbrechen','Cancel'));ok.type=no.type='button';
        ok.onclick=async()=>{ok.disabled=true;try{await api('/api/profile/memory/'+encodeURIComponent(f.id),xjson('PUT',{text:ta.value}));FEDIT=null;await showFacts()}catch(e){ok.disabled=false;$('factmsg').textContent=e.message}};
        no.onclick=()=>{FEDIT=null;factDraw()};const m=E('div','ic-rmid');m.appendChild(ta);const a=E('div','row');a.append(ok,no);m.appendChild(a);r.appendChild(m);setTimeout(()=>ta.focus(),0);rows.push([r]);return}
      const meta=FCHECK?(FSRC[f.src]||'')+(f.created||f.changed?' · '+fdate(f.changed||f.created):''):(f.auto?t('automatisch','automatic'):t('von dir','from you'))+(f.created||f.changed?' · '+fdate(f.changed||f.created):'');
      const lead=FSEL?icCheck(FSEL.has(f.id),f.text,()=>{FSEL.has(f.id)?FSEL.delete(f.id):FSEL.add(f.id);factDraw()}):null;
      const mk=FCHECK&&FMARK[f.mark];const badge=mk?E('span','ic-badge'+(mk[0]?' '+mk[0]:''),mk[1]):null;
      const acts=FSEL?[]:[badge,icBtn('pen',t('Ändern','Change'),()=>{FEDIT=f.id;factDraw()}),icBtn('trash',t('Löschen','Delete'),()=>forgetFact(f.id))];
      const r=icRow(f.text,meta,acts,lead);r.dataset.fact=f.id;if(FSEL&&FSEL.has(f.id))r.classList.add('on');
      if(FCHECK&&!FSEL){r.classList.add('click');r.querySelector('.ic-rmid').onclick=()=>{FOPEN=FOPEN===f.id?null:f.id;list()};if(FOPEN===f.id)r.classList.add('on')}
      const one=FCHECK&&!FSEL&&FOPEN===f.id?[r,factDetail(f)]:[r];one.topic=tk(f);rows.push(one)});
    let l=icList([]);const nn=FMORE||q?rows.length:15;let cur=null;
    rows.slice(0,nn).forEach(x=>{if(FTOP&&!FSEL&&x.topic!==cur){if(l.childNodes.length)box.appendChild(l);cur=x.topic;
        box.appendChild(icGroup(cur?t(FTOP[cur][0],FTOP[cur][1]):t('Noch ohne Thema','No topic yet'),rows.filter(y=>y.topic===cur).length));l=icList([])}
      x.forEach(r=>l.appendChild(r))});
    if(rows.length>nn){const b=E('button','ic-more2',t(`Weitere ${rows.length-nn} Einträge zeigen`,`Show ${rows.length-nn} more entries`));b.type='button';b.onclick=()=>{FMORE=true;list()};l.appendChild(b)}
    box.appendChild(l);
    if(FSEL){const bar=E('div','ic-save');const m=E('div','ic-mid');m.appendChild(E('b','',t(`${FSEL.size} ausgewählt`,`${FSEL.size} selected`)));
      const all=E('button','b',t('Alle gezeigten','All shown'));all.type='button';all.onclick=()=>{fs.forEach(f=>FSEL.add(f.id));factDraw()};
      const del=E('button','b ic-red',t('Löschen','Delete'));del.type='button';del.disabled=!FSEL.size;
      del.onclick=async()=>{if(!confirm(t(`${FSEL.size} Einträge löschen?`,`Delete ${FSEL.size} entries?`)))return;await api('/api/profile/memory/forget',xjson('POST',{ids:[...FSEL]}));FSEL=null;showFacts()};
      bar.append(m,all,del);box.appendChild(bar)}}}
// Documents (documents.py, wissen.py). Since V01.0.413 one compact row per document with a search field that
// filters at once, source, sort order, quick filters and tags; a click opens the details (beside the list on wide
// screens, as its own page on narrow ones) with all buttons; "Auswählen" acts on several documents in one request.
// The profile's own choice (deadline offers, when the admin allows it) sits folded under the list.
const docSize=n=>n<1048576?Math.max(1,Math.round(n/1024))+' KB':(n/1048576).toFixed(1)+' MB';
// Since "Freigabe vereinfachen" (Dominik 2026-10-13) every document function the admin allows works at once; only the deadline offer
// and „Mit Docling lesen“ (the files leave the Spark, a preference that starts on) stay a choice of the profile.
const DOCSW=[['due',t('Fristen anbieten','Offer deadlines'),t('Hat ein Dokument eine Frist, gibt es den Knopf „Erinnern“. Eine Erinnerung entsteht nur auf deinen Klick.','When a document has a deadline there is a "Remind" button. A reminder is only set on your click.')],
  ['docling',t('Mit Docling lesen','Read with Docling'),t('Der Docling-Server im Heimnetz liest deine Dateien in Pausen ein zweites Mal, mit Tabellen und Scans. Aus: Sie bleiben auf dem Spark.','The Docling server in the home network reads your files a second time in quiet moments, with tables and scans. Off: they stay on the Spark.')]];
const DOCSRC={upload:t('Hochgeladen','Uploaded'),app:t('iPhone-App','iPhone app'),begleiter:t('Begleiter','Companion'),remarkable:'reMarkable',agent:t('Aufträge','Jobs'),spark:t('Vom Spark erstellt','Made by the Spark'),nas:t('Wissensordner','Knowledge folder'),eingang:t('NAS-Eingang','NAS inbox'),other:t('Von anderen','From others')};
const DOCSORT=[['new',t('Neueste zuerst','Newest first')],['name',t('Name A–Z','Name A–Z')],['due',t('Frist zuerst','Deadline first')],['size',t('Größte zuerst','Largest first')]];
const DOCCHIP=[['',t('Alle','All')],['due',t('Frist offen','Deadline open')],['reading',t('Wird gelesen','Being read')],['error',t('Nicht lesbar','Not readable')],['shared',t('Für alle','For everyone')],['off',t('Suche aus','Search off')]];
const DOCPAGE=50;
// what the list shows; source and sort order stay in this browser (a convenience, works without storage too)
const DOCV={find:'',src:'',sort:'new',chip:'',tag:'',pick:null,sel:'',max:DOCPAGE};
try{const s=JSON.parse(localStorage.getItem('docview')||'{}');if(DOCSORT.some(([k])=>k===s.sort))DOCV.sort=s.sort;if(DOCSRC[s.src])DOCV.src=s.src}catch{}
const docKeep=()=>{try{localStorage.setItem('docview',JSON.stringify({sort:DOCV.sort,src:DOCV.src}))}catch{}};
let DOCINFO=null,DOCL=[],DOCO=[];
const docAll=()=>DOCL.concat(DOCO);
const docFind=id=>docAll().find(d=>d.id===id);
const docBrief=()=>!!(DOCINFO&&DOCINFO.allow.brief);
const docShareOn=()=>!!(DOCINFO&&DOCINFO.allow.shared);
const docSrc=d=>d.owner?'other':DOCSRC[d.source]?d.source:'upload';
const docTitle=d=>docBrief()&&d.title||d.name;
const docHas=(d,tag)=>!tag||(d.tags||[]).some(x=>x.toLowerCase()===tag.toLowerCase());
const docToday=()=>new Date().toISOString().slice(0,10);
const docDue=(d,today)=>!!(d.due&&(d.due.length===7?d.due>=today.slice(0,7):d.due>=today));
const docDay=s=>s?(s.length===7?s.slice(5,7)+'/'+s.slice(0,4):L==='en'?s.slice(8,10)+'/'+s.slice(5,7)+'/'+s.slice(0,4):s.slice(8,10)+'.'+s.slice(5,7)+'.'+s.slice(0,4)):'';
// short form for the badge: day and month in this year, else with a two-digit year
const docDayS=s=>!s||s.length===7?docDay(s):s.slice(0,4)===docToday().slice(0,4)?(L==='en'?s.slice(8,10)+'/'+s.slice(5,7):s.slice(8,10)+'.'+s.slice(5,7)+'.'):(L==='en'?s.slice(8,10)+'/'+s.slice(5,7)+'/'+s.slice(2,4):s.slice(8,10)+'.'+s.slice(5,7)+'.'+s.slice(2,4));
const docAdded=d=>d.created?new Date(d.created*1000).toLocaleDateString(L==='en'?'en-GB':'de-DE',{day:'2-digit',month:'2-digit',year:'numeric'}):'';
const docIco=d=>d.kind==='notebook'?['nb','NB']:d.kind==='picture'||/\.(jpe?g|png|webp)$/i.test(d.name)?['img',t('BILD','IMG')]:/\.pdf$/i.test(d.name)?['pdf','PDF']:
  /\.(docx|odt)$/i.test(d.name)?['doc','DOC']:/\.(xlsx|ods|csv)$/i.test(d.name)?['tab',t('TAB','TAB')]:/\.(pptx|odp)$/i.test(d.name)?['doc','PPT']:['txt','TXT'];
// progress of one document (V01.0.232): pages read of all pages, then pieces with a meaning, and why it
// waits (switch off, daily limit, someone is talking, the model waits for memory). [text, percent or null]
function docState(d){const I=DOCINFO,pics=I&&I.allow.pictures,mean=I&&I.vectors&&I.allow.semantic;
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
  const busy=l.some(d=>d.state==='reading'||(I&&I.vectors&&I.allow.semantic&&d.chunks&&d.vecs<d.chunks));
  if(busy)docTimer=setTimeout(()=>{const box=$('docbox');if(box&&box.offsetParent!==null&&!document.hidden)showDocs();else docAgain(l)},10e3)}
async function showDocs(){if(!DOCS_ON){$('docbox').style.display='none';return}$('docbox').style.display='';
  const l=await (await api('/api/profile/docs')).json();
  try{DOCINFO=await (await api('/api/profile/wissen')).json()}catch{DOCINFO=null}
  const I=DOCINFO;DOCL=l;DOCO=I&&I.others||[];
  if(typeof mkShow==='function')mkShow(I);
  if(typeof sprShow==='function')sprShow();
  $('docsw').innerHTML=I?DOCSW.filter(([k])=>k==='due'?I.allow.brief:I.allow[k]).map(([k,l,h])=>`<div class="setrow"><div class="lbl"><b>${esc(l)}</b><span>${esc(h)}</span></div><label class="tgl"><input type="checkbox" data-docsw="${k}"${I.on[k]?' checked':''}><i></i></label></div>`).join(''):'';
  if(I&&I.space){const pct=Math.min(100,Math.round(100*I.used/I.space));$('docspace').hidden=false;
    $('docspacet').textContent=t(`${docSize(I.used)} von ${docSize(I.space)} belegt`,`${docSize(I.used)} of ${docSize(I.space)} used`);
    $('docspace').title=t(`Belegt: ${pct} %`,`Used: ${pct} %`)+(I.quota?t(`, davon Originale ${docSize(I.usage)}`,`, originals ${docSize(I.usage)}`):'');
    const bar=$('docspace').querySelector('i');bar.style.width=pct+'%';$('docspace').classList.toggle('full',pct>=90)}
  const bits=[];
  if(I&&I.allow.pictures)bits.push(t(`heute ${I.today} von ${I.day_pages} Seiten gelesen`,`${I.today} of ${I.day_pages} pages read today`));
  if(I&&I.vectors&&I.allow.semantic)bits.push(t(`Bedeutungssuche: ${I.vectors[0]} von ${I.vectors[1]} Abschnitten vorbereitet`,`Meaning search: ${I.vectors[0]} of ${I.vectors[1]} sections prepared`));
  if(I&&I.heads_left)bits.push(t(`Zusammenhang der Abschnitte: ${I.heads_left} Dokumente warten auf eine ruhige Minute`,`Context of the sections: ${I.heads_left} documents wait for a quiet minute`));
  $('docuse').textContent=bits.join(' · ');docAgain(l);
  const pics=I&&I.allow.pictures;
  $('docfile').accept='.pdf,.txt,.md,.docx,.html,.htm,.csv,.xlsx,.pptx,.odt,.ods,.odp,.eml'+(pics?',.jpg,.jpeg,.png,.webp':'');
  docRender()}
// a quick filter: does document d belong to it
function docChipOk(d,c,today){return !c||(c==='due'?docDue(d,today):c==='reading'?d.state==='reading':c==='error'?d.state==='error':c==='shared'?!d.owner&&d.shared:c==='off'?!d.owner&&d.use===false:true)}
function docMatch(d,q){return !q||[d.title,d.name,d.sender,d.art,d.ref,d.owner,...(d.tags||[])].some(x=>x&&String(x).toLowerCase().includes(q))}
function docSorted(l,today){const by=DOCV.sort,n=(a,b)=>docTitle(a).localeCompare(docTitle(b),L==='en'?'en':'de',{sensitivity:'base'});
  return l.slice().sort(by==='name'?n:by==='size'?(a,b)=>(b.size||0)-(a.size||0)||n(a,b):
    by==='due'?(a,b)=>{const x=docDue(a,today)?a.due:'9',y=docDue(b,today)?b.due:'9';return x<y?-1:x>y?1:n(a,b)}:
    (a,b)=>(!!a.owner-!!b.owner)||(b.created||0)-(a.created||0))}
// the headings while sorted by date: today, the last 7 days, the months of this year, then the years
function docGroup(d,now){if(d.owner)return t('Von anderen freigegeben','Shared by others');if(!d.created)return t('Älter','Older');
  const c=new Date(d.created*1000),n=new Date(now);if(c.toDateString()===n.toDateString())return t('Heute','Today');
  if(now-c<7*864e5)return t('Letzte 7 Tage','Last 7 days');
  return c.getFullYear()===n.getFullYear()?c.toLocaleDateString(L==='en'?'en-GB':'de-DE',{month:'long'}):String(c.getFullYear())}
function docBadges(d,today){const b=[];
  if(d.state==='reading')b.push(`<span class="ld-badge read">${esc(t('liest ','reading ')+(d.pages-d.todo)+'/'+d.pages)}</span>`);
  if(d.state==='error')b.push(`<span class="ld-badge err">${esc(t('nicht lesbar','not readable'))}</span>`);
  if(docDue(d,today))b.push(`<span class="ld-badge due">${esc(t('Frist ','due ')+docDayS(d.due))}</span>`);
  if(!d.owner&&d.shared)b.push(`<span class="ld-badge sh">${esc(t('für alle','for everyone'))}</span>`);
  if(!d.owner&&d.use===false)b.push(`<span class="ld-badge off">${esc(t('Suche aus','search off'))}</span>`);
  return b.join('')}
function docRow(d,today){const [c,l]=docIco(d),pk=DOCV.pick,brief=docBrief();
  const sub=[brief&&d.art,brief&&d.sender,d.owner?t('von ','from ')+d.owner:d.place?'NAS · '+d.place:DOCSRC[docSrc(d)],brief&&d.title?d.name:''].filter(Boolean).join(' · ');
  const when=d.owner?'':[docAdded(d),d.size?docSize(d.size):''].filter(Boolean).join(' · ');
  return `<div class="ld-row${DOCV.sel===d.id&&!pk?' on':''}" data-doc="${esc(d.id)}" role="button" tabindex="0">`+
    (pk?d.owner?'<span class="ld-pick"></span>':`<input type="checkbox" class="ld-pick" data-pick="${esc(d.id)}"${pk.has(d.id)?' checked':''} aria-label="${esc(t('auswählen','select'))}">`:'')+
    `<span class="ld-ico ${c}" aria-hidden="true">${l}</span><span class="ld-mid"><b>${esc(docTitle(d))}</b><small>${esc(sub)}</small></span>`+
    `<span class="ld-right">${docBadges(d,today)}${when?`<span class="ld-when">${esc(when)}</span>`:''}</span></div>`}
function docRender(){const I=DOCINFO,brief=docBrief(),today=docToday(),q=DOCV.find.trim().toLowerCase(),all=docAll();
  // sources, tags and quick filters offer only what is there; a choice that went away falls back to "all"
  const srcs={};for(const d of all){const s=docSrc(d);srcs[s]=(srcs[s]||0)+1}
  if(DOCV.src&&!srcs[DOCV.src])DOCV.src='';
  const sel=$('docsrc');sel.hidden=Object.keys(srcs).length<2;
  sel.innerHTML=`<option value="">${esc(t(`Alle Quellen (${all.length})`,`All sources (${all.length})`))}</option>`+Object.keys(DOCSRC).filter(k=>srcs[k]).map(k=>`<option value="${k}"${DOCV.src===k?' selected':''}>${esc(DOCSRC[k])} (${srcs[k]})</option>`).join('');
  $('docsort').innerHTML=DOCSORT.filter(([k])=>k!=='due'||brief).map(([k,l])=>`<option value="${k}"${DOCV.sort===k?' selected':''}>${esc(l)}</option>`).join('');
  if(DOCV.sort==='due'&&!brief)DOCV.sort='new';
  const base=all.filter(d=>(!DOCV.src||docSrc(d)===DOCV.src)&&docMatch(d,q));
  const tags={};if(brief)for(const d of base)for(const x of d.tags||[]){const k=x.toLowerCase();tags[k]=tags[k]||[x,0];tags[k][1]++}
  if(DOCV.tag&&!tags[DOCV.tag.toLowerCase()])DOCV.tag='';
  const counts=DOCCHIP.map(([k])=>base.filter(d=>docHas(d,DOCV.tag)&&docChipOk(d,k,today)).length);
  if(DOCV.chip&&!counts[DOCCHIP.findIndex(([k])=>k===DOCV.chip)])DOCV.chip='';
  const tl=Object.values(tags).sort((a,b)=>b[1]-a[1]||a[0].localeCompare(b[0]));
  $('docchips').innerHTML=DOCCHIP.map(([k,l],i)=>!k||counts[i]?`<button type="button" class="ld-chip${DOCV.chip===k?' on':''}" data-chip="${k}">${esc(l)} <b>${counts[i]}</b></button>`:'').join('')+
    (tl.length?`<select id="doctagsel" class="ld-chip${DOCV.tag?' on':''}" aria-label="${esc(t('Tag','Tag'))}"><option value="">${esc(t('Alle Tags','All tags'))}</option>${tl.map(([x,n])=>`<option value="${esc(x)}"${x.toLowerCase()===DOCV.tag.toLowerCase()?' selected':''}>${esc(x)} (${n})</option>`).join('')}</select>`:'');
  $('docchips').hidden=!all.length;$('doctools').classList.toggle('few',!all.length);
  const l=docSorted(base.filter(d=>docHas(d,DOCV.tag)&&docChipOk(d,DOCV.chip,today)),today);
  if(DOCV.pick)for(const id of [...DOCV.pick])if(!DOCL.some(d=>d.id===id))DOCV.pick.delete(id);
  const now=Date.now();let html='',last=null;
  for(const d of l.slice(0,DOCV.max)){if(DOCV.sort==='new'){const g=docGroup(d,now);
      if(g!==last){last=g;const n=l.filter(x=>docGroup(x,now)===g).length;html+=`<div class="ld-grp"><span>${esc(g)}</span><span>${n}</span></div>`}}
    html+=docRow(d,today)}
  if(l.length>DOCV.max)html+=`<div class="ld-more"><button class="b" type="button" data-more="1">${esc(t(`Weitere ${Math.min(DOCPAGE,l.length-DOCV.max)} von ${l.length-DOCV.max} zeigen`,`Show ${Math.min(DOCPAGE,l.length-DOCV.max)} more of ${l.length-DOCV.max}`))}</button></div>`;
  $('doclist').innerHTML=html||`<div class="mut ld-empty">${esc(all.length?t('Nichts passt zu Suche und Filter.','Nothing fits the search and filter.'):t('Noch keine Dokumente. Mit „Hinzufügen“ legst du PDFs, Office-Dateien, Texte oder E-Mails ab; der Assistent sucht dann darin.','No documents yet. With "Add" you store PDFs, office files, texts or e-mails; the assistant then searches them.'))}</div>`;
  $('doccount').textContent=all.length?(l.length===all.length?t(`${all.length} Dokumente`,`${all.length} documents`):t(`${l.length} von ${all.length} Dokumenten`,`${l.length} of ${all.length} documents`)):'';
  $('docpick').hidden=!DOCL.length;$('docpick').textContent=DOCV.pick?t('Fertig','Done'):t('Auswählen','Select');
  docBulk();docDetail()}
// "Auswählen": the bar with what can be done to the selected own documents (one request, wissen.py batch)
function docBulk(){const box=$('docbulk'),pk=DOCV.pick;box.hidden=!pk;if(!pk){box.innerHTML='';return}
  const n=pk.size,dis=n?'':' disabled',typing=box.contains(document.activeElement)&&document.activeElement.id==='docbulktag';
  if(typing){box.querySelector('b').textContent=t(`${n} ausgewählt`,`${n} selected`);return}
  box.innerHTML=`<b>${esc(t(`${n} ausgewählt`,`${n} selected`))}</b><button class="b" type="button" data-bulk="all">${esc(t('Alle gezeigten','All shown'))}</button>`+
    `<button class="b" type="button" data-bulk="use"${dis}>${esc(t('Suche an','Search on'))}</button><button class="b" type="button" data-bulk="unuse"${dis}>${esc(t('Suche aus','Search off'))}</button>`+
    (docShareOn()?`<button class="b" type="button" data-bulk="share"${dis}>${esc(t('Für alle','For everyone'))}</button><button class="b" type="button" data-bulk="unshare"${dis}>${esc(t('Nicht mehr für alle','No longer for everyone'))}</button>`:'')+
    (docBrief()?`<span class="dbtag"><input id="docbulktag" maxlength="24" placeholder="${esc(t('Tag','Tag'))}" aria-label="${esc(t('Tag für die Auswahl','Tag for the selection'))}"><button class="b" type="button" data-bulk="tag"${dis}>${esc(t('Tag geben','Add tag'))}</button></span>`:'')+
    `<button class="b" type="button" data-bulk="reread"${n&&n<=20?'':' disabled'} title="${esc(t('Aus den aufbewahrten Originalen neu einlesen, höchstens 20 auf einmal','Read again from the kept originals, at most 20 at once'))}">${esc(t('Neu einlesen','Read again'))}</button>`+
    `<button class="b danger" type="button" data-bulk="delete"${dis}>${esc(t('Löschen','Delete'))}</button><button class="b" type="button" data-bulk="done">${esc(t('Fertig','Done'))}</button>`}
// the details of the selected document: its card, switches and buttons. #docdinfo is drawn again with
// every refresh (not while someone types the tags); the text view below it stays
function docDetail(){const box=$('docdetail'),d=DOCV.pick?null:docFind(DOCV.sel);
  $('docbox').classList.toggle('ld-sel',!!d);box.hidden=!d;
  if(!d){$('docdinfo').innerHTML='';$('docview').hidden=true;$('docview').textContent='';return}
  const info=$('docdinfo'),a=document.activeElement;
  if(info.dataset.id===d.id&&info.contains(a)&&a.id==='doctagin')return;
  info.dataset.id=d.id;
  const brief=docBrief(),own=!d.owner,today=docToday(),[st,pct]=own?docState(d):['',null];
  const meta=[[t('Datei','File'),d.name],brief&&[t('Art','Kind'),d.art],brief&&[t('Absender','Sender'),d.sender],brief&&[t('Datum','Date'),docDay(d.date)],
    brief&&[t('Frist','Deadline'),docDay(d.due)],brief&&[t('Nummer','Number'),d.ref],[t('Quelle','Source'),d.owner?t('von ','from ')+d.owner:d.place?t('Wissensordner','Knowledge folder')+' · NAS · '+d.place:DOCSRC[docSrc(d)]],
    own&&[t('Hinzugefügt','Added'),docAdded(d)],own&&[t('Größe','Size'),docSize(d.size||0)],own&&[t('Zustand','State'),st]].filter(x=>x&&x[1]);
  const pdf=/\.pdf$/i.test(d.name),pic=d.kind==='picture',href='/api/profile/wissen/'+encodeURIComponent(d.id)+'/file'+(pdf||pic?'?view=1':'');
  info.innerHTML=`<button class="b ld-back" type="button" data-dact="back">‹ ${esc(t('Zurück zur Liste','Back to the list'))}</button>`+
    `<h3>${esc(docTitle(d))}</h3><dl class="ld-facts">${meta.map(([k,v])=>`<dt>${esc(k)}</dt><dd${k===t('Frist','Deadline')&&docDue(d,today)?' class="due"':''}>${esc(v)}</dd>`).join('')}</dl>`+
    (pct===null?'':`<span class="qbar docbar" role="progressbar" aria-valuemin="0" aria-valuemax="100" aria-valuenow="${pct}"><i style="width:${pct}%"></i></span>`)+
    (d.note?`<p class="mut ld-note">${esc(d.note)}</p>`:'')+
    ((d.tags||[]).length?`<div class="dtags">${d.tags.map(x=>`<button type="button" class="dtag${x.toLowerCase()===DOCV.tag.toLowerCase()?' on':''}" data-doctag="${esc(x)}" title="${esc(t('Liste nach diesem Tag filtern','Filter the list by this tag'))}">${esc(x)}</button>`).join('')}</div>`:'')+
    (own&&brief&&d.state==='ready'?`<div class="dtagedit"><input id="doctagin" maxlength="250" value="${esc((d.tags||[]).join(', '))}" placeholder="${esc(t('Tags mit Komma; leer = die automatischen','Tags with commas; empty = the automatic ones'))}" aria-label="${esc(t('Eigene Tags','Own tags'))}"><button class="b" type="button" data-dact="tags">${esc(t('Speichern','Save'))}</button></div>`:'')+
    (own?`<div class="ld-sw"><span>${esc(t('Der Assistent sucht darin','The assistant searches it'))}</span><label class="tgl"><input type="checkbox" data-docuse="${esc(d.id)}"${d.use?' checked':''}><i></i></label></div>`:'')+
    (own&&docShareOn()&&d.state==='ready'?`<div class="ld-sw"><span>${esc(t('Für alle','For everyone'))}<small class="mut"> · ${esc(t('alle Profile mit „Gemeinsame Dokumente“ finden und öffnen es','every profile with "Shared documents" finds and opens it'))}</small></span><label class="tgl"><input type="checkbox" data-docshare="${esc(d.id)}"${d.shared?' checked':''}><i></i></label></div>`:'')+
    `<div class="ld-acts">`+(d.file?`<a class="b p" href="${esc(href)}"${pdf?' target="_blank"':''} rel="noopener">${esc(pdf?t('PDF öffnen','Open PDF'):pic?t('Bild öffnen','Open picture'):t('Original herunterladen','Download original'))}</a>`:'')+
    `<button class="b" type="button" data-dact="view">${esc(t('Text lesen','Read text'))}</button>`+
    (own&&brief&&DOCINFO.on.due&&docDue(d,today)?`<button class="b" type="button" data-docremind="${esc(d.id)}" title="${esc(t('Erinnerung sechs Wochen vor der Frist (oder am Tag davor)','Reminder six weeks before the deadline (or the day before)'))}">${esc(t('Erinnern','Remind'))}</button>`:'')+
    (own&&d.file&&d.state!=='reading'?`<button class="b" type="button" data-docreread="${esc(d.id)}" title="${esc(t('Aus dem aufbewahrten Original neu einlesen','Read again from the kept original'))}">${esc(t('Neu einlesen','Read again'))}</button>`:'')+
    (own?`<button class="b danger" type="button" data-docdel="${esc(d.id)}" data-name="${esc(d.name)}"${d.place?' data-nas="1"':''}>${esc(d.place?t('Nicht mehr finden','Stop finding'):t('Löschen','Delete'))}</button>`:'')+`</div>`+
    (own&&!d.file?`<p class="mut ld-note">${esc(t('Original nicht aufbewahrt: Zum Neu-Einlesen die Datei neu hochladen.','Original not kept: to read it again, upload the file again.'))}</p>`:'')}
function docOpen(id){DOCV.sel=id;const v=$('docview');if(v.dataset.id!==id){v.hidden=true;v.textContent=''}docRender();
  if($('docbox').classList.contains('ld-sel'))$('docdetail').scrollIntoView({block:'nearest'})}
const docErr=x=>{$('docmsg').innerHTML=`<span class="err">${esc(x.message)}</span>`};
$('docsw').onchange=async e=>{const k=e.target.dataset.docsw;if(!k)return;
  try{await api('/api/profile/settings',{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({['doc_'+k]:e.target.checked})})}
  catch(x){docErr(x)}showDocs()};
$('docfind').oninput=()=>{DOCV.find=$('docfind').value;DOCV.max=DOCPAGE;docRender()};
$('docfind').onkeydown=e=>{if(e.key==='Enter'){e.preventDefault();docTry()}else if(e.key==='Escape'){$('docfind').value='';DOCV.find='';$('dochits').innerHTML='';docRender()}};
$('docsrc').onchange=()=>{DOCV.src=$('docsrc').value;DOCV.max=DOCPAGE;docKeep();docRender()};
$('docsort').onchange=()=>{DOCV.sort=$('docsort').value;DOCV.max=DOCPAGE;docKeep();docRender()};
$('docchips').onclick=e=>{const c=e.target.closest('[data-chip]');if(c){DOCV.chip=c.dataset.chip;DOCV.max=DOCPAGE;docRender()}};
$('docchips').onchange=e=>{if(e.target.id==='doctagsel'){DOCV.tag=e.target.value;DOCV.max=DOCPAGE;docRender()}};
$('docpick').onclick=()=>{DOCV.pick=DOCV.pick?null:new Set();docRender()};
$('doclist').onclick=e=>{if(e.target.closest('[data-more]')){DOCV.max+=DOCPAGE;docRender();return}
  const r=e.target.closest('.ld-row');if(!r)return;const id=r.dataset.doc;
  if(DOCV.pick){if(!DOCL.some(d=>d.id===id))return;DOCV.pick.has(id)?DOCV.pick.delete(id):DOCV.pick.add(id);docRender();return}
  docOpen(id)};
$('doclist').onkeydown=e=>{const r=e.target.closest('.ld-row');if(r&&(e.key==='Enter'||e.key===' ')&&e.target===r){e.preventDefault();r.click()}};
$('docbulk').onclick=async e=>{const b=e.target.closest('[data-bulk]');if(!b||b.disabled)return;const k=b.dataset.bulk,pk=DOCV.pick;
  if(k==='done'){DOCV.pick=null;docRender();return}
  if(k==='all'){for(const el of document.querySelectorAll('#doclist [data-pick]'))pk.add(el.dataset.pick);docRender();return}
  const ids=[...pk],body={do:k,ids};
  if(k==='tag'){body.tag=$('docbulktag').value.trim();if(!body.tag){$('docbulktag').focus();return}}
  if(k==='delete'&&!confirm(t(`${ids.length} Dokumente löschen? Das lässt sich nicht rückgängig machen.`,`Delete ${ids.length} documents? This cannot be undone.`)))return;
  b.disabled=true;
  try{const r=await (await api('/api/profile/wissen/batch',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)})).json();
    $('docmsg').textContent=t(`Erledigt für ${r.done} von ${ids.length}`,`Done for ${r.done} of ${ids.length}`)+(r.failed?t(` (${r.failed} gingen nicht)`,` (${r.failed} did not work)`):'');
    if(k==='delete'){pk.clear();if(ids.includes(DOCV.sel))DOCV.sel=''}}
  catch(x){docErr(x)}showDocs()};
// a document read again: the kept original (pictures in the browser) and its stored text, built with
// textContent only; it opens in the details, so chat sources ("Aus deinen Dokumenten") land there too
async function docView(id){if(!docFind(id))await showDocs();if(DOCV.pick)DOCV.pick=null;docOpen(id);
  const box=$('docview');box.hidden=false;box.dataset.id=id;box.textContent=t('Lade …','Loading …');
  try{const d=await (await api('/api/profile/wissen/'+encodeURIComponent(id)+'/text')).json();box.textContent='';
    const head=document.createElement('div');head.className='dvhead';const nm=document.createElement('b');nm.textContent=t('Text','Text')+(d.owner?' · '+t('von ','from ')+d.owner:'');head.appendChild(nm);
    const x=document.createElement('button');x.type='button';x.className='b';x.textContent='✕';x.setAttribute('aria-label',t('Text schließen','Close text'));x.onclick=()=>{box.hidden=true;box.textContent=''};
    head.appendChild(x);box.appendChild(head);
    if(d.file&&d.kind==='picture'){const img=document.createElement('img');img.alt='';img.src='/api/profile/wissen/'+encodeURIComponent(id)+'/file?view=1';box.appendChild(img)}
    let page;const show=parts=>{for(const p of parts){if(p.page&&p.page!==page){page=p.page;const h=document.createElement('div');h.className='dvpage';h.textContent=t('Seite ','Page ')+p.page;box.appendChild(h)}
      const tx=document.createElement('p');tx.className='dvtext';tx.textContent=p.text;box.appendChild(tx)}};show(d.parts);
    if(d.related&&d.related.length){const r=document.createElement('div');r.className='dvrel';const h=document.createElement('small');h.className='mut';h.textContent=t('Dazu gehören: ','Belongs with: ');r.appendChild(h);
      for(const x of d.related){const b=document.createElement('button');b.type='button';b.className='dtag';b.textContent=x.title||x.name;
        b.title={Nummer:t('gleiche Nummer','same number'),Absender:t('gleicher Absender','same sender'),Tags:t('gleiche Schlagwörter','same keywords')}[x.why]||'';b.onclick=()=>docOpen(x.id);r.appendChild(b)}
      box.appendChild(r)}
    if(!d.parts.length){const m=document.createElement('p');m.className='mut';m.textContent=d.state==='reading'?t('Wird noch gelesen.','Still being read.'):t('Kein Text.','No text.');box.appendChild(m)}
    // long documents come a part at a time; the assistant always searches the whole text
    const more=next=>{if(next==null)return;const b=document.createElement('button');b.type='button';b.className='b';b.textContent=t('Weiterlesen','Read on');
      b.onclick=async()=>{b.disabled=true;try{const n=await (await api('/api/profile/wissen/'+encodeURIComponent(id)+'/text?start='+next)).json();b.remove();show(n.parts);more(n.next)}
        catch(x){b.disabled=false;b.textContent=x.message}};box.appendChild(b)};more(d.next);
    box.scrollIntoView({block:'nearest'})}
  catch(x){box.textContent=x.message}}
$('docdetail').onchange=async e=>{const sh=e.target.dataset.docshare,id=e.target.dataset.docuse;if(!sh&&!id)return;
  try{await api('/api/profile/wissen/'+encodeURIComponent(sh||id),{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify(sh?{shared:e.target.checked}:{use:e.target.checked})})}
  catch(x){docErr(x)}showDocs()};
async function docTagsSave(){const id=DOCV.sel,list=$('doctagin').value.split(',').map(x=>x.trim()).filter(Boolean);
  try{await api('/api/profile/wissen/'+encodeURIComponent(id),{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({tags:list.length?list:null})});
    $('docmsg').textContent=t('Tags gespeichert.','Tags saved.')}
  catch(x){docErr(x)}$('doctagin').blur();showDocs()}
$('docdetail').onkeydown=e=>{if(e.target.id==='doctagin'&&e.key==='Enter'){e.preventDefault();docTagsSave()}};
$('docdetail').onclick=async e=>{const a=e.target.closest('[data-dact]');
  if(a){const k=a.dataset.dact;if(k==='back'){DOCV.sel='';docRender();$('doclist').scrollIntoView({block:'nearest'})}else if(k==='view')docView(DOCV.sel);else if(k==='tags')docTagsSave();return}
  const c=e.target.closest('[data-doctag]');if(c){DOCV.tag=DOCV.tag.toLowerCase()===c.dataset.doctag.toLowerCase()?'':c.dataset.doctag;DOCV.max=DOCPAGE;docRender();return}
  const rm=e.target.closest('[data-docremind]');
  if(rm){rm.disabled=true;try{const r=await (await api('/api/profile/wissen/'+encodeURIComponent(rm.dataset.docremind)+'/remind',{method:'POST'})).json();
      $('docmsg').textContent=t('Erinnerung angelegt für ','Reminder set for ')+new Date(r.due).toLocaleString(L==='en'?'en-GB':'de-DE',{dateStyle:'medium',timeStyle:'short'})}
    catch(x){docErr(x);rm.disabled=false}return}
  const rr=e.target.closest('[data-docreread]');
  if(rr){rr.disabled=true;try{const r=await (await api('/api/profile/wissen/'+encodeURIComponent(rr.dataset.docreread)+'/reread',{method:'POST'})).json();
      $('docmsg').textContent=r.todo?t(`Wird neu gelesen: ${r.todo} Seiten warten.`,`Being read again: ${r.todo} pages waiting.`):t(`Neu eingelesen: ${r.chunks} Abschnitte.`,`Read again: ${r.chunks} sections.`)}
    catch(x){docErr(x)}showDocs();return}
  const b=e.target.closest('[data-docdel]');if(!b)return;
  if(!confirm(b.dataset.nas?t(`„${b.dataset.name}“ nicht mehr finden? Die Datei bleibt am Ort; ändert sie sich, liest der Spark sie wieder.`,`Stop finding "${b.dataset.name}"? The file stays at the place; when it changes the Spark reads it again.`):t('Dokument „','Delete document "')+b.dataset.name+t('“ löschen?','"?')))return;
  try{await api('/api/profile/docs/'+encodeURIComponent(b.dataset.docdel),{method:'DELETE'});DOCV.sel=''}catch(x){docErr(x)}showDocs()};
// Enter in the search field also looks inside the documents (the same search the assistant uses, without the language model)
async function docTry(){const q=$('docfind').value.trim();if(!q){$('dochits').innerHTML='';return}
  $('dochits').innerHTML=`<li class="mut">${t('Suche im Inhalt …','Searching the content …')}</li>`;
  try{const r=await (await api('/api/profile/wissen/search',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({q})})).json();
    $('dochits').innerHTML=`<li class="dhhead"><b>${esc(t('Im Inhalt gefunden','Found in the content'))}</b><button class="b" type="button" data-hitclose="1" aria-label="${esc(t('Treffer schließen','Close hits'))}">✕</button></li>`+
      (r.hits.map(h=>`<li class="dhit" data-docview="${esc(h.id)}" role="button" tabindex="0"><span><b>${esc(h.name)}${h.page?' · '+t('Seite ','page ')+h.page:''}</b><br><small>${esc(h.text)}</small></span></li>`).join('')||`<li class="mut">${t('Nichts gefunden.','Nothing found.')}</li>`)}
  catch(x){$('dochits').innerHTML=`<li class="err">${esc(x.message)}</li>`}}
$('dochits').onclick=e=>{if(e.target.closest('[data-hitclose]')){$('dochits').innerHTML='';return}const h=e.target.closest('[data-docview]');if(h)docView(h.dataset.docview)};
$('dochits').onkeydown=e=>{const h=e.target.closest('[data-docview]');if(h&&e.key==='Enter')docView(h.dataset.docview)};
let DOCS_ON=true,SPK_ON=false,CAL_ON=true,HA_ON=false,MAIL_ON=false;
// The "Ich" window: conversation settings for everyone, plus the profile's own pages once logged in.
// On phones the window opens as a list of its pages (like the iPhone settings); a page then fills the
// screen with a back arrow. Wider screens keep the side bar.
const PHONE=matchMedia('(max-width:760px)');
// the line under the page title says what this page is about (ich-aufraeumen/plan.md, 1a); the device sentence only
// where it matters, under Gespräch and Geräte
const ME_SUB={setbox:['Einstellungen gelten auf jedem Gerät dieses Profils; „Hey Spark“ stellt jedes Gerät selbst ein.','Settings apply on every device of this profile; "Hey Spark" is set per device.'],
  factbox:['Das weiß der Assistent über dich. Sag „Merk dir …“ oder „Vergiss …“, oder ändere es hier.','What the assistant knows about you. Say "Remember …" or "Forget …", or change it here.'],
  rmbox:['Notizbücher, die der Assistent lesen darf, und was er dir aufs reMarkable schickt.','Notebooks the assistant may read, and what it sends to your reMarkable.'],
  mailbox:['Postfächer, die der Assistent lesen darf, und das Aufräumen deines Posteingangs.','Mailboxes the assistant may read, and tidying your inbox.']};
function ptab(id,page=true){if(PROFILE&&!GATE&&$('setscope'))$('setscope').textContent=ME_SUB[id]?t(...ME_SUB[id]):'';document.querySelectorAll('#ptabs button').forEach(b=>{b.classList.toggle('on',b.dataset.t===id);if(b.dataset.t===id)$('mepage').textContent=b.firstChild.textContent});
  document.querySelectorAll('#profmodal .ptab').forEach(x=>x.classList.toggle('on',x.id===id));
  if(typeof guidesMe==='function')guidesMe(id);if(id==='gobox'&&typeof goBar==='function')goBar(false);
  $('profmodal').classList.toggle('sub',page);if(page)document.querySelector('#profmodal .mebody').scrollTop=0}
$('meback').onclick=()=>ptab(meLast,false);
// every page of Ich with whether it shows now (the Sprung-Links in way.js know the names of the hidden ones too)
function meAll(){return [['overbox',t('Überblick','Overview'),!!PROFILE&&!PHONE.matches],['bgbox',t('Mein Zustand','My status'),PROFILE&&MYST_ON],['gobox',t('Los geht\'s','Let\'s go'),!!PROFILE&&typeof SETUP!=='undefined'&&!!SETUP&&SETUP.open>0],['setbox',t('Gespräch','Conversation'),!GATE&&!isGuest()],['loginbox',t('Anmelden','Sign in'),!PROFILE],
    ['factbox',t('Gedächtnis','Memory'),!!PROFILE],['docbox',t('Dokumente','Documents'),PROFILE&&DOCS_ON],['bildbox',t('Bilder','Pictures'),PROFILE&&typeof BILD_ON!=='undefined'&&BILD_ON],['rmbox','reMarkable',PROFILE&&RM_ON],['storebox',t('Speicher','Storage'),PROFILE&&(typeof STORE_ON!=='undefined'&&STORE_ON||typeof NAS_ON!=='undefined'&&NAS_ON)],['logbox',t('Werkzeug-Verlauf','Tool history'),!!PROFILE],
    ['calbox',t('Kalender','Calendar'),PROFILE&&CAL_ON],['taskbox',t('Aufgaben','Tasks'),PROFILE&&TASK_ON],['agentbox',t('Aufträge','Jobs'),PROFILE&&AGENT_ON],['mymcpbox',t('Meine MCP-Dienste','My MCP services'),PROFILE&&typeof MYMCP_ON!=='undefined'&&MYMCP_ON],['wxbox',t('Wetter','Weather'),PROFILE&&WX_ON],['probox',t('Von selbst','Proactive'),PROFILE&&PRO_ON],['notebox',t('Mitteilungen','Notifications'),PROFILE&&REM_ON],
    ['mailbox',t('E-Mail','E-mail'),PROFILE&&MAIL_ON],['parbox',t('Pakete','Parcels'),PROFILE&&PAR_ON],['writebox',t('Schreibhilfe','Writing help'),PROFILE&&typeof WRITE_ON!=='undefined'&&WRITE_ON],['conbox',t('Kontakte','Contacts'),PROFILE&&CON_ON],
    ['habox',t('Smart Home','Smart home'),PROFILE&&HA_ON],['roombox',t('Raum-Modus','Room mode'),PROFILE&&ROOM_ON],['espbox',t('Lautsprecher','Speakers'),PROFILE&&ESP_ON],['telbox',t('Telefon','Phone'),PROFILE&&typeof TEL_ON!=='undefined'&&TEL_ON],
    ['trbox',t('Bus und Bahn','Bus and train'),PROFILE&&TR_ON],['tgbox',t('Telegram','Telegram'),PROFILE&&TG_ON],['appbox',t('iPhone-App','iPhone app'),PROFILE&&APP_ON],['andbox',t('Android-App','Android app'),PROFILE&&typeof AND_ON!=='undefined'&&AND_ON],['deskbox',t('Begleiter','Companion'),PROFILE&&typeof DESK_ON!=='undefined'&&DESK_ON],['pebbox',t('Pebble-Uhr','Pebble watch'),PROFILE&&PEB_ON],['termbox',t('Terminal','Terminal'),PROFILE&&typeof TERM_ON!=='undefined'&&TERM_ON],['mcpbox',t('Dienste per MCP','Services over MCP'),PROFILE&&MCPS_ON],
    ['secbox',t('Sicherheit','Security'),!!PROFILE],['rpbox',t('Probleme melden','Reporting problems'),PROFILE&&typeof RP_ON!=='undefined'&&RP_ON],['voicebox',t('Sprechererkennung','Speaker identification'),PROFILE&&SPK_ON],['usebox',t('Verbrauch','Usage'),PROFILE&&typeof VB_ON!=='undefined'&&VB_ON]]}
function meTabs(){const own=meOwnBoxes();ME_ONLY=new Set();
  // a page the admin blocked that still holds own data shows only its „Daten löschen“ card (meOwn)
  const items=meAll().map(x=>{if(!x[2]&&PROFILE&&own.has(x[0])){ME_ONLY.add(x[0]);return [x[0],x[1],true]}return x}).filter(x=>x[2]);
  // pages in the same groups as everywhere else (guides.js), with a small header per group
  let grp=null;$('ptabs').innerHTML=items.map(([id,l])=>{const g=typeof meGroup==='function'?meGroup(id):null,gg=g&&GGROUPS.find(x=>x[0]===g);
    const head=g&&g!==grp?`<div class="mgrp">${esc(t(gg[1],gg[2]))}</div>`:'';if(g)grp=g;
    return head+`<button type="button" data-t="${id}">${esc(l)}<small class="mst" data-st="${id}"></small></button>`}).join('');
  $('ptabs').querySelectorAll('button').forEach(b=>b.onclick=()=>{meLast=b.dataset.t;ptab(b.dataset.t)});ME_ITEMS=items;
  $('profmodal').classList.toggle('one',items.length<2);if(typeof meSearchMount==='function')meSearchMount();return items.map(x=>x[0])}
let meLast='overbox',ME_ITEMS=[],ME_ONLY=new Set();
// "Überblick": one line per page with its state, read from the pages just loaded (no extra requests)
function meState(){const n=id=>id==='factlist'?FACTS.length:[...document.querySelectorAll('#'+id+'>li')].filter(x=>!x.classList.contains('mut')&&!x.classList.contains('ic-more')).length;
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
  if(!box)return;let grp=null;const su=typeof SETUP!=='undefined'&&SETUP&&SETUP.open>0?SETUP:null;
  box.innerHTML=(su?`<button type="button" class="overrow gorow" data-go="gobox"><b>${esc(t('Los geht\'s','Let\'s go'))}</b><span>${esc(t('Einrichten ','Setup ')+su.done+t(' von ',' of ')+su.total)}</span></button>`:'')+`<div class="intro">${esc(t('Alles, was du für dich eingerichtet hast. Antippen öffnet die Seite.','Everything you set up for yourself. Tap to open the page.'))}</div><div class="overlist">`+
    ME_ITEMS.filter(([id])=>id!=='overbox'&&id!=='loginbox').map(([id,l])=>{const g=typeof meGroup==='function'?meGroup(id):null,gg=g&&GGROUPS.find(x=>x[0]===g);
      const head=g&&g!==grp?`<div class="mgrp">${esc(t(gg[1],gg[2]))}</div>`:'';if(g)grp=g;
      return head+`<button type="button" class="overrow" data-go="${id}"><b>${esc(l)}</b><span>${esc(st[id]||'')}</span></button>`}).join('')+'</div>';
  box.querySelectorAll('[data-go]').forEach(b=>b.onclick=()=>{meLast=b.dataset.go;ptab(b.dataset.go);if(b.dataset.go==='gobox'&&typeof goShow==='function')goShow()});
  if(FEATS)meReleased(box,FEATS.features);   // drawn anew: the line from /api/features stays
  if(typeof tipOver==='function')tipOver(box)}
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
function calRender(d){$('callist').innerHTML=d.calendars.map(c=>`<li><span><b>${esc(c.name)}</b><br><small class="mut">${esc(c.url.replace(/^\w+:\/\//,'').slice(0,48))}</small></span><button class="b" ${onAttr('calRemove',c.id,c.name)}>${t('Entfernen','Remove')}</button></li>`).join('')||`<li class="mut">${t('Noch kein Kalender verbunden.','No calendar connected yet.')}</li>`;
  $('caltopics').value=(d.topics||[]).join(', ');calKind();$('caltest').style.display=d.calendars.length?'':'none';$('caladd').open=!d.calendars.length}
async function showCal(){if(!CAL_ON)return;calRender(await (await api('/api/profile/calendar')).json());$('calmsg').textContent='';$('calmsg').className=''}
async function calRemove(id,name){if(!confirm(t('Kalender „','Remove calendar "')+name+t('“ entfernen?','"?')))return;calRender(await (await api('/api/profile/calendar/'+encodeURIComponent(id),{method:'DELETE'})).json())}
const calMsg=(x,err,list)=>{const m=$('calmsg');m.className=err?'err':'';m.innerHTML=esc(x)+(list&&list.length?'<ul class="facts small">'+list.map(e=>`<li>${esc(e)}</li>`).join('')+'</ul>':'')};
$('calsave').onclick=async()=>{calMsg(t('Prüfe den Kalender …','Checking the calendar …'));
  const {r,d}=await apiTry('/api/profile/calendar',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name:$('calname').value,url:$('calurl').value.trim(),user:$('caluser').value.trim(),password:$('calpw').value,tz:TZ()})});
  if(!r.ok){calMsg(t('Nicht hinzugefügt: ','Not added: ')+errSay(r.status,d.detail,""),true);return}
  ['calname','calurl','caluser','calpw'].forEach(i=>$(i).value='');calRender(d);
  calMsg(t('Hinzugefügt. ','Added. ')+(d.check.events.length?t('Die nächsten Termine:','Next appointments:'):t('Keine Termine in den nächsten 14 Tagen.','No appointments in the next 14 days.')),false,d.check.events)};
$('caltopsave').onclick=async()=>{const d=await (await api('/api/profile/calendar/topics',{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({topics:$('caltopics').value.split(',').map(x=>x.trim()).filter(Boolean)})})).json();calRender(d);calMsg(t('Themen gespeichert.','Topics saved.'))};
$('caltest').onclick=async()=>{calMsg(t('Lese die Kalender …','Reading the calendars …'));
  let d;try{d=await (await api('/api/profile/calendar/test',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({tz:TZ()})})).json()}catch(e){calMsg(e.message,true);return}
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
function mailRender(d){if(window.showMailTidy&&d&&TIDY&&d.accounts.length!==TIDY.accounts.length)showMailTidy().catch(()=>{});if(window.showMailStil&&d&&MSTIL&&d.accounts.length!==MSTIL.boxes.length)showMailStil().catch(()=>{});$('maillist').innerHTML=d.accounts.map(a=>`<li><span><b>${esc(a.name)}</b><br><small class="mut">${esc(a.user)} · ${esc(a.host)}</small></span><button class="b" ${onAttr('mailRemove',a.id,a.name)}>${t('Entfernen','Remove')}</button></li>`).join('')||`<li class="mut">${t('Noch kein Postfach verbunden.','No mailbox connected yet.')}</li>`;
  mailKind();$('mailtest').style.display=d.accounts.length?'':'none';$('mailadd').open=!d.accounts.length}
async function showMail(){if(!MAIL_ON)return;mailRender(await (await api('/api/profile/mail')).json());mailMsg('')}
async function mailRemove(id,name){if(!confirm(t('Postfach „','Remove mailbox "')+name+t('“ entfernen?','"?')))return;mailRender(await (await api('/api/profile/mail/'+encodeURIComponent(id),{method:'DELETE'})).json())}
$('mailsave').onclick=async()=>{mailMsg(t('Prüfe das Postfach …','Checking the mailbox …'));
  const {r,d}=await apiTry('/api/profile/mail',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({kind:$('mailkind').value,name:$('mailname').value,host:$('mailhost').value.trim(),port:$('mailport').value.trim(),user:$('mailuser').value.trim(),password:$('mailpw').value})});
  if(!r.ok){mailMsg(t('Nicht hinzugefügt: ','Not added: ')+errSay(r.status,d.detail,""),true);return}
  ['mailname','mailhost','mailuser','mailpw'].forEach(i=>$(i).value='');mailRender(d);
  mailMsg(t('Hinzugefügt. ','Added. ')+d.check.unread+t(' ungelesen, ',' unread, ')+d.check.total+t(' Mails in den letzten ',' mails in the last ')+d.check.days+t(' Tagen.',' days.'))};
$('mailtest').onclick=async()=>{mailMsg(t('Lese die Postfächer …','Reading the mailboxes …'));
  let d;try{d=await (await api('/api/profile/mail/test',{method:'POST'})).json()}catch(e){mailMsg(e.message,true);return}
  mailMsg('',d.accounts.some(a=>!a.ok),d.accounts.map(a=>a.name+': '+(a.ok?a.unread+t(' ungelesen',' unread'):'⚠ '+a.error)))};
// Home Assistant per profile; the token is never sent back, only whether one is stored.
const haMsg=(x,err)=>{$('hamsg').textContent=x;$('hamsg').className='fh'+(err?' err':'')};
function haRender(d){$('haurl').value=d.url||'';$('hatoken').value='';$('hanoverify').checked=d.verify===false;$('haagent').value=d.agent||'';
  $('hatoken').placeholder=d.has_token?t('gespeichert, leer lassen zum Behalten','stored, leave empty to keep'):'';
  $('hastate').textContent=d.has_token?t('Verbunden mit ','Connected to ')+d.url:t('Noch nicht verbunden.','Not connected yet.');$('hadel').style.display=d.has_token?'':'none';
  $('hacodebox').style.display=d.has_token?'':'none';$('hacode').value='';$('hacode').placeholder=d.code_old?t('bitte neu eingeben und speichern','please enter and save again'):d.has_code?t('gesetzt, leer speichern zum Entfernen','set, save empty to remove'):t('kein Codewort','no code word')}
async function showHa(){if(!HA_ON)return;haRender(await (await api('/api/profile/homeassistant')).json());haMsg('')}
$('hasave').onclick=async()=>{haMsg(t('Prüfe die Verbindung …','Checking the connection …'));
  const {r,d}=await apiTry('/api/profile/homeassistant',{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({url:$('haurl').value.trim(),token:$('hatoken').value.trim(),verify:!$('hanoverify').checked,agent:$('haagent').value.trim()})});
  if(!r.ok){haMsg(t('Nicht gespeichert: ','Not saved: ')+errSay(r.status,d.detail,""),true);return}haRender(d);haMsg(t('Verbunden und gespeichert.','Connected and saved.'))};
$('hadel').onclick=async()=>{if(!confirm(t('Home Assistant trennen?','Disconnect Home Assistant?')))return;haRender(await (await api('/api/profile/homeassistant',{method:'DELETE'})).json());haMsg(t('Getrennt.','Disconnected.'))};
$('hacodesave').onclick=async()=>{const {r,d}=await apiTry('/api/profile/homeassistant/code',{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({code:$('hacode').value})});
  if(!r.ok){haMsg(errSay(r.status,d.detail,""),true);return}haRender(d);haMsg(d.has_code?t('Codewort gespeichert.','Code word saved.'):t('Codewort entfernt.','Code word removed.'))};
$('hatrygo').onclick=async()=>{const text=$('hatry').value.trim();if(!text)return;haMsg(t('Frage Home Assistant …','Asking Home Assistant …'));
  let d;try{d=await (await api('/api/profile/homeassistant/test',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({text})})).json()}catch(e){haMsg(e.message,true);return}haMsg((d.targets&&d.targets.length?d.targets.join(', ')+': ':'')+d.answer,!d.ok)};
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
  b.innerHTML=`<div class="ic-note tidyhead"><div class="ic-mid"><b>${t('Aufräum-Vorschlag bereit','Cleanup proposal ready')}</b><span>${p.merge.length?t(`${p.merge.length}× zusammenfassen`,`merge ${p.merge.length}×`):''}${p.merge.length&&p.drop.length?' · ':''}${p.drop.length?t(`${p.drop.length} überholt`,`${p.drop.length} outdated`):''}. ${t('Es ändert sich erst etwas, wenn du übernimmst.','Nothing changes until you apply it.')}</span></div></div><ul>`+
    p.merge.map(m=>`<li>${t('Zusammenfassen','Merge')}: ${m.old.map(x=>'„'+esc(x)+'“').join(' + ')}<br>→ „${esc(m.text)}“</li>`).join('')+
    p.drop.map(x=>`<li>${t('Entfernen','Remove')}: „${esc(x.old)}“${x.why?` <small class="mut">(${esc(x.why)})</small>`:''}</li>`).join('')+
    `</ul><div class="row"><button class="b p" ${onAttr('tidyDo','accept')}>${t('Übernehmen','Apply')}</button><button class="b" ${onAttr('tidyDo','reject')}>${t('Verwerfen','Discard')}</button></div>`}
window.tidyDo=async what=>{$('factmsg').textContent=what==='check'?t('Der Assistent sieht sich dein Gedächtnis an …','The assistant is looking at your memory …'):'';
  try{const r=await (await api('/api/profile/memory/tidy',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({do:what})})).json();
    if(what==='check')$('factmsg').textContent=r.tidy?'':t('Nichts aufzuräumen.','Nothing to tidy up.');
    if(what==='accept')$('factmsg').textContent=t('Aufgeräumt.','Tidied up.');
    await showFacts()}
  catch(e){$('factmsg').innerHTML=`<span class="err">${esc(e.message)}</span>`}};
$('facttidy').onclick=()=>tidyDo('check');
window.forgetFact=async id=>{await api('/api/profile/memory/'+encodeURIComponent(id),{method:'DELETE'});showFacts()};
ON.forgetFact=(b,id)=>forgetFact(id);ON.tidyDo=(b,w)=>tidyDo(w);ON.calRemove=(b,id,n)=>calRemove(id,n);ON.mailRemove=(b,id,n)=>mailRemove(id,n);ON.secDrop=(b,id,n,s)=>secDrop(id,n,s);
async function openMe(tab){if(typeof whoPendingGo==='function'&&PROFILE&&whoPendingGo({me:tab||''}))return;   // saved functions wait: Ich opens with them
  $('profmsg').textContent='';$('profmodal').style.display='grid';
  const tabs=meTabs(),list=tab==='list'&&PHONE.matches&&tabs.length>1;meOwn();ptab(tabs.includes(tab)?tab:tabs.includes(meLast)?meLast:tabs[0],!list);
  $('profhead').textContent=PROFILE?PROFILE.name:GATE?t('Anmelden','Sign in'):t('Gast','Guest');
  $('setscope').textContent=GATE?'':PROFILE?((k=>ME_SUB[k]?t(...ME_SUB[k]):'')((document.querySelector('#ptabs button.on')||{dataset:{}}).dataset.t)):isGuest()?t('Als Gast gelten die Vorgaben des Admins. Mit einem Profil kannst du Einstellungen ändern, und der Assistent merkt sich Dinge nur für dich.','As a guest the admin\'s defaults apply. With a profile you can change settings, and the assistant remembers things just for you.'):t('Als Gast gelten die Einstellungen nur in diesem Browser. Mit einem Profil merkt sich der Assistent Dinge nur für dich.','As a guest the settings apply only in this browser. With a profile the assistant remembers things just for you.');
  $('proflogout').style.display=PROFILE?'':'none';$('profclose').style.display=GATE?'none':'';
  if(!GATE&&!isGuest())renderSet($('setform'),S,saveSet);
  // what the admin allows can have changed since the login (Funktionen in this browser or another): ask again
  if(PROFILE){refreshAllow().catch(()=>{});if(typeof hilfeRefresh==='function')hilfeRefresh()}
  // the locked notice needs only /api/features: draw it now, not after a queued load of all boxes (slow on a busy runner)
  if(PROFILE)loadFeats().then(()=>{meLocked($('overbox'));meLocked($('setbox'))}).catch(()=>{});
  if(PROFILE){   // B8: jumps while the boxes load ("Zeig mir wo", cards) share one load and at most one after it (no 429)
    if(ME_LOAD.p){if(!ME_LOAD.next)ME_LOAD.next=ME_LOAD.p.then(()=>{ME_LOAD.next=null;return meLoadOnce()});return ME_LOAD.next}
    return meLoadOnce()}
  $('profpin').value='';if(tab==='loginbox')setTimeout(()=>$($('profuser').value?'profpin':'profuser').focus(),50)}
// the ~30 boxes of Ich, one load at a time
function meLoadOnce(){if(!PROFILE)return;return ME_LOAD.p=meLoad().finally(()=>{ME_LOAD.p=null})}
// Ich's boxes side by side, at most four loads at a time (plan seiten-laden.md; before: one after the other, so a
// slow calendar or mail server held up every box after it). Each box shows its placeholders, „dauert länger …“ and
// its own error with „Noch einmal“ (laden.js ladeBox); one failing box takes nothing from the others. Only a 401,
// the profile's login has ended, still signs out (before: any error looked like being signed out).
// [box, load, quiet]: quiet boxes stay silent on an error, as they were before
async function meLoad(){let out=false;
  const jobs=[['factbox',async()=>{await showFacts();if(window.meMaps)await meMaps()}],['docbox',showDocs],['voicebox',showVoice],['calbox',showCal],['mailbox',async()=>{await showMail();await Promise.all([showMailTidy().catch(()=>{}),showMailStil().catch(()=>{})])}],
    ['habox',showHa],['secbox',showSecurity],['logbox',showToolLog],['probox',showPro,1],['pushbox',showPush,1]].concat(typeof extrasJobs==='function'?extrasJobs():[]);
  await lzPool(jobs.map(([id,f,quiet])=>()=>lzb($(id),f,{auth:true,quiet:!!quiet}).catch(e=>{if(e&&e.status===401)out=true})),4);
  if(out){setProfile(null);openMe('loginbox');return}
  showRoom();showOver();meOwn();if(typeof goShow==='function')goShow();if(window.meBerater)meBerater();loadFeats().then(()=>{meLocked($('overbox'));meLocked($('setbox'));if(window.meToday)meToday()}).catch(()=>{})}
window.openMe=openMe;
// Ich says what the admin has not switched on instead of hiding it without a word (plan „Vereinheitlichen“ Phase 4,
// V01.0.270): the names with the reason, for an admin a jump to Funktionen (off) or Personen und Geräte → Gesperrte Funktionen (blocked).
// From /api/features.
let FEATS=null;
async function loadFeats(){if(!PROFILE){FEATS=null;return}try{FEATS=await (await api('/api/features')).json()}catch{FEATS=null}}
function meLocked(box){if(!box)return;let el=box.querySelector(':scope>.melocked');
  const all=FEATS?FEATS.features:[],off=all.filter(f=>f.why==='spark'&&f.me&&!f.parent),blk=all.filter(f=>f.why==='blocked'&&!f.parent);
  if(box.id==='overbox')meReleased(box,all);
  if(!off.length&&!blk.length){if(el)el.remove();return}
  if(!el){el=document.createElement('div');el.className='melocked';box.appendChild(el)}
  el.textContent='';
  const part=(head,list,tail)=>{if(!list.length)return;const h=document.createElement('div');h.className='mgrp';h.textContent=head;
    const p=document.createElement('p');p.className='fh';p.textContent=list.map(f=>f.name[L==='en'?1:0]).join(', ')+'. '+tail;el.append(h,p)};
  part(t('Vom Admin nicht eingeschaltet','Not switched on by the admin'),off,ADMIN?'':t('Frag den Admin, wenn du etwas davon nutzen möchtest.','Ask the admin if you would like to use one of them.'));
  // blocked for this one profile by the admin (chat.deny): only the admin lifts it (Dominik 2026-10-13)
  part(t('Vom Admin für dich gesperrt','Blocked for you by the admin'),blk,ADMIN?'':t('Nur der Admin kann das aufheben.','Only the admin can lift this.'));
  // for an admin: what is off to Funktionen, what is blocked to Personen und Geräte → Gesperrte Funktionen
  const jump=(l,s)=>{const b=document.createElement('button');b.type='button';b.className='b';b.textContent=l;
    b.onclick=()=>{if(window.closeProf)closeProf();goSec(s)};el.appendChild(b)};
  if(ADMIN&&off.length)jump(t('Funktionen','Features'),'feat');
  if(ADMIN&&blk.length)jump(t('Gesperrte Funktionen','Blocked functions'),'prof')}
// Gesperrt, aber eigene Daten da (whoami "locked", features.OWN; Dominik 2026-10-14 „Auf der Seite nur „Daten
// löschen“ zeigen“): in place of the page or part of a function the admin blocked for this profile only a short note,
// the number of stored entries and „Daten löschen“. The page itself stays hidden (class ownonly); after deleting the
// card goes, and a page that showed only for it leaves the list.
function meOwnBoxes(){return new Set(ME_OWN.map(x=>x.box).filter(Boolean))}
function meOwn(){document.querySelectorAll('#profmodal .ptab').forEach(b=>{b.classList.toggle('ownonly',ME_ONLY.has(b.id));
    b.querySelectorAll(':scope>.meown').forEach(e=>{if(!ME_OWN.some(x=>x.key===e.dataset.own&&x.box===b.id))e.remove()})});
  for(const x of ME_OWN){const box=x.box&&$(x.box);if(!box)continue;
    let el=[...box.querySelectorAll(':scope>.meown')].find(e=>e.dataset.own===x.key);
    if(!el){el=document.createElement('div');el.className='meown';el.dataset.own=x.key;box.prepend(el)}
    const name=(x.name||[x.key,x.key])[L==='en'?1:0],p=document.createElement('p'),b=document.createElement('button'),msg=document.createElement('p');
    p.textContent=t(`Der Admin hat „${name}“ für dich gesperrt (Personen und Geräte → Gesperrte Funktionen). Gespeichert: ${x.n} ${x.n===1?'Eintrag':'Einträge'}.`,
      `The admin blocked "${name}" for you (People and devices → Blocked functions). Stored: ${x.n} ${x.n===1?'entry':'entries'}.`);
    b.type='button';b.className='b danger';b.textContent=t('Daten löschen','Delete data');msg.className='fh';
    b.onclick=()=>meOwnDelete(x,name,el,msg);el.replaceChildren(p,b,msg)}}
async function meOwnDelete(x,name,el,msg){
  if(!confirm(t(`Deine gespeicherten Daten zu „${name}“ löschen? Das lässt sich nicht rückgängig machen.`,`Delete your stored data of "${name}"? This cannot be undone.`)))return;
  msg.textContent=t('Lösche …','Deleting …');msg.className='fh';
  const {r,d}=await apiTry('/api/profile/owndata/'+encodeURIComponent(x.key),{method:'DELETE'});
  if(!r.ok){msg.textContent=t('Nicht gelöscht: ','Not deleted: ')+errSay(r.status,d.detail,'');msg.className='fh err';return}
  ME_OWN=ME_OWN.filter(y=>y.key!==x.key);el.remove();
  const tabs=meTabs();meOwn();if(!tabs.includes(x.box)&&$('profmodal').style.display==='grid'){meLast=tabs[0];ptab(tabs[0],!PHONE.matches)}}
// Ich → Überblick: one line how many functions this profile may use now (what the admin released and did not block)
function meReleased(box,all){let el=box.querySelector(':scope>.mefree');
  if(!all.length){if(el)el.remove();return}
  if(!el){el=document.createElement('p');el.className='fh mefree';const i=box.querySelector(':scope>.intro');if(i)i.after(el);else box.prepend(el)}
  const n=all.filter(f=>f.can===true).length;
  el.textContent=n===1?t('Für dich freigegeben: 1 Funktion','Released for you: 1 function'):t(`Für dich freigegeben: ${n} Funktionen`,`Released for you: ${n} functions`)}
$('profbtn').onclick=()=>openMe(PHONE.matches?'list':meLast);
$('navme').onclick=()=>openMe(meLast);   // phones: the list of pages; else the last page (first time: Überblick)
$('profuser').onkeydown=e=>{if(e.key==='Enter')$('profpin').focus()};
$('profpin').onkeydown=e=>{if(e.key==='Enter')$('proflogin').click()};
$('profcode').onkeydown=e=>{if(e.key==='Enter')$('proflogin').click()};
$('proflogin').onclick=async()=>{try{const r=await (await api('/api/profile/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name:$('profuser').value,pin:$('profpin').value,code:$('profcode').value,trust:$('proftrust').checked})})).json();
    if(r.code){$('profcodebox').style.display='';$('profmsg').textContent='';$('profcode').focus();  // second step: code next (or a passkey)
      if(window.pkLoginOffer)pkLoginOffer($('profcodebox'),r.passkey,async(pk)=>{if(!pk){$('profmsg').textContent=t('Passkey abgebrochen. Der Code geht auch.','Passkey cancelled. The code works too.');return}
        try{await api('/api/profile/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name:$('profuser').value,pin:$('profpin').value,passkey:pk,trust:$('proftrust').checked})});location.reload()}
        catch(e){$('profmsg').textContent=t('Passkey nicht angenommen.','Passkey not accepted.')}});return}
    $('profcode').value='';$('profcodebox').style.display='none';
    if(GATE||r.admin){location.reload();return}   // an admin profile: the page loads again with the admin menu
    const who=await (await api('/api/whoami')).json();SETUP=who.setup||null;setProfile(who.profile);if(typeof hilfeStart==='function')hilfeStart(who.hilfe);closeProf()}
  catch(e){$('profmsg').textContent=/too many/.test(errRaw(e))?t('Zu viele falsche Versuche. Bitte später noch einmal (','Too many wrong attempts. Please try again later (')+(errRaw(e).match(/in (.+)$/)||['',''])[1]+').':/wrong code/.test(errRaw(e))?t('Code falsch.','Wrong code.'):t('Name oder PIN falsch.','Wrong name or PIN.')}};
$('proflogout').onclick=async()=>{await /*raw: logout must not open the login or a code prompt*/fetch('/api/profile/logout',{method:'POST'});offlineWipe(true);if(!PUBLIC&&!ADMIN||elevated()){location.reload();return}setProfile(null);if(typeof hilfeStart==='function')hilfeStart(null);closeProf()};
$('factclear').onclick=async()=>{if(!confirm(t('Alles vergessen, was sich der Assistent über dich gemerkt hat?','Forget everything the assistant remembered about you?')))return;
  await api('/api/profile/memory',{method:'DELETE'});showFacts()};
// ---------------------------------------------------------------- conversation settings
let ALLOW={};
const SETF=[
  {g:t('Zuhören','Listening'),k:'hands',type:'bool',l:t('Freihändig','Hands-free'),h:t('Nach der Antwort automatisch wieder zuhören.','Listen again automatically after each answer.')},
  {k:'follow',type:'sel',prof:1,need:'follow',preset:1,l:t('Rückfrage ohne Weckwort','Follow-up without wake word'),h:t('Nach der Antwort auf eine gesprochene Frage hört der Assistent noch kurz zu, z. B. für „Und morgen?“. Danach braucht es wieder „Hey Spark“ oder „Sprechen“.','After answering a spoken question the assistant keeps listening briefly, e.g. for "And tomorrow?". After that it needs "Hey Spark" or "Speak" again.'),o:{0:t('aus','off'),4:t('4 Sekunden','4 seconds'),6:t('6 Sekunden','6 seconds'),8:t('8 Sekunden','8 seconds'),10:t('10 Sekunden','10 seconds')}},
  {k:'echo',type:'bool',prof:1,need:'echo',preset:1,l:t('Eigene Stimme überhören','Ignore my own voice'),h:t('Hört dieses Gerät, wie ein anderes Gerät gerade antwortet (Lautsprecher, iPhone), nimmt der Assistent das nicht als Frage.','When this device hears another device answering (speaker, iPhone), the assistant does not take it as a question.')},
  {k:'auto',type:'bool',l:t('Bei Stille beenden','Stop on silence'),h:t('Die Aufnahme endet von selbst, wenn du aufhörst zu sprechen.','Recording ends by itself when you stop talking.')},
  {k:'turn',type:'bool',l:t('Natürlicher Sprecherwechsel','Natural turn-taking'),h:t('Erkennt am Satz, ob du fertig bist: Ein fertiger Satz wird sofort beantwortet, bei „und …“, „weil …“ oder „ähm“ wartet der Assistent länger.','Tells from the sentence whether you are done: a finished sentence is answered at once, after "and …", "because …" or "um" the assistant waits longer.')},
  {k:'live',type:'bool',l:t('Live-Transkript','Live transcript'),h:t('Text schon beim Sprechen zeigen; die Antwort kommt etwas früher.','Show the text while you speak; the answer comes a little sooner.')},
  {k:'barge',type:'bool',l:t('Ins Wort fallen','Barge in'),h:t('Losreden unterbricht die Antwort (am besten mit Kopfhörer).','Start talking to interrupt the answer (best with headphones).')},
  {k:'barge_level',type:'sel',l:t('Empfindlichkeit','Sensitivity'),h:t('Wie leicht Geräusche die Antwort unterbrechen.','How easily sounds interrupt the answer.'),o:{low:t('gering','low'),mid:t('mittel','medium'),high:t('hoch','high')}},
  {g:t('Antwort','Answer'),k:'speak',type:'bool',l:t('Antworten vorlesen','Read answers aloud'),h:t('Aus: Antworten nur als Text, auf all deinen Geräten. Lautsprecher ohne Bildschirm und CarPlay sprechen weiter.','Off: answers as text only, on all your devices. Speakers without a screen and CarPlay keep speaking.')},
  {k:'voice',type:'voice',l:t('Stimme','Voice'),h:t('Leer = Standardstimme des Servers.','Empty = the server\'s default voice.')},
  {k:'speed',type:'range',l:t('Sprechtempo','Speaking rate'),h:t('Schneller oder langsamer, ohne die Stimmlage zu ändern. Über 1,0 hält der Spark bei langen Antworten mehr Ton auf Vorrat, damit nichts aussetzt.','Faster or slower without changing the pitch. Above 1.0 the Spark keeps more audio in stock during long answers, so nothing drops out.'),step:0.05},
  {k:'length',type:'sel',l:t('Antwortlänge','Answer length'),h:t('Wie ausführlich der Assistent antwortet.','How detailed the assistant answers.'),o:{short:t('kurz','short'),normal:t('normal','normal'),long:t('ausführlich','detailed')}},
  {k:'learn',type:'bool',prof:1,l:t('Aus Gesprächen lernen','Learn from conversations'),h:t('Nach einem Gespräch merkt sich der Assistent wenige dauerhafte Dinge über dich. Du siehst und löschst sie unter Ich.','After a conversation the assistant remembers a few lasting things about you. You can see and delete them under the Me.')},
  {g:t('Wissen und Stil','Knowledge and style'),k:'style',type:'text',prof:1,need:'style',max:500,l:t('So soll der Assistent mit mir reden','How the assistant should talk to me'),h:t('In eigenen Worten, z. B. „Sprich mich mit Dominik an und antworte locker.“ Ändert nur den Ton, nie die Regeln. Leer = aus.','In your own words, e.g. "Call me Dominik and answer casually." Changes the tone only, never the rules. Empty = off.')},
  {k:'roles',type:'text',prof:1,need:'roles',max:1500,l:t('Meine Rollen','My roles'),h:t('Eine Rolle pro Zeile, höchstens 8: „Name: wie der Assistent dann antwortet“, z. B. „Butler: höflich, trocken, mit britischem Understatement“. Ändert nur den Ton, nie die Regeln.','One role per line, at most 8: "Name: how the assistant then answers", e.g. "Butler: polite, dry, with British understatement". Changes the tone only, never the rules.')},
  {g:t('Geräte','Devices'),k:'devup_night',type:'bool',prof:1,need:'devup_night',l:t('Meine Lautsprecher nachts aktualisieren','Update my speakers at night'),h:t('Nachts startet der Spark deine Lautsprecher mit „Updates von selbst“ einzeln neu, damit sie die neue Firmware holen; nie während jemand mit ihnen spricht.','At night the Spark restarts your speakers with "Updates by themselves" one by one so they fetch the new firmware; never while someone talks to them.')},
  // Dienst-Wächter (dienstwacht.py): the notes only for admin profiles (only: those rows stay away for the others)
  {g:t('Dienste','Services'),k:'svc_note',type:'bool',prof:1,need:'svcwatch',only:'svcadmin',l:t('Hinweise bei Ausfällen','Notes on outages'),h:t('Ist ein Dienst wie das Archiv, das Internet, die Websuche oder Home Assistant ein paar Minuten weg, bekommst du einen Hinweis und eine Entwarnung, wenn er zurück ist. Kurze Wackler melden sich nicht.','When a service such as the archive, the internet, the web search or Home Assistant is gone for a few minutes, you get a note, and another when it is back. Short wobbles stay quiet.')},
  {k:'svc_device',type:'sel',prof:1,need:'svcwatch',only:'svcadmin',l:t('Hinweise auf diesem Gerät','Notes on this device'),h:t('Wohin die Hinweise gehen. Ist das gewählte Gerät nicht eingerichtet, geht es wie sonst an das zuletzt benutzte. Ohne Internet kommen iPhone und Telegram erst danach an; Android-App, Begleiter und Browser holen sie im Heimnetz.','Where the notes go. When the chosen device is not set up, they go to the one used last as usual. Without internet the iPhone and Telegram get them only afterwards; the Android app, the companion and the browser fetch them at home.'),
   o:{'':t('zuletzt benutztes Gerät','device used last'),app:t('iPhone-App','iPhone app'),and:t('Android-App','Android app'),desk:t('Spark-Begleiter','Spark companion'),tg:'Telegram',web:t('Browser','browser'),all:t('alle eingerichteten','all set up')}},
  {k:'svc_night',type:'bool',prof:1,need:'svcwatch',only:'svcadmin',l:t('Nachts nur sammeln','Only collect at night'),h:t('Zwischen 22 und 7 Uhr kommt nichts; um 7 Uhr eine Zusammenfassung, was in der Nacht weg war und ob es noch fehlt.','Nothing between 10 pm and 7 am; at 7 one summary of what was gone in the night and whether it is still missing.')},
  // Chats (chats.py): writing with other profiles like in a messenger; the admin allows it under Funktionen → Chats
  {g:t('Chats','Chats'),k:'chat_receipts',type:'bool',prof:1,need:'chats',l:t('Lesebestätigung','Read receipts'),h:t('Andere sehen zwei blaue Haken, wenn du ihre Nachricht gelesen hast. Ausgeschaltet siehst du es bei ihnen auch nicht.','Others see two blue ticks when you have read their message. Switched off, you do not see it for them either.')},
  {k:'chat_push_text',type:'bool',prof:1,need:'chats',l:t('Text in der Mitteilung','Text in the notification'),h:t('Aus: Die Mitteilung auf dem Handy sagt nur „Neue Nachricht“ und von wem. An: Sie zeigt auch den Anfang des Textes, auch auf dem Sperrbildschirm.','Off: the notification on the phone only says "New message" and from whom. On: it also shows the start of the text, also on the lock screen.')},
  {k:'msg_from',type:'sel',prof:1,need:'chats',l:t('Wer darf mir schreiben','Who may write to me'),h:t('Alle Profile mit Chats, oder nur die, die du darunter auswählst. Gesperrte erreichen dich nie; sie erfahren nicht, dass du sie gesperrt hast.','Every profile with chats, or only the ones you pick below. Blocked ones never reach you; they do not learn that you blocked them.'),o:{all:t('alle Profile mit Chats','every profile with chats'),chosen:t('nur ausgewählte','only picked ones')}},
  {k:'msg_speaker',type:'sel',prof:1,need:'chats',l:t('Neue Nachrichten auf meinem Lautsprecher','New messages on my speaker'),h:t('Dein eigener Lautsprecher sagt neue Chat-Nachrichten: sofort, wenn keine Seite offen ist, sonst beim nächsten Weckwort innerhalb von zwei Stunden. Nie in deiner Ruhezeit, nie aus stummen Chats; aus privaten Chats nur, von wem. Den Text liest er nie ungefragt in den Raum: Mit „auf Wunsch vorlesen“ sagt er „Lies die Nachricht vor“ dazu und liest sie, wenn er deine Stimme erkennt (Sprechererkennung an, Stimme angelernt).','Your own speaker says new chat messages: at once when no page is open, else at the next wake word within two hours. Never in your quiet hours, never from muted chats; from private chats only who. It never reads the text into the room unasked: with "read on request" it adds "say: read the message" and reads it when it recognizes your voice (speaker ID on, voice taught).'),o:{off:t('nichts sagen','say nothing'),hint:t('nur sagen, von wem','say only who wrote'),text:t('von wem, Text auf Wunsch vorlesen','who wrote, read the text on request')}},
  {k:'msg_all',type:'bool',prof:1,need:'chatall',only:'chatall',l:t('Nachricht an alle','Message to everybody'),h:t('Du bist in der festen Gruppe „Alle“ und kannst „Sag allen …“ sagen. Höchstens fünf Nachrichten an alle pro Stunde. Steht von Anfang an an; ausgeschaltet verlässt du die Gruppe.','You are in the fixed group "Alle" (everybody) and can say "Tell everybody …". At most five messages to everybody per hour. On from the start; switched off, you leave the group.')},
  // Einstellungs-Assistent (faelle.py, berater.py): 👍/👎, the feedback, and for admin profiles its notes and questions
  {g:t('Verbessern','Improve'),k:'rate_back',type:'bool',prof:1,need:'rateback',l:t('Sagen, wenn es behoben ist','Tell me when it is fixed'),h:t('Hat eine Änderung nach deinem 👎 geholfen, bekommst du einmal einen Hinweis.','When a change after your 👎 helped, you get one note.')},
  {k:'berater_note',type:'bool',prof:1,need:'beratnote',only:'berateradmin',l:t('Hinweis bei neuem Vorschlag','Note on a new proposal'),h:t('Gibt es einen neuen Vorschlag unter Zustand → Verbessern, bekommst du einen Hinweis, höchstens drei am Tag.','When there is a new proposal under Status → Improve, you get a note, at most three a day.')},
  // Gesicht (plaene/suche-gesicht.md): the profile's own face on all its devices; "" = the Spark's (Einstellungen → Vorgaben).
  // me: only on the own page, never a preset of the admin (who picks the Spark's face itself)
  {g:t('Anzeige','Display'),k:'face',type:'face',prof:1,me:1,l:t('Gesicht','Face'),h:t('Nur für dich, auf all deinen Geräten: Panel, iPhone, Mac, Windows und Pebble.','Just for you, on all your devices: panel, iPhone, Mac, Windows and Pebble.')},
  {k:'daily',type:'bool',l:t('Jeden Tag neues Gespräch','New conversation every day'),h:t('Am nächsten Tag beginnt automatisch ein neues Gespräch; die alten bleiben im Verlauf.','The next day a new conversation starts by itself; older ones stay in the history.')},
  {k:'timing',type:'bool',l:t('Zeiten anzeigen','Show timings'),h:t('Wie lange Erkennung, Modell und erster Ton gebraucht haben.','How long recognition, model and first audio took.')},
  {g:t('Datenschutz','Privacy'),k:'trace_name',type:'bool',prof:1,need:'trace',l:t('Mein Name im Anfragen-Log','My name in the request log'),h:t('Unter Zustand → Logs → Anfragen sieht der Admin, welchen Weg deine Anfragen nehmen (Werkzeuge, Zeiten), nie was du fragst oder was die Antwort war. Mit diesem Schalter stehen dort dein Name und dein Gerät, sonst nur „Profil“. Ändern nur in deiner eigenen Anmeldung im Browser.','Under Status → Logs → Requests the admin sees which way your requests take (tools, times), never what you ask or what the answer was. With this switch your name and device show there, otherwise only "Profile". Can only be changed in your own browser login.')}];
{let g;SETF.forEach(f=>{g=f.g||g;f.grp=g})}
// asked again each time the settings open: an empty answer (TTS still loading) must not stick for the page's life,
// and the admin's list is not the profile's
async function voiceList(admin){if(!PROFILE&&!admin)return [];try{return ((await (await api(admin?'/api/tts/voices':'/api/assistant/voices')).json()).voices||[]).filter(x=>typeof x==='string')}catch{return []}}
// Builds the settings rows into el; onchange(key, value) after each change. Returns a getter. Waits for the Spark's
// defaults and lists (setReady); the profile's own rows always show S as it is then, the admin's (no onchange) vals.
async function renderSet(el,vals,onchange){const admin=!onchange;await setReady();const voices=await voiceList(admin);const v={...(admin?vals:S)};
  // which values a list has and in which order: only the Spark's (SETC.choices); the words for them stay here (f.o)
  const opts=f=>(SETC.choices[f.k]||[]).map(a=>[String(a),f.o?f.o[a]??String(a):String(a)]),rng=SETC.ranges;
  // guests: default voice, nothing learned. need: a switch of the admin; switched off it stays visible, locked with
  // the reason (V01.0.270). The admin page presets only what is no function of its own (follow, echo: preset:1);
  // a function is released for every profile at once; single profiles are blocked in the function (Wer darf es).
  const fields=SETF.filter(f=>(!(f.k==='voice'||f.prof)||admin||PROFILE)&&(!f.need||!admin||f.preset)&&(!f.only||admin||ALLOW[f.only])&&(!f.me||!admin));
  const why=f=>!admin&&f.need&&!ALLOW[f.need]?t('Vom Admin ausgeschaltet','Switched off by the admin'):'';
  let prev;el.innerHTML=fields.map(f=>{let ctl;const id='set_'+el.id+'_'+f.k;
    if(f.type==='bool')ctl=`<label class="tgl"><input type="checkbox" id="${id}"${v[f.k]?' checked':''}><i></i></label>`;
    else if(f.type==='sel')ctl=`<select id="${id}">${opts(f).map(([a,b])=>`<option value="${a}"${String(v[f.k])===a?' selected':''}>${esc(b)}</option>`).join('')}</select>`;
    else if(f.type==='face'){const nm={robot:t('Roboter','Robot'),comic:'Comic',comic_woman:t('Comic (Frau)','Comic (woman)')},sp=window.faceSpark?faceSpark():'robot';
      ctl=`<select id="${id}" class="facesel" data-noseg>${opts(f).map(([a])=>[a,a?nm[a]||a:t('Vorgabe','Default')+' ('+nm[sp]+')'])
        .map(([a,b])=>`<option value="${a}"${a?'':` data-short="${esc(t('Vorgabe','Default'))}"`}${(v[f.k]||'')===a?' selected':''}>${esc(b)}</option>`).join('')}</select>`}
    else if(f.type==='text')ctl=`<textarea id="${id}" rows="3" maxlength="${f.max}">${esc(v[f.k]||'')}</textarea>`;
    else if(f.type==='voice')ctl=(voices.length?'':'<div>')+`<select id="${id}"><option value="">${t('Standard','Default')}</option>${[...new Set([...voices,...(v.voice?[v.voice]:[])])].map(x=>`<option${x===v.voice?' selected':''}>${esc(x)}</option>`).join('')}</select>`+(voices.length?'':`<div class="fh">${t('Die Sprachausgabe nennt gerade keine Stimmen (startet noch?). Später erneut öffnen.','The speech output lists no voices right now (still starting?). Open again later.')}</div></div>`);
    else ctl=`<input type="range" id="${id}" min="${(rng[f.k]||[])[0]}" max="${(rng[f.k]||[])[1]}" step="${f.step}" value="${v[f.k]}"><output id="${id}_o">${Number(v[f.k]).toFixed(2)}×</output>`;
    const head=f.grp!==prev;prev=f.grp;
    return (head?`${f===fields[0]?'':'</div>'}<div class="setpane${f===fields[0]||admin?' on':''}" data-g="${esc(f.grp)}">${admin?`<h3 class="sec">${esc(f.grp)}</h3>`:''}`:'')+setRow(esc(f.l),esc(f.h),ctl,{why:why(f)})}).join('')+'</div>';
  fields.forEach(f=>{const e=$('set_'+el.id+'_'+f.k);e.oninput=e.onchange=ev=>{
    const val=f.type==='bool'?e.checked:f.type==='range'?Number(e.value):f.type==='text'?e.value.replace(/<<<|>>>|[\x00-\x09\x0b-\x1f\x7f]/g,'').slice(0,f.max):e.value;
    if(f.type==='text'&&ev.type==='input')return;   // saved when the field is left
    if(f.type==='range')$(e.id+'_o').textContent=val.toFixed(2)+'×';
    if(v[f.k]===val||(f.type==='range'&&ev.type==='input'))return;v[f.k]=val;onchange&&onchange(f.k,val)}});
  if(window.faceTiles)faceTiles(el);
  if(!admin)meLayout(el);
  if(!admin&&window.cxWhoRows)cxWhoRows(el);   // „Wer darf mir schreiben“: the picked and blocked ones, the Rufname (chats.js)
  return()=>({...v})}
// Ich → Gespräch (plaene/einstellungen-anordnung.md, Umzug 1): the groups one below the other in boxes as on the
// settings pages (no tabs), "Tempo und Genauigkeit" folded, and what the admin switched off collected at the bottom
// instead of between the rows one can use. Only moves the drawn rows; their handlers stay.
function meLayout(el){const panes=[...el.querySelectorAll(':scope>.setpane')];
  panes.forEach(p=>{p.classList.add('on');const h=document.createElement('h3');h.className='sec';h.textContent=p.dataset.g;p.prepend(h)});
  const lock=[...el.querySelectorAll('.setrow.locked')];
  if(lock.length){const d=document.createElement('details');d.className='adv melockrows';const s=document.createElement('summary');
    s.textContent=lock.length===1?t('1 Einstellung vom Admin ausgeschaltet','1 setting switched off by the admin'):lock.length+t(' Einstellungen vom Admin ausgeschaltet',' settings switched off by the admin');
    const box=document.createElement('div');box.className='setpane on';box.dataset.g='locked';lock.forEach(r=>box.appendChild(r));d.append(s,box);el.appendChild(d)}
  const fold=panes.find(p=>p.dataset.g===t('Tempo und Genauigkeit','Speed and accuracy'));
  if(fold){const d=document.createElement('details');d.className='adv mefold';const s=document.createElement('summary');s.textContent=fold.dataset.g;
    const i=document.createElement('span');i.textContent=t('wie gründlich und wie schnell der Assistent Werkzeuge wählt','how thoroughly and how fast the assistant picks tools');s.appendChild(i);
    fold.before(d);d.append(s,fold);fold.querySelector(':scope>h3.sec').remove()}
  panes.forEach(p=>{const empty=!p.querySelector('.setrow');p.hidden=empty;const d=p.closest('details.mefold');if(d)d.hidden=empty});
  if(window.pageGroup)el.querySelectorAll('.setpane').forEach(window.pageGroup);if(window.pageSeg)window.pageSeg(el)}
function applySet(){$('chathands').checked=!!S.hands;if(window.faceApply)faceApply();if(typeof voiceShow==='function')voiceShow();$('chattiming').style.display=S.timing?'':'none';if(typeof picsShow==='function')picsShow();syncSettings()}
async function refreshAllow(){const d=await (await api('/api/profile/settings')).json();
  const a=d&&d.allow||{};if(JSON.stringify(a)===JSON.stringify(ALLOW))return;ALLOW=a;
  if($('profmodal').style.display==='grid')renderSet($('setform'),S,saveSet)}
// the one load of the defaults, lists and own values (SETP, chat.js); without an answer the last ones stay and it asks
// again shortly, so nothing works on settings it never got
function loadSettings(){return SETP=(async()=>{let d=null;try{d=await (await api('/api/profile/settings')).json()}catch{}
  if(d&&d.defaults){SDEF={...d.defaults};SETC={choices:d.choices||{},ranges:d.ranges||{}};S={...SDEF,...(d.settings||{})};ALLOW=d.allow||{};OFFLINE_HERE=!!d.offline_here}
  else if(!Object.keys(SDEF).length)setTimeout(()=>loadSettings().catch(()=>{}),5000);
  if(!PROFILE&&!isGuest()){try{S={...S,...JSON.parse(localStorage.getItem('chatset')||'{}')}}catch{}}
  applySet();if(!S.daily&&!chat.cid&&!chat.msgs.length)openConvo((convos.load()[0]||{}).id||null)})()}
const setReady=()=>(SETP||loadSettings()).catch(()=>{});   // the Spark's defaults and lists are in (renderSet, admin.js)
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
  const ev={profile_login:t('Anmeldung','Sign-in'),profile_login_failed:t('Falsche PIN','Wrong PIN'),profile_logout_all:t('Überall abgemeldet','Logged out everywhere'),profile_code_failed:t('Falscher Code','Wrong code'),profile_mfa_on:t('Zweiter Schritt an','Second step on'),profile_mfa_off:t('Zweiter Schritt aus','Second step off'),profile_mfa_reset:t('Zweiter Schritt vom Admin zurückgesetzt','Second step reset by the admin'),profile_device_removed:t('Gerät gesperrt','Device blocked'),profile_session_end:t('Browser abgemeldet','Browser signed out'),invite_pin:t('Neue PIN über Einladungslink','New PIN through an invitation link'),handoff_login:t('Handy über QR-Code angemeldet','Phone signed in by QR code')};
  $('secev').innerHTML=d.events.map(e=>`<li><span>${esc(ev[e.event]||e.event)} <small class="mut">${when(e.t)} · ${esc(e.ip||'')}</small></span></li>`).join('')||`<li class="mut">–</li>`}
function secRender(devs){$('secdev').innerHTML=devs.map(x=>`<li><span>${esc(x.name)}<br><small class="mut">${x.speaker?t('Lautsprecher, verwaltet unter Ich → Lautsprecher · ','Speaker, managed under Me → Speakers · '):''}${t('zuletzt','last used')}: ${x.last?when(x.last.t)+' · '+esc(x.last.ip||''):t('noch nie','never')}</small></span><button class="b" ${onAttr('secDrop',x.id,x.name,x.speaker?'1':'')}>${t('Sperren','Block')}</button></li>`).join('')||`<li class="mut">${t('Keine Geräte mit Schlüssel.','No devices with a key.')}</li>`}
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
