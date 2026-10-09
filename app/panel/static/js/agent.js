// "Ich" → Aufträge and the admin's part (agent.py, mcp.py): background jobs, scheduled jobs, routines and
// outside tools over MCP. Off until the admin gives the profile a level and the profile switches it on.
let AGENT_ON=false;
const AG_ST={queued:['wartet','waiting'],running:['läuft','running'],done:['fertig','done'],failed:['ging nicht','failed'],cancelled:['abgebrochen','cancelled']};
const AG_REP=[['daily','jeden Tag','every day'],['weekdays','werktags','on weekdays'],['weekly','jede Woche','every week'],['monthly','jeden Monat','every month'],['once','einmal','once']];
const AG_DAYS=[['Montag','Monday'],['Dienstag','Tuesday'],['Mittwoch','Wednesday'],['Donnerstag','Thursday'],['Freitag','Friday'],['Samstag','Saturday'],['Sonntag','Sunday']];
const agTime=s=>s?new Date(s*1000).toLocaleString(L==='en'?'en-GB':'de-DE',{day:'2-digit',month:'2-digit',hour:'2-digit',minute:'2-digit'}):'';
let agTimer=null;
async function showAgent(){const box=$('agentbox');if(!box)return;clearTimeout(agTimer);if(!PROFILE||!AGENT_ON){box.innerHTML='';return}
  let d;try{d=await (await api('/api/profile/agent')).json()}catch{box.innerHTML='';return}
  const lvl={read:t('nur lesen und berichten','read and report only'),act:t('auch handeln mit „Ja“','also act after "Yes"')}[d.granted]||t('nichts','nothing');
  const on=!!S.agent_on,act=d.granted==='act';
  const jobs=d.jobs.map(j=>`<li><span><b>${esc(t(...(AG_ST[j.state]||['?','?'])))}</b> · ${esc(j.task)}<br><small class="mut">${esc(agTime(j.created))}${j.origin==='plan'?t(' · geplant',' · scheduled'):''}${j.doc_name?' · '+esc(j.doc_name):''}</small>
      ${j.summary?`<br><small>${esc(j.summary)}</small>`:''}${j.error?`<br><small class="err">${esc(j.error)}</small>`:''}${j.doc_error?`<br><small class="err">${esc(j.doc_error)}</small>`:''}
      ${j.state==='running'&&j.steps.length?`<br><small class="mut">${esc(j.steps[j.steps.length-1])}</small>`:''}<div class="agrep" data-agrep="${esc(j.id)}" hidden></div></span>
      <span class="row">${j.state==='done'?`<button class="b" type="button" data-agshow="${esc(j.id)}">${t('Bericht','Report')}</button>`:''}
      ${j.state==='done'&&!j.doc_name?`<button class="b" type="button" data-agdoc="${esc(j.id)}">${t('Als Dokument','As document')}</button>`:''}
      ${j.state==='queued'||j.state==='running'?`<button class="b" type="button" data-agstop="${esc(j.id)}">${t('Abbrechen','Cancel')}</button>`:`<button class="b" type="button" data-agdel="${esc(j.id)}">${t('Löschen','Delete')}</button>`}</span></li>`).join('')
    ||`<li class="mut">${t('Noch keine Aufträge.','No jobs yet.')}</li>`;
  const plans=d.plans.map(p=>`<li><span>${esc(p.text)}<br><small class="mut">${p.paused?t('pausiert','paused'):t('nächstes Mal ','next time ')+esc(agTime(p.next))}</small></span>
      <span class="row"><button class="b" type="button" data-agpause="${esc(p.id)}">${p.paused?t('Fortsetzen','Resume'):t('Pausieren','Pause')}</button><button class="b" type="button" data-agpdel="${esc(p.id)}">${t('Löschen','Delete')}</button></span></li>`).join('')
    ||`<li class="mut">${t('Keine geplanten Aufträge.','No scheduled jobs.')}</li>`;
  const routines=d.routines.map(r=>`<li><span><b>${esc(r.name)}</b><br><small class="mut">${r.steps.map((s,i)=>esc((i+1)+'. '+s)).join('<br>')}</small></span>
      <button class="b" type="button" data-agrdel="${esc(r.id)}">${t('Löschen','Delete')}</button></li>`).join('')||`<li class="mut">${t('Noch keine Abläufe.','No routines yet.')}</li>`;
  box.innerHTML=`<div class="intro">${t('Gib dem Assistenten längere Aufgaben: „Recherchiere, welche Wärmepumpe zum Pool passt, und sag mir dann Bescheid.“ Er arbeitet im Hintergrund, liest nur und meldet sich per Mitteilung und Telegram (wie unter Mitteilungen und Telegram eingestellt). Ein Auftrag läuft nach dem anderen; Gespräche mit dir haben Vorrang. Der Admin hat dir freigegeben: ','Give the assistant longer tasks: "Research which heat pump fits the pool and let me know." It works in the background, only reads and reports by notification and Telegram (as set under Notifications and Telegram). One job runs after the other; talking to you comes first. The admin allowed you: ')}<b>${esc(lvl)}</b>.</div>
    ${xsw('agent_on',t('Agent-Funktionen für mich nutzen','Use agent functions for me'),act?t('Aufträge, geplante Aufträge, Abläufe und freigegebene Dienste.','Jobs, scheduled jobs, routines and allowed services.'):t('Aufträge, geplante Aufträge und freigegebene Dienste (nur lesend).','Jobs, scheduled jobs and allowed services (read only).'))}
    ${on?xsw('agent_doc',t('Jeden Bericht auch unter „Dokumente“ ablegen','Also keep every report under "Documents"'),t('Dann findet der Assistent ihn später wieder („Was stand im Bericht zur Wärmepumpe?“).','Then the assistant finds it again later ("What did the heat pump report say?").')):''}
    ${on?`<h3 style="margin:14px 0 4px">${t('Neuer Auftrag','New job')}</h3>
    ${d.search?'':`<div class="fh">${t('Die Websuche ist aus: Aufträge lesen dann nur deine eigenen Daten (Kalender, Erinnerungen, Dokumente).','Web search is off: jobs then only read your own data (calendar, reminders, documents).')}</div>`}
    <textarea id="agtask" rows="2" maxlength="500" placeholder="${esc(t('z. B. Vergleich die drei günstigsten Flüge nach Rom im November','e.g. Compare the three cheapest flights to Rome in November'))}"></textarea>
    <div class="row" style="margin-top:6px"><label class="chk" style="margin:0"><input type="checkbox" id="agdoc"> ${t('Bericht auch als Dokument','Report also as a document')}</label><button class="b p" type="button" id="aggo">${t('Auftrag starten','Start job')}</button></div>
    <div class="fh">${t('Höchstens ','At most ')+d.day_max+t(' Aufträge am Tag, drei warten gleichzeitig. Per Sprache: „Recherchiere …“, „Finde heraus …“, „Was laufen für Aufträge?“',' jobs a day, three wait at once. By voice: "Research …", "Find out …", "Which jobs are running?"')}</div>
    <h3 style="margin:14px 0 4px">${t('Aufträge','Jobs')}</h3><ul class="facts">${jobs}</ul>
    <h3 style="margin:14px 0 4px">${t('Geplante Aufträge','Scheduled jobs')}</h3><ul class="facts">${plans}</ul>
    <details><summary>${t('Geplanten Auftrag anlegen','Add a scheduled job')}</summary>
      <input id="agptask" maxlength="500" placeholder="${esc(t('z. B. Fass mir die Termine der Woche zusammen','e.g. Summarize my appointments of the week'))}">
      <div class="row" style="margin-top:6px"><select id="agprep">${AG_REP.map(([k,de,en])=>`<option value="${k}">${esc(t(de,en))}</option>`).join('')}</select>
        <select id="agpwd">${AG_DAYS.map(([de,en],i)=>`<option value="${i}">${esc(t(de,en))}</option>`).join('')}</select>
        <input id="agpday" type="number" min="1" max="28" value="1" style="width:5em"><input id="agpdate" type="date"><input id="agptime" type="time" value="07:00"></div>
      <div class="row" style="margin-top:6px"><label class="chk" style="margin:0"><input type="checkbox" id="agpdoc"> ${t('Bericht auch als Dokument','Report also as a document')}</label><button class="b" type="button" id="agpadd">${t('Planen','Schedule')}</button></div>
      <div class="fh">${t('Per Sprache: „Fass mir jeden Montag um 7 die Termine der Woche zusammen.“ Gespeichert wird erst nach deinem „Ja“.','By voice: "Summarize my week\'s appointments every Monday at 7." It is saved only after your "Yes".')}</div></details>
    ${act?`<h3 style="margin:14px 0 4px">${t('Abläufe','Routines')}</h3>${d.ha?'':`<div class="fh">${t('Abläufe schalten über Home Assistant: erst unter Smart Home verbinden.','Routines switch through Home Assistant: connect it under Smart home first.')}</div>`}
    <ul class="facts">${routines}</ul>
    <details><summary>${t('Ablauf anlegen','Add a routine')}</summary>
      <input id="agrname" maxlength="40" placeholder="${esc(t('Name, z. B. Feierabend','Name, e.g. Evening'))}">
      <textarea id="agrsteps" rows="3" placeholder="${esc(t('Ein Befehl pro Zeile, z. B.\nSchalte das Licht im Flur aus\nFahr die Rollläden im Wohnzimmer runter','One command per line, e.g.\nTurn off the hall light\nClose the living room blinds'))}"></textarea>
      <div class="row" style="margin-top:6px"><button class="b" type="button" id="agradd">${t('Ablauf speichern','Save routine')}</button></div>
      <div class="fh">${t('Starten: nur den Namen sagen („Feierabend“). Jeder Schritt läuft wie ein gesprochener Befehl, mit deinem Codewort, falls du eins hast. Per Sprache anlegen: „Merk dir als Feierabend: Licht im Flur aus, Rollläden runter.“','Start: just say the name ("Evening"). Each step runs like a spoken command, with your code word if you have one. By voice: "Remember as Evening: hall light off, blinds down."')}</div></details>`:''}
    ${d.servers.length?`<h3 style="margin:14px 0 4px">${t('Freigegebene Dienste','Allowed services')}</h3><ul class="facts">${d.servers.map(s=>`<li><span><b>${esc(s.name)}</b><br><small class="mut">${esc(s.tools.join(', ')||t('keine Werkzeuge','no tools'))}</small></span></li>`).join('')}</ul>`:''}`:''}
    <div class="fh" id="agmsg"></div>`;
  xbind(box,showAgent);
  const call=async(p,o)=>{try{await api(p,o);await showAgent()}catch(e){xmsg('agmsg',e.message,true)}};
  if($('aggo'))$('aggo').onclick=()=>{const v=$('agtask').value.trim();if(!v)return;call('/api/profile/agent/jobs',xjson('POST',{task:v,doc:$('agdoc').checked}))};
  box.querySelectorAll('[data-agstop]').forEach(b=>b.onclick=()=>call('/api/profile/agent/jobs/'+encodeURIComponent(b.dataset.agstop)+'/cancel',xjson('POST')));
  box.querySelectorAll('[data-agdel]').forEach(b=>b.onclick=()=>call('/api/profile/agent/jobs/'+encodeURIComponent(b.dataset.agdel),{method:'DELETE'}));
  box.querySelectorAll('[data-agdoc]').forEach(b=>b.onclick=()=>call('/api/profile/agent/jobs/'+encodeURIComponent(b.dataset.agdoc)+'/doc',xjson('POST')));
  box.querySelectorAll('[data-agshow]').forEach(b=>b.onclick=async()=>{const el=box.querySelector(`[data-agrep="${CSS.escape(b.dataset.agshow)}"]`);
    if(!el.hidden){el.hidden=true;return}
    try{const j=await (await api('/api/profile/agent/jobs/'+encodeURIComponent(b.dataset.agshow))).json();el.textContent=j.report||'';el.hidden=false}catch(e){xmsg('agmsg',e.message,true)}});
  box.querySelectorAll('[data-agpause]').forEach(b=>b.onclick=()=>call('/api/profile/agent/plans/'+encodeURIComponent(b.dataset.agpause)+'/pause',xjson('POST')));
  box.querySelectorAll('[data-agpdel]').forEach(b=>b.onclick=()=>call('/api/profile/agent/plans/'+encodeURIComponent(b.dataset.agpdel),{method:'DELETE'}));
  box.querySelectorAll('[data-agrdel]').forEach(b=>b.onclick=()=>{if(confirm(t('Ablauf löschen?','Delete the routine?')))call('/api/profile/agent/routines/'+encodeURIComponent(b.dataset.agrdel),{method:'DELETE'})});
  const rep=$('agprep');if(rep){const vis=()=>{$('agpwd').hidden=rep.value!=='weekly';$('agpday').hidden=rep.value!=='monthly';$('agpdate').hidden=rep.value!=='once'};rep.onchange=vis;vis()}
  if($('agpadd'))$('agpadd').onclick=()=>call('/api/profile/agent/plans',xjson('POST',{task:$('agptask').value,repeat:rep.value,time:$('agptime').value,weekday:+$('agpwd').value,day:+$('agpday').value,date:$('agpdate').value,doc:$('agpdoc').checked}));
  if($('agradd'))$('agradd').onclick=()=>call('/api/profile/agent/routines',xjson('POST',{name:$('agrname').value,steps:$('agrsteps').value.split('\n')}));
  // while a job waits or runs, the page looks again now and then
  if(d.jobs.some(j=>j.state==='queued'||j.state==='running'))agTimer=setTimeout(()=>{if(box.offsetParent)showAgent()},10000)}

// ---------------------------------------------------------------- admin: who may, and the MCP services
const AG_LV=[['','aus','off'],['read','nur lesen und berichten','read and report only'],['act','auch handeln mit „Ja“','also act after "Yes"']];
const AG_MODE=[['off','aus','off'],['read','lesen','read'],['act','handeln (mit „Ja“)','act (after "Yes")']];
async function agentAdmin(){const box=$('agentadmin');if(!box)return;let d;try{d=await (await api('/api/admin/agent')).json()}catch{return}
  box.innerHTML=`<div class="fh">${t('Pro Profil, was es darf. Das Profil schaltet es danach selbst ein (Ich → Aufträge). Gäste nie.','Per profile, what it may do. The profile then switches it on itself (Me → Jobs). Never guests.')}</div>
    <table><tbody>${d.users.map(u=>`<tr><td>${esc(u.name)}${u.on?` <small class="mut">${t('(eingeschaltet)','(switched on)')}</small>`:''}</td>
      <td><select data-aglv="${esc(u.id)}">${AG_LV.map(([k,de,en])=>`<option value="${k}"${u.level===k?' selected':''}>${esc(t(de,en))}</option>`).join('')}</select></td></tr>`).join('')
      ||`<tr><td class="mut">${t('Noch keine Profile.','No profiles yet.')}</td></tr>`}</tbody></table>
    <div class="row" style="margin-top:6px"><button class="b" type="button" id="aglvsave">${t('Freigaben speichern','Save permissions')}</button><span class="mut" id="aglvmsg"></span></div>`;
  $('aglvsave').onclick=async()=>{const levels={};box.querySelectorAll('[data-aglv]').forEach(s=>{if(s.value)levels[s.dataset.aglv]=s.value});
    try{await api('/api/admin/agent/levels',xjson('PUT',{levels}));$('aglvmsg').textContent=t('Gespeichert.','Saved.')}catch(e){$('aglvmsg').textContent=e.message}};
  const mb=$('mcpadmin');if(!mb)return;
  mb.innerHTML=`<div class="fh">${t('Dienste, die das MCP-Protokoll über HTTP sprechen (z. B. Paperless, Nextcloud, GitHub). Jedes Werkzeug ist aus, bis du es freigibst: „lesen“ für Profile ab „nur lesen“, „handeln“ nur für „auch handeln“ und erst nach dem „Ja“ der Person. Der Spark startet nie selbst ein Programm. Adressen im Heimnetz nur mit „Heimnetz-Adressen erlauben“ (Sicherheit).','Services that speak MCP over HTTP (e.g. Paperless, Nextcloud, GitHub). Every tool is off until you allow it: "read" for profiles from "read only", "act" only for "also act" and only after the person\'s "Yes". The Spark never starts a program itself. Home network addresses only with "Allow home network addresses" (Security).')}</div>
    ${d.servers.map(s=>`<div class="card" style="margin:8px 0;padding:10px" data-mcp="${esc(s.id)}"><b>${esc(s.name)}</b> <small class="mut">${esc(s.url)}${s.has_token?t(' · mit Token',' · with token'):''}</small>
      <div class="fh">${t('Profile, die den Dienst nutzen dürfen:','Profiles that may use the service:')} ${d.users.map(u=>`<label class="chk" style="display:inline-flex;margin:0 8px 0 0"><input type="checkbox" data-mcpuser="${esc(u.id)}"${s.users.includes(u.id)?' checked':''}> ${esc(u.name)}</label>`).join('')}</div>
      <table><tbody>${s.tools.map(x=>`<tr><td><b>${esc(x.name)}</b><br><small class="mut">${esc(x.desc)}</small></td><td><select data-mcptool="${esc(x.name)}">${AG_MODE.map(([k,de,en])=>`<option value="${k}"${x.mode===k?' selected':''}>${esc(t(de,en))}</option>`).join('')}</select></td></tr>`).join('')
        ||`<tr><td class="mut">${t('Der Dienst bietet keine Werkzeuge an.','The service offers no tools.')}</td></tr>`}</tbody></table>
      <div class="row" style="margin-top:6px"><button class="b" type="button" data-mcpsave>${t('Speichern','Save')}</button><button class="b" type="button" data-mcprefresh>${t('Werkzeuge neu abfragen','Fetch tools again')}</button><button class="b" type="button" data-mcpdel>${t('Entfernen','Remove')}</button></div></div>`).join('')}
    <label>${t('Name','Name')}</label><input id="mcpname" maxlength="40" placeholder="Paperless">
    <label>${t('Adresse','Address')}</label><input id="mcpurl" autocapitalize="off" autocomplete="off" placeholder="https://paperless.example.de/mcp">
    <label>${t('Token (optional)','Token (optional)')}</label><input id="mcptoken" type="password" autocomplete="off">
    <div class="row" style="margin-top:6px"><button class="b" type="button" id="mcpadd">${t('Verbinden und Werkzeuge abfragen','Connect and fetch tools')}</button><span class="mut" id="mcpmsg"></span></div>`;
  const run=async(p,o)=>{$('mcpmsg').textContent=t('Einen Moment …','One moment …');try{await api(p,o);await agentAdmin()}catch(e){$('mcpmsg').textContent=e.message}};
  $('mcpadd').onclick=()=>run('/api/admin/agent/mcp',xjson('POST',{name:$('mcpname').value,url:$('mcpurl').value.trim(),token:$('mcptoken').value.trim()}));
  mb.querySelectorAll('[data-mcp]').forEach(c=>{const id=encodeURIComponent(c.dataset.mcp);
    c.querySelector('[data-mcpsave]').onclick=()=>{const tools={};c.querySelectorAll('[data-mcptool]').forEach(s=>tools[s.dataset.mcptool]=s.value);
      run('/api/admin/agent/mcp/'+id,xjson('PUT',{tools,users:[...c.querySelectorAll('[data-mcpuser]')].filter(x=>x.checked).map(x=>x.dataset.mcpuser)}))};
    c.querySelector('[data-mcprefresh]').onclick=()=>run('/api/admin/agent/mcp/'+id+'/refresh',xjson('POST'));
    c.querySelector('[data-mcpdel]').onclick=()=>{if(confirm(t('Dienst entfernen? Das Token wird gelöscht.','Remove the service? The token is deleted.')))run('/api/admin/agent/mcp/'+id,{method:'DELETE'})}})}
