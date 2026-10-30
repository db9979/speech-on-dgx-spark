'use strict';
// Fernzugang → Webdienste (fernweb.py): the web pages of a paired system through its anchor, on the door's own origin
// (its own port, or the Tunnel-Adresse from the internet), never on the panel's. „Öffnen“ frames it here with a strip
// above (system, rate, „Neuer Tab“, „Schließen“); „Neuer Tab“ opens it in its own tab with a fresh one-time ticket.
// Every name and address goes through textContent; nothing of the page over there reaches this page (another origin).
const FW={g:null,d:null,form:null,tunnel:null,timer:0,rate:[]};
const FW_GRUND={offline:['Das System ist gerade nicht verbunden.','The system is not connected right now.'],
  anker_alt:['Anker aktualisieren: Webdienste brauchen den Anker 1.6.0 oder neuer.','Update the anchor: web services need anchor 1.6.0 or newer.'],
  zertifikat:['Erst das Zertifikat des Dienstes prüfen und ihm vertrauen.','Check the service\'s certificate and trust it first.'],
  adresse:['Von unterwegs braucht es eine Tunnel-Adresse: Funktionen → Fernzugang zu Servern.','From outside a tunnel address is needed: Features → Remote access to servers.'],
  tuer:['Die Tunnel-Tür startet gerade, gleich noch einmal.','The tunnel door is starting, try again in a moment.']};
function fwGrund(e){const m=String(e&&e.message||'');return FW_GRUND[m]?t(...FW_GRUND[m]):m}
function fwZiel(x){const h=x.host.includes(':')?'['+x.host+']':x.host;return `${x.schema}://${h}:${x.port}${x.pfad&&x.pfad!=='/'?x.pfad:''}`}
async function fwLaden(g){FW.g=g;let d;try{const r=await api(`/api/admin/fernzugang/web/${g.id}`);d=await r.json()}catch(e){fzFehler(e);return}
  FW.d=d;fwZeigen()}
// the block below the system's buttons
function fwBlock(g){const box=fzEl('div','fwblock');box.id='fwblock';if(!FW.g||FW.g.id!==g.id){FW.d=null;FW.form=null;fwLaden(g)}else if(FW.d)setTimeout(fwZeigen,0);
  box.appendChild(fzEl('div','mut',t('Webdienste werden geladen …','Loading web services …')));return box}
function fwZeigen(){const box=$('fwblock'),d=FW.d,g=FW.g;if(!box||!d||!g)return;box.textContent='';
  const kopf=fzEl('div','fwkopf');kopf.append(fzEl('div','fzgrp',t('Webdienste','Web services')),fzEl('span','fzfill'));
  const such=fzBtn(t('Suchen','Search'),'',()=>fwSuchen());such.disabled=!d.online||!d.anker_ok;kopf.appendChild(such);
  const neu=fzBtn(t('+ Dienst','+ Service'),'',()=>{FW.form=FW.form?null:{name:'',schema:'http',host:'127.0.0.1',port:'',pfad:'/'};fwZeigen()});neu.disabled=d.dienste.length>=d.max_dienste;kopf.appendChild(neu);box.appendChild(kopf);
  if(!d.anker_ok)box.appendChild(fzEl('div','note warn',t(...FW_GRUND.anker_alt)));
  if(!d.tor)box.appendChild(fzEl('div','note warn',d.herkunft==='internet'?t('Von unterwegs braucht es eine Tunnel-Adresse: Funktionen → Fernzugang zu Servern. Dann im Reverse-Proxy der Synology eine Regel für diesen Namen auf den Pi, Port '+d.port+', mit den WebSocket-Kopfzeilen.','From outside a tunnel address is needed: Features → Remote access to servers. Then a rule in the Synology reverse proxy for that name to the Pi, port '+d.port+', with the WebSocket headers.'):t('Die Adresse des Panels passt nicht für die Tunnel-Tür.','The panel\'s address does not fit the tunnel door.')));
  const sw=fzEl('div','setrow'),lb=fzEl('div','lbl');const nb=fzEl('b','',t('Netz dahinter','Network behind it'));if(window.codeLock)codeLock(nb,'protect');lb.append(nb,fzEl('span','',t('Aus: nur 127.0.0.1 dort. An: auch private Adressen im Netz des Systems, nie die Netze dieses Spark. Fragt den Code.','Off: only 127.0.0.1 there. On: also private addresses in the system\'s network, never this Spark\'s networks. Asks for the code.')));
  const tg=fzEl('label','tgl'),inp=document.createElement('input');inp.type='checkbox';inp.checked=!!d.netz;inp.setAttribute('aria-label',t('Netz dahinter','Network behind it'));tg.append(inp,fzEl('i'));
  inp.onchange=async()=>{try{await api(`/api/admin/fernzugang/web/${g.id}/netz`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({an:inp.checked})});fwLaden(g)}catch(e){inp.checked=!inp.checked;fzFehler(e)}};
  sw.append(lb,tg);box.appendChild(sw);
  if(FW.form)box.appendChild(fwFormular(g,d));
  const list=fzEl('div','fwliste');
  if(!d.dienste.length)list.appendChild(fzEl('div','mut',t('Noch kein Webdienst. „Suchen“ zeigt, was auf dem System lauscht.','No web service yet. "Search" shows what listens on the system.')));
  for(const x of d.dienste)list.appendChild(fwZeile(g,d,x));box.appendChild(list);
  const f=d.gefunden;if(f){box.appendChild(fzEl('div','fzgrp',t('Gefunden','Found')+' · '+fzUhr(f.t)));const gl=fzEl('div','fwliste');
    if(!f.liste.length)gl.appendChild(fzEl('div','mut',t('Nichts gefunden, das auf 127.0.0.1 lauscht.','Nothing found listening on 127.0.0.1.')));
    for(const p of f.liste){const r=fzEl('div','fwrow'),txt=fzEl('div','fwtext');txt.append(fzEl('b','',String(p.port)),fzEl('span','mut',[p.prog,p.art==='tcp'?t('TCP · Stufe 2','TCP · stage 2'):p.art].filter(Boolean).join(' · ')));r.appendChild(txt);
      if(p.art!=='tcp'){const b=fzBtn(t('Übernehmen','Add'),'',()=>{FW.form={name:p.prog||String(p.port),schema:p.art,host:'127.0.0.1',port:String(p.port),pfad:'/'};fwZeigen()});b.disabled=d.dienste.length>=d.max_dienste;r.appendChild(b)}
      gl.appendChild(r)}
    box.appendChild(gl)}
  box.appendChild(fzEl('div','fh',t(`Höchstens ${d.max_tunnel} Webdienste gleichzeitig offen, einer je Browser; nach 15 Minuten ohne Benutzung, beim Sperren und beim Notaus schließen sie.`,`At most ${d.max_tunnel} web services open at once, one per browser; they close after 15 minutes unused, on lock and on the emergency stop.`)))}
function fwZeile(g,d,x){const r=fzEl('div','fwrow'),txt=fzEl('div','fwtext');txt.append(fzEl('b','',x.name),fzEl('span','mut',fwZiel(x)));r.appendChild(txt);
  const offen=(d.tunnel||[]).some(tu=>tu.dienst===x.id),kein=!d.online||!d.anker_ok||!d.tor;
  if(x.schema==='https'&&!x.fp){const z=fzBtn(t('Zertifikat prüfen','Check certificate'),'',()=>fwZertifikat(g,x));z.disabled=kein;r.appendChild(z)}
  else{const o=fzBtn(offen?t('Ansehen','View'):t('Öffnen','Open'),'p',()=>fwOeffnen(g,x,false)),n=fzBtn(t('Neuer Tab','New tab'),'',()=>fwOeffnen(g,x,true));o.disabled=n.disabled=kein;r.append(o,n)}
  const w=fzBtn(t('Löschen','Delete'),'danger',async()=>{if(!confirm(t(`„${x.name}“ löschen?`,`Delete "${x.name}"?`)))return;try{await api(`/api/admin/fernzugang/web/${g.id}/dienste/${x.id}`,{method:'DELETE'});fwLaden(g)}catch(e){fzFehler(e)}});
  r.appendChild(w);return r}
function fwFormular(g,d){const f=FW.form,w=fzEl('div','fwform');const feld=(lab,key,attrs)=>{const l=fzEl('label','',lab),i=document.createElement('input');i.value=f[key];Object.assign(i,attrs||{});i.oninput=()=>{f[key]=i.value};l.appendChild(i);return l};
  const sel=document.createElement('select');for(const s of ['http','https']){const o=document.createElement('option');o.value=s;o.textContent=s;sel.appendChild(o)}sel.value=f.schema;sel.onchange=()=>{f.schema=sel.value};
  const sl=fzEl('label','',t('Art','Kind'));sl.appendChild(sel);
  const host=feld(t('Adresse dort','Address there'),'host',{autocomplete:'off',spellcheck:false});host.querySelector('input').disabled=!d.netz;
  w.append(feld(t('Name','Name'),'name',{maxLength:40}),sl,host,feld(t('Port','Port'),'port',{type:'number',min:1,max:65535}),feld(t('Pfad','Path'),'pfad',{maxLength:512,spellcheck:false}));
  const ok=fzBtn(t('Speichern','Save'),'p',async()=>{try{await api(`/api/admin/fernzugang/web/${g.id}/dienste`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name:f.name.trim(),schema:f.schema,host:(d.netz?f.host:'127.0.0.1').trim(),port:Number(f.port),pfad:f.pfad.trim()||'/'})});FW.form=null;fwLaden(g)}catch(e){fzFehler(e)}});
  const ab=fzBtn(t('Abbrechen','Cancel'),'',()=>{FW.form=null;fwZeigen()});const row=fzEl('div','row');row.append(ok,ab);w.appendChild(row);
  if(!d.netz)w.appendChild(fzEl('div','fh',t('Nur 127.0.0.1 dort, solange „Netz dahinter“ aus ist.','Only 127.0.0.1 there while "Network behind it" is off.')));return w}
async function fwSuchen(){const g=FW.g;if(!g)return;fzMsg(t('Der Anker sucht …','The anchor searches …'));try{await api(`/api/admin/fernzugang/web/${g.id}/suchen`,{method:'POST'});fzMsg('');fwLaden(g)}catch(e){fzMsg(fwGrund(e),true)}}
async function fwZertifikat(g,x){let d;try{const r=await api(`/api/admin/fernzugang/web/${g.id}/dienste/${x.id}/zertifikat`,{method:'POST'});d=await r.json()}catch(e){fzMsg(fwGrund(e),true);return}
  if(!confirm(t(`Zertifikat von „${x.name}“, SHA-256:\n${d.fp}\n\nStimmt es mit dem auf dem System überein? Dann vertrauen (es wird festgehalten und bei jeder Verbindung geprüft).`,`Certificate of "${x.name}", SHA-256:\n${d.fp}\n\nDoes it match the one on the system? Then trust it (it is pinned and checked on every connection).`)))return;
  try{await api(`/api/admin/fernzugang/web/${g.id}/dienste/${x.id}/vertrauen`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({fp:d.fp})});fwLaden(g)}catch(e){fzFehler(e)}}
async function fwOeffnen(g,x,tab){const w=tab?window.open('about:blank','_blank'):null;let d;
  try{const r=await api('/api/admin/fernzugang/web/oeffnen',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({geraet:g.id,dienst:x.id})});d=await r.json()}
  catch(e){if(w)w.close();fzMsg(fwGrund(e),true);return}
  if(tab){if(w){w.opener=null;w.location.replace(d.url)}fwLaden(g);return}
  FW.tunnel={id:d.tunnel,name:x.name,system:g.name,g,x};FW.rate=[];$('fwname').textContent=x.name;$('fwsystem').textContent=g.name;$('fwrate').textContent='';$('fwlangsam').hidden=true;
  $('fzmain').hidden=true;$('fzstatus').hidden=true;$('fzweb').hidden=false;const f=$('fwframe');f.src=d.url;
  clearInterval(FW.timer);FW.timer=setInterval(fwStand,5000)}
async function fwStand(){const tu=FW.tunnel;if(!tu)return;let d;try{const r=await api('/api/admin/fernzugang/web/tunnel');d=await r.json()}catch(e){fwZu(fwGrund(e));return}
  const x=(d.tunnel||[]).find(y=>y.id===tu.id);if(!x){fwZu(t('Der Webdienst wurde geschlossen (Leerlauf, Sperren oder ein anderer Tab in diesem Browser).','The web service was closed (idle, lock or another tab in this browser).'));return}
  if(Number.isInteger(x.kb_s)){$('fwrate').textContent=x.kb_s+' KB/s';FW.rate=FW.rate.concat([x.kb_s]).slice(-3)}
  $('fwlangsam').hidden=!(FW.rate.length>=2&&FW.rate.every(k=>k<(d.langsam||100)))}
async function fwSchliessen(){const tu=FW.tunnel;if(tu)try{await api(`/api/admin/fernzugang/web/tunnel/${tu.id}`,{method:'DELETE'})}catch{}fwZu('')}
function fwZu(text){clearInterval(FW.timer);const tu=FW.tunnel;FW.tunnel=null;const f=$('fwframe');if(f)f.src='about:blank';$('fzweb').hidden=true;$('fzmain').hidden=false;
  if(text)fzMsg(text,true);if(tu)fwLaden(tu.g);fzLoad()}
async function fwTab(){const tu=FW.tunnel;if(tu)await fwOeffnen(tu.g,tu.x,true)}
{const b=$('fwzu');if(b){b.onclick=fwSchliessen;$('fwtab').onclick=fwTab}}
