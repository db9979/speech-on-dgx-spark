// Admin: profiles and devices.
// ---------------------------------------------------------------- profiles and devices (admin)
async function loadProf(){let d;try{d=await (await api('/api/admin/profiles')).json()}catch(e){$('pmsg').innerHTML=`<span class="err">${esc(e.message)}</span>`;return}
  const name=id=>(d.users.find(u=>u.id===id)||{}).name||'?';
  $('proflist').innerHTML=d.users.map(u=>`<tr><td>${esc(u.name)}<div class="intro sm">${u.facts} ${t('gemerkte Fakten','remembered facts')}${u.mfa?' · '+t('mit zweitem Anmeldeschritt','with second login step'):''}</div></td><td style="text-align:right;white-space:nowrap">${u.mfa?`<button class="b" onclick="resetMfa('${escq(u.id)}','${escq(u.name)}')" title="${t('Falls Handy und Wiederherstellungscodes weg sind','If phone and recovery codes are lost')}">${t('Zweiten Schritt zurücksetzen','Reset second step')}</button> `:''}<button class="b" onclick="newPin('${escq(u.id)}','${escq(u.name)}')">${t('PIN ändern','Change PIN')}</button> <button class="b" onclick="delProf('${escq(u.id)}','${escq(u.name)}')">${t('Löschen','Delete')}</button></td></tr>`).join('')||`<tr><td class="mut">${t('Noch keine.','None yet.')}</td></tr>`;
  const opts=sel=>d.users.map(u=>`<option value="${esc(u.id)}"${u.id===sel?' selected':''}>${esc(u.name)}</option>`).join('');
  $('duser').innerHTML=opts();$('dadd').disabled=!d.users.length;
  $('devlist').innerHTML=d.devices.map(x=>`<tr><td>${esc(x.name)}<div class="intro sm">${t('zuletzt','last used')}: ${x.last?new Date(x.last.t*1000).toLocaleString([], {dateStyle:'short',timeStyle:'short'})+' · '+esc(x.last.ip||''):t('noch nie','never')}</div></td><td><select onchange="devUser('${escq(x.id)}',this.value)">${opts(x.user)}</select></td><td style="text-align:right"><button class="b" onclick="delDev('${escq(x.id)}','${escq(x.name)}')">${t('Löschen','Delete')}</button></td></tr>`).join('')||`<tr><td class="mut">${t('Noch keine.','None yet.')}</td></tr>`}
const jpost=(m,b)=>({method:m,headers:{'Content-Type':'application/json'},body:JSON.stringify(b)});
$('padd').onclick=async()=>{try{await api('/api/admin/profiles',jpost('POST',{name:$('pname').value,pin:$('ppin').value}));
    $('pmsg').textContent=t('Angelegt: ','Created: ')+$('pname').value;$('pname').value=$('ppin').value='';loadProf()}catch(e){$('pmsg').innerHTML=`<span class="err">${esc(e.message)}</span>`}};
window.newPin=async(id,n)=>{const pin=prompt(t('Neue PIN für ','New PIN for ')+n+t(' (meldet alle Browser dieses Profils ab):',' (logs out all browsers of this profile):'));if(!pin)return;
  try{await api('/api/admin/profiles/'+id,jpost('PUT',{pin}));$('pmsg').textContent=t('PIN geändert.','PIN changed.')}catch(e){$('pmsg').innerHTML=`<span class="err">${esc(e.message)}</span>`}};
window.resetMfa=async(id,n)=>{if(!confirm(t('Zweiten Anmeldeschritt für „','Switch off the second login step for "')+n+t('“ ausschalten? Danach reicht wieder die PIN.','"? Then the PIN alone is enough again.')))return;
  try{await api('/api/admin/profiles/'+id+'/mfa',{method:'DELETE'});$('pmsg').textContent=t('Zurückgesetzt.','Reset.');loadProf()}catch(e){$('pmsg').innerHTML=`<span class="err">${esc(e.message)}</span>`}};
window.delProf=async(id,n)=>{if(!confirm(t('Profil „','Delete profile "')+n+t('“ mit seinem ganzen Gedächtnis und seinen Geräten löschen?','" with all its memory and devices?')))return;
  await api('/api/admin/profiles/'+id,{method:'DELETE'});loadProf()};
$('dadd').onclick=async()=>{try{const r=await (await api('/api/admin/devices',jpost('POST',{name:$('dname').value,user:$('duser').value}))).json();
    $('dmsg').innerHTML=`${t('Geräteschlüssel (wird nur jetzt angezeigt):','Device key (shown only now):')}<div class="token">${esc(r.token)}</div>`;$('dname').value='';loadProf()}
  catch(e){$('dmsg').innerHTML=`<span class="err">${esc(e.message)}</span>`}};
window.devUser=async(id,u)=>{await api('/api/admin/devices/'+id,jpost('PUT',{user:u}));loadProf()};
window.delDev=async(id,n)=>{if(!confirm(t('Gerät „','Delete device "')+n+t('“ löschen? Sein Schlüssel gilt dann nicht mehr.','"? Its key stops working.')))return;
  await api('/api/admin/devices/'+id,{method:'DELETE'});$('dmsg').textContent='';loadProf()};
const sendTyped=()=>{const x=$('chattext').value.trim();if(!x)return;$('chattext').value='';audioCtx();stopListening(true);stopAnswer();ask(x,null)};
$('chatsend').onclick=sendTyped;$('chattext').onkeydown=e=>{if(e.key==='Enter')sendTyped()};
document.addEventListener('keydown',e=>{if(e.code!=='Space'||!$('chat').classList.contains('on')||/INPUT|TEXTAREA|SELECT|BUTTON/.test(document.activeElement.tagName))return;
  e.preventDefault();$('talk').click()});
