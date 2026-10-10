// Admin: profiles and devices.
// ---------------------------------------------------------------- profiles and devices (admin)
// For many profiles: search, filter, sort and pages of 25 (the Spark does it); details open per profile.
const PL={q:'',show:'',sort:'name',page:0,open:'',names:[],timer:null};
const pwhen=s=>s?new Date(s*1000).toLocaleString([], {dateStyle:'short',timeStyle:'short'}):t('noch nie','never');
const perr=(id,e)=>{$(id).innerHTML=`<span class="err">${esc(e.message)}</span>`};
// The profile of a device: a list of all profiles, sorted by name. Keys a profile set up itself under Ich
// (speaker, iPhone app, Pebble watch, Home Assistant) stay with it: they show the name and where they are managed.
const popts=(sel,first)=>(first?`<option value="">${esc(first)}</option>`:'')+[...PL.names].sort((a,b)=>a.name.localeCompare(b.name))
  .map(u=>`<option value="${esc(u.id)}"${u.id===sel?' selected':''}>${esc(u.name)}</option>`).join('');
const dkind=x=>x.speaker?t('Lautsprecher, eingerichtet unter Ich → Lautsprecher','Speaker, set up under Me → Speakers')
  :x.kind==='app'||x.app?t('iPhone-App, nur fragen und hören, gekoppelt unter Ich → iPhone-App','iPhone app, only asks and listens, paired under Me → iPhone app')
  :x.kind==='watch'?t('Pebble-Uhr, gekoppelt unter Ich → Pebble-Uhr','Pebble watch, paired under Me → Pebble watch')
  :x.kind==='room'?t('Home Assistant, erzeugt unter Ich → Raum-Modus','Home Assistant, made under Me → Room mode'):'';
function profFilter(){if($('pfilter').dataset.done)return;$('pfilter').dataset.done='1';
  const o=(v,l)=>`<option value="${v}">${esc(l)}</option>`;
  $('pfilter').innerHTML=`<input id="pq" type="search" placeholder="${esc(t('Suchen: Name, Rufname oder Gerät','Search: name, call name or device'))}" style="flex:2;min-width:140px" maxlength="40">
    <select id="pshow" style="width:auto">${o('',t('alle','all'))}${o('idle',t('seit 90 Tagen nicht benutzt','not used for 90 days'))}${o('nodev',t('ohne Gerät','without a device'))}${o('mfa',t('mit zweitem Schritt','with second step'))}${o('nomfa',t('ohne zweiten Schritt','without second step'))}${o('msg',t('Nachrichten an','messages on'))}${o('nomsg',t('Nachrichten aus','messages off'))}${o('room',t('hört gerade zu','listening right now'))}</select>
    <select id="psort" style="width:auto">${o('name',t('nach Name','by name'))}${o('recent',t('zuletzt benutzt zuerst','last used first'))}${o('new',t('neueste zuerst','newest first'))}</select>`;
  $('pq').oninput=()=>{clearTimeout(PL.timer);PL.timer=setTimeout(()=>{PL.q=$('pq').value;PL.page=0;loadProf()},250)};
  $('pshow').onchange=()=>{PL.show=$('pshow').value;PL.page=0;loadProf()};$('psort').onchange=()=>{PL.sort=$('psort').value;PL.page=0;loadProf()}}
async function loadProf(){profFilter();let d;
  try{d=await (await api('/api/admin/profiles?'+new URLSearchParams({q:PL.q,show:PL.show,sort:PL.sort,page:PL.page,per:25}))).json()}catch(e){perr('pmsg',e);return}
  PL.page=d.page;PL.names=d.names;const name=id=>(d.names.find(u=>u.id===id)||{}).name||'?';
  $('duser').innerHTML=popts($('duser').value,t('Profil wählen …','Pick a profile …'));
  $('proflist').innerHTML=d.users.map(u=>`<tr><td><b>${esc(u.name)}</b>${u.call?` <span class="mut">(${esc(u.call)})</span>`:''}${u.role?` <span class="pill">${esc(PROLE()[u.role]||u.role)}</span>`:''}${u.room?` <span class="pill ok">${t('hört zu','listening')}</span>`:''}<div class="intro sm">${t('zuletzt','last used')}: ${esc(pwhen(u.last))} · ${u.devices} ${t('Gerät(e)','device(s)')} · ${u.facts} ${t('gemerkte Fakten','remembered facts')}${u.mfa?' · '+t('mit zweitem Anmeldeschritt','with second login step'):''}${u.msg?' · '+t('Nachrichten an','messages on'):''}${typeof joinSetupLine==='function'&&u.setup&&u.setup.total?' · '+joinSetupLine(u.setup):''}</div></td>
    <td style="text-align:right;white-space:nowrap"><button class="b" type="button" data-popen="${esc(u.id)}">${PL.open===u.id?t('Schließen','Close'):t('Details','Details')}</button></td></tr>${PL.open===u.id?`<tr><td colspan="2"><div id="pdetail" class="mut">…</div></td></tr>`:''}`).join('')
    ||`<tr><td class="mut">${d.all?t('Kein Profil passt.','No profile matches.'):t('Noch keine.','None yet.')}</td></tr>`;
  // Gäste as the first row: who talks without a profile, and what they get (Wer darf was has the details)
  if(d.guests&&!PL.q&&!PL.show&&!d.page)$('proflist').insertAdjacentHTML('afterbegin',`<tr class="pguest"><td><b>${t('Gäste','Guests')}</b> <span class="pill${d.guests.public?' ok':''}">${d.guests.public?t('Gastzugang an','guest access on'):t('Gastzugang aus','guest access off')}</span><div class="intro sm">${d.guests.public
      ?d.guests.features+' '+t('Funktionen ohne Anmeldung, nie persönliche Daten','functions without signing in, never personal data'):t('Ohne Profil spricht niemand mit dem Assistenten.','Without a profile nobody talks to the assistant.')}</div></td>
    <td style="text-align:right;white-space:nowrap"><button class="b" type="button" id="pguests">${t('Wer darf was','Who may do what')}</button></td></tr>`);
  if($('pguests'))$('pguests').onclick=()=>goSec('who');
  const pages=Math.max(1,Math.ceil(d.total/d.per));
  $('ppager').innerHTML=`<span class="mut">${d.total===d.all?d.all+' '+t('Profile','profiles'):d.total+' '+t('von','of')+' '+d.all+' '+t('Profilen','profiles')}${pages>1?' · '+t('Seite','page')+' '+(d.page+1)+'/'+pages:''}</span>${pages>1?`<button class="b" type="button" data-ppage="${d.page-1}"${d.page?'':' disabled'}>‹</button><button class="b" type="button" data-ppage="${d.page+1}"${d.page+1<pages?'':' disabled'}>›</button>`:''}`;
  $('ppager').querySelectorAll('[data-ppage]').forEach(b=>b.onclick=()=>{PL.page=+b.dataset.ppage;loadProf()});
  $('proflist').querySelectorAll('[data-popen]').forEach(b=>b.onclick=()=>{PL.open=PL.open===b.dataset.popen?'':b.dataset.popen;loadProf()});
  $('dadd').disabled=!d.all;
  const mid='style="vertical-align:middle"';
  $('devlist').innerHTML=d.devices.map(x=>{const k=dkind(x);return `<tr><td ${mid}>${esc(x.name)}${x.room?` <span class="pill ok">${t('hört zu','listening')}</span>`:''}<div class="intro sm">${k?esc(k)+' · ':''}${t('zuletzt','last used')}: ${x.last?esc(pwhen(x.last.t))+' · '+esc(x.last.ip||''):t('noch nie','never')}</div></td>
    <td style="vertical-align:middle;width:150px">${k?`<span title="${esc(t('Fest bei diesem Profil. Zum Wechseln dort entfernen und unter dem anderen Profil neu einrichten.','Fixed to this profile. To change it, remove it there and set it up again under the other profile.'))}">${esc(name(x.user))} <small class="mut">🔒 ${t('fest','fixed')}</small></span>`
      :`<select data-dmove="${esc(x.id)}" aria-label="${esc(t('Profil','Profile'))}" style="width:100%">${popts(x.user)}</select>`}</td>
    <td style="text-align:right;vertical-align:middle"><button class="b" type="button" data-ddel="${esc(x.id)}" data-dname="${esc(x.name)}" data-dspk="${x.speaker?'1':''}">${t('Löschen','Delete')}</button></td></tr>`}).join('')
    ||`<tr><td class="mut">${PL.q||PL.show?t('Keine Geräte bei den gezeigten Profilen.','No devices with the profiles shown.'):t('Noch keine.','None yet.')}</td></tr>`;
  $('devlist').querySelectorAll('[data-dmove]').forEach(i=>i.onchange=()=>devUser(i.dataset.dmove,i.value));
  $('devlist').querySelectorAll('[data-ddel]').forEach(b=>b.onclick=()=>delDev(b.dataset.ddel,b.dataset.dname,b.dataset.dspk));
  if(PL.open&&$('pdetail'))profDetail(PL.open)}
// One profile in detail (plan „Vereinheitlichen“ Phase 5): Zugang (PIN, zweiter Schritt, Rolle, Browser), Rufname,
// Geräte, Funktionen „n von m an“ (springt zu Wer darf was), Rechte (Aufträge, Spark-Update aus der App, Platz für
// Uploads) and Löschen. Everything that used to sit on other pages per profile is here; the pages stay for the overview.
const PROLE=()=>typeof ROLE_NAME!=='undefined'?ROLE_NAME:{owner:t('Haupt-Admin','Main admin'),coadmin:t('Mit-Admin','Co-admin'),manager:t('Verwalter','Manager')};
const pbtn=(id,l,extra='')=>`<button class="b" type="button" id="${id}"${extra}>${esc(l)}</button>`;
const pmb=b=>b>=1024**2?(b/1024**2).toFixed(b>=10*1024**2?0:1)+' MB':Math.ceil(b/1024)+' KB';
async function profDetail(id){let u;try{u=await (await api('/api/admin/profiles/'+encodeURIComponent(id))).json()}catch(e){perr('pmsg',e);return}
  const R=PROLE(),r=u.rights,h3=x=>`<h3 class="sec">${esc(x)}</h3>`,sel=(v,cur,l)=>`<option value="${esc(v)}"${v===cur?' selected':''}>${esc(l)}</option>`;
  let role='';
  if(u.main)role=setRow(esc(t('Admin-Rechte','Admin rights')),esc(u.roles?t('Haupt-Admin: du als Profil, eine Anmeldung. Mit-Admin darf fast alles, Verwalter nur Zustand, Profile und Funktionen. Gilt erst mit dem zweiten Schritt.','Main admin: you as a profile, one login. A co-admin may do almost everything, a manager only status, profiles and functions. Works only with the second step.')
      :t('Der Schalter „Benutzer als Admin“ ist aus (Einstellungen → Sicherheit).','The switch "Users as admins" is off (Settings → Security).')),
    `<select id="prole" aria-label="${esc(t('Admin-Rechte','Admin rights'))}">${sel('',u.role,t('keine','none'))}${u.owner||u.role==='owner'?sel('owner',u.role,R.owner):''}${sel('coadmin',u.role,R.coadmin)}${sel('manager',u.role,R.manager)}</select>`);
  else if(u.role)role=setRow(esc(t('Admin-Rechte','Admin rights')),esc(t('Ändert nur der Hauptadmin.','Only the main admin changes it.')),`<span class="pill">${esc(R[u.role]||u.role)}</span>`);
  const sess=u.sessions.map(x=>`<li><span>${esc(x.agent)}<br><small class="mut">${t('angemeldet','signed in')} ${esc(pwhen(x.first))} · ${t('zuletzt','last used')} ${esc(pwhen(x.last))}</small></span><button class="b" type="button" data-psess="${esc(x.id)}">${t('Abmelden','Sign out')}</button></li>`).join('')
    ||`<li class="mut">${t('Kein Browser angemeldet.','No browser signed in.')}</li>`;
  let rights='';
  if(r){const off=t('Auf dem Spark aus','Off on the Spark');
    rights=h3(t('Rechte','Rights'))
    +setRow(esc(t('Aufträge im Hintergrund','Background jobs')),esc(t('Was der Assistent für dieses Profil allein erledigen darf. Das Profil schaltet es dann unter Ich ein.','What the assistant may do alone for this profile. The profile then switches it on under Ich.')),
      `<select id="pagent" aria-label="${esc(t('Aufträge','Jobs'))}">${sel('',r.agent.level,t('aus','off'))}${sel('read',r.agent.level,t('nur lesen und berichten','read and report only'))}${sel('act',r.agent.level,t('auch handeln mit „Ja“','also act after "Yes"'))}</select>`,{why:r.agent.spark?'':off})
    +setRow(esc(t('Spark-Update aus der iPhone-App','Spark update from the iPhone app')),esc(u.mfa?t('Hinweise bekommen und das Update selbst starten (mit Face ID und Code).','Get notices and start the update itself (with Face ID and code).'):t('Starten geht erst mit dem zweiten Anmeldeschritt.','Starting needs the second login step first.')),
      `<span class="row" style="gap:10px;flex-wrap:nowrap"><label class="chk"><input type="checkbox" id="pupdn"${r.update.notify?' checked':''}> ${t('Hinweise','Notices')}</label><label class="chk"><input type="checkbox" id="pupds"${r.update.start?' checked':''}${u.mfa?'':' disabled'}> ${t('Starten','Start')}</label></span>`,{why:r.update.spark?'':off})
    +setRow(esc(t('Platz für Uploads','Space for uploads')),esc(t('Belegt ','Used ')+pmb(r.quota.used)+t(' von ',' of ')+r.quota.mb+' MB'+(r.quota.own?'':t(' (Standard)',' (default)'))),
      `<span class="row" style="gap:6px;flex-wrap:nowrap"><input id="pquota" type="number" min="50" max="50000" step="50" style="width:90px" value="${r.quota.own?r.quota.mb:''}" placeholder="${r.quota.default_mb}" aria-label="MB">${pbtn('pquotasave',t('Speichern','Save'))}</span>`,{why:r.quota.spark?'':t('Dokumente sind auf dem Spark aus','Documents are off on the Spark')})}
  $('pdetail').innerHTML=`<div class="pdet"><div class="intro sm">${t('Angelegt','Created')}: ${esc(pwhen(u.created))} · ${t('zuletzt benutzt','last used')}: ${esc(pwhen(u.last))} · ${u.facts} ${t('gemerkte Fakten','remembered facts')} · ${u.msg?t('Nachrichten an','messages on'):t('Nachrichten aus','messages off')}</div>
    ${h3(t('Zugang','Access'))}
    ${setRow(esc('PIN'),esc(t('Eine neue PIN meldet alle Browser dieses Profils ab.','A new PIN signs out every browser of this profile.')),pbtn('ppinnew',t('PIN ändern','Change PIN')))}
    ${setRow(esc(t('PIN-Link','PIN link')),esc(t('Ein Link, mit dem die Person ihre PIN selbst wählt (gilt einen Tag, einmal). Besser als eine PIN weiterzusagen.','A link with which the person picks the PIN themselves (one day, once). Better than passing a PIN on.')),pbtn('ppinlink',t('PIN-Link','PIN link')))}
    <div id="ppinout"></div>
    ${setRow(esc(t('Zweiter Anmeldeschritt','Second login step')),esc(u.mfa?t('An. Zurücksetzen, falls Handy und Wiederherstellungscodes weg sind.','On. Reset it if phone and recovery codes are lost.'):t('Aus. Das Profil schaltet ihn unter Ich → Sicherheit ein.','Off. The profile switches it on under Ich → Security.')),
      u.mfa?pbtn('pmfa',t('Zurücksetzen','Reset')):`<span class="mut">${t('aus','off')}</span>`)}
    ${role}
    <b>${t('Angemeldete Browser','Signed-in browsers')}</b><ul class="facts" id="psess">${sess}</ul>
    ${h3(t('Rufname','Call name'))}
    <div class="rowin"><input id="pcall" maxlength="40" value="${esc(u.call||'')}" placeholder="${esc(t('z. B. Thomas M. oder Papa','e.g. Thomas M. or Dad'))}" aria-label="${esc(t('Rufname für Nachrichten','Call name for messages'))}"><button class="b" type="button" id="pcallsave">${t('Speichern','Save')}</button></div>
    <div class="fh">${t('So können andere ihn in Nachrichten nennen, wenn Namen sich ähneln. Muss eindeutig sein.','How others can name this profile in messages when names are alike. Must be unique.')}</div>
    ${h3(t('Geräte','Devices'))}<ul class="facts">${u.devices.map(x=>`<li><span>${esc(x.name)}${x.room?` <span class="pill ok">${t('hört zu','listening')}</span>`:''} <small class="mut">${x.speaker?t('Lautsprecher','speaker'):x.app?t('iPhone-App','iPhone app'):t('Schlüssel','key')} · ${t('zuletzt','last used')}: ${x.last?esc(pwhen(x.last.t)):t('noch nie','never')}</small></span></li>`).join('')||`<li class="mut">${t('Keine.','None.')}</li>`}</ul>
    ${h3(t('Funktionen','Functions'))}
    ${setRow(esc(u.features.on+' '+t('von','of')+' '+u.features.of+' '+t('an','on')),esc(t('Funktionen mit eigenem Schalter, die der Spark erlaubt. Das Profil schaltet sie unter Ich, du unter Wer darf was.','Functions with an own switch the Spark allows. The profile switches them under Ich, you under Who may do what.')),pbtn('pfeat',t('Wer darf was','Who may do what')))}
    ${u.setup&&u.setup.total?setRow(joinSetupLine(u.setup),esc(u.setup.open.length?t('Offen: ','Open: ')+u.setup.open.join(', '):t('Alles eingerichtet.','Everything set up.')),u.setup.open.length?pbtn('premind',t('Erinnern','Remind')):''):''}
    ${rights}
    ${h3(t('Daten','Data'))}
    ${setRow(esc(t('Profil löschen','Delete profile')),esc(t('Mit Gedächtnis, Gesprächen und Geräten. Geht nicht rückgängig.','With memory, conversations and devices. Cannot be undone.')),pbtn('pdel',t('Löschen','Delete')))}</div>`;
  const ok=m=>{$('pmsg').textContent=m},again=()=>profDetail(id);
  $('ppinlink').onclick=()=>joinPinLink(id,u.name,$('ppinout'));
  if($('premind'))$('premind').onclick=async()=>{try{const r=await (await api('/api/admin/profiles/'+encodeURIComponent(id)+'/remind',jpost('POST',{}))).json();
    ok(r.sent?t('Erinnerung geschickt.','Reminder sent.'):t('Keine Mitteilung möglich: das Profil hat noch kein Gerät mit Mitteilungen.','No notification possible: the profile has no device with notifications yet.'))}catch(e){perr('pmsg',e)}};
  $('pcallsave').onclick=async()=>{try{const r=await (await api('/api/admin/profiles/'+encodeURIComponent(id)+'/call',jpost('PUT',{call:$('pcall').value}))).json();
    ok(r.call?t('Rufname gespeichert: ','Call name saved: ')+r.call:t('Rufname entfernt.','Call name removed.'));loadProf()}catch(e){perr('pmsg',e)}};
  if($('pmfa'))$('pmfa').onclick=()=>resetMfa(id,u.name);$('ppinnew').onclick=()=>newPin(id,u.name);$('pdel').onclick=()=>delProf(id,u.name);
  $('pfeat').onclick=()=>goSec('who');
  $('psess').querySelectorAll('[data-psess]').forEach(b=>b.onclick=async()=>{try{await api('/api/admin/profiles/'+encodeURIComponent(id)+'/sessions/'+encodeURIComponent(b.dataset.psess),{method:'DELETE'});ok(t('Abgemeldet.','Signed out.'))}catch(e){perr('pmsg',e)}again()});
  if($('prole'))$('prole').onchange=async()=>{const v=$('prole').value;
    if(!v&&!confirm(t('Rolle entziehen? Ein offener Admin-Modus endet sofort.','Take the role away? An open admin mode ends at once.'))){$('prole').value=u.role;return}
    try{await api('/api/admin/roles/'+encodeURIComponent(id),jpost('PUT',{role:v}));ok(t('Rolle gespeichert.','Role saved.'));loadProf()}catch(e){perr('pmsg',e);$('prole').value=u.role}};
  if(!r)return;
  $('pagent').onchange=async()=>{try{await api('/api/admin/agent/levels/'+encodeURIComponent(id),jpost('PUT',{level:$('pagent').value}));ok(t('Gespeichert.','Saved.'))}catch(e){perr('pmsg',e);again()}};
  const upd=async()=>{try{await api('/api/admin/iphone-update/'+encodeURIComponent(id),jpost('PUT',{notify:$('pupdn').checked,start:$('pupds').checked}));ok(t('Gespeichert.','Saved.'))}catch(e){perr('pmsg',e)}again()};
  $('pupdn').onchange=upd;$('pupds').onchange=upd;
  $('pquotasave').onclick=async()=>{const v=$('pquota').value.trim();
    try{await api('/api/admin/wissen/quota',jpost('POST',{owner:id,mb:v===''?null:Number(v)}));ok(t('Gespeichert.','Saved.'))}catch(e){perr('pmsg',e)}again()}}
const jpost=(m,b)=>({method:m,headers:{'Content-Type':'application/json'},body:JSON.stringify(b)});
$('padd').onclick=async()=>{try{await api('/api/admin/profiles',jpost('POST',{name:$('pname').value,pin:$('ppin').value}));
    $('pmsg').textContent=t('Angelegt: ','Created: ')+$('pname').value;$('pname').value=$('ppin').value='';$('pnew').open=false;loadProf()}catch(e){perr('pmsg',e)}};
window.newPin=async(id,n)=>{const pin=prompt(t('Neue PIN für ','New PIN for ')+n+t(' (meldet alle Browser dieses Profils ab):',' (logs out all browsers of this profile):'));if(!pin)return;
  try{await api('/api/admin/profiles/'+id,jpost('PUT',{pin}));$('pmsg').textContent=t('PIN geändert.','PIN changed.')}catch(e){perr('pmsg',e)}};
window.resetMfa=async(id,n)=>{if(!confirm(t('Zweiten Anmeldeschritt für „','Switch off the second login step for "')+n+t('“ ausschalten? Danach reicht wieder die PIN.','"? Then the PIN alone is enough again.')))return;
  try{await api('/api/admin/profiles/'+id+'/mfa',{method:'DELETE'});$('pmsg').textContent=t('Zurückgesetzt.','Reset.');loadProf()}catch(e){perr('pmsg',e)}};
window.delProf=async(id,n)=>{if(!confirm(t('Profil „','Delete profile "')+n+t('“ mit seinem ganzen Gedächtnis und seinen Geräten löschen?','" with all its memory and devices?')))return;
  try{await api('/api/admin/profiles/'+id,{method:'DELETE'});PL.open='';$('pmsg').textContent=t('Gelöscht: ','Deleted: ')+n;loadProf()}catch(e){perr('pmsg',e)}};
$('dadd').onclick=async()=>{const u=$('duser').value;if(!u){$('dmsg').innerHTML=`<span class="err">${esc(t('Bitte ein Profil wählen.','Please pick a profile.'))}</span>`;return}
  try{const r=await (await api('/api/admin/devices',jpost('POST',{name:$('dname').value,user:u}))).json();
    $('dmsg').innerHTML=`${t('Geräteschlüssel (wird nur jetzt angezeigt):','Device key (shown only now):')}<div class="token">${esc(r.token)}</div>`;$('dname').value='';$('duser').value='';$('dnew').open=false;loadProf()}
  catch(e){perr('dmsg',e)}};
window.devUser=async(id,u)=>{try{await api('/api/admin/devices/'+id,jpost('PUT',{user:u}));$('dmsg').textContent=t('Gerät umgehängt.','Device moved.')}catch(e){perr('dmsg',e)}loadProf()};
window.delDev=async(id,n,spk)=>{if(!confirm(t('Gerät „','Delete device "')+n+t('“ löschen? Sein Schlüssel gilt dann nicht mehr.','"? Its key stops working.')+(spk?t(' Der Lautsprecher muss danach neu eingerichtet werden.',' The speaker then has to be set up again.'):'')))return;
  await api('/api/admin/devices/'+id,{method:'DELETE'});$('dmsg').textContent='';loadProf()};
const sendTyped=()=>{const x=$('chattext').value.trim()||(typeof pics!=='undefined'&&pics.list.length?t('Was ist auf dem Bild?','What is in the picture?'):'');if(!x)return;$('chattext').value='';audioCtx();stopListening(true);stopAnswer();chat.nextSpoken=false;ask(x,null)};
$('chatsend').onclick=sendTyped;$('chattext').onkeydown=e=>{if(e.key==='Enter')sendTyped()};
document.addEventListener('keydown',e=>{if(e.code!=='Space'||!$('chat').classList.contains('on')||/INPUT|TEXTAREA|SELECT|BUTTON/.test(document.activeElement.tagName))return;
  e.preventDefault();$('talk').click()});
