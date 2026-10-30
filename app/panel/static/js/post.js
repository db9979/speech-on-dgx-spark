// E-Mail (Dominik 2026-10-18, plan kalender-mail/plan.md 2a 4a): the profile's mailboxes as a page of its own in the
// menu. „Posteingang“ lists the newest messages of every mailbox (GET /api/profile/mail/inbox) and shows one as plain
// text (GET /api/profile/mail/message; with Mails ordnen it is then marked read, postSeen); „Einstellungen“ holds everything set up for mail (#mailbox
// with Aufräumen, Mailstil and Pakete in #parbox; pages of Ich until V01.0.807). Sender, subject and text come from
// other people: in the page only through esc(); a mail's HTML only as the Spark cleaned it (mailansicht.py), in a frame
// where nothing runs, pictures from outside only after „Bilder laden“, a link only after its address was shown.
const POST={menu:'',menuAt:null,data:null,sel:null,msg:null,q:'',chips:{},unread:false,seq:0,mseq:0,busy:false,err:'',done:null,folders:{},write:null,prev:null,sent:'',accts:null,sug:{},
  box:null,tree:null,pick:[],drag:null,hint:null,note:'',
  fopen:(()=>{try{return localStorage.getItem('spark.postFolds')!=='0'}catch(e){return true}})(),picking:false,pending:null};
// Ordner (Mailclient Stufe A, Dominik 2026-10-19 „1a 4a“, postfach.py, with Mails ordnen): box null = the inbox of every
// mailbox, else {account, folder, role, name} of one folder; tree = GET /api/profile/mail/tree; pick = ids of the
// Mehrfachauswahl (ticks only after „Auswählen“, picking). Apple-Stil (Dominik 2026-10-20 „1a“): the mailboxes and
// folders are the column left of the list like Apple Mail (fopen, on unless hidden in this browser, key O), mails are
// dragged onto them (drag: the ids on the way); hint = a rule the Spark proposes
// Mails ordnen (postfach.py, admin switch chat.mail_manage, start.js): read/unread, archive, move, back right after
let ORD_ON=false;
// Mails löschen (postfach.py, admin switch chat.mail_delete): into the trash and back, for good only there after a question
let DEL_ON=false;
// Mails senden (senden.py, admin switch chat.mail_send): a new mail or an answer in its window, „Senden“ with „Rückgängig“
let SEND_ON=false;
// the menu entry only for a signed-in profile that may read mail (start.js, like Kalender)
window.postStart=who=>{const on=!!(who&&who.profile&&who.mail);document.querySelectorAll('nav button[data-s=post]').forEach(b=>b.hidden=!on)};
// the time of a row like Apple Mail: today the time, yesterday „Gestern“, this week the weekday, else the date
const postWhen=s=>{const d=new Date(s*1000),now=new Date(),days=Math.round((new Date(now.toDateString())-new Date(d.toDateString()))/864e5);
  return days<=0?d.toLocaleTimeString(kalLoc(),{hour:'2-digit',minute:'2-digit'}):days===1?t('Gestern','Yesterday')
    :days<7?d.toLocaleDateString(kalLoc(),{weekday:'long'}):d.toLocaleDateString(kalLoc(),{day:'numeric',month:'numeric',year:'2-digit'})};
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
async function postLoad(again){if(!PROFILE||!MAIL_ON)return;const seq=++POST.seq;POST.moreFail='';POST.more=false;POST.busy=!again;POST.tries=again?(POST.tries||0)+1:0;postDraw();
  try{const d=await (await api(POST.box?'/api/profile/mail/folder?'+new URLSearchParams({account:POST.box.account,folder:POST.box.folder,q:postQ()})
      :'/api/profile/mail/inbox?'+new URLSearchParams({q:postQ(),unread:POST.unread?'true':'false'}))).json();
    if(seq!==POST.seq)return;if(!(d.loading&&POST.data&&again))POST.data=d;POST.err='';
    if(d.loading&&POST.tries<5)setTimeout(()=>{if(seq===POST.seq&&$('postview'))postLoad(true)},3000)}
  catch(e){if(seq!==POST.seq)return;POST.err=e.message||t('Nicht erreicht','Not reached')}
  POST.busy=false;postDraw();postFuerLoad();postLaterLoad();postSortLoad()}
// Ältere nachladen (Dominik 2026-10-21 „1a 2a 5a“): at the end of the list the next older page (mark vor, mail.more),
// in the inbox and in a folder, with the search over the whole mailbox; rows already there are not shown twice
async function postMore(){const d=POST.data;if(!d||!d.vor||POST.more||POST.busy)return;const seq=POST.seq;POST.more=true;postMoreBtn();
  try{const r=await (await api(POST.box?'/api/profile/mail/folder?'+new URLSearchParams({account:POST.box.account,folder:POST.box.folder,q:postQ(),vor:d.vor})
      :'/api/profile/mail/inbox?'+new URLSearchParams({q:postQ(),unread:POST.unread?'true':'false',vor:d.vor}))).json();
    if(seq!==POST.seq||POST.data!==d)return;const have=new Set(d.items.map(x=>x.id));
    d.items=d.items.concat((r.items||[]).filter(x=>!have.has(x.id)));d.vor=r.vor||'';d.moreErr=(r.errors||[]).length?r.errors:null;POST.moreFail=''}
  catch(e){if(seq===POST.seq)POST.moreFail=e.message||t('Nicht erreicht','Not reached')}
  POST.more=false;if(seq===POST.seq)postDraw()}
// the end of the list: one row of fixed height (nothing jumps); it loads by itself when it comes into view
function postMoreRow(d){if(!d||(!d.vor&&!(d.items||[]).length))return'';const end=!d.vor;
  return `<div class="ld-more" data-more="1"><button class="lnk" type="button" data-k="more"${end||POST.more?' disabled':''}>${esc(end?t('Keine älteren Mails','No older mail')
    :POST.more?t('Lädt ältere Mails …','Loading older mail …'):POST.moreFail?t('Nicht geladen, noch einmal','Not loaded, try again'):t('Ältere Mails laden','Load older mail'))}</button></div>`}
function postMoreBtn(){const b=document.querySelector('#postview [data-k=more]');if(b){b.disabled=true;b.textContent=t('Lädt ältere Mails …','Loading older mail …')}}
function postMoreWatch(list){if(POST.moreObs)POST.moreObs.disconnect();const row=list.querySelector('[data-more]');if(!row)return;
  const b=row.querySelector('[data-k=more]');if(b)b.onclick=()=>postMore();
  if(!('IntersectionObserver' in window)||POST.moreFail)return;   // after a failure only the button tries again
  POST.moreObs=new IntersectionObserver(es=>{if(es.some(x=>x.isIntersecting))postMore()},{root:/auto|scroll/.test(getComputedStyle(list).overflowY)?list:null,rootMargin:'0px 0px 300px 0px'});
  POST.moreObs.observe(row)}
async function postRead(id){POST.sel=id;POST.msg=null;if(POST.sug[id]&&POST.sug[id].err)delete POST.sug[id];const seq=++POST.mseq;postDraw();
  try{const m=await (await api('/api/profile/mail/message?'+new URLSearchParams(POST.box?{id,folder:POST.box.folder}:{id}))).json();if(seq===POST.mseq)POST.msg=m}
  catch(e){if(seq===POST.mseq)POST.msg={err:e.message||t('Nicht erreicht','Not reached')}}
  postDraw();
  // Unterhaltung (Dominik 2026-10-21 „1“): the other mails of the conversation come after the mail, into their own place
  if(POST.msg&&!POST.msg.err&&seq===POST.mseq){POST.thr=null;apiTry('/api/profile/mail/thread?'+new URLSearchParams(POST.box?{id,folder:POST.box.folder}:{id})).then(({r,d})=>{
    if(seq!==POST.mseq||!r.ok)return;POST.thr={id,items:d.items||[]};const el=document.querySelector('#postview .postthr');if(el)el.innerHTML=postThrInner()})}
  // Antwortvorschläge „1a“: a mail that stays open a moment gets its answers prepared, „Antworten“ finds them ready
  if(SEND_ON&&POST.msg&&!POST.msg.err)setTimeout(()=>{if(POST.sel===id&&seq===POST.mseq)postSuggest(id)},POST_SUG_MS);
  // Tagesaktuell (Dominik 2026-10-21): an opened mail counts as read, like Apple Mail; only with Mails ordnen (the server's mark)
  if(ORD_ON&&POST.msg&&!POST.msg.err)setTimeout(()=>{if(POST.sel===id&&seq===POST.mseq)postSeen(id)},POST_SEEN_MS)}
const POST_SEEN_MS=600;
async function postSeen(id){const x=POST.data&&POST.data.items.find(i=>i.id===id);if(!x||!x.unread)return;   // quiet: no note, no error
  const {r}=await apiTry('/api/profile/mail/act',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id,action:'read',folder:'',mid:'',src:postSrc(),sure:false})});
  if(r.ok){x.unread=false;postDraw()}}
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
  return `<div class="postsugs" role="group" aria-label="${esc(t('Vorschläge vom Spark, nichts wird gesendet','Suggestions of the Spark, nothing is sent'))}"><span class="postsugl">✨ ${esc(t('Vorschläge','Suggestions'))}</span>${rows}</div>`}
const POST_TONE=[['kuerzer','kürzer','shorter'],['freundlicher','freundlicher','friendlier'],['foermlicher','förmlicher','more formal'],['uebersetzen','auf Englisch','in English']];
async function postTone(art,box){const f=POST.write,ta=box.querySelector('[data-f=text]'),msg=box.querySelector('.postordmsg');
  if(!(f.text||'').trim())return;box.querySelectorAll('[data-r]').forEach(b=>b.disabled=true);msg.className='postordmsg fh';msg.textContent=t('Einen Moment …','One moment …');
  const {r,d}=await apiTry('/api/profile/mail/rewrite',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({text:f.text,art})});
  box.querySelectorAll('[data-r]').forEach(b=>b.disabled=false);
  if(!r.ok){msg.className='postordmsg err';msg.textContent=errSay(r.status,d.detail,'');return}
  f.text=d.text;f.ai=true;ta.value=d.text;ta.dispatchEvent(new Event('input'));msg.textContent=t('Text vom Spark: vor dem Senden kommt die Vorschau.','Text from the Spark: the preview comes before sending.')}
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
function postPaint(w){const d=POST.data;w.classList.toggle('ld-sel',!!POST.sel);
  if(d&&d.connected===false){w.innerHTML=`<div class="empty">${esc(t('Noch kein Postfach verbunden. Unter Einstellungen verbindest du iCloud, Gmail, GMX, web.de oder ein anderes IMAP-Postfach.','No mailbox connected yet. Under Settings you connect iCloud, Gmail, GMX, web.de or another IMAP mailbox.'))}<div><button class="b p" type="button" data-k="set">${esc(t('Postfach verbinden','Connect a mailbox'))}</button></div></div>`;
    w.querySelector('[data-k=set]').onclick=()=>{icTabSet('post','set');postOpen()};return}
  if(!w.querySelector('.ld-tools')){
    // Apple-Stil „1a“: one quiet bar: the mailboxes (O), search, „Auswählen“, reload, „Neue Mail“; with Mails ordnen the
    // filters Markiert, Mit Anhang and Ungelesen are mailboxes of the left column, else chips here
    w.innerHTML=`<div class="ld-tools posttools">${ORD_ON?`<button type="button" class="pib postfbtn" data-k="tree" aria-pressed="false" aria-label="${esc(t('Postfächer','Mailboxes'))}" data-tip="${esc(t('Postfächer ein- und ausblenden · O','Show or hide the mailboxes · O'))}">${postIc('side')}</button>`:''}`+
      `<input type="search" data-k="q" placeholder="${esc(t('Suchen, auch von: betreff: hat:anhang','Search, also from: subject: has:attachment'))}" aria-label="${esc(t('Suchen','Search'))}">`+
      (ORD_ON?'':POST_CHIPS.map(c=>`<button type="button" class="ld-chip" data-chip="${c[0]}" aria-pressed="false">${esc(t(c[2],c[3]))}</button>`).join('')+`<button type="button" class="ld-chip" data-k="unread" aria-pressed="false">${esc(t('Nur ungelesen','Unread only'))}</button>`)+
      (ORD_ON?`<button type="button" class="b postpickbtn" data-k="pickmode" aria-pressed="false">${esc(t('Auswählen','Select'))}</button>`:'')+
      `<button type="button" class="pib" data-k="again" aria-label="${esc(t('Neu laden','Reload'))}" data-tip="${esc(t('Neu laden','Reload'))}">${postIc('again')}</button>`+
      (SEND_ON?`<button type="button" class="b p postnew" data-k="new" data-tip="${esc(t('Neue Mail · N','New mail · N'))}">${postIc('pen')}<span>${esc(t('Neue Mail','New mail'))}</span></button>`:'')+`</div>`+
      `<div class="postwarn"></div><div class="postundo"></div><div class="ld-split"><aside class="postfold" hidden></aside><div class="ld-list"></div><div class="ld-detail postdet" hidden></div></div><div class="postcmp" role="dialog" aria-label="${esc(t('Mail schreiben','Write a mail'))}" hidden></div>`;
    const q=w.querySelector('[data-k=q]');q.value=POST.q;let tm=0;
    q.oninput=()=>{clearTimeout(tm);tm=setTimeout(()=>{POST.q=q.value.trim();POST.sel=null;postLoad()},400)};
    w.querySelectorAll('[data-chip]').forEach(b=>b.onclick=()=>postSmart(b.dataset.chip));
    const un=w.querySelector('[data-k=unread]');if(un)un.onclick=()=>postSmart('unread');
    const pm=w.querySelector('[data-k=pickmode]');if(pm)pm.onclick=()=>{POST.picking=!POST.picking;if(!POST.picking)POST.pick=[];postDraw()};
    const tr=w.querySelector('[data-k=tree]');if(tr)tr.onclick=()=>postFolds(!postFoldOn());
    w.querySelector('[data-k=again]').onclick=()=>postLoad();
    const nw=w.querySelector('[data-k=new]');if(nw)nw.onclick=()=>postWrite(null)}
  const u=w.querySelector('[data-k=unread]');if(u){u.classList.toggle('on',POST.unread);u.setAttribute('aria-pressed',String(POST.unread))}
  w.querySelectorAll('[data-chip]').forEach(b=>{const on=!!POST.chips[b.dataset.chip];b.classList.toggle('on',on);b.setAttribute('aria-pressed',String(on))});
  const pm=w.querySelector('[data-k=pickmode]');if(pm){const on=POST.picking||POST.pick.length>0;pm.classList.toggle('on',on);pm.setAttribute('aria-pressed',String(on));pm.textContent=on?t('Fertig','Done'):t('Auswählen','Select')}
  const tr=w.querySelector('[data-k=tree]');if(tr){tr.classList.toggle('on',postFoldOn());tr.setAttribute('aria-pressed',String(postFoldOn()))}
  w.querySelector('.postwarn').innerHTML=(POST.err?`<div class="note warn">${esc(t('Die Mails kamen nicht an: ','The mail did not arrive: ')+POST.err)}</div>`:'')+
    (d&&d.errors&&d.errors.length?`<div class="note warn">${esc(t('Nicht erreicht: ','Not reached: ')+d.errors.join(', '))}</div>`:'')+
    (d&&d.moreErr?`<div class="note warn">${esc(t('Ältere Mails nicht erreicht: ','Older mail not reached: ')+d.moreErr.join(', '))}</div>`:'')+
    (d&&d.loading?`<div class="note">${esc(t('Die Postfächer laden noch …','The mailboxes are still loading …'))}</div>`:'');
  const many=d&&d.boxes&&d.boxes.length>1,items=postItems(),list=w.querySelector('.ld-list');
  list.classList.toggle('busy',POST.busy);
  let day='';
  const ticks=ORD_ON&&(POST.picking||POST.pick.length>0);
  // a row like Apple Mail: sender and time on top, the subject, two lines of the text when the list has them (prev)
  list.innerHTML=postHead(d,items)+items.map(x=>{const g=postDay(x.date),head=g!==day?`<div class="ld-grp"><span>${esc(g)}</span></div>`:'';day=g;const fd=postFuer(x);
    return head+`<div class="ld-row${POST.sel===x.id?' on':''}${x.unread?' unread':''}${POST.pick.includes(x.id)?' picked':''}" role="button" tabindex="0" data-id="${esc(x.id)}"${ORD_ON&&postMovable()?' draggable="true"':''}>`+
      (ticks?`<input type="checkbox" class="ld-pick" data-pick="${esc(x.id)}" aria-label="${esc(t('Auswählen','Select'))}"${POST.pick.includes(x.id)?' checked':''}>`:'')+
      `<span class="postdot" aria-label="${esc(x.unread?t('ungelesen','unread'):'')}"></span><span class="postav ${postKc(x.from)}" aria-hidden="true">${esc(postInit(x.from))}</span>`+
      `<span class="ld-mid"><span class="postl1"><b>${esc(postName(x.from))}</b><span class="ld-right">${x.attach?`<span class="postmk" aria-label="${esc(t('mit Anhang','with attachment'))}">📎</span>`:''}${x.flagged?`<span class="postmk star" aria-label="${esc(t('markiert','flagged'))}">★</span>`:''}<span class="ld-when">${esc(postWhen(x.date))}</span></span></span>`+
      `<small class="postsubj">${esc(x.subject||t('(ohne Betreff)','(no subject)'))}</small>${x.prev?`<small class="postprv">${esc(x.prev)}</small>`:''}`+
      `${fd||many?`<span class="postchips">${fd?`<span class="postfd${fd.urgent?' hot':''}">${esc(FUER_KIND[fd.kind]||fd.kind)}</span>`:''}${many?`<span class="ld-badge off">${esc(d.boxes[x.box]||'')}</span>`:''}</span>`:''}</span></div>`}).join('')
    ||(POST.busy?'':`<div class="ld-empty mut">${esc(POST.box?(postQ()?t('Keine passende Mail in diesem Ordner.','No matching mail in this folder.'):t('Dieser Ordner ist leer.','This folder is empty.'))
      :postQ()||POST.unread?t('Keine passende Mail in den letzten 14 Tagen.','No matching mail in the last 14 days.'):t('Keine Mail in den letzten 14 Tagen.','No mail in the last 14 days.'))}</div>`);
  if(!POST.busy)list.insertAdjacentHTML('beforeend',postMoreRow(d));postMoreWatch(list);
  list.querySelectorAll('[data-pick]').forEach(c=>{c.onclick=e=>e.stopPropagation();c.onchange=()=>{const id=c.dataset.pick;
    POST.pick=c.checked?[...POST.pick,id].slice(-50):POST.pick.filter(x=>x!==id);postUndo(w)}});
  list.querySelectorAll('[data-id]').forEach(r=>{r.onclick=e=>{if(POST.swiped){POST.swiped=false;return}
      // ⌘ or Strg with a click ticks the row like in a mail program (only with Mails ordnen)
      if(ORD_ON&&(e.metaKey||e.ctrlKey)){const id=r.dataset.id;POST.pick=POST.pick.includes(id)?POST.pick.filter(x=>x!==id):[...POST.pick,id].slice(-50);postDraw();return}
      postRead(r.dataset.id)};r.onkeydown=e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();postRead(r.dataset.id)}};postSwipe(r);if(r.draggable)postDrag(r,w)});
  postUndo(w);if(POST.sent)w.querySelector('.postundo').insertAdjacentHTML('beforeend',`<div class="note">${esc(POST.sent)}</div>`);
  postFoldPaint(w);
  postDetail(w);postWriteBox(w)}
// the head of the list box (Dominik 2026-10-20 „gleiche Boxen“): where the list is from, how many, how many unread
function postHead(d,items){const many=d&&d.boxes&&d.boxes.length>1,u=items.filter(x=>x.unread).length;
  const name=POST.box?POST.box.name:POST.unread?t('Ungelesen','Unread'):POST.chips.flag?t('Markiert','Flagged'):POST.chips.attach?t('Mit Anhang','With attachment')
    :many?t('Alle Posteingänge','All inboxes'):t('Posteingang','Inbox');
  return `<div class="posthead"><b>${esc(name)}</b><small>${esc(items.length+' '+t('Mails','mails')+(u?' · '+u+' '+t('neu','new'):''))}</small></div>`}
// the buttons of a message (Dominik 2026-10-20 „1 und 3“): one bar that stays on top while the mail scrolls, symbols in
// three groups (write · order · rule), each with its name and key on hover; on a phone the five most used sit at the
// thumb below, ★ and ⋯ on top. Nothing is ever deleted; every move can go back right after.
const POST_IC={reply:'M9 14L4 9l5-5M4 9h10a6 6 0 0 1 6 6v4',fwd:'M15 14l5-5-5-5M20 9H10a6 6 0 0 0-6 6v4',
  cal:'M3 7a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2zM3 10h18M8 3v4M16 3v4M12 13v5M9.5 15.5h5',
  read:'M3 7a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2zM3 7l9 6 9-6',
  star:'M12 3l2.8 5.7 6.2.9-4.5 4.4 1 6.2L12 17.3 6.5 20.2l1-6.2L3 9.6l6.2-.9z',
  arch:'M3 4h18v5H3zM5 9v10a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1V9M10 13h4',
  move:'M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2zM12 11v5M9.5 13.5L12 16l2.5-2.5',
  rule:'M12 9a3 3 0 1 0 0 6 3 3 0 0 0 0-6zM12 2v3M12 19v3M2 12h3M19 12h3M4.9 4.9l2.1 2.1M17 17l2.1 2.1M4.9 19.1L7 17M17 7l2.1-2.1',
  more:'M5 12h.01M12 12h.01M19 12h.01',back:'M15 18l-6-6 6-6',close:'M6 6l12 12M18 6L6 18',
  pen:'M4 20h4L19 9l-4-4L4 16zM13.5 6.5l4 4',
  folder:'M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z',
  inbox:'M4 13h4l1.5 3h5L16 13h4M5 5h14l1 8v6H4v-6z',sent:'M4 12l16-8-6 16-3-7z',
  trash:'M4 7h16M9 7V4h6v3M6 7l1 13h10l1-13M10 11v6M14 11v6',junk:'M12 4l9 16H3zM12 10v4M12 17v.5',all:'M4 6h16M4 12h16M4 18h16',
  side:'M4 5h16v14H4zM9 5v14',again:'M20 12a8 8 0 1 1-2.3-5.7M20 4v5h-5',clip:'M20 11l-8.5 8.5a5 5 0 0 1-7-7L13 4a3.5 3.5 0 0 1 5 5l-8.5 8.5a2 2 0 0 1-3-3L14 7',
  dot:'M12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8z',lock:'M6 11h12v9H6zM8 11V8a4 4 0 0 1 8 0v3'};
const postIc=k=>`<svg viewBox="0 0 24 24" width="19" height="19" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="${POST_IC[k]}"/></svg>`;
// one symbol button: its name for screen readers and the hover note (with the key when there is one)
const postIb=(k,data,de,en,key,on)=>{const n=t(de,en);return `<button type="button" class="pib${on?' on':''}" ${data} aria-label="${esc(n)}" data-tip="${esc(n+(key&&!NARROW()?' · '+key:''))}">${postIc(k)}</button>`};
const postSrc=()=>POST.box?POST.box.folder:'INBOX';
// what the folder's role allows: moved out only of the inbox, an own folder, the archive or the trash (postfach._source)
const postMovable=()=>!POST.box||['folder','archive'].includes(POST.box.role);
// deleted out of anything but the trash itself and Gmail's views (postfach._source_del)
const postDeletable=()=>DEL_ON&&(!POST.box||!['trash','all','group'].includes(POST.box.role));
const postInTrash=()=>DEL_ON&&!!POST.box&&POST.box.role==='trash';
// [the bar on top, the thumb bar below (phones)]
function postBar(m){const menu=POST.menuAt===POST.sel?POST.menu:'',x=postItems().find(i=>i.id===POST.sel),f=POST.folders[POST.sel.split(':')[0]],src=postSrc(),ok=m&&!m.err;
  const cal=ok&&typeof CAL_ON!=='undefined'&&CAL_ON,send=ok&&SEND_ON,ord=ok&&ORD_ON,arch=ord&&postMovable()&&!(f&&f.archive===src),mv=ord&&postMovable();
  const close=NARROW()?`<button type="button" class="pib postclose ld-back" data-close="1" aria-label="${esc(t('Zurück','Back'))}">${postIc('back')}</button>`
    :`<button type="button" class="pib postclose" data-close="1" aria-label="${esc(t('Schließen','Close'))}" data-tip="${esc(t('Schließen · Esc','Close · Esc'))}">${postIc('close')}</button>`;
  const read=ord?postIb('read',`data-o="${x&&x.unread?'read':'unread'}"`,...(x&&x.unread?['Als gelesen markieren','Mark as read']:['Als ungelesen markieren','Mark as unread']),'U'):'';
  const star=ord?postIb('star',`data-o="${x&&x.flagged?'unflag':'flag'}"`,...(x&&x.flagged?['Markierung weg','Unflag']:['Markieren','Flag']),'S',x&&x.flagged):'';
  const rule=ord?postIb('rule','data-w="rule"','Regel daraus …','Rule from this …','G'):'';
  const del=ord&&postDeletable()?postIb('trash','data-o="delete"','Löschen (in den Papierkorb)','Delete (into the trash)','Entf')
    :ord&&postInTrash()?postIb('trash','data-o="erase"','Endgültig löschen','Delete for good',''):'';
  if(NARROW()){   // a phone: back, ★ and ⋯ on top, the five most used at the thumb below
    const foot=[send?['reply','data-w="reply"','Antworten','Reply']:null,send?['fwd','data-w="fwd"','Weiter','Forward']:null,
      arch?['arch','data-o="archive"','Archiv','Archive']:null,mv?['move','data-o="pick"','Ordner','Folder']:null,
      ord&&postDeletable()?['trash','data-o="delete"','Löschen','Delete']:ord&&postInTrash()?['trash','data-o="erase"','Endgültig','For good']:null,
      cal?['cal','data-w="cal"','Termin','Event']:null].filter(Boolean),top=foot.slice(5);
    const more=ord||top.length?`<button type="button" class="pib" data-o="more" aria-label="${esc(t('Mehr','More'))}" aria-expanded="${menu==='more'}">${postIc('more')}</button>`:'';
    return [`<div class="postbar" role="toolbar" aria-label="${esc(t('Mail','Mail'))}">${close}<span class="pgap"></span>`+
      (SEND_ON?`<button type="button" class="pib" data-w="new" aria-label="${esc(t('Neue Mail','New mail'))}">${postIc('pen')}</button>`:'')+star+more+`</div>`+
      (menu==='more'?`<div class="postmenu">${top.map(b=>`<button type="button" ${b[1]}>${postIc(b[0])}${esc(t(b[2],b[3]))}</button>`).join('')}${ord?`<button type="button" ${read.match(/data-o="\w+"/)[0]}>${postIc('read')}${esc(x&&x.unread?t('Als gelesen markieren','Mark as read'):t('Als ungelesen markieren','Mark as unread'))}</button><button type="button" data-w="rule">${postIc('rule')}${esc(t('Regel daraus …','Rule from this …'))}</button>`:''}</div>`:'')+
      (menu==='pick'?postMoveMenu(f,src):''),
      // the thumb bar goes last, below the mail (V01.0.865 drew it first, over the subject)
      foot.length?`<div class="postfoot" role="toolbar">${foot.slice(0,5).map(b=>`<button type="button" ${b[1]}>${postIc(b[0])}<span>${esc(t(b[2],b[3]))}</span></button>`).join('')}</div>`:'']}
  const g1=(send?`<button type="button" class="b p postpri" data-w="reply" data-tip="${esc(t('Antworten · R','Reply · R'))}">${postIc('reply')}${esc(t('Antworten','Reply'))}</button>`+postIb('fwd','data-w="fwd"','Weiterleiten','Forward','F'):'')+
    (cal?postIb('cal','data-w="cal"','Als Termin','As appointment','T'):'');
  const g2=read+star+(arch?postIb('arch','data-o="archive"','Archivieren','Archive','E'):'')+
    (mv?postIb('move','data-o="pick" aria-expanded="'+(menu==='pick')+'"','Verschieben nach …','Move to …','V'):'')+del;
  return [`<div class="postbar" role="toolbar" aria-label="${esc(t('Mail','Mail'))}">${close}<span class="psep"></span>${[g1,g2,rule].filter(Boolean).join('<span class="psep"></span>')}</div>`+
    (menu==='pick'?postMoveMenu(f,src):''),'']}
// „Verschieben nach …“: the folders of the message's mailbox as a short menu (the inbox first when in a folder)
function postMoveMenu(f,src){const into=(f&&f.folders||[]).filter(n=>n!==src);if(POST.box)into.unshift('INBOX');
  return `<div class="postmenu postmv">${into.length?into.map(n=>`<button type="button" data-mv="${esc(n)}">${postIc('move')}${esc(n==='INBOX'?t('Posteingang','Inbox'):n)}</button>`).join('')
    :`<span class="mut">${esc(t('Ordner werden geladen …','Loading folders …'))}</span>`}</div>`}
function postDetail(w){const box=w.querySelector('.postdet'),m=POST.msg;if(!box)return;box.hidden=!POST.sel;if(!POST.sel){box.textContent='';return}
  const [bar,foot]=postBar(m);
  if(!m)box.innerHTML=bar+`<div class="mut">${esc(t('Lade die Mail …','Loading the mail …'))}</div>`;
  else if(m.err)box.innerHTML=bar+`<div class="note warn">${esc(m.err)}</div>`;
  else{const when=new Date(m.date*1000).toLocaleString(kalLoc(),{weekday:'short',day:'numeric',month:'long',hour:'2-digit',minute:'2-digit'});
    // the head like Apple Mail: the sender's circle, name, address and to whom on the left, the time on the right, then
    // the subject big; attachments as tiles; the text formatted in its frame (mailansicht.py) or as plain text
    box.innerHTML=bar+`<div class="posthdr"><span class="postav big ${postKc(m.from)}" aria-hidden="true">${esc(postInit(m.from))}</span>`+
      `<div class="ld-mid"><span class="postl1"><b>${esc(postName(m.from))}</b><span class="ld-when">${esc(when)}</span></span>`+
      `<small>${esc(postAddr(m.from))}</small>${m.to?`<small>${esc(t('An: ','To: ')+m.to)}</small>`:''}</div></div>`+
      `<h3 class="postsubjbig">${esc(m.subject||t('(ohne Betreff)','(no subject)'))}</h3>`+
      (m.files&&m.files.length?`<div class="postfiles">${ORD_ON&&m.parts&&m.parts.length?m.parts.map(f=>`<a class="postfile" download href="/api/profile/mail/file?${esc(new URLSearchParams({id:POST.sel,folder:postSrc(),n:f.n}).toString())}">${postIc('clip')}<span><b>${esc(f.name)}</b><small>${f.kb} KB</small></span></a>`).join('')
        :m.files.map(n=>`<span class="postfile">${postIc('clip')}<span><b>${esc(n)}</b></span></span>`).join('')}</div>`:'')+
      (m.html?(m.remote?`<div class="postpics">${postIc('lock')}<span>${esc(POST.pics===POST.sel?t('Bilder von außen geladen, über den Spark.','Pictures from outside loaded, through the Spark.')
          :t('Bilder von außen sind aus, damit der Absender nicht sieht, dass du die Mail liest.','Pictures from outside stay off, so the sender does not learn that you read the mail.'))}</span>${POST.pics===POST.sel?'':`<button class="b" type="button" data-k="pics">${esc(t('Bilder laden','Load pictures'))}</button>`}</div>`:'')+
        `<iframe class="postframe" title="${esc(t('Inhalt der Mail','Content of the mail'))}" sandbox="allow-same-origin" referrerpolicy="no-referrer" src="/api/profile/mail/view?${esc(new URLSearchParams({id:POST.sel,...(POST.box?{folder:POST.box.folder}:{}),...(POST.pics===POST.sel?{bilder:'true'}:{})}).toString())}"></iframe>`
        :`<div class="posttext">${esc(m.text||t('(kein Text)','(no text)'))}</div>`)+
      `<div class="postlink" hidden></div><div class="postthr">${postThrInner()}</div>`+
      (SEND_ON?'':`<div class="fh">${esc(t('Antworten geht mit dem Assistenten: „Antworte Anna …“.','Reply with the assistant: "Reply to Anna …".'))}</div>`)+`<div class="postordmsg fh"></div>`+foot;
    const fr=box.querySelector('.postframe');if(fr)postFrame(fr,box.querySelector('.postlink'));
    const who=box.querySelector('.posthdr .postl1 b');if(who&&window.konShow&&CON_ON){who.className='postwho';who.tabIndex=0;who.setAttribute('role','button');who.onkeydown=e=>{if(e.key==='Enter')who.click()};who.title=t('Kontaktkarte','Contact card');who.onclick=()=>konShow(postAddr(m.from),postName(m.from))}   // Kontakte: the sender's card
    if(m.invite&&window.einShow)einShow(box.querySelector('.postsubjbig'),POST.sel,postSrc());   // Einladungen aus Mails (einladung.js)
    const pics=box.querySelector('[data-k=pics]');if(pics)pics.onclick=()=>{POST.pics=POST.sel;postDetail(w)}}
  const msg=box.querySelector('.postordmsg')||document.createElement('div');
  box.querySelector('[data-close]').onclick=()=>{POST.sel=null;POST.msg=null;postDraw()};
  const on=(q,f)=>box.querySelectorAll(q).forEach(b=>b.onclick=f);
  on('[data-w=reply]',()=>postWrite(m));on('[data-w=fwd]',()=>postWrite(m,true));on('[data-w=new]',()=>postWrite(null));
  on('[data-w=cal]',()=>postAsEvent(m));on('[data-w=rule]',()=>{postRuleFrom(m)});
  on('[data-o=pick]',()=>postMenu('pick'));on('[data-o=more]',()=>postMenu('more'));
  box.querySelectorAll('[data-o]:not([data-o=pick]):not([data-o=more]):not([data-o=erase])').forEach(b=>b.onclick=()=>{postAct(b.dataset.o,'',msg)});
  on('[data-o=erase]',()=>postErase(m,msg));
  // a mail dragged from the list onto the archive or the trash symbol of the open one
  box.querySelectorAll('[data-o=archive],[data-o=delete]').forEach(b=>postDropOn(b,()=>b.dataset.o,()=>''));
  on('[data-mv]',e=>{postAct('move',e.currentTarget.dataset.mv,msg)});
  const sel=POST.sel;if(ORD_ON&&m&&!m.err)postFoldersFor(sel.split(':')[0]).then(n=>{if(n&&$('postview')&&POST.sel===sel)postDetail($('postview'))})}
// the conversation under the mail, oldest first, each folded to one line (who, when, its first words); own ones as „Du“
function postThrInner(){const th=POST.thr;if(!th||th.id!==POST.sel||!th.items.length)return '';
  return `<div class="ld-grp"><span>${esc(t('Unterhaltung · '+th.items.length+(th.items.length>1?' weitere Mails':' weitere Mail'),'Conversation · '+th.items.length+(th.items.length>1?' more mails':' more mail')))}</span></div>`+
    th.items.map(x=>`<details class="postthrrow"><summary><span class="postav ${postKc(x.from)}" aria-hidden="true">${esc(postInit(x.from))}</span><span class="ld-mid"><span class="postl1"><b>${esc(x.own?t('Du','You'):postName(x.from))}</b>`+
      `<span class="ld-when">${esc(new Date(x.date*1000).toLocaleString(kalLoc(),{day:'numeric',month:'short',hour:'2-digit',minute:'2-digit'}))}</span></span><small>${esc((x.text||'').replace(/\s+/g,' ').slice(0,120))}</small></span></summary>`+
      `<div class="posttext">${esc(x.text||t('(kein Text)','(no text)'))}</div></details>`).join('')}
// the frame of a formatted mail (Apple-Stil „2a“): nothing runs inside it (sandbox without scripts, its own CSP); the
// page sizes it to its content and catches a tap on a link (data-href, the Spark never hands out a working href)
function postFrame(fr,lb){fr.addEventListener('load',()=>{let d=null;try{d=fr.contentDocument}catch(e){}if(!d||!d.body)return;
  // the mail frame takes the height of its page (no textarea: growing fields stay feld.js's job)
  const fit=()=>{const h=d.documentElement.scrollHeight;fr.style.height=Math.min(30000,Math.max(48,h))+'px'};fit();
  try{new ResizeObserver(fit).observe(d.body)}catch(e){}
  d.querySelectorAll('[data-href]').forEach(a=>{a.tabIndex=0;a.setAttribute('role','link')});
  const go=e=>{const a=e.target&&e.target.closest&&e.target.closest('[data-href]');if(!a)return;e.preventDefault();postLinkAsk(a.getAttribute('data-href'),a.textContent||'',lb)};
  d.addEventListener('click',go);d.addEventListener('keydown',e=>{if(e.key==='Enter')go(e)})})}
// a link of a mail opens only after its real address was shown (like Apple Mail on a long press); a text naming a
// different address than the link is said aloud (a common trick of phishing mails); mailto: opens a new mail
function postLinkAsk(url,text,lb){let u;try{u=new URL(url)}catch(e){return}
  if(u.protocol==='mailto:'){const to=decodeURIComponent(u.pathname||''),sub=u.searchParams.get('subject')||'';
    if(SEND_ON){const was=POST.write;postWrite(null).then(()=>{if(POST.write&&POST.write!==was){POST.write.to=to.slice(0,2000);POST.write.subject=sub.slice(0,200);POST.focus=true;postDraw()}})}
    else{lb.hidden=false;lb.innerHTML=`<div class="note">${esc(t('Adresse: ','Address: ')+to)}</div>`}return}
  if(!/^https?:$/.test(u.protocol))return;
  const host=u.hostname.replace(/^www\./,''),said=((/^(?:https?:\/\/)?((?:[a-z0-9-]+\.)+[a-z]{2,})(?:[\/?#]\S*)?$/i.exec(text.trim())||[])[1]||'').toLowerCase().replace(/^www\./,'');
  const other=said&&said!==host&&!host.endsWith('.'+said);
  lb.hidden=false;lb.innerHTML=`<div class="note${other?' warn':''}"><b>${esc(t('Link öffnen?','Open the link?'))}</b> ${esc(t('Er führt zu ','It leads to '))}<b>${esc(host)}</b>`+
    (other?`<br>${esc(t('Achtung: der Text in der Mail nennt „'+said+'“, der Link führt aber woanders hin.','Careful: the text in the mail says "'+said+'", but the link leads elsewhere.'))}`:'')+
    `<small class="postlinkurl">${esc(u.href.slice(0,300))}</small><span class="row postord"><button class="b${other?'':' p'}" type="button" data-l="go">${esc(t('Öffnen','Open'))}</button><button class="b" type="button" data-l="no">${esc(t('Abbrechen','Cancel'))}</button></span></div>`;
  lb.querySelector('[data-l=go]').onclick=()=>{lb.hidden=true;window.open(u.href,'_blank','noopener,noreferrer')};
  lb.querySelector('[data-l=no]').onclick=()=>{lb.hidden=true};lb.scrollIntoView({block:'nearest'})}
// the move menu (or ⋯ on a phone) opens and closes in place
function postMenu(k){POST.menu=POST.menuAt===POST.sel&&POST.menu===k?'':k;POST.menuAt=POST.sel;if($('postview'))postDetail($('postview'))}
async function postFoldersFor(acct){if(!POST.folders[acct]){const {r,d}=await apiTry('/api/profile/mail/folders?'+new URLSearchParams({account:acct}));if(r.ok)POST.folders[acct]=d;return r.ok}return false}
async function postAct(action,folder,msg,mid,which,sure){const id=which||POST.sel,src=postSrc();if(msg){msg.className='postordmsg fh';msg.textContent=t('Einen Moment …','One moment …')}
  const back=postGone([id],action);
  const {r,d}=await apiTry('/api/profile/mail/act',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id,action,folder,mid:mid||'',src,sure:!!sure})});
  if(!r.ok){postBack(back);if(msg&&msg.isConnected){msg.className='postordmsg err';msg.textContent=errSay(r.status,d.detail,'')}else{POST.err=errSay(r.status,d.detail,'');postDraw()}return}
  const x=POST.data.items.find(i=>i.id===id);
  if(action==='read'||action==='unread'){if(x)x.unread=action==='unread';postDraw();return}
  if(action==='flag'||action==='unflag'){if(x)x.flagged=action==='flag';postDraw();return}
  // archived, moved or deleted: off the list already, with „Rückgängig“ for a while (gone for good: no way back)
  POST.done=action==='erase'?null:{id,acct:id.split(':')[0],mid:d.mid,folder:d.folder,src,del:action==='delete'};
  POST.note=action==='erase'?t('Endgültig gelöscht.','Deleted for good.'):'';if(d.hint)POST.hint=d.hint;
  postTreeShift(id.split(':')[0],src,d.folder,back.filter(i=>i.unread).length);postDraw()}
// Dominik 2026-10-21 „reloaded immer die gesamte Ordnerliste“: a mail moved, archived or deleted leaves the list at once,
// the folders stay as they are (only their unread numbers change); when the Spark says no it comes back
function postGone(ids,action){if(!['archive','move','delete','erase'].includes(action)||!POST.data)return [];
  const out=POST.data.items.filter(i=>ids.includes(i.id));POST.data.items=POST.data.items.filter(i=>!ids.includes(i.id));
  POST.pick=POST.pick.filter(i=>!ids.includes(i));const sel=ids.includes(POST.sel)?{sel:POST.sel,msg:POST.msg}:null;if(sel){POST.sel=null;POST.msg=null}
  out.sel=sel;postDraw();return out}
function postBack(back){if(!back.length||!POST.data)return;const have=new Set(POST.data.items.map(i=>i.id));
  POST.data.items=POST.data.items.concat(back.filter(i=>!have.has(i.id))).sort((a,b)=>(b.date||0)-(a.date||0));if(back.sel&&!POST.sel){POST.sel=back.sel.sel;POST.msg=back.sel.msg}postDraw()}
// the unread numbers of the two folders follow here; the mailbox is asked quietly behind (postfach._tree_old reads it anew)
function postTreeShift(acct,from,into,n){const a=POST.tree&&POST.tree.accounts&&POST.tree.accounts.find(x=>x.id===acct);
  if(a&&n)for(const f of a.folders){if(f.name===from&&f.unseen)f.unseen=Math.max(0,f.unseen-n);else if(f.name===into&&f.unseen!=null)f.unseen+=n}
  clearTimeout(POST.treeLater);if(POST.tree)POST.treeLater=setTimeout(()=>{if($('postview')){POST.treeTries=0;postTreeLoad(false,true)}},2500)}
// „Endgültig löschen“ in the trash: its own question first, then exactly this mail (its Message-ID) is gone
function postErase(m,msg){if(!m||!m.mid)return;
  if(confirm(t('Diese Mail endgültig löschen? Das lässt sich nicht zurückholen.','Delete this mail for good? This cannot be undone.')))postAct('erase','',msg,m.mid,POST.sel,true)}
// the list as shown: in a folder the search and „Nur ungelesen“ work on the listing (the inbox asks the server)
// the server searches (mail._words: von:, betreff:, hat:anhang, ist:markiert); in a folder „Nur ungelesen“ is ist:ungelesen
function postItems(){return (POST.data&&POST.data.items)||[]}
const POST_CHIPS=[['flag','ist:markiert','★ Markiert','★ Flagged'],['attach','hat:anhang','📎 Anhang','📎 Attachment']];
// a filter: ★ Markiert, 📎 Anhang (chips, or the smart mailboxes left) and „Ungelesen“; one at a time from the left column
function postSmart(k,only){if(only){const on=k==='unread'?POST.unread:!!POST.chips[k];POST.chips={};POST.unread=false;if(POST.box){POST.box=null;POST.data=null}if(!on){if(k==='unread')POST.unread=true;else POST.chips[k]=true}}
  else if(k==='unread')POST.unread=!POST.unread;else POST.chips[k]=!POST.chips[k];
  POST.sel=null;POST.msg=null;POST.fsheet=false;postLoad()}
function postQ(){return [POST.q,...POST_CHIPS.filter(c=>POST.chips[c[0]]).map(c=>c[1]),POST.box&&POST.unread?'ist:ungelesen':''].filter(Boolean).join(' ').slice(0,100)}
function postUndo(w){const u=POST.done,box=w.querySelector('.postundo');if(!box)return;
  const pick=(ORD_ON&&POST.pick.length?postPickBar():'')+postHintHtml()+(POST.note?`<div class="note">${esc(POST.note)}</div>`:''),pend=postPendHtml()+postLaterHtml()+postSortHtml();
  if(!u){box.innerHTML=pend+pick;postPendBind(box);postLaterListBind(box);postSortBind(box);postPickBind(box);postHintBind(box);return}
  box.innerHTML=pend+`<div class="note">${esc(u.del?(u.n>1?t(u.n+' Mails in den Papierkorb gelegt.',u.n+' mails put into the trash.'):t('In den Papierkorb gelegt.','Put into the trash.'))
    :(u.n>1?t(u.n+' Mails verschoben nach ',u.n+' mails moved to '):t('Verschoben nach ','Moved to '))+(u.folder==='INBOX'?t('Posteingang','Inbox'):u.folder)+'.')} <button class="b" type="button" data-u="1">${esc(t('Rückgängig','Undo'))}</button></div>`+pick;
  postPendBind(box);postLaterListBind(box);postSortBind(box);postPickBind(box);postHintBind(box);
  box.querySelector('[data-u]').onclick=async()=>{const {r,d}=u.mids?await apiTry('/api/profile/mail/acts/back',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({account:u.acct,folder:u.folder,mids:u.mids,src:u.src})})
      :await apiTry('/api/profile/mail/act',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id:u.acct+':0',action:'back',folder:u.folder,mid:u.mid,src:u.src})});
    POST.done=null;if(!r.ok){box.innerHTML=`<div class="note warn">${esc(errSay(r.status,d.detail,''))}</div>`;return}postTreeShift(u.acct,'','',0);postLoad()}}
// Mehrfachauswahl: the bar above the list while messages are ticked; a move goes into a folder of one mailbox
function postPickBar(){const accts=[...new Set(POST.pick.map(i=>i.split(':')[0]))],f=accts.length===1?POST.folders[accts[0]]:null,src=postSrc();
  const into=(f&&f.folders||[]).filter(n=>n!==src);if(POST.box)into.unshift('INBOX');
  return `<div class="row postord postpick"><b>${esc(POST.pick.length+' '+t('gewählt','selected'))}</b>`+
    ['read','unread','flag'].map(a=>`<button class="b" type="button" data-m="${a}">${esc({read:t('Gelesen','Read'),unread:t('Ungelesen','Unread'),flag:t('★ Markieren','★ Flag')}[a])}</button>`).join('')+
    (postMovable()?`<button class="b" type="button" data-m="archive">${esc(t('Archivieren','Archive'))}</button>`:'')+
    (postDeletable()?`<button class="b" type="button" data-m="delete">${esc(t('Löschen','Delete'))}</button>`:'')+
    (postMovable()&&accts.length===1?`<select data-m="move" aria-label="${esc(t('Verschieben nach','Move to'))}"><option value="">${esc(t('Verschieben nach …','Move to …'))}</option>${into.map(n=>`<option value="${esc(n)}">${esc(n==='INBOX'?t('Posteingang','Inbox'):n)}</option>`).join('')}</select>`:'')+
    `<button class="b" type="button" data-m="none">${esc(t('Auswahl aufheben','Clear selection'))}</button></div><div class="postordmsg fh"></div>`}
function postPickBind(box){const bar=box.querySelector('.postpick');if(!bar)return;const msg=box.querySelector('.postordmsg'),accts=[...new Set(POST.pick.map(i=>i.split(':')[0]))];
  if(accts.length===1&&!POST.folders[accts[0]])postFoldersFor(accts[0]).then(ok=>{if(ok)postDraw()});
  bar.querySelectorAll('button[data-m]').forEach(b=>b.onclick=()=>b.dataset.m==='none'?(POST.pick=[],postDraw()):postMany(b.dataset.m,'',msg));
  const sel=bar.querySelector('select[data-m]');if(sel)sel.onchange=()=>{if(sel.value)postMany('move',sel.value,msg)}}
async function postMany(action,folder,msg){const ids=POST.pick.slice(),src=postSrc();msg.className='postordmsg fh';msg.textContent=t('Einen Moment …','One moment …');
  const back=postGone(ids,action);
  const {r,d}=await apiTry('/api/profile/mail/acts',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({ids,action,folder,src})});
  if(!r.ok){POST.pick=ids;postBack(back);if(msg.isConnected){msg.className='postordmsg err';msg.textContent=errSay(r.status,d.detail,'')}else{POST.err=errSay(r.status,d.detail,'');postDraw()}return}
  POST.pick=[];
  if(back.length){const m=d.moved&&d.moved[0];POST.done=m&&d.moved.length===1?{acct:m.acct,mids:m.mids,folder:d.folder,src,n:d.n,del:action==='delete'}:null;if(d.hint)POST.hint=d.hint;
    for(const a of new Set(back.map(i=>i.id.split(':')[0])))postTreeShift(a,src,d.folder,back.filter(i=>i.unread&&i.id.split(':')[0]===a).length)}
  else for(const x of POST.data.items)if(ids.includes(x.id)){if(action==='flag')x.flagged=true;else x.unread=action==='unread'}
  postDraw()}
// Ordner: the folders of every mailbox in the list's place; tap opens one, own folders can be renamed or removed
// a folder's line symbol and, for the mail program's own folders, one German or English name (Dominik 2026-10-20)
const POST_ROLE={inbox:['inbox','Posteingang','Inbox'],sent:['sent','Gesendet','Sent'],drafts:['pen','Entwürfe','Drafts'],archive:['arch','Archiv','Archive'],
  trash:['trash','Papierkorb','Trash'],junk:['junk','Spam','Junk'],all:['all'],group:['folder'],folder:['folder']};
// on a phone the folders come in from the right only when asked and go when one is picked (POST.fsheet, not kept)
const postFoldOn=()=>NARROW()?!!POST.fsheet:POST.fopen;
function postFolds(on){if(NARROW())POST.fsheet=on;else{POST.fopen=on;try{localStorage.setItem('spark.postFolds',on?'1':'0')}catch(e){}}if(on)postTreeLoad();postDraw()}
// Dominik 2026-10-21 „1“: a kept list (Mail-Vorrat) comes at once with neu, read anew behind; asked again after 3 s
async function postTreeLoad(fresh,again){if(POST.tree&&!fresh&&!again)return;POST.treeBusy=!again;POST.treeTries=again?(POST.treeTries||0)+1:0;
  const {r,d}=await apiTry('/api/profile/mail/tree'+(fresh?'?fresh=true':''));POST.treeBusy=false;
  // asked again: a kept list (neu) never replaces the one shown, so numbers counted here do not jump back
  const keep=again&&POST.tree&&POST.tree.accounts&&(!r.ok||d.neu);
  if(!keep)POST.tree=r.ok?d:{err:errSay(r.status,d.detail,'')};const w=$('postview');if(w&&!keep)postFoldPaint(w);
  if(r.ok&&d.neu&&POST.treeTries<5)setTimeout(()=>{if($('postview'))postTreeLoad(false,true)},3000)}
function postTreeHtml(){const tr=POST.tree;
  if(!tr||POST.treeBusy)return `<div class="ld-empty mut">${esc(t('Lade die Ordner …','Loading the folders …'))}</div>`;
  if(tr.err)return `<div class="note warn">${esc(tr.err)}</div>`;
  const row=(on,data,ico,name,badge,more)=>`<div class="ld-row${on?' on':''}" role="button" tabindex="0" ${data}><span class="postfi" aria-hidden="true">${postIc(ico)}</span><span class="ld-mid"><b>${esc(name)}</b></span><span class="ld-right">${badge}${more}</span></div>`;
  // the smart mailboxes on top like Apple Mail (Apple-Stil „1a“): every inbox, only unread, flagged or with attachment
  const smart=!POST.box&&(POST.unread||Object.values(POST.chips).some(Boolean));
  return row(!POST.box&&!smart,'data-all="1"','inbox',t('Alle Posteingänge','All inboxes'),'','')+
    [['unread','dot','Ungelesen','Unread',POST.unread],['flag','star','Markiert','Flagged',!!POST.chips.flag],['attach','clip','Mit Anhang','With attachment',!!POST.chips.attach]]
      .map(([k,ic,de,en,on])=>row(!POST.box&&on,`data-smart="${k}"`,ic,t(de,en),'','')).join('')+
    tr.accounts.map(a=>`<div class="ld-grp"><span>${esc(a.name)}</span><button type="button" class="ld-chip" data-new="${esc(a.id)}">${esc(t('+ Neuer Ordner','+ New folder'))}</button></div>`+
      (a.error?`<div class="note warn">${esc(t('Dieses Postfach war nicht erreichbar.','This mailbox was not reachable.'))}</div>`:'')+
      a.folders.map(f=>{const rl=POST_ROLE[f.role]||POST_ROLE.folder,name=rl[1]&&!f.depth?t(rl[1],rl[2]):f.name.split(a.delim).pop(),pad=f.depth?` style="padding-left:${8+f.depth*18}px"`:'';
        // Dominik 2026-10-21 „besser integriert“: a small menu at the folder like Apple Mail (⋯ or right click; a sheet from below on a phone)
        const k=a.id+'|'+f.name,fa=`data-fa2="${esc(a.id)}" data-ff2="${esc(f.name)}"`;
        // „Alle Mails hier einordnen“ (einordnen.py, Dominik 2026-10-24 „1-3“): at the inbox, the archive and every own folder
        const sortable=['inbox','archive','folder'].includes(f.role),sr=POST.sort||{},
          undo=sortable&&sr.undo&&sr.undo.account===a.id&&sr.undo.folder===f.name&&!['scan','move','back'].includes(sr.state)?sr.undo:null,hasMenu=f.own||sortable;
        const menu=POST.fmenu===k?`<div class="postmenu postfmenu" role="menu">`+
          (sortable?`<button type="button" role="menuitem" data-fo="sort" ${fa}>${postIc('folder')}<span>${esc(t('Alle Mails hier einordnen','Sort every mail here'))}<small>${esc(t('nach deinen Regeln, erst ein Vorschlag','by your rules, a proposal first'))}</small></span></button>`:'')+
          (undo?`<button type="button" role="menuitem" data-fo="sortback" ${fa}>${postIc('again')}<span>${esc(t('Einordnen rückgängig','Undo the sorting'))}<small>${esc(t(undo.n.toLocaleString(kalLoc())+' Mails zurück hierher',undo.n.toLocaleString(kalLoc())+' mails back here'))}</small></span></button>`:'')+
          (f.own?`<button type="button" role="menuitem" data-fo="rename" ${fa}>${postIc('pen')}${esc(t('Umbenennen','Rename'))}</button>`+
          `<button type="button" role="menuitem" data-fo="new" ${fa}>${postIc('folder')}${esc(t('Neuer Ordner darin','New folder inside'))}</button>`+
          `<button type="button" role="menuitem" class="bad" data-fo="remove" ${fa}>${postIc('trash')}<span>${esc(t('Ordner entfernen','Remove folder'))}<small>${esc(t('nur wenn er leer ist','only when it is empty'))}</small></span></button>`:'')+`</div>`:'';
        const fresh=POST.fnew&&POST.fnew.acct===a.id&&POST.fnew.inside===f.name?postFoldInput('new',a.id,f.name,'',(f.depth||0)+1):'';
        if(POST.fren===k)return postFoldInput('rename',a.id,f.name,name,f.depth||0)+fresh;
        return row(POST.box&&POST.box.account===a.id&&POST.box.folder===f.name,(f.role==='group'?'':`data-acct="${esc(a.id)}" data-f="${esc(f.name)}" data-role="${esc(f.role)}"`)+pad,rl[0],name,
          f.unseen?`<span class="ld-badge read">${f.unseen}</span>`:'',
          hasMenu?`<button type="button" class="postfmore" data-fa="${esc(a.id)}" data-ff="${esc(f.name)}" aria-label="${esc(t('Mehr zum Ordner','More for the folder'))}" aria-haspopup="menu" aria-expanded="${POST.fmenu===k}">${postIc('more')}</button>`+menu:'')+fresh}).join('')+
      (POST.fnew&&POST.fnew.acct===a.id&&!POST.fnew.inside?postFoldInput('new',a.id,'','',0):'')).join('')+
    `<div class="fh">${esc(t('⋯ oder Rechtsklick: alle Mails eines Ordners einordnen; bei eigenen Ordnern auch umbenennen, einen Ordner darin anlegen oder entfernen (nur leere). Ordner des Mail-Programms und von „Mails aufräumen“ bleiben, wie sie sind.','⋯ or right click: sort every mail of a folder; for own folders also rename, add a folder inside or remove (empty ones only). Folders of the mail program and of "Tidy mails" stay as they are.')+(NARROW()?'':' '+t('Mails ziehst du einfach auf einen Ordner.','Drag mails straight onto a folder.')))}</div>`}
// a folder named in its own row (Umbenennen, Neuer Ordner): Enter keeps it, Esc or leaving the field drops it
function postFoldInput(op,acct,folder,value,depth){const pad=depth?` style="padding-left:${8+depth*18}px"`:'';
  return `<div class="ld-row postfren"${pad}><span class="postfi" aria-hidden="true">${postIc('folder')}</span><input type="text" maxlength="100" data-fin="${op}" data-fa2="${esc(acct)}" data-ff2="${esc(folder)}" value="${esc(value)}" placeholder="${esc(t('Name des Ordners','Folder name'))}" aria-label="${esc(op==='new'?t('Name des neuen Ordners','Name of the new folder'):t('Neuer Name','New name'))}"></div>`}
function postTreeBind(list){
  const open=x=>{POST.box=x;POST.chips={};POST.unread=false;POST.fsheet=false;POST.sel=null;POST.msg=null;POST.pick=[];POST.done=null;POST.data=null;postLoad()};
  list.querySelectorAll('[data-all]').forEach(r=>r.onclick=()=>open(null));
  list.querySelectorAll('[data-smart]').forEach(r=>{const go=()=>postSmart(r.dataset.smart,true);r.onclick=go;r.onkeydown=e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();go()}}});
  list.querySelectorAll('[data-f]').forEach(r=>{const go=()=>open({account:r.dataset.acct,folder:r.dataset.f,role:r.dataset.role,name:r.querySelector('b').textContent});
    r.onclick=e=>{if(e.target.closest('[data-fa],.postfmenu'))return;go()};r.onkeydown=e=>{if(e.target===r&&(e.key==='Enter'||e.key===' ')){e.preventDefault();go()}}});
  list.querySelectorAll('[data-new]').forEach(b=>b.onclick=()=>postFolderNew(b.dataset.new,''));
  const menuAt=k=>{POST.fmenu=POST.fmenu===k?null:k;POST.fren=null;postDraw();const m=document.querySelector('#postview .postfmenu button');if(m)m.focus()};
  list.querySelectorAll('[data-fa]').forEach(b=>b.onclick=e=>{e.stopPropagation();menuAt(b.dataset.fa+'|'+b.dataset.ff)});
  list.querySelectorAll('[data-f]').forEach(r=>{const own=r.querySelector('[data-fa]');if(own)r.oncontextmenu=e=>{e.preventDefault();menuAt(own.dataset.fa+'|'+own.dataset.ff)}});
  list.querySelectorAll('[data-fo]').forEach(b=>b.onclick=e=>{e.stopPropagation();postFolderDo(b.dataset.fo,b.dataset.fa2,b.dataset.ff2)});
  list.querySelectorAll('.postfmenu').forEach(m=>m.onkeydown=e=>{const bs=[...m.querySelectorAll('button')],i=bs.indexOf(document.activeElement);
    if(e.key==='ArrowDown'||e.key==='ArrowUp'){e.preventDefault();bs[(i+(e.key==='ArrowDown'?1:bs.length-1))%bs.length].focus()}});
  list.querySelectorAll('[data-fin]').forEach(x=>{let done=false;const end=async keep=>{if(done)return;done=true;const n=x.value.trim(),op=x.dataset.fin,acct=x.dataset.fa2,f=x.dataset.ff2;
      POST.fren=null;POST.fnew=null;if(!keep||!n||(op==='rename'&&n===f.split(/[/.]/).pop())){postDraw();return}
      if(op==='new')await postFolderCall('/api/profile/mail/folder/new',{account:acct,folder:f,name:n});
      else{const d=await postFolderCall('/api/profile/mail/folder/rename',{account:acct,folder:f,name:n});if(d&&POST.box&&POST.box.folder===f){POST.box.folder=d.folder;POST.box.name=n}}
      postDraw()};
    x.onkeydown=e=>{if(e.key==='Enter'){e.preventDefault();end(true)}else if(e.key==='Escape'){e.preventDefault();e.stopPropagation();end(false)}};
    x.onblur=()=>end(true);x.onclick=e=>e.stopPropagation();setTimeout(()=>{x.focus();x.select()},0)});
  // beside its ⋯ (above it when there is no room below); on a phone the sheet from below (app.css); scrolling closes it
  const fm=list.querySelector('.postfmenu'),fb=fm&&list.querySelector('[data-fa][aria-expanded="true"]');
  if(fm&&fb&&!NARROW()){const r=fb.getBoundingClientRect(),h=fm.offsetHeight;
    fm.style.left=Math.max(8,Math.min(r.right-fm.offsetWidth,innerWidth-fm.offsetWidth-8))+'px';
    fm.style.top=(r.bottom+4+h>innerHeight-8?Math.max(8,r.top-4-h):r.bottom+4)+'px'}
  if(fm)(list.closest('.postfold')||list).addEventListener('scroll',()=>{if(POST.fmenu){POST.fmenu=null;postDraw()}},{once:true});
  // a click anywhere else closes the folder menu
  if(!POST.fmenuOff){POST.fmenuOff=true;
    document.addEventListener('pointerdown',e=>{if(POST.fmenu&&!e.target.closest('.postfmenu,[data-fa]')){POST.fmenu=null;postDraw()}},true);
    document.addEventListener('keydown',e=>{if(POST.fmenu&&e.key==='Escape'){e.stopPropagation();POST.fmenu=null;postDraw()}},true)}
  // drop: the dragged mails into this folder (one mailbox; into the trash only with Mails löschen)
  list.querySelectorAll('[data-f]').forEach(r=>postDropOn(r,()=>postCanDrop(r),()=>r.dataset.f))}
// the mailboxes and folders as a box of their own left of the list (Apple-Stil „1a“): shown unless hidden (O) and while dragging
function postFoldPaint(w){const fo=w.querySelector('.postfold');if(!fo)return;const on=ORD_ON&&(postFoldOn()||!!POST.drag);fo.hidden=!on;
  w.classList.toggle('postfolds',on);if(!on){fo.textContent='';return}
  if(!POST.tree&&!POST.treeBusy)postTreeLoad();
  fo.innerHTML=`<div class="posthead"><b>${esc(t('Postfächer','Mailboxes'))}</b><button type="button" class="pib" data-k="foldx" aria-label="${esc(t('Postfächer ausblenden','Hide the mailboxes'))}" data-tip="${esc(t('Ausblenden · O','Hide · O'))}">${postIc('close')}</button></div><div class="postfl">${postTreeHtml()}</div>`;
  fo.querySelector('[data-k=foldx]').onclick=()=>postFolds(false);postTreeBind(fo.querySelector('.postfl'))}
// where the dragged mails may go: a folder of their mailbox they may be moved to, the trash only with Mails löschen
function postCanDrop(r){const d=POST.drag;if(!d||r.dataset.acct!==d.acct||r.dataset.f===postSrc())return '';const role=r.dataset.role;
  if(role==='trash')return postDeletable()?'delete':'';
  if(role==='inbox')return POST.box&&postMovable()?'move':'';
  return ['folder','archive'].includes(role)&&postMovable()?'move':''}
function postDropOn(el,what,into){el.addEventListener('dragover',e=>{if(POST.drag&&what()){e.preventDefault();e.dataTransfer.dropEffect='move';el.classList.add('drop')}});
  el.addEventListener('dragleave',()=>el.classList.remove('drop'));
  el.addEventListener('drop',e=>{el.classList.remove('drop');const d=POST.drag,a=d&&what();if(!a)return;e.preventDefault();POST.drag=null;
    const w=$('postview'),msg=document.createElement('div');msg.className='postordmsg fh';if(w)w.querySelector('.postundo').appendChild(msg);
    if(d.ids.length>1){POST.pick=d.ids;postMany(a,a==='move'?into():'',msg)}else postAct(a,a==='move'?into():'',msg,'',d.ids[0]);
    if(w)postFoldPaint(w)})}
// Regel-Vorschlag (mailregeln.learn, Dominik 2026-10-20): after the third move of one sender into one folder
function postHintHtml(){const h=POST.hint;if(!h)return '';
  return `<div class="note posthint"><span>${esc(t('Mails von '+h.from+' legst du oft in „'+h.folder+'“. Eine Regel dafür anlegen?','You often put mails from '+h.from+' into "'+h.folder+'". Make a rule for it?'))}</span>`+
    `<span class="row"><button class="b p" type="button" data-h="apply">${esc(t('Regel anlegen und gleich anwenden','Make the rule and apply it now'))}</button><button class="b" type="button" data-h="save">${esc(t('Nur Regel','Rule only'))}</button><button class="b" type="button" data-h="never">${esc(t('Nicht mehr fragen','Do not ask again'))}</button><button class="b" type="button" data-h="no" aria-label="${esc(t('Schließen','Close'))}">✕</button></span></div>`}
function postHintBind(box){box.querySelectorAll('[data-h]').forEach(b=>b.onclick=()=>postHintDo(b.dataset.h))}
async function postHintDo(k){const h=POST.hint;if(!h)return;POST.hint=null;const J={method:'POST',headers:{'Content-Type':'application/json'}};
  if(k==='no'){postDraw();return}
  if(k==='never'){const {r,d}=await apiTry('/api/profile/mail/rules/never',{...J,body:JSON.stringify({account:h.account,from:h.from,folder:h.folder})});
    POST.note=r.ok?t('Gut, dafür frage ich nicht mehr.','Fine, I will not ask about this again.'):errSay(r.status,d.detail,'');postDraw();return}
  const {r,d}=await apiTry('/api/profile/mail/rules',{...J,body:JSON.stringify({account:h.account,when:{from:h.from},then:{folder:h.folder}})});
  if(!r.ok){POST.note=errSay(r.status,d.detail,'');postDraw();return}
  POST.note=t('Regel angelegt: neue Mails von '+h.from+' kommen nach „'+h.folder+'“.','Rule made: new mails from '+h.from+' go into "'+h.folder+'".');
  if(k==='apply'){const {r:r2,d:y}=await apiTry('/api/profile/mail/rules/'+encodeURIComponent(d.saved)+'/apply',{method:'POST'});
    if(r2.ok){POST.note+=' '+t(y.n+' Mails aus dem Posteingang dazu.',y.n+' mails from the inbox with it.');const m=y.moved&&y.moved[0];
      if(m&&y.moved.length===1)POST.done={acct:m.acct,mids:m.mids,folder:y.folder,src:'INBOX',n:Math.max(2,y.n)};postTreeShift(h.account,'','',0);postLoad();return}
    POST.note+=' '+errSay(r2.status,y.detail,'')}
  postDraw()}
async function postFolderCall(path,body){const {r,d}=await apiTry(path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
  if(!r.ok){alert(errSay(r.status,d.detail,''));return null}delete POST.folders[body.account];await postTreeLoad(true);return d}
// Neuer Ordner and Umbenennen happen in the row itself (postFoldInput), like Apple Mail
function postFolderNew(acct,inside){POST.fmenu=null;POST.fren=null;POST.fnew={acct,inside};postDraw()}
async function postFolderDo(op,acct,f){POST.fmenu=null;
  if(op==='sort')return postSortStart(acct,f);
  if(op==='sortback'){postDraw();if(confirm(t('Alle Mails des letzten Einordnens zurück in ihren Ordner holen?','Bring every mail of the last sorting back into its folder?')))postSortCall('/back');return}
  if(op==='new')return postFolderNew(acct,f);
  if(op==='rename'){POST.fnew=null;POST.fren=acct+'|'+f;postDraw();return}
  if(op==='remove'&&confirm(t('Den leeren Ordner „'+f+'“ entfernen? Mails werden nie gelöscht: einen Ordner mit Mails lässt der Spark stehen.','Remove the empty folder "'+f+'"? Mails are never deleted: a folder holding mails stays.'))){
    const d=await postFolderCall('/api/profile/mail/folder/remove',{account:acct,folder:f});if(d&&POST.box&&POST.box.folder===f){POST.box=null;postLoad()}}
  else postDraw()}
// Mails senden: the window (new mail, or the answer to the mail shown); the server checks every mail first
// (send/preview, its token), own words then go after the „Rückgängig“ time, text of the Spark only from the preview sheet
const postAddr=f=>{const m=/<([^>]+)>\s*$/.exec(f||'');return (m?m[1]:f||'').trim()};
// Weiterleiten (Mailclient Stufe C): the recipients typed, the original goes below the own words (senden._forward)
async function postWrite(m,fwd){if(POST.write&&!POST.prev&&(POST.write.text||'').trim()&&!confirm(t('Den Entwurf verwerfen?','Discard the draft?')))return;POST.sent='';POST.prev=null;
  POST.write=m&&fwd?{reply:'',forward:POST.sel,folder:postSrc(),files:!!(m.files&&m.files.length),to:'',cc:'',subject:/^(fwd?|wg)\s*:/i.test(m.subject||'')?m.subject:'Fwd: '+(m.subject||''),text:'',account:''}
    :m?{reply:POST.sel,to:postAddr(m.from),cc:'',subject:/^(re|aw|antw)\s*:/i.test(m.subject||'')?m.subject:'Re: '+(m.subject||''),text:'',account:''}
    :{reply:'',to:'',cc:'',subject:'',text:'',account:''};
  if(!m&&!POST.accts){const {r,d}=await apiTry('/api/profile/mail');POST.accts=r.ok?(d.accounts||[]):[]}
  if(!m&&POST.accts&&POST.accts.length)POST.write.account=POST.accts[0].id;POST.focus=true;postDraw()}
// Ziehen in einen Ordner (am Rechner): while a row (or the ticked ones) is dragged, the folders of its mailbox stand
// above the list; dropping there is the same move as the button, with „Rückgängig“
function postDrag(r,w){r.ondragstart=e=>{const id=r.dataset.id,ids=POST.pick.includes(id)?POST.pick.slice():[id],acct=id.split(':')[0];
    if(ids.some(i=>i.split(':')[0]!==acct)){e.preventDefault();return}e.dataTransfer.setData('text/plain',ids.length+'');e.dataTransfer.effectAllowed='move';
    // the folders open while dragging when they were hidden, and close again after (Dominik 2026-10-20)
    POST.drag={ids,acct};postFoldersFor(acct);setTimeout(()=>postFoldPaint(w),0)};
  r.ondragend=()=>setTimeout(()=>{if(!POST.drag)return;POST.drag=null;postFoldPaint(w)},60)}
// the compose window (Apple-Stil „3a“): its own window over the page like Apple Mail, the mail it answers stays readable
// beside it; at the computer it can be moved (by its head) and made small, on a phone it is a sheet over everything.
// „Senden“ of own words: the Spark checks the mail (send/preview), then it goes after POST_UNDO_MS with „Rückgängig“.
// Text the Spark wrote (a ✨ suggestion, a ✨ rewrite, a draft from Für dich: f.ai) keeps the preview sheet; only its
// „Senden“ sends.
let POST_UNDO_MS=10000;
function postWriteBox(w){const box=w.querySelector('.postcmp'),f=POST.write,p=POST.prev;if(!box)return;box.hidden=!f;
  if(!f){box.textContent='';box._f=null;return}
  box.classList.toggle('small',!!POST.cmpSmall&&!NARROW());
  // the same window drawn again (the list reloaded, suggestions came): only what changed, the caret stays where it is
  if(box._f===f&&box._prev===p&&box._small===!!POST.cmpSmall&&!POST.focus){const ta=box.querySelector('[data-f=text]');
    if(ta&&ta.value!==(f.text||''))ta.value=f.text||'';
    const sg=box.querySelector('.postsugs');if(sg&&f.reply){sg.outerHTML=postSugBox(f);postSugBind(box,f)}return}
  box._f=f;box._prev=p;box._small=!!POST.cmpSmall;
  if(POST.cmpAt&&!NARROW()){box.style.left=POST.cmpAt[0]+'px';box.style.top=POST.cmpAt[1]+'px';box.style.right='auto';box.style.bottom='auto'}else box.removeAttribute('style');
  const title=f.reply?t('Antworten','Reply'):f.forward?t('Weiterleiten','Forward'):t('Neue Mail','New mail');
  const head=`<div class="postcmph"><b>${esc(f.subject||title)}</b><span class="pgap"></span>`+
    (NARROW()?'':`<button type="button" class="pib" data-c="small" aria-label="${esc(POST.cmpSmall?t('Groß','Larger'):t('Klein','Smaller'))}" data-tip="${esc(POST.cmpSmall?t('Groß','Larger'):t('Klein','Smaller'))}">${postIc(POST.cmpSmall?'side':'more')}</button>`)+
    `<button type="button" class="pib postclose" data-close="1" aria-label="${esc(t('Verwerfen','Discard'))}" data-tip="${esc(t('Verwerfen · Esc','Discard · Esc'))}">${postIc('close')}</button></div>`;
  if(p){box.innerHTML=head+`<div class="postcmpb"><h3>${esc(t('So geht die Mail raus','This is the mail that goes out'))}</h3><dl class="ld-facts postprev">`+
      `<dt>${esc(t('Von','From'))}</dt><dd>${esc(p.from)}</dd>${p.server?`<dt>${esc(t('Über','Via'))}</dt><dd>${esc(p.server)}</dd>`:''}<dt>${esc(t('An','To'))}</dt><dd>${esc(p.to.join(', '))}</dd>`+
      (p.cc.length?`<dt>${esc(t('Kopie','Copy'))}</dt><dd>${esc(p.cc.join(', '))}</dd>`:'')+`<dt>${esc(t('Betreff','Subject'))}</dt><dd>${esc(p.subject||t('(ohne Betreff)','(no subject)'))}</dd>`+
      (p.files&&p.files.length?`<dt>${esc(t('Anhänge','Attachments'))}</dt><dd>${esc(p.files.join(', '))}</dd>`:'')+`</dl>`+
      `<div class="posttext">${esc(p.text)}</div><div class="fh">${esc(t('Der Text kommt vom Spark: schau ihn an, gesendet wird erst mit „Senden“.','The text comes from the Spark: look at it, it goes out only with "Send".'))}</div>`+
      `<div class="row postord"><button class="b p" type="button" data-s="send">${esc(t('Senden','Send'))}</button><button class="b" type="button" data-s="later">${esc(t('Später …','Later …'))}</button><button class="b" type="button" data-s="edit">${esc(t('Ändern','Edit'))}</button></div>`+postLaterPick()+`<div class="postordmsg fh"></div></div>`;
    box.querySelector('[data-s=edit]').onclick=()=>{POST.prev=null;postDraw()};
    postLaterBind(box,p);
    box.querySelector('[data-s=send]').onclick=e=>postSend(e.target,box.querySelector('.postordmsg'))}
  else{const many=!f.reply&&!f.forward&&POST.accts&&POST.accts.length>1,line=(k,de,en,inp)=>`<label class="postcl"><span>${esc(t(de,en))}</span>${inp}</label>`;
    box.innerHTML=head+`<div class="postcmpb postform">`+
      (many?line('account','Von','From',`<select data-f="account">${POST.accts.map(a=>`<option value="${esc(a.id)}"${a.id===f.account?' selected':''}>${esc(a.name+' · '+a.user)}</option>`).join('')}</select>`):'')+
      line('to','An','To','<input data-f="to" type="email" multiple maxlength="2000" autocomplete="off">')+
      line('cc','Kopie','Copy','<input data-f="cc" type="email" multiple maxlength="2000" autocomplete="off">')+
      line('subject','Betreff','Subject','<input data-f="subject" maxlength="200">')+
      `<textarea data-f="text" rows="10" maxlength="20000" aria-label="${esc(t('Text','Text'))}" placeholder="${esc(f.forward?t('Deine Zeilen über der weitergeleiteten Mail (darf leer bleiben)','Your lines above the forwarded mail (may stay empty)'):'')}"></textarea>`+
      (f.forward&&POST.msg&&POST.msg.files&&POST.msg.files.length?`<label class="chk"><input type="checkbox" data-f="files"${f.files?' checked':''}> ${esc(t('Anhänge mitschicken','Send the attachments along'))} (${esc(POST.msg.files.join(', '))})</label>`:'')+
      (f.reply?postSugBox(f)+`<div class="row posttone">${POST_TONE.map(([a,de,en])=>`<button class="ld-chip" type="button" data-r="${a}">✨ ${esc(t(de,en))}</button>`).join('')}</div>`:'')+
      `<div class="row postord postsendrow"><button class="b p" type="button" data-s="go">${postIc('sent')}<span>${esc(t('Senden','Send'))}</span></button>`+
      (f.ai?'':`<button class="b" type="button" data-s="later">${esc(t('Später …','Later …'))}</button>`)+
      `<span class="postordmsg fh">${esc(f.ai?t('Mit Text vom Spark: vor dem Senden kommt die Vorschau.','With text from the Spark: the preview comes before sending.'):t('Nach „Senden“ hast du '+Math.round(POST_UNDO_MS/1000)+' s für „Rückgängig“.','After "Send" you have '+Math.round(POST_UNDO_MS/1000)+' s for "Undo".'))}</span></div>`+postLaterPick()+`</div>`;
    for(const k of ['to','cc','subject','text']){const el=box.querySelector(`[data-f=${k}]`);el.value=f[k]||'';el.oninput=()=>{f[k]=el.value;if(k==='subject')box.querySelector('.postcmph b').textContent=el.value||title}}
    const ac=box.querySelector('[data-f=account]');if(ac)ac.onchange=()=>{f.account=ac.value};
    const fi=box.querySelector('[data-f=files]');if(fi)fi.onchange=()=>{f.files=fi.checked};
    if(f.reply){postSuggest(f.reply);postSugBind(box,f);
      box.querySelectorAll('[data-r]').forEach(b=>b.onclick=()=>postTone(b.dataset.r,box))}
    box.querySelector('[data-s=go]').onclick=e=>postGo(e.currentTarget,box.querySelector('.postordmsg'));
    postLaterBind(box,null);
    // ⌘/Strg+Enter sends like in a mail program
    box.querySelector('[data-f=text]').onkeydown=e=>{if(e.key==='Enter'&&(e.metaKey||e.ctrlKey)){e.preventDefault();box.querySelector('[data-s=go]').click()}};
    if(POST.focus){POST.focus=false;const ta=box.querySelector(f.reply||f.to?'[data-f=text]':'[data-f=to]');ta.focus({preventScroll:true})}}
  box.querySelector('[data-close]').onclick=()=>postDrop();
  const sm=box.querySelector('[data-c=small]');if(sm)sm.onclick=()=>{POST.cmpSmall=!POST.cmpSmall;postDraw()};
  postCmpMove(box)}
// a ✨ suggestion tapped: into the text, free to change; text of the Spark keeps the preview sheet (f.ai)
function postSugBind(box,f){box.querySelectorAll('[data-g]').forEach(b=>b.onclick=()=>{const v=POST.sug[f.reply].items[+b.dataset.g];f.text=v.text;f.picked=+b.dataset.g;f.ai=true;
  box.querySelectorAll('[data-g]').forEach(x=>x.classList.toggle('on',x===b));postDraw();
  const m=box.querySelector('.postordmsg');if(m){m.className='postordmsg fh';m.textContent=t('Mit Text vom Spark: vor dem Senden kommt die Vorschau.','With text from the Spark: the preview comes before sending.')}})}
// moving the window by its head (the computer); where it stands is kept while the page is open
function postCmpMove(box){const h=box.querySelector('.postcmph');if(!h||NARROW())return;
  h.onpointerdown=e=>{if(e.target.closest('button'))return;const r=box.getBoundingClientRect(),dx=e.clientX-r.left,dy=e.clientY-r.top;h.setPointerCapture(e.pointerId);
    h.onpointermove=m=>{const x=Math.max(0,Math.min(innerWidth-120,m.clientX-dx)),y=Math.max(0,Math.min(innerHeight-48,m.clientY-dy));POST.cmpAt=[x,y];
      box.style.left=x+'px';box.style.top=y+'px';box.style.right='auto';box.style.bottom='auto'};
    h.onpointerup=()=>{h.onpointermove=null;h.onpointerup=null}}}
// Später senden (Dominik 2026-10-21 „4“): usual times as chips and a free one; checked like „Senden“, then planned on the
// Spark (sealed until it goes out); the planned ones stand above the list and can be taken back until then
function postLaterTimes(){const n=new Date(),at=(d,h)=>{const x=new Date(n);x.setDate(x.getDate()+d);x.setHours(h,0,0,0);return x},out=[];
  if(at(0,18)-n>3600e3)out.push([t('Heute 18:00','Today 18:00'),at(0,18)]);out.push([t('Morgen 8:00','Tomorrow 8:00'),at(1,8)]);
  out.push([t('Montag 8:00','Monday 8:00'),at((8-n.getDay())%7||7,8)]);return out}
function postLaterPick(){return `<div class="row postlater" hidden>${postLaterTimes().map(([l,d])=>`<button class="ld-chip" type="button" data-lt="${d.getTime()}">${esc(l)}</button>`).join('')}`+
  `<input type="datetime-local" data-lti aria-label="${esc(t('Zeitpunkt','Time'))}"><button class="b p" type="button" data-ltgo>${esc(t('Planen','Plan'))}</button></div>`}
function postLaterBind(box,p){const b=box.querySelector('[data-s=later]'),row=box.querySelector('.postlater');if(!b||!row)return;
  b.onclick=()=>{row.hidden=!row.hidden};const msg=()=>box.querySelector('.postordmsg');
  row.querySelectorAll('[data-lt]').forEach(c=>c.onclick=()=>postLater(+c.dataset.lt,p,msg()));
  row.querySelector('[data-ltgo]').onclick=()=>{const v=row.querySelector('[data-lti]').value;if(v)postLater(new Date(v).getTime(),p,msg())}}
async function postLater(ms,p,msg){const f=POST.write,J={method:'POST',headers:{'Content-Type':'application/json'}};
  if(msg){msg.className='postordmsg fh';msg.textContent=t('Einen Moment …','One moment …')}
  if(!p){const {r,d}=await apiTry('/api/profile/mail/send/preview',{...J,body:JSON.stringify(f)});
    if(!r.ok){if(msg){msg.className='postordmsg err';msg.textContent=errSay(r.status,d.detail,'')}return}p=d}
  const {r,d}=await apiTry('/api/profile/mail/send',{...J,body:JSON.stringify({token:p.token,at:Math.round(ms/1000)})});
  if(!r.ok){if(msg){msg.className='postordmsg err';msg.textContent=errSay(r.status,d.detail,'')}return}
  POST.sent=t('Geplant für ','Planned for ')+postLaterWhen(d.at)+'.';POST.write=null;POST.prev=null;postLaterLoad();postDraw()}
const postLaterWhen=s=>new Date(s*1000).toLocaleString(kalLoc(),{weekday:'short',day:'numeric',month:'short',hour:'2-digit',minute:'2-digit'});
async function postLaterLoad(){if(!SEND_ON)return;const {r,d}=await apiTry('/api/profile/mail/later');POST.later=r.ok?d.items:[];const w=$('postview');if(w)postUndo(w)}
function postLaterHtml(){const l=POST.later||[];if(!l.length)return '';const wait=l.filter(x=>x.state==='wartet').length;
  const say={gesendet:t('gesendet','sent'),'nicht gesendet':t('nicht gesendet','not sent'),unklar:t('unklar, schau in Gesendet','unclear, look in Sent'),sendet:t('wird gesendet','sending')};
  return `<details class="note postlaterl"${POST.laterOpen?' open':''}><summary>${esc(wait?t(wait+(wait>1?' Mails geplant':' Mail geplant'),wait+(wait>1?' mails planned':' mail planned')):t('Geplante Mails','Planned mails'))}</summary>`+
    l.map(x=>`<div class="ld-row"><span class="ld-mid"><b>${esc(x.subject||t('(ohne Betreff)','(no subject)'))}</b><small>${esc(t('an ','to ')+x.to+' · '+postLaterWhen(x.at)+(x.state==='wartet'?'':' · '+(say[x.state]||x.state)))}</small></span>`+
      `<span class="ld-right"><button class="ld-chip" type="button" data-ld="${esc(x.id)}">${esc(x.state==='wartet'?t('Zurücknehmen','Take back'):t('Entfernen','Remove'))}</button></span></div>`).join('')+`</details>`}
function postLaterListBind(box){const d=box.querySelector('.postlaterl');if(!d)return;d.ontoggle=()=>{POST.laterOpen=d.open};
  d.querySelectorAll('[data-ld]').forEach(b=>b.onclick=async()=>{const x=POST.later.find(y=>y.id===b.dataset.ld);
    if(x&&x.state==='wartet'&&!confirm(t('Diese geplante Mail zurücknehmen? Sie wird nicht gesendet.','Take back this planned mail? It will not be sent.')))return;
    const {r,d:y}=await apiTry('/api/profile/mail/later/'+encodeURIComponent(b.dataset.ld),{method:'DELETE'});if(r.ok)POST.later=y.items;const w=$('postview');if(w)postUndo(w)})}
// Alle Mails hier einordnen (einordnen.py, Dominik 2026-10-24 „1-3“): a proposal for every mail of the folder, then
// „Verschieben“; the run goes on in the background (asked every 2 s while it runs), „Abbrechen“ stops it after the step
async function postSortLoad(){if(!ORD_ON)return;const {r,d}=await apiTry('/api/profile/mail/einordnen');POST.sort=r.ok?d:null;
  const w=$('postview');if(w)postUndo(w);clearTimeout(POST.sortT);
  if(r.ok&&['scan','move','back'].includes(d.state))POST.sortT=setTimeout(()=>{if($('postview'))postSortLoad()},2000)}
async function postSortCall(path,body){const {r,d}=await apiTry('/api/profile/mail/einordnen'+path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body||{})});
  if(!r.ok){POST.note=errSay(r.status,d.detail,'');postDraw();return}POST.sort=d;postSortLoad()}
function postSortStart(acct,f){postDraw();postSortCall('',{account:acct,folder:f})}
const postSortName=f=>!f||f.toUpperCase()==='INBOX'?t('Posteingang','Inbox'):f;
// only while a run is there (Dominik 2026-10-24: the bar stayed); „Rückgängig“ of the last run stays in the folder's „⋯“
function postSortHtml(){const s=POST.sort;if(!s||!s.state)return '';const n=x=>Number(x||0).toLocaleString(kalLoc());
  const into=(s.by||[]).reduce((a,x)=>a+x[1],0),where=postSortName(s.folder),btn=(k,label,p)=>`<button class="b${p?' p':''}" type="button" data-so="${k}">${esc(label)}</button>`;
  let txt='',acts='';
  if(s.state==='scan'){txt=t('Ordne „'+where+'“ ein: '+n(s.looked)+' von '+n(Math.min(s.total,50000)||s.looked)+' Mails angesehen …','Sorting "'+where+'": '+n(s.looked)+' of '+n(Math.min(s.total,50000)||s.looked)+' mails looked at …');acts=btn('stop',t('Abbrechen','Stop'))}
  else if(s.state==='ready'){txt=into?t('Vorschlag für „'+where+'“: ','Proposal for "'+where+'": ')+(s.by||[]).slice(0,6).map(x=>t(n(x[1])+' nach ',n(x[1])+' to ')+postSortName(x[0])).join(', ')+((s.by||[]).length>6?' …':'')+t('; '+n(s.stays)+' bleiben.','; '+n(s.stays)+' stay.')
      :t('In „'+where+'“ passt keine deiner Regeln: alle '+n(s.stays)+' Mails bleiben.','None of your rules fits in "'+where+'": all '+n(s.stays)+' mails stay.');
    if(s.cut)txt+=' '+t('Angesehen wurden die neuesten 50.000.','The newest 50,000 were looked at.');
    acts=(into?btn('go',t(n(into)+' verschieben','Move '+n(into)),true):'')+btn('stop',into?t('Verwerfen','Discard'):t('Schließen','Close'))}
  else if(s.state==='move'){txt=t('Verschiebe: '+n(s.moved)+' von '+n(into||s.moved)+' …','Moving: '+n(s.moved)+' of '+n(into||s.moved)+' …');acts=btn('stop',t('Abbrechen','Stop'))}
  else if(s.state==='back'){txt=t('Hole zurück nach „'+where+'“: '+n(s.moved)+' von '+n(s.total)+' …','Bringing back to "'+where+'": '+n(s.moved)+' of '+n(s.total)+' …');acts=btn('stop',t('Abbrechen','Stop'))}
  else if(s.state==='error')txt=t('Einordnen ging nicht: ','Sorting did not work: ')+({renumbered:t('der Mail-Server hat den Ordner inzwischen neu nummeriert, bitte noch einmal.','the mail server has numbered the folder anew since, please once more.'),'not reachable':t('das Postfach war nicht erreichbar.','the mailbox was not reachable.')}[s.err]||t('bitte noch einmal.','please once more.'));
  else if(s.state)txt=(s.state==='stopped'?t('Abgebrochen. ','Stopped. '):'')+t(n(s.moved)+' Mails '+(s.kind==='back'?'zurückgeholt.':'verschoben.'),n(s.moved)+' mails '+(s.kind==='back'?'brought back.':'moved.'));
  if(['done','stopped','error'].includes(s.state))acts+=btn('stop',t('Schließen','Close'));
  if(s.undo&&!['scan','move','back'].includes(s.state))acts=btn('back',t('Rückgängig: '+n(s.undo.n)+' zurück nach „'+postSortName(s.undo.folder)+'“','Undo: '+n(s.undo.n)+' back to "'+postSortName(s.undo.folder)+'"'))+acts;
  return `<div class="note postsort" role="status"><span>${esc(txt)}</span><span class="row">${acts}</span></div>`}
function postSortBind(box){box.querySelectorAll('[data-so]').forEach(b=>b.onclick=()=>{const k=b.dataset.so;
  if(k==='go'&&!confirm(t('Jetzt verschieben? Es wird nichts gelöscht, und „Rückgängig“ holt alles zurück.','Move now? Nothing is deleted, and "Undo" brings everything back.')))return;
  if(k==='back'&&!confirm(t('Alle Mails des letzten Einordnens zurück in ihren Ordner holen?','Bring every mail of the last sorting back into its folder?')))return;
  b.disabled=true;postSortCall('/'+k)})}
// leaving the form: what was typed is asked about first, nothing else is lost
function postDrop(){const f=POST.write;
  if(f&&!POST.prev&&(f.text||'').trim()&&!confirm(t('Den Entwurf verwerfen?','Discard the draft?')))return;
  POST.write=null;POST.prev=null;postDraw()}
// „Senden“ in the window: the Spark checks the mail first (the same check as the preview sheet); own words then wait
// POST_UNDO_MS with „Rückgängig“, text of the Spark shows the preview sheet
async function postGo(b,msg){const f=POST.write;b.disabled=true;msg.className='postordmsg fh';msg.textContent=t('Einen Moment …','One moment …');
  const {r,d}=await apiTry('/api/profile/mail/send/preview',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(f)});
  if(POST.write!==f)return;
  if(!r.ok){b.disabled=false;msg.className='postordmsg err';msg.textContent=errSay(r.status,d.detail,'');return}
  if(f.ai){POST.prev=d;postDraw();return}
  if(POST.pending)postSendNow(POST.pending);   // one waiting mail at a time: the one before goes now
  const job={p:d,f,until:Date.now()+POST_UNDO_MS};POST.pending=job;POST.write=null;POST.prev=null;POST.sent='';
  job.timer=setTimeout(()=>postSendNow(job),POST_UNDO_MS);job.tick=setInterval(postPendPaint,500);postDraw()}
function postPendHtml(){const j=POST.pending;if(!j)return '';const n=Math.max(0,Math.ceil((j.until-Date.now())/1000));
  return `<div class="note postpend"><span>${esc(t('Wird gesendet an ','Sending to ')+j.p.to.join(', '))} <b class="postpendn">${esc(t('in '+n+' s','in '+n+' s'))}</b></span>`+
    `<button class="b p" type="button" data-s="undo">${esc(t('Rückgängig','Undo'))}</button><button class="b" type="button" data-s="now">${esc(t('Jetzt senden','Send now'))}</button></div>`}
function postPendPaint(){const j=POST.pending,el=document.querySelector('#postview .postpendn');if(!j||!el)return;
  const n=Math.max(0,Math.ceil((j.until-Date.now())/1000));el.textContent=t('in '+n+' s','in '+n+' s')}
function postPendBind(box){const u=box.querySelector('[data-s=undo]'),n=box.querySelector('[data-s=now]'),j=POST.pending;if(!j)return;
  // „Rückgängig“: nothing went out, the window is back with everything typed
  if(u)u.onclick=()=>{if(POST.pending!==j)return;clearTimeout(j.timer);clearInterval(j.tick);POST.pending=null;POST.write=j.f;POST.focus=true;postDraw()};
  if(n)n.onclick=()=>postSendNow(j)}
async function postSendNow(j){if(POST.pending!==j)return;clearTimeout(j.timer);clearInterval(j.tick);POST.pending=null;postDraw();
  const {r,d}=await apiTry('/api/profile/mail/send',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({token:j.p.token})});
  if(!r.ok){POST.write=j.f;POST.sent='';POST.err='';postDraw();const m=document.querySelector('#postview .postcmp .postordmsg');
    if(m){m.className='postordmsg err';m.textContent=t('Nicht gesendet: ','Not sent: ')+errSay(r.status,d.detail,'')}return}
  POST.sent=t('Gesendet an ','Sent to ')+d.sent+t(' Empfänger',d.sent===1?' recipient':' recipients')+(d.refused?t(', abgelehnt: ',', refused: ')+d.refused:'')+'.';postDraw()}
// a mail still waiting is not lost by leaving the page without a word
addEventListener('beforeunload',e=>{if(POST.pending){e.preventDefault();e.returnValue=''}});
async function postSend(b,msg){b.disabled=true;msg.className='postordmsg fh';msg.textContent=t('Sende …','Sending …');
  const {r,d}=await apiTry('/api/profile/mail/send',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({token:POST.prev.token})});
  if(!r.ok){b.disabled=false;msg.className='postordmsg err';msg.textContent=errSay(r.status,d.detail,'');if(r.status===409){POST.prev=null;setTimeout(postDraw,1500)}return}
  POST.sent=t('Gesendet an ','Sent to ')+d.sent+t(' Empfänger',d.sent===1?' recipient':' recipients')+(d.refused?t(', abgelehnt: ',', refused: ')+d.refused:'')+'.';
  POST.write=null;POST.prev=null;postDraw()}
// „Als Termin“: the page Kalender with the subject in „Schnell eintragen“; the panel reads it there by its fixed
// rules, nothing is saved before „Eintragen“
function postAsEvent(m){KAL.q=postTopic(m.subject,200);KAL.qi=null;KAL.qfocus=true;
  icTabSet('cal','show');goSec('cal')}
// keys on the page (Dominik 2026-10-19 „5a“, 2026-10-20): J/K next and previous, R reply, F forward, T as appointment,
// E archive, U read or unread, S flag, V move, G rule from this, N new mail; Esc closes
// (the mail, or the window being written)
document.addEventListener('keydown',e=>{if(!$('post')||!$('post').classList.contains('on')||!$('postview'))return;
  if(e.key==='Escape'&&POST.write){e.preventDefault();postDrop();return}   // also from inside the form
  if(/^(INPUT|TEXTAREA|SELECT)$/.test((e.target&&e.target.tagName)||'')||e.metaKey||e.ctrlKey||e.altKey)return;
  const items=postItems(),i=items.findIndex(x=>x.id===POST.sel),k=e.key.toLowerCase();
  if(k==='j'||k==='k'){const n=items[k==='j'?Math.min(i+1,items.length-1):Math.max(i-1,0)];if(n){e.preventDefault();postRead(n.id)}return}
  if(k==='o'&&ORD_ON&&!POST.write){e.preventDefault();postFolds(!postFoldOn());return}
  if(k==='escape'&&POST.fsheet){POST.fsheet=false;postDraw();return}
  if(k==='escape'&&POST.menu&&POST.menuAt===POST.sel){POST.menu='';postDetail($('postview'));return}
  if(k==='escape'&&POST.sel&&!POST.write){POST.sel=null;POST.msg=null;postDraw();return}
  if(k==='n'&&SEND_ON&&!POST.write){e.preventDefault();postWrite(null);return}
  if(!POST.sel||POST.write)return;
  const m=POST.msg&&!POST.msg.err?POST.msg:null;
  if(k==='r'&&SEND_ON&&m){e.preventDefault();postWrite(m);return}
  if(k==='f'&&SEND_ON&&m){e.preventDefault();postWrite(m,true);return}
  if(k==='t'&&m&&typeof CAL_ON!=='undefined'&&CAL_ON){e.preventDefault();postAsEvent(m);return}
  if(!ORD_ON||!m)return;
  const x=items[i];
  if(k==='e'){e.preventDefault();postAct('archive','',null)}
  else if(k==='u'){if(x){e.preventDefault();postAct(x.unread?'read':'unread','',null)}}
  else if(k==='s'){if(x){e.preventDefault();postAct(x.flagged?'unflag':'flag','',null)}}
  else if(k==='v'&&postMovable()){e.preventDefault();postMenu('pick')}
  else if(k==='g'){e.preventDefault();postRuleFrom(m)}
  else if((e.key==='Delete'||e.key==='Backspace')&&postDeletable()){e.preventDefault();postAct('delete','',null)}});
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
const RULES={data:null,form:null,msg:'',err:'',test:null,undo:null,stats:null,statOpen:false,statWait:false};
async function postRulesLoad(){const {r,d}=await apiTry('/api/profile/mail/rules');RULES.data=r.ok?d:null;RULES.err=r.ok?'':errSay(r.status,d.detail,'');postRulesDraw();postStatLoad()}
// Mail-Statistik (mailregeln.stats, Dominik 2026-10-21 „6“): who writes most in 30 days, mails a week; „Regel …“ per sender
async function postStatLoad(){const {r,d}=await apiTry('/api/profile/mail/stats');RULES.stats=r.ok&&!d.loading?d:null;
  if(r.ok&&d.loading&&!RULES.statWait){RULES.statWait=true;setTimeout(()=>{RULES.statWait=false;if($('postrules'))postStatLoad()},4000)}postRulesDraw()}
function postStatHtml(){const s=RULES.stats;if(!s||!s.total)return '';const max=Math.max(1,...s.senders.map(x=>x.n));
  const wk=s.weeks.map((n,i)=>`<span class="postwk"><b>${n}</b><small>${esc(i?t('vor '+i+(i>1?' Wochen':' Woche'),i+(i>1?' weeks ago':' week ago')):t('diese Woche','this week'))}</small></span>`).join('');
  return `<details class="note poststat"${RULES.statOpen?' open':''}><summary>${esc(t('Wer schreibt dir am meisten (30 Tage, '+s.total+' Mails, '+s.unread+' ungelesen)','Who writes most (30 days, '+s.total+' mails, '+s.unread+' unread)'))}</summary>`+
    `<div class="postwks">${wk}</div><div class="ld-list">`+s.senders.map((x,i)=>`<div class="ld-row"><span class="ld-mid"><b>${esc(x.name||x.addr)}</b><small>${esc((x.name?x.addr+' · ':'')+x.n+t(' Mails',' mails')+(x.unread?', '+x.unread+t(' ungelesen',' unread'):''))}</small>`+
      `<span class="poststatbar" style="width:${Math.round(100*x.n/max)}%"></span></span><span class="ld-right">${x.rule?`<span class="ld-badge read">${esc(t('hat Regel','has rule'))}</span>`:`<button class="ld-chip" type="button" data-st="${i}">${esc(t('Regel …','Rule …'))}</button>`}</span></div>`).join('')+`</div></details>`}
function postStatBind(b){const d=b.querySelector('.poststat');if(!d)return;d.ontoggle=()=>{RULES.statOpen=d.open};
  d.querySelectorAll('[data-st]').forEach(x=>x.onclick=()=>{const s=RULES.stats.senders[+x.dataset.st];
    RULES.form={account:s.acct||((RULES.data.accounts||[])[0]||{}).id||'',when:{from:s.addr,subject:'',to:'',attach:false},then:{folder:'',read:false,flag:false,quiet:false}};RULES.test=null;postRulesDraw()})}
const postRulesDraw=()=>{const b=$('postrules');if(b)postRulesPaint(b)};
function postRuleWhen(r){const w=r.when,p=[];if(w.from)p.push((w.from.startsWith('@')?t('Absender endet auf ','Sender ends with '):t('Absender ist ','Sender is '))+w.from);
  if(w.subject)p.push(t('Betreff enthält „','Subject contains "')+w.subject+t('“','"'));if(w.to)p.push(t('an ','to ')+w.to);if(w.attach)p.push(t('mit Anhang','with attachment'));return p.join(t(' und ',' and '))}
function postRuleThen(r){const x=r.then,p=[];if(x.folder)p.push('→ '+x.folder);if(x.read)p.push(t('gelesen','read'));if(x.flag)p.push('★');if(x.quiet)p.push(t('nicht in „Für dich“','not in "For you"'));return p.join(', ')}
function postRulesPaint(b){const d=RULES.data;
  if(RULES.form){postRuleForm(b);return}
  if(!d){b.innerHTML=RULES.err?`<div class="note warn">${esc(RULES.err)}</div>`:`<div class="ld-empty mut">${esc(t('Lade die Regeln …','Loading the rules …'))}</div>`;return}
  const rows=d.rules.map((r,i)=>`<div class="ld-row" data-rid="${esc(r.id)}"><span class="ld-mid"><b>${esc(postRuleWhen(r))}</b><small>${esc(postRuleThen(r)+(r.box?' · '+r.box:'')+(r.except&&r.except.length&&!d.learn?' · '+t(r.except.length+' Ausnahmen',r.except.length+' exceptions'):''))}</small>${d.learn?postRuleLearnHtml(r):''}</span>`+
    `<span class="ld-right"><span class="ld-badge ${r.on===false?'off':'read'}">${esc(r.on===false?(r.paused?t('pausiert, oft korrigiert','paused, often corrected'):t('pausiert','paused')):d.learn?t('an','on'):t('diesen Monat ','this month ')+r.month)}</span>`+
    `<button class="ld-chip" type="button" data-up="${i}" aria-label="${esc(t('nach oben','up'))}"${i?'':' disabled'}>▲</button><button class="ld-chip${r.paused&&r.on===false?' on':''}" type="button" data-on="${esc(r.id)}">${esc(r.on===false?(r.paused?t('Wieder an','On again'):t('Weiter','Resume')):t('Pause','Pause'))}</button>`+
    `<button class="ld-chip" type="button" data-ed="${esc(r.id)}">${esc(t('Ändern','Edit'))}</button><button class="ld-chip" type="button" data-del="${esc(r.id)}">${esc(t('Löschen','Delete'))}</button></span></div>`).join('');
  b.innerHTML=`<div class="ld-tools"><button class="b p" type="button" data-k="new">${esc(t('+ Neue Regel','+ New rule'))}</button></div>`+
    (RULES.msg?`<div class="note">${esc(RULES.msg)}${RULES.undo?` <button class="b" type="button" data-k="undo">${esc(t('Rückgängig','Undo'))}</button>`:''}</div>`:'')+
    (RULES.err?`<div class="note warn">${esc(RULES.err)}</div>`:'')+postSugHtml(d.suggest||[])+(d.learn?postFixHtml(d.fixes||[]):'')+postStatHtml()+
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
  b.querySelectorAll('[data-ed]').forEach(x=>x.onclick=()=>{const r=d.rules.find(y=>y.id===x.dataset.ed);RULES.form=JSON.parse(JSON.stringify({id:r.id,account:r.account,when:r.when,then:r.then,on:r.on}));RULES.test=null;postRulesDraw()});
  b.querySelectorAll('[data-sg]').forEach(x=>x.onclick=()=>postSugDo(d.suggest.find(y=>y.id===x.dataset.sid),x.dataset.sg,call));postStatBind(b);
  // Sortieren aus Korrekturen lernen, Stufe 3: „Rückgängig“ at a correction, „Regel ändern“ opens the form, an exception off the rule
  b.querySelectorAll('[data-fu]').forEach(x=>x.onclick=()=>call('/api/profile/mail/rules/fixes/'+encodeURIComponent(x.dataset.fu)+'/undo',{method:'POST'}));
  b.querySelectorAll('[data-fe]').forEach(x=>x.onclick=()=>{const r=d.rules.find(y=>y.id===x.dataset.fe);if(!r)return;RULES.form=JSON.parse(JSON.stringify({id:r.id,account:r.account,when:r.when,then:r.then,on:r.on}));RULES.test=null;postRulesDraw()});
  b.querySelectorAll('[data-xr]').forEach(x=>x.onclick=()=>{const r=d.rules.find(y=>y.id===x.dataset.xr),a=r&&r.except[+x.dataset.xi];if(!a)return;
    if(confirm(t('„'+a+'“ ist keine Ausnahme mehr: die Regel nimmt seine neuen Mails wieder. Mails bleiben, wo sie sind.','"'+a+'" is no exception any more: the rule takes its new mails again. Mails stay where they are.')))
      call('/api/profile/mail/rules/'+encodeURIComponent(r.id)+'/except',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({from:a})})})}
// Korrekturen (30 Tage) (mailregeln.fix_list, plan mail-lernen 7a): what the person re-sorted after the Spark, with what became
// of it; „Rückgängig“ takes back the exception or pause it made (never moves a mail), „Regel ändern“ opens the rule
const postFixFolder=f=>f===''?t('Falsch sortiert','Wrongly sorted'):f.toUpperCase()==='INBOX'?t('Posteingang','Inbox'):f;
const POST_FIX_STATE={wartet:['wartet','waiting','due'],ausnahme:['Ausnahme gesetzt','exception set','read'],pausiert:['Regel pausiert','rule paused','off'],
  bleibt:['nicht wieder verschoben','not moved again','read'],zurueck:['zurückgenommen','taken back','off']};
function postFixHtml(list){if(!list.length)return '';
  return `<div class="ld-list postfix"><div class="ld-grp"><span>${esc(t('Korrekturen (30 Tage)','Corrections (30 days)'))}</span><span>${list.length}</span></div>`+list.map(x=>{const st=POST_FIX_STATE[x.state]||POST_FIX_STATE.bleibt;
    return `<div class="ld-row"><span class="ld-mid"><b>${esc(x.from||'–')}</b><small>${esc(postFixFolder(x.von)+' → '+postFixFolder(x.nach)+' · '+
      (x.by==='tidy'?t('Postfach aufräumen','Inbox tidying'):x.rule?t('Regel „'+x.rule+'“','Rule "'+x.rule+'"'):t('Regel gelöscht','rule deleted'))+' · '+cxDay(x.t)+(x.box?' · '+x.box:''))}</small></span>`+
    `<span class="ld-right"><span class="ld-badge ${st[2]}">${esc(t(st[0],st[1]))}</span>`+
    (x.undo&&x.state!=='wartet'?`<button class="ld-chip" type="button" data-fu="${esc(x.id)}">${esc(t('Rückgängig','Undo'))}</button>`:'')+
    (x.rid?`<button class="ld-chip" type="button" data-fe="${esc(x.rid)}">${esc(t('Regel ändern','Change the rule'))}</button>`:'')+`</span></div>`}).join('')+'</div>'}
// per rule: „N genommen · M korrigiert“ (this month's count, corrections of 30 days) with a bar, its exceptions to remove
function postRuleLearnHtml(r){const n=r.month||0,k=r.fixed||0,ex=r.except||[];
  return `<small>${esc(t(n+' genommen (Monat) · '+k+' korrigiert (30 Tage)',n+' taken (month) · '+k+' corrected (30 days)'))}</small>`+
    (n+k?`<span class="poststatbar${r.on===false?' warn':''}" style="width:${Math.round(100*n/(n+k))}%"></span>`:'')+
    (ex.length?`<details class="postexc"><summary>${esc(t(ex.length+(ex.length>1?' Ausnahmen':' Ausnahme'),ex.length+(ex.length>1?' exceptions':' exception')))}</summary>`+
      ex.map((a,i)=>`<span class="postexcrow"><span>${esc(a)}</span><button class="ld-chip" type="button" data-xr="${esc(r.id)}" data-xi="${i}" aria-label="${esc(t('Ausnahme entfernen','Remove the exception'))}">✕</button></span>`).join('')+'</details>':'')}
// Regel-Vorschläge aus dem Ablegen (Dominik 2026-10-21 „ok“): what the night found below the KI folder; a rule only after a click
function postSugHtml(list){if(!list.length)return '';
  return `<div class="ld-list postsug"><div class="ld-grp"><span>${esc(t('Vorschläge aus deinem Ablegen','Suggestions from your filing'))}</span></div>`+list.map(x=>
    `<div class="ld-row"><span class="ld-mid"><b>${esc(t('Mails von ','Mails from ')+x.from)}</b><small>${esc(t('legst du in „'+x.folder+'“ ('+x.n+'×)','you put into "'+x.folder+'" ('+x.n+'×)')+
    (x.inbox?t(' · '+x.inbox+' liegen gerade im Posteingang',' · '+x.inbox+' in the inbox now'):'')+(x.box?' · '+x.box:''))}</small></span>`+
    `<span class="ld-right"><button class="ld-chip" type="button" data-sg="apply" data-sid="${esc(x.id)}">${esc(x.inbox?t('Regel anlegen und ablegen','Make the rule and file'):t('Regel anlegen','Make the rule'))}</button>`+
    (x.inbox?`<button class="ld-chip" type="button" data-sg="save" data-sid="${esc(x.id)}">${esc(t('Nur Regel','Rule only'))}</button>`:'')+
    `<button class="ld-chip" type="button" data-sg="never" data-sid="${esc(x.id)}">${esc(t('Nicht mehr fragen','Do not ask again'))}</button></span></div>`).join('')+'</div>'}
async function postSugDo(s,k,call){if(!s)return;const J={method:'POST',headers:{'Content-Type':'application/json'}};
  if(k==='never'){await call('/api/profile/mail/rules/never',{...J,body:JSON.stringify({account:s.account,from:s.from,folder:s.folder})});return}
  const {r,d:y}=await apiTry('/api/profile/mail/rules',{...J,body:JSON.stringify({account:s.account,when:{from:s.from},then:{folder:s.folder}})});
  if(!r.ok){RULES.err=errSay(r.status,y.detail,'');postRulesDraw();return}
  RULES.data=y;RULES.err='';RULES.undo=null;RULES.msg=t('Regel angelegt: neue Mails von '+s.from+' kommen nach „'+s.folder+'“.','Rule made: new mails from '+s.from+' go into "'+s.folder+'".');
  if(k==='apply'&&s.inbox){const {r:r2,d:z}=await apiTry('/api/profile/mail/rules/'+encodeURIComponent(y.saved)+'/apply',{method:'POST'});
    if(r2.ok){RULES.msg+=' '+t(z.n+' Mails aus dem Posteingang dazu.',z.n+' mails from the inbox with it.');const m=z.moved&&z.moved[0];RULES.undo=m&&z.moved.length===1?{account:m.acct,folder:z.folder,mids:m.mids}:null;POST.data=null}
    else RULES.err=errSay(r2.status,z.detail,'')}
  postRulesDraw()}
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
// the subject without Re:, AW:, Fwd: … (Dominik 2026-10-20: the rule takes the mail's subject too, free to change)
const postTopic=(x,n=80)=>(x||'').replace(/^((re|aw|antw|fwd?|wg)\s*:\s*)+/i,'').trim().slice(0,n);
function postRuleFrom(m){const acct=(POST.sel||'').split(':')[0];RULES.form={account:acct,when:{from:postAddr(m.from).toLowerCase(),subject:postTopic(m.subject),to:'',attach:false},then:{folder:'',read:false,flag:false,quiet:false}};
  RULES.test=null;icTabSet('post','regeln');postOpen()}
// Für dich (fuerdich.js, Stufe 2, Dominik 2026-10-18 „5a“): „Antwort entwerfen“ opens the mail in Posteingang and its
// answer with the Antwortvorschläge, „Kündigung entwerfen“ a new mail with the fixed draft of the Spark; both send only
// from the preview sheet here
window.postFromFuer=async(id,draft)=>{icTabSet('post','show');POST.box=null;POST.write=null;POST.prev=null;goSec('post');
  if(draft){await postWrite(null);if(POST.write)Object.assign(POST.write,{to:draft.to||'',subject:draft.subject||'',text:draft.text||'',ai:true});postDraw();return}
  await postRead(id);if(POST.sel===id&&POST.msg&&!POST.msg.err)await postWrite(POST.msg)};
