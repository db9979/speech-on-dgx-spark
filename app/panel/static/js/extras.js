// "Ich" → Wetter, Kontakte, Pakete (weather.py, contacts.py, parcels.py). Each one stays off until the
// profile switches it on here; the admin only allows it.
let WX_ON=false,CON_ON=false,PAR_ON=false;
const xjson=(m,b)=>({method:m,headers:{'Content-Type':'application/json'},body:JSON.stringify(b||{})});
const xmsg=(id,x,err)=>{const m=$(id);if(m){m.textContent=x||'';m.className='fh'+(err?' err':'')}};
const xsw=(k,l,h)=>`<div class="setrow"><div class="lbl"><b>${esc(l)}</b><span>${esc(h)}</span></div><label class="tgl"><input type="checkbox" data-xk="${k}"${S[k]?' checked':''}><i></i></label></div>`;
function xbind(box,after){box.querySelectorAll('[data-xk]').forEach(e=>e.onchange=()=>{saveSet(e.dataset.xk,e.checked);if(after)setTimeout(after,400)})}
// ---------------------------------------------------------------- weather
async function showWx(){const box=$('wxbox');if(!PROFILE||!WX_ON){box.innerHTML='';return}
  let d={place:{}};try{d=await (await api('/api/profile/weather')).json()}catch{}
  const p=d.place||{};
  box.innerHTML=`<div class="intro">${t('Frag „Wie wird das Wetter morgen?“ oder „Regnet es heute noch?“. Die Vorhersage kommt von Open-Meteo, der Assistent liest sie als feste Sätze vor. Nach draußen gehen nur die Koordinaten deines Orts.','Ask "What is the weather tomorrow?" or "Will it rain today?". The forecast comes from Open-Meteo and is read as fixed sentences. Only your place\'s coordinates leave the house.')}</div>
    ${xsw('wx_on',t('Wetter für mich nutzen','Use weather for me'),t('Auch im Tagesbriefing und beim Wetterhinweis unter „Von selbst“.','Also in the daily briefing and the weather note under "Proactive".'))}
    <label>${t('Dein Ort','Your place')}</label><div class="rowin"><input id="wxplace" value="${esc(p.place||'')}" placeholder="${t('z. B. Ulm','e.g. Ulm')}" autocomplete="off"><button class="b" type="button" id="wxsave">${t('Speichern','Save')}</button></div>
    <div class="fh" id="wxname">${p.name?t('Gefunden: ','Found: ')+esc(p.name):t('Ortsname, gern mit Postleitzahl („76307 Karlsbad“), oder Koordinaten („48.87, 8.50“).','Place name, with postcode if you like ("76307 Karlsbad"), or coordinates ("48.87, 8.50").')}</div>
    <div id="wxchoices"></div>
    <div class="row" style="margin-top:8px"><button class="b" type="button" id="wxtest"${p.name?'':' disabled'}>${t('Vorhersage zeigen','Show forecast')}</button></div>
    <div class="fh" id="wxmsg"></div>`;
  xbind(box,showWx);
  $('wxsave').onclick=async()=>{xmsg('wxmsg',t('Suche den Ort …','Looking up the place …'));
    try{const place=$('wxplace').value.trim(),r=await (await api('/api/profile/weather',xjson('PUT',{place}))).json();await showWx();xmsg('wxmsg',r.sample||t('Ort gelöscht.','Place removed.'));wxChoices(place,r.choices||[])}
    catch(e){xmsg('wxmsg',e.message,true)}};
  $('wxtest').onclick=async()=>{xmsg('wxmsg','…');try{xmsg('wxmsg',(await (await api('/api/profile/weather/test',xjson('POST'))).json()).text)}catch(e){xmsg('wxmsg',e.message,true)}}}
// several places fit ("Karlsbad"): the best one is set, the others are one tap away
function wxChoices(place,list){const box=$('wxchoices');if(!box)return;if(list.length<2){box.innerHTML='';return}
  box.innerHTML=`<div class="fh">${t('Nicht der richtige Ort? Wähle:','Not the right place? Pick one:')}</div><div class="row" style="flex-wrap:wrap;gap:6px">${list.map((c,i)=>`<button class="b" type="button" data-wxi="${i}">${esc(c.name+(c.country?' ('+c.country+')':'')+(c.postcodes&&c.postcodes.length?' '+c.postcodes.slice(0,2).join(', '):''))}</button>`).join('')}</div>`;
  box.querySelectorAll('[data-wxi]').forEach(b=>b.onclick=async()=>{const c=list[+b.dataset.wxi];
    try{const r=await (await api('/api/profile/weather',xjson('PUT',{place,pick:{lat:c.lat,lon:c.lon,name:c.name}}))).json();await showWx();xmsg('wxmsg',r.sample)}catch(e){xmsg('wxmsg',e.message,true)}})}
// ---------------------------------------------------------------- contacts
const CONKIND={icloud:['iCloud','https://contacts.icloud.com',t('Benutzer: deine Apple-ID. Passwort: ein app-spezifisches Passwort von appleid.apple.com (dasselbe wie beim Kalender geht).','User: your Apple ID. Password: an app-specific password from appleid.apple.com (the calendar one works too).')],
  nextcloud:['Nextcloud','',t('Adresse mit /remote.php/dav, am besten mit App-Passwort.','Address with /remote.php/dav, best with an app password.')],
  carddav:['','',t('Adresse des CardDAV-Servers oder des Adressbuchs.','Address of the CardDAV server or address book.')]};
async function showCon(){const box=$('conbox');if(!PROFILE||!CON_ON){box.innerHTML='';return}
  let d={accounts:[],count:0,errors:[]};try{d=await (await api('/api/profile/contacts')).json()}catch{}
  const when=d.fetched?new Date(d.fetched*1000).toLocaleString(L==='en'?'en-GB':'de-DE',{day:'2-digit',month:'2-digit',hour:'2-digit',minute:'2-digit'}):'';
  box.innerHTML=`<div class="intro">${t('Frag „Wie ist die Nummer von Anna?“ oder „Wann hat Bert Geburtstag?“. Der Assistent liest dein Adressbuch nur; einmal am Tag holt er es neu und speichert es verschlüsselt auf dem Spark.','Ask "What is Anna\'s number?" or "When is Bert\'s birthday?". The assistant only reads your address book; it fetches it once a day and keeps it encrypted on the Spark.')}</div>
    ${xsw('con_on',t('Kontakte für mich nutzen','Use contacts for me'),t('Nummern, E-Mail-Adressen und Geburtstage; in Mails stehen Namen statt Adressen.','Numbers, e-mail addresses and birthdays; mails show names instead of addresses.'))}
    ${xsw('con_bday',t('Geburtstage im Tagesbriefing','Birthdays in the daily briefing'),t('Wer heute und morgen Geburtstag hat.','Who has a birthday today and tomorrow.'))}
    <ul class="facts">${d.accounts.map(a=>`<li><span><b>${esc(a.name)}</b><br><small class="mut">${esc(a.url.replace(/^\w+:\/\//,'').slice(0,48))}</small></span><button class="b" type="button" data-cdel="${esc(a.id)}">${t('Entfernen','Remove')}</button></li>`).join('')||`<li class="mut">${t('Noch kein Adressbuch verbunden.','No address book connected yet.')}</li>`}</ul>
    ${d.accounts.length?`<div class="fh">${d.count} ${t('Kontakte','contacts')}${when?t(', zuletzt geholt ',', last fetched ')+when:''}${d.errors.length?' · ⚠ '+esc(d.errors.join('; ')):''}</div>`:''}
    <details id="conadd" style="margin-top:10px"${d.accounts.length?'':' open'}><summary>${t('Adressbuch hinzufügen','Add address book')}</summary>
      <label>${t('Anbieter','Provider')}</label><select id="conkind"><option value="icloud">iCloud</option><option value="nextcloud">Nextcloud</option><option value="carddav">${t('anderer CardDAV-Server','other CardDAV server')}</option></select>
      <div class="fh" id="conhint"></div>
      <label>${t('Name','Name')}</label><input id="conname" autocomplete="off">
      <label>${t('Adresse','Address')}</label><input id="conurl" autocapitalize="off" autocomplete="off">
      <div class="two2"><div><label>${t('Benutzer','User')}</label><input id="conuser" autocapitalize="off" autocomplete="off"></div><div><label>${t('Passwort','Password')}</label><input type="password" id="conpw" autocomplete="new-password"></div></div>
      <div class="row" style="margin-top:8px"><button class="b p" type="button" id="consave">${t('Prüfen und hinzufügen','Check and add')}</button></div></details>
    ${d.accounts.length?`<div class="row" style="margin-top:8px"><button class="b" type="button" id="conref">${t('Jetzt abholen','Fetch now')}</button></div>
    <label>${t('Ausprobieren','Try it')}</label><div class="rowin"><input id="contry" placeholder="${t('Name','Name')}" autocomplete="off"><button class="b" type="button" id="contrygo">${t('Suchen','Search')}</button></div>`:''}
    <div class="fh" id="conmsg"></div>`;
  xbind(box);
  const kind=()=>{const k=CONKIND[$('conkind').value];$('conhint').textContent=k[2];$('conname').value=k[0];$('conurl').value=k[1];$('conurl').placeholder=k[1]||'https://cloud.example.de/remote.php/dav'};
  $('conkind').onchange=kind;kind();
  box.querySelectorAll('[data-cdel]').forEach(b=>b.onclick=async()=>{if(!confirm(t('Adressbuch entfernen?','Remove address book?')))return;await api('/api/profile/contacts/'+encodeURIComponent(b.dataset.cdel),{method:'DELETE'});showCon()});
  $('consave').onclick=async()=>{xmsg('conmsg',t('Lese das Adressbuch …','Reading the address book …'));
    try{const r=await (await api('/api/profile/contacts',xjson('POST',{name:$('conname').value,url:$('conurl').value.trim(),user:$('conuser').value.trim(),password:$('conpw').value}))).json();
      await showCon();xmsg('conmsg',t('Hinzugefügt: ','Added: ')+r.check+t(' Kontakte gelesen.',' contacts read.'))}catch(e){xmsg('conmsg',t('Nicht hinzugefügt: ','Not added: ')+e.message,true)}};
  if($('conref'))$('conref').onclick=async()=>{xmsg('conmsg','…');try{await api('/api/profile/contacts/refresh',xjson('POST'));await showCon();xmsg('conmsg',t('Neu geholt.','Fetched again.'))}catch(e){xmsg('conmsg',e.message,true)}};
  if($('contrygo'))$('contrygo').onclick=async()=>{try{const r=await (await api('/api/profile/contacts/find',xjson('POST',{name:$('contry').value}))).json();xmsg('conmsg',r.lines.join(' · ')||t('Nichts gefunden.','Nothing found.'))}catch(e){xmsg('conmsg',e.message,true)}}}
// ---------------------------------------------------------------- parcels
async function showPar(fresh){const box=$('parbox');if(!PROFILE||!PAR_ON){box.innerHTML='';return}
  let d={on:false,lines:[],errors:[]};try{d=await (await api('/api/profile/parcels'+(fresh?'?fresh=true':''))).json()}catch{}
  box.innerHTML=`<div class="intro">${t('Frag „Kommt heute ein Paket?“. Der Assistent liest dazu die Versandmails von DHL, Hermes, DPD, GLS, UPS und Amazon der letzten 14 Tage in deinem Postfach. Er fragt keine Paketfirma und ändert nichts.','Ask "Is a parcel coming today?". The assistant reads the shipping mails of DHL, Hermes, DPD, GLS, UPS and Amazon of the last 14 days in your mailbox. It asks no carrier and changes nothing.')}</div>
    ${xsw('par_on',t('Pakete für mich erkennen','Recognise parcels for me'),t('Auch im Tagesbriefing und unter „Von selbst“ („Paket kommt heute“).','Also in the daily briefing and under "Proactive" ("parcel comes today").'))}
    ${d.on?`<ul class="facts">${d.lines.map(x=>`<li><span>${esc(x)}</span></li>`).join('')||`<li class="mut">${t('Kein offenes Paket in den Mails.','No open parcel in the mails.')}</li>`}</ul>
    ${d.errors.length?`<div class="fh err">${esc(d.errors.join('; '))}</div>`:''}
    <div class="row" style="margin-top:8px"><button class="b" type="button" id="parrun">${t('Jetzt prüfen','Check now')}</button></div>`:''}`;
  xbind(box,()=>showPar(true));
  if($('parrun'))$('parrun').onclick=()=>showPar(true)}
// ---------------------------------------------------------------- tasks and shopping list (tasks.py)
let TASK_ON=false,TG_ON=false,APP_ON=false,PEB_ON=false;
async function showTasks(){const box=$('taskbox');if(!PROFILE||!TASK_ON){box.innerHTML='';return}
  let d={lists:{}};try{d=await (await api('/api/profile/tasks')).json()}catch{}
  const on=!!S.tasks_on,base=location.origin;
  const list=(k,l)=>{const tg=l.target;return `<h3 style="margin:14px 0 4px">${esc(L==='en'?l.name_en:l.name)}</h3>
    <div class="fh" style="margin-top:0">${tg?t('Liegt in der CalDAV-Liste ','Lives in the CalDAV list ')+'<b>'+esc(tg.name)+'</b>':t('Liegt auf dem Spark.','Lives on the Spark.')}${l.sent?' · '+l.sent+t(' ans iPhone übergeben',' handed to the iPhone'):''}</div>
    ${l.error?`<div class="fh err">${esc(l.error)}</div>`:''}
    <ul class="facts">${l.items.map(x=>`<li><span>${esc(x.text)}</span><button class="b" type="button" data-tdone="${k}" data-id="${esc(x.id)}">${t('Erledigt','Done')}</button></li>`).join('')||`<li class="mut">${t('Leer.','Empty.')}</li>`}</ul>
    <div class="rowin"><input data-tnew="${k}" placeholder="${t('Neuer Eintrag (mehrere mit Komma)','New entry (several with commas)')}" autocomplete="off"><button class="b" type="button" data-tadd="${k}">${t('Hinzufügen','Add')}</button></div>
    <div class="row" style="margin-top:6px"><select data-ttgt="${k}"><option value="">${t('Auf dem Spark (Kurzbefehl fürs iPhone)','On the Spark (shortcut for the iPhone)')}</option>${tg?`<option value="${esc(tg.acc+'|'+tg.url)}" selected>${esc(tg.name)}</option>`:''}</select>
      <button class="b" type="button" data-tfind="${k}">${t('CalDAV-Listen suchen','Find CalDAV lists')}</button></div>`};
  box.innerHTML=`<div class="intro">${t('Sag „Setz Milch auf die Einkaufsliste“ oder „Was steht auf meiner Aufgabenliste?“. Hinzufügen geht sofort; Abhaken und Löschen per Sprache erst nach deinem „Ja“.','Say "Put milk on the shopping list" or "What is on my to-do list?". Adding happens at once; ticking off and deleting by voice only after your "Yes".')}</div>
    ${xsw('tasks_on',t('Listen für mich nutzen','Use lists for me'),t('Einkaufsliste und Aufgaben. Offene Aufgaben kommen ins Tagesbriefing.','Shopping list and tasks. Open tasks go into the daily briefing.'))}
    ${on?Object.entries(d.lists).map(([k,l])=>list(k,l)).join(''):''}
    ${on?`<details style="margin-top:12px"><summary>${t('iPhone-Kurzbefehl für die Erinnerungen-App','iPhone shortcut for the Reminders app')}</summary><ol class="fh">
      <li>${t('Unter Profile bei deinem Profil ein Gerät „iPhone Listen“ anlegen und den Schlüssel kopieren (der Siri-Schlüssel geht auch).','Under Profiles add a device "iPhone lists" to your profile and copy the key (the Siri key works too).')}</li>
      <li>${t('Kurzbefehle-App → neuer Kurzbefehl → „Inhalte von URL abrufen“: ','Shortcuts app → new shortcut → "Get contents of URL": ')}<code>${esc(base)}/api/tasks/inbox?list=einkauf</code>${t(', Methode POST, Header ',', method POST, header ')}<code>X-Speech-Device</code>${t(' = dein Schlüssel.',' = your key.')}</li>
      <li>${t('„Text teilen“ nach „Neue Zeilen“, dann „Wiederholen mit jedem“ → „Erinnerung hinzufügen“ (Liste „Einkauf“ wählen).','"Split text" by "New lines", then "Repeat with each" → "Add new reminder" (pick your shopping list).')}</li>
      <li>${t('Automation: z. B. „Wenn ich die Erinnerungen-App öffne“ oder stündlich, ohne Nachfrage ausführen. Für Aufgaben dasselbe mit list=aufgaben.','Automation: e.g. "When I open Reminders" or hourly, run without asking. For tasks the same with list=aufgaben.')}</li>
      <li>${t('Übergebene Einträge verschwinden hier aus der Liste; ab dann ist die Erinnerungen-App zuständig.','Handed-over entries leave this list; from then on the Reminders app is in charge.')}</li></ol></details>`:''}
    <div class="fh" id="taskmsg"></div>`;
  xbind(box,showTasks);
  box.querySelectorAll('[data-tadd]').forEach(b=>b.onclick=async()=>{const k=b.dataset.tadd,inp=box.querySelector(`[data-tnew="${k}"]`);if(!inp.value.trim())return;
    try{await api('/api/profile/tasks/'+k,xjson('POST',{text:inp.value}));await showTasks()}catch(e){xmsg('taskmsg',e.message,true)}});
  box.querySelectorAll('[data-tdone]').forEach(b=>b.onclick=async()=>{try{await api('/api/profile/tasks/'+b.dataset.tdone+'/done',xjson('POST',{ids:[b.dataset.id]}));await showTasks()}catch(e){xmsg('taskmsg',e.message,true)}});
  box.querySelectorAll('[data-tfind]').forEach(b=>b.onclick=async()=>{const k=b.dataset.tfind,sel=box.querySelector(`[data-ttgt="${k}"]`);xmsg('taskmsg',t('Suche Aufgabenlisten in deinen Kalender-Konten …','Looking for task lists in your calendar accounts …'));
    try{const r=await (await api('/api/profile/tasks/collections')).json();const cur=sel.value;
      sel.innerHTML=`<option value="">${t('Auf dem Spark (Kurzbefehl fürs iPhone)','On the Spark (shortcut for the iPhone)')}</option>`+r.collections.map(c=>`<option value="${esc(c.acc+'|'+c.url)}">${esc(c.name+' ('+c.acc_name+')')}</option>`).join('');sel.value=cur;
      xmsg('taskmsg',(r.collections.length?r.collections.length+t(' Aufgabenlisten gefunden. Jetzt oben auswählen.',' task lists found. Pick one above.'):t('Keine Aufgabenliste gefunden. Erst unter Kalender ein CalDAV-Konto (z. B. Nextcloud) verbinden.','No task list found. First connect a CalDAV account (e.g. Nextcloud) under Calendar.'))+(r.errors.length?' ⚠ '+r.errors.join('; '):''))}catch(e){xmsg('taskmsg',e.message,true)}});
  box.querySelectorAll('[data-ttgt]').forEach(sel=>sel.onchange=async()=>{const [acc,...u]=sel.value.split('|');
    try{await api('/api/profile/tasks/target',xjson('PUT',{list:sel.dataset.ttgt,acc,url:u.join('|')}));await showTasks();xmsg('taskmsg',t('Gespeichert.','Saved.'))}catch(e){xmsg('taskmsg',e.message,true)}})}
// ---------------------------------------------------------------- Telegram (telegram.py)
async function showTg(){const box=$('tgbox');if(!PROFILE||!TG_ON){box.innerHTML='';return}
  let d={enabled:false,bot:'',linked:null};try{d=await (await api('/api/profile/telegram')).json()}catch{}
  if(!d.enabled){box.innerHTML=`<div class="intro">${t('Der Admin hat noch keinen Telegram-Bot eingerichtet.','The admin has not set up a Telegram bot yet.')}</div>`;return}
  const lk=d.linked;
  box.innerHTML=`<div class="intro">${t('Schreib dem Assistenten über Telegram oder schick eine Sprachnachricht, von überall. Bot: ','Write to the assistant over Telegram or send a voice message, from anywhere. Bot: ')}<b>@${esc(d.bot)}</b></div>
    ${lk?`<ul class="facts"><li><span>${t('Verbunden mit ','Linked with ')}<b>${esc(lk.name||'Telegram')}</b></span><button class="b" type="button" id="tgunlink">${t('Trennen','Unlink')}</button></li></ul>`
      :`<div class="row"><button class="b p" type="button" id="tglink">${t('Mit Telegram verbinden','Link with Telegram')}</button></div><div class="fh" id="tgcode"></div>`}
    ${xsw('tg_voice',t('Antworten auch als Sprachnachricht','Answers also as voice messages'),t('In der Spark-Stimme. Umschalten geht auch mit /stimme.','In the Spark voice. Also with /stimme.'))}
    ${xsw('tg_push',t('Mitteilungen auch über Telegram','Notifications also over Telegram'),t('Erinnerungen, Tagesbriefing und „Von selbst“-Hinweise (Termine und Mails nur mit dem nächsten Schalter).','Reminders, daily briefing and proactive notes (appointments and mail only with the next switch).'))}
    ${xsw('tg_private',t('Persönliches über Telegram erlauben','Allow personal data over Telegram'),t('Kalender, E-Mail, Kontakte, Pakete und Dokumente. Die Nachrichten laufen über die Server von Telegram.','Calendar, e-mail, contacts, parcels and documents. The messages pass Telegram\'s servers.'))}
    ${ALLOW.images&&S.images_on?xsw('tg_images',t('Fotos über Telegram','Photos over Telegram'),t('Schickst du dem Bot ein Foto, sieht es sich das Sprachmodell an; die Bildunterschrift ist die Frage. Für eine Rückfrage auf das Foto antworten. Fotos laufen über die Server von Telegram.','Send the bot a photo and the language model looks at it; the caption is the question. Reply to the photo for a follow-up. Photos pass Telegram\'s servers.')):''}
    ${xsw('tg_ha',t('Smart Home über Telegram schalten','Switch the smart home over Telegram'),t('Nur mit deinem Codewort (Ich → Smart Home). Ohne Codewort schaltet Telegram nie.','Only with your code word (Me → Smart home). Without a code word Telegram never switches.'))}
    <div class="fh" id="tgmsg"></div>`;
  xbind(box);
  if($('tglink'))$('tglink').onclick=async()=>{try{const r=await (await api('/api/profile/telegram/link',xjson('POST'))).json();
    $('tgcode').innerHTML=`${t('Öffne ','Open ')}<a href="${esc(r.url)}" target="_blank" rel="noopener">${esc(r.url)}</a>${t(' und tippe „Starten“, oder schick dem Bot ',' and tap "Start", or send the bot ')}<code>/start ${esc(r.code)}</code>. ${t('Der Code gilt ','The code is valid for ')}${r.minutes} ${t('Minuten.','minutes.')}`}catch(e){xmsg('tgmsg',e.message,true)}};
  if($('tgunlink'))$('tgunlink').onclick=async()=>{if(!confirm(t('Telegram trennen?','Unlink Telegram?')))return;await api('/api/profile/telegram',{method:'DELETE'});showTg()}}
async function tgAdmin(){if(!$('tgadmin'))return;let d={};try{d=await (await api('/api/admin/telegram')).json()}catch{return}
  $('tgstate').dataset.need=d.has_token?'':'1';setTimeout(()=>typeof guidesCount==='function'&&guidesCount());$('tgstate').textContent=d.has_token?t('Bot: @','Bot: @')+(d.bot||'?')+' · '+d.linked+t(' Profile verbunden.',' profiles linked.')+(d.conflict?t(' Achtung: Ein anderes Programm nutzt denselben Token. Token nur an einer Stelle nutzen oder bei @BotFather einen neuen holen.',' Note: another program uses the same token. Use it in one place only or get a new one from @BotFather.'):''):t('Noch kein Token gespeichert.','No token stored yet.');
  $('tgdel').style.display=d.has_token?'':'none';
  $('tgsave').onclick=async()=>{$('tgstate').textContent=t('Frage Telegram …','Asking Telegram …');try{await api('/api/admin/telegram',xjson('PUT',{token:$('tgtoken').value.trim()}));$('tgtoken').value='';tgAdmin()}catch(e){$('tgstate').textContent=e.message}};
  $('tgdel').onclick=async()=>{if(!confirm(t('Token löschen? Der Bot antwortet dann nicht mehr.','Delete the token? The bot stops answering.')))return;try{await api('/api/admin/telegram',{method:'DELETE'});tgAdmin()}catch(e){$('tgstate').textContent=e.message}}}
async function apnsAdmin(){if(!$('apnsadmin'))return;let d={};try{d=await (await api('/api/admin/apns')).json()}catch{return}
  $('apnskid').value=d.key_id||'';$('apnsteam').value=d.team||'';$('apnsbundle').value=d.bundle||'';$('apnsmode').value=d.sandbox?'dev':'prod';
  if(!d.has_key)$('apnsmode').value='dev';
  $('apnsstate').dataset.need=d.has_key?'':'1';setTimeout(()=>typeof guidesCount==='function'&&guidesCount());$('apnsstate').textContent=!d.available?t('Auf dem Spark fehlt das Paket cryptography.','The package cryptography is missing on the Spark.'):d.has_key?t('Schlüssel gespeichert · ','Key stored · ')+d.phones+t(' iPhones angemeldet.',' iPhones signed up.'):t('Noch kein Schlüssel gespeichert.','No key stored yet.');
  $('apnsdel').style.display=d.has_key?'':'none';
  $('apnssave').onclick=async()=>{const f=$('apnsfile').files[0];let key='';if(f){if(f.size>1000){$('apnsstate').textContent=t('Das ist keine .p8-Datei.','That is not a .p8 file.');return}key=await f.text()}
    try{await api('/api/admin/apns',xjson('PUT',{key,key_id:$('apnskid').value.trim(),team:$('apnsteam').value.trim(),bundle:$('apnsbundle').value.trim(),sandbox:$('apnsmode').value==='dev'}));$('apnsfile').value='';apnsAdmin()}catch(e){$('apnsstate').textContent=e.message}};
  $('apnsdel').onclick=async()=>{if(!confirm(t('Apple-Schlüssel löschen? Push an die App hört dann auf.','Delete the Apple key? Push to the app stops.')))return;try{await api('/api/admin/apns',{method:'DELETE'});apnsAdmin()}catch(e){$('apnsstate').textContent=e.message}}}
async function iupdAdmin(){if(!$('iupdadmin'))return;let d={};try{d=await (await api('/api/admin/iphone-update')).json()}catch{return}
  $('iupdlist').innerHTML=(d.profiles||[]).map(p=>`<tr><td>${esc(p.name)}<div class="intro sm">${p.mfa?t('mit zweitem Anmeldeschritt','with second login step'):t('ohne zweiten Anmeldeschritt: nur Hinweise','without second login step: notices only')}</div></td><td style="white-space:nowrap"><label><input type="checkbox" data-u="${esc(p.id)}" data-k="notify"${p.notify?' checked':''}> ${t('Hinweise','Notices')}</label> <label><input type="checkbox" data-u="${esc(p.id)}" data-k="start"${p.start?' checked':''}${p.mfa?'':' disabled'}> ${t('Starten','Start')}</label></td></tr>`).join('')||`<tr><td class="mut">${t('Noch keine Profile.','No profiles yet.')}</td></tr>`;
  $('iupdlist').querySelectorAll('input[data-u]').forEach(x=>x.onchange=async()=>{const u=x.dataset.u,q=k=>$('iupdlist').querySelector(`input[data-u="${CSS.escape(u)}"][data-k="${k}"]`).checked;
    try{await api('/api/admin/iphone-update/'+encodeURIComponent(u),xjson('PUT',{notify:q('notify'),start:q('start')}));$('iupdmsg').textContent=t('Gespeichert.','Saved.')}catch(e){$('iupdmsg').textContent=e.message}iupdAdmin()})}
async function showExtras(){for(const f of [showWx,showCon,showPar,showTasks,showTg,showApp,showPeb].concat(typeof showAgent==='function'?[showAgent]:[]).concat(typeof showMsg==='function'?[showMsg]:[]).concat(typeof showEsp==='function'?[showEsp]:[]))await f().catch(()=>{})}
// ---------------------------------------------------------------- iPhone app (iphone.py)
async function showApp(){const box=$('appbox');if(!box)return;if(!PROFILE||!APP_ON){box.innerHTML='';return}
  let d={phones:[],on:false,minutes:10};try{d=await (await api('/api/profile/iphone')).json()}catch{}
  const when=x=>x?new Date(x.t*1000).toLocaleString([], {dateStyle:'short',timeStyle:'short'}):t('noch nie','never');
  box.innerHTML=`<div class="intro">${t('Die App „Spark“ fürs iPhone: Knopf drücken, fragen, die Antwort kommt mit der Spark-Stimme. „Hey Siri, Frag Spark“ geht dann auch ohne Kurzbefehl. Jedes iPhone bekommt einen eigenen Schlüssel, der nur fragen und hören darf.','The "Spark" app for the iPhone: press the button, ask, the answer comes in the Spark voice. "Hey Siri, Ask Spark" then works without a shortcut. Each iPhone gets its own key that may only ask and listen.')}</div>
    ${xsw('app_on',t('iPhone-App für mich','iPhone app for me'),t('Aus: Deine gekoppelten iPhones bekommen sofort keine Antwort mehr.','Off: your paired iPhones get no answer any more, at once.'))}
    ${xsw('app_listen',t('Dauerhaft zuhören erlauben','Allow listening all the time'),t('Die App darf auf das Weckwort lauschen (in der App einschalten). Das Weckwort erkennt das iPhone selbst, erst danach geht Ton an den Spark.','The app may listen for the wake word (switch it on in the app). The iPhone itself recognises the wake word; only then does sound go to the Spark.'))}
    ${xsw('app_act',t('Route und Anrufe auf dem iPhone','Routes and calls on the iPhone'),t('Der Assistent darf eine Route in Karten öffnen oder einen Kontakt anrufen. Das iPhone fragt jedes Mal vorher.','The assistant may open a route in Maps or call a contact. The iPhone asks every time first.'))}
    ${xsw('app_ha',t('Smart Home aus der App','Smart home from the app'),t('Schalten und Abfragen wie im Panel, mit deinem Codewort. Aus: Die App fragt dein Zuhause gar nicht.','Switching and asking as in the panel, with your code word. Off: the app does not touch your home at all.'))}
    ${xsw('app_ios',t('Apple Erinnerungen auf dem iPhone','Apple Reminders on the iPhone'),t('Die App trägt Erinnerungen des Spark nach deinem „Ja“ in die Erinnerungen-App ein (Liste „Spark“) und holt neue Einträge der Einkaufs- und Aufgabenliste dorthin. Kurzbefehle dürfen etwas auf deine Listen setzen.','After your "yes" the app puts the Spark\'s reminders into the Reminders app (list "Spark") and brings new shopping and to-do entries there. Shortcuts may add to your lists.'))}
    ${xsw('app_docs',t('Dokumente aus der App ablegen','Store documents from the app'),t('In der App ein PDF, eine Textdatei oder ein Foto mit Text unter „Meine Dokumente“ speichern. Das iPhone liest den Text selbst, auch von gescannten Seiten.','Store a PDF, a text file or a photo with text from the app under "My documents". The iPhone reads the text itself, scanned pages too.'))}
    ${ALLOW.images&&S.images_on?xsw('app_images',t('Fotos aus der App ansehen lassen','Let the model look at photos from the app'),t('Fotos aus der App gehen als Bild an das Sprachmodell auf dem Spark, nicht nur ihr Text. Aus: Das iPhone liest wie bisher nur die Schrift selbst.','Photos from the app go to the language model on the Spark as pictures, not only their text. Off: the iPhone reads only the writing itself, as before.')):''}
    ${ROOM_ON?xsw('app_room',t('Raum-Modus in der App zeigen','Show room mode in the app'),t('Zeigt im Chat, im Widget und auf dem Sperrbildschirm, welches Gerät gerade zuhört, mit „Beenden“. Starten geht dort nicht.','Shows in the chat, the widget and on the lock screen which device listens right now, with "Stop". Starting is not possible there.')):''}
    ${S.app_ha?xsw('app_car_ha',t('Smart Home auch im Auto','Smart home in the car too'),t('Mit CarPlay schalten, mit deinem Codewort. Aus: Im Auto fragt die App dein Zuhause gar nicht.','Switch with CarPlay, with your code word. Off: in the car the app does not touch your home.')):''}
    ${d.push?xsw('app_push',t('Meldungen aufs iPhone','Notifications to the iPhone'),t('Erinnerungen, Morgenrunde und Hinweise kommen auch bei geschlossener App. Apple sieht nur „Neue Nachricht“, den Text holt die App vom Spark.','Reminders, the morning briefing and notes come also with the app closed. Apple only sees "New message"; the app fetches the text from the Spark.'))+(S.app_push?`<div class="row"><button class="b" type="button" id="apptest">${t('Test-Meldung schicken','Send a test message')}</button></div>`:''):''}
    <ul class="facts">${d.phones.map(p=>`<li><span><b>${esc(p.name)}</b><br><small class="mut">${t('zuletzt','last used')}: ${esc(when(p.last))}</small></span><button class="b" type="button" data-appdel="${esc(p.id)}" data-appname="${esc(p.name)}">${t('Entfernen','Remove')}</button></li>`).join('')||`<li class="mut"><span>${t('Noch kein iPhone gekoppelt.','No iPhone paired yet.')}</span></li>`}</ul>
    ${d.on?`<div class="row"><button class="b p" type="button" id="apppair">${t('iPhone koppeln','Pair an iPhone')}</button></div>`:''}
    <div id="appqr"></div><div class="fh" id="appmsg"></div>`;
  xbind(box,showApp);
  box.querySelectorAll('[data-appdel]').forEach(b=>b.onclick=async()=>{if(!confirm(t('„','"')+b.dataset.appname+t('“ entfernen? Sein Schlüssel gilt dann sofort nicht mehr.','" remove? Its key stops working at once.')))return;
    try{await api('/api/profile/iphone/'+encodeURIComponent(b.dataset.appdel),{method:'DELETE'});showApp()}catch(e){xmsg('appmsg',e.message,true)}});
  if($('apptest'))$('apptest').onclick=async()=>{xmsg('appmsg',t('Schicke …','Sending …'));try{const r=await (await api('/api/profile/iphone/push-test',xjson('POST'))).json();xmsg('appmsg',(r.ok?t('Angekommen bei Apple: ','Accepted by Apple: '):t('Nicht geklappt: ','Did not work: '))+r.why,!r.ok)}catch(e){xmsg('appmsg',e.message,true)}};
  if($('apppair'))$('apppair').onclick=async()=>{try{const r=await (await api('/api/profile/iphone/pair',xjson('POST',{base:location.origin}))).json();
    $('appqr').innerHTML=`${r.qr?`<div class="mfaqr" style="background:#fff;display:inline-block;padding:4px;border-radius:6px;margin:6px 0">${r.qr}</div>`:''}
      <div class="fh">${t('Am PC: den Code mit der Kamera des iPhones scannen. Auf dem iPhone: ','On a PC: scan the code with the iPhone camera. On the iPhone: ')}<a href="${esc(r.link)}">${t('in der App öffnen','open in the app')}</a>. ${t('Gilt ','Valid for ')}${r.minutes} ${t('Minuten und nur einmal.','minutes and once only.')}</div>`}
    catch(e){xmsg('appmsg',e.message,true)}}}
// ---------------------------------------------------------------- Pebble watch (pebblewatch.py)
// The watch app's settings on the phone take one line instead of address and key; the address is the
// plain panel port at home (the Pebble app does not trust the self-signed certificate).
function pebBase(){return location.protocol==='https:'&&location.port&&location.port!=='443'?'http://'+location.hostname+':31080':location.origin}
async function showPeb(){const box=$('pebbox');if(!box)return;if(!PROFILE||!PEB_ON){box.innerHTML='';return}
  let d={watches:[],on:false,minutes:10};try{d=await (await api('/api/profile/pebble')).json()}catch{}
  const when=x=>x?new Date(x.t*1000).toLocaleString([], {dateStyle:'short',timeStyle:'short'}):t('noch nie','never');
  box.innerHTML=`<div class="intro">${t('Die Uhr-App „Spark“ für Pebble: Knopf drücken, fragen, die Antwort kommt als Text und über den Lautsprecher der Uhr. Jede Uhr bekommt einen eigenen Schlüssel, der nur fragen darf.','The "Spark" watch app for Pebble: press the button, ask, the answer comes as text and through the watch speaker. Each watch gets its own key that may only ask.')}</div>
    ${xsw('pebble_on',t('Pebble-Uhr für mich','Pebble watch for me'),t('Aus: Deine gekoppelten Uhren bekommen sofort keine Antwort mehr.','Off: your paired watches get no answer any more, at once.'))}
    <ul class="facts">${d.watches.map(p=>`<li><span><b>${esc(p.name)}</b><br><small class="mut">${t('zuletzt','last used')}: ${esc(when(p.last))}</small></span><button class="b" type="button" data-pebdel="${esc(p.id)}">${t('Entfernen','Remove')}</button></li>`).join('')||`<li class="mut"><span>${t('Noch keine Uhr gekoppelt.','No watch paired yet.')}</span></li>`}</ul>
    ${d.on?`<label>${t('Adresse, unter der das Handy den Spark erreicht','Address the phone reaches the Spark at')}</label><input id="pebbase" value="${esc(pebBase())}" autocomplete="off">
      <div class="row"><button class="b p" type="button" id="pebpair">${t('Pebble koppeln','Pair a Pebble')}</button></div>`:''}
    <div id="pebcode"></div><div class="fh" id="pebmsg"></div>`;
  xbind(box,showPeb);
  box.querySelectorAll('[data-pebdel]').forEach(b=>b.onclick=async()=>{if(!confirm(t('Uhr entfernen? Ihr Schlüssel gilt dann sofort nicht mehr.','Remove the watch? Its key stops working at once.')))return;
    try{await api('/api/profile/pebble/'+encodeURIComponent(b.dataset.pebdel),{method:'DELETE'});showPeb()}catch(e){xmsg('pebmsg',e.message,true)}});
  if($('pebpair'))$('pebpair').onclick=async()=>{try{const r=await (await api('/api/profile/pebble/pair',xjson('POST',{base:$('pebbase').value.trim()}))).json();
    const c=$('pebcode');c.innerHTML='';const inp=document.createElement('input');inp.readOnly=true;inp.value=r.setup;inp.id='pebsetup';c.appendChild(inp);
    const row=document.createElement('div');row.className='row';const cp=document.createElement('button');cp.type='button';cp.className='b p';cp.textContent=t('Kopieren','Copy');row.appendChild(cp);c.appendChild(row);
    const fh=document.createElement('div');fh.className='fh';fh.textContent=t('In der Pebble-App am Handy bei „Spark“ die Einstellungen öffnen und unter „Einrichtungscode“ einfügen, dann Speichern. Gilt ','In the Pebble app on the phone open the settings of "Spark", paste under "Setup code", then Save. Valid for ')+r.minutes+t(' Minuten und nur einmal.',' minutes and once only.');c.appendChild(fh);
    cp.onclick=async()=>{try{await navigator.clipboard.writeText(r.setup);xmsg('pebmsg',t('Kopiert.','Copied.'))}catch{inp.select();xmsg('pebmsg',t('Markiert: jetzt kopieren.','Selected: copy it now.'))}}}
    catch(e){xmsg('pebmsg',e.message,true)}}}
// ---------------------------------------------------------------- Bus und Bahn (transit.py)
let TR_ON=false;
const TRDAYS=['Mo','Di','Mi','Do','Fr','Sa','So'];
async function showTr(){const box=$('trbox');if(!PROFILE||!TR_ON){box.innerHTML='';return}
  let d={};try{d=await (await api('/api/profile/transit')).json()}catch{}
  const h=d.home,c=d.commute;
  box.innerHTML=`<div class="intro">${t('Frag „Wann fährt der nächste Bus?“ oder „Wie komme ich nach Karlsruhe?“. Die Zeiten kommen aus dem Fahrplandienst und werden als feste Sätze vorgelesen, (+3) heißt drei Minuten Verspätung.','Ask "When does the next bus leave?" or "How do I get to Karlsruhe?". Times come from the timetable service and are read as fixed sentences, (+3) means three minutes late.')}</div>
    ${xsw('transit_on',t('Bus und Bahn für mich nutzen','Use bus and train for me'),t('Braucht deine Haltestelle.','Needs your stop.'))}
    <label>${t('Deine Haltestelle','Your stop')}</label><div class="rowin"><input id="trq" value="${esc(h?h.name:'')}" placeholder="${t('z. B. Karlsbad Bahnhof','e.g. Ulm Hbf')}" autocomplete="off"><button class="b" type="button" id="trfind">${t('Suchen','Search')}</button></div>
    <div id="trhits"></div>
    <h3 style="margin:14px 0 4px">${t('Pendelstrecke (für Verspätungshinweise)','Commute (for delay notes)')}</h3>
    <div class="fh" style="margin-top:0">${c?t('Nach ','To ')+esc(c.to.name)+t(' um ',' at ')+esc(c.at)+' · '+c.days.map(i=>TRDAYS[i]).join(', '):t('Keine eingestellt.','None set.')}</div>
    <div class="rowin"><input id="trto" placeholder="${t('Ziel, z. B. Karlsruhe Hbf','Destination')}" autocomplete="off"><input id="trat" type="time" value="${esc(c?c.at:'07:30')}" style="max-width:120px"><button class="b" type="button" id="trtofind">${t('Suchen','Search')}</button></div>
    <div class="row" style="flex-wrap:wrap;gap:6px;margin-top:6px">${TRDAYS.map((n,i)=>`<label class="chk"><input type="checkbox" data-trd="${i}"${(c?c.days:[0,1,2,3,4]).includes(i)?' checked':''}> ${n}</label>`).join('')}</div>
    <div id="trtohits"></div>
    ${c?`<div class="row" style="margin-top:6px"><button class="b" type="button" id="trnocom">${t('Pendelstrecke löschen','Remove commute')}</button></div>`:''}
    <div class="row" style="margin-top:10px"><button class="b" type="button" id="trtest"${h?'':' disabled'}>${t('Abfahrten zeigen','Show departures')}</button></div>
    <div class="fh" id="trmsg"></div>`;
  xbind(box);
  const hits=(id,list,pick)=>{$(id).innerHTML=list.length?`<div class="row" style="flex-wrap:wrap;gap:6px;margin-top:6px">${list.map((x,i)=>`<button class="b" type="button" data-i="${i}">${esc(x.name)}</button>`).join('')}</div>`:`<div class="fh">${t('Nichts gefunden.','Nothing found.')}</div>`;
    $(id).querySelectorAll('[data-i]').forEach(b=>b.onclick=()=>pick(list[+b.dataset.i]))};
  const search=async q=>(await (await api('/api/profile/transit/find',xjson('POST',{q}))).json()).stops;
  const put=async body=>{try{await api('/api/profile/transit',xjson('PUT',body));await showTr();xmsg('trmsg',t('Gespeichert.','Saved.'))}catch(e){xmsg('trmsg',e.message,true)}};
  $('trfind').onclick=async()=>{try{hits('trhits',await search($('trq').value),x=>put({home:x}))}catch(e){xmsg('trmsg',e.message,true)}};
  $('trtofind').onclick=async()=>{try{const days=[...box.querySelectorAll('[data-trd]')].filter(x=>x.checked).map(x=>+x.dataset.trd);
    hits('trtohits',await search($('trto').value),x=>put({commute:{to:x,at:$('trat').value,days}}))}catch(e){xmsg('trmsg',e.message,true)}};
  if($('trnocom'))$('trnocom').onclick=()=>put({commute:null});
  $('trtest').onclick=async()=>{xmsg('trmsg','…');try{xmsg('trmsg',(await (await api('/api/profile/transit/test',xjson('POST'))).json()).text)}catch(e){xmsg('trmsg',e.message,true)}}}
