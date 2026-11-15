// PDF-Formulare ausfüllen (formular.py, chat.pdf_forms, Dominik 2026-11-15 „1a 2 ja 3a“): a sheet over the page with
// the form's fields, each with what the Spark proposes by its fixed rules and where that came from, a picture of the
// filled page and „Ausgefüllt speichern“ (a new document, the original stays). Signature fields stay for the pen,
// IBAN and ID numbers are typed by the person. After saving: open it, or send it as the answer to the mail it came
// from (or as a new mail) with the filled form attached; the mail goes out only after the usual „Senden“.
let FM_ON=false;
const FM={key:'',d:null,src:null,page:0,timer:0,seq:0,saved:null};
const FM_SRC={profil:['aus deinem Profil','from your profile'],gedaechtnis:['aus deinem Gedächtnis','from your memory'],
  postfach:['dein Postfach','your mailbox'],regel:['heute','today']};
function fmBox(){let m=$('fmsheet');if(m)return m;
  m=document.createElement('div');m.id='fmsheet';m.className='modal fmsheet';m.setAttribute('role','dialog');m.setAttribute('aria-modal','true');
  m.setAttribute('aria-labelledby','fmhead');m.style.display='none';document.body.appendChild(m);
  m.addEventListener('click',e=>{if(e.target===m)fmClose()});
  m.addEventListener('keydown',e=>{if(e.key==='Escape')fmClose()});
  return m}
function fmClose(){const m=$('fmsheet');if(m){m.style.display='none';m.innerHTML=''}clearTimeout(FM.timer);FM.key='';FM.d=null;FM.saved=null}
// src: {doc} (an own document) or {mail, folder, n} (an attachment of an own mail)
async function fmOpen(src){const m=fmBox();FM.src=src;FM.page=0;FM.saved=null;FM.key='';
  m.innerHTML=`<div class="card fmcard"><h2 id="fmhead">${esc(t('Formular','Form'))}</h2><p class="mut">${esc(t('Felder werden gelesen …','Reading the fields …'))}</p></div>`;
  m.style.display='grid';
  const {r,d}=await apiTry('/api/profile/formular/lesen',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(src)});
  if(FM.src!==src)return;
  if(!r.ok){m.innerHTML=`<div class="card fmcard"><h2 id="fmhead">${esc(t('Formular','Form'))}</h2><p class="err">${esc(errSay(r.status,d.detail,''))}</p>`+
    `<div class="row"><button class="b" type="button" data-fm="close">${esc(t('Schließen','Close'))}</button></div></div>`;
    m.querySelector('[data-fm=close]').onclick=fmClose;return}
  FM.key=d.key;FM.d=d;fmDraw()}
function fmValues(){const out={};if(!FM.d)return out;
  for(const f of FM.d.fields){if(f.kind==='sig')continue;out[f.name]=f.kind==='check'?(f.value?'Yes':''):String(f.value||'')}return out}
function fmField(f,i){const lab=`<span class="fmlab">${esc(f.label||f.name)}</span>`;
  if(f.kind==='sig')return `<div class="fmrow fmlock">${lab}<span class="mut">${ic('lock')} ${esc(t('Unterschrift: druck es aus oder unterschreib im PDF-Programm','Signature: print it or sign in your PDF app'))}</span></div>`;
  const chip=f.src?`<span class="ld-chip fmsrc">${esc(t(...(FM_SRC[f.src]||['vom Spark','from the Spark'])))}</span>`:'';
  const hand=f.lock==='hand'?`<small class="mut">${esc(t('Trägst du selbst ein; der Spark füllt so etwas nie aus.','You type this yourself; the Spark never fills such a thing.'))}</small>`:'';
  if(f.kind==='check')return `<label class="fmrow fmchk"><input type="checkbox" data-fi="${i}"${f.value?' checked':''}> ${lab}</label>`;
  if(f.kind==='choice'&&(f.options||[]).length)return `<label class="fmrow">${lab}<select data-fi="${i}"><option value=""></option>${f.options.map(o=>`<option${o===f.value?' selected':''}>${esc(o)}</option>`).join('')}</select>${chip}</label>`;
  return `<label class="fmrow">${lab}<input data-fi="${i}" maxlength="${f.max||500}" value="${esc(f.value||'')}" autocomplete="off">${chip}${hand}</label>`}
function fmDraw(){const m=fmBox(),d=FM.d;if(!d)return;
  const filled=d.fields.filter(f=>f.src).length,pages=d.pages||1;
  m.innerHTML=`<div class="card fmcard fmwide"><div class="fmhead"><h2 id="fmhead">${esc(d.name)}</h2><span class="pgap"></span>`+
    `<button class="pib" type="button" data-fm="close" aria-label="${esc(t('Schließen','Close'))}">${ic('x')}</button></div>`+
    `<p class="mut">${esc(t(`${d.fields.length} Felder · ${filled} vom Spark vorgeschlagen. Prüf alles; gespeichert wird ein neues Dokument, das Original bleibt.`,
      `${d.fields.length} fields · ${filled} proposed by the Spark. Check everything; a new document is saved, the original stays.`))}</p>`+
    `<div class="fmgrid"><div class="fmfields">${d.fields.map(fmField).join('')}</div>`+
    `<div class="fmprev"><img id="fmimg" alt="${esc(t('Vorschau der ausgefüllten Seite','Preview of the filled page'))}">`+
    (pages>1?`<div class="row fmpages"><button class="b" type="button" data-fm="prev">‹</button><span id="fmpage" class="mut"></span><button class="b" type="button" data-fm="next">›</button></div>`:'')+`</div></div>`+
    `<div class="row fmacts" id="fmacts"></div><div id="fmmsg" class="fh"></div></div>`;
  m.querySelector('[data-fm=close]').onclick=fmClose;
  m.querySelectorAll('[data-fi]').forEach(x=>{const f=d.fields[+x.dataset.fi];
    const set=()=>{f.value=x.type==='checkbox'?x.checked:x.value;f.src='';fmSoon()};x.oninput=set;x.onchange=set});
  const pv=m.querySelector('[data-fm=prev]'),nx=m.querySelector('[data-fm=next]');
  if(pv)pv.onclick=()=>{FM.page=Math.max(0,FM.page-1);fmPreview()};
  if(nx)nx.onclick=()=>{FM.page=Math.min(pages-1,FM.page+1);fmPreview()};
  fmActs();fmPreview()}
function fmSoon(){clearTimeout(FM.timer);FM.timer=setTimeout(fmPreview,700);if(FM.saved){FM.saved=null;fmActs()}}
async function fmPreview(){const img=$('fmimg');if(!img||!FM.key)return;const seq=++FM.seq;
  const pg=$('fmpage');if(pg)pg.textContent=t(`Seite ${FM.page+1} von ${FM.d.pages}`,`Page ${FM.page+1} of ${FM.d.pages}`);
  try{const r=await api('/api/profile/formular/vorschau',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({key:FM.key,values:fmValues(),page:FM.page})});
    const b=await r.blob();if(seq!==FM.seq)return;const old=img.src;img.src=URL.createObjectURL(b);if(old&&old.startsWith('blob:'))URL.revokeObjectURL(old)}
  catch(e){if(seq===FM.seq)fmSay(e.message,true)}}
function fmSay(text,err){const m=$('fmmsg');if(m){m.className=err?'err':'fh';m.textContent=text}}
function fmActs(){const box=$('fmacts');if(!box)return;const s=FM.saved;
  if(!s){box.innerHTML=`<button class="b p" type="button" data-fm="save">${ic('doc')} ${esc(t('Ausgefüllt speichern','Save filled in'))}</button>`;
    box.querySelector('[data-fm=save]').onclick=e=>fmSave(e.currentTarget);return}
  const mailOk=typeof postWrite==='function'&&typeof SEND_ON!=='undefined'&&SEND_ON,answer=mailOk&&FM.src&&FM.src.mail;
  box.innerHTML=(s.kept?`<a class="b" href="/api/profile/wissen/${encodeURIComponent(s.doc)}/file?view=1" target="_blank" rel="noopener">${esc(t('PDF öffnen','Open PDF'))}</a>`:'')+
    (mailOk&&s.kept?`<button class="b p" type="button" data-fm="mail">${ic('clip')} ${esc(answer?t('Als Antwort …','As an answer …'):t('Als Mail senden …','Send as mail …'))}</button>`:'')+
    `<button class="b" type="button" data-fm="done">${esc(t('Fertig','Done'))}</button>`;
  box.querySelector('[data-fm=done]').onclick=fmClose;
  const ml=box.querySelector('[data-fm=mail]');if(ml)ml.onclick=()=>fmMail(s,answer)}
async function fmSave(b){b.disabled=true;fmSay(t('Speichere …','Saving …'));
  const {r,d}=await apiTry('/api/profile/formular/speichern',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({key:FM.key,values:fmValues()})});
  if(!r.ok){b.disabled=false;fmSay(errSay(r.status,d.detail,''),true);return}
  FM.saved=d;fmActs();
  fmSay(t(`Gespeichert als „${d.name}“: ${d.filled} Felder ausgefüllt`+(d.open?`, ${d.open} leer`:'')+'. Du findest es unter Ich → Dokumente.',
    `Saved as "${d.name}": ${d.filled} fields filled`+(d.open?`, ${d.open} empty`:'')+'. You find it under Me → Documents.'));
  if(typeof showDocs==='function'&&DOCS_ON)showDocs()}
// the mail with the filled form attached: an answer to the mail the form came from, or a new one; the page E-Mail
// shows it like every draft, it goes out only with „Senden“ (senden.py, body "doc")
async function fmMail(s,answer){const doc=s.doc,name=s.name;fmClose();
  if(typeof icTabSet==='function')icTabSet('post','show');goSec('post');
  if(answer&&POST.msg&&POST.sel===FM_LAST_MAIL)await postWrite(POST.msg);else await postWrite(null);
  if(POST.write){POST.write.doc=doc;POST.write.docName=name;postDraw()}}
let FM_LAST_MAIL='';
// the button on a PDF attachment of the open mail (post.js) and on an own PDF document (me.js)
document.addEventListener('click',e=>{const b=e.target.closest&&e.target.closest('[data-fmdoc],[data-fmmail]');if(!b||!FM_ON)return;
  e.preventDefault();
  if(b.dataset.fmdoc)fmOpen({doc:b.dataset.fmdoc});
  else{FM_LAST_MAIL=b.dataset.fmmail;fmOpen({mail:b.dataset.fmmail,folder:b.dataset.folder||'INBOX',n:+b.dataset.n})}});
