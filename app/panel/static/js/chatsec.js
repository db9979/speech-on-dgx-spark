// Private Chats (chatsec.py, plan messenger.md Schritt C): chats for two that only the two people's devices can read.
// Every device makes its own key (ECDH P-256) here in the browser; the private part is a non-extractable WebCrypto key
// in IndexedDB and never leaves this browser. A message is a box: the text (and an attachment's file key) under a fresh
// AES-GCM key, that key wrapped once for every current device of both people (HKDF over ECDH, info
// "spark-e2e-v1|chat|from|to"). Photos, files and voice go as iv + AES-GCM under their own file key; photos are drawn
// anew first (no place or camera data, the Spark cannot do that here). The Spark keeps only boxes and blobs.
// The Sicherheitsnummer under ⓘ: SHA-512 over both people's current public keys, 12 blocks of 5 digits; compared
// once, it is remembered on this device until a key changes. Everything that comes out of a box is data (esc, text).
// A new device of someone who has one already waits for the history (Wahl 2): an older device shows the new device's
// code (the same as on the new one: made from its public key, so a key the Spark slipped in shows another code), and
// "Übertragen" wraps each content key once more for the new device ({"b": this device} in the box).
const CS={db:null,me:null,own:[],keys:{},open:new Map(),urls:new Map()};
const csEnc=s=>new TextEncoder().encode(s);
const csRand=n=>crypto.getRandomValues(new Uint8Array(n));
function csB64(u8){let s='';for(let i=0;i<u8.length;i+=32768)s+=String.fromCharCode.apply(null,u8.subarray(i,i+32768));return btoa(s)}
const csUn=s=>Uint8Array.from(atob(String(s||'')),c=>c.charCodeAt(0));
const csOk=()=>!!(window.isSecureContext&&window.crypto&&crypto.subtle&&window.indexedDB);
const csKind=()=>/SparkAndroid\//.test(navigator.userAgent)?'android':'browser';
const csNoHttps=()=>t('Private Chats brauchen eine Seite über https (der Browser rechnet die Schlüssel nur dort).','Private chats need a page over https (the browser only does the key maths there).');

// ---------------------------------------------------------------- this device's key (IndexedDB, per profile)
function csDb(){if(!CS.db)CS.db=new Promise((ok,no)=>{const r=indexedDB.open('spark-chatsec',1);
  r.onupgradeneeded=()=>r.result.createObjectStore('keys');r.onsuccess=()=>ok(r.result);r.onerror=()=>no(r.error)});return CS.db}
async function csStore(mode,fn){const db=await csDb();return new Promise((ok,no)=>{const q=fn(db.transaction('keys',mode).objectStore('keys'));
  q.onsuccess=()=>ok(q.result);q.onerror=()=>no(q.error)})}
const csSlot=()=>'p:'+cxMe();
async function csOwn(){const r=await cxApi('/api/chats/keys');CS.own=r.keys||[];return CS.own}
// the device's record when the Spark still lists it; make: a new key (like a new device: the second step's code)
async function csDevice(make){if(!csOk())throw new Error(csNoHttps());
  let rec=null;try{rec=await csStore('readonly',s=>s.get(csSlot()))}catch{}
  const own=await csOwn();
  if(rec&&own.some(k=>k.id===rec.kid)){CS.me=rec;return rec}
  if(rec){try{await csStore('readwrite',s=>s.delete(csSlot()))}catch{}}   // removed on another device: this one starts anew
  CS.me=null;if(!make)return null;
  const kp=await crypto.subtle.generateKey({name:'ECDH',namedCurve:'P-256'},false,['deriveBits']);
  const pub=csB64(new Uint8Array(await crypto.subtle.exportKey('raw',kp.publicKey)));
  const r=await cxApi('/api/chats/keys',{pub,kind:csKind()});
  rec={kid:r.id,priv:kp.privateKey,pub};await csStore('readwrite',s=>s.put(rec,csSlot()));CS.me=rec;CS.own=r.keys||[];return rec}
async function csKeys(cid,fresh){if(fresh||!CS.keys[cid])CS.keys[cid]=(await cxApi('/api/chats/keys?id='+encodeURIComponent(cid))).keys||[];return CS.keys[cid]}

// ---------------------------------------------------------------- boxes
async function csWrap(pub,cid,from,to,salt){
  const peer=await crypto.subtle.importKey('raw',csUn(pub),{name:'ECDH',namedCurve:'P-256'},false,[]);
  const bits=await crypto.subtle.deriveBits({name:'ECDH',public:peer},CS.me.priv,256);
  const hk=await crypto.subtle.importKey('raw',bits,'HKDF',false,['deriveKey']);
  return crypto.subtle.deriveKey({name:'HKDF',hash:'SHA-256',salt,info:csEnc(`spark-e2e-v1|${cid}|${from}|${to}`)},hk,{name:'AES-GCM',length:256},false,['encrypt','decrypt'])}
const csAes=(raw,use)=>crypto.subtle.importKey('raw',raw,'AES-GCM',false,[use]);
async function csBox(cid,payload,keys){const K=csRand(32),iv=csRand(12),me=CS.me;
  const ct=await crypto.subtle.encrypt({name:'AES-GCM',iv,additionalData:csEnc(cid)},await csAes(K,'encrypt'),csEnc(JSON.stringify(payload)));
  const out={v:1,f:me.kid,iv:csB64(iv),ct:csB64(new Uint8Array(ct)),k:{}};
  for(const x of keys){if(x.gone)continue;const s=csRand(16),wi=csRand(12);
    const w=await crypto.subtle.encrypt({name:'AES-GCM',iv:wi},await csWrap(x.pub,cid,me.kid,x.id,s),K);
    out.k[x.id]={s:csB64(s),i:csB64(wi),w:csB64(new Uint8Array(w))}}
  return out}
// null: not for this device (sent before it was added) or not from the person it says
async function csKeyOf(cid,box,keys,w){const snd=keys.find(x=>x.id===box.f);if(!snd)return null;let by=snd;
  if(w.b){const me=keys.find(x=>x.id===CS.me.kid);by=keys.find(x=>x.id===w.b);if(!by||!me||by.uid!==me.uid)return null}   // only an own older device
  return {snd,K:await crypto.subtle.decrypt({name:'AES-GCM',iv:csUn(w.i)},await csWrap(by.pub,cid,by.id,CS.me.kid,csUn(w.s)),csUn(w.w))}}
async function csUnbox(cid,from,box,keys){const w=box&&box.k&&box.k[CS.me.kid];if(!w)return null;
  const o=await csKeyOf(cid,box,keys,w);if(!o||o.snd.uid!==from)return null;const K=o.K;
  const pt=await crypto.subtle.decrypt({name:'AES-GCM',iv:csUn(box.iv),additionalData:csEnc(cid)},await csAes(K,'decrypt'),csUn(box.ct));
  return csClean(JSON.parse(new TextDecoder().decode(pt)))}
// what came out of a box is data from outside: only the known fields, as plain values
function csClean(p){if(!p||typeof p!=='object')return null;const o={t:String(p.t||'').slice(0,4000)},a=p.a;
  if(a&&typeof a==='object'&&['photo','file','voice'].includes(a.kind)&&typeof a.k==='string'){
    o.a={kind:a.kind,k:a.k,name:String(a.name||'').slice(0,200),mime:String(a.mime||'').slice(0,100),size:+a.size||0,secs:+a.secs||0,w:+a.w||0,h:+a.h||0}}
  return o}

// ---------------------------------------------------------------- a private chat as chats.js shows it
// chats.js calls this before it draws: every box becomes text (and an attachment) for this device
window.csPrepare=async(d,cid)=>{if(!d||!d.private)return;d.cs='';
  if(!csOk()){d.cs='https';csLock(d);return}
  try{if(!CS.me||!CS.own.some(k=>k.id===CS.me.kid))await csDevice(false)}catch(e){d.cs='err';csLock(d);return}
  if(!CS.me){d.cs='need';csLock(d);return}
  let keys;try{keys=await csKeys(cid);
    if(d.items.some(x=>x.kind==='box'&&x.box&&!keys.some(k=>k.id===x.box.f)))keys=await csKeys(cid,true)}catch{csLock(d);return}
  if(d.items.some(x=>x.kind==='sys'&&(x.sys==='newkey'||x.sys==='keygone')&&x.t>(CS.keys[cid+':t']||0))){keys=await csKeys(cid,true);CS.keys[cid+':t']=Date.now()/1000}
  for(const x of d.items){if(x.kind!=='box'||x.gone)continue;const ck=cid+'|'+x.id;let p=CS.open.get(ck);
    if(!p){try{p=await csUnbox(cid,x.from,x.box,keys)}catch{p=null}if(p)CS.open.set(ck,p)}   // not yet: maybe the history comes
    csShow(x,p)}
  for(const x of d.items)if(x.reply&&!x.reply.gone){const p=CS.open.get(cid+'|'+x.reply.id);
    if(p){x.reply.text=p.t;x.reply.kind=p.a?p.a.kind:'text'}else if(x.reply.kind==='box')x.reply.text=t('Private Nachricht','Private message')}};
function csShow(x,p){x.box=null;
  if(!p){x.kind='text';x.locked=true;x.text=t('Auf diesem Gerät nicht lesbar (vor seinem Eintragen geschickt).','Not readable on this device (sent before it was added).');return}
  x.text=p.t;if(p.a){x.kind=p.a.kind;x.att=p.a;x.media={name:p.a.name,size:p.a.size,secs:p.a.secs,w:p.a.w,h:p.a.h,ext:(p.a.name.split('.').pop()||'')}}else x.kind='text'}
function csLock(d){d.can_send=false;d.why=d.cs==='https'?csNoHttps():d.cs==='need'?t('Dieses Gerät hat noch keinen Schlüssel für private Chats.','This device has no key for private chats yet.')
  :t('Die Schlüssel für private Chats sind gerade nicht zu holen.','The keys for private chats cannot be fetched right now.');
  for(const x of d.items)if(x.kind==='box'&&!x.gone)csShow(x,null)}
// after drawing: the line to add this device, and the attachments decrypted into blob addresses
window.csAfter=(log,d)=>{if(!d||!d.private)return;
  const mine=CS.me&&CS.own.find(k=>k.id===CS.me.kid);
  if(mine&&mine.want&&d.items.some(x=>x.locked)){const n=document.createElement('div');n.className='cx-sys';
    n.innerHTML=`${esc(t('Ältere Nachrichten liegen auf deinen anderen Geräten. Öffne Chats auf einem davon und tippe „Übertragen“, wenn dort derselbe Code steht:','Older messages are on your other devices. Open Chats on one of them and tap "Transfer" when it shows the same code:'))} <b class="cx-code" data-cscode="${esc(mine.pub)}">…</b>`;
    log.prepend(n);csCode(mine.pub).then(c=>{const b=n.querySelector('.cx-code');if(b)b.textContent=c})}
  if(d.cs==='need'){const n=document.createElement('div');n.className='cx-sys';
    n.innerHTML=`${esc(t('Damit du hier lesen und schreiben kannst, bekommt dieses Gerät einen eigenen Schlüssel.','To read and write here, this device gets its own key.'))} <button type="button" class="b p" data-cxs="dev">${esc(t('Gerät eintragen','Add this device'))}</button>`;log.prepend(n)}
  log.querySelectorAll('[data-cse]').forEach(el=>csMedia(el,d))};
window.csMediaHtml=x=>{const a=x.att,m=x.media||{};
  if(a.kind==='photo'){const w=+m.w||4,h=+m.h||3,f=Math.min(1,240/Math.max(w,h));
    return `<button type="button" class="cx-ph" data-cxa="photo" data-mid="${esc(x.id)}" aria-label="${esc(t('Foto groß zeigen','Show photo large'))}"><img data-cse="${esc(x.id)}" width="${Math.round(w*f)}" height="${Math.round(h*f)}" alt="${esc(t('Foto','Photo'))}"></button>`}
  if(a.kind==='voice')return `<span class="cx-voice"><audio controls preload="none" data-cse="${esc(x.id)}"></audio><small class="mut">${ic('mic')} ${esc(cxDur(m.secs))}</small></span>`;
  return `<a class="cx-file" data-cse="${esc(x.id)}" href="#" download="${esc(m.name||'')}"><span class="cx-fi">${ic('doc')}</span><span><b>${esc(m.name||t('Datei','File'))}</b><small class="mut">${esc((m.ext||'').toUpperCase()+' · '+cxSize(m.size))}</small></span></a>`};
async function csBlobUrl(cid,x){const ck=cid+'|'+x.id;if(CS.urls.has(ck))return CS.urls.get(ck);
  const pr=(async()=>{const r=await api('/api/chats/media?'+new URLSearchParams({id:cid,mid:x.id,part:'f'}));const b=new Uint8Array(await r.arrayBuffer());
    const pt=await crypto.subtle.decrypt({name:'AES-GCM',iv:b.subarray(0,12)},await csAes(csUn(x.att.k),'decrypt'),b.subarray(12));
    // the type the page shows it as: only the three kinds, a file is always a download
    const type=x.att.kind==='photo'?'image/jpeg':x.att.kind==='voice'&&/^audio\/[a-z0-9.+-]+$/.test(x.att.mime)?x.att.mime:'application/octet-stream';
    return URL.createObjectURL(new Blob([pt],{type}))})();
  CS.urls.set(ck,pr);pr.catch(()=>CS.urls.delete(ck));return pr}
async function csMedia(el,d){const x=d.items.find(y=>y.id===el.dataset.cse);if(!x||!x.att)return;
  try{const u=await csBlobUrl(CX.cur,x);if(el.tagName==='A')el.href=u;else el.src=u}catch{el.replaceWith(document.createTextNode(t('Anhang nicht lesbar','Attachment not readable')))}}
window.csBig=async x=>{try{cxEl('cxbigimg').src=await csBlobUrl(CX.cur,x);cxEl('cxbig').hidden=false;cxEl('cxbigx').focus()}catch(e){cxSay(e.message)}};

// ---------------------------------------------------------------- sending
// a box for every current device of both; a new device of the other one since the last fetch: fetch, box again, once
async function csSendBox(cid,payload,reply,blob){if(!CS.me)await csDevice(true);
  for(let i=0;i<2;i++){const box=await csBox(cid,payload,await csKeys(cid,i>0));
    try{if(blob){const q=new URLSearchParams({id:cid,kind:'box',reply:reply||''});
        await api('/api/chats/media?'+q,{method:'POST',headers:{'Content-Type':'application/octet-stream'},body:new Blob([JSON.stringify(box)+'\n',blob])})}
      else await cxApi('/api/chats/send',{id:cid,text:'',reply:reply||'',box});return}
    catch(e){if(i||e.status!==403||!/neues Gerät/.test(e.detail||''))throw e}}}
window.csSend=(cid,text,reply)=>csSendBox(cid,{t:text},reply);
// a photo is drawn anew (at most 2048 px, JPEG): no place or camera data leaves the device
async function csPhoto(blob){const bm=await createImageBitmap(blob),f=Math.min(1,2048/Math.max(bm.width,bm.height));
  const c=document.createElement('canvas');c.width=Math.round(bm.width*f);c.height=Math.round(bm.height*f);c.getContext('2d').drawImage(bm,0,0,c.width,c.height);
  const out=await new Promise(ok=>c.toBlob(ok,'image/jpeg',0.85));if(!out)throw new Error(t('Das Foto lässt sich nicht lesen.','The photo cannot be read.'));return {blob:out,w:c.width,h:c.height}}
window.csUpload=async(cid,kind,blob,name,secs,reply)=>{let w=0,h=0;
  if(kind==='photo'){try{({blob,w,h}=await csPhoto(blob))}catch{kind='file'}}
  const fk=csRand(32),iv=csRand(12),data=new Uint8Array(await blob.arrayBuffer());
  const ct=new Uint8Array(await crypto.subtle.encrypt({name:'AES-GCM',iv},await csAes(fk,'encrypt'),data));
  const sealed=new Uint8Array(12+ct.length);sealed.set(iv);sealed.set(ct,12);
  await csSendBox(cid,{t:'',a:{kind,k:csB64(fk),name:kind==='file'?String(name||'').slice(0,200):'',mime:String(blob.type||'').slice(0,100),size:data.length,secs:Math.round(secs||0),w,h}},reply,sealed)};

// ---------------------------------------------------------------- ⓘ: the Sicherheitsnummer and the own devices
async function csNumber(cid,keys){const by={};for(const k of keys)if(!k.gone)(by[k.uid]=by[k.uid]||[]).push(k.pub);
  const s=Object.keys(by).sort().map(u=>u+':'+by[u].sort().join(',')).join('|');
  const h=new Uint8Array(await crypto.subtle.digest('SHA-512',csEnc('spark-e2e-v1|'+cid+'|'+s))),out=[];
  for(let i=0;i<12;i++){let v=0;for(let j=0;j<5;j++)v=(v*256+h[i*5+j])%100000;out.push(String(v).padStart(5,'0'))}return out.join(' ')}
const csSeen=cid=>{try{return localStorage.getItem('cs-ok:'+cxMe()+':'+cid)||''}catch{return ''}};
window.csInfoHtml=()=>`<div class="cx-grp">${ic('lock')} ${esc(t('Ende-zu-Ende','End-to-end'))}</div><div id="csinfo" class="cx-cs"><span class="mut">…</span></div>`;
window.csInfo=async cid=>{const box=cxEl('csinfo');if(!box)return;let h='';
  if(!csOk()){box.textContent=csNoHttps();return}
  try{await csDevice(false);const keys=await csKeys(cid,true),num=await csNumber(cid,keys),ok=csSeen(cid)===num;
    h+=`<div class="intro sm">${esc(t('Nur eure Geräte können diesen Chat lesen, der Spark nicht. Vergleicht diese Nummer einmal von Angesicht zu Angesicht oder am Telefon: Ist sie bei euch beiden gleich, sitzt niemand dazwischen.','Only your devices can read this chat, the Spark cannot. Compare this number once face to face or on the phone: if it is the same for both of you, nobody sits in between.'))}</div>`+
      `<div class="cx-num" id="csnum">${esc(num)}</div>`+
      (ok?`<div class="ok sm">✓ ${esc(t('Verglichen. Ändert sich ein Schlüssel, fragt die Seite neu.','Compared. If a key changes, the page asks again.'))}</div>`
        :`<div class="cx-acts2"><button type="button" class="b" data-cxs="seen" data-num="${esc(num)}">${esc(t('Ist bei uns beiden gleich','It is the same for both of us'))}</button></div>`)}
  catch(e){h+=`<div class="cx-msgline err">${esc(cxTr(e.message))}</div>`}
  const when=ts=>new Date(ts*1000).toLocaleDateString(L==='en'?'en-GB':'de-DE',{day:'numeric',month:'short',year:'numeric'});
  const kw={browser:t('Browser','Browser'),android:t('Android-App','Android app'),iphone:t('iPhone-App','iPhone app')};
  h+=`<div class="cx-grp">${esc(t('Deine Geräte','Your devices'))}</div><div class="cx-people">`+(CS.own.length?CS.own.map(k=>`<div class="cx-pp"><span>${esc((kw[k.kind]||k.kind)+' · '+t('seit ','since ')+when(k.t))}`+
    `${CS.me&&CS.me.kid===k.id?` <small class="mut">${esc(t('dieses Gerät','this device'))}</small>`:''}</span><button type="button" class="b danger" data-cxs="rm" data-id="${esc(k.id)}">${esc(t('Entfernen','Remove'))}</button></div>`).join('')
    :`<div class="cx-none mut">${esc(t('Noch keines.','None yet.'))}</div>`)+`</div>`;
  if(!CS.me)h+=`<div class="cx-acts2"><button type="button" class="b p" data-cxs="dev">${esc(t('Dieses Gerät eintragen','Add this device'))}</button></div>`;
  box.innerHTML=h};
// a private chat with someone: this device needs its key first
window.csStartWith=async to=>{if(!csOk())throw new Error(csNoHttps());if(!CS.me)await csDevice(false);if(!CS.me)await csDevice(true);
  return (await cxApi('/api/chats/private',{to})).id};
async function csAct(e){const b=e.target.closest('[data-cxs]');if(!b)return;const a=b.dataset.cxs;
  try{if(a==='dev'){b.disabled=true;await csDevice(true);CS.open.clear();if(CX.pane==='info')csInfo(CX.cur);else cxOpen(CX.cur,true)}
    else if(a==='seen'){try{localStorage.setItem('cs-ok:'+cxMe()+':'+CX.cur,b.dataset.num)}catch{}csInfo(CX.cur)}
    else if(a==='rm'){const mine=CS.me&&CS.me.kid===b.dataset.id;
      if(!confirm(mine?t('Dieses Gerät aus den privaten Chats nehmen? Es kann sie danach nicht mehr lesen.','Take this device out of private chats? It cannot read them afterwards.')
        :t('Dieses Gerät aus den privaten Chats nehmen? Es kann neue Nachrichten danach nicht mehr lesen.','Take this device out of private chats? It cannot read new messages afterwards.')))return;
      await cxApi('/api/chats/keys/remove',{id:b.dataset.id});
      if(mine){CS.me=null;try{await csStore('readwrite',s=>s.delete(csSlot()))}catch{}CS.open.clear()}
      CS.keys={};csInfo(CX.cur)}}
  catch(err){if(CX.pane)cxPmsg(err.message,true);else cxSay(err.message)}finally{b.disabled=false}}
cxEl('cxpane').addEventListener('click',csAct);
cxEl('cxlog').addEventListener('click',csAct);

// ---------------------------------------------------------------- the history for a new device (Wahl 2)
// the code both devices show: from the new device's public key only
async function csCode(pub){const h=new Uint8Array(await crypto.subtle.digest('SHA-256',csEnc('spark-e2e-v1|device|'+pub)));
  const A='ABCDEFGHJKLMNPQRSTUVWXYZ23456789';let c='';for(let i=0;i<6;i++)c+=A[h[i]%32];return c}
const csKindName=k=>({browser:t('Browser','Browser'),android:t('Android-App','Android app'),iphone:t('iPhone-App','iPhone app')})[k]||k;
// after the chat list is drawn: an older device offers the transfer to a new one of the same person (CSH keeps it
// across redraws of the list, also while the transfer runs)
const CSH={t:0,later:0,nk:null,code:'',msg:'',busy:false,ok:''};
window.csShareCheck=async box=>{if(!csOk())return;csShareDraw(box);if(CSH.busy)return;const wait=3000-(Date.now()-CSH.t);
  if(wait>0){if(!CSH.later)CSH.later=setTimeout(()=>{CSH.later=0;csShareCheck(cxEl('cxlist'))},wait);return}CSH.t=Date.now();
  try{await csDevice(false)}catch{return}
  const me=CS.me&&CS.own.find(k=>k.id===CS.me.kid),nk=me&&!me.want?CS.own.find(k=>k.want&&k.id!==me.id&&k.t>=me.t&&k.pub):null;
  if((nk&&nk.id)!==(CSH.nk&&CSH.nk.id)){CSH.nk=nk||null;CSH.msg='';CSH.code=nk?await csCode(nk.pub):''}
  csShareDraw(cxEl('cxlist'))};
function csShareDraw(box){if(!box)return;const old=box.querySelector('.cx-share');if(old)old.remove();const nk=CSH.nk;
  if(!nk){if(CSH.ok){const n=document.createElement('div');n.className='cx-share';n.innerHTML=`<b>${ic('lock')} ${esc(CSH.ok)}</b>`;box.prepend(n)}return}
  const when=new Date(nk.t*1000).toLocaleString(L==='en'?'en-GB':'de-DE',{day:'numeric',month:'short',hour:'2-digit',minute:'2-digit'});
  const n=document.createElement('div');n.className='cx-share';
  n.innerHTML=`<b>${ic('lock')} ${esc(t('Neues Gerät','New device'))}: ${esc(csKindName(nk.kind)+', '+when)}</b>`+
    `<small>${esc(t('Verlauf deiner privaten Chats dorthin übertragen? Nur wenn dort derselbe Code steht:','Transfer the history of your private chats there? Only if it shows the same code:'))} <b class="cx-code">${esc(CSH.code)}</b></small>`+
    `<span class="cx-acts2"><button type="button" class="b p" data-csh="go"${CSH.busy?' disabled':''}>${esc(t('Übertragen','Transfer'))}</button>`+
    `<button type="button" class="b danger" data-csh="no"${CSH.busy?' disabled':''}>${esc(t('Nicht ich','Not me'))}</button></span>`+
    (CSH.msg?`<small class="mut">${esc(CSH.msg)}</small>`:'');
  box.prepend(n)}
async function csShare(nk){const me=CS.me,list=(CX.S&&CX.S.chats||[]).filter(c=>c.private);let n=0,done=0;
  for(const c of list){const r=await cxApi('/api/chats/share?'+new URLSearchParams({id:c.id,by:me.kid,new:nk.id}));
    const keys=await csKeys(c.id,true);let wraps={};
    const flush=async()=>{if(Object.keys(wraps).length){n+=(await cxApi('/api/chats/share',{id:c.id,by:me.kid,new:nk.id,wraps})).added||0;wraps={}}};
    for(const it of r.items||[]){let o=null;try{o=await csKeyOf(c.id,{f:it.f},keys,it.w)}catch{}
      if(!o||o.snd.uid!==it.from)continue;   // only what this device can open and really comes from that person
      const s=csRand(16),i=csRand(12);
      const w=await crypto.subtle.encrypt({name:'AES-GCM',iv:i},await csWrap(nk.pub,c.id,me.kid,nk.id,s),o.K);
      wraps[it.id]={s:csB64(s),i:csB64(i),w:csB64(new Uint8Array(w))};if(Object.keys(wraps).length>=300)await flush()}
    await flush();done++;CSH.msg=t('Übertragen: ','Transferred: ')+done+' / '+list.length;csShareDraw(cxEl('cxlist'))}
  await cxApi('/api/chats/share/done',{new:nk.id,n});return n}
cxEl('cxlist').addEventListener('click',async e=>{const b=e.target.closest('[data-csh]'),nk=CSH.nk;if(!b||!nk||CSH.busy)return;
  if(b.dataset.csh==='no'&&!confirm(t('Dieses neue Gerät aus den privaten Chats nehmen? Es kann sie danach nicht mehr lesen.','Take this new device out of private chats? It cannot read them afterwards.')))return;
  CSH.busy=true;csShareDraw(cxEl('cxlist'));
  try{if(b.dataset.csh==='go'){const n=await csShare(nk);CSH.ok=t('Verlauf übertragen: ','History transferred: ')+n+' '+t('Nachrichten','messages');
      setTimeout(()=>{CSH.ok='';csShareDraw(cxEl('cxlist'))},8000)}
    else{await cxApi('/api/chats/keys/remove',{id:nk.id});CS.keys={}}
    CSH.nk=null;CSH.msg=''}
  catch(err){CSH.msg=cxTr(err.message)}
  finally{CSH.busy=false;CSH.t=0;csShareDraw(cxEl('cxlist'))}});
