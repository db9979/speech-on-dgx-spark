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
    <div class="fh" id="wxname">${p.name?t('Gefunden: ','Found: ')+esc(p.name):''}</div>
    <div class="row" style="margin-top:8px"><button class="b" type="button" id="wxtest"${p.name?'':' disabled'}>${t('Vorhersage zeigen','Show forecast')}</button></div>
    <div class="fh" id="wxmsg"></div>`;
  xbind(box,showWx);
  $('wxsave').onclick=async()=>{xmsg('wxmsg',t('Suche den Ort …','Looking up the place …'));
    try{const r=await (await api('/api/profile/weather',xjson('PUT',{place:$('wxplace').value.trim()}))).json();await showWx();xmsg('wxmsg',r.sample||t('Ort gelöscht.','Place removed.'))}
    catch(e){xmsg('wxmsg',e.message,true)}};
  $('wxtest').onclick=async()=>{xmsg('wxmsg','…');try{xmsg('wxmsg',(await (await api('/api/profile/weather/test',xjson('POST'))).json()).text)}catch(e){xmsg('wxmsg',e.message,true)}}}
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
async function showExtras(){await showWx().catch(()=>{});await showCon().catch(()=>{});await showPar().catch(()=>{})}
