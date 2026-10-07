// The "Ich" window: profile login, the profile's own pages and the conversation settings.
// ---------------------------------------------------------------- profile of this browser
function setProfile(p){const changed=(p&&p.id)!==(PROFILE&&PROFILE.id);PROFILE=p||null;
  $('profname').textContent=PROFILE?PROFILE.name:t('Gast','Guest');
  if(changed){stopListening(true);stopAnswer();convos.cache=[];openConvo(null);convos.sync().then(()=>{if(!chat.msgs.length)openConvo(latestConvo())})}
  loadSettings();rem.load()}
window.closeProf=()=>{$('profmodal').style.display='none';endEnroll()};
async function showFacts(){const r=await api('/api/profile/memory');const d=await r.json();
  $('profhead').textContent=d.profile.name;
  $('factlist').innerHTML=d.facts.slice().reverse().map(f=>`<li><span>${esc(f.text)}${f.auto?` <em class="auto">${t('automatisch','automatic')}</em>`:''}</span><button class="b" onclick="forgetFact('${esc(f.id)}')">${t('Löschen','Delete')}</button></li>`).join('')||`<li class="mut">${t('Noch nichts gemerkt.','Nothing remembered yet.')}</li>`}
async function showDocs(){if(!DOCS_ON){$('docbox').style.display='none';return}$('docbox').style.display='';
  const l=await (await api('/api/profile/docs')).json();
  $('doclist').innerHTML=l.map(d=>`<li><span>${esc(d.name)}<br><small class="mut">${d.size<1048576?Math.max(1,Math.round(d.size/1024))+' KB':(d.size/1048576).toFixed(1)+' MB'} · ${d.chunks} ${t('Abschnitte','sections')}</small></span><button class="b" onclick="delDoc('${esc(d.id)}','${esc(d.name)}')">${t('Löschen','Delete')}</button></li>`).join('')||`<li class="mut">${t('Noch keine Dokumente.','No documents yet.')}</li>`}
let DOCS_ON=true,SPK_ON=false,CAL_ON=true,HA_ON=false,MAIL_ON=false;
// The "Ich" window: conversation settings for everyone, plus the profile's own pages once logged in.
function ptab(id){document.querySelectorAll('#ptabs button').forEach(b=>b.classList.toggle('on',b.dataset.t===id));
  document.querySelectorAll('#profmodal .ptab').forEach(x=>x.classList.toggle('on',x.id===id))}
function meTabs(){const items=[['setbox',t('Gespräch','Conversation'),!GATE],['loginbox',t('Anmelden','Sign in'),!PROFILE],
    ['factbox',t('Gedächtnis','Memory'),!!PROFILE],['docbox',t('Dokumente','Documents'),PROFILE&&DOCS_ON],['calbox',t('Kalender','Calendar'),PROFILE&&CAL_ON],['mailbox',t('E-Mail','E-mail'),PROFILE&&MAIL_ON],
    ['habox',t('Smart Home','Smart home'),PROFILE&&HA_ON],['voicebox',t('Stimme','Voice'),PROFILE&&SPK_ON],['secbox',t('Sicherheit','Security'),!!PROFILE]].filter(x=>x[2]);
  $('ptabs').innerHTML=items.map(([id,l])=>`<button type="button" data-t="${id}">${esc(l)}</button>`).join('');
  $('ptabs').querySelectorAll('button').forEach(b=>b.onclick=()=>{meLast=b.dataset.t;ptab(b.dataset.t)});return items.map(x=>x[0])}
let meLast='setbox';
const TZ=()=>{try{return Intl.DateTimeFormat().resolvedOptions().timeZone}catch{return ''}};
const CALKIND={icloud:{name:'iCloud',url:'https://caldav.icloud.com',user:1,h:t('Benutzer: deine Apple-ID. Passwort: ein app-spezifisches Passwort von appleid.apple.com.','User: your Apple ID. Password: an app-specific password from appleid.apple.com.')},
  nextcloud:{name:'Nextcloud',url:'',ph:'https://cloud.example.de/remote.php/dav',user:1,h:t('Adresse mit /remote.php/dav, am besten mit App-Passwort.','Address with /remote.php/dav, best with an app password.')},
  caldav:{name:'',url:'',ph:'https://server.example.de/dav/',user:1,h:t('Server-, Konto- oder Kalender-Adresse.','Server, account or calendar address.')},
  ics:{name:'',url:'',ph:'webcal://… oder https://…/basic.ics',user:0,h:t('Ohne Benutzer. Google: „Privatadresse im iCal-Format“, iCloud: „Öffentlicher Kalender“.','No user. Google: "Secret address in iCal format", iCloud: "Public calendar".')}};
function calKind(){const k=CALKIND[$('calkind').value];$('calhint').textContent=k.h;$('calurl').placeholder=k.ph||k.url;
  if(!$('calurl').value||Object.values(CALKIND).some(x=>x.url&&x.url===$('calurl').value))$('calurl').value=k.url;
  if(!$('calname').value||Object.values(CALKIND).some(x=>x.name&&x.name===$('calname').value))$('calname').value=k.name;
  $('caluser').closest('.two2').style.display=k.user?'':'none';if(!k.user){$('caluser').value='';$('calpw').value=''}}
$('calkind').onchange=calKind;
function calRender(d){$('callist').innerHTML=d.calendars.map(c=>`<li><span><b>${esc(c.name)}</b><br><small class="mut">${esc(c.url.replace(/^\w+:\/\//,'').slice(0,48))}</small></span><button class="b" onclick="calRemove('${esc(c.id)}','${esc(c.name)}')">${t('Entfernen','Remove')}</button></li>`).join('')||`<li class="mut">${t('Noch kein Kalender verbunden.','No calendar connected yet.')}</li>`;
  $('caltopics').value=(d.topics||[]).join(', ');calKind();$('caltest').style.display=d.calendars.length?'':'none';$('caladd').open=!d.calendars.length}
async function showCal(){if(!CAL_ON)return;calRender(await (await api('/api/profile/calendar')).json());$('calmsg').textContent='';$('calmsg').className=''}
async function calRemove(id,name){if(!confirm(t('Kalender „','Remove calendar "')+name+t('“ entfernen?','"?')))return;calRender(await (await api('/api/profile/calendar/'+encodeURIComponent(id),{method:'DELETE'})).json())}
const calMsg=(x,err,list)=>{const m=$('calmsg');m.className=err?'err':'';m.innerHTML=esc(x)+(list&&list.length?'<ul class="facts small">'+list.map(e=>`<li>${esc(e)}</li>`).join('')+'</ul>':'')};
$('calsave').onclick=async()=>{calMsg(t('Prüfe den Kalender …','Checking the calendar …'));
  const r=await fetch('/api/profile/calendar',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name:$('calname').value,url:$('calurl').value.trim(),user:$('caluser').value.trim(),password:$('calpw').value,tz:TZ()})});
  const d=await r.json();if(!r.ok){calMsg(t('Nicht hinzugefügt: ','Not added: ')+(d.detail||r.status),true);return}
  ['calname','calurl','caluser','calpw'].forEach(i=>$(i).value='');calRender(d);
  calMsg(t('Hinzugefügt. ','Added. ')+(d.check.events.length?t('Die nächsten Termine:','Next appointments:'):t('Keine Termine in den nächsten 14 Tagen.','No appointments in the next 14 days.')),false,d.check.events)};
$('caltopsave').onclick=async()=>{const d=await (await api('/api/profile/calendar/topics',{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({topics:$('caltopics').value.split(',').map(x=>x.trim()).filter(Boolean)})})).json();calRender(d);calMsg(t('Themen gespeichert.','Topics saved.'))};
$('caltest').onclick=async()=>{calMsg(t('Lese die Kalender …','Reading the calendars …'));
  const r=await fetch('/api/profile/calendar/test',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({tz:TZ()})});const d=await r.json();
  if(!r.ok){calMsg(d.detail||r.status,true);return}
  calMsg(d.events.length?t('Die nächsten Termine:','Next appointments:'):t('Keine Termine in den nächsten 14 Tagen.','No appointments in the next 14 days.'),d.errors.length>0,[...d.events,...d.errors.map(e=>'⚠ '+e)])};
// E-mail per profile, read only; the password is never sent back.
const MAILKIND={icloud:t('Benutzer: deine iCloud-Mailadresse. Passwort: ein neues app-spezifisches Passwort von appleid.apple.com.','User: your iCloud mail address. Password: a new app-specific password from appleid.apple.com.'),
  gmail:t('Benutzer: deine Gmail-Adresse. Passwort: ein App-Passwort (Google-Konto → Sicherheit, braucht die Bestätigung in zwei Schritten).','User: your Gmail address. Password: an app password (Google account → Security, needs 2-step verification).'),
  gmx:t('Vorher in GMX unter E-Mail-Einstellungen → POP3/IMAP-Abruf den Zugriff erlauben.','First allow access in GMX under mail settings → POP3/IMAP.'),
  webde:t('Vorher in web.de unter E-Mail-Einstellungen → POP3/IMAP-Abruf den Zugriff erlauben.','First allow access in web.de under mail settings → POP3/IMAP.'),
  other:t('Nur verschlüsselt (TLS), meist Port 993.','Encrypted (TLS) only, usually port 993.')};
function mailKind(){const k=$('mailkind').value;$('mailhint').textContent=MAILKIND[k];$('mailsrv').style.display=k==='other'?'':'none'}
$('mailkind').onchange=mailKind;
const mailMsg=(x,err,list)=>{const m=$('mailmsg');m.className=err?'err':'';m.innerHTML=esc(x)+(list&&list.length?'<ul class="facts small">'+list.map(e=>`<li>${esc(e)}</li>`).join('')+'</ul>':'')};
function mailRender(d){$('maillist').innerHTML=d.accounts.map(a=>`<li><span><b>${esc(a.name)}</b><br><small class="mut">${esc(a.user)} · ${esc(a.host)}</small></span><button class="b" onclick="mailRemove('${esc(a.id)}','${esc(a.name)}')">${t('Entfernen','Remove')}</button></li>`).join('')||`<li class="mut">${t('Noch kein Postfach verbunden.','No mailbox connected yet.')}</li>`;
  mailKind();$('mailtest').style.display=d.accounts.length?'':'none';$('mailadd').open=!d.accounts.length}
async function showMail(){if(!MAIL_ON)return;mailRender(await (await api('/api/profile/mail')).json());mailMsg('')}
async function mailRemove(id,name){if(!confirm(t('Postfach „','Remove mailbox "')+name+t('“ entfernen?','"?')))return;mailRender(await (await api('/api/profile/mail/'+encodeURIComponent(id),{method:'DELETE'})).json())}
$('mailsave').onclick=async()=>{mailMsg(t('Prüfe das Postfach …','Checking the mailbox …'));
  const r=await fetch('/api/profile/mail',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({kind:$('mailkind').value,name:$('mailname').value,host:$('mailhost').value.trim(),port:$('mailport').value.trim(),user:$('mailuser').value.trim(),password:$('mailpw').value})});
  const d=await r.json();if(!r.ok){mailMsg(t('Nicht hinzugefügt: ','Not added: ')+(d.detail||r.status),true);return}
  ['mailname','mailhost','mailuser','mailpw'].forEach(i=>$(i).value='');mailRender(d);
  mailMsg(t('Hinzugefügt. ','Added. ')+d.check.unread+t(' ungelesen, ',' unread, ')+d.check.total+t(' Mails in den letzten ',' mails in the last ')+d.check.days+t(' Tagen.',' days.'))};
$('mailtest').onclick=async()=>{mailMsg(t('Lese die Postfächer …','Reading the mailboxes …'));
  const r=await fetch('/api/profile/mail/test',{method:'POST'});const d=await r.json();if(!r.ok){mailMsg(d.detail||r.status,true);return}
  mailMsg('',d.accounts.some(a=>!a.ok),d.accounts.map(a=>a.name+': '+(a.ok?a.unread+t(' ungelesen',' unread'):'⚠ '+a.error)))};
// Home Assistant per profile; the token is never sent back, only whether one is stored.
const haMsg=(x,err)=>{$('hamsg').textContent=x;$('hamsg').className='fh'+(err?' err':'')};
function haRender(d){$('haurl').value=d.url||'';$('hatoken').value='';$('hanoverify').checked=d.verify===false;$('haagent').value=d.agent||'';
  $('hatoken').placeholder=d.has_token?t('gespeichert, leer lassen zum Behalten','stored, leave empty to keep'):'';
  $('hastate').textContent=d.has_token?t('Verbunden mit ','Connected to ')+d.url:t('Noch nicht verbunden.','Not connected yet.');$('hadel').style.display=d.has_token?'':'none';
  $('hacodebox').style.display=d.has_token?'':'none';$('hacode').value='';$('hacode').placeholder=d.has_code?t('gesetzt, leer speichern zum Entfernen','set, save empty to remove'):t('kein Codewort','no code word')}
async function showHa(){if(!HA_ON)return;haRender(await (await api('/api/profile/homeassistant')).json());haMsg('')}
$('hasave').onclick=async()=>{haMsg(t('Prüfe die Verbindung …','Checking the connection …'));
  const r=await fetch('/api/profile/homeassistant',{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({url:$('haurl').value.trim(),token:$('hatoken').value.trim(),verify:!$('hanoverify').checked,agent:$('haagent').value.trim()})});
  const d=await r.json();if(!r.ok){haMsg(t('Nicht gespeichert: ','Not saved: ')+(d.detail||r.status),true);return}haRender(d);haMsg(t('Verbunden und gespeichert.','Connected and saved.'))};
$('hadel').onclick=async()=>{if(!confirm(t('Home Assistant trennen?','Disconnect Home Assistant?')))return;haRender(await (await api('/api/profile/homeassistant',{method:'DELETE'})).json());haMsg(t('Getrennt.','Disconnected.'))};
$('hacodesave').onclick=async()=>{const r=await fetch('/api/profile/homeassistant/code',{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({code:$('hacode').value})});
  const d=await r.json();if(!r.ok){haMsg(d.detail||r.status,true);return}haRender(d);haMsg(d.has_code?t('Codewort gespeichert.','Code word saved.'):t('Codewort entfernt.','Code word removed.'))};
$('hatrygo').onclick=async()=>{const text=$('hatry').value.trim();if(!text)return;haMsg(t('Frage Home Assistant …','Asking Home Assistant …'));
  const r=await fetch('/api/profile/homeassistant/test',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({text})});const d=await r.json();
  if(!r.ok){haMsg(d.detail||r.status,true);return}haMsg((d.targets&&d.targets.length?d.targets.join(', ')+': ':'')+d.answer,!d.ok)};
// Voice enrollment for speaker identification: three sentences, each recorded and sent as WAV.
const ENROLL=[['Der Herbstwind treibt bunte Blätter über die stille Straße, und irgendwo bellt ein Hund.','The autumn wind drives colourful leaves across the quiet street, and somewhere a dog barks.'],
  ['Kannst du mir bitte sagen, wie das Wetter morgen wird und ob ich einen Schirm brauche?','Could you please tell me what the weather will be like tomorrow and whether I need an umbrella?'],
  ['Zweiundvierzig Äpfel, sieben Birnen und ein Korb voller Pflaumen stehen auf dem Küchentisch.','Forty-two apples, seven pears and a basket full of plums are on the kitchen table.']];
const enr={i:-1,rec:null,parts:[],stream:null};
async function showVoice(){if(!SPK_ON){$('voicebox').style.display='none';return}$('voicebox').style.display='';
  const d=await (await api('/api/profile/voice')).json();
  $('voicestate').textContent=d.samples?t('Eingelernt: ','Enrolled: ')+d.samples+t(' Aufnahmen. Mehr Aufnahmen machen die Erkennung sicherer.',' recordings. More recordings make recognition more reliable.'):t('Noch nicht eingelernt.','Not enrolled yet.');
  $('voicedel').style.display=d.samples?'':'none';if(enr.i<0)$('voicego').textContent=d.samples?t('Weitere Aufnahmen','More recordings'):t('Stimme einlernen','Enroll voice')}
async function enrollStep(){
  if(enr.rec){const rec=enr.rec;enr.rec=null;await new Promise(r=>{rec.onstop=r;rec.stop()});
    $('voicemsg').textContent=t('Speichere …','Saving …');
    try{const fd=new FormData();fd.append('file',await toWav(new Blob(enr.parts,{type:rec.mimeType})),'voice.wav');
      await api('/api/profile/voice',{method:'POST',body:fd});$('voicemsg').textContent=''}
    catch(e){$('voicemsg').innerHTML=`<span class="err">${esc(e.message)}</span>`;enr.i--}
    await showVoice();if(enr.i>=ENROLL.length-1){endEnroll();$('voicemsg').textContent=t('Fertig.','Done.');return}}
  enr.i++;$('voicesay').style.display='';$('voicesay').textContent=t(...ENROLL[enr.i]);
  enr.parts=[];const mime=['audio/webm;codecs=opus','audio/webm','audio/mp4'].find(m=>MediaRecorder.isTypeSupported(m))||'';
  enr.rec=new MediaRecorder(enr.stream,mime?{mimeType:mime}:{});enr.rec.ondataavailable=e=>{if(e.data.size)enr.parts.push(e.data)};enr.rec.start();
  $('voicego').textContent=(enr.i<ENROLL.length-1?t('Weiter','Next'):t('Fertig','Finish'))+` (${enr.i+1}/${ENROLL.length})`;
  $('voicemsg').textContent=t('● Aufnahme läuft, lies den Satz vor.','● Recording, read the sentence aloud.')}
function endEnroll(){if(enr.rec){try{enr.rec.stop()}catch{}enr.rec=null}if(enr.stream){enr.stream.getTracks().forEach(x=>x.stop());enr.stream=null}
  enr.i=-1;$('voicesay').style.display='none';$('voicego').textContent=$('voicedel').style.display==='none'?t('Stimme einlernen','Enroll voice'):t('Weitere Aufnahmen','More recordings')}
$('voicego').onclick=async()=>{if(enr.i<0){
    if(!window.isSecureContext||!navigator.mediaDevices){$('voicemsg').innerHTML=`<span class="err">${t('Das Mikrofon braucht https.','The microphone needs https.')}</span>`;return}
    try{enr.stream=await navigator.mediaDevices.getUserMedia({audio:{echoCancellation:true,noiseSuppression:true,autoGainControl:true}})}
    catch(e){$('voicemsg').innerHTML=`<span class="err">${esc(e.message)}</span>`;return}}
  enrollStep()};
$('voicedel').onclick=async()=>{if(!confirm(t('Gespeicherte Stimme löschen?','Delete the stored voice?')))return;await api('/api/profile/voice',{method:'DELETE'});showVoice()};
window.delDoc=async(id,n)=>{if(!confirm(t('Dokument „','Delete document "')+n+t('“ löschen?','"?')))return;await api('/api/profile/docs/'+id,{method:'DELETE'});showDocs()};
$('docadd').onclick=()=>$('docfile').click();
$('docfile').onchange=async()=>{const files=[...$('docfile').files];$('docfile').value='';
  for(const f of files){$('docmsg').textContent=t('Lade hoch: ','Uploading: ')+f.name+' …';
    try{const fd=new FormData();fd.append('file',f,f.name);const r=await (await api('/api/profile/docs',{method:'POST',body:fd})).json();
      $('docmsg').textContent=t('Hinzugefügt: ','Added: ')+r.name}
    catch(e){$('docmsg').innerHTML=`<span class="err">${esc(f.name)}: ${esc(e.message)}</span>`;}}
  showDocs()};
window.forgetFact=async id=>{await api('/api/profile/memory/'+encodeURIComponent(id),{method:'DELETE'});showFacts()};
async function openMe(tab){$('profmsg').textContent='';$('profmodal').style.display='grid';
  const tabs=meTabs();ptab(tabs.includes(tab)?tab:tabs[0]);
  $('profhead').textContent=PROFILE?PROFILE.name:GATE?t('Anmelden','Sign in'):t('Gast','Guest');
  $('setscope').textContent=GATE?'':PROFILE?t('Einstellungen gelten auf jedem Gerät dieses Profils; „Hey Spark“ stellt jedes Gerät selbst ein.','Settings apply on every device of this profile; "Hey Spark" is set per device.'):t('Als Gast gelten die Einstellungen nur in diesem Browser. Mit einem Profil merkt sich der Assistent Dinge nur für dich.','As a guest the settings apply only in this browser. With a profile the assistant remembers things just for you.');
  $('proflogout').style.display=PROFILE?'':'none';$('profclose').style.display=GATE?'none':'';
  if(!GATE)renderSet($('setform'),S,saveSet);
  if(PROFILE){try{await showFacts();await showDocs();await showVoice();await showCal();await showMail();await showHa();await showSecurity();await showPush().catch(()=>{})}catch{setProfile(null);openMe('loginbox')}return}
  $('profpin').value='';if(tab==='loginbox')setTimeout(()=>$($('profuser').value?'profpin':'profuser').focus(),50)}
window.openMe=openMe;
$('profbtn').onclick=()=>openMe(meLast);   // same window and page as the settings button
$('profuser').onkeydown=e=>{if(e.key==='Enter')$('profpin').focus()};
$('profpin').onkeydown=e=>{if(e.key==='Enter')$('proflogin').click()};
$('proflogin').onclick=async()=>{try{await api('/api/profile/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name:$('profuser').value,pin:$('profpin').value})});
    if(GATE){location.reload();return}
    const who=await (await fetch('/api/whoami')).json();setProfile(who.profile);closeProf()}
  catch(e){$('profmsg').textContent=/too many/.test(e.message)?t('Zu viele falsche Versuche. Bitte später noch einmal (','Too many wrong attempts. Please try again later (')+(e.message.match(/in (.+)$/)||['',''])[1]+').':t('Name oder PIN falsch.','Wrong name or PIN.')}};
$('proflogout').onclick=async()=>{await fetch('/api/profile/logout',{method:'POST'});if(!PUBLIC&&!ADMIN){location.reload();return}setProfile(null);closeProf()};
$('factclear').onclick=async()=>{if(!confirm(t('Alles vergessen, was sich der Assistent über dich gemerkt hat?','Forget everything the assistant remembered about you?')))return;
  await api('/api/profile/memory',{method:'DELETE'});showFacts()};
// ---------------------------------------------------------------- conversation settings
const SETF=[
  {g:t('Zuhören','Listening'),k:'hands',type:'bool',l:t('Freihändig','Hands-free'),h:t('Nach der Antwort automatisch wieder zuhören.','Listen again automatically after each answer.')},
  {k:'auto',type:'bool',l:t('Bei Stille beenden','Stop on silence'),h:t('Die Aufnahme endet von selbst, wenn du aufhörst zu sprechen.','Recording ends by itself when you stop talking.')},
  {k:'turn',type:'bool',l:t('Natürlicher Sprecherwechsel','Natural turn-taking'),h:t('Erkennt am Satz, ob du fertig bist: Ein fertiger Satz wird sofort beantwortet, bei „und …“, „weil …“ oder „ähm“ wartet der Assistent länger.','Tells from the sentence whether you are done: a finished sentence is answered at once, after "and …", "because …" or "um" the assistant waits longer.')},
  {k:'live',type:'bool',l:t('Live-Transkript','Live transcript'),h:t('Text schon beim Sprechen zeigen; die Antwort kommt etwas früher.','Show the text while you speak; the answer comes a little sooner.')},
  {k:'barge',type:'bool',l:t('Ins Wort fallen','Barge in'),h:t('Losreden unterbricht die Antwort (am besten mit Kopfhörer).','Start talking to interrupt the answer (best with headphones).')},
  {k:'barge_level',type:'sel',l:t('Empfindlichkeit','Sensitivity'),h:t('Wie leicht Geräusche die Antwort unterbrechen.','How easily sounds interrupt the answer.'),o:[['low',t('gering','low')],['mid',t('mittel','medium')],['high',t('hoch','high')]]},
  {g:t('Antwort','Answer'),k:'voice',type:'voice',l:t('Stimme','Voice'),h:t('Leer = Standardstimme des Servers.','Empty = the server\'s default voice.')},
  {k:'speed',type:'range',l:t('Sprechtempo','Speaking rate'),h:t('Schneller oder langsamer, ohne die Stimmlage zu ändern.','Faster or slower without changing the pitch.'),min:0.7,max:1.4,step:0.05},
  {k:'length',type:'sel',l:t('Antwortlänge','Answer length'),h:t('Wie ausführlich der Assistent antwortet.','How detailed the assistant answers.'),o:[['short',t('kurz','short')],['normal',t('normal','normal')],['long',t('ausführlich','detailed')]]},
  {k:'learn',type:'bool',prof:1,l:t('Aus Gesprächen lernen','Learn from conversations'),h:t('Nach einem Gespräch merkt sich der Assistent wenige dauerhafte Dinge über dich. Du siehst und löschst sie unter dem Profil-Knopf.','After a conversation the assistant remembers a few lasting things about you. You can see and delete them under the profile button.')},
  {g:t('Anzeige','Display'),k:'daily',type:'bool',l:t('Jeden Tag neues Gespräch','New conversation every day'),h:t('Am nächsten Tag beginnt automatisch ein neues Gespräch; die alten bleiben im Verlauf.','The next day a new conversation starts by itself; older ones stay in the history.')},
  {k:'timing',type:'bool',l:t('Zeiten anzeigen','Show timings'),h:t('Wie lange Erkennung, Modell und erster Ton gebraucht haben.','How long recognition, model and first audio took.')}];
{let g;SETF.forEach(f=>{g=f.g||g;f.grp=g})}
let VOICES=null;
async function voiceList(admin){if(!PROFILE&&!admin)return [];if(VOICES)return VOICES;try{const r=await fetch(admin?'/api/tts/voices':'/api/assistant/voices');VOICES=r.ok?((await r.json()).voices||[]).filter(x=>typeof x==='string'):[]}catch{VOICES=[]}return VOICES}
// Builds the settings rows into el; onchange(key, value) after each change. Returns a getter.
async function renderSet(el,vals,onchange){const admin=!onchange,voices=await voiceList(admin);const v={...vals};
  const fields=SETF.filter(f=>!(f.k==='voice'||f.prof)||admin||PROFILE);   // guests: default voice, nothing learned
  let prev;el.innerHTML=fields.map(f=>{let ctl;const id='set_'+el.id+'_'+f.k;
    if(f.type==='bool')ctl=`<label class="tgl"><input type="checkbox" id="${id}"${v[f.k]?' checked':''}><i></i></label>`;
    else if(f.type==='sel')ctl=`<select id="${id}">${f.o.map(([a,b])=>`<option value="${a}"${v[f.k]===a?' selected':''}>${esc(b)}</option>`).join('')}</select>`;
    else if(f.type==='voice')ctl=`<select id="${id}"><option value="">${t('Standard','Default')}</option>${[...new Set([...voices,...(v.voice?[v.voice]:[])])].map(x=>`<option${x===v.voice?' selected':''}>${esc(x)}</option>`).join('')}</select>`;
    else ctl=`<input type="range" id="${id}" min="${f.min}" max="${f.max}" step="${f.step}" value="${v[f.k]}"><output id="${id}_o">${Number(v[f.k]).toFixed(2)}×</output>`;
    const head=f.grp!==prev;prev=f.grp;
    return (head?`${f===fields[0]?'':'</div>'}<div class="setpane${f===fields[0]?' on':''}" data-g="${esc(f.grp)}">`:'')+`<div class="setrow"><div class="lbl"><b>${esc(f.l)}</b><span>${esc(f.h)}</span></div>${ctl}</div>`}).join('')+'</div>';
  // one group at a time, so the window stays short
  const groups=[...new Set(fields.map(f=>f.grp))],bar=document.createElement('div');bar.className='ptabs';
  bar.innerHTML=groups.map((g,i)=>`<button type="button"${i?'':' class="on"'}>${esc(g)}</button>`).join('');el.prepend(bar);
  bar.querySelectorAll('button').forEach((b,i)=>b.onclick=()=>{bar.querySelectorAll('button').forEach(x=>x.classList.toggle('on',x===b));
    el.querySelectorAll('.setpane').forEach(x=>x.classList.toggle('on',x.dataset.g===groups[i]))});
  fields.forEach(f=>{const e=$('set_'+el.id+'_'+f.k);e.oninput=e.onchange=ev=>{
    const val=f.type==='bool'?e.checked:f.type==='range'?Number(e.value):e.value;
    if(f.type==='range')$(e.id+'_o').textContent=val.toFixed(2)+'×';
    if(v[f.k]===val||(f.type==='range'&&ev.type==='input'))return;v[f.k]=val;onchange&&onchange(f.k,val)}});
  return()=>({...v})}
function applySet(){$('chathands').checked=!!S.hands;$('chattiming').style.display=S.timing?'':'none'}
async function loadSettings(){let d=null;try{d=await (await fetch('/api/profile/settings')).json()}catch{}
  SDEF={...SDEF,...(d&&d.defaults||{})};S={...SDEF,...(d&&d.settings||{})};
  if(!PROFILE){try{S={...S,...JSON.parse(localStorage.getItem('chatset')||'{}')}}catch{}}
  applySet();if(!S.daily&&!chat.cid&&!chat.msgs.length)openConvo((convos.load()[0]||{}).id||null)}
let setTimer=null;
function saveSet(k,val){S[k]=val;applySet();
  if(!PROFILE){try{const o=JSON.parse(localStorage.getItem('chatset')||'{}');o[k]=val;localStorage.setItem('chatset',JSON.stringify(o))}catch{}return}
  clearTimeout(setTimer);setTimer=setTimeout(()=>api('/api/profile/settings',{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify(S)}).catch(()=>{}),300)}
$('chathands').onchange=()=>saveSet('hands',$('chathands').checked);
const openSet=()=>openMe(meLast);
$('chatset').onclick=openSet;
$('setreset').onclick=async()=>{for(const k of Object.keys(SDEF))S[k]=SDEF[k];
  if(PROFILE)await api('/api/profile/settings',{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify(SDEF)}).catch(()=>{});
  else try{localStorage.removeItem('chatset')}catch{}
  applySet();renderSet($('setform'),S,saveSet)};
// ---------------------------------------------------------------- security: devices and logins
const when=s=>s?new Date(s*1000).toLocaleString([], {dateStyle:'short',timeStyle:'short'}):t('noch nie','never');
async function showSecurity(){const d=await (await api('/api/profile/security')).json();secRender(d.devices);
  const ev={profile_login:t('Anmeldung','Sign-in'),profile_login_failed:t('Falsche PIN','Wrong PIN'),profile_logout_all:t('Überall abgemeldet','Logged out everywhere'),profile_device_removed:t('Gerät gesperrt','Device blocked')};
  $('secev').innerHTML=d.events.map(e=>`<li><span>${esc(ev[e.event]||e.event)} <small class="mut">${when(e.t)} · ${esc(e.ip||'')}</small></span></li>`).join('')||`<li class="mut">–</li>`}
function secRender(devs){$('secdev').innerHTML=devs.map(x=>`<li><span>${esc(x.name)}<br><small class="mut">${t('zuletzt','last used')}: ${x.last?when(x.last.t)+' · '+esc(x.last.ip||''):t('noch nie','never')}</small></span><button class="b" onclick="secDrop('${esc(x.id)}','${esc(x.name)}')">${t('Sperren','Block')}</button></li>`).join('')||`<li class="mut">${t('Keine Geräte mit Schlüssel.','No devices with a key.')}</li>`}
window.secDrop=async(id,n)=>{if(!confirm(t('Gerät „','Block device "')+n+t('“ sperren? Sein Schlüssel gilt dann nicht mehr.','"? Its key stops working.')))return;
  secRender((await (await api('/api/profile/devices/'+encodeURIComponent(id),{method:'DELETE'})).json()).devices)};
$('seclogoutall').onclick=async()=>{if(!confirm(t('Dein Profil in allen anderen Browsern abmelden?','Log your profile out in all other browsers?')))return;
  try{await api('/api/profile/logout-all',{method:'POST'});$('secmsg').textContent=t('Erledigt.','Done.');showSecurity()}catch(e){$('secmsg').textContent=e.message}};
// ---------------------------------------------------------------- reminders as push notifications
// Only with https and a trusted certificate (e.g. behind a reverse proxy); iPhone: from the home screen.
const pushOk=()=>'serviceWorker' in navigator&&'PushManager' in window&&window.isSecureContext;
async function pushSub(){try{const r=await navigator.serviceWorker.getRegistration();return r&&await r.pushManager.getSubscription()}catch{return null}}
async function showPush(){const box=$('pushbox');box.style.display=PROFILE&&REM_ON?'':'none';if(!PROFILE||!REM_ON)return;
  if(!pushOk()){$('pushstate').textContent=/iPhone|iPad/.test(navigator.userAgent)&&!navigator.standalone?t('Auf dem iPhone: die Seite über „Teilen → Zum Home-Bildschirm“ als App anlegen und dort einschalten.','On an iPhone: add the page to the home screen ("Share → Add to Home Screen") and switch it on there.'):t('Geht nur über https mit gültigem Zertifikat (z. B. hinter deinem Proxy). Hier klingeln Erinnerungen, solange die Seite offen ist.','Needs https with a valid certificate (e.g. behind your proxy). Here reminders ring while the page is open.');
    $('pushgo').style.display=$('pushoff').style.display='none';return}
  const s=await pushSub();$('pushgo').style.display=s?'none':'';$('pushoff').style.display=s?'':'none';
  $('pushstate').textContent=s?t('An: Erinnerungen kommen als Mitteilung, auch wenn die Seite zu ist.','On: reminders arrive as notifications, also when the page is closed.'):t('Aus: Erinnerungen klingeln nur, solange die Seite offen ist.','Off: reminders ring only while the page is open.')}
$('pushgo').onclick=async()=>{try{if(await Notification.requestPermission()!=='granted'){$('pushstate').textContent=t('Mitteilungen sind für diese Seite nicht erlaubt (Browser- oder Systemeinstellungen).','Notifications are not allowed for this page (browser or system settings).');return}
    const reg=await navigator.serviceWorker.register('/sw.js');await navigator.serviceWorker.ready;
    const {key}=await (await api('/api/profile/push')).json();
    const raw=Uint8Array.from(atob(key.replace(/-/g,'+').replace(/_/g,'/')+'='.repeat((4-key.length%4)%4)),c=>c.charCodeAt(0));
    const sub=await reg.pushManager.subscribe({userVisibleOnly:true,applicationServerKey:raw});
    await api('/api/profile/push',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({subscription:sub.toJSON(),name:navigator.userAgent.slice(0,60)})});showPush()}
  catch(e){$('pushstate').textContent=t('Hat nicht geklappt: ','Did not work: ')+e.message}};
$('pushoff').onclick=async()=>{const s=await pushSub();if(s){try{await api('/api/profile/push',{method:'DELETE',headers:{'Content-Type':'application/json'},body:JSON.stringify({endpoint:s.endpoint})})}catch{}await s.unsubscribe().catch(()=>{})}showPush()};
