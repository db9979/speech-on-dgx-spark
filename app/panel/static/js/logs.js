// Zustand → Logs (V01.0.212, "Überblick zuerst"): tiles per area, the newest error with a fixed hint, filter
// buttons, a tidy list (time, area, message; errors red, repeats ×n, pauses), search in the browser only,
// live reload, copy for a thread, and the per-area detail switches. Lines are built with textContent only.
const LAREA={chat:[t('Gespräch','Conversation'),'#6366f1'],search:[t('Websuche','Web search'),'#0ea5e9'],weiche:[t('Weiche','Router'),'#8b5cf6'],
  ha:['Home Assistant','#f59e0b'],room:[t('Raum','Room'),'#10b981'],esp32:[t('Lautsprecher','Speakers'),'#14b8a6'],telegram:['Telegram','#3b82f6'],mail:['Mail','#64748b']};
const LV_AREAS={room:t('Raum-Modus','Room mode'),esp32:t('Lautsprecher','Speakers'),ha:'Home Assistant',chat:t('Gespräch','Conversation')};
// display only: the same fixed words as the panel uses for the diagnosis tab, for the plain service logs
const LERR=/error|exception|traceback|failed|broke|refused|timeout|timed out|fehler|not reachable/i,LWARN=/\b(warn\w*|stalled|behind|ignored|asked again|retry|slow)\b/i;
const LG={tab:'diag',min:60,lines:100,f:['room','esp32'],live:true,svc:'asr'};
try{Object.assign(LG,JSON.parse(localStorage.getItem('logview')||'{}'))}catch{}
try{if(localStorage.getItem('logfollow')==='0')LG.live=false}catch{}
let LDATA=null,LROWS=[],LAT=0;
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
  const tab=LG.tab;let rows=[],head='';LAT=Date.now();
  if(tab==='diag'||tab==='update'){
    const f=tab==='update'?'update':LG.f.join(',');
    const d=await (await api(`/api/logfilter?format=json&f=${encodeURIComponent(f)}&minutes=${LG.min}&lines=${LG.lines}`)).json();
    if(tab!==LG.tab)return;LDATA=tab==='diag'?d:null;rows=d.rows;head=d.head}
  else if(tab==='svc'){const txt=await (await api(`/api/logs/${encodeURIComponent(LG.svc)}?lines=${LG.lines}`)).text();
    if(tab!==LG.tab)return;rows=txt.split('\n').filter(x=>x.trim()&&!x.startsWith('-- ')).map(lparse);LDATA=null;head=`# ${LG.svc} · ${rows.length} Zeilen`}
  else{rows=(await auditRows()).slice(-LG.lines);if(tab!==LG.tab)return;LDATA=null;head=`# ${t('Änderungsprotokoll','Change log')} · ${rows.length}`}
  LROWS=rows;LROWS.head=head;lrender()}
function lshow(){
  document.querySelectorAll('#logtabs button').forEach(b=>b.classList.toggle('on',b.dataset.lt===LG.tab));
  document.querySelectorAll('#logmin button').forEach(b=>b.classList.toggle('on',+b.dataset.v===LG.min));
  const diag=LG.tab==='diag';$('logmin').hidden=!(diag||LG.tab==='update');$('logsum').hidden=$('logchips').hidden=!diag;
  if(!diag)$('lasterr').hidden=true;$('logsvcbar').hidden=LG.tab!=='svc';$('logsvc').value=LG.svc;$('loglines').value=String(LG.lines);
  $('loglive').classList.toggle('on',LG.live);$('loglive').setAttribute('aria-pressed',LG.live?'true':'false')}
function ltile(key,label,color,count,spark,sub){
  const b=el('button','ltile'+(key==='errors'?' err':'')+(LG.f.length===1&&LG.f[0]===key?' on':''));b.type='button';b.style.setProperty('--c',color);
  b.append(el('span','',label),el('b','',String(count||0)));
  if(spark){const s=el('div','lspark');const top=Math.max(1,...spark);spark.forEach(v=>{const i=el('i');i.style.height=(3+Math.round(v/top*22))+'px';s.append(i)});b.append(s)}
  if(sub)b.append(el('div','lsub',sub));
  b.onclick=()=>{LG.f=[key];lsave();loadLogs().catch(()=>{})};return b}
function lrender(){
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
  const name={diag:LG.f.length?LG.f.map(k=>k==='errors'?t('Fehler','errors'):(LAREA[k]||[k])[0]).join(' + '):t('Alles','Everything'),svc:LG.svc,update:'Update',audit:t('Änderungen','Changes')}[LG.tab];
  const span={10:t('letzte 10 min','last 10 min'),60:t('letzte Stunde','last hour'),120:t('letzte 2 Stunden','last 2 hours'),720:t('letzte 12 Stunden','last 12 hours'),1440:t('letzte 24 Stunden','last 24 hours')}[LG.min];
  $('loghead').textContent=name+(LG.tab==='diag'||LG.tab==='update'?' · '+span:'');
  $('logcount').textContent=q?t(`${rows.length} Treffer`,`${rows.length} hits`):(d?t(`${rows.length} von ${d.found} Zeilen`,`${rows.length} of ${d.found} lines`):t(`${rows.length} Zeilen`,`${rows.length} lines`));
  if(stick||!out.dataset.seen){out.scrollTop=1e9;out.dataset.seen='1'}}
function lcopyText(){const q=$('logq').value.trim().toLowerCase();const rows=q?LROWS.filter(r=>(r.msg).toLowerCase().includes(q)):LROWS;
  return `${$('ver').textContent} · ${LROWS.head||''}${q?' · Suche: '+q:''}\n\`\`\`\n${rows.map(r=>r.raw).join('\n')}\n\`\`\``}
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
$('logcopy').onclick=()=>copyString(lcopyText(),$('logcopy'));
const _ll=loadLogs;window.loadLogs=async()=>{await _ll();loadVerbose()};
// live: diagnosis every 10 s, service logs every 3 s; pauses while scrolled up or text is selected
setInterval(()=>{if(!LG.live||!$('logs').classList.contains('on')||document.hidden)return;
  const out=$('logout');if(out.scrollTop+out.clientHeight<out.scrollHeight-30||String(window.getSelection()||''))return;
  if(Date.now()-LAT<(LG.tab==='svc'?3000:10000))return;_ll().catch(()=>{})},1000);
lshow();
