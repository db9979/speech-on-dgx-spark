// Ich → Was ich über dich weiß (ichweiss.py, plan persoenlicher-assistent, stages 3 and 4): interests with their evidence
// (count only after „Stimmt“), what comes back every month, the week, this month's sums, the tip from the web and what
// the memory and the mail style hold. Names of shops, subjects and titles from the web are outside text: textContent
// only; the web tip's address opens only as an https link in a new tab, without the Spark's address (noreferrer).
// Proposals are topics (plan interessen-themen, Dominik 2026-10-22 „ok“): the topic as title, its senders as chips (✕
// leaves one out), up to three subjects as evidence; a sender without a topic is „Thema unklar“ with its subjects and a
// field for an own topic; an older confirmed sender is asked once for its topic.
let WISS_ON=false,WISS=null,WISS_EDIT='';
const wissMsg=(x,err)=>{const m=$('wissmsg');if(m){m.textContent=x||'';m.className='fh'+(err?' err':'')}};
async function wissCall(path,body,method='POST'){const r=await api(path,{method,headers:{'Content-Type':'application/json'},body:body?JSON.stringify(body):undefined});return r.json()}
async function showWiss(){const box=$('wissbox');if(!box)return;if(!PROFILE||!WISS_ON){box.textContent='';return}
  if(!WISS){box.textContent='';box.appendChild(icEl('div','fh',t('Einen Moment …','One moment …')))}
  try{WISS=await (await api('/api/profile/ichweiss')).json()}catch(e){box.textContent='';box.appendChild(icEl('div','fh err',e.message));return}
  wissRender();if((WISS.loading||[]).length)setTimeout(()=>{if(box.isConnected&&!box.hidden)showWiss()},4000)}
async function wissSet(name,state,extra={}){const {label,tip,...body}=extra;try{await wissCall('/api/profile/ichweiss/interest',Object.assign({name,state},body))}catch(e){wissMsg(e.message,true);return}
  await showWiss();wissMsg(tip?(body.web?t('Netz-Tipps für „','Web tips for "')+label+t('“ an: höchstens ein Tipp am Tag zwischen 10 und 19 Uhr, er steht dann im Detail und unter „Woche & Gemerkt“.','" on: at most one tip a day between 10 am and 7 pm, shown in the details and under "Week & kept".'):t('Netz-Tipps für „','Web tips for "')+label+t('“ aus.','" off.')):state==='yes'||state==='adopt'?t('Gemerkt: „','Noted: "')+(extra.label||name)+t('“ interessiert dich.','" interests you.'):state==='no'?t('Kommt nicht wieder als Vorschlag.','Will not be proposed again.'):state==='keep'?t('Bleibt, wie es ist.','Stays as it is.'):state==='drop'?t('Absender herausgenommen.','Sender taken out.'):state==='rename'?t('Geändert: „','Changed: "')+(extra.label||'')+t('“.','".'):t('Vergessen.','Forgotten.'))}
const wissName=x=>L==='en'&&x.en?x.en:x.name;
function wissProposal(x){const E=icEl,box=E('div','wiss-prop'),head=E('div','wiss-head');head.appendChild(E('span','ic-t',wissName(x)));
  if(x.unclear)head.appendChild(E('span','ic-badge warn',t('Thema unklar','Topic unclear')));box.appendChild(head);
  if(!x.unclear&&(x.senders||[]).length){const c=E('div','wiss-chips');for(const n of x.senders){const ch=E('span','chip',n+' ');
      const b=E('button','b');b.appendChild(icNode('x'));b.type='button';b.title=t('Diesen Absender nicht','Not this sender');b.setAttribute('aria-label',b.title);b.dataset.wissChipNo=n;
      b.onclick=()=>wissSet(n,'no',{src:'shop'});ch.appendChild(b);c.appendChild(ch)}box.appendChild(c)}
  const ex=(x.ex||[]).map(v=>'„'+v+'“').join(', ');
  if(ex&&!x.unclear)box.appendChild(E('small','ic-meta wiss-ex',t('z. B. ','e.g. ')+ex));
  if(x.unclear){const d=E('details','wiss-more');d.appendChild(E('summary','',t('Betreffe zeigen und eigenes Thema','Show subjects and an own topic')));
    if(ex)d.appendChild(E('small','ic-meta wiss-ex',ex));
    // an own topic: picked from the ones there are (confirmed first, then the list) or typed; typing suggests them too
    const ch=WISS.choices||[],f=E('form','row'),pick=E('select'),inp=E('input');pick.dataset.wissPick=x.name;
    pick.appendChild(E('option','',t('Vorhandenes Thema wählen …','Pick a topic …'))).value='';
    for(const c of ch){const o=E('option','',wissName(c));o.value=c.name;pick.appendChild(o)}
    pick.onchange=()=>{if(pick.value)inp.value=pick.value};
    inp.maxLength=40;inp.placeholder=t('oder eintippen, z. B. Wandern','or type one, e.g. hiking');inp.dataset.wissOwn=x.name;inp.setAttribute('list','wisstopics');
    const go=E('button','b',t('Als Thema merken','Keep as topic'));go.type='submit';f.append(pick,inp,go);
    f.onsubmit=e=>{e.preventDefault();const v=inp.value.trim();if(v.length>=2)wissSet(v,'yes',{src:'hand',senders:[x.name]})};d.appendChild(f);
    const mine=ch.filter(c=>(WISS.interests||[]).some(i=>i.state==='yes'&&i.name===c.name)).slice(0,6);
    if(mine.length){const row=E('div','wiss-chips');row.appendChild(E('small','ic-meta',t('Schnell zuordnen:','Quick pick:')));for(const c of mine){const b=E('button','chip',wissName(c));b.type='button';b.dataset.wissChoice=c.name;
        b.title=t('Zu diesem Thema','To this topic');b.onclick=()=>wissSet(c.name,'yes',{src:'hand',senders:[x.name]});row.appendChild(b)}d.appendChild(row)}
    box.appendChild(d)}
  return box}
// The page (Dominik 2026-10-22 „ok“ to plan interessen-themen/seite-aufraeumen.md): tabs „Zu klären“ (opens first when
// something waits), „Interessen“ as a list with details beside it (on the phone a page of its own), „Wiederkehrend“
// and „Woche & Gemerkt“. One title, one line of explanation; buttons say what they do in words.
let WISS_SEL='',WISS_ADD=false;
const wissB=(label,fn,cls='b')=>{const b=icEl('button',cls,label);b.type='button';b.onclick=fn;return b};
function wissRender(){const d=WISS,box=$('wissbox'),E=icEl;if(!box||!d)return;box.textContent='';
  const dl=E('datalist');dl.id='wisstopics';for(const c of d.choices||[]){const o=E('option');o.value=wissName(c);dl.appendChild(o)}box.appendChild(dl);
  const yes=d.interests.filter(x=>x.state==='yes'),open=d.proposals.length+(d.asks||[]).length;
  const menu=[{label:t('Alle Interessen vergessen','Forget every interest'),danger:true,act:async()=>{if(!confirm(t('Alle Interessen und den Tipp aus dem Netz vergessen?','Forget every interest and the web tip?')))return;
    try{await api('/api/profile/ichweiss',{method:'DELETE'})}catch(e){wissMsg(e.message,true);return}await showWiss()}}];
  box.appendChild(icCard('spark',t(`${yes.length} Interessen · ${open} zu klären`,`${yes.length} interests · ${open} to sort out`),t('Interessen zählen erst nach „Stimmt“. Feste Regeln, kein Modell, alles bleibt auf dem Spark.',
    'Interests count only after "Right". Fixed rules, no model, everything stays on the Spark.'),[],menu));
  const m=E('div','fh');m.id='wissmsg';box.appendChild(m);
  box.appendChild(icTabs('wiss',[{k:'open',label:t('Zu klären','To sort out'),n:open||'',hot:open>0,body:wissOpenTab},
    {k:'int',label:t('Interessen','Interests'),n:yes.length,body:wissIntTab},
    {k:'rec',label:t('Wiederkehrend','Recurring'),n:d.recurring.length||'',body:wissRecTab},
    {k:'week',label:t('Woche & Gemerkt','Week & kept'),body:wissWeekTab}]))}
// Zu klären: the proposals (topics) and „Zu welchem Thema gehört das?“ for senders confirmed earlier
function wissOpenTab(){const d=WISS,E=icEl,w=E('div');
  if(!d.proposals.length&&!(d.asks||[]).length){w.appendChild(icEmpty((d.loading||[]).length?t('Lese die Kopfzeilen deiner Mails …','Reading your mail headers …')
    :t('Nichts zu klären. Neue Vorschläge kommen mit der nächsten Lesung von Für dich.','Nothing to sort out. New proposals come with the next reading of For you.')));return w}
  if(d.proposals.length){w.appendChild(icGroup(t('Vorschläge','Proposals'),d.proposals.length));
    w.appendChild(icList(d.proposals.map(x=>{const ok=wissB(t('Stimmt','Right'),()=>wissSet(x.name,'yes',{src:x.src,topic:x.topic||'',senders:x.senders||[],label:wissName(x)}),'b p');ok.dataset.wissYes=x.name;
      const nope=wissB(t('Nicht so','Not really'),()=>wissSet(x.name,'no',{src:x.src,topic:x.topic||''}));nope.dataset.wissNo=x.name;
      return icRow(wissProposal(x),t('Beleg: ','Evidence: ')+x.why,[ok,nope])})))}
  if((d.asks||[]).length){w.appendChild(icGroup(t('Zu welchem Thema gehört das?','Which topic is this?'),d.asks.length));
    w.appendChild(icList(d.asks.map(x=>{const lab=L==='en'?x.en:x.label;
      const ok=wissB(t('Übernehmen','Take it'),()=>wissSet(x.name,'adopt',{topic:x.topic,label:lab}),'b p');ok.dataset.wissAdopt=x.name;
      const keep=wissB(t('So lassen','Leave it'),()=>wissSet(x.name,'keep'));keep.dataset.wissKeep=x.name;
      return icRow(t(`„${x.name}“ gehört wohl zu ${lab}`,`"${x.name}" seems to belong to ${lab}`),t('Du hast den Absender früher bestätigt. Als Thema passen auch neue Absender, und der Netz-Tipp sucht nach dem Thema.','You confirmed the sender before. As a topic, new senders fit too and the web tip searches for the topic.'),[ok,keep])})))}
  return w}
// Interessen: the list, „＋ Interesse hinzufügen“ and „Nicht so“ folded below it; the details beside it
function wissIntTab(){const d=WISS,E=icEl,yes=d.interests.filter(x=>x.state==='yes'),no=d.interests.filter(x=>x.state==='no');
  if(!yes.some(x=>x.name===WISS_SEL))WISS_SEL=NARROW()?'':(yes[0]||{}).name||'';
  const w=E('div','ld-box wiss-int'+(WISS_SEL?' ld-sel':'')),split=E('div','ld-split'),list=E('div','ld-list'),det=E('div','ld-detail');split.append(list,det);w.appendChild(split);
  for(const x of yes){const r=E('div','ld-row'+(x.name===WISS_SEL?' on':''));r.setAttribute('role','button');r.tabIndex=0;r.dataset.wissRow=x.name;
    const mid=E('span','ld-mid');mid.appendChild(E('b','',wissName(x)));const n=(x.senders||[]).length;
    mid.appendChild(E('small',x.old?'wiss-old':'',x.old?t('alter Absender, Thema fehlt','old sender, no topic yet'):n?(n===1?x.senders[0]:t(`${n} Absender`,`${n} senders`)):(d.sources[x.src]||[])[L==='en'?1:0]||''));
    r.appendChild(mid);if(x.web){const rt=E('span','ld-right');rt.appendChild(E('span','ld-badge read',t('Netz-Tipps','Web tips')));r.appendChild(rt)}
    const go=()=>{WISS_SEL=x.name;WISS_EDIT='';wissRender()};r.onclick=go;r.onkeydown=e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();go()}};list.appendChild(r)}
  if(!yes.length)list.appendChild(icEmpty(t('Noch keine. Sag zu einem Vorschlag „Stimmt“ oder trag selbst etwas ein.','None yet. Say "Right" to a proposal or add one yourself.')));
  if(WISS_ADD){const add=E('form','row wiss-add');const inp=E('input');inp.id='wissadd';inp.maxLength=40;inp.placeholder=t('z. B. Rennrad','e.g. road bike');inp.setAttribute('list','wisstopics');
    const go=E('button','b p',t('Hinzufügen','Add'));go.type='submit';add.append(inp,go,wissB(t('Abbrechen','Cancel'),()=>{WISS_ADD=false;wissRender()}));
    add.onsubmit=e=>{e.preventDefault();const v=inp.value.trim();if(v.length>=2){WISS_ADD=false;WISS_SEL=v;wissSet(v,'yes',{src:'hand'})}};list.appendChild(add);setTimeout(()=>inp.focus(),0)}
  else{const a=E('div','ld-more');const b=wissB(t('＋ Interesse hinzufügen','＋ Add an interest'),()=>{WISS_ADD=true;wissRender()});b.dataset.wissAddOpen='1';a.appendChild(b);list.appendChild(a)}
  if(no.length){const f=E('details','wiss-no');f.appendChild(E('summary','',t(`Nicht so (${no.length})`,`Not really (${no.length})`)));
    f.appendChild(icList(no.map(x=>icRow(x.name,'',[wissB(t('Wieder vorschlagen dürfen','May be proposed again'),()=>wissSet(x.name,'forget'))]))));list.appendChild(f)}
  const x=yes.find(v=>v.name===WISS_SEL);det.hidden=!x;if(x)wissDetail(det,x);
  return w}
function wissDetail(det,x){const d=WISS,E=icEl;
  const back=wissB('‹ '+t('Interessen','Interests'),()=>{WISS_SEL='';WISS_EDIT='';wissRender()},'b ld-back');det.appendChild(back);
  det.appendChild(E('h3','',wissName(x)));
  det.appendChild(E('small','ic-meta',x.old?t('Früher bestätigter Absender: gib ihm unten ein Thema, dann bleibt er als Absender darunter.','Sender confirmed earlier: give it a topic below, then it stays as a sender under it.')
    :(d.sources[x.src]||[])[L==='en'?1:0]||''));
  if((x.senders||[]).length){det.appendChild(E('div','ic-gl wiss-dl',t('Absender','Senders')));const c=E('div','wiss-chips');
    for(const n of x.senders){const ch=E('span','chip',n+' ');const b=E('button','b');b.appendChild(icNode('x'));b.type='button';b.title=t('Diesen Absender herausnehmen','Take this sender out');b.setAttribute('aria-label',b.title);
      b.dataset.wissDrop=n;b.onclick=()=>wissSet(x.name,'drop',{senders:[n]});ch.appendChild(b);c.appendChild(ch)}det.appendChild(c)}
  det.appendChild(E('div','ic-gl wiss-dl',t('Name und Thema','Name and topic')));
  if(WISS_EDIT===x.name)det.appendChild(wissEditForm(x));
  else{const ed=wissB('✎ '+t('Umbenennen oder Thema zuordnen','Rename or give a topic'),()=>{WISS_EDIT=x.name;wissRender()});ed.dataset.wissRename=x.name;det.appendChild(ed)}
  // the web tip as a switch with words (Dominik 2026-10-22: a bare magnifier said nothing); its last tip below it
  if(d.tips){const sw=E('div','ld-sw');const l=E('span');l.appendChild(E('b','',t('Tipps aus dem Netz','Tips from the web')));l.appendChild(E('br'));
    l.appendChild(E('small','mut',t('Höchstens ein Tipp am Tag, zwischen 10 und 19 Uhr. An die Suche geht nur dieses Wort.','At most one tip a day, between 10 am and 7 pm. Only this word goes to the search.')));
    const g=E('label','tgl'),i=E('input');i.type='checkbox';i.checked=!!x.web;i.dataset.wissWeb=x.name;i.setAttribute('aria-label',t('Tipps aus dem Netz','Tips from the web'));
    i.onchange=()=>wissSet(x.name,'yes',{web:i.checked,src:x.src,tip:1,label:wissName(x)});g.append(i,E('i'));sw.append(l,g);det.appendChild(sw);
    if(d.tip&&d.tip.url&&(d.tip.name||'').toLowerCase()===x.name.toLowerCase())det.appendChild(wissTip(d.tip))}
  const acts=E('div','ld-acts');const f=wissB(t('Vergessen','Forget'),()=>{WISS_SEL='';wissSet(x.name,'forget')},'b danger');f.dataset.wissForget=x.name;acts.appendChild(f);det.appendChild(acts)}
// ✎ at a confirmed interest: rename it or give it a topic (Dominik 2026-10-22 „nicht löschbar oder bearbeitbar“); an
// older confirmed sender becomes a sender of the topic it gets
function wissEditForm(x){const E=icEl,f=E('form','row wiss-edit'),pick=E('select'),inp=E('input');pick.dataset.wissEditPick=x.name;
  pick.appendChild(E('option','',t('Thema wählen …','Pick a topic …'))).value='';
  for(const c of (WISS.choices||[]).filter(c=>c.name!==x.name)){const o=E('option','',wissName(c));o.value=c.name;pick.appendChild(o)}
  pick.onchange=()=>{if(pick.value)inp.value=pick.value};
  inp.maxLength=40;inp.value=x.name;inp.setAttribute('list','wisstopics');inp.dataset.wissEdit=x.name;
  const go=E('button','b p',t('Speichern','Save'));go.type='submit';f.append(pick,inp,go,wissB(t('Abbrechen','Cancel'),()=>{WISS_EDIT='';wissRender()}));
  f.onsubmit=e=>{e.preventDefault();const v=inp.value.trim();if(v.length<2)return;WISS_EDIT='';WISS_SEL=v;wissSet(x.name,'rename',{to:v,label:v})};
  return f}
// the tip of the day: its title as text, the link only in a new tab without the Spark's address
function wissTip(tip){const a=icEl('a','b',t('Öffnen','Open'));a.href=tip.url;a.target='_blank';a.rel='noopener noreferrer';
  return icList([icRow(tip.title,t('Tipp zu „','Tip for "')+tip.name+t('“ · ','" · ')+tip.domain,[a])])}
// Wiederkehrend (6a)
function wissRecTab(){const d=WISS,w=icEl('div');
  if(d.recurring.length)w.appendChild(icList(d.recurring.map(x=>{const b=wissB(x.set?t('Erinnerung ist da','Reminder is set'):t('Monatlich erinnern','Remind me monthly'),async()=>{b.disabled=true;
      try{const r=await wissCall('/api/profile/ichweiss/recurring',{id:x.id});wissMsg(r.again?t('Diese Erinnerung gibt es schon.','This reminder exists already.'):t('Monatliche Erinnerung gesetzt: ','Monthly reminder set: ')+r.text)}catch(e){b.disabled=false;wissMsg(e.message,true)}});
      b.disabled=!!x.set;b.dataset.wissRec=x.id;
      return icRow(t('Rechnung ','Bill ')+x.who+t(' kommt um den ',' comes around the ')+x.day+'.',t(`in ${x.months} Monaten`,`in ${x.months} months`),[b])})));
  else w.appendChild(icEmpty((d.loading||[]).includes('wiederkehrend')?t('Lese die Kopfzeilen deiner Mails …','Reading your mail headers …'):t('Nichts gefunden, was jeden Monat kommt.','Nothing found that comes every month.')));
  return w}
// Woche & Gemerkt: the week, this month's sum, the tip of the day, the memory and the mail style with the ways there
function wissWeekTab(){const d=WISS,w=icEl('div');
  w.appendChild(icGroup(t('Diese Woche','This week'),''));
  w.appendChild(icList([icRow(d.week.sentence,'',[]),icRow(d.month.line,t('nur geprüfte Beträge aus Rechnungen und Bestellungen dieses Monats','only checked amounts of this month\'s bills and orders'),[])]));
  if(d.tip&&d.tip.url){w.appendChild(icGroup(t('Aus dem Netz','From the web'),1));w.appendChild(wissTip(d.tip))}
  w.appendChild(icGroup(t('Gemerkt','Kept'),d.facts.count));
  const rows=d.facts.items.map(x=>icRow(x,'',[]));
  rows.push(icRow(t(`${d.facts.count} gemerkte Fakten`,`${d.facts.count} facts kept`),t('Ändern und vergessen unter Ich → Gedächtnis','Change and forget under Me → Memory'),[]));
  if(d.style&&d.style.mails)rows.push(icRow(t(`Mailstil aus ${d.style.mails} eigenen Mails gelernt`,`Mail style learned from ${d.style.mails} own mails`),t('Ansehen unter E-Mail → Einstellungen','See it under E-mail → Settings'),[]));
  w.appendChild(icList(rows));return w}
