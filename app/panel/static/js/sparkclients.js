// Einstellungen → Spark → Betrieb → Spark-Clients (sparkclients.py, admin, plan spark-entkoppeln E1): the switch that
// opens the model computer's services for other programs, the home networks they may come from, and the clients with
// their rights, class and limits. A new key is shown once (fresh code); names, networks and numbers all through esc().
let SPC=null;
const SPC_RECHT={llm:['Sprachmodell','Language model'],sehen:['Bilder verstehen','Understand pictures'],helfer:['Hilfsmodell','Helper model'],
  systemone:['Einordnen (System One)','Classify (System One)'],asr:['Hören','Listening'],tts:['Sprechen','Speaking'],bild:['Bilder','Pictures'],musik:['Musik','Music']};
const SPC_KLASSE={sprache:['Sprache','Speech'],dialog:['Dialog','Dialogue'],hintergrund:['Hintergrund','Background']};
const spcT=p=>p?t(p[0],p[1]):'';
async function spcLoad(){const sec=$('spcsec'),box=$('spcbox');if(!sec||!box)return;
  let r;try{r=await api('/api/admin/spark-clients',{cache:'no-store'})}catch{sec.hidden=true;return}
  sec.hidden=false;SPC=await r.json();spcDraw()}
function spcDraw(msg){const d=SPC,box=$('spcbox');if(!d||!box)return;
  const rows=d.clients.map(c=>`<li><span><b>${esc(c.name)}</b> <span class="mut">${esc(c.rechte.map(x=>spcT(SPC_RECHT[x])).join(', '))}</span></span>
    <span class="mut">${esc(spcT(SPC_KLASSE[c.klasse]))} · ${esc(t(`${c.minute}/min, ${c.parallel} gleichzeitig, ${c.tokens_tag} Tokens/Tag`,`${c.minute}/min, ${c.parallel} at once, ${c.tokens_tag} tokens/day`))}${c.gesperrt?' · '+esc(t('gesperrt','blocked')):''}</span>
    <button class="b" type="button" data-spc="sperren" data-id="${esc(c.id)}">${esc(c.gesperrt?t('Entsperren','Unblock'):t('Sperren','Block'))}</button>
    <button class="b" type="button" data-spc="weg" data-id="${esc(c.id)}">${esc(t('Löschen','Delete'))}</button></li>`).join('');
  box.innerHTML=`<div class="row"><label class="tgl"><input type="checkbox" id="spcan"${d.an?' checked':''}><i></i></label>
      <span>${esc(t('Für Clients geöffnet','Open for clients'))}</span></div>
    <label for="spcnetze">${esc(t('Netze im Heimnetz, mit Komma','Home networks, separated by commas'))}</label>
    <div class="ctl full"><input class="wide" id="spcnetze" value="${esc(d.netze.join(', '))}" placeholder="192.168.178.0/24" autocomplete="off">
      <button class="b" type="button" data-spc="schalten">${esc(t('Übernehmen','Apply'))}</button></div>
    <ul class="facts">${rows||`<li class="mut">${esc(t('Noch kein Client.','No client yet.'))}</li>`}</ul>
    <div class="ctl full"><input class="wide" id="spcname" maxlength="40" placeholder="${esc(t('Name, z. B. Open WebUI','Name, e.g. Open WebUI'))}" aria-label="${esc(t('Name des Clients','Name of the client'))}">
      <select id="spcklasse" aria-label="${esc(t('Vorrangklasse','Priority class'))}">${d.klassen.map(k=>`<option value="${esc(k)}"${k===d.vorgabe.klasse?' selected':''}>${esc(spcT(SPC_KLASSE[k]))}</option>`).join('')}</select></div>
    <div class="row">${d.rechte.map(x=>`<label><input type="checkbox" data-spcrecht="${esc(x)}"${d.vorgabe.rechte.includes(x)?' checked':''}> ${esc(spcT(SPC_RECHT[x]))}</label>`).join(' ')}</div>
    <div class="row"><button class="b p" type="button" data-spc="neu"${d.clients.length>=d.max?' disabled':''}>${esc(t('Schlüssel erzeugen','Make key'))}</button><span id="spcmsg" class="fh">${esc(msg||'')}</span></div>
    <div class="full rowtail" id="spcneu" hidden><div class="fh">${esc(t('Nur jetzt sichtbar. Im Programm als API-Schlüssel eintragen (Bearer).','Visible only now. Enter it in the program as the API key (Bearer).'))}</div><pre id="spckey"></pre></div>`;
  for(const id of ['spcan'])$(id).addEventListener('change',()=>spcAct('schalten'));
  codeLock(box.querySelector('[data-spc="neu"]'),'protect')}
async function spcPost(path,body){const r=await api(path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});return r.json()}
async function spcAct(a,b){const m=x=>{const el=$('spcmsg');if(el)el.textContent=x};
  try{
    if(a==='schalten'){const netze=$('spcnetze').value.split(',').map(x=>x.trim()).filter(Boolean);
      const d=await spcPost('/api/admin/spark-clients/schalten',{an:$('spcan').checked,netze});SPC=Object.assign(SPC,d);spcDraw(d.an?t('Geöffnet.','Open.'):t('Geschlossen.','Closed.'));return}
    if(a==='neu'){const rechte=[...document.querySelectorAll('[data-spcrecht]')].filter(x=>x.checked).map(x=>x.dataset.spcrecht);
      const d=await spcPost('/api/admin/spark-clients/neu',{name:$('spcname').value,rechte,klasse:$('spcklasse').value});
      await spcLoad();$('spckey').textContent=d.key;$('spcneu').hidden=false;return}
    const c=SPC.clients.find(x=>x.id===b.dataset.id);if(!c)return;
    if(a==='sperren')await spcPost('/api/admin/spark-clients/aendern',{id:c.id,felder:{gesperrt:!c.gesperrt}});
    if(a==='weg')await spcPost('/api/admin/spark-clients/weg',{id:c.id});
    await spcLoad()}
  catch(e){m(e.message);if(a==='schalten'&&SPC)$('spcan').checked=SPC.an}}
document.addEventListener('click',e=>{const b=e.target.closest('[data-spc]');if(!b||!$('spcbox')||!$('spcbox').contains(b))return;
  const a=b.dataset.spc;if(a==='neu'||a==='schalten'||a==='sperren'||a==='weg')spcAct(a,b)});
// loaded when Einstellungen → Spark → Betrieb opens (admin.js cfgnav), never for a profile without the admin pages

// Einstellungen → Spark → Mit einem Spark koppeln (sparkclients.py, plan spark-entkoppeln E4c): name and code from the
// Spark's console; root pairs as `speech-spark teilen koppeln` does. Fresh code; the page shows only fixed words.
const SPK_STAND={laeuft:['Kopplung läuft …','Pairing …'],gekoppelt:['Gekoppelt.','Paired.'],fehler:['Die Kopplung ging nicht. Code abgelaufen oder falsch?','The pairing did not work. Code expired or wrong?']};
let SPK_T=null;
async function spkLoad(msg){const sec=$('spksec'),box=$('spkbox');if(!sec||!box)return;clearTimeout(SPK_T);
  let d;try{d=await (await api('/api/admin/spark/koppeln',{cache:'no-store'})).json()}catch{sec.hidden=true;return}
  sec.hidden=false;const st=SPK_STAND[d.stand];
  box.innerHTML=`<div class="fh">${esc(d.host?t('Dieser Rechner nutzt den Spark ','This computer uses the Spark ')+d.host+'.':t('Noch mit keinem Spark gekoppelt.','Not paired with a Spark yet.'))}</div>
    ${st?`<div class="fh">${esc(t(st[0],st[1]))}</div>`:''}
    <div class="ctl full"><input class="wide" id="spkhost" maxlength="253" placeholder="192.168.178.171" autocomplete="off" aria-label="${esc(t('Name oder Adresse des Spark','Name or address of the Spark'))}">
      <input id="spkcode" maxlength="7" placeholder="ABC-DEF" autocomplete="off" aria-label="${esc(t('Code aus der Spark-Konsole','Code from the Spark-Konsole'))}">
      <button class="b p" type="button" data-spk="koppeln"${d.stand==='laeuft'?' disabled':''}>${esc(t('Koppeln','Pair'))}</button></div>
    <div class="row"><span id="spkmsg" class="fh">${esc(msg||'')}</span></div>`;
  codeLock(box.querySelector('[data-spk="koppeln"]'),'protect');
  if(d.stand==='laeuft')SPK_T=setTimeout(()=>spkLoad(),5000)}
async function spkAct(){const m=x=>{const el=$('spkmsg');if(el)el.textContent=x};
  try{await spcPost('/api/admin/spark/koppeln',{host:$('spkhost').value.trim(),code:$('spkcode').value.trim()});spkLoad(t('Kopplung läuft …','Pairing …'))}
  catch(e){m(e.message)}}
document.addEventListener('click',e=>{const b=e.target.closest('[data-spk]');if(b)spkAct()});
