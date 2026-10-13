// "Ich" → Aufträge and the admin's part (agent.py, beobachten.py, mcp.py). Plan „Eigene Aufgaben“: one list of everything
// the Spark does again and again for the profile (watches, scheduled jobs, repeating reminders, smart home rules, mail
// senders, routines) as "Liste mit Detailbereich" (ld-…): a row each with its on/off switch, a tap opens the details
// (change, check now, history, delete); narrow, the details become a page of their own. Off until the admin allows it.
let AGENT_ON=false;
const AG_ST={queued:['wartet','waiting'],running:['läuft','running'],done:['fertig','done'],failed:['ging nicht','failed'],cancelled:['abgebrochen','cancelled']};
const AG_REP=[['daily','jeden Tag','every day'],['weekdays','werktags','on weekdays'],['weekly','jede Woche','every week'],['monthly','jeden Monat','every month'],['once','einmal','once']];
const AG_EVERY={daily:['jeden Tag','every day'],weekdays:['werktags','on weekdays'],weekly:['jede Woche','every week'],monthly:['jeden Monat','every month']};
const AG_DAYS=[['Montag','Monday'],['Dienstag','Tuesday'],['Mittwoch','Wednesday'],['Donnerstag','Thursday'],['Freitag','Friday'],['Samstag','Saturday'],['Sonntag','Sunday']];
const AG_KIND={watch:['Beobachten','Watching','👁','wa'],plan:['Geplant','Scheduled','⏱','pl'],rem:['Erinnerung','Reminder','⏰','re'],
  rule:['Smart Home','Smart home','⌂','ru'],mail:['Mail','Mail','✉','ma'],routine:['Ablauf','Routine','▶','ro']};
const AG_HIST={neu:['neu gemeldet','new, reported','due'],still:['nichts Neues','nothing new','off'],bericht:['Bericht','report','read'],fehler:['ging nicht','failed','err']};
const agTime=s=>s?new Date(s*1000).toLocaleString(L==='en'?'en-GB':'de-DE',{day:'2-digit',month:'2-digit',hour:'2-digit',minute:'2-digit'}):'';
const agHM=ms=>{const d=new Date(ms);return String(d.getHours()).padStart(2,'0')+':'+String(d.getMinutes()).padStart(2,'0')};
let agTimer=null,agSel=null,agChip='all',agFind='',agData=null;
// every own task as one row: {k: kind, id, title, meta, on, badge: [text, class], item}
function agRows(d){const o=d.own||{},rows=[];
  for(const p of d.plans){const w=p.kind==='watch',hit=w&&p.hist&&p.hist[0]&&p.hist[0].r==='neu'&&p.last_hit&&Date.now()/1000-p.last_hit<86400;
    rows.push({k:w?'watch':'plan',id:p.id,title:w?(p.title||p.task):p.task,on:!p.paused,item:p,
      meta:t(...(AG_KIND[w?'watch':'plan']).slice(0,2))+' · '+p.text.replace(/^Beobachten „[^“]*“: /,''),
      badge:p.paused?[p.why?t('pausiert (von selbst)','paused (by itself)'):t('pausiert','paused'),'off']:hit?[t('Fund heute','found today'),'due']:[t('an','on'),'read']})}
  for(const r of o.reminders||[])rows.push({k:'rem',id:r.id,title:r.text,on:!r.paused,item:r,
    meta:t('Erinnerung','Reminder')+' · '+t(...(AG_EVERY[r.every]||['',''])).trim()+' '+agHM(r.due),badge:r.paused?[t('pausiert','paused'),'off']:[t('an','on'),'read']});
  for(const r of o.rules||[])rows.push({k:'rule',id:r.id,title:r.line,on:!r.paused,item:r,meta:t('Smart Home · melden, wenn …','Smart home · tell me when …'),
    badge:r.paused?[t('pausiert','paused'),'off']:o.rules_on?[t('an','on'),'read']:[t('Smart Home aus','smart home off'),'off']});
  for(const m of o.mail||[])rows.push({k:'mail',id:m,title:t('Mail von ','Mail from ')+m,on:true,item:{who:m},meta:t('Von selbst melden · Absender','Speaking up · sender'),
    badge:o.mail_on?[t('an','on'),'read']:[t('Mail aus','mail off'),'off']});
  for(const r of d.routines||[])rows.push({k:'routine',id:r.id,title:r.name,on:true,item:r,meta:t('Ablauf · ','Routine · ')+r.steps.length+t(' Schritte',' steps'),badge:[t('bereit','ready'),'sh']});
  return rows}
const agSw=(on,attrs)=>`<label class="tgl" title="${esc(t('Ein oder aus','On or off'))}"><input type="checkbox" ${attrs}${on?' checked':''}><i></i></label>`;
function agRowHtml(r){const k=AG_KIND[r.k];const sw=['watch','plan','rem','rule'].includes(r.k)?agSw(r.on,`data-agon="${esc(r.k+':'+r.id)}" aria-label="${esc(r.title)}"`):'';
  return `<div class="ld-row${agSel===r.k+':'+r.id?' on':''}" tabindex="0" role="button" data-agrow="${esc(r.k+':'+r.id)}"><span class="ld-ico ag-${k[3]}" aria-hidden="true">${k[2]}</span>
    <span class="ld-mid"><b>${esc(r.title)}</b><small>${esc(r.meta)}</small></span><span class="ld-right"><span class="ld-badge ${r.badge[1]}">${esc(r.badge[0])}</span>${sw}</span></div>`}
function agWhen(p,pre){const rep=p.repeat||'daily';
  return `<div class="row ag-when"><select id="${pre}rep" aria-label="${esc(t('Wie oft','How often'))}">${AG_REP.filter(x=>pre!=='agw'||x[0]!=='once').map(([k,de,en])=>`<option value="${k}"${rep===k?' selected':''}>${esc(t(de,en))}</option>`).join('')}</select>
    <select id="${pre}wd" aria-label="${esc(t('Wochentag','Weekday'))}">${AG_DAYS.map(([de,en],i)=>`<option value="${i}"${(p.weekday||0)===i?' selected':''}>${esc(t(de,en))}</option>`).join('')}</select>
    <input id="${pre}day" type="number" min="1" max="28" value="${esc(p.day||1)}" aria-label="${esc(t('Tag im Monat','Day of the month'))}">
    <input id="${pre}date" type="date" value="${esc(p.date||'')}" aria-label="${esc(t('Datum','Date'))}"><input id="${pre}time" type="time" value="${esc(p.time||'08:00')}" aria-label="${esc(t('Uhrzeit','Time'))}"></div>`}
function agWhenBind(pre){const rep=$(pre+'rep');if(!rep)return;const vis=()=>{$(pre+'wd').hidden=rep.value!=='weekly';$(pre+'day').hidden=rep.value!=='monthly';$(pre+'date').hidden=rep.value!=='once'};rep.onchange=vis;vis()}
const agWhenVal=pre=>({repeat:$(pre+'rep').value,time:$(pre+'time').value,weekday:+$(pre+'wd').value,day:+$(pre+'day').value,date:$(pre+'date').value});
function agDetail(d,r){const back=`<button class="b ld-back" type="button" data-agback="1">‹ ${esc(t('Zurück zur Liste','Back to the list'))}</button>`;
  if(!r)return back+agNewForm(d);
  const k=AG_KIND[r.k],x=r.item,head=`${back}<h3>${esc(r.title)}</h3><div class="mut ld-note">${esc(t(k[0],k[1]))}${x.created?' · '+esc(t('angelegt ','made ')+agTime(x.created))+(x.created_by==='page'?t(' auf der Seite',' on the page'):x.created_by==='voice'?t(' per Sprache',' by voice'):x.created_by==='remarkable'?t(' vom reMarkable',' from the reMarkable'):''):''}</div>`;
  const onRow=(on,h)=>`<div class="ld-sw"><span><b>${esc(t('Eingeschaltet','Switched on'))}</b><br><small class="mut">${esc(h)}</small></span>${agSw(on,`data-agon="${esc(r.k+':'+r.id)}"`)}</div>`;
  if(r.k==='watch'||r.k==='plan'){const w=r.k==='watch';
    const hist=(x.hist||[]).map(h=>{const s=AG_HIST[h.r]||['?','?','off'];return `<li><span>${esc(h.what||t(s[0],s[1]))}<br><small class="mut">${esc(agTime(h.t))}</small></span><span class="ld-badge ${s[2]}">${esc(t(s[0],s[1]))}</span></li>`}).join('');
    const known=(x.known||[]).slice(0,10).map(k=>`<li><span><b>${esc(k.v)}</b><br><small class="mut">${esc(agHost(k.src))} · ${esc(agTime(k.t))}</small></span></li>`).join('');
    const last=(d.jobs||[]).find(j=>j.plan===x.id&&j.state==='done');
    return head+onRow(!x.paused,x.paused&&x.why?(x.why==='idle'?t('Hat lange nichts Neues gefunden und sich pausiert.','Found nothing new for a long time and paused itself.'):t('Ging mehrmals nicht und hat sich pausiert.','Failed several times and paused itself.')):t('Aus = pausiert, bleibt gespeichert.','Off = paused, stays saved.'))+
      `<label for="agetask">${esc(w?t('Was soll ich suchen','What should I look for'):t('Auftrag','Task'))}</label><textarea id="agetask" rows="2" maxlength="500">${esc(x.task)}</textarea>
      ${w?`<label for="agetitle">${esc(t('Name in der Liste','Name in the list'))}</label><input id="agetitle" maxlength="80" value="${esc(x.title||'')}">`:''}
      <label>${esc(t('Wie oft','How often'))}</label>${agWhen(x,w?'agw':'age')}
      ${w?`<label>${esc(t('Wann melden','When to report'))}</label><div class="segc" role="group"><button type="button" data-agnew="1" class="${x.only_new!==false?'on':''}">${esc(t('nur wenn neu','only when new'))}</button><button type="button" data-agnew="0" class="${x.only_new===false?'on':''}">${esc(t('jedes Mal','every time'))}</button></div>
      <div class="fh">${esc(t('Neu ist, was im letzten Lauf noch nicht vorkam. Das Panel prüft jeden Fund an der gelesenen Seite, nicht das Modell.','New is what the last run did not have. The panel checks every find against the page it read, not the model.'))}</div>
      <label for="agebelow">${esc(t('Nur unter diesem Preis melden (optional)','Only report below this price (optional)'))}</label><div class="row"><input id="agebelow" type="number" min="0" step="0.01" value="${x.below!=null?esc(x.below):''}" placeholder="${esc(t('z. B. 500','e.g. 500'))}"><span class="mut">€</span></div>`:''}
      <div class="ld-acts"><button class="b p" type="button" data-agsave="${esc(x.id)}">${esc(t('Speichern','Save'))}</button><button class="b" type="button" data-agrun="${esc(x.id)}">${esc(w?t('Jetzt prüfen','Check now'):t('Jetzt ausführen','Run now'))}</button>${last?`<button class="b" type="button" data-agshow="${esc(last.id)}">${esc(t('Letzter Bericht','Last report'))}</button>`:''}</div>
      <div class="agrep" data-agrep="${esc(last?last.id:'')}" hidden></div>
      ${w?`<h4 class="ag-h">${esc(t('Bekannt','Known'))}</h4>${known?`<ul class="facts">${known}</ul><button class="b" type="button" data-agforget="${esc(x.id)}">${esc(t('Bekanntes vergessen','Forget what is known'))}</button>`:`<div class="fh">${esc(t('Noch nichts gefunden.','Nothing found yet.'))}</div>`}`:''}
      <h4 class="ag-h">${esc(t('Verlauf · 14 Tage','History · 14 days'))}</h4>${hist?`<ul class="facts">${hist}</ul>`:`<div class="fh">${esc(t('Noch kein Lauf. Nächster: ','No run yet. Next: ')+(x.next?agTime(x.next):'–'))}</div>`}
      <div class="ld-acts"><button class="b danger" type="button" data-agpdel="${esc(x.id)}">${esc(t('Löschen','Delete'))}</button></div>`}
  if(r.k==='rem')return head+onRow(r.on,t('Aus = klingelt nicht, bleibt gespeichert.','Off = does not ring, stays saved.'))+
    `<label for="agrtext">${esc(t('Text','Text'))}</label><input id="agrtext" maxlength="200" value="${esc(x.text)}"${x.paused?' disabled':''}>
    <label>${esc(t('Wie oft und wann','How often and when'))}</label><div class="row ag-when"><select id="agrevery"${x.paused?' disabled':''}>${Object.entries(AG_EVERY).map(([k,v])=>`<option value="${k}"${x.every===k?' selected':''}>${esc(t(v[0],v[1]))}</option>`).join('')}</select><input id="agrtime" type="time" value="${esc(agHM(x.due))}"${x.paused?' disabled':''}></div>
    <div class="fh">${esc(t('Nächstes Mal: ','Next time: ')+(x.paused?t('pausiert','paused'):new Date(x.due).toLocaleString(L==='en'?'en-GB':'de-DE')))}</div>
    <div class="ld-acts">${x.paused?'':`<button class="b p" type="button" data-agremsave="${esc(x.id)}">${esc(t('Speichern','Save'))}</button>`}<button class="b danger" type="button" data-agremdel="${esc(x.id)}">${esc(t('Löschen','Delete'))}</button></div>`;
  if(r.k==='rule')return head+onRow(r.on,t('Aus = meldet nichts, bleibt gespeichert.','Off = says nothing, stays saved.'))+
    `<div class="ld-note">${esc(t('Ich melde mich, wenn: ','I tell you when: ')+x.line)}</div>${(d.own||{}).rules_on?'':`<div class="fh">${esc(t('Smart-Home-Regeln sind bei dir aus: Ich → Von selbst.','Smart home rules are off for you: Me → Proactive.'))}</div>`}
    <div class="fh">${esc(t('Bedingungen ändern: Ich → Von selbst.','Change the conditions: Me → Proactive.'))}</div>
    <div class="ld-acts"><button class="b danger" type="button" data-agruledel="${esc(x.id)}">${esc(t('Löschen','Delete'))}</button></div>`;
  if(r.k==='mail')return head+`<div class="ld-note">${esc(t('Kommt eine Mail, deren Absender „','When a mail comes whose sender contains "')+x.who+t('“ enthält, melde ich mich (nur Absender und Betreff, nie der Inhalt).','", I tell you (only sender and subject, never the content).'))}</div>
    ${(d.own||{}).mail_on?'':`<div class="fh">${esc(t('„Wichtige Mail“ ist bei dir aus: Ich → Von selbst.','"Important mail" is off for you: Me → Proactive.'))}</div>`}
    <div class="ld-acts"><button class="b danger" type="button" data-agmaildel="${esc(x.who)}">${esc(t('Entfernen','Remove'))}</button></div>`;
  return head+`<ol class="ag-steps">${x.steps.map(s=>`<li>${esc(s)}</li>`).join('')}</ol><div class="fh">${esc(t('Starten: nur den Namen sagen („','Start: just say the name ("')+x.name+t('“).','").'))}</div>
    <div class="ld-acts"><button class="b danger" type="button" data-agrdel="${esc(x.id)}">${esc(t('Löschen','Delete'))}</button></div>`}
const agHost=u=>{try{return new URL(u).hostname.replace(/^www\./,'')}catch{return ''}};
function agNewForm(d){const o=d.own||{};
  return `<h3>${esc(t('Neue eigene Aufgabe','New own task'))}</h3>
    ${d.watch?`<h4 class="ag-h">${esc(t('Beobachten','Watching'))}</h4><div class="fh">${esc(t('Der Spark sieht regelmäßig im Netz nach und meldet sich nur, wenn es etwas Neues gibt.','The Spark looks on the web regularly and only tells you when there is something new.'))}</div>
    <input id="agwtask" maxlength="500" placeholder="${esc(t('z. B. Neue Firmware für meine FRITZ!Box 7590','e.g. New firmware for my FRITZ!Box 7590'))}" aria-label="${esc(t('Was soll ich suchen','What should I look for'))}">
    ${agWhen({repeat:'daily',time:'08:00'},'agw')}<div class="row"><input id="agwbelow" type="number" min="0" step="0.01" placeholder="${esc(t('nur unter … € (optional)','only below … € (optional)'))}" aria-label="${esc(t('Preisgrenze','Price limit'))}"><button class="b p" type="button" id="agwadd">${esc(t('Beobachten','Watch'))}</button></div>`:''}
    <h4 class="ag-h">${esc(t('Geplanter Auftrag','Scheduled job'))}</h4><div class="fh">${esc(t('Läuft zur festen Zeit und berichtet jedes Mal.','Runs at a fixed time and reports every time.'))}</div>
    <input id="agptask" maxlength="500" placeholder="${esc(t('z. B. Fass mir die Termine der Woche zusammen','e.g. Summarize my appointments of the week'))}" aria-label="${esc(t('Auftrag','Task'))}">
    ${agWhen({repeat:'weekly',time:'07:00'},'agp')}<div class="row"><label class="chk" style="margin:0"><input type="checkbox" id="agpdoc"> ${esc(t('Bericht auch als Dokument','Report also as a document'))}</label><button class="b" type="button" id="agpadd">${esc(t('Planen','Schedule'))}</button></div>
    ${o.pro?`<h4 class="ag-h">${esc(t('Mail von …','Mail from …'))}</h4><div class="fh">${esc(t('Ich melde mich, wenn eine Mail dieses Absenders kommt.','I tell you when a mail from this sender comes.'))}</div>
    <div class="row"><input id="agmwho" maxlength="80" placeholder="${esc(t('z. B. Sparkasse','e.g. Sparkasse'))}" aria-label="${esc(t('Absender','Sender'))}"><button class="b" type="button" id="agmadd">${esc(t('Hinzufügen','Add'))}</button></div>`:''}
    <div class="fh">${esc(t('Per Sprache: „Sag mir Bescheid, wenn es eine neue Firmware für meine FRITZ!Box gibt.“ Gespeichert wird erst nach deinem „Ja“.','By voice: "Let me know when there is a new firmware for my FRITZ!Box." It is saved only after your "Yes".'))}</div>`}
async function showAgent(){const box=$('agentbox');if(!box)return;clearTimeout(agTimer);if(!PROFILE||!AGENT_ON){box.innerHTML='';return}
  let d;try{d=agData=await (await api('/api/profile/agent')).json()}catch{box.innerHTML='';return}
  const lvl={read:t('nur lesen und berichten','read and report only'),act:t('auch handeln mit „Ja“','also act after "Yes"')}[d.granted]||t('nichts','nothing');
  const on=!!S.agent_on,act=d.granted==='act';
  const rows=agRows(d),cnt=k=>rows.filter(r=>r.k===k).length;
  const shown=rows.filter(r=>(agChip==='all'||r.k===agChip)&&(!agFind||(r.title+' '+r.meta).toLowerCase().includes(agFind.toLowerCase())));
  const sel=agSel==='new'?null:rows.find(r=>r.k+':'+r.id===agSel);if(agSel&&agSel!=='new'&&!sel)agSel=null;
  const results=d.jobs.filter(j=>j.state==='done'&&(j.origin==='watch'||j.origin==='plan'));
  const fresh=results.filter(j=>j.origin==='watch'&&j.finds&&j.finds.length&&Date.now()/1000-(j.finished||0)<86400).length;
  const once=d.jobs.filter(j=>j.origin!=='watch'&&j.origin!=='plan');
  const nxt=d.plans.filter(p=>!p.paused&&p.next).map(p=>p.next).sort()[0];
  const chips=[['all',t('Alle','All'),rows.length],['watch',t('Beobachten','Watching'),cnt('watch')],['plan',t('Geplant','Scheduled'),cnt('plan')],['rem',t('Erinnerungen','Reminders'),cnt('rem')],
    ['rule',t('Smart Home','Smart home'),cnt('rule')],['mail',t('Mail','Mail'),cnt('mail')],['routine',t('Abläufe','Routines'),cnt('routine')]].filter(c=>c[0]==='all'||c[2]);
  const job=j=>`<li><span><b>${esc(t(...(AG_ST[j.state]||['?','?'])))}</b> · ${esc(j.title||j.task)}<br><small class="mut">${esc(agTime(j.created))}${j.origin==='plan'?t(' · geplant',' · scheduled'):j.origin==='watch'?t(' · Beobachten',' · watching'):''}${j.doc_name?' · '+esc(j.doc_name):''}</small>
      ${j.finds&&j.finds.length?`<br><small>${j.finds.map(f=>esc(f.v)+' ('+esc(agHost(f.src))+')').join(' · ')}</small>`:j.summary?`<br><small>${esc(j.summary)}</small>`:''}${j.error?`<br><small class="err">${esc(j.error)}</small>`:''}${j.doc_error?`<br><small class="err">${esc(j.doc_error)}</small>`:''}
      ${j.state==='running'&&j.steps.length?`<br><small class="mut">${esc(j.steps[j.steps.length-1])}</small>`:''}<div class="agrep" data-agrep="${esc(j.id)}" hidden></div></span>
      <span class="row">${j.state==='done'?`<button class="b" type="button" data-agshow="${esc(j.id)}">${t('Bericht','Report')}</button>`:''}
      ${j.state==='done'&&!j.doc_name?`<button class="b" type="button" data-agdoc="${esc(j.id)}">${t('Als Dokument','As document')}</button>`:''}
      ${j.state==='queued'||j.state==='running'?`<button class="b" type="button" data-agstop="${esc(j.id)}">${t('Abbrechen','Cancel')}</button>`:`<button class="b" type="button" data-agdel="${esc(j.id)}">${t('Löschen','Delete')}</button>`}</span></li>`;
  box.innerHTML=`<div class="intro">${t('Was der Spark dauerhaft für dich im Blick behält, plant oder auf Zuruf erledigt. Er liest nur und meldet sich per Mitteilung und Telegram (wie unter Ich → Mitteilungen eingestellt). Ein Auftrag läuft nach dem anderen; Gespräche mit dir haben Vorrang. Der Admin hat dir freigegeben: ','What the Spark keeps an eye on for you, plans or does when asked. It only reads and tells you by notification and Telegram (as set under Me → Notifications). One job runs after the other; talking to you comes first. The admin allowed you: ')}<b>${esc(lvl)}</b>.</div>
    ${xsw('agent_on',t('Agent-Funktionen für mich nutzen','Use agent functions for me'),act?t('Aufträge, Beobachten, geplante Aufträge, Abläufe und freigegebene Dienste.','Jobs, watching, scheduled jobs, routines and allowed services.'):t('Aufträge, Beobachten, geplante Aufträge und freigegebene Dienste (nur lesend).','Jobs, watching, scheduled jobs and allowed services (read only).'))}
    ${on?`<div class="ag-stats">${[[rows.length+' / '+rows.filter(r=>r.on).length+t(' an',' on'),t('eigene Aufgaben','own tasks'),0],[fresh,t('neue Funde heute','new finds today'),fresh],[nxt?agTime(nxt):'–',t('nächster Lauf','next run'),0]].map(([v,l,h])=>`<div class="ag-stat${h?' hot':''}"><b>${esc(String(v))}</b><span>${esc(l)}</span></div>`).join('')}</div>
    <h3>${t('Eigene Aufgaben','Own tasks')}</h3>
    <div class="ld-box${agSel?' ld-sel':''}" id="agld" data-tabcount="${rows.length}"><div class="ld-tools"><input type="search" id="agfind" maxlength="80" value="${esc(agFind)}" placeholder="${esc(t('Aufgaben suchen …','Search tasks …'))}" aria-label="${esc(t('Aufgaben suchen','Search tasks'))}"><button class="b p" type="button" id="agnew">+ ${esc(t('Neu','New'))}</button></div>
      <div class="ld-chips">${chips.map(([k,l,n])=>`<button type="button" class="ld-chip${agChip===k?' on':''}" data-agchip="${k}">${esc(l)} <b>${n}</b></button>`).join('')}</div>
      <div class="ld-split"><div class="ld-list">${shown.map(agRowHtml).join('')||`<div class="ld-empty mut">${esc(rows.length?t('Nichts passt zur Suche.','Nothing matches.'):t('Noch keine eigenen Aufgaben. Sag z. B. „Sag mir Bescheid, wenn es eine neue Firmware für meine FRITZ!Box gibt.“','No own tasks yet. Say e.g. "Let me know when there is a new firmware for my FRITZ!Box."'))}</div>`}</div>
      <div class="ld-detail" id="agdet"${agSel?'':' hidden'}>${agSel?agDetail(d,sel):''}</div></div></div>
    <h3>${t('Ergebnisse','Results')}</h3><ul class="facts">${results.map(job).join('')||`<li class="mut">${t('Noch keine Ergebnisse.','No results yet.')}</li>`}</ul>
    <h3>${t('Einmal-Aufträge','One-off jobs')}</h3>
    ${xsw('agent_doc',t('Jeden Bericht auch unter „Dokumente“ ablegen','Also keep every report under "Documents"'),t('Dann findet der Assistent ihn später wieder („Was stand im Bericht zur Wärmepumpe?“).','Then the assistant finds it again later ("What did the heat pump report say?").'))}
    ${d.search?'':`<div class="fh">${t('Die Websuche ist aus: Aufträge lesen dann nur deine eigenen Daten (Kalender, Erinnerungen, Dokumente).','Web search is off: jobs then only read your own data (calendar, reminders, documents).')}</div>`}
    <textarea id="agtask" rows="2" maxlength="500" placeholder="${esc(t('z. B. Vergleich die drei günstigsten Flüge nach Rom im November','e.g. Compare the three cheapest flights to Rome in November'))}" aria-label="${esc(t('Neuer Auftrag','New job'))}"></textarea>
    <div class="row" style="margin-top:6px"><label class="chk" style="margin:0"><input type="checkbox" id="agdoc"> ${t('Bericht auch als Dokument','Report also as a document')}</label><button class="b p" type="button" id="aggo">${t('Auftrag starten','Start job')}</button></div>
    <div class="fh">${t('Höchstens ','At most ')+d.day_max+t(' Aufträge am Tag, drei warten gleichzeitig. Per Sprache: „Recherchiere …“, „Finde heraus …“, „Was laufen für Aufträge?“',' jobs a day, three wait at once. By voice: "Research …", "Find out …", "Which jobs are running?"')}</div>
    <ul class="facts">${once.map(job).join('')||`<li class="mut">${t('Noch keine Aufträge.','No jobs yet.')}</li>`}</ul>
    ${act&&!d.ha?`<div class="fh">${t('Abläufe schalten über Home Assistant: erst unter Ich → Smart Home verbinden.','Routines switch through Home Assistant: connect it under Me → Smart home first.')}</div>`:''}
    ${act&&d.ha?`<details><summary>${t('Ablauf anlegen','Add a routine')}</summary>
      <input id="agrname" maxlength="40" placeholder="${esc(t('Name, z. B. Feierabend','Name, e.g. Evening'))}" aria-label="${esc(t('Name','Name'))}">
      <textarea id="agrsteps" rows="3" placeholder="${esc(t('Ein Befehl pro Zeile, z. B.\nSchalte das Licht im Flur aus\nFahr die Rollläden im Wohnzimmer runter','One command per line, e.g.\nTurn off the hall light\nClose the living room blinds'))}" aria-label="${esc(t('Schritte','Steps'))}"></textarea>
      <div class="row" style="margin-top:6px"><button class="b" type="button" id="agradd">${t('Ablauf speichern','Save routine')}</button></div>
      <div class="fh">${t('Starten: nur den Namen sagen („Feierabend“). Jeder Schritt läuft wie ein gesprochener Befehl, mit deinem Codewort, falls du eins hast.','Start: just say the name ("Evening"). Each step runs like a spoken command, with your code word if you have one.')}</div></details>`:''}
    ${d.servers.length?`<h3>${t('Freigegebene Dienste','Allowed services')}</h3><ul class="facts">${d.servers.map(s=>`<li><span><b>${esc(s.name)}</b><br><small class="mut">${esc(s.tools.join(', ')||t('keine Werkzeuge','no tools'))}</small></span></li>`).join('')}</ul>`:''}`:''}
    <div class="fh" id="agmsg"></div>`;
  if(window.icAutoTabs)icAutoTabs(box,'agent');
  xbind(box,showAgent);
  agBind(box,d);
  // while a job waits or runs, the page looks again now and then
  if(d.jobs.some(j=>j.state==='queued'||j.state==='running'))agTimer=setTimeout(()=>{if(box.offsetParent)showAgent()},10000)}
function agBind(box,d){
  const call=async(p,o,after)=>{try{await api(p,o);if(after)after();await showAgent()}catch(e){xmsg('agmsg',e.message,true);const m=$('agmsg');if(m)m.scrollIntoView({block:'nearest'})}};
  const enc=encodeURIComponent,open=k=>{agSel=k;showAgent()};
  const find=$('agfind');if(find)find.oninput=()=>{agFind=find.value;clearTimeout(find._t);find._t=setTimeout(async()=>{await showAgent();const f=$('agfind');if(f){f.focus();f.setSelectionRange(f.value.length,f.value.length)}},250)};
  box.querySelectorAll('[data-agchip]').forEach(b=>b.onclick=()=>{agChip=b.dataset.agchip;showAgent()});
  box.querySelectorAll('[data-agrow]').forEach(r=>{r.onclick=e=>{if(e.target.closest('.tgl'))return;open(r.dataset.agrow)};r.onkeydown=e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();open(r.dataset.agrow)}}});
  box.querySelectorAll('[data-agback]').forEach(b=>b.onclick=()=>{agSel=null;showAgent()});
  if($('agnew'))$('agnew').onclick=()=>open('new');
  box.querySelectorAll('[data-agon]').forEach(i=>{i.onclick=e=>e.stopPropagation();i.onchange=()=>{const [k,id]=i.dataset.agon.split(/:(.*)/s);
    if(k==='watch'||k==='plan')call('/api/profile/agent/plans/'+enc(id),xjson('PUT',{on:i.checked}));
    else if(k==='rem')call('/api/profile/agent/reminders/'+enc(id)+'/pause',xjson('POST'));
    else if(k==='rule')call('/api/profile/agent/rules/'+enc(id)+'/pause',xjson('POST'))}});
  box.querySelectorAll('[data-agnew]').forEach(b=>b.onclick=()=>{box.querySelectorAll('[data-agnew]').forEach(x=>x.classList.toggle('on',x===b))});
  agWhenBind('agw');agWhenBind('age');agWhenBind('agp');
  box.querySelectorAll('[data-agsave]').forEach(b=>b.onclick=()=>{const w=!!$('agetitle'),pre=w?'agw':'age',body=Object.assign({task:$('agetask').value},agWhenVal(pre));
    if(w){body.title=$('agetitle').value;const n=box.querySelector('[data-agnew].on');body.only_new=!n||n.dataset.agnew==='1';const v=$('agebelow').value.trim();body.below=v===''?null:+v}
    call('/api/profile/agent/plans/'+enc(b.dataset.agsave),xjson('PUT',body),()=>xmsg('agmsg',t('Gespeichert.','Saved.')))});
  box.querySelectorAll('[data-agrun]').forEach(b=>b.onclick=()=>call('/api/profile/agent/plans/'+enc(b.dataset.agrun)+'/run',xjson('POST'),()=>xmsg('agmsg',t('Läuft gleich, das Ergebnis kommt als Mitteilung.','Runs shortly, the result comes as a notification.'))));
  box.querySelectorAll('[data-agforget]').forEach(b=>b.onclick=()=>{if(confirm(t('Alles Bekannte vergessen? Dann gilt der nächste Fund wieder als neu.','Forget everything known? The next find then counts as new again.')))call('/api/profile/agent/plans/'+enc(b.dataset.agforget),xjson('PUT',{forget:true}))});
  box.querySelectorAll('[data-agpdel]').forEach(b=>b.onclick=()=>{if(confirm(t('Aufgabe löschen?','Delete the task?')))call('/api/profile/agent/plans/'+enc(b.dataset.agpdel),{method:'DELETE'},()=>{agSel=null})});
  box.querySelectorAll('[data-agremsave]').forEach(b=>b.onclick=()=>call('/api/profile/agent/reminders/'+enc(b.dataset.agremsave),xjson('PUT',{text:$('agrtext').value,every:$('agrevery').value,time:$('agrtime').value}),()=>{agSel=null;xmsg('agmsg',t('Gespeichert.','Saved.'))}));
  box.querySelectorAll('[data-agremdel]').forEach(b=>b.onclick=()=>{if(confirm(t('Erinnerung löschen?','Delete the reminder?')))call('/api/profile/agent/reminders/'+enc(b.dataset.agremdel),{method:'DELETE'},()=>{agSel=null})});
  box.querySelectorAll('[data-agruledel]').forEach(b=>b.onclick=()=>{if(confirm(t('Regel löschen?','Delete the rule?')))call('/api/proactive/rules/'+enc(b.dataset.agruledel),{method:'DELETE'},()=>{agSel=null})});
  box.querySelectorAll('[data-agmaildel]').forEach(b=>b.onclick=()=>call('/api/profile/agent/mail',xjson('PUT',{remove:b.dataset.agmaildel}),()=>{agSel=null}));
  box.querySelectorAll('[data-agrdel]').forEach(b=>b.onclick=()=>{if(confirm(t('Ablauf löschen?','Delete the routine?')))call('/api/profile/agent/routines/'+enc(b.dataset.agrdel),{method:'DELETE'},()=>{agSel=null})});
  if($('agwadd'))$('agwadd').onclick=()=>{const v=$('agwbelow').value.trim();call('/api/profile/agent/plans',xjson('POST',Object.assign({kind:'watch',task:$('agwtask').value},agWhenVal('agw'),v===''?{}:{below:+v})),()=>{agSel=null;xmsg('agmsg',t('Angelegt.','Created.'))})};
  if($('agpadd'))$('agpadd').onclick=()=>call('/api/profile/agent/plans',xjson('POST',Object.assign({task:$('agptask').value,doc:$('agpdoc').checked},agWhenVal('agp'))),()=>{agSel=null;xmsg('agmsg',t('Angelegt.','Created.'))});
  if($('agmadd'))$('agmadd').onclick=()=>call('/api/profile/agent/mail',xjson('PUT',{add:$('agmwho').value}),()=>{agSel=null});
  if($('aggo'))$('aggo').onclick=()=>{const v=$('agtask').value.trim();if(!v)return;call('/api/profile/agent/jobs',xjson('POST',{task:v,doc:$('agdoc').checked}))};
  box.querySelectorAll('[data-agstop]').forEach(b=>b.onclick=()=>call('/api/profile/agent/jobs/'+enc(b.dataset.agstop)+'/cancel',xjson('POST')));
  box.querySelectorAll('[data-agdel]').forEach(b=>b.onclick=()=>call('/api/profile/agent/jobs/'+enc(b.dataset.agdel),{method:'DELETE'}));
  box.querySelectorAll('[data-agdoc]').forEach(b=>b.onclick=()=>call('/api/profile/agent/jobs/'+enc(b.dataset.agdoc)+'/doc',xjson('POST')));
  box.querySelectorAll('[data-agshow]').forEach(b=>b.onclick=async()=>{const el=box.querySelector(`[data-agrep="${CSS.escape(b.dataset.agshow)}"]`);if(!el)return;
    if(!el.hidden){el.hidden=true;return}
    try{const j=await (await api('/api/profile/agent/jobs/'+enc(b.dataset.agshow))).json();el.textContent=j.report||'';el.hidden=false}catch(e){xmsg('agmsg',e.message,true)}});
  if($('agradd'))$('agradd').onclick=()=>call('/api/profile/agent/routines',xjson('POST',{name:$('agrname').value,steps:$('agrsteps').value.split('\n')}));
  if(agSel&&$('agdet')&&$('agld').classList.contains('ld-sel')&&getComputedStyle($('agld').querySelector('.ld-list')).display==='none')$('agdet').scrollIntoView({block:'nearest'})}

// ---------------------------------------------------------------- admin: who may, and the MCP services
const AG_LV=[['','aus','off'],['read','nur lesen und berichten','read and report only'],['act','auch handeln mit „Ja“','also act after "Yes"']];
const AG_MODE=[['off','aus','off'],['read','lesen','read'],['act','handeln (mit „Ja“)','act (after "Yes")']];
async function agentAdmin(){const box=$('agentadmin');if(!box)return;let d;try{d=await (await api('/api/admin/agent')).json()}catch{return}
  box.innerHTML=`<div class="fh">${t('Pro Profil, was es darf. Das Profil schaltet es danach selbst ein (Ich → Aufträge). Gäste nie.','Per profile, what it may do. The profile then switches it on itself (Me → Jobs). Never guests.')}</div>
    <table><tbody>${d.users.map(u=>`<tr><td>${esc(u.name)}${u.on?` <small class="mut">${t('(eingeschaltet)','(switched on)')}</small>`:''}</td>
      <td><select data-aglv="${esc(u.id)}">${AG_LV.map(([k,de,en])=>`<option value="${k}"${u.level===k?' selected':''}>${esc(t(de,en))}</option>`).join('')}</select></td></tr>`).join('')
      ||`<tr><td class="mut">${t('Noch keine Profile.','No profiles yet.')}</td></tr>`}</tbody></table>
    <div class="row" style="margin-top:6px"><button class="b" type="button" id="aglvsave">${t('Freigaben speichern','Save permissions')}</button><span class="mut" id="aglvmsg"></span></div>`;
  $('aglvsave').onclick=async()=>{const levels={};box.querySelectorAll('[data-aglv]').forEach(s=>{if(s.value)levels[s.dataset.aglv]=s.value});
    try{await api('/api/admin/agent/levels',xjson('PUT',{levels}));$('aglvmsg').textContent=t('Gespeichert.','Saved.')}catch(e){$('aglvmsg').textContent=e.message}};
  const mb=$('mcpadmin');if(!mb)return;
  mb.innerHTML=`<div class="fh">${t('Dienste, die das MCP-Protokoll über HTTP sprechen (z. B. Paperless, Nextcloud, GitHub). Jedes Werkzeug ist aus, bis du es freigibst: „lesen“ für Profile ab „nur lesen“, „handeln“ nur für „auch handeln“ und erst nach dem „Ja“ der Person. Der Spark startet nie selbst ein Programm. Adressen im Heimnetz nur mit „Heimnetz-Adressen erlauben“ (Sicherheit).','Services that speak MCP over HTTP (e.g. Paperless, Nextcloud, GitHub). Every tool is off until you allow it: "read" for profiles from "read only", "act" only for "also act" and only after the person\'s "Yes". The Spark never starts a program itself. Home network addresses only with "Allow home network addresses" (Security).')}</div>
    ${d.servers.map(s=>`<div class="card" style="margin:8px 0;padding:10px" data-mcp="${esc(s.id)}"><b>${esc(s.name)}</b> <small class="mut">${esc(s.url)}${s.has_token?t(' · mit Token',' · with token'):''}</small>
      <div class="fh">${t('Profile, die den Dienst nutzen dürfen:','Profiles that may use the service:')} ${d.users.map(u=>`<label class="chk" style="display:inline-flex;margin:0 8px 0 0"><input type="checkbox" data-mcpuser="${esc(u.id)}"${s.users.includes(u.id)?' checked':''}> ${esc(u.name)}</label>`).join('')}</div>
      <table><tbody>${s.tools.map(x=>`<tr><td><b>${esc(x.name)}</b><br><small class="mut">${esc(x.desc)}</small></td><td><select data-mcptool="${esc(x.name)}">${AG_MODE.map(([k,de,en])=>`<option value="${k}"${x.mode===k?' selected':''}>${esc(t(de,en))}</option>`).join('')}</select></td></tr>`).join('')
        ||`<tr><td class="mut">${t('Der Dienst bietet keine Werkzeuge an.','The service offers no tools.')}</td></tr>`}</tbody></table>
      <div class="row" style="margin-top:6px"><button class="b" type="button" data-mcpsave>${t('Speichern','Save')}</button><button class="b" type="button" data-mcprefresh>${t('Werkzeuge neu abfragen','Fetch tools again')}</button><button class="b" type="button" data-mcpdel>${t('Entfernen','Remove')}</button></div></div>`).join('')}
    <label>${t('Name','Name')}</label><input id="mcpname" maxlength="40" placeholder="Paperless">
    <label>${t('Adresse','Address')}</label><input id="mcpurl" autocapitalize="off" autocomplete="off" placeholder="https://paperless.example.de/mcp">
    <label>${t('Token (optional)','Token (optional)')}</label><input id="mcptoken" type="password" autocomplete="off">
    <div class="row" style="margin-top:6px"><button class="b" type="button" id="mcpadd">${t('Verbinden und Werkzeuge abfragen','Connect and fetch tools')}</button><span class="mut" id="mcpmsg"></span></div>`;
  const run=async(p,o)=>{$('mcpmsg').textContent=t('Einen Moment …','One moment …');try{await api(p,o);await agentAdmin()}catch(e){$('mcpmsg').textContent=e.message}};
  $('mcpadd').onclick=()=>run('/api/admin/agent/mcp',xjson('POST',{name:$('mcpname').value,url:$('mcpurl').value.trim(),token:$('mcptoken').value.trim()}));
  mb.querySelectorAll('[data-mcp]').forEach(c=>{const id=encodeURIComponent(c.dataset.mcp);
    c.querySelector('[data-mcpsave]').onclick=()=>{const tools={};c.querySelectorAll('[data-mcptool]').forEach(s=>tools[s.dataset.mcptool]=s.value);
      run('/api/admin/agent/mcp/'+id,xjson('PUT',{tools,users:[...c.querySelectorAll('[data-mcpuser]')].filter(x=>x.checked).map(x=>x.dataset.mcpuser)}))};
    c.querySelector('[data-mcprefresh]').onclick=()=>run('/api/admin/agent/mcp/'+id+'/refresh',xjson('POST'));
    c.querySelector('[data-mcpdel]').onclick=()=>{if(confirm(t('Dienst entfernen? Das Token wird gelöscht.','Remove the service? The token is deleted.')))run('/api/admin/agent/mcp/'+id,{method:'DELETE'})}})}
