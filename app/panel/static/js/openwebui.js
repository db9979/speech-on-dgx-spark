// "Open WebUI einbinden" (openwebui.py, plan open-webui/plan.md): one step under Ich → Sprachmodell per API makes the
// key for the language model and the MCP connection (reading and "Spark fragen" only), both home network only, and
// shows the fields to copy into Open WebUI once; "Trennen" removes both. The menu entry opens Open WebUI (inner address
// at home, outer one through the proxy). The admin sees who is connected under Apps und Schnittstellen.
let OWUI_ON=false,OWUI_NEW=null;
// the address Open WebUI's server uses for the Spark: this page's host when it is one in the home network
function owLan(path){const h=location.hostname,port=(CFG&&CFG.panel&&CFG.panel.port)||31080;
  const lan=/^(10|127|192\.168|172\.(1[6-9]|2\d|3[01]))\./.test(h)||!h.includes('.')||/\.(local|lan|home|fritz\.box)$/.test(h);
  return `http://${lan?h:t('SPARK-IP','SPARK-IP')}:${port}${path}`}
// the menu entry: only for a profile that may use it and only when there is an address for where this page is
async function owuiNav(){const b=$('navowui');if(!b)return;b.hidden=true;if(!PROFILE||!OWUI_ON)return;
  let d=null;try{d=await (await api('/api/profile/openwebui')).json()}catch{return}
  if(!d||!d.on||!/^https?:\/\//.test(d.link||''))return;
  b.hidden=false;b.onclick=()=>window.open(d.link,'_blank','noopener,noreferrer')}
async function showOwui(){const box=$('owuibox');if(!box)return;if(!PROFILE||!OWUI_ON){box.innerHTML='';return}
  let d=null;try{d=await (await api('/api/profile/openwebui')).json()}catch{box.innerHTML='';return}
  if(!d.enabled){box.innerHTML='';return}
  if(!d.on){box.innerHTML=`<h3 style="margin:14px 0 4px">Open WebUI</h3><div class="fh">${t('Für dein Profil gerade gesperrt.','Blocked for your profile right now.')}</div>`;return}
  const state=d.connected?`${t('Verbunden','Connected')}: ${t('Sprachmodell','language model')}${d.mcp_conn?' · '+t('Spark-Werkzeuge (nur lesend)','Spark tools (read only)'):''}`:t('Noch nicht verbunden.','Not connected yet.');
  box.innerHTML=`<h3 style="margin:14px 0 4px">Open WebUI</h3>
    <div class="fh">${t('Ein Schritt für Open WebUI: ein Schlüssel fürs Sprachmodell und, wenn freigegeben, die Spark-Werkzeuge zum Nachlesen (mit „Spark fragen“). Beides gilt nur im Heimnetz; das reicht, denn Open WebUI fragt den Spark von seinem Server aus, auch wenn du es unterwegs öffnest.','One step for Open WebUI: a key for the language model and, if allowed, the Spark tools for reading (with "Ask the Spark"). Both work only in the home network; that is enough, as Open WebUI asks the Spark from its server, also when you open it on the go.')}</div>
    <ul class="facts"><li><span>${esc(state)}</span>${d.connected?`<button class="b" type="button" id="owoff">${t('Trennen','Disconnect')}</button>`:''}</li></ul>
    <div class="row" style="margin-top:8px"><button class="b p" type="button" id="owon">${d.connected?t('Neu verbinden','Connect again'):t('Open WebUI verbinden','Connect Open WebUI')}</button>${d.link?`<button class="b" type="button" id="owopen">${t('Open WebUI öffnen','Open Open WebUI')}</button>`:''}</div>
    ${d.mcp?'':`<div class="fh">${t('Ohne „Spark als MCP-Server“ (Funktionen) gibt es nur das Sprachmodell, keine Spark-Werkzeuge.','Without "Spark as MCP server" (Features) there is only the language model, no Spark tools.')}</div>`}
    <div class="fh" id="owmsg" role="status"></div><div id="owkey"></div>`;
  owKeyShow();
  if($('owopen'))$('owopen').onclick=()=>window.open(d.link,'_blank','noopener,noreferrer');
  $('owon').onclick=async()=>{if(d.connected&&!confirm(t('Neu verbinden? Die alten Schlüssel für Open WebUI gelten dann sofort nicht mehr.','Connect again? The old keys for Open WebUI stop working at once.')))return;
    const b=$('owon');b.disabled=true;xmsg('owmsg',t('Wird verbunden …','Connecting …'));
    try{OWUI_NEW=await (await api('/api/profile/openwebui',xjson('POST',{}))).json();await showOwui();if($('owkey'))$('owkey').scrollIntoView({block:'nearest'})}
    catch(e){b.disabled=false;xmsg('owmsg',/code required|Code/i.test(errRaw(e))?t('Ohne deinen Code geht es nicht: bitte noch einmal tippen und den Code aus der Authenticator-App eingeben.','Not without your code: tap again and enter the code from your authenticator app.'):e.message,true)}};
  if($('owoff'))$('owoff').onclick=async()=>{if(!confirm(t('Open WebUI trennen? Schlüssel und MCP-Zugang gelten dann sofort nicht mehr.','Disconnect Open WebUI? Key and MCP access stop working at once.')))return;
    try{await api('/api/profile/openwebui',{method:'DELETE'});await showOwui();xmsg('owmsg',t('Getrennt.','Disconnected.'))}catch(e){xmsg('owmsg',e.message,true)}}}
// the fields to copy, shown once right after "Open WebUI verbinden"
function owKeyShow(){const k=$('owkey'),r=OWUI_NEW;OWUI_NEW=null;if(!k||!r)return;
  const rows=a=>`<table><tbody>${a.map(([x,y])=>`<tr><td>${esc(x)}</td><td><code>${esc(y)}</code></td></tr>`).join('')}</tbody></table>`;
  k.innerHTML=`<div class="fh"><b>${t('Nur jetzt sichtbar:','Shown only now:')}</b> ${t('in Open WebUI eintragen.','enter in Open WebUI.')}</div>
    <div class="fh"><b>1.</b> ${t('Admin-Panel → Einstellungen → Verbindungen → OpenAI-API „+“','Admin panel → Settings → Connections → OpenAI API "+"')}</div>
    ${rows([[t('URL','URL'),owLan('/v1')],[t('Schlüssel','Key'),r.llm_token]])}
    ${r.mcp_token?`<div class="fh"><b>2.</b> ${t('Admin-Panel → Einstellungen → Externe Werkzeuge → „+“, Typ MCP (Streamable HTTP), Authentifizierung Bearer','Admin panel → Settings → External tools → "+", type MCP (Streamable HTTP), authentication Bearer')}</div>
    ${rows([[t('URL','URL'),owLan('/mcp')],[t('Schlüssel','Key'),r.mcp_token]])}`:''}
    <div class="fh">${t('Sprache (Hören und Sprechen): Admin-Panel → Einstellungen → Audio; die Werte stehen unter Personen und Geräte → Apps und Schnittstellen.','Speech (listening and speaking): admin panel → Settings → Audio; the values are under People and devices → Apps and interfaces.')}</div>`;
  xmsg('owmsg',t('Verbunden.','Connected.'))}
// Apps und Schnittstellen (admin): which profiles connected Open WebUI and whether its addresses are set
async function loadOwuiAdmin(){const el=$('int-owui');if(!el)return;let d;try{d=await (await api('/api/admin/openwebui')).json()}catch{el.innerHTML='';return}
  if(!d.enabled){el.innerHTML=`<div class="mut">${t('Aus. Einschalten unter Funktionen → Open WebUI einbinden.','Off. Switch on under Features → Open WebUI integration.')}</div>`;return}
  el.innerHTML=`<ul class="facts"><li><span>${t('Adresse im Heimnetz','Address in the home network')}: ${d.inner?t('eingetragen','set'):t('fehlt (Funktionen → Open WebUI einbinden)','missing (Features → Open WebUI integration)')}</span></li>
    <li><span>${t('Adresse von außen','Address from outside')}: ${d.outer?t('eingetragen','set'):t('keine','none')}</span></li>
    <li><span>${t('Verbunden','Connected')}: ${d.profiles.length?d.profiles.map(esc).join(', '):t('noch niemand','nobody yet')}</span></li></ul>`}
