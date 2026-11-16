// Spark-Konsole (konsole.html, ../../konsole.py, plan spark-entkoppeln E4): the model computer's own page. Login and
// codes are the panel's (/api/login, x-speech-code on 428); the pages read the panel's own answers (/api/status,
// /api/admin/spark-clients, /api/admin/modelle, /api/admin/modellgenau, /api/update, /api/logs, /api/konsole/koppeln).
// Every name, number and log line goes through esc().
'use strict';
const EN=!/^de\b/i.test(navigator.language||'de');
const t=(de,en)=>EN?en:de;
const L=EN?'en':'de';   // modellgenau.js (tab Modell genau) reads the language as the panel's i18n.js gives it
const $=id=>document.getElementById(id);
const esc=s=>String(s==null?'':s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const RECHT={llm:t('Sprachmodell','Language model'),sehen:t('Bilder verstehen','Understand pictures'),helfer:t('Hilfsmodell','Helper model'),
  systemone:t('Einordnen (System One)','Classify (System One)'),asr:t('Hören','Listening'),tts:t('Sprechen','Speaking'),bild:t('Bilder','Pictures'),musik:t('Musik','Music')};
const KLASSE={sprache:t('Sprache','Speech'),dialog:t('Dialog','Dialogue'),hintergrund:t('Hintergrund','Background')};
const DIENST={asr:t('Spracherkennung','Speech recognition'),tts:t('Sprachausgabe','Speech output'),llm:t('Sprachmodell','Language model'),
  llmtor:'LLM-Tor',sehen:t('Sehen','Vision'),helfer:t('Hilfsmodell','Helper model'),bild:t('Bilder','Pictures'),musik:t('Musik','Music')};
// only the notes about the Spark itself; the rest of /api/status's notes are the assistant's (old data of a panel that ran here)
const HINWEISE=['memory','watchdog','systemupdate','systemupdate_neustart'];
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

const TABS=['ueberblick','modellgenau','modelle','clients','assistent','updates','logs'];
function show(tab){if(!TABS.includes(tab))tab='ueberblick';TAB=tab;
  document.querySelectorAll('#ktabs a').forEach(a=>a.classList.toggle('on',a.dataset.tab===tab));
  document.querySelectorAll('.tab').forEach(x=>x.hidden=x.id!=='tab-'+tab);clearInterval(TIMER);if(tab!=='modellgenau')mgClose();
  ({ueberblick,modellgenau:mgOpen,modelle,clients,assistent,updates,logs})[tab]();if(tab==='ueberblick')TIMER=setInterval(ueberblick,3000)}

const pct=(a,b)=>b?Math.max(0,Math.min(100,Math.round(a/b*100))):0;
const zust=s=>s==='active'?`<span class="pill ok">${esc(t('bereit','ready'))}</span>`:s==='inactive'?`<span class="pill grey">${esc(t('aus','off'))}</span>`:
  s==='failed'?`<span class="pill bad">${esc(t('Fehler','error'))}</span>`:s==='activating'?`<span class="pill warn">${esc(t('startet','starting'))}</span>`:
  `<span class="pill grey">${esc(t('unbekannt','unknown'))}</span>`;
// one line about the chat model (modellgenau.fuer_live): numbers only, a jump link to the tab „Modell genau“
function genau(g){if(!g||g.laufen==null)return '';const n=v=>v==null?'–':Math.round(v);
  return `<div class="card row kgenau"><b>${esc(t('Chat-Modell','Chat model'))}</b><span>${esc(t(`${n(g.laufen)} laufen · ${n(g.warten)} warten · ${n(g.tok_s)} tok/s`,`${n(g.laufen)} running · ${n(g.warten)} waiting · ${n(g.tok_s)} tok/s`))}</span>${g.kv!=null?`<span class="k">KV ${esc(n(g.kv))} %</span>`:''}
    <a href="#modellgenau" data-tab="modellgenau">${esc(t('Modell genau','Model in detail'))} →</a></div>`}
async function ueberblick(){const el=$('tab-ueberblick');let d;
  try{d=await (await api('/api/status')).json()}catch(e){el.innerHTML=`<p class="k">${esc(e.message)}</p>`;return}
  const g=d.gpu||{},s=d.system||{},used=(s.mem_total_gib||0)-(s.mem_avail_gib||0);
  const rows=Object.entries(d.services||{}).map(([n,v])=>`<tr><td>${esc(DIENST[n]||n)}</td><td class="mono">${esc(v.port||'')}</td><td>${zust(v.state)}</td></tr>`+
    (v.engines||[]).map(x=>`<tr><td class="k">↳ ${esc(x.name)} · ${esc(x.model||'')}</td><td class="mono">${esc(x.port||'')}</td><td>${zust(x.state)}</td></tr>`).join('')).join('');
  const al=(d.alerts||[]).filter(a=>HINWEISE.includes(a.kind)).map(a=>`<div class="row"><span class="pill warn">${esc(t('Hinweis','Note'))}</span> ${esc(a.text||a.message||a)}</div>`).join('');
  el.innerHTML=`<h1>${esc(t('Überblick','Overview'))}</h1><div class="k">${esc(t('Aktualisiert alle 3 Sekunden.','Refreshed every 3 seconds.'))}</div>
    <div class="g4">
      <div class="card"><div class="k">GPU</div><div class="big">${esc(g.util??'–')} %</div><div class="k">${esc(g.temp??'–')} °C · ${esc(g.power??'–')} W</div><div class="bar"><i style="width:${pct(g.util||0,100)}%"></i></div></div>
      <div class="card"><div class="k">${esc(t('Speicher (gemeinsam)','Memory (shared)'))}</div><div class="big">${esc(Math.round(used))} / ${esc(Math.round(s.mem_total_gib||0))} GiB</div><div class="k">${esc(t('frei','free'))} ${esc(Math.round(s.mem_avail_gib||0))} GiB</div><div class="bar"><i style="width:${pct(used,s.mem_total_gib)}%"></i></div></div>
      <div class="card"><div class="k">CPU</div><div class="big">${esc(Math.round(s.cpu||0))} %</div><div class="bar"><i style="width:${pct(s.cpu||0,100)}%"></i></div></div>
      <div class="card"><div class="k">${esc(t('Dienste bereit','Services ready'))}</div><div class="big">${esc(Object.values(d.services||{}).filter(v=>v.state==='active').length)} / ${esc(Object.keys(d.services||{}).length)}</div></div>
    </div>
    ${genau(d.genau)}
    <div class="g2"><div class="card"><h2>${esc(t('Dienste','Services'))}</h2><table><tr><th>${esc(t('Dienst','Service'))}</th><th>Port</th><th>${esc(t('Zustand','State'))}</th></tr>${rows}</table></div>
    <div class="card"><h2>${esc(t('Hinweise','Notes'))}</h2>${al||`<p class="k">${esc(t('Alles ruhig.','All quiet.'))}</p>`}</div></div>`}

let SPC=null;
async function clients(msg){const el=$('tab-clients');
  try{SPC=await (await api('/api/admin/spark-clients')).json()}catch(e){el.innerHTML=`<p class="k">${esc(e.message)}</p>`;return}
  const d=SPC,rows=d.clients.map(c=>`<tr><td><b>${esc(c.name)}</b><div class="k">${esc(c.rechte.map(x=>RECHT[x]||x).join(', '))}</div></td>
    <td><span class="pill ${c.klasse==='sprache'?'ok':'grey'}">${esc(KLASSE[c.klasse]||c.klasse)}</span></td>
    <td class="k">${esc(spgText(c))}${c.gesperrt?' · '+esc(t('gesperrt','blocked')):''}</td>
    <td><button class="btn sec" type="button" data-k="grenzen" data-id="${esc(c.id)}">${esc(t('Grenzen','Limits'))}</button>
      <button class="btn sec" type="button" data-k="sperren" data-id="${esc(c.id)}">${esc(c.gesperrt?t('Entsperren','Unblock'):t('Sperren','Block'))}</button>
      <button class="btn bad" type="button" data-k="weg" data-id="${esc(c.id)}">${esc(t('Löschen','Delete'))}</button></td></tr>`).join('');
  el.innerHTML=`<h1>Clients</h1><div class="k">${esc(t('Andere Programme im Heimnetz mit eigenem Schlüssel, Rechten, Vorrangklasse und Grenzen. Der Schlüssel ist nur einmal sichtbar.','Other programs in the home network with a key of their own, rights, priority class and limits. The key is visible only once.'))}</div>
    <div class="card" style="margin-top:14px"><div class="row"><label><input type="checkbox" id="kcan"${d.an?' checked':''}> ${esc(t('Für Clients geöffnet','Open for clients'))}</label>
      <input id="kcnetze" style="flex:1" value="${esc(d.netze.join(', '))}" placeholder="192.168.178.0/24" aria-label="${esc(t('Netze im Heimnetz','Home networks'))}">
      <button class="btn sec" type="button" data-k="schalten">${esc(t('Übernehmen','Apply'))}</button></div></div>
    <div class="card" style="margin-top:14px"><table><tr><th>Client</th><th>${esc(t('Klasse','Class'))}</th><th>${esc(t('Grenzen','Limits'))}</th><th></th></tr>${rows||`<tr><td class="k" colspan="4">${esc(t('Noch kein Client.','No client yet.'))}</td></tr>`}</table><div id="kcedit"></div></div>
    <div class="card" style="margin-top:14px"><h2>${esc(t('Neuer Client','New client'))}</h2>
      <div class="row"><input id="kcname" maxlength="40" placeholder="${esc(t('Name, z. B. Open WebUI','Name, e.g. Open WebUI'))}" aria-label="Name">
        <select id="kcklasse" aria-label="${esc(t('Vorrangklasse','Priority class'))}">${d.klassen.map(k=>`<option value="${esc(k)}"${k===d.vorgabe.klasse?' selected':''}>${esc(KLASSE[k]||k)}</option>`).join('')}</select></div>
      <div class="row">${d.rechte.map(x=>`<label><input type="checkbox" data-recht="${esc(x)}"${d.vorgabe.rechte.includes(x)?' checked':''}> ${esc(RECHT[x]||x)}</label>`).join('')}</div>
      ${spgFelder('kcneu',d.vorgabe,'k')}
      <div class="row"><button class="btn" type="button" data-k="neu"${d.clients.length>=d.max?' disabled':''}>${esc(t('Schlüssel erzeugen','Make key'))}</button><span class="k" id="kcmsg">${esc(msg||'')}</span></div>
      <div id="kckey" hidden><div class="k">${esc(t('Nur jetzt sichtbar. Im Programm als API-Schlüssel eintragen (Bearer).','Visible only now. Enter it in the program as the API key (Bearer).'))}</div><div class="key mono" id="kckeyv"></div></div></div>
    <div class="card spv-box" style="margin-top:14px" id="kcverb">${sparkVerbinden(d,d.host,'','k')}</div>`}
async function clientAct(a,b){const m=x=>{const el=$('kcmsg');if(el)el.textContent=x};
  try{if(a==='schalten'){const netze=$('kcnetze').value.split(',').map(x=>x.trim()).filter(Boolean);
      const d=await post('/api/admin/spark-clients/schalten',{an:$('kcan').checked,netze});return clients(d.an?t('Geöffnet.','Open.'):t('Geschlossen.','Closed.'))}
    if(a==='neu'){const rechte=[...document.querySelectorAll('[data-recht]')].filter(x=>x.checked).map(x=>x.dataset.recht);
      const d=await post('/api/admin/spark-clients/neu',{name:$('kcname').value,rechte,klasse:$('kcklasse').value,...spgLesen('kcneu')});
      await clients();$('kckeyv').textContent=d.key;$('kckey').hidden=false;$('kcverb').innerHTML=sparkVerbinden(SPC,SPC.host,d.key,'k');return}
    const c=(SPC.clients||[]).find(x=>x.id===b.dataset.id);if(!c)return;
    if(a==='grenzen'){$('kcedit').innerHTML=`<h2>${esc(t('Grenzen von','Limits of'))} ${esc(c.name)}</h2>${spgFelder('kced',c,'k')}
      <div class="row"><button class="btn" type="button" data-k="grenzen_ok" data-id="${esc(c.id)}">${esc(t('Speichern','Save'))}</button></div>`;return}
    if(a==='grenzen_ok'){await post('/api/admin/spark-clients/aendern',{id:c.id,felder:spgLesen('kced')});return clients(t('Grenzen gespeichert.','Limits saved.'))}
    if(a==='sperren')await post('/api/admin/spark-clients/aendern',{id:c.id,felder:{gesperrt:!c.gesperrt}});
    if(a==='weg')await post('/api/admin/spark-clients/weg',{id:c.id});
    await clients()}
  catch(e){m(e.message)}}

const gib=x=>x==null?'–':(Math.round(x*10)/10)+' GiB';
// Modelle (modellseite.py, the panel's own endpoints): switch, measure, own models from Hugging Face; every change with
// a code. The page polls while a switch or a measurement runs.
const EIGEN_ARTEN=['llm','sehen'];
let MOD=null,MOD_T=null,MOD_FUND=null;
async function modelle(msg){const el=$('tab-modelle');clearTimeout(MOD_T);
  try{MOD=await (await api('/api/admin/modelle?lang='+(EN?'en':'de'))).json()}catch(e){el.innerHTML=`<p class="k">${esc(e.message)}</p>`;return}
  modDraw(msg)}
function modDraw(msg){const el=$('tab-modelle'),d=MOD,b=d.budget||{},teile=b.teile||[],w=d.wechsel||{},busy=w.laeuft||w.misst;
  const start=w.start?`<div class="card" style="margin-top:14px"><h2>${esc(t('Läuft gerade','Running now'))}</h2><div><b>${esc(w.start.kopf||'')}</b></div>
      ${(w.start.zeilen||[]).map(z=>`<div class="row"><span class="pill ${z.zustand==='ok'?'ok':z.zustand==='jetzt'?'warn':'grey'}">${esc(z.zustand==='ok'?'✓':z.zustand==='jetzt'?'…':'·')}</span> ${esc(z.name)} <span class="k">${esc(z.zeit||'')}</span></div>`).join('')}
      <div class="k">${esc(w.start.rest||'')}</div></div>`:busy?`<div class="row"><span class="pill warn">${esc(w.misst?t('Messung läuft','Measuring'):t('Wechsel läuft','Switching'))}</span></div>`:'';
  const arten=(d.arten||[]).map(a=>{const rows=a.modelle.map(m=>`<tr><td><b>${esc(m.name)}</b>${m.eigen?` <span class="pill grey">${esc(t('eigen','own'))}</span>`:''}<div class="k mono">${esc(m.engine)}</div></td>
      <td>${m.aktiv?`<span class="pill ok">${esc(t('läuft','running'))}</span>`:`<span class="pill grey">${esc(t('nicht geladen','not loaded'))}</span>`}</td>
      <td class="mono">${esc(gib(m.aktiv&&m.gib!=null?m.gib:m.need_gib))}</td>
      <td class="mono">${m.messung&&m.messung.tok_s!=null?esc(m.messung.tok_s)+' tok/s':'–'}</td>
      <td>${!m.aktiv&&m.waehlbar?`<button class="btn" type="button" data-m="wechseln" data-art="${esc(a.art)}" data-id="${esc(m.id)}"${busy?' disabled':''}>${esc(t('Laden','Load'))}</button> `:''}
        ${m.messbar?`<button class="btn sec" type="button" data-m="messen" data-id="${esc(m.id)}"${busy?' disabled':''}>${esc(t('Messen','Measure'))}</button> `:''}
        ${m.eigen&&!m.aktiv?`<button class="btn bad" type="button" data-m="weg" data-id="${esc(m.id)}"${busy?' disabled':''}>${esc(t('Löschen','Delete'))}</button>`:''}</td></tr>`).join('');
    const zur=(w.alte||{})[a.art];
    return rows?`<div class="card" style="margin-top:14px"><h2>${esc(a.name)}</h2>${zur?`<div class="row"><button class="btn sec" type="button" data-m="zurueck" data-art="${esc(a.art)}"${busy?' disabled':''}>${esc(t('Vorheriges zurückholen','Bring back the previous one'))}</button></div>`:''}
      <table><tr><th>${esc(t('Modell','Model'))}</th><th>${esc(t('Zustand','State'))}</th><th>${esc(t('Speicher','Memory'))}</th><th>${esc(t('Tempo','Speed'))}</th><th></th></tr>${rows}</table></div>`:''}).join('');
  const f=MOD_FUND;
  const eigen=`<div class="card" style="margin-top:14px"><h2>${esc(t('Eigenes Modell von Hugging Face','Own model from Hugging Face'))}</h2>
    <div class="k">${esc(t('Nur Gewichte als safetensors, kein Code aus dem Repository, eine Architektur, die der Spark kennt. Geladen wird erst beim Wechseln.','Weights as safetensors only, no code from the repository, an architecture the Spark knows. It is downloaded only when you switch to it.'))}</div>
    <div class="row"><select id="kmart" aria-label="${esc(t('Art','Kind'))}">${EIGEN_ARTEN.map(x=>`<option value="${x}">${esc((d.arten||[]).find(a=>a.art===x)?.name||x)}</option>`).join('')}</select>
      <input id="kmq" maxlength="80" placeholder="${esc(t('Suchen, z. B. qwen3 nvfp4','Search, e.g. qwen3 nvfp4'))}" aria-label="${esc(t('Suche','Search'))}"><button class="btn sec" type="button" data-m="suche">${esc(t('Suchen','Search'))}</button></div>
    <div id="kmtreffer"></div>
    <div class="row"><input id="kmrepo" style="flex:1" maxlength="200" placeholder="org/name" aria-label="${esc(t('Name auf Hugging Face','Name on Hugging Face'))}"><button class="btn sec" type="button" data-m="pruefen">${esc(t('Prüfen','Check'))}</button></div>
    ${f?`<div class="row"><b>${esc(f.name&&f.name.de?(EN?f.name.en:f.name.de):f.repo)}</b> <span class="k mono">${esc(f.repo)} @ ${esc(String(f.revision).slice(0,10))}</span></div>
      <div class="k">${esc(t('Speicher','Memory'))} ${esc(gib(f.need_gib))} · ${esc(t('Platte','Disk'))} ${esc(f.platte_gb)} GB · ${esc(t('Lizenz','License'))} ${esc(f.lizenz)}${f.gewerblich?'':' · '+esc(t('nicht gewerblich','non-commercial'))}</div>
      <div class="row"><button class="btn" type="button" data-m="dazu">${esc(t('Hinzufügen','Add'))}</button></div>`:''}</div>`;
  el.innerHTML=`<h1>${esc(t('Modelle','Models'))}</h1><div class="k">${esc(t('Was dieser Spark lädt und wie viel Speicher es braucht. Laden, Messen und eigene Modelle fragen nach einem Code.','What this Spark loads and how much memory it needs. Loading, measuring and own models ask for a code.'))}</div>
    <div class="row"><span class="k" id="kmmsg">${esc(msg||'')}</span></div>${start}
    <div class="card" style="margin-top:14px"><h2>${esc(t('Speicher','Memory'))}</h2>
      <div class="big">${esc(gib(teile.reduce((a,x)=>a+(x.gib||0),0)))} / ${esc(gib(b.gesamt))}</div>
      <div class="row">${teile.map(x=>`<span class="pill">${esc(x.name)} · ${esc(gib(x.gib))}</span>`).join(' ')}</div></div>${arten}${eigen}`;
  if(busy||w.start)MOD_T=setTimeout(()=>{if(TAB==='modelle')modelle()},5000)}
async function modAct(a,b){const m=x=>{const el=$('kmmsg');if(el)el.textContent=x};const L='?lang='+(EN?'en':'de');
  try{
    if(a==='wechseln'){MOD=await post('/api/admin/modelle/wechseln'+L,{art:b.dataset.art,id:b.dataset.id});return modDraw(t('Wechsel angefragt.','Switch requested.'))}
    if(a==='zurueck'){MOD=await post('/api/admin/modelle/zurueck'+L,{art:b.dataset.art});return modDraw(t('Zurückholen angefragt.','Bring-back requested.'))}
    if(a==='messen'){MOD=await post('/api/admin/modelle/messen'+L,{id:b.dataset.id});return modDraw(t('Messung angefragt. Das Sprachmodell pausiert währenddessen.','Measurement requested. The language model pauses meanwhile.'))}
    if(a==='weg'){MOD=await (await api('/api/admin/modelle/eigen/'+encodeURIComponent(b.dataset.id)+L,{method:'DELETE'})).json();MOD_FUND=null;return modDraw(t('Gelöscht.','Deleted.'))}
    if(a==='suche'){const d=await post('/api/admin/modelle/eigen/suche',{art:$('kmart').value,q:$('kmq').value});
      $('kmtreffer').innerHTML=(d.treffer||[]).map(x=>`<div class="row"><button class="btn sec" type="button" data-m="nimm" data-repo="${esc(x.repo)}">${esc(x.repo)}</button> <span class="k">${esc(x.lizenz||'')} · ${esc(x.downloads)} Downloads</span></div>`).join('')||`<p class="k">${esc(t('Nichts gefunden.','Nothing found.'))}</p>`;return}
    if(a==='nimm'){$('kmrepo').value=b.dataset.repo;return modAct('pruefen')}
    if(a==='pruefen'){const art=$('kmart').value,d=await post('/api/admin/modelle/eigen/pruefen',{art,repo:$('kmrepo').value.trim()});MOD_FUND=Object.assign(d.vorschlag,{_art:art});return modDraw()}
    if(a==='dazu'&&MOD_FUND){MOD=await post('/api/admin/modelle/eigen'+L,{art:MOD_FUND._art,repo:MOD_FUND.repo,revision:MOD_FUND.revision});MOD_FUND=null;return modDraw(t('Hinzugefügt. Mit „Laden“ wird es geholt und gestartet.','Added. “Load” downloads and starts it.'))}
  }catch(e){m(e.message)}}

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
      <p>${esc(t('Im Panel des Pi unter Einstellungen → Spark → Spark koppeln Name und Code eintragen, oder im Terminal:','In the Pi\'s panel under Einstellungen → Spark → Spark koppeln enter name and code, or in a terminal:'))}</p><div class="key mono">sudo speech-spark teilen koppeln ${esc(host)}</div>
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
  if(b.dataset.k)clientAct(b.dataset.k,b);else if(b.dataset.u)updateAct(b.dataset.u);else if(b.dataset.l)logs(b.dataset.l);else if(b.dataset.a)assistentAct();else if(b.dataset.m)modAct(b.dataset.m,b)});
document.addEventListener('DOMContentLoaded',()=>{
  if(EN){document.documentElement.lang='en';$('klt').textContent='Sign in';$('kld').textContent="This Spark's console. Home network only, with the password from the installation.";
    $('klpw').placeholder='Password';$('klcode').placeholder='Code from the app';$('klgo').textContent='Sign in';$('kout').textContent='Sign out';
    $('kct').textContent='Confirm with a code';$('kcd').textContent='This change needs a fresh code from the authenticator app.';$('kcok').textContent='Confirm';$('kcno').textContent='Cancel';$('kmgt').textContent='Model in detail';
    const tabs={ueberblick:'Overview',modellgenau:'Model in detail',modelle:'Models',clients:'Clients',assistent:'Assistant',updates:'Updates',logs:'Logs'};document.querySelectorAll('#ktabs a').forEach(a=>a.textContent=tabs[a.dataset.tab])}
  $('klform').addEventListener('submit',login);
  $('kout').addEventListener('click',async()=>{try{await /*raw: the console loads without base.js*/fetch('/api/logout',{method:'POST'})}catch{}showLogin()});
  $('kcok').addEventListener('click',()=>codeDone($('kcin').value.trim()));$('kcno').addEventListener('click',()=>codeDone(''));
  $('kcin').addEventListener('keydown',e=>{if(e.key==='Enter')codeDone($('kcin').value.trim())});
  start()});
