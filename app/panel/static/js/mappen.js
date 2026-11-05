// Mappen (mappen.py, plan open-notebook Stufe 1, Push 1a; Dominik 2026-10-30 „1a 2a“): a page of its own in the menu.
// Left the Mappen, right the one tapped: its entries (own documents, Wissensbuch pages, notes) with the level
// aus / kurz / ganz each, the count of what goes to the model (≈ tokens of the budget) and „Fragen“ (ask in the Assistent),
// which binds the next questions in the Assistent to this Mappe (the chip above the conversation, window.MP_CHAT).
// The panel decides with fixed rules what goes to the model (mappen.plan), never the model. Names, goals and titles
// are the person's or the documents' own words: only through esc() or textContent, never markup.
const MP={list:null,sel:'',one:null,msg:'',err:false,seq:0,add:'',docs:null,pages:null,q:'',edit:false,tab:'e',neu:false,info:false};
let MP_ON=false;
// Mappen ruhiger (plan mappen-layout, Dominik 2026-11-05 „ok“: 1a 2a 3a): the list in 300 px with ＋ in its head, the
// open Mappe beside it: head (symbol, name, „Ziel · N Einträge“, „Fragen“ as the page's only blue button, ⋯ with
// Umbenennen and Mappe löschen), a thin budget bar with ⓘ (how a Mappe works, before the tab „Einstellungen“), one
// segment Einträge · Auswertungen · Hörstück; every entry with its whole title, the level as a small menu and ⋯.
const MP_LEVEL=[['aus',t('aus','off')],['kurz',t('kurz','short')],['ganz',t('ganz','whole')]];
const MP_SYM={mappe:['Mappe','Collection','folder'],haus:['Haus','Home','home'],garten:['Garten','Garden','grow'],auto:['Auto','Car','route'],
  gesundheit:['Gesundheit','Health','heart'],geld:['Geld','Money','scales'],arbeit:['Arbeit','Work','box'],reise:['Reise','Travel','globe'],
  lernen:['Lernen','Learning','book'],familie:['Familie','Family','prof']};
const mpUrl=(id,x)=>'/api/profile/mappen'+(id?'/'+encodeURIComponent(id):'')+(x||'');
const mpNum=n=>Number(n||0).toLocaleString(L==='en'?'en-GB':'de-DE');
const mpIc=s=>(MP_SYM[s]||MP_SYM.mappe)[2];
// a ⋯ menu (or another button with a menu) as markup: items [[data attribute, value, label, danger, icon]]; mpview's
// click handler opens and closes it (the ic-menu look of ichteile.js)
window.mpMenu=(items,label,btn)=>`<span class="ic-menu"><button type="button" class="${btn?'b':'b mpmore'}" data-mpmenu="1" aria-haspopup="true" aria-expanded="false" aria-label="${esc(label)}" title="${esc(label)}">${btn||ic('more')}</button><div class="ic-pop" hidden>`+
  items.filter(Boolean).map(([k,v,l,d,i])=>`<button type="button"${d?' class="danger"':''} data-${k}="${esc(v)}">${i?ic(i):''}${esc(l)}</button>`).join('')+`</div></span>`;
// the menu entry only for a signed-in profile the admin released Mappen for (start.js, like Finden)
window.mpStart=who=>{const on=!!(who&&who.profile&&who.collections);
  MP_ON=on;document.querySelectorAll('nav button[data-s=mappen]').forEach(b=>b.hidden=!on);
  if(!on&&window.MP_CHAT)mpUnbind()};
// no tabs on the page (1a): only the list and the open Mappe; #mpbox stays the place of every way and card
function mpOpen(){if(!PROFILE)return;const root=$('mproot');root.textContent='';root.appendChild(mpBody());mpLoad()}
window.mpOpen=mpOpen;
async function mpLoad(){if(!MP_ON)return;const seq=++MP.seq;const {r,d}=await apiTry(mpUrl());if(seq!==MP.seq)return;
  if(r.ok){MP.list=d;MP.err=false}else{MP.list=null;MP.msg=errSay(r.status,d.detail,'');MP.err=true}
  mpDraw();if(MP.sel)await mpPick(MP.sel,true)}
function mpBody(){const w=document.createElement('div');w.className='ld-box ld-frame mp';w.id='mpview';mpPaint(w);return w}
function mpDraw(){const w=$('mpview');if(w)mpPaint(w)}
function mpSay(x,err){MP.msg=String(x||'').slice(0,300);MP.err=!!err;document.querySelectorAll('#mpview .mpmsg').forEach(m=>{m.className='mpmsg '+(err?'err':'mut');m.textContent=MP.msg})}
const mpMsg=()=>`<div class="mpmsg ${MP.err?'err':'mut'}" role="status">${esc(MP.msg)}</div>`;
function mpPaint(w){const D=MP.list;w.classList.toggle('ld-sel',!!MP.sel);
  if(!w.querySelector('.ld-split'))w.innerHTML=`<div class="ld-split"><div class="ld-list"></div><div class="ld-detail mpdet"></div></div>`;
  const list=w.querySelector('.ld-list');
  if(!D){list.innerHTML=`<div class="ld-empty mut">${esc(MP.err?MP.msg:t('Lade die Mappen …','Loading the collections …'))}</div>`;w.querySelector('.mpdet').hidden=true;return}
  const l=D.mappen||[],full=l.length>=D.max,form=(MP.neu||!l.length)&&!full;
  list.innerHTML=`<div class="mphead"><span><b>${esc(OWN_PAGES.mpbox[1])}</b><small>${esc(t(`${l.length} von ${D.max}`,`${l.length} of ${D.max}`))}</small></span>`+
    `<button type="button" class="b mpplus" data-mpneu="1" aria-expanded="${form}" aria-label="${esc(t('Neue Mappe','New collection'))}" title="${esc(full?t(`Höchstens ${D.max} Mappen`,`At most ${D.max} collections`):t('Neue Mappe','New collection'))}"${full?' disabled':''}>${ic('plus')}</button></div>
    ${form?`<form class="ld-tools mpnew"><input type="text" class="mpname" maxlength="60" placeholder="${esc(t('Neue Mappe, z. B. Hauskauf','New collection, e.g. buying a house'))}" aria-label="${esc(t('Name der neuen Mappe','Name of the new collection'))}"><button class="b" type="submit">${esc(t('Anlegen','Create'))}</button></form>`:''}
    ${l.length?'':`<div class="ld-empty mut">${esc(t('Noch keine Mappe. Eine Mappe bündelt Dokumente, Seiten des Wissensbuchs und Notizen zu einem Vorhaben; der Assistent antwortet dann nur daraus.','No collection yet. A collection bundles documents, knowledge book pages and notes for one undertaking; the assistant then answers only from them.'))}</div>`}
    ${l.map(m=>`<div class="ld-row${m.id===MP.sel?' on':''}" role="button" tabindex="0" data-mpsel="${esc(m.id)}"><span class="ld-ico" aria-hidden="true">${ic(mpIc(m.symbol))}</span><span class="ld-mid"><b>${esc(m.name)}</b><small>${esc(m.ziel||'')}</small></span><span class="ld-right">${window.MP_CHAT&&MP_CHAT.id===m.id?`<span class="ld-badge">${esc(t('im Assistenten','in the assistant'))}</span>`:''}<span class="ld-when" title="${esc(t(`${m.n} Einträge`,`${m.n} entries`))}">${m.n}</span></span></div>`).join('')}
    ${MP.sel?'':mpMsg()}`;
  const f=list.querySelector('.mpnew');if(f){if(MP.neu)f.querySelector('.mpname').focus();f.onsubmit=async e=>{e.preventDefault();const i=f.querySelector('.mpname'),name=i.value.trim();if(!name)return;
    const r=await apiTry(mpUrl(),xjson('POST',{name}));if(!r.r.ok){mpSay(r.d.detail,true);return}
    MP.sel=r.d.id;MP.neu=false;MP.tab='e';MP.msg='';await mpLoad()}}
  list.querySelectorAll('[data-mpsel]').forEach(r=>{const go=()=>mpPick(r.dataset.mpsel);r.onclick=go;r.onkeydown=e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();go()}}});
  mpDetail(w)}
async function mpPick(id,quiet){if(id!==MP.sel){MP.add='';MP.edit=false;MP.info=false;MP.tab='e'}MP.sel=id;
  if(id){const r=await apiTry(mpUrl(id));if(!r.r.ok){MP.one=null;MP.sel='';if(!quiet)mpSay(r.d.detail,true);mpDraw();return}MP.one=r.d}else MP.one=null;mpDraw()}
// the budget as a short number under a thin bar; too big or no longer fitting as a short addition, red only when full
function mpBar(o){const pct=o.budget?Math.min(100,Math.round(100*o.token/o.budget)):0;
  return `<div class="mpbud"><div class="mpbar" title="${esc(t(`≈ ${mpNum(o.token)} von ${mpNum(o.budget)} Token gehen mit jeder Frage an das Modell`,`≈ ${mpNum(o.token)} of ${mpNum(o.budget)} tokens go to the model with every question`))}"><i style="width:${pct}%"></i></div>
    <div class="mpbudrow"><small>${esc(t(`${mpNum(o.token)} / ${mpNum(o.budget)} Token`,`${mpNum(o.token)} / ${mpNum(o.budget)} tokens`))}</small>`+
    (o.summe.suche?`<small>· ${esc(t(`${o.summe.suche} nur in Auszügen`,`${o.summe.suche} only in parts`))}</small>`:'')+
    (o.summe.voll?`<small class="err">· ${esc(t(`${o.summe.voll} passen nicht mehr ins Budget`,`${o.summe.voll} no longer fit the budget`))}</small>`:'')+
    `<button type="button" class="mpinfo" data-mpinfo="1" aria-expanded="${MP.info}" aria-label="${esc(t('So arbeitet eine Mappe','How a collection works'))}" title="${esc(t('So arbeitet eine Mappe','How a collection works'))}">${ic('info')}</button></div></div>`}
// ⓘ: what the tab „Einstellungen“ said before (aus/kurz/ganz, the budget, deleting takes only the assignment)
function mpInfo(o){const D=MP.list;return `<div class="mpinfobox"><b>${esc(t('So arbeitet eine Mappe','How a collection works'))}</b>
  <ul class="facts small"><li><span>${esc(t('aus: geht nicht an das Modell','off: does not go to the model'))}</span></li>
  <li><span>${esc(t('kurz: nur der Steckbrief des Dokuments (mit seiner Kurzfassung und seinen Kernaussagen, wenn Auswertungen an sind) oder Titel und erste Sätze der Seite','short: only the profile card of the document (with its summary and key points while analyses are on) or the title and first sentences of the page'))}</span></li>
  <li><span>${esc(t('ganz: der ganze Text, solange er ins Budget passt; sonst nur die Stellen, die zur Frage passen','whole: the whole text while it fits the budget; else only the parts that fit the question'))}</span></li>
  <li><span>${esc(t('Budget je Frage','Budget per question'))}</span><b>${esc(D?t(`≈ ${mpNum(D.budget)} Token`,`≈ ${mpNum(D.budget)} tokens`):'')}</b></li></ul>
  <p class="mut">${esc(t('„Fragen“ bindet die nächsten Fragen im Assistenten an diese Mappe, bis du das Schild über dem Gespräch abnimmst. Das Budget stellt der Admin ein. Eine Mappe zu löschen nimmt nur die Zuordnung weg, nie ein Dokument. Sperrt der Admin Mappen für dich, löschst du alle unter Ich mit „Daten löschen“.','"Ask" binds the next questions in the assistant to this collection until you take off the chip above the conversation. The admin sets the budget. Deleting a collection only removes the assignment, never a document. When the admin blocks collections for you, you delete all of them under Me with "Delete data".'))}</p>`+
  (o.hoerstueck?`<p class="mut">${esc(t('Hörstück: zwei oder drei Stimmen (A Moderation, B Fachstimme, C Nachfrage) sprechen über die Einträge auf „kurz“ und „ganz“. Der Spark prüft jede Zeile des Drehbuchs gegen die Dokumente; was nicht belegt ist, fällt weg. Ein Hörstück wird nie ein Dokument.','Audio overview: two or three voices (A host, B expert, C questions) talk about the entries on "short" and "whole". The Spark checks every line of the script against the documents; what is not backed is dropped. An audio overview never becomes a document.'))}</p>`:'')+`</div>`}
// one entry: symbol, the whole title, kind and ≈ tokens of the chosen level (a note only when too big, full or blocked),
// the level as a small menu (3a), ⋯ with Öffnen and Aus der Mappe nehmen; tapping a document opens it
function mpEntry(e){const dok=e.art_eintrag==='dok',note=dok&&e.quelle==='notiz';
  const ext=dok&&!note?String(e.datei||'').split('.').pop().toUpperCase():'';
  const kind=dok?[note?t('Notiz','Note'):ext&&ext.length<=5?ext:t('Dokument','Document'),e.seiten?t(`${e.seiten} S.`,`${e.seiten} p.`):'',e.frist?t('Frist ','Due ')+e.frist:'']
    :[t('Wissensbuch','Knowledge book'),t(`${e.saetze} Sätze`,`${e.saetze} sentences`)];
  const how=e.grau?t('Wissensbuch gesperrt','knowledge book blocked'):e.geht==='suche'?t('zu groß: nur passende Stellen','too big: only fitting parts'):e.geht==='voll'?t('Budget voll','budget full'):e.stufe!=='aus'?t(`≈ ${mpNum(e.token[e.stufe])} Token`,`≈ ${mpNum(e.token[e.stufe])} tokens`):'';
  const lvl=`<select class="ld-chip mplvl" data-mplvl="1" aria-label="${esc(t('Wie viel geht an das Modell','How much goes to the model'))}"${e.grau?' disabled':''}>${MP_LEVEL.map(([k,l])=>`<option value="${k}"${e.stufe===k?' selected':''}>${esc(l)}</option>`).join('')}</select>`;
  return `<div class="ld-row" data-mpart="${esc(e.art_eintrag)}" data-mpref="${esc(e.ref)}"${dok?` role="button" tabindex="0" data-mpdoc="${esc(e.ref)}"`:''}><span class="ld-ico" aria-hidden="true">${ic(note?'note':dok?'doc':'wbuch')}</span>
    <span class="ld-mid"><b>${esc(e.titel)}</b><small${how&&e.geht==='voll'?' class="err"':''}>${esc([...kind,how].filter(Boolean).join(' · '))}</small></span>
    <span class="ld-right">${lvl}${mpMenu([dok&&['mpdoc',e.ref,t('Öffnen','Open')],['mpweg','1',t('Aus der Mappe nehmen','Take out of the collection'),1]],t('Mehr zu ','More on ')+e.titel)}</span></div>`}
function mpTabs(o){const n=o.eintraege.filter(e=>(e.auswertungen||[]).length).length;
  return [['e',OWN_PAGES.mpbox[2],o.eintraege.length],o.auswertungen?['a',t('Auswertungen','Analyses'),n]:null,
    o.hoerstueck?['h',t('Hörstück','Audio overview'),typeof hsN==='function'?hsN(o.id):'']:null].filter(Boolean)}
// the segment again (hoerstueck.js calls it when the count of its Hörstücke arrived)
window.mpSeg=()=>{const det=document.querySelector('#mpview .mpdet'),bar=det&&det.querySelector('.mpsegbar'),o=MP.one;if(!bar||!o)return;
  const items=mpTabs(o);bar.textContent='';if(items.length>1)bar.appendChild(ldSeg(items,MP.tab,k=>{MP.tab=k;MP.add='';mpDraw()},t('Teil der Mappe','Part of the collection')))};
function mpDetail(w){const det=w.querySelector('.mpdet'),o=MP.one;det.hidden=false;
  if(!MP.sel||!o){det.classList.add('ld-idle');det.textContent='';
    if(MP.list&&(MP.list.mappen||[]).length)det.appendChild(ldEmpty('folder',t('Wähle links eine Mappe.','Pick a collection on the left.')));return}
  det.classList.remove('ld-idle');const bound=window.MP_CHAT&&MP_CHAT.id===o.id;const D=MP.list||{symbole:[]};
  if(!mpTabs(o).some(x=>x[0]===MP.tab))MP.tab='e';
  const edit=MP.edit?`<form class="mpedit"><label>${esc(t('Name','Name'))}<input type="text" name="name" maxlength="60" value="${esc(o.name)}"></label>
      <label>${esc(t('Ziel','Goal'))}<input type="text" name="ziel" maxlength="200" value="${esc(o.ziel)}" placeholder="${esc(t('Wofür ist die Mappe?','What is the collection for?'))}"></label>
      <label>${esc(t('Symbol','Symbol'))}<select name="symbol">${(D.symbole||[]).map(s=>`<option value="${esc(s)}"${s===o.symbol?' selected':''}>${esc(t(...(MP_SYM[s]||[s,s])))}</option>`).join('')}</select></label>
      <div class="row"><button class="b" type="submit">${esc(t('Speichern','Save'))}</button><button class="b" type="button" data-mpedit="0">${esc(t('Abbrechen','Cancel'))}</button></div></form>`:'';
  det.innerHTML=`<button class="b ld-back" type="button" data-mpback="1">‹ ${esc(OWN_PAGES.mpbox[1])}</button>
    <div class="mptop"><span class="ld-ico" aria-hidden="true" title="${esc(t(...(MP_SYM[o.symbol]||MP_SYM.mappe)))}">${ic(mpIc(o.symbol))}</span>
      <span class="mpname"><b>${esc(o.name)}</b><small>${esc([o.ziel,t(`${o.eintraege.length} Einträge`,`${o.eintraege.length} entries`)].filter(Boolean).join(' · '))}</small></span>
      <button type="button" class="b p" data-mpask="1" aria-pressed="${!!bound}" title="${esc(bound?t('Der Assistent fragt schon nur aus dieser Mappe','The assistant already asks only from this collection'):t('Im Assistenten nur aus dieser Mappe fragen','Ask in the assistant only from this collection'))}"${o.eintraege.length?'':' disabled'}>${ic('chat')}${esc(t('Fragen','Ask'))}</button>
      ${mpMenu([['mpedit','1',t('Umbenennen','Rename')],['mpdel','1',t('Mappe löschen','Delete collection'),1]],t('Mehr zur Mappe','More on the collection'))}</div>
    ${edit}${mpBar(o)}${MP.info?mpInfo(o):''}${mpMsg()}<div class="mpsegbar"></div><div class="mptab"></div>`;
  if(typeof hsFor==='function')hsFor(o);   // the Hörstücke of this Mappe (their count in the segment)
  mpSeg();const tab=det.querySelector('.mptab');
  const f=det.querySelector('.mpedit');if(f)f.onsubmit=async e=>{e.preventDefault();const v=Object.fromEntries(new FormData(f));
    const r=await apiTry(mpUrl(o.id),xjson('PUT',{name:v.name,ziel:v.ziel,symbol:v.symbol}));if(!r.r.ok){mpSay(r.d.detail,true);return}
    MP.edit=false;if(bound)MP_CHAT.name=String(v.name||'').trim();mpChip();await mpLoad()};
  if(MP.tab==='h'){const box=document.createElement('div');box.className='hsbox';tab.appendChild(box);if(typeof hsShow==='function')hsShow(box,o);return}
  if(MP.tab==='a'){tab.innerHTML=mpAw(o);return}
  const full=o.eintraege.length>=o.max_eintraege;
  tab.innerHTML=`<div class="mpsub"><div class="ld-grp"><span>${esc(t(`${o.eintraege.length} von ${o.max_eintraege} Einträgen`,`${o.eintraege.length} of ${o.max_eintraege} entries`))}</span></div>`+
    (full?'':mpMenu([['mpadd','dok',t('Dokument','Document'),0,'doc'],['mpadd','seite',t('Seite aus dem Wissensbuch','Page of the knowledge book'),0,'wbuch'],['mpadd','notiz',t('Notiz','Note'),0,'note']],
      t('Hinzufügen','Add'),ic('plus')+esc(t('Hinzufügen','Add'))))+`</div><div class="mpaddbox"></div>`+
    (o.eintraege.length?o.eintraege.map(mpEntry).join('')
      :`<div class="ld-empty mut">${esc(t('Noch leer. Leg Dokumente, Seiten oder eine Notiz hinein; „kurz“ gibt dem Modell nur den Steckbrief, „ganz“ den ganzen Text.','Still empty. Put documents, pages or a note in; "short" gives the model only the profile card, "whole" the whole text.'))}</div>`);
  mpAddBox(tab.querySelector('.mpaddbox'))}
// Auswertungen: one row per document of the Mappe; they come by themselves (Ich → Dokumente → a document), tapping
// opens the document with its Auswertung
function mpAw(o){const docs=o.eintraege.filter(e=>e.art_eintrag==='dok');
  if(!docs.length)return `<div class="ld-empty mut">${esc(t('Noch kein Dokument in der Mappe.','No document in the collection yet.'))}</div>`;
  return `<div class="ld-grp"><span>${esc(t('Auswertungen der Dokumente; mit „kurz“ gehen sie an das Modell mit','Analyses of the documents; with "short" they go to the model'))}</span></div>`+docs.map(e=>{const a=e.auswertungen||[];
    return `<div class="ld-row" role="button" tabindex="0" data-mpdoc="${esc(e.ref)}"><span class="ld-ico" aria-hidden="true">${ic(e.quelle==='notiz'?'note':'doc')}</span><span class="ld-mid"><b>${esc(e.titel)}</b><small>${esc(a.length?a.map(n=>t(n[0],n[1])).join(' · '):t('noch keine Auswertung','no analysis yet'))}</small></span><span class="ld-right">${a.length?`<span class="ld-st ok">${esc(t('fertig','done'))}</span>`:''}${ic('chev')}</span></div>`}).join('')}
// what can go in: the own documents (GET /api/profile/docs) and the own Wissensbuch pages, without those already in it
async function mpAddBox(box){if(!MP.add||!box)return;const o=MP.one,have=new Set(o.eintraege.map(e=>e.art_eintrag+':'+e.ref));
  const close=`<button class="b" type="button" data-mpadd="${esc(MP.add)}">${esc(t('Abbrechen','Cancel'))}</button>`;
  if(MP.add==='notiz'){box.innerHTML=`<form class="mpnote"><input type="text" name="titel" maxlength="80" placeholder="${esc(t('Titel der Notiz','Title of the note'))}" aria-label="${esc(t('Titel der Notiz','Title of the note'))}">
      <textarea name="text" rows="5" maxlength="20000" placeholder="${esc(t('Text der Notiz; sie wird ein eigenes Dokument und liegt ganz in der Mappe.','Text of the note; it becomes a document of its own and lies whole in the collection.'))}" aria-label="${esc(t('Text der Notiz','Text of the note'))}"></textarea>
      <div class="row"><button class="b" type="submit">${esc(t('Notiz speichern','Save note'))}</button>${close}</div></form>`;
    const f=box.querySelector('.mpnote');f.onsubmit=async e=>{e.preventDefault();const v=Object.fromEntries(new FormData(f));if(!String(v.text||'').trim())return;
      const r=await apiTry(mpUrl(o.id,'/notiz'),xjson('POST',{titel:v.titel,text:v.text}));if(!r.r.ok){mpSay(r.d.detail,true);return}
      MP.add='';await mpPick(o.id,true);mpSay(t('Notiz gespeichert und in die Mappe gelegt.','Note saved and put into the collection.'))};return}
  box.innerHTML=`<div class="mut">${esc(t('Lade …','Loading …'))}</div>`;let items=[];
  if(MP.add==='dok'){if(!MP.docs){try{MP.docs=await (await api('/api/profile/docs')).json()}catch(x){box.textContent=x.message;return}}
    items=MP.docs.map(d=>({ref:d.id,name:d.title||d.name,small:d.title&&d.title!==d.name?d.name:''}))}
  else{const r=await apiTry('/api/profile/wissensbuch');if(!r.r.ok){box.innerHTML=`<div class="mut">${esc(t('Das Wissensbuch ist für dieses Profil nicht freigegeben.','The knowledge book is not released for this profile.'))}</div><div class="row">${close}</div>`;return}
    items=(r.d.seiten||[]).filter(p=>p.n).map(p=>({ref:p.id,name:p.title,small:t(`${p.n} Sätze`,`${p.n} sentences`)}))}
  const art=MP.add,free=items.filter(i=>!have.has(art+':'+i.ref));
  const paint=()=>{const q=MP.q.trim().toLowerCase(),shown=(q?free.filter(i=>i.name.toLowerCase().includes(q)):free).slice(0,200);
    box.querySelector('.mppicklist').innerHTML=shown.length?shown.map(i=>`<label class="ld-row"><input type="checkbox" class="ld-pick" value="${esc(i.ref)}"><span class="ld-mid"><b>${esc(i.name)}</b><small>${esc(i.small)}</small></span></label>`).join('')
      :`<div class="ld-empty mut">${esc(t('Nichts mehr da, was noch nicht in der Mappe liegt.','Nothing left that is not in the collection yet.'))}</div>`};
  box.innerHTML=`<div class="ld-tools"><input type="search" class="mpq" value="${esc(MP.q)}" placeholder="${esc(art==='dok'?t('Dokumente suchen','Search documents'):t('Seiten suchen','Search pages'))}" aria-label="${esc(t('Suchen','Search'))}">
    <span class="segc" role="group"><button type="button" class="on" data-mplvlnew="kurz">${esc(t('kurz','short'))}</button><button type="button" data-mplvlnew="ganz">${esc(t('ganz','whole'))}</button></span>
    <button class="b" type="button" data-mpput="1">${esc(t('Hineinlegen','Put in'))}</button>${close}</div><div class="mppicklist"></div>`;
  paint();const qi=box.querySelector('.mpq');qi.oninput=()=>{MP.q=qi.value;paint()};
  box.querySelectorAll('[data-mplvlnew]').forEach(b=>b.onclick=()=>box.querySelectorAll('[data-mplvlnew]').forEach(x=>x.classList.toggle('on',x===b)));
  box.querySelector('[data-mpput]').onclick=async ev=>{const refs=[...box.querySelectorAll('.mppicklist input:checked')].map(c=>c.value).slice(0,20);if(!refs.length)return;
    const stufe=box.querySelector('[data-mplvlnew].on').dataset.mplvlnew;ev.target.disabled=true;
    const r=await apiTry(mpUrl(o.id,'/eintrag'),xjson('POST',{eintraege:refs.map(ref=>({art,ref,stufe}))}));
    if(!r.r.ok){mpSay(r.d.detail,true);ev.target.disabled=false;return}MP.add='';MP.q='';await mpPick(o.id,true);await mpLoad();
    mpSay(t(`${r.d.dazu} in die Mappe gelegt.`,`${r.d.dazu} put into the collection.`))}}
// the chip above the conversation: the next questions go only to this Mappe until it is taken off (chat.js sends the id)
function mpChip(){const c=$('mpchip');if(!c)return;const m=window.MP_CHAT;c.hidden=!m;c.textContent='';if(!m)return;
  c.append(document.createTextNode(t('Mappe „','Collection "')+m.name+t('“',`"`)+' '));
  const x=document.createElement('button');x.type='button';x.className='b';x.appendChild(icNode('x'));x.title=t('Nicht mehr nur aus der Mappe','No longer only from the collection');
  x.setAttribute('aria-label',x.title);x.onclick=mpUnbind;c.append(x)}
function mpUnbind(){window.MP_CHAT=null;mpChip();mpDraw()}
window.mpBind=(id,name)=>{window.MP_CHAT={id:String(id),name:String(name||'').slice(0,60)};mpChip();goSec('chat');const i=$('chattext');if(i)i.focus()};
{document.body.addEventListener('click',async e=>{
  // a menu of the page (⋯, „＋ Hinzufügen“): open its list and close every other; an entry of it closes it again
  const m=e.target.closest('#mpview [data-mpmenu]');
  if(m){const pop=m.nextElementSibling,open=!pop.hidden;document.querySelectorAll('.ic-pop').forEach(p=>p.hidden=true);
    document.querySelectorAll('#mpview [data-mpmenu]').forEach(x=>x.setAttribute('aria-expanded','false'));pop.hidden=open;m.setAttribute('aria-expanded',String(!open));return}
  const pop=e.target.closest('#mpview .ic-pop');if(pop&&e.target.closest('button,a')){pop.hidden=true;const k=pop.previousElementSibling;if(k)k.setAttribute('aria-expanded','false')}
  if(e.target.closest('#mpview [data-mpneu]')){MP.neu=!MP.neu;mpDraw();return}
  const b=e.target.closest('#mpview [data-mpback],#mpview [data-mpask],#mpview [data-mpedit],#mpview [data-mpdel],#mpview [data-mpadd],#mpview [data-mpweg],#mpview [data-mpdoc],#mpview [data-mpinfo]');if(!b)return;
  if(b.classList.contains('ld-row')&&e.target.closest('select,.ic-menu,label'))return;   // the level and ⋯ in a row keep their own click
  const D=b.dataset,o=MP.one;if(!o)return;
  if(D.mpback){MP.sel='';MP.one=null;MP.add='';mpDraw();return}
  if(D.mpdoc){e.preventDefault();if(typeof docView==='function')docView(D.mpdoc);return}
  if(D.mpask){mpBind(o.id,o.name);return}
  if(D.mpinfo){MP.info=!MP.info;mpDraw();return}
  if(D.mpedit){MP.edit=D.mpedit==='1';mpDraw();return}
  if(D.mpadd){MP.add=MP.add===D.mpadd?'':D.mpadd;MP.q='';if(D.mpadd==='dok')MP.docs=null;mpDraw();return}
  if(D.mpdel){if(!confirm(t('Mappe löschen? Die Dokumente bleiben.','Delete the collection? The documents stay.')))return;
    const r=await apiTry(mpUrl(o.id),{method:'DELETE'});if(!r.r.ok){mpSay(r.d.detail,true);return}
    if(window.MP_CHAT&&MP_CHAT.id===o.id)mpUnbind();MP.sel='';MP.one=null;await mpLoad();mpSay(t('Mappe gelöscht; die Dokumente bleiben.','Collection deleted; the documents stay.'));return}
  const row=b.closest('[data-mpref]');if(!row)return;const it={art:row.dataset.mpart,ref:row.dataset.mpref};
  if(D.mpweg){b.disabled=true;const r=await apiTry(mpUrl(o.id,'/eintrag'),xjson('DELETE',it));if(!r.r.ok){mpSay(r.d.detail,true);b.disabled=false;return}
    await mpPick(o.id,true);await mpLoad();mpSay(t('Aus der Mappe genommen; das Dokument bleibt.','Taken out of the collection; the document stays.'))}});
  // the level of an entry (its small menu): aus / kurz / ganz
  document.body.addEventListener('change',async e=>{const s=e.target.closest('#mpview select[data-mplvl]');if(!s||!MP.one)return;const o=MP.one,row=s.closest('[data-mpref]');
    s.disabled=true;const r=await apiTry(mpUrl(o.id,'/eintrag'),xjson('PUT',{art:row.dataset.mpart,ref:row.dataset.mpref,stufe:s.value}));
    if(!r.r.ok){mpSay(r.d.detail,true);s.disabled=false;return}await mpPick(o.id,true)});
  document.body.addEventListener('keydown',e=>{if((e.key==='Enter'||e.key===' ')&&e.target.matches&&e.target.matches('#mpview .ld-row[data-mpdoc]')){e.preventDefault();e.target.click()}})}

// Finden (finden.js, Push 1b): the chooser „Alle Mappen“ / one own Mappe beside source and category; the page then
// finds only what lies in that Mappe (every level: the person looks herself). The Spark checks the id again
// (mappen.fuer_seite): another profile's or an unknown one finds nothing. Asks for the list once, then draws Finden again.
let MP_FUNDLOAD=false;
window.mpFundWahl=sel=>{if(!MP_ON)return'';
  if(!MP.list){if(!MP_FUNDLOAD){MP_FUNDLOAD=true;mpLoad().then(()=>{if(MP.list&&typeof fundDraw==='function')fundDraw()})}return''}
  const l=MP.list.mappen||[];if(!l.length&&!sel)return'';
  return `<select class="fundmappe" aria-label="${esc(t('Mappe','Collection'))}"><option value="">${esc(t('Alle Mappen','All collections'))}</option>${l.map(m=>`<option value="${esc(m.id)}"${m.id===sel?' selected':''}>${esc(m.name)}</option>`).join('')}</select>`};
