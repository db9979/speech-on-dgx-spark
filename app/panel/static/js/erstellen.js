// Dokumente erstellen (docmake.py, plan dokumente-erstellen): the card under an answer with the outline the
// assistant proposes, its progress while the Spark writes in the background, and "Vom Spark erstellt" under
// Ich → Dokumente (preview, versions, change per part, download, send, sender lines, own templates).
// Nothing here writes a file: the card only sends the outline and "start"; the panel checks everything again.
// Every text shown comes from the model or the person, so it is set with esc() or textContent only.
let MK=null;   // the last /api/make: kinds, styles, formats, templates, docs, jobs, plan, targets
const MKFMT={docx:'Word',pptx:'PowerPoint',xlsx:'Excel',pdf:'PDF',md:'Markdown',txt:'Text',csv:'CSV'};
const MKTO={pc:['An den PC','To the PC'],rm:['An den reMarkable','To the reMarkable'],tg:['In Telegram','In Telegram'],mail:['Als Mail-Entwurf','As mail draft'],box:['Ins Postfach ablegen','File into the mailbox']};
// the Android app hands a download to the phone's browser, which has no login: there a download link (10 minutes)
const MKAND=/SparkAndroid\//.test(navigator.userAgent);
// the small preview of the first slide, page or sheet (docmake.peek: a few short lines, set with esc() only)
const MKSTY=['schlicht','spark-hell','spark-dunkel','frisch','warm','brief'];
function mkPeek(p,kind,style){if(!p)return'';const sl=kind==='praesentation',st=MKSTY.includes(style)?style:'schlicht';
  return `<div class="mkpeek ${sl?'slide':'page'} st-${st}" role="img" aria-label="${esc(t('Vorschau: ','Preview: ')+(p.heading||''))}"><b>${esc(p.heading||'')}</b>
    ${(p.rows||[]).length?`<table>${p.rows.map(r=>`<tr>${r.map(x=>`<td>${esc(x)}</td>`).join('')}</tr>`).join('')}</table>`:''}
    ${(p.lines||[]).length?(sl?`<ul>${p.lines.map(x=>`<li>${esc(x)}</li>`).join('')}</ul>`:p.lines.map(x=>`<p>${esc(x)}</p>`).join('')):''}
    ${p.chart?`<i class="mkpch"></i>`:''}${p.parts>1?`<small>${esc(t(`1 von ${p.parts}`,`1 of ${p.parts}`))}</small>`:''}</div>`}
const mkFile=(id,fmt,v)=>'/api/make/doc/'+encodeURIComponent(id)+'/file'+(fmt||v?'?'+[fmt?'fmt='+encodeURIComponent(fmt):'',v?'v='+v:''].filter(Boolean).join('&'):'');
const mkDl=(id,label,fmt,v,cls)=>`<a class="b${cls?' '+cls:''}" data-mkdl="${esc(id)}" data-fmt="${esc(fmt||'')}" data-v="${v||''}" href="${mkFile(id,fmt,v)}">${esc(label)}</a>`;
async function mkLink(id,fmt,v){const b={};if(fmt)b.fmt=fmt;if(v)b.v=+v;
  const r=await apiTry('/api/make/doc/'+encodeURIComponent(id)+'/link',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(b)});
  if(!r.r.ok)throw new Error(String(r.d.detail||t('Ging nicht.','Did not work.')));return new URL(r.d.url,location.href).href}
document.addEventListener('click',async e=>{const a=e.target.closest('a[data-mkdl]');if(!a||!MKAND)return;e.preventDefault();
  try{location.href=await mkLink(a.dataset.mkdl,a.dataset.fmt,a.dataset.v)}catch(err){alert(err.message)}});
// sending from the card in the chat and from the preview: the same request
async function mkSendNow(id,to,fmt,mailTo){const b={to};if(fmt)b.fmt=fmt;if(mailTo)b.mail_to=mailTo;
  const r=await apiTry('/api/make/doc/'+encodeURIComponent(id)+'/send',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(b)});
  return {ok:r.r.ok,text:String(r.r.ok?r.d.message:(r.d.detail||t('Ging nicht.','Did not work.'))).slice(0,300)}}
const MKSTATE={wait:['wartet','waiting'],run:['schreibt','writing'],done:['fertig','done'],error:['ging nicht','failed']};
async function mkInfo(){const r=await apiTry('/api/make');MK=r.r.ok?r.d:null;return MK}
const mkWhen=s=>s?new Date(s*1000).toLocaleString(L==='en'?'en-GB':'de-DE',{dateStyle:'short',timeStyle:'short'}):'';
const mkOpts=(list,sel)=>list.map(([v,n])=>`<option value="${esc(v)}"${v===sel?' selected':''}>${esc(n)}</option>`).join('');
const mkStyles=()=>(MK&&MK.styles||[]).map(s=>[s.id,s.name]).concat((MK&&MK.templates||[]).map(x=>[x.id,t('Vorlage: ','Template: ')+x.name]));
const mkBar=(step,steps)=>`<span class="qbar docbar" role="progressbar" aria-valuemin="0" aria-valuemax="100" aria-valuenow="${steps?Math.round(100*step/steps):0}"><i style="width:${steps?Math.round(100*step/steps):0}%"></i></span>`;
const mkJobLine=j=>`${esc(t(...(MKSTATE[j.state]||MKSTATE.wait)))}${j.state==='run'||j.state==='wait'?' · '+esc(t(`Teil ${j.step} von ${j.steps}`,`part ${j.step} of ${j.steps}`)):''}${j.error?' · '+esc(j.error):''}`;
// follows one job until it ends; tick(job) on every look, stops when the element left the page
function mkFollow(jid,el,tick){const look=async()=>{if(!el.isConnected)return;const r=await apiTry('/api/make/job/'+encodeURIComponent(jid));
    if(!r.r.ok){tick({state:'error',error:String(r.d.detail||'').slice(0,200),step:0,steps:0});return}
    tick(r.d);if(r.d.state==='wait'||r.d.state==='run')setTimeout(look,3000)};look()}

// ---------------------------------------------------------------- the card in the chat (SSE "docmake")
function mkCard(c){const d=document.createElement('div');d.className='hcard mkcard';d.dataset.plan=c.id;
  const secs=(c.sections||[]).map(s=>({heading:s.heading,note:s.note||'',pictures:s.pictures}));let started=false,watch=0;
  const draw=()=>{const fm=(c.formats||[c.format]).map(f=>[f,MKFMT[f]||f]),st=mkStyles().length?mkStyles():[[c.style,c.style]];
    d.innerHTML=`<h4>${esc(c.kind_name||t('Dokument','Document'))}</h4>
      <label class="mklbl">${esc(t('Titel','Title'))}<input class="mktitle" maxlength="200" value="${esc(c.title||'')}"></label>
      <ol class="mksecs">${secs.map((s,i)=>`<li><input data-mksec="${i}" maxlength="200" value="${esc(s.heading)}" aria-label="${esc(t('Teil ','Part ')+(i+1))}">${secs.length>1?`<button type="button" class="mlink" data-mkrm="${i}" aria-label="${esc(t('Teil weglassen','Remove part'))}">✕</button>`:''}</li>`).join('')}</ol>
      ${c.kind!=='brief'&&secs.length<((MK&&MK.limits&&MK.limits.sections)||30)?`<button type="button" class="mlink" data-mkdo="add">+ ${esc(t('Teil','Part'))}</button>`:''}
      <div class="mkpick"><label>${esc(t('Format','Format'))}<select data-mk="format">${mkOpts(fm,c.format)}</select></label>
        <label>${esc(t('Aussehen','Look'))}<select data-mk="style">${mkOpts(st,c.template||c.style)}</select></label></div>
      ${(c.documents||[]).length?`<div class="hwhy">${esc(t('Aus deinen Dokumenten: ','From your documents: ')+c.documents.join(', '))}</div>`:''}
      <div class="hwhy">${esc(t('Noch ist nichts geschrieben. „Ja“ im Gespräch oder der Knopf startet es; der Spark schreibt im Hintergrund und sagt Bescheid.','Nothing is written yet. "Yes" in the conversation or the button starts it; the Spark writes in the background and tells you.'))}</div>
      <div class="row"><button type="button" class="b p" data-mkdo="go">${esc(t('Passt, erstellen','Looks good, create'))}</button><button type="button" class="b" data-mkdo="drop">${esc(t('Verwerfen','Discard'))}</button></div>
      <div class="hmsg mut" role="status"></div>`};
  const msg=()=>d.querySelector('.hmsg');
  const body=()=>{const sel=d.querySelector('[data-mk=style]').value,own=(MK&&MK.templates||[]).some(x=>x.id===sel);
    return {title:d.querySelector('.mktitle').value,format:d.querySelector('[data-mk=format]').value,style:own?c.style:sel,template:own?sel:'',
      sections:secs.map(s=>({heading:s.heading,note:s.note,pictures:s.pictures}))}};
  // the job runs: the outline becomes a progress line, then the result with download and "Ansehen"
  const follow=jid=>{if(started)return;started=true;clearTimeout(watch);
    d.innerHTML=`<h4>${esc((c.kind_name||'')+' „'+(c.title||'')+'“')}</h4><div class="mkjob mut" role="status"></div><div class="mkpv"></div><div class="row mkdone"></div><div class="mksend"></div><div class="hmsg mut" role="status"></div>`;
    const line=d.querySelector('.mkjob'),row=d.querySelector('.mkdone');
    mkFollow(jid,d,j=>{line.innerHTML=mkJobLine(j)+(j.state==='run'||j.state==='wait'?mkBar(j.step,j.steps):'');
      if(j.state==='run'||j.state==='wait')row.innerHTML=`<button type="button" class="b" data-mkdo="cancel" data-job="${esc(jid)}">${esc(t('Abbrechen','Cancel'))}</button>`;
      else if(j.state==='done'&&j.doc){line.textContent='';row.innerHTML=mkDl(j.doc,t('Herunterladen','Download')+' ('+(MKFMT[j.format]||j.format||'')+')','','','p')+`<button type="button" class="b" data-mkdo="show" data-doc="${esc(j.doc)}">${esc(t('Ansehen und ändern','View and change'))}</button>`;
        mkInfo().then(M=>{if(!M||!d.isConnected)return;const x=(M.docs||[]).find(y=>y.id===j.doc);if(x)d.querySelector('.mkpv').innerHTML=mkPeek(x.peek,x.kind,x.style);
          const tg=(M.targets||[]).map(k=>[k,t(...MKTO[k])]),sn=d.querySelector('.mksend');
          if(tg.length)sn.innerHTML=`<div class="mkpick"><label>${esc(t('Schicken','Send'))}<select data-mk="cto">${mkOpts(tg,(M.deliver&&tg.some(z=>z[0]===M.deliver))?'':tg[0][0])}</select></label><button type="button" class="b" data-mkdo="csend" data-doc="${esc(j.doc)}">${esc(t('Schicken','Send'))}</button></div>`;
          else if(M.mail_hint)sn.innerHTML=`<div class="hwhy">${esc(t(M.mail_hint,'By mail: under Me → Email → Tidy up the mailbox, switch on "Allow reply drafts" for the mailbox (nothing is ever sent).'))}</div>`;
          if(M.deliver)msg().textContent=t('Wird auch automatisch zugestellt: ','Also delivered on its own: ')+t(...MKTO[M.deliver])})}
      else row.textContent=''})};
  // "Ja" said in the conversation starts it on the panel: look now and then whether this outline started
  const look=async()=>{if(!d.isConnected||started)return;const r=await apiTry('/api/make');if(r.r.ok){MK=r.d;const p=r.d.plan;
      if(p&&p.id===c.id&&p.state==='started'&&p.job){follow(p.job);return}
      if(!p||p.id!==c.id){d.querySelectorAll('.row button,select,input').forEach(x=>x.disabled=true);msg().textContent=t('Diese Gliederung ist nicht mehr offen.','This outline is no longer open.');return}}
    watch=setTimeout(look,5000)};
  d.addEventListener('input',e=>{const i=e.target.dataset.mksec;if(i!==undefined&&secs[+i])secs[+i].heading=e.target.value});
  d.addEventListener('click',async e=>{const rm=e.target.closest('[data-mkrm]');if(rm){secs.splice(+rm.dataset.mkrm,1);const b=body();draw();restore(b);return}
    const b=e.target.closest('[data-mkdo]');if(!b||b.disabled)return;const what=b.dataset.mkdo;
    if(what==='add'){const k=body();secs.push({heading:t('Neuer Teil','New part'),note:''});draw();restore(k);const l=d.querySelector(`[data-mksec="${secs.length-1}"]`);if(l){l.focus();l.select()}return}
    if(what==='show'){MKOPEN={id:b.dataset.doc,v:0};if(typeof openMe==='function')openMe('docbox');return}
    if(what==='csend'){b.disabled=true;const r=await mkSendNow(b.dataset.doc,d.querySelector('[data-mk=cto]').value);b.disabled=false;msg().className='hmsg '+(r.ok?'mut':'err');msg().textContent=r.text;return}
    if(what==='cancel'){b.disabled=true;await apiTry('/api/make/job/'+encodeURIComponent(b.dataset.job)+'/cancel',{method:'POST'});return}
    if(what==='drop'){b.disabled=true;await apiTry('/api/make/plan/'+encodeURIComponent(c.id),{method:'DELETE'});clearTimeout(watch);
      d.querySelectorAll('.row button,select,input').forEach(x=>x.disabled=true);msg().textContent=t('Verworfen, nichts erstellt.','Discarded, nothing made.');return}
    if(what==='go'){b.disabled=true;msg().textContent='';
      const r=await apiTry('/api/make/plan/'+encodeURIComponent(c.id),{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(Object.assign(body(),{start:true}))});
      b.disabled=false;if(!r.r.ok){msg().textContent=String(r.d.detail||t('Ging nicht.','Did not work.')).slice(0,300);return}
      if(r.d.job)follow(r.d.job)}});
  // a redraw keeps what was typed and picked
  const restore=k=>{d.querySelector('.mktitle').value=k.title;const f=d.querySelector('[data-mk=format]');if([...f.options].some(o=>o.value===k.format))f.value=k.format;
    d.querySelector('[data-mk=style]').value=k.template||k.style};
  draw();(MK?Promise.resolve(MK):mkInfo()).then(()=>{if(!started){const k=body();draw();restore(k)}});watch=setTimeout(look,4000);
  return d}

// ---------------------------------------------------------------- Ich → Dokumente: "Vom Spark erstellt"
let mkTimer=null,MKOPEN=null;
async function mkShow(I){const box=$('mkbox');if(!box)return;clearTimeout(mkTimer);
  if(!(I&&I.allow&&I.allow.make)){box.hidden=true;box.textContent='';return}
  // allowed but off for this profile: say so right here, with the switch (the same as under "Einstellungen für Dokumente")
  if(!(I.on&&I.on.make)){box.hidden=false;
    box.innerHTML=`<h3>${esc(t('Vom Spark erstellt','Made by the Spark'))}</h3><div class="mkjob"><span class="mut">${esc(t('Aus. Eingeschaltet schreibt der Spark auf Bitte Briefe, Präsentationen und Tabellen als Datei.','Off. Switched on, the Spark writes letters, presentations and spreadsheets as files on request.'))}</span><button type="button" class="b p" data-mkdo="on">${esc(t('Einschalten','Switch on'))}</button></div><div id="mkmsg" class="mut" role="status"></div>`;return}
  const M=await mkInfo();if(!M){box.hidden=true;return}box.hidden=false;
  const jobs=(M.jobs||[]).filter(j=>j.state==='wait'||j.state==='run'||j.state==='error');
  const sty=Object.fromEntries((M.styles||[]).map(s=>[s.id,s.name])),kn=k=>(M.kinds[k]||{}).name||k;
  box.innerHTML=`<h3>${esc(t('Vom Spark erstellt','Made by the Spark'))}</h3>
    <div class="mut">${esc(t('An (Schalter unter „Einstellungen für Dokumente“). ','On (switch under "Settings for documents"). '))}${esc(t('Sag zum Beispiel „Schreib mir einen Brief an die Hausverwaltung“ oder „Mach eine Präsentation über unseren Urlaub“.','Say for example "Write me a letter to the landlord" or "Make a presentation about our holiday".'))}</div>
    ${M.plan&&M.plan.state==='new'?`<div class="mkjob">${esc(t(`Gliederung „${M.plan.title}“ wartet im Gespräch auf dein Ja.`,`Outline "${M.plan.title}" waits for your yes in the conversation.`))}</div>`:''}
    ${jobs.map(j=>`<div class="mkjob"><span>${esc(kn(j.kind)+' „'+j.title+'“')} · ${mkJobLine(j)}${j.state!=='error'?mkBar(j.step,j.steps):''}</span>${j.state!=='error'?`<button type="button" class="b" data-mkcancel="${esc(j.id)}">${esc(t('Abbrechen','Cancel'))}</button>`:''}</div>`).join('')}
    <ul class="facts" id="mklist">${(M.docs||[]).map(d=>`<li><span>${esc(d.title)}<br><small class="mut">${esc(kn(d.kind))} · ${esc(MKFMT[d.format]||d.format)} · ${esc(t('Version ','version ')+d.version)} · ${esc(mkWhen(d.updated))}${d.template?'':' · '+esc(sty[d.style]||'')}</small></span>
      <button type="button" class="b" data-mkopen="${esc(d.id)}">${esc(t('Ansehen','View'))}</button>${mkDl(d.id,t('Herunterladen','Download'))}<button type="button" class="b" data-mkdel="${esc(d.id)}" data-name="${esc(d.title)}">${esc(t('Löschen','Delete'))}</button></li>`).join('')||`<li class="mut">${esc(t('Noch nichts erstellt.','Nothing made yet.'))}</li>`}</ul>
    <div id="mkview" class="docview mkview" hidden></div>
    <div class="mkpick"><label>${esc(t('Fertige Dokumente zusätzlich','Finished documents also'))}<select data-mkdeliver>${mkOpts([['',t('nur hier','only here')]].concat((M.targets||[]).map(k=>[k,t(...MKTO[k])])),M.deliver||'')}</select></label></div>
    ${M.mail_hint?`<div class="fh">${esc(t(M.mail_hint,'By mail: under Me → Email → Tidy up the mailbox, switch on "Allow reply drafts" for the mailbox (nothing is ever sent).'))}</div>`:''}
    <details class="mkmore"><summary>${esc(t('Absender für Briefe','Sender for letters'))}</summary><textarea id="mksender" rows="4" maxlength="300" placeholder="${esc(t('Name\nStraße 1\n12345 Ort','Name\nStreet 1\nTown'))}">${esc(M.sender||'')}</textarea>
      <div class="row"><button type="button" class="b" data-mkdo="sender">${esc(t('Speichern','Save'))}</button></div></details>
    ${M.templates_on?`<details class="mkmore"><summary>${esc(t('Eigene Vorlagen','Own templates'))} (${(M.templates||[]).length})</summary><ul class="facts">${(M.templates||[]).map(x=>`<li><span>${esc(x.name)} <small class="mut">${esc(x.ext==='pptx'?'PowerPoint':'Word')}</small></span><button type="button" class="b" data-mktdel="${esc(x.id)}">${esc(t('Löschen','Delete'))}</button></li>`).join('')}</ul>
      <div class="row"><button type="button" class="b" data-mkdo="tadd">${esc(t('Vorlage hochladen …','Upload template …'))}</button><input type="file" id="mktfile" accept=".docx,.dotx,.pptx,.potx" hidden></div>
      <div class="fh">${esc(t('Word oder PowerPoint ohne Makros, höchstens 10 MB. Der Spark übernimmt Schriften, Farben und Layouts.','Word or PowerPoint without macros, at most 10 MB. The Spark takes fonts, colours and layouts.'))}</div></details>`:''}
    <div id="mkmsg" class="mut" role="status"></div>`;
  if(MKOPEN&&(M.docs||[]).some(d=>d.id===MKOPEN.id))mkOpen(MKOPEN.id,MKOPEN.v);
  if(jobs.some(j=>j.state!=='error'))mkTimer=setTimeout(()=>{if(box.offsetParent!==null&&!document.hidden)mkShow(I);else mkTimer=setTimeout(()=>mkShow(I),10e3)},4000)}
const mkSay=(x,err)=>{const m=$('mkmsg');if(m){m.className=err?'err':'mut';m.textContent=String(x||'').slice(0,300)}};
const mkJSON=(p,method,b)=>apiTry(p,{method,headers:{'Content-Type':'application/json'},body:JSON.stringify(b||{})});
// one document: preview of the stored content (the same JSON the file is built from), versions, changes, sending
async function mkOpen(id,v){MKOPEN={id,v:v||0};const box=$('mkview');if(!box)return;box.hidden=false;
  const r=await apiTry('/api/make/doc/'+encodeURIComponent(id)+(v?'?v='+v:''));if(!r.r.ok){box.textContent=String(r.d.detail||'');return}
  const d=r.d,c=d.content||{},last=d.history.length?d.history[d.history.length-1].n:d.v,old=d.v!==last,M=MK||{};
  const fm=(d.formats||[d.format]).map(f=>[f,MKFMT[f]||f]),tg=(M.targets||[]).map(x=>[x,t(...MKTO[x])]);
  const sec=(s,i)=>`<div class="mksec" data-i="${i+1}"><div class="dvhead"><b>${esc((i+1)+'. '+(s.heading||''))}</b>${old?'':`<span><button type="button" class="mlink" data-mkedit="${i+1}">${esc(t('Bearbeiten','Edit'))}</button> <button type="button" class="mlink" data-mkre="${i+1}">${esc(t('Neu schreiben','Rewrite'))}</button>${(c.sections||[]).length>1?` <button type="button" class="mlink" data-mkdrop="${i+1}">${esc(t('Weglassen','Leave out'))}</button>`:''}</span>`}</div>
    ${(s.paras||[]).map(p=>`<p>${esc(p)}</p>`).join('')}${(s.bullets||[]).length?`<ul>${s.bullets.map(b=>`<li>${esc(b)}</li>`).join('')}</ul>`:''}
    ${s.table?`<div class="mktbl"><table>${(s.table.head||[]).length?`<tr>${s.table.head.map(h=>`<th>${esc(h)}</th>`).join('')}</tr>`:''}${(s.table.rows||[]).slice(0,30).map(r=>`<tr>${r.map(x=>`<td>${esc(x)}</td>`).join('')}</tr>`).join('')}</table>${(s.table.rows||[]).length>30?`<small class="mut">${esc(t(`… und ${s.table.rows.length-30} weitere Zeilen in der Datei`,`… and ${s.table.rows.length-30} more rows in the file`))}</small>`:''}</div>`:''}
    ${s.chart?`<div class="mut">📊 ${esc(t('Diagramm','Chart'))}: ${esc(s.chart.title||'')} (${esc(s.chart.labels.length+' '+t('Werte','values'))})</div>`:''}
    ${(s.pictures||[]).length?`<div class="mut">🖼 ${esc(t(`${s.pictures.length} Bild(er)`,`${s.pictures.length} picture(s)`))}</div>`:''}
    ${s.notes?`<small class="mut">${esc(t('Notizen: ','Notes: ')+s.notes)}</small>`:''}<div class="mkedit"></div></div>`;
  const L_=c.letter;
  box.innerHTML=`<div class="dvhead"><b>${esc(d.title)}</b><span><button type="button" class="b" data-mkdo="close">✕</button></span></div>
    <div class="mkpick"><label>${esc(t('Version','Version'))}<select data-mk="ver">${mkOpts(d.history.slice().reverse().map(h=>[String(h.n),h.n+' · '+mkWhen(h.t)+(h.note?' · '+h.note:'')]),String(d.v))}</select></label>
      ${old?`<button type="button" class="b" data-mkdo="restore" data-v="${d.v}">${esc(t('Diese Version zurückholen','Bring back this version'))}</button>`:''}</div>
    <div class="mkpick"><label>${esc(t('Datei als','File as'))}<select data-mk="fmt">${mkOpts(fm,d.format)}</select></label><a class="b p" data-mk="dl" data-mkdl="${esc(id)}" data-fmt="${esc(d.format)}" data-v="${old?d.v:''}" href="${mkFile(id,d.format,old?d.v:0)}">${esc(t('Herunterladen','Download'))}</a><button type="button" class="b" data-mkdo="link">${esc(t('Link kopieren','Copy link'))}</button>
      ${old?'':`<button type="button" class="b" data-mkdo="conv">${esc(t('Dauerhaft umstellen','Switch for good'))}</button>`}</div>
    ${old?'':`<div class="mkpick"><label>${esc(t('Aussehen','Look'))}<select data-mk="sty">${mkOpts(mkStyles(),d.template||d.style)}</select></label><button type="button" class="b" data-mkdo="sty">${esc(t('Übernehmen','Apply'))}</button></div>`}
    ${tg.length&&!old?`<div class="mkpick"><label>${esc(t('Schicken','Send'))}<select data-mk="to">${mkOpts(tg,tg[0][0])}</select></label><input data-mk="mailto" type="email" maxlength="200" placeholder="${esc(t('an (leer: an dich)','to (empty: to you)'))}" aria-label="${esc(t('Empfänger des Entwurfs','Recipient of the draft'))}" hidden><button type="button" class="b" data-mkdo="send">${esc(t('Schicken','Send'))}</button></div>`:''}
    ${L_?`<div class="mksec" data-i="1">${old?'':`<div class="dvhead"><b>${esc(t('Brief','Letter'))}</b><span><button type="button" class="mlink" data-mkedit="1">${esc(t('Bearbeiten','Edit'))}</button> <button type="button" class="mlink" data-mkre="1">${esc(t('Neu schreiben','Rewrite'))}</button></span></div>`}<small class="mut">${esc((L_.sender||[]).join(', '))}</small><p>${esc((L_.recipient||[]).join('\n'))}</p><p class="mut">${esc(L_.place_date||'')}</p><p><b>${esc(L_.subject||'')}</b></p><p>${esc(L_.greeting||'')}</p>${(L_.paras||[]).map(p=>`<p>${esc(p)}</p>`).join('')}<p>${esc(L_.closing||'')}<br>${esc(L_.signature||'')}</p><div class="mkedit"></div></div>`:''}
    ${(c.sections||[]).length&&!(L_&&d.kind==='brief')?(c.sections||[]).map(sec).join(''):''}
    ${old||d.kind==='brief'||(c.sections||[]).length>=30?'':`<div class="row"><button type="button" class="mlink" data-mkdo="new">+ ${esc(t('Teil dazuschreiben lassen','Have a part added'))}</button></div>`}
    <div class="mkedit mknew"></div>
    ${d.sent&&d.sent.length?`<small class="mut">${esc(t('Geschickt: ','Sent: ')+d.sent.slice(-3).map(x=>t(...MKTO[x.to]||[x.to,x.to])+' '+mkWhen(x.t)).join(', '))}</small>`:''}
    <div class="mkvmsg mut" role="status"></div>`;
  box.dataset.doc=id;box.dataset.v=d.v;box._doc=d;
  const to=box.querySelector('[data-mk=to]');if(to){const mt=box.querySelector('[data-mk=mailto]');to.onchange=()=>{mt.hidden=to.value!=='mail'};mt.hidden=to.value!=='mail'}
  box.scrollIntoView({block:'nearest'})}
const mkVSay=(x,err)=>{const m=document.querySelector('#mkview .mkvmsg');if(m){m.className='mkvmsg '+(err?'err':'mut');m.textContent=String(x||'').slice(0,300)}};
// a part in plain text: paragraphs separated by an empty line, bullets with "- "
const mkPlain=s=>(s.paras||[]).join('\n\n')+((s.bullets||[]).length?(s.paras&&s.paras.length?'\n\n':'')+s.bullets.map(b=>'- '+b).join('\n'):'');
function mkParse(txt,s){const out=Object.assign({},s,{paras:[],bullets:[]});
  for(const blk of txt.split(/\n\s*\n/)){const lines=blk.split('\n').map(x=>x.trim()).filter(Boolean);if(!lines.length)continue;
    if(lines.every(x=>/^[-•*]\s+/.test(x)))out.bullets.push(...lines.map(x=>x.replace(/^[-•*]\s+/,'')));else out.paras.push(lines.join('\n'))}
  return out}
// a running change (rewrite or a new part): follow it in the open preview, then show the new version
function mkWait(jid){const box=$('mkview');mkFollow(jid,box,j=>{mkVSay(mkJobLine(j));if(j.state==='done'){MKOPEN={id:box.dataset.doc,v:0};mkShow(DOCINFO)}})}
{const box=document.body;
 box.addEventListener('change',e=>{const s=e.target.closest('#mkview [data-mk]');if(!s)return;const v=$('mkview');
   if(s.dataset.mk==='ver'){mkOpen(v.dataset.doc,+s.value);return}
   if(s.dataset.mk==='fmt'){const a=v.querySelector('[data-mk=dl]'),old=+v.dataset.v!==(v._doc.history.slice(-1)[0]||{}).n;
     a.href=mkFile(v.dataset.doc,s.value,old?v.dataset.v:0);a.dataset.fmt=s.value}});
 box.addEventListener('change',async e=>{const s=e.target.closest('#mkbox [data-mkdeliver]');if(!s)return;
   const r=await mkJSON('/api/profile/settings','PUT',{doc_deliver:s.value});mkSay(r.r.ok?(s.value?t('Fertige Dokumente gehen jetzt auch dorthin.','Finished documents now also go there.'):t('Fertige Dokumente bleiben nur hier.','Finished documents stay only here.')):r.d.detail,!r.r.ok);if(r.r.ok&&MK)MK.deliver=s.value});
 box.addEventListener('click',async e=>{if(!e.target.closest('#mkbox'))return;
   const v=$('mkview'),id=v&&v.dataset.doc,el=e.target.closest('[data-mkopen],[data-mkdel],[data-mkcancel],[data-mktdel],[data-mkdo],[data-mkedit],[data-mkre],[data-mkdrop]');if(!el||el.disabled)return;
   const D=el.dataset;
   if(D.mkopen){mkOpen(D.mkopen);return}
   if(D.mkcancel){el.disabled=true;await apiTry('/api/make/job/'+encodeURIComponent(D.mkcancel)+'/cancel',{method:'POST'});mkShow(DOCINFO);return}
   if(D.mkdel){if(!confirm(t(`„${D.name}“ mit allen Versionen löschen?`,`Delete "${D.name}" with all versions?`)))return;
     const r=await apiTry('/api/make/doc/'+encodeURIComponent(D.mkdel),{method:'DELETE'});if(!r.r.ok){mkSay(r.d.detail,true);return}
     if(MKOPEN&&MKOPEN.id===D.mkdel)MKOPEN=null;showDocs();return}
   if(D.mktdel){const r=await apiTry('/api/make/templates/'+encodeURIComponent(D.mktdel),{method:'DELETE'});if(!r.r.ok)mkSay(r.d.detail,true);else mkShow(DOCINFO);return}
   const doc=v&&v._doc,ed=i=>v.querySelector(`.mksec[data-i="${i}"] .mkedit`);
   if(D.mkedit&&doc.content.letter&&doc.kind==='brief'){const L_=doc.content.letter;
     ed(1).innerHTML=`<label>${esc(t('Betreff','Subject'))}<input data-mkls maxlength="200" value="${esc(L_.subject||'')}"></label><textarea data-mkt rows="10" maxlength="20000">${esc((L_.paras||[]).join('\n\n'))}</textarea>
       <div class="fh">${esc(t('Absätze mit einer Leerzeile trennen.','Separate paragraphs by an empty line.'))}</div>
       <div class="row"><button type="button" class="b p" data-mkdo="lsave">${esc(t('Speichern','Save'))}</button><button type="button" class="b" data-mkdo="x" data-i="1">${esc(t('Abbrechen','Cancel'))}</button></div>`;return}
   if(D.mkedit){const i=+D.mkedit,s=doc.content.sections[i-1],box_=ed(i);
     box_.innerHTML=`<label>${esc(t('Überschrift','Heading'))}<input data-mkh maxlength="200" value="${esc(s.heading||'')}"></label><textarea data-mkt rows="8" maxlength="20000">${esc(mkPlain(s))}</textarea>
       <div class="fh">${esc(t('Absätze mit einer Leerzeile trennen, Stichpunkte mit „- “ beginnen. Tabellen und Diagramme bleiben.','Separate paragraphs by an empty line, start bullets with "- ". Tables and charts stay.'))}</div>
       <div class="row"><button type="button" class="b p" data-mkdo="save" data-i="${i}">${esc(t('Speichern','Save'))}</button><button type="button" class="b" data-mkdo="x" data-i="${i}">${esc(t('Abbrechen','Cancel'))}</button></div>`;return}
   if(D.mkre||(D.mkdo==='new')){const i=D.mkre?+D.mkre:0,box_=i?ed(i):v.querySelector('.mknew');
     box_.innerHTML=`<label>${esc(i?t('Was soll anders werden?','What should change?'):t('Worum soll es im neuen Teil gehen?','What should the new part be about?'))}<input data-mkw maxlength="2000" placeholder="${esc(i?t('z. B. kürzer, freundlicher, mit Zahlen','e.g. shorter, friendlier, with numbers'):t('z. B. Kosten und Zeitplan','e.g. costs and schedule'))}"></label>
       <div class="row"><button type="button" class="b p" data-mkdo="${i?'rewrite':'addpart'}" data-i="${i}">${esc(t('Los','Go'))}</button><button type="button" class="b" data-mkdo="x" data-i="${i}">${esc(t('Abbrechen','Cancel'))}</button></div>`;
     const w=box_.querySelector('[data-mkw]');if(w)w.focus();return}
   if(D.mkdrop){const r=await mkJSON('/api/make/doc/'+encodeURIComponent(id)+'/change','POST',{action:'weglassen',sections:[+D.mkdrop]});
     if(!r.r.ok){mkVSay(r.d.detail,true);return}MKOPEN={id,v:0};mkShow(DOCINFO);return}
   const w=D.mkdo;
   if(w==='close'){v.hidden=true;v.textContent='';MKOPEN=null;return}
   if(w==='link'){const a=v.querySelector('[data-mk=dl]');let url;try{url=await mkLink(id,a.dataset.fmt,a.dataset.v)}catch(err){mkVSay(err.message,true);return}
     const mins=(MK&&MK.link_minutes)||10;try{await navigator.clipboard.writeText(url);mkVSay(t(`Link kopiert. Er gilt ${mins} Minuten und höchstens 5 Mal, auch ohne Anmeldung.`,`Link copied. It works for ${mins} minutes and at most 5 times, also without signing in.`))}
     catch(_){mkVSay(t(`Link (${mins} Minuten gültig): `,`Link (valid ${mins} minutes): `)+url)}return}
   if(w==='x'){(+D.i?ed(+D.i):v.querySelector('.mknew')).textContent='';return}
   if(w==='on'){const r=await mkJSON('/api/profile/settings','PUT',{doc_make:true});if(!r.r.ok){mkSay(r.d.detail,true);return}showDocs();return}
   if(w==='sender'){const r=await mkJSON('/api/profile/settings','PUT',{doc_sender:$('mksender').value});mkSay(r.r.ok?t('Gespeichert.','Saved.'):r.d.detail,!r.r.ok);return}
   if(w==='tadd'){const f=$('mktfile');f.value='';f.onchange=async()=>{const file=f.files[0];if(!file)return;const fd=new FormData();fd.append('file',file);
       const r=await apiTry('/api/make/templates',{method:'POST',body:fd});if(!r.r.ok){mkSay(r.d.detail,true);return}mkShow(DOCINFO)};f.click();return}
   el.disabled=true;let r;
   try{
     if(w==='save'){const i=+D.i,s=doc.content.sections[i-1],b=ed(i);
       r=await mkJSON('/api/make/doc/'+encodeURIComponent(id)+'/edit','POST',{section:i,content:Object.assign(mkParse(b.querySelector('[data-mkt]').value,s),{heading:b.querySelector('[data-mkh]').value})})}
     else if(w==='lsave'){const b=ed(1);r=await mkJSON('/api/make/doc/'+encodeURIComponent(id)+'/edit','POST',{letter:{subject:b.querySelector('[data-mkls]').value,paras:b.querySelector('[data-mkt]').value.split(/\n\s*\n/).map(x=>x.trim()).filter(Boolean)}})}
     else if(w==='rewrite'||w==='addpart'){const i=+D.i,b=i?ed(i):v.querySelector('.mknew'),wish=b.querySelector('[data-mkw]').value.trim();
       if(!wish){mkVSay(t('Schreib kurz, was du möchtest.','Say briefly what you want.'),true);return}
       r=await mkJSON('/api/make/doc/'+encodeURIComponent(id)+'/change','POST',w==='rewrite'?{action:'umschreiben',sections:[i],wish}:{action:'neu',sections:[doc.content.sections.length],wish});
       if(r.r.ok&&r.d.job){b.textContent='';mkWait(r.d.job.id);return}}
     else if(w==='restore')r=await mkJSON('/api/make/doc/'+encodeURIComponent(id)+'/restore','POST',{v:+D.v});
     else if(w==='conv')r=await mkJSON('/api/make/doc/'+encodeURIComponent(id)+'/change','POST',{action:'format',format:v.querySelector('[data-mk=fmt]').value});
     else if(w==='sty')r=await mkJSON('/api/make/doc/'+encodeURIComponent(id)+'/change','POST',{action:'vorlage',style:v.querySelector('[data-mk=sty]').value});
     else if(w==='send'){const to=v.querySelector('[data-mk=to]').value;
       const x=await mkSendNow(id,to,v.querySelector('[data-mk=fmt]').value,to==='mail'?v.querySelector('[data-mk=mailto]').value.trim():'');
       mkVSay(x.text,!x.ok);return}
     else return;
     if(!r.r.ok){mkVSay(r.d.detail,true);return}
     MKOPEN={id,v:0};showDocs()}
   finally{el.disabled=false}})}
