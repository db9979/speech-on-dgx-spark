// Admin pages: monitoring, settings, tests, voices, logs, guides, system and the update lock.
const btns=(n,st)=>`<button class="b" ${onAttr('act',n,'restart')}>${t('Neustart','Restart')}</button>`+(st==='active'||st==='activating'?`<button class="b" ${onAttr('act',n,'stop')}>${t('Stopp','Stop')}</button>`:`<button class="b" ${onAttr('act',n,'start')}>Start</button>`);
async function act(n,a,btn){btn.disabled=true;try{await api(`/api/service/${n}/${a}`,{method:'POST'})}catch(e){alert(e.message)}btn.disabled=false;refresh()}
window.act=act;ON.act=(b,n,a)=>act(n,a,b);ON.copyPrev=b=>copyString(b.previousElementSibling.textContent,b);

async function refresh(){
  let s;try{s=await (await api('/api/status')).json()}catch(e){$('hdr').textContent=t('Panel nicht erreichbar','Panel not reachable');return}
  const g=s.gpu||{},sy=s.system,H=s.history;
  $('hdr').textContent=(g.name||t('keine GPU','no GPU'))+' · '+new Date(s.time*1000).toLocaleTimeString();
  $('m-gpu').textContent=fmt(g.util,' %');$('m-mem').textContent=fmt(sy.mem_avail_gib,' GiB',1)+' / '+sy.mem_total_gib;
  $('m-temp').textContent=fmt(g.temp,' °C')+' · '+fmt(g.power,' W');$('m-cpu').textContent=fmt(sy.cpu,' %');
  spark($('c-gpu'),H.map(x=>x.gpu),100);spark($('c-mem'),H.map(x=>x.avail),sy.mem_total_gib);spark($('c-temp'),H.map(x=>x.temp),100);spark($('c-cpu'),H.map(x=>x.cpu),100);
  showAlerts(s.alerts);zustand(s);if(typeof loadSecGlance==='function')loadSecGlance();
  $('memnote').innerHTML=sy.mem_avail_gib<12&&!(s.alerts||[]).some(x=>x.kind==='memory')?`<div class="note">${t(`Nur noch ${fmt(sy.mem_avail_gib,' GiB',1)} frei. Unter ~8 GiB beendet DGX OS (earlyoom) Prozesse. Kleinere Modelle wählen oder einen Dienst stoppen.`,`Only ${fmt(sy.mem_avail_gib,' GiB',1)} free. Below ~8 GiB DGX OS (earlyoom) kills processes. Choose smaller models or stop a service.`)}</div>`:'';
  $('svc').innerHTML=Object.entries(s.services).map(([n,v])=>{const h=v.health||{};
    const st=h.status?pill(h.status):'';const err=h.error?`<div class="err">${esc(h.error)}</div>`:(h.last_error?`<div class="err mut">${t('letzter Fehler','last error')}: ${esc(h.last_error.error)}</div>`:'');
    return `<tr><td><b>${n.toUpperCase()}</b><div class="mut">:${v.port}</div></td><td>${pill(v.state)} ${st}${v.enabled?'':` <span class="pill">${t('deaktiviert','disabled')}</span>`}</td>
    <td>${esc(h.model||'')}<div class="mut">${t('geschätzt','estimated')} ~${v.estimate_gib} GiB${h.load_seconds?` · ${t('geladen in','loaded in')} ${h.load_seconds}s`:''}</div>${err}</td>
    <td>${h.requests??'–'}${h.failures?` <span class="err">(${h.failures} ${t('Fehler','errors')})</span>`:''}${h.busy?` <span class="pill warn">${t('arbeitet','busy')}</span>`:''}</td>
    <td>${fmt(h.avg_latency_s,' s',2)}</td><td>${fmt(h.avg_ttfa_s??h.avg_ttft_s,' s',2)}${h.streams?`<div class="mut">${h.streams} Streams</div>`:''}</td><td>${fmt(h.avg_rtf,'',2)}</td><td>${fmt(h.torch_cuda_reserved_gb,' GB',1)}</td>
    <td class="row">${btns(n,v.state)}</td></tr>`+(v.engines||[]).map(e=>`<tr><td class="mut" style="padding-left:20px">↳ ${e.name==='tts-design'?'VoiceDesign-Engine':'Engine'}<div>127.0.0.1:${e.port}</div></td><td>${pill(e.state)}</td>
    <td>${esc(e.model)}<div class="mut">${e.kind} · ${t('reserviert','reserves')} ~${e.estimate_gib} GiB</div></td><td colspan=5></td><td class="row">${btns(e.name,e.state)}</td></tr>`).join('')}).join('');
  $('q38none').style.display=s.qwen38.length?'none':'block';
  $('q38').innerHTML=s.qwen38.map(q=>`<tr><td>${esc(q.unit)}</td><td>${pill(q.state)}</td><td>${q.mem_fraction!=null?(q.mem_fraction*100).toFixed(0)+t(' % des Pools',' % of the pool'):'–'}</td></tr>`).join('');
  $('gp').innerHTML=(g.processes||[]).map(p=>`<tr><td>${esc(p.pid)}</td><td>${esc(p.name)}</td><td>${p.mem_mib!=null?fmt(p.mem_mib/1024,' GiB',1):'–'}</td></tr>`).join('')||'<tr><td class="mut" colspan=3>–</td></tr>';
}

// Zustand (design „Klar“, V01.0.146): one sentence on top (all fine / what is wrong) and "Braucht dich" with
// what waits for the admin, each with a button to the place; the dot next to "Zustand" in the menus follows it.
// Built only from what the page already fetched (services, alerts, memory, update, unsaved settings pages).
const SVCNAME={asr:t('Spracherkennung','Speech recognition'),tts:t('Sprachausgabe','Speech output'),wyoming:'Wyoming'};
let ZLAST=null;
function zustand(s){if(s)ZLAST=s;s=ZLAST;if(!s)return;
  const need=[],bad=[],sy=s.system||{};
  for(const [n,v] of Object.entries(s.services||{})){const h=v.health||{},name=SVCNAME[n]||n.toUpperCase();
    if(['failed','error'].includes(v.state)||h.error)bad.push(name);
    else if(v.enabled&&['inactive','deactivating'].includes(v.state))need.push({lvl:'bad',text:t(`${name} ist aus.`,`${name} is off.`),go:'svc',btn:t('Ansehen','View')})}
  for(const n of bad)need.push({lvl:'bad',text:t(`${n} meldet einen Fehler.`,`${n} reports an error.`),go:'svc',btn:t('Ansehen','View')});
  const u=window.UPD;if(u&&u.behind&&u.behind!==0)need.push({lvl:'warn',text:t('Update bereit','Update ready')+(u.version?': '+u.version:'')+'.',go:'sys',btn:t('Zum Update','To the update')});
  if(typeof SECNEED!=='undefined')need.push(...SECNEED);   // red points of "Sicherheit auf einen Blick" (secglance.js)
  const dirty=[...document.querySelectorAll('.pane.dirty')].map(p=>{const b=document.querySelector(`#cfgnav button[data-p="${p.id.slice(5)}"]`);return b?b.firstChild.nodeValue.trim():p.id});
  if(dirty.length)need.push({lvl:'warn',text:t(`Nicht gespeichert: ${dirty.join(', ')}.`,`Not saved: ${dirty.join(', ')}.`),go:'cfg',btn:t('Öffnen','Open')});
  // running = systemd says active or the service itself answers; neither = no answer (counts as "needs you")
  const ok=([,v])=>v.state==='active'||['ready','ok'].includes((v.health||{}).status),nm=([n])=>SVCNAME[n]||n.toUpperCase();
  const all=Object.entries(s.services||{}).filter(e=>!bad.includes(nm(e))),run=all.filter(ok).map(nm),unk=all.filter(e=>!ok(e)&&e[1].enabled!==false).map(nm);
  const low=sy.mem_avail_gib!=null&&sy.mem_avail_gib<12;
  const al=s.alerts||[],lvl=bad.length||need.some(x=>x.lvl==='bad')||al.some(x=>x.level==='bad')?'bad':need.length||unk.length||low||al.length?'warn':'ok';
  $('ztitle').textContent=lvl==='ok'?t('Alles läuft.','Everything is running.'):lvl==='bad'?t('Etwas läuft nicht.','Something is not running.'):!run.length&&unk.length?t('Die Dienste melden sich nicht.','The services do not answer.'):t('Läuft, aber etwas braucht dich.','Running, but something needs you.');
  $('ztext').textContent=(bad.length?t('Fehler: ','Errors: ')+bad.join(', ')+'. ':'')+(run.length?run.join(t(' und ',' and '))+(run.length>1?t(' laufen. ',' are running. '):t(' läuft. ',' is running. ')):'')+(unk.length?t('Ohne Rückmeldung: ','No answer from: ')+unk.join(', ')+'. ':'')
    +(sy.mem_avail_gib!=null?t(`${fmt(sy.mem_avail_gib,' GiB',1)} Speicher frei`,`${fmt(sy.mem_avail_gib,' GiB',1)} memory free`)+(low?t(' (wenig)',' (low)'):'')+'.':'')+(al.length?' '+t('Hinweise stehen oben.','Notes are shown above.'):'');
  zCards(s);$('zhead').dataset.lvl=lvl;$('zicon').textContent=lvl==='ok'?'✓':'!';
  document.querySelectorAll('.hdot').forEach(d=>d.className='hdot '+lvl);
  $('zneed').hidden=!need.length;const L=$('zlist');L.textContent='';
  for(const x of need){const r=document.createElement('div');r.className='zrow';const sp=document.createElement('span');sp.className='pill '+x.lvl;sp.textContent=x.lvl==='bad'?t('Fehler','Error'):t('Offen','Open');
    const tx=document.createElement('span');tx.textContent=x.text;const b=document.createElement('button');b.type='button';b.className='b';b.textContent=x.btn;
    b.onclick=()=>{if(x.go.startsWith('sec:'))secGo(x.go.slice(4));else if(x.go==='svc')zTech('svc');else if(x.go==='cfg'){goSec('cfg');const d=document.querySelector('.pane.dirty');if(d){const nb=document.querySelector(`#cfgnav button[data-p="${d.id.slice(5)}"]`);if(nb)nb.click()}}else goSec(x.go)};
    r.append(sp,tx,b);L.appendChild(r)}}
window.zustand=zustand;
// Zustand in plain words (plan „Bedienung gesamt“ C3, V01.0.286): under the sentence version, last backup and last
// check; four cards Zuhören, Sprechen, Sprachmodell, Speicher (with the 8 GiB line below which DGX OS ends
// processes); a "Heute" line (answers, first sound, speakers online, background work that waited for speech). The
// service table, GPU and qwen38 stay complete under "Technische Details". From /api/status (admin.glance).
const zAgo=s=>{if(!s)return t('noch nie','never');const m=Math.round((Date.now()/1e3-s)/60);return m<1?t('gerade eben','just now'):m<90?(L==='en'?m+' min ago':'vor '+m+' Min.'):m<2880?(L==='en'?Math.round(m/60)+' h ago':'vor '+Math.round(m/60)+' Std.'):(L==='en'?Math.round(m/1440)+' days ago':'vor '+Math.round(m/1440)+' Tagen')};
function zTech(id){const d=$('ztech');d.open=true;const el=id&&$(id);(el?el.closest('.card'):d).scrollIntoView({behavior:'smooth',block:'start'})}
function zCard(lvl,name,big,small,go){const b=document.createElement('button');b.type='button';b.className='zcard';b.dataset.lvl=lvl;
  const k=document.createElement('span');k.className='zk';k.textContent=name;const v=document.createElement('b');v.textContent=big;b.append(k,v);
  if(small){const m=document.createElement('small');m.textContent=small;b.appendChild(m)}if(go)b.onclick=go;return b}
function zSvc(v){if(!v)return['',t('nicht eingerichtet','not set up')];const h=v.health||{};
  if(['failed','error'].includes(v.state)||h.error)return['bad',t('Fehler','Error')];
  if(v.state==='active'||['ready','ok'].includes(h.status))return['ok',h.busy?t('arbeitet','working'):t('läuft','running')];
  if(v.enabled===false)return['',t('ausgeschaltet','switched off')];
  return v.state==='activating'?['warn',t('startet','starting')]:['inactive','deactivating'].includes(v.state)?['bad',t('aus','off')]:['warn',t('keine Antwort','no answer')]}
function zCards(s){const box=$('zcards');if(!box)return;const g=s.glance||{},sv=s.services||{},sy=s.system||{};box.textContent='';
  const short=m=>String(m||'').split('/').pop();
  const a=sv.asr,ah=(a&&a.health)||{},[al,at]=zSvc(a);
  box.appendChild(zCard(al,t('Zuhören','Listening'),at,[short(ah.model),ah.avg_latency_s!=null?t('Ø ','avg ')+fmt(ah.avg_latency_s,' s',1):''].filter(Boolean).join(' · '),()=>zTech('svc')));
  const p=sv.tts,ph=(p&&p.health)||{},[pl,pt]=zSvc(p),ft=ph.avg_ttfa_s??ph.avg_ttft_s;
  box.appendChild(zCard(pl,t('Sprechen','Speaking'),pt,[short(ph.model),ft!=null?t('erster Ton Ø ','first sound avg ')+fmt(ft,' s',1):''].filter(Boolean).join(' · '),()=>zTech('svc')));
  const c=g.check||{};
  box.appendChild(zCard(c.llm===true?'ok':c.llm===false?'bad':'',t('Sprachmodell','Language model'),c.llm===true?t('antwortet','answers'):c.llm===false?t('antwortet nicht','does not answer'):t('noch nicht geprüft','not checked yet'),
    c.time?t('geprüft ','checked ')+zAgo(c.time)+(c.seconds!=null?' · '+fmt(c.seconds,' s',1):''):t('Prüfen startet die Funktionsprüfung','Prüfen runs the check'),()=>goSec('test')));
  const free=sy.mem_avail_gib,tot=sy.mem_total_gib,ml=free==null?'':free<8?'bad':free<12?'warn':'ok';
  const mc=zCard(ml,t('Speicher','Memory'),free==null?'–':fmt(free,' GiB',1)+t(' frei',' free'),t('Grenze 8 GiB: darunter beendet DGX OS Prozesse','Limit 8 GiB: below it DGX OS ends processes'),()=>zTech('c-mem'));
  if(free!=null&&tot){const bar=document.createElement('span');bar.className='zbar';const f=document.createElement('i');f.style.width=Math.max(2,Math.min(100,Math.round(100*free/tot)))+'%';
    const line=document.createElement('em');line.style.left=Math.min(100,Math.round(100*8/tot))+'%';bar.append(f,line);mc.appendChild(bar)}
  box.appendChild(mc);
  $('zmeta').textContent=[g.version,t('Sicherung ','Backup ')+zAgo(g.backup),c.time?t('Prüfung ','Check ')+zAgo(c.time):''].filter(Boolean).join(' · ');
  const bg=g.background||{},td=[];
  td.push(g.answers?(L==='en'?g.answers+' answers':g.answers+' Antworten')+(g.first_sound!=null?t(' (erster Ton im Mittel ',' (first sound median ')+fmt(g.first_sound,' s',1)+')':''):t('noch keine Antwort','no answer yet'));
  if(g.speakers)td.push(t('Lautsprecher ','Speakers ')+g.speakers.online+t(' von ',' of ')+g.speakers.known+t(' online',' online'));
  if(bg.held)td.push(t('Hintergrund hat ','Background waited ')+bg.held+t('-mal auf Sprache gewartet',' times for speech'));
  const tb=$('ztoday');tb.hidden=false;tb.textContent='';const h=document.createElement('b');h.textContent=t('Heute (24 Std.): ','Today (24 h): ');tb.append(h,td.join(' · '))}
// Zustand → "Hört gerade zu" (roomlive.py): every device in room mode, of every profile, with Beenden and
// "Alle beenden" (e.g. when guests come). Only where and until when, never what was heard.
async function zRooms(){const box=$('zroom');if(!box||document.hidden)return;let d={rooms:[],waiting:[]};
  try{const r=await fetch('/api/admin/rooms',{cache:'no-store'});if(!r.ok)return;d=await r.json()}catch{return}
  const all=d.rooms.concat(d.waiting.map(w=>Object.assign({wait:true},w)));box.hidden=!all.length;
  const hm=ms=>new Date(ms).toLocaleTimeString(L==='en'?'en-GB':'de-DE',{hour:'2-digit',minute:'2-digit'});
  const L2=$('zrooms');L2.textContent='';
  for(const x of all){const r=document.createElement('div');r.className='zrow';const sp=document.createElement('span');sp.className='pill ok';sp.textContent=x.wait?t('wartet','waiting'):t('bis ','until ')+hm(x.until);
    const tx=document.createElement('span');const b1=document.createElement('b');b1.textContent=x.profile+' · '+x.name;tx.append(b1,' '+(x.wait?t('Lautsprecher, startet beim nächsten Weckwort','speaker, starts at the next wake word'):(x.kind==='speaker'?t('Lautsprecher','speaker'):t('Browser','browser'))+' · '+t('seit ','since ')+hm(x.since)));
    const b=document.createElement('button');b.type='button';b.className='b';b.textContent=x.wait?t('Nicht starten','Do not start'):t('Beenden','Stop');
    b.onclick=async()=>{try{await api('/api/admin/rooms/end',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({key:x.key})})}catch{}zRooms()};
    r.append(sp,tx,b);L2.appendChild(r)}}
$('zroomall').onclick=async()=>{if(!confirm(t('Raum-Modus an allen Geräten beenden?','End room mode on every device?')))return;
  try{await api('/api/admin/rooms/end',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({all:true})})}catch{}zRooms()};

// Zustand → "Eigene Dokumente" (wissen.py): meaning model state and memory, pages waiting for the language
// model, pieces with a meaning vector. Counts over all profiles only; shown while a switch is on.
async function zDocs(){const box=$('zdocs');if(!box||document.hidden)return;let d={on:false};
  try{const r=await fetch('/api/admin/wissen',{cache:'no-store'});if(!r.ok)return;d=await r.json()}catch{return}
  box.hidden=!d.on;if(!d.on)return;const L2=$('zdoclist');L2.textContent='';
  const ago=s=>{if(!s)return t('noch nie','never');const m=Math.round((Date.now()/1e3-s)/60);return m<1?t('gerade eben','just now'):m<90?(L==='en'?m+' min ago':'vor '+m+' Min.'):(L==='en'?Math.round(m/60)+' h ago':'vor '+Math.round(m/60)+' Std.')};
  const row=(cls,pill,title,text)=>{const r=document.createElement('div');r.className='zrow';const sp=document.createElement('span');sp.className='pill '+cls;sp.textContent=pill;
    const tx=document.createElement('span');const b=document.createElement('b');b.textContent=title;tx.append(b,' '+text);r.append(sp,tx);L2.appendChild(r)};
  if(d.semantic&&d.model){const m=d.model;const st={ready:['ok',t('läuft','running')],starting:['warn',t('startet','starting')],waiting:['warn',t('wartet','waiting')],error:['bad',t('Fehler','error')],off:['',t('aus','off')]}[m.state]||['',m.state];
    let tx=m.state==='ready'?(m.mib?m.mib+' MiB '+t('Arbeitsspeicher','memory')+' · ':'')+t('stoppt nach ','stops after ')+m.stop_min+t(' Min. ohne Arbeit',' min idle')
      :m.state==='waiting'?t('braucht ','needs ')+m.need_gib+t(' GiB freien Arbeitsspeicher',' GiB free memory')
      :m.state==='error'?(m.error||''):m.state==='starting'?t('lädt das Modell (beim ersten Mal von Hugging Face)','loading the model (from Hugging Face the first time)')
      :t('startet, wenn etwas zu tun ist','starts when there is work');
    const v=d.vectors;tx+=' · '+v[0]+'/'+v[1]+t(' Stücke mit Bedeutung',' pieces with meaning');
    row(st[0],st[1],t('Bedeutungssuche (CPU-Modell)','Meaning search (CPU model)'),tx)}
  if(d.pictures){row(d.waiting?'warn':'ok',d.waiting?d.waiting+t(' Seiten',' pages'):t('nichts offen','nothing open'),t('Bilder und Scans lesen','Read pictures and scans'),
    d.today+t(' heute gelesen (höchstens ',' read today (at most ')+d.day_pages+t(' je Profil)',' per profile)')+' · '+t('zuletzt ','last ')+ago(d.last.read)+(d.waiting&&!d.quiet?' · '+t('wartet auf eine ruhige Minute','waits for a quiet minute'):''))}
  for(const x of d.usage||[]){const r=document.createElement('div');r.className='zrow';const pct=Math.min(100,Math.round(100*x.used/(x.quota_mb*1048576)));
    const sp=document.createElement('span');sp.className='pill '+(pct>=90?'warn':'ok');sp.textContent=pct+' %';
    const tx=document.createElement('span');const b1=document.createElement('b');b1.textContent=x.who;
    tx.append(b1,' '+(x.used<1048576?Math.max(1,Math.round(x.used/1024))+' KB':(x.used/1048576).toFixed(1)+' MB')+t(' von ',' of ')+x.quota_mb+' MB'+(x.own?t(' (eigener Wert)',' (own value)'):''));
    const inp=document.createElement('input');inp.type='number';inp.min=50;inp.max=50000;inp.className='num';inp.style.maxWidth='90px';inp.value=x.quota_mb;inp.title=t('Speicher für Dokumente in MB','Space for documents in MB');
    const b=document.createElement('button');b.type='button';b.className='b';b.textContent=t('Setzen','Set');
    b.onclick=async()=>{const v=inp.value.trim();try{await api('/api/admin/wissen/quota',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({owner:x.owner,mb:v===''||Number(v)===d.default_mb?null:Number(v)})})}catch(e){alert(e.message)}zDocs()};
    r.append(sp,tx,inp,b);L2.appendChild(r)}
  for(const x of d.shared||[]){const r=document.createElement('div');r.className='zrow';const sp=document.createElement('span');sp.className='pill ok';sp.textContent=t('für alle','shared');
    const tx=document.createElement('span');const b1=document.createElement('b');b1.textContent=x.name;tx.append(b1,' '+t('von ','from ')+x.who);
    const b=document.createElement('button');b.type='button';b.className='b';b.textContent=t('Zurücknehmen','Take back');
    b.onclick=async()=>{if(!confirm(t('„'+x.name+'“ nicht mehr für alle freigeben?','Stop sharing "'+x.name+'" with everyone?')))return;
      try{await api('/api/admin/wissen/unshare',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({owner:x.owner,id:x.id})})}catch{}zDocs()};
    r.append(sp,tx,b);L2.appendChild(r)}}
let CFG=null;
async function loadLangs(){const l=await (await api('/api/languages')).json();document.querySelectorAll('select.langs').forEach(s=>s.innerHTML=l.map(x=>`<option>${x}</option>`).join(''))}
async function instrHint(sel){if(!CFG)try{CFG=await (await api('/api/config')).json()}catch{return}const m=(sel?$('tts.model').value:CFG.tts.model)||'';const small=/0\.6B/i.test(m);
  document.querySelectorAll('.instrhint').forEach(e=>e.innerHTML=small?t('<b>Hinweis:</b> '+m.split('/').pop()+' wertet Anweisungen nicht aus (laut Qwen nur die 1.7B-Modelle). Für Stilsteuerung Qwen3-TTS-12Hz-1.7B-CustomVoice wählen; braucht etwa 2 bis 3 GiB mehr Speicher.','<b>Note:</b> '+m.split('/').pop()+' ignores instructions (per Qwen only the 1.7B models follow them). For style control choose Qwen3-TTS-12Hz-1.7B-CustomVoice; it needs about 2 to 3 GiB more memory.'):t('Beschreibung in normaler Sprache, z. B. Tonfall, Tempo, Emotion, Rolle. Deutsch oder Englisch.','Plain-language description, e.g. tone, pace, emotion, role. German or English.'))}
// Standardstimme (V01.0.252): a list that fits the chosen model instead of free text. The running model names its voices;
// a model only picked (not saved yet) offers the cloned recordings (Base) or Qwen's fixed speakers (CustomVoice);
// VoiceDesign has no speakers. A saved name missing from the list stays as its own entry, so it is never lost.
const QWEN_SPEAKERS=['aiden','dylan','eric','ono_anna','ryan','serena','sohee','uncle_fu','vivian'];
const ttsKind=m=>/-Base$/i.test(m)?'base':/VoiceDesign/i.test(m)?'voice_design':'custom_voice';
async function ttsVoiceOpts(){const sel=$('tts.default_voice');if(!sel||!CFG)return;const m=$('tts.model').value||'',kind=ttsKind(m);
  const cur=sel.value||String(CFG.tts.default_voice||'');let vs=[];
  try{if(m===CFG.tts.model)vs=(await (await api('/api/tts/voices')).json()).voices||[];
    if(!vs.length&&kind==='base')vs=await (await api('/api/clone-voices')).json()}catch{}
  if(!vs.length&&kind==='custom_voice')vs=QWEN_SPEAKERS;
  if(kind==='voice_design')vs=[];
  vs=[...new Set(vs.filter(x=>typeof x==='string'&&x))];
  const hit=vs.find(x=>x.toLowerCase()===cur.toLowerCase());
  sel.innerHTML=(cur&&!hit?`<option value="${esc(cur)}">${esc(cur)} ${esc(t('(nicht in der Liste)','(not in the list)'))}</option>`:'')+
    vs.map(x=>`<option value="${esc(x)}">${esc(x)}</option>`).join('')+(!cur&&!vs.length?`<option value="">${t('(keine)','(none)')}</option>`:'');
  sel.value=hit||cur;sel.disabled=kind==='voice_design';
  $('ttsvoicehint').textContent=kind==='voice_design'?t('VoiceDesign hat keine Sprecher; die Stimme kommt aus dem Sprechstil.','VoiceDesign has no speakers; the voice comes from the speaking style.')
    :kind==='base'?(vs.length?t('Eine eigene Stimme aus „Stimmen“.','One of your own voices from "Voices".'):t('Noch keine eigenen Stimmen; unter „Stimmen“ anlegen.','No own voices yet; add them under "Voices".'))
    :t('Einer der festen Sprecher des Modells.','One of the model\'s fixed speakers.')}
$('tts.model').addEventListener('change',ttsVoiceOpts);
async function loadCfg(){CFG=await (await api('/api/config')).json();
  const vo=CFG.tts.backend==='vllm-omni';$('ttsbackend').textContent=CFG.tts.backend;
  $('ttsbackendnote').textContent=vo?t('(gestreamte Ausgabe)','(streamed output)'):t('(ohne Streaming; umstellen mit sudo ./install.sh --tts-backend vllm-omni)','(no streaming; switch with sudo ./install.sh --tts-backend vllm-omni)');
  $('enginecfg').style.display=vo?'block':'none';$('ttsdtype').style.display=vo?'none':'block';
  const av=CFG.asr.backend==='vllm';$('asrbackend').textContent=CFG.asr.backend;
  $('asrbackendnote').textContent=av?t('(viele Anfragen gleichzeitig, gestreamter Text)','(many concurrent requests, streamed text)'):t('(eine Anfrage nach der anderen; umstellen mit sudo ./install.sh --asr-backend vllm)','(one request at a time; switch with sudo ./install.sh --asr-backend vllm)');
  $('asrengine').style.display=av?'block':'none';$('asrtf').style.display=av?'none':'block';
  for(const[sec,o]of Object.entries(CFG))for(const[k,v]of Object.entries(o)){const el=$(sec+'.'+k);if(!el)continue;
    if(el.type==='checkbox')el.checked=v;else{if(el.tagName==='SELECT'&&![...el.options].some(o=>o.value==v))el.add(new Option(v));el.value=Array.isArray(v)?v.join(', '):v}};instrHint();ttsVoiceOpts();try{kxChips()}catch{};
  getDefaults=await renderSet($('chatdefaults'),{...SDEF,...(CFG.chat.defaults||{})},null);
  asrRec();cfgDeps();if(typeof guidesCount==='function')guidesCount();if(typeof tgAdmin==='function')tgAdmin();visionLoad();if(typeof apnsAdmin==='function')apnsAdmin();if(typeof iupdAdmin==='function')iupdAdmin();if(typeof coadmAdmin==='function')coadmAdmin();if(typeof espAdmin==='function')espAdmin();if(typeof agentAdmin==='function')agentAdmin();document.querySelectorAll('.pane').forEach(p=>markDirty(p,false));document.querySelectorAll('.savemsg').forEach(m=>m.textContent='');glance();glanceLoad();llmModels()}
let getDefaults=null;
// Sprachmodell (V01.0.292): a choice of the models the configured server reports (/api/admin/llm-models). The text
// field chat.llm_model stays what is saved; the list only fills it. Without a list (server down, no address) or
// with „Anderes eingeben …“ the text field shows, so a name can always be typed by hand.
const LLM_OTHER=' other';  // a space never passes the server's name check
async function llmModels(fresh){const sel=$('llmmodelsel'),inp=$('chat.llm_model'),hint=$('llmmodelhint');if(!sel)return;
  let r;try{r=await (await api('/api/admin/llm-models'+(fresh?'?fresh=1':''))).json()}catch{r={models:[],error:t('Liste nicht abrufbar.','List not available.')}}
  const ms=r.models||[],cur=inp.value.trim();
  if(!ms.length){sel.hidden=true;inp.hidden=false;hint.textContent=(r.error||t('Der Server meldet keine Modelle.','The server reports no models.'))+' '+t('Leer = das erste, das der Server meldet.','Empty = the first one the server reports.');return}
  const known=!cur||ms.includes(cur);
  sel.innerHTML=`<option value="">${esc(t('Automatisch','Automatic')+' ('+ms[0]+')')}</option>`+ms.map(m=>`<option value="${esc(m)}">${esc(m)}</option>`).join('')+
    (known?'':`<option value="${esc(cur)}">${esc(cur+' '+t('(meldet der Server nicht)','(not reported by the server)'))}</option>`)+`<option value="${LLM_OTHER}">${esc(t('Anderes eingeben …','Type another …'))}</option>`;
  sel.value=cur;sel.hidden=false;inp.hidden=true;
  hint.textContent=ms.length===1?t('Der Server meldet ein Modell.','The server reports one model.'):t(`Der Server meldet ${ms.length} Modelle.`,`The server reports ${ms.length} models.`)}
$('llmmodelsel').addEventListener('change',()=>{const sel=$('llmmodelsel'),inp=$('chat.llm_model');
  if(sel.value===LLM_OTHER){inp.hidden=false;inp.focus();return}inp.hidden=true;inp.value=sel.value});
$('llmmodelre').onclick=()=>llmModels(true);
// Parakeet has no model choice and no engine: hide those settings while it is chosen.
function asrRec(){const qw=$('asr.recognizer').value!=='parakeet';$('asrqwen').style.display=qw?'':'none';
  $('asrengine').style.display=qw&&CFG.asr.backend==='vllm'?'block':'none'}
$('asr.recognizer').addEventListener('change',asrRec);
// Configuration in sub-tabs; each one saves only its own fields (the server restarts only
// the services whose settings changed).
const cfgPane=p=>{document.querySelectorAll('#cfgnav button').forEach(b=>b.classList.toggle('on',b.dataset.p===p));
  document.querySelectorAll('.pane').forEach(x=>x.classList.toggle('on',x.id==='pane-'+p));try{localStorage.setItem('cfgpane',p)}catch{}};
// phones: the settings open as a list of pages; a tapped page fills the screen with "back" on top
document.querySelectorAll('#cfgnav button').forEach(b=>b.onclick=()=>{cfgPane(b.dataset.p);if(b.dataset.p==='voices')loadClone();if(b.dataset.p==='upd')loadSys();if(b.dataset.p==='start')glance();if(b.dataset.p==='sec')loadSecGlance(true);document.querySelector('.cfgwrap').classList.add('sub');window.scrollTo(0,0)});
$('cfgback').onclick=()=>{document.querySelector('.cfgwrap').classList.remove('sub');window.scrollTo(0,0)};
// building blocks (V01.0.207): „Mehr“ unfolds the longer help right below its row; the password fields open on
// „Ändern …“; the audio file for a new voice is picked with a normal button that shows the chosen name
document.addEventListener('click',e=>{const b=e.target.closest&&e.target.closest('.mlink');if(!b)return;e.preventDefault();
  const host=b.closest('.setrow,.pintro'),m=host&&host.nextElementSibling;if(m&&m.classList.contains('more')){m.hidden=!m.hidden;b.textContent=m.hidden?t('Mehr','More'):t('Weniger','Less')}});
$('pwopen').onclick=()=>{const x=$('pwbox');x.hidden=!x.hidden;if(!x.hidden)$('pwold').focus()};
$('vfilebtn').onclick=()=>$('vfile').click();
$('vfile').addEventListener('change',()=>{const f=$('vfile').files[0];$('vfilename').textContent=f?f.name:t('wav, mp3, m4a, …','wav, mp3, m4a, …')});
try{const p=localStorage.getItem('cfgpane');if(p&&$('pane-'+p))cfgPane(p)}catch{}
window.goCfg=p=>{if(p==='feat'){goSec('feat');return}goSec('cfg');const b=document.querySelector(`#cfgnav button[data-p="${p}"]`);if(b)b.click()};
// „Auf einen Blick“ (V01.0.207): every settings page with its state in one line, on top what a switched-on feature
// still needs. Phones show the same lines right in the settings menu. Built only from what the page already has
// (the loaded settings, the status, the update check) plus the voice list, the backup list and the admin's second step.
const GL={};
const short=m=>String(m||'').split('/').pop();
async function glanceLoad(){const get=async(u,f)=>{try{GL[f]=await (await api(u)).json()}catch{}};
  await Promise.all([get('/api/clone-voices','voices'),get('/api/backups','bak'),get('/api/mfa','mfa')]);glance()}
function glanceText(p){const c=CFG||{},ch=c.chat||{},svc=((ZLAST||{}).services)||{},run=n=>svc[n]&&(svc[n].state==='active');
  const pill=(cls,txt)=>({cls,txt});
  if(p==='feat'){const it=[...document.querySelectorAll('#pane-feat .fitem')],on=it.filter(x=>{const s=$(x.dataset.sw);return s&&s.checked}).length,need=it.filter(featNeed).length;
    return {txt:t(`${on} von ${it.length} an`,`${on} of ${it.length} on`)+(need?t(` · ${need} brauchen dich`,` · ${need} need you`):''),pill:need?pill('warn',t('braucht dich','needs you')):null}}
  if(p==='talk'){const d=getDefaults?getDefaults():{};const f=$('chat.face');
    return {txt:[t('Freihändig ','Hands-free ')+(d.hands?t('an','on'):t('aus','off')),t('Antwortlänge ','Answer length ')+(($('set_chatdefaults_length')||{}).selectedOptions||[{text:d.length||'–'}])[0].text,f&&f.selectedOptions[0]?f.selectedOptions[0].text:''].filter(Boolean).join(' · ')}}
  if(p==='ai'){let host='';try{host=new URL(ch.llm_url).host}catch{}
    return {txt:(ch.llm_model||t('Modell automatisch','model automatic'))+(host?t(' auf ',' on ')+host:'')+t(' · Temperatur ',' · temperature ')+ch.temperature}}
  if(p==='asr'){const a=c.asr||{};if(!a.enabled)return {txt:t('aus','off'),pill:pill('',t('aus','off'))};
    return {txt:(a.recognizer==='parakeet'?'Parakeet':short(a.model))+t(' · Sprache ',' · language ')+a.default_language,pill:run('asr')?pill('ok',t('läuft','running')):null}}
  if(p==='tts'){const a=c.tts||{};if(!a.enabled)return {txt:t('aus','off'),pill:pill('',t('aus','off'))};
    return {txt:short(a.model).replace('Qwen3-TTS-12Hz-','')+t(' · Stimme ',' · voice ')+(a.default_voice||'–'),pill:run('tts')?pill('ok',t('läuft','running')):null}}
  if(p==='voices'){const n=(GL.voices||[]).length;return {txt:GL.voices?(n?t(`${n} eigene Stimme${n>1?'n':''}`,`${n} own voice${n>1?'s':''}`):t('keine eigenen Stimmen','no own voices')):'…'}}
  if(p==='sec'){const m=GL.mfa;return {txt:(ch.public?t('Assistent ohne Passwort','assistant without password'):t('Assistent nur mit Anmeldung','assistant only after sign-in'))+(m?t(' · Zweiter Schritt ',' · second step ')+(m.on?t('an','on'):t('aus','off')):''),
    pill:m&&!m.on?pill('warn',t('Zweiter Schritt aus','second step off')):null}}
  if(p==='sysc'){const m=c.memory||{},w=c.watch||{};return {txt:t('Speicherschutz ','Memory guard ')+(m.guard?t('an','on'):t('aus','off'))+t(' · Reserve ',' · reserve ')+m.reserve_gib+' GiB'+t(' · Wächter ',' · watchdog ')+(w.watchdog?t('an','on'):t('aus','off'))}}
  if(p==='upd'){const u=window.UPD||{},b=((GL.bak||{}).backups||[])[0];const ready=u.behind&&u.behind!==0;
    return {txt:[SPARK_VER,(ready?t('Update bereit','update ready'):u.behind===0?t('aktuell','up to date'):t('Stand unbekannt','state unknown')),b&&b.created?t('letzte Sicherung ','last backup ')+new Date(b.created*1000).toLocaleString([], {day:'numeric',month:'numeric',hour:'2-digit',minute:'2-digit'}):''].filter(Boolean).join(' · '),
      pill:ready?pill('warn',t('Update bereit','update ready')):u.behind===0?pill('ok',t('aktuell','up to date')):null}}
  return {txt:''}}
function glanceNeed(){return [...document.querySelectorAll('#pane-feat .fitem')].filter(featNeed).map(it=>{
  const nm=it.querySelector('.lbl>b'),name=nm&&nm.firstChild?nm.firstChild.nodeValue.trim():'';
  const empty=[...it.querySelectorAll('[data-req]')].find(x=>!x.value.trim()),lab=empty&&empty.previousElementSibling&&empty.previousElementSibling.tagName==='LABEL'?empty.previousElementSibling.textContent.trim():'';
  const st=it.querySelector('[data-need="1"]'),stx=st?st.textContent.trim():'';
  return {name,why:lab?t(`${lab}: fehlt`,`${lab}: missing`):stx&&stx.length<90?stx:t('Eine Angabe fehlt.','Something is missing.'),sw:it.dataset.sw}})}
function glRow(name,why,pill,go){const r=document.createElement('button');r.type='button';r.className='glrow';
  const l=document.createElement('span');l.className='lbl';const b=document.createElement('b');b.textContent=name;const s=document.createElement('span');s.textContent=why;l.append(b,s);r.appendChild(l);
  if(pill&&pill.txt){const p=document.createElement('span');p.className='pill '+pill.cls;p.textContent=pill.txt;r.appendChild(p)}r.onclick=go;return r}
function glanceNeedBox(){const need=glanceNeed();if(!need.length)return null;const box=document.createElement('div');box.className='glneed';
  need.forEach(n=>box.appendChild(glRow(n.name,n.why,{cls:'warn',txt:t('braucht dich','needs you')},()=>{goCfg('feat');const sw=$(n.sw);if(sw&&typeof featShow==='function'){featShow(sw.closest('.setrow')||sw);setTimeout(()=>sFlash(sw.closest('.setrow')||sw),60)}})));return box}
function glance(){if(!CFG)return;const out=$('glance');out.textContent='';const nb=glanceNeedBox();if(nb)out.appendChild(nb);
  const nav=$('cfgnav');nav.querySelectorAll(':scope>.glneed').forEach(x=>x.remove());const nb2=glanceNeedBox();if(nb2){const sb=nav.querySelector('.sbox');sb?sb.after(nb2):nav.prepend(nb2)}
  [...nav.children].forEach(el=>{if(el.classList.contains('cgrp')){const h=document.createElement('h3');h.className='sec';h.textContent=el.textContent;out.appendChild(h);return}
    const p=el.dataset&&el.dataset.p;if(!p||p==='start')return;const g=glanceText(p),name=el.firstChild.nodeValue.trim();
    out.appendChild(glRow(name,g.txt,g.pill,()=>el.click()));
    let sm=el.querySelector('small.gls');if(!sm){sm=document.createElement('small');sm.className='gls';el.appendChild(sm)}sm.textContent=g.txt})}
window.glance=glance;
// Details of a feature show only while it is on (they sit right below its switch).
function cfgDeps(){const on=id=>{const e=$(id);return !e||e.checked};
  document.querySelectorAll('#pane-cfg [data-show],[data-show]').forEach(x=>x.style.display=on(x.dataset.show)?'':'none');
}
['chat.search','chat.speaker_id','chat.mail'].forEach(id=>$(id).addEventListener('change',cfgDeps));
// every switch with details shows them at once when switched on (not only after saving)
[...new Set([...document.querySelectorAll('[data-show]')].map(x=>x.dataset.show))].forEach(id=>{const e=$(id);if(e&&!['chat.search','chat.speaker_id','chat.mail'].includes(id))e.addEventListener('change',cfgDeps)});
// Wyoming answers only listed addresses: suggest the Home Assistant address when switched on
async function wySuggest(auto){const inp=$('chat.wyoming_allow'),msg=$('wymsg');
  try{const d=await (await api('/api/admin/wyoming/suggest')).json();
    const have=inp.value.split(/[\s,;]+/).filter(Boolean),add=d.ha.map(x=>x.ip).filter(ip=>!have.includes(ip));
    if(add.length){inp.value=have.concat(add).join(', ');inp.dispatchEvent(new Event('input',{bubbles:true}));
      msg.textContent=t('Eingetragen: ','Filled in: ')+d.ha.map(x=>x.ip+' ('+x.host+')').join(', ')+t('. Prüfen, dann Speichern.','. Check it, then save.')}
    else if(!auto)msg.textContent=d.ha.length?t('Die Adresse steht schon drin.','The address is already there.'):t('Keine Home-Assistant-Adresse im Heimnetz gefunden (in keinem Profil eingerichtet, oder nur über einen Reverse-Proxy erreichbar). Trag die Adresse deines Home Assistant von Hand ein, z. B. 192.168.1.20.','No Home Assistant address in the home network found (not set up in any profile, or only reachable through a reverse proxy). Enter your Home Assistant address by hand, e.g. 192.168.1.20.');
    if(d.knocked.length)msg.textContent+=' '+t('Zuletzt abgewiesen: ','Refused lately: ')+d.knocked.join(', ')+t(' (wenn das dein Home Assistant ist, diese Adresse eintragen).',' (if that is your Home Assistant, enter this address).')}
  catch(e){if(!auto)msg.textContent=e.message}}
$('wysuggest').onclick=()=>wySuggest(false);
$('chat.wyoming').addEventListener('change',e=>{if(e.target.checked&&!$('chat.wyoming_allow').value.trim())wySuggest(true)});
const markDirty=(pane,on)=>{const b=document.querySelector(`#cfgnav button[data-p="${pane.id.slice(5)}"]`);if(b)b.classList.toggle('dirty',on);
  pane.classList.toggle('dirty',on);const bar=pane.querySelector('.savebar');if(bar)bar.classList.toggle('dirty',on);
  const n=document.querySelectorAll('.pane.dirty').length,c=$('dirtycnt');c.hidden=!n;c.textContent=n;zustand()};
// unsaved changes: the save bar says so and offers "Verwerfen"; leaving the page or the settings asks first
const dirtyPanes=()=>[...document.querySelectorAll('.pane.dirty')];
const leaveOk=()=>!dirtyPanes().length||confirm(t('Es gibt ungespeicherte Änderungen. Trotzdem verlassen? Sie gehen dann verloren.','There are unsaved changes. Leave anyway? They will be lost.'));
window.addEventListener('beforeunload',e=>{if(dirtyPanes().length){e.preventDefault();e.returnValue=''}});
document.querySelectorAll('.savebar').forEach(bar=>{if(!bar.querySelector('.savebtn'))return;
  const n=document.createElement('span');n.className='unsaved';n.textContent=t('Ungespeicherte Änderungen','Unsaved changes');
  const d=document.createElement('button');d.type='button';d.className='b undo';d.textContent=t('Verwerfen','Discard');
  d.onclick=()=>{if(confirm(t('Änderungen auf dieser Seite verwerfen?','Discard the changes on this page?')))loadCfg()};
  bar.prepend(n);bar.querySelector('.savebtn').after(d)});
// leaving the settings with unsaved changes: ask (capture phase, before the menu switches the page)
document.addEventListener('click',e=>{const b=e.target.closest&&e.target.closest('nav button[data-s],.subnav button');
  if(b&&b.dataset.s!=='cfg'&&document.getElementById('cfg').classList.contains('on')&&!leaveOk()){e.stopImmediatePropagation();e.preventDefault()}},true);
document.querySelectorAll('.pane').forEach(pane=>{if(!pane.querySelector('.savebtn'))return;const f=e=>{if(/^pw/.test(e.target.id)||e.target.closest('[data-nodirty]'))return;markDirty(pane,true)};pane.addEventListener('input',f);pane.addEventListener('change',f)});
document.querySelectorAll('.savebtn').forEach(btn=>btn.onclick=async()=>{const pane=$('pane-'+btn.dataset.p),msg=btn.nextElementSibling;
  const n=JSON.parse(JSON.stringify(CFG));if(getDefaults&&pane.contains($('chatdefaults')))n.chat.defaults=getDefaults();
  for(const[sec,o]of Object.entries(n))for(const k of Object.keys(o)){const el=$(sec+'.'+k);if(!el||!pane.contains(el))continue;
    o[k]=el.type==='checkbox'?el.checked:el.dataset.list?el.value.split(/[\s,;]+/).filter(Boolean):el.type==='number'||el.dataset.num?Number(el.value):el.value}
  if(pane.contains($('chat.wyoming'))&&$('chat.wyoming').checked&&!$('chat.wyoming_allow').value.trim()){
    const m=t('Wyoming braucht die Adresse deines Home Assistant, z. B. 192.168.1.20 (oder „Adresse von Home Assistant übernehmen“).','Wyoming needs your Home Assistant address, e.g. 192.168.1.20 (or "Take the Home Assistant address").');
    $('wymsg').innerHTML=`<span class="err">${esc(m)}</span>`;msg.innerHTML=`<span class="err">${esc(m)}</span>`;$('chat.wyoming_allow').focus();return}
  msg.textContent=t('Speichere…','Saving…');
  try{const r=await (await api('/api/config',{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify(n)})).json();
    if(pane.contains($('chat.face')))setFaceKind(n.chat.face);
    msg.innerHTML=t('Gespeichert.','Saved.')+(r.restarted.length?t(' Neu gestartet: ',' Restarted: ')+r.restarted.join(', ').toUpperCase()+t(' (Modell lädt neu).',' (model reloads).'):'')+(r.stopped&&r.stopped.length?t(' Gestoppt: ',' Stopped: ')+r.stopped.join(', ').toUpperCase()+'.':'')+(r.errors&&r.errors.length?`<div class="err">${esc(r.errors.join('\n'))}</div>`:'')+(r.panel_restart_needed?t(' Panel-Port ändert sich nach: ',' Panel port changes after: ')+'sudo systemctl restart speech-spark-panel':'');CFG=n;markDirty(pane,false);glance()}
  catch(e){msg.innerHTML=`<span class="err">${esc(e.message)}</span>`}});

// the whole prompt as the model gets it (fixed parts marked) and the shipped system prompt
$('promptdef').onclick=async()=>{try{const d=await (await api('/api/admin/prompt')).json();const el=$('chat.system_prompt');
    el.value=d.default;el.dispatchEvent(new Event('input',{bubbles:true}));$('promptmsg').textContent=t('Standard eingesetzt, noch nicht gespeichert.','Default filled in, not saved yet.')}
  catch(e){$('promptmsg').textContent=e.message}};
$('promptshow').onclick=async()=>{const v=$('promptview');if(v.style.display!=='none'){v.style.display='none';return}
  try{const d=await (await api('/api/admin/prompt')).json();
    v.innerHTML=`<div class="fh">${esc(t('So bekommt das Modell den Prompt, in dieser Reihenfolge (gespeicherter Stand). Feste Teile kann keine Einstellung und kein Prompt abschalten.','This is how the model gets the prompt, in this order (saved state). No setting and no prompt can switch off the fixed parts.'))}</div>`
      +d.parts.map(p=>`<div style="margin-top:8px"><b>${esc(p.label)}</b> <span class="pill ${p.fixed?'ok':'warn'}">${p.fixed?esc(t('fest','fixed')):esc(t('änderbar','changeable'))}</span><pre style="white-space:pre-wrap;margin:4px 0 0">${esc(p.text||'–')}</pre></div>`).join('');
    v.style.display=''}
  catch(e){$('promptmsg').textContent=e.message}};
$('asrgo').onclick=async()=>{const f=$('asrfile').files[0];if(!f)return;const fd=new FormData();fd.append('file',f);fd.append('language',$('asrlang').value);
  $('asrmsg').textContent=t('läuft…','running…');$('asrout').style.display='none';
  try{const r=await (await api('/api/test/asr',{method:'POST',body:fd})).json();$('asrmsg').textContent=`${r.processing_s}s ${t('für','for')} ${fmt(r.duration,' s',1)} Audio`;
    $('asrout').textContent=`[${r.language||'auto'}] ${r.text}`;$('asrout').style.display='block'}catch(e){$('asrmsg').innerHTML=`<span class="err">${esc(e.message)}</span>`}};
async function loadVoices(){const v=await (await api('/api/tts/voices')).json(),vs=v.voices||[];   // no list while the TTS loads
  $('ttsvoice').innerHTML=vs.length?vs.map(x=>`<option>${esc(x)}</option>`).join(''):`<option value="">${t('(Standard)','(default)')}</option>`;
  $('ttsvoice').disabled=v.model_kind==='voice_design'}
$('ttsgo').onclick=async()=>{const body={input:$('ttstext').value,voice:$('ttsvoice').value||null,language:$('ttslang').value,instruct:$('ttsinstr').value||null};
  if($('ttstask').value)body.task_type=$('ttstask').value;
  $('ttsmsg').textContent=t('läuft…','running…');$('ttsgo').disabled=true;
  try{if($('ttsstream').checked)await ttsStream(body);else{
    const r=await api('/api/test/tts',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
    const b=await r.blob();$('ttsaudio').src=URL.createObjectURL(b);$('ttsaudio').style.display='block';$('ttsaudio').play();$('ttsmsg').textContent=`${t('fertig nach','done after')} ${r.headers.get('x-processing-seconds')||'?'} s`}}
  catch(e){$('ttsmsg').innerHTML=`<span class="err">${esc(e.message)}</span>`}
  $('ttsgo').disabled=false};
// Plays the SSE stream (base64 PCM 16 bit mono 24 kHz) as it arrives, like a streaming client would.
async function ttsStream(body){const t0=performance.now();const r=await api('/api/test/tts-stream',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
  const AC=window.AudioContext||window.webkitAudioContext;let ctx;try{ctx=new AC({sampleRate:24000})}catch{ctx=new AC()}let at=ctx.currentTime+0.05,first=null,bytes=0,buf='';
  const rd=r.body.getReader(),dec=new TextDecoder();$('ttsaudio').style.display='none';
  const play=b64=>{const bin=atob(b64),n=bin.length>>1;if(!n)return;const f=new Float32Array(n);
    for(let i=0;i<n;i++){let v=bin.charCodeAt(2*i)|(bin.charCodeAt(2*i+1)<<8);if(v>=32768)v-=65536;f[i]=v/32768}
    const ab=ctx.createBuffer(1,n,24000);ab.copyToChannel(f,0);const src=ctx.createBufferSource();src.buffer=ab;src.connect(ctx.destination);
    at=Math.max(at,ctx.currentTime);src.start(at);at+=ab.duration;bytes+=n*2};
  for(;;){const{value,done}=await rd.read();if(done)break;buf+=dec.decode(value,{stream:true});let i;
    while((i=buf.indexOf('\n\n'))>=0){const ev=buf.slice(0,i);buf=buf.slice(i+2);const line=ev.split('\n').find(l=>l.startsWith('data:'));if(!line)continue;
      const d=JSON.parse(line.slice(5));if(d.type==='speech.audio.delta'){if(first===null){first=(performance.now()-t0)/1000;$('ttsmsg').textContent=`${t('erster Ton nach','first audio after')} ${first.toFixed(2)} s …`}play(d.audio)}
      else if(d.type==='speech.audio.error')throw new Error(d.error&&d.error.message||t('Fehler im Stream','error in stream'))}}
  $('ttsmsg').textContent=`${t('erster Ton nach','first audio after')} ${first!=null?first.toFixed(2):'?'} s · ${(bytes/48000).toFixed(1)} s ${t('Audio in','audio in')} ${((performance.now()-t0)/1000).toFixed(2)} s`}

async function loadClone(){const l=await (await api('/api/clone-voices')).json();
  $('vlist').innerHTML=l.map(n=>`<tr><td>${esc(n)}</td><td style="text-align:right;white-space:nowrap"><button class="b" type="button" data-vprobe="${esc(n)}">${t('Probe sprechen','Speak a sample')}</button> <button class="b" type="button" data-vref="${esc(n)}">${t('Referenz anhören','Play reference')}</button> <button class="b" type="button" data-vexp="${esc(n)}">${t('Exportieren','Export')}</button> <button class="b" type="button" data-vdel="${esc(n)}">${t('Löschen','Delete')}</button></td></tr>`).join('')||`<tr><td class="mut">${t('Noch keine.','None yet.')}</td></tr>`;if(!l.length)$('vaddbox').open=true}
// names travel in data attributes, never inside inline JavaScript
$('vlist').onclick=e=>{const b=e.target.closest('button');if(!b)return;const d=b.dataset;
  if(d.vprobe!=null)probeVoice(d.vprobe,b);else if(d.vref!=null)playRef(d.vref);
  else if(d.vexp!=null)location.href='/api/clone-voices-export?names='+encodeURIComponent(d.vexp);else if(d.vdel!=null)delVoice(d.vdel)};
$('vexpall').onclick=()=>{location.href='/api/clone-voices-export'};
$('vimpbtn').onclick=()=>$('vimpfile').click();
$('vimpfile').onchange=async()=>{const f=$('vimpfile').files[0];if(!f)return;$('vimpfile').value='';
  const fd=new FormData();fd.append('file',f);fd.append('conflict',$('vimpconflict').value);$('vimpmsg').textContent=t('Importiere …','Importing …');
  try{const r=await (await api('/api/clone-voices-import',{method:'POST',body:fd})).json();
    const ok=r.voices.filter(v=>v.result==='imported'),sk=r.voices.filter(v=>v.result==='skipped');
    $('vimpmsg').textContent=t('Importiert: ','Imported: ')+(ok.map(v=>v.as===v.name?v.name:`${v.name} → ${v.as}`).join(', ')||'–')+
      (sk.length?' · '+t('übersprungen: ','skipped: ')+sk.map(v=>v.name).join(', '):'');loadClone()}
  catch(e){$('vimpmsg').innerHTML=`<span class="err">${esc(e.message)}</span>`}};
function playRef(n){const a=new Audio('/api/clone-voices/'+encodeURIComponent(n)+'.wav');a.play()}
async function delVoice(n){if(!confirm(t(`Stimme ${n} löschen?`,`Delete voice ${n}?`)))return;await api('/api/clone-voices/'+encodeURIComponent(n),{method:'DELETE'});loadClone()}
// One short sentence with exactly this voice, through the same admin test route as Zustand → Prüfen.
// Cloned voices only sound like themselves with a Base model; otherwise the engine's answer says why.
const PROBE={de:'Hallo, so klinge ich als Stimme des Spark.',en:'Hello, this is how I sound as the voice of the Spark.'};
async function probeVoice(n,btn){const lang=$('vreadlang').value==='en'?'en':'de',msg=$('vprobemsg');btn.disabled=true;msg.textContent=t('Spreche …','Speaking …');
  try{const r=await api('/api/test/tts',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({input:PROBE[lang],voice:n,language:lang==='en'?'English':'German',instruct:null})});
    const a=new Audio(URL.createObjectURL(await r.blob()));a.play();msg.textContent=''}
  catch(e){msg.textContent=t('Probe ging nicht: ','Sample failed: ')+e.message+((CFG&&CFG.tts&&!/Base/.test(CFG.tts.model||''))?t(' (geklonte Stimmen brauchen ein Base-Modell unter Sprachausgabe)',' (cloned voices need a Base model under Speech output)'):'')}
  btn.disabled=false}
// Record the reference with the microphone: 24 kHz mono WAV, transcript filled in by the ASR.
const vr={rec:null,stream:null,blob:null,iv:null};
// The reading text sets the language the cloned voice speaks best, independent of the panel language.
const READ_TEXT={de:'Guten Tag. Ich spreche diesen Text in ruhigem Ton und normalem Tempo, damit meine Stimme gut nachgebildet werden kann. Danach klingt die Sprachausgabe so wie ich.',en:'Hello. I am reading this text in a calm voice and at a normal pace, so that my voice can be reproduced well. After that, the speech output will sound like me.'};
function setReadLang(l){$('vreadlang').value=l;$('vread').textContent=READ_TEXT[l];try{localStorage.setItem('vreadlang',l)}catch{}}
{let l='de';try{l=localStorage.getItem('vreadlang')||'de'}catch{}setReadLang(READ_TEXT[l]?l:'de')}
$('vreadlang').onchange=e=>setReadLang(e.target.value);
$('vrec').onclick=async()=>{
  if(vr.rec){vr.rec.stop();return}
  if(!window.isSecureContext||!navigator.mediaDevices){const port=CFG&&CFG.panel&&CFG.panel.https_port,u=`https://${location.hostname}:${port||31443}/`;
    $('vsecure').style.display='block';const a=document.querySelector('.vhttps');a.href=u;a.textContent=u;return}
  try{vr.stream=await navigator.mediaDevices.getUserMedia({audio:{echoCancellation:false,noiseSuppression:true,autoGainControl:true,channelCount:1}})}
  catch(e){$('vmsg').innerHTML=`<span class="err">${esc(t('Kein Zugriff aufs Mikrofon: ','No microphone access: ')+e.message)}</span>`;return}
  const mime=['audio/webm;codecs=opus','audio/webm','audio/mp4','audio/ogg'].find(m=>window.MediaRecorder&&MediaRecorder.isTypeSupported(m))||'';
  const rec=new MediaRecorder(vr.stream,mime?{mimeType:mime}:{}),parts=[];vr.rec=rec;
  const ctx=audioCtx(),src=ctx.createMediaStreamSource(vr.stream),an=ctx.createAnalyser();an.fftSize=1024;src.connect(an);const buf=new Float32Array(an.fftSize);
  const t0=performance.now();let peak=0;
  vr.iv=setInterval(()=>{an.getFloatTimeDomainData(buf);let m=0;for(const v of buf)m=Math.max(m,Math.abs(v));peak=Math.max(peak,m);
    $('vlevel').style.width=Math.min(100,m*140)+'%';const s=(performance.now()-t0)/1000;$('vtime').textContent=s.toFixed(1).replace('.',L==='en'?'.':',')+' s';
    if(s>=20)rec.stop()},60);
  rec.ondataavailable=e=>{if(e.data.size)parts.push(e.data)};
  rec.onstop=async()=>{clearInterval(vr.iv);src.disconnect();vr.stream.getTracks().forEach(x=>x.stop());vr.rec=null;$('vlevel').style.width='0';
    $('vrec').classList.remove('rec');$('vrec').textContent=t('Neu aufnehmen','Record again');
    const secs=(performance.now()-t0)/1000;
    try{vr.blob=await toWav(new Blob(parts,{type:rec.mimeType||'audio/webm'}),24000)}catch(e){$('vmsg').innerHTML=`<span class="err">${esc(e.message)}</span>`;return}
    $('vplay').src=URL.createObjectURL(vr.blob);$('vplay').style.display='block';$('vfile').value='';$('vfilename').textContent='wav, mp3, m4a, …';
    const warn=secs<4?t('Etwas kurz, 5–15 Sekunden klonen besser. ','A bit short, 5–15 seconds clone better. '):peak<0.08?t('Sehr leise, näher ans Mikrofon. ','Very quiet, move closer to the microphone. '):'';
    $('vmsg').textContent=warn+t('Erkenne den gesprochenen Text …','Transcribing what you said …');
    const fd=new FormData();fd.append('file',vr.blob,'ref.wav');fd.append('language',$('vreadlang').value==='en'?'English':'German');
    try{const r=await (await api('/api/test/asr',{method:'POST',body:fd})).json();if((r.text||'').trim())$('vtext').value=r.text.trim();
      $('vmsg').textContent=warn+t('Bitte das Transkript prüfen, dann „Hinzufügen“.','Check the transcript, then "Add".')}
    catch(e){$('vtext').value=$('vtext').value||$('vread').textContent.trim();$('vmsg').textContent=warn+t('Spracherkennung nicht erreichbar, Vorlesetext als Transkript übernommen.','Speech recognition unavailable, used the reading text as transcript.')}};
  rec.start();$('vrec').classList.add('rec');$('vrec').textContent=t('Aufnahme beenden','Stop recording');$('vmsg').textContent='';$('vplay').style.display='none';vr.blob=null};
$('vfile').onchange=()=>{vr.blob=null;$('vplay').style.display='none'};
$('vadd').onclick=async()=>{const f=vr.blob||$('vfile').files[0];if(!f||!$('vname').value){$('vmsg').textContent=t('Name und Aufnahme (oder Datei) fehlen.','Name and recording (or file) are missing.');return}const fd=new FormData();fd.append('name',$('vname').value);fd.append('text',$('vtext').value);fd.append('file',f,vr.blob?'ref.wav':f.name);
  try{await api('/api/clone-voices',{method:'POST',body:fd});$('vmsg').textContent=t('Hinzugefügt.','Added.');loadClone()}catch(e){$('vmsg').innerHTML=`<span class="err">${esc(e.message)}</span>`}};

const AUDIT={admin_login:t('Admin angemeldet','admin signed in'),admin_login_failed:t('Admin-Passwort falsch','wrong admin password'),
  admin_basic_failed:t('Admin-Passwort (Skript) falsch','wrong admin password (script)'),admin_password_failed:t('altes Passwort falsch','wrong current password'),
  admin_password_changed:t('Admin-Passwort geändert','admin password changed'),profile_login:t('Profil angemeldet','profile signed in'),
  profile_login_failed:t('PIN falsch','wrong PIN'),profile_logout_all:t('überall abgemeldet','logged out everywhere'),
  profile_device_removed:t('Gerät gesperrt','device blocked'),foreign_page_refused:t('fremde Seite abgewiesen','foreign page refused'),
  invite_made:t('Einladung erstellt','invitation created'),invite_used:t('neue Person über Einladung','new person by invitation'),
  invite_app:t('neue Person über Einladung (iPhone-App)','new person by invitation (iPhone app)'),invite_pin:t('neue PIN über Einladungslink','new PIN through an invitation link'),
  invite_revoked:t('Einladung zurückgezogen','invitation withdrawn'),handoff_login:t('Handy über QR-Code angemeldet','phone signed in by QR code'),
  backup:t('Sicherung','backup'),restore:t('Wiederherstellung','restore'),watchdog:t('Wächter','watchdog')};
async function auditText(){const d=await (await api('/api/audit?limit=500')).json();
  return d.events.slice().reverse().map(e=>{const who=e.who||(e.uid&&d.names[e.uid])||e.name||'';
    const what=e.event==='change'?`${e.method} ${e.path} → ${e.status}`:(AUDIT[e.event]||e.event)+(e.locked?t(` – gesperrt für ${e.locked} s`,` – locked for ${e.locked} s`):'')+(e.detail?' – '+e.detail:'');
    return `${new Date(e.t*1000).toLocaleString()}  ${(e.ip||'').padEnd(15)}  ${who?who+': ':''}${what}`}).join('\n')}
$('tts.model').addEventListener('change',()=>instrHint(true));


function kv(rows){return rows.map(([k,v])=>`<tr><td class="mut" style="width:40%">${k}</td><td><code>${esc(v)}</code> <button class="b" style="padding:1px 6px;font-size:12px" ${onAttr('copyPrev')}>${t('kopieren','copy')}</button></td></tr>`).join('')}
async function loadInt(){const c=await (await api('/api/config')).json();const v=await (await api('/api/tts/voices')).json();
  const host=location.hostname,asr=`http://${host}:${c.asr.port}/v1`,tts=`http://${host}:${c.tts.port}/v1`,key=c.api.key||t('beliebig, z. B. sk-local','anything, e.g. sk-local');
  const voice=c.tts.default_voice||((v.voices||[])[0]||'ryan');
  $('int-ep').innerHTML=kv([[t('Spracherkennung (STT)','Speech recognition (STT)'),asr+'/audio/transcriptions'],[t('Sprachausgabe (TTS)','Speech output (TTS)'),tts+'/audio/speech'],[t('API-Schlüssel','API key'),c.api.key||t('(keiner gesetzt)','(none set)')]]);
  $('int-owui-stt').innerHTML=kv([['Speech-to-Text Engine','OpenAI'],['API Base URL',asr],['API Key',key],['STT Model',c.asr.model]]);
  $('int-owui-tts').innerHTML=kv([['Text-to-Speech Engine','OpenAI'],['API Base URL',tts],['API Key',key],['TTS Model',c.tts.model],['TTS Voice',voice],[t('Zusätzliche TTS-Parameter (JSON, optional)','Additional TTS parameters (JSON, optional)'),JSON.stringify({temperature:c.tts.temperature,top_p:c.tts.top_p,seed:c.tts.seed})],[t('Antwort aufteilen','Response splitting'),t('Absätze (Paragraphs)','Paragraphs')]]);
  const panelUrl=`http://${host}:${(c.panel&&c.panel.port)||31080}`;
  $('int-pebble').innerHTML=kv([[t('Spark-Adresse in der Uhr-App','Spark address in the watch app'),panelUrl],[t('App-Datei','App file'),panelUrl+'/pebble/speech-spark.pbw']]);
  $('int-pbw').href=panelUrl+'/pebble/speech-spark.pbw';
  const siriBase=location.protocol==='https:'?location.origin:panelUrl;
  $('int-siri').innerHTML=kv([['URL',siriBase+'/api/siri/ask'],[t('Methode','Method'),'POST'],['Header','X-Speech-Device: sd_…'],[t('Haupttext (JSON)','Request body (JSON)'),'{"text": "…"}'],[t('Antwort','Answer'),'{"answer": "…"}']]);
  $('int-voices').textContent=v.model_kind==='voice_design'?t('VoiceDesign-Modell: die Stimme wird über die Standard-Anweisung beschrieben.','VoiceDesign model: the voice is described by the default instruction.'):((v.voices||[]).join(', ')||t('(Dienst lädt noch)','(service still loading)'));
  const auth=c.api.key?` \\\n  -H "Authorization: Bearer ${c.api.key}"`:'';
  const hello=t('Hallo aus der Spark.','Hello from the Spark.'),lng=t('German','English'),code=t('de','en'),fn=t('hallo','hello');
  const akey=c.api.key||'sk-local';
  $('int-hermes').textContent=`stt:
  enabled: true
  provider: openai
  language: ${code}
  openai:
    base_url: ${asr}
    api_key: ${akey}
    model: ${c.asr.model}
tts:
  provider: openai
  openai:
    base_url: ${tts}
    api_key: ${akey}
    model: ${c.tts.model}
    voice: ${voice}`;
  $('int-openclaw').textContent=`{
  tts: {
    auto: "inbound",
    provider: "openai",
    providers: {
      openai: {
        baseUrl: "${tts}",
        apiKey: "${akey}",
        model: "${c.tts.model}",
        speakerVoice: "${voice}",
        responseFormat: "mp3",
      },
    },
  },
  tools: {
    media: {
      models: [{
        provider: "openai",
        model: "${c.asr.model}",
        baseUrl: "${asr}",
        capabilities: ["audio"],
      }],
      audio: { enabled: true },
    },
  },
}`;
  $('int-curl').textContent=`# ${t('Text -> Sprache','Text -> speech')} (mp3)
curl ${tts}/audio/speech${auth} \\
  -H "Content-Type: application/json" \\
  -d '{"model":"qwen3-tts","input":"${hello}","voice":"${voice}","language":"${lng}"}' -o ${fn}.mp3

# ${t('Sprache -> Text','Speech -> text')}
curl ${asr}/audio/transcriptions${auth} \\
  -F file=@${fn}.mp3 -F language=${code}`;
  $('int-py').textContent=`from openai import OpenAI

tts = OpenAI(base_url="${tts}", api_key="${c.api.key||'sk-local'}")
stt = OpenAI(base_url="${asr}", api_key="${c.api.key||'sk-local'}")

with tts.audio.speech.with_streaming_response.create(
        model="qwen3-tts", voice="${voice}", input="${hello}") as r:
    r.stream_to_file("${fn}.mp3")

with open("${fn}.mp3", "rb") as f:
    print(stt.audio.transcriptions.create(model="qwen3-asr", file=f, language="${code}").text)`;}
$('adminout').onclick=async()=>{if(!confirm(t('Admin in allen Browsern abmelden, auch hier?','Log the admin out in every browser, this one too?')))return;
  try{await api('/api/logout-everywhere',{method:'POST'});location.reload()}catch(e){alert(e.message)}};
$('genkey').onclick=()=>{const a=new Uint8Array(18);crypto.getRandomValues(a);$('api.key').value='sk-'+[...a].map(x=>x.toString(16).padStart(2,'0')).join('')};

let updPoll=null;
async function loadSys(check=false){let u;try{u=await (await api('/api/update'+(check?'?check=true':''))).json()}catch(e){$('updstate').innerHTML=`<span class="err">${esc(e.message)}</span>`;return}
  const i=u.installed||{},r=u.remote||{};
  $('sysver').innerHTML=kvp([[t('Installiert','Installed'),i.short?`${i.short} · ${new Date(i.date).toLocaleString()}`:'–'],[t('Änderung','Change'),i.subject||'–'],['Engines',i.engine||'–'],[t('Quelle','Source'),i.remote||'–'],[t('Zuletzt geprüft','Last checked'),r.checked?new Date(r.checked*1000).toLocaleTimeString():'–']]);
  updBadge(r);loadBak();
  const pv=u.previous;$('updprevrow').style.display=pv&&!u.running?'flex':'none';
  if(pv)$('updprevtxt').textContent=(pv.version||pv.short||'')+(pv.subject?' · '+pv.subject:'');
  if(u.running){$('updstate').innerHTML=t('<span class="pill warn">Update läuft</span> Die Seite lädt neu, wenn das Panel neu startet.','<span class="pill warn">Update running</span> The page reloads when the panel restarts.');$('updgo').disabled=true;$('updstop').style.display='inline-block';
    if(!updPoll)updPoll=setInterval(()=>loadSys(),3000)}
  else{if(updPoll){clearInterval(updPoll);updPoll=null}$('updstop').style.display='none';
    $('updstate').innerHTML=r.error?`<span class="err">${esc(r.error)}</span>`:r.behind===0?`<span class="pill ok">${t('aktuell','up to date')}</span>`:
      `<span class="pill warn">${t('Update verfügbar','Update available')}</span> ${r.behind>0?r.behind+t(' Änderung(en)',' change(s)'):''}`+(u.last_result&&u.last_result!=='success'&&u.last_finished?` <span class="err">${t('Letztes Update fehlgeschlagen','Last update failed')} (${esc(u.last_result)}), ${t('siehe Protokoll','see log')}.</span>`:'')
      +(r.head&&r.latest&&r.head!==r.latest?` <span class="mut">${r.head_state==='red'?t('Neuere Änderungen sind auf GitHub durch die Tests gefallen und werden nicht angeboten.','Newer changes failed the tests on GitHub and are not offered.'):t('Neuere Änderungen werden auf GitHub noch geprüft und erst danach angeboten.','Newer changes are still being tested on GitHub and are offered once they pass.')}</span>`:'');
    $('updgo').disabled=!(r.behind&&r.behind!==0)}
  $('updcommits').innerHTML=(r.commits||[]).length?'<table>'+r.commits.slice().reverse().map(c=>`<tr><td class="mut" style="width:70px"><code>${esc(c.sha)}</code></td><td>${esc(c.title)}</td></tr>`).join('')+'</table>':'';
  $('updlog').textContent=await (await api('/api/logs/update?lines=200')).text()||t('(noch kein Update gelaufen)','(no update has run yet)');$('updlog').scrollTop=1e9}
const kvp=rows=>rows.map(([k,v])=>`<tr><td class="mut" style="width:35%">${k}</td><td>${esc(v)}</td></tr>`).join('');
// Update notice on top of every page, also the assistant, for the logged-in admin only; "✕" hides
// it until a newer version appears.
function updBanner(r){const on=ADMIN&&r&&r.behind&&r.behind!==0&&r.latest;let hid='';try{hid=localStorage.getItem('updhide')||''}catch{}
  $('updbanner').style.display=on&&hid!==r.latest?'flex':'none';if(!on)return;
  $('updbtext').textContent=t('Update verfügbar','Update available')+(r.version?': '+r.version:'')+(r.behind>0?t(` (${r.behind} Änderung${r.behind>1?'en':''})`,` (${r.behind} change${r.behind>1?'s':''})`):'');
  $('updbx').onclick=()=>{try{localStorage.setItem('updhide',r.latest)}catch{}$('updbanner').style.display='none'}}
$('updbgo').onclick=()=>{$('updbanner').style.display='none';goSec('sys')};
function updBadge(r){window.UPD=r;updBanner(r);zustand();if(CFG)glance();const on=r&&r.behind&&r.behind!==0;$('updbadge').style.display=on?'inline-block':'none';
  document.querySelectorAll('.subbadge').forEach(x=>x.style.display=on?'inline-block':'none')}
// "Jetzt prüfen": the button shows that it is working (asking GitHub takes a few seconds), then when it checked
$('updcheck').onclick=async()=>{const b=$('updcheck');if(b.disabled)return;b.disabled=true;b.textContent=t('Prüfe …','Checking …');
  $('updstate').innerHTML=`<span class="pill">${t('Prüfe auf GitHub …','Checking GitHub …')}</span>`;
  try{await loadSys(true)}finally{b.disabled=false;b.textContent=t('Jetzt prüfen','Check now')}
  if(!$('updstate').querySelector('.err'))$('updstate').insertAdjacentHTML('beforeend',` <span class="mut">${t('Geprüft um','Checked at')} ${esc(new Date().toLocaleTimeString())}</span>`)};
let benchPoll=null;
// how good each value is: levels and sentences come from bench.rate(), the page only shows them
const BENCH_CLS={top:'ok',ok:'ok',warn:'warn',bad:'bad'};
function benchRender(r){const box=$('benchrate');if(!r){box.innerHTML='';return}
  const v=r.verdict||{},lvl=BENCH_CLS[v.level]||'warn';
  box.innerHTML=`<div class="bverdict" data-lvl="${lvl}"><span class="bvicon">${lvl==='ok'?'✓':'!'}</span><div><b>${esc(v.title||'')}</b>${v.detail?`<div class="mut">${esc(v.detail)}</div>`:''}</div></div>`+
    `<table class="brate"><tbody>${(r.groups||[]).map(g=>`<tr class="bgrp"><td colspan="4">${esc(g.name)}</td></tr>`+g.rows.map(x=>
      `<tr><td>${esc(x.label)}</td><td class="bnum">${esc(x.value)}</td><td><span class="pill ${BENCH_CLS[x.level]||''}">${esc(x.word)}</span></td><td class="bwhy">${esc(x.why)}${x.before?` <span class="bprev">· ${t('letzte Messung','last run')} ${esc(x.before)}</span>`:''}</td></tr>`).join('')).join('')}</tbody></table>`}
async function loadBench(){let b;try{b=await (await api('/api/bench')).json()}catch(e){$('benchmsg').innerHTML=`<span class="err">${esc(e.message)}</span>`;return}
  $('benchgo').disabled=b.running;
  $('benchmsg').textContent=b.running?t('läuft…','running…'):b.result?t('letzte Messung: ','last measurement: ')+new Date(b.result.time*1000).toLocaleString():'';
  $('benchout').textContent=b.running?b.log.join('\n'):(b.report||t('(noch nicht gemessen)','(not measured yet)'));
  if(b.running)$('benchraw').open=true;else if(benchPoll)$('benchraw').open=false;benchRender(b.running?null:b.rating);
  if(b.running&&!benchPoll)benchPoll=setInterval(loadBench,2000);
  if(!b.running&&benchPoll){clearInterval(benchPoll);benchPoll=null}}
$('benchgo').onclick=async()=>{try{await api('/api/bench',{method:'POST'});loadBench()}catch(e){$('benchmsg').innerHTML=`<span class="err">${esc(e.message)}</span>`}};
// speech first (vorrang.py): today's counters and the three-way test; the verdict comes from vorrang.verdict()
let vrPoll=null;
function vrRender(d){const s=d.today||{},r=d.result;
  $('vrtoday').textContent=t(`Heute: ${s.held||0}× Hintergrundarbeit angehalten, ${s.cancelled||0}× abgebrochen, längste Wartezeit ${s.waited_max||0} s, ${s.behind||0}× Sprachausgabe mitten im Satz zu langsam.`+(s.speaking?' Gerade wird gesprochen.':'')+(d.people&&d.people.held?` Vorrang für Personen: ${d.people.held}× warteten andere, höchstens ${(d.people.held_ms_max/1000).toFixed(1)} s.`:''),
    `Today: background work held ${s.held||0}×, cancelled ${s.cancelled||0}×, longest wait ${s.waited_max||0} s, speech output too slow inside a sentence ${s.behind||0}×.`+(s.speaking?' Speech is running right now.':'')+(d.people&&d.people.held?` Priority for people: others waited ${d.people.held}×, at most ${(d.people.held_ms_max/1000).toFixed(1)} s.`:''));
  $('vrgo').disabled=!!d.running;
  $('vrmsg').textContent=d.running?t('läuft … (etwa eine Minute)','running … (about a minute)'):r&&r.t?t('letzte Prüfung: ','last check: ')+new Date(r.t*1000).toLocaleString():'';
  if(!r||d.running)$('vrout').innerHTML='';
  else if(!r.alone)$('vrout').innerHTML=`<div class="err">${esc(r.error||'')}</div>`;
  else{const v=r.verdict||{},lvl=BENCH_CLS[v.level]||'warn',ttl=v.title?(L==='en'?v.title.en:v.title.de):'';
    const n=x=>x==null?'–':(L==='en'?String(x):String(x).replace('.',','));
    const row=(name,x)=>x?`<tr><td>${name}</td><td class="bnum">${n(x.first)} s</td><td class="bnum">${n(x.rtf)}</td><td class="bnum">${n(x.asr)} s</td></tr>`:'';
    $('vrout').innerHTML=`<div class="bverdict" data-lvl="${lvl}"><span class="bvicon">${lvl==='ok'?'✓':'!'}</span><div><b>${esc(ttl)}</b>${r.error?`<div class="mut">${esc(r.error)}</div>`:''}</div></div>`+
      `<table class="brate"><tbody><tr class="bgrp"><td></td><td>${t('Erster Ton','First audio')}</td><td>${t('Echtzeitfaktor','Real-time factor')}</td><td>${t('Erkennung','Recognition')}</td></tr>`+
      row(t('Alleine','Alone'),r.alone)+row(t('Unter Last, ohne Vorfahrt','Under load, no priority'),r.load)+row(t('Unter Last, mit Vorfahrt','Under load, with priority'),r.vorrang)
      +(r.people?row(t('Zwei Personen gleichzeitig, ohne Vorrang','Two people at once, no priority'),r.people.normal)+row(t('Zwei Personen gleichzeitig, mit Vorrang','Two people at once, with priority'),r.people.vorrang):'')+`</tbody></table>`
      +(r.people_verdict?`<div class="fh">${esc(L==='en'?r.people_verdict.title.en:r.people_verdict.title.de)}</div>`:'')+
      `<div class="fh">${t('Echtzeitfaktor unter 1 heißt flüssig. Erster Ton und Erkennung in Sekunden.','Real-time factor below 1 means fluent. First audio and recognition in seconds.')}</div>`}
  if(d.running&&!vrPoll)vrPoll=setInterval(loadVorrang,3000);
  if(!d.running&&vrPoll){clearInterval(vrPoll);vrPoll=null}}
async function loadVorrang(){try{vrRender(await (await api('/api/vorrang')).json())}catch{}}
$('vrgo').onclick=async()=>{try{vrRender(await (await api('/api/vorrang',{method:'POST'})).json())}catch(e){$('vrmsg').innerHTML=`<span class="err">${esc(e.message)}</span>`}};
// own Kiwix (kiwix.py): check, and the book list to choose from (built with textContent only)
async function kxCheck(){return await (await api('/api/admin/kiwix/check',{method:'POST'})).json()}
// the picker: chosen books as chips on top (also before the catalog is loaded), below the catalog as a
// list with search, language and group filter, grouped, each with language, variant, articles, size, date
const KX={books:null,q:'',lang:'',grp:''};
// a book is chosen by its name without the date: an updated file (newer date) stays chosen (V01.0.261)
const kxKey=id=>String(id||'').replace(/_\d{4}-\d{2}(-\d{2})?$/,'')||String(id||'');
const kxSel=()=>[...new Set($('chat.kiwix_books').value.split(/[\s,;]+/).filter(Boolean).map(kxKey))];
function kxSet(v){$('chat.kiwix_books').value=v.slice(0,10).join(', ');$('chat.kiwix_books').dispatchEvent(new Event('input',{bubbles:true}));kxChips();kxList()}
let KXLN=null;try{KXLN=new Intl.DisplayNames([L==='en'?'en':'de'],{type:'language'})}catch{}
const kxLang=c=>!c?t('ohne Sprache','no language'):c==='mul'?t('mehrsprachig','multilingual'):(()=>{try{const n=KXLN&&KXLN.of(c);return n&&n!==c?n:c}catch{return c}})();
const KXG={wikipedia:'Wikipedia',wiktionary:'Wiktionary',wikivoyage:'Wikivoyage',wikibooks:'Wikibooks',wikiquote:'Wikiquote',wikisource:'Wikisource',wikiversity:'Wikiversity',wikinews:'Wikinews',ted:'TED',phet:'PhET',stack_exchange:'Stack Exchange',stackexchange:'Stack Exchange',gutenberg:'Gutenberg',devdocs:'Docs',vikidia:'Vikidia',wikihow:'wikiHow',other:t('Sonstiges','Other')};
const kxGrp=g=>KXG[g]||(g?g.charAt(0).toUpperCase()+g.slice(1).replace(/_/g,' '):t('Sonstiges','Other'));
const kxSize=n=>!n?'':n>=1e9?(n/1e9).toFixed(1).replace('.',L==='en'?'.':',')+' GB':Math.max(1,Math.round(n/1e6))+' MB';
const kxNum=n=>n?n.toLocaleString(L==='en'?'en':'de')+' '+t('Artikel','articles'):'';
const kxMeta=b=>[kxLang(b.lang),b.flavour,kxNum(b.count),kxSize(b.size),b.date].filter(Boolean).join(' · ');
function kxChips(){const box=$('kxsel'),sel=kxSel(),known=Object.fromEntries((KX.books||[]).map(b=>[b.key||kxKey(b.id),b]));box.textContent='';
  if(!sel.length){const m=document.createElement('span');m.className='mut';m.textContent=t('Keine Auswahl: deutsche und englische Wikipedia.','No choice: German and English Wikipedia.');box.appendChild(m);return}
  sel.forEach(id=>{const b=known[id],c=document.createElement('span');c.className='kxchip';c.title=id;
    const n=document.createElement('span');n.textContent=b?b.title:id;c.appendChild(n);
    if(b){const m=document.createElement('small');m.textContent=[kxLang(b.lang),b.flavour,b.date].filter(Boolean).join(', ');c.appendChild(m)}
    const x=document.createElement('button');x.type='button';x.textContent='×';x.setAttribute('aria-label',t('Entfernen','Remove'));x.onclick=()=>kxSet(kxSel().filter(y=>y!==id));c.appendChild(x);
    box.appendChild(c)})}
function kxPicker(){const box=$('kxpick');box.hidden=false;box.textContent='';const bar=document.createElement('div');bar.className='kxbar';
  const q=document.createElement('input');q.type='search';q.placeholder=t('Suchen: Titel, Name, Beschreibung','Search: title, name, description');q.value=KX.q;q.maxLength=60;
  q.oninput=()=>{KX.q=q.value;kxList()};
  const counts=(key)=>{const m={};(KX.books||[]).forEach(b=>{m[b[key]]=(m[b[key]]||0)+1});return m};
  const ls=document.createElement('select'),lc=counts('lang');
  const opt=(sel,v,l)=>{const o=document.createElement('option');o.value=v;o.textContent=l;sel.appendChild(o)};
  opt(ls,'',t('Deutsch und Englisch','German and English'));opt(ls,'*',t('Alle Sprachen','All languages')+` (${(KX.books||[]).length})`);
  Object.keys(lc).sort((a,b)=>kxLang(a).localeCompare(kxLang(b))).forEach(c=>opt(ls,c,`${kxLang(c)} (${lc[c]})`));ls.value=KX.lang;ls.onchange=()=>{KX.lang=ls.value;kxList()};
  const gs=document.createElement('select'),gc=counts('group');opt(gs,'',t('Alle Arten','All kinds'));
  Object.keys(gc).sort((a,b)=>kxGrp(a).localeCompare(kxGrp(b))).forEach(g=>opt(gs,g,`${kxGrp(g)} (${gc[g]})`));gs.value=KX.grp;gs.onchange=()=>{KX.grp=gs.value;kxList()};
  bar.append(q,ls,gs);const list=document.createElement('div');list.className='kxlist';list.id='kxlist';box.append(bar,list);kxList()}
function kxList(){const list=$('kxlist');if(!list||!KX.books)return;list.textContent='';const sel=kxSel(),full=sel.length>=10;
  const q=KX.q.trim().toLowerCase();
  const hit=b=>(KX.lang==='*'||(KX.lang?b.lang===KX.lang:['de','en'].includes(b.lang)))&&(!KX.grp||b.group===KX.grp)
    &&(!q||(b.title+' '+b.id+' '+(b.desc||'')).toLowerCase().includes(q));
  const rows=KX.books.filter(b=>sel.includes(b.key)||hit(b));
  const order=b=>(sel.includes(b.key)?0:1);
  const groups={};rows.forEach(b=>{(groups[b.group]=groups[b.group]||[]).push(b)});
  const names=Object.keys(groups).sort((a,b)=>(a==='wikipedia'?-1:b==='wikipedia'?1:kxGrp(a).localeCompare(kxGrp(b))));
  let shown=0;const MAX=150;
  for(const g of names){if(shown>=MAX)break;const h=document.createElement('div');h.className='kxgrp';h.textContent=`${kxGrp(g)} (${groups[g].length})`;list.appendChild(h);
    groups[g].sort((a,b)=>order(a)-order(b)||(a.lang==='de'?0:1)-(b.lang==='de'?0:1)||(b.count||0)-(a.count||0)||a.title.localeCompare(b.title));
    for(const b of groups[g]){if(shown++>=MAX)break;const on=sel.includes(b.key),r=document.createElement('label');r.className='kxrow'+(!on&&full?' dis':'');r.title=b.id;
      const c=document.createElement('input');c.type='checkbox';c.checked=on;c.disabled=!on&&full;
      c.onchange=()=>kxSet(c.checked?kxSel().concat([b.key]):kxSel().filter(y=>y!==b.key));
      const tx=document.createElement('div'),tt=document.createElement('div'),mm=document.createElement('div');tt.className='kxt';tt.textContent=b.title;mm.className='kxm';mm.textContent=kxMeta(b)+(b.desc?' – '+b.desc:'');
      tx.append(tt,mm);r.append(c,tx);list.appendChild(r)}}
  if(!rows.length){const m=document.createElement('div');m.className='kxmore';m.textContent=t('Nichts gefunden. Andere Sprache oder Art wählen.','Nothing found. Pick another language or kind.');list.appendChild(m)}
  else if(rows.length>MAX){const m=document.createElement('div');m.className='kxmore';m.textContent=t(`${rows.length-MAX} weitere – Suche oder Filter eingrenzen.`,`${rows.length-MAX} more – narrow the search or filter.`);list.appendChild(m)}
  if(full){const m=document.createElement('div');m.className='kxmore';m.textContent=t('10 Bücher gewählt, mehr geht nicht.','10 books chosen, that is the most.');list.prepend(m)}}
$('kxload').onclick=async()=>{if(KX.books&&!$('kxpick').hidden){$('kxpick').hidden=true;return}
  $('kxmsg').textContent=t('Lade …','Loading …');
  try{const d=await kxCheck(),best={};(d.books||[]).forEach(b=>{b.key=b.key||kxKey(b.id);const o=best[b.key];if(!o||(b.date||'')+b.id>(o.date||'')+o.id)best[b.key]=b});KX.books=Object.values(best);$('kxmsg').textContent=d.ok?t(`${KX.books.length} Bücher im Kiwix`,`${KX.books.length} books in the Kiwix`):(d.error||'');kxChips();if(d.ok)kxPicker()}
  catch(e){$('kxmsg').textContent=e.message}};
$('kxgo').onclick=async()=>{$('kxgomsg').textContent=t('Prüfe …','Checking …');$('kxout').textContent='';
  try{const d=await kxCheck(),out=$('kxout');$('kxgomsg').textContent='';
    const line=(txt,cls)=>{const x=document.createElement('div');if(cls)x.className=cls;x.textContent=txt;out.appendChild(x)};
    if(!d.ok){line(d.error||t('Nicht erreichbar','Not reachable'),'err');return}
    line(t(`Erreichbar in ${d.ms} ms, ${d.books.length} Bücher; durchsucht werden ${(d.chosen||[]).length}.`,`Reachable in ${d.ms} ms, ${d.books.length} books; ${(d.chosen||[]).length} are searched.`));
    if(d.test)line(t(`Testsuche in „${d.test.book}“: ${d.test.hits} Treffer in ${d.test.ms} ms.`,`Test search in "${d.test.book}": ${d.test.hits} hits in ${d.test.ms} ms.`));
    else line(t('Kein Wikipedia-Buch gewählt: Testsuche übersprungen.','No Wikipedia book chosen: test search skipped.'),'mut');
    const known=Object.fromEntries(d.books.map(b=>[b.id,b]));line((d.picked?t('Durchsucht:','Searched:'):t('Keine Auswahl, durchsucht:','No choice, searched:'))+' '+((d.chosen||[]).map(id=>known[id]?known[id].title+(known[id].lang?' ('+known[id].lang+')':''):id).join(', ')||t('nichts','nothing')),'mut')}
  catch(e){$('kxgomsg').textContent=e.message}};
// "Erst lokal suchen" (lokal.py): one sentence through the rule and the quick look (built with textContent only)
const LKKIND={wissen:t('Wissensfrage: erst lokal nachsehen','Knowledge question: look locally first'),lokal:t('Eigene Quelle genannt: nur lokal, kein Web','Own source named: local only, no web'),
  extern:t('Klar extern: direkt hinaus, kein Vorlauf','Clearly outside: straight out, no local look'),'':t('Kein Fall für die lokale Suche','Not a case for the local look')};
const LKSRC={docs:t('Dokumente','Documents'),kiwix:t('Kiwix-Archiv','Kiwix archive'),history:t('Frühere Gespräche','Earlier conversations')};
if($('lkgo'))$('lkgo').onclick=async()=>{const text=$('lktext').value.trim();if(!text)return;$('lkgo').disabled=true;const out=$('lkout');out.textContent='';
  const line=(txt,cls)=>{const x=document.createElement('div');if(cls)x.className=cls;x.textContent=txt;out.appendChild(x)};
  try{const r=await (await api('/api/admin/lokal/test',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({text})})).json();
    line(`${LKKIND[r.kind]??r.kind} (${r.why})`);
    if(r.words&&r.words.length)line(t('Suchwörter: ','Search words: ')+r.words.join(', '),'mut');
    if(r.kind==='wissen'){
      if(!r.sources.length)line(t('Keine eigene Quelle: kein Profil angemeldet und kein Kiwix eingerichtet.','No own source: no profile signed in and no Kiwix set up.'),'mut');
      r.sources.forEach(k=>line(`${LKSRC[k]||k}: `+(k in r.n?t(`${r.n[k]} Treffer`,`${r.n[k]} hits`):r.late.includes(k)?t(`zu langsam (über ${r.budget} ms)`,`too slow (over ${r.budget} ms)`):t('nicht erreichbar','not reachable'))));
      if(r.sources.length)line(t(`Zusammen ${r.ms} ms von höchstens ${r.budget} ms.`,`Together ${r.ms} ms of at most ${r.budget} ms.`),'mut');
      r.hits.forEach(h=>line(`✓ ${h.title} (${h.chars} ${t('Zeichen','chars')})`));
      if(r.sources.length&&!r.hits.length)line(t('Lokal nichts Passendes: das Modell antwortet aus eigenem Wissen oder sucht im Web.','Nothing fitting locally: the model answers from its own knowledge or searches the web.'),'mut')}
    if(r.profile)line(t(`Profil: ${r.profile}`,`Profile: ${r.profile}`),'mut')}
  catch(e){line(e.message,'err')}$('lkgo').disabled=false};
$('updstop').onclick=async()=>{if(!confirm(t('Update abbrechen? Was schon installiert ist, bleibt. Ein späteres Update holt den Rest nach.','Cancel the update? What is already installed stays. A later update installs the rest.')))return;
  try{await api('/api/update',{method:'DELETE'});$('updmsg').textContent=t('abgebrochen','cancelled');loadSys()}
  catch(e){$('updmsg').innerHTML=`<span class="err">${esc(e.message)}</span>`}};
// Update lock: a progress window over the whole page; the server refuses changes meanwhile.
const ul={iv:null,clicked:0,miss:0};
function ulShow(){$('updlock').style.display='grid';$('updlock').className='modal updlock busy';$('ulbtns').style.display='none';$('ullog').style.display='none';
  $('ulhead').textContent=t('Update läuft','Update running');if(!ul.iv){ul.iv=setInterval(ulPoll,2000);ulPoll()}}
function ulStop(){clearInterval(ul.iv);ul.iv=null}
function ulFail(head,text,log,cancel){ulStop();$('updlock').className='modal updlock fail';$('ulhead').textContent=head;$('ultext').textContent=text;
  $('ulnote').textContent=t('Schlägt ein Schritt vor dem Umschalten fehl, läuft die bisherige Version weiter; danach wird sie wieder eingespielt. Die Zeile oben sagt, was passiert ist.','If a step before the switch fails, the previous version keeps running; after it, the previous version is installed again. The line above says what happened.');
  if(log&&log.length){$('ullog').textContent=log.join('\n');$('ullog').style.display='block'}
  $('ulbtns').style.display='flex';$('ulcancel').style.display=cancel?'':'none'}
async function ulPoll(){let p;try{const r=await fetch('/api/update/progress');if(!r.ok)throw 0;p=await r.json();ul.miss=0}
  catch{ul.miss++;$('ultext').textContent=t('Verbinde neu … (das Panel startet neu)','Reconnecting … (the panel restarts)');return}
  const fresh=p.started&&p.started*1000>=ul.clicked-60000;
  if(p.done&&fresh){if(p.ok){ulStop();$('ulfill').style.width='100%';$('ultext').textContent=t('Fertig, lade neu …','Done, reloading …');
      try{sessionStorage.setItem('upddone',p.version||'1')}catch{}setTimeout(()=>location.reload(),1200)}
    else ulFail(t('Update fehlgeschlagen','Update failed'),p.text||'',p.log,false);return}
  if(!p.running){if(Date.now()-ul.clicked>15000){ulStop();   // nothing to do (already up to date) or ended without a report
      if(!fresh){$('updlock').style.display='none';loadSys&&loadSys()}else location.reload()}return}
  $('ulfill').style.width=(fresh?p.percent:3)+'%';$('ultext').textContent=fresh?p.text:t('Starte …','Starting …');
  if(p.started){const s=Math.max(0,p.now-p.started);$('ultime').textContent=Math.floor(s/60)+':'+String(s%60).padStart(2,'0');
    if(s>p.timeout)ulFail(t('Update dauert zu lange','Update is taking too long'),t(`Nach ${Math.round(p.timeout/60)} Minuten nicht fertig. Neu laden zeigt den aktuellen Stand; du kannst das Update auch abbrechen.`,`Not finished after ${Math.round(p.timeout/60)} minutes. Reload shows the current state; you can also cancel the update.`),p.log,true)}}
$('ulreload').onclick=()=>location.reload();
$('ulclose').onclick=()=>{$('updlock').style.display='none';ulStop();if(ADMIN)loadSys()};
$('ulcancel').onclick=async()=>{try{await api('/api/update',{method:'DELETE'})}catch{}location.reload()};
async function ulWatch(){if(ul.iv)return;try{const p=await (await fetch('/api/update/progress?log=false')).json();if(p.running){ul.clicked=(p.started||0)*1000;ulShow()}}catch{}}
setInterval(()=>{if(ADMIN)ulWatch()},8000);   // an update started from another tab or device locks this one too
async function ulCheck(){await ulWatch();
  let v=null;try{v=sessionStorage.getItem('upddone');sessionStorage.removeItem('upddone')}catch{}
  if(v){const e=$('updtoast');e.textContent=t('Update fertig','Update finished')+(v!=='1'?': '+v:'')+'.';e.style.display='block';setTimeout(()=>e.style.display='none',6000)}}
$('updgo').onclick=async()=>{if(!confirm(t('Update jetzt installieren? Die Dienste starten dabei kurz neu.','Install the update now? The services restart briefly.')))return;
  try{ul.clicked=Date.now();await api('/api/update',{method:'POST'});ulShow()}
  catch(e){$('updmsg').innerHTML=`<span class="err">${esc(e.message)}</span>`}};
setInterval(()=>{if(ADMIN)api('/api/update').then(r=>r.json()).then(u=>updBadge(u.remote)).catch(()=>{})},600000);
// ---------------------------------------------------------------- previous version, live check, backups
$('updprev').onclick=async()=>{if(!confirm(t('Die vorige Version wieder installieren? Vorher wird automatisch gesichert. Gilt die vorige Version vor V01.0.37, müssen Kalender-Passwörter und Home-Assistant-Tokens danach neu eingegeben werden.','Install the previous version again? A backup is made first. If the previous version is older than V01.0.37, calendar passwords and Home Assistant tokens have to be entered again afterwards.')))return;
  try{ul.clicked=Date.now();await api('/api/update/rollback',{method:'POST'});ulShow()}catch(e){$('updmsg').innerHTML=`<span class="err">${esc(e.message)}</span>`}};
const LIVE={llm:t('Sprachmodell','Language model'),tools:t('Werkzeugwahl','Tool choice'),search:t('Websuche','Web search'),tts:t('Sprachausgabe','Speech output'),asr:t('Spracherkennung','Speech recognition')};
function liveRender(r){if(!r||!r.steps){$('livesteps').innerHTML=`<tr><td class="mut">${t('Noch nicht geprüft.','Not checked yet.')}</td></tr>`;$('livemsg').textContent='';return}
  $('livesteps').innerHTML=r.steps.map(s=>`<tr><td style="width:34%">${s.ok===true?'✅':s.ok===false?'❌':'➖'} ${esc(LIVE[s.name]||s.name)}</td><td><span class="mut">${s.seconds} s</span> ${esc(s.detail||'')}</td></tr>`).join('');
  $('livemsg').textContent=new Date(r.t*1000).toLocaleString()+' · '+(r.version||'')+(r.reason==='after update'?t(' · nach dem Update',' · after the update'):'')}
// how long people wait for the first sound of an answer (latency.py)
function latRender(l){const f=s=>s?`<b>${s.median} s</b> <span class="mut">(${s.n} ${t('Antworten','answers')}, ${t('9 von 10 unter','9 of 10 below')} ${s.p90} s)</span>`:`<span class="mut">${t('noch keine','none yet')}</span>`;
  $('latsum').innerHTML=!l?'':`${t('Bis zum ersten Ton','Until the first sound')}: ${t('letzte 24 Stunden','last 24 hours')} ${f(l.day)} · ${t('Tage davor','days before')} ${f(l.week)}`+(l.warn?`<div class="err">${esc(l.warn)}</div>`:'')}
async function loadLive(){try{const r=await (await api('/api/livecheck')).json();liveRender(r);latRender(r.latency)}catch{}loadQuality()}
// quality test of the language model (sandbox questions, see quality.py)
let qTimer=null;
// bar while the test runs: questions done of all, time left estimated from the pace so far
function qProg(p){const box=$('qprog'),bar=$('qbar');box.hidden=!p;if(!p)return;
  const n=p.total||0,d=Math.min(p.done||0,n);bar.classList.toggle('wait',!d);bar.firstChild.style.width=d?Math.round(100*d/n)+'%':'';
  const left=d?Math.round(p.seconds/d*(n-d)):0;
  $('qprogtxt').textContent=n?`${t('Frage','Question')} ${Math.min(d+1,n)} ${t('von','of')} ${n}`+(d>=3&&left>0?` · ${t('noch etwa','about')} ${left<60?left+' s':Math.round(left/60)+' min'}${t('',' left')}`:''):t('startet …','starting …')}
function qRender(d){const r=d&&d.last;clearTimeout(qTimer);qProg(d&&d.running?(d.progress||{done:0,total:0,seconds:0}):null);
  if(d&&d.running){$('qmsg').textContent=t('läuft …','running …');$('qgo').disabled=true;qTimer=setTimeout(loadQuality,2000)}
  else{$('qgo').disabled=false;$('qmsg').textContent=r?new Date(r.t*1000).toLocaleString()+' · '+(r.version||'')+(r.reason==='after update'?t(' · nach dem Update',' · after the update'):''):''}
  const none=h=>{$('qsum').innerHTML=h;$('qlist').innerHTML='';$('qallbox').hidden=true};
  if(!r)return none(`<span class="mut">${t('Noch nicht geprüft.','Not tested yet.')}</span>`);
  if(r.error)return none(`<span class="err">${esc(r.error)}</span>`);
  const bad=r.cases.filter(x=>!x.ok),flaky=r.cases.filter(x=>x.ok&&x.flaky),held=r.cases.filter(x=>x.ok&&!x.flaky&&x.held&&x.held.length);
  const min=s=>s>=90?Math.round(s/60)+' min':s+' s';
  $('qsum').innerHTML=`<span class="pill ${bad.length?'warn':'ok'}">${r.passed} / ${r.total}</span> `
    +(bad.length?'':`<b>${t('Alle Fragen richtig.','All questions right.')}</b> `)
    +(flaky.length?`<span class="pill warn">${flaky.length} ${t('erst im zweiten Versuch','only on the second try')}</span> `:'')
    +`<div class="fh">${esc(r.model||'')} · ${t('Temperatur','temperature')} ${r.temperature}${r.tool_temperature!=null?' / '+r.tool_temperature+t(' bei der Werkzeugwahl',' choosing tools'):''} · ${min(r.seconds)}</div>`;
  const mark=x=>(x.new?` <span class="pill warn">${t('neu kaputt','newly broken')}</span>`:'')
    +(x.wobbly?` <span class="mut">${t('wackelt','wobbles')} (${x.wobbly} ${t('von','of')} ${x.runs})</span>`:'');
  const extra=x=>(x.flaky&&x.first?`<br>${t('Erster Versuch','First try')}: ${esc(x.first.why.join('; '))}`:'')
    +(x.held&&x.held.length?`<br>${t('Antwort-Prüfung hat zurückgehalten','Answer check held back')}: ${esc(x.held.join(', '))}${x.raw?' · „'+esc(x.raw)+'“':''}`:'')
    +(x.retried?`<br>${t('Ohne Werkzeug geantwortet, neu gefragt','Answered without a tool, asked again')}`:'');
  const head=x=>`<div class="qq"><span>${x.ok?'✅':'❌'} ${esc(x.q)}${mark(x)}</span><span class="qt">${esc(x.tools.join(', ')||t('kein Werkzeug','no tool'))}</span></div>`;
  // only questions that need a look stay open (one line each, answer clipped to two lines, tap opens it); the rest is folded
  const look=[...bad,...flaky,...held];
  $('qlist').innerHTML=look.map(x=>`<div class="qrow">${head(x)}${x.ok?'':`<div class="qw">${esc(x.why.join('; '))}</div>`}<div class="qa" title="${t('Antippen zeigt alles','Tap to show all')}">${esc(x.answer||'–')}${extra(x)}</div></div>`).join('');
  const rest=r.cases.filter(x=>!look.includes(x));$('qallbox').hidden=!rest.length;
  $('qallsum').textContent=look.length?`${rest.length} ${t('weitere Fragen ohne Befund','more questions without findings')}`:`${t('Alle','All')} ${rest.length} ${t('Fragen ansehen','questions')}`;
  $('qall').innerHTML=rest.map(x=>`<div class="qrow">${head(x)}</div>`).join('')}
$('qlist').addEventListener('click',e=>{const a=e.target.closest('.qa');if(a)a.classList.toggle('open')});
function qOwn(l){if(!l)return;$('qownbox').style.display=l.length?'':'none';
  $('qown').innerHTML=l.map(x=>`<li><span>${esc(x.q)}</span><button class="b" type="button" data-qdrop="${esc(x.id)}">${t('Löschen','Delete')}</button></li>`).join('')}
$('qown').addEventListener('click',async e=>{const b=e.target.closest('[data-qdrop]');if(!b)return;
  try{qOwn((await (await api('/api/quality/cases/'+encodeURIComponent(b.dataset.qdrop),{method:'DELETE'})).json()).own)}catch(err){$('qmsg').innerHTML=`<span class="err">${esc(err.message)}</span>`}});
async function loadQuality(){try{const d=await (await api('/api/quality')).json();qRender(d);qOwn(d.own)}catch{}}
$('qgo').onclick=async()=>{try{qRender(await (await api('/api/quality',{method:'POST'})).json())}catch(e){$('qmsg').innerHTML=`<span class="err">${esc(e.message)}</span>`}};
$('livego').onclick=async()=>{$('livego').disabled=true;$('livemsg').textContent=t('prüft … (bis zu einer Minute)','checking … (up to a minute)');
  try{liveRender(await (await api('/api/livecheck',{method:'POST'})).json())}catch(e){$('livemsg').innerHTML=`<span class="err">${esc(e.message)}</span>`}$('livego').disabled=false;refresh()};
const WHY={daily:t('täglich','daily'),manual:t('von Hand','manual'),'before-update':t('vor Update','before update'),'before-rollback':t('vor Rückkehr','before rollback'),'before-restore':t('vor Wiederherstellung','before restore'),move:t('Umzug (mit Schlüssel)','move (with key)')};
const mb=n=>n<1048576?Math.max(1,Math.round(n/1024))+' KB':(n/1048576).toFixed(1)+' MB';
function bakRender(l){$('baklist').innerHTML=l.map(b=>`<tr><td>${new Date(b.created*1000).toLocaleString()}<div class="mut">${esc(WHY[b.why]||b.why)} · ${mb(b.size)}</div></td><td style="text-align:right;white-space:nowrap"><button class="b mainonly" ${onAttr('bakLoad',b.name)}>${t('Laden','Download')}</button> <button class="b mainonly" ${onAttr('bakRestore',b.name)}>${t('Wiederherstellen','Restore')}</button> <button class="b mainonly" ${onAttr('bakDel',b.name)}>${t('Löschen','Delete')}</button></td></tr>`).join('')||`<tr><td class="mut">${t('Noch keine Sicherung.','No backup yet.')}</td></tr>`}
async function loadBak(){loadOff();try{bakRender((await (await api('/api/backups')).json()).backups)}catch(e){$('bakmsg').innerHTML=`<span class="err">${esc(e.message)}</span>`}}
const bakAsk=()=>confirm(t('Wiederherstellen? Profile, Stimmen und Einstellungen werden durch die Sicherung ersetzt (der jetzige Stand wird vorher gesichert). Geänderte Einstellungen der Dienste wirken nach deren Neustart.','Restore? Profiles, voices and settings are replaced by the backup (the current state is backed up first). Changed service settings take effect after their restart.'));
const bakDone=r=>{$('bakpw').value='';$('bakmsg').textContent=t('Wiederhergestellt: ','Restored: ')+r.restored.join(', ')+(r.restored.includes('admin-mfa-kept')?t(' (der zweite Anmeldeschritt des Admins bleibt der von diesem Spark)',' (the admin\'s second login step stays the one of this Spark)'):'')+(r.restored.includes('keys')?t(' – bitte überall neu anmelden.',' – please sign in again everywhere.'):'');loadBak()};
// a move backup needs its password: taken from the field below the list
const bakErr=e=>{const m=/move backup|wrong password/.test(e.message)?t('Das ist eine Umzugs-Sicherung: Passwort ins Feld unten eintragen und nochmal wiederherstellen. ','This is a move backup: enter its password in the field below and restore again. '):'';$('bakmsg').innerHTML=`<span class="err">${esc(m+e.message)}</span>`};
window.bakRestore=async n=>{if(!bakAsk())return;$('bakmsg').textContent=t('stelle wieder her …','restoring …');
  try{bakDone(await (await api('/api/backups/'+encodeURIComponent(n)+'/restore',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({password:$('bakpw').value})})).json())}catch(e){bakErr(e)}};
window.bakLoad=async n=>{try{const r=await (await api('/api/backups/'+encodeURIComponent(n)+'/ticket',{method:'POST'})).json();
  const a=document.createElement('a');a.href=r.url;a.download=n;document.body.appendChild(a);a.click();a.remove()}catch(e){$('bakmsg').innerHTML=`<span class="err">${esc(e.message)}</span>`}};
window.bakDel=async n=>{if(!confirm(t('Diese Sicherung löschen?','Delete this backup?')))return;bakRender((await (await api('/api/backups/'+encodeURIComponent(n),{method:'DELETE'})).json()).backups)};
ON.bakLoad=(b,n)=>bakLoad(n);ON.bakRestore=(b,n)=>bakRestore(n);ON.bakDel=(b,n)=>bakDel(n);
$('bakgo').onclick=async()=>{$('bakmsg').textContent=t('sichere …','backing up …');try{const b=await (await api('/api/backups',{method:'POST'})).json();$('bakmsg').textContent=t('Gesichert: ','Saved: ')+mb(b.size);loadBak()}catch(e){$('bakmsg').innerHTML=`<span class="err">${esc(e.message)}</span>`}};
// Sicherung nach außen (offsite.py, plan „Bedienung gesamt“ D4, V01.0.286): main admin only, off by default.
// The passwords are never shown again: an empty field keeps the saved one.
function offShow(d){$('offon').checked=d.on;$('offurl').value=d.url;$('offuser').value=d.user;$('offpw').value=$('offkey').value='';
  $('offpw').placeholder=d.has_password?t('WebDAV-Passwort (gespeichert)','WebDAV password (saved)'):t('WebDAV-Passwort','WebDAV password');
  $('offkey').placeholder=d.has_key?t('Sicherungs-Passwort (gespeichert)','Backup password (saved)'):t('Sicherungs-Passwort (mind. 12 Zeichen, aufschreiben)','Backup password (at least 12 characters, write it down)');
  const l=d.last;$('offmsg').textContent=d.running?t('wird gesendet …','sending …'):!l?t('Noch nie gesendet.','Never sent.')
    :l.ok?t('Zuletzt gesendet: ','Last sent: ')+new Date(l.t*1000).toLocaleString()+' · '+mb(l.bytes):t('Fehler am ','Failed on ')+new Date(l.t*1000).toLocaleString()+': '+l.error;
  $('offmsg').classList.toggle('err',!!(l&&!l.ok)&&!d.running)}
async function loadOff(){if(!$('offbox')||document.body.classList.contains('coadm')&&!document.body.classList.contains('owner'))return;
  try{offShow(await (await api('/api/admin/offsite')).json())}catch{}}
async function offPut(b){try{offShow(await (await api('/api/admin/offsite',xjson('PUT',b))).json())}catch(e){$('offmsg').textContent=e.message;$('offmsg').classList.add('err');return false}return true}
if($('offsave'))$('offsave').onclick=()=>offPut({url:$('offurl').value.trim(),user:$('offuser').value.trim(),password:$('offpw').value,key:$('offkey').value});
if($('offon'))$('offon').onchange=async e=>{const on=e.target.checked;if(!await offPut({on,url:$('offurl').value.trim(),user:$('offuser').value.trim(),password:$('offpw').value,key:$('offkey').value}))e.target.checked=!on};
if($('offnow'))$('offnow').onclick=async()=>{try{offShow(await (await api('/api/admin/offsite/now',{method:'POST'})).json());
  const poll=async()=>{let d;try{d=await (await api('/api/admin/offsite')).json()}catch{return}offShow(d);if(d.running)setTimeout(poll,3000)};setTimeout(poll,3000)}
  catch(e){$('offmsg').textContent=e.message;$('offmsg').classList.add('err')}};
$('bakup').onclick=()=>$('bakfile').click();
$('bakfile').onchange=async()=>{const f=$('bakfile').files[0];$('bakfile').value='';if(!f||!bakAsk())return;$('bakmsg').textContent=t('stelle wieder her …','restoring …');
  const fd=new FormData();fd.append('file',f,f.name);fd.append('password',$('bakpw').value);try{bakDone(await (await api('/api/backups-upload',{method:'POST',body:fd})).json())}catch(e){bakErr(e)}};
$('bakmove').onclick=async()=>{const pw=$('bakpw').value;if(pw.length<12){$('bakmsg').innerHTML=`<span class="err">${t('Das Passwort braucht mindestens 12 Zeichen.','The password needs at least 12 characters.')}</span>`;return}
  const again=prompt(t('Passwort zur Kontrolle noch einmal eingeben:','Enter the password once more:'));if(again===null)return;
  if(again!==pw){$('bakmsg').innerHTML=`<span class="err">${t('Die Passwörter sind verschieden.','The passwords differ.')}</span>`;return}
  $('bakmsg').textContent=t('sichere …','backing up …');
  try{const b=await (await api('/api/backups/move',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({password:pw})})).json();$('bakpw').value='';
    $('bakmsg').textContent=t('Umzugs-Sicherung angelegt: ','Move backup made: ')+mb(b.size)+t('. Mit „Laden“ herunterladen und das Passwort gut aufheben.','. Download it with "Download" and keep the password safe.');loadBak()}catch(e){$('bakmsg').innerHTML=`<span class="err">${esc(e.message)}</span>`}};
// alerts on top of every admin page: memory, watchdog, failed live check
function showAlerts(a){$('alerts').innerHTML=(a||[]).map(x=>`<div class="note ${x.level==='bad'?'bad':''}">${esc(x.text)}</div>`).join('')}
// ---------------------------------------------------------------- does the language model see pictures? (images.py)
function visionShow(r){if(!r){$('visionmsg').textContent=t('Noch nicht geprüft.','Not checked yet.');return}
  const when=new Date(r.t*1000).toLocaleString([], {dateStyle:'short',timeStyle:'short'});
  $('visionmsg').innerHTML=r.ok?`<span class="ok">✓ ${t('Kann Bilder','Sees pictures')}</span> · ${esc(when)} · ${esc(String(r.seconds))} s`
    :`<span class="err">✗ ${esc(r.error||t('kann keine Bilder','sees no pictures'))}</span> · ${esc(when)}`}
async function visionLoad(){if(!$('visiongo'))return;try{visionShow((await (await api('/api/admin/vision-test')).json()).last)}catch{}}
// targeted tool choice (intent.py): the rules as a table and one sentence to try (saved words only)
async function routeLoad(){if(!$('routetable'))return;try{const r=await (await api('/api/admin/routing')).json();
  $('routetable').innerHTML='<table>'+r.groups.map(g=>`<tr><td style="width:150px"><b>${esc(g.label)}</b><br><code>${esc(g.name)}</code></td><td>${esc(g.words.join(', '))}${g.own.length?`<br><span class="ok">${esc(t('Eigene','Own'))}: ${esc(g.own.join(', '))}</span>`:''}<br><span class="mut">${esc(t('Werkzeuge','Tools'))}: ${esc(g.tools.join(', '))}</span></td></tr>`).join('')+'</table>'
  +`<div class="mut">${esc(t('Immer dabei','Always kept'))}: ${esc(r.keep.join(', '))}</div>`}catch(e){$('routetable').textContent=e.message}}
if($('routerules'))$('routerules').ontoggle=()=>{if($('routerules').open)routeLoad()};
if($('routego'))$('routego').onclick=async()=>{const text=$('routetext').value.trim();if(!text)return;$('routego').disabled=true;
  try{const r=await (await api('/api/admin/routing/test',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({text})})).json();
    const why=Object.entries(r.why).map(([k,v])=>`${k}: „${v}“`).join(', ');
    $('routeout').innerHTML=`<b>${esc(r.clear?r.intent:t('unklar: alle Werkzeuge wie bisher','unclear: all tools as before'))}</b>`
      +(why?` · ${esc(t('Grund','Reason'))} ${esc(why)}`:'')+(r.tools.length?`<br>${esc(t('Werkzeuge','Tools'))}: ${esc(r.tools.join(', '))}`:'')
      +(r.refers?`<br>${esc(t('Zeigt auf die Antwort davor (nach Fremdtext bleibt gesperrt).','Points at the answer before (stays locked after outside text).'))}`:'')}
  catch(e){$('routeout').innerHTML=`<span class="err">${esc(e.message)}</span>`}$('routego').disabled=false};
if($('visiongo'))$('visiongo').onclick=async()=>{$('visiongo').disabled=true;$('visionmsg').textContent=t('prüft …','checking …');
  try{visionShow((await (await api('/api/admin/vision-test',{method:'POST'})).json()).last)}catch(e){$('visionmsg').innerHTML=`<span class="err">${esc(e.message)}</span>`}$('visiongo').disabled=false};
