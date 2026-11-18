// Spark-Konsole (konsole.html, ../../konsole.py, plan spark-entkoppeln E4; neu geordnet nach Dominik 2026-11-18 „1-6“,
// Tafeln konsole-neu/1-4): the model computer's own page in four areas: Überblick (with Modell genau as its detail),
// Modelle and Verbindungen as list and detail, Wartung (Updates and Logs). The address says where you are (#modelle/llm,
// #verbindungen/c/<id>, #wartung/log/<name>), so the browser's back button and links work. Login and codes are the
// panel's (/api/login, x-speech-code on 428); the pages read the panel's own answers (/api/status,
// /api/admin/spark-clients, /api/admin/modelle, /api/admin/modellgenau, /api/update, /api/logs, /api/konsole/koppeln).
// Every name, number and log line goes through esc().
'use strict';
const EN=!/^de\b/i.test(navigator.language||'de');
const t=(de,en)=>EN?en:de;
const L=EN?'en':'de';   // modellgenau.js (Modell genau) reads the language as the panel's i18n.js gives it
const $=id=>document.getElementById(id);
const esc=s=>String(s==null?'':s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const RECHT={llm:t('Sprachmodell','Language model'),sehen:t('Bilder verstehen','Understand pictures'),helfer:t('Hilfsmodell','Helper model'),
  systemone:t('Einordnen (System One)','Classify (System One)'),asr:t('Hören','Listening'),tts:t('Sprechen','Speaking'),bild:t('Bilder','Pictures'),musik:t('Musik','Music')};
const KLASSE={sprache:t('Sprache','Speech'),dialog:t('Dialog','Dialogue'),hintergrund:t('Hintergrund','Background')};
const DIENST={asr:t('Spracherkennung','Speech recognition'),tts:t('Sprachausgabe','Speech output'),llm:t('Sprachmodell','Language model'),
  llmtor:'LLM-Tor',sehen:t('Sehen','Vision'),helfer:t('Hilfsmodell','Helper model'),bild:t('Bilder','Pictures'),musik:t('Musik','Music')};
// the services by what they do (Überblick): symbol, name, one line; the kind of model in Modelle it opens
const AUFGABE={llm:['brain',t('Sprachmodell','Language model'),t('Gespräche, Werkzeuge, Zusammenfassungen','Talks, tools, summaries'),'llm'],
  asr:['ear',t('Hören','Listening'),t('Spracherkennung','Speech recognition'),'asr'],tts:['speaker',t('Sprechen','Speaking'),t('Sprachausgabe','Speech output'),'tts'],
  helfer:['bulb',t('Hilfsmodell','Helper model'),t('schnelles Einordnen','quick sorting'),'helfer'],sehen:['eye',t('Bilder verstehen','Understand pictures'),t('Bildverständnis','Image understanding'),'sehen'],
  bild:['image',t('Bilder malen','Painting pictures'),t('Bilder auf Wunsch','Pictures on request'),'bild'],musik:['music',t('Musik','Music'),t('Musik machen','Making music'),'musik'],
  llmtor:['route','LLM-Tor',t('Tür für Assistent und Programme','Door for the assistant and programs'),'']};
const ART_IC={llm:'brain',sehen:'eye',asr:'ear',tts:'speaker',bild:'image',musik:'music',klein:'cpu',helfer:'bulb'};
// only the notes about the Spark itself; the rest of /api/status's notes are the assistant's (old data of a panel that ran here)
const HINWEISE=['memory','watchdog','systemupdate','systemupdate_neustart'];
const LOGS=['llm','llmtor','asr','asr-engine','tts','tts-engine','update','konsole'];
let TAB='ueberblick',SUB='',TIMER=null,CODE_WAIT=null,UPD=null;
const iconsIn=el=>el.querySelectorAll('i[data-ic]').forEach(i=>i.replaceWith(icNode(i.dataset.ic)));
const st=(cls,word)=>`<span class="st ${cls}"><i></i>${esc(word)}</span>`;
const chev=()=>`<span class="chev">${ic('chev')}</span>`;
function row(o){const tag=o.href?'a':'div';
  return `<${tag} class="krow${o.on?' on':''}"${o.href?` href="${esc(o.href)}"`:''}>${o.ic?`<span class="kico">${ic(o.ic)}</span>`:''}
    <span class="kt"><b>${esc(o.title)}</b>${o.sub!=null&&o.sub!==''?`<div>${esc(o.sub)}</div>`:''}</span><span class="kr">${o.right||''}${o.href?chev():''}</span></${tag}>`}

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

function stopAll(){clearInterval(TIMER);clearTimeout(MOD_T);clearTimeout(KOPPEL_T);clearTimeout(LOG_T)}
function showLogin(){stopAll();$('klogin').hidden=false;$('kside').hidden=true;
  document.querySelectorAll('.tab').forEach(x=>x.hidden=true);$('klpw').focus()}
async function login(e){e.preventDefault();const m=$('klmsg');m.textContent='';
  const body={password:$('klpw').value};if(!$('klcode').hidden)body.code=$('klcode').value.trim();
  try{const r=await /*raw: the console loads without base.js*/fetch('/api/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
    if(!r.ok){m.textContent=r.status===429?t('Zu viele Versuche, bitte warten.','Too many tries, please wait.'):t('Passwort oder Code stimmt nicht.','Password or code is wrong.');return}
    const d=await r.json();if(d.code){$('klcode').hidden=false;$('klcode').focus();m.textContent=t('Jetzt den Code aus der App.','Now the code from the app.');return}
    $('klpw').value='';$('klcode').value='';$('klcode').hidden=true;start()}
  catch{m.textContent=t('Keine Verbindung.','No connection.')}}

let WHO={};
async function start(){let w;try{w=await (await /*raw: the console loads without base.js*/fetch('/api/whoami',{cache:'no-store'})).json()}catch{w={}}
  if(!w.admin){showLogin();return}
  WHO=w;$('klogin').hidden=true;$('kside').hidden=false;
  $('khost').textContent=location.hostname+' · '+t('nur Heimnetz','home network only');
  $('kstate').innerHTML=st('ok',w.version||'');
  updMark();show()}
// the side bar's note about a new version (one GET, the cached answer; „Neu prüfen“ in Wartung asks GitHub)
async function updMark(){try{UPD=await (await api('/api/update')).json()}catch{return}
  const inst=(UPD.installed||{}).version,rem=(UPD.remote||{}).version,neu=!!(rem&&rem!==inst);
  $('kwdot').hidden=!neu;$('kupd').innerHTML=neu?`${esc(t('Update','Update'))} ${esc(rem)} ${esc(t('bereit','ready'))} · <a href="#wartung">${esc(t('Ansehen','View'))}</a>`:''}

// the address says where you are: #bereich/teil
const TABS=['ueberblick','modellgenau','modelle','verbindungen','wartung'];
function show(){const h=decodeURIComponent((location.hash||'#ueberblick').slice(1)),i=h.indexOf('/');
  let tab=i<0?h:h.slice(0,i);const sub=i<0?'':h.slice(i+1);
  if(!TABS.includes(tab))tab='ueberblick';
  const neu=tab!==TAB;TAB=tab;SUB=sub;
  const nav=tab==='modellgenau'?'ueberblick':tab;
  document.querySelectorAll('#ktabs a').forEach(a=>{a.classList.toggle('on',a.dataset.tab===nav);if(a.dataset.tab===nav)a.setAttribute('aria-current','page');else a.removeAttribute('aria-current')});
  document.querySelectorAll('.tab').forEach(x=>x.hidden=x.id!=='tab-'+tab);stopAll();if(tab!=='modellgenau')mgClose();
  if(neu)scrollTo(0,0);
  ({ueberblick,modellgenau:mgOpen,modelle,verbindungen,wartung})[tab](sub);if(tab==='ueberblick')TIMER=setInterval(ueberblick,3000)}
function gehe(h){if(location.hash==='#'+h)show();else location.hash=h}

const pct=(a,b)=>b?Math.max(0,Math.min(100,Math.round(a/b*100))):0;
const zust=s=>s==='active'?st('ok',t('bereit','ready')):s==='inactive'?st('',t('aus','off')):
  s==='failed'?st('bad',t('Fehler','error')):s==='activating'?st('warn',t('startet','starting')):st('',t('unbekannt','unknown'));
// the curves of the tiles: the last 40 answers (2 minutes), kept only in this page
const VERLAUF={gpu:[],mem:[],tok:[]};
function merke(k,v){const a=VERLAUF[k];a.push(v==null?null:+v);if(a.length>40)a.shift()}
// the chat model's tile (modellgenau.fuer_live): numbers only, a jump link to „Modell genau“
function genau(g){const n=v=>v==null?'–':Math.round(v);if(!g||g.laufen==null)return `<div class="kv">–</div><div class="k">${esc(t('keine Zahlen vom Chat-Modell','no numbers from the chat model'))}</div>`;
  return `<div class="kv">${esc(n(g.tok_s))} <small>${esc(t(`tok/s · ${n(g.laufen)} laufen · ${n(g.warten)} warten`,`tok/s · ${n(g.laufen)} running · ${n(g.warten)} waiting`))}${g.kv!=null?' · KV '+esc(n(g.kv))+' %':''}</small></div>`}
function ueberblickGeruest(el){
  el.innerHTML=`<h1>${esc(t('Überblick','Overview'))}</h1><div class="ksub" id="kosub"></div>
    <div class="kcard khero" id="kohero"></div>
    <div class="ktiles">
      <div class="ktile"><div class="k">GPU</div><div id="kogpu"></div><svg id="kogpus" aria-hidden="true"></svg></div>
      <div class="ktile"><div class="k">${esc(t('Speicher (gemeinsam)','Memory (shared)'))}</div><div id="komem"></div><svg id="komems" aria-hidden="true"></svg></div>
      <div class="ktile kgenau"><div class="krow2"><span class="k">${esc(t('Chat-Modell','Chat model'))}</span><a href="#modellgenau" data-tab="modellgenau">${esc(t('Modell genau','Model in detail'))} ›</a></div><div id="kotok"></div><svg id="kotoks" aria-hidden="true"></svg></div>
    </div>
    <div class="ksec">${esc(t('Was dieser Spark kann','What this Spark does'))}</div><div class="kgrp" id="kolist"></div>
    <div id="kohin"></div>
    <details class="kmehr"><summary>${esc(t('Technik: Dienste und Ports','Technical: services and ports'))}</summary><div class="kcard" id="koports"></div></details>`;
  el.dataset.fertig='1'}
async function ueberblick(){const el=$('tab-ueberblick');let d;
  try{d=await (await api('/api/status')).json()}catch(e){if(!el.dataset.fertig)el.innerHTML=`<p class="k">${esc(e.message)}</p>`;return}
  if(!el.dataset.fertig)ueberblickGeruest(el);
  const g=d.gpu||{},s=d.system||{},used=(s.mem_total_gib||0)-(s.mem_avail_gib||0),sv=d.services||{},namen=Object.keys(sv);
  merke('gpu',g.util);merke('mem',used);merke('tok',(d.genau||{}).tok_s);
  // one sentence first: everything ready, starting, or what does not run
  const fehler=namen.filter(n=>sv[n].state==='failed'||(sv[n].engines||[]).some(x=>x.state==='failed'));
  const startet=namen.filter(n=>sv[n].state==='activating'),bereit=namen.filter(n=>sv[n].state==='active').length;
  const nm=n=>(AUFGABE[n]||[])[1]||DIENST[n]||n;
  const log=fehler.find(n=>LOGS.includes(n));
  const [ring,kopf,satz]=!namen.length?['warn',t('Keine Dienste','No services'),t('Der Spark meldet keine Dienste.','The Spark reports no services.')]:
    fehler.length?['bad',bereit?t('Fast alles bereit','Almost everything ready'):t('Dienste gestört','Services disturbed'),
      fehler.map(nm).join(', ')+' '+(fehler.length>1?t('starten nicht.','do not start.'):t('startet nicht.','does not start.'))]:
    startet.length?['warn',t('Startet …','Starting …'),startet.map(nm).join(', ')+' '+t('kommt gleich.','is coming.')]:
    ['ok',t('Alles bereit','Everything ready'),t(`${bereit} Dienste laufen, die übrigen sind aus.`,`${bereit} services run, the others are off.`)];
  setHtml($('kohero'),`<span class="kring ${ring}">${ic(ring==='ok'?'check':'warn')}</span><div class="kt"><b>${esc(kopf)}</b><div class="k">${esc(satz)}</div></div>
    ${log?`<a class="btn sec" href="#wartung/log/${esc(log)}">${esc(t('Log ansehen','View log'))}</a>`:''}`);
  setHtml($('kosub'),esc(t(`${bereit} von ${namen.length} Diensten bereit · aktualisiert alle 3 Sekunden`,`${bereit} of ${namen.length} services ready · refreshed every 3 seconds`)));
  setHtml($('kogpu'),`<div class="kv">${esc(g.util??'–')} % <small>${esc(g.temp??'–')} °C · ${esc(g.power??'–')} W</small></div>`);
  setHtml($('komem'),`<div class="kv">${esc(Math.round(used))} <small>${esc(t('von','of'))} ${esc(Math.round(s.mem_total_gib||0))} GiB · ${esc(t('frei','free'))} ${esc(Math.round(s.mem_avail_gib||0))} GiB</small></div>`);
  setHtml($('kotok'),genau(d.genau));
  spark($('kogpus'),VERLAUF.gpu,100);spark($('komems'),VERLAUF.mem,s.mem_total_gib||undefined);spark($('kotoks'),VERLAUF.tok);
  // the services by what they do; the language model opens Modell genau, the others their kind in Modelle
  const reihe=Object.keys(AUFGABE).filter(n=>sv[n]).concat(namen.filter(n=>!AUFGABE[n]));
  setHtml($('kolist'),reihe.map(n=>{const v=sv[n],a=AUFGABE[n]||['cpu',DIENST[n]||n,'',''],eng=(v.engines||[]).map(x=>x.model||x.name).concat(v.model?[v.model]:[]).filter(Boolean);
    const schlecht=(v.engines||[]).find(x=>x.state==='failed');
    return row({ic:a[0],title:a[1],sub:[eng.join(', ')||a[2],schlecht?t('Motor startet nicht','engine does not start'):''].filter(Boolean).join(' · '),
      right:schlecht&&v.state==='active'?zust('failed'):zust(v.state),href:n==='llm'?'#modellgenau':a[3]?'#modelle/'+a[3]:''})}).join(''));
  const al=(d.alerts||[]).filter(a=>HINWEISE.includes(a.kind));
  setHtml($('kohin'),al.length?`<div class="ksec">${esc(t('Hinweise','Notes'))}</div><div class="kgrp">${al.map(a=>row({ic:'info',title:a.text||a.message||a})).join('')}</div>`:'');
  setHtml($('koports'),`<table class="kports">${namen.map(n=>`<tr><td>${esc(DIENST[n]||n)}${sv[n].model?' · '+esc(sv[n].model):''}</td><td class="mono">${esc(sv[n].port||'')}</td><td>${zust(sv[n].state)}</td></tr>`+
    (sv[n].engines||[]).map(x=>`<tr><td class="k">↳ ${esc(x.name)} · ${esc(x.model||'')}</td><td class="mono">${esc(x.port||'')}</td><td>${zust(x.state)}</td></tr>`).join('')).join('')}</table>`)}

// ---------------------------------------------------------------- Verbindungen: the assistant and the programs
let SPC=null,KOP={},KOPPEL_T=null,NEU_KEY='';
const ENDE={gekoppelt:[t('Gekoppelt. Der Assistent nutzt jetzt diesen Spark.','Paired. The assistant now uses this Spark.'),'ok'],
  abgelaufen:[t('Der Code ist abgelaufen.','The code expired.'),'warn'],abgelehnt:[t('Dreimal falscher Code, der Code ist verfallen.','Wrong code three times, the code is gone.'),'bad'],
  fehler:[t('Die Kopplung ging nicht.','The pairing did not work.'),'bad']};
async function verbindungen(sub,msg){const el=$('tab-verbindungen');clearTimeout(KOPPEL_T);
  if(sub!=='neu')NEU_KEY='';
  try{const [a,b]=await Promise.all([api('/api/admin/spark-clients'),api('/api/konsole/koppeln')]);SPC=await a.json();KOP=await b.json()}
  catch(e){el.innerHTML=`<p class="k">${esc(e.message)}</p>`;return}
  const d=SPC,wide=matchMedia('(min-width:761px)').matches;
  if(!sub&&wide)sub='assistent';
  const c=sub.startsWith('c/')?(d.clients||[]).find(x=>x.id===sub.slice(2)):null;
  const kop=KOP.code?st('warn',t('Code gilt noch','code still valid')):ENDE[KOP.stand]?st(ENDE[KOP.stand][1],KOP.stand==='gekoppelt'?t('gekoppelt','paired'):t('nicht gekoppelt','not paired')):'';
  const liste=`<div class="klist"><h1>${esc(t('Verbindungen','Connections'))}</h1><div class="ksub">${esc(t('Wer diesen Spark nutzen darf','Who may use this Spark'))}</div>
    <div class="ksec">${esc(t('Assistent','Assistant'))}</div><div class="kgrp">${row({ic:'mobile',title:t('Assistent koppeln','Pair an assistant'),sub:t('zum Beispiel der Pi','the Pi, for example'),right:kop,href:'#verbindungen/assistent',on:sub==='assistent'})}</div>
    <div class="ksec">${esc(t('Programme im Heimnetz','Programs in the home network'))}</div>
    <div class="kgrp">${(d.clients||[]).map(x=>row({ic:'grid',title:x.name,sub:x.rechte.map(r=>RECHT[r]||r).join(', ')||t('keine Rechte','no rights'),
        right:x.gesperrt?st('',t('gesperrt','blocked')):'',href:'#verbindungen/c/'+x.id,on:c&&c.id===x.id})).join('')}
      ${(d.clients||[]).length<d.max?`<a class="krow kadd" href="#verbindungen/neu"${sub==='neu'?' aria-current="page"':''}>${ic('plus')} ${esc(t('Programm verbinden','Connect a program'))}</a>`:
        `<div class="krow k">${esc(t('Mehr Programme gehen nicht.','No more programs possible.'))}</div>`}</div>
    <div class="k">${d.an?esc(t('Offen für','Open for')+' '+d.netze.join(', ')):esc(t('Für Programme geschlossen.','Closed for programs.'))} · <a href="#verbindungen/netz">${esc(t('Ändern','Change'))}</a></div></div>`;
  let det='';
  if(sub==='assistent')det=koppelDetail(msg);
  else if(c)det=clientDetail(c,msg);
  else if(sub==='neu')det=neuDetail(msg);
  else if(sub==='netz')det=netzDetail(msg);
  const back=`<a class="kback konly-phone" href="#verbindungen">‹ ${esc(t('Verbindungen','Connections'))}</a>`;
  felderNeu(el,`<div class="kld${sub&&det?' open':''}">${liste}<div class="kdet">${det?back+det:''}</div></div>`);
  if(sub==='assistent'&&(KOP.code||msg))KOPPEL_T=setTimeout(()=>{if(TAB==='verbindungen'&&(SUB===''||SUB==='assistent'))verbindungen(SUB)},KOP.code?5000:2000)}
function koppelDetail(msg){const d=KOP,host=location.hostname,e=ENDE[d.stand];
  return `<div class="kkick">${esc(t('Verbindungen','Connections'))}</div><h1>${esc(t('Assistent koppeln','Pair an assistant'))}</h1>
    <div class="ksub">${esc(t('Ein Assistent (zum Beispiel der Pi) nutzt danach Sprache und Modelle dieses Spark. Der Code gilt 10 Minuten und nur einmal; er geht nie über das Netz, der Assistent beweist ihn nur.','An assistant (the Pi, for example) then uses this Spark\'s speech and models. The code lives 10 minutes and works once; it never crosses the network, the assistant only proves it.'))}</div>
    <div class="kcard">${d.code?`<div class="k">${esc(t('Kopplungscode','Pairing code'))}</div><div class="mono code">${esc(d.code)}</div>
        <div class="k">${esc(t('noch','still'))} ${esc(Math.ceil(d.rest/60))} min · Spark: <span class="mono">${esc(host)}</span></div>
        ${d.fingerabdruck?`<div class="k" style="margin-top:8px">${esc(t('Fingerabdruck','Fingerprint'))}</div><div class="key mono">${esc(d.fingerabdruck)}</div>`:''}`
      :`${e?`<div class="row">${st(e[1],e[0])}</div>`:''}
        <div class="row"><button class="btn" type="button" data-a="code">${esc(t('Code zeigen','Show a code'))}</button><span class="k" id="kamsg">${esc(msg||'')}</span></div>`}</div>
    <div class="ksec">${esc(t('Auf dem Assistenten','On the assistant'))}</div>
    <div class="kcard"><div>${esc(t('Im Panel des Pi unter Einstellungen → Spark → Spark koppeln Name und Code eintragen, oder im Terminal:','In the Pi\'s panel under Einstellungen → Spark → Spark koppeln enter name and code, or in a terminal:'))}</div><div class="key mono">sudo speech-spark teilen koppeln ${esc(host)}</div>
      <div class="k" style="margin-top:8px">${esc(t('Dann den Code eingeben. Der Pi prüft dabei den Fingerabdruck dieses Spark.','Then enter the code. The Pi checks this Spark\'s fingerprint on the way.'))}</div></div>`}
function clientDetail(c,msg){const d=SPC;
  return `<div class="kkick">${esc(t('Verbindungen','Connections'))}</div><h1>${esc(c.name)}</h1>
    <div class="ksub">${esc(KLASSE[c.klasse]||c.klasse)} · ${esc(spgText(c))}${c.gesperrt?' · '+esc(t('gesperrt','blocked')):''}</div>
    <div class="row"><span class="k" id="kcmsg" role="status">${esc(msg||'')}</span></div>
    <div class="ksec">${esc(t('Darf nutzen','May use'))}</div>
    <div class="kgrp">${d.rechte.map(x=>`<label class="krow"><span class="kt">${esc(RECHT[x]||x)}</span><input type="checkbox" class="tgl" data-recht-c="${esc(x)}"${c.rechte.includes(x)?' checked':''} aria-label="${esc(RECHT[x]||x)}"></label>`).join('')}</div>
    <div class="ksec">${esc(t('Vorrang und Grenzen','Priority and limits'))}</div>
    <div class="kcard"><div class="row"><span class="grow">${esc(t('Vorrang','Priority'))}</span><span class="seg">${d.klassen.map(k=>`<button type="button" data-k="klasse" data-v="${esc(k)}"${k===c.klasse?' class="on" aria-pressed="true"':''}>${esc(KLASSE[k]||k)}</button>`).join('')}</span></div>
      <div id="kcedit"><div class="row"><span class="k grow">${esc(spgText(c))}</span><button class="btn link" type="button" data-k="grenzen">${esc(t('Ändern','Change'))}</button></div></div></div>
    <details class="kmehr spv-box"><summary>${esc(t('So trägst du es im Programm ein','How to enter it in the program'))}</summary><div class="kcard">${sparkVerbinden(d,d.host,'','k')}</div></details>
    <div class="row"><button class="btn bad" type="button" data-k="sperren">${esc(c.gesperrt?t('Entsperren','Unblock'):t('Sperren','Block'))}</button>
      <button class="btn bad" type="button" data-k="weg">${esc(t('Löschen','Delete'))}</button></div>`}
function neuDetail(msg){const d=SPC;
  return `<div class="kkick">${esc(t('Verbindungen','Connections'))}</div><h1>${esc(t('Programm verbinden','Connect a program'))}</h1>
    <div class="ksub">${esc(t('Andere Programme im Heimnetz mit eigenem Schlüssel, Rechten, Vorrangklasse und Grenzen. Der Schlüssel ist nur einmal sichtbar.','Other programs in the home network with a key of their own, rights, priority class and limits. The key is visible only once.'))}</div>
    ${NEU_KEY?`<div class="kcard"><b>${esc(t('Schlüssel','Key'))}</b><div class="k">${esc(t('Nur jetzt sichtbar. Im Programm als API-Schlüssel eintragen (Bearer).','Visible only now. Enter it in the program as the API key (Bearer).'))}</div><div class="key mono" id="kckeyv">${esc(NEU_KEY)}</div></div>`:
    `<div class="ksec">1 · ${esc(t('Name und Vorrang','Name and priority'))}</div>
    <div class="kcard"><div class="row"><input id="kcname" class="grow" maxlength="40" placeholder="${esc(t('Name, z. B. Open WebUI','Name, e.g. Open WebUI'))}" aria-label="Name">
      <select id="kcklasse" aria-label="${esc(t('Vorrangklasse','Priority class'))}">${d.klassen.map(k=>`<option value="${esc(k)}"${k===d.vorgabe.klasse?' selected':''}>${esc(KLASSE[k]||k)}</option>`).join('')}</select></div></div>
    <div class="ksec">2 · ${esc(t('Darf nutzen','May use'))}</div>
    <div class="kgrp">${d.rechte.map(x=>`<label class="krow"><span class="kt">${esc(RECHT[x]||x)}</span><input type="checkbox" class="tgl" data-recht="${esc(x)}"${d.vorgabe.rechte.includes(x)?' checked':''} aria-label="${esc(RECHT[x]||x)}"></label>`).join('')}</div>
    <div class="ksec">3 · ${esc(t('Grenzen','Limits'))}</div><div class="kcard">${spgFelder('kcneu',d.vorgabe,'k')}</div>
    <div class="row"><button class="btn" type="button" data-k="neu">${esc(t('Schlüssel erzeugen','Make key'))}</button><span class="k" id="kcmsg" role="status">${esc(msg||'')}</span></div>`}
    <div class="kcard spv-box" id="kcverb">${sparkVerbinden(d,d.host,NEU_KEY,'k')}</div>`}
function netzDetail(msg){const d=SPC;
  return `<div class="kkick">${esc(t('Verbindungen','Connections'))}</div><h1>${esc(t('Für Programme öffnen','Open for programs'))}</h1>
    <div class="ksub">${esc(t('Nur Programme aus diesen Netzen erreichen den Spark mit ihrem Schlüssel.','Only programs from these networks reach the Spark with their key.'))}</div>
    <div class="kgrp"><label class="krow"><span class="kt"><b>${esc(t('Für Clients geöffnet','Open for clients'))}</b></span><input type="checkbox" class="tgl" id="kcan"${d.an?' checked':''} aria-label="${esc(t('Für Clients geöffnet','Open for clients'))}"></label></div>
    <div class="kcard"><div class="row"><input id="kcnetze" class="grow" value="${esc(d.netze.join(', '))}" placeholder="192.168.178.0/24" aria-label="${esc(t('Netze im Heimnetz','Home networks'))}">
      <button class="btn" type="button" data-k="schalten">${esc(t('Übernehmen','Apply'))}</button></div><span class="k" id="kcmsg" role="status">${esc(msg||'')}</span></div>`}
async function clientAct(a,b){const m=x=>{const el=$('kcmsg');if(el)el.textContent=x};
  try{if(a==='schalten'){const netze=$('kcnetze').value.split(',').map(x=>x.trim()).filter(Boolean);
      const d=await post('/api/admin/spark-clients/schalten',{an:$('kcan').checked,netze});return verbindungen(SUB,d.an?t('Geöffnet.','Open.'):t('Geschlossen.','Closed.'))}
    if(a==='neu'){const rechte=[...document.querySelectorAll('[data-recht]')].filter(x=>x.checked).map(x=>x.dataset.recht);
      const d=await post('/api/admin/spark-clients/neu',{name:$('kcname').value,rechte,klasse:$('kcklasse').value,...spgLesen('kcneu')});
      NEU_KEY=d.key;return verbindungen('neu')}
    const c=SUB.startsWith('c/')&&(SPC.clients||[]).find(x=>x.id===SUB.slice(2));if(!c)return;
    if(a==='grenzen'){$('kcedit').innerHTML=`${spgFelder('kced',c,'k')}<div class="row"><button class="btn" type="button" data-k="grenzen_ok">${esc(t('Speichern','Save'))}</button></div>`;return}
    if(a==='grenzen_ok'){await post('/api/admin/spark-clients/aendern',{id:c.id,felder:spgLesen('kced')});return verbindungen(SUB,t('Grenzen gespeichert.','Limits saved.'))}
    if(a==='klasse'){await post('/api/admin/spark-clients/aendern',{id:c.id,felder:{klasse:b.dataset.v}});return verbindungen(SUB,t('Vorrang gespeichert.','Priority saved.'))}
    if(a==='rechte'){const rechte=[...document.querySelectorAll('[data-recht-c]')].filter(x=>x.checked).map(x=>x.dataset.rechtC);
      await post('/api/admin/spark-clients/aendern',{id:c.id,felder:{rechte}});return verbindungen(SUB,t('Rechte gespeichert.','Rights saved.'))}
    if(a==='sperren'){await post('/api/admin/spark-clients/aendern',{id:c.id,felder:{gesperrt:!c.gesperrt}});return verbindungen(SUB)}
    if(a==='weg'){await post('/api/admin/spark-clients/weg',{id:c.id});return gehe('verbindungen')}}
  catch(e){m(e.message);if(a==='rechte')verbindungen(SUB,e.message)}}
async function assistentAct(){const m=x=>{const el=$('kamsg');if(el)el.textContent=x};
  try{await post('/api/konsole/koppeln');verbindungen('assistent',t('Code kommt …','Code coming …'))}catch(e){m(e.message)}}

// ---------------------------------------------------------------- Modelle (modellseite.py, the panel's own endpoints)
// switch, measure, own models from Hugging Face; every change with a code. List of the kinds on the left, the kind in
// detail on the right. The page polls while a switch or a measurement runs.
const gib=x=>x==null?'–':(Math.round(x*10)/10)+' GiB';
const EIGEN_ARTEN=['llm','sehen','asr','tts','bild','musik'];
// the search's star and the checked recommendation (Dominik 2026-11-16 „1-3“): fixed rules of the panel, shown as they come
const FORMAT={nvfp4:'NVFP4',fp8:'FP8',int:'INT4/8',bf16:'BF16'};
const NEIN={schon:t('schon im Katalog','already in the catalog'),zugang:t('privat oder mit Freigabe','private or gated'),aufgabe:t('andere Aufgabe','another task'),
  code:t('braucht eigenen Code','needs code of its own'),format:t('keine safetensors','no safetensors'),architektur:t('Bauart unbekannt','unknown architecture'),familie:t('andere Bauart als die geprüften','not the family of the checked ones'),budget:t('zu groß','too big')};
function treffer(x){const w=x.warum||{},zahl=[FORMAT[x.format]||'',x.need_gib!=null?'~'+gib(x.need_gib):'',x.lizenz||'',x.downloads+' Downloads'].filter(Boolean).join(' · ');
  return `<div class="row">${x.nein?`<span class="k"><b>${esc(x.repo)}</b> · ${esc((NEIN[x.nein]||t('geht nicht','not possible'))+(x.nein==='aufgabe'&&x.aufgabe?' ('+x.aufgabe+')':''))}</span>`:
    `<button class="btn ${x.empfohlen?'':'sec'}" type="button" data-m="nimm" data-repo="${esc(x.repo)}">${esc(x.repo)}</button>`}
    ${x.empfohlen?`<span class="pill ok">${esc(t('Empfohlen','Recommended')+': '+(FORMAT[w.format]||'')+' · ~'+gib(w.need_gib)+' '+t('von','of')+' '+gib(w.raum_gib)+' '+t('frei','free'))}</span>`:''}
    <span class="k">${esc(zahl)}</span></div>`}
const ART_SATZ={llm:t('Das Sprachmodell für Gespräche, Werkzeuge und Zusammenfassungen.','The language model for talks, tools and summaries.'),
  sehen:t('Versteht Bilder und Fotos.','Understands pictures and photos.'),asr:t('Macht aus Sprache Text.','Turns speech into text.'),
  tts:t('Spricht die Antworten.','Speaks the answers.'),bild:t('Malt Bilder auf Wunsch.','Paints pictures on request.'),musik:t('Macht Musik auf Wunsch.','Makes music on request.'),
  helfer:t('Ein kleines Modell für schnelles Einordnen.','A small model for quick sorting.'),klein:t('Kleine Modelle auf dem Prozessor.','Small models on the processor.')};
let MOD=null,MOD_T=null,MOD_FUND=null;
async function modelle(sub,msg){const el=$('tab-modelle');clearTimeout(MOD_T);
  try{MOD=await (await api('/api/admin/modelle?lang='+(EN?'en':'de'))).json()}catch(e){el.innerHTML=`<p class="k">${esc(e.message)}</p>`;return}
  modDraw(msg)}
function speicher(b){const teile=b.teile||[],belegt=teile.reduce((a,x)=>a+(x.gib||0),0);
  return `<div class="kmem">${teile.map(x=>`<i data-w="${pct(x.gib||0,b.gesamt)}"></i>`).join('')}</div>
    <div class="kleg">${teile.map(x=>`<span>${esc(x.name)} ${esc(gib(x.gib))}</span>`).join('')}<span class="frei">${esc(t('frei','free'))} ${esc(gib((b.gesamt||0)-belegt))}</span></div>`}
function modDraw(msg){const el=$('tab-modelle'),d=MOD,b=d.budget||{},teile=b.teile||[],w=d.wechsel||{},busy=w.laeuft||w.misst,arten=d.arten||[];
  const wide=matchMedia('(min-width:761px)').matches;let sub=SUB;
  if(!sub&&wide&&arten.length)sub=arten[0].art;
  const a=arten.find(x=>x.art===sub);
  const start=w.start?`<div class="kcard"><b>${esc(t('Läuft gerade','Running now'))}: ${esc(w.start.kopf||'')}</b>
      ${(w.start.zeilen||[]).map(z=>`<div class="row">${st(z.zustand==='ok'?'ok':z.zustand==='jetzt'?'warn':'',z.zustand==='ok'?'✓':z.zustand==='jetzt'?'…':'·')} ${esc(z.name)} <span class="k">${esc(z.zeit||'')}</span></div>`).join('')}
      <div class="k">${esc(w.start.rest||'')}</div></div>`:busy?`<div class="row">${st('warn',w.misst?t('Messung läuft','Measuring'):t('Wechsel läuft','Switching'))}</div>`:'';
  const belegt=teile.reduce((s,x)=>s+(x.gib||0),0);
  const liste=`<div class="klist"><h1>${esc(t('Modelle','Models'))}</h1><div class="ksub">${esc(gib(belegt))} ${esc(t('von','of'))} ${esc(gib(b.gesamt))} ${esc(t('belegt','in use'))}${d.geraet?' · '+esc(d.geraet):''}</div>
    <div class="kgrp">${arten.map(x=>{const m=x.modelle.find(y=>y.aktiv);
      return row({ic:ART_IC[x.art]||'cpu',title:x.name,sub:m?m.name:t('nichts geladen','nothing loaded'),right:m?st('ok',t('läuft','running')):st('',t('aus','off')),href:'#modelle/'+x.art,on:x.art===sub})}).join('')}</div>
    <div class="kgrp">${row({ic:'download',title:t('Eigenes Modell','Own model'),sub:t('von Hugging Face holen','fetch from Hugging Face'),href:'#modelle/eigen',on:sub==='eigen'})}</div></div>`;
  // two shelves: the checked catalog first, the own models (only the fixed rules checked them) below their own heading
  const zeile=(a,m)=>m.aktiv?'':`<div class="krow"><span class="kt"><b>${esc(m.name)}</b>${m.empfohlen?` <span class="pill">${esc(t('Empfohlen','Recommended'))}</span>`:''}${m.eigen?` <span class="pill grey">${esc(t('eigen','own'))}</span>`:''}
      <div>${esc([m.engine,gib(m.need_gib),m.messung&&m.messung.tok_s!=null?m.messung.tok_s+' tok/s':t('noch nicht gemessen','not measured yet')].join(' · '))}</div></span>
      <span class="kr">${m.messbar?`<button class="btn link" type="button" data-m="messen" data-id="${esc(m.id)}"${busy?' disabled':''}>${esc(t('Messen','Measure'))}</button>`:''}
        ${m.eigen?`<button class="btn bad" type="button" data-m="weg" data-id="${esc(m.id)}"${busy?' disabled':''}>${esc(t('Löschen','Delete'))}</button>`:''}
        ${m.waehlbar?`<button class="btn sec" type="button" data-m="wechseln" data-art="${esc(a.art)}" data-id="${esc(m.id)}"${busy?' disabled':''}>${esc(t('Laden','Load'))}</button>`:''}</span></div>`;
  let det='';
  if(a){const m=a.modelle.find(x=>x.aktiv),ei=a.modelle.filter(x=>x.eigen&&!x.aktiv),zur=(w.alte||{})[a.art];
    // the checked recommendation for this computer (modelle.json „empfohlen“): the one blue button of the page
    const e=a.modelle.find(x=>x.empfohlen);
    const rows=a.modelle.filter(m=>!m.eigen).map(m=>zeile(a,m)).join('');
    det=`<div class="kkick">${esc(t('Modelle','Models'))}</div><h1>${esc(a.name)}</h1><div class="ksub">${esc(ART_SATZ[a.art]||'')}</div>${start}
      <div class="kcard">${m?`<div class="row"><b>${esc(m.name)}</b>${st('ok',t('läuft','running'))}${m.empfohlen?`<span class="pill">${esc(t('Empfohlen','Recommended'))}</span>`:''}${m.eigen?`<span class="pill grey">${esc(t('eigen','own'))}</span>`:''}</div>
          <div class="k">${esc([m.engine,gib(m.gib!=null?m.gib:m.need_gib),m.messung&&m.messung.tok_s!=null?t('gemessen','measured')+' '+m.messung.tok_s+' tok/s':''].filter(Boolean).join(' · '))}</div>`
        :`<div class="k">${esc(t('Nichts geladen.','Nothing loaded.'))}</div>`}
        ${speicher(b)}
        <div class="row">${m&&m.messbar?`<button class="btn sec" type="button" data-m="messen" data-id="${esc(m.id)}"${busy?' disabled':''}>${esc(t('Messen','Measure'))}</button>`:''}
          ${zur?`<button class="btn link" type="button" data-m="zurueck" data-art="${esc(a.art)}"${busy?' disabled':''}>${esc(t('Vorheriges zurückholen','Bring back the previous one'))}</button>`:''}
          ${a.art==='llm'?`<a class="btn link" href="#modellgenau">${esc(t('Modell genau','Model in detail'))} ›</a>`:''}</div></div>
      ${e&&!e.aktiv?`<div class="ksec">${esc(t('Geprüfte Empfehlung','Checked recommendation'))}</div><div class="kgrp"><div class="krow"><span class="kt"><b>${esc(e.name)}</b>
          <div>${esc(t('Das geprüfte Modell, das zu diesem Rechner passt','The checked model that fits this computer')+(d.geraet?' ('+d.geraet+')':'')+' · '+gib(e.need_gib))}</div></span>
          <span class="kr">${e.waehlbar?`<button class="btn" type="button" data-m="wechseln" data-art="${esc(a.art)}" data-id="${esc(e.id)}"${busy?' disabled':''}>${esc(t('Laden','Load'))}</button>`:st('',t('nicht geladen','not loaded'))}</span></div></div>`:''}
      ${rows?`<div class="ksec">${esc(m?t('Stattdessen laden','Load instead'):t('Zur Wahl','To choose'))}</div><div class="kgrp">${rows}</div>`:''}
      ${ei.length?`<div class="ksec">${esc(t('Eigene, ungeprüft','Own, unchecked'))}</div><div class="kgrp">${ei.map(m=>zeile(a,m)).join('')}</div>`:''}
      <div class="k">${esc(t('Laden, Messen und eigene Modelle fragen nach einem Code. Messen pausiert das Sprachmodell.','Loading, measuring and own models ask for a code. Measuring pauses the language model.'))}</div>`}
  else if(sub==='eigen'){const f=MOD_FUND;
    det=`<div class="kkick">${esc(t('Modelle','Models'))}</div><h1>${esc(t('Eigenes Modell von Hugging Face','Own model from Hugging Face'))}</h1>
    <div class="ksub">${esc(t('Nur Gewichte als safetensors, kein Code aus dem Repository, eine Architektur, die der Spark kennt. Geladen wird erst beim Wechseln. Passende Treffer stehen oben, den Stern bekommt nach fester Regel der erste mit dem besten Format für diesen Rechner und Platz neben den laufenden Modellen.','Weights as safetensors only, no code from the repository, an architecture the Spark knows. It is downloaded only when you switch to it. Fitting hits come first; by a fixed rule the star goes to the first with the best format for this computer and room beside the running models.'))}</div>${start}
    <div class="kcard"><div class="row"><select id="kmart" aria-label="${esc(t('Art','Kind'))}">${EIGEN_ARTEN.map(x=>`<option value="${x}">${esc(arten.find(a=>a.art===x)?.name||x)}</option>`).join('')}</select>
      <input id="kmq" class="grow" maxlength="80" placeholder="${esc(t('Suchen, z. B. qwen3 nvfp4','Search, e.g. qwen3 nvfp4'))}" aria-label="${esc(t('Suche','Search'))}"><button class="btn sec" type="button" data-m="suche">${esc(t('Suchen','Search'))}</button></div>
    <div id="kmtreffer" data-halten></div>
    <div class="row"><input id="kmrepo" class="grow" maxlength="200" placeholder="org/name" aria-label="${esc(t('Name auf Hugging Face','Name on Hugging Face'))}"><button class="btn sec" type="button" data-m="pruefen">${esc(t('Prüfen','Check'))}</button></div>
    <div class="row" id="kmdateirow" hidden><input id="kmdatei" maxlength="200" placeholder="datei.gguf" aria-label="${esc(t('GGUF-Datei','GGUF file'))}">
      <select id="kmbasis" aria-label="${esc(t('Grundvariante','Basis'))}"></select>
      <span class="k">${esc(t('eine GGUF-Datei auf einer geprüften Grundvariante','a GGUF file on a checked basis'))}</span></div>
    ${f?`<div class="row"><b>${esc(f.name&&f.name.de?(EN?f.name.en:f.name.de):f.repo)}</b> <span class="k mono">${esc(f.repo)} @ ${esc(String(f.revision).slice(0,10))}</span></div>
      <div class="k">${esc(t('Speicher','Memory'))} ${esc(gib(f.need_gib))} · ${esc(t('Platte','Disk'))} ${esc(f.platte_gb)} GB · ${esc(t('Lizenz','License'))} ${esc(f.lizenz)}${f.gewerblich?'':' · '+esc(t('nicht gewerblich','non-commercial'))}</div>
      <div class="row"><button class="btn" type="button" data-m="dazu">${esc(t('Hinzufügen','Add'))}</button></div>`:''}</div>`}
  const back=`<a class="kback konly-phone" href="#modelle">‹ ${esc(t('Modelle','Models'))}</a>`;
  felderNeu(el,`<div class="kld${SUB&&det?' open':''}">${liste}<div class="kdet">${det?back+`<div class="row"><span class="k" id="kmmsg" role="status">${esc(msg||'')}</span></div>`+det:''}</div></div>`);
  el.querySelectorAll('[data-w]').forEach(x=>{x.style.width=x.dataset.w+'%'});
  // the GGUF file and its basis only for pictures and music, with the bases of the kind chosen (Dominik 17.11.: the row
  // stood under „Sprachmodell“ too, with the bases of both kinds mixed)
  const datei=()=>{const art=$('kmart').value,l=(w.basen||{})[art]||[];$('kmdateirow').hidden=!['bild','musik'].includes(art)||!l.length;
    $('kmbasis').innerHTML=l.map(b=>`<option value="${esc(b[0])}">${esc(b[1])}</option>`).join('')};
  if($('kmart')){$('kmart').onchange=datei;datei()}
  // only while something runs (a finished start stays on the page but asks for nothing more)
  if(busy||(w.start&&!w.start.ende))MOD_T=setTimeout(()=>{if(TAB==='modelle')modelle(SUB)},5000)}
async function modAct(a,b){const m=x=>{const el=$('kmmsg');if(el)el.textContent=x};const L='?lang='+(EN?'en':'de');
  try{
    if(a==='wechseln'){MOD=await post('/api/admin/modelle/wechseln'+L,{art:b.dataset.art,id:b.dataset.id});return modDraw(t('Wechsel angefragt.','Switch requested.'))}
    if(a==='zurueck'){MOD=await post('/api/admin/modelle/zurueck'+L,{art:b.dataset.art});return modDraw(t('Zurückholen angefragt.','Bring-back requested.'))}
    if(a==='messen'){MOD=await post('/api/admin/modelle/messen'+L,{id:b.dataset.id});return modDraw(t('Messung angefragt. Das Sprachmodell pausiert währenddessen.','Measurement requested. The language model pauses meanwhile.'))}
    if(a==='weg'){MOD=await (await api('/api/admin/modelle/eigen/'+encodeURIComponent(b.dataset.id)+L,{method:'DELETE'})).json();MOD_FUND=null;return modDraw(t('Gelöscht.','Deleted.'))}
    if(a==='suche'){const d=await post('/api/admin/modelle/eigen/suche',{art:$('kmart').value,q:$('kmq').value});
      $('kmtreffer').innerHTML=(d.treffer||[]).map(treffer).join('')||`<p class="k">${esc(t('Nichts gefunden.','Nothing found.'))}</p>`;return}
    if(a==='nimm'){$('kmrepo').value=b.dataset.repo;return modAct('pruefen')}
    if(a==='pruefen'){const art=$('kmart').value,datei=['bild','musik'].includes(art)?{datei:$('kmdatei').value.trim(),basis:$('kmbasis').value}:{};
      const d=await post('/api/admin/modelle/eigen/pruefen',Object.assign({art,repo:$('kmrepo').value.trim()},datei));MOD_FUND=Object.assign(d.vorschlag,{_art:art,_datei:datei});return modDraw()}
    if(a==='dazu'&&MOD_FUND){const art=MOD_FUND._art;MOD=await post('/api/admin/modelle/eigen'+L,Object.assign({art,repo:MOD_FUND.repo,revision:MOD_FUND.revision},MOD_FUND._datei));MOD_FUND=null;
      gehe('modelle/'+art);return modDraw(t('Hinzugefügt. Mit „Laden“ wird es geholt und gestartet.','Added. “Load” downloads and starts it.'))}
  }catch(e){m(e.message)}}

// ---------------------------------------------------------------- Wartung: Updates and Logs on one page
let LOG_T=null,LOG_NAME=LOGS[0];
async function wartung(sub){const el=$('tab-wartung');
  if(sub.startsWith('log/')&&LOGS.includes(sub.slice(4)))LOG_NAME=sub.slice(4);
  el.innerHTML=`<h1>${esc(t('Wartung','Maintenance'))}</h1><div class="ksub">${esc(t('Version, Updates und die Logs dieses Spark.','Version, updates and the logs of this Spark.'))}</div>
    <div class="ksec">Updates</div><div id="kwupd"><div class="kcard k">…</div></div>
    <div class="ksec">Logs</div><div class="kcard"><div class="row"><span class="seg" id="kwlogs">${LOGS.map(n=>`<button type="button" data-l="${esc(n)}"${n===LOG_NAME?' class="on" aria-pressed="true"':''}>${esc(DIENST[n]||n)}</button>`).join('')}</span>
      <label class="k"><input type="checkbox" id="kwfolge"> ${esc(t('Mitlaufen','Follow'))}</label></div><pre id="klog">…</pre></div>
    <div class="konly-phone kcard"><div class="row">${st('ok',WHO.version||'')}<span class="grow"></span><button class="btn sec" type="button" id="kout2">${esc(t('Abmelden','Sign out'))}</button></div></div>`;
  $('kwfolge').onchange=()=>{clearTimeout(LOG_T);if($('kwfolge').checked)logs(LOG_NAME)};
  $('kout2').onclick=abmelden;
  updates();logs(LOG_NAME)}
async function updates(msg){const el=$('kwupd');if(!el)return;let d,p={};
  try{d=await (await api('/api/update')).json();p=await (await api('/api/update/progress?log=true')).json()}catch(e){el.innerHTML=`<div class="kcard k">${esc(e.message)}</div>`;return}
  UPD=d;const inst=d.installed||{},rem=d.remote||{},neu=rem.version&&rem.version!==inst.version,laeuft=p.running||d.running;
  setHtml(el,`<div class="kcard"><div class="row"><span class="kt grow"><span class="k">${esc(t('Version','Version'))}</span><br><b class="kv">${esc(inst.version||inst.short||'?')}</b></span>
      ${neu?st('warn',t('Neu','New')+' '+rem.version):st('ok',t('aktuell','up to date'))}</div>
    <div class="k">${esc(t('Dieser Spark aktualisiert sich selbst; nur Versionen mit grünen Tests.','This Spark updates itself; only versions with green tests.'))}</div>
    <div class="row"><button class="btn${neu?'':' sec'}" type="button" data-u="start"${laeuft||!neu?' disabled':''}>${esc(t('Jetzt aktualisieren','Update now'))}</button>
      <button class="btn link" type="button" data-u="pruefen">${esc(t('Neu prüfen','Check again'))}</button><span class="k" id="kumsg">${esc(msg||'')}</span></div>
    ${laeuft?`<div class="row">${st('warn',t('läuft','running'))} ${esc(p.text||'')}</div>`:''}
    <details class="kmehr"${laeuft?' open':''}><summary>${esc(t('Ablauf','Progress'))}</summary><pre>${esc((p.log||[]).join('\n')||t('Noch kein Update in diesem Lauf.','No update in this run yet.'))}</pre></details></div>`);
  clearInterval(TIMER);if(laeuft)TIMER=setInterval(()=>{if(TAB==='wartung')updates()},4000)}
async function updateAct(a){const m=x=>{const el=$('kumsg');if(el)el.textContent=x};
  try{if(a==='start'){await post('/api/update');return updates(t('Gestartet.','Started.'))}
    if(a==='pruefen'){await api('/api/update?check=true');await updates();return updMark()}}
  catch(e){m(e.message)}}
async function logs(name){clearTimeout(LOG_T);name=LOGS.includes(name)?name:LOGS[0];LOG_NAME=name;
  document.querySelectorAll('#kwlogs button').forEach(b=>{const on=b.dataset.l===name;b.classList.toggle('on',on);if(on)b.setAttribute('aria-pressed','true');else b.removeAttribute('aria-pressed')});
  const pre=$('klog');if(!pre)return;
  try{const txt=await (await api('/api/logs/'+encodeURIComponent(name)+'?lines=300')).text();
    if(pre.textContent!==txt){const unten=pre.scrollTop+pre.clientHeight>=pre.scrollHeight-4;pre.textContent=txt;if(unten)pre.scrollTop=pre.scrollHeight}}
  catch(e){pre.textContent=e.message}
  if($('kwfolge')&&$('kwfolge').checked&&TAB==='wartung')LOG_T=setTimeout(()=>logs(LOG_NAME),5000)}

async function abmelden(){try{await /*raw: the console loads without base.js*/fetch('/api/logout',{method:'POST'})}catch{}showLogin()}
document.addEventListener('click',e=>{const b=e.target.closest('button');if(!b)return;
  if(b.dataset.k)clientAct(b.dataset.k,b);else if(b.dataset.u)updateAct(b.dataset.u);else if(b.dataset.l)logs(b.dataset.l);else if(b.dataset.a)assistentAct();else if(b.dataset.m)modAct(b.dataset.m,b)});
document.addEventListener('change',e=>{if(e.target.matches&&e.target.matches('[data-recht-c]'))clientAct('rechte',e.target)});
window.addEventListener('hashchange',()=>{if(!$('kside').hidden)show()});
document.addEventListener('DOMContentLoaded',()=>{
  iconsIn(document);
  if(EN){document.documentElement.lang='en';$('klt').textContent='Sign in';$('kld').textContent="This Spark's console. Home network only, with the password from the installation.";
    $('klpw').placeholder='Password';$('klcode').placeholder='Code from the app';$('klgo').textContent='Sign in';$('kout').textContent='Sign out';
    $('kct').textContent='Confirm with a code';$('kcd').textContent='This change needs a fresh code from the authenticator app.';$('kcok').textContent='Confirm';$('kcno').textContent='Cancel';$('kmgt').textContent='Model in detail';
    $('kmgback').textContent='‹ Overview';
    const tabs={ueberblick:'Overview',modelle:'Models',verbindungen:'Connections',wartung:'Maintenance'};document.querySelectorAll('#ktabs a').forEach(a=>{a.querySelector('span').textContent=tabs[a.dataset.tab]})}
  $('klform').addEventListener('submit',login);
  $('kout').addEventListener('click',abmelden);
  $('kcok').addEventListener('click',()=>codeDone($('kcin').value.trim()));$('kcno').addEventListener('click',()=>codeDone(''));
  $('kcin').addEventListener('keydown',e=>{if(e.key==='Enter')codeDone($('kcin').value.trim())});
  start()});
