// "Ich → Meine MCP-Dienste" (meinmcp.py, V01.0.363): a profile connects its own MCP services. Every tool is off until
// the profile sets it to "Lesen" or "Handeln mit Ja"; adding a service, a new address or a new key asks for a fresh code.
// The key never comes back. Apps und Schnittstellen (admin): every profile's services, block or remove, allowed hosts.
let MYMCP_ON=false;
const MYM_MODE=[['off','Aus','Off'],['read','Lesen','Read'],['act','Handeln mit Ja','Act after yes']];
const MYM_WHY={gesperrt:['Vom Admin gesperrt','Blocked by the admin'],nicht_erlaubt:['Adresse vom Admin nicht freigegeben','Address not allowed by the admin'],
  anmeldung:['Anmeldung beim Dienst nötig','Sign-in at the service needed']};
const mymWhen=x=>x?new Date(x*1000).toLocaleString([], {dateStyle:'short',timeStyle:'short'}):t('noch nie','never');
const MYM_WARN=()=>t('Was du einen Dienst fragen lässt, geht an diesen Dienst und dessen Anbieter. Antworten eines Dienstes sind fremder Text: danach schaltet und speichert der Assistent in derselben Antwort nichts mehr.',
  'What you let the assistant ask a service goes to that service and its provider. A service\'s answers are outside text: after one the assistant switches and saves nothing more in that answer.');
async function showMyMcp(){const box=$('mymcpbox');if(!box)return;if(!PROFILE||!MYMCP_ON){box.innerHTML='';return}
  let d;try{d=await (await api('/api/profile/mymcp')).json()}catch{box.innerHTML='';return}
  const svc=s=>`<li><span><b>${esc(s.name)}</b> <small class="mut">${esc(s.host)}</small>${s.why?` <small class="ftag out">${esc(t(...(MYM_WHY[s.why]||['?','?'])))}</small>`:''}<br>
      <small class="mut">${s.oauth?t('angemeldet (OAuth)','signed in (OAuth)'):s.has_key?t('mit Schlüssel','with key'):t('ohne Schlüssel','without key')} · ${s.tools.length} ${t('Werkzeuge','tools')} · ${t('abgerufen','fetched')} ${esc(mymWhen(s.checked))}</small>
      ${s.login&&d.oauth?`<div class="row" style="margin-top:6px"><button class="b p" type="button" data-mymlogin="${esc(s.id)}">${t('Beim Dienst anmelden','Sign in at the service')}</button></div>`:''}
      <details><summary>${t('Werkzeuge freigeben','Release tools')}</summary>
        <table class="mymt"><tbody>${s.tools.map(x=>`<tr><td><b>${esc(x.name)}</b>${x.desc?`<br><small class="mut">${esc(x.desc)}</small>`:''}</td>
          <td><select data-mymode="${esc(s.id)}" data-mymtool="${esc(x.name)}">${MYM_MODE.map(([k,de,en])=>`<option value="${k}"${x.mode===k?' selected':''}>${esc(t(de,en))}</option>`).join('')}</select></td></tr>`).join('')
          ||`<tr><td class="mut">${t('Keine Werkzeuge (erst anmelden oder neu abrufen).','No tools (sign in or fetch again first).')}</td></tr>`}</tbody></table>
        ${d.jobs?`<label class="chk"><input type="checkbox" data-mymjobs="${esc(s.id)}"${s.jobs?' checked':''}> ${t('Lesende Werkzeuge auch in Hintergrundaufträgen','Reading tools also in background jobs')}</label>`:''}
        <div class="row"><button class="b p" type="button" data-mymsave="${esc(s.id)}">${t('Speichern','Save')}</button><button class="b" type="button" data-mymref="${esc(s.id)}">${t('Werkzeuge neu abrufen','Fetch tools again')}</button></div></details>
      <details><summary>${t('Adresse oder Schlüssel ändern','Change address or key')}</summary>
        <label>${t('Adresse','Address')}</label><input data-mymurl="${esc(s.id)}" value="${esc(s.url)}" maxlength="300" autocomplete="off">
        <label>${t('Neuer Schlüssel (leer: keiner)','New key (empty: none)')}</label><input type="password" data-mymkey="${esc(s.id)}" maxlength="2000" autocomplete="new-password">
        <div class="fh">${t('Eine neue Adresse braucht immer einen neuen Schlüssel; alle Werkzeuge stehen dann wieder auf „Aus“.','A new address always needs a new key; all tools are "Off" again then.')}</div>
        <div class="row"><button class="b" type="button" data-mymnew="${esc(s.id)}">${t('Übernehmen','Apply')}</button></div></details></span>
      <button class="b" type="button" data-mymdel="${esc(s.id)}" data-mymname="${esc(s.name)}">${t('Entfernen','Remove')}</button></li>`;
  box.innerHTML=`<div class="intro">${t('Binde eigene Dienste an, die das Model Context Protocol sprechen (z. B. dein Paperless, Nextcloud oder ein eigener Dienst). Nur du siehst und nutzt sie. Jedes Werkzeug ist aus, bis du es auf „Lesen“ oder „Handeln mit Ja“ stellst; handelnde Werkzeuge schlägt der Assistent nur vor und führt sie erst nach deinem Ja aus.','Connect your own services that speak the Model Context Protocol (e.g. your Paperless, Nextcloud or a service of your own). Only you see and use them. Every tool is off until you set it to "Read" or "Act after yes"; acting tools are only proposed and run after your yes.')}</div>
    ${xsw('mymcp_on',t('Eigene MCP-Dienste für mich','Own MCP services for me'),t('Aus: Der Assistent fragt keinen deiner Dienste mehr, sofort.','Off: the assistant asks none of your services any more, at once.'))}
    <div class="fh" id="mymback" role="status"></div>
    ${d.on?`<div class="fh err">${esc(MYM_WARN())}</div>
    <h3 style="margin:14px 0 4px">${t('Meine Dienste','My services')}</h3><ul class="facts">${d.services.map(svc).join('')||`<li class="mut"><span>${t('Noch kein Dienst angebunden.','No service connected yet.')}</span></li>`}</ul>
    ${d.services.length<d.max?`<details style="margin-top:10px"${d.services.length?'':' open'}><summary>${t('Dienst anbinden','Connect a service')}</summary>
      <label>${t('Name','Name')}</label><input id="mymname" maxlength="40" placeholder="${esc(t('z. B. Paperless','e.g. Paperless'))}" autocomplete="off">
      <label>${t('Adresse (Streamable HTTP)','Address (Streamable HTTP)')}</label><input id="mymurl" maxlength="300" placeholder="https://…/mcp" autocomplete="off">
      <label>${t('Schlüssel (falls der Dienst einen will)','Key (if the service wants one)')}</label><input type="password" id="mymkey" maxlength="2000" autocomplete="new-password">
      <div class="fh">${d.oauth?t('Will der Dienst eine Anmeldung, Schlüssel leer lassen: danach erscheint „Beim Dienst anmelden“.','If the service wants a sign-in, leave the key empty: "Sign in at the service" appears afterwards.'):''}
        ${d.lan?'':t(' Adressen im Heimnetz sind vom Admin ausgeschaltet.',' Addresses in the home network are switched off by the admin.')}
        ${d.hosts.length?t(' Erlaubt sind nur: ',' Only allowed: ')+esc(d.hosts.join(', ')):''}</div>
      <div class="row" style="margin-top:8px"><button class="b p" type="button" id="mymadd">${t('Dienst anbinden','Connect service')}</button></div>
      <div class="fh" id="mymaddmsg" role="status"></div></details>`:`<div class="fh">${t('Höchstens ','At most ')+d.max+t(' eigene Dienste.',' own services.')}</div>`}`
    :d.why==='mfa'?`<div class="fh err">${esc(t('Erst den zweiten Anmeldeschritt einrichten (Ich → Sicherheit).','Set up the second sign-in step first (Me → Security).'))}</div>`:''}
    <div class="fh" id="mymmsg"></div>`;
  xbind(box,showMyMcp);
  const say=(id,x,err)=>{xmsg(id,x,err);const m=$(id);if(m)m.scrollIntoView({block:'nearest'})};
  const codeErr=e=>/code required|Code/i.test(e.message||'')?t('Ohne deinen Code geht es nicht: bitte noch einmal tippen und den Code eingeben.','Not without your code: tap again and enter your code.'):e.message;
  if($('mymadd'))$('mymadd').onclick=async()=>{const b=$('mymadd'),name=$('mymname').value.trim(),url=$('mymurl').value.trim();
    if(!name){say('mymaddmsg',t('Bitte zuerst einen Namen eingeben.','Please enter a name first.'),true);$('mymname').focus();return}
    if(!/^https?:\/\//.test(url)){say('mymaddmsg',t('Bitte die Adresse mit https:// eingeben.','Please enter the address with https://.'),true);$('mymurl').focus();return}
    b.disabled=true;say('mymaddmsg',t('Frage den Dienst nach seinen Werkzeugen …','Asking the service for its tools …'));
    try{const r=await (await api('/api/profile/mymcp',xjson('POST',{name,url,token:$('mymkey').value.trim()}))).json();await showMyMcp();
      xmsg('mymmsg',r.login?t('Angebunden. Jetzt „Beim Dienst anmelden“ tippen.','Connected. Now tap "Sign in at the service".'):t('Angebunden. Alle Werkzeuge stehen auf „Aus“: unter „Werkzeuge freigeben“ einzeln einschalten.','Connected. All tools are "Off": switch them on one by one under "Release tools".'))}
    catch(e){b.disabled=false;say('mymaddmsg',codeErr(e),true)}};
  box.querySelectorAll('[data-mymsave]').forEach(b=>b.onclick=async()=>{const id=b.dataset.mymsave,tools={};
    box.querySelectorAll(`[data-mymode="${id}"]`).forEach(x=>tools[x.dataset.mymtool]=x.value);
    const j=box.querySelector(`[data-mymjobs="${id}"]`),body={tools};if(j)body.jobs=j.checked;
    try{await api('/api/profile/mymcp/'+encodeURIComponent(id),xjson('PUT',body));await showMyMcp();xmsg('mymmsg',t('Gespeichert.','Saved.'))}catch(e){say('mymmsg',e.message,true)}});
  box.querySelectorAll('[data-mymnew]').forEach(b=>b.onclick=async()=>{const id=b.dataset.mymnew,u=box.querySelector(`[data-mymurl="${id}"]`).value.trim(),k=box.querySelector(`[data-mymkey="${id}"]`).value.trim();
    try{await api('/api/profile/mymcp/'+encodeURIComponent(id),xjson('PUT',{url:u,token:k}));await showMyMcp();xmsg('mymmsg',t('Übernommen.','Applied.'))}catch(e){say('mymmsg',codeErr(e),true)}});
  box.querySelectorAll('[data-mymref]').forEach(b=>b.onclick=async()=>{try{await api('/api/profile/mymcp/'+encodeURIComponent(b.dataset.mymref)+'/refresh',{method:'POST'});await showMyMcp();
    xmsg('mymmsg',t('Neu abgerufen. Geänderte Werkzeuge stehen wieder auf „Aus“.','Fetched again. Changed tools are "Off" again.'))}catch(e){say('mymmsg',e.message,true)}});
  box.querySelectorAll('[data-mymdel]').forEach(b=>b.onclick=async()=>{if(!confirm(t('„','"')+b.dataset.mymname+t('“ entfernen?','" remove?')))return;
    try{await api('/api/profile/mymcp/'+encodeURIComponent(b.dataset.mymdel),{method:'DELETE'});showMyMcp()}catch(e){say('mymmsg',e.message,true)}});
  box.querySelectorAll('[data-mymlogin]').forEach(b=>b.onclick=async()=>{try{const r=await (await api('/api/profile/mymcp/'+encodeURIComponent(b.dataset.mymlogin)+'/oauth/start',{method:'POST'})).json();
    if(/^https?:\/\//.test(r.go||''))location.href=r.go}catch(e){say('mymmsg',codeErr(e),true)}});
  mymBackFinish()}
// the service sent the browser back (/api/mymcp/back → /#mymcpback=<state>.<code>, start.js keeps it): finish the sign-in
async function mymBackFinish(){let v='';try{v=sessionStorage.getItem('mymcpback')||'';sessionStorage.removeItem('mymcpback')}catch{}if(!v)return;
  const i=v.indexOf('.');if(v==='error'||i<20){xmsg('mymback',t('Die Anmeldung beim Dienst ist nicht gelungen.','The sign-in at the service did not work.'),true);return}
  xmsg('mymback',t('Anmeldung wird abgeschlossen …','Finishing the sign-in …'));
  try{await api('/api/profile/mymcp/oauth/finish',xjson('POST',{state:v.slice(0,i),code:decodeURIComponent(v.slice(i+1))}));await showMyMcp();
    xmsg('mymmsg',t('Angemeldet. Alle Werkzeuge stehen auf „Aus“: unter „Werkzeuge freigeben“ einzeln einschalten.','Signed in. All tools are "Off": switch them on one by one under "Release tools".'))}
  catch(e){xmsg('mymback',e.message,true)}}
function mymBackStart(){let v='';try{v=sessionStorage.getItem('mymcpback')||''}catch{}if(v&&PROFILE&&MYMCP_ON&&typeof openMe==='function')openMe('mymcpbox')}
// Apps und Schnittstellen (admin): every profile's own services (never a key), block or remove at once, allowed hosts
async function loadMyMcpAdmin(){const el=$('int-mymcp');if(!el)return;let d;try{d=await (await api('/api/admin/mymcp')).json()}catch{el.innerHTML='';return}
  if(!d.enabled){el.innerHTML=`<div class="mut">${t('Aus. Einschalten unter Funktionen → Agent-Funktionen → Dienste per MCP → Eigene MCP-Dienste für Profile.','Off. Switch on under Features → Agent functions → Services over MCP → Own MCP services for profiles.')}</div>`;return}
  el.innerHTML=`<table><tbody>${d.services.map(s=>`<tr><td><b>${esc(s.name)}</b> <small class="mut">${esc(s.host)}</small>${s.why?` <small class="ftag out">${esc(t(...(MYM_WHY[s.why]||['?','?'])))}</small>`:''}<br>
      <small class="mut">${esc(s.profile)} · ${s.released} ${t('Werkzeuge frei','tools released')}${s.acts?' ('+s.acts+' '+t('handelnd','acting')+')':''} · ${s.oauth?'OAuth':t('Schlüssel oder offen','key or open')}${s.jobs?' · '+t('in Aufträgen','in jobs'):''} · ${t('abgerufen','fetched')} ${esc(mymWhen(s.checked))}</small></td>
      <td><span class="row"><button class="b" type="button" data-mymablock="${esc(s.uid)}|${esc(s.sid)}" data-mymaval="${s.blocked?'0':'1'}">${s.blocked?t('Erlauben','Allow'):t('Sperren','Block')}</button>
      <button class="b" type="button" data-mymadel="${esc(s.uid)}|${esc(s.sid)}">${t('Entfernen','Remove')}</button></span></td></tr>`).join('')||`<tr><td class="mut">${t('Noch kein Profil hat einen eigenen Dienst angebunden.','No profile has connected an own service yet.')}</td></tr>`}</tbody></table>
    <label>${t('Erlaubte Adressen (eine pro Zeile, leer: alle öffentlichen)','Allowed hosts (one per line, empty: every public one)')}</label><textarea id="mymahosts" rows="3" maxlength="2000">${esc(d.hosts.join('\n'))}</textarea>
    <div class="row"><button class="b" type="button" id="mymahsave">${t('Speichern','Save')}</button></div><div class="fh" id="mymamsg"></div>`;
  const path=v=>v.split('|').map(encodeURIComponent).join('/');
  el.querySelectorAll('[data-mymablock]').forEach(b=>b.onclick=async()=>{try{await api('/api/admin/mymcp/'+path(b.dataset.mymablock),xjson('PUT',{blocked:b.dataset.mymaval==='1'}));loadMyMcpAdmin()}catch(e){xmsg('mymamsg',e.message,true)}});
  el.querySelectorAll('[data-mymadel]').forEach(b=>b.onclick=async()=>{if(!confirm(t('Dienst dieses Profils entfernen?','Remove this profile\'s service?')))return;
    try{await api('/api/admin/mymcp/'+path(b.dataset.mymadel),{method:'DELETE'});loadMyMcpAdmin()}catch(e){xmsg('mymamsg',e.message,true)}});
  $('mymahsave').onclick=async()=>{const hosts=$('mymahosts').value.split(/[\s,]+/).map(x=>x.trim()).filter(Boolean);
    try{await api('/api/admin/mymcp/hosts',xjson('PUT',{hosts}));await loadMyMcpAdmin();xmsg('mymamsg',t('Gespeichert.','Saved.'))}catch(e){xmsg('mymamsg',e.message,true)}}}
