// E-Mail (Dominik 2026-10-18, plan kalender-mail/plan.md 2a 4a): the profile's mailboxes as a page of its own in the
// menu. „Posteingang“ lists the newest messages of every mailbox (GET /api/profile/mail/inbox) and shows one as plain
// text (GET /api/profile/mail/message, it stays unread); „Einstellungen“ holds everything set up for mail (#mailbox
// with Aufräumen, Mailstil and Pakete in #parbox; pages of Ich until V01.0.807). Sender, subject and text come from
// other people: only through esc(), no HTML, no pictures, no links that open.
const POST={data:null,sel:null,msg:null,q:'',unread:false,seq:0,mseq:0,busy:false,err:'',done:null,folders:{},write:null,prev:null,sent:'',accts:null};
// Mails ordnen (postfach.py, admin switch chat.mail_manage, start.js): read/unread, archive, move, back right after
let ORD_ON=false;
// Mails senden (senden.py, admin switch chat.mail_send): a new mail or an answer, the preview sheet, only its „Senden“ sends
let SEND_ON=false;
// the menu entry only for a signed-in profile that may read mail (start.js, like Kalender)
window.postStart=who=>{const on=!!(who&&who.profile&&who.mail);document.querySelectorAll('nav button[data-s=post]').forEach(b=>b.hidden=!on)};
const postWhen=s=>{const d=new Date(s*1000),now=new Date();
  return d.toDateString()===now.toDateString()?d.toLocaleTimeString(kalLoc(),{hour:'2-digit',minute:'2-digit'})
    :d.toLocaleDateString(kalLoc(),{day:'numeric',month:'short'})};
// the sender's name without the address, for the list
const postName=f=>{const m=/^(.*?)\s*<[^>]*>$/.exec(f||'');return (m&&m[1])||f||''};
async function postLoad(){if(!PROFILE||!MAIL_ON)return;const seq=++POST.seq;POST.busy=true;postDraw();
  try{const d=await (await api('/api/profile/mail/inbox?'+new URLSearchParams({q:POST.q,unread:POST.unread?'true':'false'}))).json();
    if(seq!==POST.seq)return;POST.data=d;POST.err=''}
  catch(e){if(seq!==POST.seq)return;POST.err=e.message||t('Nicht erreicht','Not reached')}
  POST.busy=false;postDraw()}
async function postRead(id){POST.sel=id;POST.msg=null;const seq=++POST.mseq;postDraw();
  try{const m=await (await api('/api/profile/mail/message?'+new URLSearchParams({id}))).json();if(seq===POST.mseq)POST.msg=m}
  catch(e){if(seq===POST.mseq)POST.msg={err:e.message||t('Nicht erreicht','Not reached')}}
  postDraw()}
function postOpen(){if(!PROFILE)return;const root=$('postroot');root.textContent='';
  root.appendChild(icTabs('post',[{k:'show',label:OWN_PAGES.mailbox[2],body:postBody},
    // „Für dich“ (fuerdich.js, its own function): what the Spark found in the mails, only when it is switched on
    ...(OWN_PAGES.mailbox[3][0][2]()?[{k:'fuer',label:OWN_PAGES.mailbox[3][0][1],body:()=>{const b=$('fuerbox');b.hidden=false;lzb(b,showFuerDich,{auth:true}).catch(()=>{});return b}}]:[]),
    {k:'set',label:t('Einstellungen','Settings'),body:()=>{const b=$('mailbox');b.hidden=false;$('parwrap').hidden=!PAR_ON;
      lzb(b,async()=>{await showMail();await Promise.all([showMailTidy().catch(()=>{}),showMailStil().catch(()=>{})])},{auth:true}).catch(()=>{});
      proIn('promail').catch(()=>{});if(PAR_ON)lzb($('parbox'),showPar,{auth:true}).catch(()=>{});return b}}]));
  postLoad()}
// the tab „Posteingang“: search, the list, the message tapped
function postBody(){const w=document.createElement('div');w.className='ld-box post';w.id='postview';postPaint(w);return w}
function postDraw(){const w=$('postview');if(w)postPaint(w)}
function postPaint(w){const d=POST.data;w.classList.toggle('ld-sel',!!POST.sel||!!POST.write);
  if(d&&d.connected===false){w.innerHTML=`<div class="empty">${esc(t('Noch kein Postfach verbunden. Unter Einstellungen verbindest du iCloud, Gmail, GMX, web.de oder ein anderes IMAP-Postfach.','No mailbox connected yet. Under Settings you connect iCloud, Gmail, GMX, web.de or another IMAP mailbox.'))}<div><button class="b p" type="button" data-k="set">${esc(t('Postfach verbinden','Connect a mailbox'))}</button></div></div>`;
    w.querySelector('[data-k=set]').onclick=()=>{icTabSet('post','set');postOpen()};return}
  if(!w.querySelector('.ld-tools')){
    w.innerHTML=`<div class="ld-tools"><input type="search" data-k="q" placeholder="${esc(t('Absender oder Betreff suchen','Search sender or subject'))}" aria-label="${esc(t('Suchen','Search'))}"><button type="button" class="ld-chip" data-k="unread" aria-pressed="false">${esc(t('Nur ungelesen','Unread only'))}</button>${SEND_ON?`<button type="button" class="b p" data-k="new">${esc(t('Neue Mail','New mail'))}</button>`:''}<button type="button" class="b" data-k="again">${esc(t('Neu laden','Reload'))}</button></div>`+
      `<div class="postwarn"></div><div class="postundo"></div><div class="ld-split"><div class="ld-list"></div><div class="ld-detail postdet" hidden></div></div>`;
    const q=w.querySelector('[data-k=q]');q.value=POST.q;let tm=0;
    q.oninput=()=>{clearTimeout(tm);tm=setTimeout(()=>{POST.q=q.value.trim();POST.sel=null;postLoad()},400)};
    w.querySelector('[data-k=unread]').onclick=()=>{POST.unread=!POST.unread;POST.sel=null;postLoad()};
    w.querySelector('[data-k=again]').onclick=()=>postLoad();
    const nw=w.querySelector('[data-k=new]');if(nw)nw.onclick=()=>postWrite(null)}
  const u=w.querySelector('[data-k=unread]');u.classList.toggle('on',POST.unread);u.setAttribute('aria-pressed',String(POST.unread));
  w.querySelector('.postwarn').innerHTML=(POST.err?`<div class="note warn">${esc(t('Die Mails kamen nicht an: ','The mail did not arrive: ')+POST.err)}</div>`:'')+
    (d&&d.errors&&d.errors.length?`<div class="note warn">${esc(t('Nicht erreicht: ','Not reached: ')+d.errors.join(', '))}</div>`:'');
  const many=d&&d.boxes&&d.boxes.length>1,items=(d&&d.items)||[],list=w.querySelector('.ld-list');
  list.classList.toggle('busy',POST.busy);
  list.innerHTML=items.map(x=>`<div class="ld-row${POST.sel===x.id?' on':''}${x.unread?' unread':''}" role="button" tabindex="0" data-id="${esc(x.id)}">`+
      `<span class="postdot" aria-label="${esc(x.unread?t('ungelesen','unread'):'')}"></span><span class="ld-mid"><b>${esc(postName(x.from))}</b><small>${esc(x.subject||t('(ohne Betreff)','(no subject)'))}</small></span>`+
      `<span class="ld-right">${many?`<span class="ld-badge off">${esc(d.boxes[x.box]||'')}</span>`:''}<span class="ld-when">${esc(postWhen(x.date))}</span></span></div>`).join('')
    ||(POST.busy?'':`<div class="ld-empty mut">${esc(POST.q||POST.unread?t('Keine passende Mail in den letzten 14 Tagen.','No matching mail in the last 14 days.'):t('Keine Mail in den letzten 14 Tagen.','No mail in the last 14 days.'))}</div>`);
  list.querySelectorAll('[data-id]').forEach(r=>{r.onclick=()=>postRead(r.dataset.id);r.onkeydown=e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();postRead(r.dataset.id)}}});
  postUndo(w);if(POST.sent)w.querySelector('.postundo').insertAdjacentHTML('beforeend',`<div class="note">${esc(POST.sent)}</div>`);
  if(POST.write)postWriteBox(w);else postDetail(w)}
// one message: plain text, attachments only named (to Dokumente on request through the assistant)
function postDetail(w){const box=w.querySelector('.postdet'),m=POST.msg;if(!box)return;box.hidden=!POST.sel;if(!POST.sel)return;
  const back=`<button type="button" class="b ld-back" data-close="1">‹ ${esc(t('Zurück','Back'))}</button>`;
  if(!m)box.innerHTML=back+`<div class="mut">${esc(t('Lade die Mail …','Loading the mail …'))}</div>`;
  else if(m.err)box.innerHTML=back+`<div class="note warn">${esc(m.err)}</div>`;
  else box.innerHTML=back+`<h3>${esc(m.subject||t('(ohne Betreff)','(no subject)'))}</h3>`+
    `<dl class="ld-facts"><dt>${esc(t('Von','From'))}</dt><dd>${esc(m.from)}</dd>${m.to?`<dt>${esc(t('An','To'))}</dt><dd>${esc(m.to)}</dd>`:''}<dt>${esc(t('Wann','When'))}</dt><dd>${esc(new Date(m.date*1000).toLocaleString(kalLoc(),{weekday:'short',day:'numeric',month:'long',hour:'2-digit',minute:'2-digit'}))}</dd>`+
    (m.files&&m.files.length?`<dt>${esc(t('Anhänge','Attachments'))}</dt><dd>${esc(m.files.join(', '))}</dd>`:'')+`</dl>`+
    `<div class="posttext">${esc(m.text||t('(kein Text)','(no text)'))}</div>`+
    `<div class="fh">${esc(t('Nur als Text, Bilder und Links von außen sind aus. Antworten geht mit dem Assistenten: „Antworte Anna …“.','Text only, pictures and links from outside stay off. Reply with the assistant: "Reply to Anna …".'))}</div>`+
    (SEND_ON&&!m.err?`<div class="row postord"><button class="b p" type="button" data-w="reply">${esc(t('Antworten','Reply'))}</button></div>`:'')+
    (ORD_ON&&!m.err?postOrder():'');
  box.querySelector('[data-close]').onclick=()=>{POST.sel=null;POST.msg=null;postDraw()};
  const rp=box.querySelector('[data-w=reply]');if(rp)rp.onclick=()=>postWrite(m);
  if(ORD_ON&&m&&!m.err)postOrderBind(box)}
// the buttons below a message: never delete, every move can go back right after
function postOrder(){const x=((POST.data&&POST.data.items)||[]).find(i=>i.id===POST.sel),f=POST.folders[POST.sel.split(':')[0]];
  return `<div class="row postord"><button class="b" type="button" data-o="${x&&x.unread?'read':'unread'}">${esc(x&&x.unread?t('Als gelesen markieren','Mark as read'):t('Als ungelesen markieren','Mark as unread'))}</button>`+
    `<button class="b" type="button" data-o="archive">${esc(t('Archivieren','Archive'))}</button>`+
    `<select data-o="folder" aria-label="${esc(t('Verschieben nach','Move to'))}"><option value="">${esc(t('Verschieben nach …','Move to …'))}</option>${(f&&f.folders||[]).map(n=>`<option value="${esc(n)}">${esc(n)}</option>`).join('')}</select></div><div class="postordmsg fh"></div>`}
async function postOrderBind(box){const acct=POST.sel.split(':')[0],sel=box.querySelector('select[data-o=folder]'),msg=box.querySelector('.postordmsg');
  if(!POST.folders[acct]){const {r,d}=await apiTry('/api/profile/mail/folders?'+new URLSearchParams({account:acct}));if(r.ok){POST.folders[acct]=d;if($('postview'))postDetail($('postview'))}}
  box.querySelectorAll('button[data-o]').forEach(b=>b.onclick=()=>postAct(b.dataset.o,'',msg));
  if(sel)sel.onchange=()=>{if(sel.value)postAct('move',sel.value,msg)}}
async function postAct(action,folder,msg,mid){const id=POST.sel;msg.className='postordmsg fh';msg.textContent=t('Einen Moment …','One moment …');
  const {r,d}=await apiTry('/api/profile/mail/act',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id,action,folder,mid:mid||''})});
  if(!r.ok){msg.className='postordmsg err';msg.textContent=errSay(r.status,d.detail,'');return}
  if(action==='read'||action==='unread'){const x=POST.data.items.find(i=>i.id===id);if(x)x.unread=action==='unread';postDraw();return}
  // archived or moved: off the list, with „Rückgängig“ for a while
  POST.done={id,acct:id.split(':')[0],mid:d.mid,folder:d.folder};POST.sel=null;POST.msg=null;
  POST.data.items=POST.data.items.filter(i=>i.id!==id);postDraw()}
function postUndo(w){const u=POST.done,box=w.querySelector('.postundo');if(!box)return;
  if(!u){box.innerHTML='';return}
  box.innerHTML=`<div class="note">${esc(t('Verschoben nach ','Moved to ')+u.folder+'.')} <button class="b" type="button" data-u="1">${esc(t('Rückgängig','Undo'))}</button></div>`;
  box.querySelector('[data-u]').onclick=async()=>{const {r,d}=await apiTry('/api/profile/mail/act',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id:u.acct+':0',action:'back',folder:u.folder,mid:u.mid})});
    POST.done=null;if(!r.ok){box.innerHTML=`<div class="note warn">${esc(errSay(r.status,d.detail,''))}</div>`;return}postLoad()}}
// Mails senden: the form (new mail, or the answer to the mail shown), then the preview sheet from the server;
// only „Senden“ on the sheet sends (POST /api/profile/mail/send with its token). Nothing goes out from the form.
const postAddr=f=>{const m=/<([^>]+)>\s*$/.exec(f||'');return (m?m[1]:f||'').trim()};
async function postWrite(m){POST.sent='';POST.prev=null;
  POST.write=m?{reply:POST.sel,to:postAddr(m.from),cc:'',subject:/^(re|aw|antw)\s*:/i.test(m.subject||'')?m.subject:'Re: '+(m.subject||''),text:'',account:''}
    :{reply:'',to:'',cc:'',subject:'',text:'',account:''};
  if(!m&&!POST.accts){const {r,d}=await apiTry('/api/profile/mail');POST.accts=r.ok?(d.accounts||[]):[]}
  if(!m&&POST.accts&&POST.accts.length)POST.write.account=POST.accts[0].id;postDraw()}
function postWriteBox(w){const box=w.querySelector('.postdet'),f=POST.write,p=POST.prev;if(!box)return;box.hidden=false;
  const back=`<button type="button" class="b ld-back" data-close="1">‹ ${esc(t('Verwerfen','Discard'))}</button>`;
  if(p){box.innerHTML=back+`<h3>${esc(t('So geht die Mail raus','This is the mail that goes out'))}</h3><dl class="ld-facts postprev">`+
      `<dt>${esc(t('Von','From'))}</dt><dd>${esc(p.from)}</dd><dt>${esc(t('An','To'))}</dt><dd>${esc(p.to.join(', '))}</dd>`+
      (p.cc.length?`<dt>${esc(t('Kopie','Copy'))}</dt><dd>${esc(p.cc.join(', '))}</dd>`:'')+`<dt>${esc(t('Betreff','Subject'))}</dt><dd>${esc(p.subject||t('(ohne Betreff)','(no subject)'))}</dd></dl>`+
      `<div class="posttext">${esc(p.text)}</div><div class="row postord"><button class="b p" type="button" data-s="send">${esc(t('Senden','Send'))}</button><button class="b" type="button" data-s="edit">${esc(t('Ändern','Edit'))}</button></div><div class="postordmsg fh"></div>`;
    box.querySelector('[data-s=edit]').onclick=()=>{POST.prev=null;postDraw()};
    box.querySelector('[data-s=send]').onclick=e=>postSend(e.target,box.querySelector('.postordmsg'))}
  else{const many=!f.reply&&POST.accts&&POST.accts.length>1;
    box.innerHTML=back+`<h3>${esc(f.reply?t('Antworten','Reply'):t('Neue Mail','New mail'))}</h3><div class="postform">`+
      (many?`<label>${esc(t('Von','From'))}</label><select data-f="account">${POST.accts.map(a=>`<option value="${esc(a.id)}"${a.id===f.account?' selected':''}>${esc(a.name+' · '+a.user)}</option>`).join('')}</select>`:'')+
      `<label>${esc(t('An','To'))}</label><input data-f="to" type="email" multiple maxlength="2000" autocomplete="off">`+
      `<label>${esc(t('Kopie','Copy'))}</label><input data-f="cc" type="email" multiple maxlength="2000" autocomplete="off">`+
      `<label>${esc(t('Betreff','Subject'))}</label><input data-f="subject" maxlength="200">`+
      `<label>${esc(t('Text','Text'))}</label><textarea data-f="text" rows="9" maxlength="20000"></textarea>`+
      `<div class="row postord"><button class="b p" type="button" data-s="prev">${esc(t('Vorschau','Preview'))}</button></div><div class="postordmsg fh">${esc(t('Erst die Vorschau zeigt, was rausgeht. Gesendet wird nur dort.','Only the preview shows what goes out. It is sent only there.'))}</div></div>`;
    for(const k of ['to','cc','subject','text']){const el=box.querySelector(`[data-f=${k}]`);el.value=f[k]||'';el.oninput=()=>{f[k]=el.value}}
    const ac=box.querySelector('[data-f=account]');if(ac)ac.onchange=()=>{f.account=ac.value};
    box.querySelector('[data-s=prev]').onclick=()=>postPreview(box.querySelector('.postordmsg'))}
  box.querySelector('[data-close]').onclick=()=>{POST.write=null;POST.prev=null;postDraw()}}
async function postPreview(msg){const f=POST.write;msg.className='postordmsg fh';msg.textContent=t('Einen Moment …','One moment …');
  const {r,d}=await apiTry('/api/profile/mail/send/preview',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(f)});
  if(!r.ok){msg.className='postordmsg err';msg.textContent=errSay(r.status,d.detail,'');return}
  POST.prev=d;postDraw()}
async function postSend(b,msg){b.disabled=true;msg.className='postordmsg fh';msg.textContent=t('Sende …','Sending …');
  const {r,d}=await apiTry('/api/profile/mail/send',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({token:POST.prev.token})});
  if(!r.ok){b.disabled=false;msg.className='postordmsg err';msg.textContent=errSay(r.status,d.detail,'');if(r.status===409){POST.prev=null;setTimeout(postDraw,1500)}return}
  POST.sent=t('Gesendet an ','Sent to ')+d.sent+(d.sent===1?t(' Empfänger',' recipient'):t(' Empfänger',' recipients'))+(d.refused?t(', abgelehnt: ',', refused: ')+d.refused:'')+'.';
  POST.write=null;POST.prev=null;postDraw()}
