// Zustand → Logs (V01.0.212, "Überblick zuerst"): tiles per area, the newest error with a fixed hint, filter
// buttons, a tidy list (time, area, message; errors red, repeats ×n, pauses), search in the browser only,
// live reload, copy for a thread, and the per-area detail switches. Lines are built with textContent only.
const LAREA={chat:[t('Gespräch','Conversation'),'#6366f1'],search:[t('Websuche','Web search'),'#0ea5e9'],weiche:[t('Weiche','Router'),'#8b5cf6'],
  ha:['Home Assistant','#f59e0b'],room:[t('Raum','Room'),'#10b981'],esp32:[t('Lautsprecher','Speakers'),'#14b8a6'],watch:[t('Uhr','Watch'),'#ec4899'],telegram:['Telegram','#3b82f6'],mail:['Mail','#64748b'],vorrang:[t('Vorrang','Priority'),'#ef4444'],wissen:[t('Wissen','Knowledge'),'#a16207'],anfrage:[t('Anfrage','Request'),'#5b5bf0']};
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
  else if(tab==='adm'){rows=(await adminRows()).slice(-LG.lines);if(tab!==LG.tab)return;LDATA=null;head=`# ${t('Admin-Protokoll','Admin log')} · ${rows.length}`}
  else{rows=(await auditRows()).slice(-LG.lines);if(tab!==LG.tab)return;LDATA=null;head=`# ${t('Änderungsprotokoll','Change log')} · ${rows.length}`}
  LROWS=rows;LROWS.head=head;lrender()}
function lshow(){
  $('logreqtab').hidden=!TRACE_ON;const req=LG.tab==='req';$('logreq').hidden=!req;$('logout').hidden=req;$('loglines').hidden=req;$('logcopy').hidden=req;
  document.querySelectorAll('#logtabs button').forEach(b=>b.classList.toggle('on',b.dataset.lt===LG.tab));
  document.querySelectorAll('#logmin button').forEach(b=>b.classList.toggle('on',+b.dataset.v===LG.min));
  const diag=LG.tab==='diag';$('logmin').hidden=!(diag||LG.tab==='update'||req);$('logsum').hidden=!diag;$('logchips').hidden=!(diag||req);
  if(!diag)$('lasterr').hidden=true;$('logsvcbar').hidden=LG.tab!=='svc';$('logsvc').value=LG.svc;$('loglines').value=String(LG.lines);
  $('loglive').classList.toggle('on',LG.live);$('loglive').setAttribute('aria-pressed',LG.live?'true':'false')}
function ltile(key,label,color,count,spark,sub){
  const b=el('button','ltile'+(key==='errors'?' err':'')+(LG.f.length===1&&LG.f[0]===key?' on':''));b.type='button';b.style.setProperty('--c',color);
  b.append(el('span','',label),el('b','',String(count||0)));
  if(spark){const s=el('div','lspark');const top=Math.max(1,...spark);spark.forEach(v=>{const i=el('i');i.style.height=(3+Math.round(v/top*22))+'px';s.append(i)});b.append(s)}
  if(sub)b.append(el('div','lsub',sub));
  b.onclick=()=>{LG.f=[key];lsave();loadLogs().catch(()=>{})};return b}
function lrender(){
  if(LG.tab==='req'){rrender();return}
  lshow();const d=LDATA,sum=$('logsum'),chips=$('logchips'),q=$('logq').value.trim().toLowerCase();
  if(d){const c=d.counts||{};sum.replaceChildren();
    const ea=Object.entries(d.errors_by_area||{}).sort((a,b)=>b[1]-a[1]).slice(0,2).map(([a,n])=>`${n} ${(LAREA[a]||[a==='other'?t('Sonstiges','other'):a])[0]}`).join(' · ');
    sum.append(ltile('errors',t('Fehler','Errors'),'#ef4444',c.errors,null,c.errors?ea:t('alles ruhig','all quiet')));
    Object.keys(LAREA).filter(a=>c[a]).sort((a,b)=>c[b]-c[a]).slice(0,3).forEach(a=>sum.append(ltile(a,LAREA[a][0],LAREA[a][1],c[a],(d.spark||{})[a])));
    const le=d.last_error,box=$('lasterr');box.hidden=!le;
    if(le){box.replaceChildren(el('b','',t('Letzter Fehler, ','Last error, ')+le.t.slice(0,5)),document.createTextNode(' · '+(LAREA[le.area]?LAREA[le.area][0]+': ':'')+le.msg.replace(/^[a-z0-9_]+:\s*/i,'')));
      if(le.hint)box.append(el('div','lhint',L==='en'?le.hint.en:le.hint.de))}
    chips.replaceChildren();
    [...Object.keys(LAREA),'update','errors'].filter(k=>k!=='update').forEach(k=>{const on=LG.f.includes(k),b=el('button','lchip'+(on?' on':'')+(k==='errors'?' err':''));b.type='button';
      b.style.setProperty('--c',k==='errors'?'#ef4444':LAREA[k][1]);b.append(el('i'),document.createTextNode(k==='errors'?t('Nur Fehler','Errors only'):LAREA[k][0]));
      const n=k==='errors'?c.errors:c[k];if(n)b.append(el('b','',String(n)));b.setAttribute('aria-pressed',on?'true':'false');
      b.onclick=()=>{LG.f=on?LG.f.filter(x=>x!==k):[...LG.f,k];lsave();loadLogs().catch(()=>{})};chips.append(b)});
    const all=el('button','lchip'+(LG.f.length?'':' on'),t('Alle','All'));all.type='button';all.onclick=()=>{LG.f=[];lsave();loadLogs().catch(()=>{})};chips.prepend(all)}
  const out=$('logout'),stick=out.scrollTop+out.clientHeight>=out.scrollHeight-30;
  const rows=q?LROWS.filter(r=>(r.msg+' '+(r.area||'')).toLowerCase().includes(q)):LROWS;
  out.replaceChildren();let prev=null;const mins=r=>r.t?(+r.t.slice(0,2))*60+ +r.t.slice(3,5):null;
  for(let i=0;i<rows.length;i++){const r=rows[i];
    const gap=prev&&mins(r)!=null&&mins(prev)!=null?mins(r)-mins(prev):0;if(gap>=2)out.append(el('div','lgap',t(`${gap} min nichts`,`${gap} min quiet`)));
    let n=1;while(rows[i+1]&&rows[i+1].msg===r.msg&&rows[i+1].area===r.area){n++;i++}
    const row=el('div','lrow'+(r.level?' '+r.level:''));row.append(el('span','lt',r.t||''));
    const pre=(r.msg.match(/^([a-z0-9_]+):\s/i)||[])[1],a=LAREA[r.area];
    const badge=el('span','lbadge',a?a[0]:(pre||'·'));badge.style.setProperty('--c',a?a[1]:'#94a3b8');row.append(badge);
    const m=el('span','lm');const text=pre?r.msg.slice(pre.length+1).trim():r.msg;
    if(q){const low=text.toLowerCase();let at=0,k;while((k=low.indexOf(q,at))>=0){m.append(document.createTextNode(text.slice(at,k)),el('mark','',text.slice(k,k+q.length)));at=k+q.length}m.append(document.createTextNode(text.slice(at)))}
    else m.textContent=text;
    if(n>1)m.append(' ',el('span','lrep','×'+n));row.append(m);row.title=r.raw;out.append(row);prev=r}
  if(!rows.length)out.append(el('div','lempty',q?t('Nichts gefunden.','Nothing found.'):t('Keine Zeilen in diesem Zeitraum.','No lines in this time range.')));
  const name={diag:LG.f.length?LG.f.map(k=>k==='errors'?t('Fehler','errors'):(LAREA[k]||[k])[0]).join(' + '):t('Alles','Everything'),svc:LG.svc,update:'Update',audit:t('Änderungen','Changes'),adm:t('Admin-Protokoll','Admin log')}[LG.tab];
  const span={10:t('letzte 10 min','last 10 min'),60:t('letzte Stunde','last hour'),120:t('letzte 2 Stunden','last 2 hours'),720:t('letzte 12 Stunden','last 12 hours'),1440:t('letzte 24 Stunden','last 24 hours')}[LG.min];
  $('loghead').textContent=name+(LG.tab==='diag'||LG.tab==='update'?' · '+span:'');
  $('logcount').textContent=q?t(`${rows.length} Treffer`,`${rows.length} hits`):(d?t(`${rows.length} von ${d.found} Zeilen`,`${rows.length} of ${d.found} lines`):t(`${rows.length} Zeilen`,`${rows.length} lines`));
  if(stick||!out.dataset.seen){out.scrollTop=1e9;out.dataset.seen='1'}}
function lcopyText(){const q=$('logq').value.trim().toLowerCase();const rows=q?LROWS.filter(r=>(r.msg).toLowerCase().includes(q)):LROWS;
  return `${$('ver').textContent} · ${LROWS.head||''}${q?' · Suche: '+q:''}\n\`\`\`\n${rows.map(r=>r.raw).join('\n')}\n\`\`\``}
// ---------------------------------------------------------------- Anfragen (V01.0.262, tracelog.py)
// One request's way: a list with a bead chain per request, then where the time went and the steps as a time line.
// Only ways, tool names and numbers come from the panel; names only for profiles that allowed it.
const RK={in:['#64748b','↘'],prep:['#8b5cf6','⚙'],weiche:['#8b5cf6','⑂'],llm:['#5b5bf0','◆'],tool:['#0d9488','⚒'],check:['#16a34a','✓'],tts:['#e07a10','♪'],err:['#dc2626','✕']};
const RCLIENT={web:t('Browser','Browser'),speaker:t('Lautsprecher','Speaker'),watch:t('Uhr','Watch'),siri:'Siri',telegram:'Telegram',app:t('iPhone-App','iPhone app'),car:'CarPlay',other:t('Gerät','Device')};
const RQ={data:null,sel:null,filter:'',lines:null};
const rsec=ms=>ms==null?'–':ms<1000?`${ms} ms`:(ms/1000).toFixed(1).replace('.',L==='en'?'.':',')+' s';
const rsecs=ms=>(ms/1000).toFixed(1).replace('.',L==='en'?'.':',')+' s';
const rtime=x=>new Date(x.t*1000).toTimeString().slice(0,8);
const rfirst=x=>x.marks&&x.marks.sound!=null?x.marks.sound:(x.marks||{}).end;
async function loadReq(){const d=await (await api(`/api/admin/traces?minutes=${LG.min}`)).json();if(LG.tab!=='req')return;
  RQ.data=d;if(RQ.sel&&!d.items.some(x=>x.id===RQ.sel))RQ.sel=null;if(!RQ.sel&&d.items.length&&!PHONE.matches)RQ.sel=d.items[0].id;rrender()}
function rpill(text,cls){return el('span','rpill'+(cls?' '+cls:''),text)}
function rchain(x){const c=el('span','rchain');let n=0;
  (x.steps||[]).filter(s=>s.k!=='weiche'&&s.k!=='check').forEach(s=>{if(n++)c.append(el('s'));
    if(s.k==='tool'){const b=el('i','rtool'+((s.x||{}).ok===false?' bad':''),s.n);c.append(b)}else{const i=el('i');i.style.background=RK[s.k][0];i.title=s.n;c.append(i)}});return c}
function rlist(items){const box=el('div','rlist');
  for(const x of items){const b=el('button','rq'+(x.id===RQ.sel?' on':'')+(x.status==='err'?' err':x.status==='slow'?' slow':''));b.type='button';
    const top=el('div','rtop');top.append(el('span','rt',rtime(x)),el('b','',x.name));top.append(el('span','rdev',' · '+(x.device||RCLIENT[x.client]||x.client)));
    top.append(el('span','rdur',rsec(rfirst(x))));b.append(top);
    const row=el('div','rrow');if(x.intent)row.append(rpill(x.intent,'int'));row.append(rchain(x));b.append(row);
    b.onclick=()=>{RQ.sel=x.id;RQ.lines=null;rrender();if(PHONE.matches)window.scrollTo(0,0)};box.append(b)}
  if(!items.length)box.append(el('div','lempty',RQ.data&&!RQ.data.on?t('Die Aufzeichnung ist aus: Einstellungen → Spark → Betrieb → Anfragen verfolgen.','Recording is off: Settings → Spark → Operation → Trace requests.'):t('Keine Anfragen in diesem Zeitraum.','No requests in this time range.')));
  return box}
function rdesc(s){const x=s.x||{},p=[];
  if(s.k==='in'){if(x.chars!=null)p.push(t(`${x.chars} Zeichen`,`${x.chars} characters`));if(x.voice)p.push(t('Stimme erkannt','voice recognized'));if(x.pictures)p.push(t(`${x.pictures} Bild(er)`,`${x.pictures} picture(s)`));if(x.attachment)p.push(t('Anhang','attachment'));if(x.stufe)p.push(x.stufe==='vorrang'?t('mit Vorrang','with priority'):t('hinten angestellt','last in line'))}
  else if(s.k==='prep'){if(x.rights)p.push(t('Rechte: ','Rights: ')+x.rights);if(x.allowed!=null)p.push(t(`${x.allowed} Werkzeuge erlaubt`,`${x.allowed} tools allowed`));if(x.locked)p.push(t('gesperrt nach ','locked after ')+(x.locked==='mail'?'Mail':t('Text von außen','outside text')));if(x.history!=null)p.push(t(`Verlauf ${x.history} Nachrichten`,`history ${x.history} messages`))}
  else if(s.k==='weiche'){if(x.offered!=null)p.push(t(`Werkzeuge ${x.offered} von ${x.of??x.offered}`,`tools ${x.offered} of ${x.of??x.offered}`));p.push(x.narrow?t('eingrenzen an','narrowing on'):t('eingrenzen aus','narrowing off'));if(x.must)p.push(t('Pflicht: ','required: ')+x.must);if(x.why)p.push(t('Grund: ','reason: ')+x.why)}
  else if(s.k==='llm'){if(x.tokens)p.push(t(`${x.tokens} Tokens gelesen`,`${x.tokens} tokens read`));if(x.tools)p.push(t(`${x.tools} Werkzeuge angeboten`,`${x.tools} tools offered`));p.push(x.calls?t('ruft: ','calls: ')+x.calls:t('antwortet','answers'));if(x.first!=null)p.push(t('erstes Zeichen nach ','first output after ')+rsec(x.first));if(x.think)p.push(t(`${x.think} Zeichen Denktext`,`${x.think} chars of thinking`))}
  else if(s.k==='tool'){p.push(x.ok===false?t('nicht ok','not ok'):'ok');if(x.chars)p.push(t(`${x.chars} Zeichen Ergebnis`,`${x.chars} chars result`));if(x.outside)p.push(t('Text von außen, nur als Daten','outside text, as data only'));if(x.panel)p.push(t('vom Panel ausgeführt','run by the panel'));if(x.many)p.push(t('zu viele Aufrufe in einer Runde','too many calls in one round'));if(x.locked)p.push(t('war nicht angeboten','was not offered'))}
  else if(s.k==='check'){p.push(x.again?t('ohne Werkzeug geantwortet, neu gefragt','answered without a tool, asked again'):x.held?t(`${x.held} Angabe(n) ohne Quelle zurückgehalten`,`${x.held} claim(s) without a source held back`):t('alles belegt','everything backed'))}
  else if(s.k==='tts'){p.push(t(`${x.pieces||0} Stück(e) · ${x.chars||0} Zeichen`,`${x.pieces||0} piece(s) · ${x.chars||0} chars`));if(x.behind)p.push(t(`${x.behind}× Ton gestockt`,`sound stalled ${x.behind}×`));if(x.waited_ms)p.push(t('wartete ','waited ')+rsec(x.waited_ms));if(x.overtook)p.push(t(`überholte ${x.overtook} wartende`,`overtook ${x.overtook} waiting`))}
  else if(s.k==='err')p.push(t('vorzeitig beendet, z. B. ins Wort gefallen oder Seite geschlossen','ended early, e.g. barge-in or page closed'));
  return p.join(' · ')}
function rtitle(s){return s.k==='prep'?t('Panel-Vorbereitung','Panel preparation'):s.k==='weiche'?t('Weiche: ','Switch: ')+s.n.replace(/^Weiche: /,''):s.k==='llm'?s.n.replace(/^Runde/,t('Sprachmodell, Runde','Language model, round')):s.k==='check'?t('Antwort-Prüfung','Answer check'):s.k==='tts'?t('Sprachausgabe','Speech output'):s.k==='err'?t('abgebrochen','aborted'):s.k==='in'?t('Eingang · ','Arrival · ')+s.n:s.n}
function rshares(x){const sum={prep:0,llm:0,tool:0,tts:0};(x.steps||[]).forEach(s=>{const k=s.k==='weiche'?'prep':s.k;if(k in sum)sum[k]+=s.d||0});
  const tot=Object.values(sum).reduce((a,b)=>a+b,0)||1,bar=el('div','rbar'),leg=el('div','rleg');
  [['prep',t('Panel','Panel')],['llm',t('Sprachmodell','Language model')],['tool',t('Werkzeuge','Tools')],['tts',t('Sprachausgabe','Speech output')]].forEach(([k,label])=>{
    if(!sum[k])return;const i=el('i');i.style.background=RK[k][0];i.style.width=(sum[k]/tot*100)+'%';i.title=`${label} ${rsec(sum[k])}`;bar.append(i);
    const s=el('span');const c=el('i');c.style.background=RK[k][0];s.append(c,document.createTextNode(`${label} ${rsec(sum[k])}`));leg.append(s)});
  const box=el('div','rshare');box.append(el('div','rsub',t('Wohin die Zeit ging','Where the time went')),bar,leg);return box}
function rsteps(x){const list=[...(x.steps||[])].map(s=>({...s}));const m=x.marks||{};
  if(m.first!=null)list.push({k:'mark',c:RK.llm[0],n:t('erstes Wort','first word'),a:m.first});
  if(m.sound!=null)list.push({k:'mark',c:RK.tts[0],n:t('erster Ton beim Gerät','first sound at the device'),a:m.sound});
  list.sort((a,b)=>a.a-b.a||(a.k==='mark')-(b.k==='mark'));if(m.end!=null)list.push({k:'mark',c:x.status==='err'?'#dc2626':'#16a34a',n:t('fertig','done'),a:m.end});
  const tl=el('div','rtl');
  for(const s of list){const row=el('div','rst'+(s.k==='mark'?' mark':'')+(s.k==='tool'?' tw':''));row.append(el('span','rat',rsecs(s.a)));
    const ic=el('span','ric',s.k==='mark'?'':RK[s.k][1]);ic.style.background=s.k==='mark'?s.c:RK[s.k][0];row.append(ic);
    const tx=el('div','rtx');const b=el('b','',s.k==='mark'?s.n:rtitle(s));if(s.k==='mark')b.style.color=s.c;tx.append(b);
    if(s.k!=='mark'){const d=rdesc(s);if(d)tx.append(el('div','rd',d))}if(s.k==='tool'&&(s.x||{}).ok===false)row.classList.add('bad');row.append(tx);
    row.append(s.k==='mark'?el('span'):el('span','rdu',s.d||['tool','llm','tts','prep'].includes(s.k)?rsec(s.d||0):'–'));tl.append(row)}
  return tl}
async function rshowLines(x,box){box.replaceChildren(el('div','lempty',t('Lade …','Loading …')));
  try{const d=await (await api('/api/admin/traces/'+encodeURIComponent(x.id))).json();RQ.lines=d.lines||[];RQ.linesFor=x.id;rlinesShow(box)}
  catch(e){box.replaceChildren(el('div','lempty',e.message))}}
function rlinesShow(box){box.replaceChildren();
    const out=el('div','lout rlines');for(const r of RQ.lines){const row=el('div','lrow'+(r.level?' '+r.level:''));row.append(el('span','lt',r.t||''));
      const pre=(r.msg.match(/^([a-z0-9_]+):\s/i)||[])[1],a=LAREA[r.area];const badge=el('span','lbadge',a?a[0]:(pre||'·'));badge.style.setProperty('--c',a?a[1]:'#94a3b8');
      row.append(badge,el('span','lm',pre?r.msg.slice(pre.length+1).trim():r.msg));row.title=r.raw;out.append(row)}
    if(!RQ.lines.length)out.append(el('div','lempty',t('Keine Logzeilen aus dieser Zeit.','No log lines from this time.')));
    box.append(el('div','rsub',t('Logzeilen aus dieser Zeit (gleichzeitige Anfragen können dazwischen stehen)','Log lines from this time (requests at the same moment may show too)')),out)}
function rdetail(x){const box=el('div','rdet');
  if(PHONE.matches){const back=el('button','rback',t('‹ Anfragen','‹ Requests'));back.type='button';back.onclick=()=>{RQ.sel=null;RQ.lines=null;rrender()};box.append(back)}
  box.append(el('h3','',t(`Anfrage von ${x.name} · ${rtime(x)}`,`Request from ${x.name} · ${rtime(x)}`)));
  const rounds=(x.steps||[]).filter(s=>s.k==='llm').length,tools=(x.steps||[]).filter(s=>s.k==='tool').length,m=x.marks||{};
  const sub=el('div','rsub');sub.append(document.createTextNode((x.device?x.device+' · ':'')+(RCLIENT[x.client]||x.client)+' · '+t('Absicht ','intent ')));sub.append(rpill(x.intent||'–','int'));
  sub.append(document.createTextNode(' · '+t(`${rounds} Runde(n) · ${tools} Werkzeug(e)`,`${rounds} round(s) · ${tools} tool(s)`)+(m.sound!=null?' · '+t('erster Ton ','first sound ')+rsecs(m.sound):'')+' · '+t('fertig ','done ')+rsecs(m.end||0)));box.append(sub);
  if((x.errors||[]).length)box.append(el('div','lasterr',t('Fehler: ','Errors: ')+x.errors.join(', ')));
  const bar=el('div','lbar');const lb=el('button','b',t('Zugehörige Logzeilen','Related log lines'));lb.type='button';const cp=el('button','b',t('Kopieren für Thread','Copy for thread'));cp.type='button';
  cp.onclick=()=>copyString(rcopyText(),cp);bar.append(lb,cp);box.append(bar);
  box.append(el('div','rnote',t('🔒 Ohne Frage- und Antworttext: nur Wege, Werkzeugnamen, Zahlen und Zeiten.','🔒 Without question or answer text: only ways, tool names, numbers and times.')+(x.named?'':' '+t('Name nur, wenn das Profil es erlaubt.','Name only when the profile allows it.'))));
  box.append(rshares(x),rsteps(x));const lines=el('div','rlinesbox');box.append(lines);lb.onclick=()=>rshowLines(x,lines);if(RQ.lines&&RQ.linesFor===x.id)rlinesShow(lines);return box}
function rfiltered(){const d=RQ.data;if(!d)return [];const q=$('logq').value.trim().toLowerCase();
  return d.items.filter(x=>(!RQ.filter||x.status===RQ.filter)&&(!q||[x.name,x.device,x.client,x.intent,...(x.steps||[]).map(s=>s.n)].join(' ').toLowerCase().includes(q)))}
function rrender(){lshow();const d=RQ.data,box=$('logreq'),chips=$('logchips');if(!d)return;
  chips.replaceChildren();const n=k=>d.items.filter(x=>x.status===k).length;
  [['',t('Alle','All'),'',d.items.length],['err',t('Fehler','Errors'),'#ef4444',n('err')],['slow',t('Langsam','Slow'),'#f59e0b',n('slow')]].forEach(([k,label,c,cnt])=>{
    const b=el('button','lchip'+(RQ.filter===k?' on':''));b.type='button';if(c){b.style.setProperty('--c',c);b.append(el('i'))}b.append(document.createTextNode(label));b.append(el('b','',String(cnt)));
    b.setAttribute('aria-pressed',RQ.filter===k?'true':'false');b.onclick=()=>{RQ.filter=k;rrender()};chips.append(b)});
  const items=rfiltered(),sel=d.items.find(x=>x.id===RQ.sel);box.replaceChildren();box.classList.toggle('one',!!(PHONE.matches&&sel));
  if(!(PHONE.matches&&sel))box.append(rlist(items));if(sel)box.append(rdetail(sel));
  $('loghead').textContent=t('Anfragen','Requests')+(d.on?'':' · '+t('Aufzeichnung aus','recording off'));
  $('logcount').textContent=t(`${items.length} von ${d.items.length} · höchstens ${d.keep_hours} h`,`${items.length} of ${d.items.length} · at most ${d.keep_hours} h`)}
function rcopyText(){const x=RQ.data&&RQ.data.items.find(y=>y.id===RQ.sel);if(!x)return '';const m=x.marks||{};
  const head=`${$('ver').textContent} · Anfrage ${x.id} · ${rtime(x)} · ${RCLIENT[x.client]||x.client} · ${x.intent||'-'}`+(m.sound!=null?` · erster Ton ${rsecs(m.sound)}`:'')+` · fertig ${rsecs(m.end||0)} · ${x.errors.length?x.errors.join(', '):x.status}`;
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
$('loglive').onclick=()=>{LG.live=!LG.live;lsave();try{localStorage.setItem('logfollow',LG.live?'1':'0')}catch{}lshow();if(LG.live)loadLogs().catch(()=>{})};
$('logcopy').onclick=()=>copyString(LG.tab==='req'?rcopyText():lcopyText(),$('logcopy'));
const _ll=loadLogs;window.loadLogs=async()=>{await _ll();loadVerbose()};
// live: diagnosis every 10 s, service logs every 3 s; pauses while scrolled up or text is selected
setInterval(()=>{if(!LG.live||!$('logs').classList.contains('on')||document.hidden)return;
  const out=$('logout');if(out.scrollTop+out.clientHeight<out.scrollHeight-30||String(window.getSelection()||''))return;
  if(Date.now()-LAT<(LG.tab==='svc'?3000:10000))return;_ll().catch(()=>{})},1000);
lshow();
