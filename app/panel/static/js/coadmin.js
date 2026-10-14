// Profiles as admins (coadmin.py; since V01.0.541 without the admin mode, plan plaene/admin-ohne-zweite-stufe.md):
// a profile with a role is admin in its own login, no second stage. Admins see the admin pages in the same menu;
// what only the panel password may do is hidden (class pwonly), a Verwalter sees only his pages (class mgr hides mainonly).
let ADMIN_BY='',ADMIN_ROLE=null;
const ROLE_NAME={admin:t('Admin','Admin'),manager:t('Verwalter','Manager')};
const elevated=()=>!!(ADMIN&&ADMIN_BY&&ADMIN_BY!=='main');
function coadmStart(who){ADMIN_BY=who.admin_by||'';ADMIN_ROLE=who.admin_role||null;
  if(!elevated())return;document.body.classList.add('coadm');
  if(ADMIN_BY!=='admin'&&LG.tab==='audit')LG.tab='adm';
  if(ADMIN_BY==='manager'){document.body.classList.add('mgr');
    document.querySelectorAll('nav button[data-s=cfg]').forEach(b=>b.hidden=true);GROUPS.mon=GROUPS.mon.filter(x=>x[0]!=='test'&&x[0]!=='verb'&&x[0]!=='usage'&&x[0]!=='tech');
    // Funktionen: only "Wer darf was" (the blocks, to lift them), not the settings form
    GROUPS.feat=GROUPS.feat.filter(x=>x[0]!=='feat'&&x[0]!=='route');lastSec.feat='who'}
  // signing out is the profile's own sign-out: the admin rights end with it
  const b=$('logoutbtn');b.onclick=async()=>{try{await /*raw: logout must not open the login or a code prompt*/fetch('/api/profile/logout',{method:'POST'})}catch{}location.reload()}}
// Ich → Sicherheit: the profile's own role, and why it rests when it does
function coadmMe(){const box=$('coadmbox');if(!box)return;box.replaceChildren();if(!ADMIN_ROLE)return;
  const r=ADMIN_ROLE,lbl=document.createElement('label');lbl.textContent=t('Admin-Rechte','Admin rights');
  const p=document.createElement('div');p.className='fh';
  p.textContent=r.role==='manager'?t('Verwalter: Zustand, Logs, Personen und Geräte, Sperren aufheben. Funktionen schaltet und sperrt nur der Admin.','Manager: status, logs, profiles and devices, lifting blocks. Only the admin switches and blocks functions.')
    :t('Admin: alles, nur das Panel-Passwort (Notzugang) selbst und sein zweiter Schritt bleiben beim Passwort.','Admin: everything; only the panel password (emergency access) itself and its second step stay with the password.')
     +(r.main?' '+t('Du bist Haupt-Admin: dein Code gilt auch für den Notzugang.','You are the main admin: your code also counts for the emergency access.'):'');
  box.append(lbl,p);const n=document.createElement('div');n.className='fh';
  n.textContent=r.acts?t('Gilt jetzt, solange du angemeldet bist. Schutz-Änderungen fragen weiter nach Code oder Face ID.','In effect now, as long as you are signed in. Protection changes still ask for the code or Face ID.')
    :!r.mfa?t('Ruht: dafür unten den zweiten Anmeldeschritt einschalten.','Resting: switch on the second login step below.')
    :t('Ruht in dieser Anmeldung: einmal ab- und mit Code oder Face ID wieder anmelden.','Resting in this sign-in: sign out once and back in with the code or Face ID.');
  if(!r.acts)n.classList.add('err');box.append(n)}
// Einstellungen → Sicherheit: who has which role, who is the main admin
async function coadmAdmin(){const box=$('coadmlist');if(!box||ADMIN_BY==='manager')return;let d;
  try{d=await (await api('/api/admin/roles')).json()}catch{return}
  const all=await (await api('/api/admin/profiles?per=0')).json().catch(()=>({users:[]}));
  const users=(all.users||[]).map(u=>({id:u.id,name:u.name})),role=Object.fromEntries(d.users.map(u=>[u.id,u]));
  // the main one changes only itself or the panel password (coadmin.set_main)
  const mayMain=!elevated()||(PROFILE&&PROFILE.id===d.main);
  const opt=(v,l,sel)=>`<option value="${esc(v)}"${sel?' selected':''}>${esc(l)}</option>`;
  box.innerHTML=`<table><tbody>${d.users.map(u=>`<tr><td><b>${esc(u.name)}</b><div class="intro sm">${esc(ROLE_NAME[u.role]||u.role)}${u.main?' · '+esc(t('Haupt-Admin','Main admin')):''}${u.mfa?'':' · '+esc(t('ohne zweiten Anmeldeschritt: Rechte ruhen','without second login step: rights rest'))}</div></td>
      <td style="text-align:right;white-space:nowrap">${mayMain&&u.role==='admin'&&!u.main&&u.mfa?`<button class="b" type="button" data-mkmain="${esc(u.id)}">${esc(t('Haupt-Admin','Main admin'))}</button> `:''}<button class="b" type="button" data-rmrole="${esc(u.id)}">${esc(t('Entziehen','Take away'))}</button></td></tr>`).join('')||
      `<tr><td class="mut">${esc(t('Noch kein Profil mit Admin-Rechten.','No profile with admin rights yet.'))}</td></tr>`}</tbody></table>
    <div class="row" style="margin-top:8px;gap:8px;flex-wrap:wrap"><select id="coadmuser" style="width:auto;flex:1;min-width:160px" aria-label="${esc(t('Profil','Profile'))}">${opt('',t('Profil wählen …','Choose a profile …'),true)}${users.map(u=>opt(u.id,u.name,false)).join('')}</select>
      <select id="coadmrole" style="width:auto" aria-label="${esc(t('Admin-Rechte','Admin rights'))}">${opt('admin',ROLE_NAME.admin,true)}${opt('manager',ROLE_NAME.manager,false)}</select>
      <button class="b" type="button" id="coadmset">${esc(t('Rolle geben','Give role'))}</button></div>
    <div class="fh" id="coadmmsg"></div>`;
  const done=async(p,o)=>{try{await api(p,o);$('coadmmsg').textContent=t('Gespeichert.','Saved.')}catch(e){$('coadmmsg').textContent=e.message;return}coadmAdmin()};
  box.querySelectorAll('[data-rmrole]').forEach(b=>b.onclick=()=>{if(confirm(t('Rolle entziehen? Die Admin-Rechte enden sofort.','Take the role away? The admin rights end at once.')))
    done('/api/admin/roles/'+encodeURIComponent(b.dataset.rmrole),xjson('PUT',{role:''}))});
  box.querySelectorAll('[data-mkmain]').forEach(b=>b.onclick=()=>{if(confirm(t('Zum Haupt-Admin machen? Sein Code gilt dann auch für den Notzugang.','Make the main admin? Their code then also counts for the emergency access.')))
    done('/api/admin/roles',xjson('PUT',{main:b.dataset.mkmain}))});
  $('coadmset').onclick=()=>{const u=$('coadmuser').value;if(!u)return;
    if(role[u]&&role[u].role===$('coadmrole').value)return;done('/api/admin/roles/'+encodeURIComponent(u),xjson('PUT',{role:$('coadmrole').value}))}}
// Logs → Admin-Protokoll: admin actions with who did them (admins see all, a Verwalter his own)
const ADM_EVENT={admin_login:t('Hauptadmin angemeldet','Main admin signed in'),admin_login_failed:t('Admin-Anmeldung falsch','Admin sign-in wrong'),
  admin_code_failed:t('Admin-Code falsch','Admin code wrong'),admin_profile_login:t('Admin-Profil angemeldet','Admin profile signed in'),
  admin_role:t('Rolle geändert','Role changed'),admin_role_refused:t('Rolle abgewiesen','Role refused'),admin_main:t('Haupt-Admin gewählt','Main admin chosen'),
  admin_mode_on:t('Admin-Modus geöffnet (früher)','Admin mode opened (before)'),admin_mode_off:t('Admin-Modus beendet (früher)','Admin mode ended (before)'),admin_roles_switch:t('Benutzer als Admin (früher)','Users as admins (before)'),
  admin_mfa_on:t('Zweiter Schritt Hauptadmin an','Main admin second step on'),admin_mfa_off:t('Zweiter Schritt Hauptadmin aus','Main admin second step off'),
  admin_logout_everywhere:t('Hauptadmin überall abgemeldet','Main admin signed out everywhere'),
  feature_profile:t('Funktion für ein Profil','Function for a profile'),agent_level:t('Aufträge für ein Profil','Jobs for a profile'),person_priority:t('Vorrang für ein Profil','Priority for a profile'),
  iphone_update_rights:t('Spark-Update aus der App','Spark update from the app')};
// Rückgängig (undo.py, plan „Bedienung gesamt“ C5, V01.0.286): above the admin log the last saved changes of the
// settings with their old values; "Rückgängig" puts back what is still as that change left it (same checks as saving).
const undoVal=v=>v===true?t('an','on'):v===false?t('aus','off'):v===''?'–':String(v);
function undoName(k){const i=document.getElementById(k),r=i&&i.closest('.setrow'),b=r&&r.querySelector('.lbl b');
  return b?b.textContent.trim():(i&&i.previousElementSibling&&i.previousElementSibling.tagName==='LABEL'?i.previousElementSibling.textContent.trim():k)}
async function loadUndo(){const box=$('logundo');if(!box)return;let d;
  try{d=await (await api('/api/admin/undo')).json()}catch{box.hidden=true;return}
  const key=JSON.stringify(d);if(key===loadUndo.last&&box.childElementCount){box.hidden=false;return}loadUndo.last=key;
  box.textContent='';box.hidden=!d.items.length;if(!d.items.length)return;
  const h=document.createElement('div');h.className='mgrp';h.textContent=t('Letzte Änderungen an Einstellungen','Latest settings changes');box.appendChild(h);
  for(const x of d.items.slice(0,10)){const r=document.createElement('div');r.className='zrow';const tx=document.createElement('span');
    const who=x.by==='main'?t('Panel-Passwort','Panel password'):x.by||'';const b=document.createElement('b');b.textContent=new Date(x.t*1000).toLocaleString([],{day:'numeric',month:'numeric',hour:'2-digit',minute:'2-digit'})+(who?' · '+who:'');
    const ch=x.changes.slice(0,3).map(c=>undoName(c.k)+': '+undoVal(c.old)+' → '+undoVal(c.new)).join(' · ')+(x.changes.length>3?t(` · und ${x.changes.length-3} mehr`,` · and ${x.changes.length-3} more`):'');
    tx.append(b,document.createElement('br'),ch);const btn=document.createElement('button');btn.type='button';btn.className='b';
    btn.textContent=x.undone?t('Rückgängig gemacht','Undone'):t('Rückgängig','Undo');btn.disabled=x.undone;
    btn.onclick=async()=>{if(!confirm(t('Diese Änderung rückgängig machen? Werte, die seitdem wieder geändert wurden, bleiben.','Undo this change? Values changed again since stay.')))return;
      btn.disabled=true;try{const res=await (await api('/api/admin/undo/'+encodeURIComponent(x.id),{method:'POST'})).json();
        if(typeof loadCfg==='function')await loadCfg().catch(()=>{});
        if(res.kept&&res.kept.length)alert(t('Zurückgesetzt. Seitdem wieder geändert und deshalb geblieben: ','Undone. Changed again since and so kept: ')+res.kept.map(undoName).join(', '))}
      catch(e){alert(e.message)}loadUndo.last='';loadUndo()};
    r.append(tx,btn);box.appendChild(r)}}
window.loadUndo=loadUndo;
async function adminRows(){const d=await (await api('/api/admin/protocol?limit=500')).json();
  return d.events.map(e=>{const dt=new Date(e.t*1000),by=e.by==='main'?t('Panel-Passwort','Panel password'):e.by?(d.names[e.by]||e.by):(e.name||(e.uid&&d.names[e.uid])||'');
    const what=e.event==='change'?`${e.method} ${e.path} → ${e.status}`:(ADM_EVENT[e.event]||e.event)+(e.uid&&/^admin_(role|main)/.test(e.event)?' ('+(d.names[e.uid]||e.uid)+')':'')+(e.detail?' – '+e.detail:'');
    const msg=`${by?by+': ':''}${what}`+(e.ip?`  (${e.ip})`:'');
    return {t:dt.toTimeString().slice(0,8),area:'',level:/fail/.test(e.event)||(e.status>=400)?'warn':'',msg,raw:`${dt.toLocaleString()}  ${msg}`}})}
