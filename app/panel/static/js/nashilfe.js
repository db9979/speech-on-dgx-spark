// Synology-Komfort (nashilfe.py, plan synology-bauplan.md S3) for "Ich → Speicher" (nas.js): "Im Heimnetz suchen"
// lists what announces itself by mDNS (never a scan) and fills address and kind; "Rechte anzeigen" shows per folder
// on the top level whether the Spark's user may read it, writes only a probe in spark_ablage and warns when the user
// looks like an admin account. Server text is text (esc).
const NH_RIGHT={lesen:['lesen','read','ok'],schreiben:['lesen und schreiben','read and write','ok'],nein:['kein Zugriff','no access','']};
const nhFind=()=>`<div class="row" style="margin-top:6px"><button class="b" type="button" id="nhfind">${esc(t('Im Heimnetz suchen','Search the home network'))}</button></div><div class="nhfound" id="nhfound"></div>`;
const nhRightsBtn=x=>`<button class="b" type="button" data-nhrights="${esc(x.id)}">${esc(t('Rechte anzeigen','Show rights'))}</button>`;
const nhOut=x=>`<div class="nhout" data-nhout="${esc(x.id)}"></div>`;
function nhDraw(m,d){m.textContent='';
  if(!d.supported){m.innerHTML=`<div class="fh">${esc(t('Bei SMB kann der Spark die Freigaben nicht auflisten: die Rechte siehst du im NAS (Synology: Systemsteuerung → Benutzer → Berechtigungen).','With SMB the Spark cannot list the shares: see the rights on the NAS (Synology: Control Panel → User → Permissions).'))}</div>`;return}
  const warn=d.admin_like?`<div class="nhwarn" role="alert"><b>${esc(t('Das sieht nach einem Admin-Konto aus.','This looks like an admin account.'))}</b> ${esc(t('Der Benutzer sieht Systemordner wie „homes“. Besser einen eigenen Benutzer nur für den Spark anlegen, der nur die nötigen Ordner sieht (siehe Anleitung „Synology einrichten“).','The user sees system folders such as "homes". Better create a user of its own just for the Spark that sees only the folders it needs (see the guide "Set up a Synology").'))}</div>`:'';
  const rows=d.folders.map(f=>{const r=NH_RIGHT[f.right]||NH_RIGHT.nein;return `<div class="nhrow"><span>${esc(f.name)}</span><em class="pill ${r[2]}">${esc(t(r[0],r[1]))}</em></div>`}).join('');
  const drop=d.drop==='schreiben'?t('In „spark_ablage“ darf der Spark schreiben (geprüft mit einer Probedatei, sofort gelöscht).','The Spark may write in "spark_ablage" (checked with a probe file, deleted at once).')
    :d.drop==='lesen'?t('„spark_ablage“ ist nur lesbar: zum Ablegen dort Schreibrecht geben.','"spark_ablage" is read only: give write access there for filing.')
    :t('Einen Ordner „spark_ablage“ gibt es nicht; nur dort würde der Spark später ablegen. Woanders schreibt er nie.','There is no folder "spark_ablage"; only there would the Spark file things later. It never writes anywhere else.');
  m.innerHTML=warn+(rows||`<div class="mut">${esc(t('Keine Ordner sichtbar.','No folders visible.'))}</div>`)+`<div class="fh">${esc(drop)}${d.complete?'':' '+esc(t('Nur die ersten Ordner geprüft.','Only the first folders checked.'))}</div>`}
async function nhRights(box,id,say){const m=box.querySelector(`[data-nhout="${id}"]`);if(!m)return;m.textContent=t('Prüfe die Ordner …','Checking the folders …');
  try{nhDraw(m,await (await api('/api/profile/nas/'+encodeURIComponent(id)+'/rights',{method:'POST'})).json())}catch(e){m.textContent='';say(e.message,true)}}
function nhBind(box,say){
  box.querySelectorAll('[data-nhrights]').forEach(b=>b.onclick=()=>nhRights(box,b.dataset.nhrights,say));
  const fb=$('nhfind');if(!fb)return;
  fb.onclick=async()=>{const out=$('nhfound');fb.disabled=true;out.textContent=t('Höre ein paar Sekunden ins Heimnetz …','Listening to the home network for a few seconds …');
    try{const d=await (await api('/api/profile/nas/find')).json();out.textContent='';
      if(!d.items.length){out.textContent=t('Nichts gefunden. Adresse bitte eintippen (Synology: DSM → Systemsteuerung → Netzwerk).','Nothing found. Please type the address (Synology: DSM → Control Panel → Network).');return}
      d.items.forEach(x=>{const b=document.createElement('button');b.type='button';b.className='b';
        b.textContent=(x.synology?'Synology ':'')+(x.model||x.name||x.addr)+' · '+x.addr;b.disabled=!x.suggest;
        b.onclick=()=>{if(!x.suggest)return;$('naskind').value=x.suggest.kind;$('naskind').onchange();$('nasurl').value=x.suggest.url;
          if(!$('nasname').value.trim())$('nasname').value=((x.synology?'Synology ':'')+(x.model||x.name)).trim().slice(0,40);$('nasuser').focus()};out.appendChild(b)});
      const h=document.createElement('div');h.className='fh';h.textContent=t('Antippen füllt Art und Adresse aus; Benutzer und Passwort trägst du selbst ein.','Tapping fills kind and address; you enter user and password yourself.');out.appendChild(h)}
    catch(e){out.textContent='';say(e.message,true)}finally{fb.disabled=false}}}
