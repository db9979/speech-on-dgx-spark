// ---------------------------------------------------------------- Zustand → Modelle (admin)
// The model catalog (app/modelle.json) per kind, the models this configuration runs, the memory budget and the last
// measurement (sudo speech-spark modelle messen). Stage E4, with Funktionen → Modelle wechseln on: „Wechseln“ per
// model and „Zurückholen“ per kind for 7 days; the root unit speech-spark-wechsel does the work, the panel only asks.
const MD_NEIN={revision:['noch nicht gemessen','not measured yet'],aus:['erst umziehen','move first'],budget:['zu knapp','too tight'],engine:['nicht wählbar','not selectable']};
const MD_REGEL={alle:['Alle Modelle passen gleichzeitig in den Speicher.','All models fit into memory at the same time.'],
  ein_platz:['Knapp: Modelle bei Bedarf (Bilder malen, Bildverständnis, Nachsortieren) laden nacheinander, nie gleichzeitig.','Tight: models on demand (painting pictures, image understanding, re-ranking) load one after the other, never at once.'],
  zu_knapp:['Zu knapp: neben den festen Modellen bleibt weniger als die Reserve. Ein kleineres Modell wählen oder qwen38 im 1M-Modus abschalten.','Too tight: beside the fixed models less than the reserve is left. Choose a smaller model or switch qwen38 out of its 1M mode.']};
function mdGib(v){return v==null?'–':(Math.round(v*10)/10).toLocaleString(L==='en'?'en':'de')+' GiB'}
function mdMess(m){const x=m.messung||{};if(!Object.keys(x).length)return '';if(x.ok===false)return t('abgebrochen','broke off');
  const ja=v=>v?t('ok','ok'):t('falsch','wrong');
  return [x.tok_s!=null?x.tok_s+' tok/s':'',x.erste_s!=null?t('erste ','first ')+x.erste_s+' s':'',x.mtp_annahme!=null?'MTP '+Math.round(x.mtp_annahme*100)+' %':'',
    'werkzeug' in x?t('Werkzeug ','Tool ')+ja(x.werkzeug):'','bild_text' in x?t('Text ','Text ')+ja(x.bild_text):'','bild_szene' in x?t('Szene ','Scene ')+ja(x.bild_szene):''].filter(Boolean).join(' · ')}
function mdBudget(b){const pct=v=>Math.max(0,Math.min(100,Math.round(100*v/(b.gesamt||1))));
  return `<div class="card"><h3>${esc(t('Speicher-Budget','Memory budget'))}</h3><div class="vb-hb vb-qbar"><i class="${b.regel==='alle'?'':'full'}" style="width:${pct(b.fest+b.system+b.reserve)}%"></i></div>`+
    `<div class="vb-tw"><table class="vb-tab"><tbody>`+
    [[t('Speicher gesamt','Memory in total'),b.gesamt],[t('Feste Modelle','Fixed models'),b.fest],[t('System','System'),b.system],[t('Reserve','Reserve'),b.reserve],
     [t('Modelle bei Bedarf','Models on demand'),b.bedarf],[t('Frei für Modelle bei Bedarf','Free for models on demand'),b.frei]]
      .map(([k,v])=>`<tr><td>${esc(k)}</td><td class="n">${esc(mdGib(v))}</td></tr>`).join('')+
    `</tbody></table></div><div class="mut vb-note">${esc(t(...(MD_REGEL[b.regel]||['',''])))}</div></div>`}
function mdTun(m,a,w){if(!w.an||m.aktiv)return '';if(m.waehlbar)return w.laeuft?'':`<button type="button" class="b sm" data-mdw="${esc(a.art)}" data-mdid="${esc(m.id)}">${esc(t('Wechseln','Switch'))}</button>`;
  return MD_NEIN[m.nein]?`<span class="mut">${esc(t(...MD_NEIN[m.nein]))}</span>`:''}
function mdAlt(a,w,d){const x=(w.alte||{})[a.art];if(!w.an||!x)return '';
  const n=(d.arten.flatMap(y=>y.modelle).find(y=>y.id===x.id)||{}).name||x.id;
  return `<div class="row vb-note"><span class="mut">${esc(t('Vorher: ','Before: ')+n+(x.tage_frei?t(' · noch '+x.tage_frei+' Tage zurückholbar',' · can be brought back for '+x.tage_frei+' more days'):t(' · älter als '+w.tage+' Tage',' · older than '+w.tage+' days')))}</span>`+
    (x.tage_frei&&!w.laeuft?` <button type="button" class="b sm" data-mdz="${esc(a.art)}">${esc(t('Zurückholen','Bring back'))}</button>`:'')+`</div>`}
function mdArt(a,w,d){if(!a.modelle.length)return '';
  const rows=a.modelle.map(m=>`<tr><td>${esc(m.name)}${m.aktiv?` <span class="pill ok">${esc(t('läuft','running'))}</span>`:''}${m.gewerblich?'':` <span class="pill warn">${esc(t('nur privat','private use only'))}</span>`}</td>`+
    `<td class="n">${m.gemessen?'':'~'}${esc(mdGib(m.aktiv&&m.gib!=null?m.gib:m.need_gib))}</td><td>${esc(m.betrieb==='resident'?t('immer geladen','always loaded'):t('bei Bedarf','on demand'))}</td>`+
    `<td>${esc(m.lizenz)}</td><td>${esc(mdMess(m))}</td>${w.an?`<td>${mdTun(m,a,w)}</td>`:''}</tr>`).join('');
  return `<div class="card"><h3>${esc(a.name)}</h3><div class="vb-tw"><table class="vb-tab"><thead><tr><th>${esc(t('Modell','Model'))}</th><th class="n">${esc(t('Speicher','Memory'))}</th>`+
    `<th>${esc(t('Betrieb','Runs'))}</th><th>${esc(t('Lizenz','Licence'))}</th><th>${esc(t('Messung','Measurement'))}</th>${w.an?'<th></th>':''}</tr></thead><tbody>${rows}</tbody></table></div>${mdAlt(a,w,d)}</div>`}
function mdWechsel(w){if(!w.an)return `<div class="mut vb-note">${esc(t('Wechseln: Funktionen → Modelle wechseln einschalten.','Switching: switch on Features → Switch models.'))}</div>`;
  return w.laeuft?`<div class="card"><b>${esc(t('Ein Modellwechsel läuft.','A model switch is running.'))}</b> <span class="mut">${esc(t('Fortschritt unter Zustand → Logs (Modellwechsel); die Seite zeigt das Ergebnis, sobald er fertig ist.','Progress under Status → Logs (model switch); the page shows the result once it is done.'))}</span></div>`:''}
async function mdPost(url,body,frage){if(!confirm(frage))return;const msg=$('mdmsg');msg.textContent='';
  try{await api(url+(L==='en'?'?lang=en':''),{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});loadModelle()}catch(e){msg.textContent=e.message}}
function mdKnoepfe(d){const main=$('mdmain');
  main.querySelectorAll('[data-mdw]').forEach(b=>b.onclick=()=>{const m=d.arten.flatMap(y=>y.modelle).find(y=>y.id===b.dataset.mdid);
    mdPost('/api/admin/modelle/wechseln',{art:b.dataset.mdw,id:b.dataset.mdid},t('Zu „'+(m?m.name:b.dataset.mdid)+'“ wechseln? Der Spark lädt und prüft das Modell; das alte bleibt '+d.wechsel.tage+' Tage zum Zurückholen.','Switch to "'+(m?m.name:b.dataset.mdid)+'"? The Spark loads and checks the model; the old one stays '+d.wechsel.tage+' days to bring back.'))});
  main.querySelectorAll('[data-mdz]').forEach(b=>b.onclick=()=>mdPost('/api/admin/modelle/zurueck',{art:b.dataset.mdz},t('Das vorige Modell zurückholen?','Bring back the previous model?')))}
async function loadModelle(){const main=$('mdmain'),msg=$('mdmsg');if(!main)return;msg.textContent='';
  let d;try{d=await (await api('/api/admin/modelle'+(L==='en'?'?lang=en':''))).json()}catch(e){msg.textContent=e.message;return}
  const w=d.wechsel||{};
  main.innerHTML=mdWechsel(w)+`<div class="vb-two">${mdBudget(d.budget)}${d.arten.map(a=>mdArt(a,w,d)).join('')}</div>`+
    `<div class="mut vb-note">${esc(d.messung_zeit?t('Letzte Messung: ','Last measurement: ')+new Date(d.messung_zeit*1000).toLocaleString(L==='en'?'en':'de'):t('Noch keine Messung. Auf dem Spark: sudo speech-spark modelle messen','No measurement yet. On the Spark: sudo speech-spark modelle messen'))}`+
    ` · ${esc(t('„~“ heißt geschätzt.','“~” means estimated.'))}</div>`;
  mdKnoepfe(d);if(typeof labelTables==='function')labelTables();
  clearTimeout(window.mdTick);if(w.laeuft)window.mdTick=setTimeout(()=>{if($('mdmain')&&$('mdmain').offsetParent)loadModelle()},15000)}
