// E-Mail (Dominik 2026-10-18, plan kalender-mail/plan.md 2a 4a): the profile's mailboxes as a page of its own in the
// menu. „Posteingang“ lists the newest messages of every mailbox (GET /api/profile/mail/inbox) and shows one as plain
// text (GET /api/profile/mail/message, it stays unread); „Einstellungen“ holds everything set up for mail (#mailbox
// with Aufräumen, Mailstil and Pakete in #parbox; pages of Ich until V01.0.807). Sender, subject and text come from
// other people: only through esc(), no HTML, no pictures, no links that open.
const POST={data:null,sel:null,msg:null,q:'',unread:false,seq:0,mseq:0,busy:false,err:''};
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
      if(PAR_ON)lzb($('parbox'),showPar,{auth:true}).catch(()=>{});return b}}]));
  postLoad()}
// the tab „Posteingang“: search, the list, the message tapped
function postBody(){const w=document.createElement('div');w.className='ld-box post';w.id='postview';postPaint(w);return w}
function postDraw(){const w=$('postview');if(w)postPaint(w)}
function postPaint(w){const d=POST.data;w.classList.toggle('ld-sel',!!POST.sel);
  if(d&&d.connected===false){w.innerHTML=`<div class="empty">${esc(t('Noch kein Postfach verbunden. Unter Einstellungen verbindest du iCloud, Gmail, GMX, web.de oder ein anderes IMAP-Postfach.','No mailbox connected yet. Under Settings you connect iCloud, Gmail, GMX, web.de or another IMAP mailbox.'))}<div><button class="b p" type="button" data-k="set">${esc(t('Postfach verbinden','Connect a mailbox'))}</button></div></div>`;
    w.querySelector('[data-k=set]').onclick=()=>{icTabSet('post','set');postOpen()};return}
  if(!w.querySelector('.ld-tools')){
    w.innerHTML=`<div class="ld-tools"><input type="search" data-k="q" placeholder="${esc(t('Absender oder Betreff suchen','Search sender or subject'))}" aria-label="${esc(t('Suchen','Search'))}"><button type="button" class="ld-chip" data-k="unread" aria-pressed="false">${esc(t('Nur ungelesen','Unread only'))}</button><button type="button" class="b" data-k="again">${esc(t('Neu laden','Reload'))}</button></div>`+
      `<div class="postwarn"></div><div class="ld-split"><div class="ld-list"></div><div class="ld-detail postdet" hidden></div></div>`;
    const q=w.querySelector('[data-k=q]');q.value=POST.q;let tm=0;
    q.oninput=()=>{clearTimeout(tm);tm=setTimeout(()=>{POST.q=q.value.trim();POST.sel=null;postLoad()},400)};
    w.querySelector('[data-k=unread]').onclick=()=>{POST.unread=!POST.unread;POST.sel=null;postLoad()};
    w.querySelector('[data-k=again]').onclick=()=>postLoad()}
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
  postDetail(w)}
// one message: plain text, attachments only named (to Dokumente on request through the assistant)
function postDetail(w){const box=w.querySelector('.postdet'),m=POST.msg;if(!box)return;box.hidden=!POST.sel;if(!POST.sel)return;
  const back=`<button type="button" class="b ld-back" data-close="1">‹ ${esc(t('Zurück','Back'))}</button>`;
  if(!m)box.innerHTML=back+`<div class="mut">${esc(t('Lade die Mail …','Loading the mail …'))}</div>`;
  else if(m.err)box.innerHTML=back+`<div class="note warn">${esc(m.err)}</div>`;
  else box.innerHTML=back+`<h3>${esc(m.subject||t('(ohne Betreff)','(no subject)'))}</h3>`+
    `<dl class="ld-facts"><dt>${esc(t('Von','From'))}</dt><dd>${esc(m.from)}</dd>${m.to?`<dt>${esc(t('An','To'))}</dt><dd>${esc(m.to)}</dd>`:''}<dt>${esc(t('Wann','When'))}</dt><dd>${esc(new Date(m.date*1000).toLocaleString(kalLoc(),{weekday:'short',day:'numeric',month:'long',hour:'2-digit',minute:'2-digit'}))}</dd>`+
    (m.files&&m.files.length?`<dt>${esc(t('Anhänge','Attachments'))}</dt><dd>${esc(m.files.join(', '))}</dd>`:'')+`</dl>`+
    `<div class="posttext">${esc(m.text||t('(kein Text)','(no text)'))}</div>`+
    `<div class="fh">${esc(t('Nur als Text, Bilder und Links von außen sind aus. Antworten geht mit dem Assistenten: „Antworte Anna …“.','Text only, pictures and links from outside stay off. Reply with the assistant: "Reply to Anna …".'))}</div>`;
  box.querySelector('[data-close]').onclick=()=>{POST.sel=null;POST.msg=null;postDraw()}}
