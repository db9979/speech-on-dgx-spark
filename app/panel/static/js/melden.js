// Probleme melden (meldung.py, plan probleme-melden.md): a report as a GitHub issue. The page only shows: the Spark
// builds the draft, anonymizes it with fixed rules and signs the exact preview; "An GitHub senden" sends only that.
// Ich → Probleme melden (profiles), the window from the footer, Strg/⌘ K and Logs (admins see every report there).
// Everything from the server is text (esc / textContent), GitHub's answers too.
let RP_ON=false;
const RP={d:null,cur:null,skip:new Set(),root:null,busy:false,thread:null};
const RP_ST={entwurf:['Entwurf','Draft'],gesendet:['gesendet','sent'],lokal:['nur lokal','local only'],sendet:['wird gesendet','sending']};
const RP_CH={panel:['Panel','panel'],app:['iPhone-App','iPhone app'],android:['Android-App','Android app'],telegram:['Telegram','Telegram'],
  sprache:['Sprache','voice'],esp32:['Lautsprecher','speaker'],pebble:['Pebble-Uhr','Pebble watch'],begleiter:['Begleiter','companion']};
const RP_PART={requests:['Anfrage','request'],lines:['Logzeile','log line'],applog:['App','app'],system:['System','system']};
const rpWhen=x=>x?new Date(x*1000).toLocaleString([], {dateStyle:'short',timeStyle:'short'}):'';
const rpArea=k=>{const a=((RP.d||{}).areas||[]).find(x=>x.key===k);return a?t(a.name[0],a.name[1]):k};
function rpMsg(x,err){const m=RP.root&&RP.root.querySelector('.rpmsg');if(m){m.textContent=x||'';m.className='fh rpmsg'+(err?' err':'')}}
async function rpLoad(){const r=await fetch('/api/report',{cache:'no-store'});
  if(!r.ok){let x='';try{x=(await r.json()).detail}catch{}throw Object.assign(new Error(x||t('Gerade nicht erreichbar.','Not reachable right now.')),{status:r.status})}
  RP.d=await r.json();return RP.d}
// ---------------------------------------------------------------- the list and the form
async function rpList(root){RP.root=root;RP.cur=null;RP.thread=null;
  const intro=`<div class="intro">${t('Beschreib kurz, was nicht geklappt hat. Der Spark legt einen Entwurf an, ersetzt Namen, Mail-Adressen, Adressen und Inhalte durch Platzhalter und zeigt dir genau, was rausgehen würde. Erst nach deinem Blick geht es als Meldung (Issue) an GitHub.','Describe briefly what went wrong. The Spark makes a draft, replaces names, mail addresses, addresses and contents with placeholders and shows you exactly what would go out. Only after your look does it go to GitHub as a report (issue).')}</div>`;
  let d;try{d=await rpLoad()}catch(e){root.innerHTML=intro+`<div class="fh err">${esc(e.message)}</div>`;return}
  const opts=(xs,f)=>xs.map(f).join('');
  const item=x=>{const st=RP_ST[x.status]||[x.status,x.status],gh=x.gh?` · ${esc(x.gh.state==='erledigt'?t('erledigt','done'):t('offen','open'))}${x.gh.comments?' · '+x.gh.comments+' '+esc(t(x.gh.comments===1?'Antwort':'Antworten',x.gh.comments===1?'answer':'answers')):''}`:'';
    return `<li><span><b>${esc(rpArea(x.area))}</b> <em class="pill${x.status==='gesendet'?' ok':''}">${esc(t(st[0],st[1]))}</em>${gh}<br>
      <small class="mut">${esc(rpWhen(x.t))} · ${esc(t(...(RP_CH[x.channel]||[x.channel,x.channel])))}${x.by?' · '+esc(x.by):''}${x.issue&&x.issue.number?' · #'+x.issue.number:''}</small><br>
      <small>${esc(x.text||'')}</small></span><span class="rpbtns">
      ${x.status==='entwurf'?`<button class="b" type="button" data-rpopen="${esc(x.id)}">${esc(t('Ansehen','View'))}</button>`:''}
      ${x.status==='gesendet'&&d.token?`<button class="b" type="button" data-rpthread="${esc(x.id)}">${esc(t('Antworten','Answers'))}</button>`:''}
      ${x.issue&&x.issue.url?`<a class="b" href="${esc(x.issue.url)}" target="_blank" rel="noopener noreferrer">GitHub</a>`:''}
      <button class="b" type="button" data-rpdel="${esc(x.id)}">${esc(t('Löschen','Delete'))}</button></span></li>`};
  const nsw=PROFILE&&root.id==='rpbox'&&d.notify?xsw('report_notify',t('Mich über neue Meldungen informieren','Tell me about new reports'),t('Als Admin sagt dir der Assistent, wenn ein Profil eine Meldung sendet oder ablegt: wer, Bereich und Weg, nie der Text. Aus: keine Nachricht an dich.','As an admin the assistant tells you when a profile sends or keeps a report: who, area and way, never the text. Off: no note to you.')):'';
  root.innerHTML=intro+nsw+`
    <label for="rp_text_${root.id}">${esc(t('Was ist passiert?','What happened?'))}</label>
    <textarea id="rp_text_${root.id}" class="rptext" rows="4" maxlength="${d.max_text||2000}" placeholder="${esc(t('z. B. „Der Lautsprecher in der Küche hat um 7 Uhr nicht geantwortet.“','e.g. "The kitchen speaker did not answer at 7."'))}"></textarea>
    <div class="rowin rpsel"><select class="rparea" aria-label="${esc(t('Bereich','Area'))}">${opts(d.areas,a=>`<option value="${esc(a.key)}"${a.key==='sonstiges'?' selected':''}>${esc(t(a.name[0],a.name[1]))}</option>`)}</select>
      <select class="rpmin" aria-label="${esc(t('Zeitraum','Time window'))}">${opts(d.minutes,m=>`<option value="${m}"${m===30?' selected':''}>${esc(t('letzte '+m+' Minuten','last '+m+' minutes'))}</option>`)}</select></div>
    <label class="chk"><input type="checkbox" class="rpreq" checked> ${esc(t('Meine letzten Anfragen (nur Wege, Werkzeuge, Zeiten)','My last requests (only ways, tools, times)'))}</label>
    <label class="chk"><input type="checkbox" class="rpsys" checked> ${esc(t('Systemzustand (Version, Dienste, Speicher)','System state (version, services, memory)'))}</label>
    ${d.logs?`<label class="chk"><input type="checkbox" class="rplogs"> ${esc(t('Diagnose-Logzeilen des ganzen Spark (anonymisiert)','Diagnose log lines of the whole Spark (anonymized)'))}</label>`:''}
    <div class="row" style="margin-top:8px"><button class="b p" type="button" data-rpmake="1">${esc(t('Entwurf anlegen und ansehen','Make draft and view'))}</button></div>
    <div class="fh">${esc(t('Ziel: GitHub-Repo ','Target: GitHub repository '))}<b>${esc(d.repo)}</b>${d.token?'':esc(t(' · noch kein Token: Senden geht dann über „Im Browser öffnen“.',' · no token yet: sending then goes through "Open in the browser".'))}</div>
    <div class="fh rpmsg" role="status"></div>
    <h3 style="margin:14px 0 4px">${esc(d.staff?t('Alle Meldungen','All reports'):t('Meine Meldungen','My reports'))}</h3>
    <ul class="facts rplist">${d.items.map(item).join('')||`<li class="mut"><span>${esc(t('Noch keine.','None yet.'))}</span></li>`}</ul>`;
  if(nsw)xbind(root,()=>rpList(root));
  root.querySelector('[data-rpmake]').onclick=async e=>{const b=e.currentTarget;if(RP.busy)return;RP.busy=true;b.disabled=true;rpMsg(t('Lege an und anonymisiere …','Making and anonymizing …'));
    const q=s=>root.querySelector(s);
    try{const r=await (await api('/api/report/draft',xjson('POST',{text:q('.rptext').value,area:q('.rparea').value,minutes:+q('.rpmin').value,
        requests:q('.rpreq').checked,system:q('.rpsys').checked,logs:!!(q('.rplogs')&&q('.rplogs').checked)}))).json();
      RP.skip=new Set();rpShow(root,r)}
    catch(x){rpMsg(x.message,true)}finally{RP.busy=false;b.disabled=false}};
  root.querySelectorAll('[data-rpopen]').forEach(b=>b.onclick=async()=>{try{const r=await (await api('/api/report?id='+encodeURIComponent(b.dataset.rpopen))).json();RP.skip=new Set();rpShow(root,r)}catch(x){rpMsg(x.message,true)}});
  root.querySelectorAll('[data-rpthread]').forEach(b=>b.onclick=()=>rpThread(root,b.dataset.rpthread));
  root.querySelectorAll('[data-rpdel]').forEach(b=>b.onclick=async()=>{if(!confirm(t('Diese Meldung auf dem Spark löschen? Auf GitHub bleibt eine gesendete Meldung.','Delete this report on the Spark? A sent report stays on GitHub.')))return;
    try{await api('/api/report/delete',xjson('POST',{id:b.dataset.rpdel}));rpList(root)}catch(x){rpMsg(x.message,true)}})}
// ---------------------------------------------------------------- the preview
function rpCounts(c){const n=Object.entries(c||{}).filter(([,v])=>v);return n.length?n.map(([k,v])=>`${v}× [${k}]`).join(', '):t('nichts','nothing')}
function rpShow(root,r){RP.root=root;RP.cur=r;const p=r.preview||{};
  root.innerHTML=`<div class="row"><button class="b" type="button" data-rpback="1">‹ ${esc(t('Zurück','Back'))}</button></div>
    <h3 style="margin:10px 0 4px">${esc(t('Vorschau: genau das geht raus','Preview: exactly this goes out'))}</h3>
    <div class="fh">${esc(t('Ersetzt: ','Replaced: '))}${esc(rpCounts(r.counts))}. ${esc(t('Haken weg = diese Zeile geht nicht mit.','Untick = this line stays here.'))}</div>
    <div class="fh err rpleak" hidden></div>
    <ul class="facts rplines">${(r.lines||[]).map(x=>`<li><label class="chk"><input type="checkbox" data-rpline="${x.n}"${RP.skip.has(x.n)?'':' checked'}> <small class="mut">${esc(t(...(RP_PART[x.part]||[x.part,x.part])))}</small> <code></code></label></li>`).join('')
      ||`<li class="mut"><span>${esc(t('Keine Logzeilen dabei.','No log lines included.'))}</span></li>`}</ul>
    <details open><summary>${esc(t('Text der Meldung','Text of the report'))}</summary><b class="rptitle"></b><pre class="rpbody"></pre></details>
    <div class="row rpgo" style="margin-top:8px;flex-wrap:wrap;gap:6px">
      <button class="b p" type="button" data-rpsend="gh">${esc(t('An GitHub senden','Send to GitHub'))}</button>
      <button class="b" type="button" data-rpsend="browser">${esc(t('Im Browser öffnen','Open in the browser'))}</button>
      <button class="b" type="button" data-rpsend="local">${esc(t('Nur lokal behalten','Keep locally only'))}</button></div>
    <div class="fh rpmsg" role="status"></div>`;
  // log lines as text only, never as markup
  root.querySelectorAll('.rplines code').forEach((c,i)=>{c.textContent=r.lines[i].line});
  rpPaint(root,p);
  root.querySelector('[data-rpback]').onclick=()=>rpList(root);
  root.querySelectorAll('[data-rpline]').forEach(cb=>cb.onchange=async()=>{const n=+cb.dataset.rpline;if(cb.checked)RP.skip.delete(n);else RP.skip.add(n);
    try{rpPaint(root,await (await api('/api/report/preview',xjson('POST',{id:r.id,skip:[...RP.skip]}))).json())}catch(x){rpMsg(x.message,true)}});
  root.querySelectorAll('[data-rpsend]').forEach(b=>b.onclick=()=>rpSend(root,b.dataset.rpsend,b))}
function rpPaint(root,p){RP.cur.preview=p;root.querySelector('.rptitle').textContent=p.title||'';root.querySelector('.rpbody').textContent=p.body||'';
  const lk=root.querySelector('.rpleak');lk.hidden=!(p.leaks&&p.leaks.length);
  lk.textContent=p.leaks&&p.leaks.length?t('Die Prüfung hat noch etwas gefunden: ','The check still found something: ')+p.leaks.join(', ')+t('. Bitte die betroffenen Zeilen abwählen; so geht nichts raus.','. Please untick the lines concerned; nothing goes out like this.'):'';
  const gh=root.querySelector('[data-rpsend=gh]');gh.disabled=!p.sig||!(RP.d&&RP.d.token);root.querySelector('[data-rpsend=browser]').disabled=!p.sig;
  if(RP.d&&!RP.d.token)gh.title=t('Kein Token: der Admin trägt ihn unter Funktionen → Probleme melden ein.','No token: the admin enters it under Features → Reporting problems.')}
async function rpSend(root,how,b){const r=RP.cur,p=r.preview||{};if(RP.busy)return;RP.busy=true;b.disabled=true;
  const body={id:r.id,skip:[...RP.skip],sig:p.sig};if(how==='browser')body.browser=true;if(how==='local')body.local=true;
  // the window opens right away (a later window.open after await is blocked by browsers); it gets the address next
  const w=how==='browser'?window.open('about:blank','_blank'):null;if(w)try{w.opener=null}catch{}
  try{const x=await (await api('/api/report/send',xjson('POST',body))).json();
    if(how==='browser'){if(w&&/^https:\/\/github\.com\//.test(x.url||''))w.location.href=x.url;rpMsg(t('GitHub ist offen: dort prüfen und absenden.','GitHub is open: check and submit there.'));return}
    await rpList(root);rpMsg(how==='local'?t('Bleibt nur auf dem Spark.','Stays on the Spark only.'):t('Gesendet','Sent')+(x.issue&&x.issue.number?' (#'+x.issue.number+')':'')+'.')}
  catch(e){if(w)w.close();rpMsg(e.message,true)}finally{RP.busy=false;b.disabled=false}}
// ---------------------------------------------------------------- GitHub's answers (text only)
async function rpThread(root,id){RP.root=root;
  root.innerHTML=`<div class="row"><button class="b" type="button" data-rpback="1">‹ ${esc(t('Zurück','Back'))}</button></div><div class="fh rpmsg" role="status">${esc(t('Hole den Stand von GitHub …','Fetching the state from GitHub …'))}</div><ul class="facts rpans"></ul>`;
  root.querySelector('[data-rpback]').onclick=()=>rpList(root);
  try{const d=await (await api('/api/report/thread',xjson('POST',{id}))).json();
    rpMsg(t('Stand: ','State: ')+(d.state==='erledigt'?t('erledigt','done'):t('offen','open'))+' · '+d.answers.length+' '+t('Antworten','answers'));
    const ul=root.querySelector('.rpans');
    if(!d.answers.length){ul.innerHTML=`<li class="mut"><span>${esc(t('Noch keine Antwort.','No answer yet.'))}</span></li>`;return}
    for(const a of d.answers){const li=document.createElement('li'),s=document.createElement('span'),h=document.createElement('small'),p=document.createElement('div');
      h.className='mut';h.textContent=a.by+' · '+(a.t||'').replace('T',' ').replace('Z','');p.className='rpanswer';p.textContent=a.text;s.append(h,p);li.append(s);ul.append(li)}}
  catch(e){rpMsg(e.message,true)}}
// ---------------------------------------------------------------- Ich page, window, admin settings
async function showReport(){const box=$('rpbox');if(!box)return;if(!PROFILE||!RP_ON){box.innerHTML='';return}
  if(RP.root===box&&(RP.cur||RP.thread))return;await rpList(box)}
function rpOpen(){if(typeof closeSheet==='function')closeSheet();$('rpmodal').style.display='grid';rpList($('rpbody'))}
function rpClose(){$('rpmodal').style.display='none';if(RP.root===$('rpbody'))RP.root=null}
ON.rpOpen=()=>rpOpen();ON.rpClose=()=>rpClose();
$('rpmodal').addEventListener('click',e=>{if(e.target===$('rpmodal'))rpClose()});
document.addEventListener('keydown',e=>{if(e.key==='Escape'&&$('rpmodal').style.display==='grid')rpClose()});
// the admin: the GitHub token (Funktionen → Probleme melden), shown as set / until when, never itself
async function rpAdmin(){const box=$('rpadmin');if(!box||!ADMIN)return;let d;try{d=await (await api('/api/admin/report')).json()}catch{box.textContent='';return}
  box.innerHTML=`<div class="setrow"><div class="lbl"><b>${esc(t('GitHub-Token','GitHub token'))}</b><span class="rptok"></span></div>
    <div class="ctl full"><input type="password" id="rptoken" maxlength="300" autocomplete="off" placeholder="github_pat_…" aria-label="${esc(t('Neuer Token','New token'))}"><button class="b" type="button" id="rptokset">${esc(t('Speichern','Save'))}</button></div></div>
    <div class="row" style="gap:6px"><button class="b" type="button" id="rptokcheck"${d.set?'':' disabled'}>${esc(t('Prüfen','Check'))}</button><button class="b" type="button" id="rptokdel"${d.set?'':' disabled'}>${esc(t('Entfernen','Remove'))}</button><button class="b" type="button" data-on="rpOpen">${esc(t('Meldungen ansehen','View reports'))}</button></div>
    <div class="fh">${esc(t('So bekommst du ihn: github.com → Settings → Developer settings → Fine-grained tokens → Generate new token. Repository access: „Only select repositories“ und nur ','How to get it: github.com → Settings → Developer settings → Fine-grained tokens → Generate new token. Repository access: "Only select repositories" and only '))}<b>${esc(d.repo)}</b>${esc(t('. Permissions: nur „Issues: Read and write“. Ablauf: 90 Tage. Gespeichert wird er verschlüsselt und nie wieder angezeigt; Speichern fragt einen frischen Code.','. Permissions: only "Issues: Read and write". Expiry: 90 days. It is stored encrypted and never shown again; saving asks for a fresh code.'))}</div>
    <div class="fh" id="rptokmsg" role="status"></div>`;
  const st=box.querySelector('.rptok');st.textContent=d.set?(t('gesetzt','set')+(d.until?t(', läuft bis ',', valid until ')+d.until:'')+(d.ok===false&&d.why?' · '+d.why:d.ok?' · '+t('geprüft','checked'):'')):t('nicht gesetzt: Senden geht nur über „Im Browser öffnen“','not set: sending only through "Open in the browser"');
  const msg=x=>{$('rptokmsg').textContent=x||''};
  $('rptokset').onclick=async()=>{const v=$('rptoken').value.trim();if(!v)return;try{const r=await (await api('/api/admin/report/token',xjson('PUT',{token:v}))).json();$('rptoken').value='';await rpAdmin();msg(r.ok?t('Gespeichert und geprüft.','Saved and checked.'):t('Gespeichert, aber: ','Saved, but: ')+(r.why||''))}catch(e){msg(e.message)}};
  $('rptokcheck').onclick=async()=>{try{const r=await (await api('/api/admin/report/check',{method:'POST'})).json();await rpAdmin();msg(r.ok?t('Token funktioniert.','Token works.')+(r.why?' '+r.why:''):(r.why||t('Geht nicht.','Does not work.')))}catch(e){msg(e.message)}};
  $('rptokdel').onclick=async()=>{if(!confirm(t('Token vom Spark entfernen? Widerrufen kannst du ihn auf GitHub.','Remove the token from the Spark? You revoke it on GitHub.')))return;try{await api('/api/admin/report/token',{method:'DELETE'});rpAdmin()}catch(e){msg(e.message)}}}
// after /api/whoami (start.js): the footer link, the Logs button, "#melden" from the apps and the companion
function rpStart(who){RP_ON=!!(who&&who.report);const may=RP_ON&&(!!who.admin||!!who.profile);
  $('rpfoot').hidden=!may;const lb=$('logrp');if(lb)lb.hidden=!(RP_ON&&who.admin);
  if(who&&who.admin)rpAdmin();
  if(may&&location.hash==='#melden'){try{history.replaceState(null,'',location.pathname+location.search)}catch{}rpOpen()}}
