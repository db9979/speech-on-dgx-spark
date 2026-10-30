// Finden (fund.py, plan such-index/plan.md, Stufe A): one search over the own data, a page of its own in the menu next
// to the Wissensbuch. „Suche“: a box, filters by source and category, the hits with their fields and tags; a hit opens
// its detail (every tag with where it came from, ✓ keeps, × removes for good, + adds an own one) and „Öffnen“ goes to
// the source (Eigene Dokumente, Wissensbuch). „Schlagworte“: the fixed categories with their counts and the own tags.
// „Einstellungen“: per source how many entries and how fresh, „Neu aufbauen“, „Index löschen“. Titles, fields and tags
// come from documents and mails (Stufe B, fundmail.py) and are only ever text (esc, textContent), never markup; a mail
// opens on the page E-Mail in its folder, an attachment's mail likewise. Strg K offers „In meinen Daten finden“.
// Stufe D: tags of the model shown dashed with „vom Modell“, points of the Wissenskarte with their dot, „Neu vom Modell“
// on the tab Schlagworte (✓ keeps, × removes for good), the Sofort-Karte's „Original öffnen“ (fundTreffer).
// Stufe C (fundquellen.py): appointments open the calendar on their day, contacts, lists, conversations, reminders,
// pictures and songs their own page; a period („letzte Woche“) or an event („vom OP“) in the typed words shows as a
// line with what the panel made of it (deutung: the appointment's day, or that there is none).
const FUND={q:'',quelle:'',kat:'',hits:null,sel:0,item:null,stand:null,msg:'',err:false,seq:0,deut:null};
let FUND_ON=false;
window.fundStart=who=>{FUND_ON=!!(who&&who.profile&&who.find);window.FUND_ON=FUND_ON;
  document.querySelectorAll('nav button[data-s=finden]').forEach(b=>b.hidden=!FUND_ON)};
const fundWhen=s=>s?new Date(s*1000).toLocaleDateString(L==='en'?'en-GB':'de-DE',{dateStyle:'medium'}):'';
const FUND_TYP={kategorie:['Kategorie','Category'],person:['Person','Person'],firma:['Firma','Company'],ort:['Ort','Place'],frei:['Schlagwort','Tag']};
const FUND_FROM={regel:['Regel','rule'],modell:['vom Modell','by the model'],hand:['von dir','yours'],dokument:['Steckbrief','profile card']};
const FUND_FELD={absender:['Absender','Sender'],an:['An','To'],betrag:['Betrag','Amount'],nr:['Nummer','Number'],datum:['Datum','Date'],name:['Datei','File'],anhaenge:['Anhänge','Attachments'],kb:['Größe (KB)','Size (KB)'],
  ort:['Ort','Place'],kalender:['Kalender','Calendar'],firma:['Firma','Company'],kanal:['Kanal','Channel'],fragen:['Fragen','Questions'],offen:['Offen','Open'],erledigt:['Erledigt','Done'],wiederholt:['Wiederholt','Repeats'],format:['Format','Format']};
// what the panel read from the typed words: a period and an event of the own calendar (fund.zeitraum, fund.bezug_aus)
function fundDeut(){const d=FUND.deut;if(!d)return '';const p=[];
  if(d.von)p.push(t('Zeitraum','Period')+': '+d.von+(d.bis?' – '+d.bis:' – '+t('heute','today')));
  if(d.bezug)p.push(d.termin?t(`Termin „${d.bezug}“ am ${fundWhen(d.termin)}: Treffer davor und danach zuerst`,`Appointment "${d.bezug}" on ${fundWhen(d.termin)}: hits around it first`)
    :t(`Einen Termin „${d.bezug}“ habe ich im Kalender nicht gefunden.`,`I found no appointment "${d.bezug}" in the calendar.`));
  return p.length?`<div class="mut small funddeut">${p.map(x=>esc(x)).join(' · ')}</div>`:''}
// a mail (or an attachment's mail) on the page E-Mail: its folder like the folder list does, then the mail (post.js)
async function fundMail(w){if(typeof postRead!=='function'||typeof POST==='undefined')return;icTabSet('post','show');POST.write=null;POST.prev=null;
  POST.box=w.folder&&w.folder!=='INBOX'?{account:String(w.id).split(':')[0],folder:w.folder,name:w.folder,role:w.rolle||'folder'}:null;goSec('post');await postRead(w.id)}
function fundOpen(){if(!PROFILE)return;const root=$('fundroot'),box=$('fundbox');if(box){box.hidden=true;$('finden').appendChild(box)}root.textContent='';
  root.appendChild(icTabs('finden',[{k:'show',label:OWN_PAGES.fundbox[2],body:fundBody},
    {k:'worte',label:t('Schlagworte','Tags'),body:fundWorteBody},
    {k:'set',label:t('Einstellungen','Settings'),body:()=>{const b=$('fundbox');b.hidden=false;fundSettings(b);return b}}]));
  fundStand()}
window.fundOpen=fundOpen;
// Strg K and the card under an answer: the page with these words; the hits and the open entry of the search before go
// at once, so nobody picks an old hit while the new search still runs
window.fundSuche=q=>{FUND.q=String(q||'').slice(0,200);FUND.item=null;FUND.hits=null;icTabSet('finden','show');goSec('finden');fundDraw();fundRun()};
async function fundStand(){if(!FUND_ON)return;const {r,d}=await apiTry('/api/profile/fund/stand');
  if(r.ok){FUND.stand=d}else{FUND.stand=null;fundSay(errSay(r.status,d.detail,''),true)}fundDraw()}
function fundSay(x,err){FUND.msg=String(x||'').slice(0,300);FUND.err=!!err;document.querySelectorAll('.fundmsg').forEach(m=>{m.className='fundmsg '+(err?'err':'mut');m.textContent=FUND.msg})}
function fundBody(){const w=document.createElement('div');w.className='ld-box ld-frame fund';w.id='fundview';fundPaint(w);return w}
function fundWorteBody(){const w=document.createElement('div');w.className='ld-box fund';w.id='fundworte';fundWorte(w);return w}
function fundDraw(){const w=$('fundview');if(w)fundPaint(w);const v=$('fundworte');if(v)fundWorte(v);const b=$('fundset');if(b)fundSettingsPaint(b)}
async function fundRun(){const seq=++FUND.seq;const body={worte:FUND.q.trim()};if(FUND.quelle)body.quelle=FUND.quelle;if(FUND.kat)body.kategorie=FUND.kat;
  if(!body.worte&&!body.quelle&&!body.kategorie){FUND.hits=null;fundDraw();return}
  const {r,d}=await apiTry('/api/profile/fund/suche',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});if(seq!==FUND.seq)return;
  if(r.ok){FUND.hits=d.treffer||[];FUND.deut=d.deutung||null;FUND.msg='';FUND.err=false}else{FUND.hits=[];FUND.deut=null;FUND.msg=errSay(r.status,d.detail,'');FUND.err=true}fundDraw()}
const fundSrc=n=>{const q=((FUND.stand&&FUND.stand.quellen)||[]).find(x=>x.name===n);return q?t(q.de,q.en):n};
// Stufe D: a tag of the model has a dashed edge and says „vom Modell“; a person, company or place that is a point of
// the Wissenskarte has a dot in that point's colour (wk-k-…); an own tag is filled
const fundTag=x=>`<span class="pill fundtag${x.herkunft==='hand'?' on':''}${x.herkunft==='modell'?' modell':''}" title="${esc(t(...(FUND_TYP[x.typ]||[x.typ,x.typ]))+' · '+t(...(FUND_FROM[x.herkunft]||[x.herkunft,x.herkunft])))}">${x.knoten?`<i class="wkdot wk-k-${esc(x.typ)}" aria-hidden="true"></i>`:''}${esc(x.wert)}${x.herkunft==='modell'?` <small>${esc(t('vom Modell','by the model'))}</small>`:''}</span>`;
function fundPaint(w){w.classList.toggle('ld-sel',!!FUND.item);
  if(!w.querySelector('.ld-split'))w.innerHTML=`<div class="ld-split"><div class="ld-list"></div><div class="ld-detail funddet" hidden></div></div>`;
  const list=w.querySelector('.ld-list'),S=FUND.stand;
  const srcs=((S&&S.quellen)||[]).filter(q=>q.an),kats=((S&&S.kategorien)||[]);
  list.innerHTML=`<div class="ld-tools"><input type="search" class="fundq" maxlength="200" placeholder="${esc(t('Wörter, Firma, Person, Nummer …','Words, company, person, number …'))}" aria-label="${esc(t('In meinen Daten finden','Find in my data'))}" value="${esc(FUND.q)}"></div>
    <div class="row"><select class="fundsrc" aria-label="${esc(t('Quelle','Source'))}"><option value="">${esc(t('Alle Quellen','All sources'))}</option>${srcs.map(q=>`<option value="${esc(q.name)}"${q.name===FUND.quelle?' selected':''}>${esc(t(q.de,q.en))}</option>`).join('')}</select>
    <select class="fundkat" aria-label="${esc(t('Kategorie','Category'))}"><option value="">${esc(t('Alle Kategorien','All categories'))}</option>${kats.map(k=>`<option value="${esc(k.wert)}"${k.wert===FUND.kat?' selected':''}>${esc(k.wert)}</option>`).join('')}</select></div>
    ${FUND.hits!==null?fundDeut():''}
    ${S&&!S.eintraege?`<div class="ld-empty mut">${esc(t('Der Index ist noch leer. Er füllt sich im Hintergrund, alle paar Minuten ein Stück.','The index is still empty. It fills in the background, a part every few minutes.'))}</div>`:''}
    ${FUND.hits===null?(S&&S.eintraege?`<div class="ld-empty mut">${esc(t(`${S.eintraege} Einträge im Index. Gib Wörter ein oder wähle eine Kategorie.`,`${S.eintraege} entries in the index. Type words or choose a category.`))}</div>`:'')
      :FUND.hits.length?FUND.hits.map(h=>`<div class="ld-row${FUND.item&&FUND.item.id===h.id?' on':''}" role="button" tabindex="0" data-fundsel="${esc(String(h.id))}"><span class="ld-mid"><b>${esc(h.titel||'?')}</b><small>${esc(fundSrc(h.quelle))}${h.wann?' · '+esc(fundWhen(h.wann)):''}${h.felder&&h.felder.absender?' · '+esc(h.felder.absender):''}</small>${(h.anhaenge||[]).map(a=>`<small class="mut">${esc(t('Anhang','Attachment'))}: ${esc(a.titel)}${a.felder&&a.felder.betrag?' · '+esc(a.felder.betrag):''}</small>`).join('')}${(h.tags||[]).length?`<span class="fundtags">${h.tags.slice(0,6).map(fundTag).join(' ')}</span>`:''}</span></div>`).join('')
      :`<div class="ld-empty mut">${esc(t('Nichts gefunden.','Nothing found.'))}</div>`}
    <div class="fundmsg ${FUND.err?'err':'mut'}" role="status">${esc(FUND.msg)}</div>`;
  const qi=list.querySelector('.fundq');let tm=null;
  qi.oninput=()=>{FUND.q=qi.value;clearTimeout(tm);tm=setTimeout(async()=>{const pos=qi.selectionStart;await fundRun();const n=document.querySelector('#fundview .fundq');if(n){n.focus();n.setSelectionRange(pos,pos)}},300)};
  qi.onkeydown=e=>{if(e.key==='Enter'){e.preventDefault();clearTimeout(tm);fundRun()}};
  list.querySelector('.fundsrc').onchange=e=>{FUND.quelle=e.target.value;fundRun()};
  list.querySelector('.fundkat').onchange=e=>{FUND.kat=e.target.value;fundRun()};
  list.querySelectorAll('[data-fundsel]').forEach(r=>{const go=()=>fundPick(r.dataset.fundsel);r.onclick=go;r.onkeydown=e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();go()}}});
  fundDetail(w)}
async function fundPick(id){const {r,d}=await apiTry('/api/profile/fund/eintrag/'+encodeURIComponent(id));
  if(!r.ok){FUND.item=null;fundSay(errSay(r.status,d.detail,''),true);fundDraw();return}FUND.item=d;fundDraw()}
function fundDetail(w){const det=w.querySelector('.funddet'),it=FUND.item;if(!it){det.hidden=true;det.textContent='';return}
  det.hidden=false;const f=it.felder||{};
  det.innerHTML=`<button class="b ld-back" type="button" data-fundback="1">‹ ${esc(OWN_PAGES.fundbox[1])}</button><h3>${esc(it.titel||'?')}</h3>
    <div class="mut">${esc(fundSrc(it.quelle))}${it.wann?' · '+esc(fundWhen(it.wann)):''}</div>
    <ul class="facts small">${Object.keys(FUND_FELD).filter(k=>f[k]).map(k=>`<li><span>${esc(t(...FUND_FELD[k]))}</span><b>${esc(Array.isArray(f[k])?f[k].join(', '):String(f[k]))}</b></li>`).join('')}</ul>
    ${it.auszug?`<p class="mut">${esc(it.auszug)}</p>`:''}
    <h4>${esc(t('Schlagworte','Tags'))}</h4>
    <ul class="facts fundtaglist">${(it.tags||[]).map((x,i)=>`<li><span>${fundTag(x)} <small class="mut">${esc(t(...(FUND_TYP[x.typ]||[x.typ,x.typ])))} · ${esc(t(...(FUND_FROM[x.herkunft]||[x.herkunft,x.herkunft])))}</small></span><span>${x.herkunft==='hand'?'':`<button type="button" class="b" data-fundkeep="${i}" title="${esc(t('Behalten','Keep'))}">✓</button>`} <button type="button" class="b" data-fundrm="${i}" title="${esc(t('Entfernen','Remove'))}" aria-label="${esc(t('Entfernen','Remove'))}">×</button></span></li>`).join('')||`<li class="mut">${esc(t('Noch keine.','None yet.'))}</li>`}</ul>
    <div class="row"><select class="fundtyp" aria-label="${esc(t('Art des Schlagworts','Kind of tag'))}">${Object.keys(FUND_TYP).map(k=>`<option value="${k}">${esc(t(...FUND_TYP[k]))}</option>`).join('')}</select>
      <input type="text" class="fundneu" maxlength="60" placeholder="${esc(t('Neues Schlagwort','New tag'))}" aria-label="${esc(t('Neues Schlagwort','New tag'))}" list="fundkatlist">
      <datalist id="fundkatlist">${((FUND.stand&&FUND.stand.kategorien)||[]).map(k=>`<option value="${esc(k.wert)}">`).join('')}${Object.values((FUND.stand&&FUND.stand.knoten)||{}).flat().map(n=>`<option value="${esc(n)}">`).join('')}</datalist>
      <button type="button" class="b" data-fundadd="1">+ ${esc(t('Hinzufügen','Add'))}</button></div>
    ${(it.minus||[]).length?`<div class="mut small">${esc(t('Entfernt (kommt nicht wieder): ','Removed (does not come back): '))}${it.minus.map(x=>esc(x.wert)).join(', ')}</div>`:''}
    <div class="row">${it.weg?`<button type="button" class="b p" data-fundgo="1">${esc(t('Öffnen','Open'))}</button>`:''}</div>
    <div class="fundmsg ${FUND.err?'err':'mut'}" role="status">${esc(FUND.msg)}</div>`}
// Stufe C: each source on its own page (the day of an appointment, the card of a contact, the list, the conversation)
function fundGo(w,it){
  if(w.art==='termin'&&typeof KAL!=='undefined'){KAL.day=new Date((it.wann||0)*1000);icTabSet('cal','show');goSec('cal')}
  else if(w.art==='kontakt'&&typeof KON!=='undefined'){KON.sel=String(w.id);KON.form=null;icTabSet('kontakte','show');goSec('kontakte')}
  else if(w.art==='liste'&&typeof LST!=='undefined'){LST.sel=String(w.id);icTabSet('listen','show');goSec('listen')}
  else if(w.art==='chat'&&typeof openConvo==='function'){openConvo(String(w.id),true);goSec('chat')}
  else if(w.art==='erinnerung'&&typeof openMe==='function')openMe('notebox');
  else if(w.art==='bild'&&typeof openMe==='function')openMe('bildbox');
  else if(w.art==='musik'&&typeof openMe==='function')openMe('musikbox')}
// „Öffnen“: the original of an entry on its own page (a document, a Wissensbuch page, a mail, the other sources)
async function fundOriginal(it){const w=it.weg||{};if(w.art==='dokument'){if(typeof openMe==='function')await openMe('docbox');if(typeof docView==='function')docView(w.id)}
  else if(w.art==='wissensbuch'&&typeof WB!=='undefined'){WB.sel=w.id;icTabSet('wbuch','show');goSec('wbuch')}
  else if(w.art==='mail'||w.art==='anhang')await fundMail(w);
  else fundGo(w,it)}
// Stufe D: the Sofort-Karte under an answer („Original öffnen“, chat.js) and #fund=<id> from Telegram (start.js): the
// entry as the server gives it to this profile, then its original; nothing else happens
window.fundTreffer=async id=>{if(!FUND_ON||!/^\d{1,12}$/.test(String(id)))return;const {r,d}=await apiTry('/api/profile/fund/eintrag/'+encodeURIComponent(id));
  if(!r.ok){FUND.item=null;icTabSet('finden','show');goSec('finden');fundSay(errSay(r.status,d.detail,''),true);return}await fundOriginal(d)};
// the own tags: what stays (plus) and what is gone for good (minus), sent whole each time
async function fundTags(plus,minus){const it=FUND.item;if(!it)return;
  const {r,d}=await apiTry('/api/profile/fund/eintrag/'+encodeURIComponent(it.id)+'/schlagworte',{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({plus,minus})});
  if(!r.ok){fundSay(errSay(r.status,d.detail,''),true);return}await fundPick(it.id);fundSay(t('Gespeichert. Deine Schlagworte gehen vor.','Saved. Your tags come first.'))}
const fundOwn=()=>{const it=FUND.item;return{plus:(it.tags||[]).filter(x=>x.herkunft==='hand').map(x=>({typ:x.typ,wert:x.wert})),minus:(it.minus||[]).slice()}};
{document.body.addEventListener('click',async e=>{const b=e.target.closest('#fundview [data-fundback],#fundview [data-fundkeep],#fundview [data-fundrm],#fundview [data-fundadd],#fundview [data-fundgo]');if(!b)return;const D=b.dataset,it=FUND.item;
  if(D.fundback){FUND.item=null;fundDraw();return}
  if(!it)return;const own=fundOwn();
  if(D.fundgo)return fundOriginal(it);
  if(D.fundkeep!==undefined){const x=it.tags[+D.fundkeep];if(!x)return;own.plus.push({typ:x.typ,wert:x.wert});return fundTags(own.plus,own.minus)}
  if(D.fundrm!==undefined){const x=it.tags[+D.fundrm];if(!x)return;own.plus=own.plus.filter(y=>!(y.typ===x.typ&&y.wert===x.wert));
    if(x.herkunft!=='hand')own.minus.push({typ:x.typ,wert:x.wert});return fundTags(own.plus,own.minus)}
  if(D.fundadd){const v=document.querySelector('#fundview .fundneu'),ty=document.querySelector('#fundview .fundtyp');const w=(v&&v.value||'').trim();if(!w)return;
    own.minus=own.minus.filter(y=>!(y.typ===ty.value&&y.wert.toLowerCase()===w.toLowerCase()));own.plus.push({typ:ty.value,wert:w});return fundTags(own.plus,own.minus)}})}
function fundWorte(w){const S=FUND.stand;if(!S){w.innerHTML=`<div class="mut">${esc(t('Lade …','Loading …'))}</div>`;return}
  const k=S.kategorien||[];
  w.innerHTML=`<p class="mut">${esc(t('Die Kategorien sind eine feste Liste. Tippe eine an, um ihre Einträge zu sehen. Eigene Schlagworte setzt du am Eintrag; sie gehen immer vor.','The categories are a fixed list. Tap one to see its entries. Own tags are set on the entry; they always come first.'))}</p>
    <ul class="facts">${k.map(x=>`<li><span><a href="#" data-fundkat="${esc(x.wert)}">${esc(x.wert)}</a> <small class="mut">${esc(x.bereich?t('Bereich','Area'):t('Art','Kind'))}</small></span><b>${x.n}</b></li>`).join('')}</ul>
    <div class="mut">${esc(t(`${S.eigene} eigene Schlagworte`,`${S.eigene} own tags`))}</div>
    ${S.modell?`<h4>${esc(t('Neu vom Modell','New from the model'))}</h4>
    <p class="mut small">${esc(t(`Vorschläge des Sprachmodells, nach festen Regeln geprüft. ✓ übernimmt eines als deins, × entfernt es für immer. Noch ${S.modell_offen||0} Einträge ohne Vorschlag.`,`Proposals of the language model, checked by fixed rules. ✓ keeps one as yours, × removes it for good. ${S.modell_offen||0} entries still without a proposal.`))}</p>
    <ul class="facts fundmneu">${(S.modell_neu||[]).map((x,i)=>`<li><span>${fundTag(x)} <small class="mut">${esc(x.titel||'?')}</small></span><span><button type="button" class="b" data-fundmok="${i}" title="${esc(t('Übernehmen','Keep'))}">✓</button> <button type="button" class="b" data-fundmweg="${i}" title="${esc(t('Entfernen','Remove'))}" aria-label="${esc(t('Entfernen','Remove'))}">×</button></span></li>`).join('')||`<li class="mut">${esc(t('Gerade nichts Neues.','Nothing new right now.'))}</li>`}</ul>`:''}
    <div class="fundmsg ${FUND.err?'err':'mut'}" role="status">${esc(FUND.msg)}</div>`;
  w.querySelectorAll('[data-fundkat]').forEach(a=>a.onclick=e=>{e.preventDefault();FUND.kat=a.dataset.fundkat;FUND.q='';FUND.item=null;icTabSet('finden','show');goSec('finden');fundRun()});
  // ✓ and × on a proposal: the entry's own lists as the server has them now, then the one change (Hand vor Modell)
  w.querySelectorAll('[data-fundmok],[data-fundmweg]').forEach(b=>b.onclick=async()=>{const x=(S.modell_neu||[])[+(b.dataset.fundmok??b.dataset.fundmweg)];if(!x)return;
    const {r,d}=await apiTry('/api/profile/fund/eintrag/'+encodeURIComponent(x.id));if(!r.ok){fundSay(errSay(r.status,d.detail,''),true);return}
    const plus=(d.tags||[]).filter(y=>y.herkunft==='hand').map(y=>({typ:y.typ,wert:y.wert})),minus=(d.minus||[]).slice();
    if(b.dataset.fundmok!==undefined)plus.push({typ:x.typ,wert:x.wert});else minus.push({typ:x.typ,wert:x.wert});
    const s=await apiTry('/api/profile/fund/eintrag/'+encodeURIComponent(x.id)+'/schlagworte',{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({plus,minus})});
    if(!s.r.ok){fundSay(errSay(s.r.status,s.d.detail,''),true);return}fundSay(b.dataset.fundmok!==undefined?t('Übernommen. Es gilt jetzt als deins.','Kept. It counts as yours now.'):t('Entfernt. Das Modell schlägt es hier nie wieder vor.','Removed. The model never proposes it here again.'));fundStand()})}
function fundSettings(b){let s=$('fundset');if(!s){b.textContent='';s=document.createElement('div');s.id='fundset';s.className='card';b.appendChild(s)}fundSettingsPaint(s)}
function fundSettingsPaint(s){const S=FUND.stand;if(!S){s.innerHTML=`<div class="fundmsg ${FUND.err?'err':'mut'}" role="status">${esc(FUND.msg||t('Lade …','Loading …'))}</div>`;return}
  s.innerHTML=`<h3>${esc(t('Suchindex','Search index'))}</h3>
    <p class="mut">${esc(t('Finden merkt sich Titel, Felder und Schlagworte deiner Daten in einer eigenen Datei. Den Text der Dokumente sucht es über ihre eigene Suche. Mails, Anhänge, Termine und Kontakte liegen dort versiegelt, ihre Wörter nur als Marken; Gespräche sucht es über ihren Verlauf.','Find keeps the titles, fields and tags of your data in a file of its own. It searches the documents\' text through their own search. Mail, attachments, appointments and contacts lie there sealed, their words only as marks; conversations it searches through their history.'))}</p>
    <ul class="facts">${(S.quellen||[]).map(q=>`<li><span>${esc(t(q.de,q.en))}${q.an?'':` <small class="mut">${esc(t('nicht freigegeben','not released'))}</small>`}</span><b>${q.n}${q.stand?' · '+esc(q.stand):''}</b></li>`).join('')}
      <li><span>${esc(t('Noch nicht eingelesen','Not read yet'))}</span><b>${S.rueckstand}</b></li>
      ${(S.quellen||[]).some(q=>q.name==='mail'&&q.an)?`<li><span>${esc(t('Mails noch nicht eingelesen','Mails not read yet'))}</span><b>${S.mail_rest||0}</b></li>`:''}</ul>
    ${S.platz?`<div class="err">${esc(t('Platz knapp: Das Einlesen der Mails hält an, bis auf dem Spark wieder genug Speicher frei ist.','Space low: reading mail stops until enough storage is free on the Spark again.'))}</div>`:''}
    <div class="row"><button type="button" class="b" data-fundnew="1"${S.laeuft?' disabled':''}>${esc(S.laeuft?t('Läuft …','Running …'):t('Neu aufbauen','Rebuild'))}</button>
      <button type="button" class="b" data-funddel="1">${esc(t('Index löschen','Delete the index'))}</button></div>
    <div class="fundmsg ${FUND.err?'err':'mut'}" role="status">${esc(FUND.msg)}</div>`;
  s.querySelector('[data-fundnew]').onclick=async e=>{e.target.disabled=true;fundSay(t('Baue neu auf …','Rebuilding …'));
    const {r,d}=await apiTry('/api/profile/fund/neu',{method:'POST'});if(!r.ok)fundSay(errSay(r.status,d.detail,''),true);
    else fundSay(t(`Neu aufgebaut: ${d.neu} Einträge. Deine Schlagworte bleiben.`,`Rebuilt: ${d.neu} entries. Your tags stay.`));fundStand()};
  s.querySelector('[data-funddel]').onclick=async()=>{if(!confirm(t('Den Suchindex löschen? Er baut sich danach von selbst neu auf.','Delete the search index? It builds itself again afterwards.')))return;
    const hand=confirm(t('Auch deine eigenen Schlagworte löschen? Abbrechen behält sie.','Delete your own tags too? Cancel keeps them.'));
    const {r,d}=await apiTry('/api/profile/fund'+(hand?'?hand=true':''),{method:'DELETE'});if(!r.ok){fundSay(errSay(r.status,d.detail,''),true);return}
    FUND.hits=null;FUND.item=null;fundSay(t(`Gelöscht: ${d.geloescht} Einträge.`,`Deleted: ${d.geloescht} entries.`));fundStand()}}
