// E-Mail (Dominik 2026-10-18, plan kalender-mail/plan.md 2a 4a): the profile's mailboxes as a page of its own in the
// menu. „Posteingang“ lists the newest messages of every mailbox (GET /api/profile/mail/inbox) and shows one as plain
// text (GET /api/profile/mail/message, it stays unread); „Einstellungen“ holds everything set up for mail (#mailbox
// with Aufräumen, Mailstil and Pakete in #parbox; pages of Ich until V01.0.807). Sender, subject and text come from
// other people: only through esc(), no HTML, no pictures, no links that open.
const POST={data:null,sel:null,msg:null,q:'',chips:{},unread:false,seq:0,mseq:0,busy:false,err:'',done:null,folders:{},write:null,prev:null,sent:'',accts:null,sug:{},
  box:null,tree:null,treeOpen:false,pick:[]};
// Ordner (Mailclient Stufe A, Dominik 2026-10-19 „1a 4a“, postfach.py, with Mails ordnen): box null = the inbox of every
// mailbox, else {account, folder, name} of one folder; tree = GET /api/profile/mail/tree; pick = ids of the Mehrfachauswahl
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
  try{const d=await (await api(POST.box?'/api/profile/mail/folder?'+new URLSearchParams({account:POST.box.account,folder:POST.box.folder,q:postQ()})
      :'/api/profile/mail/inbox?'+new URLSearchParams({q:postQ(),unread:POST.unread?'true':'false'}))).json();
    if(seq!==POST.seq)return;if(!(d.loading&&POST.data&&again))POST.data=d;POST.err='';
    if(d.loading&&POST.tries<5)setTimeout(()=>{if(seq===POST.seq&&$('postview'))postLoad(true)},3000)}
  catch(e){if(seq!==POST.seq)return;POST.err=e.message||t('Nicht erreicht','Not reached')}
  POST.busy=false;postDraw();postFuerLoad()}
async function postRead(id){POST.sel=id;POST.msg=null;if(POST.sug[id]&&POST.sug[id].err)delete POST.sug[id];const seq=++POST.mseq;postDraw();
  try{const m=await (await api('/api/profile/mail/message?'+new URLSearchParams(POST.box?{id,folder:POST.box.folder}:{id}))).json();if(seq===POST.mseq)POST.msg=m}
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
    // „Regeln“ (mailregeln.py, Mailclient Stufe B): own rules, ordered, with a dry run; with Mails ordnen
    ...(OWN_PAGES.mailbox[3][1][2]()?[{k:'regeln',label:OWN_PAGES.mailbox[3][1][1],body:()=>{const b=document.createElement('div');b.className='ld-box postrules';b.id='postrules';postRulesPaint(b);postRulesLoad();return b}}]:[]),
    {k:'set',label:t('Einstellungen','Settings'),body:()=>{const b=$('mailbox');b.hidden=false;$('parwrap').hidden=!PAR_ON;
      lzb(b,async()=>{await showMail();await Promise.all([showMailTidy().catch(()=>{}),showMailStil().catch(()=>{})])},{auth:true}).catch(()=>{});
      proIn('promail').catch(()=>{});if(PAR_ON)lzb($('parbox'),showPar,{auth:true}).catch(()=>{});return b}}]));
  postLoad()}
// the tab „Posteingang“: search, the list, the message tapped
function postBody(){const w=document.createElement('div');w.className='ld-box ld-frame post';w.id='postview';postPaint(w);return w}
function postDraw(){const w=$('postview');if(w)postPaint(w)}
function postPaint(w){const d=POST.data;w.classList.toggle('ld-sel',!!POST.sel||!!POST.write);
  if(d&&d.connected===false){w.innerHTML=`<div class="empty">${esc(t('Noch kein Postfach verbunden. Unter Einstellungen verbindest du iCloud, Gmail, GMX, web.de oder ein anderes IMAP-Postfach.','No mailbox connected yet. Under Settings you connect iCloud, Gmail, GMX, web.de or another IMAP mailbox.'))}<div><button class="b p" type="button" data-k="set">${esc(t('Postfach verbinden','Connect a mailbox'))}</button></div></div>`;
    w.querySelector('[data-k=set]').onclick=()=>{icTabSet('post','set');postOpen()};return}
  if(!w.querySelector('.ld-tools')){
    w.innerHTML=`<div class="ld-tools"><input type="search" data-k="q" placeholder="${esc(t('Suchen, auch von: betreff: hat:anhang','Search, also from: subject: has:attachment'))}" aria-label="${esc(t('Suchen','Search'))}">${POST_CHIPS.map(c=>`<button type="button" class="ld-chip" data-chip="${c[0]}" aria-pressed="false">${esc(t(c[2],c[3]))}</button>`).join('')}${ORD_ON?`<button type="button" class="ld-chip" data-k="tree" aria-expanded="false"></button>`:''}<button type="button" class="ld-chip" data-k="unread" aria-pressed="false">${esc(t('Nur ungelesen','Unread only'))}</button>${SEND_ON?`<button type="button" class="b p" data-k="new">${esc(t('Neue Mail','New mail'))}</button>`:''}<button type="button" class="b" data-k="again">${esc(t('Neu laden','Reload'))}</button></div>`+
      `<div class="postwarn"></div><div class="postundo"></div><div class="ld-split"><div class="ld-list"></div><div class="ld-detail postdet" hidden></div></div>`;
    const q=w.querySelector('[data-k=q]');q.value=POST.q;let tm=0;
    q.oninput=()=>{clearTimeout(tm);tm=setTimeout(()=>{POST.q=q.value.trim();POST.sel=null;postLoad()},400)};
    w.querySelectorAll('[data-chip]').forEach(b=>b.onclick=()=>{POST.chips[b.dataset.chip]=!POST.chips[b.dataset.chip];POST.sel=null;postLoad()});
    w.querySelector('[data-k=unread]').onclick=()=>{POST.unread=!POST.unread;POST.sel=null;postLoad()};
    const tr=w.querySelector('[data-k=tree]');if(tr)tr.onclick=()=>{POST.treeOpen=!POST.treeOpen;if(POST.treeOpen)postTreeLoad();postDraw()};
    w.querySelector('[data-k=again]').onclick=()=>postLoad();
    const nw=w.querySelector('[data-k=new]');if(nw)nw.onclick=()=>postWrite(null)}
  const u=w.querySelector('[data-k=unread]');u.classList.toggle('on',POST.unread);u.setAttribute('aria-pressed',String(POST.unread));
  w.querySelectorAll('[data-chip]').forEach(b=>{const on=!!POST.chips[b.dataset.chip];b.classList.toggle('on',on);b.setAttribute('aria-pressed',String(on))});
  const tr=w.querySelector('[data-k=tree]');if(tr){tr.textContent='📁 '+(POST.box?POST.box.name:t('Posteingang','Inbox'))+' ▾';tr.classList.toggle('on',POST.treeOpen);tr.setAttribute('aria-expanded',String(POST.treeOpen))}
  w.querySelector('.postwarn').innerHTML=(POST.err?`<div class="note warn">${esc(t('Die Mails kamen nicht an: ','The mail did not arrive: ')+POST.err)}</div>`:'')+
    (d&&d.errors&&d.errors.length?`<div class="note warn">${esc(t('Nicht erreicht: ','Not reached: ')+d.errors.join(', '))}</div>`:'')+
    (d&&d.loading?`<div class="note">${esc(t('Die Postfächer laden noch …','The mailboxes are still loading …'))}</div>`:'');
  const many=d&&d.boxes&&d.boxes.length>1,items=postItems(),list=w.querySelector('.ld-list');
  list.classList.toggle('busy',POST.busy);
  // the folder tree takes the list's place (one bar per area: no box of its own inside the list)
  if(POST.treeOpen){list.innerHTML=postTreeHtml();postTreeBind(list);postUndo(w);postDetail(w);return}
  let day='';
  list.innerHTML=items.map(x=>{const g=postDay(x.date),head=g!==day?`<div class="ld-grp"><span>${esc(g)}</span></div>`:'';day=g;const fd=postFuer(x);
    return head+`<div class="ld-row${POST.sel===x.id?' on':''}${x.unread?' unread':''}" role="button" tabindex="0" data-id="${esc(x.id)}"${ORD_ON&&postMovable()?' draggable="true"':''}>`+
      (ORD_ON?`<input type="checkbox" class="ld-pick" data-pick="${esc(x.id)}" aria-label="${esc(t('Auswählen','Select'))}"${POST.pick.includes(x.id)?' checked':''}>`:'')+
      `<span class="postdot" aria-label="${esc(x.unread?t('ungelesen','unread'):'')}"></span><span class="postav ${postKc(x.from)}" aria-hidden="true">${esc(postInit(x.from))}</span><span class="ld-mid"><b>${esc(postName(x.from))}</b><small>${esc(x.subject||t('(ohne Betreff)','(no subject)'))}</small>${fd?`<span class="postfd${fd.urgent?' hot':''}">${esc(FUER_KIND[fd.kind]||fd.kind)}</span>`:''}</span>`+
      `<span class="ld-right">${x.attach?`<span class="ld-badge off" aria-label="${esc(t('mit Anhang','with attachment'))}">📎</span>`:''}${x.flagged?`<span class="ld-badge due" aria-label="${esc(t('markiert','flagged'))}">★</span>`:''}${many?`<span class="ld-badge off">${esc(d.boxes[x.box]||'')}</span>`:''}<span class="ld-when">${esc(postWhen(x.date))}</span></span></div>`}).join('')
    ||(POST.busy?'':`<div class="ld-empty mut">${esc(POST.box?(postQ()?t('Keine passende Mail in diesem Ordner.','No matching mail in this folder.'):t('Dieser Ordner ist leer.','This folder is empty.'))
      :postQ()||POST.unread?t('Keine passende Mail in den letzten 14 Tagen.','No matching mail in the last 14 days.'):t('Keine Mail in den letzten 14 Tagen.','No mail in the last 14 days.'))}</div>`);
  list.querySelectorAll('[data-pick]').forEach(c=>{c.onclick=e=>e.stopPropagation();c.onchange=()=>{const id=c.dataset.pick;
    POST.pick=c.checked?[...POST.pick,id].slice(-50):POST.pick.filter(x=>x!==id);postUndo(w)}});
  list.querySelectorAll('[data-id]').forEach(r=>{r.onclick=()=>{if(POST.swiped){POST.swiped=false;return}postRead(r.dataset.id)};r.onkeydown=e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();postRead(r.dataset.id)}};postSwipe(r);if(r.draggable)postDrag(r,w)});
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
    (m.files&&m.files.length?`<dt>${esc(t('Anhänge','Attachments'))}</dt><dd>${ORD_ON&&m.parts&&m.parts.length?m.parts.map(f=>`<a class="ld-chip" download href="/api/profile/mail/file?${esc(new URLSearchParams({id:POST.sel,folder:postSrc(),n:f.n}).toString())}">⬇ ${esc(f.name)} (${f.kb} KB)</a>`).join(' '):esc(m.files.join(', '))}</dd>`:'')+`</dl>`+
    `<div class="posttext">${esc(m.text||t('(kein Text)','(no text)'))}</div>`+
    `<div class="fh">${esc(t('Nur als Text, Bilder und Links von außen sind aus.','Text only, pictures and links from outside stay off.')+' '+(SEND_ON?'':t('Antworten geht mit dem Assistenten: „Antworte Anna …“.','Reply with the assistant: "Reply to Anna …".'))+(NARROW()?'':' '+t('Tasten: J und K blättern','Keys: J and K browse')+(SEND_ON?t(', R antwortet',', R replies'):'')+(ORD_ON?t(', E archiviert, U gelesen oder ungelesen',', E archives, U read or unread'):'')+'.'))}</div>`+
    (!m.err&&(SEND_ON||(typeof CAL_ON!=='undefined'&&CAL_ON))?`<div class="row postwr">${SEND_ON?`<button class="b p" type="button" data-w="reply">${esc(t('Antworten','Reply'))}</button><button class="b" type="button" data-w="fwd">${esc(t('Weiterleiten','Forward'))}</button>`:''}${typeof CAL_ON!=='undefined'&&CAL_ON?`<button class="b" type="button" data-w="cal">${esc(t('Als Termin','As appointment'))}</button>`:''}</div>`:'')+
    (ORD_ON&&!m.err?postOrder()+`<div class="row postord"><button class="b" type="button" data-w="rule">${esc(t('⚙ Regel daraus …','⚙ Rule from this …'))}</button></div>`:'');
  box.querySelector('[data-close]').onclick=()=>{POST.sel=null;POST.msg=null;postDraw()};
  const rp=box.querySelector('[data-w=reply]');if(rp)rp.onclick=()=>postWrite(m);
  const fw=box.querySelector('[data-w=fwd]');if(fw)fw.onclick=()=>postWrite(m,true);
  const ac=box.querySelector('[data-w=cal]');if(ac)ac.onclick=()=>postAsEvent(m);
  const ru=box.querySelector('[data-w=rule]');if(ru)ru.onclick=()=>postRuleFrom(m);
  if(ORD_ON&&m&&!m.err)postOrderBind(box)}
// the buttons below a message: never delete, every move can go back right after
const postSrc=()=>POST.box?POST.box.folder:'INBOX';
// what the folder's role allows: moved out only of the inbox, an own folder or the archive (postfach._source)
const postMovable=()=>!POST.box||['folder','archive'].includes(POST.box.role);
function postOrder(){const x=postItems().find(i=>i.id===POST.sel),f=POST.folders[POST.sel.split(':')[0]],src=postSrc();
  const into=(f&&f.folders||[]).filter(n=>n!==src);if(POST.box)into.unshift('INBOX');
  return `<div class="row postord"><button class="b" type="button" data-o="${x&&x.unread?'read':'unread'}">${esc(x&&x.unread?t('Als gelesen markieren','Mark as read'):t('Als ungelesen markieren','Mark as unread'))}</button>`+
    `<button class="b" type="button" data-o="${x&&x.flagged?'unflag':'flag'}">${esc(x&&x.flagged?t('Markierung weg','Unflag'):t('★ Markieren','★ Flag'))}</button>`+
    (postMovable()&&!(f&&f.archive===src)?`<button class="b" type="button" data-o="archive">${esc(t('Archivieren','Archive'))}</button>`:'')+
    (postMovable()?`<select data-o="folder" aria-label="${esc(t('Verschieben nach','Move to'))}"><option value="">${esc(t('Verschieben nach …','Move to …'))}</option>${into.map(n=>`<option value="${esc(n)}">${esc(n==='INBOX'?t('Posteingang','Inbox'):n)}</option>`).join('')}</select>`:'')+
    `</div><div class="postordmsg fh"></div>`}
async function postFoldersFor(acct){if(!POST.folders[acct]){const {r,d}=await apiTry('/api/profile/mail/folders?'+new URLSearchParams({account:acct}));if(r.ok)POST.folders[acct]=d;return r.ok}return false}
async function postOrderBind(box){const acct=POST.sel.split(':')[0],sel=box.querySelector('select[data-o=folder]'),msg=box.querySelector('.postordmsg');
  if(await postFoldersFor(acct)&&$('postview'))postDetail($('postview'));
  box.querySelectorAll('button[data-o]').forEach(b=>b.onclick=()=>postAct(b.dataset.o,'',msg));
  if(sel)sel.onchange=()=>{if(sel.value)postAct('move',sel.value,msg)}}
async function postAct(action,folder,msg,mid,which){const id=which||POST.sel,src=postSrc();if(msg){msg.className='postordmsg fh';msg.textContent=t('Einen Moment …','One moment …')}
  const {r,d}=await apiTry('/api/profile/mail/act',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id,action,folder,mid:mid||'',src})});
  if(!r.ok){if(msg){msg.className='postordmsg err';msg.textContent=errSay(r.status,d.detail,'')}else{POST.err=errSay(r.status,d.detail,'');postDraw()}return}
  const x=POST.data.items.find(i=>i.id===id);
  if(action==='read'||action==='unread'){if(x)x.unread=action==='unread';postDraw();return}
  if(action==='flag'||action==='unflag'){if(x)x.flagged=action==='flag';postDraw();return}
  // archived or moved: off the list, with „Rückgängig“ for a while
  POST.done={id,acct:id.split(':')[0],mid:d.mid,folder:d.folder,src};if(POST.sel===id){POST.sel=null;POST.msg=null}
  POST.pick=POST.pick.filter(i=>i!==id);POST.tree=null;POST.data.items=POST.data.items.filter(i=>i.id!==id);postDraw()}
// the list as shown: in a folder the search and „Nur ungelesen“ work on the listing (the inbox asks the server)
// the server searches (mail._words: von:, betreff:, hat:anhang, ist:markiert); in a folder „Nur ungelesen“ is ist:ungelesen
function postItems(){return (POST.data&&POST.data.items)||[]}
const POST_CHIPS=[['flag','ist:markiert','★ Markiert','★ Flagged'],['attach','hat:anhang','📎 Anhang','📎 Attachment']];
function postQ(){return [POST.q,...POST_CHIPS.filter(c=>POST.chips[c[0]]).map(c=>c[1]),POST.box&&POST.unread?'ist:ungelesen':''].filter(Boolean).join(' ').slice(0,100)}
function postUndo(w){const u=POST.done,box=w.querySelector('.postundo');if(!box)return;
  const pick=ORD_ON&&POST.pick.length&&!POST.treeOpen?postPickBar():'';
  if(!u){box.innerHTML=pick;postPickBind(box);return}
  box.innerHTML=`<div class="note">${esc((u.n>1?t(u.n+' Mails verschoben nach ',u.n+' mails moved to '):t('Verschoben nach ','Moved to '))+(u.folder==='INBOX'?t('Posteingang','Inbox'):u.folder)+'.')} <button class="b" type="button" data-u="1">${esc(t('Rückgängig','Undo'))}</button></div>`+pick;
  postPickBind(box);
  box.querySelector('[data-u]').onclick=async()=>{const {r,d}=u.mids?await apiTry('/api/profile/mail/acts/back',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({account:u.acct,folder:u.folder,mids:u.mids,src:u.src})})
      :await apiTry('/api/profile/mail/act',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id:u.acct+':0',action:'back',folder:u.folder,mid:u.mid,src:u.src})});
    POST.done=null;if(!r.ok){box.innerHTML=`<div class="note warn">${esc(errSay(r.status,d.detail,''))}</div>`;return}POST.tree=null;postLoad()}}
// Mehrfachauswahl: the bar above the list while messages are ticked; a move goes into a folder of one mailbox
function postPickBar(){const accts=[...new Set(POST.pick.map(i=>i.split(':')[0]))],f=accts.length===1?POST.folders[accts[0]]:null,src=postSrc();
  const into=(f&&f.folders||[]).filter(n=>n!==src);if(POST.box)into.unshift('INBOX');
  return `<div class="row postord postpick"><b>${esc(POST.pick.length+' '+t('gewählt','selected'))}</b>`+
    ['read','unread','flag'].map(a=>`<button class="b" type="button" data-m="${a}">${esc({read:t('Gelesen','Read'),unread:t('Ungelesen','Unread'),flag:t('★ Markieren','★ Flag')}[a])}</button>`).join('')+
    (postMovable()?`<button class="b" type="button" data-m="archive">${esc(t('Archivieren','Archive'))}</button>`:'')+
    (postMovable()&&accts.length===1?`<select data-m="move" aria-label="${esc(t('Verschieben nach','Move to'))}"><option value="">${esc(t('Verschieben nach …','Move to …'))}</option>${into.map(n=>`<option value="${esc(n)}">${esc(n==='INBOX'?t('Posteingang','Inbox'):n)}</option>`).join('')}</select>`:'')+
    `<button class="b" type="button" data-m="none">${esc(t('Auswahl aufheben','Clear selection'))}</button></div><div class="postordmsg fh"></div>`}
function postPickBind(box){const bar=box.querySelector('.postpick');if(!bar)return;const msg=box.querySelector('.postordmsg'),accts=[...new Set(POST.pick.map(i=>i.split(':')[0]))];
  if(accts.length===1&&!POST.folders[accts[0]])postFoldersFor(accts[0]).then(ok=>{if(ok)postDraw()});
  bar.querySelectorAll('button[data-m]').forEach(b=>b.onclick=()=>b.dataset.m==='none'?(POST.pick=[],postDraw()):postMany(b.dataset.m,'',msg));
  const sel=bar.querySelector('select[data-m]');if(sel)sel.onchange=()=>{if(sel.value)postMany('move',sel.value,msg)}}
async function postMany(action,folder,msg){const ids=POST.pick.slice(),src=postSrc();msg.className='postordmsg fh';msg.textContent=t('Einen Moment …','One moment …');
  const {r,d}=await apiTry('/api/profile/mail/acts',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({ids,action,folder,src})});
  if(!r.ok){msg.className='postordmsg err';msg.textContent=errSay(r.status,d.detail,'');return}
  POST.pick=[];const items=POST.data.items;
  if(action==='archive'||action==='move'){POST.data.items=items.filter(i=>!ids.includes(i.id));if(ids.includes(POST.sel)){POST.sel=null;POST.msg=null}
    const m=d.moved&&d.moved[0];POST.done=m&&d.moved.length===1?{acct:m.acct,mids:m.mids,folder:d.folder,src,n:d.n}:null;POST.tree=null}
  else for(const x of items)if(ids.includes(x.id)){if(action==='flag')x.flagged=true;else x.unread=action==='unread'}
  postDraw()}
// Ordner: the folders of every mailbox in the list's place; tap opens one, own folders can be renamed or removed
const POST_ICON={inbox:'📥',sent:'📤',drafts:'📝',archive:'🗄',trash:'🗑',junk:'⚠',all:'📂',group:'📁',folder:'📁'};
async function postTreeLoad(fresh){if(POST.tree&&!fresh)return;POST.treeBusy=true;
  const {r,d}=await apiTry('/api/profile/mail/tree'+(fresh?'?fresh=true':''));POST.treeBusy=false;
  POST.tree=r.ok?d:{err:errSay(r.status,d.detail,'')};postDraw()}
function postTreeHtml(){const tr=POST.tree;
  if(!tr||POST.treeBusy)return `<div class="ld-empty mut">${esc(t('Lade die Ordner …','Loading the folders …'))}</div>`;
  if(tr.err)return `<div class="note warn">${esc(tr.err)}</div>`;
  const row=(on,data,ico,name,badge,more)=>`<div class="ld-row${on?' on':''}" role="button" tabindex="0" ${data}><span class="ld-ico" aria-hidden="true">${ico}</span><span class="ld-mid"><b>${esc(name)}</b></span><span class="ld-right">${badge}${more}</span></div>`;
  return row(!POST.box,'data-all="1"','📥',t('Alle Posteingänge','All inboxes'),'','')+
    tr.accounts.map(a=>`<div class="ld-grp"><span>${esc(a.name)}</span><button type="button" class="ld-chip" data-new="${esc(a.id)}">${esc(t('+ Neuer Ordner','+ New folder'))}</button></div>`+
      (a.error?`<div class="note warn">${esc(t('Dieses Postfach war nicht erreichbar.','This mailbox was not reachable.'))}</div>`:'')+
      a.folders.map(f=>{const name=f.name==='INBOX'?t('Posteingang','Inbox'):f.name.split(a.delim).pop(),pad=f.depth?` style="padding-left:${8+f.depth*18}px"`:'';
        const menu=POST.fmenu===a.id+'|'+f.name?`<div class="row postord"><button class="b" type="button" data-fo="rename" data-fa2="${esc(a.id)}" data-ff2="${esc(f.name)}">${esc(t('Umbenennen','Rename'))}</button><button class="b" type="button" data-fo="new" data-fa2="${esc(a.id)}" data-ff2="${esc(f.name)}">${esc(t('Ordner darin','Folder inside'))}</button><button class="b" type="button" data-fo="remove" data-fa2="${esc(a.id)}" data-ff2="${esc(f.name)}">${esc(t('Entfernen (nur leer)','Remove (empty only)'))}</button></div>`:'';
        return row(POST.box&&POST.box.account===a.id&&POST.box.folder===f.name,(f.role==='group'?'':`data-acct="${esc(a.id)}" data-f="${esc(f.name)}" data-role="${esc(f.role)}"`)+pad,POST_ICON[f.role]||'📁',name,
          f.unseen?`<span class="ld-badge read">${f.unseen}</span>`:'',
          f.own?`<button type="button" class="ld-chip" data-fa="${esc(a.id)}" data-ff="${esc(f.name)}" aria-label="${esc(t('Ordner bearbeiten','Edit folder'))}" aria-expanded="${POST.fmenu===a.id+'|'+f.name}">⋯</button>`:'')+menu}).join('')).join('')+
    `<div class="fh">${esc(t('Eigene Ordner: ⋯ zum Umbenennen, für einen Ordner darin oder zum Entfernen (nur leere). Ordner des Mail-Programms und von „Mails aufräumen“ bleiben, wie sie sind; gelöscht wird nie eine Mail.','Own folders: ⋯ to rename, for a folder inside or to remove (empty ones only). Folders of the mail program and of "Tidy mails" stay as they are; a mail is never deleted.'))}</div>`}
function postTreeBind(list){
  const open=x=>{POST.box=x;POST.treeOpen=false;POST.sel=null;POST.msg=null;POST.pick=[];POST.done=null;POST.data=null;postLoad()};
  list.querySelectorAll('[data-all]').forEach(r=>r.onclick=()=>open(null));
  list.querySelectorAll('[data-f]').forEach(r=>{const go=()=>open({account:r.dataset.acct,folder:r.dataset.f,role:r.dataset.role,name:r.querySelector('b').textContent});
    r.onclick=e=>{if(e.target.closest('[data-fa]'))return;go()};r.onkeydown=e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();go()}}});
  list.querySelectorAll('[data-new]').forEach(b=>b.onclick=()=>postFolderNew(b.dataset.new,''));
  list.querySelectorAll('[data-fa]').forEach(b=>b.onclick=e=>{e.stopPropagation();const k=b.dataset.fa+'|'+b.dataset.ff;POST.fmenu=POST.fmenu===k?null:k;postDraw()});
  list.querySelectorAll('[data-fo]').forEach(b=>b.onclick=()=>postFolderDo(b.dataset.fo,b.dataset.fa2,b.dataset.ff2))}
async function postFolderCall(path,body){const {r,d}=await apiTry(path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
  if(!r.ok){alert(errSay(r.status,d.detail,''));return null}delete POST.folders[body.account];await postTreeLoad(true);return d}
async function postFolderNew(acct,inside){const n=(prompt(inside?t('Name des neuen Ordners in „'+inside+'“:','Name of the new folder inside "'+inside+'":'):t('Name des neuen Ordners:','Name of the new folder:'))||'').trim();
  if(n)await postFolderCall('/api/profile/mail/folder/new',{account:acct,folder:inside,name:n})}
async function postFolderDo(op,acct,f){POST.fmenu=null;
  if(op==='new')return postFolderNew(acct,f);
  if(op==='rename'){const n=(prompt(t('Neuer Name für „'+f+'“:','New name for "'+f+'":'),f.split(/[/.]/).pop())||'').trim();
    if(n){const d=await postFolderCall('/api/profile/mail/folder/rename',{account:acct,folder:f,name:n});if(d&&POST.box&&POST.box.folder===f){POST.box.folder=d.folder;POST.box.name=n;postDraw()}}return}
  if(op==='remove'&&confirm(t('Den leeren Ordner „'+f+'“ entfernen? Mails werden nie gelöscht: einen Ordner mit Mails lässt der Spark stehen.','Remove the empty folder "'+f+'"? Mails are never deleted: a folder holding mails stays.'))){
    const d=await postFolderCall('/api/profile/mail/folder/remove',{account:acct,folder:f});if(d&&POST.box&&POST.box.folder===f){POST.box=null;postLoad()}}
  else postDraw()}
// Mails senden: the form (new mail, or the answer to the mail shown), then the preview sheet from the server;
// only „Senden“ on the sheet sends (POST /api/profile/mail/send with its token). Nothing goes out from the form.
const postAddr=f=>{const m=/<([^>]+)>\s*$/.exec(f||'');return (m?m[1]:f||'').trim()};
// Weiterleiten (Mailclient Stufe C): the recipients typed, the original goes below the own words (senden._forward)
async function postWrite(m,fwd){POST.sent='';POST.prev=null;
  POST.write=m&&fwd?{reply:'',forward:POST.sel,folder:postSrc(),files:!!(m.files&&m.files.length),to:'',cc:'',subject:/^(fwd?|wg)\s*:/i.test(m.subject||'')?m.subject:'Fwd: '+(m.subject||''),text:'',account:''}
    :m?{reply:POST.sel,to:postAddr(m.from),cc:'',subject:/^(re|aw|antw)\s*:/i.test(m.subject||'')?m.subject:'Re: '+(m.subject||''),text:'',account:''}
    :{reply:'',to:'',cc:'',subject:'',text:'',account:''};
  if(!m&&!POST.accts){const {r,d}=await apiTry('/api/profile/mail');POST.accts=r.ok?(d.accounts||[]):[]}
  if(!m&&POST.accts&&POST.accts.length)POST.write.account=POST.accts[0].id;POST.focus=true;postDraw()}
// Ziehen in einen Ordner (am Rechner): while a row (or the ticked ones) is dragged, the folders of its mailbox stand
// above the list; dropping there is the same move as the button, with „Rückgängig“
function postDrag(r,w){r.ondragstart=async e=>{const id=r.dataset.id,ids=POST.pick.includes(id)?POST.pick.slice():[id],acct=id.split(':')[0];
    if(ids.some(i=>i.split(':')[0]!==acct))return;e.dataTransfer.setData('text/plain',ids.length+'');e.dataTransfer.effectAllowed='move';
    await postFoldersFor(acct);const f=POST.folders[acct],bar=document.createElement('div');bar.className='postdropbar note';
    const src=postSrc(),targets=(f&&f.folders||[]).filter(x=>x!==src).slice(0,12);
    bar.innerHTML=esc(t('Hierher ziehen: ','Drop here: '))+(src!=='INBOX'?`<span class="ld-chip" data-drop="INBOX">${esc(t('Posteingang','Inbox'))}</span>`:'')+
      targets.map(x=>`<span class="ld-chip" data-drop="${esc(x)}">${esc(x)}</span>`).join(' ');
    const old=w.querySelector('.postdropbar');if(old)old.remove();w.querySelector('.postundo').before(bar);
    bar.querySelectorAll('[data-drop]').forEach(c=>{c.ondragover=ev=>{ev.preventDefault();c.classList.add('on')};c.ondragleave=()=>c.classList.remove('on');
      c.ondrop=ev=>{ev.preventDefault();bar.remove();const msg=document.createElement('div');msg.className='postordmsg fh';w.querySelector('.postundo').appendChild(msg);
        if(ids.length>1){POST.pick=ids;postMany('move',c.dataset.drop,msg)}else postAct('move',c.dataset.drop,msg,'',ids[0])}})};
  r.ondragend=()=>setTimeout(()=>{const b=w.querySelector('.postdropbar');if(b)b.remove()},300)}
// a reply opens below the mail it answers, like a mail client (Dominik 2026-10-19); a new mail fills the pane
function postWriteBox(w){let box=w.querySelector('.postdet');const f=POST.write,p=POST.prev;if(!box)return;box.hidden=false;
  const inline=!!(f.reply&&POST.sel===f.reply&&POST.msg&&!POST.msg.err);
  if(inline){postDetail(w);const rp=box.querySelector('[data-w=reply]');if(rp)rp.remove();
    box.querySelector('.ld-back').onclick=()=>postDrop(true);
    const h=document.createElement('div');h.className='postreply';box.appendChild(h);box=h}
  const back=inline?`<button type="button" class="b postdrop" data-close="1">✕ ${esc(t('Verwerfen','Discard'))}</button>`
    :postOut('Verwerfen','Discard');
  if(p){box.innerHTML=back+`<h3>${esc(t('So geht die Mail raus','This is the mail that goes out'))}</h3><dl class="ld-facts postprev">`+
      `<dt>${esc(t('Von','From'))}</dt><dd>${esc(p.from)}</dd>${p.server?`<dt>${esc(t('Über','Via'))}</dt><dd>${esc(p.server)}</dd>`:''}<dt>${esc(t('An','To'))}</dt><dd>${esc(p.to.join(', '))}</dd>`+
      (p.cc.length?`<dt>${esc(t('Kopie','Copy'))}</dt><dd>${esc(p.cc.join(', '))}</dd>`:'')+`<dt>${esc(t('Betreff','Subject'))}</dt><dd>${esc(p.subject||t('(ohne Betreff)','(no subject)'))}</dd>`+
      (p.files&&p.files.length?`<dt>${esc(t('Anhänge','Attachments'))}</dt><dd>${esc(p.files.join(', '))}</dd>`:'')+`</dl>`+
      `<div class="posttext">${esc(p.text)}</div><div class="row postord"><button class="b p" type="button" data-s="send">${esc(t('Senden','Send'))}</button><button class="b" type="button" data-s="edit">${esc(t('Ändern','Edit'))}</button></div><div class="postordmsg fh"></div>`;
    box.querySelector('[data-s=edit]').onclick=()=>{POST.prev=null;postDraw()};
    box.querySelector('[data-s=send]').onclick=e=>postSend(e.target,box.querySelector('.postordmsg'))}
  else{const many=!f.reply&&!f.forward&&POST.accts&&POST.accts.length>1;
    box.innerHTML=back+`<h3>${esc(f.reply?t('Antworten','Reply'):f.forward?t('Weiterleiten','Forward'):t('Neue Mail','New mail'))}</h3><div class="postform">`+
      (many?`<label>${esc(t('Von','From'))}</label><select data-f="account">${POST.accts.map(a=>`<option value="${esc(a.id)}"${a.id===f.account?' selected':''}>${esc(a.name+' · '+a.user)}</option>`).join('')}</select>`:'')+
      `<label>${esc(t('An','To'))}</label><input data-f="to" type="email" multiple maxlength="2000" autocomplete="off">`+
      `<label>${esc(t('Kopie','Copy'))}</label><input data-f="cc" type="email" multiple maxlength="2000" autocomplete="off">`+
      `<label>${esc(t('Betreff','Subject'))}</label><input data-f="subject" maxlength="200">`+
      (f.reply?postSugBox(f):'')+
      `<label>${esc(t('Text','Text'))}</label><textarea data-f="text" rows="9" maxlength="20000"${f.forward?` placeholder="${esc(t('Deine Zeilen über der weitergeleiteten Mail (darf leer bleiben)','Your lines above the forwarded mail (may stay empty)'))}"`:''}></textarea>`+
      (f.forward&&POST.msg&&POST.msg.files&&POST.msg.files.length?`<label class="chk"><input type="checkbox" data-f="files"${f.files?' checked':''}> ${esc(t('Anhänge mitschicken','Send the attachments along'))} (${esc(POST.msg.files.join(', '))})</label>`:'')+
      (f.reply?`<div class="row posttone">${POST_TONE.map(([a,de,en])=>`<button class="b" type="button" data-r="${a}">${esc(t(de,en))}</button>`).join('')}</div>`:'')+
      `<div class="row postord"><button class="b p" type="button" data-s="prev">${esc(t('Vorschau','Preview'))}</button></div><div class="postordmsg fh">${esc(t('Erst die Vorschau zeigt, was rausgeht. Gesendet wird nur dort.','Only the preview shows what goes out. It is sent only there.'))}</div></div>`;
    for(const k of ['to','cc','subject','text']){const el=box.querySelector(`[data-f=${k}]`);el.value=f[k]||'';el.oninput=()=>{f[k]=el.value}}
    const ac=box.querySelector('[data-f=account]');if(ac)ac.onchange=()=>{f.account=ac.value};
    const fi=box.querySelector('[data-f=files]');if(fi)fi.onchange=()=>{f.files=fi.checked};
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
  const items=postItems(),i=items.findIndex(x=>x.id===POST.sel),k=e.key.toLowerCase();
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
// Regeln (mailregeln.py, Mailclient Stufe B, Dominik 2026-10-19 „2a 3a“): fixed rules the profile makes, the first that
// fits decides; they take new mail only, the mails already there only with „Auch die vorhandenen“ (with the code).
// A rule's words are compared, never run; the Spark checks every rule again (mailregeln.clean).
const RULES={data:null,form:null,msg:'',err:'',test:null,undo:null};
async function postRulesLoad(){const {r,d}=await apiTry('/api/profile/mail/rules');RULES.data=r.ok?d:null;RULES.err=r.ok?'':errSay(r.status,d.detail,'');postRulesDraw()}
const postRulesDraw=()=>{const b=$('postrules');if(b)postRulesPaint(b)};
function postRuleWhen(r){const w=r.when,p=[];if(w.from)p.push((w.from.startsWith('@')?t('Absender endet auf ','Sender ends with '):t('Absender ist ','Sender is '))+w.from);
  if(w.subject)p.push(t('Betreff enthält „','Subject contains "')+w.subject+t('“','"'));if(w.to)p.push(t('an ','to ')+w.to);if(w.attach)p.push(t('mit Anhang','with attachment'));return p.join(t(' und ',' and '))}
function postRuleThen(r){const x=r.then,p=[];if(x.folder)p.push('→ '+x.folder);if(x.read)p.push(t('gelesen','read'));if(x.flag)p.push('★');if(x.quiet)p.push(t('nicht in „Für dich“','not in "For you"'));return p.join(', ')}
function postRulesPaint(b){const d=RULES.data;
  if(RULES.form){postRuleForm(b);return}
  if(!d){b.innerHTML=RULES.err?`<div class="note warn">${esc(RULES.err)}</div>`:`<div class="ld-empty mut">${esc(t('Lade die Regeln …','Loading the rules …'))}</div>`;return}
  const rows=d.rules.map((r,i)=>`<div class="ld-row" data-rid="${esc(r.id)}"><span class="ld-mid"><b>${esc(postRuleWhen(r))}</b><small>${esc(postRuleThen(r)+(r.box?' · '+r.box:''))}</small></span>`+
    `<span class="ld-right"><span class="ld-badge ${r.on===false?'off':'read'}">${esc(r.on===false?t('pausiert','paused'):t('diesen Monat ','this month ')+r.month)}</span>`+
    `<button class="ld-chip" type="button" data-up="${i}" aria-label="${esc(t('nach oben','up'))}"${i?'':' disabled'}>▲</button><button class="ld-chip" type="button" data-on="${esc(r.id)}">${esc(r.on===false?t('Weiter','Resume'):t('Pause','Pause'))}</button>`+
    `<button class="ld-chip" type="button" data-ed="${esc(r.id)}">${esc(t('Ändern','Edit'))}</button><button class="ld-chip" type="button" data-del="${esc(r.id)}">${esc(t('Löschen','Delete'))}</button></span></div>`).join('');
  b.innerHTML=`<div class="ld-tools"><button class="b p" type="button" data-k="new">${esc(t('+ Neue Regel','+ New rule'))}</button></div>`+
    (RULES.msg?`<div class="note">${esc(RULES.msg)}${RULES.undo?` <button class="b" type="button" data-k="undo">${esc(t('Rückgängig','Undo'))}</button>`:''}</div>`:'')+
    (RULES.err?`<div class="note warn">${esc(RULES.err)}</div>`:'')+
    `<div class="ld-list">${rows||`<div class="ld-empty mut">${esc(t('Noch keine Regel. Am schnellsten geht es an einer Mail: „⚙ Regel daraus …“.','No rule yet. Quickest from a mail: "⚙ Rule from this …".'))}</div>`}`+
    (d.tidy&&d.tidy.length?`<div class="ld-grp"><span>${esc(t('Aus „Mails aufräumen“','From "Tidy mails"'))}</span></div>`+d.tidy.map(r=>`<div class="ld-row"><span class="ld-mid"><b>${esc(r.match)}</b><small>${esc(r.keep?t('bleibt im Posteingang','stays in the inbox'):'→ '+r.folder)}</small></span><span class="ld-right"><button class="ld-chip" type="button" data-tdel="${esc(r.id)}">${esc(t('Löschen','Delete'))}</button></span></div>`).join(''):'')+
    `</div><div class="fh">${esc(t('Die erste passende Regel entscheidet (▲ ändert die Reihenfolge). Regeln nehmen neue Mails; gelöscht wird nie eine Mail, nichts kommt in Papierkorb oder Spam.','The first rule that fits decides (▲ changes the order). Rules take new mail; a mail is never deleted, nothing goes into trash or junk.'))}</div>`;
  b.querySelector('[data-k=new]').onclick=()=>{RULES.form={account:(d.accounts[0]||{}).id||'',when:{from:'',subject:'',to:'',attach:false},then:{folder:'',read:false,flag:false,quiet:false}};RULES.test=null;postRulesDraw()};
  const un=b.querySelector('[data-k=undo]');if(un)un.onclick=async()=>{const u=RULES.undo;RULES.undo=null;
    const {r,d:x}=await apiTry('/api/profile/mail/acts/back',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(u)});
    RULES.msg=r.ok?t('Zurück im Posteingang.','Back in the inbox.'):'';RULES.err=r.ok?'':errSay(r.status,x.detail,'');POST.data=null;postRulesDraw()};
  const call=async(path,opt)=>{const {r,d:x}=await apiTry(path,opt);if(!r.ok){RULES.err=errSay(r.status,x.detail,'');postRulesDraw();return}RULES.err='';RULES.msg='';RULES.data=x.rules?x:RULES.data;await postRulesLoad()};
  b.querySelectorAll('[data-del]').forEach(x=>x.onclick=()=>{if(confirm(t('Die Regel löschen? Mails bleiben, wo sie sind.','Delete the rule? Mails stay where they are.')))call('/api/profile/mail/rules/'+encodeURIComponent(x.dataset.del),{method:'DELETE'})});
  b.querySelectorAll('[data-tdel]').forEach(x=>x.onclick=()=>{if(confirm(t('Die Regel von „Mails aufräumen“ löschen?','Delete the rule of "Tidy mails"?')))call('/api/profile/tidy/rules/'+encodeURIComponent(x.dataset.tdel),{method:'DELETE'})});
  b.querySelectorAll('[data-up]').forEach(x=>x.onclick=()=>{const ids=d.rules.map(r=>r.id),i=+x.dataset.up;[ids[i-1],ids[i]]=[ids[i],ids[i-1]];
    call('/api/profile/mail/rules/order',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({ids})})});
  b.querySelectorAll('[data-on]').forEach(x=>x.onclick=()=>{const r=d.rules.find(y=>y.id===x.dataset.on);
    call('/api/profile/mail/rules',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id:r.id,account:r.account,when:r.when,then:r.then,on:r.on===false})})});
  b.querySelectorAll('[data-ed]').forEach(x=>x.onclick=()=>{const r=d.rules.find(y=>y.id===x.dataset.ed);RULES.form=JSON.parse(JSON.stringify({id:r.id,account:r.account,when:r.when,then:r.then,on:r.on}));RULES.test=null;postRulesDraw()})}
// the form: Wenn / Dann; „Probelauf“ counts the inbox mails it fits (nothing changes), „Sichern“ saves
function postRuleForm(b){const f=RULES.form,d=RULES.data||{accounts:[]},fo=f.account&&POST.folders[f.account];
  if(f.account&&!fo)postFoldersFor(f.account).then(ok=>{if(ok)postRulesDraw()});
  b.innerHTML=`<div class="postform"><h3>${esc(f.id?t('Regel ändern','Edit rule'):t('Neue Regel','New rule'))}</h3>`+
    `<label>${esc(t('Postfach','Mailbox'))}</label><select data-f="account"><option value="">${esc(t('Alle Postfächer (ohne Ordner)','All mailboxes (no folder)'))}</option>${d.accounts.map(a=>`<option value="${esc(a.id)}"${a.id===f.account?' selected':''}>${esc(a.name)}</option>`).join('')}</select>`+
    `<div class="ld-grp"><span>${esc(t('Wenn','When'))}</span></div>`+
    `<label>${esc(t('Absender (Adresse oder @domain)','Sender (address or @domain)'))}</label><input data-w="from" maxlength="80" autocomplete="off">`+
    `<label>${esc(t('Betreff enthält','Subject contains'))}</label><input data-w="subject" maxlength="80" autocomplete="off">`+
    `<label>${esc(t('An (Adresse)','To (address)'))}</label><input data-w="to" type="email" maxlength="80" autocomplete="off">`+
    `<label><input type="checkbox" data-w="attach"> ${esc(t('nur mit Anhang','with attachment only'))}</label>`+
    `<div class="ld-grp"><span>${esc(t('Dann','Then'))}</span></div>`+
    `<label>${esc(t('Verschieben nach','Move to'))}</label><select data-t="folder"${f.account?'':' disabled'}><option value="">${esc(t('– im Posteingang lassen –','– leave in the inbox –'))}</option>${(fo&&fo.folders||[]).map(n=>`<option value="${esc(n)}"${n===f.then.folder?' selected':''}>${esc(n)}</option>`).join('')}</select>`+
    `<label><input type="checkbox" data-t="read"> ${esc(t('als gelesen markieren','mark as read'))}</label><label><input type="checkbox" data-t="flag"> ${esc(t('★ markieren','★ flag'))}</label><label><input type="checkbox" data-t="quiet"> ${esc(t('nicht in „Für dich“','not in "For you"'))}</label>`+
    (RULES.test!=null?`<div class="note">${esc(t('Trifft '+RULES.test+' Mails im Posteingang der letzten 90 Tage.','Fits '+RULES.test+' mails in the inbox of the last 90 days.'))}</div>`:'')+
    `<div class="row postord"><button class="b p" type="button" data-s="save">${esc(t('Sichern','Save'))}</button><button class="b" type="button" data-s="test">${esc(t('Probelauf','Dry run'))}</button><button class="b" type="button" data-s="back">${esc(t('Abbrechen','Cancel'))}</button></div><div class="postordmsg fh"></div></div>`;
  const msg=b.querySelector('.postordmsg'),body=()=>({id:f.id||'',account:f.account,when:f.when,then:f.then,on:f.on!==false});
  for(const k of ['from','subject','to']){const el=b.querySelector(`[data-w=${k}]`);el.value=f.when[k]||'';el.oninput=()=>{f.when[k]=el.value.trim();RULES.test=null}}
  const at=b.querySelector('[data-w=attach]');at.checked=!!f.when.attach;at.onchange=()=>{f.when.attach=at.checked};
  for(const k of ['read','flag','quiet']){const el=b.querySelector(`[data-t=${k}]`);el.checked=!!f.then[k];el.onchange=()=>{f.then[k]=el.checked}}
  b.querySelector('[data-t=folder]').onchange=e=>{f.then.folder=e.target.value};
  b.querySelector('[data-f=account]').onchange=e=>{f.account=e.target.value;f.then.folder='';postRulesDraw()};
  b.querySelector('[data-s=back]').onclick=()=>{RULES.form=null;RULES.test=null;postRulesDraw()};
  b.querySelector('[data-s=test]').onclick=async()=>{msg.textContent=t('Einen Moment …','One moment …');
    const {r,d:x}=await apiTry('/api/profile/mail/rules/test',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body())});
    if(!r.ok){msg.className='postordmsg err';msg.textContent=errSay(r.status,x.detail,'');return}RULES.test=x.n;postRulesDraw()};
  b.querySelector('[data-s=save]').onclick=async()=>{msg.className='postordmsg fh';msg.textContent=t('Einen Moment …','One moment …');
    const {r,d:x}=await apiTry('/api/profile/mail/rules',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body())});
    if(!r.ok){msg.className='postordmsg err';msg.textContent=errSay(r.status,x.detail,'');return}
    let n=RULES.test;const id=x.saved,saved=body();RULES.form=null;RULES.test=null;RULES.data=x;RULES.err='';
    if(n==null&&saved.then.folder){const {r:rt,d:z}=await apiTry('/api/profile/mail/rules/test',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(saved)});n=rt.ok?z.n:0}
    // „auch die vorhandenen“: offered after saving when the dry run found some (asks for the code)
    if(n&&confirm(t('Gesichert. Auch die '+n+' Mails, die schon im Posteingang liegen, jetzt so einsortieren?','Saved. Also sort the '+n+' mails already in the inbox now?'))){
      const {r:r2,d:y}=await apiTry('/api/profile/mail/rules/'+encodeURIComponent(id)+'/apply',{method:'POST'});
      if(r2.ok){RULES.msg=t(y.n+' Mails einsortiert.',y.n+' mails sorted.');const m=y.moved&&y.moved[0];RULES.undo=m&&y.moved.length===1?{account:m.acct,folder:y.folder,mids:m.mids}:null;POST.data=null}
      else RULES.err=errSay(r2.status,y.detail,'')}
    else RULES.msg=t('Gesichert. Die Regel nimmt ab jetzt neue Mails.','Saved. The rule takes new mail from now on.');
    await postRulesLoad()}}
// „⚙ Regel daraus …“ at a mail: the form with this mail's mailbox and sender, on the tab Regeln
function postRuleFrom(m){const acct=(POST.sel||'').split(':')[0];RULES.form={account:acct,when:{from:postAddr(m.from).toLowerCase(),subject:'',to:'',attach:false},then:{folder:'',read:false,flag:false,quiet:false}};
  RULES.test=null;icTabSet('post','regeln');postOpen()}
