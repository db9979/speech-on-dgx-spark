// The assistant speaks up by itself (see proactive.py): notes arrive while the page is open and are
// spoken like a reminder; the "Ich" window page "Von selbst" sets everything, all off by default.
let PRO_ON=false;
const pro={since:Date.now()-10*60e3,seen:new Set(),busy:false,greeted:0,
  on(){return PRO_ON&&!!PROFILE&&!!S.pro_on},
  async poll(){if(!this.on()||document.hidden||this.busy)return;this.busy=true;
    try{const r=await fetch('/api/proactive?since='+this.since);if(r.ok)for(const x of (await r.json()).items)this.show(x)}catch{}
    this.busy=false},
  async greet(){if(!this.on()||document.hidden||Date.now()-this.greeted<10*60e3)return;this.greeted=Date.now();
    try{const r=await fetch('/api/proactive/greet',{method:'POST'});const d=r.ok?await r.json():{};if(d.item)this.show(d.item)}catch{}},
  // a note is said on one device only: the first that plays it takes it on the Spark, the others stay silent
  async show(x){if(this.seen.has(x.id))return;this.seen.add(x.id);this.since=Math.max(this.since,x.t);
    try{const r=await api('/api/proactive/played',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id:x.id})});
      if(r.ok&&!(await r.json()).play)return}catch{}
    const b=chatLog('assistant',x.text);b.classList.add('pro');
    const m={role:'assistant',content:x.text,...(x.mail?{mail:true}:{outside:true})};chat.msgs.push(m);deletable(b,m);saveConvo();
    const row=document.createElement('div');row.className='prorow';   // quick feedback, same as saying it
    row.innerHTML=`<button type="button" class="ib" data-v="more" title="${t('Gut so','Good')}">👍</button><button type="button" class="ib" data-v="less">${t('Weniger davon','Less of this')}</button><button type="button" class="ib" data-v="pause">${t('Nicht jetzt','Not now')}</button>`;
    row.querySelectorAll('button').forEach(btn=>btn.onclick=async()=>{const v=btn.dataset.v;
      row.innerHTML=`<small class="mut">${v==='pause'?t('Gut, zwei Stunden Ruhe.','OK, quiet for two hours.'):v==='less'?t('Gemerkt, kommt seltener.','Noted, less often.'):t('Danke.','Thanks.')}</small>`;
      try{await api('/api/proactive/feedback',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({kind:x.kind,vote:v})})}catch{}});
    b.appendChild(row);chime();
    if(document.hidden)try{if(window.Notification&&Notification.permission==='granted')new Notification('💬 Spark',{body:x.text,tag:x.id})}catch{}
    if(chat.rec||chat.ctrl||playing())return;   // a conversation is running: the bubble and the chime suffice
    sayText(x.text)}};
setInterval(()=>pro.poll(),20000);
setTimeout(()=>{pro.greet();pro.poll()},4000);
document.addEventListener('visibilitychange',()=>{if(!document.hidden){pro.greet();pro.poll()}});

// ---------------------------------------------------------------- "Ich" → Von selbst
const PROK=[['pro_events','calendar',t('Termin-Vorlauf','Upcoming appointments'),t('Kurz vor einem Termin, z. B. „In 20 Minuten: Zahnarzt.“, mit dem Angebot, dich 5 Minuten vorher noch einmal zu erinnern. Ein „Ja“ setzt die Erinnerung.','Shortly before an appointment, e.g. "In 20 minutes: dentist.", offering a reminder 5 minutes before. A "yes" sets it.'),t('Kalender verbinden','connect a calendar')],
  ['pro_ha','ha',t('Smart-Home-Regeln','Smart home rules'),t('Meldet sich, wenn eine deiner Regeln zutrifft. Dabei wird nur gelesen, nie geschaltet.','Speaks up when one of your rules applies. Only reads, never switches.'),t('Home Assistant verbinden','connect Home Assistant')],
  ['pro_greet','',t('Begrüßung','Greeting'),t('Öffnest du das Gespräch nach mindestens drei Stunden Pause, nennt der Assistent den nächsten Termin oder die nächste Erinnerung von heute. Gibt es nichts, sagt er nichts.','When you open the conversation after three hours or more, the assistant names the next appointment or reminder of today. If there is none, it says nothing.'),''],
  ['pro_follow','history',t('Nachfragen','Follow-ups'),t('Höchstens einmal am Tag (10 bis 20 Uhr) fragt er nach einem Vorhaben, das du gestern erwähnt hast, z. B. „Hat das mit dem Angebot geklappt?“. Nur wenn es wörtlich in deinen Nachrichten steht.','At most once a day (10 am to 8 pm) it asks about a plan you mentioned yesterday. Only when it is literally in your messages.'),t('vom Admin abgeschaltet','turned off by the admin')],
  ['pro_mail','mail',t('Wichtige Mails','Important mail'),t('Neue Mail von Absendern auf deiner Liste: Absender und Betreff, nie der Inhalt.','New mail from senders on your list: sender and subject, never the content.'),t('Postfach verbinden','connect a mailbox')],
  ['pro_tidy','mail',t('Postfach aufräumen','Inbox tidying'),t('Höchstens einmal am Tag: wenn beim Aufräumen drei oder mehr Absender unklar sind, nach einer Woche Vorschau und wenn ein Durchlauf angehalten hat.','At most once a day: when three or more senders are unclear while tidying, after a week of preview and when a run stopped.'),t('Postfach verbinden','connect a mailbox')],
  ['pro_weather','search',t('Wetterhinweis','Weather note'),t('Einmal am Tag zur gewählten Uhrzeit, wenn für morgen Regen, Frost, Sturm oder Hitze vorhergesagt ist (über Wetter, sonst die Websuche).','Once a day at the chosen time, when rain, frost, storm or heat is forecast for tomorrow (via weather, else web search).'),t('Websuche ist aus','web search is off')],
  ['pro_bday','contacts',t('Geburtstage','Birthdays'),t('Morgens (8 bis 11 Uhr), wenn heute jemand aus deinen Kontakten Geburtstag hat.','In the morning (8 to 11 am), when someone in your contacts has a birthday today.'),t('Kontakte einschalten','switch on contacts')],
  ['pro_parcel','parcels',t('Paket kommt heute','Parcel comes today'),t('Wenn eine Versandmail sagt, dass ein Paket heute kommt (7 bis 20 Uhr, einmal pro Paket).','When a shipping mail says a parcel comes today (7 am to 8 pm, once per parcel).'),t('Pakete einschalten','switch on parcels')],
  ['pro_transit','transit',t('Bus und Bahn','Bus and train'),t('An deinen Pendeltagen 45 bis 5 Minuten vor deiner Abfahrt: wenn die Verbindung 5 Minuten oder mehr Verspätung hat oder ausfällt. Höchstens einmal am Tag.','On your commute days 45 to 5 minutes before you leave: when the connection is 5 minutes or more late or cancelled. At most once a day.'),t('Bus und Bahn mit Pendelstrecke einrichten','set up bus and train with a commute')]];
let PROST=null;
const proRow=(k,l,h,extra='')=>setRow(esc(l),esc(h),tglIn(`data-k="${k}"`,S[k]),{extra});
async function showPro(){const box=$('probox');if(!PROFILE||!PRO_ON){box.innerHTML='';return}
  PROST=await (await api('/api/proactive/status')).json();const st=PROST;
  const [qa,qb]=(S.pro_quiet||'').split('-');
  const lowered=st.kinds.filter(x=>x.cap<x.full);
  box.innerHTML=`<div class="intro">${t('Der Assistent meldet sich von selbst, wenn wirklich etwas ist: nur aus deinem Kalender, deinen Regeln, Mails und Gesprächen, nie geraten. Ist das Gespräch offen, sagt er es, sonst kommt eine Mitteilung. Alles hier gilt nur für dich, und alles ist aus, bis du es einschaltest.','The assistant speaks up by itself when something real happens: only from your calendar, rules, mail and conversations, never guessed. With the conversation open it says it, otherwise a notification arrives. Everything here is yours only and off until you switch it on.')}</div>`+
    proRow('pro_on',t('Von selbst melden','Speak up by itself'),t('Hauptschalter für alles darunter.','Main switch for everything below.'))+
    `<div id="probody"${S.pro_on?'':' style="opacity:.55"'}>
    <div class="two2"><div><label>${t('Ruhezeit von','Quiet from')}</label><input type="time" id="proqa" value="${esc(qa||'')}"></div><div><label>${t('bis','until')}</label><input type="time" id="proqb" value="${esc(qb||'')}"></div></div>
    <div class="fh">${t('In der Ruhezeit kommt nichts. Beide Felder leer: keine Ruhezeit.','Nothing arrives during quiet hours. Both empty: no quiet hours.')}</div>
    <label>${t('Höchstens Meldungen am Tag','At most notes a day')}</label><select id="promax" style="max-width:120px">${[1,2,3,4,6,8,10,15,20,30].map(n=>`<option${n===S.pro_max?' selected':''}>${n}</option>`).join('')}</select>
    <div class="fh">${t('Heute: ','Today: ')}${st.today} ${t('von','of')} ${S.pro_max}${st.paused_until?' · '+t('Pause bis ','paused until ')+new Date(st.paused_until*1000).toLocaleTimeString([], {hour:'2-digit',minute:'2-digit'})+` <button class="b" type="button" id="proresume">${t('Pause beenden','End pause')}</button>`:''}</div>`+
    PROK.map(([k,need,l,h,miss])=>proRow(k,l,h,(need&&!st.has[need]&&!(k==='pro_weather'&&st.has.weather)?`<span class="err" style="display:block">${t('Noch nicht möglich: ','Not possible yet: ')}${esc(miss)}</span>`:'')+(PROX[k]?PROX[k](st):''))).join('')+
    proRow('pro_learn',t('Mitlernen','Learn from feedback'),t('Sagst du nach einer Meldung „Nicht jetzt“, ist zwei Stunden Ruhe. Bei „Das interessiert mich nicht“ oder „Weniger davon“ meldet er sich zu dieser Art nur noch halb so oft.','After a note, "not now" means two hours of quiet. "Not interested" or "less of this" halves how often that kind may speak.'),
      lowered.length?`<span style="display:block;margin-top:4px">${lowered.map(x=>`${esc(x.label)}: ${x.cap?t('höchstens ','at most ')+x.cap+t(' am Tag',' a day'):t('aus','off')}`).join(' · ')} <button class="b" type="button" id="proreset">${t('Zurücksetzen','Reset')}</button></span>`:'')+
    `<div class="row" style="margin-top:10px"><button class="b" type="button" id="protest">${t('Ausprobieren','Try it')}</button><span id="protmsg" class="fh"></span></div>
    <div class="fh">${t('Was er von selbst gesagt hat und warum, steht im Protokoll.','What it said by itself and why is in the log.')}</div></div>`;
  box.querySelectorAll('input[data-k]').forEach(e=>e.onchange=()=>{if(e.dataset.k==='pro_on'&&e.checked)saveSet('tz',TZ());saveSet(e.dataset.k,e.checked);if(e.dataset.k==='pro_on')showPro()});
  const quiet=()=>{const a=$('proqa').value,b=$('proqb').value;if(!!a!==!!b)return;saveSet('pro_quiet',a?a+'-'+b:'')};
  $('proqa').onchange=$('proqb').onchange=quiet;
  $('promax').onchange=()=>saveSet('pro_max',Number($('promax').value));
  if($('proresume'))$('proresume').onclick=async()=>{await api('/api/proactive/feedback',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({vote:'resume'})});showPro()};
  if($('proreset'))$('proreset').onclick=async()=>{await api('/api/proactive/feedback',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({vote:'reset'})});showPro()};
  $('protest').onclick=async()=>{$('protmsg').textContent='';try{const d=await (await api('/api/proactive/test',{method:'POST'})).json();
      $('protmsg').textContent=d.item&&d.item.pushed?t('Als Mitteilung geschickt.','Sent as a notification.'):t('Kommt gleich hier im Gespräch.','Arrives here in the conversation shortly.');setTimeout(()=>pro.poll(),300)}
    catch(e){$('protmsg').textContent=e.message}};
  for(const f of Object.values(PROBIND))f()}
// extra fields under a kind, and their handlers
const PROX={
  pro_events:()=>`<span style="display:block;margin-top:4px">${t('Wie lange vorher: ','How long before: ')}<select id="prolead" style="width:auto">${[5,10,15,20,30,45,60].map(n=>`<option value="${n}"${n===S.pro_lead?' selected':''}>${n} ${t('Minuten','minutes')}</option>`).join('')}</select></span>`,
  pro_mail:()=>`<input id="promailfrom" style="margin-top:4px" placeholder="${t('z. B. chef@firma.de, Schule, Anna','e.g. boss@company.com, school, Anna')}" value="${esc(S.pro_mail_from||'')}" autocomplete="off"><span style="display:block">${t('Absender, mit Komma getrennt; ein Teil der Adresse oder des Namens genügt.','Senders, separated by commas; part of the address or name is enough.')}</span>`,
  pro_weather:()=>`<span class="two2" style="margin-top:4px"><input id="proplace" placeholder="${t('Ort, z. B. Köln','Place, e.g. Cologne')}" value="${esc(S.pro_place||'')}" autocomplete="off"><input type="time" id="proweatherat" value="${esc(S.pro_weather_at||'18:00')}"></span>`,
  pro_ha:st=>!st.has.ha?'':`<ul class="facts small" style="margin-top:6px">${st.rules.map(r=>`<li><span>${esc(r.line)}${r.text?`<br><small class="mut">„${esc(r.text)}“</small>`:''}</span><button class="b" type="button" ${onAttr('proRuleDel',r.id)}>${t('Löschen','Delete')}</button></li>`).join('')||`<li class="mut">${t('Noch keine Regel.','No rule yet.')}</li>`}</ul>
    <details id="proruleadd"><summary>${t('Regel hinzufügen','Add a rule')}</summary>
      ${proCond('1')}
      <details><summary>${t('und eine zweite Bedingung','and a second condition')}</summary>${proCond('2')}</details>
      <div class="two2"><div><label>${t('Mindestens so lange (Minuten)','For at least (minutes)')}</label><input id="promin" inputmode="numeric" value="0"></div><div><label>${t('Eigene Meldung (leer = automatisch)','Own message (empty = automatic)')}</label><input id="protext" autocomplete="off"></div></div>
      <div class="row" style="margin-top:8px"><button class="b p" type="button" id="proruleok">${t('Prüfen und hinzufügen','Check and add')}</button><span id="prorulemsg" class="fh"></span></div>
      <span style="display:block">${t('Beispiele: „Whirlpool“ über 37,5 · „Bad Fenster“ ist offen und „Regen“ ist an · „Waschmaschine Leistung“ unter 5, mindestens 3 Minuten. Eine Regel meldet sich erst, nachdem sie einmal nicht zugetroffen hat, und dann einmal, bis sie wieder nicht zutrifft.','Examples: "Whirlpool" above 37.5 · "Bathroom window" is open and "Rain" is on · "Washing machine power" below 5, at least 3 minutes. A rule speaks only after it was false once, then once until it is false again.')}</span></details>`};
const proCond=n=>`<div class="two2"><div><label>${t('Gerät oder Sensor','Device or sensor')}</label><input id="proent${n}" placeholder="${t('Name oder entity_id','name or entity_id')}" autocomplete="off"></div><div><label>${t('Bedingung','Condition')}</label><span class="rowin"><select id="proop${n}" style="width:auto"><option value="above">${t('über','above')}</option><option value="below">${t('unter','below')}</option><option value="is">${t('ist','is')}</option><option value="changes">${t('ändert sich','changes')}</option></select><input id="proval${n}" placeholder="${t('z. B. 38 oder offen','e.g. 38 or open')}" autocomplete="off"></span></div></div>`;
const PROBIND={
  lead(){if($('prolead'))$('prolead').onchange=()=>saveSet('pro_lead',Number($('prolead').value))},
  mail(){if($('promailfrom'))$('promailfrom').onchange=()=>saveSet('pro_mail_from',$('promailfrom').value.trim().slice(0,300))},
  weather(){if($('proplace')){$('proplace').onchange=()=>saveSet('pro_place',$('proplace').value.trim().slice(0,60));$('proweatherat').onchange=()=>{if($('proweatherat').value)saveSet('pro_weather_at',$('proweatherat').value)}}},
  rule(){if(!$('proruleok'))return;$('proruleok').onclick=async()=>{const m=$('prorulemsg');m.className='fh';m.textContent=t('Prüfe in Home Assistant …','Checking in Home Assistant …');
    const conds=['1','2'].map(n=>({entity:$('proent'+n).value.trim(),op:$('proop'+n).value,value:$('proval'+n).value.trim()})).filter(c=>c.entity);
    const r=await fetch('/api/proactive/rules',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({conds,minutes:Number($('promin').value)||0,text:$('protext').value.trim()})});
    const d=await r.json();if(!r.ok){m.className='fh err';m.textContent=d.detail||r.status;return}showPro()}}};
window.proRuleDel=async id=>{await api('/api/proactive/rules/'+encodeURIComponent(id),{method:'DELETE'});showPro()};
ON.proRuleDel=(b,id)=>proRuleDel(id);
