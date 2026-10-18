// ---------------------------------------------------------------- Zustand → Modelle (admin)
// The model catalog (app/modelle.json) per kind, the models this configuration runs, the memory budget and the last
// measurement. Since Dominik's „1a 2a“ (2026-10-17) the page opens with a memory bar and one tile per kind („Läuft
// jetzt“); with Funktionen → Modelle wechseln on, „Wechseln“ on a tile shows that kind's models as cards: „Wechseln“,
// or „Ausprobieren“ (measure first, the page then asks with the numbers), and for the language model and image
// understanding, with Eigene Modelle on, „Suchen“ at Hugging Face („3a“: the panel checks the fixed rules, „Hinzufügen“
// checks the pinned commit again). Measurements, „Lange Gespräche“ and „Zurückholen“ are under „Mehr“. The root units
// do the work, the panel only asks.
const MD_NEIN={revision:['noch nicht gemessen','not measured yet'],schon:['schon in der Liste','already in the list'],zugang:['privat oder mit Freigabe','private or gated'],code:['braucht eigenen Code','needs code of its own'],format:['keine safetensors','no safetensors'],architektur:['Bauart unbekannt','unknown architecture'],aus:['erst umziehen','move first'],budget:['zu knapp','too tight'],engine:['nicht wählbar','not selectable'],ungeprueft:['erst messen','measure first'],docker:['Docker: vorerst nur messen','Docker: measuring only for now']};
const MD_REGEL={alle:['Alle Modelle passen gleichzeitig in den Speicher.','All models fit into memory at the same time.'],
  ein_platz:['Knapp: Modelle bei Bedarf (Bilder malen, Bildverständnis, Nachsortieren) laden nacheinander, nie gleichzeitig.','Tight: models on demand (painting pictures, image understanding, re-ranking) load one after the other, never at once.'],
  zu_knapp:['Zu knapp: neben den festen Modellen bleibt weniger als die Reserve. Ein kleineres Modell wählen oder qwen38 im 1M-Modus abschalten.','Too tight: beside the fixed models less than the reserve is left. Choose a smaller model or switch qwen38 out of its 1M mode.']};
function mdGib(v){return v==null?'–':(Math.round(v*10)/10).toLocaleString(L==='en'?'en':'de')+' GiB'}
function mdMess(m){const x=m.messung||{};if(!Object.keys(x).length)return '';if(x.ok===false)return t('abgebrochen','broke off');
  const ja=v=>v?t('ok','ok'):t('falsch','wrong');
  return [x.tok_s!=null?x.tok_s+' tok/s':'',x.erste_s!=null?t('erste ','first ')+x.erste_s+' s':'',x.mtp_annahme!=null?'MTP '+Math.round(x.mtp_annahme*100)+' %':'',x.erste_warm_s!=null?t('warm ','warm ')+x.erste_warm_s+' s':'',x.zwischenspeicher!=null?t('Zwischenspeicher ','Prefix cache ')+Math.round(x.zwischenspeicher*100)+' %':'',
    ...[2,4].map(n=>x['par'+n+'_tok_s']!=null?n+t(' gleichzeitig ',' at once ')+x['par'+n+'_tok_s']+t(' tok/s je Antwort',' tok/s per answer'):x['par'+n+'_fehler']?n+t(' gleichzeitig: Fehler',' at once: error'):''),
    x.lang_tokens!=null?Math.round(x.lang_tokens/1000)+t('K Tokens: erste ','K tokens: first ')+x.lang_erste_s+' s':x.lang_fehler?t('lange Frage: Fehler','long question: error'):'',
    x.platz_64k!=null?t('Platz für ','Room for ')+x.platz_64k+t(' × 64K',' × 64K'):'',
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
function mdTun(m,a,w){return w.an?mdMessKnopf(m,w):''}
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
// „Sprachmodell wechselt“ (Dominik 2026-10-18 „1a“): the six fixed steps of a switch or restart with their times, the
// engine's phase while it starts and the minutes still expected (llmstart; fixed words and numbers only)
function mdStart(x){if(!x)return '';const fertig=x.ende;     // the texts come from the panel (llmstart.zeigen), the same as in the apps
  const cls={ok:'mdst-ok',jetzt:'mdst-jetzt',offen:'mdst-offen'};
  const zeilen=x.zeilen.map(z=>`<li class="${cls[z.zustand]||'mdst-offen'}"><span>${esc(z.name)}</span><span class="mut">${esc(z.zeit)}</span></li>`).join('');
  const rest=x.rest?`<div class="mut">${esc(x.rest)}</div>`:'';
  const hin=!fertig?`<div class="mut">${esc(t('Solange antwortet das Sprachmodell nicht; der Chat sagt das mit der erwarteten Zeit. Einzelheiten: Zustand → Logs (Modellwechsel).','Meanwhile the language model does not answer; the chat says so with the expected time. Details: Status → Logs (model switch).'))}</div>`:'';
  return `<div class="card mdstart" id="mdstart"><b>${esc(x.kopf)}</b><ol class="mdschritte">${zeilen}</ol>${rest}${hin}</div>`}
function mdWechsel(w){if(!w.an)return mdStart(w.start)+`<div class="mut vb-note">${esc(t('Wechseln: Funktionen → Modelle wechseln einschalten.','Switching: switch on Features → Switch models.'))}</div>`;
  if(w.start)return mdStart(w.start)+(w.misst?mdMisst(w):'');
  return (w.laeuft?`<div class="card"><b>${esc(t('Ein Modellwechsel läuft.','A model switch is running.'))}</b> <span class="mut">${esc(t('Fortschritt unter Zustand → Logs (Modellwechsel); die Seite zeigt das Ergebnis, sobald er fertig ist.','Progress under Status → Logs (model switch); the page shows the result once it is done.'))}</span></div>`:'')+
    (w.misst?mdMisst(w):'')}
function mdMisst(w){return `<div class="card"><b>${esc(t('Eine Messung läuft.','A measurement is running.'))}</b> <span class="mut">${esc(t('Das Sprachmodell pausiert so lange (pro Modell etwa 10 bis 25 Minuten); die Zahlen erscheinen hier, sobald sie fertig ist.','The language model pauses meanwhile (about 10 to 25 minutes per model); the numbers show here once it is done.'))}</span>`+
      ((w.stand||[]).length?`<pre class="mdstand">${esc(w.stand.join('\n'))}</pre>`:`<div class="mut">${esc(t('Startet gerade …','Starting …'))}</div>`)+`</div>`}
// „Lange Gespräche“: the own language model's context store as fixed choices (modelle.PLATZ); the panel checks the
// budget, root restarts the model with it
function mdPlatz(w){const p=w.platz;if(!p||w.laeuft||w.misst)return '';
  const grund={budget:t('Speicher zu knapp','not enough memory'),kontext:t('kann dieses Modell nicht','this model cannot')};
  const zeilen=p.wahl.map(x=>`<label class="row"><input type="radio" name="mdplatz" value="${esc(x.id)}"${x.id===p.jetzt?' checked':''}${x.nein&&x.nein!=='schon'?' disabled':''}> ${esc(x.name)}`+
    `${x.plus_gib?' <span class="mut">(+'+esc(mdGib(x.plus_gib))+')</span>':''}${x.id===p.jetzt?' <span class="mut">· '+esc(t('jetzt','now'))+'</span>':''}${grund[x.nein]?' <span class="mut">· '+esc(grund[x.nein])+'</span>':''}</label>`).join('');
  return `<div class="card"><h3>${esc(t('Lange Gespräche','Long conversations'))}</h3>${zeilen}`+
    `<div class="row"><button type="button" class="b sm" id="mdplatzok">${esc(t('Übernehmen','Apply'))}</button></div>`+
    `<div class="mut vb-note">${esc(t('Alle Gespräche teilen sich einen Gesprächsspeicher. Mehr Platz kostet Speicher, der Bildern, Musik und dem Sehen-Modell fehlt. Das Sprachmodell startet dafür neu.','All conversations share one context store. More room costs memory that pictures, music and the vision model then lack. The language model restarts for it.'))}</div></div>`}
async function mdPost(url,body,frage,method='POST'){if(!confirm(frage))return;const msg=$('mdmsg');msg.textContent='';
  // the answer is the page itself (after „Messen“ already showing the measurement that starts in a moment)
  try{const r=await api(url+(L==='en'?'?lang=en':''),method==='POST'?{method,headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}:{method});
    let d=null;try{d=await r.json()}catch(_){}loadModelle(d&&d.arten?d:null)}catch(e){msg.textContent=e.message}}
// „Läuft jetzt“: the memory bar and one tile per kind with the model it runs
let MD_OFFEN='',MD_MEHR=false;const MD_TREFFER={};
// one colored piece per running model (resident first, then system and reserve, then the models on demand striped)
function mdBalken(b){const teile=b.teile||[],belegt=b.fest+b.system+b.reserve,skala=Math.max(b.gesamt||0,belegt+(b.bedarf||0))||1;
  // pictures and music share one place (never both loaded): one striped piece of the bigger one in both colors
  const platz=teile.filter(x=>x.betrieb!=='resident'&&(b.ein_platz||[]).includes(x.art)),geteilt=platz.length>1;
  const seg=(gib,cls,name)=>gib>0?`<i class="${cls}" style="width:${(100*gib/skala).toFixed(2)}%" title="${esc(name+' · '+mdGib(gib))}"></i>`:'';
  const teil=x=>seg(x.gib,'mdf-'+x.art+(x.betrieb==='resident'?'':' mdbb'),x.name);
  const zeichen=(cls,text)=>`<span><i class="${cls}"></i>${esc(text)}</span>`;
  return `<div class="card mdbalken"><div class="row mdzeile"><b>${esc(t('Speicher','Memory'))}</b><span class="mut">${esc(mdGib(belegt)+t(' von ',' of ')+mdGib(b.gesamt)+t(' fest belegt',' taken'))}</span></div>`+
    `<div class="mdbar ${b.regel==='zu_knapp'?'full':b.regel==='ein_platz'?'warn':''}">${teile.filter(x=>x.betrieb==='resident').map(teil).join('')}`+
    seg(b.system,'mdf-sys',t('System','System'))+seg(b.reserve,'mdf-res',t('Reserve','Reserve'))+teile.filter(x=>x.betrieb!=='resident'&&!(geteilt&&platz.includes(x))).map(teil).join('')+
    (geteilt?seg(Math.max(...platz.map(x=>x.gib)),'mdf-platz mdbb',platz.map(x=>x.name).join(t(' oder ',' or '))):'')+`</div>`+
    `<div class="mut mdlegende">${zeichen('mdf-sys',t('System','System'))}${zeichen('mdf-res',t('Reserve','Reserve'))}${zeichen('mdf-llm mdbb',t('gestreift: bei Bedarf','striped: on demand'))}${geteilt?zeichen('mdf-platz mdbb',t('Bilder oder Musik: ein Platz, nie beide','Pictures or music: one place, never both')):''}</div>`+
    `<div class="mut vb-note">${esc(t('Frei für Modelle bei Bedarf: ','Free for models on demand: ')+mdGib(b.frei))} · ${esc(t(...(MD_REGEL[b.regel]||['',''])))}</div></div>`}
function mdKurz(m){const x=m.messung||{};return [x.tok_s!=null?x.tok_s+' tok/s':'',mdGib(m.aktiv&&m.gib!=null?m.gib:m.need_gib),m.betrieb==='resident'?'':t('bei Bedarf','on demand')].filter(Boolean).join(' · ')}
function mdKachel(a,w){const m=a.modelle.find(x=>x.aktiv);
  const wahl=w.an&&!w.laeuft&&!w.misst&&(a.modelle.some(x=>!x.aktiv&&(x.waehlbar||x.messbar))||(w.eigene&&['llm','sehen'].includes(a.art)));
  return `<div class="mdkachel${m?' mdf-'+a.art+(m.betrieb==='resident'?'':' mdbb'):''}${MD_OFFEN===a.art?' offen':''}"><span class="mut">${esc(a.name)}</span><b>${esc(m?m.name:t('keins','none'))}</b>`+
    `<span class="mut mdzahl">${esc(m?mdKurz(m):'')}</span>`+
    (wahl?`<span><button type="button" class="b sm" data-mdo="${esc(a.art)}" aria-expanded="${MD_OFFEN===a.art}">${esc(MD_OFFEN===a.art?t('Schließen','Close'):t('Wechseln','Switch'))}</button></span>`:'')+`</div>`}
// „Wechseln“: the kind's models as cards
function mdKarte(m,a,w){const x=m.messung||{},probe=['revision','ungeprueft'].includes(m.nein)&&m.messbar;
  const tun=m.aktiv?`<span class="pill ok">${esc(t('läuft','running'))}</span>`:m.waehlbar?`<button type="button" class="b sm" data-mdw="${esc(a.art)}" data-mdid="${esc(m.id)}">${esc(t('Wechseln','Switch'))}</button>`:
    probe?`<button type="button" class="b sm" data-mdp="${esc(m.id)}">${esc(t('Ausprobieren','Try'))}</button>`:`<span class="mut">${esc(t(...(MD_NEIN[m.nein]||['nicht wählbar','not selectable'])))}</span>`;
  const weg=w.eigene&&m.eigen&&!m.aktiv?` <button type="button" class="b sm danger" data-mde="${esc(m.id)}">${esc(t('Löschen','Delete'))}</button>`:'';
  const zeile=[x.ok===false?t('Messung abgebrochen','measurement broke off'):x.tok_s!=null?x.tok_s+t(' tok/s gemessen',' tok/s measured'):probe?t('noch nicht gemessen','not measured yet'):'',
    (m.gemessen?'':'~')+mdGib(m.aktiv&&m.gib!=null?m.gib:m.need_gib),m.betrieb==='resident'?t('immer geladen','always loaded'):t('bei Bedarf','on demand'),m.lizenz].filter(Boolean).join(' · ');
  return `<div class="mdkarte${!m.aktiv&&!m.waehlbar&&!probe?' aus':''}"><div class="mdkopf"><b>${esc(m.name)}</b>${m.gewerblich?'':` <span class="pill warn">${esc(t('nur privat','private use only'))}</span>`}${m.eigen?` <span class="pill">${esc(t('eigenes','own'))}</span>`:''}</div>`+
    `<div class="mdtun">${tun}${weg}</div><div class="mut mdzahl">${esc(zeile)}</div></div>`}
function mdTreffer(art){const l=MD_TREFFER[art];if(!l)return '';if(!l.length)return `<div class="mut vb-note">${esc(t('Nichts gefunden.','Nothing found.'))}</div>`;
  return l.map(h=>`<div class="mdkarte${h.nein?' aus':''}"><div class="mdkopf"><b>${esc(h.repo)}</b>${h.gewerblich?'':` <span class="pill warn">${esc(t('nur privat','private use only'))}</span>`}</div>`+
    `<div class="mdtun">${h.nein?`<span class="mut">${esc(t(...(MD_NEIN[h.nein]||['geht nicht','not possible'])))}</span>`:`<button type="button" class="b sm" data-mdh="${esc(h.repo)}">${esc(t('Hinzufügen','Add'))}</button>`}</div>`+
    `<div class="mut mdzahl">${esc([h.gb!=null?h.gb+' GB':'',h.need_gib!=null?'~'+mdGib(h.need_gib):'',h.lizenz,h.downloads.toLocaleString(L==='en'?'en':'de')+t(' Downloads',' downloads')].filter(Boolean).join(' · '))}</div></div>`).join('')}
function mdWahl(d,w){const a=d.arten.find(x=>x.art===MD_OFFEN);if(!a||!w.an||w.laeuft||w.misst)return '';
  const such=w.eigene&&['llm','sehen'].includes(a.art)?`<h4>${esc(t('Bei Hugging Face suchen','Search Hugging Face'))}</h4><div class="row">`+
    `<input id="mdq" maxlength="60" placeholder="${esc(t('z. B. qwen coder','e.g. qwen coder'))}" aria-label="${esc(t('Suchwort','Search words'))}" autocomplete="off" spellcheck="false">`+
    ` <button type="button" class="b sm" id="mdqs">${esc(t('Suchen','Search'))}</button></div><div class="mdkarten">${mdTreffer(a.art)}</div>`+
    `<div class="mut vb-note">${esc(t('Nur offene Modelle mit safetensors, ohne eigenen Code, mit einer Bauart, die die Engine kennt, und die in den Speicher passen. Geladen wird erst beim Ausprobieren, gepinnt auf den geprüften Stand.','Only open models with safetensors, without code of their own, with an architecture the engine knows, that fit into memory. It downloads only when trying it, pinned to the checked state.'))}</div>`:'';
  return `<div class="card mdwahl"><h3>${esc(a.name)}: ${esc(t('Modell wählen','choose a model'))}</h3><div class="mdkarten">${a.modelle.map(m=>mdKarte(m,a,w)).join('')}</div>`+
    `<div class="mut vb-note">${esc(t('„Ausprobieren“ lädt das Modell falls nötig und misst es (das Sprachmodell pausiert so lange); danach fragt die Seite mit den Zahlen, ob gewechselt wird. Das alte Modell bleibt '+w.tage+' Tage zum Zurückholen.','"Try" downloads the model if needed and measures it (the language model pauses meanwhile); afterwards the page asks with the numbers whether to switch. The old model stays '+w.tage+' days to bring back.'))}</div>${such}</div>`}
// after „Ausprobieren“: the question with the numbers
function mdProbe(w){const p=w.probe;if(!p||w.laeuft)return '';
  if(!p.fertig)return `<div class="card"><b>${esc(t('„'+p.name+'“ wird ausprobiert.','Trying "'+p.name+'".'))}</b> <span class="mut">${esc(t('Erst laden und messen, dann fragt die Seite hier.','First download and measure, then the page asks here.'))}</span></div>`;
  const weg=`<button type="button" class="b sm" id="mdpv">${esc(t('Verwerfen','Discard'))}</button>`;
  if(!p.ok)return `<div class="card"><b>${esc(t('„'+p.name+'“: die Messung ist abgebrochen.','"'+p.name+'": the measurement broke off.'))}</b> <span class="mut">${esc(t('So läuft es auf dem Spark nicht; das jetzige Modell bleibt. Was passiert ist: Zustand → Logs (Messen).','It does not run on the Spark like this; the current model stays. What happened: Status → Logs (measuring).'))}</span><div class="row">${weg}</div></div>`;
  const vgl=p.tok_s!=null?p.tok_s+' tok/s'+(p.jetzt_tok_s!=null?t(' (jetzt „'+p.jetzt_name+'“: '+p.jetzt_tok_s+' tok/s)',' (now "'+p.jetzt_name+'": '+p.jetzt_tok_s+' tok/s)'):''):'';
  return `<div class="card"><b>${esc(t('„'+p.name+'“ ist gemessen: ','"'+p.name+'" is measured: ')+vgl)}</b> <span class="mut">${esc(p.waehlbar?t('Wechseln?','Switch?'):t('Wechseln geht so nicht (Speicher oder Regel), siehe Karte.','Switching is not possible like this (memory or rule), see the card.'))}</span>`+
    `<div class="row">${p.waehlbar?`<button type="button" class="b sm" data-mdw="${esc(p.art)}" data-mdid="${esc(p.id)}">${esc(t('Wechseln','Switch'))}</button> `:''}${weg}</div></div>`}
async function mdSuchen(){const art=MD_OFFEN,q=($('mdq')||{}).value||'',msg=$('mdmsg');msg.textContent='';if(!q.trim())return;
  try{MD_TREFFER[art]=(await (await api('/api/admin/modelle/eigen/suche',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({art,q:q.trim()})})).json()).treffer||[]}catch(e){msg.textContent=e.message;return}
  loadModelle(MD_SEITE)}
// „Hinzufügen“ from a hit: the full check on the newest commit, then the entry pinned to it
async function mdDazu(repo){const art=MD_OFFEN,msg=$('mdmsg');msg.textContent='';let v;
  try{v=(await (await api('/api/admin/modelle/eigen/pruefen',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({art,repo})})).json()).vorschlag}catch(e){msg.textContent=e.message;return}
  MD_TREFFER[art]=(MD_TREFFER[art]||[]).filter(h=>h.repo!==repo);
  mdPost('/api/admin/modelle/eigen',{art,repo,revision:v.revision},t('„'+repo+'“ hinzufügen? Stand '+v.revision.slice(0,12)+', Platte '+v.platte_gb+' GB, Speicher ~'+mdGib(v.need_gib)+', Lizenz '+v.lizenz+'. Geladen wird erst beim Ausprobieren.',
    'Add "'+repo+'"? Commit '+v.revision.slice(0,12)+', disk '+v.platte_gb+' GB, memory ~'+mdGib(v.need_gib)+', licence '+v.lizenz+'. It downloads only when trying it.'))}
function mdKnoepfe(d){const main=$('mdmain');
  main.querySelectorAll('[data-mdw]').forEach(b=>b.onclick=()=>{const m=d.arten.flatMap(y=>y.modelle).find(y=>y.id===b.dataset.mdid);
    mdPost('/api/admin/modelle/wechseln',{art:b.dataset.mdw,id:b.dataset.mdid},t('Zu „'+(m?m.name:b.dataset.mdid)+'“ wechseln? Der Spark lädt und prüft das Modell; das alte bleibt '+d.wechsel.tage+' Tage zum Zurückholen.','Switch to "'+(m?m.name:b.dataset.mdid)+'"? The Spark loads and checks the model; the old one stays '+d.wechsel.tage+' days to bring back.'))});
  main.querySelectorAll('[data-mdm]').forEach(b=>b.onclick=()=>{const m=d.arten.flatMap(y=>y.modelle).find(y=>y.id===b.dataset.mdm);
    mdPost('/api/admin/modelle/messen',{id:b.dataset.mdm},t('„'+(m?m.name:b.dataset.mdm)+'“ messen? Der Spark lädt es falls nötig, das Sprachmodell pausiert für etwa 10 bis 25 Minuten und startet danach wieder. Gewechselt wird nichts.','Measure "'+(m?m.name:b.dataset.mdm)+'"? The Spark downloads it if needed, the language model pauses for about 10 to 25 minutes and starts again afterwards. Nothing is switched.'))});
  if($('mdplatzok'))$('mdplatzok').onclick=()=>{const r=main.querySelector('input[name=mdplatz]:checked'),p=(d.wechsel||{}).platz;if(!r||!p)return;
    if(r.value===p.jetzt){$('mdmsg').textContent=t('Das ist schon eingestellt.','That is set already.');return}
    const n=(p.wahl.find(x=>x.id===r.value)||{}).name||r.value;
    mdPost('/api/admin/modelle/platz',{platz:r.value},t('„'+n+'“ einstellen? Das Sprachmodell startet dafür neu und antwortet ein paar Minuten nicht.','Set "'+n+'"? The language model restarts for it and does not answer for a few minutes.'))};
  main.querySelectorAll('[data-mdz]').forEach(b=>b.onclick=()=>mdPost('/api/admin/modelle/zurueck',{art:b.dataset.mdz},t('Das vorige Modell zurückholen?','Bring back the previous model?')));
  main.querySelectorAll('[data-mde]').forEach(b=>b.onclick=()=>mdPost('/api/admin/modelle/eigen/'+encodeURIComponent(b.dataset.mde),null,t('Dieses eigene Modell aus der Liste und von der Platte löschen?','Delete this own model from the list and from the disk?'),'DELETE'));
  main.querySelectorAll('[data-mdo]').forEach(b=>b.onclick=()=>{MD_OFFEN=MD_OFFEN===b.dataset.mdo?'':b.dataset.mdo;loadModelle(MD_SEITE)});
  main.querySelectorAll('[data-mdp]').forEach(b=>b.onclick=()=>{const m=d.arten.flatMap(y=>y.modelle).find(y=>y.id===b.dataset.mdp);
    mdPost('/api/admin/modelle/messen',{id:b.dataset.mdp,probe:true},t('„'+(m?m.name:b.dataset.mdp)+'“ ausprobieren? Der Spark lädt es falls nötig und misst es; das Sprachmodell pausiert für etwa 10 bis 25 Minuten. Danach fragt die Seite, ob gewechselt wird.','Try "'+(m?m.name:b.dataset.mdp)+'"? The Spark downloads it if needed and measures it; the language model pauses for about 10 to 25 minutes. Afterwards the page asks whether to switch.'))});
  main.querySelectorAll('[data-mdh]').forEach(b=>b.onclick=()=>mdDazu(b.dataset.mdh));
  if($('mdqs')){$('mdqs').onclick=mdSuchen;$('mdq').onkeydown=e=>{if(e.key==='Enter')mdSuchen()}}
  if($('mdpv'))$('mdpv').onclick=()=>mdPost('/api/admin/modelle/probe',null,t('Die Frage zum ausprobierten Modell verwerfen? Gewechselt wird nichts.','Discard the question about the tried model? Nothing is switched.'),'DELETE');
  const mehr=$('mdmehr');if(mehr)mehr.ontoggle=()=>{MD_MEHR=mehr.open}}
let MD_SEITE=null;
async function loadModelle(daten){const main=$('mdmain'),msg=$('mdmsg');if(!main)return;msg.textContent='';
  let d=daten;if(!d)try{d=await (await api('/api/admin/modelle'+(L==='en'?'?lang=en':''))).json()}catch(e){msg.textContent=e.message;return}
  const w=d.wechsel||{};
  MD_SEITE=d;if(MD_OFFEN&&!d.arten.some(a=>a.art===MD_OFFEN))MD_OFFEN='';
  main.innerHTML=mdWechsel(w)+mdProbe(w)+mdBalken(d.budget)+`<div class="mdkacheln">${d.arten.filter(a=>a.modelle.length).map(a=>mdKachel(a,w)).join('')}</div>`+mdWahl(d,w)+
    `<details class="mdmehr" id="mdmehr"${MD_MEHR?' open':''}><summary>${esc(t('Mehr: Lange Gespräche, Messwerte, Messen, Zurückholen','More: long conversations, measurements, measuring, bringing back'))}</summary>`+
    `<div class="vb-two">${mdPlatz(w)}${mdBudget(d.budget)}${d.arten.map(a=>mdArt(a,w,d)).join('')}</div>`+
    `<div class="mut vb-note">${esc(d.messung_zeit?t('Letzte Messung: ','Last measurement: ')+new Date(d.messung_zeit*1000).toLocaleString(L==='en'?'en':'de'):t('Noch keine Messung. „Messen“ beim Modell (mit Funktionen → Modelle wechseln) oder auf dem Spark: sudo speech-spark modelle messen','No measurement yet. „Measure“ at the model (with Features → Switch models) or on the Spark: sudo speech-spark modelle messen'))}`+
    ` · ${esc(t('„~“ heißt geschätzt.','“~” means estimated.'))}</div></details>`;
  mdKnoepfe(d);if(typeof labelTables==='function')labelTables();
  clearTimeout(window.mdTick);const st=w.start&&!w.start.ende;if(w.laeuft||w.misst||st)window.mdTick=setTimeout(()=>{if($('mdmain')&&$('mdmain').offsetParent)loadModelle()},w.misst||st?8000:15000)}
