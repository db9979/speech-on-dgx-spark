// Funktionen → Weiche (weiche.py, plan weiche-sichtbar.md): the switch of intent.py as a picture and a page. A sentence
// to try lights up its way (question, checks first, group, tools, locks, result); the groups as a list with details
// (built-in words, own words, „Nicht bei“, extra tools, narrowing, test sentences, counts); every change is checked
// against all test sentences before it is saved, and „Rückgängig“ puts the version before back. Admin only; the
// protection rules are shown with a lock and are never settings here. Since plan weiche-intelligenter the page also holds
// what questions no rule recognizes get (route_model, the classification's threshold, „Einordnung messen“), the must
// words (tool_words), the hint words per group and the everyday check („Alltagsquote“, intent_alltag.py).
const WH={d:null,sel:null,tr:null,edit:null,more:false,fix:null};
const WHC=['#22a35a','#e09a14','#0ea5a5','#7c5cf0','#e5484d','#3b82f6','#3b82f6','#0d9488','#c2410c','#db2777','#6366f1','#7b8499','#0891b2','#a16207','#9333ea','#64748b','#16a34a','#2563eb','#be123c','#475569'];
const whName=n=>{if(n.startsWith('@'))return whTool(n.slice(1));const g=WH.d&&WH.d.groups.find(x=>x.name===n);return n==='unklar'?t('unklar','unclear'):n==='mehrere'?t('mehrere','several'):n==='plaudern'?t('Plaudern','Small talk'):g?g.label:n};
const whTool=n=>(WH.d&&WH.d.tools[n])||n;
const whRules=()=>WH.edit||WH.d.rules;
const whDirty=()=>!!WH.edit&&!!WH.d&&JSON.stringify(WH.edit)!==JSON.stringify(WH.d.rules);
// the rule texts ("smarthome: sauna, kamin") as {group: [words]} and back
const whParse=s=>{const o={};String(s||'').split('\n').forEach(l=>{const i=l.indexOf(':');if(i<0)return;const n=l.slice(0,i).trim().toLowerCase();
  const w=l.slice(i+1).split(',').map(x=>x.trim()).filter(Boolean);if(w.length)o[n]=[...new Set([...(o[n]||[]),...w])]});return o};
const whJoin=o=>Object.entries(o).filter(([,w])=>w.length).map(([n,w])=>`${n}: ${w.join(', ')}`).join('\n');
function whChange(f){if(!WH.edit)WH.edit=JSON.parse(JSON.stringify(WH.d.rules));f(WH.edit);whRender()}
async function loadWeiche(){if(!$('whbox'))return;try{const keep=whDirty()?WH.edit:null;WH.d=await (await api('/api/admin/weiche'+(L==='en'?'?lang=en':''))).json();WH.edit=keep;   // unsaved edits stay while the page is left and opened again

  if(!WH.sel)WH.sel=WH.d.groups[0].name;whRender()}catch(e){$('whbox').textContent=e.message}}
function whRender(){const d=WH.d;if(!d)return;
  const tests=d.tests,ownOk=tests.own.filter(x=>x.ok).length,allOk=tests.builtin_ok===tests.builtin&&ownOk===tests.own.length;
  const model={off:t('Unklare Fragen: alle Werkzeuge','Unclear questions: all tools'),on:t('Unklare Fragen: Modell ordnet ein','Unclear questions: the model sorts'),
    lean:t('Unklare Fragen: knapp, mit Hinweis-Schutz','Unclear questions: lean, with hint protection'),systemone:t('Unklare Fragen: Einordnung mit Wahrscheinlichkeit','Unclear questions: classification with probability')}[d.model]||d.model;
  const last=d.history[0],A=d.alltag,aOk=A.richtig+A.geschuetzt;
  $('whpills').innerHTML=`<span class="wh-pill ${d.on?'ok':''}">● ${esc(d.on?t('Gezielte Werkzeugwahl an','Targeted tool choice on'):t('Gezielte Werkzeugwahl aus (nur Anzeige)','Targeted tool choice off (display only)'))}</span>`
    +`<span class="wh-pill">${esc(model)}</span><span class="wh-pill" title="${esc(t('Alltagssätze, die richtig landen oder deren Werkzeuge ein Hinweis behält','Everyday sentences that land right or whose tools a hint keeps'))}">${esc(t('Alltagsquote','Everyday score'))} ${aOk} ${esc(t('von','of'))} ${A.n}</span><span class="wh-pill ${allOk?'ok':'bad'}">${esc(t('Testsätze','Test sentences'))} ${tests.builtin_ok+ownOk} ${esc(t('von','of'))} ${tests.builtin+tests.own.length} ${allOk?'✓':'✗'}</span>`
    +(last?`<span class="wh-pill">${esc(t('Letzte Änderung','Last change'))} ${esc(new Date(last.t*1000).toLocaleString([],{day:'2-digit',month:'2-digit',hour:'2-digit',minute:'2-digit'}))} · <button type="button" class="mlink" data-wh="undo">${esc(t('Rückgängig','Undo'))}</button></span>`:'');
  if(!d.on)$('whpills').insertAdjacentHTML('beforeend',`<div class="mut wh-note">${esc(t('Einschalten unter Funktionen → Gezielte Werkzeugwahl. Bis dahin zeigt die Seite, was die Weiche täte.','Switch on under Features → Targeted tool choice. Until then the page shows what the switch would do.'))}</div>`);
  whFlow();whList();whDetail();whUnclear();whMust();whTests();whStats();whLocks();whBar()}
// ---------------------------------------------------------------- the way of one sentence
async function whTry(){const text=$('whtext').value.trim();if(!text)return;$('whgo').disabled=true;
  try{const body={text,tz:Intl.DateTimeFormat().resolvedOptions().timeZone,before:$('whbefore').value.trim()};if(whDirty())body.rules=WH.edit;
    WH.tr=await (await api('/api/admin/weiche/test'+(L==='en'?'?lang=en':''),{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)})).json()}
  catch(e){WH.tr={err:e.message}}$('whgo').disabled=false;whFlow()}
function whFlow(){const box=$('whflow'),r=WH.tr;if(!r){box.innerHTML=`<div class="mut wh-note">${esc(t('Ein Satz zeigt hier seinen Weg durch die Weiche. Es wird nichts gespeichert und kein Modell gefragt.','A sentence shows its way through the switch here. Nothing is stored and no model is asked.'))}</div>`;$('whwrong').hidden=true;return}
  if(r.err){box.innerHTML=`<div class="err">${esc(r.err)}</div>`;return}
  const li=(on,txt,cls='')=>`<div class="wh-li ${on?'y':''} ${cls}"><i class="wh-dot ${on?'a':''}"></i><span>${txt}</span></div>`;
  const ck=r.checks,pre=ck.plaudern?t('Plaudern','Small talk'):ck.spark?t('Frage zum Spark','About the Spark'):ck.senden?t('Nachricht an jemand','Message to someone'):t('nichts Besonderes','nothing special');
  const src={eigen:t('eigenes Wort','own word'),eingebaut:t('eingebaut','built in'),hilfe:t('Hilfe-Frage','help question'),senden:t('Sende-Bitte','send request'),folge:t('Folgefrage','follow-up')};
  const grp=r.names.length?r.names.map(whName).join(' + '):r.hints.length?t('unklar, mit Hinweis','unclear, with a hint'):t('unklar','unclear');
  const nTools=r.tools.length,kind=k=>r.tools.filter(x=>x.kind===k).length;
  const narrow={gruppe:t(`${nTools} Werkzeuge`,`${nTools} tools`),aus:t('alle (Gruppe grenzt nicht ein)','all (group does not narrow)'),plaudern:t('keine','none'),knapp:t(`${nTools} (knapp)`,`${nTools} (lean)`),modell:t('Modell ordnet ein','the model sorts'),alle:t('alle wie bisher','all as before')}[r.narrow];
  const result=r.direct?t('Panel holt selbst','panel reads itself'):r.force?t('Pflicht-Werkzeug','required tool'):r.narrow==='plaudern'?t('nur Antwort','answer only'):t('Modell wählt','model picks');
  const lockOn=r.notaus>0;
  const st=(n,title,main,body,k)=>`<button type="button" class="wh-st hit" data-wh="step" data-k="${k}"><span class="wh-n">${n} ${esc(title)}</span><b>${esc(main)}</b>${body}</button>`;
  box.innerHTML=st(1,t('Frage','Question'),'„'+r.text.slice(0,60)+(r.text.length>60?'…':'')+'“',li(r.refers,esc(r.refers?t('zeigt auf die Antwort davor','points at the answer before'):t('eigene Worte, kein Rückbezug','own words, no reference back'))),'q')
    +st(2,t('Vorprüfung','Checks first'),pre,li(ck.plaudern,esc(t('Plaudern','Small talk')))+li(ck.spark,esc(t('Frage zum Spark','About the Spark')))+li(ck.senden,esc(t('Nachricht an jemand','Message to someone'))),'pre')
    +st(3,t('Gruppe','Group'),grp,(r.why.map(w=>li(true,w.source==='folge'?`${esc(whName(w.group))} <em>${esc(t('wie die Frage davor','like the question before'))}</em>`:`${esc(whName(w.group))}: „${esc(w.word)}“ <em>${esc(src[w.source]||'')}</em>`)).join('')||li(false,esc(r.mixed?t('mehr als zwei Gruppen: unklar','more than two groups: unclear'):t('keine Regel passt','no rule fits'))))
      +r.hints.map(h=>li(true,`${esc(t('Hinweis','Hint'))} ${esc(whName(h.group))}: „${esc(h.word)}“ <em>${esc(t('grenzt nicht ein, behält die Werkzeuge','does not narrow, keeps the tools'))}</em>`)).join('')
      +r.removed.map(n=>li(false,esc(t('„Nicht bei“ nimmt heraus: ','„Not with“ takes out: ')+whName(n)),'bad')).join(''),'grp')
    +st(4,t('Werkzeuge','Tools'),narrow,(kind('gruppe')?li(true,esc(t(`${kind('gruppe')} aus der Gruppe`,`${kind('gruppe')} from the group`))):'')+(kind('zusatz')?li(true,esc(t(`${kind('zusatz')} zusätzlich`,`${kind('zusatz')} extra`))):'')
      +(kind('immer')?li(false,esc(t(`${kind('immer')} immer dabei`,`${kind('immer')} always kept`))):'')+(kind('hinweis')?li(true,esc(t(`${kind('hinweis')} durch Hinweis behalten`,`${kind('hinweis')} kept by a hint`))):'')+li(false,esc(t('nur, was das Profil sonst auch darf','only what the profile may anyway'))),'tools')
    +st(5,t('Sperren','Locks'),lockOn?t('Notaus Stufe ','Emergency stop stage ')+r.notaus:t('keine für den Satz allein','none for the sentence alone'),d_locks(r),'locks')
    +st(6,t('Ergebnis','Result'),result,(r.direct?li(true,esc(whTool(r.direct)+(r.date?' · '+r.date:''))):'')+(r.force&&!r.direct?li(true,esc(whTool(r.force))):'')
      +(r.ack?li(true,esc(t('Sofort-Satz: ','Instant sentence: ')+'„'+r.ack+'“')):li(false,esc(t('kein Sofort-Satz','no instant sentence')))),'res');
  box.querySelectorAll('.wh-st').forEach(b=>{const k=b.dataset.k;if(k==='grp'&&!r.names.length)b.classList.remove('hit');if(k==='pre'&&pre===t('nichts Besonderes','nothing special'))b.classList.add('pass')});
  $('whwrong').hidden=false}
function d_locks(r){return WH.d.locks.filter(x=>x.k!=='notaus'||r.notaus>0).map(x=>`<div class="wh-li"><span>🔒 ${esc(x.s)}</span></div>`).join('')
  +(r.refers?`<div class="wh-li y"><span>${esc(t('Eine Sperre aus der Antwort davor bliebe bestehen.','A lock from the answer before would stay.'))}</span></div>`:'')}
// ---------------------------------------------------------------- the groups, list and details
function whList(){const d=WH.d,box=$('whlist');const rows=d.groups.slice();rows.push({name:'unklar',label:t('unklar','unclear'),tools:[],own:[],words:[],stats:d.unklar.stats||{}});
  const shown=WH.more?rows:rows.slice(0,10);
  box.innerHTML=shown.map((g,i)=>{const s=g.stats||{},r=whGroup(g.name);const own=g.name==='unklar'?0:r.own.length;
    const small=g.name==='unklar'?t('alle Werkzeuge, so wie ohne Weiche','all tools, as without the switch'):t(`${g.words.length} Wörter`,`${g.words.length} words`)+(own?t(` · ${own} eigene`,` · ${own} own`):'')+t(` · ${g.tools.length} Werkzeuge`,` · ${g.tools.length} tools`)+(g.direct&&g.direct.length?t(' · direkt',' · direct'):'')+(r.off?t(' · grenzt nicht ein',' · does not narrow'):'');
    return `<div class="ld-row${WH.sel===g.name?' on':''}" role="button" tabindex="0" data-wh="pick" data-g="${esc(g.name)}"><span class="ld-ico" style="background:${g.name==='unklar'?'#7b8499':WHC[i%WHC.length]}">${esc((g.label||g.name).slice(0,1))}</span><span class="ld-mid"><b>${esc(g.label)}</b><small>${esc(small)}</small></span><span class="ld-right"><span class="ld-when" title="${esc(t('heute / 7 Tage','today / 7 days'))}">${s.today||0} · ${s.n||0}</span></span></div>`}).join('')
    +(rows.length>10?`<div class="ld-more"><button type="button" class="b" data-wh="more">${esc(WH.more?t('Weniger zeigen','Show fewer'):t(`Weitere zeigen (${rows.length-10})`,`Show more (${rows.length-10})`))}</button></div>`:'')}
function whGroup(n){const r=whRules();return {own:whParse(r.route_words)[n]||[],not:whParse(r.route_not)[n]||[],extra:whParse(r.route_extra)[n]||[],off:(r.route_off||[]).includes(n),
  tests:(r.route_tests||[]).filter(x=>x.want.split('+').includes(n))}}
function whChips(list,kind,g){return list.map(w=>`<span class="wh-chip ${kind}">${esc(w)}<button type="button" aria-label="${esc(t('entfernen','remove'))}" data-wh="del" data-kind="${kind}" data-g="${esc(g)}" data-w="${esc(w)}">×</button></span>`).join('')
  +`<span class="wh-add"><input maxlength="40" placeholder="${esc(t('+ Wort','+ word'))}" data-kind="${kind}" data-g="${esc(g)}" aria-label="${esc(t('Wort hinzufügen','Add word'))}"></span>`}
function whDetail(){const box=$('whdet'),d=WH.d,n=WH.sel;
  if(n==='unklar'){const s=d.unklar.stats||{};box.innerHTML=`<button type="button" class="b ld-back" data-wh="back">‹ ${esc(t('Gruppen','Groups'))}</button><h3>${esc(t('unklar','unclear'))}</h3>`
    +`<p class="ld-note">${esc(t('Fragen, die keine Regel erkennt. Was sie bekommen, stellst du unten bei „Fragen, die keine Regel erkennt“ ein. Hinweiswörter behalten dabei die Werkzeuge ihrer Gruppe.','Questions no rule recognizes. What they get is set below at “Questions no rule recognizes”. Hint words keep their group’s tools.'))}</p>`
    +`<div class="wh-sec"><div class="wh-h">${esc(t('Zählung','Counts'))}</div>${esc(t(`heute ${s.today||0}, 7 Tage ${s.n||0}`,`today ${s.today||0}, 7 days ${s.n||0}`))}</div>`
    +`<p class="ld-note">${esc(t('Eine Frage landet hier und gehört woandershin? Oben ausprobieren und „Falsch zugeordnet …“ wählen.','A question lands here but belongs elsewhere? Try it above and choose “Wrongly sorted …”.'))}</p>`;return}
  const g=d.groups.find(x=>x.name===n);if(!g){box.innerHTML='';return}const r=whGroup(n),s=g.stats||{};
  const built=WH.wordsOpen===n?g.words:g.words.slice(0,16);
  const addable=d.known.filter(x=>!g.tools.includes(x)&&!d.keep.includes(x)&&!r.extra.includes(x));
  box.innerHTML=`<button type="button" class="b ld-back" data-wh="back">‹ ${esc(t('Gruppen','Groups'))}</button>`
    +`<div class="wh-dh"><h3>${esc(g.label)}</h3><label class="wh-sw"><span>${esc(t('eingrenzen','narrow'))}</span>${tglIn(`data-wh="off" data-g="${esc(n)}"`,!r.off)}</label></div>`
    +(g.says?`<p class="ld-note mut">${esc(g.says)}</p>`:'')
    +`<div class="wh-sec"><div class="wh-h">${esc(t('Erkennt die Frage an','Recognizes the question by'))}<span>${esc(t('eingebaut, immer aktiv','built in, always on'))}</span></div>${built.map(w=>`<span class="wh-chip">${esc(w)}</span>`).join('')}${g.words.length>16?`<button type="button" class="mlink" data-wh="words" data-g="${esc(n)}">${esc(WH.wordsOpen===n?t('weniger','fewer'):'+ '+(g.words.length-16))}</button>`:''}</div>`
    +`<div class="wh-sec"><div class="wh-h">${esc(t('Eigene Wörter','Own words'))}<span>${esc(t(`höchstens ${d.limits.words}`,`at most ${d.limits.words}`))}</span></div>${whChips(r.own,'own',n)}</div>`
    +`<div class="wh-sec"><div class="wh-h">${esc(t('Nicht bei','Not with'))}<span>${esc(t('Wort nimmt diese Gruppe heraus','word takes this group out'))}</span></div>${whChips(r.not,'not',n)}</div>`
    +(g.hints&&g.hints.length?`<div class="wh-sec"><div class="wh-h">${esc(t('Hinweiswörter','Hint words'))}<span>${esc(t('eingebaut, grenzen nie ein','built in, never narrow'))}</span></div>${g.hints.map(w=>`<span class="wh-chip hint">${esc(w)}</span>`).join('')}<div class="mut wh-small">${esc(t('Erkennt keine Regel die Frage sicher, behalten diese Wörter die Werkzeuge der Gruppe, auch bei „knapp“ und neben der Wahl des Modells.','When no rule recognizes the question for sure, these words keep the group’s tools, also with “lean” and beside the model’s pick.'))}</div></div>`:'')
    +`<div class="wh-sec"><div class="wh-h">${esc(t('Werkzeuge','Tools'))}<span>${esc(t('nur, was das Profil sonst auch darf','only what the profile may anyway'))}</span></div>`
      +g.tools.map(x=>`<div class="wh-tool"><i class="wh-cb fix">✓</i>${esc(whTool(x))} <code>${esc(x)}</code></div>`).join('')
      +r.extra.map(x=>`<div class="wh-tool"><i class="wh-cb on">✓</i>${esc(whTool(x))} <code>${esc(x)}</code> <span class="wh-tag">${esc(t('zusätzlich','extra'))}</span><button type="button" class="mlink" data-wh="del" data-kind="extra" data-g="${esc(n)}" data-w="${esc(x)}">${esc(t('entfernen','remove'))}</button></div>`).join('')
      +(r.extra.length<d.limits.extra&&addable.length?`<select class="wh-addtool" data-g="${esc(n)}" aria-label="${esc(t('Werkzeug hinzufügen','Add tool'))}"><option value="">${esc(t('+ Werkzeug zusätzlich …','+ extra tool …'))}</option>${addable.map(x=>`<option value="${esc(x)}">${esc(whTool(x))}</option>`).join('')}</select>`:'')
      +`<div class="mut wh-small">${esc(t('Immer dabei: ','Always kept: ')+d.keep.map(whTool).join(', '))}</div></div>`
    +(g.vorrang?`<div class="wh-sec"><div class="wh-h">${esc(t('Vorrang','Precedence'))}</div><div class="wh-small">${esc(g.vorrang)}</div></div>`:'')
    +(g.direct.length?`<div class="wh-sec"><div class="wh-h">${esc(t('Direkt abrufen','Read directly'))}</div><div class="wh-small">${esc(t('Kurze, eindeutige Lesefragen holt das Panel selbst: ','Short, plain reading questions the panel reads itself: ')+g.direct.map(whTool).join(', '))}</div></div>`:'')
    +`<div class="wh-sec"><div class="wh-h">${esc(t('Testsätze','Test sentences'))}<span>${g.tests.filter(x=>x.ok).length} / ${g.tests.length} ✓</span></div>`
      +g.tests.slice(0,8).map(x=>`<div class="wh-tool"><span class="${x.ok?'ok':'err'}">${x.ok?'✓':'✗'}</span> ${esc(x.q)}${x.ok?'':` <span class="mut">→ ${esc(x.got?x.got.split('+').map(whName).join(' + '):t('unklar','unclear'))}</span>`}</div>`).join('')
      +`<div class="wh-add wide"><input maxlength="${d.limits.q}" placeholder="${esc(t('+ Testsatz für diese Gruppe','+ test sentence for this group'))}" data-kind="test" data-g="${esc(n)}" aria-label="${esc(t('Testsatz hinzufügen','Add test sentence'))}"></div></div>`
    +`<div class="wh-sec"><div class="wh-h">${esc(t('Zählung','Counts'))}</div><div class="wh-small">${esc(t(`heute ${s.today||0}, 7 Tage ${s.n||0}`,`today ${s.today||0}, 7 days ${s.n||0}`)+(s.n?t(` · im Schnitt ${s.avg} von ${s.avg_of} Werkzeugen`,` · on average ${s.avg} of ${s.avg_of} tools`)+(s.direct?t(` · ${s.direct} direkt`,` · ${s.direct} direct`):''):''))}</div></div>`;
  $('whsplit').classList.add('wh-has')}
// ---------------------------------------------------------------- questions no rule recognizes, must words
const WHM={off:['Alle Werkzeuge wie bisher (empfohlen)','All tools as before (recommended)'],on:['Das Sprachmodell ordnet kurz einer Gruppe zu (etwa eine halbe Sekunde)','The language model sorts into a group (about half a second)'],
  lean:['Knapp: Websuche, Gedächtnis und Hinweis-Gruppen (beginnt früher)','Lean: web search, memory and hinted groups (starts sooner)'],systemone:['Einordnung mit Wahrscheinlichkeit, erst ab der Schwelle (qwen38, etwa 0,2 s)','Classification with probability, only from the threshold (qwen38, about 0.2 s)']};
function whUnclear(){const d=WH.d,r=whRules(),A=d.alltag;
  $('whunclear').innerHTML=`<div class="wh-unc"><label for="whmodel">${esc(t('Was bekommen sie?','What do they get?'))}</label><select id="whmodel">${Object.keys(WHM).map(k=>`<option value="${k}"${r.route_model===k?' selected':''}>${esc(t(...WHM[k]))}</option>`).join('')}</select>`
    +(d.systemone?`<label for="whmin">${esc(t('Einordnung grenzt ein ab','Classification narrows from'))}</label><select id="whmin">${d.steps.map(v=>`<option value="${v}"${Number(r.systemone_min)===v?' selected':''}>${Math.round(v*100)} %${v===0.8?esc(t(' (Standard)',' (default)')):''}</option>`).join('')}</select>`:'')+'</div>'
    +`<div class="wh-score"><span><b>${A.richtig}</b> ${esc(t('richtig','right'))}</span><span><b>${A.geschuetzt}</b> ${esc(t('durch Hinweis behalten','kept by a hint'))}</span><span><b>${A.offen}</b> ${esc(t('offen','open'))}</span><span><b>${A.falsch}</b> ${esc(t('falsch','wrong'))}</span></div>`
    +`<div class="mut wh-small">${esc(t(`Gemessen an ${A.n} Alltagssätzen, die nie zum Einstellen benutzt werden. „Offen“ heißt: Mit „knapp“ oder einer Modellwahl fehlt das passende Werkzeug.`,`Measured on ${A.n} everyday sentences never used to set the rules up. “Open” means: with “lean” or a model pick the right tool is missing.`))}</div>`;
  $('whs1').hidden=!d.systemone}
window.whSetMin=v=>{if(!WH.d||!WH.d.steps.includes(v))return false;whChange(r=>{r.systemone_min=v});return true};
function whMust(){const d=WH.d,o=whParse(whRules().tool_words),tools=Object.keys(o);
  $('whmust').innerHTML=`<p class="ld-note mut">${esc(t('Kommt eines dieser Wörter vor, muss das Modell zuerst dieses Werkzeug benutzen, und die Weiche findet seine Gruppe. Nur ganze Wörter, höchstens 20 pro Werkzeug; die eingebauten bleiben immer.','When one of these words comes up, the model has to use this tool first, and the switch finds its group. Whole words only, at most 20 per tool; the built-in ones always stay.'))}</p>`
    +(tools.length?tools.map(x=>`<div class="wh-must"><b>${esc(whTool(x))}</b> <code>${esc(x)}</code><div>${o[x].map(w=>`<span class="wh-chip own">${esc(w)}<button type="button" aria-label="${esc(t('entfernen','remove'))}" data-wh="del" data-kind="must" data-g="${esc(x)}" data-w="${esc(w)}">×</button></span>`).join('')}</div></div>`).join(''):`<div class="mut wh-small">${esc(t('Noch keine Pflicht-Wörter.','No must words yet.'))}</div>`)
    +`<div class="wh-try"><select id="whmusttool" aria-label="${esc(t('Werkzeug','Tool'))}">${d.must_tools.slice().sort((a,b)=>whTool(a).localeCompare(whTool(b))).map(x=>`<option value="${esc(x)}">${esc(whTool(x))}</option>`).join('')}</select><span class="wh-add"><input maxlength="40" placeholder="${esc(t('+ Wort','+ word'))}" data-kind="must" aria-label="${esc(t('Pflicht-Wort hinzufügen','Add must word'))}"></span></div>`}
// ---------------------------------------------------------------- test sentences, counts, locks
function whTests(){const d=WH.d,own=d.tests.own,A=d.alltag;
  $('whtests').innerHTML=`<p class="ld-note">${esc(t(`${d.tests.builtin_ok} von ${d.tests.builtin} eingebauten Sätzen landen richtig. Eigene Sätze kommen dazu; vor jedem Speichern prüft das Panel alle.`,`${d.tests.builtin_ok} of ${d.tests.builtin} built-in sentences land right. Own sentences come on top; before every save the panel checks them all.`))}</p>`
    +(own.length?`<table class="wh-tab"><tr><th>${esc(t('Satz','Sentence'))}</th><th>${esc(t('erwartet','expected'))}</th><th>${esc(t('jetzt','now'))}</th><th></th></tr>`+own.map(x=>`<tr><td>${esc(x.q)}</td><td>${esc(x.want?x.want.split('+').map(whName).join(' + '):t('unklar','unclear'))}</td><td class="${x.ok?'ok':'err'}">${x.ok?'✓':'✗ '+esc(x.got?x.got.split('+').map(whName).join(' + '):t('unklar','unclear'))}</td><td><button type="button" class="mlink" data-wh="deltest" data-q="${esc(x.q)}">${esc(t('entfernen','remove'))}</button></td></tr>`).join('')+'</table>':`<div class="mut wh-small">${esc(t('Noch keine eigenen Testsätze. Unter einer Gruppe oder über „Falsch zugeordnet …“ hinzufügen.','No own test sentences yet. Add them under a group or through “Wrongly sorted …”.'))}</div>`)
    +`<details class="wh-alltag"><summary>${esc(t(`Alltagssätze: ${A.richtig+A.geschuetzt} von ${A.n} gut`,`Everyday sentences: ${A.richtig+A.geschuetzt} of ${A.n} fine`))}</summary>`
      +`<div class="mut wh-small">${esc(t('Eingebaut, nur zum Messen: sie werden nie zu Regeln. Diese landen nicht richtig:','Built in, for measuring only: they never become rules. These do not land right:'))}</div>`
      +A.rows.filter(x=>x.kind!=='geschuetzt').map(x=>`<div class="wh-tool"><span class="${x.kind==='falsch'?'err':'mut'}">${x.kind==='falsch'?'✗':'○'}</span> ${esc(x.q)} <span class="mut">→ ${esc(x.got?x.got.split('+').map(whName).join(' + '):t('unklar','unclear'))} (${esc(t('erwartet','expected'))} ${esc(x.want?x.want.split('+').map(whName).join(' + '):t('unklar','unclear'))})</span></div>`).join('')+'</details>'
    +(d.tests.wrong.filter(x=>!x.own).length?`<div class="err wh-small">${esc(t('Eingebaute Sätze, die mit deinen Regeln anders landen: ','Built-in sentences that land elsewhere with your rules: '))}${d.tests.wrong.filter(x=>!x.own).slice(0,5).map(x=>esc('„'+x.q+'“')).join(', ')}</div>`:'')}
// Lernen (weiche.learned): which group the model took for questions no rule knew, and hint words to take over
function whLearn(){const L2=WH.d.lernen;if(!L2||!L2.rows.length)return '';const own=whParse(whRules().route_words);
  return `<div class="wh-small wh-learn"><b>${esc(t('Gelernt aus unklaren Fragen','Learned from unclear questions'))}</b> <span class="mut">${esc(t('(nur Gruppe und festes Hinweiswort, nie ein Wort der Frage)','(only the group and a fixed hint word, never a word of the question)'))}</span></div>`
    +L2.rows.map(r=>`<div class="wh-tool">${esc(t(`${r.label}: ${r.n}× vom Modell gewählt`,`${r.label}: picked ${r.n}× by the model`))}`
      +r.offer.filter(o=>!(own[r.group]||[]).includes(o.word)).map(o=>` <button type="button" class="wh-chip hint" data-wh="learnuse" data-g="${esc(r.group)}" data-w="${esc(o.word)}" title="${esc(t(`„${o.word}“ führte ${o.n}× hierher: als Wort der Gruppe übernehmen`,`„${o.word}“ led here ${o.n}×: take it as a word of the group`))}">＋ ${esc(o.word)} (${o.n}×)</button>`).join('')+'</div>').join('')}
function whStats(){const s=WH.d.stats,tot=s.total;if(!tot.n){$('whstats').innerHTML=`<div class="mut wh-small">${esc(t('Noch keine Fragen gezählt. Gezählt wird nur die Gruppe und die Zahl der Werkzeuge, nie ein Wort der Frage.','No questions counted yet. Only the group and the number of tools are counted, never a word of the question.'))}</div>`+whLearn();return}
  const p=x=>Math.round(100*x/tot.n),rules=p(tot.rules),model=p(tot.model),unk=p(tot.unklar);
  const rows=Object.entries(s.groups).sort((a,b)=>b[1].n-a[1].n).slice(0,8);
  $('whstats').innerHTML=`<div class="wh-small">${esc(t(`${tot.n} Fragen in 7 Tagen`,`${tot.n} questions in 7 days`))}</div><div class="wh-bar"><i style="width:${rules}%" class="r"></i><i style="width:${model}%" class="m"></i><i style="width:${unk}%" class="u"></i></div>`
    +`<div class="wh-small wh-legend"><span><i class="r"></i>${esc(t(`von Regeln erkannt ${rules} %`,`recognized by rules ${rules} %`))}</span><span><i class="m"></i>${esc(t(`vom Modell eingeordnet ${model} %`,`sorted by the model ${model} %`))}</span><span><i class="u"></i>${esc(t(`unklar ${unk} %`,`unclear ${unk} %`))}</span></div>`
    +`<table class="wh-tab"><tr><th>${esc(t('Gruppe','Group'))}</th><th>${esc(t('Fragen','Questions'))}</th><th>${esc(t('Ø Werkzeuge','Ø tools'))}</th><th>${esc(t('direkt','direct'))}</th></tr>`
    +rows.map(([k,v])=>`<tr><td>${esc(whName(k))}</td><td>${v.n}</td><td>${esc(t(`${v.avg} von ${v.avg_of}`,`${v.avg} of ${v.avg_of}`))}</td><td>${v.direct||'–'}</td></tr>`).join('')+'</table>'+whLearn()}
function whLocks(){$('whlocks').innerHTML=WH.d.locks.map(x=>`<div class="wh-tool">🔒 ${esc(x.t)}</div>`).join('')+`<div class="mut wh-small">${esc(t('Schutzregeln gelten immer und lassen sich hier nicht abschalten.','Protection rules always apply and cannot be switched off here.'))}</div>`}
function whBar(){const bar=$('whbar');bar.hidden=!whDirty()}
// ---------------------------------------------------------------- saving
async function whSave(confirm){const msg=$('whmsg');msg.textContent=t('Prüfe alle Testsätze …','Checking all test sentences …');
  try{const r=await api('/api/admin/weiche'+(L==='en'?'?lang=en':''),{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({rules:WH.edit,confirm:!!confirm})});
    WH.d=await r.json();WH.edit=null;msg.textContent=t('Gespeichert.','Saved.');whRender();if(WH.tr&&!WH.tr.err)whTry()}
  catch(e){if(e.status===409){let f={flips:[],count:0};try{f=JSON.parse(e.detail)}catch{}
      msg.innerHTML=`<div class="err">${esc(t(`${f.count} Testsatz/Testsätze landen danach anders:`,`${f.count} test sentence(s) land elsewhere afterwards:`))}</div>`+f.flips.slice(0,6).map(x=>`<div class="wh-small">„${esc(x.q)}“ → ${esc(x.got?x.got.split('+').map(whName).join(' + '):t('unklar','unclear'))} (${esc(t('erwartet','expected'))} ${esc(x.want?x.want.split('+').map(whName).join(' + '):t('unklar','unclear'))})</div>`).join('')
        +`<button type="button" class="b" data-wh="force">${esc(t('Trotzdem speichern','Save anyway'))}</button>`}
    else msg.innerHTML=`<span class="err">${esc(e.message)}</span>`}}
async function whUndo(){if(!confirm(t('Die letzte Änderung der Weiche zurücknehmen?','Take back the last change of the switch?')))return;
  try{WH.d=await (await api('/api/admin/weiche/undo'+(L==='en'?'?lang=en':''),{method:'POST'})).json();WH.edit=null;whRender()}catch(e){$('whmsg').innerHTML=`<span class="err">${esc(e.message)}</span>`}}
// ---------------------------------------------------------------- „Falsch zugeordnet“: from the trial, Logs → Anfragen and the chat
window.whOpenFix=(text,group)=>{WH.fix={text:text||'',want:'',got:group||'',res:null};if(typeof goSec==='function')goSec('route');
  const go=()=>{if(!WH.d){setTimeout(go,150);return}whFix();$('whfix').scrollIntoView({behavior:'smooth',block:'start'});if(!WH.fix.text)$('whfixq').focus()};go()};
function whFix(){const box=$('whfix'),f=WH.fix;if(!f){box.hidden=true;return}box.hidden=false;
  box.innerHTML=`<div class="wh-dh"><h3>${esc(t('Falsch zugeordnet','Wrongly sorted'))}</h3><button type="button" class="b" data-wh="fixclose">${esc(t('Schließen','Close'))}</button></div>`
    +(f.got&&!f.text?`<p class="ld-note mut">${esc(t(`Die Anfrage landete bei „${whName(f.got)}“. Die Frage selbst wird nie aufgezeichnet: schreib sie hier noch einmal.`,`The request landed at “${whName(f.got)}”. The question itself is never recorded: type it here again.`))}</p>`:'')
    +`<div class="wh-step"><i>1</i><div><b>${esc(t('Satz','Sentence'))}</b><input id="whfixq" maxlength="${WH.d.limits.q}" value="${esc(f.text)}" aria-label="${esc(t('Satz','Sentence'))}"></div></div>`
    +`<div class="wh-step"><i>2</i><div><b>${esc(t('Richtige Gruppe','Right group'))}</b><div>${WH.d.groups.map(g=>`<button type="button" class="ld-chip${f.want===g.name?' on':''}" data-wh="fixwant" data-g="${esc(g.name)}">${esc(g.label)}</button>`).join(' ')}</div></div></div>`
    +`<div class="wh-step"><i>3</i><div><b>${esc(t('Vorschlag der Weiche','The switch suggests'))}</b><div id="whfixres" class="wh-small mut">${esc(t('Satz und Gruppe wählen.','Choose sentence and group.'))}</div></div></div>`;
  if(f.res)whFixRes()}
async function whSuggest(){const f=WH.fix;f.text=$('whfixq').value.trim();if(!f.text||!f.want)return;$('whfixres').textContent=t('Prüfe …','Checking …');
  try{f.res=await (await api('/api/admin/weiche/suggest',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({text:f.text,want:f.want})})).json();whFixRes()}
  catch(e){$('whfixres').innerHTML=`<span class="err">${esc(e.message)}</span>`}}
function whFixRes(){const f=WH.fix,r=f.res,box=$('whfixres');box.classList.remove('mut');
  const now=r.names.length?r.names.map(whName).join(' + '):t('unklar','unclear');
  if(r.names.includes(f.want)&&r.names.length===1){box.innerHTML=esc(t(`Landet schon bei „${whName(f.want)}“. Als Testsatz merken?`,`Already lands at “${whName(f.want)}”. Keep it as a test sentence?`))+` <button type="button" class="b" data-wh="fixtest">${esc(t('Als Testsatz','As test sentence'))}</button>`;return}
  box.innerHTML=`<div>${esc(t('Jetzt: ','Now: ')+now)}</div>`+(r.words.length?r.words.map((w,i)=>`<div class="wh-sug"><span class="wh-chip own">${esc(w.word)}</span> ${esc(t(`als eigenes Wort für „${whName(f.want)}“`,`as own word for “${whName(f.want)}”`))} → ${w.ok?'<span class="ok">✓</span>':'<span class="err">✗</span>'} <span class="${w.count?'err':'mut'}">${esc(w.count?t(`${w.count} Testsatz/-sätze landen anders`,`${w.count} test sentence(s) change`):t('alle Testsätze unverändert','all test sentences unchanged'))}</span> <button type="button" class="b p" data-wh="fixuse" data-i="${i}">${esc(t('Übernehmen','Apply'))}</button></div>`).join('')
    :`<div class="mut">${esc(t('Kein Wort des Satzes taugt als eigenes Wort (zu kurz, zu allgemein oder schon vergeben).','No word of the sentence fits as an own word (too short, too common or taken).'))}</div>`)
    +r.not.map(x=>`<div class="wh-sug"><span class="wh-chip not">${esc(x.word)}</span> ${esc(t(`als „Nicht bei“ für „${whName(x.group)}“`,`as “Not with” for “${whName(x.group)}”`))} <button type="button" class="b" data-wh="fixnot" data-g="${esc(x.group)}" data-w="${esc(x.word)}">${esc(t('Übernehmen','Apply'))}</button></div>`).join('')
    +`<label class="wh-small wh-keep"><input type="checkbox" id="whfixkeep" checked> ${esc(t('als Testsatz speichern','save as test sentence'))}</label>`
    +`<div class="mut wh-small">${esc(t('Übernehmen ändert erst die Regeln auf dieser Seite; gespeichert wird mit „Prüfen und speichern“ (mit Rückgängig).','Apply changes the rules on this page first; “Check and save” stores them (with undo).'))}</div>`}
function whAddTest(r,q,want){r.route_tests=(r.route_tests||[]).filter(x=>x.q.toLowerCase()!==q.toLowerCase());r.route_tests.push({q,want})}
// ---------------------------------------------------------------- events (no inline handlers: strict CSP)
if($('whbox')){
  const W={h:t('Weiche','Switch'),intro:t('Hier entscheidet der Spark mit festen Regeln, welche Werkzeuge eine Frage bekommt. Das Sprachmodell sieht nur, was die Weiche durchlässt; Regeln lassen sich ergänzen, aber nie über die Rechte eines Profils hinaus.','Here the Spark decides with fixed rules which tools a question gets. The language model only sees what the switch lets through; rules can be added to, never beyond what a profile may do.'),
    groups:t('Gruppen','Groups'),tests:t('Testsätze','Test sentences'),stats:t('Statistik (7 Tage, nur Anzahlen)','Statistics (7 days, counts only)'),locks:t('Schutzregeln','Protection rules'),unclear:t('Fragen, die keine Regel erkennt','Questions no rule recognizes'),must:t('Pflicht-Wörter','Must words'),
    s1:t('Die Testsätze der Weiche einmal durch die Einordnung schicken: wie oft sie eingrenzt und wie oft das falsch wäre, je Schwelle, mit Vorschlag. Läuft im Hintergrund und wartet, solange jemand spricht.','Send the switch’s test sentences through the classification once: how often it narrows and how often that would be wrong, per threshold, with a suggestion. Runs in the background and waits while someone speaks.'),dirty:t('Ungespeicherte Änderungen an der Weiche','Unsaved changes to the switch')};
  document.querySelectorAll('[data-wht]').forEach(x=>x.textContent=W[x.dataset.wht]);
  $('whtext').placeholder=t('Satz ausprobieren, z. B. Mach die Sauna an','Try a sentence, e.g. Turn on the sauna');$('whtext').setAttribute('aria-label',t('Satz ausprobieren','Try a sentence'));
  $('whbefore').placeholder=t('Frage davor (wahlweise, für Folgefragen)','Question before (optional, for follow-ups)');$('whbefore').setAttribute('aria-label',t('Frage davor','Question before'));
  $('whgo').textContent=t('Ausprobieren','Try');$('whwrong').textContent=t('Falsch zugeordnet …','Wrongly sorted …');
  $('whsave').textContent=t('Prüfen und speichern','Check and save');$('whdrop').textContent=t('Verwerfen','Discard');
  $('whgo').onclick=whTry;$('whtext').addEventListener('keydown',e=>{if(e.key==='Enter'){e.preventDefault();whTry()}});
  $('whwrong').onclick=()=>window.whOpenFix(WH.tr&&WH.tr.text||$('whtext').value.trim(),WH.tr&&WH.tr.label);
  $('whsave').onclick=()=>whSave(false);$('whdrop').onclick=()=>{WH.edit=null;$('whmsg').textContent='';whRender()};
  $('whbox').addEventListener('click',e=>{const b=e.target.closest('[data-wh]');if(!b)return;const a=b.dataset.wh,g=b.dataset.g;
    if(a==='pick'){WH.sel=g;whList();whDetail();$('whsplit').classList.add('ld-sel')}
    else if(a==='back'){$('whsplit').classList.remove('ld-sel')}
    else if(a==='more'){WH.more=!WH.more;whList()}
    else if(a==='words'){WH.wordsOpen=WH.wordsOpen===g?null:g;whDetail()}
    else if(a==='undo')whUndo();
    else if(a==='force')whSave(true);
    else if(a==='step'){const k=b.dataset.k;if(k==='grp'&&WH.tr&&WH.tr.names[0]){WH.sel=WH.tr.names[0];whList();whDetail();$('whsplit').scrollIntoView({behavior:'smooth'})}
      else if(k==='locks')$('whlocks').scrollIntoView({behavior:'smooth'});else if(k==='res'||k==='tools'){if(WH.tr&&WH.tr.names[0]){WH.sel=WH.tr.names[0];whDetail()}$('whdet').scrollIntoView({behavior:'smooth'})}}
    else if(a==='del'){const kind=b.dataset.kind,w=b.dataset.w,key={own:'route_words',not:'route_not',extra:'route_extra',must:'tool_words'}[kind];
      whChange(r=>{const o=whParse(r[key]);o[g]=(o[g]||[]).filter(x=>x!==w);r[key]=whJoin(o)})}
    else if(a==='learnuse'){const w=b.dataset.w;whChange(r=>{const o=whParse(r.route_words);o[g]=[...new Set([...(o[g]||[]),w])];r.route_words=whJoin(o)});
      WH.sel=g;whList();whDetail();$('whbar').scrollIntoView({behavior:'smooth',block:'center'})}
    else if(a==='deltest'){const q=b.dataset.q;whChange(r=>{r.route_tests=(r.route_tests||[]).filter(x=>x.q!==q)})}
    else if(a==='fixclose'){WH.fix=null;whFix()}
    else if(a==='fixwant'){WH.fix.want=g;WH.fix.text=$('whfixq').value.trim();whFix();whSuggest()}
    else if(a==='fixuse'||a==='fixnot'||a==='fixtest'){const f=WH.fix,keep=a==='fixtest'||($('whfixkeep')&&$('whfixkeep').checked);
      whChange(r=>{if(a==='fixuse'){const w=f.res.words[+b.dataset.i];const o=whParse(r.route_words);o[f.want]=[...new Set([...(o[f.want]||[]),w.word])];r.route_words=whJoin(o)}
        if(a==='fixnot'){const o=whParse(r.route_not);o[g]=[...new Set([...(o[g]||[]),b.dataset.w])];r.route_not=whJoin(o)}
        if(keep)whAddTest(r,f.text,f.want)});
      WH.sel=f.want;WH.fix=null;whFix();whList();whDetail();$('whbar').scrollIntoView({behavior:'smooth',block:'center'})}});
  $('whbox').addEventListener('change',e=>{const x=e.target;
    if(x.dataset.wh==='off'){const g=x.dataset.g;whChange(r=>{const o=new Set(r.route_off||[]);if(x.checked)o.delete(g);else o.add(g);r.route_off=[...o]})}
    else if(x.classList.contains('wh-addtool')&&x.value){const g=x.dataset.g,v=x.value;whChange(r=>{const o=whParse(r.route_extra);o[g]=[...new Set([...(o[g]||[]),v])];r.route_extra=whJoin(o)})}
    else if(x.id==='whmodel'){const v=x.value;whChange(r=>{r.route_model=v})}
    else if(x.id==='whmin'){const v=Number(x.value);whChange(r=>{r.systemone_min=v})}
    else if(x.id==='whfixq'&&WH.fix){WH.fix.text=x.value.trim();if(WH.fix.want)whSuggest()}});
  $('whbox').addEventListener('keydown',e=>{const x=e.target;if(e.key==='Enter'&&x.closest&&x.closest('.ld-row')){x.click();return}
    if(e.key!=='Enter'||!x.dataset||!x.dataset.kind||x.tagName!=='INPUT')return;e.preventDefault();const v=x.value.trim(),g=x.dataset.g,kind=x.dataset.kind;if(!v)return;
    if(kind==='test'){whChange(r=>whAddTest(r,v,g));return}
    if(!/^[\p{L}\p{N}][\p{L}\p{N} \-]{1,39}$/u.test(v)){x.setCustomValidity(t('Nur Buchstaben, Ziffern, Leerzeichen und Bindestrich, 2 bis 40 Zeichen.','Letters, digits, spaces and hyphens only, 2 to 40 characters.'));x.reportValidity();return}
    if(kind==='must'){const tool=$('whmusttool').value;whChange(r=>{const o=whParse(r.tool_words);o[tool]=[...new Set([...(o[tool]||[]),v.toLowerCase()])];r.tool_words=whJoin(o)});return}
    const key=kind==='own'?'route_words':'route_not';whChange(r=>{const o=whParse(r[key]);o[g]=[...new Set([...(o[g]||[]),v.toLowerCase()])];r[key]=whJoin(o)})});
  $('whbox').addEventListener('input',e=>{if(e.target.setCustomValidity)e.target.setCustomValidity('')});
}
