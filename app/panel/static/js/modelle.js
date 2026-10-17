// ---------------------------------------------------------------- Zustand → Modelle (admin)
// The model catalog (app/modelle.json) per kind, the models this configuration runs, the memory budget and the last
// measurement (sudo speech-spark modelle messen, or „Messen“ per model). Stage E4, with Funktionen → Modelle wechseln on: „Wechseln“ per
// model and „Zurückholen“ per kind for 7 days; the root unit speech-spark-wechsel does the work, the panel only asks.
// Stage E5, with Funktionen → Eigene Modelle on: „Prüfen“ and „Hinzufügen“ of a Hugging Face model for the language
// model or image understanding (the panel checks the fixed rules), „Löschen“ per own model.
const MD_NEIN={revision:['noch nicht gemessen','not measured yet'],aus:['erst umziehen','move first'],budget:['zu knapp','too tight'],engine:['nicht wählbar','not selectable'],ungeprueft:['erst messen','measure first']};
const MD_REGEL={alle:['Alle Modelle passen gleichzeitig in den Speicher.','All models fit into memory at the same time.'],
  ein_platz:['Knapp: Modelle bei Bedarf (Bilder malen, Bildverständnis, Nachsortieren) laden nacheinander, nie gleichzeitig.','Tight: models on demand (painting pictures, image understanding, re-ranking) load one after the other, never at once.'],
  zu_knapp:['Zu knapp: neben den festen Modellen bleibt weniger als die Reserve. Ein kleineres Modell wählen oder qwen38 im 1M-Modus abschalten.','Too tight: beside the fixed models less than the reserve is left. Choose a smaller model or switch qwen38 out of its 1M mode.']};
function mdGib(v){return v==null?'–':(Math.round(v*10)/10).toLocaleString(L==='en'?'en':'de')+' GiB'}
function mdMess(m){const x=m.messung||{};if(!Object.keys(x).length)return '';if(x.ok===false)return t('abgebrochen','broke off');
  const ja=v=>v?t('ok','ok'):t('falsch','wrong');
  return [x.tok_s!=null?x.tok_s+' tok/s':'',x.erste_s!=null?t('erste ','first ')+x.erste_s+' s':'',x.mtp_annahme!=null?'MTP '+Math.round(x.mtp_annahme*100)+' %':'',x.erste_warm_s!=null?t('warm ','warm ')+x.erste_warm_s+' s':'',x.zwischenspeicher!=null?t('Zwischenspeicher ','Prefix cache ')+Math.round(x.zwischenspeicher*100)+' %':'',
    'werkzeug' in x?t('Werkzeug ','Tool ')+ja(x.werkzeug):'','bild_text' in x?t('Text ','Text ')+ja(x.bild_text):'','bild_szene' in x?t('Szene ','Scene ')+ja(x.bild_szene):''].filter(Boolean).join(' · ')}
function mdBudget(b){const pct=v=>Math.max(0,Math.min(100,Math.round(100*v/(b.gesamt||1))));
  return `<div class="card"><h3>${esc(t('Speicher-Budget','Memory budget'))}</h3><div class="vb-hb vb-qbar"><i class="${b.regel==='alle'?'':'full'}" style="width:${pct(b.fest+b.system+b.reserve)}%"></i></div>`+
    `<div class="vb-tw"><table class="vb-tab"><tbody>`+
    [[t('Speicher gesamt','Memory in total'),b.gesamt],[t('Feste Modelle','Fixed models'),b.fest],[t('System','System'),b.system],[t('Reserve','Reserve'),b.reserve],
     [t('Modelle bei Bedarf','Models on demand'),b.bedarf],[t('Frei für Modelle bei Bedarf','Free for models on demand'),b.frei]]
      .map(([k,v])=>`<tr><td>${esc(k)}</td><td class="n">${esc(mdGib(v))}</td></tr>`).join('')+
    `</tbody></table></div><div class="mut vb-note">${esc(t(...(MD_REGEL[b.regel]||['',''])))}</div></div>`}
// „Messen“ (Dominik 2026-10-17): like sudo speech-spark modelle messen <id>; the language model pauses meanwhile
function mdMessKnopf(m,w){return m.messbar&&!w.laeuft&&!w.misst?` <button type="button" class="b sm" data-mdm="${esc(m.id)}">${esc(t('Messen','Measure'))}</button>`:''}
function mdTun(m,a,w){if(!w.an)return '';if(m.aktiv)return mdMessKnopf(m,w);
  const weg=w.eigene&&m.eigen&&!w.laeuft?` <button type="button" class="b sm danger" data-mde="${esc(m.id)}">${esc(t('Löschen','Delete'))}</button>`:'';
  if(m.waehlbar)return (w.laeuft||w.misst?'':`<button type="button" class="b sm" data-mdw="${esc(a.art)}" data-mdid="${esc(m.id)}">${esc(t('Wechseln','Switch'))}</button>`)+mdMessKnopf(m,w)+weg;
  return (MD_NEIN[m.nein]?`<span class="mut">${esc(t(...MD_NEIN[m.nein]))}</span>`:'')+mdMessKnopf(m,w)+weg}
function mdAlt(a,w,d){const x=(w.alte||{})[a.art];if(!w.an||!x)return '';
  const n=(d.arten.flatMap(y=>y.modelle).find(y=>y.id===x.id)||{}).name||x.id;
  return `<div class="row vb-note"><span class="mut">${esc(t('Vorher: ','Before: ')+n+(x.tage_frei?t(' · noch '+x.tage_frei+' Tage zurückholbar',' · can be brought back for '+x.tage_frei+' more days'):t(' · älter als '+w.tage+' Tage',' · older than '+w.tage+' days')))}</span>`+
    (x.tage_frei&&!w.laeuft?` <button type="button" class="b sm" data-mdz="${esc(a.art)}">${esc(t('Zurückholen','Bring back'))}</button>`:'')+`</div>`}
function mdArt(a,w,d){if(!a.modelle.length)return '';
  const rows=a.modelle.map(m=>`<tr><td>${esc(m.name)}${m.aktiv?` <span class="pill ok">${esc(t('läuft','running'))}</span>`:''}${m.gewerblich?'':` <span class="pill warn">${esc(t('nur privat','private use only'))}</span>`}${m.eigen?` <span class="pill">${esc(t('eigenes','own'))}</span>`:''}</td>`+
    `<td class="n">${m.gemessen?'':'~'}${esc(mdGib(m.aktiv&&m.gib!=null?m.gib:m.need_gib))}</td><td>${esc(m.betrieb==='resident'?t('immer geladen','always loaded'):t('bei Bedarf','on demand'))}</td>`+
    `<td>${esc(m.lizenz)}</td><td>${esc(mdMess(m))}</td>${w.an?`<td>${mdTun(m,a,w)}</td>`:''}</tr>`).join('');
  return `<div class="card"><h3>${esc(a.name)}</h3><div class="vb-tw"><table class="vb-tab"><thead><tr><th>${esc(t('Modell','Model'))}</th><th class="n">${esc(t('Speicher','Memory'))}</th>`+
    `<th>${esc(t('Betrieb','Runs'))}</th><th>${esc(t('Lizenz','Licence'))}</th><th>${esc(t('Messung','Measurement'))}</th>${w.an?'<th></th>':''}</tr></thead><tbody>${rows}</tbody></table></div>${mdAlt(a,w,d)}</div>`}
function mdWechsel(w){if(!w.an)return `<div class="mut vb-note">${esc(t('Wechseln: Funktionen → Modelle wechseln einschalten.','Switching: switch on Features → Switch models.'))}</div>`;
  return (w.laeuft?`<div class="card"><b>${esc(t('Ein Modellwechsel läuft.','A model switch is running.'))}</b> <span class="mut">${esc(t('Fortschritt unter Zustand → Logs (Modellwechsel); die Seite zeigt das Ergebnis, sobald er fertig ist.','Progress under Status → Logs (model switch); the page shows the result once it is done.'))}</span></div>`:'')+
    (w.misst?`<div class="card"><b>${esc(t('Eine Messung läuft.','A measurement is running.'))}</b> <span class="mut">${esc(t('Das Sprachmodell pausiert so lange (pro Modell etwa 10 bis 25 Minuten); die Zahlen erscheinen hier, sobald sie fertig ist.','The language model pauses meanwhile (about 10 to 25 minutes per model); the numbers show here once it is done.'))}</span></div>`:'')}
async function mdPost(url,body,frage,method='POST'){if(!confirm(frage))return;const msg=$('mdmsg');msg.textContent='';
  try{await api(url+(L==='en'?'?lang=en':''),method==='POST'?{method,headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}:{method});loadModelle()}catch(e){msg.textContent=e.message}}
function mdEigen(w){if(!w.an||!w.eigene||w.laeuft)return '';
  return `<div class="card"><h3>${esc(t('Eigenes Modell hinzufügen','Add an own model'))}</h3><div class="row">`+
    `<select id="mdeart" aria-label="${esc(t('Art','Kind'))}"><option value="llm">${esc(t('Sprachmodell','Language model'))}</option><option value="sehen">${esc(t('Bildverständnis','Image understanding'))}</option></select>`+
    ` <input id="mderepo" maxlength="200" placeholder="besitzer/modell" aria-label="${esc(t('Name bei Hugging Face','Name on Hugging Face'))}" autocomplete="off" spellcheck="false">`+
    ` <button type="button" class="b sm" id="mdepr">${esc(t('Prüfen','Check'))}</button></div><div id="mdevor"></div>`+
    `<div class="mut vb-note">${esc(t('Nur offene Modelle mit safetensors, ohne eigenen Code, mit einer Bauart, die die Engine kennt. Geladen wird erst beim Wechseln, gepinnt auf den geprüften Stand.','Only open models with safetensors, without code of their own, with an architecture the engine knows. It downloads only when switching, pinned to the checked state.'))}</div></div>`}
function mdVorschlag(v){return `<div class="vb-tw"><table class="vb-tab"><tbody>`+
  [[t('Name','Name'),v.name[L==='en'?'en':'de']],[t('Stand','Commit'),v.revision.slice(0,12)],[t('Platte','Disk'),v.platte_gb+' GB'],[t('Speicher','Memory'),'~'+mdGib(v.need_gib)],
   [t('Lizenz','Licence'),v.lizenz+(v.gewerblich?'':t(' (nur privat)',' (private use only)'))],[t('Werkzeuge','Tools'),v.werkzeuge?t('ja','yes'):t('nein','no')],[t('Sieht Bilder','Sees pictures'),v.kann_sehen?t('ja','yes'):t('nein','no')]]
    .map(([k,x])=>`<tr><td>${esc(k)}</td><td>${esc(String(x))}</td></tr>`).join('')+
  `</tbody></table></div><div class="row"><button type="button" class="b sm" id="mdedazu">${esc(t('Hinzufügen','Add'))}</button></div>`}
async function mdPruefen(){const msg=$('mdmsg'),vor=$('mdevor'),art=$('mdeart').value,repo=$('mderepo').value.trim();msg.textContent='';vor.innerHTML='';if(!repo)return;
  let v;try{v=(await (await api('/api/admin/modelle/eigen/pruefen',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({art,repo})})).json()).vorschlag}catch(e){msg.textContent=e.message;return}
  vor.innerHTML=mdVorschlag(v);
  $('mdedazu').onclick=()=>mdPost('/api/admin/modelle/eigen',{art,repo,revision:v.revision},t('„'+repo+'“ zur Liste hinzufügen? Geladen wird erst beim Wechseln.','Add "'+repo+'" to the list? It downloads only when switching.'))}
function mdKnoepfe(d){const main=$('mdmain');
  main.querySelectorAll('[data-mdw]').forEach(b=>b.onclick=()=>{const m=d.arten.flatMap(y=>y.modelle).find(y=>y.id===b.dataset.mdid);
    mdPost('/api/admin/modelle/wechseln',{art:b.dataset.mdw,id:b.dataset.mdid},t('Zu „'+(m?m.name:b.dataset.mdid)+'“ wechseln? Der Spark lädt und prüft das Modell; das alte bleibt '+d.wechsel.tage+' Tage zum Zurückholen.','Switch to "'+(m?m.name:b.dataset.mdid)+'"? The Spark loads and checks the model; the old one stays '+d.wechsel.tage+' days to bring back.'))});
  main.querySelectorAll('[data-mdm]').forEach(b=>b.onclick=()=>{const m=d.arten.flatMap(y=>y.modelle).find(y=>y.id===b.dataset.mdm);
    mdPost('/api/admin/modelle/messen',{id:b.dataset.mdm},t('„'+(m?m.name:b.dataset.mdm)+'“ messen? Der Spark lädt es falls nötig, das Sprachmodell pausiert für etwa 10 bis 25 Minuten und startet danach wieder. Gewechselt wird nichts.','Measure "'+(m?m.name:b.dataset.mdm)+'"? The Spark downloads it if needed, the language model pauses for about 10 to 25 minutes and starts again afterwards. Nothing is switched.'))});
  main.querySelectorAll('[data-mdz]').forEach(b=>b.onclick=()=>mdPost('/api/admin/modelle/zurueck',{art:b.dataset.mdz},t('Das vorige Modell zurückholen?','Bring back the previous model?')));
  main.querySelectorAll('[data-mde]').forEach(b=>b.onclick=()=>mdPost('/api/admin/modelle/eigen/'+encodeURIComponent(b.dataset.mde),null,t('Dieses eigene Modell aus der Liste und von der Platte löschen?','Delete this own model from the list and from the disk?'),'DELETE'));
  if($('mdepr'))$('mdepr').onclick=mdPruefen}
async function loadModelle(){const main=$('mdmain'),msg=$('mdmsg');if(!main)return;msg.textContent='';
  let d;try{d=await (await api('/api/admin/modelle'+(L==='en'?'?lang=en':''))).json()}catch(e){msg.textContent=e.message;return}
  const w=d.wechsel||{};
  main.innerHTML=mdWechsel(w)+`<div class="vb-two">${mdBudget(d.budget)}${d.arten.map(a=>mdArt(a,w,d)).join('')}${mdEigen(w)}</div>`+
    `<div class="mut vb-note">${esc(d.messung_zeit?t('Letzte Messung: ','Last measurement: ')+new Date(d.messung_zeit*1000).toLocaleString(L==='en'?'en':'de'):t('Noch keine Messung. „Messen“ beim Modell (mit Funktionen → Modelle wechseln) oder auf dem Spark: sudo speech-spark modelle messen','No measurement yet. „Measure“ at the model (with Features → Switch models) or on the Spark: sudo speech-spark modelle messen'))}`+
    ` · ${esc(t('„~“ heißt geschätzt.','“~” means estimated.'))}</div>`;
  mdKnoepfe(d);if(typeof labelTables==='function')labelTables();
  clearTimeout(window.mdTick);if(w.laeuft||w.misst)window.mdTick=setTimeout(()=>{if($('mdmain')&&$('mdmain').offsetParent)loadModelle()},15000)}
