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
  if(!conn){box.innerHTML=head+body+`<div class="fh" id="rmmsg"></div>`;xbind(box,showRm);RMALL=null;RMPICK=null;rmBind(box)}
  else rmDraw(box,d);
  if(d.busy)rmTimer=setTimeout(()=>{if(box.offsetParent===null||document.hidden)return;const a=document.activeElement,id=a&&box.contains(a)?a.id:'',c=id&&a.selectionStart!=null?a.selectionStart:null;
    showRm().then(()=>{const f=id&&$(id);if(f){f.focus();if(c!=null)f.setSelectionRange(c,c)}})},5e3)}
// Connected (ich-aufraeumen/plan.md, Paket 3): a card with the state, "Jetzt abgleichen" and "⋯ Trennen", numbers,
// then tabs. "Lesen" shows the folders as a tree (left on a wide page) and the open folder's content; a ticked folder
// takes everything in it. The choice is kept until "Auswahl speichern" in the bar below.
let RMDIR='',RMMORE=false;
const rmParent=p=>p.includes('/')?p.slice(0,p.lastIndexOf('/')):'';
const rmName=p=>p.slice(p.lastIndexOf('/')+1);
const rmCount=n=>n===1?t('1 Eintrag','1 entry'):t(`${n} Einträge`,`${n} entries`);
function rmDraw(box,d){const E=icEl,lib=d.library||[];
  if(!RMPICK)RMPICK=new Set(lib.filter(x=>x.picked).map(x=>x.id));if(RMALL===null)RMALL=!!d.all;
  const byPath=new Map(lib.filter(x=>x.folder).map(x=>[x.path,x]));if(RMDIR&&!byPath.has(RMDIR))RMDIR='';
  // ticked itself, through a folder above it, or partly (something inside it)
  const up=x=>{for(let p=rmParent(x.path);p;p=rmParent(p)){const f=byPath.get(p);if(f&&RMPICK.has(f.id))return f}return null};
  const state=x=>{if(RMPICK.has(x.id)||up(x))return true;if(x.folder){const pre=x.path+'/';if(lib.some(y=>y.path.startsWith(pre)&&RMPICK.has(y.id)))return 'half'}return false};
  const saved=new Set(lib.filter(x=>x.picked).map(x=>x.id)),changes=[...RMPICK].filter(x=>!saved.has(x)).length+[...saved].filter(x=>!RMPICK.has(x)).length+(RMALL!==!!d.all?1:0);
  box.textContent='';
  const st=d.busy?t('Abgleich läuft …','Comparing …'):t('zuletzt abgeglichen ','last compared ')+rmWhen(d.last);
  const sync=E('button','b',t('Jetzt abgleichen','Compare now'));sync.type='button';sync.id='rmsync';sync.disabled=!!d.busy;sync.prepend(icSvg('sync',14));
  sync.onclick=async()=>{try{await api('/api/profile/remarkable/sync',{method:'POST'});showRm()}catch(e){xmsg('rmmsg',e.message,true)}};
  box.appendChild(icCard('pen',t('my.remarkable','my.remarkable'),t('Verbunden seit ','Connected since ')+rmWhen(d.since)+' · '+st+(d.error?' · ⚠ '+d.error:''),[sync],
    [{label:t('Trennen …','Disconnect …'),danger:true,act:rmDisconnect}]));
  if(!d.pictures)box.appendChild(E('div','fh',t('Handschrift wird erst gelesen, wenn unter Ich → Dokumente „Bilder und Scans lesen lassen“ an ist. Getippter Text und Markierungen kommen sofort.','Handwriting is only read once "Let pictures and scans be read" is on under Me → Documents. Typed text and highlights come at once.')));
  const stats=[[d.count,t('Notizbücher im Spark','notebooks on the Spark')],[RMALL?t('alle','all'):String(RMPICK.size),t('ausgewählt zum Lesen','chosen to read')]];
  if(d.send){stats.push([`${d.sent_today} / ${d.send_day}`,t('heute aufs reMarkable','to the reMarkable today')]);const tg=lib.find(x=>x.id===d.target);stats.push([tg?rmName(tg.path):'Spark',t('Ablage für Neues','where new things go')])}
  box.appendChild(icStats(stats));
  const tabs=[{k:'read',label:t('Lesen','Read'),n:RMALL?'':RMPICK.size,body:()=>rmRead(d,lib,byPath,state,up)}];
  if(RMSEND_ON)tabs.push({k:'send',label:t('Schicken','Send'),n:'',body:()=>rmSendTab(d,lib)});
  if(d.send&&RMPLUS_ON&&d.plus)tabs.push({k:'plus',label:t('Mehr','More'),n:d.plus.on&&d.plus.on.rmtodo&&d.plus.todos.length?d.plus.todos.length:'',body:()=>{const w=E('div');w.innerHTML=rmPlus(d.plus);xbind(w,showRm);rmBind(w);return w}});
  tabs.push({k:'set',label:t('Einstellungen','Settings'),n:'',body:()=>{const w=E('div');w.innerHTML=xsw('rm_on',t('reMarkable für mich','reMarkable for me'),t('Aus: Es wird nichts mehr abgeglichen; die gelesenen Notizbücher bleiben, bis du trennst.','Off: nothing is compared any more; notebooks already read stay until you disconnect.'))+
    (RMFRESH_ON?xsw('rm_fresh',t('Neueste zuerst','Newest first'),t('Bei ähnlich guten Treffern nimmt der Assistent die neuere Notiz und nennt ihr Datum; „Was habe ich zuletzt notiert?“ (auch heute, gestern, diese Woche) nennt die neuesten Seiten. Gilt für alle deine Dokumente.','With similar hits the assistant takes the newer note and names its date; "What did I note last?" (also today, yesterday, this week) names the newest pages. Applies to all your documents.')):'');
    xbind(w,showRm);if(typeof pageGroup==='function')pageGroup(w);return w}});
  box.appendChild(icTabs('rm',tabs));
  if(changes){const bar=E('div','ic-save'),m=E('div','ic-mid');m.append(E('b','',t(`${changes} Änderung${changes>1?'en':''}`,`${changes} change${changes>1?'s':''}`)),E('span','',t('an der Auswahl, was der Assistent lesen darf','to what the assistant may read')));
    const no=E('button','b',t('Verwerfen','Discard')),ok=E('button','b p',t('Auswahl speichern','Save choice'));no.type=ok.type='button';ok.id='rmsave';
    no.onclick=()=>{RMPICK=null;RMALL=null;rmDraw(box,d)};
    ok.onclick=async()=>{ok.disabled=true;try{await api('/api/profile/remarkable/pick',xjson('PUT',{ids:[...RMPICK],all:RMALL}));RMPICK=null;RMALL=null;await showRm();xmsg('rmmsg',t('Gespeichert. Der Abgleich beginnt in den nächsten Minuten.','Saved. The comparison starts within the next minutes.'))}
      catch(e){ok.disabled=false;xmsg('rmmsg',e.message,true)}};
    bar.append(m,no,ok);box.appendChild(bar)}
  box.appendChild(Object.assign(E('div','fh'),{id:'rmmsg'}));
  const redraw=()=>{const y=box.closest('.mebody');const s=y?y.scrollTop:0;rmDraw(box,d);if(y)y.scrollTop=s};
  rmDraw.redraw=redraw}
function rmToggle(x,on){if(on){RMPICK.add(x.id);if(x.folder){const pre=x.path+'/';for(const y of RM.library)if(y.path.startsWith(pre))RMPICK.delete(y.id)}}else RMPICK.delete(x.id);rmDraw.redraw()}
const RMKIND_IC={folder:'folder',notebook:'nb',pdf:'pdf',epub:'nb'};
function rmRead(d,lib,byPath,state,up){const E=icEl,w=E('div');
  const all=E('label','chk');const cb=document.createElement('input');cb.type='checkbox';cb.id='rmall';cb.checked=RMALL;cb.onchange=()=>{RMALL=cb.checked;rmDraw.redraw()};
  all.append(cb,document.createTextNode(' '+t('Alle Notizbücher (ohne PDFs und Bücher, nie der Papierkorb)','All notebooks (no PDFs or books, never the trash)')));w.appendChild(all);
  w.appendChild(E('div','fh',t('Oder einzeln ankreuzen; ein Ordner nimmt alles darin mit. Bei PDFs und Büchern liest er nur Markierungen und deine Notizen.','Or tick single ones; a folder takes everything in it. For PDFs and books only highlights and your notes are read.')));
  const tools=E('div','ic-tools');tools.appendChild(icSearch(t('In allen Notizbüchern suchen …','Search all notebooks …'),rmFind,v=>{rmFind=v;clearTimeout(rmTimer);rmTimer=setTimeout(()=>{list.textContent='';fill()},200)},'rmfind'));w.appendChild(tools);
  const two=E('div','ic-two'),tree=E('div','ic-tree wide'),right=E('div');two.append(tree,right);w.appendChild(two);
  // tree: the root and the folders, open along the way to the open folder
  const open=new Set(['']);for(let p=RMDIR;p;p=rmParent(p))open.add(p);
  const tn=(path,label,depth,n)=>{const f=byPath.get(path),r=E('div','ic-tn'+(path===RMDIR?' on':''));r.style.paddingLeft=(6+depth*16)+'px';r.dataset.dir=path;
    if(f)r.appendChild(icCheck(state(f),label,()=>rmToggle(f,!(RMPICK.has(f.id))))).disabled=!!up(f);r.appendChild(icSvg('folder',15));const nm=E('span','nm',label);nm.title=label;r.appendChild(nm);
    r.appendChild(E('small','',String(n)));r.onclick=()=>{RMDIR=path;rmFind='';rmDraw.redraw()};return r};
  const kids=p=>lib.filter(x=>rmParent(x.path)===p);
  const walk=(p,depth)=>{for(const f of kids(p).filter(x=>x.folder).sort((a,b)=>a.path.localeCompare(b.path))){tree.appendChild(tn(f.path,rmName(f.path),depth,kids(f.path).length));if(open.has(f.path))walk(f.path,depth+1)}};
  tree.appendChild(tn('',t('Alle','All'),0,kids('').length));walk('',1);
  const list=E('div');right.appendChild(list);
  function fill(){const q=rmFind.trim().toLowerCase();list.textContent='';
    let items;if(q){items=lib.filter(x=>x.path.toLowerCase().includes(q)).slice(0,300);list.appendChild(E('div','ic-crumb',t(`${items.length} Treffer für „${rmFind.trim()}“`,`${items.length} hits for "${rmFind.trim()}"`)))}
    else{items=kids(RMDIR).sort((a,b)=>(b.folder-a.folder)||a.path.localeCompare(b.path));
      const c=E('div','ic-crumb');const parts=RMDIR?RMDIR.split('/'):[];const go=p=>{RMDIR=p;rmDraw.redraw()};
      const root=E('button','',t('Alle','All'));root.type='button';root.onclick=()=>go('');c.appendChild(root);
      parts.forEach((x,i)=>{c.appendChild(document.createTextNode('›'));const p=parts.slice(0,i+1).join('/');if(i===parts.length-1)c.appendChild(E('b','',x));else{const b=E('button','',x);b.type='button';b.onclick=()=>go(p);c.appendChild(b)}});
      c.appendChild(document.createTextNode(' · '+rmCount(items.length)));list.appendChild(c)}
    if(!items.length){list.appendChild(icList([icEmpty(q?t('Nichts gefunden.','Nothing found.'):t('Dieser Ordner ist leer.','This folder is empty.'))]));return}
    const rows=items.map(x=>{const s=state(x),via=up(x);const kind=t(...(RMKIND[x.kind]||RMKIND.notebook));
      const meta=x.folder?rmCount(kids(x.path).length):kind+' · '+x.pages+t(' Seiten',' pages')+(x.kind==='pdf'||x.kind==='epub'?' · '+t('nur Markierungen und Notizen','only highlights and notes'):'');
      const cbx=icCheck(s,x.path,()=>rmToggle(x,!RMPICK.has(x.id)));cbx.dataset.rmid=x.id;if(via){cbx.disabled=true;cbx.title=t('Über den Ordner „','Through the folder "')+rmName(via.path)+t('“ gewählt','" chosen')}
      const k=E('span','ic-kind');k.appendChild(icSvg(RMKIND_IC[x.kind]||'nb',16));
      const acts=[];
      if(x.folder){const b=icBtn('chev',t('Öffnen','Open'),()=>{RMDIR=x.path;rmFind='';rmDraw.redraw()});acts.push(b)}
      const r=icRow(rmName(x.path),(q?x.path:meta)+(s===true?' · '+t('wird gelesen','is read'):x.read?' · '+t('gelesen','read'):''),acts,[cbx,k],true);if(x.folder){r.classList.add('click');r.onclick=()=>{RMDIR=x.path;rmFind='';rmDraw.redraw()}}return r});
    const l=icList([]);const n=RMMORE?rows.length:30;rows.slice(0,n).forEach(r=>l.appendChild(r));
    if(rows.length>n){const b=E('button','ic-more2',t(`Weitere ${rows.length-n} zeigen`,`Show ${rows.length-n} more`));b.type='button';b.onclick=()=>{RMMORE=true;b.remove();rows.slice(n).forEach(r=>l.appendChild(r))};l.appendChild(b)}
    list.appendChild(l)}
  fill();return w}
function rmSendTab(d,lib){const E=icEl,w=E('div');
  w.innerHTML=xsw('rm_send',t('Aufs reMarkable schicken','Send to the reMarkable'),t('Unter jeder Antwort „Aufs reMarkable“, und „Schreib aufs reMarkable: …“ legt eine Notiz an. Höchstens 20 am Tag.','"To the reMarkable" below every answer, and "Write on the reMarkable: …" makes a note. At most 20 a day.'))+
    (d.send?`<h4 class="ic-h4">${esc(t('Ablegen in','Put into'))}</h4><select id="rmtarget" aria-label="${esc(t('Ablegen in','Put into'))}"><option value="">${esc(t('Spark (Standard)','Spark (default)'))}</option>${lib.filter(x=>x.folder).map(x=>`<option value="${esc(x.id)}"${x.id===d.target?' selected':''}>${esc(x.path)}</option>`).join('')}</select>
    <div class="fh">${esc(t('Dorthin legt der Spark neue Dokumente; Bestehendes ändert er nie. Fehlt der Ordner später, nimmt er wieder „Spark“ und sagt es dir.','New documents go there; the Spark never changes anything that exists. If the folder is gone later, it takes "Spark" again and tells you.'))}</div>
    <div class="fh">${esc(t('Heute aufs reMarkable geschickt: ','Sent to the reMarkable today: '))}${d.sent_today} / ${d.send_day}</div>`:'');
  xbind(w,showRm);rmBind(w);if(typeof pageGroup==='function')pageGroup(w);return w}
function rmBind(root){const q=s=>root.querySelector(s);
  if(q('#rmpair'))q('#rmpair').onclick=async()=>{xmsg('rmmsg',t('Verbinde …','Connecting …'));
    try{await api('/api/profile/remarkable/pair',xjson('POST',{code:q('#rmcode').value.trim().toLowerCase()}));xmsg('rmmsg',t('Verbunden. Die Liste deiner Notizbücher wird geladen.','Connected. The list of your notebooks is loading.'));showRm()}
    catch(e){xmsg('rmmsg',e.message,true)}};
  if(q('#rmtarget'))q('#rmtarget').onchange=async e=>{try{await api('/api/profile/remarkable/target',xjson('PUT',{id:e.target.value}));xmsg('rmmsg',t('Gespeichert.','Saved.'))}catch(x){xmsg('rmmsg',x.message,true)}};
  if(q('#rmsync'))q('#rmsync').onclick=async()=>{try{await api('/api/profile/remarkable/sync',{method:'POST'});showRm()}catch(e){xmsg('rmmsg',e.message,true)}};
  if(q('#rmdel'))q('#rmdel').onclick=rmDisconnect;
  if(q('#rmat'))q('#rmat').onchange=e=>{if(e.target.value)saveSet('rm_morning_at',e.target.value)};
  root.querySelectorAll('[data-rmtodo]').forEach(b=>b.onclick=async()=>{const id=b.dataset.rmtodo,remind=b.dataset.do==='remind',w=$('rmdue-'+id);
    const due=remind&&w&&w.value?new Date(w.value).getTime():0;if(remind&&!due)return;
    try{await api('/api/profile/remarkable/todo',xjson('POST',remind?{id,do:'remind',due}:{id,do:'drop'}));showRm().then(()=>xmsg('rmmsg',remind?t('Erinnerung eingetragen.','Reminder set.'):t('Weg.','Removed.')))}
    catch(e){xmsg('rmmsg',e.message,true)}});
  if(q('#rmguide'))q('#rmguide').onclick=async()=>{xmsg('rmmsg',t('Lege die Anleitung ab …','Putting the guide there …'));
    try{const r=await (await api('/api/profile/remarkable/guide',{method:'POST'})).json();xmsg('rmmsg',(r.renewed?t('Anleitung erneuert in „','Guide renewed in "'):t('Anleitung liegt in „','Guide is in "'))+r.where+(L==='en'?'"':'“'))}
    catch(e){xmsg('rmmsg',e.message,true)}};}
async function rmDisconnect(){if(!confirm(t('reMarkable trennen? Alle gelesenen Notizbücher verschwinden vom Spark (auf dem reMarkable bleibt alles).','Disconnect the reMarkable? All notebooks read disappear from the Spark (everything stays on the reMarkable).')))return;
    try{const r=await (await api('/api/profile/remarkable',{method:'DELETE'})).json();xmsg('rmmsg',t('Getrennt. Entferne das Gerät „desktop-linux“ auch auf my.remarkable.com.','Disconnected. Also remove the device "desktop-linux" on my.remarkable.com.'));RM=null;showRm().then(()=>xmsg('rmmsg',r.hint||''))}
    catch(e){xmsg('rmmsg',e.message,true)}}
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
