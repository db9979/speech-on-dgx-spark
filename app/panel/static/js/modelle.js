// ---------------------------------------------------------------- Zustand → Modelle (admin, only to look at)
// The model catalog (app/modelle.json) per kind, the models this configuration runs, the memory budget and the last
// measurement (sudo speech-spark modelle messen). Nothing here switches a model.
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
function mdArt(a){if(!a.modelle.length)return '';
  const rows=a.modelle.map(m=>`<tr><td>${esc(m.name)}${m.aktiv?` <span class="pill ok">${esc(t('läuft','running'))}</span>`:''}${m.gewerblich?'':` <span class="pill warn">${esc(t('nur privat','private use only'))}</span>`}</td>`+
    `<td class="n">${m.gemessen?'':'~'}${esc(mdGib(m.aktiv&&m.gib!=null?m.gib:m.need_gib))}</td><td>${esc(m.betrieb==='resident'?t('immer geladen','always loaded'):t('bei Bedarf','on demand'))}</td>`+
    `<td>${esc(m.lizenz)}</td><td>${esc(mdMess(m))}</td></tr>`).join('');
  return `<div class="card"><h3>${esc(a.name)}</h3><div class="vb-tw"><table class="vb-tab"><thead><tr><th>${esc(t('Modell','Model'))}</th><th class="n">${esc(t('Speicher','Memory'))}</th>`+
    `<th>${esc(t('Betrieb','Runs'))}</th><th>${esc(t('Lizenz','Licence'))}</th><th>${esc(t('Messung','Measurement'))}</th></tr></thead><tbody>${rows}</tbody></table></div></div>`}
async function loadModelle(){const main=$('mdmain'),msg=$('mdmsg');if(!main)return;msg.textContent='';
  let d;try{d=await (await api('/api/admin/modelle'+(L==='en'?'?lang=en':''))).json()}catch(e){msg.textContent=e.message;return}
  main.innerHTML=`<div class="vb-two">${mdBudget(d.budget)}${d.arten.map(mdArt).join('')}</div>`+
    `<div class="mut vb-note">${esc(d.messung_zeit?t('Letzte Messung: ','Last measurement: ')+new Date(d.messung_zeit*1000).toLocaleString(L==='en'?'en':'de'):t('Noch keine Messung. Auf dem Spark: sudo speech-spark modelle messen','No measurement yet. On the Spark: sudo speech-spark modelle messen'))}`+
    ` · ${esc(t('„~“ heißt geschätzt.','“~” means estimated.'))}</div>`;
  if(typeof labelTables==='function')labelTables()}
