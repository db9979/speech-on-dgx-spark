// Notaus (notaus.py, plan plaene/notaus.md): the red button, the band on every page, Zustand → "Was der Notaus
// gerade abhält" and, in stage 3 or from outside, the whole page. Triggering goes only up and needs no code;
// lifting is the admin's, in the browser at home, with a fresh code (the 428 of api() asks for it).
const NA={s:{level:0},pick:2,timer:null};
const NA_STAGES=[[1,t('Außen zu','Outside closed'),t('Kein Zugriff aus dem Internet (Proxy, MCP von außen, Telegram). Der Spark erreicht nichts im Internet. Das Heimnetz läuft weiter.','No access from the internet (proxy, MCP from outside, Telegram). The Spark reaches nothing on the internet. The home network goes on.')],
  [2,t('Hände weg','Hands off'),t('Dazu keine Aktionen: Home Assistant, Mail, Nachrichten, Termine, Listen, reMarkable. Aufträge angehalten. Spark antwortet nur noch aus seinem Wissen.','Plus no actions: smart home, mail, messages, appointments, lists, reMarkable. Jobs held. The Spark only answers from what it knows.')],
  [3,t('Alles still','All quiet'),t('Dazu kein Gespräch, kein Zuhören, Lautsprecher stumm. Das Panel zeigt nur noch diese Seite.','Plus no conversation, no listening, speakers silent. The panel shows only this page.')]];
const naName=l=>(NA_STAGES.find(x=>x[0]===l)||[0,''])[1];
const naChan=c=>({panel:t('das Panel','the panel'),app:t('die iPhone-App','the iPhone app'),android:t('die Android-App','the Android app'),telegram:'Telegram',sprache:t('Sprache','voice'),
  esp32:t('einen Lautsprecher','a speaker'),ha:'Home Assistant',pebble:'Pebble',waechter:t('den Wächter','the guard')}[c]||c||'');
function naWhen(ts){if(!ts)return '';const d=new Date(ts*1000),now=new Date();
  const hm=d.toLocaleTimeString(L==='en'?'en-GB':'de-DE',{hour:'2-digit',minute:'2-digit'});
  return d.toDateString()===now.toDateString()?hm:d.toLocaleDateString(L==='en'?'en-GB':'de-DE',{day:'numeric',month:'numeric'})+' '+hm}
function naLine(s){return [t('seit ','since ')+naWhen(s.since),s.by?t('von ','by ')+s.by:'',s.channel?t('über ','via ')+naChan(s.channel):''].filter(Boolean).join(' · ')
  +(s.reason?' · „'+s.reason+'“':'')}
async function notausLoad(){try{const r=await fetch('/api/notaus',{cache:'no-store'});if(r.status===429)setTimeout(notausLoad,5000);if(!r.ok)return;NA.s=await r.json();naRender()}catch{}}
window.notausLoad=notausLoad;
function naRender(){const s=NA.s,l=s.level||0,may=!!s.may,lift=s.lift||'';
  const btn=$('notausbtn');btn.hidden=!may;btn.querySelector('span').textContent=l?t('Stufe ändern','Change stage'):t('Notaus','Kill switch');
  // only admins see the band, who and why (Dominik 2026-10-10: the Notaus is the admins' matter);
  // a profile whose own Notaus is on sees a band of its own
  const mi=s.mine||{},own=!!mi.on&&!(l&&may);
  const band=$('notausband');band.hidden=!((l&&may)||own);document.body.classList.toggle('notaus',!!((l&&may)||own));
  if(own){$('nbtitle').textContent=t('MEIN NOTAUS IST AN','MY KILL SWITCH IS ON');
    $('nbtext').textContent=t('In deinem Namen passiert nichts, andere Anmeldungen und Geräte sind gesperrt. Lesen und Fragen gehen weiter.','Nothing happens in your name, other logins and devices are locked. Reading and asking go on.')+(mi.since?' · '+t('seit ','since ')+naWhen(mi.since):'');
    $('nbup').hidden=true;$('nblift').hidden=!mi.lift}
  if(l&&may){$('nbtitle').textContent=(t('NOTAUS · STUFE ','KILL SWITCH · STAGE ')+l+' · '+naName(l)).toUpperCase();
    $('nbtext').textContent=s.since?naLine(s):t('Nicht alles ist erreichbar, bis ein Admin ihn aufhebt.','Not everything works until an admin lifts it.');
    $('nbup').hidden=!(may&&l<3);$('nblift').hidden=!lift}
  // the whole page: stage 3, or any stage from outside the home network
  const all=l>=3||(l&&s.outside);$('notausall').hidden=!all;
  if(all&&!may){$('natitle').textContent=t('Der Spark ist gerade angehalten','The Spark is stopped right now');
    $('natext').textContent=t('Ein Admin kümmert sich darum. Bis dahin geht hier nichts.','An admin is looking after it. Until then nothing works here.');
    $('nameta').textContent='';$('naup').hidden=true;$('nalift').hidden=true;$('nalogin').hidden=!!s.outside}
  else if(all){$('natitle').textContent=t('Notaus Stufe ','Kill switch stage ')+l+': '+naName(l);
    $('natext').textContent=s.outside?t('Von außen ist der Spark gerade gesperrt. Im Heimnetz geht, was die Stufe erlaubt.','The Spark is closed from outside right now. At home, what the stage allows still works.')
      :t('Der Spark ist angehalten: kein Gespräch, kein Zuhören, keine Aktionen.','The Spark is stopped: no conversation, no listening, no actions.');
    $('nameta').textContent=s.since?naLine(s):'';
    $('naup').hidden=!(l<3);$('nalift').hidden=!lift;$('nalogin').hidden=true}
  naMine();
  const card=$('znotaus');card.hidden=!(l&&s.kinds);
  if(l&&s.kinds){$('znsince').textContent=naLine(s);
    $('znrows').innerHTML=s.kinds.map(k=>{const held=l>=k.from,n=(s.counts||{})[k.k]||0;
      return `<div class="znrow"><span>${esc(L==='en'?k.en:k.de)}</span><span class="pill ${held?'bad':'ok'}">${held?t('gesperrt','held off'):t('läuft','running')}</span><span class="n">${held?n:'–'}</span></div>`}).join('')}
  if(typeof renderManage==='function'&&$('apmanage')&&$('apmanage').classList.contains('on'))try{renderManage()}catch{}}
// triggering: three stages, only higher than now
function naOpen(){const l=NA.s.level||0;NA.pick=Math.max(2,l+1);if(NA.pick>3)return;
  $('nmhead').lastChild.textContent=l?t('Notaus erhöhen','Raise the kill switch'):t('Notaus auslösen','Trigger the kill switch');
  $('nmstages').innerHTML=NA_STAGES.map(([n,name,what])=>`<button type="button" class="nastage${n===NA.pick?' on':''}" data-n="${n}"${n<=l?' disabled':''}>
    <small>${t('Stufe','Stage')} ${n}${n===2?' · '+t('empfohlen','recommended'):''}</small><b>${esc(name)}</b><span>${esc(what)}</span></button>`).join('');
  $('nmreason').value='';$('nmmsg').textContent='';naGoText();$('notausmodal').style.display='grid'}
function naGoText(){$('nmgo').textContent=t('Stufe ','Stage ')+NA.pick+t(' jetzt auslösen',' now')}
$('nmstages').addEventListener('click',e=>{const b=e.target.closest('.nastage');if(!b||b.disabled)return;NA.pick=+b.dataset.n;
  $('nmstages').querySelectorAll('.nastage').forEach(x=>x.classList.toggle('on',x===b));naGoText()});
$('nmcancel').addEventListener('click',()=>$('notausmodal').style.display='none');
$('nmgo').addEventListener('click',async()=>{$('nmgo').disabled=true;$('nmmsg').textContent='';
  try{const r=await api('/api/notaus',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({level:NA.pick,reason:$('nmreason').value})});
    NA.s=await r.json();$('notausmodal').style.display='none';naRender()}catch(e){$('nmmsg').textContent=e.message}finally{$('nmgo').disabled=false}});
// lifting
function naLiftOpen(){const l=NA.s.level||0;$('noto1').hidden=l<2;$('noresume').hidden=l<2;$('noresumebox').checked=false;
  document.querySelector('input[name=noto][value="0"]').checked=true;$('nopwbox').hidden=NA.s.lift!=='password';$('nopw').value='';$('nomsg').textContent='';
  $('notausoff').style.display='grid'}
$('nocancel').addEventListener('click',()=>$('notausoff').style.display='none');
$('nogo').addEventListener('click',async()=>{$('nogo').disabled=true;$('nomsg').textContent='';
  const to=+(document.querySelector('input[name=noto]:checked')||{value:0}).value;
  try{const r=await api('/api/admin/notaus/off',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({to,resume:$('noresumebox').checked,password:NA.s.lift==='password'?$('nopw').value:undefined})});
    NA.s=await r.json();$('notausoff').style.display='none';naRender();if(!NA.s.level)location.reload()}catch(e){$('nomsg').textContent=e.message}finally{$('nogo').disabled=false}});
for(const id of ['notausbtn','nbup','naup'])$(id).addEventListener('click',naOpen);
$('nalift').addEventListener('click',naLiftOpen);
$('nblift').addEventListener('click',()=>{const mi=NA.s.mine||{};if(mi.on&&!((NA.s.level||0)&&NA.s.may)){if(typeof openMe==='function')openMe('secbox')}else naLiftOpen()});
// Mein Notaus (notaus.py, 3b): Ich → Sicherheit for the profile, and Zustand's list for the admins
function naMine(){const s=NA.s,mi=s.mine||{};
  if($('mynabox')){$('mynabox').hidden=!('mine' in s);$('mynaon').hidden=!!mi.on;$('mynaoff').hidden=!(mi.on&&mi.lift);
    $('mynamsg').textContent=mi.on?(t('Mein Notaus ist an','My kill switch is on')+(mi.since?' · '+t('seit ','since ')+naWhen(mi.since):'')+(mi.lift?'':' · '+t('Aufheben nur im Browser mit PIN.','Lift only in the browser with your PIN.'))):''}
  const L2=s.mine_list||[],box=$('znmine');if(!box)return;box.hidden=!L2.length;
  $('znmpwbox').hidden=!(L2.length&&s.lift==='password');
  $('znmrows').innerHTML=L2.map(x=>`<div class="znrow"><span>${esc(x.name)}</span><span class="mut">${x.since?esc(t('seit ','since ')+naWhen(x.since)):''}</span>${s.lift?`<button class="b" type="button" data-mineoff="${esc(x.uid)}">${esc(t('Aufheben','Lift'))}</button>`:''}</div>`).join('')}
$('mynaon').addEventListener('click',async()=>{
  if(!confirm(t('Mein Notaus auslösen? Alle anderen Anmeldungen und Geräte deines Profils werden gesperrt, und in deinem Namen passiert nichts mehr, bis du ihn hier mit deiner PIN aufhebst.','Trigger my kill switch? All other logins and devices of your profile are locked and nothing happens in your name until you lift it here with your PIN.')))return;
  if(typeof whoLocal==='function')whoLocal();
  $('mynaon').disabled=true;$('mynamsg').textContent='';
  try{const r=await api('/api/notaus/mine',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'});NA.s=await r.json();naRender()}
  catch(e){$('mynamsg').textContent=e.message}finally{$('mynaon').disabled=false}});
$('mynago').addEventListener('click',async()=>{if(typeof whoLocal==='function')whoLocal();$('mynago').disabled=true;$('mynamsg').textContent='';
  try{const r=await api('/api/notaus/mine/off',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({pin:$('mynapin').value})});
    $('mynapin').value='';NA.s=await r.json();naRender()}catch(e){$('mynamsg').textContent=e.message}finally{$('mynago').disabled=false}});
$('znmrows').addEventListener('click',async e=>{const b=e.target.closest('[data-mineoff]');if(!b)return;b.disabled=true;$('znmmsg').textContent='';
  try{const r=await api('/api/admin/notaus/mine/off',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({uid:b.dataset.mineoff,password:NA.s.lift==='password'?$('znmpw').value:undefined})});
    NA.s=await r.json();$('znmpw').value='';naRender()}catch(e2){$('znmmsg').textContent=e2.message;b.disabled=false}});
$('nalogin').addEventListener('click',()=>{if(window.showLogin)showLogin()});
// the stage of other devices: looked at every 15 seconds and when the page comes back
notausLoad();NA.timer=setInterval(notausLoad,15000);
document.addEventListener('visibilitychange',()=>{if(document.visibilityState==='visible')notausLoad()});

// Home Assistant keys (notaus.py key_new): only the admin, made with a fresh code, shown once with a ready snippet
async function naKeys(){const box=$('nakeys');if(!box||!NA.s.may)return;
  try{const r=await fetch('/api/admin/notaus/keys',{cache:'no-store'});if(!r.ok){$('nakeysec').hidden=true;return}const d=await r.json();
    $('nakeysec').hidden=false;
    box.innerHTML=d.keys.length?d.keys.map(k=>`<li><span>${esc(k.name)}</span><span class="mut">${esc(t('angelegt ','made ')+naWhen(k.created))}${k.used?esc(' · '+t('zuletzt ','last ')+naWhen(k.used)):''}</span><button class="b" type="button" data-nakeydel="${esc(k.id)}">${esc(t('Löschen','Delete'))}</button></li>`).join('')
      :`<li class="mut">${esc(t('Noch kein Schlüssel.','No key yet.'))}</li>`;
    $('nakeymake').disabled=d.keys.length>=d.max}catch{}}
function naYaml(key){const o=location.origin;
  return `rest_command:\n  spark_notaus:\n    url: "${o}/api/notaus/ha"\n    method: POST\n    headers:\n      Authorization: "Bearer ${key}"\n    content_type: "application/json"\n    payload: '{"level": 2}'\n\nsensor:\n  - platform: rest\n    name: Spark Notaus\n    resource: "${o}/api/notaus"\n    value_template: "{{ value_json.level }}"\n    scan_interval: 30\n`}
$('nakeymake').addEventListener('click',async()=>{$('nakeymake').disabled=true;$('nakeymsg').textContent='';
  try{const r=await api('/api/admin/notaus/keys',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name:$('nakeyname').value})});
    const d=await r.json();$('nakeyyaml').textContent=naYaml(d.token);$('nakeynew').hidden=false;$('nakeyname').value='';naKeys()}
  catch(e){$('nakeymsg').textContent=e.message}finally{$('nakeymake').disabled=false}});
$('nakeys').addEventListener('click',async e=>{const b=e.target.closest('[data-nakeydel]');if(!b)return;b.disabled=true;
  try{await api('/api/admin/notaus/keys/'+encodeURIComponent(b.dataset.nakeydel),{method:'DELETE'});$('nakeynew').hidden=true;naKeys()}catch(e2){$('nakeymsg').textContent=e2.message;b.disabled=false}});
setTimeout(naKeys,1500);
