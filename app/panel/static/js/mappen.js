// Mappen (mappen.py, plan open-notebook Stufe 1, Push 1a; Dominik 2026-10-30 „1a 2a“): a page of its own in the menu.
// Left the Mappen, right the one tapped: its entries (own documents, Wissensbuch pages, notes) with the level
// aus / kurz / ganz each, the count of what goes to the model (≈ tokens of the budget) and „Im Assistenten fragen“,
// which binds the next questions in the Assistent to this Mappe (the chip above the conversation, window.MP_CHAT).
// The panel decides with fixed rules what goes to the model (mappen.plan), never the model. Names, goals and titles
// are the person's or the documents' own words: only through esc() or textContent, never markup.
const MP={list:null,sel:'',one:null,msg:'',err:false,seq:0,add:'',docs:null,pages:null,q:'',edit:false};
let MP_ON=false;
const MP_LEVEL=[['aus',t('aus','off')],['kurz',t('kurz','short')],['ganz',t('ganz','whole')]];
const MP_GOES={kurz:['geht kurz mit','goes short'],ganz:['geht ganz mit','goes whole'],suche:['zu groß: nur die passenden Stellen','too big: only the fitting parts'],
  aus:['geht nicht mit','does not go'],voll:['Budget voll: geht nicht mit','budget full: does not go']};
const MP_SYM={mappe:['Mappe','Collection'],haus:['Haus','Home'],garten:['Garten','Garden'],auto:['Auto','Car'],gesundheit:['Gesundheit','Health'],
  geld:['Geld','Money'],arbeit:['Arbeit','Work'],reise:['Reise','Travel'],lernen:['Lernen','Learning'],familie:['Familie','Family']};
const mpUrl=(id,x)=>'/api/profile/mappen'+(id?'/'+encodeURIComponent(id):'')+(x||'');
const mpNum=n=>Number(n||0).toLocaleString(L==='en'?'en-GB':'de-DE');
// the menu entry only for a signed-in profile the admin released Mappen for (start.js, like Finden)
window.mpStart=who=>{const on=!!(who&&who.profile&&who.collections);
  MP_ON=on;document.querySelectorAll('nav button[data-s=mappen]').forEach(b=>b.hidden=!on);
  if(!on&&window.MP_CHAT)mpUnbind()};
function mpOpen(){if(!PROFILE)return;const root=$('mproot'),box=$('mpbox');if(box){box.hidden=true;$('mappen').appendChild(box)}root.textContent='';
  root.appendChild(icTabs('mappen',[{k:'show',label:OWN_PAGES.mpbox[2],body:mpBody},
    {k:'set',label:t('Einstellungen','Settings'),body:()=>{const b=$('mpbox');b.hidden=false;mpSettings(b);return b}}]));
  mpLoad()}
window.mpOpen=mpOpen;
async function mpLoad(){if(!MP_ON)return;const seq=++MP.seq;const {r,d}=await apiTry(mpUrl());if(seq!==MP.seq)return;
  if(r.ok){MP.list=d;MP.err=false}else{MP.list=null;MP.msg=errSay(r.status,d.detail,'');MP.err=true}
  mpDraw();if(MP.sel)await mpPick(MP.sel,true)}
function mpBody(){const w=document.createElement('div');w.className='ld-box ld-frame mp';w.id='mpview';mpPaint(w);return w}
function mpDraw(){const w=$('mpview');if(w)mpPaint(w)}
function mpSay(x,err){MP.msg=String(x||'').slice(0,300);MP.err=!!err;const m=document.querySelector('#mpview .mpmsg');if(m){m.className='mpmsg '+(err?'err':'mut');m.textContent=MP.msg}}
function mpPaint(w){const D=MP.list;w.classList.toggle('ld-sel',!!MP.sel);
  if(!w.querySelector('.ld-split'))w.innerHTML=`<div class="ld-split"><div class="ld-list"></div><div class="ld-detail mpdet" hidden></div></div>`;
  const list=w.querySelector('.ld-list');
  if(!D){list.innerHTML=`<div class="ld-empty mut">${esc(MP.err?MP.msg:t('Lade die Mappen …','Loading the collections …'))}</div>`;return}
  const l=D.mappen||[];
  list.innerHTML=`<form class="ld-tools mpnew"><input type="text" class="mpname" maxlength="60" placeholder="${esc(t('Neue Mappe, z. B. Hauskauf','New collection, e.g. buying a house'))}" aria-label="${esc(t('Name der neuen Mappe','Name of the new collection'))}"><button class="b p" type="submit"${l.length>=D.max?' disabled':''}>${esc(t('Anlegen','Create'))}</button></form>
    ${l.length?'':`<div class="ld-empty mut">${esc(t('Noch keine Mappe. Eine Mappe bündelt Dokumente, Seiten des Wissensbuchs und Notizen zu einem Vorhaben; der Assistent antwortet dann nur daraus.','No collection yet. A collection bundles documents, knowledge book pages and notes for one undertaking; the assistant then answers only from them.'))}</div>`}
    ${l.map(m=>`<div class="ld-row${m.id===MP.sel?' on':''}" role="button" tabindex="0" data-mpsel="${esc(m.id)}"><span class="ld-ico mpico" aria-hidden="true">${esc((m.name||'?').slice(0,1).toUpperCase())}</span><span class="ld-mid"><b>${esc(m.name)}</b><small>${esc([m.ziel,t(`${m.n} Einträge`,`${m.n} entries`)].filter(Boolean).join(' · '))}</small></span><span class="ld-right">${window.MP_CHAT&&MP_CHAT.id===m.id?`<span class="ld-badge">${esc(t('im Assistenten','in the assistant'))}</span>`:''}</span></div>`).join('')}
    <div class="mut mpsum">${esc(t(`${l.length} von ${D.max} Mappen`,`${l.length} of ${D.max} collections`))}</div>
    <div class="mpmsg ${MP.err?'err':'mut'}" role="status">${esc(MP.msg)}</div>`;
  list.querySelector('.mpnew').onsubmit=async e=>{e.preventDefault();const i=list.querySelector('.mpname'),name=i.value.trim();if(!name)return;
    const r=await apiTry(mpUrl(),xjson('POST',{name}));if(!r.r.ok){mpSay(r.d.detail,true);return}
    MP.sel=r.d.id;MP.msg='';await mpLoad()};
  list.querySelectorAll('[data-mpsel]').forEach(r=>{const go=()=>mpPick(r.dataset.mpsel);r.onclick=go;r.onkeydown=e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();go()}}});
  mpDetail(w)}
async function mpPick(id,quiet){if(id!==MP.sel){MP.add='';MP.edit=false}MP.sel=id;
  if(id){const r=await apiTry(mpUrl(id));if(!r.r.ok){MP.one=null;MP.sel='';if(!quiet)mpSay(r.d.detail,true);mpDraw();return}MP.one=r.d}else MP.one=null;mpDraw()}
function mpBar(o){const pct=o.budget?Math.min(100,Math.round(100*o.token/o.budget)):0;
  return `<div class="mpbudget"><div class="mpbar" title="${esc(t(`${pct} % des Budgets`,`${pct} % of the budget`))}"><i style="width:${pct}%"></i></div>
    <div class="mut">${esc(t(`≈ ${mpNum(o.token)} von ${mpNum(o.budget)} Token gehen mit jeder Frage an das Modell`,`≈ ${mpNum(o.token)} of ${mpNum(o.budget)} tokens go to the model with every question`))}</div>
    ${o.summe.suche?`<div class="mut">${esc(t(`${o.summe.suche} zu große Einträge: von ihnen nur die Stellen, die zur Frage passen.`,`${o.summe.suche} entries too big: only the parts that fit the question.`))}</div>`:''}
    ${o.summe.voll?`<div class="err">${esc(t(`${o.summe.voll} Einträge passen nicht mehr ins Budget. Stell einige auf „kurz“ oder „aus“.`,`${o.summe.voll} entries no longer fit the budget. Set some to "short" or "off".`))}</div>`:''}</div>`}
function mpEntry(e){const lvl=MP_LEVEL.map(([k,l])=>`<button type="button" class="${e.stufe===k?'on':''}" data-mplvl="${k}" aria-pressed="${e.stufe===k}"${e.grau?' disabled':''}>${esc(l)}</button>`).join('');
  const tok=t(`kurz ≈ ${mpNum(e.token.kurz)} · ganz ≈ ${mpNum(e.token.ganz)} Token`,`short ≈ ${mpNum(e.token.kurz)} · whole ≈ ${mpNum(e.token.ganz)} tokens`);
  const what=e.art_eintrag==='dok'?[e.quelle==='notiz'?t('Notiz','Note'):e.datei,e.seiten?t(`${e.seiten} S.`,`${e.seiten} p.`):'',e.frist?t('Frist ','Due ')+e.frist:''].filter(Boolean).join(' · ')
    :t(`Wissensbuch · ${e.saetze} Sätze`,`Knowledge book · ${e.saetze} sentences`);
  return `<div class="ld-row mprow" data-mpart="${esc(e.art_eintrag)}" data-mpref="${esc(e.ref)}"><span class="ld-ico mpico" aria-hidden="true">${e.art_eintrag==='dok'?(e.quelle==='notiz'?'N':'D'):'S'}</span>
    <span class="ld-mid">${e.art_eintrag==='dok'?`<b><a href="#" data-mpdoc="${esc(e.ref)}">${esc(e.titel)}</a></b>`:`<b>${esc(e.titel)}</b>`}<small>${esc(what)}</small>
    <small>${esc(e.grau?t('Wissensbuch gesperrt: geht nicht mit','Knowledge book blocked: does not go'):t(...(MP_GOES[e.geht]||MP_GOES.aus))+' · '+tok)}</small></span>
    <span class="ld-right"><span class="segc" role="group" aria-label="${esc(t('Wie viel geht an das Modell','How much goes to the model'))}">${lvl}</span><button type="button" class="b" data-mpweg="1" title="${esc(t('Aus der Mappe nehmen (das Dokument bleibt)','Take out of the collection (the document stays)'))}" aria-label="${esc(t('Aus der Mappe nehmen','Take out of the collection'))}">${ic('x')}</button></span></div>`}
function mpDetail(w){const det=w.querySelector('.mpdet'),o=MP.one;if(!MP.sel||!o){det.hidden=true;det.textContent='';return}
  det.hidden=false;const bound=window.MP_CHAT&&MP_CHAT.id===o.id;const D=MP.list||{symbole:[]};
  const head=MP.edit?`<form class="mpedit"><label>${esc(t('Name','Name'))}<input type="text" name="name" maxlength="60" value="${esc(o.name)}"></label>
      <label>${esc(t('Ziel','Goal'))}<input type="text" name="ziel" maxlength="200" value="${esc(o.ziel)}" placeholder="${esc(t('Wofür ist die Mappe? (für später: Projekte im Assistenten)','What is the collection for? (for later: projects in the assistant)'))}"></label>
      <label>${esc(t('Symbol','Symbol'))}<select name="symbol">${(D.symbole||[]).map(s=>`<option value="${esc(s)}"${s===o.symbol?' selected':''}>${esc(t(...(MP_SYM[s]||[s,s])))}</option>`).join('')}</select></label>
      <div class="row"><button class="b p" type="submit">${esc(t('Speichern','Save'))}</button><button class="b" type="button" data-mpedit="0">${esc(t('Abbrechen','Cancel'))}</button></div></form>`
    :`<h3>${esc(o.name)}</h3><div class="mut">${esc([t(...(MP_SYM[o.symbol]||MP_SYM.mappe)),o.ziel].filter(Boolean).join(' · '))}</div>`;
  det.innerHTML=`<button class="b ld-back" type="button" data-mpback="1">‹ ${esc(OWN_PAGES.mpbox[1])}</button>${head}
    <div class="row"><button type="button" class="b p" data-mpask="1"${o.eintraege.length?'':' disabled'}>${esc(bound?t('Im Assistenten fragen (gebunden)','Ask in the assistant (bound)'):t('Im Assistenten fragen','Ask in the assistant'))}</button>
      ${MP.edit?'':`<button type="button" class="b" data-mpedit="1">${esc(t('Umbenennen','Rename'))}</button>`}<button type="button" class="b" data-mpdel="1">${esc(t('Mappe löschen','Delete collection'))}</button></div>
    ${mpBar(o)}
    <div class="row"><button type="button" class="b${MP.add==='dok'?' p':''}" data-mpadd="dok">+ ${esc(t('Dokument','Document'))}</button><button type="button" class="b${MP.add==='seite'?' p':''}" data-mpadd="seite">+ ${esc(t('Seite','Page'))}</button><button type="button" class="b${MP.add==='notiz'?' p':''}" data-mpadd="notiz">+ ${esc(t('Notiz','Note'))}</button></div>
    <div class="mpaddbox"></div>
    ${o.eintraege.length?`<div class="ld-grp"><span>${esc(t('Einträge','Entries'))}</span><span>${o.eintraege.length} / ${o.max_eintraege}</span></div>${o.eintraege.map(mpEntry).join('')}`
      :`<div class="ld-empty mut">${esc(t('Noch leer. Leg Dokumente, Seiten oder eine Notiz hinein; „kurz“ gibt dem Modell nur den Steckbrief, „ganz“ den ganzen Text.','Still empty. Put documents, pages or a note in; "short" gives the model only the profile card, "whole" the whole text.'))}</div>`}`;
  const f=det.querySelector('.mpedit');if(f)f.onsubmit=async e=>{e.preventDefault();const v=Object.fromEntries(new FormData(f));
    const r=await apiTry(mpUrl(o.id),xjson('PUT',{name:v.name,ziel:v.ziel,symbol:v.symbol}));if(!r.r.ok){mpSay(r.d.detail,true);return}
    MP.edit=false;if(bound)MP_CHAT.name=String(v.name||'').trim();mpChip();await mpLoad()};
  mpAddBox(det.querySelector('.mpaddbox'))}
// what can go in: the own documents (GET /api/profile/docs) and the own Wissensbuch pages, without those already in it
async function mpAddBox(box){if(!MP.add||!box)return;const o=MP.one,have=new Set(o.eintraege.map(e=>e.art_eintrag+':'+e.ref));
  if(MP.add==='notiz'){box.innerHTML=`<form class="mpnote"><input type="text" name="titel" maxlength="80" placeholder="${esc(t('Titel der Notiz','Title of the note'))}" aria-label="${esc(t('Titel der Notiz','Title of the note'))}">
      <textarea name="text" rows="5" maxlength="20000" placeholder="${esc(t('Text der Notiz; sie wird ein eigenes Dokument und liegt ganz in der Mappe.','Text of the note; it becomes a document of its own and lies whole in the collection.'))}" aria-label="${esc(t('Text der Notiz','Text of the note'))}"></textarea>
      <div class="row"><button class="b p" type="submit">${esc(t('Notiz speichern','Save note'))}</button></div></form>`;
    const f=box.querySelector('.mpnote');f.onsubmit=async e=>{e.preventDefault();const v=Object.fromEntries(new FormData(f));if(!String(v.text||'').trim())return;
      const r=await apiTry(mpUrl(o.id,'/notiz'),xjson('POST',{titel:v.titel,text:v.text}));if(!r.r.ok){mpSay(r.d.detail,true);return}
      MP.add='';await mpPick(o.id,true);mpSay(t('Notiz gespeichert und in die Mappe gelegt.','Note saved and put into the collection.'))};return}
  box.innerHTML=`<div class="mut">${esc(t('Lade …','Loading …'))}</div>`;let items=[];
  if(MP.add==='dok'){if(!MP.docs){try{MP.docs=await (await api('/api/profile/docs')).json()}catch(x){box.textContent=x.message;return}}
    items=MP.docs.map(d=>({ref:d.id,name:d.title||d.name,small:d.title&&d.title!==d.name?d.name:''}))}
  else{const r=await apiTry('/api/profile/wissensbuch');if(!r.r.ok){box.innerHTML=`<div class="mut">${esc(t('Das Wissensbuch ist für dieses Profil nicht freigegeben.','The knowledge book is not released for this profile.'))}</div>`;return}
    items=(r.d.seiten||[]).filter(p=>p.n).map(p=>({ref:p.id,name:p.title,small:t(`${p.n} Sätze`,`${p.n} sentences`)}))}
  const art=MP.add,free=items.filter(i=>!have.has(art+':'+i.ref));
  const paint=()=>{const q=MP.q.trim().toLowerCase(),shown=(q?free.filter(i=>i.name.toLowerCase().includes(q)):free).slice(0,200);
    box.querySelector('.mppicklist').innerHTML=shown.length?shown.map(i=>`<label class="ld-row"><input type="checkbox" class="ld-pick" value="${esc(i.ref)}"><span class="ld-mid"><b>${esc(i.name)}</b><small>${esc(i.small)}</small></span></label>`).join('')
      :`<div class="ld-empty mut">${esc(t('Nichts mehr da, was noch nicht in der Mappe liegt.','Nothing left that is not in the collection yet.'))}</div>`};
  box.innerHTML=`<div class="ld-tools"><input type="search" class="mpq" value="${esc(MP.q)}" placeholder="${esc(art==='dok'?t('Dokumente suchen','Search documents'):t('Seiten suchen','Search pages'))}" aria-label="${esc(t('Suchen','Search'))}">
    <span class="segc" role="group"><button type="button" class="on" data-mplvlnew="kurz">${esc(t('kurz','short'))}</button><button type="button" data-mplvlnew="ganz">${esc(t('ganz','whole'))}</button></span>
    <button class="b p" type="button" data-mpput="1">${esc(t('Hineinlegen','Put in'))}</button></div><div class="mppicklist"></div>`;
  paint();const qi=box.querySelector('.mpq');qi.oninput=()=>{MP.q=qi.value;paint()};
  box.querySelectorAll('[data-mplvlnew]').forEach(b=>b.onclick=()=>box.querySelectorAll('[data-mplvlnew]').forEach(x=>x.classList.toggle('on',x===b)));
  box.querySelector('[data-mpput]').onclick=async ev=>{const refs=[...box.querySelectorAll('.mppicklist input:checked')].map(c=>c.value).slice(0,20);if(!refs.length)return;
    const stufe=box.querySelector('[data-mplvlnew].on').dataset.mplvlnew;ev.target.disabled=true;
    const r=await apiTry(mpUrl(o.id,'/eintrag'),xjson('POST',{eintraege:refs.map(ref=>({art,ref,stufe}))}));
    if(!r.r.ok){mpSay(r.d.detail,true);ev.target.disabled=false;return}MP.add='';MP.q='';await mpPick(o.id,true);await mpLoad();
    mpSay(t(`${r.d.dazu} in die Mappe gelegt.`,`${r.d.dazu} put into the collection.`))}}
function mpSettings(b){const D=MP.list;b.innerHTML=`<div class="card"><h3>${esc(t('So arbeitet eine Mappe','How a collection works'))}</h3>
  <ul class="facts small"><li><span>${esc(t('aus: geht nicht an das Modell','off: does not go to the model'))}</span></li>
  <li><span>${esc(t('kurz: nur der Steckbrief des Dokuments oder Titel und erste Sätze der Seite','short: only the profile card of the document or the title and first sentences of the page'))}</span></li>
  <li><span>${esc(t('ganz: der ganze Text, solange er ins Budget passt; sonst nur die Stellen, die zur Frage passen','whole: the whole text while it fits the budget; else only the parts that fit the question'))}</span></li>
  <li><span>${esc(t('Budget je Frage','Budget per question'))}</span><b>${esc(D?t(`≈ ${mpNum(D.budget)} Token`,`≈ ${mpNum(D.budget)} tokens`):'')}</b></li></ul>
  <div class="mut">${esc(t('Das Budget stellt der Admin ein. Eine Mappe zu löschen nimmt nur die Zuordnung weg, nie ein Dokument. Sperrt der Admin Mappen für dich, löschst du alle unter Ich mit „Daten löschen“.','The admin sets the budget. Deleting a collection only removes the assignment, never a document. When the admin blocks collections for you, you delete all of them under Me with "Delete data".'))}</div></div>`}
// the chip above the conversation: the next questions go only to this Mappe until it is taken off (chat.js sends the id)
function mpChip(){const c=$('mpchip');if(!c)return;const m=window.MP_CHAT;c.hidden=!m;c.textContent='';if(!m)return;
  c.append(document.createTextNode(t('Mappe „','Collection "')+m.name+t('“',`"`)+' '));
  const x=document.createElement('button');x.type='button';x.className='b';x.appendChild(icNode('x'));x.title=t('Nicht mehr nur aus der Mappe','No longer only from the collection');
  x.setAttribute('aria-label',x.title);x.onclick=mpUnbind;c.append(x)}
function mpUnbind(){window.MP_CHAT=null;mpChip();mpDraw()}
window.mpBind=(id,name)=>{window.MP_CHAT={id:String(id),name:String(name||'').slice(0,60)};mpChip();goSec('chat');const i=$('chattext');if(i)i.focus()};
{document.body.addEventListener('click',async e=>{const b=e.target.closest('#mpview [data-mpback],#mpview [data-mpask],#mpview [data-mpedit],#mpview [data-mpdel],#mpview [data-mpadd],#mpview [data-mplvl],#mpview [data-mpweg],#mpview [data-mpdoc]');if(!b)return;
  const D=b.dataset,o=MP.one;if(!o)return;
  if(D.mpback){MP.sel='';MP.one=null;MP.add='';mpDraw();return}
  if(D.mpdoc){e.preventDefault();if(typeof docView==='function')docView(D.mpdoc);return}
  if(D.mpask){mpBind(o.id,o.name);return}
  if(D.mpedit){MP.edit=D.mpedit==='1';mpDraw();return}
  if(D.mpadd){MP.add=MP.add===D.mpadd?'':D.mpadd;MP.q='';if(D.mpadd==='dok')MP.docs=null;mpDraw();return}
  if(D.mpdel){if(!confirm(t('Mappe löschen? Die Dokumente bleiben.','Delete the collection? The documents stay.')))return;
    const r=await apiTry(mpUrl(o.id),{method:'DELETE'});if(!r.r.ok){mpSay(r.d.detail,true);return}
    if(window.MP_CHAT&&MP_CHAT.id===o.id)mpUnbind();MP.sel='';MP.one=null;await mpLoad();mpSay(t('Mappe gelöscht; die Dokumente bleiben.','Collection deleted; the documents stay.'));return}
  const row=b.closest('[data-mpref]');if(!row)return;const it={art:row.dataset.mpart,ref:row.dataset.mpref};
  if(D.mplvl){b.disabled=true;const r=await apiTry(mpUrl(o.id,'/eintrag'),xjson('PUT',{...it,stufe:D.mplvl}));if(!r.r.ok){mpSay(r.d.detail,true);b.disabled=false;return}await mpPick(o.id,true);return}
  if(D.mpweg){b.disabled=true;const r=await apiTry(mpUrl(o.id,'/eintrag'),xjson('DELETE',it));if(!r.r.ok){mpSay(r.d.detail,true);b.disabled=false;return}
    await mpPick(o.id,true);await mpLoad();mpSay(t('Aus der Mappe genommen; das Dokument bleibt.','Taken out of the collection; the document stays.'))}})}
