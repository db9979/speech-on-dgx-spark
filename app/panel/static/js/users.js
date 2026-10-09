// Admin: profiles and devices.
// ---------------------------------------------------------------- profiles and devices (admin)
// For many profiles: search, filter, sort and pages of 25 (the Spark does it); details open per profile.
const PL={q:'',show:'',sort:'name',page:0,open:'',names:[],timer:null};
const pwhen=s=>s?new Date(s*1000).toLocaleString([], {dateStyle:'short',timeStyle:'short'}):t('noch nie','never');
const perr=(id,e)=>{$(id).innerHTML=`<span class="err">${esc(e.message)}</span>`};
// a profile from a typed name (the shared list of names below the table): exact, else the only one that starts with it
const pid=v=>{const s=String(v||'').trim().toLowerCase();if(!s)return '';const ex=PL.names.find(u=>u.name.toLowerCase()===s);if(ex)return ex.id;
  const st=PL.names.filter(u=>u.name.toLowerCase().startsWith(s));return st.length===1?st[0].id:''};
function profFilter(){if($('pfilter').dataset.done)return;$('pfilter').dataset.done='1';
  const o=(v,l)=>`<option value="${v}">${esc(l)}</option>`;
  $('pfilter').innerHTML=`<input id="pq" type="search" placeholder="${esc(t('Suchen: Name, Rufname oder Gerät','Search: name, call name or device'))}" style="flex:2;min-width:140px" maxlength="40">
    <select id="pshow" style="width:auto">${o('',t('alle','all'))}${o('idle',t('seit 90 Tagen nicht benutzt','not used for 90 days'))}${o('nodev',t('ohne Gerät','without a device'))}${o('mfa',t('mit zweitem Schritt','with second step'))}${o('nomfa',t('ohne zweiten Schritt','without second step'))}${o('msg',t('Nachrichten an','messages on'))}${o('nomsg',t('Nachrichten aus','messages off'))}</select>
    <select id="psort" style="width:auto">${o('name',t('nach Name','by name'))}${o('recent',t('zuletzt benutzt zuerst','last used first'))}${o('new',t('neueste zuerst','newest first'))}</select>`;
  $('pq').oninput=()=>{clearTimeout(PL.timer);PL.timer=setTimeout(()=>{PL.q=$('pq').value;PL.page=0;loadProf()},250)};
  $('pshow').onchange=()=>{PL.show=$('pshow').value;PL.page=0;loadProf()};$('psort').onchange=()=>{PL.sort=$('psort').value;PL.page=0;loadProf()};
  $('duser').placeholder=t('Profil (Name tippen)','Profile (type a name)')}
async function loadProf(){profFilter();let d;
  try{d=await (await api('/api/admin/profiles?'+new URLSearchParams({q:PL.q,show:PL.show,sort:PL.sort,page:PL.page,per:25}))).json()}catch(e){perr('pmsg',e);return}
  PL.page=d.page;PL.names=d.names;const name=id=>(d.names.find(u=>u.id===id)||{}).name||'?';
  $('pnames').innerHTML=d.names.map(u=>`<option value="${esc(u.name)}"></option>`).join('');
  $('proflist').innerHTML=d.users.map(u=>`<tr><td><b>${esc(u.name)}</b>${u.call?` <span class="mut">(${esc(u.call)})</span>`:''}<div class="intro sm">${t('zuletzt','last used')}: ${esc(pwhen(u.last))} · ${u.devices} ${t('Gerät(e)','device(s)')} · ${u.facts} ${t('gemerkte Fakten','remembered facts')}${u.mfa?' · '+t('mit zweitem Anmeldeschritt','with second login step'):''}${u.msg?' · '+t('Nachrichten an','messages on'):''}</div></td>
    <td style="text-align:right;white-space:nowrap"><button class="b" type="button" data-popen="${esc(u.id)}">${PL.open===u.id?t('Schließen','Close'):t('Details','Details')}</button></td></tr>${PL.open===u.id?`<tr><td colspan="2"><div id="pdetail" class="mut">…</div></td></tr>`:''}`).join('')
    ||`<tr><td class="mut">${d.all?t('Kein Profil passt.','No profile matches.'):t('Noch keine.','None yet.')}</td></tr>`;
  const pages=Math.max(1,Math.ceil(d.total/d.per));
  $('ppager').innerHTML=`<span class="mut">${d.total===d.all?d.all+' '+t('Profile','profiles'):d.total+' '+t('von','of')+' '+d.all+' '+t('Profilen','profiles')}${pages>1?' · '+t('Seite','page')+' '+(d.page+1)+'/'+pages:''}</span>${pages>1?`<button class="b" type="button" data-ppage="${d.page-1}"${d.page?'':' disabled'}>‹</button><button class="b" type="button" data-ppage="${d.page+1}"${d.page+1<pages?'':' disabled'}>›</button>`:''}`;
  $('ppager').querySelectorAll('[data-ppage]').forEach(b=>b.onclick=()=>{PL.page=+b.dataset.ppage;loadProf()});
  $('proflist').querySelectorAll('[data-popen]').forEach(b=>b.onclick=()=>{PL.open=PL.open===b.dataset.popen?'':b.dataset.popen;loadProf()});
  $('dadd').disabled=!d.all;
  $('devlist').innerHTML=d.devices.map(x=>`<tr><td>${esc(x.name)}<div class="intro sm">${x.speaker?t('Lautsprecher, verwaltet unter Ich → Lautsprecher · ','Speaker, managed under Me → Speakers · '):''}${x.app?t('iPhone-App, nur fragen und hören, verwaltet unter Ich → iPhone-App · ','iPhone app, only asks and listens, managed under Me → iPhone app · '):''}${t('zuletzt','last used')}: ${x.last?esc(pwhen(x.last.t))+' · '+esc(x.last.ip||''):t('noch nie','never')}</div></td><td>${x.speaker||x.app?`<span class="mut">${esc(name(x.user))}</span>`:`<input list="pnames" data-dmove="${esc(x.id)}" value="${esc(name(x.user))}" style="min-width:110px" maxlength="40">`}</td><td style="text-align:right"><button class="b" type="button" data-ddel="${esc(x.id)}" data-dname="${esc(x.name)}" data-dspk="${x.speaker?'1':''}">${t('Löschen','Delete')}</button></td></tr>`).join('')
    ||`<tr><td class="mut">${PL.q||PL.show?t('Keine Geräte bei den gezeigten Profilen.','No devices with the profiles shown.'):t('Noch keine.','None yet.')}</td></tr>`;
  $('devlist').querySelectorAll('[data-dmove]').forEach(i=>i.onchange=()=>{const u=pid(i.value);if(!u){$('dmsg').innerHTML=`<span class="err">${esc(t('Kein eindeutiges Profil mit diesem Namen.','No single profile with this name.'))}</span>`;return}devUser(i.dataset.dmove,u)});
  $('devlist').querySelectorAll('[data-ddel]').forEach(b=>b.onclick=()=>delDev(b.dataset.ddel,b.dataset.dname,b.dataset.dspk));
  if(PL.open&&$('pdetail'))profDetail(PL.open)}
async function profDetail(id){let u;try{u=await (await api('/api/admin/profiles/'+encodeURIComponent(id))).json()}catch(e){perr('pmsg',e);return}
  $('pdetail').innerHTML=`<div class="intro sm">${t('Angelegt','Created')}: ${esc(pwhen(u.created))} · ${t('zuletzt benutzt','last used')}: ${esc(pwhen(u.last))} · ${u.facts} ${t('gemerkte Fakten','remembered facts')} · ${u.mfa?t('mit zweitem Anmeldeschritt','with second login step'):t('ohne zweiten Anmeldeschritt','without second login step')} · ${u.msg?t('Nachrichten an','messages on'):t('Nachrichten aus','messages off')}</div>
    <label>${t('Rufname für Nachrichten','Call name for messages')}</label><div class="rowin"><input id="pcall" maxlength="40" value="${esc(u.call||'')}" placeholder="${esc(t('z. B. Thomas M. oder Papa','e.g. Thomas M. or Dad'))}"><button class="b" type="button" id="pcallsave">${t('Speichern','Save')}</button></div>
    <div class="fh">${t('So können andere ihn in Nachrichten nennen, wenn Namen sich ähneln. Muss eindeutig sein.','How others can name this profile in messages when names are alike. Must be unique.')}</div>
    <b>${t('Geräte','Devices')}</b><ul class="facts">${u.devices.map(x=>`<li><span>${esc(x.name)} <small class="mut">${x.speaker?t('Lautsprecher','speaker'):x.app?t('iPhone-App','iPhone app'):t('Schlüssel','key')} · ${t('zuletzt','last used')}: ${x.last?esc(pwhen(x.last.t)):t('noch nie','never')}</small></span></li>`).join('')||`<li class="mut">${t('Keine.','None.')}</li>`}</ul>
    <div class="row" style="flex-wrap:wrap;gap:6px">${u.mfa?`<button class="b" type="button" id="pmfa" title="${esc(t('Falls Handy und Wiederherstellungscodes weg sind','If phone and recovery codes are lost'))}">${t('Zweiten Schritt zurücksetzen','Reset second step')}</button>`:''}<button class="b" type="button" id="ppinnew">${t('PIN ändern','Change PIN')}</button><button class="b" type="button" id="pdel">${t('Löschen','Delete')}</button></div>`;
  $('pcallsave').onclick=async()=>{try{const r=await (await api('/api/admin/profiles/'+encodeURIComponent(id)+'/call',jpost('PUT',{call:$('pcall').value}))).json();
    $('pmsg').textContent=r.call?t('Rufname gespeichert: ','Call name saved: ')+r.call:t('Rufname entfernt.','Call name removed.');loadProf()}catch(e){perr('pmsg',e)}};
  if($('pmfa'))$('pmfa').onclick=()=>resetMfa(id,u.name);$('ppinnew').onclick=()=>newPin(id,u.name);$('pdel').onclick=()=>delProf(id,u.name)}
const jpost=(m,b)=>({method:m,headers:{'Content-Type':'application/json'},body:JSON.stringify(b)});
$('padd').onclick=async()=>{try{await api('/api/admin/profiles',jpost('POST',{name:$('pname').value,pin:$('ppin').value}));
    $('pmsg').textContent=t('Angelegt: ','Created: ')+$('pname').value;$('pname').value=$('ppin').value='';loadProf()}catch(e){perr('pmsg',e)}};
window.newPin=async(id,n)=>{const pin=prompt(t('Neue PIN für ','New PIN for ')+n+t(' (meldet alle Browser dieses Profils ab):',' (logs out all browsers of this profile):'));if(!pin)return;
  try{await api('/api/admin/profiles/'+id,jpost('PUT',{pin}));$('pmsg').textContent=t('PIN geändert.','PIN changed.')}catch(e){perr('pmsg',e)}};
window.resetMfa=async(id,n)=>{if(!confirm(t('Zweiten Anmeldeschritt für „','Switch off the second login step for "')+n+t('“ ausschalten? Danach reicht wieder die PIN.','"? Then the PIN alone is enough again.')))return;
  try{await api('/api/admin/profiles/'+id+'/mfa',{method:'DELETE'});$('pmsg').textContent=t('Zurückgesetzt.','Reset.');loadProf()}catch(e){perr('pmsg',e)}};
window.delProf=async(id,n)=>{if(!confirm(t('Profil „','Delete profile "')+n+t('“ mit seinem ganzen Gedächtnis und seinen Geräten löschen?','" with all its memory and devices?')))return;
  try{await api('/api/admin/profiles/'+id,{method:'DELETE'});PL.open='';$('pmsg').textContent=t('Gelöscht: ','Deleted: ')+n;loadProf()}catch(e){perr('pmsg',e)}};
$('dadd').onclick=async()=>{const u=pid($('duser').value);if(!u){$('dmsg').innerHTML=`<span class="err">${esc(t('Profil wählen: Namen tippen.','Pick a profile: type its name.'))}</span>`;return}
  try{const r=await (await api('/api/admin/devices',jpost('POST',{name:$('dname').value,user:u}))).json();
    $('dmsg').innerHTML=`${t('Geräteschlüssel (wird nur jetzt angezeigt):','Device key (shown only now):')}<div class="token">${esc(r.token)}</div>`;$('dname').value=$('duser').value='';loadProf()}
  catch(e){perr('dmsg',e)}};
window.devUser=async(id,u)=>{try{await api('/api/admin/devices/'+id,jpost('PUT',{user:u}));$('dmsg').textContent=t('Gerät umgehängt.','Device moved.')}catch(e){perr('dmsg',e)}loadProf()};
window.delDev=async(id,n,spk)=>{if(!confirm(t('Gerät „','Delete device "')+n+t('“ löschen? Sein Schlüssel gilt dann nicht mehr.','"? Its key stops working.')+(spk?t(' Der Lautsprecher muss danach neu eingerichtet werden.',' The speaker then has to be set up again.'):'')))return;
  await api('/api/admin/devices/'+id,{method:'DELETE'});$('dmsg').textContent='';loadProf()};
const sendTyped=()=>{const x=$('chattext').value.trim()||(typeof pics!=='undefined'&&pics.list.length?t('Was ist auf dem Bild?','What is in the picture?'):'');if(!x)return;$('chattext').value='';audioCtx();stopListening(true);stopAnswer();chat.nextSpoken=false;ask(x,null)};
$('chatsend').onclick=sendTyped;$('chattext').onkeydown=e=>{if(e.key==='Enter')sendTyped()};
document.addEventListener('keydown',e=>{if(e.code!=='Space'||!$('chat').classList.contains('on')||/INPUT|TEXTAREA|SELECT|BUTTON/.test(document.activeElement.tagName))return;
  e.preventDefault();$('talk').click()});
