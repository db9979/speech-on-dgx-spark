// Kontakte wie Apple Kontakte (Apple-Stil „6a“, Dominik 2026-10-21 „Weiter“): a page of its own in the menu, like
// Kalender, E-Mail and Listen. Left the address books as groups, a search and A–Z with a letter bar; right the card
// with Nachricht, Anruf, Mail, Termin and Teilen, its phones, mails, addresses and „Mit Anna“ (the next appointment
// and the newest mail, GET /api/profile/contacts/with). „Bearbeiten“ (admin switch „Kontakte ändern“) edits like
// Apple with − and + per field; „Fertig“ writes the card back into its own address book with its ETag, a new one
// into the book chosen or „Auf dem Spark“ (contacts.save). „Einstellungen“ holds the address books (the box #conbox,
// a page of Ich until Kontakte came). Names, numbers and notes come from address books: only through esc().
const KON={data:null,sel:'',book:'',q:'',seq:0,busy:false,err:'',msg:'',form:null,with:{}};
const KON_PHONE=['Handy','Privat','Arbeit','Telefon'],KON_ADDR=['Privat','Arbeit','Adresse'];
const KON_EN={Handy:'Mobile',Privat:'Home',Arbeit:'Work',Telefon:'Phone',Adresse:'Address'};
const konKind=k=>L==='en'?KON_EN[k]||k:k;
// the menu entry only for a signed-in profile with contacts (start.js, like Listen)
window.konStart=who=>{const on=!!(who&&who.profile&&who.contacts);document.querySelectorAll('nav button[data-s=kontakte]').forEach(b=>b.hidden=!on)};
const konCard=()=>KON.data&&KON.data.cards.find(c=>c.id===KON.sel);
const konBook=id=>KON.data&&KON.data.books.find(b=>b.id===id);
// the letter a card stands under: its family name (or name) without accents, „#“ for anything else
const konLetter=c=>{const s=(c.family||c.name||'').normalize('NFD').replace(/[̀-ͯ]/g,'').charAt(0).toUpperCase();return /[A-Z]/.test(s)?s:'#'};
const konInit=c=>((c.given||c.name||'').charAt(0)+(c.family||'').charAt(0)).toUpperCase()||'?';
async function konLoad(){if(!PROFILE||!CON_ON)return;const seq=++KON.seq;KON.busy=true;konDraw();
  const {r,d}=await apiTry('/api/profile/contacts/page');if(seq!==KON.seq)return;
  if(r.ok){KON.data=d;KON.err='';if(KON.sel&&!konCard())KON.sel=''}else KON.err=errSay(r.status,d.detail,'');
  KON.busy=false;konDraw()}
const KON_BOX=$('conbox');   // the tab „Einstellungen“ shows it; kept in the section between visits (like Listen)
window.konOpen=()=>{if(!PROFILE)return;const root=$('konroot');if(KON_BOX){KON_BOX.hidden=true;$('kontakte').appendChild(KON_BOX)}root.textContent='';
  root.appendChild(icTabs('kontakte',[{k:'show',label:OWN_PAGES.conbox[2],body:konBody},
    {k:'set',label:t('Einstellungen','Settings'),body:()=>{const b=$('conbox');b.hidden=false;lzb(b,showCon,{auth:true}).catch(()=>{});return b}}]));
  konLoad()};
// a sender tapped in E-Mail (post.js): its card, or a new one with name and address when changing is on
window.konShow=async(addr,name)=>{if(!CON_ON||!addr)return false;addr=String(addr).toLowerCase();
  if(!KON.data)await konLoad();if(!KON.data)return false;
  const c=KON.data.cards.find(x=>x.emails.includes(addr));
  if(c){KON.sel=c.id;KON.form=null}
  else if(KON.data.edit){const p=String(name||'').trim().split(/\s+/);KON.sel='';
    KON.form=konBlank({given:p.length>1?p.slice(0,-1).join(' '):p[0]||'',family:p.length>1?p[p.length-1]:'',emails:[addr]})}
  else return false;
  icTabSet('kontakte','show');goSec('kontakte');return true};
function konBody(){const w=document.createElement('div');w.className='ld-box ld-frame kon';w.id='konview';konPaint(w);return w}
function konDraw(){const w=$('konview');if(w)konPaint(w)}
function konPaint(w){const d=KON.data;w.classList.toggle('ld-sel',!!(KON.sel||KON.form));
  if(!w.querySelector('.ld-split')){w.innerHTML=`<div class="konwarn"></div><div class="ld-split"><div class="ld-list"><div class="kontools">`+
      `<input type="search" data-k="q" autocomplete="off" placeholder="${esc(t('Suchen','Search'))}" aria-label="${esc(t('Kontakte durchsuchen','Search contacts'))}">`+
      `<div class="ld-chips konbooks"></div></div><div class="konwrap"><div class="konrows"></div><nav class="konlet" aria-label="${esc(t('Buchstaben','Letters'))}"></nav></div></div>`+
      `<div class="ld-detail kondet" hidden></div></div>`;
    const q=w.querySelector('[data-k=q]');q.value=KON.q;q.oninput=()=>{KON.q=q.value;konRows(w)}}
  w.querySelector('.konwarn').innerHTML=KON.err?`<div class="note warn">${esc(t('Die Kontakte kamen nicht an: ','The contacts did not arrive: ')+KON.err)}</div>`
    :d&&d.errors.length?`<div class="note warn">${esc(t('Ein Adressbuch war beim letzten Abholen nicht erreichbar; gezeigt wird der letzte Stand.','An address book was not reachable when last fetched; the last copy is shown.'))}</div>`:'';
  const bk=w.querySelector('.konbooks');
  bk.innerHTML=!d||d.books.length<2?'':[['',t('Alle','All'),d.cards.length],...d.books.map(b=>[b.id,b.name,d.cards.filter(c=>c.book===b.id).length])]
    .map(([id,n,k])=>`<button type="button" class="ld-chip${id===KON.book?' on':''}" data-b="${esc(id)}" aria-pressed="${id===KON.book}">${esc(n)} <b>${k}</b></button>`).join('');
  bk.querySelectorAll('[data-b]').forEach(b=>b.onclick=()=>{KON.book=b.dataset.b;konDraw()});
  konRows(w);konDetail(w)}
function konShown(){const d=KON.data,q=KON.q.trim().toLowerCase();
  return d.cards.filter(c=>(!KON.book||c.book===KON.book)&&(!q||[c.name,c.org,c.nick,...c.emails,...c.phones.map(p=>p[1])].some(v=>String(v||'').toLowerCase().includes(q))))}
// the rows under their letters and the bar of the letters there are (tapping one jumps to it)
function konRows(w){const d=KON.data,rows=w.querySelector('.konrows'),bar=w.querySelector('.konlet');
  if(!d){rows.innerHTML=KON.busy?`<div class="ld-empty mut">${esc(t('Lade die Kontakte …','Loading the contacts …'))}</div>`:'';bar.innerHTML='';return}
  const shown=konShown(),by={};shown.forEach(c=>{(by[konLetter(c)]=by[konLetter(c)]||[]).push(c)});
  const lets=Object.keys(by).sort((a,b)=>a==='#'?1:b==='#'?-1:a.localeCompare(b));
  rows.innerHTML=(d.edit?`<div class="ld-more"><button class="b" type="button" data-k="new">${esc(t('+ Neuer Kontakt','+ New contact'))}</button></div>`:'')+
    (shown.length?lets.map(l=>`<div class="ld-grp" data-g="${esc(l)}"><span>${esc(l)}</span><span>${by[l].length}</span></div>`+by[l].map(c=>
      `<div class="ld-row${c.id===KON.sel?' on':''}" role="button" tabindex="0" data-c="${esc(c.id)}"><span class="ld-ico konav" aria-hidden="true">${esc(konInit(c))}</span>`+
      `<span class="ld-mid"><b>${esc(c.name)}</b><small>${esc(c.org&&c.org!==c.name?c.org:c.emails[0]||(c.phones[0]||[])[1]||'')}</small></span></div>`).join('')).join('')
    :`<div class="ld-empty mut">${esc(d.cards.length?t('Kein Kontakt passt.','No contact fits.'):t('Noch keine Kontakte. Ein Adressbuch kommt unter Einstellungen dazu.','No contacts yet. Add an address book under Settings.'))}</div>`);
  bar.innerHTML=lets.length>1?lets.map(l=>`<button type="button" data-l="${esc(l)}">${esc(l)}</button>`).join(''):'';
  bar.querySelectorAll('[data-l]').forEach(b=>b.onclick=()=>{const g=rows.querySelector(`[data-g="${CSS.escape(b.dataset.l)}"]`);if(g)g.scrollIntoView({block:'start'})});
  rows.querySelectorAll('[data-c]').forEach(r=>{const go=()=>{KON.sel=r.dataset.c;KON.form=null;KON.msg='';konDraw()};
    r.onclick=go;r.onkeydown=e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();go()}}});
  const nb=rows.querySelector('[data-k=new]');if(nb)nb.onclick=()=>{KON.sel='';KON.msg='';KON.form=konBlank({});konDraw()}}
function konBlank(x){const d=KON.data,own=d.books.filter(b=>b.write),pick=own.find(b=>b.id===KON.book)||own.find(b=>b.id!=='spark')||own[0];
  return {id:null,etag:'',book:pick?pick.id:'spark',given:'',family:'',org:'',title:'',nick:'',phones:[['Handy','']],emails:[],addrs:[],urls:[],bday:'',note:'',...x}}
function konDetail(w){const box=w.querySelector('.kondet'),c=konCard(),f=KON.form;box.hidden=!c&&!f;if(box.hidden)return;
  if(f&&box.querySelector('.konform'))konFormRead(box);   // a redraw while typing keeps what is typed
  const back=`<button type="button" class="b ld-back" data-k="back">‹ ${esc(t('Kontakte','Contacts'))}</button>`;
  box.innerHTML=back+(KON.msg?`<div class="note warn">${esc(KON.msg)}</div>`:'')+(f?konFormHtml(f):konCardHtml(c));
  box.querySelector('[data-k=back]').onclick=()=>{KON.sel='';KON.form=null;KON.msg='';konDraw()};
  if(f)konFormBind(box);else konCardBind(box,c)}
// the five buttons as line symbols in the accent colour, like the mail buttons (Dominik 2026-10-21: no emoji)
const KON_IC={sms:'M21 12a8 8 0 0 1-11.6 7.1L4 20l1-4.6A8 8 0 1 1 21 12z',
  tel:'M22 16.9v3a2 2 0 0 1-2.2 2 19.8 19.8 0 0 1-8.6-3.1 19.5 19.5 0 0 1-6-6A19.8 19.8 0 0 1 2.1 4.2 2 2 0 0 1 4.1 2h3a2 2 0 0 1 2 1.7c.1 1 .4 1.9.7 2.8a2 2 0 0 1-.5 2.1L8 9.9a16 16 0 0 0 6 6l1.3-1.3a2 2 0 0 1 2.1-.5c.9.3 1.8.6 2.8.7a2 2 0 0 1 1.7 2z',
  mail:'M3 7a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2zM3 7l9 6 9-6',
  event:'M3 7a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2zM3 10h18M8 3v4M16 3v4',
  share:'M4 12v7a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-7M16 6l-4-4-4 4M12 2v13'};
const konIc=k=>`<svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="${KON_IC[k]}"/></svg>`;
// „Nachricht“ opens the messages app where there is one (phone, tablet, Mac); a Windows or Linux browser has none,
// there the button copies the number and says so (before, nothing happened)
const konSms=()=>/iPhone|iPad|Android|Macintosh/.test(navigator.userAgent)||matchMedia('(pointer:coarse)').matches;
// the card: the person, the five buttons, the fields, „Mit Anna“
function konCardHtml(c){const tel=(c.phones.find(p=>p[0]==='Handy')||c.phones[0]||[])[1]||'',mail=c.emails[0]||'',bk=konBook(c.book);
  const act=(k,lbl,on,href)=>{const ic=konIc(k);return href&&on?`<a class="konact" data-k="${k}" href="${esc(href)}">${ic}${esc(lbl)}</a>`
    :`<button type="button" class="konact" data-k="${k}"${on?'':' disabled'}>${ic}${esc(lbl)}</button>`};
  const num=s=>s.replace(/[^\d+]/g,'');
  const row=(lbl,val)=>`<div class="konf"><small>${esc(lbl)}</small><div>${val}</div></div>`;
  const bd=c.bday?(()=>{const m=/^(\d{4}|-)-(\d\d)-(\d\d)$/.exec(c.bday);if(!m)return '';const dt=new Date(2000,+m[2]-1,+m[3]);
    return dt.toLocaleDateString(L==='en'?'en-GB':'de-DE',{day:'numeric',month:'long'})+(m[1]!=='-'?' '+m[1]:'')})():'';
  return `<div class="koncard"><div class="konhead"><span class="konav big" aria-hidden="true">${esc(konInit(c))}</span><h3>${esc(c.name)}</h3>`+
    (c.title||c.org&&c.org!==c.name?`<div class="mut">${esc([c.title,c.org!==c.name?c.org:''].filter(Boolean).join(' · '))}</div>`:'')+
    `<div class="konacts">${act('sms',t('Nachricht','Message'),!!tel,konSms()&&tel&&'sms:'+num(tel))}${act('tel',t('Anruf','Call'),!!tel,tel&&'tel:'+num(tel))}`+
    `${act('mail',t('Mail','Mail'),!!mail)}${act('event',t('Termin','Event'),typeof CAL_ON==='undefined'||CAL_ON)}`+
    `${act('share',t('Teilen','Share'),true,'/api/profile/contacts/vcf/'+encodeURIComponent(c.id))}</div>`+
    `<div class="konhint mut" aria-live="polite"></div></div>`+
    c.phones.map(p=>row(konKind(p[0]),`<a href="tel:${esc(num(p[1]))}">${esc(p[1])}</a>`)).join('')+
    c.emails.map(m=>row(t('E-Mail','E-mail'),`<a href="#" data-mail="${esc(m)}">${esc(m)}</a>`)).join('')+
    c.addrs.map(a=>row(konKind(a.kind),esc([a.street,[a.zip,a.city].filter(Boolean).join(' '),a.country].filter(Boolean).join('\n')).replace(/\n/g,'<br>'))).join('')+
    c.urls.map(u=>row(t('Webseite','Website'),/^https?:\/\//i.test(u)?`<a href="${esc(u)}" target="_blank" rel="noopener noreferrer">${esc(u)}</a>`:esc(u))).join('')+
    (bd?row(t('Geburtstag','Birthday'),esc(bd)):'')+(c.nick?row(t('Spitzname','Nickname'),esc(c.nick)):'')+
    (c.note?row(t('Notiz','Note'),esc(c.note).replace(/\n/g,'<br>')):'')+
    `<div class="konwith" aria-live="polite"></div>`+
    `<div class="konfoot"><small class="mut">${esc(bk?t('Adressbuch: ','Address book: ')+bk.name:'')}</small>`+
    (c.edit?`<button class="b" type="button" data-k="edit">${esc(t('Bearbeiten','Edit'))}</button>`:'')+`</div></div>`}
function konCardBind(box,c){
  const mail=a=>{if(typeof postWrite==='function'&&typeof MAIL_ON!=='undefined'&&MAIL_ON){icTabSet('post','show');goSec('post');
      postWrite(null).then(()=>{if(POST.write){POST.write.to=a;postDraw()}})}else location.href='mailto:'+a};
  box.querySelectorAll('[data-mail]').forEach(a=>a.onclick=e=>{e.preventDefault();mail(a.dataset.mail)});
  const b=k=>box.querySelector(`.konacts [data-k=${k}]`);
  if(c.emails[0])b('mail').onclick=()=>mail(c.emails[0]);
  const sms=b('sms'),hint=box.querySelector('.konhint');
  if(sms.tagName==='BUTTON'&&!sms.disabled)sms.onclick=async()=>{const n=(c.phones.find(p=>p[0]==='Handy')||c.phones[0])[1];
    let ok=false;try{await navigator.clipboard.writeText(n);ok=true}catch(e){}
    hint.textContent=(ok?t('Nummer kopiert. ','Number copied. '):n+' · ')+t('Dieser Rechner hat keine Nachrichten-App; die Nachricht geht vom Handy aus, auch in der Spark-App unter Kontakte.',
      'This computer has no messages app; send the message from the phone, also in the Spark app under Contacts.')};
  b('event').onclick=()=>{if(typeof KAL==='undefined')return;KAL.q=t('Termin mit ','Meeting with ')+c.name+' ';KAL.qi=null;KAL.qfocus=true;icTabSet('cal','show');goSec('cal')};
  b('share').setAttribute('download',(c.name||'kontakt').replace(/[^\p{L}\p{N} ._-]/gu,'')+'.vcf');
  const ed=box.querySelector('[data-k=edit]');
  if(ed)ed.onclick=()=>{KON.msg='';KON.form=konBlank({id:c.id,etag:c.etag,book:c.book,given:c.given,family:c.family,org:c.org,title:c.title,nick:c.nick,
    phones:c.phones.map(p=>[KON_PHONE.includes(p[0])?p[0]:'Telefon',p[1]]),emails:[...c.emails],addrs:c.addrs.map(a=>({...a})),urls:[...c.urls],bday:c.bday,note:c.note});konDraw()};
  konWith(box,c)}
// „Mit Anna“: asked once per card and visit of the page; only what is there (calendar and mail supply)
async function konWith(box,c){const el=box.querySelector('.konwith');if(!el)return;
  let x=KON.with[c.id];
  if(!x){const {r,d}=await apiTry('/api/profile/contacts/with/'+encodeURIComponent(c.id)+'?tz='+encodeURIComponent(Intl.DateTimeFormat().resolvedOptions().timeZone||''));
    if(!r.ok)return;x=KON.with[c.id]=d}
  if(!el.isConnected||KON.sel!==c.id)return;
  const loc=L==='en'?'en-GB':'de-DE',when=(s,all)=>new Date(s*1000).toLocaleString(loc,all?{weekday:'short',day:'numeric',month:'short'}:{weekday:'short',day:'numeric',month:'short',hour:'2-digit',minute:'2-digit'});
  if(!x.event&&!x.mail)return;
  el.innerHTML=`<div class="ld-grp"><span>${esc(t('Mit ','With ')+(c.given||c.name))}</span></div>`+
    (x.event?`<div class="konf"><small>${esc(t('Nächster Termin','Next appointment'))}</small><div><a href="#" data-k="ev">${esc(x.event.title)}</a> · ${esc(when(x.event.start,x.event.allday))}</div></div>`:'')+
    (x.mail?`<div class="konf"><small>${esc(t('Letzte Mail','Latest mail'))}</small><div>${esc(x.mail.subject||t('(ohne Betreff)','(no subject)'))} · ${esc(when(x.mail.date,true))}</div></div>`:'');
  const ev=el.querySelector('[data-k=ev]');
  if(ev)ev.onclick=e=>{e.preventDefault();if(typeof KAL==='undefined')return;KAL.day=new Date(x.event.start*1000);icTabSet('cal','show');goSec('cal')}}
// Bearbeiten like Apple: every field a row with −, every kind a „+ hinzufügen“; „Fertig“ saves, „Abbrechen“ leaves it
function konFormHtml(f){const d=KON.data,opt=(ks,cur)=>ks.map(k=>`<option value="${esc(k)}"${k===cur?' selected':''}>${esc(konKind(k))}</option>`).join('');
  const minus=`<button type="button" class="konminus" data-k="minus" aria-label="${esc(t('Feld entfernen','Remove field'))}">−</button>`;
  const inp=(k,v,ph,more)=>`<input data-v="${k}" value="${esc(v||'')}" placeholder="${esc(ph)}" aria-label="${esc(ph)}" autocomplete="off"${more||''}>`;
  const sec=(k,rows,add)=>`<div class="konsec" data-f="${k}">${rows}</div><button type="button" class="b konadd" data-add="${k}">${esc(add)}</button>`;
  const own=d.books.filter(b=>b.write);
  return `<div class="konform"><h3>${esc(f.id?t('Kontakt bearbeiten','Edit contact'):t('Neuer Kontakt','New contact'))}</h3>`+
    (f.id?'':own.length>1?`<label>${esc(t('Adressbuch','Address book'))}<select data-k="book">${own.map(b=>`<option value="${esc(b.id)}"${b.id===f.book?' selected':''}>${esc(b.name)}</option>`).join('')}</select></label>`:'')+
    `<div class="konnames">${inp('given',f.given,t('Vorname','First name'),' data-n="1" maxlength="80"')}${inp('family',f.family,t('Nachname','Last name'),' data-n="1" maxlength="80"')}`+
    `${inp('org',f.org,t('Firma','Company'),' data-n="1" maxlength="120"')}${inp('title',f.title,t('Position','Job title'),' data-n="1" maxlength="120"')}${inp('nick',f.nick,t('Spitzname','Nickname'),' data-n="1" maxlength="60"')}</div>`+
    sec('phones',f.phones.map(p=>`<div class="konrow"><select data-v="kind">${opt(KON_PHONE,p[0])}</select>${inp('num',p[1],t('Telefon','Phone'),' type="tel" maxlength="30"')}${minus}</div>`).join(''),t('+ Telefon hinzufügen','+ Add phone'))+
    sec('emails',f.emails.map(m=>`<div class="konrow">${inp('mail',m,'anna@example.org',' type="email" maxlength="200"')}${minus}</div>`).join(''),t('+ E-Mail hinzufügen','+ Add e-mail'))+
    sec('addrs',f.addrs.map(a=>`<div class="konrow konadr"><select data-v="kind">${opt(KON_ADDR,a.kind)}</select>${inp('street',a.street,t('Straße','Street'))}`+
      `${inp('zip',a.zip,t('PLZ','Postcode'))}${inp('city',a.city,t('Ort','City'))}${inp('country',a.country,t('Land','Country'))}${minus}</div>`).join(''),t('+ Adresse hinzufügen','+ Add address'))+
    sec('urls',f.urls.map(u=>`<div class="konrow">${inp('url',u,'https://',' type="url" maxlength="300"')}${minus}</div>`).join(''),t('+ Webseite hinzufügen','+ Add website'))+
    `<label>${esc(t('Geburtstag','Birthday'))}${inp('bday',f.bday,t('JJJJ-MM-TT oder --MM-TT','YYYY-MM-DD or --MM-DD'),' data-n="1" maxlength="10"')}</label>`+
    `<label>${esc(t('Notiz','Note'))}<textarea data-v="note" data-n="1" maxlength="2000" rows="3">${esc(f.note)}</textarea></label>`+
    `<div class="row"><button class="b p" type="button" data-k="save"${KON.busy?' disabled':''}>${esc(t('Fertig','Done'))}</button><button class="b" type="button" data-k="cancel">${esc(t('Abbrechen','Cancel'))}</button>`+
    (f.id?`<button class="b bad" type="button" data-k="del">${esc(t('Kontakt löschen','Delete contact'))}</button>`:'')+`</div></div>`}
const KON_MAX={phones:8,emails:6,addrs:4,urls:4};   // kontaktkarte.PHONES_MAX …; the panel checks again
// what is typed goes into KON.form before any redraw, so − and + never lose a field
function konFormRead(box){const f=KON.form,v=(r,k)=>(r.querySelector(`[data-v=${k}]`)||{}).value||'';
  box.querySelectorAll('[data-n]').forEach(i=>{f[i.dataset.v]=i.value});
  const rows=k=>[...box.querySelectorAll(`[data-f=${k}] .konrow`)];
  f.phones=rows('phones').map(r=>[v(r,'kind'),v(r,'num')]);f.emails=rows('emails').map(r=>v(r,'mail'));f.urls=rows('urls').map(r=>v(r,'url'));
  f.addrs=rows('addrs').map(r=>({kind:v(r,'kind'),street:v(r,'street'),zip:v(r,'zip'),city:v(r,'city'),country:v(r,'country')}));
  const bk=box.querySelector('[data-k=book]');if(bk)f.book=bk.value}
function konFormBind(box){const f=KON.form;
  box.querySelectorAll('[data-k=minus]').forEach(m=>m.onclick=()=>{m.closest('.konrow').remove();konFormRead(box);konDraw()});
  box.querySelectorAll('[data-add]').forEach(a=>{const k=a.dataset.add;a.disabled=f[k].length>=KON_MAX[k];a.onclick=()=>{konFormRead(box);
    f[k].push(k==='phones'?['Handy','']:k==='addrs'?{kind:'Privat',street:'',zip:'',city:'',country:''}:'');konDraw();
    const r=$('konview').querySelector(`[data-f=${k}] .konrow:last-child input`);if(r)r.focus()}});
  box.querySelector('[data-k=cancel]').onclick=()=>{KON.form=null;KON.msg='';konDraw()};
  box.querySelector('[data-k=save]').onclick=()=>{konFormRead(box);konSave()};
  const del=box.querySelector('[data-k=del]');if(del)del.onclick=()=>konDelete()}
async function konSave(){const f=KON.form;if(!f||KON.busy)return;KON.busy=true;konDraw();
  const body={...f,phones:f.phones.filter(p=>p[1].trim()),emails:f.emails.filter(Boolean),urls:f.urls.filter(Boolean)};
  const {r,d}=await apiTry(f.id?'/api/profile/contacts/card/'+encodeURIComponent(f.id):'/api/profile/contacts/card',xjson(f.id?'PUT':'POST',body));
  KON.busy=false;
  if(!r.ok){KON.msg=r.status===409?t('Der Kontakt wurde inzwischen in seinem Adressbuch geändert; hier steht jetzt der neue Stand. Bitte noch einmal bearbeiten.','The contact was changed meanwhile in its address book; the new version is shown now. Please edit it again.')
      :errSay(r.status,d.detail,'');
    if(r.status===409){KON.form=null;await konLoad()}konDraw();return}
  const cs=KON.data.cards.filter(c=>c.id!==d.id);cs.push(d);cs.sort((a,b)=>(a.family||a.name).toLowerCase().localeCompare((b.family||b.name).toLowerCase()));
  KON.data.cards=cs;delete KON.with[d.id];KON.sel=d.id;KON.form=null;KON.msg='';
  if(!KON.data.books.some(b=>b.id===d.book))konLoad();konDraw()}
async function konDelete(){const f=KON.form;if(!f||!f.id||KON.busy)return;
  if(!confirm(t('Diesen Kontakt löschen? Er wird auch aus seinem Adressbuch gelöscht.','Delete this contact? It is deleted from its address book too.')))return;
  KON.busy=true;konDraw();
  const {r,d}=await apiTry('/api/profile/contacts/card/'+encodeURIComponent(f.id)+'?etag='+encodeURIComponent(f.etag||''),{method:'DELETE'});KON.busy=false;
  if(!r.ok){KON.msg=errSay(r.status,d.detail,'');if(r.status===409){KON.form=null;await konLoad()}konDraw();return}
  KON.data.cards=KON.data.cards.filter(c=>c.id!==f.id);KON.sel='';KON.form=null;KON.msg='';konDraw()}
