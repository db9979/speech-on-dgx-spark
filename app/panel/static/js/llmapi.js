// "Ich → Sprachmodell per API" (llmapi.py, plan llm-api/plan.md): own programs use the Spark's language model,
// OpenAI-compatible at /v1, with a key of this profile. Text only; up to 5 keys, each "home network only" or "also from
// outside"; the key is shown once. The admin sees every key under Apps und Schnittstellen.
let LLMAPI_ON=false,LLMAPI_NEW=null;
const laWhen=x=>x?new Date(x*1000).toLocaleString([], {dateStyle:'short',timeStyle:'short'}):t('noch nie','never');
const laWhere=w=>w==='extern'?t('auch von außen','also from outside'):t('nur Heimnetz','home network only');
const laNum=n=>Number(n||0).toLocaleString();
const LLMAPI_WARN=()=>t('Von außen: Der Schlüssel öffnet das Sprachmodell des Spark über den Reverse-Proxy im Internet. Wer ihn hat, kann Fragen stellen, bis du ihn löschst. Fragen und Antworten werden nicht gespeichert, gehen aber durch den Proxy zum Programm.',
  'From outside: the key opens the Spark\'s language model through the reverse proxy on the internet. Whoever has it can ask until you delete it. Questions and answers are not kept, but they pass the proxy to the program.');
// the address a program in the home network uses: this page's host when it is one there, else a placeholder
function laLan(port){const h=location.hostname;
  const lan=/^(10|127|192\.168|172\.(1[6-9]|2\d|3[01]))\./.test(h)||!h.includes('.')||/\.(local|lan|home|fritz\.box)$/.test(h);
  return `http://${lan?h:t('SPARK-IP','SPARK-IP')}:${port||31080}/v1`}
async function showLlmApi(){const box=$('llmapibox');if(!box)return;if(!PROFILE||!LLMAPI_ON){box.innerHTML='';return}
  let d={keys:[]};try{d=await (await api('/api/profile/llmapi')).json()}catch{}
  const lim=d.unlimited?t('ohne Grenzen (Admin)','no limits (admin)'):`${d.per_minute} ${t('pro Minute','per minute')} · ${d.at_once} ${t('gleichzeitig','at once')} · ${t('höchstens','at most')} ${laNum(d.tag_k*1000)} ${t('Tokens in 24 Stunden','tokens in 24 hours')}`;
  const row=k=>`<li><span><b>${esc(k.name)}</b> <small class="ftag ${k.where==='extern'?'out':'me'}">${esc(laWhere(k.where))}</small><br>
      <small class="mut">${t('zuletzt','last used')}: ${esc(laWhen(k.last))} · ${laNum(k.used)} ${t('Tokens in 24 Stunden','tokens in 24 hours')}${!d.unlimited&&k.tag_k?' · '+t('Tageslimit','daily limit')+' '+laNum(k.tag_k*1000):''} · ${t('endet ohne Nutzung am','ends without use on')} ${esc(new Date(k.ends*1000).toLocaleDateString())}</small></span>
      <button class="b" type="button" data-ladel="${esc(k.id)}" data-laname="${esc(k.name)}">${t('Löschen','Delete')}</button></li>`;
  box.innerHTML=`<div class="intro">${t('Eigene Programme (Python openai, Open WebUI, Continue, n8n …) nutzen das Sprachmodell des Spark wie die OpenAI-Schnittstelle: nur Text, ohne Werkzeuge des Spark und ohne deine Daten. Fragen und Antworten werden nicht gespeichert; Sprache geht immer vor.','Own programs (Python openai, Open WebUI, Continue, n8n …) use the Spark\'s language model like the OpenAI interface: text only, without the Spark\'s tools and without your data. Questions and answers are not kept; speech always goes first.')}</div>
    ${d.on?`<div class="fh">${t('Grenzen je Schlüssel','Limits per key')}: ${esc(lim)}</div>${d.assist?`<div class="fh">${t('Modell „spark-assistent“: dein Spark-Assistent, nur lesend (Kalender, Erinnerungen, Dokumente, Nachschlagen); nichts wird gespeichert oder geschaltet.','Model "spark-assistent": your Spark assistant, read only (calendar, reminders, documents, look-ups); nothing is kept or switched.')}</div>`:''}
    <h3 style="margin:14px 0 4px">${t('Meine Schlüssel','My keys')} (${d.keys.length} ${t('von','of')} ${d.most})</h3><ul class="facts">${d.keys.map(row).join('')||`<li class="mut"><span>${t('Noch kein Schlüssel.','No key yet.')}</span></li>`}</ul>
    ${d.keys.length<d.most?`<details style="margin-top:10px"><summary>${t('＋ Schlüssel anlegen','＋ Make a key')}</summary>
      <label>${t('Name des Programms','Name of the program')}</label><input id="laname" maxlength="60" placeholder="${t('z. B. Laptop Continue','e.g. Laptop Continue')}" autocomplete="off">
      <label>${t('Erreichbar','Reachable')}</label><select id="lawhere"><option value="lokal">${t('Nur im Heimnetz (empfohlen)','Home network only (recommended)')}</option>${d.extern?`<option value="extern"${d.mfa?'':' disabled'}>${t('Auch von außen über den Reverse-Proxy','Also from outside through the reverse proxy')}${d.mfa?'':t(' (braucht deinen zweiten Anmeldeschritt)',' (needs your second sign-in step)')}</option>`:''}</select>
      <div class="fh err" id="lawarn" hidden>${esc(LLMAPI_WARN())}</div>
      ${d.unlimited?'':`<label>${t('Tageslimit in tausend Tokens (leer: das Höchste)','Daily limit in thousand tokens (empty: the highest)')}</label><input id="latag" type="number" min="1" max="${d.tag_k}" placeholder="${d.tag_k}">`}
      <div class="row" style="margin-top:8px"><button class="b p" type="button" id="lamake">${t('Schlüssel erzeugen','Create key')}</button></div>
      <div class="fh" id="lamakemsg" role="status"></div>
      <div id="lakey"></div></details>`:''}`:`<div class="fh">${t('Für dein Profil gerade gesperrt.','Blocked for your profile right now.')}</div>`}
    <div class="fh" id="lamsg"></div><div id="owuibox"></div>`;
  laKeyShow();if(typeof showOwui==='function')showOwui();
  if($('lawhere'))$('lawhere').onchange=()=>{$('lawarn').hidden=$('lawhere').value!=='extern'};
  if($('lamake'))$('lamake').onclick=async()=>{const where=$('lawhere').value,b=$('lamake'),say=(x,err)=>{xmsg('lamakemsg',x,err);$('lamakemsg').scrollIntoView({block:'nearest'})};
    const name=$('laname').value.trim(),tag=$('latag')&&$('latag').value?parseInt($('latag').value,10):null;
    if(!name){say(t('Bitte zuerst einen Namen für das Programm eingeben.','Please enter a name for the program first.'),true);$('laname').focus();return}
    if(where==='extern'&&!confirm(LLMAPI_WARN()))return;
    b.disabled=true;say(t('Schlüssel wird erzeugt …','Creating the key …'));
    try{const body={name,where};if(tag)body.tag_k=tag;const r=await (await api('/api/profile/llmapi/keys',xjson('POST',body))).json();
      LLMAPI_NEW=Object.assign({},r,{url:where==='extern'?r.url:laLan(CFG&&CFG.panel&&CFG.panel.port)});await showLlmApi();
      const k=$('lakey');if(k)k.scrollIntoView({block:'nearest'})}
    catch(e){b.disabled=false;say(/code required|Code/i.test(errRaw(e))?t('Ohne deinen Code geht es nicht: bitte noch einmal tippen und den Code aus der Authenticator-App eingeben.','Not without your code: tap again and enter the code from your authenticator app.'):e.message,true)}};
  box.querySelectorAll('[data-ladel]').forEach(b=>b.onclick=async()=>{if(!confirm(t('„','"')+b.dataset.laname+t('“ löschen? Der Schlüssel gilt dann sofort nicht mehr.','" delete? The key stops working at once.')))return;
    try{await api('/api/profile/llmapi/keys/'+encodeURIComponent(b.dataset.ladel),{method:'DELETE'});showLlmApi()}catch(e){xmsg('lamsg',e.message,true)}})}
// the new key, shown once right after "Schlüssel erzeugen" (the page is drawn again with the new key)
function laKeyShow(){const k=$('llmapibox').querySelector('#lakey'),r=LLMAPI_NEW;LLMAPI_NEW=null;if(!k||!r)return;k.closest('details').open=true;
  k.innerHTML=`<div class="fh"><b>${t('Nur jetzt sichtbar:','Shown only now:')}</b> ${t('Schlüssel kopieren und im Programm eintragen.','copy the key and enter it in the program.')}</div>
    <table><tbody>${[['base_url',r.url],['api_key',r.token]].map(([a,b])=>`<tr><td>${esc(a)}</td><td><code>${esc(b)}</code></td></tr>`).join('')}</tbody></table>
    <pre>from openai import OpenAI
c = OpenAI(base_url="${esc(r.url)}", api_key="${esc(r.token)}")
print(c.chat.completions.create(model="spark", messages=[{"role": "user", "content": "Hallo"}]).choices[0].message.content)</pre>
    <div class="fh">${t('Der Modellname ist egal: der Spark nimmt immer sein eigenes Sprachmodell.','The model name does not matter: the Spark always uses its own language model.')}</div>`;
  xmsg('lamsg',t('Schlüssel angelegt.','Key made.'))}
// Apps und Schnittstellen (admin): every key of every profile, with "Löschen"
async function loadLlmApiAdmin(){const el=$('int-llmapi');if(!el)return;let d;try{d=await (await api('/api/admin/llmapi')).json()}catch{el.innerHTML='';return}
  if(!d.enabled){el.innerHTML=`<div class="mut">${t('Aus. Einschalten unter Funktionen → Sprachmodell per API.','Off. Switch on under Features → Language model by API.')}</div>`;return}
  el.innerHTML=`<table><tbody>${d.keys.map(k=>`<tr><td><b>${esc(k.name)}</b><br><small class="mut">${esc(k.profile)} · ${esc(laWhere(k.where))} · ${t('zuletzt','last used')} ${esc(laWhen(k.last))} · ${laNum(k.used)} ${t('Tokens in 24 Stunden','tokens in 24 hours')}</small></td>
    <td><button class="b" type="button" data-laadel="${esc(k.id)}">${t('Löschen','Delete')}</button></td></tr>`).join('')||`<tr><td class="mut">${t('Noch kein Schlüssel.','No key yet.')}</td></tr>`}</tbody></table>`;
  el.querySelectorAll('[data-laadel]').forEach(b=>b.onclick=async()=>{if(!confirm(t('Schlüssel löschen? Er gilt dann sofort nicht mehr.','Delete the key? It stops working at once.')))return;
    try{await api('/api/admin/llmapi/'+encodeURIComponent(b.dataset.laadel),{method:'DELETE'});loadLlmApiAdmin()}catch(e){alert(e.message)}})}
