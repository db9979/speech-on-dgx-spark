// Admin pages: monitoring, settings, tests, voices, logs, guides, system and the update lock.
const btns=(n,st)=>`<button class="b" ${onAttr('act',n,'restart')}>${t('Neustart','Restart')}</button>`+(st==='active'||st==='activating'?`<button class="b" ${onAttr('act',n,'stop')}>${t('Stopp','Stop')}</button>`:`<button class="b" ${onAttr('act',n,'start')}>Start</button>`);
async function act(n,a,btn){btn.disabled=true;try{await api(`/api/service/${n}/${a}`,{method:'POST'})}catch(e){alert(e.message)}btn.disabled=false;refresh()}
window.act=act;ON.act=(b,n,a)=>act(n,a,b);ON.copyPrev=b=>copyString(b.previousElementSibling.textContent,b);

// every 3 s while Zustand is open, else every 30 s (the dot beside Zustand in the menu); nothing while the update window
// is open. Tables are written only when their content changed, so marking, focus and hover stay (setHtml, base.js).
let REFRESH_AT=0;
// Zustand opened (or the tab back in front): at once, not up to 3 s later
if($('mon')){let was=false;new MutationObserver(()=>{const on=$('mon').classList.contains('on');if(on&&!was&&ADMIN){REFRESH_AT=0;refresh();zPollNow()}was=on}).observe($('mon'),{attributes:true,attributeFilter:['class']})}
document.addEventListener('visibilitychange',()=>{if(!document.hidden&&ADMIN&&zSeen()){REFRESH_AT=0;refresh();zPollNow()}});
// The cards on Zustand (Hört gerade zu, Dienste, NAS, Verbrauch …) ask the panel only while Zustand is seen, all at
// once when it opens, then each at its own pace. At the start on the assistant they asked 13 times for nothing
// (V01.0.749). The dot beside Zustand in the menu comes from refresh(), not from these cards.
const ZPOLL=[];
const zSeen=()=>!!$('mon')&&$('mon').classList.contains('on')&&!document.hidden;
function zPollNow(){for(const [f] of ZPOLL)f()}
function zPoll(list){for(const [n,ms] of list){const f=window[n];if(typeof f!=='function')continue;ZPOLL.push([f,ms]);setInterval(()=>{if(zSeen())f()},ms)}
  if(zSeen())zPollNow()}
async function refresh(){const seen=$('mon')&&$('mon').classList.contains('on')&&!document.hidden;
  if(updBusy()||!seen&&Date.now()-REFRESH_AT<30e3)return;REFRESH_AT=Date.now();
  let s;try{s=await (await api('/api/status')).json()}catch(e){$('hdr').textContent=t('Panel nicht erreichbar','Panel not reachable');return}
  const g=s.gpu||{},sy=s.system,H=s.history;
  $('hdr').textContent=(g.name||t('keine GPU','no GPU'))+' · '+new Date(s.time*1000).toLocaleTimeString();
  $('m-gpu').textContent=fmt(g.util,' %');$('m-mem').textContent=fmt(sy.mem_avail_gib,' GiB',1)+' / '+(sy.mem_total_gib??'–');
  $('m-temp').textContent=fmt(g.temp,' °C')+' · '+fmt(g.power,' W');$('m-cpu').textContent=fmt(sy.cpu,' %');
  spark($('c-gpu'),H.map(x=>x.gpu),100);spark($('c-mem'),H.map(x=>x.avail),sy.mem_total_gib);spark($('c-temp'),H.map(x=>x.temp),100);spark($('c-cpu'),H.map(x=>x.cpu),100);
  showAlerts(s.alerts);zustand(s);if(typeof loadSecGlance==='function')loadSecGlance();
  setHtml($('memnote'),sy.mem_avail_gib!=null&&sy.mem_avail_gib<12&&!(s.alerts||[]).some(x=>x.kind==='memory')?`<div class="note">${t(`Nur noch ${fmt(sy.mem_avail_gib,' GiB',1)} frei. Unter ~8 GiB beendet DGX OS (earlyoom) Prozesse. Kleinere Modelle wählen oder einen Dienst stoppen.`,`Only ${fmt(sy.mem_avail_gib,' GiB',1)} free. Below ~8 GiB DGX OS (earlyoom) kills processes. Choose smaller models or stop a service.`)}</div>`:'');
  setHtml($('svc'),Object.entries(s.services).map(([n,v])=>{const h=v.health||{};
    const st=h.status?pill(h.status):'';const err=h.error?`<div class="err">${esc(h.error)}</div>`:(h.last_error?`<div class="err mut">${t('letzter Fehler','last error')}: ${esc(h.last_error.error)}</div>`:'');
    return `<tr><td><b>${n.toUpperCase()}</b><div class="mut">:${v.port}</div></td><td>${pill(v.state)} ${st}${v.enabled?'':` <span class="pill">${t('deaktiviert','disabled')}</span>`}</td>
    <td>${esc(h.model||'')}<div class="mut">${v.estimate_gib!=null?`${t('geschätzt','estimated')} ~${v.estimate_gib} GiB`:''}${h.load_seconds?` · ${t('geladen in','loaded in')} ${h.load_seconds}s`:''}</div>${err}</td>
    <td>${h.requests??'–'}${h.failures?` <span class="err">(${h.failures} ${t('Fehler','errors')})</span>`:''}${h.busy?` <span class="pill warn">${t('arbeitet','busy')}</span>`:''}</td>
    <td>${fmt(h.avg_latency_s,' s',2)}</td><td>${fmt(h.avg_ttfa_s??h.avg_ttft_s,' s',2)}${h.streams?`<div class="mut">${h.streams} Streams</div>`:''}</td><td>${fmt(h.avg_rtf,'',2)}</td><td>${fmt(h.torch_cuda_reserved_gb,' GB',1)}</td>
    <td class="row">${btns(n,v.state)}</td></tr>`+(v.engines||[]).map(e=>`<tr><td class="mut" style="padding-left:20px">↳ ${e.name==='tts-design'?'VoiceDesign-Engine':'Engine'}<div>127.0.0.1:${e.port}</div></td><td>${pill(e.state)}</td>
    <td>${esc(e.model)}<div class="mut">${e.kind}${e.estimate_gib!=null?` · ${t('reserviert','reserves')} ~${e.estimate_gib} GiB`:''}</div></td><td colspan=5></td><td class="row">${btns(e.name,e.state)}</td></tr>`).join('')}).join(''));
  $('q38none').style.display=s.qwen38.length?'none':'block';
  setHtml($('q38'),s.qwen38.map(q=>`<tr><td>${esc(q.unit)}</td><td>${pill(q.state)}</td><td>${q.mem_fraction!=null?(q.mem_fraction*100).toFixed(0)+t(' % des Pools',' % of the pool'):'–'}</td></tr>`).join(''));
  setHtml($('gp'),(g.processes||[]).map(p=>`<tr><td>${esc(p.pid)}</td><td>${esc(p.name)}</td><td>${p.mem_mib!=null?fmt(p.mem_mib/1024,' GiB',1):'–'}</td></tr>`).join('')||'<tr><td class="mut" colspan=3>–</td></tr>');
}

// Zustand (design „Klar“, V01.0.146): one sentence on top (all fine / what is wrong) and "Braucht dich" with
// what waits for the admin, each with a button to the place; the dot next to "Zustand" in the menus follows it.
// Built only from what the page already fetched (services, alerts, memory, update, unsaved settings pages).
const SVCNAME={asr:t('Spracherkennung','Speech recognition'),tts:t('Sprachausgabe','Speech output'),wyoming:'Wyoming'};
let ZLAST=null;
function zustand(s){if(s)ZLAST=s;s=ZLAST;if(!s)return;
  const need=[],bad=[],aus=[],sy=s.system||{};
  for(const [n,v] of Object.entries(s.services||{})){const h=v.health||{},name=SVCNAME[n]||n.toUpperCase();
    if(['failed','error'].includes(v.state)||h.error)bad.push(name);
    else if(v.enabled&&['inactive','deactivating'].includes(v.state)){aus.push(name);need.push({lvl:'bad',text:t(`${name} ist aus.`,`${name} is off.`),go:'svc',btn:t('Ansehen','View')})}}
  for(const n of bad)need.push({lvl:'bad',text:t(`${n} meldet einen Fehler.`,`${n} reports an error.`),go:'svc',btn:t('Ansehen','View')});
  const u=window.UPD;if(u&&u.behind&&u.behind!==0)need.push({lvl:'warn',text:t('Update bereit','Update ready')+(u.version?': '+u.version:'')+'.',go:'sys',btn:t('Zum Update','To the update')});
  // running = systemd says active or the service itself answers; neither = no answer (counts as "needs you")
  const ok=([,v])=>v.state==='active'||['ready','ok'].includes((v.health||{}).status),nm=([n])=>SVCNAME[n]||n.toUpperCase();
  const all=Object.entries(s.services||{}).filter(e=>!bad.includes(nm(e))),run=all.filter(ok).map(nm),unk=all.filter(e=>!ok(e)&&e[1].enabled!==false).map(nm);
  const low=sy.mem_avail_gib!=null&&sy.mem_avail_gib<12;
  // services without an answer before advice and unsaved pages (code check 19.10. D2); one line per service
  for(const n of unk)if(!aus.includes(n))need.push({lvl:'warn',text:t(`${n} antwortet nicht.`,`${n} does not answer.`),go:'svc',btn:t('Ansehen','View')});
  // red points of "Sicherheit auf einen Blick" (secglance.js): advice, never "something is not running" (code check 19.10. D2)
  if(typeof SECNEED!=='undefined')need.push(...SECNEED.map(x=>({...x,lvl:'warn'})));
  const dirty=[...document.querySelectorAll('.pane.dirty')].map(p=>{const b=document.querySelector(`#cfgnav button[data-p="${p.id.slice(5)}"]`);return b?b.firstChild.nodeValue.trim():p.id});
  if(dirty.length)need.push({lvl:'warn',text:t(`Nicht gespeichert: ${dirty.join(', ')}.`,`Not saved: ${dirty.join(', ')}.`),go:'cfg',btn:t('Öffnen','Open')});
  const al=(s.alerts||[]).filter(x=>x.level!=='info'),lvl=bad.length||need.some(x=>x.lvl==='bad')||al.some(x=>x.level==='bad')?'bad':need.length||unk.length||low||al.length?'warn':'ok';
  $('ztitle').textContent=lvl==='ok'?t('Alles läuft.','Everything is running.'):lvl==='bad'?t('Etwas läuft nicht.','Something is not running.'):!run.length&&unk.length?t('Die Dienste melden sich nicht.','The services do not answer.'):t('Läuft, aber etwas braucht dich.','Running, but something needs you.');
  $('ztext').textContent=(bad.length?t('Fehler: ','Errors: ')+bad.join(', ')+'. ':'')+(run.length?run.join(t(' und ',' and '))+(run.length>1?t(' laufen. ',' are running. '):t(' läuft. ',' is running. ')):'')+(unk.length?t('Ohne Rückmeldung: ','No answer from: ')+unk.join(', ')+'. ':'')
    +(sy.mem_avail_gib!=null?t(`${fmt(sy.mem_avail_gib,' GiB',1)} Speicher frei`,`${fmt(sy.mem_avail_gib,' GiB',1)} memory free`)+(low?t(' (wenig)',' (low)'):'')+'.':'')+(al.length?' ':'');
  // the notes above, one tap away (they hold the way to the place each is about)
  if(al.length){const a=document.createElement('a');a.href='#';a.className='wayl';a.textContent=t('Hinweise stehen oben.','Notes are shown above.');
    a.onclick=e=>{e.preventDefault();const f=$('alerts').querySelector('details.afold');if(f)f.open=true;const n=$('alerts').firstElementChild;if(n)sFlash(n)};$('ztext').appendChild(a)}
  zCards(s);$('zhead').dataset.lvl=lvl;$('zicon').textContent=lvl==='ok'?'✓':'!';$('zgo').hidden=!need.length;
  document.querySelectorAll('.hdot').forEach(d=>d.className='hdot '+lvl);
  $('zneed').hidden=!need.length;const L=$('zlist');L.textContent='';
  for(const x of need){const r=document.createElement('div');r.className='zrow';const sp=document.createElement('span');sp.className='pill '+x.lvl;sp.textContent=x.lvl==='bad'?t('Fehler','Error'):t('Offen','Open');
    const tx=document.createElement('span');tx.textContent=x.text;const b=document.createElement('button');b.type='button';b.className='b';b.textContent=x.btn;
    b.onclick=()=>{if(x.go.startsWith('sec:'))secGo(x.go.slice(4));else if(x.go==='svc')zTech('svc');else if(x.go==='cfg'){const d=document.querySelector('.pane.dirty');goSec(d&&d.id==='pane-feat'?'feat':'cfg');if(d){const nb=document.querySelector(`#cfgnav button[data-p="${d.id.slice(5)}"]`);if(nb)nb.click()}}else goSec(x.go)};
    r.append(sp,tx,b);L.appendChild(r)}}
window.zustand=zustand;
// Zustand in plain words (plan „Bedienung gesamt“ C3, V01.0.286; tiles since the plan „Zustand-Übersicht“ 1): under
// the sentence chips with version, last backup and last check; „Jetzt“ four tiles Zuhören, Sprechen, Sprachmodell,
// Speicher (with the 8 GiB line below which DGX OS ends processes); „Heute“ tiles for answers, first sound, speakers
// online and background work that waited for speech, each one a jump link to its place; the other cards below as
// „Bereiche“ with an icon. The service table, GPU and qwen38 stay complete under "Technische Details". From
// /api/status (admin.glance); the colours come from fixed rules there and here, never from the model.
const zAgo=s=>{if(!s)return t('noch nie','never');const m=Math.round((Date.now()/1e3-s)/60);return m<1?t('gerade eben','just now'):m<90?(L==='en'?m+' min ago':'vor '+m+' Min.'):m<2880?(L==='en'?Math.round(m/60)+' h ago':'vor '+Math.round(m/60)+' Std.'):(L==='en'?Math.round(m/1440)+' days ago':'vor '+Math.round(m/1440)+' Tagen')};
function zTech(id){const d=$('ztech');d.open=true;const el=id&&$(id);(el?el.closest('.card'):d).scrollIntoView({behavior:'smooth',block:'start'})}
// line icons (24 grid) of the tiles and of the cards under Zustand; a card without one shows none
const ZCARD_ICO={zneed:'alert',zroom:'ear',zbg:'user',zsvc:'globe',zoffline:'globe',zwart:'pause',znas:'nas',znaszustand:'nas',znasquelle:'folder',zverbrauch:'bars',zstore:'copy',zdev:'dev',zdocs:'doc'};
function zIco(name,cls){return icNode(name,cls||'zico')}   // icons.js
for(const [id,ic] of Object.entries(ZCARD_ICO)){const h=document.querySelector('#'+id+'>h2');if(h){const b=document.createElement('span');b.className='zbub';b.appendChild(zIco(ic));h.prepend(b)}}
$('zgo').onclick=()=>sFlash($('zneed'));
// one tile: icon, name, big value (+unit), one small line; a button (go) or a jump link (way) or nothing
function zCard(lvl,ic,name,big,unit,small,go,way){const b=way?wayEl('',way):document.createElement(go?'button':'div');b.textContent='';
  if(go){b.type='button';b.onclick=go}b.classList.add('zcard');b.dataset.lvl=lvl;
  const hd=document.createElement('span');hd.className='zhd';const bub=document.createElement('span');bub.className='zbub';bub.appendChild(zIco(ic));
  const k=document.createElement('span');k.className='zk';k.textContent=name;hd.append(bub,k);if(go||way)hd.appendChild(zIco('chev','zch'));
  const v=document.createElement('b');v.textContent=big;if(unit){const u=document.createElement('small');u.className='zu';u.textContent=unit;v.appendChild(u)}b.append(hd,v);
  if(small){const m=document.createElement('small');m.textContent=small;b.appendChild(m)}return b}
// the wide „Heute“ tile: answers per hour of the last 24 hours (admin.glance hours, oldest first, the running hour
// last) as bars, with the hour under every sixth bar; a jump link to the requests like the answers tile
function zDay(hrs,way){const b=zCard('acc','bars',t('Antworten pro Stunde','Answers per hour'),'','','',null,way);b.classList.add('zwide');b.querySelector('b').remove();
  const sum=hrs.reduce((a,x)=>a+x,0),max=Math.max(...hrs),now=Date.now(),hh=i=>String(new Date(now-(23-i)*3600e3).getHours()).padStart(2,'0');
  b.setAttribute('aria-label',L==='en'?sum+' answers in the last 24 hours':sum+' Antworten in den letzten 24 Stunden');
  const bars=document.createElement('span');bars.className='zbars';
  hrs.forEach((x,i)=>{const e=document.createElement('i');if(!x)e.className='z';e.style.height=(x?Math.max(8,Math.round(100*x/max)):3)+'%';e.title=hh(i)+(L==='en'?' h: ':' Uhr: ')+x;bars.appendChild(e)});
  const ax=document.createElement('span');ax.className='zax';
  for(const i of [0,6,12,18]){const e=document.createElement('span');e.textContent=hh(i)+(L==='en'?':00':' Uhr');ax.appendChild(e)}
  const e=document.createElement('span');e.textContent=t('jetzt','now');ax.appendChild(e);b.append(bars,ax);return b}
function zSvc(v){if(!v)return['',t('nicht eingerichtet','not set up')];const h=v.health||{};
  if(['failed','error'].includes(v.state)||h.error)return['bad',t('Fehler','Error')];
  if(v.state==='active'||['ready','ok'].includes(h.status))return['ok',h.busy?t('arbeitet','working'):t('läuft','running')];
  if(v.enabled===false)return['',t('ausgeschaltet','switched off')];
  return v.state==='activating'?['warn',t('startet','starting')]:['inactive','deactivating'].includes(v.state)?['bad',t('aus','off')]:['warn',t('keine Antwort','no answer')]}
function zCards(s){const box=$('zcards');if(!box)return;const g=s.glance||{},sv=s.services||{},sy=s.system||{};box.textContent='';
  const short=m=>String(m||'').split('/').pop();
  const a=sv.asr,ah=(a&&a.health)||{},[al,at]=zSvc(a);
  box.appendChild(zCard(al,'ear',t('Zuhören','Listening'),at,'',[short(ah.model),ah.avg_latency_s!=null?t('Ø ','avg ')+fmt(ah.avg_latency_s,' s',1):''].filter(Boolean).join(' · '),()=>zTech('svc')));
  const p=sv.tts,ph=(p&&p.health)||{},[pl,pt]=zSvc(p),ft=ph.avg_ttfa_s??ph.avg_ttft_s;
  box.appendChild(zCard(pl,'spk',t('Sprechen','Speaking'),pt,'',[short(ph.model),ft!=null?t('erster Ton Ø ','first sound avg ')+fmt(ft,' s',1):''].filter(Boolean).join(' · '),()=>zTech('svc')));
  const c=g.check||{};
  box.appendChild(zCard(c.llm===true?'ok':c.llm===false?'bad':'','llm',t('Sprachmodell','Language model'),c.llm===true?t('antwortet','answers'):c.llm===false?t('antwortet nicht','does not answer'):t('noch nicht geprüft','not checked yet'),'',
    c.time?t('geprüft ','checked ')+zAgo(c.time)+(c.seconds!=null?' · '+fmt(c.seconds,' s',1):''):t('Prüfen startet die Funktionsprüfung','Checks runs the function check'),()=>goSec('test')));
  const free=sy.mem_avail_gib,tot=sy.mem_total_gib,ml=free==null?'':free<8?'bad':free<12?'warn':'ok';
  const R=(s.rechner&&s.rechner.an&&s.rechner.liste)||[],rm=R.find(x=>x.id==='modell'),rp=R.find(x=>x.id==='panel'),rg=(rm&&rm.gpu)||{};
  const mc=rm?zCard(zWorst(ml,rm.stufe),'mem',zRName(rm),free==null?'–':fmt(free,'',1),free==null?'':t(' GiB frei',' GiB free'),
      ['GPU '+fmt(rg.util,' %'),fmt(rg.temp,' °C'),'CPU '+fmt(rm.cpu,' %')].join(' · '),zRGo)
    :zCard(ml,'mem',t('Speicher','Memory'),free==null?'–':fmt(free,'',1),free==null?'':t(' GiB frei',' GiB free'),t('Grenze 8 GiB: darunter beendet DGX OS Prozesse','Limit 8 GiB: below it DGX OS ends processes'),()=>zTech('c-mem'));
  if(free!=null&&tot){const bar=document.createElement('span');bar.className='zbar';const f=document.createElement('i');f.style.width=Math.max(2,Math.min(100,Math.round(100*free/tot)))+'%';
    const line=document.createElement('em');line.style.left=Math.min(100,Math.round(100*8/tot))+'%';bar.append(f,line);mc.appendChild(bar)}
  box.appendChild(mc);
  if(rp)box.appendChild(zRTile(rp));
  box.classList.toggle('z5',!!rp);zRechner(R);zRund(s.rundlauf||{});zFern(s.fernzugang||{});
  const meta=$('zmeta');meta.textContent='';
  for(const x of [g.version,t('Sicherung ','Backup ')+zAgo(g.backup),c.time?t('Prüfung ','Check ')+zAgo(c.time):''].filter(Boolean)){const sp=document.createElement('span');sp.textContent=x;meta.appendChild(sp)}
  // „Heute“: each tile opens where its number comes from (way.js wayFirst): the requests, the own speakers, the logs
  const bg=g.background||{},tb=$('ztoday'),sk=g.speakers;tb.textContent='';
  const req=wayFirst(t('Zustand → Logs → Anfragen','Status → Logs → Requests'));
  const hrs=Array.isArray(g.hours)&&g.hours.length===24?g.hours:null;
  if(hrs&&hrs.some(x=>x>0))tb.appendChild(zDay(hrs,req));
  tb.appendChild(zCard('acc','chat',t('Antworten','Answers'),String(g.answers||0),'',g.answers?t('ansehen unter Logs','see them in the logs'):t('noch keine Antwort','no answer yet'),null,req));
  const ak=g.aktiv;   // people with a request in the last 10 minutes (aktiv.py), as on the case's display
  if(ak)tb.appendChild(zCard(ak.gesamt?'ok':'','user',t('Aktiv (10 min)','Active (10 min)'),String(ak.gesamt||0),'',
    t(`${ak.profile||0} Profile · ${ak.gaeste||0} Gäste`,`${ak.profile||0} profiles · ${ak.gaeste||0} guests`)));
  if(g.first_sound!=null)tb.appendChild(zCard(g.slower?'warn':'acc','timer',t('Erster Ton','First sound'),fmt(g.first_sound,'',1),' s',
    g.slower?t('langsamer als sonst','slower than usual'):t('im Mittel','median'),null,req));
  if(sk)tb.appendChild(zCard(!sk.known?'':sk.online<sk.known?'warn':'ok','esp',t('Lautsprecher','Speakers'),String(sk.online),t(' von ',' of ')+sk.known+t(' online',' online'),
    sk.known&&!sk.online?t('keiner erreichbar','none reachable'):sk.online<sk.known?t('nicht alle erreichbar','not all reachable'):t('alle erreichbar','all reachable'),null,
    wayFirst(t('Ich → Lautsprecher','Me → Speakers'),t('Funktionen → Eigene Lautsprecher (ESP32)','Features → Own speakers (ESP32)'))));
  if(bg.held)tb.appendChild(zCard('acc2','pulse',t('Hintergrund','Background'),String(bg.held),t('× gewartet','× waited'),t('auf Sprache gewartet','waited for speech'),null,wayFirst(t('Zustand → Logs','Status → Logs'))));
  tb.hidden=$('ztodayh').hidden=false}
// Zustand → Überblick → Rechner (rechnerblick.py, Dominik 2026-10-16): with the models on another computer both
// computers side by side, a tile each in „Jetzt“ and a card each under „Rechner“ with curves of the last 20 minutes.
// Level and warnings come from fixed rules in rechnerblick.py; a model computer that does not answer keeps its card,
// red and with its last values greyed out. Numbers and fixed words only (no address, no process).
// „Wer rechnet gerade“ (Dominik 2026-10-18 „1a 2a 3a 4b“): services by their share of the CPU (the panel with its parts),
// the biggest in the tile, the strip of who worked most in the last 20 minutes; names (de/en) only from rechnerblick.py.
// Since 2026-10-20 (Spiegel-Karten) the list stands still: rechnerblick.wer gives always the same lines in a fixed order
// (a resting service at 0 % in grey, an empty place kept), the rest, the panel's line „darin“, the strip and its legend
// always, the legend on one line.
const zNm=x=>x?(L==='en'?x.en:x.name)||x.name||'':'';
const ZR_FARBE=['#3b6fd8','#0d9488','#7c3aed','#d97706','#db2777','#65a30d','#0891b2','#9333ea'];
function zRFarben(c){const f={},W=c.wer||{};let i=0;const add=id=>{if(id&&!(id in f))f[id]=ZR_FARBE[i++%ZR_FARBE.length]};
  for(const x of W.zeilen||[])if(x)add(x.id);for(const y of W.darin||[])add('panel/'+y.id);
  for(const id of (c.kurven||{}).top||[])add(id);return f}
function zRWer(c){const W=c.wer||{},T=((c.kurven||{}).top||[]),f=zRFarben(c);
  const r=document.createElement('div');r.className='zrrow zrwer';const w=document.createElement('div'),k=document.createElement('small');
  k.textContent=t('Wer rechnet gerade','Who is computing now');w.appendChild(k);
  const line=(x,col,wort)=>{const l=document.createElement('div');l.className='zrl'+(x&&x.pct?'':wort?' zr0':x?' zr0':' zrleer');
    const n=document.createElement('span');n.textContent=x?zNm(x):wort||'·';
    const b=document.createElement('span');b.className='zrb';const i=document.createElement('i');
    if(x&&x.pct){i.style.width=Math.max(1,Math.min(100,Math.round(100*x.pct/Math.max(1,c.cpu||0))))+'%';i.style.background=col||'var(--mut)'}
    b.appendChild(i);const p=document.createElement('span');p.className='p';p.textContent=x&&x.pct?fmt(x.pct,' %',x.pct<1?1:0):'–';l.append(n,b,p);w.appendChild(l)};
  const Z=W.zeilen||[null],da=Z.filter(Boolean);   // the services, the rest, then the empty places (the card keeps its height)
  const darin=()=>{const d=document.createElement('small');d.className='zrdarin';const D=W.darin||[];   // the panel's parts, one line under it
    d.textContent=t('darin: ','inside: ')+(D.length?D.map(y=>zNm(y)+' '+fmt(y.pct,' %',y.pct<1?1:0)).join(' · '):'–');d.title=d.textContent;w.appendChild(d)};
  for(const x of da){line(x,f[x.id]);if(c.id==='panel'&&x.id==='panel')darin()}
  if(c.id==='panel'&&!da.some(x=>x.id==='panel'))darin();
  line(W.rest||{id:'rest',name:'System und Rest',en:'System and rest',pct:0},'#94a3b8');
  Z.slice(da.length).forEach((x,j)=>line(null,'',!j&&!W.gemessen?t('wird gemessen …','being measured …'):''));
  const h=document.createElement('small');h.textContent=t('Wer am meisten rechnete (20 min)','Who computed most (20 min)');
  const st=document.createElement('div');st.className='zrstrip';st.setAttribute('aria-hidden','true');
  for(const id of T){const i=document.createElement('i');if(id)i.style.background=f[id];st.appendChild(i)}
  const lg=document.createElement('div');lg.className='zrleg zr1';const N=c.namen||{};
  const g=document.createElement('span');g.textContent=t('grau = Leerlauf (unter 5 %)','grey = idle (below 5 %)');lg.appendChild(g);
  for(const id of [...new Set(T.filter(Boolean))]){const s2=document.createElement('span'),q=document.createElement('i');q.style.background=f[id];
    s2.append(q,zNm({name:(N[id]||[id])[0],en:(N[id]||[id,id])[1]}));lg.appendChild(s2)}
  w.append(h,st,lg);r.appendChild(w);return r}
const ZR_STROM={ok:'ok','zu niedrig':t('Spannung zu niedrig','voltage too low'),'war niedrig':t('Spannung war niedrig','voltage was low'),
  nein:t('nie gedrosselt','never throttled'),jetzt:t('drosselt gerade','throttling now'),'war an':t('war gedrosselt','was throttled')};
const zRRole=c=>c.id==='modell'?t('Modell-Rechner','Model computer'):t('Panel-Rechner','Panel computer');
const zRName=c=>c.name?c.name+' · '+zRRole(c):zRRole(c);
const zWorst=(...a)=>a.includes('bad')?'bad':a.includes('warn')?'warn':a.includes('ok')?'ok':'';
const zRGo=()=>{const h=$('zrechnerh');if(h)h.scrollIntoView({behavior:'smooth',block:'start'})};
const zDur=s=>s==null?'–':s>=86400?Math.floor(s/86400)+t(' T ',' d ')+Math.floor(s%86400/3600)+t(' Std.',' h'):s>=3600?Math.floor(s/3600)+t(' Std. ',' h ')+Math.floor(s%3600/60)+' min':Math.max(1,Math.round(s/60))+' min';
const zUsed=c=>c.ram_total!=null&&c.ram_frei!=null?c.ram_total-c.ram_frei:null;
function zRTile(c){const bel=zUsed(c);
  const b=zCard(c.stufe,'mem',zRName(c),bel==null?'–':fmt(bel,'',1),bel==null?'':t(' GiB belegt',' GiB used'),
    ['CPU '+fmt(c.cpu,' %'),c.temp!=null?fmt(c.temp,' °C'):'',c.platte_pct!=null?t('Platte ','Disk ')+fmt(c.platte_pct,' %'):'',
     c.spitze?t('am meisten: ','most: ')+zNm(c.spitze)+' '+fmt(c.spitze.pct,' %'):(c.wer||{}).gemessen?t('Leerlauf','idle'):''].filter(Boolean).join(' · '),zRGo);
  if(bel!=null&&c.ram_total){const bar=document.createElement('span');bar.className='zbar';const f=document.createElement('i');
    f.style.width=Math.max(2,Math.min(100,Math.round(100*bel/c.ram_total)))+'%';bar.appendChild(f);b.appendChild(bar)}
  return b}
// Spiegel-Karten (Dominik 2026-10-20 „so umsetzen“, plan rechner-karten/plan.md): both cards have the same rows in the
// same order, each on the height of its neighbour (CSS subgrid in #zrechner, also two columns on the phone): CPU,
// Speicher (always free), GPU, Temperatur, Platte, Netz, the computer's own row (Sprachmodell / Panel hing with Strom),
// Wer rechnet gerade, Dienste. What a computer lacks shows „–“; a curve row keeps its curve even before two values.
const ZR_ZEILEN=11;   // h2, the line below it and the nine rows: #zrechner's subgrid spans them (--zrz in app.css)
function zRCard(c){const card=document.createElement('div');card.className='card zrcard';card.dataset.lvl=c.stufe;card.dataset.id=c.id;
  const stale=c.id==='modell'&&!c.ok;card.classList.toggle('zrstale',stale);
  const h=document.createElement('h2'),nm=document.createElement('span'),pl=document.createElement('span');nm.textContent=zRName(c);
  pl.className='pill '+(c.stufe||'');pl.textContent=stale?t('antwortet nicht','not answering')+(c.stumm_s!=null?t(' seit ',' for ')+zDur(c.stumm_s):''):c.stufe==='ok'?t('alles gut','all good'):c.stufe==='bad'?t('Fehler','Error'):t('Hinweis','Note');
  h.append(nm,pl);const meta=document.createElement('div');meta.className='mut zrmeta';
  meta.textContent=[c.geraet,c.system,c.laeuft_s!=null?t('läuft seit ','up ')+zDur(c.laeuft_s):'',c.version].filter(Boolean).join(' · ');card.append(h,meta);
  const K=c.kurven||{},hw=c.hinweise||[],g=c.gpu||{},modell=c.id==='modell';
  const row=(k,big,small,curve,max,lvl,cls)=>{const r=document.createElement('div');r.className='zrrow'+(cls?' '+cls:'');const tx=document.createElement('div');
    const kk=document.createElement('small');kk.textContent=k;const b=document.createElement('b');b.textContent=big;tx.append(kk,b);
    b.title=big;const sm=document.createElement('small');sm.textContent=small||'\u00a0';sm.title=small||'';tx.appendChild(sm);r.appendChild(tx);
    if(curve){const v=document.createElementNS('http://www.w3.org/2000/svg','svg');v.setAttribute('class','zrspark');v.setAttribute('aria-hidden','true');spark(v,curve,max);r.appendChild(v)}
    else{const d=document.createElement('span');d.className='zrdot';d.dataset.lvl=lvl||'';r.appendChild(d)}
    card.appendChild(r)};
  row('CPU',fmt(c.cpu,' %'),[c.kerne?c.kerne+t(' Kerne',' cores'):'',c.last!=null?t('Last ','load ')+fmt(c.last,'',2):''].filter(Boolean).join(' · '),K.cpu||[],100);
  const bel=zUsed(c);
  row(t('Speicher','Memory')+(modell?' · Unified Memory':''),c.ram_frei==null?'–':fmt(c.ram_frei,t(' GiB frei',' GiB free'),1),
    [c.ram_total!=null?t('von ','of ')+fmt(c.ram_total,' GiB',1):'',bel!=null?fmt(bel,t(' belegt',' used'),1):'',c.ram_cache!=null?t('Cache ','cache ')+fmt(c.ram_cache,'',1):'',
     c.swap?t('Swap ','swap ')+fmt(c.swap,'',1):'',modell?t('Grenze 8 GiB','limit 8 GiB'):''].filter(Boolean).join(' · '),K.frei||[],c.ram_total);
  if(modell)row('GPU',fmt(g.util,' %'),g.power!=null?fmt(g.power,' W'):'',K.gpu||[],100);
  else row('GPU','–',t('keine GPU','no GPU'),null,null,'','zrna');
  const tp=c.temp??g.temp;
  row(t('Temperatur','Temperature'),fmt(tp,' °C'),(modell?[c.temp!=null&&g.temp!=null?'GPU '+fmt(g.temp,' °C'):'']
    :[c.luefter==null?'':c.luefter?t('Lüfter an','fan on'):t('Lüfter aus','fan off'),c.temp_warn?t('Hinweis ab ','note from ')+c.temp_warn+' °C':'']).filter(Boolean).join(' · '),K.temp||[],100);
  row(t('Platte','Disk'),fmt(c.platte_frei,t(' GB frei',' GB free')),c.platte_total!=null?t('von ','of ')+fmt(c.platte_total,' GB')+' · '+fmt(c.platte_pct,t(' % belegt',' % used')):'',
    null,null,c.platte_pct==null?'':hw.includes('platte_'+c.id)?'warn':'ok');
  row(t('Netz','Network'),!c.netz_mbit?'–':c.netz_mbit>=1000?fmt(c.netz_mbit/1000,' Gbit/s',c.netz_mbit%1000?1:0):fmt(c.netz_mbit,' Mbit/s'),
    `↓ ${fmt(c.netz_rx_mbs,' MB/s',1)} ↑ ${fmt(c.netz_tx_mbs,' MB/s',1)}`,K.netz||[],null);
  if(modell)row(t('Sprachmodell','Language model'),c.llm||t('aus','off'),'',null,null,c.llm?'ok':'');
  else{const hg=c.haenger||{},st=c.strom,bad=!!st&&(st.spannung==='zu niedrig'||st.drossel==='jetzt');   // the Hänge-Wächter (loopwacht.py) and the power
    row(t('Panel hing','Panel stalled'),hg.jetzt_s?t('gerade ','now ')+hg.jetzt_s+' s':(hg.n||0)+t('-mal','×'),
      [hg.n?t('in 24 Std., längstens ','in 24 h, longest ')+hg.max_s+' s':t('in 24 Std. nie','never in 24 h'),
       st?t('Strom ','power ')+(bad?[ZR_STROM[st.spannung],ZR_STROM[st.drossel]].filter(x=>x&&x!=='ok').join(' · '):'ok'):''].filter(Boolean).join(' · '),
      null,null,hg.jetzt_s||bad?'bad':hg.n?'warn':'ok')}
  card.appendChild(zRWer(c));
  const D=c.dienste||[],r=document.createElement('div');r.className='zrrow zrsvc';const k=document.createElement('small');
  // „bereit“ (rechnerblick.ABRUF): a part that starts only for a job and rests now, counted as fine, hollow green dot
  k.textContent=t('Dienste','Services')+' · '+D.filter(x=>x.state==='active'||x.state==='bereit').length+t(' von ',' of ')+D.length+t(' bereit',' ready');
  const w=document.createElement('div');w.className='zrchips';
  for(const x of D){const sp=document.createElement('span');sp.dataset.lvl=x.state==='active'?'ok':x.state==='bereit'?'rest':x.state==='failed'?'bad':x.state==='activating'?'warn':'';
    sp.textContent=zNm(x)||x.id;sp.title=sp.textContent+(x.state==='bereit'?t(' · bereit, startet bei Bedarf',' · ready, starts when needed'):'');w.appendChild(sp)}
  r.append(k,w);card.appendChild(r);
  return card}
// a poll only puts in what changed (Richtlinie 6 „Ruhig, nichts springt“): same cards, same rows, each row that differs
// is swapped in its place; new cards only when the computers change
function zRechner(R){const box=$('zrechner'),h=$('zrechnerh');if(!box)return;box.hidden=h.hidden=!R.length;box.style.setProperty('--zrz',ZR_ZEILEN);
  const neu=R.map(zRCard),alt=[...box.children];
  if(alt.length!==neu.length||alt.some((c,i)=>c.dataset.id!==neu[i].dataset.id)){box.replaceChildren(...neu);return}
  neu.forEach((n,i)=>zRSetzen(alt[i],n))}
function zRSetzen(alt,neu){alt.className=neu.className;alt.dataset.lvl=neu.dataset.lvl;const N=[...neu.children];
  N.forEach((x,i)=>{const a=alt.children[i];if(!a)alt.appendChild(x);else if(!a.isEqualNode(x))a.replaceWith(x)});
  while(alt.children.length>N.length)alt.lastElementChild.remove()}
// Zustand → Überblick → Rundlauf (rundlauf.py, plan verbesserungen 3a): the last real round trip through Sprechen,
// Hören and the language model, each step in ms, the whole way with the curve of the last runs; a step that hakt is
// red with a fixed word. Shown while Funktionen → Dienst-Wächter → Rundlauf prüfen is on. Numbers and fixed words only.
const ZRD_WHY={zeit:t('antwortet nicht rechtzeitig','does not answer in time'),fehler:t('antwortet nicht','does not answer'),stumm:t('liefert keinen Ton','gives no sound'),
  falsch:t('versteht den Satz nicht','does not understand the sentence'),leer:t('antwortet leer','answers empty')};
const ZRD_AUS={start:t('Panel startet','panel starting'),notaus:'Notaus',update:'Update',gespraech:t('Gespräch läuft','conversation going on'),nacht:t('Update-Nacht','update night'),
  wartung:t('Wartungspause','maintenance pause'),bild:t('Bild entsteht','picture being made'),musik:t('Lied entsteht','song being made')};
const zMs=v=>v==null?'–':v>=1000?fmt(v/1000,' s',1):v+' ms';
// Zustand → Überblick → Fernzugang (fernzugang.py): numbers only, red while a remote shell is open
function zFern(F){const box=$('zfern'),h=$('zfernh');if(!box)return;box.hidden=h.hidden=!F.on;box.textContent='';if(!F.on)return;
  const card=document.createElement('div');card.className='card zrcard';card.dataset.lvl=F.hostkey?'bad':F.sitzungen?'warn':'ok';
  const hd=document.createElement('h2'),nm=document.createElement('span'),pl=document.createElement('span');nm.textContent=t('Fern-Server','Remote servers');
  pl.className='pill '+card.dataset.lvl;pl.textContent=F.hostkey?t('Host-Schlüssel falsch','Host key wrong'):F.sitzungen?t('Sitzung offen','Session open'):t('ruhig','quiet');
  hd.append(nm,pl);card.appendChild(hd);
  for(const [k,de,en] of [['gekoppelt','gekoppelt','paired'],['online','online','online'],['sitzungen','offene Sitzungen','open sessions'],['dateien','davon Dateien','of them files'],['uebertragungen','Übertragungen','transfers'],['abbau','warten auf Abbau','waiting for removal']]){
    const r=document.createElement('div');r.className='zrrow';const tx=document.createElement('div'),kk=document.createElement('small'),b=document.createElement('b');
    kk.textContent=t(de,en);b.textContent=String(F[k]||0);tx.append(kk,b);r.appendChild(tx);card.appendChild(r)}
  card.appendChild(wayEl(t('Fernzugang → Systeme','Remote access → Systems'),t('Fernzugang → Systeme','Remote access → Systems')));box.appendChild(card)}
function zRund(R){const box=$('zrund'),h=$('zrundh');if(!box)return;box.hidden=h.hidden=!R.an;box.textContent='';if(!R.an)return;
  const la=R.letzt,st=R.stoerung,card=document.createElement('div');card.className='card zrcard';
  card.dataset.lvl=st?'bad':!la?'':la.ok?(R.langsam||[]).length?'warn':'ok':'warn';
  const hd=document.createElement('h2'),nm=document.createElement('span'),pl=document.createElement('span');nm.textContent=t('Probelauf','Test run');
  pl.className='pill '+card.dataset.lvl;pl.textContent=st?t('Störung','Fault'):!la?t('noch kein Lauf','no run yet'):la.ok?t('kommt durch','gets through'):t('ein Fehler','one error');
  hd.append(nm,pl);const meta=document.createElement('div');meta.className='mut zrmeta';
  meta.textContent=[t('alle ','every ')+R.min+' min',la?t('zuletzt ','last ')+zAgo(la.t):'',R.aus?t('wartet: ','waiting: ')+(ZRD_AUS[R.aus]||R.aus):'',
    t('heute ','today ')+R.heute.ok+' ok'+(R.heute.fehler?' · '+R.heute.fehler+t(' Fehler',' errors'):'')].filter(Boolean).join(' · ');card.append(hd,meta);
  const ms=(la&&la.ms)||{},slow=R.langsam||[];
  for(const [k,de,en] of [['tts','Sprechen','Speaking'],['asr','Hören','Listening'],['llm','Sprachmodell','Language model']]){
    const r=document.createElement('div');r.className='zrrow';const tx=document.createElement('div'),kk=document.createElement('small'),b=document.createElement('b');
    kk.textContent=t(de,en);const bad=la&&!la.ok&&la.step===k;b.textContent=bad?(ZRD_WHY[la.why]||t('Fehler','error')):zMs(ms[k]);tx.append(kk,b);
    if(slow.includes(k)){const sm=document.createElement('small');sm.textContent=t('langsamer als sonst','slower than usual');tx.appendChild(sm)}
    const d=document.createElement('span');d.className='zrdot';d.dataset.lvl=bad?'bad':slow.includes(k)?'warn':ms[k]!=null?'ok':'';r.append(tx,d);card.appendChild(r)}
  const r=document.createElement('div');r.className='zrrow';const tx=document.createElement('div'),kk=document.createElement('small'),b=document.createElement('b');
  kk.textContent=t('Ganzer Weg','Whole way');b.textContent=la&&la.ok?zMs(ms.ganz):'–';tx.append(kk,b);r.appendChild(tx);
  if((R.kurve||[]).filter(x=>x!=null).length>1){const v=document.createElementNS('http://www.w3.org/2000/svg','svg');v.setAttribute('class','zrspark');v.setAttribute('aria-hidden','true');spark(v,R.kurve);r.appendChild(v)}
  card.appendChild(r);box.appendChild(card)}
// Zustand → "Hört gerade zu" (roomlive.py): every device in room mode, of every profile, with Beenden and
// "Alle beenden" (e.g. when guests come). Only where and until when, never what was heard.
async function zRooms(){const box=$('zroom');if(!box||document.hidden)return;let d={rooms:[],waiting:[]};
  try{d=await (await api('/api/admin/rooms',{cache:'no-store'})).json()}catch{return}
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
  try{d=await (await api('/api/admin/wissen',{cache:'no-store'})).json()}catch{return}
  box.hidden=!d.on;if(!d.on)return;const L2=$('zdoclist');L2.textContent='';
  const ago=s=>{if(!s)return t('noch nie','never');const m=Math.round((Date.now()/1e3-s)/60);return m<1?t('gerade eben','just now'):m<90?(L==='en'?m+' min ago':'vor '+m+' Min.'):(L==='en'?Math.round(m/60)+' h ago':'vor '+Math.round(m/60)+' Std.')};
  const row=(cls,pill,title,text)=>{const r=document.createElement('div');r.className='zrow';const sp=document.createElement('span');sp.className='pill '+cls;sp.textContent=pill;
    const tx=document.createElement('span');const b=document.createElement('b');b.textContent=title;tx.append(b,' '+text);r.append(sp,tx);L2.appendChild(r)};
  if(d.semantic&&d.model){const m=d.model;// loaded and working = "arbeitet"; loaded but idle or not loaded = green "Standby" (Dominik 2026-10-12)
    const st=m.state==='ready'&&m.busy?['ok',t('arbeitet','working')]:{ready:['ok',t('Standby','standby')],starting:['warn',t('startet','starting')],waiting:['warn',t('wartet','waiting')],error:['bad',t('Fehler','error')],off:['ok',t('Standby','standby')]}[m.state]||['',m.state];
    const mins=s=>Math.max(1,Math.round((s||0)/60));
    const use=m.used?(m.used==='passage'?t('neue Stücke','new pieces'):t('eine Frage','a question'))+', '+(L==='en'?mins(m.used_ago)+' min ago':'vor '+mins(m.used_ago)+' Min.')+' · ':'';
    let tx=m.state==='ready'?t('geladen','loaded')+' · '+(m.mib?m.mib+' MiB '+t('Arbeitsspeicher','memory')+' · ':'')+(use?t('zuletzt gebraucht für ','last needed for ')+use:'')
      +(typeof m.stop_in==='number'?(L==='en'?'stops in '+mins(m.stop_in)+' min without work':'stoppt in '+mins(m.stop_in)+' Min. ohne Arbeit'):t('stoppt nach ','stops after ')+m.stop_min+t(' Min. ohne Arbeit',' min idle'))
      :m.state==='waiting'?t('braucht ','needs ')+m.need_gib+t(' GiB freien Arbeitsspeicher',' GiB free memory')
      :m.state==='error'?(m.error||''):m.state==='starting'?t('lädt das Modell (beim ersten Mal von Hugging Face)','loading the model (from Hugging Face the first time)')
      :t('nicht geladen, startet, wenn etwas zu tun ist','not loaded, starts when there is work');
    const v=d.vectors;tx+=' · '+v[0]+'/'+v[1]+t(' Stücke mit Bedeutung',' pieces with meaning');
    row(st[0],st[1],t('Bedeutungssuche (CPU-Modell)','Meaning search (CPU model)'),tx)}
  if(d.rank){const m=d.rank,mins=s=>Math.max(1,Math.round((s||0)/60));   // Treffer nachsortieren (nachsortieren.py)
    const st=m.running&&m.busy?['ok',t('arbeitet','working')]:{ready:['ok',t('Standby','standby')],starting:['warn',t('startet','starting')],waiting:['warn',t('wartet','waiting')],error:['bad',t('Fehler','error')],off:['ok',t('Standby','standby')]}[m.state]||['',m.state];
    const tx=(m.state==='ready'?t('geladen','loaded')+(m.mib?' · '+m.mib+' MiB':'')+(typeof m.stop_in==='number'?' · '+(L==='en'?'stops in '+mins(m.stop_in)+' min without work':'stoppt in '+mins(m.stop_in)+' Min. ohne Arbeit'):'')
      :m.state==='waiting'?t('braucht ','needs ')+m.need_gib+t(' GiB freien Arbeitsspeicher',' GiB free memory')
      :m.state==='error'?(m.error||''):m.state==='starting'?t('lädt das Modell (beim ersten Mal von Hugging Face)','loading the model (from Hugging Face the first time)')
      :t('nicht geladen, startet bei der nächsten Dokumentensuche','not loaded, starts with the next document search'))
      +' · '+t('Modell ','model ')+(m.size==='gross'?t('groß','large'):t('klein','small'))+(m.ms?' · '+t('zuletzt ','last ')+m.ms+' ms':'')+' · '+t('höchstens ','at most ')+m.budget+' ms';
    row(st[0],st[1],t('Treffer nachsortieren (CPU-Modell)','Re-rank hits (CPU model)'),tx)}
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
  await setReady();getDefaults=await renderSet($('chatdefaults'),{...SDEF,...(CFG.chat.defaults||{})},null);if(window.faceTiles)faceTiles($('pane-talk'));if(typeof presetMove==='function')presetMove();
  asrRec();cfgDeps();if(typeof guidesCount==='function')guidesCount();if(typeof tgAdmin==='function')tgAdmin();visionLoad();satzendeLoad();bildTestLoad();musikModelLoad();dlLoad();if(typeof nzLoad==='function')nzLoad();if(typeof gehLoad==='function')gehLoad();if(typeof telLoad==='function')telLoad();if(typeof apnsAdmin==='function')apnsAdmin();if(typeof iupdAdmin==='function')iupdAdmin();if(typeof coadmAdmin==='function')coadmAdmin();if(typeof espAdmin==='function')espAdmin();if(typeof andAdmin==='function')andAdmin();if(typeof deskAdmin==='function')deskAdmin();if(typeof agentAdmin==='function')agentAdmin();if(typeof vbAdmin==='function')vbAdmin();document.querySelectorAll('.pane').forEach(p=>markDirty(p,false));document.querySelectorAll('.savemsg').forEach(m=>m.textContent='');glance();glanceLoad();llmModels()}
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
document.querySelectorAll('#cfgnav button').forEach(b=>b.onclick=()=>{cfgPane(b.dataset.p);if(b.dataset.p==='voices')loadClone();if(b.dataset.p==='upd'||b.dataset.p==='bak')loadSys();if(b.dataset.p==='upd')ghAdmin();if(b.dataset.p==='start'){glance();loadSecGlance(true)}if(b.dataset.p==='sysc'&&window.liveMons)liveMons();document.querySelector('.cfgwrap').classList.add('sub');window.scrollTo(0,0)});
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
  // the panel password's second step only with the panel password: an admin profile has its own under Ich → Sicherheit
  await Promise.all([get('/api/clone-voices','voices'),get('/api/backups','bak'),typeof elevated==='function'&&elevated()?(GL.mfa=null):get('/api/mfa','mfa')]);glance()}
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
  if(p==='bak'){const b=((GL.bak||{}).backups||[])[0];
    return {txt:b&&b.created?t('letzte Sicherung ','last backup ')+new Date(b.created*1000).toLocaleString([], {day:'numeric',month:'numeric',hour:'2-digit',minute:'2-digit'}):GL.bak?t('noch keine Sicherung','no backup yet'):'…'}}
  if(p==='upd'){const u=window.UPD||{};const ready=u.behind&&u.behind!==0;
    return {txt:[SPARK_VER,(ready?t('Update bereit','update ready'):u.behind===0?t('aktuell','up to date'):t('Stand unbekannt','state unknown'))].join(' · '),
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
  // switches only for Spark teilen (the models on another computer, models.host not this one): hidden on the all-in-one
  const h=String((CFG&&CFG.models&&CFG.models.host)||'127.0.0.1'),split=!/^(127\.|::1$|localhost$)/.test(h);
  document.querySelectorAll('[data-teilen]').forEach(x=>x.style.display=split?'':'none');
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
  // unsaved functions show at „Funktionen“, the rest at „Einstellungen“ (code check 19.10. D4)
  const n=document.querySelectorAll('.pane.dirty:not(#pane-feat)').length,c=$('dirtycnt');c.hidden=!n;c.textContent=n;
  const f=$('featdirty');if(f)f.hidden=!$('pane-feat').classList.contains('dirty');zustand()};
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
  const n=JSON.parse(JSON.stringify(CFG));// the presets: only those whose row is on this page (two of them sit under Funktionen, fdetail.js presetMove)
  if(getDefaults){const d=getDefaults(),o={...SDEF,...(CFG.chat.defaults||{})};let any=false;
    for(const k of Object.keys(d)){const e=$('set_chatdefaults_'+k);if(e&&pane.contains(e)){o[k]=d[k];any=true}}if(any)n.chat.defaults=o}
  for(const[sec,o]of Object.entries(n))for(const k of Object.keys(o)){const el=$(sec+'.'+k);if(!el||!pane.contains(el))continue;
    o[k]=el.type==='checkbox'?el.checked:el.dataset.list?el.value.split(/[\s,;]+/).filter(Boolean):el.type==='number'||el.dataset.num?Number(el.value):el.value}
  if(pane.contains($('chat.wyoming'))&&$('chat.wyoming').checked&&!$('chat.wyoming_allow').value.trim()){
    const m=t('Wyoming braucht die Adresse deines Home Assistant, z. B. 192.168.1.20 (oder „Adresse von Home Assistant übernehmen“).','Wyoming needs your Home Assistant address, e.g. 192.168.1.20 (or "Take the Home Assistant address").');
    $('wymsg').innerHTML=`<span class="err">${esc(m)}</span>`;msg.innerHTML=`<span class="err">${esc(m)}</span>`;$('chat.wyoming_allow').focus();return}
  msg.textContent=t('Speichere…','Saving…');
  try{const r=await (await api('/api/config',{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify(n)})).json();
    if(pane.contains($('chat.face'))){setFaceSpark(n.chat.face);faceApply();setFaceLife(n.chat.face_life===true)}
    if(typeof hilfeRefresh==='function')hilfeRefresh();   // Funktionen → Hilfe zum Spark: the face follows at once
    if(pane.contains($('chat.fernzugang'))&&window.fzStart)api('/api/whoami').then(r=>r.json()).then(fzStart).catch(()=>{});   // the menu entry Fernzugang follows its switch
    msg.innerHTML=t('Gespeichert.','Saved.')+(r.restarted.length?t(' Neu gestartet: ',' Restarted: ')+r.restarted.join(', ').toUpperCase()+t(' (Modell lädt neu).',' (model reloads).'):'')+(r.stopped&&r.stopped.length?t(' Gestoppt: ',' Stopped: ')+r.stopped.join(', ').toUpperCase()+'.':'')+(r.errors&&r.errors.length?`<div class="err">${esc(r.errors.join('\n'))}</div>`:'')+(r.panel_restart_needed?t(' Panel-Port ändert sich nach: ',' Panel port changes after: ')+'sudo systemctl restart speech-spark-panel':'');CFG=n;markDirty(pane,false);glance();
    sayToast(r.errors&&r.errors.length?t('Gespeichert, mit Fehlern (siehe unten).','Saved, with errors (see below).'):t('Gespeichert.','Saved.'),2500)}   // the bar leaves its floating place: say it where the person looks
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
  catch(e){$('vmsg').innerHTML=`<span class="err">${esc(micError(e))}</span>`;return}
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
  invite_revoked:t('Einladung zurückgezogen','invitation withdrawn'),review_made:t('Prüfzugang erstellt','review access made'),review_used:t('iPhone mit Prüf-Code gekoppelt','iPhone paired with a review code'),review_deleted:t('Prüfzugang gelöscht','review access deleted'),handoff_login:t('Handy über QR-Code angemeldet','phone signed in by QR code'),
  backup:t('Sicherung','backup'),restore:t('Wiederherstellung','restore'),watchdog:t('Wächter','watchdog'),
  audit_chain_broken:t('Änderungsprotokoll nachträglich verändert','change log changed afterwards'),offsite_log_failed:t('Protokoll-Kopie nicht auf den NAS gekommen','log copy did not reach the NAS')};
$('tts.model').addEventListener('change',()=>instrHint(true));


function kv(rows){return rows.map(([k,v])=>`<tr><td class="mut" style="width:40%">${k}</td><td><code>${esc(v)}</code> <button class="b" style="padding:1px 6px;font-size:12px" ${onAttr('copyPrev')}>${t('kopieren','copy')}</button></td></tr>`).join('')}
async function loadInt(){const [c,v]=await Promise.all([api('/api/config').then(r=>r.json()),api('/api/tts/voices').then(r=>r.json())]);   // side by side (seiten-laden.md)
  const host=location.hostname,asr=`http://${host}:${c.asr.port}/v1`,tts=`http://${host}:${c.tts.port}/v1`,key=c.api.key||t('beliebig, z. B. sk-local','anything, e.g. sk-local');
  const voice=c.tts.default_voice||((v.voices||[])[0]||'ryan');
  $('int-ep').innerHTML=kv([[t('Spracherkennung (STT)','Speech recognition (STT)'),asr+'/audio/transcriptions'],[t('Sprachausgabe (TTS)','Speech output (TTS)'),tts+'/audio/speech'],[t('API-Schlüssel','API key'),c.api.key||t('(keiner gesetzt)','(none set)')]]);
  $('int-owui-stt').innerHTML=kv([['Speech-to-Text Engine','OpenAI'],['API Base URL',asr],['API Key',key],['STT Model',c.asr.model]]);
  $('int-owui-tts').innerHTML=kv([['Text-to-Speech Engine','OpenAI'],['API Base URL',tts],['API Key',key],['TTS Model',c.tts.model],['TTS Voice',voice],[t('Zusätzliche TTS-Parameter (JSON, optional)','Additional TTS parameters (JSON, optional)'),JSON.stringify({temperature:c.tts.temperature,top_p:c.tts.top_p,seed:c.tts.seed})],[t('Antwort aufteilen','Response splitting'),t('Absätze (Paragraphs)','Paragraphs')]]);
  const panelUrl=`http://${host}:${(c.panel&&c.panel.port)||31080}`;
  // the download follows this page (B8): served over https, the link is https too (no blocked http link on an https page);
  // the address in the watch app stays plain http, the Pebble app does not trust the self-signed certificate
  const siriBase=location.protocol==='https:'?location.origin:panelUrl;
  $('int-pebble').innerHTML=kv([[t('Spark-Adresse in der Uhr-App','Spark address in the watch app'),panelUrl],[t('App-Datei','App file'),siriBase+'/pebble/speech-spark.pbw']]);
  $('int-pbw').href=siriBase+'/pebble/speech-spark.pbw';
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
  $('sysver').innerHTML=kvp([[t('Installiert','Installed'),i.short?`${i.short} · ${new Date(i.date).toLocaleString()}`:'–'],[t('Änderung','Change'),i.subject||'–'],['Engines',i.engine||'–'],[t('Quelle','Source'),i.remote||'–'],[t('Zuletzt geprüft','Last checked'),r.checked?new Date(r.checked*1000).toLocaleTimeString():'–']].concat(u.modell?[[t('Modell-Rechner','Model computer'),!u.modell.ok?t('nicht erreichbar','not reachable'):(u.modell.version||'–')+(u.modell.update?t(' · Update läuft',' · update running'):u.modell.gleich?t(' · gleiche Version',' · same version'):t(' · andere Version, das nächste Update gleicht an',' · other version, the next update evens it out'))]]:[]).concat(u.umzug?[[t('Nach dem Umzug','After the move'),t('Noch von Hand: im Router die Weiterleitung 31443 und für Anrufe die Ports von Funktionen → Chats → „Anrufe von unterwegs“ auf diesen Rechner; in Home Assistant Wyoming auf diesen Rechner (Funktionen → Home Assistant Assist); bei jedem Lautsprecher die neue Server-Adresse (Funktionen → Eigene Lautsprecher (ESP32)); den Reverse Proxy der Apps (iPhone, Android, Passkeys) auf diesen Rechner zeigen lassen und seine Adresse unter Einstellungen → Sicherheit → Reverse Proxy prüfen.','Still by hand: in the router the forward of 31443 and, for calls, the ports of Features → Chats → "Calls when away" to this computer; in Home Assistant Wyoming to this computer (Features → Home Assistant Assist); on every speaker the new server address (Features → Own speakers (ESP32)); point the reverse proxy of the apps (iPhone, Android, passkeys) to this computer and check its address under Settings → Security → Reverse proxy.')]]:[]));
  updBadge(r);loadBak();
  const pv=u.previous;$('updprevrow').style.display=pv&&!u.running?'flex':'none';
  if(pv)$('updprevtxt').textContent=(pv.version||pv.short||'')+(pv.subject?' · '+pv.subject:'');
  if(u.running){$('updstate').innerHTML=t('<span class="pill warn">Update läuft</span> Die Seite lädt neu, wenn das Panel neu startet.','<span class="pill warn">Update running</span> The page reloads when the panel restarts.');$('updgo').disabled=true;$('updstop').style.display='inline-block';
    if(!updPoll)updPoll=setInterval(()=>{if(!updBusy())loadSys()},3000)}   // the update window shows the progress itself
  else{if(updPoll){clearInterval(updPoll);updPoll=null}$('updstop').style.display='none';
    $('updstate').innerHTML=r.error?`<span class="err">${esc(r.error)}</span>`:r.behind===0?`<span class="pill ok">${t('aktuell','up to date')}</span>`:
      `<span class="pill warn">${t('Update verfügbar','Update available')}</span> ${r.behind>0?r.behind+t(' Änderung(en)',' change(s)'):''}`+(u.last_result&&u.last_result!=='success'&&u.last_finished?` <span class="err">${t('Letztes Update fehlgeschlagen','Last update failed')} (${esc(u.last_result)}), ${t('siehe Protokoll','see log')}.</span>`:'')
      +(r.head&&r.latest&&r.head!==r.latest?` <span class="mut">${r.head_state==='red'?t('Neuere Änderungen sind auf GitHub durch die Tests gefallen und werden nicht angeboten.','Newer changes failed the tests on GitHub and are not offered.')+(r.red_since?' '+t('Rot seit','Red since')+' '+esc(new Date(r.red_since*1000).toLocaleString(L==='en'?'en-GB':'de-DE',{weekday:'short',hour:'2-digit',minute:'2-digit'}))+'.':''):t('Neuere Änderungen werden auf GitHub noch geprüft und erst danach angeboten.','Newer changes are still being tested on GitHub and are offered once they pass.')}</span>`:'');
    $('updgo').disabled=!(r.behind&&r.behind!==0)}
  $('updcommits').innerHTML=(r.commits||[]).length?'<table>'+r.commits.slice().reverse().map(c=>`<tr><td class="mut" style="width:70px"><code>${esc(c.sha)}</code></td><td>${esc(c.title)}</td></tr>`).join('')+'</table>':'';
  // the log only when it grew, and to its end only when it was at its end (reading further up stays where it is)
  const lg=$('updlog'),txt=await (await api('/api/logs/update?lines=200')).text()||t('(noch kein Update gelaufen)','(no update has run yet)');
  if(lg.textContent!==txt){const end=lg.scrollTop+lg.clientHeight>=lg.scrollHeight-30;lg.textContent=txt;if(end)lg.scrollTop=1e9}}
const kvp=rows=>rows.map(([k,v])=>`<tr><td class="mut" style="width:35%">${k}</td><td>${esc(v)}</td></tr>`).join('');
// Update notice on top of every page, also the assistant, for the logged-in admin only; "✕" hides
// it until a newer version appears.
function updBanner(r){const on=ADMIN&&r&&r.behind&&r.behind!==0&&r.latest;let hid='';try{hid=localStorage.getItem('updhide')||''}catch{}
  $('updbanner').style.display=on&&hid!==r.latest?'flex':'none';if(!on)return;
  $('updbtext').textContent=t('Update verfügbar','Update available')+(r.version?': '+r.version:'')+(r.behind>0?t(` (${r.behind} Änderung${r.behind>1?'en':''})`,` (${r.behind} change${r.behind>1?'s':''})`):'');
  $('updbx').onclick=()=>{try{localStorage.setItem('updhide',r.latest)}catch{}$('updbanner').style.display='none'}}
$('updbgo').onclick=()=>{$('updbanner').style.display='none';goSec('sys')};
// „Sprachmodell wechselt“ on top of every page for the admin (Dominik 2026-10-18 „2a“): step and minutes while the
// own language model switches, starts or is measured, a jump link to Zustand → Modelle; nothing otherwise
async function llmBanner(){if(!ADMIN||document.hidden)return;let d=null;try{const r=await api('/api/admin/modelle/lage'+(L==='en'?'?lang=en':''));if(r.ok)d=await r.json()}catch{}
  const x=d&&d.start,b=$('llmbanner');let txt='';
  if(x&&!x.ende)txt=x.titel+' · '+t('Schritt ','step ')+x.n+t(' von ',' of ')+x.von+': '+x.schritt_name+(x.rest_min?t(' · noch etwa ',' · about ')+x.rest_min+t(' min',' min left'):'')+t(' · Antworten pausieren',' · answers pause');
  else if(x&&x.ergebnis==='zurueck')txt=t('Modellwechsel zurückgenommen, das Modell davor läuft wieder','Model switch taken back, the model before runs again');
  else if(d&&d.misst)txt=t('Eine Modell-Messung läuft, das Sprachmodell pausiert','A model measurement is running, the language model pauses');
  b.style.display=txt?'flex':'none';$('llmbtext').textContent=txt}
$('llmbgo').onclick=()=>wayGo('Zustand → Modelle');
setInterval(llmBanner,15000);setTimeout(llmBanner,3000);
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
const KX={books:null,q:'',lang:'',grp:'',max:30};   // 30 rows, then „Weitere … zeigen“ (no scroll box inside the page)
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
  // one question asks at most kiwix.MAX_SEARCH_BOOKS (KX.most from the check): the German Wikipedia, the books that
  // fit its words, then this order (kiwix.pick); drag a chip or tap ◀ to move it forward
  const move=(id,to)=>{const l=kxSel().filter(y=>y!==id);l.splice(Math.max(0,to),0,id);kxSet(l)};
  sel.forEach((id,i)=>{const b=known[id],c=document.createElement('span');c.className='kxchip';c.title=id;c.draggable=true;
    c.ondragstart=e=>{KX.drag=id;try{e.dataTransfer.setData('text/plain',id)}catch{}};c.ondragover=e=>e.preventDefault();
    c.ondrop=e=>{e.preventDefault();if(KX.drag&&KX.drag!==id)move(KX.drag,kxSel().indexOf(id));KX.drag=''};
    if(i){const f=document.createElement('button');f.type='button';f.textContent='◀';f.title=t('Weiter nach vorn','Move forward');f.setAttribute('aria-label',f.title);f.onclick=()=>move(id,i-1);c.appendChild(f)}
    const n=document.createElement('span');n.textContent=b?b.title:id;c.appendChild(n);
    if(b){const m=document.createElement('small');m.textContent=[kxLang(b.lang),b.flavour,b.date].filter(Boolean).join(', ');c.appendChild(m)}
    const x=document.createElement('button');x.type='button';x.textContent='×';x.setAttribute('aria-label',t('Entfernen','Remove'));x.onclick=()=>kxSet(kxSel().filter(y=>y!==id));c.appendChild(x);
    box.appendChild(c)});
  if(KX.most&&sel.length>KX.most){const m=document.createElement('span');m.className='mut';m.textContent=t(`Je Frage höchstens ${KX.most}: die deutsche Wikipedia, die zur Frage passenden Bücher, dann diese Reihenfolge (ziehen oder ◀).`,`At most ${KX.most} per question: the German Wikipedia, the books fitting the question, then this order (drag or ◀).`);box.appendChild(m)}}
function kxPicker(){const box=$('kxpick');box.hidden=false;box.textContent='';const bar=document.createElement('div');bar.className='kxbar';
  const q=document.createElement('input');q.type='search';q.placeholder=t('Suchen: Titel, Name, Beschreibung','Search: title, name, description');q.value=KX.q;q.maxLength=60;
  q.oninput=()=>{KX.q=q.value;KX.max=30;kxList()};
  const counts=(key)=>{const m={};(KX.books||[]).forEach(b=>{m[b[key]]=(m[b[key]]||0)+1});return m};
  const ls=document.createElement('select'),lc=counts('lang');
  const opt=(sel,v,l)=>{const o=document.createElement('option');o.value=v;o.textContent=l;sel.appendChild(o)};
  opt(ls,'',t('Deutsch und Englisch','German and English'));opt(ls,'*',t('Alle Sprachen','All languages')+` (${(KX.books||[]).length})`);
  Object.keys(lc).sort((a,b)=>kxLang(a).localeCompare(kxLang(b))).forEach(c=>opt(ls,c,`${kxLang(c)} (${lc[c]})`));ls.value=KX.lang;ls.onchange=()=>{KX.lang=ls.value;KX.max=30;kxList()};
  const gs=document.createElement('select'),gc=counts('group');opt(gs,'',t('Alle Arten','All kinds'));
  Object.keys(gc).sort((a,b)=>kxGrp(a).localeCompare(kxGrp(b))).forEach(g=>opt(gs,g,`${kxGrp(g)} (${gc[g]})`));gs.value=KX.grp;gs.onchange=()=>{KX.grp=gs.value;KX.max=30;kxList()};
  bar.append(q,ls,gs);const list=document.createElement('div');list.className='kxlist';list.id='kxlist';box.append(bar,list);kxList()}
function kxList(){const list=$('kxlist');if(!list||!KX.books)return;list.textContent='';const sel=kxSel(),full=sel.length>=10;
  const q=KX.q.trim().toLowerCase();
  const hit=b=>(KX.lang==='*'||(KX.lang?b.lang===KX.lang:['de','en'].includes(b.lang)))&&(!KX.grp||b.group===KX.grp)
    &&(!q||(b.title+' '+b.id+' '+(b.desc||'')).toLowerCase().includes(q));
  const rows=KX.books.filter(b=>sel.includes(b.key)||hit(b));
  const order=b=>(sel.includes(b.key)?0:1);
  const groups={};rows.forEach(b=>{(groups[b.group]=groups[b.group]||[]).push(b)});
  const names=Object.keys(groups).sort((a,b)=>(a==='wikipedia'?-1:b==='wikipedia'?1:kxGrp(a).localeCompare(kxGrp(b))));
  let shown=0;const MAX=KX.max;
  for(const g of names){if(shown>=MAX)break;const h=document.createElement('div');h.className='kxgrp';h.textContent=`${kxGrp(g)} (${groups[g].length})`;list.appendChild(h);
    groups[g].sort((a,b)=>order(a)-order(b)||(a.lang==='de'?0:1)-(b.lang==='de'?0:1)||(b.count||0)-(a.count||0)||a.title.localeCompare(b.title));
    for(const b of groups[g]){if(shown++>=MAX)break;const on=sel.includes(b.key),r=document.createElement('label');r.className='kxrow'+(!on&&full?' dis':'');r.title=b.id;
      const c=document.createElement('input');c.type='checkbox';c.checked=on;c.disabled=!on&&full;
      c.onchange=()=>kxSet(c.checked?kxSel().concat([b.key]):kxSel().filter(y=>y!==b.key));
      const tx=document.createElement('div'),tt=document.createElement('div'),mm=document.createElement('div');tt.className='kxt';tt.textContent=b.title;mm.className='kxm';mm.textContent=kxMeta(b)+(b.desc?' – '+b.desc:'');
      tx.append(tt,mm);r.append(c,tx);list.appendChild(r)}}
  if(!rows.length){const m=document.createElement('div');m.className='kxmore';m.textContent=t('Nichts gefunden. Andere Sprache oder Art wählen.','Nothing found. Pick another language or kind.');list.appendChild(m)}
  else if(rows.length>MAX){const m=document.createElement('button');m.type='button';m.className='b kxmore';m.textContent=t(`Weitere ${rows.length-MAX} zeigen`,`Show ${rows.length-MAX} more`);m.onclick=()=>{KX.max+=30;kxList()};list.appendChild(m)}
  if(full){const m=document.createElement('div');m.className='kxmore';m.textContent=t('10 Bücher gewählt, mehr geht nicht.','10 books chosen, that is the most.');list.prepend(m)}}
$('kxload').onclick=async()=>{if(KX.books&&!$('kxpick').hidden){$('kxpick').hidden=true;return}
  $('kxmsg').textContent=t('Lade …','Loading …');
  try{const d=await kxCheck(),best={};KX.most=d.most||0;(d.books||[]).forEach(b=>{b.key=b.key||kxKey(b.id);const o=best[b.key];if(!o||(b.date||'')+b.id>(o.date||'')+o.id)best[b.key]=b});KX.books=Object.values(best);$('kxmsg').textContent=d.ok?t(`${KX.books.length} Bücher im Kiwix`,`${KX.books.length} books in the Kiwix`):(d.error||'');kxChips();if(d.ok)kxPicker()}
  catch(e){$('kxmsg').textContent=e.message}};
$('kxgo').onclick=async()=>{$('kxgomsg').textContent=t('Prüfe …','Checking …');$('kxout').textContent='';
  try{const d=await kxCheck(),out=$('kxout');KX.most=d.most||0;$('kxgomsg').textContent='';
    const line=(txt,cls)=>{const x=document.createElement('div');if(cls)x.className=cls;x.textContent=txt;out.appendChild(x)};
    if(!d.ok){line(d.error||t('Nicht erreichbar','Not reachable'),'err');return}
    line(t(`Erreichbar in ${d.ms} ms, ${d.books.length} Bücher; durchsucht werden ${(d.chosen||[]).length}.`,`Reachable in ${d.ms} ms, ${d.books.length} books; ${(d.chosen||[]).length} are searched.`));
    if(d.test)line(t(`Testsuche in „${d.test.book}“: ${d.test.hits} Treffer in ${d.test.ms} ms.`,`Test search in "${d.test.book}": ${d.test.hits} hits in ${d.test.ms} ms.`));
    else line(t('Kein Wikipedia-Buch gewählt: Testsuche übersprungen.','No Wikipedia book chosen: test search skipped.'),'mut');
    const known=Object.fromEntries(d.books.map(b=>[b.id,b]));line((d.picked?t('Durchsucht:','Searched:'):t('Keine Auswahl, durchsucht:','No choice, searched:'))+' '+((d.chosen||[]).map(id=>known[id]?known[id].title+(known[id].lang?' ('+known[id].lang+')':''):id).join(', ')||t('nichts','nothing')),'mut');
    if((d.missing||[]).length)line(t(`Nicht mehr im Kiwix und übersprungen: ${d.missing.join(', ')}. Unter „Bücher auswählen“ neu wählen.`,`No longer in the Kiwix and skipped: ${d.missing.join(', ')}. Pick again under "Choose books".`),'err')}
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
      r.sources.forEach(k=>line(`${LKSRC[k]||k}: `+(k in r.n?t(`${r.n[k]} Treffer`,`${r.n[k]} hits`):r.late.includes(k)?t(`zu langsam (über ${k==='kiwix'?r.kiwix_budget:r.budget} ms)`,`too slow (over ${k==='kiwix'?r.kiwix_budget:r.budget} ms)`):t('nicht erreichbar','not reachable'))));
      if(r.sources.length){const most=r.sources.includes('kiwix')?Math.max(r.budget,r.kiwix_budget):r.budget;line(t(`Zusammen ${r.ms} ms von höchstens ${most} ms.`,`Together ${r.ms} ms of at most ${most} ms.`),'mut')}
      r.hits.forEach(h=>line(`✓ ${h.title} (${h.chars} ${t('Zeichen','chars')})`));
      if(r.sources.length&&!r.hits.length)line(t('Lokal nichts Passendes: das Modell antwortet aus eigenem Wissen oder sucht im Web.','Nothing fitting locally: the model answers from its own knowledge or searches the web.'),'mut')}
    if(r.profile)line(t(`Profil: ${r.profile}`,`Profile: ${r.profile}`),'mut')}
  catch(e){line(e.message,'err')}$('lkgo').disabled=false};
$('updstop').onclick=async()=>{if(!confirm(t('Update abbrechen? Was schon installiert ist, bleibt. Ein späteres Update holt den Rest nach.','Cancel the update? What is already installed stays. A later update installs the rest.')))return;
  try{await api('/api/update',{method:'DELETE'});$('updmsg').textContent=t('abgebrochen','cancelled');loadSys()}
  catch(e){$('updmsg').innerHTML=`<span class="err">${esc(e.message)}</span>`}};
// Update lock: a progress window over the whole page; the server refuses changes meanwhile. One calm window from the
// question to the end (plaene/ruhige-seiten.md, Dominik 14.10.2026: „schaltet durch zu viele Fenster, wirkt zuckend“):
// behind it every other poll, band and bar keeps still (base.js updBusy), the bar only moves forward, the line changes
// at most every 2 s, the panel's restart is one quiet line, and at the end the page loads once, back at the same place.
const ul={iv:null,clicked:0,miss:0,max:0,said:0,ask:null};
const ulNote=()=>t('Bitte warten. Bis das Update fertig ist, sind Änderungen gesperrt. Die Seite lädt danach von selbst neu.','Please wait. Until the update is finished, changes are locked. The page reloads by itself afterwards.');
// each state shows only its own buttons (Dominik 15.10.2026: „zuviele knöpfe“): ask = Installieren/Abbrechen,
// running = none, slow = Neu laden/Update abbrechen, failed = Schließen/Protokoll kopieren; the log stays folded
function ulBtns(which,log){['ulask','ulslow','ulfail'].forEach(id=>$(id).hidden=id!==which);
  $('ullog').textContent=log&&log.length?log.join('\n'):'';$('ulpbox').hidden=!(log&&log.length);$('ulpbox').open=false}
// the question in the same window (before: the browser's own dialog, then a second window)
function ulAsk(head,text,yes){return new Promise(res=>{const u=$('updlock');u.style.display='grid';u.className='modal updlock ask';
  $('ulhead').textContent=head;$('ultext').textContent=text;$('ultime').textContent='';$('ulnote').textContent='';$('ulfill').style.width='0';
  ulBtns('ulask');$('ulyes').textContent=yes;$('ulno').textContent=t('Abbrechen','Cancel');
  const done=ok=>{ulBtns(null);ul.ask=null;if(!ok)u.style.display='none';res(ok)};ul.ask=done;$('ulyes').focus()})}
$('ulyes').onclick=()=>ul.ask&&ul.ask(true);$('ulno').onclick=()=>ul.ask&&ul.ask(false);
$('updlock').addEventListener('keydown',e=>{if(e.key==='Escape'&&ul.ask)ul.ask(false)});
function ulShow(){$('updlock').style.display='grid';$('updlock').className='modal updlock busy';ulBtns(null);
  $('ulhead').textContent=t('Update läuft','Update running');$('ulnote').textContent=ulNote();$('ultime').textContent='';if(!ul.iv)$('ultext').textContent=t('Starte …','Starting …');
  if(!ul.iv){ul.max=0;ul.said=0;$('ulfill').style.width='3%';ul.iv=setInterval(ulPoll,2000);ulPoll()}}
// the line under the bar: a new text at most every 2 s, the bar never back
function ulSay(text,pct){const now=Date.now();if(pct!=null){ul.max=Math.max(ul.max,Math.min(100,pct));$('ulfill').style.width=Math.max(3,ul.max)+'%'}
  if(text&&$('ultext').textContent!==text&&now-ul.said>=2000){$('ultext').textContent=text;ul.said=now}}
function ulStop(){clearInterval(ul.iv);ul.iv=null}
// slow: still running past the time limit, so reload or cancel; failed: the update ended, so close (and copy the log)
function ulFail(head,text,note,log,slow){ulStop();$('updlock').className='modal updlock fail';$('ulhead').textContent=head;$('ultext').textContent=text;
  $('ulnote').textContent=note;ulBtns(slow?'ulslow':'ulfail',log)}
async function ulPoll(){let p;try{const r=await /*raw: panel restarts during the update; 401/503 stay silent*/fetch('/api/update/progress');if(!r.ok)throw 0;p=await r.json();if(ul.miss){ul.miss=0;$('ulnote').textContent=ulNote()}}
  catch{ul.miss++;$('ulnote').textContent=t('Das Panel startet gerade neu, das gehört dazu. Das Fenster wartet und macht von selbst weiter.','The panel is restarting right now, that is part of it. The window waits and carries on by itself.');return}
  const fresh=p.started&&p.started*1000>=ul.clicked-60000;
  if(p.done&&fresh){if(p.ok){ulStop();ul.said=0;ulSay(t('Fertig, lade neu …','Done, reloading …'),100);
      try{sessionStorage.setItem('upddone',p.version||'1')}catch{}setTimeout(()=>verReload(),1200)}
    else ulFail(t('Update fehlgeschlagen','Update failed'),p.text||'',t('Schlägt ein Schritt vor dem Umschalten fehl, läuft die bisherige Version weiter; danach wird sie wieder eingespielt.','If a step before the switch fails, the previous version keeps running; after it, the previous version is installed again.'),p.log,false);return}
  if(!p.running){if(Date.now()-ul.clicked>15000){ulStop();   // nothing to do (already up to date) or ended without a report
      if(!fresh){$('updlock').style.display='none';loadSys&&loadSys()}else verReload()}return}
  ulSay(fresh?p.text:t('Starte …','Starting …'),fresh?p.percent:null);
  // only this update's own file: in its first seconds the unit runs while the file is still the last update's,
  // whose start would count as „too long“ (Dominik 2026-10-15: 102 minutes = the time since the update before)
  if(fresh&&p.started){const s=Math.max(0,p.now-p.started);$('ultime').textContent=Math.floor(s/60)+':'+String(s%60).padStart(2,'0');
    if(s>p.timeout)ulFail(t('Update dauert ungewöhnlich lange','Update is taking unusually long'),t('Letzter Schritt: ','Last step: ')+(p.text||'–'),
      t(`Nach ${Math.round(p.timeout/60)} Minuten nicht fertig. Neu laden zeigt den aktuellen Stand; Abbrechen gibt die Sperre frei, was schon installiert ist, bleibt.`,`Not finished after ${Math.round(p.timeout/60)} minutes. Reload shows the current state; cancelling releases the lock, what is already installed stays.`),p.log,true)}}
$('ulreload').onclick=()=>verReload();
$('ulclose').onclick=()=>{$('updlock').style.display='none';ulStop();if(ADMIN)loadSys()};
$('ulcancel').onclick=async()=>{try{await api('/api/update',{method:'DELETE'})}catch{}verReload()};
async function ulWatch(){if(ul.iv||ul.ask)return;try{const p=await (await api('/api/update/progress?log=false')).json();if(p.running){ul.clicked=p.started&&p.now-p.started<p.timeout?p.started*1000:Date.now();ulShow()}}catch{}}
setInterval(()=>{if(ADMIN&&!document.hidden)ulWatch()},8000);   // an update started from another tab or device locks this one too
document.addEventListener('visibilitychange',()=>{if(ADMIN&&!document.hidden)ulWatch()});   // Akku: hidden pages ask on coming back
async function ulCheck(){await ulWatch();
  let v=null;try{v=sessionStorage.getItem('upddone');sessionStorage.removeItem('upddone')}catch{}
  if(v)sayToast(t('Update fertig','Update finished')+(v!=='1'?': '+v:'')+'.',6000)}
$('updgo').onclick=async()=>{let tk={};try{tk=(await (await api('/api/update')).json()).talking||{}}catch{}
  // somebody talks with the Spark right now (vorrang.py): the restart would cut that conversation off
  const ask=tk.now?t(`Gerade läuft ein Gespräch mit dem Spark (zuletzt vor ${tk.ago} s gesprochen). Das Update startet die Dienste kurz neu und unterbricht es. Trotzdem jetzt installieren?`,`Somebody is talking with the Spark right now (last speech ${tk.ago} s ago). The update restarts the services briefly and cuts that off. Install anyway?`)
    :t('Update jetzt installieren? Die Dienste starten dabei kurz neu.','Install the update now? The services restart briefly.');
  if(!await ulAsk(t('Update installieren?','Install the update?'),ask,t('Installieren','Install')))return;
  // the lock shows at once and the server holds it from the click (update.begin): backup, then the unit
  try{ul.clicked=Date.now();ulShow();await api('/api/update',{method:'POST'})}
  catch(e){if(e.status===409)return;   // one runs already (another tab or device): this window follows it
    ulFail(t('Update konnte nicht starten','Update could not start'),e.message,t('Die bisherige Version läuft weiter.','The previous version keeps running.'),null,false)}};
setInterval(()=>{if(ADMIN)api('/api/update').then(r=>r.json()).then(u=>updBadge(u.remote)).catch(()=>{})},600000);
// ---------------------------------------------------------------- previous version, live check, backups
$('updprev').onclick=async()=>{if(!await ulAsk(t('Vorige Version einspielen?','Install the previous version?'),t('Die vorige Version wieder installieren? Vorher wird automatisch gesichert. Gilt die vorige Version vor V01.0.37, müssen Kalender-Passwörter und Home-Assistant-Tokens danach neu eingegeben werden.','Install the previous version again? A backup is made first. If the previous version is older than V01.0.37, calendar passwords and Home Assistant tokens have to be entered again afterwards.'),t('Einspielen','Install')))return;
  try{ul.clicked=Date.now();ulShow();await api('/api/update/rollback',{method:'POST'})}catch(e){ulStop();$('updlock').style.display='none';$('updmsg').innerHTML=`<span class="err">${esc(e.message)}</span>`}};
const LIVE={llm:t('Sprachmodell','Language model'),tools:t('Werkzeugwahl','Tool choice'),search:t('Websuche','Web search'),tts:t('Sprachausgabe','Speech output'),asr:t('Spracherkennung','Speech recognition')};
function liveRender(r){if(!r||!r.steps){$('livesteps').innerHTML=`<tr><td class="mut">${t('Noch nicht geprüft.','Not checked yet.')}</td></tr>`;$('livemsg').textContent='';return}
  $('livesteps').innerHTML=r.steps.map(s=>`<tr><td style="width:34%">${ic(s.ok===true?'check':s.ok===false?'x':'minus',s.ok===true?'okc':s.ok===false?'badc':'')} ${esc(LIVE[s.name]||s.name)}</td><td><span class="mut">${s.seconds} s</span> ${esc(s.detail||'')}</td></tr>`).join('');
  $('livemsg').textContent=new Date(r.t*1000).toLocaleString()+' · '+(r.version||'')+(r.reason==='after update'?t(' · nach dem Update',' · after the update'):'')}
// how long people wait for the first sound of an answer (latency.py)
function latRender(l){const f=s=>s?`<b>${s.median} s</b> <span class="mut">(${s.n} ${t('Antworten','answers')}, ${t('9 von 10 unter','9 of 10 below')} ${s.p90} s)</span>`:`<span class="mut">${t('noch keine','none yet')}</span>`;
  $('latsum').innerHTML=!l?'':`${t('Bis zum ersten Ton','Until the first sound')}: ${t('letzte 24 Stunden','last 24 hours')} ${f(l.day)} · ${t('Tage davor','days before')} ${f(l.week)}`+(l.warn?`<div class="err">${esc(l.warn)}</div>`:'')+
    (l.ack?`<div>${t('Erste Rückmeldung (fertiger Satz)','First acknowledgement (ready-made sentence)')}: ${f(l.ack)}</div>`:'')+
    latTables(l)+
    (l.ack_today&&(l.ack_today.with||l.ack_today.without)?`<div class="mut">${t(`Heute ${l.ack_today.with} Antworten mit sofortigem Satz, ${l.ack_today.without} ohne`,`Today ${l.ack_today.with} answers with an instant sentence, ${l.ack_today.without} without`)}${l.ack_today.top.length?t(', am häufigsten ohne: ',', most often without: ')+l.ack_today.top.map(x=>`${esc(x.group)} (${x.n})`).join(', '):''}</div>`:'')}
// per kind of question (Weiche group) and per version: where answers are slow, and whether a version made it better
function latTables(l){const s=v=>v==null?'–':v+' s',p=v=>v==null?'–':v+' %';
  const H=[t('Weiche','Switch'),t('Antworten','Answers'),t('Erster Ton (9 von 10)','First sound (9 of 10)'),t('Erstes Zeichen','First character'),t('Ende','End'),t('Aus dem Speicher','From the cache'),t('Werkzeuge','Tools'),t('Werkzeuge warten','Tools wait')];
  const V=[t('Version','Version'),H[1],H[2],H[5]];
  const D=[t('Dienst','Service'),t('Antworten','Answers'),t('Aus dem Vorrat','From the store'),t('Älterer Stand','Older reading'),t('Gewartet','Waited'),t('Werkzeuge warten','Tools wait')];
  const DN={mail:t('E-Mail','E-mail'),calendar:t('Kalender','Calendar'),weather:t('Wetter','Weather'),parcels:t('Pakete','Parcels'),fuerdich:t('Für dich','For you')};
  const d=(l.services||[]).map(r=>[esc(DN[r.service]||r.service),r.n,`<b>${p(r.share)}</b> <span class="mut">(${r.warm})</span>`,r.alt,r.kalt,s(r.wait)]);
  const tb=(hd,rows)=>`<table class="stack"><thead><tr>${hd.map(h=>`<th>${h}</th>`).join('')}</tr></thead><tbody>${rows.map(r=>`<tr>${r.map((c,i)=>`<td data-label="${hd[i]}">${c}</td>`).join('')}</tr>`).join('')}</tbody></table>`;
  const g=(l.groups||[]).map(r=>[esc(r.group),r.n,`<b>${s(r.median)}</b> <span class="mut">(${s(r.p90)})</span>`,s(r.first),s(r.end),p(r.cache),r.tools??'–',s(r.wait)]);
  const v=(l.versions||[]).map(r=>[esc(r.version),r.n,`<b>${s(r.median)}</b> <span class="mut">(${s(r.p90)})</span>`,p(r.cache)]);
  return (g.length?`<details class="adv"><summary>${t('Je Fragenart, letzte 7 Tage','Per kind of question, last 7 days')}</summary>${tb(H,g)}</details>`:'')+
    (v.length?`<details class="adv"><summary>${t('Je Version','Per version')}</summary>${tb(V,v)}</details>`:'')+
    (d.length?`<details class="adv"><summary>${t('Je Dienst: Vorrat, letzte 7 Tage','Per service: store, last 7 days')}</summary>${tb(D,d)}</details>`:'')}
async function loadLive(){try{const r=await (await api('/api/livecheck')).json();liveRender(r);latRender(r.latency)}catch{}loadQuality()}
// quality test of the language model (sandbox questions, see quality.py)
let qTimer=null;
// bar while the test runs: questions done of all, time left estimated from the pace so far
function qProg(p){const box=$('qprog'),bar=$('qbar');box.hidden=!p;if(!p)return;
  const n=p.total||0,d=Math.min(p.done||0,n);bar.classList.toggle('wait',!d);bar.firstChild.style.width=d?Math.round(100*d/n)+'%':'';
  const left=d?Math.round(p.seconds/d*(n-d)):0;
  $('qprogtxt').textContent=n?`${t('Frage','Question')} ${Math.min(d+1,n)} ${t('von','of')} ${n}`+(d>=3&&left>0?` · ${t('noch etwa','about')} ${left<60?left+' s':Math.round(left/60)+' min'}${t('',' left')}`:''):t('startet …','starting …')}
function qRender(d){const r=d&&d.last;clearTimeout(qTimer);qProg(d&&d.running?(d.progress||{done:0,total:0,seconds:0}):null);
  qCompare(d&&d.compare);
  if(d&&d.running){$('qmsg').textContent=t('läuft …','running …');$('qgo').disabled=$('qgoqwen').disabled=true;qTimer=setTimeout(loadQuality,2000)}
  else{$('qgo').disabled=$('qgoqwen').disabled=false;$('qmsg').textContent=r?new Date(r.t*1000).toLocaleString()+' · '+(r.version||'')+(r.reason==='after update'?t(' · nach dem Update',' · after the update'):''):''}
  const none=h=>{$('qsum').innerHTML=h;$('qlist').innerHTML='';$('qallbox').hidden=true};
  if(!r)return none(`<span class="mut">${t('Noch nicht geprüft.','Not tested yet.')}</span>`);
  if(r.error)return none(`<span class="err">${esc(r.error)}</span>`);
  const bad=r.cases.filter(x=>!x.ok),flaky=r.cases.filter(x=>x.ok&&x.flaky),held=r.cases.filter(x=>x.ok&&!x.flaky&&x.held&&x.held.length);
  // Einordnung im Qualitätstest (systemone): a second opinion only; a passed case it doubts stays open to look at
  const doubt=x=>!!(x.judge&&(x.judge.passt<1||x.judge.erfunden>=0.5)),doubted=r.cases.filter(x=>x.ok&&!x.flaky&&!(x.held&&x.held.length)&&doubt(x));
  const min=s=>s>=90?Math.round(s/60)+' min':s+' s';
  $('qsum').innerHTML=`<span class="pill ${bad.length?'warn':'ok'}">${r.passed} / ${r.total}</span> `
    +(bad.length?'':`<b>${t('Alle Fragen richtig.','All questions right.')}</b> `)
    +(flaky.length?`<span class="pill warn">${flaky.length} ${t('erst im zweiten Versuch','only on the second try')}</span> `:'')
    +`<div class="fh">${esc(r.model||'')}${r.sampling==='qwen'?' · '+t('mit Qwen-Empfehlung','with Qwen\'s recommendation'):''} · ${t('Temperatur','temperature')} ${r.temperature}${r.tool_temperature!=null?' / '+r.tool_temperature+t(' bei der Werkzeugwahl',' choosing tools'):''} · ${min(r.seconds)}</div>`;
  const mark=x=>(x.new?` <span class="pill warn">${t('neu kaputt','newly broken')}</span>`:'')
    +(x.wobbly?` <span class="mut">${t('wackelt','wobbles')} (${x.wobbly} ${t('von','of')} ${x.runs})</span>`:'');
  const extra=x=>(x.flaky&&x.first?`<br>${t('Erster Versuch','First try')}: ${esc(x.first.why.join('; '))}`:'')
    +(x.held&&x.held.length?`<br>${t('Antwort-Prüfung hat zurückgehalten','Answer check held back')}: ${esc(x.held.join(', '))}${x.raw?' · „'+esc(x.raw)+'“':''}`:'')
    +(x.retried?`<br>${t('Ohne Werkzeug geantwortet, neu gefragt','Answered without a tool, asked again')}`:'')
    +(x.judge?`<br>${t('Einordnung (systemone)','Classification (systemone)')}: ${t('beantwortet','answers')} ${String(x.judge.passt).replace('.',',')} ${t('von 2','of 2')} · ${t('erfunden','made up')} ${Math.round(x.judge.erfunden*100)} %${doubt(x)?' · '+t('zweifelt','doubts'):''}`:'');
  const head=x=>`<div class="qq"><span>${ic(x.ok?'check':'x',x.ok?'okc':'badc')} ${esc(x.q)}${mark(x)}</span><span class="qt">${esc(x.tools.map(wzName).join(', ')||t('kein Werkzeug','no tool'))}</span></div>`;
  // only questions that need a look stay open (one line each, answer clipped to two lines, tap opens it); the rest is folded
  const look=[...bad,...flaky,...held,...doubted];
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
// Wortwahl messen (quality.QWEN_SAMPLING): the newest run with the own values beside the newest with Qwen's recommendation
function qCompare(c){const box=$('qcmp'),e=c&&c.eigen,q=c&&c.qwen;box.hidden=!(e&&q);if(!(e&&q))return;
  box.textContent=`${t('Eigene Wortwahl','Own word choice')} ${e.passed} / ${e.total} · ${t('Qwen-Empfehlung','Qwen\'s recommendation')} ${q.passed} / ${q.total}`
    +(q.passed>e.passed?' · '+t('Die Empfehlung war besser: unter Einstellungen → Sprachmodell top_p 0,8, top_k 20 und presence_penalty 1 eintragen.','The recommendation was better: set top_p 0.8, top_k 20 and presence_penalty 1 under Settings → Language model.'):'')}
const qStart=body=>async()=>{try{qRender(await (await api('/api/quality',{method:'POST',body:JSON.stringify(body)})).json())}catch(e){$('qmsg').innerHTML=`<span class="err">${esc(e.message)}</span>`}};
$('qgo').onclick=qStart({});$('qgoqwen').onclick=qStart({sampling:'qwen'});
$('livego').onclick=async()=>{$('livego').disabled=true;$('livemsg').textContent=t('prüft … (bis zu einer Minute)','checking … (up to a minute)');
  try{liveRender(await (await api('/api/livecheck',{method:'POST'})).json())}catch(e){$('livemsg').innerHTML=`<span class="err">${esc(e.message)}</span>`}$('livego').disabled=false;refresh()};
const WHY={daily:t('täglich','daily'),manual:t('von Hand','manual'),'before-update':t('vor Update','before update'),'before-rollback':t('vor Rückkehr','before rollback'),'before-restore':t('vor Wiederherstellung','before restore'),move:t('Umzug (mit Schlüssel)','move (with key)')};
const mb=n=>n<1048576?Math.max(1,Math.round(n/1024))+' KB':(n/1048576).toFixed(1)+' MB';
function bakRender(l){$('baklist').innerHTML=l.map(b=>`<tr><td>${new Date(b.created*1000).toLocaleString()}<div class="mut">${esc(WHY[b.why]||b.why)} · ${mb(b.size)}</div></td><td style="text-align:right;white-space:nowrap"><button class="b mainonly" ${onAttr('bakLoad',b.name)}>${t('Laden','Download')}</button> <button class="b mainonly" ${onAttr('bakRestore',b.name)}>${t('Wiederherstellen','Restore')}</button> <button class="b mainonly" ${onAttr('bakDel',b.name)}>${t('Löschen','Delete')}</button></td></tr>`).join('')||`<tr><td class="mut">${t('Noch keine Sicherung.','No backup yet.')}</td></tr>`}
async function loadBak(){loadOff();try{bakRender((await (await api('/api/backups')).json()).backups)}catch(e){$('bakmsg').innerHTML=`<span class="err">${esc(e.message)}</span>`}}
const bakAsk=()=>confirm(t('Wiederherstellen? Profile, Stimmen und Einstellungen werden durch die Sicherung ersetzt (der jetzige Stand wird vorher gesichert). Geänderte Einstellungen der Dienste wirken nach deren Neustart.','Restore? Profiles, voices and settings are replaced by the backup (the current state is backed up first). Changed service settings take effect after their restart.'));
const bakDone=r=>{$('bakpw').value='';$('bakmsg').textContent=t('Wiederhergestellt: ','Restored: ')+r.restored.join(', ')+(r.restored.includes('admin-mfa-kept')?t(' (der zweite Anmeldeschritt des Admins bleibt der von diesem Spark)',' (the admin\'s second login step stays the one of this Spark)'):'')+(r.restored.includes('admin-password-kept')?t(' (Panel-Passwort und sein zweiter Schritt bleiben unverändert: die stellt nur der Hauptadmin wieder her)',' (the panel password and its second step stay unchanged: only the main admin restores those)'):'')+(r.restored.includes('keys')?t(' – bitte überall neu anmelden.',' – please sign in again everywhere.'):'');loadBak()};
// a move backup needs its password: taken from the field below the list
const bakErr=e=>{const m=/move backup|wrong password/.test(errRaw(e))?t('Das ist eine Umzugs-Sicherung: Passwort ins Feld unten eintragen und nochmal wiederherstellen. ','This is a move backup: enter its password in the field below and restore again. '):'';$('bakmsg').innerHTML=`<span class="err">${esc(m+e.message)}</span>`};
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
  $('offmsg').classList.toggle('err',!!(l&&!l.ok)&&!d.running);offCertShow(d)}
// Zertifikat prüfen (zertpin.py): a NAS whose certificate does not fit its address is never sent to with the check
// off; the admin compares the fingerprint with the one the NAS shows and accepts exactly that certificate.
function offCertShow(d,c){certBox($('offcertmsg'),c,d&&d.cert,sha=>offPut({url:$('offurl').value.trim(),cert:sha}),
  ()=>{if(confirm(t('Das angenommene Zertifikat vergessen? Danach geht die Sicherung nur noch mit einem Zertifikat, das zur Adresse passt.','Forget the accepted certificate? Then the backup only goes to a certificate that fits the address.')))offPut({cert:''})})}
// one box for every server whose certificate the admin may accept (NAS backup, Docling server): c = what the server shows now,
// pinned = the fingerprint accepted before; accept(sha) and forget() save it with a fresh code
function certBox(m,c,pinned,accept,forget){if(!m)return;m.textContent='';m.classList.remove('err');
  const line=x=>{const s=document.createElement('div');s.textContent=x;m.appendChild(s);return s};
  const btn=(x,f)=>{const b=document.createElement('button');b.type='button';b.className='b';b.textContent=x;b.onclick=f;m.appendChild(b)};
  if(c){line(t('Fingerabdruck (SHA-256): ','Fingerprint (SHA-256): ')+c.sha256);
    line(t('Gilt für: ','Valid for: ')+(c.names.join(', ')||'–')+' · '+t('bis ','until ')+new Date(c.until*1000).toLocaleDateString()+(c.expired?t(' (abgelaufen)',' (expired)'):''));
    if(c.pinned)line(t('Dieses Zertifikat ist angenommen.','This certificate is accepted.'));
    else if(c.fits&&!c.self_signed)line(t('Passt zur Adresse; nichts zu tun.','Fits the address; nothing to do.'));
    else{line(t('Passt nicht zur Adresse oder ist selbst ausgestellt. Besser: die Adresse mit einem Namen von oben eintragen. Sonst den Fingerabdruck mit dem auf dem Server vergleichen (Synology: Systemsteuerung, Sicherheit, Zertifikat) und nur wenn er gleich ist annehmen.',
      'Does not fit the address or is self-made. Better: enter the address with a name from above. Otherwise compare the fingerprint with the one on the server (Synology: Control Panel, Security, Certificate) and accept it only when it is the same.'));
      btn(t('Diesem Zertifikat vertrauen','Trust this certificate'),()=>accept(c.sha256))}
    return}
  if(pinned){line(t('Angenommenes Zertifikat: ','Accepted certificate: ')+pinned);btn(t('Vergessen','Forget'),forget)}}
async function loadOff(){if(!$('offbox')||document.body.classList.contains('mgr'))return;
  try{offShow(await (await api('/api/admin/offsite')).json())}catch{}}
async function offPut(b){try{offShow(await (await api('/api/admin/offsite',xjson('PUT',b))).json())}catch(e){$('offmsg').textContent=e.message;$('offmsg').classList.add('err');return false}return true}
if($('offcert'))$('offcert').onclick=async()=>{const m=$('offcertmsg');m.textContent=t('frage den NAS …','asking the NAS …');
  try{offCertShow(null,await (await api('/api/admin/offsite/cert',xjson('POST',{url:$('offurl').value.trim()}))).json())}catch(e){m.textContent=e.message;m.classList.add('err')}};
if($('offsave'))$('offsave').onclick=()=>offPut({url:$('offurl').value.trim(),user:$('offuser').value.trim(),password:$('offpw').value,key:$('offkey').value});
if($('offon'))$('offon').onchange=async e=>{const on=e.target.checked;if(!await offPut({on,url:$('offurl').value.trim(),user:$('offuser').value.trim(),password:$('offpw').value,key:$('offkey').value}))e.target.checked=!on};
if($('offnow'))$('offnow').onclick=async()=>{try{offShow(await (await api('/api/admin/offsite/now',{method:'POST'})).json());
  const poll=async()=>{let d;try{d=await (await api('/api/admin/offsite')).json()}catch{return}offShow(d);if(d.running)setTimeout(poll,3000)};setTimeout(poll,3000)}
  catch(e){$('offmsg').textContent=e.message;$('offmsg').classList.add('err')}};
// Docling-Server (doclingdienst.py): address, key and certificate; the key is never shown again (an empty field keeps it).
// Changing the address or key asks for the code every time (stufen.py); "Probe lesen" sends only the Spark's own sample.
const DLWHY={down:t('nicht erreichbar','not reachable'),cert:t('Zertifikat passt nicht','certificate does not fit'),key:t('Schlüssel abgelehnt','key refused'),
  blocked:t('vom Wächter nicht erlaubt','not allowed by the Wächter'),failed:t('Probe nicht lesbar','sample not readable')};
function dlShow(d){$('dlurl').value=d.url||'';$('dlkey').value='';$('dlplain').hidden=!d.plain;$('dlcert').hidden=!!d.plain;
  $('dlkey').placeholder=d.has_key?t('API-Schlüssel (gespeichert)','API key (saved)'):t('API-Schlüssel (DOCLING_SERVE_API_KEY)','API key (DOCLING_SERVE_API_KEY)');
  const l=d.last,s=d.stats||{};const m=$('dlmsg');
  m.textContent=(!d.url?t('Noch keine Adresse.','No address yet.'):!l?t('Noch nicht geprüft.','Not checked yet.')
    :l.ok?t('Zuletzt gelesen: ','Last read: ')+new Date(l.t*1000).toLocaleString():t('Fehler am ','Failed on ')+new Date(l.t*1000).toLocaleString()+': '+(DLWHY[l.why]||l.why))
    +(d.url?' · '+t(`heute ${s.ok||0} gelesen, ${s.failed||0} Fehler`,`today ${s.ok||0} read, ${s.failed||0} failed`):'');
  m.classList.toggle('err',!!(l&&!l.ok));
  certBox($('dlcertmsg'),null,d.cert,()=>{},()=>{if(confirm(t('Das angenommene Zertifikat vergessen? Danach liest Docling nur mit einem Zertifikat, das zur Adresse passt.','Forget the accepted certificate? Then Docling only reads with a certificate that fits the address.')))dlPut({cert:''})})}
async function dlLoad(){if(!$('dlbox')||document.body.classList.contains('mgr'))return;
  try{dlShow(await (await api('/api/admin/docling')).json())}catch{}}
async function dlPut(b){try{dlShow(await (await api('/api/admin/docling',xjson('PUT',b))).json())}catch(e){$('dlmsg').textContent=e.message;$('dlmsg').classList.add('err');return false}return true}
if($('dlsave'))$('dlsave').onclick=()=>dlPut({url:$('dlurl').value.trim(),key:$('dlkey').value});
if($('dlurl'))$('dlurl').oninput=()=>{$('dlplain').hidden=!/^http:\/\//i.test($('dlurl').value.trim())};
if($('dlcert'))$('dlcert').onclick=async()=>{const m=$('dlcertmsg');m.textContent=t('frage den Server …','asking the server …');
  try{const c=await (await api('/api/admin/docling/cert',xjson('POST',{url:$('dlurl').value.trim()}))).json();
    certBox(m,c,'',sha=>dlPut({url:$('dlurl').value.trim(),cert:sha}),()=>{})}catch(e){m.textContent=e.message;m.classList.add('err')}};
if($('dltest'))$('dltest').onclick=async()=>{const o=$('dlout');o.hidden=false;o.textContent=t('liest die Probe …','reading the sample …');
  try{const r=await (await api('/api/admin/docling/test',{method:'POST'})).json();
    o.textContent=r.ok?t(`Gelesen in ${r.seconds} s, ${r.chars} Zeichen`,`Read in ${r.seconds} s, ${r.chars} characters`)+(r.table?t(', Tabelle erkannt.',', table found.'):t(', keine Tabelle erkannt.',', no table found.')):(r.say||DLWHY[r.why]||r.why);
    o.classList.toggle('err',!r.ok);if(r.ok&&r.text){const pre=document.createElement('pre');pre.className='mut';pre.textContent=r.text;o.appendChild(pre)}dlLoad()}
  catch(e){o.textContent=e.message;o.classList.add('err')}};
$('bakup').onclick=()=>$('bakfile').click();
$('bakfile').onchange=async()=>{const f=$('bakfile').files[0];$('bakfile').value='';if(!f||!bakAsk())return;$('bakmsg').textContent=t('stelle wieder her …','restoring …');
  const fd=new FormData();fd.append('file',f,f.name);fd.append('password',$('bakpw').value);try{bakDone(await (await api('/api/backups-upload',{method:'POST',body:fd})).json())}catch(e){bakErr(e)}};
$('bakmove').onclick=async()=>{const pw=$('bakpw').value;if(pw.length<12){$('bakmsg').innerHTML=`<span class="err">${t('Das Passwort braucht mindestens 12 Zeichen.','The password needs at least 12 characters.')}</span>`;return}
  const again=prompt(t('Passwort zur Kontrolle noch einmal eingeben:','Enter the password once more:'));if(again===null)return;
  if(again!==pw){$('bakmsg').innerHTML=`<span class="err">${t('Die Passwörter sind verschieden.','The passwords differ.')}</span>`;return}
  $('bakmsg').textContent=t('sichere …','backing up …');
  try{const b=await (await api('/api/backups/move',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({password:pw})})).json();$('bakpw').value='';
    $('bakmsg').textContent=t('Umzugs-Sicherung angelegt: ','Move backup made: ')+mb(b.size)+t('. Mit „Laden“ herunterladen und das Passwort gut aufheben.','. Download it with "Download" and keep the password safe.');loadBak()}catch(e){$('bakmsg').innerHTML=`<span class="err">${esc(e.message)}</span>`}};
// alerts on top of every admin page: memory, watchdog, failed live check, slow answers, a service gone. Each names
// with go (health.alerts, a way like "Zustand → Logs → Anfragen") where to look or act: the button jumps there
// (way.js, Dominik 12.10.2026). Drawn again only when something changed (refresh runs every 3 s).
// One slim line each; from two on, everything but "bad" folds into one line with the count, folded by default
// and remembered per browser (Dominik 16.10.2026: „zu groß, muss einklappbar sein“). "bad" always stays open.
let ALERTS_LAST='';
function alertsOpen(){try{return localStorage.getItem('alertsopen')==='1'}catch{return false}}
function alertRow(x){const n=document.createElement('div');n.className='note anote'+(x.level==='bad'?' bad':'')+(x.go?' gonote':'');
  const s=document.createElement('span');s.textContent=x.text;s.title=x.text;n.appendChild(s);
  if(x.go&&typeof wayGo==='function'){const b=document.createElement('button');b.type='button';b.className='b';b.textContent=t('Ansehen','View');
    b.title=x.go;b.onclick=()=>wayGo(x.go);n.appendChild(b)}
  return n}
// notes only to know (level "info", e.g. open hands-on tests) stand on Zustand only, not above every page (code check 19.10. D12)
let ALERTS_RAW=[];
function showAlerts(a){a=a||[];ALERTS_RAW=a;const mon=!!document.querySelector('section#mon.on');if(!mon)a=a.filter(x=>x.level!=='info');
  const k=JSON.stringify(a);if(k===ALERTS_LAST)return;ALERTS_LAST=k;const box=$('alerts');box.textContent='';
  const bad=a.filter(x=>x.level==='bad'),rest=a.filter(x=>x.level!=='bad');
  for(const x of bad)box.appendChild(alertRow(x));
  if(rest.length===1){box.appendChild(alertRow(rest[0]));return}
  if(!rest.length)return;
  const d=document.createElement('details');d.className='afold';d.open=alertsOpen();
  const sm=document.createElement('summary'),c=document.createElement('b'),l=document.createElement('span');
  c.textContent=rest.length+' '+t('Hinweise','notes');l.textContent=rest.map(x=>x.text.replace(/[.:].*$/,'')).join(' · ');
  sm.appendChild(c);sm.appendChild(l);d.appendChild(sm);
  for(const x of rest)d.appendChild(alertRow(x));
  d.ontoggle=()=>{try{localStorage.setItem('alertsopen',d.open?'1':'0')}catch{}};
  box.appendChild(d)}
// ---------------------------------------------------------------- does the language model see pictures? (images.py)
function visionShow(r){if(!r){$('visionmsg').textContent=t('Noch nicht geprüft.','Not checked yet.');return}
  const when=new Date(r.t*1000).toLocaleString([], {dateStyle:'short',timeStyle:'short'});
  $('visionmsg').innerHTML=r.ok?`<span class="ok">✓ ${t('Kann Bilder','Sees pictures')}</span> · ${esc(when)} · ${esc(String(r.seconds))} s`
    :`<span class="err">✗ ${esc(r.error||t('kann keine Bilder','sees no pictures'))}</span> · ${esc(when)}`}
// Satzende am Tonfall (satzende.py): the measurement's numbers, never words
async function satzendeLoad(){if(!$('satzendemsg'))return;try{const d=await (await api('/api/admin/satzende')).json();
  $('satzendemsg').textContent=!d.n?t('Noch keine Pause gemessen.','No pause measured yet.'):`${d.n} / ${d.rows} ${t('Pausen','pauses')}${d.measuring?'':' · '+t('Messung fertig','measurement done')} · `+
    `${t('mit Zahl','with a number')} ${d.rated} · ${t('Treffer','hits')} ${d.hits} · ${t('Fehlalarme','false alarms')} ${d.false} · ${t('gespart','saved')} ${d.saved_s} s`+(d.ms!=null?` · ${d.ms} ms`:'')}catch{}}
async function visionLoad(){if(!$('visiongo'))return;try{visionShow((await (await api('/api/admin/vision-test')).json()).last)}catch{}}
// Einordnung mit Wahrscheinlichkeit (systemone.py): one question of the switch through qwen38's /v1/systemone
// the label mass (how much of the probability fell on any option) and the option orders qwen38 asked in
function s1Extra(r){const m=typeof r.mass==='number'?' · '+t('Label-Masse','label mass')+' '+Math.round(r.mass*100)+' %':'';
  const o=r.orders===2?' · '+t('zwei Reihenfolgen an','two orders on'):r.orders===1?' · '+t('eine Reihenfolge (zwei Reihenfolgen aus)','one order (two orders off)'):'';return m+o}
if($('s1go'))$('s1go').onclick=async()=>{$('s1go').disabled=true;$('s1msg').textContent=t('prüft …','checking …');
  try{const r=await (await api('/api/admin/systemone/test',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({text:($('routetext')&&$('routetext').value.trim())||''})})).json();
    const pc=Math.round((r.min||0.8)*100)+' %';
    $('s1msg').innerHTML=r.ok?`<b>${t('antwortet','answers')}</b> ${t('in','in')} ${r.ms} ms · ${(r.top||[]).map(([k,p])=>esc(k)+' '+Math.round(p*100)+' %').join(', ')} · ${r.used?t('Weiche grenzt ein','switch narrows'):esc(t('unter ','below ')+pc+t(' oder unklar: alle Werkzeuge',' or unclear: all tools'))}${esc(s1Extra(r))}${r.sentence?' '+t('(Beispielsatz; ein Satz unter „Ausprobieren“ wird genommen)','(sample sentence; a sentence under "Try it" is used)'):''}`
      :`<span class="err">${esc(t('Keine Antwort: ','No answer: ')+(r.why==='unsicher'?t('unsicher (Label-Masse zu klein)','unsure (label mass too small)'):(r.why||'')))}</span>${esc(s1Extra(r))}`}
  catch(e){$('s1msg').innerHTML=`<span class="err">${esc(e.message)}</span>`}$('s1go').disabled=false};
// Einordnung messen: the Weiche's test sentences through the switch question, numbers per threshold (systemone.bench_result)
function s1BenchShow(d){const out=$('s1benchout'),msg=$('s1benchmsg');if(!out)return;
  msg.textContent=d.run?t('misst … ','measuring … ')+d.done+' / '+d.total:d.why?t('abgebrochen: ','stopped: ')+d.why:'';
  const r=d.result;if(!r){out.textContent='';return}
  const rows=r.per.map(x=>`<tr><td class="bnum">${Math.round(x.min*100)} %</td><td class="bnum">${x.narrow} (${Math.round(x.share*100)} %)</td><td class="bnum">${x.wrong} (${Math.round(x.wrong_share*100)} %)</td></tr>`).join('');
  const miss=(r.misses||[]).map(([k,n])=>esc(k.replace('>',' → '))+' '+n+'×').join(', ');
  out.innerHTML=`<div class="fh">${esc(t('Sätze','Sentences'))} ${r.n} · ${esc(t('beantwortet','answered'))} ${r.answered} · ${esc(t('richtig','right'))} ${r.hits} · ${esc(t('Mitte','median'))} ${r.ms_mid} ms${typeof r.mass_mid==='number'?' · '+esc(t('Label-Masse Mitte','label mass median'))+' '+Math.round(r.mass_mid*100)+' %, '+esc(t('kleinste','smallest'))+' '+Math.round(r.mass_min*100)+' %':''}${esc(s1Extra({orders:r.orders}))}</div>
    <table class="brate"><tbody><tr class="bgrp"><td>${esc(t('Schwelle','Threshold'))}</td><td>${esc(t('grenzt ein','narrows'))}</td><td>${esc(t('davon falsch','of them wrong'))}</td></tr>${rows}</tbody></table>
    <div class="fh">${r.suggest?esc(t('Vorschlag: ','Suggestion: ')+Math.round(r.suggest*100)+' %'+t(' (höchstens 3 % falsch eingegrenzt).',' (at most 3 % narrowed wrongly).')):esc(t('Keine Schwelle mit höchstens 3 % Fehlern: lieber 90 % oder die Einordnung für die Werkzeugwahl nicht nutzen.','No threshold with at most 3 % errors: rather 90 % or do not use the classification for the tool choice.'))}${miss?' '+esc(t('Verwechselt: ','Mixed up: '))+miss:''}</div>
    ${r.suggest?`<div class="row"><button class="b" type="button" id="s1take">${esc(t('Vorschlag übernehmen','Take the suggestion'))}</button></div>`:''}`;
  // the threshold lives on Funktionen → Weiche (weiche.js): taken there, saved with „Prüfen und speichern“
  if($('s1take'))$('s1take').onclick=()=>{if(!(window.whSetMin&&window.whSetMin(r.suggest)))return;
    msg.textContent=t('Eingesetzt, noch nicht gespeichert.','Filled in, not saved yet.')}}
let s1Timer=null;
async function s1BenchPoll(){clearTimeout(s1Timer);try{const d=await (await api('/api/admin/systemone/messen')).json();s1BenchShow(d);
  if(d.run&&document.getElementById('s1bench'))s1Timer=setTimeout(s1BenchPoll,2000)}catch{}}
if($('s1bench'))$('s1bench').onclick=async()=>{try{s1BenchShow(await (await api('/api/admin/systemone/messen',{method:'POST'})).json());s1Timer=setTimeout(s1BenchPoll,2000)}
  catch(e){$('s1benchmsg').innerHTML=`<span class="err">${esc(e.message)}</span>`}};
// Bilder malen (bilder.py): one sample picture, the service's measurements (load time, seconds, memory)
function bildTestShow(d){const m=$('bildtestmsg');if(!m)return;const r=d&&d.last,h=d&&d.health||{};
  const st={missing:t('Bildmodell nicht installiert (sudo ./install.sh --bild 4b-q8)','picture model not installed (sudo ./install.sh --bild 4b-q8)'),off_install:t('Bildmodell nicht installiert (sudo ./install.sh --bild 4b-q8)','picture model not installed (sudo ./install.sh --bild 4b-q8)'),
    down:t('Bild-Dienst antwortet nicht','picture service does not answer'),off:t('entladen','unloaded'),starting:t('lädt','loading'),ready:t('geladen','loaded'),busy:t('malt','painting'),error:t('Fehler','error')}[h.status]||'';
  const num=(v,u)=>v==null?'':String(v).replace('.',L==='en'?'.':',')+' '+u;
  const parts=[h.name,st,h.load_s!=null&&t('Laden ','load ')+num(h.load_s,'s'),h.last_s!=null&&t('Bild ','picture ')+num(h.last_s,'s'),h.peak_gib!=null&&t('Speicher ','memory ')+num(h.peak_gib,'GB')].filter(Boolean);
  m.textContent=(r?(r.ok?'✓ '+t('Probebild gemalt','sample painted'):'✗ '+t('nicht gemalt: ','not painted: ')+r.why)+' · ':'')+parts.join(' · ')}
async function bildTestLoad(){if(!$('bildtestgo'))return;try{bildTestShow(await (await api('/api/admin/bild-test')).json())}catch{}}
if($('bildtestgo'))$('bildtestgo').onclick=async()=>{$('bildtestgo').disabled=true;$('bildtestmsg').textContent=t('malt ein Probebild …','painting a sample …');
  try{bildTestShow(await (await api('/api/admin/bild-test',{method:'POST'})).json())}catch(e){$('bildtestmsg').textContent=e.message}$('bildtestgo').disabled=false};
// Musik machen (musik.py): Musik testen measures every installed model with two fixed sample songs (seconds and
// memory at the peak, both to listen to); Funktionen → Musik machen offers only the installed models
function musikTestShow(d){const m=$('musiktestmsg'),box=$('musiktestrows');musikModelShow(d);if(!m||!box)return;const h=d&&d.health||{},r=d&&d.last;
  const st={missing:t('Musikmodell nicht vollständig installiert (sudo ./install.sh --musik 2b)','music model not fully installed (sudo ./install.sh --musik 2b)'),off_install:t('Musikmodell nicht installiert (sudo ./install.sh --musik 2b)','music model not installed (sudo ./install.sh --musik 2b)'),
    down:t('Musik-Dienst antwortet nicht','music service does not answer'),off:t('entladen','unloaded'),starting:t('lädt','loading'),ready:t('geladen','loaded'),busy:t('macht Musik','making music'),error:t('Fehler','error')}[h.status]||'';
  const num=(v,u)=>v==null?'':String(v).replace('.',L==='en'?'.':',')+' '+u;
  const why={missing:t('nicht installiert','not installed'),memory:t('zu wenig Speicher frei','too little memory free'),engine:t('Engine-Fehler','engine error'),zeit:t('Zeit abgelaufen','timed out'),dienst:t('Dienst antwortet nicht','service does not answer'),pause:t('Wartungspause','maintenance pause')};
  const vn={};(d&&d.variants||[]).forEach(([k,de,en])=>vn[k]=L==='en'?en:de);
  const inst=(h.installed||[]).map(k=>vn[k]||k).join(', ');
  m.textContent=[inst?t('installiert: ','installed: ')+inst:h.name,st,d&&d.run?t('misst … ','measuring … ')+(d.done||0)+'/'+(d.total||2):''].filter(Boolean).join(' · ');
  const names={};(d&&d.tests||[]).forEach(x=>names[x.n]=L==='en'?x.name.en:x.name.de);
  box.innerHTML=(r&&r.runs||[]).map(run=>`<div class="fh"><b>${esc(vn[run.variant]||run.variant)}</b></div>`+(run.tests||[]).map(x=>`<div class="fh">${x.ok?'✓':'✗'} ${esc(names[x.n]||String(x.n))}: `+(x.ok?esc([t('fertig in ','done in ')+num(x.seconds,'s'),t('Planen ','planning ')+num(x.lm_s,'s'),t('Klang ','sound ')+num(x.synth_s,'s'),t('Speicher ','memory ')+num(x.peak_gib,'GB')].join(' · '))+`<br><audio controls preload="none" src="/api/admin/musik-test/${encodeURIComponent(run.variant)}/${x.n}.mp3?t=${r.t}"></audio>`:esc(why[x.why]||x.why))+'</div>').join('')).join('')}
// the model select of Funktionen → Musik machen: models that are not installed can not be picked
function musikModelShow(d){const sel=$('music.model'),msg=$('musikmodelmsg');if(!sel||!d)return;const inst=(d.health||{}).installed;if(!Array.isArray(inst))return;
  [...sel.options].forEach(o=>{if(o.value)o.disabled=!inst.includes(o.value)});
  if(msg)msg.textContent=sel.value&&!inst.includes(sel.value)?t('Dieses Modell ist auf dem Modell-Rechner nicht installiert (sudo ./install.sh --musik '+sel.value+').','This model is not installed on the model computer (sudo ./install.sh --musik '+sel.value+').'):t('Wählbar sind die installierten Modelle; vergleichen mit Zustand → Prüfen → „Musik testen“.','The installed models can be picked; compare them with State → Checks → „Test music“.')}
async function musikModelLoad(){if(!$('music.model'))return;try{musikModelShow(await (await api('/api/admin/musik-test')).json())}catch{}}
let musikTimer=null;
async function musikTestLoad(){clearTimeout(musikTimer);if(!$('musiktestgo'))return;try{const d=await (await api('/api/admin/musik-test')).json();musikTestShow(d);
  $('musiktestgo').disabled=!!d.run;if(d.run)musikTimer=setTimeout(musikTestLoad,3000)}catch{}}
if($('musiktestgo'))$('musiktestgo').onclick=async()=>{$('musiktestgo').disabled=true;
  try{musikTestShow(await (await api('/api/admin/musik-test',{method:'POST'})).json());musikTimer=setTimeout(musikTestLoad,3000)}catch(e){$('musiktestmsg').textContent=e.message;$('musiktestgo').disabled=false}};
if($('visiongo'))$('visiongo').onclick=async()=>{$('visiongo').disabled=true;$('visionmsg').textContent=t('prüft …','checking …');
  try{visionShow((await (await api('/api/admin/vision-test',{method:'POST'})).json()).last)}catch(e){$('visionmsg').innerHTML=`<span class="err">${esc(e.message)}</span>`}$('visiongo').disabled=false};

// the read-only GitHub token for update checks and downloads (Einstellungen → Update), shown as set / until when, never itself;
// set and checked as working: only a status line with "Ändern" and "Entfernen" (Dominik 14.10.2026), else the field stays open
let GH_EDIT=false;
async function ghAdmin(){const box=$('ghtokadmin');if(!box||!ADMIN)return;let d;try{d=await (await api('/api/admin/ghtoken')).json()}catch{box.textContent='';return}
  // after a restart nobody knows yet whether it works: ask once (GitHub's /rate_limit costs nothing of the limit)
  if(d.set&&d.ok==null&&d.used!=='Token abgelehnt'){try{d=await (await api('/api/admin/ghtoken/check',{method:'POST'})).json()}catch{}}
  const good=d.set&&d.ok===true&&d.used==='mit Token',open=!good||GH_EDIT;
  const info=esc(t('Ohne Token beantwortet GitHub allen Geräten hinter deinem Internetanschluss zusammen nur 60 Fragen pro Stunde, mit Token 5000. So bekommst du ihn: github.com → Settings → Developer settings → Fine-grained tokens → Generate new token. Repository access: „Public repositories“, keine Rechte, Ablauf 1 Jahr. Er geht nur an api.github.com, wird verschlüsselt gespeichert und nie wieder angezeigt; Speichern fragt einen frischen Code. Der Token für „Probleme melden“ bleibt ein eigener.','Without a token GitHub answers only 60 questions per hour for all devices behind your internet connection together, with one 5000. How to get it: github.com → Settings → Developer settings → Fine-grained tokens → Generate new token. Repository access: "Public repositories", no permissions, expiry 1 year. It goes only to api.github.com, is stored encrypted and never shown again; saving asks for a fresh code. The token for "Report problems" stays a separate one.'));
  box.innerHTML=open?`<div class="setrow"><div class="lbl"><b>${esc(t('GitHub-Token (nur lesen)','GitHub token (read only)'))}</b><span class="ghtok"></span></div>
    <div class="ctl full"><input type="password" id="ghtoken" maxlength="300" autocomplete="off" placeholder="github_pat_…" aria-label="${esc(t('Neuer Token','New token'))}"><button class="b" type="button" id="ghtokset">${esc(t('Speichern','Save'))}</button></div></div>
    <div class="row" style="gap:6px"><button class="b" type="button" id="ghtokcheck"${d.set?'':' disabled'}>${esc(t('Prüfen','Check'))}</button><button class="b" type="button" id="ghtokdel"${d.set?'':' disabled'}>${esc(t('Entfernen','Remove'))}</button>${good?`<button class="b" type="button" id="ghtokcancel">${esc(t('Abbrechen','Cancel'))}</button>`:''}</div>
    <div class="fh">${info}</div>
    <div class="fh" id="ghtokmsg" role="status"></div>`
   :`<div class="setrow"><div class="lbl"><b>${esc(t('GitHub-Token (nur lesen)','GitHub token (read only)'))}</b><span class="ghtok"></span></div>
    <div class="ctl"><button class="b" type="button" id="ghtokedit">${esc(t('Ändern','Change'))}</button><button class="b" type="button" id="ghtokdel">${esc(t('Entfernen','Remove'))}</button></div></div>
    <div class="fh" id="ghtokmsg" role="status"></div>`;
  const st=box.querySelector('.ghtok');st.textContent=d.set?(d.used==='Token abgelehnt'?t('abgelehnt oder abgelaufen: GitHub wird ohne Token gefragt, bitte neuen speichern','refused or expired: GitHub is asked without it, please save a new one'):t('gesetzt','set')+(good?t(', geprüft ✓',', checked ✓'):'')+(d.until?t(', läuft bis ',', valid until ')+d.until:'')+(d.limit?' · '+d.limit+t(' pro Stunde',' per hour'):'')+(d.ok===false&&d.why?' · '+d.why:'')):t('nicht gesetzt: 60 Fragen pro Stunde für alle Geräte zusammen','not set: 60 questions per hour for all devices together');
  const msg=x=>{$('ghtokmsg').textContent=x||''};
  if(open){
    $('ghtokset').onclick=async()=>{const v=$('ghtoken').value.trim();if(!v)return;try{const r=await (await api('/api/admin/ghtoken',xjson('PUT',{token:v}))).json();$('ghtoken').value='';GH_EDIT=false;await ghAdmin();msg(r.ok?t('Gespeichert und geprüft.','Saved and checked.'):t('Gespeichert, aber: ','Saved, but: ')+(r.why||''))}catch(e){msg(e.message)}};
    $('ghtokcheck').onclick=async()=>{try{const r=await (await api('/api/admin/ghtoken/check',{method:'POST'})).json();GH_EDIT=false;await ghAdmin();msg(r.ok?t('Token funktioniert.','Token works.'):(r.why||t('Geht nicht.','Does not work.')))}catch(e){msg(e.message)}};
    if($('ghtokcancel'))$('ghtokcancel').onclick=()=>{GH_EDIT=false;ghAdmin()};
  }else $('ghtokedit').onclick=()=>{GH_EDIT=true;ghAdmin().then(()=>{const i=$('ghtoken');if(i)i.focus()})};
  $('ghtokdel').onclick=async()=>{if(!confirm(t('Token vom Spark entfernen? Widerrufen kannst du ihn auf GitHub.','Remove the token from the Spark? You revoke it on GitHub.')))return;try{await api('/api/admin/ghtoken',{method:'DELETE'});GH_EDIT=false;ghAdmin()}catch(e){msg(e.message)}}}
