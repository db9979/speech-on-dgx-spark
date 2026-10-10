// Ich → Mein Zustand (hintergrund.py): what the Spark does in the background for this profile and whether
// its connected services answer. The server sends fixed words and numbers; names the person gave (documents,
// mailboxes, devices) go in with esc() only. bgCard(el) draws the card into any element (later Ich → Heute).
let MYST_ON=false,bgTimer=null,BGOPEN=new Set();
const bgW=a=>Array.isArray(a)?t(a[0],a[1]):'';
const bgWhen=s=>{if(!s)return '';const d=new Date(s*1000),now=new Date(),same=d.toDateString()===now.toDateString();
  return same?d.toLocaleTimeString([], {hour:'2-digit',minute:'2-digit'}):d.toLocaleString([], {weekday:'short',hour:'2-digit',minute:'2-digit'})};
const BGSTATE={run:['läuft','running'],wait:['wartet','waiting'],ok:['in Ordnung','fine'],bad:['braucht dich','needs you'],idle:['noch nichts','nothing yet']};
const BGACT={rmsync:['/api/profile/remarkable/sync',['Jetzt abgleichen','Compare now']],conrefresh:['/api/profile/contacts/refresh',['Jetzt holen','Fetch now']]};
function bgLine(s){const p=[];if(s.bad)p.push(t(`${s.bad} gestört`,`${s.bad} with a problem`));if(s.run)p.push(t(`${s.run} läuft`,`${s.run} running`));
  if(s.wait)p.push(t(`${s.wait} wartet`,`${s.wait} waiting`));if(s.ok)p.push(t(`${s.ok} in Ordnung`,`${s.ok} fine`));return p.join(' · ')}
function bgRow(r){const tag=r.why_text?bgW(r.why_text):t(...BGSTATE[r.state]||['','']);
  const bits=[];if(r.label)bits.push('„'+esc(r.label)+'“');const det=bgW(r.detail);if(det)bits.push(esc(det));
  if(r.last)bits.push(esc(t('zuletzt ','last ')+bgWhen(r.last)));if(r.next)bits.push(esc(t('nächstes Mal ','next ')+bgWhen(r.next)));
  const bar=r.total?`<div class="bgbar"><i style="width:${Math.max(0,Math.min(100,Math.round(100*(r.done||0)/r.total)))}%"></i></div>`:'';
  const act=r.act&&BGACT[r.act]&&!r.app?`<button class="b" type="button" data-bgact="${esc(r.act)}">${esc(t(...BGACT[r.act][1]))}</button>`:'';
  const go=r.go&&document.getElementById(r.go)?`<button class="b" type="button" data-bggo="${esc(r.go)}">${esc(t('Öffnen','Open'))}</button>`:'';
  const hk=r.key+'|'+(r.label||''),open=BGOPEN.has(hk),hist=(r.hist||[]);
  const hb=hist.length?`<button class="b" type="button" data-bghist="${esc(hk)}">${esc(open?t('Weniger','Less'):t('Verlauf','History'))}</button>`:'';
  const hl=open&&hist.length?`<ul class="bghist">${hist.slice().reverse().slice(0,14).map(([ts,ok,n])=>`<li>${esc(bgWhen(ts))} · ${ok?esc(t('erledigt','done')):esc(t('nicht geklappt','failed'))}${n?' · '+n:''}</li>`).join('')}</ul>`:'';
  return `<div class="bgrow"><span class="bgdot ${esc(r.state)}"></span><div><b>${esc(bgW(r.name))}</b><span class="bgtag ${esc(r.state)}">${esc(tag)}</span>
    <div class="bgd">${bits.join(' · ')}</div>${bar}</div><div class="bgbtns">${act}${hb}${go}</div>${hl}</div>`}
async function bgCard(el,d){if(!el)return;
  if(!d){try{d=await (await api('/api/profile/hintergrund')).json()}catch(e){el.innerHTML=`<div class="fh">${esc(e.message)}</div>`;return}}
  const s=d.sum||{},rows=d.rows||[],jobs=rows.filter(r=>r.area==='jobs'),svc=rows.filter(r=>r.area==='services');
  const need=rows.filter(r=>r.state==='bad');
  const head=need.length?[need.length===1?t(`${bgW(need[0].name)} braucht dich`,`${bgW(need[0].name)} needs you`):t(`${need.length} Dinge brauchen dich`,`${need.length} things need you`),'bad']
    :s.run?[t('Der Spark arbeitet für dich.','The Spark is working for you.'),'run']:rows.length?[t('Alles in Ordnung.','All fine.'),'ok']:[t('Für dich läuft nichts im Hintergrund.','Nothing runs in the background for you.'),'idle'];
  const when=d.now?bgWhen(d.now):'';
  const html=`<div class="bgsum"><span class="bgdot ${head[1]}"></span><div><b>${esc(head[0])}</b><span>${esc(bgLine(s))}${when?' · '+esc(t('Stand ','as of ')+when):''}</span></div></div>`+
    (jobs.length?`<h3 class="sec">${esc(t('Im Hintergrund','In the background'))}</h3><div>${jobs.map(bgRow).join('')}</div>`:'')+
    (svc.length?`<h3 class="sec">${esc(t('Verbunden','Connected'))}</h3><div>${svc.map(bgRow).join('')}</div>`:'')+
    `<div class="fh">${esc(t('Nur was bei dir an und verbunden ist. Inhalte von Mails und Dokumenten stehen hier nie; der Stand eines Dienstes ist die letzte echte Abfrage.','Only what is on and connected for you. Contents of mails and documents never appear here; a service shows the outcome of its last real request.'))}</div>`;
  // a refresh that changed nothing leaves the card alone; one that did keeps where the page was scrolled to
  bgDotSet(s);if(el.dataset.bghtml===html)return;
  let sc=el.parentElement;while(sc&&sc.scrollHeight<=sc.clientHeight)sc=sc.parentElement;const top=sc?sc.scrollTop:0,wy=window.scrollY;
  el.style.minHeight=el.offsetHeight+'px';el.innerHTML=html;el.dataset.bghtml=html;el.style.minHeight='';
  if(sc)sc.scrollTop=top;if(window.scrollY!==wy)window.scrollTo(0,wy);
  el.querySelectorAll('[data-bggo]').forEach(b=>b.onclick=()=>{meLast=b.dataset.bggo;ptab(b.dataset.bggo)});
  el.querySelectorAll('[data-bghist]').forEach(b=>b.onclick=()=>{const k=b.dataset.bghist;BGOPEN.has(k)?BGOPEN.delete(k):BGOPEN.add(k);bgCard(el,d)});
  el.querySelectorAll('[data-bgact]').forEach(b=>b.onclick=async()=>{b.disabled=true;
    try{await api(BGACT[b.dataset.bgact][0],{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'})}catch(e){alert(e.message)}setTimeout(()=>bgCard(el),800)})}
async function showBg(){const box=$('bgbox');if(!box)return;clearTimeout(bgTimer);if(!PROFILE||!MYST_ON){box.innerHTML='';return}
  box.innerHTML=`<div class="intro">${esc(t('Was der Spark gerade für dich erledigt, worauf es wartet und ob deine verbundenen Dienste antworten. Nur deine eigenen Sachen, nur Namen und Zahlen.','What the Spark is doing for you right now, what it waits for and whether your connected services answer. Only your own things, only names and numbers.'))}</div>
    ${xsw('my_status',t('Mein Zustand anzeigen','Show my status'),t('Aus: Die Seite bleibt leer und der Punkt bei „Ich“ kommt nicht.','Off: the page stays empty and the dot at "Me" does not come.'))}<div id="bgcard"></div>`;
  xbind(box,showBg);
  if(!S.my_status){bgDotSet(null);return}
  await bgCard($('bgcard'));bgFollow()}
// while the page is open it follows the work every 10 seconds; only the card is redrawn (V01.0.293: the whole
// page was rebuilt before, which threw the page back to the top)
function bgFollow(){clearTimeout(bgTimer);bgTimer=setTimeout(async()=>{const box=$('bgbox'),card=$('bgcard');
  if(!box||!card||!box.classList.contains('on')||!$('profmodal')||$('profmodal').style.display==='none')return;
  if(!document.hidden&&S.my_status)await bgCard(card);bgFollow()},10e3)}
function bgDotSet(s){document.querySelectorAll('.medot').forEach(e=>e.hidden=!(s&&s.need))}
async function bgDot(){if(!PROFILE||!MYST_ON||!S.my_status||document.hidden){if(!MYST_ON||!S.my_status)bgDotSet(null);return}
  try{const r=await fetch('/api/profile/hintergrund?brief=1',{cache:'no-store'});if(r.ok)bgDotSet((await r.json()).sum)}catch{}}
setInterval(bgDot,60e3);setTimeout(bgDot,3e3);
// Zustand → Monitoring "Mein Zustand aller Profile" (admin): counts only, shown while the admin switch is on
async function zBg(){const box=$('zbg');if(!box||document.hidden)return;let d={on:false};
  try{const r=await fetch('/api/admin/hintergrund',{cache:'no-store'});if(!r.ok)return;d=await r.json()}catch{return}
  box.hidden=!d.on;if(!d.on)return;
  const part=(x,de,en)=>`<div class="zrow"><span class="pill ${x.bad?'bad':x.wait?'warn':'ok'}">${esc(t(de,en))}</span><span>${esc(bgLine(x)||t('nichts','nothing'))}</span></div>`;
  $('zbglist').innerHTML=`<div class="zrow"><span class="pill">${d.profiles}</span><span>${esc(t('Profile nutzen die Seite','profiles use the page'))}${d.need?' · '+esc(t(`${d.need} Dinge brauchen ihre Besitzer`,`${d.need} things need their owners`)):''}</span></div>`+
    part(d.jobs,'Im Hintergrund','In the background')+part(d.services,'Verbunden','Connected')}
