// E-Mail (Dominik 2026-10-18, plan kalender-mail/plan.md 2a 4a): the profile's mailboxes as a page of its own in the
// menu. „Posteingang“ lists the newest messages of every mailbox (GET /api/profile/mail/inbox) and shows one as plain
// text (GET /api/profile/mail/message, it stays unread); „Einstellungen“ holds everything set up for mail (#mailbox
// with Aufräumen, Mailstil and Pakete in #parbox; pages of Ich until V01.0.807). Sender, subject and text come from
// other people: only through esc(), no HTML, no pictures, no links that open.
const POST={data:null,sel:null,msg:null,q:'',unread:false,seq:0,mseq:0,busy:false,err:'',done:null,folders:{},write:null,prev:null,sent:'',accts:null,sug:{}};
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
// the mail-client look (Dominik 2026-10-19 „4a“): the list by day, the sender's initials in a colour of their own
const postDay=s=>{const d=new Date(s*1000),n=new Date(),y=new Date(n.getFullYear(),n.getMonth(),n.getDate()-1);
  return d.toDateString()===n.toDateString()?t('Heute','Today'):d.toDateString()===y.toDateString()?t('Gestern','Yesterday')
    :d.toLocaleDateString(kalLoc(),{weekday:'long',day:'numeric',month:'long'})};
const postInit=f=>{const w=postName(f).split('@')[0].replace(/["'„“]/g,'').split(/[\s._-]+/).filter(Boolean);return ((w[0]||'?')[0]+(w.length>1?w[1][0]:'')).toUpperCase()};
const postKc=f=>{let h=0;for(const c of postAddr(f).toLowerCase())h=(h*31+c.charCodeAt(0))>>>0;return kalKc(h)};
// what Für dich found in a mail, as a small chip in the list (its own cached reading, only when switched on)
const postFuer=x=>typeof FUER!=='undefined'&&FUER&&FUER.items?FUER.items.find(i=>i.subject&&i.subject===x.subject&&postName(x.from).includes(i.who||'\u0000')):null;
async function postFuerLoad(){if(typeof FUER_ON==='undefined'||!FUER_ON||FUER)return;
  try{const d=await (await api('/api/profile/fuerdich')).json();if(!d.loading&&!FUER){FUER=d;postDraw()}}catch(e){}}
// again: mailboxes still loading in the background (mail.inbox) are asked for once more after 3 s, at most 5 times
async function postLoad(again){if(!PROFILE||!MAIL_ON)return;const seq=++POST.seq;POST.busy=!again;POST.tries=again?(POST.tries||0)+1:0;postDraw();
  try{const d=await (await api('/api/profile/mail/inbox?'+new URLSearchParams({q:POST.q,unread:POST.unread?'true':'false'}))).json();
    if(seq!==POST.seq)return;if(!(d.loading&&POST.data&&again))POST.data=d;POST.err='';
    if(d.loading&&POST.tries<5)setTimeout(()=>{if(seq===POST.seq&&$('postview'))postLoad(true)},3000)}
  catch(e){if(seq!==POST.seq)return;POST.err=e.message||t('Nicht erreicht','Not reached')}
  POST.busy=false;postDraw();postFuerLoad()}
async function postRead(id){POST.sel=id;POST.msg=null;if(POST.sug[id]&&POST.sug[id].err)delete POST.sug[id];const seq=++POST.mseq;postDraw();
  try{const m=await (await api('/api/profile/mail/message?'+new URLSearchParams({id}))).json();if(seq===POST.mseq)POST.msg=m}
  catch(e){if(seq===POST.mseq)POST.msg={err:e.message||t('Nicht erreicht','Not reached')}}
  postDraw();
  // Antwortvorschläge „1a“: a mail that stays open a moment gets its answers prepared, „Antworten“ finds them ready
  if(SEND_ON&&POST.msg&&!POST.msg.err)setTimeout(()=>{if(POST.sel===id&&seq===POST.mseq)postSuggest(id)},POST_SUG_MS)}
// Antwortvorschläge (antwortvorschlag.py): three answers per mail, asked once, kept on the Spark for a while
const POST_SUG_MS=1200;
async function postSuggest(id){if(POST.sug[id])return;   // asked once; a failed one again when the mail is opened anew
  POST.sug[id]={busy:true};
  const {r,d}=await apiTry('/api/profile/mail/suggest',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id})});
  POST.sug[id]=r.ok?{items:d.items||[]}:{err:errSay(r.status,d.detail,'')};
  if(POST.write&&POST.write.reply===id&&!POST.prev)postDraw()}
function postSugBox(f){const x=POST.sug[f.reply]||{busy:true};
  const rows=x.items?x.items.map((v,i)=>`<button type="button" class="postsug${f.picked===i?' on':''}" data-g="${i}"><i>${esc(v.label)}</i>${esc(v.text)}</button>`).join('')
    :x.err?`<div class="fh err">${esc(x.err)}</div>`:`<div class="fh">${esc(t('Vorschläge kommen …','Suggestions coming …'))}</div>`;
  return `<label>${esc(t('Vorschläge (nichts wird gesendet)','Suggestions (nothing is sent)'))}</label><div class="postsugs">${rows}</div>`}
const POST_TONE=[['kuerzer','kürzer','shorter'],['freundlicher','freundlicher','friendlier'],['foermlicher','förmlicher','more formal'],['uebersetzen','auf Englisch','in English']];
async function postTone(art,box){const f=POST.write,ta=box.querySelector('[data-f=text]'),msg=box.querySelector('.postordmsg');
  if(!(f.text||'').trim())return;box.querySelectorAll('[data-r]').forEach(b=>b.disabled=true);msg.className='postordmsg fh';msg.textContent=t('Einen Moment …','One moment …');
  const {r,d}=await apiTry('/api/profile/mail/rewrite',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({text:f.text,art})});
  box.querySelectorAll('[data-r]').forEach(b=>b.disabled=false);
  if(!r.ok){msg.className='postordmsg err';msg.textContent=errSay(r.status,d.detail,'');return}
  f.text=d.text;ta.value=d.text;ta.dispatchEvent(new Event('input'));msg.textContent=''}
// the boxes a tab shows (Für dich, Einstellungen) live in the section; back there before the tabs are drawn anew,
// else clearing the card would take them out of the page and a second visit showed an empty card
const POST_BOXES=['fuerbox','mailbox'].map(id=>$(id));
function postOpen(){if(!PROFILE)return;const root=$('postroot');for(const b of POST_BOXES)if(b){b.hidden=true;$('post').appendChild(b)}root.textContent='';
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
    (d&&d.errors&&d.errors.length?`<div class="note warn">${esc(t('Nicht erreicht: ','Not reached: ')+d.errors.join(', '))}</div>`:'')+
    (d&&d.loading?`<div class="note">${esc(t('Die Postfächer laden noch …','The mailboxes are still loading …'))}</div>`:'');
  const many=d&&d.boxes&&d.boxes.length>1,items=(d&&d.items)||[],list=w.querySelector('.ld-list');
  list.classList.toggle('busy',POST.busy);
  let day='';
  list.innerHTML=items.map(x=>{const g=postDay(x.date),head=g!==day?`<div class="ld-grp"><span>${esc(g)}</span></div>`:'';day=g;const fd=postFuer(x);
    return head+`<div class="ld-row${POST.sel===x.id?' on':''}${x.unread?' unread':''}" role="button" tabindex="0" data-id="${esc(x.id)}">`+
      `<span class="postdot" aria-label="${esc(x.unread?t('ungelesen','unread'):'')}"></span><span class="postav ${postKc(x.from)}" aria-hidden="true">${esc(postInit(x.from))}</span><span class="ld-mid"><b>${esc(postName(x.from))}</b><small>${esc(x.subject||t('(ohne Betreff)','(no subject)'))}</small>${fd?`<span class="postfd${fd.urgent?' hot':''}">${esc(FUER_KIND[fd.kind]||fd.kind)}</span>`:''}</span>`+
      `<span class="ld-right">${many?`<span class="ld-badge off">${esc(d.boxes[x.box]||'')}</span>`:''}<span class="ld-when">${esc(postWhen(x.date))}</span></span></div>`}).join('')
    ||(POST.busy?'':`<div class="ld-empty mut">${esc(POST.q||POST.unread?t('Keine passende Mail in den letzten 14 Tagen.','No matching mail in the last 14 days.'):t('Keine Mail in den letzten 14 Tagen.','No mail in the last 14 days.'))}</div>`);
  list.querySelectorAll('[data-id]').forEach(r=>{r.onclick=()=>{if(POST.swiped){POST.swiped=false;return}postRead(r.dataset.id)};r.onkeydown=e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();postRead(r.dataset.id)}};postSwipe(r)});
  postUndo(w);if(POST.sent)w.querySelector('.postundo').insertAdjacentHTML('beforeend',`<div class="note">${esc(POST.sent)}</div>`);
  if(POST.write)postWriteBox(w);else postDetail(w)}
// one message: plain text, attachments only named (to Dokumente on request through the assistant)
// the way out is always shown (Dominik 2026-10-19): on the phone „‹ Zurück“, beside the list „✕ Schließen“
const postOut=(de,en)=>`<button type="button" class="b ld-back postclose" data-close="1">${NARROW()?'‹':'✕'} ${esc(t(de,en))}</button>`;
function postDetail(w){const box=w.querySelector('.postdet'),m=POST.msg;if(!box)return;box.hidden=!POST.sel;if(!POST.sel)return;
  const back=NARROW()?postOut('Zurück','Back'):postOut('Schließen','Close');
  if(!m)box.innerHTML=back+`<div class="mut">${esc(t('Lade die Mail …','Loading the mail …'))}</div>`;
  else if(m.err)box.innerHTML=back+`<div class="note warn">${esc(m.err)}</div>`;
  else box.innerHTML=back+`<h3>${esc(m.subject||t('(ohne Betreff)','(no subject)'))}</h3>`+
    `<dl class="ld-facts"><dt>${esc(t('Von','From'))}</dt><dd>${esc(m.from)}</dd>${m.to?`<dt>${esc(t('An','To'))}</dt><dd>${esc(m.to)}</dd>`:''}<dt>${esc(t('Wann','When'))}</dt><dd>${esc(new Date(m.date*1000).toLocaleString(kalLoc(),{weekday:'short',day:'numeric',month:'long',hour:'2-digit',minute:'2-digit'}))}</dd>`+
    (m.files&&m.files.length?`<dt>${esc(t('Anhänge','Attachments'))}</dt><dd>${esc(m.files.join(', '))}</dd>`:'')+`</dl>`+
    `<div class="posttext">${esc(m.text||t('(kein Text)','(no text)'))}</div>`+
    `<div class="fh">${esc(t('Nur als Text, Bilder und Links von außen sind aus.','Text only, pictures and links from outside stay off.')+' '+(SEND_ON?'':t('Antworten geht mit dem Assistenten: „Antworte Anna …“.','Reply with the assistant: "Reply to Anna …".'))+(NARROW()?'':' '+t('Tasten: J und K blättern','Keys: J and K browse')+(SEND_ON?t(', R antwortet',', R replies'):'')+(ORD_ON?t(', E archiviert, U gelesen oder ungelesen',', E archives, U read or unread'):'')+'.'))}</div>`+
    (!m.err&&(SEND_ON||(typeof CAL_ON!=='undefined'&&CAL_ON))?`<div class="row postwr">${SEND_ON?`<button class="b p" type="button" data-w="reply">${esc(t('Antworten','Reply'))}</button>`:''}${typeof CAL_ON!=='undefined'&&CAL_ON?`<button class="b" type="button" data-w="cal">${esc(t('Als Termin','As appointment'))}</button>`:''}</div>`:'')+
    (ORD_ON&&!m.err?postOrder():'');
  box.querySelector('[data-close]').onclick=()=>{POST.sel=null;POST.msg=null;postDraw()};
  const rp=box.querySelector('[data-w=reply]');if(rp)rp.onclick=()=>postWrite(m);
  const ac=box.querySelector('[data-w=cal]');if(ac)ac.onclick=()=>postAsEvent(m);
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
async function postAct(action,folder,msg,mid,which){const id=which||POST.sel;if(msg){msg.className='postordmsg fh';msg.textContent=t('Einen Moment …','One moment …')}
  const {r,d}=await apiTry('/api/profile/mail/act',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id,action,folder,mid:mid||''})});
  if(!r.ok){if(msg){msg.className='postordmsg err';msg.textContent=errSay(r.status,d.detail,'')}else{POST.err=errSay(r.status,d.detail,'');postDraw()}return}
  if(action==='read'||action==='unread'){const x=POST.data.items.find(i=>i.id===id);if(x)x.unread=action==='unread';postDraw();return}
  // archived or moved: off the list, with „Rückgängig“ for a while
  POST.done={id,acct:id.split(':')[0],mid:d.mid,folder:d.folder};if(POST.sel===id){POST.sel=null;POST.msg=null}
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
  if(!m&&POST.accts&&POST.accts.length)POST.write.account=POST.accts[0].id;POST.focus=true;postDraw()}
// a reply opens below the mail it answers, like a mail client (Dominik 2026-10-19); a new mail fills the pane
function postWriteBox(w){let box=w.querySelector('.postdet');const f=POST.write,p=POST.prev;if(!box)return;box.hidden=false;
  const inline=!!(f.reply&&POST.sel===f.reply&&POST.msg&&!POST.msg.err);
  if(inline){postDetail(w);const rp=box.querySelector('[data-w=reply]');if(rp)rp.remove();
    box.querySelector('.ld-back').onclick=()=>postDrop(true);
    const h=document.createElement('div');h.className='postreply';box.appendChild(h);box=h}
  const back=inline?`<button type="button" class="b postdrop" data-close="1">✕ ${esc(t('Verwerfen','Discard'))}</button>`
    :postOut('Verwerfen','Discard');
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
      (f.reply?postSugBox(f):'')+
      `<label>${esc(t('Text','Text'))}</label><textarea data-f="text" rows="9" maxlength="20000"></textarea>`+
      (f.reply?`<div class="row posttone">${POST_TONE.map(([a,de,en])=>`<button class="b" type="button" data-r="${a}">${esc(t(de,en))}</button>`).join('')}</div>`:'')+
      `<div class="row postord"><button class="b p" type="button" data-s="prev">${esc(t('Vorschau','Preview'))}</button></div><div class="postordmsg fh">${esc(t('Erst die Vorschau zeigt, was rausgeht. Gesendet wird nur dort.','Only the preview shows what goes out. It is sent only there.'))}</div></div>`;
    for(const k of ['to','cc','subject','text']){const el=box.querySelector(`[data-f=${k}]`);el.value=f[k]||'';el.oninput=()=>{f[k]=el.value}}
    const ac=box.querySelector('[data-f=account]');if(ac)ac.onchange=()=>{f.account=ac.value};
    if(f.reply){postSuggest(f.reply);
      box.querySelectorAll('[data-g]').forEach(b=>b.onclick=()=>{const v=POST.sug[f.reply].items[+b.dataset.g];f.text=v.text;f.picked=+b.dataset.g;postDraw()});
      box.querySelectorAll('[data-r]').forEach(b=>b.onclick=()=>postTone(b.dataset.r,box))}
    box.querySelector('[data-s=prev]').onclick=()=>postPreview(box.querySelector('.postordmsg'));
    if(POST.focus){POST.focus=false;const ta=box.querySelector(f.reply?'[data-f=text]':'[data-f=to]');ta.focus({preventScroll:true});box.scrollIntoView({block:'nearest'})}}
  box.querySelector('[data-close]').onclick=()=>postDrop()}
// leaving the form: what was typed is asked about first, nothing else is lost
function postDrop(all){const f=POST.write;
  if(f&&!POST.prev&&(f.text||'').trim()&&!confirm(t('Den Entwurf verwerfen?','Discard the draft?')))return;
  POST.write=null;POST.prev=null;if(all){POST.sel=null;POST.msg=null}postDraw()}
async function postPreview(msg){const f=POST.write;msg.className='postordmsg fh';msg.textContent=t('Einen Moment …','One moment …');
  const {r,d}=await apiTry('/api/profile/mail/send/preview',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(f)});
  if(!r.ok){msg.className='postordmsg err';msg.textContent=errSay(r.status,d.detail,'');return}
  POST.prev=d;postDraw()}
async function postSend(b,msg){b.disabled=true;msg.className='postordmsg fh';msg.textContent=t('Sende …','Sending …');
  const {r,d}=await apiTry('/api/profile/mail/send',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({token:POST.prev.token})});
  if(!r.ok){b.disabled=false;msg.className='postordmsg err';msg.textContent=errSay(r.status,d.detail,'');if(r.status===409){POST.prev=null;setTimeout(postDraw,1500)}return}
  POST.sent=t('Gesendet an ','Sent to ')+d.sent+(d.sent===1?t(' Empfänger',' recipient'):t(' Empfänger',' recipients'))+(d.refused?t(', abgelehnt: ',', refused: ')+d.refused:'')+'.';
  POST.write=null;POST.prev=null;postDraw()}
// „Als Termin“: the page Kalender with the subject in „Schnell eintragen“; the panel reads it there by its fixed
// rules, nothing is saved before „Eintragen“
function postAsEvent(m){KAL.q=(m.subject||'').replace(/^(re|aw|antw|fwd?|wg)\s*:\s*/i,'').slice(0,200);KAL.qi=null;KAL.qfocus=true;
  icTabSet('cal','show');goSec('cal')}
// keys on the page (Dominik 2026-10-19 „5a“): J/K next and previous, R reply, E archive, U read or unread, Esc closes
// (the mail, or the form being written)
document.addEventListener('keydown',e=>{if(!$('post')||!$('post').classList.contains('on')||!$('postview'))return;
  if(e.key==='Escape'&&POST.write){e.preventDefault();postDrop();return}   // also from inside the form
  if(/^(INPUT|TEXTAREA|SELECT)$/.test((e.target&&e.target.tagName)||'')||e.metaKey||e.ctrlKey||e.altKey)return;
  const items=(POST.data&&POST.data.items)||[],i=items.findIndex(x=>x.id===POST.sel),k=e.key.toLowerCase();
  if(k==='j'||k==='k'){const n=items[k==='j'?Math.min(i+1,items.length-1):Math.max(i-1,0)];if(n){e.preventDefault();postRead(n.id)}return}
  if(k==='escape'&&POST.sel&&!POST.write){POST.sel=null;POST.msg=null;postDraw();return}
  if(!POST.sel||POST.write)return;
  if(k==='r'&&SEND_ON&&POST.msg&&!POST.msg.err){e.preventDefault();postWrite(POST.msg);return}
  if(!ORD_ON)return;
  if(k==='e'){e.preventDefault();postAct('archive','',null)}
  else if(k==='u'){const x=items[i];if(x){e.preventDefault();postAct(x.unread?'read':'unread','',null)}}});
// a phone: swipe a row left to archive, right for read or unread (only with Mails ordnen)
function postSwipe(r){if(!ORD_ON)return;let x0=0,y0=0,dx=0,on=false;
  r.addEventListener('touchstart',e=>{const p=e.touches[0];x0=p.clientX;y0=p.clientY;dx=0;on=true},{passive:true});
  r.addEventListener('touchmove',e=>{if(!on)return;const p=e.touches[0];dx=p.clientX-x0;
    if(Math.abs(p.clientY-y0)>Math.abs(dx)){on=false;r.style.transform='';return}
    r.style.transform=`translateX(${Math.max(-120,Math.min(120,dx))}px)`;r.classList.toggle('swl',dx<-60);r.classList.toggle('swr',dx>60)},{passive:true});
  r.addEventListener('touchend',()=>{if(!on)return;on=false;r.style.transform='';r.classList.remove('swl','swr');
    if(Math.abs(dx)<80)return;POST.swiped=true;setTimeout(()=>{POST.swiped=false},400);const x=((POST.data&&POST.data.items)||[]).find(i=>i.id===r.dataset.id);if(!x)return;
    postAct(dx<0?'archive':x.unread?'read':'unread','',null,'',x.id)})}
