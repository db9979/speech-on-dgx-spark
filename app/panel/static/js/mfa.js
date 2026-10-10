// Second login step (authenticator app) for the admin (Einstellungen → Sicherheit) and for a profile (Ich → Sicherheit).
// Setting up: QR code or key into the app, confirm with its code, write down the recovery codes (shown once).
const jbody=b=>({method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(b||{})});
const mfaMsg=(box,m,err)=>{const e=box.querySelector('.mfamsg');if(e)e.innerHTML=err?`<span class="err">${esc(m)}</span>`:esc(m)};
const mfaCodes=codes=>`<div class="token" style="display:grid;grid-template-columns:repeat(2,max-content);gap:4px 28px;margin:10px 0">${codes.map(c=>`<span>${esc(c)}</span>`).join('')}</div>`;
async function mfaShow(id,base){const box=$(id);if(!box)return;let s;
  try{s=await (await api(base)).json()}catch(e){box.innerHTML=`<span class="err">${esc(e.message)}</span>`;return}
  const admin=base==='/api/mfa';
  if(!s.on){
    if(!admin&&!s.allowed){box.innerHTML=`<div class="fh">${t('Vom Admin nicht freigegeben.','Not enabled by the admin.')}</div>`;return}
    box.innerHTML=`<div class="fh">${t('Aus. Mit einer Authenticator-App (z. B. Apple Passwörter, Google Authenticator, 1Password) fragt die Anmeldung zusätzlich einen sechsstelligen Code ab.','Off. With an authenticator app (e.g. Apple Passwords, Google Authenticator, 1Password) the login also asks for a six-digit code.')}</div>
      <div class="row" style="margin-top:6px"><button class="b" type="button" data-a="setup">${t('Einrichten','Set up')}</button><span class="mfamsg"></span></div>`}
  else box.innerHTML=`<div class="fh">${t('An','On')}${s.since?' '+t('seit','since')+' '+new Date(s.since*1000).toLocaleDateString():''}. ${t('Wiederherstellungscodes übrig:','Recovery codes left:')} <b>${s.codes_left}</b>${s.codes_left<3?' – '+t('bitte neue erzeugen.','please make new ones.'):''}</div>
      <div class="row" style="margin-top:6px;flex-wrap:wrap"><button class="b" type="button" data-a="recovery">${t('Neue Wiederherstellungscodes','New recovery codes')}</button>${admin?`<button class="b" type="button" data-a="forget">${t('Allen Browsern das Vertrauen entziehen','Forget trusted browsers')}</button>`:''}<button class="b" type="button" data-a="setup">${t('Neu einrichten','Set up again')}</button><button class="b" type="button" data-a="disable">${t('Ausschalten','Switch off')}</button><span class="mfamsg"></span></div>`;
  box.querySelectorAll('button[data-a]').forEach(b=>b.onclick=()=>mfaAct(box,base,b.dataset.a));
  if(s.on)mfaTrusted(box,base).then(()=>pkShow(box,base))}
// the trusted browsers one by one: short name, since when, last use, until when; "Entfernen" makes that one ask again
async function mfaTrusted(box,base){let d;try{d=await (await api(base+'/trusted')).json()}catch{return}
  const wrap=document.createElement('div');wrap.className='mfatrust';const lbl=document.createElement('label');lbl.textContent=t('Vertraute Browser','Trusted browsers');
  const ul=document.createElement('ul');ul.className='facts';const day=x=>new Date(x*1000).toLocaleDateString();
  for(const x of d.items){const li=document.createElement('li'),sp=document.createElement('span'),sm=document.createElement('small');
    sp.textContent=x.name+(x.this?t(' (dieser Browser)',' (this browser)'):'');sm.className='mut';
    sm.textContent=t('seit ','since ')+day(x.first)+' · '+t('zuletzt ','last used ')+day(x.last)+' · '+t('fragt wieder ab ','asks again from ')+day(x.until);
    sp.append(document.createElement('br'),sm);const b=document.createElement('button');b.type='button';b.className='b';b.textContent=t('Entfernen','Remove');
    b.onclick=async()=>{try{await api(base+'/trusted/'+encodeURIComponent(x.id),{method:'DELETE'})}catch(e){mfaMsg(box,e.message,true);return}mfaShow(box.id,base)};
    li.append(sp,b);ul.appendChild(li)}
  if(!d.items.length){const li=document.createElement('li');li.className='mut';li.textContent=t('Keiner. Beim Anmelden „Diesem Browser vertrauen“ ankreuzen, dann fragt er bis zu '+d.days+' Tage keinen Code.','None. Tick "Trust this browser" when signing in, then it asks for no code for up to '+d.days+' days.');ul.appendChild(li)}
  const fh=document.createElement('div');fh.className='fh';fh.textContent=t(`Ein vertrauter Browser fragt bei der Anmeldung ${d.days} Tage keinen Code, nach ${d.idle} Tagen ohne Nutzung wieder. Admin-Modus und wichtige Änderungen fragen trotzdem.`,`A trusted browser asks for no code at sign-in for ${d.days} days, after ${d.idle} days without use again. The admin mode and important changes still ask.`);
  wrap.append(lbl,ul,fh);box.appendChild(wrap)}
async function mfaAct(box,base,a){try{
  if(a==='setup'){const r=await (await api(base+'/setup',jbody())).json();
    box.innerHTML=`<div class="fh">${t('1. In der Authenticator-App einen neuen Eintrag anlegen und diesen QR-Code scannen','1. Add a new entry in the authenticator app and scan this QR code')}${/iPhone|iPad|Android/.test(navigator.userAgent)?t(' oder auf diesem Handy ',' or on this phone ')+`<a href="${esc(r.uri)}">${t('den Link öffnen','open the link')}</a>`:''}.</div>
      ${r.qr?`<div class="mfaqr" style="background:#fff;display:inline-block;padding:4px;border-radius:6px;margin:6px 0">${r.qr}</div>`:''}
      <div class="fh">${t('Oder den Schlüssel von Hand eingeben:','Or type the key by hand:')} <span class="token">${esc(r.secret)}</span></div>
      <label>${t('2. Code aus der App','2. Code from the app')}</label><div class="rowin"><input class="mfacode" inputmode="numeric" autocomplete="one-time-code" maxlength="6" style="max-width:140px"><button class="b p" type="button" data-a="enable">${t('Bestätigen','Confirm')}</button><button class="b" type="button" data-a="cancel">${t('Abbrechen','Cancel')}</button></div><span class="mfamsg"></span>`;
    box.querySelector('[data-a=enable]').onclick=()=>mfaAct(box,base,'enable');box.querySelector('[data-a=cancel]').onclick=()=>mfaShow(box.id,base);
    box.querySelector('.mfacode').onkeydown=e=>{if(e.key==='Enter')mfaAct(box,base,'enable')};box.querySelector('.mfacode').focus();return}
  if(a==='enable'){const r=await (await api(base+'/enable',jbody({code:box.querySelector('.mfacode').value}))).json();return mfaRecovery(box,base,r.recovery,true)}
  if(a==='recovery'){if(!confirm(t('Neue Wiederherstellungscodes erzeugen? Die alten gelten dann nicht mehr.','Make new recovery codes? The old ones stop working.')))return;
    const r=await (await api(base+'/recovery',jbody())).json();return mfaRecovery(box,base,r.recovery,false)}
  if(a==='forget'){if(!confirm(t('Alle vertrauten Browser müssen wieder einen Code eingeben, und alle anderen Admin-Anmeldungen enden. Fortfahren?','All trusted browsers have to enter a code again, and every other admin login ends. Go on?')))return;
    await api(base+'/forget',jbody());mfaMsg(box,t('Erledigt.','Done.'));return}
  if(a==='disable'){if(!confirm(t('Zweiten Anmeldeschritt ausschalten? Dann reicht wieder das Passwort bzw. die PIN.','Switch off the second login step? Then the password or PIN alone is enough again.')))return;
    await api(base+'/disable',jbody());mfaShow(box.id,base)}
  }catch(e){mfaMsg(box,/wrong code/.test(e.message)?t('Code falsch. Uhrzeit des Handys stimmt? Bitte den nächsten Code versuchen.','Wrong code. Is the phone\'s clock right? Please try the next code.'):e.message,true)}}
function mfaRecovery(box,base,codes,fresh){
  box.innerHTML=`<div class="fh"><b>${fresh?t('Eingerichtet.','Set up.')+' ':''}${t('Diese Wiederherstellungscodes jetzt aufschreiben oder im Passwort-Manager speichern.','Write these recovery codes down now or keep them in your password manager.')}</b> ${t('Jeder gilt einmal, falls das Handy weg ist, und wird nur jetzt angezeigt.','Each one works once if the phone is gone, and is shown only now.')}</div>${mfaCodes(codes)}
    <div class="row"><button class="b" type="button" data-a="copy">${t('Kopieren','Copy')}</button><button class="b p" type="button" data-a="done">${t('Aufgeschrieben','Written down')}</button></div>`;
  box.querySelector('[data-a=copy]').onclick=()=>navigator.clipboard&&navigator.clipboard.writeText(codes.join('\n'));
  box.querySelector('[data-a=done]').onclick=()=>mfaShow(box.id,base)}
window.mfaShow=mfaShow;
// Fewer codes (plan „Zweiten Anmeldeschritt seltener“, V01.0.289): the login's checkbox names the days and keeps the
// last choice in this browser; a right code counts CONFIRM_WINDOW (10 minutes) in this login, shown as a bar with "Beenden".
function trustUi(who){const d=who.trust_days||60;
  document.querySelectorAll('.trusttxt').forEach(e=>e.textContent=t(`Diesem Browser ${d} Tage vertrauen`,`Trust this browser for ${d} days`));
  let last=false;try{last=localStorage.getItem('trustlast')==='1'}catch{}
  ['logintrust','proftrust'].forEach(id=>{const c=$(id);if(!c)return;c.checked=last;c.onchange=()=>{try{localStorage.setItem('trustlast',c.checked?'1':'0')}catch{}}});
  confirmShow(who.confirm_until||0)}
let CONF_UNTIL=0,CONF_T=null;
function confirmShow(until){CONF_UNTIL=until||0;let bar=$('confbar');
  if(CONF_UNTIL*1000<=Date.now()){if(bar)bar.remove();clearInterval(CONF_T);CONF_T=null;return}
  if(!bar){bar=document.createElement('div');bar.id='confbar';bar.className='updbanner';const sp=document.createElement('span');sp.id='conftext';
    const end=document.createElement('button');end.type='button';end.className='b';end.textContent=t('Beenden','End');
    end.onclick=async()=>{try{await fetch('/api/confirm/end',{method:'POST'})}catch{}confirmShow(0)};
    bar.append(sp,end);$('updbanner').before(bar)}
  const tick=()=>{const left=Math.ceil((CONF_UNTIL*1000-Date.now())/60000);if(left<=0)return confirmShow(0);
    $('conftext').textContent=t(`Code bestätigt: wichtige Änderungen noch ${left} min ohne neuen Code.`,`Code confirmed: important changes need no new code for ${left} more min.`)};
  tick();clearInterval(CONF_T);CONF_T=setInterval(tick,20e3)}
async function confirmRefresh(){try{const w=await (await fetch('/api/whoami',{cache:'no-store'})).json();confirmShow(w.confirm_until||0)}catch{}}
window.trustUi=trustUi;window.confirmShow=confirmShow;window.confirmRefresh=confirmRefresh;
// Passkeys (Face ID, Touch ID, Windows Hello; passkey.py, V01.0.295): wherever a code is asked, the browser may sign
// the panel's challenge instead. Only over the address with a name (https), never over an IP address.
const PK=window.PublicKeyCredential&&navigator.credentials?{}:null;
const b64d=s=>Uint8Array.from(atob(String(s).replace(/-/g,'+').replace(/_/g,'/')+'==='.slice((String(s).length+3)%4)),c=>c.charCodeAt(0));
const b64e=b=>{const u=new Uint8Array(b);let s='';for(let i=0;i<u.length;i++)s+=String.fromCharCode(u[i]);return btoa(s).replace(/\+/g,'-').replace(/\//g,'_').replace(/=+$/,'')};
async function pkGet(o){const pk=o.publicKey;
  const c=await navigator.credentials.get({publicKey:{challenge:b64d(pk.challenge),rpId:pk.rpId,userVerification:pk.userVerification,timeout:pk.timeout,
    allowCredentials:(pk.allowCredentials||[]).map(x=>({type:x.type,id:b64d(x.id),transports:x.transports}))}});
  const r=c.response,out={clientDataJSON:b64e(r.clientDataJSON),authenticatorData:b64e(r.authenticatorData),signature:b64e(r.signature)};
  if(r.userHandle)out.userHandle=b64e(r.userHandle);
  return {id:c.id,rawId:b64e(c.rawId),type:c.type,response:out,clientExtensionResults:{}}}
async function pkCreate(o){const pk=o.publicKey;
  const c=await navigator.credentials.create({publicKey:{rp:pk.rp,user:Object.assign({},pk.user,{id:b64d(pk.user.id)}),challenge:b64d(pk.challenge),
    pubKeyCredParams:pk.pubKeyCredParams,timeout:pk.timeout,attestation:pk.attestation||'none',authenticatorSelection:pk.authenticatorSelection,
    excludeCredentials:(pk.excludeCredentials||[]).map(x=>({type:x.type,id:b64d(x.id),transports:x.transports}))}});
  const r=c.response;
  return {id:c.id,rawId:b64e(c.rawId),type:c.type,clientExtensionResults:{},
    response:{clientDataJSON:b64e(r.clientDataJSON),attestationObject:b64e(r.attestationObject),transports:r.getTransports?r.getTransports():[]}}}
// "428 code required" with a passkey challenge: a small window with "Mit Passkey" (a tap, which the browser needs),
// "Code eingeben" (the authenticator app or a recovery code) and "Abbrechen". Resolves {pk} / {code} / null.
function confirmAsk(wrong,opt){
  const ask=()=>{const c=prompt((wrong?t('Code falsch. ','Wrong code. '):'')+t('Bitte den aktuellen Code aus deiner Authenticator-App eingeben (oder einen Wiederherstellungscode):','Please enter the current code from your authenticator app (or a recovery code):'));return c&&c.trim()?{code:c.trim()}:null};
  if(!opt||!PK)return Promise.resolve(ask());
  return new Promise(done=>{const m=document.createElement('div');m.className='modal';m.id='pkmodal';const card=document.createElement('div');card.className='card modalcard';
    const h=document.createElement('h3');h.textContent=t('Bestätigen','Confirm');const p=document.createElement('div');p.className='fh';
    p.textContent=(wrong?t('Das hat nicht geklappt. ','That did not work. '):'')+t('Mit deinem Passkey (Face ID, Touch ID, Windows Hello) oder dem Code aus der Authenticator-App.','With your passkey (Face ID, Touch ID, Windows Hello) or the code from the authenticator app.');
    const row=document.createElement('div');row.className='row';row.style.marginTop='10px';row.style.flexWrap='wrap';const msg=document.createElement('div');msg.className='fh';
    const mk=(txt,cls,fn)=>{const b=document.createElement('button');b.type='button';b.className='b'+(cls?' '+cls:'');b.textContent=txt;b.onclick=fn;row.appendChild(b);return b};
    const close=v=>{m.remove();done(v)};
    mk(t('Mit Passkey','With passkey'),'p',async()=>{try{const a=await pkGet(opt.options);close({pk:b64e(new TextEncoder().encode(JSON.stringify({sid:opt.sid,response:a})))})}
      catch(e){msg.textContent=t('Passkey abgebrochen oder nicht gefunden. Code geht auch.','Passkey cancelled or not found. A code works too.')}});
    mk(t('Code eingeben','Enter code'),'',()=>{m.remove();done(ask())});mk(t('Abbrechen','Cancel'),'',()=>close(null));
    card.append(h,p,row,msg);m.appendChild(card);document.body.appendChild(m);row.firstChild.focus()})}
// the login forms: after the right password or PIN the answer may carry a passkey challenge
function pkLoginOffer(box,opt,send){let b=box.querySelector('.pklogin');if(!opt||!PK){if(b)b.remove();return}
  if(!b){b=document.createElement('button');b.type='button';b.className='b p pklogin';b.style.marginTop='8px';b.textContent=t('Mit Passkey anmelden','Sign in with passkey');box.appendChild(b)}
  b.onclick=async()=>{try{const a=await pkGet(opt.options);await send({sid:opt.sid,response:a})}catch(e){send(null,e)}}}
// Einstellungen → Sicherheit and Ich → Sicherheit: the person's passkeys, add one (fresh code), remove one
async function pkShow(box,base){let d;try{d=await (await api(base+'/passkeys')).json()}catch{return}
  const wrap=document.createElement('div');wrap.className='pkwrap';const lbl=document.createElement('label');lbl.textContent=t('Passkeys','Passkeys');
  const ul=document.createElement('ul');ul.className='facts';const day=x=>x?new Date(x*1000).toLocaleDateString():t('noch nie','never');
  for(const x of d.items){const li=document.createElement('li'),sp=document.createElement('span'),sm=document.createElement('small');
    sp.textContent=x.name;sm.className='mut';sm.textContent=x.rp+' · '+t('seit ','since ')+day(x.added)+' · '+t('zuletzt ','last used ')+day(x.last);
    sp.append(document.createElement('br'),sm);const b=document.createElement('button');b.type='button';b.className='b';b.textContent=t('Entfernen','Remove');
    b.onclick=async()=>{if(!confirm(t('Passkey „','Remove passkey "')+x.name+t('“ entfernen?','"?')))return;try{await api(base+'/passkeys/'+encodeURIComponent(x.id),{method:'DELETE'})}catch(e){mfaMsg(box,e.message,true);return}mfaShow(box.id,base)};
    li.append(sp,b);ul.appendChild(li)}
  if(!d.items.length){const li=document.createElement('li');li.className='mut';li.textContent=t('Noch keiner.','None yet.');ul.appendChild(li)}
  const fh=document.createElement('div');fh.className='fh';
  fh.textContent=!d.ready?t('Auf dem Spark fehlt die Passkey-Bibliothek (kommt mit dem nächsten Update).','The passkey library is missing on the Spark (comes with the next update).')
    :!d.host?t('Passkeys gehen nur über die Adresse mit Namen (https), nicht über eine IP-Adresse.','Passkeys only work over the address with a name (https), not over an IP address.')
    :!PK?t('Dieser Browser kann keine Passkeys.','This browser cannot do passkeys.')
    :t('Statt den Code abzutippen: Face ID, Touch ID oder Windows Hello. Sicherer als der Code, weil keine fremde Seite ihn abfangen kann. Der Code aus der App bleibt als Rückfall.','Instead of typing the code: Face ID, Touch ID or Windows Hello. Safer than the code, because no other page can catch it. The app code stays as the way back.');
  wrap.append(lbl,ul,fh);
  if(d.ready&&d.host&&PK&&d.items.length<d.max){const row=document.createElement('div');row.className='row';row.style.flexWrap='wrap';
    const name=document.createElement('input');name.placeholder=t('Name, z. B. iPhone','Name, e.g. iPhone');name.maxLength=60;name.style.maxWidth='200px';
    const add=document.createElement('button');add.type='button';add.className='b';add.textContent=t('Passkey hinzufügen','Add passkey');
    add.onclick=async()=>{let o;try{o=await (await api(base+'/passkeys/begin',{method:'POST'})).json()}catch(e){mfaMsg(box,e.message,true);return}
      // the browser needs a tap of its own for creating the passkey
      add.textContent=t('Jetzt anlegen','Create now');add.className='b p';
      add.onclick=async()=>{try{const a=await pkCreate(o.options);
        await api(base+'/passkeys/finish',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({sid:o.sid,response:a,name:name.value.trim()})});mfaShow(box.id,base)}
        catch(e){mfaMsg(box,/NotAllowed|abort/i.test(e.name+e.message)?t('Abgebrochen.','Cancelled.'):e.message,true)}}};
    row.append(name,add);wrap.appendChild(row)}
  box.appendChild(wrap)}
window.pkLoginOffer=pkLoginOffer;window.confirmAsk=confirmAsk;
