// Spark-Konsole (konsole.html, ../../konsole.py, plan spark-entkoppeln E4): the model computer's own page. Login and
// codes are the panel's (/api/login, x-speech-code on 428); the pages read the panel's own answers (/api/status,
// /api/admin/spark-clients, /api/admin/modelle, /api/update, /api/logs, /api/konsole/koppeln). Every name, number and
// log line goes through esc().
'use strict';
const EN=!/^de\b/i.test(navigator.language||'de');
const t=(de,en)=>EN?en:de;
const $=id=>document.getElementById(id);
const esc=s=>String(s==null?'':s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const RECHT={llm:t('Sprachmodell','Language model'),sehen:t('Bilder verstehen','Understand pictures'),helfer:t('Hilfsmodell','Helper model'),
  systemone:t('Einordnen (System One)','Classify (System One)'),asr:t('Hören','Listening'),tts:t('Sprechen','Speaking'),bild:t('Bilder','Pictures'),musik:t('Musik','Music')};
const KLASSE={sprache:t('Sprache','Speech'),dialog:t('Dialog','Dialogue'),hintergrund:t('Hintergrund','Background')};
const DIENST={asr:t('Spracherkennung','Speech recognition'),tts:t('Sprachausgabe','Speech output'),llm:t('Sprachmodell','Language model'),
  llmtor:'LLM-Tor',sehen:t('Sehen','Vision'),helfer:t('Hilfsmodell','Helper model'),bild:t('Bilder','Pictures'),musik:t('Musik','Music')};
const LOGS=['llm','llmtor','asr','asr-engine','tts','tts-engine','update','konsole'];
let TAB='ueberblick',TIMER=null,CODE_WAIT=null;

// one fetch for every call: a 428 asks for the code once and repeats the call with it
async function api(path,opt={},code){
  const o=Object.assign({cache:'no-store',credentials:'same-origin'},opt);
  o.headers=Object.assign({},opt.headers||{},code?{'x-speech-code':code}:{});
  const r=await /*raw: the console loads without base.js*/fetch(path,o);
  if(r.status===428&&!code){const c=await askCode();if(c)return api(path,opt,c);throw new Error(t('Abgebrochen.','Cancelled.'))}
  if(r.status===401){showLogin();throw new Error(t('Bitte anmelden.','Please sign in.'))}
  if(!r.ok){let d='';try{d=(await r.json()).detail}catch{}throw new Error(typeof d==='string'&&d?d:t('Fehler ','Error ')+r.status)}
  return r}
const post=(path,body)=>api(path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body||{})}).then(r=>r.json());
function askCode(){$('kcin').value='';$('kcode').hidden=false;$('kcin').focus();return new Promise(res=>{CODE_WAIT=res})}
function codeDone(v){$('kcode').hidden=true;const f=CODE_WAIT;CODE_WAIT=null;if(f)f(v)}

function showLogin(){clearInterval(TIMER);$('klogin').hidden=false;$('ktabs').hidden=true;$('kout').hidden=true;
  document.querySelectorAll('.tab').forEach(x=>x.hidden=true);$('klpw').focus()}
async function login(e){e.preventDefault();const m=$('klmsg');m.textContent='';
  const body={password:$('klpw').value};if(!$('klcode').hidden)body.code=$('klcode').value.trim();
  try{const r=await /*raw: the console loads without base.js*/fetch('/api/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
    if(!r.ok){m.textContent=r.status===429?t('Zu viele Versuche, bitte warten.','Too many tries, please wait.'):t('Passwort oder Code stimmt nicht.','Password or code is wrong.');return}
    const d=await r.json();if(d.code){$('klcode').hidden=false;$('klcode').focus();m.textContent=t('Jetzt den Code aus der App.','Now the code from the app.');return}
    $('klpw').value='';$('klcode').value='';$('klcode').hidden=true;start()}
  catch{m.textContent=t('Keine Verbindung.','No connection.')}}

async function start(){let w;try{w=await (await /*raw: the console loads without base.js*/fetch('/api/whoami',{cache:'no-store'})).json()}catch{w={}}
  if(!w.admin){showLogin();return}
  $('klogin').hidden=true;$('ktabs').hidden=false;$('kout').hidden=false;
  $('kstate').innerHTML=`<span class="dot"></span>${esc(w.version||'')} · ${esc(t('nur Heimnetz','home network only'))}`;
  show((location.hash||'#ueberblick').slice(1))}

const TABS=['ueberblick','modelle','clients','assistent','updates','logs'];
function show(tab){if(!TABS.includes(tab))tab='ueberblick';TAB=tab;
  document.querySelectorAll('#ktabs a').forEach(a=>a.classList.toggle('on',a.dataset.tab===tab));
  document.querySelectorAll('.tab').forEach(x=>x.hidden=x.id!=='tab-'+tab);clearInterval(TIMER);
  ({ueberblick,modelle,clients,assistent,updates,logs})[tab]();if(tab==='ueberblick')TIMER=setInterval(ueberblick,3000)}

const pct=(a,b)=>b?Math.max(0,Math.min(100,Math.round(a/b*100))):0;
const zust=s=>s==='active'?`<span class="pill ok">${esc(t('bereit','ready'))}</span>`:s==='inactive'?`<span class="pill grey">${esc(t('aus','off'))}</span>`:
  s==='failed'?`<span class="pill bad">${esc(t('Fehler','error'))}</span>`:s==='activating'?`<span class="pill warn">${esc(t('startet','starting'))}</span>`:
  `<span class="pill grey">${esc(t('unbekannt','unknown'))}</span>`;
async function ueberblick(){const el=$('tab-ueberblick');let d;
  try{d=await (await api('/api/status')).json()}catch(e){el.innerHTML=`<p class="k">${esc(e.message)}</p>`;return}
  const g=d.gpu||{},s=d.system||{},used=(s.mem_total_gib||0)-(s.mem_avail_gib||0);
  const rows=Object.entries(d.services||{}).map(([n,v])=>`<tr><td>${esc(DIENST[n]||n)}</td><td class="mono">${esc(v.port||'')}</td><td>${zust(v.state)}</td></tr>`+
    (v.engines||[]).map(x=>`<tr><td class="k">↳ ${esc(x.name)} · ${esc(x.model||'')}</td><td class="mono">${esc(x.port||'')}</td><td>${zust(x.state)}</td></tr>`).join('')).join('');
  const al=(d.alerts||[]).map(a=>`<div class="row"><span class="pill warn">${esc(t('Hinweis','Note'))}</span> ${esc(a.text||a.message||a)}</div>`).join('');
  el.innerHTML=`<h1>${esc(t('Überblick','Overview'))}</h1><div class="k">${esc(t('Aktualisiert alle 3 Sekunden.','Refreshed every 3 seconds.'))}</div>
    <div class="g4">
      <div class="card"><div class="k">GPU</div><div class="big">${esc(g.util??'–')} %</div><div class="k">${esc(g.temp??'–')} °C · ${esc(g.power??'–')} W</div><div class="bar"><i style="width:${pct(g.util||0,100)}%"></i></div></div>
      <div class="card"><div class="k">${esc(t('Speicher (gemeinsam)','Memory (shared)'))}</div><div class="big">${esc(Math.round(used))} / ${esc(Math.round(s.mem_total_gib||0))} GiB</div><div class="k">${esc(t('frei','free'))} ${esc(Math.round(s.mem_avail_gib||0))} GiB</div><div class="bar"><i style="width:${pct(used,s.mem_total_gib)}%"></i></div></div>
      <div class="card"><div class="k">CPU</div><div class="big">${esc(Math.round(s.cpu||0))} %</div><div class="bar"><i style="width:${pct(s.cpu||0,100)}%"></i></div></div>
      <div class="card"><div class="k">${esc(t('Dienste bereit','Services ready'))}</div><div class="big">${esc(Object.values(d.services||{}).filter(v=>v.state==='active').length)} / ${esc(Object.keys(d.services||{}).length)}</div></div>
    </div>
    <div class="g2"><div class="card"><h2>${esc(t('Dienste','Services'))}</h2><table><tr><th>${esc(t('Dienst','Service'))}</th><th>Port</th><th>${esc(t('Zustand','State'))}</th></tr>${rows}</table></div>
    <div class="card"><h2>${esc(t('Hinweise','Notes'))}</h2>${al||`<p class="k">${esc(t('Alles ruhig.','All quiet.'))}</p>`}</div></div>`}

let SPC=null;
async function clients(msg){const el=$('tab-clients');
  try{SPC=await (await api('/api/admin/spark-clients')).json()}catch(e){el.innerHTML=`<p class="k">${esc(e.message)}</p>`;return}
  const d=SPC,rows=d.clients.map(c=>`<tr><td><b>${esc(c.name)}</b><div class="k">${esc(c.rechte.map(x=>RECHT[x]||x).join(', '))}</div></td>
    <td><span class="pill ${c.klasse==='sprache'?'ok':'grey'}">${esc(KLASSE[c.klasse]||c.klasse)}</span></td>
    <td class="k">${esc(`${c.minute}/min · ${c.parallel} ${t('gleichzeitig','at once')} · ${c.tokens_tag} ${t('Tokens/Tag','tokens/day')}`)}${c.gesperrt?' · '+esc(t('gesperrt','blocked')):''}</td>
    <td><button class="btn sec" type="button" data-k="sperren" data-id="${esc(c.id)}">${esc(c.gesperrt?t('Entsperren','Unblock'):t('Sperren','Block'))}</button>
      <button class="btn bad" type="button" data-k="weg" data-id="${esc(c.id)}">${esc(t('Löschen','Delete'))}</button></td></tr>`).join('');
  el.innerHTML=`<h1>Clients</h1><div class="k">${esc(t('Andere Programme im Heimnetz mit eigenem Schlüssel, Rechten, Vorrangklasse und Grenzen. Der Schlüssel ist nur einmal sichtbar.','Other programs in the home network with a key of their own, rights, priority class and limits. The key is visible only once.'))}</div>
    <div class="card" style="margin-top:14px"><div class="row"><label><input type="checkbox" id="kcan"${d.an?' checked':''}> ${esc(t('Für Clients geöffnet','Open for clients'))}</label>
      <input id="kcnetze" style="flex:1" value="${esc(d.netze.join(', '))}" placeholder="192.168.178.0/24" aria-label="${esc(t('Netze im Heimnetz','Home networks'))}">
      <button class="btn sec" type="button" data-k="schalten">${esc(t('Übernehmen','Apply'))}</button></div></div>
    <div class="card" style="margin-top:14px"><table><tr><th>Client</th><th>${esc(t('Klasse','Class'))}</th><th>${esc(t('Grenzen','Limits'))}</th><th></th></tr>${rows||`<tr><td class="k" colspan="4">${esc(t('Noch kein Client.','No client yet.'))}</td></tr>`}</table></div>
    <div class="card" style="margin-top:14px"><h2>${esc(t('Neuer Client','New client'))}</h2>
      <div class="row"><input id="kcname" maxlength="40" placeholder="${esc(t('Name, z. B. Open WebUI','Name, e.g. Open WebUI'))}" aria-label="Name">
        <select id="kcklasse" aria-label="${esc(t('Vorrangklasse','Priority class'))}">${d.klassen.map(k=>`<option value="${esc(k)}"${k===d.vorgabe.klasse?' selected':''}>${esc(KLASSE[k]||k)}</option>`).join('')}</select></div>
      <div class="row">${d.rechte.map(x=>`<label><input type="checkbox" data-recht="${esc(x)}"${d.vorgabe.rechte.includes(x)?' checked':''}> ${esc(RECHT[x]||x)}</label>`).join('')}</div>
      <div class="row"><button class="btn" type="button" data-k="neu"${d.clients.length>=d.max?' disabled':''}>${esc(t('Schlüssel erzeugen','Make key'))}</button><span class="k" id="kcmsg">${esc(msg||'')}</span></div>
      <div id="kckey" hidden><div class="k">${esc(t('Nur jetzt sichtbar. Im Programm als API-Schlüssel eintragen (Bearer).','Visible only now. Enter it in the program as the API key (Bearer).'))}</div><div class="key mono" id="kckeyv"></div></div></div>`}
async function clientAct(a,b){const m=x=>{const el=$('kcmsg');if(el)el.textContent=x};
  try{if(a==='schalten'){const netze=$('kcnetze').value.split(',').map(x=>x.trim()).filter(Boolean);
      const d=await post('/api/admin/spark-clients/schalten',{an:$('kcan').checked,netze});return clients(d.an?t('Geöffnet.','Open.'):t('Geschlossen.','Closed.'))}
    if(a==='neu'){const rechte=[...document.querySelectorAll('[data-recht]')].filter(x=>x.checked).map(x=>x.dataset.recht);
      const d=await post('/api/admin/spark-clients/neu',{name:$('kcname').value,rechte,klasse:$('kcklasse').value});
      await clients();$('kckeyv').textContent=d.key;$('kckey').hidden=false;return}
    const c=(SPC.clients||[]).find(x=>x.id===b.dataset.id);if(!c)return;
    if(a==='sperren')await post('/api/admin/spark-clients/aendern',{id:c.id,felder:{gesperrt:!c.gesperrt}});
    if(a==='weg')await post('/api/admin/spark-clients/weg',{id:c.id});
    await clients()}
  catch(e){m(e.message)}}

const gib=x=>x==null?'–':(Math.round(x*10)/10)+' GiB';
async function modelle(){const el=$('tab-modelle');let d;
  try{d=await (await api('/api/admin/modelle?lang='+(EN?'en':'de'))).json()}catch(e){el.innerHTML=`<p class="k">${esc(e.message)}</p>`;return}
  const b=d.budget||{},teile=b.teile||[];
  const arten=(d.arten||[]).map(a=>{const rows=a.modelle.map(m=>`<tr><td><b>${esc(m.name)}</b><div class="k mono">${esc(m.engine)}</div></td>
      <td>${m.aktiv?`<span class="pill ok">${esc(t('läuft','running'))}</span>`:`<span class="pill grey">${esc(t('nicht geladen','not loaded'))}</span>`}</td>
      <td class="mono">${esc(gib(m.aktiv&&m.gib!=null?m.gib:m.need_gib))}</td>
      <td class="mono">${m.messung&&m.messung.tok_s!=null?esc(m.messung.tok_s)+' tok/s':'–'}</td></tr>`).join('');
    return rows?`<div class="card" style="margin-top:14px"><h2>${esc(a.name)}</h2><table><tr><th>${esc(t('Modell','Model'))}</th><th>${esc(t('Zustand','State'))}</th><th>${esc(t('Speicher','Memory'))}</th><th>${esc(t('Tempo','Speed'))}</th></tr>${rows}</table></div>`:''}).join('');
  el.innerHTML=`<h1>${esc(t('Modelle','Models'))}</h1><div class="k">${esc(t('Was dieser Spark lädt und wie viel Speicher es braucht. Wechseln und Messen bleiben vorerst am Assistenten oder in der Kommandozeile (sudo speech-spark modelle).','What this Spark loads and how much memory it needs. Switching and measuring stay with the assistant or the command line for now (sudo speech-spark modelle).'))}</div>
    <div class="card" style="margin-top:14px"><h2>${esc(t('Speicher','Memory'))}</h2>
      <div class="big">${esc(gib(teile.reduce((a,x)=>a+(x.gib||0),0)))} / ${esc(gib(b.gesamt))}</div>
      <div class="row">${teile.map(x=>`<span class="pill">${esc(x.name)} · ${esc(gib(x.gib))}</span>`).join(' ')}</div></div>${arten}`}

let KOPPEL_T=null;
async function assistent(msg){const el=$('tab-assistent');let d;clearTimeout(KOPPEL_T);
  try{d=await (await api('/api/konsole/koppeln')).json()}catch(e){el.innerHTML=`<p class="k">${esc(e.message)}</p>`;return}
  const host=location.hostname,ENDE={gekoppelt:[t('Gekoppelt. Der Assistent nutzt jetzt diesen Spark.','Paired. The assistant now uses this Spark.'),'ok'],
    abgelaufen:[t('Der Code ist abgelaufen.','The code expired.'),'warn'],abgelehnt:[t('Dreimal falscher Code, der Code ist verfallen.','Wrong code three times, the code is gone.'),'bad'],
    fehler:[t('Die Kopplung ging nicht.','The pairing did not work.'),'bad']};
  const e=ENDE[d.stand];
  el.innerHTML=`<h1>${esc(t('Assistent koppeln','Pair an assistant'))}</h1>
    <div class="k">${esc(t('Ein Assistent (zum Beispiel der Pi) nutzt danach Sprache und Modelle dieses Spark. Der Code gilt 10 Minuten und nur einmal; er geht nie über das Netz, der Assistent beweist ihn nur.','An assistant (the Pi, for example) then uses this Spark\'s speech and models. The code lives 10 minutes and works once; it never crosses the network, the assistant only proves it.'))}</div>
    <div class="g2" style="margin-top:14px"><div class="card">
      ${d.code?`<h2>${esc(t('Kopplungscode','Pairing code'))}</h2><div class="big mono code">${esc(d.code)}</div>
        <div class="k">${esc(t('noch','still'))} ${esc(Math.ceil(d.rest/60))} min · ${esc(t('Spark','Spark'))}: <span class="mono">${esc(host)}</span></div>
        ${d.fingerabdruck?`<div class="k" style="margin-top:8px">${esc(t('Fingerabdruck','Fingerprint'))}</div><div class="key mono">${esc(d.fingerabdruck)}</div>`:''}`
      :`${e?`<div class="row"><span class="pill ${e[1]}">${esc(e[0])}</span></div>`:''}
        <div class="row"><button class="btn" type="button" data-a="code">${esc(t('Code zeigen','Show a code'))}</button><span class="k" id="kamsg">${esc(msg||'')}</span></div>`}
    </div><div class="card"><h2>${esc(t('Auf dem Assistenten','On the assistant'))}</h2>
      <p>${esc(t('Auf dem Pi in einem Terminal:','On the Pi in a terminal:'))}</p><div class="key mono">sudo speech-spark teilen koppeln ${esc(host)}</div>
      <p class="k">${esc(t('Dann den Code eingeben. Der Pi prüft dabei den Fingerabdruck dieses Spark.','Then enter the code. The Pi checks this Spark\'s fingerprint on the way.'))}</p></div></div>`;
  if(d.code||msg)KOPPEL_T=setTimeout(()=>{if(TAB==='assistent')assistent()},d.code?5000:2000)}
async function assistentAct(){const m=x=>{const el=$('kamsg');if(el)el.textContent=x};
  try{await post('/api/konsole/koppeln');assistent(t('Code kommt …','Code coming …'))}catch(e){m(e.message)}}

async function updates(msg){const el=$('tab-updates');let d,p={};
  try{d=await (await api('/api/update')).json();p=await (await api('/api/update/progress?log=true')).json()}catch(e){el.innerHTML=`<p class="k">${esc(e.message)}</p>`;return}
  const inst=d.installed||{},rem=d.remote||{},neu=rem.version&&rem.version!==inst.version;
  el.innerHTML=`<h1>Updates</h1><div class="k">${esc(t('Dieser Spark aktualisiert sich selbst; nur Versionen mit grünen Tests.','This Spark updates itself; only versions with green tests.'))}</div>
    <div class="g2" style="margin-top:14px"><div class="card"><h2>${esc(t('Version','Version'))}</h2>
      <div class="big">${esc(inst.version||inst.short||'?')}</div>
      <div class="row">${neu?`<span class="pill warn">${esc(t('Neu','New'))}</span> ${esc(rem.version)}`:`<span class="pill ok">${esc(t('aktuell','up to date'))}</span>`}</div>
      <div class="row"><button class="btn" type="button" data-u="start"${d.running||!neu?' disabled':''}>${esc(t('Jetzt aktualisieren','Update now'))}</button>
        <button class="btn sec" type="button" data-u="pruefen">${esc(t('Neu prüfen','Check again'))}</button><span class="k" id="kumsg">${esc(msg||'')}</span></div></div>
    <div class="card"><h2>${esc(t('Ablauf','Progress'))}</h2>${p.running||d.running?`<div class="row"><span class="pill warn">${esc(t('läuft','running'))}</span> ${esc(p.text||'')}</div>`:''}
      <pre>${esc((p.log||[]).join('\n')||t('Noch kein Update in diesem Lauf.','No update in this run yet.'))}</pre></div></div>`;
  if(p.running||d.running){clearInterval(TIMER);TIMER=setInterval(()=>{if(TAB==='updates')updates()},4000)}}
async function updateAct(a){const m=x=>{const el=$('kumsg');if(el)el.textContent=x};
  try{if(a==='start'){await post('/api/update');return updates(t('Gestartet.','Started.'))}
    if(a==='pruefen'){await api('/api/update?check=true');return updates()}}
  catch(e){m(e.message)}}

async function logs(name){const el=$('tab-logs');name=LOGS.includes(name)?name:LOGS[0];
  el.innerHTML=`<h1>Logs</h1><div class="row">${LOGS.map(n=>`<button class="btn ${n===name?'':'sec'}" type="button" data-l="${esc(n)}">${esc(DIENST[n]||n)}</button>`).join('')}</div><pre id="klog">…</pre>`;
  try{$('klog').textContent=await (await api('/api/logs/'+encodeURIComponent(name)+'?lines=300')).text()}catch(e){$('klog').textContent=e.message}}

document.addEventListener('click',e=>{const b=e.target.closest('button,a');if(!b)return;
  if(b.dataset.tab){e.preventDefault();history.replaceState(null,'','#'+b.dataset.tab);show(b.dataset.tab);return}
  if(b.dataset.k)clientAct(b.dataset.k,b);else if(b.dataset.u)updateAct(b.dataset.u);else if(b.dataset.l)logs(b.dataset.l);else if(b.dataset.a)assistentAct()});
document.addEventListener('DOMContentLoaded',()=>{
  if(EN){document.documentElement.lang='en';$('klt').textContent='Sign in';$('kld').textContent="This Spark's console. Home network only, with the password from the installation.";
    $('klpw').placeholder='Password';$('klcode').placeholder='Code from the app';$('klgo').textContent='Sign in';$('kout').textContent='Sign out';
    $('kct').textContent='Confirm with a code';$('kcd').textContent='This change needs a fresh code from the authenticator app.';$('kcok').textContent='Confirm';$('kcno').textContent='Cancel';
    const tabs={ueberblick:'Overview',modelle:'Models',clients:'Clients',assistent:'Assistant',updates:'Updates',logs:'Logs'};document.querySelectorAll('#ktabs a').forEach(a=>a.textContent=tabs[a.dataset.tab])}
  $('klform').addEventListener('submit',login);
  $('kout').addEventListener('click',async()=>{try{await /*raw: the console loads without base.js*/fetch('/api/logout',{method:'POST'})}catch{}showLogin()});
  $('kcok').addEventListener('click',()=>codeDone($('kcin').value.trim()));$('kcno').addEventListener('click',()=>codeDone(''));
  $('kcin').addEventListener('keydown',e=>{if(e.key==='Enter')codeDone($('kcin').value.trim())});
  start()});
