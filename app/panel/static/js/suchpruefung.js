// Ich → Dokumente → Suchprüfung (suchpruefung.py, plan plaene/suche-schaerfen.md, Stufe 1): test questions with a
// known right place measure how well the document search finds it; Sammelfragen need several documents at once. Only numbers and the person's own questions;
// nothing changes by itself. "Richtige Stelle angeben" under an answer fills the form here.
const SPRMODE=[['wort',['Wörter','Words']],['bedeutung',['Bedeutung','Meaning']],['gemischt',['Gemischt','Mixed']],['nachsortiert',['Nachsortiert','Re-ranked']],['wissensbuch',['Mit Wissensbuch','With knowledge book']],['karte',['Mit Wissenskarte','With knowledge map']]];
const SPRSRC={spark:['vom Spark','by the Spark'],eigen:['eigene','own'],antwort:['aus einer Antwort','from an answer']};
let SPR=null,SPRPRE=null;
const sprWhen=s=>s?new Date(s*1000).toLocaleString(L==='en'?'en-GB':'de-DE',{dateStyle:'short',timeStyle:'short'}):'';
const sprPlace=p=>p?t(`Platz ${p}`,`place ${p}`):t('nicht unter den ersten 30','not among the first 30');
const sprSay=(x,err)=>{const m=$('sprmsg');if(m){m.className=err?'err':'mut';m.textContent=String(x||'').slice(0,300)}};
// is the search check open for this profile? (from /api/features, the same rules as the Spark's)
let SPRASK=false;
function sprCan(){if(typeof FEATS==='undefined')return false;
  if(!FEATS){if(!SPRASK&&typeof PROFILE!=='undefined'&&PROFILE&&typeof loadFeats==='function'){SPRASK=true;loadFeats().catch(()=>{})}return false}   // the next answer has it
  return FEATS.features.some(f=>f.key==='suchpruefung'&&f.can)}
async function sprShow(){const box=$('sprbox');if(!box)return;
  if(typeof FEATS!=='undefined'&&!FEATS&&typeof loadFeats==='function')await loadFeats();
  if(!sprCan()){box.hidden=true;return}
  const r=await apiTry('/api/profile/suchpruefung');if(!r.r.ok){box.hidden=true;return}
  SPR=r.d;box.hidden=false;sprDraw();if(SPRPRE){box.open=true;box.scrollIntoView({block:'nearest'})}}
function sprBars(run){if(!run)return '';
  return SPRMODE.filter(([k])=>run.modes&&run.modes[k]).map(([k,n])=>{const v=run.modes[k];
    return `<div class="sprrow"><span>${esc(t(...n))}</span><span class="qbar"><i style="width:${+v.top5||0}%"></i></span><b>${+v.top5||0} %</b><small class="mut">${esc(t(`als Erstes ${+v.top1||0} %`,`first ${+v.top1||0} %`))}</small></div>`}).join('')}
// Sammelfragen (plan wissensbuch, Stufe A): questions that need several documents; measured is how many of them are
// among the first five pieces, and whether all are
function sprSammel(run){const s=run&&run.sammel;if(!s||!s.n)return '';
  return `<h3>${esc(t(`Sammelfragen (${s.n})`,`Multi-document questions (${s.n})`))}</h3>`+SPRMODE.filter(([k])=>s.modes&&s.modes[k]).map(([k,n])=>{const v=s.modes[k];
    return `<div class="sprrow"><span>${esc(t(...n))}</span><span class="qbar"><i style="width:${+v.teil||0}%"></i></span><b>${+v.teil||0} %</b><small class="mut">${esc(t(`alle gefunden ${+v.alle||0} %`,`all found ${+v.alle||0} %`))}</small></div>`}).join('')}
const sprMany=q=>(q.mehr||[]).length>0;
const sprBad=q=>q.at&&(sprMany(q)?!(q.last&&q.last.gemischt>=q.last.von):!(q.last&&q.last.gemischt>0&&q.last.gemischt<=5));
function sprQ(q){const l=q.last||{},g=l.gemischt,many=sprMany(q);
  const names=[q.name||t('Dokument fehlt','document missing'),...(q.mehr||[]).map(m=>m.name||t('Dokument fehlt','document missing'))];
  const where=many?t(`Sammelfrage · ${names.join(', ')}`,`multi-document · ${names.join(', ')}`):names[0]+(q.page?t(' · S. ',' · p. ')+q.page:'');
  const res=many?t(`${+g||0} von ${+l.von||names.length} unter den ersten 5`,`${+g||0} of ${+l.von||names.length} among the first 5`):sprPlace(g);
  return `<li><span>${esc(q.q)}<br><small class="mut">${esc(where)} · ${esc(t(...(SPRSRC[q.src]||SPRSRC.eigen)))}${q.at?' · '+esc(res):''}</small><span class="sprhits" data-sprhits="${esc(q.id)}"></span></span>
    ${q.gone?'':`<button type="button" class="b" data-sprprobe="${esc(q.id)}">${esc(t('Ausprobieren','Try'))}</button>`}<button type="button" class="b" data-sprdel="${esc(q.id)}">${esc(t('Löschen','Delete'))}</button></li>`}
function sprDraw(){const box=$('sprin'),S=SPR;if(!box||!S)return;
  const runs=S.laeufe||[],last=runs[runs.length-1],qs=S.fragen||[];
  const bad=qs.filter(sprBad);
  const docs=(typeof DOCL!=='undefined'&&DOCL||[]).filter(d=>d.state==='ready');
  const pre=SPRPRE||{};
  box.innerHTML=`<div class="intro">${esc(t('Prüffragen mit bekannter richtiger Stelle zeigen, wie oft die Suche in deinen Dokumenten das Richtige findet. Der Spark misst nachts; geändert wird dabei nichts.','Test questions with a known right place show how often the search in your documents finds the right thing. The Spark measures at night; nothing is changed by it.'))}</div>
    <div class="mut">${esc(t(`${qs.length} Prüffragen (höchstens ${S.max})`,`${qs.length} test questions (at most ${S.max})`))}${S.auto?esc(t(' · der Spark schreibt neue in ruhigen Minuten',' · the Spark writes new ones in quiet minutes')):''}${last?' · '+esc(t('letzte Prüfung ','last check ')+sprWhen(last.at)):''}</div>
    ${last?`<div class="sprbars">${sprBars(last)}${sprSammel(last)}</div>${last.seite!=null?`<div class="mut">${esc(t(`Richtige Seite unter den ersten 5: ${last.seite} %`,`Right page among the first 5: ${last.seite} %`))}</div>`:''}<div class="mut">${esc(t(`Suche dauert im Mittel ${last.ms} ms, langsamste ${last.p90} ms`,`Search takes ${last.ms} ms on average, slowest ${last.p90} ms`))}${last.rank_ms?esc(t(` · Nachsortieren ${last.rank_ms} ms`,` · re-ranking ${last.rank_ms} ms`)):''}</div>`:`<div class="mut">${esc(t('Noch keine Prüfung.','No check yet.'))}</div>`}
    ${runs.length>1?`<details class="mkmore"><summary>${esc(t('Verlauf','History'))}</summary><ul class="facts small">${runs.slice().reverse().map(x=>`<li><span>${esc(sprWhen(x.at))} · ${esc(t(`${x.n} Fragen`,`${x.n} questions`))}</span><b>${+((x.modes||{}).gemischt||{}).top5||0} %</b></li>`).join('')}</ul></details>`:''}
    <div class="row"><button type="button" class="b p" data-sprdo="run"${S.running||S.wait?' disabled':''}>${esc(S.running?t('Prüft gerade …','Checking …'):S.wait?t(`Wieder in ${Math.ceil(S.wait/60)} min`,`Again in ${Math.ceil(S.wait/60)} min`):t('Jetzt prüfen','Check now'))}</button></div>
    ${bad.length?`<h3>${esc(t(`Schlecht gefunden (${bad.length})`,`Found badly (${bad.length})`))}</h3><ul class="facts">${bad.slice(0,20).map(sprQ).join('')}</ul>`:''}
    <details class="mkmore"${SPRPRE?' open':''}><summary>${esc(t('Prüffrage hinzufügen','Add a test question'))}</summary>
      <label>${esc(t('Frage','Question'))}</label><input id="sprq" maxlength="200" autocomplete="off" value="${esc(pre.q||'')}" placeholder="${esc(t('z. B. Wie lange gilt die Garantie für den Kühlschrank?','e.g. How long is the fridge under warranty?'))}">
      <div class="two2"><div><label>${esc(t('Richtiges Dokument','Right document'))}</label><select id="sprdoc">${docs.map(d=>`<option value="${esc(d.id)}"${d.id===pre.doc?' selected':''}>${esc(d.title||d.name)}</option>`).join('')}</select></div>
        <div><label>${esc(t('Seite (frei lassen: egal)','Page (empty: any)'))}</label><input id="sprpage" class="num" type="number" min="1" max="100000" value="${pre.page?+pre.page:''}"></div></div>
      <label>${esc(t('Weitere richtige Dokumente (Sammelfrage, frei lassen: keine)','More right documents (multi-document question, empty: none)'))}</label>
      <div class="two2">${[1,2].map(i=>`<div><select id="sprmore${i}"><option value="">${esc(t('– keins –','– none –'))}</option>${docs.map(d=>`<option value="${esc(d.id)}">${esc(d.title||d.name)}</option>`).join('')}</select></div>`).join('')}</div>
      <div class="row"><button type="button" class="b p" data-sprdo="add"${docs.length?'':' disabled'}>${esc(t('Hinzufügen','Add'))}</button></div></details>
    ${qs.length?`<details class="mkmore"><summary>${esc(t(`Alle Prüffragen (${qs.length})`,`All test questions (${qs.length})`))}</summary><ul class="facts">${qs.slice().reverse().map(sprQ).join('')}</ul></details>`:''}
    <div id="sprmsg" class="mut" role="status"></div>`;
  if(SPRPRE){const q=$('sprq');if(q)q.focus()}}
// from an answer: open Ich → Dokumente with the form filled (the question asked, the document shown first)
async function sprFromAnswer(q,doc){SPRPRE={q:String(q||'').slice(0,200),doc:doc||'',src:'antwort'};await openMe('docbox');await sprShow()}
{document.body.addEventListener('click',async e=>{const b=e.target.closest('#sprbox [data-sprdo],#sprbox [data-sprdel],#sprbox [data-sprprobe]');if(!b)return;const D=b.dataset;
  if(D.sprdo==='run'){b.disabled=true;sprSay(t('Prüft …','Checking …'));const r=await apiTry('/api/profile/suchpruefung/lauf',{method:'POST'});
    if(!r.r.ok){sprSay(r.d.detail,true);b.disabled=false;return}await sprShow();sprSay(t('Fertig.','Done.'));return}
  if(D.sprdo==='add'){const page=+$('sprpage').value||null;
    const r=await apiTry('/api/profile/suchpruefung',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({q:$('sprq').value,doc:$('sprdoc').value,page,mehr:[1,2].map(i=>$('sprmore'+i).value).filter(Boolean),src:SPRPRE&&SPRPRE.src||'eigen'})});
    if(!r.r.ok){sprSay(r.d.detail,true);return}SPRPRE=null;await sprShow();sprSay(t('Prüffrage gespeichert; sie zählt ab der nächsten Prüfung.','Test question saved; it counts from the next check.'));return}
  if(D.sprdel){const r=await apiTry('/api/profile/suchpruefung/'+encodeURIComponent(D.sprdel),{method:'DELETE'});if(!r.r.ok){sprSay(r.d.detail,true);return}await sprShow();return}
  if(D.sprprobe){b.disabled=true;const r=await apiTry('/api/profile/suchpruefung/'+encodeURIComponent(D.sprprobe)+'/probe',{method:'POST'});b.disabled=false;
    const at=document.querySelector(`#sprbox [data-sprhits="${CSS.escape(D.sprprobe)}"]`);if(!at)return;
    if(!r.r.ok){at.textContent=String(r.d.detail||'');return}
    at.innerHTML=`<br><small>${esc(t('Jetzt: ','Now: ')+(r.d.von?t(`${r.d.found} von ${r.d.von} unter den ersten 5`,`${r.d.found} of ${r.d.von} among the first 5`):sprPlace(r.d.place)))}</small><ol class="sprtop">${r.d.hits.map(h=>`<li class="${h.ok?'ok':''}">${esc(h.name+(h.page?t(' · S. ',' · p. ')+h.page:''))}</li>`).join('')}</ol>`}})}
// Zustand → Prüfen → Suche prüfen (admin): sums over all profiles, never a question or a document
function sprAdminDraw(d){const c=$('sprcard');if(!c)return;c.hidden=!d.on;if(!d.on)return;const out=$('sprout');
  const run={modes:d.modes||{}};const has=Object.keys(run.modes).length;
  out.innerHTML=`<div class="mut">${esc(t(`${d.fragen} Prüffragen in ${d.profiles} Profilen`,`${d.fragen} test questions in ${d.profiles} profiles`))}${d.last?' · '+esc(t('letzte Prüfung ','last check ')+sprWhen(d.last)):''}</div>
    ${has?`<div class="sprbars">${sprBars(run)}${sprSammel({sammel:{n:Math.max(0,...Object.values(d.sammel||{}).map(v=>v.n)),modes:d.sammel||{}}})}</div><div class="mut">${esc(t(`Suche dauert im Mittel ${d.ms} ms`,`Search takes ${d.ms} ms on average`))}</div>`:`<div class="mut">${esc(t('Noch keine Prüfung. Prüffragen legen die Profile unter Ich → Dokumente → Suchprüfung an.','No check yet. Profiles add test questions under Me → Documents → Search check.'))}</div>`}`;
  const b=$('sprgo');b.disabled=!!(d.running||d.wait);b.textContent=d.running?t('Prüft gerade …','Checking …'):d.wait?t(`Wieder in ${Math.ceil(d.wait/60)} min`,`Again in ${Math.ceil(d.wait/60)} min`):t('Jetzt prüfen','Check now')}
async function sprAdmin(){const r=await apiTry('/api/admin/suchpruefung');if(r.r.ok)sprAdminDraw(r.d)}
if($('sprgo'))$('sprgo').onclick=async()=>{const b=$('sprgo');b.disabled=true;$('sprgomsg').textContent=t('Prüft …','Checking …');
  const r=await apiTry('/api/admin/suchpruefung/lauf',{method:'POST'});
  $('sprgomsg').textContent=r.r.ok?t(`Fertig: ${r.d.done} Profile geprüft.`,`Done: ${r.d.done} profiles checked.`):String(r.d.detail||'');
  if(r.r.ok)sprAdminDraw(r.d);else b.disabled=false};
