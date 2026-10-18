// Ich → Dokumente → Wissensbuch (wissensbuch.py, plan plaene/wissensbuch.md): pages the language model wrote from the own
// documents, every sentence with its source. The contents by kind, one page with its sentences, "Stimmt nicht" per
// sentence, "Neu schreiben" and "Löschen" per page; the nightly check's open items: contradictions ("Stimmt" keeps one
// value) and sentences marked "veraltet?" ("Stimmt noch"). Titles and sentences come from documents: shown as text only.
const WBART={Thema:['Themen','Topics'],Person:['Personen','People'],Firma:['Firmen','Companies'],Ding:['Dinge','Things'],Ort:['Orte','Places']};
const WBWORD={eingearbeitet:['eingearbeitet','worked in'],nichts:['nichts Neues','nothing new'],fehler:['nicht eingearbeitet','not worked in'],
  geloescht:['Seite gelöscht','page deleted'],neu:['Seite neu geschrieben','page written again'],falsch:['Satz entfernt','sentence removed'],
  quelle:['Dokumente weg','documents gone'],geprueft:['nachts geprüft','checked at night'],probe:['Stichprobe: Satz entfernt','sample: sentence removed'],
  stimmt:['Widerspruch geklärt','contradiction settled'],noch:['stimmt noch','still right']};
let WB=null,WBSEL='';
const wbWhen=s=>s?new Date(s*1000).toLocaleString(L==='en'?'en-GB':'de-DE',{dateStyle:'short',timeStyle:'short'}):'';
const wbSay=(x,err)=>{const m=$('wbmsg');if(m){m.className=err?'err':'mut';m.textContent=String(x||'').slice(0,300)}};
function wbCan(){return typeof FEATS!=='undefined'&&!!FEATS&&FEATS.features.some(f=>f.key==='wissensbuch'&&f.can)}
async function wbShow(){const box=$('wbbox');if(!box)return;
  if(typeof FEATS!=='undefined'&&!FEATS&&typeof loadFeats==='function')await loadFeats();
  if(!wbCan()){box.hidden=true;return}
  const r=await apiTry('/api/profile/wissensbuch');if(!r.r.ok){box.hidden=true;return}
  WB=r.d;box.hidden=false;wbDraw()}
function wbDraw(){const box=$('wbin'),W=WB;if(!box||!W)return;
  const pages=(W.seiten||[]).filter(p=>p.n);
  const groups=Object.keys(WBART).map(a=>[a,pages.filter(p=>p.art===a)]).filter(([,l])=>l.length);
  box.innerHTML=`<div class="intro">${esc(t('Der Spark fasst deine Dokumente in ruhigen Minuten zu Seiten zusammen, jeder Satz mit Quelle. Fragen beantwortet er zuerst aus diesen Seiten. Was nicht stimmt, entfernst du hier; es kommt aus demselben Dokument nicht wieder.','In quiet minutes the Spark sums up your documents in pages, every sentence with its source. It answers questions from these pages first. What is wrong you remove here; it does not come back from the same document.'))}</div>
    <div class="mut">${esc(t(`${pages.length} Seiten · ${W.saetze} Sätze · ${W.done} Dokumente eingearbeitet`,`${pages.length} pages · ${W.saetze} sentences · ${W.done} documents worked in`))}${W.wait?esc(t(` · ${W.wait} warten`,` · ${W.wait} waiting`)):''}${W.running?esc(t(' · arbeitet gerade',' · working')):''}</div>
    ${pages.length?'':`<div class="mut">${esc(t('Noch keine Seiten. Sie entstehen, während niemand mit dem Spark spricht, höchstens '+W.day+' Dokumente am Tag.','No pages yet. They are made while nobody talks to the Spark, at most '+W.day+' documents a day.'))}</div>`}
    ${wbOpenItems(W)}
    ${groups.map(([a,l])=>`<h3>${esc(t(...WBART[a]))} (${l.length})</h3><ul class="facts">${l.map(p=>`<li><span><b>${esc(p.title)}</b><br><small class="mut">${esc(t(`${p.n} Sätze aus ${p.docs} Dokumenten`,`${p.n} sentences from ${p.docs} documents`))}${p.widerspruch?' · '+esc(t(`${p.widerspruch} Widersprüche`,`${p.widerspruch} contradictions`)):''}</small></span><button type="button" class="b" data-wbopen="${esc(p.id)}">${esc(t('Lesen','Read'))}</button></li><li hidden data-wbpage="${esc(p.id)}"></li>`).join('')}</ul>`).join('')}
    ${(W.verlauf||[]).length?`<details class="mkmore"><summary>${esc(t('Verlauf','History'))}</summary><ul class="facts small">${W.verlauf.map(v=>`<li><span>${esc(wbWhen(v.at))} · ${esc(t(...(WBWORD[v.word]||[v.word,v.word])))}</span><b>${v.word==='eingearbeitet'?esc(t(`${v.n} Seiten, ${v.m} Sätze`,`${v.n} pages, ${v.m} sentences`)):''}</b></li>`).join('')}</ul></details>`:''}
    <div id="wbmsg" class="mut" role="status"></div>`;
  if(WBSEL)wbOpen(WBSEL)}
function wbSrc(s){return `<small class="mut"><a href="#" data-wbdoc="${esc(s.doc)}">${esc(s.name+(s.page?t(' · S. ',' · p. ')+s.page:''))}</a></small>`}
function wbOpenItems(W){const c=W.widersprueche||[],v=W.veraltet||[];if(!c.length&&!v.length)return'';
  return (c.length?`<h3>${esc(t(`Widersprüche (${c.length})`,`Contradictions (${c.length})`))}</h3><div class="mut">${esc(t('Zwei Dokumente sagen verschiedene Werte. Welcher stimmt? Die anderen fallen weg.','Two documents say different values. Which is right? The others go.'))}</div>
    <ul class="facts">${c.map(g=>`<li><span><b>${esc(g.seite)}</b>${g.werte.map(s=>`<br>${esc(s.text)} ${wbSrc(s)} <button type="button" class="b" data-wbright="${esc(String(s.id))}">${esc(t('Stimmt','Right'))}</button>`).join('')}</span></li>`).join('')}</ul>`:'')
   +(v.length?`<h3>${esc(t(`Veraltet? (${v.length})`,`Out of date? (${v.length})`))}</h3><div class="mut">${esc(t('Ein Datum ist vorbei oder ein Wort wie „derzeit“ ist alt.','A date has passed or a word like "currently" is old.'))}</div>
    <ul class="facts">${v.map(s=>`<li><span>${esc(s.text)}<br><b>${esc(s.seite)}</b> · ${wbSrc(s)}</span><span><button type="button" class="b" data-wbstill="${esc(String(s.id))}">${esc(t('Stimmt noch','Still right'))}</button> <button type="button" class="b" data-wbbad="${esc(String(s.id))}">${esc(t('Stimmt nicht','Wrong'))}</button></span></li>`).join('')}</ul>`:'')}
async function wbOpen(id){const at=document.querySelector(`#wbbox [data-wbpage="${CSS.escape(id)}"]`);if(!at)return;
  const r=await apiTry('/api/profile/wissensbuch/'+encodeURIComponent(id));if(!r.r.ok){wbSay(r.d.detail,true);return}
  WBSEL=id;const p=r.d;at.hidden=false;
  at.innerHTML=`<div class="wbpage"><ul class="facts">${p.saetze.map(s=>`<li><span>${esc(s.text)}<br><small class="mut"><a href="#" data-wbdoc="${esc(s.doc)}">${esc(s.name+(s.page?t(' · S. ',' · p. ')+s.page:''))}</a>${s.mark==='widerspruch'?' · <b class="err">'+esc(t('Widerspruch','Contradiction'))+'</b>':''}${s.flag==='veraltet'?' · <span class="pill warn">'+esc(t('veraltet?','out of date?'))+'</span>':''}</small></span><button type="button" class="b" data-wbbad="${esc(String(s.id))}">${esc(t('Stimmt nicht','Wrong'))}</button></li>`).join('')}</ul>
    <div class="row"><button type="button" class="b" data-wbagain="${esc(p.id)}">${esc(t('Neu schreiben','Write again'))}</button><button type="button" class="b" data-wbdel="${esc(p.id)}">${esc(t('Seite löschen','Delete page'))}</button><button type="button" class="b" data-wbclose="${esc(p.id)}">${esc(t('Schließen','Close'))}</button></div></div>`}
{document.body.addEventListener('click',async e=>{const b=e.target.closest('#wbbox [data-wbopen],#wbbox [data-wbbad],#wbbox [data-wbagain],#wbbox [data-wbdel],#wbbox [data-wbclose],#wbbox [data-wbdoc],#wbbox [data-wbright],#wbbox [data-wbstill]');if(!b)return;const D=b.dataset;
  if(D.wbopen){await wbOpen(D.wbopen);return}
  if(D.wbclose){WBSEL='';const at=document.querySelector(`#wbbox [data-wbpage="${CSS.escape(D.wbclose)}"]`);if(at){at.hidden=true;at.innerHTML=''}return}
  if(D.wbdoc){e.preventDefault();if(typeof docView==='function')docView(D.wbdoc);return}
  if(D.wbright||D.wbstill){b.disabled=true;const r=await apiTry('/api/profile/wissensbuch/satz/'+encodeURIComponent(D.wbright||D.wbstill)+(D.wbright?'/stimmt':'/noch'),{method:'POST'});
    if(!r.r.ok){wbSay(r.d.detail,true);b.disabled=false;return}await wbShow();wbSay(D.wbright?t('Geklärt; die anderen Werte kommen nicht wieder.','Settled; the other values do not come back.'):t('Gemerkt.','Noted.'));return}
  if(D.wbbad){b.disabled=true;const r=await apiTry('/api/profile/wissensbuch/satz/'+encodeURIComponent(D.wbbad),{method:'DELETE'});
    if(!r.r.ok){wbSay(r.d.detail,true);b.disabled=false;return}await wbShow();wbSay(t('Satz entfernt; aus diesem Dokument kommt er nicht wieder.','Sentence removed; it does not come back from this document.'));return}
  if(D.wbagain||D.wbdel){const again=!!D.wbagain,id=D.wbagain||D.wbdel;
    if(!again&&!confirm(t('Seite löschen? Ihre Dokumente werden später neu eingearbeitet.','Delete the page? Its documents are worked in again later.')))return;
    const r=await apiTry('/api/profile/wissensbuch/'+encodeURIComponent(id)+(again?'/neu':''),{method:again?'POST':'DELETE'});
    if(!r.r.ok){wbSay(r.d.detail,true);return}WBSEL='';await wbShow();
    wbSay(again?t('Die Seite entsteht in ruhigen Minuten neu.','The page is written again in quiet minutes.'):t('Seite gelöscht.','Page deleted.'))}})}
