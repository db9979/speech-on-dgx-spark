// Admin login and start-up.
// ---------------------------------------------------------------- login
// Guests see only the assistant; everything else needs the panel password (cookie login).
let ADMIN=false,PUBLIC=true,GATE=false;
window.showLogin=()=>{if($('login').style.display==='none'){$('login').style.display='grid';$('loginmsg').textContent='';$('loginpw').value='';setTimeout(()=>$('loginpw').focus(),50)}};
$('loginbtn').onclick=showLogin;$('logincancel').onclick=()=>{$('login').style.display='none';if(GATE)openMe('loginbox')};
$('loginform').onsubmit=async e=>{e.preventDefault();
  try{await api('/api/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({password:$('loginpw').value})});location.reload()}
  catch(err){$('loginmsg').textContent=/too many/.test(err.message)?t('Zu viele falsche Versuche, bitte später noch einmal.','Too many wrong attempts, please try again later.'):t('Falsches Passwort.','Wrong password.')}};
$('logoutbtn').onclick=async()=>{await fetch('/api/logout',{method:'POST'});location.reload()};
$('pwset').onclick=async()=>{try{await api('/api/password',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({old:$('pwold').value,new:$('pwnew').value})});
  $('pwold').value=$('pwnew').value='';$('pwmsg').textContent=t('Passwort geändert.','Password changed.')}catch(e){$('pwmsg').innerHTML=`<span class="err">${esc(e.message)}</span>`}};
(async()=>{let who={admin:true};try{who=await (await fetch('/api/whoami')).json()}catch{}
  ADMIN=who.admin;DOCS_ON=who.documents!==false;REM_ON=who.reminders!==false;SPK_ON=!!who.speaker_id;CAL_ON=who.calendar!==false;HA_ON=!!who.homeassistant;const a=who.assistant||{};setProfile(who.profile);$('ver').textContent=t('Speech auf DGX Spark','Speech on DGX Spark')+' '+(who.version||'');
  if(!ADMIN){document.body.classList.add('guest');
    CFG={tts:{default_voice:a.default_voice},asr:{default_language:a.asr_language},panel:{https_port:a.https_port}};
    PUBLIC=who.public!==false;
    // without "Assistent ohne Passwort" guests are locked out, but profiles still sign in with name and PIN
    if(!PUBLIC&&!who.profile){GATE=true;$('profgate').style.display='';$('profadmin').style.display='';openMe('loginbox');return}}
  else $('logoutbtn').style.display='inline-block';
  document.querySelector('nav button[data-s=chat]').click();       // the assistant is the start page
  if(ADMIN){ulCheck();loadLangs();refresh();setInterval(refresh,3000);api('/api/update').then(r=>r.json()).then(u=>updBadge(u.remote)).catch(()=>{})}})();
