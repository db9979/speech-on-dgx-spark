// "Kopie meiner Daten" (speicher.py, plan eigener-speicher.md): a profile puts an encrypted copy of its data on one
// of its places (nas.js: a NAS or cloud connection, or a folder the admin mounted on the Spark). The page itself is
// nas.js (Ich → Speicher, places with "Wofür", Dominik 2026-10-13); this file draws the copy part of a place and
// Zustand → Kopie meiner Daten (admin: per profile only kind, state, sizes and counts). Server text is text (esc).
let STORE_ON=false;
const SP_WHY={offline:['nicht erreichbar','not reachable'],auth:['Anmeldung abgelehnt','sign-in refused'],full:['voll','full'],
  blocked:['vom Wächter nicht erlaubt','not allowed by the Wächter'],key:['Schlüssel fehlt','key missing'],cert:['Zertifikat passt nicht','certificate does not fit'],notaus:['Notaus','kill switch'],hostkey:['Schlüssel des Servers hat sich geändert','the server\'s key changed'],other:['Fehler beim Ablegen','error while storing']};
const SP_KIND={webdav:['WebDAV','WebDAV'],sftp:['SFTP','SFTP'],smb:['SMB','SMB'],folder:['Ordner','folder']};
const SP_ZONE={lan:['Heimnetz','home network'],net:['Internet','internet'],spark:['Ordner auf dem Spark','folder on the Spark']};
const spSize=n=>{n=+n||0;return n>=1e12?(n/1e12).toFixed(1)+' TB':n>=1e9?(n/1e9).toFixed(1)+' GB':n>=1e6?Math.round(n/1e6)+' MB':n>=1e3?Math.round(n/1e3)+' KB':n+' B'};
const spWhen=x=>x?new Date(x*1000).toLocaleString([], {dateStyle:'short',timeStyle:'short'}):t('noch nie','never');
const spWhy=k=>t(...(SP_WHY[k]||SP_WHY.other));
function spState(x){if(x.running)return ['warn',x.running==='restore'?t('holt zurück','restoring'):t('gleicht ab','copying')];
  if(x.fail)return [x.fail.kind==='offline'?'warn':'bad',spWhy(x.fail.kind)];
  if(x.last&&x.last.ok)return ['ok',t('abgeglichen','in sync')];return ['',t('noch nicht abgeglichen','not copied yet')]}
function spFree(f){if(!f||f.avail==null&&f.used==null)return '';
  return f.avail!=null?t(`${spSize(f.avail)} frei`,`${spSize(f.avail)} free`):t(`${spSize(f.used)} belegt`,`${spSize(f.used)} used`)}
const SP_PATH={webdav:'/spark',sftp:'spark',smb:'/freigabe/spark'};
async function showStore(){if(typeof showNas==='function')await showNas()}   // the page is nas.js
const spAreas=(d,sel,pre)=>d.areas.map(a=>`<label class="chk"><input type="checkbox" data-sparea="${esc(pre)}" value="${esc(a.id)}"${sel.includes(a.id)?' checked':''}> ${esc(t(...a.name))}</label>`).join('');
function spHist(x){const h=(x.hist||[]).slice(-10).reverse();return h.length?`<ul class="bghist">${h.map(e=>`<li>${esc(spWhen(e.t))} · ${e.what==='restore'?esc(t('zurückgeholt','restored')):esc(t('Abgleich','copy'))} · ${e.ok?esc(t(`${e.n||0} Dateien`,`${e.n||0} files`))+(e.bytes?' · '+esc(spSize(e.bytes)):''):`<span class="err">${esc(spWhy(e.kind))}</span>`}</li>`).join('')}</ul>`:`<div class="mut">${esc(t('Noch nichts.','Nothing yet.'))}</div>`}
function spFix(x){const k=x.fail&&x.fail.kind;
  return k==='auth'?`<div class="fh err">${esc(t('Der Ort lehnt die Anmeldung ab: oben bei „Anmeldung ändern“ das Passwort neu eingeben.','The place refuses the sign-in: enter the password again above under "Change sign-in".'))}</div>`
    :k==='full'?`<div class="fh err">${esc(t('Der Ort ist voll. Neues bleibt auf dem Spark, bis dort wieder Platz ist; nichts wird gelöscht.','The place is full. New things stay on the Spark until there is room again; nothing is deleted.'))}</div>`
    :k==='offline'?`<div class="fh">${esc(t('Gerade nicht erreichbar. Alles bleibt auf dem Spark und wird nachgeholt, sobald der Ort wieder da ist.','Not reachable right now. Everything stays on the Spark and is copied once the place is back.'))}</div>`
    :k==='cert'?`<div class="fh err">${esc(t('Das Zertifikat hat sich geändert: oben „Verbindung prüfen“ und den Fingerabdruck vergleichen.','The certificate changed: tap "Check connection" above and compare the fingerprint.'))}</div>`
    :k==='hostkey'?`<div class="fh err">${esc(t('Der Server meldet sich mit einem anderen Schlüssel. Nichts geht dorthin. Nur wenn du den Grund kennst: oben bei „Anmeldung ändern“ den neuen Schlüssel annehmen.','The server shows a different key. Nothing goes there. Only if you know why: accept the new key above under "Change sign-in".'))}</div>`
    :k==='key'?`<div class="fh err">${esc(t('Der Schlüssel fehlt (Spark ohne Umzugs-Sicherung umgezogen). Die Kopie dort ist nicht mehr lesbar; aus- und wieder einschalten legt eine neue an.','The key is missing (Spark moved without a move backup). The copy there cannot be read any more; switch it off and on for a new one.'))}</div>`:''}
// the "Kopie meiner Daten" part of a place: x = the copy (speicher target) or null; place = {id, kind} of the place
function spCopy(d,x,place){
  if(!x){const k=place.kind;
    return `<div class="use"><div class="use-h"><span><b>${esc(t('Kopie meiner Daten','Copy of my data'))}</b><small>${esc(t('verschlüsselt, alle 30 Minuten was sich geändert hat','encrypted, every 30 minutes what changed'))}</small></span>${tglIn(`data-spon="${esc(place.id)}" aria-label="${esc(t('Kopie meiner Daten','Copy of my data'))}"`,false)}</div>
      <div class="useform" data-spform="${esc(place.id)}" hidden>${k!=='folder'?`<label>${esc(t('Ordner dort','Folder there'))}</label><input data-sppath="${esc(place.id)}" maxlength="200" value="${esc(SP_PATH[k]||'/spark')}" autocomplete="off">
        <div class="fh">${esc(k==='smb'?t('Freigabe und Ordner, z. B. /home/spark','Share and folder, e.g. /home/spark'):k==='sftp'?t('Pfad auf dem Server, z. B. /volume1/spark','Path on the server, e.g. /volume1/spark'):t('Ordner unter der Adresse, z. B. /home/spark','Folder below the address, e.g. /home/spark'))}</div>`:''}
        <label style="margin-top:8px">${esc(t('Was dorthin geht','What goes there'))}</label>${spAreas(d,d.areas.map(a=>a.id),'on-'+place.id)}
        <div class="row" style="margin-top:8px"><button class="b p" type="button" data-spgo="${esc(place.id)}">${esc(t('Prüfen und einschalten','Check and switch on'))}</button></div></div></div>`}
  const [cls,word]=spState(x);
  return `<div class="use"><div class="use-h"><span><b>${esc(t('Kopie meiner Daten','Copy of my data'))}</b> <em class="pill ${cls}">${esc(word)}</em>
      <small>${x.path?esc(x.path)+' · ':''}${esc(t(`${x.files} Dateien`,`${x.files} files`))} · ${esc(spSize(x.bytes))}${spFree(x.free)?' · '+esc(spFree(x.free)):''} · ${esc(t('zuletzt','last'))} ${esc(spWhen(x.last&&x.last.t))}${x.last&&x.last.pending?' · '+esc(t(`${x.last.pending} warten`,`${x.last.pending} waiting`)):''}${x.away?' · '+esc(t(`${x.away} Originale nur dort`,`${x.away} originals only there`)):''}</small></span>
      ${tglIn(`data-spoffcopy="${esc(x.id)}" aria-label="${esc(t('Kopie meiner Daten','Copy of my data'))}"`,true)}</div>${spFix(x)}
    <div class="row" style="margin-top:6px"><button class="b" type="button" data-spnow="${esc(x.id)}">${esc(t('Jetzt abgleichen','Copy now'))}</button><button class="b" type="button" data-sprestore="${esc(x.id)}">${esc(t('Fehlendes zurückholen','Restore what is missing'))}</button></div>
    <details><summary>${esc(t('Was dorthin geht','What goes there'))}</summary>${spAreas(d,x.areas,x.id)}
      ${d.offload||x.offload?`<label class="chk"><input type="checkbox" data-spoff="${esc(x.id)}"${x.offload?' checked':''}> ${esc(t(`Alte Originale von Dokumenten nur dort aufheben (nach ${d.offload_days} Tagen ohne Öffnen; beim Öffnen holt der Spark sie zurück)`,`Keep old originals of documents only there (after ${d.offload_days} days unopened; the Spark fetches them back when opened)`))}</label>`:''}
      <div class="row"><button class="b p" type="button" data-spsave="${esc(x.id)}">${esc(t('Speichern','Save'))}</button></div></details>
    ${x.nas?`<details><summary>${esc(t('Ordner ändern','Change folder'))}</summary><input data-spnewpath="${esc(x.id)}" maxlength="200" value="${esc(x.path||'')}" autocomplete="off">
      <div class="fh">${esc(t('Danach geht alles neu dorthin; der alte Ordner bleibt, wie er ist.','Then everything goes there anew; the old folder stays as it is.'))}</div>
      <div class="row"><button class="b" type="button" data-sppath2="${esc(x.id)}" data-spnas="${esc(x.nas)}">${esc(t('Übernehmen','Apply'))}</button></div></details>`:''}
    <details><summary>${esc(t('Letzte 7 Tage','Last 7 days'))}</summary>${spHist(x)}</details></div>`}
// buttons of the copy parts in box; after() draws the page again, say(text, err) shows a message
function spBind(box,d,after,say){
  const codeErr=e=>/code required|Code/i.test(errRaw(e))?t('Ohne deinen Code geht es nicht: bitte noch einmal tippen und den Code eingeben.','Not without your code: tap again and enter your code.'):e.message;
  const picked=pre=>[...box.querySelectorAll(`[data-sparea="${pre}"]`)].filter(c=>c.checked).map(c=>c.value);
  const go=async(url,opts,ok)=>{try{const r=await (await api(url,opts)).json();await after();if(ok)say(ok(r))}catch(e){await after();say(codeErr(e),true)}};
  box.querySelectorAll('[data-spgo]').forEach(b=>codeLock(b,'confirm'));
  box.querySelectorAll('[data-spon]').forEach(c=>c.onchange=()=>{const f=box.querySelector(`[data-spform="${c.dataset.spon}"]`);if(f)f.hidden=!c.checked});
  box.querySelectorAll('[data-spgo]').forEach(b=>b.onclick=async()=>{const id=b.dataset.spgo,p=box.querySelector(`[data-sppath="${id}"]`),place=(typeof NAS_LIST!=='undefined'?NAS_LIST:[]).find(c=>c.id===id);
    const body={name:(place?place.name:t('Kopie','Copy')).slice(0,40),areas:picked('on-'+id),nas:id,path:p?p.value.trim():''};
    b.disabled=true;say(t('Prüfe den Ort (Ordner anlegen, Probe schreiben und löschen) …','Checking the place (make folder, write and delete a probe) …'));
    try{await api('/api/profile/speicher',xjson('POST',body));await after();say(t('Eingeschaltet. Der erste Abgleich startet in einer ruhigen Minute, oder „Jetzt abgleichen“.','Switched on. The first copy starts in a quiet minute, or tap "Copy now".'))}
    catch(e){b.disabled=false;say(codeErr(e),true)}});
  box.querySelectorAll('[data-spnow]').forEach(b=>b.onclick=()=>go('/api/profile/speicher/'+encodeURIComponent(b.dataset.spnow)+'/now',{method:'POST'},()=>t('Abgleich läuft.','Copy running.')));
  box.querySelectorAll('[data-sprestore]').forEach(b=>b.onclick=()=>{if(!confirm(t('Alles aus der Kopie holen, was auf dem Spark fehlt? Vorhandenes bleibt unverändert.','Get everything from the copy that is missing on the Spark? What is there stays unchanged.')))return;
    say(t('Hole zurück …','Restoring …'));go('/api/profile/speicher/'+encodeURIComponent(b.dataset.sprestore)+'/restore',{method:'POST'},r=>t(`${r.restored.n} Dateien zurückgeholt.`,`${r.restored.n} files restored.`)+(r.restored.skipped?' '+t(`${r.restored.skipped} übersprungen.`,`${r.restored.skipped} skipped.`):''))});
  box.querySelectorAll('[data-spsave]').forEach(b=>b.onclick=()=>{const id=b.dataset.spsave,body={areas:picked(id)},o=box.querySelector(`[data-spoff="${id}"]`);if(o)body.offload=o.checked;
    go('/api/profile/speicher/'+encodeURIComponent(id),xjson('PUT',body),()=>t('Gespeichert.','Saved.'))});
  box.querySelectorAll('[data-sppath2]').forEach(b=>{codeLock(b,'confirm');b.onclick=()=>{const id=b.dataset.sppath2;
    go('/api/profile/speicher/'+encodeURIComponent(id),xjson('PUT',{nas:b.dataset.spnas,path:box.querySelector(`[data-spnewpath="${id}"]`).value.trim()}),()=>t('Übernommen und geprüft.','Applied and checked.'))}});
  box.querySelectorAll('[data-spoffcopy]').forEach(c=>c.onchange=()=>{if(!confirm(t('Kopie hier ausschalten? Was dort liegt, bleibt dort; der Spark schickt nichts mehr hin.','Switch the copy off here? What is there stays there; the Spark sends nothing more.'))){c.checked=true;return}
    go('/api/profile/speicher/'+encodeURIComponent(c.dataset.spoffcopy),{method:'DELETE'},()=>t('Ausgeschaltet.','Switched off.'))})}
// Zustand → Kopie meiner Daten (admin)
async function zStore(){const box=$('zstore');if(!box||document.hidden)return;let d;
  try{const r=await /*raw: timer poll, a 401/503 must stay silent*/fetch('/api/admin/speicher',{cache:'no-store'});if(!r.ok)return;d=await r.json()}catch{return}
  box.hidden=!d.on;if(!d.on)return;const s=d.sum||{};
  $('zstorelist').innerHTML=`<div class="mut" style="margin-bottom:6px">${esc(t(`${s.targets} Speicher · ${spSize(s.bytes)} abgelegt · ${s.failing} mit Fehler · ${s.errors_today} Fehlversuche heute`,`${s.targets} targets · ${spSize(s.bytes)} stored · ${s.failing} failing · ${s.errors_today} failed tries today`))}</div>`+
    ((d.rows||[]).map(x=>{const [cls,word]=spState(x);return `<div class="zrow"><span class="pill ${cls}">${esc(word)}</span><span><b>${esc(x.profile)}</b> · ${esc(x.name)} · ${esc(t(...SP_KIND[x.kind]||SP_KIND.webdav))} · ${esc(t(...(SP_ZONE[x.zone]||SP_ZONE.net)))}<div class="mut">${esc(t(`${x.files} Dateien`,`${x.files} files`))} · ${esc(spSize(x.bytes))}${spFree(x.free)?' · '+esc(spFree(x.free)):''} · ${esc(t('zuletzt','last'))} ${esc(spWhen(x.last&&x.last.t))}${x.pending?' · '+esc(t(`${x.pending} warten`,`${x.pending} waiting`)):''}${x.away?' · '+esc(t(`${x.away} Originale nur dort`,`${x.away} originals only there`)):''}</div></span></div>`}).join('')
     ||`<div class="mut">${esc(t('Noch kein Profil hat einen Speicher eingebunden.','No profile has added storage yet.'))}</div>`)}
