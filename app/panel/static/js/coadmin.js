// Profiles as admins (V01.0.255, coadmin.py): the main admin gives roles under Einstellungen → Sicherheit, a profile
// with a role opens its admin mode under Ich → Sicherheit with a fresh code. While it is open a bar says who is admin
// until when; what only the main admin may do is hidden (class mainonly), a Verwalter sees only his pages.
let ADMIN_BY='',ADMIN_UNTIL=0,ADMIN_ROLE=null,ADMIN_KEEP=0;
const ROLE_NAME={owner:t('Haupt-Admin','Main admin'),coadmin:t('Mit-Admin','Co-admin'),manager:t('Verwalter','Manager')};
const elevated=()=>!!(ADMIN&&ADMIN_BY&&ADMIN_BY!=='main');
const hm=s=>new Date(s*1000).toLocaleTimeString([],{hour:'2-digit',minute:'2-digit'});
function coadmStart(who){ADMIN_BY=who.admin_by||'';ADMIN_UNTIL=who.admin_until||0;ADMIN_ROLE=who.admin_role||null;
  if(!elevated())return;document.body.classList.add('coadm');
  // the Haupt-Admin profile (role owner) sees what the main admin sees, only the password's own things stay hidden
  if(ADMIN_BY==='owner')document.body.classList.add('owner');else if(LG.tab==='audit')LG.tab='adm';
  if(ADMIN_BY==='manager'){document.body.classList.add('mgr');
    document.querySelectorAll('nav button[data-s=cfg]').forEach(b=>b.hidden=true);GROUPS.mon=GROUPS.mon.filter(x=>x[0]!=='test');
    // Funktionen: only "Wer darf was" (the switches over /api/admin/switches, like in the app), not the settings form
    GROUPS.feat=GROUPS.feat.filter(x=>x[0]!=='feat');lastSec.feat='who'}
  const b=$('logoutbtn');b.textContent=t('Admin-Modus beenden','End admin mode');b.onclick=coadmEnd;
  const bar=document.createElement('div');bar.id='coadmbar';bar.className='updbanner';
  const sp=document.createElement('span');sp.id='coadmtext';const end=document.createElement('button');end.type='button';end.className='b';
  end.textContent=t('Beenden','End');end.onclick=coadmEnd;bar.append(sp,end);$('updbanner').before(bar);
  bar.dataset.name=who.admin_name||'';coadmTick();setInterval(coadmTick,20e3);
  // using the page keeps the admin mode open (15 minutes without use end it, 8 hours in any case)
  const keep=()=>{if(Date.now()-ADMIN_KEEP<120e3)return;ADMIN_KEEP=Date.now();
    api('/api/admin/elevate/keep',{method:'POST'}).then(r=>r.json()).then(d=>{ADMIN_UNTIL=d.until||ADMIN_UNTIL;coadmTick()}).catch(()=>{})};
  ADMIN_KEEP=Date.now();document.addEventListener('pointerdown',keep,true);document.addEventListener('keydown',keep,true)}
function coadmTick(){const e=$('coadmtext');if(!e)return;const left=Math.round((ADMIN_UNTIL-Date.now()/1000)/60);
  if(left<0){location.reload();return}
  e.textContent=t(`Admin-Modus: ${$('coadmbar').dataset.name} als ${ROLE_NAME[ADMIN_BY]||ADMIN_BY}, bis ${hm(ADMIN_UNTIL)} (noch ${left} min ohne Bedienung)`,
    `Admin mode: ${$('coadmbar').dataset.name} as ${ROLE_NAME[ADMIN_BY]||ADMIN_BY}, until ${hm(ADMIN_UNTIL)} (${left} min left without use)`)}
async function coadmEnd(){try{await fetch('/api/admin/elevate/end',{method:'POST'})}catch{}location.reload()}
// Ich → Sicherheit: the profile's own role and its admin mode
function coadmMe(){const box=$('coadmbox');if(!box)return;box.replaceChildren();if(!ADMIN_ROLE)return;
  const r=ADMIN_ROLE,lbl=document.createElement('label');lbl.textContent=t('Admin-Rechte','Admin rights');
  const p=document.createElement('div');p.className='fh';const row=document.createElement('div');row.className='row';const msg=document.createElement('span');msg.className='fh';
  const what=r.role==='owner'?t('Haupt-Admin: alles wie mit dem Panel-Passwort, nur das Passwort selbst, sein zweiter Schritt und „Überall abmelden“ bleiben beim Passwort.','Main admin: everything like with the panel password; only the password itself, its second step and "sign out everywhere" stay with the password.')
    :r.role==='manager'?t('Verwalter: Zustand, Logs, Personen und Geräte, Funktionen ein und aus.','Manager: status, logs, profiles and devices, functions on and off.')
    :t('Mit-Admin: alles wie der Admin, außer Admin-Passwort, Rollen, Sicherungen einspielen und Admin-Profile ändern.','Co-admin: everything like the admin, except the admin password, roles, restoring backups and changing admin profiles.');
  p.textContent=what;box.append(lbl,p);
  if(elevated()){const b=document.createElement('button');b.type='button';b.className='b';b.textContent=t('Admin-Modus beenden','End admin mode');b.onclick=coadmEnd;
    msg.textContent=t('Offen bis ','Open until ')+hm(ADMIN_UNTIL)+'.';row.append(b,msg);box.append(row);return}
  if(!r.mfa||!r.main_mfa){const n=document.createElement('div');n.className='fh';
    n.textContent=!r.mfa?t('Dafür zuerst unten den zweiten Anmeldeschritt für dein Profil einschalten.','First switch on the second login step for your profile below.')
      :t('Der Hauptadmin muss erst seinen zweiten Anmeldeschritt einschalten.','The main admin has to switch on his second login step first.');box.append(n);return}
  const b=document.createElement('button');b.type='button';b.className='b p';b.textContent=t('Admin-Modus öffnen','Open admin mode');
  b.onclick=async()=>{msg.textContent='';try{await api('/api/admin/elevate',{method:'POST'});location.reload()}catch(e){msg.textContent=e.message}};
  row.append(b,msg);box.append(row);
  const h=document.createElement('div');h.className='fh';h.textContent=t('Fragt jedes Mal nach dem Code aus deiner Authenticator-App. Endet nach 15 Minuten ohne Bedienung, spätestens nach 8 Stunden.','Asks for the code from your authenticator app every time. Ends after 15 minutes without use, after 8 hours at the latest.');box.append(h)}
// Einstellungen → Sicherheit (main admin only): the switch, who has which role, who hears of admin modes
async function coadmAdmin(){const box=$('coadmlist');if(!box||elevated()&&ADMIN_BY!=='owner')return;let d;
  try{d=await (await api('/api/admin/roles')).json()}catch{return}
  $('coadmon').checked=d.on;$('coadmon').disabled=!d.on&&!d.main_mfa;
  const all=await (await api('/api/admin/profiles?per=0')).json().catch(()=>({users:[]}));
  const users=(all.users||[]).map(u=>({id:u.id,name:u.name})),role=Object.fromEntries(d.users.map(u=>[u.id,u]));
  const opt=(v,l,sel)=>`<option value="${esc(v)}"${sel?' selected':''}>${esc(l)}</option>`;
  box.innerHTML=(d.main_mfa?'':`<div class="fh err">${esc(t('Geht erst mit dem zweiten Anmeldeschritt für den Hauptadmin (oben).','Needs the second login step for the main admin first (above).'))}</div>`)+
    `<table><tbody>${d.users.map(u=>`<tr><td><b>${esc(u.name)}</b><div class="intro sm">${esc(ROLE_NAME[u.role]||u.role)}${u.mfa?'':' · '+esc(t('ohne zweiten Anmeldeschritt: noch kein Admin-Modus','without second login step: no admin mode yet'))}</div></td>
      <td style="text-align:right"><button class="b" type="button" data-rmrole="${esc(u.id)}">${esc(t('Entziehen','Take away'))}</button></td></tr>`).join('')||
      `<tr><td class="mut">${esc(t('Noch kein Profil mit Admin-Rechten.','No profile with admin rights yet.'))}</td></tr>`}</tbody></table>
    <div class="row" style="margin-top:8px;gap:8px;flex-wrap:wrap"><select id="coadmuser" style="width:auto;flex:1;min-width:160px" aria-label="${esc(t('Profil','Profile'))}">${opt('',t('Profil wählen …','Choose a profile …'),true)}${users.map(u=>opt(u.id,u.name,false)).join('')}</select>
      <select id="coadmrole" style="width:auto" aria-label="${esc(t('Admin-Rechte','Admin rights'))}">${elevated()?'':opt('owner',ROLE_NAME.owner,false)}${opt('coadmin',ROLE_NAME.coadmin,true)}${opt('manager',ROLE_NAME.manager,false)}</select>
      <button class="b" type="button" id="coadmset">${esc(t('Rolle geben','Give role'))}</button></div>
    <div class="setrow"><div class="lbl"><b>${esc(t('Bescheid geben','Notify'))}</b><span>${esc(t('Öffnet ein Profil den Admin-Modus, bekommt dieses Profil eine Mitteilung (Push).','When a profile opens the admin mode, this profile gets a notification (push).'))}</span></div>
      <select id="coadmnotify">${opt('',t('Niemand','Nobody'),!d.notify)}${users.map(u=>opt(u.id,u.name,u.id===d.notify)).join('')}</select></div>
    <div class="fh" id="coadmmsg"></div>`;
  const done=async(p,o)=>{try{await api(p,o);$('coadmmsg').textContent=t('Gespeichert.','Saved.')}catch(e){$('coadmmsg').textContent=e.message;return}coadmAdmin()};
  box.querySelectorAll('[data-rmrole]').forEach(b=>b.onclick=()=>{if(confirm(t('Rolle entziehen? Ein offener Admin-Modus endet sofort.','Take the role away? An open admin mode ends at once.')))
    done('/api/admin/roles/'+encodeURIComponent(b.dataset.rmrole),xjson('PUT',{role:''}))});
  $('coadmset').onclick=()=>{const u=$('coadmuser').value;if(!u)return;
    if(role[u]&&role[u].role===$('coadmrole').value)return;done('/api/admin/roles/'+encodeURIComponent(u),xjson('PUT',{role:$('coadmrole').value}))};
  $('coadmnotify').onchange=()=>done('/api/admin/roles',xjson('PUT',{notify:$('coadmnotify').value}))}
if($('coadmon'))$('coadmon').onchange=async e=>{const on=e.target.checked;
  try{await api('/api/admin/roles',xjson('PUT',{on}));$('coadmmsg')&&($('coadmmsg').textContent=t('Gespeichert.','Saved.'))}
  catch(x){e.target.checked=!on;if($('coadmmsg'))$('coadmmsg').textContent=x.message}coadmAdmin()};
// Logs → Admin-Protokoll: admin actions with who did them (the main admin sees all, a profile in its admin mode its own)
const ADM_EVENT={admin_login:t('Hauptadmin angemeldet','Main admin signed in'),admin_login_failed:t('Admin-Anmeldung falsch','Admin sign-in wrong'),
  admin_code_failed:t('Admin-Code falsch','Admin code wrong'),admin_mode_on:t('Admin-Modus geöffnet','Admin mode opened'),admin_mode_off:t('Admin-Modus beendet','Admin mode ended'),
  admin_mode_failed:t('Admin-Modus: Code falsch','Admin mode: wrong code'),admin_role:t('Rolle geändert','Role changed'),admin_roles_switch:t('Benutzer als Admin','Users as admins'),
  admin_mfa_on:t('Zweiter Schritt Hauptadmin an','Main admin second step on'),admin_mfa_off:t('Zweiter Schritt Hauptadmin aus','Main admin second step off'),
  admin_logout_everywhere:t('Hauptadmin überall abgemeldet','Main admin signed out everywhere'),
  feature_profile:t('Funktion für ein Profil','Function for a profile'),agent_level:t('Aufträge für ein Profil','Jobs for a profile'),person_priority:t('Vorrang für ein Profil','Priority for a profile'),
  iphone_update_rights:t('Spark-Update aus der App','Spark update from the app')};
async function adminRows(){const d=await (await api('/api/admin/protocol?limit=500')).json();
  return d.events.map(e=>{const dt=new Date(e.t*1000),by=e.by==='main'?t('Hauptadmin','Main admin'):e.by?(d.names[e.by]||e.by):(e.name||(e.uid&&d.names[e.uid])||'');
    const what=e.event==='change'?`${e.method} ${e.path} → ${e.status}`:(ADM_EVENT[e.event]||e.event)+(e.uid&&e.event==='admin_role'?' ('+(d.names[e.uid]||e.uid)+')':'')+(e.detail?' – '+e.detail:'');
    const msg=`${by?by+': ':''}${what}`+(e.ip?`  (${e.ip})`:'');
    return {t:dt.toTimeString().slice(0,8),area:'',level:/fail/.test(e.event)||(e.status>=400)?'warn':'',msg,raw:`${dt.toLocaleString()}  ${msg}`}})}
