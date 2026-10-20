// Ich → Was ich über dich weiß (ichweiss.py, plan persoenlicher-assistent, stages 3 and 4): interests with their evidence
// (count only after „Stimmt“), what comes back every month, the week, this month's sums, the tip from the web and what
// the memory and the mail style hold. Names of shops and titles from the web are outside text: textContent only; the
// web tip's address opens only as an https link in a new tab, without the Spark's address (noreferrer).
let WISS_ON=false,WISS=null;
const wissMsg=(x,err)=>{const m=$('wissmsg');if(m){m.textContent=x||'';m.className='fh'+(err?' err':'')}};
async function wissCall(path,body,method='POST'){const r=await api(path,{method,headers:{'Content-Type':'application/json'},body:body?JSON.stringify(body):undefined});return r.json()}
async function showWiss(){const box=$('wissbox');if(!box)return;if(!PROFILE||!WISS_ON){box.textContent='';return}
  if(!WISS){box.textContent='';box.appendChild(icEl('div','fh',t('Einen Moment …','One moment …')))}
  try{WISS=await (await api('/api/profile/ichweiss')).json()}catch(e){box.textContent='';box.appendChild(icEl('div','fh err',e.message));return}
  wissRender();if((WISS.loading||[]).length)setTimeout(()=>{if(box.isConnected&&!box.hidden)showWiss()},4000)}
async function wissSet(name,state,extra={}){try{await wissCall('/api/profile/ichweiss/interest',Object.assign({name,state},extra))}catch(e){wissMsg(e.message,true);return}
  await showWiss();wissMsg(state==='yes'?t('Gemerkt: „','Noted: "')+name+t('“ interessiert dich.','" interests you.'):state==='no'?t('Kommt nicht wieder als Vorschlag.','Will not be proposed again.'):t('Vergessen.','Forgotten.'))}
function wissRender(){const d=WISS,box=$('wissbox'),E=icEl;if(!box||!d)return;box.textContent='';
  box.appendChild(E('h3','sec',t('Was ich über dich weiß','What I know about you')));
  box.appendChild(E('div','intro',t('Was der Spark über dich weiß und woher: Interessen zählen erst, wenn du „Stimmt“ sagst; alles hier kannst du ändern oder vergessen. Feste Regeln, kein Modell, alles bleibt auf dem Spark.',
    'What the Spark knows about you and where from: interests count only once you say "Right"; you can change or forget everything here. Fixed rules, no model, everything stays on the Spark.')));
  const yes=d.interests.filter(x=>x.state==='yes'),no=d.interests.filter(x=>x.state==='no');
  const menu=[{label:t('Alle Interessen vergessen','Forget every interest'),danger:true,act:async()=>{if(!confirm(t('Alle Interessen und den Tipp aus dem Netz vergessen?','Forget every interest and the web tip?')))return;
    try{await api('/api/profile/ichweiss',{method:'DELETE'})}catch(e){wissMsg(e.message,true);return}await showWiss()}}];
  box.appendChild(icCard('spark',t('Was ich über dich weiß','What I know about you'),t(`${yes.length} Interessen · ${d.proposals.length} Vorschläge`,`${yes.length} interests · ${d.proposals.length} proposals`),[],menu));
  const m=E('div','fh');m.id='wissmsg';box.appendChild(m);
  // Diese Woche, Diesen Monat (stage 4)
  box.appendChild(icGroup(t('Diese Woche','This week'),''));
  box.appendChild(icList([icRow(d.week.sentence,'',[]),icRow(d.month.line,t('nur geprüfte Beträge aus Rechnungen und Bestellungen dieses Monats','only checked amounts of this month\'s bills and orders'),[])]));
  if(d.proposals.length){box.appendChild(icGroup(t('Vorschläge','Proposals'),d.proposals.length));
    box.appendChild(icList(d.proposals.map(x=>{const ok=icBtn('check',t('Stimmt','Right'),()=>wissSet(x.name,'yes',{src:x.src}));ok.dataset.wissYes=x.name;
      const nope=icBtn('x',t('Nicht so','Not really'),()=>wissSet(x.name,'no',{src:x.src}));nope.dataset.wissNo=x.name;
      return icRow(x.name,t('Beleg: ','Evidence: ')+x.why,[ok,nope])})))}
  box.appendChild(icGroup(t('Interessen','Interests'),yes.length));
  const add=E('form','row');const inp=E('input');inp.id='wissadd';inp.maxLength=40;inp.placeholder=t('z. B. Rennrad','e.g. road bike');const go=E('button','b',t('Hinzufügen','Add'));go.type='submit';
  add.appendChild(inp);add.appendChild(go);add.onsubmit=e=>{e.preventDefault();const v=inp.value.trim();if(v.length>=2)wissSet(v,'yes',{src:'hand'})};
  box.appendChild(add);
  if(yes.length)box.appendChild(icList(yes.map(x=>{const src=(d.sources[x.src]||[])[L==='en'?1:0]||'';const acts=[];
      if(d.tips){const w=icBtn('search',x.web?t('Keine Tipps aus dem Netz','No tips from the web'):t('Tipps aus dem Netz','Tips from the web'),()=>wissSet(x.name,'yes',{web:!x.web,src:x.src}),x.web?'on':'');w.dataset.wissWeb=x.name;acts.push(w)}
      const f=icBtn('trash',t('Vergessen','Forget'),()=>wissSet(x.name,'forget'));f.dataset.wissForget=x.name;acts.push(f);
      return icRow(x.name,[src,x.web?t('Tipps aus dem Netz an','tips from the web on'):''].filter(Boolean).join(' · '),acts)})));
  else box.appendChild(icEmpty(t('Noch keine. Sag zu einem Vorschlag „Stimmt“ oder trag selbst etwas ein.','None yet. Say "Right" to a proposal or add one yourself.')));
  if(no.length){box.appendChild(icGroup(t('Nicht so','Not really'),no.length));
    box.appendChild(icList(no.map(x=>{const f=icBtn('trash',t('Wieder vorschlagen dürfen','May be proposed again'),()=>wissSet(x.name,'forget'));return icRow(x.name,'',[f])})))}
  // Aus dem Netz (4a): one tip a day for an interest with „Tipps aus dem Netz“
  if(d.tip&&d.tip.url){box.appendChild(icGroup(t('Aus dem Netz','From the web'),1));
    const a=E('a','b',t('Öffnen','Open'));a.href=d.tip.url;a.target='_blank';a.rel='noopener noreferrer';
    box.appendChild(icList([icRow(d.tip.title,t('Tipp zu „','Tip for "')+d.tip.name+t('“ · ','" · ')+d.tip.domain,[a])]))}
  else if(d.tips&&yes.some(x=>x.web))box.appendChild(E('div','fh',t('Höchstens ein Tipp am Tag, zwischen 10 und 19 Uhr. An die Suche geht nur das Wort deines Interesses.','At most one tip a day, between 10 am and 7 pm. Only your interest\'s word goes to the search.')));
  // Wiederkehrendes (6a)
  box.appendChild(icGroup(t('Wiederkehrendes','Recurring'),d.recurring.length));
  if(d.recurring.length)box.appendChild(icList(d.recurring.map(x=>{const b=icBtn('bell',x.set?t('Erinnerung ist da','Reminder is set'):t('Monatlich erinnern','Remind me monthly'),async b=>{b.disabled=true;
      try{const r=await wissCall('/api/profile/ichweiss/recurring',{id:x.id});wissMsg(r.again?t('Diese Erinnerung gibt es schon.','This reminder exists already.'):t('Monatliche Erinnerung gesetzt: ','Monthly reminder set: ')+r.text)}catch(e){b.disabled=false;wissMsg(e.message,true)}});
      b.disabled=!!x.set;b.dataset.wissRec=x.id;
      return icRow(t('Rechnung ','Bill ')+x.who+t(' kommt um den ',' comes around the ')+x.day+'.',t(`in ${x.months} Monaten`,`in ${x.months} months`),[b])})));
  else box.appendChild(icEmpty((d.loading||[]).includes('wiederkehrend')?t('Lese die Kopfzeilen deiner Mails …','Reading your mail headers …'):t('Nichts gefunden, was jeden Monat kommt.','Nothing found that comes every month.')));
  // Gemerkt: the memory and the mail style, each with the way to its page
  box.appendChild(icGroup(t('Gemerkt','Kept'),d.facts.count));
  const rows=d.facts.items.map(x=>icRow(x,'',[]));
  rows.push(icRow(t(`${d.facts.count} gemerkte Fakten`,`${d.facts.count} facts kept`),t('Ändern und vergessen unter Ich → Gedächtnis','Change and forget under Me → Memory'),[]));
  if(d.style&&d.style.mails)rows.push(icRow(t(`Mailstil aus ${d.style.mails} eigenen Mails gelernt`,`Mail style learned from ${d.style.mails} own mails`),t('Ansehen unter E-Mail → Einstellungen','See it under E-mail → Settings'),[]));
  box.appendChild(icList(rows))}
