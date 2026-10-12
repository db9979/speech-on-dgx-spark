// Zustand → Verbessern (berater.py, faelle.py, admin): cases, proposals from the fixed catalog, Prüfstand, Übernehmen /
// Ablehnen / Anders, Nachkontrolle after 24 hours. Every text from the server goes through esc; the model's one short
// reason is data and shown as such. Stufe C asks for a second step (a code shown here), Umgebung only shows steps to copy.
const VB={d:null,tab:'props',sel:null,more:10};
const VBST={offen:t('offen','open'),uebernommen:t('übernommen','taken'),abgelehnt:t('abgelehnt','rejected'),zurueck:t('zurückgenommen','undone'),erledigt:t('erledigt','done')};
const VBCS={neu:t('neu','new'),vorschlag:t('Vorschlag da','proposal ready'),lokal:t('lokal behoben','fixed locally'),issue:t('als Meldung','as a report'),erledigt:t('erledigt','done'),verworfen:t('verworfen','dropped')};
const VBSTUFE={A:t('Stufe A · Regeln','Stage A · rules'),B:t('Stufe B · Feinwert','Stage B · fine value'),C:t('Stufe C · zweiter Schritt','Stage C · second step'),
  U:t('Umgebung · von Hand','Environment · by hand'),I:t('Meldung','Report'),P:t('Profil','Profile')};
const VBRES={hilft:t('hilft','helps'),gleich:t('unverändert','unchanged'),schlechter:t('schlechter','worse')};
const vbT=x=>Array.isArray(x)?t(x[0],x[1]||x[0]):x||'';
const vbWhen=s=>s?new Date(s*1000).toLocaleString([], {day:'2-digit',month:'2-digit',hour:'2-digit',minute:'2-digit'}):'';
async function loadVerb(){const box=$('vbbox');if(!box)return;
  try{VB.d=await (await api('/api/admin/berater')).json()}catch(e){$('vbmsg').textContent=e.message;return}
  vbRender()}
function vbLists(d){const p=d.props||[];return {
  cases:(d.cases||[]).filter(x=>x.status==='neu'),props:p.filter(x=>x.status==='offen'),
  check:p.filter(x=>x.status==='uebernommen'&&!x.check),done:p.filter(x=>x.status!=='offen'&&!(x.status==='uebernommen'&&!x.check)),kat:d.katalog||[]}}
function vbRender(){const d=VB.d;if(!d)return;const L=vbLists(d);
  $('vboff').hidden=d.on;$('vbmain').hidden=!d.on;
  const lv=d.live||{};$('vbsum').textContent=d.on?t(`Heute ${lv.gut||0} 👍 · ${lv.schlecht||0} 👎 · ${lv.faelle||0} neue Fälle · ${L.props.length} ${L.props.length===1?'Vorschlag':'Vorschläge'} offen`,
    `Today ${lv.gut||0} 👍 · ${lv.schlecht||0} 👎 · ${lv.faelle||0} new cases · ${L.props.length} ${L.props.length===1?'proposal':'proposals'} open`)+(d.model?'':' · '+t('ohne Sprachmodell im Heimnetz: die Regel wählt','no language model at home: the rule picks')):'';
  // the 👍 share per group (7 days): red under 75 % (from 20 ratings on that is a finding of its own)
  $('vbquote').innerHTML=(d.quote||[]).length?esc(t('👍-Quote, 7 Tage: ','👍 share, 7 days: '))+d.quote.map(q=>`<span class="${q.pct<75&&q.good+q.bad>=20?'vbqbad':''}">${esc(q.name)} ${q.pct} % (${q.good+q.bad})</span>`).join(' · '):'';
  $('vbquote').hidden=!d.on||!(d.quote||[]).length;
  const tabs=[['cases',t('Eingang','Inbox'),L.cases.length],['props',t('Vorschläge','Proposals'),L.props.length],['check',t('Nachkontrolle','Re-check'),L.check.length],
    ['done',t('Erledigt','Done'),L.done.length],['kat',t('Katalog','Catalog'),L.kat.length]];
  $('vbchips').innerHTML=tabs.map(([k,l,n])=>`<button type="button" class="ld-chip${VB.tab===k?' on':''}" data-vbtab="${k}">${esc(l)} <b>${n}</b></button>`).join('');
  const rows=L[VB.tab]||[];let html='';
  if(VB.tab==='kat')html=vbKat(d);
  else if(!rows.length)html=`<div class="ld-empty mut">${esc({cases:t('Kein neuer Fall.','No new case.'),props:t('Kein offener Vorschlag.','No open proposal.'),
    check:t('Nichts wartet auf die Nachkontrolle.','Nothing waits for the re-check.'),done:t('Noch nichts erledigt.','Nothing done yet.')}[VB.tab])}</div>`;
  else html=rows.slice(0,VB.more).map(x=>VB.tab==='cases'?vbCaseRow(x,d):vbPropRow(x)).join('')+(rows.length>VB.more?`<div class="ld-more"><button type="button" class="b" data-vbmore="1">${esc(t('Weitere zeigen','Show more'))}</button></div>`:'');
  $('vblist').innerHTML=html;vbDetail()}
function vbCaseRow(x,d){const k=(d.kinds||{})[x.kind]||[x.kind,x.kind];
  const sub=[x.title||'',x.group||'',x.tool?wzName(x.tool):'',x.code||'',x.grund?vbT((d.reasons||{})[x.grund]):''].filter(Boolean).join(' · ');
  return `<div class="ld-row${VB.sel==='c'+x.id?' on':''}" tabindex="0" data-vbsel="c${esc(x.id)}"><div class="ld-mid"><b>${esc(vbT(k))}</b><small>${esc(sub||'–')}</small></div>
    <div class="ld-right"><span class="ld-badge">${x.n}×</span><span class="ld-when">${esc(vbWhen(x.last||x.t))}</span></div></div>`}
function vbPropRow(x){const st=x.status==='uebernommen'&&x.check?VBRES[x.check.result]||x.check.result:VBST[x.status]||x.status;
  const cls=x.status==='offen'?(x.pruef&&x.pruef.ok?'read':'err'):x.check&&x.check.result==='schlechter'?'err':x.check&&x.check.result==='hilft'?'sh':'off';
  return `<div class="ld-row${VB.sel==='p'+x.id?' on':''}" tabindex="0" data-vbsel="p${esc(x.id)}"><div class="ld-mid"><b>${esc(vbT(x.title))}</b><small>${esc(x.why||'')}</small></div>
    <div class="ld-right"><span class="ld-badge ${cls}">${esc(st)}</span><span class="ld-badge off">${esc(x.stufe)}</span>${x.auto?`<span class="ld-badge due">${esc(t('Autopilot','autopilot'))}</span>`:''}</div></div>`}
function vbKat(d){const g={A:[],B:[],C:[],P:[]};for(const e of d.katalog||[])(g[e.stufe]||[]).push(e);
  return Object.entries(g).map(([s,rows])=>`<div class="ld-grp"><span>${esc(VBSTUFE[s])}</span><span>${rows.length}</span></div>`+rows.map(e=>`<div class="ld-row" style="cursor:default"><div class="ld-mid"><b>${esc(vbT(e.name))}</b><small>${esc(e.way)}${e.range?' · '+esc(e.range[0]+' … '+e.range[1]+', '+t('Schritt','step')+' '+e.range[2]):''}</small></div></div>`).join('')).join('')+
    `<div class="ld-grp"><span>${esc(t('Stufe D · nie','Stage D · never'))}</span><span>${(d.never||[]).length}</span></div>`+(d.never||[]).map(x=>`<div class="ld-row" style="cursor:default"><div class="ld-mid"><b>${esc(vbT(x))}</b></div></div>`).join('')+
    `<div class="ld-grp"><span>${esc(t('Melder','Detectors'))}</span><span></span></div>`+(d.melder||[]).map(m=>`<label class="ld-sw"><span>${esc(vbT(m.name))}</span><input type="checkbox" data-vbmelder="${esc(m.key)}"${m.on?' checked':''}></label>`).join('')}
function vbFind(){const d=VB.d;if(!d||!VB.sel)return null;const id=VB.sel.slice(1);
  return VB.sel[0]==='c'?{c:(d.cases||[]).find(x=>x.id===id)}:{p:(d.props||[]).find(x=>x.id===id)}}
function vbDetail(){const el=$('vbdetail'),f=vbFind(),box=$('vbbox');el.hidden=!f||!(f.c||f.p);box.classList.toggle('ld-sel',!el.hidden);if(el.hidden)return;
  const back=`<button type="button" class="b ld-back" data-vbback="1">← ${esc(t('Zurück','Back'))}</button>`;
  if(f.c){const x=f.c,d=VB.d;const ex=(x.examples||[]).map(e=>`<li>${esc(vbWhen(e.t))}${e.q?' · „'+esc(e.q)+'“':''}${e.trace?' · '+esc(t('Anfrage','request'))+' '+esc(e.trace):''}</li>`).join('');
    el.innerHTML=back+`<h3>${esc(vbT((d.kinds||{})[x.kind]||x.kind))}</h3><dl class="ld-facts">`+
      [[t('Zustand','State'),VBCS[x.status]||x.status],[t('Wie oft','How often'),x.n+'×'+(x.who?' · '+x.who+' '+t('Personen','people'):'')],[t('Gruppe','Group'),x.group],[t('Werkzeug','Tool'),x.tool?wzFull(x.tool):x.tool],
       [t('Fehler','Error'),x.code],[t('Grund','Reason'),x.grund?vbT((d.reasons||{})[x.grund]):''],[t('Befund','Finding'),x.title],[t('Seit','Since'),vbWhen(x.t)]].filter(r=>r[1]).map(r=>`<dt>${esc(r[0])}</dt><dd>${esc(r[1])}</dd>`).join('')+'</dl>'+
      (ex?`<div class="mut">${esc(t('Beispiele (Fragen nur mit Zustimmung):','Examples (questions only with consent):'))}</div><ul class="bghist">${ex}</ul>`:'')+
      ((x.notes||[]).length?`<div class="ld-note">${(x.notes||[]).map(n=>'„'+esc(n)+'“').join('<br>')}</div>`:'')+
      `<div class="ld-acts"><button type="button" class="b p" data-vbcase="propose">${esc(t('Jetzt Vorschlag machen','Make a proposal now'))}</button><button type="button" class="b danger" data-vbcase="drop">${esc(t('Verwerfen','Drop'))}</button></div><div class="ld-note mut" id="vbdmsg"></div>`;return}
  const x=f.p,pr=x.pruef||{};
  const ch=x.change||{},facts=[[t('Stufe','Stage'),VBSTUFE[x.stufe]||x.stufe],[t('Fall','Case'),x.why],[t('Zustand','State'),VBST[x.status]||x.status],[t('Seit','Since'),vbWhen(x.t)]];
  if('old' in ch)facts.push([t('Jetzt','Now'),String(ch.old)],[t('Neu','New'),String(ch.new)]);
  if(x.check)facts.push([t('Nachkontrolle','Re-check'),(VBRES[x.check.result]||x.check.result)+' · '+t(`${x.check.again} neue Meldungen`,`${x.check.again} new reports`)]);
  else if(x.check_at&&x.status==='uebernommen')facts.push([t('Nachkontrolle','Re-check'),vbWhen(x.check_at)]);
  let acts='';
  if(x.status==='offen'){
    if(x.stufe==='U')acts=`<button type="button" class="b p" data-vbact="done">${esc(t('Erledigt, nachkontrollieren','Done, re-check'))}</button>`;
    else if(x.stufe==='I')acts=VB.d.issue?`<button type="button" class="b p" data-vbact="issue">${esc(t('Als Meldung vorbereiten','Prepare as a report'))}</button>`:`<span class="mut">${esc(t('Dafür unter Funktionen „Fälle als Meldung vorbereiten“ einschalten.','For this switch on "Prepare cases as reports" under Features.'))}</span>`;
    else acts=`<button type="button" class="b p" data-vbact="take"${pr.ok?'':' disabled'}>${esc(t('Übernehmen','Take'))}</button>`;
    acts+=`<button type="button" class="b" data-vbact="reject">${esc(t('Ablehnen','Reject'))}</button>`}
  else if(x.status==='uebernommen'&&x.stufe!=='U')acts=`<button type="button" class="b" data-vbact="undo">${esc(t('Zurücknehmen','Undo'))}</button>`;
  const steps=x.stufe==='U'?(ch.steps||[]).map((s,i)=>`<div class="row" style="gap:6px;margin:4px 0"><code style="flex:1;min-width:0;overflow-wrap:anywhere">${esc(s)}</code><button type="button" class="b" data-vbcopy="${i}">${esc(t('Kopieren','Copy'))}</button></div>`).join(''):'';
  const laut=x.key==='aussprache'&&x.status==='offen'?`<label>${esc(t('So soll es klingen','How it should sound'))} („${esc(ch.word||'')}“)</label><input id="vblaut" maxlength="40" value="${esc(ch.laut||'')}" autocomplete="off">`:'';
  const alts=x.status==='offen'&&(x.alts||[]).length?`<details class="adv"><summary>${esc(t('Anders','Other'))} (${x.alts.length})</summary>`+x.alts.map((a,i)=>`<div class="ld-sw"><span>${esc(vbT(a.title))}${a.pruef&&!a.pruef.ok?' · <span class="danger">'+esc(t('rot','red'))+'</span>':''}</span><button type="button" class="b" data-vbalt="${i}">${esc(t('Diesen','This one'))}</button></div>`).join('')+'</details>':'';
  const idea=vbIdea(x);
  el.innerHTML=back+`<h3>${esc(vbT(x.title))}</h3><dl class="ld-facts">${facts.filter(r=>r[1]!=null&&r[1]!=='').map(r=>`<dt>${esc(r[0])}</dt><dd>${esc(r[1])}</dd>`).join('')}</dl>`+
    (x.model?`<div class="ld-note"><span class="mut">${esc(t('Sprachmodell:','Language model:'))}</span> ${esc(x.model)}</div>`:'')+steps+laut+
    `<div class="ld-note"><b class="${pr.ok?'':'danger'}">${esc(pr.ok?t('Prüfstand grün','Test bench green'):t('Prüfstand rot','Test bench red'))}</b>${(pr.red||[]).map(r=>'<br><span class="danger">'+esc(r)+'</span>').join('')}${(pr.notes||[]).map(r=>'<br><span class="mut">'+esc(r)+'</span>').join('')}${(pr.flips||[]).slice(0,5).map(f=>'<br><span class="mut">„'+esc(f.q)+'“ → '+esc(f.got||t('unklar','unclear'))+'</span>').join('')}</div>`+
    idea+alts+`<div class="ld-acts">${acts}</div><div class="ld-note" id="vbdmsg"></div>`}
// Ideen außerhalb des Katalogs: only to read, a way to the named setting, steps to copy; the panel never applies them
function vbIdea(x){const i=x.idea;if(!VB.d.ideas||(x.stufe!=='I'&&x.stufe!=='U'))return '';
  if(!i)return x.status==='offen'?`<div class="ld-acts"><button type="button" class="b" data-vbact="idee">${esc(t('Idee holen','Get idea'))}</button></div>`:'';
  const el=i.setting?document.getElementById(i.setting):null;
  const steps=(i.steps||[]).map((s,n)=>`<div class="row" style="gap:6px;margin:4px 0"><code style="flex:1;min-width:0;overflow-wrap:anywhere">${esc(s)}</code><button type="button" class="b" data-vbicopy="${n}">${esc(t('Kopieren','Copy'))}</button></div>`).join('');
  return `<div class="ld-note"><b>${esc(t('Idee, nicht geprüft','Idea, not checked'))}</b><br>${esc(i.text)}`+
    (i.setting?`<br><span class="mut">${esc(t('Einstellung:','Setting:'))}</span> <code>${esc(i.setting)}</code> `+(el?`<button type="button" class="b" data-vbgo="1">${esc(t('Zur Einstellung','To the setting'))}</button>`:`<span class="mut">${esc(t('(auf keiner Seite)','(on no page)'))}</span>`):'')+
    `</div>${steps}<div class="ld-acts">`+(i.good?`<span class="mut">${esc(t(`Gute Idee · ${i.count}×`,`Good idea · ${i.count}×`))}</span>`:`<button type="button" class="b" data-vbact="gut">${esc(t('Gute Idee','Good idea'))}</button>`)+
    (i.good&&i.count>=2&&!i.wish&&VB.d.issue?`<button type="button" class="b p" data-vbact="wunsch">${esc(t('Als Katalog-Wunsch melden','Report as catalog wish'))}</button>`:'')+
    (i.wish?`<span class="mut">${esc(t('Wunsch liegt unter Probleme melden.','The wish is under Reporting problems.'))}</span>`:'')+'</div>'}
function vbGoSetting(id){const el=document.getElementById(id),pane=el&&el.closest('.pane');if(!pane)return;
  const p=pane.id.slice(5);if(typeof goCfg==='function')goCfg(p);if(typeof cfgGo==='function')cfgGo({p,el:el.closest('.setrow')||el})}
async function vbPost(path,body){const m=$('vbdmsg');if(m)m.textContent=t('Einen Moment …','One moment …');
  try{const r=await (await api(path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body||{})})).json();
    if(r.view)VB.d=r.view;else if(r.cases)VB.d=r;return r}catch(e){if($('vbdmsg'))$('vbdmsg').textContent=e.message;return null}}
if($('vbbox')){
  $('vbbox').addEventListener('click',async e=>{const b=e.target.closest('button,[data-vbsel]');if(!b)return;const f=vbFind();
    if(b.dataset.vbtab){VB.tab=b.dataset.vbtab;VB.sel=null;VB.more=10;vbRender();return}
    if(b.dataset.vbmore){VB.more+=10;vbRender();return}
    if(b.dataset.vbsel){VB.sel=b.dataset.vbsel;vbRender();return}
    if(b.dataset.vbback){VB.sel=null;vbRender();return}
    if(b.dataset.vbicopy!=null&&f&&f.p&&f.p.idea){copyString((f.p.idea.steps||[])[+b.dataset.vbicopy]||'',b);return}
    if(b.dataset.vbgo&&f&&f.p&&f.p.idea){vbGoSetting(f.p.idea.setting);return}
    if(b.dataset.vbcopy!=null&&f&&f.p){copyString((f.p.change.steps||[])[+b.dataset.vbcopy]||'',b);return}
    if(b.dataset.vbcase&&f&&f.c){const r=await vbPost(`/api/admin/berater/case/${encodeURIComponent(f.c.id)}/${b.dataset.vbcase}`);if(r){VB.sel=null;vbRender()}return}
    if(b.dataset.vbalt!=null&&f&&f.p){const r=await vbPost(`/api/admin/berater/${encodeURIComponent(f.p.id)}/other`,{i:+b.dataset.vbalt});if(r)vbRender();return}
    if(b.dataset.vbact&&f&&f.p){const act=b.dataset.vbact,body={};
      if(act==='take'&&$('vblaut'))body.laut=$('vblaut').value;
      let r=await vbPost(`/api/admin/berater/${encodeURIComponent(f.p.id)}/${act}`,body);
      if(r&&r.prop&&r.prop.confirm){   // Stufe C: the second step, the code shown here typed back
        const code=prompt(t(`Zweiter Schritt: gib ${r.prop.confirm} ein, um „${vbT(f.p.title)}“ zu übernehmen.`,`Second step: type ${r.prop.confirm} to take "${vbT(f.p.title)}".`));
        if(!code)return;r=await vbPost(`/api/admin/berater/${encodeURIComponent(f.p.id)}/take`,Object.assign(body,{confirm:code.trim().toUpperCase()}))}
      if(r)vbRender()}});
  $('vbbox').addEventListener('change',async e=>{const c=e.target.closest('[data-vbmelder]');if(!c)return;
    const off=[...document.querySelectorAll('[data-vbmelder]')].filter(x=>!x.checked).map(x=>x.dataset.vbmelder);
    try{VB.d=await (await api('/api/admin/berater/melder',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({off})})).json();vbRender()}catch(err){$('vbmsg').textContent=err.message;c.checked=!c.checked}});
  $('vbbox').addEventListener('keydown',e=>{if(e.key==='Enter'&&e.target.dataset.vbsel){VB.sel=e.target.dataset.vbsel;vbRender()}});
  $('vbrun').onclick=async()=>{$('vbmsg').textContent=t('Schaue nach …','Looking …');
    try{VB.d=await (await api('/api/admin/berater/run',{method:'POST'})).json();$('vbmsg').textContent=t(`${VB.d.made||0} neue Vorschläge.`,`${VB.d.made||0} new proposals.`);vbRender()}catch(e){$('vbmsg').textContent=e.message}}}
window.loadVerb=loadVerb;
