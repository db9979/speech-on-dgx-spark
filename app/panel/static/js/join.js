// New people and "Los geht's" (join.py, onboard.py; plan plaene/registrierung-onboarding.md, V01.0.269).
// - #join=<code>: the welcome page of an invitation (name and PIN, or a new PIN for an existing profile)
// - #hand=<code>: a phone continues where the computer is ("Am Handy weitermachen")
// - Personen und Geräte → "Neue Personen": the switch, invitations, packs (admin)
// - Ich → "Los geht's": the profile's own setup list, step by step; opens the Ich page of each item
let SETUP=null;
const GO={step:null,data:null,from:false,hand:null,timer:null};
// the public routes answer with their own codes; api() would open the admin login on a 401
async function jpub(p,b){const r=await fetch(p,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(b||{})});
  let d={};try{d=await r.json()}catch{}
  if(!r.ok){const e=new Error(typeof d.detail==='string'?d.detail:'');e.status=r.status;throw e}return d}
const jerr=e=>e.status===404?t('Einladungen sind auf diesem Spark gerade aus.','Invitations are switched off on this Spark right now.')
  :e.status===429?t('Zu viele Versuche. Bitte später noch einmal.','Too many attempts. Please try again later.')
  :e.message||t('Das hat nicht geklappt.','That did not work.');
function joinModal(){let m=$('joinmodal');if(!m){m=document.createElement('div');m.id='joinmodal';m.className='modal';
  m.innerHTML='<div class="card modalcard joincard" id="joincard"></div>';document.body.appendChild(m)}m.style.display='grid';return $('joincard')}
const jhead=()=>`<div class="row joinbrand"><span class="logo"></span><b>Spark</b></div>`;
// ---------------------------------------------------------------- the invitation
function joinHash(){const m=/^#(join|hand)=([A-Za-z0-9_-]{20,40})$/.exec(location.hash);if(!m)return false;
  history.replaceState(null,'',location.pathname+location.search);
  if(m[1]==='join')joinWelcome(m[2]);else handPhone(m[2]);return true}
async function joinWelcome(code){const box=joinModal();box.innerHTML=jhead()+`<div class="mut">${t('Einladung wird geprüft …','Checking the invitation …')}</div>`;
  let d;try{d=await jpub('/api/join/check',{code})}catch(e){box.innerHTML=jhead()+`<h2>${t('Einladung','Invitation')}</h2><div class="err">${esc(jerr(e))}</div><div class="row joinfoot"><button class="b" type="button" id="joinhome">${t('Zur Startseite','To the start page')}</button></div>`;$('joinhome').onclick=()=>location.reload();return}
  const pin=d.kind==='pin',until=d.until?new Date(d.until*1000).toLocaleDateString():'';
  const iphone=d.app&&/iPhone|iPad/.test(navigator.userAgent)&&location.protocol==='https:';
  box.innerHTML=jhead()+`<h2>${pin?t('Neue PIN für ','New PIN for ')+esc(d.name):d.name?t('Willkommen, ','Welcome, ')+esc(d.name)+'!':t('Willkommen!','Welcome!')}</h2>
    <div class="intro">${pin?t('Wähle eine neue PIN. Danach bist du in diesem Browser angemeldet; andere Browser melden sich neu an.','Pick a new PIN. Then you are signed in in this browser; other browsers sign in again.')
      :t('Du bist zum Sprachassistenten auf dem Spark eingeladen. Wähle Name und PIN, dann richten wir zusammen deine Geräte ein.','You are invited to the voice assistant on the Spark. Pick a name and a PIN, then we set up your devices together.')}</div>
    ${pin?'':`<label for="joinname">${t('Dein Name','Your name')}</label><input id="joinname" maxlength="40" autocomplete="username" value="${esc(d.name||'')}">`}
    <label for="joinpin">${t('PIN (mindestens ','PIN (at least ')+d.pin_min+t(' Zeichen)',' characters)')}</label><input id="joinpin" type="password" autocomplete="new-password">
    <label for="joinpin2">${t('PIN wiederholen','Repeat the PIN')}</label><input id="joinpin2" type="password" autocomplete="new-password">
    <div id="joincodebox" hidden><label for="joincode">${t('Code aus der Authenticator-App','Code from the authenticator app')}</label><input id="joincode" inputmode="numeric" autocomplete="one-time-code"></div>
    ${!pin&&d.mfa?`<div class="fh">${t('Für E-Mail, Dokumente und Aufträge richtest du danach den zweiten Anmeldeschritt ein.','For e-mail, documents and jobs you set up the second sign-in step afterwards.')}</div>`:''}
    <div class="row joinfoot"><span class="mut sm">${until?t('gültig bis ','valid until ')+esc(until)+' · ':''}${t('nur einmal','once only')}</span><button class="b p" type="button" id="joingo">${pin?t('PIN setzen','Set the PIN'):t('Profil anlegen','Create the profile')}</button></div>
    ${iphone?`<div class="row"><a class="b" id="joinapp" href="#">${t('Lieber gleich in der iPhone-App','Rather straight in the iPhone app')}</a></div>`:''}
    <div id="joinmsg" class="err"></div>`;
  if($('joinapp'))$('joinapp').href='spark-app://join?'+new URLSearchParams({url:location.origin,code});
  const go=async()=>{const p=$('joinpin').value;$('joinmsg').textContent='';
    if(p.length<d.pin_min){$('joinmsg').textContent=t('Die PIN braucht mindestens ','The PIN needs at least ')+d.pin_min+t(' Zeichen.',' characters.');return}
    if(p!==$('joinpin2').value){$('joinmsg').textContent=t('Die beiden PINs sind nicht gleich.','The two PINs differ.');return}
    $('joingo').disabled=true;
    try{const r=await jpub('/api/join',{code,pin:p,name:pin?undefined:$('joinname').value.trim(),mfa_code:$('joincode').value.trim()||undefined});
      if(r.code){$('joincodebox').hidden=false;$('joincode').focus();$('joingo').disabled=false;return}
      try{sessionStorage.setItem('golets',r.kind==='new'?'1':'')}catch{}location.reload()}
    catch(e){$('joinmsg').textContent=e.status===401?t('Code falsch.','Wrong code.'):jerr(e);$('joingo').disabled=false}};
  $('joingo').onclick=go;box.querySelectorAll('input').forEach(i=>i.onkeydown=e=>{if(e.key==='Enter')go()});
  setTimeout(()=>($('joinname')||$('joinpin')).focus(),50)}
// ---------------------------------------------------------------- the phone side of "Am Handy weitermachen"
async function handPhone(code){const box=joinModal();box.innerHTML=jhead()+`<div class="mut">${t('Verbinde …','Connecting …')}</div>`;
  let d;try{d=await jpub('/api/handoff/claim',{code})}catch(e){box.innerHTML=jhead()+`<h2>${t('Am Handy weitermachen','Continue on the phone')}</h2><div class="err">${esc(e.status===404?t('Das ist auf diesem Spark aus.','This is switched off on this Spark.'):jerr(e))}</div><div class="row joinfoot"><button class="b" type="button" id="joinhome">${t('Zur Startseite','To the start page')}</button></div>`;$('joinhome').onclick=()=>location.reload();return}
  box.innerHTML=jhead()+`<h2>${t('Am Handy weitermachen','Continue on the phone')}</h2><div class="intro">${t('Tippe am Rechner auf diese Zahl:','Tap this number on the computer:')}</div><div class="gonum">${esc(d.num)}</div><div class="mut" id="handmsg">${t('Wartet auf den Rechner …','Waiting for the computer …')}</div>`;
  const end=Date.now()+125e3;
  const poll=async()=>{if(Date.now()>end){$('handmsg').textContent=t('Abgelaufen. Am Rechner einen neuen Code holen.','Expired. Get a new code on the computer.');return}
    try{const r=await jpub('/api/handoff/finish',{code,wait:d.wait});if(r.ok){try{sessionStorage.setItem('golets','1')}catch{}location.reload();return}}
    catch(e){$('handmsg').textContent=e.status===410?t('Nicht bestätigt. Am Rechner einen neuen Code holen.','Not confirmed. Get a new code on the computer.'):jerr(e);return}
    setTimeout(poll,1500)};
  setTimeout(poll,1500)}
// ---------------------------------------------------------------- admin: Personen und Geräte → Neue Personen
const JA={d:null,made:null,edit:false,t:0};
const jwhen=s=>s?new Date(s*1000).toLocaleDateString():'';
async function joinAdmin(force){const box=$('joinadmin');if(!box)return;if(!force&&Date.now()-JA.t<3000)return;JA.t=Date.now();
  try{JA.d=await (await api('/api/admin/join')).json()}catch(e){box.innerHTML=`<h2>${t('Neue Personen','New people')}</h2><div class="err">${esc(e.message)}</div>`;return}
  const d=JA.d,on=d.mode==='invite',https=location.protocol==='https:';
  const packName=id=>(d.packs.find(p=>p.id===id)||{}).name||'';
  const st={open:['ok',t('offen','open')],used:['',t('benutzt','used')],gone:['',t('abgelaufen','expired')]};
  box.innerHTML=`<div class="row"><h2 class="sp">${t('Neue Personen','New people')}</h2><div class="lseg" role="group" aria-label="${esc(t('Neue Personen','New people'))}">
      <button type="button" data-jmode="off" class="${on?'':'on'}">${t('Aus','Off')}</button><button type="button" data-jmode="invite" class="${on?'on':''}">${t('Nur mit Einladung','Invitation only')}</button></div></div>
    <div class="intro">${t('Mit einer Einladung legt sich jemand selbst ein Profil an (Name und eigene PIN) und wird danach durch das Einrichten geführt. Jede Einladung gilt einmal und nur bis zu ihrem Tag.','With an invitation someone creates their own profile (name and own PIN) and is then guided through the setup. Each invitation works once and only until its day.')}</div>
    ${on?`<div class="jline"><span class="sp">${t('Zweiter Anmeldeschritt für neue Profile','Second sign-in step for new profiles')}${d.mfa_on?'':`<div class="fh">${t('Braucht Funktionen → Zweiter Anmeldeschritt.','Needs Features → Second sign-in step.')}</div>`}</span>
        <select id="jmfa"><option value="data"${d.mfa==='data'?' selected':''}>${t('Pflicht für E-Mail, Dokumente, Aufträge','Required for e-mail, documents, jobs')}</option><option value="off"${d.mfa==='off'?' selected':''}>${t('freiwillig','optional')}</option></select></div>
      <div class="jline"><label class="chk sp"><input type="checkbox" id="jhand"${d.handoff?' checked':''}> ${t('„Am Handy weitermachen“ anbieten','Offer "Continue on the phone"')}</label></div>
      <div class="fh">${t('Ein QR-Code am Rechner meldet das Handy im selben Profil an, erst nach Antippen der passenden Zahl am Rechner.','A QR code on the computer signs the phone in to the same profile, only after tapping the matching number on the computer.')}</div>
      ${d.iphone_on?`<label for="jappl">${t('Link zum Laden der iPhone-App (App Store oder TestFlight)','Link to get the iPhone app (App Store or TestFlight)')}</label><div class="rowin"><input id="jappl" maxlength="300" placeholder="https://testflight.apple.com/join/…" value="${esc(d.app_link)}"><button class="b" type="button" id="japplsave">${t('Speichern','Save')}</button></div>`:''}
      <div class="jline"><span class="sp"><b>${t('Startpakete','Starter packs')}</b> ${d.packs.map(p=>`<span class="chip">${esc(p.name)}</span>`).join(' ')}</span><button class="b" type="button" id="jpackedit">${JA.edit?t('Schließen','Close'):t('Bearbeiten','Edit')}</button></div>
      <div id="jpacks"></div>
      <div class="jline"><span class="sp"><b>${t('Einladungen','Invitations')}</b></span><button class="b p" type="button" id="jnew"${https?'':' disabled'}>+ ${t('Einladen','Invite')}</button></div>
      ${https?'':`<div class="fh">${t('Einladungen brauchen die https-Adresse des Panels. Diese Seite über https öffnen.','Invitations need the panel\'s https address. Open this page over https.')}</div>`}
      <div id="jform"></div>`:''}
    <ul class="facts jlist">${d.invites.map(i=>`<li><span><b>${esc(i.kind==='pin'?t('Neue PIN: ','New PIN: ')+(i.profile||'?'):i.name||t('ohne Namen','without a name'))}</b>${i.pack?` <span class="chip hi">${esc(packName(i.pack)||i.pack)}</span>`:''}
      <br><small class="mut">${esc(st[i.state][1])} · ${i.state==='used'?t('am ','on ')+esc(jwhen(i.used)):t('bis ','until ')+esc(jwhen(i.until))} · ${t('von ','by ')}${esc(i.by)}</small></span>
      ${i.state==='open'?`<button class="b" type="button" data-jrev="${esc(i.id)}">${t('Zurückziehen','Revoke')}</button>`:''}</li>`).join('')||(on?`<li class="mut"><span>${t('Noch keine Einladungen.','No invitations yet.')}</span></li>`:'')}</ul>
    <div class="fh" id="jmsg"></div>`;
  const msg=(x,err)=>{$('jmsg').className=err?'fh err':'fh';$('jmsg').textContent=x};
  const put=async b=>{try{await api('/api/admin/join',xjson('PUT',b));joinAdmin(true)}catch(e){msg(e.message,true)}};
  box.querySelectorAll('[data-jmode]').forEach(b=>b.onclick=()=>{if(b.dataset.jmode!==d.mode)put({mode:b.dataset.jmode})});
  if($('jmfa'))$('jmfa').onchange=()=>put({mfa:$('jmfa').value});
  if($('jhand'))$('jhand').onchange=()=>put({handoff:$('jhand').checked});
  if($('japplsave'))$('japplsave').onclick=()=>put({app_link:$('jappl').value.trim()});
  if($('jpackedit'))$('jpackedit').onclick=()=>{JA.edit=!JA.edit;joinAdmin(true)};
  if(JA.edit&&$('jpacks'))joinPacks();
  if($('jnew'))$('jnew').onclick=()=>joinForm();
  box.querySelectorAll('[data-jrev]').forEach(b=>b.onclick=async()=>{if(!confirm(t('Einladung zurückziehen? Der Link geht dann nicht mehr.','Revoke the invitation? The link stops working.')))return;
    try{await api('/api/admin/join/invites/'+encodeURIComponent(b.dataset.jrev),{method:'DELETE'});joinAdmin(true)}catch(e){msg(e.message,true)}});
  if(JA.made)joinShow(JA.made)}
function joinForm(){const d=JA.d;$('jform').innerHTML=`<div class="jform"><div class="two2"><div><label for="jname">${t('Name (die Person darf ihn ändern)','Name (the person may change it)')}</label><input id="jname" maxlength="40"></div>
    <div><label for="jpack">${t('Startpaket','Starter pack')}</label><select id="jpack"><option value="">${t('keins','none')}</option>${d.packs.map(p=>`<option value="${esc(p.id)}">${esc(p.name)}</option>`).join('')}</select></div></div>
    <label for="jdays">${t('Gültig','Valid')}</label><select id="jdays">${d.days.map(n=>`<option value="${n}"${n===7?' selected':''}>${n===1?t('1 Tag','1 day'):n+t(' Tage',' days')}</option>`).join('')}</select>
    <div class="row joinfoot"><button class="b p" type="button" id="jmake">${t('Einladung erstellen','Create the invitation')}</button><button class="b" type="button" id="jcancel">${t('Abbrechen','Cancel')}</button></div></div>`;
  $('jcancel').onclick=()=>{$('jform').innerHTML=''};
  $('jmake').onclick=async()=>{try{const r=await (await api('/api/admin/join/invites',xjson('POST',{name:$('jname').value.trim(),pack:$('jpack').value,days:+$('jdays').value,base:location.origin}))).json();
    JA.made=Object.assign(r,{who:$('jname').value.trim()});joinAdmin(true)}catch(e){$('jmsg').className='fh err';$('jmsg').textContent=e.message}}}
// the link and its QR code are shown only right after making it (only the code's hash is kept)
function joinShow(r,target){const box=target||$('jform');if(!box)return;
  box.innerHTML=`<div class="jmade"><div class="jqr">${r.qr||''}</div><div class="sp"><b>${esc(r.who?t('Einladung für ','Invitation for ')+r.who:t('Einladung','Invitation'))}</b>
    <div class="fh">${t('Mit der Handy-Kamera scannen oder den Link schicken. Er wird nur jetzt angezeigt, gilt einmal und ','Scan with the phone camera or send the link. It is shown only now, works once and for ')}${r.days===1?t('einen Tag.','one day.'):r.days+t(' Tage.',' days.')}</div>
    <input readonly class="token" value="${esc(r.link)}" aria-label="Link">
    <div class="row"><button class="b" type="button" data-jcopy>${t('Kopieren','Copy')}</button>${navigator.share?`<button class="b" type="button" data-jshare>${t('Teilen …','Share …')}</button>`:''}<button class="b" type="button" data-jprint>${t('Als Karte drucken','Print as a card')}</button><button class="b" type="button" data-jdone>${t('Fertig','Done')}</button></div></div></div>`;
  box.querySelector('[data-jcopy]').onclick=async()=>{try{await navigator.clipboard.writeText(r.link)}catch{box.querySelector('input').select()}};
  if(box.querySelector('[data-jshare]'))box.querySelector('[data-jshare]').onclick=()=>navigator.share({title:'Spark',text:t('Deine Einladung zum Sprachassistenten:','Your invitation to the voice assistant:'),url:r.link}).catch(()=>{});
  box.querySelector('[data-jprint]').onclick=()=>joinPrint(r);
  box.querySelector('[data-jdone]').onclick=()=>{JA.made=null;box.innerHTML='';if(!target)joinAdmin(true)}}
function joinPrint(r){let p=$('joinprint');if(!p){p=document.createElement('div');p.id='joinprint';document.body.appendChild(p)}
  p.innerHTML=`<div class="jcard"><h1>Spark</h1><p>${esc(r.who?t('Hallo ','Hello ')+r.who+'!':t('Hallo!','Hello!'))}</p><div class="jqr">${r.qr||''}</div>
    <ol><li>${t('Mit der Handy-Kamera den Code scannen.','Scan the code with the phone camera.')}</li><li>${t('Name und eigene PIN wählen.','Pick a name and your own PIN.')}</li><li>${t('Den Schritten unter „Los geht\'s“ folgen.','Follow the steps under "Let\'s go".')}</li></ol>
    <p class="mut">${t('Gilt einmal.','Works once.')}</p></div>`;
  document.body.classList.add('printjoin');window.print();setTimeout(()=>document.body.classList.remove('printjoin'),500)}
function joinPacks(){const d=JA.d;let packs=JSON.parse(JSON.stringify(d.packs));
  const draw=()=>{$('jpacks').innerHTML=packs.map((p,i)=>`<div class="jpack"><div class="rowin"><input data-jpn="${i}" maxlength="30" value="${esc(p.name)}" aria-label="${esc(t('Name des Pakets','Name of the pack'))}"><button class="b" type="button" data-jpdel="${i}">${t('Entfernen','Remove')}</button></div>
      <div class="jkeys">${d.packable.map(f=>`<label class="chk"><input type="checkbox" data-jpk="${i}" value="${esc(f.key)}"${p.keys.includes(f.key)?' checked':''}> ${esc(t(f.name[0],f.name[1]))}${f.on?'':` <small class="mut">(${t('Spark aus','Spark off')})</small>`}</label>`).join('')}</div></div>`).join('')
      +`<div class="row">${packs.length<10?`<button class="b" type="button" id="jpadd">+ ${t('Paket','Pack')}</button>`:''}<button class="b p" type="button" id="jpsave">${t('Pakete speichern','Save the packs')}</button></div>
      <div class="fh">${t('Ein Paket schaltet beim neuen Profil die eigenen Schalter dieser Funktionen ein, nur wenn sie für den Spark an sind. Rollen gibt es nie über ein Paket.','A pack switches on the new profile\'s own switches of these functions, only while they are on for the Spark. Roles never come with a pack.')}</div>`;
    $('jpacks').querySelectorAll('[data-jpn]').forEach(x=>x.oninput=()=>{packs[+x.dataset.jpn].name=x.value});
    $('jpacks').querySelectorAll('[data-jpk]').forEach(x=>x.onchange=()=>{const p=packs[+x.dataset.jpk];p.keys=x.checked?[...new Set(p.keys.concat(x.value))]:p.keys.filter(k=>k!==x.value)});
    $('jpacks').querySelectorAll('[data-jpdel]').forEach(x=>x.onclick=()=>{packs.splice(+x.dataset.jpdel,1);draw()});
    if($('jpadd'))$('jpadd').onclick=()=>{let n=1;while(packs.some(p=>p.id==='p'+n))n++;packs.push({id:'p'+n,name:t('Neues Paket','New pack'),keys:[]});draw()};
    $('jpsave').onclick=async()=>{try{await api('/api/admin/join/packs',xjson('PUT',{packs}));JA.edit=false;joinAdmin(true)}catch(e){$('jmsg').className='fh err';$('jmsg').textContent=e.message}}};
  draw()}
// in a profile's details: a one-time link to pick a new PIN, and the setup state with "Erinnern"
async function joinPinLink(id,name,box){try{const r=await (await api('/api/admin/join/invites',xjson('POST',{uid:id,days:1,base:location.origin}))).json();
    joinShow(Object.assign(r,{who:name}),box)}catch(e){box.innerHTML=`<span class="err">${esc(e.message)}</span>`}}
function joinSetupLine(s){if(!s||!s.total)return'';return `<span class="pill ${s.done>=s.total?'ok':'warn'}">${t('Einrichten ','Setup ')}${s.done} ${t('von','of')} ${s.total}</span>`}
// ---------------------------------------------------------------- Ich → Los geht's
async function goShow(){const box=$('gobox');if(!box||!PROFILE)return;
  let d;try{d=await (await api('/api/profile/setup')).json()}catch(e){box.innerHTML=`<div class="err">${esc(e.message)}</div>`;return}
  GO.data=d;const its=d.items,steps=d.steps.filter(s=>s.key==='done'||its.some(x=>x.step===s.key));
  if(!GO.step||!steps.some(s=>s.key===GO.step))GO.step=(steps.find(s=>its.some(x=>x.step===s.key&&!x.done&&!x.later))||steps[steps.length-1]).key;
  const idx=steps.findIndex(s=>s.key===GO.step),cur=steps[idx];
  const live=its.filter(x=>!x.later),done=live.filter(x=>x.done).length;
  const stepDone=s=>s.key==='done'?done===live.length:its.filter(x=>x.step===s.key&&!x.later).every(x=>x.done);
  const card=x=>{const why=x.why==='mfa'?t('Erst den zweiten Anmeldeschritt (Schritt „Absichern“).','First the second sign-in step (step "Secure").'):'';
    return `<div class="gocard${x.done?' done':''}"><div class="row"><b class="sp">${esc(t(x.name[0],x.name[1]))}${x.required?` <span class="pill warn">${t('Pflicht','required')}</span>`:''}</b>
      ${x.done?`<span class="pill ok">✓ ${t('erledigt','done')}</span>`:x.later?`<button class="b" type="button" data-golater="${esc(x.key)}" data-v="0">${t('Doch anzeigen','Show again')}</button>`
        :why?'':`<button class="b p" type="button" data-gogo="${esc(x.key)}">${x.mine?t('Einrichten','Set up'):t('Einschalten und einrichten','Switch on and set up')}</button>${x.required?'':`<button class="b" type="button" data-golater="${esc(x.key)}" data-v="1">${t('Später','Later')}</button>`}`}</div>
      ${why?`<div class="fh">${esc(why)}</div>`:''}
      ${x.key==='iphone'&&!x.done&&d.app_link?`<div class="goapp"><div class="jqr">${d.app_qr||''}</div><div class="fh">${t('1. App laden: mit der iPhone-Kamera scannen oder ','1. Get the app: scan with the iPhone camera or ')}<a href="${esc(d.app_link)}" target="_blank" rel="noopener">${t('hier antippen','tap here')}</a>. ${t('2. „Einrichten“ zeigt den Code zum Koppeln.','2. "Set up" shows the pairing code.')}</div></div>`:''}</div>`};
  let body='';
  if(cur.key==='done'){body=`<div class="intro">${done===live.length?t('Alles eingerichtet. Probier mal:','All set up. Try:'):t('Fast fertig. Was noch offen ist, findest du jederzeit hier unter Ich → Los geht\'s. Probier mal:','Nearly done. What is still open stays here under Me → Let\'s go. Try:')}</div><div class="gosay" id="gosay"></div>`}
  else body=(cur.key==='hello'?`<div class="intro">${t('Hier stellst du ein, mit welcher Stimme und wie ausführlich der Assistent mit dir spricht.','Here you set the voice and how detailed the assistant talks to you.')}</div>`
      :cur.key==='secure'?`<div class="intro">${t('Ein zweiter Schritt mit einer Authenticator-App schützt dein Profil, auch wenn jemand deine PIN kennt.','A second step with an authenticator app protects your profile, even if someone knows your PIN.')}</div>`
      :cur.key==='devices'?`<div class="intro">${t('Jedes Gerät hat genau einen Weg. Am Handy reicht meist Antippen statt Scannen.','Each device has exactly one way. On a phone, tapping usually replaces scanning.')}</div>`
      :`<div class="intro">${t('Verbinde, was der Assistent für dich lesen soll. Passwörter bleiben verschlüsselt auf dem Spark.','Connect what the assistant should read for you. Passwords stay encrypted on the Spark.')}</div>`)
    +its.filter(x=>x.step===cur.key).map(card).join('')
    +(cur.key==='devices'&&d.handoff&&!PHONE.matches?`<div class="gocard gohand"><div class="row"><b class="sp">${t('Am Handy weitermachen','Continue on the phone')}</b><button class="b" type="button" id="gohandgo">${t('QR-Code zeigen','Show the QR code')}</button></div><div class="fh">${t('Scannen meldet dein Handy in diesem Profil an, nachdem du hier die passende Zahl angetippt hast.','Scanning signs your phone in to this profile after you tap the matching number here.')}</div><div id="gohand"></div></div>`:'');
  box.innerHTML=`<div class="intro">${t('Schritt für Schritt alles, was du nutzen darfst. Erledigtes hakt der Spark selbst ab.','Step by step everything you may use. The Spark ticks off what is done itself.')}</div>
    <div class="gosteps">${steps.map((s,i)=>`<button type="button" data-gostep="${esc(s.key)}" class="${s.key===cur.key?'on':''}${stepDone(s)?' ok':''}"><i></i>${i+1}. ${esc(t(s.name[0],s.name[1]))}</button>`).join('')}</div>
    <div class="mut sm">${done} ${t('von','of')} ${live.length} ${t('erledigt','done')}</div>${body}
    <div class="row joinfoot">${idx>0?`<button class="b" type="button" id="goback">${t('Zurück','Back')}</button>`:''}<span class="sp"></span>${idx<steps.length-1?`<button class="b p" type="button" id="gonext">${t('Weiter','Next')}</button>`:`<button class="b p" type="button" id="goend">${t('Fertig','Done')}</button>`}</div>
    <div class="fh" id="gomsg"></div>`;
  box.querySelectorAll('[data-gostep]').forEach(b=>b.onclick=()=>{GO.step=b.dataset.gostep;goShow()});
  if($('goback'))$('goback').onclick=()=>{GO.step=steps[idx-1].key;goShow()};
  if($('gonext'))$('gonext').onclick=async()=>{if(cur.key==='hello')await goPut({welcome:true});GO.step=steps[idx+1].key;goShow()};
  if($('goend'))$('goend').onclick=()=>{$('profmodal').style.display='none'};
  box.querySelectorAll('[data-gogo]').forEach(b=>b.onclick=()=>goItem(its.find(x=>x.key===b.dataset.gogo)));
  box.querySelectorAll('[data-golater]').forEach(b=>b.onclick=async()=>{const later=new Set(d.state.later);if(b.dataset.v==='1')later.add(b.dataset.golater);else later.delete(b.dataset.golater);
    await goPut({later:[...later]});goShow()});
  if($('gohandgo'))$('gohandgo').onclick=handPc;
  if(cur.key==='done')goSay()}
async function goPut(b){try{const r=await (await api('/api/profile/setup',xjson('PUT',b))).json();if(SETUP)Object.assign(SETUP,{done:r.summary.done,total:r.summary.total,open:r.summary.open.length});return r}catch(e){if($('gomsg'))$('gomsg').textContent=e.message}}
// one item: switch the profile's own switch on when it is still off, then open its Ich page with a way back
async function goItem(x){if(!x)return;
  try{if(!x.mine&&x.own){await api('/api/profile/settings',xjson('PUT',{[x.own]:true}));if(typeof loadSettings==='function')await loadSettings().catch(()=>{})}
    if(x.key==='welcome')await goPut({welcome:true})}catch(e){$('gomsg').textContent=e.message;return}
  GO.from=true;if(typeof meTabs==='function')meTabs();if(typeof showExtras==='function')await showExtras();
  if(!$(x.me)){$('gomsg').textContent=t('Diese Seite ist gerade nicht da. Seite neu laden.','This page is not there right now. Reload the page.');return}
  meLast=x.me;ptab(x.me);goBar(true)}
function goBar(show){let b=$('gobar');if(!b){b=document.createElement('button');b.type='button';b.id='gobar';b.className='b gobar';
    b.onclick=()=>{goBar(false);meLast='gobox';ptab('gobox');goShow()};const body=document.querySelector('#profmodal .mebody');if(!body)return;body.prepend(b)}
  b.textContent='← '+t('Zurück zu „Los geht\'s“','Back to "Let\'s go"');b.hidden=!show||!GO.from}
async function goSay(){const box=$('gosay');if(!box)return;let f={features:[]};try{f=await (await api('/api/features')).json()}catch{}
  const clean=s=>s.replace(/^[„"]|[“"](?:\s*\(.*\))?$/g,'').replace(/^Hey Spark,\s*/,'').replace(/[“"]\s*\(.*\)$/,'').trim();
  const say=f.features.filter(x=>x.can&&x.guide).map(x=>(typeof GUIDES!=='undefined'?GUIDES.find(g=>g.id===x.guide):null)).filter(g=>g&&g.say&&g.say.length).slice(0,8)
    .map(g=>clean(t(g.say[0][0],g.say[0][1]))).filter(Boolean);
  const base=[t('Was kannst du?','What can you do?'),t('Wie wird das Wetter morgen?','What is the weather tomorrow?')];
  box.innerHTML=[...new Set(base.concat(say))].slice(0,8).map(s=>`<button type="button" class="b gotry" data-say="${esc(s)}">${esc('„'+s+'“')}</button>`).join('');
  box.querySelectorAll('[data-say]').forEach(b=>b.onclick=()=>{$('profmodal').style.display='none';if(typeof ask==='function'){goSec('chat');ask(b.dataset.say,null)}})}
// "Am Handy weitermachen", the computer's side: the QR code, then the three numbers
async function handPc(){const box=$('gohand');clearTimeout(GO.timer);
  let r;try{r=await (await api('/api/profile/handoff',xjson('POST',{base:location.origin}))).json()}catch(e){box.innerHTML=`<span class="err">${esc(e.message)}</span>`;return}
  GO.hand=r.id;box.innerHTML=`<div class="goapp"><div class="jqr">${r.qr||''}</div><div class="fh" id="handst">${t('Mit dem Handy scannen. Gilt zwei Minuten und nur einmal.','Scan with the phone. Valid for two minutes and once only.')}</div></div><div class="row" id="handnums"></div>`;
  const end=Date.now()+r.seconds*1000;
  const poll=async()=>{if(GO.hand!==r.id||!$('handnums'))return;if(Date.now()>end){$('handst').textContent=t('Abgelaufen.','Expired.');return}
    let s;try{s=await (await api('/api/profile/handoff/'+r.id)).json()}catch{$('handst').textContent=t('Abgelaufen.','Expired.');return}
    if(s.state==='claimed'&&s.choices&&!$('handnums').childElementCount){$('handst').textContent=(s.agent?s.agent+': ':'')+t('Welche Zahl zeigt dein Handy?','Which number does your phone show?');
      $('handnums').innerHTML=s.choices.map(n=>`<button class="b gonumb" type="button" data-hn="${n}">${n}</button>`).join('')+`<button class="b" type="button" data-hn="-1">${t('Keine davon','None of them')}</button>`;
      $('handnums').querySelectorAll('[data-hn]').forEach(b=>b.onclick=async()=>{try{const c=await (await api('/api/profile/handoff/'+r.id+'/confirm',xjson('POST',{num:+b.dataset.hn}))).json();
        $('handnums').innerHTML='';$('handst').textContent=c.state==='ok'?t('Dein Handy ist angemeldet und macht dort weiter.','Your phone is signed in and continues there.'):t('Abgebrochen. Für einen neuen Versuch den QR-Code neu holen.','Cancelled. Get a new QR code for another try.')}catch(e){$('handst').textContent=e.message}})}
    if(s.state==='open'||s.state==='claimed')GO.timer=setTimeout(poll,1500)};
  GO.timer=setTimeout(poll,1500)}
// after the first sign-in through an invitation (or a phone that continues): straight to "Los geht's"
async function goStart(who){SETUP=who&&who.setup||null;let first=false;try{first=sessionStorage.getItem('golets')==='1';sessionStorage.removeItem('golets')}catch{}
  if(!PROFILE||!SETUP||!SETUP.total)return;if(first||SETUP.fresh){if(SETUP.fresh)goPut({fresh:false});await openMe('gobox')}}
