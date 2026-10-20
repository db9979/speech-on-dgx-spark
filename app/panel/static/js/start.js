// Admin login and start-up.
// ---------------------------------------------------------------- login
// Guests see only the assistant; everything else needs the panel password (cookie login).
// ADMIN, PUBLIC and GATE are declared in base.js (V01.0.422)
window.showLogin=()=>{if($('login').style.display==='none'){$('login').style.display='grid';$('loginmsg').textContent='';$('loginpw').value=$('logincode').value='';$('logincodebox').style.display='none';setTimeout(()=>$('loginpw').focus(),50)}};
ON.adminLogin=()=>{$('profmodal').style.display='none';showLogin()};
// a profile with an admin role is admin in its own login (coadmin.js); the panel password is the emergency access,
// only over the address with #admin
// the address with #admin typed into an open page changes only the hash, the page is not loaded again (V01.0.439)
window.addEventListener('hashchange',()=>{if(location.hash!=='#admin')return;history.replaceState(null,'',location.pathname+location.search);
  if(!ADMIN){$('profmodal').style.display='none';showLogin()}});
$('logincancel').onclick=()=>{$('login').style.display='none';if(GATE)openMe('loginbox')};
$('loginform').onsubmit=async e=>{e.preventDefault();
  try{const r=await (await api('/api/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({password:$('loginpw').value,code:$('logincode').value,trust:$('logintrust').checked})})).json();
    // right password, the second step is on: the code field comes next
    if(r.code){$('logincodebox').style.display='';$('loginmsg').textContent='';$('logincode').focus();
      if(window.pkLoginOffer)pkLoginOffer($('logincodebox'),r.passkey,async(pk,err)=>{if(!pk){$('loginmsg').textContent=t('Passkey abgebrochen. Der Code geht auch.','Passkey cancelled. The code works too.');return}
        try{await api('/api/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({password:$('loginpw').value,passkey:pk,trust:$('logintrust').checked})});location.reload()}
        catch(e){$('loginmsg').textContent=/too many/.test(errRaw(e))?t('Zu viele falsche Versuche, bitte später noch einmal.','Too many wrong attempts, please try again later.'):t('Passkey nicht angenommen.','Passkey not accepted.')}});return}
    location.reload()}
  catch(err){$('loginmsg').textContent=/too many/.test(err.message)?t('Zu viele falsche Versuche, bitte später noch einmal.','Too many wrong attempts, please try again later.'):/wrong code/.test(err.message)?t('Code falsch.','Wrong code.'):t('Falsches Passwort.','Wrong password.')}};
$('logoutbtn').onclick=async()=>{await /*raw: logout, the page reloads whatever the answer*/fetch('/api/logout',{method:'POST'});location.reload()};
$('pwset').onclick=async()=>{try{await api('/api/password',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({old:$('pwold').value,new:$('pwnew').value})});
  $('pwold').value=$('pwnew').value='';$('pwmsg').textContent=t('Passwort geändert.','Password changed.')}catch(e){$('pwmsg').innerHTML=`<span class="err">${esc(e.message)}</span>`}};
// Stelle merken, the way back (plaene/ruhige-seiten.md): the page, the settings page, the open function, person or Ich
// area, then the scroll once the boxes are drawn (lzIdle), unless the person already moved by himself
async function placeBack(){let p=null;try{p=JSON.parse(sessionStorage.getItem('place')||'null');sessionStorage.removeItem('place')}catch{}
  if(!p||typeof p!=='object')return;const sec=p.sec==='feat'?'cfg':p.sec,act=LZ.act;
  try{if(p.person&&typeof PL!=='undefined')PL.open=String(p.person);
    if(sec&&sec!=='chat'&&$(sec)&&$(sec).tagName==='SECTION'){if(sec==='cfg'&&p.pane&&$('pane-'+p.pane))goCfg(p.pane);else goSec(p.sec)}
    if(p.me!=null&&typeof openMe==='function')openMe(p.me||undefined)}catch{return}
  for(let i=0;i<50&&!(window.lzIdle&&lzIdle()&&i>2);i++)await new Promise(r=>setTimeout(r,100));
  if(LZ.act!==act)return;
  if(p.feat){const it=[...document.querySelectorAll('#pane-feat .fitem')].find(x=>x.dataset.sw===p.feat);if(it&&!it.classList.contains('open')&&typeof featOpen==='function')featOpen(it,true)}
  if(p.mey)$('profmodal').scrollTop=p.mey
  if(p.y)window.scrollTo(0,p.y)}
// the start of the page; theme.js (Start-Wächter) learns how it ended: a start that failed loads the page again later
async function startPage(){let who=null;try{who=await (await /*raw: the first who-am-I, before the login and the bar exist*/fetch('/api/whoami')).json()}catch{}
  // no answer from the Spark: a browser the profile trusts opens its offline copy to read (verlauf.js); else the Spark
  // is restarting (an update): the Start-Wächter waits for it and loads the page again (before: an empty admin page for good)
  if(!who||typeof who!=='object')who=offlineWho();
  if(!who)throw new Error('no whoami');
  if(who.version!==undefined)WHO_FLAGS=whoFlags(who);ADMIN=who.admin;DOCS_ON=who.documents!==false;REM_ON=who.reminders!==false;SPK_ON=!!who.speaker_id;CAL_ON=who.calendar!==false;TEIL_ON=!!who.share;HA_ON=!!who.homeassistant;MAIL_ON=!!who.mail;TIDY_ON=!!who.mail_tidy;MSTIL_ON=!!who.mail_style;if(typeof FUER_ON!=='undefined')FUER_ON=!!who.mail_insight;if(typeof WISS_ON!=='undefined')WISS_ON=!!who.ichweiss;if(typeof ORD_ON!=='undefined')ORD_ON=!!who.mail_manage;DEL_ON=!!who.mail_delete;if(typeof SEND_ON!=='undefined')SEND_ON=!!who.mail_send;PRO_ON=!!who.proactive;S1MAIL_ON=!!who.systemone_mail;HALIVE_ON=!!who.ha_live;HALOUD_ON=!!who.ha_loud;HAEV_ON=!!who.ha_events;HAVOICE_ON=!!who.ha_voice_rules;HACAM_ON=!!who.ha_camera;MCPS_ON=!!who.mcp_server;if(typeof MYMCP_ON!=='undefined')MYMCP_ON=!!who.my_mcp;if(typeof STORE_ON!=='undefined')STORE_ON=!!who.storage;if(typeof NAS_ON!=='undefined')NAS_ON=!!who.nas;ROOM_ON=!!who.room;RV_ON=!!who.room_voices;RHA_ON=!!who.room_ha;RFAR_ON=!!who.room_remote;WX_ON=!!who.weather;CON_ON=!!who.contacts;PAR_ON=!!who.parcels;TASK_ON=!!who.tasks;AGENT_ON=!!who.agent;TR_ON=!!who.transit;FD_ON=!!who.feeds;TG_ON=!!who.telegram;ESP_ON=!!who.esp32;APP_ON=!!who.iphone;APP_PANEL=!!who.iphone_panel;PEB_ON=!!who.pebble;if(typeof TERM_ON!=='undefined')TERM_ON=!!who.terminal;AND_ON=!!who.android;if(typeof DESK_ON!=='undefined')DESK_ON=!!who.desk;RM_ON=!!who.remarkable;RMSEND_ON=!!who.remarkable_send;RMFRESH_ON=!!who.remarkable_fresh;RMPLUS_ON=!!who.remarkable_plus;RMPAPER_ON=!!who.remarkable_paper;RMTASKS_ON=!!who.remarkable_tasks;MYST_ON=!!who.my_status;if(typeof VB_ON!=='undefined')VB_ON=!!who.usage_count;if(typeof TEL_ON!=='undefined')TEL_ON=!!who.telefon;if(typeof BILD_ON!=='undefined')BILD_ON=!!who.bilder;if(typeof MUSIK_ON!=='undefined')MUSIK_ON=!!who.musik;if(typeof BILDAE_ON!=='undefined')BILDAE_ON=!!who.bilder_aendern;if(typeof WRITE_ON!=='undefined')WRITE_ON=!!who.write_help;VOR_ON=!!who.person_priority;TRACE_ON=!!who.trace;ME_OWN=Array.isArray(who.locked)?who.locked:[];if(typeof TIPS_ON!=='undefined')TIPS_ON=!!who.tipps;if(typeof SATZ_ON!=='undefined'){SATZ_ON=!!who.saetze;if(typeof moreStart==='function')moreStart()}if(typeof hilfeStart==='function')hilfeStart(who.hilfe);coadmStart(who);room.show();setFaceSpark(who.face_spark||who.face);setFaceKind(who.face);setFaceLife(who.face_life===true);const a=who.assistant||{};setProfile(who.profile);$('ver').textContent=t('Speech auf DGX Spark','Speech on DGX Spark')+' '+(who.version||'');
  if(window.trustUi)trustUi(who);
  if(window.cxStart)cxStart(who);   // Chats (chats.js): the menu entry only when this profile may use them
  // Kalender (kalender.js) and E-Mail (post.js): the menu entry only for a profile that may use it
  if(window.kalStart)kalStart(who);
  if(window.postStart)postStart(who);
  if(window.lstStart)lstStart(who);   // Listen (listen.js): the menu entry only for a profile that may use lists
  // a program's OAuth sign-in (mcpserver.py): kept until the profile is signed in, then Ich → Spark als MCP-Server asks
  try{const m=/^#mcpauth=([A-Za-z0-9_-]{20,48})$/.exec(location.hash);if(m){sessionStorage.setItem('mcpauth',m[1]);history.replaceState(null,'',location.pathname+location.search)}}catch{}
  // an own MCP service's sign-in came back (meinmcp.py /api/mymcp/back): Ich → Meine MCP-Dienste finishes it
  try{const m=/^#mymcpback=([A-Za-z0-9_-]{20,64}\.[A-Za-z0-9._~%-]{1,3100}|error)$/.exec(location.hash);if(m){sessionStorage.setItem('mymcpback',m[1]);history.replaceState(null,'',location.pathname+location.search)}}catch{}
  SETUP=who.setup||null;if(typeof joinHash==='function'&&joinHash())return;   // an invitation or "Am Handy weitermachen" (join.js)
  if(!ADMIN){document.body.classList.add('guest');
    CFG={tts:{default_voice:a.default_voice},asr:{default_language:a.asr_language},panel:{https_port:a.https_port}};
    PUBLIC=who.public!==false;
    const toAdmin=location.hash==='#admin';if(toAdmin){history.replaceState(null,'',location.pathname+location.search);showLogin()}   // the main admin's way in
    // without "Assistent ohne Passwort" guests are locked out, but profiles still sign in with name and PIN
    if(!PUBLIC&&!who.profile){GATE=true;$('profgate').style.display='';if(!toAdmin)openMe('loginbox');return}   // the password only with #admin
    // one shell for everybody (plan „Vereinheitlichen“ Phase 7): a signed-in profile gets the same menu as the admin,
    // with only what it may (Assistent, Ich); guests keep the plain page with the assistant
    if(who.profile){document.body.classList.remove('guest');document.body.classList.add('adm','prof')}}
  else{$('logoutbtn').style.display='inline-block';document.body.classList.add('adm');hdrH();if(typeof grundLoad==='function')grundLoad()}
  document.querySelector('nav button[data-s=chat]').click();       // the assistant is the start page
  placeBack();   // a reload the page did itself: back to the same place (base.js placeNow)
  // "Im Panel öffnen" in the iPhone app: #go=<page>, #cfg=<settings page> or #me=<Ich area>, only known names
  try{const h=/^#(go|cfg|me)=([a-z]{2,12})$/.exec(location.hash);if(h){history.replaceState(null,'',location.pathname+location.search);
    if(h[1]==='go'&&ADMIN&&h[2]!=='chat'&&$(h[2])&&$(h[2]).tagName==='SECTION')goSec(h[2]);
    else if(h[1]==='cfg'&&ADMIN&&$('pane-'+h[2]))goCfg(h[2]);
    else if(h[1]==='me'&&PROFILE&&typeof OWN_PAGES!=='undefined'&&OWN_PAGES[h[2]]){icTabSet(OWN_PAGES[h[2]][0],'show');goSec(OWN_PAGES[h[2]][0])}   // a page of its own (Kalender): its first tab
    else if(h[1]==='me'&&PROFILE&&/box$/.test(h[2])&&$(h[2]))openMe(h[2])}}catch{}
  // #kal=YYYY-MM-DD from the Begleiter („Als Nächstes“, Begleiter nachziehen 7a): the page Kalender on that day
  try{const k=/^#kal=(\d{4})-(\d{2})-(\d{2})$/.exec(location.hash);if(k){history.replaceState(null,'',location.pathname+location.search);
    if(PROFILE&&typeof KAL!=='undefined'&&$('cal')){KAL.day=new Date(+k[1],k[2]-1,+k[3]);icTabSet('cal','show');goSec('cal')}}}catch{}
  // #weg=<a way like „Ich → Sicherheit“> from the apps, mails and messages: opens it like a Sprung-Link (way.js)
  try{if(typeof wayHash==='function')wayHash()}catch{}
  try{const fr=sessionStorage.getItem('flagsreload');if(fr){sessionStorage.removeItem('flagsreload');if(fr==='away')sayToast(t('Deine Funktionen wurden geändert, Seite neu geladen.','Your functions were changed, page reloaded.'),5000)}}catch{}   // back where the new version was loaded
  if(typeof goStart==='function')goStart(who);
  if(typeof mcpAuthStart==='function')mcpAuthStart();
  if(typeof mymBackStart==='function')mymBackStart();
  if(typeof rpStart==='function')rpStart(who);   // Probleme melden (melden.js): footer, Logs, #melden
  if(ADMIN){ulCheck();if(!elevated())wizCheck();loadLangs();refresh();setInterval(refresh,3000);
    zPoll([['zRooms',30e3],['zDocs',30e3],['zBg',60e3],['zDev',60e3],['zWatch',60e3],['zWartung',30e3],['zStore',60e3],['zNas',60e3],['zNasquelle',60e3],['zNasZustand',60e3],['zUsage',60e3]]);api('/api/update').then(r=>r.json()).then(u=>updBadge(u.remote)).catch(()=>{})}}
startPage().then(()=>{if(window.sparkBootDone)sparkBootDone()},e=>{if(window.sparkBootFail)sparkBootFail(e)});
