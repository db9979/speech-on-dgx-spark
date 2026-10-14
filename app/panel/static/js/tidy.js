// "Ich" → E-Mail, part "Postfach aufräumen": inbox tidying per mailbox (see tidy.py). Moves only, never deletes; drafts only.
let TIDY_ON=false,TIDY=null;
// the modes per mailbox: short label on the segment, name as tooltip, and a visible line what the Spark does (tidy._run)
const TMODES=[['off',t('Aus','Off'),t('Aus','Off'),t('Der Spark prüft dieses Postfach nicht und verschiebt nichts.','The Spark does not check this mailbox and moves nothing.')],
  ['preview',t('Vorschau','Preview'),t('Vorschau (verschiebt nichts)','Preview (moves nothing)'),t('Der Spark prüft neue Mails und schlägt nur vor: Vorschläge stehen unter „Vorschau“, Unklares unter „Fragen“. Verschoben wird erst, wenn du es bestätigst.','The Spark checks new mail and only proposes: proposals are under "Preview", unclear mail under "Questions". Nothing moves until you confirm it.')],
  ['safe',t('Sicher','Safe'),t('Sicher automatisch','Safe automatic'),t('Der Spark verschiebt nur Eindeutiges: was deine Regeln sagen oder Kopfzeilen belegen (Abmelde-Link, Verteiler, soziales Netzwerk, automatischer Absender). Was nur das Sprachmodell vermutet, kommt in die Vorschau; Ordner auf „erst nachfragen“ fragt er vorher.','The Spark moves only clear cases: what your rules say or headers prove (unsubscribe link, mailing list, social network, automatic sender). What only the language model guesses goes to the preview; for folders set to "ask first" it asks.')],
  ['auto',t('Voll','Full'),t('Voll automatisch','Fully automatic'),t('Wie „Sicher“, und zusätzlich verschiebt der Spark, was das Sprachmodell zu mindestens 85 % sicher einordnet. Ist es unsicherer, fragt er nach.','Like "Safe", and the Spark also moves what the language model files with at least 85 % certainty. When it is less sure, it asks.')]];
const tmodeSay=k=>(TMODES.find(m=>m[0]===k)||TMODES[0])[3];
const tidyMsg=(x,err)=>{const m=$('tidymsg');if(m){m.textContent=x||'';m.className='fh'+(err?' err':'')}};
const tdate=s=>new Date(s*1000).toLocaleString(L==='en'?'en-GB':'de-DE',{day:'2-digit',month:'2-digit',hour:'2-digit',minute:'2-digit'});
// through api(): settings (PUT) need the current code when the profile has the second step (stufen.py, 428); api() asks
// for it in the one code window and sends again. With a bare fetch the 428 only ended as a grey line (V01.0.533).
async function tidyCall(path,body,method='POST'){let r;
  try{r=await api('/api/profile/tidy'+path,{method,headers:{'Content-Type':'application/json'},body:JSON.stringify(body||{})})}catch(e){tidyMsg(e.message,true);return null}
  const d=await r.json().catch(()=>({}));TIDY=d;tidyRender();return d}
function catSel(id,val,keep=true){return `<select id="${id}">${Object.entries(TIDY.cats).map(([k,v])=>`<option value="${k}"${k===val?' selected':''}>${esc(TIDY.folders[k]||v)}</option>`).join('')}${keep?`<option value="keep"${val==='keep'?' selected':''}>${t('Posteingang','Inbox')}</option>`:''}</select>`}
async function showMailTidy(){const box=$('mailtidy');if(!box)return;if(!PROFILE||!TIDY_ON){box.innerHTML='';return}
  try{TIDY=await (await api('/api/profile/tidy')).json()}catch{box.innerHTML='';return}tidyRender()}
// Since the Ich pages were tidied up (ich-aufraeumen/plan.md, Paket 2): a card per mailbox (mode as segments, "Jetzt
// prüfen", rare things in "⋯"), then tabs with counts instead of six arrows. A question is answered with one tap on a
// folder, "Immer so" makes it a rule; the preview is grouped by the folder it would go to.
const tcat=k=>k==='keep'?t('Posteingang','Inbox'):(TIDY.folders[k]||TIDY.cats[k]||k);
const TSHOW=new Set();let TQ='';
// a new own folder: the same fixed rule as tidy.check_new_name (the panel checks again, this only answers sooner)
const TNAME=/^[\p{L}\p{N}][\p{L}\p{N}_ .,&()+'-]{0,39}$/u;
const tnameBad=v=>!TNAME.test(v)?t('Ordnername: 1 bis 40 Buchstaben oder Ziffern (auch Leerzeichen . , & ( ) + \' -), kein / und keine anderen Zeichen.','Folder name: 1 to 40 letters or digits (also space . , & ( ) + \' -), no / or other marks.'):'';
// "＋ Neuer Ordner" in a question: a name field; the folder is made only after "Anlegen", then the mail moves there
function tidyNewFolder(q,chips,always){const E=icEl,f=E('div','rowin ic-newf');f.style.marginTop='8px';
  const inp=E('input');inp.maxLength=40;inp.autocapitalize='off';inp.autocomplete='off';inp.placeholder=t('Name des neuen Ordners','Name of the new folder');inp.setAttribute('aria-label',t('Neuer Ordner','New folder'));
  const path=E('small','fh',''),ok=E('button','b p',t('Anlegen und einsortieren','Create and file')),no=E('button','b',t('Abbrechen','Cancel'));ok.type=no.type='button';
  const show=()=>{const v=inp.value.trim();path.textContent=v?'→ '+(TIDY.root?TIDY.root+'/':'')+v:''};inp.oninput=show;
  no.onclick=()=>{f.remove();chips.querySelectorAll('button').forEach(b=>b.disabled=false)};
  const go=async()=>{const v=inp.value.trim(),bad=tnameBad(v);if(bad){tidyMsg(bad,true);inp.focus();return}ok.disabled=no.disabled=true;
    const r=await tidyCall('/answer',{id:q.id,new:v,always:always()});if(r)tidyMsg(t('Ordner angelegt.','Folder created.')+(r.report.moved?' '+r.report.moved+t(' verschoben.',' moved.'):''));else ok.disabled=no.disabled=false};
  ok.onclick=go;inp.onkeydown=e=>{if(e.key==='Enter')go();if(e.key==='Escape')no.onclick()};
  f.append(inp,ok,no);chips.after(f);f.after(path);chips.querySelectorAll('button').forEach(b=>b.disabled=true);inp.focus()}
function tidyMore(list,key,rows,n){const shown=TSHOW.has(key)?rows:rows.slice(0,n);shown.forEach(r=>list.appendChild(r));
  if(rows.length>shown.length){const b=icEl('button','ic-more2',t(`Weitere ${rows.length-shown.length} zeigen`,`Show ${rows.length-shown.length} more`));b.type='button';
    b.onclick=()=>{TSHOW.add(key);b.remove();rows.slice(n).forEach(r=>list.appendChild(r))};list.appendChild(b)}return list}
function tidyRender(){const d=TIDY,box=$('mailtidy'),E=icEl;
  if(!d.accounts.length){box.innerHTML='';return}
  box.textContent='';box.appendChild(E('h3','sec',t('Postfach aufräumen','Inbox tidying')));
  box.appendChild(E('div','intro',(d.root?t('Der Spark sortiert Werbung, Newsletter und Ähnliches in Ordner unter „','The Spark sorts advertising, newsletters and the like into folders under "')+d.root+t('/“.','/".'):t('Der Spark sortiert Werbung, Newsletter und Ähnliches in eigene Ordner.','The Spark sorts advertising, newsletters and the like into folders of their own.'))+' '+t('Er verschiebt nur, er löscht nie. Leute, denen du geschrieben hast, und Anmelde- oder Sicherheitsmails bleiben immer im Posteingang. Unklares fragt er nach. Jede Verschiebung lässt sich 30 Tage lang zurückholen.','It only moves, never deletes. People you wrote to and sign-in or security mails always stay in the inbox. It asks about unclear mail. Every move can be undone for 30 days.')));
  for(const a of d.accounts){const parts=[];
    if(a.mode==='preview'&&a.since)parts.push(t('Vorschau seit ','Preview since ')+tdate(a.since)+(Date.now()/1000-a.since>7*86400?t(' – eine Woche ist um, passt es? Dann „Sicher“.',' – a week is over; if it fits, switch to "Safe".'):''));
    if(a.last_run)parts.push(t('zuletzt ','last ')+tdate(a.last_run));if(a.mode!=='off')parts.push(t(`prüft alle ${d.every} Minuten`,`checks every ${d.every} minutes`));
    if(a.error)parts.push('⚠ '+a.error);if(a.stopped)parts.push('⚠ '+t('angehalten: ','stopped: ')+a.stopped);
    const seg=E('div','ic-seg');seg.setAttribute('role','group');seg.setAttribute('aria-label',t('Aufräumen für ','Tidying for ')+a.name);
    // a visible line under the card says what the chosen mode does; pointing at or focusing a segment shows that one's line
    const say=E('div','fh ic-modesay',tmodeSay(a.mode));say.dataset.modesay=a.id;say.id='tmode-'+a.id;
    for(const [k,short,name] of TMODES){const b=E('button',k===a.mode?'on':'',short);
      b.type='button';b.title=name;b.dataset.mode=a.id;b.dataset.v=k;b.setAttribute('aria-pressed',k===a.mode?'true':'false');b.setAttribute('aria-describedby',say.id);
      b.onmouseenter=b.onfocus=()=>{say.textContent=tmodeSay(k)};b.onmouseleave=b.onblur=()=>{say.textContent=tmodeSay(a.mode)};
      b.onclick=()=>{if(k!==a.mode)tidyCall('',{accounts:{[a.id]:{mode:k}}},'PUT')};seg.appendChild(b)}
    const run=E('button','b',t('Jetzt prüfen','Check now'));run.type='button';run.dataset.run=a.id;
    run.onclick=async()=>{tidyMsg(t('Prüfe …','Checking …'));const r0=await tidyCall('/run',{aid:a.id});
      if(r0&&r0.report){const r=r0.report;tidyMsg(r.first?t('Gestartet: ab jetzt werden neue Mails sortiert.','Started: new mail is sorted from now on.'):r.error?'⚠ '+r.error:`${r.new||0} ${t('neu','new')}, ${r.moved||0} ${t('verschoben','moved')}, ${r.preview||0} ${t('in der Vorschau','in the preview')}, ${r.asked||0} ${t('Fragen','questions')}`+(r.waiting?`, ${r.waiting} ${t('warten aufs Modell','wait for the model')}`:''),!!r.error)}};
    const card=icCard('mail',a.name,parts.join(' · '),[seg,run],[
      {label:t('Altlasten der letzten 90 Tage ansehen','Look at old mail of the last 90 days'),act:async()=>{tidyMsg(t('Sehe mir die letzten 90 Tage an …','Looking at the last 90 days …'));if(await tidyCall('/backlog',{aid:a.id}))tidyMsg('')}},
      {label:a.drafts?t('Antwort-Entwürfe nicht mehr erlauben','Stop allowing reply drafts'):t('Antwort-Entwürfe erlauben (nie senden)','Allow reply drafts (never sent)'),act:()=>tidyCall('',{accounts:{[a.id]:{drafts:!a.drafts}}},'PUT')}]);card.appendChild(say);box.appendChild(card)}
  const msg=E('div','fh');msg.id='tidymsg';box.appendChild(msg);
  if(d.backlog){const bl=d.backlog,go=E('button','b p',t('Verschieben','Move')),drop=E('button','b',t('Verwerfen','Discard'));go.type=drop.type='button';go.disabled=!bl.moves;
    go.onclick=async()=>{if(!confirm(t('Jetzt verschieben? Es wird nichts gelöscht, und alles lässt sich zurückholen.','Move now? Nothing is deleted, and everything can be brought back.')))return;tidyMsg(t('Verschiebe …','Moving …'));const r=await tidyCall('/backlog',{apply:true});if(r)tidyMsg(r.report.moved+t(' Mails verschoben.',' mails moved.'))};
    drop.onclick=()=>tidyCall('/backlog',{drop:true});
    box.appendChild(icNote(t('Altlasten-Vorschlag','Old mail proposal'),t('Von ','Of ')+bl.total+t(' Mails der letzten ',' mails of the last ')+bl.days+t(' Tage würde ich ',' days I would move ')+bl.moves+t(' verschieben: ',': ')+Object.entries(bl.by).map(([k,n])=>(d.folders[k]||k)+' '+n).join(', ')+(bl.top.length?' · '+bl.top.map(([s,n])=>s+' ('+n+')').join(', '):''),[go,drop]))}
  box.appendChild(icTabs('tidy',[
    {k:'q',label:t('Fragen','Questions'),n:d.questions.length,hot:d.questions.length>0,body:tidyQuestions},
    {k:'p',label:t('Vorschau','Preview'),n:d.preview.length,hot:d.preview.length>0,body:tidyPreview},
    {k:'log',label:t('Verlauf','History'),n:'',body:tidyLog},
    {k:'r',label:t('Regeln','Rules'),n:d.rules.length,body:tidyRules},
    {k:'f',label:t('Ordner und Ausnahmen','Folders and exceptions'),n:'',body:tidyFolders}]))}
function tidyQuestions(){const d=TIDY,E=icEl,w=E('div');
  if(!d.questions.length){w.appendChild(icEmpty(t('Keine offenen Fragen.','No open questions.')));return w}
  w.appendChild(E('div','fh',t('Ein Tipp ordnet zu. Bei „Immer so“ merkt sich der Spark den Absender als Regel.','One tap files it. With "Always like this" the Spark keeps the sender as a rule.')));
  for(const q of d.questions){const c=E('div','ic-q');c.dataset.q=q.id;const h=E('div','ic-qh');h.append(E('b','',q.name||q.sender),E('small','',`${q.sender} · ${q.uids.length} ${t('Mail(s)','mail(s)')}`));
    h.lastChild.title=q.sender;c.appendChild(h);const subj=(q.subjects||[]).slice(-2).join(' · ');if(subj)c.appendChild(E('q','',subj));
    let always=true;const chips=E('div','ic-chips');
    for(const k of [...Object.keys(d.cats),'keep']){const ch=icChip(tcat(k),false,async()=>{chips.querySelectorAll('button').forEach(b=>b.disabled=true);
        const r=await tidyCall('/answer',{id:q.id,cat:k,always});if(r)tidyMsg(t('Gemerkt.','Noted.')+(r.report.moved?' '+r.report.moved+t(' verschoben.',' moved.'):''));else chips.querySelectorAll('button').forEach(b=>b.disabled=false)},k===q.guess?'guess':'');
      ch.dataset.cat=k;if(k===q.guess)ch.appendChild(E('em','',t('vermutet','guessed')));chips.appendChild(ch)}
    const nf=icChip('＋ '+t('Neuer Ordner','New folder'),false,()=>{if(!c.querySelector('.ic-newf'))tidyNewFolder(q,chips,()=>always)},'new');nf.dataset.cat='new';chips.appendChild(nf);
    c.appendChild(chips);const f=E('div','ic-qf');const cb=icCheck(true,t('Immer so für diesen Absender','Always like this for this sender'),b=>{always=!always;
      b.classList.toggle('on',always);b.setAttribute('aria-checked',always?'true':'false');b.textContent='';if(always)b.appendChild(icSvg('check',12))});
    f.append(cb,E('span','',t('Immer so für diesen Absender (wird eine Regel)','Always like this for this sender (becomes a rule)')));c.appendChild(f);w.appendChild(c)}
  return w}
function tidyPreview(){const d=TIDY,E=icEl,w=E('div');
  if(!d.preview.length){w.appendChild(icEmpty(t('Nichts in der Vorschau.','Nothing in the preview.')));return w}
  const tools=E('div','ic-tools'),all=E('button','b p',t(`Alle ${d.preview.length} verschieben`,`Move all ${d.preview.length}`));all.type='button';all.id='pokall';
  all.onclick=()=>{if(confirm(t('Alle Vorschläge der Vorschau verschieben?','Move every proposal of the preview?')))tidyCall('/preview',{ok:d.preview.map(p=>p.id)})};
  const out=E('div');tools.append(icSearch(t('In der Vorschau suchen …','Search the preview …'),TQ,v=>{TQ=v;draw()}),all);w.append(tools,out);
  const no=p=>tidyCall('/preview',{no:p.id,protect:confirm(t('Diesen Absender künftig immer im Posteingang lassen?','Always keep this sender in the inbox from now on?'))});
  function draw(){out.textContent='';const q=TQ.toLowerCase(),by={};
    for(const p of d.preview)if(!q||(p.name+' '+p.sender+' '+p.subject+' '+p.folder).toLowerCase().includes(q))(by[p.folder]=by[p.folder]||[]).push(p);
    const keys=Object.keys(by);if(!keys.length){out.appendChild(icEmpty(t('Nichts gefunden.','Nothing found.')));return}
    for(const f of keys){const ps=by[f];out.appendChild(icGroup('→ '+f,ps.length,icLink(t(`Alle ${ps.length} verschieben`,`Move all ${ps.length}`),()=>tidyCall('/preview',{ok:ps.map(p=>p.id)}))));
      out.appendChild(tidyMore(icList([]),'p:'+f,ps.map(p=>{const r=icRow(`${p.name||p.sender}: ${p.subject}`,p.why,[icBtn('check',t('Verschieben','Move'),()=>tidyCall('/preview',{ok:[p.id]}),'ok'),icBtn('x',t('Nicht verschieben','Do not move'),()=>no(p),'no')],null,true);r.dataset.pv=p.id;return r}),5))}}
  draw();return w}
function tidyLog(){const d=TIDY,E=icEl;if(!d.log.length)return icEmpty(t('Noch nichts verschoben.','Nothing moved yet.'));
  const rows=d.log.slice(0,60).map(x=>icRow(`${x.name||x.sender}: ${x.subject}`,`${tdate(x.t)} → ${x.folder} · ${x.why}`+(x.undone?' · '+t('zurückgeholt','brought back'):'')+(x.returned?' · '+t('von dir zurückgelegt','moved back by you'):''),
    x.undone?[]:[icBtn('back',t('Zurückholen','Bring back'),()=>tidyCall('/undo',{ids:[x.id],protect:confirm(t('Diesen Absender künftig immer im Posteingang lassen?','Always keep this sender in the inbox from now on?'))}))],null,true));
  const w=E('div');w.appendChild(E('div','fh',t('Was der Spark in den letzten 30 Tagen verschoben hat; ↩ holt eine Mail zurück.','What the Spark moved in the last 30 days; ↩ brings a mail back.')));w.appendChild(tidyMore(icList([]),'log',rows,10));return w}
function tidyRules(){const d=TIDY,E=icEl,w=E('div');
  w.appendChild(d.rules.length?icList(d.rules.slice().reverse().map(r=>icRow(`${r.match} → ${tcat(r.cat)}`,'',[icBtn('trash',t('Regel löschen','Delete rule'),()=>tidyCall('/rules/'+encodeURIComponent(r.id),{},'DELETE'))]))):icEmpty(t('Noch keine Regeln.','No rules yet.')));
  const add=E('div','rowin');add.style.marginTop='10px';add.innerHTML=`<input id="rmatch" placeholder="${esc(t('absender@firma.de oder firma.de','sender@company.com or company.com'))}" autocapitalize="off" autocomplete="off" aria-label="${esc(t('Absender oder Domain','Sender or domain'))}">${catSel('rcat','werbung')}<button class="b" type="button" id="radd">${esc(t('Hinzufügen','Add'))}</button>`;
  add.querySelector('#radd').onclick=()=>tidyCall('/rules',{match:add.querySelector('#rmatch').value,cat:add.querySelector('#rcat').value});w.appendChild(add);return w}
function tidyFolders(){const d=TIDY,E=icEl,w=E('div','ic-form');const fpath=n=>(d.root?d.root+'/':'')+n;
  w.innerHTML=`<h4>${esc(t('Hauptordner','Main folder'))}</h4><div class="rowin"><input id="tidyroot" value="${esc(d.root)}" maxlength="40" autocapitalize="off" autocomplete="off" aria-label="${esc(t('Hauptordner','Main folder'))}"><button class="b" type="button" id="tidyrootsave">${esc(t('Umbenennen','Rename'))}</button></div>
    <div class="fh">${esc(t('Darunter liegen die Ordner. Umbenennen benennt den Ordner auch im Postfach um, die Mails darin wandern mit. Leer = Ordner direkt oben.','The folders sit below it. Renaming also renames the folder in the mailbox; the mail in it moves along. Empty = folders at the top.'))}</div>
    <div class="setrow"><div class="lbl"><b>${esc(t('Wie oft prüfen','How often to check'))}</b><span>${esc(t('Nur neue Mails seit dem letzten Mal.','Only new mail since the last time.'))}</span></div><select id="tidyevery">${[5,15,60].map(m=>`<option value="${m}"${d.every===m?' selected':''}>${m} ${esc(t('Minuten','minutes'))}</option>`).join('')}</select></div>
    <h4>${esc(t('Ordner und was verschoben wird','Folders and what is moved'))}</h4>
    ${Object.entries(d.cats).map(([k,v])=>`<div class="setrow"><div class="lbl"><input data-fname="${k}" value="${esc(d.folders[k]||v)}" style="max-width:180px" aria-label="${esc(v)}"><span>${esc(fpath(d.folders[k]||v))}</span></div>${(d.own||[]).includes(k)?`<button class="b" type="button" data-drop="${esc(k)}" title="${esc(t('Aus der Liste nehmen','Take off the list'))}">${esc(t('Entfernen','Remove'))}</button>`:''}
      <select data-act="${k}">${[['move',t('verschieben','move')],['ask',t('erst nachfragen','ask first')],['keep',t('im Posteingang lassen','keep in inbox')]].map(([a,l])=>`<option value="${a}"${d.actions[k]===a?' selected':''}>${esc(l)}</option>`).join('')}</select></div>`).join('')}
    <div class="row"><button class="b" type="button" id="tactsave">${esc(t('Speichern','Save'))}</button></div>
    <h4>${esc(t('Eigener Ordner','Own folder'))}</h4><div class="rowin"><input id="tnewf" maxlength="40" autocapitalize="off" autocomplete="off" placeholder="${esc(t('Name des neuen Ordners','Name of the new folder'))}" aria-label="${esc(t('Neuer Ordner','New folder'))}"><button class="b" type="button" id="tnewfadd">${esc(t('Hinzufügen','Add'))}</button></div>
    <div class="fh">${esc(t('Eigene Ordner füllt nur, was du zuordnest (Fragen, Regeln); der Spark legt sie im Postfach an, sobald die erste Mail hineinkommt. Entfernen nimmt sie nur aus der Liste, Ordner und Mails bleiben.','Own folders get only what you assign (questions, rules); the Spark creates them in the mailbox with the first mail. Remove only takes them off the list; folder and mail stay.'))}</div>
    <h4>${esc(t('Immer im Posteingang lassen','Always keep in inbox'))}</h4><textarea id="tprot" rows="3" placeholder="${esc(t('Eine Adresse oder Domain pro Zeile','One address or domain per line'))}">${esc(d.protected.join('\n'))}</textarea>
    <div class="row"><button class="b" type="button" id="tprotsave">${esc(t('Speichern','Save'))}</button></div>`;
  const q=s=>w.querySelector(s);
  q('#tidyrootsave').onclick=async()=>{const v=q('#tidyroot').value.trim();if(v===d.root)return;
    if(!confirm(t('Den Hauptordner in allen Postfächern umbenennen? Die Mails darin wandern mit, es wird nichts gelöscht.','Rename the main folder in every mailbox? The mail in it moves along; nothing is deleted.')))return;
    tidyMsg(t('Benenne um …','Renaming …'));const r=await tidyCall('',{root:v},'PUT');if(r)tidyRenamed(r)};
  q('#tnewfadd').onclick=()=>{const v=q('#tnewf').value.trim(),bad=tnameBad(v);if(bad){tidyMsg(bad,true);return}tidyCall('',{add_folder:v},'PUT')};
  w.querySelectorAll('[data-drop]').forEach(b=>b.onclick=()=>{const k=b.dataset.drop;
    if(confirm(t('„','"')+(d.folders[k]||k)+t('“ aus der Liste nehmen? Die Regeln dafür werden gelöscht; der Ordner und die Mails darin bleiben im Postfach.','" off the list? Its rules are deleted; the folder and the mail in it stay in the mailbox.')))tidyCall('',{remove_folder:k},'PUT')});
  q('#tidyevery').onchange=()=>tidyCall('',{every:+q('#tidyevery').value},'PUT');
  q('#tprotsave').onclick=()=>tidyCall('',{protected:q('#tprot').value.split(/[\n,]/).map(x=>x.trim()).filter(Boolean)},'PUT');
  q('#tactsave').onclick=async()=>{const actions={},folders={};w.querySelectorAll('[data-act]').forEach(s=>actions[s.dataset.act]=s.value);w.querySelectorAll('[data-fname]').forEach(i=>folders[i.dataset.fname]=i.value);const r=await tidyCall('',{actions,folders},'PUT');if(r)tidyRenamed(r)};
  return w}
function tidyRenamed(r){const bad=(r.renamed||[]).filter(x=>!x.ok);
  tidyMsg(bad.length?bad.map(x=>'⚠ '+x.account+': '+x.error).join(' · ')+t(' – dort bleibt der alte Ordner; neue Mails gehen in den neuen.',' – the old folder stays there; new mail goes to the new one.'):(r.renamed?t('Umbenannt.','Renamed.'):t('Gespeichert.','Saved.')),!!bad.length)}
