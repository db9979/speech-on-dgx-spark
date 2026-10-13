// "Ich → Speicher → Meine NAS" (nas.py, plan synology-bauplan.md S1): one connection per NAS (address, kind, user,
// password, accepted certificate or server key), used by Eigener Speicher and later by the Wissensordner and the
// Ablage. Adding one or changing its login asks for a code; the password never comes back; a certificate that does
// not fit is accepted only by its fingerprint. Everything from the server is text (esc).
let NAS_ON=false;
const NAS_WHY={offline:['nicht erreichbar','not reachable'],auth:['Anmeldung abgelehnt','sign-in refused'],cert:['Zertifikat passt nicht','certificate does not fit'],
  hostkey:['Schlüssel des Servers hat sich geändert','the server\'s key changed'],blocked:['vom Wächter nicht erlaubt','not allowed by the Wächter'],notaus:['Notaus','kill switch'],other:['antwortet nicht wie erwartet','does not answer as expected']};
const NAS_KIND={webdav:['WebDAV (https)','WebDAV (https)'],smb:['SMB-Freigabe (Heimnetz)','SMB share (home network)'],sftp:['SFTP (SSH)','SFTP (SSH)']};
const NAS_HINT={webdav:['https://nas.fritz.box:5006','Synology: Paket „WebDAV Server“, HTTPS-Port 5006. Nur Adresse und Port, ohne Ordner.','Synology: package "WebDAV Server", HTTPS port 5006. Only address and port, no folder.'],
  smb:['smb://nas.fritz.box','Nur im Heimnetz und nur verschlüsselt (SMB 3). Nur die Adresse, die Freigabe kommt bei der Nutzung.','Only at home and only encrypted (SMB 3). Only the address, the share comes with the use.'],
  sftp:['sftp://nas.fritz.box','SSH am NAS einschalten. Der Schlüssel des Servers wird beim Verbinden gemerkt.','Turn on SSH on the NAS. The server\'s key is remembered when connecting.']};
const NAS_USE={speicher:['Eigener Speicher','Own storage'],sicherung:['Sicherung','Backup']};
const nasWhy=k=>t(...(NAS_WHY[k]||NAS_WHY.other));
let NAS_LIST=[];
function nasState(x){const c=x.checked;if(!c)return ['',t('noch nicht geprüft','not checked yet')];
  return c.ok?['ok',t('verbunden','connected')]:[c.kind==='offline'?'warn':'bad',nasWhy(c.kind)]}
function nasCert(m,c,again){m.textContent='';const line=x=>{const s=document.createElement('div');s.textContent=x;m.appendChild(s)};
  line(t('Fingerabdruck (SHA-256): ','Fingerprint (SHA-256): ')+c.sha256);
  line(t('Gilt für: ','Valid for: ')+((c.names||[]).join(', ')||'–')+' · '+t('bis ','until ')+new Date(c.until*1000).toLocaleDateString()+(c.expired?t(' (abgelaufen)',' (expired)'):''));
  line(t('Passt nicht zur Adresse oder ist selbst ausgestellt. Den Fingerabdruck mit dem im NAS vergleichen (Synology: Systemsteuerung → Sicherheit → Zertifikat) und nur annehmen, wenn er gleich ist.',
    'Does not fit the address or is self-made. Compare the fingerprint with the one in the NAS (Synology: Control Panel → Security → Certificate) and accept it only when it is the same.'));
  const b=document.createElement('button');b.type='button';b.className='b';b.textContent=t('Fingerabdruck stimmt, annehmen','Fingerprint matches, accept');b.onclick=()=>again(c.sha256);codeLock(b,'confirm');m.appendChild(b)}
const nasCertOf=e=>{if(e.status!==409)return null;try{return JSON.parse(e.detail).cert||null}catch{return null}};
async function showNas(){const box=$('nasbox');if(!box)return;if(!PROFILE||!NAS_ON){box.innerHTML='';NAS_LIST=[];return}
  let d;try{d=await (await api('/api/profile/nas')).json()}catch{box.innerHTML='';return}
  NAS_LIST=d.on?d.items:[];
  const uses=x=>Object.entries(x.uses||{}).map(([k,n])=>t(...(NAS_USE[k]||[k,k]))+(n>1?' ×'+n:'')).join(', ');
  const item=x=>{const [cls,word]=nasState(x),z=x.zone==='lan'?t('Heimnetz','home network'):t('Internet','internet');
    const login=`<details><summary>${esc(t('Benutzer, Passwort oder Zertifikat ändern','Change user, password or certificate'))}</summary>
        <label>${esc(t('Name','Name'))}</label><input data-nasname="${esc(x.id)}" value="${esc(x.name)}" maxlength="40" autocomplete="off">
        <label>${esc(t('Benutzer','User'))}</label><input data-nasuser="${esc(x.id)}" value="${esc(x.user)}" maxlength="128" autocomplete="off">
        <label>${esc(t('Neues Passwort','New password'))}</label><input type="password" data-naspw="${esc(x.id)}" maxlength="256" autocomplete="new-password">
        ${x.kind==='webdav'?`<div class="fh">${esc(t('Angenommenes Zertifikat: ','Accepted certificate: '))}<code>${esc(x.cert||t('keins (Zertifikat passt zur Adresse)','none (certificate fits the address)'))}</code></div>`:''}
        ${x.kind==='sftp'?`<div class="fh">${esc(t('Schlüssel des Servers: ','Server key: '))}<code>${esc(x.hostkey||t('noch keiner','none yet'))}</code></div>
        <label class="chk"><input type="checkbox" data-naskey="${esc(x.id)}"> ${esc(t('Neuen Schlüssel des Servers annehmen','Accept the server\'s new key'))}</label>`:''}
        <div class="fh">${esc(t('Gilt sofort für alles, was diese NAS nutzt. Eine andere Adresse ist eine neue Verbindung.','Counts at once for everything that uses this NAS. Another address is a new connection.'))}</div>
        <div class="row"><button class="b" type="button" data-nasput="${esc(x.id)}">${esc(t('Übernehmen','Apply'))}</button></div><div class="fh" data-nascert="${esc(x.id)}" role="status"></div></details>`;
    return `<li><span><b>${esc(x.name)}</b> <em class="pill ${cls}">${esc(word)}</em><br>
      <small class="mut">${esc(t(...NAS_KIND[x.kind]||NAS_KIND.webdav))} · ${esc(z)} · ${esc(x.url)}${x.user?' · '+esc(x.user):''}${uses(x)?' · '+esc(t('genutzt von ','used by '))+esc(uses(x)):' · '+esc(t('noch nicht genutzt','not used yet'))}</small>
      <div class="row" style="margin-top:6px"><button class="b" type="button" data-nascheck="${esc(x.id)}">${esc(t('Verbindung prüfen','Check connection'))}</button></div>${login}</span>
      <button class="b" type="button" data-nasdel="${esc(x.id)}" data-nasn="${esc(x.name)}">${esc(t('Entfernen','Remove'))}</button></li>`};
  box.innerHTML=!d.on?'':`<h3 style="margin:4px 0 4px">${esc(t('Meine NAS','My NAS'))}</h3>
    <div class="intro">${esc(t('Deine NAS einmal verbinden (Synology, QNAP, Fritzbox oder ein anderer Server im Heimnetz): Adresse, Benutzer und Passwort stehen dann an einer Stelle, und alles, was die NAS nutzt, nimmt sie von hier. Am besten ein eigener Benutzer am NAS nur für den Spark.','Connect your NAS once (Synology, QNAP, Fritzbox or another server at home): address, user and password are then in one place, and everything that uses the NAS takes them from here. Best a user of its own on the NAS just for the Spark.'))}</div>
    <ul class="facts">${d.items.map(item).join('')||`<li class="mut"><span>${esc(t('Noch keine NAS verbunden.','No NAS connected yet.'))}</span></li>`}</ul>
    ${d.items.length<d.max?`<details style="margin-top:10px"${d.items.length?'':' open'}><summary>${esc(t('NAS verbinden','Connect a NAS'))}</summary>
      <label>${esc(t('Name','Name'))}</label><input id="nasname" maxlength="40" placeholder="${esc(t('z. B. Synology Keller','e.g. Synology basement'))}" autocomplete="off">
      <label>${esc(t('Art','Kind'))}</label><select id="naskind">${Object.keys(NAS_KIND).map(k=>`<option value="${k}">${esc(t(...NAS_KIND[k]))}</option>`).join('')}</select>
      <label>${esc(t('Adresse','Address'))}</label><input id="nasurl" maxlength="300" placeholder="${esc(NAS_HINT.webdav[0])}" autocomplete="off">
      <label>${esc(t('Benutzer','User'))}</label><input id="nasuser" maxlength="128" autocomplete="off">
      <label>${esc(t('Passwort','Password'))}</label><input type="password" id="naspw" maxlength="256" autocomplete="new-password">
      <div class="fh" id="nashint">${esc(t(NAS_HINT.webdav[1],NAS_HINT.webdav[2]))}</div>
      <div class="row" style="margin-top:8px"><button class="b p" type="button" id="nasadd">${esc(t('Prüfen und verbinden','Check and connect'))}</button></div>
      <div class="fh" id="nasaddmsg" role="status"></div></details>`:`<div class="fh">${esc(t(`Höchstens ${d.max} NAS-Verbindungen.`,`At most ${d.max} NAS connections.`))}</div>`}
    <div class="fh" id="nasmsg" role="status"></div>`;
  const say=(id,x,err)=>{xmsg(id,x,err);const m=$(id);if(m)m.scrollIntoView({block:'nearest'})};
  const codeErr=e=>/code required|Code/i.test(errRaw(e))?t('Ohne deinen Code geht es nicht: bitte noch einmal tippen und den Code eingeben.','Not without your code: tap again and enter your code.'):e.message;
  const after=async ok=>{await (typeof showStore==='function'?showStore():showNas());if(ok)xmsg('nasmsg',ok)};
  codeLock($('nasadd'),'confirm');box.querySelectorAll('[data-nasput]').forEach(b=>codeLock(b,'confirm'));
  if($('naskind'))$('naskind').onchange=()=>{const k=$('naskind').value;$('nasurl').placeholder=NAS_HINT[k][0];$('nashint').textContent=t(NAS_HINT[k][1],NAS_HINT[k][2])};
  if($('nasadd'))$('nasadd').onclick=async()=>{const b=$('nasadd'),kind=$('naskind').value,name=$('nasname').value.trim();
    if(!name){say('nasaddmsg',t('Bitte zuerst einen Namen eingeben.','Please enter a name first.'),true);$('nasname').focus();return}
    const body={name,kind,url:$('nasurl').value.trim(),user:$('nasuser').value.trim(),password:$('naspw').value};
    const ok=kind==='webdav'?/^https?:\/\//.test(body.url):body.url.startsWith(kind+'://');
    if(!ok){say('nasaddmsg',t(`Bitte die Adresse mit ${kind==='webdav'?'https://':kind+'://'} eingeben.`,`Please enter the address with ${kind==='webdav'?'https://':kind+'://'}.`),true);$('nasurl').focus();return}
    if(!body.password){say('nasaddmsg',t('Bitte das Passwort eingeben.','Please enter the password.'),true);$('naspw').focus();return}
    const send=async cert=>{if(cert)body.cert=cert;b.disabled=true;say('nasaddmsg',t('Melde mich an der NAS an …','Signing in to the NAS …'));
      try{await api('/api/profile/nas',xjson('POST',body));await after(t('Verbunden. Unter „Eigener Speicher“ kannst du sie jetzt auswählen.','Connected. You can now pick it under "Own storage".'))}
      catch(e){b.disabled=false;const c=nasCertOf(e);if(c){nasCert($('nasaddmsg'),c,send);return}say('nasaddmsg',codeErr(e),true)}};
    send()};
  box.querySelectorAll('[data-nascheck]').forEach(b=>b.onclick=async()=>{xmsg('nasmsg',t('Prüfe …','Checking …'));
    try{await api('/api/profile/nas/'+encodeURIComponent(b.dataset.nascheck)+'/check',{method:'POST'});await after(t('Die NAS ist erreichbar und nimmt die Anmeldung an.','The NAS is reachable and accepts the sign-in.'))}
    catch(e){await showNas();const c=nasCertOf(e),m=box.querySelector(`[data-nascert="${b.dataset.nascheck}"]`);
      if(c&&m){m.closest('details').open=true;nasCert(m,c,sha=>put(b.dataset.nascheck,{cert:sha}));return}say('nasmsg',e.message,true)}});
  const put=async(id,body)=>{const m=box.querySelector(`[data-nascert="${id}"]`);
    try{await api('/api/profile/nas/'+encodeURIComponent(id),xjson('PUT',body));await after(t('Übernommen und geprüft.','Applied and checked.'))}
    catch(e){const c=nasCertOf(e);if(c&&m){nasCert(m,c,sha=>put(id,Object.assign({},body,{cert:sha})));return}say('nasmsg',codeErr(e),true)}};
  box.querySelectorAll('[data-nasput]').forEach(b=>b.onclick=()=>{const id=b.dataset.nasput,q=a=>box.querySelector(`[${a}="${id}"]`);
    const body={name:q('data-nasname').value.trim(),user:q('data-nasuser').value.trim()},pw=q('data-naspw').value;if(pw)body.password=pw;
    const k=q('data-naskey');if(k&&k.checked)body.accept_key=true;put(id,body)});
  box.querySelectorAll('[data-nasdel]').forEach(b=>b.onclick=async()=>{if(!confirm(t(`„${b.dataset.nasn}“ entfernen? Das Passwort wird gelöscht; auf der NAS bleibt alles, wie es ist.`,`Remove "${b.dataset.nasn}"? The password is deleted; everything on the NAS stays as it is.`)))return;
    try{await api('/api/profile/nas/'+encodeURIComponent(b.dataset.nasdel),{method:'DELETE'});await after(t('Entfernt.','Removed.'))}catch(e){say('nasmsg',e.message,true)}})}
// Zustand → NAS (admin): per profile only name, kind, zone, state and uses (never an address or a password)
async function zNas(){const box=$('znas');if(!box||document.hidden)return;let d;
  try{const r=await fetch('/api/admin/nas',{cache:'no-store'});if(!r.ok)return;d=await r.json()}catch{return}
  box.hidden=!d.on;if(!d.on)return;
  const row=(who,x)=>{const [cls,word]=nasState(x);return `<div class="zrow"><span class="pill ${cls}">${esc(word)}</span><span><b>${esc(who)}</b> · ${esc(x.name)} · ${esc(t(...NAS_KIND[x.kind]||NAS_KIND.webdav))} · ${esc(x.zone==='lan'?t('Heimnetz','home network'):t('Internet','internet'))}<div class="mut">${esc(Object.keys(x.uses||{}).map(k=>t(...(NAS_USE[k]||[k,k]))).join(', ')||t('noch nicht genutzt','not used yet'))}</div></span></div>`};
  $('znaslist').innerHTML=(d.rows||[]).map(x=>row(x.profile,x)).join('')+(d.spark||[]).map(x=>row('Spark',x)).join('')
    ||`<div class="mut">${esc(t('Noch keine NAS verbunden.','No NAS connected yet.'))}</div>`}
