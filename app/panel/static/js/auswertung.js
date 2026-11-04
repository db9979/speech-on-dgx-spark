// Auswertungen (auswertung.py, plan open-notebook Stufe 2, Push 2a): the sheet in the details of an own document under
// Ich → Dokumente. Kurzfassung and Kernaussagen come by themselves in quiet minutes; Fragen, Inhaltsverzeichnis,
// Fristen and Beteiligte per click „Erstellen“. Every point with its place (page · heading) as a chip that opens the
// text there, „Stimmt nicht“ for the model's points. The panel checked them with fixed rules; the texts are the
// model's or the document's own words: only through esc(), never markup. Push 2b: the admin's own kinds (Vorlagen) come
// as further kinds of the sheet; a deadline of the Wissenskarte with a full date ahead gets „Erinnern“ (erinnern).
// The admin part below: which kinds come by themselves (chat.doc_auswertung_auto) and the Vorlagen (PUT).
const AW={doc:'',data:null,seq:0,msg:'',timer:null};
const AW_STAND={wartet:['wartet auf ruhige Minuten','waits for quiet minutes'],leer:['nichts Passendes gefunden','nothing fitting found'],
  x:['ging nicht, später noch einmal','did not work, try again later']};
const awUrl=(doc,x)=>'/api/profile/wissen/'+encodeURIComponent(doc)+'/auswertung'+(x||'');
function awWhere(p){return [p.at?t(p.at,p.at.replace(/^bei /,'at ')):p.page?t('S. ','p. ')+p.page:'',p.part&&p.part!==p.text?p.part:''].filter(Boolean).join(' · ')}
function awState(a){if(a.stand==='ok')return t('fertig','done')+(a.at&&a.modell?' · '+docDate(a.at):'');
  if(a.stand&&AW_STAND[a.stand])return t(...AW_STAND[a.stand]);
  return a.auto?t('entsteht in ruhigen Minuten','made in quiet minutes'):''}
function awPoint(a,p,i,d){const w=awWhere(p),today=docToday();
  const extra=a.art==='fragen'&&p.zitat?`<small>${esc(t('Im Dokument: ','In the document: '))}${esc(p.zitat)}</small>`
    :a.art==='fristen'&&(p.daten||[]).length&&p.daten[0]!==p.text?`<small>${esc(p.daten.join(', '))}</small>`
    :a.art==='fristen'&&p.art==='steckbrief'?`<small>${esc(t('aus dem Steckbrief','from the profile card'))}</small>`:'';
  const due=DOCINFO&&DOCINFO.on.due;
  const remind=a.art==='fristen'&&p.art==='steckbrief'&&due&&docDue(d,today)?
    `<button class="b" type="button" data-docremind="${esc(d.id)}">${esc(t('Erinnern','Remind'))}</button>`
    :a.art==='fristen'&&p.erinnern&&due?`<button class="b" type="button" data-awremind="${i}" title="${esc(t('Erinnerung sechs Wochen vor dem ','Reminder six weeks before ')+docDay(p.erinnern)+t(' (oder am Tag davor)',' (or the day before)'))}">${esc(t('Erinnern','Remind'))}</button>`:'';
  return `<div class="ld-row" data-awi="${i}"><span class="ld-mid"><b>${esc(a.art==='fristen'&&p.art==='steckbrief'?docDay(p.text):p.text)}</b>${extra}</span>`+
    `<span class="ld-right">${w?`<button type="button" class="ld-chip" data-awgo="${esc(String(p.page||''))}"${p.at?` data-awat="${esc(p.at)}"`:''} title="${esc(t('Stelle im Text zeigen','Show the place in the text'))}">${esc(w)}</button>`:''}`+
    remind+(a.modell?`<button type="button" class="b" data-awno="${esc(a.art)}" data-awn="${i}">${esc(t('Stimmt nicht','Not right'))}</button>`:'')+`</span></div>`}
function awKind(a,d){const st=awState(a),can=!a.stand||a.stand==='ok'||a.stand==='leer'||a.stand==='x';
  const btn=a.stand==='wartet'?'':`<button type="button" class="b${a.stand?'':' p'}" data-awmake="${esc(a.art)}">${esc(a.stand?t('Neu erstellen','Make again'):a.modell?t('Erstellen','Make'):t('Zeigen','Show'))}</button>`;
  return `<div class="ld-grp"><span>${esc(t(a.name[0],a.name[1]))}</span><span>${esc(st)}</span></div>`+
    (a.punkte.length?a.punkte.map((p,i)=>awPoint(a,p,i,d)).join(''):'')+
    (can&&(a.stand!=='ok'||a.modell)?`<div class="ld-acts">${btn}</div>`:'')}
function awPaint(d){const box=$('docaw'),D=AW.data;if(!box)return;
  if(!D){box.innerHTML=`<p class="mut ld-note">${esc(AW.msg||t('Lade die Auswertungen …','Loading the analyses …'))}</p>`;return}
  const karte=D.arten.some(a=>(a.art==='fristen'||a.art==='beteiligte')&&a.stand)&&D.karte;
  box.innerHTML=`<h3>${esc(t('Auswertungen','Analyses'))}</h3>`+
    `<p class="mut ld-note">${esc(t('Kurzfassung, Kernaussagen, Fragen und die eigenen Arten des Admins schreibt das Sprachmodell, das Panel prüft jeden Punkt: jede Zahl steht an der genannten Stelle im Dokument. Inhaltsverzeichnis, Fristen und Beteiligte kommen ohne Modell aus dem Dokument und der Wissenskarte.','Summary, key points, questions and the admin\'s own kinds are written by the language model; the panel checks every point: every number stands at the named place in the document. Contents, deadlines and people come without the model from the document and the knowledge map.'))}</p>`+
    D.arten.map(a=>awKind(a,d)).join('')+
    (karte?`<p class="mut ld-note">${esc(D.karte)}</p>`:'')+
    (AW.msg?`<p class="mut ld-note" role="status">${esc(AW.msg)}</p>`:'')}
async function awLoad(d){const seq=++AW.seq;const {r,d:x}=await apiTry(awUrl(d.id));if(seq!==AW.seq||AW.doc!==d.id)return;
  if(r.ok){AW.data=x;AW.msg=''}else{AW.data=null;AW.msg=errSay(r.status,x.detail,'')}
  awPaint(d);clearTimeout(AW.timer);
  // something waits for quiet minutes: look again while the sheet is on screen
  if(AW.data&&AW.data.arten.some(a=>a.stand==='wartet'))AW.timer=setTimeout(()=>{const b=$('docaw');if(b&&!b.hidden&&b.offsetParent!==null&&!document.hidden&&AW.doc===d.id)awLoad(d)},30e3)}
// me.js docDetail calls this with the shown document: only own, read documents, only while the admin released it
window.awShow=d=>{const box=$('docaw');if(!box)return;
  const on=!!(d&&!d.owner&&d.state==='ready'&&DOCINFO&&DOCINFO.auswertung);box.hidden=!on;
  if(!on){AW.doc='';AW.data=null;box.textContent='';clearTimeout(AW.timer);return}
  if(AW.doc!==d.id){AW.doc=d.id;AW.data=null;AW.msg='';awPaint(d);awLoad(d)}};
if($('docaw'))$('docaw').addEventListener('click',async e=>{const d=docFind(AW.doc);if(!d)return;
  const mk=e.target.closest('[data-awmake]');
  if(mk){mk.disabled=true;const {r,d:x}=await apiTry(awUrl(d.id,'/'+encodeURIComponent(mk.dataset.awmake)),xjson('POST',{}));
    AW.msg=r.ok?(x.stand==='wartet'?t('Eingereiht: entsteht in der nächsten ruhigen Minute.','Queued: made in the next quiet minute.'):''):errSay(r.status,x.detail,'');
    await awLoad(d);return}
  const no=e.target.closest('[data-awno]');
  if(no){no.disabled=true;const {r,d:x}=await apiTry(awUrl(d.id,'/'+encodeURIComponent(no.dataset.awno)+'/'+encodeURIComponent(no.dataset.awn)),{method:'DELETE'});
    AW.msg=r.ok?t('Entfernt: dieser Punkt kommt aus diesem Dokument nicht wieder.','Removed: this point does not come back from this document.'):errSay(r.status,x.detail,'');
    await awLoad(d);return}
  const rm=e.target.closest('[data-awremind]');
  if(rm){rm.disabled=true;const {r,d:x}=await apiTry(awUrl(d.id,'/fristen/'+encodeURIComponent(rm.dataset.awremind)+'/erinnern'),xjson('POST',{}));
    AW.msg=r.ok?t('Erinnerung angelegt für ','Reminder set for ')+new Date(x.due).toLocaleString(L==='en'?'en-GB':'de-DE',{dateStyle:'medium',timeStyle:'short'}):errSay(r.status,x.detail,'');
    awPaint(d);return}
  const go=e.target.closest('[data-awgo]');
  if(go){await docView(d.id);const pg=go.dataset.awgo;if(!pg&&!go.dataset.awat)return;
    const at=go.dataset.awat,h=[...document.querySelectorAll('#docview .dvpage')].find(x=>x.textContent===(at||t('Seite ','Page ')+pg));if(h)h.scrollIntoView({block:'start'})}});

// Admin (Funktionen → Eigene Dokumente → Auswertungen): the kinds by themselves fill the hidden list field (saved with
// the other settings); the Vorlagen are saved on their own (PUT /api/admin/auswertung/vorlagen, checked there).
const AWA={d:null,list:[],msg:''};
const awAutoList=()=>{const el=$('chat.doc_auswertung_auto');return el?el.value.split(/[\s,;]+/).filter(Boolean):[]};
function awAutoPaint(){const box=$('awauto'),D=AWA.d;if(!box||!D)return;const on=awAutoList();
  box.innerHTML=D.arten.map(a=>`<button type="button" class="ld-chip${on.includes(a.art)?' on':''}" aria-pressed="${on.includes(a.art)}" data-awauto="${esc(a.art)}">${esc(t(a.name[0],a.name[1]))}</button>`).join('')}
function awVorlPaint(){const box=$('awvorl'),D=AWA.d;if(!box||!D)return;
  box.innerHTML=AWA.list.map((v,i)=>`<div class="ld-row" data-awv="${i}"><span class="ld-mid">`+
    `<input type="text" maxlength="${D.name_len}" data-awf="name_de" value="${esc(v.name_de||'')}" placeholder="${esc(t('Name','Name'))}" aria-label="${esc(t('Name auf Deutsch','Name in German'))}">`+
    `<input type="text" maxlength="${D.name_len}" data-awf="name_en" value="${esc(v.name_en||'')}" placeholder="${esc(t('Name auf Englisch','Name in English'))}" aria-label="${esc(t('Name auf Englisch','Name in English'))}">`+
    `<textarea rows="2" maxlength="${D.auftrag_len}" data-awf="auftrag" placeholder="${esc(t('Auftrag, z. B. die Risiken und Pflichten für den Mieter','Task, e.g. the risks and duties for the tenant'))}" aria-label="${esc(t('Auftrag','Task'))}">${esc(v.auftrag||'')}</textarea>`+
    `<label class="row"><input type="checkbox" data-awf="auto"${v.auto?' checked':''}> ${esc(t('von selbst in ruhigen Minuten','by itself in quiet minutes'))}</label></span>`+
    `<span class="ld-right"><button type="button" class="b" data-awvweg="${i}" aria-label="${esc(t('Vorlage entfernen','Remove template'))}">${ic('trash')}</button></span></div>`).join('')+
    `<div class="ld-acts">${AWA.list.length<D.most?`<button type="button" class="b" data-awvneu="1">${ic('plus')} ${esc(t('Neue Vorlage','New template'))}</button>`:''}`+
    `<button type="button" class="b p" data-awvsave="1">${esc(t('Vorlagen speichern','Save templates'))}</button></div>`+
    (AWA.msg?`<p class="mut ld-note" role="status">${esc(AWA.msg)}</p>`:'')}
async function awAdminLoad(){if(!$('awvorl')||document.body.classList.contains('mgr'))return;
  const {r,d:x}=await apiTry('/api/admin/auswertung');if(!r.ok)return;
  AWA.d=x;AWA.list=x.vorlagen.map(v=>({...v}));awAutoPaint();awVorlPaint()}
function awVorlRead(){document.querySelectorAll('#awvorl [data-awv]').forEach(row=>{const v=AWA.list[+row.dataset.awv];if(!v)return;
  row.querySelectorAll('[data-awf]').forEach(el=>{v[el.dataset.awf]=el.type==='checkbox'?el.checked:el.value})})}
if($('awauto'))$('awauto').addEventListener('click',e=>{const b=e.target.closest('[data-awauto]');if(!b)return;
  const k=b.dataset.awauto,on=awAutoList(),el=$('chat.doc_auswertung_auto');
  el.value=(on.includes(k)?on.filter(x=>x!==k):[...on,k]).join(', ');el.dispatchEvent(new Event('input',{bubbles:true}));awAutoPaint()});
if($('awvorl'))$('awvorl').addEventListener('click',async e=>{
  if(e.target.closest('[data-awvneu]')){awVorlRead();AWA.list.push({name_de:'',name_en:'',auftrag:'',auto:false});AWA.msg='';awVorlPaint();return}
  const w=e.target.closest('[data-awvweg]');if(w){awVorlRead();AWA.list.splice(+w.dataset.awvweg,1);AWA.msg=t('Entfernt; erst mit „Vorlagen speichern“ gilt es.','Removed; it holds once you save the templates.');awVorlPaint();return}
  const sv=e.target.closest('[data-awvsave]');if(!sv)return;awVorlRead();sv.disabled=true;
  const {r,d:x}=await apiTry('/api/admin/auswertung/vorlagen',xjson('PUT',{vorlagen:AWA.list}));
  if(r.ok){AWA.d=x;AWA.list=x.vorlagen.map(v=>({...v}));AWA.msg=t('Gespeichert.','Saved.')}
  else AWA.msg=Array.isArray(x.detail)?x.detail.join(' · '):errSay(r.status,x.detail,'');
  awVorlPaint()});
