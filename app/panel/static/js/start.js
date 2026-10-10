// Admin login and start-up.
// ---------------------------------------------------------------- login
// Guests see only the assistant; everything else needs the panel password (cookie login).
let ADMIN=false,PUBLIC=true,GATE=false;
window.showLogin=()=>{if($('login').style.display==='none'){$('login').style.display='grid';$('loginmsg').textContent='';$('loginpw').value=$('logincode').value='';$('logincodebox').style.display='none';setTimeout(()=>$('loginpw').focus(),50)}};
$('loginbtn').onclick=showLogin;$('logincancel').onclick=()=>{$('login').style.display='none';if(GATE)openMe('loginbox')};
$('loginform').onsubmit=async e=>{e.preventDefault();
  try{const r=await (await api('/api/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({password:$('loginpw').value,code:$('logincode').value,trust:$('logintrust').checked})})).json();
    // right password, the second step is on: the code field comes next
    if(r.code){$('logincodebox').style.display='';$('loginmsg').textContent='';$('logincode').focus();return}
    location.reload()}
  catch(err){$('loginmsg').textContent=/too many/.test(err.message)?t('Zu viele falsche Versuche, bitte später noch einmal.','Too many wrong attempts, please try again later.'):/wrong code/.test(err.message)?t('Code falsch.','Wrong code.'):t('Falsches Passwort.','Wrong password.')}};
$('logoutbtn').onclick=async()=>{await fetch('/api/logout',{method:'POST'});location.reload()};
$('pwset').onclick=async()=>{try{await api('/api/password',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({old:$('pwold').value,new:$('pwnew').value})});
  $('pwold').value=$('pwnew').value='';$('pwmsg').textContent=t('Passwort geändert.','Password changed.')}catch(e){$('pwmsg').innerHTML=`<span class="err">${esc(e.message)}</span>`}};
(async()=>{let who={admin:true};try{who=await (await fetch('/api/whoami')).json()}catch{}
  if(who.version!==undefined)WHO_FLAGS=whoFlags(who);ADMIN=who.admin;DOCS_ON=who.documents!==false;REM_ON=who.reminders!==false;SPK_ON=!!who.speaker_id;CAL_ON=who.calendar!==false;HA_ON=!!who.homeassistant;MAIL_ON=!!who.mail;TIDY_ON=!!who.mail_tidy;PRO_ON=!!who.proactive;ROOM_ON=!!who.room;RV_ON=!!who.room_voices;RHA_ON=!!who.room_ha;RFAR_ON=!!who.room_remote;WX_ON=!!who.weather;CON_ON=!!who.contacts;PAR_ON=!!who.parcels;TASK_ON=!!who.tasks;AGENT_ON=!!who.agent;MSG_ON=!!who.messages;TR_ON=!!who.transit;TG_ON=!!who.telegram;ESP_ON=!!who.esp32;APP_ON=!!who.iphone;APP_PANEL=!!who.iphone_panel;PEB_ON=!!who.pebble;RM_ON=!!who.remarkable;RMSEND_ON=!!who.remarkable_send;MYST_ON=!!who.my_status;VOR_ON=!!who.person_priority;TRACE_ON=!!who.trace;coadmStart(who);room.show();setFaceKind(who.face);const a=who.assistant||{};setProfile(who.profile);$('ver').textContent=t('Speech auf DGX Spark','Speech on DGX Spark')+' '+(who.version||'');
  SETUP=who.setup||null;if(typeof joinHash==='function'&&joinHash())return;   // an invitation or "Am Handy weitermachen" (join.js)
  if(!ADMIN){document.body.classList.add('guest');
    CFG={tts:{default_voice:a.default_voice},asr:{default_language:a.asr_language},panel:{https_port:a.https_port}};
    PUBLIC=who.public!==false;
    const toAdmin=location.hash==='#admin';if(toAdmin){history.replaceState(null,'',location.pathname+location.search);showLogin()}   // the main admin's way in
    // without "Assistent ohne Passwort" guests are locked out, but profiles still sign in with name and PIN
    if(!PUBLIC&&!who.profile){GATE=true;$('profgate').style.display='';$('profadmin').style.display='';if(!toAdmin)openMe('loginbox');return}
    // one shell for everybody (plan „Vereinheitlichen“ Phase 7): a signed-in profile gets the same menu as the admin,
    // with only what it may (Assistent, Ich); guests keep the plain page with the assistant
    if(who.profile){document.body.classList.remove('guest');document.body.classList.add('adm','prof')}
    // "Spark verwalten" only for a profile with an admin role; the main admin opens the page with #admin (above)
    if(who.profile&&who.admin_role)document.body.classList.add('mayadm');}
  else{$('logoutbtn').style.display='inline-block';document.body.classList.add('adm');hdrH()}
  document.querySelector('nav button[data-s=chat]').click();       // the assistant is the start page
  try{const s=sessionStorage.getItem('versec');sessionStorage.removeItem('versec');if(s&&s!=='chat'&&$(s))goSec(s)}catch{}
  // "Im Panel öffnen" in the iPhone app: #go=<page>, #cfg=<settings page> or #me=<Ich area>, only known names
  try{const h=/^#(go|cfg|me)=([a-z]{2,12})$/.exec(location.hash);if(h){history.replaceState(null,'',location.pathname+location.search);
    if(h[1]==='go'&&ADMIN&&h[2]!=='chat'&&$(h[2])&&$(h[2]).tagName==='SECTION')goSec(h[2]);
    else if(h[1]==='cfg'&&ADMIN&&$('pane-'+h[2]))goCfg(h[2]);
    else if(h[1]==='me'&&PROFILE&&/box$/.test(h[2])&&$(h[2]))openMe(h[2])}}catch{}
  try{if(sessionStorage.getItem('flagsreload')){sessionStorage.removeItem('flagsreload');const e=$('updtoast');e.textContent=t('Gespeichert, Seite mit den neuen Funktionen geladen.','Saved, page loaded with the new functions.');e.style.display='block';setTimeout(()=>e.style.display='none',5000)}}catch{}   // back where the new version was loaded
  if(typeof goStart==='function')goStart(who);
  if(ADMIN){ulCheck();if(!elevated())wizCheck();loadLangs();refresh();setInterval(refresh,3000);zRooms();setInterval(zRooms,30e3);zDocs();setInterval(zDocs,30e3);zBg();setInterval(zBg,60e3);api('/api/update').then(r=>r.json()).then(u=>updBadge(u.remote)).catch(()=>{})}})();
