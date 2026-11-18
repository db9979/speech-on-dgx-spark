// Ein Programm verbinden (Spark-Clients, Dominik 2026-11-14 „richtig dokumentiert … was ich eingeben muss“): what a
// program enters to reach this Spark, filled with its address, ports, fixed model names and the key just made. Shared
// by the panel (sparkclients.js) and the Spark-Konsole (konsole.js); both define t() and esc(). The certificate is
// public (mandanten.verbinden); the key is shown only right after it was made. Everything through esc().
// Also the limits of a client (Dominik 2026-11-14 „keine Grenzen oder einstellbar“), new and existing: three numbers,
// 0 or empty = no limit (mandanten.OHNE), and one box for no limits at all; the Spark checks every value again.
let SPV_PEM='';
const SPV_DIENST=[['llm','/v1',['Sprachmodell (OpenAI-kompatibel), Basis-URL','Language model (OpenAI compatible), base URL']],
  ['asr','/v1/audio/transcriptions',['Hören (Spracherkennung)','Listening (speech recognition)']],
  ['tts','/v1/audio/speech',['Sprechen (Sprachausgabe)','Speaking (speech output)']],
  ['bild','/v1/bild',['Bilder malen','Painting pictures']],['musik','/v1/musik',['Musik machen','Making music']]];
function spvHost(h){h=h||location.hostname;return h.includes(':')?`[${h}]`:h}
function sparkVerbinden(d,host,key,klein){const v=d&&d.verbinden;if(!v)return '';
  const k=klein||'',s=v.https?'https':'http',h=spvHost(host),c=x=>`<code>${esc(x)}</code>`;SPV_PEM=v.zertifikat||'';
  const url=(art,p)=>`${s}://${h}:${v.dienste[art]}${p}`;
  const rows=SPV_DIENST.filter(([a])=>v.dienste[a]).map(([a,p,n])=>`<tr><td>${esc(t(n[0],n[1]))}</td><td>${c(url(a,p))}${a==='llm'?`<div class="${k}">${esc(t('Modellname','Model name'))} ${c(v.modell)} · ${esc(t('Bilder verstehen','Understand pictures'))} ${c('sehen')} · ${esc(t('Hilfsmodell','Helper model'))} ${c('helfer')}</div>`:''}</td></tr>`).join('');
  // Einbetten / Nachsortieren through the LLM-Tor, only while a model of that kind is loaded (Spark-Konsole, Spark alone)
  const pool=v.pool||{},prow=(art,p,n)=>pool[art]&&v.dienste.llm?`<tr><td>${esc(t(n[0],n[1]))}</td><td>${c(url('llm',p))}<div class="${k}">${esc(t('Modellname','Model name'))} ${c(pool[art])} · ${esc(t('Recht','Right'))} „${esc(t(n[2],n[3]))}“</div></td></tr>`:'';
  const prows=prow('einbetten','/v1/embeddings',['Einbetten (OpenAI-kompatibel)','Embeddings (OpenAI compatible)','Einbetten','Embeddings'])
    +prow('nachsortieren','/v1/rerank',['Nachsortieren (wie Jina/Cohere, z. B. Open WebUI)','Re-ranking (like Jina/Cohere, e.g. Open WebUI)','Nachsortieren','Re-ranking']);
  const schl=key||'sk-spark-…';
  const probe=v.dienste.llm?url('llm','/v1/spark/faehigkeiten'):v.dienste.asr?url('asr','/v1/spark/faehigkeiten'):'';
  return `<h3>${esc(t('Ein Programm verbinden','Connect a program'))}</h3>
  <ol class="spv">
    <li>${esc(t('Oben „Für Clients geöffnet“ einschalten, das Netz des Programms eintragen (z. B. 192.168.178.0/24) und „Übernehmen“.','Above, switch on “Open for clients”, enter the program\'s network (e.g. 192.168.178.0/24) and “Apply”.'))}${d.an?'':` <b>${esc(t('Noch aus.','Still off.'))}</b>`}</li>
    <li>${esc(t('Name, Vorrangklasse und Rechte wählen, „Schlüssel erzeugen“ und den Schlüssel sofort kopieren: er ist nur jetzt sichtbar.','Choose name, priority class and rights, “Make key” and copy the key right away: it is visible only now.'))}</li>
    <li>${esc(t('Im Programm eintragen:','Enter in the program:'))}
      <table class="spvt"><tbody>${rows}${prows}<tr><td>${esc(t('API-Schlüssel (Bearer)','API key (Bearer)'))}</td><td>${c(schl)}</td></tr></tbody></table></li>
    ${v.https?`<li>${esc(t('Zertifikat: der Spark nutzt ein eigenes, selbst signiertes Zertifikat. Die Datei laden und im Programm als vertrauenswürdig eintragen (oft „CA-Zertifikat“ oder „Zertifikat-Datei“); ohne das meldet das Programm einen Zertifikatfehler.','Certificate: the Spark uses a self-signed certificate of its own. Download the file and enter it in the program as trusted (often “CA certificate” or “certificate file”); without it the program reports a certificate error.'))}
      ${SPV_PEM?`<div class="row"><button class="b btn sec" type="button" data-spv="zert">${esc(t('Zertifikat laden','Download certificate'))}</button></div>`:''}
      <div class="${k}">${esc(t('Fingerabdruck (SHA-256) zum Vergleichen:','Fingerprint (SHA-256) to compare:'))} ${c(v.fingerabdruck||'–')}</div></li>`
      :`<li>${esc(t('Ohne Verschlüsselung (http), nur aus den Netzen oben. Kein Zertifikat nötig.','Without encryption (http), only from the networks above. No certificate needed.'))}</li>`}
    ${probe?`<li>${esc(t('Prüfen (im Terminal des Programm-Rechners, mit dem Schlüssel):','Check (in a terminal on the program\'s computer, with the key):'))}
      <pre>curl${v.https?' --cacert spark-zertifikat.pem':''} -H "Authorization: Bearer ${esc(schl)}" ${esc(probe)}</pre>
      <div class="${k}">${esc(t('Die Antwort nennt die Dienste und was der Schlüssel darf.','The answer lists the services and what the key may do.'))}</div></li>`:''}
  </ol>
  <div class="${k}">${esc(t('Wenn es nicht klappt: 401 = Schlüssel falsch oder gelöscht · 403 „netz“ = Netz fehlt oben · 403 „recht“ = Recht fehlt beim Client · 429 = Grenze erreicht · keine Verbindung = „Für Clients geöffnet“ aus oder Netz fehlt · Zertifikatfehler = Zertifikat nicht eingetragen.','If it fails: 401 = wrong or deleted key · 403 “netz” = network missing above · 403 “recht” = the client lacks the right · 429 = limit reached · no connection = “Open for clients” off or network missing · certificate error = certificate not entered.'))}</div>`}
document.addEventListener('click',e=>{const b=e.target.closest&&e.target.closest('[data-spv="zert"]');if(!b||!SPV_PEM)return;
  const a=document.createElement('a');a.href=URL.createObjectURL(new Blob([SPV_PEM],{type:'application/x-pem-file'}));
  a.download='spark-zertifikat.pem';document.body.appendChild(a);a.click();setTimeout(()=>{URL.revokeObjectURL(a.href);a.remove()},1000)});
const SPG=[['minute',['Anfragen pro Minute','Requests per minute'],600],['parallel',['gleichzeitig','at once'],8],['tokens_tag',['Tokens pro Tag','Tokens per day'],50000000]];
function spgText(c){if(SPG.every(([k])=>c[k]===0))return t('keine Grenzen','no limits');
  return [c.minute?`${c.minute}/min`:t('ohne Minutengrenze','no limit per minute'),
    c.parallel?t(`${c.parallel} gleichzeitig`,`${c.parallel} at once`):t('beliebig viele gleichzeitig','any number at once'),
    c.tokens_tag?t(`${c.tokens_tag} Tokens/Tag`,`${c.tokens_tag} tokens/day`):t('Tokens ohne Grenze','tokens without limit')].join(' · ')}
function spgFelder(p,c,klein){const o=SPG.every(([k])=>c[k]===0);
  return `<div class="row spg">${SPG.map(([k,n,max])=>`<label>${esc(t(n[0],n[1]))} <input type="number" id="${p}_${k}" min="0" max="${max}" value="${c[k]?esc(c[k]):''}" placeholder="${esc(t('keine Grenze','no limit'))}"${o?' disabled':''}></label>`).join(' ')}
    <label><input type="checkbox" id="${p}_ohne" data-spg="${p}"${o?' checked':''}> ${esc(t('Keine Grenzen','No limits'))}</label></div>
    <div class="${klein||''}">${esc(t('Leer oder 0 heißt keine Grenze. Ohne Grenzen bremst nur noch der Vorrang: die Sprache des Assistenten geht immer vor.','Empty or 0 means no limit. Without limits only the priority holds back: the assistant\'s speech always goes first.'))}</div>`}
function spgLesen(p){const o=document.getElementById(p+'_ohne'),out={};
  for(const [k] of SPG){const v=(document.getElementById(p+'_'+k)||{}).value||'';out[k]=o&&o.checked?0:(v.trim()===''?0:parseInt(v,10));
    if(!Number.isInteger(out[k])||out[k]<0)throw new Error(t('Bitte ganze Zahlen ab 0.','Please whole numbers from 0.'))}
  return out}
document.addEventListener('change',e=>{const b=e.target.closest&&e.target.closest('[data-spg]');if(!b)return;
  for(const [k] of SPG){const i=document.getElementById(b.dataset.spg+'_'+k);if(i)i.disabled=b.checked}});
