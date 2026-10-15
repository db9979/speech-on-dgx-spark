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

// ---------------------------------------------------------------- Ich → Telefon (telefon_ich.py, Stufe T2): own numbers
// confirmed with a code typed on a call from that number, the Telefon-PIN (fresh code, never shown), the handsets the
// admin assigned (read only) and the profile's calls (when, how long, how many questions; delete one or all).
let TEL_ON=false;
const TEL_ART={intern:['Mobilteil','Handset'],gemeinsam:['Gemeinsames Telefon','Shared phone'],bestaetigung:['Nummer bestätigt','Number confirmed']};
const telWhen=s=>new Date(s*1000).toLocaleString(L==='en'?'en-GB':'de-DE',{day:'2-digit',month:'2-digit',hour:'2-digit',minute:'2-digit'});
const telDur=s=>s<60?t(`${s} s`,`${s} s`):t(`${Math.round(s/60)} min`,`${Math.round(s/60)} min`);
function telMeNums(d){const now=Date.now()/1000;
  return (d.nummern||[]).map(n=>`<div class="rowin" data-nid="${esc(n.id)}" style="margin-top:6px"><b style="min-width:9em">${esc(n.nr)}</b>${n.name?`<span class="mut">${esc(n.name)}</span>`:''}`
    +(n.ok?`<span class="ok">${esc(t('bestätigt','confirmed'))}</span>`:n.code?`<span>${esc(t('Code','Code'))} <b class="telcode">${esc(n.code)}</b> · ${esc(t(`noch ${Math.max(1,Math.round((n.bis-now)/60))} min`,`${Math.max(1,Math.round((n.bis-now)/60))} min left`))}</span>`
      :`<span class="mut">${esc(t('nicht bestätigt','not confirmed'))}</span><button class="b" type="button" data-act="code">${esc(t('Neuer Code','New code'))}</button>`)
    +`<button class="b" type="button" data-act="weg">${esc(t('Entfernen','Remove'))}</button></div>`).join('')}
async function showTel(){const box=$('telbox');if(!box)return;if(!PROFILE||!TEL_ON){box.innerHTML='';return}
  let d;try{d=await (await api('/api/profile/telefon')).json()}catch(e){box.innerHTML=`<div class="fh">${esc(e.message)}</div>`;return}
  const waits=(d.nummern||[]).some(n=>!n.ok&&n.code);
  box.innerHTML=`<div class="intro">${esc(t('Ruf den Spark vom Telefon an: vom Mobilteil im Haus, das der Admin dir zugeordnet hat. Hier trägst du deine eigenen Rufnummern ein, legst eine Telefon-PIN fest und siehst deine Telefonate.','Call the Spark from a phone: from the handset in the house the admin assigned to you. Here you add your own phone numbers, set a phone PIN and see your calls.'))}</div>`
    +(d.angemeldet?'':`<div class="card"><div class="mut">${esc(t('Der Spark ist gerade nicht an der Telefonanlage angemeldet.','The Spark is not signed in at the telephone system right now.'))}</div></div>`)
    +`<div class="card"><h3>${esc(t('Meine Rufnummern','My phone numbers'))}</h3><div class="mut">${esc(t('Handy oder Festnetz. Eine Nummer gilt erst, wenn sie bestätigt ist: ruf den Spark von dieser Nummer an (die Rufnummer, bei der er klingelt, weiß dein Admin) und tippe den Code. So kann niemand deine Nummer auf sein Profil legen.','Mobile or landline. A number counts only once it is confirmed: call the Spark from that number (your admin knows the number it rings at) and type the code. So nobody can put your number on their profile.'))}</div>`
    +`<div id="telmynums">${telMeNums(d)||`<div class="mut" style="margin-top:6px">${esc(t('Noch keine Rufnummer.','No phone number yet.'))}</div>`}</div>`
    +((d.nummern||[]).length<d.max?`<div class="two2" style="margin-top:8px"><div><label for="telmynr">${esc(t('Rufnummer','Phone number'))}</label><input id="telmynr" inputmode="tel" maxlength="24" autocomplete="tel" placeholder="0170 1234567"></div><div><label for="telmyname">${esc(t('Name (frei)','Name (optional)'))}</label><input id="telmyname" maxlength="40" placeholder="${esc(t('z. B. Handy','e.g. mobile'))}"></div></div><div class="row"><button class="b" type="button" id="telmyadd">${esc(t('Eintragen','Add'))}</button></div>`:'')
    +(waits?`<div class="mut">${esc(t(`Ein Code gilt ${d.code_min} Minuten. Der Spark nimmt den Anruf nur dafür an und legt danach auf.`,`A code counts ${d.code_min} minutes. The Spark takes the call only for that and hangs up afterwards.`))}</div>`:'')
    +`<div class="fh" id="telmymsg"></div></div>`
    +`<div class="card"><h3>${esc(t('Telefon-PIN','Phone PIN'))}</h3><div class="mut">${esc(t(`Erkennt der Spark deine Stimme am Telefon nicht sicher, tippst du die PIN und dann die Raute (#). Danach weiß er für dieses Gespräch, dass du es bist. ${d.pin_len[0]} bis ${d.pin_len[1]} Ziffern; drei falsche sperren die PIN an diesem Telefon für eine halbe Stunde.`,`If the Spark does not clearly know your voice on the phone, type the PIN and then the hash key (#). For this call it then knows it is you. ${d.pin_len[0]} to ${d.pin_len[1]} digits; three wrong ones lock the PIN at that phone for half an hour.`))}</div>`
    +`<div class="two2"><div><label for="telmypin">${esc(d.pin?t('Neue PIN','New PIN'):t('PIN','PIN'))}</label><input id="telmypin" type="password" inputmode="numeric" autocomplete="new-password" maxlength="${d.pin_len[1]}" placeholder="${esc(d.pin?t('gesetzt','set'):t('keine PIN','no PIN'))}"></div><div><label>&nbsp;</label><button class="b" type="button" id="telmypinset">${esc(t('PIN speichern','Save PIN'))}</button></div></div>`
    +(d.pin?`<div class="row"><button class="b" type="button" id="telmypinweg">${esc(t('PIN entfernen','Remove PIN'))}</button></div>`:'')+`<div class="fh" id="telmypinmsg"></div></div>`
    +((d.mobilteile||[]).length?`<div class="card"><h3>${esc(t('Meine Mobilteile','My handsets'))}</h3>${d.mobilteile.map(h=>`<div class="rowin"><b>${esc(h.nr)}</b><span class="mut">${esc(h.name||'')}</span></div>`).join('')}<div class="mut">${esc(t('Mobilteile ordnet der Admin zu (Funktionen → Den Spark anrufen).','The admin assigns handsets (Features → Calling the Spark).'))}</div></div>`:'')
    +`<div class="card"><h3>${esc(t('Meine Telefonate','My calls'))}</h3>`+((d.anrufe||[]).length?d.anrufe.map(a=>`<div class="rowin" data-aid="${esc(a.id)}"><b style="min-width:7em">${esc(telWhen(a.t))}</b><span>${esc(t(...(TEL_ART[a.art]||TEL_ART.intern)))} · ${esc(telDur(a.s))} · ${esc(t(`${a.fragen} Fragen`,`${a.fragen} questions`))}</span><button class="b" type="button" data-act="del">${esc(t('Löschen','Delete'))}</button></div>`).join('')
      +`<div class="row"><button class="b" type="button" id="telmycallsdel">${esc(t('Alle löschen','Delete all'))}</button></div><div class="mut">${esc(t('Nur wann, wie lange und wie viele Fragen. Die Fragen selbst stehen in deinem Verlauf.','Only when, how long and how many questions. The questions themselves are in your history.'))}</div>`
      :`<div class="mut">${esc(t('Noch kein Telefonat.','No call yet.'))}</div>`)+`</div>`;
  const msg=(id,x,bad)=>{$(id).textContent=x;$(id).classList.toggle('err',!!bad)};
  const add=async(nr,name)=>{const {r,d:x}=await apiTry('/api/profile/telefon/nummern',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({nr,name})});
    if(!r.ok){msg('telmymsg',String(x.detail||r.status),true);return}showTel()};
  if($('telmyadd')){codeLock($('telmyadd'),'confirm');$('telmyadd').onclick=()=>add($('telmynr').value.trim(),$('telmyname').value.trim())}
  $('telmynums').onclick=async ev=>{const b=ev.target.closest('button[data-act]');if(!b)return;const row=b.closest('[data-nid]');
    if(b.dataset.act==='code'){add(row.querySelector('b').textContent,'');return}
    if(!confirm(t('Diese Rufnummer entfernen?','Remove this phone number?')))return;
    const {r,d:x}=await apiTry('/api/profile/telefon/nummern/'+encodeURIComponent(row.dataset.nid),{method:'DELETE'});if(!r.ok){msg('telmymsg',String(x.detail||r.status),true);return}showTel()};
  codeLock($('telmypinset'),'protect');
  $('telmypinset').onclick=async()=>{const {r,d:x}=await apiTry('/api/profile/telefon/pin',{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({pin:$('telmypin').value})});
    $('telmypin').value='';if(!r.ok){msg('telmypinmsg',String(x.detail||r.status),true);return}showTel()};
  if($('telmypinweg'))$('telmypinweg').onclick=async()=>{if(!confirm(t('Die Telefon-PIN entfernen?','Remove the phone PIN?')))return;
    const {r,d:x}=await apiTry('/api/profile/telefon/pin',{method:'DELETE'});if(!r.ok){msg('telmypinmsg',String(x.detail||r.status),true);return}showTel()};
  box.querySelectorAll('[data-aid] button[data-act="del"]').forEach(b=>b.onclick=async()=>{
    await apiTry('/api/profile/telefon/anrufe?id='+encodeURIComponent(b.closest('[data-aid]').dataset.aid),{method:'DELETE'});showTel()});
  if($('telmycallsdel'))$('telmycallsdel').onclick=async()=>{if(!confirm(t('Alle Telefonate aus dieser Liste löschen?','Delete all calls from this list?')))return;
    await apiTry('/api/profile/telefon/anrufe',{method:'DELETE'});showTel()};
  if(typeof labelTables==='function')labelTables()}
