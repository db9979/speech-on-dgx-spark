// Zustand → Verbessern (berater.py, faelle.py, admin): cases, proposals from the fixed catalog, Prüfstand, Übernehmen /
// Ablehnen / Anders, Nachkontrolle after 24 hours. Every text from the server goes through esc; the model's one short
// reason is data and shown as such. Stufe C asks for a second step (a code shown here), Umgebung only shows steps to copy.
const VB={d:null,tab:'props',sel:null,more:10};
const VBST={offen:t('offen','open'),uebernommen:t('übernommen','taken'),abgelehnt:t('abgelehnt','rejected'),zurueck:t('zurückgenommen','undone'),erledigt:t('erledigt','done')};
const VBCS={neu:t('neu','new'),vorschlag:t('Vorschlag da','proposal ready'),lokal:t('lokal behoben','fixed locally'),issue:t('als Meldung','as a report'),erledigt:t('erledigt','done'),verworfen:t('verworfen','dropped')};
// the kinds of proposal as words with what they risk (berater.STUFEN, Plan „Verbessern verständlicher“ 4)
const vbStufe=k=>{const s=((VB.d||{}).stufen||{})[k];return s?t(s[0],s[1]):k};
const vbRisk=k=>{const s=((VB.d||{}).stufen||{})[k];return s?t(s[2],s[3]):''};
function vbLegend(d){const s=d.stufen||{};return `<details class="adv"><summary>${esc(t('Was die Arten bedeuten','What the kinds mean'))}: ${esc(Object.keys(s).map(vbStufe).join(' · '))}</summary>`+
  Object.keys(s).map(k=>`<div class="ld-sw"><span><b>${esc(vbStufe(k))}</b><br><small class="mut">${esc(vbRisk(k))}</small></span></div>`).join('')+'</details>'}
// Klartext-Karte (klartext.card): what happened, where from, why (the Befund, with whose word), what helps
function vbKarte(k,rows){if(!k)return '';const w=k.woher||{},src=(rows||[]).map(r=>r.src);
  const chips=[vbT(w.src),...(w.clients||[]).map(c=>typeof RCLIENT!=='undefined'&&RCLIENT[c]||c),w.tool?t('Werkzeug: ','Tool: ')+vbT(w.tool):'',w.group?t('Gruppe: ','Group: ')+w.group:'',
    `${w.n||1}×`+(w.who?' · '+w.who+' '+t(w.who===1?'Person':'Personen',w.who===1?'person':'people'):''),w.first?vbWhen(w.first)+(w.last&&w.last!==w.first?' – '+vbWhen(w.last):''):''].filter(Boolean);
  const traces=(w.traces||[]).length&&typeof window.openTrace==='function'&&!document.body.classList.contains('mgr')?(w.traces||[]).map(id=>`<button type="button" class="b" data-vbtrace="${esc(id)}">${esc(t('Anfrage ansehen','View request'))} ${esc(id)}</button>`).join(''):'';
  return `<div class="vbk"><div class="vbk-s vbk-was"><b>${esc(t('Was ist passiert','What happened'))}</b>${esc(vbT(k.was))}</div>`+
    `<div class="vbk-s vbk-woher"><b>${esc(t('Woher','Where from'))}</b><div class="vbk-chips">${chips.map(c=>`<span class="ld-badge">${esc(c)}</span>`).join('')}</div>${traces?`<div class="ld-acts" style="margin-top:4px">${traces}</div>`:''}</div>`+
    ((k.warum||[]).length?`<div class="vbk-s vbk-warum"><b>${esc(t('Warum','Why'))}</b>${k.warum.map((r,i)=>esc(vbT(r))+(src[i]&&VBSRC[src[i]]?` <span class="mut">(${esc(VBSRC[src[i]])})</span>`:'')).join('<br>')}</div>`:'')+
    ((k.hilft||[]).length?`<div class="vbk-s vbk-hilft"><b>${esc(t('Was hilft','What helps'))}</b><ol>${k.hilft.map(h=>`<li>${esc(vbT(h))}</li>`).join('')}</ol></div>`:'')+'</div>'}
const VBRES={hilft:t('hilft','helps'),gleich:t('unverändert','unchanged'),schlechter:t('schlechter','worse')};
const vbT=x=>Array.isArray(x)?t(x[0],x[1]||x[0]):x||'';
const vbWhen=s=>s?new Date(s*1000).toLocaleString([], {day:'2-digit',month:'2-digit',hour:'2-digit',minute:'2-digit'}):'';
async function loadVerb(){const box=$('vbbox');if(!box)return;
  try{VB.d=await (await api('/api/admin/berater')).json()}catch(e){$('vbmsg').textContent=e.message;return}
  vbRender()}
function vbLists(d){const p=d.props||[];return {
  cases:(d.cases||[]).filter(x=>x.status==='neu'),props:p.filter(x=>x.status==='offen'),
  check:p.filter(x=>x.status==='uebernommen'&&!x.check),done:p.filter(x=>x.status!=='offen'&&!(x.status==='uebernommen'&&!x.check)),
  luecken:d.luecken||[],regeln:d.regeln||[],kat:d.katalog||[]}}
function vbRender(){const d=VB.d;if(!d)return;const L=vbLists(d);
  $('vboff').hidden=d.on;$('vbmain').hidden=!d.on;
  const lv=d.live||{};$('vbsum').textContent=d.on?t(`Heute ${lv.gut||0} 👍 · ${lv.schlecht||0} 👎 · ${lv.faelle||0} neue Fälle · ${L.props.length} ${L.props.length===1?'Vorschlag':'Vorschläge'} offen`,
    `Today ${lv.gut||0} 👍 · ${lv.schlecht||0} 👎 · ${lv.faelle||0} new cases · ${L.props.length} ${L.props.length===1?'proposal':'proposals'} open`)+(d.model?'':' · '+t('ohne Sprachmodell im Heimnetz: die Regel wählt','no language model at home: the rule picks')):'';
  // the 👍 share per group (7 days): red under 75 % (from 20 ratings on that is a finding of its own)
  $('vbquote').innerHTML=(d.quote||[]).length?esc(t('👍-Quote, 7 Tage: ','👍 share, 7 days: '))+d.quote.map(q=>`<span class="${q.pct<75&&q.good+q.bad>=20?'vbqbad':''}">${esc(q.name)} ${q.pct} % (${q.good+q.bad})</span>`).join(' · '):'';
  $('vbquote').hidden=!d.on||!(d.quote||[]).length;
  const tabs=[['cases',t('Eingang','Inbox'),L.cases.length],['props',t('Vorschläge','Proposals'),L.props.length],['check',t('Nachkontrolle','Re-check'),L.check.length],
    ['done',t('Erledigt','Done'),L.done.length],['luecken',t('Lücken','Gaps'),L.luecken.length],['regeln',t('Regeln','Rules'),L.regeln.length],['bericht',t('Bericht','Report'),''],['kat',t('Katalog','Catalog'),L.kat.length]];
  $('vbchips').innerHTML=tabs.map(([k,l,n])=>`<button type="button" class="ld-chip${VB.tab===k?' on':''}" data-vbtab="${k}">${esc(l)} <b>${n}</b></button>`).join('');
  const rows=L[VB.tab]||[];let html='';
  if(VB.tab==='kat')html=vbKat(d);
  else if(VB.tab==='bericht')html=vbReport(d.bericht||{});
  else if(VB.tab==='regeln')html=vbBuiltin(d)+(rows.length?vbRules(rows,d):`<div class="ld-empty mut">${esc(t('Noch keine eigene Regel. Sie entstehen hier aus Vorschlägen oder von Hand unter Funktionen → Weiche und Einstellungen → Sprachmodell.','No own rule yet. They come from proposals here or by hand under Features → Switch and Settings → Language model.'))}</div>`);
  else if(VB.tab==='luecken')html=rows.length?vbGaps(rows):`<div class="ld-empty mut">${esc(t('Keine Lücke: für jede Frage war ein passendes Werkzeug da.','No gap: a fitting tool was there for every question.'))}</div>`;
  else if(!rows.length)html=`<div class="ld-empty mut">${esc({cases:t('Kein neuer Fall.','No new case.'),props:t('Kein offener Vorschlag.','No open proposal.'),
    check:t('Nichts wartet auf die Nachkontrolle.','Nothing waits for the re-check.'),done:t('Noch nichts erledigt.','Nothing done yet.')}[VB.tab])}</div>`;
  else html=(VB.tab==='props'?vbLegend(d):'')+rows.slice(0,VB.more).map(x=>VB.tab==='cases'?vbCaseRow(x,d):vbPropRow(x)).join('')+(rows.length>VB.more?`<div class="ld-more"><button type="button" class="b" data-vbmore="1">${esc(t('Weitere zeigen','Show more'))}</button></div>`:'');
  $('vblist').innerHTML=html;vbDetail()}
function vbCaseRow(x,d){const k=(d.kinds||{})[x.kind]||[x.kind,x.kind];
  const sub=x.karte?vbT(x.karte.was):[x.title||'',x.tool?wzName(x.tool):''].filter(Boolean).join(' · ');
  return `<div class="ld-row${VB.sel==='c'+x.id?' on':''}" tabindex="0" data-vbsel="c${esc(x.id)}"><div class="ld-mid"><b>${esc(vbT(k))}</b><small>${esc(sub||'–')}</small></div>
    <div class="ld-right"><span class="ld-badge">${x.n}×</span><span class="ld-when">${esc(vbWhen(x.last||x.t))}</span></div></div>`}
function vbPropRow(x){const st=x.status==='uebernommen'&&x.check?VBRES[x.check.result]||x.check.result:VBST[x.status]||x.status;
  const cls=x.status==='offen'?(x.pruef&&x.pruef.ok?'read':'err'):x.check&&x.check.result==='schlechter'?'err':x.check&&x.check.result==='hilft'?'sh':'off';
  const n=(x.faelle||[]).length,sub=(n>1?t(`${n} Fälle · `,`${n} cases · `):'')+(x.karte?vbT(x.karte.was):x.why||'');
  return `<div class="ld-row${VB.sel==='p'+x.id?' on':''}" tabindex="0" data-vbsel="p${esc(x.id)}"><div class="ld-mid"><b>${esc(vbT(x.title))}</b><small>${esc(sub)}</small></div>
    <div class="ld-right">${VB.d&&VB.d.best===x.id?`<span class="ld-badge sh">★ ${esc(t('beste Empfehlung','best pick'))}</span>`:''}<span class="ld-badge ${cls}">${esc(st)}</span><span class="ld-badge off">${esc(vbStufe(x.stufe))}</span>${x.auto?`<span class="ld-badge due">${esc(t('Autopilot','autopilot'))}</span>`:''}</div></div>`}
function vbKat(d){const g={A:[],B:[],C:[],P:[]};for(const e of d.katalog||[])(g[e.stufe]||[]).push(e);
  return Object.entries(g).map(([s,rows])=>`<div class="ld-grp"><span>${esc(vbStufe(s))}</span><span>${rows.length}</span></div>`+rows.map(e=>`<div class="ld-row" style="cursor:default"><div class="ld-mid"><b>${esc(vbT(e.name))}</b><small>${esc(e.way)}${e.range?' · '+esc(e.range[0]+' … '+e.range[1]+', '+t('Schritt','step')+' '+e.range[2]):''}</small></div></div>`).join('')).join('')+
    `<div class="ld-grp"><span>${esc(t('Stufe D · nie','Stage D · never'))}</span><span>${(d.never||[]).length}</span></div>`+(d.never||[]).map(x=>`<div class="ld-row" style="cursor:default"><div class="ld-mid"><b>${esc(vbT(x))}</b></div></div>`).join('')+
    `<div class="ld-grp"><span>${esc(t('Melder','Detectors'))}</span><span></span></div>`+(d.melder||[]).map(m=>`<label class="ld-sw"><span>${esc(vbT(m.name))}</span><input type="checkbox" data-vbmelder="${esc(m.key)}"${m.on?' checked':''}></label>`).join('')}
// Lücken (plan vorschlaege-besser.md, V5): what no offered tool could answer, counted; a wish goes to Probleme melden
function vbGaps(rows){return `<div class="ld-note mut">${esc(t('Für diese Fragen war kein passendes Werkzeug angeboten: Funktion aus, für das Profil gesperrt, nicht eingerichtet oder es fehlt dem Spark.','For these questions no fitting tool was offered: function off, locked for the profile, not set up or missing in the Spark.'))}</div>`+
  rows.map(r=>`<div class="ld-row" style="cursor:default"><div class="ld-mid"><b>${esc(r.names.map(vbT).join(', '))}</b><small>${esc(t(`${r.cases} Fälle · ${r.n} Meldungen · ${r.who} Personen`,`${r.cases} cases · ${r.n} reports · ${r.who} people`))}</small></div><div class="ld-right"><span class="ld-when">${esc(vbWhen(r.last))}</span></div></div>`).join('')}
// Regeln (R7): every own rule of the admin with where it came from; „Entfernen“ takes out just that one
function vbRuleSrc(s){if(!s)return t('von Hand','by hand');
  return (s.auto?t('Autopilot','autopilot'):s.analyse?t('Analyse','analysis'):t('Vorschlag','proposal'))+' · '+vbWhen(s.t)}
function vbRules(rows,d){const by={};rows.forEach((r,i)=>{(by[r.key]=by[r.key]||[]).push([r,i])});
  return vbRuleTools(d)+Object.entries(by).map(([k,rs])=>{const a=(d.regel_arten||{})[k]||[k,k,''];
    return `<div class="ld-grp"><span>${esc(t(a[0],a[1]))}</span><span>${rs.length}</span></div><div class="ld-note mut">${esc(t(a[2],a[3]||a[2]))}</div>`+
      rs.map(([r,i])=>`<div class="ld-row" style="cursor:default"><div class="ld-mid"><b>${esc(r.name==='test'?r.item:(vbT(r.label)||r.name)+': '+r.item)}</b><small>${esc(r.name==='test'?'':r.name)}${r.name==='test'?'':' · '}${esc(vbRuleSrc(r.src))}</small></div>`+(r.weg?`<span class="ld-badge due">${esc(vbT(r.weg))}</span>`:'')+
        `<div class="ld-right"><button type="button" class="b" data-vbrule="${i}">${esc(t('Entfernen','Remove'))}</button></div></div>`).join('')}).join('')}
// the panel's built-in answer rules (answercheck.BUILTIN, taten.py): what they do, on or off, how often today; never removable
function vbBuiltin(d){const b=d.eingebaut||[];if(!b.length)return '';
  return `<div class="ld-grp"><span>${esc(t('Eingebaut','Built in'))}</span><span>${b.length}</span></div>`+b.map(x=>`<div class="ld-row" style="cursor:default"><div class="ld-mid"><b>${esc(vbT(x.name))}</b><small>${esc(vbT(x.what))}</small></div>`+
    `<div class="ld-right"><span class="ld-badge ${x.on?'sh':'off'}">${esc(x.on?t(`heute ${x.today}× eingegriffen`,`stepped in ${x.today}× today`):t('aus','off'))}</span></div></div>`).join('')}
// Monatsbericht (Version 4): numbers of the last 30 days, never a question
function vbReport(r){const g=r.groups||[];
  return `<div class="ld-note">${esc(t(`Letzte ${r.days||30} Tage: ${r.taken||0} Regeln übernommen (${r.auto||0} Autopilot), ${r.helped||0} geholfen, ${r.worse||0} schlechter, ${r.undone||0} zurückgenommen · ${r.open||0} Vorschläge offen · ${r.gaps||0} Lücken · ${r.rules||0} eigene Regeln`,
    `Last ${r.days||30} days: ${r.taken||0} rules taken (${r.auto||0} autopilot), ${r.helped||0} helped, ${r.worse||0} worse, ${r.undone||0} undone · ${r.open||0} proposals open · ${r.gaps||0} gaps · ${r.rules||0} own rules`))}</div>`+
    g.map(x=>`<div class="ld-row" style="cursor:default"><div class="ld-mid"><b>${esc(x.name)}</b><small>${x.good} 👍 · ${x.bad} 👎</small></div><div class="ld-right"><span class="ld-badge ${x.before!=null&&x.pct<x.before?'err':x.before!=null&&x.pct>x.before?'sh':''}">${x.pct==null?'–':x.pct+' %'}${x.before!=null?' ('+esc(t('davor','before'))+' '+x.before+' %)':''}</span></div></div>`).join('')}
// Version 3: export, import (Prüfstand first) and the kept versions of the rules
function vbRuleTools(d){const v=d.versionen||[];
  return `<div class="ld-acts"><button type="button" class="b" data-vbrx="export">${esc(t('Exportieren','Export'))}</button><label class="b" style="cursor:pointer">${esc(t('Importieren','Import'))}<input type="file" accept="application/json,.json" data-vbrx="import" hidden></label></div>`+
    (v.length?`<details class="adv"><summary>${esc(t('Frühere Versionen','Earlier versions'))} (${v.length})</summary>`+v.map((x,i)=>`<div class="ld-sw"><span>${esc(vbWhen(x.t))} · ${esc(x.why)}</span><button type="button" class="b" data-vbver="${i}">${esc(t('Zurück zu dieser','Back to this one'))}</button></div>`).join('')+'</details>':'')}
async function vbImport(file,force){let rules;try{const j=JSON.parse(await file.text());rules=j.rules}catch(e){$('vbmsg').textContent=t('Keine Regel-Datei.','Not a rules file.');return}
  try{const r=await (await api('/api/admin/berater/regeln/import',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({rules,force:!!force})})).json();VB.d=r;const im=r.imported||{};
    if(!im.ok){if(confirm(t(`${im.count} Testsätze der Weiche kämen anders heraus. Trotzdem importieren?`,`${im.count} test sentences of the Weiche would come out differently. Import anyway?`)))return vbImport(file,true)}
    else $('vbmsg').textContent=t('Regeln importiert; die Version davor ist aufgehoben.','Rules imported; the version before is kept.');vbRender()}catch(e){$('vbmsg').textContent=e.message}}
// the Befund (befund.py): the cause by fixed rules, before any proposal
const VBSRC={person:t('laut Person (👎)','by the person (👎)'),admin:t('laut Admin','by the admin'),weiche:t('laut Weiche','by the Weiche'),frage:t('aus der Frage','from the question'),pflicht:t('Pflicht-Regel','must rule')};
function vbBefund(rows){return (rows||[]).length?`<div class="ld-note"><span class="mut">${esc(t('Befund:','Finding:'))}</span> `+rows.map(r=>esc(t(r.de,r.en))+(r.src&&VBSRC[r.src]?` <span class="mut">(${esc(VBSRC[r.src])})</span>`:'')).join('<br>')+'</div>':''}
function vbSoll(x,d){const k=d.karte||[],cur=(x.want_tool||[])[0]||'';const top=Object.entries(x.soll||{}).sort((a,b)=>b[1]-a[1])[0];
  return `<label for="vbsoll">${esc(t('Was wäre richtig gewesen? Erwartetes Werkzeug','What would have been right? Expected tool'))}</label>`+
    (top?`<div class="mut">${esc(t('Person sagt: hätte nachsehen sollen ','The person says: should have looked '))}${esc(vbT((d.soll||{})[top[0]]))} (${top[1]}×)</div>`:'')+
    `<div class="row" style="gap:6px;flex-wrap:wrap"><select id="vbsoll" style="flex:1;min-width:0"><option value="">${esc(t('– wählen –','– choose –'))}</option>`+
    k.map(e=>`<option value="${esc(e.tool)}"${e.tool===cur?' selected':''}>${esc(vbT(e.name))} · ${esc(e.tool)}</option>`).join('')+
    `</select><button type="button" class="b" data-vbcase="soll">${esc(t('Neu bewerten','Re-assess'))}</button></div>`}
// Nachstellen (V3): the question again with the change, only reading tools; the result is data
function vbReplay(x){const r=x.replay;if(!r)return '';
  return `<div class="ld-note"><b class="${r.ok?'':'danger'}">${esc(r.ok?t('Nachgestellt: passt','Replayed: fits'):t('Nachgestellt: passt nicht','Replayed: does not fit'))}</b><br>${esc(t(r.de,r.en))}</div>`}
function vbFind(){const d=VB.d;if(!d||!VB.sel)return null;const id=VB.sel.slice(1);
  return VB.sel[0]==='c'?{c:(d.cases||[]).find(x=>x.id===id)}:{p:(d.props||[]).find(x=>x.id===id)}}
function vbDetail(){const el=$('vbdetail'),f=vbFind(),box=$('vbbox');el.hidden=!f||!(f.c||f.p);box.classList.toggle('ld-sel',!el.hidden);if(el.hidden)return;
  const back=`<button type="button" class="b ld-back" data-vbback="1">← ${esc(t('Zurück','Back'))}</button>`;
  if(f.c){const x=f.c,d=VB.d;const ex=(x.examples||[]).filter(e=>e.q).map(e=>`<li>${esc(vbWhen(e.t))} · „${esc(e.q)}“</li>`).join('');
    const p=x.pid&&(d.props||[]).find(y=>y.id===x.pid&&y.status==='offen');
    el.innerHTML=back+`<h3>${esc(vbT((d.kinds||{})[x.kind]||x.kind))}</h3><dl class="ld-facts">`+
      [[t('Zustand','State'),VBCS[x.status]||x.status],[t('Fehlercode','Error code'),x.code],[t('Seit','Since'),vbWhen(x.t)]].filter(r=>r[1]).map(r=>`<dt>${esc(r[0])}</dt><dd>${esc(r[1])}</dd>`).join('')+'</dl>'+
      (x.karte?vbKarte(x.karte,x.befund):vbBefund(x.befund))+
      (p?`<div class="ld-note"><span class="mut">${esc(t('Vorschlag dazu:','Proposal for it:'))}</span> <button type="button" class="mlink" data-vbsel="p${esc(p.id)}">${esc(vbT(p.title))}</button></div>`:'')+
      (ex?`<div class="mut">${esc(t('Fragen (nur mit Zustimmung):','Questions (only with consent):'))}</div><ul class="bghist">${ex}</ul>`:'')+
      ((x.notes||[]).length?`<div class="ld-note">${(x.notes||[]).map(n=>'„'+esc(n)+'“').join('<br>')}</div>`:'')+vbSoll(x,d)+
      `<div class="ld-acts"><button type="button" class="b p" data-vbcase="propose">${esc(t('Jetzt Vorschlag machen','Make a proposal now'))}</button>${d.analyse&&d.model?`<button type="button" class="b" data-vbcase="analyse">${esc(t('Fall analysieren','Analyse case'))}</button>`:''}<button type="button" class="b danger" data-vbcase="drop">${esc(t('Verwerfen','Drop'))}</button></div><div class="ld-note mut" id="vbdmsg"></div>`;return}
  const x=f.p,pr=x.pruef||{};
  const ch=x.change||{},facts=[[t('Art','Kind'),vbStufe(x.stufe)],[t('Zustand','State'),VBST[x.status]||x.status],[t('Seit','Since'),vbWhen(x.t)]];
  if('old' in ch)facts.push([t('Jetzt','Now'),String(ch.old)],[t('Neu','New'),String(ch.new)]);
  if(x.check)facts.push([t('Nachkontrolle','Re-check'),(VBRES[x.check.result]||x.check.result)+' · '+t(`${x.check.again} neue Meldungen`,`${x.check.again} new reports`)+(x.check.drop!=null?' · 👍 '+(x.check.drop>0?'−':'+')+Math.abs(x.check.drop)+t(' Punkte',' points'):'')]);
  else if(x.check_at&&x.status==='uebernommen')facts.push([t('Nachkontrolle','Re-check'),vbWhen(x.check_at)]);
  let acts='';
  if(x.status==='offen'){
    if(x.stufe==='U')acts=`<button type="button" class="b p" data-vbact="done">${esc(t('Erledigt, nachkontrollieren','Done, re-check'))}</button>`;
    else if(x.stufe==='I')acts=VB.d.issue?`<button type="button" class="b p" data-vbact="issue">${esc(t('Als Meldung vorbereiten','Prepare as a report'))}</button>`:`<span class="mut">${esc(t('Dafür unter Funktionen „Fälle als Meldung vorbereiten“ einschalten.','For this switch on "Prepare cases as reports" under Features.'))}</span>`;
    else acts=`<button type="button" class="b p" data-vbact="take"${pr.ok?'':' disabled'}>${esc(t('Übernehmen','Take'))}</button>`;
    acts+=`<button type="button" class="b" data-vbact="reject">${esc(t('Ablehnen','Reject'))}</button><button type="button" class="b" data-vbact="nutzlos" title="${esc(t('Passt nicht zur Ursache: der Fall bekommt den nächsten Vorschlag','Does not fit the cause: the case gets the next proposal'))}">${esc(t('Nicht zielführend','Not helpful'))}</button>`}
  else if(x.status==='uebernommen'&&x.stufe!=='U')acts=`<button type="button" class="b" data-vbact="undo">${esc(t('Zurücknehmen','Undo'))}</button>`;
  const steps=x.stufe==='U'?(ch.steps||[]).map((s,i)=>`<div class="row" style="gap:6px;margin:4px 0"><code style="flex:1;min-width:0;overflow-wrap:anywhere">${esc(s)}</code><button type="button" class="b" data-vbcopy="${i}">${esc(t('Kopieren','Copy'))}</button></div>`).join(''):'';
  const laut=x.key==='aussprache'&&x.status==='offen'?`<label>${esc(t('So soll es klingen','How it should sound'))} („${esc(ch.word||'')}“)</label><input id="vblaut" maxlength="40" value="${esc(ch.laut||'')}" autocomplete="off">`:'';
  const alts=x.status==='offen'&&(x.alts||[]).length?`<details class="adv"><summary>${esc(t('Anders','Other'))} (${x.alts.length})</summary>`+x.alts.map((a,i)=>`<div class="ld-sw"><span>${esc(vbT(a.title))}${a.pruef&&!a.pruef.ok?' · <span class="danger">'+esc(t('rot','red'))+'</span>':''}</span><button type="button" class="b" data-vbalt="${i}">${esc(t('Diesen','This one'))}</button></div>`).join('')+'</details>':'';
  const idea=vbIdea(x);
  el.innerHTML=back+`<h3>${esc(vbT(x.title))}</h3><dl class="ld-facts">${facts.filter(r=>r[1]!=null&&r[1]!=='').map(r=>`<dt>${esc(r[0])}</dt><dd>${esc(r[1])}</dd>`).join('')}</dl>`+
    (x.trusted===false?`<div class="ld-note mut">${esc(t('Nur von einer Person gemeldet: der Autopilot übernimmt das nie.','Reported by one person only: the autopilot never takes this.'))}</div>`:'')+
    (x.recheck?`<div class="ld-note"><b class="${x.recheck.ok?'':'danger'}">${esc(x.recheck.why==='update'?t('Nachgeprüft nach Update','Re-checked after update'):t('Nachgeprüft nach Modellwechsel','Re-checked after model change'))}</b><br>${esc(t(x.recheck.de,x.recheck.en))}</div>`:'')+
    (x.karte?vbKarte(x.karte,x.befund):vbBefund(x.befund))+vbWhy(x)+(x.model?`<div class="ld-note"><span class="mut">${esc(t('Sprachmodell:','Language model:'))}</span> ${esc(x.model)}</div>`:'')+steps+laut+vbReplay(x)+
    `<div class="ld-note"><b class="${pr.ok?'':'danger'}">${esc(pr.ok?t('Prüfstand grün','Test bench green'):t('Prüfstand rot','Test bench red'))}</b>${(pr.red||[]).map(r=>'<br><span class="danger">'+esc(r)+'</span>').join('')}${(pr.notes||[]).map(r=>'<br><span class="mut">'+esc(r)+'</span>').join('')}${(pr.flips||[]).slice(0,5).map(f=>'<br><span class="mut">„'+esc(f.q)+'“ → '+esc(f.got||t('unklar','unclear'))+'</span>').join('')}</div>`+
    idea+alts+`<div class="ld-acts">${acts}</div><div class="ld-note" id="vbdmsg"></div>`}
// „Warum dieser Vorschlag“ (berater._prop_why, best_pick): the cause it fits, what it risks and how it is undone,
// the cases it stands for (each opens its own card)
function vbWhy(x){const fs=x.faelle||[];
  return `<div class="vbk-s"><b>${esc(t('Warum dieser Vorschlag','Why this proposal'))}</b>${VB.d.best===x.id?`<span class="ld-badge sh">★ ${esc(t('beste Empfehlung','best pick'))}</span> `:''}${esc(vbT(x.warum))}`+
    (vbRisk(x.stufe)?`<br><span class="mut">${esc(t('Risiko und Rückgängig:','Risk and undo:'))}</span> ${esc(vbRisk(x.stufe))}`:'')+
    (fs.length>1?`<ol class="vbk-cases">${fs.map(c=>`<li><button type="button" class="mlink" data-vbsel="c${esc(c.case)}">${esc(c.was?vbT(c.was):c.why||c.case)}</button></li>`).join('')}</ol>`:'')+'</div>'}
// Ideen außerhalb des Katalogs: only to read, a way to the named setting, steps to copy; the panel never applies them
function vbIdea(x){const i=x.idea;if(!VB.d.ideas||(x.stufe!=='I'&&x.stufe!=='U'))return '';
  if(!i)return x.status==='offen'?`<div class="ld-acts"><button type="button" class="b" data-vbact="idee">${esc(t('Idee holen','Get idea'))}</button></div>`:'';
  const steps=(i.steps||[]).map((s,n)=>`<div class="row" style="gap:6px;margin:4px 0"><code style="flex:1;min-width:0;overflow-wrap:anywhere">${esc(s)}</code><button type="button" class="b" data-vbicopy="${n}">${esc(t('Kopieren','Copy'))}</button></div>`).join('');
  return `<div class="ld-note"><b>${esc(t('Idee, nicht geprüft','Idea, not checked'))}</b><br>${esc(i.text)}`+
    (i.where?`<br><span class="mut">${esc(t('Einstellung:','Setting:'))}</span> ${esc(i.where)}`:'')+
    `</div>${steps}<div class="ld-acts">`+(i.good?`<span class="mut">${esc(t(`Gute Idee · ${i.count}×`,`Good idea · ${i.count}×`))}</span>`:`<button type="button" class="b" data-vbact="gut">${esc(t('Gute Idee','Good idea'))}</button>`)+
    (i.good&&i.count>=2&&!i.wish&&VB.d.issue?`<button type="button" class="b p" data-vbact="wunsch">${esc(t('Als Katalog-Wunsch melden','Report as catalog wish'))}</button>`:'')+
    (i.wish?`<span class="mut">${esc(t('Wunsch liegt unter Probleme melden.','The wish is under Reporting problems.'))}</span>`:'')+'</div>'}
async function vbPost(path,body){const m=$('vbdmsg');if(m)m.textContent=t('Einen Moment …','One moment …');
  try{const r=await (await api(path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body||{})})).json();
    if(r.view)VB.d=r.view;else if(r.cases)VB.d=r;return r}catch(e){if($('vbdmsg'))$('vbdmsg').textContent=e.message;return null}}
if($('vbbox')){
  $('vbbox').addEventListener('click',async e=>{const b=e.target.closest('button,[data-vbsel]');if(!b)return;const f=vbFind();
    if(b.dataset.vbtab){VB.tab=b.dataset.vbtab;VB.sel=null;VB.more=10;vbRender();return}
    if(b.dataset.vbmore){VB.more+=10;vbRender();return}
    if(b.dataset.vbrx==='export'){try{const j=await (await api('/api/admin/berater/regeln/export')).json();
      const a=document.createElement('a');a.href=URL.createObjectURL(new Blob([JSON.stringify(j,null,2)],{type:'application/json'}));a.download='spark-regeln.json';a.click();setTimeout(()=>URL.revokeObjectURL(a.href),2000)}catch(err){$('vbmsg').textContent=err.message}return}
    if(b.dataset.vbver!=null){if(!confirm(t('Zu dieser Version der Regeln zurück? Der jetzige Stand wird aufgehoben.','Back to this version of the rules? The current state is kept.')))return;
      try{VB.d=await (await api('/api/admin/berater/regeln/version',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({i:+b.dataset.vbver})})).json();vbRender()}catch(err){$('vbmsg').textContent=err.message}return}
    if(b.dataset.vbrule!=null){const r=(VB.d.regeln||[])[+b.dataset.vbrule];if(!r)return;
      if(!confirm(t(`Regel entfernen: ${r.name}: ${r.item}?`,`Remove rule: ${r.name}: ${r.item}?`)))return;
      try{VB.d=await (await api('/api/admin/berater/regel',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({key:r.key,name:r.name,item:r.item})})).json();vbRender()}catch(err){$('vbmsg').textContent=err.message}return}
    if(b.dataset.vbsel){VB.sel=b.dataset.vbsel;vbRender();return}
    if(b.dataset.vbback){VB.sel=null;vbRender();return}
    if(b.dataset.vbicopy!=null&&f&&f.p&&f.p.idea){copyString((f.p.idea.steps||[])[+b.dataset.vbicopy]||'',b);return}
    if(b.dataset.vbtrace&&typeof window.openTrace==='function'){window.openTrace(b.dataset.vbtrace);return}
    if(b.dataset.vbcopy!=null&&f&&f.p){copyString((f.p.change.steps||[])[+b.dataset.vbcopy]||'',b);return}
    if(b.dataset.vbcase&&f&&f.c){const body=b.dataset.vbcase==='soll'?{tool:($('vbsoll')||{}).value||''}:{};
      const r=await vbPost(`/api/admin/berater/case/${encodeURIComponent(f.c.id)}/${b.dataset.vbcase}`,body);if(r){VB.sel=null;vbRender()}return}
    if(b.dataset.vbalt!=null&&f&&f.p){const r=await vbPost(`/api/admin/berater/${encodeURIComponent(f.p.id)}/other`,{i:+b.dataset.vbalt});if(r)vbRender();return}
    if(b.dataset.vbact&&f&&f.p){const act=b.dataset.vbact,body={};
      if(act==='take'&&$('vblaut'))body.laut=$('vblaut').value;
      let r=await vbPost(`/api/admin/berater/${encodeURIComponent(f.p.id)}/${act}`,body);
      if(r&&r.prop&&r.prop.confirm){   // Stufe C: the second step, the code shown here typed back
        const code=prompt(t(`Zweiter Schritt: gib ${r.prop.confirm} ein, um „${vbT(f.p.title)}“ zu übernehmen.`,`Second step: type ${r.prop.confirm} to take "${vbT(f.p.title)}".`));
        if(!code)return;r=await vbPost(`/api/admin/berater/${encodeURIComponent(f.p.id)}/take`,Object.assign(body,{confirm:code.trim().toUpperCase()}))}
      if(r)vbRender()}});
  $('vbbox').addEventListener('change',async e=>{if(e.target.dataset.vbrx==='import'&&e.target.files[0]){vbImport(e.target.files[0]);e.target.value='';return}
    const c=e.target.closest('[data-vbmelder]');if(!c)return;
    const off=[...document.querySelectorAll('[data-vbmelder]')].filter(x=>!x.checked).map(x=>x.dataset.vbmelder);
    try{VB.d=await (await api('/api/admin/berater/melder',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({off})})).json();vbRender()}catch(err){$('vbmsg').textContent=err.message;c.checked=!c.checked}});
  $('vbbox').addEventListener('keydown',e=>{if(e.key==='Enter'&&e.target.dataset.vbsel){VB.sel=e.target.dataset.vbsel;vbRender()}});
  $('vbrun').onclick=async()=>{$('vbmsg').textContent=t('Schaue nach …','Looking …');
    try{VB.d=await (await api('/api/admin/berater/run',{method:'POST'})).json();$('vbmsg').textContent=t(`${VB.d.made||0} neue Vorschläge.`,`${VB.d.made||0} new proposals.`);vbRender()}catch(e){$('vbmsg').textContent=e.message}}}
window.loadVerb=loadVerb;
// the 👎 on a request in Zustand → Logs → Anfragen jumps to its case (logs.js rdetail)
window.openCase=id=>{VB.tab='cases';VB.sel='c'+id;VB.more=10;if(typeof goSec==='function')goSec('verb')};
