// Zustand → Modell-Rechner genau (modellgenau.py, Dominik 2026-11-16 „Alles auf einmal umsetzen“): what the computer
// with the models does right now: tiles, services with their slots, the requests (kind, stage, seconds, tokens; never
// what was asked), the language model inside (vLLM), the GPU and the memory per service, the events and one curve of
// 20 minutes, 24 hours or 7 days. Opened from the model computer's card under Rechner, from „Technische Details“ (one
// Spark without a Pi) and by the way „Zustand → Modell-Rechner genau“. Every number and word through esc(); a poll
// every 3 s while the page shows. Widths of bars are set through the CSSOM, never as inline style.
let MG=null,MG_T=0,MG_ZEIT='20m',MG_INNEN='llm';
const MG_SERIEN=[['tok','tok/s','tok/s','mgs1'],['gpu','GPU %','GPU %','mgs2'],['warten',['wartende Anfragen','waiting requests'],null,'mgs3']];
const mgN=(v,d=0)=>v==null?'–':(+v).toLocaleString(L==='en'?'en':'de',{maximumFractionDigits:d,minimumFractionDigits:0});
const mgS=v=>v==null?'–':v<1?mgN(v*1000)+' ms':mgN(v,2)+' s';
const mgNm=(x,de,en)=>esc(L==='en'?(x[en]||x[de]||''):(x[de]||''));
function mgOpen(){const p=$('zmgdet');if(!p)return;p.hidden=false;document.body.classList.add('mgdet');mgDraw();mgLoad()}
function mgClose(){const p=$('zmgdet');if(!p||p.hidden)return;p.hidden=true;document.body.classList.remove('mgdet');clearTimeout(MG_T)}
window.mgOpen=mgOpen;
async function mgLoad(){clearTimeout(MG_T);const p=$('zmgdet');if(!p||p.hidden)return;
  if(!document.hidden){try{MG=await (await api('/api/admin/modellgenau?zeit='+MG_ZEIT,{cache:'no-store'})).json();mgDraw()}catch{}}
  MG_T=setTimeout(mgLoad,3e3)}
function mgTile(k,big,unit,small,serie,max){return `<div class="mgtile"><small>${esc(k)}</small><b>${esc(big)}</b><span class="mut">${esc(unit)}</span>
  ${small?`<small class="mut">${esc(small)}</small>`:''}<svg class="zrspark" aria-hidden="true" data-serie="${esc(serie||'')}" data-max="${max??''}"></svg></div>`}
function mgBar(pct,cls){return `<span class="mgbar${cls?' '+cls:''}"><i data-w="${Math.max(0,Math.min(100,Math.round(pct||0)))}"></i></span>`}
function mgSlots(x){const n=Math.min(x.plaetze||0,16);if(!n)return '–';let h='';for(let i=0;i<n;i++)h+=`<i class="mgslot${i<(x.laufen||0)?' r':i<(x.laufen||0)+(x.warten||0)?' w':''}"></i>`;
  return `<span class="mgslots" title="${esc(t(`${x.laufen||0} laufen, ${x.warten||0} warten, ${x.plaetze} Plätze`,`${x.laufen||0} running, ${x.warten||0} waiting, ${x.plaetze} slots`))}">${h}</span>`}
const MG_ZLVL={geladen:'ok',laedt:'warn',haengt:'bad',fehler:'bad',entladen:'',aus:'',fehlt:''};
function mgDienste(d){return `<div class="mgtab"><table><thead><tr><th>${esc(t('Dienst','Service'))}</th><th>${esc(t('Zustand','State'))}</th><th>${esc(t('Modell','Model'))}</th>
  <th>${esc(t('Plätze','Slots'))}</th><th>${esc(t('läuft / wartet','running / waiting'))}</th><th>${esc(t('letzte 5 min','last 5 min'))}</th><th>${esc(t('abgelehnt','refused'))}</th></tr></thead><tbody>
  ${d.dienste.map(x=>`<tr><td><b>${mgNm(x,'name','en')}</b></td><td><span class="pill ${MG_ZLVL[x.zustand]||''}">${mgNm(x,'zustand_name','zustand_en')}</span></td>
   <td>${mgNm(x,'modell','modell_en')||'–'}</td><td>${mgSlots(x)}</td><td>${x.plaetze!=null||x.laufen!=null?mgN(x.laufen||0)+' / '+mgN(x.warten||0):'–'}</td>
   <td>${mgN(x.anfragen_5m)}</td><td>${x.voll?mgN(x.voll):'0'}</td></tr>`).join('')}</tbody></table></div>`}
function mgAnfragen(d){if(!d.anfragen.length)return `<div class="mut mgleer">${esc(t('Gerade keine Anfrage.','No request right now.'))}</div>`;
  return `<div class="mgtab"><table><thead><tr><th>#</th><th>${esc(t('Dienst','Service'))}</th><th>${esc(t('Art','Kind'))}</th><th>${esc(t('Stufe','Stage'))}</th>
  <th>${esc(t('seit','for'))}</th><th>${esc(t('Tokens rein','Tokens in'))}</th><th>${esc(t('Tokens raus','Tokens out'))}</th><th>tok/s</th></tr></thead><tbody>
  ${d.anfragen.map((x,i)=>`<tr${x.z==='wartet'?' class="mgwartet"':''}><td>${i+1}</td><td>${mgNm(x,'dienst','dienst_en')}</td><td>${mgNm(x,'art_name','art_en')}${x.folge?esc(t(' · Folgesatz',' · follow-up')):''}${x.kunde?' · '+esc(x.kunde):''}</td>
   <td><span class="${x.stufe===2?'mgst mgst2':'mgst'}">${mgNm(x,'stufe_name','stufe_en')}</span></td><td>${x.z==='wartet'?esc(t('wartet ','waits '))+mgN(x.s,1)+' s':mgN(x.s,1)+' s'}</td>
   <td>${mgN(x.rein)}</td><td>${mgN(x.raus)}</td><td>${mgN(x.tok_s)}</td></tr>`).join('')}</tbody></table></div>`}
const MG_ERG={fertig:'ok',abgebrochen:'warn',zeit:'bad',fehler:'bad'};
function mgFertig(d){if(!d.fertig||!d.fertig.length)return `<div class="mut mgleer">${esc(t('Noch keine fertige Anfrage.','No finished request yet.'))}</div>`;
  return `<div class="mgtab"><table><thead><tr><th>${esc(t('Ende','End'))}</th><th>${esc(t('Art','Kind'))}</th><th>${esc(t('Stufe','Stage'))}</th><th>${esc(t('Dauer','Duration'))}</th>
  <th>${esc(t('Tokens rein','Tokens in'))}</th><th>${esc(t('Tokens raus','Tokens out'))}</th><th>${esc(t('Ergebnis','Result'))}</th></tr></thead><tbody>
  ${d.fertig.map(x=>`<tr><td>${esc(new Date(x.t*1000).toLocaleTimeString(L==='en'?'en':'de',{hour:'2-digit',minute:'2-digit',second:'2-digit'}))}</td>
   <td>${mgNm(x,'art_name','art_en')}${x.kunde?' · '+esc(x.kunde):''}</td><td>${mgNm(x,'stufe_name','stufe_en')}</td><td>${mgN(x.s,1)} s</td>
   <td>${mgN(x.rein)}</td><td>${mgN(x.raus)}</td><td><span class="pill ${MG_ERG[x.ergebnis]||''}">${mgNm(x,'ergebnis_name','ergebnis_en')}</span></td></tr>`).join('')}</tbody></table></div>`}
function mgRow(k,v,bar){return `<div class="mgrow"><span>${esc(k)}</span><b>${bar||''}${esc(v)}</b></div>`}
function mgInnen(d){const ids=Object.keys(d.innen);if(!ids.length)return `<div class="mut mgleer">${esc(t('Keine vLLM-Engine läuft gerade.','No vLLM engine runs right now.'))}</div>`;
  if(!d.innen[MG_INNEN])MG_INNEN=ids[0];const x=d.innen[MG_INNEN];
  const seg=ids.length>1?`<div class="segc mgseg">${ids.map(i=>`<button type="button" data-mgi="${esc(i)}" class="${i===MG_INNEN?'on':''}">${mgNm(d.innen[i],'name','en')}</button>`).join('')}</div>`:'';
  const k=x.kanarie;
  return seg+mgRow(t('Schreiben (Ausgabe)','Writing (output)'),x.raus_s==null?'–':mgN(x.raus_s,1)+' tok/s')
    +mgRow(t('Lesen (Prefill)','Reading (prefill)'),x.rein_s==null?'–':mgN(x.rein_s)+' tok/s')
    +mgRow(t('läuft / wartet in der Engine','running / waiting in the engine'),mgN(x.laufen)+' / '+mgN(x.warten))
    +mgRow(t('Erstes Token p50 / p95','First token p50 / p95'),mgS(x.ttft_p50)+' / '+mgS(x.ttft_p95))
    +mgRow(t('Zeit je Token p50','Time per token p50'),mgS(x.itl_p50))
    +mgRow(t('KV-Cache belegt','KV cache used'),x.kv==null?'–':mgN(x.kv,1)+' %'+(x.kv_tokens?t(` von ${mgN(x.kv_tokens)} Token`,` of ${mgN(x.kv_tokens)} tokens`):''),x.kv==null?'':mgBar(x.kv,x.kv>=90?'bad':''))
    +mgRow(t('Prefix-Cache Treffer (5 min)','Prefix cache hits (5 min)'),x.prefix_pct==null?'–':mgN(x.prefix_pct,1)+' %',x.prefix_pct==null?'':mgBar(x.prefix_pct,'ok'))
    +mgRow(t('MTP angenommen (5 min)','MTP accepted (5 min)'),x.mtp_pct==null?t('aus','off'):mgN(x.mtp_pct,1)+' %'+(x.mtp_je_schritt?t(` · Ø ${mgN(x.mtp_je_schritt,2)} Token je Schritt`,` · ⌀ ${mgN(x.mtp_je_schritt,2)} tokens per step`):''))
    +mgRow(t('Fertige Anfragen (5 min)','Finished requests (5 min)'),mgN(x.fertig_5m))
    +mgRow(t('Verdrängt (Preemption) seit Start','Preempted since start'),mgN(x.verdraengt))
    +(k?mgRow(t('Probeantwort','Test answer'),(k.status==='ready'?t('klappt','works'):k.status==='error'?t('klappt nicht','fails'):k.status==='loading'?t('lädt','loading'):'–')+(k.ms!=null?' · '+mgN(k.ms)+' ms':'')):'')
    +(x.kontext?mgRow(t('Kontext','Context'),t(`höchstens ${mgN(x.kontext)} Token`,`at most ${mgN(x.kontext)} tokens`)):'')}
const MG_FARBEN=['mgc1','mgc2','mgc3','mgc4','mgc5','mgc6','mgc7'];
function mgGpu(d){const g=d.gpu||{},gr=g.grenze&&g.grenze.wort&&g.grenze.wort!=='aus'?g.grenze.wort:'';
  const dr=(g.drossel_namen||[]).filter(x=>x[0]!=='Leerlauf');
  const sp=d.speicher||[],belegt=sp.reduce((a,x)=>a+x.gib,0),ges=d.mem.gesamt||(d.mem.frei!=null?belegt+d.mem.frei:belegt);
  return mgRow(t('Auslastung','Load'),g.util==null?'–':mgN(g.util)+' %',g.util==null?'':mgBar(g.util,''))
    +mgRow(t('SM-Takt','SM clock'),(g.clock==null?'–':mgN(g.clock)+' MHz')+(gr?t(` · Grenze ${gr}`,` · cap ${gr}`):g.takt_max?t(` · höchstens ${mgN(g.takt_max)}`,` · at most ${mgN(g.takt_max)}`):''))
    +mgRow(t('Leistung','Power'),g.power==null?'–':mgN(g.power,1)+' W')+mgRow(t('Temperatur','Temperature'),g.temp==null?'–':mgN(g.temp)+' °C')
    +mgRow(t('Drosselt gerade','Throttling now'),g.drossel==null?'–':dr.length?dr.map(x=>L==='en'?x[1]:x[0]).join(', '):t('nein','no'))
    +mgRow(t('Leistungsstufe','Performance state'),g.pstate||'–')
    +mgRow(t('Speicher verweigert (Treiber)','Memory refused (driver)'),g.nvrm==null?'–':t(`${mgN(g.nvrm.h1)} in 1 Std. · ${mgN(g.nvrm.h24)} in 24 Std.`,`${mgN(g.nvrm.h1)} in 1 h · ${mgN(g.nvrm.h24)} in 24 h`))
    +`<h3 class="sec">${esc(t('Speicher je Dienst','Memory per service'))}<span class="mut">${esc(t('Schätzung','estimate'))}</span></h3>`
    +(sp.length&&ges?`<div class="mgmem">${sp.map((x,i)=>`<i class="${MG_FARBEN[i%MG_FARBEN.length]}" data-w="${Math.max(0.5,100*x.gib/ges)}" title="${mgNm(x,'name','en')} ${mgN(x.gib,1)} GiB"></i>`).join('')}</div>
      <div class="mgleg">${sp.map((x,i)=>`<span><i class="${MG_FARBEN[i%MG_FARBEN.length]}"></i>${mgNm(x,'name','en')} ${mgN(x.gib,1)} GiB</span>`).join('')}<span><i class="mgfrei"></i>${esc(t('frei','free'))} ${mgN(d.mem.frei,1)} GiB</span></div>`
      :`<div class="mut">${esc(t('Noch keine Werte.','No values yet.'))}</div>`)
    +`<div class="mut mgnote">${esc(t(`Die Dienste halten zusammen ${mgN(belegt,1)} GiB. Unter etwa 8 GiB frei beendet DGX OS Prozesse.`,`The services hold ${mgN(belegt,1)} GiB together. Below about 8 GiB free DGX OS kills processes.`))}</div>`}
function mgEreignisse(d){if(!d.ereignisse.length)return `<div class="mut mgleer">${esc(t('Noch keine Ereignisse.','No events yet.'))}</div>`;
  return d.ereignisse.map(e=>`<div class="mgev"><time>${esc(new Date(e.t*1000).toLocaleString(L==='en'?'en':'de',{weekday:'short',hour:'2-digit',minute:'2-digit'}))}</time>
    <span>${esc((e.dienst&&e.dienst[0]?(L==='en'?e.dienst[1]:e.dienst[0])+': ':'')+(L==='en'?e.name[1]:e.name[0])+(e.n!=null?' ('+e.n+')':''))}</span></div>`).join('')}
function mgVerlauf(){return `<div class="segc mgseg">${[['20m','20 min','20 min'],['24h','24 Std.','24 h'],['7d','7 Tage','7 days']].map(z=>`<button type="button" data-mgz="${z[0]}" class="${z[0]===MG_ZEIT?'on':''}">${esc(t(z[1],z[2]))}</button>`).join('')}</div>
  <svg class="mgchart" id="zmgchart" viewBox="0 0 800 140" preserveAspectRatio="none" aria-hidden="true"></svg>
  <div class="mgleg">${MG_SERIEN.map(s=>`<span><i class="${s[3]}"></i>${esc(Array.isArray(s[1])?t(...s[1]):s[1])}</span>`).join('')}</div>`}
// three lines on one chart, each scaled to its own top (a tooltip-free overview; the numbers stand in the tiles)
function mgChart(svg,K){if(!svg)return;const W=800,H=140,n=K.length;svg.textContent='';
  for(const y of [35,70,105]){const l=document.createElementNS('http://www.w3.org/2000/svg','line');l.setAttribute('x1',0);l.setAttribute('x2',W);l.setAttribute('y1',y);l.setAttribute('y2',y);l.setAttribute('class','mggrid');svg.appendChild(l)}
  if(n<2)return;
  for(const [k,,,cls] of MG_SERIEN){const vs=K.map(p=>p[k]),max=Math.max(k==='gpu'?100:1,...vs.filter(v=>v!=null));let d='',pen=false;
    vs.forEach((v,i)=>{if(v==null){pen=false;return}const x=(i/(n-1))*W,y=H-4-(v/max)*(H-12);d+=(pen?'L':'M')+x.toFixed(1)+' '+y.toFixed(1);pen=true});
    const p=document.createElementNS('http://www.w3.org/2000/svg','path');p.setAttribute('d',d);p.setAttribute('class','mgline '+cls);svg.appendChild(p)}}
function mgDraw(){const p=$('zmgdet');if(!p||p.hidden)return;const b=$('zmgbody'),d=MG;
  if(!d){setHtml(b,`<div class="card mut">${esc(t('Lädt …','Loading …'))}</div>`);return}
  if(!d.da){setHtml(b,`<div class="card mut">${esc(d.remote?t('Der Modell-Rechner antwortet gerade nicht. Seine Werte kommen, sobald er wieder antwortet.','The model computer does not answer right now. Its values come once it answers again.')
    :t('Noch keine Werte: die erste Messung kommt in wenigen Sekunden.','No values yet: the first measurement comes in a few seconds.'))}</div>`);return}
  const g=d.gpu||{},j=d.jetzt,K=d.kurve||[];
  $('zmgmeta').textContent=[g.name||'',d.remote?t('Werte vom Wärter des Modell-Rechners','values from the model computer\'s Wärter'):t('dieser Rechner','this computer'),
    t('alle 3 s neu','new every 3 s'),t('nur Zahlen und feste Wörter, nie Inhalte','numbers and fixed words only, never content')].filter(Boolean).join(' · ');
  const hin=d.hinweise.length?`<div class="card mghin">${d.hinweise.map(h=>`<div class="mghrow"><span class="zrdot" data-lvl="warn"></span>${mgNm(h,'text','en')}</div>`).join('')}</div>`:'';
  setHtml(b,hin+`<div class="mgtiles">${mgTile(t('Anfragen laufen','Requests running'),mgN(j.laufen),t(` von ${mgN(j.plaetze)} Plätzen`,` of ${mgN(j.plaetze)} slots`),'','laufen')
    +mgTile(t('Warten','Waiting'),mgN(j.warten),j.warten?t(` längstens ${mgN(j.warten_max_s,1)} s`,` longest ${mgN(j.warten_max_s,1)} s`):'','','warten')
    +mgTile(t('Sprachmodell schreibt','Language model writes'),mgN(j.tok_s),' tok/s','','tok')
    +mgTile('GPU',mgN(g.util),' %'+(g.clock!=null?' · '+mgN(g.clock)+' MHz':''),'','gpu',100)
    +mgTile(t('Leistung · Temperatur','Power · temperature'),mgN(g.power),' W'+(g.temp!=null?' · '+mgN(g.temp)+' °C':''),'','w')
    +mgTile('Unified Memory',mgN(d.mem.frei,1),t(` GiB frei von ${mgN(d.mem.gesamt,1)}`,` GiB free of ${mgN(d.mem.gesamt,1)}`),'','frei',d.mem.gesamt)}</div>
    <div class="mggrid">
     <div class="card mgwide"><h2>${esc(t('Dienste und Anfragen','Services and requests'))}<span class="mut">${esc(t('Plätze: blau läuft, gelb wartet','Slots: blue runs, yellow waits'))}</span></h2>${mgDienste(d)}
      <h3 class="sec">${esc(t('Laufende und wartende Anfragen','Running and waiting requests'))}<span class="mut">${esc(t('ohne Inhalt, ohne Profil','without content, without profile'))}</span></h3>${mgAnfragen(d)}
      <h3 class="sec">${esc(t('Zuletzt fertig','Finished lately'))}<span class="mut">${esc(t('Sprachmodell, mit Ergebnis','language model, with result'))}</span></h3>${mgFertig(d)}</div>
     <div class="card"><h2>${esc(t('Sprachmodell innen','Language model inside'))}<span class="mut">vLLM /metrics</span></h2>${mgInnen(d)}</div>
     <div class="card"><h2>GPU<span class="mut">${esc(t('nvidia-smi, nur lesen','nvidia-smi, read only'))}</span></h2>${mgGpu(d)}</div>
     <div class="card"><h2>${esc(t('Ereignisse','Events'))}<span class="mut">${esc(t('feste Wörter, wie im Log','fixed words, as in the log'))}</span></h2><div>${mgEreignisse(d)}</div></div>
     <div class="card mgwide"><h2>${esc(t('Verlauf','History'))}</h2>${mgVerlauf()}</div>
    </div>`);
  b.querySelectorAll('[data-w]').forEach(e=>{e.style.width=e.dataset.w+'%'});
  b.querySelectorAll('svg[data-serie]').forEach(v=>{const k=v.dataset.serie;if(k)spark(v,K.map(x=>x[k]),v.dataset.max?+v.dataset.max:undefined)});
  mgChart($('zmgchart'),K);
  b.querySelectorAll('[data-mgz]').forEach(x=>x.onclick=()=>{MG_ZEIT=x.dataset.mgz;mgLoad()});
  b.querySelectorAll('[data-mgi]').forEach(x=>x.onclick=()=>{MG_INNEN=x.dataset.mgi;mgDraw()})}
{const p=$('zmgdet');
 if(p){$('zmgback').onclick=mgClose;$('zmggo').onclick=mgOpen;
  $('mon').addEventListener('wayopen',e=>{if(p.contains(e.target))mgOpen();else mgClose()});
  document.addEventListener('visibilitychange',()=>{if(!document.hidden&&!p.hidden)mgLoad()})}}
