// "Ich → Dienste per MCP" (mcpserver.py, V01.0.303): the Spark as an MCP server for other programs. The profile connects
// a program (a key for the home network or from outside, or the OAuth sign-in of claude.ai and the like), gives it tools,
// and confirms or declines what such a program proposes. The admin sees all connections under Apps und Schnittstellen.
let MCPS_ON=false,MCP_NEW=null;
const MCPGRP={speech:['Sprache','Speech'],read:['Lesen','Reading'],ask:['Spark fragen','Ask Spark'],act:['Handeln mit Bestätigung','Acting with confirmation']};
const mcpWhen=x=>x?new Date(x*1000).toLocaleString([], {dateStyle:'short',timeStyle:'short'}):t('noch nie','never');
const mcpWhere=w=>w==='extern'?t('von außen','from outside'):t('nur Heimnetz','home network only');
// the address a program in the home network uses: this page's host when it is one there, else a placeholder
function mcpLan(port){const h=location.hostname;
  const lan=/^(10|127|192\.168|172\.(1[6-9]|2\d|3[01]))\./.test(h)||!h.includes('.')||/\.(local|lan|home|fritz\.box)$/.test(h);
  return `http://${lan?h:t('SPARK-IP','SPARK-IP')}:${port||31080}/mcp`}
function mcpTools(list,have,pre){const by={};list.forEach(x=>(by[x.group]=by[x.group]||[]).push(x));
  return Object.keys(MCPGRP).filter(g=>by[g]).map(g=>`<div class="fh" style="margin-top:8px"><b>${esc(t(...MCPGRP[g]))}</b></div>`+
    by[g].map(x=>`<label class="chk"${x.ok?'':' title="'+esc(t('Für dich gerade aus (Funktionen bzw. Ich)','Off for you right now (Features or Me)'))+'"'}><input type="checkbox" data-${pre}="${esc(x.name)}"${have.includes(x.name)?' checked':''}${x.ok?'':' disabled'}> ${esc(x.label)}</label>`).join('')).join('')}
const mcpPicked=(box,pre)=>[...box.querySelectorAll(`[data-${pre}]`)].filter(x=>x.checked).map(x=>x.getAttribute('data-'+pre));
const MCP_WARN=()=>t('Von außen: Alles, was dieses Programm über den Spark liest, geht an das Programm und dessen Anbieter (bei claude.ai oder ChatGPT in deren Cloud) und verlässt dein Heimnetz. Gib nur die Werkzeuge frei, die es wirklich braucht.',
  'From outside: everything this program reads through the Spark goes to the program and its provider (with claude.ai or ChatGPT into their cloud) and leaves your home network. Only give it the tools it really needs.');
async function showMcp(){const box=$('mcpbox');if(!box)return;if(!PROFILE||!MCPS_ON){box.innerHTML='';return}
  let d={conns:[],tools:[],actions:[]};try{d=await (await api('/api/profile/mcp')).json()}catch{}
  const wait=d.actions.filter(x=>x.state==='wait'),old=d.actions.filter(x=>x.state!=='wait').slice(0,8);
  const conn=c=>`<li><span><b>${esc(c.name)}</b> <small class="ftag ${c.where==='extern'?'out':'me'}">${esc(mcpWhere(c.where))}</small><br>
      <small class="mut">${c.kind==='oauth'?t('OAuth','OAuth')+(c.client?' · '+esc(c.client):''):t('Schlüssel','Key')} · ${c.tools.length} ${t('Werkzeuge','tools')} · ${t('zuletzt','last used')}: ${esc(mcpWhen(c.last))} · ${t('endet ohne Nutzung am','ends without use on')} ${esc(new Date(c.ends*1000).toLocaleDateString())}</small>
      <details><summary>${t('Werkzeuge ändern','Change tools')}</summary>${mcpTools(d.tools,c.tools,'mce-'+c.id)}
        ${c.kind==='key'&&c.where!=='extern'&&d.extern?`<label class="chk"><input type="checkbox" data-mcx="${esc(c.id)}"> ${t('Auch von außen erlauben','Also allow from outside')}</label>`:''}
        ${c.kind==='key'&&c.where==='extern'?`<label class="chk"><input type="checkbox" data-mcl="${esc(c.id)}"> ${t('Wieder nur im Heimnetz','Home network only again')}</label>`:''}
        <div class="row"><button class="b" type="button" data-mcsave="${esc(c.id)}">${t('Speichern','Save')}</button></div></details></span>
      <button class="b" type="button" data-mcdel="${esc(c.id)}" data-mcname="${esc(c.name)}">${t('Entfernen','Remove')}</button></li>`;
  box.innerHTML=`<div class="intro">${t('Andere Programme (Open WebUI, n8n, Home Assistant, Claude …) nutzen den Spark über das Model Context Protocol: hören, sprechen, nachlesen, ihn fragen. Jedes Programm bekommt einen eigenen Zugang mit genau den Werkzeugen, die du ihm gibst. Schalten, Termine und Erinnerungen schlägt ein Programm nur vor; ausgeführt wird erst nach deinem Ja hier.','Other programs (Open WebUI, n8n, Home Assistant, Claude …) use the Spark over the Model Context Protocol: listen, speak, look things up, ask it. Each program gets its own access with exactly the tools you give it. Switching, appointments and reminders are only proposed by a program; they run only after your yes here.')}</div>
    ${xsw('mcps_on',t('Spark als MCP-Server für mich','Spark as MCP server for me'),t('Aus: Alle deine Programme bekommen sofort keine Antwort mehr.','Off: all your programs get no answer any more, at once.'))}
    <div id="mcpauth"></div>
    ${d.on&&wait.length?`<h3 style="margin:14px 0 4px">${t('Wartet auf dich','Waiting for you')}</h3><ul class="facts">${wait.map(x=>`<li><span><b>${esc(x.by)}</b> ${t('möchte','wants')}: ${esc(x.what)}<br><small class="mut">${esc(mcpWhen(x.t))}</small></span>
      <span class="row"><button class="b p" type="button" data-mcyes="${esc(x.id)}">${t('Ja, ausführen','Yes, do it')}</button><button class="b" type="button" data-mcno="${esc(x.id)}">${t('Nein','No')}</button></span></li>`).join('')}</ul>`:''}
    ${d.on?`<h3 style="margin:14px 0 4px">${t('Verbundene Programme','Connected programs')}</h3><ul class="facts">${d.conns.map(conn).join('')||`<li class="mut"><span>${t('Noch kein Programm verbunden.','No program connected yet.')}</span></li>`}</ul>
    <details style="margin-top:10px"><summary>${t('Programm mit Schlüssel verbinden','Connect a program with a key')}</summary>
      <label>${t('Name des Programms','Name of the program')}</label><input id="mcpname" maxlength="60" placeholder="${t('z. B. Open WebUI','e.g. Open WebUI')}" autocomplete="off">
      <label>${t('Erreichbar','Reachable')}</label><select id="mcpwhere"><option value="lokal">${t('Nur im Heimnetz (empfohlen)','Home network only (recommended)')}</option>${d.extern?`<option value="extern"${d.mfa?'':' disabled'}>${t('Auch von außen über den Reverse-Proxy','Also from outside through the reverse proxy')}${d.mfa?'':t(' (braucht deinen zweiten Anmeldeschritt)',' (needs your second sign-in step)')}</option>`:''}</select>
      <div class="fh err" id="mcpwarn" hidden>${esc(MCP_WARN())}</div>
      ${mcpTools(d.tools,[],'mcn')}
      <div class="row" style="margin-top:8px"><button class="b p" type="button" id="mcpmake">${t('Schlüssel erzeugen','Create key')}</button></div>
      <div id="mcpkey"></div></details>
    ${d.extern?`<details style="margin-top:6px"><summary>${t('claude.ai, ChatGPT und andere mit Anmeldung (OAuth)','claude.ai, ChatGPT and others with sign-in (OAuth)')}</summary>
      <div class="fh">${t('Im Programm einen eigenen MCP-Connector mit dieser Adresse anlegen:','In the program add a custom MCP connector with this address:')} <code>${esc(d.url)}</code>. ${t('Das Programm schickt dich zur Anmeldung hierher; du wählst die Werkzeuge und bestätigst mit deinem Code.','The program sends you here to sign in; you pick the tools and confirm with your code.')}</div>
      <div class="fh err">${esc(MCP_WARN())}</div></details>`:''}
    ${old.length?`<details style="margin-top:6px"><summary>${t('Letzte Entscheidungen','Recent decisions')}</summary><ul class="facts small">${old.map(x=>`<li><span>${esc(x.by)}: ${esc(x.what)}<br><small class="mut">${esc({done:t('ausgeführt','done'),fail:t('fehlgeschlagen','failed'),no:t('abgelehnt','declined'),gone:t('abgelaufen','expired'),busy:'…'}[x.state]||x.state)}${x.result?' · '+esc(x.result):''}</small></span></li>`).join('')}</ul></details>`:''}`:''}
    <div class="fh" id="mcpmsg"></div>`;
  xbind(box,showMcp);
  mcpAuthShow(d);mcpKeyShow();
  if($('mcpwhere'))$('mcpwhere').onchange=()=>{$('mcpwarn').hidden=$('mcpwhere').value!=='extern'};
  if($('mcpmake'))$('mcpmake').onclick=async()=>{const where=$('mcpwhere').value;
    if(where==='extern'&&!confirm(MCP_WARN()))return;
    try{const r=await (await api('/api/profile/mcp/keys',xjson('POST',{name:$('mcpname').value.trim(),tools:mcpPicked(box,'mcn'),where}))).json();
      MCP_NEW=Object.assign({},r,{url:where==='extern'?r.url:mcpLan(CFG&&CFG.panel&&CFG.panel.port)});await showMcp()}
    catch(e){xmsg('mcpmsg',e.message,true)}};
  box.querySelectorAll('[data-mcdel]').forEach(b=>b.onclick=async()=>{if(!confirm(t('„','"')+b.dataset.mcname+t('“ entfernen? Sein Zugang gilt dann sofort nicht mehr.','" remove? Its access stops working at once.')))return;
    try{await api('/api/profile/mcp/conns/'+encodeURIComponent(b.dataset.mcdel),{method:'DELETE'});showMcp()}catch(e){xmsg('mcpmsg',e.message,true)}});
  box.querySelectorAll('[data-mcsave]').forEach(b=>b.onclick=async()=>{const id=b.dataset.mcsave,body={tools:mcpPicked(box,'mce-'+id)};
    const x=box.querySelector(`[data-mcx="${id}"]`),l=box.querySelector(`[data-mcl="${id}"]`);
    if(x&&x.checked){if(!confirm(MCP_WARN()))return;body.where='extern'}if(l&&l.checked)body.where='lokal';
    try{await api('/api/profile/mcp/conns/'+encodeURIComponent(id),xjson('PUT',body));await showMcp();xmsg('mcpmsg',t('Gespeichert.','Saved.'))}catch(e){xmsg('mcpmsg',e.message,true)}});
  const decide=async(id,yes)=>{try{const r=await (await api('/api/profile/mcp/actions/'+encodeURIComponent(id),xjson('POST',{yes}))).json();await showMcp();
    xmsg('mcpmsg',r.state==='done'?t('Ausgeführt: ','Done: ')+r.result:r.state==='no'?t('Abgelehnt.','Declined.'):r.result,r.state==='fail')}catch(e){xmsg('mcpmsg',e.message,true)}};
  box.querySelectorAll('[data-mcyes]').forEach(b=>b.onclick=()=>decide(b.dataset.mcyes,true));
  box.querySelectorAll('[data-mcno]').forEach(b=>b.onclick=()=>decide(b.dataset.mcno,false))}
// the new key, shown once right after "Schlüssel erzeugen" (the page is drawn again with the new connection)
function mcpKeyShow(){const k=$('mcpbox').querySelector('#mcpkey'),r=MCP_NEW;MCP_NEW=null;if(!k||!r)return;k.closest('details').open=true;
  k.innerHTML=`<div class="fh"><b>${t('Nur jetzt sichtbar:','Shown only now:')}</b> ${t('Schlüssel kopieren und im Programm eintragen.','copy the key and enter it in the program.')}</div>
    <table><tbody>${[['URL',r.url],[t('Übertragung','Transport'),'Streamable HTTP'],['Header','Authorization: Bearer '+r.token]].map(([a,b])=>`<tr><td>${esc(a)}</td><td><code>${esc(b)}</code></td></tr>`).join('')}</tbody></table>
    <div class="fh">${t('Open WebUI: Einstellungen → Externe Werkzeuge → „+“, Typ MCP (Streamable HTTP), URL und Schlüssel (Bearer). n8n: Knoten „MCP Client Tool“, Transport HTTP Streamable, Authentifizierung Bearer. Programme ohne Header-Feld: ','Open WebUI: Settings → External tools → "+", type MCP (Streamable HTTP), URL and key (Bearer). n8n: node "MCP Client Tool", transport HTTP Streamable, authentication Bearer. Programs without a header field: ')}<code>npx mcp-remote ${esc(r.url)} --header "Authorization: Bearer ${esc(r.token)}"</code></div>`;
  xmsg('mcpmsg',t('Verbunden.','Connected.'))}
// OAuth: /oauth/authorize sends the browser to /#mcpauth=<id> (start.js keeps it while signing in); the profile sees who
// asks, the warning and the tools, and answers with its code; the panel then sends the browser back to the program.
function mcpAuthStart(){let id='';try{id=sessionStorage.getItem('mcpauth')||''}catch{}if(id&&PROFILE&&MCPS_ON&&typeof openMe==='function')openMe('mcpbox')}
async function mcpAuthShow(d){const el=$('mcpauth');if(!el)return;let id='';try{id=sessionStorage.getItem('mcpauth')||''}catch{}
  if(!id||!/^[A-Za-z0-9_-]{20,48}$/.test(id)){el.innerHTML='';return}
  if(!d.on){el.innerHTML=`<div class="fh err">${t('Ein Programm möchte sich verbinden. Erst „Spark als MCP-Server für mich“ einschalten.','A program wants to connect. First switch on "Spark as MCP server for me".')}</div>`;return}
  let a;try{a=await (await api('/api/profile/mcp/oauth/'+encodeURIComponent(id))).json()}catch(e){try{sessionStorage.removeItem('mcpauth')}catch{}el.innerHTML=`<div class="fh err">${esc(e.message)}</div>`;return}
  el.innerHTML=`<div class="card" style="margin:10px 0"><h3 style="margin:0 0 6px">${t('Programm verbinden','Connect a program')}</h3>
    <div class="fh"><b>${esc(a.name)}</b> (${esc(a.host||'')}) ${t('möchte deinen Spark nutzen.','wants to use your Spark.')}</div>
    <div class="fh err">${esc(MCP_WARN())}</div>
    ${d.mfa?'':`<div class="fh err">${t('Dafür braucht dein Profil den zweiten Anmeldeschritt (Ich → Sicherheit).','For this your profile needs the second sign-in step (Me → Security).')}</div>`}
    <label>${t('Name','Name')}</label><input id="mcpaname" maxlength="60" value="${esc(a.name)}" autocomplete="off">
    ${mcpTools(a.tools,[],'mca')}
    <div class="row" style="margin-top:8px"><button class="b p" type="button" id="mcpayes"${d.mfa?'':' disabled'}>${t('Erlauben','Allow')}</button><button class="b" type="button" id="mcpano">${t('Ablehnen','Decline')}</button></div></div>`;
  const answer=async yes=>{try{const r=await (await api('/api/profile/mcp/oauth/'+encodeURIComponent(id),xjson('POST',{yes,name:$('mcpaname').value.trim(),tools:mcpPicked(el,'mca')}))).json();
      try{sessionStorage.removeItem('mcpauth')}catch{}
      if(/^https?:\/\//.test(r.redirect))location.href=r.redirect}catch(e){xmsg('mcpmsg',e.message,true)}};
  $('mcpayes').onclick=()=>answer(true);$('mcpano').onclick=()=>answer(false)}
// Apps und Schnittstellen (admin): every connection of every profile, with "Entfernen"
async function loadMcpAdmin(){const el=$('int-mcp');if(!el)return;let d;try{d=await (await api('/api/admin/mcp')).json()}catch{el.innerHTML='';return}
  if(!d.enabled){el.innerHTML=`<div class="mut">${t('Aus. Einschalten unter Funktionen → Spark als MCP-Server.','Off. Switch on under Features → Spark as MCP server.')}</div>`;return}
  el.innerHTML=`<table><tbody>${d.conns.map(c=>`<tr><td><b>${esc(c.name)}</b><br><small class="mut">${esc(c.profile)} · ${esc(mcpWhere(c.where))} · ${c.kind==='oauth'?'OAuth':t('Schlüssel','Key')} · ${c.tools.length} ${t('Werkzeuge','tools')} · ${t('zuletzt','last used')} ${esc(mcpWhen(c.last))}</small></td>
    <td><button class="b" type="button" data-mcadel="${esc(c.id)}">${t('Entfernen','Remove')}</button></td></tr>`).join('')||`<tr><td class="mut">${t('Noch kein Programm verbunden.','No program connected yet.')}</td></tr>`}</tbody></table>`;
  el.querySelectorAll('[data-mcadel]').forEach(b=>b.onclick=async()=>{if(!confirm(t('Zugang entfernen? Er gilt dann sofort nicht mehr.','Remove the access? It stops working at once.')))return;
    try{await api('/api/admin/mcp/'+encodeURIComponent(b.dataset.mcadel),{method:'DELETE'});loadMcpAdmin()}catch(e){alert(e.message)}})}
