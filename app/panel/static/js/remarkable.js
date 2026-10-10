// Ich → reMarkable (remarkable.py): connect the own my.remarkable account with a one-time code, pick
// notebooks or folders, compare now, disconnect; "Aufs reMarkable" under answers (rm_send).
// Names from the cloud are put in with esc()/textContent only.
let RM_ON=false,RMSEND_ON=false,RMFRESH_ON=false,RMPLUS_ON=false,RM=null,rmTimer=null,rmFind='',RMPICK=null,RMALL=null;
const rmWhen=x=>x?new Date(x*1000).toLocaleString([], {dateStyle:'short',timeStyle:'short'}):t('noch nie','never');
const RMKIND={folder:['Ordner','folder'],notebook:['Notizbuch','notebook'],pdf:['PDF','PDF'],epub:['E-Book','e-book']};
async function showRm(){const box=$('rmbox');if(!box)return;clearTimeout(rmTimer);if(!PROFILE||!RM_ON){box.innerHTML='';return}
  let d=null;if(S.rm_on){try{d=await (await api('/api/profile/remarkable')).json()}catch{}}RM=d;
  const head=`<div class="intro">${t('Verbinde dein my.remarkable-Konto (reMarkable 2, Paper Pro, Paper Pro Move). Der Assistent liest die Notizbücher, die du unten auswählst: getippten Text und Markierungen direkt, Handschrift liest das Sprachmodell auf dem Spark in Gesprächspausen ab. Danach findest du sie in der Dokumentensuche. Der Spark ändert dort nichts; nur „Aufs reMarkable schicken“ legt neue Dokumente im Ordner „Spark“ an.','Connect your my.remarkable account (reMarkable 2, Paper Pro, Paper Pro Move). The assistant reads the notebooks you pick below: typed text and highlights directly, handwriting is read by the language model on the Spark in quiet moments. The document search then finds them. The Spark changes nothing there; only "Send to the reMarkable" adds new documents in the folder "Spark".')}</div>
    ${xsw('rm_on',t('reMarkable für mich','reMarkable for me'),t('Aus: Es wird nichts mehr abgeglichen; die gelesenen Notizbücher bleiben, bis du trennst.','Off: nothing is compared any more; notebooks already read stay until you disconnect.'))}
    ${RMSEND_ON?xsw('rm_send',t('Aufs reMarkable schicken','Send to the reMarkable'),t('Unter jeder Antwort „Aufs reMarkable“, und „Schreib aufs reMarkable: …“ legt eine Notiz an. Höchstens 20 am Tag.','"To the reMarkable" below every answer, and "Write on the reMarkable: …" makes a note. At most 20 a day.')):''}
    ${RMFRESH_ON?xsw('rm_fresh',t('Neueste zuerst','Newest first'),t('Bei ähnlich guten Treffern nimmt der Assistent die neuere Notiz und nennt ihr Datum; „Was habe ich zuletzt notiert?“ (auch heute, gestern, diese Woche) nennt die neuesten Seiten. Gilt für alle deine Dokumente.','With similar hits the assistant takes the newer note and names its date; "What did I note last?" (also today, yesterday, this week) names the newest pages. Applies to all your documents.')):''}`;
  if(!d){box.innerHTML=head+`<div class="fh" id="rmmsg"></div>`;xbind(box,showRm);return}
  const conn=d.connected;
  let body='';
  if(!conn)body=`<h3>${t('Verbinden','Connect')}</h3>
    <div class="fh"><b>1.</b> ${t('Auf','On')} <a href="${esc(d.connect_url)}" target="_blank" rel="noopener noreferrer">my.remarkable.com/pair</a> ${t('anmelden und einen Einmalcode für eine Desktop-App holen (acht Buchstaben).','sign in and get a one-time code for a desktop app (eight letters).')}</div>
    <div class="fh"><b>2.</b> ${t('Code hier eintragen. Ist der zweite Anmeldeschritt an, fragt der Spark danach.','Enter the code here. With the second sign-in step on, the Spark asks for it.')}</div>
    <div class="rowin"><input id="rmcode" maxlength="8" placeholder="abcdefgh" autocapitalize="off" autocomplete="off" spellcheck="false"><button class="b p" type="button" id="rmpair">${t('Verbinden','Connect')}</button></div>
    <div class="fh">${t('Ohne Connect-Abo synchronisiert reMarkable nur eingeschränkt in die Cloud; was dort nicht liegt, sieht auch der Spark nicht. Die Verbindung nutzt eine inoffizielle Schnittstelle, die reMarkable ändern kann.','Without a Connect subscription reMarkable syncs to the cloud only in part; what is not there the Spark does not see either. The connection uses an unofficial interface that reMarkable may change.')}</div>`;
  else{const lib=d.library||[],q=rmFind.toLowerCase(),shown=lib.filter(x=>!q||x.path.toLowerCase().includes(q)).slice(0,300);
    const st=d.busy?t('Abgleich läuft …','Comparing …'):t('Zuletzt abgeglichen: ','Last compared: ')+rmWhen(d.last);
    body=`<div class="fh">${t('Verbunden seit ','Connected since ')}${esc(rmWhen(d.since))} · ${esc(st)} · ${d.count} ${t('Notizbücher im Spark','notebooks on the Spark')}${d.error?`<br><span class="err">${esc(d.error)}</span>`:''}</div>
      ${d.pictures?'':`<div class="fh">${t('Handschrift wird erst gelesen, wenn unter Ich → Dokumente „Bilder und Scans lesen lassen“ an ist. Getippter Text und Markierungen kommen sofort.','Handwriting is only read once "Let pictures and scans be read" is on under Me → Documents. Typed text and highlights come at once.')}</div>`}
      <h3>${t('Was der Assistent lesen darf','What the assistant may read')}</h3>
      <label class="chk"><input type="checkbox" id="rmall"${(RMALL===null?d.all:RMALL)?' checked':''}> ${t('Alle Notizbücher (ohne PDFs und Bücher, nie der Papierkorb)','All notebooks (no PDFs or books, never the trash)')}</label>
      <div class="fh">${t('Oder einzeln ankreuzen; ein Ordner nimmt alles darin mit. Bei PDFs und Büchern liest er nur Markierungen und deine Notizen.','Or tick single ones; a folder takes everything in it. For PDFs and books only highlights and your notes are read.')}</div>
      <input id="rmfind" type="search" maxlength="80" placeholder="${esc(t('Suchen','Search'))}" value="${esc(rmFind)}">
      <ul class="facts small" id="rmlist">${shown.map(x=>`<li><label class="chk" style="flex:1"><input type="checkbox" data-rmid="${esc(x.id)}"${(RMPICK?RMPICK.has(x.id):x.picked)?' checked':''}> <span><b>${esc(x.path)}</b><br><small class="mut">${esc(t(...(RMKIND[x.kind]||RMKIND.notebook)))}${x.folder?'':' · '+x.pages+t(' Seiten',' pages')}${x.read&&!x.picked?' · '+t('wird gelesen','is read'):''}</small></span></label></li>`).join('')||`<li class="mut"><span>${d.busy?t('Liste wird geladen …','Loading the list …')+(d.progress&&d.progress[1]?` ${d.progress[0]} / ${d.progress[1]}`:''):t('Nichts gefunden.','Nothing found.')}</span></li>`}</ul>
      ${lib.length>shown.length?`<div class="fh">${t('Weitere mit der Suche finden.','Find more with the search.')}</div>`:''}
      <div class="row" style="margin-top:8px"><button class="b p" type="button" id="rmsave">${t('Auswahl speichern','Save choice')}</button><button class="b" type="button" id="rmsync"${d.busy?' disabled':''}>${t('Jetzt abgleichen','Compare now')}</button><button class="b" type="button" id="rmdel">${t('Trennen','Disconnect')}</button></div>
      ${d.send?`<h3>${t('Ablegen in','Put into')}</h3>
      <select id="rmtarget"><option value="">${t('Spark (Standard)','Spark (default)')}</option>${lib.filter(x=>x.folder).map(x=>`<option value="${esc(x.id)}"${x.id===d.target?' selected':''}>${esc(x.path)}</option>`).join('')}</select>
      <div class="fh">${t('Dorthin legt der Spark neue Dokumente; Bestehendes ändert er nie. Fehlt der Ordner später, nimmt er wieder „Spark“ und sagt es dir.','New documents go there; the Spark never changes anything that exists. If the folder is gone later, it takes "Spark" again and tells you.')}</div>
      <div class="fh">${t('Heute aufs reMarkable geschickt: ','Sent to the reMarkable today: ')}${d.sent_today} / ${d.send_day}</div>`:''}
      ${d.send&&RMPLUS_ON&&d.plus?rmPlus(d.plus):''}`}
  box.innerHTML=head+body+`<div class="fh" id="rmmsg"></div>`;
  xbind(box,showRm);
  if(!conn)RMALL=null;if($('rmall'))$('rmall').onchange=e=>{RMALL=e.target.checked};
  if(!RMPICK||!conn)RMPICK=new Set((d.library||[]).filter(x=>x.picked).map(x=>x.id));const picked=RMPICK;
  box.querySelectorAll('[data-rmid]').forEach(c=>c.onchange=()=>{if(c.checked)picked.add(c.dataset.rmid);else picked.delete(c.dataset.rmid)});
  if($('rmfind'))$('rmfind').oninput=e=>{rmFind=e.target.value;clearTimeout(rmTimer);rmTimer=setTimeout(()=>{showRm().then(()=>{const f=$('rmfind');if(f){f.focus();f.setSelectionRange(f.value.length,f.value.length)}})},300)};
  if($('rmpair'))$('rmpair').onclick=async()=>{xmsg('rmmsg',t('Verbinde …','Connecting …'));
    try{await api('/api/profile/remarkable/pair',xjson('POST',{code:$('rmcode').value.trim().toLowerCase()}));xmsg('rmmsg',t('Verbunden. Die Liste deiner Notizbücher wird geladen.','Connected. The list of your notebooks is loading.'));showRm()}
    catch(e){xmsg('rmmsg',e.message,true)}};
  if($('rmsave'))$('rmsave').onclick=async()=>{try{await api('/api/profile/remarkable/pick',xjson('PUT',{ids:[...picked],all:$('rmall').checked}));RMPICK=null;RMALL=null;xmsg('rmmsg',t('Gespeichert. Der Abgleich beginnt in den nächsten Minuten.','Saved. The comparison starts within the next minutes.'))}
    catch(e){xmsg('rmmsg',e.message,true)}};
  if($('rmtarget'))$('rmtarget').onchange=async e=>{try{await api('/api/profile/remarkable/target',xjson('PUT',{id:e.target.value}));xmsg('rmmsg',t('Gespeichert.','Saved.'))}catch(x){xmsg('rmmsg',x.message,true)}};
  if($('rmsync'))$('rmsync').onclick=async()=>{try{await api('/api/profile/remarkable/sync',{method:'POST'});showRm()}catch(e){xmsg('rmmsg',e.message,true)}};
  if($('rmdel'))$('rmdel').onclick=async()=>{if(!confirm(t('reMarkable trennen? Alle gelesenen Notizbücher verschwinden vom Spark (auf dem reMarkable bleibt alles).','Disconnect the reMarkable? All notebooks read disappear from the Spark (everything stays on the reMarkable).')))return;
    try{const r=await (await api('/api/profile/remarkable',{method:'DELETE'})).json();xmsg('rmmsg',t('Getrennt. Entferne das Gerät „desktop-linux“ auch auf my.remarkable.com.','Disconnected. Also remove the device "desktop-linux" on my.remarkable.com.'));RM=null;showRm().then(()=>xmsg('rmmsg',r.hint||''))}
    catch(e){xmsg('rmmsg',e.message,true)}};
  if($('rmat'))$('rmat').onchange=e=>{if(e.target.value)saveSet('rm_morning_at',e.target.value)};
  box.querySelectorAll('[data-rmtodo]').forEach(b=>b.onclick=async()=>{const id=b.dataset.rmtodo,remind=b.dataset.do==='remind',w=$('rmdue-'+id);
    const due=remind&&w&&w.value?new Date(w.value).getTime():0;if(remind&&!due)return;
    try{await api('/api/profile/remarkable/todo',xjson('POST',remind?{id,do:'remind',due}:{id,do:'drop'}));showRm().then(()=>xmsg('rmmsg',remind?t('Erinnerung eingetragen.','Reminder set.'):t('Weg.','Removed.')))}
    catch(e){xmsg('rmmsg',e.message,true)}});
  if($('rmguide'))$('rmguide').onclick=async()=>{xmsg('rmmsg',t('Lege die Anleitung ab …','Putting the guide there …'));
    try{const r=await (await api('/api/profile/remarkable/guide',{method:'POST'})).json();xmsg('rmmsg',(r.renewed?t('Anleitung erneuert in „','Guide renewed in "'):t('Anleitung liegt in „','Guide is in "'))+r.where+(L==='en'?'"':'“'))}
    catch(e){xmsg('rmmsg',e.message,true)}};
  if(d.busy)rmTimer=setTimeout(()=>{if(box.offsetParent===null||document.hidden)return;const a=document.activeElement,id=a&&box.contains(a)?a.id:'',c=id&&a.selectionStart!=null?a.selectionStart:null;
    showRm().then(()=>{const f=id&&$(id);if(f){f.focus();if(c!=null)f.setSelectionRange(c,c)}})},5e3)}
// an answer onto the reMarkable, only on the person's click (chat.js adds the button)
async function rmSend(text,b){b.disabled=true;const first=(text.split('\n').find(x=>x.trim())||'').replace(/[#*_`>]/g,'').trim();
  try{const r=await (await api('/api/profile/remarkable/send',xjson('POST',{title:first.slice(0,60)||t('Vom Spark','From the Spark'),text}))).json();b.textContent=t('Auf dem reMarkable: ','On the reMarkable: ')+r.where+' / '+r.title+(r.lost?t(' (gewählter Ordner fehlt)',' (chosen folder is gone)'):'')}
  catch(e){b.disabled=false;b.textContent=e.message}}
// more with the reMarkable (rmplus.py): one switch per part, the Morgenblatt's time, the tasks found on paper
const RMPARTS=[['rmmorning','rm_morning',['Morgenblatt','Morning sheet'],['Jeden Morgen ein Blatt mit Terminen, Erinnerungen, Wetter und Nachrichten, darunter Linien für Notizen.','Every morning a sheet with appointments, reminders, weather and news, with lines for notes below.']],
  ['rmask','rm_ask',['@Spark auf Papier','@Spark on paper'],['Schreib „@Spark“ und eine Frage in ein gelesenes Notizbuch; die Antwort liegt nach dem nächsten Abgleich daneben.','Write "@Spark" and a question in a notebook that is read; the answer lies next to it after the next comparison.']],
  ['rmtodo','rm_todo',['Aufgaben vom reMarkable','Tasks from the reMarkable'],['Zeilen mit ☐, [ ], „TODO“ oder „Aufgabe:“ erscheinen hier; eine Erinnerung erst auf deinen Klick.','Lines with ☐, [ ], "TODO" or "Aufgabe:" show up here; a reminder only on your click.']],
  ['rmmeet','rm_meet',['Besprechungen zusammenfassen','Meeting summaries'],['Notizbuch oder erste Zeile „Besprechung“, „Meeting“ oder „Protokoll“: eine halbe Stunde nach der letzten Änderung Zusammenfassung mit Aufgaben, dazu eine Mitteilung.','Notebook or first line "Besprechung", "Meeting" or "Protokoll": half an hour after the last change a summary with tasks, plus a note.']],
  ['rmweek','rm_week',['Wochenrückblick','Week in review'],['Freitags ab 17 Uhr ein Blatt mit dem Wichtigsten der Woche und dem, was offen ist.','On Fridays from 5 pm a sheet with the week’s main points and what is open.']],
  ['rmweb','rm_web',['Webseiten und Anhänge','Web pages and attachments'],['„Leg die Seite https://… aufs reMarkable“ und „Leg den Anhang der Mail von … aufs reMarkable“ (PDF oder EPUB, letzte 30 Tage).','"Put the page https://… on the reMarkable" and "Put the attachment of the mail from … on the reMarkable" (PDF or EPUB, last 30 days).']],
  ['rminbox','rm_inbox',['Eingang pro Tag','Daily inbox'],['Diktierte Notizen sammeln sich in einem Dokument „Eingang“ pro Tag statt einzeln.','Dictated notes gather in one "Eingang" document per day instead of one each.']],
  ['rmguide','rm_guide',['Spark-Anleitung','Spark guide'],['Eine Anleitung zu allen reMarkable-Funktionen und zum Dienst; der Spark hält sie selbst aktuell.','A guide to all reMarkable functions and the service; the Spark keeps it up to date itself.']]];
function rmPlus(p){const at=new Date(Date.now()+864e5);at.setHours(9,0,0,0);const dflt=new Date(at-at.getTimezoneOffset()*6e4).toISOString().slice(0,16);
  return `<h3>${t('Mehr mit dem reMarkable','More with the reMarkable')}</h3>
  ${RMPARTS.filter(x=>p.spark[x[0]]).map(x=>xsw(x[1],t(...x[2]),t(...x[3]))).join('')}
  ${p.on.rmmorning?`<div class="rowin"><span>${t('Morgenblatt um','Morning sheet at')}</span><input type="time" id="rmat" value="${esc(p.morning_at)}"></div>`:''}
  ${p.on.rmguide?`<div class="row"><button class="b" type="button" id="rmguide">${t('Anleitung jetzt ablegen','Put the guide there now')}</button></div>`:''}
  ${p.on.rmtodo?`<h3>${t('Aufgaben vom Papier','Tasks from paper')}</h3>${p.todos.length?`<ul class="facts small">${p.todos.map(x=>`<li><span style="flex:1"><b>${esc(x.text)}</b><br><small class="mut">${esc(x.doc)}${x.page?', '+t('Seite ','page ')+x.page:''}</small><br><input type="datetime-local" id="rmdue-${esc(x.id)}" value="${dflt}"></span><button class="b p" type="button" data-rmtodo="${esc(x.id)}" data-do="remind">${t('Erinnern','Remind')}</button><button class="b" type="button" data-rmtodo="${esc(x.id)}" data-do="drop">${t('Weg','Remove')}</button></li>`).join('')}</ul>`:`<div class="fh">${t('Noch keine gefunden.','None found yet.')}</div>`}`:''}`}
