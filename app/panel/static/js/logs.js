// Zustand → Logs (V01.0.212, "Überblick zuerst"): the counts of the window, the newest error with a fixed hint, the
// areas to show, a tidy list (time, area, message; repeats ×n, pauses), search in the browser only, live reload, copy
// for a thread, and the per-area detail switches. Lines are built with textContent only. Klar 6 (Redesign Stufe 6,
// Tafel redesign/a-rechner-logs.png): a dense table with a fixed row height (--h-log), time and message in monospace,
// the level only as a dot, the areas of logfilter.AREAS as a menu with ticks, newest line on top; nothing jumps when
// the live refresh comes (the open menu, an opened row and the place in the list stay).
const LAREA={chat:[t('Gespräch','Conversation')],search:[t('Websuche','Web search')],weiche:[t('Weiche','Router')],
  ha:['Home Assistant'],room:[t('Raum','Room')],esp32:[t('Lautsprecher','Speakers')],telefon:[t('Telefon','Phone')],watch:[t('Uhr','Watch')],telegram:['Telegram'],mail:['Mail'],vorrang:[t('Vorrang','Priority')],wissen:[t('Wissen','Knowledge')],fund:[t('Finden','Find')],anfrage:[t('Anfrage','Request')],speicher:[t('Speicher','Storage')],gedaechtnis:[t('Gedächtnis','Memory')],klaeren:[t('Rückfrage','Asking back')],seite:[t('Seite lädt','Page loading')],nachrichten:[t('Nachrichten und Chats','Messages and chats')],werkzeug:[t('Werkzeuge','Tools')],listen:[t('Listen, Termine, Erinnerungen','Lists, appointments, reminders')],mitteilung:[t('Mitteilungen','Notifications')],pc:[t('Rechner, eigene Dienste, Dokumente','Computer, own services, documents')],bild:[t('Bilder malen','Painting pictures')],musik:[t('Musik machen','Making music')],dungeon:[t('Dungeon-Master','Dungeon Master')],schwer:[t('Schwere Aufträge','Heavy jobs')],remarkable:['reMarkable'],nas:['NAS'],apps:[t('Apps','Apps')],vonselbst:[t('Von selbst','By itself')],verbessern:[t('Verbessern','Improve')],fernzugang:[t('Fernzugang','Remote access')],spontanhilfe:[t('Spontanhilfe','Spontaneous help')],system:[t('System und Sicherheit','System and security')],ereignis:[t('Ereignisse (wie in Live)','Events (as in Live)')]};
const LV_AREAS={room:t('Raum-Modus','Room mode'),esp32:t('Lautsprecher','Speakers'),ha:'Home Assistant',chat:t('Gespräch','Conversation')};
// display only: the same fixed words as the panel uses for the diagnosis tab, for the plain service logs
const LERR=/error|exception|traceback|failed|broke|refused|timeout|timed out|fehler|not reachable/i,LWARN=/\b(warn\w*|stalled|behind|ignored|asked again|retry|slow)\b/i;
const LG={tab:'diag',min:60,lines:100,f:['room','esp32'],live:true,svc:'asr'};
try{Object.assign(LG,JSON.parse(localStorage.getItem('logview')||'{}'))}catch{}
try{if(localStorage.getItem('logfollow')==='0')LG.live=false}catch{}
let LDATA=null,LROWS=[],LAT=0,TRACE_ON=false;
const lsave=()=>{try{localStorage.setItem('logview',JSON.stringify({tab:LG.tab,min:LG.min,lines:LG.lines,f:LG.f,live:LG.live,svc:LG.svc}))}catch{}};
const el=(tag,cls,text)=>{const e=document.createElement(tag);if(cls)e.className=cls;if(text!=null)e.textContent=text;return e};
function lparse(line){const m=line.match(/^(\d{4}-\d\d-\d\dT(\d\d:\d\d:\d\d)\S*)\s+\S+\s+[^:\s]+?(?:\[\d+\])?:\s?(.*)$/);
  const msg=m?m[3]:line;return {t:m?m[2]:'',area:'',level:LERR.test(msg)?'err':LWARN.test(msg)?'warn':'',msg,raw:line}}
async function auditRows(){const d=await (await api('/api/audit?limit=500')).json();
  return d.events.map(e=>{const who=e.who||(e.uid&&d.names[e.uid])||e.name||'',dt=new Date(e.t*1000);
    const what=e.event==='change'?`${e.method} ${e.path} → ${e.status}`:(AUDIT[e.event]||e.event)+(e.locked?t(` – gesperrt für ${e.locked} s`,` – locked for ${e.locked} s`):'')+(e.detail?' – '+e.detail:'');
    const msg=`${who?who+': ':''}${what}`+(e.ip?`  (${e.ip})`:'');
    return {t:dt.toTimeString().slice(0,8),area:'',level:/fail|locked|refused/.test(e.event)?'warn':'',msg,raw:`${dt.toLocaleString()}  ${msg}`}})}
// the first break in the fixed words of guard.BREAK_WORDS (broken.say: German, English); an unreadable line has no time
// of its own, then the time of the entry before it; the number of breaks, and whether the chain fits again after it
function chainBreak(c,day){const b=c.broken,say=b.say||[],when=b.t?day(b.t):t('nach ','after ')+day(b.before);
  let s=t(`Kette bricht in ${b.file}, Zeile ${b.line} (${when}): ${say[0]||'Art unbekannt'}.`,`Chain breaks in ${b.file}, line ${b.line} (${when}): ${say[1]||'kind unknown'}.`);
  if(c.breaks>1)s+=t(` ${c.breaks} Bruchstellen.`,` ${c.breaks} breaks.`);
  if(b.after_ok)s+=t(' Danach ist die Kette wieder heil.',' After it the chain is whole again.');
  return s}
// „Protokoll prüfen“ : the chain of the change log and the sealed copy on the NAS (guard.verify, offsite.compare_audit)
function auditChain(){const box=$('logkette');if(!box||box.childElementCount)return;
  const b=el('button','b',t('Protokoll prüfen','Check the log'));b.type='button';const out=el('span','lsub',t('Prüft die Kette aller Einträge und vergleicht mit der Kopie auf dem NAS.','Checks the chain of all entries and compares with the copy on the NAS.'));
  box.append(b,out);b.onclick=async()=>{b.disabled=true;out.textContent=t('prüft …','checking …');
    try{out.textContent=chainSay(await (await api('/api/audit/check?nas=1')).json())}catch(e){out.textContent=e.message}finally{b.disabled=false}}}
function chainSay(d){const c=d.chain,n=d.nas,day=x=>x?new Date(x*1000).toLocaleDateString():'–';
  let s=c.ok?t(`Kette heil: ${c.lines} Einträge seit ${day(c.first)}.`,`Chain whole: ${c.lines} entries since ${day(c.first)}.`)
    :chainBreak(c,day);
  if(c.old)s+=t(` ${c.old} ältere Einträge ohne Kette.`,` ${c.old} older entries without chain.`);
  if(n)s+=n.missing?t(` NAS-Kopie: ${n.missing} von ${n.lines} Einträgen fehlen hier oder sind verändert.`,` NAS copy: ${n.missing} of ${n.lines} entries are missing here or changed.`)
    :t(` NAS-Kopie stimmt (${n.lines} Einträge).`,` NAS copy matches (${n.lines} entries).`);
  else s+=d.nas_error?t(' NAS-Kopie nicht erreichbar.',' NAS copy not reachable.'):t(' Noch keine NAS-Kopie: Einstellungen → Sicherung → Sicherung nach außen.',' No NAS copy yet: Settings → Backup → Backup to the outside.');
  return s}
async function loadLogs(){
  if(LG.tab==='req'&&!TRACE_ON)LG.tab='diag';
  const tab=LG.tab;let rows=[],head='';LAT=Date.now();
  if(tab==='req'){await loadReq();return}
  if(tab==='diag'||tab==='update'){
    const f=tab==='update'?'update':LG.f.join(',');
    const d=await (await api(`/api/logfilter?format=json&f=${encodeURIComponent(f)}&minutes=${LG.min}&lines=${LG.lines}`)).json();
    if(tab!==LG.tab)return;LDATA=tab==='diag'?d:null;rows=d.rows;head=d.head}
  else if(tab==='svc'){const txt=await (await api(`/api/logs/${encodeURIComponent(LG.svc)}?lines=${LG.lines}`)).text();
    if(tab!==LG.tab)return;rows=txt.split('\n').filter(x=>x.trim()&&!x.startsWith('-- ')).map(lparse);LDATA=null;head=`# ${LG.svc} · ${rows.length} Zeilen`}
  else if(tab==='adm'){loadUndo().catch(()=>{});rows=(await adminRows()).slice(0,LG.lines);if(tab!==LG.tab)return;LDATA=null;head=`# ${t('Admin-Protokoll','Admin log')} · ${rows.length}`}
  else{rows=(await auditRows()).slice(0,LG.lines);if(tab!==LG.tab)return;LDATA=null;head=`# ${t('Änderungsprotokoll','Change log')} · ${rows.length}`}
  LROWS=rows;LROWS.head=head;lrender()}
function lshow(){
  $('logreqtab').hidden=!TRACE_ON;const req=LG.tab==='req';$('logreq').hidden=!req;$('logout').hidden=req;$('loglines').hidden=req;$('logcopy').hidden=req;
  document.querySelectorAll('#logtabs button').forEach(b=>b.classList.toggle('on',b.dataset.lt===LG.tab));
  document.querySelectorAll('#logmin button').forEach(b=>b.classList.toggle('on',+b.dataset.v===LG.min));
  const diag=LG.tab==='diag';$('logmin').hidden=!(diag||LG.tab==='update'||req);$('logsum').hidden=!diag;$('logchips').hidden=!req;$('logpick').hidden=$('logerr').hidden=!diag;if(!diag)$('logpick').open=false;
  if(!diag)$('lasterr').hidden=true;if(LG.tab!=='adm')$('logundo').hidden=true;$('logkette').hidden=LG.tab!=='audit';if(LG.tab==='audit')auditChain();$('logsvc').hidden=LG.tab!=='svc';$('logsvc').value=LG.svc;$('loglines').value=String(LG.lines);
  $('loglive').classList.toggle('on',LG.live);$('loglive').setAttribute('aria-pressed',LG.live?'true':'false')}
// the counts of the window as one line of numbers (tabular digits): errors (a tap shows only them), warnings, lines
const lnum=n=>Number(n||0).toLocaleString(L==='en'?'en':'de');
function lsumLine(c){const sum=$('logsum');sum.replaceChildren();
  const err=el('button','lsn'+(c.errors?' bad':'')+(LG.f.includes('errors')?' on':''));err.type='button';err.append(el('b','',lnum(c.errors)),document.createTextNode(' '+t('Fehler','errors')));
  err.onclick=()=>lpickErr(!LG.f.includes('errors'));
  const warn=el('span','lsn');warn.append(el('b','',lnum(c.warnings)),document.createTextNode(' '+t('Warnungen','warnings')));
  const lines=el('span','lsn');lines.append(el('b','',lnum(c.lines)),document.createTextNode(' '+t('Zeilen in ','lines in ')+(LG.min<60?LG.min+' min':LG.min/60+' h')));
  sum.append(err,warn,lines)}
function lpickErr(on){LG.f=on?[...LG.f.filter(x=>x!=='errors'),'errors']:LG.f.filter(x=>x!=='errors');lsave();loadLogs().catch(()=>{})}
// the areas (logfilter.AREAS, here LAREA) as a menu with ticks: built once, the live refresh only sets ticks and counts
function lpickBuild(){const box=$('logpicklist');if(box.childElementCount)return;
  const row=(k,label)=>{const l=el('label','lmi');const c=el('input');c.type='checkbox';c.dataset.k=k;l.append(c,el('span','',label),el('b','lmn'));
    c.onchange=()=>{LG.f=k?(c.checked?[...LG.f,k]:LG.f.filter(x=>x!==k)):LG.f.filter(x=>x==='errors');lsave();loadLogs().catch(()=>{})};return l};
  box.append(row('',t('Alle Bereiche','All areas')));for(const [k,v] of Object.entries(LAREA))box.append(row(k,v[0]))}
function lpickShow(c){lpickBuild();const areas=LG.f.filter(k=>k!=='errors');
  $('logpickt').textContent=areas.length?t(`Bereiche: ${areas.length}`,`Areas: ${areas.length}`):t('Alle Bereiche','All areas');
  $('logpicklist').querySelectorAll('input').forEach(i=>{const k=i.dataset.k;i.checked=k?areas.includes(k):!areas.length;const n=k?c[k]:c.lines;i.parentNode.querySelector('.lmn').textContent=n?lnum(n):''});
  const e=$('logerr'),on=LG.f.includes('errors');e.classList.toggle('on',on);e.setAttribute('aria-pressed',on?'true':'false')}
let AEX=null;   // the open explanation survives the live refresh (every 10 s) while the newest error keeps its area
function areaExplain(area){if(AEX&&AEX.area===area)return AEX.w;const w=el('div','rexpl');AEX={area,w};const eb=el('button','b',t('Erklären','Explain'));eb.type='button';w.append(eb);
  eb.onclick=async()=>{eb.disabled=true;try{const d=await (await api('/api/admin/berater/bereich/'+encodeURIComponent(area))).json();w.replaceChildren();
    for(const l of d.lines||[])w.append(el('div','rd',l));if((d.helps||[]).length)w.append(el('div','rsub',t('Was helfen könnte: ','What could help: ')+d.helps.map(h=>t(h[0],h[1])).join(' · ')));
    const fb=el('button','b',t('Als Fall aufnehmen','Take as a case'));fb.type='button';fb.onclick=async()=>{try{await api('/api/admin/berater/bereich/'+encodeURIComponent(area)+'/fall',{method:'POST'});fb.textContent=t('Aufgenommen: Zustand → Verbessern','Taken: Status → Improve');fb.disabled=true}catch(e){fb.textContent=e.message}};w.append(fb)}
    catch(e){w.replaceChildren(el('div','lempty',e.message))}};return w}
function lrender(){
  if(LG.tab==='req'){rrender();return}
  lshow();const d=LDATA,q=$('logq').value.trim().toLowerCase();
  if(d){const c=d.counts||{};lsumLine(c);lpickShow(c);
    const le=d.last_error,box=$('lasterr');box.hidden=!le;
    if(le){box.replaceChildren(el('b','',t('Letzter Fehler, ','Last error, ')+le.t.slice(0,5)),document.createTextNode(' · '+(LAREA[le.area]?LAREA[le.area][0]+': ':'')+le.msg.replace(/^[a-z0-9_]+:\s*/i,'')));
      if(le.hint)box.append(el('div','lhint',L==='en'?le.hint.en:le.hint.de));
      // „Erklären“ (Einstellungs-Assistent): the error's area in fixed sentences, steps, what could help, „Als Fall aufnehmen“
      if(d.explain&&!document.body.classList.contains('mgr'))box.append(areaExplain(le.area||'other'))}}
  // newest line on top (Diagnose, Update and the service logs come oldest first; the protocols already newest first);
  // at the top the list stays at the top, scrolled down it keeps its place (the live refresh waits there anyway)
  const out=$('logout'),keep=out.scrollTop;
  const base=q?LROWS.filter(r=>(r.msg+' '+(r.area||'')).toLowerCase().includes(q)):LROWS,rows=['diag','update','svc'].includes(LG.tab)?[...base].reverse():base;
  out.replaceChildren(lheadRow());let prev=null;const mins=r=>r.t?(+r.t.slice(0,2))*60+ +r.t.slice(3,5):null;
  for(let i=0;i<rows.length;i++){const r=rows[i];
    const gap=prev&&mins(r)!=null&&mins(prev)!=null?Math.abs(mins(prev)-mins(r)):0;if(gap>=2)out.append(el('div','lgap',t(`${gap} min nichts`,`${gap} min quiet`)));
    let n=1;while(rows[i+1]&&rows[i+1].msg===r.msg&&rows[i+1].area===r.area){n++;i++}
    out.append(lrowEl(r,q,n));prev=r}
  if(!rows.length)out.append(el('div','lempty',q?t('Nichts gefunden.','Nothing found.'):t('Keine Zeilen in diesem Zeitraum.','No lines in this time range.')));
  const name={diag:LG.f.length?LG.f.map(k=>k==='errors'?t('Fehler','errors'):(LAREA[k]||[k])[0]).join(' + '):t('Alles','Everything'),svc:LG.svc,update:'Update',audit:t('Änderungen','Changes'),adm:t('Admin-Protokoll','Admin log')}[LG.tab];
  const span={10:t('letzte 10 min','last 10 min'),60:t('letzte Stunde','last hour'),120:t('letzte 2 Stunden','last 2 hours'),720:t('letzte 12 Stunden','last 12 hours'),1440:t('letzte 24 Stunden','last 24 hours')}[LG.min];
  $('loghead').textContent=name+(LG.tab==='diag'||LG.tab==='update'?' · '+span:'');
  $('logcount').textContent=q?t(`${rows.length} Treffer`,`${rows.length} hits`):(d?t(`${rows.length} von ${d.found} Zeilen`,`${rows.length} of ${d.found} lines`):t(`${rows.length} Zeilen`,`${rows.length} lines`));
  out.scrollTop=out.dataset.seen?keep:0;out.dataset.seen='1'}
// one row of the table: time, area (a word of LAREA or the line's own prefix), level as a dot, the message on one line
// (a click shows it whole; the row keeps its height in the list, only the opened one grows)
const LOPEN=new Set();
function lheadRow(){const h=el('div','lrow lhd');h.setAttribute('aria-hidden','true');h.append(el('span','lt',t('Zeit','Time')),el('span','lbadge',t('Bereich','Area')),el('span','llv',t('Stufe','Level')),el('span','lm',t('Meldung','Message')));return h}
function lrowEl(r,q,n){const row=el('div','lrow'+(r.level?' '+r.level:'')+(LOPEN.has(r.raw)?' open':''));row.append(el('span','lt',r.t||''));
  const pre=(r.msg.match(/^([a-z0-9_]+):\s/i)||[])[1],a=LAREA[r.area];row.append(el('span','lbadge',a?a[0]:(pre||'·')));
  const lv=el('span','llv');if(r.level){lv.title=r.level==='err'?t('Fehler','Error'):t('Warnung','Warning');lv.setAttribute('aria-label',lv.title);lv.append(el('i'))}row.append(lv);
  const m=el('span','lm');const text=pre?r.msg.slice(pre.length+1).trim():r.msg;
  if(q){const low=text.toLowerCase();let at=0,k;while((k=low.indexOf(q,at))>=0){m.append(document.createTextNode(text.slice(at,k)),el('mark','',text.slice(k,k+q.length)));at=k+q.length}m.append(document.createTextNode(text.slice(at)))}
  else m.textContent=text;
  if(n>1)m.prepend(el('span','lrep','×'+n),' ');row.append(m);row.title=r.raw;
  row.onclick=()=>{if(String(window.getSelection()||''))return;row.classList.toggle('open');if(row.classList.contains('open'))LOPEN.add(r.raw);else LOPEN.delete(r.raw)};return row}
function lcopyText(){const q=$('logq').value.trim().toLowerCase();const rows=q?LROWS.filter(r=>(r.msg).toLowerCase().includes(q)):LROWS;
  return `${$('ver').textContent} · ${LROWS.head||''}${q?' · Suche: '+q:''}\n\`\`\`\n${rows.map(r=>r.raw).join('\n')}\n\`\`\``}
// ---------------------------------------------------------------- Anfragen (V01.0.262, tracelog.py)
// One request's way: a list with a bead chain per request, then where the time went and the steps as a time line.
// Only ways, tool names and numbers come from the panel; names only for profiles that allowed it.
const RK={in:['#64748b','inbox'],prep:['#8b5cf6','gear'],weiche:['#8b5cf6','route'],llm:['#5b5bf0','brain'],tool:['#0d9488','wrench'],check:['#16a34a','check'],asr:['#0ea5c6','mic'],tts:['#e07a10','vol'],ack:['#f59e0b','bolt'],err:['#dc2626','x']};   // colour, symbol (icons.js)
const RCLIENT={web:t('Browser','Browser'),speaker:t('Lautsprecher','Speaker'),watch:t('Uhr','Watch'),siri:'Siri',telegram:'Telegram',app:t('iPhone-App','iPhone app'),car:'CarPlay',mcp:t('Programm (MCP)','Program (MCP)'),ha:'Home Assistant',auto:t('Von selbst','By itself'),desk:'Spark-Begleiter',tui:'Terminal',other:t('Gerät','Device')};
const RQ={data:null,sel:null,filter:'',lines:null};
const rsec=ms=>ms==null?'–':ms<1000?`${ms} ms`:(ms/1000).toFixed(1).replace('.',L==='en'?'.':',')+' s';
const rsecs=ms=>(ms/1000).toFixed(1).replace('.',L==='en'?'.':',')+' s';
const rtime=x=>new Date(x.t*1000).toTimeString().slice(0,8);
const rfirst=x=>x.marks&&x.marks.sound!=null?x.marks.sound:(x.marks||{}).end;
async function loadReq(){const d=await (await api(`/api/admin/traces?minutes=${LG.min}`)).json();if(LG.tab!=='req')return;
  RQ.data=d;if(RQ.sel&&!d.items.some(x=>x.id===RQ.sel))RQ.sel=null;if(!RQ.sel&&d.items.length&&!PHONE.matches)RQ.sel=d.items[0].id;rrender()}
function rpill(text,cls){return el('span','rpill'+(cls?' '+cls:''),text)}
// thumbs up or down of the person for this answer (tracelog.vote): thumb, fixed reason, seconds after the answer, never the note
const rvote=x=>(x.vote||{}).v||'';
function rthumb(x){const v=rvote(x);if(!v)return null;const s=el('span','rvote '+(v==='gut'?'up':'dn'));s.appendChild(icNode(v==='gut'?'up_thumb':'down_thumb'));s.title=v==='gut'?t('Gut bewertet','Rated good'):t('Schlecht bewertet','Rated bad');s.setAttribute('aria-label',s.title);return s}
function rreason(x){const g=(x.vote||{}).grund,r=(RQ.data&&RQ.data.reasons||{})[g];return r?t(r[0],r[1]):''}
function rchain(x){const c=el('span','rchain');let n=0;
  (x.steps||[]).filter(s=>s.k!=='weiche'&&s.k!=='check').forEach(s=>{if(n++)c.append(el('s'));
    if(s.k==='tool'){const b=el('i','rtool'+((s.x||{}).ok===false?' bad':''),wzName(s.n));b.title=s.n;c.append(b)}else{const i=el('i');i.style.background=RK[s.k][0];i.title=s.n;c.append(i)}});return c}
function rlist(items){const box=el('div','rlist');
  for(const x of items){const b=el('button','rq'+(x.id===RQ.sel?' on':'')+(x.status==='err'?' err':x.status==='slow'?' slow':''));b.type='button';
    const top=el('div','rtop');top.append(el('span','rt',rtime(x)),el('b','',x.name));top.append(el('span','rdev',' · '+(x.device||RCLIENT[x.client]||x.client)));
    top.append(el('span','rid',' · '+x.id),el('span','rdur',rsec(rfirst(x))));const th=rthumb(x);if(th)top.append(th);b.append(top);
    const row=el('div','rrow');if(x.intent)row.append(rpill(x.intent,'int'));row.append(rchain(x));b.append(row);
    b.onclick=()=>{RQ.sel=x.id;RQ.lines=null;rrender();if(PHONE.matches)window.scrollTo(0,0)};box.append(b)}
  if(!items.length)box.append(el('div','lempty',RQ.data&&!RQ.data.on?t('Die Aufzeichnung ist aus: Einstellungen → Spark → Betrieb → Anfragen verfolgen.','Recording is off: Settings → Spark → Operation → Trace requests.'):t('Keine Anfragen in diesem Zeitraum.','No requests in this time range.')));
  return box}
function rdesc(s){const x=s.x||{},p=[];
  if(s.k==='in'){if(x.chars!=null)p.push(t(`${x.chars} Zeichen`,`${x.chars} characters`));if(x.voice)p.push(t('Stimme erkannt','voice recognized'));if(x.pictures)p.push(t(`${x.pictures} Bild(er)`,`${x.pictures} picture(s)`));if(x.attachment)p.push(t('Anhang','attachment'));if(x.stufe)p.push(x.stufe==='vorrang'?t('mit Vorrang','with priority'):t('hinten angestellt','last in line'))}
  else if(s.k==='prep'){if(x.rights)p.push(t('Rechte: ','Rights: ')+x.rights);if(x.allowed!=null)p.push(t(`${x.allowed} Werkzeuge erlaubt`,`${x.allowed} tools allowed`));if(x.locked)p.push(t('gesperrt nach ','locked after ')+(x.locked==='mail'?'Mail':t('Text von außen','outside text')));if(x.history!=null)p.push(t(`Verlauf ${x.history} Nachrichten`,`history ${x.history} messages`));if(x.facts!=null)p.push(t(`${x.facts} Einträge: ${x.confirmed||0} bestätigt, ${x.learned||0} gelernt, ${x.stale||0} als „unsicher“ ans Modell`,`${x.facts} entries: ${x.confirmed||0} confirmed, ${x.learned||0} learned, ${x.stale||0} to the model as "unsure"`))}
  else if(s.k==='weiche'){if(x.offered!=null)p.push(t(`Werkzeuge ${x.offered} von ${x.of??x.offered}`,`tools ${x.offered} of ${x.of??x.offered}`));p.push(x.narrow?t('eingrenzen an','narrowing on'):t('eingrenzen aus','narrowing off'));if(x.must)p.push(t('Pflicht: ','required: ')+x.must);if(x.why)p.push(t('Grund: ','reason: ')+x.why);if(x.herkunft)p.push(t('Herkunft: ','origin: ')+x.herkunft);if(x.model)p.push((x.via==='systemone'?t('Einordnung (systemone): ','classification (systemone): '):t('Modell-Zuordnung: ','model pick: '))+({'gewählt':t('gewählt','picked'),'zu spät':t('zu spät','too late'),'keine':t('keine','none'),'unsicher':t('zu unsicher','too unsure')}[x.model]||x.model)+(x.sure!=null?` (${Math.round(x.sure*100)} %)`:''))}
  else if(s.k==='llm'){if(x.tokens)p.push(t(`${x.tokens} Tokens gelesen`,`${x.tokens} tokens read`));if(x.cached!=null)p.push(t(`davon ${x.cached} aus dem Zwischenspeicher`,`${x.cached} of them from the cache`));if(x.system_chars!=null)p.push(t(`Zeichen: Anweisung ${x.system_chars}, Werkzeuge ${x.tool_chars||0}, Gespräch ${x.history_chars||0}`,`characters: instructions ${x.system_chars}, tools ${x.tool_chars||0}, conversation ${x.history_chars||0}`));if(x.tools)p.push(t(`${x.tools} Werkzeuge angeboten`,`${x.tools} tools offered`));p.push(x.calls?t('ruft: ','calls: ')+x.calls:t('antwortet','answers'));if(x.first!=null)p.push(t('erstes Zeichen nach ','first output after ')+rsec(x.first));if(x.think)p.push(t(`${x.think} Zeichen Denktext`,`${x.think} chars of thinking`));if(x.held_ms)p.push(t('wartete ','waited ')+rsec(x.held_ms)+t(' auf eine Antwort mit Vorrang',' for an answer with priority'))}
  else if(s.k==='tool'){if(wzName(s.n)!==s.n)p.push(s.n);p.push(x.ok===false?t('nicht ok','not ok'):'ok');if(x.chars)p.push(t(`${x.chars} Zeichen Ergebnis`,`${x.chars} chars result`));if(x.outside)p.push(t('Text von außen, nur als Daten','outside text, as data only'));if(x.panel)p.push(t('vom Panel ausgeführt','run by the panel'));if(x.hits!=null)p.push(t(`${x.hits} Treffer`,`${x.hits} hits`)+[['docs',t('Dokumente','documents')],['archive',t('Archiv','archive')],['history',t('Verlauf','history')]].filter(([k])=>x[k]!=null).map(([k,l])=>` · ${l} ${x[k]}`).join('')+(x.late?t(` · ${x.late} zu langsam`,` · ${x.late} too slow`):''));if(x.many)p.push(t('zu viele Aufrufe in einer Runde','too many calls in one round'));if(x.locked)p.push(t('war nicht angeboten','was not offered'))}
  else if(s.k==='check'){p.push(x.again?t('ohne Werkzeug geantwortet, neu gefragt','answered without a tool, asked again'):x.held?t(`${x.held} Angabe(n) ohne Quelle zurückgehalten`,`${x.held} claim(s) without a source held back`):t('alles belegt','everything backed'))}
  else if(s.k==='tts'){p.push(t(`${x.pieces||0} Stück(e) · ${x.chars||0} Zeichen`,`${x.pieces||0} piece(s) · ${x.chars||0} chars`));if(x.behind)p.push(t(`${x.behind}× Ton gestockt`,`sound stalled ${x.behind}×`));if(x.waited_ms)p.push(t('wartete ','waited ')+rsec(x.waited_ms));if(x.overtook)p.push(t(`überholte ${x.overtook} wartende`,`overtook ${x.overtook} waiting`));if(x.empty)p.push(t(`${x.empty} ohne Sprechbares übersprungen`,`${x.empty} with nothing to say skipped`))}
  else if(s.k==='ack')p.push(x.bridge?t('zweiter fertiger Satz, die Antwort dauerte','second ready-made sentence, the answer took longer'):t('fertiger Satz aus der Aufnahme, ohne Grafikkarte','ready-made sentence from its recording, no GPU'));
  else if(s.k==='err')p.push(t('vorzeitig beendet, z. B. ins Wort gefallen oder Seite geschlossen','ended early, e.g. barge-in or page closed'));
  return p.join(' · ')}
function rtitle(s){return s.k==='prep'?(/^Gedächtnis/.test(s.n)?t('Gedächtnis (Panel)','Memory (panel)'):/^Nachfrage/.test(s.n)?t('Nachfrage zum Gedächtnis (Panel)','Memory check-back (panel)'):t('Panel-Vorbereitung','Panel preparation')):s.k==='weiche'?t('Weiche: ','Switch: ')+s.n.replace(/^Weiche: /,''):s.k==='llm'?s.n.replace(/^Runde/,t('Sprachmodell, Runde','Language model, round')):s.k==='check'?t('Antwort-Prüfung','Answer check'):s.k==='tts'?t('Sprachausgabe','Speech output'):s.k==='ack'?(s.n==='Brücke'?t('Brücke','Bridge'):t('Sofortige Rückmeldung','Instant acknowledgement')):s.k==='err'?t('abgebrochen','aborted'):s.k==='in'?t('Eingang · ','Arrival · ')+s.n:s.k==='tool'?wzName(s.n):s.n}
function rshares(x){const sum={prep:0,llm:0,tool:0,tts:0};(x.steps||[]).forEach(s=>{const k=s.k==='weiche'?'prep':s.k;if(k in sum)sum[k]+=s.d||0});
  const tot=Object.values(sum).reduce((a,b)=>a+b,0)||1,bar=el('div','rbar'),leg=el('div','rleg');
  [['prep',t('Panel','Panel')],['llm',t('Sprachmodell','Language model')],['tool',t('Werkzeuge','Tools')],['tts',t('Sprachausgabe','Speech output')]].forEach(([k,label])=>{
    if(!sum[k])return;const i=el('i');i.style.background=RK[k][0];i.style.width=(sum[k]/tot*100)+'%';i.title=`${label} ${rsec(sum[k])}`;bar.append(i);
    const s=el('span');const c=el('i');c.style.background=RK[k][0];s.append(c,document.createTextNode(`${label} ${rsec(sum[k])}`));leg.append(s)});
  const box=el('div','rshare');box.append(el('div','rsub',t('Wohin die Zeit ging','Where the time went')),bar,leg);return box}
function rsteps(x){const list=[...(x.steps||[])].map(s=>({...s}));const m=x.marks||{};
  if(m.first!=null)list.push({k:'mark',c:RK.llm[0],n:t('erstes Wort','first word'),a:m.first});
  if(m.ack!=null)list.push({k:'mark',c:RK.ack[0],n:t('erste Rückmeldung beim Gerät','first acknowledgement at the device'),a:m.ack});
  if(m.sound!=null)list.push({k:'mark',c:RK.tts[0],n:t('erster Ton beim Gerät','first sound at the device'),a:m.sound});
  list.sort((a,b)=>a.a-b.a||(a.k==='mark')-(b.k==='mark'));if(m.end!=null)list.push({k:'mark',c:x.status==='err'?'#dc2626':'#16a34a',n:t('fertig','done'),a:m.end});
  const tl=el('div','rtl');
  for(const s of list){const row=el('div','rst'+(s.k==='mark'?' mark':'')+(s.k==='tool'?' tw':''));row.append(el('span','rat',rsecs(s.a)));
    const dot=el('span','ric');if(s.k!=='mark')dot.appendChild(icNode(RK[s.k][1]));dot.style.background=s.k==='mark'?s.c:RK[s.k][0];row.append(dot);
    const tx=el('div','rtx');const b=el('b','',s.k==='mark'?s.n:rtitle(s));if(s.k==='mark')b.style.color=s.c;tx.append(b);
    if(s.k!=='mark'){const d=rdesc(s);if(d)tx.append(el('div','rd',d))}
    // „Falsch zugeordnet …“ (Funktionen → Weiche): the question is never recorded, the admin types it there again
    if(s.k==='weiche'&&typeof whOpenFix==='function'&&!document.body.classList.contains('mgr')){const g=String(s.n||'').replace(/^Weiche: /,'').replace(/^-$/,'unklar');
      const b=el('button','mlink',t('Falsch zugeordnet …','Wrongly sorted …'));b.type='button';b.onclick=e=>{e.stopPropagation();whOpenFix('',g.includes('+')?'mehrere':g)};tx.append(b)}if(s.k==='tool'&&(s.x||{}).ok===false)row.classList.add('bad');row.append(tx);
    row.append(s.k==='mark'?el('span'):el('span','rdu',s.d||['tool','llm','tts','prep'].includes(s.k)?rsec(s.d||0):'–'));tl.append(row)}
  return tl}
async function rshowLines(x,box){box.replaceChildren(el('div','lempty',t('Lade …','Loading …')));
  try{const d=await (await api('/api/admin/traces/'+encodeURIComponent(x.id))).json();RQ.lines=d.lines||[];RQ.linesFor=x.id;rlinesShow(box)}
  catch(e){box.replaceChildren(el('div','lempty',e.message))}}
function rlinesShow(box){box.replaceChildren();
    const out=el('div','lout rlines');out.append(lheadRow());for(const r of RQ.lines)out.append(lrowEl(r,'',1));
    if(!RQ.lines.length)out.append(el('div','lempty',t('Keine Logzeilen aus dieser Zeit.','No log lines from this time.')));
    box.append(el('div','rsub',t('Logzeilen aus dieser Zeit (gleichzeitige Anfragen können dazwischen stehen)','Log lines from this time (requests at the same moment may show too)')),out)}
// an error code of a request as a plain sentence (klartext.CODES, sent with the list); the code stays small beside it
function rerr(c){const x=((RQ.data||{}).codes||{})[c];return x?t(x[0],x[1]):c}
function rdetail(x){const box=el('div','rdet');
  if(PHONE.matches){const back=el('button','rback',t('‹ Anfragen','‹ Requests'));back.type='button';back.onclick=()=>{RQ.sel=null;RQ.lines=null;rrender()};box.append(back)}
  box.append(el('h3','',t(`Anfrage ${x.id} von ${x.name} · ${rtime(x)}`,`Request ${x.id} from ${x.name} · ${rtime(x)}`)));
  const rounds=(x.steps||[]).filter(s=>s.k==='llm').length,tools=(x.steps||[]).filter(s=>s.k==='tool').length,m=x.marks||{};
  const sub=el('div','rsub');sub.append(document.createTextNode((x.device?x.device+' · ':'')+(RCLIENT[x.client]||x.client)+' · '+t('Absicht ','intent ')));sub.append(rpill(x.intent||'–','int'));
  sub.append(document.createTextNode(' · '+t(`${rounds} Runde(n) · ${tools} Werkzeug(e)`,`${rounds} round(s) · ${tools} tool(s)`)+(m.sound!=null?' · '+t('erster Ton ','first sound ')+rsecs(m.sound):'')+' · '+t('fertig ','done ')+rsecs(m.end||0)));box.append(sub);
  if((x.errors||[]).length){const eb=el('div','lasterr');for(const c of x.errors){const r=el('div','',t('Fehler: ','Error: ')+rerr(c)+' ');r.append(el('code','lcode',c));eb.append(r)}box.append(eb)}
  if(rvote(x)){const v=x.vote,vb=el('div','rvoted '+(v.v==='gut'?'up':'dn'));const r=rreason(x);
    vb.append(icNode(v.v==='gut'?'up_thumb':'down_thumb'),el('b','',' '+t(`Bewertet nach ${v.after} s`,`Rated after ${v.after} s`)+(r?' · '+t('Grund: ','Reason: ')+r:'')));
    if(v.case&&typeof window.openCase==='function'&&!document.body.classList.contains('mgr')){const cb=el('button','mlink',t('Fall öffnen: Zustand → Verbessern','Open case: Status → Improve'));cb.type='button';cb.onclick=()=>window.openCase(v.case);vb.append(document.createTextNode(' '),cb)}
    box.append(vb)}
  const bar=el('div','lbar');const lb=el('button','b',t('Zugehörige Logzeilen','Related log lines'));lb.type='button';const cp=el('button','b',t('Kopieren für Thread','Copy for thread'));cp.type='button';
  cp.onclick=()=>copyString(rcopyText(),cp);bar.append(lb,cp);box.append(bar);
  // „Erklären“ (Einstellungs-Assistent, berater.py): the request in fixed sentences and what could help; „Als Fall aufnehmen“
  const ex=el('div','rexpl');if(RQ.data&&RQ.data.explain&&!document.body.classList.contains('mgr')){const eb=el('button','b',t('Erklären','Explain'));eb.type='button';bar.append(eb);
    eb.onclick=async()=>{ex.replaceChildren(el('div','lempty',t('Lade …','Loading …')));try{const d=await (await api('/api/admin/berater/erklaeren/'+encodeURIComponent(x.id))).json();ex.replaceChildren();
      for(const l of d.lines||[])ex.append(el('div','rd',l));if((d.helps||[]).length)ex.append(el('div','rsub',t('Was helfen könnte: ','What could help: ')+d.helps.map(h=>t(h[0],h[1])).join(' · ')));
      const fb=el('button','b',t('Als Fall aufnehmen','Take as a case'));fb.type='button';fb.onclick=async()=>{try{await api('/api/admin/berater/erklaeren/'+encodeURIComponent(x.id)+'/fall',{method:'POST'});fb.textContent=t('Aufgenommen: Zustand → Verbessern','Taken: Status → Improve');fb.disabled=true}catch(e){fb.textContent=e.message}};ex.append(fb)}
      catch(e){ex.replaceChildren(el('div','lempty',e.message))}}}
  box.append(ex);
  box.append(el('div','rnote',t('Ohne Frage- und Antworttext: nur Wege, Werkzeugnamen, Zahlen und Zeiten.','Without question or answer text: only ways, tool names, numbers and times.')+(x.named?'':' '+t('Name nur, wenn das Profil es erlaubt.','Name only when the profile allows it.'))));
  box.append(rshares(x),rsteps(x));const lines=el('div','rlinesbox');box.append(lines);lb.onclick=()=>rshowLines(x,lines);if(RQ.lines&&RQ.linesFor===x.id)rlinesShow(lines);return box}
function rfiltered(){const d=RQ.data;if(!d)return [];const q=$('logq').value.trim().toLowerCase();
  return d.items.filter(x=>(!RQ.filter||(RQ.filter==='gut'||RQ.filter==='schlecht'?rvote(x)===RQ.filter:x.status===RQ.filter))&&(!q||[x.id,x.name,x.device,x.client,x.intent,...(x.steps||[]).map(s=>s.k==='tool'?s.n+' '+wzName(s.n):s.n)].join(' ').toLowerCase().includes(q)))}
function rrender(){lshow();const d=RQ.data,box=$('logreq'),chips=$('logchips');if(!d)return;
  chips.replaceChildren();const n=k=>d.items.filter(x=>x.status===k).length;
  const nv=k=>d.items.filter(x=>rvote(x)===k).length;
  [['',t('Alle','All'),'',d.items.length],['err',t('Fehler','Errors'),'#ef4444',n('err')],['slow',t('Langsam','Slow'),'#f59e0b',n('slow')],['gut',t('Gut bewertet','Rated good'),'#16a34a',nv('gut'),'up_thumb'],['schlecht',t('Schlecht bewertet','Rated bad'),'#dc2626',nv('schlecht'),'down_thumb']].forEach(([k,label,c,cnt,sym])=>{
    const b=el('button','lchip'+(RQ.filter===k?' on':''));b.type='button';if(c){b.style.setProperty('--c',c);b.append(el('i'))}if(sym){b.appendChild(icNode(sym));b.setAttribute('aria-label',label);b.title=label}else b.append(document.createTextNode(label));b.append(el('b','',String(cnt)));
    b.setAttribute('aria-pressed',RQ.filter===k?'true':'false');b.onclick=()=>{RQ.filter=k;rrender()};chips.append(b)});
  // the live refresh (every 10 s) builds the list anew: it keeps where the person had scrolled to (V01.0.387, Dominik
  // 2026-10-11: the list jumped back to the top while picking a request)
  const old=box.querySelector('.rlist'),keep=old?old.scrollTop:0,keepY=window.scrollY;
  const items=rfiltered(),sel=d.items.find(x=>x.id===RQ.sel);box.replaceChildren();box.classList.toggle('one',!!(PHONE.matches&&sel));
  if(!(PHONE.matches&&sel))box.append(rlist(items));if(sel)box.append(rdetail(sel));
  const now=box.querySelector('.rlist');if(now&&keep)now.scrollTop=keep;if(window.scrollY!==keepY)window.scrollTo(0,keepY);
  $('loghead').textContent=t('Anfragen','Requests')+(d.on?'':' · '+t('Aufzeichnung aus','recording off'));
  $('logcount').textContent=t(`${items.length} von ${d.items.length} · höchstens ${d.keep_hours} h`,`${items.length} of ${d.items.length} · at most ${d.keep_hours} h`)}
function rcopyText(){const x=RQ.data&&RQ.data.items.find(y=>y.id===RQ.sel);if(!x)return '';const m=x.marks||{};
  const head=`${$('ver').textContent} · Anfrage ${x.id} · ${rtime(x)} · ${RCLIENT[x.client]||x.client} · ${x.intent||'-'}`+(m.ack!=null?` · Rückmeldung ${rsecs(m.ack)}`:'')+(m.sound!=null?` · erster Ton ${rsecs(m.sound)}`:'')+` · fertig ${rsecs(m.end||0)} · ${x.errors.length?x.errors.join(', '):x.status}`+(rvote(x)?` · Bewertung ${x.vote.v==='gut'?'gut':'schlecht'}`+(rreason(x)?` (${rreason(x)})`:''):'');
  const rows=[...(x.steps||[])].sort((a,b)=>a.a-b.a).map(s=>`+${(s.a/1000).toFixed(2)} ${rtitle(s)} ${s.d?rsec(s.d):''} (${rdesc(s)})`.replace(' ()',''));
  return `${head}\n\`\`\`\n${rows.join('\n')}\n\`\`\``}
// detail switches (Ausführlich): admin only, off by default, switch themselves off
async function loadVerbose(){const box=$('logverbose');let d;try{d=await (await api('/api/logverbose')).json()}catch{return}
  box.replaceChildren();const det=el('details','adv');const sm=el('summary','',t('Erweitert','Advanced'));sm.append(el('span','mut',t(' · ausführliche Diagnose pro Bereich',' · detailed diagnosis per area')));det.append(sm);
  det.append(el('div','fh',t('Schreibt zusätzlich Zeiten, Längen und Entscheidungen ins Log, nie Texte, Namen oder Geheimnisse. Schaltet sich selbst wieder ab, spätestens beim Neustart.','Adds times, lengths and decisions to the log, never text, names or secrets. Switches itself off again, at the latest on restart.')));
  const on=Object.values(d.areas).some(v=>v>0);if(on)det.open=true;
  for(const [a,label] of Object.entries(LV_AREAS)){const left=d.areas[a]||0,row=el('div','setrow');const lbl=el('div','lbl');lbl.append(el('b','',label),el('span','',left?t(`an, noch ${Math.ceil(left/60)} min`,`on, ${Math.ceil(left/60)} min left`):t('aus','off')));
    const sel=el('select','lsel');sel.setAttribute('aria-label',label);[[0,t('aus','off')],...d.minutes.map(m=>[m,m<60?t(`${m} min`,`${m} min`):t(`${m/60} h`,`${m/60} h`)])].forEach(([v,txt])=>{const o=el('option','',txt);o.value=v;sel.append(o)});
    sel.value=left?String(d.minutes.find(m=>m*60>=left)||d.minutes[d.minutes.length-1]):'0';
    sel.onchange=async()=>{try{await api('/api/logverbose',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({area:a,minutes:+sel.value})})}catch(e){alert(e.message)}loadVerbose()};
    row.append(lbl,sel);det.append(row)}
  box.append(det)}
document.querySelectorAll('#logtabs button').forEach(b=>b.onclick=()=>{LG.tab=b.dataset.lt;lsave();$('logout').dataset.seen='';loadLogs().catch(()=>{})});
document.querySelectorAll('#logmin button').forEach(b=>b.onclick=()=>{LG.min=+b.dataset.v;lsave();loadLogs().catch(()=>{})});
$('loglines').onchange=()=>{LG.lines=+$('loglines').value;lsave();loadLogs().catch(()=>{})};
$('logsvc').onchange=()=>{LG.svc=$('logsvc').value;lsave();loadLogs().catch(()=>{})};
$('logq').oninput=()=>lrender();
$('logerr').onclick=()=>lpickErr(!LG.f.includes('errors'));
document.addEventListener('click',e=>{const m=$('logpick');if(m.open&&!m.contains(e.target))m.open=false});
$('logpick').addEventListener('keydown',e=>{if(e.key==='Escape'){$('logpick').open=false;$('logpick').querySelector('summary').focus()}});
$('loglive').onclick=()=>{LG.live=!LG.live;lsave();try{localStorage.setItem('logfollow',LG.live?'1':'0')}catch{}lshow();if(LG.live)loadLogs().catch(()=>{})};
$('logcopy').onclick=()=>copyString(LG.tab==='req'?rcopyText():lcopyText(),$('logcopy'));
const _ll=loadLogs;window.loadLogs=async()=>{await _ll();loadVerbose()};
// live: diagnosis every 10 s, service logs every 3 s; pauses while scrolled down, the area menu is open or text is selected
setInterval(()=>{if(!LG.live||!$('logs').classList.contains('on')||document.hidden)return;
  const out=$('logout');if(out.scrollTop>30||$('logpick').open||String(window.getSelection()||''))return;
  if(Date.now()-LAT<(LG.tab==='svc'?3000:10000))return;_ll().catch(()=>{})},1000);
lshow();

// Zustand → Live: "Anfrage öffnen" jumps here with the request selected (empty id: just the list)
window.openTrace=id=>{LG.tab='req';lsave();RQ.sel=id||null;RQ.lines=null;const q=$('logq');if(q)q.value=id||'';if(typeof goSec==='function')goSec('logs')};
