// "Ich → Speicher" (speicher.py, plan eigener-speicher.md): a profile puts an encrypted copy of its data on its own
// NAS, WebDAV service or a folder the admin mounted on the Spark. Adding a target or changing its address or password
// asks for a code; the password never comes back. Zustand → Eigener Speicher (admin): per profile only kind, state,
// sizes and counts. Everything from the server is text (esc).
let STORE_ON=false;
const SP_WHY={offline:['nicht erreichbar','not reachable'],auth:['Anmeldung abgelehnt','sign-in refused'],full:['voll','full'],
  blocked:['vom Wächter nicht erlaubt','not allowed by the Wächter'],key:['Schlüssel fehlt','key missing'],notaus:['Notaus','kill switch'],hostkey:['Schlüssel des Servers hat sich geändert','the server\'s key changed'],other:['Fehler beim Ablegen','error while storing']};
const SP_KIND={webdav:['WebDAV','WebDAV'],sftp:['SFTP','SFTP'],smb:['SMB','SMB'],folder:['Ordner','folder']};
const SP_START={webdav:'https://',sftp:'sftp://',smb:'smb://'};
const SP_HINT={webdav:['https://nas.fritz.box:5006/spark','Am besten ein eigener Benutzer am NAS nur für den Spark. https:// immer, http:// nur im Heimnetz.','Best a user of its own on the NAS just for the Spark. Always https://, http:// only at home.'],
  sftp:['sftp://nas.fritz.box/volume1/spark','SSH-Zugang am NAS oder Server, am besten ein eigener Benutzer nur für den Spark. Der Schlüssel des Servers wird beim Einbinden gemerkt.','SSH access on the NAS or server, best a user of its own just for the Spark. The server\'s key is remembered when you add it.'],
  smb:['smb://nas.fritz.box/freigabe/spark','Windows- oder NAS-Freigabe, nur im Heimnetz und nur verschlüsselt (SMB 3). Am besten ein eigener Benutzer nur für den Spark.','Windows or NAS share, only at home and only encrypted (SMB 3). Best a user of its own just for the Spark.']};
const SP_ZONE={lan:['Heimnetz','home network'],net:['Internet','internet'],spark:['Ordner auf dem Spark','folder on the Spark']};
const spSize=n=>{n=+n||0;return n>=1e12?(n/1e12).toFixed(1)+' TB':n>=1e9?(n/1e9).toFixed(1)+' GB':n>=1e6?Math.round(n/1e6)+' MB':n>=1e3?Math.round(n/1e3)+' KB':n+' B'};
const spWhen=x=>x?new Date(x*1000).toLocaleString([], {dateStyle:'short',timeStyle:'short'}):t('noch nie','never');
const spWhy=k=>t(...(SP_WHY[k]||SP_WHY.other));
function spState(x){if(x.running)return ['warn',x.running==='restore'?t('holt zurück','restoring'):t('gleicht ab','copying')];
  if(x.fail)return [x.fail.kind==='offline'?'warn':'bad',spWhy(x.fail.kind)];
  if(x.last&&x.last.ok)return ['ok',t('abgeglichen','in sync')];return ['',t('noch nicht abgeglichen','not copied yet')]}
function spFree(f){if(!f||f.avail==null&&f.used==null)return '';
  return f.avail!=null?t(`${spSize(f.avail)} frei`,`${spSize(f.avail)} free`):t(`${spSize(f.used)} belegt`,`${spSize(f.used)} used`)}
async function showStore(){if(typeof showNas==='function')await showNas();   // Meine NAS (nas.js) above
  const box=$('spbox');if(!box)return;if(!PROFILE||!STORE_ON){box.innerHTML='';return}
  let d;try{d=await (await api('/api/profile/speicher')).json()}catch{box.innerHTML='';return}
  const area=(id,on,pre)=>`<label class="chk"><input type="checkbox" data-sparea="${esc(pre)}" value="${esc(id)}"${on?' checked':''}> ${esc(t(...d.areas.find(a=>a.id===id).name))}</label>`;
  const areas=(sel,pre)=>d.areas.map(a=>area(a.id,sel.includes(a.id),pre)).join('');
  const hist=x=>{const h=(x.hist||[]).slice(-10).reverse();return h.length?`<ul class="bghist">${h.map(e=>`<li>${esc(spWhen(e.t))} · ${e.what==='restore'?esc(t('zurückgeholt','restored')):esc(t('Abgleich','copy'))} · ${e.ok?esc(t(`${e.n||0} Dateien`,`${e.n||0} files`))+(e.bytes?' · '+esc(spSize(e.bytes)):''):`<span class="err">${esc(spWhy(e.kind))}</span>`}</li>`).join('')}</ul>`:`<div class="mut">${esc(t('Noch nichts.','Nothing yet.'))}</div>`};
  const tgt=x=>{const [cls,word]=spState(x),z=SP_ZONE[x.zone]||SP_ZONE.net;
    const where=x.kind!=='folder'?`${esc(t(...SP_KIND[x.kind]||SP_KIND.webdav))} · ${esc(t(...z))}`:`${esc(t(...z))} · ${esc(x.folder)}`;
    const fix=x.fail&&x.fail.kind==='auth'?`<div class="fh err">${esc(t('Der Speicher lehnt die Anmeldung ab: unten unter „Adresse oder Passwort ändern“ das Passwort neu eingeben.','The storage refuses the sign-in: enter the password again below under "Change address or password".'))}</div>`
      :x.fail&&x.fail.kind==='full'?`<div class="fh err">${esc(t('Der Speicher ist voll. Neues bleibt auf dem Spark, bis dort wieder Platz ist; nichts wird gelöscht.','The storage is full. New things stay on the Spark until there is room again; nothing is deleted.'))}</div>`
      :x.fail&&x.fail.kind==='offline'?`<div class="fh">${esc(t('Gerade nicht erreichbar. Alles bleibt auf dem Spark und wird nachgeholt, sobald der Speicher wieder da ist.','Not reachable right now. Everything stays on the Spark and is copied once the storage is back.'))}</div>`
      :x.fail&&x.fail.kind==='hostkey'?`<div class="fh err">${esc(t('Der Server meldet sich mit einem anderen Schlüssel als beim Einbinden. Das passiert, wenn er neu eingerichtet wurde, aber auch, wenn sich jemand dazwischen schiebt. Nichts geht dorthin. Nur wenn du den Grund kennst: unten „Neuen Schlüssel des Servers annehmen“ mit Passwort.','The server shows a different key than when it was added. That happens when it was set up again, but also when someone gets in between. Nothing goes there. Only if you know why: below "Accept the server\'s new key" with the password.'))}</div>`
      :x.fail&&x.fail.kind==='key'?`<div class="fh err">${esc(t('Der Schlüssel fehlt (Spark ohne Umzugs-Sicherung umgezogen). Die Kopie dort ist nicht mehr lesbar; trennen und neu einbinden legt eine neue an.','The key is missing (Spark moved without a move backup). The copy there cannot be read any more; disconnect and add it again for a new one.'))}</div>`:'';
    return `<li><span><b>${esc(x.name)}</b> <em class="pill ${cls}">${esc(word)}</em><br>
      <small class="mut">${where} · ${esc(t(`${x.files} Dateien`,`${x.files} files`))} · ${esc(spSize(x.bytes))}${spFree(x.free)?' · '+esc(spFree(x.free)):''} · ${esc(t('zuletzt','last'))} ${esc(spWhen(x.last&&x.last.t))}${x.last&&x.last.pending?' · '+esc(t(`${x.last.pending} warten`,`${x.last.pending} waiting`)):''}${x.away?' · '+esc(t(`${x.away} Originale nur dort`,`${x.away} originals only there`)):''}</small>${fix}
      <div class="row" style="margin-top:6px"><button class="b" type="button" data-spnow="${esc(x.id)}">${esc(t('Jetzt abgleichen','Copy now'))}</button><button class="b" type="button" data-spcheck="${esc(x.id)}">${esc(t('Verbindung prüfen','Check connection'))}</button><button class="b" type="button" data-sprestore="${esc(x.id)}">${esc(t('Fehlendes zurückholen','Restore what is missing'))}</button></div>
      <details><summary>${esc(t('Was dorthin geht','What goes there'))}</summary>${areas(x.areas,x.id)}
        ${d.offload||x.offload?`<label class="chk"><input type="checkbox" data-spoff="${esc(x.id)}"${x.offload?' checked':''}> ${esc(t(`Alte Originale von Dokumenten nur dort aufheben (nach ${d.offload_days} Tagen ohne Öffnen; beim Öffnen holt der Spark sie zurück)`,`Keep old originals of documents only there (after ${d.offload_days} days unopened; the Spark fetches them back when opened)`))}</label>`:''}
        <div class="row"><button class="b p" type="button" data-spsave="${esc(x.id)}">${esc(t('Speichern','Save'))}</button></div></details>
      ${x.kind!=='folder'?`<details><summary>${esc(t('Adresse oder Passwort ändern','Change address or password'))}</summary>
        <label>${esc(t('Adresse','Address'))}</label><input data-spurl="${esc(x.id)}" value="${esc(x.url)}" maxlength="300" autocomplete="off">
        <label>${esc(t('Benutzer','User'))}</label><input data-spuser="${esc(x.id)}" value="${esc(x.user)}" maxlength="128" autocomplete="off">
        <label>${esc(t('Neues Passwort','New password'))}</label><input type="password" data-sppw="${esc(x.id)}" maxlength="256" autocomplete="new-password">
        ${x.kind==='sftp'?`<div class="fh">${esc(t('Schlüssel des Servers: ','Server key: '))}<code>${esc(x.hostkey||t('noch keiner','none yet'))}</code></div>
        <label class="chk"><input type="checkbox" data-spkey="${esc(x.id)}"> ${esc(t('Neuen Schlüssel des Servers annehmen','Accept the server\'s new key'))}</label>`:''}
        <div class="fh">${esc(t('Eine neue Adresse braucht das Passwort noch einmal; danach geht alles neu dorthin.','A new address needs the password again; then everything goes there anew.'))}</div>
        <div class="row"><button class="b" type="button" data-spnew="${esc(x.id)}">${esc(t('Übernehmen','Apply'))}</button></div></details>`:''}
      <details><summary>${esc(t('Letzte 7 Tage','Last 7 days'))}</summary>${hist(x)}</details></span>
      <button class="b" type="button" data-spdel="${esc(x.id)}" data-spname="${esc(x.name)}">${esc(t('Trennen','Disconnect'))}</button></li>`};
  const nasK=(typeof NAS_LIST!=='undefined'?NAS_LIST:[]).filter(c=>c.kind!=='smb'||d.lan).map(c=>['nas:'+c.id,t('Auf meiner NAS: ','On my NAS: ')+c.name]);
  const kinds=nasK.concat([['webdav',t('NAS oder WebDAV-Dienst','NAS or WebDAV service')],['sftp',t('SFTP (SSH)','SFTP (SSH)')]].concat(d.lan?[['smb',t('SMB-Freigabe im Heimnetz','SMB share at home')]]:[]).concat(d.folder?[['folder',t('Ordner auf dem Spark','Folder on the Spark')]]:[]));
  box.innerHTML=`<div class="intro">${esc(t('Eine Kopie deiner Daten auf deinem eigenen Speicher: NAS im Heimnetz (Synology, QNAP, Fritzbox), Nextcloud, ownCloud, HiDrive, MagentaCLOUD, ein anderer WebDAV-Dienst, ein SFTP-Server oder eine SMB-Freigabe. Alles geht verschlüsselt dorthin; der Speicher sieht nur Rauschen. Der Spark arbeitet immer lokal weiter, auch wenn der Speicher mal weg ist.','A copy of your data on your own storage: a NAS at home (Synology, QNAP, Fritzbox), Nextcloud, ownCloud, HiDrive, MagentaCLOUD, another WebDAV service, an SFTP server or an SMB share. Everything goes there encrypted; the storage only sees noise. The Spark always keeps working locally, even when the storage is gone.'))}</div>
    ${xsw('storage_on',t('Eigener Speicher für mich','Own storage for me'),t('Aus: Es geht nichts mehr zu deinen Speichern; was dort liegt, bleibt.','Off: nothing goes to your storage any more; what is there stays.'))}
    ${d.on?`<div class="fh">${esc(t('Bleibt immer auf dem Spark: Schlüssel und Anmeldung, zweiter Anmeldeschritt, Passwörter deiner Dienste, Einstellungen und Stimmabdruck.','Always stays on the Spark: keys and sign-in, second sign-in step, passwords of your services, settings and voice print.'))}</div>
    <h3 style="margin:14px 0 4px">${esc(t('Meine Speicher','My storage'))}</h3><ul class="facts">${d.targets.map(tgt).join('')||`<li class="mut"><span>${esc(t('Noch kein Speicher eingebunden.','No storage added yet.'))}</span></li>`}</ul>
    ${d.targets.length<d.max?`<details style="margin-top:10px"${d.targets.length?'':' open'}><summary>${esc(t('Speicher einbinden','Add storage'))}</summary>
      <label>${esc(t('Name','Name'))}</label><input id="spname" maxlength="40" placeholder="${esc(t('z. B. NAS Keller','e.g. NAS basement'))}" autocomplete="off">
      <label>${esc(t('Art','Kind'))}</label><select id="spkind">${kinds.map(([k,l])=>`<option value="${k}">${esc(l)}</option>`).join('')}</select>
      <div id="spwebdav"><label>${esc(t('Adresse','Address'))}</label><input id="spurl" maxlength="300" placeholder="${SP_HINT.webdav[0]}" autocomplete="off">
        <label>${esc(t('Benutzer','User'))}</label><input id="spuser" maxlength="128" autocomplete="off">
        <label>${esc(t('Passwort','Password'))}</label><input type="password" id="sppw" maxlength="256" autocomplete="new-password">
        <div class="fh"><span id="sphint">${esc(t(SP_HINT.webdav[1],SP_HINT.webdav[2]))}</span>${d.lan?'':' '+esc(t('Adressen im Heimnetz hat der Admin nicht erlaubt.','The admin has not allowed addresses in the home network.'))}</div></div>
      <div id="spnas" hidden><label>${esc(t('Ordner auf der NAS','Folder on the NAS'))}</label><input id="sppath" maxlength="200" placeholder="${esc(t('z. B. /home/spark','e.g. /home/spark'))}" autocomplete="off">
        <div class="fh">${esc(t('Adresse, Benutzer und Passwort kommen von der NAS-Verbindung oben. WebDAV: der Ordner unter der Adresse; SMB: Freigabe und Ordner; SFTP: der Pfad auf dem Server.','Address, user and password come from the NAS connection above. WebDAV: the folder below the address; SMB: share and folder; SFTP: the path on the server.'))}</div></div>
      <div id="spfolder" hidden><label>${esc(t('Unterordner','Subfolder'))}</label><input id="spsub" maxlength="40" placeholder="${esc(t('z. B. anna','e.g. anna'))}" autocomplete="off">
        <div class="fh">${esc(t('Liegt unter ','Lies below '))}${esc(d.root||'')}</div></div>
      <label style="margin-top:8px">${esc(t('Was dorthin geht','What goes there'))}</label>${areas(d.areas.map(a=>a.id),'new')}
      <div class="row" style="margin-top:8px"><button class="b p" type="button" id="spadd">${esc(t('Prüfen und einbinden','Check and add'))}</button></div>
      <div class="fh" id="spaddmsg" role="status"></div></details>`:`<div class="fh">${esc(t(`Höchstens ${d.max} Speicher.`,`At most ${d.max} storage targets.`))}</div>`}`:''}
    <div class="fh" id="spmsg" role="status"></div>`;
  xbind(box,showStore);
  const say=(id,x,err)=>{xmsg(id,x,err);const m=$(id);if(m)m.scrollIntoView({block:'nearest'})};
  const codeErr=e=>/code required|Code/i.test(errRaw(e))?t('Ohne deinen Code geht es nicht: bitte noch einmal tippen und den Code eingeben.','Not without your code: tap again and enter your code.'):e.message;
  const picked=pre=>[...box.querySelectorAll(`[data-sparea="${pre}"]`)].filter(c=>c.checked).map(c=>c.value);
  const spKind=()=>{const k=$('spkind').value,f=k==='folder',n=k.startsWith('nas:');$('spwebdav').hidden=f||n;$('spfolder').hidden=!f;$('spnas').hidden=!n;
    if(!f&&!n){$('spurl').placeholder=SP_HINT[k][0];$('sphint').textContent=t(SP_HINT[k][1],SP_HINT[k][2])}};
  if($('spkind')){$('spkind').onchange=spKind;spKind()}
  if($('spadd'))$('spadd').onclick=async()=>{const b=$('spadd'),kind=$('spkind').value,name=$('spname').value.trim();
    if(!name){say('spaddmsg',t('Bitte zuerst einen Namen eingeben.','Please enter a name first.'),true);$('spname').focus();return}
    const body={name,kind,areas:picked('new')};
    if(kind.startsWith('nas:')){delete body.kind;body.nas=kind.slice(4);body.path=$('sppath').value.trim()}
    else if(kind!=='folder'){body.url=$('spurl').value.trim();body.user=$('spuser').value.trim();body.password=$('sppw').value;
      const ok=kind==='webdav'?/^https?:\/\//.test(body.url):body.url.startsWith(SP_START[kind]);
      if(!ok){say('spaddmsg',t(`Bitte die Adresse mit ${SP_START[kind]} eingeben.`,`Please enter the address with ${SP_START[kind]}.`),true);$('spurl').focus();return}}
    else body.folder=$('spsub').value.trim();
    b.disabled=true;say('spaddmsg',t('Prüfe den Speicher (Ordner anlegen, Probe schreiben und löschen) …','Checking the storage (make folder, write and delete a probe) …'));
    try{await api('/api/profile/speicher',xjson('POST',body));await showStore();xmsg('spmsg',t('Eingebunden. Der erste Abgleich startet in einer ruhigen Minute, oder „Jetzt abgleichen“.','Added. The first copy starts in a quiet minute, or tap "Copy now".'))}
    catch(e){b.disabled=false;say('spaddmsg',codeErr(e),true)}};
  const go=async(url,opts,ok)=>{try{const r=await (await api(url,opts)).json();await showStore();if(ok)xmsg('spmsg',ok(r))}catch(e){say('spmsg',codeErr(e),true)}};
  box.querySelectorAll('[data-spnow]').forEach(b=>b.onclick=()=>go('/api/profile/speicher/'+encodeURIComponent(b.dataset.spnow)+'/now',{method:'POST'},()=>t('Abgleich läuft.','Copy running.')));
  box.querySelectorAll('[data-spcheck]').forEach(b=>b.onclick=()=>{xmsg('spmsg',t('Prüfe …','Checking …'));go('/api/profile/speicher/'+encodeURIComponent(b.dataset.spcheck)+'/check',{method:'POST'},()=>t('Der Speicher ist erreichbar und nimmt Dateien an.','The storage is reachable and takes files.'))});
  box.querySelectorAll('[data-sprestore]').forEach(b=>b.onclick=()=>{if(!confirm(t('Alles aus der Kopie holen, was auf dem Spark fehlt? Vorhandenes bleibt unverändert.','Get everything from the copy that is missing on the Spark? What is there stays unchanged.')))return;
    xmsg('spmsg',t('Hole zurück …','Restoring …'));go('/api/profile/speicher/'+encodeURIComponent(b.dataset.sprestore)+'/restore',{method:'POST'},r=>t(`${r.restored.n} Dateien zurückgeholt.`,`${r.restored.n} files restored.`)+(r.restored.skipped?' '+t(`${r.restored.skipped} übersprungen.`,`${r.restored.skipped} skipped.`):''))});
  box.querySelectorAll('[data-spsave]').forEach(b=>b.onclick=()=>{const id=b.dataset.spsave,body={areas:picked(id)},o=box.querySelector(`[data-spoff="${id}"]`);if(o)body.offload=o.checked;
    go('/api/profile/speicher/'+encodeURIComponent(id),xjson('PUT',body),()=>t('Gespeichert.','Saved.'))});
  box.querySelectorAll('[data-spnew]').forEach(b=>b.onclick=()=>{const id=b.dataset.spnew,q=a=>box.querySelector(`[${a}="${id}"]`).value;
    const body={url:q('data-spurl').trim(),user:q('data-spuser').trim()},pw=q('data-sppw');if(pw)body.password=pw;
    const k=box.querySelector(`[data-spkey="${id}"]`);if(k&&k.checked)body.accept_key=true;
    go('/api/profile/speicher/'+encodeURIComponent(id),xjson('PUT',body),()=>t('Übernommen und geprüft.','Applied and checked.'))});
  box.querySelectorAll('[data-spdel]').forEach(b=>b.onclick=()=>{if(!confirm(t(`„${b.dataset.spname}“ trennen? Was dort liegt, bleibt dort; der Spark schickt nichts mehr hin.`,`Disconnect "${b.dataset.spname}"? What is there stays there; the Spark sends nothing more.`)))return;
    go('/api/profile/speicher/'+encodeURIComponent(b.dataset.spdel),{method:'DELETE'},()=>t('Getrennt.','Disconnected.'))})}
// Zustand → Eigener Speicher (admin)
async function zStore(){const box=$('zstore');if(!box||document.hidden)return;let d;
  try{const r=await fetch('/api/admin/speicher',{cache:'no-store'});if(!r.ok)return;d=await r.json()}catch{return}
  box.hidden=!d.on;if(!d.on)return;const s=d.sum||{};
  $('zstorelist').innerHTML=`<div class="mut" style="margin-bottom:6px">${esc(t(`${s.targets} Speicher · ${spSize(s.bytes)} abgelegt · ${s.failing} mit Fehler · ${s.errors_today} Fehlversuche heute`,`${s.targets} targets · ${spSize(s.bytes)} stored · ${s.failing} failing · ${s.errors_today} failed tries today`))}</div>`+
    ((d.rows||[]).map(x=>{const [cls,word]=spState(x);return `<div class="zrow"><span class="pill ${cls}">${esc(word)}</span><span><b>${esc(x.profile)}</b> · ${esc(x.name)} · ${esc(t(...SP_KIND[x.kind]||SP_KIND.webdav))} · ${esc(t(...(SP_ZONE[x.zone]||SP_ZONE.net)))}<div class="mut">${esc(t(`${x.files} Dateien`,`${x.files} files`))} · ${esc(spSize(x.bytes))}${spFree(x.free)?' · '+esc(spFree(x.free)):''} · ${esc(t('zuletzt','last'))} ${esc(spWhen(x.last&&x.last.t))}${x.pending?' · '+esc(t(`${x.pending} warten`,`${x.pending} waiting`)):''}${x.away?' · '+esc(t(`${x.away} Originale nur dort`,`${x.away} originals only there`)):''}${x.allowed?'':' · '+esc(t('Profil-Schalter aus','profile switch off'))}</div></span></div>`}).join('')
     ||`<div class="mut">${esc(t('Noch kein Profil hat einen Speicher eingebunden.','No profile has added storage yet.'))}</div>`)}
