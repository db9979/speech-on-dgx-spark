// Den Spark anrufen (telefon.py, plan telefon-anruf.md): Funktionen → Den Spark anrufen. Four steps: pick the
// telephone system (or search the home network), the clicks to add the Spark there, the access (saved with a code,
// the password never shown again) with a check in plain words, and the handsets that called, assigned to a profile
// or as a shared phone. Everything from the server or the PBX is text (esc).
let TEL=null;
const telVal=id=>($(id)&&$(id).value||'').trim();
function telSteps(){const a=(TEL&&TEL.anlagen||[]).find(x=>x.id===$('telanlage').value)||{};
  $('telwie').innerHTML=(a.steps||[]).map(s=>`<li>${esc(t(s[0],s[1]))}</li>`).join('');
  $('telhint').textContent=a.hint?t(a.hint[0],a.hint[1]):'';
  if(!telVal('telhost')&&a.host)$('telhost').placeholder=a.host}
function telState(z){const m=$('telstate');if(!m)return;
  m.textContent=z.ok?t('Angemeldet an der Telefonanlage.','Signed in at the telephone system.')+(z.calls?' '+t(`${z.calls} Gespräch(e) gerade.`,`${z.calls} call(s) right now.`):'')
    :z.why==='aus'?t('Ausgeschaltet.','Switched off.'):z.why==='fehlt'?t('Noch nicht eingerichtet: die vier Schritte unten.','Not set up yet: the four steps below.')
    :t('Nicht angemeldet: ','Not signed in: ')+telSay(z.why,z.text);
  m.classList.toggle('err',!z.ok&&z.why!=='aus'&&z.why!=='fehlt')}
const TEL_SAY={zugang:['Benutzername oder Kennwort falsch. Bitte in der Telefonanlage nachsehen und neu eintragen.','User name or password wrong. Please look them up in the telephone system and enter them again.'],
  unbekannt:['Die Anlage kennt diesen Benutzernamen nicht.','The system does not know this user name.'],
  stumm:['Die Anlage antwortet nicht. Ist die Adresse richtig und die Anlage an?','The system does not answer. Is the address right and the system on?'],
  verboten:['Die Anlage lehnt Anmeldungen aus dem Heimnetz ab. In der Anlage das IP-Telefon „Spark“ prüfen.','The system refuses sign-ins from the home network. Check the IP phone "Spark" in the system.'],
  name:['Diese Adresse findet der Spark nicht.','The Spark cannot find this address.'],
  lan:['Die Telefonanlage muss im Heimnetz stehen (eine Adresse wie 192.168.178.1).','The telephone system has to be in the home network (an address like 192.168.178.1).'],
  blocked:['Der Wächter erlaubt diese Adresse nicht.','The Wächter does not allow this address.'],
  abgelehnt:['Die Anlage lehnt die Anmeldung ab.','The system refuses the sign-in.'],
  port:['Der Telefon-Port 31060 ist auf diesem Rechner schon belegt.','The phone port 31060 is already in use on this computer.'],
  ok:['Angemeldet.','Signed in.']};
const telSay=(why,text)=>TEL_SAY[why]?t(TEL_SAY[why][0],TEL_SAY[why][1]):(text||why||'');
function telNums(d){const opts=sel=>`<option value="">${esc(t('Gemeinsames Telefon','Shared phone'))}</option>`+(d.profile||[]).map(p=>`<option value="${esc(p.id)}"${p.id===sel?' selected':''}>${esc(p.name)}</option>`).join('');
  const row=(nr,sel,known,name)=>`<div class="rowin" data-nr="${esc(nr)}" style="margin-top:4px"><b style="min-width:5em">${esc(nr)}</b><select data-nodirty="1">${opts(sel)}</select>`
    +`<input data-nodirty="1" maxlength="40" placeholder="${esc(t('Name, z. B. Küche','Name, e.g. kitchen'))}" value="${esc(name||'')}">`
    +`<button class="b" type="button" data-act="set">${esc(known?t('Ändern','Change'):t('Zuordnen','Assign'))}</button>`+(known?`<button class="b" type="button" data-act="weg">${esc(t('Entfernen','Remove'))}</button>`:'')+'</div>';
  const seen=(d.gesehen||[]).map(x=>row(x.nr,'',false,'')).join('');
  const known=(d.nummern||[]).map(x=>row(x.nr,x.uid,true,x.name)).join('');
  $('telnums').innerHTML=(seen?`<div class="fh">${esc(t('Zuletzt angerufen, noch nicht zugeordnet:','Called lately, not assigned yet:'))}</div>`+seen:'')
    +(known?`<div class="fh">${esc(t('Zugeordnet:','Assigned:'))}</div>`+known:'')
    +(!seen&&!known?`<div class="mut">${esc(t('Noch kein Anruf. Ruf den Spark vom Mobilteil an und lade neu.','No call yet. Call the Spark from a handset and reload.'))}</div>`:'')}
function telShow(d){TEL=d;if(!$('teladmin'))return;const z=d.zugang||{};
  const s=$('telanlage');s.innerHTML=(d.anlagen||[]).map(a=>`<option value="${esc(a.id)}">${esc(a.name)}</option>`).join('');
  s.value=z.anlage||'fritzbox';if(!s.value&&s.options.length)s.selectedIndex=0;
  $('telhost').value=z.host||'';$('telport').value=z.port&&z.port!==5060?z.port:'';$('teluser').value=z.user||'';$('telpw').value='';
  $('telpw').placeholder=z.pw?t('Kennwort (gespeichert, leer lassen = behalten)','Password (saved, leave empty = keep)'):t('Kennwort aus der Anlage','Password from the system');
  $('telvuser').textContent=d.vorschlag&&d.vorschlag.user||'';$('telvpw').textContent=d.vorschlag&&d.vorschlag.pw||'';
  telSteps();telState(d.zustand||{});telNums(d)}
async function telLoad(){if(!$('teladmin')||document.body.classList.contains('mgr'))return;
  try{telShow(await (await api('/api/admin/telefon')).json())}catch{}}
const telMsg=(text,bad)=>{$('telmsg').textContent=text;$('telmsg').classList.toggle('err',!!bad)};
if($('telanlage')){
  $('telanlage').onchange=telSteps;
  $('telsuchen').onclick=async()=>{$('telfound').textContent=t('Suche im Heimnetz …','Searching the home network …');
    try{const d=await (await api('/api/admin/telefon/suchen',{method:'POST'})).json(),g=d.gefunden||[];
      if(!g.length){$('telfound').textContent=t('Keine Anlage gefunden. Wähle sie oben und trag die Adresse in Schritt 3 ein.','No system found. Pick it above and enter the address in step 3.');return}
      const f=g[0];$('telanlage').value=f.anlage;if(!telVal('telhost'))$('telhost').value=f.host;telSteps();
      $('telfound').textContent=t(`${f.name} gefunden unter ${f.ip}.`,`${f.name} found at ${f.ip}.`)}catch(e){$('telfound').textContent=e.message}};
  $('telcopy').onclick=()=>{const u=$('telvuser').textContent,p=$('telvpw').textContent;
    if(!telVal('teluser'))$('teluser').value=u;if(!$('telpw').value)$('telpw').value=p;
    try{navigator.clipboard.writeText(t(`Benutzername: ${u}\nKennwort: ${p}`,`User name: ${u}\nPassword: ${p}`))}catch{}
    telMsg(t('Übernommen und kopiert. In der Anlage genauso eintragen, dann hier speichern.','Taken and copied. Enter the same in the system, then save here.'))};
  $('telsave').onclick=async()=>{telMsg(t('Speichere und melde an …','Saving and signing in …'));
    const b={anlage:$('telanlage').value,host:telVal('telhost'),port:+telVal('telport')||5060,user:telVal('teluser')};if($('telpw').value)b.pw=$('telpw').value;
    try{telShow(await (await api('/api/admin/telefon/zugang',{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify(b)})).json());
      const r=await (await api('/api/admin/telefon/pruefen',{method:'POST'})).json();telMsg(telSay(r.why,r.text),!r.ok);telLoad()}catch(e){telMsg(e.message,true)}};
  $('telcheck').onclick=async()=>{telMsg(t('Prüfe …','Checking …'));
    try{const r=await (await api('/api/admin/telefon/pruefen',{method:'POST'})).json();telMsg(telSay(r.why,r.text),!r.ok);telLoad()}catch(e){telMsg(e.message,true)}};
  $('telreload').onclick=telLoad;
  $('telnums').onclick=async ev=>{const b=ev.target.closest('button[data-act]');if(!b)return;const row=b.closest('[data-nr]');
    const body=b.dataset.act==='weg'?{nr:row.dataset.nr,weg:true}:{nr:row.dataset.nr,uid:row.querySelector('select').value,name:row.querySelector('input').value.trim()};
    try{telShow(await (await api('/api/admin/telefon/nummern',{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)})).json())}catch(e){telMsg(e.message,true)}};
  $('chat.telefon').addEventListener('change',e=>{if(e.target.checked)telLoad()})}
